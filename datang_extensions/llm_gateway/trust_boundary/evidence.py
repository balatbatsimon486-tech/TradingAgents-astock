"""Trust-boundary manifest and prerequisite evidence checks for R2C-E."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.contracts import STABLE_BASELINE, SUPPORTED_VERSION, hash_value, is_sha256, require_safe_id, scan_forbidden_surface, trust_error

REVIEW_FALSE_FIELDS = (
    "human_review_completed",
    "reviewer_identity_verified",
    "detached_signature_verified",
    "live_authorization_issued",
    "secret_resolution_authorized",
    "network_execution_authorized",
    "live_execution_authorized",
    "credential_value_resolved",
    "provider_transport_called",
)
EVIDENCE_FALSE_FIELDS = (
    "human_review_completed",
    "identity_verification_performed",
    "signature_verification_performed",
    "nonce_issued",
    "live_authorization_issued",
    "required_integration_actions_marked_complete",
)


def validate_r2c_d_review_result(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="trust_boundary_evidence_invalid", field_path="r2c_d_review_result")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("stage") != "tradingagents_r2c_d_offline_live_authorization_review":
        errors.append(trust_error("trust_boundary_evidence_invalid", "R2C-D review stage mismatch", field_path="stage"))
    if payload.get("passed") is not True or payload.get("decision") != "ready_for_human_signoff":
        errors.append(trust_error("trust_boundary_evidence_invalid", "R2C-D review result must be ready", field_path="decision"))
    if payload.get("review_package_sealed") is not True or payload.get("ready_for_human_signoff") is not True or payload.get("live_authorization_contract_ready") is not True:
        errors.append(trust_error("trust_boundary_evidence_invalid", "R2C-D package must be sealed and contract-ready", field_path="review_package_sealed"))
    for field in REVIEW_FALSE_FIELDS:
        if payload.get(field) is not False:
            errors.append(trust_error("trust_boundary_evidence_invalid", f"{field} must remain false", field_path=field))
    for field in ("review_package_hash", "authorization_draft_hash", "change_freeze_hash", "audit_hash"):
        if not is_sha256(payload.get(field)):
            errors.append(trust_error("trust_boundary_evidence_invalid", f"{field} must be SHA-256", field_path=field))
    return hash_value(payload), errors


def validate_trust_provider_manifest(
    payload: Mapping[str, Any],
    *,
    review_result: Mapping[str, Any],
    identity_contract: Mapping[str, Any],
    signature_contract: Mapping[str, Any],
    nonce_contract: Mapping[str, Any],
    issuer_contract: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="invalid_trust_provider_manifest", field_path="trust_provider_manifest")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("trust_provider_manifest_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("unsupported_trust_boundary_version", "unsupported trust boundary manifest version", field_path="trust_provider_manifest_version"))
    require_safe_id(payload.get("manifest_id"), errors, "invalid_trust_provider_manifest", "manifest_id")
    if payload.get("status") != "draft_for_integration_review":
        errors.append(trust_error("invalid_trust_provider_manifest", "manifest must be draft for integration review", field_path="status"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(trust_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("review_package_hash") != review_result.get("review_package_hash"):
        errors.append(trust_error("review_package_mismatch", "review package hash mismatch", field_path="review_package_hash"))
    if payload.get("authorization_draft_hash") != review_result.get("authorization_draft_hash"):
        errors.append(trust_error("authorization_draft_mismatch", "authorization draft hash mismatch", field_path="authorization_draft_hash"))
    contract_fields = {
        "identity_provider_contract_id": identity_contract.get("contract_id"),
        "signature_verifier_contract_id": signature_contract.get("contract_id"),
        "nonce_issuer_contract_id": nonce_contract.get("contract_id"),
        "authorization_issuer_contract_id": issuer_contract.get("contract_id"),
    }
    seen: set[str] = set()
    for field, expected in contract_fields.items():
        value = payload.get(field)
        require_safe_id(value, errors, "invalid_trust_provider_manifest", field)
        if value != expected:
            errors.append(trust_error("invalid_trust_provider_manifest", f"{field} does not match contract", field_path=field))
        text = str(value)
        if text in seen:
            errors.append(trust_error("duplicate_trust_contract_id", "contract ids must be unique", field_path=field))
        seen.add(text)
    if payload.get("environment") != "sandbox":
        errors.append(trust_error("invalid_trust_provider_manifest", "environment must be sandbox", field_path="environment"))
    if payload.get("single_call_only") is not True:
        errors.append(trust_error("invalid_trust_provider_manifest", "single call only must be true", field_path="single_call_only"))
    if payload.get("real_service_connections_allowed") is not False:
        errors.append(trust_error("invalid_trust_provider_manifest", "real service connections must be false", field_path="real_service_connections_allowed"))
    return hash_value(payload), errors


def validate_prerequisite_evidence(payload: Mapping[str, Any], *, review_result: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="trust_boundary_evidence_invalid", field_path="prerequisite_evidence")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("trust_boundary_evidence_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("trust_boundary_evidence_invalid", "unsupported evidence version", field_path="trust_boundary_evidence_version"))
    if payload.get("source_stage") != "R2C-D":
        errors.append(trust_error("trust_boundary_evidence_invalid", "source stage must be R2C-D", field_path="source_stage"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(trust_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    ci = payload.get("r2c_d_main_ci") if isinstance(payload.get("r2c_d_main_ci"), Mapping) else {}
    if ci.get("commit") != STABLE_BASELINE or ci.get("result") != "completed_success":
        errors.append(trust_error("trust_boundary_evidence_invalid", "R2C-D main CI evidence is invalid", field_path="r2c_d_main_ci"))
    for field in ("review_package_hash", "authorization_draft_hash", "change_freeze_hash"):
        if payload.get(field) != review_result.get(field):
            errors.append(trust_error("trust_boundary_evidence_invalid", f"{field} mismatch", field_path=field))
    if payload.get("review_package_sealed") is not True or payload.get("authorization_state") != "review_ready":
        errors.append(trust_error("trust_boundary_evidence_invalid", "review package or draft state is invalid", field_path="authorization_state"))
    for field in EVIDENCE_FALSE_FIELDS:
        if payload.get(field) is not False:
            errors.append(trust_error("trust_boundary_evidence_invalid", f"{field} must remain false", field_path=field))
    for field in ("no_secret", "no_network", "no_transport", "supersede_detection_required", "issuance_rejected_in_r2c_d", "consume_rejected_in_r2c_d"):
        if payload.get(field) is not True:
            errors.append(trust_error("trust_boundary_evidence_invalid", f"{field} must be true", field_path=field))
    return hash_value(payload), errors
