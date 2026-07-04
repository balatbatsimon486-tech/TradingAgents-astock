"""Authorization policy validation for R2C-B."""

from __future__ import annotations

from typing import Any, Mapping

from datang_extensions.llm_gateway.provider_authorization.contracts import (
    ALLOWED_ENVIRONMENT,
    AUTHORIZATION_POLICY_VERSION,
    GRANT_MODE,
    REQUIRED_FALSE_CAPABILITIES,
    AuthorizationContractError,
    auth_error,
    decimal_value,
    hash_value,
    is_explicit_safe_id,
    safe_string_list,
)


def load_authorization_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AuthorizationContractError([auth_error("invalid_authorization_policy", "authorization policy must be an object")])
    errors: list[dict[str, str]] = []
    if payload.get("authorization_policy_version") != AUTHORIZATION_POLICY_VERSION:
        errors.append(auth_error("unsupported_authorization_policy_version", "unsupported authorization policy version", field_path="authorization_policy_version"))
    if not is_explicit_safe_id(payload.get("policy_id")) or not is_explicit_safe_id(payload.get("policy_version")):
        errors.append(auth_error("invalid_authorization_policy", "policy id and version must be safe", field_path="policy_id"))
    if payload.get("status") != "approved":
        errors.append(auth_error("authorization_policy_not_approved", "policy must be approved", field_path="status"))
    if payload.get("grant_mode") != GRANT_MODE:
        errors.append(auth_error("unsupported_grant_mode", "only offline_preflight grants are supported", field_path="grant_mode"))
    if payload.get("allowed_environment") != ALLOWED_ENVIRONMENT:
        errors.append(auth_error("invalid_authorization_policy", "allowed_environment must be sandbox", field_path="allowed_environment"))
    if payload.get("requester_may_approve") is not False:
        errors.append(auth_error("invalid_authorization_policy", "requester may not approve own request", field_path="requester_may_approve"))
    for field in ("allow_network_execution", "allow_tools", "allow_streaming", "allow_trading_actions"):
        if payload.get(field) is not False:
            errors.append(auth_error("authorization_capability_not_allowed", f"{field} must be false", field_path=field))
    quorum = payload.get("required_approval_quorum")
    if not isinstance(quorum, int) or quorum < 2:
        errors.append(auth_error("invalid_authorization_policy", "approval quorum must be at least 2", field_path="required_approval_quorum"))
    roles = safe_string_list(payload.get("required_approval_roles"))
    if roles is None or len(set(roles)) != len(roles):
        errors.append(auth_error("invalid_authorization_policy", "required approval roles must be explicit and unique", field_path="required_approval_roles"))
    for field in ("allowed_purposes", "allowed_task_types"):
        if safe_string_list(payload.get(field)) is None:
            errors.append(auth_error("invalid_authorization_policy", f"{field} must be an explicit allowlist", field_path=field))
    lifetime = payload.get("max_grant_lifetime_seconds")
    if not isinstance(lifetime, int) or not 1 <= lifetime <= 3600:
        errors.append(auth_error("invalid_authorization_policy", "grant lifetime must be bounded", field_path="max_grant_lifetime_seconds"))
    if payload.get("max_calls") != 1:
        errors.append(auth_error("invalid_authorization_policy", "offline preflight grants are single-call only", field_path="max_calls"))
    for field in ("max_input_tokens", "max_output_tokens", "max_total_tokens"):
        value = payload.get(field)
        if not isinstance(value, int) or value <= 0:
            errors.append(auth_error("invalid_authorization_policy", f"{field} must be a positive integer", field_path=field))
    cost = decimal_value(payload.get("max_cost_usd"))
    if cost is None or cost <= 0:
        errors.append(auth_error("invalid_authorization_policy", "max_cost_usd must be positive", field_path="max_cost_usd"))
    if errors:
        raise AuthorizationContractError(errors)
    return {
        "policy_id": str(payload["policy_id"]),
        "policy_version": str(payload["policy_version"]),
        "grant_mode": GRANT_MODE,
        "required_approval_roles": list(payload["required_approval_roles"]),
        "required_approval_quorum": int(payload["required_approval_quorum"]),
        "allowed_environment": ALLOWED_ENVIRONMENT,
        "allowed_purposes": list(payload["allowed_purposes"]),
        "allowed_task_types": list(payload["allowed_task_types"]),
        "max_grant_lifetime_seconds": int(payload["max_grant_lifetime_seconds"]),
        "max_calls": 1,
        "max_input_tokens": int(payload["max_input_tokens"]),
        "max_output_tokens": int(payload["max_output_tokens"]),
        "max_total_tokens": int(payload["max_total_tokens"]),
        "max_cost_usd": str(payload["max_cost_usd"]),
        "policy_hash": hash_value(payload),
        "capabilities": {field: False for field in REQUIRED_FALSE_CAPABILITIES},
    }
