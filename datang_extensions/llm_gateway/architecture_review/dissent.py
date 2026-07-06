"""Dissent and objection validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import REQUIRED_REVIEW_SCOPE, SUPPORTED_VERSION, hash_value, require_safe_id, review_error, scan_forbidden_surface, sorted_records

POSITIONS = frozenset({"support", "conditional_objection", "formal_objection", "abstain"})


def validate_dissent_records(payload: Mapping[str, Any], required_roles: list[str], remediation_ids: set[str]) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="dissent_records")
    if forbidden:
        errors.append(forbidden)
    if payload.get("dissent_record_set_version") not in SUPPORTED_VERSION:
        errors.append(review_error("architecture_review_error", "unsupported dissent record set version", field_path="dissent_record_set_version"))
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    seen: set[str] = set()
    canonical: list[dict[str, Any]] = []
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(review_error("architecture_review_error", "dissent record must be an object", field_path=f"records[{index}]"))
            continue
        item = dict(raw)
        dissent_id = str(item.get("dissent_id", ""))
        require_safe_id(dissent_id, errors, "architecture_review_error", f"records[{index}].dissent_id")
        if dissent_id in seen:
            errors.append(review_error("architecture_review_error", "dissent id must be unique", field_path=f"records[{index}].dissent_id"))
        seen.add(dissent_id)
        if item.get("dissent_record_version") not in SUPPORTED_VERSION:
            errors.append(review_error("architecture_review_error", "unsupported dissent record version", field_path=f"records[{index}].dissent_record_version"))
        for field in ("reviewer_id", "reviewer_role", "reason_code"):
            require_safe_id(item.get(field), errors, "architecture_review_error", f"records[{index}].{field}")
        if item.get("reviewer_role") not in required_roles:
            errors.append(review_error("architecture_review_error", "dissent reviewer role is not covered", field_path=f"records[{index}].reviewer_role"))
        if item.get("position") not in POSITIONS:
            errors.append(review_error("architecture_review_error", "dissent position is invalid", field_path=f"records[{index}].position"))
        if item.get("affected_component") not in REQUIRED_REVIEW_SCOPE:
            errors.append(review_error("architecture_review_error", "dissent component is invalid", field_path=f"records[{index}].affected_component"))
        if item.get("position") == "formal_objection" and item.get("resolution_status") != "resolved_offline":
            errors.append(review_error("formal_objection_unresolved", "formal objection is unresolved", field_path=f"records[{index}].resolution_status"))
        if item.get("position") == "conditional_objection" and item.get("resolution_status") == "unresolved":
            remediation_id = str(item.get("remediation_id", ""))
            if remediation_id not in remediation_ids and not item.get("signoff_precondition"):
                errors.append(review_error("formal_objection_unresolved", "conditional objection needs remediation or signoff precondition", field_path=f"records[{index}]"))
        if item.get("supersede_on_architecture_change") is not True:
            errors.append(review_error("architecture_review_error", "dissent must supersede on architecture change", field_path=f"records[{index}].supersede_on_architecture_change"))
        canonical.append(item)
    canonical = sorted_records(canonical, "dissent_id")
    return hash_value({"dissent_record_set_version": payload.get("dissent_record_set_version"), "records": canonical}), errors, canonical
