# File: `cogs/memory/services/vectorization_service.py`

## Overview
Core logic and functionalities for vectorization_service.py. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `VectorizationService`
Service responsible for converting EventSummary objects into MemoryFragment objects,

- **Attributes**:
  - `bot` (`Any`): Instance attribute.
  - `storage` (`Any`): Instance attribute.
  - `vector_manager` (`Any`): Instance attribute.
  - `settings` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(bot: Any, storage: StorageInterface, vector_manager: Any, settings: MemoryConfig) -> None`: Executes __init__ operation.
  - `process_event_summaries(event_summaries: List[EventSummary]) -> None`: Process a list of EventSummary objects and store them in the vector database.
  - `_convert_event_summaries_to_fragments(event_summaries: List[EventSummary]) -> List[MemoryFragment]`: Convert EventSummary objects to MemoryFragment objects.
