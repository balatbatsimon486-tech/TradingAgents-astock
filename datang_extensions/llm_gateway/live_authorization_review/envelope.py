"""Authorization draft and state helpers for R2C-D."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from datang_extensions.llm_gateway.live_authorization_review.contracts import (
    FALSE_EXECUTION_FIELDS,
    MAX_COST_USD,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MAX_TOTAL_TOKENS,
    MAX_WINDOW_SECONDS,
    STABLE_BASELINE,
    SUPPORTED_VERSION,
    decimal_value,
    hash_value,
    parse_utc,
    require_false,
    require_safe_id,
    review_error,
    scan_forbidden_surface,
)

DRAFT_BINDING_FIELDS = ("provider_id", "model_id", "adapter_id", "binding_id", "case_id", "prompt_spec_hash", "input_artifact_hash")


def _authorization_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "authorization_mode": payload.get("authorization_mode"),
        "stable_baseline": payload.get("stable_baseline"),
        "readiness_package_hash": payload.get("readiness_package_hash"),
        "review_package_hash": payload.get("review_package_hash"),
        "change_freeze_hash": payload.get("change_freeze_hash"),
        "provider_id": payload.get("provider_id"),
        "model_id": payload.get("model_id"),
        "adapter_id": payload.get("adapter_id"),
        "binding_id": payload.get("binding_id"),
        "case_id": payload.get("case_id"),
        "prompt_spec_hash": payload.get("prompt_spec_hash"),
        "input_artifact_hash": payload.get("input_artifact_hash"),
        "budget": payload.get("budget"),
        "proposed_window_start": payload.get("proposed_window_start"),
        "proposed_window_end": payload.get("proposed_window_end"),
        "max_calls": payload.get("max_calls"),
    }


def derive_authorization_id(payload: Mapping[str, Any]) -> str:
    return hash_value({"authorization_identity": _authorization_identity(payload), "bearer_token": False})


def _validate_budget(payload: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    budget = payload.get("budget")
    if not isinstance(budget, Mapping):
        errors.append(review_error("authorization_budget_exceeded", "budget must be an object", field_path="budget"))
        return
    max_cost = decimal_value(budget.get("max_cost_usd"))
    if budget.get("max_input_tokens") != MAX_INPUT_TOKENS:
        errors.append(review_error("authorization_budget_exceeded", "max_input_tokens exceeds review ceiling", field_path="budget.max_input_tokens"))
    if budget.get("max_output_tokens") != MAX_OUTPUT_TOKENS:
        errors.append(review_error("authorization_budget_exceeded", "max_output_tokens exceeds review ceiling", field_path="budget.max_output_tokens"))
    if budget.get("max_total_tokens") != MAX_TOTAL_TOKENS:
        errors.append(review_error("authorization_budget_exceeded", "max_total_tokens exceeds review ceiling", field_path="budget.max_total_tokens"))
    if max_cost is None or max_cost <= 0 or max_cost > MAX_COST_USD:
        errors.append(review_error("authorization_budget_exceeded", "max_cost_usd exceeds review ceiling", field_path="budget.max_cost_usd"))


def _validate_window(payload: Mapping[str, Any], fixed_now: str, errors: list[dict[str, str]]) -> None:
    try:
        start = parse_utc(payload.get("proposed_window_start"))
        end = parse_utc(payload.get("proposed_window_end"))
        now = parse_utc(fixed_now)
    except ValueError:
        errors.append(review_error("authorization_window_invalid", "window timestamps must be UTC Z", field_path="proposed_window"))
        return
    if end <= start or end - start > timedelta(seconds=MAX_WINDOW_SECONDS):
        errors.append(review_error("authorization_window_invalid", "window must be positive and bounded", field_path="proposed_window_end"))
    if end <= now:
        errors.append(review_error("authorization_window_invalid", "window must not be expired", field_path="proposed_window_end"))


def validate_authorization_draft(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    readiness_package_hash: str,
    review_package_hash: str,
    change_freeze_hash: str,
    fixed_now: str,
) -> tuple[str, list[dict[str, str]], str]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, prefix="authorization_draft")
    if forbidden:
        errors.append(forbidden)
        return hash_value(payload), errors, ""
    if payload.get("live_authorization_contract_version") not in SUPPORTED_VERSION:
        errors.append(review_error("authorization_draft_invalid", "unsupported authorization draft version", field_path="live_authorization_contract_version"))
    if payload.get("authorization_state") != "review_ready":
        errors.append(review_error("live_authorization_issuance_not_available", "R2C-D cannot issue live authorization", field_path="authorization_state"))
    if payload.get("authorization_mode") != "single_sandbox_call":
        errors.append(review_error("authorization_draft_mode_invalid", "authorization mode must be single_sandbox_call", field_path="authorization_mode"))
    if payload.get("stable_baseline") != STABLE_BASELINE:
        errors.append(review_error("authorization_scope_mismatch", "stable baseline mismatch", field_path="stable_baseline"))
    if payload.get("readiness_package_hash") != readiness_package_hash:
        errors.append(review_error("authorization_scope_mismatch", "readiness package hash mismatch", field_path="readiness_package_hash"))
    if payload.get("review_package_hash") != review_package_hash:
        errors.append(review_error("authorization_scope_mismatch", "review package hash mismatch", field_path="review_package_hash"))
    if payload.get("change_freeze_hash") != change_freeze_hash:
        errors.append(review_error("authorization_scope_mismatch", "change freeze hash mismatch", field_path="change_freeze_hash"))
    for field in ("provider_id", "model_id", "adapter_id", "binding_id", "case_id"):
        require_safe_id(payload.get(field), errors, "authorization_scope_mismatch", field)
    for field in DRAFT_BINDING_FIELDS:
        if payload.get(field) != manifest.get(field):
            errors.append(review_error("authorization_scope_mismatch", f"{field} mismatch", field_path=field))
    if payload.get("max_calls") != 1:
        errors.append(review_error("authorization_budget_exceeded", "max_calls must be 1", field_path="max_calls"))
    if payload.get("consumed_calls") != 0:
        errors.append(review_error("authorization_replay_not_allowed", "draft must not be consumed", field_path="consumed_calls"))
    _validate_budget(payload, errors)
    _validate_window(payload, fixed_now, errors)
    for field in ("manual_issue_required", "real_identity_verification_required", "detached_signature_required", "execution_nonce_required"):
        if payload.get(field) is not True:
            errors.append(review_error("authorization_draft_invalid", f"{field} must be true", field_path=field))
    if payload.get("execution_nonce_present") is not False:
        errors.append(review_error("execution_nonce_not_available", "execution nonce is not generated in R2C-D", field_path="execution_nonce_present"))
    if payload.get("reviewer_identity_verified") is not False:
        errors.append(review_error("real_identity_verification_unavailable", "real identity is not verified in R2C-D", field_path="reviewer_identity_verified"))
    if payload.get("detached_signature_verified") is not False:
        errors.append(review_error("detached_signature_verification_unavailable", "detached signature is not verified in R2C-D", field_path="detached_signature_verified"))
    if payload.get("live_authorization_issued") is not False:
        errors.append(review_error("live_authorization_issuance_not_available", "live authorization is not issued in R2C-D", field_path="live_authorization_issued"))
    require_false(payload, FALSE_EXECUTION_FIELDS, errors)
    derived_id = derive_authorization_id(payload)
    auth_id = str(payload.get("authorization_id", ""))
    if auth_id != derived_id or "bearer" in auth_id.lower() or not auth_id:
        errors.append(review_error("authorization_id_invalid", "authorization id must be stable derived id and not a bearer token", field_path="authorization_id"))
    return hash_value(payload), errors, derived_id


def transition_authorization_state(current_state: str, requested_state: str) -> dict[str, Any]:
    if current_state == "draft" and requested_state == "review_ready":
        return {"passed": True, "authorization_state": "review_ready", "errors": []}
    if requested_state == "issued":
        error = review_error("live_authorization_issuance_not_available", "live issuance is unavailable in R2C-D", field_path="authorization_state")
    elif current_state == "issued" and requested_state == "consumed":
        error = review_error("live_execution_not_authorized", "live execution is not authorized in R2C-D", field_path="authorization_state")
    else:
        error = review_error("authorization_state_transition_rejected", "state transition is not available", field_path="authorization_state")
    return {"passed": False, "authorization_state": current_state, "errors": [error]}


def attempt_issue_live_authorization(draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "passed": False,
        "authorization_state": draft.get("authorization_state", ""),
        "live_authorization_issued": False,
        "errors": [review_error("live_authorization_issuance_not_available", "manual live issuance is outside R2C-D", field_path="authorization_state")],
    }


def consume_live_authorization_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "passed": False,
        "authorization_state": draft.get("authorization_state", ""),
        "consumed_calls": draft.get("consumed_calls", 0),
        "live_execution_authorized": False,
        "errors": [review_error("live_execution_not_authorized", "R2C-D drafts cannot be consumed", field_path="authorization_state")],
    }


def mark_draft_superseded_if_mismatch(original: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    original_identity = _authorization_identity(original)
    candidate_identity = _authorization_identity(candidate)
    if original_identity == candidate_identity:
        return {"passed": True, "authorization_state": candidate.get("authorization_state", "review_ready"), "errors": []}
    return {
        "passed": False,
        "authorization_state": "superseded",
        "errors": [review_error("authorization_draft_superseded", "changed authorization identity supersedes draft", field_path="authorization_identity")],
    }
