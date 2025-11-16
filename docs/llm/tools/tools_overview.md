# Tools Overview Generator

## Overview

The `ToolsOverviewTools` class provides a dynamic LangChain-compatible tool that discovers and summarizes all available tools in the llm.tools package. It uses automatic introspection to generate comprehensive tool listings without hard-coded dependencies.

## Class: ToolsOverviewTools

### Constructor

```python
def __init__(self, runtime: Any):
```

**Parameters:**
- `runtime`: Runtime context containing bot, message, and logger

**Description:**
Initializes the tools overview container with runtime context for tool discovery and introspection.

### Methods

#### `get_tools(self) -> List`

**Returns:**
- `List`: List containing the list_tools tool with runtime context

**Description:**
Returns a list containing a single tool that discovers and summarizes all available LLM tools.

### Tool: list_tools

```python
@tool
async def list_tools() -> str:
```

**Returns:**
- `str`: Human-readable summary of discovered tools with names, signatures, descriptions, and source information

**Purpose:**
Dynamically discovers tools across the llm.tools package and returns a comprehensive summary.

**Discovery Process:**

**1. Package Import:**
```python
package_name = "llm.tools"
try:
    pkg = importlib.import_module(package_name)
except Exception as e:
    await func.report_error(e, f"Failed to import package {package_name}")
    return f"Error: Failed to import tools package: {e}"
```

**2. Module Enumeration:**
```python
for finder, module_shortname, ispkg in pkgutil.iter_modules(pkg.__path__):
    module_name = prefix + module_shortname
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        await func.report_error(e, f"Importing module {module_name} failed")
        continue
```

**3. Class Discovery:**
```python
# Inspect module members for classes that expose get_tools()
for cls_name, cls_obj in inspect.getmembers(module, inspect.isclass):
    # Only consider classes defined in this module
    if getattr(cls_obj, "__module__", "") != module_name:
        continue
    if not hasattr(cls_obj, "get_tools"):
        continue
```

**4. Tool Instantiation:**
```python
# Instantiate the container with the current runtime
try:
    instance = cls_obj(runtime)
except TypeError:
    # If constructor signature differs, try without args
    instance = cls_obj()  # type: ignore
tools = instance.get_tools() or []
```

**5. Tool Metadata Extraction:**
```python
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
    except Exception as e:
        await func.report_error(e, f"Inspecting tool in {module_name}.{cls_name} failed")
        continue
```

**Output Format:**

**Tool Summary Structure:**
```
Tool: search_episodic_memory
Signature: (vector_query=None, keyword_query=None, user_id=None, global_search=False)
Description: Search episodic memory using semantic vectors and/or keyword matching.

---
Tool: generate_image  
Signature: (prompt, image_url=None)
Description: Generates an image based on a text prompt.

---
Tool: internet_search
Signature: (query, search_type='general', search_instructions='')
Description: Performs an internet search and records Gemini grounding usage.
```

**Discovery Features:**

**Automatic Tool Detection:**
- Scans all modules in llm.tools package
- Identifies classes with get_tools() methods
- Instantiates tool containers with runtime context
- Extracts tool function metadata

**Flexible Instantiation:**
- Standard instantiation with runtime parameter
- Fallback instantiation without arguments for compatibility
- Handles varying constructor signatures gracefully

**Comprehensive Metadata:**
- **Tool Name**: Function name or object representation
- **Function Signature**: Complete parameter list with defaults
- **Short Description**: First line of tool's docstring
- **Source Information**: Module and container class identification

**Error Resilience:**

**Graceful Error Handling:**
1. **Package Import Failures**: Continue with other packages
2. **Module Import Errors**: Skip problematic modules and report
3. **Instantiation Failures**: Try alternative instantiation methods
4. **Tool Inspection Errors**: Skip problematic tools and continue
5. **Signature Analysis**: Fallback to "signature unavailable"

**Error Reporting:**
- Uses `func.report_error()` for all failure scenarios
- Continues discovery despite individual tool failures
- Provides detailed error context for debugging

**Discovery Scope:**

**Tool Types Covered:**
- **EpisodicMemoryTools**: Memory search and retrieval
- **ImageTools**: AI image generation
- **InternetSearchTools**: Web search capabilities  
- **MathTools**: Mathematical calculations
- **ReminderTools**: Scheduling and notifications
- **UserDataTools**: User information management

**Container Class Pattern:**
```python
class ExampleTools:
    def __init__(self, runtime):
        self.runtime = runtime
    
    def get_tools(self) -> list:
        @tool
        async def example_tool(param: str) -> str:
            """Example tool description."""
            # Tool implementation
            return result
        
        return [example_tool]
```

**Output Quality:**

**User-Friendly Format:**
- Clear tool names and descriptions
- Complete parameter signatures
- Consistent formatting with separators
- Error messages for unavailable information

**Debugging Information:**
- Source module identification
- Container class tracking
- Error reporting for troubleshooting

## Integration

The ToolsOverviewTools is used by:
- **LangChain agents** for tool discovery and selection
- **Developer tools** for system introspection
- **Documentation generation** for automatic tool catalogs
- **Runtime debugging** for tool availability checking

## Dependencies

- `importlib`: For dynamic module loading
- `inspect`: For code introspection and signature analysis
- `logging`: For operation monitoring
- `pkgutil`: For package module discovery
- `langchain_core.tools`: For tool integration
- `function.func`: For error reporting

## Usage Examples

**Tool Discovery:**
```python
# Get overview of all available tools
result = await list_tools()
print(result)
# Output: Comprehensive list of all discovered tools with metadata
```

**Development Debugging:**
```python
# Check available tools in development
available_tools = await list_tools()
# Verify tool discovery and metadata extraction
```

**Dynamic Tool Selection:**
```python
# Discover available capabilities
tool_list = await list_tools()
# Use tool overview for intelligent tool selection
```

## Performance Considerations

**Introspection Overhead:**
- Imports all llm.tools modules
- Instantiates tool containers
- Analyzes function signatures
- Extracts documentation

**Caching Strategy:**
- Results may be cached for performance
- Discovery run once per agent session
- Metadata extraction optimized for speed

**Error Isolation:**
- Individual tool failures don't stop discovery
- Partial results provided on errors
- Detailed error reporting for maintenance

## Maintenance Benefits

**Automatic Updates:**
- New tools automatically discovered
- No manual list updates required
- Metadata stays current with code

**Development Efficiency:**
- Rapid tool availability checking
- Consistent documentation generation
- Simplified debugging of tool integration