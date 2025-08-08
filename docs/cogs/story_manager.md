# Story Manager Cog

**File:** [`cogs/story_manager.py`](cogs/story_manager.py)

This cog serves as the main entry point for the bot's interactive storytelling feature. It is designed with a UI-first approach, centralizing all user interactions through a single command group.

## Dependencies

This cog is the command interface for the **[Story System](./story/index.md)**. It relies on the `StoryManager` and `UIManager` from the story library, as well as the `SystemPromptManager` for handling prompts.

## UI-Driven Design

The cog is intentionally lightweight and acts primarily as a dispatcher. All complex logic is handled by the managers in the `cogs/story/` library. The user experience is centered around interactive UI components (buttons, modals, select menus) rather than a complex web of text commands.

## Commands

### `/story menu`

This is the primary and most important command for the story mode. It opens the main story management menu.

*   **Behavior:** The menu displayed is context-aware.
    *   If no story is active in the channel, it shows a menu with options to **create a new world**, **define characters**, and **start a new story**.
    *   If a story is already in progress, it displays a control panel with options to **join the story**, **pause**, **end the story**, etc.

### `/story intervene`

Allows a user to provide out-of-character (OOC) instructions to the "Director" (the LLM controlling the story). This is useful for steering the narrative or correcting course if the story goes in an undesirable direction.

*   **Behavior:** This command opens a modal where the user can type their intervention. The `StoryManager` then incorporates this instruction into its next generation step.
*   **Usage Condition:** A story must be active in the channel for this command to work.

## Event Handling

### `handle_story_message(self, message: discord.Message)`

This method is not a command but a crucial event handler. It is called by the main `on_message` event in the bot's core whenever a message is sent in a channel that is set to "story mode".

*   **Function:** It passes the user's message to the `StoryManager` to be processed as part of the ongoing story. This is how players interact with and advance the narrative.