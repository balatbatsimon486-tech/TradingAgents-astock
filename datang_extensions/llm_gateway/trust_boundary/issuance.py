"""Authorization issuer and unavailable trust-service protocol boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from datang_extensions.llm_gateway.trust_boundary.contracts import SUPPORTED_VERSION, hash_value, require_safe_id, require_true, scan_forbidden_surface, trust_error

REQUIRED_TRUE_FIELDS = (
    "manual_issue_required",
    "identity_verification_required",
    "detached_signature_verification_required",
    "nonce_issuance_required",
    "change_freeze_revalidation_required",
    "stable_baseline_revalidation_required",
    "atomic_issue_required",
    "duplicate_issue_rejected",
)


class IdentityAssertionVerifier(Protocol):
    def verify(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class DetachedSignatureVerifier(Protocol):
    def verify(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class OneTimeNonceIssuer(Protocol):
    def issue(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class LiveAuthorizationIssuer(Protocol):
    def issue(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


def validate_authorization_issuer_contract(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, code="authorization_issuer_contract_invalid", field_path="authorization_issuer_contract")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("authorization_issuer_contract_version") not in SUPPORTED_VERSION:
        errors.append(trust_error("authorization_issuer_contract_invalid", "unsupported issuer contract version", field_path="authorization_issuer_contract_version"))
    require_safe_id(payload.get("contract_id"), errors, "authorization_issuer_contract_invalid", "contract_id")
    if payload.get("configuration_status") != "not_configured":
        errors.append(trust_error("authorization_issuer_must_be_unconfigured", "authorization issuer must remain unconfigured", field_path="configuration_status"))
    if payload.get("issuance_mode") != "single_sandbox_call":
        errors.append(trust_error("authorization_issuer_contract_invalid", "issuance mode must be single sandbox call", field_path="issuance_mode"))
    require_true(payload, REQUIRED_TRUE_FIELDS, errors, "authorization_issuer_contract_invalid")
    ttl = payload.get("authorization_ttl_seconds_max")
    if not isinstance(ttl, int) or ttl <= 0 or ttl > 900:
        errors.append(trust_error("authorization_issuer_contract_invalid", "authorization ttl is invalid", field_path="authorization_ttl_seconds_max"))
    if payload.get("authorization_issued") is not False or payload.get("authorization_value_present") is not False or payload.get("execution_authorized") is not False:
        errors.append(trust_error("authorization_issuance_not_available", "authorization issuance is unavailable in R2C-E", field_path="authorization_issued"))
    return hash_value(payload), errors


class UnavailableIdentityAssertionVerifier:
    def verify(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {"passed": False, "verification_performed": False, "verification_succeeded": False, "errors": [trust_error("identity_verification_not_available", "identity verification is unavailable", field_path="identity_verifier")]}


class UnavailableDetachedSignatureVerifier:
    def verify(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {"passed": False, "verification_performed": False, "verification_succeeded": False, "errors": [trust_error("signature_verification_not_available", "signature verification is unavailable", field_path="signature_verifier")]}


class UnavailableOneTimeNonceIssuer:
    def issue(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {"passed": False, "nonce_issued": False, "nonce_value_present": False, "errors": [trust_error("nonce_generation_not_available", "nonce issuance is unavailable", field_path="nonce_issuer")]}


class UnavailableAuthorizationIssuer:
    def issue(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {"passed": False, "authorization_issued": False, "execution_authorized": False, "errors": [trust_error("authorization_issuance_not_available", "authorization issuance is unavailable", field_path="authorization_issuer")]}
