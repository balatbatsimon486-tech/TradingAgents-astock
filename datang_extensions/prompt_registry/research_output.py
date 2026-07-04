"""Research input and structured output validation for R2B."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.contracts import SHA256_RE, stable_json_hash
from datang_extensions.prompt_registry.contracts import (
    ALLOWED_CONFIDENCE,
    ALLOWED_STANCES,
    MAX_EVIDENCE_COUNT,
    MAX_EVIDENCE_TEXT_CHARS,
    OUTPUT_SCHEMA_ID,
    OUTPUT_SCHEMA_VERSION,
    R2BContractError,
    r2b_error,
    safe_identifier,
    scan_security_fields,
)


class ResearchContractError(R2BContractError):
    """Raised when research input or output validation fails closed."""


def _raise_first(errors: list[dict[str, str]]) -> None:
    if errors:
        raise ResearchContractError(errors)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_research_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    if not isinstance(payload, Mapping):
        raise ResearchContractError([r2b_error("invalid_research_input", "research input must be an object")])
    for field in ("case_id", "snapshot_id", "input_artifact_id"):
        if not safe_identifier(payload.get(field)):
            errors.append(r2b_error("invalid_research_input", f"{field} must be a safe identifier", field_path=field))
    artifact_hash = payload.get("input_artifact_hash")
    if not isinstance(artifact_hash, str) or not SHA256_RE.fullmatch(artifact_hash):
        errors.append(r2b_error("invalid_research_input", "input_artifact_hash must be a lowercase SHA-256", field_path="input_artifact_hash"))
    context = payload.get("research_context")
    if not isinstance(context, Mapping):
        errors.append(r2b_error("invalid_research_input", "research_context must be an object", field_path="research_context"))
        _raise_first(errors)

    evidence = context.get("evidence")
    if not isinstance(evidence, list) or not evidence or len(evidence) > MAX_EVIDENCE_COUNT:
        errors.append(r2b_error("invalid_evidence", "evidence must be a non-empty bounded list", field_path="research_context.evidence"))
        _raise_first(errors)

    seen: set[str] = set()
    evidence_ids: list[str] = []
    evidence_by_id: dict[str, dict[str, str]] = {}
    for index, item in enumerate(evidence):
        field_prefix = f"research_context.evidence[{index}]"
        if not isinstance(item, Mapping):
            errors.append(r2b_error("invalid_evidence", "evidence entries must be objects", field_path=field_prefix))
            continue
        errors.extend(scan_security_fields(item, field_prefix))
        evidence_id = item.get("evidence_id")
        text = item.get("text")
        source_ref = item.get("source_ref")
        if not safe_identifier(evidence_id):
            errors.append(r2b_error("invalid_evidence", "evidence_id must be safe", field_path=f"{field_prefix}.evidence_id"))
            continue
        evidence_id = str(evidence_id)
        if evidence_id in seen:
            errors.append(r2b_error("duplicate_evidence_id", "evidence_id must be unique", field_path=f"{field_prefix}.evidence_id"))
            continue
        seen.add(evidence_id)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_EVIDENCE_TEXT_CHARS:
            errors.append(r2b_error("invalid_evidence", "evidence text must be non-empty and bounded", field_path=f"{field_prefix}.text"))
            continue
        if not isinstance(source_ref, str) or not source_ref.strip():
            errors.append(r2b_error("invalid_evidence", "source_ref must be non-empty", field_path=f"{field_prefix}.source_ref"))
            continue
        evidence_ids.append(evidence_id)
        evidence_by_id[evidence_id] = {"evidence_id": evidence_id, "text": text, "source_ref": source_ref}
    _raise_first(errors)
    context_copy = copy.deepcopy(dict(context))
    context_json = _canonical_json(context_copy)
    return {
        "case_id": str(payload["case_id"]),
        "snapshot_id": str(payload["snapshot_id"]),
        "input_artifact_id": str(payload["input_artifact_id"]),
        "input_artifact_hash": str(payload["input_artifact_hash"]),
        "research_context": context_copy,
        "research_context_json": context_json,
        "research_context_hash": stable_json_hash(context_copy),
        "evidence_ids": evidence_ids,
        "evidence_by_id": evidence_by_id,
        "fake_provider_mode": payload.get("fake_provider_mode"),
    }


def _claim_items(output: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    items = output.get(field)
    if not isinstance(items, list):
        raise ResearchContractError([r2b_error("invalid_research_output", f"{field} must be a list", field_path=field)])
    if not all(isinstance(item, Mapping) for item in items):
        raise ResearchContractError([r2b_error("invalid_research_output", f"{field} entries must be objects", field_path=field)])
    return list(items)


def validate_research_output(output: Mapping[str, Any], *, allowed_evidence_ids: list[str]) -> dict[str, Any]:
    if not isinstance(output, Mapping):
        raise ResearchContractError([r2b_error("invalid_research_output", "research output must be an object")])
    errors = scan_security_fields(output)
    if output.get("output_schema_id") != OUTPUT_SCHEMA_ID or output.get("output_schema_version") != OUTPUT_SCHEMA_VERSION:
        errors.append(r2b_error("unsupported_research_output_schema", "unsupported research output schema", field_path="output_schema_version"))
    if output.get("research_stance") not in ALLOWED_STANCES:
        errors.append(r2b_error("invalid_research_output", "research_stance is not allowlisted", field_path="research_stance"))
    if output.get("confidence") not in ALLOWED_CONFIDENCE:
        errors.append(r2b_error("invalid_research_output", "confidence is not allowlisted", field_path="confidence"))
    for flag in ("research_only", "not_a_trading_signal", "no_trading_decision"):
        if output.get(flag) is not True:
            errors.append(r2b_error("research_policy_violation", f"{flag} must be true", field_path=flag))
    if not isinstance(output.get("summary"), str) or not output.get("summary", "").strip():
        errors.append(r2b_error("invalid_research_output", "summary must be non-empty", field_path="summary"))
    uncertainties = output.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(isinstance(item, str) and item.strip() for item in uncertainties):
        errors.append(r2b_error("invalid_research_output", "uncertainties must be a text list", field_path="uncertainties"))

    allowed = set(allowed_evidence_ids)
    total_claims = 0
    cited_claims = 0
    for section in ("facts", "bull_case", "bear_case", "key_risks"):
        for index, item in enumerate(_claim_items(output, section)):
            total_claims += 1
            claim = item.get("claim")
            refs = item.get("evidence_refs")
            prefix = f"{section}[{index}]"
            if not isinstance(claim, str) or not claim.strip():
                errors.append(r2b_error("invalid_research_output", "claim must be non-empty", field_path=f"{prefix}.claim"))
            if not isinstance(refs, list) or not refs:
                errors.append(r2b_error("uncited_research_claim", "claim must cite evidence", field_path=f"{prefix}.evidence_refs"))
                continue
            if any(ref not in allowed for ref in refs):
                errors.append(r2b_error("unknown_evidence_reference", "claim cites unknown evidence", field_path=f"{prefix}.evidence_refs"))
                continue
            cited_claims += 1
    _raise_first(errors)
    coverage = cited_claims / total_claims if total_claims else 0
    return {
        "output": copy.deepcopy(dict(output)),
        "output_hash": stable_json_hash(output),
        "metrics": {
            "total_claims": total_claims,
            "cited_claims": cited_claims,
            "coverage_ratio": coverage,
        },
    }


def structured_output_from_gateway_content(content: Mapping[str, Any], *, evidence_ids: list[str], evidence_by_id: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    refs = evidence_ids or []
    first_ref = refs[:1]
    last_ref = refs[-1:] if refs else []
    summary = str(content.get("summary", "")).strip() or "Synthetic R2B structured research summary."
    bull_values = content.get("bull_case") if isinstance(content.get("bull_case"), list) else []
    bear_values = content.get("bear_case") if isinstance(content.get("bear_case"), list) else []
    risk_values = content.get("key_risks") if isinstance(content.get("key_risks"), list) else []
    uncertainty_values = content.get("uncertainties") if isinstance(content.get("uncertainties"), list) else []
    return {
        "output_schema_id": OUTPUT_SCHEMA_ID,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "summary": summary,
        "facts": [
            {
                "claim": f"Evidence {evidence_id} was considered as synthetic research data.",
                "evidence_refs": [evidence_id],
            }
            for evidence_id in refs
        ],
        "bull_case": [
            {"claim": str(value), "evidence_refs": first_ref or refs}
            for value in bull_values
        ],
        "bear_case": [
            {"claim": str(value), "evidence_refs": last_ref or refs}
            for value in bear_values
        ],
        "key_risks": [
            {"claim": str(value), "evidence_refs": last_ref or refs}
            for value in risk_values
        ],
        "uncertainties": [str(value) for value in uncertainty_values if str(value).strip()] or ["Synthetic R2B uncertainty only."],
        "research_stance": "neutral",
        "confidence": "low",
        "research_only": True,
        "not_a_trading_signal": True,
        "no_trading_decision": True,
    }
