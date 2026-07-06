"""Risk-acceptance request validation for R2C-G."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import SUPPORTED_VERSION, expiry_too_long, hash_value, parse_utc, require_safe_id, review_error, scan_forbidden_surface, sorted_records


def validate_risk_acceptance_requests(payload: Mapping[str, Any], findings_by_id: dict[str, dict[str, Any]], *, fixed_now: str) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_forbidden_surface(payload, field_path="risk_acceptance_requests")
    if forbidden:
        errors.append(forbidden)
    if payload.get("risk_acceptance_request_set_version") not in SUPPORTED_VERSION:
        errors.append(review_error("invalid_risk_acceptance_request", "unsupported risk request set version", field_path="risk_acceptance_request_set_version"))
    records = payload.get("requests") if isinstance(payload.get("requests"), list) else []
    canonical: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(review_error("invalid_risk_acceptance_request", "request must be an object", field_path=f"requests[{index}]"))
            continue
        item = dict(raw)
        request_id = str(item.get("request_id", ""))
        require_safe_id(request_id, errors, "invalid_risk_acceptance_request", f"requests[{index}].request_id")
        if request_id in seen:
            errors.append(review_error("invalid_risk_acceptance_request", "request id must be unique", field_path=f"requests[{index}].request_id"))
        seen.add(request_id)
        finding_id = str(item.get("finding_id", ""))
        finding = findings_by_id.get(finding_id)
        if not finding:
            errors.append(review_error("invalid_risk_acceptance_request", "request references unknown finding", field_path=f"requests[{index}].finding_id"))
        elif finding.get("severity") == "critical":
            errors.append(review_error("critical_risk_acceptance_not_allowed", "critical risk acceptance request is not allowed", field_path=f"requests[{index}].finding_id"))
        if item.get("requested_scope") != "offline_architecture_only":
            errors.append(review_error("invalid_risk_acceptance_request", "risk request scope cannot cover real deployment", field_path=f"requests[{index}].requested_scope"))
        try:
            parse_utc(item.get("requested_expiry"))
        except ValueError:
            errors.append(review_error("invalid_risk_acceptance_request", "risk request expiry is required", field_path=f"requests[{index}].requested_expiry"))
        if expiry_too_long(item.get("requested_expiry"), fixed_now, max_days=366):
            errors.append(review_error("invalid_risk_acceptance_request", "risk request expiry exceeds offline review limit", field_path=f"requests[{index}].requested_expiry"))
        if not item.get("business_justification_code"):
            errors.append(review_error("invalid_risk_acceptance_request", "business justification code is required", field_path=f"requests[{index}].business_justification_code"))
        if not isinstance(item.get("compensating_controls"), list) or not item.get("compensating_controls"):
            errors.append(review_error("invalid_risk_acceptance_request", "compensating controls are required", field_path=f"requests[{index}].compensating_controls"))
        approvers = item.get("approval_required_roles") if isinstance(item.get("approval_required_roles"), list) else []
        if not approvers or item.get("requested_by_role") in approvers:
            errors.append(review_error("invalid_risk_acceptance_request", "requester cannot self-approve", field_path=f"requests[{index}].approval_required_roles"))
        if item.get("approval_state") != "not_approved":
            errors.append(review_error("risk_acceptance_not_approved", "risk acceptance is not approved in R2C-G", field_path=f"requests[{index}].approval_state"))
        if item.get("real_approvers_assigned") is not False:
            errors.append(review_error("invalid_risk_acceptance_request", "real approvers must not be assigned", field_path=f"requests[{index}].real_approvers_assigned"))
        canonical.append(item)
    canonical = sorted_records(canonical, "request_id")
    return hash_value({"risk_acceptance_request_set_version": payload.get("risk_acceptance_request_set_version"), "requests": canonical}), errors, canonical
