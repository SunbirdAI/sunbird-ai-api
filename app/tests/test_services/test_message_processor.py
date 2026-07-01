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
            # Greeting guides the user to the menu / core capabilities.
            assert "menu" in res.message.lower()

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


class TestOrpheusViaSpeechService:
    """2A: WhatsApp Orpheus path reuses the shared SpeechService."""

    def _patch_speech_service(self, monkeypatch, audio_url="https://signed/a.wav"):
        service = MagicMock()
        result = MagicMock()
        result.audio_url = audio_url
        service.validate_request = MagicMock()
        service.synthesize = AsyncMock(return_value=result)
        monkeypatch.setattr(mp, "get_speech_service", lambda: service)
        return service

    @pytest.mark.asyncio
    async def test_orpheus_uses_speech_service_request(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        service = self._patch_speech_service(monkeypatch)
        monkeypatch.setattr(
            proc, "_download_audio_bytes", AsyncMock(return_value=b"WAVBYTES")
        )

        out = await proc._generate_orpheus_wav_bytes("Hello", "lug")

        assert out == b"WAVBYTES"
        # validate_request was run and synthesize received a SpeechRequest.
        service.validate_request.assert_called_once()
        req = service.synthesize.await_args.args[0]
        assert req.text == "Hello"
        assert req.model == mp.TTSModel.orpheus_3b_tts
        assert req.platform == mp.TTSPlatform.modal
        assert req.language == "lug"
        # WhatsApp never sends a blind voice: SpeechService picks per language.
        assert req.voice is None
        # WAV URL is downloaded, never returned for direct WhatsApp link send.
        proc._download_audio_bytes.assert_awaited_once_with("https://signed/a.wav")

    @pytest.mark.asyncio
    async def test_voice_is_none_for_language_aware_selection(
        self, monkeypatch
    ) -> None:
        """WhatsApp passes voice=None so SpeechService selects by language
        (English never gets the Luganda default)."""
        proc = OptimizedMessageProcessor()
        service = self._patch_speech_service(monkeypatch)
        monkeypatch.setattr(
            proc, "_download_audio_bytes", AsyncMock(return_value=b"WAV")
        )

        await proc._generate_orpheus_wav_bytes("Hi", "eng")

        req = service.synthesize.await_args.args[0]
        assert req.voice is None
        assert req.language == "eng"

    @pytest.mark.asyncio
    async def test_language_codes_propagated(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        service = self._patch_speech_service(monkeypatch)
        monkeypatch.setattr(
            proc, "_download_audio_bytes", AsyncMock(return_value=b"WAV")
        )
        for given, expected in [
            ("eng", "eng"),
            ("English", "eng"),
            ("lug", "lug"),
            ("Acholi", "ach"),
        ]:
            await proc._generate_orpheus_wav_bytes("Hi", given)
            req = service.synthesize.await_args.args[0]
            assert req.language == expected


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


class TestTTSMode:
    """2B: persistent TTS task mode."""

    async def _cmd(self, text: str, mode: str = "chat"):
        proc = OptimizedMessageProcessor()
        with patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ) as mock_save:
            res = await proc._handle_quick_commands(
                input_text=text,
                target_language="eng",
                sender_name="John",
                from_number="256700000001",
                user_mode=mode,
                tts_enabled=False,
            )
        return res, mock_save

    @pytest.mark.asyncio
    async def test_enter_tts_mode(self) -> None:
        for cmd in ["mode tts", "tts mode", "set mode tts", "speak mode"]:
            res, mock_save = await self._cmd(cmd)
            assert res is not None
            assert res.response_type == ResponseType.TEXT
            assert "TTS mode" in res.message
            mock_save.assert_awaited_once_with("256700000001", "tts")

    @pytest.mark.asyncio
    async def test_text_in_tts_mode_routes_to_tts_not_sunflower(self) -> None:
        proc = OptimizedMessageProcessor()
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "256700000001",
                                        "id": "wamid.x",
                                        "text": {"body": "Welcome to Sunbird AI"},
                                    }
                                ],
                                "metadata": {"phone_number_id": "PNID"},
                            }
                        }
                    ]
                }
            ]
        }
        with patch(
            "app.services.message_processor.asyncio.create_task",
            return_value=MagicMock(),
        ), patch.object(proc, "_call_sunflower", new=AsyncMock()) as mock_model:
            result = await proc._handle_text_optimized(
                payload=payload,
                target_language="eng",
                from_number="256700000001",
                sender_name="John",
                user_mode="tts",
                tts_enabled=False,
                is_new_user=False,
                lookup_failed=False,
            )

        assert result.message == "Welcome to Sunbird AI"
        assert result.send_tts is True
        mock_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_and_mode_chat_exit_tts(self) -> None:
        res_cancel, save_cancel = await self._cmd("cancel", mode="tts")
        assert res_cancel is not None
        save_cancel.assert_awaited_once_with("256700000001", "chat")

        res_chat, save_chat = await self._cmd("mode chat", mode="tts")
        assert res_chat is not None
        save_chat.assert_awaited_once_with("256700000001", "chat")

    @pytest.mark.asyncio
    async def test_tts_added_to_valid_modes(self) -> None:
        proc = OptimizedMessageProcessor()
        assert "tts" in proc.valid_modes
        assert proc._normalize_mode("tts") == "tts"


class TestReplyContext:
    """2C: best-effort WhatsApp reply context threading."""

    @pytest.mark.asyncio
    async def test_process_message_sets_reply_to_message_id(self) -> None:
        clear_processed_messages()
        proc = OptimizedMessageProcessor()
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "256700000001",
                                        "id": "wamid.INBOUND",
                                        "text": {"body": "hello"},
                                    }
                                ],
                                "metadata": {"phone_number_id": "PNID"},
                            }
                        }
                    ]
                }
            ]
        }
        with patch(
            "app.services.message_processor.get_user_settings",
            new=AsyncMock(
                return_value={
                    "found": True,
                    "lookup_failed": False,
                    "target_language": "eng",
                    "mode": "chat",
                    "tts_enabled": False,
                }
            ),
        ), patch(
            "app.services.message_processor.asyncio.create_task",
            return_value=MagicMock(),
        ):
            result = await proc.process_message(
                payload=payload,
                from_number="256700000001",
                sender_name="John",
                target_language="eng",
                phone_number_id="PNID",
            )

        assert result.reply_to_message_id == "wamid.INBOUND"

    @pytest.mark.asyncio
    async def test_tts_audio_replies_to_context_message(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_tts_backend", "orpheus")
        monkeypatch.setattr(
            proc, "_generate_orpheus_wav_bytes", AsyncMock(return_value=b"WAV")
        )
        monkeypatch.setattr(
            mp.AudioSegment, "from_file", MagicMock(return_value=MagicMock())
        )
        ws = MagicMock()
        ws.upload_media.return_value = {"id": "MID"}
        ws.send_audio.return_value = {}
        monkeypatch.setattr(mp, "whatsapp_service", ws)

        await proc.send_tts_audio_response(
            "Hello", "lug", "256700000001", "PNID", context_message_id="wamid.IN"
        )

        assert ws.send_audio.call_args.kwargs["context_message_id"] == "wamid.IN"

    @pytest.mark.asyncio
    async def test_asr_failure_replies_to_audio_message(self, monkeypatch) -> None:
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.asyncio, "sleep", AsyncMock())
        ws = MagicMock()
        monkeypatch.setattr(mp, "whatsapp_service", ws)

        endpoint = MagicMock()
        endpoint.run_sync.side_effect = RuntimeError("asr down")

        out = await proc._run_asr_with_retry(
            endpoint=endpoint,
            transcription_data={"input": {}},
            from_number="256700000001",
            phone_number_id="PNID",
            context_message_id="wamid.AUDIO",
        )

        assert out is None
        # Every notice replied to the original audio message.
        assert ws.send_message.call_count >= 1
        for call in ws.send_message.call_args_list:
            assert call.kwargs.get("context_message_id") == "wamid.AUDIO"


class TestHelpAndDiscoveryText:
    """2D: help/menu/mode/voice/status text surfaces TTS features."""

    async def _cmd(self, text: str, mode: str = "chat", tts_enabled: bool = False):
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
                user_mode=mode,
                tts_enabled=tts_enabled,
            )

    @pytest.mark.asyncio
    async def test_help_mentions_tts_mode_and_oneoff_examples(self) -> None:
        res = await self._cmd("help")
        msg = res.message
        assert "mode tts" in msg
        assert "speak Welcome to Sunbird AI" in msg
        assert "change Welcome to Sunbird AI to speech" in msg
        assert "voice on" in msg and "voice off" in msg
        assert "cancel" in msg and "menu" in msg
        for m in ("mode chat", "mode translate", "mode transcribe"):
            assert m in msg

    @pytest.mark.asyncio
    async def test_menu_mentions_speak_mode(self) -> None:
        res = await self._cmd("menu")
        msg = res.message.lower()
        assert "mode tts" in msg or "speak" in msg

    @pytest.mark.asyncio
    async def test_mode_list_includes_all_four_modes(self) -> None:
        res = await self._cmd("mode")
        assert res.response_type == ResponseType.BUTTON
        # List message (not reply buttons): all four modes are selectable rows.
        rows = res.button_data["action"]["sections"][0]["rows"]
        row_ids = {r["id"] for r in rows}
        assert row_ids == {
            "mode_chat",
            "mode_translate",
            "mode_transcribe",
            "mode_tts",
        }
        titles = " ".join(r["title"] for r in rows).lower()
        assert "speak" in titles or "tts" in titles
        # Not a reply-button payload (reply buttons cap at 3).
        assert "interactive_type" not in res.button_data

    @pytest.mark.asyncio
    async def test_modes_alias_opens_mode_buttons(self) -> None:
        res = await self._cmd("modes")
        assert res is not None
        assert res.response_type == ResponseType.BUTTON

    @pytest.mark.asyncio
    async def test_mode_tts_activates_tts_mode(self) -> None:
        res = await self._cmd("mode tts")
        assert res.response_type == ResponseType.TEXT
        assert "TTS mode" in res.message

    @pytest.mark.asyncio
    async def test_voice_alone_explains_replies_and_oneoff(self) -> None:
        res = await self._cmd("voice")
        assert res.response_type == ResponseType.TEXT
        msg = res.message.lower()
        assert "voice on" in msg and "voice off" in msg
        assert "voice <your text>" in msg or "voice welcome" in msg
        assert "mode tts" in msg

    @pytest.mark.asyncio
    async def test_voice_on_still_toggles(self) -> None:
        res = await self._cmd("voice on")
        assert res.response_type == ResponseType.TEXT
        assert "ON" in res.message
        assert res.send_tts is False

    @pytest.mark.asyncio
    async def test_voice_off_still_toggles(self) -> None:
        res = await self._cmd("voice off")
        assert res.response_type == ResponseType.TEXT
        assert "OFF" in res.message
        assert res.send_tts is False

    @pytest.mark.asyncio
    async def test_voice_hello_routes_to_tts(self) -> None:
        res = await self._cmd("voice hello")
        assert res.send_tts is True
        assert res.message == "hello"

    def test_status_shows_tts_mode(self) -> None:
        proc = OptimizedMessageProcessor()
        text = proc._get_status_text("eng", "John", "tts", False)
        assert "Speak (TTS)" in text
        assert "mode" in text.lower()

    def test_status_shows_voice_replies_state(self) -> None:
        proc = OptimizedMessageProcessor()
        on = proc._get_status_text("lug", "John", "chat", True)
        off = proc._get_status_text("lug", "John", "chat", False)
        assert "ON" in on
        assert "OFF" in off


class TestModeSelectorList:
    """2F: mode selector uses a list message with a selectable Speak/TTS row."""

    def test_mode_list_builder_has_four_rows_within_limits(self) -> None:
        proc = OptimizedMessageProcessor()
        button = proc.create_mode_selection_list_button("chat")
        rows = button["action"]["sections"][0]["rows"]
        assert len(rows) == 4
        # WhatsApp list row constraints: title <= 24, description <= 72.
        for r in rows:
            assert len(r["title"]) <= 24
            assert len(r.get("description", "")) <= 72
        assert {r["id"] for r in rows} == {
            "mode_chat",
            "mode_translate",
            "mode_transcribe",
            "mode_tts",
        }

    async def _select_row(self, row_id: str, title: str = ""):
        proc = OptimizedMessageProcessor()
        with patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ) as mock_save:
            res = await proc._handle_list_reply(
                {"id": row_id, "title": title}, "256700000001", "John"
            )
        return res, mock_save

    @pytest.mark.asyncio
    async def test_select_speak_sets_tts_mode(self) -> None:
        res, mock_save = await self._select_row("mode_tts", "Speak / TTS")
        mock_save.assert_awaited_once_with("256700000001", "tts")
        assert "TTS mode is active" in res.message

    @pytest.mark.asyncio
    async def test_select_chat_translate_transcribe(self) -> None:
        for row_id, mode in [
            ("mode_chat", "chat"),
            ("mode_translate", "translate"),
            ("mode_transcribe", "transcribe"),
        ]:
            res, mock_save = await self._select_row(row_id)
            mock_save.assert_awaited_once_with("256700000001", mode)
            assert res.response_type == ResponseType.TEXT

    @pytest.mark.asyncio
    async def test_legacy_button_reply_speak_still_works(self) -> None:
        """Any in-flight 3-button message tapping mode_tts still works."""
        proc = OptimizedMessageProcessor()
        with patch(
            "app.services.message_processor.save_user_mode", new=AsyncMock()
        ) as mock_save:
            res = await proc._handle_button_reply(
                {"id": "mode_tts", "title": "Speak"}, "256700000001", "John"
            )
        mock_save.assert_awaited_once_with("256700000001", "tts")
        assert "TTS mode is active" in res.message


class TestInboundDedupReverted:
    """P0 hotfix: Phase 3A DB dedup reverted; in-memory dedup restored.

    Regression guards: one response per message, no fallback on success, and
    the DB dedup path is fully de-wired from process_message (so the env flag
    cannot re-trigger it).
    """

    def _payload(self, message_id="wamid.DUP1"):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "256700000001",
                                        "id": message_id,
                                        "text": {"body": "hello"},
                                    }
                                ],
                                "metadata": {"phone_number_id": "PNID"},
                            }
                        }
                    ]
                }
            ]
        }

    def _patch_common(self, monkeypatch):
        monkeypatch.setattr(
            mp,
            "get_user_settings",
            AsyncMock(
                return_value={
                    "found": True,
                    "lookup_failed": False,
                    "target_language": "eng",
                    "mode": "chat",
                    "tts_enabled": False,
                }
            ),
        )
        monkeypatch.setattr(
            "app.services.message_processor.asyncio.create_task",
            lambda *a, **k: MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_single_response_no_fallback_on_success(self, monkeypatch) -> None:
        clear_processed_messages()
        proc = OptimizedMessageProcessor()
        self._patch_common(monkeypatch)
        monkeypatch.setattr(
            proc,
            "_handle_text_optimized",
            AsyncMock(return_value=ProcessingResult("Real answer", ResponseType.TEXT)),
        )
        result = await proc.process_message(
            self._payload(), "256700000001", "John", "eng", "PNID"
        )
        assert result.response_type == ResponseType.TEXT
        assert result.message == "Real answer"
        # The success path must NOT emit the corruption fallback.
        assert result.message != CORRUPTED_OUTPUT_FALLBACK

    @pytest.mark.asyncio
    async def test_duplicate_message_id_skips_silently(self, monkeypatch) -> None:
        clear_processed_messages()
        proc = OptimizedMessageProcessor()
        self._patch_common(monkeypatch)
        monkeypatch.setattr(
            proc,
            "_handle_text_optimized",
            AsyncMock(return_value=ProcessingResult("Real answer", ResponseType.TEXT)),
        )
        r1 = await proc.process_message(
            self._payload(), "256700000001", "John", "eng", "PNID"
        )
        r2 = await proc.process_message(
            self._payload(), "256700000001", "John", "eng", "PNID"
        )
        assert r1.response_type == ResponseType.TEXT
        # Duplicate delivery -> SKIP (empty), never a second/fallback message.
        assert r2.response_type == ResponseType.SKIP
        assert r2.message == ""

    @pytest.mark.asyncio
    async def test_dedup_flag_db_does_not_change_behavior(self, monkeypatch) -> None:
        """Even if WHATSAPP_DEDUP_BACKEND=db is set, the request path stays
        in-memory (DB dedup fully de-wired) — no DB calls, same dedup result."""
        clear_processed_messages()
        proc = OptimizedMessageProcessor()
        monkeypatch.setattr(mp.settings, "whatsapp_dedup_backend", "db")
        self._patch_common(monkeypatch)
        monkeypatch.setattr(
            proc,
            "_handle_text_optimized",
            AsyncMock(return_value=ProcessingResult("Real answer", ResponseType.TEXT)),
        )
        r1 = await proc.process_message(
            self._payload("wamid.DBFLAG"), "256700000001", "John", "eng", "PNID"
        )
        r2 = await proc.process_message(
            self._payload("wamid.DBFLAG"), "256700000001", "John", "eng", "PNID"
        )
        assert r1.response_type == ResponseType.TEXT
        assert r2.response_type == ResponseType.SKIP

    def test_db_dedup_path_is_removed_from_processor(self) -> None:
        """Regression guard: the DB dedup wiring is no longer in the hot path."""
        proc = OptimizedMessageProcessor()
        assert not hasattr(proc, "_claim_inbound")
        assert not hasattr(proc, "_finalize_inbound")
        # The store dedup helpers are not imported into the processor module.
        assert not hasattr(mp, "claim_inbound_message")
        assert not hasattr(mp, "finalize_inbound_message")
