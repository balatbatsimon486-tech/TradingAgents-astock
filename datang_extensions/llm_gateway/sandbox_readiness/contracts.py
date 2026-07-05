"""Shared contracts for the R2C-C offline sandbox readiness gate."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_authorization.contracts import external_calls_false, is_explicit_safe_id

READINESS_STAGE = "tradingagents_r2c_c_offline_sandbox_readiness"
READINESS_CONTRACT_VERSION = "1.0"
STABLE_BASELINE = "65a396120a5734b7e06855000c84e7a2e581b617"
SUPPORTED_VERSION = frozenset({"1.0"})
DECISION_READY = "ready_for_human_review"
DECISION_BLOCKED = "blocked"
SAFE_REVIEW_STATUSES = frozenset({"covered_by_offline_control", "requires_human_review", "blocked"})
SEVERITIES_REQUIRING_CONTROLS = frozenset({"high", "critical"})
REQUIRED_MILESTONES = {
    "R2A": "bd7279e127c815c43ac760c2aa86a5ccf50fb1f5",
    "R2B": "16da82868393b499b1c07ccce2fc0e13e4ac00d0",
    "R2C-A": "084ab293b5c190d4219ab72ac01eea3aa9fa90d5",
    "R2C-B": STABLE_BASELINE,
}
REQUIRED_EVIDENCE_IDS = frozenset(
    {
        "r2a-evidence",
        "r2b-evidence",
        "r2c-a-evidence",
        "r2c-b-evidence",
        "boundary-audit-evidence",
        "main-ci-evidence",
        "no-network-evidence",
        "no-secret-evidence",
        "redaction-evidence",
        "replay-protection-evidence",
        "readiness-package-evidence",
        "incident-response-evidence",
    }
)
REQUIRED_THREAT_IDS = frozenset(
    {
        "secret_to_git",
        "secret_to_logs",
        "secret_to_exception",
        "environment_variable_read",
        "prompt_injection_policy_bypass",
        "caller_endpoint_injection",
        "redirect_bypass",
        "dns_rebinding",
        "proxy_bypass",
        "private_network_ssrf",
        "provider_identity_drift",
        "response_schema_drift",
        "model_version_drift",
        "retry_cost_loss",
        "grant_replay",
        "grant_cross_request_use",
        "approval_expired_or_forged",
        "requester_self_approval",
        "audit_loss_or_mutation",
        "redaction_failure",
        "trading_field_output",
        "production_data_in_sandbox",
        "sandbox_credential_misuse",
        "kill_switch_ineffective",
        "incident_response_unclear",
    }
)
REQUIRED_STOP_CONDITIONS = frozenset(
    {
        "secret_value_in_log",
        "binding_identity_mismatch",
        "approval_or_grant_expired",
        "provider_identity_drift",
        "endpoint_not_allowlisted",
        "redirect_proxy_or_private_network_requested",
        "budget_exceeded",
        "response_size_exceeded",
        "token_limit_exceeded",
        "tools_or_streaming_requested",
        "trading_field_detected",
        "provider_response_unparseable",
        "auth_401_or_403",
        "rate_limit_or_5xx_repeated",
        "redaction_failed",
        "audit_write_failed",
        "kill_switch_state_unclear",
    }
)
MATERIAL_FIELD_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bearer",
        "cookie",
        "credential",
        "credential_value",
        "private_key",
        "secret",
        "secret_name",
        "secret_value",
        "set-cookie",
        "token",
        "x-api-key",
    }
)
TRADING_FIELD_KEYS = frozenset(
    {
        "auto_trade",
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
        "target_price",
        "target_weight",
        "win_rate",
    }
)


class ReadinessContractError(ValueError):
    """Raised for schema or file loading errors in the R2C-C CLI."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def readiness_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def hash_value(value: Any) -> str:
    return stable_json_hash(value)


def safe_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def as_mapping(value: Any, code: str, field_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if isinstance(value, Mapping):
        return dict(value), []
    return {}, [readiness_error(code, "payload must be an object", field_path=field_path)]


def safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    strings = [str(item) for item in value]
    if any(not item or "*" in item or "/" in item or "\\" in item for item in strings):
        return None
    return strings


def decimal_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def parse_utc(value: Any) -> datetime:
    text = str(value)
    if not text.endswith("Z"):
        raise ValueError("timestamp must be UTC Z")
    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ValueError("timestamp must be UTC")
    return parsed


def scan_forbidden_surface(value: Any, *, prefix: str = "payload") -> dict[str, str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).strip().lower()
            if lowered in MATERIAL_FIELD_KEYS:
                return readiness_error("secret_material_field_detected", "secret material is not allowed", field_path="redacted_secret_material")
            if lowered in TRADING_FIELD_KEYS:
                return readiness_error("readiness_trading_field_detected", "trading or performance fields are not allowed", field_path="redacted_forbidden_field")
            found = scan_forbidden_surface(nested, prefix=prefix)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = scan_forbidden_surface(item, prefix=prefix)
            if found:
                return found
    return None


def require_safe_id(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_explicit_safe_id(value):
        errors.append(readiness_error(code, "field must be a safe explicit id", field_path=field_path))


def require_false(payload: Mapping[str, Any], fields: Sequence[str], code: str, errors: list[dict[str, str]]) -> None:
    for field in fields:
        if payload.get(field) is not False:
            errors.append(readiness_error(code, f"{field} must be false", field_path=field))


def base_result(errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failed = list(errors or [])
    passed = not failed
    return {
        "stage": READINESS_STAGE,
        "readiness_contract_version": READINESS_CONTRACT_VERSION,
        "passed": passed,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "ready_for_human_review": passed,
        "human_review_completed": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "external_calls": external_calls_false(),
        "profile_hash": "",
        "secret_proposal_hash": "",
        "egress_policy_hash": "",
        "manifest_hash": "",
        "threat_model_hash": "",
        "evidence_hash": "",
        "incident_plan_hash": "",
        "readiness_package_hash": "",
        "audit_hash": "",
        "manual_review_requirements": [],
        "blocking_findings": failed,
        "audit": {},
        "warnings": [],
        "errors": failed,
    }


def sorted_records(items: list[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: str(item.get(key, "")))]
