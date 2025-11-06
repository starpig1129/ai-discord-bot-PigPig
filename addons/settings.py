import yaml
import asyncio


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
    
    def get_system_prompt(self, agent_name: str) -> str:
        """
        從指定的 agent 設定中取得 system_prompt
        
        Args:
            agent_name: agent 名稱
        
        Returns:
            system_prompt 字串，若找不到則返回空字串
        """
        try:
            from llm.prompting.manager import get_prompt_manager
            
            config_file = f"{self.path}/{agent_name}.yaml"
            prompt_manager = get_prompt_manager(config_file)
            system_prompt = prompt_manager.compose_prompt(['base'])
            return system_prompt if system_prompt else ''
        except Exception as e:
            try:
                asyncio.create_task(func.report_error(e, f"loading {agent_name} system prompt"))
            except Exception:
                pass
            return ''

class MemoryConfig:
    """對應 config/memory.yaml 的設定物件"""

    def __init__(self, path: str = "config/memory.yaml") -> None:
        self.path = path
        data = _load_yaml_file(path)
        self.user_data_path: str = data.get("user_data_path", "data/memory/memory.db")
        self.short_term_memory_size: int = data.get("short_term_memory_size", 10)
        self.long_term_memory_size: int = data.get("long_term_memory_size", 1024)
        self.long_term_memory_count: int = data.get("long_term_memory_count", 5)
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
