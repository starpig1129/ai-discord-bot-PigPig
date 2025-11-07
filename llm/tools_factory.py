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

import discord
import pkgutil
import importlib
import asyncio
import threading
import logging
logger = logging.getLogger(__name__)

from langchain_core.tools import StructuredTool,BaseTool
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
    tools_py = os.path.join(os.path.dirname(__file__), "tools.py")

    # 非破壞性 debug 日誌：紀錄是否存在 llm/tools.py 與 llm/tools/ 資料夾
    try:
        logger.debug(
            "llm.tools debug: tools_py exists=%s, tools_dir exists=%s, pkg_dir=%s",
            os.path.isfile(tools_py),
            os.path.isdir(pkg_dir),
            pkg_dir,
        )
    except Exception:
        # 若 logger 尚未正確建立，回退到 print（不改變程式行為）
        try:
            print(
                f"[llm.tools debug] tools_py exists={os.path.isfile(tools_py)}, "
                f"tools_dir exists={os.path.isdir(pkg_dir)}, pkg_dir={pkg_dir}"
            )
        except Exception:
            pass

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


def _extract_tools_from_module(mod: Any, runtime: "OrchestratorRequest") -> List[Any]:
    """從模組中以「get_tools()」收集工具。
    
    策略：
    - 若模組提供 module-level get_tools()，則呼叫它並使用回傳的同步 list。
    - 否則尋找以 *Tools 命名的類別，建立 instance(runtime) 並呼叫 instance.get_tools()（必須回傳同步 list）。
    - 不再掃描 instance 的成員或模組層級的任意成員。
    - 若 get_tools() 回傳 coroutine，會非同步回報錯誤並跳過該項。
    """
    tools: List[Any] = []
    mod_name = getattr(mod, "__name__", repr(mod))
    try:
        logger.debug("llm.tools: collecting tools from module %s", mod_name)
        # 1) module-level get_tools 優先
        module_get_fn = getattr(mod, "get_tools", None)
        if callable(module_get_fn):
            try:
                # 儘量嘗試以 runtime 當參數呼叫；若不接受參數則改用無參呼叫
                try:
                    returned = module_get_fn(runtime)
                except TypeError:
                    returned = module_get_fn()
            except Exception as e:
                _report_async(e, f"llm.tools: calling module.get_tools in {mod_name}")
                returned = []
            if asyncio.iscoroutine(returned):
                _report_async(
                    Exception("module.get_tools returned coroutine"),
                    f"llm.tools: {mod_name}.get_tools returned coroutine",
                )
            else:
                # 確認回傳值為可疊代（同步）容器，再進行迭代
                if not isinstance(returned, (list, tuple, set)):
                    _report_async(
                        Exception("module.get_tools did not return iterable"),
                        f"llm.tools: {mod_name}.get_tools returned non-iterable {type(returned)}",
                    )
                else:
                    for item in (returned or []):
                        tools.append(item)
                        try:
                            logger.debug(
                                "llm.tools: module %s provided tool %s",
                                mod_name,
                                getattr(item, "name", getattr(item, "__name__", repr(item))),
                            )
                        except Exception:
                            pass
                return tools

        # 2) 尋找以 Tools 結尾的類別並呼叫其 get_tools()
        for name in dir(mod):
            if name.startswith("_"):
                continue
            try:
                obj = getattr(mod, name)
            except Exception:
                continue
            if isinstance(obj, type) and name.endswith("Tools"):
                try:
                    instance = obj(runtime)
                    get_fn = getattr(instance, "get_tools", None)
                    if callable(get_fn):
                        try:
                            returned = get_fn()
                        except Exception as e:
                            _report_async(e, f"llm.tools: calling {mod_name}.{name}.get_tools")
                            returned = []
                        if asyncio.iscoroutine(returned):
                            _report_async(
                                Exception("instance.get_tools returned coroutine"),
                                f"llm.tools: {mod_name}.{name}.get_tools returned coroutine",
                            )
                            continue
                        # 確認 instance.get_tools() 回傳可疊代結果
                        if not isinstance(returned, (list, tuple, set)):
                            _report_async(
                                Exception("instance.get_tools did not return iterable"),
                                f"llm.tools: {mod_name}.{name}.get_tools returned non-iterable {type(returned)}",
                            )
                            continue
                        for item in (returned or []):
                            tools.append(item)
                            try:
                                logger.debug(
                                    "llm.tools: %s.%s.get_tools -> %s",
                                    mod_name,
                                    name,
                                    getattr(item, "name", getattr(item, "__name__", repr(item))),
                                )
                            except Exception:
                                pass
                except Exception as e:
                    _report_async(e, f"llm.tools: instantiating or calling get_tools on {mod_name}.{name}")
    except Exception as e:
        _report_async(e, f"llm.tools: collecting from module {mod_name}")
    return tools


def _get_user_permissions(user: discord.Member, guid: discord.Guild) -> dict:
    """嘗試從專案內部取得該 Discord 使用者的權限資訊。

    此函式嘗試匯入 `cogs.system_prompt.permissions` 模組並呼叫 `get_user_permissions(user_id)`。
    若找不到或呼叫失敗，回傳一個保守的預設權限集 (非 admin / moderator)。
    """
    try:
        from main import bot
        from cogs.system_prompt.permissions import PermissionValidator
        permissions = PermissionValidator(bot)  # type: ignore

        perms = permissions.get_user_permissions(user, guid)
        if isinstance(perms, dict):
            return perms
    except Exception as e:
        _report_async(e, "llm.tools: _get_user_permissions")
    return {"is_admin": False, "is_moderator": False}


from llm.schema import OrchestratorRequest


def get_tools(
    user: discord.Member, guid: discord.Guild, runtime: OrchestratorRequest
) -> List[BaseTool]:
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

    # 檢查是否需要重新掃描工具目錄
    pkg_dir = os.path.join(os.path.dirname(__file__), "tools")
    try:
        current_mtime = (
            _compute_pkg_dir_mtime(pkg_dir) if os.path.isdir(pkg_dir) else 0.0
        )
    except Exception:
        current_mtime = 0.0

    with _cache_lock:
        if (
            _cached_collected_tools is None
            or current_mtime != _cached_collected_mtime
        ):
            try:
                temp_collected: List[Any] = []
                for mod in _discover_tools_package():
                    # 傳入專案的 OrchestratorRequest，確保工具類別建構子接收正確型態
                    temp_collected.extend(_extract_tools_from_module(mod, runtime))
                _cached_collected_tools = temp_collected
                _cached_collected_mtime = current_mtime
            except Exception as e:
                _report_async(e, "llm.tools: scanning tools for cache")
                _cached_collected_tools = _cached_collected_tools or []

        collected = list(_cached_collected_tools or [])

    # 根據使用者權限過濾
    perms = _get_user_permissions(user, guid)
    result: List[Any] = []

    for t in collected:
        try:
            # 僅接受由 @tool 裝飾或 BaseTool 的物件
            if not (_is_decorated_tool(t) or isinstance(t, BaseTool)):
                continue

            required = getattr(t, "required_permission", None)
            if required is None:
                result.append(t)
                continue

            if isinstance(required, str):
                required_set = {
                    p.strip().lower() for p in required.split(",") if p.strip()
                }
            else:
                try:
                    required_set = {str(p).lower() for p in required}
                except Exception:
                    required_set = set()

            allowed = False
            if "admin" in required_set and perms.get("is_admin"):
                allowed = True
            if "moderator" in required_set and perms.get("is_moderator"):
                allowed = True

            if allowed:
                result.append(t)
        except Exception as e:
            _report_async(
                e, f"llm.tools: filtering tool {getattr(t, 'name', repr(t))}"
            )

    try:
        return cast(List[BaseTool], result)
    except Exception as e:
        _report_async(e, "llm.tools: casting result to List[BaseTool]")
        # 若 cast 失敗，仍回傳結果（type checker 層面的保護）
        return result  # type: ignore