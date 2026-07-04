"""Redaction helpers for R2C-A provider adapter audits."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_HEADER_KEYS = frozenset({"authorization", "cookie", "set-cookie", "x-api-key"})
SENSITIVE_VALUE_MARKERS = ("Bearer ", "sk-", "api_key", "token", "secret", "password")


def safe_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return a small allowlisted header view."""

    if not isinstance(headers, Mapping):
        return {}
    allowed = {"content-type", "x-request-id"}
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key).lower()
        if key_text in allowed and key_text not in SENSITIVE_HEADER_KEYS:
            sanitized[key_text] = str(value)
    return sanitized


def redact_sensitive_mapping(value: Any) -> Any:
    """Recursively remove credential-like header keys without echoing values."""

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_HEADER_KEYS:
                continue
            sanitized[key_text] = redact_sensitive_mapping(nested)
        return sanitized
    if isinstance(value, list):
        return [redact_sensitive_mapping(item) for item in value]
    if isinstance(value, str) and any(marker.lower() in value.lower() for marker in SENSITIVE_VALUE_MARKERS):
        return "<redacted>"
    return value


def safe_error_message(message: object) -> str:
    text = str(message)
    if any(marker.lower() in text.lower() for marker in SENSITIVE_VALUE_MARKERS):
        return "provider error redacted"
    return text[:160]
