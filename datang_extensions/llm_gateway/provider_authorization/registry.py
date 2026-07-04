"""Opaque secret binding registry validation for R2C-B."""

from __future__ import annotations

from typing import Any, Mapping

from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock, parse_utc_datetime
from datang_extensions.llm_gateway.provider_authorization.contracts import (
    ALLOWED_BINDING_STATES,
    ALLOWED_ENVIRONMENT,
    BINDING_REGISTRY_VERSION,
    GRANT_MODE,
    TERMINAL_BINDING_STATES,
    AuthorizationContractError,
    auth_error,
    hash_value,
    is_explicit_safe_id,
    safe_string_list,
    scan_secret_or_trading_fields,
)

VALID_TRANSITIONS = {
    "registered": {"active", "suspended", "revoked", "expired"},
    "active": {"suspended", "revoked", "expired"},
    "suspended": {"active", "revoked", "expired"},
    "revoked": set(),
    "expired": set(),
}


def _validate_binding(item: Mapping[str, Any], index: int) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_secret_or_trading_fields(item)
    if secret_error:
        errors.append(secret_error)
        return errors
    for field in ("binding_id", "binding_version", "provider_id", "adapter_id", "adapter_version", "secret_kind"):
        if not is_explicit_safe_id(item.get(field)):
            errors.append(auth_error("invalid_binding_registry", f"{field} must be an opaque safe id", field_path=f"bindings[{index}].{field}"))
    if item.get("environment") != ALLOWED_ENVIRONMENT:
        errors.append(auth_error("invalid_binding_registry", "binding environment must be sandbox", field_path=f"bindings[{index}].environment"))
    if item.get("resolution_mode") != "unavailable":
        errors.append(auth_error("secret_resolution_not_available", "secret resolver is unavailable in R2C-B", field_path=f"bindings[{index}].resolution_mode"))
    if item.get("material_present") is not False:
        errors.append(auth_error("secret_material_field_detected", "binding must not contain secret material", field_path="redacted_secret_material"))
    if item.get("max_calls_per_grant") != 1:
        errors.append(auth_error("invalid_binding_registry", "binding grants are single-call only", field_path=f"bindings[{index}].max_calls_per_grant"))
    if item.get("state") not in ALLOWED_BINDING_STATES:
        errors.append(auth_error("invalid_binding_registry", "binding state is unsupported", field_path=f"bindings[{index}].state"))
    for field in ("model_ids", "allowed_purposes", "allowed_task_types"):
        if safe_string_list(item.get(field)) is None:
            errors.append(auth_error("invalid_binding_registry", f"{field} must be an explicit allowlist", field_path=f"bindings[{index}].{field}"))
    try:
        valid_from = parse_utc_datetime(str(item.get("valid_from", "")))
        valid_until = parse_utc_datetime(str(item.get("valid_until", "")))
    except ValueError:
        errors.append(auth_error("invalid_binding_registry", "binding validity window must use fixed UTC timestamps", field_path=f"bindings[{index}].validity"))
    else:
        if valid_from >= valid_until:
            errors.append(auth_error("invalid_binding_registry", "binding valid_from must be before valid_until", field_path=f"bindings[{index}].validity"))
    return errors


def load_binding_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AuthorizationContractError([auth_error("invalid_binding_registry", "binding registry must be an object")])
    errors: list[dict[str, str]] = []
    if payload.get("binding_registry_version") != BINDING_REGISTRY_VERSION:
        errors.append(auth_error("unsupported_binding_registry_version", "unsupported binding registry version", field_path="binding_registry_version"))
    if not is_explicit_safe_id(payload.get("registry_id")):
        errors.append(auth_error("invalid_binding_registry", "registry_id must be a safe id", field_path="registry_id"))
    bindings = payload.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append(auth_error("invalid_binding_registry", "bindings must be a non-empty list", field_path="bindings"))
        raise AuthorizationContractError(errors)
    seen: set[str] = set()
    bindings_by_id: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(bindings):
        if not isinstance(item, Mapping):
            errors.append(auth_error("invalid_binding_registry", "binding must be an object", field_path=f"bindings[{index}]"))
            continue
        errors.extend(_validate_binding(item, index))
        binding_id = str(item.get("binding_id", ""))
        if binding_id in seen:
            errors.append(auth_error("duplicate_binding_id", "binding IDs must be unique", field_path=f"bindings[{index}].binding_id"))
        seen.add(binding_id)
        bindings_by_id[binding_id] = item
    if errors:
        raise AuthorizationContractError(errors)
    return {
        "registry_id": str(payload["registry_id"]),
        "binding_registry_version": BINDING_REGISTRY_VERSION,
        "bindings_by_id": dict(bindings_by_id),
        "registry_hash": hash_value(payload),
    }


def binding_state_error(binding: Mapping[str, Any], clock: FixedAuthorizationClock) -> dict[str, str] | None:
    state = str(binding.get("state", ""))
    if state == "registered":
        return auth_error("binding_not_active", "binding is registered but not active", field_path="binding.state")
    if state == "suspended":
        return auth_error("binding_suspended", "binding is suspended", field_path="binding.state")
    if state == "revoked":
        return auth_error("binding_revoked", "binding is revoked", field_path="binding.state")
    if state == "expired":
        return auth_error("binding_expired", "binding is expired", field_path="binding.state")
    now = clock.now()
    valid_from = parse_utc_datetime(str(binding["valid_from"]))
    valid_until = parse_utc_datetime(str(binding["valid_until"]))
    if now < valid_from:
        return auth_error("binding_not_active", "binding validity window has not started", field_path="binding.valid_from")
    if now > valid_until:
        return auth_error("binding_expired", "binding validity window has expired", field_path="binding.valid_until")
    return None


def transition_binding_state(
    binding: Mapping[str, Any],
    *,
    new_state: str,
    transition_id: str,
    reason_code: str,
    event_time: str,
    clock: FixedAuthorizationClock,
) -> dict[str, Any]:
    previous_state = str(binding.get("state", ""))
    if previous_state in TERMINAL_BINDING_STATES or new_state not in VALID_TRANSITIONS.get(previous_state, set()):
        raise ValueError("invalid_binding_transition")
    if not is_explicit_safe_id(transition_id) or not is_explicit_safe_id(reason_code):
        raise ValueError("invalid_binding_transition")
    parse_utc_datetime(event_time)
    transition = {
        "transition_version": "1.0",
        "transition_id": transition_id,
        "binding_id": str(binding.get("binding_id", "")),
        "previous_state": previous_state,
        "new_state": new_state,
        "reason_code": reason_code,
        "event_time": event_time,
        "observed_at": clock.now_iso(),
        "grant_mode": GRANT_MODE,
    }
    transition["transition_hash"] = hash_value(transition)
    return transition
