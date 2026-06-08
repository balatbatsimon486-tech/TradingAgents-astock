"""Standard Datang JSON contract for TradingAgents-astock research reports."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

STANDARD_REPORT_FIELDS: tuple[str, ...] = (
    "symbol",
    "trade_date",
    "source",
    "upstream_commit",
    "datang_extension_version",
    "run_time_utc",
    "llm_model",
    "analysis_mode",
    "final_signal",
    "confidence",
    "risk_flags",
    "policy_summary",
    "sentiment_summary",
    "technical_summary",
    "fundamental_summary",
    "hot_money_summary",
    "lockup_summary",
    "raw_report_path",
    "json_report_path",
    "error",
)

VALID_RESEARCH_SIGNALS = frozenset(
    {
        "research_buy",
        "research_hold",
        "research_sell",
        "no_actionable_signal",
        "analysis_failed",
    }
)

DEFAULT_REPORT: dict[str, Any] = {
    "symbol": "",
    "trade_date": "",
    "source": "tradingagents-astock",
    "upstream_commit": "",
    "datang_extension_version": "",
    "run_time_utc": "",
    "llm_model": "",
    "analysis_mode": "",
    "final_signal": "no_actionable_signal",
    "confidence": None,
    "risk_flags": [],
    "policy_summary": "",
    "sentiment_summary": "",
    "technical_summary": "",
    "fundamental_summary": "",
    "hot_money_summary": "",
    "lockup_summary": "",
    "raw_report_path": "",
    "json_report_path": "",
    "error": None,
}

STANDARD_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": list(STANDARD_REPORT_FIELDS),
    "additionalProperties": False,
    "properties": {
        "symbol": {"type": "string"},
        "trade_date": {"type": "string"},
        "source": {"type": "string", "const": "tradingagents-astock"},
        "upstream_commit": {"type": "string"},
        "datang_extension_version": {"type": "string"},
        "run_time_utc": {"type": "string"},
        "llm_model": {"type": "string"},
        "analysis_mode": {"type": "string"},
        "final_signal": {"type": "string", "enum": sorted(VALID_RESEARCH_SIGNALS)},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "policy_summary": {"type": "string"},
        "sentiment_summary": {"type": "string"},
        "technical_summary": {"type": "string"},
        "fundamental_summary": {"type": "string"},
        "hot_money_summary": {"type": "string"},
        "lockup_summary": {"type": "string"},
        "raw_report_path": {"type": "string"},
        "json_report_path": {"type": "string"},
        "error": {"type": ["string", "null"]},
    },
}


def blank_report(**overrides: Any) -> dict[str, Any]:
    """Return a report with every standard field present."""

    report = deepcopy(DEFAULT_REPORT)
    for key, value in overrides.items():
        if key in report:
            report[key] = value
    return report


def missing_standard_fields(report: Mapping[str, Any]) -> list[str]:
    """Return standard fields absent from a report mapping."""

    return [field for field in STANDARD_REPORT_FIELDS if field not in report]


def has_only_standard_fields(report: Mapping[str, Any]) -> bool:
    """Return whether the report has exactly the standard field set."""

    return set(report) == set(STANDARD_REPORT_FIELDS)

