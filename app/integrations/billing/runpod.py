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
        # Runpod billing API has no tag filter; ProviderQuery.tag_names is ignored here.
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

    def _normalize(self, rows: list[dict]) -> list[BillingRecord]:
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
            if resp.status_code >= 400:
                raise ProviderUnavailable(
                    "runpod", f"billing API returned {resp.status_code}"
                )
        except ProviderUnavailable:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "runpod", f"billing API request failed: {exc}"
            ) from exc
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("billingData", [])
        return self._normalize(rows)
