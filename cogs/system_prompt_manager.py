"""
System Prompt Management Module Main Cog

This file serves as the entry point for the system prompt management module,
integrating all functional components.
"""

import discord
from discord.ext import commands
from typing import Optional, Any

from .system_prompt.manager import SystemPromptManager
from .system_prompt.commands import SystemPromptCommands
from .system_prompt.permissions import PermissionValidator
from utils.logger import LoggerMixin
from function import func


class SystemPromptManagerCog(commands.Cog, LoggerMixin):
    """System prompt management main Cog class"""
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize system prompt management Cog
        
        Args:
            bot: Discord bot instance
        """
        LoggerMixin.__init__(self, "SystemPromptManagerCog")
        self.bot = bot
        
        # Initialize core components
        self.manager = SystemPromptManager(bot)
        self.permission_validator = PermissionValidator(bot)
        
        # Initialize command components
        self.commands_cog = SystemPromptCommands(bot)
        
        self.logger.info("System prompt management module initialized")
    
    async def cog_load(self):
        """Cog 載入時的初始化"""
        try:
            # 載入命令 Cog
            await self.bot.add_cog(self.commands_cog)
            self.logger.info("System prompt commands module loaded")
            
        except Exception as e:
            await func.report_error(e, "loading system prompt commands cog")
            raise
    
    async def cog_unload(self):
        """Cog 卸載時的清理"""
        try:
            # 卸載命令 Cog
            await self.bot.remove_cog(self.commands_cog.__class__.__name__)
            self.logger.info("系統提示命令模組已卸載")
            
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
                                     target: Optional[Any] = None) -> bool:
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
            
            self.logger.info(f"為新伺服器 {guild.name} ({guild.id}) 初始化系統提示配置")
            
        except Exception as e:
            await func.report_error(e, "initializing config for new guild")
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """當機器人離開伺服器時的處理"""
        try:
            # 清除該伺服器的快取
            self.manager.clear_cache(str(guild.id))
            
            self.logger.info(f"已清除伺服器 {guild.name} ({guild.id}) 的系統提示快取")
            
        except Exception as e:
            await func.report_error(e, "clearing server cache on guild remove")
    
    @commands.command(name="system_prompt_status", hidden=True)
    @commands.is_owner()
    async def system_prompt_status(self, ctx):
        """查看系統提示模組狀態（機器人擁有者專用）"""
        try:
            embed = discord.Embed(
                title="🤖 系統提示模組狀態",
                color=discord.Color.blue()
            )
            
            # 快取統計
            cache_size = len(self.manager.cache.cache)
            embed.add_field(
                name="快取狀態",
                value=f"快取項目數: {cache_size}",
                inline=True
            )
            
            # 模組狀態
            available_modules = self.manager.get_available_modules()
            embed.add_field(
                name="可用模組",
                value=f"模組數量: {len(available_modules)}",
                inline=True
            )
            
            # 組件狀態
            components_status = []
            components_status.append("✅ SystemPromptManager")
            components_status.append("✅ PermissionValidator")
            components_status.append("✅ SystemPromptCommands")
            
            embed.add_field(
                name="組件狀態",
                value="\n".join(components_status),
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await func.report_error(e, "getting system prompt status")
            await ctx.send(f"❌ 查看狀態時發生錯誤: {str(e)}")
    
    @commands.command(name="system_prompt_clear_cache", hidden=True)
    @commands.is_owner()
    async def clear_system_prompt_cache(self, ctx, guild_id: Optional[str] = None):
        """清除系統提示快取（機器人擁有者專用）"""
        try:
            if guild_id:
                self.manager.clear_cache(guild_id)
                await ctx.send(f"✅ 已清除伺服器 {guild_id} 的系統提示快取")
            else:
                self.manager.clear_cache()
                await ctx.send("✅ 已清除所有系統提示快取")
            
        except Exception as e:
            await func.report_error(e, "clearing system prompt cache")
            await ctx.send(f"❌ 清除快取時發生錯誤: {str(e)}")


async def setup(bot):
    """設定函式，用於載入 Cog"""
    await bot.add_cog(SystemPromptManagerCog(bot))