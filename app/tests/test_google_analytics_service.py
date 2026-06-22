import pytest

from app.core.exceptions import BadRequestError
from app.services.google_analytics_service import (
    REPORT_NAMES,
    GoogleAnalyticsService,
    _parse_time_range,
)


class TestParseTimeRange:
    @pytest.mark.parametrize(
        "tr,expected",
        [
            ("24h", ("yesterday", "today")),
            ("7d", ("7daysAgo", "today")),
            ("30d", ("30daysAgo", "today")),
            ("60d", ("60daysAgo", "today")),
            ("90d", ("90daysAgo", "today")),
        ],
    )
    def test_supported_values(self, tr, expected):
        assert _parse_time_range(tr) == expected

    def test_invalid_value_raises(self):
        with pytest.raises(BadRequestError, match="Invalid time_range"):
            _parse_time_range("1y")


class TestPropertyAllowlist:
    def test_validate_accepts_known_property(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower,448469065:Sunbird Speech",
        )
        svc = GoogleAnalyticsService(
            ga_client=None, cache=None  # type: ignore[arg-type]
        )
        svc._require_allowed_property("506611499")

    def test_validate_rejects_unknown_property(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        svc = GoogleAnalyticsService(
            ga_client=None, cache=None  # type: ignore[arg-type]
        )
        with pytest.raises(BadRequestError, match="not in allowlist"):
            svc._require_allowed_property("999999999")


def test_report_names_matches_aggregator_keys():
    assert set(REPORT_NAMES) == {
        "traffic",
        "pages",
        "platforms",
        "geography",
        "events",
    }


from unittest.mock import AsyncMock  # noqa: E402

from app.tests.fixtures.ga.responses import (  # noqa: E402
    EVENTS_RESPONSE,
    GEO_RESPONSE,
    PLATFORM_RESPONSE,
    TOP_PAGES_RESPONSE,
    TRAFFIC_RESPONSE,
)


def _service_with_mocks(monkeypatch, response):
    monkeypatch.setattr(
        "app.core.config.settings.ga_properties_raw",
        "506611499:Sunflower,448469065:Sunbird Speech",
    )
    ga = AsyncMock()
    ga.run_report.return_value = response

    async def miss(_key):
        return None

    cache = AsyncMock()
    cache.get = AsyncMock(side_effect=miss)
    cache.set = AsyncMock()

    return GoogleAnalyticsService(ga_client=ga, cache=cache), ga, cache


class TestTrafficReport:
    async def test_returns_aligned_series(self, monkeypatch):
        svc, ga, cache = _service_with_mocks(monkeypatch, TRAFFIC_RESPONSE)
        out = await svc.get_traffic_overview("506611499", "7d")
        assert out["labels"] == ["20260413", "20260414"]
        assert out["active_users"] == [100, 110]
        assert out["new_users"] == [30, 35]
        assert out["engagement_rate"] == pytest.approx([0.67, 0.65])
        ga.run_report.assert_awaited_once()
        cache.set.assert_awaited_once()

    async def test_uses_cache_on_hit(self, monkeypatch):
        svc, ga, cache = _service_with_mocks(monkeypatch, TRAFFIC_RESPONSE)
        cached = {
            "cached_at": "2026-04-19T14:00:00Z",
            "data": {
                "labels": ["cached"],
                "active_users": [1],
                "new_users": [0],
                "sessions": [1],
                "engaged_sessions": [1],
                "engagement_rate": [1.0],
                "avg_session_duration": [0.0],
                "bounce_rate": [0.0],
            },
        }
        cache.get = AsyncMock(return_value=cached)
        out = await svc.get_traffic_overview("506611499", "7d")
        assert out["labels"] == ["cached"]
        ga.run_report.assert_not_awaited()


class TestTopPages:
    async def test_shapes_rows(self, monkeypatch):
        svc, ga, _ = _service_with_mocks(monkeypatch, TOP_PAGES_RESPONSE)
        out = await svc.get_top_pages("506611499", "7d", limit=10)
        assert out == [
            {
                "path": "/dashboard",
                "title": "Dashboard",
                "views": 200,
                "users": 150,
                "avg_duration": 120.5,
            },
            {
                "path": "/login",
                "title": "Login",
                "views": 180,
                "users": 170,
                "avg_duration": 45.2,
            },
        ]


class TestPlatformBreakdown:
    async def test_groups_by_dimension(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, PLATFORM_RESPONSE)
        out = await svc.get_platform_breakdown("506611499", "7d")
        device_map = {r["label"]: r["users"] for r in out["device"]}
        assert device_map == {"desktop": 500, "mobile": 400}
        os_map = {r["label"]: r["users"] for r in out["os"]}
        assert os_map == {"Windows": 500, "Android": 300, "iOS": 100}
        browser_map = {r["label"]: r["users"] for r in out["browser"]}
        assert browser_map == {"Chrome": 800, "Safari": 100}


class TestGeoBreakdown:
    async def test_returns_country_city_rows(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, GEO_RESPONSE)
        out = await svc.get_geo_breakdown("506611499", "7d", limit=20)
        assert out == [
            {
                "country": "Uganda",
                "city": "Kampala",
                "users": 800,
                "sessions": 900,
            },
            {
                "country": "Kenya",
                "city": "Nairobi",
                "users": 100,
                "sessions": 120,
            },
        ]


class TestTopEvents:
    async def test_shapes_rows(self, monkeypatch):
        svc, _, _ = _service_with_mocks(monkeypatch, EVENTS_RESPONSE)
        out = await svc.get_top_events("506611499", "7d", limit=15)
        assert out == [
            {"name": "page_view", "count": 1200, "users": 400},
            {"name": "session_start", "count": 450, "users": 400},
        ]


class TestAggregator:
    async def test_overview_returns_all_reports(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        responses = [
            TRAFFIC_RESPONSE,
            TOP_PAGES_RESPONSE,
            PLATFORM_RESPONSE,
            GEO_RESPONSE,
            EVENTS_RESPONSE,
        ]
        ga.run_report = AsyncMock(side_effect=responses)

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        out = await svc.get_property_overview("506611499", "7d")

        assert out["property_id"] == "506611499"
        assert out["property_name"] == "Sunflower"
        assert out["time_range"] == "7d"
        assert out["partial"] is False
        assert out["failed_reports"] == []
        assert out["traffic"]["labels"] == ["20260413", "20260414"]
        assert len(out["top_pages"]) == 2

    async def test_overview_tolerates_partial_failure(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        ga.run_report = AsyncMock(
            side_effect=[
                TRAFFIC_RESPONSE,
                TOP_PAGES_RESPONSE,
                PLATFORM_RESPONSE,
                GEO_RESPONSE,
                RuntimeError("quota"),
            ]
        )

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        out = await svc.get_property_overview("506611499", "7d")

        assert out["partial"] is True
        assert out["failed_reports"] == ["events"]
        assert out["events"] == []
        assert out["traffic"]["labels"] == ["20260413", "20260414"]

    async def test_force_refresh_deletes_cache_then_refetches(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.settings.ga_properties_raw",
            "506611499:Sunflower",
        )
        ga = AsyncMock()
        ga.run_report = AsyncMock(
            side_effect=[
                TRAFFIC_RESPONSE,
                TOP_PAGES_RESPONSE,
                PLATFORM_RESPONSE,
                GEO_RESPONSE,
                EVENTS_RESPONSE,
            ]
        )

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        cache.delete = AsyncMock()

        svc = GoogleAnalyticsService(ga_client=ga, cache=cache)
        await svc.get_property_overview("506611499", "7d", force_refresh=True)

        deleted_keys = {c.args[0] for c in cache.delete.await_args_list}
        assert deleted_keys == {
            "ga:506611499:traffic:7d",
            "ga:506611499:pages:7d",
            "ga:506611499:platforms:7d",
            "ga:506611499:geography:7d",
            "ga:506611499:events:7d",
        }
