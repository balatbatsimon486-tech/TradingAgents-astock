"""Structured finding catalog validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import REQUIRED_REVIEW_SCOPE, SUPPORTED_VERSION, hash_value, require_safe_id, review_error, scan_forbidden_surface, sorted_records

SEVERITIES = ("critical", "high", "medium", "low", "informational")
STATUSES = frozenset({"open", "remediation_planned", "resolved_offline", "risk_acceptance_requested", "waiver_requested", "not_applicable"})


def validate_findings(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, int], set[str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="findings")
    if forbidden:
        errors.append(forbidden)
    if payload.get("findings_version") not in SUPPORTED_VERSION:
        errors.append(review_error("invalid_finding", "unsupported findings version", field_path="findings_version"))
    records = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    seen: set[str] = set()
    canonical: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    distribution = {severity: 0 for severity in SEVERITIES}
    remediation_required: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(review_error("invalid_finding", "finding must be an object", field_path=f"findings[{index}]"))
            continue
        item = dict(raw)
        finding_id = str(item.get("finding_id", ""))
        require_safe_id(finding_id, errors, "invalid_finding", f"findings[{index}].finding_id")
        if finding_id in seen:
            errors.append(review_error("duplicate_finding", "finding id must be unique", field_path=f"findings[{index}].finding_id"))
        seen.add(finding_id)
        severity = str(item.get("severity", ""))
        status = str(item.get("status", ""))
        if severity not in SEVERITIES:
            errors.append(review_error("invalid_finding", "finding severity is invalid", field_path=f"findings[{index}].severity"))
        else:
            distribution[severity] += 1
        if status not in STATUSES:
            errors.append(review_error("invalid_finding", "finding status is invalid", field_path=f"findings[{index}].status"))
        if not item.get("affected_component") or item.get("affected_component") not in REQUIRED_REVIEW_SCOPE:
            errors.append(review_error("invalid_finding", "finding must bind an architecture component", field_path=f"findings[{index}].affected_component"))
        for field in ("category", "description_code", "evidence_reference", "owner_role", "due_condition"):
            if not item.get(field):
                errors.append(review_error("invalid_finding", "finding field is required", field_path=f"findings[{index}].{field}"))
        if item.get("remediation_required") is True:
            remediation_id = str(item.get("remediation_id", ""))
            require_safe_id(remediation_id, errors, "remediation_missing", f"findings[{index}].remediation_id")
            if remediation_id:
                remediation_required.add(finding_id)
        if severity == "critical" and status != "resolved_offline":
            errors.append(review_error("critical_finding_unresolved", "critical finding is unresolved", field_path=f"findings[{index}].status"))
        if severity == "high" and status != "resolved_offline":
            errors.append(review_error("high_finding_unresolved", "high finding is unresolved", field_path=f"findings[{index}].status"))
        if severity == "medium" and status == "remediation_planned" and item.get("remediation_required") is not True:
            errors.append(review_error("remediation_missing", "medium finding requires remediation", field_path=f"findings[{index}].remediation_required"))
        if status == "risk_acceptance_requested" and severity == "critical":
            errors.append(review_error("critical_risk_acceptance_not_allowed", "critical finding cannot request risk acceptance", field_path=f"findings[{index}].status"))
        canonical.append(item)
        by_id[finding_id] = item
    canonical = sorted_records(canonical, "finding_id")
    return hash_value({"findings_version": payload.get("findings_version"), "findings": canonical}), errors, canonical, by_id, distribution, remediation_required
