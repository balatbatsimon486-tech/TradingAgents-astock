"""Guardrails for treating AI research output as non-executable evidence."""

from __future__ import annotations

from datang_extensions.adapters.json_schema import VALID_RESEARCH_SIGNALS

RESEARCH_SIGNAL_FLAG = "not_validated_trade_signal"
UNTRUSTED_SIGNAL_FLAG = "untrusted_or_missing_final_signal"
FAILED_ANALYSIS_FLAG = "analysis_failed"


def audit_research_signal(final_signal: str) -> list[str]:
    if final_signal == "analysis_failed":
        return [FAILED_ANALYSIS_FLAG, RESEARCH_SIGNAL_FLAG]
    if final_signal not in VALID_RESEARCH_SIGNALS or final_signal == "no_actionable_signal":
        return [UNTRUSTED_SIGNAL_FLAG, RESEARCH_SIGNAL_FLAG]
    return [RESEARCH_SIGNAL_FLAG]


def is_executable_trade_signal(final_signal: str) -> bool:
    """AI research signals are never executable by this adapter."""

    return False

