from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.integrations.billing.base import ProviderQuery, ProviderUnavailable
from app.integrations.billing.modal import ModalAnalyticsProvider


def _query():
    return ProviderQuery(
        start=datetime(2026, 5, 1),
        end=datetime(2026, 5, 3),
        base_resolution="day",
        tag_names=["*"],
    )


def _item(**kw):
    """Mimic a modal.billing.BillingReportItem dataclass (attribute access)."""
    base = dict(cost_by_resource={}, tags={})
    base.update(kw)
    return SimpleNamespace(**base)


# The new Workspace.billing.report() API returns BillingReportItem dataclasses
# (attribute access), not dicts.
SAMPLE_ITEMS = [
    _item(
        object_id="ap-123",
        description="inference-engine",
        environment_name="main",
        interval_start=datetime(2026, 5, 1),
        cost=Decimal("12.50"),
        tags={"team": "llm-platform"},
        cost_by_resource={"GPU": Decimal("10.00"), "CPU": Decimal("2.50")},
    ),
    _item(
        object_id="ap-456",
        description="batch-job",
        environment_name="main",
        interval_start=datetime(2026, 5, 2),
        cost=Decimal("3.25"),
        tags={},
    ),
]


async def test_fetch_records_normalizes(monkeypatch):
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")
    provider = ModalAnalyticsProvider()
    with patch.object(provider, "_call_report", return_value=SAMPLE_ITEMS):
        records = await provider.fetch_records(_query())
    assert len(records) == 2
    r = records[0]
    assert r.provider == "modal"
    assert r.object_id == "ap-123"
    assert r.object_name == "inference-engine"
    assert r.cost == 12.5
    assert r.environment == "main"
    assert r.tags == {"team": "llm-platform"}
    assert r.resource_breakdown == {"GPU": 10.0, "CPU": 2.5}
    assert r.runtime_ms is None


async def test_is_available_requires_tokens(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    assert await ModalAnalyticsProvider().is_available() is False


async def test_fetch_records_raises_on_sdk_error(monkeypatch):
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")
    provider = ModalAnalyticsProvider()
    with patch.object(
        provider, "_call_report", side_effect=RuntimeError("plan required")
    ):
        with pytest.raises(ProviderUnavailable):
            await provider.fetch_records(_query())
