# Story System - UI Manager

**File:** [`cogs/story/ui/ui_manager.py`](cogs/story/ui/ui_manager.py)

The `UIManager` is the central component for handling all user interactions with the story system. It is responsible for displaying the correct menus and modals based on the current state of the story in a channel.

## `UIManager` Class

### `__init__(self, bot, story_manager, ...)`

Initializes the UI manager with instances of the `StoryManager` and other necessary components.

### `async show_main_menu(self, interaction: discord.Interaction)`

This is the primary method of the class, called when a user executes the `/story menu` command.

*   **Behavior:** The method is context-aware.
    1.  It checks the database to see if a `StoryInstance` is currently active in the channel where the command was used.
    2.  **If a story is active:** It displays the `ActiveStoryView`, which contains controls for managing the ongoing story (e.g., pause, end).
    3.  **If no story is active:** It displays the `InitialStoryView`, which provides the setup options for starting a new story (e.g., create world, manage characters, start story).

### UI Views and Modals

The `UIManager` makes use of several custom classes from the `views` and `modals` subdirectories to create the interactive experience.

*   **`InitialStoryView`:** The view for starting a new story. It includes:
    *   Buttons to create a new world, manage characters, or start the story.
    *   A dropdown menu to select an existing world.
*   **`ActiveStoryView`:** The view for managing an ongoing story. It includes buttons to pause, resume, or end the story.
*   **`CharacterCreateModal`:** A popup form (`discord.ui.Modal`) that allows users to input the details for a new character (name, description, etc.).
*   **`InterventionModal`:** A popup form for the `/story intervene` command, allowing users to provide out-of-character directions to the GM agent.

### Helper Methods

*   **`_create_initial_story_embed(...)`:** Creates the embed for the `InitialStoryView`, showing a list of available worlds.
*   **`_create_active_story_embed(...)`:** Creates the embed for the `ActiveStoryView`, showing the status of the current story.
*   **`_update_world_select_options(...)`:** Dynamically populates the world selection dropdown with the worlds available on the server.