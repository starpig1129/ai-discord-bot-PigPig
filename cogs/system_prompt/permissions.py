"""
頻道系統提示管理模組的權限驗證器

提供完整的權限檢查和驗證邏輯，支援多層權限控制。
"""

import discord
import logging
from typing import Dict, List, Optional, Set
from .exceptions import PermissionError


class PermissionValidator:
    """權限驗證器類別"""
    
    def __init__(self, bot: discord.Client):
        """
        初始化權限驗證器
        
        Args:
            bot: Discord 機器人實例
        """
        self.bot = bot
        self.logger = logging.getLogger(__name__)
    
    def can_modify_channel_prompt(self, user: discord.Member, 
                                 channel: discord.TextChannel,
                                 config: Optional[Dict] = None) -> bool:
        """
        檢查用戶是否可修改頻道提示
        
        Args:
            user: Discord 用戶
            channel: 目標頻道
            config: 頻道配置（可選）
            
        Returns:
            是否有權限
        """
        try:
            # 1. 檢查機器人擁有者權限
            if self._is_bot_owner(user):
                return True
            
            # 2. 檢查伺服器管理員權限
            if user.guild_permissions.administrator:
                return True
            
            # 3. 檢查頻道管理權限
            if channel.permissions_for(user).manage_channels:
                return True
            
            # 4. 檢查自訂權限配置
            if config and self._has_custom_permission(user, channel, config):
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"檢查頻道提示修改權限時發生錯誤: {e}")
            return False
    
    def can_modify_server_prompt(self, user: discord.Member, 
                                guild: discord.Guild,
                                config: Optional[Dict] = None) -> bool:
        """
        檢查用戶是否可修改伺服器提示
        
        Args:
            user: Discord 用戶
            guild: 目標伺服器
            config: 伺服器配置（可選）
            
        Returns:
            是否有權限
        """
        try:
            # 1. 檢查機器人擁有者權限
            if self._is_bot_owner(user):
                return True
            
            # 2. 檢查伺服器管理員權限
            if user.guild_permissions.administrator:
                return True
            
            # 3. 檢查自訂的伺服器級別權限
            if config and self._has_server_level_permission(user, config):
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"檢查伺服器提示修改權限時發生錯誤: {e}")
            return False
    
    def can_view_prompt(self, user: discord.Member, 
                       channel: Optional[discord.TextChannel] = None) -> bool:
        """
        檢查用戶是否可查看系統提示
        
        Args:
            user: Discord 用戶
            channel: 目標頻道（可選）
            
        Returns:
            是否有權限
        """
        try:
            # 查看權限相對寬鬆，只要能看到頻道就能查看系統提示
            if channel:
                return channel.permissions_for(user).view_channel
            return True
            
        except Exception as e:
            self.logger.error(f"檢查系統提示查看權限時發生錯誤: {e}")
            return False
    
    def get_user_permissions(self, user: discord.Member, 
                           guild: discord.Guild,
                           config: Optional[Dict] = None) -> Dict[str, any]:
        """
        取得用戶的詳細權限資訊
        
        Args:
            user: Discord 用戶
            guild: Discord 伺服器
            config: 配置檔案（可選）
            
        Returns:
            權限資訊字典
        """
        permissions = {
            'can_modify_server': False,
            'can_modify_channels': [],
            'allowed_channels': [],
            'permission_level': 'none',
            'is_bot_owner': False,
            'is_administrator': False
        }
        
        try:
            # 檢查機器人擁有者
            permissions['is_bot_owner'] = self._is_bot_owner(user)
            if permissions['is_bot_owner']:
                permissions.update({
                    'can_modify_server': True,
                    'permission_level': 'bot_owner',
                    'allowed_channels': self._get_all_channels(guild)
                })
                return permissions
            
            # 檢查伺服器管理員
            permissions['is_administrator'] = user.guild_permissions.administrator
            if permissions['is_administrator']:
                permissions.update({
                    'can_modify_server': True,
                    'permission_level': 'administrator',
                    'allowed_channels': self._get_all_channels(guild)
                })
                return permissions
            
            # 檢查頻道管理權限
            manageable_channels = []
            for channel in guild.text_channels:
                if channel.permissions_for(user).manage_channels:
                    manageable_channels.append(str(channel.id))
            
            if manageable_channels:
                permissions.update({
                    'can_modify_channels': manageable_channels,
                    'allowed_channels': manageable_channels,
                    'permission_level': 'channel_manager'
                })
            
            # 檢查自訂權限
            if config:
                custom_permissions = self._get_custom_permissions(user, config)
                if custom_permissions:
                    permissions.update(custom_permissions)
                    if permissions['permission_level'] == 'none':
                        permissions['permission_level'] = 'custom'
            
            return permissions
            
        except Exception as e:
            self.logger.error(f"取得用戶權限時發生錯誤: {e}")
            return permissions
    
    def validate_permission_or_raise(self, user: discord.Member,
                                   action: str,
                                   target: any = None,
                                   config: Optional[Dict] = None) -> None:
        """
        驗證權限，如果沒有權限則拋出例外
        
        Args:
            user: Discord 用戶
            action: 操作類型 ('modify_channel', 'modify_server', 'view')
            target: 目標物件（頻道或伺服器）
            config: 配置檔案（可選）
            
        Raises:
            PermissionError: 當用戶沒有足夠權限時
        """
        has_permission = False
        
        if action == 'modify_channel' and isinstance(target, discord.TextChannel):
            has_permission = self.can_modify_channel_prompt(user, target, config)
        elif action == 'modify_server' and isinstance(target, discord.Guild):
            has_permission = self.can_modify_server_prompt(user, target, config)
        elif action == 'view':
            has_permission = self.can_view_prompt(user, target)
        else:
            raise ValueError(f"未知的操作類型: {action}")
        
        if not has_permission:
            action_names = {
                'modify_channel': '修改頻道系統提示',
                'modify_server': '修改伺服器系統提示',
                'view': '查看系統提示'
            }
            raise PermissionError(
                f"您沒有權限執行 '{action_names.get(action, action)}'",
                action
            )
    
    def _is_bot_owner(self, user: discord.Member) -> bool:
        """檢查是否為機器人擁有者"""
        try:
            # 從 tokens.py 取得 bot_owner_id
            from addons.settings import TOKENS
            tokens = TOKENS()
            bot_owner_id = getattr(tokens, 'bot_owner_id', 0)
            return user.id == bot_owner_id
        except Exception as e:
            self.logger.error(f"檢查機器人擁有者權限時發生錯誤: {e}")
            return False
    
    def _has_custom_permission(self, user: discord.Member,
                              channel: discord.TextChannel,
                              config: Dict) -> bool:
        """檢查是否有自訂頻道權限"""
        try:
            system_prompts = config.get('system_prompts', {})
            permissions = system_prompts.get('permissions', {})
            
            # 檢查允許的用戶列表
            allowed_users = permissions.get('allowed_users', [])
            if str(user.id) in allowed_users:
                return True
            
            # 檢查允許的角色列表
            allowed_roles = permissions.get('allowed_roles', [])
            user_role_ids = [str(role.id) for role in user.roles]
            if any(role_id in allowed_roles for role_id in user_role_ids):
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"檢查自訂頻道權限時發生錯誤: {e}")
            return False
    
    def _has_server_level_permission(self, user: discord.Member, config: Dict) -> bool:
        """檢查是否有伺服器級別的自訂權限"""
        try:
            system_prompts = config.get('system_prompts', {})
            permissions = system_prompts.get('permissions', {})
            
            # 檢查伺服器級別管理權限
            manage_server_prompts = permissions.get('manage_server_prompts', [])
            user_role_ids = [str(role.id) for role in user.roles]
            
            return any(role_id in manage_server_prompts for role_id in user_role_ids)
            
        except Exception as e:
            self.logger.error(f"檢查伺服器級別權限時發生錯誤: {e}")
            return False
    
    def _get_all_channels(self, guild: discord.Guild) -> List[str]:
        """取得伺服器所有文字頻道 ID"""
        return [str(channel.id) for channel in guild.text_channels]
    
    def _get_custom_permissions(self, user: discord.Member, config: Dict) -> Dict:
        """取得自訂權限設定"""
        try:
            system_prompts = config.get('system_prompts', {})
            permissions = system_prompts.get('permissions', {})
            
            custom_perms = {
                'can_modify_server': False,
                'can_modify_channels': [],
                'allowed_channels': []
            }
            
            # 檢查用戶 ID
            allowed_users = permissions.get('allowed_users', [])
            user_has_custom_access = str(user.id) in allowed_users
            
            # 檢查角色權限
            allowed_roles = permissions.get('allowed_roles', [])
            manage_server_roles = permissions.get('manage_server_prompts', [])
            user_role_ids = [str(role.id) for role in user.roles]
            
            role_has_access = any(role_id in allowed_roles for role_id in user_role_ids)
            role_has_server_access = any(role_id in manage_server_roles for role_id in user_role_ids)
            
            if user_has_custom_access or role_has_access:
                # 有基本自訂權限，可管理特定頻道
                all_channels = self._get_all_channels(user.guild)
                custom_perms['allowed_channels'] = all_channels
                custom_perms['can_modify_channels'] = all_channels
            
            if role_has_server_access:
                # 有伺服器級別權限
                custom_perms['can_modify_server'] = True
            
            return custom_perms
            
        except Exception as e:
            self.logger.error(f"取得自訂權限時發生錯誤: {e}")
            return {}