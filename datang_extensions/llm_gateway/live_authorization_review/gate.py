"""Offline R2C-D review sealing gate."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.live_authorization_review.audit import build_review_audit
from datang_extensions.llm_gateway.live_authorization_review.attestations import validate_review_manifest, validate_reviewer_records
from datang_extensions.llm_gateway.live_authorization_review.contracts import (
    DECISION_BLOCKED,
    DECISION_READY,
    FALSE_EXECUTION_FIELDS,
    LiveAuthorizationReviewError,
    base_result,
    hash_value,
    review_error,
    scan_forbidden_surface,
)
from datang_extensions.llm_gateway.live_authorization_review.envelope import validate_authorization_draft
from datang_extensions.llm_gateway.live_authorization_review.freeze import validate_change_freeze


def _mapping(value: Mapping[str, Any] | Any, field_path: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if isinstance(value, Mapping):
        return dict(value), []
    return {}, [review_error("review_schema_error", "payload must be an object", field_path=field_path)]


def _readiness_errors(readiness: Mapping[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(readiness, prefix="readiness_result")
    if forbidden:
        errors.append(forbidden)
    if readiness.get("stage") != "tradingagents_r2c_c_offline_sandbox_readiness":
        errors.append(review_error("readiness_result_invalid", "readiness stage mismatch", field_path="stage"))
    if readiness.get("passed") is not True or readiness.get("decision") != "ready_for_human_review" or readiness.get("ready_for_human_review") is not True:
        errors.append(review_error("readiness_result_not_ready", "readiness result must be ready_for_human_review", field_path="decision"))
    if readiness.get("readiness_package_hash") in (None, ""):
        errors.append(review_error("readiness_result_invalid", "readiness package hash is required", field_path="readiness_package_hash"))
    for field in ("human_review_completed",) + FALSE_EXECUTION_FIELDS:
        if readiness.get(field) is not False:
            errors.append(review_error("readiness_result_invalid", f"{field} must remain false", field_path=field))
    return errors


def _package_hash(*, readiness_package_hash: str, review_manifest_hash: str, review_record_set_hash: str, change_freeze_hash: str) -> str:
    return hash_value(
        {
            "readiness_package_hash": readiness_package_hash,
            "review_manifest_hash": review_manifest_hash,
            "review_record_set_hash": review_record_set_hash,
            "change_freeze_hash": change_freeze_hash,
            "decision_ceiling": DECISION_READY,
            "live_authorized": False,
        }
    )


def run_offline_live_authorization_review(
    readiness_result: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
    reviewer_records: Mapping[str, Any],
    change_freeze: Mapping[str, Any],
    authorization_draft: Mapping[str, Any],
    *,
    fixed_now: str,
) -> dict[str, Any]:
    readiness, readiness_schema_errors = _mapping(readiness_result, "readiness_result")
    manifest, manifest_schema_errors = _mapping(review_manifest, "review_manifest")
    records, records_schema_errors = _mapping(reviewer_records, "reviewer_records")
    freeze, freeze_schema_errors = _mapping(change_freeze, "change_freeze")
    draft, draft_schema_errors = _mapping(authorization_draft, "authorization_draft")
    errors = readiness_schema_errors + manifest_schema_errors + records_schema_errors + freeze_schema_errors + draft_schema_errors

    errors.extend(_readiness_errors(readiness))
    review_manifest_hash, manifest_errors, required_roles = validate_review_manifest(manifest, readiness)
    errors.extend(manifest_errors)
    review_record_set_hash, record_errors, covered_roles = validate_reviewer_records(records, manifest, required_roles, fixed_now=fixed_now)
    errors.extend(record_errors)
    change_freeze_hash, freeze_errors = validate_change_freeze(readiness_result=readiness, payload=freeze, review_manifest_hash=review_manifest_hash, review_record_set_hash=review_record_set_hash)
    errors.extend(freeze_errors)
    review_package_hash = _package_hash(
        readiness_package_hash=str(readiness.get("readiness_package_hash", "")),
        review_manifest_hash=review_manifest_hash,
        review_record_set_hash=review_record_set_hash,
        change_freeze_hash=change_freeze_hash,
    )
    authorization_draft_hash, draft_errors, authorization_id = validate_authorization_draft(
        draft,
        manifest,
        readiness_package_hash=str(readiness.get("readiness_package_hash", "")),
        review_package_hash=review_package_hash,
        change_freeze_hash=change_freeze_hash,
        fixed_now=fixed_now,
    )
    errors.extend(draft_errors)

    result = base_result(errors)
    result.update(
        {
            "decision": DECISION_READY if not errors else DECISION_BLOCKED,
            "review_package_sealed": not errors,
            "ready_for_human_signoff": not errors,
            "live_authorization_contract_ready": not errors,
            "authorization_id": authorization_id,
            "review_manifest_hash": review_manifest_hash,
            "review_record_set_hash": review_record_set_hash,
            "change_freeze_hash": change_freeze_hash,
            "authorization_draft_hash": authorization_draft_hash,
            "review_package_hash": review_package_hash,
            "required_reviewer_roles": sorted(required_roles),
            "covered_reviewer_roles": sorted(covered_roles),
            "errors": list(errors),
        }
    )
    if errors:
        result["passed"] = False
    audit = build_review_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def build_expected_review_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(result))


def schema_error_result(exc: Exception) -> dict[str, Any]:
    errors = getattr(exc, "errors", None)
    if not errors:
        errors = [review_error("review_schema_error", type(exc).__name__)]
    result = base_result(list(errors))
    audit = build_review_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def require_json_object(value: Any, *, field_path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveAuthorizationReviewError([review_error("review_schema_error", "payload must be a JSON object", field_path=field_path)])
    return dict(value)
