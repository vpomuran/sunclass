from __future__ import annotations

import logging

from .base import BaseNotifier
from ..models import Discrepancy

logger = logging.getLogger(__name__)


class StdoutNotifier(BaseNotifier):
    """Prints discrepancies to stdout — always available, no credentials needed."""

    @property
    def channel_name(self) -> str:
        return "stdout"

    def send(self, discrepancies: list[Discrepancy]) -> None:
        for d in discrepancies:
            print(self._format(d))

    @staticmethod
    def _format(d: Discrepancy) -> str:
        lines = [
            "=" * 60,
            f"[DISCREPANCY] {d.kind.upper()}",
            f"Detail : {d.detail}",
            f"Time   : {d.detected_at.strftime('%Y-%m-%d %H:%M UTC')}",
        ]
        for r in d.reservations:
            lines.append(
                f"  ├ {r.source}: '{r.guest_name}' "
                f"{r.check_in} → {r.check_out}"
            )
        lines.append("=" * 60)
        return "\n".join(lines)
