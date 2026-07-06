"""Offline ownership matrix validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import architecture_error, hash_value, require_safe_id, scan_architecture_surface, sorted_records

REQUIRED_CONTROLS = frozenset({"identity-provider-policy", "signature-verifier-policy", "nonce-issuer-policy", "authorization-issuer-policy", "audit-sink-policy", "change-control-policy", "rollback-policy"})


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def validate_ownership_matrix(ownership: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(ownership, code="invalid_ownership_matrix", field_path="ownership_matrix")
    if forbidden:
        errors.append(forbidden)
    if ownership.get("ownership_matrix_version") != "1.0":
        errors.append(architecture_error("invalid_ownership_matrix", "unsupported ownership matrix version", field_path="ownership_matrix_version"))
    if ownership.get("real_people_assigned") is not False:
        errors.append(architecture_error("invalid_ownership_matrix", "real people assignment is outside R2C-F", field_path="real_people_assigned"))
    assignments = _records(ownership.get("assignments"))
    controls = {str(item.get("control_id", "")) for item in assignments}
    if not REQUIRED_CONTROLS.issubset(controls):
        errors.append(architecture_error("invalid_ownership_matrix", "required control ownership is incomplete", field_path="assignments"))
    seen_controls: set[str] = set()
    for index, item in enumerate(assignments):
        control_id = str(item.get("control_id", ""))
        require_safe_id(control_id, errors, "invalid_ownership_matrix", f"assignments[{index}].control_id")
        if control_id in seen_controls:
            errors.append(architecture_error("invalid_ownership_matrix", "control ownership rows must be unique", field_path=f"assignments[{index}].control_id"))
        seen_controls.add(control_id)
        if "accountable_roles" in item:
            errors.append(architecture_error("accountable_role_not_unique", "each control must have exactly one accountable role", field_path=f"assignments[{index}].accountable_roles"))
        if not isinstance(item.get("accountable_role"), str) or not item.get("accountable_role"):
            errors.append(architecture_error("accountable_role_not_unique", "accountable role is required", field_path=f"assignments[{index}].accountable_role"))
        for role_field in ("responsible_roles", "consulted_roles", "informed_roles"):
            if not isinstance(item.get(role_field), list) or not item.get(role_field):
                errors.append(architecture_error("invalid_ownership_matrix", "role list is required", field_path=f"assignments[{index}].{role_field}"))

    duties = ownership.get("separation_of_duties") if isinstance(ownership.get("separation_of_duties"), Mapping) else {}
    change_approver = duties.get("change_approver_role")
    change_requester = duties.get("change_requester_role")
    incident_commander = duties.get("incident_commander_role")
    rollback_operator = duties.get("rollback_operator_role")
    if change_approver in {change_requester, incident_commander, rollback_operator} or incident_commander == rollback_operator:
        errors.append(architecture_error("separation_of_duties_violation", "approval, request, incident and rollback roles must stay separated", field_path="separation_of_duties"))
    service_roles = duties.get("failed_service_owner_roles") if isinstance(duties.get("failed_service_owner_roles"), list) else []
    if not service_roles or any(role in {change_approver, rollback_operator} for role in service_roles):
        errors.append(architecture_error("separation_of_duties_violation", "service owners must not be the approver or rollback operator", field_path="separation_of_duties.failed_service_owner_roles"))

    canonical = dict(ownership)
    canonical["assignments"] = sorted_records(assignments, "control_id")
    if isinstance(duties, Mapping):
        canonical["separation_of_duties"] = {str(key): duties[key] for key in sorted(duties)}
    return hash_value(canonical), errors, canonical["assignments"]
