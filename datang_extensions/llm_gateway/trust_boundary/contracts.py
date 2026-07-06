"""Offline trust-boundary contracts for R2C-E."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_authorization.contracts import external_calls_false, is_explicit_safe_id

TRUST_BOUNDARY_STAGE = "tradingagents_r2c_e_offline_trust_boundary"
TRUST_BOUNDARY_CONTRACT_VERSION = "1.0"
STABLE_BASELINE = "45492693d586df1f1cb4ca715a608bbad0c754d1"
DECISION_READY = "ready_for_trust_service_integration_review"
DECISION_BLOCKED = "blocked"
SUPPORTED_VERSION = frozenset({"1.0"})

FALSE_EXECUTION_FIELDS = (
    "secret_resolution_authorized",
    "network_execution_authorized",
    "live_execution_authorized",
    "credential_value_resolved",
    "provider_transport_called",
)
REQUIRED_INTEGRATION_ACTIONS = [
    "select_and_approve_enterprise_identity_provider",
    "approve_protocol_and_issuer_allowlist",
    "configure_mfa_and_fresh_auth_policy",
    "define_opaque_subject_role_mapping",
    "select_detached_signature_format",
    "approve_algorithm_chain_and_trusted_roots_policy",
    "configure_revocation_checks",
    "deploy_nonce_issuer",
    "deploy_atomic_nonce_registry",
    "verify_nonce_entropy_and_ttl",
    "deploy_authorization_issuer",
    "define_atomic_issuance_and_duplicate_rejection",
    "define_real_audit_sink",
    "drill_identity_provider_outage",
    "drill_signature_verification_failure",
    "drill_nonce_replay",
    "drill_duplicate_authorization_issuance",
    "reconfirm_stable_baseline_and_freeze",
    "complete_real_security_review",
    "separately_approve_real_integration",
]
MATERIAL_FIELD_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "assertion",
        "assertion_body",
        "bearer",
        "certificate",
        "client_id",
        "cookie",
        "credential",
        "credential_value",
        "email",
        "employee_id",
        "endpoint",
        "id_token",
        "issuer_url",
        "nonce_value",
        "private_key",
        "public_key",
        "real_name",
        "secret",
        "secret_value",
        "signature_value",
        "subject",
        "tenant_id",
        "token",
        "url",
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


class TrustBoundaryError(ValueError):
    """Raised by the R2C-E CLI for schema-loading failures."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def trust_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def hash_value(value: Any) -> str:
    return stable_json_hash(value)


def safe_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def external_calls_all_false() -> dict[str, bool]:
    calls = external_calls_false()
    calls.update(
        {
            "identity_provider_called": False,
            "signature_service_called": False,
            "nonce_service_called": False,
            "authorization_issuer_called": False,
        }
    )
    return calls


def scan_forbidden_surface(value: Any, *, code: str, field_path: str = "payload") -> dict[str, str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).strip().lower()
            if lowered in MATERIAL_FIELD_KEYS:
                return trust_error(code, "material-bearing field is not allowed", field_path="redacted_material_field")
            if lowered in TRADING_FIELD_KEYS:
                return trust_error(code, "trading or performance field is not allowed", field_path="redacted_forbidden_field")
            found = scan_forbidden_surface(nested, code=code, field_path=field_path)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = scan_forbidden_surface(item, code=code, field_path=field_path)
            if found:
                return found
    return None


def require_safe_id(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_explicit_safe_id(value):
        errors.append(trust_error(code, "field must be a safe explicit id", field_path=field_path))


def require_true(payload: Mapping[str, Any], fields: Sequence[str], errors: list[dict[str, str]], code: str) -> None:
    for field in fields:
        if payload.get(field) is not True:
            errors.append(trust_error(code, f"{field} must be true", field_path=field))


def require_false(payload: Mapping[str, Any], fields: Sequence[str], errors: list[dict[str, str]], code: str) -> None:
    for field in fields:
        if payload.get(field) is not False:
            errors.append(trust_error(code, f"{field} must be false", field_path=field))


def base_result(errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failed = list(errors or [])
    passed = not failed
    return {
        "stage": TRUST_BOUNDARY_STAGE,
        "trust_boundary_contract_version": TRUST_BOUNDARY_CONTRACT_VERSION,
        "passed": passed,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "ready_for_trust_service_integration_review": passed,
        "identity_provider_contract_ready": passed,
        "signature_verifier_contract_ready": passed,
        "nonce_issuer_contract_ready": passed,
        "authorization_issuer_contract_ready": passed,
        "identity_service_configured": False,
        "identity_assertion_present": False,
        "identity_verification_performed": False,
        "reviewer_identity_verified": False,
        "signature_service_configured": False,
        "signature_value_present": False,
        "signature_verification_performed": False,
        "detached_signature_verified": False,
        "nonce_service_configured": False,
        "execution_nonce_issued": False,
        "execution_nonce_present": False,
        "nonce_commitment_present": False,
        "authorization_issuer_configured": False,
        "live_authorization_issued": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "trust_provider_manifest_hash": "",
        "identity_contract_hash": "",
        "signature_contract_hash": "",
        "nonce_contract_hash": "",
        "issuer_contract_hash": "",
        "evidence_bundle_hash": "",
        "blocking_findings_hash": "",
        "required_integration_actions_hash": "",
        "trust_boundary_package_hash": "",
        "audit_hash": "",
        "blocking_findings": failed,
        "required_integration_actions": list(REQUIRED_INTEGRATION_ACTIONS),
        "external_calls": external_calls_all_false(),
        "warnings": [],
        "errors": failed,
        "audit": {},
    }


def require_json_object(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustBoundaryError([trust_error("trust_boundary_error", "payload must be a JSON object", field_path=field_path)])
    return dict(value)
