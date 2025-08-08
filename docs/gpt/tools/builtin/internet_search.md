# Built-in Tools - Internet Search

**File:** [`gpt/tools/builtin/internet_search.py`](gpt/tools/builtin/internet_search.py)

This module defines the `internet_search` tool, which acts as a versatile gateway to the various search functionalities provided by the `InternetSearchCog`.

## `@tool` `async def internet_search(...)`

This function allows the AI to perform different kinds of searches on the internet.

*   **Parameters:**
    *   `context` (ToolExecutionContext): The standard execution context.
    *   `query` (str): The search term, URL, or keyword for the search.
    *   `search_type` (Literal["general", "image", "youtube", "url", "eat"]): The specific type of search to perform. This is a required parameter, forcing the AI to be explicit about its search intent.
*   **Logic:**
    1.  It retrieves the `InternetSearchCog` instance from the bot.
    2.  It calls the `internet_search` method on the cog, passing along all the parameters.
    3.  The cog handles the specific logic for the chosen `search_type`.
*   **Returns:** A string containing the result of the search. For search types that send a message directly (like `image` or `eat`), it returns a simple confirmation message.