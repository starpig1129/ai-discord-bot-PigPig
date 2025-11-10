import yaml
import asyncio
import logging
from typing import Optional, List

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


class BaseConfig:
    """對應 config/base.yaml 的設定物件"""

    def __init__(self, path: str = "config/base.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.prefix: str = data.get("prefix", "/")
        self.activity: list = data.get("activity", [])
        self.ipc_server: dict = data.get("ipc_server", {})
        self.version: str = data.get("version", "")
        self.logging: dict = data.get("logging", {})


class LLMConfig:
    """對應 config/llm.yaml 的設定物件"""

    def __init__(self, path: str = "config/llm.yaml") -> None:
        self.path = path
        self.data: dict = _load_yaml_file(path)
        self.model_priorities: list = self.data.get("model_priorities", [])


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

            # 嘗試使用 PromptBuilder 的 format_with_variables 進行替換，並記錄結果
            try:
                formatted = prompt_manager.builder.format_with_variables(system_prompt, variables)
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
        self.user_data_path: str = data.get("user_data_path", "data/memory/memory.db")
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

        # Batch sizes for fetch/process pipelines
        self.fetch_batch_size: int = data.get("fetch_batch_size", 100)
        self.process_batch_size: int = data.get("process_batch_size", 50)

        # Ollama provider options
        self.ollama_url: Optional[str] = data.get("ollama_url", "http://localhost:11434")
        # Generic provider options bag for future extensions
        self.provider_options: dict = data.get("provider_options", {})

        # Optional tuning parameters (present in YAML)
        self.store_refresh_interval_seconds: int | None = data.get("store_refresh_interval_seconds", None)
        self.max_memory_items_per_user: int | None = data.get("max_memory_items_per_user", None)
try:
    base_config = BaseConfig("config/base.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 BaseConfig 時發生錯誤: {e}")
    base_config = BaseConfig()

try:
    llm_config = LLMConfig("config/llm.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 LLMConfig 時發生錯誤: {e}")
    llm_config = LLMConfig()

try:
    update_config = UpdateConfig("config/update.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 UpdateConfig 時發生錯誤: {e}")
    update_config = UpdateConfig()
try:
    music_config = MusicConfig("config/music.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MusicConfig 時發生錯誤: {e}")
    music_config = MusicConfig()
try:
    prompt_config = PromptConfig("config/prompt")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 PromptConfig 時發生錯誤: {e}")
    prompt_config = PromptConfig()
try:
    memory_config = MemoryConfig("config/memory.yaml")
except Exception as e:
    try:
        from function import func
        asyncio.create_task(func.report_error(e, "addons/settings.py/module_init"))
    except Exception:
        print(f"初始化 MemoryConfig 時發生錯誤: {e}")
    memory_config = MemoryConfig()    
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
