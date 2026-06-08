"""Minimal cost tracking primitives for later LLM evaluation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCostUsage:
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def empty_usage(model: str = "") -> ModelCostUsage:
    return ModelCostUsage(model=model)

