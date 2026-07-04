"""Deterministic fake LLM provider for R2A offline gateway tests."""

from __future__ import annotations

from typing import Any, Mapping

from datang_extensions.llm_gateway.contracts import stable_json_hash


class DeterministicFakeProvider:
    """Offline provider that derives stable content from the canonical request."""

    provider_id = "fake"

    def __init__(self, fixture_map: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._fixture_map = dict(fixture_map or {})

    def generate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        payload = request.get("input_payload")
        mode = payload.get("fake_provider_mode") if isinstance(payload, Mapping) else None
        if mode == "raise":
            raise RuntimeError("synthetic_provider_failure")
        if mode == "invalid_response":
            return {
                "response_schema_version": "1.0",
                "provider_id": request.get("provider_id", ""),
                "model_id": request.get("model_id", ""),
                "model_version": request.get("model_version", ""),
                "request_id": request.get("request_id", ""),
                "content": {"summary": "Synthetic invalid response."},
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "finish_reason": "stop",
                "provider_metadata": {"fake_provider": True, "mode": "invalid_response"},
            }

        case_id = str(request.get("case_id", ""))
        if case_id in self._fixture_map:
            response = dict(self._fixture_map[case_id])
            response["request_id"] = request.get("request_id", "")
            return response

        request_hash = stable_json_hash(request)
        summary = f"Deterministic fake research summary for {case_id} ({request_hash[:12]})."
        input_tokens = max(1, len(stable_json_hash(request.get("input_payload", {}))) // 8)
        output_tokens = 18 + (int(request_hash[:2], 16) % 7)
        return {
            "response_schema_version": "1.0",
            "provider_id": request.get("provider_id", ""),
            "model_id": request.get("model_id", ""),
            "model_version": request.get("model_version", ""),
            "request_id": request.get("request_id", ""),
            "content": {
                "summary": summary,
                "bull_case": [f"Synthetic bull case hash={request_hash[:8]}"],
                "bear_case": [f"Synthetic bear case hash={request_hash[8:16]}"],
                "key_risks": ["Synthetic R2A contract risk only."],
                "uncertainties": ["Synthetic R2A uncertainty only."],
                "evidence_refs": list((request.get("input_payload") or {}).get("evidence_refs") or []),
                "research_only": True,
                "not_a_trading_signal": True,
                "no_trading_decision": True,
            },
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "finish_reason": "stop",
            "provider_metadata": {
                "fake_provider": True,
                "deterministic_rule": "request_hash_prefix",
            },
        }
