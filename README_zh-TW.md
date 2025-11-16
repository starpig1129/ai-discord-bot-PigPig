# PigPig: 先進的多模態大型語言模型 Discord 機器人

[English](README.md) | 繁體中文

<p align="center">
  <a href="https://discord.gg/BvP64mqKzR">
    <img src="https://img.shields.io/discord/1212823415204085770?color=7289DA&label=Support&logo=discord&style=for-the-badge" alt="Discord">
  </a>
</p>

## 簡介

PigPig 是一款由大型語言模型 (LLM) 驅動的強大、多模態 Discord 機器人。透過自然語言與使用者互動，結合先進的 AI 功能與實用、有趣的特性，豐富任何 Discord 社群。

[**邀請 PigPig 到您的伺服器！**](https://discord.com/oauth2/authorize?client_id=1208661941539704852&permissions=4292493394706417&integration_type=0&scope=bot+applications.commands)

## 📄 法律文件
為了確保使用者權益與服務透明度，請參閱以下文件：

* **服務條款 (Terms of Service)**：[TERMS_OF_SERVICE.md](docs/TERMS_OF_SERVICE.md)
* **隱私權政策 (Privacy Policy)**：[PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md)
* **支援信箱**：james911129@gmail.com
* **支援伺服器**：[https://discord.gg/BvP64mqKzR](https://discord.gg/BvP64mqKzR)

## 🌟 主要功能

*   🧠 **AI 驅動的對話**：利用先進的大型語言模型進行自然語言理解與生成。
*   🖼️ **多模態能力**：支援視覺問答 (VQA) 和 AI 圖像生成。
*   🎵 **音樂播放**：從 YouTube 播放音樂，並提供佇列和播放清單管理。
*   🧠 **智慧頻道記憶**：永久儲存並透過語意搜尋智慧檢索對話歷史，為回應提供增強的上下文。
*   🔄 **自動更新系統**：自動檢查並應用 GitHub 更新，具備安全備份和還原功能。
*   🍽️ **實用工具**：設定提醒、獲取餐廳推薦、執行計算等。

## 📸 功能展示

![alt text](readmeimg/image-4.png)
![alt text](readmeimg/image.png)
![alt text](readmeimg/image-1.png)
![alt text](readmeimg/image-2.png)
![alt text](readmeimg/image-3.png)

## 🚀 開始使用

### 系統需求

*   **基本依賴項目：**
    *   [Python 3.11+](https://www.python.org/downloads/)
    *   [FFmpeg](https://ffmpeg.org/) (用於音樂播放)
    
    **FFmpeg 安裝：**
    *   **Ubuntu/Debian：** `sudo apt update && sudo apt install ffmpeg`
    *   **CentOS/RHEL：** `sudo yum install epel-release && sudo yum install ffmpeg`
    *   **macOS：** `brew install ffmpeg`
    *   **Windows：** 從 [FFmpeg Windows builds](https://www.gyan.dev/ffmpeg/builds/) 下載
    
    *   [`requirements.txt`](./requirements.txt) 中列出的 Python 套件

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

# --- 向量資料庫 API 金鑰 ---
VECTOR_STORE_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# --- 機器人設定檔路徑 ---
CONFIG_ROOT="/path/to/your/config"
```

| 變數                  | 描述                                                                                                       |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `TOKEN`               | **(必要)** 您在 [Discord 開發者入口網站](https://discord.com/developers/applications) 取得的 Discord 機器人權杖。 |
| `CLIENT_ID`           | **(必要)** 您機器人的用戶端 ID，來自開發者入口網站。                                                         |
| `CLIENT_SECRET_ID`    | *(可選)* 您機器人的用戶端密鑰，用於特定的 API 互動。                                                         |
| `SERCET_KEY`          | *(可選)* 用於儀表板驗證的密鑰。                                                                            |
| `BOT_OWNER_ID`        | **(必要)** 您的 Discord 使用者 ID。授予擁有者等級的權限，並且是自動更新系統所必需的。                             |
| `BUG_REPORT_CHANNEL_ID` | *(可選)* 用於發送錯誤訊息和錯誤報告的 Discord 頻道 ID。                                                    |
| `MODEL_NAME`          | 要使用的預設本地多模態模型。                                                                                 |
| `ANTHROPIC_API_KEY`   | *(可選)* 您用於 Anthropic 的 Claude 模型的 API 金鑰，可以在[Anthropic 官方網站](https://www.anthropic.com/)取得。                                                      |
| `OPENAI_API_KEY`      | *(可選)* 您用於 OpenAI 的 GPT 模型的 API 金鑰，可以在[OpenAI 官方網站](https://platform.openai.com/)取得。                                                            |
| `GEMINI_API_KEY`      | *(可選)* 您用於 Google 的 Gemini 模型的 API 金鑰，可以在[Google AI Studio](https://aistudio.google.com/)取得。                                                         |
| `VECTOR_STORE_API_KEY` | *(可選)* 您用於向量資料庫（如 Qdrant）的 API 金鑰，若使用雲端資料庫才需要。                                     |
| `CONFIG_ROOT`         | *(可選)* 自訂設定檔和資料的根目錄路徑。預設為當前目錄下的 `./base_configs` 資料夾。                               |

### 步驟 2：設定 `configs` 資料夾

機器人預設檔案在 [./base_configs](./base_configs) 資料夾中。您可以根據需要編輯這些 JSON 檔案來自訂機器人行為，建議複製一份並且在 '.env' 中設定 'CONFIG_ROOT' 參數。

### 步驟 3：設定長期記憶系統
如果您不希望啟用長期記憶系統，請在 `base_configs/memory.yaml` 中將 `enabled` 設為 `false`。
如果您使用雲端向量資料庫（如 Qdrant），請在 `.env` 檔案中設定 `VECTOR_STORE_API_KEY`。
並且確保在 `base_configs/memory.yaml` 中正確設定向量資料庫的 URL 和其他參數。
本地安裝方式或是雲端設定方法可以參考[Qdrant 官方文件](https://qdrant.tech/documentation/).

### 步驟 4：啟動機器人

設定完成後，您可以使用以下指令啟動機器人：

```bash
python main.py
```

## 📦 功能 / Cogs 總覽

機器人的功能被劃分為稱為 "Cogs" 的模組。以下是可用的主要功能：

---

### 🧠 記憶系統 (Memory System)
*   **描述：** 管理長期對話記憶，使機器人能夠回憶過去的互動。它使用語意搜尋來尋找最相關的上下文。
*   **主要指令：** `/memory_search`, `/memory_stats`, `/memory_config`
*   **[完整文件](./docs/cogs/memory/index.md)**

---

### 🎵 音樂 (Music)
*   **描述：** 提供完整的 YouTube 音樂播放功能，支援歌曲點播、佇列管理、播放清單和多種播放模式。
*   **主要指令：** `/play`, `/mode`, `/shuffle`
*   **[完整文件](./docs/cogs/music_lib/index.md)**

---

### 📖 故事管理員 (Story Manager)
*   **描述：** 利用多代理 (multi-agent) AI 架構，促進互動式、協作性的故事創作，根據使用者的行動創造動態的敘事。
*   **主要指令：** `/story`
*   **[完整文件](./docs/cogs/story_manager.md)**

---

### 🍽️ 吃什麼 (Eat - 餐廳推薦)
*   **描述：** 一個智慧引擎，透過學習伺服器使用者的評分和回饋，來推薦餐廳，從而了解伺服器的美食偏好。
*   **主要指令：** `/internet_search search_type: eat`
*   **[完整文件](./docs/cogs/eat/index.md)**

---

### 🖼️ 圖像生成 (Image Generation)
*   **描述：** 使用先進的 AI 模型，根據文字提示生成和編輯圖像，支援從頭創作和基於指令的修改。
*   **主要指令：** `/generate_image`
*   **[完整文件](./docs/cogs/gen_img.md)**

---

### 🌐 網路搜尋 (Internet Search)
*   **描述：** 一個多功能工具，可用於搜尋網頁、尋找圖片、查詢 YouTube 影片或從 URL 獲取內容。
*   **主要指令：** `/internet_search`
*   **[完整文件](./docs/cogs/internet_search.md)**

---

### ⚙️ 系統提示管理員 (System Prompt Manager)
*   **描述：** 允許透過三層繼承模型，對每個伺服器或每個頻道的機器人個性和行為進行深度客製化。
*   **主要指令：** `/system_prompt`
*   **[完整文件](./docs/cogs/system_prompt_manager.md)**

---

### ⏰ 提醒 (Reminder)
*   **描述：** 允許使用者為自己或他人設定提醒，可使用自然語言來指定時間（例如「10 分鐘後」或特定日期）。
*   **主要指令：** `/remind`
*   **[完整文件](./docs/cogs/remind.md)**

---

### 📅 排程管理員 (Schedule Manager)
*   **描述：** 使用 YAML 檔案管理伺服器排程，允許使用者透過自然語言上傳、查詢和更新排程。
*   **主要指令：** `/upload_schedule`, `/query_schedule`, `/update_schedule`
*   **[完整文件](./docs/cogs/schedule.md)**

---

### 🔄 更新管理員 (Update Manager)
*   **描述：** 提供一個指令介面，用於檢查、啟動和監控機器人從 GitHub 進行的自動更新過程。
*   **主要指令：** `/update_check`, `/update_now`
*   **[完整文件](./docs/cogs/update_manager.md)**

---

### 🛂 頻道管理員 (Channel Manager)
*   **描述：** 為管理員提供工具，透過伺服器範圍的政策和個別頻道的覆寫，來控制機器人可以互動的範圍。
*   **主要指令：** `/set_server_mode`, `/set_channel_mode`, `/auto_response`
*   **[完整文件](./docs/cogs/channel_manager.md)**

---

### 👤 使用者資料 (User Data)
*   **描述：** 一個用於儲存和管理使用者特定資料的系統，可以手動更新或由 AI 智慧合併。
*   **主要指令：** `/userdata`
*   **[完整文件](./docs/cogs/userdata.md)**

---

### 🌍 語言管理員 (Language Manager)
*   **描述：** 管理多語言支援，允許伺服器設定機器人回應和指令的首選語言。
*   **主要指令：** `/set_language`, `/current_language`
*   **[完整文件](./docs/cogs/language_manager.md)**

---

### 🧠 模型管理 (Model Management)
*   **描述：** 一個為機器人擁有者設計的開發者工具，用於動態載入和卸載本地 AI 模型，以管理 GPU 資源。
*   **主要指令：** `/model_management`
*   **[完整文件](./docs/cogs/model_management.md)**

---

### 🧮 數學計算機 (Math Calculator)
*   **描述：** 一個使用 `sympy` 函式庫來安全評估各種數學表達式的工具。
*   **主要指令：** 這是一個內部工具，沒有直接的斜線指令。
*   **[完整文件](./docs/cogs/math.md)**

---

### 📝 摘要工具 (Summarizer)
*   **描述：** 使用 AI 摘要頻道對話，附帶訊息來源歸屬和可自訂的限制。
*   **主要指令：** `/summarize`
*   **[完整文件](./docs/cogs/summarizer.md)**

---

### 🔍 GIF 工具 (GIF Tools)
*   **描述：** 為 Discord 伺服器搜尋和管理 GIF 內容，具備智慧配對功能。
*   **主要指令：** `/search_gif`
*   **[完整文件](./docs/cogs/gif_tools.md)**

---

### 🤖 機器人資訊 (Bot Info)
*   **描述：** 顯示機器人的詳細資訊，包括運行時間、版本和系統狀態。
*   **主要指令：** `/botinfo`
*   **[文件](./docs/cogs/) (一般文件區域)**

---

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
| ↳ 故事系統 | 互動式故事生成模組。 | [`cogs/story/`](./docs/cogs/story_manager.md) |
| ↳ 系統提示 | 管理伺服器和頻道的系統提示。 | [`cogs/system_prompt/`](./docs/cogs/system_prompt_manager.md) |

## 授權

本專案採用 MIT 授權。詳情請參閱 `LICENSE` 檔案。
