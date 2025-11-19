# MIT License
# Tools overview generator for LLM integration.
#
# This module provides a LangChain-compatible tool that dynamically
# discovers other tools in the llm.tools package and returns a
# concise, auto-generated string summary describing each available tool.
#
# The implementation follows the pattern used by other tool modules:
# - Exposes a class with a get_tools() method.
# - Uses a closure (decorated with @tool) to bind runtime context.
#
# Error reporting uses func.report_error to comply with project rules.
import importlib
import inspect
from addons.logging import get_logger
import pkgutil
from typing import Any, List

from langchain_core.tools import tool

from function import func

_logger = get_logger(server_id="Bot", source="llm.tools.tools_overview")


class ToolsOverviewTools:
    """Container for a tool that lists available tools and their short descriptions.

    Usage:
        tools = ToolsOverviewTools(runtime).get_tools()
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.logger = getattr(runtime, "logger", _logger)

    def get_tools(self) -> List:
        """Return a list containing a single tool that summarizes available tools.

        The returned tool inspects modules under the llm.tools package, instantiates
        any discovered '*Tools' container classes (passing the current runtime), calls
        their get_tools() methods, and extracts each tool function's name, signature,
        and first-line docstring as a short description.

        This process is automatic and does not rely on hard-coded tool lists.
        """
        runtime = self.runtime
        logger = self.logger

        @tool
        async def list_tools() -> str:
            """Generate a summary string of available tools.

            Returns a human-readable string where each discovered tool includes:
              - Tool name
              - Function signature
              - One-line description (first line of the tool's docstring)
              - Source module and container class

            If any module or tool cannot be inspected, the error is reported via
            func.report_error and the discovery continues.
            """
            try:
                package_name = "llm.tools"
                try:
                    pkg = importlib.import_module(package_name)
                except Exception as e:
                    await func.report_error(e, f"Failed to import package {package_name}")
                    return f"Error: Failed to import tools package: {e}"

                discovered_entries: List[str] = []
                prefix = pkg.__name__ + "."

                # Iterate over submodules in llm.tools
                for finder, module_shortname, ispkg in pkgutil.iter_modules(pkg.__path__):
                    module_name = prefix + module_shortname
                    try:
                        module = importlib.import_module(module_name)
                    except Exception as e:
                        # Report and skip modules that fail to import
                        await func.report_error(e, f"Importing module {module_name} failed")
                        continue

                    # Inspect module members for classes that expose get_tools()
                    for cls_name, cls_obj in inspect.getmembers(module, inspect.isclass):
                        # Only consider classes defined in this module
                        if getattr(cls_obj, "__module__", "") != module_name:
                            continue
                        if not hasattr(cls_obj, "get_tools"):
                            continue

                        try:
                            # Instantiate the container with the current runtime
                            try:
                                instance = cls_obj(runtime)
                            except TypeError:
                                # If constructor signature differs, try without args
                                instance = cls_obj()  # type: ignore
                            tools = instance.get_tools() or []
                        except Exception as e:
                            await func.report_error(e, f"Instantiating {module_name}.{cls_name} failed")
                            continue

                        # Extract metadata from each tool function
                        for tool_obj in tools:
                            try:
                                tool_name = getattr(tool_obj, "__name__", repr(tool_obj))
                                tool_doc = inspect.getdoc(tool_obj) or ""
                                # Use the first non-empty line as a short description
                                short_desc = ""
                                for line in tool_doc.splitlines():
                                    if line.strip():
                                        short_desc = line.strip()
                                        break
                                try:
                                    signature = str(inspect.signature(tool_obj))
                                except (ValueError, TypeError):
                                    signature = "(signature unavailable)"

                                entry = (
                                    f"Tool: {tool_name}\n"
                                    f"Signature: {signature}\n"
                                    f"Description: {short_desc}\n"
                                )
                                discovered_entries.append(entry)
                            except Exception as e:
                                await func.report_error(e, f"Inspecting tool in {module_name}.{cls_name} failed")
                                # Continue with other tools
                                continue

                if not discovered_entries:
                    return "No tools found."

                # Join entries with a clear separator
                return "\n\n---\n\n".join(discovered_entries)

            except Exception as e:
                await func.report_error(e, "list_tools failed unexpectedly")
                return f"Error: {e}"

        return [list_tools]