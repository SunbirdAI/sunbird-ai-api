from unittest.mock import AsyncMock, patch  # noqa: F401

import pytest

from app.tests.fixtures.ga.responses import (
    EVENTS_RESPONSE,
    GEO_RESPONSE,
    PLATFORM_RESPONSE,
    TOP_PAGES_RESPONSE,
    TRAFFIC_RESPONSE,
)


async def test_properties_requires_auth(async_client):
    resp = await async_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 401


async def test_properties_requires_admin(authenticated_client):
    resp = await authenticated_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code in (401, 403)


async def test_properties_returns_list_when_enabled(admin_client, monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    monkeypatch.setattr(
        "app.core.config.settings.ga_impersonation_target",
        "ga-reader@test.iam.gserviceaccount.com",
    )
    resp = await admin_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "properties": [
            {"id": "506611499", "name": "Sunflower"},
            {"id": "448469065", "name": "Sunbird Speech"},
        ]
    }


async def test_properties_returns_503_when_disabled(admin_client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ga_properties_raw", "")
    monkeypatch.setattr("app.core.config.settings.ga_impersonation_target", None)
    resp = await admin_client.get("/api/admin/google-analytics/properties")
    assert resp.status_code == 503


@pytest.fixture
def enable_ga(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    monkeypatch.setattr(
        "app.core.config.settings.ga_impersonation_target",
        "ga-reader@test.iam.gserviceaccount.com",
    )


def _to_proto(response_dict: dict):
    """Convert a fixture dict back into a mock that quacks like a RunReportResponse."""
    from unittest.mock import MagicMock

    proto = MagicMock()
    proto.dimension_headers = [MagicMock() for _ in response_dict["dimension_headers"]]
    for hdr, name in zip(proto.dimension_headers, response_dict["dimension_headers"]):
        hdr.name = name
    proto.metric_headers = [MagicMock() for _ in response_dict["metric_headers"]]
    for hdr, name in zip(proto.metric_headers, response_dict["metric_headers"]):
        hdr.name = name
    rows = []
    for row_data in response_dict["rows"]:
        row = MagicMock()
        row.dimension_values = [MagicMock() for _ in row_data["dimensions"]]
        for d, v in zip(row.dimension_values, row_data["dimensions"]):
            d.value = v
        row.metric_values = [MagicMock() for _ in row_data["metrics"]]
        for m, v in zip(row.metric_values, row_data["metrics"]):
            m.value = v
        rows.append(row)
    proto.rows = rows
    return proto


async def test_overview_returns_all_reports(admin_client, enable_ga):
    # BetaAnalyticsDataClient.run_report is sync (we wrap with asyncio.to_thread
    # in the integration layer), so use MagicMock, not AsyncMock.
    from unittest.mock import MagicMock

    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ), patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_cls:
        # Reset singletons so they pick up the mocked client
        import app.integrations.google_analytics as int_mod
        import app.services.cache as cache_mod
        import app.services.google_analytics_service as svc_mod

        svc_mod._instance = None
        int_mod._instance = None
        # Also reset the cache singleton so each test starts fresh
        cache_mod._instance = None

        ga_client = MagicMock()
        ga_client.run_report = MagicMock(
            side_effect=[
                _to_proto(TRAFFIC_RESPONSE),
                _to_proto(TOP_PAGES_RESPONSE),
                _to_proto(PLATFORM_RESPONSE),
                _to_proto(GEO_RESPONSE),
                _to_proto(EVENTS_RESPONSE),
            ]
        )
        mock_cls.return_value = ga_client

        resp = await admin_client.get(
            "/api/admin/google-analytics/overview",
            params={"property_id": "506611499", "time_range": "7d"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["property_id"] == "506611499"
    assert data["property_name"] == "Sunflower"
    assert data["partial"] is False
    assert data["traffic"]["labels"] == ["20260413", "20260414"]


async def test_overview_rejects_unknown_property(admin_client, enable_ga):
    resp = await admin_client.get(
        "/api/admin/google-analytics/overview",
        params={"property_id": "9999", "time_range": "7d"},
    )
    assert resp.status_code == 400


async def test_overview_rejects_invalid_time_range(admin_client, enable_ga):
    resp = await admin_client.get(
        "/api/admin/google-analytics/overview",
        params={"property_id": "506611499", "time_range": "1y"},
    )
    assert resp.status_code == 400


async def test_refresh_busts_cache_then_returns_fresh(admin_client, enable_ga):
    from unittest.mock import MagicMock

    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ), patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_cls:
        import app.integrations.google_analytics as int_mod
        import app.services.cache as cache_mod
        import app.services.google_analytics_service as svc_mod

        svc_mod._instance = None
        int_mod._instance = None
        cache_mod._instance = None

        ga_client = MagicMock()
        ga_client.run_report = MagicMock(
            side_effect=[
                _to_proto(TRAFFIC_RESPONSE),
                _to_proto(TOP_PAGES_RESPONSE),
                _to_proto(PLATFORM_RESPONSE),
                _to_proto(GEO_RESPONSE),
                _to_proto(EVENTS_RESPONSE),
            ]
        )
        mock_cls.return_value = ga_client

        resp = await admin_client.post(
            "/api/admin/google-analytics/refresh",
            params={"property_id": "506611499", "time_range": "7d"},
        )

    assert resp.status_code == 200
    assert resp.json()["property_id"] == "506611499"
