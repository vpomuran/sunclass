from __future__ import annotations

import logging

import requests

from .base import BaseNotifier, NotifierError
from ..models import Discrepancy, DiscrepancyKind

logger = logging.getLogger(__name__)

_EMOJI = {
    DiscrepancyKind.ONLY_IN_ICAL: "🔴",
    DiscrepancyKind.ONLY_IN_SCRAPE: "🟠",
    DiscrepancyKind.DATE_MISMATCH: "🟡",
    DiscrepancyKind.GUEST_MISMATCH: "🟡",
    DiscrepancyKind.SUSPICIOUS_MATCH: "⚠️",
}


class TelegramNotifier(BaseNotifier):
    """Sends discrepancy alerts via Telegram Bot API."""

    @property
    def channel_name(self) -> str:
        return "telegram"

    def _validate(self) -> None:
        if not self._settings.telegram_bot_token:
            raise NotifierError("TELEGRAM_BOT_TOKEN is not set")
        if not self._settings.telegram_chat_id:
            raise NotifierError("TELEGRAM_CHAT_ID is not set")

    def send(self, discrepancies: list[Discrepancy]) -> None:
        self._validate()
        token = self._settings.telegram_bot_token
        chat_id = self._settings.telegram_chat_id
        api_url = f"https://api.telegram.org/bot{token}/sendMessage"

        for d in discrepancies:
            text = self._format(d)
            try:
                resp = requests.post(
                    api_url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=10,
                )
                resp.raise_for_status()
                logger.info("Telegram alert sent for fingerprint %s", d.fingerprint[:8])
            except requests.RequestException as e:
                logger.error("Telegram send failed: %s", e)
                raise

    @staticmethod
    def _format(d: Discrepancy) -> str:
        emoji = _EMOJI.get(d.kind, "❓")
        lines = [
            f"{emoji} *Reservation discrepancy detected*",
            f"*Type:* `{d.kind}`",
            f"*Detail:* {d.detail}",
        ]
        for r in d.reservations:
            lines.append(
                f"  • `{r.source}`: {r.guest_name} | {r.check_in} → {r.check_out}"
            )
        lines.append(f"_Detected: {d.detected_at.strftime('%Y-%m-%d %H:%M UTC')}_")
        return "\n".join(lines)
