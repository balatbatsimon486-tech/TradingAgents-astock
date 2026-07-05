"""Offline sandbox readiness gate for R2C-C."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.audit import build_readiness_audit
from datang_extensions.llm_gateway.sandbox_readiness.contracts import base_result, hash_value, safe_copy, scan_forbidden_surface
from datang_extensions.llm_gateway.sandbox_readiness.egress import validate_egress_policy
from datang_extensions.llm_gateway.sandbox_readiness.evidence import validate_incident_response, validate_prerequisite_evidence
from datang_extensions.llm_gateway.sandbox_readiness.profile import validate_run_manifest, validate_sandbox_profile, validate_secret_storage_proposal
from datang_extensions.llm_gateway.sandbox_readiness.threat_model import validate_threat_model


def _mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _component_hashes(
    profile: Mapping[str, Any],
    secret_proposal: Mapping[str, Any],
    egress_policy: Mapping[str, Any],
    manifest: Mapping[str, Any],
    threat_model: Mapping[str, Any],
    evidence: Mapping[str, Any],
    incident_response: Mapping[str, Any],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    profile_hash, profile_errors = validate_sandbox_profile(profile, manifest)
    secret_hash, secret_errors = validate_secret_storage_proposal(secret_proposal, profile)
    egress_hash, egress_errors = validate_egress_policy(egress_policy)
    manifest_hash, manifest_errors = validate_run_manifest(manifest, profile)
    threat_hash, threat_errors = validate_threat_model(threat_model)
    evidence_hash, evidence_errors = validate_prerequisite_evidence(evidence)
    incident_hash, incident_errors = validate_incident_response(incident_response)
    hashes = {
        "profile_hash": profile_hash,
        "secret_proposal_hash": secret_hash,
        "egress_policy_hash": egress_hash,
        "manifest_hash": manifest_hash,
        "threat_model_hash": threat_hash,
        "evidence_hash": evidence_hash,
        "incident_plan_hash": incident_hash,
    }
    errors = profile_errors + secret_errors + egress_errors + manifest_errors + threat_errors + evidence_errors + incident_errors
    return hashes, errors


def _package_hash(component_hashes: Mapping[str, str], manifest: Mapping[str, Any]) -> str:
    return hash_value(
        {
            "component_hashes": dict(component_hashes),
            "manual_review_requirements": list(manifest.get("manual_review_requirements", [])) if isinstance(manifest.get("manual_review_requirements"), list) else [],
            "decision_ceiling": "ready_for_human_review",
            "live_authorized": False,
        }
    )


def run_offline_sandbox_readiness(
    sandbox_profile: Mapping[str, Any],
    secret_storage_proposal: Mapping[str, Any],
    egress_policy: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    threat_model: Mapping[str, Any],
    prerequisite_evidence: Mapping[str, Any],
    incident_response: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an offline readiness package without resolving secrets or executing providers."""

    profile = _mapping(sandbox_profile)
    secret_proposal = _mapping(secret_storage_proposal)
    egress = _mapping(egress_policy)
    manifest = _mapping(run_manifest)
    threats = _mapping(threat_model)
    evidence = _mapping(prerequisite_evidence)
    incident = _mapping(incident_response)
    errors: list[dict[str, str]] = []
    for name, payload in (
        ("sandbox_profile", profile),
        ("secret_storage_proposal", secret_proposal),
        ("egress_policy", egress),
        ("run_manifest", manifest),
        ("threat_model", threats),
        ("prerequisite_evidence", evidence),
        ("incident_response", incident),
    ):
        found = scan_forbidden_surface(payload, prefix=name)
        if found:
            errors.append(found)
    component_hashes, component_errors = _component_hashes(profile, secret_proposal, egress, manifest, threats, evidence, incident)
    errors.extend(component_errors)
    result = base_result(errors)
    result.update(component_hashes)
    result["manual_review_requirements"] = list(manifest.get("manual_review_requirements", [])) if isinstance(manifest.get("manual_review_requirements"), list) else []
    result["blocking_findings"] = list(errors)
    result["readiness_package_hash"] = _package_hash(component_hashes, manifest)
    audit = build_readiness_audit(result)
    result["audit"] = audit
    result["audit_hash"] = str(audit["audit_hash"])
    return result


def build_expected_readiness_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(result))
