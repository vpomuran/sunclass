from __future__ import annotations

import logging
from datetime import date

from .base import BaseNotifier
from ..models import Discrepancy, DiscrepancyKind

logger = logging.getLogger(__name__)

_KIND_LABEL = {
    DiscrepancyKind.ONLY_IN_ICAL:    "MISSING FROM SUNCLASS",
    DiscrepancyKind.ONLY_IN_SCRAPE:  "not in iCal feeds",
    DiscrepancyKind.DATE_MISMATCH:   "DATE MISMATCH",
    DiscrepancyKind.SUSPICIOUS_MATCH: "suspicious match — needs review",
}


def _days_until(d: Discrepancy) -> int:
    checkin = min(r.check_in for r in d.reservations)
    return (checkin - date.today()).days


class StdoutNotifier(BaseNotifier):
    """Prints discrepancies to stdout — always available, no credentials needed."""

    @property
    def channel_name(self) -> str:
        return "stdout"

    def send(self, discrepancies: list[Discrepancy], urgent: bool = False) -> None:
        sorted_disc = sorted(discrepancies, key=_days_until)
        for d in sorted_disc:
            print(self._format(d, urgent))

    @staticmethod
    def _format(d: Discrepancy, urgent: bool) -> str:
        days = _days_until(d)
        kind_label = _KIND_LABEL.get(d.kind, d.kind)

        if urgent:
            border = "!" * 60
            prefix = f"*** URGENT — {days} day(s) until arrival ***"
        else:
            border = "-" * 60
            prefix = f"Info — {days} day(s) until arrival"

        lines = [border, prefix, f"Type   : {kind_label}", f"Detail : {d.detail}"]
        for r in d.reservations:
            name = r.guest_name or "n/a"
            lines.append(f"  > {r.source}: {name!r}  {r.check_in} → {r.check_out}")
        lines.append(border)
        return "\n".join(lines)
