"""Offline chat provider adapter for R2C-A fake transport conformance."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from datang_extensions.llm_gateway.contracts import (
    GATEWAY_CONTRACT_VERSION,
    REQUEST_SCHEMA_VERSION,
    RESPONSE_SCHEMA_VERSION,
    find_forbidden_key,
    stable_json_hash,
)
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_adapters.budget import estimate_cost_usd, estimate_tokens
from datang_extensions.llm_gateway.provider_adapters.contracts import (
    ADAPTER_CONTRACT_VERSION,
    ADAPTER_STAGE,
    ALLOWED_FINISH_REASONS,
    NON_RETRYABLE_STATUS_CODES,
    PROVIDER_RESPONSE_SCHEMA_VERSION,
    RETRYABLE_STATUS_CODES,
    R2C_CREDENTIAL_FIELDS,
    R2C_FORBIDDEN_TRADING_FIELDS,
    SAFE_EXTERNAL_CALLS,
    ProviderAdapterConfig,
    ProviderAdapterContractError,
    adapter_error,
    load_provider_adapter_config,
    scan_forbidden_fields,
)
from datang_extensions.llm_gateway.provider_adapters.redaction import redact_sensitive_mapping, safe_error_message, safe_headers
from datang_extensions.llm_gateway.provider_adapters.transport import ProviderTransport

ALLOWED_PARAMETER_KEYS = frozenset({"temperature", "max_output_tokens", "seed"})
CALLER_TRANSPORT_KEYS = frozenset({"endpoint", "headers", "tools", "functions", "function_call", "tool_choice", "stream", "streaming", "response_format"})


class ProviderAdapterExecutionError(RuntimeError):
    """Raised when the adapter is used through the R2A provider protocol."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _base_result(
    request: Mapping[str, Any] | None,
    config: ProviderAdapterConfig | None,
    errors: list[dict[str, str]],
    *,
    wire_request: Mapping[str, Any] | None = None,
    wire_response: Mapping[str, Any] | None = None,
    provider_response: Mapping[str, Any] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    request_map = request or {}
    config_provider_id = config.provider_id if config else str(request_map.get("provider_id", ""))
    config_model_id = config.model_id if config else str(request_map.get("model_id", ""))
    provider_response_map = dict(provider_response or {})
    usage = provider_response_map.get("usage") if isinstance(provider_response_map.get("usage"), Mapping) else {}
    result = {
        "stage": ADAPTER_STAGE,
        "adapter_contract_version": config.adapter_contract_version if config else ADAPTER_CONTRACT_VERSION,
        "passed": False,
        "request_id": str(request_map.get("request_id", "")),
        "request_hash": stable_json_hash(request_map) if request_map else "",
        "provider_id": config_provider_id,
        "model_id": config_model_id,
        "model_version": config.model_version if config else str(request_map.get("model_version", "")),
        "adapter_id": config.adapter_id if config else "",
        "adapter_version": config.adapter_version if config else "",
        "transport_kind": config.transport_kind if config else "",
        "live_mode_enabled": False,
        "credential_binding_present": bool(config.credential_binding_id) if config else False,
        "credential_value_resolved": False,
        "wire_request_hash": str((wire_request or {}).get("wire_request_hash", "")),
        "idempotency_key": str((wire_request or {}).get("idempotency_key", "")),
        "wire_response_hash": stable_json_hash(redact_sensitive_mapping(wire_response or {})) if wire_response else "",
        "normalized_response_hash": stable_json_hash(provider_response_map) if provider_response_map else "",
        "usage": dict(usage) if isinstance(usage, Mapping) else {},
        "cost": {"currency": "USD", "amount": "0"},
        "retry_count": retry_count,
        "finish_reason": str(provider_response_map.get("finish_reason", "")),
        "attempts": attempts or [],
        "external_calls": dict(SAFE_EXTERNAL_CALLS),
        "provider_response": {},
        "audit": {},
        "warnings": [],
        "errors": errors,
    }
    result["audit"] = _audit_record(result)
    return result


def _audit_record(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "audit_schema_version": "1.0",
        "request_id": str(result.get("request_id", "")),
        "request_hash": str(result.get("request_hash", "")),
        "provider_id": str(result.get("provider_id", "")),
        "model_id": str(result.get("model_id", "")),
        "model_version": str(result.get("model_version", "")),
        "adapter_id": str(result.get("adapter_id", "")),
        "adapter_version": str(result.get("adapter_version", "")),
        "transport_kind": str(result.get("transport_kind", "")),
        "live_mode_enabled": False,
        "credential_binding_present": bool(result.get("credential_binding_present", False)),
        "credential_value_resolved": False,
        "wire_request_hash": str(result.get("wire_request_hash", "")),
        "idempotency_key": str(result.get("idempotency_key", "")),
        "wire_response_hash": str(result.get("wire_response_hash", "")),
        "normalized_response_hash": str(result.get("normalized_response_hash", "")),
        "retry_count": int(result.get("retry_count", 0)),
        "attempt_count": len(result.get("attempts", [])) if isinstance(result.get("attempts"), list) else 0,
        "passed": bool(result.get("passed", False)),
        "error_codes": [str(error.get("code", "")) for error in result.get("errors", []) if isinstance(error, Mapping)],
        "external_calls": dict(SAFE_EXTERNAL_CALLS),
    }


def _success_result(
    request: Mapping[str, Any],
    config: ProviderAdapterConfig,
    wire_request: Mapping[str, Any],
    wire_response: Mapping[str, Any],
    provider_response: Mapping[str, Any],
    attempts: list[dict[str, Any]],
    retry_count: int,
) -> dict[str, Any]:
    usage = provider_response["usage"]
    total_tokens = int(usage["total_tokens"])
    result = _base_result(
        request,
        config,
        [],
        wire_request=wire_request,
        wire_response=wire_response,
        provider_response=provider_response,
        attempts=attempts,
        retry_count=retry_count,
    )
    result.update(
        {
            "passed": True,
            "usage": dict(usage),
            "cost": {"currency": "USD", "amount": str(estimate_cost_usd(total_tokens))},
            "finish_reason": str(provider_response["finish_reason"]),
            "provider_response": copy.deepcopy(dict(provider_response)),
            "errors": [],
        }
    )
    result["audit"] = _audit_record(result)
    return result


def build_expected_adapter_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": result.get("stage", ""),
        "adapter_contract_version": result.get("adapter_contract_version", ""),
        "passed": result.get("passed", False),
        "request_id": result.get("request_id", ""),
        "request_hash": result.get("request_hash", ""),
        "provider_id": result.get("provider_id", ""),
        "model_id": result.get("model_id", ""),
        "model_version": result.get("model_version", ""),
        "adapter_id": result.get("adapter_id", ""),
        "adapter_version": result.get("adapter_version", ""),
        "transport_kind": result.get("transport_kind", ""),
        "live_mode_enabled": result.get("live_mode_enabled", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "wire_request_hash": result.get("wire_request_hash", ""),
        "idempotency_key": result.get("idempotency_key", ""),
        "wire_response_hash": result.get("wire_response_hash", ""),
        "normalized_response_hash": result.get("normalized_response_hash", ""),
        "usage": copy.deepcopy(result.get("usage", {})),
        "cost": copy.deepcopy(result.get("cost", {})),
        "retry_count": result.get("retry_count", 0),
        "finish_reason": result.get("finish_reason", ""),
        "provider_response": copy.deepcopy(result.get("provider_response", {})),
        "external_calls": copy.deepcopy(result.get("external_calls", {})),
        "errors": copy.deepcopy(result.get("errors", [])),
    }


class ChatProviderAdapter:
    """R2A-compatible provider adapter backed only by a fake transport."""

    def __init__(self, config: ProviderAdapterConfig, transport: ProviderTransport) -> None:
        self.config = config
        self.transport = transport
        self.provider_id = config.provider_id
        self.adapter_id = config.adapter_id
        self.adapter_version = config.adapter_version
        self.last_result: dict[str, Any] | None = None

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        result = run_provider_adapter(request, provider_config=self.config, transport=self.transport)
        self.last_result = result
        if result.get("passed") is not True:
            raise ProviderAdapterExecutionError(list(result.get("errors", [])))
        return dict(result["provider_response"])

    def build_wire_request(self, request: Mapping[str, Any], *, attempt_number: int) -> dict[str, Any]:
        errors = _validate_provider_request(request, self.config)
        if errors:
            raise ProviderAdapterContractError(errors)
        payload = request.get("input_payload") if isinstance(request.get("input_payload"), Mapping) else {}
        system_prompt = str(payload.get("system_prompt") or "You are an offline research-only provider adapter.")
        user_prompt = str(payload.get("user_prompt") or payload.get("research_context") or "")
        parameters = request["parameters"]
        body = {
            "model": self.config.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": parameters["temperature"],
            "max_tokens": parameters["max_output_tokens"],
            "seed": parameters["seed"],
        }
        base = {
            "method": "POST",
            "endpoint": {
                "scheme": self.config.endpoint_policy.scheme,
                "host": self.config.endpoint_policy.host,
                "path": self.config.endpoint_policy.path,
                "allow_redirects": False,
                "allow_proxy": False,
            },
            "headers": {
                "content-type": "application/json",
                "x-adapter-id": self.config.adapter_id,
            },
            "canonical_body": body,
            "timeout_ms": self.config.limits.timeout_ms,
        }
        wire_hash = stable_json_hash(base)
        idempotency_key = stable_json_hash(
            {
                "adapter_id": self.config.adapter_id,
                "adapter_version": self.config.adapter_version,
                "wire_request_hash": wire_hash,
            }
        )
        return {
            **base,
            "wire_request_hash": wire_hash,
            "idempotency_key": idempotency_key,
            "attempt_number": attempt_number,
        }


def _validate_provider_request(request: Mapping[str, Any], config: ProviderAdapterConfig) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for key in request:
        if str(key) in CALLER_TRANSPORT_KEYS:
            errors.append(adapter_error("provider_request_rejected", "caller cannot inject provider transport fields", field_path=str(key)))
    parameters = request.get("parameters")
    if not isinstance(parameters, Mapping):
        errors.append(adapter_error("provider_request_rejected", "parameters must be an object", field_path="parameters"))
    else:
        for key in parameters:
            if str(key) not in ALLOWED_PARAMETER_KEYS:
                errors.append(adapter_error("unknown_provider_parameter", "unknown provider parameter is not allowed", field_path=f"parameters.{key}"))
        if parameters.get("temperature") != 0:
            errors.append(adapter_error("provider_request_rejected", "temperature must be deterministic", field_path="parameters.temperature"))
        if not isinstance(parameters.get("max_output_tokens"), int):
            errors.append(adapter_error("provider_request_rejected", "max_output_tokens must be an integer", field_path="parameters.max_output_tokens"))
        if not isinstance(parameters.get("seed"), int):
            errors.append(adapter_error("provider_request_rejected", "seed must be an integer", field_path="parameters.seed"))
    payload = request.get("input_payload")
    if isinstance(payload, Mapping):
        for key in payload:
            if str(key) in CALLER_TRANSPORT_KEYS:
                errors.append(adapter_error("provider_request_rejected", "caller cannot inject provider transport fields", field_path=f"input_payload.{key}"))
        errors.extend(scan_forbidden_fields(payload, "input_payload"))
    else:
        errors.append(adapter_error("provider_request_rejected", "input_payload must be an object", field_path="input_payload"))
    if request.get("provider_id") != config.provider_id:
        errors.append(adapter_error("provider_identity_mismatch", "request provider_id must match adapter config", field_path="provider_id"))
    if request.get("model_id") != config.model_id:
        errors.append(adapter_error("model_identity_mismatch", "request model_id must match adapter config", field_path="model_id"))
    if request.get("model_version") != config.model_version:
        errors.append(adapter_error("model_identity_mismatch", "request model_version must match adapter config", field_path="model_version"))
    return errors


def _preflight_budget(request: Mapping[str, Any], config: ProviderAdapterConfig) -> list[dict[str, str]]:
    payload = request.get("input_payload") if isinstance(request.get("input_payload"), Mapping) else {}
    text = " ".join(str(payload.get(key, "")) for key in ("system_prompt", "user_prompt", "research_context"))
    input_tokens = estimate_tokens(text)
    parameters = request.get("parameters") if isinstance(request.get("parameters"), Mapping) else {}
    output_tokens = int(parameters.get("max_output_tokens") or 0)
    total_tokens = input_tokens + output_tokens
    errors: list[dict[str, str]] = []
    if input_tokens > config.limits.max_input_tokens:
        errors.append(adapter_error("token_budget_exceeded", "input token budget exceeded", field_path="limits.max_input_tokens"))
    if output_tokens > config.limits.max_output_tokens:
        errors.append(adapter_error("token_budget_exceeded", "output token budget exceeded", field_path="limits.max_output_tokens"))
    if total_tokens > config.limits.max_total_tokens:
        errors.append(adapter_error("token_budget_exceeded", "total token budget exceeded", field_path="limits.max_total_tokens"))
    if estimate_cost_usd(total_tokens) > config.limits.max_cost_usd:
        errors.append(adapter_error("cost_budget_exceeded", "synthetic cost budget exceeded", field_path="limits.max_cost_usd"))
    return errors


def _transport_attempt_audit(attempt_number: int, wire_request: Mapping[str, Any], response: Mapping[str, Any], *, retryable: bool, error_code: str = "") -> dict[str, Any]:
    return {
        "attempt_number": attempt_number,
        "wire_request_hash": str(wire_request.get("wire_request_hash", "")),
        "idempotency_key": str(wire_request.get("idempotency_key", "")),
        "status_code": int(response.get("status_code", 0) or 0),
        "timeout": bool(response.get("timeout", False)),
        "retryable": retryable,
        "error_code": error_code,
        "planned_delay_ms": 0,
        "elapsed_ms": int(response.get("elapsed_ms", 0) or 0),
        "response_headers": safe_headers(response.get("headers") if isinstance(response.get("headers"), Mapping) else {}),
    }


def _status_error(status_code: int) -> tuple[str, bool]:
    if status_code == 400:
        return "provider_invalid_request", False
    if status_code == 401:
        return "provider_authentication_failed", False
    if status_code == 403:
        return "provider_permission_denied", False
    if status_code == 404:
        return "provider_not_found", False
    if status_code in RETRYABLE_STATUS_CODES:
        return "provider_retryable_error", True
    return "provider_response_invalid", False


def _parse_body(response: Mapping[str, Any], config: ProviderAdapterConfig) -> tuple[Mapping[str, Any] | None, list[dict[str, str]]]:
    body = response.get("body")
    if isinstance(body, str):
        if len(body.encode("utf-8")) > config.limits.max_response_bytes:
            return None, [adapter_error("response_size_exceeded", "provider response exceeds byte budget", field_path="body")]
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None, [adapter_error("provider_malformed_json", "provider response JSON is malformed", field_path="body")]
    elif isinstance(body, Mapping):
        body_text = _canonical_json(body)
        if len(body_text.encode("utf-8")) > config.limits.max_response_bytes:
            return None, [adapter_error("response_size_exceeded", "provider response exceeds byte budget", field_path="body")]
        parsed = dict(body)
    else:
        return None, [adapter_error("provider_response_invalid", "provider body must be object or JSON string", field_path="body")]
    if not isinstance(parsed, Mapping):
        return None, [adapter_error("provider_response_invalid", "provider body must decode to an object", field_path="body")]
    return parsed, []


def _normalize_response(request: Mapping[str, Any], config: ProviderAdapterConfig, response: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if response.get("timeout") is True:
        return None, [adapter_error("provider_timeout", "provider timeout", field_path="transport.timeout")]
    status_code = int(response.get("status_code", 0) or 0)
    if status_code != 200:
        code, _retryable = _status_error(status_code)
        return None, [adapter_error(code, safe_error_message(response.get("body", "")), field_path="status_code")]
    body, parse_errors = _parse_body(response, config)
    if parse_errors:
        return None, parse_errors
    assert body is not None
    errors = scan_forbidden_fields(body, "body")
    if body.get("model") != config.model_id:
        errors.append(adapter_error("model_identity_mismatch", "wire response model does not match config", field_path="body.model"))
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        errors.append(adapter_error("provider_response_invalid", "provider response must contain one choice", field_path="body.choices"))
        return None, errors
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping) or message.get("role") != "assistant":
        errors.append(adapter_error("provider_response_invalid", "choice message must be assistant", field_path="body.choices[0].message"))
        return None, errors
    content = message.get("content")
    if not isinstance(content, Mapping):
        errors.append(adapter_error("provider_response_invalid", "assistant content must be an object", field_path="body.choices[0].message.content"))
        return None, errors
    errors.extend(scan_forbidden_fields(content, "content"))
    for field in ("research_only", "not_a_trading_signal", "no_trading_decision"):
        if content.get(field) is not True:
            errors.append(adapter_error("provider_response_invalid", f"{field} must be true", field_path=f"content.{field}"))
    finish_reason = str(choice.get("finish_reason", ""))
    if finish_reason not in ALLOWED_FINISH_REASONS:
        errors.append(adapter_error("provider_response_invalid", "finish reason is not allowed", field_path="body.choices[0].finish_reason"))
    usage = body.get("usage")
    if not isinstance(usage, Mapping):
        errors.append(adapter_error("usage_validation_failed", "usage must be an object", field_path="body.usage"))
        return None, errors
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(isinstance(value, int) and value >= 0 for value in (prompt_tokens, completion_tokens, total_tokens)):
        errors.append(adapter_error("usage_validation_failed", "usage tokens must be non-negative integers", field_path="body.usage"))
    elif total_tokens != prompt_tokens + completion_tokens:
        errors.append(adapter_error("usage_validation_failed", "total tokens must equal prompt plus completion", field_path="body.usage.total_tokens"))
    elif total_tokens > config.limits.max_total_tokens or completion_tokens > config.limits.max_output_tokens:
        errors.append(adapter_error("token_budget_exceeded", "provider usage exceeds configured token budget", field_path="body.usage"))
    if estimate_cost_usd(int(total_tokens or 0)) > config.limits.max_cost_usd:
        errors.append(adapter_error("cost_budget_exceeded", "provider usage exceeds synthetic cost budget", field_path="body.usage.total_tokens"))
    if errors:
        return None, errors
    provider_response = {
        "response_schema_version": RESPONSE_SCHEMA_VERSION,
        "provider_id": config.provider_id,
        "model_id": config.model_id,
        "model_version": config.model_version,
        "request_id": str(request.get("request_id", "")),
        "content": copy.deepcopy(dict(content)),
        "usage": {
            "input_tokens": int(prompt_tokens),
            "output_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
        },
        "finish_reason": finish_reason,
        "provider_metadata": {
            "adapter_id": config.adapter_id,
            "adapter_version": config.adapter_version,
            "transport_kind": "fake",
            "wire_response_id": str(body.get("id", "")),
            "response_headers": safe_headers(response.get("headers") if isinstance(response.get("headers"), Mapping) else {}),
        },
    }
    return provider_response, []


def run_provider_adapter(
    request: Mapping[str, Any],
    *,
    provider_config: Mapping[str, Any] | ProviderAdapterConfig,
    transport: ProviderTransport,
) -> dict[str, Any]:
    config = provider_config if isinstance(provider_config, ProviderAdapterConfig) else load_provider_adapter_config(provider_config)
    request_map = copy.deepcopy(dict(request)) if isinstance(request, Mapping) else {}
    if not isinstance(request, Mapping):
        return _base_result({}, config, [adapter_error("invalid_provider_request", "request must be an object")])
    adapter = ChatProviderAdapter(config, transport)
    budget_errors = _preflight_budget(request_map, config)
    if budget_errors:
        return _base_result(request_map, config, budget_errors)
    try:
        initial_wire_request = adapter.build_wire_request(request_map, attempt_number=1)
    except ProviderAdapterContractError as exc:
        return _base_result(request_map, config, list(exc.errors))
    attempts: list[dict[str, Any]] = []
    last_wire_request: dict[str, Any] = initial_wire_request
    last_wire_response: Mapping[str, Any] | None = None
    last_errors: list[dict[str, str]] = []
    retry_count = 0
    for attempt_number in range(1, config.limits.max_attempts + 1):
        wire_request = adapter.build_wire_request(request_map, attempt_number=attempt_number)
        last_wire_request = wire_request
        wire_response = dict(transport.send(wire_request))
        last_wire_response = wire_response
        status_code = int(wire_response.get("status_code", 0) or 0)
        timeout = bool(wire_response.get("timeout", False))
        retryable = timeout or status_code in RETRYABLE_STATUS_CODES
        provider_response, errors = _normalize_response(request_map, config, wire_response)
        if provider_response is not None and not errors:
            attempts.append(_transport_attempt_audit(attempt_number, wire_request, wire_response, retryable=False))
            return _success_result(request_map, config, wire_request, wire_response, provider_response, attempts, retry_count)
        last_errors = errors
        error_code = errors[0]["code"] if errors else "provider_response_invalid"
        if retryable and attempt_number < config.limits.max_attempts:
            attempts.append(_transport_attempt_audit(attempt_number, wire_request, wire_response, retryable=True, error_code=error_code))
            retry_count += 1
            continue
        if retryable:
            last_errors = [adapter_error("provider_retry_exhausted", "retryable provider error exhausted configured attempts", field_path="attempts")]
        attempts.append(_transport_attempt_audit(attempt_number, wire_request, wire_response, retryable=retryable, error_code=last_errors[0]["code"] if last_errors else error_code))
        break
    return _base_result(
        request_map,
        config,
        last_errors or [adapter_error("provider_response_invalid", "provider adapter failed")],
        wire_request=last_wire_request,
        wire_response=last_wire_response,
        attempts=attempts,
        retry_count=retry_count,
    )
