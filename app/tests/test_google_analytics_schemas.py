from app.schemas.google_analytics import (
    EventRow,
    GeoRow,
    PlatformRow,
    PlatformsBreakdown,
    PropertyInfo,
    PropertyOverviewResponse,
    TopPageRow,
    TrafficTimeSeries,
)


def test_property_info_round_trip():
    p = PropertyInfo(id="506611499", name="Sunflower")
    assert p.model_dump() == {"id": "506611499", "name": "Sunflower"}


def test_property_overview_accepts_empty_reports():
    resp = PropertyOverviewResponse(
        property_id="506611499",
        property_name="Sunflower",
        time_range="7d",
        cached_until="2026-04-19T15:00:00Z",
        traffic=TrafficTimeSeries(
            labels=[],
            active_users=[],
            new_users=[],
            sessions=[],
            engaged_sessions=[],
            engagement_rate=[],
            avg_session_duration=[],
            bounce_rate=[],
        ),
        top_pages=[],
        platforms=PlatformsBreakdown(device=[], os=[], browser=[]),
        geography=[],
        events=[],
        partial=False,
        failed_reports=[],
    )
    d = resp.model_dump()
    assert d["property_id"] == "506611499"
    assert d["partial"] is False


def test_partial_failure_lists_failed_reports():
    resp = PropertyOverviewResponse(
        property_id="506611499",
        property_name="Sunflower",
        time_range="7d",
        cached_until="2026-04-19T15:00:00Z",
        traffic=TrafficTimeSeries(
            labels=[],
            active_users=[],
            new_users=[],
            sessions=[],
            engaged_sessions=[],
            engagement_rate=[],
            avg_session_duration=[],
            bounce_rate=[],
        ),
        top_pages=[
            TopPageRow(path="/", title="Home", views=10, users=5, avg_duration=0.0)
        ],
        platforms=PlatformsBreakdown(
            device=[PlatformRow(label="desktop", users=5, sessions=5)],
            os=[],
            browser=[],
        ),
        geography=[GeoRow(country="Uganda", city="Kampala", users=5, sessions=5)],
        events=[EventRow(name="page_view", count=10, users=5)],
        partial=True,
        failed_reports=["events"],
    )
    assert resp.partial is True
    assert resp.failed_reports == ["events"]
