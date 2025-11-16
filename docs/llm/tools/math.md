# Math Calculation Tools

## Overview

The `MathTools` class provides LangChain-compatible tools for performing mathematical calculations using the MathCalculatorCog. It enables agents to perform complex mathematical operations through natural language expressions.

## Class: MathTools

### Constructor

```python
def __init__(self, runtime: "OrchestratorRequest"):
```

**Parameters:**
- `runtime`: Orchestrator request containing bot, message, and logger

**Description:**
Initializes the math tools container with runtime context for Discord integration and calculation capabilities.

### Methods

#### `get_tools(self) -> list`

**Returns:**
- `list`: List containing the calculate_math tool with runtime context

**Description:**
Returns a list of LangChain tools bound to the current runtime context.

### Tool: calculate_math

```python
@tool
async def calculate_math(expression: str) -> str:
```

**Parameters:**
- `expression`: A mathematical expression to evaluate (e.g., "2 + 2", "sqrt(16)", "sin(pi/2)")

**Returns:**
- `str`: The calculation result as a string, or an error message if the calculation failed

**Purpose:**
Performs mathematical calculations by delegating to the MathCalculatorCog.

**Supported Operations:**

**Basic Arithmetic:**
- Addition: `"2 + 3"`
- Subtraction: `"10 - 4"`
- Multiplication: `"6 * 7"`
- Division: `"15 / 3"`

**Advanced Functions:**
- Square root: `"sqrt(16)"`
- Trigonometric: `"sin(pi/2)"`, `"cos(0)"`, `"tan(pi/4)"`
- Logarithmic: `"log(100)"`, `"ln(e)"`
- Exponential: `"2^10"`, `"exp(1)"`

**Complex Expressions:**
- Parentheses grouping: `"(2 + 3) * 4"`
- Mixed operations: `"sqrt(144) + sin(pi/2)"`
- Constants: `"pi"`, `"e"`

**Expression Examples:**
```python
# Basic calculations
"2 + 2"
"10 * 5 - 3"

# Advanced functions  
"sqrt(144)"
"sin(pi/2) + cos(0)"
"log(100) / ln(e)"

# Complex expressions
"(2 + 3) * sqrt(16)"
"sin(pi/4) * cos(pi/4)"
"2^(log(100) / log(10))"
```

**Discord Integration:**

**Context Extraction:**
```python
# Extract guild_id for context-aware calculations
guild_id: Optional[str] = None
message = getattr(runtime, "message", None)
if message and getattr(message, "guild", None):
    guild_id = str(message.guild.id)

# Delegate to MathCalculatorCog
result = await cog.calculate_math(expression, guild_id=guild_id)
```

**Error Handling:**

**Comprehensive Error Recovery:**
1. **Bot Instance Check**: Validates bot availability
2. **Cog Validation**: Ensures MathCalculatorCog is loaded
3. **Expression Validation**: Handles invalid mathematical expressions
4. **Result Processing**: Manages calculation errors and edge cases

**Error Scenarios:**
- Bot instance not available
- MathCalculatorCog not found
- Invalid mathematical expression
- Division by zero
- Unsupported functions
- Overflow errors

**Logging and Monitoring:**

**Operation Logging:**
```python
logger.info("calculate_math called", extra={"expression": expression})
logger.info(
    "Delegated calculation completed",
    extra={"expression": expression, "result": result},
)
```

**Performance Considerations:**
- Async delegation to MathCalculatorCog
- Guild-specific calculation history (if enabled)
- Expression caching for repeated calculations
- Error reporting for invalid expressions

## Integration

The MathTools is used by:
- **ToolsFactory** for dynamic tool loading
- **LangChain agents** for mathematical capabilities
- **Orchestrator** for calculation functionality

## Dependencies

- `logging`: For operation monitoring
- `langchain_core.tools`: For tool integration
- `MathCalculatorCog`: For calculation functionality
- `function.func`: For error reporting

## Usage Examples

**Basic Arithmetic:**
```python
# Simple calculations
result = await calculate_math("2 + 3")
# Returns: "5"

result = await calculate_math("10 * 5 - 3")
# Returns: "47"
```

**Advanced Functions:**
```python
# Square root
result = await calculate_math("sqrt(144)")
# Returns: "12.0"

# Trigonometric functions
result = await calculate_math("sin(pi/2)")
# Returns: "1.0"

# Logarithmic functions
result = await calculate_math("log(100)")
# Returns: "4.605170186"
```

**Complex Expressions:**
```python
# Parentheses grouping
result = await calculate_math("(2 + 3) * sqrt(16)")
# Returns: "20.0"

# Mixed operations
result = await calculate_math("sin(pi/4) + cos(pi/4)")
# Returns: "1.414213562"
```

## Error Handling Examples

**Invalid Expression:**
```python
result = await calculate_math("invalid expression")
# Returns: "Error: Invalid mathematical expression"
```

**Division by Zero:**
```python
result = await calculate_math("10 / 0")
# Returns: "Error: Division by zero"
```

**Unsupported Function:**
```python
result = await calculate_math("unknown_function(5)")
# Returns: "Error: Unknown function 'unknown_function'"
```

## Security Considerations

**Input Validation:**
- Expression parsing and validation
- Prevention of code injection through mathematical expressions
- Safe evaluation environment

**Rate Limiting:**
- Guild-specific rate limiting (if configured)
- Prevention of calculation spam
- Resource usage monitoring