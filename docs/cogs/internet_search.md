# Internet Search Cog Documentation

## Overview

The Internet Search cog provides advanced web searching, video discovery, and restaurant recommendation capabilities. It integrates Google's Gemini grounding technology for high-accuracy web answers, while maintaining a robust Selenium-based fallback system. It also serves as the entry point for specialized searches like YouTube and the "Eat" (restaurant) system.

## Features

- **Gemini Grounding Search**: Uses Google's latest models with built-in search grounding for factual, cited answers.
- **Selenium Fallback**: Automatically falls back to traditional web scraping if AI services are unavailable or fail.
- **YouTube Integration**: Search for relevant videos and receive randomized recommendations.
- **Eat (Restaurant) System**: Context-aware food recommendations using a weighted recommender engine and Google Maps integration.
- **Multi-language Support**: Fully localized responses for all search types (general, youtube, eat).
- **Intelligent Message Splitting**: Automatically handles long markdown responses to fit Discord's message limits.

## Commands

### `/search`
The primary command for all search types.

**Parameters**:
- `type` (Choice: `general`, `youtube`, `eat`): The category of search to perform.
- `query` (string, required): The search keywords or restaurant requirements.

**Behavior by Type**:
- **`general`**: Performs a grounded web search. Returns a structured answer with bulleted highlights and source links.
- **`youtube`**: Searches for videos and returns a random selection from the top results.
- **`eat`**: Searches for restaurants. If `_` is used as a keyword, the bot uses its internal recommender to suggest food based on history and weights.

## Technical Implementation

### Class Structure
```python
class InternetSearchCog(commands.Cog):
    def __init__(self, bot):
        self.recommender = WeightedRecommender(db=DB())
        self.provider = get_restaurant_provider()
```

### Search Logic

#### 1. Gemini Grounding (`google_search`)
The cog uses the `google-genai` SDK. It passes a specialized system prompt to the `gemini-2.0-flash` (or configured) model, instructing it to return:
- A concise paragraph answer.
- Up to 5 bulleted highlights.
- Grounding citations (which are converted into markdown links).

#### 2. Legacy Fallback (`_legacy_google_search`)
If the Gemini API key is missing or the request fails, the cog initializes a headless Chrome instance via Selenium to scrape Google Search results, ensuring the bot always provides information.

#### 3. YouTube Search (`youtube_search`)
Utilizes the `youtube-search` library to fetch 5 results and randomly selects one to present to the user, providing title, channel, views, and URL.

#### 4. Eat Search (`eat_search`)
A complex integration that:
1. Uses a `WeightedRecommender` to suggest keywords if none provided.
2. Calls a `restaurant_provider` (Google Maps or Foursquare).
3. Ranks candidates using server-specific weights.
4. Returns an interactive `EatBrowseView` for UI interaction.

## Error Handling

- **Grounding Failures**: Automatically triggers the legacy scraper.
- **CAPTCHA Detection**: Identifies if Google has blocked the scraper and reports it.
- **Permission Errors**: Reports issues through the centralized `func.report_error` system.
- **Message Length**: Uses `_split_markdown` to prevent Discord's 2000-character limit from truncating results.

## Dependencies

- `google-genai`: For AI grounding search.
- `selenium` & `webdriver_manager`: For fallback scraping.
- `beautifulsoup4`: For parsing HTML results.
- `youtube-search`: For video discovery.
- `LanguageManager`: For multi-language support.

## Related Files

- `cogs/internet_search.py`: Main implementation.
- `cogs/eat/`: Sub-module for restaurant logic.
- `llm/utils/send_message.py`: Utility for safe message editing.