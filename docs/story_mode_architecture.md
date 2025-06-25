# PigPig Discord LLM Bot - 故事功能模組架構規劃 (v2)

這份文件詳細說明了 PigPig Discord LLM Bot 的「故事功能模組」的架構設計。

## 1. 整體架構設計

故事模組將作為一個獨立的 `cog` 存在，並與現有的核心系統（頻道管理、提示管理、記憶系統、語言模型）互動。其核心思想是：當一個頻道被設定為「故事模式」時，該頻道的所有訊息將由 `StoryManager` 接管，而非通過標準的對話流程。

我們將引入一個**雙層記憶策略**：

1.  **狀態資料庫 (`StoryDB`)**: 負責儲存**即時、結構化的狀態**，如角色屬性、物品欄、世界規則等需要快速精確讀取的資料。
2.  **敘事記憶 (`MemoryManager`)**: 用於儲存**故事的歷史事件和對話**。每次故事有重大進展時，`StoryManager` 會生成一段事件摘要，並將這段摘要存入 `MemoryManager`。

### 架構互動圖 (Mermaid)

```mermaid
graph TD
    subgraph User Interaction
        A[User sends message in Story Channel]
    end

    subgraph PigPig Bot Core
        B[bot.py: on_message]
        C[cogs/channel_manager.py]
        D[cogs/system_prompt_manager.py]
        E[gpt/gpt_response_gen.py]
        MM[cogs/memory/memory_manager.py]
    end

    subgraph New Story Module
        F[cogs/story.py (Commands)]
        G[cogs/story/manager.py (StoryManager)]
        H[cogs/story/database.py (StoryDB)]
        I[cogs/story/prompt_engine.py (StoryPromptEngine)]
        J[cogs/story/state_manager.py (StoryStateManager)]
    end

    A --> B
    B -- Check Channel Mode --> C
    C -- Returns 'Story Mode' --> B
    B -- Route to Story Module --> G

    G -- Manages Story Flow --> J
    J -- Reads/Writes Current State --> H
    G -- Builds Prompt --> I
    
    I -- Gets Base Personality --> D
    I -- Searches Past Events --> MM
    
    G -- Sends to LLM --> E
    E -- Generates Story --> G
    
    G -- Updates State --> J
    G -- Stores Event Summary --> MM
    
    G -- Sends to Discord --> A

    subgraph Admin Interaction
        K[Admin uses /story commands]
    end
    K --> F
    F -- Calls Manager --> G
    G -- Updates DB --> H
```

### 流程說明

1.  **模式啟動**: 管理員使用 `/story set` 命令將特定頻道設定為故事模式。
2.  **訊息路由**: `bot.py` 的 `on_message` 事件觸發，`ChannelManager` 確認頻道為「故事模式」，將訊息處理權交給 `StoryManager`。
3.  **提示建構**: `StoryPromptEngine` 建構提示時，會：
    *   從 `StoryDB` 讀取當前的**結構化狀態**。
    *   向 `MemoryManager` 發起語意搜尋，查詢相關的**過去事件**。
    *   從 `SystemPromptManager` 獲取基礎 Bot 人格。
4.  **故事生成**: `StoryManager` 呼叫語言模型介面獲取故事的下一步發展。
5.  **狀態更新與記憶儲存**:
    *   `StoryStateManager` 解析 LLM 回應，更新 `StoryDB` 中的**當前狀態**。
    *   `StoryManager` 生成事件**文字摘要**，並呼叫 `memory_manager.store_message()` 存入長期記憶。
6.  **回應輸出**: `StoryManager` 將故事內容發送回 Discord。

---

## 2. 資料結構設計

使用 Pydantic 或 Python 的 `dataclasses` 來定義資料模型，並對應到 SQLite 資料表。

*   **`StoryWorld` (世界觀)**
    *   `guild_id: int`
    *   `world_name: str` (主鍵)
    *   `background: str`
    *   `rules: List[str]`
    *   `elements: Dict[str, Any]`

*   **`StoryCharacter` (角色)**
    *   `character_id: str` (UUID)
    *   `world_name: str` (外鍵)
    *   `name: str`
    *   `is_pc: bool`
    *   `user_id: Optional[int]`
    *   `description: str`
    *   `attributes: Dict[str, Any]`
    *   `inventory: List[str]`
    *   `status: str`

*   **`StoryInstance` (故事實例)**
    *   `channel_id: int` (主鍵)
    *   `guild_id: int`
    *   `world_name: str` (外鍵)
    *   `active_characters: List[str]`
    *   `current_state: Dict[str, Any]`
    *   `event_log: List[str]`
    *   `is_active: bool`

**資料庫方案**: 在 `cogs/story/data/` 目錄下為每個伺服器 (`guild_id`) 建立一個獨立的 SQLite 資料庫檔案 (`{guild_id}_story.db`)。

---

## 3. API 設計 (內部介面)

*   **`cogs.story.manager.StoryManager`**: 核心協調器，處理訊息、啟動/結束故事、管理世界與角色，並與 `MemoryManager` 互動。
*   **`cogs.story.database.StoryDB`**: 負責 `StoryDB` 的所有 CRUD 操作。
*   **`cogs.story.prompt_engine.StoryPromptEngine`**: 負責建構完整的 LLM 提示，會查詢 `StoryDB`, `MemoryManager`, `SystemPromptManager`。
*   **`cogs.story.state_manager.StoryStateManager`**: 負責載入、解析 LLM 輸出、更新並儲存故事的即時狀態到 `StoryDB`。

---

## 4. 檔案組織結構

```
PigPig-discord-LLM-bot/
└── cogs/
    ├── story.py             # (新) 使用者命令
    └── story/               # (新) 核心邏輯
        ├── __init__.py
        ├── manager.py         # (新) StoryManager
        ├── database.py        # (新) StoryDB
        ├── prompt_engine.py   # (新) StoryPromptEngine
        ├── state_manager.py   # (新) StoryStateManager
        ├── models.py          # (新) 資料模型
        ├── exceptions.py      # (新) 自訂例外
        └── data/              # (新) SQLite 資料庫
            └── .gitkeep
```

---

## 5. 與現有系統的整合方案

*   **`bot.py`**: 在 `on_message` 中增加路由邏輯，將故事頻道的訊息導向 `StoryManager`。
*   **`cogs/channel_manager.py`**: 在 `set_channel_mode` 命令中增加 "故事模式" (`story`) 的選項。
*   **`cogs/memory/memory_manager.py`**:
    *   `StoryManager` 將獲取並使用 `MemoryManager` 實例。
    *   故事事件摘要將被格式化後儲存到 `MemoryManager`。
    *   `StoryPromptEngine` 將使用 `SearchQuery` 從 `MemoryManager` 檢索相關歷史。
*   **`cogs/system_prompt_manager.py`**: `StoryPromptEngine` 將呼叫它來獲取基礎 Bot 人格，確保敘事風格一致。
*   **權限控制**: 所有管理命令將使用現有的管理員權限檢查邏輯。

---

## 6. 實作優先順序建議

1.  **Phase 1: 核心資料結構與儲存**: 建立檔案結構、定義資料模型、實作 `StoryDB`。
2.  **Phase 2: 基礎命令與模式切換**: 實作 `/story` 命令、修改 `ChannelManager` 和 `bot.py` 以完成訊息路由。
3.  **Phase 3: 故事生成主循環與記憶整合**: 實作 `StoryManager` 和 `StoryPromptEngine` 的骨架，並整合 `MemoryManager` 的儲存與搜尋邏輯。
4.  **Phase 4: 狀態與角色管理**: 實作 `StoryStateManager`，完成 `/story create_world` 和 `/story create_character` 命令。
5.  **Phase 5: 優化與進階功能**: 完善提示模板、權限細化、錯誤處理等。