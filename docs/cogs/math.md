# Math Calculator Cog

**File:** [`cogs/math.py`](cogs/math.py)

This cog provides a secure and powerful mathematical calculation tool. It uses the `sympy` library to parse and evaluate mathematical expressions provided by the user.

## Features

*   **Secure Parsing:** The cog uses a whitelist of allowed functions and constants from the `sympy` library, preventing the execution of arbitrary or unsafe code. It explicitly disallows the creation of symbols or undefined functions.
*   **Advanced Calculations:** Supports a wide range of mathematical operations, including trigonometry, logarithms, exponentials, and more.
*   **Implicit Multiplication:** Understands expressions like `2x` or `(x+1)(x-1)`.
*   **Localization:** Error and result messages are translated using the `LanguageManager`.

## Core Method

### `async calculate_math(self, expression: str, ...)`

This is the core function that performs the calculation. It is not exposed as a command directly but is designed to be called by other parts of the bot (e.g., a general-purpose tool).

*   **Parameters:**
    *   `expression` (str): The mathematical expression to evaluate.
*   **Returns:** A string containing the formatted result or an error message.

## Security Measures

To ensure safety, the calculator implements several restrictions:

1.  **Expression Length Limit:** Expressions are limited to 200 characters to prevent overly complex or malicious inputs.
2.  **Whitelisted Functions:** Only a pre-defined set of safe mathematical functions and constants from `sympy` (like `sin`, `cos`, `pi`, `E`) are allowed.
3.  **Disabled Globals:** The `sympy` parser is configured with an empty `global_dict`, preventing it from accessing any global variables.
4.  **Type Checking:** The parsed expression is checked for unsafe types like `sympy.Symbol` or `sympy.Function`, which are rejected.

### Example Usage

While not a direct command, the functionality can be imagined as:

```
/calculate expression: "sqrt(pi^2 + log(10))"
```

The cog would then return the calculated numerical result.