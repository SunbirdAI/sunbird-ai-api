# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sunbird AI API — a FastAPI application providing African language AI services (speech-to-text, translation, text-to-speech, language identification) deployed on Google Cloud Run with a PostgreSQL backend.

**Supported languages**: Acholi (ach), Ateso (teo), English (eng), Luganda (lug), Lugbara (lgg), Runyankole (nyn). Translation is always to/from English.

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

## Definition of Done

Every new feature, bug fix, or improvement — backend or frontend — must meet these criteria before being considered complete:

1. **Tests**: Write tests for the new/changed behavior. Run `pytest app/tests/ -v` (backend) or verify frontend builds with `npm run build` in `frontend/`. All tests must pass.
2. **Linting**: Run `make lint-check` (backend) and `npm run lint` in `frontend/`. Fix all issues before committing.
3. **Security audit (frontend)**: Run `npm audit` in `frontend/` after adding or updating any JS dependency. Flag any high/critical vulnerabilities and resolve them before proceeding. Do not ignore security warnings.

## Code Review Workflow

When making code changes (new features, refactors, improvements):

1. **Clarify first** — Before planning or implementing, ask clarifying questions about the request. Probe for missing details: edge cases, expected behavior, affected endpoints/pages, backward compatibility, and scope boundaries. Do not assume — surface ambiguity early so nothing is missed.
2. **Propose second** — After clarifications are resolved, present a summary of the planned changes: which files will be modified/created, what the approach is, and any trade-offs. Wait for approval before writing code.
3. **Review after implementation** — After implementing, present a summary of what changed and suggest any further improvements (performance, readability, security). Only apply improvement suggestions after explicit approval.
4. **No silent changes** — Do not make changes beyond what was discussed and approved. If you discover something that should be fixed along the way, flag it separately rather than bundling it in.

## Documentation Lookup

Always use Context7 MCP to fetch up-to-date library documentation when adding new features or working with libraries/frameworks (e.g., FastAPI, SQLAlchemy, Pydantic, Alembic). Do not rely solely on training data — library APIs change between versions.

## Rules

@.claude/rules/commands.md
@.claude/rules/architecture.md
@.claude/rules/database.md
@.claude/rules/routers.md
@.claude/rules/testing.md
@.claude/rules/frontend.md
