"""Review charter validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import ARCHITECTURE_PACKAGE_HASH, REQUIRED_REVIEW_SCOPE, REQUIRED_REVIEWER_ROLES, STABLE_BASELINE, SUPPORTED_VERSION, hash_value, require_safe_id, review_error, scan_forbidden_surface


def validate_review_charter(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any], list[str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="review_charter")
    if forbidden:
        errors.append(forbidden)
    if payload.get("review_charter_version") not in SUPPORTED_VERSION:
        errors.append(review_error("unsupported_architecture_review_version", "unsupported review charter version", field_path="review_charter_version"))
    require_safe_id(payload.get("review_charter_id"), errors, "invalid_review_charter", "review_charter_id")
    if payload.get("status") != "draft_for_review":
        errors.append(review_error("invalid_review_charter", "review charter must remain draft", field_path="status"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("architecture_package_hash") != ARCHITECTURE_PACKAGE_HASH:
        errors.append(review_error("architecture_package_mismatch", "architecture package hash mismatch", field_path="architecture_package_hash"))
    roles = [str(item) for item in payload.get("required_reviewer_roles", [])] if isinstance(payload.get("required_reviewer_roles"), list) else []
    if set(roles) != set(REQUIRED_REVIEWER_ROLES) or len(roles) != len(set(roles)):
        errors.append(review_error("required_reviewer_role_missing", "required reviewer roles are incomplete", field_path="required_reviewer_roles"))
    if payload.get("required_role_quorum") != len(REQUIRED_REVIEWER_ROLES):
        errors.append(review_error("review_quorum_not_met", "quorum must cover all required roles", field_path="required_role_quorum"))
    requester_role = str(payload.get("requester_role", ""))
    require_safe_id(requester_role, errors, "invalid_review_charter", "requester_role")
    if payload.get("requester_may_review") is not False:
        errors.append(review_error("requester_cannot_review", "requester may not review", field_path="requester_may_review"))
    scope = [str(item) for item in payload.get("review_scope", [])] if isinstance(payload.get("review_scope"), list) else []
    if "*" in scope or not REQUIRED_REVIEW_SCOPE.issubset(set(scope)):
        errors.append(review_error("invalid_review_charter", "review scope must cover required components without wildcards", field_path="review_scope"))
    if payload.get("real_reviewers_assigned") is not False:
        errors.append(review_error("invalid_review_charter", "real reviewers must not be assigned in R2C-G", field_path="real_reviewers_assigned"))
    if payload.get("real_signatures_required") is not True:
        errors.append(review_error("invalid_review_charter", "real signatures remain a future requirement", field_path="real_signatures_required"))
    if payload.get("real_signatures_present") is not False:
        errors.append(review_error("invalid_review_charter", "real signatures must not be present", field_path="real_signatures_present"))
    canonical = dict(payload)
    canonical["required_reviewer_roles"] = sorted(set(roles))
    canonical["review_scope"] = sorted(set(scope))
    return hash_value(canonical), errors, canonical, sorted(set(roles))
