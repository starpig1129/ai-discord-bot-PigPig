# PigPig：多模態大型語言模型 Discord 機器人

<p align="center">
  <a href="README.md">English</a> | <a href="README_zh-TW.md">繁體中文</a>
</p>

<p align="center">
  <a href="https://discord.gg/BvP64mqKzR">
    <img src="https://img.shields.io/discord/1212823415204085770?color=7289DA&label=Support&logo=discord&style=for-the-badge" alt="Discord">
  </a>
</p>

PigPig 是一個基於多模態大型語言模型 (LLM) 的強大 Discord 機器人，旨在透過自然語言與使用者互動。它結合了先進的 AI 功能與實用特性，為 Discord 社群提供豐富的體驗。

[邀請 PigPig 到您的伺服器](https://discord.com/oauth2/authorize?client_id=1208661941539704852&permissions=8&scope=bot)

## 🌟 主要功能

- 🧠 **AI 驅動的對話**: 使用 LLM 和 LangChain 進行自然語言理解和生成。
- 🖼️ **多模態功能**: 視覺問答和圖片生成。
- 🍽️ **實用功能**: 設定提醒事項、獲得推薦和執行計算。
- 👤 **使用者資訊管理**: 建立和維護使用者個人資料。
- 📊 **頻道資料 RAG**: 使用頻道歷史記錄來獲得具備情境感知的回應。
- 💭 **思維鏈推理 (Chain of Thought Reasoning)**：採用思維鏈推理來提供詳細的、循序漸進的思考過程說明，增強透明度和理解力。此功能允許機器人將複雜的問題分解成較小的、易於管理的步驟，提供更全面和有見地的回應。


## 🖥️ 系統需求

- [Python 3.10+](https://www.python.org/downloads/)
- [Lavalink 伺服器 (4.0.0+)](https://github.com/freyacodes/Lavalink)
- [requirements 中的模組](https://github.com/ChocoMeow/Vocard/blob/main/requirements.txt)
- 至少具有 12GB VRAM 的 NVIDIA GPU（最佳 AI 效能所需）

## 📸 功能展示
### Discord 機器人

![alt text](readmeimg/image-4.png)

![alt text](readmeimg/image.png)

![alt text](readmeimg/image-1.png)

![alt text](readmeimg/image-2.png)

![alt text](readmeimg/image-3.png)

## 🚀 快速入門
```sh
git clone https://github.com/starpig1129/discord-LLM-bot-PigPig.git  #複製儲存庫
cd PigPig-discord-LLM-bot                                        #進入目錄
python -m pip install -r requirements.txt          #安裝所需的套件
```
安裝所有套件後，您必須先設定機器人才能啟動！[如何設定](https://github.com/ChocoMeow/Vocard#configuration)<br />
使用 `python main.py` 啟動您的機器人

## ⚙️ 設定
1. **將 `.env Example` 重新命名為 `.env` 並填寫所有值**
```sh
TOKEN = XXXXXXXXXXXXXXXXXXXXXXXX.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX
CLIENT_ID = 123456789012345678
CLIENT_SECRET_ID = XXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXX
SERCET_KEY = DASHBOARD_SERCET_KEY

BUG_REPORT_CHANNEL_ID = 123456789012345678

LLM_MODEL_NAME = shenzhi-wang/Llama3-8B-Chinese-Chat
VQA_MODEL_NAME = openbmb/MiniCPM-Llama3-V-2_5-int4
ANTHROPIC_API_KEY = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
OPENAI_API_KEY = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GEMINI_API_KEY = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```
| 值 | 描述 |
|---|---|
| TOKEN | 您的 Discord 機器人權杖 [(Discord 入口網站)](https://discord.com/developers/applications) |
| CLIENT_ID | 您的 Discord 機器人客戶端 ID [(Discord 入口網站)](https://discord.com/developers/applications) |
| CLIENT_SECRET_ID | 您的 Discord 機器人客戶端秘密 ID [(Discord 入口網站)](https://discord.com/developers/applications) ***(選填)*** |
| SERCET_KEY | 儀表板的秘密金鑰 ***(選填)*** |
| BUG_REPORT_CHANNEL_ID | 所有錯誤訊息將會傳送到此文字頻道 ***(選填)*** |
| ANTHROPIC_API_KEY | 您的 Anthropic API 金鑰 [(Anthropic API)](https://www.anthropic.com/api) ***(選填)*** |
| OPENAI_API_KEY | 您的 OpenAI API 金鑰 [(OpenAI API)](https://openai.com/api/) ***(選填)*** |
| GEMINI_API_KEY | 您的 GEMINI API 金鑰 [(GEMINI API)](https://aistudio.google.com/app/apikey/) ***(選填)*** |
1. **將 `settings Example.json` 重新命名為 `settings.json` 並自訂您的設定**
***(注意：請勿更改 `settings.json` 中的任何金鑰)***
```json
{
    "prefix": "/",
    "activity": [
        {
            "paly": "\u5b78\u7fd2\u8aaa\u8a71"
        }
    ],
    "ipc_server": {
        "host": "127.0.0.1",
        "port": 8000,
        "enable": false
    },
    "version": "v1.2.0"
}
```

## Cogs 概述

此機器人採用模組化設計，包含數個 Cogs (模組) 來處理不同的功能。以下是簡要概述：

- **CoT_AI:** 實現思維鏈推理，提供詳細的、循序漸進的回應。
- **頻道管理器 (Channel Manager):** 管理特定頻道的設定和權限。
- **圖片生成 (Image Generation):** 基於文字提示生成圖片。
- **說明 (Help):** 提供可用指令的列表。
- **網路搜尋 (Internet Search):** 執行各種網路搜尋 (一般、圖片、YouTube、網址內容)。
- **數學 (Math):** 執行數學計算。
- **模型管理 (Model Management):** 載入和卸載語言模型。
- **提醒 (Reminder):** 為使用者設定提醒事項。
- **行程表 (Schedule):** 管理使用者行程表。
- **使用者資料 (User Data):** 管理使用者特定資料。
- **美食推薦 (Eat):** 提供美食推薦。


## 授權條款

此專案採用 MIT 授權條款授權 - 詳細資訊請參閱 [LICENSE](LICENSE) 檔案。
