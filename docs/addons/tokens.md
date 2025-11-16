# TOKENS Module

**File:** [`addons/tokens.py`](addons/tokens.py)

The TOKENS module is responsible for managing all environment variables, API keys, and sensitive authentication tokens required for the Discord bot and its integrations. It provides secure loading and validation of sensitive configuration data.

## Overview

The `TOKENS` class centralizes all authentication and API key management, ensuring that sensitive data is:
- Loaded securely from environment variables
- Validated before bot startup
- Protected from accidental exposure
- Used consistently across the application

## Class: `TOKENS`

### Initialization

```python
class TOKENS:
    def __init__(self) -> None:
```

The `TOKENS` class automatically loads and validates all required environment variables upon instantiation.

### Properties

#### Core Bot Authentication
- **`token`** (str): Discord bot token for bot authentication
- **`client_id`** (str): Discord application client ID
- **`client_secret_id`** (str): Discord application client secret ID  
- **`sercet_key`** (str): Secret key for bot operations

#### User Management
- **`bot_owner_id`** (int): Discord user ID of the bot owner (0 if not set)
- **`bug_report_channel_id`** (int | None): Discord channel ID for bug reports

#### AI Service API Keys
- **`anthropic_api_key`** (str | None): Anthropic Claude API key
- **`openai_api_key`** (str | None): OpenAI API key
- **`google_api_key`** (str | None): Google API key (Gemini services)
- **`tenor_api_key`** (str | None): Tenor GIF API key
- **`vector_store_api_key`** (str | None): Vector store API key (for memory system)

### Environment Variable Loading

The module automatically loads environment variables using `python-dotenv`:

```python
from dotenv import load_dotenv

load_dotenv()  # Loads .env file automatically
```

### Required Environment Variables

The following environment variables are **required** for bot operation:

```
TOKEN=your_discord_bot_token
CLIENT_ID=your_discord_client_id
CLIENT_SECRET_ID=your_discord_client_secret
SERCET_KEY=your_secret_key
BOT_OWNER_ID=your_user_id
BUG_REPORT_CHANNEL_ID=channel_id_for_bugs
```

### Optional API Keys

These environment variables are **optional** but enable additional functionality:

```
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
TENOR_API_KEY=your_tenor_key
VECTOR_STORE_API_KEY=your_vector_store_key
```

## Security Validation

### `validate_environment_variables()` Method

The module performs comprehensive validation of all environment variables:

1. **Required Variables Check**: Verifies all essential variables are present
2. **Data Type Validation**: Ensures numeric IDs are valid integers
3. **API Key Warning**: Logs warnings for missing optional API keys
4. **Critical Error Handling**: Exits with SystemExit if required variables are missing

### Validation Rules

```python
# Required variables must not be empty
required_vars = {
    "TOKEN": self.token,
    "CLIENT_ID": self.client_id,
    "CLIENT_SECRET_ID": self.client_secret_id,
    "SERCET_KEY": self.sercet_key,
    "BUG_REPORT_CHANNEL_ID": os.getenv("BUG_REPORT_CHANNEL_ID"),
    "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID"),
}

# Numeric validation for IDs
if var_name == "BUG_REPORT_CHANNEL_ID":
    try:
        int(var_value)
    except (ValueError, TypeError):
        invalid_vars.append(f"{var_name} (must be valid integer)")
```

### Error Handling Strategy

1. **Primary**: Use `func.report_error()` for unified error reporting
2. **Fallback**: Print to stdout if error reporting system is unavailable
3. **Critical**: Exit with `SystemExit(1)` if required variables are missing

## Usage Examples

### Basic Token Access

```python
from addons.tokens import TOKENS, tokens

# Create instance (loads all environment variables)
tokens_instance = TOKENS()

# Access individual tokens
discord_token = tokens_instance.token
owner_id = tokens_instance.bot_owner_id
bug_channel = tokens_instance.bug_report_channel_id

# Check optional API keys
if tokens_instance.anthropic_api_key:
    print("Anthropic integration enabled")
```

### Using Pre-initialized Instance

```python
from addons import tokens

# Use the pre-initialized instance
if tokens.anthropic_api_key:
    # Initialize Anthropic client
    client = anthropic.Anthropic(api_key=tokens.anthropic_api_key)
```

### Environment Variable Setup

Create a `.env` file in your project root:

```env
# Discord Bot Configuration
TOKEN=your_discord_bot_token_here
CLIENT_ID=your_client_id_here
CLIENT_SECRET_ID=your_client_secret_here
SERCET_KEY=your_secret_key_here

# Bot Management
BOT_OWNER_ID=123456789012345678
BUG_REPORT_CHANNEL_ID=123456789012345678

# Optional API Keys
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
TENOR_API_KEY=your_tenor_key
VECTOR_STORE_API_KEY=your_vector_store_key
```

### Integration with Discord Bot

```python
import discord
from addons.tokens import tokens

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot logged in as {client.user}')

# Use token from TOKENS instance
client.run(tokens.token)
```

## Integration with Other Modules

### Error Reporting Integration

The TOKENS module integrates with the global error reporting system:

```python
try:
    from function import func
    asyncio.create_task(func.report_error(error, "addons/tokens.py/method_name"))
except Exception:
    # Fallback to local logging
    print(f"Error in TOKENS module: {e}")
```

### Configuration Loading

Used by other modules for authentication:

```python
# In settings.py
from addons.tokens import tokens
bot_owner_id = getattr(tokens, "bot_owner_id", 0)
```

## Error Scenarios and Handling

### Missing Required Variables

If required environment variables are missing:
1. Error logged via `func.report_error()`
2. User-friendly error message displayed
3. Program exits with `SystemExit(1)`

### Invalid Data Types

For invalid numeric IDs (non-integer values):
1. Specific error message indicates the problematic variable
2. Program exits to prevent runtime errors

### Optional API Keys Missing

For optional API keys:
1. Warning logged without stopping execution
2. Features that require those keys will be disabled
3. Bot operates with available functionality

## Security Best Practices

1. **Environment Files**: Always use `.env` files, never hardcode credentials
2. **File Permissions**: Restrict access to `.env` files (chmod 600)
3. **Version Control**: Add `.env` to `.gitignore`
4. **Key Rotation**: Regularly rotate API keys and tokens
5. **Monitoring**: Monitor API usage and key exposure

## Troubleshooting

### Common Issues

**"Environment variable validation failed"**
- Check that all required variables are set in `.env`
- Verify variable names match exactly (case-sensitive)
- Ensure no trailing spaces or quotes

**"BOT_OWNER_ID must be valid integer"**
- Check that BOT_OWNER_ID contains only digits
- Remove any formatting (commas, spaces, etc.)

**"ANTHROPIC_API_KEY not set"**
- This is a warning, not an error
- Bot will work but Claude integration disabled
- Set the key to enable Anthropic features

### Debugging Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Print all relevant variables (remove sensitive data in production)
print("Bot Owner ID:", os.getenv("BOT_OWNER_ID"))
print("Client ID:", os.getenv("CLIENT_ID"))
print("Has Token:", bool(os.getenv("TOKEN")))
```

## Related Documentation

- **[Settings Module](./settings.md):** Configuration management
- **[Update System](./update/index.md):** Automatic update system
- **[Error Handling Guide](../guides/error-handling.md):** Centralized error reporting

---

*Note: Always handle tokens and API keys with extreme care. Never commit them to version control or expose them in logs.*