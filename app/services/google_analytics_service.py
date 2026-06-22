"""Google Analytics orchestration service.

Responsibilities:
- Map admin-facing time ranges to GA date range values
- Run and cache individual reports (traffic, pages, platforms, geo, events)
- Aggregate reports, shape results for the frontend, tolerate partial failures
"""

from __future__ import annotations

from typing import Tuple

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.integrations.google_analytics import GoogleAnalyticsClient
from app.services.cache import CacheBackend

REPORT_NAMES: Tuple[str, ...] = (
    "traffic",
    "pages",
    "platforms",
    "geography",
    "events",
)

_TIME_RANGE_MAP: dict[str, tuple[str, str]] = {
    "24h": ("yesterday", "today"),
    "7d": ("7daysAgo", "today"),
    "30d": ("30daysAgo", "today"),
    "60d": ("60daysAgo", "today"),
    "90d": ("90daysAgo", "today"),
}


def _parse_time_range(time_range: str) -> tuple[str, str]:
    try:
        return _TIME_RANGE_MAP[time_range]
    except KeyError as exc:
        raise BadRequestError(
            f"Invalid time_range '{time_range}'. "
            f"Supported: {sorted(_TIME_RANGE_MAP.keys())}"
        ) from exc


class GoogleAnalyticsService:
    def __init__(self, ga_client: GoogleAnalyticsClient, cache: CacheBackend) -> None:
        self._ga = ga_client
        self._cache = cache

    def _require_allowed_property(self, property_id: str) -> str:
        allowlist = settings.ga_properties
        if property_id not in allowlist:
            raise BadRequestError(f"Property '{property_id}' is not in allowlist.")
        return allowlist[property_id]

    async def _cached_or_fetch(self, cache_key: str, fetch_fn) -> dict:
        """Return cached payload; on miss, fetch and cache with configured TTL."""
        from datetime import datetime, timezone

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached["data"]

        data = await fetch_fn()
        wrapped = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        await self._cache.set(
            cache_key, wrapped, ttl_seconds=settings.ga_cache_ttl_seconds
        )
        return data

    async def get_traffic_overview(self, property_id: str, time_range: str) -> dict:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:traffic:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=[
                    "activeUsers",
                    "newUsers",
                    "sessions",
                    "engagedSessions",
                    "engagementRate",
                    "averageSessionDuration",
                    "bounceRate",
                ],
                start_date=start,
                end_date=end,
            )
            labels = [r["dimensions"][0] for r in resp["rows"]]
            if resp["rows"]:
                cols = list(zip(*[r["metrics"] for r in resp["rows"]]))
            else:
                cols = [()] * 7

            def to_int(xs):
                return [int(x) for x in xs]

            def to_float(xs):
                return [float(x) for x in xs]

            return {
                "labels": labels,
                "active_users": to_int(cols[0]),
                "new_users": to_int(cols[1]),
                "sessions": to_int(cols[2]),
                "engaged_sessions": to_int(cols[3]),
                "engagement_rate": to_float(cols[4]),
                "avg_session_duration": to_float(cols[5]),
                "bounce_rate": to_float(cols[6]),
            }

        return await self._cached_or_fetch(key, fetch)

    async def get_top_pages(
        self, property_id: str, time_range: str, limit: int = 10
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:pages:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["pagePath", "pageTitle"],
                metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "path": r["dimensions"][0],
                    "title": r["dimensions"][1],
                    "views": int(r["metrics"][0]),
                    "users": int(r["metrics"][1]),
                    "avg_duration": float(r["metrics"][2]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)

    async def get_platform_breakdown(self, property_id: str, time_range: str) -> dict:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:platforms:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["deviceCategory", "operatingSystem", "browser"],
                metrics=["activeUsers", "sessions"],
                start_date=start,
                end_date=end,
            )
            device: dict[str, dict] = {}
            os_: dict[str, dict] = {}
            browser: dict[str, dict] = {}
            for row in resp["rows"]:
                dev, osn, br = row["dimensions"]
                users = int(row["metrics"][0])
                sessions = int(row["metrics"][1])
                for bucket, label in ((device, dev), (os_, osn), (browser, br)):
                    entry = bucket.setdefault(
                        label, {"label": label, "users": 0, "sessions": 0}
                    )
                    entry["users"] += users
                    entry["sessions"] += sessions

            def sort_desc(d):
                return sorted(d.values(), key=lambda x: -x["users"])

            return {
                "device": sort_desc(device),
                "os": sort_desc(os_),
                "browser": sort_desc(browser),
            }

        return await self._cached_or_fetch(key, fetch)

    async def get_geo_breakdown(
        self, property_id: str, time_range: str, limit: int = 20
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:geography:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["country", "city"],
                metrics=["activeUsers", "sessions"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="activeUsers"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "country": r["dimensions"][0],
                    "city": r["dimensions"][1],
                    "users": int(r["metrics"][0]),
                    "sessions": int(r["metrics"][1]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)

    async def get_top_events(
        self, property_id: str, time_range: str, limit: int = 15
    ) -> list[dict]:
        self._require_allowed_property(property_id)
        key = f"ga:{property_id}:events:{time_range}"
        start, end = _parse_time_range(time_range)

        async def fetch():
            from google.analytics.data_v1beta.types import OrderBy

            resp = await self._ga.run_report(
                property_id=property_id,
                dimensions=["eventName"],
                metrics=["eventCount", "totalUsers"],
                start_date=start,
                end_date=end,
                limit=limit,
                order_bys=[
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name="eventCount"),
                        desc=True,
                    )
                ],
            )
            return [
                {
                    "name": r["dimensions"][0],
                    "count": int(r["metrics"][0]),
                    "users": int(r["metrics"][1]),
                }
                for r in resp["rows"]
            ]

        return await self._cached_or_fetch(key, fetch)

    async def get_property_overview(
        self,
        property_id: str,
        time_range: str,
        force_refresh: bool = False,
    ) -> dict:
        """Run all 5 reports concurrently; tolerate individual failures."""
        import asyncio
        import logging
        from datetime import datetime, timedelta, timezone

        logger = logging.getLogger(__name__)
        property_name = self._require_allowed_property(property_id)
        _parse_time_range(time_range)  # validate early

        if force_refresh:
            for report in REPORT_NAMES:
                await self._cache.delete(f"ga:{property_id}:{report}:{time_range}")

        traffic_task = self.get_traffic_overview(property_id, time_range)
        pages_task = self.get_top_pages(property_id, time_range)
        platforms_task = self.get_platform_breakdown(property_id, time_range)
        geo_task = self.get_geo_breakdown(property_id, time_range)
        events_task = self.get_top_events(property_id, time_range)

        results = await asyncio.gather(
            traffic_task,
            pages_task,
            platforms_task,
            geo_task,
            events_task,
            return_exceptions=True,
        )
        labels = ("traffic", "pages", "platforms", "geography", "events")
        payload: dict = {}
        failed: list[str] = []
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.warning(
                    "GA report '%s' failed for property %s/%s: %s",
                    label,
                    property_id,
                    time_range,
                    result,
                )
                failed.append(label)
                payload[label] = _empty_payload_for(label)
            else:
                payload[label] = result

        cached_until = (
            datetime.now(timezone.utc)
            + timedelta(seconds=settings.ga_cache_ttl_seconds)
        ).isoformat()

        return {
            "property_id": property_id,
            "property_name": property_name,
            "time_range": time_range,
            "cached_until": cached_until,
            "traffic": payload["traffic"],
            "top_pages": payload["pages"],
            "platforms": payload["platforms"],
            "geography": payload["geography"],
            "events": payload["events"],
            "partial": bool(failed),
            "failed_reports": failed,
        }


def _empty_payload_for(label: str):
    """Default shape when an individual report fails."""
    if label == "traffic":
        return {
            "labels": [],
            "active_users": [],
            "new_users": [],
            "sessions": [],
            "engaged_sessions": [],
            "engagement_rate": [],
            "avg_session_duration": [],
            "bounce_rate": [],
        }
    if label == "platforms":
        return {"device": [], "os": [], "browser": []}
    return []


_instance: GoogleAnalyticsService | None = None


def get_google_analytics_service() -> GoogleAnalyticsService:
    global _instance
    if _instance is None:
        from app.integrations.google_analytics import get_google_analytics_client
        from app.services.cache import get_cache_backend

        _instance = GoogleAnalyticsService(
            ga_client=get_google_analytics_client(),
            cache=get_cache_backend(),
        )
    return _instance
