"""Prerequisite R2C-F evidence validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import ARCHITECTURE_PACKAGE_HASH, COMPONENT_HASH_FIELDS, FALSE_REVIEW_FIELDS, STABLE_BASELINE, SUPPORTED_VERSION, external_calls_all_false, hash_value, is_sha256, review_error, scan_forbidden_surface

EXPECTED_STAGE = "tradingagents_r2c_f_offline_trust_integration_architecture"
EXPECTED_DECISION = "ready_for_architecture_review"


def validate_prerequisite_evidence(architecture_result: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    for payload, name in ((architecture_result, "r2c_f_architecture_result"), (evidence, "prerequisite_evidence")):
        forbidden = scan_forbidden_surface(payload, field_path=name)
        if forbidden:
            errors.append(forbidden)
    if architecture_result.get("stage") != EXPECTED_STAGE:
        errors.append(review_error("architecture_review_error", "R2C-F stage mismatch", field_path="r2c_f.stage"))
    if architecture_result.get("passed") is not True or architecture_result.get("decision") != EXPECTED_DECISION:
        errors.append(review_error("architecture_review_blocked", "R2C-F architecture result must be ready", field_path="r2c_f.decision"))
    if architecture_result.get("architecture_package_hash") != ARCHITECTURE_PACKAGE_HASH:
        errors.append(review_error("architecture_package_mismatch", "R2C-F architecture package hash mismatch", field_path="r2c_f.architecture_package_hash"))
    if architecture_result.get("architecture_package_sealed") is not True or architecture_result.get("ready_for_architecture_review") is not True:
        errors.append(review_error("architecture_review_blocked", "R2C-F architecture package must be sealed", field_path="r2c_f.ready"))
    calls = architecture_result.get("external_calls") if isinstance(architecture_result.get("external_calls"), Mapping) else {}
    if calls and any(value is not False for value in calls.values()):
        errors.append(review_error("architecture_review_error", "R2C-F external call flags must be false", field_path="r2c_f.external_calls"))
    for field in FALSE_REVIEW_FIELDS:
        if field in architecture_result and architecture_result.get(field) is not False:
            errors.append(review_error("architecture_review_error", f"{field} must remain false", field_path=field))
    if evidence.get("prerequisite_evidence_version") not in SUPPORTED_VERSION:
        errors.append(review_error("architecture_review_error", "unsupported prerequisite evidence version", field_path="prerequisite_evidence_version"))
    if evidence.get("source_stage") != "R2C-F":
        errors.append(review_error("architecture_review_error", "source stage must be R2C-F", field_path="source_stage"))
    if evidence.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("stable_baseline_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if evidence.get("architecture_package_hash") != ARCHITECTURE_PACKAGE_HASH:
        errors.append(review_error("architecture_package_mismatch", "architecture package hash mismatch", field_path="architecture_package_hash"))
    component_hashes = evidence.get("component_hashes") if isinstance(evidence.get("component_hashes"), Mapping) else {}
    for field in COMPONENT_HASH_FIELDS:
        expected = architecture_result.get(field)
        actual = component_hashes.get(field)
        if expected and actual != expected:
            errors.append(review_error("architecture_review_package_superseded", "R2C-F component hash mismatch", field_path=f"component_hashes.{field}"))
        if actual is not None and not is_sha256(actual):
            errors.append(review_error("architecture_review_package_superseded", "component hash must be SHA-256", field_path=f"component_hashes.{field}"))
    if evidence.get("review_evidence_sealing_allowed") is not True:
        errors.append(review_error("architecture_review_error", "review evidence sealing must be allowed", field_path="review_evidence_sealing_allowed"))
    for field in ("real_review_completed", "real_signatures_verified", "architecture_approved", "vendor_selected", "procurement_approved", "deployment_authorized", "network_change_authorized", "real_integration_started"):
        if evidence.get(field) is not False:
            errors.append(review_error("architecture_approval_not_available", f"{field} must remain false", field_path=field))
    canonical = {
        "source_stage": evidence.get("source_stage"),
        "stable_baseline": evidence.get("stable_baseline"),
        "architecture_package_hash": evidence.get("architecture_package_hash"),
        "architecture_stage": architecture_result.get("stage"),
        "architecture_decision": architecture_result.get("decision"),
        "component_hashes": {key: component_hashes.get(key) for key in sorted(component_hashes)},
        "external_calls": external_calls_all_false(),
    }
    return hash_value(canonical), errors, canonical
