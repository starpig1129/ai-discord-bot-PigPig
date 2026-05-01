# Settings Manager

## Overview

The `addons/settings.py` module is the central configuration engine for the PigPig Bot. It handles loading YAML configuration files, managing environment variables via `.env`, and providing a structured API for other modules to access settings.

## Configuration Hierarchy

The bot uses a "Config Root" pattern for flexibility:
1. **`CONFIG_ROOT`**: Defined by the `CONFIG_ROOT` environment variable. Defaults to `./base_configs`.
2. **YAML Files**: Settings are split into logical files within the config root (e.g., `base.yaml`, `llm.yaml`, `memory.yaml`).
3. **Environment Variables**: Sensitive data (tokens, keys) are loaded from `.env` via `tokens.py`.

## Core Configuration Objects

The module exposes several specialized config classes:

### `BaseConfig` (`base.yaml`)
- **Prefix**: The default command prefix.
- **Activity**: Discord "Watching/Playing" status rotation.
- **Logging**: Detailed console and file logging settings (colors, levels, retention).

### `LLMConfig` (`llm.yaml`)
- **Model Priorities**: Ordered list of LLM models to try.
- **Ollama URL**: Connection string for local models.
- **Timeouts**: Global LLM call timeout settings.

### `MemoryConfig` (`memory.yaml`)
- **Enabled**: Toggle for the entire memory subsystem.
- **Vector Store**: Qdrant connection details and collection names.
- **Embeddings**: Provider (Google/OpenAI) and model selection.
- **Thresholds**: Message/Time limits for triggering memory processing.

### `PromptConfig` (`prompt/*.yaml`)
- **Dynamic Prompts**: Manages agent-specific system prompts.
- **Variable Injection**: Automatically replaces placeholders like `{bot_name}`, `{creator}`, and `{environment}`.

## Technical Details

- **Safe Loading**: YAML files are loaded with error handling that reports failures via `func.report_error`.
- **Async Initialization**: Configuration is evaluated at module import time but can interact with the async event loop for error reporting.
- **Logging Integration**: The settings module explicitly reloads the logging configuration once `BaseConfig` is loaded to ensure that `CONFIG_ROOT` settings are respected.

## Usage

Modules should import the pre-instantiated config objects:

```python
from addons.settings import llm_config, memory_config

print(llm_config.ollama_url)
if memory_config.enabled:
    # Do something
```

---
*By centralizing settings, PigPig Bot remains highly portable and easy to configure for different Discord environments.*
