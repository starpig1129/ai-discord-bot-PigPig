"""
頻道系統提示管理模組的主要 Cog

這個檔案作為系統提示管理模組的入口點，整合所有功能組件。
"""

import discord
from discord.ext import commands
from typing import Optional, TYPE_CHECKING
from addons.logging import get_logger

from .system_prompt.manager import SystemPromptManager
from .system_prompt.commands import SystemPromptCommands
from .system_prompt.permissions import PermissionValidator
from function import func

# 避免循環導入的類型檢查
if TYPE_CHECKING:
    from .language_manager import LanguageManager
else:
    LanguageManager = None


class SystemPromptManagerCog(commands.Cog):
    """系統提示管理主要 Cog 類別"""
    
    def __init__(self, bot: commands.Bot):
        """
        初始化系統提示管理 Cog
        
        Args:
            bot: Discord 機器人實例
        """
        self.bot = bot
        self.logger = get_logger(source=__name__, server_id="system")
        
        # 初始化核心組件
        self.manager = SystemPromptManager(bot)
        self.permission_validator = PermissionValidator(bot)
        
        # 初始化命令組件
        self.commands_cog = SystemPromptCommands(bot)
        
        # 語言管理器將在 cog_load 中初始化
        self.language_manager = None
        
        self.logger.info("系統提示管理模組已初始化")
    
    def _get_language_manager(self):
        """安全地取得語言管理器實例"""
        if self.language_manager is None:
            self.language_manager = self.bot.get_cog('LanguageManager')
        return self.language_manager
    
    def _translate(self, guild_id: str, *keys):
        """安全的翻譯方法，使用 getattr 避免類型檢查問題"""
        lang_manager = self._get_language_manager()
        if not lang_manager:
            # 回退到預設字串
            fallback_map = {
                ("commands", "system_prompt", "manager", "status", "title"): "🤖 System Prompt Module Status",
                ("commands", "system_prompt", "manager", "status", "cache_status"): "Cache Status",
                ("commands", "system_prompt", "manager", "status", "cache_items"): "Cache Items",
                ("commands", "system_prompt", "manager", "status", "modules_count"): "Modules Count",
                ("commands", "system_prompt", "manager", "status", "components_status"): "Components Status",
                ("commands", "system_prompt", "manager", "status", "system_prompt_manager"): "SystemPromptManager",
                ("commands", "system_prompt", "manager", "status", "permission_validator"): "PermissionValidator",
                ("commands", "system_prompt", "manager", "status", "system_prompt_commands"): "SystemPromptCommands",
                ("commands", "system_prompt", "manager", "status", "error_message"): "Error occurred while viewing status",
                ("commands", "system_prompt", "manager", "cache", "success_message_all"): "Successfully cleared all system prompt cache",
                ("commands", "system_prompt", "manager", "cache", "success_message_guild"): "Successfully cleared system prompt cache for server {guild_id}",
                ("commands", "system_prompt", "manager", "cache", "error_message"): "Error occurred while clearing cache"
            }
            key_tuple = tuple(keys)
            return fallback_map.get(key_tuple, f"[Missing translation: {'.'.join(keys)}]")
        
        # 使用 getattr 來調用 translate 方法
        translate_method = getattr(lang_manager, 'translate', None)
        if translate_method:
            return translate_method(guild_id, *keys)
        else:
            return f"[Translation method not available]"
    
    async def cog_load(self):
        """Cog 載入時的初始化"""
        try:
            # 載入命令 Cog
            await self.bot.add_cog(self.commands_cog)
            self.logger.info("System prompt command module loaded")
            
        except Exception as e:
            await func.report_error(e, "loading system prompt commands cog")
            raise
    
    async def cog_unload(self):
        """Cog 卸載時的清理"""
        try:
            # 卸載命令 Cog
            await self.bot.remove_cog(self.commands_cog.__class__.__name__)
            self.logger.info("System prompt command module unloaded")
            
        except Exception as e:
            await func.report_error(e, "unloading system prompt commands cog")

    def get_system_prompt_manager(self) -> SystemPromptManager:
        """
        取得系統提示管理器實例
        
        這個方法供 gpt/sendmessage.py 調用，以整合系統提示功能。
        
        Returns:
            SystemPromptManager 實例
        """
        return self.manager
    
    def get_permission_validator(self) -> PermissionValidator:
        """
        取得權限驗證器實例
        
        Returns:
            PermissionValidator 實例
        """
        return self.permission_validator
    
    async def get_effective_system_prompt(self, 
                                        channel_id: str, 
                                        guild_id: str,
                                        message: Optional[discord.Message] = None) -> str:
        """
        取得有效的系統提示（供外部模組調用的便利方法）
        
        Args:
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            message: Discord 訊息物件（可選）
            
        Returns:
            完整的系統提示字串
        """
        try:
            prompt_data = self.manager.get_effective_prompt(channel_id, guild_id, message)
            return prompt_data.get('prompt', '')
        except Exception as e:
            await func.report_error(e, "getting effective system prompt")
            return ''
    
    async def validate_user_permission(self, 
                                     user: discord.Member,
                                     action: str,
                                     target: any = None) -> bool:
        """
        驗證用戶權限（供外部模組調用的便利方法）
        
        Args:
            user: Discord 用戶
            action: 操作類型
            target: 目標物件
            
        Returns:
            是否有權限
        """
        try:
            if action == 'modify_channel' and isinstance(target, discord.TextChannel):
                return self.permission_validator.can_modify_channel_prompt(user, target)
            elif action == 'modify_server' and isinstance(target, discord.Guild):
                return self.permission_validator.can_modify_server_prompt(user, target)
            elif action == 'view':
                return self.permission_validator.can_view_prompt(user, target)
            else:
                return False
        except Exception as e:
            await func.report_error(e, "validating user permission")
            return False
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """當機器人加入新伺服器時的處理"""
        try:
            # 為新伺服器初始化預設配置
            config = self.manager._get_default_config()
            self.manager._save_guild_config(str(guild.id), config)
            
            self.logger.info(f"Initialized system prompt configuration for new server {guild.name} ({guild.id})")
            
        except Exception as e:
            await func.report_error(e, "initializing config for new guild")
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """當機器人離開伺服器時的處理"""
        try:
            # 清除該伺服器的快取
            self.manager.clear_cache(str(guild.id))
            
            self.logger.info(f"Cleared system prompt cache for server {guild.name} ({guild.id})")
            
        except Exception as e:
            await func.report_error(e, "clearing server cache on guild remove")
    
    @commands.command(name="system_prompt_status", hidden=True)
    @commands.is_owner()
    async def system_prompt_status(self, ctx):
        """View system prompt module status (bot owner only)"""
        try:
            # Get translated strings using safe method
            title = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "title")
            cache_status = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "cache_status")
            cache_items = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "cache_items")
            modules_count = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "modules_count")
            components_status = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "components_status")
            system_prompt_manager = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "system_prompt_manager")
            permission_validator = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "permission_validator")
            system_prompt_commands = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "system_prompt_commands")
            error_message = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "error_message")
            
            embed = discord.Embed(
                title=title,
                color=discord.Color.blue()
            )
            
            # Cache statistics
            cache_size = len(self.manager.cache.cache)
            embed.add_field(
                name=cache_status,
                value=f"{cache_items}: {cache_size}",
                inline=True
            )
            
            # Module status
            available_modules = self.manager.get_available_modules()
            embed.add_field(
                name=modules_count,
                value=f"{modules_count}: {len(available_modules)}",
                inline=True
            )
            
            # Component status
            components_status_text = []
            components_status_text.append(f"✅ {system_prompt_manager}")
            components_status_text.append(f"✅ {permission_validator}")
            components_status_text.append(f"✅ {system_prompt_commands}")
            
            embed.add_field(
                name=components_status,
                value="\n".join(components_status_text),
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await func.report_error(e, "getting system prompt status")
            error_msg = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "status", "error_message")
            await ctx.send(f"❌ {error_msg}: {str(e)}")
    
    @commands.command(name="system_prompt_clear_cache", hidden=True)
    @commands.is_owner()
    async def clear_system_prompt_cache(self, ctx, guild_id: Optional[str] = None):
        """Clear system prompt cache (bot owner only)"""
        try:
            # Get translated strings using safe method
            success_message_all = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "cache", "success_message_all")
            success_message_guild = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "cache", "success_message_guild")
            error_message = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "cache", "error_message")
            
            if guild_id:
                self.manager.clear_cache(guild_id)
                await ctx.send(f"✅ {success_message_guild.format(guild_id=guild_id)}")
            else:
                self.manager.clear_cache()
                await ctx.send(f"✅ {success_message_all}")
            
        except Exception as e:
            await func.report_error(e, "clearing system prompt cache")
            error_msg = self._translate(str(ctx.guild.id), "commands", "system_prompt", "manager", "cache", "error_message")
            await ctx.send(f"❌ {error_msg}: {str(e)}")


async def setup(bot):
    """設定函式，用於載入 Cog"""
    await bot.add_cog(SystemPromptManagerCog(bot))