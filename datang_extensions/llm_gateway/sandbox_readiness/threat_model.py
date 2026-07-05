"""Threat model validation for R2C-C sandbox readiness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.contracts import REQUIRED_THREAT_IDS, SAFE_REVIEW_STATUSES, SEVERITIES_REQUIRING_CONTROLS, SUPPORTED_VERSION, hash_value, readiness_error, require_safe_id, scan_forbidden_surface, sorted_records, string_list


def validate_threat_model(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(payload, prefix="threat_model")
    if secret_error:
        errors.append(secret_error)
        return hash_value(payload), errors
    if payload.get("threat_model_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("threat_model_invalid", "unsupported threat model version", field_path="threat_model_version"))
    require_safe_id(payload.get("threat_model_id"), errors, "threat_model_invalid", "threat_model_id")
    threats = payload.get("threats")
    if not isinstance(threats, list) or not threats:
        errors.append(readiness_error("threat_model_invalid", "threats must be a non-empty list", field_path="threats"))
        return hash_value(payload), errors
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, threat in enumerate(threats):
        if not isinstance(threat, Mapping):
            errors.append(readiness_error("threat_model_invalid", "threat must be an object", field_path=f"threats[{index}]"))
            continue
        item = dict(threat)
        threat_id = str(item.get("threat_id", ""))
        if not threat_id:
            errors.append(readiness_error("threat_model_invalid", "threat_id is required", field_path=f"threats[{index}].threat_id"))
        if threat_id in seen:
            errors.append(readiness_error("threat_model_invalid", "threat_id must be unique", field_path=f"threats[{index}].threat_id"))
        seen.add(threat_id)
        for field in ("category", "description", "residual_risk"):
            if not isinstance(item.get(field), str) or not item.get(field):
                errors.append(readiness_error("threat_model_invalid", f"{field} is required", field_path=f"threats[{index}].{field}"))
        severity = str(item.get("severity", ""))
        if severity not in {"low", "medium", "high", "critical"}:
            errors.append(readiness_error("threat_model_invalid", "severity is unsupported", field_path=f"threats[{index}].severity"))
        if item.get("review_status") not in SAFE_REVIEW_STATUSES:
            errors.append(readiness_error("threat_model_invalid", "review status is unsupported", field_path=f"threats[{index}].review_status"))
        controls = string_list(item.get("required_controls"))
        if severity in SEVERITIES_REQUIRING_CONTROLS and controls is None:
            errors.append(readiness_error("threat_model_invalid", "high severity threats require controls", field_path=f"threats[{index}].required_controls"))
        if string_list(item.get("evidence_refs")) is None:
            errors.append(readiness_error("threat_model_invalid", "evidence_refs must be explicit", field_path=f"threats[{index}].evidence_refs"))
        normalized.append(item)
    missing = sorted(REQUIRED_THREAT_IDS - seen)
    if missing:
        errors.append(readiness_error("threat_model_missing_required_threat", "required threat coverage is missing", field_path="threats"))
    canonical = {"threat_model_version": payload.get("threat_model_version"), "threat_model_id": payload.get("threat_model_id"), "threats": sorted_records(normalized, "threat_id")}
    return hash_value(canonical), errors
