from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.ingestion.research_snapshot_reader import (  # noqa: E402
    read_research_snapshot,
)


def _valid_snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "synthetic-snapshot-001",
        "schema_version": "1.0",
        "source": "datang_quant_platform",
        "as_of_time": "2026-06-28T09:00:00+00:00",
        "generated_at": "2026-06-28T09:05:00+00:00",
        "symbol": "000001.SZ",
        "trade_date": "2024-01-31",
        "source_platform": "datang_quant_platform",
        "data_source": "offline_test_fixture",
        "snapshot_version": "1.0",
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
            "errors": [],
            "warnings": [],
        },
        "warnings": ["synthetic snapshot for reader test"],
        "errors": [],
    }


def _write_snapshot(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _read_snapshot(snapshot_path: Path, allowed_root: Path) -> dict[str, object]:
    return read_research_snapshot(snapshot_path, allowed_root=allowed_root)


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

    result = _read_snapshot(snapshot_path, tmp_path)

    assert result["passed"] is True
    assert result["ok"] is True
    context = result["context"]
    assert context["read_only"] is True
    assert context["source_platform"] == "datang_quant_platform"
    assert context["allowed_usage"] == "research_context_only"
    assert context["no_trading_decision"] is True
    assert context["snapshot_id"] == "synthetic-snapshot-001"
    assert context["schema_version"] == "1.0"
    assert context["source"] == "datang_quant_platform"
    assert context["as_of_time"] == "2026-06-28T09:00:00+00:00"
    assert context["warnings"] == ["synthetic snapshot for reader test"]
    assert context["errors"] == []
    assert context["data_quality"] == {
        "passed": True,
        "missing_rows": 0,
        "errors": [],
        "warnings": [],
    }


def test_missing_allowed_root_fails_closed(tmp_path: Path) -> None:
    snapshot_path = _write_snapshot(tmp_path, _valid_snapshot())

    result = read_research_snapshot(snapshot_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_allowed_root"


def test_missing_snapshot_file_returns_structured_error(tmp_path: Path) -> None:
    result = _read_snapshot(tmp_path / "missing.json", tmp_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "missing_snapshot_file"


def test_invalid_json_returns_structured_error(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "bad.json"
    snapshot_path.write_text("{not valid json", encoding="utf-8")

    result = _read_snapshot(snapshot_path, tmp_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_json"


def test_missing_required_fields_rejected(tmp_path: Path) -> None:
    payload = _valid_snapshot()
    payload.pop("symbol")
    snapshot_path = _write_snapshot(tmp_path, payload)

    result = _read_snapshot(snapshot_path, tmp_path)

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_snapshot_schema"
    assert result["error"]["field"] == "symbol"


def test_required_identity_fields_are_rejected_when_missing_or_invalid(tmp_path: Path) -> None:
    cases = [
        ("snapshot_id", None, "invalid_snapshot_schema"),
        ("snapshot_id", "", "invalid_snapshot_schema"),
        ("snapshot_id", 123, "invalid_snapshot_schema"),
        ("schema_version", None, "invalid_snapshot_schema"),
        ("schema_version", "", "unsupported_schema_version"),
        ("source", None, "invalid_snapshot_schema"),
        ("source", "", "invalid_snapshot_schema"),
        ("as_of_time", None, "invalid_snapshot_schema"),
        ("data_quality", None, "invalid_snapshot_schema"),
        ("data_quality", "passed", "invalid_snapshot_schema"),
    ]

    for field, value, expected_code in cases:
        payload = _valid_snapshot()
        if value is None:
            payload.pop(field)
        else:
            payload[field] = value
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == expected_code
        assert result["error"]["field"] == field


def test_schema_version_allowlist_and_snapshot_version_compatibility(tmp_path: Path) -> None:
    valid = _valid_snapshot()
    assert _read_snapshot(_write_snapshot(tmp_path, valid), tmp_path)["ok"] is True

    for version in ("0.9", "2.0", ""):
        payload = _valid_snapshot()
        payload["schema_version"] = version
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "unsupported_schema_version"
        assert result["error"]["field"] == "schema_version"

    payload = _valid_snapshot()
    payload["schema_version"] = 1.0
    result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_snapshot_schema"

    payload = _valid_snapshot()
    payload["snapshot_version"] = "1.0"
    assert _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)["ok"] is True

    payload = _valid_snapshot()
    payload["snapshot_version"] = "0.9"
    result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "unsupported_schema_version"
    assert result["error"]["field"] == "snapshot_version"


def test_data_quality_must_pass_strictly_and_have_no_blockers(tmp_path: Path) -> None:
    for value in (False, None, 0, 1, "true", "false"):
        payload = _valid_snapshot()
        payload["data_quality"] = deepcopy(payload["data_quality"])
        payload["data_quality"]["passed"] = value
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "data_quality_not_passed"
        assert result["error"]["field"] == "data_quality.passed"

    for field in ("errors", "blockers", "critical_issues"):
        payload = _valid_snapshot()
        payload["data_quality"] = deepcopy(payload["data_quality"])
        payload["data_quality"][field] = ["synthetic blocker"]
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "data_quality_not_passed"
        assert result["error"]["field"] == f"data_quality.{field}"

    payload = _valid_snapshot()
    payload["data_quality"] = {"errors": []}
    result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "data_quality_not_passed"


def test_as_of_time_and_generated_at_require_timezone_aware_iso8601(tmp_path: Path) -> None:
    for as_of_time in ("2026-06-28T09:00:00Z", "2026-06-28T17:00:00+08:00"):
        payload = _valid_snapshot()
        payload["as_of_time"] = as_of_time
        payload["generated_at"] = "2026-06-28T10:00:00Z"
        assert _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)["ok"] is True

    for value in ("2026-06-28T09:00:00", "not-a-time", "", 123):
        payload = _valid_snapshot()
        payload["as_of_time"] = value
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_as_of_time"

    for generated_at in ("not-a-time", "2026-06-28T09:05:00", 123):
        payload = _valid_snapshot()
        payload["generated_at"] = generated_at
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_generated_at"

    payload = _valid_snapshot()
    payload["generated_at"] = "2026-06-28T08:59:59+00:00"
    result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_generated_at"


def test_forbidden_trading_fields_rejected(tmp_path: Path) -> None:
    # These field names are negative-test fixtures and must be rejected.
    for field in ("signal", "recommendation", "expected_return"):
        payload = _valid_snapshot()
        payload[field] = "forbidden"
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

        assert result["ok"] is False
        assert result["error"]["code"] == "forbidden_trading_field"
        assert result["error"]["field"] == field


def test_credential_fields_rejected(tmp_path: Path) -> None:
    # These field names are negative-test fixtures and must be rejected.
    for field in ("token", "api_key", "secret", "password"):
        payload = _valid_snapshot()
        payload[field] = "forbidden"
        result = _read_snapshot(_write_snapshot(tmp_path, payload), tmp_path)

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
    result = _read_snapshot(snapshot_path, tmp_path)
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
    result = _read_snapshot(snapshot_path, tmp_path)

    context_keys = _flatten_keys(result["context"])

    assert not {"signal", "recommendation", "strategy", "backtest", "expected_return"}.intersection(
        context_keys
    )
    assert not {"token", "api_key", "secret", "password"}.intersection(context_keys)


def test_path_security_rejects_unsafe_paths_and_non_json_inputs(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    inside_snapshot = _write_snapshot(allowed_root, _valid_snapshot())

    assert _read_snapshot(inside_snapshot, allowed_root)["ok"] is True

    outside_snapshot = _write_snapshot(outside_root, _valid_snapshot())
    result = _read_snapshot(outside_snapshot, allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "path_outside_allowed_root"

    traversal_path = allowed_root / ".." / "outside" / "snapshot.json"
    result = _read_snapshot(traversal_path, allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "path_outside_allowed_root"

    result = _read_snapshot(Path("C:/Windows/system32/drivers/etc/hosts"), allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] in {"path_outside_allowed_root", "missing_snapshot_file"}

    result = _read_snapshot(allowed_root / "missing.json", allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "missing_snapshot_file"

    result = _read_snapshot(allowed_root, allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "snapshot_path_not_file"

    text_path = allowed_root / "snapshot.txt"
    text_path.write_text("{}", encoding="utf-8")
    result = _read_snapshot(text_path, allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_snapshot_extension"

    malformed_path = allowed_root / "malformed.json"
    malformed_path.write_text("{bad", encoding="utf-8")
    result = _read_snapshot(malformed_path, allowed_root)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_json"


def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    if os.name == "nt" and not hasattr(os, "symlink"):
        import pytest

        pytest.skip("Windows environment does not expose os.symlink")

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_snapshot = _write_snapshot(outside_root, _valid_snapshot())
    link_path = allowed_root / "linked.json"
    try:
        link_path.symlink_to(outside_snapshot)
    except (OSError, NotImplementedError) as exc:
        import pytest

        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    result = _read_snapshot(link_path, allowed_root)

    assert result["ok"] is False
    assert result["error"]["code"] == "path_outside_allowed_root"


def test_reader_is_readonly_and_does_not_create_outputs(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    snapshot_path = _write_snapshot(allowed_root, _valid_snapshot())
    before_hash = sha256(snapshot_path.read_bytes()).hexdigest()
    before_mtime = snapshot_path.stat().st_mtime_ns

    result = _read_snapshot(snapshot_path, allowed_root)

    assert result["ok"] is True
    assert sha256(snapshot_path.read_bytes()).hexdigest() == before_hash
    assert snapshot_path.stat().st_mtime_ns == before_mtime
    assert sorted(path.name for path in allowed_root.iterdir()) == ["snapshot.json"]

    context_keys = _flatten_keys(result["context"])
    assert not {"order_size", "position_size", "target_weight", "trade_order"}.intersection(
        context_keys
    )
