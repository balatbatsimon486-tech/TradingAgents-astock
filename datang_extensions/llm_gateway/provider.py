"""Provider protocol for the offline R2A LLM gateway."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class LLMProvider(Protocol):
    """Minimal provider interface consumed by the gateway."""

    provider_id: str

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Generate a structured provider response for a validated request."""

        ...
