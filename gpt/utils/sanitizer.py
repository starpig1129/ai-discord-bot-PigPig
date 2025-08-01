# -*- coding: utf-8 -*-
"""Tools for sanitizing and masking sensitive information from logs."""

import re
from typing import Any, Dict, List, Set, Union

# Regex patterns for common secrets, inspired by trufflehog
# This is a basic set and not exhaustive.
SECRET_PATTERNS = {
    "URL with credentials": re.compile(r"https?://[^:]+:[^@]+@\w+"),
    "Email": re.compile(r"[\w\.-]+@[\w\.-]+"),
    "IP Address": re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"),
}
DEFAULT_SENSITIVE_KEYS = {"token", "api_key", "auth", "cookie", "session", "password", "secret"}

def mask_text(text: str, max_len: int = 256) -> str:
    """Masks secrets in a text and truncates it for safe logging.

    Args:
        text: The input string to sanitize.
        max_len: The maximum length of the returned string.

    Returns:
        A sanitized and truncated string.
    """
    if not isinstance(text, str):
        text = str(text)

    # Mask common patterns
    for pattern in SECRET_PATTERNS.values():
        text = pattern.sub("****", text)

    # Truncate the text if it's too long
    if len(text) > max_len:
        return f"{text[:max_len//2]}...{text[-max_len//2:]}"
    return text

def mask_json(data: Any, sensitive_keys: Set[str] = DEFAULT_SENSITIVE_KEYS) -> Any:
    """Recursively masks sensitive values in a JSON-like object.

    Args:
        data: The dict or list to sanitize.
        sensitive_keys: A set of keys to consider sensitive.

    Returns:
        A new object with sensitive values masked.
    """
    if isinstance(data, dict):
        return {
            key: "****" if key in sensitive_keys else mask_json(value, sensitive_keys)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [mask_json(item, sensitive_keys) for item in data]
    return data