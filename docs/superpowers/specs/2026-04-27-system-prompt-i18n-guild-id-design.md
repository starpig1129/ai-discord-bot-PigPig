# System Prompt UI — i18n 修復與 guild_id 傳遞設計

**日期**：2026-04-27  
**狀態**：已核准  
**範圍**：`cogs/system_prompt/views.py`、`cogs/system_prompt/commands.py`、`translations/*/commands/system_prompt.json`

---

## 問題描述

1. `views.py` 中所有 View 的按鈕標籤、選擇器 placeholder、確認/錯誤訊息均為硬編碼中文字串，完全繞過翻譯系統。
2. `SystemPromptMainView._setup_main_buttons()` 使用 `guild_id = "system"` 而非實際伺服器 ID，導致即使呼叫了 `LanguageManager.translate()`，也永遠只回傳預設語言（zh_TW）的翻譯。
3. 子 View（SetView、ViewOptionsView、ModuleEditView 等）沒有接收 `guild_id`，因此無法進行正確的多語言翻譯。
4. 4 個語言的 `system_prompt.json` 缺少部分 key（`reload_config`、`direct_edit`、`edit_mode_title`、`edit_mode_description`、`messages.success.reload`、`messages.info.reload_unavailable`）。

---

## 設計目標

- 所有顯示給使用者的字串（按鈕標籤、選擇器 placeholder、embed 文字、確認/錯誤訊息）一律使用翻譯系統。
- `guild_id` 從 Discord interaction 正確向下傳遞至整個 View 層級。
- 補齊 4 個語言的缺失翻譯 key。
- 不改動翻譯系統本身（`language_manager.py`）、業務邏輯（`manager.py`）或 `ui.py`。

---

## 架構：`LocalizedView` 基礎類別

在 `views.py` 新增一個薄基礎類別，提供翻譯方法：

```python
class LocalizedView(discord.ui.View):
    def __init__(self, manager: SystemPromptManager, guild_id: str = "system", timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.manager = manager
        self.guild_id = guild_id
        self._bot = manager.bot

    def _t(self, *keys: str, fallback: str = "") -> str:
        """翻譯輔助方法，找不到 key 或 LanguageManager 不可用時回傳 fallback。"""
        try:
            lm = self._bot.get_cog("LanguageManager") if self._bot else None
            if lm:
                return lm.translate(self.guild_id, *keys)
        except Exception:
            pass
        return fallback or (keys[-1] if keys else "")
```

所有現有 View 改為繼承 `LocalizedView`：

| View 類別 | 原繼承 | 新繼承 |
|-----------|--------|--------|
| `SystemPromptMainView` | `discord.ui.View` | `LocalizedView` |
| `SystemPromptSetView` | `discord.ui.View` | `LocalizedView` |
| `EditModeSelectionView` | `discord.ui.View` | `LocalizedView` |
| `SystemPromptViewOptionsView` | `discord.ui.View` | `LocalizedView` |
| `ModuleEditView` | `discord.ui.View` | `LocalizedView` |
| `SystemPromptCopyView` | `discord.ui.View` | `LocalizedView` |
| `SystemPromptRemoveView` | `discord.ui.View` | `LocalizedView` |
| `SystemPromptResetView` | `discord.ui.View` | `LocalizedView` |

---

## guild_id 傳遞鏈

`guild_id` 永遠從當下的 `interaction.guild.id` 取得，而非從父 View 的 `self.guild_id` 往下傳。這確保語言切換能即時生效。

```
commands.py: system_prompt(interaction)
  guild_id = str(interaction.guild.id)
  → SystemPromptMainView(manager, permission_validator, guild_id)

SystemPromptMainView._handle_set_function(interaction)
  guild_id = str(interaction.guild.id)
  → SystemPromptSetView(manager, permission_validator, guild_id)

SystemPromptSetView.scope_callback(interaction, scope)
  guild_id = str(interaction.guild.id)
  → EditModeSelectionView(manager, permission_validator, scope, channel, scope_text, guild, guild_id)

（其他 callback 以相同模式類推）
```

**`BackButton`** 例外：它不繼承 `LocalizedView`，改為接收 `guild_id` 和 `bot` 兩個參數，在 `__init__` 時用 `bot.get_cog("LanguageManager")` 翻譯 label，在 callback 中用儲存的 `guild_id` 重建 `SystemPromptMainView`。

---

## 補齊翻譯 key

修改 `translations/{zh_TW,zh_CN,en_US,ja_JP}/commands/system_prompt.json`，新增以下 key：

### `ui.buttons`
| key | zh_TW | zh_CN | en_US | ja_JP |
|-----|-------|-------|-------|-------|
| `reload_config` | 重載設定 | 重载配置 | Reload Config | 設定を再読込 |
| `direct_edit` | 直接編輯 | 直接编辑 | Direct Edit | 直接編集 |

### `ui.menus`
| key | zh_TW | zh_CN | en_US | ja_JP |
|-----|-------|-------|-------|-------|
| `edit_mode_title` | ⚙️ 編輯 {scope} 系統提示 | ⚙️ 编辑 {scope} 系统提示 | ⚙️ Edit {scope} Prompt | ⚙️ {scope} プロンプトを編集 |
| `edit_mode_description` | 請選擇編輯模式 | 请选择编辑模式 | Please select edit mode | 編集モードを選択してください |

### `messages.success`
| key | zh_TW | zh_CN | en_US | ja_JP |
|-----|-------|-------|-------|-------|
| `reload` | ✅ 設定已成功重載 | ✅ 配置重载成功 | ✅ Configuration reloaded successfully | ✅ 設定の再読込が成功しました |

### `messages.info`
| key | zh_TW | zh_CN | en_US | ja_JP |
|-----|-------|-------|-------|-------|
| `reload_unavailable` | ⚠️ 重載功能目前無法使用 | ⚠️ 重载功能目前不可用 | ⚠️ Reload function is currently unavailable | ⚠️ 再読込機能は現在利用できません |

---

## 硬編碼字串替換範圍

### `views.py` — View `__init__` 按鈕標籤（建立時翻譯）

| View | 硬編碼字串 | 翻譯 key |
|------|-----------|---------|
| `SystemPromptMainView` | `"Reload Config"` | `ui.buttons.reload_config` |
| `SystemPromptSetView` | `"頻道特定"` | `ui.buttons.channel_specific` |
| `SystemPromptSetView` | `"伺服器預設"` | `ui.buttons.server_default` |
| `EditModeSelectionView` | `"直接編輯提示"` | `ui.buttons.direct_edit` |
| `EditModeSelectionView` | `"模組化編輯"` | `ui.buttons.module_edit` |
| `SystemPromptViewOptionsView` | `"當前頻道有效提示"` | `ui.buttons.current_channel` |
| `SystemPromptViewOptionsView` | `"顯示繼承關係"` | `ui.buttons.show_inheritance` |
| `ModuleEditView._setup_scope_selector` | `"頻道模組"` | `ui.buttons.channel_module` |
| `ModuleEditView._setup_scope_selector` | `"伺服器模組"` | `ui.buttons.server_module` |
| `ModuleEditView._setup_module_selector` | `"選擇要編輯的模組"` | `ui.selectors.module_placeholder` |
| `ModuleEditView._setup_module_selector` | `"編輯 {name} 模組"` | `ui.selectors.module_description` |
| `SystemPromptCopyView` | `"選擇來源頻道"` | `ui.selectors.from_channel_placeholder` |
| `SystemPromptCopyView` | `"選擇目標頻道"` | `ui.selectors.to_channel_placeholder` |
| `SystemPromptRemoveView` | `"移除當前頻道提示"` | `ui.buttons.remove_channel_prompt` |
| `SystemPromptRemoveView` | `"移除伺服器預設提示"` | `ui.buttons.remove_server_prompt` |
| `SystemPromptResetView` | `"重置當前頻道"` | `ui.buttons.reset_current_channel` |
| `SystemPromptResetView` | `"重置伺服器預設"` | `ui.buttons.reset_server_default` |
| `SystemPromptResetView` | `"重置全部設定"` | `ui.buttons.reset_all_settings` |
| `BackButton` | `"返回主選單"` | `ui.buttons.back_to_main` |
| `CopyExecuteButton` | `"執行複製"` | `ui.buttons.execute_copy` |

### `views.py` — Callback 動態訊息（執行時翻譯）

Callback 中動態訊息改用 `interaction.client.get_cog("LanguageManager")` + `str(interaction.guild.id)` 翻譯。涵蓋：
- 所有 `errors.*` 錯誤訊息
- 所有 `messages.success.*` 成功訊息
- 所有 `messages.confirm.*` 確認訊息
- `_handle_reload_function` 的成功/不可用訊息
- `scope_text` 字串（改用 `messages.info.scope_channel`、`messages.info.scope_server`）
- 所有 `"❌ 內部錯誤..."` 類型的後備訊息

### `commands.py`

- `system_prompt()` 建立 `SystemPromptMainView` 時加入 `guild_id=str(interaction.guild.id)`。

---

## 不在本次範圍內

- 改動 `language_manager.py`、`manager.py`、`ui.py`、`permissions.py`
- UX 流程重構（選單層級、步驟數）
- 新增語言支援
- Logger 訊息（內部日誌保持現有語言）

---

## 測試驗證標準

1. 將伺服器語言設為 `en_US` 後執行 `/system_prompt`，所有按鈕標籤應顯示英文。
2. 將伺服器語言設為 `ja_JP` 後執行 `/system_prompt`，所有按鈕標籤應顯示日文。
3. 點擊各功能按鈕後的子選單按鈕也應符合伺服器語言。
4. 所有錯誤訊息、確認對話框應符合伺服器語言。
5. 當 `LanguageManager` 不可用時，所有 UI 應降級顯示英文（fallback）而非崩潰。
