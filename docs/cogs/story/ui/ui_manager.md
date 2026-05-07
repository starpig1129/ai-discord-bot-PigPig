# File: `cogs/story/ui/ui_manager.py`

## Overview
Core logic and functionalities for ui_manager.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `UIManager`
故事模組的 UI 管理器

- **Attributes**:
  - `bot` (`Any`): Instance attribute.
  - `story_manager` (`Any`): Instance attribute.
  - `character_db` (`Any`): Instance attribute.
  - `system_prompt_manager` (`Any`): Instance attribute.
  - `logger` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(bot: commands.Bot, story_manager: StoryManager, system_prompt_manager: SystemPromptManager) -> Any`: Executes __init__ operation.
  - `show_main_menu(interaction: discord.Interaction) -> Any`: 顯示主要的故事管理選單
  - `_create_initial_story_embed(guild_id: int, channel_id: int) -> discord.Embed`: 創建初始故事選單的 Embed
  - `_create_active_story_embed(story_instance: Any) -> discord.Embed`: 創建進行中故事的 Embed
  - `_update_world_select_options(view: Any, guild_id: int) -> Any`: 更新視圖中的世界選擇選單選項
  - `handle_load_default_character(interaction: discord.Interaction) -> Any`: 處理從頻道預設設定載入角色的請求
  - `show_character_create_modal(interaction: discord.Interaction, name: str, description: str) -> Any`: 顯示角色創建 Modal，可選填預設值
