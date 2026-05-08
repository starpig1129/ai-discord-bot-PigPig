"""
Channel system prompt manager.

Provides core system prompt management functionality, including three-level inheritance,
caching system, and configuration management.
"""

import json
import os
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import discord
from addons.logging import get_logger

from .exceptions import (
    SystemPromptError,
    ValidationError,
    ConfigurationError,
    ContentTooLongError,
    UnsafeContentError,
    PromptNotFoundError
)
from .permissions import PermissionValidator

from function import func
import asyncio
# Production cache fixer integrated into core module
PRODUCTION_CACHE_FIXER_AVAILABLE = False
ProductionCacheFixer = None


class SystemPromptCache:
    """System prompt cache manager."""
    
    def __init__(self, ttl: int = 3600):
        """
        Initialize cache manager.
        
        Args:
            ttl: Cache time-to-live (seconds).
        """
        self.cache: Dict[str, Tuple[float, str]] = {}
        self.ttl = ttl
    
    def get_cache_key(self, guild_id: str, channel_id: str, lang: str = "zh_TW") -> str:
        """Generate cache key."""
        return f"system_prompt:{guild_id}:{channel_id}:{lang}"
    
    def get(self, guild_id: str, channel_id: str, lang: str = "zh_TW") -> Optional[str]:
        """Get system prompt from cache."""
        key = self.get_cache_key(guild_id, channel_id, lang)
        if key in self.cache:
            timestamp, prompt = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return prompt
            else:
                del self.cache[key]
        return None
    
    def set(self, guild_id: str, channel_id: str, prompt: str, lang: str = "zh_TW") -> None:
        """Set cache."""
        key = self.get_cache_key(guild_id, channel_id, lang)
        self.cache[key] = (time.time(), prompt)
    
    def invalidate(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """Invalidate cache."""
        pattern = f"system_prompt:{guild_id}"
        if channel_id:
            pattern += f":{channel_id}"
        
        keys_to_remove = [key for key in self.cache.keys() if key.startswith(pattern)]
        for key in keys_to_remove:
            del self.cache[key]
    
    def clear_all(self) -> None:
        """Clear all cache."""
        self.cache.clear()


class PromptValidator:
    """System prompt validator."""
    def __init__(self, bot: discord.Client):
        """
        Initialize system prompt validator.
        
        Args:
            bot: Discord bot instance.
        """
        self.bot = bot
        
    MAX_PROMPT_LENGTH = 4000
    MAX_MODULE_COUNT = 10
    
    # Dangerous pattern list
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>',
        r'javascript:',
        r'data:text/html',
        r'eval\s*\(',
        r'setTimeout\s*\(',
        r'setInterval\s*\(',
        r'<iframe[^>]*>',
        r'<object[^>]*>',
        r'<embed[^>]*>'
    ]
    
    def validate_prompt_content(self, content: str) -> Tuple[bool, str]:
        """
        Validate prompt content.
        
        Args:
            content: Prompt content.
            
        Returns:
            (is_valid, error_message)
        """
        # Length check
        if len(content) > self.MAX_PROMPT_LENGTH:
            raise ContentTooLongError(self.MAX_PROMPT_LENGTH, len(content))
        
        # Basic format check
        if not content.strip():
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            guild_id = getattr(self.bot, 'current_guild_id', None)
            raise ValidationError(None, "content", lang_manager, guild_id)
        
        # Check for potential injection attacks
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
                guild_id = getattr(self.bot, 'current_guild_id', None)
                raise UnsafeContentError(pattern, lang_manager, guild_id)
        
        return True, ""
    
    def validate_modules(self, modules: Dict[str, str], guild_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate module configuration.
        
        Args:
            modules: Module dictionary.
            guild_id: Server ID (optional).
            
        Returns:
            (is_valid, error_message)
        """
        if len(modules) > self.MAX_MODULE_COUNT:
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            raise ValidationError(
                None,
                "modules",
                lang_manager,
                guild_id
            )
        
        for module_name, module_content in modules.items():
            if not isinstance(module_content, str):
                lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
                raise ValidationError(
                    None,
                    f"module_{module_name}",
                    lang_manager,
                    guild_id
                )
            
            self.validate_prompt_content(module_content)
        
        return True, ""


class SystemPromptManager:
    """System prompt manager - Core coordinator."""
    
    def __init__(self, bot: discord.Client):
        """
        Initialize system prompt manager.
        
        Args:
            bot: Discord bot instance.
        """
        self.bot = bot
        self.logger = get_logger(server_id="system", source=__name__)
        self.cache = SystemPromptCache()
        self.validator = PromptValidator(bot)
        self.permission_validator = PermissionValidator(bot)
        
        # Data directory path
        self.data_dir = Path("data/channel_configs")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize YAML prompt manager
        self._prompt_manager = None
        self._init_prompt_manager()
        
        # Cache invalidation strategy integrated into core methods
        self.logger.info("✅ Using integrated cache invalidation strategy")
    
    def _init_prompt_manager(self) -> None:
        """Initialize YAML prompt manager."""
        try:
            from llm.prompting.manager import get_prompt_manager
            self._prompt_manager = get_prompt_manager()
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Failed to initialize PromptManager"))
            self.logger.error(f"Failed to initialize PromptManager: {e}")
            self._prompt_manager = None
    
    
    def get_effective_prompt(self, channel_id: str, guild_id: str, 
                           message: Optional[discord.Message] = None) -> Dict[str, Any]:
        """
        Get effective system prompt (integrated three-level inheritance).
        
        Args:
            channel_id: Channel ID.
            guild_id: Server ID.
            message: Discord message object (for language detection).
            
        Returns:
            Dictionary containing prompt content and source.
        """
        try:
            # Try to get from cache
            lang = self._get_language(guild_id, message)
            cached_prompt = self.cache.get(guild_id, channel_id, lang)
            if cached_prompt:
                return {
                    'prompt': cached_prompt,
                    'source': 'cache',
                    'timestamp': time.time()
                }
            
            # Load configuration
            config = self._load_guild_config(guild_id)
            system_prompts = config.get('system_prompts', {})
            
            if not system_prompts.get('enabled', False):
                # System prompt functionality disabled, use YAML default
                return self._get_yaml_prompt(guild_id, message)
            
            # Level 1: Load YAML base prompt
            base_prompt_data = self._get_yaml_prompt(guild_id, message)
            base_prompt = base_prompt_data.get('prompt', '')
            
            # Level 2: Apply server-level prompt
            server_level = system_prompts.get('server_level', {})
            if server_level:
                prompt = self._apply_server_overrides(base_prompt, server_level, guild_id)
                source = 'server'
            else:
                prompt = base_prompt
                source = 'yaml'
            
            # Level 3: Apply channel-level prompt
            channels = system_prompts.get('channels', {})
            channel_config = channels.get(channel_id)
            
            if channel_config and channel_config.get('enabled', True):
                prompt = self._apply_channel_overrides(prompt, channel_config, guild_id)
                source = 'channel'
            
            # Apply language localization
            prompt = self._apply_language_localization(prompt, lang, guild_id)
            
            # 🔧 Fix: Ensure final prompt goes through variable replacement
            # Variable replacement only needed for non-YAML sources (YAML already replaced in PromptManager)
            if source != 'yaml':
                prompt = self._apply_variable_replacements(prompt, guild_id)
                self.logger.debug(f"✅ Applied final variable replacement for {source} level prompt")
            
            # Set cache
            self.cache.set(guild_id, channel_id, prompt, lang)
            
            return {
                'prompt': prompt,
                'source': source,
                'timestamp': time.time(),
                'language': lang
            }
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting effective system prompt"))
            self.logger.error(f"Error getting effective system prompt: {e}")
            # Fallback to YAML prompt
            return self._get_yaml_prompt(guild_id, message)
    
    def get_channel_prompt_config(self, guild_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        取得指定頻道的原始系統提示設定。

        這個方法會直接從設定檔中讀取並回傳該頻道的設定字典，
        而不會進行繼承合併或變數替換。

        Args:
            guild_id: 伺服器 ID。
            channel_id: 頻道 ID。

        Returns:
            包含頻道設定的字典，如果不存在則回傳 None。
        """
        try:
            config = self._load_guild_config(guild_id)
            return config.get('system_prompts', {}).get('channels', {}).get(channel_id)
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"Error getting raw config for channel {channel_id}"))
            self.logger.error(f"取得頻道 {channel_id} 的原始設定時發生錯誤: {e}")
            return None
    
    def set_channel_prompt(self, guild_id: str, channel_id: str, 
                          prompt_data: Dict[str, Any], user_id: str) -> bool:
        """
        設定頻道系統提示
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            prompt_data: 提示資料
            user_id: 操作用戶 ID
            
        Returns:
            是否設定成功
        """
        try:
            self.logger.info(f"🔧 開始設定頻道系統提示 - 伺服器: {guild_id}, 頻道: {channel_id}")
            self.logger.debug(f"提示數據: {prompt_data}")
            
            # 驗證提示內容
            if 'prompt' in prompt_data:
                self.validator.validate_prompt_content(prompt_data['prompt'])
                self.logger.debug("✅ 提示內容驗證通過")
            
            if 'modules' in prompt_data:
                self.validator.validate_modules(prompt_data['modules'])
                self.logger.debug(f"✅ 模組驗證通過，模組數量: {len(prompt_data['modules'])}")
            
            # 載入配置
            config = self._load_guild_config(guild_id)
            self.logger.debug(f"✅ 載入配置完成，現有結構: {bool(config.get('system_prompts'))}")
            
            # 確保系統提示結構存在
            if 'system_prompts' not in config:
                config['system_prompts'] = {
                    'enabled': True,
                    'server_level': {},
                    'channels': {},
                    'permissions': {}
                }
                self.logger.debug("✅ 創建新的 system_prompts 結構")
            
            # 設定頻道提示
            channels = config['system_prompts']['channels']
            if channel_id not in channels:
                channels[channel_id] = {}
                self.logger.debug(f"✅ 創建新的頻道配置: {channel_id}")
            else:
                self.logger.debug(f"✅ 使用現有頻道配置: {channel_id}")
            
            # 記錄更新前的狀態
            old_channel_config = channels[channel_id].copy()
            self.logger.debug(f"更新前頻道配置: {old_channel_config}")
            
            # 更新頻道配置
            channel_config = channels[channel_id]
            channel_config.update({
                'enabled': prompt_data.get('enabled', True),
                'created_by': user_id,
                'created_at': datetime.now().isoformat(),
                'updated_by': user_id,
                'updated_at': datetime.now().isoformat()
            })
            
            # 設定提示內容
            if 'prompt' in prompt_data:
                channel_config['prompt'] = prompt_data['prompt']
                self.logger.debug(f"✅ 設定提示內容，長度: {len(prompt_data['prompt'])}")
            
            if 'modules' in prompt_data:
                channel_config['modules'] = prompt_data['modules']
                self.logger.info(f"✅ 設定模組: {list(prompt_data['modules'].keys())}")
                for module_name, module_content in prompt_data['modules'].items():
                    content_preview = module_content[:50] + "..." if len(module_content) > 50 else module_content
                    self.logger.debug(f"  - {module_name}: {content_preview}")
            
            if 'override_modules' in prompt_data:
                channel_config['override_modules'] = prompt_data['override_modules']
                self.logger.debug("✅ 設定覆蓋模組")
            
            if 'append_content' in prompt_data:
                channel_config['append_content'] = prompt_data['append_content']
                self.logger.debug("✅ 設定追加內容")
            
            # 記錄更新後的狀態
            self.logger.debug(f"更新後頻道配置: {channel_config}")
            
            # 保存配置
            self.logger.info(f"💾 開始保存配置到檔案...")
            self._save_guild_config(guild_id, config)
            self.logger.info(f"✅ 配置保存完成")
            
            # 立即驗證保存結果
            verification_config = self._load_guild_config(guild_id)
            verification_channels = verification_config.get('system_prompts', {}).get('channels', {})
            if channel_id in verification_channels:
                verification_channel_config = verification_channels[channel_id]
                verification_modules = verification_channel_config.get('modules', {})
                self.logger.info(f"🔍 保存驗證 - 檔案中的模組: {verification_modules}")
                
                # 比較模組
                if 'modules' in prompt_data:
                    expected_modules = prompt_data['modules']
                    if verification_modules == expected_modules:
                        self.logger.info("✅ 保存驗證通過：模組數據一致")
                    else:
                        self.logger.warning(f"⚠️ 保存驗證失敗：模組數據不一致")
                        self.logger.warning(f"期望: {expected_modules}")
                        self.logger.warning(f"實際: {verification_modules}")
            else:
                self.logger.warning(f"⚠️ 保存驗證失敗：找不到頻道 {channel_id} 的配置")
            
            # 強制清除所有相關快取（確保即時生效）
            self.logger.debug(f"🗑️ 強制清除所有快取: {guild_id}:{channel_id}")
            # 使用同步版本的清除方法，避免異步問題
            self._legacy_force_clear_all_caches(guild_id, channel_id)
            
            self.logger.info(f"✅ 頻道 {channel_id} 系統提示設定成功，操作者: {user_id}")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error setting channel system prompt"))
            self.logger.error(f"設定頻道系統提示時發生錯誤: {e}")
            raise SystemPromptError(f"設定失敗: {str(e)}")
    
    def set_server_prompt(self, guild_id: str, prompt_data: Dict[str, Any], 
                         user_id: str) -> bool:
        """
        設定伺服器級別系統提示
        
        Args:
            guild_id: 伺服器 ID
            prompt_data: 提示資料
            user_id: 操作用戶 ID
            
        Returns:
            是否設定成功
        """
        try:
            # 驗證提示內容
            if 'prompt' in prompt_data:
                self.validator.validate_prompt_content(prompt_data['prompt'])
            
            if 'modules' in prompt_data:
                self.validator.validate_modules(prompt_data['modules'])
            
            # 載入配置
            config = self._load_guild_config(guild_id)
            
            # 確保系統提示結構存在
            if 'system_prompts' not in config:
                config['system_prompts'] = {
                    'enabled': True,
                    'server_level': {},
                    'channels': {},
                    'permissions': {}
                }
            
            # 設定伺服器級別提示
            server_level = config['system_prompts']['server_level']
            server_level.update({
                'created_by': user_id,
                'created_at': datetime.now().isoformat(),
                'updated_by': user_id,
                'updated_at': datetime.now().isoformat()
            })
            
            # 設定提示內容
            for key in ['prompt', 'modules', 'language_preference', 'custom_modules']:
                if key in prompt_data:
                    server_level[key] = prompt_data[key]
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 清除快取（全面同步）
            self.clear_cache(guild_id)
            
            self.logger.info(f"伺服器 {guild_id} 系統提示設定成功，操作者: {user_id}")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error setting server system prompt"))
            self.logger.error(f"設定伺服器系統提示時發生錯誤: {e}")
            raise SystemPromptError(f"設定失敗: {str(e)}")
    
    def remove_channel_prompt(self, guild_id: str, channel_id: str) -> bool:
        """
        移除頻道系統提示
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID
            
        Returns:
            是否移除成功
        """
        try:
            config = self._load_guild_config(guild_id)
            
            system_prompts = config.get('system_prompts', {})
            channels = system_prompts.get('channels', {})
            
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            
            if channel_id not in channels:
                raise PromptNotFoundError('channel', channel_id, lang_manager, guild_id)
            
            del channels[channel_id]
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 清除快取（全面同步）
            self.clear_cache(guild_id, channel_id)
            
            self.logger.info(f"頻道 {channel_id} 系統提示移除成功")
            return True
            
        except Exception as e:
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            asyncio.create_task(func.report_error(e, "Error removing channel system prompt"))
            self.logger.error(f"移除頻道系統提示時發生錯誤: {e}")
            
            error_message = "移除失敗"
            if lang_manager and guild_id:
                try:
                    error_message = lang_manager.translate(
                        guild_id,
                        "commands", "system_prompt",
                        "errors", "operation_failed"
                    ).format(error=str(e))
                except Exception:
                    pass
            
            raise SystemPromptError(f"移除失敗: {str(e)}")
    
    def remove_server_prompt(self, guild_id: str) -> bool:
        """
        移除伺服器級別系統提示
        
        Args:
            guild_id: 伺服器 ID
            
        Returns:
            是否移除成功
        """
        try:
            config = self._load_guild_config(guild_id)
            
            system_prompts = config.get('system_prompts', {})
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            
            if not system_prompts.get('server_level'):
                raise PromptNotFoundError('server', guild_id, lang_manager, guild_id)
            
            system_prompts['server_level'] = {}
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 強制清除所有相關快取（確保即時生效）
            self._legacy_force_clear_all_caches(guild_id)
            
            self.logger.info(f"伺服器 {guild_id} 系統提示移除成功")
            return True
            
        except Exception as e:
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            asyncio.create_task(func.report_error(e, "Error removing server system prompt"))
            self.logger.error(f"移除伺服器系統提示時發生錯誤: {e}")
            
            error_message = "移除失敗"
            if lang_manager and guild_id:
                try:
                    error_message = lang_manager.translate(
                        guild_id,
                        "commands", "system_prompt",
                        "errors", "operation_failed"
                    ).format(error=str(e))
                except Exception:
                    pass
            
            raise SystemPromptError(f"移除失敗: {str(e)}")
    
    def copy_channel_prompt(self, source_guild: str, source_channel: str,
                           target_guild: str, target_channel: str) -> bool:
        """
        複製頻道提示設定
        
        Args:
            source_guild: 來源伺服器 ID
            source_channel: 來源頻道 ID
            target_guild: 目標伺服器 ID
            target_channel: 目標頻道 ID
            
        Returns:
            是否複製成功
        """
        try:
            # 取得來源配置
            source_config = self._load_guild_config(source_guild)
            source_prompts = source_config.get('system_prompts', {})
            source_channels = source_prompts.get('channels', {})
            
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            
            if source_channel not in source_channels:
                raise PromptNotFoundError('channel', source_channel, lang_manager, source_guild)
            
            source_data = source_channels[source_channel].copy()
            
            # 更新時間戳記
            source_data.update({
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })
            
            # 設定到目標頻道
            target_config = self._load_guild_config(target_guild)
            
            if 'system_prompts' not in target_config:
                target_config['system_prompts'] = {
                    'enabled': True,
                    'server_level': {},
                    'channels': {},
                    'permissions': {}
                }
            
            target_config['system_prompts']['channels'][target_channel] = source_data
            
            # 保存配置
            self._save_guild_config(target_guild, target_config)
            
            # 強制清除所有相關快取（確保即時生效）
            self._legacy_force_clear_all_caches(target_guild, target_channel)
            
            self.logger.info(f"頻道提示複製成功：{source_guild}:{source_channel} -> {target_guild}:{target_channel}")
            return True
            
        except Exception as e:
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            asyncio.create_task(func.report_error(e, "Error copying channel prompt"))
            self.logger.error(f"複製頻道提示時發生錯誤: {e}")
            
            error_message = "複製失敗"
            if lang_manager and target_guild:
                try:
                    error_message = lang_manager.translate(
                        target_guild,
                        "commands", "system_prompt",
                        "errors", "operation_failed"
                    ).format(error=str(e))
                except Exception:
                    pass
            
            raise SystemPromptError(f"複製失敗: {str(e)}")
    
    def get_available_modules(self) -> List[str]:
        """取得可覆蓋的 YAML 模組列表"""
        try:
            if self._prompt_manager:
                # 從 YAML 提示管理器取得模組列表
                return self._prompt_manager.get_available_modules()
            else:
                # 預設模組列表（基於 YAML 配置）
                return [
                    'base',
                    'personality',
                    'answering_principles',
                    'language',
                    'professionalism',
                    'interaction',
                    'formatting',
                    'professional_personality'
                ]
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting available modules"))
            self.logger.error(f"取得可用模組列表時發生錯誤: {e}")
            return []
    
    def get_default_module_content(self, module_name: str) -> str:
        """
        獲取指定模組的預設內容
        
        Args:
            module_name: 模組名稱
            
        Returns:
            模組的預設內容字串
        """
        try:
            if not self._prompt_manager:
                return ""
            
            # 載入 YAML 配置
            config = self._prompt_manager.loader.load_yaml_config()
            if not config or module_name not in config:
                return ""
            
            module_config = config[module_name]
            
            # 根據模組類型格式化內容
            if module_name == 'base':
                return module_config.get('core_instruction', '')
            elif module_name == 'personality':
                style_items = module_config.get('style', [])
                content_items = module_config.get('content_filtering', [])
                content = ""
                if style_items:
                    content += "風格特點：\n" + "\n".join(f"- {item}" for item in style_items)
                if content_items:
                    if content:
                        content += "\n\n"
                    content += "內容過濾：\n" + "\n".join(f"- {item}" for item in content_items)
                return content
            elif module_name == 'language':
                primary = module_config.get('primary', '')
                elements = module_config.get('style_elements', [])
                length_settings = module_config.get('response_length', {})
                
                content = f"主要語言：{primary}"
                if elements:
                    content += "\n\n風格元素：\n" + "\n".join(f"- {item}" for item in elements)
                if length_settings:
                    content += "\n\n回應長度設定：\n"
                    for key, value in length_settings.items():
                        content += f"- {key}: {value}\n"
                return content
            elif module_name == 'answering_principles':
                focus_items = module_config.get('focus', [])
                info_items = module_config.get('information_handling', [])
                source_format = module_config.get('source_format', '')
                
                content = ""
                if focus_items:
                    content += "專注原則：\n" + "\n".join(f"- {item}" for item in focus_items)
                if info_items:
                    if content:
                        content += "\n\n"
                    content += "資訊處理：\n" + "\n".join(f"- {item}" for item in info_items)
                if source_format:
                    if content:
                        content += "\n\n"
                    content += f"來源格式：{source_format}"
                return content
            else:
                # 通用格式處理
                if isinstance(module_config, dict):
                    content_parts = []
                    for key, value in module_config.items():
                        if isinstance(value, list):
                            content_parts.append(f"{key}：\n" + "\n".join(f"- {item}" for item in value))
                        elif isinstance(value, str):
                            content_parts.append(f"{key}：{value}")
                        elif isinstance(value, dict):
                            sub_content = []
                            for sub_key, sub_value in value.items():
                                if isinstance(sub_value, str):
                                    sub_content.append(f"  - {sub_key}: {sub_value}")
                            if sub_content:
                                content_parts.append(f"{key}：\n" + "\n".join(sub_content))
                    return "\n\n".join(content_parts)
                elif isinstance(module_config, list):
                    return "\n".join(f"- {item}" for item in module_config)
                else:
                    return str(module_config)
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, f"Error getting default content for module '{module_name}'"))
            self.logger.error(f"獲取模組 '{module_name}' 預設內容時發生錯誤: {e}")
            return ""
    
    def get_effective_full_prompt(self, channel_id: str, guild_id: str, for_editing: bool = False) -> str:
        """
        獲取當前有效的完整系統提示（用於直接編輯時顯示）
        
        Args:
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            for_editing: 是否用於編輯（如果是，返回未替換變數的版本）
            
        Returns:
            完整的有效系統提示內容
        """
        try:
            if for_editing:
                # 編輯模式：返回原始配置中的提示（保留變數占位符）
                config = self._load_guild_config(guild_id)
                system_prompts = config.get('system_prompts', {})
                
                # 優先檢查頻道特定提示
                if channel_id:
                    channels = system_prompts.get('channels', {})
                    if channel_id in channels and 'prompt' in channels[channel_id]:
                        return channels[channel_id]['prompt']
                
                # 檢查伺服器級別提示
                server_level = system_prompts.get('server_level', {})
                if 'prompt' in server_level:
                    return server_level['prompt']
                
                # 如果沒有自定義提示，從 YAML 提示取得原始內容
                if self._prompt_manager:
                    try:
                        config = self._prompt_manager.loader.load_yaml_config()
                        default_modules = config.get('composition', {}).get('default_modules', [])
                        return self._prompt_manager.builder.build_system_prompt(config, default_modules)
                    except Exception as yaml_error:
                        self.logger.warning(f"無法取得 YAML 原始提示: {yaml_error}")
                
                return ""
            else:
                # 非編輯模式：返回完全處理後的提示（包含變數替換）
                prompt_data = self.get_effective_prompt(channel_id, guild_id)
                return prompt_data.get('prompt', '')
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting full effective prompt"))
            self.logger.error(f"獲取完整系統提示時發生錯誤: {e}")
            return ""
    
    def get_module_descriptions(self, lang: str = "zh_TW") -> Dict[str, str]:
        """
        獲取模組說明字典
        
        Args:
            lang: 語言代碼
            
        Returns:
            模組名稱對應說明的字典
        """
        # 模組說明字典（支援多語言）
        descriptions = {
            "zh_TW": {
                'base': '定義 AI 的基本身份和核心指令，包括機器人名稱、創建者信息等基礎設定',
                'personality': '設定 AI 的個性特徵和表達風格，包括幽默感、禮貌程度、語言風格等',
                'answering_principles': '規定 AI 回答問題的基本原則，如優先級處理、資訊來源標註等',
                'language': '設定 AI 的語言偏好和表達方式，包括主要語言、風格元素、回應長度等',
                'professionalism': '定義 AI 在專業話題上的表現標準，平衡幽默性與專業性',
                'interaction': '設定 AI 的互動模式，包括對話風格、專注度管理等',
                'formatting': '規定 Discord 環境下的格式化規則，包括 Markdown 語法、提及格式等'
            },
            "zh_CN": {
                'base': '定义 AI 的基本身份和核心指令，包括机器人名称、创建者信息等基础设定',
                'personality': '设定 AI 的个性特征和表达风格，包括幽默感、礼貌程度、语言风格等',
                'answering_principles': '规定 AI 回答问题的基本原则，如优先级处理、信息来源标注等',
                'language': '设定 AI 的语言偏好和表达方式，包括主要语言、风格元素、回应长度等',
                'professionalism': '定义 AI 在专业话题上的表现标准，平衡幽默性与专业性',
                'interaction': '设定 AI 的互动模式，包括对话风格、专注度管理等',
                'formatting': '规定 Discord 环境下的格式化规则，包括 Markdown 语法、提及格式等'
            },
            "en_US": {
                'base': 'Define AI\'s basic identity and core instructions, including bot name, creator info, and basic settings',
                'personality': 'Set AI\'s personality traits and expression style, including humor, politeness, language style, etc.',
                'answering_principles': 'Define basic principles for AI responses, such as priority handling, source attribution, etc.',
                'language': 'Set AI\'s language preferences and expression methods, including primary language, style elements, response length, etc.',
                'professionalism': 'Define AI\'s performance standards on professional topics, balancing humor and professionalism',
                'interaction': 'Set AI\'s interaction modes, including conversation style, focus management, etc.',
                'formatting': 'Define formatting rules for Discord environment, including Markdown syntax, mention formats, etc.'
            },
            "ja_JP": {
                'base': 'AIの基本的なアイデンティティとコア指示を定義し、ボット名、作成者情報などの基本設定を含む',
                'personality': 'AIの個性特性と表現スタイルを設定し、ユーモア、礼儀、言語スタイルなどを含む',
                'answering_principles': 'AI応答の基本原則を規定し、優先度処理、情報源表示などを含む',
                'language': 'AIの言語設定と表現方法を設定し、主要言語、スタイル要素、応答長などを含む',
                'professionalism': '専門的なトピックでのAIのパフォーマンス基準を定義し、ユーモアと専門性のバランスを取る',
                'interaction': 'AIのインタラクションモードを設定し、会話スタイル、集中管理などを含む',
                'formatting': 'Discord環境でのフォーマットルールを規定し、Markdown構文、言及フォーマットなどを含む'
            }
        }
        
        return descriptions.get(lang, descriptions["zh_TW"])
    
    def clear_cache(self, guild_id: Optional[str] = None,
                   channel_id: Optional[str] = None) -> None:
        """
        清除快取（全面同步清除）
        
        Args:
            guild_id: 伺服器 ID（可選）
            channel_id: 頻道 ID（可選）
        """
        if guild_id:
            self.cache.invalidate(guild_id, channel_id)
        else:
            self.cache.clear_all()
        
        # 同步清除 YAML PromptManager 的相關快取
        self._clear_yaml_prompt_cache(guild_id, channel_id)
    
    async def force_clear_all_caches(self, guild_id: str, channel_id: Optional[str] = None, interaction: Optional[object] = None) -> None:
        """
        強制清除所有相關快取（整合版）- 異步版本
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
            interaction: Discord 互動物件（可選）
        """
        self.logger.info(f"🔥 開始強制清除所有快取 - 伺服器: {guild_id}, 頻道: {channel_id}")
        
        # 使用整合的強化快取清除方法
        self._enhanced_force_clear_all_caches(guild_id, channel_id)
        self.logger.info(f"✅ 快取清除完成")
    
    def _enhanced_force_clear_all_caches(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        增強的強制清除所有相關快取方法（整合版）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        self.logger.info(f"🔄 使用增強快取清除方法 - 伺服器: {guild_id}, 頻道: {channel_id}")
        
        # 1. 清除 SystemPromptCache
        self.cache.invalidate(guild_id, channel_id)
        self.logger.debug("✅ 已清除 SystemPromptCache")
        
        # 2. 強化清除 YAML PromptManager 快取
        self._force_clear_yaml_cache(guild_id)
        
        # 3. 強化清除 sendmessage 模組快取
        self._force_clear_sendmessage_cache(guild_id, channel_id)
        
        # 4. 清除可能的其他隱藏快取
        self._clear_hidden_caches(guild_id, channel_id)
        
        # 5. 額外的深度清除策略
        self._deep_cache_cleanup(guild_id, channel_id)
        
        self.logger.info(f"✅ 增強快取清除完成")
    
    def _legacy_force_clear_all_caches(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        原有的強制清除所有相關快取方法（降級使用）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        self.logger.info(f"🔄 使用傳統快取清除方法 - 伺服器: {guild_id}, 頻道: {channel_id}")
        
        # 1. 清除 SystemPromptCache
        self.cache.invalidate(guild_id, channel_id)
        
        # 2. 強制清除 YAML PromptManager 快取
        self._force_clear_yaml_cache(guild_id)
        
        # 3. 清除 sendmessage 模組快取
        self._force_clear_sendmessage_cache(guild_id, channel_id)
        
        # 4. 清除可能的其他隱藏快取
        self._clear_hidden_caches(guild_id, channel_id)
        
        self.logger.info(f"✅ 傳統快取清除完成")
    
    def reload_system_prompts(self, guild_id: str, channel_id: Optional[str] = None) -> bool:
        """
        重新載入系統提示配置（完整重新載入方案）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
            
        Returns:
            是否重新載入成功
        """
        try:
            self.logger.info(f"🔄 開始重新載入系統提示配置 - 伺服器: {guild_id}, 頻道: {channel_id}")
            
            # 1. 強制清除所有快取
            self._legacy_force_clear_all_caches(guild_id, channel_id)
            
            # 2. 重新載入 YAML 配置
            if self._prompt_manager:
                success = self._prompt_manager.reload_prompts()
                if not success:
                    self.logger.warning("YAML 提示重新載入失敗")
            
            # 3. 重新初始化相關組件
            self._reinitialize_components()
            
            # 4. 驗證重新載入結果
            verification_result = self._verify_reload_result(guild_id, channel_id)
            
            self.logger.info(f"✅ 系統提示重新載入完成，驗證結果: {verification_result}")
            return verification_result
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error reloading system prompts"))
            self.logger.error(f"重新載入系統提示時發生錯誤: {e}")
            return False
    
    def _clear_yaml_prompt_cache(self, guild_id: Optional[str] = None,
                                channel_id: Optional[str] = None) -> None:
        """
        清除 YAML PromptManager 的相關快取
        
        Args:
            guild_id: 伺服器 ID（可選）
            channel_id: 頻道 ID（可選）
        """
        try:
            if self._prompt_manager and hasattr(self._prompt_manager, 'cache'):
                if guild_id:
                    # 清除特定伺服器相關的快取項目
                    bot_id = str(self.bot.user.id) if self.bot.user else ""
                    
                    # 清除不同語言的快取鍵
                    languages = ["zh_TW", "zh_CN", "en_US", "ja_JP"]
                    for lang in languages:
                        cache_key = f"system_prompt_{bot_id}_{lang}"
                        self._prompt_manager.cache.invalidate(cache_key)
                        self.logger.debug(f"清除 YAML 快取鍵: {cache_key}")
                else:
                    # 清除所有快取
                    self._prompt_manager.cache.clear_all()
                    self.logger.debug("清除所有 YAML 快取")
                    
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error clearing YAML PromptManager cache"))
            self.logger.warning(f"清除 YAML PromptManager 快取時發生錯誤: {e}")
    
    def _force_clear_yaml_cache(self, guild_id: str) -> None:
        """
        強制清除 YAML PromptManager 的所有相關快取
        
        Args:
            guild_id: 伺服器 ID
        """
        try:
            if self._prompt_manager and hasattr(self._prompt_manager, 'cache'):
                # 取得所有可能的快取鍵值並清除
                bot_id = str(self.bot.user.id) if self.bot.user else ""
                languages = ["zh_TW", "zh_CN", "en_US", "ja_JP"]
                
                # 清除標準快取鍵
                for lang in languages:
                    cache_key = f"system_prompt_{bot_id}_{lang}"
                    self._prompt_manager.cache.invalidate(cache_key)
                    
                    # 清除可能的變體快取鍵
                    for variant in ["", "_fallback", "_cached", f"_{guild_id}"]:
                        variant_key = f"{cache_key}{variant}"
                        self._prompt_manager.cache.invalidate(variant_key)
                
                # 清除預編譯快取
                if hasattr(self._prompt_manager.cache, 'precompiled_cache'):
                    self._prompt_manager.cache.precompiled_cache.clear()
                
                # 強制清理過期項目
                if hasattr(self._prompt_manager.cache, 'cleanup_expired'):
                    self._prompt_manager.cache.cleanup_expired()
                
                self.logger.debug(f"強制清除 YAML 快取完成 - 伺服器: {guild_id}")
                
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error force-clearing YAML cache"))
            self.logger.warning(f"強制清除 YAML 快取時發生錯誤: {e}")
    
    def _force_clear_sendmessage_cache(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        強制清除 prompting 模組的所有相關快取
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        try:
            self.logger.info(f"🔥 開始強制清除 prompting 模組快取 - 伺服器: {guild_id}, 頻道: {channel_id}")
            
            # 清除新架構中的 PromptManager 快取
            try:
                from llm.prompting.manager import get_prompt_manager
                
                # 取得全域 PromptManager 實例
                global_prompt_manager = get_prompt_manager()
                if global_prompt_manager:
                    # 清除主要快取
                    if hasattr(global_prompt_manager, 'cache'):
                        if hasattr(global_prompt_manager.cache, 'clear_all'):
                            global_prompt_manager.cache.clear_all()
                            self.logger.debug("✅ 已清除全域 PromptManager 主要快取")
                    
                    # 清除可能的其他快取屬性
                    cache_attrs = ['_cached_prompts', '_cache', 'prompt_cache', '_prompt_cache', '_system_prompts']
                    for attr in cache_attrs:
                        if hasattr(global_prompt_manager, attr):
                            cache_obj = getattr(global_prompt_manager, attr)
                            if hasattr(cache_obj, 'clear'):
                                cache_obj.clear()
                                self.logger.debug(f"✅ 已清除 {attr}")
                            elif hasattr(cache_obj, 'clear_all'):
                                cache_obj.clear_all()
                                self.logger.debug(f"✅ 已清除 {attr}")
                    
                    # 強制重置時間戳以觸發重新載入
                    timestamp_attrs = ['_last_reload_time', '_last_update_time', '_cache_timestamp']
                    for attr in timestamp_attrs:
                        if hasattr(global_prompt_manager, attr):
                            setattr(global_prompt_manager, attr, 0)
                            self.logger.debug(f"✅ 已重置 {attr}")
                    
                    self.logger.info(f"✅ PromptManager 快取強制清除完成")
                else:
                    self.logger.warning("⚠️ 無法取得 PromptManager 實例")
                    
            except ImportError as import_err:
                self.logger.warning(f"⚠️ 無法匯入 llm.prompting.manager: {import_err}")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error force-clearing prompting cache"))
            self.logger.warning(f"強制清除 prompting 快取時發生錯誤: {e}")
            import traceback
            self.logger.debug(f"詳細錯誤追蹤: {traceback.format_exc()}")
    
    def _clear_hidden_caches(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        清除可能的隱藏快取層級
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        try:
            # 清除可能的模組級別快取
            import sys
            
            # 清除可能被匯入模組的快取
            modules_to_clear = [
                'llm.prompting.manager',
                'llm.prompting.cache',
                'llm.prompting.builder',
                'llm.prompting.system_prompt'
            ]
            
            for module_name in modules_to_clear:
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                    
                    # 檢查模組是否有快取相關的屬性
                    cache_attrs = ['cache', '_cache', 'prompt_cache', '_prompt_cache']
                    for attr in cache_attrs:
                        if hasattr(module, attr):
                            cache_obj = getattr(module, attr)
                            if hasattr(cache_obj, 'clear_all'):
                                cache_obj.clear_all()
                            elif hasattr(cache_obj, 'clear'):
                                cache_obj.clear()
            
            self.logger.debug(f"清除隱藏快取完成 - 伺服器: {guild_id}")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error clearing hidden caches"))
            self.logger.warning(f"清除隱藏快取時發生錯誤: {e}")
    
    def _deep_cache_cleanup(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        深度快取清理（額外的清除策略）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        try:
            self.logger.debug(f"🔍 開始深度快取清理 - 伺服器: {guild_id}")
            
            # 1. 強制垃圾回收以清除可能的記憶體快取
            import gc
            gc.collect()
            
            # 2. 清除可能的函數快取（如果有使用 functools.lru_cache）
            try:
                if hasattr(self, 'get_effective_prompt') and hasattr(self.get_effective_prompt, 'cache_clear'):
                    self.get_effective_prompt.cache_clear()
                    
                if self._prompt_manager and hasattr(self._prompt_manager, 'get_system_prompt'):
                    if hasattr(self._prompt_manager.get_system_prompt, 'cache_clear'):
                        self._prompt_manager.get_system_prompt.cache_clear()
            except Exception as e:
                self.logger.debug(f"清除函數快取時發生錯誤: {e}")
            
            # 3. 重置快取相關的實例變數
            cache_instance_vars = ['_cached_prompts', '_last_cache_clear', '_cache_version']
            for var in cache_instance_vars:
                if hasattr(self, var):
                    if isinstance(getattr(self, var), dict):
                        getattr(self, var).clear()
                    else:
                        setattr(self, var, None)
            
            # 4. 清除可能的單例快取
            try:
                from llm.prompting.manager import _prompt_manager_instances
                if _prompt_manager_instances:
                    _prompt_manager_instances.clear()
                    self.logger.debug("✅ 已清除全域 PromptManager 實例快取")
            except Exception as e:
                self.logger.debug(f"清除全域 PromptManager 實例時發生錯誤: {e}")
            
            self.logger.debug(f"✅ 深度快取清理完成")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error during deep cache cleanup"))
            self.logger.warning(f"深度快取清理時發生錯誤: {e}")
    
    def _reinitialize_components(self) -> None:
        """重新初始化相關組件"""
        try:
            # 重新初始化 YAML 提示管理器
            if self._prompt_manager:
                if hasattr(self._prompt_manager, '_initialized'):
                    self._prompt_manager._initialized = False
                
                # 重新載入配置
                if hasattr(self._prompt_manager, 'loader'):
                    self._prompt_manager.loader._cached_config = None
            
            self.logger.debug("組件重新初始化完成")
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error reinitializing components"))
            self.logger.warning(f"重新初始化組件時發生錯誤: {e}")
    
    def _verify_reload_result(self, guild_id: str, channel_id: Optional[str] = None) -> bool:
        """
        驗證重新載入結果
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
            
        Returns:
            驗證是否成功
        """
        try:
            # 1. 驗證快取已清除
            cache_cleared = True
            if guild_id in [key.split(':')[1] for key in self.cache.cache.keys() if ':' in key]:
                cache_cleared = False
            
            # 2. 驗證配置可以正常載入
            config_loadable = True
            try:
                config = self._load_guild_config(guild_id)
                if not isinstance(config, dict):
                    config_loadable = False
            except Exception:
                config_loadable = False
            
            # 3. 驗證 YAML 提示可以正常取得
            yaml_accessible = True
            try:
                if self._prompt_manager:
                    bot_id = str(self.bot.user.id) if self.bot.user else ""
                    prompt = self._prompt_manager.get_system_prompt(bot_id, None)
                    if not prompt:
                        yaml_accessible = False
            except Exception:
                yaml_accessible = False
            
            verification_result = cache_cleared and config_loadable and yaml_accessible
            
            self.logger.info(f"驗證結果 - 快取清除: {cache_cleared}, 配置載入: {config_loadable}, YAML 存取: {yaml_accessible}")
            
            return verification_result
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error verifying reload result"))
            self.logger.error(f"驗證重新載入結果時發生錯誤: {e}")
            return False
    
    def _load_guild_config(self, guild_id: str) -> Dict[str, Any]:
        """載入伺服器配置"""
        config_file = self.data_dir / f"{guild_id}.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Error loading guild config {guild_id}"))
                self.logger.error(f"載入伺服器配置失敗 {guild_id}: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _save_guild_config(self, guild_id: str, config: Dict[str, Any]) -> None:
        """保存伺服器配置"""
        config_file = self.data_dir / f"{guild_id}.json"
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            lang_manager = self.bot.get_cog("LanguageManager") if hasattr(self.bot, 'get_cog') else None
            asyncio.create_task(func.report_error(e, f"Error saving guild config {guild_id}"))
            self.logger.error(f"保存伺服器配置失敗 {guild_id}: {e}")
            
            error_message = f"無法保存配置: {str(e)}"
            if lang_manager and guild_id:
                try:
                    error_message = lang_manager.translate(
                        guild_id,
                        "commands", "system_prompt",
                        "errors", "operation_failed"
                    ).format(error=str(e))
                except Exception:
                    pass
        
            raise ConfigurationError(error_message, str(config_file))
    
    def _get_default_config(self) -> Dict[str, Any]:
        """取得預設配置"""
        return {
            'mode': 'unrestricted',
            'whitelist': [],
            'blacklist': [],
            'auto_response': {},
            'system_prompts': {
                'enabled': True,
                'server_level': {},
                'channels': {},
                'permissions': {
                    'allowed_roles': [],
                    'allowed_users': [],
                    'manage_server_prompts': []
                }
            }
        }
    
    def _get_yaml_prompt(self, guild_id: str, message: Optional[discord.Message] = None) -> Dict[str, Any]:
        """取得 YAML 基礎提示"""
        try:
            if self._prompt_manager:
                bot_id = str(self.bot.user.id) if self.bot.user else ""
                prompt = self._prompt_manager.get_system_prompt(bot_id, message)
                return {
                    'prompt': prompt,
                    'source': 'yaml',
                    'timestamp': time.time()
                }
            else:
                return {
                    'prompt': '',
                    'source': 'none',
                    'timestamp': time.time()
                }
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting YAML prompt"))
            self.logger.error(f"取得 YAML 提示時發生錯誤: {e}")
            return {
                'prompt': '',
                'source': 'error',
                'timestamp': time.time()
            }
    
    def _append_protected_suffix(self, prompt: str) -> str:
        """Re-appends critical protected modules (output_format, reminders) from base YAML.

        Called only after a full `prompt` replacement, which discards the base content.
        Ensures <som>/<eom> rules and thinking-model ordering are never silently lost.
        The protected content goes through variable replacement in the caller.
        """
        try:
            from llm.prompting.protected_prompt_manager import get_protected_prompt_manager
            protected_manager = get_protected_prompt_manager()
            parts = []
            for module_name in ("output_format", "reminders"):
                content = protected_manager.get_protected_module(module_name)
                if content and content.strip():
                    parts.append(content.strip())
            if parts:
                return prompt + "\n\n" + "\n\n".join(parts)
            return prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "_append_protected_suffix failed"))
            self.logger.warning(f"_append_protected_suffix failed, protected modules may be missing: {e}")
            return prompt

    def _apply_server_overrides(self, base_prompt: str, server_config: Dict[str, Any], guild_id: Optional[str] = None) -> str:
        """應用伺服器級別覆蓋"""
        try:
            if 'prompt' in server_config:
                prompt = server_config['prompt']
                # Full replacement discards the base prompt entirely.
                # Re-attach output_format + reminders so critical rules are never lost.
                prompt = self._append_protected_suffix(prompt)
                return self._apply_variable_replacements(prompt, guild_id)

            # 模組覆蓋邏輯 — 僅允許覆蓋可自訂模組，保護模組永遠從 YAML 載入
            from llm.prompting.protected_prompt_manager import ProtectedPromptManager
            modules = {
                k: v for k, v in server_config.get('modules', {}).items()
                if k not in ProtectedPromptManager.PROTECTED_MODULES
            }
            override_modules = [
                m for m in server_config.get('override_modules', [])
                if m not in ProtectedPromptManager.PROTECTED_MODULES
            ]

            if modules or override_modules:
                prompt = self._rebuild_prompt_with_module_overrides(modules, override_modules)
                self.logger.info(f"🔄 伺服器級別應用模組覆蓋：{list(modules.keys())}")
            else:
                prompt = base_prompt

            # 追加內容
            if 'append_content' in server_config:
                prompt += f"\n\n{server_config['append_content']}"

            return self._apply_variable_replacements(prompt, guild_id)

        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error applying server overrides"))
            self.logger.error(f"應用伺服器覆蓋時發生錯誤: {e}")
            return base_prompt

    def _apply_channel_overrides(self, base_prompt: str, channel_config: Dict[str, Any], guild_id: Optional[str] = None) -> str:
        """應用頻道級別覆蓋"""
        try:
            if 'prompt' in channel_config:
                prompt = channel_config['prompt']
                # Full replacement discards the base prompt entirely.
                # Re-attach output_format + reminders so critical rules are never lost.
                prompt = self._append_protected_suffix(prompt)
                return self._apply_variable_replacements(prompt, guild_id)

            # 模組覆蓋邏輯 — 僅允許覆蓋可自訂模組，保護模組永遠從 YAML 載入
            from llm.prompting.protected_prompt_manager import ProtectedPromptManager
            modules = {
                k: v for k, v in channel_config.get('modules', {}).items()
                if k not in ProtectedPromptManager.PROTECTED_MODULES
            }
            override_modules = [
                m for m in channel_config.get('override_modules', [])
                if m not in ProtectedPromptManager.PROTECTED_MODULES
            ]

            if modules or override_modules:
                prompt = self._rebuild_prompt_with_module_overrides(modules, override_modules)
                self.logger.info(f"🔄 頻道級別應用模組覆蓋：{list(modules.keys())}")
            else:
                prompt = base_prompt

            # 追加內容
            if 'append_content' in channel_config:
                prompt += f"\n\n{channel_config['append_content']}"

            return self._apply_variable_replacements(prompt, guild_id)

        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error applying channel overrides"))
            self.logger.error(f"應用頻道覆蓋時發生錯誤: {e}")
            return base_prompt
    
    def _apply_language_localization(self, prompt: str, lang: str, guild_id: str) -> str:
        """應用語言本地化"""
        try:
            lang_manager = self.bot.get_cog("LanguageManager")
            if not lang_manager:
                return prompt
            
            # 語言特定的替換規則
            language_replacements = {
                'zh_TW': {
                    'Always answer in Traditional Chinese': '總是使用繁體中文回答',
                    'Keep responses concise': '保持回答簡潔'
                },
                'zh_CN': {
                    'Always answer in Traditional Chinese': '总是使用简体中文回答',
                    'Keep responses concise': '保持回答简洁'
                },
                'en_US': {
                    'Always answer in Traditional Chinese': 'Always answer in English',
                    'Keep responses concise': 'Keep responses concise'
                },
                'ja_JP': {
                    'Always answer in Traditional Chinese': '常に日本語で回答してください',
                    'Keep responses concise': '回答は簡潔に保ってください'
                }
            }
            
            replacements = language_replacements.get(lang, {})
            for original, replacement in replacements.items():
                prompt = prompt.replace(original, replacement)
            
            return prompt
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error applying language localization"))
            self.logger.error(f"應用語言本地化時發生錯誤: {e}")
            return prompt
    
    def _rebuild_prompt_with_module_overrides(self, module_overrides: Dict[str, str],
                                            override_modules: List[str] = None) -> str:
        """
        使用模組覆蓋重新建構 YAML 提示
        
        Args:
            module_overrides: 模組覆蓋字典 {模組名: 覆蓋內容}
            override_modules: 要覆蓋的模組列表
            
        Returns:
            重新建構的提示字串
        """
        try:
            if not self._prompt_manager:
                self.logger.warning("PromptManager 未初始化，無法重新建構提示")
                return ""
            
            self.logger.debug(f"🔧 開始重新建構提示，覆蓋模組: {list(module_overrides.keys())}")
            
            # 取得原始 YAML 配置
            config = self._prompt_manager.loader.load_yaml_config()
            if not config:
                self.logger.error("無法載入 YAML 配置")
                return ""
            
            # 創建配置副本以進行修改
            modified_config = config.copy()
            
            # 應用模組覆蓋
            for module_name, module_content in module_overrides.items():
                if module_name in config:
                    self.logger.debug(f"📝 覆蓋模組 '{module_name}': {module_content[:50]}...")
                    
                    # 將字串內容轉換為適合的模組結構
                    if module_name == 'personality':
                        modified_config[module_name] = {
                            'style': [module_content],
                            'content_filtering': modified_config[module_name].get('content_filtering', [])
                        }
                    elif module_name == 'language':
                        modified_config[module_name] = {
                            'primary': module_content,
                            'style_elements': modified_config[module_name].get('style_elements', []),
                            'response_length': modified_config[module_name].get('response_length', {})
                        }
                    elif module_name == 'base':
                        # 基礎模組需要保持結構，只覆蓋核心指令
                        base_config = modified_config[module_name].copy()
                        base_config['core_instruction'] = module_content
                        modified_config[module_name] = base_config
                    else:
                        # 其他模組使用通用格式
                        if isinstance(config.get(module_name), dict):
                            # 保持原始結構，添加覆蓋內容
                            original_module = config[module_name].copy()
                            original_module['override_content'] = [module_content]
                            modified_config[module_name] = original_module
                        else:
                            # 簡單結構
                            modified_config[module_name] = {'content': [module_content]}
                else:
                    self.logger.warning(f"⚠️ 模組 '{module_name}' 不存在於 YAML 配置中")
            
            # 取得預設模組列表
            default_modules = modified_config.get('composition', {}).get('default_modules', [])
            
            # 使用修改後的配置重新建構提示
            prompt = self._prompt_manager.builder.build_system_prompt(modified_config, default_modules)
            
            self.logger.info(f"✅ 重新建構提示完成，長度: {len(prompt)}")
            self.logger.debug(f"重新建構的提示預覽: {prompt[:200]}...")
            
            return prompt
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error rebuilding prompt with module overrides"))
            self.logger.error(f"重新建構提示時發生錯誤: {e}")
            # 降級到原始提示
            if self._prompt_manager:
                try:
                    config = self._prompt_manager.loader.load_yaml_config()
                    default_modules = config.get('composition', {}).get('default_modules', [])
                    return self._prompt_manager.builder.build_system_prompt(config, default_modules)
                except Exception as fallback_error:
                    asyncio.create_task(func.report_error(fallback_error, "Fallback prompt rebuild failed"))
                    self.logger.error(f"降級重建也失敗: {fallback_error}")
            return ""
    
    def _apply_variable_replacements(self, prompt: str, guild_id: Optional[str] = None) -> str:
        """
        對系統提示應用變數替換
        
        Args:
            prompt: 包含變數占位符的提示字串
            guild_id: 伺服器 ID（用於語言本地化）
            
        Returns:
            替換變數後的提示字串
        """
        try:
            # 獲取必要的變數
            variables = self._get_system_variables()
            
            if self._prompt_manager and hasattr(self._prompt_manager, 'builder'):
                # 獲取語言管理器
                lang_manager = self.bot.get_cog("LanguageManager")
                
                formatted_prompt = self._prompt_manager.builder.format_with_variables(
                    prompt, variables, lang_manager, guild_id
                )
                self.logger.debug(f"✅ 變數替換完成 - 原長度: {len(prompt)}, 新長度: {len(formatted_prompt)}")
                return formatted_prompt
            else:
                # 降級策略：直接使用 format 方法
                formatted_prompt = prompt.format(**variables)
                self.logger.debug(f"✅ 變數替換完成（降級策略）- 原長度: {len(prompt)}, 新長度: {len(formatted_prompt)}")
                return formatted_prompt
                
        except KeyError as e:
            self.logger.warning(f"⚠️ 變數替換時缺少變數: {e}，返回原始提示")
            return prompt
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error during variable replacement"))
            self.logger.error(f"❌ 變數替換時發生錯誤: {e}，返回原始提示")
            return prompt
    
    def _get_system_variables(self) -> Dict[str, Any]:
        """
        獲取系統變數字典
        
        Returns:
            系統變數字典
        """
        try:
            variables = {}
            
            # 獲取機器人 ID
            if self.bot and hasattr(self.bot, 'user') and self.bot.user:
                variables['bot_id'] = str(self.bot.user.id)
            else:
                variables['bot_id'] = '0'  # 預設值
            
            # 獲取機器人擁有者 ID
            try:
                from addons.tokens import tokens
                variables['bot_owner_id'] = getattr(tokens, 'bot_owner_id', 0)
            except ImportError:
                variables['bot_owner_id'] = 0
            
            # 🔧 修復：從 YAML 配置中取得預設值，確保所有變數都可用
            try:
                if self._prompt_manager:
                    config = self._prompt_manager.loader.load_yaml_config()
                    base_config = config.get('base', {})
                    variables['bot_name'] = base_config.get('bot_name', '🐖🐖')
                    variables['creator'] = base_config.get('creator', '星豬')
                    variables['environment'] = base_config.get('environment', 'Discord server')
                else:
                    # 降級預設值
                    variables['bot_name'] = '🐖🐖'
                    variables['creator'] = '星豬'
                    variables['environment'] = 'Discord server'
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Could not get base variables from YAML"))
                self.logger.warning(f"無法從 YAML 取得基礎變數，使用預設值: {e}")
                variables['bot_name'] = '🐖🐖'
                variables['creator'] = '星豬'
                variables['environment'] = 'Discord server'
            
            # 添加其他可能的系統變數
            variables['timestamp'] = time.time()
            
            self.logger.debug(f"🔧 系統變數已準備: {list(variables.keys())}")
            return variables
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting system variables"))
            self.logger.error(f"獲取系統變數時發生錯誤: {e}")
            return {
                'bot_id': '0',
                'bot_owner_id': 0,
                'bot_name': '🐖🐖',
                'creator': '星豬',
                'environment': 'Discord server',
                'timestamp': time.time()
            }
    
    def _get_language(self, guild_id: str, message: Optional[discord.Message] = None) -> str:
        """取得語言設定"""
        try:
            lang_manager = self.bot.get_cog("LanguageManager")
            if lang_manager:
                return lang_manager.get_server_lang(guild_id)
            return "zh_TW"
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error getting language"))
            return "zh_TW"
    
    async def debug_cache_state(self, guild_id: str, channel_id: str = None) -> Dict[str, Any]:
        """
        快取狀態除錯（供管理員使用）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
            
        Returns:
            詳細的快取狀態報告
        """
        try:
            import time
            cache_info = {
                'timestamp': time.time(),
                'guild_id': guild_id,
                'channel_id': channel_id,
                'system_prompt_cache': {},
                'yaml_cache_info': {},
                'sendmessage_cache_info': {}
            }
            
            # 檢查 SystemPromptCache 狀態
            cache_keys = [key for key in self.cache.cache.keys() if guild_id in key]
            cache_info['system_prompt_cache'] = {
                'total_keys': len(self.cache.cache),
                'guild_related_keys': len(cache_keys),
                'keys': cache_keys
            }
            
            # 檢查 YAML PromptManager 快取
            if self._prompt_manager and hasattr(self._prompt_manager, 'cache'):
                cache_info['yaml_cache_info'] = {
                    'cache_available': True,
                    'cache_size': len(self._prompt_manager.cache.cache) if hasattr(self._prompt_manager.cache, 'cache') else 0
                }
            
            self.logger.info(f"快取狀態除錯完成: {cache_info}")
            return cache_info
            
        except Exception as e:
            await func.report_error(e, "Failed to debug cache state")
            self.logger.error(f"快取狀態除錯失敗: {e}")
            return {'error': str(e)}
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        取得診斷資訊
        
        Returns:
            診斷資訊字典
        """
        try:
            import time
            diagnostics = {
                'timestamp': time.time(),
                'cache_manager_available': self.cache is not None,
                'prompt_manager_available': self._prompt_manager is not None,
                'total_cache_items': len(self.cache.cache) if self.cache else 0,
                'cache_ttl': self.cache.ttl if self.cache else 0
            }
            
            return diagnostics
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Failed to get diagnostics"))
            self.logger.error(f"取得診斷資訊失敗: {e}")
            return {'error': str(e)}
    
    async def handle_discord_interaction_cache_issues(self, interaction) -> Dict[str, Any]:
        """
        處理 Discord 互動的快取問題（整合版）
        
        Args:
            interaction: Discord 互動物件
            
        Returns:
            處理結果報告
        """
        try:
            import time
            guild_id = str(interaction.guild.id) if interaction.guild else None
            channel_id = str(interaction.channel.id) if interaction.channel else None
            
            if guild_id:
                # 使用增強的快取清除策略
                self._enhanced_force_clear_all_caches(guild_id, channel_id)
                return {
                    'success': True,
                    'method': 'enhanced_clear',
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'timestamp': time.time()
                }
            else:
                return {'error': '無法取得有效的 guild_id', 'method': 'no_guild'}
                
        except Exception as e:
            await func.report_error(e, "Failed to handle discord interaction cache issues")
            self.logger.error(f"handle_discord_interaction_cache_issues 失敗: {e}")
    
    def reload_all_configs(self) -> bool:
        """
        重新載入所有配置（用於 UI 介面）
        
        Returns:
            是否重新載入成功
        """
        try:
            self.logger.info("🔄 開始重新載入所有配置")
            
            # 清除所有快取
            self.clear_cache()
            
            # 重新載入 YAML 配置
            if self._prompt_manager:
                if hasattr(self._prompt_manager, 'reload_prompts'):
                    success = self._prompt_manager.reload_prompts()
                    if not success:
                        self.logger.warning("YAML 提示重新載入失敗")
                else:
                    # 如果沒有 reload_prompts 方法，嘗試重新初始化
                    self._init_prompt_manager()
            
            # 重新初始化組件
            self._reinitialize_components()
            
            self.logger.info("✅ 所有配置重新載入完成")
            return True
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error reloading all configs"))
            self.logger.error(f"重新載入所有配置時發生錯誤: {e}")
            return False
            return {'error': str(e), 'method': 'exception'}