# File: `cogs/system_prompt/ui.py`

## Overview
頻道系統提示管理模組的 UI 元件 This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `SystemPromptModal`
系統提示設定的 Modal 對話框

- **Attributes**:
  - `callback_func` (`Any`): Instance attribute.
  - `manager` (`Any`): Instance attribute.
  - `channel_id` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `prompt_input` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(title: str, prompt_label: str, prompt_placeholder: str, initial_value: str, callback_func: Optional[Callable], manager: Any, channel_id: str, guild_id: str, show_default_content: bool, **kwargs) -> Any`: 初始化 Modal 對話框
  - `_restore_variable_placeholders(prompt: str, manager: Any) -> str`: 還原變數占位符格式
  - `on_submit(interaction: discord.Interaction) -> Any`: 處理 Modal 提交
  - `on_error(interaction: discord.Interaction, error: Exception) -> Any`: 處理 Modal 錯誤

### `SystemPromptModuleModal`
模組設定的 Modal 對話框

- **Attributes**:
  - `module_name` (`Any`): Instance attribute.
  - `callback_func` (`Any`): Instance attribute.
  - `manager` (`Any`): Instance attribute.
  - `module_description` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `module_input` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(module_name: str, initial_value: str, callback_func: Optional[Callable], manager: Any, lang: str, show_default_content: bool, **kwargs) -> Any`: 初始化模組設定 Modal
  - `on_submit(interaction: discord.Interaction) -> Any`: 處理模組 Modal 提交

### `ConfirmationView`
確認對話框 View

- **Attributes**:
  - `result` (`Any`): Instance attribute.
  - `confirmed` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `confirm_button` (`Any`): Instance attribute.
  - `cancel_button` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(confirm_text: str, cancel_text: str, confirm_style: discord.ButtonStyle, timeout: float, **kwargs) -> Any`: 初始化確認對話框
  - `_confirm_callback(interaction: discord.Interaction) -> Any`: 確認按鈕回調
  - `_cancel_callback(interaction: discord.Interaction) -> Any`: 取消按鈕回調
  - `on_timeout() -> Any`: 處理超時

### `ChannelSelectView`
頻道選擇器 View

- **Attributes**:
  - `callback_func` (`Any`): Instance attribute.
  - `selected_channel` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(channels: List[discord.TextChannel], placeholder: str, callback_func: Optional[Callable], timeout: float, **kwargs) -> Any`: 初始化頻道選擇器
  - `_select_callback(interaction: discord.Interaction) -> Any`: 選擇器回調

### `ModuleSelectView`
模組選擇器 View

- **Attributes**:
  - `callback_func` (`Any`): Instance attribute.
  - `selected_modules` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(modules: List[str], placeholder: str, callback_func: Optional[Callable], timeout: float, **kwargs) -> Any`: 初始化模組選擇器
  - `_select_callback(interaction: discord.Interaction) -> Any`: 模組選擇器回調

### `SystemPromptView`
系統提示管理的主要 View

- **Attributes**:
  - `prompt_data` (`Any`): Instance attribute.
  - `can_edit` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `preview_button` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(prompt_data: Dict[Tuple[str, Any]], can_edit: bool, timeout: float, **kwargs) -> Any`: 初始化系統提示 View
  - `_edit_callback(interaction: discord.Interaction) -> Any`: 編輯按鈕回調
  - `_edit_modal_callback(interaction: discord.Interaction, new_prompt: str) -> Any`: 編輯 Modal 回調
  - `_preview_callback(interaction: discord.Interaction) -> Any`: 預覽按鈕回調
  - `on_timeout() -> Any`: 處理超時

## Functions

### `create_system_prompt_embed(prompt_data: Dict[Tuple[str, Any]], channel: Optional[discord.TextChannel]) -> discord.Embed`
建立系統提示的 Embed Plays a key role in the system logic.
