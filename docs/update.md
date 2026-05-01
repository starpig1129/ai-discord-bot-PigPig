# Update System

## Overview

The PigPig Bot features a sophisticated update system divided into two parts: a Command-Line Interface (CLI) for manual management and an integrated background service for automatic checks.

## Update CLI (`update.py`)

A lightweight wrapper for the update architecture, allowing administrators to manage versions from the terminal.

### Usage

| Command | Action |
|---------|--------|
| `python update.py -c` | Check the current version against GitHub. |
| `python update.py -l` | Download and install the latest stable version. |
| `python update.py -b` | Install the latest beta version. |
| `python update.py -v <version>` | Install a specific version/tag. |

## Internal Architecture (`addons/update/`)

The system is built on several specialized modules:

- **`manager.py`**: Coordinates the update process and interacts with the bot instance.
- **`checker.py`**: Queries the GitHub API to compare local and remote versions.
- **`downloader.py`**: Handles secure downloading and extraction of update packages.
- **`security.py`**: Validates `BOT_OWNER_ID` permissions before allowing updates.
- **`notifier.py`**: Provides interactive Discord UI (buttons) for initiating updates.

## Update Process Flow

1. **Detection**: `VersionChecker` identifies a new release on GitHub.
2. **Permission Check**: `UpdatePermissionChecker` ensures the user has administrative rights.
3. **Download**: `UpdateDownloader` fetches the ZIP archive to a temporary directory.
4. **Installation**: `UpdateManager` extracts the files, preserving the `.env` and `data/` folders.
5. **Completion**: The bot logs the success and requires a restart to apply changes.

## Configuration

Settings for the update system are managed in `base_configs/update.yaml`:
- **Repository**: `starpig1129/ai-discord-bot-PigPig`
- **Branch**: `main` (default) or `beta`.
- **Auto-check**: Enable/disable background checks on startup.

---
*Always ensure you have a backup of your data before performing a major version update.*
