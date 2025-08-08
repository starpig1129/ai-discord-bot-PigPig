# Eat System - Google Maps Crawler

**File:** [`cogs/eat/providers/googlemap_crawler.py`](cogs/eat/providers/googlemap_crawler.py)

The `GoogleMapCrawler` class is responsible for fetching real-time restaurant data from Google Maps. It uses the Selenium library to automate a Chrome browser, enabling it to perform searches and scrape information from the resulting pages.

## `GoogleMapCrawler` Class

### `__init__(self)`

Initializes the Selenium WebDriver. It configures Chrome to run in headless mode (without a visible UI) for efficiency.

### `search(self, keyword)`

This is the main method of the class. It performs a search on Google Maps and returns detailed information about a randomly selected restaurant.

*   **Parameters:**
    *   `keyword` (str): The food type or restaurant name to search for (e.g., "pizza", "Taverna Siguenza").
*   **Returns:** A tuple containing the following information about the restaurant:
    1.  `title` (str): The name of the restaurant.
    2.  `rating` (str): The star rating (e.g., "4.5 stars").
    3.  `category` (str): The type of restaurant (e.g., "Italian restaurant").
    4.  `address` (str): The physical address.
    5.  `url` (str): The Google Maps URL for the restaurant.
    6.  `reviews` (str): A string containing snippets of user reviews.
    7.  `menu` (str): A URL to the menu image, if available.

### Crawling Process

1.  **Initial Search:** Navigates to `https://www.google.com/maps/search/{keyword}餐廳`.
2.  **Result Selection:** It finds all the search result links on the page and randomly clicks one to navigate to the restaurant's specific page.
3.  **Data Extraction:** It uses `BeautifulSoup` to parse the HTML of the restaurant's page and extracts key information like the title, rating, address, and category.
4.  **Review Scraping:** It scrolls down the page to load user reviews and then extracts the text from them.
5.  **Menu Scraping:** It attempts to find and click the "Menu" button to reveal and scrape the URL of the menu image.
6.  **Cleanup:** The `close()` method is called to shut down the WebDriver instance when it's no longer needed.