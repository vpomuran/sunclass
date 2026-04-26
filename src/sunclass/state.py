from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AlertRecord, Discrepancy, Reservation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    fingerprint      TEXT NOT NULL,
    channel          TEXT NOT NULL,
    sent_at          TEXT NOT NULL,
    -- audit trail: not queried by the app, but readable via SQLite browser
    discrepancy_kind TEXT NOT NULL,
    detail           TEXT NOT NULL,
    PRIMARY KEY (fingerprint, channel)
);
"""


class StateStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def is_alerted(self, fingerprint: str, channel: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM alerts WHERE fingerprint = ? AND channel = ?",
            (fingerprint, channel),
        )
        return cur.fetchone() is not None

    def mark_alerted(self, record: AlertRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO alerts
                (fingerprint, channel, sent_at, discrepancy_kind, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.fingerprint,
                record.channel,
                record.sent_at.isoformat(),
                record.discrepancy_kind,
                record.detail,
            ),
        )
        self._conn.commit()

    def get_unsent(
        self, discrepancies: list[Discrepancy], channel: str
    ) -> list[Discrepancy]:
        return [d for d in discrepancies if not self.is_alerted(d.fingerprint, channel)]

    def bootstrap_baseline(self, reservations: list[Reservation], channels: list[str]) -> None:
        """Mark all current reservations as already-alerted so first run is silent."""
        from .models import AlertRecord, DiscrepancyKind, Discrepancy

        now = datetime.utcnow()
        for r in reservations:
            d = Discrepancy(
                kind=DiscrepancyKind.ONLY_IN_ICAL,
                reservations=[r],
                detail=f"baseline:{r.external_uid}",
            )
            for channel in channels:
                self.mark_alerted(
                    AlertRecord(
                        fingerprint=d.fingerprint,
                        sent_at=now,
                        channel=channel,
                        discrepancy_kind=d.kind,
                        detail=d.detail,
                    )
                )

    def close(self) -> None:
        self._conn.close()
