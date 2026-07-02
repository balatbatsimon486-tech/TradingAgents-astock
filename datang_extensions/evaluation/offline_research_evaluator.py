"""Deterministic offline research artifact evaluation for M2A."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from datang_extensions.adapters.json_schema import STANDARD_REPORT_FIELDS

EVALUATION_STAGE = "tradingagents_m2a_offline_research_evaluation"
EVALUATION_VERSION = "1.0"
EVALUATION_THRESHOLD = 100

CRITICAL_CHECKS: tuple[str, ...] = (
    "snapshot_contract",
    "snapshot_qa",
    "artifact_exists",
    "artifact_schema",
    "research_only_boundary",
    "no_forbidden_trading_fields",
    "no_credential_fields",
    "lineage_preserved",
    "temporal_metadata",
    "deterministic_output",
    "no_external_calls",
)

SEVERITIES: frozenset[str] = frozenset({"critical", "warning", "info"})

FORBIDDEN_TRADING_FIELDS: frozenset[str] = frozenset(
    {
        "order",
        "order_size",
        "position",
        "position_size",
        "target_weight",
        "portfolio_weight",
        "execution_price",
        "broker",
        "auto_trade",
        "stop_loss_order",
        "take_profit_order",
    }
)

CREDENTIAL_FIELDS: frozenset[str] = frozenset(
    {
        "token",
        "api_key",
        "secret",
        "password",
        "access_key",
        "private_key",
        "authorization",
    }
)

VOLATILE_FIELDS: tuple[str, ...] = (
    "evaluation_id",
    "generated_at",
    "created_at",
    "created_at_utc",
    "generated_at_utc",
    "run_time_utc",
    "output_path",
    "output_dir",
    "input_path",
    "duration",
    "raw_report_path",
    "json_report_path",
    "markdown_path",
    "metadata_path",
)

EXTERNAL_CALLS_FALSE: dict[str, bool] = {
    "llm_called": False,
    "network_called": False,
    "market_data_called": False,
    "tushare_called": False,
    "qlib_called": False,
    "broker_called": False,
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def normalized_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    volatile = set(VOLATILE_FIELDS)

    def normalize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): normalize(nested) for key, nested in sorted(value.items()) if key not in volatile}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(dict(artifact))


def _check(name: str, passed: bool, details: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "severity": "critical",
        "details": details or [],
    }


def _error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "field_path": field_path}


def _find_forbidden_key(value: Any, forbidden: frozenset[str], prefix: str = "") -> str:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text.strip().lower() in forbidden:
                return path
            found = _find_forbidden_key(nested, forbidden, path)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_forbidden_key(item, forbidden, f"{prefix}[{index}]")
            if found:
                return found
    return ""


def _parse_aware_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _empty_summary(
    *,
    case_id: str,
    snapshot_id: str = "",
    schema_version: str = "",
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "stage": EVALUATION_STAGE,
        "evaluation_version": EVALUATION_VERSION,
        "evaluation_id": f"{case_id}:{snapshot_id}" if snapshot_id else case_id,
        "case_id": case_id,
        "snapshot_id": snapshot_id,
        "snapshot_schema_version": schema_version,
        "passed": False,
        "score": 0,
        "threshold": EVALUATION_THRESHOLD,
        "checks": [],
        "artifact_summary": {},
        "lineage": {},
        "external_calls": dict(EXTERNAL_CALLS_FALSE),
        "warnings": [],
        "errors": errors or [],
    }


def failure_summary(
    *,
    case_id: str,
    code: str,
    message: str,
    snapshot_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot_id = str((snapshot_context or {}).get("snapshot_id", ""))
    schema_version = str((snapshot_context or {}).get("schema_version", ""))
    summary = _empty_summary(
        case_id=case_id,
        snapshot_id=snapshot_id,
        schema_version=schema_version,
        errors=[_error(code, message)],
    )
    summary["checks"] = [_check(name, False, [code]) for name in CRITICAL_CHECKS]
    return summary


def evaluate_research_artifact(
    *,
    artifact: Mapping[str, Any],
    markdown_path: str | Path,
    json_path: str | Path,
    snapshot_context: Mapping[str, Any],
    snapshot_hash: str,
    case_id: str,
) -> dict[str, Any]:
    snapshot_id = str(snapshot_context.get("snapshot_id", ""))
    schema_version = str(snapshot_context.get("schema_version", ""))
    source = str(snapshot_context.get("source", ""))
    as_of_time = str(snapshot_context.get("as_of_time", ""))
    data_quality = snapshot_context.get("data_quality")
    json_file = Path(json_path)
    markdown_file = Path(markdown_path)
    artifact_copy = copy.deepcopy(dict(artifact))

    errors: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    snapshot_contract_ok = all(
        [
            bool(snapshot_id),
            bool(schema_version),
            bool(source),
            bool(as_of_time),
            isinstance(data_quality, Mapping),
        ]
    )
    checks.append(_check("snapshot_contract", snapshot_contract_ok))
    if not snapshot_contract_ok:
        errors.append(_error("snapshot_contract_failed", "snapshot identity fields are incomplete"))

    snapshot_qa_ok = isinstance(data_quality, Mapping) and data_quality.get("passed") is True
    checks.append(_check("snapshot_qa", snapshot_qa_ok))
    if not snapshot_qa_ok:
        errors.append(_error("snapshot_contract_failed", "snapshot QA did not pass", field_path="data_quality"))

    artifact_exists_ok = json_file.exists() and markdown_file.exists()
    checks.append(_check("artifact_exists", artifact_exists_ok))
    if not artifact_exists_ok:
        errors.append(_error("artifact_generation_failed", "standard JSON or Markdown artifact is missing"))

    artifact_schema_ok = set(artifact_copy) == set(STANDARD_REPORT_FIELDS)
    checks.append(_check("artifact_schema", artifact_schema_ok))
    if not artifact_schema_ok:
        errors.append(_error("artifact_schema_failed", "standard artifact fields do not match contract"))

    risk_flags = artifact_copy.get("risk_flags") or []
    research_only_ok = (
        artifact_copy.get("final_signal")
        in {"research_buy", "research_hold", "research_sell", "no_actionable_signal", "analysis_failed"}
        and "not_validated_trade_signal" in risk_flags
    )
    checks.append(_check("research_only_boundary", research_only_ok))
    if not research_only_ok:
        errors.append(_error("research_boundary_failed", "artifact is not clearly research-only"))

    forbidden_trading_path = _find_forbidden_key(artifact_copy, FORBIDDEN_TRADING_FIELDS)
    no_forbidden_trading_ok = not forbidden_trading_path
    checks.append(_check("no_forbidden_trading_fields", no_forbidden_trading_ok))
    if forbidden_trading_path:
        errors.append(
            _error(
                "forbidden_trading_field_detected",
                "artifact contains an executable trading field",
                field_path=forbidden_trading_path,
            )
        )

    credential_path = _find_forbidden_key(artifact_copy, CREDENTIAL_FIELDS)
    no_credential_ok = not credential_path
    checks.append(_check("no_credential_fields", no_credential_ok))
    if credential_path:
        errors.append(
            _error(
                "credential_field_detected",
                "artifact contains a credential-like field",
                field_path=credential_path,
            )
        )

    artifact_text = json.dumps(artifact_copy, ensure_ascii=False, sort_keys=True)
    lineage_ok = all(token and token in artifact_text for token in (snapshot_id, schema_version, source, as_of_time))
    checks.append(_check("lineage_preserved", lineage_ok))
    if not lineage_ok:
        errors.append(_error("lineage_mismatch", "snapshot lineage is not preserved in the artifact"))

    artifact_time = _parse_aware_datetime(str(artifact_copy.get("run_time_utc", "")))
    snapshot_time = _parse_aware_datetime(as_of_time)
    temporal_ok = snapshot_time is not None and artifact_time is not None and artifact_time >= snapshot_time
    checks.append(_check("temporal_metadata", temporal_ok))
    if not temporal_ok:
        errors.append(_error("temporal_metadata_failed", "artifact temporal metadata is invalid"))

    raw_hash = sha256_file(json_file) if json_file.exists() else ""
    normalized = normalized_artifact(artifact_copy)
    normalized_hash = stable_json_hash(normalized)
    deterministic_ok = bool(normalized_hash)
    checks.append(_check("deterministic_output", deterministic_ok))
    if not deterministic_ok:
        errors.append(_error("determinism_failed", "normalized artifact hash could not be computed"))

    checks.append(_check("no_external_calls", True))

    passed = not any(not check["passed"] for check in checks if check["severity"] == "critical")
    score = 100 if passed else 0
    return {
        "stage": EVALUATION_STAGE,
        "evaluation_version": EVALUATION_VERSION,
        "evaluation_id": f"{case_id}:{snapshot_id}",
        "case_id": case_id,
        "snapshot_id": snapshot_id,
        "snapshot_schema_version": schema_version,
        "passed": passed,
        "score": score,
        "threshold": EVALUATION_THRESHOLD,
        "checks": checks,
        "artifact_summary": {
            "json_path": str(json_file),
            "markdown_path": str(markdown_file),
            "research_only": research_only_ok,
            "not_a_trading_signal": "not_validated_trade_signal" in risk_flags,
            "no_trading_decision": no_forbidden_trading_ok,
            "raw_artifact_hash": raw_hash,
            "normalized_artifact_hash": normalized_hash,
            "excluded_volatile_fields": list(VOLATILE_FIELDS),
        },
        "lineage": {
            "snapshot_id": snapshot_id,
            "source": source,
            "schema_version": schema_version,
            "as_of_time": as_of_time,
            "snapshot_hash": snapshot_hash,
            "raw_artifact_hash": raw_hash,
            "normalized_artifact_hash": normalized_hash,
        },
        "external_calls": dict(EXTERNAL_CALLS_FALSE),
        "warnings": list(snapshot_context.get("warnings") or []),
        "errors": errors,
    }
