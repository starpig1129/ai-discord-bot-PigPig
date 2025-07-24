# Story System - Story Manager

**File:** [`cogs/story/manager.py`](cogs/story/manager.py)

The `StoryManager` is the central orchestrator of the story system. It implements the layered AI agent architecture and coordinates all other components to drive the narrative forward.

## `StoryManager` Class

### `__init__(self, bot, cog, system_prompt_manager)`

Initializes the manager and its dependencies.

*   **Dependencies:**
    *   `StoryDB` & `CharacterDB`: For all database interactions.
    *   `StoryPromptEngine`: To build prompts for the AI agents.
    *   `StoryStateManager`: To apply state updates from the AI's plan.
    *   `MemoryManager`: To potentially inject long-term memories into the context.
    *   `LanguageManager`: For localization.

### `async process_story_message(self, message: discord.Message)`

This is the main entry point for the story generation pipeline, called every time a user sends a message in a story channel.

*   **Process (Layered AI Agent Pipeline):**
    1.  **GM Agent Call:** It first calls the `StoryPromptEngine` to build a comprehensive prompt for the "Director" (GM) agent. This prompt includes the world state, character details, recent events, and the user's latest message.
    2.  **Plan Generation:** It sends this prompt to the LLM, instructing it to return a structured `GMActionPlan` JSON object. This plan dictates the next story beat.
    3.  **Plan Execution:** The manager parses the `GMActionPlan`.
        *   If the plan's `action_type` is `NARRATE`, it sends the narration content directly to the channel.
        *   If the `action_type` is `DIALOGUE`, it proceeds to the next layer.
    4.  **Actor Agent Calls:** For a `DIALOGUE` action, the manager iterates through the `dialogue_context` list provided in the GM's plan. For each character scheduled to speak:
        *   It calls the `StoryPromptEngine` again to build a specific prompt for that "Actor" (Character) agent. This prompt includes the character's personality and the Director's specific instructions (motivation, emotional state).
        *   It sends this prompt to the LLM, instructing it to return a `CharacterAction` JSON object containing the character's speech, actions, and thoughts.
        *   The character's response is sent to the channel. The state (location, time) from this action becomes the authoritative state for the *next* actor in the sequence.
    5.  **State Update:** After the plan is fully executed, it uses the final authoritative state (from the last actor's action) to update the `StoryInstance` via the `StoryStateManager`. It also updates any player-NPC relationships defined in the GM's plan.
    6.  **Event Recording:** The entire sequence of events is recorded as a single `Event` in the world's history.
    7.  **Summary & Outline Generation:** It maintains a message counter. After a certain number of messages (e.g., 20), it automatically triggers `_generate_and_save_summary` to create a summary of recent events. After a certain number of summaries (e.g., 10), it triggers `_generate_and_save_outline` to create a higher-level plot outline. These are then fed back into the GM's context in future turns.

### Other Key Methods

*   **`start_story(...)`:** Initializes a new `StoryInstance` in the database and calls `generate_first_scene` to kick off the narrative.
*   **`generate_first_scene(...)`:** A special method that calls the GM agent with a prompt specifically designed to generate the opening narration for the story.
*   **`add_intervention(...)`:** Stores an out-of-character instruction from a user, which will be injected with high priority into the next GM prompt.