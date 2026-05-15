"""Pytest fixtures and mocks for dashboard tests.

This conftest ensures that importing dashboard or cog modules does not
trigger real environment reads (settings files, .env, Qdrant, etc.) so
the test suite can run cleanly in CI without a full bot setup.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub out heavy external dependencies before any test module is imported.
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs: object) -> types.ModuleType:
    """Create a lightweight stub module and register it in sys.modules."""
    mod = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    sys.modules[name] = mod
    return mod


# -- addons.settings --------------------------------------------------------
_memory_cfg = MagicMock()
_memory_cfg.qdrant.host = "localhost"
_memory_cfg.qdrant.port = 6333

_settings_mod = _stub_module(
    "addons.settings",
    memory_config=_memory_cfg,
    update_config=MagicMock(),
)
# Ensure parent package is also registered
sys.modules.setdefault("addons", _stub_module("addons"))

# -- addons.logging ---------------------------------------------------------
_logging_mod = _stub_module(
    "addons.logging",
    get_logger=lambda **kwargs: MagicMock(),
)

# -- addons.tokens ----------------------------------------------------------
_stub_module("addons.tokens", tokens=MagicMock())

# -- qdrant_client ----------------------------------------------------------
_qdrant_mod = _stub_module("qdrant_client", QdrantClient=MagicMock())
_stub_module(
    "qdrant_client.models",
    Filter=MagicMock(),
    FieldCondition=MagicMock(),
    MatchAny=MagicMock(),
)

# -- function (ROOT_DIR) ----------------------------------------------------
_stub_module("function", ROOT_DIR="/tmp/pigpig_test_root")

# ---------------------------------------------------------------------------
# FastAPI test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def owner_token_payload() -> dict:
    """Return a minimal JWT payload with Bot Owner role."""
    return {"sub": "owner_discord_id", "role": "owner", "guild_ids": []}


@pytest.fixture()
def user_token_payload() -> dict:
    """Return a minimal JWT payload with general user role."""
    return {"sub": "user_discord_id", "role": "user", "guild_ids": []}
