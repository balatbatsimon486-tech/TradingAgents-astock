"""One-time nonce issuer boundary validation for R2C-E."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.contracts import SUPPORTED_VERSION, hash_value, require_safe_id, require_true, scan_forbidden_surface, trust_error

REPLAY_FIELDS = ("single_use_required", "atomic_consume_required", "replay_detection_required", "revocation_required")
REQUIRED_TRUE_FIELDS = ("binding_required", "storage_required")


def validate_nonce_issuer_contract(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="nonce_issuer_contract_invalid", field_path="nonce_issuer_contract")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("nonce_issuer_contract_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("nonce_issuer_contract_invalid", "unsupported nonce contract version", field_path="nonce_issuer_contract_version"))
    require_safe_id(payload.get("contract_id"), errors, "nonce_issuer_contract_invalid", "contract_id")
    if payload.get("configuration_status") != "not_configured":
        errors.append(trust_error("nonce_service_must_be_unconfigured", "nonce service must remain unconfigured", field_path="configuration_status"))
    if payload.get("nonce_kind") != "single_use_cryptographic_challenge":
        errors.append(trust_error("nonce_issuer_contract_invalid", "nonce kind must describe future one-time challenge", field_path="nonce_kind"))
    entropy = payload.get("minimum_entropy_bits")
    if not isinstance(entropy, int) or entropy < 128:
        errors.append(trust_error("nonce_issuer_contract_invalid", "nonce entropy requirement is too low", field_path="minimum_entropy_bits"))
    lifetime = payload.get("maximum_lifetime_seconds")
    if not isinstance(lifetime, int) or lifetime <= 0 or lifetime > 300:
        errors.append(trust_error("nonce_issuer_contract_invalid", "nonce lifetime is invalid", field_path="maximum_lifetime_seconds"))
    require_true(payload, REQUIRED_TRUE_FIELDS, errors, "nonce_issuer_contract_invalid")
    for field in REPLAY_FIELDS:
        if payload.get(field) is not True:
            errors.append(trust_error("nonce_replay_control_incomplete", f"{field} must be true", field_path=field))
    if payload.get("authorization_id_as_nonce_forbidden") is not True:
        errors.append(trust_error("nonce_issuer_contract_invalid", "authorization id must not be used as nonce", field_path="authorization_id_as_nonce_forbidden"))
    if payload.get("nonce_value_present") is not False or payload.get("nonce_commitment_present") is not False:
        errors.append(trust_error("nonce_value_must_be_absent", "nonce value and commitment must be absent", field_path="nonce_value_present"))
    if payload.get("nonce_issued") is not False or payload.get("nonce_consumed") is not False:
        errors.append(trust_error("nonce_generation_not_available", "nonce issue and consume are unavailable in R2C-E", field_path="nonce_issued"))
    return hash_value(payload), errors
