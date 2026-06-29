from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.message_processor as mp
from app.services.message_processor import (
    CORRUPTED_OUTPUT_FALLBACK,
    OptimizedMessageProcessor,
    ProcessingResult,
    ResponseType,
    clear_processed_messages,
)


@pytest.fixture
def sample_text_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"profile": {"name": "John"}, "wa_id": "256700000001"}
                            ],
                            "messages": [
                                {
                                    "from": "256700000001",
                                    "id": "wamid.text123",
                                    "text": {"body": "help"},
                                }
                            ],
                            "metadata": {"phone_number_id": "123456789"},
                        }
                    }
                ]
            }
        ]
    }


class TestOptimizedMessageProcessor:
    @pytest.mark.asyncio
    async def test_process_message_passes_lookup_failure_flag_to_text_handler(
        self, sample_text_payload: dict
    ) -> None:
        clear_processed_messages()
        processor = OptimizedMessageProcessor()
        expected_result = ProcessingResult("ok", ResponseType.TEXT)

        with patch(
            "app.services.message_processor.get_user_settings",
            new=AsyncMock(
                return_value={
                    "found": False,
                    "lookup_failed": True,
                    "target_language": None,
                    "mode": None,
                    "tts_enabled": None,
                }
            ),
        ), patch.object(
            processor,
            "_handle_text_optimized",
            new=AsyncMock(return_value=expected_result),
        ) as mock_handle_text:
            result = await processor.process_message(
                payload=sample_text_payload,
                from_number="256700000001",
                sender_name="John",
                target_language="eng",
                phone_number_id="123456789",
            )

        assert result is expected_result
        mock_handle_text.assert_awaited_once()
        assert mock_handle_text.await_args.args[-2:] == (False, True)

    @pytest.mark.asyncio
    async def test_set_default_preference_does_not_overwrite_mode_or_tts(self) -> None:
        processor = OptimizedMessageProcessor()

        with patch(
            "app.services.message_processor.save_user_preference", new=AsyncMock()
        ) as mock_save_preference:
            await processor._set_default_preference_async("256700000001")

        mock_save_preference.assert_awaited_once_with("256700000001", "English", "eng")

    @pytest.mark.asyncio
    async def test_quick_command_carries_user_message_for_router_persistence(
        self, sample_text_payload: dict
    ) -> None:
        processor = OptimizedMessageProcessor()

        with patch(
            "app.services.message_processor.asyncio.create_task",
            return_value=MagicMock(),
        ), patch.object(
            processor,
            "_handle_quick_commands",
            new=AsyncMock(
                return_value=ProcessingResult("Help text", ResponseType.TEXT)
            ),
        ):
            result = await processor._handle_text_optimized(
                payload=sample_text_payload,
                target_language="eng",
                from_number="256700000001",
                sender_name="John",
                user_mode="chat",
                tts_enabled=False,
                is_new_user=False,
                lookup_failed=False,
            )

        assert result.user_message == "help"


class TestSunflowerOutputSafety:
    """Phase 1: endpoint-independent output safety guards (no max_tokens)."""

    def _proc(self) -> OptimizedMessageProcessor:
        return OptimizedMessageProcessor()

    def test_glued_role_tokens_replaced_with_fallback(self) -> None:
        proc = self._proc()
        out = proc._clean_response(
            {"content": "assistantuserassistantassistantassistantassistant"}
        )
        assert out == CORRUPTED_OUTPUT_FALLBACK

    def test_translateuser_replaced_with_fallback(self) -> None:
        proc = self._proc()
        assert proc._clean_response({"content": "Translateuser"}) == (
            CORRUPTED_OUTPUT_FALLBACK
        )
        assert proc._clean_response({"content": "Translateassistantuser"}) == (
            CORRUPTED_OUTPUT_FALLBACK
        )

    def test_special_tokens_removed(self) -> None:
        proc = self._proc()
        out = proc._clean_response(
            {"content": "<|im_start|>assistant Hello there<|im_end|>"}
        )
        # Special tokens stripped; usable text salvaged.
        assert "<|" not in out
        assert "im_start" not in out
        assert "Hello there" in out

    def test_legitimate_text_with_user_assistant_preserved(self) -> None:
        proc = self._proc()
        text = "The user asked the assistant to summarise the system design."
        assert proc._clean_response({"content": text}) == text

    def test_empty_content_returns_fallback(self) -> None:
        proc = self._proc()
        assert proc._clean_response({"content": "   "}) == CORRUPTED_OUTPUT_FALLBACK
        assert proc._clean_response({}) == CORRUPTED_OUTPUT_FALLBACK

    def test_repeated_greeting_flagged(self) -> None:
        proc = self._proc()
        assert proc._clean_response({"content": "Hello! 🌻 " * 40}) == (
            CORRUPTED_OUTPUT_FALLBACK
        )

    def test_repeated_emoji_flagged(self) -> None:
        proc = self._proc()
        assert proc._clean_response({"content": "🌍" * 60}) == (
            CORRUPTED_OUTPUT_FALLBACK
        )

    def test_repeated_role_label_lines_flagged(self) -> None:
        proc = self._proc()
        assert proc._clean_response({"content": "assistant\n" * 30}) == (
            CORRUPTED_OUTPUT_FALLBACK
        )

    def test_long_output_capped(self) -> None:
        proc = self._proc()
        long_text = "A unique clause number {}. ".format
        content = " ".join(long_text(i) for i in range(2000))
        out = proc._clean_response({"content": content})
        assert len(out) <= 3501  # WHATSAPP_MAX_RESPONSE_CHARS + ellipsis
        assert out.endswith("…")

    def test_normal_short_answer_unchanged(self) -> None:
        proc = self._proc()
        text = "The meeting starts at 8am tomorrow."
        assert proc._clean_response({"content": text}) == text


class TestSunflowerInputGuards:
    def test_low_value_inputs(self) -> None:
        proc = OptimizedMessageProcessor()
        assert proc._is_low_value_input("") is True
        assert proc._is_low_value_input("    ") is True
        assert proc._is_low_value_input("%%%%%%") is True
        assert proc._is_low_value_input("😀😀😀") is True
        assert proc._is_low_value_input("a") is True

    def test_real_inputs_pass(self) -> None:
        proc = OptimizedMessageProcessor()
        assert proc._is_low_value_input("hello there") is False
        assert proc._is_low_value_input("Oli otya") is False
        assert proc._is_low_value_input("Translate this") is False


class TestSunflowerGreetingsAndCommands:
    async def _cmd(self, text: str, mode: str = "chat"):
        proc = OptimizedMessageProcessor()
        with patch("app.services.message_processor.save_user_mode", new=AsyncMock()):
            return await proc._handle_quick_commands(
                input_text=text,
                target_language="eng",
                sender_name="John",
                from_number="256700000001",
                user_mode=mode,
                tts_enabled=False,
                is_new_user=False,
            )

    @pytest.mark.asyncio
    async def test_english_greetings_deterministic(self) -> None:
        for g in ["hello", "hi", "hey", "Good Morning", "good evening"]:
            res = await self._cmd(g)
            assert res is not None
            assert res.response_type == ResponseType.TEXT
            assert "Sunflower" in res.message

    @pytest.mark.asyncio
    async def test_luganda_greetings_deterministic(self) -> None:
        for g in ["wasuze otya", "oli otya", "ssebo", "nyabo"]:
            res = await self._cmd(g)
            assert res is not None
            assert res.response_type == ResponseType.TEXT

    @pytest.mark.asyncio
    async def test_navigation_commands(self) -> None:
        for c in ["menu", "start", "start over", "cancel", "help"]:
            res = await self._cmd(c)
            assert res is not None
            assert res.response_type in (ResponseType.TEXT, ResponseType.BUTTON)

    @pytest.mark.asyncio
    async def test_cancel_resets_mode_to_chat(self) -> None:
        proc = OptimizedMessageProcessor()
        with patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ) as mock_save:
            res = await proc._handle_quick_commands(
                input_text="cancel",
                target_language="eng",
                sender_name="John",
                from_number="256700000001",
                user_mode="translate",
                tts_enabled=False,
            )
        assert res is not None
        mock_save.assert_awaited_once_with("256700000001", "chat")


class TestTTSBackendSelection:
    """Phase 2: WhatsApp TTS backend flag + Orpheus path."""

    @pytest.mark.asyncio
    async def test_spark_backend_uses_spark_service(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "spark")
        spark = MagicMock()
        spark.generate_audio = AsyncMock(return_value=b"WAV-SPARK")
        monkeypatch.setattr(mp, "get_tts_service", lambda: spark)
        orpheus_called = MagicMock()
        monkeypatch.setattr(
            proc, "_generate_orpheus_wav_bytes", AsyncMock(side_effect=orpheus_called)
        )

        out = await proc._generate_tts_wav_bytes("hello", "lug")

        assert out == b"WAV-SPARK"
        spark.generate_audio.assert_awaited_once()
        orpheus_called.assert_not_called()

    @pytest.mark.asyncio
    async def test_orpheus_backend_uses_orpheus(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "orpheus")
        monkeypatch.setattr(
            proc, "_generate_orpheus_wav_bytes", AsyncMock(return_value=b"WAV-ORPHEUS")
        )

        out = await proc._generate_tts_wav_bytes("hello", "lug")

        assert out == b"WAV-ORPHEUS"

    @pytest.mark.asyncio
    async def test_unknown_backend_falls_back_to_spark(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "weird")
        spark = MagicMock()
        spark.generate_audio = AsyncMock(return_value=b"WAV")
        monkeypatch.setattr(mp, "get_tts_service", lambda: spark)

        out = await proc._generate_tts_wav_bytes("hi", "eng")

        assert out == b"WAV"
        spark.generate_audio.assert_awaited_once()


class TestOrpheusRequestAndSpeakerMapping:
    @pytest.mark.asyncio
    async def test_orpheus_request_passes_text_speaker_language(
        self, monkeypatch
    ) -> None:
        proc = OptimizedMessageProcessor()
        service = MagicMock()
        result = MagicMock()
        result.audio_url = "https://signed.example/a.wav"
        service.synthesize = AsyncMock(return_value=result)
        monkeypatch.setattr(mp, "get_orpheus_tts_service", lambda: service)
        monkeypatch.setattr(
            proc, "_resolve_orpheus_speaker", AsyncMock(return_value=("sp_lug", "lug"))
        )
        monkeypatch.setattr(
            proc, "_download_audio_bytes", AsyncMock(return_value=b"WAVBYTES")
        )

        out = await proc._generate_orpheus_wav_bytes("Hello", "lug")

        assert out == b"WAVBYTES"
        kwargs = service.synthesize.await_args.kwargs
        assert kwargs["text"] == "Hello"
        assert kwargs["speaker_id"] == "sp_lug"
        assert isinstance(kwargs["speaker_id"], str)
        assert kwargs["language"] == "lug"
        # WAV URL is downloaded, never returned for direct WhatsApp link send.
        proc._download_audio_bytes.assert_awaited_once_with(
            "https://signed.example/a.wav"
        )

    @pytest.mark.asyncio
    async def test_configured_speaker_used(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(
            mp.settings, "whatsapp_orpheus_speakers", {"lug": "cfg_lug"}
        )
        service = MagicMock()
        service.list_speakers = AsyncMock()
        speaker, lang = await proc._resolve_orpheus_speaker(service, "Luganda")
        assert speaker == "cfg_lug"
        assert lang == "lug"
        service.list_speakers.assert_not_called()

    @pytest.mark.asyncio
    async def test_catalog_by_language_selected(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_orpheus_speakers", {})
        catalog = MagicMock()
        catalog.by_language = {"eng": ["sp_eng_1", "sp_eng_2"]}
        catalog.default = "sp_default"
        service = MagicMock()
        service.list_speakers = AsyncMock(return_value=catalog)
        speaker, lang = await proc._resolve_orpheus_speaker(service, "eng")
        assert speaker == "sp_eng_1"
        assert lang == "eng"

    @pytest.mark.asyncio
    async def test_unsupported_language_falls_back_to_default(
        self, monkeypatch
    ) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_orpheus_speakers", {})
        catalog = MagicMock()
        catalog.by_language = {"eng": ["sp_eng"]}
        catalog.default = "sp_default"
        service = MagicMock()
        service.list_speakers = AsyncMock(return_value=catalog)
        speaker, lang = await proc._resolve_orpheus_speaker(service, "xyz")
        assert speaker == "sp_default"
        assert lang is None

    @pytest.mark.asyncio
    async def test_catalog_unavailable_uses_configured_default(
        self, monkeypatch
    ) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_orpheus_speakers", {})
        monkeypatch.setattr(
            mp.settings, "whatsapp_orpheus_default_speaker", "env_default"
        )
        service = MagicMock()
        service.list_speakers = AsyncMock(side_effect=RuntimeError("catalog down"))
        speaker, lang = await proc._resolve_orpheus_speaker(service, "lug")
        assert speaker == "env_default"
        assert lang is None

    @pytest.mark.asyncio
    async def test_no_speaker_anywhere_raises(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_orpheus_speakers", {})
        monkeypatch.setattr(mp.settings, "whatsapp_orpheus_default_speaker", None)
        service = MagicMock()
        service.list_speakers = AsyncMock(side_effect=RuntimeError("down"))
        with pytest.raises(RuntimeError):
            await proc._resolve_orpheus_speaker(service, "lug")


class TestOrpheusAudioDelivery:
    @pytest.mark.asyncio
    async def test_wav_converted_and_uploaded_not_sent_by_link(
        self, monkeypatch
    ) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "orpheus")
        monkeypatch.setattr(
            proc, "_generate_orpheus_wav_bytes", AsyncMock(return_value=b"WAVDATA")
        )
        segment = MagicMock()
        monkeypatch.setattr(
            mp.AudioSegment, "from_file", MagicMock(return_value=segment)
        )
        ws = MagicMock()
        ws.upload_media.return_value = {"id": "MEDIA-123"}
        ws.send_audio.return_value = {}
        monkeypatch.setattr(mp, "whatsapp_service", ws)

        await proc.send_tts_audio_response("Hello there", "lug", "256700000001", "PNID")

        ws.upload_media.assert_called_once()
        ws.send_audio.assert_called_once()
        send_kwargs = ws.send_audio.call_args.kwargs
        assert send_kwargs["link"] is False
        assert send_kwargs["audio"] == "MEDIA-123"

    @pytest.mark.asyncio
    async def test_orpheus_failure_sends_friendly_fallback(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "orpheus")
        monkeypatch.setattr(
            proc,
            "_generate_orpheus_wav_bytes",
            AsyncMock(side_effect=RuntimeError("orpheus boom")),
        )
        monkeypatch.setattr(mp.asyncio, "sleep", AsyncMock())
        ws = MagicMock()
        monkeypatch.setattr(mp, "whatsapp_service", ws)

        await proc.send_tts_audio_response("Hi", "lug", "256700000001", "PNID")

        # A friendly text fallback is sent; no raw error/tokens, not silent.
        assert ws.send_message.called
        sent = " ".join(
            str(c.kwargs.get("message", "")) for c in ws.send_message.call_args_list
        )
        assert "orpheus boom" not in sent
        assert "voice reply" in sent.lower() or "voice" in sent.lower()


class TestExplicitTTSCommands:
    async def _cmd(self, text: str):
        proc = OptimizedMessageProcessor()
        with patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ), patch(
            "app.services.message_processor.save_user_tts_enabled", new=AsyncMock()
        ):
            return await proc._handle_quick_commands(
                input_text=text,
                target_language="eng",
                sender_name="John",
                from_number="256700000001",
                user_mode="chat",
                tts_enabled=False,
            )

    @pytest.mark.asyncio
    async def test_speak_routes_to_tts(self) -> None:
        res = await self._cmd("speak hello there")
        assert res is not None
        assert res.send_tts is True
        assert res.message == "hello there"

    @pytest.mark.asyncio
    async def test_voice_text_routes_to_tts(self) -> None:
        res = await self._cmd("voice good morning")
        assert res is not None and res.send_tts is True
        assert res.message == "good morning"

    @pytest.mark.asyncio
    async def test_change_name_to_speech_routes_to_tts(self) -> None:
        res = await self._cmd("change Ssemuli Joseph to speech")
        assert res is not None and res.send_tts is True
        assert res.message == "Ssemuli Joseph"

    @pytest.mark.asyncio
    async def test_change_number_to_speech_routes_to_tts(self) -> None:
        res = await self._cmd("change 0772123456 to speech")
        assert res is not None and res.send_tts is True
        assert res.message == "0772123456"

    @pytest.mark.asyncio
    async def test_missing_text_asks_user(self) -> None:
        res = await self._cmd("speak")
        assert res is not None
        assert res.send_tts is False
        assert "what would you like me to say" in res.message.lower()

    @pytest.mark.asyncio
    async def test_voice_on_still_toggles_not_tts(self) -> None:
        res = await self._cmd("voice on")
        assert res is not None
        assert res.send_tts is False
        assert "ON" in res.message

    @pytest.mark.asyncio
    async def test_explicit_tts_does_not_call_sunflower(self) -> None:
        proc = OptimizedMessageProcessor()
        with patch.object(
            proc, "_call_sunflower", new=AsyncMock()
        ) as mock_model, patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ):
            res = await proc._handle_quick_commands(
                input_text="change 0772123456 to speech",
                target_language="eng",
                sender_name="John",
                from_number="256700000001",
                user_mode="chat",
                tts_enabled=False,
            )
        assert res is not None and res.send_tts is True
        mock_model.assert_not_called()
