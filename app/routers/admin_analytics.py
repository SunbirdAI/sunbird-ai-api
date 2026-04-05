import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.crud.admin_monitoring import (
    get_unique_organization_types,
    get_unique_organizations,
    get_unique_sectors,
)
from app.deps import get_current_admin, get_db
from app.schemas.users import User
from app.utils.admin_monitoring_utils import (
    get_admin_org_stats,
    get_admin_org_type_stats,
    get_admin_overview_stats,
    get_admin_sector_stats,
)
from app.utils.monitoring_utils import parse_time_range

router = APIRouter()


def _validate_time_range(time_range: str):
    try:
        parse_time_range(time_range)
    except ValueError:
        raise BadRequestError(
            f"Invalid time_range '{time_range}'. "
            "Use values like 5m, 15m, 30m, 1h, 2h, 6h, 12h, 24h, 7d, 30d, 60d, 90d."
        )


@router.get("/filters")
async def get_filter_options(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return available filter values for admin analytics dropdowns."""
    organizations = await get_unique_organizations(db)
    organization_types = await get_unique_organization_types(db)
    sectors = await get_unique_sectors(db)

    return {
        "organizations": sorted(organizations),
        "organization_types": sorted(organization_types),
        "sectors": sorted(sectors),
    }


@router.get("/overview")
async def get_overview(
    time_range: str = "7d",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get overall usage analytics across all users."""
    _validate_time_range(time_range)
    stats = await get_admin_overview_stats(db, time_range)

    usage_data = [
        {"endpoint": ep, "used": count} for ep, count in stats["usage_counts"].items()
    ]

    return {
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "latency_distribution": stats["latency_distribution"],
    }


@router.get("/by-organization")
async def get_by_organization(
    organization: str,
    time_range: str = "7d",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get usage analytics filtered by organization, with per-user breakdown."""
    _validate_time_range(time_range)
    stats = await get_admin_org_stats(db, organization, time_range)

    usage_data = [
        {"endpoint": ep, "used": count} for ep, count in stats["usage_counts"].items()
    ]

    return {
        "organization": stats["organization"],
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "latency_distribution": stats["latency_distribution"],
        "per_user_breakdown": stats["per_user_breakdown"],
    }


@router.get("/by-organization-type")
async def get_by_organization_type(
    organization_type: str,
    time_range: str = "7d",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get usage analytics filtered by organization type."""
    _validate_time_range(time_range)
    stats = await get_admin_org_type_stats(db, organization_type, time_range)

    usage_data = [
        {"endpoint": ep, "used": count} for ep, count in stats["usage_counts"].items()
    ]

    return {
        "organization_type": stats["organization_type"],
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "latency_distribution": stats["latency_distribution"],
    }


@router.get("/by-sector")
async def get_by_sector(
    sector: str,
    time_range: str = "7d",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get usage analytics filtered by sector."""
    _validate_time_range(time_range)
    stats = await get_admin_sector_stats(db, sector, time_range)

    usage_data = [
        {"endpoint": ep, "used": count} for ep, count in stats["usage_counts"].items()
    ]

    return {
        "sector": stats["sector"],
        "usage": usage_data,
        "recent_activity": stats["recent_activity"],
        "chart_data": stats["chart_data"],
        "endpoint_chart_data": stats["endpoint_chart_data"],
        "latency_chart": stats["latency_chart"],
        "distribution_chart": stats["distribution_chart"],
        "latency_distribution": stats["latency_distribution"],
    }


@router.get("/export")
async def export_csv(
    view: str = "overview",
    time_range: str = "7d",
    organization: str = None,
    organization_type: str = None,
    sector: str = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export aggregated analytics data as CSV."""
    _validate_time_range(time_range)

    if view == "overview":
        stats = await get_admin_overview_stats(db, time_range)
    elif view == "organization":
        if not organization:
            raise BadRequestError("'organization' parameter is required for this view.")
        stats = await get_admin_org_stats(db, organization, time_range)
    elif view == "organization_type":
        if not organization_type:
            raise BadRequestError(
                "'organization_type' parameter is required for this view."
            )
        stats = await get_admin_org_type_stats(db, organization_type, time_range)
    elif view == "sector":
        if not sector:
            raise BadRequestError("'sector' parameter is required for this view.")
        stats = await get_admin_sector_stats(db, sector, time_range)
    else:
        raise BadRequestError(
            f"Invalid view '{view}'. "
            "Use: overview, organization, organization_type, sector."
        )

    output = io.StringIO()
    writer = csv.writer(output)

    # Endpoint summary section
    writer.writerow(["Endpoint Summary"])
    writer.writerow(["Endpoint", "Request Count"])
    for ep, count in stats["usage_counts"].items():
        writer.writerow([ep, count])
    writer.writerow([])

    # Latency distribution section
    writer.writerow(["Latency Distribution"])
    latency_dist = stats.get("latency_distribution", {})
    writer.writerow(["Bucket", "Count"])
    for label, val in zip(latency_dist.get("labels", []), latency_dist.get("data", [])):
        writer.writerow([label, val])
    writer.writerow([])

    # Time series section
    writer.writerow(["Time Series - Request Volume"])
    chart = stats.get("chart_data", {})
    writer.writerow(["Time Bucket", "Requests"])
    for label, val in zip(chart.get("labels", []), chart.get("data", [])):
        writer.writerow([label, val])
    writer.writerow([])

    # Time series - avg latency
    writer.writerow(["Time Series - Avg Latency (seconds)"])
    latency = stats.get("latency_chart", {})
    writer.writerow(["Time Bucket", "Avg Latency"])
    for label, val in zip(latency.get("labels", []), latency.get("data", [])):
        writer.writerow([label, f"{val:.4f}" if val else "0"])
    writer.writerow([])

    # Per-user breakdown (organization view only)
    if "per_user_breakdown" in stats:
        writer.writerow(["Per-User Breakdown"])
        writer.writerow(["Username", "Total Requests", "Endpoints"])
        for user in stats["per_user_breakdown"]:
            endpoints_str = "; ".join(
                f"{ep}: {cnt}" for ep, cnt in user["endpoints"].items()
            )
            writer.writerow([user["username"], user["total_requests"], endpoints_str])

    output.seek(0)
    filename = f"analytics_{view}_{time_range}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
