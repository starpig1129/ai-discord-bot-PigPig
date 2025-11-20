# Protected Prompt Management System

## 概述

此系統實現了**雙層提示詞管理架構**，確保系統層級的關鍵提示詞不會被使用者意外修改，同時允許使用者自訂個性化的機器人行為。

## 架構設計

### 兩層提示詞分類

#### 1. **受保護模組（Protected Modules）** ❌ 不可修改

這些模組包含系統運作的關鍵指示，**絕對不允許使用者修改**：

- **`output_format`**: Discord 格式規則（`<som>` `<eom>` 標籤、時間戳格式、mention 格式等）
- **`input_parsing`**: 訊息格式理解、發言者識別、代名詞使用規則
- **`memory_system`**: Procedural Memory 和 Short-term Memory 的使用方式
- **`information_handling`**: 資訊來源的優先順序
- **`error_handling`**: 錯誤處理指南
- **`reminders`**: 最後的關鍵提醒

**為什麼這些必須保護？**
- 如果使用者修改了 Output Format，bot 的回應可能無法正確被解析
- 如果修改了 Input Parsing，bot 可能無法正確理解多使用者對話
- 如果修改了 Memory System，bot 可能無法正確使用上下文記憶

#### 2. **可自訂模組（Customizable Modules）** ✅ 可修改

這些模組允許使用者自訂機器人的個性和行為：

- **`identity`**: 機器人名稱、創建者、角色定義
- **`response_principles`**: 語氣、風格、語言偏好、回應長度
- **`interaction`**: 互動方式、參與度
- **`professional_personality`**: 專業模式的個性設定

**使用者可以自訂什麼？**
- 機器人的名字和角色
- 對話的語氣（幽默/正式/友善等）
- 回應的風格和長度偏好
- 語言和措辭習慣

## 使用方法

### 在 Orchestrator 中的實現

```python
from llm.prompting.protected_prompt_manager import get_protected_prompt_manager

# 獲取 Protected Prompt Manager
protected_manager = get_protected_prompt_manager()

# 組合系統提示詞
# 受保護的模組永遠從 base_configs 載入
# 可自訂的模組可以透過 custom_module_contents 覆蓋
system_prompt = protected_manager.compose_system_prompt(
    custom_module_contents={
        'identity': '自訂的身份描述',  # ✅ 允許
        'output_format': '自訂的格式'   # ❌ 會被忽略，使用 base_configs 版本
    }
)
```

### 檢查模組是否受保護

```python
# 檢查模組是否受保護
protected_manager.is_module_protected('output_format')  # True
protected_manager.is_module_customizable('identity')    # True

# 獲取模組資訊
info = protected_manager.get_module_info()
# {
#     'protected_modules': ['output_format', 'input_parsing', ...],
#     'customizable_modules': ['identity', 'response_principles', ...],
#     'module_descriptions': {...}
# }
```

### 設定自訂模組

```python
# 只有可自訂的模組才能設定
success = protected_manager.set_custom_module('identity', '我是一個友善的助手')
# Returns True

# 嘗試設定受保護的模組會失敗
success = protected_manager.set_custom_module('output_format', '自訂格式')
# Returns False, 並記錄警告日誌
```

## 資料流程

```
User Request → Orchestrator
                    ↓
         _build_message_agent_prompt()
                    ↓
         ProtectedPromptManager
                    ↓
    ┌───────────────┴────────────────┐
    │                                │
Protected Modules          Customizable Modules
(base_configs ONLY)      (base_configs + custom overrides)
    │                                │
    └───────────────┬────────────────┘
                    ↓
         compose_system_prompt()
                    ↓
         Complete System Prompt
         (with variable replacements)
                    ↓
            Message Agent
```

## 安全性保證

1. **受保護模組永遠從 base_configs 載入**
   - 即使資料庫或設定中有覆蓋，也會被忽略
   - 確保系統關鍵指示不會被破壞

2. **明確的模組分類**
   - `PROTECTED_MODULES` 和 `CUSTOMIZABLE_MODULES` 在程式碼中明確定義
   - 任何新增的模組都需要明確分類

3. **日誌記錄和錯誤報告**
   - 所有嘗試修改受保護模組的行為都會被記錄
   - 提供清楚的錯誤訊息指導正確使用

## 未來擴展

### 階段 1（當前）✅
- 實現基礎的受保護/可自訂模組分離
- 在 Orchestrator 中使用 ProtectedPromptManager
- 為 message_agent 提供保護

### 階段 2（計劃中）
- 同樣為 info_agent 實現保護機制
- 在資料庫層面實現自訂模組儲存
- 提供 Discord 指令讓使用者管理自訂模組

### 階段 3（計劃中）
- 實現模組版本控制
- 提供模組範本和預設套裝
- 更精細的權限控制（server-level, channel-level）

## 範例場景

### 場景 1：使用者想要更改機器人名稱

```python
# ✅ 允許：identity 是可自訂模組
protected_manager.set_custom_module('identity', """
## Bot Identity
- Name: 超級助手 <@{bot_id}>
- Creator: {creator} <@{bot_owner_id}>
- Platform: {environment}
- Role: 專業的技術支援助手
""")
```

### 場景 2：使用者嘗試修改輸出格式

```python
# ❌ 拒絕：output_format 是受保護模組
result = protected_manager.set_custom_module('output_format', """
## Custom Output Format
- Use [bot]: prefix instead of <som><eom> tags
""")
# result = False
# 日誌：Cannot customize protected module 'output_format'
```

### 場景 3：組合帶有自訂模組的提示詞

```python
custom_modules = {
    'identity': '自訂身份',
    'response_principles': '自訂回應原則'
}

prompt = protected_manager.compose_system_prompt(
    custom_module_contents=custom_modules
)

# 結果：
# - identity, response_principles 使用自訂內容
# - output_format, input_parsing 等受保護模組使用 base_configs
```

## 疑難排解

### Q: 為什麼我的自訂提示詞沒有生效？

A: 檢查你嘗試自訂的是否是受保護模組。使用 `is_module_protected()` 確認。

### Q: 如何知道哪些模組可以自訂？

A: 使用 `get_module_info()` 方法查看所有模組分類。

### Q: 受保護模組是否會隨版本更新？

A: 是的，受保護模組會隨著 base_configs 的更新而更新，確保系統功能始終正常。

## 相關檔案

- `llm/prompting/protected_prompt_manager.py` - 保護系統實現
- `llm/orchestrator.py` - 在 Orchestrator 中的使用
- `base_configs/prompt/message_agent.yaml` - 基礎配置（包含所有模組）
- `base_configs/prompt/info_agent.yaml` - Info Agent 配置

## 總結

Protected Prompt Management System 提供了一個平衡的方案：

✅ **保護系統完整性**：關鍵的 Discord 格式和上下文處理指示不會被破壞
✅ **允許個性化**：使用者仍然可以自訂機器人的性格和行為
✅ **清楚的界限**：明確區分哪些可以改，哪些不能改
✅ **向後兼容**：現有的 get_system_prompt 仍然可以作為 fallback
