"""Offline Stage 3A to Stage 2 research evaluation pipeline for M2A."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from datang_extensions.evaluation.offline_research_evaluator import (
    evaluate_research_artifact,
    failure_summary,
    sha256_file,
)
from datang_extensions.ingestion.offline_report_ingestion import ingest_offline_report
from datang_extensions.ingestion.research_snapshot_reader import read_research_snapshot
from datang_extensions.utils.safe_io import write_json_file


def _stage2_input_from_context(
    context: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    case_id: str,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    required = ("symbol", "trade_date")
    missing = [field for field in required if not str(context.get(field, "")).strip()]
    research_opinion = snapshot.get("research_opinion")
    if not str(research_opinion or "").strip():
        missing.append("research_opinion")
    if missing:
        return None, {
            "code": "stage2_input_mapping_failed",
            "message": f"snapshot missing Stage 2 mapping fields: {', '.join(missing)}",
        }

    key_points = snapshot.get("key_points") or []
    risks = snapshot.get("risks") or []
    references = snapshot.get("source_references") or []
    lineage_text = (
        f"snapshot_id={context.get('snapshot_id')}; "
        f"schema_version={context.get('schema_version')}; "
        f"source={context.get('source')}; "
        f"as_of_time={context.get('as_of_time')}; "
        f"case_id={case_id}"
    )
    return {
        "symbol": context.get("symbol", ""),
        "trade_date": context.get("trade_date", ""),
        "model_name": "offline-synthetic-no-api",
        "analysis_mode": "m2a_offline_research_evaluation",
        "final_signal": research_opinion,
        "confidence": None,
        "risk_flags": ["m2a_synthetic_fixture", "not_validated_trade_signal"],
        "policy_summary": f"{snapshot.get('summary', '')}\n{lineage_text}",
        "sentiment_summary": "Synthetic fixture only; no live sentiment or news feed was called.",
        "technical_summary": "Synthetic fixture only; no market data interface was called.",
        "fundamental_summary": "Synthetic fixture only; no financial data provider was called.",
        "hot_money_summary": "Synthetic fixture only; no Dragon Tiger List endpoint was called.",
        "lockup_summary": "Synthetic fixture only; no shareholder lockup endpoint was called.",
        "raw_text": "\n".join(
            [
                "M2A synthetic offline research fixture.",
                lineage_text,
                f"key_points={json.dumps(key_points, ensure_ascii=False)}",
                f"risks={json.dumps(risks, ensure_ascii=False)}",
                f"source_references={json.dumps(references, ensure_ascii=False)}",
                "research_only=true",
                "not_a_trading_signal=true",
                "no_trading_decision=true",
            ]
        ),
    }, None


def run_offline_research_evaluation(
    snapshot_path: str | Path,
    *,
    allowed_root: str | Path,
    output_root: str | Path,
    case_id: str,
) -> dict[str, Any]:
    """Run the fully offline M2A research evaluation pipeline."""

    snapshot_file = Path(snapshot_path)
    snapshot_hash = sha256_file(snapshot_file) if snapshot_file.exists() and snapshot_file.is_file() else ""
    snapshot_result = read_research_snapshot(snapshot_file, allowed_root=allowed_root)
    if not snapshot_result.get("ok"):
        return failure_summary(
            case_id=case_id,
            code="snapshot_rejected",
            message=str((snapshot_result.get("error") or {}).get("code", "snapshot rejected")),
        )

    context = snapshot_result["context"]
    try:
        snapshot_payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return failure_summary(
            case_id=case_id,
            code="stage2_input_mapping_failed",
            message=type(exc).__name__,
            snapshot_context=context,
        )
    if not isinstance(snapshot_payload, Mapping):
        return failure_summary(
            case_id=case_id,
            code="stage2_input_mapping_failed",
            message="snapshot payload is not an object",
            snapshot_context=context,
        )

    stage2_input, mapping_error = _stage2_input_from_context(context, snapshot_payload, case_id)
    if mapping_error is not None or stage2_input is None:
        return failure_summary(
            case_id=case_id,
            code=mapping_error["code"],
            message=mapping_error["message"],
            snapshot_context=context,
        )

    case_root = Path(output_root) / case_id
    input_path = case_root / "stage2_input.json"
    metadata_path = case_root / "stage2_metadata.json"
    artifact_root = case_root / "artifacts"
    write_json_file(input_path, stage2_input)

    try:
        stage2_result = ingest_offline_report(
            input_path,
            artifact_root,
            metadata_path=metadata_path,
        )
    except Exception as exc:
        return failure_summary(
            case_id=case_id,
            code="artifact_generation_failed",
            message=type(exc).__name__,
            snapshot_context=context,
        )

    report = stage2_result["report"]
    if report.get("error"):
        return failure_summary(
            case_id=case_id,
            code="artifact_generation_failed",
            message="Stage 2 ingestion returned an error",
            snapshot_context=context,
        )

    summary = evaluate_research_artifact(
        artifact=report,
        markdown_path=stage2_result["markdown_path"],
        json_path=stage2_result["json_path"],
        snapshot_context=context,
        snapshot_hash=snapshot_hash,
        case_id=case_id,
    )
    summary["snapshot_context"] = {
        "snapshot_id": context.get("snapshot_id", ""),
        "schema_version": context.get("schema_version", ""),
        "source": context.get("source", ""),
        "as_of_time": context.get("as_of_time", ""),
        "data_quality": context.get("data_quality", {}),
        "warnings": context.get("warnings", []),
        "errors": context.get("errors", []),
    }
    write_json_file(case_root / "evaluation_summary.json", summary)
    return summary
