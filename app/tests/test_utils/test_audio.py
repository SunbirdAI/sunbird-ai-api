"""
Tests for Audio Utilities Module.

This module contains tests for the audio utility functions defined in
app/utils/audio.py. Tests verify audio file handling, validation,
and metadata extraction.
"""

import pytest

from app.utils.audio import (
    AUDIO_MIME_TYPES,
    EXTENSION_TO_MIME,
    estimate_speech_duration,
    format_duration,
    get_audio_extension,
    get_content_type_from_extension,
    get_supported_extensions,
    get_supported_mime_types,
    is_audio_file,
    sanitize_filename,
    validate_audio_mime_type,
)


class TestGetAudioExtension:
    """Tests for get_audio_extension function."""

    def test_simple_extension(self):
        """Test extracting simple file extension."""
        assert get_audio_extension("audio.mp3") == ".mp3"
        assert get_audio_extension("recording.wav") == ".wav"

    def test_multiple_dots_in_filename(self):
        """Test filename with multiple dots returns last extension."""
        assert get_audio_extension("my.audio.file.mp3") == ".mp3"
        assert get_audio_extension("test.recording.v2.wav") == ".wav"

    def test_no_extension(self):
        """Test filename without extension returns empty string."""
        assert get_audio_extension("audiofile") == ""
        assert get_audio_extension("noext") == ""

    def test_case_insensitive(self):
        """Test extension extraction is case-insensitive."""
        assert get_audio_extension("audio.MP3") == ".mp3"
        assert get_audio_extension("recording.WAV") == ".wav"

    def test_path_with_extension(self):
        """Test full path with filename."""
        assert get_audio_extension("/path/to/audio.mp3") == ".mp3"
        assert get_audio_extension("folder/subfolder/file.wav") == ".wav"


class TestValidateAudioMimeType:
    """Tests for validate_audio_mime_type function."""

    def test_valid_mime_types(self):
        """Test validation of supported MIME types."""
        assert validate_audio_mime_type("audio/mpeg") is True
        assert validate_audio_mime_type("audio/wav") is True
        assert validate_audio_mime_type("audio/ogg") is True

    def test_invalid_mime_types(self):
        """Test rejection of unsupported MIME types."""
        assert validate_audio_mime_type("video/mp4") is False
        assert validate_audio_mime_type("text/plain") is False
        assert validate_audio_mime_type("application/json") is False

    def test_empty_mime_type(self):
        """Test empty MIME type returns False."""
        assert validate_audio_mime_type("") is False

    def test_case_sensitive(self):
        """Test MIME type validation is case-sensitive."""
        assert validate_audio_mime_type("AUDIO/MPEG") is False
        assert validate_audio_mime_type("Audio/Mpeg") is False


class TestGetContentTypeFromExtension:
    """Tests for get_content_type_from_extension function."""

    def test_extension_with_dot(self):
        """Test getting MIME type from extension with dot."""
        assert get_content_type_from_extension(".mp3") == "audio/mpeg"
        assert get_content_type_from_extension(".wav") == "audio/wav"

    def test_extension_without_dot(self):
        """Test getting MIME type from extension without dot."""
        assert get_content_type_from_extension("mp3") == "audio/mpeg"
        assert get_content_type_from_extension("wav") == "audio/wav"

    def test_case_insensitive(self):
        """Test extension lookup is case-insensitive."""
        assert get_content_type_from_extension(".MP3") == "audio/mpeg"
        assert get_content_type_from_extension("WAV") == "audio/wav"

    def test_unknown_extension(self):
        """Test unknown extension returns None."""
        assert get_content_type_from_extension(".xyz") is None
        assert get_content_type_from_extension(".doc") is None


class TestGetSupportedExtensions:
    """Tests for get_supported_extensions function."""

    def test_returns_list(self):
        """Test returns a list."""
        result = get_supported_extensions()
        assert isinstance(result, list)

    def test_contains_common_extensions(self):
        """Test list contains common audio extensions."""
        extensions = get_supported_extensions()
        assert ".mp3" in extensions
        assert ".wav" in extensions
        assert ".ogg" in extensions

    def test_extensions_have_dots(self):
        """Test all extensions include leading dot."""
        extensions = get_supported_extensions()
        for ext in extensions:
            assert ext.startswith(".")


class TestGetSupportedMimeTypes:
    """Tests for get_supported_mime_types function."""

    def test_returns_list(self):
        """Test returns a list."""
        result = get_supported_mime_types()
        assert isinstance(result, list)

    def test_contains_common_mime_types(self):
        """Test list contains common audio MIME types."""
        mime_types = get_supported_mime_types()
        assert "audio/mpeg" in mime_types
        assert "audio/wav" in mime_types

    def test_all_start_with_audio(self):
        """Test all MIME types start with 'audio/'."""
        mime_types = get_supported_mime_types()
        for mime_type in mime_types:
            assert mime_type.startswith("audio/")


class TestEstimateSpeechDuration:
    """Tests for estimate_speech_duration function."""

    def test_empty_text(self):
        """Test empty text returns zero duration."""
        assert estimate_speech_duration("") == 0.0
        assert estimate_speech_duration("   ") == 0.0

    def test_single_word(self):
        """Test single word has non-zero duration."""
        duration = estimate_speech_duration("Hello")
        assert duration > 0

    def test_longer_text_longer_duration(self):
        """Test longer text results in longer duration."""
        short_text = "Hello world"
        long_text = "Hello world " * 10
        assert estimate_speech_duration(long_text) > estimate_speech_duration(
            short_text
        )

    def test_custom_words_per_minute(self):
        """Test custom speaking rate affects duration."""
        text = "word " * 150  # 150 words
        fast_duration = estimate_speech_duration(text, words_per_minute=200)
        slow_duration = estimate_speech_duration(text, words_per_minute=100)
        assert slow_duration > fast_duration

    def test_returns_float(self):
        """Test function returns float."""
        duration = estimate_speech_duration("Hello world")
        assert isinstance(duration, float)


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_seconds_only(self):
        """Test formatting duration with only seconds."""
        assert format_duration(30) == "0:30"
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        """Test formatting duration with minutes and seconds."""
        assert format_duration(90) == "1:30"
        assert format_duration(125) == "2:05"

    def test_hours_minutes_seconds(self):
        """Test formatting duration with hours."""
        assert format_duration(3665) == "1:01:05"
        assert format_duration(7200) == "2:00:00"

    def test_zero_duration(self):
        """Test formatting zero duration."""
        assert format_duration(0) == "0:00"

    def test_padding_zeros(self):
        """Test proper zero padding in output."""
        assert format_duration(65) == "1:05"  # Not "1:5"
        assert format_duration(3605) == "1:00:05"  # Not "1:0:5"


class TestIsAudioFile:
    """Tests for is_audio_file function."""

    def test_valid_audio_files(self):
        """Test recognition of valid audio files."""
        assert is_audio_file("audio.mp3") is True
        assert is_audio_file("recording.wav") is True
        assert is_audio_file("sound.ogg") is True

    def test_invalid_audio_files(self):
        """Test rejection of non-audio files."""
        assert is_audio_file("document.pdf") is False
        assert is_audio_file("video.avi") is False
        assert is_audio_file("image.jpg") is False

    def test_no_extension(self):
        """Test file without extension returns False."""
        assert is_audio_file("audiofile") is False

    def test_case_insensitive(self):
        """Test check is case-insensitive."""
        assert is_audio_file("audio.MP3") is True
        assert is_audio_file("recording.WAV") is True

    def test_path_with_audio_file(self):
        """Test full path with audio file."""
        assert is_audio_file("/path/to/audio.mp3") is True
        assert is_audio_file("folder/recording.wav") is True


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_safe_filename_unchanged(self):
        """Test safe filename remains unchanged."""
        assert sanitize_filename("audio.mp3") == "audio.mp3"
        assert sanitize_filename("recording_01.wav") == "recording_01.wav"

    def test_spaces_replaced(self):
        """Test spaces are replaced with underscores."""
        assert sanitize_filename("my audio.mp3") == "my_audio.mp3"
        assert sanitize_filename("test recording.wav") == "test_recording.wav"

    def test_unsafe_characters_replaced(self):
        """Test unsafe characters are replaced."""
        assert sanitize_filename("audio/file?.mp3") == "audio_file.mp3"
        assert sanitize_filename("test:file|name.wav") == "test_file_name.wav"

    def test_multiple_underscores_collapsed(self):
        """Test multiple consecutive underscores are collapsed."""
        assert sanitize_filename("audio___file.mp3") == "audio_file.mp3"

    def test_leading_trailing_underscores_removed(self):
        """Test leading/trailing underscores are removed."""
        assert sanitize_filename("_audio_.mp3") == "audio.mp3"
        assert sanitize_filename("__file__.wav") == "file.wav"

    def test_preserves_extension(self):
        """Test file extension is preserved."""
        assert sanitize_filename("bad/name?.mp3").endswith(".mp3")
        assert sanitize_filename("test:file.wav").endswith(".wav")

    def test_no_extension(self):
        """Test sanitization works without extension."""
        assert sanitize_filename("bad/filename?") == "bad_filename"


class TestConstants:
    """Tests for audio constants."""

    def test_audio_mime_types_structure(self):
        """Test AUDIO_MIME_TYPES has correct structure."""
        assert isinstance(AUDIO_MIME_TYPES, dict)
        for mime_type, extensions in AUDIO_MIME_TYPES.items():
            assert isinstance(mime_type, str)
            assert isinstance(extensions, list)
            assert all(ext.startswith(".") for ext in extensions)

    def test_extension_to_mime_structure(self):
        """Test EXTENSION_TO_MIME has correct structure."""
        assert isinstance(EXTENSION_TO_MIME, dict)
        for extension, mime_type in EXTENSION_TO_MIME.items():
            assert extension.startswith(".")
            assert isinstance(mime_type, str)
            assert mime_type.startswith("audio/")

    def test_consistency_between_mappings(self):
        """Test consistency between AUDIO_MIME_TYPES and EXTENSION_TO_MIME."""
        # All extensions in EXTENSION_TO_MIME should exist in AUDIO_MIME_TYPES
        for ext, mime in EXTENSION_TO_MIME.items():
            found = False
            for mt, exts in AUDIO_MIME_TYPES.items():
                if ext in exts:
                    found = True
                    break
            assert found, f"Extension {ext} not found in AUDIO_MIME_TYPES"
