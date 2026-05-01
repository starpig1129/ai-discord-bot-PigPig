# Token & Secret Management

## Overview

The `addons/tokens.py` module manages sensitive credentials and API keys. It serves as the single source of truth for all secrets required by the PigPig Bot.

## Secret Loading

Secrets are loaded from two primary sources:
1. **`.env` File**: A local file containing `KEY=VALUE` pairs.
2. **Environment Variables**: System-level variables that override `.env`.

The module uses `python-dotenv` to ensure that local development is seamless.

## Managed Secrets

| Variable | Description | Requirement |
|----------|-------------|-------------|
| `TOKEN` | Discord Bot Token. | **Required** |
| `CLIENT_ID` | Discord Application ID. | **Required** |
| `BUG_REPORT_CHANNEL_ID` | Discord ID for centralized error logs. | **Required** |
| `GOOGLE_API_KEY` | Key for Gemini and Google Search. | Optional |
| `OPENAI_API_KEY` | Key for GPT-4 or OpenAI Embeddings. | Optional |
| `ANTHROPIC_API_KEY` | Key for Claude models. | Optional |
| `TENOR_API_KEY` | Key for searching GIFs. | Optional |

## Validation Logic

On startup, the `TOKENS` class performs a strict validation check:
- **Missing Required Vars**: If any critical tokens (Discord, Client ID, etc.) are missing, the bot will log a critical error and **terminate immediately** (`SystemExit(1)`).
- **Format Validation**: Ensures that IDs (like `BUG_REPORT_CHANNEL_ID`) are valid integers.
- **Optional Warnings**: If optional API keys (Gemini, OpenAI) are missing, it schedules an asynchronous warning via `func.report_error` to alert the admin.

## Usage

Access tokens globally via the `tokens` instance:

```python
from addons.tokens import tokens

if tokens.google_api_key:
    # Initialize Google client
```

---
> [!CAUTION]
> Never commit your `.env` file to version control. The repository includes a `.gitignore` entry to prevent accidental exposure of your secrets.