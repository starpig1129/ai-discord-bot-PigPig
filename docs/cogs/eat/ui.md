# Eat Module UI Documentation

## Overview

The Eat module features a rich, interactive user interface designed to guide users from initial food recommendations to detailed restaurant reviews. The UI is built using Discord's `View` and `Embed` systems, supporting multi-language localization and real-time AI content generation.

## Key UI Components

### Embeds (`embeds.py`)

The module uses specialized embeds for different stages of the user journey:

- **`browseEmbed`**: Displays a list of search results. Features pagination progress (e.g., "1 / 10"), restaurant name, rating, category, and address.
- **`eatEmbed`**: The detailed view for a selected restaurant. Includes large photos, price levels, and opening hours.
- **`loadingEmbed`**: A transient embed shown during search or while fetching detailed restaurant data.
- **`mapEmbed` & `menuEmbed`**: Simple embeds used to display specific restaurant assets.

### Views (`views.py`)

Interactive elements that handle user input and transitions.

#### 1. `EatBrowseView` (Main Search View)
The primary interface after a `/search type:eat` command.
- **Pagination**: "Previous" and "Next" buttons to navigate the result list.
- **Dropdown Selection**: A `discord.ui.Select` menu allowing direct navigation to any previously explored restaurant.
- **"Choose this!" Button**: Confirms the selection and transitions to `EatDetailView`.
- **"Next Recommendation" Button**: Triggers the next recommendation and performs real-time data fetching if background prefetching hasn't finished.

#### 2. `EatDetailView` (Operation View)
The control panel for a specific restaurant.
- **"Map" Button**: Sends an ephemeral link to Google Maps.
- **"Menu" Button**: Displays a menu image if available.
- **"AI Review" Button**: **Core Feature**. Generates a professional, witty review using a LangChain agent. This process is streamed to the user in real-time.
- **Feedback Buttons (👍/👎)**: Allows users to rate the recommendation. Likes increase the restaurant's weight in future searches.
- **"Back to List" Button**: Returns the user to the `EatBrowseView`.

#### 3. `DislikeModal`
Triggered by the 👎 button. Collects a textual reason for the dislike (e.g., "Too expensive") to improve future recommendations.

## Technical Flow

### Real-time Prefetching
When `EatBrowseView` is initialized, it starts an asynchronous background task (`_background_prefetch`) to fetch detailed information (via Selenium) for the first 15 candidates. If a user navigates to a restaurant before its data is ready, the view performs an on-demand "real-time fetch" while showing the `loadingEmbed`.

### AI Review Generation
The "AI Review" button utilizes the `ModelManager` and `init_chat_model` from LangChain. It uses a specialized system prompt to maintain the bot's "witty food critic" persona. The review is generated using `astream` for a responsive user experience.

## Multi-language Support
Every text element in the UI, including button labels, embed titles, and modal placeholders, is passed through `LanguageManager.translate`. This ensures a native experience for all supported locales (English, Traditional Chinese, Simplified Chinese, Japanese).

## Related Files
- `cogs/eat/views.py`: Logic for interactive components.
- `cogs/eat/embeds.py`: Visual structure for restaurant data.
- `translations/[LOCALE]/commands/eat.json`: Source text for all UI elements.