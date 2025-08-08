# Reminder Cog

**File:** [`cogs/remind.py`](cogs/remind.py)

This cog provides a user-friendly reminder feature. Users can set reminders for themselves or others using natural language for the timing.

## Features

*   **Flexible Time Parsing:** Understands both relative time ("10 minutes later", "2 hours later") and absolute time ("2023-12-31 20:00:00").
*   **Multi-language Support:** The time parser recognizes time units in multiple languages (e.g., "分鐘", "minutes", "分"). All user-facing messages are localized.
*   **User Targeting:** A user can set a reminder for another user in the server.
*   **Asynchronous Operation:** Reminders are handled by background `asyncio` tasks, ensuring the bot remains responsive while waiting to send a reminder.

## Main Command

### `/remind`

Sets a reminder.

*   **Parameters:**
    *   `time` (str): The time for the reminder. This can be a relative duration or a specific date and time.
    *   `message` (str): The content of the reminder message.
    *   `user` (Optional[discord.User]): The user to remind. If not provided, the reminder is set for the person who invoked the command.

### Example Usage

```
/remind time: "30 minutes later" message: "Check on the server status."
/remind time: "2024-01-01 00:00:00" message: "Happy New Year!" user: @SomeUser
```

## Core Logic

### `_set_reminder_logic(...)`

This is the central function that contains the logic for setting a reminder. It is designed to be reusable, potentially by an LLM tool in the future.

1.  It calls `parse_time()` to convert the user's time string into a `datetime` object.
2.  It calculates the time difference between now and the target reminder time.
3.  It sends a confirmation message to the user, letting them know the reminder has been set.
4.  It creates an `asyncio.create_task()` to run the `reminder_task` in the background.

### `reminder_task()`

This background task simply sleeps for the required duration and then sends the reminder message to the original channel, mentioning the target user.

### `parse_time(self, time_str: str, ...)`

This utility function is key to the cog's flexibility. It uses a series of regular expressions to match relative time formats in different languages. If no relative time format is matched, it attempts to parse the string as an absolute timestamp using several common formats.