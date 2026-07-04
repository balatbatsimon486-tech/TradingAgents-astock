"""Deterministic offline budget checks for R2C-A."""

from __future__ import annotations

from decimal import Decimal


def estimate_tokens(text: str) -> int:
    """Return a stable conservative token estimate without model tokenizers."""

    return max(1, (len(text) + 3) // 4)


def estimate_cost_usd(total_tokens: int) -> Decimal:
    """Return a synthetic pre-execution cost estimate."""

    return Decimal(total_tokens) * Decimal("0.00001")
