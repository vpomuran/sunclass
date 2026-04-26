from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import TYPE_CHECKING

from ..fetchers.base import BaseFetcher, FetchError
from ..models import Reservation

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]

# Actual date format used by the Sunclass portal: "23-05-2026"
_DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]

# Owner-booking prefix pattern — e.g. "(EIG102)Pomuran, V.M"
# These are owner's personal stays; included in comparison but labelled.
_OWNER_PREFIX = re.compile(r"^\(EIG\d+\)")


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {raw!r}")


def _clean_name(raw: str) -> str:
    """Strip non-breaking spaces and normalise whitespace."""
    return raw.replace("\xa0", " ").strip()


class SunclassScraper(BaseFetcher):
    """
    Scrapes the reservation table from mijn.sunclassdurbuy.com.

    Table columns (confirmed from live HTML, 0-indexed):
      0  Reservation number  — <a href="/reservations/{id}"> or /booking/{id}
      1  Object              — property description
      2  Name                — guest name (may have &nbsp; prefix or (EIG102) owner prefix)
      3  City
      4  Arrival date        — dd-mm-yyyy
      5  Departure date      — dd-mm-yyyy
      6  Revenue
      7  Notes icon          — optional
      8  Aangebracht door eigenaar

    Login selectors are standard form fields; update if the portal changes auth method.
    """

    def __init__(self, settings: Settings) -> None:
        self._login_url = "https://mijn.sunclassdurbuy.com/login"
        self._reservations_url = settings.sunclass_url
        self._email = settings.sunclass_email
        self._password = settings.sunclass_password
        self._timeout = settings.scraper_timeout_ms
        self._property_label = settings.property_label
        self._headless = settings.playwright_headless
        self._slowmo = settings.playwright_slowmo
        self._screenshot_dir = settings.state_db_path.replace("state.db", "")

    @property
    def source_name(self) -> str:
        return "sunclass"

    def fetch(self) -> list[Reservation]:
        last_error: Exception | None = None
        for attempt, delay in enumerate(
            [0] + _RETRY_DELAYS[: _MAX_RETRIES - 1], start=1
        ):
            if delay:
                logger.info("Retrying Sunclass scrape in %ds (attempt %d)", delay, attempt)
                time.sleep(delay)
            try:
                return self._run_scrape()
            except FetchError as e:
                last_error = e
                logger.warning("Scrape attempt %d failed: %s", attempt, e)

        raise FetchError(
            f"Sunclass scrape failed after {_MAX_RETRIES} attempts"
        ) from last_error

    def _run_scrape(self) -> list[Reservation]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise FetchError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from e

        headless = self._headless
        slowmo = self._slowmo
        if not headless:
            logger.info("Playwright debug mode: browser window visible, slow_mo=%dms", slowmo)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, slow_mo=slowmo)
            try:
                context = browser.new_context()
                page = context.new_page()
                self._login(page)
                return self._scrape_reservations(page)
            except FetchError:
                raise
            except Exception as e:
                self._save_screenshot(page, "error")
                raise FetchError(f"Scrape error: {e}") from e
            finally:
                browser.close()

    def _save_screenshot(self, page, label: str) -> None:
        """Save a screenshot to data/ for post-mortem debugging."""
        from pathlib import Path
        from datetime import datetime
        path = Path(self._screenshot_dir) / f"screenshot_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            logger.info("Screenshot saved: %s", path)
        except Exception as e:
            logger.warning("Could not save screenshot: %s", e)

    def _login(self, page) -> None:
        logger.info("Logging in to Sunclass portal")
        page.goto(self._login_url, timeout=self._timeout)

        # Use type=submit rather than button text — text varies by browser language (i18n)
        page.wait_for_selector('input[name="login"]', timeout=self._timeout)
        page.fill('input[name="login"]', self._email)
        page.fill('input[name="password"]', self._password)
        page.click('button[type="submit"]')

        # Wait for the page to settle before checking outcome
        try:
            page.wait_for_load_state("networkidle", timeout=self._timeout)
        except Exception:
            pass  # networkidle may not fire on all SPAs; URL check below is the real guard

        # Still on the login page → credentials were rejected
        if "/login" in page.url:
            self._save_screenshot(page, "login_failed")
            raise FetchError(
                "Login failed — still on login page after submitting credentials. "
                "Check SUNCLASS_EMAIL and SUNCLASS_PASSWORD in .env"
            )

        # Login succeeded; navigate to reservations if the portal landed elsewhere
        if "/reservations" not in page.url:
            logger.debug("Post-login URL is %s; navigating to reservations", page.url)
            page.goto(self._reservations_url, timeout=self._timeout)

        logger.info("Sunclass login OK — at %s", page.url)
        if not self._headless:
            self._save_screenshot(page, "after_login")

    def _scrape_reservations(self, page) -> list[Reservation]:
        logger.info("Waiting for reservation table")

        # The table class is confirmed from live HTML
        page.wait_for_selector(
            "table.product-overview tbody tr", timeout=self._timeout
        )
        rows = page.query_selector_all("table.product-overview tbody tr")
        if not self._headless:
            self._save_screenshot(page, "reservations_table")

        reservations: list[Reservation] = []
        for row in rows:
            try:
                r = self._parse_row(row)
                if r:
                    reservations.append(r)
            except Exception as e:
                logger.warning("Skipping unreadable row: %s", e)

        logger.info("Scraped %d reservations from Sunclass", len(reservations))
        return reservations

    def _parse_row(self, row) -> Reservation | None:
        cells = row.query_selector_all("td")
        if len(cells) < 6:
            return None  # Safety: need at least reservation#, object, name, city, arrival, departure

        # ── Column 0: reservation link → extract internal ID for UID ─────────
        link = cells[0].query_selector("a")
        if link:
            href = link.get_attribute("href") or ""
            # href is "/reservations/26553821" or "/booking/26493770"
            uid = href.strip("/").replace("/", "_")  # "reservations_26553821"
        else:
            uid = _clean_name(cells[0].inner_text())

        # ── Column 2: guest name ──────────────────────────────────────────────
        guest_name = _clean_name(cells[2].inner_text())
        if not guest_name:
            return None

        is_owner = bool(_OWNER_PREFIX.match(guest_name))
        if is_owner:
            # Strip the (EIG102) prefix so name is still usable in reports
            guest_name = _OWNER_PREFIX.sub("", guest_name).strip()
            logger.debug("Owner booking: %s", guest_name)

        # ── Column 4/5: arrival / departure dates ─────────────────────────────
        check_in_raw = _clean_name(cells[4].inner_text())
        check_out_raw = _clean_name(cells[5].inner_text())

        if not check_in_raw or not check_out_raw:
            return None

        check_in = _parse_date(check_in_raw)
        check_out = _parse_date(check_out_raw)

        return Reservation(
            source="sunclass",
            external_uid=uid or f"sunclass:{check_in}:{check_out}",
            check_in=check_in,
            check_out=check_out,
            guest_name=guest_name,
            num_guests=None,
            property_label=self._property_label,
            raw_summary=None,
        )
