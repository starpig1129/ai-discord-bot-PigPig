"""
頻道系統提示管理模組的 UI 元件

提供 Discord UI 元件，包含 Modal 對話框、確認按鈕、選擇器等。
"""

import discord
from typing import Optional, Dict, Any, Callable, List
import logging

from .exceptions import ValidationError, ContentTooLongError


class SystemPromptModal(discord.ui.Modal):
    """系統提示設定的 Modal 對話框"""
    
    def __init__(self, 
                 title: str = "設定系統提示",
                 prompt_label: str = "系統提示內容",
                 prompt_placeholder: str = "請輸入系統提示內容...",
                 initial_value: str = "",
                 callback_func: Optional[Callable] = None,
                 **kwargs):
        """
        初始化 Modal 對話框
        
        Args:
            title: Modal 標題
            prompt_label: 提示輸入框標籤
            prompt_placeholder: 提示輸入框佔位文字
            initial_value: 初始值
            callback_func: 回調函式
            **kwargs: 其他參數
        """
        super().__init__(title=title, **kwargs)
        self.callback_func = callback_func
        self.logger = logging.getLogger(__name__)
        
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
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理 Modal 提交"""
        try:
            prompt_content = self.prompt_input.value.strip()
            
            if not prompt_content:
                await interaction.response.send_message(
                    "❌ 系統提示內容不能為空", 
                    ephemeral=True
                )
                return
            
            if self.callback_func:
                await self.callback_func(interaction, prompt_content)
            else:
                await interaction.response.send_message(
                    "✅ 系統提示已設定",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"處理 Modal 提交時發生錯誤: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 處理請求時發生錯誤: {str(e)}",
                    ephemeral=True
                )
    
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
                 **kwargs):
        """
        初始化模組設定 Modal
        
        Args:
            module_name: 模組名稱
            initial_value: 初始值
            callback_func: 回調函式
            **kwargs: 其他參數
        """
        super().__init__(title=f"設定模組: {module_name}", **kwargs)
        self.module_name = module_name
        self.callback_func = callback_func
        self.logger = logging.getLogger(__name__)
        
        # 模組內容輸入框
        self.module_input = discord.ui.TextInput(
            label=f"{module_name} 模組內容",
            placeholder=f"請輸入 {module_name} 模組的內容...",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            default=initial_value,
            required=True
        )
        self.add_item(self.module_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """處理模組 Modal 提交"""
        try:
            module_content = self.module_input.value.strip()
            
            if not module_content:
                await interaction.response.send_message(
                    f"❌ {self.module_name} 模組內容不能為空",
                    ephemeral=True
                )
                return
            
            if self.callback_func:
                await self.callback_func(interaction, self.module_name, module_content)
            else:
                await interaction.response.send_message(
                    f"✅ {self.module_name} 模組已設定",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"處理模組 Modal 提交時發生錯誤: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ 設定模組時發生錯誤: {str(e)}",
                    ephemeral=True
                )


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