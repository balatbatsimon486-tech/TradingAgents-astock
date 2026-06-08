"""Future adapter from A-share AI research reports to datang-quant-platform."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.adapters.json_schema import missing_standard_fields

PLATFORM_CONTRACT_VERSION = "research.astock.v1"


def to_quant_platform_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    missing = missing_standard_fields(report)
    if missing:
        raise ValueError(f"standard report missing fields: {', '.join(missing)}")

    return {
        "contract_version": PLATFORM_CONTRACT_VERSION,
        "producer": report["source"],
        "symbol": report["symbol"],
        "trade_date": report["trade_date"],
        "research_layer": {
            "final_signal": report["final_signal"],
            "confidence": report["confidence"],
            "policy_summary": report["policy_summary"],
            "sentiment_summary": report["sentiment_summary"],
            "technical_summary": report["technical_summary"],
            "fundamental_summary": report["fundamental_summary"],
            "hot_money_summary": report["hot_money_summary"],
            "lockup_summary": report["lockup_summary"],
            "risk_flags": list(report["risk_flags"]),
        },
        "metadata": {
            "upstream_commit": report["upstream_commit"],
            "datang_extension_version": report["datang_extension_version"],
            "run_time_utc": report["run_time_utc"],
            "llm_model": report["llm_model"],
            "analysis_mode": report["analysis_mode"],
            "raw_report_path": report["raw_report_path"],
            "json_report_path": report["json_report_path"],
            "error": report["error"],
        },
        "execution_policy": {
            "is_trade_order": False,
            "requires_human_review": True,
            "may_feed_factor_engine_directly": False,
        },
    }

