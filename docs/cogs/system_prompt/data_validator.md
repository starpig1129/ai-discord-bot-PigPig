# File: `cogs/system_prompt/data_validator.py`

## Overview
系統提示數據驗證助手 This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `SystemPromptDataValidator`
系統提示數據驗證器

- **Attributes**:
  - `data_dir` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(data_dir: str) -> Any`: Executes __init__ operation.
  - `validate_config_consistency(guild_id: str, channel_id: str) -> Dict[Tuple[str, Any]]`: 驗證配置一致性
  - `fix_inconsistent_data(guild_id: str, channel_id: str) -> bool`: 修復不一致的數據
  - `get_module_comparison(guild_id: str, channel_id: str, expected_modules: Dict[Tuple[str, str]]) -> Dict[Tuple[str, Any]]`: 比較期望的模組與實際存儲的模組
