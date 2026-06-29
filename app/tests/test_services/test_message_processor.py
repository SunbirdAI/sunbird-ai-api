from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
