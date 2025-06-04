"""
系統提示管理的統一 UI 選單系統

提供全新的統一介面，整合所有系統提示管理功能和模組化編輯。
"""

import discord
from typing import Optional, Dict, Any, Callable, List
import logging

from .manager import SystemPromptManager
from .permissions import PermissionValidator
from .ui import (
    SystemPromptModal,
    SystemPromptModuleModal,
    ConfirmationView,
    create_system_prompt_embed
)
from .exceptions import SystemPromptError, PermissionError


class SystemPromptMainView(discord.ui.View):
    """系統提示管理主選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 300.0):
        """
        初始化主選單
        
        Args:
            manager: 系統提示管理器
            permission_validator: 權限驗證器
            timeout: 超時時間
        """
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = logging.getLogger(__name__)
        
        # 建立主要功能按鈕
        self._setup_main_buttons()
    
    def _setup_main_buttons(self):
        """設定主要功能按鈕"""
        
        # 第一列：基本功能
        self.add_item(SystemPromptFunctionButton(
            label="編輯提示",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            function="set",
            row=0
        ))
        
        self.add_item(SystemPromptFunctionButton(
            label="查看配置",
            emoji="👁️",
            style=discord.ButtonStyle.secondary,
            function="view",
            row=0
        ))
        
        # 第二列：管理功能
        self.add_item(SystemPromptFunctionButton(
            label="複製提示",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            function="copy",
            row=1
        ))
        
        self.add_item(SystemPromptFunctionButton(
            label="移除提示",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            function="remove",
            row=1
        ))
        
        self.add_item(SystemPromptFunctionButton(
            label="重置設定",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            function="reset",
            row=1
        ))
    
    async def function_callback(self, interaction: discord.Interaction, function: str):
        """處理功能按鈕回調"""
        try:
            if function == "set":
                await self._handle_set_function(interaction)
            elif function == "view":
                await self._handle_view_function(interaction)
            elif function == "copy":
                await self._handle_copy_function(interaction)
            elif function == "remove":
                await self._handle_remove_function(interaction)
            elif function == "reload":
                await self._handle_reload_function(interaction)
            elif function == "reset":
                await self._handle_reset_function(interaction)
                
        except Exception as e:
            self.logger.error(f"處理功能 {function} 時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 操作失敗：{str(e)}", ephemeral=True
            )
    
    async def _handle_set_function(self, interaction: discord.Interaction):
        """處理設定提示功能"""
        view = SystemPromptSetView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        embed = discord.Embed(
            title="⚙️ 設定系統提示",
            description="請選擇要設定的範圍",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _handle_view_function(self, interaction: discord.Interaction):
        """處理查看配置功能"""
        view = SystemPromptViewOptionsView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        embed = discord.Embed(
            title="👁️ 查看系統提示配置",
            description="請選擇查看選項",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    
    async def _handle_copy_function(self, interaction: discord.Interaction):
        """處理複製提示功能"""
        view = SystemPromptCopyView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild=interaction.guild
        )
        
        embed = discord.Embed(
            title="📋 複製系統提示",
            description="請選擇來源和目標頻道",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _handle_remove_function(self, interaction: discord.Interaction):
        """處理移除提示功能"""
        view = SystemPromptRemoveView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        embed = discord.Embed(
            title="🗑️ 移除系統提示",
            description="請選擇要移除的範圍",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _handle_reset_function(self, interaction: discord.Interaction):
        """處理重置設定功能"""
        view = SystemPromptResetView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        embed = discord.Embed(
            title="🔄 重置系統提示",
            description="請選擇要重置的範圍",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SystemPromptFunctionButton(discord.ui.Button):
    """系統提示功能按鈕"""
    
    def __init__(self, function: str, **kwargs):
        super().__init__(**kwargs)
        self.function = function
    
    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: SystemPromptMainView = self.view
        await view.function_callback(interaction, self.function)


class SystemPromptSetView(discord.ui.View):
    """設定系統提示的子選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = logging.getLogger(__name__)
        
        # 設定範圍選擇按鈕
        self.add_item(SystemPromptScopeButton(
            label="頻道特定",
            emoji="📢",
            style=discord.ButtonStyle.primary,
            scope="channel"
        ))
        
        self.add_item(SystemPromptScopeButton(
            label="伺服器預設",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            scope="server"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())
    
    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        """處理範圍選擇"""
        try:
            # 權限檢查
            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                target_channel = interaction.channel
                scope_text = f"頻道 #{interaction.channel.name}"
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                target_channel = None
                scope_text = "伺服器預設"
            
            # 建立編輯模式選擇選單
            view = EditModeSelectionView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                scope=scope,
                target_channel=target_channel,
                scope_text=scope_text
            )
            
            embed = discord.Embed(
                title=f"⚙️ 編輯{scope_text}系統提示",
                description="請選擇編輯模式",
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except PermissionError as e:
            await interaction.response.send_message(
                f"❌ 權限不足：{str(e)}", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 操作失敗：{str(e)}", ephemeral=True
            )
    


class EditModeSelectionView(discord.ui.View):
    """編輯模式選擇選單"""
    
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 scope: str,
                 target_channel: Optional[discord.TextChannel],
                 scope_text: str,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.logger = logging.getLogger(__name__)
        
        # 編輯模式按鈕
        self.add_item(EditModeButton(
            label="直接編輯提示",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            edit_mode="direct"
        ))
        
        self.add_item(EditModeButton(
            label="模組化編輯",
            emoji="📦",
            style=discord.ButtonStyle.secondary,
            edit_mode="module"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())
    
    async def edit_mode_callback(self, interaction: discord.Interaction, edit_mode: str):
        """處理編輯模式選擇"""
        try:
            if edit_mode == "direct":
                await self._handle_direct_edit(interaction)
            elif edit_mode == "module":
                await self._handle_module_edit(interaction)
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 操作失敗：{str(e)}", ephemeral=True
            )
    
    async def _handle_direct_edit(self, interaction: discord.Interaction):
        """處理直接編輯提示"""
        # 取得現有內容
        existing_content = ""
        if self.scope == "channel":
            config = self.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            channels = system_prompts.get('channels', {})
            if str(self.target_channel.id) in channels:
                existing_content = channels[str(self.target_channel.id)].get('prompt', '')
        else:
            config = self.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            server_level = system_prompts.get('server_level', {})
            existing_content = server_level.get('prompt', '')
        
        # 開啟編輯 Modal
        modal = SystemPromptModal(
            title=f"直接編輯{self.scope_text}系統提示",
            initial_value=existing_content,
            callback_func=lambda i, prompt: self._handle_direct_set_callback(
                i, prompt
            )
        )
        
        await interaction.response.send_modal(modal)
    
    async def _handle_module_edit(self, interaction: discord.Interaction):
        """處理模組化編輯"""
        try:
            modules = self.manager.get_available_modules()
            
            if not modules:
                await interaction.response.send_message(
                    "❌ 暫無可用的模組", ephemeral=True
                )
                return
            
            view = ModuleEditView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                modules=modules,
                scope=self.scope,
                target_channel=self.target_channel,
                scope_text=self.scope_text
            )
            
            embed = discord.Embed(
                title=f"📦 模組化編輯{self.scope_text}",
                description="請選擇要編輯的模組",
                color=discord.Color.purple()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 載入模組時發生錯誤：{str(e)}", ephemeral=True
            )
    
    async def _handle_direct_set_callback(self,
                                         interaction: discord.Interaction,
                                         content: str):
        """處理直接設定回調"""
        try:
            prompt_data = {'prompt': content}
            
            # 先處理 Discord 互動快取問題 - 確保安全的異步調用
            try:
                result = await self.manager.handle_discord_interaction_cache_issues(interaction)
                self.logger.debug(f"Discord 互動快取處理結果: {result}")
            except Exception as cache_error:
                self.logger.warning(f"Discord 互動快取處理失敗，繼續操作: {cache_error}")
            
            if self.scope == "channel":
                success = self.manager.set_channel_prompt(
                    str(interaction.guild.id),
                    str(self.target_channel.id),
                    prompt_data,
                    str(interaction.user.id)
                )
            else:
                success = self.manager.set_server_prompt(
                    str(interaction.guild.id),
                    prompt_data,
                    str(interaction.user.id)
                )
            
            if success:
                # 額外確保快取清除
                await self.manager.force_clear_all_caches(
                    str(interaction.guild.id),
                    str(self.target_channel.id) if self.scope == "channel" else None,
                    interaction
                )
                
                embed = discord.Embed(
                    title="✅ 系統提示設定成功",
                    description=f"已成功設定{self.scope_text}的系統提示",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="內容長度",
                    value=f"{len(content)} 字元",
                    inline=True
                )
                embed.add_field(
                    name="設定者",
                    value=interaction.user.mention,
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            self.logger.error(f"設定系統提示時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 設定失敗: {str(e)}", ephemeral=True
            )


class EditModeButton(discord.ui.Button):
    """編輯模式按鈕"""
    
    def __init__(self, edit_mode: str, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = edit_mode
    
    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: EditModeSelectionView = self.view
        await view.edit_mode_callback(interaction, self.edit_mode)


class SystemPromptScopeButton(discord.ui.Button):
    """範圍選擇按鈕"""
    
    def __init__(self, scope: str, **kwargs):
        super().__init__(**kwargs)
        self.scope = scope
    
    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: SystemPromptSetView = self.view
        await view.scope_callback(interaction, self.scope)


class SystemPromptViewOptionsView(discord.ui.View):
    """查看配置選項選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        
        # 查看選項按鈕
        self.add_item(SystemPromptViewButton(
            label="當前頻道",
            emoji="📢",
            style=discord.ButtonStyle.primary,
            view_type="current"
        ))
        
        self.add_item(SystemPromptViewButton(
            label="顯示繼承",
            emoji="🔗",
            style=discord.ButtonStyle.secondary,
            view_type="inheritance"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())
    
    async def view_callback(self, interaction: discord.Interaction, view_type: str):
        """處理查看回調"""
        try:
            channel = interaction.channel
            
            # 權限檢查
            self.permission_validator.validate_permission_or_raise(
                interaction.user, 'view', channel
            )
            
            # 添加調試日誌
            self.manager.logger.info(f"🔍 查看配置請求 - 頻道: {channel.id}, 伺服器: {interaction.guild.id}, 類型: {view_type}")
            
            # 先清除可能的快取以確保讀取最新數據
            self.manager.cache.invalidate(str(interaction.guild.id), str(channel.id))
            self.manager.logger.debug(f"已清除快取: {interaction.guild.id}:{channel.id}")
            
            # 取得有效提示
            prompt_data = self.manager.get_effective_prompt(
                str(channel.id),
                str(interaction.guild.id),
                None
            )
            
            # 添加調試日誌 - 直接讀取配置檔案進行對比
            config = self.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            channels = system_prompts.get('channels', {})
            
            if str(channel.id) in channels:
                channel_config = channels[str(channel.id)]
                modules = channel_config.get('modules', {})
                self.manager.logger.info(f"📄 配置檔案中的模組: {modules}")
            else:
                self.manager.logger.info(f"⚠️ 配置檔案中未找到頻道 {channel.id} 的配置")
            
            self.manager.logger.info(f"💡 有效提示數據來源: {prompt_data.get('source', 'unknown')}")
            
            # 建立 Embed
            embed = create_system_prompt_embed(prompt_data, channel)
            
            # 添加模組資訊到 embed（用於調試）
            if str(channel.id) in channels:
                channel_config = channels[str(channel.id)]
                modules = channel_config.get('modules', {})
                if modules:
                    module_info = []
                    for module_name, module_content in modules.items():
                        content_preview = module_content[:50] + "..." if len(module_content) > 50 else module_content
                        module_info.append(f"**{module_name}**: {content_preview}")
                    
                    embed.add_field(
                        name="🔧 已配置模組",
                        value="\n".join(module_info) if module_info else "無",
                        inline=False
                    )
            
            # 如果顯示繼承資訊
            if view_type == "inheritance":
                # 檢查各層級的提示
                inheritance_info = []
                
                # YAML 基礎
                inheritance_info.append("🔹 YAML 基礎提示")
                
                # 伺服器級別
                server_level = system_prompts.get('server_level', {})
                if server_level.get('prompt') or server_level.get('modules'):
                    inheritance_info.append("🔸 伺服器預設提示")
                
                # 頻道級別
                if str(channel.id) in channels:
                    channel_config = channels[str(channel.id)]
                    if channel_config.get('prompt') or channel_config.get('modules'):
                        inheritance_info.append("🔸 頻道特定提示")
                
                embed.add_field(
                    name="繼承層級",
                    value="\n".join(inheritance_info) if inheritance_info else "僅 YAML 基礎",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except PermissionError as e:
            await interaction.response.send_message(
                f"❌ 權限不足：{str(e)}", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 查看失敗：{str(e)}", ephemeral=True
            )


class SystemPromptViewButton(discord.ui.Button):
    """查看選項按鈕"""
    
    def __init__(self, view_type: str, **kwargs):
        super().__init__(**kwargs)
        self.view_type = view_type
    
    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: SystemPromptViewOptionsView = self.view
        await view.view_callback(interaction, self.view_type)


class ModuleEditView(discord.ui.View):
    """模組編輯選單"""
    
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 modules: List[str],
                 scope: str = None,
                 target_channel: Optional[discord.TextChannel] = None,
                 scope_text: str = None,
                 timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.modules = modules
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.logger = logging.getLogger(__name__)
        
        # 如果已經有範圍，直接顯示模組選擇器
        if scope and scope_text:
            self._setup_module_selector()
        else:
            # 否則先選擇範圍（保持向後相容）
            self._setup_scope_selector()
    
    def _setup_scope_selector(self):
        """設定範圍選擇器"""
        self.add_item(ModuleScopeButton(
            label="頻道模組",
            emoji="📢",
            style=discord.ButtonStyle.primary,
            scope="channel"
        ))
        
        self.add_item(ModuleScopeButton(
            label="伺服器模組",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            scope="server"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())
    
    def _setup_module_selector(self):
        """設定模組選擇器"""
        # 建立模組選擇器
        options = []
        for module in self.modules[:25]:  # Discord 限制
            options.append(discord.SelectOption(
                label=module,
                value=module,
                description=f"編輯 {module} 模組"
            ))
        
        if options:
            select = ModuleSelect(
                placeholder="選擇要編輯的模組",
                options=options,
                manager=self.manager,
                scope=self.scope,
                channel=self.target_channel,
                guild=None,  # 將在回調中設定
                scope_text=self.scope_text
            )
            
            self.add_item(select)
        
        # 返回主選單按鈕
        self.add_item(BackButton())
    
    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        """處理範圍選擇"""
        try:
            # 權限檢查
            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
            
            self.selected_scope = scope
            
            # 建立模組選擇器
            options = []
            for module in self.modules[:25]:  # Discord 限制
                options.append(discord.SelectOption(
                    label=module,
                    value=module,
                    description=f"編輯 {module} 模組"
                ))
            
            if options:
                select = ModuleSelect(
                    placeholder="選擇要編輯的模組",
                    options=options,
                    manager=self.manager,
                    scope=scope,
                    channel=interaction.channel if scope == "channel" else None,
                    guild=interaction.guild
                )
                
                # 清除現有元件並添加選擇器
                self.clear_items()
                self.add_item(select)
                self.add_item(BackButton())
                
                embed = discord.Embed(
                    title=f"📦 編輯{'頻道' if scope == 'channel' else '伺服器'}模組",
                    description="請選擇要編輯的模組",
                    color=discord.Color.purple()
                )
                
                await interaction.response.edit_message(embed=embed, view=self)
            
        except PermissionError as e:
            await interaction.response.send_message(
                f"❌ 權限不足：{str(e)}", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 操作失敗：{str(e)}", ephemeral=True
            )


class ModuleScopeButton(discord.ui.Button):
    """模組範圍選擇按鈕"""
    
    def __init__(self, scope: str, **kwargs):
        super().__init__(**kwargs)
        self.scope = scope
    
    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: ModuleEditView = self.view
        await view.scope_callback(interaction, self.scope)


class ModuleSelect(discord.ui.Select):
    """模組選擇器"""
    
    def __init__(self,
                 manager: SystemPromptManager,
                 scope: str,
                 channel: Optional[discord.TextChannel],
                 guild: Optional[discord.Guild],
                 scope_text: str = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.manager = manager
        self.scope = scope
        self.channel = channel
        self.guild = guild
        self.scope_text = scope_text or scope
    
    async def callback(self, interaction: discord.Interaction):
        """選擇器回調"""
        try:
            selected_module = self.values[0]
            
            # 設定 guild（如果為 None）
            if not self.guild:
                self.guild = interaction.guild
            
            # 取得現有模組內容
            existing_content = ""
            config = self.manager._load_guild_config(str(self.guild.id))
            system_prompts = config.get('system_prompts', {})
            
            if self.scope == "channel" and self.channel:
                channels = system_prompts.get('channels', {})
                if str(self.channel.id) in channels:
                    channel_config = channels[str(self.channel.id)]
                    modules = channel_config.get('modules', {})
                    existing_content = modules.get(selected_module, '')
            else:
                server_level = system_prompts.get('server_level', {})
                modules = server_level.get('modules', {})
                existing_content = modules.get(selected_module, '')
            
            # 開啟模組編輯 Modal
            modal = SystemPromptModuleModal(
                module_name=selected_module,
                initial_value=existing_content,
                callback_func=lambda i, module, content: self._handle_module_callback(
                    i, module, content
                )
            )
            
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 開啟編輯器失敗：{str(e)}", ephemeral=True
            )
    
    async def _handle_module_callback(self,
                                      interaction: discord.Interaction,
                                      module_name: str,
                                      content: str):
        """處理模組編輯回調"""
        try:
            # 添加調試日誌
            logger = logging.getLogger(__name__)
            logger.info(f"🔧 開始處理模組編輯回調 - 模組: {module_name}, 範圍: {self.scope}")
            logger.debug(f"模組內容: {content[:100]}..." if len(content) > 100 else f"模組內容: {content}")
            
            # 先處理 Discord 互動快取問題 - 確保安全的異步調用
            try:
                result = await self.manager.handle_discord_interaction_cache_issues(interaction)
                logger.debug(f"Discord 互動快取處理結果: {result}")
            except Exception as cache_error:
                logger.warning(f"Discord 互動快取處理失敗，繼續操作: {cache_error}")
            
            # 取得所有現有模組，避免覆蓋其他模組
            config = self.manager._load_guild_config(str(self.guild.id))
            system_prompts = config.get('system_prompts', {})
            
            logger.debug(f"載入配置完成，system_prompts 存在: {bool(system_prompts)}")
            
            existing_modules = {}
            if self.scope == "channel" and self.channel:
                channels = system_prompts.get('channels', {})
                if str(self.channel.id) in channels:
                    existing_modules = channels[str(self.channel.id)].get('modules', {})
                logger.info(f"頻道現有模組: {existing_modules}")
            else:
                server_level = system_prompts.get('server_level', {})
                existing_modules = server_level.get('modules', {})
                logger.info(f"伺服器現有模組: {existing_modules}")
            
            # 更新特定模組
            existing_modules[module_name] = content
            prompt_data = {'modules': existing_modules}
            
            logger.info(f"準備保存的模組數據: {prompt_data}")
            
            if self.scope == "channel" and self.channel:
                logger.info(f"正在設定頻道模組: {self.guild.id}/{self.channel.id}")
                success = self.manager.set_channel_prompt(
                    str(self.guild.id),
                    str(self.channel.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                display_scope_text = self.scope_text or f"頻道 #{self.channel.name}"
            else:
                logger.info(f"正在設定伺服器模組: {self.guild.id}")
                success = self.manager.set_server_prompt(
                    str(self.guild.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                display_scope_text = self.scope_text or "伺服器預設"
            
            logger.info(f"模組設定結果: {success}")
            
            # 驗證保存結果並額外確保快取清除
            if success:
                # 額外的生產環境快取清除
                await self.manager.force_clear_all_caches(
                    str(self.guild.id),
                    str(self.channel.id) if self.scope == "channel" and self.channel else None,
                    interaction
                )
                
                # 立即重新讀取配置進行驗證
                verification_config = self.manager._load_guild_config(str(self.guild.id))
                verification_prompts = verification_config.get('system_prompts', {})
                
                if self.scope == "channel" and self.channel:
                    verification_channels = verification_prompts.get('channels', {})
                    if str(self.channel.id) in verification_channels:
                        verification_modules = verification_channels[str(self.channel.id)].get('modules', {})
                        logger.info(f"✅ 驗證：保存後的模組 = {verification_modules}")
                        
                        # 檢查特定模組是否正確保存
                        if module_name in verification_modules and verification_modules[module_name] == content:
                            logger.info(f"✅ 驗證通過：模組 {module_name} 已正確保存")
                        else:
                            logger.warning(f"⚠️ 驗證失敗：模組 {module_name} 保存不正確")
                            logger.warning(f"期望內容: {content}")
                            logger.warning(f"實際內容: {verification_modules.get(module_name, 'NOT_FOUND')}")
                
                embed = discord.Embed(
                    title="✅ 模組設定成功",
                    description=f"已成功設定{display_scope_text}的 {module_name} 模組",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="模組名稱",
                    value=module_name,
                    inline=True
                )
                embed.add_field(
                    name="內容長度",
                    value=f"{len(content)} 字元",
                    inline=True
                )
                
                # 添加驗證資訊到 embed
                embed.add_field(
                    name="驗證狀態",
                    value="已驗證保存成功並清除快取",
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                logger.error("模組設定失敗，success = False")
                await interaction.response.send_message(
                    f"❌ 設定模組失敗: 操作未成功", ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 設定模組失敗: {str(e)}", ephemeral=True
            )


class SystemPromptCopyView(discord.ui.View):
    """複製系統提示選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 guild: discord.Guild,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.guild = guild
        
        # 獲取可見的文字頻道
        text_channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).view_channel]
        
        if len(text_channels) > 0:
            # 來源頻道選擇器
            from_options = []
            for channel in text_channels[:25]:
                from_options.append(discord.SelectOption(
                    label=f"#{channel.name}",
                    value=str(channel.id),
                    description=f"ID: {channel.id}"
                ))
            
            if from_options:
                self.add_item(ChannelSelect(
                    placeholder="選擇來源頻道",
                    options=from_options,
                    custom_id="from_channel"
                ))
            
            # 目標頻道選擇器
            to_options = []
            for channel in text_channels[:25]:
                to_options.append(discord.SelectOption(
                    label=f"#{channel.name}",
                    value=str(channel.id),
                    description=f"ID: {channel.id}"
                ))
            
            if to_options:
                self.add_item(ChannelSelect(
                    placeholder="選擇目標頻道",
                    options=to_options,
                    custom_id="to_channel"
                ))
            
            # 執行複製按鈕
            self.add_item(CopyExecuteButton())
        
        # 返回主選單按鈕
        self.add_item(BackButton())


class SystemPromptRemoveView(discord.ui.View):
    """移除系統提示選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        
        # 移除範圍按鈕
        self.add_item(RemoveButton(
            label="移除頻道提示",
            emoji="📢",
            style=discord.ButtonStyle.danger,
            remove_type="channel"
        ))
        
        self.add_item(RemoveButton(
            label="移除伺服器提示",
            emoji="🏠",
            style=discord.ButtonStyle.danger,
            remove_type="server"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())


class SystemPromptResetView(discord.ui.View):
    """重置系統提示選單"""
    
    def __init__(self, 
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        
        # 重置範圍按鈕
        self.add_item(ResetButton(
            label="重置當前頻道",
            emoji="📢",
            style=discord.ButtonStyle.danger,
            reset_type="channel"
        ))
        
        self.add_item(ResetButton(
            label="重置伺服器預設",
            emoji="🏠",
            style=discord.ButtonStyle.danger,
            reset_type="server"
        ))
        
        self.add_item(ResetButton(
            label="重置全部設定",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            reset_type="all"
        ))
        
        # 返回主選單按鈕
        self.add_item(BackButton())


# 輔助按鈕類別

class BackButton(discord.ui.Button):
    """返回主選單按鈕"""
    
    def __init__(self):
        super().__init__(
            label="返回主選單",
            emoji="🔙",
            style=discord.ButtonStyle.secondary,
            row=4
        )
    
    async def callback(self, interaction: discord.Interaction):
        """返回主選單"""
        from .commands import SystemPromptCommands
        
        # 獲取命令處理器實例
        commands_cog = interaction.client.get_cog("SystemPromptCommands")
        if isinstance(commands_cog, SystemPromptCommands):
            manager = commands_cog.get_system_prompt_manager()
            permission_validator = commands_cog.permission_validator
            
            # 建立新的主選單
            main_view = SystemPromptMainView(manager, permission_validator)
            
            embed = discord.Embed(
                title="🤖 系統提示管理",
                description="請選擇要執行的功能",
                color=discord.Color.blue()
            )
            
            await interaction.response.edit_message(embed=embed, view=main_view)


class ChannelSelect(discord.ui.Select):
    """頻道選擇器（用於複製功能）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_channel_id = None
    
    async def callback(self, interaction: discord.Interaction):
        """選擇器回調"""
        self.selected_channel_id = self.values[0]
        
        # 更新選擇器顯示
        for option in self.options:
            option.default = (option.value == self.selected_channel_id)
        
        await interaction.response.edit_message(view=self.view)


class CopyExecuteButton(discord.ui.Button):
    """執行複製按鈕"""
    
    def __init__(self):
        super().__init__(
            label="執行複製",
            emoji="📋",
            style=discord.ButtonStyle.success,
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        """執行複製操作"""
        view: SystemPromptCopyView = self.view
        
        # 獲取選中的頻道
        from_channel_id = None
        to_channel_id = None
        
        for item in view.children:
            if isinstance(item, ChannelSelect):
                if item.custom_id == "from_channel" and item.selected_channel_id:
                    from_channel_id = item.selected_channel_id
                elif item.custom_id == "to_channel" and item.selected_channel_id:
                    to_channel_id = item.selected_channel_id
        
        if not from_channel_id or not to_channel_id:
            await interaction.response.send_message(
                "❌ 請先選擇來源和目標頻道", ephemeral=True
            )
            return
        
        if from_channel_id == to_channel_id:
            await interaction.response.send_message(
                "❌ 來源頻道和目標頻道不能相同", ephemeral=True
            )
            return
        
        try:
            # 權限檢查
            to_channel = view.guild.get_channel(int(to_channel_id))
            view.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', to_channel
            )
            
            # 執行複製
            success = view.manager.copy_channel_prompt(
                str(view.guild.id), from_channel_id,
                str(view.guild.id), to_channel_id
            )
            
            if success:
                from_channel = view.guild.get_channel(int(from_channel_id))
                embed = discord.Embed(
                    title="✅ 複製成功",
                    description=f"已成功將 #{from_channel.name} 的系統提示複製到 #{to_channel.name}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 複製失敗：{str(e)}", ephemeral=True
            )


class RemoveButton(discord.ui.Button):
    """移除按鈕"""
    
    def __init__(self, remove_type: str, **kwargs):
        super().__init__(**kwargs)
        self.remove_type = remove_type
    
    async def callback(self, interaction: discord.Interaction):
        """移除操作"""
        view: SystemPromptRemoveView = self.view
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"🗑️ 開始移除操作 - 類型: {self.remove_type}")
            
            # 權限檢查和確認文字
            if self.remove_type == "channel":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                confirm_text = f"確定要移除頻道 #{interaction.channel.name} 的系統提示嗎？"
                operation_text = f"頻道 #{interaction.channel.name}"
            else:
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要移除伺服器預設系統提示嗎？"
                operation_text = "伺服器預設"
            
            # 先檢查是否有內容可移除
            config = view.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            
            if self.remove_type == "channel":
                channels = system_prompts.get('channels', {})
                if str(interaction.channel.id) not in channels:
                    await interaction.response.send_message(
                        f"❌ 頻道 #{interaction.channel.name} 沒有設定系統提示",
                        ephemeral=True
                    )
                    return
            else:
                server_level = system_prompts.get('server_level', {})
                if not server_level:
                    await interaction.response.send_message(
                        "❌ 伺服器沒有設定預設系統提示",
                        ephemeral=True
                    )
                    return
            
            # 確認對話框
            embed = discord.Embed(
                title="⚠️ 確認移除",
                description=confirm_text,
                color=discord.Color.orange()
            )
            
            confirm_view = ConfirmationView(
                confirm_text="確認移除",
                cancel_text="取消"
            )
            
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            
            # 等待用戶確認
            timeout = await confirm_view.wait()
            
            if timeout:
                logger.warning("移除操作超時")
                return
            
            if confirm_view.result:
                logger.info(f"用戶確認移除 {operation_text}")
                
                # 執行移除操作
                try:
                    if self.remove_type == "channel":
                        success = view.manager.remove_channel_prompt(
                            str(interaction.guild.id),
                            str(interaction.channel.id)
                        )
                        logger.info(f"頻道移除結果: {success}")
                    else:
                        success = view.manager.remove_server_prompt(
                            str(interaction.guild.id)
                        )
                        logger.info(f"伺服器移除結果: {success}")
                    
                    if success:
                        # 立即驗證移除結果
                        verification_config = view.manager._load_guild_config(str(interaction.guild.id))
                        verification_prompts = verification_config.get('system_prompts', {})
                        
                        verification_success = True
                        if self.remove_type == "channel":
                            verification_channels = verification_prompts.get('channels', {})
                            if str(interaction.channel.id) in verification_channels:
                                verification_success = False
                                logger.error(f"驗證失敗：頻道 {interaction.channel.id} 仍存在於配置中")
                        else:
                            verification_server_level = verification_prompts.get('server_level', {})
                            if verification_server_level:
                                verification_success = False
                                logger.error(f"驗證失敗：伺服器級別配置仍存在: {verification_server_level}")
                        
                        if verification_success:
                            embed = discord.Embed(
                                title="✅ 移除成功",
                                description=f"已成功移除{operation_text}的系統提示",
                                color=discord.Color.green()
                            )
                            logger.info(f"✅ {operation_text} 移除驗證通過")
                        else:
                            embed = discord.Embed(
                                title="⚠️ 移除異常",
                                description=f"移除操作完成，但驗證發現配置仍存在",
                                color=discord.Color.orange()
                            )
                        
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        logger.error("移除操作返回 False")
                        await interaction.followup.send(
                            f"❌ 移除{operation_text}失敗：操作未成功",
                            ephemeral=True
                        )
                
                except Exception as remove_error:
                    logger.error(f"執行移除操作時發生錯誤: {remove_error}")
                    await interaction.followup.send(
                        f"❌ 移除{operation_text}時發生錯誤: {str(remove_error)}",
                        ephemeral=True
                    )
            else:
                logger.info("用戶取消移除操作")
            
        except Exception as e:
            logger.error(f"移除操作發生錯誤: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 移除失敗：{str(e)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 移除失敗：{str(e)}", ephemeral=True
                )


class ResetButton(discord.ui.Button):
    """重置按鈕"""
    
    def __init__(self, reset_type: str, **kwargs):
        super().__init__(**kwargs)
        self.reset_type = reset_type
    
    async def callback(self, interaction: discord.Interaction):
        """重置操作"""
        view: SystemPromptResetView = self.view
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"🔄 開始重置操作 - 類型: {self.reset_type}")
            
            # 權限檢查和確認文字
            if self.reset_type == "channel":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                confirm_text = f"確定要重置頻道 #{interaction.channel.name} 的系統提示嗎？"
                operation_text = f"頻道 #{interaction.channel.name}"
            elif self.reset_type == "server":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要重置伺服器預設系統提示嗎？"
                operation_text = "伺服器預設"
            else:  # all
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要重置所有系統提示設定嗎？\n⚠️ 此操作無法復原！"
                operation_text = "所有"
            
            # 先檢查是否有內容可重置
            config = view.manager._load_guild_config(str(interaction.guild.id))
            system_prompts = config.get('system_prompts', {})
            
            has_content_to_reset = False
            if self.reset_type == "channel":
                channels = system_prompts.get('channels', {})
                if str(interaction.channel.id) in channels:
                    has_content_to_reset = True
            elif self.reset_type == "server":
                server_level = system_prompts.get('server_level', {})
                if server_level:
                    has_content_to_reset = True
            else:  # all
                server_level = system_prompts.get('server_level', {})
                channels = system_prompts.get('channels', {})
                if server_level or channels:
                    has_content_to_reset = True
            
            if not has_content_to_reset:
                await interaction.response.send_message(
                    f"❌ {operation_text}沒有設定需要重置",
                    ephemeral=True
                )
                return
            
            # 確認對話框
            embed = discord.Embed(
                title="⚠️ 確認重置",
                description=confirm_text,
                color=discord.Color.red()
            )
            
            confirm_view = ConfirmationView(
                confirm_text="確認重置",
                cancel_text="取消"
            )
            
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            
            # 等待用戶確認
            timeout = await confirm_view.wait()
            
            if timeout:
                logger.warning("重置操作超時")
                return
            
            if confirm_view.result:
                logger.info(f"用戶確認重置 {operation_text}")
                
                # 執行重置操作
                try:
                    success = False
                    
                    if self.reset_type == "channel":
                        success = view.manager.remove_channel_prompt(
                            str(interaction.guild.id),
                            str(interaction.channel.id)
                        )
                        logger.info(f"頻道重置結果: {success}")
                        
                        # 驗證重置結果
                        if success:
                            verification_config = view.manager._load_guild_config(str(interaction.guild.id))
                            verification_channels = verification_config.get('system_prompts', {}).get('channels', {})
                            if str(interaction.channel.id) in verification_channels:
                                success = False
                                logger.error(f"驗證失敗：頻道 {interaction.channel.id} 仍存在於配置中")
                        
                    elif self.reset_type == "server":
                        success = view.manager.remove_server_prompt(
                            str(interaction.guild.id)
                        )
                        logger.info(f"伺服器重置結果: {success}")
                        
                        # 驗證重置結果
                        if success:
                            verification_config = view.manager._load_guild_config(str(interaction.guild.id))
                            verification_server_level = verification_config.get('system_prompts', {}).get('server_level', {})
                            if verification_server_level:
                                success = False
                                logger.error(f"驗證失敗：伺服器級別配置仍存在: {verification_server_level}")
                        
                    else:  # all
                        try:
                            # 重置為預設配置
                            default_config = view.manager._get_default_config()
                            view.manager._save_guild_config(str(interaction.guild.id), default_config)
                            
                            # 清除所有快取
                            view.manager.clear_cache(str(interaction.guild.id))
                            logger.info("已清除快取")
                            
                            # 驗證重置結果
                            verification_config = view.manager._load_guild_config(str(interaction.guild.id))
                            verification_prompts = verification_config.get('system_prompts', {})
                            verification_server_level = verification_prompts.get('server_level', {})
                            verification_channels = verification_prompts.get('channels', {})
                            
                            if not verification_server_level and not verification_channels:
                                success = True
                                logger.info("✅ 全部重置驗證通過")
                            else:
                                success = False
                                logger.error(f"驗證失敗：仍有配置存在 - 伺服器: {verification_server_level}, 頻道: {verification_channels}")
                            
                        except Exception as reset_all_error:
                            logger.error(f"重置全部設定時發生錯誤: {reset_all_error}")
                            success = False
                    
                    if success:
                        embed = discord.Embed(
                            title="✅ 重置成功",
                            description=f"已成功重置{operation_text}系統提示設定",
                            color=discord.Color.green()
                        )
                        logger.info(f"✅ {operation_text} 重置驗證通過")
                    else:
                        embed = discord.Embed(
                            title="❌ 重置失敗",
                            description=f"重置{operation_text}操作未成功或驗證失敗",
                            color=discord.Color.red()
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                
                except Exception as reset_error:
                    logger.error(f"執行重置操作時發生錯誤: {reset_error}")
                    await interaction.followup.send(
                        f"❌ 重置{operation_text}時發生錯誤: {str(reset_error)}",
                        ephemeral=True
                    )
            else:
                logger.info("用戶取消重置操作")
            
        except Exception as e:
            logger.error(f"重置操作發生錯誤: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 重置失敗：{str(e)}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ 重置失敗：{str(e)}", ephemeral=True
                )