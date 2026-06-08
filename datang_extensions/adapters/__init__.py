"""Adapters for Datang's TradingAgents-astock extension layer."""

from __future__ import annotations

from .astock_report_adapter import (
    build_standard_report,
    normalize_final_signal,
    render_markdown_report,
    run_analysis_with_fallback,
    write_standard_outputs,
)
from .quant_platform_adapter import to_quant_platform_payload

__all__ = [
    "build_standard_report",
    "normalize_final_signal",
    "render_markdown_report",
    "run_analysis_with_fallback",
    "to_quant_platform_payload",
    "write_standard_outputs",
]

