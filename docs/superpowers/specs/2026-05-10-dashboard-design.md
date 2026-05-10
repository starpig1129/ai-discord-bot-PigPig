# PigPig Dashboard 設計文件

**日期：** 2026-05-10  
**狀態：** 已核准

---

## 背景

PigPig 是一個功能豐富的 Discord LLM Bot，目前所有設定（頻道管理、系統提示詞、LLM 模型、記憶系統等）都需要直接編輯設定檔或透過 Discord 指令操作。為了讓 Bot Owner、伺服器管理員和一般使用者都能方便地管理與查看自己的資料，需要建立一個網頁控制介面（Dashboard）。

安全性是核心需求：未來將對所有 Discord 使用者開放，因此需要嚴格的認證與資料隔離機制。目前以 Bot Owner 功能為優先開發。

---

## 架構

### 整體架構

```
[使用者瀏覽器]
     │
     │ HTTPS
     ▼
[Cloudflare Pages]          ← React 前端，靜態部署
     │
     │ HTTPS REST + WebSocket
     ▼
[FastAPI Dashboard Server]  ← 嵌入 Bot 程序，同一 asyncio event loop
     │
     ├── 直接存取 Bot 物件狀態
     ├── 讀寫 YAML/JSON 設定檔
     ├── 讀寫統計資料（SQLite stats DB）
     └── WebSocket 推送 Bot 即時事件
```

FastAPI 以獨立 asyncio task 嵌入 Bot 程序（`bot.py` 的 `setup_hook()` 中啟動），共享同一個 event loop，可直接存取 Bot 狀態而不需要額外 IPC。

### 認證流程（Discord OAuth2）

```
使用者點擊登入
  → 導向 Discord OAuth2 授權頁（scope: identify + guilds）
  → Discord 回傳 authorization code
  → FastAPI 用 code 換取 Discord access_token
  → 呼叫 Discord API 取得 user_id 與所在伺服器列表
  → 判斷權限等級，簽發 JWT（含 user_id、role、guild_ids）
  → 前端儲存 JWT，後續請求帶入 Authorization: Bearer header
```

`.env` 中已有 `CLIENT_ID`、`CLIENT_SECRET_ID`、`SERCET_KEY`，直接使用。

---

## 權限模型

| 角色 | 判斷條件 | 可存取範圍 |
|------|---------|-----------|
| **Bot Owner** | Discord ID == `BOT_OWNER_ID` | 全部功能，包含全域設定、更新管理、所有伺服器、全域統計 |
| **Server Admin** | 在該伺服器擁有 Administrator 權限 | 僅限自己管理的伺服器：頻道設定、系統提示詞、伺服器日誌、伺服器統計 |
| **一般使用者** | 任何成功登入的 Discord 帳號 | 僅限自己的資料：個人記憶、程序性記憶、個人使用統計 |

一個使用者可同時擁有多個角色（例如在某伺服器是 Admin，對其他伺服器只是一般使用者）。

---

## 安全機制

1. **JWT Token** — 含 `user_id`、`role`、`guild_ids`，有效期 1 小時；Refresh Token 有效期 7 天，儲存於 HttpOnly Cookie
2. **CORS 限制** — 後端只接受來自 Cloudflare Pages 域名的跨域請求
3. **Rate Limiting** — 登入端點：每 IP 每分鐘 5 次；一般 API：每使用者每分鐘 60 次
4. **資料隔離** — 每個端點強制驗證請求者只能存取自己有權限的資源；Server Admin 無法跨伺服器存取
5. **敏感操作確認** — 刪除記憶、修改 LLM 設定、執行更新需要額外確認
6. **API Key 遮罩** — 所有 API 金鑰只顯示遮罩（`sk-...****`），不允許透過介面讀取明文
7. **HTTPS 強制** — 後端部署需配置 TLS；Cloudflare Pages 自動提供 HTTPS

---

## 功能模組

### Bot Owner 頁面

| 頁面 | 功能 |
|------|------|
| 全域總覽 | Bot 狀態、連線伺服器數、WebSocket 即時心跳 |
| 全域統計 | 跨伺服器彙總統計（訊息數、LLM 呼叫、錯誤率、回應時間趨勢圖） |
| 全域設定 | 編輯 `base.yaml`、`llm.yaml`、`memory.yaml`、`music.yaml` |
| 更新管理 | 檢查版本、執行更新、查看更新日誌 |
| 全伺服器列表 | 所有伺服器概覽，可進入任一伺服器的管理頁 |
| 即時日誌 | WebSocket 串流所有伺服器日誌，可按伺服器/等級篩選 |

### Server Admin 頁面

| 頁面 | 功能 |
|------|------|
| 伺服器概覽 | 頻道列表、目前模式、Bot 在線狀態 |
| 伺服器統計 | 該伺服器訊息數、活躍用戶、頻道活躍度、LLM 使用量（時間範圍可選） |
| 頻道管理 | 白名單/黑名單切換、故事模式開關、自動回應設定 |
| 系統提示詞 | 查看與編輯該伺服器的 system prompt |
| 伺服器日誌 | 僅顯示該伺服器的日誌（WebSocket） |

### 一般使用者頁面

| 頁面 | 功能 |
|------|------|
| 我的統計 | 個人訊息數、與 Bot 互動次數、各伺服器活躍度 |
| 我的記憶 | 查看程序性記憶（個人偏好）、查詢情節記憶片段 |
| 個人資料 | 顯示 Discord 頭像、用戶名、所在伺服器 |
| 刪除資料 | 請求刪除自己的全部記憶資料（GDPR 友善） |

---

## 統計系統設計

統計資料以獨立的 SQLite 資料庫儲存（`data/stats/stats.db`），由 Bot 程序在關鍵事件發生時非同步寫入，不影響主要訊息處理效能。

### 收集的指標

**Bot 使用統計：**
- 每則訊息記錄：`guild_id`、`user_id`、`channel_id`、`timestamp`
- 每次 LLM 呼叫記錄：`guild_id`、`model_name`、`timestamp`、`duration_ms`、`success`
- 指令使用記錄：`guild_id`、`user_id`、`command_name`、`timestamp`

**記憶系統統計：**
- 情節記憶總數（來自現有 `episodic.db`）
- 程序性記憶用戶數
- 向量存儲集合大小（透過 Qdrant API 查詢）

**系統效能統計：**
- LLM 回應時間（P50/P95/P99）
- 模型熔斷器觸發次數（來自現有 `model_circuit_breaker.py`）
- API 錯誤率（按模型分類）

### 統計 API 端點

```
GET /api/admin/stats/global              → 全域統計彙總（Bot Owner）
GET /api/admin/stats/models              → 模型使用與效能統計（Bot Owner）
GET /api/admin/stats/memory              → 記憶系統統計（Bot Owner）
GET /api/guild/{guild_id}/stats          → 伺服器統計（Server Admin）
GET /api/user/stats                      → 個人使用統計（一般使用者）
```

所有統計端點支援 `?period=7d|30d|90d` 查詢參數。

---

## 完整 API 端點

### 認證
```
GET  /auth/discord/login                  → 導向 Discord OAuth2
GET  /auth/discord/callback               → 處理回調，簽發 JWT
POST /auth/refresh                        → 刷新 JWT
POST /auth/logout                         → 撤銷 Refresh Token
GET  /auth/me                             → 取得目前登入使用者資訊與權限
```

### Bot Owner
```
GET  /api/admin/status                    → Bot 即時狀態
GET  /api/admin/guilds                    → 所有伺服器列表
GET  /api/admin/config/{file}             → 讀取指定 YAML 設定
PUT  /api/admin/config/{file}             → 寫入指定 YAML 設定
POST /api/admin/update/check              → 檢查版本更新
POST /api/admin/update/execute            → 執行更新
GET  /api/admin/stats/global              → 全域統計彙總
GET  /api/admin/stats/models              → 模型使用與效能統計
GET  /api/admin/stats/memory              → 記憶系統統計
WS   /ws/admin/logs                       → 全域日誌串流
```

### Server Admin
```
GET  /api/guild/{guild_id}/overview       → 伺服器概覽
GET  /api/guild/{guild_id}/channels       → 頻道列表與設定
PUT  /api/guild/{guild_id}/channels/{id}  → 更新頻道設定
GET  /api/guild/{guild_id}/prompt         → 取得系統提示詞
PUT  /api/guild/{guild_id}/prompt         → 更新系統提示詞
GET  /api/guild/{guild_id}/stats          → 伺服器統計
WS   /ws/guild/{guild_id}/logs            → 伺服器日誌串流
```

### 一般使用者
```
GET    /api/user/memory/procedural        → 取得個人程序性記憶
GET    /api/user/memory/episodic          → 查詢個人情節記憶片段
DELETE /api/user/memory                   → 刪除自己的全部記憶資料
GET    /api/user/stats                    → 個人使用統計
```

---

## 專案結構

### 後端（嵌入 Bot）
```
dashboard/
├── main.py                  ← FastAPI app 工廠，在 bot.py setup_hook() 中掛載
├── auth/
│   ├── discord_oauth.py     ← Discord OAuth2 流程（使用現有 CLIENT_ID/SECRET）
│   └── jwt_handler.py       ← JWT 簽發/驗證（使用現有 SERCET_KEY）
├── middleware/
│   ├── rate_limit.py        ← slowapi 限速中介層
│   └── permission.py        ← 權限驗證 FastAPI Dependency
├── routers/
│   ├── admin.py             ← Bot Owner 路由
│   ├── guild.py             ← Server Admin 路由
│   ├── user.py              ← 一般使用者路由
│   └── stats.py             ← 統計路由
├── services/
│   └── stats_collector.py   ← 統計資料收集與查詢服務
└── websocket/
    └── log_streamer.py      ← 日誌 WebSocket 管理
```

### 前端（Cloudflare Pages）
```
dashboard-frontend/
├── src/
│   ├── pages/
│   │   ├── admin/           ← Bot Owner 頁面（含統計圖表）
│   │   ├── guild/           ← Server Admin 頁面（含統計圖表）
│   │   └── user/            ← 一般使用者頁面
│   ├── components/
│   │   └── charts/          ← 統計圖表元件（Recharts）
│   ├── hooks/               ← useWebSocket、useAuth 等
│   └── lib/
│       ├── api.ts            ← API 呼叫封裝（axios + JWT interceptor）
│       └── auth.ts           ← Discord OAuth2 處理
└── public/
```

**前端技術：** React + TypeScript + TailwindCSS + React Router + TanStack Query + Recharts（統計圖表）

---

## 開發優先順序

**第一階段（Bot Owner 優先）：**
1. FastAPI 基礎架構 + Discord OAuth2 認證
2. JWT 權限中介層
3. 統計收集器（`stats_collector.py`）嵌入 Bot 事件流
4. Bot Owner：全域總覽、設定檔編輯、統計頁、WebSocket 日誌串流
5. React 前端：登入頁、Admin Dashboard（含圖表）
6. 部署：後端 TLS 設定、Cloudflare Pages 部署

**第二階段：**
7. Server Admin 功能（頻道管理、系統提示詞、伺服器統計）

**第三階段：**
8. 一般使用者功能（記憶查詢、個人統計、刪除資料）

---

## 驗證方式

- **登入流程：** 使用真實 Discord 帳號走完 OAuth2 流程，確認 JWT 簽發正確
- **權限隔離：** 以非 Admin 帳號嘗試存取 `/api/admin/*`，應回傳 403
- **跨伺服器隔離：** 以 Admin 帳號嘗試存取非自己伺服器的 `/api/guild/{other_id}/*`，應回傳 403
- **WebSocket：** 開啟日誌頁，確認 Bot 有訊息時即時推送
- **Rate Limiting：** 連續超過限速後應回傳 429
- **統計資料：** 發送測試訊息後，確認統計端點數值正確增加
- **設定檔寫入：** 修改 `llm.yaml` 後確認檔案正確更新，Bot 重啟後生效
