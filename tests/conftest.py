# tests/conftest.py
#
# This conftest pre-loads the real addons.settings module before any test
# module is collected. Without this, test files that install lightweight
# sys.modules stubs for addons.settings (e.g. test_bot_info_tool.py via
# setdefault) would install a sparse fake before the real module is cached,
# causing ImportError for symbols like attachment_config or memory_config in
# subsequently-collected test modules.
#
# Loading the real module here guarantees sys.modules["addons.settings"] holds
# the genuine object when test_bot_info_tool.py's setdefault calls execute,
# so those calls become no-ops.  test_context_manager.py still unconditionally
# overwrites the entry with its own stub, but that stub is enriched with the
# real attachment/memory symbols (see that file) so downstream modules remain
# importable.

import addons.settings  # noqa: F401  — side-effect: caches real module

import sys
import unittest.mock

# Create a mock discord module that has the required types for other modules to import
mock_discord = unittest.mock.MagicMock()
mock_discord.AllowedMentions = unittest.mock.MagicMock
mock_discord.Message = unittest.mock.MagicMock
mock_discord.Embed = unittest.mock.MagicMock
mock_discord.File = unittest.mock.MagicMock
mock_discord.Colour = unittest.mock.MagicMock
mock_discord.Color = unittest.mock.MagicMock

# Do not overwrite if discord is already in sys.modules,
# but our mock helps when tests bypass loading real discord.py
if 'discord' not in sys.modules:
    sys.modules['discord'] = mock_discord
