# Model Circuit Breaker

## Overview

The `ModelCircuitBreaker` module implements a fault-tolerance pattern to manage LLM provider failures. It tracks model performance in real-time and temporarily "trips" (disables) models that are consistently failing, preventing the bot from wasting API quota and reducing latency caused by doomed retry attempts.

## Core Concepts

### Error Categorization

The circuit breaker classifies exceptions into different categories, each with a specific cooldown strategy:

| Category | Typical Cause | Cooldown Period |
|----------|---------------|-----------------|
| `QUOTA_EXHAUSTED` | 429 Errors / Resource Exhausted | 12 Hours |
| `MODEL_NOT_FOUND` | Incorrect model names / Deprecated models | 1 Hour |
| `RATE_LIMITED` | Transient high-frequency usage | 30 Seconds |
| `AUTHENTICATION` | Invalid API Keys / Permissions | 2 Hours |
| `TRANSIENT` | Network timeouts / Connection issues | 10 Seconds |
| `UNKNOWN` | Unexpected server-side errors | 1 Minute |

## How it Works

1. **Pre-Check**: Before calling an LLM, the `ModelManager` queries `is_available(model_name)`.
2. **Failure Recording**: If a model call fails, `record_failure(model_name, error)` is called.
3. **Cooldown**: The model is marked as "open" (unavailable). Consecutive failures lead to exponential backoff (up to 4x the base cooldown).
4. **Reset**: After the cooldown period expires, the circuit resets, allowing the model to be tried again.

## Benefits

- **Quota Preservation**: Stops calling models that have already reported quota exhaustion.
- **Improved UX**: Automatically skips "dead" models and proceeds to fallbacks instantly, rather than waiting for multiple timeouts.
- **Self-Healing**: Models are automatically reintroduced once their recovery period (or rate-limit window) is likely to have passed.

## Usage Example

```python
from llm.model_circuit_breaker import get_model_circuit_breaker

cb = get_model_circuit_breaker()

if cb.is_available("gemini-1.5-pro"):
    try:
        response = await model.invoke(prompt)
    except Exception as e:
        cb.record_failure("gemini-1.5-pro", e)
```

---
*The circuit breaker is a singleton instance (`get_model_circuit_breaker()`) ensuring consistent failure tracking across the entire bot process.*
