# 故事功能模組 UI 重構架構

本文檔詳細說明了故事功能模組從命令驅動到 UI 驅動的重構計畫。

## 1. 核心設計原則

- **單一入口**: 使用者僅需透過 `/story` 命令即可存取所有功能。
- **UI 驅動互動**: 廢除繁雜的子命令，所有操作（世界創建、角色管理、故事啟動）均透過 Discord UI 元件（按鈕、選擇選單、Modals）完成。
- **臨時性介面 (Ephemeral)**: 所有 UI 介面均為臨時性，僅發起操作的使用者可見，操作完成或超時後自動消失，大幅降低 UI 狀態管理的複雜度。
- **頻道級別管理**: 所有的世界觀、角色和故事進度都與特定的頻道實例綁定，簡化了資料的歸屬和查詢邏輯。

## 2. 最終檔案結構

```
cogs/
└── story/
    ├── __init__.py
    ├── manager.py         # 核心邏輯，進行少量調整以配合 UI 呼叫
    ├── database.py        # 資料庫操作
    ├── prompt_engine.py   # 不變
    ├── state_manager.py   # 不變
    ├── models.py          # 資料模型
    ├── exceptions.py      # 不變
    └── ui/                  # (新) UI 元件
        ├── __init__.py
        ├── ui_manager.py    # (新) 負責產生並發送臨時性的 View
        ├── views.py         # (新) 存放主要的 View 元件 (e.g., StoryControlView)
        └── modals.py        # (新) 存放 Modals (e.g., WorldModal, CharacterModal)
```

## 3. 命令與 UI 流程

新的流程將以 `/story` 作為單一入口，所有後續操作都在臨時性的 UI 中完成。

```mermaid
graph TD
    subgraph User
        A[使用者輸入 /story]
    end

    subgraph Bot UI Logic
        B{檢查頻道狀態}
        C[顯示「故事初始選單」 View (臨時性)]
        D[顯示「故事進行中選單」 View (臨時性)]
    end

    subgraph User Actions
        E[點擊「創建世界」] --> F[彈出 WorldCreateModal]
        G[點擊「創建角色」] --> H[彈出 CharacterCreateModal]
        I[選擇世界並點擊「開始故事」]
    end
    
    subgraph Bot Core Logic
        J[story_manager.create_world]
        K[story_manager.create_character]
        L[story_manager.start_story]
    end

    A --> B
    B -- 頻道無故事 --> C
    B -- 頻道有故事 --> D

    C --> E
    C --> G
    C --> I

    F -- 提交 --> J
    H -- 提交 --> K
    I -- 確認 --> L

    J -- 成功 --> M[更新 C View]
    K -- 成功 --> M
    L -- 成功 --> N[發送「故事已開始」訊息]

    subgraph Bot Response
        M
        N
    end
```

## 4. 核心組件設計

- **`cogs/story.py` (命令入口)**
    -   只保留一個根命令 `/story`。
    -   其唯一職責是呼叫 `UIManager.show_main_menu(interaction)` 來啟動 UI 流程。

- **`ui/ui_manager.py` (UI 協調器)**
    -   `show_main_menu(interaction)`: 根據當前頻道是否存在活躍故事，決定回應 `InitialStoryView` 還是 `ActiveStoryView`，並設定 `ephemeral=True`。

- **`ui/views.py` (互動視圖)**
    -   `class InitialStoryView(discord.ui.View)`: 用於故事開始前的準備工作。
        -   **元件**: 世界選擇選單、創建世界按鈕、創建角色按鈕、開始故事按鈕。
        -   **邏輯**: 按鈕會觸發對應的 Modal，或呼叫 `manager` 中的方法。
    -   `class ActiveStoryView(discord.ui.View)`: 用於管理正在進行中的故事。
        -   **元件**: 加入故事按鈕、暫停/恢復按鈕、結束故事按鈕。
        -   **邏輯**: 直接與 `manager` 互動，管理故事實例的狀態。

- **`ui/modals.py` (資料輸入)**
    -   `class WorldCreateModal(discord.ui.Modal)`:
        -   **用途**: 透過表單收集新世界觀的名稱和背景故事。
        -   **提交後**: 呼叫 `story_manager.create_world()` 並在成功後通知使用者或更新 View。
    -   `class CharacterCreateModal(discord.ui.Modal)`:
        -   **用途**: 透過表單收集新角色的名稱和描述。
        -   **提交後**: 呼叫 `story_manager.create_character()`。

## 5. 資料與邏輯調整
- **`manager.py`**: 核心方法（如 `create_world`）將進行微調，以接受 `interaction` 物件作為參數，從而能在操作完成後直接與 UI 互動（如更新訊息、發送確認）。
- **`models.py`**: 資料模型保持不變，但業務邏輯層將確保所有資料（世界、角色）都透過 `StoryInstance` 與 `channel_id` 進行關聯，以實現頻道級別的管理。