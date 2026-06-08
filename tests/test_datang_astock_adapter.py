from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.adapters.astock_report_adapter import (  # noqa: E402
    build_standard_report,
    run_analysis_with_fallback,
    write_standard_outputs,
)
from datang_extensions.adapters.json_schema import STANDARD_REPORT_FIELDS  # noqa: E402
from datang_extensions.adapters.quant_platform_adapter import to_quant_platform_payload  # noqa: E402


def _sample_raw_result() -> dict[str, object]:
    return {
        "final_signal": "BUY",
        "confidence": 0.72,
        "risk_flags": ["policy_uncertainty"],
        "policy_summary": "Policy view for unit test.",
        "sentiment_summary": "Sentiment view for unit test.",
        "technical_summary": "Technical view for unit test.",
        "fundamental_summary": "Fundamental view for unit test.",
        "hot_money_summary": "Hot-money view for unit test.",
        "lockup_summary": "Lockup view for unit test.",
        "raw_report": "Original multi-agent report body.",
    }


def test_standard_json_fields_are_complete(tmp_path: Path) -> None:
    report = write_standard_outputs(
        _sample_raw_result(),
        symbol="600519",
        trade_date="2026-06-08",
        output_dir=tmp_path,
        upstream_commit="abc123",
        llm_model="fake-llm",
        analysis_mode="unit",
    )

    assert list(report) == list(STANDARD_REPORT_FIELDS)
    assert set(report) == set(STANDARD_REPORT_FIELDS)
    assert report["source"] == "tradingagents-astock"
    assert report["final_signal"] == "research_buy"
    assert "not_validated_trade_signal" in report["risk_flags"]


def test_markdown_and_json_report_paths_can_be_generated(tmp_path: Path) -> None:
    report = write_standard_outputs(
        _sample_raw_result(),
        symbol="000001",
        trade_date="2026-06-08",
        output_dir=tmp_path,
    )

    markdown_path = Path(report["raw_report_path"])
    json_path = Path(report["json_report_path"])

    assert markdown_path.exists()
    assert markdown_path.suffix == ".md"
    assert json_path.exists()
    assert json_path.suffix == ".json"

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(saved) == set(STANDARD_REPORT_FIELDS)


def test_external_failure_sets_error_without_crashing(tmp_path: Path) -> None:
    def failing_analyzer() -> dict[str, object]:
        raise RuntimeError("LLM provider unavailable")

    report = run_analysis_with_fallback(
        failing_analyzer,
        symbol="600000",
        trade_date="2026-06-08",
        output_dir=tmp_path,
        llm_model="fake-llm",
        analysis_mode="unit",
    )

    assert report["error"]
    assert "LLM provider unavailable" in report["error"]
    assert report["final_signal"] == "analysis_failed"
    assert Path(report["raw_report_path"]).exists()
    assert Path(report["json_report_path"]).exists()


def test_empty_or_abnormal_final_signal_is_not_tradeable() -> None:
    for raw_signal in ("", None, "certain_alpha"):
        report = build_standard_report({"final_signal": raw_signal})
        assert report["final_signal"] == "no_actionable_signal"
        assert "untrusted_or_missing_final_signal" in report["risk_flags"]

        payload = to_quant_platform_payload(report)
        assert payload["execution_policy"]["is_trade_order"] is False
        assert payload["execution_policy"]["may_feed_factor_engine_directly"] is False


def test_extension_code_does_not_use_hardcoded_absolute_paths() -> None:
    forbidden_fragments = ("C:\\", "D:\\", "/Users/", "/home/", "Desktop")

    for source_path in (PROJECT_ROOT / "datang_extensions").rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        assert not any(fragment in source for fragment in forbidden_fragments)


def test_windows_path_unsafe_symbol_parts_are_sanitized(tmp_path: Path) -> None:
    report = write_standard_outputs(
        _sample_raw_result(),
        symbol='SH:600519/A*TEST',
        trade_date="2026/06/08",
        output_dir=tmp_path,
    )

    markdown_name = Path(report["raw_report_path"]).name
    json_name = Path(report["json_report_path"]).name
    unsafe_chars = set('<>:"/\\|?*')

    assert not unsafe_chars.intersection(markdown_name)
    assert not unsafe_chars.intersection(json_name)
    assert Path(report["raw_report_path"]).exists()
    assert Path(report["json_report_path"]).exists()
