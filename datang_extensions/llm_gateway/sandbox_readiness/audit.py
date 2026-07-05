"""Audit helpers for the R2C-C offline sandbox readiness gate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.contracts import READINESS_STAGE, hash_value


def build_readiness_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = {
        "audit_schema_version": "1.0",
        "stage": READINESS_STAGE,
        "decision": payload.get("decision", "blocked"),
        "ready_for_human_review": bool(payload.get("ready_for_human_review", False)),
        "human_review_completed": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "profile_hash": str(payload.get("profile_hash", "")),
        "secret_proposal_hash": str(payload.get("secret_proposal_hash", "")),
        "egress_policy_hash": str(payload.get("egress_policy_hash", "")),
        "manifest_hash": str(payload.get("manifest_hash", "")),
        "threat_model_hash": str(payload.get("threat_model_hash", "")),
        "evidence_hash": str(payload.get("evidence_hash", "")),
        "incident_plan_hash": str(payload.get("incident_plan_hash", "")),
        "readiness_package_hash": str(payload.get("readiness_package_hash", "")),
        "manual_review_requirement_count": len(payload.get("manual_review_requirements", [])) if isinstance(payload.get("manual_review_requirements"), list) else 0,
        "blocking_finding_count": len(payload.get("blocking_findings", [])) if isinstance(payload.get("blocking_findings"), list) else 0,
        "external_calls": dict(payload.get("external_calls", {})) if isinstance(payload.get("external_calls"), Mapping) else {},
        "error_codes": [str(error.get("code", "")) for error in payload.get("errors", []) if isinstance(error, Mapping)],
    }
    audit["audit_hash"] = hash_value({key: value for key, value in audit.items() if key != "audit_hash"})
    return audit
