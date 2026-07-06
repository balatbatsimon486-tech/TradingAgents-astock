"""Synthetic architecture review record validation."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import SUPPORTED_VERSION, hash_value, parse_utc, require_safe_id, review_error, scan_forbidden_surface, sorted_records

ALLOWED_RECOMMENDATIONS = frozenset({"recommend_approve", "recommend_approve_with_conditions", "request_changes", "recommend_block", "abstain"})


def validate_review_records(payload: Mapping[str, Any], charter: Mapping[str, Any], required_roles: list[str], *, fixed_now: str) -> tuple[str, list[dict[str, str]], list[str], list[dict[str, Any]], bool]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="review_records")
    if forbidden:
        errors.append(forbidden)
    if payload.get("review_record_set_version") not in SUPPORTED_VERSION:
        errors.append(review_error("unsupported_architecture_review_version", "unsupported review record set version", field_path="review_record_set_version"))
    if payload.get("review_charter_id") != charter.get("review_charter_id"):
        errors.append(review_error("invalid_review_charter", "review charter id mismatch", field_path="review_charter_id"))
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    now = parse_utc(fixed_now)
    seen_reviewers: set[str] = set()
    seen_records: set[str] = set()
    covered: set[str] = set()
    counted: set[str] = set()
    summaries: list[dict[str, Any]] = []
    request_changes_present = False
    requester_role = str(charter.get("requester_role", ""))
    scope = set(str(item) for item in charter.get("review_scope", []) if isinstance(item, str))
    canonical_records: list[dict[str, Any]] = []
    if not records:
        errors.append(review_error("required_reviewer_role_missing", "review records are required", field_path="records"))
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(review_error("architecture_review_error", "review record must be an object", field_path=f"records[{index}]"))
            continue
        record = dict(raw)
        for field in ("review_record_id", "review_charter_id", "reviewer_id", "reviewer_role", "record_kind"):
            require_safe_id(record.get(field), errors, "architecture_review_error", f"records[{index}].{field}")
        record_id = str(record.get("review_record_id", ""))
        reviewer_id = str(record.get("reviewer_id", ""))
        role = str(record.get("reviewer_role", ""))
        if record_id in seen_records:
            errors.append(review_error("duplicate_reviewer", "review record id must be unique", field_path=f"records[{index}].review_record_id"))
        seen_records.add(record_id)
        if reviewer_id in seen_reviewers:
            errors.append(review_error("duplicate_reviewer", "reviewer id must be unique", field_path=f"records[{index}].reviewer_id"))
        seen_reviewers.add(reviewer_id)
        if role == requester_role or reviewer_id == requester_role:
            errors.append(review_error("requester_cannot_review", "requester cannot review", field_path=f"records[{index}].reviewer_role"))
        if role in required_roles:
            covered.add(role)
        else:
            errors.append(review_error("required_reviewer_role_missing", "reviewer role is not required", field_path=f"records[{index}].reviewer_role"))
        if record.get("review_record_version") not in SUPPORTED_VERSION:
            errors.append(review_error("unsupported_architecture_review_version", "unsupported review record version", field_path=f"records[{index}].review_record_version"))
        if record.get("review_charter_id") != charter.get("review_charter_id"):
            errors.append(review_error("invalid_review_charter", "record charter id mismatch", field_path=f"records[{index}].review_charter_id"))
        if record.get("record_kind") != "architecture_review_recommendation":
            errors.append(review_error("architecture_review_error", "record kind is invalid", field_path=f"records[{index}].record_kind"))
        decision = record.get("recommendation")
        if decision not in ALLOWED_RECOMMENDATIONS:
            errors.append(review_error("architecture_review_error", "review decision is invalid", field_path=f"records[{index}].recommendation"))
        if decision == "recommend_block":
            errors.append(review_error("review_block_recommendation_present", "review block recommendation is present", field_path=f"records[{index}].recommendation"))
        if decision == "request_changes":
            request_changes_present = True
        if decision != "abstain" and role in required_roles:
            counted.add(role)
        if record.get("identity_verification_status") != "not_available":
            errors.append(review_error("reviewer_identity_verification_unavailable", "real reviewer identity verification is unavailable", field_path=f"records[{index}].identity_verification_status"))
        if record.get("signature_status") != "not_available":
            errors.append(review_error("review_signature_verification_unavailable", "real review signatures are unavailable", field_path=f"records[{index}].signature_status"))
        if record.get("synthetic_record") is not True:
            errors.append(review_error("architecture_review_error", "record must be synthetic", field_path=f"records[{index}].synthetic_record"))
        reviewed = set(record.get("reviewed_components") if isinstance(record.get("reviewed_components"), list) else [])
        if not reviewed or not reviewed.issubset(scope):
            errors.append(review_error("architecture_review_error", "reviewed components must stay in charter scope", field_path=f"records[{index}].reviewed_components"))
        try:
            recorded_at = parse_utc(record.get("recorded_at"))
            valid_until = parse_utc(record.get("valid_until"))
        except ValueError:
            errors.append(review_error("architecture_review_error", "record timestamps must be UTC Z", field_path=f"records[{index}]"))
        else:
            if valid_until <= recorded_at:
                errors.append(review_error("architecture_review_error", "valid_until must be after recorded_at", field_path=f"records[{index}].valid_until"))
            if now >= valid_until:
                errors.append(review_error("review_record_expired", "review record is expired", field_path=f"records[{index}].valid_until"))
        summaries.append({"review_record_id": record_id, "reviewer_role": role, "record_decision": str(decision), "synthetic_record": bool(record.get("synthetic_record"))})
        canonical_records.append(record)
    missing = set(required_roles) - covered
    if missing:
        errors.append(review_error("required_reviewer_role_missing", "required reviewer role is missing", field_path="records"))
    if set(required_roles) - counted:
        errors.append(review_error("review_quorum_not_met", "effective quorum must cover all required roles", field_path="records"))
    canonical = {"review_record_set_version": payload.get("review_record_set_version"), "review_charter_id": payload.get("review_charter_id"), "records": sorted_records(canonical_records, "review_record_id")}
    return hash_value(canonical), errors, sorted(covered), sorted_records(summaries, "review_record_id"), request_changes_present
