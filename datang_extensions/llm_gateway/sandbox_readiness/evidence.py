"""Prerequisite evidence and incident response validation for R2C-C."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.contracts import REQUIRED_EVIDENCE_IDS, REQUIRED_MILESTONES, REQUIRED_STOP_CONDITIONS, STABLE_BASELINE, SUPPORTED_VERSION, hash_value, is_sha256, readiness_error, scan_forbidden_surface, sorted_records, string_list


def validate_prerequisite_evidence(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(payload, prefix="prerequisite_evidence")
    if secret_error:
        errors.append(secret_error)
        return hash_value(payload), errors
    if payload.get("evidence_bundle_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("evidence_invalid", "unsupported evidence version", field_path="evidence_bundle_version"))
    if payload.get("project") != "TradingAgents-astock":
        errors.append(readiness_error("evidence_invalid", "project mismatch", field_path="project"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(readiness_error("evidence_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    milestones = payload.get("milestones") if isinstance(payload.get("milestones"), list) else []
    by_name = {str(item.get("milestone", "")): item for item in milestones if isinstance(item, Mapping)}
    for milestone, commit in REQUIRED_MILESTONES.items():
        item = by_name.get(milestone)
        if item is None or item.get("status") != "sealed" or item.get("commit") != commit:
            errors.append(readiness_error("evidence_missing_milestone", "sealed milestone evidence is missing", field_path=f"milestones.{milestone}"))
    refs = payload.get("evidence_refs") if isinstance(payload.get("evidence_refs"), list) else []
    by_ref = {str(item.get("evidence_id", "")): item for item in refs if isinstance(item, Mapping)}
    for evidence_id in REQUIRED_EVIDENCE_IDS:
        item = by_ref.get(evidence_id)
        if item is None or item.get("status") != "passed" or not is_sha256(item.get("hash")):
            errors.append(readiness_error("evidence_missing_required_ref", "required evidence reference is missing", field_path=f"evidence_refs.{evidence_id}"))
    canonical = {
        "evidence_bundle_version": payload.get("evidence_bundle_version"),
        "project": payload.get("project"),
        "stable_baseline": payload.get("stable_baseline"),
        "milestones": sorted_records([dict(item) for item in milestones if isinstance(item, Mapping)], "milestone"),
        "evidence_refs": sorted_records([dict(item) for item in refs if isinstance(item, Mapping)], "evidence_id"),
    }
    return hash_value(canonical), errors


def validate_incident_response(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(payload, prefix="incident_response")
    if secret_error:
        errors.append(secret_error)
        return hash_value(payload), errors
    if payload.get("kill_switch_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("incident_response_invalid", "unsupported kill switch version", field_path="kill_switch_version"))
    if payload.get("default_state") != "blocked":
        errors.append(readiness_error("incident_response_invalid", "default state must be blocked", field_path="default_state"))
    if payload.get("live_execution_enabled") is not False:
        errors.append(readiness_error("incident_response_invalid", "live execution must remain disabled", field_path="live_execution_enabled"))
    if payload.get("manual_enable_required") is not True:
        errors.append(readiness_error("incident_response_invalid", "manual enable must be required", field_path="manual_enable_required"))
    if payload.get("automatic_enable_allowed") is not False:
        errors.append(readiness_error("incident_response_invalid", "automatic enable is not allowed", field_path="automatic_enable_allowed"))
    if payload.get("fail_closed") is not True:
        errors.append(readiness_error("incident_response_invalid", "kill switch must fail closed", field_path="fail_closed"))
    if payload.get("automatic_retry_after_incident") is not False:
        errors.append(readiness_error("incident_response_invalid", "automatic retry after incident is not allowed", field_path="automatic_retry_after_incident"))
    for field in ("secret_exposure_rotation_plan", "unauthorized_network_shutdown_plan", "audit_failure_plan", "rollback_plan", "incident_owner_role"):
        if not isinstance(payload.get(field), str) or not payload.get(field):
            errors.append(readiness_error("incident_response_invalid", f"{field} is required", field_path=field))
    conditions = set(string_list(payload.get("stop_conditions")) or [])
    if REQUIRED_STOP_CONDITIONS - conditions:
        errors.append(readiness_error("incident_stop_condition_missing", "required stop condition is missing", field_path="stop_conditions"))
    canonical = dict(payload)
    if isinstance(canonical.get("stop_conditions"), list):
        canonical["stop_conditions"] = sorted(str(item) for item in canonical["stop_conditions"])
    return hash_value(canonical), errors
