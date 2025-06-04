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
            label="設定提示",
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
        
        self.add_item(SystemPromptFunctionButton(
            label="模組編輯",
            emoji="📦",
            style=discord.ButtonStyle.secondary,
            function="modules",
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
            elif function == "modules":
                await self._handle_modules_function(interaction)
            elif function == "copy":
                await self._handle_copy_function(interaction)
            elif function == "remove":
                await self._handle_remove_function(interaction)
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
    
    async def _handle_modules_function(self, interaction: discord.Interaction):
        """處理模組編輯功能"""
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
                modules=modules
            )
            
            embed = discord.Embed(
                title="📦 模組化編輯",
                description="請選擇要編輯的模組和範圍",
                color=discord.Color.purple()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 載入模組時發生錯誤：{str(e)}", ephemeral=True
            )
    
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
            
            # 取得現有內容
            existing_content = ""
            if scope == "channel":
                config = self.manager._load_guild_config(str(interaction.guild.id))
                system_prompts = config.get('system_prompts', {})
                channels = system_prompts.get('channels', {})
                if str(interaction.channel.id) in channels:
                    existing_content = channels[str(interaction.channel.id)].get('prompt', '')
            else:
                config = self.manager._load_guild_config(str(interaction.guild.id))
                system_prompts = config.get('system_prompts', {})
                server_level = system_prompts.get('server_level', {})
                existing_content = server_level.get('prompt', '')
            
            # 開啟編輯 Modal
            modal = SystemPromptModal(
                title=f"設定{scope_text}系統提示",
                initial_value=existing_content,
                callback_func=lambda i, prompt: self._handle_set_callback(
                    i, scope, target_channel, prompt
                )
            )
            
            await interaction.response.send_modal(modal)
            
        except PermissionError as e:
            await interaction.response.send_message(
                f"❌ 權限不足：{str(e)}", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 操作失敗：{str(e)}", ephemeral=True
            )
    
    async def _handle_set_callback(self, 
                                   interaction: discord.Interaction,
                                   scope: str,
                                   channel: Optional[discord.TextChannel],
                                   content: str):
        """處理設定回調"""
        try:
            prompt_data = {'prompt': content}
            
            if scope == "channel":
                success = self.manager.set_channel_prompt(
                    str(interaction.guild.id),
                    str(channel.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = f"頻道 #{channel.name}"
            else:
                success = self.manager.set_server_prompt(
                    str(interaction.guild.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = "伺服器預設"
            
            if success:
                embed = discord.Embed(
                    title="✅ 系統提示設定成功",
                    description=f"已成功設定{scope_text}的系統提示",
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
            
            # 取得有效提示
            prompt_data = self.manager.get_effective_prompt(
                str(channel.id),
                str(interaction.guild.id),
                None
            )
            
            # 建立 Embed
            embed = create_system_prompt_embed(prompt_data, channel)
            
            # 如果顯示繼承資訊
            if view_type == "inheritance":
                config = self.manager._load_guild_config(str(interaction.guild.id))
                system_prompts = config.get('system_prompts', {})
                
                # 檢查各層級的提示
                inheritance_info = []
                
                # YAML 基礎
                inheritance_info.append("🔹 YAML 基礎提示")
                
                # 伺服器級別
                server_level = system_prompts.get('server_level', {})
                if server_level.get('prompt'):
                    inheritance_info.append("🔸 伺服器預設提示")
                
                # 頻道級別
                channels = system_prompts.get('channels', {})
                if str(channel.id) in channels:
                    channel_config = channels[str(channel.id)]
                    if channel_config.get('prompt'):
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
                 timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.modules = modules
        self.selected_scope = None
        self.logger = logging.getLogger(__name__)
        
        # 先選擇範圍
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
                 guild: discord.Guild,
                 **kwargs):
        super().__init__(**kwargs)
        self.manager = manager
        self.scope = scope
        self.channel = channel
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        """選擇器回調"""
        try:
            selected_module = self.values[0]
            
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
            # 準備模組資料
            modules_data = {module_name: content}
            prompt_data = {'modules': modules_data}
            
            if self.scope == "channel" and self.channel:
                success = self.manager.set_channel_prompt(
                    str(self.guild.id),
                    str(self.channel.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = f"頻道 #{self.channel.name}"
            else:
                success = self.manager.set_server_prompt(
                    str(self.guild.id),
                    prompt_data,
                    str(interaction.user.id)
                )
                scope_text = "伺服器預設"
            
            if success:
                embed = discord.Embed(
                    title="✅ 模組設定成功",
                    description=f"已成功設定{scope_text}的 {module_name} 模組",
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
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
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
        
        try:
            # 權限檢查和確認文字
            if self.remove_type == "channel":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                confirm_text = f"確定要移除頻道 #{interaction.channel.name} 的系統提示嗎？"
            else:
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要移除伺服器預設系統提示嗎？"
            
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
            await confirm_view.wait()
            
            if confirm_view.result:
                if self.remove_type == "channel":
                    success = view.manager.remove_channel_prompt(
                        str(interaction.guild.id),
                        str(interaction.channel.id)
                    )
                    scope_text = f"頻道 #{interaction.channel.name}"
                else:
                    success = view.manager.remove_server_prompt(
                        str(interaction.guild.id)
                    )
                    scope_text = "伺服器預設"
                
                if success:
                    embed = discord.Embed(
                        title="✅ 移除成功",
                        description=f"已成功移除{scope_text}的系統提示",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
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
        
        try:
            # 權限檢查和確認文字
            if self.reset_type == "channel":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                confirm_text = f"確定要重置頻道 #{interaction.channel.name} 的系統提示嗎？"
            elif self.reset_type == "server":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要重置伺服器預設系統提示嗎？"
            else:  # all
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                confirm_text = "確定要重置所有系統提示設定嗎？\n⚠️ 此操作無法復原！"
            
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
            await confirm_view.wait()
            
            if confirm_view.result:
                if self.reset_type == "channel":
                    success = view.manager.remove_channel_prompt(
                        str(interaction.guild.id),
                        str(interaction.channel.id)
                    )
                    scope_text = f"頻道 #{interaction.channel.name}"
                elif self.reset_type == "server":
                    success = view.manager.remove_server_prompt(
                        str(interaction.guild.id)
                    )
                    scope_text = "伺服器預設"
                else:  # all
                    config = view.manager._get_default_config()
                    view.manager._save_guild_config(str(interaction.guild.id), config)
                    view.manager.clear_cache(str(interaction.guild.id))
                    success = True
                    scope_text = "所有"
                
                if success:
                    embed = discord.Embed(
                        title="✅ 重置成功",
                        description=f"已成功重置{scope_text}系統提示設定",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 重置失敗：{str(e)}", ephemeral=True
            )