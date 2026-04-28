"""Tests for translation key completeness in system_prompt.json files."""
import json
import pytest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = [
    ("ui", "buttons", "reload_config"),
    ("ui", "buttons", "direct_edit"),
    ("ui", "menus", "edit_mode_title"),
    ("ui", "menus", "edit_mode_description"),
    ("messages", "success", "reload"),
    ("messages", "info", "reload_unavailable"),
]
LANGUAGES = ["zh_TW", "zh_CN", "en_US", "ja_JP"]


def _load(lang: str) -> dict:
    path = BASE / "translations" / lang / "commands" / "system_prompt.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get(d: dict, keys: tuple):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


@pytest.mark.parametrize("lang", LANGUAGES)
def test_edit_mode_title_contains_scope_placeholder(lang):
    data = _load(lang)
    value = _get(data, ("ui", "menus", "edit_mode_title"))
    assert value and "{scope}" in value, (
        f"edit_mode_title missing {{scope}} placeholder in {lang}"
    )


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("key_path", REQUIRED_KEYS)
def test_required_key_exists(lang, key_path):
    data = _load(lang)
    value = _get(data, key_path)
    assert value is not None, f"Missing key {'.'.join(key_path)} in {lang}"
    assert isinstance(value, str) and len(value) > 0, (
        f"Empty key {'.'.join(key_path)} in {lang}"
    )


# ─── Unit tests for LocalizedView._t() ───────────────────────────────────────

import sys, types
from unittest.mock import MagicMock

# Minimal discord stub so views.py can be imported without a real Discord client
_discord = types.ModuleType("discord")
_discord_ui = types.ModuleType("discord.ui")
_discord_ext = types.ModuleType("discord.ext")
_discord_ext_commands = types.ModuleType("discord.ext.commands")
_discord_app_commands = types.ModuleType("discord.app_commands")

class _FakeView:
    def __init__(self, **kwargs): pass
    def add_item(self, item): pass
    def clear_items(self): pass

_discord_ui.View = _FakeView
_discord_ui.Button = object
_discord_ui.Select = object
_discord.ui = _discord_ui
_discord.Color = MagicMock()
_discord.ButtonStyle = MagicMock()
_discord.SelectOption = MagicMock()
_discord.Embed = MagicMock()
_discord.utils = MagicMock()
_discord.Interaction = MagicMock()
_discord.Guild = MagicMock()
_discord.TextChannel = MagicMock()
for _mod, _name in [
    (_discord, "discord"),
    (_discord_ui, "discord.ui"),
    (_discord_ext, "discord.ext"),
    (_discord_ext_commands, "discord.ext.commands"),
    (_discord_app_commands, "discord.app_commands"),
]:
    sys.modules[_name] = _mod  # force override any earlier incomplete stub (e.g. from test_context_manager)

# Stub heavy project dependencies
_addons = types.ModuleType("addons")
_addons_logging = types.ModuleType("addons.logging")
_addons_logging.get_logger = lambda **kw: MagicMock()
_addons.logging = _addons_logging
sys.modules.setdefault("addons", _addons)
sys.modules.setdefault("addons.logging", _addons_logging)

_function = types.ModuleType("function")
_function.func = MagicMock()
sys.modules.setdefault("function", _function)

# Stub for cogs.system_prompt submodules
_manager_mod = types.ModuleType("cogs.system_prompt.manager")
class _FakeManager:
    bot = None
_manager_mod.SystemPromptManager = _FakeManager
sys.modules.setdefault("cogs.system_prompt.manager", _manager_mod)

_perm_mod = types.ModuleType("cogs.system_prompt.permissions")
_perm_mod.PermissionValidator = object
sys.modules.setdefault("cogs.system_prompt.permissions", _perm_mod)

_ui_mod = types.ModuleType("cogs.system_prompt.ui")
_ui_mod.SystemPromptModal = object
_ui_mod.SystemPromptModuleModal = object
_ui_mod.ConfirmationView = object
_ui_mod.create_system_prompt_embed = lambda *a, **kw: MagicMock()
sys.modules.setdefault("cogs.system_prompt.ui", _ui_mod)

_exc_mod = types.ModuleType("cogs.system_prompt.exceptions")
class _FakeError(Exception): pass
_exc_mod.SystemPromptError = _FakeError
_exc_mod.PermissionError = _FakeError
sys.modules.setdefault("cogs.system_prompt.exceptions", _exc_mod)

_cogs_mod = types.ModuleType("cogs")
_cogs_mod.__path__ = [str(BASE / "cogs")]
_cogs_mod.__package__ = "cogs"
_cogs_sp_mod = types.ModuleType("cogs.system_prompt")
_cogs_sp_mod.__path__ = [str(BASE / "cogs" / "system_prompt")]
_cogs_sp_mod.__package__ = "cogs.system_prompt"
sys.modules.setdefault("cogs", _cogs_mod)
sys.modules.setdefault("cogs.system_prompt", _cogs_sp_mod)

# Import after stubs are in place
sys.path.insert(0, str(BASE))


def _make_localized_view(bot=None, guild_id="12345"):
    """Helper that builds a LocalizedView with minimal mocking."""
    from cogs.system_prompt.views import LocalizedView  # noqa: PLC0415

    mock_manager = MagicMock()
    mock_manager.bot = bot
    return LocalizedView(manager=mock_manager, guild_id=guild_id)


def test_localized_view_t_calls_translate_with_correct_args():
    mock_lm = MagicMock()
    mock_lm.translate.return_value = "Translated"
    mock_bot = MagicMock()
    mock_bot.get_cog.return_value = mock_lm

    view = _make_localized_view(bot=mock_bot, guild_id="99")
    result = view._t("commands", "system_prompt", "ui", "buttons", "set_prompt")

    mock_lm.translate.assert_called_once_with(
        "99", "commands", "system_prompt", "ui", "buttons", "set_prompt"
    )
    assert result == "Translated"


def test_localized_view_t_returns_fallback_when_no_bot():
    view = _make_localized_view(bot=None)
    result = view._t("commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Set Prompt")
    assert result == "Set Prompt"


def test_localized_view_t_returns_last_key_when_no_fallback_and_no_bot():
    view = _make_localized_view(bot=None)
    result = view._t("commands", "system_prompt", "ui", "buttons", "set_prompt")
    assert result == "set_prompt"


def test_localized_view_t_returns_fallback_on_exception():
    mock_bot = MagicMock()
    mock_bot.get_cog.side_effect = RuntimeError("cog error")

    view = _make_localized_view(bot=mock_bot)
    result = view._t("commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Fallback")
    assert result == "Fallback"


# ─── Unit tests for _ti() ─────────────────────────────────────────────────────

def test_ti_calls_translate_with_guild_id_from_interaction():
    mock_lm = MagicMock()
    mock_lm.translate.return_value = "Translated"
    mock_client = MagicMock()
    mock_client.get_cog.return_value = mock_lm
    mock_guild = MagicMock()
    mock_guild.id = 42
    mock_interaction = MagicMock()
    mock_interaction.client = mock_client
    mock_interaction.guild = mock_guild

    from cogs.system_prompt.views import _ti
    result = _ti(mock_interaction, "commands", "system_prompt", "ui", "buttons", "set_prompt")

    mock_lm.translate.assert_called_once_with(
        "42", "commands", "system_prompt", "ui", "buttons", "set_prompt"
    )
    assert result == "Translated"


def test_ti_uses_system_guild_id_when_no_guild():
    mock_lm = MagicMock()
    mock_lm.translate.return_value = "Fallback"
    mock_client = MagicMock()
    mock_client.get_cog.return_value = mock_lm
    mock_interaction = MagicMock()
    mock_interaction.client = mock_client
    mock_interaction.guild = None

    from cogs.system_prompt.views import _ti
    _ti(mock_interaction, "commands", "system_prompt", "ui", "buttons", "set_prompt")

    mock_lm.translate.assert_called_once_with(
        "system", "commands", "system_prompt", "ui", "buttons", "set_prompt"
    )


def test_ti_returns_fallback_when_no_client():
    mock_interaction = MagicMock()
    mock_interaction.client = None
    mock_interaction.guild = MagicMock()
    mock_interaction.guild.id = 99

    from cogs.system_prompt.views import _ti
    result = _ti(mock_interaction, "commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Set Prompt")
    assert result == "Set Prompt"


def test_ti_returns_fallback_on_exception():
    mock_client = MagicMock()
    mock_client.get_cog.side_effect = RuntimeError("cog error")
    mock_guild = MagicMock()
    mock_guild.id = 77
    mock_interaction = MagicMock()
    mock_interaction.client = mock_client
    mock_interaction.guild = mock_guild

    from cogs.system_prompt.views import _ti
    result = _ti(mock_interaction, "commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Fallback")
    assert result == "Fallback"
