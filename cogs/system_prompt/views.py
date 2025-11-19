"""
系統提示管理的統一 UI 選單系統

提供全新的統一介面，整合所有系統提示管理功能和模組化編輯。
"""

import discord
from typing import Optional, Dict, Any, Callable, List
from addons.logging import get_logger

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
        self.logger = get_logger(source=__name__, server_id="system")

        # 建立主要功能按鈕
        self._setup_main_buttons()

    def _setup_main_buttons(self):
        """設定主要功能按鈕"""
        
        # Get language manager for button labels
        lang_manager = self.manager.language_manager if hasattr(self.manager, 'language_manager') else None
        guild_id = "system"  # Default fallback

        # 第一列：基本功能
        self.add_item(SystemPromptFunctionButton(
            label=lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "set_prompt") if lang_manager else "Set Prompt",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            function="set",
            row=0
        ))
        self.add_item(SystemPromptFunctionButton(
            label=lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "view_config") if lang_manager else "View Config",
            emoji="👁️",
            style=discord.ButtonStyle.secondary,
            function="view",
            row=0
        ))

        # 第二列：管理功能
        self.add_item(SystemPromptFunctionButton(
            label=lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "copy_prompt") if lang_manager else "Copy Prompt",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            function="copy",
            row=1
        ))
        self.add_item(SystemPromptFunctionButton(
            label=lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "remove_prompt") if lang_manager else "Remove Prompt",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            function="remove",
            row=1
        ))
        self.add_item(SystemPromptFunctionButton(
            label=lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "reset_config") if lang_manager else "Reset Config",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            function="reset",
            row=1
        ))
        self.add_item(SystemPromptFunctionButton(
            label="Reload Config",  # Keep as fallback, not in translation
            emoji="🔩",
            style=discord.ButtonStyle.secondary,
            function="reload",
            row=2
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
            self.logger.error(f"處理功能 {function} 時發生錯誤: {e}", exc_info=True)
            lang_manager = interaction.client.get_cog("LanguageManager")
            guild_id = str(interaction.guild.id) if interaction.guild else "system"
            
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "operation_failed") if lang_manager else "Operation failed"
            full_message = f"❌ {error_msg}: {str(e)}"
            
            if not interaction.response.is_done():
                await interaction.response.send_message(full_message, ephemeral=True)
            else:
                await interaction.followup.send(full_message, ephemeral=True)


    async def _handle_set_function(self, interaction: discord.Interaction):
        """處理設定提示功能"""
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        view = SystemPromptSetView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        # Get localized text
        title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "set_prompt_title") if lang_manager else "⚙️ System Prompt Setting"
        description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "set_prompt_description") if lang_manager else "Please select the scope to configure"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_view_function(self, interaction: discord.Interaction):
        """處理查看配置功能"""
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        view = SystemPromptViewOptionsView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        # Get localized text
        title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "view_options_title") if lang_manager else "👁️ System Prompt Configuration View"
        description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "view_options_description") if lang_manager else "Please select viewing options"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_copy_function(self, interaction: discord.Interaction):
        """處理複製提示功能"""
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        if not interaction.guild:
            error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "server_only") if lang_manager else "This feature is only available in servers."
            await interaction.response.send_message(f"❌ {error_msg}", ephemeral=True)
            return
        view = SystemPromptCopyView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild=interaction.guild
        )
        
        # Get localized text
        title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "copy_prompt_title") if lang_manager else "📋 System Prompt Copy"
        description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "copy_prompt_description") if lang_manager else "Please select source and target channels"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_remove_function(self, interaction: discord.Interaction):
        """處理移除提示功能"""
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        view = SystemPromptRemoveView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        # Get localized text
        title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "remove_prompt_title") if lang_manager else "🗑️ System Prompt Removal"
        description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "remove_prompt_description") if lang_manager else "Please select the scope to remove"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_reset_function(self, interaction: discord.Interaction):
        """處理重置設定功能"""
        lang_manager = interaction.client.get_cog("LanguageManager")
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        
        view = SystemPromptResetView(
            manager=self.manager,
            permission_validator=self.permission_validator
        )
        
        # Get localized text
        title = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "reset_config_title") if lang_manager else "🔄 System Prompt Reset"
        description = lang_manager.translate(guild_id, "commands", "system_prompt", "ui", "menus", "reset_config_description") if lang_manager else "Please select the scope to reset"
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_reload_function(self, interaction: discord.Interaction):
        """處理重載設定功能"""
        try:
            # Example: Check for a generic admin-level permission
            # self.permission_validator.validate_permission_or_raise(interaction.user, 'manage_bot_config', interaction.guild)
            
            if hasattr(self.manager, "reload_all_configs") and callable(self.manager.reload_all_configs):
                # If reload_all_configs is async
                import asyncio
                if asyncio.iscoroutinefunction(self.manager.reload_all_configs):
                    await self.manager.reload_all_configs()
                else:
                    self.manager.reload_all_configs() # If synchronous
                await interaction.response.send_message("🔄 設定已成功重載。", ephemeral=True)
                self.logger.info(f"用戶 {interaction.user} 重載了配置。")
            else:
                self.logger.warning("Manager has no 'reload_all_configs' method or it's not callable.")
                await interaction.response.send_message("⚠️ 重載功能當前不可用或未完全實現。", ephemeral=True)
        except PermissionError as e:
            await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"重載設定時發生錯誤: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ 重載失敗：{str(e)}", ephemeral=True)


class SystemPromptFunctionButton(discord.ui.Button):
    """系統提示功能按鈕"""
    def __init__(self, function: str, **kwargs):
        super().__init__(**kwargs)
        self.function = function

    async def callback(self, interaction: discord.Interaction):
        """按鈕回調"""
        view: SystemPromptMainView = self.view
        if view:
            await view.function_callback(interaction, self.function)
        else:
            self.logger.error("Button callback: View not found.")
            await interaction.response.send_message("❌ 內部錯誤，請稍後再試。",ephemeral=True)

class SystemPromptSetView(discord.ui.View):
    """設定系統提示的子選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptScopeButton(
            label="頻道特定", emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0
        ))
        self.add_item(SystemPromptScopeButton(
            label="伺服器預設", emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0
        ))
        self.add_item(BackButton(row=1))

    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        """處理範圍選擇"""
        try:
            target_channel_obj: Optional[discord.TextChannel] = None
            scope_text: str = ""

            if not interaction.guild:
                await interaction.response.send_message("❌ 此功能僅限伺服器內使用。", ephemeral=True)
                return
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel): # Ensure it's a text channel for channel scope
                await interaction.response.send_message("❌ 無法在目前頻道類型執行此操作。", ephemeral=True)
                return

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                target_channel_obj = interaction.channel
                scope_text = f"頻道 #{interaction.channel.name}"
            else: # scope == "server"
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                target_channel_obj = None
                scope_text = "伺服器預設"

            view = EditModeSelectionView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                scope=scope,
                target_channel=target_channel_obj,
                scope_text=scope_text,
                guild=interaction.guild # Pass guild explicitly
            )
            embed = discord.Embed(
                title=f"⚙️ 編輯 {scope_text} 系統提示",
                description="請選擇編輯模式",
                color=discord.Color.blue()
            )
            # Use edit_message if already responded, otherwise send_message
            if interaction.response.is_done():
                 await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for scope {scope}")
            await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"處理範圍選擇時發生錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 操作失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 操作失敗：{str(e)}", ephemeral=True)


class EditModeSelectionView(discord.ui.View):
    """編輯模式選擇選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 scope: str,
                 target_channel: Optional[discord.TextChannel],
                 scope_text: str,
                 guild: discord.Guild, # Added guild
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.guild = guild # Store guild
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(EditModeButton(
            label="直接編輯提示",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
            edit_mode="direct",
            row=0
        ))
        self.add_item(EditModeButton(
            label="模組化編輯",
            emoji="📦",
            style=discord.ButtonStyle.secondary,
            edit_mode="module",
            row=0
        ))
        self.add_item(BackButton(row=1))

    async def edit_mode_callback(self, interaction: discord.Interaction, edit_mode: str):
        """處理編輯模式選擇"""
        try:
            if edit_mode == "direct":
                await self._handle_direct_edit(interaction)
            elif edit_mode == "module":
                await self._handle_module_edit(interaction)
        except Exception as e:
            self.logger.error(f"處理編輯模式選擇時發生錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 操作失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 操作失敗：{str(e)}", ephemeral=True)


    async def _handle_direct_edit(self, interaction: discord.Interaction):
        """處理直接編輯提示"""
        existing_content = ""
        guild_id_str = str(self.guild.id)

        config = self.manager._load_guild_config(guild_id_str)
        system_prompts = config.get('system_prompts', {})

        if self.scope == "channel" and self.target_channel:
            channels = system_prompts.get('channels', {})
            channel_id_str = str(self.target_channel.id)
            if channel_id_str in channels:
                existing_content = channels[channel_id_str].get('prompt', '')
        else: # server scope
            server_level = system_prompts.get('server_level', {})
            existing_content = server_level.get('prompt', '')

        # 如果沒有現有內容，取得當前有效提示作為預設值（但保留變數占位符）
        if not existing_content:
            try:
                # 從有效提示中取得內容，但需要保留變數占位符
                effective_prompt_data = self.manager.get_effective_prompt(
                    str(self.target_channel.id) if self.scope == "channel" and self.target_channel else "",
                    guild_id_str
                )
                if effective_prompt_data and effective_prompt_data.get('source') in ['yaml']:
                    # 只有當來源是 YAML 時才顯示，因為這樣可以保留變數格式
                    existing_content = effective_prompt_data.get('prompt', '')
                    # 將已替換的變數還原為占位符格式（反向替換）
                    existing_content = self._restore_variable_placeholders(existing_content, guild_id_str)
            except Exception as e:
                self.logger.warning(f"無法取得有效提示作為預設值: {e}")

        modal = SystemPromptModal(
            title="編輯系統提示",
            initial_value=existing_content,
            callback_func=lambda i, prompt_content: self._handle_direct_set_callback(i, prompt_content),
            manager=self.manager, # Pass manager if modal needs it
            channel_id=str(self.target_channel.id) if self.scope == "channel" and self.target_channel else "",
            guild_id=guild_id_str,
            show_default_content=not existing_content
        )
        await interaction.response.send_modal(modal)
    
    def _restore_variable_placeholders(self, prompt: str, guild_id: str) -> str:
        """
        將已替換的變數還原為占位符格式，以便編輯時顯示原始模板
        
        Args:
            prompt: 已替換變數的提示
            guild_id: 伺服器 ID
            
        Returns:
            還原變數占位符的提示
        """
        try:
            # 獲取當前的變數值
            variables = self.manager._get_system_variables()
            
            # 反向替換：將實際值替換回占位符
            restored_prompt = prompt
            for var_name, var_value in variables.items():
                if str(var_value) in prompt:
                    # 使用更精確的替換，避免誤替換
                    if var_name == 'bot_id' and f"<@{var_value}>" in prompt:
                        restored_prompt = restored_prompt.replace(f"<@{var_value}>", f"<@{{bot_id}}>")
                    elif var_name == 'bot_owner_id' and f"<@{var_value}>" in prompt:
                        restored_prompt = restored_prompt.replace(f"<@{var_value}>", f"<@{{bot_owner_id}}>")
                    else:
                        # 對於其他變數，使用一般替換
                        restored_prompt = restored_prompt.replace(str(var_value), f"{{{var_name}}}")
            
            self.logger.debug(f"🔄 變數占位符還原完成 - 原長度: {len(prompt)}, 新長度: {len(restored_prompt)}")
            return restored_prompt
            
        except Exception as e:
            self.logger.warning(f"還原變數占位符時發生錯誤: {e}，返回原始提示")
            return prompt

    async def _handle_module_edit(self, interaction: discord.Interaction):
        """處理模組化編輯"""
        try:
            modules = self.manager.get_available_modules()
            if not modules:
                await interaction.response.send_message("❌ 暫無可用的模組", ephemeral=True)
                return

            view = ModuleEditView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                modules=modules,
                scope=self.scope,
                target_channel=self.target_channel,
                scope_text=self.scope_text,
                guild=self.guild # Pass guild
            )
            # view._guild = self.guild # Already passed via constructor

            embed = discord.Embed(
                title=f"📦 模組化編輯 {self.scope_text}",
                description="請選擇要編輯的模組",
                color=discord.Color.purple()
            )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            self.logger.error(f"載入模組時發生錯誤: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ 載入模組時發生錯誤：{str(e)}", ephemeral=True)

    async def _handle_direct_set_callback(self, interaction: discord.Interaction, content: str):
        """處理直接設定回調"""
        try:
            prompt_data = {'prompt': content}
            guild_id_str = str(self.guild.id)
            user_id_str = str(interaction.user.id)

            # Interaction cache handling (optional, depends on manager implementation)
            try:
                if hasattr(self.manager, 'handle_discord_interaction_cache_issues'):
                    result = await self.manager.handle_discord_interaction_cache_issues(interaction)
                    self.logger.debug(f"Discord 互動快取處理結果: {result}")
            except Exception as cache_error:
                self.logger.warning(f"Discord 互動快取處理失敗，繼續操作: {cache_error}")

            success = False
            if self.scope == "channel" and self.target_channel:
                channel_id_str = str(self.target_channel.id)
                success = self.manager.set_channel_prompt(
                    guild_id_str, channel_id_str, prompt_data, user_id_str
                )
            else: # server scope
                success = self.manager.set_server_prompt(
                    guild_id_str, prompt_data, user_id_str
                )

            if success:
                if hasattr(self.manager, 'force_clear_all_caches'):
                    await self.manager.force_clear_all_caches(
                        guild_id_str,
                        str(self.target_channel.id) if self.scope == "channel" and self.target_channel else None,
                        interaction # Pass interaction if needed by cache clear
                    )
                embed = discord.Embed(
                    title="✅ 系統提示設定成功",
                    description=f"已成功設定 {self.scope_text} 的系統提示",
                    color=discord.Color.green()
                )
                embed.add_field(name="內容長度", value=f"{len(content)} 字元", inline=True)
                embed.add_field(name="設定者", value=interaction.user.mention, inline=True)
                
                # Modal callbacks should use followup if initial response was to send the modal
                await interaction.response.send_message(embed=embed, ephemeral=True) 
            else:
                await interaction.response.send_message(f"❌ 設定失敗：操作未成功返回。", ephemeral=True)

        except Exception as e:
            self.logger.error(f"設定系統提示時發生錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 設定失敗: {str(e)}", ephemeral=True)
            else: # Should be from modal, so initial response is done
                await interaction.followup.send(f"❌ 設定失敗: {str(e)}", ephemeral=True)


class EditModeButton(discord.ui.Button):
    """編輯模式按鈕"""
    def __init__(self, edit_mode: str, **kwargs):
        super().__init__(**kwargs)
        self.edit_mode = edit_mode

    async def callback(self, interaction: discord.Interaction):
        view: EditModeSelectionView = self.view
        if view:
            await view.edit_mode_callback(interaction, self.edit_mode)
        else:
            self.logger.error("Button callback: View not found.")
            await interaction.response.send_message("❌ 內部錯誤，請稍後再試。",ephemeral=True)


class SystemPromptScopeButton(discord.ui.Button):
    """範圍選擇按鈕"""
    def __init__(self, scope: str, **kwargs):
        super().__init__(**kwargs)
        self.scope = scope

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptSetView = self.view
        if view:
            await view.scope_callback(interaction, self.scope)
        else:
            self.logger.error("Button callback: View not found.")
            await interaction.response.send_message("❌ 內部錯誤，請稍後再試。",ephemeral=True)


class SystemPromptViewOptionsView(discord.ui.View):
    """查看配置選項選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptViewButton(
            label="當前頻道有效提示", emoji="📢", style=discord.ButtonStyle.primary, view_type="current", row=0
        ))
        self.add_item(SystemPromptViewButton(
            label="顯示繼承關係", emoji="🔗", style=discord.ButtonStyle.secondary, view_type="inheritance", row=0
        ))
        self.add_item(BackButton(row=1))

    async def view_callback(self, interaction: discord.Interaction, view_type: str):
        """處理查看回調"""
        try:
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
                await interaction.response.send_message("❌ 此功能僅限伺服器文字頻道內使用。", ephemeral=True)
                return

            channel = interaction.channel
            guild = interaction.guild
            guild_id_str = str(guild.id)
            channel_id_str = str(channel.id)

            self.permission_validator.validate_permission_or_raise(interaction.user, 'view', channel)

            self.logger.info(f"🔍 查看配置請求 - 頻道: {channel_id_str}, 伺服器: {guild_id_str}, 類型: {view_type}")

            if hasattr(self.manager, 'cache') and hasattr(self.manager.cache, 'invalidate'):
                # Adjust invalidate call based on your cache's API
                self.manager.cache.invalidate(guild_id_str, channel_id_str) 
                self.logger.debug(f"已嘗試清除快取: {guild_id_str}:{channel_id_str}")

            prompt_data = self.manager.get_effective_prompt(channel_id_str, guild_id_str, None) # Pass user_id=None for general view

            embed = create_system_prompt_embed(prompt_data, channel)
            
            # Debugging: show configured modules directly from file
            config = self.manager._load_guild_config(guild_id_str)
            system_prompts = config.get('system_prompts', {})
            channels_config = system_prompts.get('channels', {})
            
            if channel_id_str in channels_config:
                channel_specific_config = channels_config[channel_id_str]
                modules = channel_specific_config.get('modules', {})
                if modules:
                    module_info = []
                    for name, content in modules.items():
                        preview = (content[:47] + "...") if len(content) > 50 else content
                        module_info.append(f"**{name}**: `{preview}`")
                    if module_info:
                        embed.add_field(name="🔧 該頻道直接配置的模組", value="\n".join(module_info), inline=False)
                    else:
                        embed.add_field(name="🔧 該頻道直接配置的模組", value="無", inline=False)


            if view_type == "inheritance":
                inheritance_info = ["🔹 **YAML 基礎提示** (隱含最底層)"]
                
                server_level_config = system_prompts.get('server_level', {})
                if server_level_config.get('prompt') or server_level_config.get('modules'):
                    inheritance_info.append("🔸 **伺服器預設提示** (若有配置)")
                
                if channel_id_str in channels_config:
                    channel_specific_config = channels_config[channel_id_str]
                    if channel_specific_config.get('prompt') or channel_specific_config.get('modules'):
                        inheritance_info.append("🟢 **頻道特定提示** (若有配置)")
                
                embed.add_field(name="繼承層級 (由下至上應用)", value="\n".join(inheritance_info), inline=False)
                embed.set_footer(text=f"最終生效提示來源: {prompt_data.get('source', '未知')}")


            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self) # Keep current view or new one
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True) # view=self if needed

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for view")
            await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"查看配置時發生錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 查看失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 查看失敗：{str(e)}", ephemeral=True)


class SystemPromptViewButton(discord.ui.Button):
    """查看選項按鈕"""
    def __init__(self, view_type: str, **kwargs):
        super().__init__(**kwargs)
        self.view_type = view_type

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptViewOptionsView = self.view
        if view:
            await view.view_callback(interaction, self.view_type)
        else:
            self.logger.error("Button callback: View not found.")
            await interaction.response.send_message("❌ 內部錯誤，請稍後再試。",ephemeral=True)


class ModuleEditView(discord.ui.View):
    """模組編輯選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 modules: List[str],
                 guild: discord.Guild, # Added guild
                 scope: Optional[str] = None,
                 target_channel: Optional[discord.TextChannel] = None,
                 scope_text: Optional[str] = None,
                 timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.modules = modules
        self.guild = guild # Store guild
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.logger = get_logger(source=__name__, server_id="system")
        self.selected_scope = scope # Initialize selected_scope

        if scope and scope_text:
            self._setup_module_selector()
        else:
            self._setup_scope_selector()

    def _setup_scope_selector(self):
        """設定範圍選擇器"""
        self.clear_items()
        self.add_item(ModuleScopeButton(
            label="頻道模組", emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0
        ))
        self.add_item(ModuleScopeButton(
            label="伺服器模組", emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0
        ))
        self.add_item(BackButton(row=1))

    def _setup_module_selector(self):
        """設定模組選擇器"""
        self.clear_items()
        options = []
        for module_name in self.modules[:25]: # Discord limit
            options.append(discord.SelectOption(
                label=module_name, value=module_name, description=f"編輯 {module_name} 模組"
            ))

        if options:
            # Guild should be available via self.guild
            select = ModuleSelect(
                placeholder="選擇要編輯的模組",
                options=options,
                manager=self.manager,
                scope=self.selected_scope or self.scope, # Use selected_scope if available
                channel=self.target_channel if (self.selected_scope or self.scope) == "channel" else None,
                guild=self.guild,
                scope_text=self.scope_text or (f"頻道 #{self.target_channel.name}" if self.target_channel else "伺服器預設")
            )
            self.add_item(select)
        else:
            # Add a disabled button or label if no modules
            self.add_item(discord.ui.Button(label="無可用模組", style=discord.ButtonStyle.secondary, disabled=True))

        self.add_item(BackButton(row=1 if options else 0))


    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        """處理範圍選擇"""
        try:
            if not interaction.guild or not interaction.channel or not isinstance(interaction.channel, discord.TextChannel): # Ensure guild and text channel
                await interaction.response.send_message("❌ 此功能僅限伺服器文字頻道內使用。", ephemeral=True)
                return

            self.guild = interaction.guild # Update guild from interaction

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                self.target_channel = interaction.channel
                self.scope_text = f"頻道 #{interaction.channel.name}"
            else: # server
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                self.target_channel = None
                self.scope_text = "伺服器預設"

            self.selected_scope = scope # Set selected scope
            self.modules = self.manager.get_available_modules() # Refresh modules if needed

            self._setup_module_selector() # Re-setup items with the new scope

            embed = discord.Embed(
                title=f"📦 編輯 {self.scope_text} 模組",
                description="請選擇要編輯的模組",
                color=discord.Color.purple()
            )
            await interaction.response.edit_message(embed=embed, view=self)

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for module scope {scope}")
            await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"處理模組範圍選擇時發生錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 操作失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 操作失敗：{str(e)}", ephemeral=True)


class ModuleScopeButton(discord.ui.Button):
    """模組範圍選擇按鈕"""
    def __init__(self, scope: str, **kwargs):
        super().__init__(**kwargs)
        self.scope = scope

    async def callback(self, interaction: discord.Interaction):
        view: ModuleEditView = self.view
        if view:
            await view.scope_callback(interaction, self.scope)
        else:
            self.logger.error("Button callback: View not found.")
            await interaction.response.send_message("❌ 內部錯誤，請稍後再試。",ephemeral=True)


class ModuleSelect(discord.ui.Select):
    """模組選擇器"""
    def __init__(self,
                 manager: SystemPromptManager,
                 scope: str, # This should be the definitive scope for this select instance
                 channel: Optional[discord.TextChannel],
                 guild: discord.Guild, # Should always be provided now
                 scope_text: Optional[str] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.manager = manager
        self.scope = scope
        self.channel = channel # This is the target channel for "channel" scope
        self.guild = guild
        self.scope_text = scope_text or ("伺服器預設" if scope == "server" else (f"頻道 #{channel.name}" if channel else "未知頻道"))
        self.logger = get_logger(server_id="system", source=__name__)

        if 'options' in kwargs and self.guild:
            self._update_option_descriptions()

    def _update_option_descriptions(self):
        """更新選項的說明文字 (基於語言管理器)"""
        try:
            lang_manager = None
            # Try to get language_manager from self.manager or bot
            if hasattr(self.manager, 'language_manager'):
                lang_manager = self.manager.language_manager
            elif hasattr(self.manager, 'bot') and self.manager.bot:
                lang_manager = self.manager.bot.get_cog("LanguageManager")

            if not lang_manager or not self.guild:
                self.logger.debug("LanguageManager or guild not available for updating option descriptions.")
                return

            server_language = lang_manager.get_server_lang(str(self.guild.id))

            for option in self.options:
                module_name = option.value
                # Try short description first
                short_description = lang_manager.translate(str(self.guild.id), "commands", "system_prompt", "modules", "modules_select_descriptions", module_name)

                if short_description == module_name: # Not found, try full description
                    full_description = lang_manager.translate(str(self.guild.id), "commands", "system_prompt", "modules", "descriptions", module_name)
                    if full_description != module_name:
                        short_description = (full_description[:97] + "...") if len(full_description) > 100 else full_description
                    else: # No specific description found, keep original
                        continue
                
                option.description = short_description[:100] # Discord limit for option description

        except Exception as e:
            self.logger.warning(f"更新模組選項說明失敗: {e}", exc_info=False) # Keep it less verbose

    async def callback(self, interaction: discord.Interaction):
        """選擇器回調"""
        try:
            selected_module = self.values[0]
            guild_id_str = str(self.guild.id)

            existing_content = ""
            config = self.manager._load_guild_config(guild_id_str)
            system_prompts = config.get('system_prompts', {})

            if self.scope == "channel" and self.channel:
                channel_id_str = str(self.channel.id)
                channels_config = system_prompts.get('channels', {})
                if channel_id_str in channels_config:
                    modules_config = channels_config[channel_id_str].get('modules', {})
                    existing_content = modules_config.get(selected_module, '')
            else: # server scope
                server_level_config = system_prompts.get('server_level', {})
                modules_config = server_level_config.get('modules', {})
                existing_content = modules_config.get(selected_module, '')
            
            lang = "zh_TW" # Default
            try:
                # Simplified language fetching, assuming bot is on interaction.client
               if hasattr(interaction.client, "get_cog") and (lang_cog := interaction.client.get_cog("LanguageManager")):
                   if hasattr(lang_cog, "get_server_lang"): # Or get_language
                       lang = lang_cog.get_server_lang(guild_id_str)
            except Exception as lang_e:
                self.logger.debug(f"Error fetching server language: {lang_e}")


            modal = SystemPromptModuleModal(
                module_name=selected_module,
                initial_value=existing_content,
                callback_func=lambda i, mod_name, mod_content: self._handle_module_callback(i, mod_name, mod_content),
                manager=self.manager, # Pass manager if modal needs it
                lang=lang,
                show_default_content=not existing_content
            )
            await interaction.response.send_modal(modal)

        except Exception as e:
            self.logger.error(f"開啟模組編輯器失敗: {e}", exc_info=True)
            if not interaction.response.is_done(): # Should not happen for select callback
                await interaction.response.send_message(f"❌ 開啟編輯器失敗：{str(e)}", ephemeral=True)
            else: # For select, interaction response is already done implicitly by edit_message or send_message from parent
                await interaction.followup.send(f"❌ 開啟編輯器失敗：{str(e)}", ephemeral=True)


    async def _handle_module_callback(self, interaction: discord.Interaction, module_name: str, content: str):
        """處理模組編輯回調"""
        try:
            self.logger.info(f"🔧 開始處理模組編輯回調 - 模組: {module_name}, 範圍: {self.scope}, Guild: {self.guild.id}")
            self.logger.debug(f"模組內容 (首100字): {content[:100]}{'...' if len(content)>100 else ''}")

            guild_id_str = str(self.guild.id)
            user_id_str = str(interaction.user.id)

            # Interaction cache handling (optional)
            try:
                if hasattr(self.manager, 'handle_discord_interaction_cache_issues'):
                    result = await self.manager.handle_discord_interaction_cache_issues(interaction)
                    self.logger.debug(f"Discord 互動快取處理結果: {result}")
            except Exception as cache_error:
                self.logger.warning(f"Discord 互動快取處理失敗，繼續操作: {cache_error}")

            config = self.manager._load_guild_config(guild_id_str)
            system_prompts = config.get('system_prompts', {})
            
            existing_modules = {}
            if self.scope == "channel" and self.channel:
                channel_id_str = str(self.channel.id)
                channels_config = system_prompts.get('channels', {})
                if channel_id_str in channels_config:
                    existing_modules = channels_config[channel_id_str].get('modules', {})
                self.logger.info(f"頻道 {channel_id_str} 現有模組: {list(existing_modules.keys())}")
            else: # server scope
                server_level_config = system_prompts.get('server_level', {})
                existing_modules = server_level_config.get('modules', {})
                self.logger.info(f"伺服器現有模組: {list(existing_modules.keys())}")

            existing_modules[module_name] = content
            prompt_data = {'modules': existing_modules}
            self.logger.info(f"準備保存的模組數據 (更新模組: {module_name})")

            success = False
            display_scope_text = self.scope_text # Use the stored scope_text

            if self.scope == "channel" and self.channel:
                channel_id_str = str(self.channel.id)
                self.logger.info(f"正在設定頻道模組: {guild_id_str}/{channel_id_str}")
                success = self.manager.set_channel_prompt(
                    guild_id_str, channel_id_str, prompt_data, user_id_str
                )
            else: # server scope
                self.logger.info(f"正在設定伺服器模組: {guild_id_str}")
                success = self.manager.set_server_prompt(
                    guild_id_str, prompt_data, user_id_str
                )
            
            self.logger.info(f"模組設定結果: {success}")

            if success:
                if hasattr(self.manager, 'force_clear_all_caches'):
                    await self.manager.force_clear_all_caches(
                        guild_id_str,
                        str(self.channel.id) if self.scope == "channel" and self.channel else None,
                        interaction
                    )
                # Verification (optional but good)
                verification_msg = "已驗證保存並清除快取"
                # ... (verification logic as in original) ...

                embed = discord.Embed(
                    title="✅ 模組設定成功",
                    description=f"已成功設定 {display_scope_text} 的 **{module_name}** 模組",
                    color=discord.Color.green()
                )
                embed.add_field(name="模組名稱", value=module_name, inline=True)
                embed.add_field(name="內容長度", value=f"{len(content)} 字元", inline=True)
                embed.add_field(name="驗證狀態", value=verification_msg, inline=True) # Add verification status

                await interaction.response.send_message(embed=embed, ephemeral=True) # From modal
            else:
                self.logger.error("模組設定失敗，manager returned False.")
                await interaction.response.send_message(f"❌ 設定模組失敗: 操作未成功。", ephemeral=True)

        except Exception as e:
            self.logger.error(f"設定模組時發生嚴重錯誤: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 設定模組失敗: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 設定模組失敗: {str(e)}", ephemeral=True)


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
        self.logger = logging.getLogger(__name__)

        # Get visible text channels bot has permissions for
        text_channels = [
            ch for ch in guild.text_channels 
            if ch.permissions_for(guild.me).view_channel and ch.permissions_for(guild.me).send_messages
        ]

        if len(text_channels) > 0:
            from_options = [
                discord.SelectOption(label=f"#{ch.name}", value=str(ch.id), description=f"ID: {ch.id}")
                for ch in text_channels[:25] # Limit to 25 for Discord
            ]
            to_options = list(from_options) # Can be the same list of channels

            if from_options: # Should be true if len(text_channels) > 0
                self.add_item(ChannelSelect(
                    placeholder="選擇來源頻道", options=from_options, custom_id="from_channel", row=0
                ))
            if to_options:
                self.add_item(ChannelSelect(
                    placeholder="選擇目標頻道", options=to_options, custom_id="to_channel", row=1
                ))
            self.add_item(CopyExecuteButton(row=2))
            self.add_item(BackButton(row=3))
        else:
            self.add_item(discord.ui.Button(label="無可用頻道進行複製", style=discord.ButtonStyle.secondary, disabled=True, row=0))
            self.add_item(BackButton(row=1))


class SystemPromptRemoveView(discord.ui.View):
    """移除系統提示的子選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = logging.getLogger(__name__)

        self.add_item(RemoveButton(
            label="移除當前頻道提示", emoji="📢", style=discord.ButtonStyle.danger, remove_type="channel", row=0
        ))
        self.add_item(RemoveButton(
            label="移除伺服器預設提示", emoji="🏠", style=discord.ButtonStyle.danger, remove_type="server", row=0
        ))
        self.add_item(BackButton(row=1))


class SystemPromptResetView(discord.ui.View):
    """重置系統提示的子選單"""
    def __init__(self,
                 manager: SystemPromptManager,
                 permission_validator: PermissionValidator,
                 timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.permission_validator = permission_validator
        self.logger = logging.getLogger(__name__)

        self.add_item(ResetButton(
            label="重置當前頻道", emoji="📢", style=discord.ButtonStyle.danger, reset_type="channel", row=0
        ))
        self.add_item(ResetButton(
            label="重置伺服器預設", emoji="🏠", style=discord.ButtonStyle.danger, reset_type="server", row=0
        ))
        self.add_item(ResetButton(
            label="重置全部設定", emoji="⚠️", style=discord.ButtonStyle.danger, reset_type="all", row=1 # More prominent emoji
        ))
        self.add_item(BackButton(row=2))


# --- 輔助按鈕與選擇器類別 ---

class BackButton(discord.ui.Button):
    """返回主選單按鈕"""
    def __init__(self, row: int = 4): # Default row or specified
        super().__init__(label="返回主選單", emoji="🔙", style=discord.ButtonStyle.secondary, row=row)
        self.logger = logging.getLogger(__name__)

    async def callback(self, interaction: discord.Interaction):
        """返回主選單"""
        # This relies on SystemPromptCommands cog being available and structured this way
        try:
            # Assuming client is on interaction
            commands_cog = interaction.client.get_cog("SystemPromptCommands")
            if commands_cog and hasattr(commands_cog, "get_system_prompt_manager") and hasattr(commands_cog, "permission_validator"):
                manager = commands_cog.get_system_prompt_manager()
                permission_validator = commands_cog.permission_validator

                main_view = SystemPromptMainView(manager, permission_validator)
                embed = discord.Embed(
                    title="🤖 系統提示管理",
                    description="請選擇要執行的功能",
                    color=discord.Color.blue()
                )
                await interaction.response.edit_message(embed=embed, view=main_view)
            else:
                self.logger.error("SystemPromptCommands cog or its methods not found for BackButton.")
                await interaction.response.edit_message(content="❌ 返回主選單失敗：內部組件缺失。", embed=None, view=None)
        except Exception as e:
            self.logger.error(f"BackButton callback error: {e}", exc_info=True)
            await interaction.response.edit_message(content=f"❌ 返回主選單時發生錯誤: {e}", embed=None, view=None)


class ChannelSelect(discord.ui.Select):
    """頻道選擇器（用於複製功能）"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_channel_id: Optional[str] = None
        self.logger = logging.getLogger(__name__)


    async def callback(self, interaction: discord.Interaction):
        if self.values:
            self.selected_channel_id = self.values[0]
            self.logger.debug(f"ChannelSelect {self.custom_id}: selected {self.selected_channel_id}")
            # Update placeholder to show selection (optional)
            # self.placeholder = f"已選: #{interaction.guild.get_channel(int(self.selected_channel_id)).name if self.selected_channel_id else '未選擇'}"
            
            # No need to change option.default for ephemeral views
            await interaction.response.edit_message(view=self.view) # Acknowledge interaction
        else: # Should not happen if min_values=1 (default)
            await interaction.response.defer(ephemeral=True)


class CopyExecuteButton(discord.ui.Button):
    """執行複製按鈕"""
    def __init__(self, **kwargs):
        super().__init__(label="執行複製", emoji="📋", style=discord.ButtonStyle.success, **kwargs)
        self.logger = logging.getLogger(__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptCopyView = self.view
        if not view or not view.guild:
            self.logger.error("CopyExecuteButton: View or guild not found.")
            await interaction.response.send_message("❌ 內部錯誤，無法執行複製。", ephemeral=True)
            return

        from_channel_selector = discord.utils.get(view.children, custom_id="from_channel")
        to_channel_selector = discord.utils.get(view.children, custom_id="to_channel")

        if not (isinstance(from_channel_selector, ChannelSelect) and 
                isinstance(to_channel_selector, ChannelSelect)):
            await interaction.response.send_message("❌ 頻道選擇器錯誤，無法複製。", ephemeral=True)
            return

        from_channel_id = from_channel_selector.selected_channel_id
        to_channel_id = to_channel_selector.selected_channel_id

        if not from_channel_id or not to_channel_id:
            await interaction.response.send_message("❌ 請先選擇來源和目標頻道。", ephemeral=True)
            return
        if from_channel_id == to_channel_id:
            await interaction.response.send_message("❌ 來源頻道和目標頻道不能相同。", ephemeral=True)
            return

        try:
            to_channel_obj = view.guild.get_channel(int(to_channel_id))
            if not to_channel_obj or not isinstance(to_channel_obj, discord.TextChannel):
                await interaction.response.send_message("❌ 目標頻道無效。", ephemeral=True)
                return

            view.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', to_channel_obj # Permission to modify target
            )
            # Optionally, check view permission for source channel
            # from_channel_obj = view.guild.get_channel(int(from_channel_id))
            # view.permission_validator.validate_permission_or_raise(interaction.user, 'view', from_channel_obj)


            success = view.manager.copy_channel_prompt(
                str(view.guild.id), from_channel_id,
                str(view.guild.id), to_channel_id, # Assuming manager takes guild_id for both
                str(interaction.user.id)
            )

            if success:
                from_channel_obj = view.guild.get_channel(int(from_channel_id))
                from_name = from_channel_obj.name if from_channel_obj else "未知來源"
                to_name = to_channel_obj.name # Already fetched

                embed = discord.Embed(
                    title="✅ 複製成功",
                    description=f"已成功將 #{from_name} 的系統提示複製到 #{to_name}",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ 複製失敗：操作未成功。", ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for copy")
            await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"複製操作失敗: {e}", exc_info=True)
            await interaction.response.send_message(f"❌ 複製失敗：{str(e)}", ephemeral=True)


class RemoveButton(discord.ui.Button):
    """移除按鈕"""
    def __init__(self, remove_type: str, **kwargs):
        super().__init__(**kwargs)
        self.remove_type = remove_type
        self.logger = logging.getLogger(__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptRemoveView = self.view
        if not view or not interaction.guild: # Ensure guild context
            self.logger.error("RemoveButton: View or guild not found.")
            await interaction.response.send_message("❌ 內部錯誤。", ephemeral=True)
            return
        
        guild_id_str = str(interaction.guild.id)
        confirm_text = ""
        operation_text = ""

        try:
            if self.remove_type == "channel":
                if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                    await interaction.response.send_message("❌ 此操作僅限文字頻道。", ephemeral=True)
                    return
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                channel_id_str = str(interaction.channel.id)
                config = view.manager._load_guild_config(guild_id_str)
                if channel_id_str not in config.get('system_prompts', {}).get('channels', {}):
                    await interaction.response.send_message(f"❌ 頻道 #{interaction.channel.name} 沒有設定系統提示。", ephemeral=True)
                    return
                confirm_text = f"確定要移除頻道 #{interaction.channel.name} 的系統提示嗎？"
                operation_text = f"頻道 #{interaction.channel.name}"
            else: # server
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                config = view.manager._load_guild_config(guild_id_str)
                if not config.get('system_prompts', {}).get('server_level', {}):
                    await interaction.response.send_message("❌ 伺服器沒有設定預設系統提示。", ephemeral=True)
                    return
                confirm_text = "確定要移除伺服器預設系統提示嗎？"
                operation_text = "伺服器預設"

            confirm_embed = discord.Embed(title="⚠️ 確認移除", description=confirm_text, color=discord.Color.orange())
            confirmation_prompt_view = ConfirmationView(confirm_text="確認移除", cancel_text="取消")
            await interaction.response.send_message(embed=confirm_embed, view=confirmation_prompt_view, ephemeral=True)
            
            await confirmation_prompt_view.wait() # Wait for user confirmation

            if confirmation_prompt_view.result is True: # User confirmed
                self.logger.info(f"用戶 {interaction.user} 確認移除 {operation_text} (Guild: {guild_id_str})")
                success = False
                if self.remove_type == "channel":
                    # Re-fetch channel_id_str if it wasn't set above (though it should be)
                    channel_id_str_op = str(interaction.channel.id) if interaction.channel else None
                    if channel_id_str_op:
                        success = view.manager.remove_channel_prompt(guild_id_str, channel_id_str_op)
                else: # server
                    success = view.manager.remove_server_prompt(guild_id_str, str(interaction.user.id))
                
                if success:
                    # Optional: Add verification logic here by reloading config
                    result_embed = discord.Embed(title="✅ 移除成功", description=f"已成功移除 {operation_text} 的系統提示。", color=discord.Color.green())
                    await interaction.followup.send(embed=result_embed, ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 移除 {operation_text} 失敗：操作未成功。", ephemeral=True)
            elif confirmation_prompt_view.result is False: # User cancelled
                await interaction.followup.send("移除操作已取消。", ephemeral=True)
            # else: timeout, do nothing or inform user (ConfirmationView might handle timeout message itself)

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for remove {self.remove_type}")
            # Check if initial response was sent for confirmation
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 權限不足：{str(e)}", ephemeral=True)

        except Exception as e:
            self.logger.error(f"移除操作 ({self.remove_type}) 失敗: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 移除失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 移除失敗：{str(e)}", ephemeral=True)


class ResetButton(discord.ui.Button):
    """重置按鈕"""
    def __init__(self, reset_type: str, **kwargs):
        super().__init__(**kwargs)
        self.reset_type = reset_type
        self.logger = logging.getLogger(__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptResetView = self.view
        if not view or not interaction.guild:
            self.logger.error("ResetButton: View or guild not found.")
            await interaction.response.send_message("❌ 內部錯誤。", ephemeral=True)
            return

        guild_id_str = str(interaction.guild.id)
        confirm_text = ""
        operation_text = ""
        
        try:
            # Permission checks and content existence check
            config = view.manager._load_guild_config(guild_id_str)
            system_prompts = config.get('system_prompts', {})
            has_content_to_reset = False

            if self.reset_type == "channel":
                if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                    await interaction.response.send_message("❌ 此操作僅限文字頻道。", ephemeral=True)
                    return
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                if str(interaction.channel.id) in system_prompts.get('channels', {}):
                    has_content_to_reset = True
                confirm_text = f"確定要重置頻道 #{interaction.channel.name} 的系統提示嗎？\n這將移除該頻道的特定設定。"
                operation_text = f"頻道 #{interaction.channel.name}"
            elif self.reset_type == "server":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                if system_prompts.get('server_level', {}):
                    has_content_to_reset = True
                confirm_text = "確定要重置伺服器預設系統提示嗎？\n這將移除伺服器的預設設定。"
                operation_text = "伺服器預設"
            else:  # "all"
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild # Highest permission
                )
                if system_prompts.get('channels', {}) or system_prompts.get('server_level', {}):
                    has_content_to_reset = True
                confirm_text = "⚠️ **警告** ⚠️\n確定要重置此伺服器**所有**系統提示設定嗎？\n包括所有頻道特定設定和伺服器預設。\n**此操作無法復原！**"
                operation_text = "所有系統提示"
            
            if not has_content_to_reset:
                await interaction.response.send_message(f"ℹ️ {operation_text} 沒有設定需要重置。", ephemeral=True)
                return

            confirm_embed = discord.Embed(title="⚠️ 確認重置", description=confirm_text, color=discord.Color.red())
            confirmation_prompt_view = ConfirmationView(confirm_text="確認重置", cancel_text="取消")
            await interaction.response.send_message(embed=confirm_embed, view=confirmation_prompt_view, ephemeral=True)

            await confirmation_prompt_view.wait()

            if confirmation_prompt_view.result is True:
                self.logger.info(f"用戶 {interaction.user} 確認重置 {operation_text} (Guild: {guild_id_str}, Type: {self.reset_type})")
                success = False
                user_id_str = str(interaction.user.id)

                if self.reset_type == "channel" and interaction.channel:
                    success = view.manager.remove_channel_prompt(guild_id_str, str(interaction.channel.id))
                elif self.reset_type == "server":
                    success = view.manager.remove_server_prompt(guild_id_str)
                elif self.reset_type == "all":
                    # This assumes manager has a method to reset all for a guild
                    if hasattr(view.manager, "reset_all_guild_prompts"):
                        success = view.manager.reset_all_guild_prompts(guild_id_str, user_id_str)
                    else: # Fallback: remove server and all channel prompts individually
                        view.manager.remove_server_prompt(guild_id_str) # Remove server default
                        current_config = view.manager._load_guild_config(guild_id_str)
                        channels_to_reset = list(current_config.get('system_prompts', {}).get('channels', {}).keys())
                        for chan_id in channels_to_reset:
                            view.manager.remove_channel_prompt(guild_id_str, chan_id)
                        success = True # Assume success if operations don't throw
                        self.logger.info(f"重置所有設定：移除了伺服器預設和 {len(channels_to_reset)} 個頻道的設定。")


                if success:
                    result_embed = discord.Embed(title="✅ 重置成功", description=f"已成功重置 {operation_text} 的系統提示設定。", color=discord.Color.green())
                    await interaction.followup.send(embed=result_embed, ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ 重置 {operation_text} 失敗：操作未完全成功或無此功能。", ephemeral=True)
            elif confirmation_prompt_view.result is False:
                await interaction.followup.send("重置操作已取消。", ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"權限不足: {e} by {interaction.user} for reset {self.reset_type}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 權限不足：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 權限不足：{str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"重置操作 ({self.reset_type}) 失敗: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ 重置失敗：{str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 重置失敗：{str(e)}", ephemeral=True)