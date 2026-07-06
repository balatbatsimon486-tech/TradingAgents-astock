"""Audit helpers for R2C-F architecture packages."""

from __future__ import annotations
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.contracts import ARCHITECTURE_CONTRACT_VERSION, ARCHITECTURE_STAGE, DECISION_BLOCKED, DECISION_READY, external_calls_all_false, hash_value


def build_audit(result: dict[str, Any]) -> dict[str, Any]:
    passed = bool(result.get("passed"))
    audit = {
        "audit_schema_version": "1.0",
        "stage": ARCHITECTURE_STAGE,
        "architecture_contract_version": ARCHITECTURE_CONTRACT_VERSION,
        "decision": DECISION_READY if passed else DECISION_BLOCKED,
        "ready_for_architecture_review": passed,
        "architecture_package_sealed": passed,
        "external_calls": external_calls_all_false(),
        "error_codes": [str(error.get("code", "")) for error in result.get("errors", [])],
        "candidate_catalog_hash": result.get("candidate_catalog_hash", ""),
        "evaluation_policy_hash": result.get("evaluation_policy_hash", ""),
        "recommendation_set_hash": result.get("recommendation_set_hash", ""),
        "deployment_topology_hash": result.get("deployment_topology_hash", ""),
        "ownership_matrix_hash": result.get("ownership_matrix_hash", ""),
        "change_control_hash": result.get("change_control_hash", ""),
        "rollback_plan_hash": result.get("rollback_plan_hash", ""),
        "drill_plan_hash": result.get("drill_plan_hash", ""),
        "evidence_bundle_hash": result.get("evidence_bundle_hash", ""),
        "architecture_package_hash": result.get("architecture_package_hash", ""),
    }
    audit["audit_hash"] = hash_value(audit)
    return audit
