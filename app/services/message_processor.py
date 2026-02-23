"""
WhatsApp Message Processor Service.

This module contains the OptimizedMessageProcessor class for handling
WhatsApp messages with optimized processing paths for text, audio,
and interactive messages.

Architecture:
    The processor integrates with multiple services:
    - WhatsApp API for sending/receiving messages
    - RunPod for audio transcription
    - UG40 inference for language model responses
    - User preference storage for personalization

Usage:
    from app.services.message_processor import (
        OptimizedMessageProcessor,
        MessageType,
        ResponseType,
        ProcessingResult,
    )

    processor = OptimizedMessageProcessor()
    result = await processor.process_message(
        payload, from_number, sender_name, target_language, phone_number_id
    )

Note:
    This module was consolidated from app/inference_services/OptimizedMessageProcessor.py
    as part of the services layer refactoring.
"""

import asyncio
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set

import runpod
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from app.integrations.whatsapp_store import (
    get_user_conversation_pairs,
    get_user_memory_note,
    get_user_mode,
    get_user_preference,
    get_user_tts_enabled,
    save_detailed_feedback,
    save_feedback_with_context,
    save_message,
    save_response,
    save_user_mode,
    save_user_preference,
    save_user_tts_enabled,
    upsert_user_memory_note,
    update_feedback,
)
from app.models.enums import SpeakerID
from app.services.inference_service import run_inference
from app.services.tts_service import get_tts_service
from app.services.whatsapp_service import get_whatsapp_service
from app.utils.upload_audio_file_gcp import delete_audio_file, upload_audio_file

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Configuration
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")
WHATSAPP_TTS_ENABLED = os.getenv("WHATSAPP_TTS_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WHATSAPP_TTS_MAX_CHARS = int(os.getenv("WHATSAPP_TTS_MAX_CHARS", "600"))
WHATSAPP_ASR_TIMEOUT_SECONDS = int(os.getenv("WHATSAPP_ASR_TIMEOUT_SECONDS", "150"))
WHATSAPP_ASR_RETRY_TIMEOUT_SECONDS = int(
    os.getenv("WHATSAPP_ASR_RETRY_TIMEOUT_SECONDS", "240")
)
WHATSAPP_RETRY_DELAY_SECONDS = float(os.getenv("WHATSAPP_RETRY_DELAY_SECONDS", "2"))

# Initialize services
whatsapp_service = get_whatsapp_service()
processed_messages: Set[str] = set()


class MessageType(Enum):
    """Enum representing different WhatsApp message types.

    Attributes:
        TEXT: Plain text messages.
        AUDIO: Voice/audio messages.
        UNSUPPORTED: Message types not currently supported (images, videos, etc.).
        REACTION: Emoji reactions to messages.
        INTERACTIVE: Interactive button/list responses.
    """

    TEXT = "text"
    AUDIO = "audio"
    UNSUPPORTED = "unsupported"
    REACTION = "reaction"
    INTERACTIVE = "interactive"


class ResponseType(Enum):
    """Enum representing different response types.

    Attributes:
        TEXT: Plain text response.
        TEMPLATE: Template-based response (welcome, feedback, etc.).
        BUTTON: Interactive button response.
        SKIP: No response needed (e.g., duplicate message).
    """

    TEXT = "text"
    TEMPLATE = "template"
    BUTTON = "button"
    SKIP = "skip"


@dataclass
class ProcessingResult:
    """Result of processing a WhatsApp message.

    Attributes:
        message: The response message text.
        response_type: Type of response to send.
        template_name: Name of template if response_type is TEMPLATE.
        should_save: Whether to save this interaction to the database.
        processing_time: Time taken to process the message in seconds.
        button_data: Button data if response_type is BUTTON.
        send_tts: Whether to also send a TTS audio response.
        post_template_name: Optional template to send after the main response.
    """

    message: str
    response_type: ResponseType
    template_name: str = ""
    should_save: bool = True
    processing_time: float = 0.0
    button_data: Optional[Dict] = None
    send_tts: bool = False
    post_template_name: str = ""


def clear_processed_messages() -> None:
    """Clear the processed messages set.

    Useful for testing to reset state between tests.
    """
    processed_messages.clear()


class OptimizedMessageProcessor:
    """Optimized message processor for fast WhatsApp responses.

    This processor handles incoming WhatsApp messages with optimized paths
    for different message types. It provides fast text responses (2-4 seconds)
    and background processing for heavy operations like audio transcription.

    Attributes:
        language_mapping: Mapping of language codes to full names.
        system_message: System prompt for the language model.

    Example:
        processor = OptimizedMessageProcessor()
        result = await processor.process_message(
            payload=webhook_payload,
            from_number="1234567890",
            sender_name="John",
            target_language="eng",
            phone_number_id="0987654321"
        )
    """

    def __init__(self) -> None:
        """Initialize the message processor with language mappings."""
        self.language_mapping = {
            "lug": "Luganda",
            "ach": "Acholi",
            "teo": "Ateso",
            "lgg": "Lugbara",
            "nyn": "Runyankole",
            "eng": "English",
        }
        self.system_message = (
            "You are Sunflower, a multilingual assistant for Ugandan languages "
            "made by Sunbird AI. You specialise in accurate translations, "
            "explanations, summaries and other cross-lingual tasks."
        )
        self.valid_modes = {"chat", "translate", "transcribe"}
        self.mode_labels = {
            "chat": "Chat",
            "translate": "Translate",
            "transcribe": "Transcribe",
        }
        self.tts_speaker_by_language = {
            "ach": SpeakerID.ACHOLI_FEMALE,
            "teo": SpeakerID.ATESO_FEMALE,
            "nyn": SpeakerID.RUNYANKORE_FEMALE,
            "lgg": SpeakerID.LUGBARA_FEMALE,
            "swa": SpeakerID.SWAHILI_MALE,
            "sw": SpeakerID.SWAHILI_MALE,
            "swh": SpeakerID.SWAHILI_MALE,
            "lug": SpeakerID.LUGANDA_FEMALE,
            # Product requirement: English defaults to Luganda voice.
            "eng": SpeakerID.LUGANDA_FEMALE,
        }

    async def process_message(
        self,
        payload: Dict,
        from_number: str,
        sender_name: str,
        target_language: str,
        phone_number_id: str,
    ) -> ProcessingResult:
        """Process an incoming WhatsApp message.

        This is the main entry point for message processing. It determines
        the message type and routes to the appropriate handler.

        Args:
            payload: The webhook payload from WhatsApp.
            from_number: The sender's phone number.
            sender_name: The sender's display name.
            target_language: The user's preferred language code.
            phone_number_id: The WhatsApp Business phone number ID.

        Returns:
            ProcessingResult containing the response to send.
        """
        start_time = time.time()

        try:
            message_id = self._get_message_id(payload)

            # Quick duplicate check
            if message_id in processed_messages:
                return ProcessingResult(
                    "", ResponseType.SKIP, processing_time=time.time() - start_time
                )

            processed_messages.add(message_id)

            # Determine message type quickly
            message_type = self._determine_message_type(payload)
            user_mode = await get_user_mode(from_number) or "chat"
            tts_enabled = await get_user_tts_enabled(from_number)
            if tts_enabled is None:
                tts_enabled = False

            # Route to appropriate handler
            if message_type == MessageType.REACTION:
                result = self._handle_reaction(payload)
            elif message_type == MessageType.INTERACTIVE:
                result = await self._handle_interactive(payload, sender_name, from_number)
            elif message_type == MessageType.UNSUPPORTED:
                result = self._handle_unsupported(sender_name)
            elif message_type == MessageType.AUDIO:
                # Keep original audio pipeline - return processing message immediately
                result = await self._handle_audio_immediate_response(
                    payload,
                    target_language,
                    from_number,
                    sender_name,
                    phone_number_id,
                    user_mode,
                    tts_enabled,
                )
            else:  # TEXT
                result = await self._handle_text_optimized(
                    payload,
                    target_language,
                    from_number,
                    sender_name,
                    user_mode,
                    tts_enabled,
                )

            result.processing_time = time.time() - start_time
            return result

        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")
            return ProcessingResult(
                f"Sorry {sender_name}, I encountered an error. Please try again.",
                ResponseType.TEXT,
                processing_time=time.time() - start_time,
            )

    def _determine_message_type(self, payload: Dict) -> MessageType:
        """Determine the type of incoming message.

        Args:
            payload: The webhook payload.

        Returns:
            The detected MessageType.
        """
        try:
            messages = payload["entry"][0]["changes"][0]["value"]["messages"]
            message = messages[0]

            if "reaction" in message:
                return MessageType.REACTION
            elif "interactive" in message:
                return MessageType.INTERACTIVE
            elif "audio" in message:
                return MessageType.AUDIO
            elif any(
                key in message for key in ["image", "video", "document", "location"]
            ):
                return MessageType.UNSUPPORTED
            else:
                return MessageType.TEXT
        except (KeyError, IndexError):
            return MessageType.TEXT

    def _handle_reaction(self, payload: Dict) -> ProcessingResult:
        """Handle emoji reactions with proper feedback saving.

        Args:
            payload: The webhook payload.

        Returns:
            ProcessingResult for the reaction.
        """
        try:
            reaction = self._get_reaction(payload)
            if reaction:
                mess_id = reaction["message_id"]
                emoji = reaction["emoji"]
                # Save feedback with context
                asyncio.create_task(self._save_reaction_feedback_async(mess_id, emoji))
                return ProcessingResult(
                    "",
                    ResponseType.TEMPLATE,
                    template_name="custom_feedback",
                    should_save=False,
                )
        except Exception as e:
            logging.error(f"Error handling reaction: {e}")
        return ProcessingResult("", ResponseType.SKIP)

    async def _handle_interactive(
        self, payload: Dict, sender_name: str, from_number: str
    ) -> ProcessingResult:
        """Handle interactive button responses.

        Args:
            payload: The webhook payload.
            sender_name: The sender's display name.
            from_number: The sender's phone number.

        Returns:
            ProcessingResult for the interactive response.
        """
        try:
            interactive_response = self._get_interactive_response(payload)
            if not interactive_response:
                return ProcessingResult(
                    f"Dear {sender_name}, I didn't receive your selection properly. "
                    "\n\n Please try again.",
                    ResponseType.TEXT,
                    should_save=False,
                )

            # Handle different types of interactive responses
            if "list_reply" in interactive_response:
                return await self._handle_list_reply(
                    interactive_response["list_reply"], from_number, sender_name
                )
            elif "button_reply" in interactive_response:
                return await self._handle_button_reply(
                    interactive_response["button_reply"], from_number, sender_name
                )
            else:
                logging.warning(
                    f"Unknown interactive response type: {interactive_response}"
                )
                return ProcessingResult(
                    f"Dear {sender_name}, I received your response but couldn't "
                    "process it. \n\n Please try again.",
                    ResponseType.TEXT,
                    should_save=False,
                )

        except Exception as e:
            logging.error(f"Error handling interactive response: {e}")
            return ProcessingResult(
                f"Dear {sender_name}, I encountered an error processing your "
                "selection. Please try again.",
                ResponseType.TEXT,
                should_save=False,
            )

    def _handle_unsupported(self, sender_name: str) -> ProcessingResult:
        """Handle unsupported message types.

        Args:
            sender_name: The sender's display name.

        Returns:
            ProcessingResult informing user of unsupported type.
        """
        return ProcessingResult(
            f"Dear {sender_name}, I currently only support text and audio messages. "
            "\n\n Please try again with text or voice.",
            ResponseType.TEXT,
            should_save=False,
        )

    async def _handle_audio_immediate_response(
        self,
        payload: Dict,
        target_language: str,
        from_number: str,
        sender_name: str,
        phone_number_id: str,
        user_mode: str,
        tts_enabled: bool,
    ) -> ProcessingResult:
        """Handle audio - return immediate response and process in background.

        Args:
            payload: The webhook payload.
            target_language: The user's preferred language.
            from_number: The sender's phone number.
            sender_name: The sender's display name.
            phone_number_id: The WhatsApp Business phone number ID.

        Returns:
            ProcessingResult with immediate acknowledgment.
        """
        # Start background processing immediately
        asyncio.create_task(
            self._handle_audio_with_ug40_background(
                payload,
                target_language,
                from_number,
                sender_name,
                phone_number_id,
                user_mode,
                tts_enabled,
            )
        )

        return ProcessingResult(
            "Audio message received. Processing...",
            ResponseType.TEXT,
            should_save=False,
        )

    async def _handle_audio_with_ug40_background(
        self,
        payload: Dict,
        target_language: str,
        from_number: str,
        sender_name: str,
        phone_number_id: str,
        user_mode: str,
        tts_enabled: bool,
    ) -> None:
        """Background audio processing pipeline.

        This method handles the full audio processing workflow:
        1. Fetch media URL from WhatsApp
        2. Download audio file
        3. Validate audio
        4. Upload to cloud storage
        5. Transcribe with RunPod
        6. Process with UG40 language model
        7. Send response

        Args:
            payload: The webhook payload.
            target_language: The user's preferred language.
            from_number: The sender's phone number.
            sender_name: The sender's display name.
            phone_number_id: The WhatsApp Business phone number ID.
        """
        audio_info = self._get_audio_info(payload)
        if not audio_info:
            logging.error("No audio information provided.")
            whatsapp_service.send_message(
                recipient_id=from_number,
                message="Failed to process audio message.",
                phone_number_id=phone_number_id,
            )
            return

        audio_message_id = self._get_payload_message_id(payload)
        user_mode = self._normalize_mode(user_mode)
        tts_enabled = bool(tts_enabled)

        if not target_language:
            target_language = "eng"

        # Initialize variables for cleanup
        local_audio_path = None
        blob_name = None

        try:
            # Step 2: Fetch media URL from WhatsApp
            audio_url = whatsapp_service.fetch_media_url(
                audio_info["id"], WHATSAPP_TOKEN
            )
            if not audio_url:
                logging.error("Failed to fetch media URL from WhatsApp API")
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message="Failed to retrieve audio file. Please try sending the audio again.",
                    phone_number_id=phone_number_id,
                )
                return

            # Step 3: Download audio file
            local_audio_path = whatsapp_service.download_whatsapp_audio(
                audio_url, WHATSAPP_TOKEN
            )
            if not local_audio_path:
                logging.error("Failed to download audio from WhatsApp")
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        "Failed to download audio file. Please check your internet "
                        "connection and try again."
                    ),
                    phone_number_id=phone_number_id,
                )
                return

            # Step 4: Validate audio file
            try:
                audio_segment = AudioSegment.from_file(local_audio_path)
                duration_minutes = len(audio_segment) / (1000 * 60)
                file_size_mb = os.path.getsize(local_audio_path) / (1024 * 1024)

                logging.info(
                    f"Audio validated - Duration: {duration_minutes:.1f}min, "
                    f"Size: {file_size_mb:.1f}MB"
                )

                if duration_minutes > 10:
                    logging.info(
                        f"Long audio file detected: {duration_minutes:.1f} minutes"
                    )

            except CouldntDecodeError:
                logging.error("Downloaded audio file is corrupted")
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message="Audio file appears to be corrupted. Please try sending again.",
                    phone_number_id=phone_number_id,
                )
                return

            # Step 5: Upload to cloud storage
            try:
                blob_name, blob_url = upload_audio_file(file_path=local_audio_path)
                if not blob_name:
                    raise Exception("Upload failed")
                logging.info(f"Audio uploaded: {blob_url}")
            except Exception as e:
                logging.error(f"Cloud storage upload error: {str(e)}")
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message="Failed to upload audio. \n\n Please try again.",
                    phone_number_id=phone_number_id,
                )
                return

            # Step 6: Transcribe
            endpoint = runpod.Endpoint(RUNPOD_ENDPOINT_ID)
            transcription_data = {
                "input": {
                    "task": "transcribe",
                    "target_lang": target_language,
                    "adapter": target_language,
                    "audio_file": blob_name,
                    "whisper": True,
                    "recognise_speakers": False,
                }
            }

            request_response = await self._run_asr_with_retry(
                endpoint=endpoint,
                transcription_data=transcription_data,
                from_number=from_number,
                phone_number_id=phone_number_id,
            )
            if not request_response:
                return

            # Step 7: Validate transcription
            transcribed_text = request_response.get("audio_transcription", "").strip()
            if not transcribed_text:
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        "*No speech detected*. \n\n Please ensure you're speaking "
                        "clearly and try again."
                    ),
                    phone_number_id=phone_number_id,
                )
                return

            # Send transcription as a threaded reply to the original audio message.
            transcription_message = f'*Transcription:*\n"{transcribed_text}"'
            if audio_message_id:
                try:
                    whatsapp_service.reply_to_message(
                        message_id=audio_message_id,
                        recipient_id=from_number,
                        message=transcription_message,
                        phone_number_id=phone_number_id,
                    )
                except Exception as reply_error:
                    logging.warning(
                        f"Could not send threaded transcription reply: {reply_error}"
                    )
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=transcription_message,
                        phone_number_id=phone_number_id,
                    )
            else:
                logging.warning(
                    "Missing inbound audio message id; sending transcription "
                    "without threaded context."
                )
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=transcription_message,
                    phone_number_id=phone_number_id,
                )

            # Step 8: Mode-specific handling after transcription
            if user_mode == "transcribe":
                await save_response(
                    from_number,
                    "[AUDIO]",
                    f"[TRANSCRIPTION]: {transcribed_text}",
                )
                return

            if user_mode == "translate":
                try:
                    translated_text = await self._generate_translation_response(
                        transcribed_text, target_language
                    )
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=translated_text,
                        phone_number_id=phone_number_id,
                    )
                    if tts_enabled:
                        asyncio.create_task(
                            self.send_tts_audio_response(
                                response_text=translated_text,
                                target_language=target_language,
                                from_number=from_number,
                                phone_number_id=phone_number_id,
                            )
                        )
                    await save_response(
                        from_number,
                        f"[AUDIO-TRANSCRIBED]: {transcribed_text}",
                        translated_text,
                    )
                except Exception as translate_error:
                    logging.error(
                        f"Translation mode audio processing error: {translate_error}"
                    )
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=(
                            "I transcribed your audio, but couldn't translate it right "
                            "now. Please try again."
                        ),
                        phone_number_id=phone_number_id,
                    )
                return

            try:
                logging.info(f"Sending to UG40 for processing: {transcribed_text}")
                conversation_pairs = await get_user_conversation_pairs(
                    from_number, limit_pairs=10
                )
                recent_pairs = conversation_pairs[-5:]
                older_pairs = conversation_pairs[:-5]
                memory_note = await get_user_memory_note(from_number)
                if older_pairs and not memory_note:
                    memory_note = self._build_memory_note_fallback(older_pairs)
                if older_pairs:
                    asyncio.create_task(
                        self._refresh_memory_note_async(
                            from_number=from_number,
                            older_pairs=older_pairs,
                            existing_memory=memory_note,
                        )
                    )

                messages = self._build_optimized_prompt(
                    input_text=transcribed_text,
                    context=recent_pairs,
                    memory_note=memory_note,
                )

                logging.info(f"UG40 Messages: {messages}")
                response = await self._call_ug40_optimized(messages)
                final_response = self._clean_response(response)
                logging.info(f"Final UG40 Response: {final_response}")
                if final_response:
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=final_response,
                        phone_number_id=phone_number_id,
                    )
                    if tts_enabled:
                        asyncio.create_task(
                            self.send_tts_audio_response(
                                response_text=final_response,
                                target_language=target_language,
                                from_number=from_number,
                                phone_number_id=phone_number_id,
                            )
                        )
                    await save_response(
                        from_number, f"[AUDIO]: {transcribed_text}", final_response
                    )
                else:
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=(
                            "I transcribed your audio, but couldn't generate a model response. "
                            "Please try again."
                        ),
                        phone_number_id=phone_number_id,
                    )

            except Exception as ug40_error:
                logging.error(f"UG40 processing error: {str(ug40_error)}")
                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        "I transcribed your audio, but ran into an issue generating "
                        "the model response. Please try again."
                    ),
                    phone_number_id=phone_number_id,
                )

        except Exception as e:
            logging.error(f"Unexpected error in audio processing: {str(e)}")
            whatsapp_service.send_message(
                recipient_id=from_number,
                message=(
                    "An unexpected error occurred while processing your audio. "
                    "\n\n Please try again."
                ),
                phone_number_id=phone_number_id,
            )
        finally:
            # Cleanup
            if local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.remove(local_audio_path)
                    logging.info("Cleaned up local audio file")
                except Exception as cleanup_error:
                    logging.warning(f"Could not clean up: {cleanup_error}")
            if blob_name:
                try:
                    delete_audio_file(blob_name)
                    logging.info(f"Cleaned up uploaded audio blob: {blob_name}")
                except Exception as cleanup_error:
                    logging.warning(
                        f"Could not clean up uploaded audio blob {blob_name}: "
                        f"{cleanup_error}"
                    )

    async def _handle_text_optimized(
        self,
        payload: Dict,
        target_language: str,
        from_number: str,
        sender_name: str,
        user_mode: str,
        tts_enabled: bool,
    ) -> ProcessingResult:
        """Optimized text processing without caching.

        Args:
            payload: The webhook payload.
            target_language: The user's preferred language.
            from_number: The sender's phone number.
            sender_name: The sender's display name.

        Returns:
            ProcessingResult with the text response.
        """
        try:
            input_text = self._get_message_text(payload)
            message_id = self._get_message_id(payload)
            user_mode = self._normalize_mode(user_mode)
            tts_enabled = bool(tts_enabled)

            # Determine whether this is a new or returning user before command handling.
            user_preference = await get_user_preference(from_number)
            is_new_user = user_preference is None

            # Save message in background
            asyncio.create_task(self._save_message_async(from_number, input_text))

            # Quick command check first (most performance gain)
            command_result = await self._handle_quick_commands(
                input_text=input_text,
                target_language=target_language,
                sender_name=sender_name,
                from_number=from_number,
                user_mode=user_mode,
                tts_enabled=tts_enabled,
                is_new_user=is_new_user,
            )
            if command_result:
                if is_new_user:
                    asyncio.create_task(self._set_default_preference_async(from_number))
                    if (
                        command_result.response_type == ResponseType.TEXT
                        and not command_result.post_template_name
                    ):
                        command_result.post_template_name = "welcome_message"
                return command_result

            if not user_preference:
                # Do not block model processing for new users or transient DB failures.
                # Default to English and initialize preference in the background.
                user_preference = target_language or "eng"
                asyncio.create_task(self._set_default_preference_async(from_number))
                logging.info(
                    f"No stored language preference for {from_number}; "
                    f"continuing with default '{user_preference}'."
                )

            if user_mode == "transcribe":
                return ProcessingResult(
                    "📝 *Transcribe mode is active.* Send a voice note and I will "
                    "return the transcription.",
                    ResponseType.TEXT,
                    should_save=False,
                    post_template_name="welcome_message" if is_new_user else "",
                )

            if user_mode == "translate":
                translated_text = await self._generate_translation_response(
                    input_text, target_language
                )
                asyncio.create_task(
                    self._save_response_async(
                        from_number, input_text, translated_text, message_id
                    )
                )
                return ProcessingResult(
                    translated_text,
                    ResponseType.TEXT,
                    send_tts=tts_enabled,
                    post_template_name="welcome_message" if is_new_user else "",
                )

            # Chat mode context strategy:
            # - Keep the latest 5 conversation pairs as raw context.
            # - Compress older turns into a compact memory note.
            conversation_pairs = await get_user_conversation_pairs(
                from_number, limit_pairs=30
            )
            recent_pairs = conversation_pairs[-5:]
            older_pairs = conversation_pairs[:-5]

            memory_note = await get_user_memory_note(from_number)
            if older_pairs and not memory_note:
                memory_note = self._build_memory_note_fallback(older_pairs)

            if older_pairs:
                asyncio.create_task(
                    self._refresh_memory_note_async(
                        from_number=from_number,
                        older_pairs=older_pairs,
                        existing_memory=memory_note,
                    )
                )

            messages = self._build_optimized_prompt(
                input_text=input_text,
                context=recent_pairs,
                memory_note=memory_note,
            )

            response = await self._call_ug40_optimized(messages)
            response_content = self._clean_response(response)

            # Save response in background only if not a technical error
            if (
                response_content
                != "I'm having technical difficulties. \n\n Please try again."
            ):
                asyncio.create_task(
                    self._save_response_async(
                        from_number, input_text, response_content, message_id
                    )
                )

            send_tts_for_response = response_content not in {
                "I'm having technical difficulties. \n\n Please try again.",
                "I'm running a bit slow right now. \n\n Please try again.",
            }
            return ProcessingResult(
                response_content,
                ResponseType.TEXT,
                send_tts=send_tts_for_response and tts_enabled,
                post_template_name="welcome_message" if is_new_user else "",
            )

        except Exception as e:
            logging.error(f"Error in text processing: {str(e)}")
            return ProcessingResult(
                "I'm experiencing issues. Please try again.", ResponseType.TEXT
            )

    async def _handle_quick_commands(
        self,
        input_text: str,
        target_language: str,
        sender_name: str,
        from_number: str,
        user_mode: str,
        tts_enabled: bool,
        is_new_user: bool = False,
    ) -> Optional[ProcessingResult]:
        """Handle most common commands quickly.

        Args:
            input_text: The user's input text.
            target_language: The user's preferred language.
            sender_name: The sender's display name.
            from_number: The sender's phone number.
            user_mode: The current conversation mode.
            tts_enabled: Whether voice replies are enabled for this user.

        Returns:
            ProcessingResult if command matched, None otherwise.
        """
        text_lower = input_text.lower().strip()

        # Greeting messages should continue to normal model processing.
        if text_lower in ["hello", "hi", "hey", "hola", "greetings"]:
            return None

        # Most common commands - return immediately without UG40 calls
        elif text_lower in ["help", "commands"]:
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)
        elif text_lower == "status":
            return ProcessingResult(
                self._get_status_text(
                    target_language, sender_name, user_mode, tts_enabled
                ),
                ResponseType.TEXT,
            )
        elif text_lower in ["languages", "language"]:
            return ProcessingResult(self._get_languages_text(), ResponseType.TEXT)
        elif text_lower.startswith("set language"):
            return ProcessingResult(
                "", ResponseType.TEMPLATE, template_name="choose_language"
            )
        elif text_lower in ["mode", "switch mode", "change mode"]:
            return ProcessingResult(
                "",
                ResponseType.BUTTON,
                should_save=False,
                button_data={
                    "interactive_type": "reply",
                    "payload": self.create_mode_selection_reply_button(user_mode),
                },
            )
        elif text_lower in ["mode chat", "chat mode", "set mode chat"]:
            await self._set_user_mode_async(from_number, "chat")
            return ProcessingResult(
                "✅ Mode switched to *Chat*.\nI will answer normally using conversation context.",
                ResponseType.TEXT,
                should_save=False,
            )
        elif text_lower in ["mode translate", "translate mode", "set mode translate"]:
            await self._set_user_mode_async(from_number, "translate")
            return ProcessingResult(
                "✅ Mode switched to *Translate*.\nSend text or audio and I will return translation only.",
                ResponseType.TEXT,
                should_save=False,
            )
        elif text_lower in ["mode transcribe", "transcribe mode", "set mode transcribe"]:
            await self._set_user_mode_async(from_number, "transcribe")
            return ProcessingResult(
                "✅ Mode switched to *Transcribe*.\nSend a voice note and I will return transcription only.",
                ResponseType.TEXT,
                should_save=False,
            )
        elif text_lower in [
            "voice",
            "voice settings",
            "audio settings",
            "tts settings",
            "audio replies",
        ]:
            return ProcessingResult(
                "",
                ResponseType.BUTTON,
                should_save=False,
                button_data={
                    "interactive_type": "reply",
                    "payload": self.create_tts_selection_reply_button(tts_enabled),
                },
            )
        elif text_lower in [
            "voice on",
            "audio on",
            "tts on",
            "audio replies on",
        ]:
            await self._set_user_tts_enabled_async(from_number, True)
            return ProcessingResult(
                "🔊 Voice replies are now *ON* for Chat/Translate modes.",
                ResponseType.TEXT,
                should_save=False,
            )
        elif text_lower in [
            "voice off",
            "audio off",
            "tts off",
            "audio replies off",
            "text only",
        ]:
            await self._set_user_tts_enabled_async(from_number, False)
            return ProcessingResult(
                "🔇 Voice replies are now *OFF*. You will receive text only.",
                ResponseType.TEXT,
                should_save=False,
            )

        return None

    def _build_optimized_prompt(
        self, input_text: str, context: list, memory_note: Optional[str] = None
    ) -> list:
        """Build messages array with conversation context.

        Args:
            input_text: The current user input.
            context: Previous conversation pairs.

        Returns:
            List of message dicts for the language model.
        """
        messages = [
            {"role": "system", "content": self.system_message},
        ]

        if memory_note:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Conversation memory from earlier turns "
                        f"(use as context): {memory_note}"
                    ),
                }
            )

        # Add conversation context
        for conv in context:
            messages.append({"role": "user", "content": conv["user_message"]})
            messages.append({"role": "assistant", "content": conv["bot_response"]})

        # Add current message
        messages.append({"role": "user", "content": input_text})

        return messages

    async def _call_ug40_optimized(self, messages: list) -> Dict:
        """Call UG40 language model with optimized settings.

        Args:
            messages: List of message dicts for the model.

        Returns:
            Response dict from the model.
        """
        try:
            logging.info(
                f"Calling UG40 model with optimized settings. Messages: {messages}"
            )
            response = run_inference(messages=messages, model_type="qwen")
            return response
        except asyncio.TimeoutError:
            logging.error("UG40 call timed out")
            return {
                "content": "I'm running a bit slow right now. \n\n Please try again."
            }
        except Exception as e:
            logging.error(f"UG40 call error: {e}")
            return {
                "content": "I'm having technical difficulties. \n\n Please try again."
            }

    def _clean_response(self, ug40_response: Dict) -> str:
        """Clean and validate response from the language model.

        Args:
            ug40_response: Response dict from UG40.

        Returns:
            Cleaned response string.
        """
        content = ug40_response.get("content", "").strip()

        if not content:
            return "I'm having trouble understanding. Could you please rephrase?"

        return content

    async def _generate_translation_response(
        self, input_text: str, target_language: str
    ) -> str:
        """Generate translation-only output for text/audio in translate mode."""
        target_language_name = self.language_mapping.get(target_language, target_language)
        translate_messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict translation engine. Translate the input to "
                    f"{target_language_name}. Return only the translated text, with "
                    "no preamble, no notes, and no extra formatting."
                ),
            },
            {"role": "user", "content": input_text},
        ]
        response = await self._call_ug40_optimized(translate_messages)
        return self._clean_response(response)

    async def _run_asr_with_retry(
        self,
        endpoint: runpod.Endpoint,
        transcription_data: Dict,
        from_number: str,
        phone_number_id: str,
    ) -> Optional[Dict]:
        """Run ASR with one retry and user notification on delay/failure."""
        attempt_timeouts = [
            WHATSAPP_ASR_TIMEOUT_SECONDS,
            WHATSAPP_ASR_RETRY_TIMEOUT_SECONDS,
        ]

        for idx, timeout_seconds in enumerate(attempt_timeouts):
            attempt_num = idx + 1
            is_last_attempt = attempt_num == len(attempt_timeouts)
            try:
                return await asyncio.to_thread(
                    lambda: endpoint.run_sync(
                        transcription_data, timeout=timeout_seconds
                    )
                )
            except Exception as asr_error:
                logging.error(
                    "ASR attempt %s/%s failed: %s",
                    attempt_num,
                    len(attempt_timeouts),
                    asr_error,
                )

                if not is_last_attempt:
                    whatsapp_service.send_message(
                        recipient_id=from_number,
                        message=(
                            "⏳ I’m still processing your voice note. It took longer "
                            "than expected, so I’m retrying now."
                        ),
                        phone_number_id=phone_number_id,
                    )
                    await asyncio.sleep(WHATSAPP_RETRY_DELAY_SECONDS)
                    continue

                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        "I couldn't transcribe your audio after retrying. Please try "
                        "again with a shorter or clearer voice note."
                    ),
                    phone_number_id=phone_number_id,
                )
                return None

        return None

    def _resolve_tts_speaker_id(
        self, target_language: Optional[str], text: Optional[str] = None
    ) -> SpeakerID:
        """Resolve speaker ID from language code, with English defaulting to Luganda."""
        if not target_language:
            return SpeakerID.LUGANDA_FEMALE

        normalized = str(target_language).strip().lower()
        if normalized in self.tts_speaker_by_language:
            return self.tts_speaker_by_language[normalized]

        # Support full language names if they appear.
        language_alias_map = {
            "acholi": "ach",
            "ateso": "teo",
            "runyankore": "nyn",
            "runyankole": "nyn",
            "lugbara": "lgg",
            "swahili": "swa",
            "luganda": "lug",
            "english": "eng",
        }
        alias_code = language_alias_map.get(normalized)
        if alias_code and alias_code in self.tts_speaker_by_language:
            return self.tts_speaker_by_language[alias_code]

        logging.info(
            "Unknown target language '%s' for TTS; defaulting to Luganda speaker.",
            target_language,
        )
        return SpeakerID.LUGANDA_FEMALE

    async def send_tts_audio_response(
        self,
        response_text: str,
        target_language: str,
        from_number: str,
        phone_number_id: str,
    ) -> None:
        """Generate TTS audio for response text and send it through WhatsApp."""
        if not WHATSAPP_TTS_ENABLED:
            return

        clean_text = self._clean_text_for_tts(response_text or "")
        if not clean_text:
            return

        # Keep TTS payload bounded to avoid long generation times/timeouts.
        if len(clean_text) > WHATSAPP_TTS_MAX_CHARS:
            clean_text = clean_text[: WHATSAPP_TTS_MAX_CHARS].rstrip() + "..."

        tts_service = get_tts_service()
        speaker_id = self._resolve_tts_speaker_id(target_language, clean_text)
        notified_retry = False
        max_attempts = 2

        for attempt_num in range(1, max_attempts + 1):
            wav_path = ""
            media_path = ""
            is_last_attempt = attempt_num == max_attempts
            try:
                audio_bytes = await tts_service.generate_audio(clean_text, speaker_id)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
                    wav_file.write(audio_bytes)
                    wav_path = wav_file.name

                # WhatsApp accepts mpeg/ogg/amr/mp4 audio; convert wav -> mp3.
                try:
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".mp3"
                    ) as mp3_file:
                        media_path = mp3_file.name
                    audio_segment = AudioSegment.from_file(wav_path)
                    audio_segment.export(media_path, format="mp3", bitrate="96k")
                except Exception as conversion_error:
                    logging.warning(
                        "TTS wav->mp3 conversion failed (%s); falling back to wav upload.",
                        conversion_error,
                    )
                    media_path = wav_path

                upload_response = await asyncio.to_thread(
                    lambda: whatsapp_service.upload_media(media_path, phone_number_id)
                )
                media_id = (upload_response or {}).get("id")
                if not media_id:
                    raise RuntimeError(
                        f"Failed to upload TTS media to WhatsApp: {upload_response}"
                    )

                send_audio_response = await asyncio.to_thread(
                    lambda: whatsapp_service.send_audio(
                        recipient_id=from_number,
                        audio=media_id,
                        link=False,
                        phone_number_id=phone_number_id,
                    )
                )
                if (send_audio_response or {}).get("error"):
                    raise RuntimeError(
                        f"Failed to send TTS audio message: {send_audio_response}"
                    )
                return
            except Exception as tts_error:
                logging.error(
                    "TTS attempt %s/%s failed for %s: %s",
                    attempt_num,
                    max_attempts,
                    from_number,
                    tts_error,
                )
                if not is_last_attempt:
                    if not notified_retry:
                        whatsapp_service.send_message(
                            recipient_id=from_number,
                            message=(
                                "⏳ Voice reply is taking longer than expected. I’m "
                                "retrying and will send it shortly."
                            ),
                            phone_number_id=phone_number_id,
                        )
                        notified_retry = True
                    await asyncio.sleep(WHATSAPP_RETRY_DELAY_SECONDS)
                    continue

                whatsapp_service.send_message(
                    recipient_id=from_number,
                    message=(
                        "I couldn't deliver the voice reply this time after retrying, "
                        "but the text response above is ready."
                    ),
                    phone_number_id=phone_number_id,
                )
            finally:
                for temp_path in {wav_path, media_path}:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as cleanup_error:
                            logging.warning(
                                "Could not remove temp TTS file %s: %s",
                                temp_path,
                                cleanup_error,
                            )

    def _clean_text_for_tts(self, text: str) -> str:
        """Normalize response text for TTS by removing markdown and emoji noise."""
        cleaned = (text or "").replace("\n", " ")
        cleaned = re.sub(r"[*_~`#>|[\]{}()]+", " ", cleaned)
        cleaned = re.sub(
            r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _build_memory_note_fallback(self, older_pairs: list) -> str:
        """Fallback memory compression when no model summary is available yet."""
        recent_older_pairs = older_pairs[-4:]
        lines = []
        for pair in recent_older_pairs:
            user = (pair.get("user_message") or "").strip().replace("\n", " ")
            bot = (pair.get("bot_response") or "").strip().replace("\n", " ")
            lines.append(
                f"- User: {user[:120]} | Assistant: {bot[:120]}"
            )
        return "Earlier context highlights:\n" + "\n".join(lines)

    async def _refresh_memory_note_async(
        self,
        from_number: str,
        older_pairs: list,
        existing_memory: Optional[str],
    ) -> None:
        """Refresh compact memory note in the background."""
        try:
            condensed_pairs = older_pairs[-12:]
            serialized_pairs = []
            for pair in condensed_pairs:
                user_text = (pair.get("user_message") or "").strip().replace("\n", " ")
                bot_text = (pair.get("bot_response") or "").strip().replace("\n", " ")
                serialized_pairs.append(
                    f"User: {user_text[:280]}\nAssistant: {bot_text[:280]}"
                )

            if not serialized_pairs:
                return

            memory_prompt = [
                {
                    "role": "system",
                    "content": (
                        "Summarize older conversation context into a compact memory "
                        "note for a chatbot. Keep facts, user preferences, unresolved "
                        "tasks, and constraints. Be concise and specific."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Existing memory note:\n{existing_memory or 'None'}\n\n"
                        "Older conversation pairs:\n"
                        f"{chr(10).join(serialized_pairs)}\n\n"
                        "Write an updated compact memory note in <= 120 words."
                    ),
                },
            ]

            summary_response = await asyncio.to_thread(
                lambda: run_inference(messages=memory_prompt, model_type="qwen")
            )
            memory_note = self._clean_response(summary_response)
            if memory_note:
                await upsert_user_memory_note(from_number, memory_note[:800])
        except Exception as e:
            logging.warning("Background memory refresh failed for %s: %s", from_number, e)

    async def _set_user_mode_async(self, from_number: str, mode: str) -> None:
        """Persist user mode safely."""
        normalized_mode = self._normalize_mode(mode)
        try:
            await save_user_mode(from_number, normalized_mode)
            logging.info("User mode set: %s -> %s", from_number, normalized_mode)
        except Exception as e:
            logging.error("Error saving user mode for %s: %s", from_number, e)

    async def _set_user_tts_enabled_async(
        self, from_number: str, tts_enabled: bool
    ) -> None:
        """Persist user TTS preference safely."""
        try:
            await save_user_tts_enabled(from_number, bool(tts_enabled))
            logging.info(
                "User tts preference set: %s -> %s",
                from_number,
                bool(tts_enabled),
            )
        except Exception as e:
            logging.error("Error saving user tts preference for %s: %s", from_number, e)

    def _normalize_mode(self, mode: Optional[str]) -> str:
        if not mode:
            return "chat"
        normalized = str(mode).strip().lower()
        return normalized if normalized in self.valid_modes else "chat"

    async def _set_default_preference_async(self, from_number: str) -> None:
        """Set default user preference asynchronously.

        Args:
            from_number: The user's phone number.
        """
        try:
            await save_user_preference(
                from_number, "English", "eng", "chat", tts_enabled=False
            )
            logging.info(f"Default preference set for new user: {from_number}")
        except Exception as e:
            logging.error(f"Error setting default preference: {e}")

    async def _save_message_async(self, from_number: str, message: str) -> None:
        """Save message asynchronously.

        Args:
            from_number: The user's phone number.
            message: The message text.
        """
        try:
            await save_message(from_number, message)
        except Exception as e:
            logging.error(f"Error saving message: {e}")

    async def _save_response_async(
        self, from_number: str, user_message: str, response: str, message_id: str
    ) -> None:
        """Save response asynchronously.

        Args:
            from_number: The user's phone number.
            user_message: The original user message.
            response: The bot's response.
            message_id: The WhatsApp message ID.
        """
        try:
            await save_response(from_number, user_message, response, message_id)
        except Exception as e:
            logging.error(f"Error saving response: {e}")

    async def _update_feedback_async(self, message_id: str, emoji: str) -> None:
        """Update feedback asynchronously.

        Args:
            message_id: The WhatsApp message ID.
            emoji: The emoji reaction.
        """
        try:
            await update_feedback(message_id, emoji)
        except Exception as e:
            logging.error(f"Error updating feedback: {e}")

    # Utility methods for payload extraction
    def _get_message_id(self, payload: Dict) -> str:
        """Extract message ID from payload.

        Args:
            payload: The webhook payload.

        Returns:
            The message ID or a generated fallback.
        """
        try:
            return payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
        except (KeyError, IndexError):
            return f"unknown_{int(time.time())}"

    def _get_payload_message_id(self, payload: Dict) -> Optional[str]:
        """Extract the inbound WhatsApp message ID, if present."""
        try:
            message_id = payload["entry"][0]["changes"][0]["value"]["messages"][0].get(
                "id"
            )
            return message_id if isinstance(message_id, str) and message_id else None
        except (KeyError, IndexError):
            return None

    def _get_message_text(self, payload: Dict) -> str:
        """Extract message text from payload.

        Args:
            payload: The webhook payload.

        Returns:
            The message text or empty string.
        """
        try:
            return payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"][
                "body"
            ]
        except (KeyError, IndexError):
            return ""

    def _get_reaction(self, payload: Dict) -> Optional[Dict]:
        """Extract reaction from payload.

        Args:
            payload: The webhook payload.

        Returns:
            Reaction dict or None.
        """
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("reaction")
        except (KeyError, IndexError):
            return None

    def _get_interactive_response(self, payload: Dict) -> Optional[Dict]:
        """Extract interactive response from payload.

        Args:
            payload: The webhook payload.

        Returns:
            Interactive response dict or None.
        """
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("interactive")
        except (KeyError, IndexError):
            return None

    def _get_audio_info(self, payload: Dict) -> Optional[Dict]:
        """Extract audio info from payload.

        Args:
            payload: The webhook payload.

        Returns:
            Audio info dict with id and mime_type, or None.
        """
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            if "audio" in message:
                return {
                    "id": message["audio"]["id"],
                    "mime_type": message["audio"]["mime_type"],
                }
        except (KeyError, IndexError):
            pass
        return None

    # Interactive response handlers
    async def _handle_list_reply(
        self, list_reply: Dict, from_number: str, sender_name: str
    ) -> ProcessingResult:
        """Handle list selection responses.

        Args:
            list_reply: The list reply data.
            from_number: The sender's phone number.
            sender_name: The sender's display name.

        Returns:
            ProcessingResult for the selection.
        """
        try:
            selected_id = list_reply.get("id", "")
            selected_title = list_reply.get("title", "")

            if not selected_id:
                return ProcessingResult(
                    f"Dear {sender_name}, I didn't receive your selection properly. "
                    "Please try again.",
                    ResponseType.TEXT,
                    should_save=False,
                )

            # Map row IDs to specific actions based on context
            # Welcome button responses
            if selected_id == "row 1" and selected_title == "Get Help":
                return ProcessingResult(
                    self._get_help_text(), ResponseType.TEXT, should_save=True
                )

            elif selected_id == "row 2" and selected_title == "Set Language":
                return ProcessingResult(
                    "",
                    ResponseType.TEMPLATE,
                    template_name="choose_language",
                    should_save=False,
                )

            elif selected_id == "row 3" and selected_title == "Start Chatting":
                return ProcessingResult(
                    f"Perfect {sender_name}! 🌻 I'm ready to help you with:\n\n"
                    f"• Translations between Ugandan languages and English\n"
                    f"• Audio transcription in local languages\n"
                    f"• Language learning support\n\n"
                    f"Just send me a message or audio to get started!",
                    ResponseType.TEXT,
                    should_save=True,
                )

            # Language selection responses
            elif selected_title in self.language_mapping.values():
                return await self._handle_language_selection_by_name(
                    selected_title, from_number, sender_name
                )

            # Feedback responses
            elif selected_title in ["Excellent", "Good", "Fair", "Poor"]:
                return self._handle_feedback_by_title(
                    selected_title, from_number, sender_name
                )

            # Unknown selection - fallback
            else:
                logging.warning(
                    f"Unknown list selection: {selected_id} - {selected_title}"
                )
                return ProcessingResult(
                    f"Thanks {sender_name}! I received your selection. "
                    "How can I help you further?",
                    ResponseType.TEXT,
                    should_save=True,
                )

        except Exception as e:
            logging.error(f"Error handling list reply: {e}")
            return ProcessingResult(
                f"Dear {sender_name}, I encountered an error processing your "
                "selection. Please try again.",
                ResponseType.TEXT,
                should_save=False,
            )

    async def _handle_button_reply(
        self, button_reply: Dict, from_number: str, sender_name: str
    ) -> ProcessingResult:
        """Handle button reply responses.

        Args:
            button_reply: The button reply data.
            from_number: The sender's phone number.
            sender_name: The sender's display name.

        Returns:
            ProcessingResult for the button response.
        """
        button_id = (button_reply.get("id") or "").strip().lower()
        if button_id in {"mode_chat", "mode_translate", "mode_transcribe"}:
            selected_mode = button_id.replace("mode_", "")
            await self._set_user_mode_async(from_number, selected_mode)
            mode_label = self.mode_labels.get(selected_mode, selected_mode.title())
            return ProcessingResult(
                f"✅ Mode switched to *{mode_label}*.",
                ResponseType.TEXT,
                should_save=False,
            )
        if button_id == "tts_on":
            await self._set_user_tts_enabled_async(from_number, True)
            return ProcessingResult(
                "🔊 Voice replies are now *ON* for Chat/Translate modes.",
                ResponseType.TEXT,
                should_save=False,
            )
        if button_id == "tts_off":
            await self._set_user_tts_enabled_async(from_number, False)
            return ProcessingResult(
                "🔇 Voice replies are now *OFF*. You will receive text only.",
                ResponseType.TEXT,
                should_save=False,
            )

        return ProcessingResult(
            f"Thanks {sender_name}! I received your response.",
            ResponseType.TEXT,
            should_save=True,
        )

    async def _handle_language_selection_by_name(
        self, language_name: str, from_number: str, sender_name: str
    ) -> ProcessingResult:
        """Handle language selection by language name.

        Args:
            language_name: The selected language name.
            from_number: The sender's phone number.
            sender_name: The sender's display name.

        Returns:
            ProcessingResult confirming the language selection.
        """
        try:
            # Find the language code for the selected name
            language_code = None
            for code, name in self.language_mapping.items():
                if name == language_name:
                    language_code = code
                    break

            if not language_code:
                return ProcessingResult(
                    f"Sorry {sender_name}, I couldn't find that language. "
                    "Please try again.",
                    ResponseType.TEXT,
                    should_save=False,
                )

            # Save the language preference
            try:
                await save_user_preference(from_number, "English", language_code)
                logging.info(
                    f"Language preference saved for {from_number}: {language_code}"
                )

                return ProcessingResult(
                    f"✅ Perfect! Language set to {language_name}!\n\n"
                    f"You can now:\n"
                    f"• Send messages in {language_name} or English\n"
                    f"• Ask me to translate to {language_name}\n"
                    f"• Send audio in {language_name} for transcription\n\n"
                    f"Just start typing or send an audio message! 🎤📝",
                    ResponseType.TEXT,
                    should_save=True,
                )

            except Exception as db_error:
                logging.error(f"Database error saving language preference: {db_error}")
                return ProcessingResult(
                    f"I've set your language to {language_name}! "
                    f"You can now send messages or audio in {language_name}. "
                    f"How can I help you today?",
                    ResponseType.TEXT,
                    should_save=True,
                )

        except Exception as e:
            logging.error(f"Error handling language selection by name: {e}")
            return ProcessingResult(
                "I've received your language preference. How can I help you today?",
                ResponseType.TEXT,
                should_save=True,
            )

    def _handle_feedback_by_title(
        self, feedback_title: str, from_number: str, sender_name: str
    ) -> ProcessingResult:
        """Handle feedback by title with personalized responses.

        Args:
            feedback_title: The feedback rating (Excellent, Good, Fair, Poor).
            from_number: The sender's phone number.
            sender_name: The sender's display name.

        Returns:
            ProcessingResult with acknowledgment.
        """
        try:
            feedback_responses = {
                "Excellent": (
                    f"🌟 *Wonderful* {sender_name}!\n\n"
                    f"Thank you for the *excellent* rating!\n"
                    f"I'm *thrilled* I could help you effectively.\n\n"
                    f"*Feel free to ask me anything else!*"
                ),
                "Good": (
                    f"😊 Thank you {sender_name}!\n\n"
                    f"I'm glad the response was *helpful*.\n"
                    f"I'm here whenever you need *assistance* with *languages* "
                    f"or *translations*!"
                ),
                "Fair": (
                    f"👍 Thanks {sender_name} for the *honest feedback*!\n\n"
                    f"I'm always *learning* and *improving*.\n"
                    f"Please let me know how I can help *better* next time!"
                ),
                "Poor": (
                    f"🤔 Thank you {sender_name} for the feedback.\n\n"
                    f"I apologize the response wasn't *helpful*.\n"
                    f"Please try *rephrasing your question* - I'll do my best "
                    f"to give you a *better answer*!"
                ),
            }

            response_message = feedback_responses.get(
                feedback_title,
                f"Thank you {sender_name} for your feedback! It helps me improve.",
            )

            # Save detailed feedback with context
            asyncio.create_task(
                self._save_detailed_feedback_async(
                    from_number, feedback_title, sender_name
                )
            )

            return ProcessingResult(
                response_message, ResponseType.TEXT, should_save=True
            )

        except Exception as e:
            logging.error(f"Error handling feedback by title: {e}")
            return ProcessingResult(
                f"Thank you {sender_name} for the feedback! How can I help you next?",
                ResponseType.TEXT,
                should_save=True,
            )

    # Async feedback methods
    async def _save_reaction_feedback_async(self, message_id: str, emoji: str) -> None:
        """Save reaction feedback with context.

        Args:
            message_id: The WhatsApp message ID being reacted to.
            emoji: The emoji reaction.
        """
        try:
            saved = await save_detailed_feedback(
                message_id, emoji, feedback_type="reaction"
            )
            if saved:
                logging.info(f"Reaction feedback saved: {message_id} - {emoji}")
            else:
                logging.warning(
                    f"Could not map reaction feedback to message: {message_id}"
                )
        except Exception as e:
            logging.error(f"Error saving reaction feedback: {e}")

    async def _save_detailed_feedback_async(
        self, from_number: str, feedback_title: str, sender_name: str
    ) -> None:
        """Save detailed feedback for button selections.

        Args:
            from_number: The sender's phone number.
            feedback_title: The feedback rating.
            sender_name: The sender's display name.
        """
        try:
            saved = await save_feedback_with_context(
                from_number,
                feedback_title,
                sender_name,
                feedback_type="button",
            )
            if saved:
                logging.info(
                    f"Detailed feedback saved: {from_number} - {feedback_title}"
                )
            else:
                logging.warning(
                    f"Failed to save detailed feedback: {from_number} - {feedback_title}"
                )
        except Exception as e:
            logging.error(f"Error saving detailed feedback: {e}")

    # Button creation methods
    def create_mode_selection_reply_button(self, current_mode: Optional[str] = None) -> Dict:
        """Create one-tap reply buttons for mode switching."""
        normalized_mode = self._normalize_mode(current_mode)
        current_mode_label = self.mode_labels.get(normalized_mode, "Chat")
        return {
            "type": "button",
            "body": {
                "text": (
                    "Choose how I should handle your next messages:\n"
                    "• Chat: normal assistant mode\n"
                    "• Translate: translation-only output\n"
                    "• Transcribe: audio transcription-only"
                )
            },
            "footer": {"text": f"Current mode: {current_mode_label}"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "mode_chat", "title": "Chat"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "mode_translate", "title": "Translate"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "mode_transcribe", "title": "Transcribe"},
                    },
                ]
            },
        }

    def create_tts_selection_reply_button(self, tts_enabled: bool) -> Dict:
        """Create one-tap reply buttons for voice reply preference."""
        voice_status = "ON" if tts_enabled else "OFF"
        return {
            "type": "button",
            "body": {
                "text": (
                    "Choose reply format for Chat/Translate modes:\n"
                    "• Text + Voice\n"
                    "• Text only"
                )
            },
            "footer": {"text": f"Current voice replies: {voice_status}"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "tts_on", "title": "Text + Voice"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "tts_off", "title": "Text Only"},
                    },
                ]
            },
        }

    def create_language_selection_button(self) -> Dict:
        """Create interactive button for language selection.

        Returns:
            Dict containing the button structure for WhatsApp.
        """
        language_rows = []
        i = 1
        for code, name in self.language_mapping.items():
            language_rows.append(
                {
                    "id": f"row {i}",
                    "title": name,
                    "description": f"Set your preferred language to {name}",
                }
            )
            i += 1

        return {
            "header": "🌐 Language Selection",
            "body": "Please select your preferred language for your audio commands:",
            "footer": "Powered by Sunbird AI 🌻",
            "action": {
                "button": "Select Language",
                "sections": [{"title": "Available Languages", "rows": language_rows}],
            },
        }

    def create_feedback_button(self) -> Dict:
        """Create feedback button.

        Returns:
            Dict containing the button structure for WhatsApp.
        """
        return {
            "header": "📝 Feedback",
            "body": "How was my response? Your feedback helps me improve!",
            "footer": "Thank you for helping Sunflower grow 🌻",
            "action": {
                "button": "Rate Response",
                "sections": [
                    {
                        "title": "Response Quality",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Excellent",
                                "description": "🌟 Very helpful response!",
                            },
                            {
                                "id": "row 2",
                                "title": "Good",
                                "description": "😊 Helpful response",
                            },
                            {
                                "id": "row 3",
                                "title": "Fair",
                                "description": "👌 Somewhat helpful",
                            },
                            {
                                "id": "row 4",
                                "title": "Poor",
                                "description": "👎 Not helpful",
                            },
                        ],
                    }
                ],
            },
        }

    def create_welcome_button(self) -> Dict:
        """Create welcome button for new users.

        Returns:
            Dict containing the button structure for WhatsApp.
        """
        return {
            "header": "🌻 Welcome to Sunflower!",
            "body": (
                "I'm your multilingual assistant for Ugandan languages. "
                "What would you like to do first?"
            ),
            "footer": "Made with ❤️ by Sunbird AI",
            "action": {
                "button": "Get Started",
                "sections": [
                    {
                        "title": "Quick Actions",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Get Help",
                                "description": "📚 Learn what I can do for you",
                            },
                            {
                                "id": "row 2",
                                "title": "Set Language",
                                "description": (
                                    "🌐 Choose language in which your audio "
                                    "commands will be sent"
                                ),
                            },
                            {
                                "id": "row 3",
                                "title": "Start Chatting",
                                "description": "💬 Begin our conversation",
                            },
                        ],
                    }
                ],
            },
        }

    # Text generators for commands
    def _get_help_text(self) -> str:
        """Get help text for the help command.

        Returns:
            Formatted help text string.
        """
        return (
            "*🌻 Sunflower Assistant Commands*\n\n"
            "*Basic Commands:*\n"
            "• *help* – Show this help message\n"
            "• *status* – Show your current settings\n"
            "• *languages* – Show supported languages\n\n"
            "*Language Commands:*\n"
            "• *set language* – Set your preferred language for audio commands\n\n"
            "*Mode Commands:*\n"
            "• *mode* – Open one-tap mode switch buttons\n"
            "• *mode chat* – Standard conversational assistant\n"
            "• *mode translate* – Translation-only output\n"
            "• *mode transcribe* – Audio transcription-only\n\n"
            "*Voice Reply Commands:*\n"
            "• *voice* – Open one-tap voice reply options\n"
            "• *voice on* – Enable text + voice replies\n"
            "• *voice off* – Text only replies\n\n"
            "*Natural Questions:*\n"
            "You can also ask naturally:\n"
            "• *What can you do?*\n"
            "• *What languages do you support?*\n\n"
            "Just type your message normally – *I'm here to help!*"
        )

    def _get_status_text(
        self,
        target_language: str,
        sender_name: str,
        user_mode: str,
        tts_enabled: bool,
    ) -> str:
        """Get status text showing current settings.

        Args:
            target_language: The user's preferred language code.
            sender_name: The sender's display name.
            user_mode: The user's active mode.
            tts_enabled: Whether voice replies are enabled.

        Returns:
            Formatted status text string.
        """
        language_name = self.language_mapping.get(target_language, target_language)
        mode_label = self.mode_labels.get(self._normalize_mode(user_mode), "Chat")
        voice_label = "ON (Text + Voice)" if tts_enabled else "OFF (Text Only)"
        return (
            f"*🌻 Status for {sender_name}*\n\n"
            f"*Current Language:* *{language_name}* ({target_language})\n"
            f"*Current Mode:* *{mode_label}*\n"
            f"*Voice Replies:* *{voice_label}*\n"
            "*Assistant:* Sunflower by Sunbird AI\n"
            "*Platform:* WhatsApp\n\n"
            "Type *help* for available commands or just *chat naturally!*"
        )

    def _get_languages_text(self) -> str:
        """Get languages text showing supported languages.

        Returns:
            Formatted languages text string.
        """
        languages_list = [
            f"• *{name}* ({code})"
            for code, name in sorted(self.language_mapping.items())
        ]
        return (
            "*🌐 Supported Languages*\n\n"
            f"{chr(10).join(languages_list)}\n\n"
            "To set your language, type:\n"
            "*set language [name]* or *set language [code]*\n\n"
            "Example: *set language english*"
        )
