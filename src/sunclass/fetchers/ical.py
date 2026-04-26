from __future__ import annotations

import logging
import re
import zoneinfo
from datetime import date, datetime
from typing import TYPE_CHECKING

import requests
from icalendar import Calendar

from ..fetchers.base import BaseFetcher, FetchError
from ..models import Reservation

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# Summaries that represent blocked/unavailable slots (not real bookings)
_BLOCKED_PATTERNS = re.compile(
    r"^(CLOSED|Not available|Blocked|Unavailable|Reserved|Owner)",
    flags=re.IGNORECASE,
)


class ICalFetcher(BaseFetcher):
    """
    Fetches and parses a single iCal feed URL.

    iCal feeds from Booking.com and Airbnb only expose blocked date ranges —
    guest names are not included. Each VEVENT is treated as an opaque blocked
    interval identified solely by (check_in, check_out).
    """

    def __init__(
        self,
        url: str,
        source: str,
        label: str,
        settings: Settings,
    ) -> None:
        self._url = url
        self._source = source
        self._label = label
        self._timeout = settings.ical_fetch_timeout_seconds
        self._tz = zoneinfo.ZoneInfo(settings.canonical_tz)
        self._property_label = settings.property_label

    @property
    def source_name(self) -> str:
        return self._source

    def fetch(self) -> list[Reservation]:
        logger.info("Fetching iCal feed: %s (%s)", self._label, self._url)
        try:
            resp = requests.get(self._url, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise FetchError(f"Failed to fetch iCal from {self._url}: {e}") from e

        try:
            cal = Calendar.from_ical(resp.content)
        except Exception as e:
            raise FetchError(f"Failed to parse iCal from {self._url}: {e}") from e

        reservations: list[Reservation] = []
        for component in cal.walk("VEVENT"):
            try:
                r = self._parse_vevent(component)
                if r is not None:
                    reservations.append(r)
            except Exception as e:
                logger.warning("Skipping malformed VEVENT: %s", e)

        logger.info("Fetched %d blocked interval(s) from %s", len(reservations), self._label)
        return reservations

    def _parse_vevent(self, component) -> Reservation | None:
        uid = str(component.get("UID", "")).strip()
        summary = str(component.get("SUMMARY", "")).strip()

        dtstart_prop = component.get("DTSTART")
        dtend_prop = component.get("DTEND")
        if dtstart_prop is None or dtend_prop is None:
            return None

        check_in = self._to_date(dtstart_prop.dt)
        check_out = self._to_date(dtend_prop.dt)

        if check_in >= check_out:
            logger.debug("Skipping zero-length interval: %s", uid)
            return None

        return Reservation(
            source=self._source,
            external_uid=uid or f"{self._source}:{check_in}:{check_out}",
            check_in=check_in,
            check_out=check_out,
            guest_name=None,       # not available in iCal feeds
            num_guests=None,
            property_label=self._property_label,
            raw_summary=summary,
        )

    def _to_date(self, dt) -> date:
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=self._tz)
            return dt.astimezone(self._tz).date()
        return dt  # already a date object
