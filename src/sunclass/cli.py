from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from .config import Settings
from .fetchers.base import FetchError
from .fetchers.ical import ICalFetcher
from .fetchers.sunclass import SunclassScraper
from .comparator import match_reservations
from .logging_setup import configure_logging
from .models import AlertRecord
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
        "--bootstrap",
        action="store_true",
        help="Mark all current reservations as baseline (suppresses alerts on first run).",
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
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Load config
    try:
        settings = Settings.from_env(env_file=args.env_file)
    except (KeyError, ValueError) as e:
        print(f"CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    # --debug-browser overrides headless/slowmo from .env
    if args.debug_browser:
        settings.playwright_headless = False
        settings.playwright_slowmo = 500

    configure_logging(
        args.log_level or settings.log_level,
        settings.log_file_path,
    )

    logger.info("=== sunclass-monitor starting ===")

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

    logger.info(
        "Fetched %d iCal reservation(s) and %d Sunclass reservation(s).",
        len(ical_reservations),
        len(scraped),
    )

    # ── Bootstrap mode ──────────────────────────────────────────────────────
    if args.bootstrap:
        state.bootstrap_baseline(ical_reservations + scraped)
        logger.info(
            "Bootstrap complete. %d reservation(s) marked as baseline.",
            len(ical_reservations) + len(scraped),
        )
        state.close()
        sys.exit(EXIT_OK)

    # ── Compare ─────────────────────────────────────────────────────────────
    discrepancies = match_reservations(
        ical_reservations,
        scraped,
        date_tolerance_days=settings.date_tolerance_days,
    )

    if not discrepancies:
        logger.info("No discrepancies found. All reservations are consistent.")
        state.close()
        sys.exit(EXIT_OK)

    logger.warning("Found %d discrepancy(s).", len(discrepancies))
    for d in discrepancies:
        logger.warning("  %s: %s", d.kind, d.detail)

    # ── Dry run: report but don't send ─────────────────────────────────────
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
        unsent = state.get_unsent(discrepancies, notifier.channel_name)
        if not unsent:
            logger.info("Channel '%s': all discrepancies already reported.", notifier.channel_name)
            continue

        try:
            notifier.send(unsent)
            now = datetime.utcnow()
            for d in unsent:
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
                "Channel '%s': sent %d alert(s).", notifier.channel_name, len(unsent)
            )
        except Exception as e:
            logger.error(
                "Channel '%s' failed to send: %s — will retry on next run.",
                notifier.channel_name,
                e,
            )

    state.close()
    sys.exit(EXIT_DISCREPANCY)


if __name__ == "__main__":
    main()
