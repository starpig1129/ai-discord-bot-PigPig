# Qwen3 模型硬體配置建議指南

本指南提供針對不同硬體環境的 Qwen3 模型最佳配置建議，幫助您根據實際硬體情況選擇最適合的設定。

## 目錄

1. [硬體需求概覽](#硬體需求概覽)
2. [配置檔案詳解](#配置檔案詳解)
3. [記憶體最佳化](#記憶體最佳化)
4. [GPU 配置指南](#gpu-配置指南)
5. [CPU 最佳化](#cpu-最佳化)
6. [效能調校建議](#效能調校建議)

## 硬體需求概覽

### 最低系統需求

| 組件 | 最低需求 | 推薦配置 | 最佳配置 |
|------|----------|----------|----------|
| **RAM** | 8GB | 16GB | 32GB+ |
| **CPU** | 4核心 | 8核心 | 16核心+ |
| **GPU** | 不必需 | 6GB VRAM | 12GB+ VRAM |
| **儲存** | 10GB 可用空間 | 50GB SSD | 100GB+ NVMe |

### 不同規模的建議配置

#### 小型部署（<10,000 向量）
```json
{
  "memory_system": {
    "profile": "qwen3_medium_performance",
    "cpu_only_mode": false,
    "memory_threshold_mb": 3072,
    "performance": {
      "batch_size": 16,
      "max_concurrent_queries": 8
    }
  }
}
```

#### 中型部署（10,000-100,000 向量）
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

#### 大型部署（>100,000 向量）
```json
{
  "memory_system": {
    "profile": "qwen3_high_performance",
    "cpu_only_mode": false,
    "memory_threshold_mb": 12288,
    "performance": {
      "batch_size": 64,
      "max_concurrent_queries": 32
    },
    "hardware_detection": {
      "gpu_memory_limit_mb": 8192,
      "gpu_temp_memory_mb": 2048
    }
  }
}
```

## 配置檔案詳解

### qwen3_medium_performance
**適用環境**: 8-16GB RAM，可選 GPU
```json
{
  "memory_system": {
    "profile": "qwen3_medium_performance",
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_dimension": 1536,
    "cpu_only_mode": false,
    "memory_threshold_mb": 4096,
    "cache": {
      "enabled": true,
      "max_size_mb": 1024,
      "ttl_seconds": 3600
    },
    "performance": {
      "batch_size": 32,
      "max_concurrent_queries": 12,
      "query_timeout_seconds": 30
    },
    "hardware_detection": {
      "gpu_memory_limit_mb": 2048,
      "gpu_temp_memory_mb": 512,
      "fallback_to_cpu": true
    }
  }
}
```

### qwen3_high_performance
**適用環境**: 16GB+ RAM，推薦 GPU
```json
{
  "memory_system": {
    "profile": "qwen3_high_performance",
    "embedding_model": "Qwen/Qwen3-Embedding-0.6B",
    "embedding_dimension": 1536,
    "cpu_only_mode": false,
    "memory_threshold_mb": 6144,
    "cache": {
      "enabled": true,
      "max_size_mb": 1536,
      "ttl_seconds": 7200
    },
    "performance": {
      "batch_size": 64,
      "max_concurrent_queries": 20,
      "query_timeout_seconds": 45
    },
    "hardware_detection": {
      "gpu_memory_limit_mb": 3072,
      "gpu_temp_memory_mb": 768,
      "fallback_to_cpu": false
    }
  }
}
```

## 記憶體最佳化

### RAM 使用策略

#### 8GB RAM 系統
```json
{
  "memory_system": {
    "memory_threshold_mb": 3072,
    "cache": {
      "max_size_mb": 512
    },
    "performance": {
      "batch_size": 16,
      "max_concurrent_queries": 6
    }
  }
}
```

#### 16GB RAM 系統
```json
{
  "memory_system": {
    "memory_threshold_mb": 6144,
    "cache": {
      "max_size_mb": 1024
    },
    "performance": {
      "batch_size": 32,
      "max_concurrent_queries": 12
    }
  }
}
```

#### 32GB+ RAM 系統
```json
{
  "memory_system": {
    "memory_threshold_mb": 12288,
    "cache": {
      "max_size_mb": 2048
    },
    "performance": {
      "batch_size": 64,
      "max_concurrent_queries": 24
    }
  }
}
```

### 記憶體監控配置

```json
{
  "memory_system": {
    "hardware_detection": {
      "memory_monitoring": true,
      "memory_warning_threshold": 0.8,
      "memory_critical_threshold": 0.9,
      "auto_cleanup_on_high_usage": true
    }
  }
}
```

## GPU 配置指南

### NVIDIA GPU 最佳化

#### RTX 3060 (12GB)
```json
{
  "memory_system": {
    "hardware_detection": {
      "gpu_memory_limit_mb": 8192,
      "gpu_temp_memory_mb": 1024,
      "gpu_utilization_threshold": 0.85
    },
    "performance": {
      "batch_size": 32,
      "gpu_batch_multiplier": 2
    }
  }
}
```

#### RTX 4090 (24GB)
```json
{
  "memory_system": {
    "hardware_detection": {
      "gpu_memory_limit_mb": 16384,
      "gpu_temp_memory_mb": 2048,
      "gpu_utilization_threshold": 0.9
    },
    "performance": {
      "batch_size": 64,
      "gpu_batch_multiplier": 4
    }
  }
}
```

#### GTX 1660 Ti (6GB)
```json
{
  "memory_system": {
    "hardware_detection": {
      "gpu_memory_limit_mb": 4096,
      "gpu_temp_memory_mb": 512,
      "fallback_to_cpu": true
    },
    "performance": {
      "batch_size": 16,
      "gpu_batch_multiplier": 1
    }
  }
}
```

### AMD GPU 配置

```json
{
  "memory_system": {
    "hardware_detection": {
      "gpu_vendor": "amd",
      "rocm_enabled": true,
      "gpu_memory_limit_mb": 6144,
      "fallback_to_cpu": true
    }
  }
}
```

### Apple Silicon 配置

```json
{
  "memory_system": {
    "hardware_detection": {
      "mps_enabled": true,
      "unified_memory": true,
      "memory_allocation_strategy": "unified"
    },
    "performance": {
      "batch_size": 32,
      "use_metal_performance_shaders": true
    }
  }
}
```

## CPU 最佳化

### 多核心系統配置

#### 4-8 核心
```json
{
  "memory_system": {
    "performance": {
      "cpu_threads": 4,
      "parallel_processing": true,
      "thread_pool_size": 6
    }
  }
}
```

#### 8-16 核心
```json
{
  "memory_system": {
    "performance": {
      "cpu_threads": 8,
      "parallel_processing": true,
      "thread_pool_size": 12
    }
  }
}
```

#### 16+ 核心
```json
{
  "memory_system": {
    "performance": {
      "cpu_threads": 12,
      "parallel_processing": true,
      "thread_pool_size": 20
    }
  }
}
```

### CPU 特定最佳化

#### Intel CPU
```json
{
  "memory_system": {
    "cpu_optimizations": {
      "use_mkl": true,
      "intel_extension": true,
      "avx_optimization": true
    }
  }
}
```

#### AMD CPU
```json
{
  "memory_system": {
    "cpu_optimizations": {
      "use_blas": true,
      "amd_optimization": true,
      "zen_architecture": true
    }
  }
}
```

## 效能調校建議

### 批次大小調校

根據硬體資源動態調整批次大小：

```python
# 自動批次大小計算
def calculate_optimal_batch_size(ram_gb, gpu_memory_gb=0):
    base_batch_size = 16
    
    # 根據 RAM 調整
    if ram_gb >= 32:
        ram_multiplier = 4
    elif ram_gb >= 16:
        ram_multiplier = 2
    else:
        ram_multiplier = 1
    
    # 根據 GPU 記憶體調整
    if gpu_memory_gb >= 12:
        gpu_multiplier = 2
    elif gpu_memory_gb >= 6:
        gpu_multiplier = 1.5
    else:
        gpu_multiplier = 1
    
    return int(base_batch_size * ram_multiplier * gpu_multiplier)
```

### 快取策略調校

```json
{
  "memory_system": {
    "cache": {
      "strategy": "adaptive",
      "lru_cache_size": 1000,
      "bloom_filter_enabled": true,
      "compression_enabled": true,
      "cache_warming": {
        "enabled": true,
        "preload_common_queries": true
      }
    }
  }
}
```

### 並行處理調校

```json
{
  "memory_system": {
    "performance": {
      "async_processing": true,
      "worker_pool_size": "auto",
      "queue_management": {
        "max_queue_size": 1000,
        "priority_scheduling": true
      }
    }
  }
}
```

### I/O 最佳化

```json
{
  "memory_system": {
    "io_optimization": {
      "database_cache_size": "256MB",
      "journal_mode": "WAL",
      "synchronous": "NORMAL",
      "temp_store": "MEMORY"
    }
  }
}
```

## 常見配置範例

### 開發環境
```json
{
  "memory_system": {
    "profile": "qwen3_medium_performance",
    "cpu_only_mode": false,
    "memory_threshold_mb": 2048,
    "performance": {
      "batch_size": 8,
      "max_concurrent_queries": 4
    },
    "logging": {
      "level": "DEBUG",
      "performance_monitoring": true
    }
  }
}
```

### 生產環境
```json
{
  "memory_system": {
    "profile": "qwen3_high_performance",
    "cpu_only_mode": false,
    "memory_threshold_mb": 8192,
    "performance": {
      "batch_size": 64,
      "max_concurrent_queries": 32
    },
    "reliability": {
      "error_recovery": true,
      "auto_restart_on_failure": true,
      "health_check_interval": 300
    }
  }
}
```

### 邊緣設備
```json
{
  "memory_system": {
    "profile": "qwen3_medium_performance",
    "cpu_only_mode": true,
    "memory_threshold_mb": 1024,
    "performance": {
      "batch_size": 4,
      "max_concurrent_queries": 2
    },
    "optimization": {
      "model_quantization": true,
      "inference_acceleration": true
    }
  }
}
```

## 效能基準測試

### 測試腳本

```python
#!/usr/bin/env python3
"""硬體效能基準測試腳本"""

import time
import psutil
import torch
from cogs.memory.embedding_service import embedding_service_manager
from cogs.memory.config import MemoryConfig

def run_performance_test():
    """執行效能測試"""
    config = MemoryConfig()
    profile = config.get_current_profile()
    service = embedding_service_manager.get_service(profile)
    
    # 測試資料
    test_texts = [f"測試句子 {i}" for i in range(1000)]
    
    # 記憶體使用監控
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    # GPU 記憶體監控
    if torch.cuda.is_available():
        initial_gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
    
    # 執行測試
    start_time = time.time()
    embeddings = service.encode_batch(test_texts)
    end_time = time.time()
    
    # 計算效能指標
    duration = end_time - start_time
    throughput = len(test_texts) / duration
    final_memory = process.memory_info().rss / 1024 / 1024
    memory_usage = final_memory - initial_memory
    
    if torch.cuda.is_available():
        final_gpu_memory = torch.cuda.memory_allocated() / 1024 / 1024
        gpu_memory_usage = final_gpu_memory - initial_gpu_memory
    else:
        gpu_memory_usage = 0
    
    # 輸出結果
    print(f"效能測試結果:")
    print(f"  處理文本數: {len(test_texts)}")
    print(f"  總耗時: {duration:.2f} 秒")
    print(f"  吞吐量: {throughput:.1f} 文本/秒")
    print(f"  記憶體使用: {memory_usage:.1f} MB")
    print(f"  GPU 記憶體使用: {gpu_memory_usage:.1f} MB")
    print(f"  向量維度: {embeddings.shape[1]}")

if __name__ == "__main__":
    run_performance_test()
```

## 故障排除

### 記憶體不足

**症狀**: `OutOfMemoryError`, `CUDA out of memory`

**解決方案**:
1. 減少批次大小
2. 降低快取大小
3. 啟用 CPU 回退模式

### GPU 不可用

**症狀**: `CUDA not available`, GPU 檢測失敗

**解決方案**:
1. 檢查 GPU 驅動程式
2. 驗證 CUDA/ROCm 安裝
3. 啟用 CPU 模式

### 效能低下

**症狀**: 處理速度過慢

**解決方案**:
1. 增加批次大小
2. 啟用並行處理
3. 檢查系統資源使用率

---

*本指南將根據社群回饋和硬體發展持續更新*