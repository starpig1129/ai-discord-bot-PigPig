# Update System

The update system, located in the [`addons/update/`](addons/update/) directory, is a comprehensive module responsible for managing automatic updates for the bot. It handles version checking, downloading, security, and notifications.

## Modules

This system is composed of the following modules:

*   **[Checker](./checker.md):** Checks for new versions on GitHub.
*   **[Downloader](./downloader.md):** Securely downloads update files.
*   **[Manager](./manager.md):** The core orchestrator of the update process.
*   **[Notifier](./notifier.md):** Sends update-related notifications via Discord.
*   **[Restart](./restart.md):** Manages the graceful restart of the bot after an update.
*   **[Security](./security.md):** Handles permissions, backups, and configuration protection.
