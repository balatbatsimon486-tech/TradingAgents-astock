"""Structured error helpers for the offline R2A LLM gateway."""

from __future__ import annotations


def gateway_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    """Return a non-secret structured gateway error."""

    return {
        "code": code,
        "message": message,
        "field_path": field_path,
    }
