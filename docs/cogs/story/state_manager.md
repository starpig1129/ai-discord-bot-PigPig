# Story System - State Manager

**File:** [`cogs/story/state_manager.py`](cogs/story/state_manager.py)

The `StoryStateManager` is a focused utility responsible for applying state changes to a `StoryInstance` based on the structured plan provided by the Director (GM) agent.

## `StoryStateManager` Class

### `__init__(self, bot)`

Initializes the state manager.

### `async update_state_from_gm_plan(self, instance: StoryInstance, gm_plan: GMActionPlan) -> StoryInstance`

This is the primary method of the class. It takes the current story instance and the `GMActionPlan` from the Director AI and applies the planned updates.

*   **Parameters:**
    *   `instance` (StoryInstance): The current state of the story.
    *   `gm_plan` (GMActionPlan): The structured plan from the Director AI.
*   **Process:**
    1.  **Core State Update:** It checks the `state_update` field of the plan. If it exists, it updates the `instance`'s `current_location`, `current_date`, and `current_time` with the new values from the plan.
    2.  **Relationship Logging:** It logs any relationship updates specified in the `relationships_update` field of the plan. The actual database update for relationships is handled in the `StoryManager`.
    3.  **Event Log Management:** It ensures the `event_log` on the story instance does not grow indefinitely by trimming it to the last 20 entries.
*   **Returns:** The modified `StoryInstance` object with the updated state.

### `initialize_default_state(self, instance: StoryInstance) -> StoryInstance`

A helper method to set up default values for a new story instance, such as setting the initial weather to "sunny".