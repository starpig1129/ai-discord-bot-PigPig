# Performance Cog

**File:** [`cogs/performance.py`](cogs/performance.py)

This cog provides a command for the bot owner to view performance metrics. It is a tool for monitoring the bot's operational efficiency and resource usage.

## Features

*   **Owner-only Access:** The command is restricted to the bot owner for security and administrative purposes.
*   **Integration with Performance Monitor:** It fetches data from the `performance_monitor` instance, which is responsible for collecting metrics throughout the bot's runtime.
*   **Clear Data Presentation:** Displays statistics in a clean, embedded format, separating timers from counters.

## Main Command

### `/perf_stats`

Displays a collection of performance statistics for the bot.

*   **Permissions:** Bot Owner Only
*   **Returns:** An ephemeral embed containing the following information:
    *   **Uptime:** The total duration the bot has been running since its last restart.
    *   **Timers:** Detailed metrics for timed operations, such as:
        *   Average execution time.
        *   Total time spent on the operation.
        *   The number of times the operation was performed.
    *   **Counters:** Counts of various events, such as:
        *   Total messages processed.
        *   Commands executed.
        *   Cache hit rate.

## Core Logic

The `perf_stats` command retrieves a dictionary of statistics from `self.bot.performance_monitor.get_performance_stats()`. It then iterates through this dictionary, formatting the timer and counter data into fields within a Discord embed. The uptime is calculated from the `session_duration_seconds` value and formatted into a human-readable string.