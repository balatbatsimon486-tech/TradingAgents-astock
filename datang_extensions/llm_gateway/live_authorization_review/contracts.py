"""Offline human review sealing contracts for R2C-D."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_authorization.clock import parse_utc_datetime
from datang_extensions.llm_gateway.provider_authorization.contracts import external_calls_false, is_explicit_safe_id

REVIEW_STAGE = "tradingagents_r2c_d_offline_live_authorization_review"
REVIEW_CONTRACT_VERSION = "1.0"
STABLE_BASELINE = "ef9a37abaf6586bf31f436d9a07ca8edb601c77d"
DECISION_READY = "ready_for_human_signoff"
DECISION_BLOCKED = "blocked"
SUPPORTED_VERSION = frozenset({"1.0"})
REQUIRED_REAL_WORLD_ACTIONS = [
    "verify_real_reviewer_identity",
    "verify_detached_signatures",
    "approve_secret_backend",
    "review_resolver_design",
    "approve_real_endpoint_and_egress",
    "approve_budget_and_execution_window",
    "generate_execution_nonce_out_of_band",
    "complete_kill_switch_drill",
    "confirm_incident_owner",
    "issue_single_call_authorization_manually",
]
REQUIRED_FREEZE_KINDS = frozenset(
    {
        "sandbox_profile",
        "secret_storage_proposal",
        "egress_policy",
        "run_manifest",
        "threat_model",
        "prerequisite_evidence",
        "incident_response",
        "review_manifest",
        "reviewer_records",
    }
)
IDENTITY_MATERIAL_FIELDS = frozenset({"real_name", "email", "employee_id", "certificate", "public_key"})
SECRET_OR_SIGNATURE_FIELDS = frozenset(
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
        "secret_value",
        "set-cookie",
        "signature_value",
        "token",
        "x-api-key",
    }
)
TRADING_FIELDS = frozenset(
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
        "sell",
        "sharpe",
        "target_price",
        "target_weight",
        "win_rate",
    }
)
FALSE_EXECUTION_FIELDS = (
    "secret_resolution_authorized",
    "network_execution_authorized",
    "live_execution_authorized",
    "credential_value_resolved",
    "provider_transport_called",
)
MAX_INPUT_TOKENS = 1024
MAX_OUTPUT_TOKENS = 512
MAX_TOTAL_TOKENS = 1536
MAX_COST_USD = Decimal("0.10")
MAX_WINDOW_SECONDS = 900


class LiveAuthorizationReviewError(ValueError):
    """Raised by the R2C-D CLI for schema-loading failures."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def review_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def hash_value(value: Any) -> str:
    return stable_json_hash(value)


def safe_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def decimal_value(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_utc(value: Any) -> datetime:
    return parse_utc_datetime(str(value))


def sorted_records(items: list[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: str(item.get(key, "")))]


def scan_forbidden_surface(value: Any, *, prefix: str = "payload") -> dict[str, str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).strip().lower()
            if lowered in IDENTITY_MATERIAL_FIELDS:
                return review_error("review_identity_material_detected", "real identity material is not allowed", field_path="redacted_identity_material")
            if lowered in SECRET_OR_SIGNATURE_FIELDS:
                return review_error("review_secret_material_detected", "secret or signature material is not allowed", field_path="redacted_secret_material")
            if lowered in TRADING_FIELDS:
                return review_error("review_trading_field_detected", "trading or performance field is not allowed", field_path="redacted_forbidden_field")
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
        errors.append(review_error(code, "field must be a safe explicit id", field_path=field_path))


def require_sha256(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_sha256(value):
        errors.append(review_error(code, "field must be a lowercase SHA-256", field_path=field_path))


def require_false(payload: Mapping[str, Any], fields: tuple[str, ...], errors: list[dict[str, str]], code: str = "live_execution_not_authorized") -> None:
    for field in fields:
        if payload.get(field) is not False:
            errors.append(review_error(code, f"{field} must remain false", field_path=field))


def base_result(errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failed = list(errors or [])
    passed = not failed
    return {
        "stage": REVIEW_STAGE,
        "review_contract_version": REVIEW_CONTRACT_VERSION,
        "passed": passed,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "review_package_sealed": passed,
        "ready_for_human_signoff": passed,
        "human_review_completed": False,
        "reviewer_identity_verified": False,
        "detached_signature_verified": False,
        "live_authorization_contract_ready": passed,
        "live_authorization_issued": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "external_calls": external_calls_false(),
        "authorization_id": "",
        "review_manifest_hash": "",
        "review_record_set_hash": "",
        "change_freeze_hash": "",
        "authorization_draft_hash": "",
        "review_package_hash": "",
        "audit_hash": "",
        "required_real_world_actions": list(REQUIRED_REAL_WORLD_ACTIONS),
        "audit": {},
        "warnings": [],
        "errors": failed,
    }
