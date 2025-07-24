# PigPig: 先進的多模態大型語言模型 Discord 機器人

[English](README.md) | 繁體中文

<p align="center">
  <a href="https://discord.gg/BvP64mqKzR">
    <img src="https://img.shields.io/discord/1212823415204085770?color=7289DA&label=Support&logo=discord&style=for-the-badge" alt="Discord">
  </a>
</p>

## 簡介

PigPig 是一款由大型語言模型 (LLM) 驅動的強大、多模態 Discord 機器人。它旨在透過自然語言與使用者互動，結合先進的 AI 功能與實用、有趣的特性，豐富任何 Discord 社群。

[**邀請 PigPig 到您的伺服器！**](https://discord.com/oauth2/authorize?client_id=1208661941539704852&permissions=8&scope=bot)

## 🌟 主要功能

*   🧠 **AI 驅動的對話**：利用先進的大型語言模型進行自然語言理解與生成。
*   🖼️ **多模態能力**：支援視覺問答 (VQA) 和 AI 圖像生成。
*   🎵 **音樂播放**：從 YouTube 播放音樂，並提供佇列和播放清單管理。
*   🧠 **智慧頻道記憶**：永久儲存並透過語意搜尋智慧檢索對話歷史，為回應提供增強的上下文。
*   🔄 **自動更新系統**：自動檢查並應用 GitHub 更新，具備安全備份和還原功能。
*   🍽️ **實用工具**：設定提醒、獲取餐廳推薦、執行計算等。
*   💭 **思維鏈推理**：提供其思維過程的詳細、逐步解釋，以增強透明度。

## 📸 功能展示

![alt text](readmeimg/image-4.png)
![alt text](readmeimg/image.png)
![alt text](readmeimg/image-1.png)
![alt text](readmeimg/image-2.png)
![alt text](readmeimg/image-3.png)

## 🚀 開始使用

### 系統需求

*   **基本依賴項目：**
    *   [Python 3.10+](https://www.python.org/downloads/)
    *   [MongoDB](https://www.mongodb.com/) (用於使用者資料和特定功能)
    *   [FFmpeg](https://ffmpeg.org/) (用於音樂播放)
    *   [`requirements.txt`](./requirements.txt) 中列出的 Python 套件
*   **硬體需求：**
    *   **GPU (可選)**：建議使用至少 12GB VRAM 的 NVIDIA GPU 來運行本地模型。機器人優先使用 API 服務，因此大多數功能不需要 GPU。

### 安裝步驟

```bash
# 複製儲存庫
git clone https://github.com/starpig1129/discord-LLM-bot-PigPig.git

# 進入專案目錄
cd discord-LLM-bot-PigPig

# 安裝所需的 Python 套件
pip install -r requirements.txt
```

## ⚙️ 設定

請按照以下步驟設定您的機器人實例。

### 步驟 1：設定 `.env` 檔案

將 `.env Example` 檔案重新命名為 `.env` 並填入所需的值。

```env
# .env

# --- Discord 機器人憑證 ---
TOKEN=XXXXXXXXXXXXXXXXXXXXXXXX.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX
CLIENT_ID=123456789012345678
CLIENT_SECRET_ID=XXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXX
SERCET_KEY=DASHBOARD_SERCET_KEY

# --- 機器人設定 ---
BOT_OWNER_ID=123456789012345678
BUG_REPORT_CHANNEL_ID=123456789012345678

# --- AI 模型設定 ---
MODEL_NAME=openbmb/MiniCPM-o-2_6
ANTHROPIC_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
OPENAI_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

| 變數                  | 描述                                                                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `TOKEN`               | **(必要)** 您在 [Discord 開發者入口網站](https://discord.com/developers/applications) 取得的 Discord 機器人權杖。 |
| `CLIENT_ID`           | **(必要)** 您機器人的用戶端 ID，來自開發者入口網站。                                                         |
| `CLIENT_SECRET_ID`    | *(可選)* 您機器人的用戶端密鑰，用於特定的 API 互動。                                                         |
| `SERCET_KEY`          | *(可選)* 用於儀表板驗證的密鑰。                                                                            |
| `BOT_OWNER_ID`        | **(必要)** 您的 Discord 使用者 ID。授予擁有者等級的權限，並且是自動更新系統所必需的。                         |
| `BUG_REPORT_CHANNEL_ID` | *(可選)* 用於發送錯誤訊息和錯誤報告的 Discord 頻道 ID。                                                    |
| `MODEL_NAME`          | 預設使用的本地多模態模型。                                                                                 |
| `ANTHROPIC_API_KEY`   | *(可選)* 您用於 Anthropic 的 Claude 模型的 API 金鑰。                                                      |
| `OPENAI_API_KEY`      | *(可選)* 您用於 OpenAI 的 GPT 模型的 API 金鑰。                                                            |
| `GEMINI_API_KEY`      | *(可選)* 您用於 Google 的 Gemini 模型的 API 金鑰。                                                         |

### 步驟 2：設定 `settings.json` 檔案

如果存在 `settingsExample.json` 檔案，請將其重新命名為 `settings.json`。否則，請建立它。此檔案控制機器人的行為、功能和其他操作參數。請勿更改鍵名。

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

### 步驟 3：啟動機器人

設定完成後，您可以使用以下指令啟動機器人：

```bash
python main.py
```

## 📦 功能 / Cogs 總覽

機器人採用模組化的 "Cogs" 設計，其中每個檔案代表一組不同的功能。

*   **Channel Manager**：管理特定頻道的設定和權限。
*   **Image Generation**：使用 AI 從文字提示生成圖像。
*   **Internet Search**：執行網路搜尋以獲取最新資訊。
*   **Language Manager**：處理多語言支援和翻譯。
*   **Math**：執行數學計算。
*   **Memory System**：管理長期對話記憶，實現語意搜尋和上下文檢索。
*   **Model Management**：處理本地 AI 模型的載入和卸載以管理資源。
*   **Music**：提供完整的音樂播放功能。
*   **Reminder**：允許使用者設定和管理提醒。
*   **Story Manager**：促進互動式、由 AI 驅動的故事生成。
*   **System Prompt Manager**：管理不同頻道或伺服器的系統提示。
*   **Update Manager**：管理自動更新過程。
*   **User Data**：管理使用者特定的資料和設定檔。
*   **Eat**：提供智慧餐廳和美食推薦。

## 📚 開發者：技術文件

程式碼庫有廣泛的文件紀錄。以下是為開發者提供的主要文件部分的連結：

| 模組類別 | 描述 | 文件連結 |
|---|---|---|
| **核心 GPT 引擎** | 處理 LLM 整合、回應生成和工具。 | [`gpt/`](./docs/gpt/core/index.md) |
| **附加元件** | 管理系統級功能，如自動更新。 | [`addons/`](./docs/addons/update/index.md) |
| **Cogs (功能)** | 核心機器人功能和指令。 | [`cogs/`](./docs/cogs/) |
| ↳ Eat 系統 | 智慧美食推薦模組。 | [`cogs/eat/`](./docs/cogs/eat/index.md) |
| ↳ 記憶系統 | 管理長期對話記憶。 | [`cogs/memory/`](./docs/cogs/memory/index.md) |
| ↳ 音樂系統 | 處理音樂播放和佇列。 | [`cogs/music_lib/`](./docs/cogs/music_lib/index.md) |
| ↳ 故事系統 | 互動式故事生成模組。 | [`cogs/story/`](./docs/cogs/story/index.md) |
| ↳ 系統提示 | 管理伺服器和頻道的系統提示。 | [`cogs/system_prompt/`](./docs/cogs/system_prompt/index.md) |

## 授權

本專案採用 MIT 授權。詳情請參閱 `LICENSE` 檔案。
