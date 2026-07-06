"""Supersede and re-review policy validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import ARCHITECTURE_PACKAGE_HASH, REQUIRED_SUPERSEDE_TRIGGERS, STABLE_BASELINE, SUPPORTED_VERSION, hash_value, parse_utc, require_safe_id, review_error, scan_forbidden_surface

ALLOWED_STATES = frozenset({"draft", "sealed_for_signoff", "superseded", "expired", "blocked"})


def evaluate_supersede_state(policy: Mapping[str, Any], original: Mapping[str, Any], candidate: Mapping[str, Any], *, fixed_now: str) -> dict[str, Any]:
    try:
        if parse_utc(fixed_now) >= parse_utc(policy.get("evidence_valid_until")):
            return {"state": "expired", "reason_code": "review_evidence_expiry"}
    except ValueError:
        return {"state": "expired", "reason_code": "review_evidence_expiry"}
    for key, value in original.items():
        if candidate.get(key) != value:
            return {"state": "superseded", "reason_code": f"{key}_change"}
    return {"state": "sealed_for_signoff", "reason_code": "unchanged"}


def validate_supersede_policy(payload: Mapping[str, Any], *, fixed_now: str) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="supersede_policy")
    if forbidden:
        errors.append(forbidden)
    if payload.get("supersede_policy_version") not in SUPPORTED_VERSION:
        errors.append(review_error("invalid_supersede_policy", "unsupported supersede policy version", field_path="supersede_policy_version"))
    require_safe_id(payload.get("supersede_policy_id"), errors, "invalid_supersede_policy", "supersede_policy_id")
    state = payload.get("evidence_state")
    if state not in ALLOWED_STATES:
        errors.append(review_error("invalid_supersede_policy", "evidence state is invalid", field_path="evidence_state"))
    if state == "superseded":
        errors.append(review_error("architecture_review_package_superseded", "review package is superseded", field_path="evidence_state"))
    if state == "expired":
        errors.append(review_error("architecture_review_evidence_expired", "review evidence is expired", field_path="evidence_state"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("architecture_package_hash") != ARCHITECTURE_PACKAGE_HASH:
        errors.append(review_error("architecture_package_mismatch", "architecture package hash mismatch", field_path="architecture_package_hash"))
    triggers = set(payload.get("supersede_triggers") if isinstance(payload.get("supersede_triggers"), list) else [])
    if not REQUIRED_SUPERSEDE_TRIGGERS.issubset(triggers):
        errors.append(review_error("invalid_supersede_policy", "supersede triggers are incomplete", field_path="supersede_triggers"))
    try:
        if parse_utc(fixed_now) >= parse_utc(payload.get("evidence_valid_until")):
            errors.append(review_error("architecture_review_evidence_expired", "review evidence is expired", field_path="evidence_valid_until"))
    except ValueError:
        errors.append(review_error("architecture_review_evidence_expired", "review evidence expiry must be UTC Z", field_path="evidence_valid_until"))
    if payload.get("approved_state_available") is not False:
        errors.append(review_error("invalid_supersede_policy", "approved state is outside R2C-G", field_path="approved_state_available"))
    canonical = dict(payload)
    canonical["supersede_triggers"] = sorted(triggers)
    return hash_value(canonical), errors, canonical
