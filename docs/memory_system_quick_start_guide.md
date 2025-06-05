# 記憶系統快速使用指南

[← 返回主文檔](../README_zh-TW.md#記憶系統配置)

## 🚀 快速開始

### 1. 啟用記憶系統
在 `settings.json` 中設定：
```json
{
  "memory_system": {
    "enabled": true,
    "auto_detection": true,
    "vector_enabled": true
  }
}
```

### 2. 啟動 Bot
```bash
python main.py
```

記憶系統會自動：
- 檢測硬體規格
- 選擇最佳配置檔案
- 初始化向量搜尋引擎
- 開始自動儲存對話

## 💬 使用 Discord 指令

### 搜尋記憶
```
/memory-search query:Python 程式設計 search_type:hybrid limit:5
```

### 查看統計
```
/memory-stats
```

### 查看配置
```
/memory-config
```

### 清除記憶 (管理員)
```
/memory-clear confirm:CONFIRM
```

## 🧠 智能對話體驗

### 自動記憶增強
當您與 Bot 對話時，系統會：

1. **自動儲存對話** - 所有訊息都被記錄到記憶系統
2. **智能檢索** - 根據當前對話內容搜尋相關歷史
3. **上下文增強** - 將相關記憶融入 GPT 回應中
4. **個性化回應** - 基於歷史互動提供更準確的答案

### 範例對話
```
用戶: "@Bot 我們之前討論的 Python 專案進展如何？"

Bot: "根據我們上週的討論，你正在開發一個網路爬蟲專案。
     你當時提到遇到了反爬蟲機制的問題。現在進展如何？
     需要我提供更多關於處理 JavaScript 渲染頁面的建議嗎？"
```

## ⚙️ 配置選項

### 自動硬體偵測
系統會自動選擇最適合的配置：

- **高效能模式** (8GB+ RAM, GPU)
  - 啟用完整向量搜尋
  - 使用高精度嵌入模型
  - 最佳搜尋品質

- **中等效能模式** (4GB+ RAM)
  - 平衡效能與品質
  - 適中的嵌入維度
  - 推薦配置

- **低效能模式** (2GB+ RAM)
  - 關鍵字搜尋為主
  - 最小資源使用
  - 基本功能保證

### 手動配置
在 `settings.json` 中自訂：

```json
{
  "memory_system": {
    "enabled": true,
    "vector_enabled": true,
    "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "database_path": "data/memory/memory.db",
    "search_settings": {
      "default_search_type": "hybrid",
      "semantic_threshold": 0.7,
      "max_context_messages": 5
    },
    "cache": {
      "enabled": true,
      "max_size_mb": 512,
      "ttl_seconds": 3600
    }
  }
}
```

## 🔧 進階功能

### 搜尋類型
- **語義搜尋** (`semantic`) - 理解意思，找相關內容
- **關鍵字搜尋** (`keyword`) - 精確匹配關鍵字
- **混合搜尋** (`hybrid`) - 結合語義和關鍵字 (推薦)
- **時間搜尋** (`temporal`) - 基於時間範圍搜尋

### 頻道管理
```json
{
  "memory_system": {
    "channel_settings": {
      "default_enabled": true,
      "whitelist_channels": ["123456789"],
      "blacklist_channels": ["987654321"]
    }
  }
}
```

### 效能監控
- 查詢時間統計
- 快取命中率監控
- 記憶體使用追蹤
- 慢查詢日誌

## 🎯 最佳實務

### 1. 合理設定快取
```json
{
  "cache": {
    "enabled": true,
    "max_size_mb": 512,  // 根據可用記憶體調整
    "ttl_seconds": 3600  // 1小時快取過期
  }
}
```

### 2. 定期清理舊資料
```json
{
  "index_optimization": {
    "enabled": true,
    "cleanup_old_data_days": 90  // 90天後清理
  }
}
```

### 3. 監控效能
```json
{
  "monitoring": {
    "enable_metrics": true,
    "log_slow_queries": true,
    "slow_query_threshold_ms": 1000
  }
}
```

## 🔍 故障排除

### 記憶系統無法啟動
1. 檢查 `settings.json` 中 `enabled: true`
2. 確認資料庫路徑有寫入權限
3. 檢查日誌中的錯誤訊息

### 搜尋結果不準確
1. 調整 `semantic_threshold` (0.5-0.9)
2. 增加 `max_context_messages`
3. 嘗試不同的 `search_type`

### 效能問題
1. 啟用快取 `cache.enabled: true`
2. 降低 `embedding_dimension`
3. 使用 `cpu_only_mode: true` 如果 GPU 記憶體不足

### 記憶體使用過高
1. 減少 `cache.max_size_mb`
2. 啟用 `cleanup_old_data`
3. 降低 `batch_size`

## 📊 效能基準

### 典型效能指標
- **訊息儲存**: < 50ms
- **關鍵字搜尋**: < 100ms
- **語義搜尋**: < 300ms
- **混合搜尋**: < 200ms
- **快取命中率**: > 80% (穩定運行後)

### 硬體建議
- **最低配置**: 2GB RAM, 2 CPU 核心
- **推薦配置**: 4GB RAM, 4 CPU 核心
- **最佳體驗**: 8GB+ RAM, GPU 支援

## 🛡️ 安全性

### 資料保護
- 本地資料庫儲存
- 自動備份機制
- 敏感資訊過濾

### 權限控制
- 管理員限定的清除功能
- 頻道白名單/黑名單
- 用戶權限驗證

## 📈 未來功能

- [ ] 跨伺服器記憶共享
- [ ] 多模態記憶 (圖片、檔案)
- [ ] 高級分析報告
- [ ] API 外部接口
- [ ] 機器學習優化

---

## 🆘 取得幫助

如果遇到問題：
1. 查看日誌檔案中的詳細錯誤
2. 執行 `/memory-stats` 檢查系統狀態
3. 查看 [記憶系統架構文檔](discord_bot_memory_system_architecture.md) 了解技術細節

**享受更智能的 Discord Bot 體驗！** 🎉

[← 返回主文檔](../README_zh-TW.md#記憶系統配置)