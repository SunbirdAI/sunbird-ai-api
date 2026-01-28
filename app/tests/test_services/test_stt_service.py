"""
Tests for STT Service Module.

This module contains unit tests for the STTService class defined in
app/services/stt_service.py. Tests cover audio validation, audio processing,
cloud storage interactions, and transcription API calls.
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydub.exceptions import CouldntDecodeError

from app.services.base import BaseService
from app.services.stt_service import (
    AudioProcessingError,
    AudioValidationError,
    STTService,
    TranscriptionError,
    TranscriptionResult,
    get_stt_service,
    reset_stt_service,
)


class TestSTTServiceInitialization:
    """Tests for STTService initialization."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_stt_service()

    def test_default_initialization(self) -> None:
        """Test that service initializes with environment settings."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test-endpoint-id",
                "AUDIO_CONTENT_BUCKET_NAME": "test-bucket",
                "RUNPOD_API_KEY": "test-api-key",
            },
        ):
            service = STTService()

            assert service.runpod_endpoint_id == "test-endpoint-id"
            assert service.audio_bucket_name == "test-bucket"
            assert service.service_name == "STTService"

    def test_custom_initialization(self) -> None:
        """Test that service accepts custom configuration."""
        service = STTService(
            runpod_endpoint_id="custom-endpoint",
            audio_bucket_name="custom-bucket",
        )

        assert service.runpod_endpoint_id == "custom-endpoint"
        assert service.audio_bucket_name == "custom-bucket"

    def test_inherits_from_base_service(self) -> None:
        """Test that STTService inherits from BaseService."""
        service = STTService(
            runpod_endpoint_id="test",
            audio_bucket_name="test",
        )

        assert isinstance(service, BaseService)
        assert hasattr(service, "log_info")
        assert hasattr(service, "log_error")
        assert hasattr(service, "log_warning")

    def test_logs_warning_when_endpoint_missing(self) -> None:
        """Test that warning is logged when RUNPOD_ENDPOINT_ID is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(STTService, "log_warning") as mock_log_warning:
                STTService()

                mock_log_warning.assert_called_with("RUNPOD_ENDPOINT_ID not configured")


class TestTranscriptionResultDataclass:
    """Tests for TranscriptionResult dataclass."""

    def test_required_fields(self) -> None:
        """Test TranscriptionResult with required fields only."""
        result = TranscriptionResult(
            transcription="Hello world",
            diarization_output={"speakers": []},
            formatted_diarization_output="Speaker 1: Hello",
        )

        assert result.transcription == "Hello world"
        assert result.diarization_output == {"speakers": []}
        assert result.formatted_diarization_output == "Speaker 1: Hello"
        assert result.audio_url is None
        assert result.blob_name is None
        assert result.was_trimmed is False
        assert result.original_duration is None

    def test_all_fields(self) -> None:
        """Test TranscriptionResult with all fields."""
        result = TranscriptionResult(
            transcription="Hello world",
            diarization_output={"speakers": ["A", "B"]},
            formatted_diarization_output="A: Hello\nB: World",
            audio_url="gs://bucket/file.mp3",
            blob_name="file.mp3",
            was_trimmed=True,
            original_duration=15.5,
            processing_time=2.3,
        )

        assert result.transcription == "Hello world"
        assert result.audio_url == "gs://bucket/file.mp3"
        assert result.blob_name == "file.mp3"
        assert result.was_trimmed is True
        assert result.original_duration == 15.5
        assert result.processing_time == 2.3


class TestAudioValidation:
    """Tests for audio file validation."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test",
            audio_bucket_name="test",
        )

    def test_validate_valid_mp3(self) -> None:
        """Test validation passes for valid MP3 file."""
        # Should not raise
        self.service.validate_audio_file("audio/mpeg", ".mp3")

    def test_validate_valid_wav(self) -> None:
        """Test validation passes for valid WAV file."""
        self.service.validate_audio_file("audio/wav", ".wav")

    def test_validate_valid_ogg(self) -> None:
        """Test validation passes for valid OGG file."""
        self.service.validate_audio_file("audio/ogg", ".ogg")

    def test_validate_valid_m4a(self) -> None:
        """Test validation passes for valid M4A file."""
        self.service.validate_audio_file("audio/x-m4a", ".m4a")

    def test_validate_invalid_content_type(self) -> None:
        """Test validation fails for invalid content type."""
        with pytest.raises(AudioValidationError) as exc_info:
            self.service.validate_audio_file("video/mp4", ".mp4")

        assert "Unsupported file type" in str(exc_info.value)

    def test_validate_mismatched_extension(self) -> None:
        """Test validation fails when extension doesn't match content type."""
        with pytest.raises(AudioValidationError) as exc_info:
            self.service.validate_audio_file("audio/mpeg", ".wav")

        assert "Unsupported file type" in str(exc_info.value)


class TestAudioDurationProcessing:
    """Tests for audio duration processing."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test",
            audio_bucket_name="test",
        )

    def test_audio_under_limit_not_trimmed(self) -> None:
        """Test that audio under limit is not trimmed."""
        # Create mock audio segment (5 minutes = 300000 ms)
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=300000)

        with patch(
            "app.services.stt_service.AudioSegment.from_file", return_value=mock_audio
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name

            try:
                (
                    result_path,
                    was_trimmed,
                    original_duration,
                ) = self.service.process_audio_duration(temp_path, ".mp3")

                assert result_path == temp_path
                assert was_trimmed is False
                assert original_duration is None
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    def test_audio_over_limit_is_trimmed(self) -> None:
        """Test that audio over limit is trimmed."""
        # Create mock audio segment (15 minutes = 900000 ms)
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=900000)
        mock_trimmed = MagicMock()
        mock_audio.__getitem__ = MagicMock(return_value=mock_trimmed)

        with patch(
            "app.services.stt_service.AudioSegment.from_file", return_value=mock_audio
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name
                f.write(b"fake audio data")

            trimmed_path = os.path.join(
                os.path.dirname(temp_path),
                f"trimmed_{os.path.basename(temp_path)}",
            )

            try:
                (
                    result_path,
                    was_trimmed,
                    original_duration,
                ) = self.service.process_audio_duration(temp_path, ".mp3")

                assert was_trimmed is True
                assert original_duration == pytest.approx(15.0, rel=0.1)
                mock_trimmed.export.assert_called_once()
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(trimmed_path):
                    os.remove(trimmed_path)

    def test_corrupted_audio_raises_error(self) -> None:
        """Test that corrupted audio raises AudioProcessingError."""
        with patch(
            "app.services.stt_service.AudioSegment.from_file",
            side_effect=CouldntDecodeError("Decoding failed"),
        ):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name

            with pytest.raises(AudioProcessingError) as exc_info:
                self.service.process_audio_duration(temp_path, ".mp3")

            assert "Could not decode audio file" in str(exc_info.value)


class TestCloudStorageUpload:
    """Tests for cloud storage upload functionality."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_upload(self) -> None:
        """Test successful file upload to cloud storage."""
        with patch(
            "app.services.stt_service.upload_audio_file",
            return_value=("blob-name.mp3", "https://storage.example.com/blob-name.mp3"),
        ):
            blob_name, blob_url = await self.service.upload_to_storage(
                "/path/to/file.mp3"
            )

            assert blob_name == "blob-name.mp3"
            assert blob_url == "https://storage.example.com/blob-name.mp3"

    @pytest.mark.asyncio
    async def test_upload_returns_none_raises_error(self) -> None:
        """Test that upload failure raises AudioProcessingError."""
        with patch(
            "app.services.stt_service.upload_audio_file",
            return_value=(None, None),
        ):
            with pytest.raises(AudioProcessingError) as exc_info:
                await self.service.upload_to_storage("/path/to/file.mp3")

            assert "Failed to upload" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_exception_raises_error(self) -> None:
        """Test that upload exception raises AudioProcessingError."""
        with patch(
            "app.services.stt_service.upload_audio_file",
            side_effect=Exception("Network error"),
        ):
            with pytest.raises(AudioProcessingError) as exc_info:
                await self.service.upload_to_storage("/path/to/file.mp3")

            assert "Failed to upload" in str(exc_info.value)


class TestTranscriptionAPI:
    """Tests for transcription API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_transcription(self) -> None:
        """Test successful transcription API call."""
        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {"speakers": []},
            "formatted_diarization_output": "",
        }

        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=(mock_response, {}),
        ):
            result = await self.service.call_transcription_api(
                blob_name="audio.mp3",
                language="lug",
                adapter="lug",
            )

            assert result["audio_transcription"] == "Hello world"

    @pytest.mark.asyncio
    async def test_transcription_with_diarization(self) -> None:
        """Test transcription API call with speaker diarization."""
        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {"speakers": ["A", "B"]},
            "formatted_diarization_output": "A: Hello\nB: World",
        }

        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=(mock_response, {}),
        ) as mock_run:
            await self.service.call_transcription_api(
                blob_name="audio.mp3",
                language="lug",
                adapter="lug",
                recognise_speakers=True,
            )

            # Verify recognise_speakers was passed in payload
            call_args = mock_run.call_args[0][0]
            assert call_args["recognise_speakers"] is True

    @pytest.mark.asyncio
    async def test_transcription_timeout_raises_error(self) -> None:
        """Test that timeout raises TranscriptionError."""
        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=TimeoutError("Request timed out"),
        ):
            with pytest.raises(TranscriptionError) as exc_info:
                await self.service.call_transcription_api(
                    blob_name="audio.mp3",
                    language="lug",
                    adapter="lug",
                )

            assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcription_connection_error_raises_error(self) -> None:
        """Test that connection error raises TranscriptionError."""
        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(TranscriptionError) as exc_info:
                await self.service.call_transcription_api(
                    blob_name="audio.mp3",
                    language="lug",
                    adapter="lug",
                )

            assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcription_organisation_flag(self) -> None:
        """Test transcription API call with organisation flag."""
        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            return_value=(mock_response, {}),
        ) as mock_run:
            await self.service.call_transcription_api(
                blob_name="audio.mp3",
                language="",
                adapter="",
                organisation=True,
            )

            # Verify organisation was passed in payload
            call_args = mock_run.call_args[0][0]
            assert call_args.get("organisation") is True


class TestTranscriptionSyncAPI:
    """Tests for sync transcription API calls."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_sync_transcription(self) -> None:
        """Test successful sync transcription API call."""
        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(return_value=mock_response)

        with patch(
            "app.services.stt_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            result = await self.service.call_transcription_api_sync(
                blob_name="audio.mp3",
                language="lug",
                adapter="lug",
            )

            assert result["audio_transcription"] == "Hello world"

    @pytest.mark.asyncio
    async def test_sync_transcription_timeout(self) -> None:
        """Test sync transcription timeout raises TranscriptionError."""
        mock_endpoint = MagicMock()
        mock_endpoint.run_sync = MagicMock(side_effect=TimeoutError("Timeout"))

        with patch(
            "app.services.stt_service.runpod.Endpoint", return_value=mock_endpoint
        ):
            with pytest.raises(TranscriptionError) as exc_info:
                await self.service.call_transcription_api_sync(
                    blob_name="audio.mp3",
                    language="lug",
                    adapter="lug",
                )

            assert "timed out" in str(exc_info.value)


class TestTranscribeFromGCS:
    """Tests for transcribe_from_gcs method."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_gcs_transcription(self) -> None:
        """Test successful transcription from GCS."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_to_filename = MagicMock()

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=300000)  # 5 minutes

        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        with patch("app.services.stt_service.storage.Client", return_value=mock_client):
            with patch(
                "app.services.stt_service.AudioSegment.from_file",
                return_value=mock_audio,
            ):
                with patch.object(
                    self.service,
                    "call_transcription_api_sync",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    result = await self.service.transcribe_from_gcs(
                        gcs_blob_name="audio.mp3",
                        language="lug",
                    )

                    assert result.transcription == "Hello world"
                    assert result.blob_name == "audio.mp3"
                    assert result.was_trimmed is False

    @pytest.mark.asyncio
    async def test_gcs_blob_not_found(self) -> None:
        """Test that missing GCS blob raises AudioProcessingError."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("app.services.stt_service.storage.Client", return_value=mock_client):
            with pytest.raises(AudioProcessingError) as exc_info:
                await self.service.transcribe_from_gcs(gcs_blob_name="missing.mp3")

            assert "does not exist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_gcs_transcription_no_result(self) -> None:
        """Test that empty transcription raises TranscriptionError."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_to_filename = MagicMock()

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=300000)

        mock_response = {
            "audio_transcription": None,
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        with patch("app.services.stt_service.storage.Client", return_value=mock_client):
            with patch(
                "app.services.stt_service.AudioSegment.from_file",
                return_value=mock_audio,
            ):
                with patch.object(
                    self.service,
                    "call_transcription_api_sync",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    with pytest.raises(TranscriptionError) as exc_info:
                        await self.service.transcribe_from_gcs(
                            gcs_blob_name="audio.mp3",
                        )

                    assert "No transcription was generated" in str(exc_info.value)


class TestTranscribeUploadedFile:
    """Tests for transcribe_uploaded_file method."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_uploaded_file_transcription(self) -> None:
        """Test successful transcription of uploaded file."""
        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=300000)

        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
            f.write(b"fake audio")

        try:
            with patch(
                "app.services.stt_service.AudioSegment.from_file",
                return_value=mock_audio,
            ):
                with patch.object(
                    self.service,
                    "upload_to_storage",
                    new_callable=AsyncMock,
                    return_value=("blob.mp3", "https://example.com/blob.mp3"),
                ):
                    with patch.object(
                        self.service,
                        "call_transcription_api",
                        new_callable=AsyncMock,
                        return_value=mock_response,
                    ):
                        result = await self.service.transcribe_uploaded_file(
                            file_path=temp_path,
                            file_extension=".mp3",
                            language="lug",
                        )

                        assert result.transcription == "Hello world"
                        assert result.audio_url == "https://example.com/blob.mp3"
                        assert result.was_trimmed is False
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestTranscribeOrgAudio:
    """Tests for transcribe_org_audio method."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_successful_org_transcription(self) -> None:
        """Test successful organization audio transcription."""
        mock_response = {
            "audio_transcription": "Hello world",
            "diarization_output": {"speakers": ["A"]},
            "formatted_diarization_output": "A: Hello world",
        }

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name
            f.write(b"fake audio")

        try:
            with patch.object(
                self.service,
                "upload_to_storage",
                new_callable=AsyncMock,
                return_value=("blob.mp3", "https://example.com/blob.mp3"),
            ):
                with patch.object(
                    self.service,
                    "call_transcription_api",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ) as mock_api:
                    result = await self.service.transcribe_org_audio(
                        file_path=temp_path,
                        recognise_speakers=True,
                    )

                    assert result.transcription == "Hello world"
                    assert result.diarization_output == {"speakers": ["A"]}

                    # Verify organisation flag was passed
                    call_kwargs = mock_api.call_args[1]
                    assert call_kwargs["organisation"] is True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestSTTServiceSingleton:
    """Tests for singleton pattern and dependency injection."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_stt_service()

    def test_get_stt_service_creates_singleton(self) -> None:
        """Test that get_stt_service returns the same instance."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "AUDIO_CONTENT_BUCKET_NAME": "test",
            },
        ):
            service1 = get_stt_service()
            service2 = get_stt_service()

            assert service1 is service2

    def test_reset_stt_service_clears_singleton(self) -> None:
        """Test that reset_stt_service clears the singleton."""
        with patch.dict(
            os.environ,
            {
                "RUNPOD_ENDPOINT_ID": "test",
                "AUDIO_CONTENT_BUCKET_NAME": "test",
            },
        ):
            service1 = get_stt_service()
            reset_stt_service()
            service2 = get_stt_service()

            assert service1 is not service2


class TestSTTServiceLogging:
    """Tests for logging functionality."""

    def setup_method(self) -> None:
        """Create service instance for tests."""
        self.service = STTService(
            runpod_endpoint_id="test-endpoint",
            audio_bucket_name="test-bucket",
        )

    @pytest.mark.asyncio
    async def test_transcription_logs_info(self) -> None:
        """Test that transcription logs info messages."""
        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_to_filename = MagicMock()

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        mock_audio = MagicMock()
        mock_audio.__len__ = MagicMock(return_value=300000)

        mock_response = {
            "audio_transcription": "Hello",
            "diarization_output": {},
            "formatted_diarization_output": "",
        }

        with patch("app.services.stt_service.storage.Client", return_value=mock_client):
            with patch(
                "app.services.stt_service.AudioSegment.from_file",
                return_value=mock_audio,
            ):
                with patch.object(
                    self.service,
                    "call_transcription_api_sync",
                    new_callable=AsyncMock,
                    return_value=mock_response,
                ):
                    with patch.object(self.service, "log_info") as mock_log:
                        await self.service.transcribe_from_gcs("audio.mp3")

                        # Should log at least once
                        assert mock_log.call_count >= 1

    @pytest.mark.asyncio
    async def test_transcription_logs_error_on_failure(self) -> None:
        """Test that transcription logs errors on API failure."""
        with patch(
            "app.services.stt_service.run_job_and_get_output",
            new_callable=AsyncMock,
            side_effect=Exception("API Error"),
        ):
            with patch.object(self.service, "log_error") as mock_log:
                with pytest.raises(TranscriptionError):
                    await self.service.call_transcription_api(
                        blob_name="audio.mp3",
                        language="lug",
                        adapter="lug",
                    )

                mock_log.assert_called()


class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_audio_validation_error(self) -> None:
        """Test AudioValidationError exception."""
        error = AudioValidationError("Invalid audio format")
        assert str(error) == "Invalid audio format"

    def test_audio_processing_error(self) -> None:
        """Test AudioProcessingError exception."""
        error = AudioProcessingError("Could not process audio")
        assert str(error) == "Could not process audio"

    def test_transcription_error(self) -> None:
        """Test TranscriptionError exception."""
        error = TranscriptionError("Transcription failed")
        assert str(error) == "Transcription failed"
