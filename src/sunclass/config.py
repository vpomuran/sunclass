from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Settings:
    ical_urls: list[str]
    ical_sources: list[str]
    ical_labels: list[str]

    sunclass_email: str
    sunclass_password: str
    sunclass_url: str
    scraper_timeout_ms: int
    property_label: str | None

    notifier_channels: list[str]
    telegram_bot_token: str
    telegram_chat_id: str

    date_tolerance_days: int
    ical_fetch_timeout_seconds: int
    canonical_tz: str

    state_db_path: str
    log_file_path: str
    log_level: str

    # Playwright debug options
    playwright_headless: bool    # False = show browser window
    playwright_slowmo: int       # milliseconds between each action (0 = no delay)

    @classmethod
    def from_env(cls, env_file: str = ".env") -> Settings:
        if Path(env_file).exists():
            load_dotenv(env_file)

        def _list(key: str, default: str = "") -> list[str]:
            raw = os.getenv(key, default).strip()
            return [v.strip() for v in raw.split(",") if v.strip()] if raw else []

        urls = _list("ICAL_URLS")
        sources = _list("ICAL_SOURCES")
        labels = _list("ICAL_LABELS")

        if not urls:
            raise ValueError("ICAL_URLS must contain at least one URL")
        if len(urls) != len(sources):
            raise ValueError("ICAL_URLS and ICAL_SOURCES must have the same number of entries")

        # Pad labels to match url count if not provided
        while len(labels) < len(urls):
            labels.append(sources[len(labels)] if len(labels) < len(sources) else "unknown")

        notifier_channels = _list("NOTIFIER_CHANNELS", "telegram,stdout")

        property_label_raw = os.getenv("PROPERTY_LABEL", "").strip()
        property_label = property_label_raw if property_label_raw else None

        return cls(
            ical_urls=urls,
            ical_sources=sources,
            ical_labels=labels,
            sunclass_email=os.environ["SUNCLASS_EMAIL"],
            sunclass_password=os.environ["SUNCLASS_PASSWORD"],
            sunclass_url=os.getenv(
                "SUNCLASS_URL", "https://mijn.sunclassdurbuy.com/reservations"
            ),
            scraper_timeout_ms=int(os.getenv("SCRAPER_TIMEOUT_MS", "30000")),
            property_label=property_label,
            notifier_channels=notifier_channels,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            date_tolerance_days=int(os.getenv("DATE_TOLERANCE_DAYS", "0")),
            ical_fetch_timeout_seconds=int(os.getenv("ICAL_FETCH_TIMEOUT_SECONDS", "30")),
            canonical_tz=os.getenv("CANONICAL_TZ", "Europe/Brussels"),
            state_db_path=os.getenv("STATE_DB_PATH", "data/state.db"),
            log_file_path=os.getenv("LOG_FILE_PATH", "data/sunclass.log"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            playwright_headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false",
            playwright_slowmo=int(os.getenv("PLAYWRIGHT_SLOWMO", "0")),
        )
