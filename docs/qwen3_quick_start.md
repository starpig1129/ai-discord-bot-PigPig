# Qwen3 模型遷移快速開始指南

本指南提供最簡化的 Qwen3 模型遷移步驟，讓您能快速完成遷移。

## 5 分鐘快速遷移

### 步驟 1: 環境檢查 (1 分鐘)

```bash
# 檢查 Python 和依賴
python --version  # 需要 Python 3.8+
pip install --upgrade transformers torch sentence-transformers

# 檢查系統狀態
python migrate_to_qwen3.py --check-only
```

### 步驟 2: 備份資料 (1 分鐘)

```bash
# 快速備份
cp settings.json settings.json.backup
cp data/memory/memory.db data/memory/memory.db.backup 2>/dev/null || echo "資料庫不存在，跳過備份"
```

### 步驟 3: 執行遷移 (2-3 分鐘)

```bash
# 自動遷移（推薦）
python migrate_to_qwen3.py --migrate

# 或指定配置
python migrate_to_qwen3.py --migrate --profile=qwen3_medium_performance
```

### 步驟 4: 驗證結果 (30 秒)

```bash
# 驗證遷移
python migrate_to_qwen3.py --verify

# 測試功能
python test_qwen3_integration.py
```

## 常見配置選擇

### 8GB RAM + 無 GPU
```bash
python migrate_to_qwen3.py --migrate --profile=qwen3_medium_performance --batch-size=16
```

### 16GB RAM + GPU
```bash
python migrate_to_qwen3.py --migrate --profile=qwen3_high_performance --batch-size=32
```

### 大型資料集 (>50,000 向量)
```bash
python migrate_to_qwen3.py --migrate --strategy=regenerate --batch-size=25
```

## 如果遇到問題

### 記憶體不足
```bash
# 減少批次大小
python migrate_to_qwen3.py --migrate --batch-size=8
```

### 模型下載失敗
```bash
# 使用鏡像
export HF_ENDPOINT=https://hf-mirror.com
python migrate_to_qwen3.py --migrate
```

### 回滾遷移
```bash
# 自動回滾到最新備份
python rollback_migration.py --latest
```

## 遷移後建議

1. **測試功能**: 確認搜尋和對話功能正常
2. **監控效能**: 觀察記憶體和響應時間
3. **定期備份**: 建立定期備份機制

## 需要幫助？

- 📖 詳細指南: [`docs/qwen3_migration_guide.md`](qwen3_migration_guide.md)
- 🔧 故障排除: [`docs/troubleshooting_guide.md`](troubleshooting_guide.md)
- ⚙️ 硬體配置: [`docs/hardware_configuration_guide.md`](hardware_configuration_guide.md)

---

*大多數用戶只需要執行 `python migrate_to_qwen3.py --migrate` 即可完成遷移！*