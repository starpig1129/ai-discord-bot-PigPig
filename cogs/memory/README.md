# Discord Bot 永久頻道記憶系統

## 概述

這是 Discord LLM Bot 的永久頻道記憶系統第一階段實作，提供基於 SQLite + FAISS 混合架構的高效記憶存儲和檢索功能。

## 功能特色

### ✅ 已實作功能 (第一階段)

- **智能硬體檢測**: 自動檢測系統硬體規格並推薦最適配置
- **SQLite 資料庫**: 完整的資料庫 Schema 設計和 CRUD 操作
- **配置管理系統**: 支援多種效能配置檔案的自動和手動選擇
- **基礎記憶管理**: 訊息存儲、基本搜尋和上下文檢索
- **執行緒安全**: 支援多執行緒並發操作
- **錯誤處理**: 完整的例外處理和日誌記錄

### ✅ 第二階段完成功能

- **FAISS 向量搜尋**: 語義搜尋和相似性檢索
- **嵌入模型整合**: Sentence Transformers 多語言支援
- **智能搜尋引擎**: 語義搜尋、快取系統和效能優化
- **向量索引管理**: 頻道級別的向量索引和批次處理

### 🚧 計劃實作功能 (後續階段)

- **混合搜尋引擎**: 結合關鍵字、語義和時間篩選
- **使用者偏好學習**: 個人化搜尋結果排序
- **分散式存儲**: 大規模部署的向量分片
- **效能監控**: 即時性能指標和自動調優

## 系統架構

### 模組結構

```
cogs/memory/
├── __init__.py              # 模組初始化
├── memory_manager.py        # 核心記憶管理器
├── database.py              # 資料庫操作類別
├── config.py                # 配置管理和硬體檢測
├── embedding_service.py     # 嵌入模型服務
├── vector_manager.py        # FAISS 向量索引管理
├── search_engine.py         # 語義搜尋引擎
├── exceptions.py            # 自定義例外類別
├── test_memory_system.py    # 基礎功能測試
├── test_vector_search.py    # 向量搜尋測試
└── README.md               # 使用文檔
```

### 硬體配置檔案

系統會自動檢測硬體並選擇適合的配置檔案：

| 配置檔案 | 最低需求 | GPU | 向量搜尋 | 快取大小 | 適用場景 |
|---------|---------|-----|---------|---------|---------|
| `high_performance` | 8GB RAM | 需要 | 啟用 | 1GB | 高效能伺服器 |
| `medium_performance` | 4GB RAM | 不需要 | 啟用 | 512MB | 一般電腦 |
| `low_performance` | 2GB RAM | 不需要 | 停用 | 256MB | 低配置環境 |

## 使用方法

### 1. 配置設定

在 `settings.json` 中添加記憶系統配置：

```json
{
  "memory_system": {
    "enabled": true,
    "auto_detection": true,
    "vector_enabled": true,
    "database_path": "data/memory/memory.db",
    "performance": {
      "max_concurrent_queries": 10,
      "query_timeout_seconds": 30,
      "batch_size": 50
    }
  }
}
```

### 2. 初始化記憶系統

```python
from cogs.memory import MemoryManager

# 初始化記憶管理器
memory_manager = MemoryManager("settings.json")
await memory_manager.initialize()

# 初始化頻道記憶
await memory_manager.initialize_channel(channel_id, guild_id)
```

### 3. 儲存訊息

```python
# 儲存 Discord 訊息
success = await memory_manager.store_message(discord_message)
```

### 4. 搜尋記憶

```python
from cogs.memory import SearchQuery, SearchType

# 建立搜尋查詢
query = SearchQuery(
    text="關鍵字搜尋",
    channel_id="123456789",
    search_type=SearchType.KEYWORD,
    limit=10
)

# 執行搜尋
result = await memory_manager.search_memory(query)
print(f"找到 {result.total_found} 條相關訊息")
```

### 5. 取得頻道上下文

```python
# 取得最近的頻道訊息
context = await memory_manager.get_context(channel_id, limit=50)
```

## 資料庫設計

### 主要資料表

#### channels 表
- `channel_id` (主鍵): 頻道 ID
- `guild_id`: 伺服器 ID  
- `created_at`: 建立時間
- `last_active`: 最後活動時間
- `message_count`: 訊息數量
- `vector_enabled`: 是否啟用向量搜尋
- `config_profile`: 配置檔案名稱

#### messages 表
- `message_id` (主鍵): 訊息 ID
- `channel_id` (外鍵): 頻道 ID
- `user_id`: 使用者 ID
- `content`: 訊息內容
- `content_processed`: 處理後內容
- `timestamp`: 時間戳記
- `message_type`: 訊息類型
- `relevance_score`: 相關性分數

#### embeddings 表 (預留)
- `embedding_id` (主鍵): 嵌入向量 ID
- `message_id` (外鍵): 訊息 ID
- `vector_data`: 向量資料
- `model_version`: 模型版本
- `dimension`: 向量維度

## 測試

執行基礎功能測試：

```bash
python test_memory_basic.py
```

測試項目：
- ✅ 硬體檢測
- ✅ 資料庫結構建立
- ✅ 資料庫 CRUD 操作  
- ✅ 配置系統
- ✅ 配置檔案載入

## 效能指標

當前第一階段測試結果：
- 硬體檢測: 125.5 GB RAM, 32 CPU 核心, 24 GB GPU
- 推薦配置: `high_performance`
- 資料庫: 5 個資料表, 11 個索引
- 所有基礎功能測試通過

## 錯誤處理

系統定義了完整的例外類別：

- `MemorySystemError`: 記憶系統基礎例外
- `DatabaseError`: 資料庫操作錯誤
- `ConfigurationError`: 配置相關錯誤
- `HardwareIncompatibleError`: 硬體不相容錯誤
- `VectorOperationError`: 向量操作錯誤
- `SearchError`: 搜尋操作錯誤

每個例外都包含詳細的錯誤訊息和上下文資訊。

## 日誌記錄

系統使用 Python logging 模組記錄重要事件：

```python
import logging
logging.basicConfig(level=logging.INFO)

# 記憶系統會自動記錄：
# - 初始化過程
# - 硬體檢測結果
# - 資料庫操作
# - 搜尋查詢
# - 錯誤和警告
```

## 相容性

- **Python**: 3.8+
- **作業系統**: Linux, Windows, macOS
- **資料庫**: SQLite 3.x
- **依賴**: 見 `requirements.txt`

## 接下來的發展

### 第二階段：向量搜尋實作
- FAISS 向量存儲整合
- 多語言嵌入模型支援
- 語義搜尋功能

### 第三階段：混合搜尋系統  
- 全文搜尋引擎 (FTS5)
- 時間範圍篩選
- 智能搜尋結果合併

### 第四階段：效能優化
- 多層快取架構
- 即時性能監控
- 自動調優機制

## 貢獻

歡迎提交 Issue 和 Pull Request 來改進記憶系統！

## 授權

MIT License