"""Review manifest and reviewer evidence validation for R2C-D."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.live_authorization_review.contracts import (
    STABLE_BASELINE,
    SUPPORTED_VERSION,
    hash_value,
    is_sha256,
    parse_utc,
    require_safe_id,
    require_sha256,
    review_error,
    scan_forbidden_surface,
    sorted_records,
)

REQUIRED_MANIFEST_IDS = (
    "review_manifest_id",
    "binding_id",
    "authorization_policy_id",
    "sandbox_profile_id",
    "provider_id",
    "model_id",
    "adapter_id",
    "adapter_version",
    "purpose",
    "task_type",
    "case_id",
    "prompt_id",
    "prompt_version",
    "snapshot_id",
    "input_artifact_id",
    "requester_id",
)
ALLOWED_RECOMMENDATIONS = frozenset({"recommend_approve", "recommend_block"})


def _role_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    roles = [str(item) for item in value]
    if len(set(roles)) != len(roles):
        return None
    for role in roles:
        if not role or "*" in role or "/" in role or "\\" in role:
            return None
    return roles


def validate_review_manifest(payload: Mapping[str, Any], readiness_result: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], list[str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, prefix="review_manifest")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors, []
    if payload.get("review_manifest_version") not in SUPPORTED_VERSION:
        errors.append(review_error("review_manifest_invalid", "unsupported review manifest version", field_path="review_manifest_version"))
    if payload.get("review_state") != "draft":
        errors.append(review_error("review_manifest_invalid", "review_state must be draft", field_path="review_state"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("review_manifest_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if readiness_result.get("passed") is not True or readiness_result.get("decision") != "ready_for_human_review":
        errors.append(review_error("readiness_result_not_ready", "R2C-C readiness result must be ready_for_human_review", field_path="readiness_result"))
    if payload.get("readiness_package_hash") != readiness_result.get("readiness_package_hash") or not is_sha256(payload.get("readiness_package_hash")):
        errors.append(review_error("review_manifest_readiness_mismatch", "readiness package hash mismatch", field_path="readiness_package_hash"))
    for field in REQUIRED_MANIFEST_IDS:
        require_safe_id(payload.get(field), errors, "review_manifest_identity_invalid", field)
    for field in ("prompt_spec_hash", "input_artifact_hash"):
        require_sha256(payload.get(field), errors, "review_manifest_lineage_invalid", field)
    roles = _role_list(payload.get("required_reviewer_roles"))
    if roles is None:
        errors.append(review_error("review_manifest_role_invalid", "required reviewer roles must be unique safe ids", field_path="required_reviewer_roles"))
        roles = []
    if payload.get("required_role_quorum") != len(roles) or not roles:
        errors.append(review_error("review_manifest_quorum_invalid", "quorum must cover all required roles", field_path="required_role_quorum"))
    if payload.get("requester_may_review") is not False:
        errors.append(review_error("review_manifest_requester_invalid", "requester may not review", field_path="requester_may_review"))
    canonical = dict(payload)
    canonical["required_reviewer_roles"] = sorted(roles)
    return hash_value(canonical), errors, roles


def validate_reviewer_records(payload: Mapping[str, Any], manifest: Mapping[str, Any], required_roles: list[str], *, fixed_now: str) -> tuple[str, list[dict[str, str]], list[str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, prefix="reviewer_records")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors, []
    if payload.get("review_record_set_version") not in SUPPORTED_VERSION:
        errors.append(review_error("review_record_set_invalid", "unsupported reviewer record set version", field_path="review_record_set_version"))
    if payload.get("review_manifest_id") != manifest.get("review_manifest_id"):
        errors.append(review_error("review_record_manifest_mismatch", "review manifest id mismatch", field_path="review_manifest_id"))
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    if not records:
        errors.append(review_error("review_record_set_invalid", "records must be non-empty", field_path="records"))
    now = parse_utc(fixed_now)
    seen_reviewers: set[str] = set()
    seen_ids: set[str] = set()
    covered_roles: set[str] = set()
    requester_id = str(manifest.get("requester_id", ""))
    canonical_records: list[dict[str, Any]] = []
    for index, raw_record in enumerate(records):
        if not isinstance(raw_record, Mapping):
            errors.append(review_error("review_record_invalid", "record must be an object", field_path=f"records[{index}]"))
            continue
        record = dict(raw_record)
        for field in ("review_record_id", "review_manifest_id", "reviewer_id", "reviewer_role", "record_kind", "reason_code"):
            require_safe_id(record.get(field), errors, "review_record_invalid", f"records[{index}].{field}")
        record_id = str(record.get("review_record_id", ""))
        reviewer_id = str(record.get("reviewer_id", ""))
        role = str(record.get("reviewer_role", ""))
        if record_id in seen_ids:
            errors.append(review_error("review_record_duplicate", "review record id must be unique", field_path=f"records[{index}].review_record_id"))
        seen_ids.add(record_id)
        if reviewer_id in seen_reviewers:
            errors.append(review_error("reviewer_duplicate", "reviewer id must be unique", field_path=f"records[{index}].reviewer_id"))
        seen_reviewers.add(reviewer_id)
        if reviewer_id == requester_id:
            errors.append(review_error("requester_review_not_allowed", "requester cannot be reviewer", field_path=f"records[{index}].reviewer_id"))
        if role in required_roles:
            covered_roles.add(role)
        else:
            errors.append(review_error("review_role_coverage_missing", "reviewer role is not required", field_path=f"records[{index}].reviewer_role"))
        if record.get("review_record_version") not in SUPPORTED_VERSION:
            errors.append(review_error("review_record_invalid", "unsupported record version", field_path=f"records[{index}].review_record_version"))
        if record.get("review_manifest_id") != manifest.get("review_manifest_id"):
            errors.append(review_error("review_record_manifest_mismatch", "record manifest id mismatch", field_path=f"records[{index}].review_manifest_id"))
        if record.get("record_kind") != "review_recommendation":
            errors.append(review_error("review_record_invalid", "record_kind must be review_recommendation", field_path=f"records[{index}].record_kind"))
        if record.get("recommendation") not in ALLOWED_RECOMMENDATIONS:
            errors.append(review_error("review_record_invalid", "recommendation is invalid", field_path=f"records[{index}].recommendation"))
        if record.get("recommendation") == "recommend_block":
            errors.append(review_error("reviewer_recommended_block", "a reviewer recommended block", field_path=f"records[{index}].recommendation"))
        if record.get("identity_verification_status") != "not_available":
            errors.append(review_error("real_identity_verification_unavailable", "real identity verification is unavailable", field_path=f"records[{index}].identity_verification_status"))
        if record.get("signature_status") != "not_available":
            errors.append(review_error("detached_signature_verification_unavailable", "detached signature verification is unavailable", field_path=f"records[{index}].signature_status"))
        if record.get("synthetic_record") is not True:
            errors.append(review_error("review_record_invalid", "record must be synthetic", field_path=f"records[{index}].synthetic_record"))
        try:
            recorded_at = parse_utc(record.get("recorded_at"))
            valid_until = parse_utc(record.get("valid_until"))
        except ValueError:
            errors.append(review_error("review_record_time_invalid", "record timestamps must be UTC Z", field_path=f"records[{index}]"))
        else:
            if valid_until <= recorded_at:
                errors.append(review_error("review_record_time_invalid", "valid_until must be after recorded_at", field_path=f"records[{index}].valid_until"))
            if now >= valid_until:
                errors.append(review_error("review_record_expired", "review record is expired", field_path=f"records[{index}].valid_until"))
        canonical_records.append(record)
    missing = set(required_roles) - covered_roles
    if missing:
        errors.append(review_error("review_role_coverage_missing", "required reviewer role is missing", field_path="records"))
    canonical = {
        "review_record_set_version": payload.get("review_record_set_version"),
        "review_manifest_id": payload.get("review_manifest_id"),
        "records": sorted_records(canonical_records, "review_record_id"),
    }
    return hash_value(canonical), errors, sorted(covered_roles)
