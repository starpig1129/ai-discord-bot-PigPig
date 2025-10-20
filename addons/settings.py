import json
import os
import sys
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
        self.youtube_cookies_path: str = settings.get("youtube_cookies_path", "data/cookies.txt")
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
                ".git/",
                ".gitignore",
                ".gitattributes",
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
        
        # FFmpeg 設定
        self.ffmpeg: dict = settings.get("ffmpeg", self._get_default_ffmpeg())
        
        # 記憶系統設定
        self.memory_system: dict = settings.get("memory_system", self._get_default_memory_system())
    
    def _get_default_ffmpeg(self) -> dict:
        """獲取預設 FFmpeg 設定"""
        return {
            "location": "/usr/bin/ffmpeg",
            "audio_quality": "192",
            "audio_codec": "mp3",
            "postprocessor_args": {
                "threads": 2,
                "loglevel": "warning",
                "overwrite_output": True,
                "max_muxing_queue_size": 2048,
                "analyzeduration": "20M",
                "probesize": "20M",
                "reconnect": True,
                "reconnect_streamed": True,
                "reconnect_delay_max": 30,
                "timeout": 30000000,
                "rw_timeout": 30000000
            },
            "ytdlp_options": {
                "socket_timeout": 300,
                "retries": 10,
                "concurrent_fragment_downloads": 1,
                "file_access_retries": 5,
                "fragment_retries": 10,
                "retry_sleep_http": 5
            },
            "http_headers": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept_language": "en-us,en;q=0.5",
                "sec_fetch_mode": "navigate"
            }
        }
    
    def _get_default_memory_system(self) -> dict:
        """獲取預設記憶系統設定"""
        return {
            "enabled": True,
            "auto_detection": True,
            "vector_enabled": True,
            "cpu_only_mode": False,
            "memory_threshold_mb": 2048,
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "database_path": "data/memory/memory.db",
            "channel_settings": {
                "default_enabled": True,
                "whitelist_channels": [],
                "blacklist_channels": [],
                "auto_initialize": True
            },
            "search_settings": {
                "default_search_type": "hybrid",
                "semantic_threshold": 0.7,
                "keyword_threshold": 0.5,
                "max_context_messages": 5,
                "enable_temporal_decay": True
            },
            "index_optimization": {
                "enabled": True,
                "interval_hours": 24,
                "cleanup_old_data_days": 90,
                "auto_rebuild": False,
                "compression_enabled": True
            },
            "cache": {
                "enabled": True,
                "max_size_mb": 512,
                "ttl_seconds": 3600,
                "query_cache_size": 1000,
                "preload_frequent_queries": True
            },
            "performance": {
                "max_concurrent_queries": 10,
                "query_timeout_seconds": 30,
                "batch_size": 50,
                "async_storage": True,
                "memory_pool_size": 4
            },
            "monitoring": {
                "enable_metrics": True,
                "log_slow_queries": True,
                "slow_query_threshold_ms": 1000,
                "performance_alerts": False
            },
            "backup": {
                "enabled": True,
                "interval_hours": 168,
                "max_backups": 7,
                "compression": True
            }
        }

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

        self.bot_owner_id = int(os.getenv("BOT_OWNER_ID", 0))

                # 驗證環境變數
        self._validate_environment_variables()

    def _validate_environment_variables(self) -> None:
        """驗證所有必要的環境變數是否存在且有效"""
        missing_vars = []
        invalid_vars = []

        # 檢查必要環境變數
        required_vars = {
            "TOKEN": self.token,
            "CLIENT_ID": self.client_id,
            "CLIENT_SECRET_ID": self.client_secret_id,
            "SERCET_KEY": self.sercet_key,
            "BUG_REPORT_CHANNEL_ID": os.getenv("BUG_REPORT_CHANNEL_ID"),
            "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID")
        }

        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
            elif var_name == "BUG_REPORT_CHANNEL_ID":
                try:
                    int(var_value)
                except (ValueError, TypeError):
                    invalid_vars.append(f"{var_name} (必須為有效的整數)")

        # 檢查 API 金鑰（可選但建議設定）
        optional_api_keys = {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "OPENAI_API_KEY": self.openai_api_key,
            "GEMINI_API_KEY": self.gemini_api_key
        }

        for api_name, api_value in optional_api_keys.items():
            if not api_value:
                print(f"警告：{api_name} 未設定，可能影響相關功能")

        # 如果有缺失或無效的環境變數，終止程式
        if missing_vars or invalid_vars:
            error_msg = "環境變數驗證失敗：\n"

            if missing_vars:
                error_msg += f"缺失的環境變數：{', '.join(missing_vars)}\n"

            if invalid_vars:
                error_msg += f"無效的環境變數：{', '.join(invalid_vars)}\n"

            error_msg += "\n請檢查 .env 檔案並設定所有必要的環境變數。"

            print(error_msg)
            sys.exit(1)

        print("環境變數驗證成功")

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
                ".git/",
                ".gitignore",
                ".gitattributes",
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
