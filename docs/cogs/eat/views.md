# File: `cogs/eat/views.py`

## Overview
Core logic and functionalities for views.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `DislikeModal`
Modal for users to provide feedback on disliked restaurants.

- **Attributes**:
  - `db` (`Any`): Instance attribute.
  - `record_id` (`Any`): Instance attribute.
  - `detail_view` (`Any`): Instance attribute.
  - `lang_manager` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DB, record_id: int, detail_view: EatDetailView, lang_manager: Any, guild_id: str) -> Any`: Executes __init__ operation.
  - `on_submit(interaction: discord.Interaction) -> Any`: Handle modal submission.

### `EatDetailView`
Interactive View after selecting a single restaurant.

- **Attributes**:
  - `result` (`Any`): Instance attribute.
  - `db` (`Any`): Instance attribute.
  - `record_id` (`Any`): Instance attribute.
  - `discord_id` (`Any`): Instance attribute.
  - `provider` (`Any`): Instance attribute.
  - `keyword` (`Any`): Instance attribute.
  - `browse_results` (`Any`): Instance attribute.
  - `browse_index` (`Any`): Instance attribute.
  - `lang_manager` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `_rated` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(result: dict, db: DB, record_id: int, discord_id: str, provider: Any, keyword: str, browse_results: list, browse_index: int, lang_manager: Any, guild_id: str) -> Any`: Executes __init__ operation.
  - `_update_labels() -> Any`: Update button labels based on localization.
  - `map_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Provide a link to Google Maps for the selected restaurant.
  - `menu_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Display a menu image if available.
  - `review_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Generate food reviews using LangChain streaming.
  - `like_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Record positive feedback for the restaurant.
  - `dislike_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Record negative feedback and open a reason modal.
  - `back_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Return to the multi-result browsing View.
  - `on_timeout() -> Any`: Disable all buttons when the View times out.

### `EatBrowseView`
Multi-result browsing View, supporting pagination and dropdown selection.

- **Attributes**:
  - `results` (`Any`): Instance attribute.
  - `keyword` (`Any`): Instance attribute.
  - `db` (`Any`): Instance attribute.
  - `discord_id` (`Any`): Instance attribute.
  - `provider` (`Any`): Instance attribute.
  - `current_index` (`Any`): Instance attribute.
  - `lang_manager` (`Any`): Instance attribute.
  - `guild_id` (`Any`): Instance attribute.
  - `_max_viewed_index` (`Any`): Instance attribute.
  - `_is_fetching` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(results: list, keyword: str, db: DB, discord_id: str, provider: Any, initial_index: int, lang_manager: Any, guild_id: str) -> Any`: Executes __init__ operation.
  - `_update_labels() -> Any`: Update button labels based on localization.
  - `_background_prefetch() -> Any`: Complete detailed restaurant info in the background.
  - `_rebuild_select() -> Any`: Rebuild the dropdown selection menu.
  - `_select_callback(interaction: discord.Interaction) -> Any`: Handle restaurant selection from dropdown.
  - `_update_nav_buttons() -> Any`: Enable or disable navigation buttons based on current index.
  - `prev_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Go to the previous restaurant result.
  - `next_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Go to the next restaurant result.
  - `confirm_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Confirm the current restaurant selection.
  - `regenerate_button(interaction: discord.Interaction, button: discord.ui.Button) -> Any`: Cycle to the next recommended restaurant, performing real-time fetch if needed.
  - `on_timeout() -> Any`: Disable all buttons when the View times out.
