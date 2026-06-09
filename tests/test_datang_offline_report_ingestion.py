from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.adapters.json_schema import STANDARD_REPORT_FIELDS  # noqa: E402
from datang_extensions.ingestion.offline_report_ingestion import (  # noqa: E402
    DEFAULT_INPUT_PATH,
    ingest_offline_report,
    load_offline_input,
)


def _write_input(tmp_path: Path, **overrides: object) -> Path:
    payload = load_offline_input(DEFAULT_INPUT_PATH)
    payload.update(overrides)
    input_path = tmp_path / "offline_input.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return input_path


def test_offline_sample_generates_markdown_json_and_metadata(tmp_path: Path) -> None:
    result = ingest_offline_report(output_dir=tmp_path)

    markdown_path = result["markdown_path"]
    json_path = result["json_path"]
    metadata_path = result["metadata_path"]

    assert markdown_path.exists()
    assert markdown_path.suffix == ".md"
    assert json_path.exists()
    assert json_path.suffix == ".json"
    assert metadata_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert list(result["report"]) == list(STANDARD_REPORT_FIELDS)
    assert set(report) == set(STANDARD_REPORT_FIELDS)
    assert metadata["llm_called"] is False
    assert metadata["market_data_called"] is False
    assert metadata["tushare_called"] is False
    assert metadata["trade_order_created"] is False


def test_buy_hold_sell_are_research_signals_only(tmp_path: Path) -> None:
    cases = {
        "BUY": "research_buy",
        "HOLD": "research_hold",
        "SELL": "research_sell",
    }

    for raw_signal, expected in cases.items():
        input_path = _write_input(tmp_path, final_signal=raw_signal)
        result = ingest_offline_report(input_path, tmp_path / raw_signal.lower())

        assert result["report"]["final_signal"] == expected
        assert "not_validated_trade_signal" in result["report"]["risk_flags"]
        assert result["metadata"]["trade_order_created"] is False


def test_blank_final_signal_is_not_tradeable(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path, final_signal="")
    result = ingest_offline_report(input_path, tmp_path / "blank_signal")

    assert result["report"]["final_signal"] in {"no_actionable_signal", "analysis_failed"}
    assert "research_buy" != result["report"]["final_signal"]
    assert "research_sell" != result["report"]["final_signal"]


def test_missing_required_fields_sets_structured_error(tmp_path: Path) -> None:
    input_path = tmp_path / "missing_fields.json"
    input_path.write_text(json.dumps({"symbol": "000001.SZ"}), encoding="utf-8")

    result = ingest_offline_report(input_path, tmp_path / "missing_fields")

    assert result["report"]["error"]
    assert "missing required fields" in result["report"]["error"]
    assert list(result["report"]) == list(STANDARD_REPORT_FIELDS)


def test_ingestion_does_not_call_network(monkeypatch, tmp_path: Path) -> None:
    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in offline smoke tests")

    monkeypatch.setattr(socket, "socket", fail_socket)
    result = ingest_offline_report(output_dir=tmp_path)

    assert result["metadata"]["llm_called"] is False
    assert result["metadata"]["market_data_called"] is False


def test_sources_do_not_reference_tushare_or_hardcoded_absolute_paths() -> None:
    source_paths = [
        PROJECT_ROOT / "datang_extensions" / "ingestion" / "offline_report_ingestion.py",
        PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_report_smoke.py",
    ]
    forbidden_paths = ("C:\\", "D:\\", "/Users/", "/home/", "Desktop")
    forbidden_tushare_calls = ("import tushare", "from tushare", "tushare.")

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        lowered = source.lower()
        assert not any(fragment in source for fragment in forbidden_paths)
        assert not any(fragment in lowered for fragment in forbidden_tushare_calls)


def test_default_offline_smoke_output_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "reports/tradingagents_astock/offline_smoke/sample.json"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
