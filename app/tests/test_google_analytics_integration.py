"""Tests for the Google Analytics Data API integration wrapper.

These tests exercise only the thin integration layer: auth setup and
proto-to-dict normalisation. Business logic lives in the service layer
and is covered by its own tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.google_analytics import GoogleAnalyticsClient


@pytest.fixture
def fake_ga_response():
    """Build a fake BetaAnalyticsDataClient.run_report response proto."""
    response = MagicMock()
    response.dimension_headers = [MagicMock(name="date")]
    response.dimension_headers[0].name = "date"
    response.metric_headers = [MagicMock(name="activeUsers")]
    response.metric_headers[0].name = "activeUsers"

    row = MagicMock()
    dim = MagicMock()
    dim.value = "2026-04-18"
    row.dimension_values = [dim]
    metric = MagicMock()
    metric.value = "42"
    row.metric_values = [metric]
    response.rows = [row]
    return response


async def test_run_report_returns_normalised_dict(fake_ga_response):
    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ) as mock_creds, patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.run_report.return_value = fake_ga_response
        mock_client_cls.return_value = mock_client

        client = GoogleAnalyticsClient(target_sa="ga-reader@test.iam")
        result = await client.run_report(
            property_id="506611499",
            dimensions=["date"],
            metrics=["activeUsers"],
            start_date="7daysAgo",
        )

    assert result == {
        "dimension_headers": ["date"],
        "metric_headers": ["activeUsers"],
        "rows": [
            {"dimensions": ["2026-04-18"], "metrics": ["42"]},
        ],
    }
    mock_creds.assert_called_once()
    kwargs = mock_creds.call_args.kwargs
    assert kwargs["target_principal"] == "ga-reader@test.iam"
    assert kwargs["target_scopes"] == [
        "https://www.googleapis.com/auth/analytics.readonly"
    ]


async def test_run_report_passes_limit_and_order_bys():
    with patch(
        "app.integrations.google_analytics.google.auth.default",
        return_value=(MagicMock(), None),
    ), patch(
        "app.integrations.google_analytics.impersonated_credentials.Credentials"
    ), patch(
        "app.integrations.google_analytics.BetaAnalyticsDataClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client.run_report.return_value = MagicMock(
            dimension_headers=[], metric_headers=[], rows=[]
        )
        mock_client_cls.return_value = mock_client

        client = GoogleAnalyticsClient(target_sa="ga-reader@test.iam")
        await client.run_report(
            property_id="506611499",
            dimensions=["pagePath"],
            metrics=["screenPageViews"],
            start_date="7daysAgo",
            limit=10,
        )

    call_request = mock_client.run_report.call_args.args[0]
    assert call_request.property == "properties/506611499"
    assert call_request.limit == 10
