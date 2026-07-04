"""Shared contracts for the R2C-B offline authorization gate."""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from datang_extensions.llm_gateway.contracts import (
    CREDENTIAL_FIELDS,
    EXTERNAL_CALLS,
    FORBIDDEN_TRADING_FIELDS,
    SHA256_RE,
    find_forbidden_key,
    is_safe_identifier,
    stable_json_hash,
)
from datang_extensions.llm_gateway.errors import gateway_error

AUTHORIZATION_STAGE = "tradingagents_r2c_b_offline_authorization"
AUTHORIZATION_CONTRACT_VERSION = "1.0"
BINDING_REGISTRY_VERSION = "1.0"
AUTHORIZATION_POLICY_VERSION = "1.0"
APPROVAL_SET_VERSION = "1.0"
GRANT_MODE = "offline_preflight"
ALLOWED_ENVIRONMENT = "sandbox"
ALLOWED_BINDING_STATES = frozenset({"registered", "active", "suspended", "revoked", "expired"})
TERMINAL_BINDING_STATES = frozenset({"revoked", "expired"})
REQUIRED_FALSE_CAPABILITIES = ("network_execution", "streaming", "tools", "trading_actions")
SECRET_MATERIAL_FIELDS = frozenset(
    set(CREDENTIAL_FIELDS)
    | {
        "api_key",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credential_value",
        "material",
        "password",
        "private_key",
        "secret",
        "secret_value",
        "set-cookie",
        "token",
        "x-api-key",
    }
)
AUTHORIZATION_FORBIDDEN_FIELDS = frozenset(
    set(FORBIDDEN_TRADING_FIELDS)
    | {
        "auto_trade",
        "broker",
        "buy",
        "expected_return",
        "hold",
        "max_drawdown",
        "order",
        "order_size",
        "pnl",
        "position_size",
        "profit",
        "recommendation",
        "sell",
        "sharpe",
        "target_weight",
        "trade",
        "win_rate",
    }
)
TRANSPORT_SURFACE_FIELDS = frozenset(
    {
        "endpoint",
        "headers",
        "http_headers",
        "proxy",
        "request_options",
        "response_format",
        "stream",
        "tool_choice",
        "tools",
        "transport",
        "url",
    }
)
SAFE_EXTERNAL_CALLS = copy.deepcopy(EXTERNAL_CALLS)
SAFE_EXTERNAL_CALLS.update(
    {
        "provider_transport_called": False,
        "credential_value_resolved": False,
        "live_execution_called": False,
        "environment_read": False,
    }
)


class AuthorizationContractError(ValueError):
    """Raised when an R2C-B offline authorization contract fails closed."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def auth_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def hash_value(value: Any) -> str:
    return stable_json_hash(value)


def external_calls_false() -> dict[str, bool]:
    return copy.deepcopy(SAFE_EXTERNAL_CALLS)


def is_explicit_safe_id(value: Any) -> bool:
    if not is_safe_identifier(value):
        return False
    text = str(value)
    lowered = text.lower()
    return "*" not in text and "/" not in text and "\\" not in text and not lowered.startswith("sk-") and "bearer" not in lowered


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def decimal_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def safe_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    strings: list[str] = []
    for item in value:
        if not is_explicit_safe_id(item):
            return None
        strings.append(str(item))
    if "*" in strings:
        return None
    return strings


def scan_secret_or_trading_fields(value: Any) -> dict[str, str] | None:
    if find_forbidden_key(value, SECRET_MATERIAL_FIELDS, "payload"):
        return auth_error("secret_material_field_detected", "secret material is not allowed", field_path="redacted_secret_material")
    if find_forbidden_key(value, AUTHORIZATION_FORBIDDEN_FIELDS, "payload"):
        return auth_error("authorization_capability_not_allowed", "trading or performance fields are not allowed", field_path="redacted_forbidden_field")
    return None


def reject_transport_surface(value: Mapping[str, Any]) -> dict[str, str] | None:
    for key in value:
        normalized = str(key).strip().lower()
        if normalized in TRANSPORT_SURFACE_FIELDS:
            return auth_error("authorization_request_invalid", "caller-supplied transport surface is not allowed", field_path=normalized)
    return None
