"""
Discord 更新管理 Cog

提供 Discord 命令介面來管理自動更新系統。
"""

import discord
from discord.ext import commands
from discord import app_commands
from addons.logging import get_logger
log = get_logger(source=__name__, server_id="system")
logger = log
from typing import Optional
import asyncio

from .language_manager import LanguageManager
from addons.update.manager import UpdateManager
from addons.update.security import UpdatePermissionChecker
from function import func


class UpdateManagerCog(commands.Cog):
    """Discord 更新管理介面"""
    
    def __init__(self, bot):
        """
        初始化更新管理 Cog
        
        Args:
            bot: Discord Bot 實例
        """
        self.bot = bot
        self.logger = log
        self.lang_manager: Optional[LanguageManager] = None
        
        # 初始化更新管理器
        try:
            self.update_manager = UpdateManager(bot)
            self.permission_checker = UpdatePermissionChecker()
            self.logger.info("更新管理器初始化成功")
        except Exception as e:
            self.logger.error(f"更新管理器初始化失敗: {e}")
            self.update_manager = None
            self.permission_checker = UpdatePermissionChecker()
    
    async def cog_load(self):
        """Cog 載入時初始化語言管理器"""
        self.lang_manager = LanguageManager.get_instance(self.bot)
        try:
            if self.update_manager:
                # 執行重啟後檢查
                await self.update_manager.post_restart_initialization()
            self.logger.info("更新管理 Cog 載入完成")
        except Exception as e:
            self.logger.error(f"Cog 載入時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"UpdateManagerCog Cog 載入時發生錯誤")
    
    def _get_translation(self, guild_id: str, *keys, **kwargs) -> str:
        """取得翻譯文字的安全方法"""
        if not self.lang_manager:
            # 如果語言管理器不可用，返回預設值
            return "Translation not available"
        
        try:
            return self.lang_manager.translate(guild_id, *keys, **kwargs)
        except Exception as e:
            self.logger.error(f"翻譯錯誤: {e}")
            return "Translation error"
    
    @app_commands.command(name="update_check", description="檢查是否有可用更新")
    async def check_update(self, interaction: discord.Interaction):
        """檢查更新命令"""
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        
        if not self.permission_checker.check_status_permission(interaction):
            no_permission_msg = self._get_translation(guild_id, "permissions", "no_permission")
            await interaction.response.send_message(no_permission_msg, ephemeral=True)
            return
        
        if not self.update_manager:
            not_initialized_msg = self._get_translation(guild_id, "system", "not_initialized")
            await interaction.response.send_message(not_initialized_msg, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            result = await self.update_manager.check_for_updates()
            
            title = self._get_translation(guild_id, "commands", "check_update", "title")
            current_version_label = self._get_translation(guild_id, "commands", "check_update", "current_version")
            latest_version_label = self._get_translation(guild_id, "commands", "check_update", "latest_version")
            
            embed = discord.Embed(
                title=title,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name=current_version_label, 
                value=f"`{result['current_version']}`", 
                inline=True
            )
            embed.add_field(
                name=latest_version_label, 
                value=f"`{result['latest_version']}`", 
                inline=True
            )
            
            if result.get("update_available"):
                status_label = self._get_translation(guild_id, "commands", "check_update", "available", "status")
                embed.add_field(
                    name="狀態", 
                    value=status_label, 
                    inline=False
                )
                embed.color = discord.Color.green()
                
                if result.get("published_at"):
                    published_at_label = self._get_translation(guild_id, "commands", "check_update", "available", "published_at")
                    embed.add_field(
                        name=published_at_label, 
                        value=result["published_at"], 
                        inline=True
                    )
                
                # 只有擁有者才顯示更新按鈕
                if self.permission_checker.check_update_permission(interaction.user.id):
                    view = UpdateActionView(self.update_manager, guild_id, self._get_translation)
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                status_label = self._get_translation(guild_id, "commands", "check_update", "up_to_date", "status")
                embed.add_field(
                    name="狀態", 
                    value=status_label, 
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            self.logger.error(f"檢查更新時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"檢查更新時發生錯誤")
            error_title = self._get_translation(guild_id, "commands", "check_update", "error", "title")
            error_desc = self._get_translation(guild_id, "commands", "check_update", "error", "description")
            embed = discord.Embed(
                title=error_title,
                description=error_desc,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="update_now", description="立即執行更新（僅限擁有者）")
    async def update_now(self, interaction: discord.Interaction, force: bool = False):
        """
        立即更新命令
        
        Args:
            force: 是否強制更新（即使沒有新版本）
        """
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        
        if not self.permission_checker.check_update_permission(interaction.user.id):
            owner_only_msg = self._get_translation(guild_id, "permissions", "owner_only_update")
            await interaction.response.send_message(owner_only_msg, ephemeral=True)
            return
        
        if not self.update_manager:
            not_initialized_msg = self._get_translation(guild_id, "system", "not_initialized")
            await interaction.response.send_message(not_initialized_msg, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # 檢查更新狀態
            status = self.update_manager.get_status()
            if status["status"] != "idle":
                busy_title = self._get_translation(guild_id, "system", "busy")
                busy_desc = self._get_translation(guild_id, "system", "busy_description", status=status['status'])
                embed = discord.Embed(
                    title=busy_title,
                    description=busy_desc,
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # 檢查是否有可用更新
            if not force:
                check_result = await self.update_manager.check_for_updates()
                if not check_result.get("update_available"):
                    no_update_title = self._get_translation(guild_id, "commands", "update_now", "no_update_needed", "title")
                    no_update_desc = self._get_translation(guild_id, "commands", "update_now", "no_update_needed", "description")
                    embed = discord.Embed(
                        title=no_update_title,
                        description=no_update_desc,
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # 創建確認視圖
                view = UpdateConfirmView(self.update_manager, check_result, guild_id, self._get_translation)
                confirm_title = self._get_translation(guild_id, "commands", "update_now", "confirm", "title")
                confirm_desc = self._get_translation(
                    guild_id, "commands", "update_now", "confirm", "description",
                    current_version=check_result['current_version'],
                    latest_version=check_result['latest_version']
                )
                embed = discord.Embed(
                    title=confirm_title,
                    description=confirm_desc,
                    color=discord.Color.orange()
                )
                warning_label = self._get_translation(guild_id, "commands", "update_now", "confirm", "warning")
                embed.add_field(name="注意", value=warning_label, inline=False)
                
            else:
                # 強制更新確認
                view = UpdateConfirmView(self.update_manager, None, guild_id, self._get_translation, force=True)
                force_title = self._get_translation(guild_id, "commands", "update_now", "force_confirm", "title")
                force_desc = self._get_translation(guild_id, "commands", "update_now", "force_confirm", "description")
                embed = discord.Embed(
                    title=force_title,
                    description=force_desc,
                    color=discord.Color.red()
                )
                force_warning = self._get_translation(guild_id, "commands", "update_now", "force_confirm", "warning")
                embed.add_field(name="警告", value=force_warning, inline=False)
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            self.logger.error(f"準備更新時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"準備更新時發生錯誤")
            error_title = self._get_translation(guild_id, "commands", "update_now", "error", "title")
            error_desc = self._get_translation(guild_id, "commands", "update_now", "error", "description")
            embed = discord.Embed(
                title=error_title,
                description=error_desc,
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="update_status", description="查看更新系統狀態")
    async def update_status(self, interaction: discord.Interaction):
        """更新狀態查詢"""
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        
        if not self.permission_checker.check_status_permission(interaction):
            no_permission_msg = self._get_translation(guild_id, "permissions", "no_permission")
            await interaction.response.send_message(no_permission_msg, ephemeral=True)
            return
        
        if not self.update_manager:
            not_initialized_msg = self._get_translation(guild_id, "system", "not_initialized")
            await interaction.response.send_message(not_initialized_msg, ephemeral=True)
            return
        
        try:
            status = self.update_manager.get_status()
            embed = self._create_status_embed(status, guild_id)
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"獲取更新狀態時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"獲取更新狀態時發生錯誤")
            error_title = self._get_translation(guild_id, "commands", "update_status", "error", "title")
            error_desc = self._get_translation(guild_id, "commands", "update_status", "error", "description")
            embed = discord.Embed(
                title=error_title,
                description=error_desc,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="update_config", description="配置自動更新設定（僅限擁有者）")
    async def configure_update(self, interaction: discord.Interaction):
        """更新配置命令"""
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        
        if not self.permission_checker.check_update_permission(interaction.user.id):
            owner_only_msg = self._get_translation(guild_id, "permissions", "owner_only_config")
            await interaction.response.send_message(owner_only_msg, ephemeral=True)
            return
        
        if not self.update_manager:
            not_initialized_msg = self._get_translation(guild_id, "system", "not_initialized")
            await interaction.response.send_message(not_initialized_msg, ephemeral=True)
            return
        
        # 創建配置視圖
        view = UpdateConfigView(self.update_manager, guild_id, self._get_translation)
        title = self._get_translation(guild_id, "commands", "update_config", "title")
        description = self._get_translation(guild_id, "commands", "update_config", "description")
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        
        config = self.update_manager.config
        auto_update_label = self._get_translation(guild_id, "commands", "update_config", "auto_update")
        auto_update_value = self._get_translation(guild_id, "commands", "update_config", "enabled") if config["auto_update"]["enabled"] else self._get_translation(guild_id, "commands", "update_config", "disabled")
        embed.add_field(
            name=auto_update_label, 
            value=auto_update_value, 
            inline=True
        )
        
        check_interval_label = self._get_translation(guild_id, "commands", "update_config", "check_interval")
        hours_value = self._get_translation(guild_id, "commands", "update_config", "hours", hours=config['auto_update']['check_interval'] // 3600)
        embed.add_field(
            name=check_interval_label, 
            value=hours_value, 
            inline=True
        )
        
        require_conf_label = self._get_translation(guild_id, "commands", "update_config", "require_confirmation")
        require_conf_value = self._get_translation(guild_id, "commands", "update_config", "enabled") if config["auto_update"]["require_owner_confirmation"] else self._get_translation(guild_id, "commands", "update_config", "disabled")
        embed.add_field(
            name=require_conf_label, 
            value=require_conf_value, 
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    def _create_status_embed(self, status: dict, guild_id: str) -> discord.Embed:
        """創建狀態嵌入"""
        status_text = status["status"]
        
        # 取得狀態相關的翻譯
        if status_text == "idle":
            color = discord.Color.green()
            status_key = "system", "idle"
        elif status_text == "checking":
            color = discord.Color.blue()
            status_key = "system", "checking"
        elif status_text == "downloading":
            color = discord.Color.orange()
            status_key = "system", "downloading"
        elif status_text == "updating":
            color = discord.Color.yellow()
            status_key = "system", "updating"
        elif status_text == "restarting":
            color = discord.Color.purple()
            status_key = "system", "restarting"
        elif status_text == "error":
            color = discord.Color.red()
            status_key = "system", "error"
        else:
            color = discord.Color.grey()
            status_key = "system", "unknown"
        
        title = self._get_translation(guild_id, *status_key, "title")
        if status_key[1] == "downloading" or status_key[1] == "updating":
            description = self._get_translation(guild_id, *status_key, "description", progress=status['progress'])
        elif status_key[1] == "error":
            description = self._get_translation(guild_id, *status_key, "description", error=status.get('error', '未知錯誤'))
        elif status_key[1] == "unknown":
            description = self._get_translation(guild_id, *status_key, "description", status=status_text)
        else:
            description = self._get_translation(guild_id, *status_key, "description")
        
        embed = discord.Embed(
            title=title, 
            description=description, 
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        if status.get("operation"):
            operation_label = self._get_translation(guild_id, "fields", "operation")
            embed.add_field(name=operation_label, value=status["operation"], inline=False)
        
        if status.get("current_version"):
            current_version_label = self._get_translation(guild_id, "commands", "check_update", "current_version")
            embed.add_field(name=current_version_label, value=f"`{status['current_version']}`", inline=True)
        
        if status.get("last_check"):
            last_check_label = self._get_translation(guild_id, "fields", "last_check")
            embed.add_field(name=last_check_label, value=f"<t:{int(discord.utils.parse_time(status['last_check']).timestamp())}:R>", inline=True)
        
        auto_update_label = self._get_translation(guild_id, "fields", "auto_update")
        auto_update_value = self._get_translation(guild_id, "commands", "update_config", "enabled") if status.get("auto_update_enabled") else self._get_translation(guild_id, "commands", "update_config", "disabled")
        embed.add_field(
            name=auto_update_label, 
            value=auto_update_value, 
            inline=True
        )
        
        return embed


class UpdateActionView(discord.ui.View):
    """更新操作視圖"""
    
    def __init__(self, update_manager, guild_id: str, get_translation_func):
        super().__init__(timeout=300)
        self.update_manager = update_manager
        self.guild_id = guild_id
        self.get_translation = get_translation_func
    
    @discord.ui.button(label="立即更新", style=discord.ButtonStyle.success, emoji="🚀")
    async def update_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        """立即更新按鈕"""
        # 創建確認視圖
        view = UpdateConfirmView(self.update_manager, None, self.guild_id, self.get_translation)
        confirm_title = self.get_translation(self.guild_id, "views", "update_action", "confirm", "title")
        confirm_desc = self.get_translation(self.guild_id, "views", "update_action", "confirm", "description")
        embed = discord.Embed(
            title=confirm_title,
            description=confirm_desc,
            color=discord.Color.orange()
        )
        warning_label = self.get_translation(self.guild_id, "views", "update_action", "confirm", "warning")
        embed.add_field(name="注意", value=warning_label, inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="稍後提醒", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def remind_later(self, interaction: discord.Interaction, button: discord.ui.Button):
        """稍後提醒按鈕"""
        reminded_title = self.get_translation(self.guild_id, "views", "update_action", "reminded", "title")
        reminded_desc = self.get_translation(self.guild_id, "views", "update_action", "reminded", "description")
        embed = discord.Embed(
            title=reminded_title,
            description=reminded_desc,
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class UpdateConfirmView(discord.ui.View):
    """更新確認視圖"""
    
    def __init__(self, update_manager, version_info=None, guild_id: str = None, get_translation_func=None, force=False):
        super().__init__(timeout=300)
        self.update_manager = update_manager
        self.version_info = version_info
        self.guild_id = guild_id
        self.get_translation = get_translation_func
        self.force = force
    
    @discord.ui.button(label="確認更新", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確認更新按鈕"""
        await interaction.response.defer()
        
        starting_title = self.get_translation(self.guild_id, "views", "update_confirm", "starting", "title")
        starting_desc = self.get_translation(self.guild_id, "views", "update_confirm", "starting", "description")
        embed = discord.Embed(
            title=starting_title,
            description=starting_desc,
            color=discord.Color.blue()
        )
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
        
        # 在背景執行更新
        asyncio.create_task(self._execute_update(interaction))
    
    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """取消更新按鈕"""
        cancelled_title = self.get_translation(self.guild_id, "views", "update_confirm", "cancelled", "title")
        cancelled_desc = self.get_translation(self.guild_id, "views", "update_confirm", "cancelled", "description")
        embed = discord.Embed(
            title=cancelled_title,
            description=cancelled_desc,
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def _execute_update(self, interaction):
        """執行更新"""
        try:
            result = await self.update_manager.execute_update(interaction, self.force)
            
            if not result.get("success"):
                # 更新失敗，發送錯誤訊息
                failed_title = self.get_translation(self.guild_id, "views", "update_confirm", "failed", "title")
                failed_desc = self.get_translation(self.guild_id, "views", "update_confirm", "failed", "description", error=result.get('error', '未知錯誤'))
                embed = discord.Embed(
                    title=failed_title,
                    description=failed_desc,
                    color=discord.Color.red()
                )
                
                if result.get("backup_id"):
                    backup_name = self.get_translation(self.guild_id, "views", "update_confirm", "backup", "name")
                    backup_value = self.get_translation(self.guild_id, "views", "update_confirm", "backup", "value", backup_id=result['backup_id'])
                    embed.add_field(
                        name=backup_name, 
                        value=backup_value, 
                        inline=False
                    )
                
                await interaction.edit_original_response(embed=embed, view=None)
                
        except Exception as e:
            # 處理未預期的錯誤
            await func.report_error(self.update_manager.bot, e, f"執行更新時發生嚴重錯誤")
            error_title = self.get_translation(self.guild_id, "views", "update_confirm", "failed", "title")
            error_desc = self.get_translation(self.guild_id, "views", "update_confirm", "failed", "description", error="執行更新時發生嚴重錯誤，已回報給開發者。")
            embed = discord.Embed(
                title=error_title,
                description=error_desc,
                color=discord.Color.red()
            )
            
            try:
                await interaction.edit_original_response(embed=embed, view=None)
            except:
                # 如果無法編輯訊息（例如 Bot 已重啟），則忽略
                pass


class UpdateConfigView(discord.ui.View):
    """更新配置視圖"""
    
    def __init__(self, update_manager, guild_id: str, get_translation_func):
        super().__init__(timeout=300)
        self.update_manager = update_manager
        self.guild_id = guild_id
        self.get_translation = get_translation_func
    
    @discord.ui.button(label="開關自動更新", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_auto_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換自動更新開關"""
        # 這裡實現配置切換邏輯
        in_dev_msg = self.get_translation(self.guild_id, "views", "update_config", "in_development")
        await interaction.response.send_message(in_dev_msg, ephemeral=True)
    
    @discord.ui.button(label="設定檢查間隔", style=discord.ButtonStyle.secondary, emoji="⏱️")
    async def set_check_interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        """設定檢查間隔"""
        in_dev_msg = self.get_translation(self.guild_id, "views", "update_config", "in_development")
        await interaction.response.send_message(in_dev_msg, ephemeral=True)


async def setup(bot):
    """設定 Cog"""
    await bot.add_cog(UpdateManagerCog(bot))