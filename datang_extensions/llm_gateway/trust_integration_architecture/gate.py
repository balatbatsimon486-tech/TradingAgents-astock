"""Offline R2C-F trust integration architecture gate."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.trust_integration_architecture.audit import build_audit
from datang_extensions.llm_gateway.trust_integration_architecture.candidates import validate_candidate_catalog, validate_evaluation_policy
from datang_extensions.llm_gateway.trust_integration_architecture.change_control import validate_change_control_plan
from datang_extensions.llm_gateway.trust_integration_architecture.contracts import (
    REQUIRED_REAL_WORLD_ACTIONS,
    ArchitectureError,
    base_result,
    hash_value,
    require_json_object,
)
from datang_extensions.llm_gateway.trust_integration_architecture.drills import validate_drill_plan
from datang_extensions.llm_gateway.trust_integration_architecture.evidence import validate_prerequisite_evidence
from datang_extensions.llm_gateway.trust_integration_architecture.ownership import validate_ownership_matrix
from datang_extensions.llm_gateway.trust_integration_architecture.rollback import validate_rollback_plan
from datang_extensions.llm_gateway.trust_integration_architecture.topology import validate_deployment_topology


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


def _ensure_payloads(payloads: tuple[Any, ...]) -> tuple[dict[str, Any], ...]:
    names = (
        "r2c_e_trust_boundary_result",
        "candidate_catalog",
        "evaluation_policy",
        "deployment_topology",
        "ownership_matrix",
        "change_control_plan",
        "rollback_plan",
        "drill_plan",
        "prerequisite_evidence",
    )
    return tuple(require_json_object(value, field_path=name) for value, name in zip(payloads, names))


def _package_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": result["stage"],
        "architecture_contract_version": result["architecture_contract_version"],
        "passed": result["passed"],
        "decision": result["decision"],
        "candidate_catalog_hash": result["candidate_catalog_hash"],
        "evaluation_policy_hash": result["evaluation_policy_hash"],
        "assessment_result_hash": result["assessment_result_hash"],
        "recommendation_set_hash": result["recommendation_set_hash"],
        "deployment_topology_hash": result["deployment_topology_hash"],
        "trust_zone_model_hash": result["trust_zone_model_hash"],
        "data_flow_set_hash": result["data_flow_set_hash"],
        "ownership_matrix_hash": result["ownership_matrix_hash"],
        "change_control_hash": result["change_control_hash"],
        "rollback_plan_hash": result["rollback_plan_hash"],
        "drill_plan_hash": result["drill_plan_hash"],
        "evidence_bundle_hash": result["evidence_bundle_hash"],
        "blocking_findings_hash": result["blocking_findings_hash"],
        "required_real_world_actions_hash": result["required_real_world_actions_hash"],
        "candidate_assessments": result["candidate_assessments"],
        "recommendations": result["recommendations"],
        "trust_zone_model": result["trust_zone_model"],
        "data_flow_set": result["data_flow_set"],
        "ownership_assignments": result["ownership_assignments"],
        "change_control_summary": result["change_control_summary"],
        "rollback_summary": result["rollback_summary"],
        "drill_scenarios": result["drill_scenarios"],
        "evidence_summary": result["evidence_summary"],
        "required_real_world_actions": result["required_real_world_actions"],
        "blocking_findings": result["blocking_findings"],
    }


def run_offline_trust_integration_architecture(
    r2c_e_trust_boundary_result: Mapping[str, Any],
    candidate_catalog: Mapping[str, Any],
    evaluation_policy: Mapping[str, Any],
    deployment_topology: Mapping[str, Any],
    ownership_matrix: Mapping[str, Any],
    change_control_plan: Mapping[str, Any],
    rollback_plan: Mapping[str, Any],
    drill_plan: Mapping[str, Any],
    prerequisite_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    trust_boundary, catalog, policy, topology, ownership, change, rollback, drill, evidence = _ensure_payloads(
        (
            r2c_e_trust_boundary_result,
            candidate_catalog,
            evaluation_policy,
            deployment_topology,
            ownership_matrix,
            change_control_plan,
            rollback_plan,
            drill_plan,
            prerequisite_evidence,
        )
    )

    errors: list[dict[str, str]] = []
    evaluation_policy_hash, policy_errors, policy_info = validate_evaluation_policy(policy)
    errors.extend(policy_errors)
    candidate_catalog_hash, catalog_errors, assessments, recommendations = validate_candidate_catalog(catalog, policy_info)
    errors.extend(catalog_errors)
    deployment_hash, trust_zone_hash, data_flow_hash, topology_errors, trust_zone_model, _, data_flow_set = validate_deployment_topology(topology)
    errors.extend(topology_errors)
    ownership_hash, ownership_errors, ownership_assignments = validate_ownership_matrix(ownership)
    errors.extend(ownership_errors)
    change_hash, change_errors, change_summary = validate_change_control_plan(change)
    errors.extend(change_errors)
    rollback_hash, rollback_errors, rollback_summary = validate_rollback_plan(rollback)
    errors.extend(rollback_errors)
    drill_hash, drill_errors, drill_scenarios = validate_drill_plan(drill)
    errors.extend(drill_errors)
    evidence_hash, evidence_errors, evidence_summary = validate_prerequisite_evidence(trust_boundary, evidence)
    errors.extend(evidence_errors)

    errors = _dedupe_errors(errors)
    result = base_result(errors)
    result.update(
        {
            "candidate_catalog_hash": candidate_catalog_hash,
            "evaluation_policy_hash": evaluation_policy_hash,
            "assessment_result_hash": hash_value(assessments),
            "recommendation_set_hash": hash_value(recommendations),
            "deployment_topology_hash": deployment_hash,
            "trust_zone_model_hash": trust_zone_hash,
            "data_flow_set_hash": data_flow_hash,
            "ownership_matrix_hash": ownership_hash,
            "change_control_hash": change_hash,
            "rollback_plan_hash": rollback_hash,
            "drill_plan_hash": drill_hash,
            "evidence_bundle_hash": evidence_hash,
            "blocking_findings_hash": hash_value(errors),
            "required_real_world_actions_hash": hash_value(REQUIRED_REAL_WORLD_ACTIONS),
            "candidate_assessments": assessments,
            "recommendations": recommendations if not errors else [item for item in recommendations if item.get("recommendation_ready") is True],
            "trust_zone_model": trust_zone_model,
            "data_flow_set": data_flow_set,
            "ownership_assignments": ownership_assignments,
            "change_control_summary": {
                "change_plan_id": change_summary.get("change_plan_id"),
                "status": change_summary.get("status"),
                "abort_conditions": change_summary.get("abort_conditions", []),
                "required_approver_roles": change_summary.get("required_approver_roles", []),
            },
            "rollback_summary": {
                "rollback_plan_id": rollback_summary.get("rollback_plan_id"),
                "status": rollback_summary.get("status"),
                "trigger_count": len(rollback_summary.get("triggers", [])),
                "exit_strategy": rollback_summary.get("exit_strategy", {}),
            },
            "drill_scenarios": [
                {
                    "drill_id": item.get("drill_id"),
                    "scenario": item.get("scenario"),
                    "execution_state": item.get("execution_state"),
                    "expected_decision": item.get("expected_decision"),
                    "expected_rollback_path": item.get("expected_rollback_path"),
                }
                for item in drill_scenarios
            ],
            "evidence_summary": evidence_summary,
        }
    )
    result["architecture_package_hash"] = hash_value(_package_payload(result))
    audit = build_audit(result)
    result["audit"] = audit
    result["audit_hash"] = audit["audit_hash"]
    result["warnings"] = []
    result["errors"] = errors
    result["blocking_findings"] = errors
    return result


def build_expected_architecture_result(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    fields = [
        "stage",
        "architecture_contract_version",
        "passed",
        "decision",
        "architecture_package_sealed",
        "ready_for_architecture_review",
        "candidate_assessment_ready",
        "candidate_recommendation_ready",
        "deployment_topology_contract_ready",
        "trust_zone_model_ready",
        "ownership_matrix_ready",
        "change_control_plan_ready",
        "rollback_plan_ready",
        "operational_drill_plan_ready",
        "candidate_catalog_hash",
        "evaluation_policy_hash",
        "assessment_result_hash",
        "recommendation_set_hash",
        "deployment_topology_hash",
        "trust_zone_model_hash",
        "data_flow_set_hash",
        "ownership_matrix_hash",
        "change_control_hash",
        "rollback_plan_hash",
        "drill_plan_hash",
        "evidence_bundle_hash",
        "blocking_findings_hash",
        "required_real_world_actions_hash",
        "architecture_package_hash",
        "audit_hash",
        "recommendations",
        "required_real_world_actions",
        "blocking_findings",
        "errors",
    ]
    return {field: payload.get(field) for field in fields}


__all__ = ["ArchitectureError", "build_expected_architecture_result", "run_offline_trust_integration_architecture"]
