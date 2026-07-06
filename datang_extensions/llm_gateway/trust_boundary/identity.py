"""Identity-provider boundary validation for R2C-E."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_boundary.contracts import (
    SUPPORTED_VERSION,
    hash_value,
    require_safe_id,
    require_true,
    scan_forbidden_surface,
    trust_error,
)

REQUIRED_TRUE_FIELDS = (
    "requester_reviewer_separation_required",
    "multi_factor_authentication_required",
    "fresh_authentication_required",
    "audience_binding_required",
    "nonce_binding_required",
    "issuer_allowlist_required",
    "subject_uniqueness_required",
    "fail_closed_required",
)


def validate_identity_provider_contract(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="identity_provider_contract_invalid", field_path="identity_provider_contract")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("identity_provider_contract_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("identity_provider_contract_invalid", "unsupported identity contract version", field_path="identity_provider_contract_version"))
    require_safe_id(payload.get("contract_id"), errors, "identity_provider_contract_invalid", "contract_id")
    if payload.get("provider_kind") != "external_enterprise_identity_provider":
        errors.append(trust_error("identity_provider_contract_invalid", "provider kind must be external enterprise boundary", field_path="provider_kind"))
    if payload.get("configuration_status") != "not_configured":
        errors.append(trust_error("identity_service_must_be_unconfigured", "identity service must remain unconfigured", field_path="configuration_status"))
    if payload.get("protocol_kind") != "not_selected":
        errors.append(trust_error("identity_provider_contract_invalid", "protocol must not be selected in R2C-E", field_path="protocol_kind"))
    if payload.get("identity_subject_kind") != "opaque_subject_reference":
        errors.append(trust_error("identity_provider_contract_invalid", "subject must be opaque", field_path="identity_subject_kind"))
    if payload.get("required_assurance_level") != "high":
        errors.append(trust_error("identity_provider_contract_invalid", "high assurance is required", field_path="required_assurance_level"))
    require_true(payload, REQUIRED_TRUE_FIELDS, errors, "identity_provider_contract_invalid")
    age = payload.get("maximum_assertion_age_seconds")
    if not isinstance(age, int) or age <= 0 or age > 300:
        errors.append(trust_error("identity_provider_contract_invalid", "assertion age limit is invalid", field_path="maximum_assertion_age_seconds"))
    skew = payload.get("clock_skew_seconds_max")
    if not isinstance(skew, int) or skew < 0 or skew > 60:
        errors.append(trust_error("identity_provider_contract_invalid", "clock skew limit is invalid", field_path="clock_skew_seconds_max"))
    if payload.get("identity_assertion_present") is not False:
        errors.append(trust_error("identity_assertion_must_be_absent", "identity assertion must be absent", field_path="identity_assertion_present"))
    if payload.get("verification_performed") is not False or payload.get("verification_succeeded") is not False:
        errors.append(trust_error("identity_verification_not_available", "identity verification is not available in R2C-E", field_path="verification_performed"))
    return hash_value(payload), errors
