from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def configure_logging(level: str, log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Always log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    # Rotating file: 5 MB × 3 backups
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
