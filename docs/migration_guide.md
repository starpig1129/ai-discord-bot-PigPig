# 對話歷史資料轉移指南

本指南說明如何將舊版的對話歷史資料轉移到新的記憶系統中。

## 概述

轉移工具支援將各種格式的舊版對話資料轉換為新記憶系統的標準格式，包括：

- JSON 對話歷史檔案
- SQLite 資料庫
- CSV 匯出檔案
- 其他自定義格式

## 快速開始

### 1. 檢查資料格式

首先確認您的對話歷史檔案格式。系統支援以下格式：

**標準對話格式**（如 `data/dialogue_history.json`）：
```json
{
  "channel_id_1": [
    {
      "role": "user",
      "content": "使用者訊息"
    },
    {
      "role": "assistant", 
      "content": "AI 回應"
    }
  ],
  "channel_id_2": [...]
}
```

### 2. 執行預覽轉移

建議先執行乾運行來預覽轉移結果：

```bash
python migrate_dialogue_history.py --dry-run --verbose
```

### 3. 執行實際轉移

確認預覽結果正確後，執行實際轉移：

```bash
python migrate_dialogue_history.py --backup
```

## 命令列選項

### 基本選項

- `--dry-run`: 預覽模式，不實際執行轉移
- `--backup`: 轉移前建立現有資料的備份
- `--verbose`: 顯示詳細的日誌輸出

### 進階選項

- `--source-file PATH`: 指定要轉移的來源檔案（預設：`data/dialogue_history.json`）
- `--config PATH`: 指定記憶系統配置檔案路徑

### 使用範例

```bash
# 預覽轉移 dialogue_history.json
python migrate_dialogue_history.py --dry-run

# 執行完整轉移並建立備份
python migrate_dialogue_history.py --backup --verbose

# 轉移指定檔案
python migrate_dialogue_history.py --source-file custom_data.json --backup

# 使用自定義配置
python migrate_dialogue_history.py --config custom_config.json
```

## 資料格式轉換

### 輸入格式

系統自動識別以下輸入格式：

1. **頻道對話格式**：
   ```json
   {
     "1234567890": [
       {"role": "user", "content": "訊息內容"},
       {"role": "assistant", "content": "回應內容"}
     ]
   }
   ```

2. **標準訊息格式**：
   ```json
   [
     {
       "message_id": "123",
       "channel_id": "456", 
       "content": "訊息內容",
       "timestamp": "2023-01-01T00:00:00Z"
     }
   ]
   ```

3. **SQLite 資料庫**：
   - 自動掃描包含訊息的表格
   - 支援常見的欄位名稱映射

### 輸出格式

所有資料都會轉換為新記憶系統的標準格式：

```json
{
  "message_id": "unique_id",
  "channel_id": "channel_id", 
  "user_id": "user_id",
  "content": "訊息內容",
  "message_type": "user|bot|system",
  "timestamp": "2023-01-01T00:00:00+00:00",
  "metadata": {
    "migration_source": "dialogue_history",
    "original_data": {...},
    "migration_timestamp": "2023-01-01T00:00:00"
  }
}
```

## 性能優化

### 硬體需求

- **RAM**: 建議至少 8GB，大型資料集需要 16GB+
- **CPU**: 多核心處理器提升轉換速度
- **GPU**: 支援 CUDA 的 GPU 加速向量計算
- **磁碟**: SSD 提升 I/O 性能

### 批次處理

系統自動進行批次處理以優化性能：

- 大型檔案分批讀取，避免記憶體溢出
- 並行處理多個轉換任務
- 智慧快取減少重複計算

### 性能監控

轉移過程中會顯示實時性能指標：

```
進度: 85.2% (102,450/120,801) 已用時間: 45.3s
  - 已完成來源: 1/1
  - 目前處理: dialogue_history.json
  - 處理速度: 2,260 記錄/秒
```

## 錯誤處理

### 常見錯誤

1. **檔案格式錯誤**
   ```
   ❌ 錯誤: JSON 格式錯誤 - Expecting ',' delimiter
   ```
   - 解決方案：檢查 JSON 檔案語法是否正確

2. **記憶體不足**
   ```
   ❌ 錯誤: 記憶體不足，無法載入大型檔案
   ```
   - 解決方案：增加系統記憶體或分割檔案

3. **權限問題**
   ```
   ❌ 錯誤: 無法寫入資料庫檔案
   ```
   - 解決方案：檢查檔案權限或以管理員身份執行

### 資料驗證

轉移完成後會自動執行驗證：

- 記錄數量一致性檢查
- 資料庫完整性驗證
- 向量索引正確性檢查

## 備份與恢復

### 自動備份

使用 `--backup` 選項會自動建立備份：

```
✅ 已建立資料備份: data/backups/memory_migration/memory_backup_20231201_143022.db
```

### 手動備份

也可以手動備份重要檔案：

```bash
# 備份記憶資料庫
cp data/memory/memory.db data/memory/memory.db.backup

# 備份向量索引
cp -r data/memory/vectors data/memory/vectors.backup
```

### 恢復資料

如果轉移出現問題，可以恢復備份：

```bash
# 恢復資料庫
mv data/memory/memory.db.backup data/memory/memory.db

# 恢復向量索引
rm -rf data/memory/vectors
mv data/memory/vectors.backup data/memory/vectors
```

## 疑難排解

### 日誌檔案

詳細的轉移日誌記錄在 `migration.log` 中：

```bash
# 查看最新日誌
tail -f migration.log

# 搜尋錯誤訊息
grep "ERROR" migration.log
```

### 除錯模式

啟用詳細日誌來診斷問題：

```bash
python migrate_dialogue_history.py --dry-run --verbose
```

### 支援與回報

如遇到問題，請提供以下資訊：

1. 錯誤訊息的完整輸出
2. 系統硬體規格
3. 資料檔案的大小和格式
4. `migration.log` 的相關片段

## 最佳實踐

### 轉移前準備

1. **資料備份**：務必備份原始資料
2. **系統檢查**：確認系統資源充足
3. **預覽測試**：先執行乾運行模式
4. **分段轉移**：大型資料集考慮分批處理

### 轉移後檢查

1. **資料完整性**：檢查記錄數量是否正確
2. **功能測試**：測試搜尋和檢索功能
3. **性能驗證**：確認系統響應速度正常
4. **清理工作**：移除臨時檔案和舊備份

### 維護建議

1. **定期備份**：建立定期備份機制
2. **監控性能**：關注系統性能指標
3. **更新維護**：定期更新系統組件
4. **文檔記錄**：記錄轉移過程和自定義配置

---

## 版本歷史

- **v1.0.0** (2023-12-01): 初始版本，支援基本對話歷史轉移
- 支援多種輸入格式自動識別
- 高效能批次處理機制
- 完整的錯誤處理和驗證系統