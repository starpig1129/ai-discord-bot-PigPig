# Schedule Manager Cog

**File:** [`cogs/schedule.py`](cogs/schedule.py)

This cog allows users to manage personal schedules by uploading, querying, and updating YAML files. It's designed for users to keep track of their weekly recurring events.

## Features

*   **YAML-based Schedules:** Schedules are defined in a simple and human-readable YAML format.
*   **Per-user Storage:** Each user's schedule is stored in a separate file named after their Discord ID (`data/schedule/{user_id}.yaml`).
*   **Permission Checks:** When querying another user's schedule, the cog checks if both the querier and the target user have read access to the channel where the schedule was originally uploaded.
*   **Flexible Queries:** Users can view a full schedule, query for events at a specific time, or find their next upcoming event.

## Commands

### `/upload_schedule`

Uploads a YAML schedule file for the user.

*   **Parameters:**
    *   `file` (discord.Attachment): The YAML file to upload.
*   **Note:** The channel where this command is used is saved and used for future permission checks.

### `/query_schedule`

Queries a user's schedule.

*   **Parameters:**
    *   `query_type` (Choice): The type of query to perform.
        *   `完整行程表 (Full Schedule)`: Displays the entire weekly schedule.
        *   `特定時間 (Specific Time)`: Shows events occurring at a specific time.
        *   `下一個行程 (Next Event)`: Finds the next scheduled event from the current time.
    *   `time` (Optional[str]): The specific time to query (format: `YYYY-MM-DD HH:MM:SS`), used with `Specific Time`.
    *   `day` (Optional[Choice]): The day of the week to query, used with `Specific Time`.
    *   `target_user` (Optional[discord.Member]): The user whose schedule you want to query. Defaults to yourself.

### `/update_schedule`

Adds a new event to the user's schedule.

*   **Parameters:**
    *   `day` (str): The day of the week for the new event (e.g., "Monday").
    *   `time` (str): The time for the event (format: `HH:MM-HH:MM`).
    *   `description` (str): A description of the event.

### `/show_template`

Displays the template for the schedule YAML file, which users can use as a starting point.

## YAML Format

The schedule is defined in a YAML file with the days of the week as top-level keys. Each day contains a list of events, with each event having a `time` and a `description`.

```yaml
Monday:
  - time: "09:00-10:00"
    description: "Team Meeting"
  - time: "14:00-15:00"
    description: "Project Work"
Tuesday:
  - time: "11:00-12:00"
    description: "Client Call"
# ... and so on for other days