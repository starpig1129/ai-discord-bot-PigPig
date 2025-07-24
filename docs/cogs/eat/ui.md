# Eat System - User Interface

**Files:**
*   [`cogs/eat/embeds.py`](cogs/eat/embeds.py)
*   [`cogs/eat/views.py`](cogs/eat/views.py)

The user interface for the "Eat What" system is composed of two main parts: embeds, which display information, and views, which contain interactive components like buttons.

## Embeds

The `embeds.py` file contains helper functions to create standardized `discord.Embed` objects for the system.

*   **`eatEmbed(...)`:** Creates the main embed that displays the restaurant recommendation, including the keyword, restaurant name, address, and rating.
*   **`mapEmbed(...)`:** Creates an embed to display the restaurant's location on a map (currently sends a URL directly).
*   **`menuEmbed(...)`:** Creates an embed to display the restaurant's menu, typically by setting an image URL.

## `EatWhatView` Class

Defined in `views.py`, this `discord.ui.View` is the core of the interactive experience. It is attached to the main `eatEmbed` and provides several buttons for the user to interact with the recommendation.

### `__init__(self, result, predict, keyword, db, record_id, discord_id)`

Initializes the view with all the necessary context from the search result and the database.

*   **Parameters:**
    *   `result`: The tuple of restaurant data returned by the `GoogleMapCrawler`.
    *   `predict` (str): The keyword that was predicted by the model (if any).
    *   `keyword` (str): The keyword that was used for the search.
    *   `db` (DB): An instance of the database manager.
    *   `record_id` (int): The ID of the search record in the database, used for updating the rating.
    *   `discord_id` (str): The ID of the server.

### Buttons

*   **地圖 (Map):** Sends the Google Maps URL for the restaurant.
*   **菜單 (Menu):** Displays the restaurant's menu in an embed.
*   **👍 (Like):** Sets the user's rating for this recommendation to `1`. This feedback is saved to the database and triggers a retraining of the server's recommendation model.
*   **👎 (Dislike):** Sets the user's rating to `-1` and triggers a model retraining.
*   **🔄 (Regenerate):** Sets the rating for the current recommendation to `-0.5` (a slight dislike), triggers a model retraining, and then generates a completely new recommendation.
*   **查看評論 (View Reviews):** Uses the Gemini API to generate a witty, AI-powered food review based on the review snippets scraped from Google Maps.