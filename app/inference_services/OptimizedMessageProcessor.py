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
                result = self._handle_interactive(payload, sender_name)
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

    def _handle_interactive(self, payload: Dict, sender_name: str) -> ProcessingResult:
        """Handle interactive button responses"""
        try:
            interactive_response = self._get_interactive_response(payload)
            if interactive_response:
                # Handle different types of button responses
                if "list_reply" in interactive_response:
                    return self._handle_list_reply(interactive_response["list_reply"], sender_name)
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

            # Step 8: Process with UG40
            whatsapp_service.send_message(
                "Processing with language model...",
                WHATSAPP_TOKEN,
                from_number,
                phone_number_id,
            )

            try:
                ug40_response = run_inference(
                    transcribed_text, 
                    "qwen",
                    custom_system_message=self.system_message
                )
                
                final_response = ug40_response.get("content", "")
                if final_response:
                    whatsapp_service.send_message(
                        final_response,
                        WHATSAPP_TOKEN,
                        from_number,
                        phone_number_id
                    )
                else:
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
        if text_lower in ['help', 'commands', 'Help', 'HELP']:
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)
        elif text_lower == 'status':
            return ProcessingResult(self._get_status_text(target_language, sender_name), ResponseType.TEXT)
        elif text_lower in ['languages', 'language', 'Languages', 'LANGUAGES', 'Language', 'LANGUAGE']:
            return ProcessingResult(self._get_languages_text(), ResponseType.TEXT)
        elif text_lower.startswith('set language'):
            return ProcessingResult("", ResponseType.TEMPLATE, template_name="choose_language")
        
        return None
    
    def _build_optimized_prompt(self, input_text: str, context: list) -> str:
        """Build prompt with clear separation between context and current message"""
        if not context:
            return f'Current message: "{input_text}"'
        
        # Format context more clearly to prevent confusion
        context_str = ""
        for i, conv in enumerate(context, 1):
            user_msg = conv['user_message']
            bot_msg = conv['bot_response']
            context_str += f"\n{i}. User said: \"{user_msg}\"\n   You replied: \"{bot_msg}\""
        
        return (
            f"=== CONVERSATION HISTORY (for context only) ===\n"
            f"{context_str}\n\n"
            f"=== CURRENT MESSAGE (respond to this) ===\n"
            f'User: "{input_text}"\n\n'
            f"Your response:"
        )

    async def _call_ug40_optimized(self, user_instruction: str) -> Dict:
        """Optimized UG40 call with shorter timeout"""
        try:
            logging.error(f"User instruction: {user_instruction}")
        
            response = run_inference(
                user_instruction,
                "qwen",
                custom_system_message=self.system_message
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
    def _handle_list_reply(self, list_reply: Dict, sender_name: str) -> ProcessingResult:
        """Handle list selection responses"""
        selected_id = list_reply.get("id", "")
        selected_title = list_reply.get("title", "")
        
        # Handle language selection
        if selected_id.startswith("lang_"):
            language_code = selected_id.replace("lang_", "")
            if language_code in self.language_mapping:
                language_name = self.language_mapping[language_code]
                # Here you would typically save the user's language preference
                # save_user_language_preference(from_number, language_code)
                return ProcessingResult(
                    f"✅ Language set to {language_name}! You can now send messages in {language_name} or ask me to translate to {language_name}.",
                    ResponseType.TEXT
                )
        
        # Handle feedback selection
        elif selected_id.startswith("feedback_"):
            feedback_type = selected_id.replace("feedback_", "")
            return ProcessingResult(
                f"Thank you for your {feedback_type} feedback! It helps us improve Sunflower.",
                ResponseType.TEXT,
                should_save=False
            )
        
        return ProcessingResult(
            f"Thanks {sender_name}, I received your selection: {selected_title}",
            ResponseType.TEXT
        )

    def _handle_button_reply(self, button_reply: Dict, sender_name: str) -> ProcessingResult:
        """Handle button click responses"""
        button_id = button_reply.get("id", "")
        button_title = button_reply.get("title", "")
        
        if button_id == "get_help":
            return ProcessingResult(self._get_help_text(), ResponseType.TEXT)
        elif button_id == "show_languages":
            return ProcessingResult(
                "",
                ResponseType.BUTTON,
                button_data=self._create_language_selection_button()
            )
        
        return ProcessingResult(
            f"Thanks {sender_name}!",
            ResponseType.TEXT,
            should_save=False
        )

    def _create_language_selection_button(self) -> Dict:
        """Create interactive button for language selection"""
        language_rows = []
        for code, name in self.language_mapping.items():
            language_rows.append({
                "id": f"lang_{code}",
                "title": name,
                "description": f"Set language to {name}"
            })
        
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

    def _create_feedback_button(self) -> Dict:
        """Create feedback button"""
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
                                "id": "feedback_excellent",
                                "title": "Excellent",
                                "description": "Very helpful response"
                            },
                            {
                                "id": "feedback_good", 
                                "title": "Good",
                                "description": "Helpful response"
                            },
                            {
                                "id": "feedback_fair",
                                "title": "Fair", 
                                "description": "Somewhat helpful"
                            },
                            {
                                "id": "feedback_poor",
                                "title": "Poor",
                                "description": "Not helpful"
                            }
                        ]
                    }
                ]
            }
        }

    def _create_welcome_button(self) -> Dict:
        """Create welcome button for new users"""
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
                                "id": "get_help",
                                "title": "Get Help",
                                "description": "Learn what I can do"
                            },
                            {
                                "id": "show_languages",
                                "title": "Languages",
                                "description": "See supported languages"
                            },
                            {
                                "id": "start_chat",
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

