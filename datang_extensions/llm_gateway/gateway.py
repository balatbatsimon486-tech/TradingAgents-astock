"""Offline auditable LLM gateway for R2A."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.contracts import (
    EXTERNAL_CALLS,
    GATEWAY_CONTRACT_VERSION,
    GATEWAY_STAGE,
    canonical_copy,
    normalized_response,
    stable_json_hash,
    validate_request,
    validate_response,
)
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.fake_provider import DeterministicFakeProvider
from datang_extensions.llm_gateway.provider import LLMProvider


def _empty_result(
    request: Mapping[str, Any] | None,
    errors: list[dict[str, str]],
    *,
    response: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    request_map = request or {}
    response_map = response or {}
    usage = response_map.get("usage") if isinstance(response_map.get("usage"), Mapping) else {}
    finish_reason = str(response_map.get("finish_reason", ""))
    return {
        "stage": GATEWAY_STAGE,
        "gateway_contract_version": str(request_map.get("gateway_contract_version", GATEWAY_CONTRACT_VERSION)),
        "passed": False,
        "request_id": str(request_map.get("request_id", "")),
        "request_hash": stable_json_hash(request_map) if request_map else "",
        "response_hash": stable_json_hash(response_map) if response_map else "",
        "normalized_response_hash": stable_json_hash(normalized_response(response_map)) if response_map else "",
        "provider_id": str(request_map.get("provider_id", "")),
        "model_id": str(request_map.get("model_id", "")),
        "model_version": str(request_map.get("model_version", "")),
        "prompt_id": str(request_map.get("prompt_id", "")),
        "prompt_version": str(request_map.get("prompt_version", "")),
        "snapshot_id": str(request_map.get("snapshot_id", "")),
        "input_artifact_id": str(request_map.get("input_artifact_id", "")),
        "input_artifact_hash": str(request_map.get("input_artifact_hash", "")),
        "usage": dict(usage) if isinstance(usage, Mapping) else {},
        "cost": {"currency": "USD", "amount": 0},
        "latency": {"duration_ms": 0},
        "retry_count": 0,
        "finish_reason": finish_reason,
        "external_calls": dict(EXTERNAL_CALLS),
        "response": {},
        "audit": _audit_record(request_map, response_map, errors, passed=False),
        "warnings": [],
        "errors": errors,
    }


def _audit_record(
    request: Mapping[str, Any],
    response: Mapping[str, Any],
    errors: list[dict[str, str]],
    *,
    passed: bool,
) -> dict[str, Any]:
    return {
        "audit_schema_version": "1.0",
        "request_id": str(request.get("request_id", "")),
        "request_hash": stable_json_hash(request) if request else "",
        "response_hash": stable_json_hash(response) if response else "",
        "normalized_response_hash": stable_json_hash(normalized_response(response)) if response else "",
        "provider_id": str(request.get("provider_id", "")),
        "model_id": str(request.get("model_id", "")),
        "model_version": str(request.get("model_version", "")),
        "prompt_id": str(request.get("prompt_id", "")),
        "prompt_version": str(request.get("prompt_version", "")),
        "snapshot_id": str(request.get("snapshot_id", "")),
        "input_artifact_id": str(request.get("input_artifact_id", "")),
        "input_artifact_hash": str(request.get("input_artifact_hash", "")),
        "usage": dict(response.get("usage", {})) if isinstance(response.get("usage"), Mapping) else {},
        "cost": {"currency": "USD", "amount": 0},
        "retry_count": 0,
        "finish_reason": str(response.get("finish_reason", "")),
        "passed": passed,
        "error_codes": [error["code"] for error in errors],
        "external_calls": dict(EXTERNAL_CALLS),
    }


def run_llm_gateway(
    request: Mapping[str, Any],
    *,
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Validate a request, call the allowlisted fake provider, and audit the result."""

    if not isinstance(request, Mapping):
        return _empty_result({}, [gateway_error("invalid_gateway_request", "request must be an object")])

    request_copy = canonical_copy(dict(request))
    request_errors = validate_request(request_copy)
    if request_errors:
        return _empty_result(request_copy, request_errors)

    provider_instance = provider or DeterministicFakeProvider()
    provider_id = str(getattr(provider_instance, "provider_id", ""))
    if provider_id != request_copy.get("provider_id"):
        return _empty_result(
            request_copy,
            [
                gateway_error(
                    "provider_identity_mismatch",
                    "provider_id does not match request",
                    field_path="provider_id",
                )
            ],
        )

    try:
        provider_response = provider_instance.generate(canonical_copy(request_copy))
    except Exception as exc:
        return _empty_result(
            request_copy,
            [gateway_error("provider_execution_failed", type(exc).__name__)],
        )

    if not isinstance(provider_response, Mapping):
        return _empty_result(
            request_copy,
            [gateway_error("provider_response_invalid", "provider response must be an object")],
        )

    response_copy = canonical_copy(dict(provider_response))
    response_errors = validate_response(request_copy, response_copy)
    if response_errors:
        return _empty_result(request_copy, response_errors, response=response_copy)

    request_hash = stable_json_hash(request_copy)
    response_hash = stable_json_hash(response_copy)
    normalized_hash = stable_json_hash(normalized_response(response_copy))
    audit = _audit_record(request_copy, response_copy, [], passed=True)
    return {
        "stage": GATEWAY_STAGE,
        "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
        "passed": True,
        "request_id": str(request_copy["request_id"]),
        "request_hash": request_hash,
        "response_hash": response_hash,
        "normalized_response_hash": normalized_hash,
        "provider_id": str(request_copy["provider_id"]),
        "model_id": str(request_copy["model_id"]),
        "model_version": str(request_copy["model_version"]),
        "prompt_id": str(request_copy["prompt_id"]),
        "prompt_version": str(request_copy["prompt_version"]),
        "snapshot_id": str(request_copy["snapshot_id"]),
        "input_artifact_id": str(request_copy["input_artifact_id"]),
        "input_artifact_hash": str(request_copy["input_artifact_hash"]),
        "usage": dict(response_copy["usage"]),
        "cost": {"currency": "USD", "amount": 0},
        "latency": {"duration_ms": 0},
        "retry_count": 0,
        "finish_reason": str(response_copy["finish_reason"]),
        "external_calls": dict(EXTERNAL_CALLS),
        "response": response_copy,
        "audit": audit,
        "warnings": [],
        "errors": [],
    }
