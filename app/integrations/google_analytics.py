"""Google Analytics Data API v1beta client with impersonated credentials.

This is a thin integration wrapper. It only handles auth setup and
proto-to-dict normalisation. All business logic lives in
`app/services/google_analytics_service.py`.
"""

import asyncio
import logging
from typing import Any

import google.auth
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunReportRequest,
)
from google.auth import impersonated_credentials

logger = logging.getLogger(__name__)

GA_READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class GoogleAnalyticsClient:
    """Wraps `BetaAnalyticsDataClient` with impersonated credentials.

    The source credentials come from the Cloud Run runtime identity
    (or a developer's gcloud ADC locally). They are exchanged for
    short-lived credentials of `target_sa` every hour.
    """

    def __init__(self, target_sa: str, scopes: list[str] | None = None) -> None:
        self._target_sa = target_sa
        source_creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=target_sa,
            target_scopes=scopes or [GA_READ_SCOPE],
            lifetime=3600,
        )
        self._client = BetaAnalyticsDataClient(credentials=self._creds)
        logger.info("GoogleAnalyticsClient initialised (impersonating %s)", target_sa)

    async def run_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: str,
        end_date: str = "today",
        limit: int | None = None,
        order_bys: list[OrderBy] | None = None,
    ) -> dict[str, Any]:
        """Execute a run_report call and return a plain-dict response.

        The underlying gRPC call is sync; we offload it to a thread so
        the FastAPI event loop stays responsive.
        """
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            limit=limit,
            order_bys=order_bys or [],
        )
        response = await asyncio.to_thread(self._client.run_report, request)
        return _response_to_dict(response)


def _response_to_dict(response: Any) -> dict[str, Any]:
    """Convert a RunReportResponse proto to a plain-dict shape."""
    return {
        "dimension_headers": [h.name for h in response.dimension_headers],
        "metric_headers": [h.name for h in response.metric_headers],
        "rows": [
            {
                "dimensions": [dv.value for dv in row.dimension_values],
                "metrics": [mv.value for mv in row.metric_values],
            }
            for row in response.rows
        ],
    }


_instance: GoogleAnalyticsClient | None = None


def get_google_analytics_client() -> GoogleAnalyticsClient:
    """Return a process-wide singleton client."""
    from app.core.config import settings

    global _instance
    if _instance is None:
        if not settings.ga_impersonation_target:
            raise RuntimeError(
                "GA_IMPERSONATION_TARGET is not configured. Set the env var "
                "or check `settings.ga_enabled` before constructing a client."
            )
        _instance = GoogleAnalyticsClient(
            target_sa=settings.ga_impersonation_target,
        )
    return _instance
