"""Offline operational drill plan validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import architecture_error, hash_value, require_safe_id, scan_architecture_surface, sorted_records


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def validate_drill_plan(drill: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(drill, code="invalid_drill_plan", field_path="drill_plan")
    if forbidden:
        errors.append(forbidden)
    if drill.get("drill_plan_version") != "1.0":
        errors.append(architecture_error("invalid_drill_plan", "unsupported drill plan version", field_path="drill_plan_version"))
    if drill.get("ready_for_tabletop_review") is not True:
        errors.append(architecture_error("invalid_drill_plan", "drill plan must be ready for tabletop review", field_path="ready_for_tabletop_review"))
    drills = _records(drill.get("drills"))
    if len(drills) < 12:
        errors.append(architecture_error("invalid_drill_plan", "drill plan must cover required failure modes", field_path="drills"))
    seen: set[str] = set()
    for index, item in enumerate(drills):
        drill_id = str(item.get("drill_id", ""))
        require_safe_id(drill_id, errors, "invalid_drill_plan", f"drills[{index}].drill_id")
        if drill_id in seen:
            errors.append(architecture_error("invalid_drill_plan", "drill ids must be unique", field_path=f"drills[{index}].drill_id"))
        seen.add(drill_id)
        if item.get("execution_state") != "not_executed":
            errors.append(architecture_error("drill_execution_not_available", "operational drills must not be executed in R2C-F", field_path=f"drills[{index}].execution_state"))
        if item.get("expected_decision") != "blocked":
            errors.append(architecture_error("invalid_drill_plan", "drills must expect fail-closed behavior", field_path=f"drills[{index}].expected_decision"))
        for required in ("scenario", "injected_failure", "expected_abort_condition", "expected_detection", "expected_owner_role", "expected_rollback_path"):
            if not item.get(required):
                errors.append(architecture_error("invalid_drill_plan", "drill field is required", field_path=f"drills[{index}].{required}"))
        if not isinstance(item.get("evidence_required"), list) or not item.get("evidence_required"):
            errors.append(architecture_error("invalid_drill_plan", "drill evidence list is required", field_path=f"drills[{index}].evidence_required"))
    canonical = dict(drill)
    canonical["drills"] = sorted_records(drills, "drill_id")
    return hash_value(canonical), errors, canonical["drills"]
