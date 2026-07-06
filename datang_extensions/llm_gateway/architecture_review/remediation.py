"""Remediation plan validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import SUPPORTED_VERSION, hash_value, require_safe_id, review_error, scan_forbidden_surface, sorted_records

ALLOWED_STATES = frozenset({"not_completed", "offline_contract_satisfied"})


def validate_remediation_plan(payload: Mapping[str, Any], findings_by_id: dict[str, dict[str, Any]], required_finding_ids: set[str], *, request_changes_present: bool) -> tuple[str, list[dict[str, str]], list[dict[str, Any]], set[str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="remediation_plan")
    if forbidden:
        errors.append(forbidden)
    if payload.get("remediation_plan_version") not in SUPPORTED_VERSION:
        errors.append(review_error("remediation_missing", "unsupported remediation plan version", field_path="remediation_plan_version"))
    if payload.get("status") != "draft_for_review":
        errors.append(review_error("remediation_missing", "remediation plan must remain draft", field_path="status"))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    canonical: list[dict[str, Any]] = []
    by_finding: dict[str, dict[str, Any]] = {}
    remediation_ids: set[str] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            errors.append(review_error("remediation_missing", "remediation item must be an object", field_path=f"items[{index}]"))
            continue
        item = dict(raw)
        remediation_id = str(item.get("remediation_id", ""))
        finding_id = str(item.get("finding_id", ""))
        require_safe_id(remediation_id, errors, "remediation_missing", f"items[{index}].remediation_id")
        require_safe_id(finding_id, errors, "remediation_missing", f"items[{index}].finding_id")
        remediation_ids.add(remediation_id)
        if finding_id not in findings_by_id:
            errors.append(review_error("remediation_missing", "remediation references unknown finding", field_path=f"items[{index}].finding_id"))
        if finding_id in by_finding:
            errors.append(review_error("remediation_missing", "finding remediation must be unique", field_path=f"items[{index}].finding_id"))
        by_finding[finding_id] = item
        if not item.get("owner_role"):
            errors.append(review_error("remediation_missing", "remediation owner role is required", field_path=f"items[{index}].owner_role"))
        if not item.get("required_action_code"):
            errors.append(review_error("remediation_missing", "required action code is required", field_path=f"items[{index}].required_action_code"))
        if item.get("completion_state") not in ALLOWED_STATES:
            errors.append(review_error("remediation_missing", "real remediation completion is not available", field_path=f"items[{index}].completion_state"))
        if not isinstance(item.get("evidence_required"), list) or not item.get("evidence_required"):
            errors.append(review_error("remediation_missing", "remediation evidence requirements are required", field_path=f"items[{index}].evidence_required"))
        if item.get("blocks_real_integration") is not True:
            errors.append(review_error("remediation_missing", "real integration must remain blocked", field_path=f"items[{index}].blocks_real_integration"))
        canonical.append(item)
    for finding_id in required_finding_ids:
        if finding_id not in by_finding:
            errors.append(review_error("remediation_missing", "required finding remediation is missing", field_path=finding_id))
    if request_changes_present:
        unfinished = [item for item in by_finding.values() if item.get("completion_state") != "offline_contract_satisfied"]
        if unfinished:
            errors.append(review_error("review_changes_requested", "requested changes are not closed by offline remediation", field_path="review_records"))
    canonical = sorted_records(canonical, "remediation_id")
    return hash_value({"remediation_plan_version": payload.get("remediation_plan_version"), "status": payload.get("status"), "items": canonical}), errors, canonical, remediation_ids
