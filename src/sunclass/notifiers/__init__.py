from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseNotifier, NotifierError
from .stdout import StdoutNotifier
from .telegram import TelegramNotifier

if TYPE_CHECKING:
    from ..config import Settings

_REGISTRY: dict[str, type[BaseNotifier]] = {
    "stdout": StdoutNotifier,
    "telegram": TelegramNotifier,
}


def build_notifiers(settings: Settings) -> list[BaseNotifier]:
    """Build and validate all configured notification channels."""
    notifiers: list[BaseNotifier] = []
    for channel in settings.notifier_channels:
        cls = _REGISTRY.get(channel)
        if cls is None:
            raise NotifierError(
                f"Unknown notification channel: {channel!r}. "
                f"Valid options: {', '.join(_REGISTRY)}"
            )
        notifiers.append(cls(settings))
    return notifiers
