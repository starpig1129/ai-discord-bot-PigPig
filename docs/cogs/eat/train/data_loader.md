# File: `cogs/eat/train/data_loader.py`

## Overview
Core logic and functionalities for data_loader.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `DataLoader`
Represents DataLoader.

- **Attributes**:
  - `db` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DB) -> None`: Executes __init__ operation.
  - `loadingData(discord_id: str) -> Any`: Executes loadingData operation.
  - `procressData(data: Any) -> Any`: Executes procressData operation.
  - `genVocabularyList(data: Any) -> Any`: Executes genVocabularyList operation.
  - `transform(data: Any, voc_length: Any, batch_size: Any) -> Any`: Executes transform operation.
