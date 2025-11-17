import yaml
import asyncio
import logging
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

def _load_yaml_file(path: str) -> dict:
    """安全讀取 YAML 檔案，失敗時使用 func.report_error 回報並回傳空 dict"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        try:
            from function import func
            asyncio.create_task(func.report_error(e, "addons/settings.py/_load_yaml_file"))
        except Exception:
            print(f"載入 YAML 檔案失敗 ({path}): {e}")
        return {}

def _get_config_root() -> str:
    """Read CONFIG_ROOT environment variable.

    If CONFIG_ROOT is not set, report the issue via func.report_error and
    fall back to 'config' to allow startup to continue.
    """
    try:
        root = os.getenv("CONFIG_ROOT")
        if root is None:
            raise KeyError("CONFIG_ROOT environment variable not set")
        # Remove any trailing slashes for consistent joins
        return root.rstrip("/\\")
    except KeyError:
        try:
            from function import func
            asyncio.create_task(
                func.report_error(Exception("CONFIG_ROOT environment variable not set"), "addons/settings.py/_get_config_root")
            )
        except Exception:
            logging.getLogger(__name__).warning("CONFIG_ROOT environment variable not set; defaulting to './base_configs'")
        return "./base_configs"

# Evaluate CONFIG_ROOT at module import time so the module-level config loaders
# below use the configured root directory.
CONFIG_ROOT = _get_config_root()
logger = logging.getLogger(__name__)
logger.debug(f"addons.settings CONFIG_ROOT={CONFIG_ROOT}")


class BaseConfig:
    """Configuration object mapped from config/base.yaml"""

    def __init__(self, path: str = "config/base.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.prefix: str = data.get("prefix", "/")
        self.activity: list = data.get("activity", [])
        self.ipc_server: dict = data.get("ipc_server", {})
        self.version: str = data.get("version", "")

        # Logging configuration schema (merge defaults with provided values).
        # The resulting `self.logging` is a plain dict so other modules (e.g. addons.logging_manager)
        # can shallow-merge it with their defaults.
        defaults = {
            "console": {"enabled": True, "color": True, "level": "INFO"},
            "color_map": {
                "level": {
                    "ERROR": "red",
                    "WARNING": "yellow",
                    "INFO": "green",
                    "DEBUG": "cyan",
                    "CRITICAL": "bright_red"
                },
                "source": {
                    "system": "magenta",
                    "external": "blue",
                    "server": "bright_blue"
                },
                "fields": {
                    "timestamp": "bright_black",
                    "channel": "bright_black",
                    "user": "bright_black",
                    "action": "bright_cyan",
                    "message": "white"
                }
            },
            "async": {"batch_size": 500, "flush_interval": 2.0},
            "rotation": {"policy": "daily", "compress": True, "retention_days": 300},
            "per_level_retention": {"INFO": 300, "WARNING": 300, "ERROR": 900},
            "fsync_on_flush": False,
            "log_base_path": "logs",
            "use_emoji": True,  # Enable emoji indicators in console output
            # Per-logger overrides to reduce noise from verbose third-party libraries.
            # Example in YAML:
            # logging:
            #   third_party_levels:
            #     sqlalchemy: WARNING
            #     httpx: WARNING
            "third_party_levels": {
                # Default reduced-noise levels for common noisy third-party libraries.
                # Users can override these in their CONFIG_ROOT/base.yaml under `logging.third_party_levels`.
                "sqlalchemy": "WARNING",
                "httpx": "WARNING",
                "httpcore": "WARNING",
                "urllib3": "WARNING",
                "selenium": "WARNING",
                "WDM": "INFO",
                "discord": "INFO",
            },
        }
        
        cfg = data.get("logging", {}) or {}
        
        # Shallow merge top-level keys
        merged = {**defaults, **cfg}
        
        # Merge nested structures conservatively
        merged["console"] = {**defaults["console"], **cfg.get("console", {})}
        
        # Merge color_map with all three sub-sections: level, source, and fields
        color_map_cfg = cfg.get("color_map", {})
        merged["color_map"] = {
            "level": {**defaults["color_map"]["level"], **color_map_cfg.get("level", {})},
            "source": {**defaults["color_map"]["source"], **color_map_cfg.get("source", {})},
            "fields": {**defaults["color_map"]["fields"], **color_map_cfg.get("fields", {})},
        }
        
        merged["async"] = {**defaults["async"], **cfg.get("async", {})}
        merged["rotation"] = {**defaults["rotation"], **cfg.get("rotation", {})}
        merged["per_level_retention"] = {**defaults["per_level_retention"], **cfg.get("per_level_retention", {})}
        
        # Merge third_party_levels (dict of logger name -> level)
        merged["third_party_levels"] = {
            **defaults.get("third_party_levels", {}),
            **cfg.get("third_party_levels", {})
        }
        
        # Preserve use_emoji setting
        merged["use_emoji"] = cfg.get("use_emoji", defaults.get("use_emoji", True))

        self.logging: dict = merged


class LLMConfig:
    """對應 config/llm.yaml 的設定物件"""

    def __init__(self, path: str = "config/llm.yaml") -> None:
        self.path = path
        self.data: dict = _load_yaml_file(path)
        self.model_priorities: list = self.data.get("model_priorities", [])
        self.google_search_agent: str = self.data.get("google_search_agent", "gemini-2.0-flash")


class UpdateConfig:
    """對應 config/update.yaml 的設定物件"""

    def __init__(self, path: str = "config/update.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.auto_update: dict = data.get("auto_update", {})
        self.security: dict = data.get("security", {})
        self.notification: dict = data.get("notification", {})
        self.restart: dict = data.get("restart", {})
        self.github: dict = data.get("github", {})

class MusicConfig:
    """對應 config/music.yaml 的設定物件"""

    def __init__(self, path: str = "config/music.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.music_temp_base: dict = data.get("music_temp_base", "temp/music")
        self.ffmpeg : dict = data.get("ffmpeg", {})
        self.youtube_cookies_path: str = data.get("youtube_cookies_path", "./data/youtube_cookies.txt")

class PromptConfig:
    """對應 config/prompt/*.yaml 的設定物件"""

    def __init__(self, path: str = "config/prompt") -> None:
        self.path = path
    
    def get_system_prompt(self, agent_name: str, bot_id: int | None = None, message=None) -> str:
        """
        從指定的 agent 設定中取得 system_prompt，並嘗試套用已知變數替換
        
        Args:
            agent_name: agent 名稱
            bot_id: 可選的機器人 ID（用於替換 {bot_id}）
            message: 可選的 Discord 訊息物件（未使用，但保留以備將來擴充）
        
        Returns:
            system_prompt 字串，若找不到則返回空字串
        """
        try:
            from llm.prompting.manager import get_prompt_manager

            logger = logging.getLogger(__name__)
            config_file = f"{self.path}/{agent_name}.yaml"
            logger.debug(f"PromptConfig.get_system_prompt: loading config_file={config_file}")

            prompt_manager = get_prompt_manager(config_file)
            # 嘗試記錄 prompt_manager 的 config_path（若有）
            try:
                pm_config_path = getattr(prompt_manager, "config_path", None)
                logger.debug(f"PromptConfig: prompt_manager.config_path={pm_config_path}")
            except Exception:
                logger.debug("PromptConfig: prompt_manager has no attribute 'config_path'")

            # 取得原始 prompt（尚未套用動態變數）
            system_prompt = prompt_manager.compose_prompt(None)
            logger.debug(f"PromptConfig.get_system_prompt: raw system_prompt={system_prompt!r}")

            # 準備可替換變數（盡可能填入已知值）
            try:
                from addons.tokens import tokens
                bot_owner_id = getattr(tokens, "bot_owner_id", 0)
            except Exception:
                bot_owner_id = 0

            try:
                # 優先從 prompt_manager 的 loader 讀取 base 配置
                config = prompt_manager.loader.load_yaml_config()
                base_cfg = config.get("base", {})
                bot_name = base_cfg.get("bot_name", "🐖🐖")
                creator = base_cfg.get("creator", "星豬")
                environment = base_cfg.get("environment", "Discord server")
            except Exception:
                bot_name = "🐖🐖"
                creator = "星豬"
                environment = "Discord server"

            # 將 bot_id 明確轉為字串以供 format 使用
            bot_id_str = str(bot_id) if bot_id is not None else "{bot_id}"

            variables = {
                "bot_id": bot_id_str,
                "bot_owner_id": bot_owner_id,
                "bot_name": bot_name,
                "creator": creator,
                "environment": environment,
            }

            logger.debug(f"PromptConfig.get_system_prompt: variables={variables!r}")

            try:
                # 嘗試獲取語言管理器（可能在某些上下文中可用）
                lang_manager = None
                guild_id = None
                
                # 嘗試從全局變數或上下文獲取語言管理器
                try:
                    import discord
                    lang_manager = None  
                    guild_id = None     
                except Exception:
                    pass 
                
                formatted = prompt_manager.builder.format_with_variables(system_prompt, variables, lang_manager, guild_id)
                logger.debug(f"PromptConfig.get_system_prompt: formatted system_prompt={formatted!r}")
                return formatted if formatted else system_prompt if system_prompt else ''
            except Exception as e:
                logger.exception(f"Formatting system_prompt failed: {e}")
                return system_prompt if system_prompt else ''

        except Exception as e:
            # 先嘗試使用現有的報錯機制
            try:
                asyncio.create_task(func.report_error(e, f"loading {agent_name} system prompt"))
            except Exception:
                # 若報錯機制不可用，記錄本地日誌以便診斷
                logger = logging.getLogger(__name__)
                logger.exception(f"Error loading {agent_name} system prompt: {e}")
            return ''

class MemoryConfig:
    """Memory subsystem configuration object mapped from config/memory.yaml"""

    def __init__(self, path: str = "config/memory.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)

        # Toggle to enable/disable memory subsystem
        self.enabled: bool = bool(data.get("enabled", True))

        # Storage / vector store configuration
        self.procedural_data_path: str = data.get("procedural_data_path", "data/memory/procedural.db")
        self.episodic_data_path: str = data.get("episodic_data_path", "data/memory/episodic.db")
        self.vector_store_type: str = data.get("vector_store_type", "qdrant")
        self.qdrant_url: str = data.get("qdrant_url", "http://localhost:6333")
        self.qdrant_api_key: Optional[str] = data.get("qdrant_api_key", None)
        self.qdrant_collection_name: str = data.get("qdrant_collection_name", "ephemeral_memory")

        # Embedding provider selection and provider-specific settings.
        # provider values: base, openai, huggingface, ollama, google
        self.embedding_provider: str = data.get("embedding_provider", "google")
        # Embedding model defaults (generic)
        self.embedding_model_name: str = data.get("embedding_model_name", "gemini-embedding-001")
        self.embedding_dim: int = data.get("embedding_dim", 768)

        # Search tuning
        self.vector_search_k: int = data.get("vector_search_k", 5)
        self.keyword_search_k: int = data.get("keyword_search_k", 5)

        # Ollama provider options
        self.ollama_url: Optional[str] = data.get("ollama_url", "http://localhost:11434")
        # Generic provider options bag for future extensions
        self.provider_options: dict = data.get("provider_options", {})

        # Message threshold for triggering memory processing
        self.message_threshold: int = data.get("message_threshold", 100)

try:
    base_config = BaseConfig(f"{CONFIG_ROOT}/base.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 BaseConfig 時發生錯誤: {e}")
    base_config = BaseConfig(f"{CONFIG_ROOT}/base.yaml")

try:
    llm_config = LLMConfig(f"{CONFIG_ROOT}/llm.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 LLMConfig 時發生錯誤: {e}")
    llm_config = LLMConfig(f"{CONFIG_ROOT}/llm.yaml")

try:
    update_config = UpdateConfig(f"{CONFIG_ROOT}/update.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 UpdateConfig 時發生錯誤: {e}")
    update_config = UpdateConfig(f"{CONFIG_ROOT}/update.yaml")
try:
    music_config = MusicConfig(f"{CONFIG_ROOT}/music.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MusicConfig 時發生錯誤: {e}")
    music_config = MusicConfig(f"{CONFIG_ROOT}/music.yaml")
try:
    prompt_config = PromptConfig(f"{CONFIG_ROOT}/prompt")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 PromptConfig 時發生錯誤: {e}")
    prompt_config = PromptConfig(f"{CONFIG_ROOT}/prompt")
try:
    memory_config = MemoryConfig(f"{CONFIG_ROOT}/memory.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MemoryConfig 時發生錯誤: {e}")
    memory_config = MemoryConfig(f"{CONFIG_ROOT}/memory.yaml")
__all__ = [
    "BaseConfig",
    "base_config",
    "LLMConfig",
    "llm_config",
    "UpdateConfig",
    "update_config",
    "MusicConfig",
    "music_config",
    "PromptConfig",
    "prompt_config",
    "MemoryConfig",
    "memory_config",
]
