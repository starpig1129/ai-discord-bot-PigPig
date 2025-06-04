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
            
            # 清除快取
            self.logger.debug(f"🗑️ 清除快取: {guild_id}:{channel_id}")
            self.cache.invalidate(guild_id, channel_id)
            
            self.logger.info(f"✅ 頻道 {channel_id} 系統提示設定成功，操作者: {user_id}")
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
            
            # 模組覆蓋邏輯 - 重新建構 YAML 提示
            modules = server_config.get('modules', {})
            override_modules = server_config.get('override_modules', [])
            
            if modules or override_modules:
                prompt = self._rebuild_prompt_with_module_overrides(modules, override_modules)
                self.logger.info(f"🔄 伺服器級別應用模組覆蓋：{list(modules.keys())}")
            else:
                prompt = base_prompt
            
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
            
            # 模組覆蓋邏輯 - 重新建構 YAML 提示
            modules = channel_config.get('modules', {})
            override_modules = channel_config.get('override_modules', [])
            
            if modules or override_modules:
                prompt = self._rebuild_prompt_with_module_overrides(modules, override_modules)
                self.logger.info(f"🔄 頻道級別應用模組覆蓋：{list(modules.keys())}")
            else:
                prompt = base_prompt
            
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
            self.logger.error(f"重新建構提示時發生錯誤: {e}")
            # 降級到原始提示
            if self._prompt_manager:
                try:
                    config = self._prompt_manager.loader.load_yaml_config()
                    default_modules = config.get('composition', {}).get('default_modules', [])
                    return self._prompt_manager.builder.build_system_prompt(config, default_modules)
                except Exception as fallback_error:
                    self.logger.error(f"降級重建也失敗: {fallback_error}")
            return ""
    
    def _get_language(self, guild_id: str, message: Optional[discord.Message] = None) -> str:
        """取得語言設定"""
        try:
            lang_manager = self.bot.get_cog("LanguageManager")
            if lang_manager:
                return lang_manager.get_server_lang(guild_id)
            return "zh_TW"
        except Exception:
            return "zh_TW"