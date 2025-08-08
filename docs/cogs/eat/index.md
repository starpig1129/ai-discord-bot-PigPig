# "Eat What" System

**Location:** [`cogs/eat/`](cogs/eat/)

The "Eat What" system is a sophisticated, personalized restaurant recommendation engine integrated into the bot. It combines web crawling, database storage, and machine learning to learn a server's food preferences and provide tailored suggestions. This feature is primarily accessed through the `eat` option in the `/internet_search` command.

## Core Components

The system is divided into several key components:

*   **[Database](./db.md):** Manages the storage of search history and user preferences.
*   **[Google Maps Crawler](./googlemap_crawler.md):** Fetches real-time restaurant data from Google Maps.
*   **[Machine Learning Model](./train.md):** Trains on user feedback to provide personalized recommendations.
*   **[UI (Embeds & Views)](./ui.md):** Provides the interactive Discord interface for users.

## Workflow

1.  A user initiates a search via `/internet_search search_type: eat`.
2.  If the user provides a keyword, the **[Google Maps Crawler](./googlemap_crawler.md)** searches for that type of food.
3.  If no keyword is provided, the **[Machine Learning Model](./train.md)** predicts a food recommendation based on the server's past ratings.
4.  The crawler fetches details for a randomly selected restaurant.
5.  The **[UI](./ui.md)** displays the recommendation in an interactive embed with buttons (Map, Menu, Like, Dislike, etc.).
6.  The search result is saved to the **[Database](./db.md)**.
7.  When a user clicks "Like" or "Dislike", their rating is saved to the database.
8.  This new rating triggers the **[Machine Learning Model](./train.md)** to retrain, refining its future recommendations for that server.