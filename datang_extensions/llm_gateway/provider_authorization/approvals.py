"""Approval-set validation for R2C-B offline authorization."""

from __future__ import annotations

from typing import Any, Mapping

from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock, parse_utc_datetime
from datang_extensions.llm_gateway.provider_authorization.contracts import APPROVAL_SET_VERSION, auth_error, hash_value, is_explicit_safe_id


def validate_approvals(payload: Mapping[str, Any], *, context: Mapping[str, Any], clock: FixedAuthorizationClock) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(payload, Mapping):
        payload = {}
        errors.append(auth_error("approval_invalid", "approval set must be an object"))
    if payload.get("approval_set_version") != APPROVAL_SET_VERSION:
        errors.append(auth_error("approval_invalid", "unsupported approval set version", field_path="approval_set_version"))
    approvals = payload.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
        errors.append(auth_error("approval_invalid", "approvals must be a list", field_path="approvals"))

    requester_id = str(context.get("requester_id", ""))
    request_id = str(context.get("authorization_request_id", ""))
    required_roles = [str(role) for role in context.get("required_roles", [])]
    quorum = int(context.get("quorum", 0))
    seen_approvers: set[str] = set()
    satisfied_roles: set[str] = set()
    approving_records: list[dict[str, Any]] = []

    for index, approval in enumerate(approvals):
        if not isinstance(approval, Mapping):
            errors.append(auth_error("approval_invalid", "approval must be an object", field_path=f"approvals[{index}]"))
            continue
        for field in ("approval_id", "approver_id", "approver_role", "reason_code"):
            if not is_explicit_safe_id(approval.get(field)):
                errors.append(auth_error("approval_invalid", f"{field} must be a safe id", field_path=f"approvals[{index}].{field}"))
        approver_id = str(approval.get("approver_id", ""))
        role = str(approval.get("approver_role", ""))
        if approval.get("authorization_request_id") != request_id:
            errors.append(auth_error("approval_invalid", "approval request id does not match", field_path=f"approvals[{index}].authorization_request_id"))
        if approver_id == requester_id:
            errors.append(auth_error("requester_cannot_approve", "requester cannot approve own authorization", field_path=f"approvals[{index}].approver_id"))
        if approver_id in seen_approvers:
            errors.append(auth_error("duplicate_approver", "approvers must be unique", field_path=f"approvals[{index}].approver_id"))
        seen_approvers.add(approver_id)
        decision = approval.get("decision")
        if decision not in {"approve", "reject"}:
            errors.append(auth_error("approval_invalid", "approval decision must be approve or reject", field_path=f"approvals[{index}].decision"))
        if decision == "reject":
            errors.append(auth_error("approval_rejected", "an approval record rejected the authorization", field_path=f"approvals[{index}].decision"))
        if approval.get("revoked") is not False:
            errors.append(auth_error("approval_revoked", "approval was revoked", field_path=f"approvals[{index}].revoked"))
        try:
            decision_time = parse_utc_datetime(str(approval.get("decision_time", "")))
            valid_until = parse_utc_datetime(str(approval.get("valid_until", "")))
        except ValueError:
            errors.append(auth_error("approval_invalid", "approval timestamps must be fixed UTC", field_path=f"approvals[{index}].time"))
            continue
        if decision_time > clock.now():
            errors.append(auth_error("approval_invalid", "approval decision time cannot be in the future", field_path=f"approvals[{index}].decision_time"))
        if clock.now() > valid_until:
            errors.append(auth_error("approval_expired", "approval expired", field_path=f"approvals[{index}].valid_until"))
        if decision == "approve" and approval.get("revoked") is False and clock.now() <= valid_until:
            approving_records.append(
                {
                    "approval_id": str(approval.get("approval_id", "")),
                    "approver_id": approver_id,
                    "approver_role": role,
                    "authorization_request_id": request_id,
                    "decision": "approve",
                    "decision_time": str(approval.get("decision_time", "")),
                    "valid_until": str(approval.get("valid_until", "")),
                }
            )
            if role in required_roles:
                satisfied_roles.add(role)

    if len(approving_records) < quorum:
        errors.append(auth_error("approval_quorum_not_met", "approval quorum was not met", field_path="approvals"))
    missing_roles = [role for role in required_roles if role not in satisfied_roles]
    if missing_roles:
        errors.append(auth_error("required_approval_role_missing", "required approval role is missing", field_path="required_approval_roles"))

    canonical_records = sorted(approving_records, key=lambda item: (item["approver_id"], item["approval_id"]))
    return {
        "passed": not errors,
        "errors": errors,
        "approval_set_hash": hash_value({"approval_set_version": APPROVAL_SET_VERSION, "approvals": canonical_records}),
        "approval_quorum_required": quorum,
        "approval_quorum_satisfied": len(approving_records),
        "required_roles_satisfied": [role for role in required_roles if role in satisfied_roles],
    }
