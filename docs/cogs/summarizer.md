# Summarizer Cog

**File:** [`cogs/summarizer.py`](cogs/summarizer.py)

This cog provides a powerful AI-driven tool to summarize conversations within a Discord channel. It is designed to handle long conversations and provide concise, actionable summaries with clear source attribution.

## Features

*   **AI-Powered Summarization:** Uses a large language model to generate summaries.
*   **Source Linking:** Each point in the summary is linked back to the original Discord message, allowing for easy context checking.
*   **Dual Limits:** The cog respects both a message count limit and a total character count limit to ensure efficient and cost-effective processing.
*   **Persona Customization:** Users can specify a "persona" for the AI to adopt when writing the summary (e.g., "a professional meeting recorder").
*   **Robust Text Handling:** Includes logic to split long summaries into multiple embeds to avoid Discord's character limits.

## Main Command

### `/summarize`

Generates a summary of the recent conversation in the current channel.

*   **Parameters:**
    *   `limit` (Optional[int]): The maximum number of recent messages to fetch for the summary. Defaults to 100.
    *   `persona` (Optional[str]): A persona for the AI to use while summarizing.
    *   `only_me` (Optional[bool]): If `True`, the summary will be sent as an ephemeral message, visible only to the user who ran the command. Defaults to `False`.

## Core Logic

1.  **Message Fetching:** The command fetches up to `limit` messages from the channel's history.
2.  **Content Formatting:** It iterates through the messages from newest to oldest, formatting them into a structured dialogue history.
    *   Human messages are prefixed with a unique `[MSG-ID]` and include the author and timestamp.
    *   Bot messages are noted but not included in the main content to be summarized.
    *   A mapping of each `MSG-ID` to its `message.jump_url` is created.
3.  **Limit Enforcement:** The process stops when either the message `limit` is reached or the total character count of the formatted history exceeds `MAX_CHAR_COUNT` (15,000 characters).
4.  **AI Invocation:** The formatted and reversed (to be chronological) dialogue history is sent to the language model via `generate_response`. A detailed system prompt instructs the AI on how to structure the summary and, crucially, to include the `[MSG-ID]` tags.
5.  **Post-processing:** After receiving the summary from the AI, the cog uses a regular expression to find all `[MSG-ID]` tags and replaces them with formatted markdown links `[[Source-ID]](jump_url)`, creating the clickable source links.
6.  **Display:** The final, processed summary is sent as one or more embeds.