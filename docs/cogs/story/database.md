# Story System - Database

**File:** [`cogs/story/database.py`](cogs/story/database.py)

This module handles all data persistence for the story system. It is uniquely designed with two separate database classes to manage global and server-specific data.

## `CharacterDB` Class (Global)

This class manages a single, global database file: `data/story/characters.db`. This database stores all characters created across all servers the bot is in.

*   **Purpose:** To create a shared repository of characters. A character created on one server can potentially be used in another, depending on its `is_public` flag.
*   **Key Methods:**
    *   `save_character(...)`: Saves or updates a `StoryCharacter` object.
    *   `get_character(...)`: Retrieves a single character by its unique ID.
    *   `get_characters_by_guild(...)`: Retrieves all characters associated with a specific server.
    *   `get_selectable_characters(...)`: Retrieves all characters a specific user is allowed to use in a story. This includes all public characters in the server plus any private characters created by that user.
    *   `delete_character(...)`: Deletes a character from the database.

## `StoryDB` Class (Per-Guild)

This class manages a separate database file for each server (guild), located at `data/story/{guild_id}_story.db`.

*   **Purpose:** To keep all story-related data completely isolated between servers. One server's worlds, ongoing stories, and character relationships cannot be accessed by another.
*   **Key Methods:**
    *   **World Management:**
        *   `save_world(...)`: Saves or updates a `StoryWorld` object, serializing its complex nested data (locations, events) into JSON format for storage.
        *   `get_world(...)`: Retrieves and deserializes a `StoryWorld` object from the database.
        *   `get_all_worlds()`: Gets a list of all worlds created on that server.
    *   **Instance Management:**
        *   `save_story_instance(...)`: Saves or updates a `StoryInstance`, which represents an active story in a specific channel. This includes the current state, active characters, summaries, and outlines.
        *   `get_story_instance(...)`: Retrieves the active story for a specific channel.
    *   **Relationship Management:**
        *   `save_player_relationship(...)`: Saves or updates the description of the relationship between a player (user) and an NPC (character).
        *   `get_relationships_for_story(...)`: Retrieves all relationship data for an ongoing story.