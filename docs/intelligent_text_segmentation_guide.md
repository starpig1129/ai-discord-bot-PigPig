# 智慧文本分割系統使用指南

## 概述

智慧文本分割系統是 Discord 記憶體系統的進階功能，能夠自動將對話分割成有意義的片段。系統結合了時間間隔、語義相似性和對話活躍度等多個因素，提供智慧化的對話管理。

## 核心功能

### 1. 多策略分割

- **時間策略 (TIME_ONLY)**: 僅基於時間間隔分割
- **語義策略 (SEMANTIC_ONLY)**: 僅基於語義相似性分割
- **混合策略 (HYBRID)**: 結合時間和語義因素（推薦）
- **自適應策略 (ADAPTIVE)**: 根據對話活躍度動態調整

### 2. 動態時間間隔

系統會根據頻道活躍度動態調整分割間隔：

- **高活躍度**: 較短的分割間隔，避免長片段
- **低活躍度**: 較長的分割間隔，避免短片段
- **可配置範圍**: 最小 5 分鐘到最大 120 分鐘

### 3. 語義相似性分析

使用 Qwen3-Embedding 模型分析對話主題變化：

- **相似度閾值**: 可調整的語義相似性門檻
- **主題偵測**: 自動識別對話主題轉換
- **連貫性評分**: 計算片段內語義連貫性

### 4. 活躍度感知

系統監控對話活躍度指標：

- **訊息頻率**: 每小時訊息數量
- **參與用戶**: 獨特用戶數量
- **回應速度**: 平均回應時間
- **峰值活動**: 最高活動時段

## 配置說明

### 基本配置

```json
{
  "memory_system": {
    "text_segmentation": {
      "enabled": true,
      "strategy": "hybrid"
    }
  }
}
```

### 進階配置

```json
{
  "memory_system": {
    "text_segmentation": {
      "enabled": true,
      "strategy": "hybrid",
      "dynamic_interval": {
        "min_minutes": 5,
        "max_minutes": 120,
        "base_minutes": 30,
        "activity_multiplier": 0.2
      },
      "semantic_threshold": {
        "similarity_cutoff": 0.6,
        "min_messages_per_segment": 3,
        "max_messages_per_segment": 50
      },
      "processing": {
        "batch_size": 20,
        "async_processing": true,
        "background_segmentation": true
      },
      "quality_control": {
        "coherence_threshold": 0.5,
        "merge_small_segments": true,
        "split_large_segments": true
      }
    }
  }
}
```

## 參數詳解

### 動態間隔設定

| 參數 | 說明 | 預設值 | 範圍 |
|------|------|--------|------|
| `min_minutes` | 最小分割間隔（分鐘） | 5 | 1-60 |
| `max_minutes` | 最大分割間隔（分鐘） | 120 | 60-480 |
| `base_minutes` | 基礎分割間隔（分鐘） | 30 | 5-120 |
| `activity_multiplier` | 活躍度調整係數 | 0.2 | 0.1-1.0 |

### 語義閾值設定

| 參數 | 說明 | 預設值 | 範圍 |
|------|------|--------|------|
| `similarity_cutoff` | 語義相似性閾值 | 0.6 | 0.3-0.9 |
| `min_messages_per_segment` | 片段最小訊息數 | 3 | 1-10 |
| `max_messages_per_segment` | 片段最大訊息數 | 50 | 10-200 |

### 處理設定

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `batch_size` | 批次處理大小 | 20 |
| `async_processing` | 啟用非同步處理 | true |
| `background_segmentation` | 背景分割處理 | true |

### 品質控制

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `coherence_threshold` | 連貫性閾值 | 0.5 |
| `merge_small_segments` | 合併小片段 | true |
| `split_large_segments` | 分割大片段 | true |

## 使用方法

### 1. 初始化系統

```python
from cogs.memory.memory_manager import MemoryManager

# 初始化記憶管理器
manager = MemoryManager("settings_qwen3_example.json")
await manager.initialize()
```

### 2. 儲存訊息

```python
# 系統會自動進行分割處理
await manager.store_message(discord_message)
```

### 3. 查詢片段

```python
# 取得指定時間範圍的片段
segments = await manager.segmentation_service.get_segments_for_timerange(
    channel_id="123456789",
    start_time=datetime.now() - timedelta(hours=1),
    end_time=datetime.now()
)

for segment in segments:
    print(f"片段 ID: {segment.segment_id}")
    print(f"訊息數量: {segment.message_count}")
    print(f"連貫性分數: {segment.semantic_coherence_score}")
    print(f"持續時間: {segment.duration_minutes} 分鐘")
```

### 4. 分析片段品質

```python
# 檢查片段連貫性
coherence_score = await manager.segmentation_service._calculate_segment_coherence(segment)

# 取得片段代表性文本
representative_text = await manager.segmentation_service._get_segment_representative_text(segment)
```

## 性能調優

### 1. 記憶體優化

- **CPU 模式**: 設定 `cpu_only_mode: true`
- **批次大小**: 根據可用記憶體調整 `batch_size`
- **快取設定**: 適當配置快取大小和 TTL

### 2. 處理速度優化

- **背景處理**: 啟用 `background_segmentation`
- **非同步處理**: 啟用 `async_processing`
- **併發限制**: 調整 `max_concurrent_queries`

### 3. 分割品質優化

- **語義閾值**: 根據語言特性調整 `similarity_cutoff`
- **片段大小**: 平衡 `min_messages_per_segment` 和 `max_messages_per_segment`
- **活躍度係數**: 根據頻道特性調整 `activity_multiplier`

## 監控與除錯

### 1. 日誌監控

系統會記錄詳細的分割過程日誌：

```
INFO - 完成對話片段: seg_123456789_1234567890_abcd1234，訊息數: 5，持續時間: 12.3分鐘
DEBUG - 語義相似性: 0.85，時間間隔: 8.5分鐘，決策: 繼續片段
WARNING - 片段過大（25條訊息），觸發強制分割
```

### 2. 統計資訊

```python
# 取得分割統計
stats = await manager.get_segmentation_stats()
print(f"總片段數: {stats.total_segments}")
print(f"平均片段大小: {stats.average_segment_size}")
print(f"平均連貫性: {stats.average_coherence}")
```

### 3. 資料庫查詢

```sql
-- 查詢所有片段
SELECT segment_id, start_time, end_time, message_count, semantic_coherence_score
FROM conversation_segments
WHERE channel_id = ?
ORDER BY start_time DESC;

-- 查詢片段訊息
SELECT m.content, sm.position_in_segment
FROM segment_messages sm
JOIN messages m ON sm.message_id = m.message_id
WHERE sm.segment_id = ?
ORDER BY sm.position_in_segment;
```

## 故障排除

### 常見問題

1. **分割過於頻繁**
   - 調高 `similarity_cutoff`
   - 增加 `min_interval_minutes`
   - 檢查 `activity_multiplier` 設定

2. **分割不夠頻繁**
   - 調低 `similarity_cutoff`
   - 減少 `max_interval_minutes`
   - 啟用 `split_large_segments`

3. **性能問題**
   - 啟用 `background_segmentation`
   - 調整 `batch_size`
   - 檢查 GPU/CPU 使用率

4. **語義分析不準確**
   - 檢查嵌入模型載入狀態
   - 調整 `coherence_threshold`
   - 驗證文本預處理邏輯

### 除錯模式

啟用除錯日誌：

```json
{
  "logging": {
    "level": "DEBUG"
  }
}
```

## 最佳實踐

1. **漸進式調整**: 從預設配置開始，逐步調整參數
2. **測試驗證**: 使用測試腳本驗證分割效果
3. **監控觀察**: 定期檢查分割品質和性能指標
4. **備份資料**: 定期備份分割結果和配置
5. **版本控制**: 記錄配置變更歷史

## 進階功能

### 1. 自訂分割策略

```python
# 實作自訂分割邏輯
class CustomSegmentationStrategy:
    async def should_segment(self, context):
        # 自訂分割邏輯
        return custom_decision
```

### 2. 片段後處理

```python
# 自訂片段後處理
async def custom_post_process(segment):
    # 生成自訂摘要
    # 計算額外指標
    # 發送通知
    pass
```

### 3. 整合外部 API

```python
# 整合外部語意分析服務
async def external_semantic_analysis(text):
    # 呼叫外部 API
    # 處理回應
    return analysis_result
```

## 結論

智慧文本分割系統為 Discord 記憶體系統提供了強大的對話管理能力。通過適當的配置和調優，能夠有效提升對話檢索的準確性和效率。建議根據實際使用場景調整相關參數，並持續監控系統性能。