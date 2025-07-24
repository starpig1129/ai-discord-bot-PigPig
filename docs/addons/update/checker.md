# Checker Module

**File:** [`addons/update/checker.py`](addons/update/checker.py)

This module is responsible for checking for new versions of the bot on GitHub. It compares the local version with the latest release available in the repository.

## `VersionChecker` Class

The `VersionChecker` class handles the logic for checking versions.

### `__init__(self, github_config: Dict[str, str])`

Initializes the `VersionChecker`.

*   **Parameters:**
    *   `github_config` (Dict[str, str]): A dictionary containing GitHub configuration, including the `api_url`.

### Methods

#### `async check_for_updates(self) -> Dict[str, any]`

Checks for available updates by querying the GitHub API.

*   **Returns:** A dictionary containing version information and the update status. The dictionary includes keys such as `current_version`, `latest_version`, `update_available`, `release_notes`, and `download_url`.

#### `get_current_version(self) -> str`

Retrieves the current version of the bot.

*   **Returns:** The current version string.

### Example Usage

```python
import asyncio
from addons.update.checker import VersionChecker

async def main():
    # Example GitHub configuration
    github_config = {
        "api_url": "https://api.github.com/repos/starpig1129/ai-discord-bot-PigPig/releases/latest"
    }

    checker = VersionChecker(github_config)
    update_info = await checker.check_for_updates()

    if update_info.get("update_available"):
        print(f"New version available: {update_info['latest_version']}")
        print(f"Release notes: {update_info['release_notes']}")
    else:
        print("You are using the latest version.")

if __name__ == "__main__":
    asyncio.run(main())