"""Waiver-request validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import NON_WAIVABLE_CONTROLS, SUPPORTED_VERSION, expiry_too_long, hash_value, parse_utc, require_safe_id, review_error, scan_forbidden_surface, sorted_records


def validate_waiver_requests(payload: Mapping[str, Any], *, fixed_now: str) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="waiver_requests")
    if forbidden:
        errors.append(forbidden)
    if payload.get("waiver_request_set_version") not in SUPPORTED_VERSION:
        errors.append(review_error("invalid_waiver_request", "unsupported waiver request set version", field_path="waiver_request_set_version"))
    records = payload.get("requests") if isinstance(payload.get("requests"), list) else []
    canonical: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(review_error("invalid_waiver_request", "waiver request must be an object", field_path=f"requests[{index}]"))
            continue
        item = dict(raw)
        waiver_id = str(item.get("waiver_request_id", ""))
        require_safe_id(waiver_id, errors, "invalid_waiver_request", f"requests[{index}].waiver_request_id")
        if waiver_id in seen:
            errors.append(review_error("invalid_waiver_request", "waiver request id must be unique", field_path=f"requests[{index}].waiver_request_id"))
        seen.add(waiver_id)
        control_id = str(item.get("control_id", ""))
        require_safe_id(control_id, errors, "invalid_waiver_request", f"requests[{index}].control_id")
        if control_id in NON_WAIVABLE_CONTROLS:
            errors.append(review_error("non_waivable_control", "control is non-waivable", field_path=f"requests[{index}].control_id"))
        try:
            parse_utc(item.get("requested_expiry"))
        except ValueError:
            errors.append(review_error("invalid_waiver_request", "waiver expiry is required", field_path=f"requests[{index}].requested_expiry"))
        if expiry_too_long(item.get("requested_expiry"), fixed_now, max_days=366):
            errors.append(review_error("invalid_waiver_request", "waiver expiry exceeds offline review limit", field_path=f"requests[{index}].requested_expiry"))
        if not isinstance(item.get("compensating_controls"), list) or not item.get("compensating_controls"):
            errors.append(review_error("invalid_waiver_request", "compensating controls are required", field_path=f"requests[{index}].compensating_controls"))
        approvers = item.get("approval_required_roles") if isinstance(item.get("approval_required_roles"), list) else []
        if not approvers or item.get("requested_by_role") in approvers:
            errors.append(review_error("invalid_waiver_request", "requester cannot self-approve", field_path=f"requests[{index}].approval_required_roles"))
        if item.get("approval_state") != "not_approved":
            errors.append(review_error("waiver_not_approved", "waiver is not approved in R2C-G", field_path=f"requests[{index}].approval_state"))
        if item.get("real_approvers_assigned") is not False:
            errors.append(review_error("invalid_waiver_request", "real approvers must not be assigned", field_path=f"requests[{index}].real_approvers_assigned"))
        canonical.append(item)
    canonical = sorted_records(canonical, "waiver_request_id")
    return hash_value({"waiver_request_set_version": payload.get("waiver_request_set_version"), "requests": canonical}), errors, canonical
