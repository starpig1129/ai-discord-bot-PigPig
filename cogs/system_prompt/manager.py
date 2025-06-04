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

# 生產環境快取修復器已整合到核心模組中，不再需要外部依賴
PRODUCTION_CACHE_FIXER_AVAILABLE = False
ProductionCacheFixer = None


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
        
        # 快取清除策略已整合到核心方法中
        self.logger.info("✅ 使用整合快取清除策略")
    
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
            
            # 強制清除所有相關快取（確保即時生效）
            self.logger.debug(f"🗑️ 強制清除所有快取: {guild_id}:{channel_id}")
            # 使用同步版本的清除方法，避免異步問題
            self._legacy_force_clear_all_caches(guild_id, channel_id)
            
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
            
            # 清除快取（全面同步）
            self.clear_cache(guild_id)
            
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
            
            # 清除快取（全面同步）
            self.clear_cache(guild_id, channel_id)
            
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
            
            # 強制清除所有相關快取（確保即時生效）
            self._legacy_force_clear_all_caches(guild_id)
            
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
            
            # 強制清除所有相關快取（確保即時生效）
            self._legacy_force_clear_all_caches(target_guild, target_channel)
            
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
            self.logger.error(f"重新載入系統提示時發生錯誤: {e}")
            return False
    
    def _clear_yaml_prompt_cache(self, guild_id: Optional[str] = None,
                                channel_id: Optional[str] = None) -> None:
        """
        清除 YAML PromptManager 和 sendmessage 的相關快取
        
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
            
            # 同步清除 sendmessage 模組的快取
            try:
                from gpt.sendmessage import clear_system_prompt_cache
                clear_system_prompt_cache(guild_id, channel_id)
                self.logger.debug("已同步清除 sendmessage 快取")
            except ImportError:
                self.logger.warning("無法匯入 sendmessage 快取清除函式")
                    
        except Exception as e:
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
            self.logger.warning(f"強制清除 YAML 快取時發生錯誤: {e}")
    
    def _force_clear_sendmessage_cache(self, guild_id: str, channel_id: Optional[str] = None) -> None:
        """
        強制清除 sendmessage 模組的所有相關快取（加強版）
        
        Args:
            guild_id: 伺服器 ID
            channel_id: 頻道 ID（可選）
        """
        try:
            self.logger.info(f"🔥 開始強制清除 sendmessage 快取 - 伺服器: {guild_id}, 頻道: {channel_id}")
            
            # 清除 sendmessage 模組快取（使用加強版清除）
            from gpt.sendmessage import clear_system_prompt_cache, _get_prompt_manager
            
            # 使用加強版快取清除
            clear_system_prompt_cache(guild_id, channel_id)
            
            # 額外清除全域 PromptManager 實例的所有可能快取
            global_prompt_manager = _get_prompt_manager()
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
                
            self.logger.info(f"✅ sendmessage 快取強制清除完成")
            
        except Exception as e:
            self.logger.warning(f"強制清除 sendmessage 快取時發生錯誤: {e}")
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
                'gpt.prompt_manager',
                'gpt.sendmessage',
                'gpt.prompt_cache',
                'gpt.prompt_builder'
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
                from gpt import sendmessage
                if hasattr(sendmessage, '_prompt_manager'):
                    sendmessage._prompt_manager = None
                    self.logger.debug("✅ 已重置 sendmessage 全域 PromptManager")
            except Exception as e:
                self.logger.debug(f"重置全域變數時發生錯誤: {e}")
            
            self.logger.debug(f"✅ 深度快取清理完成")
            
        except Exception as e:
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
            self.logger.error(f"handle_discord_interaction_cache_issues 失敗: {e}")
            return {'error': str(e), 'method': 'exception'}