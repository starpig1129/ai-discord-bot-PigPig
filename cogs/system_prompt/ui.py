"""
頻道系統提示管理模組的 UI 元件

提供 Discord UI 元件，包含 Modal 對話框、確認按鈕、選擇器等。
"""

import discord
from typing import Optional, Dict, Any, Callable, List
import logging
from function import func
import asyncio

from .exceptions import ValidationError, ContentTooLongError


class SystemPromptModal(discord.ui.Modal):
    """系統提示設定的 Modal 對話框"""
    
    def __init__(self,
                 title: str = None,
                 prompt_label: str = None,
                 prompt_placeholder: str = None,
                 initial_value: str = "",
                 callback_func: Optional[Callable] = None,
                 manager=None,
                 channel_id: str = "",
                 guild_id: str = "",
                 show_default_content: bool = True,
                 **kwargs):
        """
        初始化 Modal 對話框
        
        Args:
            title: Modal 標題（如果未提供，將使用本地化）
            prompt_label: 提示輸入框標籤（如果未提供，將使用本地化）
            prompt_placeholder: 提示輸入框佔位文字（如果未提供，將使用本地化）
            initial_value: 初始值
            callback_func: 回調函式
            manager: SystemPromptManager 實例
            channel_id: 頻道 ID
            guild_id: 伺服器 ID
            show_default_content: 是否顯示預設內容
            **kwargs: 其他參數
        """
        # 獲取本地化文字，帶有降級機制
        if manager and hasattr(manager, 'language_manager') and manager.language_manager and guild_id:
            title = title or manager.language_manager.translate(guild_id, "commands", "system_prompt", "ui", "modals", "system_prompt", "title")
            prompt_label = prompt_label or manager.language_manager.translate(guild_id, "commands", "system_prompt", "ui", "modals", "system_prompt", "prompt_label")
            prompt_placeholder = prompt_placeholder or manager.language_manager.translate(guild_id, "commands", "system_prompt", "ui", "modals", "system_prompt", "prompt_placeholder")
        
        # 降級到預設值
        title = title or "System Prompt Setting"
        prompt_label = prompt_label or "System Prompt Content"
        prompt_placeholder = prompt_placeholder or "Please enter system prompt content..."
        
        super().__init__(title=title, **kwargs)
        self.callback_func = callback_func
        self.manager = manager
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.logger = logging.getLogger(__name__)
        
        # 如果沒有提供初始值且需要顯示預設內容，嘗試載入完整有效提示
        if not initial_value and show_default_content and manager and channel_id and guild_id:
            try:
                # 先嘗試從配置中取得原始提示（保留變數占位符）
                config = manager._load_guild_config(guild_id)
                system_prompts = config.get('system_prompts', {})
                
                if channel_id:
                    # 頻道特定提示
                    channels = system_prompts.get('channels', {})
                    if channel_id in channels:
                        initial_value = channels[channel_id].get('prompt', '')
                        if initial_value and manager.language_manager:
                            prompt_placeholder = manager.language_manager.translate(guild_id, "commands", "system_prompt", "user_experience", "editing", "channel_specific_edit")
                        self.logger.info(f"已載入頻道提示作為預設內容，長度: {len(initial_value)}")
                
                # 如果還沒有內容，嘗試伺服器級別提示
                if not initial_value:
                    server_level = system_prompts.get('server_level', {})
                    if server_level.get('prompt'):
                        initial_value = server_level['prompt']
                        if manager.language_manager:
                            prompt_placeholder = manager.language_manager.translate(guild_id, "commands", "system_prompt", "user_experience", "editing", "server_default_edit")
                        self.logger.info(f"已載入伺服器提示作為預設內容，長度: {len(initial_value)}")
                
                # 最後降級到有效提示，但要還原變數占位符
                if not initial_value:
                    effective_prompt = manager.get_effective_full_prompt(channel_id, guild_id)
                    if effective_prompt:
                        # 還原變數占位符
                        initial_value = self._restore_variable_placeholders(effective_prompt, manager)
                        if manager.language_manager:
                            prompt_placeholder = manager.language_manager.translate(guild_id, "commands", "system_prompt", "user_experience", "editing", "current_effective_edit")
                        self.logger.info(f"已載入有效提示並還原變數格式，長度: {len(initial_value)}")
                        
            except Exception as e:
                asyncio.create_task(func.report_error(e, "Error loading default content"))
                self.logger.warning(f"載入預設內容時發生錯誤: {e}")
        
        # 檢查並處理初始值的長度限制
        if initial_value and len(initial_value) > 4000:
            self.logger.warning(f"Initial content too long ({len(initial_value)} chars), truncating to 4000 chars")
            initial_value = initial_value[:4000]
            if manager and hasattr(manager, 'language_manager') and manager.language_manager and guild_id:
                truncation_warning = manager.language_manager.translate(guild_id, "commands", "system_prompt", "errors", "content_too_long")
                prompt_placeholder = f"{prompt_placeholder} ({truncation_warning.format(length='4000', max='4000')})"
            else:
                prompt_placeholder += " (內容已截斷以符合 Discord 限制)"
        
        # 系統提示輸入框
        self.prompt_input = discord.ui.TextInput(
            label=prompt_label,
            placeholder=prompt_placeholder,
            style=discord.TextStyle.paragraph,
            max_length=4000,
            default=initial_value,
            required=True
        )
        self.add_item(self.prompt_input)
    
    def _restore_variable_placeholders(self, prompt: str, manager) -> str:
        """
        還原變數占位符格式
        
        Args:
            prompt: 已替換變數的提示
            manager: SystemPromptManager 實例
            
        Returns:
            還原變數占位符的提示
        """
        try:
            if not manager or not hasattr(manager, '_get_system_variables'):
                return prompt
                
            # 獲取當前的變數值
            variables = manager._get_system_variables()
            
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
            
            self.logger.debug(f"🔄 UI 模組變數占位符還原完成")
            return restored_prompt
            
        except Exception as e:
            asyncio.create_task(func.report_error(e, "Error restoring variable placeholders in UI"))
            self.logger.warning(f"UI 模組還原變數占位符時發生錯誤: {e}")
            return prompt
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理 Modal 提交"""
        try:
            prompt_content = self.prompt_input.value.strip()
            
            if not prompt_content:
                # Get language manager for error messages
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "validation", "prompt_empty")
                else:
                    error_msg = "❌ 系統提示內容不能為空"
                
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            if self.callback_func:
                await self.callback_func(interaction, prompt_content)
            else:
                # Get language manager for success message
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    success_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "messages", "success", "set")
                else:
                    success_msg = "✅ 系統提示已設定"
                
                await interaction.response.send_message(success_msg, ephemeral=True)
                
        except Exception as e:
            await func.report_error(e, "Error processing Modal submission")
            self.logger.error(f"處理 Modal 提交時發生錯誤: {e}")
            if not interaction.response.is_done():
                # Get language manager for error messages
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "modal_error")
                    formatted_error = error_msg.format(error=str(e))
                else:
                    formatted_error = f"❌ 處理請求時發生錯誤: {str(e)}"
                
                await interaction.response.send_message(formatted_error, ephemeral=True)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """處理 Modal 錯誤"""
        self.logger.error(f"Modal 錯誤: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ 發生未知錯誤，請稍後再試",
                ephemeral=True
            )


class SystemPromptModuleModal(discord.ui.Modal):
    """模組設定的 Modal 對話框"""
    
    def __init__(self,
                 module_name: str,
                 initial_value: str = "",
                 callback_func: Optional[Callable] = None,
                 manager=None,
                 lang: str = "zh_TW",
                 show_default_content: bool = True,
                 **kwargs):
        """
        初始化模組設定 Modal
        
        Args:
            module_name: 模組名稱
            initial_value: 初始值
            callback_func: 回調函式
            manager: SystemPromptManager 實例
            lang: 語言代碼
            show_default_content: 是否顯示預設內容
            **kwargs: 其他參數
        """
        # 獲取模組說明
        module_description = ""
        if manager:
            descriptions = manager.get_module_descriptions(lang)
            module_description = descriptions.get(module_name, "")
        
        # 構建標題，確保不超過 45 字元限制
        title = f"編輯模組: {module_name}"
        if len(title) > 45:
            # 如果模組名稱太長，縮短標題
            max_module_name_len = 45 - len("編輯模組: ")
            short_module_name = module_name[:max_module_name_len] + "..." if len(module_name) > max_module_name_len else module_name
            title = f"編輯模組: {short_module_name}"
        
        super().__init__(title=title[:45], **kwargs)  # Discord 限制標題長度為 45 字元
        self.module_name = module_name
        self.callback_func = callback_func
        self.manager = manager
        self.module_description = module_description
        self.logger = logging.getLogger(__name__)
        
        # 如果沒有提供初始值且需要顯示預設內容，載入預設模組內容
        placeholder_text = f"請輸入 {module_name} 模組的內容..."
        if not initial_value and show_default_content and manager:
            try:
                default_content = manager.get_default_module_content(module_name)
                if default_content:
                    initial_value = default_content
                    placeholder_text = f"基於 {module_name} 模組的預設內容進行編輯..."
                    self.logger.info(f"已載入模組 '{module_name}' 的預設內容，長度: {len(default_content)}")
            except Exception as e:
                asyncio.create_task(func.report_error(e, f"Error loading default content for module '{module_name}'"))
                self.logger.warning(f"載入模組 '{module_name}' 預設內容時發生錯誤: {e}")
        
        # 檢查並處理初始值的長度限制（模組輸入框限制為2000字符）
        if initial_value and len(initial_value) > 2000:
            self.logger.warning(f"Module '{module_name}' initial content too long ({len(initial_value)} chars), truncating to 2000 chars")
            initial_value = initial_value[:2000]
            placeholder_text += " (內容已截斷以符合 Discord 限制)"
        
        # 構建標籤，包含模組說明
        label_text = f"{module_name} 模組內容"
        if module_description:
            # 在標籤中添加簡短說明
            short_label_desc = module_description[:30] + "..." if len(module_description) > 30 else module_description
            label_text = f"{module_name} - {short_label_desc}"
        
        # 模組內容輸入框
        self.module_input = discord.ui.TextInput(
            label=label_text[:45],  # Discord 限制標籤長度
            placeholder=placeholder_text,
            style=discord.TextStyle.paragraph,
            max_length=2000,
            default=initial_value,
            required=True
        )
        self.add_item(self.module_input)
        
        # 如果有詳細說明，添加說明輸入框（僅顯示，不可編輯）
        if module_description and len(module_description) > 50:
            # 檢查說明長度是否超過限制
            description_content = module_description
            if len(description_content) > 1000:
                self.logger.warning(f"Module '{module_name}' description too long ({len(description_content)} chars), truncating to 1000 chars")
                description_content = description_content[:1000]
            
            self.description_display = discord.ui.TextInput(
                label="📋 模組說明",
                placeholder="",
                default=description_content,
                style=discord.TextStyle.paragraph,
                max_length=1000,
                required=False
            )
            # 讓說明框只讀（雖然Discord不直接支持，但可以在提交時忽略）
            self.add_item(self.description_display)
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理模組 Modal 提交"""
        try:
            module_content = self.module_input.value.strip()
            
            if not module_content:
                # Get language manager for error messages
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "validation", "module_empty")
                    formatted_error = error_msg.format(module=self.module_name)
                else:
                    formatted_error = f"❌ {self.module_name} 模組內容不能為空"
                
                await interaction.response.send_message(formatted_error, ephemeral=True)
                return
            
            if self.callback_func:
                await self.callback_func(interaction, self.module_name, module_content)
            else:
                # Get language manager for success message
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    success_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "messages", "success", "set")
                    formatted_success = success_msg.format(scope=f"{self.module_name} 模組")
                else:
                    formatted_success = f"✅ {self.module_name} 模組已設定"
                
                await interaction.response.send_message(formatted_success, ephemeral=True)
                
        except Exception as e:
            await func.report_error(e, "Error processing module Modal submission")
            self.logger.error(f"處理模組 Modal 提交時發生錯誤: {e}")
            if not interaction.response.is_done():
                # Get language manager for error messages
                guild_id = str(interaction.guild.id) if interaction.guild else "system"
                lang_manager = interaction.client.get_cog("LanguageManager") if hasattr(interaction.client, 'get_cog') else None
                
                if lang_manager:
                    error_msg = lang_manager.translate(guild_id, "commands", "system_prompt", "errors", "operation_failed")
                    formatted_error = error_msg.format(error=str(e))
                else:
                    formatted_error = f"❌ 設定模組時發生錯誤: {str(e)}"
                
                await interaction.response.send_message(formatted_error, ephemeral=True)


class ConfirmationView(discord.ui.View):
    """確認對話框 View"""
    
    def __init__(self,
                 confirm_text: str = "確認",
                 cancel_text: str = "取消",
                 confirm_style: discord.ButtonStyle = discord.ButtonStyle.danger,
                 timeout: float = 180.0,
                 **kwargs):
        """
        初始化確認對話框
        
        Args:
            confirm_text: 確認按鈕文字
            cancel_text: 取消按鈕文字
            confirm_style: 確認按鈕樣式
            timeout: 超時時間
            **kwargs: 其他參數
        """
        super().__init__(timeout=timeout, **kwargs)
        self.result = None
        self.confirmed = False
        self.logger = logging.getLogger(__name__)
        
        # 確認按鈕
        self.confirm_button = discord.ui.Button(
            label=confirm_text,
            style=confirm_style,
            emoji="✅"
        )
        self.confirm_button.callback = self._confirm_callback
        self.add_item(self.confirm_button)
        
        # 取消按鈕
        self.cancel_button = discord.ui.Button(
            label=cancel_text,
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        self.cancel_button.callback = self._cancel_callback
        self.add_item(self.cancel_button)
    
    async def _confirm_callback(self, interaction: discord.Interaction):
        """確認按鈕回調"""
        self.confirmed = True
        self.result = True
        self.stop()
        
        await interaction.response.edit_message(
            content="✅ 操作已確認",
            view=None
        )
    
    async def _cancel_callback(self, interaction: discord.Interaction):
        """取消按鈕回調"""
        self.confirmed = False
        self.result = False
        self.stop()
        
        await interaction.response.edit_message(
            content="❌ 操作已取消",
            view=None
        )
    
    async def on_timeout(self):
        """處理超時"""
        self.result = False
        self.stop()


class ChannelSelectView(discord.ui.View):
    """頻道選擇器 View"""
    
    def __init__(self,
                 channels: List[discord.TextChannel],
                 placeholder: str = "選擇頻道",
                 callback_func: Optional[Callable] = None,
                 timeout: float = 180.0,
                 **kwargs):
        """
        初始化頻道選擇器
        
        Args:
            channels: 頻道列表
            placeholder: 佔位文字
            callback_func: 回調函式
            timeout: 超時時間
            **kwargs: 其他參數
        """
        super().__init__(timeout=timeout, **kwargs)
        self.callback_func = callback_func
        self.selected_channel = None
        self.logger = logging.getLogger(__name__)
        
        # 建立選項
        options = []
        for channel in channels[:25]:  # Discord 限制最多 25 個選項
            options.append(discord.SelectOption(
                label=f"#{channel.name}",
                value=str(channel.id),
                description=f"ID: {channel.id}"
            ))
        
        if options:
            # 頻道選擇器
            self.channel_select = discord.ui.Select(
                placeholder=placeholder,
                options=options,
                min_values=1,
                max_values=1
            )
            self.channel_select.callback = self._select_callback
            self.add_item(self.channel_select)
    
    async def _select_callback(self, interaction: discord.Interaction):
        """選擇器回調"""
        try:
            selected_channel_id = self.channel_select.values[0]
            self.selected_channel = selected_channel_id
            
            if self.callback_func:
                await self.callback_func(interaction, selected_channel_id)
            else:
                await interaction.response.send_message(
                    f"✅ 已選擇頻道: <#{selected_channel_id}>",
                    ephemeral=True
                )
            
            self.stop()
            
        except Exception as e:
            await func.report_error(e, "Error processing channel selection")
            self.logger.error(f"處理頻道選擇時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 選擇頻道時發生錯誤: {str(e)}",
                ephemeral=True
            )


class ModuleSelectView(discord.ui.View):
    """模組選擇器 View"""
    
    def __init__(self,
                 modules: List[str],
                 placeholder: str = "選擇要覆蓋的模組",
                 callback_func: Optional[Callable] = None,
                 timeout: float = 180.0,
                 **kwargs):
        """
        初始化模組選擇器
        
        Args:
            modules: 模組列表
            placeholder: 佔位文字
            callback_func: 回調函式
            timeout: 超時時間
            **kwargs: 其他參數
        """
        super().__init__(timeout=timeout, **kwargs)
        self.callback_func = callback_func
        self.selected_modules = []
        self.logger = logging.getLogger(__name__)
        
        # 建立選項
        options = []
        for module in modules[:25]:  # Discord 限制最多 25 個選項
            options.append(discord.SelectOption(
                label=module,
                value=module,
                description=f"覆蓋 {module} 模組"
            ))
        
        if options:
            # 模組選擇器
            self.module_select = discord.ui.Select(
                placeholder=placeholder,
                options=options,
                min_values=1,
                max_values=min(len(options), 10)  # 最多選擇 10 個
            )
            self.module_select.callback = self._select_callback
            self.add_item(self.module_select)
    
    async def _select_callback(self, interaction: discord.Interaction):
        """模組選擇器回調"""
        try:
            selected_modules = self.module_select.values
            self.selected_modules = selected_modules
            
            if self.callback_func:
                await self.callback_func(interaction, selected_modules)
            else:
                modules_text = ", ".join(selected_modules)
                await interaction.response.send_message(
                    f"✅ 已選擇模組: {modules_text}",
                    ephemeral=True
                )
            
            self.stop()
            
        except Exception as e:
            await func.report_error(e, "Error processing module selection")
            self.logger.error(f"處理模組選擇時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 選擇模組時發生錯誤: {str(e)}",
                ephemeral=True
            )


class SystemPromptView(discord.ui.View):
    """系統提示管理的主要 View"""
    
    def __init__(self,
                 prompt_data: Dict[str, Any],
                 can_edit: bool = False,
                 timeout: float = 300.0,
                 **kwargs):
        """
        初始化系統提示 View
        
        Args:
            prompt_data: 提示資料
            can_edit: 是否可編輯
            timeout: 超時時間
            **kwargs: 其他參數
        """
        super().__init__(timeout=timeout, **kwargs)
        self.prompt_data = prompt_data
        self.can_edit = can_edit
        self.logger = logging.getLogger(__name__)
        
        if can_edit:
            # 編輯按鈕
            self.edit_button = discord.ui.Button(
                label="編輯",
                style=discord.ButtonStyle.primary,
                emoji="✏️"
            )
            self.edit_button.callback = self._edit_callback
            self.add_item(self.edit_button)
        
        # 預覽按鈕
        self.preview_button = discord.ui.Button(
            label="預覽",
            style=discord.ButtonStyle.secondary,
            emoji="👁️"
        )
        self.preview_button.callback = self._preview_callback
        self.add_item(self.preview_button)
    
    async def _edit_callback(self, interaction: discord.Interaction):
        """編輯按鈕回調"""
        try:
            current_prompt = self.prompt_data.get('prompt', '')
            
            modal = SystemPromptModal(
                title="編輯系統提示",
                initial_value=current_prompt,
                callback_func=self._edit_modal_callback
            )
            
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            await func.report_error(e, "Error opening edit Modal")
            self.logger.error(f"開啟編輯 Modal 時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 開啟編輯器時發生錯誤: {str(e)}",
                ephemeral=True
            )
    
    async def _edit_modal_callback(self, interaction: discord.Interaction, new_prompt: str):
        """編輯 Modal 回調"""
        try:
            # 這裡需要實際的編輯邏輯，由使用者實作
            await interaction.response.send_message(
                "✅ 系統提示編輯功能需要由主命令處理器實作",
                ephemeral=True
            )
            
        except Exception as e:
            await func.report_error(e, "Error handling edit callback")
            self.logger.error(f"處理編輯回調時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 編輯時發生錯誤: {str(e)}",
                ephemeral=True
            )
    
    async def _preview_callback(self, interaction: discord.Interaction):
        """預覽按鈕回調"""
        try:
            prompt = self.prompt_data.get('prompt', '未設定')
            source = self.prompt_data.get('source', 'unknown')
            
            # 建立預覽 Embed
            embed = discord.Embed(
                title="🔍 系統提示預覽",
                color=discord.Color.blue()
            )
            
            # 限制預覽長度
            preview_content = prompt[:1000] + "..." if len(prompt) > 1000 else prompt
            embed.add_field(
                name="內容",
                value=f"```\n{preview_content}\n```",
                inline=False
            )
            
            embed.add_field(
                name="來源",
                value=source,
                inline=True
            )
            
            embed.add_field(
                name="長度",
                value=f"{len(prompt)} 字元",
                inline=True
            )
            
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        except Exception as e:
            await func.report_error(e, "Error handling preview")
            self.logger.error(f"處理預覽時發生錯誤: {e}")
            await interaction.response.send_message(
                f"❌ 預覽時發生錯誤: {str(e)}",
                ephemeral=True
            )
    
    async def on_timeout(self):
        """處理超時"""
        try:
            # 禁用所有按鈕
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
        except Exception as e:
            await func.report_error(e, "Error handling View timeout")
            self.logger.error(f"處理 View 超時時發生錯誤: {e}")


def create_system_prompt_embed(prompt_data: Dict[str, Any], 
                              channel: Optional[discord.TextChannel] = None) -> discord.Embed:
    """
    建立系統提示的 Embed
    
    Args:
        prompt_data: 提示資料
        channel: 頻道物件（可選）
        
    Returns:
        Discord Embed 物件
    """
    embed = discord.Embed(
        title="🤖 系統提示設定",
        color=discord.Color.green()
    )
    
    # 提示內容
    prompt = prompt_data.get('prompt', '未設定')
    if len(prompt) > 1000:
        preview = prompt[:1000] + "..."
        embed.add_field(
            name="系統提示（預覽）",
            value=f"```\n{preview}\n```",
            inline=False
        )
    else:
        embed.add_field(
            name="系統提示",
            value=f"```\n{prompt}\n```" if prompt else "未設定",
            inline=False
        )
    
    # 來源資訊
    source = prompt_data.get('source', 'unknown')
    source_names = {
        'yaml': 'YAML 基礎提示',
        'server': '伺服器預設 + YAML',
        'channel': '頻道特定 + 伺服器預設 + YAML',
        'cache': '快取'
    }
    
    embed.add_field(
        name="來源",
        value=source_names.get(source, source),
        inline=True
    )
    
    # 提示長度
    embed.add_field(
        name="長度",
        value=f"{len(prompt)} 字元",
        inline=True
    )
    
    # 語言設定
    if 'language' in prompt_data:
        embed.add_field(
            name="語言",
            value=prompt_data['language'],
            inline=True
        )
    
    # 頻道資訊
    if channel:
        embed.add_field(
            name="頻道",
            value=f"#{channel.name}",
            inline=True
        )
    
    # 時間戳記
    if 'timestamp' in prompt_data:
        embed.timestamp = discord.utils.utcnow()
    
    return embed