# WhatsApp Service Update: UG40 Model Integration

## Overview
This update replaces the OpenAI-based message classification system with your custom UG40 model while maintaining all the existing OpenAI methods for backward compatibility.

## Changes Made

### 1. New UG40 Inference Service
- **File**: `app/inference_services/ug40_inference.py`
- **Purpose**: Handles communication with your UG40 models (Gemma and Qwen) via RunPod
- **Features**:
  - Exponential backoff retry logic for model loading
  - Support for both Gemma and Qwen UG40 models
  - Comprehensive error handling
  - OpenAI-compatible API integration
  - Automatic response cleaning (removes `<think>` tags)

### 2. Updated WhatsApp Service
- **File**: `app/inference_services/whatsapp_service.py`
- **New Method**: `handle_ug40_message()` - Main handler for UG40-powered message processing
- **Helper Methods**:
  - `_handle_audio_with_ug40()` - Processes audio messages using UG40
  - `_handle_text_with_ug40()` - Processes text messages using UG40
- **Features**:
  - Intelligent message classification and routing
  - Advanced audio transcription with UG40 processing
  - Context-aware conversation handling
  - JSON-structured responses from UG40 model
  - Fallback to existing translation methods if UG40 fails

### 3. Updated Tasks Router
- **File**: `app/routers/tasks.py`
- **Change**: Webhook now uses `handle_ug40_message()` instead of `handle_openai_message()`
- **Backward Compatibility**: OpenAI method call is commented out but preserved

## UG40 Model Capabilities

The UG40 model integration supports:

### Text Processing
- **Language Detection**: Automatic detection of Ugandan languages
- **Translation**: Between Ugandan languages and English
- **Conversation**: Natural dialogue handling
- **Language Setting**: User preference management
- **Help**: Contextual assistance

### Audio Processing
- **Transcription**: Audio to text conversion
- **Language Processing**: UG40-powered transcription analysis
- **Translation**: Audio content translation
- **Response Generation**: Intelligent audio message responses

## Environment Variables Required

Add these to your `.env` file:

```bash
# Existing (should already be set)
RUNPOD_API_KEY=your_runpod_api_key

# New for UG40 models
GEMMA_ENDPOINT_ID=your_gemma_endpoint_id
QWEN_ENDPOINT_ID=your_qwen_endpoint_id
```

## UG40 Model Endpoints

The system expects these models to be deployed on RunPod:
- `patrickcmd/gemma3-12b-ug40-merged`
- `patrickcmd/qwen3-14b-ug40-merged`

## Response Format

The UG40 model returns structured JSON responses:

```json
{
  "task": "translation|greeting|setLanguage|help|conversation",
  "detected_language": "language_code",
  "target_language": "target_language_code",
  "text_to_translate": "text_if_needed",
  "response": "response_to_user",
  "needs_translation": true/false,
  "translation": "translated_text_if_needed"
}
```

## Error Handling

### Retry Logic
- **Model Loading**: Automatic retry when models are cold-starting
- **Timeouts**: Exponential backoff for temporary failures
- **Network Issues**: Connection error handling

### Fallback Strategy
1. UG40 model processing
2. If UG40 fails → Basic translation service
3. If all fails → User-friendly error message

## Migration Notes

### Switching Back to OpenAI (if needed)
In `app/routers/tasks.py`, comment out the UG40 line and uncomment the OpenAI line:

```python
# Use OpenAI
message = whatsapp_service.handle_openai_message(...)

# Use UG40 (current)
# message = whatsapp_service.handle_ug40_message(...)
```

### Testing
1. Ensure environment variables are set
2. Deploy UG40 models to RunPod
3. Test with various message types:
   - Simple text messages
   - Language change requests
   - Audio messages
   - Greetings and help requests

## Benefits of UG40 Integration

1. **Cultural Context**: Better understanding of Ugandan languages and contexts
2. **Local Expertise**: Specialized knowledge of local languages
3. **Cost Control**: Reduced dependency on external APIs
4. **Customization**: Ability to fine-tune for specific use cases
5. **Performance**: Optimized for Ugandan language tasks

## Monitoring and Logging

The system includes comprehensive logging:
- UG40 model request/response logging
- Processing time tracking
- Error classification and reporting
- Fallback mechanism activation

## Next Steps

1. Set up the required environment variables
2. Deploy the UG40 models to RunPod
3. Test the integration thoroughly
4. Monitor performance and adjust as needed
5. Consider gradual rollout if needed
