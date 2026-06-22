"""Pydantic response schemas for the Google Analytics admin endpoints."""

from pydantic import BaseModel, Field


class PropertyInfo(BaseModel):
    id: str
    name: str


class TrafficTimeSeries(BaseModel):
    """All lists are aligned to `labels` (one entry per date)."""

    labels: list[str]
    active_users: list[int]
    new_users: list[int]
    sessions: list[int]
    engaged_sessions: list[int]
    engagement_rate: list[float]
    avg_session_duration: list[float]
    bounce_rate: list[float]


class TopPageRow(BaseModel):
    path: str
    title: str
    views: int
    users: int
    avg_duration: float


class PlatformRow(BaseModel):
    label: str
    users: int
    sessions: int


class PlatformsBreakdown(BaseModel):
    device: list[PlatformRow]
    os: list[PlatformRow]
    browser: list[PlatformRow]


class GeoRow(BaseModel):
    country: str
    city: str
    users: int
    sessions: int


class EventRow(BaseModel):
    name: str
    count: int
    users: int


class PropertyOverviewResponse(BaseModel):
    property_id: str
    property_name: str
    time_range: str
    cached_until: str = Field(
        description="ISO-8601 timestamp when the oldest cached report expires."
    )
    traffic: TrafficTimeSeries
    top_pages: list[TopPageRow]
    platforms: PlatformsBreakdown
    geography: list[GeoRow]
    events: list[EventRow]
    partial: bool = False
    failed_reports: list[str] = Field(default_factory=list)


class PropertiesListResponse(BaseModel):
    properties: list[PropertyInfo]
