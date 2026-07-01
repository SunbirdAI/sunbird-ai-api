# Vast.ai Training Billing + Dashboard Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the admin billing dashboard into category sections and add Vast.ai as a "Training" category (amortized per-day records + a per-job table), reusing the existing Inference dashboard machinery.

**Architecture:** A thin `PROVIDER_CATEGORY` map + a `category` query param select which providers a request targets; the existing provider-agnostic schema/aggregation/caching pipeline is otherwise unchanged. A new `VastaiAnalyticsProvider` fetches Vast.ai's per-contract charges, parses the item breakdown, and amortizes each contract's cost/runtime evenly across the days it spans into per-day `BillingRecord`s. The frontend gains a tab switcher; the Training tab reuses the Inference components with training labels and a per-job (grouped) table.

**Tech Stack:** FastAPI, Pydantic v2, async `httpx` (Vast.ai `/api/v0/charges/`), existing `CacheBackend`, React 18 + Vite + TypeScript + Chart.js + axios.

## Global Constraints

- Backend gate per task: run the task's tests with `python -m pytest <files> -v` (all pass). The repo has 4 PRE-EXISTING failures in `app/tests/test_config.py` (Google Analytics) — ignore them; never count them as regressions.
- Lint gate (the real one): changed files clean under black, isort, AND flake8 — `python -m black --check <files>`, `python -m isort --check-only <files>`, `python -m flake8 <files>`. Apply `python -m black <files>` / `python -m isort <files>` and re-check if needed. IGNORE `make lint-check` (pre-existingly broken by a `node_modules` flake8 error) and `npm run lint` (no eslint config in the repo).
- Frontend gate: `cd frontend && npm run build` (runs `tsc && vite build`, `noUnusedLocals`/`noUnusedParameters` enforced — remove every unused import/var). The repo tracks build output under `app/static/react_build/`; commit it when it changes.
- Reuse existing patterns: providers implement `AnalyticsProvider.fetch_records`; DI/service singletons unchanged; router imports deps from `app/deps.py`; custom exceptions from `app/core/exceptions.py`.
- All timestamps are UTC and **naive** (the `BillingRecord.timestamp` field validator coerces tz-aware → naive UTC). Provider API keys are server-side only (never in responses/warnings/CSV).
- Tests follow `asyncio_mode=auto` (no `@pytest.mark.asyncio`). Stage ONLY each task's files with explicit `git add <paths>` (never `-am`/`-A`; never commit `.claude/settings.local.json`).
- Categories: `inference` = {runpod, modal}; `training` = {vastai}. Default category is `inference`. Vast.ai contract types default to `instance,volume`.

---

### Task 1: Foundations — provider literal, category map, `object` group key, config

**Files:**
- Modify: `app/schemas/billing_analytics.py` (Provider literal)
- Create: `app/integrations/billing/categories.py`
- Modify: `app/services/billing_analytics/aggregation.py` (`_GROUP_KEY_FUNCS`)
- Modify: `app/core/config.py` (Vast.ai settings)
- Test: `app/tests/test_billing_categories.py`, and additions to `app/tests/test_billing_aggregation.py`

**Interfaces:**
- Produces:
  - `Provider = Literal["runpod", "modal", "vastai"]`.
  - `app/integrations/billing/categories.py`: `PROVIDER_CATEGORY: dict[str, str]`, `CATEGORIES: tuple[str, ...]` (`("inference", "training")`), `providers_in_category(category: str) -> list[str]`.
  - aggregation `SUPPORTED_GROUP_BYS` gains `"object"` (maps `object_name` for any provider).
  - config: `vast_api_key`? (No — read via env in the provider.) New settings: `vast_billing_base_url: str`, `vast_billing_timeout_seconds: float`, `vast_contract_types_raw: str` + property `vast_contract_types: list[str]`.

- [ ] **Step 1: Write the failing test for the categories module**

Create `app/tests/test_billing_categories.py`:

```python
import pytest

from app.integrations.billing.categories import (
    CATEGORIES,
    PROVIDER_CATEGORY,
    providers_in_category,
)


def test_provider_category_map():
    assert PROVIDER_CATEGORY["runpod"] == "inference"
    assert PROVIDER_CATEGORY["modal"] == "inference"
    assert PROVIDER_CATEGORY["vastai"] == "training"


def test_categories_tuple():
    assert CATEGORIES == ("inference", "training")


def test_providers_in_category():
    assert set(providers_in_category("inference")) == {"runpod", "modal"}
    assert providers_in_category("training") == ["vastai"]


def test_providers_in_category_unknown_raises():
    with pytest.raises(ValueError):
        providers_in_category("nope")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest app/tests/test_billing_categories.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.billing.categories'`.

- [ ] **Step 3: Create the categories module**

Create `app/integrations/billing/categories.py`:

```python
"""Mapping of billing providers to dashboard categories.

A thin layer so the provider-agnostic pipeline can be sliced by category
(inference / training / later cloud) without any structural change.
"""

from __future__ import annotations

# provider -> category
PROVIDER_CATEGORY: dict[str, str] = {
    "runpod": "inference",
    "modal": "inference",
    "vastai": "training",
}

CATEGORIES: tuple[str, ...] = ("inference", "training")


def providers_in_category(category: str) -> list[str]:
    """Return the provider names belonging to a category (order-stable)."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'. Use one of: {CATEGORIES}.")
    return [p for p, c in PROVIDER_CATEGORY.items() if c == category]
```

- [ ] **Step 4: Add `"vastai"` to the Provider literal**

In `app/schemas/billing_analytics.py`, change:

```python
Provider = Literal["runpod", "modal"]
```

to:

```python
Provider = Literal["runpod", "modal", "vastai"]
```

- [ ] **Step 5: Write the failing test for the `object` group key**

Append to `app/tests/test_billing_aggregation.py`:

```python
def test_group_records_by_object_any_provider():
    recs = [
        _rec(provider="vastai", object_id="instance-1", object_name="job-a", cost=10.0),
        _rec(provider="vastai", object_id="instance-1", object_name="job-a", cost=5.0),
        _rec(provider="vastai", object_id="instance-2", object_name="job-b", cost=3.0),
    ]
    rows = group_records(recs, "object")
    keys = {row["key"]: row["cost"] for row in rows}
    assert keys == {"job-a": 15.0, "job-b": 3.0}


def test_object_in_supported_group_bys():
    from app.services.billing_analytics.aggregation import SUPPORTED_GROUP_BYS

    assert "object" in SUPPORTED_GROUP_BYS
```

- [ ] **Step 6: Run to verify the group-key tests fail**

Run: `python -m pytest app/tests/test_billing_aggregation.py::test_object_in_supported_group_bys -v`
Expected: FAIL (`"object"` not in `SUPPORTED_GROUP_BYS`).

- [ ] **Step 7: Add the `object` group key**

In `app/services/billing_analytics/aggregation.py`, extend `_GROUP_KEY_FUNCS`:

```python
_GROUP_KEY_FUNCS = {
    "provider": lambda r: r.provider,
    "object": lambda r: r.object_name,
    "endpoint": lambda r: r.object_name if r.provider == "runpod" else None,
    "app": lambda r: r.object_name if r.provider == "modal" else None,
    "gpu": lambda r: r.gpu,
    "environment": lambda r: r.environment,
}
```

- [ ] **Step 8: Add Vast.ai config fields**

In `app/core/config.py`, immediately after the `runpod_include_network_volumes` field, add:

```python
    # Vast.ai (training) billing
    vast_billing_base_url: str = Field(
        default="https://console.vast.ai",
        description="Base URL for the Vast.ai charges API.",
    )
    vast_billing_timeout_seconds: float = Field(
        default=30.0, description="Timeout for a single Vast.ai charges API call."
    )
    vast_contract_types_raw: str = Field(
        default="instance,volume",
        alias="VAST_CONTRACT_TYPES",
        description=(
            "Comma-separated Vast.ai contract types to include "
            "(instance, volume, serverless). Empty = all types."
        ),
    )

    @property
    def vast_contract_types(self) -> list[str]:
        """Parsed list of Vast.ai contract types to include (may be empty)."""
        return [
            part.strip()
            for part in self.vast_contract_types_raw.split(",")
            if part.strip()
        ]
```

`VAST_API_KEY` is read from the environment directly in the provider (`os.getenv`).

- [ ] **Step 9: Run all Task 1 tests**

Run: `python -m pytest app/tests/test_billing_categories.py app/tests/test_billing_aggregation.py -v`
Expected: PASS.

- [ ] **Step 10: Lint and commit**

Run black/isort/flake8 on the changed files (apply formatting if needed).

```bash
git add app/integrations/billing/categories.py app/schemas/billing_analytics.py app/services/billing_analytics/aggregation.py app/core/config.py app/tests/test_billing_categories.py app/tests/test_billing_aggregation.py
git commit -m "feat(billing): category map, vastai provider literal, object group key, vast config"
```

---

### Task 2: VastaiAnalyticsProvider (fetch, pagination, item parse, amortization)

**Files:**
- Create: `app/integrations/billing/vastai.py`
- Test: `app/tests/test_integrations/test_vastai_billing.py`

**Interfaces:**
- Consumes: `AnalyticsProvider`, `ProviderQuery`, `ProviderUnavailable` from `base.py`; `BillingRecord`; `settings.vast_billing_base_url`, `settings.vast_billing_timeout_seconds`, `settings.vast_contract_types`.
- Produces: `VastaiAnalyticsProvider(AnalyticsProvider)` with `name = "vastai"`. `fetch_records(query)` returns amortized per-day `BillingRecord`s (`provider="vastai"`, `object_id=source`, `object_name=label|description`, `cost=amount/num_days`, `runtime_ms=gpu_ms/num_days | None`, `storage_gb=None`, `resource_breakdown` per item type, `metadata={"kind":"vastai_contract", "contract_type", "contract_start", "contract_end", "gpu_name", "num_days"}`). Patch seams for tests: `_request`.

- [ ] **Step 1: Write the failing tests**

Create `app/tests/test_integrations/test_vastai_billing.py`:

```python
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
    "end": 1730678400,    # 2024-11-04 00:00 UTC
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
        provider, "_request", AsyncMock(side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
        ])
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest app/tests/test_integrations/test_vastai_billing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.integrations.billing.vastai'`.

- [ ] **Step 3: Create the provider**

Create `app/integrations/billing/vastai.py`:

```python
"""Vast.ai billing analytics provider (async httpx, paginated, amortizing)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
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

_HOURS_RE = re.compile(r"([\d.]+)\s*hours?")
_MAX_PAGES = 50  # safety cap


def _to_unix(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def _from_unix_day(ts: int) -> datetime:
    """Unix seconds -> naive UTC datetime truncated to the start of the day."""
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


class VastaiAnalyticsProvider(AnalyticsProvider):
    name = "vastai"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("VAST_API_KEY")
        self.base_url = settings.vast_billing_base_url.rstrip("/")
        self.timeout = settings.vast_billing_timeout_seconds
        self.contract_types = settings.vast_contract_types
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
            "/api/v0/charges/",
            params=params,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _select_filters(self, query: ProviderQuery) -> str:
        filters: dict = {
            "day": {"gte": _to_unix(query.start), "lte": _to_unix(query.end)}
        }
        if self.contract_types:
            filters["type"] = {"in": self.contract_types}
        return json.dumps(filters)

    async def _fetch_all_contracts(self, query: ProviderQuery) -> list[dict]:
        contracts: list[dict] = []
        after_token: Optional[str] = None
        for _ in range(_MAX_PAGES):
            params: list[tuple[str, str]] = [
                ("select_filters", self._select_filters(query)),
                ("limit", "500"),
            ]
            if after_token:
                params.append(("after_token", after_token))
            resp = await self._request(params)
            if resp.status_code >= 400:
                raise ProviderUnavailable(
                    "vastai", f"charges API returned {resp.status_code}"
                )
            payload = resp.json()
            contracts.extend(payload.get("results") or payload.get("rows") or [])
            after_token = payload.get("next_token") or (
                payload.get("pagination") or {}
            ).get("next_page_token")
            if not after_token:
                break
        return contracts

    @staticmethod
    def _parse_gpu_ms(items: list[dict]) -> Optional[int]:
        total = 0.0
        for item in items:
            if item.get("type") == "gpu":
                match = _HOURS_RE.search(item.get("description", "") or "")
                if match:
                    total += float(match.group(1)) * 3600 * 1000
        return int(total) if total else None

    def _amortize(self, contract: dict) -> list[BillingRecord]:
        start = contract.get("start")
        end = contract.get("end")
        if start is None or end is None:
            return []
        amount = float(contract.get("amount", 0.0))
        items = contract.get("items") or []
        source = str(contract.get("source") or "vastai")
        meta = contract.get("metadata") or {}
        label = meta.get("label") or contract.get("description") or source
        contract_type = contract.get("type")

        breakdown: dict[str, float] = {}
        for item in items:
            itype = item.get("type")
            if itype:
                breakdown[itype] = breakdown.get(itype, 0.0) + float(
                    item.get("amount", 0.0)
                )
        gpu_ms = self._parse_gpu_ms(items)

        start_day = _from_unix_day(start)
        end_dt = datetime.fromtimestamp(int(end), tz=timezone.utc).replace(tzinfo=None)
        days: list[datetime] = []
        cursor = start_day
        while cursor <= end_dt:
            days.append(cursor)
            cursor += timedelta(days=1)
        num_days = max(len(days), 1)

        per_day_breakdown = {k: v / num_days for k, v in breakdown.items()}
        records: list[BillingRecord] = []
        for day in days:
            records.append(
                BillingRecord(
                    provider="vastai",
                    object_id=source,
                    object_name=str(label),
                    timestamp=day,
                    cost=amount / num_days,
                    runtime_ms=(gpu_ms // num_days) if gpu_ms else None,
                    storage_gb=None,
                    resource_breakdown=dict(per_day_breakdown),
                    metadata={
                        "kind": "vastai_contract",
                        "contract_type": contract_type,
                        "contract_start": int(start),
                        "contract_end": int(end),
                        "gpu_name": meta.get("gpu_name"),
                        "num_days": num_days,
                    },
                )
            )
        return records

    async def fetch_records(self, query: ProviderQuery) -> list[BillingRecord]:
        if not self.api_key:
            raise ProviderUnavailable("vastai", "VAST_API_KEY is not configured")
        try:
            contracts = await self._fetch_all_contracts(query)
        except ProviderUnavailable:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "vastai", f"charges API request failed: {exc}"
            ) from exc
        records: list[BillingRecord] = []
        for contract in contracts:
            records.extend(self._amortize(contract))
        return records
```

- [ ] **Step 4: Run the Vast.ai tests**

Run: `python -m pytest app/tests/test_integrations/test_vastai_billing.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint and commit**

Run black/isort/flake8 on the two files (apply formatting if needed).

```bash
git add app/integrations/billing/vastai.py app/tests/test_integrations/test_vastai_billing.py
git commit -m "feat(billing): Vast.ai provider with paginated fetch + per-day amortization"
```

---

### Task 3: Service — category routing, register Vast.ai, cache key, active_instances

**Files:**
- Modify: `app/services/billing_analytics/service.py`
- Modify: `app/services/billing_analytics/aggregation.py` (`summarize` → `active_instances`)
- Modify: `app/schemas/billing_analytics.py` (`SummaryResponse.active_instances`)
- Test: additions to `app/tests/test_services/test_billing_analytics_service.py`, `app/tests/test_billing_aggregation.py`

**Interfaces:**
- Consumes: `providers_in_category` from `categories.py`; `VastaiAnalyticsProvider`.
- Produces:
  - `BillingQueryParams` gains `category: str = "inference"`.
  - `BillingAnalyticsService.__init__` adds `self.vastai`; `_providers_for(category, provider)`.
  - `_cache_key` includes `category`.
  - `summarize(...)` result gains `active_instances` (distinct `vastai` object_ids); `SummaryResponse.active_instances: int`.

- [ ] **Step 1: Write the failing test for active_instances**

Append to `app/tests/test_billing_aggregation.py`:

```python
def test_summarize_active_instances():
    recs = [
        _rec(provider="vastai", object_id="instance-1", object_name="a", cost=5.0),
        _rec(provider="vastai", object_id="instance-2", object_name="b", cost=3.0),
        _rec(provider="runpod", object_id="ep1", object_name="ep1", cost=1.0),
    ]
    s = summarize(recs, num_days=1)
    assert s["active_instances"] == 2
    assert s["active_endpoints"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest app/tests/test_billing_aggregation.py::test_summarize_active_instances -v`
Expected: FAIL with `KeyError: 'active_instances'`.

- [ ] **Step 3: Add active_instances to summarize**

In `app/services/billing_analytics/aggregation.py`, inside `summarize`, add near the other counts (after `apps = {...}`):

```python
    instances = {r.object_id for r in records if r.provider == "vastai"}
```

and add to the returned dict (after `"active_modal_apps": len(apps),`):

```python
        "active_instances": len(instances),
```

- [ ] **Step 4: Add the field to SummaryResponse**

In `app/schemas/billing_analytics.py`, in `SummaryResponse`, after `active_modal_apps: int`:

```python
    active_instances: int = 0
```

(Default `0` keeps existing test fixtures valid.)

- [ ] **Step 5: Write the failing service test for category routing**

Append to `app/tests/test_services/test_billing_analytics_service.py`:

```python
def _service_with_vastai():
    runpod = AsyncMock()
    runpod.name = "runpod"
    runpod.fetch_records = AsyncMock(return_value=_runpod_records())
    modal = AsyncMock()
    modal.name = "modal"
    modal.fetch_records = AsyncMock(return_value=_modal_records())
    vastai = AsyncMock()
    vastai.name = "vastai"
    vastai.fetch_records = AsyncMock(return_value=[
        BillingRecord(
            provider="vastai", object_id="instance-1", object_name="job",
            timestamp=datetime(2026, 5, 1), cost=7.0,
        )
    ])
    service = BillingAnalyticsService(
        runpod_provider=runpod, modal_provider=modal, cache=FakeCache()
    )
    service.vastai = vastai
    return service, runpod, modal, vastai


async def test_training_category_uses_only_vastai():
    service, runpod, modal, vastai = _service_with_vastai()
    p = BillingQueryParams(
        provider="all", start=datetime(2026, 5, 1), end=datetime(2026, 5, 3),
        resolution="day", category="training",
    )
    result = await service.summary(p)
    vastai.fetch_records.assert_awaited()
    runpod.fetch_records.assert_not_awaited()
    modal.fetch_records.assert_not_awaited()
    assert result.total_spend == 7.0


async def test_inference_category_uses_runpod_and_modal():
    service, runpod, modal, vastai = _service_with_vastai()
    p = BillingQueryParams(
        provider="all", start=datetime(2026, 5, 1), end=datetime(2026, 5, 3),
        resolution="day", category="inference",
    )
    await service.summary(p)
    runpod.fetch_records.assert_awaited()
    modal.fetch_records.assert_awaited()
    vastai.fetch_records.assert_not_awaited()
```

- [ ] **Step 6: Run to verify it fails**

Run: `python -m pytest app/tests/test_services/test_billing_analytics_service.py::test_training_category_uses_only_vastai -v`
Expected: FAIL (`BillingQueryParams` has no `category`, or routing ignores it).

- [ ] **Step 7: Implement category routing in the service**

In `app/services/billing_analytics/service.py`:

Add the import near the other billing imports:

```python
from app.integrations.billing.categories import providers_in_category
from app.integrations.billing.vastai import VastaiAnalyticsProvider
```

Add `category` to `BillingQueryParams` (after `provider`):

```python
    category: str = "inference"
```

In `__init__`, add this line right after `self.modal = modal_provider or ModalAnalyticsProvider()`:

```python
        self.vastai = VastaiAnalyticsProvider()
```

Replace `_providers_for` with a category+provider aware version:

```python
    def _provider_by_name(self, name: str) -> AnalyticsProvider:
        return {"runpod": self.runpod, "modal": self.modal, "vastai": self.vastai}[name]

    def _providers_for(self, category: str, provider: str) -> list[AnalyticsProvider]:
        names = providers_in_category(category)
        if provider != "all":
            names = [n for n in names if n == provider]
        return [self._provider_by_name(n) for n in names]
```

Update the call site in `_fetch_and_cache` from `self._providers_for(p.provider)` to:

```python
        providers = self._providers_for(p.category, p.provider)
```

Update `_cache_key` to include the category — change the returned string prefix to:

```python
        return (
            f"billing:v3:{p.category}:{p.provider}:{p.start.isoformat()}"
            f":{p.end.isoformat()}:{p.base_resolution}:{runpod_grouping}"
            f":{gpus}:{dcs}:{eids}"
        )
```

In `summary(...)`, add `active_instances=data["active_instances"]` to the `SummaryResponse(...)` construction (alongside `active_modal_apps=...`).

- [ ] **Step 8: Run the service + aggregation tests**

Run: `python -m pytest app/tests/test_services/test_billing_analytics_service.py app/tests/test_billing_aggregation.py -v`
Expected: PASS.

- [ ] **Step 9: Lint and commit**

Run black/isort/flake8 on the changed files (apply formatting if needed).

```bash
git add app/services/billing_analytics/service.py app/services/billing_analytics/aggregation.py app/schemas/billing_analytics.py app/tests/test_services/test_billing_analytics_service.py app/tests/test_billing_aggregation.py
git commit -m "feat(billing): category-aware provider routing + register Vast.ai + active_instances"
```

---

### Task 4: Router — `category` query param on all endpoints

**Files:**
- Modify: `app/routers/admin_billing.py`
- Test: additions to `app/tests/test_admin_billing.py`

**Interfaces:**
- Consumes: `CATEGORIES` from `categories.py`; `BillingQueryParams.category`.
- Produces: every billing endpoint accepts `category` (default `inference`), validated; passed into `BillingQueryParams`.

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/test_admin_billing.py`:

```python
class TestCategory:
    async def test_invalid_category_rejected(self, admin_client, test_db):
        resp = await admin_client.get(f"{BASE}/summary?category=banana")
        assert resp.status_code == 400

    async def test_training_category_routes_to_service(self, admin_client, test_db):
        captured = {}

        async def fake_summary(params):
            captured["category"] = params.category
            return _summary()

        with patch("app.routers.admin_billing.get_billing_analytics_service"):
            # dependency override path
            from app.api import app
            from app.services.billing_analytics.service import (
                get_billing_analytics_service,
            )

            svc = AsyncMock()
            svc.summary = AsyncMock(side_effect=fake_summary)
            app.dependency_overrides[get_billing_analytics_service] = lambda: svc
            try:
                resp = await admin_client.get(
                    f"{BASE}/summary?category=training&range=last_7_days"
                )
            finally:
                app.dependency_overrides.pop(get_billing_analytics_service, None)
        assert resp.status_code == 200
        assert captured["category"] == "training"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest app/tests/test_admin_billing.py::TestCategory -v`
Expected: FAIL (category not validated / not threaded).

- [ ] **Step 3: Add category to the router**

In `app/routers/admin_billing.py`:

Add the import:

```python
from app.integrations.billing.categories import CATEGORIES
```

Add `category` to `_build_params` — change its signature and body:

```python
def _build_params(
    provider: str,
    range_name: str | None,
    start: str | None,
    end: str | None,
    resolution: str,
    group_by: str | None = None,
    search: str | None = None,
    category: str = "inference",
) -> BillingQueryParams:
    if category not in CATEGORIES:
        raise BadRequestError(
            f"Invalid category '{category}'. Use one of: {', '.join(CATEGORIES)}."
        )
    if provider not in _VALID_PROVIDERS:
        raise BadRequestError(
            f"Invalid provider '{provider}'. Use: all, runpod, modal."
        )
    ...  # (keep the existing resolution check and resolve_range block)
    return BillingQueryParams(
        provider=provider,
        category=category,
        start=start_dt,
        end=end_dt,
        resolution=resolution,
        group_by=group_by,
        search=search,
    )
```

Add a `category: str = "inference"` query parameter to EACH of the six endpoints (`get_summary`, `get_timeseries`, `get_providers`, `get_breakdown`, `get_table`, `export_csv`) and pass `category=category` into their `_build_params(...)` call. Example for `get_summary`:

```python
@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    svc: BillingAnalyticsServiceDep,
    current_user: CurrentAdminDep,
    provider: str = "all",
    category: str = "inference",
    range: str | None = "last_30_days",
    start: str | None = None,
    end: str | None = None,
    resolution: str = "day",
):
    params = _build_params(provider, range, start, end, resolution, category=category)
    return await svc.summary(params)
```

Apply the same `category` parameter + `category=category` argument to the other five endpoints.

- [ ] **Step 4: Run the router tests + full billing suite**

Run: `python -m pytest app/tests/test_admin_billing.py -v`
Expected: PASS.
Run: `python -m pytest app/tests/ -q` → all pass except the 4 pre-existing `test_config.py` GA failures.

- [ ] **Step 5: Lint and commit**

Run black/isort/flake8 on the changed files (apply formatting if needed).

```bash
git add app/routers/admin_billing.py app/tests/test_admin_billing.py
git commit -m "feat(billing): category query param on all admin billing endpoints"
```

---

### Task 5: Frontend — category tabs, training labels, per-job table

**Files:**
- Modify: `frontend/src/hooks/useBillingAnalytics.ts`
- Modify: `frontend/src/pages/AdminBilling.tsx`

**Interfaces:**
- Consumes the `category` query param on the endpoints; the `/breakdown` endpoint with `group_by=object` for the per-job table.
- Produces: a tab switcher (Inference / Training / Cloud-disabled); `category` threaded into requests; a `useBillingBreakdown` hook; a per-job table on the Training tab.

- [ ] **Step 1: Add category + breakdown to the hooks**

In `frontend/src/hooks/useBillingAnalytics.ts`:

Add `category` to `BillingFilters`:

```typescript
export interface BillingFilters {
  category: 'inference' | 'training';
  provider: 'all' | 'runpod' | 'modal' | 'vastai';
  range: string;
  resolution: 'hour' | 'day' | 'week' | 'month' | 'year';
  groupBy?: string;
  search?: string;
}
```

Add `active_instances` to `SummaryData`:

```typescript
  active_instances: number;
```

Add a `BreakdownData` interface and hook, and include `category` in the shared `params`:

```typescript
export interface BreakdownRow {
  key: string;
  cost: number;
  runtime_ms: number;
  storage_gb: number;
  count: number;
}
export interface BreakdownData {
  group_by: string;
  rows: BreakdownRow[];
  warnings: string[];
}
```

In the `params()` helper, add `category: f.category` to the `URLSearchParams` object.

Add the breakdown hook:

```typescript
export const useBillingBreakdown = (f: BillingFilters, groupBy: string) =>
  useEndpoint<BreakdownData>('/breakdown', f, { group_by: groupBy });
```

- [ ] **Step 2: Add the tab switcher + category state to the page**

In `frontend/src/pages/AdminBilling.tsx`:

Initialize filters with a category and add tab state:

```tsx
  const [filters, setFilters] = useState<BillingFilters>({
    category: 'inference', provider: 'all', range: 'last_30_days', resolution: 'day',
  });
```

Add a tab switcher directly under the page header (before the Filters block):

```tsx
      {/* Category tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-white/10">
        {([
          ['inference', 'Inference (Runpod & Modal)', false],
          ['training', 'Training (Vast.ai)', false],
          ['cloud', 'Cloud (coming soon)', true],
        ] as const).map(([cat, label, disabled]) => (
          <button
            key={cat}
            disabled={disabled}
            onClick={() => {
              setFilters((f) => ({
                ...f,
                category: cat as BillingFilters['category'],
                provider: 'all',
              }));
              setPage(1);
            }}
            className={
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ' +
              (disabled
                ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed border-transparent'
                : filters.category === cat
                ? 'border-primary-600 text-primary-700 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200')
            }
          >
            {label}
          </button>
        ))}
      </div>
```

- [ ] **Step 3: Make the provider dropdown + labels category-aware**

In the Filters block, only show the provider dropdown for Inference (Training has a single provider):

```tsx
        {filters.category === 'inference' && (
          <select
            value={filters.provider}
            onChange={(e) => set({ provider: e.target.value as BillingFilters['provider'] })}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
          >
            <option value="all">All Platforms</option>
            <option value="runpod">Runpod</option>
            <option value="modal">Modal</option>
          </select>
        )}
```

Change the "Active endpoints / Modal apps" highlights and the third summary card to reflect the category. Replace the "Compute Time" card label to `GPU Hours` (it already shows hours) and make the Highlights list conditional:

```tsx
        <MetricCard label="GPU Hours" value={`${((summary?.total_runtime_ms || 0) / 3_600_000).toFixed(1)}h`} icon={Clock} color="bg-orange-500" />
```

In the Highlights `<ul>`, show training-specific rows when `filters.category === 'training'`:

```tsx
          {filters.category === 'training' ? (
            <li>Active jobs/instances: <b>{summary?.active_instances ?? 0}</b></li>
          ) : (
            <>
              <li>Active endpoints: <b>{summary?.active_endpoints ?? 0}</b></li>
              <li>Active Modal apps: <b>{summary?.active_modal_apps ?? 0}</b></li>
            </>
          )}
```

- [ ] **Step 4: Render a per-job table for Training**

Add the breakdown hook call near the other hooks:

```tsx
  const { data: jobs } = useBillingBreakdown(filters, 'object');
```

In the Table section, when `filters.category === 'training'`, render the jobs table instead of the raw records table. Replace the `<table>...</table>` body with a conditional:

```tsx
          {filters.category === 'training' ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-white/10 text-left text-gray-500 dark:text-gray-400">
                  <th className="py-2 px-3">Job / Instance</th>
                  <th className="py-2 px-3 text-right">GPU Hours</th>
                  <th className="py-2 px-3 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(jobs?.rows || []).map((row) => (
                  <tr key={row.key} className="border-b border-gray-100 dark:border-white/5">
                    <td className="py-2 px-3">{row.key}</td>
                    <td className="py-2 px-3 text-right">{(row.runtime_ms / 3_600_000).toFixed(1)}h</td>
                    <td className="py-2 px-3 text-right">${row.cost.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            /* existing inference records table unchanged */
            <table className="w-full text-sm">
              ...existing thead/tbody...
            </table>
          )}
```

Keep the existing inference `<table>` markup verbatim inside the `else` branch. Update the table heading text to be category-aware:

```tsx
            <Server size={18} /> {filters.category === 'training' ? 'Training Jobs' : 'Billing Records'}
```

Hide the search input and pagination controls when `filters.category === 'training'` (the jobs view is grouped, not paginated) by wrapping them in `{filters.category === 'inference' && ( ... )}`.

- [ ] **Step 5: Add a Vast.ai note to the explainer**

In the explainer `<details>` block, add a paragraph:

```tsx
          <p><b>Training (Vast.ai)</b> — Vast.ai bills per contract (a whole job), not per
            day. We spread each contract's cost and GPU-hours evenly across the days it ran so
            the charts and totals are smooth and correct; the Training Jobs table lists one row
            per contract (job/instance) with its total GPU-hours and cost. Storage is billed as
            cost (not GB), so it appears in spend rather than the storage figure.</p>
```

- [ ] **Step 6: Build**

Run: `cd frontend && npm run build`
Expected: `tsc` compiles (no type errors, no unused vars), Vite build succeeds. Fix any type/unused-import errors before committing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useBillingAnalytics.ts frontend/src/pages/AdminBilling.tsx app/static/react_build
git commit -m "feat(billing): category tabs + Vast.ai training view with per-job table"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/billing-analytics.md`

- [ ] **Step 1: Update the docs**

In `docs/billing-analytics.md`, under `## Configuration`, add:

```markdown
- `VAST_API_KEY` — Vast.ai charges API auth (training category).
- `VAST_BILLING_BASE_URL` — optional, defaults to `https://console.vast.ai`.
- `VAST_CONTRACT_TYPES` — optional, comma-separated (default `instance,volume`; empty = all).
```

Add a new section after `## Field meanings`:

```markdown
## Categories

The dashboard is split into categories, selected by the `category` query param
(default `inference`):

- **Inference** — Runpod + Modal (per-day billing).
- **Training** — Vast.ai. Vast.ai bills per contract (one total per job), so the provider
  amortizes each contract's cost and GPU-hours evenly across the days it ran into per-day
  records; the Training Jobs table groups those back into one row per contract. Vast.ai
  storage is billed as cost, not GB.
- **Cloud** (AWS/GCP/Heroku) — reserved for a later phase.
```

- [ ] **Step 2: Commit**

```bash
git add docs/billing-analytics.md
git commit -m "docs(billing): document training category and Vast.ai config"
```

---

## Self-Review Notes

- **Spec coverage:** category map + `category` param (Tasks 1, 3, 4) ✓; Vast.ai provider with pagination + item parse + amortization (Task 2) ✓; per-day records driving summary/timeseries + per-job table via `object` group key (Tasks 1, 5) ✓; `active_instances` training metric (Task 3) ✓; frontend tabs reusing the layout with training labels + Vast.ai explainer (Task 5) ✓; config/schema/caching (Tasks 1, 3) ✓; tests at each backend layer + frontend build (all tasks) ✓; docs (Task 6) ✓. Cloud infra explicitly deferred.
- **Type consistency:** `BillingQueryParams.category`, `_providers_for(category, provider)`, `providers_in_category`, `PROVIDER_CATEGORY`, `SUPPORTED_GROUP_BYS += "object"`, `SummaryResponse.active_instances`, and the frontend `BillingFilters.category` / `useBillingBreakdown` names are used identically across tasks.
- **Known MVP limitations (intentional, documented):** amortization spreads cost evenly across contract days; Vast.ai storage is cost-only (no GB); the Training table is grouped (not paginated/searchable); the `provider` dropdown is hidden on the Training tab (single provider).
