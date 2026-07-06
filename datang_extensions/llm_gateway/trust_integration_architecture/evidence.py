"""Offline prerequisite evidence validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import STABLE_BASELINE, architecture_error, external_calls_all_false, hash_value, is_sha256, scan_architecture_surface

EXPECTED_R2C_E_STAGE = "tradingagents_r2c_e_offline_trust_boundary"
EXPECTED_R2C_E_DECISION = "ready_for_trust_service_integration_review"


def _false(value: Mapping[str, Any], field: str, errors: list[dict[str, str]]) -> None:
    if value.get(field) is not False:
        errors.append(architecture_error("architecture_evidence_invalid", "field must remain false", field_path=field))


def _true(value: Mapping[str, Any], field: str, errors: list[dict[str, str]]) -> None:
    if value.get(field) is not True:
        errors.append(architecture_error("architecture_evidence_invalid", "field must be true", field_path=field))


def _validate_trust_boundary(trust_boundary: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    if trust_boundary.get("stage") != EXPECTED_R2C_E_STAGE:
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-E stage mismatch", field_path="trust_boundary.stage"))
    if trust_boundary.get("passed") is not True or trust_boundary.get("decision") != EXPECTED_R2C_E_DECISION:
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-E prerequisite must be passed", field_path="trust_boundary.decision"))
    if trust_boundary.get("ready_for_trust_service_integration_review") is not True:
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-E readiness flag is required", field_path="trust_boundary.ready"))
    for field in ("trust_boundary_package_hash", "audit_hash", "evidence_bundle_hash"):
        if not is_sha256(trust_boundary.get(field)):
            errors.append(architecture_error("architecture_evidence_invalid", "R2C-E hash is required", field_path=f"trust_boundary.{field}"))
    calls = trust_boundary.get("external_calls") if isinstance(trust_boundary.get("external_calls"), Mapping) else {}
    if any(value is not False for value in calls.values()):
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-E external call flags must be false", field_path="trust_boundary.external_calls"))
    for field in ("identity_service_configured", "signature_service_configured", "nonce_service_configured", "authorization_issuer_configured", "secret_resolution_authorized", "network_execution_authorized", "live_execution_authorized", "provider_transport_called", "credential_value_resolved"):
        _false(trust_boundary, field, errors)


def validate_prerequisite_evidence(trust_boundary: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    for payload, name in ((trust_boundary, "trust_boundary"), (evidence, "architecture_evidence")):
        forbidden = scan_architecture_surface(payload, code="architecture_evidence_invalid", field_path=name)
        if forbidden:
            errors.append(forbidden)
    _validate_trust_boundary(trust_boundary, errors)
    if evidence.get("architecture_evidence_version") != "1.0":
        errors.append(architecture_error("architecture_evidence_invalid", "unsupported evidence version", field_path="architecture_evidence_version"))
    if evidence.get("source_stage") != "R2C-E":
        errors.append(architecture_error("architecture_evidence_invalid", "source stage must be R2C-E", field_path="source_stage"))
    if evidence.get("stable_baseline") != STABLE_BASELINE:
        errors.append(architecture_error("architecture_evidence_invalid", "stable baseline mismatch", field_path="stable_baseline"))
    if evidence.get("trust_boundary_package_hash") != trust_boundary.get("trust_boundary_package_hash") or evidence.get("trust_boundary_audit_hash") != trust_boundary.get("audit_hash"):
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-E package hash mismatch", field_path="trust_boundary_package_hash"))
    for field in ("identity_provider_contract_ready", "signature_verifier_contract_ready", "nonce_issuer_contract_ready", "authorization_issuer_contract_ready", "r2c_d_change_freeze_present", "no_network", "no_secret", "no_transport", "protocol_unavailable", "random_and_crypto_blocked"):
        _true(evidence, field, errors)
    for field in ("identity_service_configured", "signature_service_configured", "nonce_service_configured", "authorization_issuer_configured", "identity_verification_performed", "signature_verification_performed", "nonce_issued", "live_authorization_issued", "real_vendor_capability_proven", "real_deployment_capability_proven"):
        _false(evidence, field, errors)
    if evidence.get("real_integration_started", False) is not False:
        errors.append(architecture_error("architecture_evidence_invalid", "real integration must not be started", field_path="real_integration_started"))
    if evidence.get("r2c_d_authorization_draft_state") != "review_ready":
        errors.append(architecture_error("architecture_evidence_invalid", "R2C-D authorization draft must be review ready", field_path="r2c_d_authorization_draft_state"))
    canonical = {
        "source_stage": evidence.get("source_stage"),
        "stable_baseline": evidence.get("stable_baseline"),
        "trust_boundary_package_hash": evidence.get("trust_boundary_package_hash"),
        "trust_boundary_audit_hash": evidence.get("trust_boundary_audit_hash"),
        "r2c_e_decision": trust_boundary.get("decision"),
        "r2c_e_stage": trust_boundary.get("stage"),
        "r2c_e_external_calls": external_calls_all_false(),
        "evidence_id": evidence.get("evidence_id"),
        "no_network": evidence.get("no_network"),
        "no_secret": evidence.get("no_secret"),
        "no_transport": evidence.get("no_transport"),
    }
    return hash_value(canonical), errors, canonical
