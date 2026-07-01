from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.billing.base import ProviderQuery, ProviderUnavailable
from app.integrations.billing.vastai import VastaiAnalyticsProvider


def _query():
    # 2024-11-01 .. 2024-11-05 UTC
    return ProviderQuery(
        start=datetime(2024, 11, 1),
        end=datetime(2024, 11, 5),
        base_resolution="day",
    )


CONTRACT = {
    "start": 1730419200,  # 2024-11-01 00:00 UTC
    "end": 1730678400,  # 2024-11-04 00:00 UTC
    "type": "instance",
    "source": "instance-12345678",
    "description": "Instance 12345678 Charges - 4 days",
    "amount": 38.421,
    "metadata": {"label": "my-training-job", "template_id": 101},
    "items": [
        {"type": "gpu", "description": "96.000 hours at $0.389/hour", "amount": 37.344},
        {"type": "disk", "description": "disk", "amount": 1.0},
        {"type": "bwd", "description": "download", "amount": 0.077},
    ],
}


async def test_fetch_records_amortizes_contract(monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "test-key")
    provider = VastaiAnalyticsProvider()
    page = {"results": [CONTRACT], "next_token": None}
    with patch.object(
        provider, "_request", AsyncMock(return_value=httpx.Response(200, json=page))
    ):
        records = await provider.fetch_records(_query())

    # 2024-11-01, 02, 03, 04 -> 4 daily records
    assert len(records) == 4
    assert all(r.provider == "vastai" for r in records)
    assert all(r.object_id == "instance-12345678" for r in records)
    assert all(r.object_name == "my-training-job" for r in records)
    # cost split evenly, sums back to the contract total
    assert round(sum(r.cost for r in records), 3) == 38.421
    assert round(records[0].cost, 5) == round(38.421 / 4, 5)
    # gpu hours -> runtime split (96h total -> 24h/day = 86_400_000 ms)
    assert records[0].runtime_ms == 86_400_000
    assert records[0].metadata["kind"] == "vastai_contract"
    assert records[0].metadata["contract_type"] == "instance"
    # resource breakdown per day
    assert round(records[0].resource_breakdown["gpu"], 5) == round(37.344 / 4, 5)


async def test_fetch_records_paginates(monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "test-key")
    provider = VastaiAnalyticsProvider()
    c2 = {**CONTRACT, "source": "instance-999", "metadata": {"label": "job2"}}
    page1 = {"results": [CONTRACT], "next_token": "tok2"}
    page2 = {"results": [c2], "next_token": None}
    with patch.object(
        provider,
        "_request",
        AsyncMock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        ),
    ) as req:
        records = await provider.fetch_records(_query())
    assert {r.object_id for r in records} == {"instance-12345678", "instance-999"}
    assert req.await_count == 2


async def test_is_available_requires_key(monkeypatch):
    monkeypatch.delenv("VAST_API_KEY", raising=False)
    assert await VastaiAnalyticsProvider().is_available() is False


async def test_fetch_records_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "test-key")
    provider = VastaiAnalyticsProvider()
    with patch.object(
        provider, "_request", AsyncMock(return_value=httpx.Response(429, json={}))
    ):
        with pytest.raises(ProviderUnavailable):
            await provider.fetch_records(_query())


async def test_fetch_records_wraps_parse_errors(monkeypatch):
    monkeypatch.setenv("VAST_API_KEY", "test-key")
    provider = VastaiAnalyticsProvider()
    bad = {
        "start": 1730419200,
        "end": 1730678400,
        "type": "instance",
        "source": "instance-1",
        "amount": "not-a-number",
        "items": [],
    }
    page = {"results": [bad], "next_token": None}
    with patch.object(
        provider, "_request", AsyncMock(return_value=httpx.Response(200, json=page))
    ):
        with pytest.raises(ProviderUnavailable):
            await provider.fetch_records(_query())
