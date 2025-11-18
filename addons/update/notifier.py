"""
Discord 通知系統模組

負責發送更新相關的通知給 Bot 擁有者和管理員。
"""

import os
import discord
from addons.logging import get_logger
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from function import func
# module-level logger
log = get_logger(server_id="Bot", source=__name__)


class DiscordNotifier:
    """Discord 通知系統"""
    
    def __init__(self, bot):
        """
        初始化通知系統
        
        Args:
            bot: Discord Bot 實例
        """
        self.bot = bot
        # use system-scoped logger for notifier
        self.logger = get_logger(server_id="Bot", source=__name__)
        load_dotenv()
        self.owner_id = int(os.getenv("BOT_OWNER_ID", 0))
        
        if self.owner_id == 0:
            self.logger.error("BOT_OWNER_ID 未設定或為 0，無法發送通知")
        else:
            self.logger.info(f"DiscordNotifier 初始化完成，Bot 擁有者 ID: {self.owner_id}")
    
    async def _get_bot_owner_safely(self) -> Optional[discord.User]:
        """
        安全地獲取 Bot 擁有者
        
        Returns:
            Bot 擁有者物件，如果獲取失敗則返回 None
        """
        if self.owner_id == 0:
            self.logger.error("BOT_OWNER_ID 未設定或為 0")
            return None
        
        try:
            owner = await self.bot.fetch_user(self.owner_id)
            if owner:
                self.logger.debug(f"成功獲取 Bot 擁有者: {owner.name}")
            return owner
        except Exception as e:
            self.logger.error(f"獲取 Bot 擁有者失敗: {e}")
            await func.report_error(e, "addons/update/notifier.py/_get_bot_owner_safely")
            return None
    
    async def notify_update_available(self, version_info: Dict[str, Any]) -> bool:
        """
        通知有新版本可用
        
        Args:
            version_info: 版本資訊字典
            
        Returns:
            通知是否發送成功
        """
        owner = await self._get_bot_owner_safely()
        if not owner:
            return False
        try:
            embed = discord.Embed(
                title="🆕 新版本可用",
                description="PigPig Bot 有新版本可用！",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="當前版本", 
                value=f"`{version_info['current_version']}`", 
                inline=True
            )
            embed.add_field(
                name="新版本", 
                value=f"`{version_info['latest_version']}`", 
                inline=True
            )
            
            if version_info.get("published_at"):
                try:
                    # 解析 ISO 時間格式
                    pub_time = datetime.fromisoformat(
                        version_info["published_at"].replace('Z', '+00:00')
                    )
                    embed.add_field(
                        name="發布時間", 
                        value=f"<t:{int(pub_time.timestamp())}:R>", 
                        inline=False
                    )
                except Exception as e:
                    await func.report_error(e, "addons/update/notifier.py/notify_update_available/parse_time")
                    embed.add_field(
                        name="發布時間", 
                        value=version_info["published_at"], 
                        inline=False
                    )
            
            if version_info.get("release_notes"):
                # 限制更新說明長度
                notes = version_info["release_notes"][:1000]
                if len(version_info["release_notes"]) > 1000:
                    notes += "..."
                embed.add_field(name="更新說明", value=notes, inline=False)
            
            # 添加更新按鈕
            view = QuickUpdateView()
            
            await owner.send(embed=embed, view=view)
            self.logger.info("新版本通知已發送")
            return True
            
        except discord.Forbidden:
            self.logger.error("無法發送 DM 給 Bot 擁有者（可能被封鎖）")
            return False
        except Exception as e:
            self.logger.error(f"發送新版本通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/notify_update_available")
            return False
    
    async def notify_update_progress(self, stage: str, progress: int, details: str = "") -> bool:
        """
        通知更新進度
        
        Args:
            stage: 當前階段
            progress: 進度百分比
            details: 詳細資訊
            
        Returns:
            通知是否發送成功
        """
        owner = await self._get_bot_owner_safely()
        if not owner:
            return False
        
        try:
            embed = discord.Embed(
                title="🔄 更新進行中",
                description=f"**當前階段**: {stage}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # 創建進度條
            progress_bar = self._create_progress_bar(progress)
            embed.add_field(
                name="進度", 
                value=f"{progress_bar} {progress}%", 
                inline=False
            )
            
            if details:
                embed.add_field(name="詳細資訊", value=details, inline=False)
            
            await owner.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"發送更新進度通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/notify_update_progress")
            return False
    
    async def notify_update_complete(self, result: Dict[str, Any]) -> bool:
        """
        通知更新完成
        
        Args:
            result: 更新結果字典
            
        Returns:
            通知是否發送成功
        """
        owner = await self._get_bot_owner_safely()
        if not owner:
            return False
        
        try:
            if result.get("success", False):
                embed = discord.Embed(
                    title="✅ 更新完成",
                    description="PigPig Bot 已成功更新！",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                
                if result.get("old_version") and result.get("new_version"):
                    embed.add_field(
                        name="版本變更", 
                        value=f"`{result['old_version']}` → `{result['new_version']}`", 
                        inline=False
                    )
                
                if result.get("duration"):
                    embed.add_field(
                        name="更新時間", 
                        value=f"{result['duration']:.1f}秒", 
                        inline=True
                    )
                
                if result.get("restart_required", False):
                    embed.add_field(
                        name="狀態", 
                        value="🔄 Bot 正在重啟中...", 
                        inline=True
                    )
                else:
                    embed.add_field(
                        name="狀態", 
                        value="✅ 更新完成，無需重啟", 
                        inline=True
                    )
                    
            else:
                embed = discord.Embed(
                    title="❌ 更新失敗",
                    description="更新過程中發生錯誤",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                if result.get("error"):
                    error_msg = str(result["error"])[:1000]
                    embed.add_field(name="錯誤訊息", value=f"```{error_msg}```", inline=False)
                
                if result.get("backup_id"):
                    embed.add_field(
                        name="備份資訊", 
                        value=f"可使用備份 `{result['backup_id']}` 進行回滾", 
                        inline=False
                    )
            
            await owner.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"發送更新完成通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/notify_update_complete")
            return False
    
    async def notify_update_error(self, error: Exception, context: str = "") -> bool:
        """
        通知更新錯誤
        
        Args:
            error: 錯誤物件
            context: 錯誤上下文
            
        Returns:
            通知是否發送成功
        """
        owner = await self._get_bot_owner_safely()
        if not owner:
            return False
        
        try:
            embed = discord.Embed(
                title="❌ 更新系統錯誤",
                description="自動更新系統發生錯誤",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="錯誤類型", 
                value=f"`{type(error).__name__}`", 
                inline=True
            )
            
            error_msg = str(error)[:1000]
            embed.add_field(
                name="錯誤訊息", 
                value=f"```{error_msg}```", 
                inline=False
            )
            
            if context:
                embed.add_field(
                    name="錯誤上下文", 
                    value=context, 
                    inline=False
                )
            
            await owner.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"發送錯誤通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/notify_update_error")
            return False
    
    async def notify_restart_success(self, restart_info: Dict[str, Any]) -> bool:
        """
        通知重啟成功
        
        Args:
            restart_info: 重啟資訊
            
        Returns:
            通知是否發送成功
        """
        owner = await self._get_bot_owner_safely()
        if not owner:
            return False
        
        try:
            embed = discord.Embed(
                title="🚀 重啟完成",
                description="PigPig Bot 已成功重啟！",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            if restart_info.get("restart_time"):
                try:
                    restart_time = datetime.fromisoformat(restart_info["restart_time"])
                    elapsed = (datetime.now() - restart_time).total_seconds()
                    embed.add_field(
                        name="重啟時間", 
                        value=f"{elapsed:.1f}秒", 
                        inline=True
                    )
                except Exception as e:
                    await func.report_error(e, "addons/update/notifier.py/notify_restart_success/parse_time")
                    pass
            
            embed.add_field(
                name="狀態", 
                value="✅ 所有系統正常運行", 
                inline=True
            )
            
            await owner.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"發送重啟成功通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/notify_restart_success")
            return False
    
    def _create_progress_bar(self, progress: int, length: int = 20) -> str:
        """
        創建進度條
        
        Args:
            progress: 進度百分比 (0-100)
            length: 進度條長度
            
        Returns:
            進度條字串
        """
        filled_length = int(length * progress / 100)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return f"[{bar}]"
    
    async def send_channel_notification(self, channel_id: int, embed: discord.Embed) -> bool:
        """
        發送頻道通知
        
        Args:
            channel_id: 頻道 ID
            embed: 嵌入訊息
            
        Returns:
            通知是否發送成功
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return False
            
            await channel.send(embed=embed)
            return True
            
        except Exception as e:
            self.logger.error(f"發送頻道通知時發生錯誤: {e}")
            await func.report_error(e, "addons/update/notifier.py/send_channel_notification")
            return False


class QuickUpdateView(discord.ui.View):
    """快速更新視圖"""
    
    def __init__(self):
        super().__init__(timeout=3600)  # 1小時後過期
    
    @discord.ui.button(label="立即更新", style=discord.ButtonStyle.success, emoji="🚀")
    async def quick_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """快速更新按鈕"""
        # 檢查是否為 Bot 擁有者
        load_dotenv()
        owner_id = int(os.getenv("BOT_OWNER_ID", 0))
        logger = get_logger(server_id="Bot", source=__name__)
        
        if owner_id == 0:
            logger.error("Bot 擁有者未配置")
            await interaction.response.send_message("❌ Bot 擁有者未配置", ephemeral=True)
            return
        
        if interaction.user.id != owner_id:
            logger.warning(f"非擁有者嘗試執行更新: {interaction.user.name}")
            await interaction.response.send_message("❌ 僅限 Bot 擁有者可以執行更新", ephemeral=True)
            return
        
        # 觸發更新
        update_cog = interaction.client.get_cog("UpdateManagerCog")
        if update_cog:
            await interaction.response.defer()
            
            # 直接調用更新管理器
            try:
                update_manager = update_cog.update_manager
                result = await update_manager.execute_update(interaction)
                
                if result.get("success"):
                    embed = discord.Embed(
                        title="✅ 更新已啟動",
                        description="更新程序已開始，請查看 DM 獲取詳細進度。",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="❌ 更新失敗",
                        description=f"更新啟動失敗：{result.get('error', '未知錯誤')}",
                        color=discord.Color.red()
                    )
                
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
                
            except Exception as e:
                embed = discord.Embed(
                    title="❌ 更新錯誤",
                    description=f"執行更新時發生錯誤：{e}",
                    color=discord.Color.red()
                )
                await func.report_error(e, "addons/update/notifier.py/quick_update")
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
        else:
            await interaction.response.send_message("❌ 更新系統未載入", ephemeral=True)
    
    @discord.ui.button(label="稍後提醒", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def remind_later(self, interaction: discord.Interaction, button: discord.ui.Button):
        """稍後提醒按鈕"""
        embed = discord.Embed(
            title="⏰ 已設定稍後提醒",
            description="將在下次檢查更新時再次提醒您。",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=None)
    
    @discord.ui.button(label="忽略", style=discord.ButtonStyle.danger, emoji="❌")
    async def ignore_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        """忽略更新按鈕"""
        embed = discord.Embed(
            title="❌ 已忽略更新",
            description="已忽略此次更新通知。",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)