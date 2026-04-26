from __future__ import annotations

import logging

from .base import BaseNotifier
from ._format import KIND_LABEL, days_until
from ..models import Discrepancy

logger = logging.getLogger(__name__)


class StdoutNotifier(BaseNotifier):
    """Prints a single consolidated report to stdout."""

    @property
    def channel_name(self) -> str:
        return "stdout"

    def send(self, discrepancies: list[Discrepancy], urgent: bool = False) -> None:
        print(self._build_report(discrepancies, urgent))

    @staticmethod
    def _build_report(discrepancies: list[Discrepancy], urgent: bool) -> str:
        sorted_disc = sorted(discrepancies, key=days_until)
        count = len(sorted_disc)
        border = "=" * 60

        if urgent:
            title = f"⚠  SUNCLASS RESERVATION ALERT — {count} issue(s) require attention"
        else:
            title = f"ℹ  SUNCLASS RESERVATION REPORT — {count} informational item(s)"

        lines = [border, title, border]

        for i, d in enumerate(sorted_disc, 1):
            kind_label = KIND_LABEL.get(d.kind, d.kind)
            lines.append(f"\n[{i}/{count}] {kind_label} — {days_until(d)} day(s) until arrival")
            lines.append(f"  {d.detail}")
            for r in d.reservations:
                name = r.guest_name or "n/a"
                lines.append(f"  > {r.source}: {name!r}  {r.check_in} → {r.check_out}")

        lines.append(f"\n{border}")
        return "\n".join(lines)
