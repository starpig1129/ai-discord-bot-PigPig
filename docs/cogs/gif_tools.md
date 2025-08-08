# GIF Tools Cog

**File:** [`cogs/gif_tools.py`](cogs/gif_tools.py)

This cog provides tools for searching and retrieving GIFs using the Tenor API. It is designed to be used both as a direct user command and as a backend tool for other systems, such as the AI.

## Features

*   **Tenor API Integration:** Connects to the Tenor API to search for GIFs based on a query.
*   **Randomized Results:** The search is configured to return a random GIF from the results to provide variety.
*   **Dual Interface:**
    *   A `/search_gif` slash command for users.
    *   A `get_gif_url` method for programmatic use by other cogs or AI tools.

## Main Command

### `/search_gif`

Searches for a GIF and sends a random result to the channel.

*   **Parameters:**
    *   `query` (str): The search term for the GIF (e.g., "happy cat").

## Core Methods

### `async search_gif(self, query: str, limit: int = 1) -> list`

This is the core function that communicates with the Tenor API.

*   **Parameters:**
    *   `query` (str): The search term.
    *   `limit` (int): The number of results to fetch. Defaults to 1.
*   **Returns:** A list of GIF URLs. Returns an empty list if the search fails or no results are found.

### `async get_gif_url(self, query: str) -> str`

A convenience wrapper around `search_gif` designed for programmatic use. It searches for a GIF and returns the URL of a single, randomly chosen result.

*   **Parameters:**
    *   `query` (str): The search term.
*   **Returns:** A single GIF URL as a string, or an empty string if no GIF is found.