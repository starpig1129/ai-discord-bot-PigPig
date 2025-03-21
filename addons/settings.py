import json
import os
from dotenv import load_dotenv

class Settings:
    def __init__(self, settings_path: str = "settings.json") -> None:
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        self.invite_link: str = "https://discord.gg/BvP64mqKzR"
        self.bot_prefix: str = settings.get("prefix", "")
        self.activity: dict = settings.get("activity", [{"listen": "/help"}])
        self.ipc_server: dict = settings.get("ipc_server", {})
        self.version: str = settings.get("version", "")
        self.mongodb_uri: str = settings.get("mongodb", "")
        self.music_temp_base: str = settings.get("music_temp_base", "./temp/music")
        self.model_priority: list = settings.get("model_priority", ["gemini","local", "openai", "claude"])

class TOKENS:
    def __init__(self) -> None:
        load_dotenv()
        self.token = os.getenv("TOKEN")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret_id = os.getenv("CLIENT_SECRET_ID")
        self.sercet_key = os.getenv("SERCET_KEY")
        self.bug_report_channel_id = int(os.getenv("BUG_REPORT_CHANNEL_ID"))
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY",None)
        self.openai_api_key = os.getenv("OPENAI_API_KEY",None)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY",None)
        self.tenor_api_key = os.getenv("TENOR_API_KEY",None)
