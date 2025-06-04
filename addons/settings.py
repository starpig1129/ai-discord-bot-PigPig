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
        
        # 自動更新配置
        self.auto_update: dict = settings.get("auto_update", {
            "enabled": True,
            "check_interval": 21600,
            "require_owner_confirmation": True,
            "auto_restart": True
        })
        self.notification: dict = settings.get("notification", {
            "discord_dm": True,
            "update_channel_id": None,
            "notification_mentions": []
        })
        self.security: dict = settings.get("security", {
            "backup_enabled": True,
            "max_backups": 5,
            "verify_downloads": True,
            "protected_files": [
                "settings.json",
                ".env",
                "data/schedule/",
                "data/dialogue_history.json",
                "data/channel_configs/",
                "data/user_data/",
                "data/update_logs/"
            ]
        })
        self.restart: dict = settings.get("restart", {
            "graceful_shutdown_timeout": 30,
            "restart_command": "python main.py",
            "pre_restart_delay": 5
        })
        self.github: dict = settings.get("github", {
            "repository": "starpig1129/ai-discord-bot-PigPig",
            "api_url": "https://api.github.com/repos/starpig1129/ai-discord-bot-PigPig/releases/latest",
            "download_url": "https://github.com/starpig1129/ai-discord-bot-PigPig/archive/"
        })

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
        
        # 新增：Bot 擁有者配置
        self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", 0))

class UpdateSettings:
    """更新系統配置管理器"""
    
    def __init__(self, settings_path: str = "settings.json"):
        """
        初始化更新配置
        
        Args:
            settings_path: 主要設定檔案路徑
        """
        load_dotenv()
        
        # 從環境變數讀取 Bot 擁有者 ID
        self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", 0))
        
        # 從統一設定檔讀取配置
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                main_settings = json.load(f)
            
            self.config = {
                "auto_update": main_settings.get("auto_update", self._get_default_auto_update()),
                "notification": main_settings.get("notification", self._get_default_notification()),
                "security": main_settings.get("security", self._get_default_security()),
                "restart": main_settings.get("restart", self._get_default_restart()),
                "github": main_settings.get("github", self._get_default_github())
            }
            
        except Exception as e:
            print(f"載入更新配置失敗: {e}")
            self.config = self._get_default_config()
        
        # 更新相關配置
        self.auto_update = self.config.get("auto_update", {})
        self.notification = self.config.get("notification", {})
        self.security = self.config.get("security", {})
        self.restart = self.config.get("restart", {})
        self.github = self.config.get("github", {})
    
    def _get_default_auto_update(self) -> dict:
        """獲取預設自動更新配置"""
        return {
            "enabled": True,
            "check_interval": 21600,
            "require_owner_confirmation": True,
            "auto_restart": True
        }
    
    def _get_default_notification(self) -> dict:
        """獲取預設通知配置"""
        return {
            "discord_dm": True,
            "update_channel_id": None,
            "notification_mentions": []
        }
    
    def _get_default_security(self) -> dict:
        """獲取預設安全配置"""
        return {
            "backup_enabled": True,
            "max_backups": 5,
            "verify_downloads": True,
            "protected_files": [
                "settings.json",
                ".env",
                "data/schedule/",
                "data/dialogue_history.json",
                "data/channel_configs/",
                "data/user_data/",
                "data/update_logs/"
            ]
        }
    
    def _get_default_restart(self) -> dict:
        """獲取預設重啟配置"""
        # 根據作業系統調整重啟命令
        if os.name == 'nt':  # Windows
            restart_command = "python.exe main.py"
        else:  # Unix/Linux
            restart_command = "python main.py"
            
        return {
            "graceful_shutdown_timeout": 30,
            "restart_command": restart_command,
            "pre_restart_delay": 5,
            "restart_flag_file": "data/restart_flag.json"
        }
    
    def _get_default_github(self) -> dict:
        """獲取預設 GitHub 配置"""
        return {
            "repository": "starpig1129/ai-discord-bot-PigPig",
            "api_url": "https://api.github.com/repos/starpig1129/ai-discord-bot-PigPig/releases/latest",
            "download_url": "https://github.com/starpig1129/ai-discord-bot-PigPig/archive/"
        }
    
    def _get_default_config(self) -> dict:
        """獲取預設配置"""
        return {
            "auto_update": self._get_default_auto_update(),
            "notification": self._get_default_notification(),
            "security": self._get_default_security(),
            "restart": self._get_default_restart(),
            "github": self._get_default_github()
        }
    
    def update_config(self, section: str, key: str, value):
        """
        更新配置值
        
        Args:
            section: 配置區段
            key: 配置鍵
            value: 配置值
        """
        if section in self.config:
            self.config[section][key] = value
            # 同步更新屬性
            setattr(self, section, self.config[section])
    
    def is_auto_update_enabled(self) -> bool:
        """檢查是否啟用自動更新"""
        return self.auto_update.get("enabled", False)
    
    def get_check_interval(self) -> int:
        """獲取檢查間隔（秒）"""
        return self.auto_update.get("check_interval", 21600)
    
    def requires_owner_confirmation(self) -> bool:
        """檢查是否需要擁有者確認"""
        return self.auto_update.get("require_owner_confirmation", True)
