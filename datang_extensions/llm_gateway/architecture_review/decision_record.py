"""Architecture decision-record draft validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import ARCHITECTURE_PACKAGE_HASH, REQUIRED_REAL_WORLD_ACTIONS, STABLE_BASELINE, SUPPORTED_VERSION, hash_value, require_safe_id, review_error, scan_forbidden_surface

ALLOWED_PROPOSED = frozenset({"approve_offline_architecture", "approve_offline_architecture_with_conditions", "request_architecture_changes", "reject_offline_architecture"})
FALSE_DECISION_FIELDS = ("real_signoff_completed", "architecture_decision_approved", "vendor_selection_approved", "procurement_approved", "deployment_authorized", "network_change_authorized")


def validate_decision_record_draft(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="decision_record_draft")
    if forbidden:
        errors.append(forbidden)
    if payload.get("decision_record_version") not in SUPPORTED_VERSION:
        errors.append(review_error("invalid_decision_record", "unsupported decision record version", field_path="decision_record_version"))
    require_safe_id(payload.get("decision_record_id"), errors, "invalid_decision_record", "decision_record_id")
    if payload.get("decision_state") != "draft_ready_for_signoff":
        errors.append(review_error("invalid_decision_record", "decision record must remain draft", field_path="decision_state"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("architecture_package_hash") != ARCHITECTURE_PACKAGE_HASH:
        errors.append(review_error("architecture_package_mismatch", "architecture package mismatch", field_path="architecture_package_hash"))
    if payload.get("proposed_decision") not in ALLOWED_PROPOSED:
        errors.append(review_error("invalid_decision_record", "proposed decision is invalid", field_path="proposed_decision"))
    if payload.get("approved_decision") is not None:
        errors.append(review_error("architecture_approval_not_available", "approved decision is not available in R2C-G", field_path="approved_decision"))
    if payload.get("real_signoff_required") is not True:
        errors.append(review_error("invalid_decision_record", "real signoff remains required", field_path="real_signoff_required"))
    for field in FALSE_DECISION_FIELDS:
        if payload.get(field) is not False:
            errors.append(review_error("architecture_approval_not_available", f"{field} must remain false", field_path=field))
    if not payload.get("required_real_world_actions"):
        errors.append(review_error("required_real_world_actions_missing", "required real-world actions are required", field_path="required_real_world_actions"))
    canonical = dict(payload)
    canonical["conditions"] = sorted(str(item) for item in payload.get("conditions", []) if isinstance(item, str))
    canonical["open_findings"] = sorted(str(item) for item in payload.get("open_findings", []) if isinstance(item, str))
    canonical["unresolved_dissent"] = sorted(str(item) for item in payload.get("unresolved_dissent", []) if isinstance(item, str))
    canonical["required_real_world_actions"] = list(REQUIRED_REAL_WORLD_ACTIONS)
    return hash_value(canonical), errors, canonical
