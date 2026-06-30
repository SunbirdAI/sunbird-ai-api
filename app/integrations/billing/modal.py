"""Modal billing analytics provider (wraps Workspace.billing.report)."""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal

from app.integrations.billing.base import (
    AnalyticsProvider,
    ProviderQuery,
    ProviderUnavailable,
)
from app.schemas.billing_analytics import BillingRecord

logger = logging.getLogger(__name__)


def _as_float(value) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0.0)


class ModalAnalyticsProvider(AnalyticsProvider):
    name = "modal"

    def __init__(self) -> None:
        self.token_id = os.getenv("MODAL_TOKEN_ID")
        self.token_secret = os.getenv("MODAL_TOKEN_SECRET")

    async def is_available(self) -> bool:
        return bool(self.token_id and self.token_secret)

    def _call_report(self, query: ProviderQuery) -> list:
        """Blocking call into the Modal SDK. Patched in tests.

        Uses the current (non-deprecated) ``Workspace.billing.report`` API, which
        authenticates against the active ``MODAL_TOKEN_ID`` / ``MODAL_TOKEN_SECRET``
        credentials and returns ``BillingReportItem`` dataclasses.
        """
        import modal  # imported lazily so import-time never requires modal config

        resolution = "h" if query.base_resolution == "hour" else "d"
        workspace = modal.Workspace.from_context()
        return workspace.billing.report(
            start=query.start,
            end=query.end,
            resolution=resolution,
            tag_names=query.tag_names or ["*"],
        )

    def _normalize(self, items: list) -> list[BillingRecord]:
        records: list[BillingRecord] = []
        for item in items:
            cost_by_resource = getattr(item, "cost_by_resource", None) or {}
            resource_breakdown = {k: _as_float(v) for k, v in cost_by_resource.items()}
            records.append(
                BillingRecord(
                    provider="modal",
                    object_id=str(item.object_id),
                    object_name=str(item.description or item.object_id),
                    timestamp=item.interval_start,
                    cost=_as_float(item.cost),
                    environment=item.environment_name,
                    tags=dict(item.tags or {}),
                    resource_breakdown=resource_breakdown,
                )
            )
        return records

    async def fetch_records(self, query: ProviderQuery) -> list[BillingRecord]:
        if not await self.is_available():
            raise ProviderUnavailable("modal", "MODAL_TOKEN_ID/SECRET not configured")
        try:
            items = await asyncio.to_thread(self._call_report, query)
        except Exception as exc:  # SDK raises various errors (plan/auth/network)
            raise ProviderUnavailable("modal", f"billing report failed: {exc}") from exc
        return self._normalize(items)
