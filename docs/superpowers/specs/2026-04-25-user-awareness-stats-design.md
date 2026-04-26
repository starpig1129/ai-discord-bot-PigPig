# 使用者感知與統計互動功能設計

**日期：** 2026-04-25  
**狀態：** 已確認，待實作

## Context

目前 PigPig bot 的 LLM agent 缺乏對以下資訊的感知能力：
1. Discord 伺服器結構（身份組、頻道清單、boost 等級等）
2. 使用者在伺服器中的具體資訊（加入時間、身份組、暱稱）
3. 累積性的使用者行為統計（發言次數、活躍時段、常用詞語）

目標是讓機器人能**自主判斷**何時需要這些資訊並取用，讓對話更個人化、更有情境感，並能以文字或圖片名片方式呈現使用者統計。

現有資產可利用：
- 大量已存在的 NDJSON log 檔（`logs/{guild_id}/{YYYYMMDD}/info.jsonl`），每筆記錄含 `user_id`、`channel_or_file`、`timestamp`、`action`、`message`
- 現有 SQLite DB（`cogs/memory/db/`）可直接新增表格
- 工具自動發現機制（`llm/tools_factory.py`）支援新增工具模組

---

## 架構概覽

```
新增 DB 表
  user_stats           ← on_message 即時更新（新訊息）
  log_migration_state  ← 背景 log 解析進度追蹤（歷史遷移）

新增 Cog
  cogs/stats_cog.py    ← on_message 監聽 + 背景 log 遷移排程

新增 Tools (llm/tools/)
  server_context.py    ← 3 個工具：查伺服器/頻道/使用者 Discord 資訊
  user_stats.py        ← 2 個工具：文字統計卡（給 AI）/ 圖片統計卡（給使用者）

新增依賴
  jieba                ← 中文斷詞（分析 top_words）
  wordcloud            ← 生成文字雲圖片
```

---

## 一、DB Schema

修改檔案：`cogs/memory/db/schema.py`

新增兩個 SQLite 表：

```sql
-- 使用者累積統計（跨伺服器獨立計算）
CREATE TABLE IF NOT EXISTS user_stats (
    user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    total_messages INTEGER NOT NULL DEFAULT 0,
    active_hours TEXT NOT NULL DEFAULT '{}',
        -- JSON 物件，key 為小時數 (0-23)，value 為訊息數
        -- 例：{"14": 45, "22": 30, "0": 12}
    top_channels TEXT NOT NULL DEFAULT '{}',
        -- JSON 物件，key 為頻道名稱，value 為訊息數
    top_emojis TEXT NOT NULL DEFAULT '{}',
        -- JSON 物件，key 為 emoji 字元，value 為出現次數
    top_words TEXT NOT NULL DEFAULT '{}',
        -- JSON 物件，key 為詞語，value 為出現次數（jieba 斷詞）
    streak_days INTEGER NOT NULL DEFAULT 0,
        -- 當前連續活躍天數
    streak_last_date TEXT,
        -- "YYYY-MM-DD" 格式，用於計算連續天數
    last_active_at DATETIME,
    first_message_at DATETIME,
    PRIMARY KEY (user_id, guild_id)
);

-- Log 遷移進度追蹤（防止重複處理）
CREATE TABLE IF NOT EXISTS log_migration_state (
    guild_id TEXT PRIMARY KEY,
    last_processed_date TEXT NOT NULL
        -- "YYYYMMDD" 格式，例 "20260424"
);
```

---

## 二、新增 Cog：`cogs/stats_cog.py`

**職責：**
1. `on_message` 事件監聽：每收到新訊息即時更新 `user_stats`
2. 啟動時排程背景 log 遷移任務（處理歷史資料）

**StatsStorage 類別**（內嵌在 cog 或獨立於 `cogs/memory/db/stats_storage.py`）：
- `get_user_stats(user_id, guild_id)` → dict
- `update_user_stats(user_id, guild_id, message_content, channel_name, timestamp)` → None
  - 更新 `total_messages + 1`
  - 更新 `active_hours[hour] + 1`
  - 更新 `top_channels[channel_name] + 1`
  - 解析 emoji 並更新 `top_emojis`
  - 使用 jieba 斷詞後更新 `top_words`（過濾停用詞，最多保留前 200 個詞）
  - 計算並更新 `streak_days`
  - 更新 `last_active_at`，若為空則同時設定 `first_message_at`
- `get_migration_state(guild_id)` → Optional[str]（last_processed_date）
- `set_migration_state(guild_id, date_str)` → None

**背景 Log 遷移任務：**
```
非同步背景 task（low-priority，每次處理一天）
1. 讀取 logs/ 目錄，找出所有 guild_id 子目錄
2. 對每個 guild：
   a. 讀取 log_migration_state 的 last_processed_date
   b. 找出未處理的日期目錄（按日期升序排列）
   c. 對每個日期：
      - 開啟 info.jsonl
      - 逐行讀取，篩選 action == "receive_message"
      - 每 500 筆呼叫一次 update_user_stats（批次 commit）
      - await asyncio.sleep(0)（讓出 event loop，避免阻塞）
      - 完成後更新 log_migration_state
   d. 每天處理完 sleep(30)，等待後再處理下一天
3. 全部完成後記錄 log，任務結束
```

**效能保護：**
- 讀取 NDJSON 時逐行處理，不一次性載入整個檔案
- 每 500 筆批次 commit，降低寫入次數
- 每天之間 sleep(30)，避免 I/O 競爭
- jieba 斷詞僅處理中文和英文詞，過濾長度 < 2 的詞和純數字

---

## 三、新增 Tools：`llm/tools/server_context.py`

**agent_mode：** `"info"`（給 info_agent 使用，讓 AI 在分析階段取得情境）

**工具清單：**

### 3.1 `get_server_context`
查詢目前 Discord 伺服器的基本資訊。  
- 無參數（從 runtime 取得當前 guild）
- 回傳格式（文字）：
  ```
  伺服器：xxx（ID: 123）
  成員數：245 人
  Boost 等級：Level 2（15 次 boost）
  身份組（10 個）：管理員、VIP、一般成員...
  文字頻道（8 個）：公告、聊天室、音樂...
  ```

### 3.2 `get_channel_context`
查詢指定頻道的詳細資訊。  
- 參數：`channel_name: Optional[str]`（預設為當前頻道）
- 回傳：頻道 topic、分類、目前在線人數（語音頻道則為連接人數）

### 3.3 `get_user_discord_info`
查詢指定成員在伺服器中的 Discord 資料。  
- 參數：`user_id: Optional[str]`（預設為訊息發送者）
- 回傳：加入伺服器時間、擁有的身份組、伺服器暱稱、當前活動狀態

---

## 四、新增 Tools：`llm/tools/user_stats.py`

**agent_mode：** `"info"`（給 info_agent 使用）

### 4.1 `get_user_stats_card`
給 AI 使用的文字格式統計卡，AI 可自然嵌入對話回覆中。  
- 參數：`user_id: Optional[str]`（預設為訊息發送者）
- 回傳格式（文字）：
  ```
  📊 xxx 的統計
  ────────────
  總發言數：1,247 則
  最活躍時段：晚上 10-11 點（342 則）
  連續活躍：7 天
  最常待的頻道：聊天室（55%）
  高頻詞：哈哈哈、好無語、要死了、OK
  最愛 emoji：😂 × 142、👍 × 98
  第一次發言：2025-12-01（145 天前）
  ```

### 4.2 `get_user_stats_image`
生成含文字雲的 PNG 統計圖片，直接傳送到 Discord 頻道作為附件。  
- 參數：`user_id: Optional[str]`（預設為訊息發送者）
- 使用 `wordcloud` 庫生成文字雲，`Pillow` 組合成完整統計圖片
- 需要中文字型（優先使用系統 NotoSansCJK 或自帶字型備援）
- 圖片內容：
  - 頂部：使用者名稱、頭像縮圖、基本數字（總發言、連續天數）
  - 中間：文字雲（top_words 加權）
  - 底部：最愛 emoji 條、最活躍時段橫條圖
- 回傳：發送成功的確認文字（圖片已作為 `discord.File` 附件傳送）

---

## 五、依賴新增

`requirements.txt` 新增：
```
jieba>=0.42.1
wordcloud>=1.9.3
```

（`Pillow` 已存在，不需重複新增）

---

## 六、修改的現有檔案

| 檔案 | 修改內容 |
|------|---------|
| `cogs/memory/db/schema.py` | 新增 `user_stats` 和 `log_migration_state` 表的建立 SQL |
| `bot.py` | 在 `setup_hook()` 中載入 `stats_cog`（與其他 cog 自動載入相同機制） |
| `requirements.txt` | 新增 jieba、wordcloud |

---

## 七、新增的檔案

| 檔案 | 說明 |
|------|------|
| `cogs/stats_cog.py` | StatsCog：on_message 監聽 + 背景 log 遷移 |
| `cogs/memory/db/stats_storage.py` | StatsStorage：user_stats 和 log_migration_state 的 DB 操作 |
| `llm/tools/server_context.py` | 3 個伺服器/頻道/使用者資訊查詢工具 |
| `llm/tools/user_stats.py` | 2 個統計工具（文字卡 + 圖片卡） |

---

## 八、資料流

```
Discord 訊息 → bot.on_message()
  → StatsCog.on_message()
      → StatsStorage.update_user_stats()  [即時更新]

用戶詢問相關問題 → info_agent
  → get_user_discord_info()               [Discord API 查詢]
  → get_user_stats_card()                 [讀取 user_stats 表]
  → get_server_context()                  [Discord API 查詢]
  結果傳給 message_agent → 生成個人化回覆

用戶要求看統計名片 → info_agent
  → get_user_stats_image()
      → 讀 user_stats
      → jieba 斷詞（已存在 top_words，不需即時斷詞）
      → wordcloud 生成文字雲
      → Pillow 組合圖片
      → message.channel.send(file=discord.File(image))
  → message_agent 回覆「統計圖已傳送」

Bot 啟動 → StatsCog background task
  → 逐天讀取 logs/{guild_id}/{YYYYMMDD}/info.jsonl
  → 篩選 receive_message，批次更新 user_stats
  → 每天間隔 sleep(30)，記錄進度到 log_migration_state
```

---

## 九、驗證方式

1. **單元：** 確認 `StatsStorage.update_user_stats()` 正確更新 JSON 欄位（active_hours、top_channels 等）
2. **整合：** 啟動 bot，發幾條訊息，查 SQLite 確認 `user_stats` 有資料
3. **工具呼叫：** 跟機器人說「看一下我在這個伺服器的發言統計」，確認 AI 自動呼叫 `get_user_stats_card`
4. **圖片生成：** 跟機器人說「幫我生成統計名片」，確認 Discord 頻道收到圖片附件
5. **Log 遷移：** 啟動後確認背景任務在 log 中輸出進度，查 `log_migration_state` 表確認日期更新
6. **伺服器查詢：** 跟機器人說「這個伺服器有幾個人？」，確認 AI 呼叫 `get_server_context`
