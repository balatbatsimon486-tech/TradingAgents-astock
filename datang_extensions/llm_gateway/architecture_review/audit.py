"""Audit helpers for R2C-G architecture review packages."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from datang_extensions.llm_gateway.architecture_review.contracts import ARCHITECTURE_REVIEW_CONTRACT_VERSION, ARCHITECTURE_REVIEW_STAGE, FALSE_REVIEW_FIELDS, external_calls_all_false, hash_value


def build_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = {
        "audit_schema_version": "1.0",
        "stage": ARCHITECTURE_REVIEW_STAGE,
        "architecture_review_contract_version": ARCHITECTURE_REVIEW_CONTRACT_VERSION,
        "decision": payload.get("decision", "blocked"),
        "architecture_review_evidence_sealed": bool(payload.get("architecture_review_evidence_sealed", False)),
        "ready_for_architecture_signoff": bool(payload.get("ready_for_architecture_signoff", False)),
        "false_fields": {field: False for field in FALSE_REVIEW_FIELDS},
        "external_calls": external_calls_all_false(),
        "error_codes": [str(error.get("code", "")) for error in payload.get("errors", []) if isinstance(error, Mapping)],
        "review_charter_hash": str(payload.get("review_charter_hash", "")),
        "review_record_set_hash": str(payload.get("review_record_set_hash", "")),
        "findings_set_hash": str(payload.get("findings_set_hash", "")),
        "dissent_set_hash": str(payload.get("dissent_set_hash", "")),
        "remediation_plan_hash": str(payload.get("remediation_plan_hash", "")),
        "risk_acceptance_request_set_hash": str(payload.get("risk_acceptance_request_set_hash", "")),
        "waiver_request_set_hash": str(payload.get("waiver_request_set_hash", "")),
        "decision_record_draft_hash": str(payload.get("decision_record_draft_hash", "")),
        "supersede_policy_hash": str(payload.get("supersede_policy_hash", "")),
        "evidence_bundle_hash": str(payload.get("evidence_bundle_hash", "")),
        "architecture_review_package_hash": str(payload.get("architecture_review_package_hash", "")),
        "required_real_world_action_count": len(payload.get("required_real_world_actions", [])) if isinstance(payload.get("required_real_world_actions"), list) else 0,
    }
    audit["audit_hash"] = hash_value(audit)
    return audit
