
# API Refactoring Plan: Standardize Sunbird AI Audio Endpoints

## Background

Our current API has evolved organically and now contains multiple overlapping endpoints for Speech-to-Text (STT) and Text-to-Speech (TTS). This has resulted in inconsistent API design, duplicated logic, and increased maintenance complexity.

We want to consolidate and standardize our APIs following modern REST patterns similar to the OpenAI API:

### Reference APIs

* `POST /v1/chat/completions`
* `POST /v1/audio/transcriptions`
* `POST /v1/audio/speech`

Reference:

* [OpenAI API Documentation](https://platform.openai.com/docs/api-reference?utm_source=chatgpt.com)

The goal is to create a clean, scalable, and maintainable API surface while preserving backward compatibility for existing consumers.

---

# High-Level Objectives

1. Consolidate multiple STT endpoints into a single transcription endpoint.
2. Consolidate multiple TTS endpoints into a single speech generation endpoint.
3. Preserve all existing functionality.
4. Maintain backward compatibility where possible.
5. Introduce a clear service abstraction layer to separate:

   * API routing
   * Business logic
   * Platform providers (Modal, Runpod, etc.)
6. Implement incrementally:

   * STT first
   * Verify functionality
   * Run tests
   * Then proceed to TTS

**Do not begin TTS implementation until STT migration has been completed and validated.**

---

# Existing Translation Endpoint

### Current Endpoint

```http
POST /tasks/translate
```

This endpoint already follows a reasonable design pattern and should remain unchanged.

### Action

* Keep existing implementation.
* Use it as a reference for request validation and endpoint structure.

---

# Phase 1: Speech-to-Text (STT) Consolidation

## Current Endpoints

The current STT implementation is fragmented across multiple endpoints:

```http
POST /tasks/stt_from_gcs
POST /tasks/stt
POST /tasks/org/stt
POST /tasks/modal/stt
```

### Existing Responsibilities

#### `/tasks/stt_from_gcs`

Transcribe audio stored in Google Cloud Storage.

Required:

```json
{
  "gcs_blob_name": "..."
}
```

---

#### `/tasks/stt`

RunPod-based transcription.

---

#### `/tasks/org/stt`

Organization-specific transcription workflow.

---

#### `/tasks/modal/stt`

Modal-based transcription workflow.

---

# New Unified Endpoint

Create a single endpoint:

```http
POST /tasks/audio/transcriptions
```

Similar to:

```http
POST /v1/audio/transcriptions
```

---

## Request Schema

### Required

```json
{
  "language": "lug"
}
```

Maintain support for all currently supported languages.

---

### Optional Inputs

#### Audio File

```json
{
  "audio": "<uploaded_file>"
}
```

If provided:

* Generate transcription from uploaded audio.

---

#### GCS Blob

```json
{
  "gcs_blob_name": "audio/file.wav"
}
```

If provided:

* Generate transcription from GCS object.

---

### Platform Selection

```json
{
  "platform": "modal"
}
```

Supported values:

```text
modal
runpod
```

Default:

```text
modal
```

---

### RunPod-Specific Options

```json
{
  "whisper": false,
  "recognise_speakers": false
}
```

Behavior:

* Only applicable when:

```json
{
  "platform": "runpod"
}
```

Defaults:

```json
{
  "whisper": true,
  "recognise_speakers": true
}
```

when RunPod is selected.

---

### Organization Workflow

```json
{
  "org": false
}
```

If:

```json
{
  "org": true
}
```

use the existing `/tasks/org/stt` processing logic.

---

# STT Refactoring Requirements

Before implementing:

1. Audit all existing STT endpoints.
2. Document:

   * Request schemas
   * Response schemas
   * Internal service calls
   * Platform-specific behavior
3. Identify shared logic.
4. Extract shared functionality into reusable services.
5. Create a migration strategy.

---

# STT Validation Checklist

Before proceeding to TTS:

## Functional Tests

Verify:

* Modal transcription
* RunPod transcription
* GCS transcription
* Uploaded-file transcription
* Organization workflow
* Speaker recognition
* Whisper mode
* All supported languages

---

## Backward Compatibility

Legacy endpoints should either:

### Option A

Remain functional and internally call:

```http
POST /tasks/audio/transcriptions
```

or

### Option B

Return deprecation warnings while continuing to work.

---

## Unit Tests

Ensure:

* Existing tests pass.
* New endpoint has coverage.
* Edge cases are covered.
* Invalid parameter combinations are validated.

---

# Phase 2: Text-to-Speech (TTS) Consolidation

**Do not start this phase until STT has been completed, tested, and approved.**

---

## Current Situation

We currently have multiple TTS implementations:

### TTS (Modal)

Uses:

```text
spark-tts
```

Platform:

```text
Modal
```

---

### TTS (Orpheus)

Uses:

```text
orpheus-3b-tts
```

Platform:

```text
Modal
```

Includes:

* Speaker listing
* Language speaker discovery
* Batch generation
* Additional Orpheus-specific workflows

---

### TTS (RunPod)

Uses:

```text
spark-tts
```

Platform:

```text
RunPod
```

---

# New Unified Endpoint

Create:

```http
POST /tasks/audio/speech
```

Similar to:

```http
POST /v1/audio/speech
```

---

## Request Schema

### Model Selection

```json
{
  "model": "orpheus-3b-tts"
}
```

Supported values:

```text
orpheus-3b-tts
spark-tts
```

Default:

```text
orpheus-3b-tts
```

---

### Platform Selection

```json
{
  "platform": "modal"
}
```

Supported values:

```text
modal
runpod
```

Default:

```text
modal
```

---

## Routing Rules

### Orpheus

If:

```json
{
  "model": "orpheus-3b-tts"
}
```

Use all existing Orpheus workflows:

* Speaker listing
* Language speakers
* Batch processing
* Voice synthesis

---

### Spark TTS via Modal

If:

```json
{
  "model": "spark-tts",
  "platform": "modal"
}
```

Use existing Modal Spark-TTS implementation.

---

### Spark TTS via RunPod

If:

```json
{
  "model": "spark-tts",
  "platform": "runpod"
}
```

Use existing RunPod implementation.

---

## TTS Refactoring Requirements

Before implementation:

1. Audit all current TTS endpoints.
2. Document:

   * Inputs
   * Outputs
   * Model-specific behavior
   * Platform-specific behavior
3. Design a provider abstraction layer.
4. Ensure no functionality is lost.

---

# Expected Deliverables

## Phase 1

### Architecture Document

Include:

* Current state
* Proposed state
* Migration strategy
* Risks
* Backward compatibility plan

---

### STT Refactor

* Unified endpoint
* Service abstraction
* Tests
* Documentation

---

### Validation Report

Provide:

* Test results
* Verified workflows
* Remaining issues

---

## Phase 2 (After Approval)

* Unified TTS endpoint
* Provider abstraction layer
* Tests
* Documentation
* Migration guide

---

# Implementation Constraints

1. Do not remove existing endpoints immediately.
2. Preserve backward compatibility.
3. Refactor incrementally.
4. Complete and validate STT before starting TTS.
5. Run unit and integration tests after every major change.
6. Prefer composition and service abstraction over duplicating logic.
7. Keep API naming consistent with OpenAI-style endpoint conventions.
8. Document every public API change.
