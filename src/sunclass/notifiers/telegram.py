from __future__ import annotations

import html
import logging
from datetime import date

import requests

from .base import BaseNotifier, NotifierError
from ..models import Discrepancy, DiscrepancyKind

logger = logging.getLogger(__name__)

_KIND_LABEL = {
    DiscrepancyKind.ONLY_IN_ICAL:     "MISSING FROM SUNCLASS",
    DiscrepancyKind.ONLY_IN_SCRAPE:   "Not in iCal feeds",
    DiscrepancyKind.DATE_MISMATCH:    "Date mismatch",
    DiscrepancyKind.SUSPICIOUS_MATCH: "Suspicious match — needs review",
}


def _days_until(d: Discrepancy) -> int:
    checkin = min(r.check_in for r in d.reservations)
    return (checkin - date.today()).days


def _e(text: str) -> str:
    """Escape user-supplied text for Telegram HTML mode."""
    return html.escape(str(text))


class TelegramNotifier(BaseNotifier):
    """Sends discrepancy alerts via Telegram Bot API (HTML parse mode)."""

    @property
    def channel_name(self) -> str:
        return "telegram"

    def _validate(self) -> None:
        if not self._settings.telegram_bot_token:
            raise NotifierError("TELEGRAM_BOT_TOKEN is not set")
        if not self._settings.telegram_chat_id:
            raise NotifierError("TELEGRAM_CHAT_ID is not set")

    def send(self, discrepancies: list[Discrepancy], urgent: bool = False) -> None:
        self._validate()
        token = self._settings.telegram_bot_token
        chat_id = self._settings.telegram_chat_id
        api_url = f"https://api.telegram.org/bot{token}/sendMessage"

        sorted_disc = sorted(discrepancies, key=_days_until)
        for d in sorted_disc:
            text = self._format(d, urgent)
            try:
                resp = requests.post(
                    api_url,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=10,
                )
            except requests.RequestException as e:
                logger.error("Telegram request failed (network): %s", e)
                raise

            if not resp.ok:
                try:
                    body = resp.json()
                    description = body.get("description", "no description")
                    error_code = body.get("error_code", resp.status_code)
                except Exception:
                    description = resp.text or "empty response"
                    error_code = resp.status_code
                logger.error("Telegram API error %s: %s", error_code, description)
                resp.raise_for_status()

            logger.info("Telegram alert sent: %s (%d days)", d.kind, _days_until(d))

    @staticmethod
    def _format(d: Discrepancy, urgent: bool) -> str:
        days = _days_until(d)
        kind_label = _KIND_LABEL.get(d.kind, d.kind)

        if urgent:
            header = f"🚨 <b>URGENT — {days} day(s) until arrival</b>"
        else:
            header = f"ℹ️ <b>Info — {days} day(s) until arrival</b>"

        lines = [
            header,
            f"<b>{_e(kind_label)}</b>",
            _e(d.detail),
        ]
        for r in d.reservations:
            name = _e(r.guest_name or "n/a")
            lines.append(f"  • <code>{_e(r.source)}</code>: {name} | {r.check_in} → {r.check_out}")
        lines.append(f"<i>Detected: {d.detected_at.strftime('%Y-%m-%d %H:%M UTC')}</i>")
        return "\n".join(lines)
