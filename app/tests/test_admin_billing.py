from unittest.mock import AsyncMock, patch

from app.schemas.billing_analytics import (
    BillingRecord,
    SummaryResponse,
    TableResponse,
    TimeseriesResponse,
)

BASE = "/api/admin/analytics/billing"


def _summary():
    return SummaryResponse(
        total_spend=14.0,
        avg_daily_spend=7.0,
        total_runtime_ms=1000,
        avg_daily_runtime_ms=500.0,
        total_storage_gb=5.0,
        active_endpoints=1,
        active_modal_apps=1,
        num_days=2,
        warnings=[],
    )


class TestAuth:
    async def test_summary_requires_admin(self, authenticated_client, test_db):
        resp = await authenticated_client.get(f"{BASE}/summary")
        assert resp.status_code == 403

    async def test_summary_unauthenticated(self, async_client, test_db):
        resp = await async_client.get(f"{BASE}/summary")
        assert resp.status_code == 401


class TestEndpoints:
    async def test_summary_ok(self, admin_client, test_db):
        with patch(
            "app.routers.admin_billing.get_billing_analytics_service"
        ) as factory:
            svc = factory.return_value
            svc.summary = AsyncMock(return_value=_summary())
            resp = await admin_client.get(f"{BASE}/summary?range=last_7_days")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_spend"] == 14.0
        assert body["active_modal_apps"] == 1

    async def test_timeseries_ok(self, admin_client, test_db):
        ts = TimeseriesResponse(
            labels=["2026-05-01"],
            cost=[14.0],
            runtime_ms=[1000.0],
            storage_gb=[5.0],
        )
        with patch(
            "app.routers.admin_billing.get_billing_analytics_service"
        ) as factory:
            factory.return_value.timeseries = AsyncMock(return_value=ts)
            resp = await admin_client.get(
                f"{BASE}/timeseries?range=last_7_days&resolution=day"
            )
        assert resp.status_code == 200
        assert resp.json()["cost"] == [14.0]

    async def test_breakdown_rejects_bad_group_by(self, admin_client, test_db):
        resp = await admin_client.get(
            f"{BASE}/breakdown?range=last_7_days&group_by=banana"
        )
        assert resp.status_code == 400

    async def test_table_ok(self, admin_client, test_db):
        table = TableResponse(
            rows=[
                BillingRecord(
                    provider="runpod",
                    object_id="ep1",
                    object_name="ep1",
                    timestamp="2026-05-01T00:00:00",
                    cost=10.0,
                )
            ],
            total=1,
            page=1,
            page_size=50,
        )
        with patch(
            "app.routers.admin_billing.get_billing_analytics_service"
        ) as factory:
            factory.return_value.table = AsyncMock(return_value=table)
            resp = await admin_client.get(f"{BASE}/table?range=last_7_days")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_export_csv(self, admin_client, test_db):
        with patch(
            "app.routers.admin_billing.get_billing_analytics_service"
        ) as factory:
            factory.return_value.records_for_export = AsyncMock(
                return_value=[
                    BillingRecord(
                        provider="runpod",
                        object_id="ep1",
                        object_name="ep1",
                        timestamp="2026-05-01T00:00:00",
                        cost=10.0,
                        runtime_ms=1000,
                        storage_gb=5.0,
                    )
                ]
            )
            resp = await admin_client.get(f"{BASE}/export?range=last_7_days")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "ep1" in resp.text

    async def test_ai_endpoint_not_implemented(self, admin_client, test_db):
        resp = await admin_client.post(f"{BASE}/ai", json={"question": "hi"})
        assert resp.status_code == 501
