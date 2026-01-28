"""
Enumeration Types

Contains all enum definitions used across the application.
"""

from enum import Enum


class TTSResponseMode(str, Enum):
    """
    Response mode for the TTS endpoint.

    Attributes:
        URL: Return only the signed URL after generation completes
        STREAM: Stream audio chunks directly to the client
        BOTH: Stream audio chunks AND return a signed URL at the end
    """

    URL = "url"
    STREAM = "stream"
    BOTH = "both"


class SpeakerID(int, Enum):
    """
    Available speaker voices for TTS generation.

    Each speaker represents a different language/voice combination
    supported by the TTS service.
    """

    ACHOLI_FEMALE = 241
    ATESO_FEMALE = 242
    RUNYANKORE_FEMALE = 243
    LUGBARA_FEMALE = 245
    SWAHILI_MALE = 246
    LUGANDA_FEMALE = 248

    @property
    def display_name(self) -> str:
        """Get human-readable name for the speaker."""
        return SPEAKER_METADATA.get(self.value, {}).get("display_name", "Unknown")

    @property
    def language(self) -> str:
        """Get the language for this speaker."""
        return SPEAKER_METADATA.get(self.value, {}).get("language", "Unknown")

    @property
    def gender(self) -> str:
        """Get the gender for this speaker."""
        return SPEAKER_METADATA.get(self.value, {}).get("gender", "unknown")


# Speaker metadata lookup table
SPEAKER_METADATA: dict[int, dict[str, str]] = {
    241: {
        "display_name": "Acholi (female)",
        "language": "Acholi",
        "gender": "female",
    },
    242: {
        "display_name": "Ateso (female)",
        "language": "Ateso",
        "gender": "female",
    },
    243: {
        "display_name": "Runyankore (female)",
        "language": "Runyankore",
        "gender": "female",
    },
    245: {
        "display_name": "Lugbara (female)",
        "language": "Lugbara",
        "gender": "female",
    },
    246: {
        "display_name": "Swahili (male)",
        "language": "Swahili",
        "gender": "male",
    },
    248: {
        "display_name": "Luganda (female)",
        "language": "Luganda",
        "gender": "female",
    },
}


def get_all_speakers() -> list[dict]:
    """
    Get all available speakers with their metadata.

    Returns:
        List of speaker dictionaries with id, name, display_name, language, gender
    """
    return [
        {
            "id": speaker.value,
            "name": speaker.name,
            "display_name": speaker.display_name,
            "language": speaker.language,
            "gender": speaker.gender,
        }
        for speaker in SpeakerID
    ]
