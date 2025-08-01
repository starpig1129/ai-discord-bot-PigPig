# -*- coding: utf-8 -*-
from typing import Any, Dict, Optional, Set

# Retryable error codes
RETRYABLE_CODES: Set[str] = {
    "network_timeout",
    "connection_error",
    "dns_error",
    "rate_limited",
    "server_overload",
    "gateway_error",
    "provider_unavailable",
}

# Non-retryable error codes
NON_RETRYABLE_CODES: Set[str] = {
    "invalid_request",
    "auth_failed",
    "quota_exceeded",
    "unsupported_model",
    "content_filter_block",
    "input_too_large",
    "malformed_response",
}


class LLMProviderError(Exception):
    """Unified provider exception for centralized handling."""

    def __init__(
        self,
        code: str,
        retriable: bool,
        status: Optional[int],
        provider: str,
        details: Dict[str, Any],
        trace_id: str,
    ) -> None:
        super().__init__(f"[{provider}] {code}")
        self.code: str = code
        self.retriable: bool = retriable
        self.status: Optional[int] = status
        self.provider: str = provider
        self.details: Dict[str, Any] = details
        self.trace_id: str = trace_id


def is_retryable(code: str) -> bool:
    """Check if an error code is retryable by policy."""
    return code in RETRYABLE_CODES