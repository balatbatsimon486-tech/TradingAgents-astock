"""Adapter from TradingAgents-astock results to Datang report contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from datang_extensions import __version__
from datang_extensions.adapters.json_schema import (
    STANDARD_REPORT_FIELDS,
    VALID_RESEARCH_SIGNALS,
    blank_report,
)
from datang_extensions.evaluation.signal_audit import audit_research_signal
from datang_extensions.utils.run_metadata import utc_now_iso
from datang_extensions.utils.safe_io import safe_filename_part, write_json_file, write_text_file

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "ticker", "code"),
    "trade_date": ("trade_date", "date", "as_of_date"),
    "llm_model": ("llm_model", "model"),
    "analysis_mode": ("analysis_mode", "mode"),
    "final_signal": ("final_signal", "signal", "recommendation", "decision"),
    "confidence": ("confidence", "score", "probability"),
    "risk_flags": ("risk_flags", "risks", "risk_tags"),
    "policy_summary": ("policy_summary", "policy", "policy_analysis"),
    "sentiment_summary": ("sentiment_summary", "sentiment", "sentiment_analysis"),
    "technical_summary": ("technical_summary", "technical", "technical_analysis"),
    "fundamental_summary": (
        "fundamental_summary",
        "fundamental",
        "fundamental_analysis",
    ),
    "hot_money_summary": ("hot_money_summary", "hot_money", "lhb_summary"),
    "lockup_summary": ("lockup_summary", "lockup", "unlock_risk", "lockup_risk"),
}

SIGNAL_ALIASES: dict[str, str] = {
    "buy": "research_buy",
    "strong buy": "research_buy",
    "bullish": "research_buy",
    "research_buy": "research_buy",
    "sell": "research_sell",
    "strong sell": "research_sell",
    "bearish": "research_sell",
    "research_sell": "research_sell",
    "hold": "research_hold",
    "neutral": "research_hold",
    "wait": "research_hold",
    "research_hold": "research_hold",
    "no_actionable_signal": "no_actionable_signal",
    "analysis_failed": "analysis_failed",
    "买入": "research_buy",
    "看多": "research_buy",
    "卖出": "research_sell",
    "看空": "research_sell",
    "持有": "research_hold",
    "观望": "research_hold",
    "中性": "research_hold",
}


def _as_mapping(raw_result: Any) -> dict[str, Any]:
    if raw_result is None:
        return {}
    if isinstance(raw_result, Mapping):
        return dict(raw_result)
    return {"raw_report": str(raw_result)}


def _first_value(raw: Mapping[str, Any], field: str) -> Any:
    for key in FIELD_ALIASES.get(field, (field,)):
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _string_value(raw: Mapping[str, Any], field: str) -> str:
    value = _first_value(raw, field)
    if value is None:
        return ""
    return str(value)


def _normalize_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= confidence <= 1:
        return confidence
    if 1 < confidence <= 100:
        return confidence / 100
    return None


def normalize_final_signal(value: Any, *, has_error: bool = False) -> str:
    if has_error:
        return "analysis_failed"
    if value is None:
        return "no_actionable_signal"

    signal = str(value).strip()
    if not signal:
        return "no_actionable_signal"

    normalized = SIGNAL_ALIASES.get(signal.lower(), SIGNAL_ALIASES.get(signal))
    if normalized in VALID_RESEARCH_SIGNALS:
        return normalized
    return "no_actionable_signal"


def _normalize_risk_flags(raw_flags: Any, final_signal: str, error: str | None) -> list[str]:
    if raw_flags is None:
        flags: list[str] = []
    elif isinstance(raw_flags, (list, tuple, set)):
        flags = [str(item) for item in raw_flags if str(item).strip()]
    else:
        flags = [str(raw_flags)]

    flags.extend(audit_research_signal(final_signal))
    if error:
        flags.append("external_dependency_failed")

    deduped: list[str] = []
    for flag in flags:
        if flag not in deduped:
            deduped.append(flag)
    return deduped


def _default_paths(
    *,
    symbol: str,
    trade_date: str,
    output_dir: str | Path | None,
    raw_report_path: str | Path | None,
    json_report_path: str | Path | None,
) -> tuple[Path, Path]:
    if raw_report_path and json_report_path:
        return Path(raw_report_path), Path(json_report_path)

    base_dir = Path(output_dir) if output_dir else Path("reports") / "tradingagents_astock"
    stem = "_".join(
        [
            safe_filename_part(symbol, "unknown_symbol"),
            safe_filename_part(trade_date, "unknown_date"),
            "research",
        ]
    )
    return Path(raw_report_path or base_dir / f"{stem}.md"), Path(
        json_report_path or base_dir / f"{stem}.json"
    )


def build_standard_report(
    raw_result: Any = None,
    *,
    symbol: str = "",
    trade_date: str = "",
    upstream_commit: str = "",
    datang_extension_version: str = __version__,
    run_time_utc: str | None = None,
    llm_model: str = "",
    analysis_mode: str = "",
    raw_report_path: str | Path = "",
    json_report_path: str | Path = "",
    error: str | Exception | None = None,
) -> dict[str, Any]:
    raw = _as_mapping(raw_result)
    error_text = (
        None
        if error is None
        else f"{type(error).__name__}: {error}"
        if isinstance(error, Exception)
        else str(error)
    )
    final_signal = normalize_final_signal(_first_value(raw, "final_signal"), has_error=bool(error_text))

    report = blank_report(
        symbol=symbol or _string_value(raw, "symbol"),
        trade_date=trade_date or _string_value(raw, "trade_date"),
        upstream_commit=upstream_commit or str(raw.get("upstream_commit", "")),
        datang_extension_version=datang_extension_version,
        run_time_utc=run_time_utc or utc_now_iso(),
        llm_model=llm_model or _string_value(raw, "llm_model"),
        analysis_mode=analysis_mode or _string_value(raw, "analysis_mode"),
        final_signal=final_signal,
        confidence=_normalize_confidence(_first_value(raw, "confidence")),
        policy_summary=_string_value(raw, "policy_summary"),
        sentiment_summary=_string_value(raw, "sentiment_summary"),
        technical_summary=_string_value(raw, "technical_summary"),
        fundamental_summary=_string_value(raw, "fundamental_summary"),
        hot_money_summary=_string_value(raw, "hot_money_summary"),
        lockup_summary=_string_value(raw, "lockup_summary"),
        raw_report_path=str(raw_report_path),
        json_report_path=str(json_report_path),
        error=error_text,
    )
    report["risk_flags"] = _normalize_risk_flags(_first_value(raw, "risk_flags"), final_signal, error_text)
    return {field: report[field] for field in STANDARD_REPORT_FIELDS}


def _raw_report_text(raw_result: Any) -> str:
    raw = _as_mapping(raw_result)
    for key in ("markdown", "raw_report", "report", "final_report", "analysis"):
        value = raw.get(key)
        if value:
            return str(value)
    if raw_result is not None and not isinstance(raw_result, Mapping):
        return str(raw_result)
    return ""


def render_markdown_report(report: Mapping[str, Any], raw_result: Any = None) -> str:
    raw_text = _raw_report_text(raw_result)
    sections = [
        f"# TradingAgents-astock Research Report: {report.get('symbol') or 'UNKNOWN'}",
        "",
        f"- trade_date: {report.get('trade_date') or ''}",
        f"- source: {report.get('source') or ''}",
        f"- upstream_commit: {report.get('upstream_commit') or ''}",
        f"- datang_extension_version: {report.get('datang_extension_version') or ''}",
        f"- run_time_utc: {report.get('run_time_utc') or ''}",
        f"- llm_model: {report.get('llm_model') or ''}",
        f"- analysis_mode: {report.get('analysis_mode') or ''}",
        f"- final_signal: {report.get('final_signal') or 'no_actionable_signal'}",
        f"- confidence: {report.get('confidence')}",
        f"- risk_flags: {', '.join(report.get('risk_flags') or [])}",
        "",
        "> Research-layer output only. This is not an executable trading signal.",
        "",
        "## Policy Summary",
        str(report.get("policy_summary") or ""),
        "",
        "## Sentiment Summary",
        str(report.get("sentiment_summary") or ""),
        "",
        "## Technical Summary",
        str(report.get("technical_summary") or ""),
        "",
        "## Fundamental Summary",
        str(report.get("fundamental_summary") or ""),
        "",
        "## Hot Money Summary",
        str(report.get("hot_money_summary") or ""),
        "",
        "## Lockup Summary",
        str(report.get("lockup_summary") or ""),
    ]

    if report.get("error"):
        sections.extend(["", "## Error", str(report["error"])])
    if raw_text:
        sections.extend(["", "## Raw TradingAgents-astock Output", raw_text])
    return "\n".join(sections).rstrip() + "\n"


def write_standard_outputs(
    raw_result: Any = None,
    *,
    symbol: str = "",
    trade_date: str = "",
    output_dir: str | Path | None = None,
    raw_report_path: str | Path | None = None,
    json_report_path: str | Path | None = None,
    upstream_commit: str = "",
    datang_extension_version: str = __version__,
    llm_model: str = "",
    analysis_mode: str = "",
    error: str | Exception | None = None,
) -> dict[str, Any]:
    raw = _as_mapping(raw_result)
    md_path, json_path = _default_paths(
        symbol=symbol or _string_value(raw, "symbol"),
        trade_date=trade_date or _string_value(raw, "trade_date"),
        output_dir=output_dir,
        raw_report_path=raw_report_path,
        json_report_path=json_report_path,
    )
    report = build_standard_report(
        raw_result,
        symbol=symbol,
        trade_date=trade_date,
        upstream_commit=upstream_commit,
        datang_extension_version=datang_extension_version,
        llm_model=llm_model,
        analysis_mode=analysis_mode,
        raw_report_path=md_path,
        json_report_path=json_path,
        error=error,
    )

    write_text_file(md_path, render_markdown_report(report, raw_result))
    write_json_file(json_path, report)
    return report


def run_analysis_with_fallback(
    analyzer: Callable[[], Any],
    *,
    symbol: str,
    trade_date: str,
    output_dir: str | Path | None = None,
    upstream_commit: str = "",
    llm_model: str = "",
    analysis_mode: str = "",
) -> dict[str, Any]:
    try:
        raw_result = analyzer()
    except Exception as exc:
        return write_standard_outputs(
            {},
            symbol=symbol,
            trade_date=trade_date,
            output_dir=output_dir,
            upstream_commit=upstream_commit,
            llm_model=llm_model,
            analysis_mode=analysis_mode,
            error=exc,
        )

    return write_standard_outputs(
        raw_result,
        symbol=symbol,
        trade_date=trade_date,
        output_dir=output_dir,
        upstream_commit=upstream_commit,
        llm_model=llm_model,
        analysis_mode=analysis_mode,
    )

