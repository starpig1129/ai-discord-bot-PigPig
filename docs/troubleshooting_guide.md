# Qwen3 模型遷移故障排除指南

本指南提供 Qwen3 模型遷移過程中常見問題的診斷和解決方案。

## 目錄

1. [常見錯誤與解決方案](#常見錯誤與解決方案)
2. [系統診斷工具](#系統診斷工具)
3. [日誌分析](#日誌分析)
4. [效能問題](#效能問題)
5. [資料完整性問題](#資料完整性問題)
6. [緊急恢復程序](#緊急恢復程序)

## 常見錯誤與解決方案

### 1. 記憶體相關錯誤

#### OutOfMemoryError
```
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
```

**原因**: GPU 記憶體不足

**解決方案**:
```bash
# 方案 1: 減少批次大小
python migrate_to_qwen3.py --migrate --batch-size=10

# 方案 2: 啟用 CPU 模式
# 編輯 settings.json
{
  "memory_system": {
    "cpu_only_mode": true
  }
}

# 方案 3: 增加 GPU 記憶體限制
{
  "memory_system": {
    "hardware_detection": {
      "gpu_memory_limit_mb": 1024,
      "fallback_to_cpu": true
    }
  }
}
```

#### MemoryError: Unable to allocate array
```
MemoryError: Unable to allocate 4.00 GiB for an array
```

**原因**: 系統 RAM 不足

**解決方案**:
```bash
# 關閉其他程序釋放記憶體
sudo systemctl stop unnecessary-services

# 使用較小批次大小
python migrate_to_qwen3.py --migrate --batch-size=5

# 增加虛擬記憶體 (Linux)
sudo swapon --show
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 2. 模型載入錯誤

#### 模型下載失敗
```
OSError: Can't load tokenizer for 'Qwen/Qwen3-Embedding-0.6B'
```

**解決方案**:
```bash
# 方案 1: 手動下載模型
python -c "
from transformers import AutoTokenizer, AutoModel
import os
os.environ['HF_HOME'] = './data/memory/models'
tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen3-Embedding-0.6B')
model = AutoModel.from_pretrained('Qwen/Qwen3-Embedding-0.6B')
print('模型下載完成')
"

# 方案 2: 使用鏡像站點
export HF_ENDPOINT=https://hf-mirror.com
python migrate_to_qwen3.py --migrate

# 方案 3: 離線模式（需要預先下載的模型）
{
  "memory_system": {
    "embedding_model": "./data/memory/models/Qwen3-Embedding-0.6B"
  }
}
```

#### 模型版本不相容
```
ValueError: Model version mismatch
```

**解決方案**:
```bash
# 清理快取
rm -rf ~/.cache/huggingface/
rm -rf ./data/memory/models/

# 重新下載最新版本
python migrate_to_qwen3.py --migrate
```

### 3. 資料庫錯誤

#### 資料庫鎖定
```
sqlite3.OperationalError: database is locked
```

**解決方案**:
```bash
# 檢查是否有程序在使用資料庫
lsof data/memory/memory.db

# 終止相關程序
pkill -f "python.*memory"

# 檢查資料庫完整性
sqlite3 data/memory/memory.db "PRAGMA integrity_check;"

# 如果資料庫損壞，從備份恢復
cp data/memory/memory.db.backup data/memory/memory.db
```

#### 資料庫架構錯誤
```
sqlite3.OperationalError: no such table: embeddings
```

**解決方案**:
```python
# 重新初始化資料庫
from cogs.memory.database import DatabaseManager

db_manager = DatabaseManager("data/memory/memory.db")
# 資料庫將自動重建表格
```

### 4. 配置檔案錯誤

#### JSON 格式錯誤
```
json.JSONDecodeError: Expecting ',' delimiter
```

**解決方案**:
```bash
# 驗證 JSON 格式
python -m json.tool settings.json

# 使用範例配置
cp settings_qwen3_example.json settings.json

# 或重新生成配置
python migrate_to_qwen3.py --migrate  # 會自動創建有效配置
```

#### 配置參數錯誤
```
ConfigurationError: Invalid configuration parameter
```

**解決方案**:
```bash
# 檢查配置檔案
python -c "
from cogs.memory.config import MemoryConfig
try:
    config = MemoryConfig('settings.json')
    print('配置檔案有效')
except Exception as e:
    print(f'配置錯誤: {e}')
"

# 恢復預設配置
{
  "memory_system": {
    "enabled": true,
    "auto_detection": true,
    "profile": "qwen3_medium_performance"
  }
}
```

### 5. 向量遷移錯誤

#### 維度不匹配
```
VectorOperationError: Vector dimension mismatch: expected 1536, got 768
```

**解決方案**:
```bash
# 使用 regenerate 策略（推薦）
python migrate_to_qwen3.py --migrate --strategy=regenerate

# 或使用轉換策略
python migrate_to_qwen3.py --migrate --strategy=transform
```

#### 遷移進度停止
```
INFO - 遷移進度: 45.2% (stuck)
```

**解決方案**:
```bash
# 檢查系統資源
htop
nvidia-smi  # 如果有 GPU

# 重新啟動遷移（會從中斷點繼續）
python migrate_to_qwen3.py --migrate --batch-size=25

# 檢查日誌
tail -f logs/qwen3_migration_*.log
```

### 6. 依賴套件問題

#### PyTorch 版本不相容
```
ImportError: cannot import name 'xxx' from 'torch'
```

**解決方案**:
```bash
# 更新 PyTorch
pip install --upgrade torch torchvision torchaudio

# 或安裝特定版本
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu118
```

#### Transformers 版本過舊
```
AttributeError: module 'transformers' has no attribute 'AutoModel'
```

**解決方案**:
```bash
# 更新 transformers
pip install --upgrade transformers>=4.30.0

# 檢查版本
python -c "import transformers; print(transformers.__version__)"
```

## 系統診斷工具

### 完整系統診斷腳本

```python
#!/usr/bin/env python3
"""系統診斷腳本"""

import json
import logging
import sqlite3
import sys
from pathlib import Path

def diagnose_system():
    """執行完整系統診斷"""
    print("🔍 開始系統診斷...")
    
    issues = []
    
    # 1. 檢查配置檔案
    config_file = Path("settings.json")
    if not config_file.exists():
        issues.append("❌ settings.json 不存在")
    else:
        try:
            with open(config_file, "r") as f:
                json.load(f)
            print("✅ 配置檔案格式正確")
        except json.JSONDecodeError as e:
            issues.append(f"❌ 配置檔案 JSON 格式錯誤: {e}")
    
    # 2. 檢查資料庫
    db_file = Path("data/memory/memory.db")
    if not db_file.exists():
        print("⚠️ 資料庫不存在（首次運行時正常）")
    else:
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
            count = cursor.fetchone()[0]
            print(f"✅ 資料庫可訪問，包含 {count} 個向量")
            conn.close()
        except Exception as e:
            issues.append(f"❌ 資料庫錯誤: {e}")
    
    # 3. 檢查依賴套件
    dependencies = {
        "torch": "PyTorch",
        "transformers": "Transformers",
        "sentence_transformers": "SentenceTransformers",
        "faiss": "FAISS",
        "sklearn": "Scikit-learn"
    }
    
    for pkg, name in dependencies.items():
        try:
            __import__(pkg)
            print(f"✅ {name} 已安裝")
        except ImportError:
            issues.append(f"❌ {name} 未安裝")
    
    # 4. 檢查 GPU
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU 可用: {gpu_name} (共 {gpu_count} 個)")
        else:
            print("⚠️ GPU 不可用，將使用 CPU 模式")
    except:
        issues.append("❌ PyTorch GPU 檢測失敗")
    
    # 5. 檢查記憶體
    try:
        import psutil
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        total_gb = memory.total / (1024**3)
        print(f"✅ 記憶體: {available_gb:.1f}GB 可用 / {total_gb:.1f}GB 總量")
        
        if available_gb < 4:
            issues.append("⚠️ 可用記憶體不足 4GB")
    except:
        issues.append("❌ 記憶體檢測失敗")
    
    # 總結
    print("\n" + "="*50)
    if issues:
        print("發現以下問題:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("✅ 系統檢查通過，可以進行遷移")
    
    return len(issues) == 0

if __name__ == "__main__":
    success = diagnose_system()
    sys.exit(0 if success else 1)
```

### 記憶體使用監控

```python
#!/usr/bin/env python3
"""記憶體使用監控腳本"""

import psutil
import time
import torch

def monitor_memory(duration=60):
    """監控記憶體使用"""
    print(f"監控記憶體使用 {duration} 秒...")
    
    for i in range(duration):
        # 系統記憶體
        memory = psutil.virtual_memory()
        used_gb = (memory.total - memory.available) / (1024**3)
        total_gb = memory.total / (1024**3)
        
        # GPU 記憶體
        gpu_info = ""
        if torch.cuda.is_available():
            gpu_used = torch.cuda.memory_allocated() / (1024**3)
            gpu_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            gpu_info = f", GPU: {gpu_used:.1f}GB/{gpu_total:.1f}GB"
        
        print(f"\r記憶體使用: {used_gb:.1f}GB/{total_gb:.1f}GB{gpu_info}", end="")
        time.sleep(1)
    
    print("\n監控完成")

if __name__ == "__main__":
    monitor_memory()
```

## 日誌分析

### 常見日誌模式

#### 正常遷移日誌
```
2025-07-06 01:00:00 - INFO - 開始向量遷移: paraphrase-multilingual-mpnet-base-v2 -> Qwen/Qwen3-Embedding-0.6B
2025-07-06 01:00:01 - INFO - 維度變化: 768 -> 1536
2025-07-06 01:00:02 - INFO - 總向量數: 15420
2025-07-06 01:00:03 - INFO - 遷移策略: regenerate
2025-07-06 01:05:30 - INFO - 遷移進度: 50.0%
2025-07-06 01:10:45 - INFO - 向量遷移完成: 成功 15420/15420, 成功率 100.00%
```

#### 記憶體不足日誌
```
2025-07-06 01:00:00 - ERROR - 批次遷移失敗 (offset=1000): CUDA out of memory
2025-07-06 01:00:01 - WARNING - GPU 記憶體不足，切換到 CPU 模式
2025-07-06 01:00:02 - INFO - 繼續使用 CPU 進行遷移...
```

#### 模型載入失敗日誌
```
2025-07-06 01:00:00 - ERROR - 模型載入失敗: Can't load tokenizer
2025-07-06 01:00:01 - INFO - 嘗試從快取載入模型...
2025-07-06 01:00:02 - INFO - 開始下載模型檔案...
```

### 日誌分析腳本

```bash
#!/bin/bash
# 日誌分析腳本

LOG_FILE="logs/qwen3_migration_$(date +%Y%m%d)*.log"

echo "=== 遷移進度分析 ==="
grep "遷移進度" $LOG_FILE | tail -10

echo -e "\n=== 錯誤訊息 ==="
grep -i "error\|failed\|exception" $LOG_FILE | tail -5

echo -e "\n=== 警告訊息 ==="
grep -i "warning\|warn" $LOG_FILE | tail -5

echo -e "\n=== 效能統計 ==="
grep -E "成功率|耗時|throughput" $LOG_FILE | tail -3
```

## 效能問題

### 遷移速度過慢

**症狀**: 遷移速度 < 100 向量/分鐘

**診斷步驟**:
```bash
# 1. 檢查系統資源
htop
iotop
nvidia-smi

# 2. 檢查批次大小
grep "batch_size" settings.json

# 3. 檢查 I/O 使用率
iostat -x 1
```

**解決方案**:
```json
{
  "memory_system": {
    "performance": {
      "batch_size": 32,
      "max_concurrent_queries": 16
    },
    "migration": {
      "migration_batch_size": 50
    }
  }
}
```

### 記憶體洩漏

**症狀**: 記憶體使用持續增長

**診斷腳本**:
```python
import gc
import psutil
import time

def check_memory_leak():
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    for i in range(10):
        # 模擬一些操作
        time.sleep(30)
        gc.collect()
        
        current_memory = process.memory_info().rss / 1024 / 1024
        growth = current_memory - initial_memory
        
        print(f"週期 {i+1}: {current_memory:.1f}MB (+{growth:.1f}MB)")
        
        if growth > 500:  # 500MB 增長視為可能的記憶體洩漏
            print("⚠️ 檢測到可能的記憶體洩漏")
            break
```

## 資料完整性問題

### 向量數量不匹配

**診斷查詢**:
```sql
-- 檢查不同模型的向量數量
SELECT model_version, COUNT(*) as count, AVG(dimension) as avg_dim
FROM embeddings 
GROUP BY model_version;

-- 檢查是否有重複向量
SELECT message_id, COUNT(*) as count
FROM embeddings 
GROUP BY message_id 
HAVING COUNT(*) > 1;

-- 檢查向量維度一致性
SELECT DISTINCT dimension, COUNT(*) 
FROM embeddings 
GROUP BY dimension;
```

### 資料一致性驗證腳本

```python
#!/usr/bin/env python3
"""資料一致性驗證腳本"""

import sqlite3
from pathlib import Path

def verify_data_consistency():
    """驗證資料一致性"""
    db_path = Path("data/memory/memory.db")
    if not db_path.exists():
        print("❌ 資料庫不存在")
        return False
    
    issues = []
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 1. 檢查孤立向量
        cursor.execute("""
            SELECT COUNT(*) FROM embeddings e 
            LEFT JOIN messages m ON e.message_id = m.message_id 
            WHERE m.message_id IS NULL
        """)
        orphaned_vectors = cursor.fetchone()[0]
        if orphaned_vectors > 0:
            issues.append(f"發現 {orphaned_vectors} 個孤立向量")
        
        # 2. 檢查缺失向量
        cursor.execute("""
            SELECT COUNT(*) FROM messages m 
            LEFT JOIN embeddings e ON m.message_id = e.message_id 
            WHERE e.message_id IS NULL
        """)
        missing_vectors = cursor.fetchone()[0]
        if missing_vectors > 0:
            issues.append(f"發現 {missing_vectors} 個缺失向量")
        
        # 3. 檢查維度一致性
        cursor.execute("""
            SELECT model_version, dimension, COUNT(*) 
            FROM embeddings 
            GROUP BY model_version, dimension
        """)
        dimension_info = cursor.fetchall()
        
        print("維度分佈:")
        for model, dim, count in dimension_info:
            print(f"  {model}: {dim}維 ({count} 個)")
        
        conn.close()
        
        if issues:
            print("發現資料一致性問題:")
            for issue in issues:
                print(f"  ❌ {issue}")
            return False
        else:
            print("✅ 資料一致性檢查通過")
            return True
            
    except Exception as e:
        print(f"❌ 資料一致性檢查失敗: {e}")
        return False

if __name__ == "__main__":
    verify_data_consistency()
```

## 緊急恢復程序

### 快速回滾

```bash
#!/bin/bash
# 緊急回滾腳本

echo "🚨 執行緊急回滾..."

# 1. 停止所有相關程序
pkill -f "python.*memory"
pkill -f "migrate_to_qwen3"

# 2. 恢復配置檔案
if [ -f "settings.json.backup" ]; then
    cp settings.json.backup settings.json
    echo "✅ 配置檔案已恢復"
fi

# 3. 恢復資料庫
if [ -f "data/memory/memory.db.backup" ]; then
    cp data/memory/memory.db.backup data/memory/memory.db
    echo "✅ 資料庫已恢復"
fi

# 4. 恢復向量索引
if [ -d "data/memory/vectors.backup" ]; then
    rm -rf data/memory/vectors
    cp -r data/memory/vectors.backup data/memory/vectors
    echo "✅ 向量索引已恢復"
fi

echo "🎉 緊急回滾完成"
```

### 系統重置

```bash
#!/bin/bash
# 系統重置腳本（謹慎使用）

read -p "⚠️ 這將清除所有遷移資料，確定要繼續嗎？(y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "操作已取消"
    exit 1
fi

echo "🔄 開始系統重置..."

# 停止所有程序
pkill -f "python.*memory"

# 清理模型快取
rm -rf ~/.cache/huggingface/
rm -rf ./data/memory/models/

# 重置資料庫
rm -f data/memory/memory.db
rm -rf data/memory/vectors/

# 重置配置
if [ -f "settings_qwen3_example.json" ]; then
    cp settings_qwen3_example.json settings.json
fi

echo "✅ 系統重置完成，可以重新開始遷移"
```

### 聯絡支援

如果問題無法解決，請收集以下資訊並尋求技術支援：

1. **系統資訊**:
   ```bash
   uname -a
   python --version
   pip list | grep -E "(torch|transformers|sentence-transformers)"
   ```

2. **錯誤日誌**:
   ```bash
   tail -50 logs/qwen3_migration_*.log
   ```

3. **配置檔案**:
   ```bash
   cat settings.json
   ```

4. **系統資源**:
   ```bash
   free -h
   df -h
   nvidia-smi  # 如果有 GPU
   ```

---

*如有其他問題，請參考項目 README 或提交 GitHub Issue*