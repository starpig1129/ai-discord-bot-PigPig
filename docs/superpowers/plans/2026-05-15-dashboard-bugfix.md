# Dashboard 缺陷修復與功能補完實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 Dashboard 的 17 個已知缺陷與技術債，涵蓋 Auth/JWT 安全、後端邏輯、GDPR 合規、前端 UX，並補完記憶編輯與 i18n。

**Architecture:** 三個獨立群組（可各自交付）：A-群組修復 JWT/refresh token 安全問題；B-群組修復後端路由衝突、Qdrant GDPR 刪除、async 阻塞、config 驗證；C-群組修復前端錯誤狀態、新增記憶編輯功能並清理 i18n。

**Tech Stack:** Python 3.11 / FastAPI / aiosqlite / SQLite / QdrantClient / React 19 / TypeScript / react-i18next / Framer Motion

---

## 檔案異動總覽

| 操作 | 路徑 | 群組 |
|------|------|------|
| Modify | `dashboard/auth/jwt_handler.py` | A |
| Create | `dashboard/auth/token_store.py` | A |
| Modify | `dashboard/auth/discord_oauth.py` | A |
| Modify | `dashboard/main.py` | A, B |
| Modify | `dashboard/routers/stats.py` | B |
| Modify | `dashboard/routers/admin.py` | B, C |
| Modify | `dashboard/routers/guild.py` | B |
| Modify | `dashboard/routers/user.py` | C |
| Modify | `cogs/memory/interfaces/vector_store_interface.py` | B |
| Modify | `cogs/memory/vector_stores/qdrant_store.py` | B |
| Modify | `cogs/memory/db/procedural_storage.py` | B |
| Modify | `cogs/memory/users/manager.py` | B |
| Modify | `dashboard-frontend/src/pages/admin/Dashboard.tsx` | C |
| Modify | `dashboard-frontend/src/pages/admin/Users.tsx` | C |
| Modify | `dashboard-frontend/src/pages/admin/user/Memory.tsx` | C |
| Modify | `dashboard-frontend/src/pages/admin/user/UserStats.tsx` | C |
| Modify | `dashboard-frontend/src/pages/admin/guild/Overview.tsx` | C |
| Modify | `dashboard-frontend/src/i18n/locales/en.json` | C |
| Modify | `dashboard-frontend/src/i18n/locales/zh-TW.json` | C |

---

## ══════════════════════════════════
## 群組 A：Auth / JWT 安全修復
## ══════════════════════════════════

### Task 1：修復 JWT secret key 拼字錯誤（D-2）

**Files:**
- Modify: `dashboard/auth/jwt_handler.py`

問題：第 27 行 `getattr(tokens, "sercet_key", None)` 拼錯（多一個 e），永遠讀不到 `.env` 中的正確值，每次重啟用隨機 key，所有 token 失效。

- [ ] **Step 1：確認 `.env Example` 中的變數名稱**

```bash
grep -i "secret\|sercet" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/.env\ Example
```

預期輸出包含 `DASHBOARD_SECRET_KEY` 或類似名稱，確認正確拼法。

- [ ] **Step 2：確認 `addons/tokens.py` 的屬性名稱**

```bash
grep -n "secret\|sercet" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/addons/tokens.py
```

- [ ] **Step 3：修改 `jwt_handler.py` 第 27-29 行**

將：
```python
_SECRET_KEY: str = getattr(tokens, "sercet_key", None) or secrets.token_urlsafe(64)
if _SECRET_KEY == "DASHBOARD_SERCET_KEY":
    log.warning("Using placeholder SERCET_KEY — replace before production!")
```

改為（`sercet_key` → `secret_key`，placeholder 檢查同步修正）：
```python
_SECRET_KEY: str = getattr(tokens, "secret_key", None) or secrets.token_urlsafe(64)
if not getattr(tokens, "secret_key", None):
    log.warning("DASHBOARD_SECRET_KEY not set in .env — using random key (all tokens invalidated on restart)")
```

- [ ] **Step 4：確認 `addons/tokens.py` 中屬性讀取方式，確保名稱對應**

若 `tokens.py` 中的屬性也拼錯，同步修正（讀取環境變數的那一行）。

- [ ] **Step 5：Commit**

```bash
git add dashboard/auth/jwt_handler.py addons/tokens.py
git commit -m "fix: correct JWT secret_key attribute name typo (sercet → secret)"
```

---

### Task 2：將 Refresh Token 持久化至 SQLite（D-3）

**Files:**
- Create: `dashboard/auth/token_store.py`
- Modify: `dashboard/auth/jwt_handler.py`
- Modify: `dashboard/main.py`

問題：`_refresh_store` 是 module-level dict，Bot 重啟後所有 refresh token 遺失，所有用戶被強制重新登入。

- [ ] **Step 1：建立 `dashboard/auth/token_store.py`**

```python
"""Persistent refresh-token store backed by SQLite.

Replaces the in-memory dict so tokens survive bot restarts.
"""
from __future__ import annotations

import time
from pathlib import Path

import aiosqlite

from addons.logging import get_logger
from function import ROOT_DIR

log = get_logger(server_id="Bot", source=__name__)

_DB_PATH = Path(ROOT_DIR) / "data" / "auth" / "tokens.db"


async def initialize() -> None:
    """Create the tokens table if it doesn't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token      TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                exp        REAL NOT NULL
            )
            """
        )
        await db.commit()


async def store(token: str, user_id: str, exp: float) -> None:
    """Persist a new refresh token."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute(
            "INSERT OR REPLACE INTO refresh_tokens (token, user_id, exp) VALUES (?, ?, ?)",
            (token, user_id, exp),
        )
        await db.commit()


async def lookup(token: str) -> str | None:
    """Return user_id for a valid non-expired token, or None."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, exp FROM refresh_tokens WHERE token = ?", (token,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    if time.time() > row["exp"]:
        await revoke(token)
        return None
    return row["user_id"]


async def revoke(token: str) -> None:
    """Delete a single refresh token."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
        await db.commit()


async def cleanup_expired() -> None:
    """Purge all expired tokens from the database."""
    async with aiosqlite.connect(str(_DB_PATH)) as db:
        await db.execute("DELETE FROM refresh_tokens WHERE exp < ?", (time.time(),))
        await db.commit()
```

- [ ] **Step 2：更新 `jwt_handler.py` 使用 token_store**

將 `jwt_handler.py` 中的 `create_refresh_token`、`verify_refresh_token`、`revoke_refresh_token`、`_cleanup_expired_refresh_tokens` 全部改為呼叫 `token_store`：

```python
# 在檔案頂部加入 import
from dashboard.auth import token_store

# 修改 create_refresh_token
def create_refresh_token(user_id: str) -> str:
    """Create a long-lived opaque refresh token and schedule persistence."""
    token = secrets.token_urlsafe(48)
    exp = time.time() + REFRESH_TOKEN_EXPIRE_SECONDS
    # Schedule async persistence without blocking
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(token_store.store(token, user_id, exp))
    except RuntimeError:
        # No running loop (test context) — skip persistence
        pass
    return token


async def verify_refresh_token_async(token: str) -> str | None:
    """Async version of verify_refresh_token using persistent store."""
    return await token_store.lookup(token)


def verify_refresh_token(token: str) -> str | None:
    """Sync shim — only used in test context. Use verify_refresh_token_async in endpoints."""
    import asyncio
    try:
        return asyncio.get_event_loop().run_until_complete(token_store.lookup(token))
    except Exception:
        return None


async def revoke_refresh_token_async(token: str) -> None:
    """Async version of revoke_refresh_token."""
    await token_store.revoke(token)


def revoke_refresh_token(token: str) -> None:
    """Sync shim — for backwards compatibility."""
    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(token_store.revoke(token))
    except Exception:
        pass
```

保留 `_refresh_store` 相關的函數名稱作為 shim 以防其他地方引用，但實際儲存已切換到 SQLite。

- [ ] **Step 3：更新 `discord_oauth.py` 的 refresh 和 logout 端點改用 async 版本**

在 `discord_oauth.py` 中：
- `/auth/refresh` 將 `verify_refresh_token(refresh_tok)` 改為 `await verify_refresh_token_async(refresh_tok)`
- `/auth/logout` 將 `revoke_refresh_token(refresh_tok)` 改為 `await revoke_refresh_token_async(refresh_tok)`

- [ ] **Step 4：在 `dashboard/main.py` 的 `start_dashboard` 中初始化 token_store**

在 `await app.state.stats_collector.initialize()` 後加入：

```python
from dashboard.auth import token_store as _token_store
await _token_store.initialize()
log.info("Refresh token store initialized")
```

- [ ] **Step 5：確認不會引入 import cycle**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python3 -c "from dashboard.auth.token_store import initialize; print('OK')"
```

預期：`OK`

- [ ] **Step 6：Commit**

```bash
git add dashboard/auth/token_store.py dashboard/auth/jwt_handler.py dashboard/auth/discord_oauth.py dashboard/main.py
git commit -m "feat: persist refresh tokens in SQLite to survive bot restarts"
```

---

### Task 3：修復 Refresh Token 後角色與 Guild 遺失（D-1 / M-1）

**Files:**
- Modify: `dashboard/auth/discord_oauth.py`

問題：`/auth/refresh` 端點重新發行 access token 時只處理 owner/user 兩個角色，`guild_ids` 硬寫為 `[]`，導致 server admin 刷新後失去所有 guild 存取權。

修復策略：利用 `request.app.state.bot` 的 guild cache 重新計算 role 和 guild_ids，不需要再次呼叫 Discord API。

- [ ] **Step 1：修改 `discord_oauth.py` 的 `/auth/refresh` 端點**

將第 202-229 行的 `refresh` 函數替換為：

```python
@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    """Refresh the JWT access token using the refresh token cookie.

    Recalculates role and guild_ids from the bot's cached guild state
    so server admins don't lose permissions after token expiry.
    """
    from dashboard.auth.jwt_handler import verify_refresh_token_async, create_access_token

    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    user_id = await verify_refresh_token_async(refresh_tok)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Re-derive role and guild_ids from bot state (no Discord API call needed)
    bot_owner_id = str(getattr(tokens, "bot_owner_id", 0))
    bot = _get_bot(request)

    if user_id == bot_owner_id:
        role = "owner"
        guild_ids = [str(g.id) for g in bot.guilds] if bot else []
    elif bot:
        guild_ids = []
        admin_guild_ids = []
        for guild in bot.guilds:
            member = guild.get_member(int(user_id))
            if member:
                guild_ids.append(str(guild.id))
                if member.guild_permissions.administrator:
                    admin_guild_ids.append(str(guild.id))
        role = "admin" if admin_guild_ids else "user"
    else:
        role = "user"
        guild_ids = []

    # Preserve existing access token claims we don't re-fetch (avatar, username)
    # by reading them from the old access token if present
    old_auth = request.headers.get("Authorization", "")
    avatar, username = "", ""
    if old_auth.startswith("Bearer "):
        from dashboard.auth.jwt_handler import verify_access_token
        old_payload = verify_access_token(old_auth[7:])
        if old_payload:
            avatar = old_payload.get("avatar", "")
            username = old_payload.get("username", "")

    access_token = create_access_token(
        user_id=user_id,
        role=role,
        guild_ids=guild_ids,
        avatar=avatar,
        username=username,
    )
    return JSONResponse({"access_token": access_token, "token_type": "Bearer"})
```

- [ ] **Step 2：手動測試 refresh 端點（若有測試環境）**

```bash
# 以 server admin 身份登入後取得 refresh cookie，然後：
curl -X POST http://localhost:8005/auth/refresh \
  -H "Cookie: refresh_token=<token>" \
  -H "Authorization: Bearer <old_access_token>"
# 預期回應中 role 為 "admin" 且 guild_ids 非空
```

- [ ] **Step 3：Commit**

```bash
git add dashboard/auth/discord_oauth.py
git commit -m "fix: recalculate role and guild_ids on token refresh to prevent admin permission loss"
```

---

## ══════════════════════════════════
## 群組 B：後端邏輯修復
## ══════════════════════════════════

### Task 4：移除重複的 guild stats 路由（D-4）

**Files:**
- Modify: `dashboard/routers/stats.py`

問題：`stats.py` 有 `GET /api/guild/{guild_id}/stats`（用 `require_admin` 保護），`guild.py` 有 `GET /api/guild/{guild_id}/stats`（用 `require_guild_access` 保護）。`main.py` 先 include `guild_router` 再 include `stats_router`，所以 `guild.py` 的版本生效，`stats.py` 的 `require_admin` 限制完全失效。

正確行為：guild stats 應由 `guild.py` 統一管理，`stats.py` 只處理 `/api/admin/stats/*`。

- [ ] **Step 1：確認 stats.py 中重複定義的路由位置**

```bash
grep -n "guild_id\|/guild" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard/routers/stats.py
```

- [ ] **Step 2：從 `stats.py` 刪除第 83-95 行的 `guild_stats` 函數**

刪除以下整個函數（包含上方空行）：

```python
@router.get("/guild/{guild_id}/stats")
async def guild_stats(
    guild_id: str,
    request: Request,
    period: str = Query(default="30d"),
    user: dict = Depends(require_admin),
) -> JSONResponse:
    """Per-guild statistics (Server Admin or Owner)."""
    from dashboard.middleware.permission import require_guild_access
    require_guild_access(guild_id, user)
    stats = _get_stats(request)
    data = await stats.get_guild_stats(guild_id, period)
    return JSONResponse(data)
```

- [ ] **Step 3：確認 `stats.py` 的 import 中 `require_admin` 若不再使用則移除**

```bash
grep -n "require_admin" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard/routers/stats.py
```

若 `require_admin` 已無其他使用，從 import 行移除。

- [ ] **Step 4：確認端點清單**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python3 -c "
from dashboard.routers.stats import router
from dashboard.routers.guild import router as gr
print('stats:', [r.path for r in router.routes])
print('guild:', [r.path for r in gr.routes if 'stats' in r.path])
"
```

預期 stats router 不再包含 `/guild/{guild_id}/stats`。

- [ ] **Step 5：Commit**

```bash
git add dashboard/routers/stats.py
git commit -m "fix: remove duplicate guild stats route from stats.py to prevent security policy conflict"
```

---

### Task 5：新增 Qdrant 向量刪除以完成 GDPR 合規（D-7）

**Files:**
- Modify: `cogs/memory/interfaces/vector_store_interface.py`
- Modify: `cogs/memory/vector_stores/qdrant_store.py`
- Modify: `dashboard/routers/admin.py`

問題：admin 的刪除端點只清 SQLite，Qdrant 中包含該用戶 `author_ids` 的所有向量片段仍殘留。由於刪除向量會影響頻道記憶運作，**僅 admin 端點執行此操作**，user 的 GDPR self-delete 不刪向量。

- [ ] **Step 1：在 `VectorStoreInterface` 新增抽象方法**

在 `cogs/memory/interfaces/vector_store_interface.py` 末尾（`search` 方法之後）加入：

```python
    @abstractmethod
    async def delete_vectors_by_user(self, user_id: str) -> int:
        """Delete all vector fragments where user_id appears in metadata.author_ids.

        Only administrators should call this — it removes shared conversation
        segments, which affects channel memory continuity.

        Args:
            user_id: Discord user ID.

        Returns:
            Number of deleted points, or -1 if the store does not report a count.
        """
        raise NotImplementedError
```

- [ ] **Step 2：在 `QdrantStore` 實作 `delete_vectors_by_user`**

在 `cogs/memory/vector_stores/qdrant_store.py` 的 `_report_error` 方法之前插入：

```python
    async def delete_vectors_by_user(self, user_id: str) -> int:
        """Delete all vectors where user_id appears in metadata.author_ids."""
        from qdrant_client.models import Filter, FieldCondition, MatchAny, FilterSelector

        def _do_delete() -> int:
            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="metadata.author_ids",
                                match=MatchAny(any=[str(user_id)]),
                            )
                        ]
                    )
                ),
            )
            # UpdateResult has operation_id but no deleted count; return sentinel
            return -1

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _do_delete)
        except Exception as e:
            asyncio.create_task(self._report_error(e))
            raise VectorOperationError(f"Failed to delete vectors for user {user_id}") from e
```

- [ ] **Step 3：在 `admin.py` 的 `admin_delete_user_memory` 端點末尾加入向量清理**

在 `dashboard/routers/admin.py` 的 `admin_delete_user_memory` 函數中，`stats_db` 刪除完畢之後（第 437 行 `log.info` 之前）加入：

```python
    # Delete vectors from Qdrant (admin-only; affects channel memory continuity)
    bot = request.app.state.bot
    vector_manager = getattr(bot, "vector_manager", None)
    if vector_manager and getattr(vector_manager, "_store", None):
        try:
            await vector_manager.store.delete_vectors_by_user(user_id)
            deleted["qdrant_vectors"] = -1  # count not available from Qdrant API
            log.info(f"Qdrant vectors deleted for user {user_id}")
        except Exception as exc:
            log.warning(f"Qdrant vector deletion failed for {user_id}: {exc}")
            deleted["qdrant_vectors"] = 0
```

- [ ] **Step 4：確認端點路由仍可正確載入**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python3 -c "
from cogs.memory.vector_stores.qdrant_store import QdrantStore
print('delete_vectors_by_user' in dir(QdrantStore))
"
```

預期：`True`

- [ ] **Step 5：Commit**

```bash
git add cogs/memory/interfaces/vector_store_interface.py \
        cogs/memory/vector_stores/qdrant_store.py \
        dashboard/routers/admin.py
git commit -m "feat: add Qdrant vector deletion to admin user delete endpoint for GDPR compliance"
```

---

### Task 6：修復 `_update_cache` 在同步執行緒中呼叫 asyncio.create_task（D-8）

**Files:**
- Modify: `cogs/memory/db/procedural_storage.py`

問題：`_update_cache` 是同步方法，在 `asyncio.to_thread` 的工作執行緒中被呼叫。其 except block 呼叫 `asyncio.create_task`，但執行緒沒有 event loop，會拋出 `RuntimeError`。

- [ ] **Step 1：找到 `_update_cache` 的位置**

```bash
grep -n "_update_cache\|create_task" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/cogs/memory/db/procedural_storage.py
```

- [ ] **Step 2：修改 `_update_cache` 方法，移除 `asyncio.create_task`**

將：
```python
    def _update_cache(self, user_id: str, user_info: UserInfo) -> None:
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            # avoid awaiting in synchronous helper; spawn a task
            asyncio.create_task(func.report_error(e, "cache update failed"))
```

改為：
```python
    def _update_cache(self, user_id: str, user_info: UserInfo) -> None:
        try:
            if len(self._user_cache) >= self._cache_size_limit:
                oldest = next(iter(self._user_cache))
                del self._user_cache[oldest]
            self._user_cache[user_id] = user_info
        except Exception as e:
            # This runs in a thread — cannot await or create tasks
            import logging as _logging
            _logging.getLogger(__name__).exception("cache update failed: %s", e)
```

- [ ] **Step 3：Commit**

```bash
git add cogs/memory/db/procedural_storage.py
git commit -m "fix: replace asyncio.create_task with logger in sync _update_cache to prevent RuntimeError in thread"
```

---

### Task 7：修復 Qdrant 同步阻塞呼叫並建立共享 client（D-9 / T-5）

**Files:**
- Modify: `dashboard/routers/guild.py`
- Modify: `dashboard/main.py`

問題：`guild.py` 第 682-699 行在 async endpoint 中直接呼叫 `client.scroll()`（同步阻塞），且每次請求都重新建立 `QdrantClient` 連線（程式碼注釋也承認此問題）。

修復：將 `QdrantClient` 改為 app-level shared dependency，並用 `asyncio.to_thread` 包裝阻塞呼叫。

- [ ] **Step 1：在 `dashboard/main.py` 的 `create_app` 中初始化共享 Qdrant client**

在 `app.state.stats_collector = bot.stats_collector` 之後加入：

```python
    # Shared Qdrant client for dashboard routers (avoids per-request reconnect)
    from addons.settings import memory_config
    from addons.tokens import tokens as _tokens
    if getattr(memory_config, "enabled", False) and getattr(memory_config, "vector_store_type", "") == "qdrant":
        try:
            from qdrant_client import QdrantClient as _QC
            app.state.qdrant_client = _QC(
                url=memory_config.qdrant_url,
                api_key=getattr(_tokens, "vector_store_api_key", None),
                timeout=60,
            )
            log.info("Shared Qdrant client initialized for dashboard")
        except Exception as _e:
            log.warning(f"Could not initialize shared Qdrant client: {_e}")
            app.state.qdrant_client = None
    else:
        app.state.qdrant_client = None
```

- [ ] **Step 2：更新 `guild.py` 的 episodic fragments 查詢，改用共享 client 和 `asyncio.to_thread`**

找到 `guild.py` 第 679-709 行（episodic Qdrant 查詢區塊），替換為：

```python
    # 3. Fetch episodic fragments from Qdrant
    if memory_config.enabled and memory_config.vector_store_type == "qdrant":
        qdrant_client = getattr(request.app.state, "qdrant_client", None)
        if qdrant_client:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                def _scroll_channel(client, collection, channel_id):
                    points, _ = client.scroll(
                        collection_name=collection,
                        scroll_filter=Filter(
                            must=[FieldCondition(
                                key="metadata.channel_id",
                                match=MatchValue(value=str(channel_id))
                            )]
                        ),
                        limit=50,
                        with_payload=True,
                        with_vectors=False,
                    )
                    return points

                points = await asyncio.to_thread(
                    _scroll_channel,
                    qdrant_client,
                    memory_config.qdrant_collection_name,
                    channel_id,
                )
                for p in points:
                    payload = p.payload or {}
                    metadata = payload.get("metadata", {})
                    fragments.append({
                        "id": metadata.get("fragment_id", str(p.id)),
                        "content": metadata.get("summary", payload.get("page_content", "")),
                        "timestamp": metadata.get("end_timestamp") or metadata.get("timestamp"),
                    })
            except Exception as exc:
                log.warning(f"Qdrant episodic fetch failed for channel {channel_id}: {exc}")
```

- [ ] **Step 3：移除 `guild.py` 頂部不再需要的 per-request QdrantClient import**

確認 `from qdrant_client import QdrantClient` 這個 import 在 guild.py 中是否還有其他用途。若只有此處，從 import 中移除。

- [ ] **Step 4：Commit**

```bash
git add dashboard/main.py dashboard/routers/guild.py
git commit -m "fix: use shared Qdrant client and asyncio.to_thread to prevent event loop blocking in guild router"
```

---

### Task 8：為 `write_config` 新增 YAML schema 驗證（T-2）

**Files:**
- Modify: `dashboard/routers/admin.py`

問題：`write_config` 只確認 `config` key 存在，沒有驗證結構，Owner 可以寫入任意內容覆蓋 config 導致 Bot 啟動失敗。

修復：確認寫入內容為 dict，且頂層 key 在白名單內（各 config 各有不同白名單）。

- [ ] **Step 1：在 `admin.py` 的 `write_config` 中加入驗證（第 117-134 行區域）**

在 `config_data = body.get("config")` 和 `if config_data is None:` 之後加入：

```python
    # Validate: must be a dict
    if not isinstance(config_data, dict):
        raise HTTPException(status_code=400, detail="'config' must be a JSON object (dict)")

    # Per-file top-level key whitelists (prevents accidental full-overwrite with garbage)
    _CONFIG_ALLOWED_KEYS: dict[str, set[str]] = {
        "base":   {"bot_prefix", "ipc", "logging", "dashboard", "version"},
        "llm":    {"task_models", "default_model", "fallback_chain", "circuit_breaker"},
        "memory": {"enabled", "vector_store_type", "qdrant_url", "qdrant_collection_name",
                   "embedding_provider", "embedding_model", "embedding_dim",
                   "message_threshold", "time_threshold", "sqlite_db_path"},
        "music":  {"ffmpeg_path", "ytdl_format", "volume"},
    }
    allowed = _CONFIG_ALLOWED_KEYS.get(file)
    if allowed:
        unknown = set(config_data.keys()) - allowed
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown keys for config '{file}': {sorted(unknown)}. Allowed: {sorted(allowed)}",
            )
```

- [ ] **Step 2：測試邊界情況**

```bash
# 測試寫入非 dict 應回傳 400
curl -X PUT http://localhost:8005/api/admin/config/base \
  -H "Authorization: Bearer <owner_token>" \
  -H "Content-Type: application/json" \
  -d '{"config": "not_a_dict"}'
# 預期 400

# 測試寫入未知 key 應回傳 400
curl -X PUT http://localhost:8005/api/admin/config/base \
  -H "Authorization: Bearer <owner_token>" \
  -H "Content-Type: application/json" \
  -d '{"config": {"unknown_key": "value"}}'
# 預期 400

# 測試寫入合法 key 應回傳 200
curl -X PUT http://localhost:8005/api/admin/config/base \
  -H "Authorization: Bearer <owner_token>" \
  -H "Content-Type: application/json" \
  -d '{"config": {"bot_prefix": "!"}}'
# 預期 200
```

- [ ] **Step 3：Commit**

```bash
git add dashboard/routers/admin.py
git commit -m "feat: add schema validation to write_config endpoint to prevent malformed YAML overwrites"
```

---

### Task 9：移除 SQLiteUserManager 的獨立快取層（T-6）

**Files:**
- Modify: `cogs/memory/users/manager.py`

問題：`SQLiteUserManager` 有自己的 `_user_cache`，`ProceduralStorage` 也有自己的 `_user_cache`。當 storage 快取清除後，manager 快取可能仍持有舊資料，造成不一致。

修復：移除 manager 的快取，直接委派給 storage（storage 已有完整的 TTL 快取機制）。

- [ ] **Step 1：從 `manager.py` 移除 `_user_cache` 和 `_cache_size_limit`**

刪除 `__init__` 中的：
```python
        self._user_cache: Dict[str, UserInfo] = {}
        self._cache_size_limit = 1000
```

- [ ] **Step 2：移除 `get_user_info` 中的快取讀寫邏輯**

將：
```python
    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """Retrieve user info via storage and update cache."""
        if use_cache and user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            user_info = await self.storage.get_user_info(user_id)
            if user_info and use_cache:
                self._update_cache(user_id, user_info)
            return user_info
        except Exception as e:
            await func.report_error(e, f"Failed to retrieve user info (user: {user_id})")
```

改為：
```python
    async def get_user_info(self, user_id: str, use_cache: bool = True) -> Optional[UserInfo]:
        """Retrieve user info via storage (storage handles its own caching)."""
        try:
            return await self.storage.get_user_info(user_id)
        except Exception as e:
            await func.report_error(e, f"Failed to retrieve user info (user: {user_id})")
            return None
```

- [ ] **Step 3：移除 `_update_cache` 方法**

找到並刪除 manager.py 中的 `_update_cache` 方法（若有的話）。

- [ ] **Step 4：搜尋其他引用 `_user_cache` 的地方**

```bash
grep -rn "_user_cache\|_update_cache" /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/cogs/memory/users/manager.py
```

確認清理完畢。

- [ ] **Step 5：Commit**

```bash
git add cogs/memory/users/manager.py
git commit -m "refactor: remove redundant user cache layer from SQLiteUserManager to prevent cache inconsistency"
```

---

## ══════════════════════════════════
## 群組 C：前端 UX 修復與功能補完
## ══════════════════════════════════

### Task 10：為四個頁面新增 API 錯誤狀態顯示（D-12）

**Files:**
- Modify: `dashboard-frontend/src/pages/admin/Dashboard.tsx`
- Modify: `dashboard-frontend/src/pages/admin/user/Memory.tsx`
- Modify: `dashboard-frontend/src/pages/admin/guild/Overview.tsx`
- Modify: `dashboard-frontend/src/pages/admin/user/UserStats.tsx`

問題：四個頁面的 `.catch(() => {})` 靜默吞掉所有 API 錯誤，用戶只看到永久 loading 或空白。

模式：各頁面加入 `error` state，`.catch` 中 `setError(...)` 而非空函數，UI 頂部顯示錯誤 banner。

- [ ] **Step 1：修改 `Dashboard.tsx`**

找到現有的 `setLoading` state 宣告，加入 error state 並更新 `catch`：

```tsx
// 加在 useState 宣告區
const [error, setError] = useState('');

// 將 .catch(() => {}) 改為：
.catch((err) => {
  setError(err?.response?.data?.detail || 'Failed to load dashboard data');
})
```

在 loading 判斷之後、return 的第一個 `<div>` 內頂部加入：

```tsx
{error && (
  <div style={{
    padding: '0.75rem 1rem',
    marginBottom: '1rem',
    borderRadius: 'var(--radius-md)',
    background: 'rgba(244,63,94,0.1)',
    border: '1px solid rgba(244,63,94,0.3)',
    color: '#f43f5e',
    fontSize: '0.875rem',
  }}>
    ⚠️ {error}
  </div>
)}
```

- [ ] **Step 2：修改 `Memory.tsx`**

```tsx
// 加在 useState 宣告區
const [error, setError] = useState('');

// 將 catch 改為：
} catch (err: any) {
  setError(err?.response?.data?.detail || 'Failed to load memory data');
}
```

在 return 最外層 div 內頂部加入同樣的 error banner（同 Step 1 樣式）。

- [ ] **Step 3：修改 `Overview.tsx`**

```tsx
// 加在 useState 宣告區
const [error, setError] = useState('');

// 將 .catch(() => {}) 改為：
.catch((err) => {
  setError(err?.response?.data?.detail || 'Failed to load overview data');
})
```

加入同樣的 error banner。

- [ ] **Step 4：修改 `UserStats.tsx`**

```tsx
// 加在 useState 宣告區
const [error, setError] = useState('');

// 將 .catch(() => {}) 改為：
.catch((err) => {
  setError(err?.response?.data?.detail || 'Failed to load statistics');
})
```

加入同樣的 error banner。

- [ ] **Step 5：Build 前端確認無 TypeScript 錯誤**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard-frontend
npm run build 2>&1 | tail -20
```

預期：Build 成功，無錯誤。

- [ ] **Step 6：Commit**

```bash
git add dashboard-frontend/src/pages/admin/Dashboard.tsx \
        dashboard-frontend/src/pages/admin/user/Memory.tsx \
        dashboard-frontend/src/pages/admin/guild/Overview.tsx \
        dashboard-frontend/src/pages/admin/user/UserStats.tsx
git commit -m "fix: add error state display to Dashboard, Memory, Overview, UserStats pages instead of silently swallowing API errors"
```

---

### Task 11：修復刪除按鈕無 loading 狀態，可重複點擊（D-11）

**Files:**
- Modify: `dashboard-frontend/src/pages/admin/Users.tsx`

問題：`handleDelete` 執行期間，確認彈窗的刪除按鈕未 disabled，可連續送出多次 DELETE 請求。

- [ ] **Step 1：在 `Users.tsx` 加入 `isDeleting` state**

在現有 state 宣告區加入：
```tsx
const [isDeleting, setIsDeleting] = useState(false);
```

- [ ] **Step 2：更新 `handleDelete` 函數**

將 `handleDelete` 改為：
```tsx
const handleDelete = async (userId: string) => {
  setIsDeleting(true);
  try {
    await api.delete(`/api/admin/users/${userId}/memory`, { data: { confirm: true } });
    setDeleteMsg(t('admin.deleteSuccess', { id: userId }));
    msgTimerRef.current = setTimeout(() => setDeleteMsg(''), 5000);
    setDeleteConfirm(null);
    setSelectedUser(null);
    refetch();
  } catch {
    setDeleteMsg(t('admin.deleteFailed'));
    msgTimerRef.current = setTimeout(() => setDeleteMsg(''), 5000);
  } finally {
    setIsDeleting(false);
  }
};
```

- [ ] **Step 3：在確認模態框的刪除按鈕加入 disabled 和 loading 樣式**

找到確認 modal 中的刪除按鈕（`onClick={() => handleDelete(deleteConfirm)}`），改為：

```tsx
<button
  onClick={() => handleDelete(deleteConfirm)}
  disabled={isDeleting}
  style={{
    padding: '0.5rem 1rem',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: isDeleting ? 'rgba(244,63,94,0.5)' : '#f43f5e',
    color: 'white',
    cursor: isDeleting ? 'not-allowed' : 'pointer',
    fontWeight: 600,
    opacity: isDeleting ? 0.7 : 1,
  }}
>
  {isDeleting ? '...' : t('admin.deleteMemory')}
</button>
```

- [ ] **Step 4：Build 前端確認**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard-frontend
npm run build 2>&1 | tail -10
```

- [ ] **Step 5：Commit**

```bash
git add dashboard-frontend/src/pages/admin/Users.tsx
git commit -m "fix: disable delete button during deletion to prevent duplicate DELETE requests"
```

---

### Task 12：在 Admin 用戶詳細面板顯示 Guild 名稱（M-3）

**Files:**
- Modify: `dashboard/routers/admin.py`
- Modify: `dashboard-frontend/src/pages/admin/Users.tsx`

問題：`get_user_detail` 回傳的 `guild_stats` 只有 `guild_id`（數字），前端直接顯示看不懂。

- [ ] **Step 1：在 `admin.py` 的 `get_user_detail` 中注入 guild_name**

找到 `guild_stats.append({` 的那段（約第 383-389 行），修改為：

```python
        bot_ref = request.app.state.bot
        guild_obj = bot_ref.get_guild(int(row["guild_id"])) if bot_ref else None
        guild_stats.append({
            "guild_id": row["guild_id"],
            "guild_name": guild_obj.name if guild_obj else f"Unknown ({row['guild_id']})",
            "total_messages": row["total_messages"],
            "streak_days": row["streak_days"],
            "last_active_at": row["last_active_at"],
            "first_message_at": row["first_message_at"],
        })
```

注意：`get_user_detail` 需要有 `request` 參數才能存取 `app.state.bot`。確認函數簽名包含 `request: Request`（若未包含，加入）。

- [ ] **Step 2：更新 `Users.tsx` 的 TypeScript 介面和顯示**

在 `UserDetail` interface 的 `guild_stats` 型別中加入 `guild_name`:

```tsx
guild_stats: {
  guild_id: string;
  guild_name?: string;      // 新增
  total_messages: number;
  streak_days: number;
  last_active_at: string | null;
  first_message_at: string | null;
}[];
```

在 guild activity 區塊（顯示 `gs.guild_id` 的地方）改為顯示名稱優先：

```tsx
<div style={{ fontFamily: 'monospace', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
  {gs.guild_name || gs.guild_id}
</div>
```

- [ ] **Step 3：Build 前端確認**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard-frontend
npm run build 2>&1 | tail -10
```

- [ ] **Step 4：Commit**

```bash
git add dashboard/routers/admin.py dashboard-frontend/src/pages/admin/Users.tsx
git commit -m "feat: resolve guild names in admin user detail panel instead of showing raw IDs"
```

---

### Task 13：新增用戶記憶自助編輯功能（M-2）

**Files:**
- Modify: `dashboard/routers/user.py`
- Modify: `dashboard-frontend/src/pages/admin/user/Memory.tsx`
- Modify: `dashboard-frontend/src/i18n/locales/en.json`
- Modify: `dashboard-frontend/src/i18n/locales/zh-TW.json`

問題：`/me/memory` 頁面只能查看 `procedural_memory` 和 `user_background`，無法編輯。

- [ ] **Step 1：在 `user.py` 新增 `PUT /api/user/memory/procedural` 端點**

在 `get_procedural_memory` 函數之後（第 139 行後）插入：

```python
@router.put("/memory/procedural")
async def update_procedural_memory(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Update the authenticated user's procedural memory and background.

    Only allows updating procedural_memory and user_background.
    Does not allow changing discord_id or discord_name.

    Request body: {"procedural_memory": "...", "user_background": "..."}
    Either field can be omitted (PATCH semantics — only provided fields are updated).
    """
    body: dict[str, Any] = await request.json()

    # Validate: only allow these two fields
    allowed = {"procedural_memory", "user_background"}
    unknown = set(body.keys()) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {sorted(unknown)}")

    procedural_memory = body.get("procedural_memory")
    user_background = body.get("user_background")

    # At least one field must be provided
    if procedural_memory is None and user_background is None:
        raise HTTPException(status_code=400, detail="Provide at least one of: procedural_memory, user_background")

    user_id: str = user["sub"]

    if not _PROCEDURAL_DB.exists():
        raise HTTPException(status_code=404, detail="Memory database not found")

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            # Verify user exists
            cursor = await db.execute(
                "SELECT discord_id FROM users WHERE discord_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="User memory record not found")

            # PATCH-style update: only update provided fields
            updates = []
            params = []
            if procedural_memory is not None:
                updates.append("procedural_memory = ?")
                params.append(procedural_memory)
            if user_background is not None:
                updates.append("user_background = ?")
                params.append(user_background)

            params.append(user_id)
            await db.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE discord_id = ?",
                params,
            )
            await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        log.error(f"update_procedural_memory failed for {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database temporarily unavailable")

    log.info(f"User {user_id} updated procedural memory")
    return JSONResponse({"detail": "Memory updated", "user_id": user_id})
```

- [ ] **Step 2：在 i18n 加入新的翻譯 key**

在 `en.json` 的 `user` 區段加入：
```json
"editMemory": "Edit Memory",
"editProcedural": "Edit Procedural Memory",
"editBackground": "Edit User Background",
"saveMemory": "Save",
"cancelEdit": "Cancel",
"memorySaved": "Memory saved successfully",
"memoryPlaceholderProcedural": "Enter preferences, habits, communication style...",
"memoryPlaceholderBackground": "Enter background information, context..."
```

在 `zh-TW.json` 的 `user` 區段加入：
```json
"editMemory": "編輯記憶",
"editProcedural": "編輯程序記憶",
"editBackground": "編輯用戶背景",
"saveMemory": "儲存",
"cancelEdit": "取消",
"memorySaved": "記憶儲存成功",
"memoryPlaceholderProcedural": "輸入偏好、習慣、溝通風格...",
"memoryPlaceholderBackground": "輸入背景資訊、個人脈絡..."
```

- [ ] **Step 3：在 `Memory.tsx` 加入編輯功能**

在現有 `procedural_memory` 顯示區塊旁加入編輯按鈕，展開行內編輯區：

在 `Memory.tsx` 的 state 宣告區加入：
```tsx
const [editing, setEditing] = useState<'procedural' | 'background' | null>(null);
const [editValue, setEditValue] = useState('');
const [saving, setSaving] = useState(false);
const [saveMsg, setSaveMsg] = useState('');
```

加入 save 函數：
```tsx
const handleSave = async () => {
  if (!editing) return;
  setSaving(true);
  try {
    const body = editing === 'procedural'
      ? { procedural_memory: editValue }
      : { user_background: editValue };
    await api.put('/api/user/memory/procedural', body);
    setSaveMsg(t('user.memorySaved'));
    setTimeout(() => setSaveMsg(''), 4000);
    setEditing(null);
    // 重新載入
    const p = await api.get('/api/user/memory/procedural');
    setProcedural(p.data);
  } catch {
    setSaveMsg(t('common.error'));
  } finally {
    setSaving(false);
  }
};
```

在 `procedural_memory` 顯示 div 右上角加入編輯按鈕：
```tsx
<button
  onClick={() => {
    setEditing('procedural');
    setEditValue(procedural?.procedural_memory || '');
  }}
  style={{
    background: 'none', border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-sm)', color: 'var(--color-text-muted)',
    cursor: 'pointer', fontSize: '0.75rem', padding: '0.2rem 0.5rem',
  }}
>
  ✏️ {t('user.editMemory')}
</button>
```

當 `editing === 'procedural'` 時顯示 textarea 和儲存/取消按鈕（同樣結構應用於 `user_background`）。

- [ ] **Step 4：Build 前端確認**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard-frontend
npm run build 2>&1 | tail -10
```

- [ ] **Step 5：Commit**

```bash
git add dashboard/routers/user.py \
        dashboard-frontend/src/pages/admin/user/Memory.tsx \
        dashboard-frontend/src/i18n/locales/en.json \
        dashboard-frontend/src/i18n/locales/zh-TW.json
git commit -m "feat: add self-service procedural memory editing to user Memory page with PUT /api/user/memory/procedural endpoint"
```

---

### Task 14：修復硬寫英文字串與 i18n 動態修改問題（T-1 / T-4）

**Files:**
- Modify: `dashboard-frontend/src/pages/admin/Dashboard.tsx`
- Modify: `dashboard-frontend/src/pages/admin/user/UserStats.tsx`
- Modify: `dashboard-frontend/src/i18n/locales/en.json`
- Modify: `dashboard-frontend/src/i18n/locales/zh-TW.json`

問題 T-1：`Dashboard.tsx` 有 `"Welcome back 👋"`、`"Quick Actions"`、`"Edit Config"` 等硬寫英文字串。
問題 T-4：`UserStats.tsx` 第 58 行使用 `t('guild.activeUsers').replace('Active', 'Active on')` 在中文下完全失效。

- [ ] **Step 1：在 i18n 加入缺少的 Dashboard 翻譯 key**

在 `en.json` 的 `dashboard` 區段加入：
```json
"welcomeBack": "Welcome back 👋",
"quickActions": "Quick Actions",
"editConfig": "Edit Config",
"viewLogs": "View Logs",
"manageBots": "Manage Bot",
"viewStats": "View Stats"
```

在 `zh-TW.json` 的 `dashboard` 區段加入：
```json
"welcomeBack": "歡迎回來 👋",
"quickActions": "快速操作",
"editConfig": "編輯設定",
"viewLogs": "查看日誌",
"manageBots": "管理機器人",
"viewStats": "查看統計"
```

- [ ] **Step 2：更新 `Dashboard.tsx` 改用 i18n**

```tsx
// 在元件頂部加入（若尚未 import）
const { t } = useTranslation();

// 替換硬寫字串
// "Welcome back 👋"  →  {t('dashboard.welcomeBack')}
// "Quick Actions"    →  {t('dashboard.quickActions')}
// "⚙️ Edit Config"  →  ⚙️ {t('dashboard.editConfig')}
```

- [ ] **Step 3：在 i18n 加入 `user.activeOnServers` key**

在 `en.json` 的 `user` 區段加入：
```json
"activeOnServers": "Active on servers"
```

在 `zh-TW.json` 的 `user` 區段加入：
```json
"activeOnServers": "活躍伺服器數"
```

- [ ] **Step 4：修改 `UserStats.tsx` 第 58 行**

將：
```tsx
{ label: t('guild.activeUsers').replace('Active', 'Active on'), value: (data.guild_breakdown?.length || 0) + ' servers', icon: '🏠' },
```

改為：
```tsx
{ label: t('user.activeOnServers'), value: `${data.guild_breakdown?.length || 0}`, icon: '🏠' },
```

- [ ] **Step 5：Build 前端確認**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot/dashboard-frontend
npm run build 2>&1 | tail -10
```

- [ ] **Step 6：Commit**

```bash
git add dashboard-frontend/src/pages/admin/Dashboard.tsx \
        dashboard-frontend/src/pages/admin/user/UserStats.tsx \
        dashboard-frontend/src/i18n/locales/en.json \
        dashboard-frontend/src/i18n/locales/zh-TW.json
git commit -m "fix: replace hardcoded English strings with i18n keys in Dashboard and UserStats, fix broken .replace() i18n pattern"
```

---

## 驗證清單

### 群組 A（Auth）
- [ ] `python3 -c "from dashboard.auth.jwt_handler import _SECRET_KEY; print('key set:', bool(_SECRET_KEY))"` — 回傳 `True`（非隨機 key）
- [ ] Bot 重啟後，持有 refresh token 的用戶不需要重新登入
- [ ] Server admin refresh token 後，`/auth/me` 回傳 `role: "admin"` 且 `guild_ids` 非空
- [ ] 呼叫 `/auth/refresh` 後重新取得的 access token 可正常存取 `/api/guild/*` 端點

### 群組 B（後端）
- [ ] `python3 -c "from dashboard.routers.stats import router; print([r.path for r in router.routes])"` — 不包含 `/guild/{guild_id}/stats`
- [ ] 以 guild admin 身份呼叫 `/api/guild/<id>/stats` — 回傳正常資料而非 403
- [ ] Admin 刪除用戶後，response body 包含 `"qdrant_vectors"` key
- [ ] `dashboard/routers/guild.py` 不再有 `QdrantClient(...)` 直接初始化的程式碼
- [ ] `write_config` 傳入 `{"config": "string"}` 應回傳 400
- [ ] `write_config` 傳入 `{"config": {"unknown_key": 1}}` 應回傳 400

### 群組 C（前端）
- [ ] 斷開後端連線後，Dashboard / Memory / Overview / UserStats 頁面顯示紅色錯誤 banner 而非永久 loading
- [ ] Users 頁面的刪除確認按鈕在請求進行中 disabled 且呈半透明
- [ ] Admin 用戶詳細面板顯示 guild 名稱而非數字 ID
- [ ] `/me/memory` 頁面的 procedural_memory 和 user_background 旁有 ✏️ 編輯按鈕，點擊可展開 textarea 並儲存
- [ ] 切換語言為中文後，Dashboard 首頁顯示「歡迎回來 👋」而非英文
- [ ] `UserStats.tsx` 的活躍伺服器數 label 在中文下正確顯示

---

## 執行順序建議

**群組 A**（Task 1→2→3）必須依序執行，Task 2 完成前不要執行 Task 3。

**群組 B**（Task 4→5→6→7→8→9）各 Task 互相獨立，可平行執行。

**群組 C**（Task 10→11→12→13→14）Task 12 依賴 Task 13（i18n key），建議先完成 Task 13 再做 Task 12，其餘互相獨立。
