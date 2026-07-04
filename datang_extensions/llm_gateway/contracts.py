"""Versioned offline LLM gateway contracts for R2A."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

from datang_extensions.evaluation.offline_research_evaluator import (
    CREDENTIAL_FIELDS as M2A_CREDENTIAL_FIELDS,
    EXTERNAL_CALLS_FALSE,
    FORBIDDEN_TRADING_FIELDS as M2A_FORBIDDEN_TRADING_FIELDS,
    stable_json_hash,
)
from datang_extensions.llm_gateway.errors import gateway_error

GATEWAY_STAGE = "tradingagents_r2a_offline_llm_gateway"
GATEWAY_CONTRACT_VERSION = "1.0"
REQUEST_SCHEMA_VERSION = "1.0"
RESPONSE_SCHEMA_VERSION = "1.0"
AUDIT_SCHEMA_VERSION = "1.0"

SUPPORTED_GATEWAY_CONTRACT_VERSIONS = frozenset({GATEWAY_CONTRACT_VERSION})
SUPPORTED_REQUEST_SCHEMA_VERSIONS = frozenset({REQUEST_SCHEMA_VERSION})
SUPPORTED_RESPONSE_SCHEMA_VERSIONS = frozenset({RESPONSE_SCHEMA_VERSION})
SUPPORTED_AUDIT_SCHEMA_VERSIONS = frozenset({AUDIT_SCHEMA_VERSION})

ALLOWED_PROVIDERS = frozenset({"fake"})
ALLOWED_MODELS = frozenset({"fake-deterministic-v1"})
ALLOWED_TASK_TYPES = frozenset({"research_generation"})
ALLOWED_FINISH_REASONS = frozenset({"stop", "length", "error"})
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_OUTPUT_TOKENS_MIN = 1
MAX_OUTPUT_TOKENS_MAX = 4096

CREDENTIAL_FIELDS = frozenset(
    set(M2A_CREDENTIAL_FIELDS)
    | {
        "access_token",
        "refresh_token",
        "cookie",
        "credential",
    }
)
FORBIDDEN_TRADING_FIELDS = frozenset(
    set(M2A_FORBIDDEN_TRADING_FIELDS)
    | {
        "signal",
        "recommendation",
        "strategy",
        "buy",
        "sell",
        "hold",
    }
)
NORMALIZED_RESPONSE_EXCLUDED_FIELDS = (
    "duration",
    "duration_ms",
    "latency",
    "created_at",
    "created_at_utc",
    "generated_at",
    "generated_at_utc",
)

EXTERNAL_CALLS = {
    "network_called": False,
    "market_data_called": False,
    "tushare_called": False,
    "qlib_called": False,
    "broker_called": False,
}


def canonical_copy(value: Any) -> Any:
    """Return a JSON-compatible deep copy used before hashing."""

    return copy.deepcopy(value)


def is_safe_identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and bool(SAFE_ID_RE.fullmatch(value))


def find_forbidden_key(value: Any, forbidden: frozenset[str], prefix: str = "") -> str:
    """Return the first forbidden key path without exposing field values."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text.strip().lower() in forbidden:
                return path
            found = find_forbidden_key(nested, forbidden, path)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_forbidden_key(item, forbidden, f"{prefix}[{index}]")
            if found:
                return found
    return ""


def normalized_response(response: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize provider responses for deterministic comparison."""

    excluded = set(NORMALIZED_RESPONSE_EXCLUDED_FIELDS)

    def normalize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): normalize(nested) for key, nested in sorted(value.items()) if key not in excluded}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(dict(response))


def validate_request(request: Mapping[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    gateway_version = str(request.get("gateway_contract_version", ""))
    request_version = str(request.get("request_schema_version", ""))
    if gateway_version not in SUPPORTED_GATEWAY_CONTRACT_VERSIONS:
        errors.append(gateway_error("unsupported_gateway_contract_version", "unsupported gateway contract version", field_path="gateway_contract_version"))
    if request_version not in SUPPORTED_REQUEST_SCHEMA_VERSIONS:
        errors.append(gateway_error("unsupported_request_schema_version", "unsupported request schema version", field_path="request_schema_version"))

    for field in (
        "request_id",
        "case_id",
        "snapshot_id",
        "input_artifact_id",
        "prompt_id",
        "prompt_version",
        "model_version",
    ):
        if not is_safe_identifier(request.get(field)):
            errors.append(gateway_error("invalid_gateway_request", f"{field} must be a safe non-empty identifier", field_path=field))

    if str(request.get("task_type", "")) not in ALLOWED_TASK_TYPES:
        errors.append(gateway_error("invalid_gateway_request", "task_type is not allowed", field_path="task_type"))

    artifact_hash = request.get("input_artifact_hash")
    if not isinstance(artifact_hash, str) or not SHA256_RE.fullmatch(artifact_hash):
        errors.append(gateway_error("invalid_input_artifact_hash", "input_artifact_hash must be a lowercase SHA-256", field_path="input_artifact_hash"))

    provider_id = request.get("provider_id")
    model_id = request.get("model_id")
    if provider_id not in ALLOWED_PROVIDERS:
        errors.append(gateway_error("provider_not_allowed", "provider is not allowlisted", field_path="provider_id"))
    if model_id not in ALLOWED_MODELS:
        errors.append(gateway_error("model_not_allowed", "model is not allowlisted", field_path="model_id"))

    parameters = request.get("parameters")
    if not isinstance(parameters, Mapping):
        errors.append(gateway_error("invalid_model_parameters", "parameters must be an object", field_path="parameters"))
    else:
        if parameters.get("temperature") != 0:
            errors.append(gateway_error("invalid_model_parameters", "temperature must be 0 for deterministic fake provider", field_path="parameters.temperature"))
        max_tokens = parameters.get("max_output_tokens")
        if not isinstance(max_tokens, int) or not MAX_OUTPUT_TOKENS_MIN <= max_tokens <= MAX_OUTPUT_TOKENS_MAX:
            errors.append(gateway_error("invalid_model_parameters", "max_output_tokens is outside the safe range", field_path="parameters.max_output_tokens"))
        if not isinstance(parameters.get("seed"), int):
            errors.append(gateway_error("invalid_model_parameters", "seed must be an integer", field_path="parameters.seed"))

    policy = request.get("policy")
    if not isinstance(policy, Mapping):
        errors.append(gateway_error("invalid_gateway_request", "policy must be an object", field_path="policy"))
    else:
        if policy.get("research_only") is not True:
            errors.append(gateway_error("invalid_gateway_request", "policy.research_only must be true", field_path="policy.research_only"))
        for field in ("allow_network", "allow_tools", "allow_market_data", "allow_trading_actions"):
            if policy.get(field) is not False:
                errors.append(gateway_error("invalid_gateway_request", f"policy.{field} must be false", field_path=f"policy.{field}"))

    input_payload = request.get("input_payload")
    if not isinstance(input_payload, Mapping):
        errors.append(gateway_error("invalid_gateway_request", "input_payload must be an object", field_path="input_payload"))
    else:
        credential_path = find_forbidden_key(input_payload, CREDENTIAL_FIELDS, "input_payload")
        if credential_path:
            errors.append(gateway_error("credential_field_detected", "credential-like field is not allowed", field_path=credential_path))
        trading_path = find_forbidden_key(input_payload, FORBIDDEN_TRADING_FIELDS, "input_payload")
        if trading_path:
            errors.append(gateway_error("forbidden_trading_field_detected", "trading execution field is not allowed", field_path=trading_path))

    return errors


def validate_response(
    request: Mapping[str, Any],
    response: Mapping[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    response_version = str(response.get("response_schema_version", ""))
    if response_version not in SUPPORTED_RESPONSE_SCHEMA_VERSIONS:
        errors.append(gateway_error("unsupported_response_schema_version", "unsupported response schema version", field_path="response_schema_version"))

    if response.get("provider_id") != request.get("provider_id"):
        errors.append(gateway_error("provider_identity_mismatch", "response provider_id does not match request", field_path="provider_id"))
    if response.get("model_id") != request.get("model_id"):
        errors.append(gateway_error("model_identity_mismatch", "response model_id does not match request", field_path="model_id"))
    if response.get("model_version") != request.get("model_version"):
        errors.append(gateway_error("model_identity_mismatch", "response model_version does not match request", field_path="model_version"))
    if response.get("request_id") != request.get("request_id"):
        errors.append(gateway_error("request_id_mismatch", "response request_id does not match request", field_path="request_id"))

    content = response.get("content")
    if not isinstance(content, Mapping):
        errors.append(gateway_error("provider_response_invalid", "response content must be an object", field_path="content"))
    else:
        for field in ("research_only", "not_a_trading_signal", "no_trading_decision"):
            if content.get(field) is not True:
                errors.append(gateway_error("provider_response_invalid", f"content.{field} must be true", field_path=f"content.{field}"))
        if not isinstance(content.get("evidence_refs"), list):
            errors.append(gateway_error("provider_response_invalid", "content.evidence_refs must be a list", field_path="content.evidence_refs"))
        credential_path = find_forbidden_key(content, CREDENTIAL_FIELDS, "content")
        if credential_path:
            errors.append(gateway_error("credential_field_detected", "credential-like field is not allowed", field_path=credential_path))
        trading_path = find_forbidden_key(content, FORBIDDEN_TRADING_FIELDS, "content")
        if trading_path:
            errors.append(gateway_error("forbidden_trading_field_detected", "trading execution field is not allowed", field_path=trading_path))

    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        errors.append(gateway_error("usage_validation_failed", "usage must be an object", field_path="usage"))
    else:
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if not all(isinstance(value, int) and value >= 0 for value in (input_tokens, output_tokens, total_tokens)):
            errors.append(gateway_error("usage_validation_failed", "usage tokens must be non-negative integers", field_path="usage"))
        elif total_tokens != input_tokens + output_tokens:
            errors.append(gateway_error("usage_validation_failed", "total_tokens must equal input_tokens + output_tokens", field_path="usage.total_tokens"))

    if response.get("finish_reason") not in ALLOWED_FINISH_REASONS:
        errors.append(gateway_error("provider_response_invalid", "finish_reason is not allowed", field_path="finish_reason"))

    metadata = response.get("provider_metadata", {})
    if metadata is not None and not isinstance(metadata, Mapping):
        errors.append(gateway_error("provider_response_invalid", "provider_metadata must be an object", field_path="provider_metadata"))
    else:
        credential_path = find_forbidden_key(metadata or {}, CREDENTIAL_FIELDS, "provider_metadata")
        if credential_path:
            errors.append(gateway_error("credential_field_detected", "credential-like field is not allowed", field_path=credential_path))
        trading_path = find_forbidden_key(metadata or {}, FORBIDDEN_TRADING_FIELDS, "provider_metadata")
        if trading_path:
            errors.append(gateway_error("forbidden_trading_field_detected", "trading execution field is not allowed", field_path=trading_path))

    return errors
