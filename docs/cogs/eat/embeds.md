# File: `cogs/eat/embeds.py`

## Overview
Core logic and functionalities for embeds.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Functions

### `eatEmbed(keyword: str, title: str, address: str, rating: Any, photo_url: str, price_level: int, opening_hours: list, lang_manager: Any, guild_id: str) -> discord.Embed`
Detailed Embed after selecting a restaurant. Plays a key role in the system logic.

### `browseEmbed(results: list, current_index: int, lang_manager: Any, guild_id: str) -> discord.Embed`
Multi-result browsing Embed, showing current restaurant info and pagination progress. Plays a key role in the system logic.

### `loadingEmbed(keyword: str, lang_manager: Any, guild_id: str) -> discord.Embed`
Loading Embed for search in progress. Plays a key role in the system logic.

### `mapEmbed(map_url: str, lang_manager: Any, guild_id: str) -> discord.Embed`
Embed for displaying restaurant map. Plays a key role in the system logic.

### `menuEmbed(menu_url: str, lang_manager: Any, guild_id: str) -> discord.Embed`
Embed for displaying restaurant menu. Plays a key role in the system logic.
