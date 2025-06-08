"""記憶系統 Discord 指令模組

提供記憶系統的 Discord slash 指令介面，包括搜尋、統計、配置和清除功能。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .memory.memory_manager import MemoryManager, SearchQuery, SearchType, MemoryStats
from .memory.exceptions import MemorySystemError, SearchError, ConfigurationError


class MemoryCommands(commands.Cog):
    """記憶系統指令 Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
    
    def get_memory_manager(self) -> Optional[MemoryManager]:
        """取得記憶管理器實例"""
        return getattr(self.bot, 'memory_manager', None)
    
    def is_memory_enabled(self) -> bool:
        """檢查記憶系統是否啟用"""
        return getattr(self.bot, 'memory_enabled', False)
    
    async def check_memory_available(self, interaction: discord.Interaction) -> bool:
        """檢查記憶系統可用性並回應錯誤"""
        if not self.is_memory_enabled():
            await interaction.response.send_message(
                "❌ 記憶系統未啟用或不可用",
                ephemeral=True
            )
            return False
        return True
    
    @app_commands.command(name="memory-search", description="搜尋頻道記憶")
    @app_commands.describe(
        query="搜尋關鍵字或語句",
        search_type="搜尋類型 (semantic: 語義搜尋, keyword: 關鍵字搜尋, hybrid: 混合搜尋)",
        limit="搜尋結果數量限制 (1-20)",
        days_ago="搜尋範圍 (最近N天，0表示不限制)"
    )
    async def memory_search(
        self,
        interaction: discord.Interaction,
        query: str,
        search_type: Optional[str] = "hybrid",
        limit: Optional[int] = 10,
        days_ago: Optional[int] = 0
    ):
        """搜尋頻道記憶指令"""
        
        if not await self.check_memory_available(interaction):
            return
        
        # 參數驗證
        if not query.strip():
            await interaction.response.send_message(
                "❌ 請提供搜尋關鍵字",
                ephemeral=True
            )
            return
        
        if limit < 1 or limit > 20:
            limit = 10
        
        # 解析搜尋類型
        type_mapping = {
            "semantic": SearchType.SEMANTIC,
            "keyword": SearchType.KEYWORD,
            "hybrid": SearchType.HYBRID,
            "temporal": SearchType.TEMPORAL
        }
        
        search_type_enum = type_mapping.get(search_type.lower(), SearchType.HYBRID)
        
        # 計算時間範圍
        time_range = None
        if days_ago > 0:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days_ago)
            time_range = (start_time, end_time)
        
        await interaction.response.defer()
        
        try:
            memory_manager = self.get_memory_manager()
            
            # 建立搜尋查詢
            search_query = SearchQuery(
                text=query,
                channel_id=str(interaction.channel.id),
                search_type=search_type_enum,
                limit=limit,
                threshold=0.3,
                time_range=time_range,
                include_metadata=True
            )
            
            # 執行搜尋
            search_result = await memory_manager.search_memory(search_query)
            
            # 建立回應嵌入
            embed = discord.Embed(
                title="🔍 記憶搜尋結果",
                description=f"搜尋關鍵字: `{query}`",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="搜尋資訊",
                value=f"**方法**: {search_result.search_method}\n"
                      f"**結果數**: {search_result.total_found}\n"
                      f"**搜尋時間**: {search_result.search_time_ms}ms\n"
                      f"**快取命中**: {'是' if search_result.cache_hit else '否'}",
                inline=True
            )
            
            if search_result.messages:
                # 顯示搜尋結果
                results_text = []
                for i, (message, score) in enumerate(zip(search_result.messages, search_result.relevance_scores)):
                    if i >= 5:  # 限制顯示數量
                        break
                    
                    content = message.get("content", "")[:100]
                    if len(message.get("content", "")) > 100:
                        content += "..."
                    
                    timestamp = message.get("timestamp", "")
                    if isinstance(timestamp, datetime):
                        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M")
                    else:
                        timestamp_str = str(timestamp)[:16]
                    
                    results_text.append(
                        f"**{i+1}.** ({score:.2f}) `{timestamp_str}`\n{content}"
                    )
                
                embed.add_field(
                    name="搜尋結果",
                    value="\n\n".join(results_text) if results_text else "無相關結果",
                    inline=False
                )
            else:
                embed.add_field(
                    name="搜尋結果",
                    value="❌ 未找到相關記憶",
                    inline=False
                )
            
            embed.set_footer(text=f"頻道: #{interaction.channel.name}")
            
            await interaction.followup.send(embed=embed)
            
        except SearchError as e:
            self.logger.error(f"記憶搜尋失敗: {e}")
            await interaction.followup.send(
                f"❌ 搜尋失敗: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"記憶搜尋發生未預期錯誤: {e}")
            await interaction.followup.send(
                "❌ 搜尋過程中發生錯誤，請稍後再試",
                ephemeral=True
            )
    
    @app_commands.command(name="memory-stats", description="顯示記憶系統統計資訊")
    async def memory_stats(self, interaction: discord.Interaction):
        """記憶系統統計資訊指令"""
        
        if not await self.check_memory_available(interaction):
            return
        
        await interaction.response.defer()
        
        try:
            memory_manager = self.get_memory_manager()
            stats = await memory_manager.get_stats()
            
            # 建立統計嵌入
            embed = discord.Embed(
                title="📊 記憶系統統計",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # 基本統計
            embed.add_field(
                name="基本資訊",
                value=f"**總頻道數**: {stats.total_channels}\n"
                      f"**總訊息數**: {stats.total_messages:,}\n"
                      f"**啟用向量搜尋**: {stats.vector_enabled_channels}",
                inline=True
            )
            
            # 性能統計
            embed.add_field(
                name="性能指標",
                value=f"**平均查詢時間**: {stats.average_query_time_ms:.1f}ms\n"
                      f"**快取命中率**: {stats.cache_hit_rate:.1%}\n"
                      f"**存儲大小**: {stats.storage_size_mb:.1f}MB",
                inline=True
            )
            
            # 系統狀態
            memory_enabled = self.is_memory_enabled()
            vector_enabled = (memory_manager.current_profile.vector_enabled
                            if memory_manager and memory_manager.current_profile else False)
            
            embed.add_field(
                name="系統狀態",
                value=f"**記憶系統**: {'🟢 啟用' if memory_enabled else '🔴 停用'}\n"
                      f"**向量搜尋**: {'🟢 啟用' if vector_enabled else '🔴 停用'}\n"
                      f"**配置檔案**: {memory_manager.current_profile.name if memory_manager and memory_manager.current_profile else '預設'}",
                inline=True
            )
            
            embed.set_footer(text="記憶系統統計資訊")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"取得記憶統計失敗: {e}")
            await interaction.followup.send(
                "❌ 無法取得統計資訊，請稍後再試",
                ephemeral=True
            )
    
    @app_commands.command(name="memory-clear", description="清除特定頻道的記憶 (需要管理權限)")
    @app_commands.describe(
        confirm="確認清除 (請輸入 'CONFIRM' 來確認操作)"
    )
    async def memory_clear(
        self,
        interaction: discord.Interaction,
        confirm: str
    ):
        """清除頻道記憶指令"""
        
        # 權限檢查
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "❌ 您需要管理頻道權限才能執行此操作",
                ephemeral=True
            )
            return
        
        if not await self.check_memory_available(interaction):
            return
        
        # 確認檢查
        if confirm != "CONFIRM":
            await interaction.response.send_message(
                "❌ 請輸入 `CONFIRM` 來確認清除操作\n"
                "⚠️ **警告**: 此操作將永久刪除該頻道的所有記憶資料",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        try:
            memory_manager = self.get_memory_manager()
            channel_id = str(interaction.channel.id)
            
            # TODO: 實作清除功能 (需要在 MemoryManager 中添加此方法)
            # success = await memory_manager.clear_channel_memory(channel_id)
            
            # 暫時回應
            embed = discord.Embed(
                title="🗑️ 記憶清除",
                description=f"頻道 #{interaction.channel.name} 的記憶清除功能即將推出",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"清除頻道記憶失敗: {e}")
            await interaction.followup.send(
                "❌ 清除記憶時發生錯誤，請稍後再試",
                ephemeral=True
            )
    
    @app_commands.command(name="memory-config", description="顯示記憶系統配置資訊")
    async def memory_config(self, interaction: discord.Interaction):
        """顯示記憶系統配置資訊"""
        
        if not await self.check_memory_available(interaction):
            return
        
        try:
            memory_manager = self.get_memory_manager()
            
            embed = discord.Embed(
                title="⚙️ 記憶系統配置",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            if memory_manager and memory_manager.current_profile:
                profile = memory_manager.current_profile
                
                embed.add_field(
                    name="配置檔案",
                    value=f"**名稱**: {profile.name}\n"
                          f"**向量搜尋**: {'啟用' if profile.vector_enabled else '停用'}\n"
                          f"**嵌入模型**: {profile.embedding_model[:50]}...",
                    inline=False
                )
                
                embed.add_field(
                    name="硬體設定",
                    value=f"**裝置**: {profile.device}\n"
                          f"**CPU 模式**: {'是' if profile.cpu_only else '否'}\n"
                          f"**記憶體閾值**: {profile.memory_threshold_mb}MB",
                    inline=True
                )
                
                # 取得記憶系統配置
                config = memory_manager.config.get_memory_config()
                
                embed.add_field(
                    name="系統設定",
                    value=f"**自動檢測**: {'啟用' if config.get('auto_detection', True) else '停用'}\n"
                          f"**快取**: {'啟用' if config.get('cache', {}).get('enabled', True) else '停用'}\n"
                          f"**索引優化**: {'啟用' if config.get('index_optimization', {}).get('enabled', True) else '停用'}",
                    inline=True
                )
            else:
                embed.add_field(
                    name="配置狀態",
                    value="❌ 無法載入配置資訊",
                    inline=False
                )
            
            embed.set_footer(text="記憶系統配置資訊")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            self.logger.error(f"取得記憶配置失敗: {e}")
            await interaction.response.send_message(
                "❌ 無法取得配置資訊，請稍後再試",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """設定 Cog"""
    await bot.add_cog(MemoryCommands(bot))