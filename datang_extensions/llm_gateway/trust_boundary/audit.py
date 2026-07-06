"""Audit helpers for R2C-E offline trust-boundary review."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.contracts import TRUST_BOUNDARY_STAGE, hash_value


def build_trust_boundary_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = {
        "audit_schema_version": "1.0",
        "stage": TRUST_BOUNDARY_STAGE,
        "decision": payload.get("decision", "blocked"),
        "ready_for_trust_service_integration_review": bool(payload.get("ready_for_trust_service_integration_review", False)),
        "identity_provider_contract_ready": bool(payload.get("identity_provider_contract_ready", False)),
        "signature_verifier_contract_ready": bool(payload.get("signature_verifier_contract_ready", False)),
        "nonce_issuer_contract_ready": bool(payload.get("nonce_issuer_contract_ready", False)),
        "authorization_issuer_contract_ready": bool(payload.get("authorization_issuer_contract_ready", False)),
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
        "trust_provider_manifest_hash": str(payload.get("trust_provider_manifest_hash", "")),
        "identity_contract_hash": str(payload.get("identity_contract_hash", "")),
        "signature_contract_hash": str(payload.get("signature_contract_hash", "")),
        "nonce_contract_hash": str(payload.get("nonce_contract_hash", "")),
        "issuer_contract_hash": str(payload.get("issuer_contract_hash", "")),
        "evidence_bundle_hash": str(payload.get("evidence_bundle_hash", "")),
        "trust_boundary_package_hash": str(payload.get("trust_boundary_package_hash", "")),
        "required_integration_action_count": len(payload.get("required_integration_actions", [])) if isinstance(payload.get("required_integration_actions"), list) else 0,
        "external_calls": dict(payload.get("external_calls", {})) if isinstance(payload.get("external_calls"), Mapping) else {},
        "error_codes": [str(error.get("code", "")) for error in payload.get("errors", []) if isinstance(error, Mapping)],
    }
    audit["audit_hash"] = hash_value({key: value for key, value in audit.items() if key != "audit_hash"})
    return audit
