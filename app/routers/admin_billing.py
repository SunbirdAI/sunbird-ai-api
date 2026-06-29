"""Admin billing analytics endpoints (Runpod + Modal). Admin-only."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse, StreamingResponse

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
            f"Invalid resolution '{resolution}'. " "Use: hour, day, week, month, year."
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
        [
            "Provider",
            "Object",
            "Timestamp",
            "Cost (USD)",
            "Runtime (ms)",
            "Storage (GB)",
            "GPU",
            "Environment",
            "Tags",
        ]
    )
    for r in records:
        tags = "; ".join(f"{k}={v}" for k, v in r.tags.items())
        writer.writerow(
            [
                r.provider,
                r.object_name,
                r.timestamp.isoformat(),
                f"{r.cost:.6f}",
                r.runtime_ms or "",
                r.storage_gb or "",
                r.gpu or "",
                r.environment or "",
                tags,
            ]
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
