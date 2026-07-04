"""Provider transport protocol for R2C-A."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class ProviderTransport(Protocol):
    """Transport boundary consumed by provider adapters."""

    transport_kind: str

    def send(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a provider-shaped transport result for a wire request."""

        ...
