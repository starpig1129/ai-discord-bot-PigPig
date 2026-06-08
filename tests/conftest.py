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

import discord          # noqa: F401  — side-effect: caches real discord module safely
import addons.settings  # noqa: F401  — side-effect: caches real module
