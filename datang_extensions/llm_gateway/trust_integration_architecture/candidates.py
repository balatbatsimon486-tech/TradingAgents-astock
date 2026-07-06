"""Synthetic candidate catalog validation and scoring for R2C-F."""

from __future__ import annotations
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from datang_extensions.llm_gateway.trust_integration_architecture.contracts import SERVICE_CLASSES, architecture_error, decimal_string, decimal_value, hash_value, require_safe_id, scan_architecture_surface, sorted_records


def validate_evaluation_policy(policy: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    if policy.get("evaluation_policy_version") != "1.0":
        errors.append(architecture_error("invalid_evaluation_policy", "unsupported evaluation policy version", field_path="evaluation_policy_version"))
    controls = policy.get("mandatory_controls") if isinstance(policy.get("mandatory_controls"), list) else []
    if len(controls) < 15 or any(not isinstance(item, str) or not item for item in controls):
        errors.append(architecture_error("invalid_evaluation_policy", "mandatory controls are incomplete", field_path="mandatory_controls"))
    weights = policy.get("scoring_weights") if isinstance(policy.get("scoring_weights"), Mapping) else {}
    total = sum(int(value) for value in weights.values() if isinstance(value, int))
    if total != 100:
        errors.append(architecture_error("evaluation_weight_total_invalid", "scoring weights must total 100", field_path="scoring_weights"))
    threshold = decimal_value(policy.get("recommendation_threshold"))
    if threshold is None or threshold < Decimal("85"):
        errors.append(architecture_error("invalid_evaluation_policy", "recommendation threshold must be at least 85", field_path="recommendation_threshold"))
    canonical = dict(policy)
    canonical["mandatory_controls"] = sorted(str(item) for item in controls)
    canonical["scoring_weights"] = {str(key): weights[key] for key in sorted(weights)}
    return hash_value(canonical), errors, {"mandatory_controls": list(controls), "weights": dict(weights), "threshold": threshold or Decimal("999")}


def validate_candidate_catalog(catalog: Mapping[str, Any], policy_info: Mapping[str, Any]) -> tuple[str, list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, str]] = []
    forbidden = scan_architecture_surface(catalog, code="invalid_candidate_catalog", field_path="candidate_catalog")
    if forbidden:
        errors.append(forbidden)
    if catalog.get("candidate_catalog_version") != "1.0":
        errors.append(architecture_error("invalid_candidate_catalog", "unsupported candidate catalog version", field_path="candidate_catalog_version"))
    if catalog.get("synthetic_only") is not True:
        errors.append(architecture_error("candidate_catalog_must_be_synthetic", "candidate catalog must be synthetic only", field_path="synthetic_only"))
    if catalog.get("real_vendor_research_completed") is not False:
        errors.append(architecture_error("invalid_candidate_catalog", "real vendor research is outside R2C-F", field_path="real_vendor_research_completed"))
    candidates = catalog.get("candidates") if isinstance(catalog.get("candidates"), list) else []
    seen: set[str] = set()
    counts = {service: 0 for service in SERVICE_CLASSES}
    assessments: list[dict[str, Any]] = []
    controls = list(policy_info.get("mandatory_controls", []))
    weights = dict(policy_info.get("weights", {}))
    threshold = policy_info.get("threshold", Decimal("999"))
    for index, raw in enumerate(candidates):
        if not isinstance(raw, Mapping):
            errors.append(architecture_error("invalid_candidate_catalog", "candidate must be an object", field_path=f"candidates[{index}]"))
            continue
        candidate = dict(raw)
        cid = str(candidate.get("candidate_id", ""))
        require_safe_id(cid, errors, "real_vendor_identifier_not_allowed" if cid else "invalid_candidate_catalog", f"candidates[{index}].candidate_id")
        if cid in seen:
            errors.append(architecture_error("duplicate_candidate_id", "candidate ids must be unique", field_path=f"candidates[{index}].candidate_id"))
        seen.add(cid)
        service = str(candidate.get("service_class", ""))
        if service in counts:
            counts[service] += 1
        if service not in SERVICE_CLASSES:
            errors.append(architecture_error("invalid_candidate_catalog", "service class is not allowed", field_path=f"candidates[{index}].service_class"))
        if candidate.get("status") != "assessment_only":
            errors.append(architecture_error("invalid_candidate_catalog", "candidate status must be assessment_only", field_path=f"candidates[{index}].status"))
        for field in ("capability_claims_verified", "commercial_terms_verified", "deployment_support_verified"):
            if candidate.get(field) is not False:
                errors.append(architecture_error("invalid_candidate_catalog", f"{field} must be false", field_path=f"candidates[{index}].{field}"))
        mandatory = candidate.get("mandatory_control_responses") if isinstance(candidate.get("mandatory_control_responses"), Mapping) else {}
        failed_controls = [control for control in controls if mandatory.get(control) is not True]
        score_value: Decimal | None = None
        score_text: str | None = None
        qualified = not failed_controls
        if failed_controls:
            errors.append(architecture_error("mandatory_control_failed", "candidate failed mandatory control", field_path=f"candidates[{index}].mandatory_control_responses"))
        attrs = candidate.get("scored_attributes") if isinstance(candidate.get("scored_attributes"), Mapping) else {}
        if qualified:
            score_value = Decimal("0")
            for name, weight in weights.items():
                value = decimal_value(attrs.get(name))
                if value is None or value < 0 or value > 10:
                    errors.append(architecture_error("candidate_score_invalid", "candidate score must be between 0 and 10", field_path=f"candidates[{index}].scored_attributes.{name}"))
                    qualified = False
                    score_value = None
                    break
                score_value += value * Decimal(str(weight)) / Decimal("10")
            if score_value is not None:
                score_text = decimal_string(score_value)
        assessments.append({"candidate_id": cid, "service_class": service, "candidate_qualified": qualified, "candidate_score": score_text, "recommendation_eligible": bool(qualified and score_value is not None and score_value >= threshold)})
    for service, count in counts.items():
        if count < 2:
            errors.append(architecture_error("candidate_service_class_missing", "each service class requires at least two candidates", field_path=service))
    canonical = dict(catalog)
    canonical["candidates"] = sorted_records([dict(item) for item in candidates if isinstance(item, Mapping)], "candidate_id")
    recommendations: list[dict[str, Any]] = []
    for service in SERVICE_CLASSES:
        eligible = [item for item in assessments if item["service_class"] == service and item["recommendation_eligible"]]
        eligible.sort(key=lambda item: (-Decimal(str(item["candidate_score"])), str(item["candidate_id"])))
        if eligible:
            selected = eligible[0]
            recommendations.append({"service_class": service, "recommended_candidate_id": selected["candidate_id"], "candidate_score": selected["candidate_score"], "recommendation_ready": True, "vendor_selected": False, "procurement_approved": False})
        else:
            errors.append(architecture_error("candidate_recommendation_unavailable", "no eligible synthetic candidate met threshold", field_path=service))
    recommendations.sort(key=lambda item: str(item["recommended_candidate_id"]))
    assessments.sort(key=lambda item: str(item["candidate_id"]))
    return hash_value(canonical), errors, assessments, recommendations
