# File: `cogs/story/ui/views.py`

## Overview
Core logic and functionalities for views.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `InitialStoryView`
初始故事視圖

- **Attributes**:
  - `story_manager` (`Any`): Instance attribute.
  - `ui_manager` (`Any`): Instance attribute.
  - `channel_id` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `selected_world` (`Optional[str]`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: StoryManager, channel_id: int, guild_id: int, ui_manager: UIManager) -> Any`: Executes __init__ operation.
  - `on_timeout() -> Any`: 視圖超時處理
  - `world_select(interaction: discord.Interaction, select: discord.ui.Select) -> Any`: 世界選擇選單
  - `create_world_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 創建世界按鈕
  - `create_character_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 創建角色按鈕
  - `load_default_character_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 從預設載入角色按鈕
  - `start_story_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 開始故事按鈕
  - `_refresh_world_select() -> Any`: 重新整理世界選擇選單

### `ActiveStoryView`
進行中故事視圖

- **Attributes**:
  - `story_manager` (`Any`): Instance attribute.
  - `story_instance` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(manager: StoryManager, story_instance: StoryInstance) -> Any`: Executes __init__ operation.
  - `_update_narration_button_state() -> Any`: 更新旁白切換按鈕的狀態
  - `_update_pause_button_state() -> Any`: 更新暫停/恢復按鈕的狀態
  - `join_story_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 加入故事按鈕
  - `pause_story_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 暫停故事按鈕（管理員專用）
  - `toggle_narration_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 切換旁白功能的按鈕
  - `end_story_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 結束故事按鈕（管理員專用）

### `NPCSelectView`
NPC 選擇視圖

- **Attributes**:
  - `story_manager` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `channel_id` (`Any`): Instance attribute.
  - `world_name` (`Any`): Instance attribute.
  - `initial_date` (`Any`): Instance attribute.
  - `initial_time` (`Any`): Instance attribute.
  - `initial_location` (`Any`): Instance attribute.
  - `characters` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.
  - `npc_select` (`Any`): Instance attribute.

- **Methods**:
  - `create(manager: StoryManager, interaction: discord.Interaction, channel_id: int, world_name: str, initial_date: Optional[str], initial_time: Optional[str], initial_location: str, system_prompt: str) -> NPCSelectView`: 非同步工廠方法，用於創建和填充 NPCSelectView。
  - `__init__(manager: StoryManager, guild_id: int, channel_id: int, world_name: str, initial_date: Optional[str], initial_time: Optional[str], initial_location: str, characters: List[StoryCharacter], options: List[discord.SelectOption]) -> Any`: Executes __init__ operation.
  - `npc_select_callback(interaction: discord.Interaction) -> Any`: 處理 NPC 選擇的回調
  - `confirm_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: 確認選擇並將邏輯委派給 StoryManager 開始故事
