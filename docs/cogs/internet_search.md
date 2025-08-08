# Internet Search Cog

**File:** [`cogs/internet_search.py`](cogs/internet_search.py)

This cog provides a versatile set of tools for searching the internet from within Discord. It acts as a gateway to various search functionalities, including general web search, image search, YouTube search, and more.

## Features

*   **Unified Search Interface:** A single entry point, `internet_search`, routes requests to the appropriate specialized search function.
*   **Web Scraping:** Uses `selenium` and `BeautifulSoup` for robust web and image searches, mimicking human interaction to avoid blocks.
*   **YouTube Search:** Integrates with the `youtube_search` library to find videos.
*   **URL Content Fetching:** Can extract the main text content from a given URL.
*   **Specialized "Eat" Search:** Includes a unique feature to recommend restaurants, integrated with its own database and machine learning model.

## Core Method

### `async internet_search(self, ctx, query, search_type, ...)`

This is the main method that delegates tasks to other search functions based on the `search_type`.

*   **Parameters:**
    *   `ctx`: The command context.
    *   `query` (str): The search term or URL.
    *   `search_type` (str): The type of search to perform. Can be `general`, `image`, `youtube`, `url`, or `eat`.
*   **Returns:** A string containing the search results, or `None` if the result is sent directly (e.g., an image or embed).

## Search Functions

### `google_search(self, ...)`

Performs a standard Google search and returns the top text results, including titles, snippets, and links.

### `send_img(self, ...)`

Performs a Google Image search. It downloads a set of potential images, uses Structural Similarity Index (SSIM) to find the best match for the clicked thumbnail, and sends the highest quality image to the channel.

### `youtube_search(self, ...)`

Searches YouTube for videos matching the query and returns a randomly selected result from the top 5 hits.

### `fetch_page_content(self, ...)`

Takes a URL, fetches the webpage, strips away common non-content elements (like headers, footers, and nav bars), and returns the clean text content.

### `eat_search(self, ...)`

A specialized search for food recommendations.
*   If no keyword is provided, it uses a trained model to predict a recommendation based on the server's history.
*   If a keyword is provided, it searches for that type of food.
*   It uses a `GoogleMapCrawler` to find restaurant details and presents the result in an interactive embed with voting buttons.
*   The results are used to further train the recommendation model for the server.