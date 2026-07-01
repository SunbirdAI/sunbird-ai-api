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
            key,
            {"key": key, "cost": 0.0, "runtime_ms": 0, "storage_gb": 0.0, "count": 0},
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

    # Runpod "endpoints" exclude account-level network volume storage records.
    runpod_endpoint_records = [
        r
        for r in records
        if r.provider == "runpod" and r.metadata.get("kind") != "network_volume"
    ]
    endpoints = {r.object_id for r in runpod_endpoint_records}
    apps = {r.object_id for r in records if r.provider == "modal"}

    endpoint_rows = group_records(runpod_endpoint_records, "endpoint")
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
        # storage_gb is GB-hours (capacity x hours billed); dividing by the period's
        # hours gives the time-weighted average provisioned storage in GB.
        "avg_storage_gb": round(total_storage / (days * 24), 4),
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
    return {
        "labels": labels,
        "cost": cost,
        "runtime_ms": runtime,
        "storage_gb": storage,
    }


_SORT_KEYS = {
    "cost": lambda r: r.cost,
    "timestamp": lambda r: r.timestamp,
    "runtime": lambda r: r.runtime_ms or 0,
}


def paginate_sort_search(
    records: list[BillingRecord],
    page: int,
    page_size: int,
    sort: Optional[str],
    search: Optional[str],
    descending: bool = True,
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
    key_func = _SORT_KEYS.get(sort)
    if key_func is not None:
        rows = sorted(rows, key=key_func, reverse=descending)
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total  # noqa: E203
