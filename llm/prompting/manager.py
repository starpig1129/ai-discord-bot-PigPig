import asyncio
import logging
from typing import Dict, List, Optional, Any

from llm.prompting.loader import PromptLoader
from llm.prompting.cache import PromptCache
from llm.prompting.builder import PromptBuilder
from llm.utils.file_watcher import FileWatcher
from function import func
from addons.settings import prompt_config
class PromptManager:
    """YAML 基礎的系統提示管理器"""
    
    def __init__(self, config_path: str = f'{prompt_config.path}/message_agent.yaml'):
        """
        初始化提示管理器
        
        Args:
            config_path: YAML 配置檔案路徑
        """
        self.config_path = config_path
        self.loader = PromptLoader(config_path)
        self.cache = PromptCache()
        self.builder = PromptBuilder()
        self.file_watcher = FileWatcher()
        
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        
        # 初始化管理器
        self._initialize()
    
    def _initialize(self):
        """初始化管理器"""
        try:
            # 載入初始配置
            config = self.loader.load_yaml_config()
            if not self._validate_config(config):
                raise ValueError("Invalid YAML configuration structure")
            
            # 設定檔案監控
            self.file_watcher.watch_file(self.config_path, self._on_config_changed)
            
            # 預編譯快取
            self.cache.precompile_templates(config)
            
            self._initialized = True
            self.logger.info("PromptManager initialized successfully")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "PromptManager initialization"))
            raise
    
    def _validate_config(self, config: dict) -> bool:
        """
        驗證配置的基本結構
        
        Args:
            config: 配置字典
            
        Returns:
            bool: 配置是否有效
        """
        required_sections = ['metadata', 'base', 'composition']
        
        for section in required_sections:
            if section not in config:
                self.logger.error(f"Missing required section: {section}")
                return False
        
        # 檢查 composition 區段
        composition = config.get('composition', {})
        if 'default_modules' not in composition:
            self.logger.error("Missing 'default_modules' in composition section")
            return False
        
        return True
    
    def get_system_prompt(self, bot_id: str, message=None) -> str:
        """
        取得系統提示（替換原有的 get_system_prompt 函式）
        
        Args:
            bot_id: Discord 機器人 ID
            message: Discord 訊息物件（用於語言檢測）
            
        Returns:
            完整的系統提示字串
        """
        try:
            if not self._initialized:
                self._initialize()
            
            # 產生快取鍵值
            lang_key = self._get_language_key(message)
            cache_key = f"system_prompt_{bot_id}_{lang_key}"
            
            # 檢查快取
            cached_prompt = self.cache.get(cache_key)
            if cached_prompt:
                return self._apply_dynamic_replacements(cached_prompt, bot_id, message)
            
            # 從配置建構提示
            config = self.loader.load_yaml_config()
            default_modules = config['composition']['default_modules']
            prompt = self.builder.build_system_prompt(config, default_modules)
            
            # 快取結果
            ttl = config.get('metadata', {}).get('cache_ttl', 3600)
            self.cache.set(cache_key, prompt, ttl)
            
            return self._apply_dynamic_replacements(prompt, bot_id, message)
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "getting system prompt"))
            # 降級到基本提示
            return self._get_fallback_prompt(bot_id)
    
    def _get_language_key(self, message) -> str:
        """
        取得語言鍵值用於快取
        
        Args:
            message: Discord 訊息物件
            
        Returns:
            語言鍵值
        """
        try:
            if message and message.guild:
                bot = message.guild.me._state._get_client()
                if lang_manager := bot.get_cog("LanguageManager"):
                    guild_id = str(message.guild.id)
                    return lang_manager.get_server_lang(guild_id)
        except Exception:
            pass
        
        return "zh_TW"  # 預設語言
    
    def _apply_dynamic_replacements(self, prompt: str, bot_id: str, message) -> str:
        """
        套用動態替換（整合現有語言管理功能）
        
        Args:
            prompt: 基礎提示
            bot_id: 機器人 ID
            message: Discord 訊息物件
            
        Returns:
            套用替換後的提示
        """
        # 基本變數替換
        try:
            from addons.tokens import tokens
            bot_owner_id = getattr(tokens, 'bot_owner_id', 0)
        except ImportError:
            bot_owner_id = 0
        
        # 從 systemPrompt.yaml 的 base 配置中取得預設值
        try:
            config = self.loader.load_yaml_config()
            base_config = config.get('base', {})
            bot_name = base_config.get('bot_name', '🐖🐖')
            creator = base_config.get('creator', '星豬')
            environment = base_config.get('environment', 'Discord server')
        except Exception:
            # 降級預設值
            bot_name = '🐖🐖'
            creator = '星豬'
            environment = 'Discord server'
        
        variables = {
            'bot_id': bot_id,
            'bot_owner_id': bot_owner_id,
            'bot_name': bot_name,
            'creator': creator,
            'environment': environment
        }
        
        # 語言相關變數
        lang_manager = None
        guild_id = None
        if message and message.guild:
            try:
                bot = message.guild.me._state._get_client()
                lang_manager = bot.get_cog("LanguageManager")
                if lang_manager:
                    guild_id = str(message.guild.id)
                    # Add language replacements mappings to variables
                    try:
                        config = self.loader.load_yaml_config()
                        variables['language_replacements'] = config.get('language_replacements', {})
                    except Exception:
                        pass
            except Exception as e:
                self.logger.warning(f"Failed to get language manager: {e}")
        
        # 使用更新後的方法進行變數替換
        prompt = self.builder.format_with_variables(prompt, variables, lang_manager, guild_id)
        
        return prompt
    
    def _get_fallback_prompt(self, bot_id: str) -> str:
        """
        降級策略：使用硬編碼的基本提示
        
        Args:
            bot_id: 機器人 ID
            
        Returns:
            基本的系統提示
        """
        try:
            from addons.tokens import tokens
            bot_owner_id = getattr(tokens, 'bot_owner_id', 0)
        except ImportError:
            bot_owner_id = 0
        
        fallback_prompt = '''You are an AI chatbot named 🐖🐖 <@{bot_id}>, created by 星豬<@{bot_owner_id}>. You are chatting in a Discord server, so keep responses concise and engaging. Please follow these instructions:

1. Personality and Expression (表達風格):
- Maintain a humorous and fun conversational style.
- Be polite, respectful, and honest.
- Use vivid and lively language, but don't be overly exaggerated or lose professionalism.

2. Language Requirements (語言要求):
- Always answer in Traditional Chinese.
- Keep casual chat responses short and natural, like a friendly Discord conversation.

3. Interaction:
- Engage in natural chat-like interactions.
- Keep responses concise and interactive.
- Stay focused on the current topic and avoid bringing up old conversations.

Remember: You're in a Discord chat environment - keep responses brief and engaging for casual conversations.'''
        
        return fallback_prompt.format(bot_id=bot_id, bot_owner_id=bot_owner_id)
    
    def reload_prompts(self) -> bool:
        """
        重新載入提示配置
        
        Returns:
            bool: 是否成功重新載入
        """
        try:
            self.cache.clear_all()
            config = self.loader.load_yaml_config()
            
            if self._validate_config(config):
                self.cache.precompile_templates(config)
                self.logger.info("Prompts reloaded successfully")
                return True
            else:
                self.logger.error("Failed to validate reloaded configuration")
                return False
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "reloading prompts"))
            return False
    
    def _on_config_changed(self, path: str):
        """
        配置檔案變更回調
        
        Args:
            path: 變更的檔案路徑
        """
        self.logger.info(f"Configuration file changed: {path}")
        if self.reload_prompts():
            self.logger.info("Configuration reloaded successfully")
        else:
            self.logger.error("Failed to reload configuration after file change")
    
    def get_module_prompt(self, module_name: str) -> str:
        """
        取得特定模組的提示內容
        
        Args:
            module_name: 模組名稱
            
        Returns:
            模組提示內容
        """
        try:
            config = self.loader.load_yaml_config()
            return self.builder.compose_modules(config, [module_name])
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"getting module prompt for '{module_name}'"))
            return ""
    
    def compose_prompt(self, modules: Optional[List[str]] = None) -> str:
        """
        組合指定模組的提示內容

        Args:
            modules: 要組合的模組列表，如果為 None 則使用預設模組

        Returns:
            組合後的提示內容
        """
        try:
            config = self.loader.load_yaml_config()
            # 安全取得 default_modules（避免 KeyError）
            default_modules = config.get('composition', {}).get('default_modules', [])
            # 確保傳入 build_system_prompt 的參數類型為 List[str]
            modules_to_use: List[str] = default_modules if modules is None else modules
            return self.builder.build_system_prompt(config, modules_to_use)
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"composing prompt with modules {modules}"))
            return ""
    
    def get_available_modules(self) -> List[str]:
        """
        取得可用的模組列表
        
        Returns:
            可用模組名稱列表
        """
        try:
            config = self.loader.load_yaml_config()
            # 排除非模組的頂層鍵值
            excluded_keys = {'metadata', 'composition', 'conditions', 'language_replacements'}
            modules = [key for key in config.keys() if key not in excluded_keys]
            return modules
        except Exception as e:
            asyncio.create_task(func.report_error(e, "getting available modules"))
            return []
    
    def validate_modules(self, modules: List[str]) -> Dict[str, bool]:
        """
        驗證模組是否存在
        
        Args:
            modules: 要驗證的模組列表
            
        Returns:
            模組驗證結果字典 {模組名: 是否存在}
        """
        try:
            config = self.loader.load_yaml_config()
            return {module: module in config for module in modules}
        except Exception as e:
            asyncio.create_task(func.report_error(e, "validating modules"))
            return {module: False for module in modules}
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        取得快取統計資訊
        
        Returns:
            快取統計資訊字典
        """
        return self.cache.get_cache_stats()
    
    def get_manager_info(self) -> Dict[str, Any]:
        """
        取得管理器資訊
        
        Returns:
            管理器資訊字典
        """
        try:
            config = self.loader.get_cached_config()
            return {
                'initialized': self._initialized,
                'config_path': self.config_path,
                'config_loaded': config is not None,
                'config_version': config.get('metadata', {}).get('version') if config else None,
                'available_modules': self.get_available_modules(),
                'file_watcher_running': self.file_watcher._running if hasattr(self.file_watcher, '_running') else False,
                'cache_stats': self.get_cache_stats()
            }
        except Exception as e:
            asyncio.create_task(func.report_error(e, "getting manager info"))
            return {'error': str(e)}
    
    def cleanup(self):
        """清理資源"""
        try:
            self.file_watcher.stop_watching()
            self.cache.clear_all()
            self.logger.info("PromptManager cleanup completed")
        except Exception as e:
            asyncio.create_task(func.report_error(e, "PromptManager cleanup"))
    
    def __del__(self):
        """析構函式"""
        self.cleanup()

# 管理多個 PromptManager 實例，key 為配置檔路徑
from typing import Dict

_prompt_manager_instances: Dict[str, PromptManager] = {}

def get_prompt_manager(config_path: str = f'{prompt_config.path}/message_agent.yaml') -> PromptManager:
    """
    取得指定 config_path 的 PromptManager 實例（若不存在則建立並快取）。
    這樣可以支援多個不同 agent 的配置檔案，而不會互相覆寫單一全域實例。
    
    Args:
        config_path: 配置檔案路徑
        
    Returns:
        PromptManager 實例
    """
    # 使用簡單的路徑字串作為 key（可根據需要擴充為絕對路徑）
    key = config_path
    if key not in _prompt_manager_instances:
        _prompt_manager_instances[key] = PromptManager(config_path)
    return _prompt_manager_instances[key]