# System Prompt UI — i18n 修復與 guild_id 傳遞 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 `cogs/system_prompt/views.py` 所有按鈕標籤、選擇器 placeholder 與 callback 動態訊息，從硬編碼中文改為透過翻譯系統輸出；並補齊 4 個語言 JSON 檔案的缺失 key。

**Architecture:** 新增 `LocalizedView(discord.ui.View)` 薄基礎類別提供 `_t()` 翻譯方法；新增 `_ti()` 模組層級輔助函式供 callback 中非繼承 View 的 Button/Select 使用；所有 View 繼承 `LocalizedView` 並接收 `guild_id` 參數，`guild_id` 永遠由最近一層 `interaction.guild.id` 取得。

**Tech Stack:** Python 3.11+、discord.py、pytest、json

---

## 檔案結構

| 動作 | 路徑 | 說明 |
|------|------|------|
| 建立 | `tests/test_system_prompt_i18n.py` | 翻譯 key 完整性測試 + `LocalizedView._t()` 單元測試 |
| 修改 | `translations/zh_TW/commands/system_prompt.json` | 新增 6 個缺失 key |
| 修改 | `translations/zh_CN/commands/system_prompt.json` | 新增 6 個缺失 key |
| 修改 | `translations/en_US/commands/system_prompt.json` | 新增 6 個缺失 key |
| 修改 | `translations/ja_JP/commands/system_prompt.json` | 新增 6 個缺失 key |
| 修改 | `cogs/system_prompt/views.py` | 新增 `LocalizedView`、`_ti()`；更新 8 個 View 繼承與 `__init__`；更新所有 callback 動態訊息 |
| 修改 | `cogs/system_prompt/commands.py` | 主命令傳入 `guild_id` |

---

## Task 1：翻譯 key 完整性測試 + 補齊缺失 key

**Files:**
- Create: `tests/test_system_prompt_i18n.py`
- Modify: `translations/zh_TW/commands/system_prompt.json`
- Modify: `translations/zh_CN/commands/system_prompt.json`
- Modify: `translations/en_US/commands/system_prompt.json`
- Modify: `translations/ja_JP/commands/system_prompt.json`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_system_prompt_i18n.py`：

```python
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
@pytest.mark.parametrize("key_path", REQUIRED_KEYS)
def test_required_key_exists(lang, key_path):
    data = _load(lang)
    value = _get(data, key_path)
    assert value is not None, f"Missing key {'.'.join(key_path)} in {lang}"
    assert isinstance(value, str) and len(value) > 0, (
        f"Empty key {'.'.join(key_path)} in {lang}"
    )
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/test_system_prompt_i18n.py -v 2>&1 | head -40
```

預期：24 個測試全部 FAIL（KeyError 或 AssertionError）

- [ ] **Step 3: 在 zh_TW JSON 新增缺失 key**

在 `translations/zh_TW/commands/system_prompt.json` 的 `ui.buttons` 物件末尾加入：

```json
"reload_config": "重載設定",
"direct_edit": "直接編輯"
```

在 `ui.menus` 物件末尾加入：

```json
"edit_mode_title": "⚙️ 編輯 {scope} 系統提示",
"edit_mode_description": "請選擇編輯模式"
```

在 `messages.success` 物件末尾加入：

```json
"reload": "✅ 設定已成功重載"
```

在 `messages.info` 物件末尾加入：

```json
"reload_unavailable": "⚠️ 重載功能目前無法使用"
```

- [ ] **Step 4: 在 zh_CN JSON 新增缺失 key**

在 `translations/zh_CN/commands/system_prompt.json` 對應位置加入：

```json
// ui.buttons
"reload_config": "重载配置",
"direct_edit": "直接编辑"

// ui.menus
"edit_mode_title": "⚙️ 编辑 {scope} 系统提示",
"edit_mode_description": "请选择编辑模式"

// messages.success
"reload": "✅ 配置重载成功"

// messages.info
"reload_unavailable": "⚠️ 重载功能目前不可用"
```

- [ ] **Step 5: 在 en_US JSON 新增缺失 key**

```json
// ui.buttons
"reload_config": "Reload Config",
"direct_edit": "Direct Edit"

// ui.menus
"edit_mode_title": "⚙️ Edit {scope} Prompt",
"edit_mode_description": "Please select edit mode"

// messages.success
"reload": "✅ Configuration reloaded successfully"

// messages.info
"reload_unavailable": "⚠️ Reload function is currently unavailable"
```

- [ ] **Step 6: 在 ja_JP JSON 新增缺失 key**

```json
// ui.buttons
"reload_config": "設定を再読込",
"direct_edit": "直接編集"

// ui.menus
"edit_mode_title": "⚙️ {scope} プロンプトを編集",
"edit_mode_description": "編集モードを選択してください"

// messages.success
"reload": "✅ 設定の再読込が成功しました"

// messages.info
"reload_unavailable": "⚠️ 再読込機能は現在利用できません"
```

- [ ] **Step 7: 執行測試確認全部通過**

```bash
python -m pytest tests/test_system_prompt_i18n.py -v
```

預期：24 個測試全部 PASS

- [ ] **Step 8: Commit**

```bash
git add tests/test_system_prompt_i18n.py \
    translations/zh_TW/commands/system_prompt.json \
    translations/zh_CN/commands/system_prompt.json \
    translations/en_US/commands/system_prompt.json \
    translations/ja_JP/commands/system_prompt.json
git commit -m "feat: add missing i18n keys and translation completeness test"
```

---

## Task 2：新增 `LocalizedView` 基礎類別與 `_ti()` 輔助函式

**Files:**
- Modify: `cogs/system_prompt/views.py`（在現有 import 之後、`SystemPromptMainView` 之前插入）
- Modify: `tests/test_system_prompt_i18n.py`（新增 `_t()` 單元測試）

- [ ] **Step 1: 為 `LocalizedView` 與 `_ti()` 寫單元測試**

在 `tests/test_system_prompt_i18n.py` 末尾追加：

```python
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
for _mod, _name in [
    (_discord, "discord"),
    (_discord_ui, "discord.ui"),
    (_discord_ext, "discord.ext"),
    (_discord_ext_commands, "discord.ext.commands"),
    (_discord_app_commands, "discord.app_commands"),
]:
    sys.modules.setdefault(_name, _mod)

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

# Import after stubs are in place
# (Adjust path as needed when running from project root)
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
```

- [ ] **Step 2: 執行測試確認失敗（LocalizedView 尚未建立）**

```bash
python -m pytest tests/test_system_prompt_i18n.py::test_localized_view_t_calls_translate_with_correct_args -v
```

預期：ImportError 或 AttributeError（`LocalizedView` 不存在）

- [ ] **Step 3: 在 `views.py` 插入 `LocalizedView` 與 `_ti()` 輔助函式**

在 `cogs/system_prompt/views.py` 頂部，`from .exceptions import ...` 那行之後、`class SystemPromptMainView` 之前，插入：

```python
# ─── Translation helpers ──────────────────────────────────────────────────────

def _ti(interaction: "discord.Interaction", *keys: str, fallback: str = "") -> str:
    """Translate a key using the guild language from an interaction context.

    Falls back to ``fallback`` (or the last key segment) when LanguageManager
    is unavailable or the key is missing.
    """
    guild_id = str(interaction.guild.id) if interaction.guild else "system"
    try:
        lm = interaction.client.get_cog("LanguageManager") if interaction.client else None
        if lm:
            return lm.translate(guild_id, *keys)
    except Exception:
        pass
    return fallback or (keys[-1] if keys else "")


class LocalizedView(discord.ui.View):
    """Base class for all system-prompt views.

    Provides :meth:`_t` for translating strings at construction time using
    the server's configured language.
    """

    def __init__(
        self,
        manager: "SystemPromptManager",
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.guild_id = guild_id
        self._bot = manager.bot

    def _t(self, *keys: str, fallback: str = "") -> str:
        """Translate *keys* using the guild's language.

        Falls back to ``fallback`` (or the last key segment) when
        LanguageManager is unavailable or the key is missing.
        """
        try:
            lm = self._bot.get_cog("LanguageManager") if self._bot else None
            if lm:
                return lm.translate(self.guild_id, *keys)
        except Exception:
            pass
        return fallback or (keys[-1] if keys else "")
```

- [ ] **Step 4: 執行測試確認通過**

```bash
python -m pytest tests/test_system_prompt_i18n.py -v
```

預期：所有 28 個測試通過

- [ ] **Step 5: Commit**

```bash
git add cogs/system_prompt/views.py tests/test_system_prompt_i18n.py
git commit -m "feat: add LocalizedView base class and _ti() translation helper"
```

---

## Task 3：更新 `SystemPromptMainView`

**Files:**
- Modify: `cogs/system_prompt/views.py`（`SystemPromptMainView` 類別）

- [ ] **Step 1: 將 `SystemPromptMainView` 改繼承 `LocalizedView`**

將現有 `class SystemPromptMainView(discord.ui.View):` 的 `__init__` 替換為：

```python
class SystemPromptMainView(LocalizedView):
    """系統提示管理主選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")
        self._setup_main_buttons()
```

- [ ] **Step 2: 更新 `_setup_main_buttons()` 使用翻譯**

將整個 `_setup_main_buttons` 方法替換為：

```python
    def _setup_main_buttons(self):
        """設定主要功能按鈕"""
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "set_prompt", fallback="Set Prompt"),
            emoji="✏️", style=discord.ButtonStyle.primary, function="set", row=0,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "view_config", fallback="View Config"),
            emoji="👁️", style=discord.ButtonStyle.secondary, function="view", row=0,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "copy_prompt", fallback="Copy Prompt"),
            emoji="📋", style=discord.ButtonStyle.secondary, function="copy", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_prompt", fallback="Remove Prompt"),
            emoji="🗑️", style=discord.ButtonStyle.danger, function="remove", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_config", fallback="Reset Config"),
            emoji="🔄", style=discord.ButtonStyle.danger, function="reset", row=1,
        ))
        self.add_item(SystemPromptFunctionButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reload_config", fallback="Reload Config"),
            emoji="🔩", style=discord.ButtonStyle.secondary, function="reload", row=2,
        ))
```

- [ ] **Step 3: 更新所有 `_handle_*` handler — 傳入 `guild_id` 至子 View 並使用翻譯**

將 `_handle_set_function` 替換為：

```python
    async def _handle_set_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptSetView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "set_prompt_title", fallback="⚙️ Set System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "set_prompt_description", fallback="Please select the scope to configure")
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
```

將 `_handle_view_function` 替換為：

```python
    async def _handle_view_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptViewOptionsView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "view_options_title", fallback="👁️ View System Prompt Configuration")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "view_options_description", fallback="Please select view options")
        embed = discord.Embed(title=title, description=description, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
```

將 `_handle_copy_function` 替換為：

```python
    async def _handle_copy_function(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'server_only', fallback='Server only')}",
                ephemeral=True,
            )
            return
        guild_id = str(interaction.guild.id)
        view = SystemPromptCopyView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild=interaction.guild,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "copy_prompt_title", fallback="📋 Copy System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "copy_prompt_description", fallback="Please select source and target channels")
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
```

將 `_handle_remove_function` 替換為：

```python
    async def _handle_remove_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptRemoveView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "remove_prompt_title", fallback="🗑️ Remove System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "remove_prompt_description", fallback="Please select scope to remove")
        embed = discord.Embed(title=title, description=description, color=discord.Color.red())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
```

將 `_handle_reset_function` 替換為：

```python
    async def _handle_reset_function(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        view = SystemPromptResetView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
        title = _ti(interaction, "commands", "system_prompt", "ui", "menus", "reset_config_title", fallback="🔄 Reset System Prompt")
        description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "reset_config_description", fallback="Please select scope to reset")
        embed = discord.Embed(title=title, description=description, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
```

將 `_handle_reload_function` 替換為：

```python
    async def _handle_reload_function(self, interaction: discord.Interaction):
        try:
            if hasattr(self.manager, "reload_all_configs") and callable(self.manager.reload_all_configs):
                import asyncio as _asyncio
                if _asyncio.iscoroutinefunction(self.manager.reload_all_configs):
                    await self.manager.reload_all_configs()
                else:
                    self.manager.reload_all_configs()
                msg = _ti(interaction, "commands", "system_prompt", "messages", "success", "reload",
                          fallback="✅ Configuration reloaded successfully")
                await interaction.response.send_message(msg, ephemeral=True)
                self.logger.info(f"User {interaction.user} reloaded configuration.")
            else:
                msg = _ti(interaction, "commands", "system_prompt", "messages", "info", "reload_unavailable",
                          fallback="⚠️ Reload function is currently unavailable")
                await interaction.response.send_message(msg, ephemeral=True)
        except PermissionError as e:
            err = _ti(interaction, "commands", "system_prompt", "errors", "permission_denied", fallback="Permission denied")
            await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error reloading config: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
```

- [ ] **Step 4: Commit**

```bash
git add cogs/system_prompt/views.py
git commit -m "feat: update SystemPromptMainView to use LocalizedView and translations"
```

---

## Task 4：更新 `SystemPromptSetView` 與 `EditModeSelectionView`

**Files:**
- Modify: `cogs/system_prompt/views.py`

- [ ] **Step 1: 替換 `SystemPromptSetView`**

```python
class SystemPromptSetView(LocalizedView):
    """設定系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "channel_specific", fallback="Channel Specific"),
            emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0,
        ))
        self.add_item(SystemPromptScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "server_default", fallback="Server Default"),
            emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))
```

- [ ] **Step 2: 更新 `SystemPromptSetView.scope_callback` 使用翻譯**

將 `scope_callback` 方法替換為：

```python
    async def scope_callback(self, interaction: discord.Interaction, scope: str):
        try:
            if not interaction.guild:
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'server_only', fallback='Server only')}",
                    ephemeral=True,
                )
                return
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)
            target_channel_obj: Optional[discord.TextChannel] = None

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_channel", interaction.channel
                )
                target_channel_obj = interaction.channel
                raw = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                          fallback="Channel #{channel}")
                scope_text = raw.format(channel=interaction.channel.name)
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_server", interaction.guild
                )
                scope_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                 fallback="Server Default")

            view = EditModeSelectionView(
                manager=self.manager,
                permission_validator=self.permission_validator,
                scope=scope,
                target_channel=target_channel_obj,
                scope_text=scope_text,
                guild=interaction.guild,
                guild_id=guild_id,
            )
            title_tpl = _ti(interaction, "commands", "system_prompt", "ui", "menus", "edit_mode_title",
                            fallback="⚙️ Edit {scope} Prompt")
            title = title_tpl.format(scope=scope_text)
            description = _ti(interaction, "commands", "system_prompt", "ui", "menus", "edit_mode_description",
                               fallback="Please select edit mode")
            embed = discord.Embed(title=title, description=description, color=discord.Color.blue())

            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except PermissionError as e:
            self.logger.warning(f"Permission denied: {e} by {interaction.user} for scope {scope}")
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'permission_denied', fallback='Permission denied')}: {e}",
                ephemeral=True,
            )
        except Exception as e:
            self.logger.error(f"Error handling scope selection: {e}", exc_info=True)
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)
```

- [ ] **Step 3: 替換 `EditModeSelectionView`**

```python
class EditModeSelectionView(LocalizedView):
    """編輯模式選擇選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        scope: str,
        target_channel: Optional[discord.TextChannel],
        scope_text: str,
        guild: discord.Guild,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.guild = guild
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(EditModeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "direct_edit", fallback="Direct Edit"),
            emoji="✏️", style=discord.ButtonStyle.primary, edit_mode="direct", row=0,
        ))
        self.add_item(EditModeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "module_edit", fallback="Module Edit"),
            emoji="📦", style=discord.ButtonStyle.secondary, edit_mode="module", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))
```

- [ ] **Step 4: 更新 `EditModeSelectionView._handle_direct_edit` 中 modal 標題**

在 `_handle_direct_edit` 方法內，將 `modal = SystemPromptModal(title="編輯系統提示", ...)` 改為：

```python
        modal_title = _ti(
            interaction,
            "commands", "system_prompt", "ui", "modals", "system_prompt", "title_edit",
            fallback="Edit System Prompt",
        )
        modal = SystemPromptModal(
            title=modal_title,
            initial_value=existing_content,
            callback_func=lambda i, prompt_content: self._handle_direct_set_callback(i, prompt_content),
            manager=self.manager,
            channel_id=str(self.target_channel.id) if self.scope == "channel" and self.target_channel else "",
            guild_id=guild_id_str,
            show_default_content=not existing_content,
        )
```

- [ ] **Step 5: 更新 `_handle_module_edit` 的 embed 文字**

在 `_handle_module_edit` 方法內，將 embed 建立改為：

```python
            guild_id = str(self.guild.id)
            title_tpl = _ti(
                interaction,
                "commands", "system_prompt", "ui", "menus", "edit_mode_title",
                fallback="⚙️ Edit {scope} Prompt",
            )
            embed = discord.Embed(
                title=title_tpl.format(scope=self.scope_text),
                description=_ti(interaction, "commands", "system_prompt", "ui", "menus", "module_scope_description",
                                 fallback="Please select module to edit"),
                color=discord.Color.purple(),
            )
```

- [ ] **Step 6: 更新 `_handle_direct_set_callback` 成功 embed 使用翻譯**

將成功 embed 建立（約第 550 行）替換為：

```python
                embed = discord.Embed(
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "set",
                              fallback="✅ System prompt set successfully"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "set_description",
                                    fallback="Successfully set {scope} system prompt").format(scope=self.scope_text),
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name=_ti(interaction, "commands", "system_prompt", "messages", "info", "content_length",
                             fallback="Content length"),
                    value=f"{len(content)} characters",
                    inline=True,
                )
                embed.add_field(
                    name=_ti(interaction, "commands", "system_prompt", "messages", "info", "created_by",
                             fallback="Created by"),
                    value=interaction.user.mention,
                    inline=True,
                )
```

- [ ] **Step 7: Commit**

```bash
git add cogs/system_prompt/views.py
git commit -m "feat: update SystemPromptSetView and EditModeSelectionView with translations"
```

---

## Task 5：更新 `SystemPromptViewOptionsView` 與 `ModuleEditView`

**Files:**
- Modify: `cogs/system_prompt/views.py`

- [ ] **Step 1: 替換 `SystemPromptViewOptionsView`**

```python
class SystemPromptViewOptionsView(LocalizedView):
    """查看配置選項選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(source=__name__, server_id="system")

        self.add_item(SystemPromptViewButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "current_channel", fallback="Current Channel"),
            emoji="📢", style=discord.ButtonStyle.primary, view_type="current", row=0,
        ))
        self.add_item(SystemPromptViewButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "show_inheritance", fallback="Show Inheritance"),
            emoji="🔗", style=discord.ButtonStyle.secondary, view_type="inheritance", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))
```

- [ ] **Step 2: 更新 `view_callback` 中的硬編碼訊息**

在 `view_callback` 方法中，將前置檢查的錯誤訊息替換：

```python
            if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
                await interaction.response.send_message(
                    f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'text_channel_only', fallback='Text channel only')}",
                    ephemeral=True,
                )
                return
```

將 `view_type == "inheritance"` 區塊中的硬編碼字串替換：

```python
            if view_type == "inheritance":
                yaml_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_yaml",
                               fallback="🔹 YAML Base Prompt")
                srv_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_server",
                              fallback="🔸 Server Default Prompt")
                ch_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_channel",
                             fallback="🟢 Channel Specific Prompt")
                title_lbl = _ti(interaction, "commands", "system_prompt", "messages", "info", "inheritance_title",
                                fallback="Inheritance Hierarchy")

                inheritance_info = [f"**{yaml_lbl}**"]
                server_level_config = system_prompts.get("server_level", {})
                if server_level_config.get("prompt") or server_level_config.get("modules"):
                    inheritance_info.append(f"**{srv_lbl}**")
                if channel_id_str in channels_config:
                    ch_cfg = channels_config[channel_id_str]
                    if ch_cfg.get("prompt") or ch_cfg.get("modules"):
                        inheritance_info.append(f"**{ch_lbl}**")

                embed.add_field(
                    name=title_lbl,
                    value="\n".join(inheritance_info),
                    inline=False,
                )
                embed.set_footer(text=f"{prompt_data.get('source', 'unknown')}")
```

- [ ] **Step 3: 替換 `ModuleEditView` — `__init__`、`_setup_scope_selector`、`_setup_module_selector`**

`__init__` 簽名改為：

```python
class ModuleEditView(LocalizedView):
    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        modules: List[str],
        guild: discord.Guild,
        scope: Optional[str] = None,
        target_channel: Optional[discord.TextChannel] = None,
        scope_text: Optional[str] = None,
        guild_id: str = "system",
        timeout: float = 300.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.modules = modules
        self.guild = guild
        self.scope = scope
        self.target_channel = target_channel
        self.scope_text = scope_text
        self.logger = get_logger(source=__name__, server_id="system")
        self.selected_scope = scope

        if scope and scope_text:
            self._setup_module_selector()
        else:
            self._setup_scope_selector()
```

`_setup_scope_selector` 替換為：

```python
    def _setup_scope_selector(self):
        self.clear_items()
        self.add_item(ModuleScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "channel_module", fallback="Channel Module"),
            emoji="📢", style=discord.ButtonStyle.primary, scope="channel", row=0,
        ))
        self.add_item(ModuleScopeButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "server_module", fallback="Server Module"),
            emoji="🏠", style=discord.ButtonStyle.secondary, scope="server", row=0,
        ))
        self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))
```

`_setup_module_selector` 替換為：

```python
    def _setup_module_selector(self):
        self.clear_items()
        placeholder = self._t("commands", "system_prompt", "ui", "selectors", "module_placeholder",
                               fallback="Select module to edit")
        desc_tpl = self._t("commands", "system_prompt", "ui", "selectors", "module_description",
                            fallback="Edit {module} module")

        options = [
            discord.SelectOption(
                label=mod,
                value=mod,
                description=desc_tpl.format(module=mod)[:100],
            )
            for mod in self.modules[:25]
        ]

        if options:
            effective_scope = self.selected_scope or self.scope
            select = ModuleSelect(
                placeholder=placeholder,
                options=options,
                manager=self.manager,
                scope=effective_scope,
                channel=self.target_channel if effective_scope == "channel" else None,
                guild=self.guild,
                scope_text=self.scope_text or (
                    f"#{self.target_channel.name}" if self.target_channel else "server"
                ),
            )
            self.add_item(select)
            self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))
        else:
            no_mod = self._t("commands", "system_prompt", "messages", "info", "modules_none",
                             fallback="No modules available")
            self.add_item(discord.ui.Button(label=no_mod, style=discord.ButtonStyle.secondary, disabled=True))
            self.add_item(BackButton(guild_id=self.guild_id, bot=self.manager.bot, row=1))
```

- [ ] **Step 4: 更新 `ModuleEditView.scope_callback` 的 scope_text 計算**

在 `scope_callback` 方法中，將 scope_text 計算替換為：

```python
            guild_id = str(interaction.guild.id)
            self.guild = interaction.guild

            if scope == "channel":
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_channel", interaction.channel
                )
                self.target_channel = interaction.channel
                raw = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_channel",
                          fallback="Channel #{channel}")
                self.scope_text = raw.format(channel=interaction.channel.name)
            else:
                self.permission_validator.validate_permission_or_raise(
                    interaction.user, "modify_server", interaction.guild
                )
                self.target_channel = None
                self.scope_text = _ti(interaction, "commands", "system_prompt", "messages", "info", "scope_server",
                                      fallback="Server Default")

            self.selected_scope = scope
            self.guild_id = guild_id  # update for re-setup
            self.modules = self.manager.get_available_modules()
            self._setup_module_selector()

            title_tpl = _ti(interaction, "commands", "system_prompt", "ui", "menus", "edit_mode_title",
                            fallback="⚙️ Edit {scope} Prompt")
            embed = discord.Embed(
                title=title_tpl.format(scope=self.scope_text),
                description=_ti(interaction, "commands", "system_prompt", "ui", "menus", "module_scope_description",
                                 fallback="Please select module to edit"),
                color=discord.Color.purple(),
            )
            await interaction.response.edit_message(embed=embed, view=self)
```

- [ ] **Step 5: Commit**

```bash
git add cogs/system_prompt/views.py
git commit -m "feat: update SystemPromptViewOptionsView and ModuleEditView with translations"
```

---

## Task 6：更新 `SystemPromptCopyView`、`SystemPromptRemoveView`、`SystemPromptResetView`

**Files:**
- Modify: `cogs/system_prompt/views.py`

- [ ] **Step 1: 替換 `SystemPromptCopyView`**

```python
class SystemPromptCopyView(LocalizedView):
    """複製系統提示選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild: discord.Guild,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.guild = guild
        self.logger = get_logger(server_id="system", source=__name__)

        text_channels = [
            ch for ch in guild.text_channels
            if ch.permissions_for(guild.me).view_channel and ch.permissions_for(guild.me).send_messages
        ]

        if text_channels:
            from_placeholder = self._t("commands", "system_prompt", "ui", "selectors", "from_channel_placeholder",
                                        fallback="Select source channel")
            to_placeholder = self._t("commands", "system_prompt", "ui", "selectors", "to_channel_placeholder",
                                      fallback="Select target channel")
            execute_label = self._t("commands", "system_prompt", "ui", "buttons", "execute_copy",
                                     fallback="Execute Copy")

            options = [
                discord.SelectOption(label=f"#{ch.name}", value=str(ch.id), description=f"ID: {ch.id}")
                for ch in text_channels[:25]
            ]
            self.add_item(ChannelSelect(placeholder=from_placeholder, options=options, custom_id="from_channel", row=0))
            self.add_item(ChannelSelect(placeholder=to_placeholder, options=list(options), custom_id="to_channel", row=1))
            self.add_item(CopyExecuteButton(label=execute_label, row=2))
            self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=3))
        else:
            no_ch = self._t("commands", "system_prompt", "errors", "no_channels_available",
                             fallback="No channels available")
            self.add_item(discord.ui.Button(label=no_ch, style=discord.ButtonStyle.secondary, disabled=True, row=0))
            self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))
```

- [ ] **Step 2: 替換 `SystemPromptRemoveView`**

```python
class SystemPromptRemoveView(LocalizedView):
    """移除系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(server_id="system", source=__name__)

        self.add_item(RemoveButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_channel_prompt",
                          fallback="Remove Channel Prompt"),
            emoji="📢", style=discord.ButtonStyle.danger, remove_type="channel", row=0,
        ))
        self.add_item(RemoveButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "remove_server_prompt",
                          fallback="Remove Server Prompt"),
            emoji="🏠", style=discord.ButtonStyle.danger, remove_type="server", row=0,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=1))
```

- [ ] **Step 3: 替換 `SystemPromptResetView`**

```python
class SystemPromptResetView(LocalizedView):
    """重置系統提示的子選單"""

    def __init__(
        self,
        manager: SystemPromptManager,
        permission_validator: PermissionValidator,
        guild_id: str = "system",
        timeout: float = 180.0,
    ):
        super().__init__(manager, guild_id, timeout)
        self.permission_validator = permission_validator
        self.logger = get_logger(server_id="system", source=__name__)

        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_current_channel",
                          fallback="Reset Current Channel"),
            emoji="📢", style=discord.ButtonStyle.danger, reset_type="channel", row=0,
        ))
        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_server_default",
                          fallback="Reset Server Default"),
            emoji="🏠", style=discord.ButtonStyle.danger, reset_type="server", row=0,
        ))
        self.add_item(ResetButton(
            label=self._t("commands", "system_prompt", "ui", "buttons", "reset_all_settings",
                          fallback="Reset All Settings"),
            emoji="⚠️", style=discord.ButtonStyle.danger, reset_type="all", row=1,
        ))
        self.add_item(BackButton(guild_id=guild_id, bot=manager.bot, row=2))
```

- [ ] **Step 4: Commit**

```bash
git add cogs/system_prompt/views.py
git commit -m "feat: update CopyView, RemoveView, ResetView with translations"
```

---

## Task 7：更新 `BackButton`、`CopyExecuteButton` 與 callback 動態訊息

**Files:**
- Modify: `cogs/system_prompt/views.py`

- [ ] **Step 1: 替換 `BackButton`**

```python
class BackButton(discord.ui.Button):
    """返回主選單按鈕"""

    def __init__(self, guild_id: str = "system", bot=None, row: int = 4):
        label = "Back"
        try:
            if bot and (lm := bot.get_cog("LanguageManager")):
                label = lm.translate(guild_id, "commands", "system_prompt", "ui", "buttons", "back_to_main")
        except Exception:
            pass
        super().__init__(label=label, emoji="🔙", style=discord.ButtonStyle.secondary, row=row)
        self.guild_id = guild_id
        self._bot = bot
        self.logger = get_logger(server_id="system", source=__name__)

    async def callback(self, interaction: discord.Interaction):
        try:
            commands_cog = interaction.client.get_cog("SystemPromptCommands")
            if commands_cog and hasattr(commands_cog, "get_system_prompt_manager") and hasattr(commands_cog, "permission_validator"):
                manager = commands_cog.get_system_prompt_manager()
                permission_validator = commands_cog.permission_validator
                guild_id = str(interaction.guild.id) if interaction.guild else self.guild_id

                main_view = SystemPromptMainView(manager, permission_validator, guild_id=guild_id)
                title = _ti(interaction, "commands", "system_prompt", "ui", "main_menu", "title",
                            fallback="🤖 System Prompt Management")
                description = _ti(interaction, "commands", "system_prompt", "ui", "main_menu", "description",
                                  fallback="Please select a function")
                embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
                await interaction.response.edit_message(embed=embed, view=main_view)
            else:
                self.logger.error("SystemPromptCommands cog not found for BackButton.")
                err = _ti(interaction, "commands", "system_prompt", "errors", "internal_error",
                          fallback="Internal error")
                await interaction.response.edit_message(content=f"❌ {err}", embed=None, view=None)
        except Exception as e:
            self.logger.error(f"BackButton callback error: {e}", exc_info=True)
            await interaction.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)
```

- [ ] **Step 2: 替換 `CopyExecuteButton`**

```python
class CopyExecuteButton(discord.ui.Button):
    """執行複製按鈕"""

    def __init__(self, label: str = "Execute Copy", **kwargs):
        super().__init__(label=label, emoji="📋", style=discord.ButtonStyle.success, **kwargs)
        self.logger = get_logger(server_id="system", source=__name__)
```

（callback 方法保持不變，但錯誤訊息改為 `_ti()`，見下步）

- [ ] **Step 3: 更新 `CopyExecuteButton.callback` 的錯誤訊息**

在 `CopyExecuteButton.callback` 中，將所有硬編碼錯誤訊息替換：

```python
        if not from_channel_id or not to_channel_id:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'validation_failed', fallback='Please select source and target channels')}",
                ephemeral=True,
            )
            return
        if from_channel_id == to_channel_id:
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'messages', 'validation', 'same_channel', fallback='Source and target must differ')}",
                ephemeral=True,
            )
            return
```

成功訊息替換為：

```python
                from_channel_obj = view.guild.get_channel(int(from_channel_id))
                from_name = from_channel_obj.name if from_channel_obj else "unknown"
                embed = discord.Embed(
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "copy",
                              fallback="✅ Copy successful"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "copy_description",
                                    fallback="Copied from #{from_channel} to #{to_channel}").format(
                        from_channel=from_name, to_channel=to_channel_obj.name
                    ),
                    color=discord.Color.green(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
```

- [ ] **Step 4: 更新 `RemoveButton.callback` 確認與結果訊息**

在 `RemoveButton.callback` 中，將確認文字計算替換為：

```python
            guild_id = str(interaction.guild.id) if interaction.guild else "system"

            if self.remove_type == "channel":
                ...
                raw = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "remove_channel",
                          fallback="Remove channel #{channel} prompt?")
                confirm_text = raw.format(channel=interaction.channel.name)
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_remove",
                                 fallback="⚠️ Confirm Removal")
            else:
                confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "remove_server",
                                   fallback="Remove server default prompt?")
                title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_remove",
                                 fallback="⚠️ Confirm Removal")

            confirm_embed = discord.Embed(title=title_text, description=confirm_text, color=discord.Color.orange())
```

成功結果 embed 替換為：

```python
                    result_embed = discord.Embed(
                        title=_ti(interaction, "commands", "system_prompt", "messages", "success", "remove",
                                  fallback="✅ Removal successful"),
                        description=_ti(interaction, "commands", "system_prompt", "messages", "success", "remove_description",
                                        fallback="Removed {scope} system prompt").format(scope=operation_text),
                        color=discord.Color.green(),
                    )
```

- [ ] **Step 5: 更新 `ResetButton.callback` 確認與結果訊息**

依相同模式，在 `ResetButton.callback` 中：

channel 確認文字：
```python
raw = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_channel",
          fallback="Reset channel #{channel} prompt?")
confirm_text = raw.format(channel=interaction.channel.name)
```

server 確認文字：
```python
confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_server",
                   fallback="Reset server default prompt?")
```

all 確認文字：
```python
confirm_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "reset_all",
                   fallback="Reset ALL system prompt settings? This cannot be undone!")
```

title 文字：
```python
title_text = _ti(interaction, "commands", "system_prompt", "messages", "confirm", "title_reset",
                 fallback="⚠️ Confirm Reset")
```

成功 embed：
```python
                    result_embed = discord.Embed(
                        title=_ti(interaction, "commands", "system_prompt", "messages", "success", "reset",
                                  fallback="✅ Reset successful"),
                        description=_ti(interaction, "commands", "system_prompt", "messages", "success", "reset_description",
                                        fallback="Reset {scope} settings").format(scope=operation_text),
                        color=discord.Color.green(),
                    )
```

- [ ] **Step 6: 更新 `ModuleSelect._handle_module_callback` 成功 embed**

```python
                embed = discord.Embed(
                    title=_ti(interaction, "commands", "system_prompt", "messages", "success", "set",
                              fallback="✅ Module set successfully"),
                    description=_ti(interaction, "commands", "system_prompt", "messages", "success", "set_description",
                                    fallback="Set {scope} {module}").format(
                        scope=display_scope_text, module=module_name
                    ),
                    color=discord.Color.green(),
                )
```

- [ ] **Step 7: 更新小型 Button callback 的「View not found」訊息**

`SystemPromptFunctionButton`、`EditModeButton`、`SystemPromptScopeButton`、`SystemPromptViewButton`、`ModuleScopeButton` 的 callback 中各有一個 `else` 分支（view 找不到時）。將所有此類 `"❌ 內部錯誤，請稍後再試。"` 替換為（5 個位置）：

```python
            await interaction.response.send_message(
                f"❌ {_ti(interaction, 'commands', 'system_prompt', 'errors', 'internal_error', fallback='Internal error')}",
                ephemeral=True,
            )
```

- [ ] **Step 8: 更新 `ModuleSelect.callback` 的錯誤訊息**

在 `ModuleSelect.callback` 的 except 區塊中，將 `f"❌ 開啟編輯器失敗：{str(e)}"` 替換為：

```python
            err = _ti(interaction, "commands", "system_prompt", "errors", "operation_failed", fallback="Operation failed")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ {err}: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {err}: {e}", ephemeral=True)
```

- [ ] **Step 9: Commit**

```bash
git add cogs/system_prompt/views.py
git commit -m "feat: update BackButton, CopyExecuteButton and all callback messages with translations"
```

---

## Task 8：更新 `commands.py` 傳入 `guild_id`

**Files:**
- Modify: `cogs/system_prompt/commands.py`

- [ ] **Step 1: 在 `system_prompt` 命令中傳入 `guild_id`**

在 `commands.py` 的 `system_prompt` 方法中，找到建立 `SystemPromptMainView` 的程式碼（約第 118 行），替換為：

```python
        guild_id = str(interaction.guild.id) if interaction.guild else "system"
        main_view = SystemPromptMainView(
            manager=self.manager,
            permission_validator=self.permission_validator,
            guild_id=guild_id,
        )
```

- [ ] **Step 2: 執行全部測試確認沒有退化**

```bash
python -m pytest tests/ -v 2>&1 | tail -20
```

預期：所有測試通過（包含 Task 1 & 2 新增的 28 個測試）

- [ ] **Step 3: Commit**

```bash
git add cogs/system_prompt/commands.py
git commit -m "feat: pass guild_id to SystemPromptMainView from slash command"
```

---

## 自審核清單（實作者完成後確認）

- [ ] `tests/test_system_prompt_i18n.py` 全部 28 個測試通過
- [ ] 4 個語言 JSON 的 `reload_config`、`direct_edit`、`edit_mode_title`、`edit_mode_description`、`messages.success.reload`、`messages.info.reload_unavailable` 均已新增
- [ ] `LocalizedView` 繼承 `discord.ui.View`，方法僅有 `__init__` 與 `_t()`
- [ ] 8 個 View 全部改繼承 `LocalizedView`，`__init__` 均接受 `guild_id` 參數
- [ ] `BackButton.__init__` 接受 `guild_id` 與 `bot`，callback 重建主選單時使用 `str(interaction.guild.id)`
- [ ] `CopyExecuteButton.__init__` 接受 `label` 參數
- [ ] 所有 `_handle_*` callback 建立子 View 時傳入 `guild_id = str(interaction.guild.id)`
- [ ] `scope_text` 透過 `messages.info.scope_channel.format(channel=...)` 與 `messages.info.scope_server` 建構
- [ ] `commands.py` 傳入 `guild_id=str(interaction.guild.id)` 至 `SystemPromptMainView`
- [ ] `_ti()` 在所有非 LocalizedView 的 callback 中一致使用
