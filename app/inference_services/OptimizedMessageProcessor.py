import asyncio
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set
import runpod
from dotenv import load_dotenv
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from app.inference_services.ug40_inference import run_inference
from app.inference_services.user_preference import (
    get_user_last_five_conversation_pairs,
    get_user_preference,
    save_user_preference,
    save_message,
    save_response,
    update_feedback,
)
from app.inference_services.whatsapp_service import WhatsAppService
from app.utils.upload_audio_file_gcp import upload_audio_file

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Configuration
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID")

# Initialize services
whatsapp_service = WhatsAppService(token=WHATSAPP_TOKEN, phone_number_id=PHONE_NUMBER_ID)
processed_messages: Set[str] = set()

class MessageType(Enum):
    TEXT = "text"
    AUDIO = "audio"
    UNSUPPORTED = "unsupported"
    REACTION = "reaction"
    INTERACTIVE = "interactive"

class ResponseType(Enum):
    TEXT = "text"
    TEMPLATE = "template" 
    BUTTON = "button"
    SKIP = "skip"

@dataclass
class ProcessingResult:
    message: str
    response_type: ResponseType
    template_name: str = ""
    should_save: bool = True
    processing_time: float = 0.0

class OptimizedMessageProcessor:
    """Optimized message processor for fast WhatsApp responses without Redis"""
    
    def __init__(self):
        self.language_mapping = {
            "lug": "Luganda", "ach": "Acholi", "teo": "Ateso",
            "lgg": "Lugbara", "nyn": "Runyankole", "eng": "English"
        }
        self.system_message = (
            "You are Sunflower, a multilingual assistant for Ugandan languages made by Sunbird AI. "
            "You specialise in accurate translations, explanations, summaries, and other cross-lingual tasks. "
            "Keep responses concise and helpful.\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "- You will receive conversation history for context only - DO NOT continue or respond to old messages\n"
            "- Only respond to the CURRENT message that comes after 'Current message:'\n"
            "- Use the conversation history only to understand context, user preferences, or ongoing topics\n"
            "- Give a fresh, direct response to the current message only\n"
            "- Do not acknowledge or reference the conversation history unless directly relevant to the current message"
        )

    async def process_message(
        self, 
        payload: Dict, 
        from_number: str, 
        sender_name: str,
        target_language: str,
        phone_number_id: str
    ) -> ProcessingResult:
        """Fast message processing with optimized paths"""
        start_time = time.time()
        
        try:
            message_id = self._get_message_id(payload)
            
            # Quick duplicate check
            if message_id in processed_messages:
                return ProcessingResult("", ResponseType.SKIP, processing_time=time.time() - start_time)
            
            processed_messages.add(message_id)
            
            # Determine message type quickly
            message_type = self._determine_message_type(payload)
            
            # Route to appropriate handler
            if message_type == MessageType.REACTION:
                result = self._handle_reaction(payload)
            elif message_type == MessageType.INTERACTIVE:
                result = self._handle_interactive(payload, sender_name, from_number)
            elif message_type == MessageType.UNSUPPORTED:
                result = self._handle_unsupported(sender_name)
            elif message_type == MessageType.AUDIO:
                # Keep original audio pipeline - return processing message immediately
                result = await self._handle_audio_immediate_response(
                    payload, target_language, from_number, sender_name, phone_number_id
                )
            else:  # TEXT
                result = await self._handle_text_optimized(payload, target_language, from_number, sender_name)
            
            result.processing_time = time.time() - start_time
            return result
            
        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")
            return ProcessingResult(
                f"Sorry {sender_name}, I encountered an error. Please try again.",
                ResponseType.TEXT,
                processing_time=time.time() - start_time
            )

    def _determine_message_type(self, payload: Dict) -> MessageType:
        """Ultra-fast message type detection"""
        try:
            messages = payload["entry"][0]["changes"][0]["value"]["messages"]
            message = messages[0]
            
            if "reaction" in message:
                return MessageType.REACTION
            elif "interactive" in message:
                return MessageType.INTERACTIVE
            elif "audio" in message:
                return MessageType.AUDIO
            elif any(key in message for key in ["image", "video", "document", "location"]):
                return MessageType.UNSUPPORTED
            else:
                return MessageType.TEXT
        except (KeyError, IndexError):
            return MessageType.TEXT

    def _handle_reaction(self, payload: Dict) -> ProcessingResult:
        """Handle emoji reactions"""
        try:
            reaction = self._get_reaction(payload)
            if reaction:
                mess_id = reaction["message_id"]
                emoji = reaction["emoji"]
                # Non-blocking feedback update
                asyncio.create_task(self._update_feedback_async(mess_id, emoji))
                return ProcessingResult("", ResponseType.TEMPLATE, template_name="custom_feedback", should_save=False)
        except Exception as e:
            logging.error(f"Error handling reaction: {e}")
        return ProcessingResult("", ResponseType.SKIP)

    def _handle_interactive(self, payload: Dict, sender_name: str, from_number: str) -> ProcessingResult:
        """Handle interactive button responses"""
        try:
            interactive_response = self._get_interactive_response(payload)
            if interactive_response:
                # Handle different types of button responses
                if "list_reply" in interactive_response:
                    return self._handle_list_reply(interactive_response["list_reply"], from_number, sender_name)
                elif "button_reply" in interactive_response:
                    return self._handle_button_reply(interactive_response["button_reply"], sender_name)
        except Exception as e:
            logging.error(f"Error handling interactive response: {e}")
        
        return ProcessingResult(
            f"Dear {sender_name}, Thanks for that response.",
            ResponseType.TEXT,
            should_save=False
        )

    def _handle_unsupported(self, sender_name: str) -> ProcessingResult:
        """Handle unsupported message types"""
        return ProcessingResult(
            f"Dear {sender_name}, I currently only support text and audio messages. Please try again with text or voice.",
            ResponseType.TEXT,
            should_save=False
        )

    async def _handle_audio_immediate_response(
        self, 
        payload: Dict, 
        target_language: str, 
        from_number: str, 
        sender_name: str,
        phone_number_id: str
    ) -> ProcessingResult:
        """Handle audio - return immediate response and process in background"""
        # Start background processing immediately
        asyncio.create_task(self._handle_audio_with_ug40_background(
            payload, target_language, from_number, sender_name, phone_number_id
        ))
        
        return ProcessingResult(
            f"Audio message received. Processing...",
            ResponseType.TEXT,
            should_save=False
        )

    async def _handle_audio_with_ug40_background(
        self, payload, target_language, from_number, sender_name, phone_number_id
    ):
        """
        Background audio processing - your original audio pipeline
        """
        audio_info = self._get_audio_info(payload)
        if not audio_info:
            logging.error("No audio information provided.")
            whatsapp_service.send_message(
                "Failed to process audio message.",
                WHATSAPP_TOKEN,
                from_number,
                phone_number_id
            )
            return

        target_lang_name = self.language_mapping.get(target_language, "English")
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
                    "Failed to retrieve audio file. Please try sending the audio again.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
                )
                return

            # Step 3: Download audio file
            whatsapp_service.send_message(
                "Downloading audio file...",
                WHATSAPP_TOKEN,
                from_number,
                phone_number_id,
            )
            
            local_audio_path = whatsapp_service.download_whatsapp_audio(
                audio_url, WHATSAPP_TOKEN
            )
            if not local_audio_path:
                logging.error("Failed to download audio from WhatsApp")
                whatsapp_service.send_message(
                    "Failed to download audio file. Please check your internet connection and try again.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
                )
                return

            # Step 4: Validate audio file
            try:
                audio_segment = AudioSegment.from_file(local_audio_path)
                duration_minutes = len(audio_segment) / (1000 * 60)
                file_size_mb = os.path.getsize(local_audio_path) / (1024 * 1024)
                
                logging.info(f"Audio validated - Duration: {duration_minutes:.1f}min, Size: {file_size_mb:.1f}MB")
                
                if duration_minutes > 10:
                    logging.info(f"Long audio file detected: {duration_minutes:.1f} minutes")
                    
            except CouldntDecodeError:
                logging.error("Downloaded audio file is corrupted")
                whatsapp_service.send_message(
                    "Audio file appears to be corrupted. Please try sending again.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
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
                    "Failed to upload audio. Please try again.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
                )
                return

            # Step 6: Transcribe
            whatsapp_service.send_message(
                f"Starting transcription to {target_lang_name}...",
                WHATSAPP_TOKEN,
                from_number,
                phone_number_id,
            )

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

            try:
                request_response = endpoint.run_sync(transcription_data, timeout=150)
            except Exception as e:
                logging.error(f"Transcription error: {str(e)}")
                whatsapp_service.send_message(
                    "An error occurred during transcription. Please try again later.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
                )
                return

            # Step 7: Validate transcription
            transcribed_text = request_response.get("audio_transcription", "").strip()
            if not transcribed_text:
                whatsapp_service.send_message(
                    "No speech detected. Please ensure you're speaking clearly and try again.",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id
                )
                return

            # Step 8: Process with UG40 using messages format
            if transcribed_text:
                whatsapp_service.send_message(
                    "Processing with language model...",
                    WHATSAPP_TOKEN,
                    from_number,
                    phone_number_id,
                )

                try:
                    # Build messages for audio transcription
                    messages = [
                        {
                            "role": "system",
                            "content": self.system_message
                        },
                        {
                            "role": "user",
                            "content": transcribed_text
                        }
                    ]
                    
                    ug40_response = run_inference(
                        model_type="qwen",
                        messages=messages
                    )
                    
                    final_response = ug40_response.get("content", "")
                    if final_response and not self._is_error_response(final_response):
                        whatsapp_service.send_message(
                            final_response,
                            WHATSAPP_TOKEN,
                            from_number,
                            phone_number_id
                        )
                        # Save the audio transcription and response
                        save_response(from_number, f"[AUDIO]: {transcribed_text}", final_response)
                    else:
                        # Fallback to just showing transcription
                        whatsapp_service.send_message(
                            f"Audio Transcription: \"{transcribed_text}\"\n\nYour message has been transcribed successfully!",
                            WHATSAPP_TOKEN,
                            from_number,
                            phone_number_id
                        )
                        
                except Exception as ug40_error:
                    logging.error(f"UG40 processing error: {str(ug40_error)}")
                    whatsapp_service.send_message(
                        f"Audio Transcription: \"{transcribed_text}\"\n\nYour message has been transcribed successfully!",
                        WHATSAPP_TOKEN,
                        from_number,
                        phone_number_id
                    )

        except Exception as e:
            logging.error(f"Unexpected error in audio processing: {str(e)}")
            whatsapp_service.send_message(
                "An unexpected error occurred while processing your audio. Please try again.",
                WHATSAPP_TOKEN,
                from_number,
                phone_number_id
            )
        finally:
            # Cleanup
            if local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.remove(local_audio_path)
                    logging.info("Cleaned up local audio file")
                except Exception as cleanup_error:
                    logging.warning(f"Could not clean up: {cleanup_error}")

    async def _handle_text_optimized(
        self, 
        payload: Dict, 
        target_language: str, 
        from_number: str, 
        sender_name: str
    ) -> ProcessingResult:
        """Optimized text processing without caching"""
        try:
            input_text = self._get_message_text(payload)
            message_id = self._get_message_id(payload)
            
            # Save message in background
            asyncio.create_task(self._save_message_async(from_number, input_text))

            # Quick command check first (most performance gain)
            command_result = self._handle_quick_commands(input_text, target_language, sender_name)
            if command_result:
                return command_result

            # Check if new user (direct DB call - no caching)
            conversation_pairs = get_user_last_five_conversation_pairs(from_number)
            is_new_user = len(conversation_pairs) == 0
            
            if is_new_user:
                return ProcessingResult("", ResponseType.TEMPLATE, template_name="welcome_message", should_save=False)

            # Build optimized prompt (limit context for speed)
            user_instruction = self._build_optimized_prompt(input_text, conversation_pairs[-2:])  # Only last 2
            
            # Call UG40 model with timeout
            response = await self._call_ug40_optimized(user_instruction)
            response_content = self._clean_response(response)
            
            # Save response in background only if not a technical error
            if response_content != "I'm having technical difficulties. Please try again.":
                asyncio.create_task(self._save_response_async(from_number, input_text, response_content, message_id))
            
            return ProcessingResult(response_content, ResponseType.TEXT)
            
        except Exception as e:
            logging.error(f"Error in text processing: {str(e)}")
            return ProcessingResult(
                "I'm experiencing issues. Please try again.",
                ResponseType.TEXT
            )

    def _handle_quick_commands(self, input_text: str, target_language: str, sender_name: str) -> Optional[ProcessingResult]:
        """Handle most common commands quickly"""
        text_lower = input_text.lower().strip()
        
        # Most common commands - return immediately without UG40 calls
        if text_lower in ['help', 'commands']:
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)
        elif text_lower == 'status':
            return ProcessingResult(self._get_status_text(target_language, sender_name), ResponseType.TEXT)
        elif text_lower in ['languages', 'language']:
            return ProcessingResult(self._get_languages_text(), ResponseType.TEXT)
        elif text_lower.startswith('set language'):
            return ProcessingResult("", ResponseType.TEMPLATE, template_name="choose_language")
        
        return None
    
    def _build_optimized_prompt(self, input_text: str, context: list) -> str:
        """Build prompt with clear separation between context and current message"""
        if not context:
            return f'Current message: "{input_text}"'
        
        # Format context more clearly to prevent confusion
        messages = [
            {"role": "system", "content": self.system_message},
        ]
        for i, conv in enumerate(context, 1):
            messages.append({"role": "user", "content": conv['user_message']})
            messages.append({"role": "assistant", "content": conv['bot_response']})

        return messages

    async def _call_ug40_optimized(self, messages: list, user_instruction: str) -> Dict:
        """Optimized UG40 call with shorter timeout"""
        try:
            logging.error(f"User instruction: {user_instruction}")
        
            response = run_inference(
                messages=messages,
                model="qwen"
                )
            return response
        except asyncio.TimeoutError:
            logging.error("UG40 call timed out")
            return {"content": "I'm running a bit slow right now. Please try again."}
        except Exception as e:
            logging.error(f"UG40 call error: {e}")
            return {"content": "I'm having technical difficulties. Please try again."}

    def _clean_response(self, ug40_response: Dict) -> str:
        """Clean and validate response"""
        content = ug40_response.get("content", "").strip()
        
        if not content:
            return "I'm having trouble understanding. Could you please rephrase?"
        
        return content

    # Async database operations
    async def _save_message_async(self, from_number: str, message: str):
        """Save message asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, save_message, from_number, message)
        except Exception as e:
            logging.error(f"Error saving message: {e}")

    async def _save_response_async(self, from_number: str, user_message: str, response: str, message_id: str):
        """Save response asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, save_response, from_number, user_message, response, message_id)
        except Exception as e:
            logging.error(f"Error saving response: {e}")

    async def _update_feedback_async(self, message_id: str, emoji: str):
        """Update feedback asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, update_feedback, message_id, emoji)
        except Exception as e:
            logging.error(f"Error updating feedback: {e}")

    # Utility methods
    def _get_message_id(self, payload: Dict) -> str:
        try:
            return payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
        except (KeyError, IndexError):
            return f"unknown_{int(time.time())}"

    def _get_message_text(self, payload: Dict) -> str:
        try:
            return payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
        except (KeyError, IndexError):
            return ""

    def _get_reaction(self, payload: Dict) -> Optional[Dict]:
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("reaction")
        except (KeyError, IndexError):
            return None
        
    def _get_interactive_response(self, payload: Dict) -> Optional[Dict]:
        """Extract interactive response from payload"""
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            return message.get("interactive")
        except (KeyError, IndexError):
            return None

    def _get_audio_info(self, payload: Dict) -> Optional[Dict]:
        try:
            message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
            if "audio" in message:
                return {"id": message["audio"]["id"], "mime_type": message["audio"]["mime_type"]}
        except (KeyError, IndexError):
            pass
        return None

    # Response generators
    def _handle_interactive(self, payload: Dict, sender_name: str, from_number: str) -> ProcessingResult:
        """Handle interactive button responses with improved feedback and language management"""
        try:
            interactive_response = self._get_interactive_response(payload)
            if not interactive_response:
                return ProcessingResult(
                    f"Dear {sender_name}, I didn't receive your selection properly. Please try again.",
                    ResponseType.TEXT,
                    should_save=False
                )

            # Handle different types of interactive responses
            if "list_reply" in interactive_response:
                return self._handle_list_reply(interactive_response["list_reply"], from_number, sender_name)
            elif "button_reply" in interactive_response:
                return self._handle_button_reply(interactive_response["button_reply"], from_number, sender_name)
            else:
                logging.warning(f"Unknown interactive response type: {interactive_response}")
                return ProcessingResult(
                    f"Dear {sender_name}, I received your response but couldn't process it. Please try again.",
                    ResponseType.TEXT,
                    should_save=False
                )
                
        except Exception as e:
            logging.error(f"Error handling interactive response: {e}")
            return ProcessingResult(
                f"Dear {sender_name}, I encountered an error processing your selection. Please try again.",
                ResponseType.TEXT,
                should_save=False
            )

    def _handle_list_reply(self, list_reply: Dict, from_number: str, sender_name: str) -> ProcessingResult:
        """Handle list selection responses with comprehensive error handling"""
        try:
            selected_id = list_reply.get("id", "")
            selected_title = list_reply.get("title", "")
            
            if not selected_id:
                return ProcessingResult(
                    f"Dear {sender_name}, I didn't receive your selection properly. Please try again.",
                    ResponseType.TEXT,
                    should_save=False
                )

            # Handle language selection
            if selected_id.startswith("lang_"):
                return self._handle_language_selection(selected_id, selected_title, from_number, sender_name)
            
            # Handle feedback selection
            elif selected_id.startswith("feedback_"):
                return self._handle_feedback_selection(selected_id, selected_title, from_number, sender_name)
            
            # Handle welcome/onboarding selections
            elif selected_id.startswith("welcome_"):
                return self._handle_welcome_selection(selected_id, selected_title, from_number, sender_name)
            
            # Unknown selection type
            else:
                logging.warning(f"Unknown list selection: {selected_id}")
                return ProcessingResult(
                    f"Thanks {sender_name}, I received your selection: {selected_title}",
                    ResponseType.TEXT,
                    should_save=True
                )
                
        except Exception as e:
            logging.error(f"Error handling list reply: {e}")
            return ProcessingResult(
                f"Dear {sender_name}, I encountered an error processing your selection. Please try again.",
                ResponseType.TEXT,
                should_save=False
            )

    def _handle_button_reply(self, button_reply: Dict, from_number: str, sender_name: str) -> ProcessingResult:
        """Handle button click responses with proper routing"""
        try:
            button_id = button_reply.get("id", "")
            button_title = button_reply.get("title", "")
            
            if not button_id:
                return ProcessingResult(
                    f"Dear {sender_name}, I didn't receive your selection properly. Please try again.",
                    ResponseType.TEXT,
                    should_save=False
                )

            # Route to specific handlers
            if button_id == "get_help":
                return ProcessingResult(self._get_help_text(), ResponseType.TEXT, should_save=True)
            
            elif button_id == "show_languages":
                return ProcessingResult("", ResponseType.TEMPLATE, template_name="choose_language", should_save=False)
            
            elif button_id == "start_chat":
                return ProcessingResult(
                    f"Perfect {sender_name}! I'm ready to help. You can:\n\n"
                    "• Send me text messages to translate or get help\n"
                    "• Send audio messages for transcription\n"
                    "• Ask me questions about Ugandan languages\n\n"
                    "Just type your message or send an audio - I'm here to help!",
                    ResponseType.TEXT,
                    should_save=True
                )
            
            elif button_id == "set_language":
                return ProcessingResult("", ResponseType.TEMPLATE, template_name="choose_language", should_save=False)
            
            # Unknown button
            else:
                logging.warning(f"Unknown button clicked: {button_id}")
                return ProcessingResult(
                    f"Thanks {sender_name} for clicking '{button_title}'!",
                    ResponseType.TEXT,
                    should_save=True
                )
                
        except Exception as e:
            logging.error(f"Error handling button reply: {e}")
            return ProcessingResult(
                f"Dear {sender_name}, I encountered an error processing your selection. Please try again.",
                ResponseType.TEXT,
                should_save=False
            )

    def _handle_language_selection(self, selected_id: str, selected_title: str, from_number: str, sender_name: str) -> ProcessingResult:
        """Handle language selection with validation and confirmation"""
        try:
            language_code = selected_id.replace("lang_", "")
            
            # Validate language code
            if language_code not in self.language_mapping:
                logging.error(f"Invalid language code selected: {language_code}")
                return ProcessingResult(
                    f"Sorry {sender_name}, there was an error with your language selection. Please try again.",
                    ResponseType.TEXT,
                    should_save=False
                )

            language_name = self.language_mapping[language_code]
            
            # Save the language preference
            try:
                save_user_preference(from_number, "preferred_language", language_code)
                logging.info(f"Language preference saved for {from_number}: {language_code}")
                
                return ProcessingResult(
                    f"✅ Language set to {language_name}!\n\n"
                    f"You can now:\n"
                    f"• Send messages in {language_name} or English\n"
                    f"• Ask me to translate to {language_name}\n"
                    f"• Send audio in {language_name} for transcription\n\n"
                    f"Just start typing or send an audio message!",
                    ResponseType.TEXT,
                    should_save=True
                )
                
            except Exception as db_error:
                logging.error(f"Database error saving language preference: {db_error}")
                return ProcessingResult(
                    f"I set your language to {language_name}, but there was a small issue saving it. "
                    f"You can still use the service normally!",
                    ResponseType.TEXT,
                    should_save=True
                )
                
        except Exception as e:
            logging.error(f"Error handling language selection: {e}")
            return ProcessingResult(
                f"Sorry {sender_name}, I encountered an error setting your language. Please try again.",
                ResponseType.TEXT,
                should_save=False
            )

    def _handle_feedback_selection(self, selected_id: str, selected_title: str, from_number: str, sender_name: str) -> ProcessingResult:
        """Handle feedback selection with proper saving"""
        try:
            feedback_type = selected_id.replace("feedback_", "")
            
            # Map feedback to emojis for consistency with reaction handling
            feedback_emoji_map = {
                "excellent": "👍",
                "good": "👍", 
                "fair": "👌",
                "poor": "👎"
            }
            
            emoji = feedback_emoji_map.get(feedback_type, "👍")
            
            # Try to get the most recent message ID for this user to link feedback
            # This is a simplified approach - in production you might want more sophisticated linking
            try:
                # You might want to store the message ID being referenced in the button payload
                # For now, we'll just log the feedback
                logging.info(f"Feedback received from {from_number}: {feedback_type} ({emoji})")
                
                # You could also save general feedback to the database
                save_message(from_number, f"FEEDBACK: {selected_title}")
                
                feedback_responses = {
                    "excellent": f"🌟 Thank you {sender_name}! I'm glad I could help you excellently.",
                    "good": f"😊 Thank you {sender_name}! I'm happy the response was helpful.",
                    "fair": f"👍 Thank you {sender_name} for the feedback. I'll keep improving!",
                    "poor": f"🤔 Thank you {sender_name} for the honest feedback. I'll work on doing better!"
                }
                
                response_message = feedback_responses.get(
                    feedback_type,
                    f"Thank you {sender_name} for your feedback! It helps me improve."
                )
                
                return ProcessingResult(response_message, ResponseType.TEXT, should_save=True)
                
            except Exception as save_error:
                logging.error(f"Error saving feedback: {save_error}")
                return ProcessingResult(
                    f"Thank you {sender_name} for your {selected_title.lower()} feedback! "
                    f"It helps us improve Sunflower.",
                    ResponseType.TEXT,
                    should_save=True
                )
                
        except Exception as e:
            logging.error(f"Error handling feedback selection: {e}")
            return ProcessingResult(
                f"Thank you {sender_name} for the feedback!",
                ResponseType.TEXT,
                should_save=True
            )

    def _handle_welcome_selection(self, selected_id: str, selected_title: str, from_number: str, sender_name: str) -> ProcessingResult:
        """Handle welcome/onboarding selections"""
        try:
            action = selected_id.replace("welcome_", "")
            
            if action == "get_help":
                return ProcessingResult(self._get_help_text(), ResponseType.TEXT, should_save=True)
            
            elif action == "show_languages":
                return ProcessingResult("", ResponseType.TEMPLATE, template_name="choose_language", should_save=False)
            
            elif action == "start_chat":
                return ProcessingResult(
                    f"Welcome {sender_name}! 🌻\n\n"
                    f"I'm ready to help you with:\n"
                    f"• Translations between Ugandan languages and English\n"
                    f"• Audio transcription in local languages\n"
                    f"• Language learning support\n\n"
                    f"Just send me a message or audio to get started!",
                    ResponseType.TEXT,
                    should_save=True
                )
            
            else:
                return ProcessingResult(
                    f"Thanks {sender_name} for selecting '{selected_title}'!",
                    ResponseType.TEXT,
                    should_save=True
                )
                
        except Exception as e:
            logging.error(f"Error handling welcome selection: {e}")
            return ProcessingResult(
                f"Welcome {sender_name}! How can I help you today?",
                ResponseType.TEXT,
                should_save=True
            )


    # Updated button creation methods with proper IDs

    def create_language_selection_button(self) -> Dict:
        """Create interactive button for language selection with proper IDs"""
        language_rows = []
        i = 1
        for code, name in self.language_mapping.items():
            language_rows.append({
                "id": f"row {i}",
                "title": name,
                "description": f"Set language to {name}"
            })
            i += 1
        
        return {
            "header": "Language Selection",
            "body": "Please select your preferred language for translations and responses:",
            "footer": "Powered by Sunbird AI",
            "action": {
                "button": "Select Language",
                "sections": [
                    {
                        "title": "Available Languages", 
                        "rows": language_rows
                    }
                ]
            }
        }

    def create_feedback_button(self) -> Dict:
        """Create feedback button with proper IDs"""
        return {
            "header": "Feedback",
            "body": "Please help us improve Sunflower with your feedback:",
            "footer": "Your feedback helps us serve you better",
            "action": {
                "button": "Rate Response",
                "sections": [
                    {
                        "title": "Response Quality",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Excellent",
                                "description": "Very helpful response"
                            },
                            {
                                "id": "row 2",
                                "title": "Good",
                                "description": "Helpful response"
                            },
                            {
                                "id": "row 3",
                                "title": "Fair", 
                                "description": "Somewhat helpful"
                            },
                            {
                                "id": "row 4",
                                "title": "Poor",
                                "description": "Not helpful"
                            }
                        ]
                    }
                ]
            }
        }

    def create_welcome_button(self) -> Dict:
        """Create welcome button for new users with proper IDs"""
        return {
            "header": "Welcome to Sunflower!",
            "body": "I'm your Ugandan language assistant. What would you like to do?",
            "footer": "Made by Sunbird AI",
            "action": {
                "button": "Get Started",
                "sections": [
                    {
                        "title": "Quick Actions",
                        "rows": [
                            {
                                "id": "row 1",
                                "title": "Get Help",
                                "description": "Learn what I can do"
                            },
                            {
                                "id": "row 2",
                                "title": "Set Language",
                                "description": "Choose your preferred language"
                            },
                            {
                                "id": "row 3",
                                "title": "Start Chatting",
                                "description": "Begin conversation"
                            }
                        ]
                    }
                ]
            }
        }
    
    def _get_help_text(self) -> str:
        return """Sunflower Assistant Commands

*Basic Commands:*
• `help` - Show this help message  
• `status` - Show your current settings
• `languages` - Show supported languages

*Language Commands:*
• `set language [name]` - Set your preferred language
Example: `set language luganda`

*Natural Questions:*
You can also ask naturally:
• "What can you do?"
• "What languages do you support?"

Just type your message normally - I'm here to help!"""

    def _get_status_text(self, target_language: str, sender_name: str) -> str:
        language_name = self.language_mapping.get(target_language, target_language)
        return f"""*Status for {sender_name}*

*Current Language:* {language_name} ({target_language})
*Assistant:* Sunflower by Sunbird AI
*Platform:* WhatsApp

Type `help` for available commands or just chat naturally!"""

    def _get_languages_text(self) -> str:
        languages_list = [f"• {name} ({code})" for code, name in sorted(self.language_mapping.items())]
        return f"""*Supported Languages*

{chr(10).join(languages_list)}

To set your language, type:
`set language [name]` or `set language [code]`

Example: `set language english`"""

