from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.ingestion.research_snapshot_reader import (  # noqa: E402
    read_research_snapshot,
)


def _valid_snapshot() -> dict[str, object]:
    return {
        "symbol": "000001.SZ",
        "trade_date": "2024-01-31",
        "source_platform": "datang_quant_platform",
        "data_source": "offline_test_fixture",
        "snapshot_version": "0.1",
        "created_at_utc": "2026-06-09T00:00:00Z",
        "price_window": {
            "start": "2024-01-02",
            "end": "2024-01-31",
            "rows": 20,
        },
        "latest_ohlcv": {
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 1000000,
        },
        "adj_factor": 1.0,
        "stock_basic": {
            "name": "Synthetic Bank",
            "exchange": "SZSE",
        },
        "data_quality": {
            "passed": True,
            "missing_rows": 0,
        },
        "warnings": ["synthetic snapshot for reader test"],
        "errors": [],
    }


def _write_snapshot(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _flatten_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(_flatten_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.update(_flatten_keys(item))
    return keys


def test_read_valid_snapshot_returns_readonly_context(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path, _valid_snapshot())

    result = read_research_snapshot(snapshot_path)

    assert result["passed"] is True
    assert result["ok"] is True
    context = result["context"]
    assert context["read_only"] is True
    assert context["source_platform"] == "datang_quant_platform"
    assert context["allowed_usage"] == "research_context_only"
    assert context["no_trading_decision"] is True
    assert context["warnings"] == ["synthetic snapshot for reader test"]
    assert context["errors"] == []
    assert context["data_quality"] == {"passed": True, "missing_rows": 0}


def test_missing_snapshot_file_returns_structured_error(tmp_path: Path) -> None:
    result = read_research_snapshot(tmp_path / "missing.json")

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_snapshot_file"


def test_invalid_json_returns_structured_error(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "bad.json"
    snapshot_path.write_text("{not valid json", encoding="utf-8")

    result = read_research_snapshot(snapshot_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_json"


def test_missing_required_fields_rejected(tmp_path: Path) -> None:
    payload = _valid_snapshot()
    payload.pop("symbol")
    snapshot_path = _write_snapshot(tmp_path, payload)

    result = read_research_snapshot(snapshot_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_snapshot_schema"
    assert result["error"]["field"] == "symbol"


def test_forbidden_trading_fields_rejected(tmp_path: Path) -> None:
    # These field names are negative-test fixtures and must be rejected.
    for field in ("signal", "recommendation", "expected_return"):
        payload = _valid_snapshot()
        payload[field] = "forbidden"
        result = read_research_snapshot(_write_snapshot(tmp_path, payload))

        assert result["ok"] is False
        assert result["error"]["code"] == "forbidden_trading_field"
        assert result["error"]["field"] == field


def test_credential_fields_rejected(tmp_path: Path) -> None:
    # These field names are negative-test fixtures and must be rejected.
    for field in ("token", "api_key", "secret", "password"):
        payload = _valid_snapshot()
        payload[field] = "forbidden"
        result = read_research_snapshot(_write_snapshot(tmp_path, payload))

        assert result["ok"] is False
        assert result["error"]["code"] == "credential_field_detected"
        assert result["error"]["field"] == field


def test_reader_does_not_import_tushare_or_read_token() -> None:
    source_path = PROJECT_ROOT / "datang_extensions" / "ingestion" / "research_snapshot_reader.py"
    source = source_path.read_text(encoding="utf-8")
    forbidden = (
        "import " + "tushare",
        "pro" + "_api",
        "TUSHARE" + "_FAST_TOKEN",
        "TUSHARE" + "_TOKEN",
        "os" + ".environ",
        "get" + "env",
    )

    assert not any(fragment in source for fragment in forbidden)


def test_no_real_snapshot_json_tracked_or_created_by_tests(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path, _valid_snapshot())
    result = read_research_snapshot(snapshot_path)
    assert result["ok"] is True

    tracked = subprocess.run(
        ["git", "ls-files", "data/exports"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert tracked.stdout.strip() == ""


def test_context_excludes_forbidden_decision_and_credential_keys(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path, _valid_snapshot())
    result = read_research_snapshot(snapshot_path)

    context_keys = _flatten_keys(result["context"])

    assert not {"signal", "recommendation", "strategy", "backtest", "expected_return"}.intersection(
        context_keys
    )
    assert not {"token", "api_key", "secret", "password"}.intersection(context_keys)
