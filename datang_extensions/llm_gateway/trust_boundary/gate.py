"""Offline trust-boundary review gate for R2C-E."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.audit import build_trust_boundary_audit
from datang_extensions.llm_gateway.trust_boundary.contracts import (
    DECISION_BLOCKED,
    DECISION_READY,
    TrustBoundaryError,
    base_result,
    hash_value,
    trust_error,
)
from datang_extensions.llm_gateway.trust_boundary.evidence import validate_prerequisite_evidence, validate_r2c_d_review_result, validate_trust_provider_manifest
from datang_extensions.llm_gateway.trust_boundary.identity import validate_identity_provider_contract
from datang_extensions.llm_gateway.trust_boundary.issuance import validate_authorization_issuer_contract
from datang_extensions.llm_gateway.trust_boundary.nonces import validate_nonce_issuer_contract
from datang_extensions.llm_gateway.trust_boundary.signatures import validate_signature_verifier_contract


def _mapping(value: Mapping[str, Any] | Any, field_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if isinstance(value, Mapping):
        return dict(value), []
    return {}, [trust_error("trust_boundary_error", "payload must be an object", field_path=field_path)]


def _package_hash(component_hashes: Mapping[str, str], decision: str) -> str:
    return hash_value(
        {
            "component_hashes": dict(component_hashes),
            "decision_ceiling": DECISION_READY,
            "decision": decision,
            "identity_verified": False,
            "signature_verified": False,
            "nonce_issued": False,
            "authorization_issued": False,
            "live_authorized": False,
        }
    )


def run_offline_trust_boundary_review(
    r2c_d_review_result: Mapping[str, Any],
    trust_provider_manifest: Mapping[str, Any],
    identity_provider_contract: Mapping[str, Any],
    signature_verifier_contract: Mapping[str, Any],
    nonce_issuer_contract: Mapping[str, Any],
    authorization_issuer_contract: Mapping[str, Any],
    prerequisite_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    review, review_schema_errors = _mapping(r2c_d_review_result, "r2c_d_review_result")
    manifest, manifest_schema_errors = _mapping(trust_provider_manifest, "trust_provider_manifest")
    identity, identity_schema_errors = _mapping(identity_provider_contract, "identity_provider_contract")
    signature, signature_schema_errors = _mapping(signature_verifier_contract, "signature_verifier_contract")
    nonce, nonce_schema_errors = _mapping(nonce_issuer_contract, "nonce_issuer_contract")
    issuer, issuer_schema_errors = _mapping(authorization_issuer_contract, "authorization_issuer_contract")
    evidence, evidence_schema_errors = _mapping(prerequisite_evidence, "prerequisite_evidence")
    errors = review_schema_errors + manifest_schema_errors + identity_schema_errors + signature_schema_errors + nonce_schema_errors + issuer_schema_errors + evidence_schema_errors

    r2c_d_hash, r2c_d_errors = validate_r2c_d_review_result(review)
    identity_hash, identity_errors = validate_identity_provider_contract(identity)
    signature_hash, signature_errors = validate_signature_verifier_contract(signature)
    nonce_hash, nonce_errors = validate_nonce_issuer_contract(nonce)
    issuer_hash, issuer_errors = validate_authorization_issuer_contract(issuer)
    manifest_hash, manifest_errors = validate_trust_provider_manifest(
        manifest,
        review_result=review,
        identity_contract=identity,
        signature_contract=signature,
        nonce_contract=nonce,
        issuer_contract=issuer,
    )
    evidence_hash, evidence_errors = validate_prerequisite_evidence(evidence, review_result=review)
    errors.extend(r2c_d_errors + manifest_errors + identity_errors + signature_errors + nonce_errors + issuer_errors + evidence_errors)

    decision = DECISION_READY if not errors else DECISION_BLOCKED
    component_hashes = {
        "r2c_d_review_result_hash": r2c_d_hash,
        "trust_provider_manifest_hash": manifest_hash,
        "identity_contract_hash": identity_hash,
        "signature_contract_hash": signature_hash,
        "nonce_contract_hash": nonce_hash,
        "issuer_contract_hash": issuer_hash,
        "evidence_bundle_hash": evidence_hash,
        "blocking_findings_hash": hash_value(errors),
    }
    component_hashes["required_integration_actions_hash"] = hash_value(base_result([])["required_integration_actions"])

    result = base_result(errors)
    result.update(
        {
            "passed": not errors,
            "decision": decision,
            "ready_for_trust_service_integration_review": not errors,
            "identity_provider_contract_ready": not identity_errors and not identity_schema_errors,
            "signature_verifier_contract_ready": not signature_errors and not signature_schema_errors,
            "nonce_issuer_contract_ready": not nonce_errors and not nonce_schema_errors,
            "authorization_issuer_contract_ready": not issuer_errors and not issuer_schema_errors,
            "trust_provider_manifest_hash": manifest_hash,
            "identity_contract_hash": identity_hash,
            "signature_contract_hash": signature_hash,
            "nonce_contract_hash": nonce_hash,
            "issuer_contract_hash": issuer_hash,
            "evidence_bundle_hash": evidence_hash,
            "blocking_findings_hash": component_hashes["blocking_findings_hash"],
            "required_integration_actions_hash": component_hashes["required_integration_actions_hash"],
            "trust_boundary_package_hash": _package_hash(component_hashes, decision),
            "blocking_findings": list(errors),
            "errors": list(errors),
        }
    )
    if errors:
        result["ready_for_trust_service_integration_review"] = False
    audit = build_trust_boundary_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def build_expected_trust_boundary_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(result))


def schema_error_result(exc: Exception) -> dict[str, Any]:
    errors = getattr(exc, "errors", None)
    if not errors:
        errors = [trust_error("trust_boundary_error", type(exc).__name__)]
    result = base_result(list(errors))
    audit = build_trust_boundary_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def require_json_object(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustBoundaryError([trust_error("trust_boundary_error", "payload must be a JSON object", field_path=field_path)])
    return dict(value)
