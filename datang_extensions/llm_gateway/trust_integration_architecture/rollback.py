"""Offline rollback and exit-plan validation for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import architecture_error, hash_value, scan_architecture_surface, sorted_records

REQUIRED_EXIT_FLAGS = frozenset({"connections_disabled_required", "restore_no_service_configured_state_required", "configuration_revert_required", "credential_rotation_requirement", "authorization_revocation_required", "nonce_registry_isolation_required", "audit_preservation_required", "dependency_removal_required", "data_deletion_verification_required", "synthetic_configuration_export_required", "vendor_portability_requirements"})


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def validate_rollback_plan(rollback: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(rollback, code="invalid_rollback_plan", field_path="rollback_plan")
    if forbidden:
        errors.append(forbidden)
    if rollback.get("rollback_plan_version") != "1.0":
        errors.append(architecture_error("invalid_rollback_plan", "unsupported rollback plan version", field_path="rollback_plan_version"))
    if rollback.get("status") != "draft_for_review":
        errors.append(architecture_error("invalid_rollback_plan", "rollback plan must remain draft", field_path="status"))
    if rollback.get("rollback_approved") is not False:
        errors.append(architecture_error("invalid_rollback_plan", "rollback approval is outside R2C-F", field_path="rollback_approved"))
    if rollback.get("automatic_rollback_execution_allowed") is not False or rollback.get("rollback_test_executed") is not False:
        errors.append(architecture_error("rollback_execution_not_available", "rollback execution must not occur in R2C-F", field_path="rollback_test_executed"))
    if rollback.get("rollback_ready_for_dry_run_review") is not True:
        errors.append(architecture_error("invalid_rollback_plan", "rollback plan must be ready for dry-run review", field_path="rollback_ready_for_dry_run_review"))
    if len(rollback.get("triggers") if isinstance(rollback.get("triggers"), list) else []) < 10:
        errors.append(architecture_error("invalid_rollback_plan", "rollback triggers are incomplete", field_path="triggers"))
    exit_strategy = rollback.get("exit_strategy") if isinstance(rollback.get("exit_strategy"), Mapping) else {}
    for flag in REQUIRED_EXIT_FLAGS:
        if exit_strategy.get(flag) is not True:
            errors.append(architecture_error("invalid_rollback_plan", "exit strategy flag is required", field_path=f"exit_strategy.{flag}"))
    for field in ("rollback_steps", "validation_steps"):
        if not _records(rollback.get(field)):
            errors.append(architecture_error("invalid_rollback_plan", "rollback section must be non-empty", field_path=field))
    canonical = dict(rollback)
    canonical["triggers"] = sorted(str(item) for item in rollback.get("triggers", []) if isinstance(item, str))
    canonical["exit_strategy"] = {str(key): exit_strategy[key] for key in sorted(exit_strategy)}
    canonical["rollback_steps"] = sorted_records(_records(rollback.get("rollback_steps")), "step_id")
    canonical["validation_steps"] = sorted_records(_records(rollback.get("validation_steps")), "step_id")
    return hash_value(canonical), errors, canonical
