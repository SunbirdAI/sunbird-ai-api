"""
Audio Processing Utilities.

This module provides common audio processing utilities used across the Sunbird AI API.
Contains helper functions for audio validation, format handling, and metadata extraction.

Usage:
    from app.utils.audio import (
        get_audio_extension,
        validate_audio_mime_type,
        estimate_speech_duration,
        get_content_type_from_extension
    )

Note:
    For service-specific audio processing (transcription, TTS), see:
    - app/services/stt_service.py - STT audio processing
    - app/services/tts_service.py - TTS audio generation
    - app/utils/upload_audio_file_gcp.py - Audio file uploads
"""

from typing import Optional

# Common audio MIME types and their extensions
AUDIO_MIME_TYPES = {
    "audio/mpeg": [".mp3"],
    "audio/wav": [".wav"],
    "audio/x-wav": [".wav"],
    "audio/ogg": [".ogg"],
    "audio/x-m4a": [".m4a"],
    "audio/aac": [".aac"],
    "audio/mp4": [".m4a", ".mp4"],
    "audio/webm": [".webm"],
}

# Reverse mapping: extension to MIME type
EXTENSION_TO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/x-m4a",
    ".aac": "audio/aac",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
}


def get_audio_extension(filename: str) -> str:
    """Extract file extension from filename.

    Args:
        filename: The name of the audio file.

    Returns:
        File extension including the dot (e.g., '.mp3').
        Returns empty string if no extension found.

    Example:
        >>> get_audio_extension("recording.mp3")
        '.mp3'
        >>> get_audio_extension("audio.file.wav")
        '.wav'
    """
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def validate_audio_mime_type(content_type: str) -> bool:
    """Check if a MIME type is a supported audio format.

    Args:
        content_type: The MIME type to validate.

    Returns:
        True if the MIME type is supported, False otherwise.

    Example:
        >>> validate_audio_mime_type("audio/mpeg")
        True
        >>> validate_audio_mime_type("video/mp4")
        False
    """
    return content_type in AUDIO_MIME_TYPES


def get_content_type_from_extension(extension: str) -> Optional[str]:
    """Get MIME type from file extension.

    Args:
        extension: File extension (with or without leading dot).

    Returns:
        MIME type string if found, None otherwise.

    Example:
        >>> get_content_type_from_extension(".mp3")
        'audio/mpeg'
        >>> get_content_type_from_extension("wav")
        'audio/wav'
    """
    if not extension.startswith("."):
        extension = "." + extension
    return EXTENSION_TO_MIME.get(extension.lower())


def get_supported_extensions() -> list[str]:
    """Get list of all supported audio file extensions.

    Returns:
        List of supported extensions including dots.

    Example:
        >>> extensions = get_supported_extensions()
        >>> ".mp3" in extensions
        True
    """
    return list(EXTENSION_TO_MIME.keys())


def get_supported_mime_types() -> list[str]:
    """Get list of all supported audio MIME types.

    Returns:
        List of supported MIME types.

    Example:
        >>> mime_types = get_supported_mime_types()
        >>> "audio/mpeg" in mime_types
        True
    """
    return list(AUDIO_MIME_TYPES.keys())


def estimate_speech_duration(text: str, words_per_minute: int = 150) -> float:
    """Estimate duration of synthesized speech from text.

    Provides a rough estimate of how long generated speech audio will be
    based on an assumed speaking rate. Useful for UI feedback and
    progress indicators.

    Args:
        text: Input text to estimate duration for.
        words_per_minute: Assumed speaking rate. Defaults to 150 WPM,
            which is typical for clear speech synthesis.

    Returns:
        Estimated duration in seconds.

    Example:
        >>> text = "Hello, this is a test."
        >>> duration = estimate_speech_duration(text)
        >>> duration > 0
        True
        >>> # Longer text = longer duration
        >>> estimate_speech_duration("word " * 150) > estimate_speech_duration("word")
        True
    """
    if not text or not text.strip():
        return 0.0

    # Count words (simple split on whitespace)
    word_count = len(text.split())

    # Convert words per minute to words per second
    words_per_second = words_per_minute / 60

    # Calculate duration
    duration_seconds = word_count / words_per_second

    return round(duration_seconds, 2)


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string (e.g., "2:30", "1:05:23").

    Example:
        >>> format_duration(90)
        '1:30'
        >>> format_duration(3665)
        '1:01:05'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def is_audio_file(filename: str) -> bool:
    """Check if a filename has a supported audio extension.

    Args:
        filename: The filename to check.

    Returns:
        True if the file has a supported audio extension.

    Example:
        >>> is_audio_file("recording.mp3")
        True
        >>> is_audio_file("document.pdf")
        False
    """
    extension = get_audio_extension(filename)
    return extension in EXTENSION_TO_MIME


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove unsafe characters.

    Removes or replaces characters that could cause issues in file systems
    or URLs while preserving the extension.

    Args:
        filename: Original filename.

    Returns:
        Sanitized filename safe for file system use.

    Example:
        >>> sanitize_filename("my audio/file?.mp3")
        'my_audio_file.mp3'
    """
    # Preserve extension
    extension = get_audio_extension(filename)
    name_without_ext = filename[: -len(extension)] if extension else filename

    # Replace unsafe characters with underscore
    unsafe_chars = ["/", "\\", "?", "%", "*", ":", "|", '"', "<", ">", " "]
    sanitized = name_without_ext
    for char in unsafe_chars:
        sanitized = sanitized.replace(char, "_")

    # Remove multiple consecutive underscores
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")

    # Remove leading/trailing underscores
    sanitized = sanitized.strip("_")

    return sanitized + extension


__all__ = [
    "AUDIO_MIME_TYPES",
    "EXTENSION_TO_MIME",
    "get_audio_extension",
    "validate_audio_mime_type",
    "get_content_type_from_extension",
    "get_supported_extensions",
    "get_supported_mime_types",
    "estimate_speech_duration",
    "format_duration",
    "is_audio_file",
    "sanitize_filename",
]
