"""
Tests for RunPod Integration Module.

This module contains unit tests for the RunPodClient class and related
functions defined in app/integrations/runpod.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.runpod import (
    RunPodClient,
    get_runpod_client,
    normalize_runpod_response,
    reset_runpod_client,
    run_job_and_get_output,
)


class TestRunPodClientInitialization:
    """Tests for RunPodClient initialization."""

    def test_default_initialization_from_env(self) -> None:
        """Test that client initializes with environment variables."""
        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint-id",
                "RUNPOD_API_KEY": "test-api-key",
            },
        ):
            client = RunPodClient()

            assert client.endpoint_id == "test-endpoint-id"
            assert client.api_key == "test-api-key"
            assert client.default_timeout == 600

    def test_custom_initialization(self) -> None:
        """Test that client accepts custom configuration."""
        client = RunPodClient(
            endpoint_id="custom-endpoint",
            api_key="custom-key",
            default_timeout=300,
        )

        assert client.endpoint_id == "custom-endpoint"
        assert client.api_key == "custom-key"
        assert client.default_timeout == 300

    def test_missing_endpoint_id_logs_warning(self) -> None:
        """Test that missing endpoint ID logs a warning."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("app.integrations.runpod.logger") as mock_logger:
                client = RunPodClient(api_key="test-key")

                mock_logger.warning.assert_called()
                assert client.endpoint_id is None


class TestRunPodClientRunJob:
    """Tests for RunPodClient.run_job method."""

    @pytest.mark.asyncio
    async def test_run_job_raises_without_endpoint_id(self) -> None:
        """Test that run_job raises ValueError without endpoint_id."""
        # Ensure no env var fallback by clearing it
        with patch.dict("os.environ", {}, clear=True):
            client = RunPodClient(endpoint_id=None, api_key="test-key")

            with pytest.raises(ValueError, match="RUNPOD_ENDPOINT_ID"):
                await client.run_job({"input": "test"})

    @pytest.mark.asyncio
    async def test_run_job_success(self) -> None:
        """Test successful job execution."""
        client = RunPodClient(
            endpoint_id="test-endpoint",
            api_key="test-key",
        )

        mock_job = AsyncMock()
        mock_job.endpoint_id = "test-endpoint"
        mock_job.job_id = "job-123"
        mock_job.status = AsyncMock(return_value="COMPLETED")
        mock_job.output = AsyncMock(return_value={"result": "success"})

        mock_endpoint = AsyncMock()
        mock_endpoint.run = AsyncMock(return_value=mock_job)

        with patch(
            "app.integrations.runpod.http_client.AsyncClientSession"
        ) as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with patch(
                "app.integrations.runpod.AsyncioEndpoint", return_value=mock_endpoint
            ):
                with patch.object(
                    client,
                    "_get_job_details_sync",
                    return_value={"status": "COMPLETED"},
                ):
                    output, details = await client.run_job({"input": "test"})

                    assert output == {"result": "success"}
                    assert details["status"] == "COMPLETED"


class TestNormalizeRunpodResponse:
    """Tests for normalize_runpod_response function."""

    def test_normalize_non_dict_input(self) -> None:
        """Test that non-dict input gets wrapped."""
        resp = "plain string output"
        out = normalize_runpod_response(resp)

        assert isinstance(out, dict)
        assert out["output"] == resp
        assert out["delayTime"] is None
        assert out["executionTime"] is None
        assert out["id"] is None
        assert out["status"] is None
        assert out["workerId"] is None

    def test_normalize_already_full_shape(self) -> None:
        """Test that full response passes through unchanged."""
        resp = {
            "delayTime": 0.1,
            "executionTime": 0.2,
            "id": "job-123",
            "output": {"translated_text": "hola"},
            "status": "COMPLETED",
            "workerId": "worker-1",
        }
        out = normalize_runpod_response(resp)

        # Should return unchanged (same reference or equivalent content)
        assert out["id"] == "job-123"
        assert out["status"] == "COMPLETED"
        assert out["output"] == {"translated_text": "hola"}

    def test_normalize_with_nested_output_field(self) -> None:
        """Test normalization of dict with only output field."""
        resp = {"output": {"text": "hello", "translated": "salut"}}
        out = normalize_runpod_response(resp)

        assert out["output"] == resp["output"]
        assert out["status"] == "COMPLETED"
        assert out["delayTime"] is None

    def test_normalize_empty_dict(self) -> None:
        """Test normalization of empty dict."""
        resp = {}
        out = normalize_runpod_response(resp)

        # empty dict -> output={}, status should be None
        assert out["output"] == {}
        assert out["status"] is None

    def test_normalize_partial_response(self) -> None:
        """Test normalization with some top-level keys."""
        resp = {
            "id": "job-456",
            "status": "COMPLETED",
        }
        out = normalize_runpod_response(resp)

        # Has top-level keys, should pass through
        assert out["id"] == "job-456"
        assert out["status"] == "COMPLETED"

    def test_normalize_integer_input(self) -> None:
        """Test normalization of integer input."""
        resp = 42
        out = normalize_runpod_response(resp)

        assert out["output"] == 42
        assert out["status"] is None

    def test_normalize_list_input(self) -> None:
        """Test normalization of list input."""
        resp = [1, 2, 3]
        out = normalize_runpod_response(resp)

        assert out["output"] == [1, 2, 3]
        assert out["status"] is None


class TestRunPodClientSingleton:
    """Tests for singleton pattern and dependency injection."""

    def test_get_runpod_client_creates_singleton(self) -> None:
        """Test that get_runpod_client returns the same instance."""
        reset_runpod_client()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "RUNPOD_API_KEY": "test-key",
            },
        ):
            client1 = get_runpod_client()
            client2 = get_runpod_client()

            assert client1 is client2

    def test_reset_runpod_client_clears_singleton(self) -> None:
        """Test that reset_runpod_client clears the singleton."""
        reset_runpod_client()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "RUNPOD_API_KEY": "test-key",
            },
        ):
            client1 = get_runpod_client()
            reset_runpod_client()
            client2 = get_runpod_client()

            assert client1 is not client2


class TestBackwardCompatibility:
    """Tests for backward-compatible functions."""

    @pytest.mark.asyncio
    async def test_run_job_and_get_output_uses_singleton(self) -> None:
        """Test that run_job_and_get_output uses the singleton client."""
        reset_runpod_client()

        with patch.dict(
            "os.environ",
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint",
                "RUNPOD_API_KEY": "test-key",
            },
        ):
            with patch.object(
                RunPodClient, "run_job", new_callable=AsyncMock
            ) as mock_run_job:
                mock_run_job.return_value = (
                    {"result": "test"},
                    {"status": "COMPLETED"},
                )

                output, details = await run_job_and_get_output(
                    {"input": "test"}, timeout=300
                )

                mock_run_job.assert_called_once_with({"input": "test"}, timeout=300)
                assert output == {"result": "test"}
