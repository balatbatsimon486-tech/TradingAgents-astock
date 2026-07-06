"""Offline R2C-G architecture review evidence sealing gate."""

from __future__ import annotations
import copy
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.audit import build_audit
from datang_extensions.llm_gateway.architecture_review.charter import validate_review_charter
from datang_extensions.llm_gateway.architecture_review.contracts import ArchitectureReviewError, REQUIRED_REAL_WORLD_ACTIONS, base_result, hash_value, require_json_object, review_error
from datang_extensions.llm_gateway.architecture_review.decision_record import validate_decision_record_draft
from datang_extensions.llm_gateway.architecture_review.dissent import validate_dissent_records
from datang_extensions.llm_gateway.architecture_review.evidence import validate_prerequisite_evidence
from datang_extensions.llm_gateway.architecture_review.findings import validate_findings
from datang_extensions.llm_gateway.architecture_review.remediation import validate_remediation_plan
from datang_extensions.llm_gateway.architecture_review.reviews import validate_review_records
from datang_extensions.llm_gateway.architecture_review.risk_acceptance import validate_risk_acceptance_requests
from datang_extensions.llm_gateway.architecture_review.supersede import validate_supersede_policy
from datang_extensions.llm_gateway.architecture_review.waivers import validate_waiver_requests


def _dedupe_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for error in errors:
        item = {"code": str(error.get("code", "")), "message": str(error.get("message", "")), "field_path": str(error.get("field_path", ""))}
        key = (item["code"], item["message"], item["field_path"])
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def _ensure_payloads(values: tuple[Any, ...]) -> tuple[dict[str, Any], ...]:
    names = (
        "r2c_f_architecture_result",
        "review_charter",
        "review_records",
        "findings",
        "dissent_records",
        "remediation_plan",
        "risk_acceptance_requests",
        "waiver_requests",
        "decision_record_draft",
        "supersede_policy",
        "prerequisite_evidence",
    )
    return tuple(require_json_object(value, field_path=name) for value, name in zip(values, names))


def _package_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": result.get("stage"),
        "architecture_review_contract_version": result.get("architecture_review_contract_version"),
        "decision_ceiling": "ready_for_architecture_signoff",
        "r2c_f_architecture_package_hash": result.get("r2c_f_architecture_package_hash"),
        "review_charter_hash": result.get("review_charter_hash"),
        "review_record_set_hash": result.get("review_record_set_hash"),
        "findings_set_hash": result.get("findings_set_hash"),
        "dissent_set_hash": result.get("dissent_set_hash"),
        "remediation_plan_hash": result.get("remediation_plan_hash"),
        "risk_acceptance_request_set_hash": result.get("risk_acceptance_request_set_hash"),
        "waiver_request_set_hash": result.get("waiver_request_set_hash"),
        "decision_record_draft_hash": result.get("decision_record_draft_hash"),
        "supersede_policy_hash": result.get("supersede_policy_hash"),
        "evidence_bundle_hash": result.get("evidence_bundle_hash"),
        "required_real_world_actions_hash": result.get("required_real_world_actions_hash"),
        "approved": False,
        "live_authorized": False,
    }


def run_offline_architecture_review(
    r2c_f_architecture_result: Mapping[str, Any],
    review_charter: Mapping[str, Any],
    review_records: Mapping[str, Any],
    findings: Mapping[str, Any],
    dissent_records: Mapping[str, Any],
    remediation_plan: Mapping[str, Any],
    risk_acceptance_requests: Mapping[str, Any],
    waiver_requests: Mapping[str, Any],
    decision_record_draft: Mapping[str, Any],
    supersede_policy: Mapping[str, Any],
    prerequisite_evidence: Mapping[str, Any],
    *,
    fixed_now: str,
) -> dict[str, Any]:
    architecture, charter, records, finding_payload, dissent_payload, remediation_payload, risk_payload, waiver_payload, decision_payload, supersede_payload, evidence_payload = _ensure_payloads(
        (
            r2c_f_architecture_result,
            review_charter,
            review_records,
            findings,
            dissent_records,
            remediation_plan,
            risk_acceptance_requests,
            waiver_requests,
            decision_record_draft,
            supersede_policy,
            prerequisite_evidence,
        )
    )
    errors: list[dict[str, str]] = []
    evidence_hash, evidence_errors, evidence_summary = validate_prerequisite_evidence(architecture, evidence_payload)
    errors.extend(evidence_errors)
    charter_hash, charter_errors, canonical_charter, required_roles = validate_review_charter(charter)
    errors.extend(charter_errors)
    record_hash, record_errors, covered_roles, record_summaries, request_changes_present = validate_review_records(records, canonical_charter, required_roles, fixed_now=fixed_now)
    errors.extend(record_errors)
    findings_hash, finding_errors, canonical_findings, findings_by_id, severity_distribution, remediation_required = validate_findings(finding_payload)
    errors.extend(finding_errors)
    remediation_hash, remediation_errors, canonical_remediation, remediation_ids = validate_remediation_plan(remediation_payload, findings_by_id, remediation_required, request_changes_present=request_changes_present)
    errors.extend(remediation_errors)
    dissent_hash, dissent_errors, canonical_dissent = validate_dissent_records(dissent_payload, required_roles, remediation_ids)
    errors.extend(dissent_errors)
    risk_hash, risk_errors, canonical_risk = validate_risk_acceptance_requests(risk_payload, findings_by_id, fixed_now=fixed_now)
    errors.extend(risk_errors)
    waiver_hash, waiver_errors, canonical_waivers = validate_waiver_requests(waiver_payload, fixed_now=fixed_now)
    errors.extend(waiver_errors)
    decision_hash, decision_errors, canonical_decision = validate_decision_record_draft(decision_payload)
    errors.extend(decision_errors)
    supersede_hash, supersede_errors, canonical_supersede = validate_supersede_policy(supersede_payload, fixed_now=fixed_now)
    errors.extend(supersede_errors)
    if not REQUIRED_REAL_WORLD_ACTIONS:
        errors.append(review_error("required_real_world_actions_missing", "required real-world actions are required", field_path="required_real_world_actions"))
    errors = _dedupe_errors(errors)
    result = base_result(errors)
    result.update(
        {
            "r2c_f_architecture_package_hash": architecture.get("architecture_package_hash", ""),
            "review_charter_hash": charter_hash,
            "review_record_set_hash": record_hash,
            "findings_set_hash": findings_hash,
            "dissent_set_hash": dissent_hash,
            "remediation_plan_hash": remediation_hash,
            "risk_acceptance_request_set_hash": risk_hash,
            "waiver_request_set_hash": waiver_hash,
            "decision_record_draft_hash": decision_hash,
            "supersede_policy_hash": supersede_hash,
            "evidence_bundle_hash": evidence_hash,
            "blocking_findings_hash": hash_value(errors),
            "required_real_world_actions_hash": hash_value(REQUIRED_REAL_WORLD_ACTIONS),
            "review_charter": canonical_charter,
            "required_reviewer_roles": sorted(required_roles),
            "covered_reviewer_roles": sorted(covered_roles),
            "review_record_summary": record_summaries,
            "findings_catalog": canonical_findings,
            "severity_distribution": severity_distribution,
            "dissent_records": canonical_dissent,
            "remediation_items": canonical_remediation,
            "risk_acceptance_requests": canonical_risk,
            "waiver_requests": canonical_waivers,
            "decision_record_draft": canonical_decision,
            "proposed_decision": canonical_decision.get("proposed_decision", ""),
            "approved_decision": None,
            "supersede_policy": canonical_supersede,
            "prerequisite_evidence_summary": evidence_summary,
        }
    )
    result["architecture_review_package_hash"] = hash_value(_package_payload(result))
    audit = build_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    result["errors"] = errors
    result["blocking_findings"] = errors
    if errors:
        result.update({"passed": False, "decision": "blocked", "architecture_review_evidence_sealed": False, "review_role_coverage_complete": False, "review_findings_catalog_ready": False, "remediation_plan_ready": False, "architecture_decision_record_ready": False, "supersede_policy_ready": False, "ready_for_architecture_signoff": False})
    return result


def build_expected_architecture_review_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(result))


def schema_error_result(exc: Exception) -> dict[str, Any]:
    errors = getattr(exc, "errors", None)
    if not errors:
        errors = [review_error("architecture_review_error", type(exc).__name__, field_path="input")]
    result = base_result(list(errors))
    audit = build_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result

__all__ = ["ArchitectureReviewError", "build_expected_architecture_review_result", "run_offline_architecture_review", "schema_error_result"]
