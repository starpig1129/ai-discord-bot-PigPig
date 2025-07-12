import inspect
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Type

from gpt.tools.tool_context import ToolExecutionContext


@dataclass
class ToolParameter:
    """Defines a parameter for a tool."""
    name: str
    type: str
    description: str
    required: bool


class Tool(ABC):
    """Abstract base class for a tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """The description of the tool."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """The parameters of the tool."""
        pass

    @abstractmethod
    async def execute(self, context: ToolExecutionContext, **kwargs) -> Any:
        """Executes the tool with the given context and arguments."""
        pass


class _FunctionTool(Tool):
    """A tool implemented from a function."""

    def __init__(self, func: Callable, name: str, description: str, params: List[ToolParameter]):
        self._func = func
        self._name = name
        self._description = description
        self._parameters = params

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> List[ToolParameter]:
        return self._parameters

    async def execute(self, context: ToolExecutionContext, **kwargs) -> Any:
        # The first parameter of the decorated function is always the context.
        return await self._func(context, **kwargs)


class ToolRegistry:
    """A singleton registry for managing tools."""
    _instance = None
    _tools: Dict[str, Tool] = {}
    _tools_string_for_prompt: str | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._tools = {}
            cls._tools_string_for_prompt = None
        return cls._instance

    def register(self, tool: Tool):
        """Registers a tool and invalidates the prompt string cache."""
        if tool.name in self._tools:
            # In a real-world scenario, you might want to log a warning.
            # For now, we'll just overwrite.
            pass
        self._tools[tool.name] = tool
        # Invalidate the cached string whenever a new tool is registered.
        self._tools_string_for_prompt = None

    def get_tool(self, name: str) -> Tool:
        """Gets a tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found.")
        return self._tools[name]

    def get_all_tools(self) -> List[Tool]:
        """Gets all registered tools."""
        return list(self._tools.values())

    def get_tool_schema(self) -> List[Dict]:
        """Generates the JSON schema for all registered tools."""
        schemas = []
        for tool in self.get_all_tools():
            properties = {}
            required = []
            for param in tool.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description,
                }
                if param.required:
                    required.append(param.name)

            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            schemas.append(schema)
        return schemas

    def _generate_tools_string_for_prompt(self) -> str:
        """Generates a semi-structured string for all registered tools."""
        tool_strings = []
        for tool in self.get_all_tools():
            description = f"# {tool.description}"
            param_names = [p.name for p in tool.parameters]
            signature = f"{tool.name}({', '.join(param_names)})"
            
            param_details = []
            for param in tool.parameters:
                param_desc = param.description or "No description available."
                param_details.append(f"  - {param.name} ({param.type}): {param_desc}")

            full_tool_string = "\n".join([description, signature] + param_details)
            tool_strings.append(full_tool_string)

        return "\n---\n".join(tool_strings)

    def get_tools_string_for_prompt(self) -> str:
        """
        Gets a semi-structured string for all registered tools, for use in prompts.
        Caches the string for efficiency.
        """
        if self._tools_string_for_prompt is None:
            self._tools_string_for_prompt = self._generate_tools_string_for_prompt()
        return self._tools_string_for_prompt


_registry = ToolRegistry()


def _parse_docstring_args(docstring: str) -> Dict[str, str]:
    """Parses the Args section of a Google-style docstring in a robust way."""
    arg_descriptions = {}
    
    # 1. Isolate the 'Args:' section.
    args_section_match = re.search(r'Args:(.*?)(?:Returns:|Raises:|Yields:|\Z)', docstring, re.S)
    if not args_section_match:
        return {}

    args_content = args_section_match.group(1)
    
    # 2. Split the content by lines that start a new argument definition.
    # The regex looks for a newline, optional whitespace, and then a word followed by an optional type and a colon.
    # This effectively splits the content into a list where each item is the full text for one argument.
    arg_blocks = re.split(r'\n\s*(?=[a-zA-Z0-9_]+\s*(?:\(.*\))?:)', args_content)

    # 3. Regex to parse each individual argument block.
    arg_detail_pattern = re.compile(r'^\s*([a-zA-Z0-9_]+)\s*(?:\(.*\))?:\s*(.*)', re.S)

    for block in arg_blocks:
        block = block.strip()
        if not block:
            continue
        
        match = arg_detail_pattern.match(block)
        if match:
            param_name = match.group(1)
            # Clean up the multi-line description by replacing newlines and squashing whitespace.
            description = ' '.join(match.group(2).strip().split())
            arg_descriptions[param_name] = description
            
    return arg_descriptions


def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    A decorator to register a function as a tool.
    It automatically infers the description from the docstring and parameters
    from type hints.
    """
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func) or ""
    description = docstring.split('\n')[0]
    
    # Parse parameter descriptions from the docstring
    param_descriptions = _parse_docstring_args(docstring)
    
    tool_params: List[ToolParameter] = []
    
    # Skip the first parameter which is expected to be ToolExecutionContext
    for param in list(sig.parameters.values())[1:]:
        if param.name == 'kwargs': # Skip kwargs
            continue
            
        param_type = "string" # Default to string for simplicity
        if param.annotation is not inspect.Parameter.empty:
            # A more robust implementation would map Python types to JSON schema types
            if param.annotation in [int, float]:
                param_type = "number"
            elif param.annotation is bool:
                param_type = "boolean"
            elif param.annotation is list:
                param_type = "array"
            elif param.annotation is dict:
                param_type = "object"

        tool_params.append(
            ToolParameter(
                name=param.name,
                type=param_type,
                description=param_descriptions.get(param.name, "No description available."),
                required=param.default is inspect.Parameter.empty,
            )
        )

    tool_instance = _FunctionTool(
        func=func,
        name=func.__name__,
        description=description,
        params=tool_params,
    )
    
    _registry.register(tool_instance)
    
    return func

# Export the singleton instance
tool_registry = _registry