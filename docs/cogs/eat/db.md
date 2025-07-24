# Eat System - Database

**File:** [`cogs/eat/db/db.py`](cogs/eat/db/db.py)

The `DB` class is the data persistence layer for the "Eat What" system. It uses SQLAlchemy to interact with a SQLite database (`data/eatdatabase.sqlite`) to store and retrieve information about food keywords, search history, and user ratings.

## `DB` Class

### `__init__(self)`

Initializes the database connection and creates the necessary tables (`Keywords`, `SearchRecord`) if they don't already exist, based on the schema defined in `cogs/eat/db/tables.py`.

### Key Methods

#### `storeKeyword(self, keyword: str)`

Stores a new food keyword (e.g., "ramen", "sushi") in the `Keywords` table. This is used to build a vocabulary of food types for the machine learning model.

#### `getKeywords(self) -> list`

Retrieves a list of all unique keywords that have been searched or encountered.

#### `storeSearchRecord(self, discord_id, title, keyword, map_rate, tag, map_address) -> int`

Logs a new search event to the `SearchRecord` table. This includes who performed the search, what the keyword was, and the details of the recommended restaurant.

*   **Returns:** The ID of the newly created record, which is used by the UI to link user feedback to the correct record.

#### `updateRecordRate(self, id: int, new_rate: float)`

Updates a search record with a user's rating. This is called when a user clicks the "Like" (`1`), "Dislike" (`-1`), or "Regenerate" (`-0.5`) buttons.

*   **Parameters:**
    *   `id` (int): The ID of the search record to update.
    *   `new_rate` (float): The user's rating for the recommendation.

#### `getSearchRecoreds(self, discord_id: str) -> list`

Retrieves all search records for a specific Discord server ID. This data is used as the input for training the machine learning model.