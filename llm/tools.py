"""Factory for LangChain tools that auto-loads only @tool-decorated functions.

設計要點:
- 自動載入 `llm/tools/` 資料夾下的模組（若存在）。
- 只收集已由 LangChain 的 `@tool` 裝飾過的 callable 或 BaseTool 實例。
- 不做額外的標準化或權限過濾（使用者 ID 參數保留以便未來擴充）。
- 例外使用 `func.report_error` 非同步回報，失敗時 fallback 為 print。
- 使用快取避免每次呼叫重複掃描模組，以提升效能。
"""

from typing import Any, Iterable, List, Optional, cast
import os
import pkgutil
import importlib
import asyncio
import threading

from langchain.tools import BaseTool
from function import func

# 快取變數：儲存已解析出的 decorated tools 以及對應的檔案最大 mtime
_cached_collected_tools: Optional[List[Any]] = None
_cached_collected_mtime: float = 0.0
_cache_lock = threading.Lock()

def _report_async(exc: Exception, ctx: str) -> None:
    """非同步回報錯誤；失敗時以 print 作為後備輸出。"""
    try:
        asyncio.create_task(func.report_error(exc, ctx))
    except Exception:
        print(f"[llm.tools] report_error failed: {exc} ({ctx})")


def _compute_pkg_dir_mtime(pkg_dir: str) -> float:
    """計算 package 目錄下所有 .py 檔案的最大 mtime，若無檔案回傳 0."""
    try:
        max_mtime = 0.0
        for root, _, files in os.walk(pkg_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                try:
                    path = os.path.join(root, f)
                    m = os.path.getmtime(path)
                    if m > max_mtime:
                        max_mtime = m
                except Exception:
                    # 忽略單一檔案錯誤
                    continue
        return max_mtime
    except Exception as e:
        _report_async(e, "llm.tools: compute_pkg_dir_mtime failed")
        return 0.0


def _discover_tools_package() -> Iterable[Any]:
    """匯入並回傳 llm/tools 下所有模組（若資料夾存在）。"""
    pkg_dir = os.path.join(os.path.dirname(__file__), "tools")
    if not os.path.isdir(pkg_dir):
        return []

    modules = []
    try:
        for finder, name, ispkg in pkgutil.iter_modules([pkg_dir]):
            module_name = f"llm.tools.{name}"
            try:
                mod = importlib.import_module(module_name)
                modules.append(mod)
            except Exception as e:
                _report_async(e, f"llm.tools: import {module_name}")
    except Exception as e:
        _report_async(e, "llm.tools: discovering tools")
    return modules


def _is_decorated_tool(obj: Any) -> bool:
    """檢查物件是否為 LangChain 工具（BaseTool 或被 @tool 裝飾的 callable）。"""
    try:
        if isinstance(obj, BaseTool):
            return True
        if not callable(obj):
            return False

        # 常見標記屬性（若 langchain 有放置標記）
        for attr in ("_is_tool", "is_tool", "__langchain_tool__"):
            if getattr(obj, attr, False):
                return True

        # 檢查是否為 decorator 的 wrapper
        wrapped = getattr(obj, "__wrapped__", None)
        if wrapped is not None:
            mod = getattr(wrapped, "__module__", "")
            if mod and not mod.startswith("builtins"):
                return True

        # 有些 wrapper 的 module 來自 langchain
        module_name = getattr(obj, "__module__", "") or ""
        if "langchain" in module_name.lower():
            return True
    except Exception as e:
        _report_async(e, "llm.tools: _is_decorated_tool failed")
    return False


def _extract_tools_from_module(mod: Any) -> List[Any]:
    """從模組中抽取所有已裝飾為工具的物件。"""
    tools: List[Any] = []
    try:
        for name in dir(mod):
            if name.startswith("_"):
                continue
            try:
                obj = getattr(mod, name)
            except Exception:
                continue
            try:
                if _is_decorated_tool(obj):
                    tools.append(obj)
            except Exception as e:
                _report_async(e, f"llm.tools: checking {name} in {getattr(mod, '__name__', repr(mod))}")
    except Exception as e:
        _report_async(e, f"llm.tools: extract_tools_from_module {getattr(mod, '__name__', repr(mod))}")
    return tools


def _get_user_permissions(user_id: int, guid: int) -> dict:
    """嘗試從專案內部取得該 Discord 使用者的權限資訊。

    此函式嘗試匯入 `cogs.system_prompt.permissions` 模組並呼叫 `get_user_permissions(user_id)`。
    若找不到或呼叫失敗，回傳一個保守的預設權限集 (非 admin / moderator)。
    """
    try:
        from main import bot
        from cogs.system_prompt.permissions import PermissionValidator
        permissions = PermissionValidator(bot)  # type: ignore

        perms = permissions.get_user_permissions(user_id, guid)
        if isinstance(perms, dict):
            return perms
    except Exception as e:
        _report_async(e, "llm.tools: _get_user_permissions")
    return {"is_admin": False, "is_moderator": False}


def get_tools(user_id: int, guid: int) -> List[BaseTool]:
    """根據 Discord 使用者權限回傳可用的 LangChain 工具清單。

    簡易權限策略:
    - tools 可以宣告屬性 `required_permission`（字串, e.g. "admin", "moderator"）。
      若宣告，則只有擁有該權限的使用者才會取得該工具。
    - 若工具沒有宣告 `required_permission`，則預設對所有使用者開放。
    - 權限屬性可以設在 BaseTool 實例或原始 callable 上。

    Args:
        user_id: Discord 使用者 ID

    Returns:
        List[BaseTool]: 可供 LangChain 使用的工具清單（靜態類型上會 cast 為 List[BaseTool]）。
    """
    global _cached_collected_tools, _cached_collected_mtime

    collected: List[Any] = []

    # 檢查是否需要重新掃描工具目錄（基於 mtime）
    pkg_dir = os.path.join(os.path.dirname(__file__), "tools")
    try:
        current_mtime = _compute_pkg_dir_mtime(pkg_dir) if os.path.isdir(pkg_dir) else 0.0
    except Exception:
        current_mtime = 0.0

    with _cache_lock:
        if _cached_collected_tools is None or current_mtime != _cached_collected_mtime:
            # 重新掃描並更新快取
            try:
                temp_collected: List[Any] = []
                for mod in _discover_tools_package():
                    temp_collected.extend(_extract_tools_from_module(mod))
                _cached_collected_tools = temp_collected
                _cached_collected_mtime = current_mtime
            except Exception as e:
                _report_async(e, "llm.tools: scanning tools for cache")
                _cached_collected_tools = _cached_collected_tools or []

        # 使用快取結果
        collected = list(_cached_collected_tools or [])

    # 根據使用者權限過濾
    perms = _get_user_permissions(user_id, guid)
    result: List[Any] = []
    for t in collected:
        try:
            required = getattr(t, "required_permission", None)
            # 若 tool 為 BaseTool，某些實作把 meta 放在 .name 或 .description；我們僅依 required_permission 篩選
            if required is None:
                result.append(t)
                continue
            # required can be comma separated permissions
            if isinstance(required, str):
                required_set = {p.strip().lower() for p in required.split(",") if p.strip()}
            else:
                # 若工具以 list/iterable 指定權限
                try:
                    required_set = {str(p).lower() for p in required}
                except Exception:
                    required_set = set()

            allowed = False
            if "admin" in required_set and perms.get("is_admin"):
                allowed = True
            if "moderator" in required_set and perms.get("is_moderator"):
                allowed = True
            # 未滿足任何 required_permission 則跳過
            if allowed:
                result.append(t)
        except Exception as e:
            _report_async(e, f"llm.tools: filtering tool {getattr(t, '__name__', repr(t))}")

    # 最後嘗試轉型為 List[BaseTool] 以符合呼叫端預期；實際上 LangChain 接受 callable 或 BaseTool
    try:
        return cast(List[BaseTool], result)
    except Exception as e:
        _report_async(e, "llm.tools: casting result to List[BaseTool]")
        # 若 cast 失敗，仍回傳結果（type checker 層面的保護）
        return result  # type: ignore