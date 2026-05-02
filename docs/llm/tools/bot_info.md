# Bot Info Tools

## Overview

The `BotInfoTools` class provides tools for the AI agent to query information about the bot itself, specifically its version history and recent updates from GitHub. This allows the bot to answer questions like "What's new?" or "What version are you running?".

## Class: BotInfoTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: A list containing the `get_bot_changelog` tool.

### Tool: get_bot_changelog

```python
async def get_bot_changelog() -> str:
```

**Returns:**
- `str`: A formatted string containing current version, latest version, update status, and release notes.

**Purpose:**
Fetches the latest release notes from the bot's GitHub repository.

**Features:**
- **Version Tracking**: Compares current local version with the latest GitHub release.
- **Update Status**: Indicates if a new version is available for deployment.
- **Changelog Extraction**: Retrieves and formats the Markdown release notes from GitHub.
- **Release Date**: Shows when the latest update was published.

## Integration

- **VersionChecker**: Uses the `VersionChecker` utility from `addons.update.checker`.
- **Settings**: Reads GitHub repository configuration from `addons.settings.update_config`.
- **Target Mode**: Routed to the **Info Agent** (`target_agent_mode = "info"`).

## Usage Examples

**Querying Updates:**
```python
# Returns a summary of the latest version and notes
result = await get_bot_changelog()
```

## Dependencies

- `addons.update.checker.VersionChecker`: Core logic for GitHub API interaction.
- `addons.settings.update_config`: Configuration for the repository URL and credentials.
- `langchain_core.tools.StructuredTool`: LangChain integration wrapper.
