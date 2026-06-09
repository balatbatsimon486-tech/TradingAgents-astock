"""Offline report ingestion smoke path for TradingAgents-astock output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datang_extensions.adapters.astock_report_adapter import write_standard_outputs
from datang_extensions.adapters.json_schema import (
    STANDARD_REPORT_FIELDS,
    missing_standard_fields,
)
from datang_extensions.utils.run_metadata import utc_now_iso
from datang_extensions.utils.safe_io import write_json_file

DEFAULT_INPUT_PATH = Path("datang_extensions") / "examples" / "offline_sample_input.json"
DEFAULT_OUTPUT_DIR = Path("reports") / "tradingagents_astock" / "offline_smoke"

REQUIRED_INPUT_FIELDS: tuple[str, ...] = ("symbol", "trade_date", "final_signal")


def load_offline_input(input_path: str | Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    """Load a synthetic offline TradingAgents-astock result from JSON."""

    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("offline input must be a JSON object")
    return payload


def _adapter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    adapted = dict(payload)
    if "raw_text" in adapted and "raw_report" not in adapted:
        adapted["raw_report"] = adapted["raw_text"]
    if "model_name" in adapted and "llm_model" not in adapted:
        adapted["llm_model"] = adapted["model_name"]
    return adapted


def _missing_required_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_INPUT_FIELDS:
        value = payload.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def _metadata_payload(
    *,
    input_path: Path,
    output_dir: Path,
    metadata_path: Path,
    report: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "generated_at_utc": utc_now_iso(),
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "markdown_report_path": str(report.get("raw_report_path", "")),
        "json_report_path": str(report.get("json_report_path", "")),
        "metadata_path": str(metadata_path),
        "standard_fields": list(STANDARD_REPORT_FIELDS),
        "missing_standard_fields": missing_standard_fields(report),
        "final_signal": report.get("final_signal", ""),
        "error": report.get("error"),
        "llm_called": False,
        "market_data_called": False,
        "tushare_called": False,
        "broker_called": False,
        "trade_order_created": False,
        "research_output_only": True,
    }


def ingest_offline_report(
    input_path: str | Path = DEFAULT_INPUT_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    upstream_commit: str = "",
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convert an offline sample input into standard Markdown, JSON, and metadata."""

    input_file = Path(input_path)
    output_directory = Path(output_dir)
    metadata_file = Path(metadata_path) if metadata_path else output_directory / "smoke_metadata.json"

    try:
        payload = load_offline_input(input_file)
        adapted = _adapter_payload(payload)
        missing = _missing_required_fields(adapted)
        error = ""
        if missing:
            error = f"offline input missing required fields: {', '.join(missing)}"

        report = write_standard_outputs(
            adapted,
            symbol=str(adapted.get("symbol", "")),
            trade_date=str(adapted.get("trade_date", "")),
            output_dir=output_directory,
            upstream_commit=upstream_commit,
            llm_model=str(adapted.get("llm_model", "")),
            analysis_mode=str(adapted.get("analysis_mode", "offline_smoke")),
            error=error or None,
        )
    except Exception as exc:
        report = write_standard_outputs(
            {},
            output_dir=output_directory,
            upstream_commit=upstream_commit,
            analysis_mode="offline_smoke",
            error=exc,
        )

    status = "failed" if report.get("error") else "ok"
    metadata = _metadata_payload(
        input_path=input_file,
        output_dir=output_directory,
        metadata_path=metadata_file,
        report=report,
        status=status,
    )
    write_json_file(metadata_file, metadata)

    return {
        "report": report,
        "metadata": metadata,
        "markdown_path": Path(str(report["raw_report_path"])),
        "json_path": Path(str(report["json_report_path"])),
        "metadata_path": metadata_file,
    }
