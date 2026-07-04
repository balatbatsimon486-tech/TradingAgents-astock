"""Provider adapter config and shared contracts for R2C-A."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from datang_extensions.llm_gateway.contracts import (
    CREDENTIAL_FIELDS,
    FORBIDDEN_TRADING_FIELDS,
    SAFE_ID_RE,
    find_forbidden_key,
    is_safe_identifier,
)
from datang_extensions.llm_gateway.errors import gateway_error

ADAPTER_STAGE = "tradingagents_r2c_offline_provider_adapter"
ADAPTER_CONTRACT_VERSION = "1.0"
SUPPORTED_ADAPTER_CONTRACT_VERSIONS = frozenset({ADAPTER_CONTRACT_VERSION})
ALLOWED_TRANSPORT_KINDS = frozenset({"fake"})
MAX_TIMEOUT_MS = 60_000
MAX_ATTEMPTS = 3
MAX_INPUT_TOKENS = 8192
MAX_OUTPUT_TOKENS = 4096
MAX_TOTAL_TOKENS = 12_000
MAX_RESPONSE_BYTES = 1_048_576
MAX_COST_USD = Decimal("10.00")
PROVIDER_RESPONSE_SCHEMA_VERSION = "1.0"
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404})
ALLOWED_FINISH_REASONS = frozenset({"stop", "length"})
SAFE_EXTERNAL_CALLS = {
    "network_called": False,
    "market_data_called": False,
    "tushare_called": False,
    "qlib_called": False,
    "broker_called": False,
}
R2C_CREDENTIAL_FIELDS = frozenset(set(CREDENTIAL_FIELDS) | {"authorization", "cookie", "set-cookie", "x-api-key"})
R2C_FORBIDDEN_TRADING_FIELDS = frozenset(
    set(FORBIDDEN_TRADING_FIELDS)
    | {
        "target_price",
        "target_weight",
        "position_size",
        "order",
        "broker",
        "auto_trade",
    }
)


class ProviderAdapterContractError(ValueError):
    """Raised when a provider adapter contract fails closed."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


@dataclass(frozen=True)
class EndpointPolicy:
    scheme: str
    host: str
    path: str
    allow_redirects: bool
    allow_proxy: bool


@dataclass(frozen=True)
class ProviderLimits:
    timeout_ms: int
    max_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    max_total_tokens: int
    max_response_bytes: int
    max_cost_usd: Decimal


@dataclass(frozen=True)
class ProviderAdapterConfig:
    adapter_contract_version: str
    adapter_id: str
    adapter_version: str
    provider_id: str
    model_id: str
    model_version: str
    enabled: bool
    live_mode_enabled: bool
    transport_kind: str
    endpoint_policy: EndpointPolicy
    credential_binding_id: str
    limits: ProviderLimits


def adapter_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def raise_adapter(code: str, message: str, *, field_path: str = "") -> None:
    raise ProviderAdapterContractError([adapter_error(code, message, field_path=field_path)])


def scan_forbidden_fields(value: Any, prefix: str = "") -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    credential_path = find_forbidden_key(value, R2C_CREDENTIAL_FIELDS, prefix)
    if credential_path:
        errors.append(adapter_error("credential_field_detected", "credential-like field is not allowed", field_path=credential_path))
    trading_path = find_forbidden_key(value, R2C_FORBIDDEN_TRADING_FIELDS, prefix)
    if trading_path:
        errors.append(adapter_error("forbidden_trading_field_detected", "trading execution field is not allowed", field_path=trading_path))
    return errors


def _decimal(value: Any, *, field_path: str, errors: list[dict[str, str]]) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(adapter_error("limit_out_of_range", "decimal limit is invalid", field_path=field_path))
        return Decimal("0")
    return parsed


def _safe_credential_binding(value: Any) -> bool:
    if not is_safe_identifier(value):
        return False
    text = str(value)
    lowered = text.lower()
    if lowered.startswith("env:") or lowered.startswith("sk-") or "bearer" in lowered:
        return False
    if "://" in text or "\\" in text or "/" in text or ":" in text:
        return False
    return True


def _safe_endpoint(policy: Mapping[str, Any], errors: list[dict[str, str]]) -> EndpointPolicy:
    scheme = str(policy.get("scheme", ""))
    host = str(policy.get("host", ""))
    path = str(policy.get("path", ""))
    allow_redirects = policy.get("allow_redirects")
    allow_proxy = policy.get("allow_proxy")
    if scheme != "https":
        errors.append(adapter_error("endpoint_policy_rejected", "endpoint scheme must be https", field_path="endpoint_policy.scheme"))
    if not host.endswith(".invalid") or host in {"localhost", "127.0.0.1", "::1"}:
        errors.append(adapter_error("endpoint_policy_rejected", "endpoint host must be a synthetic .invalid host", field_path="endpoint_policy.host"))
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None and (parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local):
        errors.append(adapter_error("endpoint_policy_rejected", "endpoint host must not be a private IP", field_path="endpoint_policy.host"))
    if not path.startswith("/") or "://" in path:
        errors.append(adapter_error("endpoint_policy_rejected", "endpoint path must be absolute path identity", field_path="endpoint_policy.path"))
    if allow_redirects is not False:
        errors.append(adapter_error("endpoint_policy_rejected", "redirects must be disabled", field_path="endpoint_policy.allow_redirects"))
    if allow_proxy is not False:
        errors.append(adapter_error("endpoint_policy_rejected", "proxy must be disabled", field_path="endpoint_policy.allow_proxy"))
    return EndpointPolicy(scheme=scheme, host=host, path=path, allow_redirects=bool(allow_redirects), allow_proxy=bool(allow_proxy))


def _limits(payload: Mapping[str, Any], errors: list[dict[str, str]]) -> ProviderLimits:
    timeout_ms = payload.get("timeout_ms")
    max_attempts = payload.get("max_attempts")
    max_input_tokens = payload.get("max_input_tokens")
    max_output_tokens = payload.get("max_output_tokens")
    max_total_tokens = payload.get("max_total_tokens")
    max_response_bytes = payload.get("max_response_bytes")
    max_cost_usd = _decimal(payload.get("max_cost_usd"), field_path="limits.max_cost_usd", errors=errors)
    int_limits = (
        ("limits.timeout_ms", timeout_ms, 1, MAX_TIMEOUT_MS),
        ("limits.max_attempts", max_attempts, 1, MAX_ATTEMPTS),
        ("limits.max_input_tokens", max_input_tokens, 1, MAX_INPUT_TOKENS),
        ("limits.max_output_tokens", max_output_tokens, 1, MAX_OUTPUT_TOKENS),
        ("limits.max_total_tokens", max_total_tokens, 1, MAX_TOTAL_TOKENS),
        ("limits.max_response_bytes", max_response_bytes, 1, MAX_RESPONSE_BYTES),
    )
    for field_path, value, low, high in int_limits:
        if not isinstance(value, int) or not low <= value <= high:
            errors.append(adapter_error("limit_out_of_range", "integer limit is outside allowed range", field_path=field_path))
    if max_cost_usd <= 0 or max_cost_usd > MAX_COST_USD:
        errors.append(adapter_error("limit_out_of_range", "cost limit is outside allowed range", field_path="limits.max_cost_usd"))
    return ProviderLimits(
        timeout_ms=int(timeout_ms or 0),
        max_attempts=int(max_attempts or 0),
        max_input_tokens=int(max_input_tokens or 0),
        max_output_tokens=int(max_output_tokens or 0),
        max_total_tokens=int(max_total_tokens or 0),
        max_response_bytes=int(max_response_bytes or 0),
        max_cost_usd=max_cost_usd,
    )


def load_provider_adapter_config(payload: Mapping[str, Any]) -> ProviderAdapterConfig:
    if not isinstance(payload, Mapping):
        raise_adapter("invalid_provider_config", "provider config must be an object")
    errors: list[dict[str, str]] = []
    version = str(payload.get("adapter_contract_version", ""))
    if version not in SUPPORTED_ADAPTER_CONTRACT_VERSIONS:
        errors.append(adapter_error("unsupported_adapter_contract_version", "unsupported adapter contract version", field_path="adapter_contract_version"))
    for field in ("adapter_id", "adapter_version", "provider_id", "model_id", "model_version"):
        if not is_safe_identifier(payload.get(field)):
            errors.append(adapter_error("invalid_provider_config", f"{field} must be a safe identifier", field_path=field))
    if payload.get("enabled") is not True:
        errors.append(adapter_error("adapter_disabled", "adapter must be explicitly enabled for fake transport conformance", field_path="enabled"))
    if payload.get("live_mode_enabled") is not False:
        errors.append(adapter_error("live_mode_not_allowed", "live mode is not available in R2C-A", field_path="live_mode_enabled"))
    transport_kind = str(payload.get("transport_kind", ""))
    if transport_kind not in ALLOWED_TRANSPORT_KINDS:
        errors.append(adapter_error("transport_not_allowed", "only fake transport is allowed", field_path="transport_kind"))
    endpoint_payload = payload.get("endpoint_policy")
    if not isinstance(endpoint_payload, Mapping):
        errors.append(adapter_error("endpoint_policy_rejected", "endpoint policy must be an object", field_path="endpoint_policy"))
        endpoint = EndpointPolicy("", "", "", False, False)
    else:
        endpoint = _safe_endpoint(endpoint_payload, errors)
    credential_binding_id = str(payload.get("credential_binding_id", ""))
    if not _safe_credential_binding(payload.get("credential_binding_id")):
        errors.append(adapter_error("credential_binding_invalid", "credential binding must be an opaque safe id", field_path="credential_binding_id"))
    limits_payload = payload.get("limits")
    if not isinstance(limits_payload, Mapping):
        errors.append(adapter_error("limit_out_of_range", "limits must be an object", field_path="limits"))
        limits = ProviderLimits(0, 0, 0, 0, 0, 0, Decimal("0"))
    else:
        limits = _limits(limits_payload, errors)
    if errors:
        raise ProviderAdapterContractError(errors)
    return ProviderAdapterConfig(
        adapter_contract_version=version,
        adapter_id=str(payload["adapter_id"]),
        adapter_version=str(payload["adapter_version"]),
        provider_id=str(payload["provider_id"]),
        model_id=str(payload["model_id"]),
        model_version=str(payload["model_version"]),
        enabled=True,
        live_mode_enabled=False,
        transport_kind=transport_kind,
        endpoint_policy=endpoint,
        credential_binding_id=credential_binding_id,
        limits=limits,
    )
