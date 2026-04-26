from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ..models import DiscrepancyKind

if TYPE_CHECKING:
    from ..models import Discrepancy

KIND_LABEL = {
    DiscrepancyKind.ONLY_IN_ICAL:     "MISSING FROM SUNCLASS",
    DiscrepancyKind.ONLY_IN_SCRAPE:   "Not in iCal feeds",
    DiscrepancyKind.DATE_MISMATCH:    "Date mismatch",
    DiscrepancyKind.SUSPICIOUS_MATCH: "Suspicious match — needs review",
}


def days_until(d: Discrepancy) -> int:
    checkin = min(r.check_in for r in d.reservations)
    return (checkin - date.today()).days
