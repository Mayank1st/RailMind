from abc import ABC, abstractmethod
from datetime import date

from .schemas import LiveStatusResult


class LiveStatusProvider(ABC):
    """Abstract base for any train live-status data provider."""

    provider_name: str

    @abstractmethod
    async def fetch_live_status(
        self, train_number: str, journey_date: date
    ) -> LiveStatusResult:
        """Fetch live status. Raises ProviderError subclasses on failure."""
        ...
