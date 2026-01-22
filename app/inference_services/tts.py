"""
TTS Service

Handles interactions with the external Text-to-Speech API.
Supports both synchronous and streaming audio generation.
"""

from typing import AsyncGenerator, Optional

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.models.enums import SpeakerID


class TTSService:
    """
    Service for interacting with the external TTS API.

    Supports both full audio generation and streaming responses.
    """

    def __init__(self, api_url: Optional[str] = None, timeout: Optional[int] = None):
        """
        Initialize the TTS service.

        Args:
            api_url: External TTS API URL (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
        """
        self.api_url = api_url or settings.tts_api_url
        self.timeout = timeout or settings.request_timeout_seconds

    def _get_speaker_id_value(self, speaker_id: int | SpeakerID) -> int:
        """Extract integer value from speaker_id."""
        return speaker_id.value if isinstance(speaker_id, SpeakerID) else speaker_id

    async def generate_audio(self, text: str, speaker_id: int | SpeakerID) -> bytes:
        """
        Generate audio from text using the external TTS API.

        Args:
            text: Text to convert to speech
            speaker_id: Speaker voice ID

        Returns:
            Raw audio bytes (WAV format)

        Raises:
            HTTPException: If the TTS API returns an error
        """
        sid = self._get_speaker_id_value(speaker_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.api_url, params={"text": text, "speaker_id": str(sid)}
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"TTS API error: {response.text}",
                )

            return response.content

    async def generate_audio_stream(
        self, text: str, speaker_id: int | SpeakerID, chunk_size: int = 8192
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream audio chunks from the TTS API.

        Args:
            text: Text to convert to speech
            speaker_id: Speaker voice ID
            chunk_size: Size of each chunk in bytes

        Yields:
            Audio data chunks

        Raises:
            HTTPException: If the TTS API returns an error
        """
        sid = self._get_speaker_id_value(speaker_id)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", self.api_url, params={"text": text, "speaker_id": str(sid)}
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"TTS API error: {error_text.decode()}",
                    )

                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    yield chunk

    async def health_check(self) -> bool:
        """
        Check if the TTS API is reachable.

        Returns:
            True if the API responds, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Just check if we can connect (HEAD or small request)
                response = await client.head(self.api_url)
                return response.status_code < 500
        except Exception:
            return False

    @staticmethod
    def estimate_duration(text: str, words_per_minute: int = 150) -> float:
        """
        Estimate audio duration based on text length.

        Args:
            text: Input text
            words_per_minute: Assumed speaking rate

        Returns:
            Estimated duration in seconds
        """
        word_count = len(text.split())
        return (word_count / words_per_minute) * 60


# Singleton instance for dependency injection
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """
    Get or create the TTS service singleton.

    Returns:
        TTSService instance
    """
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
