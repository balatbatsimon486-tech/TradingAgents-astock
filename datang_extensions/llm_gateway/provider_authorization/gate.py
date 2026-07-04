"""R2C-B offline preflight authorization gate."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from datang_extensions.llm_gateway.provider_adapters.contracts import ProviderAdapterContractError, load_provider_adapter_config
from datang_extensions.llm_gateway.provider_authorization.approvals import validate_approvals
from datang_extensions.llm_gateway.provider_authorization.audit import build_authorization_audit
from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock, parse_utc_datetime
from datang_extensions.llm_gateway.provider_authorization.contracts import (
    AUTHORIZATION_CONTRACT_VERSION,
    AUTHORIZATION_STAGE,
    GRANT_MODE,
    REQUIRED_FALSE_CAPABILITIES,
    AuthorizationContractError,
    auth_error,
    decimal_value,
    external_calls_false,
    hash_value,
    is_explicit_safe_id,
    is_sha256,
    reject_transport_surface,
    scan_secret_or_trading_fields,
)
from datang_extensions.llm_gateway.provider_authorization.policy import load_authorization_policy
from datang_extensions.llm_gateway.provider_authorization.registry import binding_state_error, load_binding_registry


def _safe_request_id(request: Mapping[str, Any]) -> str:
    value = request.get("authorization_request_id", "")
    return str(value) if is_explicit_safe_id(value) else ""


def _base_result(request: Mapping[str, Any] | None = None, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    safe_request = request or {}
    result = {
        "stage": AUTHORIZATION_STAGE,
        "authorization_contract_version": AUTHORIZATION_CONTRACT_VERSION,
        "authorization_request_id": _safe_request_id(safe_request),
        "provider_id": str(safe_request.get("provider_id", "")) if is_explicit_safe_id(safe_request.get("provider_id")) else "",
        "model_id": str(safe_request.get("model_id", "")) if is_explicit_safe_id(safe_request.get("model_id")) else "",
        "adapter_id": str(safe_request.get("adapter_id", "")) if is_explicit_safe_id(safe_request.get("adapter_id")) else "",
        "binding_id": str(safe_request.get("binding_id", "")) if is_explicit_safe_id(safe_request.get("binding_id")) else "",
        "policy_id": "",
        "passed": False,
        "decision": "deny",
        "preflight_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "external_calls": external_calls_false(),
        "authorization_request_hash": "",
        "binding_hash": "",
        "policy_hash": "",
        "approval_set_hash": "",
        "decision_hash": "",
        "audit_hash": "",
        "approval_quorum_required": 0,
        "approval_quorum_satisfied": 0,
        "required_roles_satisfied": [],
        "grant": None,
        "audit": {},
        "warnings": [],
        "errors": list(errors or []),
    }
    audit = build_authorization_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def _request_hash(request: Mapping[str, Any]) -> str:
    return hash_value(request)


def _validate_request(request: Mapping[str, Any], *, binding: Mapping[str, Any], policy: Mapping[str, Any], adapter_config: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not isinstance(request, Mapping):
        return [auth_error("authorization_request_invalid", "authorization request must be an object")]
    transport_error = reject_transport_surface(request)
    if transport_error:
        return [transport_error]
    secret_error = scan_secret_or_trading_fields(request)
    if secret_error:
        return [secret_error]
    if request.get("authorization_contract_version") != AUTHORIZATION_CONTRACT_VERSION:
        errors.append(auth_error("unsupported_authorization_contract_version", "unsupported authorization contract version", field_path="authorization_contract_version"))

    for field in ("authorization_request_id", "binding_id", "requester_id", "provider_id", "model_id", "adapter_id", "adapter_version"):
        if not is_explicit_safe_id(request.get(field)):
            errors.append(auth_error("authorization_request_invalid", f"{field} must be a safe id", field_path=field))
    for field in ("case_id", "snapshot_id", "gateway_request_id", "input_artifact_id", "prompt_id", "prompt_version"):
        if not is_explicit_safe_id(request.get(field)):
            errors.append(auth_error("authorization_lineage_invalid", f"{field} must be a safe lineage id", field_path=field))
    for field in ("gateway_request_hash", "input_artifact_hash", "prompt_spec_hash"):
        if not is_sha256(request.get(field)):
            errors.append(auth_error("authorization_lineage_invalid", f"{field} must be a lowercase SHA-256", field_path=field))

    if request.get("binding_id") != binding.get("binding_id"):
        errors.append(auth_error("authorization_identity_mismatch", "request binding_id does not match registry", field_path="binding_id"))
    if request.get("provider_id") != binding.get("provider_id") or request.get("provider_id") != adapter_config.provider_id:
        errors.append(auth_error("authorization_identity_mismatch", "provider identity mismatch", field_path="provider_id"))
    if request.get("model_id") not in binding.get("model_ids", []) or request.get("model_id") != adapter_config.model_id:
        errors.append(auth_error("authorization_identity_mismatch", "model identity mismatch", field_path="model_id"))
    if request.get("adapter_id") != binding.get("adapter_id") or request.get("adapter_id") != adapter_config.adapter_id:
        errors.append(auth_error("authorization_identity_mismatch", "adapter identity mismatch", field_path="adapter_id"))
    if request.get("adapter_version") != binding.get("adapter_version") or request.get("adapter_version") != adapter_config.adapter_version:
        errors.append(auth_error("authorization_identity_mismatch", "adapter version mismatch", field_path="adapter_version"))
    if request.get("environment") != policy.get("allowed_environment") or request.get("environment") != binding.get("environment"):
        errors.append(auth_error("authorization_environment_mismatch", "environment is outside policy or binding scope", field_path="environment"))
    if request.get("purpose") not in policy.get("allowed_purposes", []) or request.get("purpose") not in binding.get("allowed_purposes", []):
        errors.append(auth_error("authorization_purpose_not_allowed", "purpose is outside policy or binding scope", field_path="purpose"))
    if request.get("task_type") not in policy.get("allowed_task_types", []) or request.get("task_type") not in binding.get("allowed_task_types", []):
        errors.append(auth_error("authorization_task_type_not_allowed", "task type is outside policy or binding scope", field_path="task_type"))

    capabilities = request.get("requested_capabilities")
    if not isinstance(capabilities, Mapping):
        errors.append(auth_error("authorization_capability_not_allowed", "requested_capabilities must be an object", field_path="requested_capabilities"))
    else:
        for field in REQUIRED_FALSE_CAPABILITIES:
            if capabilities.get(field) is not False:
                errors.append(auth_error("authorization_capability_not_allowed", f"{field} is not allowed", field_path=f"requested_capabilities.{field}"))

    budget = request.get("requested_budget")
    if not isinstance(budget, Mapping):
        errors.append(auth_error("authorization_budget_exceeded", "requested_budget must be an object", field_path="requested_budget"))
    else:
        max_cost_usd = decimal_value(budget.get("max_cost_usd"))
        if budget.get("max_calls") != 1:
            errors.append(auth_error("authorization_budget_exceeded", "max_calls must be 1", field_path="requested_budget.max_calls"))
        checks = (
            ("max_input_tokens", budget.get("max_input_tokens"), int(policy["max_input_tokens"]), adapter_config.limits.max_input_tokens),
            ("max_output_tokens", budget.get("max_output_tokens"), int(policy["max_output_tokens"]), adapter_config.limits.max_output_tokens),
            ("max_total_tokens", budget.get("max_total_tokens"), int(policy["max_total_tokens"]), adapter_config.limits.max_total_tokens),
        )
        for field, value, policy_limit, adapter_limit in checks:
            if not isinstance(value, int) or value <= 0 or value > policy_limit or value > adapter_limit:
                errors.append(auth_error("authorization_budget_exceeded", f"{field} exceeds policy or adapter limit", field_path=f"requested_budget.{field}"))
        policy_cost = decimal_value(policy["max_cost_usd"])
        if max_cost_usd is None or policy_cost is None or max_cost_usd <= 0 or max_cost_usd > policy_cost or max_cost_usd > adapter_config.limits.max_cost_usd:
            errors.append(auth_error("authorization_budget_exceeded", "max_cost_usd exceeds policy or adapter limit", field_path="requested_budget.max_cost_usd"))
    try:
        parse_utc_datetime(str(request.get("request_time", "")))
    except ValueError:
        errors.append(auth_error("authorization_request_invalid", "request_time must be fixed UTC", field_path="request_time"))
    return errors


def _build_grant(*, request: Mapping[str, Any], request_hash: str, binding_hash: str, policy: Mapping[str, Any], approval_set_hash: str, clock: FixedAuthorizationClock) -> dict[str, Any]:
    grant_core = {
        "grant_schema_version": "1.0",
        "grant_mode": GRANT_MODE,
        "grant_state": "issued",
        "authorization_request_id": request["authorization_request_id"],
        "authorization_request_hash": request_hash,
        "binding_id": request["binding_id"],
        "binding_hash": binding_hash,
        "policy_id": policy["policy_id"],
        "policy_hash": policy["policy_hash"],
        "approval_set_hash": approval_set_hash,
        "provider_id": request["provider_id"],
        "model_id": request["model_id"],
        "adapter_id": request["adapter_id"],
        "issued_at": clock.now_iso(),
        "expires_at": clock.plus_seconds_iso(int(policy["max_grant_lifetime_seconds"])),
        "max_calls": 1,
        "consumed_calls": 0,
        "budget": copy.deepcopy(request["requested_budget"]),
        "live_execution_authorized": False,
        "credential_resolution_authorized": False,
        "provider_transport_authorized": False,
    }
    grant = dict(grant_core)
    grant["grant_id"] = hash_value({"grant_identity": grant_core})
    grant["grant_hash"] = hash_value(grant)
    return grant


def _success_result(*, request: Mapping[str, Any], binding: Mapping[str, Any], policy: Mapping[str, Any], approvals: Mapping[str, Any], clock: FixedAuthorizationClock) -> dict[str, Any]:
    request_hash = _request_hash(request)
    binding_hash = hash_value(binding)
    grant = _build_grant(request=request, request_hash=request_hash, binding_hash=binding_hash, policy=policy, approval_set_hash=str(approvals["approval_set_hash"]), clock=clock)
    decision_record = {
        "authorization_request_hash": request_hash,
        "binding_hash": binding_hash,
        "policy_hash": policy["policy_hash"],
        "approval_set_hash": approvals["approval_set_hash"],
        "decision": "allow",
        "grant_hash": grant["grant_hash"],
        "preflight_authorized": True,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
    }
    result = _base_result(request)
    result.update(
        {
            "policy_id": policy["policy_id"],
            "passed": True,
            "decision": "allow",
            "preflight_authorized": True,
            "authorization_request_hash": request_hash,
            "binding_hash": binding_hash,
            "policy_hash": policy["policy_hash"],
            "approval_set_hash": approvals["approval_set_hash"],
            "decision_hash": hash_value(decision_record),
            "approval_quorum_required": approvals["approval_quorum_required"],
            "approval_quorum_satisfied": approvals["approval_quorum_satisfied"],
            "required_roles_satisfied": approvals["required_roles_satisfied"],
            "grant": grant,
            "errors": [],
        }
    )
    audit = build_authorization_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def _deny_with_context(*, request: Mapping[str, Any], errors: list[dict[str, str]], binding: Mapping[str, Any] | None = None, policy: Mapping[str, Any] | None = None, approval_result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _base_result(request, errors)
    if binding is not None:
        result["binding_hash"] = hash_value(binding)
    if policy is not None:
        result["policy_id"] = str(policy.get("policy_id", ""))
        result["policy_hash"] = str(policy.get("policy_hash", ""))
        result["approval_quorum_required"] = int(policy.get("required_approval_quorum", 0))
    if approval_result is not None:
        result["approval_set_hash"] = str(approval_result.get("approval_set_hash", ""))
        result["approval_quorum_required"] = int(approval_result.get("approval_quorum_required", result["approval_quorum_required"]))
        result["approval_quorum_satisfied"] = int(approval_result.get("approval_quorum_satisfied", 0))
        result["required_roles_satisfied"] = list(approval_result.get("required_roles_satisfied", []))
    if is_explicit_safe_id(request.get("authorization_request_id")) and not any(error.get("code") == "secret_material_field_detected" for error in errors):
        result["authorization_request_hash"] = _request_hash(request)
    audit = build_authorization_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    result["decision_hash"] = hash_value(
        {
            "authorization_request_hash": result["authorization_request_hash"],
            "binding_hash": result["binding_hash"],
            "policy_hash": result["policy_hash"],
            "approval_set_hash": result["approval_set_hash"],
            "decision": "deny",
            "errors": errors,
        }
    )
    return result


def run_offline_authorization(binding_registry: Mapping[str, Any], policy_payload: Mapping[str, Any], authorization_request: Mapping[str, Any], approvals_payload: Mapping[str, Any], *, adapter_config: Mapping[str, Any], clock: FixedAuthorizationClock) -> dict[str, Any]:
    request = dict(authorization_request) if isinstance(authorization_request, Mapping) else {}
    try:
        registry = load_binding_registry(binding_registry)
        policy = load_authorization_policy(policy_payload)
        config = load_provider_adapter_config(adapter_config)
    except (AuthorizationContractError, ProviderAdapterContractError) as exc:
        errors = getattr(exc, "errors", [auth_error("authorization_contract_invalid", type(exc).__name__)])
        return _deny_with_context(request=request, errors=list(errors))

    binding = registry["bindings_by_id"].get(str(request.get("binding_id", "")))
    if binding is None:
        return _deny_with_context(request=request, errors=[auth_error("binding_not_found", "binding id was not found", field_path="binding_id")], policy=policy)

    state_error = binding_state_error(binding, clock)
    if state_error:
        return _deny_with_context(request=request, errors=[state_error], binding=binding, policy=policy)

    request_errors = _validate_request(request, binding=binding, policy=policy, adapter_config=config)
    if request_errors:
        return _deny_with_context(request=request, errors=request_errors, binding=binding, policy=policy)

    approval_context = {
        "authorization_request_id": request["authorization_request_id"],
        "requester_id": request["requester_id"],
        "required_roles": policy["required_approval_roles"],
        "quorum": policy["required_approval_quorum"],
    }
    approval_result = validate_approvals(approvals_payload, context=approval_context, clock=clock)
    if not approval_result["passed"]:
        return _deny_with_context(request=request, errors=list(approval_result["errors"]), binding=binding, policy=policy, approval_result=approval_result)

    return _success_result(request=request, binding=binding, policy=policy, approvals=approval_result, clock=clock)


def build_expected_authorization_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(result))


def consume_offline_preflight_grant(grant: Mapping[str, Any], authorization_request: Mapping[str, Any], *, clock: FixedAuthorizationClock) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    request_hash = _request_hash(authorization_request)
    grant_copy = copy.deepcopy(dict(grant)) if isinstance(grant, Mapping) else {}
    if grant_copy.get("grant_mode") != GRANT_MODE:
        errors.append(auth_error("authorization_grant_invalid", "grant mode is not offline_preflight", field_path="grant_mode"))
    if grant_copy.get("grant_state") == "revoked":
        errors.append(auth_error("authorization_grant_revoked", "grant was revoked", field_path="grant_state"))
    elif grant_copy.get("grant_state") == "consumed" or int(grant_copy.get("consumed_calls", 0)) >= int(grant_copy.get("max_calls", 1)):
        errors.append(auth_error("authorization_grant_already_consumed", "grant has already been consumed", field_path="grant_state"))
    if grant_copy.get("authorization_request_hash") != request_hash:
        errors.append(auth_error("authorization_grant_mismatch", "grant request hash mismatch", field_path="authorization_request_hash"))
    try:
        expires_at = parse_utc_datetime(str(grant_copy.get("expires_at", "")))
    except ValueError:
        errors.append(auth_error("authorization_grant_invalid", "grant expiry is invalid", field_path="expires_at"))
    else:
        if clock.now() > expires_at:
            errors.append(auth_error("authorization_grant_expired", "grant has expired", field_path="expires_at"))
    result = _base_result(authorization_request, errors)
    result["authorization_request_hash"] = request_hash
    result["grant"] = grant_copy
    if errors:
        return result
    grant_copy["grant_state"] = "consumed"
    grant_copy["consumed_calls"] = int(grant_copy.get("consumed_calls", 0)) + 1
    grant_copy["consumed_at"] = clock.now_iso()
    grant_copy["grant_hash"] = hash_value({key: value for key, value in grant_copy.items() if key != "grant_hash"})
    result.update({"passed": True, "decision": "allow", "preflight_authorized": True, "grant": grant_copy, "errors": []})
    audit = build_authorization_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    result["decision_hash"] = hash_value({"decision": "allow", "grant_hash": grant_copy["grant_hash"], "authorization_request_hash": request_hash})
    return result
