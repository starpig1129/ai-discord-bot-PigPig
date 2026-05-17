# File: `cogs/eat/recommender.py`

## Overview
Lightweight Weighted Recommender. This file is part of the cogs subsystem and handles the primary operations for its respective domain.

## Classes

### `WeightedRecommender`
Weighted recommender based on user rating history.

- **Attributes**:
  - `db` (`Any`): Instance attribute.

- **Methods**:
  - `__init__(db: DB) -> Any`: Executes __init__ operation.
  - `suggest_keyword(discord_id: str, available_keywords: list[str]) -> str`: Suggest the next search keyword based on user preferences.
  - `rank_candidates(discord_id: str, candidates: list[dict]) -> list[dict]`: Rank candidate restaurants, excluding disliked ones and weighting liked categories.
