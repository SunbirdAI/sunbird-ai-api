# Sunflower WhatsApp Tester Guide

This guide is for users who are testing the Sunflower WhatsApp assistant in production.

## What Sunflower Can Do

- Chat naturally in English or a supported Ugandan language
- Translate text
- Transcribe voice notes
- Send text replies, and optionally voice replies

## Supported Languages

- Luganda
- Acholi
- Ateso
- Lugbara
- Runyankole
- English

## How To Start

1. Open the WhatsApp chat with Sunflower.
2. Send a simple message like `Hello`.
3. Wait for the reply.
4. If you want, type `help` to see the available commands.

## Useful Commands

- `help` - Show available commands
- `status` - Show your current settings
- `languages` - Show supported languages
- `set language` - Open language selection
- `mode` - Choose how Sunflower should handle your messages
- `mode chat` - Normal assistant mode
- `mode translate` - Translation-only mode
- `mode transcribe` - Audio transcription-only mode
- `voice` - Choose text-only or text plus voice replies
- `voice on` - Enable voice replies
- `voice off` - Disable voice replies

## Simple Things To Test

- Send a normal text question
- Ask for a translation
- Change language and test again
- Switch to `mode translate` and send text
- Switch to `mode transcribe` and send a voice note
- Turn `voice on` and confirm you receive a voice reply

## Voice Note Tips

- Speak clearly
- Keep background noise low
- Keep the message short when possible
- If transcription fails, resend a clearer or shorter voice note

## What Testers Should Report

Please report:

- What you sent
- What Sunflower replied
- Whether the reply was correct or incorrect
- Whether the response was slow
- Whether buttons or language selection worked
- Whether voice notes were transcribed correctly

If possible, include screenshots.

## Important Notes

- Do not send highly sensitive personal information during testing.
- Small delays can happen, especially for voice notes.
- If something fails once, try the same action again and report both attempts.
