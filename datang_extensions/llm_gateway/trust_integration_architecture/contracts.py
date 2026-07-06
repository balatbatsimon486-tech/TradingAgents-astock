"""Shared contracts for R2C-F offline trust integration architecture."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.llm_gateway.errors import gateway_error
from datang_extensions.llm_gateway.provider_authorization.contracts import external_calls_false, is_explicit_safe_id
from datang_extensions.llm_gateway.trust_boundary.contracts import scan_forbidden_surface as trust_boundary_forbidden

ARCHITECTURE_STAGE = "tradingagents_r2c_f_offline_trust_integration_architecture"
ARCHITECTURE_CONTRACT_VERSION = "1.0"
STABLE_BASELINE = "70763a31c5fe01135bda9b02be91103eefc341ce"
DECISION_READY = "ready_for_architecture_review"
DECISION_BLOCKED = "blocked"
SUPPORTED_VERSION = frozenset({"1.0"})
SERVICE_CLASSES = ("identity_provider", "detached_signature_verifier", "nonce_issuer", "authorization_issuer")
REQUIRED_NODES = frozenset({"research-orchestration-boundary", "trust-control-plane", "identity-service-boundary", "signature-verification-boundary", "nonce-service-boundary", "authorization-issuer-boundary", "immutable-audit-sink-boundary", "kill-switch-control-boundary", "provider-sandbox-boundary"})
REQUIRED_DATA_CLASSES = frozenset({"public_metadata", "internal_configuration", "restricted_identity_metadata", "restricted_authorization_metadata", "secret_material", "signature_material", "nonce_material", "research_artifact", "audit_metadata"})
DISALLOWED_FLOW_CLASSES = frozenset({"secret_material", "signature_material", "nonce_material"})
REAL_VENDOR_MARKERS: tuple[str, ...] = ()
REAL_LOCATION_KEYS = frozenset({"endpoint", "host", "hostname", "ip", "cidr", "domain", "url", "port", "region", "account", "tenant", "tenant_id"})
FALSE_FIELDS = ("real_vendor_selected", "procurement_approved", "deployment_approved", "change_request_approved", "rollback_test_executed", "network_configuration_applied", "identity_service_configured", "signature_service_configured", "nonce_service_configured", "authorization_issuer_configured", "real_integration_started", "secret_resolution_authorized", "network_execution_authorized", "live_execution_authorized", "credential_value_resolved", "provider_transport_called")
REQUIRED_REAL_WORLD_ACTIONS = [
    "perform_independent_real_vendor_due_diligence",
    "verify_real_product_security_claims",
    "verify_real_commercial_terms_and_service_levels",
    "complete_legal_procurement_and_data_protection_review",
    "confirm_data_residency_and_cross_border_requirements",
    "approve_real_identity_protocol_and_issuer_policy",
    "approve_real_signature_algorithm_and_trusted_root",
    "verify_real_nonce_storage_and_atomic_consume",
    "verify_real_authorization_issuer_atomic_issue",
    "verify_real_audit_sink",
    "approve_real_network_topology_and_egress",
    "approve_real_secret_ownership",
    "complete_threat_model_review",
    "complete_capacity_and_availability_review",
    "complete_exit_and_portability_review",
    "approve_change_window",
    "approve_rollback_plan",
    "execute_tabletop_drill",
    "execute_isolated_environment_dry_run",
    "separately_approve_real_deployment_and_integration",
]

class ArchitectureError(ValueError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def architecture_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
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


def decimal_string(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def external_calls_all_false() -> dict[str, bool]:
    calls = external_calls_false()
    calls.update({"vendor_api_called": False, "identity_provider_called": False, "signature_service_called": False, "nonce_service_called": False, "authorization_issuer_called": False})
    return calls


def require_object(value: Any, field_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if isinstance(value, Mapping):
        return dict(value), []
    return {}, [architecture_error("trust_integration_architecture_error", "payload must be an object", field_path=field_path)]


def require_json_object(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArchitectureError([architecture_error("trust_integration_architecture_error", "payload must be a JSON object", field_path=field_path)])
    return dict(value)


def _tokens(value: Any) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if token}


def has_real_vendor_marker(value: Any) -> bool:
    tokens = _tokens(value)
    return any(marker in tokens for marker in REAL_VENDOR_MARKERS)


def has_real_vendor_placeholder(value: Any) -> bool:
    tokens = _tokens(value)
    return "real" in tokens and "vendor" in tokens


def scan_architecture_surface(value: Any, *, code: str, field_path: str = "payload") -> dict[str, str] | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).strip().lower()
            if lowered in REAL_LOCATION_KEYS:
                return architecture_error("real_endpoint_not_allowed", "real network location field is not allowed", field_path="redacted_network_location")
            if has_real_vendor_marker(key):
                return architecture_error("real_vendor_identifier_not_allowed", "real vendor marker is not allowed", field_path="redacted_vendor_identifier")
            if isinstance(nested, str) and has_real_vendor_marker(nested):
                return architecture_error("real_vendor_identifier_not_allowed", "real vendor marker is not allowed", field_path="redacted_vendor_identifier")
            forbidden = trust_boundary_forbidden({key: None}, code=code, field_path=field_path)
            if forbidden:
                return forbidden
            found = scan_architecture_surface(nested, code=code, field_path=field_path)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = scan_architecture_surface(item, code=code, field_path=field_path)
            if found:
                return found
    elif isinstance(value, str) and has_real_vendor_marker(value):
        return architecture_error("real_vendor_identifier_not_allowed", "real vendor marker is not allowed", field_path="redacted_vendor_identifier")
    return None


def require_safe_id(value: Any, errors: list[dict[str, str]], code: str, field_path: str) -> None:
    if not is_explicit_safe_id(value) or has_real_vendor_marker(value) or has_real_vendor_placeholder(value):
        errors.append(architecture_error(code, "field must be a synthetic safe id", field_path=field_path))


def sorted_records(items: list[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(items, key=lambda item: str(item.get(key, "")))]


def base_result(errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failed = list(errors or [])
    passed = not failed
    return {
        "stage": ARCHITECTURE_STAGE,
        "architecture_contract_version": ARCHITECTURE_CONTRACT_VERSION,
        "passed": passed,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "architecture_package_sealed": passed,
        "ready_for_architecture_review": passed,
        "candidate_assessment_ready": passed,
        "candidate_recommendation_ready": passed,
        "deployment_topology_contract_ready": passed,
        "trust_zone_model_ready": passed,
        "ownership_matrix_ready": passed,
        "change_control_plan_ready": passed,
        "rollback_plan_ready": passed,
        "operational_drill_plan_ready": passed,
        "real_vendor_selected": False,
        "procurement_approved": False,
        "deployment_approved": False,
        "change_request_approved": False,
        "rollback_test_executed": False,
        "network_configuration_applied": False,
        "identity_service_configured": False,
        "signature_service_configured": False,
        "nonce_service_configured": False,
        "authorization_issuer_configured": False,
        "real_integration_started": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "candidate_assessments": [],
        "recommendations": [],
        "required_real_world_actions": list(REQUIRED_REAL_WORLD_ACTIONS),
        "external_calls": external_calls_all_false(),
        "candidate_catalog_hash": "",
        "evaluation_policy_hash": "",
        "assessment_result_hash": "",
        "recommendation_set_hash": "",
        "deployment_topology_hash": "",
        "trust_zone_model_hash": "",
        "data_flow_set_hash": "",
        "ownership_matrix_hash": "",
        "change_control_hash": "",
        "rollback_plan_hash": "",
        "drill_plan_hash": "",
        "evidence_bundle_hash": "",
        "blocking_findings_hash": "",
        "required_real_world_actions_hash": "",
        "architecture_package_hash": "",
        "audit_hash": "",
        "blocking_findings": failed,
        "warnings": [],
        "errors": failed,
        "audit": {},
    }
