"""Audit record helpers for R2C-B offline authorization."""

from __future__ import annotations

from typing import Any, Mapping

from datang_extensions.llm_gateway.provider_authorization.contracts import AUTHORIZATION_STAGE, external_calls_false, hash_value


def build_authorization_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = {
        "audit_schema_version": "1.0",
        "stage": AUTHORIZATION_STAGE,
        "authorization_request_id": payload.get("authorization_request_id", ""),
        "binding_id": payload.get("binding_id", ""),
        "policy_id": payload.get("policy_id", ""),
        "provider_id": payload.get("provider_id", ""),
        "model_id": payload.get("model_id", ""),
        "adapter_id": payload.get("adapter_id", ""),
        "decision": payload.get("decision", "deny"),
        "preflight_authorized": payload.get("preflight_authorized", False),
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "approval_quorum_required": payload.get("approval_quorum_required", 0),
        "approval_quorum_satisfied": payload.get("approval_quorum_satisfied", 0),
        "required_roles_satisfied": list(payload.get("required_roles_satisfied", [])),
        "external_calls": external_calls_false(),
        "errors": list(payload.get("errors", [])),
    }
    audit["audit_hash"] = hash_value({key: value for key, value in audit.items() if key != "audit_hash"})
    return audit
