# Downloader Module

**File:** [`addons/update/downloader.py`](addons/update/downloader.py)

This module is responsible for securely downloading update files from a given URL. It includes features for progress tracking, file verification, and cleanup of old downloads.

## `UpdateDownloader` Class

The `UpdateDownloader` class manages the download process.

### `__init__(self, download_dir: str = "temp/downloads")`

Initializes the `UpdateDownloader`.

*   **Parameters:**
    *   `download_dir` (str): The directory where update files will be stored. Defaults to `"temp/downloads"`.

### Methods

#### `async download_update(self, download_url: str, progress_callback: Optional[Callable[[int], Awaitable[None]]] = None, chunk_size: int = 8192) -> str`

Downloads an update file from the specified URL.

*   **Parameters:**
    *   `download_url` (str): The URL of the update file.
    *   `progress_callback` (Optional[Callable[[int], Awaitable[None]]]): An optional async callback function to report download progress (0-100).
    *   `chunk_size` (int): The size of download chunks in bytes.
*   **Returns:** The file path of the downloaded update.
*   **Raises:** `Exception` if the download fails or the file verification is unsuccessful.

#### `calculate_file_hash(self, filepath: str, algorithm: str = 'sha256') -> str`

Calculates the hash of a file.

*   **Parameters:**
    *   `filepath` (str): The path to the file.
    *   `algorithm` (str): The hashing algorithm to use (e.g., `'sha256'`).
*   **Returns:** The hexadecimal hash string of the file.

#### `cleanup_downloads(self, keep_latest: int = 3) -> None`

Cleans up old update files in the download directory.

*   **Parameters:**
    *   `keep_latest` (int): The number of latest downloads to keep.

#### `get_download_dir(self) -> str`

Gets the path to the download directory.

*   **Returns:** The download directory path.

### Example Usage

```python
import asyncio
from addons.update.downloader import UpdateDownloader

async def progress_reporter(progress):
    print(f"Download progress: {progress}%")

async def main():
    downloader = UpdateDownloader()
    download_url = "https://github.com/starpig1129/ai-discord-bot-PigPig/archive/refs/tags/v2.0.0.zip" # Example URL

    try:
        download_path = await downloader.download_update(download_url, progress_callback=progress_reporter)
        print(f"Update downloaded to: {download_path}")

        # Clean up old downloads, keeping the 3 most recent
        downloader.cleanup_downloads(keep_latest=3)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())