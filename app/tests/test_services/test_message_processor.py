from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.message_processor import (
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
