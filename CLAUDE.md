# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sunbird AI API — a FastAPI application providing African language AI services (speech-to-text, translation, text-to-speech, language identification) deployed on Google Cloud Run with a PostgreSQL backend.

## Required Environment Variables

```
SECRET_KEY
DATABASE_URL
RUNPOD_API_KEY
REDIS_URL
RUNPOD_ENDPOINT
AUDIO_CONTENT_BUCKET_NAME
VERIFY_TOKEN          # WhatsApp webhook verification
```

See `app/core/config.py` for the full list of optional variables (OAuth, Firebase, email, GCP).

## Rules

@.claude/rules/commands.md
@.claude/rules/architecture.md
