from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Reservation


class FetchError(Exception):
    """Unrecoverable fetch or scrape failure."""


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self) -> list[Reservation]:
        """Return all reservations from this source. Raises FetchError on failure."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable source name used in logs."""
        ...
