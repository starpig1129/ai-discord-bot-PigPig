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

## 📄 Legal Documents
To ensure user rights and service transparency, please refer to the following documents:

* **Terms of Service**: [TERMS\_OF\_SERVICE.md](docs/TERMS_OF_SERVICE.md)
* **Privacy Policy**: [PRIVACY\_POLICY.md](docs/PRIVACY_POLICY.md)
* **Support Email**: james911129@gmail.com
* **Support Server**: [https://discord.gg/BvP64mqKzR](https://discord.gg/BvP64mqKzR)

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

The bot's functionality is divided into modules called "Cogs". Here are the key features available:

---

### 🧠 Memory System
*   **Description:** Manages long-term conversation memory, enabling the bot to recall past interactions. It uses semantic search to find the most relevant context.
*   **Key Commands:** `/memory_search`, `/memory_stats`, `/memory_config`
*   **[Full Documentation](./docs/cogs/memory/index.md)**

---

### 🎵 Music
*   **Description:** Provides full music playback from YouTube, supporting song requests, queue management, playlists, and various playback modes.
*   **Key Commands:** `/play`, `/mode`, `/shuffle`
*   **[Full Documentation](./docs/cogs/music_lib/index.md)**

---

### 📖 Story Manager
*   **Description:** Facilitates interactive, collaborative storytelling using a multi-agent AI architecture to create dynamic narratives guided by user actions.
*   **Key Commands:** `/story`
*   **[Full Documentation](./docs/cogs/story/index.md)**

---

### 🍽️ Eat (Restaurant Recommendations)
*   **Description:** An intelligent engine that recommends restaurants by learning a server's food preferences through user ratings and feedback.
*   **Key Commands:** `/internet_search search_type: eat`
*   **[Full Documentation](./docs/cogs/eat/index.md)**

---

### 🖼️ Image Generation
*   **Description:** Generates and edits images from text prompts using advanced AI models, supporting both creation and instruction-based modification.
*   **Key Commands:** `/generate_image`
*   **[Full Documentation](./docs/cogs/gen_img.md)**

---

### 🌐 Internet Search
*   **Description:** A versatile tool to search the web, find images, look up YouTube videos, or fetch content from a URL.
*   **Key Commands:** `/internet_search`
*   **[Full Documentation](./docs/cogs/internet_search.md)**

---

### ⚙️ System Prompt Manager
*   **Description:** Allows deep customization of the bot's personality and behavior on a per-server or per-channel basis using a three-tiered inheritance model.
*   **Key Commands:** `/system_prompt`
*   **[Full Documentation](./docs/cogs/system_prompt/index.md)**

---

### ⏰ Reminder
*   **Description:** Allows users to set reminders for themselves or others using natural language for timing (e.g., "in 10 minutes" or a specific date).
*   **Key Commands:** `/remind`
*   **[Full Documentation](./docs/cogs/remind.md)**

---

### 🔄 Update Manager
*   **Description:** Provides a command interface to check for, initiate, and monitor the bot's automatic update process from GitHub.
*   **Key Commands:** `/update_check`, `/update_now`
*   **[Full Documentation](./docs/cogs/update_manager.md)**

---

### 🛂 Channel Manager
*   **Description:** Provides administrators with tools to control where the bot can interact, using server-wide policies and per-channel overrides.
*   **Key Commands:** `/set_server_mode`, `/set_channel_mode`, `/auto_response`
*   **[Full Documentation](./docs/cogs/channel_manager.md)**

---

### 👤 User Data
*   **Description:** A system for storing and managing user-specific data, which can be updated manually or merged intelligently by the AI.
*   **Key Commands:** `/userdata`
*   **[Full Documentation](./docs/cogs/userdata.md)**

---

### 🌍 Language Manager
*   **Description:** Manages multi-language support, allowing servers to set their preferred language for bot responses and commands.
*   **Key Commands:** `/set_language`, `/current_language`
*   **[Full Documentation](./docs/cogs/language_manager.md)**

---

### 🧠 Model Management
*   **Description:** A developer tool for the bot owner to dynamically load and unload the local AI model to manage GPU resources.
*   **Key Commands:** `/model_management`
*   **[Full Documentation](./docs/cogs/model_management.md)**

---

### 🧮 Math Calculator
*   **Description:** A secure tool for evaluating a wide range of mathematical expressions using the `sympy` library.
*   **Key Commands:** This is an internal tool, not a direct slash command.
*   **[Full Documentation](./docs/cogs/math.md)**

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