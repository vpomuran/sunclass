from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings
    from ..models import Discrepancy


class NotifierError(Exception):
    """Configuration or credential failure for a notifier."""


class BaseNotifier(ABC):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @abstractmethod
    def send(self, discrepancies: list[Discrepancy]) -> None:
        """Send notifications. Raises NotifierError on config failure."""
        ...

    @property
    @abstractmethod
    def channel_name(self) -> str:
        ...
