"""Tests for dashboard usage stats endpoint and monitoring utilities."""

from datetime import datetime, timedelta

import pytest

from app.models.monitoring import EndpointLog
from app.utils.monitoring_utils import (
    VALID_TIME_RANGES,
    _bucket_format,
    _generate_labels,
    get_dashboard_stats,
    parse_time_range,
)

# ---------------------------------------------------------------------------
# Unit tests for parse_time_range
# ---------------------------------------------------------------------------


class TestParseTimeRange:
    def test_valid_predefined_ranges(self):
        for key, expected_td in VALID_TIME_RANGES.items():
            assert parse_time_range(key) == expected_td

    def test_backward_compat_bare_days(self):
        assert parse_time_range("14d") == timedelta(days=14)

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError, match="Invalid time_range"):
            parse_time_range("abc")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid time_range"):
            parse_time_range("10x")


# ---------------------------------------------------------------------------
# Unit tests for _bucket_format
# ---------------------------------------------------------------------------


class TestBucketFormat:
    def test_minute_bucket_for_short_ranges(self):
        assert _bucket_format(timedelta(minutes=5)) == "%H:%M"
        assert _bucket_format(timedelta(minutes=30)) == "%H:%M"
        assert _bucket_format(timedelta(hours=1)) == "%H:%M"

    def test_hour_bucket_for_medium_ranges(self):
        assert _bucket_format(timedelta(hours=2)) == "%b %d %H:00"
        assert _bucket_format(timedelta(hours=12)) == "%b %d %H:00"
        assert _bucket_format(timedelta(hours=24)) == "%b %d %H:00"

    def test_day_bucket_for_long_ranges(self):
        assert _bucket_format(timedelta(days=7)) == "%Y-%m-%d"
        assert _bucket_format(timedelta(days=30)) == "%Y-%m-%d"
        assert _bucket_format(timedelta(days=90)) == "%Y-%m-%d"


# ---------------------------------------------------------------------------
# Unit tests for _generate_labels
# ---------------------------------------------------------------------------


class TestGenerateLabels:
    def test_minute_labels_count(self):
        start = datetime.now() - timedelta(minutes=5)
        labels = _generate_labels(start, timedelta(minutes=5))
        # Should have ~6 labels (0..5 minutes)
        assert len(labels) >= 5
        assert len(labels) <= 7

    def test_hour_labels_count(self):
        start = datetime.now() - timedelta(hours=6)
        labels = _generate_labels(start, timedelta(hours=6))
        # Should have ~7 labels (0..6 hours)
        assert len(labels) >= 6
        assert len(labels) <= 8

    def test_day_labels_count(self):
        start = datetime.now() - timedelta(days=7)
        labels = _generate_labels(start, timedelta(days=7))
        # Should have 7-8 labels
        assert len(labels) >= 7
        assert len(labels) <= 8

    def test_labels_are_unique(self):
        start = datetime.now() - timedelta(days=30)
        labels = _generate_labels(start, timedelta(days=30))
        assert len(labels) == len(set(labels))


# ---------------------------------------------------------------------------
# Integration tests for get_dashboard_stats
# ---------------------------------------------------------------------------


class TestGetDashboardStats:
    async def test_empty_stats(self, db_session, test_db):
        stats = await get_dashboard_stats(db_session, "nonexistent_user", "7d")
        assert stats["usage_counts"] == {}
        assert stats["recent_activity"] == []
        assert stats["chart_data"]["data"] == [0] * len(stats["chart_data"]["labels"])

    async def test_stats_with_logs(self, db_session, test_db):
        # Insert some test logs
        now = datetime.now()
        for i in range(3):
            log = EndpointLog(
                username="test_user",
                endpoint="/tasks/stt",
                time_taken=0.5,
                organization="Test Org",
                date=now - timedelta(hours=i),
            )
            db_session.add(log)

        log2 = EndpointLog(
            username="test_user",
            endpoint="/tasks/translate",
            time_taken=0.2,
            organization="Test Org",
            date=now - timedelta(hours=1),
        )
        db_session.add(log2)
        await db_session.commit()

        stats = await get_dashboard_stats(db_session, "test_user", "7d")

        # Usage counts should reflect all logs
        assert stats["usage_counts"]["/tasks/stt"] == 3
        assert stats["usage_counts"]["/tasks/translate"] == 1

        # Chart data should have non-zero values
        total_volume = sum(stats["chart_data"]["data"])
        assert total_volume == 4

        # distribution_chart should list both endpoints
        assert "/tasks/stt" in stats["distribution_chart"]["labels"]
        assert "/tasks/translate" in stats["distribution_chart"]["labels"]

        # endpoint_chart_data should have datasets for both endpoints
        assert "/tasks/stt" in stats["endpoint_chart_data"]["datasets"]
        assert "/tasks/translate" in stats["endpoint_chart_data"]["datasets"]

    async def test_stats_minute_range(self, db_session, test_db):
        now = datetime.now()
        log = EndpointLog(
            username="test_user",
            endpoint="/tasks/stt",
            time_taken=0.3,
            organization="Test Org",
            date=now - timedelta(minutes=2),
        )
        db_session.add(log)
        await db_session.commit()

        stats = await get_dashboard_stats(db_session, "test_user", "5m")

        # The log should appear in the volume data
        total_volume = sum(stats["chart_data"]["data"])
        assert total_volume == 1

    async def test_stats_hour_range(self, db_session, test_db):
        now = datetime.now()
        log = EndpointLog(
            username="test_user",
            endpoint="/tasks/translate",
            time_taken=0.1,
            organization="Test Org",
            date=now - timedelta(hours=1),
        )
        db_session.add(log)
        await db_session.commit()

        stats = await get_dashboard_stats(db_session, "test_user", "6h")

        total_volume = sum(stats["chart_data"]["data"])
        assert total_volume == 1

    async def test_stats_30d_range(self, db_session, test_db):
        """Regression: 30d range previously showed all zeros due to key mismatch."""
        now = datetime.now()
        log = EndpointLog(
            username="test_user",
            endpoint="/tasks/stt",
            time_taken=0.5,
            organization="Test Org",
            date=now - timedelta(days=5),
        )
        db_session.add(log)
        await db_session.commit()

        stats = await get_dashboard_stats(db_session, "test_user", "30d")

        total_volume = sum(stats["chart_data"]["data"])
        assert total_volume == 1

    async def test_latency_distribution(self, db_session, test_db):
        now = datetime.now()
        # One fast, one slow
        db_session.add(
            EndpointLog(
                username="test_user",
                endpoint="/tasks/stt",
                time_taken=0.05,  # 50ms
                organization="Test Org",
                date=now,
            )
        )
        db_session.add(
            EndpointLog(
                username="test_user",
                endpoint="/tasks/stt",
                time_taken=3.0,  # 3000ms
                organization="Test Org",
                date=now,
            )
        )
        await db_session.commit()

        stats = await get_dashboard_stats(db_session, "test_user", "7d")
        dist = stats["latency_distribution"]
        assert "<100ms" in dist["labels"]
        assert ">2s" in dist["labels"]
        # Should have values in two buckets
        assert sum(dist["data"]) == 2


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:
    async def test_usage_endpoint_requires_auth(self, async_client, test_db):
        response = await async_client.get("/api/dashboard/usage")
        assert response.status_code == 401

    async def test_usage_endpoint_default_range(self, authenticated_client, test_db):
        response = await authenticated_client.get("/api/dashboard/usage")
        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert "chart_data" in data
        assert "endpoint_chart_data" in data
        assert "latency_chart" in data
        assert "distribution_chart" in data
        assert "latency_distribution" in data
        assert "account_type" in data

    async def test_usage_endpoint_minute_range(self, authenticated_client, test_db):
        response = await authenticated_client.get("/api/dashboard/usage?time_range=5m")
        assert response.status_code == 200

    async def test_usage_endpoint_hour_range(self, authenticated_client, test_db):
        response = await authenticated_client.get("/api/dashboard/usage?time_range=6h")
        assert response.status_code == 200

    async def test_usage_endpoint_invalid_range(self, authenticated_client, test_db):
        response = await authenticated_client.get(
            "/api/dashboard/usage?time_range=invalid"
        )
        assert response.status_code == 400

    async def test_usage_endpoint_all_valid_ranges(self, authenticated_client, test_db):
        for time_range in VALID_TIME_RANGES.keys():
            response = await authenticated_client.get(
                f"/api/dashboard/usage?time_range={time_range}"
            )
            assert response.status_code == 200, f"Failed for time_range={time_range}"
