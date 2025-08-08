# Built-in Tools

**Location:** [`gpt/tools/builtin/`](gpt/tools/builtin/)

This directory contains the implementations of the standard tools available to the AI. Each file in this directory defines one or more functions decorated with `@tool`, making them available to the `ToolRegistry`.

These tool functions are designed to be simple wrappers that delegate their core logic to the more complex cogs. This keeps the tool definitions clean and separates the tool interface from the implementation.

## Available Tools

*   **`generate_image`:**
    *   **File:** [`image.py`](./image.md)
    *   **Description:** Generates or edits an image based on a text prompt and an optional base image.
    *   **Delegates to:** `ImageGenerationCog`

*   **`internet_search`:**
    *   **File:** [`internet_search.py`](./internet_search.md)
    *   **Description:** Performs various types of internet searches (general, image, YouTube, etc.).
    *   **Delegates to:** `InternetSearchCog`

*   **`manage_user_data`:**
    *   **File:** [`user_data.py`](./user_data.md)
    *   **Description:** Reads or saves data associated with a specific user.
    *   **Delegates to:** `UserDataCog`

*   **`math` (from `cogs/math.py`):**
    *   **Description:** A secure calculator for mathematical expressions.
    *   **Delegates to:** `MathCalculatorCog`

*   **`reminder` (from `cogs/remind.py`):**
    *   **Description:** Sets a reminder for a user.
    *   **Delegates to:** `ReminderCog`

*   **`schedule` (from `cogs/schedule.py`):**
    *   **Description:** Manages user schedules.
    *   **Delegates to:** `ScheduleManager`