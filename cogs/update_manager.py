"""
Discord 更新管理 Cog

提供 Discord 命令介面來管理自動更新系統。
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
import asyncio

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
        self.logger = logging.getLogger(__name__)
        
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
        """Cog 載入時的初始化"""
        try:
            if self.update_manager:
                # 執行重啟後檢查
                await self.update_manager.post_restart_initialization()
            self.logger.info("更新管理 Cog 載入完成")
        except Exception as e:
            self.logger.error(f"Cog 載入時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"UpdateManagerCog Cog 載入時發生錯誤")
    
    @app_commands.command(name="update_check", description="檢查是否有可用更新")
    async def check_update(self, interaction: discord.Interaction):
        """檢查更新命令"""
        if not self.permission_checker.check_status_permission(interaction):
            await interaction.response.send_message("❌ 您沒有權限使用此命令", ephemeral=True)
            return
        
        if not self.update_manager:
            await interaction.response.send_message("❌ 更新系統未正確初始化", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            result = await self.update_manager.check_for_updates()
            
            embed = discord.Embed(
                title="🔍 版本檢查結果",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="當前版本", 
                value=f"`{result['current_version']}`", 
                inline=True
            )
            embed.add_field(
                name="最新版本", 
                value=f"`{result['latest_version']}`", 
                inline=True
            )
            
            if result.get("update_available"):
                embed.add_field(
                    name="狀態", 
                    value="🆕 有新版本可用", 
                    inline=False
                )
                embed.color = discord.Color.green()
                
                if result.get("published_at"):
                    embed.add_field(
                        name="發布時間", 
                        value=result["published_at"], 
                        inline=True
                    )
                
                # 只有擁有者才顯示更新按鈕
                if self.permission_checker.check_update_permission(interaction.user.id):
                    view = UpdateActionView(self.update_manager)
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                embed.add_field(
                    name="狀態", 
                    value="✅ 已是最新版本", 
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            self.logger.error(f"檢查更新時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"檢查更新時發生錯誤")
            embed = discord.Embed(
                title="❌ 檢查失敗",
                description=f"檢查更新時發生錯誤，已回報給開發者。",
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
        if not self.permission_checker.check_update_permission(interaction.user.id):
            await interaction.response.send_message("❌ 僅限 Bot 擁有者可以執行更新", ephemeral=True)
            return
        
        if not self.update_manager:
            await interaction.response.send_message("❌ 更新系統未正確初始化", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # 檢查更新狀態
            status = self.update_manager.get_status()
            if status["status"] != "idle":
                embed = discord.Embed(
                    title="⚠️ 更新進行中",
                    description=f"更新系統正忙碌中，當前狀態：{status['status']}",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # 檢查是否有可用更新
            if not force:
                check_result = await self.update_manager.check_for_updates()
                if not check_result.get("update_available"):
                    embed = discord.Embed(
                        title="ℹ️ 無需更新",
                        description="已是最新版本，無需更新。如要強制更新，請使用 `force: True` 參數。",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # 創建確認視圖
                view = UpdateConfirmView(self.update_manager, check_result)
                embed = discord.Embed(
                    title="⚠️ 更新確認",
                    description=f"確定要從 `{check_result['current_version']}` 更新到 `{check_result['latest_version']}` 嗎？",
                    color=discord.Color.orange()
                )
                embed.add_field(name="注意", value="更新過程中 Bot 將會重啟", inline=False)
                
            else:
                # 強制更新確認
                view = UpdateConfirmView(self.update_manager, None, force=True)
                embed = discord.Embed(
                    title="⚠️ 強制更新確認",
                    description="確定要執行強制更新嗎？",
                    color=discord.Color.red()
                )
                embed.add_field(name="警告", value="強制更新可能會覆蓋當前版本", inline=False)
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            self.logger.error(f"準備更新時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"準備更新時發生錯誤")
            embed = discord.Embed(
                title="❌ 更新失敗",
                description=f"準備更新時發生錯誤，已回報給開發者。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="update_status", description="查看更新系統狀態")
    async def update_status(self, interaction: discord.Interaction):
        """更新狀態查詢"""
        if not self.permission_checker.check_status_permission(interaction):
            await interaction.response.send_message("❌ 您沒有權限使用此命令", ephemeral=True)
            return
        
        if not self.update_manager:
            await interaction.response.send_message("❌ 更新系統未正確初始化", ephemeral=True)
            return
        
        try:
            status = self.update_manager.get_status()
            embed = self._create_status_embed(status)
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"獲取更新狀態時發生錯誤: {e}")
            await func.report_error(self.bot, e, f"獲取更新狀態時發生錯誤")
            embed = discord.Embed(
                title="❌ 狀態查詢失敗",
                description=f"獲取狀態時發生錯誤，已回報給開發者。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="update_config", description="配置自動更新設定（僅限擁有者）")
    async def configure_update(self, interaction: discord.Interaction):
        """更新配置命令"""
        if not self.permission_checker.check_update_permission(interaction.user.id):
            await interaction.response.send_message("❌ 僅限 Bot 擁有者可以配置更新設定", ephemeral=True)
            return
        
        if not self.update_manager:
            await interaction.response.send_message("❌ 更新系統未正確初始化", ephemeral=True)
            return
        
        # 創建配置視圖
        view = UpdateConfigView(self.update_manager)
        embed = discord.Embed(
            title="⚙️ 更新系統配置",
            description="請選擇要配置的選項：",
            color=discord.Color.blue()
        )
        
        config = self.update_manager.config
        embed.add_field(
            name="自動更新", 
            value="✅ 啟用" if config["auto_update"]["enabled"] else "❌ 停用", 
            inline=True
        )
        embed.add_field(
            name="檢查間隔", 
            value=f"{config['auto_update']['check_interval'] // 3600}小時", 
            inline=True
        )
        embed.add_field(
            name="需要確認", 
            value="✅ 是" if config["auto_update"]["require_owner_confirmation"] else "❌ 否", 
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    def _create_status_embed(self, status: dict) -> discord.Embed:
        """創建狀態嵌入"""
        status_text = status["status"]
        
        if status_text == "idle":
            color = discord.Color.green()
            title = "💤 更新系統閒置"
            description = "自動更新系統正常運行"
        elif status_text == "checking":
            color = discord.Color.blue()
            title = "🔍 正在檢查更新"
            description = "正在查詢 GitHub 最新版本..."
        elif status_text == "downloading":
            color = discord.Color.orange()
            title = "⬇️ 正在下載更新"
            description = f"下載進度：{status['progress']}%"
        elif status_text == "updating":
            color = discord.Color.yellow()
            title = "🔄 正在更新"
            description = f"更新進度：{status['progress']}%"
        elif status_text == "restarting":
            color = discord.Color.purple()
            title = "🔄 正在重啟"
            description = "Bot 正在重新啟動..."
        elif status_text == "error":
            color = discord.Color.red()
            title = "❌ 系統錯誤"
            description = f"錯誤：{status.get('error', '未知錯誤')}"
        else:
            color = discord.Color.grey()
            title = "❓ 未知狀態"
            description = f"狀態：{status_text}"
        
        embed = discord.Embed(
            title=title, 
            description=description, 
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        if status.get("operation"):
            embed.add_field(name="當前操作", value=status["operation"], inline=False)
        
        if status.get("current_version"):
            embed.add_field(name="當前版本", value=f"`{status['current_version']}`", inline=True)
        
        if status.get("last_check"):
            embed.add_field(name="上次檢查", value=f"<t:{int(discord.utils.parse_time(status['last_check']).timestamp())}:R>", inline=True)
        
        embed.add_field(
            name="自動更新", 
            value="✅ 啟用" if status.get("auto_update_enabled") else "❌ 停用", 
            inline=True
        )
        
        return embed


class UpdateActionView(discord.ui.View):
    """更新操作視圖"""
    
    def __init__(self, update_manager):
        super().__init__(timeout=300)
        self.update_manager = update_manager
    
    @discord.ui.button(label="立即更新", style=discord.ButtonStyle.success, emoji="🚀")
    async def update_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        """立即更新按鈕"""
        # 創建確認視圖
        view = UpdateConfirmView(self.update_manager, None)
        embed = discord.Embed(
            title="⚠️ 更新確認",
            description="確定要立即執行更新嗎？",
            color=discord.Color.orange()
        )
        embed.add_field(name="注意", value="更新過程中 Bot 將會重啟", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="稍後提醒", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def remind_later(self, interaction: discord.Interaction, button: discord.ui.Button):
        """稍後提醒按鈕"""
        embed = discord.Embed(
            title="⏰ 已設定稍後提醒",
            description="將在下次檢查更新時再次提醒您。",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)


class UpdateConfirmView(discord.ui.View):
    """更新確認視圖"""
    
    def __init__(self, update_manager, version_info=None, force=False):
        super().__init__(timeout=300)
        self.update_manager = update_manager
        self.version_info = version_info
        self.force = force
    
    @discord.ui.button(label="確認更新", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """確認更新按鈕"""
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="🔄 開始更新",
            description="更新程序已開始，請查看 DM 獲取詳細進度。\n\n⚠️ **請不要關閉 Bot，更新完成後將自動重啟。**",
            color=discord.Color.blue()
        )
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
        
        # 在背景執行更新
        asyncio.create_task(self._execute_update(interaction))
    
    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """取消更新按鈕"""
        embed = discord.Embed(
            title="❌ 更新已取消",
            description="更新操作已被取消。",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    async def _execute_update(self, interaction):
        """執行更新"""
        try:
            result = await self.update_manager.execute_update(interaction, self.force)
            
            if not result.get("success"):
                # 更新失敗，發送錯誤訊息
                embed = discord.Embed(
                    title="❌ 更新失敗",
                    description=f"更新過程中發生錯誤：{result.get('error', '未知錯誤')}",
                    color=discord.Color.red()
                )
                
                if result.get("backup_id"):
                    embed.add_field(
                        name="備份資訊", 
                        value=f"系統已回滾到備份：`{result['backup_id']}`", 
                        inline=False
                    )
                
                await interaction.edit_original_response(embed=embed, view=None)
                
        except Exception as e:
            # 處理未預期的錯誤
            await func.report_error(self.update_manager.bot, e, f"執行更新時發生嚴重錯誤")
            embed = discord.Embed(
                title="❌ 更新錯誤",
                description=f"執行更新時發生嚴重錯誤，已回報給開發者。",
                color=discord.Color.red()
            )
            
            try:
                await interaction.edit_original_response(embed=embed, view=None)
            except:
                # 如果無法編輯訊息（例如 Bot 已重啟），則忽略
                pass


class UpdateConfigView(discord.ui.View):
    """更新配置視圖"""
    
    def __init__(self, update_manager):
        super().__init__(timeout=300)
        self.update_manager = update_manager
    
    @discord.ui.button(label="開關自動更新", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_auto_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """切換自動更新開關"""
        # 這裡實現配置切換邏輯
        await interaction.response.send_message("⚠️ 配置功能開發中...", ephemeral=True)
    
    @discord.ui.button(label="設定檢查間隔", style=discord.ButtonStyle.secondary, emoji="⏱️")
    async def set_check_interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        """設定檢查間隔"""
        await interaction.response.send_message("⚠️ 配置功能開發中...", ephemeral=True)


async def setup(bot):
    """設定 Cog"""
    await bot.add_cog(UpdateManagerCog(bot))