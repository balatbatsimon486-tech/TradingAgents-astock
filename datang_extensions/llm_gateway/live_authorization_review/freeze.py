"""Change freeze validation for R2C-D."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.live_authorization_review.contracts import (
    REQUIRED_FREEZE_KINDS,
    STABLE_BASELINE,
    SUPPORTED_VERSION,
    hash_value,
    is_sha256,
    parse_utc,
    require_safe_id,
    review_error,
    scan_forbidden_surface,
    sorted_records,
)


def validate_change_freeze(payload: Mapping[str, Any], readiness_result: Mapping[str, Any], *, review_manifest_hash: str, review_record_set_hash: str) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, prefix="change_freeze")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors
    if payload.get("change_freeze_version") not in SUPPORTED_VERSION:
        errors.append(review_error("change_freeze_invalid", "unsupported freeze version", field_path="change_freeze_version"))
    if payload.get("freeze_state") != "sealed_for_review":
        errors.append(review_error("change_freeze_invalid", "freeze_state must be sealed_for_review", field_path="freeze_state"))
    require_safe_id(payload.get("freeze_id"), errors, "change_freeze_invalid", "freeze_id")
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("change_freeze_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("readiness_package_hash") != readiness_result.get("readiness_package_hash"):
        errors.append(review_error("change_freeze_readiness_mismatch", "readiness package hash mismatch", field_path="readiness_package_hash"))
    if payload.get("review_manifest_hash") != review_manifest_hash:
        errors.append(review_error("change_freeze_manifest_mismatch", "review manifest hash mismatch", field_path="review_manifest_hash"))
    if payload.get("automatic_unfreeze_allowed") is not False:
        errors.append(review_error("change_freeze_invalid", "automatic unfreeze is not allowed", field_path="automatic_unfreeze_allowed"))
    if payload.get("changes_require_new_review") is not True:
        errors.append(review_error("change_freeze_invalid", "changes must require new review", field_path="changes_require_new_review"))
    try:
        parse_utc(payload.get("sealed_at"))
    except ValueError:
        errors.append(review_error("change_freeze_invalid", "sealed_at must be UTC Z", field_path="sealed_at"))
    artifacts = payload.get("frozen_artifacts") if isinstance(payload.get("frozen_artifacts"), list) else []
    if not artifacts:
        errors.append(review_error("change_freeze_artifact_missing", "frozen artifacts must be non-empty", field_path="frozen_artifacts"))
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    canonical_artifacts: list[dict[str, Any]] = []
    for index, raw_artifact in enumerate(artifacts):
        if not isinstance(raw_artifact, Mapping):
            errors.append(review_error("change_freeze_artifact_invalid", "artifact must be an object", field_path=f"frozen_artifacts[{index}]"))
            continue
        artifact = dict(raw_artifact)
        require_safe_id(artifact.get("artifact_kind"), errors, "change_freeze_artifact_invalid", f"frozen_artifacts[{index}].artifact_kind")
        require_safe_id(artifact.get("artifact_id"), errors, "change_freeze_artifact_invalid", f"frozen_artifacts[{index}].artifact_id")
        artifact_id = str(artifact.get("artifact_id", ""))
        artifact_kind = str(artifact.get("artifact_kind", ""))
        if artifact_id in seen_ids:
            errors.append(review_error("change_freeze_artifact_duplicate", "artifact id must be unique", field_path=f"frozen_artifacts[{index}].artifact_id"))
        seen_ids.add(artifact_id)
        seen_kinds.add(artifact_kind)
        if not is_sha256(artifact.get("artifact_hash")):
            errors.append(review_error("change_freeze_artifact_invalid", "artifact hash must be SHA-256", field_path=f"frozen_artifacts[{index}].artifact_hash"))
        if artifact_kind == "review_manifest" and artifact.get("artifact_hash") != review_manifest_hash:
            errors.append(review_error("change_freeze_manifest_mismatch", "review manifest artifact hash mismatch", field_path=f"frozen_artifacts[{index}].artifact_hash"))
        if artifact_kind == "reviewer_records" and artifact.get("artifact_hash") != review_record_set_hash:
            errors.append(review_error("change_freeze_artifact_invalid", "reviewer record artifact hash mismatch", field_path=f"frozen_artifacts[{index}].artifact_hash"))
        canonical_artifacts.append(artifact)
    if REQUIRED_FREEZE_KINDS - seen_kinds:
        errors.append(review_error("change_freeze_artifact_missing", "required frozen artifact is missing", field_path="frozen_artifacts"))
    canonical = dict(payload)
    canonical["frozen_artifacts"] = sorted_records(canonical_artifacts, "artifact_id")
    return hash_value(canonical), errors
