import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from app.integrations.billing.base import ProviderUnavailable
from app.schemas.billing_analytics import BillingRecord
from app.services.billing_analytics.service import (
    BillingAnalyticsService,
    BillingQueryParams,
)


class FakeCache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl_seconds):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


def _params(provider="all"):
    return BillingQueryParams(
        provider=provider,
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 3),
        resolution="day",
    )


def _runpod_records():
    return [
        BillingRecord(
            provider="runpod",
            object_id="ep1",
            object_name="ep1",
            timestamp=datetime(2026, 5, 1),
            cost=10.0,
            runtime_ms=1000,
            storage_gb=5,
        )
    ]


def _modal_records():
    return [
        BillingRecord(
            provider="modal",
            object_id="app1",
            object_name="app1",
            timestamp=datetime(2026, 5, 2),
            cost=4.0,
        )
    ]


def _service():
    runpod = AsyncMock()
    runpod.name = "runpod"
    runpod.fetch_records = AsyncMock(return_value=_runpod_records())
    modal = AsyncMock()
    modal.name = "modal"
    modal.fetch_records = AsyncMock(return_value=_modal_records())
    return (
        BillingAnalyticsService(
            runpod_provider=runpod, modal_provider=modal, cache=FakeCache()
        ),
        runpod,
        modal,
    )


async def test_summary_merges_both_providers():
    service, _, _ = _service()
    result = await service.summary(_params())
    assert result.total_spend == 14.0
    assert result.active_endpoints == 1
    assert result.active_modal_apps == 1
    assert result.warnings == []


async def test_provider_filter_runpod_only_skips_modal():
    service, runpod, modal = _service()
    await service.summary(_params(provider="runpod"))
    runpod.fetch_records.assert_awaited()
    modal.fetch_records.assert_not_awaited()


async def test_partial_failure_adds_warning():
    service, runpod, modal = _service()
    modal.fetch_records = AsyncMock(
        side_effect=ProviderUnavailable("modal", "plan required")
    )
    result = await service.summary(_params())
    assert result.total_spend == 10.0  # only runpod
    assert any("modal" in w for w in result.warnings)


async def test_records_are_cached():
    service, runpod, modal = _service()
    await service.summary(_params())
    await service.timeseries(_params())
    # Second call served from cache → providers only fetched once.
    assert runpod.fetch_records.await_count == 1


async def test_partial_failure_is_not_cached():
    service, runpod, modal = _service()
    modal.fetch_records = AsyncMock(
        side_effect=ProviderUnavailable("modal", "plan required")
    )
    await service.summary(_params())
    await service.timeseries(_params())
    # Degraded result must not be cached -> runpod re-fetched on the second call.
    assert runpod.fetch_records.await_count == 2


async def test_timeseries_and_breakdown_and_table():
    service, _, _ = _service()
    ts = await service.timeseries(_params())
    assert ts.labels == ["2026-05-01", "2026-05-02"]
    bd = await service.breakdown(
        BillingQueryParams(
            provider="all",
            start=datetime(2026, 5, 1),
            end=datetime(2026, 5, 3),
            resolution="day",
            group_by="provider",
        )
    )
    assert {row.key for row in bd.rows} == {"runpod", "modal"}
    table = await service.table(_params(), page=1, page_size=10, sort="cost")
    assert table.total == 2
    assert table.rows[0].cost == 10.0


async def test_concurrent_fetches_coalesce_to_one_provider_call():
    """Four endpoints firing the same query concurrently share one provider fetch."""
    service, runpod, modal = _service()

    async def slow_runpod(_query):
        await asyncio.sleep(0.05)
        return _runpod_records()

    async def slow_modal(_query):
        await asyncio.sleep(0.05)
        return _modal_records()

    runpod.fetch_records = AsyncMock(side_effect=slow_runpod)
    modal.fetch_records = AsyncMock(side_effect=slow_modal)

    p = _params()
    await asyncio.gather(
        service.summary(p),
        service.timeseries(p),
        service.providers(p),
        service.table(p, page=1, page_size=10, sort="cost"),
    )

    # Without coalescing each endpoint fetches independently (await_count == 4).
    assert runpod.fetch_records.await_count == 1
    assert modal.fetch_records.await_count == 1


async def test_runpod_query_scoped_to_configured_endpoint_ids():
    service, runpod, modal = _service()
    service.runpod_endpoint_ids = ["epA", "epB"]
    await service.summary(_params(provider="runpod"))
    query = runpod.fetch_records.call_args.args[0]
    assert query.endpoint_ids == ["epA", "epB"]


def _service_with_vastai():
    runpod = AsyncMock()
    runpod.name = "runpod"
    runpod.fetch_records = AsyncMock(return_value=_runpod_records())
    modal = AsyncMock()
    modal.name = "modal"
    modal.fetch_records = AsyncMock(return_value=_modal_records())
    vastai = AsyncMock()
    vastai.name = "vastai"
    vastai.fetch_records = AsyncMock(
        return_value=[
            BillingRecord(
                provider="vastai",
                object_id="instance-1",
                object_name="job",
                timestamp=datetime(2026, 5, 1),
                cost=7.0,
            )
        ]
    )
    service = BillingAnalyticsService(
        runpod_provider=runpod, modal_provider=modal, cache=FakeCache()
    )
    service.vastai = vastai
    return service, runpod, modal, vastai


async def test_training_category_uses_only_vastai():
    service, runpod, modal, vastai = _service_with_vastai()
    p = BillingQueryParams(
        provider="all",
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 3),
        resolution="day",
        category="training",
    )
    result = await service.summary(p)
    vastai.fetch_records.assert_awaited()
    runpod.fetch_records.assert_not_awaited()
    modal.fetch_records.assert_not_awaited()
    assert result.total_spend == 7.0


async def test_inference_category_uses_runpod_and_modal():
    service, runpod, modal, vastai = _service_with_vastai()
    p = BillingQueryParams(
        provider="all",
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 3),
        resolution="day",
        category="inference",
    )
    await service.summary(p)
    runpod.fetch_records.assert_awaited()
    modal.fetch_records.assert_awaited()
    vastai.fetch_records.assert_not_awaited()
