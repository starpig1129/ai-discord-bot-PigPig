# PigPig: Advanced Multi-modal LLM Discord Bot

English | [繁體中文](README_zh-TW.md)

<p align="center">
  <a href="https://discord.gg/BvP64mqKzR">
    <img src="https://img.shields.io/discord/1212823415204085770?color=7289DA&label=Support&logo=discord&style=for-the-badge" alt="Discord">
  </a>
</p>

## Introduction

PigPig is a powerful, multi-modal Discord bot powered by Large Language Models (LLMs). It's designed to interact with users through natural language, combining advanced AI capabilities with practical, fun features to enrich any Discord community.

[**Invite PigPig to your server!**](https://discord.com/oauth2/authorize?client_id=1208661941539704852&permissions=8&scope=bot)

## 🌟 Key Features

*   🧠 **AI-Powered Conversations**: Utilizes advanced LLMs for natural language understanding and generation.
*   🖼️ **Multi-modal Capabilities**: Supports visual question answering (VQA) and AI image generation.
*   🎵 **Music Playback**: Plays music from YouTube with queue and playlist management.
*   🧠 **Intelligent Channel Memory**: Permanently stores and intelligently retrieves conversation history with semantic search to provide enhanced context for responses.
*   🔄 **Auto-Update System**: Automatically checks for and applies GitHub updates with secure backups and rollback functionality.
*   🍽️ **Practical Tools**: Set reminders, get restaurant recommendations, perform calculations, and more.
*   💭 **Chain of Thought Reasoning**: Provides detailed, step-by-step explanations of its thought process for enhanced transparency.

## 📸 Feature Showcase

![alt text](readmeimg/image-4.png)
![alt text](readmeimg/image.png)
![alt text](readmeimg/image-1.png)
![alt text](readmeimg/image-2.png)
![alt text](readmeimg/image-3.png)

## 🚀 Getting Started

### System Requirements

*   **Essential Dependencies:**
    *   [Python 3.10+](https://www.python.org/downloads/)
    *   [MongoDB](https://www.mongodb.com/) (For user data and certain features)
    *   [FFmpeg](https://ffmpeg.org/) (For music playback)
    *   Python packages listed in [`requirements.txt`](./requirements.txt)
*   **Hardware Requirements:**
    *   **GPU (Optional)**: An NVIDIA GPU with at least 12GB VRAM is recommended for running local models. The bot prioritizes API services, so a GPU is not required for most features.

### Installation Steps

```bash
# Clone the repository
git clone https://github.com/starpig1129/discord-LLM-bot-PigPig.git

# Navigate to the project directory
cd discord-LLM-bot-PigPig

# Install required Python packages
pip install -r requirements.txt
```

## ⚙️ Configuration

Follow these steps to configure your bot instance.

### Step 1: Configure `.env` file

Rename the `.env Example` file to `.env` and fill in the required values.

```env
# .env

# --- Discord Bot Credentials ---
TOKEN=XXXXXXXXXXXXXXXXXXXXXXXX.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX
CLIENT_ID=123456789012345678
CLIENT_SECRET_ID=XXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXX
SERCET_KEY=DASHBOARD_SERCET_KEY

# --- Bot Configuration ---
BOT_OWNER_ID=123456789012345678
BUG_REPORT_CHANNEL_ID=123456789012345678

# --- AI Model Configuration ---
MODEL_NAME=openbmb/MiniCPM-o-2_6
ANTHROPIC_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
OPENAI_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

| Variable              | Description                                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `TOKEN`               | **(Required)** Your Discord bot token from the [Discord Developer Portal](https://discord.com/developers/applications). |
| `CLIENT_ID`           | **(Required)** Your bot's client ID from the Developer Portal.                                             |
| `CLIENT_SECRET_ID`    | *(Optional)* Your bot's client secret, used for specific API interactions.                                 |
| `SERCET_KEY`          | *(Optional)* A secret key for dashboard authentication.                                                    |
| `BOT_OWNER_ID`        | **(Required)** Your Discord User ID. Grants owner-level privileges and is required for the auto-update system. |
| `BUG_REPORT_CHANNEL_ID` | *(Optional)* A Discord channel ID where error messages and bug reports will be sent.                       |
| `MODEL_NAME`          | The default local multi-modal model to use.                                                                |
| `ANTHROPIC_API_KEY`   | *(Optional)* Your API key for Anthropic's Claude models.                                                   |
| `OPENAI_API_KEY`      | *(Optional)* Your API key for OpenAI's GPT models.                                                         |
| `GEMINI_API_KEY`      | *(Optional)* Your API key for Google's Gemini models.                                                      |

### Step 2: Configure `settings.json` file

If a `settingsExample.json` file exists, rename it to `settings.json`. Otherwise, create it. This file controls the bot's behavior, features, and other operational parameters. Do not change the key names.

```json
{
    "prefix": "/",
    "activity": [
        {
            "paly": "學習說話"
        }
    ],
    "ipc_server": {
        "host": "127.0.0.1",
        "port": 8000,
        "enable": false
    },
    "version": "v2.2.11",
    "mongodb": "mongodb://localhost:27017/",
    "music_temp_base": "./temp/music",
    "model_priority": ["gemini", "local", "openai", "claude"],
    "auto_update": {
        "enabled": true,
        "check_interval": 21600,
        "require_owner_confirmation": true,
        "auto_restart": true
    },
    "notification": {
        "discord_dm": true,
        "update_channel_id": null,
        "notification_mentions": []
    },
    "security": {
        "backup_enabled": true,
        "max_backups": 5,
        "verify_downloads": true,
        "protected_files": ["settings.json", ".env", "data/"]
    },
    "restart": {
        "graceful_shutdown_timeout": 30,
        "restart_command": "python bot.py",
        "pre_restart_delay": 5
    },
    "github": {
        "repository": "starpig1129/ai-discord-bot-PigPig",
        "api_url": "https://github.com/starpig1129/ai-discord-bot-PigPig/releases/latest",
        "download_url": "https://github.com/starpig1129/ai-discord-bot-PigPig/archive/"
    },
    "ffmpeg": {
        "location": "/usr/bin/ffmpeg",
        "audio_quality": "192"
    }
}
```

### Step 3: Start the Bot

Once configured, you can start the bot with the following command:

```bash
python main.py
```

## 📦 Features / Cogs Overview

The bot uses a modular "Cogs" design, where each file represents a distinct feature set.

*   **Channel Manager**: Manages channel-specific settings and permissions.
*   **Image Generation**: Generates images from text prompts using AI.
*   **Internet Search**: Performs web searches to fetch up-to-date information.
*   **Language Manager**: Handles multi-language support and translations.
*   **Math**: Performs mathematical calculations.
*   **Memory System**: Manages the long-term conversation memory, enabling semantic search and context retrieval.
*   **Model Management**: Handles the loading and unloading of local AI models to manage resources.
*   **Music**: Provides full music playback functionality.
*   **Reminder**: Allows users to set and manage reminders.
*   **Story Manager**: Facilitates interactive, AI-driven story generation.
*   **System Prompt Manager**: Manages system prompts for different channels or servers.
*   **Update Manager**: Manages the automatic update process.
*   **User Data**: Manages user-specific data and profiles.
*   **Eat**: Provides intelligent restaurant and food recommendations.

## 📚 For Developers: Technical Documentation

The codebase is extensively documented. Below are links to the main documentation sections for developers:

| Module Category | Description | Documentation Link |
|---|---|---|
| **Core GPT Engine** | Handles LLM integration, response generation, and tools. | [`gpt/`](./docs/gpt/core/index.md) |
| **Addons** | Manages system-level features like auto-updates. | [`addons/`](./docs/addons/update/index.md) |
| **Cogs (Features)** | Core bot features and commands. | [`cogs/`](./docs/cogs/) |
| ↳ Eat System | Intelligent food recommendation module. | [`cogs/eat/`](./docs/cogs/eat/index.md) |
| ↳ Memory System | Manages long-term conversation memory. | [`cogs/memory/`](./docs/cogs/memory/index.md) |
| ↳ Music System | Handles music playback and queues. | [`cogs/music_lib/`](./docs/cogs/music_lib/index.md) |
| ↳ Story System | Interactive story generation module. | [`cogs/story/`](./docs/cogs/story/index.md) |
| ↳ System Prompt | Manages server and channel system prompts. | [`cogs/system_prompt/`](./docs/cogs/system_prompt/index.md) |

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.