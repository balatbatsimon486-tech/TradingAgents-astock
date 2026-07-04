"""Deterministic fake transport for R2C-A provider adapter conformance."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping


class FakeProviderTransport:
    """Fixture-backed transport that never opens sockets or reads secrets."""

    transport_kind = "fake"

    def __init__(self, fixtures: Mapping[str, list[Mapping[str, Any]]]) -> None:
        self._fixtures = {str(key): [copy.deepcopy(dict(item)) for item in value] for key, value in fixtures.items()}
        self._counts: dict[str, int] = {}

    def send(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request_hash = str(request.get("wire_request_hash", ""))
        sequence = self._fixtures.get(request_hash) or self._fixtures.get("default") or []
        if not sequence:
            return {
                "status_code": 500,
                "headers": {"Content-Type": "application/json"},
                "body": {"error": {"message": "missing fake transport fixture"}},
                "elapsed_ms": 0,
                "timeout": False,
                "transport_error": "missing_fixture",
            }
        index = self._counts.get(request_hash, 0)
        self._counts[request_hash] = index + 1
        return copy.deepcopy(dict(sequence[min(index, len(sequence) - 1)]))


def load_fake_transport_from_directory(path: str | Path) -> FakeProviderTransport:
    root = Path(path)
    if not root.is_dir():
        raise ValueError("fixture map must be a directory")
    fixtures: dict[str, list[dict[str, Any]]] = {}
    for file_path in sorted(root.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        key = str(payload.get("request_hash") or file_path.stem)
        if isinstance(payload, Mapping) and isinstance(payload.get("sequence"), list):
            fixtures[key] = [dict(item) for item in payload["sequence"] if isinstance(item, Mapping)]
        elif isinstance(payload, Mapping):
            fixtures[key] = [dict(payload)]
    return FakeProviderTransport(fixtures)
