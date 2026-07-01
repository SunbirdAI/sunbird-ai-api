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
