# Core Addons (System Services)

## Overview

The `addons/` directory contains the low-level infrastructure that powers the PigPig Bot. These are "non-cog" modules that provide essential services such as configuration management, logging, and update logic.

## Core Modules

| Module | Description | Documentation |
|--------|-------------|---------------|
| `settings.py` | Configuration loading and inheritance. | [Settings](settings.md) |
| `logging.py` | Multi-guild structured logging. | [Logging](logging.md) |
| `tokens.py` | API key and secret management. | [Tokens](tokens.md) |
| `update/` | Bot versioning and automatic updates. | [Update System](../update.md) |

## Design Principles

- **Separation of Concerns**: Addons handle system-level logic, leaving Cogs to handle Discord-specific features.
- **Fail-Fast Configuration**: If essential tokens or settings are missing, the bot will log a critical error and refuse to start.
- **Global Accessibility**: Most addons are imported once and used globally throughout the lifecycle of the bot.

---
*For daily bot operation, you rarely need to modify these files. However, they are the first place to look when troubleshooting connection or configuration issues.*