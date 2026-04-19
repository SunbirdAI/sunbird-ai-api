"""Admin routes for surfacing Google Analytics data."""

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.deps import CurrentAdminDep, GoogleAnalyticsServiceDep
from app.schemas.google_analytics import (
    PropertiesListResponse,
    PropertyInfo,
    PropertyOverviewResponse,
)

router = APIRouter()


def _require_enabled():
    if not settings.ga_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Analytics is not configured.",
        )


@router.get("/properties", response_model=PropertiesListResponse)
async def list_properties(_: CurrentAdminDep):
    _require_enabled()
    return PropertiesListResponse(
        properties=[
            PropertyInfo(id=pid, name=name)
            for pid, name in settings.ga_properties.items()
        ]
    )


@router.get("/overview", response_model=PropertyOverviewResponse)
async def get_overview(
    property_id: str,
    ga_service: GoogleAnalyticsServiceDep,
    _: CurrentAdminDep,
    time_range: str = "7d",
):
    _require_enabled()
    data = await ga_service.get_property_overview(property_id, time_range)
    return PropertyOverviewResponse(**data)


@router.post("/refresh", response_model=PropertyOverviewResponse)
async def refresh_overview(
    property_id: str,
    ga_service: GoogleAnalyticsServiceDep,
    _: CurrentAdminDep,
    time_range: str = "7d",
):
    _require_enabled()
    data = await ga_service.get_property_overview(
        property_id, time_range, force_refresh=True
    )
    return PropertyOverviewResponse(**data)
