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

# Telegram hard limit per message
_MAX_MESSAGE_LEN = 4096


def _days_until(d: Discrepancy) -> int:
    checkin = min(r.check_in for r in d.reservations)
    return (checkin - date.today()).days


def _e(text: str) -> str:
    """Escape user-supplied text for Telegram HTML mode."""
    return html.escape(str(text))


def _chunk(text: str) -> list[str]:
    """Split a message that exceeds Telegram's limit into safe chunks."""
    if len(text) <= _MAX_MESSAGE_LEN:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + _MAX_MESSAGE_LEN
        # Break at a newline if possible to avoid splitting mid-line
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline
        chunks.append(text[start:end])
        start = end
    return chunks


class TelegramNotifier(BaseNotifier):
    """Sends a single consolidated alert message via Telegram Bot API (HTML mode)."""

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

        full_message = self._build_report(discrepancies, urgent)
        parts = _chunk(full_message)

        for part in parts:
            self._send_part(api_url, chat_id, part)

        logger.info(
            "Telegram report sent: %d discrepancy(s) in %d message(s).",
            len(discrepancies), len(parts),
        )

    def _send_part(self, api_url: str, chat_id: str, text: str) -> None:
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

    @staticmethod
    def _build_report(discrepancies: list[Discrepancy], urgent: bool) -> str:
        sorted_disc = sorted(discrepancies, key=_days_until)
        count = len(sorted_disc)

        if urgent:
            header = f"🚨 <b>SUNCLASS RESERVATION ALERT — {count} issue(s)</b>"
        else:
            header = f"ℹ️ <b>SUNCLASS RESERVATION REPORT — {count} informational item(s)</b>"

        lines = [header]

        for i, d in enumerate(sorted_disc, 1):
            days = _days_until(d)
            kind_label = _KIND_LABEL.get(d.kind, d.kind)
            lines.append(
                f"\n<b>[{i}/{count}] {_e(kind_label)}</b> — {days} day(s) until arrival"
            )
            lines.append(_e(d.detail))
            for r in d.reservations:
                name = _e(r.guest_name or "n/a")
                lines.append(
                    f"  • <code>{_e(r.source)}</code>: {name} | {r.check_in} → {r.check_out}"
                )

        lines.append(f"\n<i>Generated: {date.today()}</i>")
        return "\n".join(lines)
