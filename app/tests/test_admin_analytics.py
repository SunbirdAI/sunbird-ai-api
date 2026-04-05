"""Tests for admin analytics endpoints and utilities."""

from datetime import datetime, timedelta

import pytest

from app.models.monitoring import EndpointLog
from app.utils.admin_monitoring_utils import (
    _build_chart_data,
    get_admin_org_stats,
    get_admin_org_type_stats,
    get_admin_overview_stats,
    get_admin_sector_stats,
)

# ---------------------------------------------------------------------------
# Helper: create an admin-authenticated client
# ---------------------------------------------------------------------------


@pytest.fixture
async def admin_client(async_client, admin_user):
    async_client.headers["Authorization"] = f"Bearer {admin_user['token']}"
    return async_client


# ---------------------------------------------------------------------------
# Helper: seed log data for multiple users/orgs
# ---------------------------------------------------------------------------


async def _seed_logs(db_session):
    """Insert diverse endpoint logs for testing admin analytics."""
    now = datetime.now()
    logs = [
        EndpointLog(
            username="alice",
            endpoint="/tasks/stt",
            time_taken=0.3,
            organization="Org A",
            organization_type="NGO",
            sector=["Health", "Education"],
            date=now - timedelta(hours=1),
        ),
        EndpointLog(
            username="alice",
            endpoint="/tasks/translate",
            time_taken=0.1,
            organization="Org A",
            organization_type="NGO",
            sector=["Health", "Education"],
            date=now - timedelta(hours=2),
        ),
        EndpointLog(
            username="bob",
            endpoint="/tasks/stt",
            time_taken=0.5,
            organization="Org A",
            organization_type="NGO",
            sector=["Health"],
            date=now - timedelta(hours=3),
        ),
        EndpointLog(
            username="charlie",
            endpoint="/tasks/translate",
            time_taken=0.2,
            organization="Org B",
            organization_type="Government",
            sector=["Agriculture"],
            date=now - timedelta(days=2),
        ),
        EndpointLog(
            username="charlie",
            endpoint="/tasks/stt",
            time_taken=2.5,
            organization="Org B",
            organization_type="Government",
            sector=["Agriculture"],
            date=now - timedelta(days=3),
        ),
    ]
    for log in logs:
        db_session.add(log)
    await db_session.commit()


# ---------------------------------------------------------------------------
# Unit tests: _build_chart_data
# ---------------------------------------------------------------------------


class TestBuildChartData:
    def test_empty_logs(self):
        start = datetime.now() - timedelta(days=7)
        result = _build_chart_data([], "%Y-%m-%d", start, timedelta(days=7))
        assert all(v == 0 for v in result["chart_data"]["data"])
        assert result["latency_distribution"]["data"] == [0, 0, 0, 0, 0]

    def test_single_log(self):
        now = datetime.now()
        log = EndpointLog(
            username="u",
            endpoint="/tasks/stt",
            time_taken=0.05,
            organization="O",
            date=now,
        )
        start = now - timedelta(days=7)
        result = _build_chart_data([log], "%Y-%m-%d", start, timedelta(days=7))
        total_volume = sum(result["chart_data"]["data"])
        assert total_volume == 1
        assert "/tasks/stt" in result["endpoint_chart_data"]["datasets"]

    def test_latency_distribution_buckets(self):
        now = datetime.now()
        logs = [
            EndpointLog(
                username="u", endpoint="/e", time_taken=0.05, organization="O", date=now
            ),  # <100ms
            EndpointLog(
                username="u", endpoint="/e", time_taken=0.3, organization="O", date=now
            ),  # 100-500ms
            EndpointLog(
                username="u", endpoint="/e", time_taken=0.7, organization="O", date=now
            ),  # 500ms-1s
            EndpointLog(
                username="u", endpoint="/e", time_taken=1.5, organization="O", date=now
            ),  # 1s-2s
            EndpointLog(
                username="u", endpoint="/e", time_taken=3.0, organization="O", date=now
            ),  # >2s
        ]
        start = now - timedelta(days=1)
        result = _build_chart_data(logs, "%Y-%m-%d", start, timedelta(days=1))
        dist = result["latency_distribution"]
        assert dist["data"] == [1, 1, 1, 1, 1]


# ---------------------------------------------------------------------------
# Integration tests: admin aggregation utils
# ---------------------------------------------------------------------------


class TestAdminOverviewStats:
    async def test_empty_overview(self, db_session, test_db):
        stats = await get_admin_overview_stats(db_session, "7d")
        assert stats["usage_counts"] == {}
        assert stats["recent_activity"] == []

    async def test_overview_with_data(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_overview_stats(db_session, "7d")
        assert stats["usage_counts"]["/tasks/stt"] == 3
        assert stats["usage_counts"]["/tasks/translate"] == 2
        total_volume = sum(stats["chart_data"]["data"])
        assert total_volume == 5


class TestAdminOrgStats:
    async def test_filter_by_organization(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_org_stats(db_session, "Org A", "7d")
        assert stats["organization"] == "Org A"
        # Org A has 3 logs
        total = sum(count for count in stats["usage_counts"].values())
        assert total == 3
        # Per-user breakdown
        usernames = [u["username"] for u in stats["per_user_breakdown"]]
        assert "alice" in usernames
        assert "bob" in usernames
        assert "charlie" not in usernames

    async def test_per_user_breakdown_sorted(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_org_stats(db_session, "Org A", "7d")
        # alice has 2 requests, bob has 1 — alice should come first
        assert stats["per_user_breakdown"][0]["username"] == "alice"
        assert stats["per_user_breakdown"][0]["total_requests"] == 2


class TestAdminOrgTypeStats:
    async def test_filter_by_org_type(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_org_type_stats(db_session, "Government", "7d")
        assert stats["organization_type"] == "Government"
        total = sum(count for count in stats["usage_counts"].values())
        assert total == 2


class TestAdminSectorStats:
    async def test_filter_by_sector(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_sector_stats(db_session, "Health", "7d")
        assert stats["sector"] == "Health"
        # alice has 2 logs with Health, bob has 1
        total = sum(count for count in stats["usage_counts"].values())
        assert total == 3

    async def test_sector_not_found(self, db_session, test_db):
        await _seed_logs(db_session)
        stats = await get_admin_sector_stats(db_session, "NonexistentSector", "7d")
        assert stats["usage_counts"] == {}


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestAdminEndpointAuth:
    async def test_overview_requires_admin(self, authenticated_client, test_db):
        """Non-admin user should get 403."""
        response = await authenticated_client.get("/api/admin/analytics/overview")
        assert response.status_code == 403

    async def test_overview_unauthenticated(self, async_client, test_db):
        response = await async_client.get("/api/admin/analytics/overview")
        assert response.status_code == 401

    async def test_filters_requires_admin(self, authenticated_client, test_db):
        response = await authenticated_client.get("/api/admin/analytics/filters")
        assert response.status_code == 403

    async def test_export_requires_admin(self, authenticated_client, test_db):
        response = await authenticated_client.get("/api/admin/analytics/export")
        assert response.status_code == 403


class TestAdminOverviewEndpoint:
    async def test_overview_success(self, admin_client, test_db):
        response = await admin_client.get("/api/admin/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert "chart_data" in data
        assert "endpoint_chart_data" in data
        assert "latency_chart" in data
        assert "latency_distribution" in data

    async def test_overview_invalid_time_range(self, admin_client, test_db):
        response = await admin_client.get(
            "/api/admin/analytics/overview?time_range=invalid"
        )
        assert response.status_code == 400

    async def test_overview_all_valid_ranges(self, admin_client, test_db):
        for tr in ["5m", "1h", "7d", "30d"]:
            response = await admin_client.get(
                f"/api/admin/analytics/overview?time_range={tr}"
            )
            assert response.status_code == 200, f"Failed for time_range={tr}"


class TestAdminByOrganizationEndpoint:
    async def test_by_org_success(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get(
            "/api/admin/analytics/by-organization?organization=Org A"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["organization"] == "Org A"
        assert "per_user_breakdown" in data

    async def test_by_org_missing_param(self, admin_client, test_db):
        """organization query param is required by FastAPI — returns 422."""
        response = await admin_client.get("/api/admin/analytics/by-organization")
        assert response.status_code == 422


class TestAdminByOrgTypeEndpoint:
    async def test_by_org_type_success(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get(
            "/api/admin/analytics/by-organization-type?organization_type=NGO"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["organization_type"] == "NGO"


class TestAdminBySectorEndpoint:
    async def test_by_sector_success(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get(
            "/api/admin/analytics/by-sector?sector=Health"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sector"] == "Health"


class TestAdminFiltersEndpoint:
    async def test_filters_success(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get("/api/admin/analytics/filters")
        assert response.status_code == 200
        data = response.json()
        assert "Org A" in data["organizations"]
        assert "Org B" in data["organizations"]
        assert "NGO" in data["organization_types"]
        assert "Government" in data["organization_types"]
        assert "Health" in data["sectors"]
        assert "Agriculture" in data["sectors"]

    async def test_filters_empty_db(self, admin_client, test_db):
        response = await admin_client.get("/api/admin/analytics/filters")
        assert response.status_code == 200
        data = response.json()
        assert data["organizations"] == []
        assert data["organization_types"] == []
        assert data["sectors"] == []


class TestAdminExportEndpoint:
    async def test_export_overview_csv(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get(
            "/api/admin/analytics/export?view=overview&time_range=7d"
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        content = response.text
        assert "Endpoint Summary" in content
        assert "/tasks/stt" in content

    async def test_export_org_csv(self, admin_client, test_db, db_session):
        await _seed_logs(db_session)
        response = await admin_client.get(
            "/api/admin/analytics/export?view=organization&organization=Org A&time_range=7d"
        )
        assert response.status_code == 200
        content = response.text
        assert "Per-User Breakdown" in content
        assert "alice" in content

    async def test_export_org_missing_param(self, admin_client, test_db):
        response = await admin_client.get(
            "/api/admin/analytics/export?view=organization&time_range=7d"
        )
        assert response.status_code == 400

    async def test_export_invalid_view(self, admin_client, test_db):
        response = await admin_client.get(
            "/api/admin/analytics/export?view=invalid&time_range=7d"
        )
        assert response.status_code == 400
