"""Factory for LangChain tools that auto-loads only @tool-decorated functions.

Design Points:
- Automatically loads modules under the `llm/tools/` folder (if it exists).
- Only collects callables or BaseTool instances decorated with LangChain's `@tool`.
- Implements permission-based filtering (admin/moderator) and agent mode routing.
- Exceptions are reported asynchronously via `func.report_error`, with logger fallback.
- Uses a caching mechanism to avoid repeated disk scans, improving performance.
"""

from typing import Any, Iterable, List, Optional, cast
import os

import discord
import pkgutil
import importlib
import asyncio
import threading
from addons.logging import get_logger

logger = get_logger(server_id="Bot", source="llm.tools_factory")

_VALID_AGENT_MODES: frozenset = frozenset({"info", "message", "all"})

from langchain_core.tools import StructuredTool, BaseTool
from function import func

# Cache variables: Stores the parsed module list and the maximum mtime of the files
_cached_modules: Optional[List[Any]] = None
_cached_collected_mtime: float = 0.0
_cache_lock = threading.Lock()

def _report_async(exc: Exception, ctx: str) -> None:
    """Report an error asynchronously; falls back to logger on failure."""
    try:
        asyncio.create_task(func.report_error(exc, ctx))
    except Exception:
        logger.error(f"[llm.tools] report_error failed: {exc} ({ctx})")


def _compute_pkg_dir_mtime(pkg_dir: str) -> float:
    """Calculate the maximum mtime of all .py files in the package directory."""
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
                    # Ignore individual file errors
                    continue
        return max_mtime
    except Exception as e:
        _report_async(e, "llm.tools: compute_pkg_dir_mtime failed")
        return 0.0


def _discover_tools_package() -> Iterable[Any]:
    """Import and return all modules under llm/tools (if the directory exists)."""

    pkg_dir = os.path.join(os.path.dirname(__file__), "tools")
    tools_py = os.path.join(os.path.dirname(__file__), "tools.py")

    # Debug logs for troubleshooting directory existence
    try:
        logger.debug(
            f"llm.tools debug: tools_py exists={os.path.isfile(tools_py)}, "
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
    """Check if an object is a LangChain tool (BaseTool or @tool-decorated callable)."""
    try:
        if isinstance(obj, BaseTool):
            return True
        if not callable(obj):
            return False

        # Common marker attributes used by LangChain
        for attr in ("_is_tool", "is_tool", "__langchain_tool__"):
            if getattr(obj, attr, False):
                return True

        # Check if it's a decorator wrapper
        wrapped = getattr(obj, "__wrapped__", None)
        if wrapped is not None:
            mod = getattr(wrapped, "__module__", "")
            if mod and not mod.startswith("builtins"):
                return True

        # Some wrappers have modules from LangChain
        module_name = getattr(obj, "__module__", "") or ""
        if "langchain" in module_name.lower():
            return True
    except Exception as e:
        _report_async(e, "llm.tools: _is_decorated_tool failed")
    return False


def _extract_tools_from_module(mod: Any, runtime: "OrchestratorRequest") -> List[Any]:
    """Collect tools from a module using get_tools() discovery.
    
    Strategies:
    - If the module provides a module-level `get_tools(runtime)`, use its returned list.
    - Otherwise, find classes ending in `Tools`, instantiate them with `runtime`, 
      and call `instance.get_tools()`.
    - Does not scan individual members or arbitrary classes.
    - Reports errors if `get_tools()` returns a coroutine instead of a list.
    """
    tools: List[Any] = []
    mod_name = getattr(mod, "__name__", repr(mod))
    try:
        logger.debug(f"llm.tools: collecting tools from module {mod_name}")
        # 1) Module-level get_tools priority
        module_get_fn = getattr(mod, "get_tools", None)
        if callable(module_get_fn):
            try:
                # Try calling with runtime first; fallback to no-arg call if it fails
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
                # Ensure the return value is a synchronous iterable
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
                                f"llm.tools: module {mod_name} provided tool "
                                f"{getattr(item, 'name', getattr(item, '__name__', repr(item)))}"
                            )
                        except Exception:
                            pass
                return tools

        # 2) Find classes ending with 'Tools' and call their get_tools()
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
                        # Ensure instance.get_tools() returns a synchronous iterable
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
                                    f"llm.tools: {mod_name}.{name}.get_tools -> "
                                    f"{getattr(item, 'name', getattr(item, '__name__', repr(item)))}"
                                )
                            except Exception:
                                pass
                except Exception as e:
                    _report_async(e, f"llm.tools: instantiating or calling get_tools on {mod_name}.{name}")
    except Exception as e:
        _report_async(e, f"llm.tools: collecting from module {mod_name}")
    return tools


def _get_user_permissions(user: discord.Member, guid: discord.Guild) -> dict:
    """Retrieve Discord user permission info from the project's PermissionValidator.
    
    Tries to import `cogs.system_prompt.permissions` and validate the user.
    Falls back to a conservative default (non-admin, non-moderator) if it fails.
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
    user: discord.Member, 
    guid: discord.Guild, 
    runtime: OrchestratorRequest,
    agent_mode: str = "all"
) -> List[BaseTool]:
    """Returns a list of LangChain tools available to the Discord user based on permissions.

    Permission Strategy:
    - Tools can declare a `required_permission` attribute (string, e.g., "admin", "moderator").
    - If declared, only users with that permission will receive the tool.
    - If undeclared, the tool is open to all users.

    Routing Strategy (target_agent_mode):
    - Tools can specify which Agent they belong to via `target_agent_mode`.
    - Supported values:
        - "info" (Default) - Only for the Info Agent.
        - "message" - Only for the Message Agent.
        - "all" - Available to both Agents.
    - Discovery order for the attribute: 
        1. metadata["target_agent_mode"]
        2. direct attribute on tool instance
        3. attribute on original callable

    Args:
        user: The Discord user.
        guid: The Discord Guild.
        runtime: Execution runtime context.
        agent_mode: Filtering mode ("all", "info", "message").
            - "all": Return all available tools.
            - "info": Return tools for Info Agent (excludes message-only tools).
            - "message": Return tools for Message Agent (excludes info-only tools).

    Returns:
        List[BaseTool]: List of filtered tools compatible with LangChain.
    """
    global _cached_modules, _cached_collected_mtime

    collected: List[Any] = []

    # Check if we need to re-scan the tools directory
    pkg_dir = os.path.join(os.path.dirname(__file__), "tools")
    try:
        current_mtime = (
            _compute_pkg_dir_mtime(pkg_dir) if os.path.isdir(pkg_dir) else 0.0
        )
    except Exception:
        current_mtime = 0.0

    with _cache_lock:
        if (
            _cached_modules is None
            or current_mtime != _cached_collected_mtime
        ):
            try:
                # Only cache module objects to avoid leaking runtime context between calls
                _cached_modules = list(_discover_tools_package())
                _cached_collected_mtime = current_mtime
            except Exception as e:
                _report_async(e, "llm.tools: scanning modules for cache")
                _cached_modules = _cached_modules or []

        cached_modules = list(_cached_modules or [])

    # Re-instantiate tools on every call with the current runtime
    for mod in cached_modules:
        collected.extend(_extract_tools_from_module(mod, runtime))

    # Filter based on user permissions
    perms = _get_user_permissions(user, guid)
    result: List[Any] = []

    for t in collected:
        try:
            # Only accept objects decorated with @tool or instances of BaseTool
            if not (_is_decorated_tool(t) or isinstance(t, BaseTool)):
                continue

            required = getattr(t, "required_permission", None)
            if required is not None:
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
                
                if not allowed:
                    continue

            # Filter based on agent_mode using target_agent_mode attribute
            target_agent_mode = "info"
            
            # Extract target_agent_mode from metadata or attributes
            raw_mode: object = None
            try:
                metadata = getattr(t, "metadata", None)
                if isinstance(metadata, dict) and "target_agent_mode" in metadata:
                    raw_mode = metadata["target_agent_mode"]
                elif hasattr(t, "target_agent_mode"):
                    raw_mode = getattr(t, "target_agent_mode")
                elif hasattr(t, "func") and t.func is not None and hasattr(t.func, "target_agent_mode"):
                    raw_mode = getattr(t.func, "target_agent_mode")
                elif hasattr(t, "coroutine") and t.coroutine is not None and hasattr(t.coroutine, "target_agent_mode"):
                    raw_mode = getattr(t.coroutine, "target_agent_mode")
            except (AttributeError, KeyError, TypeError) as e:
                logger.warning(
                    "Failed to extract target_agent_mode for tool %s: %s",
                    getattr(t, "name", repr(t)),
                    e,
                )

            if raw_mode is not None:
                normalized_mode = str(raw_mode).lower()
                if normalized_mode in _VALID_AGENT_MODES:
                    target_agent_mode = normalized_mode
                else:
                    logger.warning(
                        "Tool %s has unknown target_agent_mode %r; falling back to 'info'.",
                        getattr(t, "name", repr(t)),
                        raw_mode,
                    )

            if agent_mode == "info" and target_agent_mode == "message":
                continue
            elif agent_mode == "message" and target_agent_mode == "info":
                continue
            
            # Assign agent_mode to the tool instance for identification
            try:
                t.agent_mode = agent_mode
            except Exception:
                pass

            result.append(t)
        except Exception as e:
            _report_async(
                e, f"llm.tools: filtering tool {getattr(t, 'name', repr(t))}"
            )
    
    try:
        return cast(List[BaseTool], result)
    except Exception as e:
        _report_async(e, "llm.tools: casting result to List[BaseTool]")
        return result  # type: ignore


__all__ = ["get_tools"]