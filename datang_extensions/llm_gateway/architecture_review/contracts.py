"""Shared contracts for R2C-G offline architecture review evidence sealing."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_authorization.clock import parse_utc_datetime
from datang_extensions.llm_gateway.provider_authorization.contracts import external_calls_false, is_explicit_safe_id

ARCHITECTURE_REVIEW_STAGE = "tradingagents_r2c_g_offline_architecture_review"
ARCHITECTURE_REVIEW_CONTRACT_VERSION = "1.0"
STABLE_BASELINE = "1330d21562e43346502bbee5816236b4e806168d"
ARCHITECTURE_PACKAGE_HASH = "7f5c95724b82724138a9b7a173bd5a5dbc7a6260f02cf962806bbed89e4e0682"
DECISION_READY = "ready_for_architecture_signoff"
DECISION_BLOCKED = "blocked"
SUPPORTED_VERSION = frozenset({"1.0"})
REQUIRED_REVIEWER_ROLES = (
    "security_architecture_reviewer",
    "platform_architecture_reviewer",
    "operations_reviewer",
    "data_governance_reviewer",
    "incident_response_reviewer",
)
REQUIRED_REVIEW_SCOPE = frozenset({
    "candidate_assessment",
    "topology",
    "trust_zones",
    "data_flows",
    "ownership",
    "change_control",
    "rollback",
    "operational_drills",
})
COMPONENT_HASH_FIELDS = (
    "candidate_catalog_hash",
    "evaluation_policy_hash",
    "assessment_result_hash",
    "recommendation_set_hash",
    "deployment_topology_hash",
    "trust_zone_model_hash",
    "data_flow_set_hash",
    "ownership_matrix_hash",
    "change_control_hash",
    "rollback_plan_hash",
    "drill_plan_hash",
    "evidence_bundle_hash",
    "required_real_world_actions_hash",
)
FALSE_REVIEW_FIELDS = (
    "architecture_review_completed",
    "reviewer_identity_verified",
    "review_signatures_verified",
    "architecture_decision_approved",
    "risk_acceptance_approved",
    "waiver_approved",
    "vendor_selection_approved",
    "procurement_approved",
    "deployment_authorized",
    "network_change_authorized",
    "real_integration_started",
    "secret_resolution_authorized",
    "network_execution_authorized",
    "live_execution_authorized",
    "credential_value_resolved",
    "provider_transport_called",
)
EXTERNAL_CALL_KEYS = (
    "network_called",
    "identity_provider_called",
    "signature_service_called",
    "vendor_api_called",
    "procurement_system_called",
    "deployment_system_called",
    "market_data_called",
    "tushare_called",
    "qlib_called",
    "broker_called",
)
REQUIRED_REAL_WORLD_ACTIONS = [
    "assign_real_reviewers",
    "verify_all_reviewer_identities",
    "verify_reviewer_roles_and_authority",
    "complete_real_architecture_review_meeting",
    "verify_all_detached_signatures",
    "review_all_findings",
    "close_or_approve_handling_for_critical_high_findings",
    "review_medium_finding_remediation",
    "resolve_unresolved_dissent",
    "approve_or_reject_risk_acceptance_requests",
    "approve_or_reject_waiver_requests",
    "reconfirm_stable_baseline",
    "reconfirm_architecture_package_unchanged",
    "reconfirm_candidates_and_scoring_unchanged",
    "reconfirm_topology_and_data_flows_unchanged",
    "reconfirm_ownership_and_separation_unchanged",
    "reconfirm_change_rollback_and_drill_plans_unchanged",
    "complete_independent_real_vendor_due_diligence",
    "complete_legal_procurement_data_protection_and_security_approvals",
    "separately_approve_any_real_deployment_or_network_change",
]
REQUIRED_SUPERSEDE_TRIGGERS = frozenset({
    "stable_baseline_change",
    "architecture_package_hash_change",
    "candidate_catalog_change",
    "evaluation_policy_change",
    "recommended_candidate_change",
    "topology_node_or_edge_change",
    "trust_zone_change",
    "data_flow_change",
    "ownership_matrix_change",
    "separation_of_duties_change",
    "change_control_plan_change",
    "rollback_plan_change",
    "drill_plan_change",
    "required_real_world_actions_change",
    "new_critical_or_high_finding",
    "finding_severity_increase",
    "risk_acceptance_or_waiver_request_change",
    "review_charter_or_required_roles_change",
    "review_evidence_expiry",
    "real_vendor_or_endpoint_detected",
})
NON_WAIVABLE_CONTROLS = frozenset({
    "requester_reviewer_separation",
    "identity_verification",
    "signature_verification",
    "nonce_replay_protection",
    "duplicate_issuance_rejection",
    "kill_switch",
    "audit_sink",
    "no_secret_boundary",
    "no_network_boundary",
})
IDENTITY_FIELDS = frozenset({"real_name", "email", "employee_id", "account", "certificate", "public_key"})
SECRET_OR_SIGNATURE_FIELDS = frozenset({"signature_value", "private_key", "secret", "secret_value", "credential_value", "access_token", "api_key", "authorization", "cookie", "token"})
LOCATION_FIELDS = frozenset({"endpoint", "cidr", "ip", "host", "hostname", "domain", "url", "port"})
TRADING_FIELDS = frozenset({"target_price", "target_weight", "position_size", "order_size", "buy", "sell", "hold", "pnl", "profit", "sharpe", "max_drawdown", "win_rate"})

class ArchitectureReviewError(ValueError):
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


def parse_utc(value: Any):
    return parse_utc_datetime(str(value))


def require_safe_id(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_explicit_safe_id(value):
        errors.append(review_error(code, "field must be a synthetic safe id", field_path=field_path))


def require_sha256(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_sha256(value):
        errors.append(review_error(code, "field must be a lowercase SHA-256", field_path=field_path))


def sorted_records(items: list[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: str(item.get(key, "")))]


def external_calls_all_false() -> dict[str, bool]:
    calls = {key: False for key in EXTERNAL_CALL_KEYS}
    inherited = external_calls_false()
    for key in inherited:
        calls.setdefault(key, False)
    return calls


def scan_forbidden_surface(value: Any, *, field_path: str = "payload") -> dict[str, str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).strip().lower()
            if lowered in IDENTITY_FIELDS:
                return review_error("architecture_review_error", "real identity material is not allowed", field_path="redacted_identity_material")
            if lowered in SECRET_OR_SIGNATURE_FIELDS:
                return review_error("architecture_review_error", "signature or secret material is not allowed", field_path="redacted_secret_material")
            if lowered in LOCATION_FIELDS:
                return review_error("architecture_review_error", "real location material is not allowed", field_path="redacted_location_material")
            if lowered in TRADING_FIELDS:
                return review_error("architecture_review_error", "trading material is not allowed", field_path="redacted_trading_material")
            if isinstance(nested, str) and ("@" in nested or "http://" in nested.lower() or "https://" in nested.lower()):
                return review_error("architecture_review_error", "real-world locator text is not allowed", field_path="redacted_locator_text")
            found = scan_forbidden_surface(nested, field_path=field_path)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = scan_forbidden_surface(item, field_path=field_path)
            if found:
                return found
    return None


def require_object(value: Any, field_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if isinstance(value, Mapping):
        return dict(value), []
    return {}, [review_error("architecture_review_error", "payload must be an object", field_path=field_path)]


def require_json_object(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArchitectureReviewError([review_error("architecture_review_error", "payload must be a JSON object", field_path=field_path)])
    return dict(value)


def expiry_too_long(expiry: Any, fixed_now: str, *, max_days: int) -> bool:
    try:
        return parse_utc(expiry) - parse_utc(fixed_now) > timedelta(days=max_days)
    except ValueError:
        return True


def base_result(errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failed = list(errors or [])
    passed = not failed
    return {
        "stage": ARCHITECTURE_REVIEW_STAGE,
        "architecture_review_contract_version": ARCHITECTURE_REVIEW_CONTRACT_VERSION,
        "passed": passed,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "architecture_review_evidence_sealed": passed,
        "review_role_coverage_complete": passed,
        "review_findings_catalog_ready": passed,
        "remediation_plan_ready": passed,
        "architecture_decision_record_ready": passed,
        "supersede_policy_ready": passed,
        "ready_for_architecture_signoff": passed,
        "architecture_review_completed": False,
        "reviewer_identity_verified": False,
        "review_signatures_verified": False,
        "architecture_decision_approved": False,
        "risk_acceptance_approved": False,
        "waiver_approved": False,
        "vendor_selection_approved": False,
        "procurement_approved": False,
        "deployment_authorized": False,
        "network_change_authorized": False,
        "real_integration_started": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "review_charter_hash": "",
        "review_record_set_hash": "",
        "findings_set_hash": "",
        "dissent_set_hash": "",
        "remediation_plan_hash": "",
        "risk_acceptance_request_set_hash": "",
        "waiver_request_set_hash": "",
        "decision_record_draft_hash": "",
        "supersede_policy_hash": "",
        "evidence_bundle_hash": "",
        "blocking_findings_hash": "",
        "required_real_world_actions_hash": "",
        "architecture_review_package_hash": "",
        "audit_hash": "",
        "blocking_findings": failed,
        "required_real_world_actions": list(REQUIRED_REAL_WORLD_ACTIONS),
        "external_calls": external_calls_all_false(),
        "warnings": [],
        "errors": failed,
        "audit": {},
    }
