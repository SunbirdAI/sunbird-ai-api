"""Provider-agnostic billing analytics interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.schemas.billing_analytics import BillingRecord


class ProviderUnavailable(Exception):
    """Raised when a provider cannot serve a request (auth/network/plan/etc.)."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        self.message = message
        super().__init__(f"[{provider}] {message}")


@dataclass
class ProviderQuery:
    start: datetime
    end: datetime
    base_resolution: str  # "hour" | "day"
    grouping: Optional[str] = None
    endpoint_ids: Optional[list[str]] = None
    gpu_types: Optional[list[str]] = None
    data_center_ids: Optional[list[str]] = None
    tag_names: Optional[list[str]] = None


class AnalyticsProvider(ABC):
    """Async interface every billing provider implements."""

    name: str = "base"

    @abstractmethod
    async def is_available(self) -> bool:
        """True if the provider has the credentials/config to serve requests."""

    @abstractmethod
    async def fetch_records(self, query: ProviderQuery) -> list[BillingRecord]:
        """Fetch and normalize billing rows. Raises ProviderUnavailable on failure."""
