# Admin Billing Analytics (Runpod + Modal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only Billing Analytics surface that reports infrastructure spend/runtime/storage across Runpod and Modal, fetched live and cached, normalized into one schema, served to a new `/admin/billing` dashboard page.

**Architecture:** Provider-agnostic backend (`AnalyticsProvider` interface + Runpod & Modal implementations) behind a `BillingAnalyticsService` orchestrator that fetches concurrently, caches normalized records, and runs pure aggregation functions to build Chart.js-friendly response envelopes. A new admin router exposes six REST endpoints; a new React page consumes them, reusing existing chart/metric/filter components.

**Tech Stack:** FastAPI, Pydantic v2, async `httpx` (Runpod), Modal SDK `modal.billing` (Modal), existing `CacheBackend`, React 18 + Vite + TypeScript + Chart.js (react-chartjs-2) + axios + sonner.

## Global Constraints

- Backend gate per task: `pytest app/tests/ -v` (all pass) and `make lint-check` (clean: black + isort + flake8).
- Frontend gate (Task 6): `npm run build` and `npm run lint` in `frontend/` both succeed. No frontend test runner is installed; do NOT add one. Verify the page renders manually.
- Reuse existing patterns: DI aliases live in `app/deps.py`; routers import deps only from `app/deps.py`; use custom exceptions from `app/core/exceptions.py` (never bare `HTTPException`); service singletons via `get_<service>()` factory.
- Admin gate: every endpoint uses `CurrentAdminDep` (`get_current_admin`, returns 403 for non-admin, 401 unauthenticated).
- Provider API keys are server-side only and never returned to the client.
- All timestamps are UTC. `cost` is USD float. Modal billing resolution is only `"d"`/`"h"`; week/month/year are rolled up in our aggregation layer.
- Tests follow `asyncio_mode=auto` (no `@pytest.mark.asyncio`). Reuse `admin_client`, `async_client`, `authenticated_client` fixtures from `app/tests/conftest.py`.
- Provider modules read credentials from settings/env; mock providers in tests (never hit live APIs).

---

### Task 1: Unified schema, date-range resolver, and aggregation functions

**Files:**
- Create: `app/schemas/billing_analytics.py`
- Create: `app/services/billing_analytics/__init__.py` (empty package marker)
- Create: `app/services/billing_analytics/ranges.py`
- Create: `app/services/billing_analytics/aggregation.py`
- Test: `app/tests/test_billing_aggregation.py`

**Interfaces:**
- Produces:
  - `BillingRecord(BaseModel)` with fields: `provider: Literal["runpod","modal"]`, `object_id: str`, `object_name: str`, `timestamp: datetime`, `cost: float`, `runtime_ms: int | None = None`, `storage_gb: float | None = None`, `gpu: str | None = None`, `environment: str | None = None`, `tags: dict[str, str] = {}`, `resource_breakdown: dict[str, float] = {}`, `metadata: dict = {}`.
  - Response models: `SummaryResponse`, `TimeseriesResponse`, `ProvidersResponse`, `BreakdownRow`, `BreakdownResponse`, `TableResponse` (fields defined in Step 3).
  - `resolve_range(range_name: str | None, start: str | None, end: str | None, now: datetime) -> tuple[datetime, datetime]` in `ranges.py`.
  - Aggregation functions in `aggregation.py`: `sum_cost`, `sum_runtime_ms`, `sum_storage_gb`, `bucket_key(ts, resolution)`, `rollup_timeseries`, `group_records`, `summarize`, `provider_totals`, `paginate_sort_search`. Signatures in Step 5/7.

- [ ] **Step 1: Write the failing test for the schema + range resolver**

Create `app/tests/test_billing_aggregation.py`:

```python
from datetime import datetime

import pytest

from app.schemas.billing_analytics import BillingRecord
from app.services.billing_analytics.ranges import resolve_range


def _rec(**kw):
    base = dict(
        provider="runpod",
        object_id="ep1",
        object_name="ep1",
        timestamp=datetime(2026, 5, 1),
        cost=10.0,
    )
    base.update(kw)
    return BillingRecord(**base)


def test_billing_record_defaults():
    r = _rec()
    assert r.runtime_ms is None
    assert r.storage_gb is None
    assert r.tags == {}
    assert r.resource_breakdown == {}


def test_resolve_range_named_last_7_days():
    now = datetime(2026, 6, 29, 12, 0, 0)
    start, end = resolve_range("last_7_days", None, None, now)
    assert end == now
    assert (end - start).days == 7


def test_resolve_range_this_month():
    now = datetime(2026, 6, 29, 12, 0, 0)
    start, end = resolve_range("this_month", None, None, now)
    assert start == datetime(2026, 6, 1)
    assert end == now


def test_resolve_range_custom_requires_both():
    now = datetime(2026, 6, 29)
    with pytest.raises(ValueError):
        resolve_range("custom", "2026-06-01T00:00:00Z", None, now)


def test_resolve_range_custom_parses_iso():
    now = datetime(2026, 6, 29)
    start, end = resolve_range(
        "custom", "2026-05-01T00:00:00Z", "2026-06-01T00:00:00Z", now
    )
    assert start == datetime(2026, 5, 1)
    assert end == datetime(2026, 6, 1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest app/tests/test_billing_aggregation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.billing_analytics'`.

- [ ] **Step 3: Create the schema module**

Create `app/schemas/billing_analytics.py`:

```python
"""Unified, provider-agnostic billing analytics schema.

A single normalized bucket-row (`BillingRecord`) that both the Runpod and Modal
providers map into, plus the response envelopes the admin endpoints return.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["runpod", "modal"]


class BillingRecord(BaseModel):
    """One normalized billing bucket-row from a provider."""

    provider: Provider
    object_id: str
    object_name: str
    timestamp: datetime  # UTC, start of the bucket
    cost: float  # USD
    runtime_ms: Optional[int] = None
    storage_gb: Optional[float] = None
    gpu: Optional[str] = None
    environment: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)
    resource_breakdown: dict[str, float] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class HighestCost(BaseModel):
    name: str
    cost: float


class SummaryResponse(BaseModel):
    total_spend: float
    avg_daily_spend: float
    total_runtime_ms: int
    avg_daily_runtime_ms: float
    total_storage_gb: float
    active_endpoints: int
    active_modal_apps: int
    highest_cost_endpoint: Optional[HighestCost] = None
    highest_cost_platform: Optional[HighestCost] = None
    num_days: int
    warnings: list[str] = Field(default_factory=list)


class TimeseriesResponse(BaseModel):
    labels: list[str]
    cost: list[float]
    runtime_ms: list[float]
    storage_gb: list[float]
    cost_by_group: dict[str, list[float]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ProvidersResponse(BaseModel):
    labels: list[str]
    cost: list[float]
    runtime_ms: list[float]
    storage_gb: list[float]
    warnings: list[str] = Field(default_factory=list)


class BreakdownRow(BaseModel):
    key: str
    cost: float
    runtime_ms: int
    storage_gb: float
    count: int


class BreakdownResponse(BaseModel):
    group_by: str
    rows: list[BreakdownRow]
    warnings: list[str] = Field(default_factory=list)


class TableResponse(BaseModel):
    rows: list[BillingRecord]
    total: int
    page: int
    page_size: int
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Create the range resolver**

Create `app/services/billing_analytics/__init__.py` (empty file).

Create `app/services/billing_analytics/ranges.py`:

```python
"""Resolve named or explicit date ranges into concrete UTC datetimes."""

from __future__ import annotations

from datetime import datetime, timedelta


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string, tolerating a trailing 'Z', returning naive UTC."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def resolve_range(
    range_name: str | None,
    start: str | None,
    end: str | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return (start, end) UTC datetimes for a named or custom range.

    Named ranges: today, yesterday, last_7_days, last_30_days, last_90_days,
    this_month, last_month. 'custom' (or any explicit start/end) requires both
    `start` and `end`. Raises ValueError on invalid input.
    """
    if range_name in (None, "", "custom") and (start or end):
        if not (start and end):
            raise ValueError("custom range requires both 'start' and 'end'")
        return _parse_iso(start), _parse_iso(end)

    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    mapping = {
        "today": (today, now),
        "yesterday": (today - timedelta(days=1), today),
        "last_7_days": (now - timedelta(days=7), now),
        "last_30_days": (now - timedelta(days=30), now),
        "last_90_days": (now - timedelta(days=90), now),
        "this_month": (today.replace(day=1), now),
    }
    if range_name == "last_month":
        first_this = today.replace(day=1)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end
    if range_name in mapping:
        return mapping[range_name]
    # Default when nothing supplied.
    if range_name in (None, "", "custom"):
        return now - timedelta(days=30), now
    raise ValueError(f"Unknown range '{range_name}'")
```

- [ ] **Step 5: Run schema + range tests to verify they pass**

Run: `pytest app/tests/test_billing_aggregation.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Write failing tests for aggregation functions**

Append to `app/tests/test_billing_aggregation.py`:

```python
from app.services.billing_analytics.aggregation import (
    bucket_key,
    group_records,
    paginate_sort_search,
    provider_totals,
    rollup_timeseries,
    summarize,
)


def test_bucket_key_resolutions():
    ts = datetime(2026, 5, 4, 13, 0, 0)  # a Monday
    assert bucket_key(ts, "hour") == "2026-05-04 13:00"
    assert bucket_key(ts, "day") == "2026-05-04"
    assert bucket_key(ts, "month") == "2026-05"
    assert bucket_key(ts, "year") == "2026"
    assert bucket_key(ts, "week") == "2026-W19"


def test_rollup_timeseries_sums_per_bucket():
    recs = [
        _rec(timestamp=datetime(2026, 5, 1), cost=10.0, runtime_ms=1000, storage_gb=5),
        _rec(timestamp=datetime(2026, 5, 1), cost=5.0, runtime_ms=500, storage_gb=2),
        _rec(timestamp=datetime(2026, 5, 2), cost=7.0, runtime_ms=700, storage_gb=3),
    ]
    ts = rollup_timeseries(recs, "day", group_by=None)
    assert ts["labels"] == ["2026-05-01", "2026-05-02"]
    assert ts["cost"] == [15.0, 7.0]
    assert ts["runtime_ms"] == [1500.0, 700.0]
    assert ts["storage_gb"] == [7.0, 3.0]
    assert ts["cost_by_group"] == {}


def test_rollup_timeseries_grouped():
    recs = [
        _rec(provider="runpod", timestamp=datetime(2026, 5, 1), cost=10.0),
        _rec(provider="modal", object_id="app1", object_name="app1",
             timestamp=datetime(2026, 5, 1), cost=4.0),
    ]
    ts = rollup_timeseries(recs, "day", group_by="provider")
    assert ts["cost_by_group"]["runpod"] == [10.0]
    assert ts["cost_by_group"]["modal"] == [4.0]


def test_group_records_by_gpu_skips_none():
    recs = [
        _rec(gpu="NVIDIA A40", cost=10.0, runtime_ms=100, storage_gb=1),
        _rec(gpu="NVIDIA A40", cost=5.0, runtime_ms=50, storage_gb=1),
        _rec(gpu=None, cost=99.0),
    ]
    rows = group_records(recs, "gpu")
    assert len(rows) == 1
    assert rows[0]["key"] == "NVIDIA A40"
    assert rows[0]["cost"] == 15.0
    assert rows[0]["count"] == 2


def test_summarize_counts_and_tops():
    recs = [
        _rec(provider="runpod", object_id="ep1", object_name="ep1",
             timestamp=datetime(2026, 5, 1), cost=20.0, runtime_ms=2000, storage_gb=10),
        _rec(provider="runpod", object_id="ep2", object_name="ep2",
             timestamp=datetime(2026, 5, 2), cost=5.0, runtime_ms=500, storage_gb=2),
        _rec(provider="modal", object_id="app1", object_name="app1",
             timestamp=datetime(2026, 5, 2), cost=8.0),
    ]
    s = summarize(recs, num_days=2)
    assert s["total_spend"] == 33.0
    assert s["avg_daily_spend"] == 16.5
    assert s["active_endpoints"] == 2
    assert s["active_modal_apps"] == 1
    assert s["highest_cost_endpoint"]["name"] == "ep1"
    assert s["highest_cost_platform"]["name"] == "runpod"


def test_provider_totals():
    recs = [
        _rec(provider="runpod", cost=10.0, runtime_ms=100, storage_gb=1),
        _rec(provider="modal", object_id="a", object_name="a", cost=4.0),
    ]
    pt = provider_totals(recs)
    assert pt["labels"] == ["runpod", "modal"]
    assert pt["cost"] == [10.0, 4.0]


def test_paginate_sort_search():
    recs = [
        _rec(object_name="alpha", cost=1.0),
        _rec(object_name="beta", cost=3.0),
        _rec(object_name="gamma", cost=2.0),
    ]
    page, total = paginate_sort_search(
        recs, page=1, page_size=2, sort="cost", search=None
    )
    assert total == 3
    assert [r.cost for r in page] == [3.0, 2.0]  # cost desc
    page2, total2 = paginate_sort_search(
        recs, page=1, page_size=10, sort="cost", search="alp"
    )
    assert total2 == 1
    assert page2[0].object_name == "alpha"
```

- [ ] **Step 7: Run to verify the new tests fail**

Run: `pytest app/tests/test_billing_aggregation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.billing_analytics.aggregation'`.

- [ ] **Step 8: Create the aggregation module**

Create `app/services/billing_analytics/aggregation.py`:

```python
"""Pure aggregation functions over lists of BillingRecord.

No provider knowledge, no I/O — fully unit-testable. Reused by every endpoint
(and, later, the AI pipeline).
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import datetime
from typing import Optional

from app.schemas.billing_analytics import BillingRecord

# group_by keys we can derive directly from a normalized record.
_GROUP_KEY_FUNCS = {
    "provider": lambda r: r.provider,
    "endpoint": lambda r: r.object_name if r.provider == "runpod" else None,
    "app": lambda r: r.object_name if r.provider == "modal" else None,
    "gpu": lambda r: r.gpu,
    "environment": lambda r: r.environment,
}
SUPPORTED_GROUP_BYS = tuple(_GROUP_KEY_FUNCS.keys())


def _group_value(record: BillingRecord, group_by: str) -> Optional[str]:
    func = _GROUP_KEY_FUNCS.get(group_by)
    return func(record) if func else None


def sum_cost(records: list[BillingRecord]) -> float:
    return round(sum(r.cost for r in records), 6)


def sum_runtime_ms(records: list[BillingRecord]) -> int:
    return sum(r.runtime_ms or 0 for r in records)


def sum_storage_gb(records: list[BillingRecord]) -> float:
    return round(sum(r.storage_gb or 0.0 for r in records), 4)


def bucket_key(ts: datetime, resolution: str) -> str:
    if resolution == "hour":
        return ts.strftime("%Y-%m-%d %H:00")
    if resolution == "day":
        return ts.strftime("%Y-%m-%d")
    if resolution == "week":
        iso = ts.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if resolution == "month":
        return ts.strftime("%Y-%m")
    if resolution == "year":
        return ts.strftime("%Y")
    raise ValueError(f"Unknown resolution '{resolution}'")


def rollup_timeseries(
    records: list[BillingRecord], resolution: str, group_by: Optional[str]
) -> dict:
    cost: "OrderedDict[str, float]" = OrderedDict()
    runtime: defaultdict[str, float] = defaultdict(float)
    storage: defaultdict[str, float] = defaultdict(float)
    grouped: defaultdict[str, defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for r in sorted(records, key=lambda x: x.timestamp):
        b = bucket_key(r.timestamp, resolution)
        cost.setdefault(b, 0.0)
        cost[b] += r.cost
        runtime[b] += r.runtime_ms or 0
        storage[b] += r.storage_gb or 0.0
        if group_by:
            gv = _group_value(r, group_by)
            if gv is not None:
                grouped[gv][b] += r.cost

    labels = list(cost.keys())
    cost_by_group = {
        gv: [round(buckets.get(b, 0.0), 6) for b in labels]
        for gv, buckets in grouped.items()
    }
    return {
        "labels": labels,
        "cost": [round(cost[b], 6) for b in labels],
        "runtime_ms": [round(runtime[b], 1) for b in labels],
        "storage_gb": [round(storage[b], 4) for b in labels],
        "cost_by_group": cost_by_group,
    }


def group_records(records: list[BillingRecord], group_by: str) -> list[dict]:
    agg: "OrderedDict[str, dict]" = OrderedDict()
    for r in records:
        key = _group_value(r, group_by)
        if key is None:
            continue
        row = agg.setdefault(
            key, {"key": key, "cost": 0.0, "runtime_ms": 0, "storage_gb": 0.0, "count": 0}
        )
        row["cost"] += r.cost
        row["runtime_ms"] += r.runtime_ms or 0
        row["storage_gb"] += r.storage_gb or 0.0
        row["count"] += 1
    rows = list(agg.values())
    for row in rows:
        row["cost"] = round(row["cost"], 6)
        row["storage_gb"] = round(row["storage_gb"], 4)
    rows.sort(key=lambda x: x["cost"], reverse=True)
    return rows


def summarize(records: list[BillingRecord], num_days: int) -> dict:
    total_spend = sum_cost(records)
    total_runtime = sum_runtime_ms(records)
    total_storage = sum_storage_gb(records)
    days = max(num_days, 1)

    endpoints = {r.object_id for r in records if r.provider == "runpod"}
    apps = {r.object_id for r in records if r.provider == "modal"}

    endpoint_rows = group_records(
        [r for r in records if r.provider == "runpod"], "endpoint"
    )
    highest_endpoint = (
        {"name": endpoint_rows[0]["key"], "cost": endpoint_rows[0]["cost"]}
        if endpoint_rows
        else None
    )

    platform_rows = group_records(records, "provider")
    highest_platform = (
        {"name": platform_rows[0]["key"], "cost": platform_rows[0]["cost"]}
        if platform_rows
        else None
    )

    return {
        "total_spend": total_spend,
        "avg_daily_spend": round(total_spend / days, 6),
        "total_runtime_ms": total_runtime,
        "avg_daily_runtime_ms": round(total_runtime / days, 1),
        "total_storage_gb": total_storage,
        "active_endpoints": len(endpoints),
        "active_modal_apps": len(apps),
        "highest_cost_endpoint": highest_endpoint,
        "highest_cost_platform": highest_platform,
        "num_days": num_days,
    }


def provider_totals(records: list[BillingRecord]) -> dict:
    labels: list[str] = []
    cost: list[float] = []
    runtime: list[float] = []
    storage: list[float] = []
    for provider in ("runpod", "modal"):
        subset = [r for r in records if r.provider == provider]
        if not subset:
            continue
        labels.append(provider)
        cost.append(sum_cost(subset))
        runtime.append(sum_runtime_ms(subset))
        storage.append(sum_storage_gb(subset))
    return {"labels": labels, "cost": cost, "runtime_ms": runtime, "storage_gb": storage}


def paginate_sort_search(
    records: list[BillingRecord],
    page: int,
    page_size: int,
    sort: Optional[str],
    search: Optional[str],
) -> tuple[list[BillingRecord], int]:
    rows = records
    if search:
        needle = search.lower()
        rows = [
            r
            for r in rows
            if needle in r.object_name.lower()
            or needle in (r.environment or "").lower()
            or needle in (r.gpu or "").lower()
        ]
    if sort == "cost":
        rows = sorted(rows, key=lambda r: r.cost, reverse=True)
    elif sort == "timestamp":
        rows = sorted(rows, key=lambda r: r.timestamp, reverse=True)
    elif sort == "runtime":
        rows = sorted(rows, key=lambda r: r.runtime_ms or 0, reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total
```

- [ ] **Step 9: Run all Task 1 tests to verify they pass**

Run: `pytest app/tests/test_billing_aggregation.py -v`
Expected: PASS (12 tests).

- [ ] **Step 10: Lint and commit**

Run: `make lint-check`
Expected: clean. (If black/isort reports formatting, run `make lint-apply` then re-run `make lint-check`.)

```bash
git add app/schemas/billing_analytics.py app/services/billing_analytics/ app/tests/test_billing_aggregation.py
git commit -m "feat(billing): unified schema, date-range resolver, aggregation functions"
```

---

### Task 2: Provider interface + Runpod provider + config fields

**Files:**
- Create: `app/integrations/billing/__init__.py` (empty package marker)
- Create: `app/integrations/billing/base.py`
- Create: `app/integrations/billing/runpod.py`
- Modify: `app/core/config.py` (add settings fields after the `cache_backend` field, ~line 130)
- Test: `app/tests/test_integrations/test_runpod_billing.py`

**Interfaces:**
- Consumes: `BillingRecord` from `app/schemas/billing_analytics.py`.
- Produces:
  - `ProviderQuery` dataclass: `start: datetime`, `end: datetime`, `base_resolution: str` (`"hour"|"day"`), `grouping: str | None = None`, `endpoint_ids: list[str] | None = None`, `gpu_types: list[str] | None = None`, `data_center_ids: list[str] | None = None`, `tag_names: list[str] | None = None`.
  - `ProviderUnavailable(Exception)`.
  - `AnalyticsProvider(ABC)`: `name: str` (class attr), `async is_available() -> bool`, `async fetch_records(query: ProviderQuery) -> list[BillingRecord]`.
  - `RunpodAnalyticsProvider(AnalyticsProvider)` with `name = "runpod"`.
  - New settings: `runpod_billing_base_url: str`, `billing_cache_ttl_seconds: int`, `runpod_billing_timeout_seconds: float`.

- [ ] **Step 1: Add config fields**

In `app/core/config.py`, immediately after the `cache_backend` field (ends ~line 130), add:

```python
    # Billing analytics (Runpod + Modal)
    runpod_billing_base_url: str = Field(
        default="https://rest.runpod.io/v1",
        description="Base URL for the Runpod REST billing API.",
    )
    runpod_billing_timeout_seconds: float = Field(
        default=30.0, description="Timeout for a single Runpod billing API call."
    )
    billing_cache_ttl_seconds: int = Field(
        default=3600, description="TTL for cached normalized billing records."
    )
```

`RUNPOD_API_KEY` continues to be read from the environment directly (`os.getenv`).

- [ ] **Step 2: Write the failing test for the Runpod provider**

Create `app/tests/test_integrations/test_runpod_billing.py`:

```python
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
    with patch.object(
        provider, "_request", AsyncMock(return_value=mock_resp)
    ):
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
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest app/tests/test_integrations/test_runpod_billing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.billing'`.

- [ ] **Step 4: Create the provider base**

Create `app/integrations/billing/__init__.py` (empty file).

Create `app/integrations/billing/base.py`:

```python
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
```

- [ ] **Step 5: Create the Runpod provider**

Create `app/integrations/billing/runpod.py`:

```python
"""Runpod billing analytics provider (async httpx)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from app.core.config import settings
from app.integrations.billing.base import (
    AnalyticsProvider,
    ProviderQuery,
    ProviderUnavailable,
)
from app.schemas.billing_analytics import BillingRecord

logger = logging.getLogger(__name__)

# Map our base_resolution to Runpod's bucketSize enum.
_BUCKET = {"hour": "hour", "day": "day"}


class RunpodAnalyticsProvider(AnalyticsProvider):
    name = "runpod"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("RUNPOD_API_KEY")
        self.base_url = settings.runpod_billing_base_url.rstrip("/")
        self.timeout = settings.runpod_billing_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    transport=httpx.AsyncHTTPTransport(retries=1),
                )
        return self._client

    async def _request(self, params: list[tuple[str, str]]) -> httpx.Response:
        client = await self._get_client()
        return await client.get(
            "/billing/endpoints",
            params=params,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _build_params(self, query: ProviderQuery) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = [
            ("bucketSize", _BUCKET.get(query.base_resolution, "day")),
            ("startTime", query.start.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("endTime", query.end.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        if query.grouping:
            params.append(("grouping", query.grouping))
        for ep in query.endpoint_ids or []:
            params.append(("endpointId", ep))
        for gpu in query.gpu_types or []:
            params.append(("gpuTypeId", gpu))
        for dc in query.data_center_ids or []:
            params.append(("dataCenterId", dc))
        return params

    @staticmethod
    def _parse_time(value: str) -> datetime:
        text = value.replace("Z", "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        # Last resort: ISO parse.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)

    def _normalize(self, rows: list[dict], grouping: Optional[str]) -> list[BillingRecord]:
        records: list[BillingRecord] = []
        for row in rows:
            gpu = row.get("gpuTypeId")
            endpoint_id = row.get("endpointId")
            object_id = endpoint_id or gpu or "unknown"
            storage = row.get("diskSpaceBilledGB", row.get("diskSpaceBilledGb"))
            records.append(
                BillingRecord(
                    provider="runpod",
                    object_id=str(object_id),
                    object_name=str(object_id),
                    timestamp=self._parse_time(row["time"]),
                    cost=float(row.get("amount", 0.0)),
                    runtime_ms=int(row["timeBilledMs"])
                    if row.get("timeBilledMs") is not None
                    else None,
                    storage_gb=float(storage) if storage is not None else None,
                    gpu=gpu,
                    metadata={"data_center": row.get("dataCenter")},
                )
            )
        return records

    async def fetch_records(self, query: ProviderQuery) -> list[BillingRecord]:
        if not self.api_key:
            raise ProviderUnavailable("runpod", "RUNPOD_API_KEY is not configured")
        params = self._build_params(query)
        try:
            resp = await self._request(params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                "runpod", f"billing API returned {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("runpod", f"billing API request failed: {exc}") from exc
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("billingData", [])
        return self._normalize(rows, query.grouping)
```

- [ ] **Step 6: Run the Runpod tests to verify they pass**

Run: `pytest app/tests/test_integrations/test_runpod_billing.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Lint and commit**

Run: `make lint-check` (run `make lint-apply` first if needed).

```bash
git add app/integrations/billing/__init__.py app/integrations/billing/base.py app/integrations/billing/runpod.py app/core/config.py app/tests/test_integrations/test_runpod_billing.py
git commit -m "feat(billing): AnalyticsProvider interface + Runpod provider + config"
```

---

### Task 3: Modal provider

**Files:**
- Create: `app/integrations/billing/modal.py`
- Test: `app/tests/test_integrations/test_modal_billing.py`

**Interfaces:**
- Consumes: `AnalyticsProvider`, `ProviderQuery`, `ProviderUnavailable` from `base.py`; `BillingRecord`.
- Produces: `ModalAnalyticsProvider(AnalyticsProvider)` with `name = "modal"`.
- Note: `modal.billing.workspace_billing_report(...)` is called via `asyncio.to_thread` (treated as blocking). Modal resolution is `"d"`/`"h"`; base_resolution `"hour"` → `"h"`, else `"d"`. Credentials via `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` env vars (the SDK reads them).

- [ ] **Step 1: Write the failing test**

Create `app/tests/test_integrations/test_modal_billing.py`:

```python
from datetime import datetime
from decimal import Decimal
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


SAMPLE_ITEMS = [
    {
        "object_id": "ap-123",
        "description": "inference-engine",
        "environment_name": "main",
        "interval_start": datetime(2026, 5, 1),
        "cost": Decimal("12.50"),
        "tags": {"team": "llm-platform"},
    },
    {
        "object_id": "ap-456",
        "description": "batch-job",
        "environment_name": "main",
        "interval_start": datetime(2026, 5, 2),
        "cost": Decimal("3.25"),
        "tags": {},
    },
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
    assert r.runtime_ms is None


async def test_is_available_requires_tokens(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    assert await ModalAnalyticsProvider().is_available() is False


async def test_fetch_records_raises_on_sdk_error(monkeypatch):
    monkeypatch.setenv("MODAL_TOKEN_ID", "id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "secret")
    provider = ModalAnalyticsProvider()
    with patch.object(provider, "_call_report", side_effect=RuntimeError("plan required")):
        with pytest.raises(ProviderUnavailable):
            await provider.fetch_records(_query())
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest app/tests/test_integrations/test_modal_billing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.billing.modal'`.

- [ ] **Step 3: Create the Modal provider**

Create `app/integrations/billing/modal.py`:

```python
"""Modal billing analytics provider (wraps modal.billing.workspace_billing_report)."""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Optional

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

    def _call_report(self, query: ProviderQuery) -> list[dict]:
        """Blocking call into the Modal SDK. Patched in tests."""
        import modal  # imported lazily so import-time never requires modal config

        resolution = "h" if query.base_resolution == "hour" else "d"
        return modal.billing.workspace_billing_report(
            start=query.start,
            end=query.end,
            resolution=resolution,
            tag_names=query.tag_names or ["*"],
        )

    def _normalize(self, items: list[dict]) -> list[BillingRecord]:
        records: list[BillingRecord] = []
        for item in items:
            cost_by_resource = item.get("cost_by_resource") or {}
            resource_breakdown = {k: _as_float(v) for k, v in cost_by_resource.items()}
            records.append(
                BillingRecord(
                    provider="modal",
                    object_id=str(item["object_id"]),
                    object_name=str(item.get("description") or item["object_id"]),
                    timestamp=item["interval_start"],
                    cost=_as_float(item.get("cost")),
                    environment=item.get("environment_name"),
                    tags=dict(item.get("tags") or {}),
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
```

- [ ] **Step 4: Run the Modal tests to verify they pass**

Run: `pytest app/tests/test_integrations/test_modal_billing.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint and commit**

Run: `make lint-check` (apply formatting if needed).

```bash
git add app/integrations/billing/modal.py app/tests/test_integrations/test_modal_billing.py
git commit -m "feat(billing): Modal provider via workspace_billing_report"
```

---

### Task 4: BillingAnalyticsService (orchestration, caching, DI)

**Files:**
- Create: `app/services/billing_analytics/service.py`
- Modify: `app/deps.py` (import + alias + `__all__`)
- Test: `app/tests/test_services/test_billing_analytics_service.py`

**Interfaces:**
- Consumes: providers (`RunpodAnalyticsProvider`, `ModalAnalyticsProvider`), `ProviderQuery`, `ProviderUnavailable`; aggregation functions; `BillingRecord` + response models; `CacheBackend` via `get_cache_backend`.
- Produces:
  - `BillingQueryParams` dataclass: `provider: str` (`"all"|"runpod"|"modal"`), `start: datetime`, `end: datetime`, `resolution: str` (display), `group_by: str | None = None`, `search: str | None = None`, `gpu_types: list[str] | None = None`, `data_center_ids: list[str] | None = None`.
  - `BillingAnalyticsService` with async methods: `summary(p)`, `timeseries(p)`, `providers(p)`, `breakdown(p)`, `table(p, page, page_size, sort)`, `records_for_export(p)`.
  - `get_billing_analytics_service() -> BillingAnalyticsService` singleton.
  - `BillingAnalyticsServiceDep` in `app/deps.py`.

- [ ] **Step 1: Write the failing service test**

Create `app/tests/test_services/test_billing_analytics_service.py`:

```python
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

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
            provider="runpod", object_id="ep1", object_name="ep1",
            timestamp=datetime(2026, 5, 1), cost=10.0, runtime_ms=1000, storage_gb=5,
        )
    ]


def _modal_records():
    return [
        BillingRecord(
            provider="modal", object_id="app1", object_name="app1",
            timestamp=datetime(2026, 5, 2), cost=4.0,
        )
    ]


def _service():
    runpod = AsyncMock()
    runpod.name = "runpod"
    runpod.fetch_records = AsyncMock(return_value=_runpod_records())
    modal = AsyncMock()
    modal.name = "modal"
    modal.fetch_records = AsyncMock(return_value=_modal_records())
    return BillingAnalyticsService(
        runpod_provider=runpod, modal_provider=modal, cache=FakeCache()
    ), runpod, modal


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


async def test_timeseries_and_breakdown_and_table():
    service, _, _ = _service()
    ts = await service.timeseries(_params())
    assert ts.labels == ["2026-05-01", "2026-05-02"]
    bd = await service.breakdown(
        BillingQueryParams(
            provider="all", start=datetime(2026, 5, 1), end=datetime(2026, 5, 3),
            resolution="day", group_by="provider",
        )
    )
    assert {row.key for row in bd.rows} == {"runpod", "modal"}
    table = await service.table(_params(), page=1, page_size=10, sort="cost")
    assert table.total == 2
    assert table.rows[0].cost == 10.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest app/tests/test_services/test_billing_analytics_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.billing_analytics.service'`.

- [ ] **Step 3: Create the service**

Create `app/services/billing_analytics/service.py`:

```python
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
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `pytest app/tests/test_services/test_billing_analytics_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Register the DI alias**

In `app/deps.py`, add the import near the other service imports (e.g. after the cache import on line 46):

```python
from app.services.billing_analytics.service import (
    BillingAnalyticsService,
    get_billing_analytics_service,
)
```

Add the alias next to `CacheBackendDep` (~line 107):

```python
BillingAnalyticsServiceDep = Annotated[
    BillingAnalyticsService, Depends(get_billing_analytics_service)
]
```

Add `"BillingAnalyticsServiceDep"` and `"get_billing_analytics_service"` to the `__all__` list.

- [ ] **Step 6: Verify imports resolve, lint, commit**

Run: `python -c "import app.deps; print('BillingAnalyticsServiceDep' in app.deps.__all__)"`
Expected: prints `True`.

Run: `pytest app/tests/test_services/test_billing_analytics_service.py app/tests/test_billing_aggregation.py -v` → PASS.
Run: `make lint-check` (apply formatting if needed).

```bash
git add app/services/billing_analytics/service.py app/deps.py app/tests/test_services/test_billing_analytics_service.py
git commit -m "feat(billing): orchestrator service with caching + DI registration"
```

---

### Task 5: Admin router + endpoints + app mount

**Files:**
- Create: `app/routers/admin_billing.py`
- Modify: `app/api.py` (import + `include_router` with prefix `/api/admin/analytics/billing`)
- Test: `app/tests/test_admin_billing.py`

**Interfaces:**
- Consumes: `BillingAnalyticsServiceDep`, `CurrentAdminDep` from `app/deps.py`; `BillingQueryParams` from service; `resolve_range`; `aggregation.SUPPORTED_GROUP_BYS`; `BadRequestError`.
- Produces: routes `GET /summary`, `/timeseries`, `/providers`, `/breakdown`, `/table`, `/export`, `POST /ai` (501). Mounted at `/api/admin/analytics/billing`.

- [ ] **Step 1: Write the failing router tests**

Create `app/tests/test_admin_billing.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.billing_analytics import (
    BillingRecord,
    SummaryResponse,
    TableResponse,
    TimeseriesResponse,
)

BASE = "/api/admin/analytics/billing"


def _summary():
    return SummaryResponse(
        total_spend=14.0, avg_daily_spend=7.0, total_runtime_ms=1000,
        avg_daily_runtime_ms=500.0, total_storage_gb=5.0, active_endpoints=1,
        active_modal_apps=1, num_days=2, warnings=[],
    )


class TestAuth:
    async def test_summary_requires_admin(self, authenticated_client, test_db):
        resp = await authenticated_client.get(f"{BASE}/summary")
        assert resp.status_code == 403

    async def test_summary_unauthenticated(self, async_client, test_db):
        resp = await async_client.get(f"{BASE}/summary")
        assert resp.status_code == 401


class TestEndpoints:
    async def test_summary_ok(self, admin_client, test_db):
        with patch(
            "app.routers.admin_billing.get_billing_analytics_service"
        ) as factory:
            svc = factory.return_value
            svc.summary = AsyncMock(return_value=_summary())
            resp = await admin_client.get(f"{BASE}/summary?range=last_7_days")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_spend"] == 14.0
        assert body["active_modal_apps"] == 1

    async def test_timeseries_ok(self, admin_client, test_db):
        ts = TimeseriesResponse(
            labels=["2026-05-01"], cost=[14.0], runtime_ms=[1000.0],
            storage_gb=[5.0],
        )
        with patch("app.routers.admin_billing.get_billing_analytics_service") as factory:
            factory.return_value.timeseries = AsyncMock(return_value=ts)
            resp = await admin_client.get(f"{BASE}/timeseries?range=last_7_days&resolution=day")
        assert resp.status_code == 200
        assert resp.json()["cost"] == [14.0]

    async def test_breakdown_rejects_bad_group_by(self, admin_client, test_db):
        resp = await admin_client.get(f"{BASE}/breakdown?range=last_7_days&group_by=banana")
        assert resp.status_code == 400

    async def test_table_ok(self, admin_client, test_db):
        table = TableResponse(
            rows=[BillingRecord(
                provider="runpod", object_id="ep1", object_name="ep1",
                timestamp="2026-05-01T00:00:00", cost=10.0,
            )],
            total=1, page=1, page_size=50,
        )
        with patch("app.routers.admin_billing.get_billing_analytics_service") as factory:
            factory.return_value.table = AsyncMock(return_value=table)
            resp = await admin_client.get(f"{BASE}/table?range=last_7_days")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_export_csv(self, admin_client, test_db):
        with patch("app.routers.admin_billing.get_billing_analytics_service") as factory:
            factory.return_value.records_for_export = AsyncMock(return_value=[
                BillingRecord(
                    provider="runpod", object_id="ep1", object_name="ep1",
                    timestamp="2026-05-01T00:00:00", cost=10.0, runtime_ms=1000,
                    storage_gb=5.0,
                )
            ])
            resp = await admin_client.get(f"{BASE}/export?range=last_7_days")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "ep1" in resp.text

    async def test_ai_endpoint_not_implemented(self, admin_client, test_db):
        resp = await admin_client.post(f"{BASE}/ai", json={"question": "hi"})
        assert resp.status_code == 501
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest app/tests/test_admin_billing.py -v`
Expected: FAIL (404s / import error — router not mounted yet).

- [ ] **Step 3: Create the router**

Create `app/routers/admin_billing.py`:

```python
"""Admin billing analytics endpoints (Runpod + Modal). Admin-only."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.exceptions import BadRequestError
from app.deps import CurrentAdminDep
from app.schemas.billing_analytics import (
    BreakdownResponse,
    ProvidersResponse,
    SummaryResponse,
    TableResponse,
    TimeseriesResponse,
)
from app.services.billing_analytics import aggregation
from app.services.billing_analytics.ranges import resolve_range
from app.services.billing_analytics.service import (
    BillingQueryParams,
    get_billing_analytics_service,
)

router = APIRouter()

_VALID_PROVIDERS = {"all", "runpod", "modal"}
_VALID_RESOLUTIONS = {"hour", "day", "week", "month", "year"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_params(
    provider: str,
    range_name: str | None,
    start: str | None,
    end: str | None,
    resolution: str,
    group_by: str | None = None,
    search: str | None = None,
) -> BillingQueryParams:
    if provider not in _VALID_PROVIDERS:
        raise BadRequestError(
            f"Invalid provider '{provider}'. Use: all, runpod, modal."
        )
    if resolution not in _VALID_RESOLUTIONS:
        raise BadRequestError(
            f"Invalid resolution '{resolution}'. "
            "Use: hour, day, week, month, year."
        )
    try:
        start_dt, end_dt = resolve_range(range_name, start, end, _utcnow())
    except ValueError as exc:
        raise BadRequestError(str(exc))
    return BillingQueryParams(
        provider=provider,
        start=start_dt,
        end=end_dt,
        resolution=resolution,
        group_by=group_by,
        search=search,
    )


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    current_user: CurrentAdminDep,
    provider: str = "all",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
):
    params = _build_params(provider, range, start, end, resolution)
    return await get_billing_analytics_service().summary(params)


@router.get("/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(
    current_user: CurrentAdminDep,
    provider: str = "all",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
    group_by: str | None = None,
):
    if group_by is not None and group_by not in aggregation.SUPPORTED_GROUP_BYS:
        raise BadRequestError(
            f"Invalid group_by '{group_by}'. "
            f"Use one of: {', '.join(aggregation.SUPPORTED_GROUP_BYS)}."
        )
    params = _build_params(provider, range, start, end, resolution, group_by=group_by)
    return await get_billing_analytics_service().timeseries(params)


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers(
    current_user: CurrentAdminDep,
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
):
    params = _build_params("all", range, start, end, resolution)
    return await get_billing_analytics_service().providers(params)


@router.get("/breakdown", response_model=BreakdownResponse)
async def get_breakdown(
    current_user: CurrentAdminDep,
    group_by: str = "provider",
    provider: str = "all",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
):
    if group_by not in aggregation.SUPPORTED_GROUP_BYS:
        raise BadRequestError(
            f"Invalid group_by '{group_by}'. "
            f"Use one of: {', '.join(aggregation.SUPPORTED_GROUP_BYS)}."
        )
    params = _build_params(provider, range, start, end, resolution, group_by=group_by)
    return await get_billing_analytics_service().breakdown(params)


@router.get("/table", response_model=TableResponse)
async def get_table(
    current_user: CurrentAdminDep,
    provider: str = "all",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str | None = "cost",
):
    if page < 1 or page_size < 1 or page_size > 500:
        raise BadRequestError("page must be >= 1 and page_size between 1 and 500.")
    params = _build_params(provider, range, start, end, resolution, search=search)
    return await get_billing_analytics_service().table(
        params, page=page, page_size=page_size, sort=sort
    )


@router.get("/export")
async def export_csv(
    current_user: CurrentAdminDep,
    provider: str = "all",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
):
    params = _build_params(provider, range, start, end, resolution)
    records = await get_billing_analytics_service().records_for_export(params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Provider", "Object", "Timestamp", "Cost (USD)", "Runtime (ms)",
         "Storage (GB)", "GPU", "Environment", "Tags"]
    )
    for r in records:
        tags = "; ".join(f"{k}={v}" for k, v in r.tags.items())
        writer.writerow(
            [r.provider, r.object_name, r.timestamp.isoformat(), f"{r.cost:.6f}",
             r.runtime_ms or "", r.storage_gb or "", r.gpu or "",
             r.environment or "", tags]
        )
    output.seek(0)
    filename = f"billing_{provider}_{params.resolution}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/ai")
async def billing_ai(current_user: CurrentAdminDep):
    """Reserved for the AI Analytics Assistant phase (not yet implemented)."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error_code": "NOT_IMPLEMENTED",
            "message": "The billing AI assistant is not yet available.",
        },
    )
```

Add the two imports this needs to the top of `app/routers/admin_billing.py` — extend the existing `from fastapi import APIRouter` line to `from fastapi import APIRouter, status` and add `from fastapi.responses import JSONResponse, StreamingResponse` (replacing the `StreamingResponse`-only import).

- [ ] **Step 4: Mount the router**

In `app/api.py`, find where `admin_analytics` is included (around line 202-206) and add alongside it:

```python
from app.routers import admin_billing

app.include_router(
    admin_billing.router,
    prefix="/api/admin/analytics/billing",
    tags=["Admin Billing Analytics"],
)
```

(Match the exact import/include style already used for `admin_analytics` in that file.)

- [ ] **Step 5: Run the router tests to verify they pass**

Run: `pytest app/tests/test_admin_billing.py -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Run the full suite, lint, commit**

Run: `pytest app/tests/ -v`
Expected: all pass (no regressions).
Run: `make lint-check` (apply formatting if needed).

```bash
git add app/routers/admin_billing.py app/api.py app/tests/test_admin_billing.py
git commit -m "feat(billing): admin billing analytics endpoints + router mount"
```

---

### Task 6: Frontend billing dashboard page

**Files:**
- Create: `frontend/src/hooks/useBillingAnalytics.ts`
- Create: `frontend/src/pages/AdminBilling.tsx`
- Modify: `frontend/src/App.tsx` (import + route `/admin/billing`)
- Modify: `frontend/src/components/Layout.tsx` (admin nav entry)

**Interfaces:**
- Consumes backend endpoints under `/api/admin/analytics/billing`.
- Produces: `useBillingSummary`, `useBillingTimeseries`, `useBillingProviders`, `useBillingTable`, `useBillingExport` hooks; `AdminBilling` default-export page; `/admin/billing` route; "Billing" nav link.

- [ ] **Step 1: Create the data hooks**

Create `frontend/src/hooks/useBillingAnalytics.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const BASE = '/api/admin/analytics/billing';

export interface BillingFilters {
  provider: 'all' | 'runpod' | 'modal';
  range: string;
  resolution: 'hour' | 'day' | 'week' | 'month' | 'year';
  groupBy?: string;
  search?: string;
}

export interface SummaryData {
  total_spend: number;
  avg_daily_spend: number;
  total_runtime_ms: number;
  avg_daily_runtime_ms: number;
  total_storage_gb: number;
  active_endpoints: number;
  active_modal_apps: number;
  highest_cost_endpoint?: { name: string; cost: number } | null;
  highest_cost_platform?: { name: string; cost: number } | null;
  num_days: number;
  warnings: string[];
}

export interface TimeseriesData {
  labels: string[];
  cost: number[];
  runtime_ms: number[];
  storage_gb: number[];
  cost_by_group: Record<string, number[]>;
  warnings: string[];
}

export interface ProvidersData {
  labels: string[];
  cost: number[];
  runtime_ms: number[];
  storage_gb: number[];
  warnings: string[];
}

export interface BillingRow {
  provider: string;
  object_name: string;
  timestamp: string;
  cost: number;
  runtime_ms: number | null;
  storage_gb: number | null;
  gpu: string | null;
  environment: string | null;
  tags: Record<string, string>;
}

export interface TableData {
  rows: BillingRow[];
  total: number;
  page: number;
  page_size: number;
  warnings: string[];
}

function params(f: BillingFilters, extra: Record<string, string> = {}) {
  const p = new URLSearchParams({
    provider: f.provider,
    range: f.range,
    resolution: f.resolution,
    ...extra,
  });
  return p;
}

function useEndpoint<T>(path: string, f: BillingFilters, extra: Record<string, string> = {}) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const extraKey = JSON.stringify(extra);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = params(f, JSON.parse(extraKey));
      const resp = await axios.get(`${BASE}${path}?${p.toString()}`);
      setData(resp.data);
    } catch (err: any) {
      toast.error(err.response?.data?.message || `Failed to load ${path}`);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, f.provider, f.range, f.resolution, extraKey]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading };
}

export const useBillingSummary = (f: BillingFilters) =>
  useEndpoint<SummaryData>('/summary', f);

export const useBillingTimeseries = (f: BillingFilters) =>
  useEndpoint<TimeseriesData>('/timeseries', f, f.groupBy ? { group_by: f.groupBy } : {});

export const useBillingProviders = (f: BillingFilters) =>
  useEndpoint<ProvidersData>('/providers', f);

export const useBillingTable = (f: BillingFilters, page: number) =>
  useEndpoint<TableData>('/table', f, {
    page: String(page),
    page_size: '50',
    sort: 'cost',
    ...(f.search ? { search: f.search } : {}),
  });

export function useBillingExport() {
  const exportCSV = async (f: BillingFilters) => {
    try {
      const p = params(f);
      const resp = await axios.get(`${BASE}/export?${p.toString()}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([resp.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `billing_${f.provider}_${f.resolution}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success('CSV exported');
    } catch {
      toast.error('Failed to export CSV');
    }
  };
  return { exportCSV };
}
```

- [ ] **Step 2: Create the page**

Create `frontend/src/pages/AdminBilling.tsx`:

```tsx
import { useState } from 'react';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Pie } from 'react-chartjs-2';
import { DollarSign, Clock, HardDrive, Server, Download } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import ChartCard from '../components/ChartCard';
import { Skeleton } from '../components/ui/Skeleton';
import {
  BillingFilters,
  useBillingSummary,
  useBillingTimeseries,
  useBillingProviders,
  useBillingTable,
  useBillingExport,
} from '../hooks/useBillingAnalytics';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement,
  Title, Tooltip, Legend, Filler
);

const RANGES = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['last_7_days', 'Last 7 Days'],
  ['last_30_days', 'Last 30 Days'], ['last_90_days', 'Last 90 Days'],
  ['this_month', 'This Month'], ['last_month', 'Last Month'],
] as const;

const PLATFORM_COLORS = ['#4363D8', '#F58231'];

export default function AdminBilling() {
  const [filters, setFilters] = useState<BillingFilters>({
    provider: 'all', range: 'last_30_days', resolution: 'day',
  });
  const [page, setPage] = useState(1);

  const { data: summary, loading: summaryLoading } = useBillingSummary(filters);
  const { data: timeseries } = useBillingTimeseries(filters);
  const { data: providers } = useBillingProviders(filters);
  const { data: table } = useBillingTable(filters, page);
  const { exportCSV } = useBillingExport();

  const set = (patch: Partial<BillingFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const costLine = {
    labels: timeseries?.labels || [],
    datasets: [{
      label: 'Cost (USD)', data: timeseries?.cost || [],
      borderColor: '#4363D8', backgroundColor: 'transparent', tension: 0.4,
    }],
  };

  const platformPie = {
    labels: providers?.labels || [],
    datasets: [{
      data: providers?.cost || [],
      backgroundColor: PLATFORM_COLORS,
    }],
  };

  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false }, ticks: { color: 'rgba(156,163,175,0.8)' } },
      y: { grid: { color: 'rgba(156,163,175,0.1)' }, beginAtZero: true,
           ticks: { color: 'rgba(156,163,175,0.8)' } },
    },
  };

  if (summaryLoading && !summary) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
        <Skeleton className="h-[400px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Infrastructure Billing
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Runpod & Modal spend, runtime, and storage analytics.
          </p>
        </div>
        <button
          onClick={() => exportCSV(filters)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium"
        >
          <Download size={16} /> Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filters.provider}
          onChange={(e) => set({ provider: e.target.value as BillingFilters['provider'] })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          <option value="all">All Platforms</option>
          <option value="runpod">Runpod</option>
          <option value="modal">Modal</option>
        </select>
        <select
          value={filters.range}
          onChange={(e) => set({ range: e.target.value })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {RANGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <select
          value={filters.resolution}
          onChange={(e) => set({ resolution: e.target.value as BillingFilters['resolution'] })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {['hour', 'day', 'week', 'month', 'year'].map((r) =>
            <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
        </select>
      </div>

      {summary?.warnings?.map((w) => (
        <div key={w} className="text-sm text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 px-4 py-2 rounded-lg">
          {w}
        </div>
      ))}

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard label="Total Spend" value={`$${(summary?.total_spend || 0).toFixed(2)}`} icon={DollarSign} color="bg-blue-500" />
        <MetricCard label="Avg Daily Spend" value={`$${(summary?.avg_daily_spend || 0).toFixed(2)}`} icon={DollarSign} color="bg-green-500" />
        <MetricCard label="Compute Time" value={`${((summary?.total_runtime_ms || 0) / 3_600_000).toFixed(1)}h`} icon={Clock} color="bg-orange-500" />
        <MetricCard label="Storage" value={`${(summary?.total_storage_gb || 0).toFixed(0)} GB`} icon={HardDrive} color="bg-purple-500" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="lg:col-span-2">
          <ChartCard title="Cost Over Time" description="Spend per bucket across selected platforms" className="h-[400px]">
            <div className="flex-1 min-h-0"><Line options={chartOptions} data={costLine} /></div>
          </ChartCard>
        </div>
        <ChartCard title="Spend by Platform" description="Runpod vs Modal">
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <Pie data={platformPie} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </ChartCard>
        <div className="bg-white dark:bg-secondary rounded-xl border border-gray-200 dark:border-white/5 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Highlights</h3>
          <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-2">
            <li>Active endpoints: <b>{summary?.active_endpoints ?? 0}</b></li>
            <li>Active Modal apps: <b>{summary?.active_modal_apps ?? 0}</b></li>
            <li>Top endpoint: <b>{summary?.highest_cost_endpoint?.name ?? 'N/A'}</b> (${(summary?.highest_cost_endpoint?.cost ?? 0).toFixed(2)})</li>
            <li>Top platform: <b>{summary?.highest_cost_platform?.name ?? 'N/A'}</b> (${(summary?.highest_cost_platform?.cost ?? 0).toFixed(2)})</li>
          </ul>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-secondary rounded-xl border border-gray-200 dark:border-white/5 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Server size={18} /> Billing Records
          </h3>
          <input
            type="text" placeholder="Search object / GPU / env..."
            onChange={(e) => set({ search: e.target.value || undefined })}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-white/10 text-left text-gray-500 dark:text-gray-400">
                <th className="py-2 px-3">Provider</th><th className="py-2 px-3">Object</th>
                <th className="py-2 px-3">Date</th><th className="py-2 px-3 text-right">Cost</th>
                <th className="py-2 px-3">GPU</th><th className="py-2 px-3">Env</th>
              </tr>
            </thead>
            <tbody>
              {(table?.rows || []).map((r, i) => (
                <tr key={i} className="border-b border-gray-100 dark:border-white/5">
                  <td className="py-2 px-3">{r.provider}</td>
                  <td className="py-2 px-3">{r.object_name}</td>
                  <td className="py-2 px-3">{r.timestamp.slice(0, 10)}</td>
                  <td className="py-2 px-3 text-right">${r.cost.toFixed(4)}</td>
                  <td className="py-2 px-3">{r.gpu || '-'}</td>
                  <td className="py-2 px-3">{r.environment || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between mt-4 text-sm text-gray-500 dark:text-gray-400">
          <span>{table?.total ?? 0} records</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 rounded border border-gray-200 dark:border-white/10 disabled:opacity-40">Prev</button>
            <button disabled={!table || page * table.page_size >= table.total}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border border-gray-200 dark:border-white/10 disabled:opacity-40">Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add the route**

In `frontend/src/App.tsx`, add the import next to the `AdminAnalytics` import:

```tsx
import AdminBilling from './pages/AdminBilling';
```

Add a route block mirroring the existing `/admin/analytics` route (copy its structure exactly, changing path and component):

```tsx
<Route
  path="/admin/billing"
  element={
    <RequireAuth>
      <Layout>
        <PageTitle title="Infrastructure Billing">
          <AdminBilling />
        </PageTitle>
      </Layout>
    </RequireAuth>
  }
/>
```

- [ ] **Step 4: Add the nav link**

In `frontend/src/components/Layout.tsx`, add `Wallet` to the lucide-react import (line 4-16), and add a nav entry inside the admin array (after the `Analytics` entry at line 30):

```tsx
          { name: 'Billing', href: '/admin/billing', icon: Wallet },
```

- [ ] **Step 5: Build and lint**

Run: `cd frontend && npm run build`
Expected: TypeScript compiles, Vite build succeeds, output in `../app/static/react_build/`.

Run: `cd frontend && npm run lint`
Expected: no errors, no warnings (lint runs with `--max-warnings 0`).

Fix any type/lint errors before committing (common: unused imports — remove `BarElement` if unused, etc.).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useBillingAnalytics.ts frontend/src/pages/AdminBilling.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat(billing): admin billing dashboard page + route + nav"
```

---

### Task 7: Documentation + deferred-phase notes

**Files:**
- Create: `docs/billing-analytics.md`
- Modify: `docs/superpowers/specs/2026-06-29-runpod-modal-billing-analytics-design.md` (append an "Implemented (MVP)" status note)

- [ ] **Step 1: Write the feature doc**

Create `docs/billing-analytics.md`:

```markdown
# Admin Billing Analytics (Runpod + Modal)

Admin-only dashboard at `/admin/billing` reporting infrastructure spend, runtime,
and storage across Runpod and Modal. Backed by `/api/admin/analytics/billing/*`.

## Configuration

Environment variables:

- `RUNPOD_API_KEY` — Runpod billing API auth (already used elsewhere).
- `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` — Modal billing API (Team/Enterprise plan).
- `RUNPOD_BILLING_BASE_URL` — optional, defaults to `https://rest.runpod.io/v1`.
- `BILLING_CACHE_TTL_SECONDS` — optional, defaults to 3600.

## Endpoints

All admin-only (`CurrentAdminDep`), under `/api/admin/analytics/billing`:

| Endpoint | Purpose |
|---|---|
| `GET /summary` | Executive summary cards |
| `GET /timeseries` | Cost/runtime/storage over time (`resolution`, `group_by`) |
| `GET /providers` | Per-platform comparison |
| `GET /breakdown` | Grouped aggregates (`group_by`) |
| `GET /table` | Paginated, sortable, searchable rows |
| `GET /export` | CSV export |
| `POST /ai` | Reserved (501) — AI assistant phase |

Shared query params: `provider` (all/runpod/modal), `range` (named) or
`start`/`end` (ISO), `resolution` (hour/day/week/month/year). `group_by`
supports: provider, endpoint, app, gpu, environment.

## Architecture

`router → BillingAnalyticsService → AnalyticsProvider (Runpod|Modal) → cache → aggregation`.
Providers fetch at a base resolution (hour/day); the aggregation layer rolls up to
week/month/year. Records are cached in `CacheBackend` keyed by query.

## Deferred (later phases)

- AI Analytics Assistant (`POST /ai`) + automatic insights/anomalies — consume the
  same aggregation outputs (structured summary → GPT), never raw rows.
- Forecasting / predictions.
- `group_by` for datacenter and tags; GPU-utilization charts; heatmaps; Excel/PDF export.
- Optional DB persistence + scheduled sync for longer history (slots behind the
  service without changing the API contract).
```

- [ ] **Step 2: Append implementation status to the spec**

Append to the end of `docs/superpowers/specs/2026-06-29-runpod-modal-billing-analytics-design.md`:

```markdown

## Implementation status

MVP implemented per `docs/superpowers/plans/2026-06-29-admin-billing-analytics.md`.
Deferred items (AI assistant, forecasting, datacenter/tags grouping, heatmaps,
Excel/PDF export, DB persistence) remain for later phases.
```

- [ ] **Step 3: Run full suite + lint one final time, commit**

Run: `pytest app/tests/ -v` → all pass.
Run: `make lint-check` → clean.

```bash
git add docs/billing-analytics.md docs/superpowers/specs/2026-06-29-runpod-modal-billing-analytics-design.md
git commit -m "docs(billing): feature documentation + spec status note"
```

---

## Self-Review Notes

- **Spec coverage:** unified schema (Task 1) ✓; aggregation utilities (Task 1) ✓; Runpod provider w/ httpx + filters (Task 2) ✓; Modal provider (Task 3) ✓; service + caching + concurrency + partial failure (Task 4) ✓; six MVP endpoints + admin gating + CSV export + reserved AI 501 (Task 5) ✓; config/env (Task 2/3) ✓; frontend page + hooks + route + nav + charts (Task 6) ✓; tests at every backend layer (Tasks 1–5) ✓; docs (Task 7) ✓. Deferred items explicitly out of scope and documented.
- **Type consistency:** `BillingRecord`, `BillingQueryParams`, `ProviderQuery`, response envelopes, and aggregation function names are used identically across Tasks 1–6. Service method names (`summary/timeseries/providers/breakdown/table/records_for_export`) match the router calls and the frontend hook endpoints.
- **Known MVP limitations (documented, intentional):** `group_by` supports provider/endpoint/app/gpu/environment (datacenter/tags deferred); Modal rows have no runtime/storage; frontend uses build+lint as the gate (no test runner installed).
