from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

from .config import Settings
from .fetchers.base import FetchError
from .fetchers.ical import ICalFetcher
from .fetchers.sunclass import SunclassScraper
from .comparator import match_reservations
from .logging_setup import configure_logging
from .models import AlertRecord, Discrepancy, DiscrepancyKind
from .notifiers import build_notifiers
from .notifiers.base import NotifierError
from .state import StateStore

EXIT_OK = 0
EXIT_DISCREPANCY = 1
EXIT_CONFIG_ERROR = 2
EXIT_FETCH_ERROR = 3

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sunclass-monitor",
        description="Compare Sunclass reservations against iCal feeds and report discrepancies.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect discrepancies but do not send any notifications.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override LOG_LEVEL from .env.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env).",
    )
    parser.add_argument(
        "--debug-browser",
        action="store_true",
        help=(
            "Show the Playwright browser window and slow down each action (500ms). "
            "Saves screenshots to data/ after login and after loading the table. "
            "Useful for diagnosing scraper failures."
        ),
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help=(
            "RARELY NEEDED. Mark all current discrepancies as already seen, "
            "suppressing the one-time batch of informational (>30 day) alerts. "
            "Has no effect on critical alerts (≤30 days) which always fire. "
            "Only use this if you are flooded with low-priority alerts you do not care about."
        ),
    )
    return parser


def _earliest_checkin(d: Discrepancy) -> date:
    return min(r.check_in for r in d.reservations)


def _split_by_urgency(
    discrepancies: list[Discrepancy], horizon: date
) -> tuple[list[Discrepancy], list[Discrepancy]]:
    """
    Split into (critical, informational).

    Critical: check_in within the horizon AND missing from Sunclass (the dangerous case).
    Informational: everything else — further out, or present in Sunclass but not iCal.
    """
    critical, informational = [], []
    for d in discrepancies:
        checkin = _earliest_checkin(d)
        is_urgent_window = checkin <= horizon
        is_missing_from_sunclass = d.kind in (
            DiscrepancyKind.ONLY_IN_ICAL,
            DiscrepancyKind.DATE_MISMATCH,
            DiscrepancyKind.SUSPICIOUS_MATCH,
        )
        if is_urgent_window and is_missing_from_sunclass:
            critical.append(d)
        else:
            informational.append(d)
    return critical, informational


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        settings = Settings.from_env(env_file=args.env_file)
    except (KeyError, ValueError) as e:
        print(f"CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    if args.debug_browser:
        settings.playwright_headless = False
        settings.playwright_slowmo = 500

    configure_logging(
        args.log_level or settings.log_level,
        settings.log_file_path,
    )

    logger.info("=== sunclass-monitor starting ===")

    today = date.today()
    horizon = today + timedelta(days=settings.critical_window_days)
    logger.info(
        "Checking future reservations from %s — critical window: %s to %s",
        today, today, horizon,
    )

    state = StateStore(settings.state_db_path)

    # ── Fetch iCal feeds ────────────────────────────────────────────────────
    ical_reservations = []
    for url, source, label in zip(
        settings.ical_urls, settings.ical_sources, settings.ical_labels
    ):
        fetcher = ICalFetcher(url=url, source=source, label=label, settings=settings)
        try:
            batch = fetcher.fetch()
            ical_reservations.extend(batch)
        except FetchError as e:
            logger.error("iCal fetch failed: %s", e)
            sys.exit(EXIT_FETCH_ERROR)

    # ── Scrape Sunclass portal ──────────────────────────────────────────────
    try:
        scraper = SunclassScraper(settings)
        scraped = scraper.fetch()
    except FetchError as e:
        logger.error("Sunclass scrape failed: %s", e)
        sys.exit(EXIT_FETCH_ERROR)

    # ── Filter to future reservations only ─────────────────────────────────
    ical_future = [r for r in ical_reservations if r.check_in >= today]
    scraped_future = [r for r in scraped if r.check_in >= today]

    logger.info(
        "After filtering to future: %d iCal interval(s), %d Sunclass reservation(s).",
        len(ical_future), len(scraped_future),
    )

    # ── Bootstrap mode (escape hatch, rarely needed) ────────────────────────
    if args.bootstrap:
        all_reservations = ical_future + scraped_future
        state.bootstrap_baseline(all_reservations)
        logger.warning(
            "Bootstrap: %d future reservation(s) marked as baseline. "
            "Note: critical (≤%d day) alerts will still fire on the next run.",
            len(all_reservations), settings.critical_window_days,
        )
        state.close()
        sys.exit(EXIT_OK)

    # ── Compare ─────────────────────────────────────────────────────────────
    discrepancies = match_reservations(
        ical_future,
        scraped_future,
        date_tolerance_days=settings.date_tolerance_days,
    )

    if not discrepancies:
        logger.info("No discrepancies found. All future reservations are consistent.")
        state.close()
        sys.exit(EXIT_OK)

    critical, informational = _split_by_urgency(discrepancies, horizon)

    logger.warning(
        "Found %d discrepancy(s): %d critical (≤%dd), %d informational.",
        len(discrepancies), len(critical), settings.critical_window_days, len(informational),
    )
    for d in sorted(critical, key=_earliest_checkin):
        logger.warning("  [CRITICAL] %s: %s", d.kind, d.detail)
    for d in sorted(informational, key=_earliest_checkin):
        logger.info("  [INFO] %s: %s", d.kind, d.detail)

    if args.dry_run:
        logger.info("Dry-run mode: skipping notifications.")
        state.close()
        sys.exit(EXIT_DISCREPANCY)

    # ── Notify ──────────────────────────────────────────────────────────────
    try:
        notifiers = build_notifiers(settings)
    except NotifierError as e:
        logger.error("Notifier configuration error: %s", e)
        state.close()
        sys.exit(EXIT_CONFIG_ERROR)

    for notifier in notifiers:
        now = datetime.utcnow()

        # Critical: always send — bypass idempotency (guest may arrive soon)
        if critical:
            try:
                notifier.send(critical, urgent=True)
                logger.info(
                    "Channel '%s': sent %d critical alert(s).",
                    notifier.channel_name, len(critical),
                )
            except Exception as e:
                logger.error(
                    "Channel '%s' failed on critical alerts: %s", notifier.channel_name, e
                )

        # Informational: send once, then suppress repeats
        unsent_info = state.get_unsent(informational, notifier.channel_name)
        if unsent_info:
            try:
                notifier.send(unsent_info, urgent=False)
                for d in unsent_info:
                    state.mark_alerted(
                        AlertRecord(
                            fingerprint=d.fingerprint,
                            sent_at=now,
                            channel=notifier.channel_name,
                            discrepancy_kind=d.kind,
                            detail=d.detail,
                        )
                    )
                logger.info(
                    "Channel '%s': sent %d informational alert(s).",
                    notifier.channel_name, len(unsent_info),
                )
            except Exception as e:
                logger.error(
                    "Channel '%s' failed on informational alerts: %s — will retry.",
                    notifier.channel_name, e,
                )

    state.close()
    sys.exit(EXIT_DISCREPANCY)


if __name__ == "__main__":
    main()
