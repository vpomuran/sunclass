from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class DiscrepancyKind(str, Enum):
    ONLY_IN_ICAL = "only_in_ical"
    ONLY_IN_SCRAPE = "only_in_scrape"
    DATE_MISMATCH = "date_mismatch"
    SUSPICIOUS_MATCH = "suspicious_match"


@dataclass
class Reservation:
    source: str
    external_uid: str
    check_in: date
    check_out: date
    # Guest name is only available from the Sunclass scrape.
    # iCal feeds (Booking.com, Airbnb) only expose blocked date ranges.
    guest_name: str | None
    property_label: str | None

    @property
    def canonical_key(self) -> tuple[date, date]:
        """Match reservations purely on date range — guest names not in iCal."""
        return (self.check_in, self.check_out)

    @property
    def source_key(self) -> tuple[str, str]:
        return (self.source, self.external_uid)

    def __repr__(self) -> str:
        name = self.guest_name or "n/a"
        return (
            f"Reservation({self.source} | {name!r} | "
            f"{self.check_in}→{self.check_out})"
        )


@dataclass
class Discrepancy:
    kind: DiscrepancyKind
    reservations: list[Reservation]
    detail: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "kind": self.kind,
                "keys": sorted(str(r.source_key) for r in self.reservations),
                "detail": self.detail,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"Discrepancy({self.kind} | {self.detail!r})"


@dataclass
class AlertRecord:
    fingerprint: str
    sent_at: datetime
    channel: str
    discrepancy_kind: str
    detail: str
