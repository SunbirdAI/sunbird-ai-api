"""
TTS API Client Example

This module demonstrates how to use all modes of the TTS API.

Available Speakers:
- ACHOLI_FEMALE (241)
- ATESO_FEMALE (242)
- RUNYANKORE_FEMALE (243)
- LUGBARA_FEMALE (245)
- SWAHILI_MALE (246)
- LUGANDA_FEMALE (248)
"""

import asyncio
import base64
import json
from enum import Enum
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"


class SpeakerID(int, Enum):
    """Available speaker voices (mirrors server enum)."""

    ACHOLI_FEMALE = 241
    ATESO_FEMALE = 242
    RUNYANKORE_FEMALE = 243
    LUGBARA_FEMALE = 245
    SWAHILI_MALE = 246
    LUGANDA_FEMALE = 248


async def list_speakers() -> list[dict]:
    """Fetch available speakers from the API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BASE_URL}/tasks/modal/tts/speakers")
        response.raise_for_status()
        data = response.json()

        print("Available Speakers:")
        for speaker in data["speakers"]:
            print(f"  {speaker['id']}: {speaker['display_name']} ({speaker['name']})")

        return data["speakers"]


async def tts_url_mode(
    text: str,
    speaker_id: SpeakerID = SpeakerID.LUGANDA_FEMALE,
    output_file: str | None = None,
) -> dict:
    """
    Generate TTS and get a signed URL.

    Args:
        text: Text to convert to speech
        speaker_id: Voice/speaker enum
        output_file: Optional path to download the audio to

    Returns:
        API response with signed URL
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{BASE_URL}/tasks/modal/tts",
            json={"text": text, "speaker_id": speaker_id.value, "response_mode": "url"},
        )
        response.raise_for_status()
        data = response.json()

        print(f"✓ Audio generated successfully")
        print(f"  Speaker: {data.get('speaker_name', 'N/A')}")
        print(f"  URL: {data['audio_url'][:80]}...")
        print(f"  Expires: {data['expires_at']}")
        print(f"  File: {data['file_name']}")
        print(f"  Duration estimate: {data.get('duration_estimate_seconds', 'N/A')}s")

        if output_file:
            audio_response = await client.get(data["audio_url"])
            Path(output_file).write_bytes(audio_response.content)
            print(f"  Downloaded to: {output_file}")

        return data


async def tts_stream_mode(
    text: str,
    speaker_id: SpeakerID = SpeakerID.LUGANDA_FEMALE,
    output_file: str = "output_streamed.wav",
) -> int:
    """
    Stream TTS audio and save to file.

    Args:
        text: Text to convert to speech
        speaker_id: Voice/speaker enum
        output_file: Path to save the audio

    Returns:
        Total bytes received
    """
    total_bytes = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/tasks/modal/tts/stream",
            json={"text": text, "speaker_id": speaker_id.value},
        ) as response:
            response.raise_for_status()

            with open(output_file, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    total_bytes += len(chunk)
                    print(
                        f"  Received chunk: {len(chunk):,} bytes (total: {total_bytes:,})"
                    )

    print(f"✓ Stream complete: {total_bytes:,} bytes saved to {output_file}")
    return total_bytes


async def tts_stream_with_url_mode(
    text: str,
    speaker_id: SpeakerID = SpeakerID.LUGANDA_FEMALE,
    output_file: str = "output_sse.wav",
) -> dict:
    """
    Stream TTS audio via SSE and get final URL.

    Args:
        text: Text to convert to speech
        speaker_id: Voice/speaker enum
        output_file: Path to save the audio locally

    Returns:
        Final response with signed URL
    """
    audio_chunks: list[bytes] = []
    final_response = None

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/tasks/modal/tts/stream-with-url",
            json={"text": text, "speaker_id": speaker_id.value},
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                event_data = json.loads(line[6:])
                event_type = event_data.get("event", "")

                if event_type == "audio_chunk":
                    chunk = base64.b64decode(event_data["data"])
                    audio_chunks.append(chunk)
                    print(f"  Chunk received: {event_data['bytes']:,} bytes")

                elif event_type == "complete":
                    final_response = event_data
                    print(f"✓ Stream complete!")
                    print(f"  Total bytes: {event_data['total_bytes']:,}")
                    print(f"  URL: {event_data['audio_url'][:80]}...")
                    print(f"  Expires: {event_data['expires_at']}")

                elif event_type == "error":
                    print(f"✗ Error: {event_data['error']}")
                    raise Exception(event_data["error"])

    if audio_chunks:
        with open(output_file, "wb") as f:
            f.write(b"".join(audio_chunks))
        print(f"  Saved locally to: {output_file}")

    return final_response


async def refresh_url(file_name: str) -> dict:
    """
    Refresh the signed URL for an existing file.

    Args:
        file_name: The file path in GCP Storage

    Returns:
        New signed URL response
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{BASE_URL}/tasks/modal/tts/refresh-url", params={"file_name": file_name}
        )
        response.raise_for_status()
        data = response.json()

        print(f"✓ URL refreshed")
        print(f"  New URL: {data['audio_url'][:80]}...")
        print(f"  Expires: {data['expires_at']}")

        return data


async def main():
    """Run example demonstrations of all TTS modes."""

    sample_text = "I am a nurse who takes care of many people who have cancer."
    long_text = """
    Welcome to our text-to-speech demonstration. This is a longer piece of text
    that showcases the streaming capabilities of our API. When you have large
    amounts of text to convert, streaming allows you to start playing the audio
    immediately while the rest is still being generated.
    """.strip()

    print("=" * 60)
    print("TTS API Client Demo")
    print("=" * 60)

    # List available speakers
    print("\n[0] Available Speakers")
    print("-" * 40)
    await list_speakers()

    # Test URL mode with Luganda speaker
    print("\n[1] URL Mode - Luganda (female)")
    print("-" * 40)
    url_result = await tts_url_mode(
        sample_text,
        speaker_id=SpeakerID.LUGANDA_FEMALE,
        output_file="output_luganda.wav",
    )

    # Test stream mode with Swahili speaker
    print("\n[2] Stream Mode - Swahili (male)")
    print("-" * 40)
    await tts_stream_mode(
        sample_text, speaker_id=SpeakerID.SWAHILI_MALE, output_file="output_swahili.wav"
    )

    # Test stream with URL mode
    print("\n[3] Stream + URL Mode (SSE) - Acholi (female)")
    print("-" * 40)
    await tts_stream_with_url_mode(
        long_text, speaker_id=SpeakerID.ACHOLI_FEMALE, output_file="output_acholi.wav"
    )

    # Test URL refresh
    if url_result and url_result.get("file_name"):
        print("\n[4] Refresh URL")
        print("-" * 40)
        await refresh_url(url_result["file_name"])

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
