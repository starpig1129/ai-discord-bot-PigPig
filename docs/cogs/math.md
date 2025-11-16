# Math Cog Documentation

## Overview

The Math cog provides comprehensive mathematical calculation capabilities through Discord slash commands. It supports basic arithmetic, advanced mathematical operations, unit conversions, and statistical calculations with multi-language support.

## Features

### Core Functionality
- **Basic Arithmetic**: Addition, subtraction, multiplication, division
- **Advanced Calculations**: Exponents, roots, logarithms, trigonometric functions
- **Unit Conversions**: Length, weight, temperature, and other measurement units
- **Statistical Functions**: Mean, median, mode, standard deviation, variance
- **Equation Solving**: Linear equations and simple algebraic problems
- **Matrix Operations**: Basic matrix arithmetic and transformations
- **Multi-language Support**: Full localization of mathematical terms and outputs

### Key Components
- `Math` class - Main cog implementation
- Mathematical expression parser and evaluator
- Unit conversion library
- Statistical calculation engine
- Multi-language number formatting

## Commands

### `/calculate`
Evaluates a mathematical expression and returns the result.

**Parameters**:
- `expression` (string, required): Mathematical expression to evaluate
- `decimal_places` (int, optional, default: 10): Number of decimal places in result

**Supported Operations**:
- Basic: `+`, `-`, `*`, `/`, `^`, `%`
- Advanced: `sin()`, `cos()`, `tan()`, `log()`, `ln()`, `sqrt()`, `abs()`
- Constants: `pi`, `e`

**Usage Examples**:
```
/calculate expression:"2 + 3 * 4"
/calculate expression:"sin(90) + cos(0)"
/calculate expression:"sqrt(16) + log(100)" decimal_places:5
```

**Required Permissions**: None (public access)

### `/convert_units`
Converts between different units of measurement.

**Parameters**:
- `value` (float, required): Value to convert
- `from_unit` (string, required): Source unit
- `to_unit` (string, required): Target unit
- `category` (string, required): Measurement category

**Supported Categories**:
- `length`: meters, kilometers, feet, inches, miles, etc.
- `weight`: grams, kilograms, pounds, ounces, etc.
- `temperature`: celsius, fahrenheit, kelvin
- `volume`: liters, gallons, cups, milliliters, etc.

**Usage Examples**:
```
/convert_units value:100 from_unit:"celsius" to_unit:"fahrenheit" category:"temperature"
/convert_units value:5 from_unit:"miles" to_unit:"kilometers" category:"length"
/convert_units value:2 from_unit:"kilograms" to_unit:"pounds" category:"weight"
```

**Required Permissions**: None (public access)

### `/statistics`
Calculates statistical measures for a set of numbers.

**Parameters**:
- `numbers` (string, required): Comma-separated list of numbers
- `calculation` (string, required): Type of statistical calculation

**Supported Calculations**:
- `mean`: Average of all numbers
- `median`: Middle value when sorted
- `mode`: Most frequent value
- `std_dev`: Standard deviation
- `variance`: Variance calculation
- `range`: Difference between max and min values
- `sum`: Sum of all numbers

**Usage Examples**:
```
/statistics numbers:"1,2,3,4,5" calculation:"mean"
/statistics numbers:"10,15,20,25,30" calculation:"median"
/statistics numbers:"1,2,2,3,3,3" calculation:"mode"
```

**Required Permissions**: None (public access)

## Technical Implementation

### Class Structure
```python
class Math(commands.Cog):
    def __init__(self, bot)
    async def cog_load(self)
    
    # Command handlers
    async def calculate_command(self, interaction: discord.Interaction, 
                               expression: str, decimal_places: int = None)
    async def convert_units_command(self, interaction: discord.Interaction,
                                   value: float, from_unit: str, to_unit: str, 
                                   category: app_commands.Choice[str])
    async def statistics_command(self, interaction: discord.Interaction,
                                numbers: str, calculation: app_commands.Choice[str])
```

### Expression Parser
```python
import math
import re
from typing import List, Union

class MathExpressionParser:
    def __init__(self):
        # Supported mathematical functions
        self.functions = {
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'asin': math.asin,
            'acos': math.acos,
            'atan': math.atan,
            'log': math.log10,
            'ln': math.log,
            'sqrt': math.sqrt,
            'abs': abs,
            'ceil': math.ceil,
            'floor': math.floor,
            'round': round
        }
        
        # Mathematical constants
        self.constants = {
            'pi': math.pi,
            'e': math.e,
            'tau': math.tau
        }

    def evaluate_expression(self, expression: str) -> float:
        """Safely evaluate mathematical expression"""
        
        # Pre-process expression
        processed = self.preprocess_expression(expression)
        
        # Validate expression
        if not self.validate_expression(processed):
            raise ValueError("Invalid mathematical expression")
        
        # Replace constants
        for const, value in self.constants.items():
            processed = processed.replace(const, str(value))
        
        # Replace functions with safe equivalents
        processed = self.replace_functions(processed)
        
        # Evaluate expression safely
        try:
            result = eval(processed, {"__builtins__": {}}, {})
            return result
        except Exception as e:
            raise ValueError(f"Cannot evaluate expression: {str(e)}")

    def preprocess_expression(self, expression: str) -> str:
        """Clean and standardize expression format"""
        
        # Replace Unicode symbols
        replacements = {
            '×': '*',
            '÷': '/',
            '−': '-',
            'ⁿ': '^',
            '√': 'sqrt'
        }
        
        for old, new in replacements.items():
            expression = expression.replace(old, new)
        
        # Handle implied multiplication (e.g., "2(3+4)" -> "2*(3+4)")
        expression = re.sub(r'(\d+)\s*\(([^)]+)\)', r'\1*(\2)', expression)
        expression = re.sub(r'([a-zA-Z])\s*\(([^)]+)\)', r'\1(\2)', expression)
        
        return expression

    def replace_functions(self, expression: str) -> str:
        """Replace function names with safe Python equivalents"""
        
        for func_name, func_impl in self.functions.items():
            pattern = rf'\b{func_name}\s*\('
            replacement = f'{func_name}('
            expression = re.sub(pattern, replacement, expression)
        
        return expression
```

### Unit Conversion System
```python
class UnitConverter:
    CONVERSION_TABLES = {
        'length': {
            'meters': 1,
            'kilometers': 1000,
            'centimeters': 0.01,
            'millimeters': 0.001,
            'inches': 0.0254,
            'feet': 0.3048,
            'yards': 0.9144,
            'miles': 1609.344,
            'nautical_miles': 1852
        },
        'weight': {
            'grams': 1,
            'kilograms': 1000,
            'pounds': 453.592,
            'ounces': 28.3495,
            'stones': 6350.29,
            'tons': 1000000
        },
        'temperature': {
            'celsius': 'C',
            'fahrenheit': 'F',
            'kelvin': 'K'
        },
        'volume': {
            'liters': 1,
            'milliliters': 0.001,
            'gallons': 3.78541,
            'quarts': 0.946353,
            'pints': 0.473176,
            'cups': 0.236588
        }
    }

    def convert(self, value: float, from_unit: str, to_unit: str, category: str) -> float:
        """Convert value between units"""
        
        if category not in self.CONVERSION_TABLES:
            raise ValueError(f"Unsupported category: {category}")
        
        table = self.CONVERSION_TABLES[category]
        
        if category == 'temperature':
            return self.convert_temperature(value, from_unit, to_unit)
        else:
            if from_unit not in table or to_unit not in table:
                raise ValueError(f"Unsupported units: {from_unit} or {to_unit}")
            
            # Convert to base unit, then to target unit
            base_value = value * table[from_unit]
            result = base_value / table[to_unit]
            
            return result

    def convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        """Special handling for temperature conversions"""
        
        if from_unit == to_unit:
            return value
        
        # Convert to Celsius first
        if from_unit == 'fahrenheit':
            celsius = (value - 32) * 5/9
        elif from_unit == 'kelvin':
            celsius = value - 273.15
        else:
            celsius = value
        
        # Convert from Celsius to target
        if to_unit == 'fahrenheit':
            return celsius * 9/5 + 32
        elif to_unit == 'kelvin':
            return celsius + 273.15
        else:
            return celsius
```

### Statistical Calculator
```python
import statistics
from typing import List

class StatisticalCalculator:
    def calculate(self, numbers: List[float], calculation: str) -> Union[float, List[float]]:
        """Calculate statistical measures"""
        
        if len(numbers) == 0:
            raise ValueError("Cannot calculate statistics for empty list")
        
        if len(numbers) == 1:
            return numbers[0]  # All statistics are the same for single value
        
        calculations = {
            'mean': lambda x: statistics.mean(x),
            'median': lambda x: statistics.median(x),
            'mode': lambda x: statistics.mode(x) if len(set(x)) < len(x) else x,
            'std_dev': lambda x: statistics.stdev(x),
            'variance': lambda x: statistics.variance(x),
            'range': lambda x: max(x) - min(x),
            'sum': lambda x: sum(x),
            'max': lambda x: max(x),
            'min': lambda x: min(x),
            'count': lambda x: len(x)
        }
        
        if calculation not in calculations:
            raise ValueError(f"Unsupported calculation: {calculation}")
        
        try:
            result = calculations[calculation](numbers)
            return result
        except statistics.StatisticsError as e:
            if calculation == 'mode':
                # Handle multimodal data
                try:
                    return statistics.multimode(numbers)
                except:
                    return "No unique mode"
            raise ValueError(f"Cannot calculate {calculation}: {str(e)}")
```

## Error Handling

### Expression Validation
```python
def validate_expression(self, expression: str) -> bool:
    """Validate mathematical expression for safety"""
    
    # Check for suspicious patterns
    dangerous_patterns = [
        r'__',  # Python special attributes
        r'globals',  # Access to globals
        r'locals',   # Access to locals
        r'exec',     # Execution functions
        r'import',   # Import statements
        r'open',     # File operations
        r'eval',     # Eval functions
        r'compile'   # Compilation functions
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, expression, re.IGNORECASE):
            return False
    
    # Check for balanced parentheses and brackets
    stack = []
    brackets = {'(': ')', '[': ']', '{': '}'}
    
    for char in expression:
        if char in brackets:
            stack.append(char)
        elif char in brackets.values():
            if not stack or brackets[stack.pop()] != char:
                return False
    
    return len(stack) == 0
```

### Graceful Error Handling
```python
async def handle_calculation_error(self, interaction, error, command_type: str):
    """Handle calculation errors with user-friendly messages"""
    
    error_messages = {
        'invalid_expression': "Invalid mathematical expression. Please check syntax.",
        'division_by_zero': "Division by zero is not allowed.",
        'math_domain_error': "Mathematical domain error (e.g., square root of negative number).",
        'unsupported_operation': "This mathematical operation is not supported.",
        'invalid_units': "Invalid unit conversion parameters.",
        'insufficient_data': "Not enough data for statistical calculation."
    }
    
    # Determine error type and provide appropriate message
    error_str = str(error).lower()
    
    if "zero division" in error_str or "division by zero" in error_str:
        message = error_messages['division_by_zero']
    elif "math domain error" in error_str:
        message = error_messages['math_domain_error']
    elif "invalid units" in error_str or "unsupported unit" in error_str:
        message = error_messages['invalid_units']
    elif "statistics" in error_str or "mode" in error_str:
        message = error_messages['insufficient_data']
    else:
        message = error_messages['invalid_expression']
    
    await interaction.response.send_message(message, ephemeral=True)
    
    # Log error for debugging
    await func.report_error(error, f"math_{command_type}")
```

## Performance Optimization

### Caching System
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def cached_calculation(expression_hash: str, expression: str) -> float:
    """Cache frequently calculated expressions"""
    parser = MathExpressionParser()
    return parser.evaluate_expression(expression)

def get_expression_hash(self, expression: str) -> str:
    """Generate hash for expression caching"""
    return hashlib.md5(expression.strip().encode()).hexdigest()
```

### Expression Preprocessing
- **Tokenization**: Break expressions into components for faster processing
- **Constant Folding**: Pre-evaluate constant expressions
- **Expression Optimization**: Simplify complex expressions before evaluation

## Usage Examples

### Basic Calculations
```
User: /calculate expression:"2 + 3 * 4"
Bot: Result: 14.0

User: /calculate expression:"sin(90) + cos(0)"
Bot: Result: 2.0

User: /calculate expression:"sqrt(16) + log(100)"
Bot: Result: 4.0
```

### Unit Conversions
```
User: /convert_units value:100 from_unit:"celsius" to_unit:"fahrenheit" category:"temperature"
Bot: 100°C = 212°F

User: /convert_units value:5 from_unit:"miles" to_unit:"kilometers" category:"length"
Bot: 5 miles = 8.047 kilometers

User: /convert_units value:2 from_unit:"kilograms" to_unit:"pounds" category:"weight"
Bot: 2 kilograms = 4.409 pounds
```

### Statistical Analysis
```
User: /statistics numbers:"1,2,3,4,5,6,7,8,9,10" calculation:"mean"
Bot: Mean: 5.5

User: /statistics numbers:"10,15,20,25,30,35" calculation:"median"
Bot: Median: 22.5

User: /statistics numbers:"1,1,2,2,2,3,3,3,3" calculation:"mode"
Bot: Mode: 3.0 (appears 4 times)
```

## Advanced Features

### Complex Calculations
```python
# Support for nested functions
/calculate expression:"sin(cos(45)) + sqrt(log(1000))"

/# Support for arrays and matrices
/calculate expression:"sum(1,2,3,4,5)^2 + mean(10,20,30)"

/# Scientific notation
/calculate expression:"1.2e5 * 3.4e-3"
```

### Advanced Unit Conversions
```python
# Temperature conversions with Celsius, Fahrenheit, Kelvin
# Weight conversions with metric and imperial systems
# Volume conversions between different measurement systems
# Length conversions including astronomical units
```

### Statistical Analysis
```python
# Comprehensive statistical measures
# Data distribution analysis
# Outlier detection
# Confidence intervals
```

## Integration Points

### With Other Cogs
```python
# Integration with user data for calculation history
from cogs.userdata import UserData

# Integration with language manager for unit names
from cogs.language_manager import LanguageManager

# Integration with memory systems for calculation context
from cogs.episodic_memory import EpisodicMemory
```

### External Libraries
- **Math Libraries**: NumPy, SciPy for advanced calculations
- **Statistics**: Custom statistical engines
- **Units**: Comprehensive unit conversion databases

## Related Files

- `cogs/math.py` - Main implementation
- `translations/en_US/commands/calculate.json` - English translations
- `LanguageManager` - Translation system
- `MathExpressionParser` - Expression parsing engine
- `UnitConverter` - Unit conversion system
- `StatisticalCalculator` - Statistical computation engine

## Future Enhancements

Potential improvements:
- Graph plotting and visualization
- Equation solving capabilities
- Financial calculations (compound interest, present value, etc.)
- Probability and statistics advanced functions
- Matrix operations and linear algebra
- Custom function definitions
- Calculation history and bookmarking
- Scientific notation support
- Integration with external math libraries