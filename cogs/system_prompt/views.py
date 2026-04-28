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


# ─── Translation helpers ──────────────────────────────────────────────────────

def _ti(interaction: discord.Interaction, *keys: str, fallback: str = "") -> str:
    """Translate a key using the guild language from an interaction context.

    Falls back to ``fallback`` (or the last key segment) when LanguageManager
    is unavailable or the key is missing.
    """
    guild_id = str(interaction.guild.id) if interaction.guild else "system"
    try:
        lm = interaction.client.get_cog("LanguageManager") if interaction.client else None
        if lm:
            return lm.translate(guild_id, *keys)
    except Exception:
        pass
    return fallback or (keys[-1] if keys else "")


class LocalizedView(discord.ui.View):
    """Base class for all system-prompt views.

    Provides :meth:`_t` for translating strings at construction time using
    the server's configured language.
    """

    def __init__(
        self,
        manager: "SystemPromptManager",
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.guild_id = guild_id
        self._bot = manager.bot

    def _t(self, *keys: str, fallback: str = "") -> str:
        """Translate *keys* using the guild's language.

        Falls back to ``fallback`` (or the last key segment) when
        LanguageManager is unavailable or the key is missing.
        """
        try:
            lm = self._bot.get_cog("LanguageManager") if self._bot else None
            if lm:
                return lm.translate(self.guild_id, *keys)
        except Exception:
            pass
        return fallback or (keys[-1] if keys else "")


class SystemPromptMainView(LocalizedView):
    """系統提示管理主選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")
        self._setup_main_buttons()

    def _setup_main_buttons(self):
        """設定主要功能按鈕"""
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Set Prompt"),
            emoji="✏️", style=discord.ButtonStyle.primary, function="set", row=0,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "view_config", fallback="View Config"),
            emoji="👁️", style=discord.ButtonStyle.secondary, function="view", row=0,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "copy_prompt", fallback="Copy Prompt"),
            emoji="📋", style=discord.ButtonStyle.secondary, function="copy", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_prompt", fallback="Remove Prompt"),
            emoji="🗑️", style=discord.ButtonStyle.danger, function="remove", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_config", fallback="Reset Config"),
            emoji="🔄", style=discord.ButtonStyle.danger, function="reset", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reload_config", fallback="Reload Config"),
            emoji="🔩", style=discord.ButtonStyle.secondary, function="reload", row=2,
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
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            full_message = f"❌ {err}: {str(e)}"

            if not interaction.response.is_done():
                await interaction.response.send_message(full_message, ephemeral=True)
            else:
                await interaction.followup.send(full_message, ephemeral=True)


    async def _handle_set_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptSetView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "set_prompt_title", fallback="⚙️ Set System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "set_prompt_description", fallback="Please select the scope to configure")
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_view_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptViewOptionsView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "view_options_title", fallback="👁️ View System Prompt Configuration")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "view_options_description", fallback="Please select view options")
        embed = discord.Embed(title=title, description=description, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_copy_function(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'server_only', fallback='Server only')}",
                ephemeral=True,
            )
            return
        guild_id = str(interaction.guild.id)
        view = SystemPromptCopyView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild=interaction.guild,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "copy_prompt_title", fallback="📋 Copy System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "copy_prompt_description", fallback="Please select source and target channels")
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_remove_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptRemoveView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "remove_prompt_title", fallback="🗑️ Remove System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "remove_prompt_description", fallback="Please select scope to remove")
        embed = discord.Embed(title=title, description=description, color=discord.Color.red())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_reset_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptResetView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "reset_config_title", fallback="🔄 Reset System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "reset_config_description", fallback="Please select scope to reset")
        embed = discord.Embed(title=title, description=description, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _handle_reload_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        try:
            if hasattr(self.manager, "reload_all_configs") and callable(self.manager.reload_all_configs):
                import asyncio as _asyncio
                if _asyncio.iscoroutinefunction(self.manager.reload_all_configs):
                    await self.manager.reload_all_configs()
                else:
                    self.manager.reload_all_configs()
                msg = _ti(interaction, "commands", "system_prompt", "messages", "success", "reload",
                          fallback="✅ Configuration reloaded successfully")
                await interaction.response.send_message(msg, ephemeral=True)
                self.logger.info(f"User {interaction.user} reloaded configuration.")
            else:
                msg = _ti(interaction, "commands", "system_prompt", "messages", "info", "reload_unavailable",
                          fallback="⚠️ Reload function is currently unavailable")
                await interaction.response.send_message(msg, ephemeral=True)
        except PermissionError as e:
            err = _ti(interaction, "commands", "system_prompt", "errors", "permission_denied", fallback="Permission denied")
            await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error reloading config: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)


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
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )

class SystemPromptSetView(LocalizedView):
    """設定系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "channel_specific", fallback="Channel Specific"),
            emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0,
        ))
        self.add_item(SystemPromptScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "server_default", fallback="Server Default"),
            emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))

    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        try:
            if not interaction.guild:
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'server_only', fallback='Server only')}",
                    ephemeral=True,
                )
                return
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            target_channel_obj: Optional[discord.TextChannel] = None

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_channel", interaction.channel
                )
                target_channel_obj = interaction.channel
                raw = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                          fallback="Channel #{channel}")
                scope_text = raw.format(channel=interaction.channel.name)
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_server", interaction.guild
                )
                scope_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                 fallback="Server Default")

            view = EditModeSelectionView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                scope=scope,
                target_channel=target_channel_obj,
                scope_text=scope_text,
                guild=interaction.guild,
                guild_id=guild_id,
            )
            title_tpl = _ti(interaction, "commands", "system_prompt", "ui", "menus", "edit_mode_title",
                            fallback="⚙️ Edit {scope} Prompt")
            title = title_tpl.format(scope=scope_text)
            description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "edit_mode_description",
                               fallback="Please select edit mode")
            embed = discord.Embed(title=title, description=description, color=discord.Color.blue())

            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for scope {scope}")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'permission_denied', fallback='Permission denied')}: {e}",
                ephemeral=True,
            )
        except Exception as e:
            self.logger.error(f"Error handling scope selection: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)


class EditModeSelectionView(LocalizedView):
    """編輯模式選擇選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        scope: str,
        target_channel: Optional[discord.TextChannel],
        scope_text: str,
        guild: discord.Guild,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.guild = guild
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(EditModeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "direct_edit", fallback="Direct Edit"),
            emoji="✏️", style=discord.ButtonStyle.primary, edit_mode="direct", row=0,
        ))
        self.add_item(EditModeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "module_edit", fallback="Module Edit"),
            emoji="📦", style=discord.ButtonStyle.secondary, edit_mode="module", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))

    async def edit_mode_callback(self, interaction: discord.Interaction, edit_mode: str):
        """處理編輯模式選擇"""
        try:
            if edit_mode == "direct":
                await self._handle_direct_edit(interaction)
            elif edit_mode == "module":
                await self._handle_module_edit(interaction)
        except Exception as e:
            self.logger.error(f"EditModeButton callback error: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)


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

        modal_title = _ti(
            interaction,
            "commands", "system_prompt", "ui", "modals", "system_prompt", "title_edit",
            fallback="Edit System Prompt",
        )
        modal = SystemPromptModal(
            title=modal_title,
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
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'messages', 'info', 'modules_none', fallback='No modules available')}",
                    ephemeral=True,
                )
                return

            view = ModuleEditView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                modules=modules,
                scope=self.scope,
                target_channel=self.target_channel,
                scope_text=self.scope_text,
                guild=self.guild,
                guild_id=self.guild_id,
            )
            # view._guild = self.guild # Already passed via constructor

            guild_id = str(interaction.guild.id) if interaction.guild else "system"
            title_tpl = _ti(
                interaction,
                "commands", "system_prompt", "ui", "menus", "module_scope_title",
                fallback="📦 Edit {scope} Module",
            )
            embed = discord.Embed(
                title=title_tpl.format(scope=self.scope_text),
                description=_ti(interaction, "commands", "system_prompt", "ui", "menus", "module_scope_description",
                                 fallback="Please select module to edit"),
                color=discord.Color.purple(),
            )
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            self.logger.error(f"載入模組時發生錯誤: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)

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
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "set",
                              fallback="✅ System prompt set successfully"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "set_description",
                                    fallback="Successfully set {scope} system prompt").format(scope=self.scope_text),
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name=_ti(interaction, "commands", "system_prompt", "messages", "info", "content_length",
                             fallback="Content length"),
                    value=f"{len(content)} characters",
                    inline=True,
                )
                embed.add_field(
                    name=_ti(interaction, "commands", "system_prompt", "messages", "info", "created_by",
                             fallback="Created by"),
                    value=interaction.user.mention,
                    inline=True,
                )
                
                # Modal callbacks should use followup if initial response was to send the modal
                await interaction.response.send_message(embed=embed, ephemeral=True) 
            else:
                err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ {err}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ {err}", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in _handle_direct_set_callback: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)


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
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )


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
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )


class SystemPromptViewOptionsView(LocalizedView):
    """查看配置選項選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptViewButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "current_channel", fallback="Current Channel"),
            emoji="📢", style=discord.ButtonStyle.primary, view_type="current", row=0,
        ))
        self.add_item(SystemPromptViewButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "show_inheritance", fallback="Show Inheritance"),
            emoji="🔗", style=discord.ButtonStyle.secondary, view_type="inheritance", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))

    async def view_callback(self, interaction: discord.Interaction, view_type: str):
        """處理查看回調"""
        try:
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                    ephemeral=True,
                )
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
                yaml_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_yaml",
                               fallback="🔹 YAML Base Prompt")
                srv_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_server",
                              fallback="🔸 Server Default Prompt")
                ch_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_channel",
                             fallback="🔸 Channel Specific Prompt")
                title_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_title",
                                fallback="Inheritance Hierarchy")

                inheritance_info = [yaml_lbl]

                server_level_config = system_prompts.get('server_level', {})
                if server_level_config.get('prompt') or server_level_config.get('modules'):
                    inheritance_info.append(srv_lbl)

                if channel_id_str in channels_config:
                    channel_specific_config = channels_config[channel_id_str]
                    if channel_specific_config.get('prompt') or channel_specific_config.get('modules'):
                        inheritance_info.append(ch_lbl)

                embed.add_field(
                    name=title_lbl,
                    value="\n".join(inheritance_info),
                    inline=False,
                )
                source_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "source",
                                 fallback="Source")
                embed.set_footer(text=f"{source_lbl}: {prompt_data.get('source', '?')}")


            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self) # Keep current view or new one
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True) # view=self if needed

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for view")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'permission_denied', fallback='Permission denied')}: {str(e)}",
                ephemeral=True,
            )
        except Exception as e:
            self.logger.error(f"Error in view_callback: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {str(e)}", ephemeral=True)


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
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )


class ModuleEditView(LocalizedView):
    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        modules: List[str],
        guild: discord.Guild,
        scope: Optional[str] = None,
        target_channel: Optional[discord.TextChannel] = None,
        scope_text: Optional[str] = None,
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.modules = modules
        self.guild = guild
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.logger = get_logger(source=__name__, server_id="system")
        self.selected_scope = scope

        if scope and scope_text:
            self._setup_module_selector()
        else:
            self._setup_scope_selector()

    def _setup_scope_selector(self):
        self.clear_items()
        self.add_item(ModuleScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "channel_module", fallback="Channel Module"),
            emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0,
        ))
        self.add_item(ModuleScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "server_module", fallback="Server Module"),
            emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0,
        ))
        self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))

    def _setup_module_selector(self):
        self.clear_items()
        placeholder = self._t("commands", "system_prompt", "ui", "selectors", "module_placeholder",
                               fallback="Select module to edit")
        desc_tpl = self._t("commands", "system_prompt", "ui", "selectors", "module_description",
                            fallback="Edit {module} module")

        options = [
            discord.SelectOption(
                label=mod,
                value=mod,
                description=desc_tpl.format(module=mod)[:100],
            )
            for mod in self.modules[:25]
        ]

        if options:
            effective_scope = self.selected_scope or self.scope
            select = ModuleSelect(
                placeholder=placeholder,
                options=options,
                manager=self.manager,
                scope=effective_scope,
                channel=self.target_channel if effective_scope == "channel" else None,
                guild=self.guild,
                scope_text=self.scope_text or (
                    f"#{self.target_channel.name}" if self.target_channel else "server"
                ),
            )
            self.add_item(select)
            self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))
        else:
            no_mod = self._t("commands", "system_prompt", "messages", "info", "modules_none",
                             fallback="No modules available")
            self.add_item(discord.ui.Button(label=no_mod, style=discord.ButtonStyle.secondary, disabled=True))
            self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))


    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        try:
            if not interaction.guild:
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'server_only', fallback='Server only')}",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            self.guild = interaction.guild

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_channel", interaction.channel
                )
                self.target_channel = interaction.channel
                raw = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                          fallback="Channel #{channel}")
                self.scope_text = raw.format(channel=interaction.channel.name)
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_server", interaction.guild
                )
                self.target_channel = None
                self.scope_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                      fallback="Server Default")

            self.selected_scope = scope
            self.guild_id = guild_id
            self.modules = self.manager.get_available_modules()
            self._setup_module_selector()

            title_tpl = _ti(interaction, "commands", "system_prompt", "ui", "menus", "module_scope_title",
                            fallback="📦 Edit {scope} Module")
            embed = discord.Embed(
                title=title_tpl.format(scope=self.scope_text),
                description=_ti(interaction, "commands", "system_prompt", "ui", "menus", "module_scope_description",
                                 fallback="Please select module to edit"),
                color=discord.Color.purple(),
            )
            await interaction.response.edit_message(embed=embed, view=self)

        except PermissionError as e:
            self.logger.warning(f"Permission denied in ModuleEditView: {e}")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'permission_denied', fallback='Permission denied')}: {e}",
                ephemeral=True,
            )
        except Exception as e:
            self.logger.error(f"Error in ModuleEditView.scope_callback: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)


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
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )


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
        self.scope_text = scope_text or ("Server Default" if scope == "server" else (f"#{channel.name}" if channel else "unknown"))
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
            self.logger.error(f"ModuleSelect callback error: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)


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
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "set",
                              fallback="✅ Module set successfully"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "set_description",
                                    fallback="Successfully set {scope} system prompt").format(scope=display_scope_text),
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name=_ti(interaction, "commands", "system_prompt", "messages", "info", "content_length",
                             fallback="Content length"),
                    value=f"{len(content)} characters",
                    inline=True,
                )

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


class SystemPromptCopyView(LocalizedView):
    """複製系統提示選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild: discord.Guild,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.guild = guild
        self.logger = get_logger(server_id="system", source=__name__)

        text_channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).view_channel and ch.permissions_for(guild.me).send_messages
        ]

        if text_channels:
            from_placeholder = self._t("commands", "system_prompt", "ui", "selectors", "from_channel_placeholder",
                                        fallback="Select source channel")
            to_placeholder = self._t("commands", "system_prompt", "ui", "selectors", "to_channel_placeholder",
                                      fallback="Select target channel")
            execute_label = self._t("commands", "system_prompt", "ui", "buttons", "execute_copy",
                                     fallback="Execute Copy")

            options = [
                discord.SelectOption(label=f"#{ch.name}", value=str(ch.id), description=f"ID: {ch.id}")
                for ch in text_channels[:25]
            ]
            self.add_item(ChannelSelect(placeholder=from_placeholder, options=options, custom_id="from_channel", row=0))
            self.add_item(ChannelSelect(placeholder=to_placeholder, options=list(options), custom_id="to_channel", row=1))
            self.add_item(CopyExecuteButton(label=execute_label, row=2))
            self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=3))
        else:
            no_ch = self._t("commands", "system_prompt", "errors", "no_channels_available",
                             fallback="No channels available")
            self.add_item(discord.ui.Button(label=no_ch, style=discord.ButtonStyle.secondary, disabled=True, row=0))
            self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))


class SystemPromptRemoveView(LocalizedView):
    """移除系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(server_id="system", source=__name__)

        self.add_item(RemoveButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_channel_prompt",
                          fallback="Remove Channel Prompt"),
            emoji="📢", style=discord.ButtonStyle.danger, remove_type="channel", row=0,
        ))
        self.add_item(RemoveButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_server_prompt",
                          fallback="Remove Server Prompt"),
            emoji="🏠", style=discord.ButtonStyle.danger, remove_type="server", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))


class SystemPromptResetView(LocalizedView):
    """重置系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(server_id="system", source=__name__)

        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_current_channel",
                          fallback="Reset Current Channel"),
            emoji="📢", style=discord.ButtonStyle.danger, reset_type="channel", row=0,
        ))
        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_server_default",
                          fallback="Reset Server Default"),
            emoji="🏠", style=discord.ButtonStyle.danger, reset_type="server", row=0,
        ))
        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_all_settings",
                          fallback="Reset All Settings"),
            emoji="⚠️", style=discord.ButtonStyle.danger, reset_type="all", row=1,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=2))


# --- 輔助按鈕與選擇器類別 ---

class BackButton(discord.ui.Button):
    """返回主選單按鈕"""
    def __init__(self, row: int = 4, guild_id: str = "system", bot=None): # Default row or specified
        label = "Back"
        try:
            if bot and (lm := bot.get_cog("LanguageManager")):
                label = lm.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "back_to_main")
        except Exception:
            pass
        super().__init__(label=label, emoji="🔙", style=discord.ButtonStyle.secondary, row=row)
        self.guild_id: str = guild_id
        self._bot = bot
        self.logger = get_logger(server_id="system", source=__name__)

    async def callback(self, interaction: discord.Interaction):
        """返回主選單"""
        # This relies on SystemPromptCommands cog being available and structured this way
        try:
            # Assuming client is on interaction
            commands_cog = interaction.client.get_cog("SystemPromptCommands")
            if commands_cog and hasattr(commands_cog, "get_system_prompt_manager") and hasattr(commands_cog, "permission_validator"):
                manager = commands_cog.get_system_prompt_manager()
                permission_validator = commands_cog.permission_validator

                guild_id = str(interaction.guild.id) if interaction.guild else self.guild_id
                main_view = SystemPromptMainView(manager, permission_validator, guild_id=guild_id)
                title = _ti(interaction, "commands", "system_prompt", "ui", "main_menu", "title",
                            fallback="🤖 System Prompt Management")
                description = _ti(interaction, "commands", "system_prompt", "ui", "main_menu", "description",
                                  fallback="Please select a function")
                embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
                await interaction.response.edit_message(embed=embed, view=main_view)
            else:
                self.logger.error("SystemPromptCommands cog or its methods not found for BackButton.")
                await interaction.response.edit_message(
                    content=f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                    embed=None,
                    view=None,
                )
        except Exception as e:
            self.logger.error(f"BackButton callback error: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            await interaction.response.edit_message(content=f"❌ {err}: {e}", embed=None, view=None)


class ChannelSelect(discord.ui.Select):
    """頻道選擇器（用於複製功能）"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_channel_id: Optional[str] = None
        self.logger = get_logger(server_id="system", source=__name__)


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
    def __init__(self, label: str = "Execute Copy", **kwargs):
        super().__init__(label=label, emoji="📋", style=discord.ButtonStyle.success, **kwargs)
        self.logger = get_logger(server_id="system", source=__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptCopyView = self.view
        if not view or not view.guild:
            self.logger.error("CopyExecuteButton: View or guild not found.")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )
            return

        from_channel_selector = discord.utils.get(view.children, custom_id="from_channel")
        to_channel_selector = discord.utils.get(view.children, custom_id="to_channel")

        if not (isinstance(from_channel_selector, ChannelSelect) and
                isinstance(to_channel_selector, ChannelSelect)):
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )
            return

        from_channel_id = from_channel_selector.selected_channel_id
        to_channel_id = to_channel_selector.selected_channel_id

        if not from_channel_id or not to_channel_id:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'validation_failed', fallback='Please select source and target channels')}",
                ephemeral=True,
            )
            return
        if from_channel_id == to_channel_id:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'messages', 'validation', 'same_channel', fallback='Source and target must differ')}",
                ephemeral=True,
            )
            return

        try:
            to_channel_obj = view.guild.get_channel(int(to_channel_id))
            if not to_channel_obj or not isinstance(to_channel_obj, discord.TextChannel):
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                    ephemeral=True,
                )
                return

            view.permission_validator.validate_permission_or_raise(
                interaction.user, 'modify_channel', to_channel_obj  # Permission to modify target
            )
            # Optionally, check view permission for source channel
            # from_channel_obj = view.guild.get_channel(int(from_channel_id))
            # view.permission_validator.validate_permission_or_raise(interaction.user, 'view', from_channel_obj)

            success = view.manager.copy_channel_prompt(
                str(view.guild.id), from_channel_id,
                str(view.guild.id), to_channel_id,  # Assuming manager takes guild_id for both
                str(interaction.user.id)
            )

            if success:
                from_channel_obj = view.guild.get_channel(int(from_channel_id))
                from_name = from_channel_obj.name if from_channel_obj else from_channel_id

                embed = discord.Embed(
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "copy",
                              fallback="✅ Copy successful"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "copy_description",
                                    fallback="Copied from #{from_channel} to #{to_channel}").format(
                        from_channel=from_name, to_channel=to_channel_obj.name
                    ),
                    color=discord.Color.green(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
                await interaction.response.send_message(f"❌ {err}", ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for copy")
            err = _ti(interaction, "commands", "system_prompt", "errors", "permission_denied", fallback="Permission denied")
            await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Copy operation failed: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)


class RemoveButton(discord.ui.Button):
    """移除按鈕"""
    def __init__(self, label: str, remove_type: str, **kwargs):
        super().__init__(label=label, **kwargs)
        self.remove_type = remove_type
        self.logger = get_logger(server_id="system", source=__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptRemoveView = self.view
        if not view or not interaction.guild:  # Ensure guild context
            self.logger.error("RemoveButton: View or guild not found.")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )
            return

        guild_id_str = str(interaction.guild.id)
        confirm_text = ""
        operation_text = ""

        try:
            if self.remove_type == "channel":
                if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                    await interaction.response.send_message(
                        f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                        ephemeral=True,
                    )
                    return
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                channel_id_str = str(interaction.channel.id)
                config = view.manager._load_guild_config(guild_id_str)
                if channel_id_str not in config.get('system_prompts', {}).get('channels', {}):
                    raw = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "remove_channel",
                              fallback="Remove channel #{channel} prompt?")
                    await interaction.response.send_message(
                        f"❌ {raw.format(channel=interaction.channel.name)}",
                        ephemeral=True,
                    )
                    return
                raw = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "remove_channel",
                          fallback="Remove channel #{channel} prompt?")
                confirm_text = raw.format(channel=interaction.channel.name)
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_remove",
                                 fallback="⚠️ Confirm Removal")
                raw_scope = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                                fallback="Channel #{channel}")
                operation_text = raw_scope.format(channel=interaction.channel.name)
            else:  # server
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                config = view.manager._load_guild_config(guild_id_str)
                if not config.get('system_prompts', {}).get('server_level', {}):
                    await interaction.response.send_message(
                        f"❌ {_ti(interaction, 'commands', 'system_prompt', 'messages', 'confirm', 'remove_server', fallback='Remove server default prompt?')}",
                        ephemeral=True,
                    )
                    return
                confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "remove_server",
                                   fallback="Remove server default prompt?")
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_remove",
                                 fallback="⚠️ Confirm Removal")
                operation_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                     fallback="Server Default")

            confirm_embed = discord.Embed(title=title_text, description=confirm_text, color=discord.Color.orange())
            confirmation_prompt_view = ConfirmationView(confirm_text="Confirm", cancel_text="Cancel")
            await interaction.response.send_message(embed=confirm_embed, view=confirmation_prompt_view, ephemeral=True)

            await confirmation_prompt_view.wait()  # Wait for user confirmation

            if confirmation_prompt_view.result is True:  # User confirmed
                self.logger.info(f"User {interaction.user} confirmed removal of {operation_text} (Guild: {guild_id_str})")
                success = False
                if self.remove_type == "channel":
                    channel_id_str_op = str(interaction.channel.id) if interaction.channel else None
                    if channel_id_str_op:
                        success = view.manager.remove_channel_prompt(guild_id_str, channel_id_str_op)
                else:  # server
                    success = view.manager.remove_server_prompt(guild_id_str, str(interaction.user.id))

                if success:
                    result_embed = discord.Embed(
                        title=_ti(interaction, "commands", "system_prompt", "messages", "success", "remove",
                                  fallback="✅ Removal successful"),
                        description=_ti(interaction, "commands", "system_prompt", "messages", "success", "remove_description",
                                        fallback="Removed {scope} system prompt").format(scope=operation_text),
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=result_embed, ephemeral=True)
                else:
                    err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
                    await interaction.followup.send(f"❌ {err}", ephemeral=True)
            elif confirmation_prompt_view.result is False:  # User cancelled
                await interaction.followup.send(
                    _ti(interaction, "commands", "system_prompt", "messages", "info", "operation_cancelled",
                        fallback="Operation cancelled"),
                    ephemeral=True,
                )
            # else: timeout

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for remove {self.remove_type}")
            err = _ti(interaction, "commands", "system_prompt", "errors", "permission_denied", fallback="Permission denied")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {str(e)}", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Remove operation ({self.remove_type}) failed: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {str(e)}", ephemeral=True)


class ResetButton(discord.ui.Button):
    """重置按鈕"""
    def __init__(self, label: str, reset_type: str, **kwargs):
        super().__init__(label=label, **kwargs)
        self.reset_type = reset_type
        self.logger = get_logger(server_id="system", source=__name__)

    async def callback(self, interaction: discord.Interaction):
        view: SystemPromptResetView = self.view
        if not view or not interaction.guild:
            self.logger.error("ResetButton: View or guild not found.")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )
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
                    await interaction.response.send_message(
                        f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                        ephemeral=True,
                    )
                    return
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_channel', interaction.channel
                )
                if str(interaction.channel.id) in system_prompts.get('channels', {}):
                    has_content_to_reset = True
                raw = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_channel",
                          fallback="Reset channel #{channel} prompt?")
                confirm_text = raw.format(channel=interaction.channel.name)
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_reset",
                                 fallback="⚠️ Confirm Reset")
                raw_scope = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                                fallback="Channel #{channel}")
                operation_text = raw_scope.format(channel=interaction.channel.name)
            elif self.reset_type == "server":
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild
                )
                if system_prompts.get('server_level', {}):
                    has_content_to_reset = True
                confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_server",
                                   fallback="Reset server default prompt?")
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_reset",
                                 fallback="⚠️ Confirm Reset")
                operation_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                     fallback="Server Default")
            else:  # "all"
                view.permission_validator.validate_permission_or_raise(
                    interaction.user, 'modify_server', interaction.guild  # Highest permission
                )
                if system_prompts.get('channels', {}) or system_prompts.get('server_level', {}):
                    has_content_to_reset = True
                confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_all",
                                   fallback="Reset ALL system prompt settings? This cannot be undone!")
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_reset",
                                 fallback="⚠️ Confirm Reset")
                operation_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_all",
                                     fallback="All")

            if not has_content_to_reset:
                await interaction.response.send_message(
                    f"ℹ️ {operation_text}",
                    ephemeral=True,
                )
                return

            confirm_embed = discord.Embed(title=title_text, description=confirm_text, color=discord.Color.red())
            confirmation_prompt_view = ConfirmationView(confirm_text="Confirm", cancel_text="Cancel")
            await interaction.response.send_message(embed=confirm_embed, view=confirmation_prompt_view, ephemeral=True)

            await confirmation_prompt_view.wait()

            if confirmation_prompt_view.result is True:
                self.logger.info(f"User {interaction.user} confirmed reset of {operation_text} (Guild: {guild_id_str}, Type: {self.reset_type})")
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
                    else:  # Fallback: remove server and all channel prompts individually
                        view.manager.remove_server_prompt(guild_id_str)  # Remove server default
                        current_config = view.manager._load_guild_config(guild_id_str)
                        channels_to_reset = list(current_config.get('system_prompts', {}).get('channels', {}).keys())
                        for chan_id in channels_to_reset:
                            view.manager.remove_channel_prompt(guild_id_str, chan_id)
                        success = True  # Assume success if operations don't throw
                        self.logger.info(f"Reset all: removed server default and {len(channels_to_reset)} channel settings.")

                if success:
                    result_embed = discord.Embed(
                        title=_ti(interaction, "commands", "system_prompt", "messages", "success", "reset",
                                  fallback="✅ Reset successful"),
                        description=_ti(interaction, "commands", "system_prompt", "messages", "success", "reset_description",
                                        fallback="Reset {scope} settings").format(scope=operation_text),
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=result_embed, ephemeral=True)
                else:
                    err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
                    await interaction.followup.send(f"❌ {err}", ephemeral=True)
            elif confirmation_prompt_view.result is False:
                await interaction.followup.send(
                    _ti(interaction, "commands", "system_prompt", "messages", "info", "operation_cancelled",
                        fallback="Operation cancelled"),
                    ephemeral=True,
                )

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for reset {self.reset_type}")
            err = _ti(interaction, "commands", "system_prompt", "errors", "permission_denied", fallback="Permission denied")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {str(e)}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Reset operation ({self.reset_type}) failed: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {str(e)}", ephemeral=True)