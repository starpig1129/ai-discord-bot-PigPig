# File: `cogs/system_prompt/views.py`

## Overview
系統提示管理的統一 UI 選單系統 This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `LocalizedView`
Base class for all system-prompt views.

- **Attributes**:
  - `manager` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `_bot` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `_t(*keys) -> str`: Translate *keys* using the guild's language.

### `SystemPromptMainView`
系統提示管理主選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `_setup_main_buttons() -> Any`: 設定主要功能按鈕
  - `function_callback(interaction: discord.Interaction, function: str) -> Any`: 處理功能按鈕回調
  - `_handle_set_function(interaction: discord.Interaction) -> Any`: Executes _handle_set_function operation.
  - `_handle_view_function(interaction: discord.Interaction) -> Any`: Executes _handle_view_function operation.
  - `_handle_copy_function(interaction: discord.Interaction) -> Any`: Executes _handle_copy_function operation.
  - `_handle_remove_function(interaction: discord.Interaction) -> Any`: Executes _handle_remove_function operation.
  - `_handle_reset_function(interaction: discord.Interaction) -> Any`: Executes _handle_reset_function operation.
  - `_handle_reload_function(interaction: discord.Interaction) -> Any`: Executes _handle_reload_function operation.

### `SystemPromptFunctionButton`
系統提示功能按鈕

- **Attributes**:
  - `function` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(function: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: 按鈕回調

### `SystemPromptSetView`
設定系統提示的子選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `scope_callback(interaction: discord.Interaction, scope: str) -> Any`: Executes scope_callback operation.

### `EditModeSelectionView`
編輯模式選擇選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `scope` (`Any`): Instance attribute.
  - `target_channel` (`Any`): Instance attribute.
  - `scope_text` (`Any`): Instance attribute.
  - `guild` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, scope: str, target_channel: Optional[discord.TextChannel], scope_text: str, guild: discord.Guild, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `edit_mode_callback(interaction: discord.Interaction, edit_mode: str) -> Any`: 處理編輯模式選擇
  - `_handle_direct_edit(interaction: discord.Interaction) -> Any`: 處理直接編輯提示
  - `_restore_variable_placeholders(prompt: str, guild_id: str) -> str`: 將已替換的變數還原為占位符格式，以便編輯時顯示原始模板
  - `_handle_module_edit(interaction: discord.Interaction) -> Any`: 處理模組化編輯
  - `_handle_direct_set_callback(interaction: discord.Interaction, content: str) -> Any`: 處理直接設定回調

### `EditModeButton`
編輯模式按鈕

- **Attributes**:
  - `edit_mode` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(edit_mode: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `SystemPromptScopeButton`
範圍選擇按鈕

- **Attributes**:
  - `scope` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(scope: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `SystemPromptViewOptionsView`
查看配置選項選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `view_callback(interaction: discord.Interaction, view_type: str) -> Any`: 處理查看回調

### `SystemPromptViewButton`
查看選項按鈕

- **Attributes**:
  - `view_type` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(view_type: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `ModuleEditView`
Represents ModuleEditView.

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `modules` (`Any`): Instance attribute.
  - `guild` (`Any`): Instance attribute.
  - `scope` (`Any`): Instance attribute.
  - `target_channel` (`Any`): Instance attribute.
  - `scope_text` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `selected_scope` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, modules: List[str], guild: discord.Guild, scope: Optional[str], target_channel: Optional[discord.TextChannel], scope_text: Optional[str], guild_id: str, timeout: float) -> Any`: Executes __init__ operation.
  - `_setup_scope_selector() -> Any`: Executes _setup_scope_selector operation.
  - `_setup_module_selector() -> Any`: Executes _setup_module_selector operation.
  - `scope_callback(interaction: discord.Interaction, scope: str) -> Any`: Executes scope_callback operation.

### `ModuleScopeButton`
模組範圍選擇按鈕

- **Attributes**:
  - `scope` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(scope: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `ModuleSelect`
模組選擇器

- **Attributes**:
  - `manager` (`Any`): Instance attribute.
  - `scope` (`Any`): Instance attribute.
  - `channel` (`Any`): Instance attribute.
  - `guild` (`Any`): Instance attribute.
  - `scope_text` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, scope: str, channel: Optional[discord.TextChannel], guild: discord.Guild, scope_text: Optional[str], **kwargs) -> Any`: Executes __init__ operation.
  - `_update_option_descriptions() -> Any`: 更新選項的說明文字 (基於語言管理器)
  - `callback(interaction: discord.Interaction) -> Any`: 選擇器回調
  - `_handle_module_callback(interaction: discord.Interaction, module_name: str, content: str) -> Any`: 處理模組編輯回調

### `SystemPromptCopyView`
複製系統提示選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `guild` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild: discord.Guild, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.

### `SystemPromptRemoveView`
移除系統提示的子選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.

### `SystemPromptResetView`
重置系統提示的子選單

- **Attributes**:
  - `permission_validator` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: SystemPromptManager, permission_validator: PermissionValidator, guild_id: str, timeout: float) -> Any`: Executes __init__ operation.

### `BackButton`
返回主選單按鈕

- **Attributes**:
  - `guild_id` (`str`): Instance attribute.
  - `_bot` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(row: int, guild_id: str, bot: Any) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: 返回主選單

### `ChannelSelect`
頻道選擇器（用於複製功能）

- **Attributes**:
  - `selected_channel_id` (`Optional[str]`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(**kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `CopyExecuteButton`
執行複製按鈕

- **Attributes**:
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(label: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `RemoveButton`
移除按鈕

- **Attributes**:
  - `remove_type` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(label: str, remove_type: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.

### `ResetButton`
重置按鈕

- **Attributes**:
  - `reset_type` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(label: str, reset_type: str, **kwargs) -> Any`: Executes __init__ operation.
  - `callback(interaction: discord.Interaction) -> Any`: Executes callback operation.
