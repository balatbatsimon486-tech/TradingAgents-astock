"""Detached-signature verifier boundary validation for R2C-E."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.contracts import SUPPORTED_VERSION, hash_value, require_safe_id, require_true, scan_forbidden_surface, trust_error

REQUIRED_TRUE_FIELDS = (
    "certificate_chain_validation_required",
    "key_usage_validation_required",
    "revocation_check_required",
    "trusted_root_policy_required",
    "signer_identity_binding_required",
    "payload_binding_required",
)
WEAK_ALGORITHM_MARKERS = ("none", "shared", "hmac", "md5", "sha1")


def validate_signature_verifier_contract(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="signature_verifier_contract_invalid", field_path="signature_verifier_contract")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("signature_verifier_contract_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("signature_verifier_contract_invalid", "unsupported signature contract version", field_path="signature_verifier_contract_version"))
    require_safe_id(payload.get("contract_id"), errors, "signature_verifier_contract_invalid", "contract_id")
    if payload.get("configuration_status") != "not_configured":
        errors.append(trust_error("signature_service_must_be_unconfigured", "signature service must remain unconfigured", field_path="configuration_status"))
    if payload.get("signature_format") != "detached":
        errors.append(trust_error("signature_verifier_contract_invalid", "signature format must be detached", field_path="signature_format"))
    policy = payload.get("algorithm_policy")
    if not isinstance(policy, list) or not policy:
        errors.append(trust_error("signature_verifier_contract_invalid", "algorithm policy is required", field_path="algorithm_policy"))
    else:
        for item in policy:
            lowered = str(item).lower()
            if "policy_placeholder" not in lowered or any(marker in lowered for marker in WEAK_ALGORITHM_MARKERS):
                errors.append(trust_error("signature_verifier_contract_invalid", "algorithm policy must be a safe placeholder", field_path="algorithm_policy"))
                break
    if payload.get("payload_hash_algorithm") != "sha256":
        errors.append(trust_error("signature_verifier_contract_invalid", "payload hash algorithm must be sha256", field_path="payload_hash_algorithm"))
    require_true(payload, REQUIRED_TRUE_FIELDS, errors, "signature_verifier_contract_invalid")
    if payload.get("signature_value_present") is not False:
        errors.append(trust_error("signature_value_must_be_absent", "signature value must be absent", field_path="signature_value_present"))
    if payload.get("verification_performed") is not False or payload.get("verification_succeeded") is not False:
        errors.append(trust_error("signature_verification_not_available", "signature verification is not available in R2C-E", field_path="verification_performed"))
    return hash_value(payload), errors
