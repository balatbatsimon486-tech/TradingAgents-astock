"""Offline change-control plan validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import architecture_error, hash_value, scan_architecture_surface, sorted_records

REQUIRED_APPROVER_ROLES = frozenset({"security_owner", "platform_owner", "change_approver"})
REQUIRED_ABORT_CONDITIONS = frozenset({"stable_baseline_drift", "architecture_hash_mismatch", "unexpected_network_request", "secret_material_detected", "manual_approval_skip_attempted"})


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def validate_change_control_plan(change: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(change, code="invalid_change_control_plan", field_path="change_control_plan")
    if forbidden:
        errors.append(forbidden)
    if change.get("change_control_version") != "1.0":
        errors.append(architecture_error("invalid_change_control_plan", "unsupported change control version", field_path="change_control_version"))
    if change.get("status") != "draft_for_review":
        errors.append(architecture_error("invalid_change_control_plan", "change plan must remain draft", field_path="status"))
    if change.get("change_request_approved") is not False:
        errors.append(architecture_error("change_approval_not_available", "change approval is outside R2C-F", field_path="change_request_approved"))
    for field in ("implementation_authorized", "manual_approval_skip_allowed", "network_change_authorized", "production_change_allowed"):
        if change.get(field) is not False:
            errors.append(architecture_error("invalid_change_control_plan", "change execution must remain unavailable", field_path=field))
    approvers = set(change.get("required_approver_roles") if isinstance(change.get("required_approver_roles"), list) else [])
    if not REQUIRED_APPROVER_ROLES.issubset(approvers):
        errors.append(architecture_error("invalid_change_control_plan", "required approver roles are incomplete", field_path="required_approver_roles"))
    aborts = set(change.get("abort_conditions") if isinstance(change.get("abort_conditions"), list) else [])
    if not REQUIRED_ABORT_CONDITIONS.issubset(aborts):
        errors.append(architecture_error("invalid_change_control_plan", "abort conditions are incomplete", field_path="abort_conditions"))
    for field in ("pre_change_checks", "implementation_steps", "post_change_checks", "validation_steps"):
        if not _records(change.get(field)):
            errors.append(architecture_error("invalid_change_control_plan", "plan section must be non-empty", field_path=field))
    canonical = dict(change)
    canonical["required_approver_roles"] = sorted(approvers)
    canonical["abort_conditions"] = sorted(aborts)
    for field in ("pre_change_checks", "implementation_steps", "post_change_checks", "validation_steps"):
        canonical[field] = sorted_records(_records(change.get(field)), "check_id" if "checks" in field else "step_id")
    return hash_value(canonical), errors, canonical
