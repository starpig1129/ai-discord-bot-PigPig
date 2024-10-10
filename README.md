# PigPig: Advanced Multi-modal LLM Discord Bot

<p align="center">
  <a href="https://discord.gg/BvP64mqKzR">
    <img src="https://img.shields.io/discord/1212823415204085770?color=7289DA&label=Support&logo=discord&style=for-the-badge" alt="Discord">
  </a>
</p>

PigPig is a powerful Discord bot based on multi-modal Large Language Models (LLM), designed to interact with users through natural language. It combines advanced AI capabilities with practical features, offering a rich experience for Discord communities.

[Invite PigPig to your server](https://discord.com/oauth2/authorize?client_id=1208661941539704852&permissions=8&scope=bot)

## 🌟 Key Features

- 🧠 **AI-Powered Conversations**: Utilizes LLMs and LangChain for natural language understanding and generation.
- 🎵 **Advanced Music Player**: Stream music from various sources with playlist management and lyrics search.
- 🖼️ **Multi-modal Capabilities**: Visual question answering and image generation.
- 🍽️ **Practical Features**: Set reminders, get recommendations, and perform calculations.
- 👤 **User Information Management**: Create and maintain user profiles.
- 📊 **Channel Data RAG**: Use channel history for context-aware responses.

## 🖥️ System Requirements

- [Python 3.10+](https://www.python.org/downloads/)
- [Lavalink Server (4.0.0+)](https://github.com/freyacodes/Lavalink)
- [Modules in requirements](https://github.com/ChocoMeow/Vocard/blob/main/requirements.txt)
- NVIDIA GPU with at least 12GB VRAM (required for optimal AI performance)

## 📸 Feature Showcase
### Discord Bot

![alt text](readmeimg/image-4.png)

![alt text](readmeimg/image.png)

![alt text](readmeimg/image-1.png)

![alt text](readmeimg/image-2.png)

![alt text](readmeimg/image-3.png)

## 🚀 Quick Start
```sh
git clone https://github.com/starpig1129/discord-LLM-bot-PigPig.git  #Clone the repository
cd PigPig-discord-LLM-bot                                        #Go to the directory
python -m pip install -r requirements.txt          #Install required packages
```
After installing all packages, you must configure the bot before to start! [How To Configure](https://github.com/ChocoMeow/Vocard#configuration)<br />
Start your bot with `python main.py`

## ⚙️ Configuration
1. **Rename `.env Example` to `.env` and fill all the values**
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
```
| Values | Description |
| --- | --- |
| TOKEN | Your Discord bot token [(Discord Portal)](https://discord.com/developers/applications) |
| CLIENT_ID | Your Discord bot client id [(Discord Portal)](https://discord.com/developers/applications) |
| CLIENT_SECRET_ID | Your Discord bot client secret id [(Discord Portal)](https://discord.com/developers/applications) ***(optional)*** |
| SERCET_KEY | Secret key for dashboard ***(optional)*** |
| BUG_REPORT_CHANNEL_ID | All the error messages will send to this text channel ***(optional)*** |
| ANTHROPIC_API_KEY | Your Anthropic api key [(Anthropic API)](https://www.anthropic.com/api) ***(optional)*** |
| OPENAI_API_KEY | Your OpenAI api key [(OpenAI API)](https://openai.com/api/) ***(optional)*** |
1. **Rename `settings Example.json` to `settings.json` and customize your settings**
***(Note: Do not change any keys from `settings.json`)***
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


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.