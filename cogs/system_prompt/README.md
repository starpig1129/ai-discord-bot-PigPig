# 頻道系統提示管理模組

## 📋 概覽

頻道系統提示管理模組提供完整的系統提示自訂功能，支援三層繼承機制（全域 → 伺服器 → 頻道），與現有 Discord 機器人系統深度整合。

## 🏗️ 架構

### 模組結構
```
cogs/system_prompt/
├── __init__.py          # 模組初始化
├── manager.py           # 核心 SystemPromptManager 類別
├── commands.py          # Discord 斜線命令
├── ui.py               # Discord UI 元件
├── permissions.py       # 權限管理
├── exceptions.py        # 自訂例外類別
└── README.md           # 此文件
```

### 核心組件

#### SystemPromptManager
- 三層繼承機制管理
- 智慧快取系統
- YAML 提示整合
- 多語言支援

#### PermissionValidator
- 多層權限控制
- 角色與用戶權限
- 動態權限檢查

#### SystemPromptCommands
- 完整的斜線命令介面
- Modal 對話框支援
- 確認與選擇 UI

## 🚀 使用方法

### 1. 載入模組

在 `bot.py` 中添加：

```python
# 載入系統提示管理模組
await bot.load_extension('cogs.system_prompt_manager')
```

### 2. Discord 命令

#### 設定系統提示
```
/system_prompt set type:頻道特定 channel:#技術討論
/system_prompt set type:伺服器預設
```

#### 查看系統提示
```
/system_prompt view channel:#技術討論 show_inherited:True
```

#### 移除系統提示
```
/system_prompt remove type:頻道特定 channel:#技術討論
/system_prompt remove type:伺服器預設
```

#### 複製系統提示
```
/system_prompt copy from_channel:#技術討論 to_channel:#程式設計
```

#### 重置系統提示
```
/system_prompt reset type:當前頻道
/system_prompt reset type:伺服器預設
/system_prompt reset type:全部重置
```

#### 查看可用模組
```
/system_prompt modules
```

### 3. 權限設定

#### 權限層級
1. **機器人擁有者** - 完整權限
2. **伺服器管理員** - 管理所有系統提示
3. **頻道管理員** - 管理對應頻道
4. **自訂角色** - 設定的特定權限

#### 配置權限
在伺服器配置中設定：

```json
{
  "system_prompts": {
    "permissions": {
      "allowed_roles": ["角色ID1", "角色ID2"],
      "allowed_users": ["用戶ID1"],
      "manage_server_prompts": ["管理員角色ID"]
    }
  }
}
```

## 🔧 配置格式

### 完整配置範例
```json
{
  "mode": "unrestricted",
  "whitelist": [],
  "blacklist": [],
  "auto_response": {},
  "system_prompts": {
    "enabled": true,
    "server_level": {
      "prompt": "伺服器級別的系統提示",
      "modules": {
        "personality": "專業助手",
        "interaction_style": "正式語調"
      },
      "created_by": "用戶ID",
      "created_at": "2025-01-04T12:00:00Z",
      "updated_at": "2025-01-04T12:00:00Z"
    },
    "channels": {
      "頻道ID": {
        "enabled": true,
        "prompt": "頻道特定的系統提示",
        "modules": {
          "personality": "技術專家"
        },
        "override_modules": ["personality"],
        "append_content": "額外的指令",
        "created_by": "用戶ID",
        "created_at": "2025-01-04T12:30:00Z",
        "updated_at": "2025-01-04T12:30:00Z"
      }
    },
    "permissions": {
      "allowed_roles": ["角色ID"],
      "allowed_users": ["用戶ID"],
      "manage_server_prompts": ["管理員角色ID"]
    }
  }
}
```

## 🔄 三層繼承機制

### 繼承順序
1. **YAML 基礎提示** - 全域預設
2. **伺服器級別提示** - 覆蓋或擴展基礎提示
3. **頻道級別提示** - 最終的頻道特定提示

### 模組覆蓋
- 可以選擇性覆蓋特定模組
- 支援追加內容
- 保持其他模組不變

## 🛡️ 安全性

### 內容驗證
- 最大長度限制：4000 字元
- 危險模式檢測
- XSS 防護

### 權限控制
- 分層權限管理
- 動態權限檢查
- 審計追蹤

## ⚡ 效能

### 快取策略
- 智慧快取系統
- TTL 控制（預設 1 小時）
- 自動快取失效

### 最佳化
- 延遲載入
- 異步處理
- 記憶體效率

## 🌐 多語言支援

### 支援語言
- 繁體中文 (zh_TW)
- 簡體中文 (zh_CN)
- 英文 (en_US)
- 日文 (ja_JP)

### 語言本地化
自動根據伺服器語言設定調整系統提示內容。

## 🔌 整合

### 與現有系統整合
- 無縫整合現有 YAML 提示系統
- 完全向後相容
- 不影響現有功能

### API 介面
```python
# 取得系統提示管理器
manager = bot.get_cog('SystemPromptManagerCog').get_system_prompt_manager()

# 取得有效提示
prompt_data = manager.get_effective_prompt(channel_id, guild_id)

# 權限檢查
validator = bot.get_cog('SystemPromptManagerCog').get_permission_validator()
can_edit = validator.can_modify_channel_prompt(user, channel)
```

## 📊 監控

### 狀態命令
```
!system_prompt_status        # 查看模組狀態
!system_prompt_clear_cache   # 清除快取
```

### 日誌記錄
- 操作審計
- 錯誤追蹤
- 效能監控

## 🚨 錯誤處理

### 自訂例外
- `SystemPromptError` - 基礎錯誤
- `PermissionError` - 權限錯誤
- `ValidationError` - 驗證錯誤
- `ConfigurationError` - 配置錯誤

### 錯誤回復
- 優雅降級
- 自動重試
- 用戶友好提示

## 📚 開發指南

### 擴展功能
1. 繼承相應的基類
2. 實作所需的方法
3. 註冊到管理器

### 測試
```python
# 單元測試範例
from cogs.system_prompt.manager import SystemPromptManager

def test_system_prompt_manager():
    manager = SystemPromptManager(bot)
    # 測試邏輯...
```

## 🔮 未來規劃

### 計劃功能
- 模板系統
- 版本控制
- 匯入/匯出功能
- 統計分析
- Web 管理介面

### 效能最佳化
- 分散式快取
- 資料庫後端
- 批量操作

## 📄 授權

MIT License - 請參考專案根目錄的 LICENSE 檔案。

## 👥 貢獻

歡迎提交 Issue 和 Pull Request 來改善這個模組。

---

**注意：** 此模組需要 Discord.py 2.0+ 和 Python 3.8+