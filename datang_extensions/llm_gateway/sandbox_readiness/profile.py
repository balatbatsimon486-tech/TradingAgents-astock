"""Sandbox profile, secret proposal, and run manifest validation for R2C-C."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.contracts import (
    SUPPORTED_VERSION,
    decimal_value,
    hash_value,
    parse_utc,
    readiness_error,
    require_false,
    require_safe_id,
    scan_forbidden_surface,
    string_list,
)


def validate_sandbox_profile(profile: Mapping[str, Any], manifest: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(profile, prefix="sandbox_profile")
    if secret_error:
        errors.append(secret_error)
        return hash_value(profile), errors
    if profile.get("sandbox_profile_contract_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("unsupported_sandbox_profile_version", "unsupported sandbox profile version", field_path="sandbox_profile_contract_version"))
    for field in ("profile_id", "profile_version", "provider_id", "model_id", "adapter_id", "adapter_version", "binding_id", "authorization_policy_id"):
        require_safe_id(profile.get(field), errors, "sandbox_profile_invalid", field)
    if profile.get("status") != "draft_for_review":
        errors.append(readiness_error("sandbox_profile_invalid", "profile must be draft_for_review", field_path="status"))
    if profile.get("environment") != "sandbox":
        errors.append(readiness_error("sandbox_profile_invalid", "environment must be sandbox", field_path="environment"))
    if profile.get("single_case_only") is not True:
        errors.append(readiness_error("sandbox_profile_invalid", "single_case_only must be true", field_path="single_case_only"))
    if profile.get("max_calls") != 1:
        errors.append(readiness_error("sandbox_profile_invalid", "max_calls must be 1", field_path="max_calls"))
    if profile.get("allowed_purpose") != "single_case_research":
        errors.append(readiness_error("sandbox_profile_invalid", "allowed purpose is unsupported", field_path="allowed_purpose"))
    if profile.get("allowed_task_type") != "research_generation":
        errors.append(readiness_error("sandbox_profile_invalid", "allowed task type is unsupported", field_path="allowed_task_type"))
    require_false(
        profile,
        ("tools_enabled", "streaming_enabled", "fallback_enabled", "production_data_allowed", "trading_actions_allowed"),
        "sandbox_profile_capability_not_allowed",
        errors,
    )
    for field in ("provider_id", "model_id"):
        if manifest.get(field) and profile.get(field) != manifest.get(field):
            errors.append(readiness_error("readiness_identity_mismatch", "profile identity does not match run manifest", field_path=field))
    return hash_value(profile), errors


def validate_secret_storage_proposal(proposal: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(proposal, prefix="secret_storage_proposal")
    if secret_error:
        errors.append(secret_error)
        return hash_value(proposal), errors
    if proposal.get("secret_storage_proposal_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("secret_storage_proposal_invalid", "unsupported proposal version", field_path="secret_storage_proposal_version"))
    for field in ("proposal_id", "backend_kind", "credential_binding_id"):
        require_safe_id(proposal.get(field), errors, "secret_storage_proposal_invalid", field)
    if proposal.get("credential_binding_id") != profile.get("binding_id"):
        errors.append(readiness_error("readiness_identity_mismatch", "secret proposal binding does not match profile", field_path="credential_binding_id"))
    if proposal.get("backend_status") != "not_configured":
        errors.append(readiness_error("secret_storage_proposal_invalid", "backend must not be configured", field_path="backend_status"))
    if proposal.get("secret_material_present") is not False:
        errors.append(readiness_error("secret_storage_proposal_invalid", "secret material must be absent", field_path="secret_material_present"))
    if proposal.get("resolver_implemented") is not False:
        errors.append(readiness_error("secret_storage_proposal_invalid", "resolver must not be implemented", field_path="resolver_implemented"))
    for field in ("least_privilege_required", "rotation_required", "audit_access_required"):
        if proposal.get(field) is not True:
            errors.append(readiness_error("secret_storage_proposal_invalid", f"{field} must be true", field_path=field))
    require_false(
        proposal,
        ("plaintext_export_allowed", "environment_variable_fallback_allowed", "local_file_fallback_allowed", "git_storage_allowed"),
        "secret_storage_proposal_invalid",
        errors,
    )
    return hash_value(proposal), errors


def validate_run_manifest(manifest: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(manifest, prefix="run_manifest")
    if secret_error:
        errors.append(secret_error)
        return hash_value(manifest), errors
    if manifest.get("run_manifest_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("run_manifest_invalid", "unsupported run manifest version", field_path="run_manifest_version"))
    for field in ("run_manifest_id", "case_id", "prompt_id", "prompt_version", "provider_id", "model_id"):
        require_safe_id(manifest.get(field), errors, "run_manifest_invalid", field)
    if manifest.get("run_mode") != "proposed_single_call":
        errors.append(readiness_error("run_manifest_invalid", "run mode must be proposed_single_call", field_path="run_mode"))
    if manifest.get("max_calls") != 1:
        errors.append(readiness_error("run_manifest_invalid", "max_calls must be 1", field_path="max_calls"))
    if manifest.get("provider_id") != profile.get("provider_id") or manifest.get("model_id") != profile.get("model_id"):
        errors.append(readiness_error("readiness_identity_mismatch", "run manifest identity does not match profile", field_path="provider_id"))
    for field, limit in (("max_input_tokens", 1024), ("max_output_tokens", 512), ("max_total_tokens", 1536)):
        value = manifest.get(field)
        if not isinstance(value, int) or value <= 0 or value > limit:
            errors.append(readiness_error("run_manifest_budget_exceeded", "run budget exceeds offline readiness limit", field_path=field))
    cost = decimal_value(manifest.get("max_cost_usd"))
    if cost is None or cost <= 0 or cost > decimal_value("0.10"):
        errors.append(readiness_error("run_manifest_budget_exceeded", "cost budget exceeds offline readiness limit", field_path="max_cost_usd"))
    if not isinstance(manifest.get("timeout_ms"), int) or not 1 <= int(manifest.get("timeout_ms", 0)) <= 30000:
        errors.append(readiness_error("run_manifest_budget_exceeded", "timeout exceeds offline readiness limit", field_path="timeout_ms"))
    try:
        start = parse_utc(manifest.get("proposed_window_start"))
        end = parse_utc(manifest.get("proposed_window_end"))
    except ValueError:
        errors.append(readiness_error("run_manifest_schema_error", "window timestamps must be fixed UTC", field_path="proposed_window_start"))
        errors.append(readiness_error("run_manifest_window_invalid", "window timestamps must be fixed UTC", field_path="proposed_window_start"))
    else:
        duration = (end - start).total_seconds()
        if duration <= 0 or duration > 900:
            errors.append(readiness_error("run_manifest_window_invalid", "window duration must be between 1 and 900 seconds", field_path="proposed_window_end"))
    require_false(manifest, ("tools", "streaming", "fallback", "production_data", "trading_actions"), "run_manifest_capability_not_allowed", errors)
    if string_list(manifest.get("manual_review_requirements")) is None:
        errors.append(readiness_error("manual_review_required", "manual review requirements must be explicit", field_path="manual_review_requirements"))
    return hash_value(manifest), errors
