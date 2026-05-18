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
# Snapshot real symbols from the already-loaded module (if present) so that
# tests collected *after* this conftest — e.g. test_attachment_config.py
# (imports AttachmentConfig) and test_embed_processor.py (imports
# attachment_config) — continue to receive valid, non-stub values even
# though sys.modules["addons.settings"] will point to our lightweight stub.
_real_settings = sys.modules.get("addons.settings")
_real_attachment_config = getattr(_real_settings, "attachment_config", None)
_real_AttachmentConfig = getattr(_real_settings, "AttachmentConfig", None)
_real_memory_config = getattr(_real_settings, "memory_config", None)
_real_update_config = getattr(_real_settings, "update_config", None)

_memory_cfg = MagicMock()
_memory_cfg.qdrant.host = "localhost"
_memory_cfg.qdrant.port = 6333

_settings_mod = _stub_module(
    "addons.settings",
    memory_config=_real_memory_config if _real_memory_config is not None else _memory_cfg,
    update_config=_real_update_config if _real_update_config is not None else MagicMock(),
    attachment_config=_real_attachment_config if _real_attachment_config is not None else MagicMock(),
    AttachmentConfig=_real_AttachmentConfig if _real_AttachmentConfig is not None else MagicMock(),
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
