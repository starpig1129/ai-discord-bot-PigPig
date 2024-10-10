import os
from dotenv import load_dotenv

class Settings:
    def __init__(self, settings: dict) -> None:
        self.invite_link: str = "https://discord.gg/BvP64mqKzR"
        self.bot_prefix: str = settings.get("prefix", "")
        self.activity: dict = settings.get("activity", [{"listen": "/help"}])
        self.ipc_server: dict = settings.get("ipc_server", {})
        self.version: str = settings.get("version", "")

class TOKENS:
    def __init__(self) -> None:
        load_dotenv()
        self.token = os.getenv("TOKEN")
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret_id = os.getenv("CLIENT_SECRET_ID")
        self.sercet_key = os.getenv("SERCET_KEY")
        self.bug_report_channel_id = int(os.getenv("BUG_REPORT_CHANNEL_ID"))