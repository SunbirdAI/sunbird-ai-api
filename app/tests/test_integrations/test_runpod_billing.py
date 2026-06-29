from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.integrations.billing.base import ProviderQuery, ProviderUnavailable
from app.integrations.billing.runpod import RunpodAnalyticsProvider

SAMPLE = [
    {
        "amount": 28.73,
        "timeBilledMs": 82924997,
        "diskSpaceBilledGB": 136400,
        "endpointId": "yapuzewu3ebmzq",
        "time": "2026-05-01 00:00:00",
    },
    {
        "amount": 23.31,
        "timeBilledMs": 67270463,
        "diskSpaceBilledGB": 107400,
        "endpointId": "yapuzewu3ebmzq",
        "time": "2026-05-02 00:00:00",
    },
]


def _query():
    return ProviderQuery(
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 3),
        base_resolution="day",
        grouping="endpointId",
    )


async def test_fetch_records_normalizes_sample(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    provider = RunpodAnalyticsProvider()

    mock_resp = httpx.Response(200, json=SAMPLE)
    with patch.object(provider, "_request", AsyncMock(return_value=mock_resp)):
        records = await provider.fetch_records(_query())

    assert len(records) == 2
    r = records[0]
    assert r.provider == "runpod"
    assert r.object_id == "yapuzewu3ebmzq"
    assert r.cost == 28.73
    assert r.runtime_ms == 82924997
    assert r.storage_gb == 136400.0
    assert r.timestamp == datetime(2026, 5, 1, 0, 0, 0)


async def test_fetch_records_handles_lowercase_gb_key(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    provider = RunpodAnalyticsProvider()
    payload = [
        {
            "amount": 1.0,
            "timeBilledMs": 100,
            "diskSpaceBilledGb": 50,  # documented (lowercase b) variant
            "gpuTypeId": "NVIDIA A40",
            "time": "2026-05-01T00:00:00Z",
        }
    ]
    mock_resp = httpx.Response(200, json=payload)
    with patch.object(provider, "_request", AsyncMock(return_value=mock_resp)):
        q = _query()
        q.grouping = "gpuTypeId"
        records = await provider.fetch_records(q)
    assert records[0].storage_gb == 50.0
    assert records[0].gpu == "NVIDIA A40"
    assert records[0].object_id == "NVIDIA A40"


async def test_is_available_false_without_key(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    provider = RunpodAnalyticsProvider()
    assert await provider.is_available() is False


async def test_fetch_records_raises_provider_unavailable_on_http_error(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    provider = RunpodAnalyticsProvider()
    with patch.object(
        provider, "_request", AsyncMock(side_effect=httpx.ConnectError("boom"))
    ):
        with pytest.raises(ProviderUnavailable):
            await provider.fetch_records(_query())
