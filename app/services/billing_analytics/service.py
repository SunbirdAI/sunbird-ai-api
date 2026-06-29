"""Billing analytics orchestrator: fetch (concurrent) -> cache -> aggregate."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.integrations.billing.base import (
    AnalyticsProvider,
    ProviderQuery,
    ProviderUnavailable,
)
from app.integrations.billing.modal import ModalAnalyticsProvider
from app.integrations.billing.runpod import RunpodAnalyticsProvider
from app.schemas.billing_analytics import (
    BillingRecord,
    BreakdownResponse,
    BreakdownRow,
    HighestCost,
    ProvidersResponse,
    SummaryResponse,
    TableResponse,
    TimeseriesResponse,
)
from app.services.billing_analytics import aggregation
from app.services.cache import CacheBackend, get_cache_backend

logger = logging.getLogger(__name__)


@dataclass
class BillingQueryParams:
    provider: str  # "all" | "runpod" | "modal"
    start: datetime
    end: datetime
    resolution: str  # display: hour | day | week | month | year
    group_by: Optional[str] = None
    search: Optional[str] = None
    gpu_types: Optional[list[str]] = None
    data_center_ids: Optional[list[str]] = None

    @property
    def base_resolution(self) -> str:
        return "hour" if self.resolution == "hour" else "day"

    @property
    def num_days(self) -> int:
        return max((self.end - self.start).days, 1)


class BillingAnalyticsService:
    def __init__(
        self,
        runpod_provider: Optional[AnalyticsProvider] = None,
        modal_provider: Optional[AnalyticsProvider] = None,
        cache: Optional[CacheBackend] = None,
    ) -> None:
        self.runpod = runpod_provider or RunpodAnalyticsProvider()
        self.modal = modal_provider or ModalAnalyticsProvider()
        self.cache = cache or get_cache_backend()
        self.ttl = settings.billing_cache_ttl_seconds

    # ---- record fetching (cached) ----

    def _cache_key(self, p: BillingQueryParams) -> str:
        runpod_grouping = "gpuTypeId" if p.group_by == "gpu" else "endpointId"
        gpus = ",".join(p.gpu_types or [])
        dcs = ",".join(p.data_center_ids or [])
        return (
            f"billing:v1:{p.provider}:{p.start.isoformat()}:{p.end.isoformat()}"
            f":{p.base_resolution}:{runpod_grouping}:{gpus}:{dcs}"
        )

    def _providers_for(self, provider: str) -> list[AnalyticsProvider]:
        if provider == "runpod":
            return [self.runpod]
        if provider == "modal":
            return [self.modal]
        return [self.runpod, self.modal]

    async def _fetch_records(
        self, p: BillingQueryParams
    ) -> tuple[list[BillingRecord], list[str]]:
        key = self._cache_key(p)
        cached = await self.cache.get(key)
        if cached is not None:
            records = [BillingRecord(**row) for row in cached["records"]]
            return records, list(cached.get("warnings", []))

        runpod_grouping = "gpuTypeId" if p.group_by == "gpu" else "endpointId"
        query = ProviderQuery(
            start=p.start,
            end=p.end,
            base_resolution=p.base_resolution,
            grouping=runpod_grouping,
            gpu_types=p.gpu_types,
            data_center_ids=p.data_center_ids,
            tag_names=["*"],
        )

        providers = self._providers_for(p.provider)
        results = await asyncio.gather(
            *(prov.fetch_records(query) for prov in providers),
            return_exceptions=True,
        )

        records: list[BillingRecord] = []
        warnings: list[str] = []
        for prov, result in zip(providers, results):
            if isinstance(result, ProviderUnavailable):
                warnings.append(f"{prov.name} unavailable: {result.message}")
                logger.warning("billing_provider_unavailable: %s", result)
            elif isinstance(result, Exception):
                warnings.append(f"{prov.name} error: {result}")
                logger.exception("billing_provider_error", exc_info=result)
            else:
                records.extend(result)

        # Only cache fully-successful results; never persist degraded/partial data
        # (a billing surface must not serve understated totals after a provider recovers).
        if not warnings:
            await self.cache.set(
                key,
                {
                    "records": [r.model_dump(mode="json") for r in records],
                    "warnings": warnings,
                },
                self.ttl,
            )
        return records, warnings

    # ---- high-level endpoints ----

    async def summary(self, p: BillingQueryParams) -> SummaryResponse:
        records, warnings = await self._fetch_records(p)
        data = aggregation.summarize(records, num_days=p.num_days)
        he = data["highest_cost_endpoint"]
        hp = data["highest_cost_platform"]
        return SummaryResponse(
            total_spend=data["total_spend"],
            avg_daily_spend=data["avg_daily_spend"],
            total_runtime_ms=data["total_runtime_ms"],
            avg_daily_runtime_ms=data["avg_daily_runtime_ms"],
            total_storage_gb=data["total_storage_gb"],
            active_endpoints=data["active_endpoints"],
            active_modal_apps=data["active_modal_apps"],
            highest_cost_endpoint=HighestCost(**he) if he else None,
            highest_cost_platform=HighestCost(**hp) if hp else None,
            num_days=data["num_days"],
            warnings=warnings,
        )

    async def timeseries(self, p: BillingQueryParams) -> TimeseriesResponse:
        records, warnings = await self._fetch_records(p)
        ts = aggregation.rollup_timeseries(records, p.resolution, p.group_by)
        return TimeseriesResponse(**ts, warnings=warnings)

    async def providers(self, p: BillingQueryParams) -> ProvidersResponse:
        records, warnings = await self._fetch_records(p)
        pt = aggregation.provider_totals(records)
        return ProvidersResponse(**pt, warnings=warnings)

    async def breakdown(self, p: BillingQueryParams) -> BreakdownResponse:
        records, warnings = await self._fetch_records(p)
        rows = aggregation.group_records(records, p.group_by or "provider")
        return BreakdownResponse(
            group_by=p.group_by or "provider",
            rows=[BreakdownRow(**row) for row in rows],
            warnings=warnings,
        )

    async def table(
        self, p: BillingQueryParams, page: int, page_size: int, sort: Optional[str]
    ) -> TableResponse:
        records, warnings = await self._fetch_records(p)
        rows, total = aggregation.paginate_sort_search(
            records, page=page, page_size=page_size, sort=sort, search=p.search
        )
        return TableResponse(
            rows=rows, total=total, page=page, page_size=page_size, warnings=warnings
        )

    async def records_for_export(self, p: BillingQueryParams) -> list[BillingRecord]:
        records, _ = await self._fetch_records(p)
        return sorted(records, key=lambda r: (r.provider, r.timestamp))


_service_instance: Optional[BillingAnalyticsService] = None


def get_billing_analytics_service() -> BillingAnalyticsService:
    global _service_instance
    if _service_instance is None:
        _service_instance = BillingAnalyticsService()
    return _service_instance
