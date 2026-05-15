# Dashboard 記憶管理強化實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 Dashboard 新增三個功能：記憶統計補完（Stats.tsx 顯示記憶系統指標）、記憶細節查看（逐筆查看並刪除情節記憶）、使用者管理（Bot Owner 管理所有使用者記憶資料）。

**Architecture:** 後端在 `ProceduralStorage` 加入 `get_all_users()` / `get_users_count()`、在 `EpisodicStorage` 加入 `get_total_count()`、在 `SQLiteUserManager` 暴露 `get_all_users()`；`admin.py` 新增三個使用者管理端點；`user.py` 新增逐 guild 刪除端點；前端 `Stats.tsx` 新增記憶統計區塊、新建 `Users.tsx` 管理頁面、增強 `Memory.tsx` 的逐筆刪除。

**Tech Stack:** Python 3.11 / FastAPI / aiosqlite / SQLite（同步 DatabaseConnection）、React 19 / TypeScript / TailwindCSS / Framer Motion / Recharts

---

## 檔案異動總覽

| 操作 | 路徑 |
|------|------|
| Modify | `cogs/memory/db/procedural_storage.py` |
| Modify | `cogs/memory/db/episodic_storage.py` |
| Modify | `cogs/memory/users/manager.py` |
| Modify | `dashboard/routers/admin.py` |
| Modify | `dashboard/routers/user.py` |
| Modify | `dashboard-frontend/src/pages/admin/Stats.tsx` |
| Create | `dashboard-frontend/src/pages/admin/Users.tsx` |
| Modify | `dashboard-frontend/src/pages/admin/user/Memory.tsx` |
| Modify | `dashboard-frontend/src/App.tsx` |
| Modify | `dashboard-frontend/src/components/Sidebar.tsx` |
| Create | `tests/dashboard/test_memory_admin.py` |

---

## Task 1：ProceduralStorage — 新增 `get_all_users()` 與 `get_users_count()`

**Files:**
- Modify: `cogs/memory/db/procedural_storage.py`
- Create: `tests/dashboard/test_memory_admin.py`

- [ ] **Step 1：建立測試檔，寫入兩個失敗測試**

建立 `tests/dashboard/__init__.py`（空白），再建立 `tests/dashboard/test_memory_admin.py`：

```python
"""Tests for new ProceduralStorage methods added for dashboard memory management."""
import json
import asyncio
import tempfile
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------- helpers ----------

def _make_storage(db_path: str):
    """Build a real ProceduralStorage backed by a temp SQLite file."""
    from cogs.memory.db.connection import DatabaseConnection
    from cogs.memory.db.procedural_storage import ProceduralStorage
    db = DatabaseConnection(db_path)
    return ProceduralStorage(db)


async def _seed_users(storage, count: int = 3):
    """Insert `count` test users via update_user_data."""
    for i in range(count):
        await storage.update_user_data(
            discord_id=f"user_{i}",
            discord_name=f"TestUser{i}",
            procedural_memory=f"memory_{i}",
            user_background=f"bg_{i}",
            display_names=[f"nick_{i}"],
        )


# ---------- ProceduralStorage tests ----------

@pytest.mark.asyncio
async def test_get_all_users_returns_list():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 3)
        users = await storage.get_all_users()
        assert isinstance(users, list)
        assert len(users) == 3
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_get_users_count_returns_int():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 5)
        count = await storage.get_users_count()
        assert count == 5
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2：執行測試，確認失敗**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -m pytest tests/dashboard/test_memory_admin.py::test_get_all_users_returns_list tests/dashboard/test_memory_admin.py::test_get_users_count_returns_int -v
```

預期：`AttributeError: 'ProceduralStorage' object has no attribute 'get_all_users'`

- [ ] **Step 3：在 `procedural_storage.py` 的 `get_config` 方法之前插入兩個新方法**

在 `cogs/memory/db/procedural_storage.py` 第 213 行（`get_config` 方法）前插入：

```python
    async def get_all_users(self, limit: int = 500, offset: int = 0) -> List[UserInfo]:
        """Return all users ordered by creation date (newest first)."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT discord_id, discord_name, display_names,
                           procedural_memory, user_background, created_at
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                rows = cursor.fetchall()

            users: List[UserInfo] = []
            for row in rows:
                display_names: List[str] = []
                if row["display_names"]:
                    try:
                        parsed = json.loads(row["display_names"])
                        display_names = parsed if isinstance(parsed, list) else [str(parsed)]
                    except Exception:
                        display_names = [row["display_names"]]

                created_at = None
                if row["created_at"]:
                    try:
                        created_at = datetime.fromisoformat(row["created_at"])
                    except Exception:
                        try:
                            created_at = datetime.fromtimestamp(float(row["created_at"]))
                        except Exception:
                            created_at = None

                users.append(UserInfo(
                    discord_id=str(row["discord_id"]),
                    discord_name=row["discord_name"] or "",
                    display_names=display_names,
                    procedural_memory=row["procedural_memory"],
                    user_background=row["user_background"],
                    created_at=created_at,
                ))
            return users
        except Exception as e:
            await func.report_error(e, "get_all_users failed")
            return []

    async def get_users_count(self) -> int:
        """Return total number of users in the database."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM users")
                row = cursor.fetchone()
                return int(row["count"]) if row else 0
        except Exception as e:
            await func.report_error(e, "get_users_count failed")
            return 0

```

- [ ] **Step 4：執行測試，確認通過**

```bash
python -m pytest tests/dashboard/test_memory_admin.py::test_get_all_users_returns_list tests/dashboard/test_memory_admin.py::test_get_users_count_returns_int -v
```

預期：兩個測試 PASS

- [ ] **Step 5：Commit**

```bash
git add cogs/memory/db/procedural_storage.py tests/dashboard/__init__.py tests/dashboard/test_memory_admin.py
git commit -m "feat: add get_all_users and get_users_count to ProceduralStorage"
```

---

## Task 2：EpisodicStorage — 新增 `get_total_count()`

**Files:**
- Modify: `cogs/memory/db/episodic_storage.py`
- Modify: `tests/dashboard/test_memory_admin.py`

- [ ] **Step 1：在測試檔末尾新增失敗測試**

在 `tests/dashboard/test_memory_admin.py` 末尾追加：

```python
# ---------- EpisodicStorage tests ----------

@pytest.mark.asyncio
async def test_episodic_get_total_count():
    from cogs.memory.db.connection import DatabaseConnection
    from cogs.memory.db.episodic_storage import EpisodicStorage

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseConnection(db_path)
        storage = EpisodicStorage(db)
        # Insert two channel states
        await storage.update_channel_memory_state("ch_1", 5, "msg_1", None, None)
        await storage.update_channel_memory_state("ch_2", 3, "msg_2", None, None)
        count = await storage.get_total_count()
        assert count == 2
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2：執行測試，確認失敗**

```bash
python -m pytest tests/dashboard/test_memory_admin.py::test_episodic_get_total_count -v
```

預期：`AttributeError: 'EpisodicStorage' object has no attribute 'get_total_count'`

- [ ] **Step 3：在 `episodic_storage.py` 末尾（`_update_cache` 之前）新增方法**

開啟 `cogs/memory/db/episodic_storage.py`，在最後一個 `async def` 方法之後插入：

```python
    async def get_total_count(self) -> int:
        """Return total number of channel memory states stored."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM channel_memory_state"
                )
                row = cursor.fetchone()
                return int(row["count"]) if row else 0
        except Exception as e:
            await func.report_error(e, "get_total_count failed")
            return 0
```

確認 `func` 和 `DatabaseConnection` 已在 `episodic_storage.py` 中被 import（參照現有 import 段落）。

- [ ] **Step 4：執行測試，確認通過**

```bash
python -m pytest tests/dashboard/test_memory_admin.py::test_episodic_get_total_count -v
```

預期：PASS

- [ ] **Step 5：Commit**

```bash
git add cogs/memory/db/episodic_storage.py tests/dashboard/test_memory_admin.py
git commit -m "feat: add get_total_count to EpisodicStorage"
```

---

## Task 3：SQLiteUserManager — 暴露 `get_all_users()`

**Files:**
- Modify: `cogs/memory/users/manager.py`
- Modify: `tests/dashboard/test_memory_admin.py`

- [ ] **Step 1：在測試檔末尾新增失敗測試**

```python
# ---------- SQLiteUserManager tests ----------

@pytest.mark.asyncio
async def test_user_manager_get_all_users():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = _make_storage(db_path)
        await _seed_users(storage, 4)
        from cogs.memory.users.manager import SQLiteUserManager
        manager = SQLiteUserManager(storage)
        users = await manager.get_all_users()
        assert len(users) == 4
        assert all(hasattr(u, "discord_id") for u in users)
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2：執行測試，確認失敗**

```bash
python -m pytest tests/dashboard/test_memory_admin.py::test_user_manager_get_all_users -v
```

預期：`AttributeError: 'SQLiteUserManager' object has no attribute 'get_all_users'`

- [ ] **Step 3：在 `manager.py` 的 `search_users_by_display_name` 方法之後插入**

在 `cogs/memory/users/manager.py` 第 147 行（`search_users_by_display_name` 回傳後）後插入：

```python
    async def get_all_users(self, limit: int = 500, offset: int = 0) -> List[UserInfo]:
        """Return all users from storage; delegates to storage.get_all_users if available."""
        try:
            if hasattr(self.storage, "get_all_users"):
                return await self.storage.get_all_users(limit=limit, offset=offset)
            return []
        except Exception as e:
            await func.report_error(e, "SQLiteUserManager.get_all_users failed")
            return []

    async def get_users_count(self) -> int:
        """Return total user count from storage."""
        try:
            if hasattr(self.storage, "get_users_count"):
                return await self.storage.get_users_count()
            return 0
        except Exception as e:
            await func.report_error(e, "SQLiteUserManager.get_users_count failed")
            return 0
```

- [ ] **Step 4：執行測試，確認通過**

```bash
python -m pytest tests/dashboard/test_memory_admin.py::test_user_manager_get_all_users -v
```

預期：PASS

- [ ] **Step 5：執行所有測試確認無迴歸**

```bash
python -m pytest tests/dashboard/test_memory_admin.py -v
```

預期：所有測試 PASS

- [ ] **Step 6：Commit**

```bash
git add cogs/memory/users/manager.py tests/dashboard/test_memory_admin.py
git commit -m "feat: expose get_all_users and get_users_count in SQLiteUserManager"
```

---

## Task 4：後端 — Admin API 使用者管理端點

**Files:**
- Modify: `dashboard/routers/admin.py`

在 `admin.py` 末尾（`write_config` 之後）插入以下內容。

- [ ] **Step 1：新增 import**

在 `admin.py` 頂部的 import 區段加入：

```python
import aiosqlite
from pathlib import Path
from fastapi import Query
```

（確認 `aiosqlite`、`Path`、`Query` 尚未 import，若已有則略過）

- [ ] **Step 2：在 `admin.py` 末尾追加三個端點**

```python
# ── User Management (Bot Owner) ───────────────────────────────────────

_PROCEDURAL_DB = Path(ROOT_DIR) / "data" / "memory" / "procedural.db"


@router.get("/users")
async def list_users(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """List all users with procedural memory data (Bot Owner only)."""
    if not _PROCEDURAL_DB.exists():
        return JSONResponse({"users": [], "total": 0})

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row
            if search:
                pattern = f"%{search}%"
                cursor = await db.execute(
                    """
                    SELECT discord_id, discord_name, display_names, created_at,
                           CASE WHEN procedural_memory IS NOT NULL THEN 1 ELSE 0 END as has_memory
                    FROM users
                    WHERE discord_name LIKE ? OR display_names LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (pattern, pattern, limit, offset),
                )
                count_cursor = await db.execute(
                    "SELECT COUNT(*) FROM users WHERE discord_name LIKE ? OR display_names LIKE ?",
                    (pattern, pattern),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT discord_id, discord_name, display_names, created_at,
                           CASE WHEN procedural_memory IS NOT NULL THEN 1 ELSE 0 END as has_memory
                    FROM users
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
                count_cursor = await db.execute("SELECT COUNT(*) FROM users")

            rows = await cursor.fetchall()
            total = (await count_cursor.fetchone())[0]

    except Exception as exc:
        log.error(f"list_users failed: {exc}")
        raise HTTPException(status_code=503, detail="Memory database unavailable")

    import json as _json
    users_out = []
    for row in rows:
        display_names = []
        try:
            display_names = _json.loads(row["display_names"] or "[]")
        except Exception:
            pass
        users_out.append({
            "discord_id": row["discord_id"],
            "discord_name": row["discord_name"],
            "display_names": display_names,
            "created_at": row["created_at"],
            "has_memory": bool(row["has_memory"]),
        })

    return JSONResponse({"users": users_out, "total": total, "limit": limit, "offset": offset})


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Get full memory details for a specific user (Bot Owner only)."""
    if not _PROCEDURAL_DB.exists():
        raise HTTPException(status_code=404, detail="Memory database not found")

    import json as _json

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            db.row_factory = aiosqlite.Row

            user_cursor = await db.execute(
                "SELECT discord_id, discord_name, display_names, procedural_memory, user_background, created_at "
                "FROM users WHERE discord_id = ?",
                (user_id,),
            )
            user_row = await user_cursor.fetchone()

            stats_cursor = await db.execute(
                "SELECT guild_id, total_messages, streak_days, last_active_at, first_message_at "
                "FROM user_stats WHERE user_id = ? ORDER BY total_messages DESC",
                (user_id,),
            )
            stats_rows = await stats_cursor.fetchall()

    except Exception as exc:
        log.error(f"get_user_detail failed for {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database unavailable")

    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")

    display_names = []
    try:
        display_names = _json.loads(user_row["display_names"] or "[]")
    except Exception:
        pass

    guild_stats = [
        {
            "guild_id": row["guild_id"],
            "total_messages": row["total_messages"],
            "streak_days": row["streak_days"],
            "last_active_at": row["last_active_at"],
            "first_message_at": row["first_message_at"],
        }
        for row in stats_rows
    ]

    return JSONResponse({
        "discord_id": user_row["discord_id"],
        "discord_name": user_row["discord_name"],
        "display_names": display_names,
        "procedural_memory": user_row["procedural_memory"],
        "user_background": user_row["user_background"],
        "created_at": user_row["created_at"],
        "guild_stats": guild_stats,
    })


@router.delete("/users/{user_id}/memory")
async def admin_delete_user_memory(
    user_id: str,
    request: Request,
    user: dict = Depends(require_owner),
) -> JSONResponse:
    """Delete all memory data for a specific user (Bot Owner only)."""
    body: dict = await request.json()
    if not body.get("confirm"):
        raise HTTPException(status_code=400, detail="Requires {'confirm': true}")

    deleted: dict[str, int] = {}
    stats_db = Path(ROOT_DIR) / "data" / "stats" / "stats.db"

    if _PROCEDURAL_DB.exists():
        try:
            async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
                c = await db.execute("DELETE FROM users WHERE discord_id = ?", (user_id,))
                deleted["procedural_users"] = c.rowcount
                c = await db.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
                deleted["user_stats"] = c.rowcount
                await db.commit()
        except Exception as exc:
            log.error(f"admin_delete_user_memory failed for {user_id}: {exc}")
            raise HTTPException(status_code=503, detail="Failed to delete user memory")

    if stats_db.exists():
        try:
            async with aiosqlite.connect(str(stats_db)) as db:
                c = await db.execute("DELETE FROM message_events WHERE user_id = ?", (user_id,))
                deleted["message_events"] = c.rowcount
                c = await db.execute("DELETE FROM command_events WHERE user_id = ?", (user_id,))
                deleted["command_events"] = c.rowcount
                await db.commit()
        except Exception as exc:
            log.warning(f"admin stats deletion failed for {user_id}: {exc}")

    log.info(f"Admin GDPR deletion for user {user_id} by owner: {deleted}")
    return JSONResponse({"detail": "User memory deleted", "user_id": user_id, "deleted_rows": deleted})
```

- [ ] **Step 3：啟動後端，確認端點出現在 `/docs`**

```bash
cd /media/ubuntu/4TB-HDD/ziyue/PigPig-discord-LLM-bot
python -c "from dashboard.routers.admin import router; print([r.path for r in router.routes])"
```

預期輸出包含 `/api/admin/users`、`/api/admin/users/{user_id}`

- [ ] **Step 4：Commit**

```bash
git add dashboard/routers/admin.py
git commit -m "feat: add admin user management endpoints (list, detail, delete)"
```

---

## Task 5：後端 — User API 新增逐 guild 刪除情節記憶

**Files:**
- Modify: `dashboard/routers/user.py`

- [ ] **Step 1：在 `user.py` 的 `delete_user_memory` 函數之前插入新端點**

在 `# ── GDPR Delete` 區塊（第 232 行）前插入：

```python
# ── Per-Guild Episodic Deletion ───────────────────────────────────────

@router.delete("/memory/episodic/{guild_id}")
async def delete_episodic_by_guild(
    guild_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Delete the authenticated user's episodic memory for a specific guild.

    Removes only the ``user_stats`` row matching (user_id, guild_id).
    Does not affect procedural memory or other guilds.

    Args:
        guild_id: Discord guild ID to delete episodic memory for.
        user: Authenticated user payload (JWT).

    Returns:
        JSON confirming deletion.
    """
    user_id: str = user["sub"]

    if not _PROCEDURAL_DB.exists():
        raise HTTPException(status_code=404, detail="Memory database not found")

    try:
        async with aiosqlite.connect(str(_PROCEDURAL_DB)) as db:
            cursor = await db.execute(
                "DELETE FROM user_stats WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
            await db.commit()
            deleted = cursor.rowcount
    except Exception as exc:
        log.error(f"delete_episodic_by_guild failed for {user_id}/{guild_id}: {exc}")
        raise HTTPException(status_code=503, detail="Memory database temporarily unavailable")

    if deleted == 0:
        raise HTTPException(status_code=404, detail="No episodic memory found for this guild")

    log.info(f"Deleted episodic memory for user {user_id} in guild {guild_id}")
    return JSONResponse({
        "detail": "Episodic memory deleted for guild",
        "user_id": user_id,
        "guild_id": guild_id,
    })

```

- [ ] **Step 2：確認端點清單**

```bash
python -c "from dashboard.routers.user import router; print([r.path for r in router.routes])"
```

預期輸出包含 `/api/user/memory/episodic/{guild_id}`（DELETE）

- [ ] **Step 3：Commit**

```bash
git add dashboard/routers/user.py
git commit -m "feat: add per-guild episodic memory deletion endpoint"
```

---

## Task 6：前端 — Stats.tsx 補完記憶統計區塊

**Files:**
- Modify: `dashboard-frontend/src/pages/admin/Stats.tsx`

- [ ] **Step 1：更新 `Stats.tsx` — 加入記憶統計狀態與 API 呼叫**

將 `Stats.tsx` 第 14–31 行（`useState` 宣告與 `useEffect`）替換為：

```tsx
  const [period, setPeriod] = useState('30d');
  const [globalStats, setGlobalStats] = useState<any>(null);
  const [modelStats, setModelStats] = useState<any>(null);
  const [memoryStats, setMemoryStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/api/admin/stats/global?period=${period}`),
      api.get(`/api/admin/stats/models?period=${period}`),
      api.get('/api/admin/stats/memory'),
    ])
      .then(([g, m, mem]) => {
        setGlobalStats(g.data);
        setModelStats(m.data);
        setMemoryStats(mem.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [period]);
```

- [ ] **Step 2：在 Stats.tsx 末尾的 `</div>` 之前（第 178 行前）插入記憶統計區塊**

在最後的 `</div>` 結束標籤（包住 Model Usage 的那個）之後、函式的最終 `</div>` 之前插入：

```tsx
      {/* Memory Stats */}
      <motion.div
        className="glass-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        style={{ padding: '1.5rem', marginTop: '1.5rem' }}
      >
        <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem' }}>🧠 Memory System</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
          {[
            { label: 'Users with Memory', value: memoryStats?.procedural_users ?? '—', icon: '👤' },
            { label: 'Channel Segments',  value: memoryStats?.episodic_total ?? '—',   icon: '💾' },
            { label: 'Vector Collections', value: memoryStats?.vector_collections ?? '—', icon: '🔮' },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                padding: '1rem',
                background: 'rgba(139,92,246,0.08)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(139,92,246,0.2)',
              }}
            >
              <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginBottom: '0.5rem' }}>
                {item.icon} {item.label}
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 700 }}>{item.value}</div>
            </div>
          ))}
        </div>
      </motion.div>
```

- [ ] **Step 3：Commit**

```bash
git add dashboard-frontend/src/pages/admin/Stats.tsx
git commit -m "feat: add memory stats section to Stats page"
```

---

## Task 7：前端 — 新建 Users.tsx 使用者管理頁面

**Files:**
- Create: `dashboard-frontend/src/pages/admin/Users.tsx`

- [ ] **Step 1：建立 `Users.tsx`**

建立 `dashboard-frontend/src/pages/admin/Users.tsx`：

```tsx
import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import api from '../../lib/api';

interface UserSummary {
  discord_id: string;
  discord_name: string;
  display_names: string[];
  created_at: string | null;
  has_memory: boolean;
}

interface UserDetail {
  discord_id: string;
  discord_name: string;
  display_names: string[];
  procedural_memory: string | null;
  user_background: string | null;
  created_at: string | null;
  guild_stats: {
    guild_id: string;
    total_messages: number;
    streak_days: number;
    last_active_at: string | null;
    first_message_at: string | null;
  }[];
}

export default function Users() {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(0);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteMsg, setDeleteMsg] = useState('');
  const LIMIT = 50;

  // Debounce search input
  const handleSearchChange = (val: string) => {
    setSearch(val);
    clearTimeout((handleSearchChange as any)._t);
    (handleSearchChange as any)._t = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(0);
    }, 400);
  };

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['admin-users', debouncedSearch, page],
    queryFn: () =>
      api
        .get(`/api/admin/users?limit=${LIMIT}&offset=${page * LIMIT}&search=${encodeURIComponent(debouncedSearch)}`)
        .then((r) => r.data as { users: UserSummary[]; total: number }),
  });

  const openDetail = async (userId: string) => {
    setDetailLoading(true);
    try {
      const res = await api.get(`/api/admin/users/${userId}`);
      setSelectedUser(res.data as UserDetail);
    } catch {
      setSelectedUser(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDelete = async (userId: string) => {
    try {
      await api.delete(`/api/admin/users/${userId}/memory`, { data: { confirm: true } });
      setDeleteMsg(`✅ Deleted memory for user ${userId}`);
      setDeleteConfirm(null);
      setSelectedUser(null);
      refetch();
    } catch {
      setDeleteMsg('❌ Deletion failed');
    }
  };

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700 }}>👥 User Management</h1>
        <span style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          {data?.total ?? 0} users with memory data
        </span>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search by name..."
        value={search}
        onChange={(e) => handleSearchChange(e.target.value)}
        style={{
          width: '100%',
          padding: '0.625rem 1rem',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-border)',
          background: 'var(--color-bg-secondary)',
          color: 'var(--color-text-primary)',
          fontSize: '0.875rem',
          marginBottom: '1.5rem',
          outline: 'none',
        }}
      />

      {deleteMsg && (
        <div style={{ padding: '0.75rem 1rem', borderRadius: 'var(--radius-md)', background: 'rgba(16,185,129,0.1)',
          border: '1px solid rgba(16,185,129,0.3)', color: '#10b981', fontSize: '0.875rem', marginBottom: '1rem' }}>
          {deleteMsg}
        </div>
      )}

      {/* User Table */}
      <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
              {['Discord ID', 'Name', 'Display Names', 'Created', 'Memory', ''].map((h) => (
                <th key={h} style={{ padding: '0.875rem 1rem', textAlign: 'left',
                  color: 'var(--color-text-muted)', fontWeight: 500, fontSize: '0.75rem', textTransform: 'uppercase' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>Loading...</td></tr>
            ) : (data?.users ?? []).map((u, i) => (
              <motion.tr
                key={u.discord_id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.03 }}
                style={{ borderBottom: '1px solid rgba(148,163,184,0.06)', cursor: 'pointer' }}
                onClick={() => openDetail(u.discord_id)}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(148,163,184,0.05)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <td style={{ padding: '0.875rem 1rem', fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                  {u.discord_id}
                </td>
                <td style={{ padding: '0.875rem 1rem', fontWeight: 500 }}>{u.discord_name || '—'}</td>
                <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                  {u.display_names.slice(0, 2).join(', ')}{u.display_names.length > 2 ? ` +${u.display_names.length - 2}` : ''}
                </td>
                <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td style={{ padding: '0.875rem 1rem' }}>
                  <span style={{
                    padding: '0.2rem 0.5rem', borderRadius: '9999px', fontSize: '0.7rem', fontWeight: 600,
                    background: u.has_memory ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.1)',
                    color: u.has_memory ? '#10b981' : 'var(--color-text-muted)',
                  }}>
                    {u.has_memory ? 'Yes' : 'No'}
                  </span>
                </td>
                <td style={{ padding: '0.875rem 1rem' }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(u.discord_id); }}
                    style={{
                      padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem',
                      background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
                      color: '#f43f5e', cursor: 'pointer',
                    }}
                  >
                    Delete
                  </button>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem' }}>
          <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
            style={{ padding: '0.4rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
              background: 'transparent', color: page === 0 ? 'var(--color-text-muted)' : 'var(--color-text-primary)', cursor: page === 0 ? 'default' : 'pointer' }}>
            ←
          </button>
          <span style={{ padding: '0.4rem 0.875rem', color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
            {page + 1} / {totalPages}
          </span>
          <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
            style={{ padding: '0.4rem 0.875rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
              background: 'transparent', color: page >= totalPages - 1 ? 'var(--color-text-muted)' : 'var(--color-text-primary)', cursor: page >= totalPages - 1 ? 'default' : 'pointer' }}>
            →
          </button>
        </div>
      )}

      {/* Delete Confirm Modal */}
      <AnimatePresence>
        {deleteConfirm && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
            onClick={() => setDeleteConfirm(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
              className="glass-card"
              style={{ padding: '2rem', width: 380, maxWidth: '90vw' }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '0.5rem', color: '#f43f5e' }}>
                ⚠️ Delete User Memory
              </h3>
              <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
                This will permanently delete all memory data for user <code style={{ color: 'var(--color-text-primary)' }}>{deleteConfirm}</code>.
                This action cannot be undone.
              </p>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                <button onClick={() => setDeleteConfirm(null)}
                  style={{ padding: '0.5rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)',
                    background: 'transparent', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
                  Cancel
                </button>
                <button onClick={() => handleDelete(deleteConfirm)}
                  style={{ padding: '0.5rem 1rem', borderRadius: 'var(--radius-sm)', border: 'none',
                    background: '#f43f5e', color: 'white', cursor: 'pointer', fontWeight: 600 }}>
                  Delete Memory
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* User Detail Side Panel */}
      <AnimatePresence>
        {(selectedUser || detailLoading) && (
          <motion.div
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, maxWidth: '90vw',
              background: 'var(--color-bg-secondary)', borderLeft: '1px solid var(--color-border)',
              zIndex: 50, overflowY: 'auto', padding: '1.5rem',
            }}
          >
            <button onClick={() => setSelectedUser(null)}
              style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer',
                fontSize: '1.25rem', marginBottom: '1rem' }}>
              ✕
            </button>
            {detailLoading ? (
              <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', paddingTop: '4rem' }}>Loading...</div>
            ) : selectedUser && (
              <>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                  {selectedUser.discord_name || selectedUser.discord_id}
                </h2>
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem', marginBottom: '1.5rem', fontFamily: 'monospace' }}>
                  ID: {selectedUser.discord_id}
                </p>

                {selectedUser.display_names.length > 0 && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>Display Names</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                      {selectedUser.display_names.map((n) => (
                        <span key={n} style={{ padding: '0.2rem 0.5rem', borderRadius: '9999px', fontSize: '0.8125rem',
                          background: 'rgba(59,130,246,0.1)', color: 'var(--color-accent-blue)' }}>{n}</span>
                      ))}
                    </div>
                  </div>
                )}

                {selectedUser.procedural_memory && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>Procedural Memory</div>
                    <div style={{ padding: '0.875rem', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-md)',
                      fontSize: '0.8125rem', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                      {selectedUser.procedural_memory}
                    </div>
                  </div>
                )}

                {selectedUser.user_background && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.5rem' }}>User Background</div>
                    <div style={{ padding: '0.875rem', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-md)',
                      fontSize: '0.8125rem', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                      {selectedUser.user_background}
                    </div>
                  </div>
                )}

                {selectedUser.guild_stats.length > 0 && (
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textTransform: 'uppercase',
                      letterSpacing: '0.05em', marginBottom: '0.75rem' }}>Guild Activity ({selectedUser.guild_stats.length})</div>
                    {selectedUser.guild_stats.map((gs) => (
                      <div key={gs.guild_id} style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.15)',
                        borderRadius: 'var(--radius-md)', marginBottom: '0.5rem', fontSize: '0.8125rem' }}>
                        <div style={{ fontFamily: 'monospace', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>{gs.guild_id}</div>
                        <div style={{ display: 'flex', gap: '1rem', marginTop: '0.375rem', flexWrap: 'wrap' }}>
                          <span>💬 {gs.total_messages} msgs</span>
                          <span>🔥 {gs.streak_days}d streak</span>
                          {gs.last_active_at && (
                            <span style={{ color: 'var(--color-text-muted)' }}>
                              Last: {new Date(gs.last_active_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => setDeleteConfirm(selectedUser.discord_id)}
                  style={{ width: '100%', padding: '0.625rem', borderRadius: 'var(--radius-md)',
                    background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
                    color: '#f43f5e', cursor: 'pointer', fontWeight: 600, fontSize: '0.875rem' }}>
                  🗑️ Delete This User's Memory
                </button>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2：Commit**

```bash
git add dashboard-frontend/src/pages/admin/Users.tsx
git commit -m "feat: create Users management page for Bot Owner"
```

---

## Task 8：前端 — Memory.tsx 增加逐 guild 刪除

**Files:**
- Modify: `dashboard-frontend/src/pages/admin/user/Memory.tsx`

- [ ] **Step 1：讀取現有 Memory.tsx 確認結構**

```bash
cat -n dashboard-frontend/src/pages/admin/user/Memory.tsx
```

- [ ] **Step 2：在情節記憶每個 guild 卡片右上角加入刪除按鈕**

找到渲染 guild 記錄的地方（`records.map` 迴圈），在每張卡片中加入刪除按鈕。找到渲染 `record.guild_id` 的父元素，加入刪除功能：

在 `Memory.tsx` 頂部 import 區加入：

```tsx
import { useState } from 'react';
import api from '../../../lib/api';
```

（如果已有 useState import，只加 api import）

在元件頂層加入狀態：

```tsx
const [deletingGuild, setDeletingGuild] = useState<string | null>(null);
const [deleteError, setDeleteError] = useState('');
```

在 `records.map` 每個 guild 卡片的右上角（guild_id 標題行）旁加入刪除按鈕：

```tsx
<button
  disabled={deletingGuild === record.guild_id}
  onClick={async () => {
    if (!confirm(`Delete episodic memory for guild ${record.guild_id}?`)) return;
    setDeletingGuild(record.guild_id);
    setDeleteError('');
    try {
      await api.delete(`/api/user/memory/episodic/${record.guild_id}`);
      refetch(); // 重新載入記憶列表
    } catch {
      setDeleteError('Delete failed');
    } finally {
      setDeletingGuild(null);
    }
  }}
  style={{
    padding: '0.2rem 0.5rem',
    fontSize: '0.7rem',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid rgba(244,63,94,0.3)',
    background: 'rgba(244,63,94,0.08)',
    color: '#f43f5e',
    cursor: 'pointer',
    opacity: deletingGuild === record.guild_id ? 0.5 : 1,
  }}
>
  {deletingGuild === record.guild_id ? '...' : '🗑️'}
</button>
```

若 `refetch` 不在 scope 中，改用 `window.location.reload()`，或在元件中使用 `useQuery` + 其 `refetch`。

- [ ] **Step 3：Commit**

```bash
git add dashboard-frontend/src/pages/admin/user/Memory.tsx
git commit -m "feat: add per-guild episodic memory deletion to Memory page"
```

---

## Task 9：前端 — 更新路由與側邊欄

**Files:**
- Modify: `dashboard-frontend/src/App.tsx`
- Modify: `dashboard-frontend/src/components/Sidebar.tsx`

- [ ] **Step 1：在 App.tsx 加入 Users 頁面 import 與路由**

在 `App.tsx` 的 import 區（第 11 行後）加入：

```tsx
import Users from './pages/admin/Users';
```

在 `/admin/update` 路由（第 55 行）之後加入：

```tsx
            <Route path="/admin/users" element={<Users />} />
```

- [ ] **Step 2：在 Sidebar.tsx 加入 Users 導航項目**

在 `Sidebar.tsx` 的 `NAV_ITEMS` 陣列（第 16 行）中，在 `update` 項目之後加入：

```tsx
    { path: '/admin/users', label: 'Users', icon: '👥' },
```

- [ ] **Step 3：Build 前端確認無 TypeScript 錯誤**

```bash
cd dashboard-frontend
npm run build
```

預期：Build 成功，無錯誤。若有類型錯誤，依錯誤訊息修正。

- [ ] **Step 4：Commit**

```bash
git add dashboard-frontend/src/App.tsx dashboard-frontend/src/components/Sidebar.tsx
git commit -m "feat: add Users page to routing and sidebar navigation"
```

---

## 驗證清單

- [ ] `python -m pytest tests/dashboard/test_memory_admin.py -v` — 所有後端測試通過
- [ ] 開啟 Dashboard → Stats 頁面，確認底部出現 Memory System 統計卡片，顯示 procedural_users、episodic_total、vector_collections 數值
- [ ] Sidebar 出現 👥 Users 項目，點擊進入 `/admin/users`
- [ ] Users 頁面顯示使用者列表，搜尋框可過濾，點擊行展開側邊詳情面板
- [ ] 詳情面板顯示 procedural_memory、user_background、guild activity
- [ ] 點擊 Delete Memory 按鈕，確認對話框出現，確認後使用者從列表中消失
- [ ] 進入 `/me/memory` 的情節記憶 tab，每個 guild 卡片右側出現 🗑️ 刪除按鈕
- [ ] 刪除特定 guild 的情節記憶後，該卡片從列表消失
- [ ] 以非 Bot Owner 身份呼叫 `GET /api/admin/users` 應回傳 403
