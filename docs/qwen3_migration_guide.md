# Qwen3 模型遷移完整指南

本指南提供從舊 embedding 模型到 Qwen3-Embedding-0.6B 和 Qwen3-Reranker-0.6B 的完整遷移解決方案。

## 目錄

1. [概述](#概述)
2. [遷移前準備](#遷移前準備)
3. [硬體需求評估](#硬體需求評估)
4. [遷移策略選擇](#遷移策略選擇)
5. [逐步遷移指南](#逐步遷移指南)
6. [故障排除](#故障排除)
7. [效能調優](#效能調優)
8. [驗證與測試](#驗證與測試)
9. [回滾程序](#回滾程序)

## 概述

### 什麼是 Qwen3 模型？

Qwen3-Embedding-0.6B 是阿里巴巴推出的新一代多語言嵌入模型，相比舊模型具有以下優勢：

- **更高準確性**: 在多語言語義理解任務上表現更優
- **更好的中文支援**: 針對中文語義理解進行特別最佳化
- **統一架構**: 與 Qwen3-Reranker-0.6B 配合使用效果更佳
- **記憶體效率**: 0.6B 參數規模在效能和資源消耗間取得平衡

### 遷移的必要性

如果您目前使用以下模型，建議遷移到 Qwen3：

- `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768維)
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384維)
- 其他較舊的 SentenceTransformers 模型

### 遷移影響

- **向量維度變化**: 從 384/768 維變更為 1536 維
- **模型載入時間**: 首次載入需要下載模型檔案
- **記憶體使用**: GPU 記憶體需求約 2-4GB
- **運算速度**: 可能略慢於小型模型，但準確性顯著提升

## 遷移前準備

### 1. 系統備份

**❗ 重要**: 遷移前務必備份以下檔案：

```bash
# 備份配置檔案
cp settings.json settings.json.backup

# 備份記憶資料庫
cp data/memory/memory.db data/memory/memory.db.backup

# 備份向量索引（如果存在）
cp -r data/memory/vectors data/memory/vectors.backup
```

### 2. 環境檢查

執行系統檢查來評估準備度：

```bash
python migrate_to_qwen3.py --check-only
```

檢查項目包括：
- 硬體規格（RAM、GPU）
- 依賴套件版本
- 現有資料庫狀態
- 配置檔案有效性

### 3. 依賴套件更新

確保以下套件為最新版本：

```bash
pip install --upgrade transformers torch sentence-transformers
pip install --upgrade faiss-cpu  # 或 faiss-gpu（如果有 GPU）
pip install --upgrade scikit-learn psutil
```

**GPU 用戶額外需求**：
```bash
# NVIDIA GPU
pip install faiss-gpu torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Apple Silicon
pip install torch torchvision torchaudio
```

## 硬體需求評估

### 最低需求

| 配置檔案 | RAM | GPU | 推薦使用情境 |
|---------|-----|-----|-------------|
| qwen3_medium_performance | 8GB | 不必需 | 一般使用，平衡效能 |
| qwen3_high_performance | 12GB | 推薦 | 高負載，追求極致效能 |

### 硬體建議

**記憶體配置**：
- **8GB RAM**: 基本配置，適合小型資料集（<10,000 向量）
- **16GB RAM**: 推薦配置，適合中型資料集（10,000-100,000 向量）
- **32GB+ RAM**: 大型資料集（>100,000 向量）

**GPU 建議**：
- **NVIDIA GTX 1660 Ti** (6GB): 入門級加速
- **NVIDIA RTX 3060** (12GB): 推薦配置
- **NVIDIA RTX 4090** (24GB): 最佳效能

**儲存空間**：
- 模型檔案：約 2-3GB
- 向量索引：資料量的 1.5-2 倍
- 備份空間：現有資料的 2 倍

## 遷移策略選擇

### 1. regenerate（重新生成）- 推薦 ⭐

**適用情境**：
- 有原始文本內容
- 追求最佳準確性
- 資料量適中（<100,000 向量）

**優點**：
- 最高準確性
- 完全利用新模型能力
- 資料一致性最佳

**缺點**：
- 耗時最長
- 需要原始文本

**預估時間**：
- 1,000 向量：5-10 分鐘
- 10,000 向量：30-60 分鐘
- 100,000 向量：5-10 小時

### 2. transform（PCA 轉換）

**適用情境**：
- 無原始文本
- 需要快速遷移
- 可接受略低準確性

**優點**：
- 速度較快
- 不需原始文本
- 保持相對關係

**缺點**：
- 準確性損失
- 無法完全利用新模型

### 3. pad（填充）/ truncate（截斷）

**適用情境**：
- 臨時解決方案
- 極大資料集的快速遷移
- 後續計劃重新生成

**優點**：
- 極快速度
- 最小資源消耗

**缺點**：
- 顯著準確性損失
- 不推薦長期使用

## 逐步遷移指南

### 步驟 1: 遷移前檢查

```bash
# 檢查系統狀態
python migrate_to_qwen3.py --check-only --verbose
```

檢查輸出並確認：
- ✅ 硬體資源充足
- ✅ 依賴套件完整
- ✅ 配置檔案有效
- ✅ 資料庫可訪問

### 步驟 2: 乾運行預覽

```bash
# 預覽遷移步驟
python migrate_to_qwen3.py --dry-run --profile=qwen3_medium_performance
```

這會顯示：
- 將執行的步驟
- 預估時間
- 資源需求
- 風險評估

### 步驟 3: 執行遷移

**基本遷移**（推薦新手）：
```bash
python migrate_to_qwen3.py --migrate
```

**進階遷移**（自定義參數）：
```bash
python migrate_to_qwen3.py --migrate \
  --profile=qwen3_high_performance \
  --strategy=regenerate \
  --batch-size=50 \
  --verbose
```

**大型資料集遷移**：
```bash
# 使用較小批次大小減少記憶體使用
python migrate_to_qwen3.py --migrate \
  --strategy=regenerate \
  --batch-size=25 \
  --verbose
```

### 步驟 4: 驗證結果

```bash
# 驗證遷移結果
python migrate_to_qwen3.py --verify
```

### 步驟 5: 測試功能

```bash
# 測試 Qwen3 整合
python test_qwen3_integration.py

# 測試分割功能
python test_segmentation_integration.py
```

## 故障排除

### 常見問題與解決方案

#### 1. 記憶體不足錯誤

**錯誤訊息**：
```
RuntimeError: CUDA out of memory
MemoryError: Unable to allocate array
```

**解決方案**：
```bash
# 減少批次大小
python migrate_to_qwen3.py --migrate --batch-size=10

# 使用 CPU 模式
# 編輯 settings.json，設定 "cpu_only_mode": true
```

#### 2. 模型下載失敗

**錯誤訊息**：
```
OSError: Can't load tokenizer for 'Qwen/Qwen3-Embedding-0.6B'
```

**解決方案**：
```bash
# 手動下載模型
python -c "
from transformers import AutoTokenizer, AutoModel
tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen3-Embedding-0.6B')
model = AutoModel.from_pretrained('Qwen/Qwen3-Embedding-0.6B')
"
```

#### 3. 配置檔案錯誤

**錯誤訊息**：
```
ConfigurationError: 配置檔案 JSON 格式錯誤
```

**解決方案**：
```bash
# 使用範例配置
cp settings_qwen3_example.json settings.json

# 或重新生成配置
python migrate_to_qwen3.py --migrate  # 會自動創建
```

#### 4. 資料庫鎖定

**錯誤訊息**：
```
sqlite3.OperationalError: database is locked
```

**解決方案**：
```bash
# 確保沒有其他程序在使用資料庫
pkill -f "python.*memory"

# 如果問題持續，重啟系統
```

#### 5. 向量維度不匹配

**錯誤訊息**：
```
VectorOperationError: Vector dimension mismatch
```

**解決方案**：
```bash
# 使用 regenerate 策略
python migrate_to_qwen3.py --migrate --strategy=regenerate
```

### 進階故障排除

#### 檢查日誌檔案

```bash
# 查看最新遷移日誌
ls -la logs/qwen3_migration_*.log | tail -1 | awk '{print $9}' | xargs cat

# 搜尋錯誤
grep -i error logs/qwen3_migration_*.log
```

#### 資料庫診斷

```bash
# 檢查資料庫完整性
sqlite3 data/memory/memory.db "PRAGMA integrity_check;"

# 檢查向量統計
sqlite3 data/memory/memory.db "
SELECT model_version, COUNT(*), AVG(dimension) 
FROM embeddings 
GROUP BY model_version;
"
```

## 效能調優

### 配置檔案最佳化

根據您的硬體選擇最適合的配置：

**8GB RAM + 無 GPU**：
```json
{
  "memory_system": {
    "profile": "qwen3_medium_performance",
    "cpu_only_mode": true,
    "memory_threshold_mb": 3072,
    "performance": {
      "batch_size": 16,
      "max_concurrent_queries": 8
    }
  }
}
```

**16GB RAM + GPU**：
```json
{
  "memory_system": {
    "profile": "qwen3_high_performance",
    "cpu_only_mode": false,
    "memory_threshold_mb": 6144,
    "performance": {
      "batch_size": 32,
      "max_concurrent_queries": 16
    }
  }
}
```

### 批次大小調優

根據資料量調整批次大小：

| 向量數量 | 推薦批次大小 | 記憶體使用 |
|---------|-------------|-----------|
| < 1,000 | 100 | 低 |
| 1,000 - 10,000 | 50 | 中 |
| 10,000 - 100,000 | 25 | 高 |
| > 100,000 | 10 | 極高 |

### GPU 記憶體最佳化

```json
{
  "memory_system": {
    "hardware_detection": {
      "gpu_memory_limit_mb": 2048,
      "gpu_temp_memory_mb": 512,
      "fallback_to_cpu": true
    }
  }
}
```

## 驗證與測試

### 自動驗證腳本

```bash
# 完整驗證
python migrate_to_qwen3.py --verify

# Qwen3 模型測試
python test_qwen3_integration.py

# 分割系統測試
python test_segmentation_integration.py
```

### 手動驗證步驟

#### 1. 配置驗證

```python
from cogs.memory.config import MemoryConfig

config = MemoryConfig()
profile = config.get_current_profile()
print(f"模型: {profile.embedding_model}")
print(f"維度: {profile.embedding_dimension}")
```

#### 2. 嵌入服務測試

```python
from cogs.memory.embedding_service import embedding_service_manager
from cogs.memory.config import MemoryConfig

config = MemoryConfig()
profile = config.get_current_profile()
service = embedding_service_manager.get_service(profile)

# 測試編碼
texts = ["測試句子", "Test sentence"]
embeddings = service.encode_batch(texts)
print(f"嵌入形狀: {embeddings.shape}")
```

#### 3. 相似度測試

```python
import numpy as np

# 計算相似度
vec1, vec2 = embeddings[0], embeddings[1]
similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
print(f"相似度: {similarity:.4f}")
```

### 效能基準測試

建立效能基準來評估遷移效果：

```python
import time
from cogs.memory.embedding_service import embedding_service_manager

# 測試文本
test_texts = ["測試文本"] * 100

# 測量編碼速度
start_time = time.time()
embeddings = service.encode_batch(test_texts)
encoding_time = time.time() - start_time

print(f"編碼 {len(test_texts)} 個文本耗時: {encoding_time:.2f}秒")
print(f"平均速度: {len(test_texts)/encoding_time:.1f} 文本/秒")
```

## 回滾程序

如果遷移遇到問題，可以使用以下步驟回滾：

### 自動回滾

```bash
# 使用備份自動回滾
python rollback_migration.py --backup-path=data/backups/qwen3_migration/qwen3_migration_backup_YYYYMMDD_HHMMSS
```

### 手動回滾

#### 1. 恢復配置檔案

```bash
cp settings.json.backup settings.json
```

#### 2. 恢復資料庫

```bash
cp data/memory/memory.db.backup data/memory/memory.db
```

#### 3. 恢復向量索引

```bash
rm -rf data/memory/vectors
cp -r data/memory/vectors.backup data/memory/vectors
```

#### 4. 驗證回滾

```bash
python test_qwen3_integration.py
```

### 部分回滾

如果只需要回滾特定部分：

```bash
# 僅回滾配置
cp settings.json.backup settings.json

# 僅回滾向量（保留新配置）
sqlite3 data/memory/memory.db "DELETE FROM embeddings WHERE model_version LIKE '%Qwen3%';"
```

## 最佳實踐建議

### 遷移前

1. **充分備份**: 務必備份所有重要資料
2. **硬體檢查**: 確認硬體資源充足
3. **測試環境**: 在測試環境先行驗證
4. **時間規劃**: 選擇系統負載較低的時間進行

### 遷移中

1. **監控進度**: 注意記憶體和 CPU 使用率
2. **避免中斷**: 不要在遷移過程中關閉程序
3. **日誌檢查**: 及時查看日誌了解進度
4. **資源管理**: 關閉不必要的其他程序

### 遷移後

1. **功能驗證**: 測試所有相關功能
2. **效能監控**: 觀察系統效能變化
3. **使用者回饋**: 收集使用者體驗回饋
4. **定期維護**: 建立定期備份和維護機制

## 常見問題 FAQ

### Q: 遷移會影響現有的對話歷史嗎？
A: 不會。遷移只更新向量表示，原始對話內容完全保留。

### Q: 可以在不停機的情況下遷移嗎？
A: 建議在系統維護時間進行，雖然理論上支援線上遷移，但可能影響效能。

### Q: 遷移失敗了怎麼辦？
A: 使用自動備份快速回滾，然後檢查日誌找出問題原因。

### Q: 需要重新訓練模型嗎？
A: 不需要。Qwen3 是預訓練模型，可以直接使用。

### Q: 遷移後向量數量會變化嗎？
A: 向量數量不變，但維度從 384/768 變更為 1536。

### Q: 支援增量遷移嗎？
A: 支援。可以分批遷移不同頻道的資料。

---

## 技術支援

如果遇到本指南未涵蓋的問題，請提供以下資訊：

1. **錯誤訊息**: 完整的錯誤輸出
2. **系統資訊**: 硬體規格和作業系統
3. **配置檔案**: settings.json 內容
4. **日誌檔案**: 相關的日誌片段
5. **資料規模**: 向量數量和資料庫大小

**聯絡方式**：
- 查看項目 README.md 獲取支援資訊
- 檢查 GitHub Issues 尋找類似問題
- 提交新的 Issue 描述您的問題

---

*最後更新: 2025年7月6日*