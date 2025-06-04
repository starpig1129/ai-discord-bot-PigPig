"""
頻道系統提示管理器

提供核心的系統提示管理功能，包含三層繼承機制、快取系統和配置管理。
"""

import json
import os
import time
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import discord

from .exceptions import (
    SystemPromptError,
    ValidationError,
    ConfigurationError,
    ContentTooLongError,
    UnsafeContentError,
    PromptNotFoundError
)
from .permissions import PermissionValidator


class SystemPromptCache:
    """系統提示快取管理器"""
    
    def __init__(self, ttl: int = 3600):
        """
        初始化快取管理器
        
        Args:
            ttl: 快取生存時間（秒）
        """
        self.cache: Dict[str, Tuple[float, str]] = {}
        self.ttl = ttl
    
    def get_cache_key(self, guild_id: str, channel_id: str, lang: str = "zh_TW") -> str:
        """生成快取鍵值"""
        return f"system_prompt:{guild_id}:{channel_id}:{lang}"
    
    def get(self, guild_id: str, channel_id: str, lang: str = "zh_TW") -> Optional[str]:
        """從快取取得系統提示"""
        key = self.get_cache_key(guild_id, channel_id, lang)
        if key in self.cache:
            timestamp, prompt = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return prompt
            else:
                del self.cache[key]
        return None
    
    def set(self, guild_id: str, channel_id: str, prompt: str, lang: str = "zh_TW") -> None:
        """設定快取"""
        key = self.get_cache_key(guild_id, channel_id, lang)
        self.cache[key] = (time.time(), prompt)
    
    def invalidate(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """清除快取"""
        pattern = f"system_prompt:{guild_id}"
        if channel_id:
            pattern += f":{channel_id}"
        
        keys_to_remove = [key for key in self.cache.keys() if key.startswith(pattern)]
        for key in keys_to_remove:
            del self.cache[key]
    
    def clear_all(self) -> None:
        """清除所有快取"""
        self.cache.clear()


class PromptValidator:
    """系統提示驗證器"""
    
    MAX_PROMPT_LENGTH = 4000
    MAX_MODULE_COUNT = 10
    
    # 危險模式列表
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
        驗證提示內容
        
        Args:
            content: 提示內容
            
        Returns:
            (是否有效, 錯誤訊息)
        """
        # 長度檢查
        if len(content) > self.MAX_PROMPT_LENGTH:
            raise ContentTooLongError(self.MAX_PROMPT_LENGTH, len(content))
        
        # 基本格式檢查
        if not content.strip():
            raise ValidationError("系統提示不能為空", "content")
        
        # 檢查潛在的注入攻擊
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                raise UnsafeContentError(pattern)
        
        return True, ""
    
    def validate_modules(self, modules: Dict[str, str]) -> Tuple[bool, str]:
        """
        驗證模組設定
        
        Args:
            modules: 模組字典
            
        Returns:
            (是否有效, 錯誤訊息)
        """
        if len(modules) > self.MAX_MODULE_COUNT:
            raise ValidationError(f"模組數量過多，最多 {self.MAX_MODULE_COUNT} 個")
        
        for module_name, module_content in modules.items():
            if not isinstance(module_content, str):
                raise ValidationError(f"模組 '{module_name}' 的內容必須是字串")
            
            self.validate_prompt_content(module_content)
        
        return True, ""


class SystemPromptManager:
    """系統提示管理器 - 核心協調器"""
    
    def __init__(self, bot: discord.Client):
        """
        初始化系統提示管理器
        
        Args:
            bot: Discord 機器人實例
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.cache = SystemPromptCache()
        self.validator = PromptValidator()
        self.permission_validator = PermissionValidator(bot)
        
        # 資料目錄路徑
        self.data_dir = Path("data/channel_configs")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 YAML 提示管理器
        self._prompt_manager = None
        self._init_prompt_manager()
    
    def _init_prompt_manager(self) -> None:
        """初始化 YAML 提示管理器"""
        try:
            from gpt.prompt_manager import get_prompt_manager
            self._prompt_manager = get_prompt_manager()
        except Exception as e:
            self.logger.error(f"Failed to initialize PromptManager: {e}")
            self._prompt_manager = None
    
    def get_effective_prompt(self, channel_id: str, guild_id: str, 
                           message: Optional[discord.Message] = None) -> Dict[str, Any]:
        """
        取得有效的系統提示（整合三層繼承）
        
        Args:
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            message: Discord 訊息物件（用於語言檢測）
            
        Returns:
            包含提示內容和來源的字典
        """
        try:
            # 嘗試從快取取得
            lang = self._get_language(guild_id, message)
            cached_prompt = self.cache.get(guild_id, channel_id, lang)
            if cached_prompt:
                return {
                    'prompt': cached_prompt,
                    'source': 'cache',
                    'timestamp': time.time()
                }
            
            # 載入配置
            config = self._load_guild_config(guild_id)
            system_prompts = config.get('system_prompts', {})
            
            if not system_prompts.get('enabled', False):
                # 系統提示功能未啟用，使用 YAML 預設
                return self._get_yaml_prompt(guild_id, message)
            
            # 第一層：載入 YAML 基礎提示
            base_prompt_data = self._get_yaml_prompt(guild_id, message)
            base_prompt = base_prompt_data.get('prompt', '')
            
            # 第二層：應用伺服器級別提示
            server_level = system_prompts.get('server_level', {})
            if server_level:
                prompt = self._apply_server_overrides(base_prompt, server_level)
                source = 'server'
            else:
                prompt = base_prompt
                source = 'yaml'
            
            # 第三層：應用頻道級別提示
            channels = system_prompts.get('channels', {})
            channel_config = channels.get(channel_id)
            
            if channel_config and channel_config.get('enabled', True):
                prompt = self._apply_channel_overrides(prompt, channel_config)
                source = 'channel'
            
            # 應用語言本地化
            prompt = self._apply_language_localization(prompt, lang, guild_id)
            
            # 快取結果
            self.cache.set(guild_id, channel_id, prompt, lang)
            
            return {
                'prompt': prompt,
                'source': source,
                'timestamp': time.time(),
                'language': lang
            }
            
        except Exception as e:
            self.logger.error(f"取得有效系統提示時發生錯誤: {e}")
            # 降級到 YAML 提示
            return self._get_yaml_prompt(guild_id, message)
    
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
            
            # 設定頻道提示
            channels = config['system_prompts']['channels']
            if channel_id not in channels:
                channels[channel_id] = {}
            
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
            
            if 'modules' in prompt_data:
                channel_config['modules'] = prompt_data['modules']
            
            if 'override_modules' in prompt_data:
                channel_config['override_modules'] = prompt_data['override_modules']
            
            if 'append_content' in prompt_data:
                channel_config['append_content'] = prompt_data['append_content']
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 清除快取
            self.cache.invalidate(guild_id, channel_id)
            
            self.logger.info(f"頻道 {channel_id} 系統提示設定成功，操作者: {user_id}")
            return True
            
        except Exception as e:
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
            
            # 清除快取
            self.cache.invalidate(guild_id)
            
            self.logger.info(f"伺服器 {guild_id} 系統提示設定成功，操作者: {user_id}")
            return True
            
        except Exception as e:
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
            
            if channel_id not in channels:
                raise PromptNotFoundError('channel', channel_id)
            
            del channels[channel_id]
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 清除快取
            self.cache.invalidate(guild_id, channel_id)
            
            self.logger.info(f"頻道 {channel_id} 系統提示移除成功")
            return True
            
        except Exception as e:
            self.logger.error(f"移除頻道系統提示時發生錯誤: {e}")
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
            if not system_prompts.get('server_level'):
                raise PromptNotFoundError('server', guild_id)
            
            system_prompts['server_level'] = {}
            
            # 保存配置
            self._save_guild_config(guild_id, config)
            
            # 清除快取
            self.cache.invalidate(guild_id)
            
            self.logger.info(f"伺服器 {guild_id} 系統提示移除成功")
            return True
            
        except Exception as e:
            self.logger.error(f"移除伺服器系統提示時發生錯誤: {e}")
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
            
            if source_channel not in source_channels:
                raise PromptNotFoundError('channel', source_channel)
            
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
            
            # 清除快取
            self.cache.invalidate(target_guild, target_channel)
            
            self.logger.info(f"頻道提示複製成功：{source_guild}:{source_channel} -> {target_guild}:{target_channel}")
            return True
            
        except Exception as e:
            self.logger.error(f"複製頻道提示時發生錯誤: {e}")
            raise SystemPromptError(f"複製失敗: {str(e)}")
    
    def get_available_modules(self) -> List[str]:
        """取得可覆蓋的 YAML 模組列表"""
        try:
            if self._prompt_manager:
                # 從 YAML 提示管理器取得模組列表
                return self._prompt_manager.get_available_modules()
            else:
                # 預設模組列表
                return [
                    'personality',
                    'interaction_style',
                    'language_preference',
                    'technical_focus',
                    'response_format',
                    'behavior_rules'
                ]
        except Exception as e:
            self.logger.error(f"取得可用模組列表時發生錯誤: {e}")
            return []
    
    def clear_cache(self, guild_id: Optional[str] = None, 
                   channel_id: Optional[str] = None) -> None:
        """
        清除快取
        
        Args:
            guild_id: 伺服器 ID（可選）
            channel_id: 頻道 ID（可選）
        """
        if guild_id:
            self.cache.invalidate(guild_id, channel_id)
        else:
            self.cache.clear_all()
    
    def _load_guild_config(self, guild_id: str) -> Dict[str, Any]:
        """載入伺服器配置"""
        config_file = self.data_dir / f"{guild_id}.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
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
            self.logger.error(f"保存伺服器配置失敗 {guild_id}: {e}")
            raise ConfigurationError(f"無法保存配置: {str(e)}", str(config_file))
    
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
            self.logger.error(f"取得 YAML 提示時發生錯誤: {e}")
            return {
                'prompt': '',
                'source': 'error',
                'timestamp': time.time()
            }
    
    def _apply_server_overrides(self, base_prompt: str, server_config: Dict[str, Any]) -> str:
        """應用伺服器級別覆蓋"""
        try:
            if 'prompt' in server_config:
                return server_config['prompt']
            
            # 模組覆蓋邏輯
            prompt = base_prompt
            modules = server_config.get('modules', {})
            
            for module_name, module_content in modules.items():
                # 簡單的模組替換邏輯（可擴展）
                prompt = prompt.replace(f"[{module_name}]", module_content)
            
            # 追加內容
            if 'append_content' in server_config:
                prompt += f"\n\n{server_config['append_content']}"
            
            return prompt
            
        except Exception as e:
            self.logger.error(f"應用伺服器覆蓋時發生錯誤: {e}")
            return base_prompt
    
    def _apply_channel_overrides(self, base_prompt: str, channel_config: Dict[str, Any]) -> str:
        """應用頻道級別覆蓋"""
        try:
            if 'prompt' in channel_config:
                return channel_config['prompt']
            
            # 模組覆蓋邏輯
            prompt = base_prompt
            modules = channel_config.get('modules', {})
            
            for module_name, module_content in modules.items():
                prompt = prompt.replace(f"[{module_name}]", module_content)
            
            # 追加內容
            if 'append_content' in channel_config:
                prompt += f"\n\n{channel_config['append_content']}"
            
            return prompt
            
        except Exception as e:
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
            self.logger.error(f"應用語言本地化時發生錯誤: {e}")
            return prompt
    
    def _get_language(self, guild_id: str, message: Optional[discord.Message] = None) -> str:
        """取得語言設定"""
        try:
            lang_manager = self.bot.get_cog("LanguageManager")
            if lang_manager:
                return lang_manager.get_server_lang(guild_id)
            return "zh_TW"
        except Exception:
            return "zh_TW"