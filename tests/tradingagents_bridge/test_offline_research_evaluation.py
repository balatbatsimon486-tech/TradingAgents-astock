from __future__ import annotations

import builtins
import json
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.evaluation.offline_research_evaluator import (  # noqa: E402
    CRITICAL_CHECKS,
    evaluate_research_artifact,
)
from datang_extensions.evaluation.offline_research_pipeline import (  # noqa: E402
    run_offline_research_evaluation,
)

FIXTURE_PATH = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "m2a_valid_snapshot.json"


def _copy_fixture(tmp_path: Path, name: str = "snapshot.json") -> Path:
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    snapshot_path = snapshot_dir / name
    snapshot_path.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return snapshot_path


def _load_snapshot(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_snapshot(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _run_pipeline(snapshot_path: Path, tmp_path: Path, case_id: str = "synthetic-policy-event-001") -> dict:
    return run_offline_research_evaluation(
        snapshot_path,
        allowed_root=snapshot_path.parent,
        output_root=tmp_path / "outputs",
        case_id=case_id,
    )


def test_valid_synthetic_snapshot_runs_full_offline_chain(tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)

    result = _run_pipeline(snapshot_path, tmp_path)

    assert result["passed"] is True
    assert result["score"] == 100
    assert {check["name"] for check in result["checks"]} >= set(CRITICAL_CHECKS)
    assert all(check["passed"] for check in result["checks"] if check["severity"] == "critical")
    assert Path(result["artifact_summary"]["json_path"]).exists()
    assert Path(result["artifact_summary"]["markdown_path"]).exists()
    assert result["artifact_summary"]["research_only"] is True
    assert result["artifact_summary"]["not_a_trading_signal"] is True
    assert result["artifact_summary"]["no_trading_decision"] is True
    assert result["lineage"]["snapshot_id"] == "synthetic-m2a-snapshot-001"
    assert result["lineage"]["source"] == "datang_quant_platform"
    assert result["lineage"]["schema_version"] == "1.0"
    assert result["lineage"]["as_of_time"] == "2026-06-28T09:00:00+00:00"
    assert len(result["lineage"]["snapshot_hash"]) == 64
    assert len(result["lineage"]["raw_artifact_hash"]) == 64
    assert len(result["lineage"]["normalized_artifact_hash"]) == 64
    assert all(value is False for value in result["external_calls"].values())
    assert result["errors"] == []


def test_pipeline_calls_stage3a_reader_with_allowed_root(monkeypatch, tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)
    calls: dict[str, object] = {}

    from datang_extensions.ingestion.research_snapshot_reader import read_research_snapshot

    def recording_reader(snapshot_arg: object, *, allowed_root: object, **kwargs: object) -> dict:
        calls["snapshot_path"] = snapshot_arg
        calls["allowed_root"] = allowed_root
        return read_research_snapshot(snapshot_arg, allowed_root=allowed_root, **kwargs)

    monkeypatch.setattr(
        "datang_extensions.evaluation.offline_research_pipeline.read_research_snapshot",
        recording_reader,
    )

    result = _run_pipeline(snapshot_path, tmp_path)

    assert result["passed"] is True
    assert calls["snapshot_path"] == snapshot_path
    assert calls["allowed_root"] == snapshot_path.parent


def test_evaluator_rejects_forbidden_trading_and_credential_fields(tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)
    result = _run_pipeline(snapshot_path, tmp_path)
    artifact = json.loads(Path(result["artifact_summary"]["json_path"]).read_text(encoding="utf-8"))

    forbidden = dict(artifact)
    forbidden["nested"] = {"order_size": 100}
    rejected = evaluate_research_artifact(
        artifact=forbidden,
        markdown_path=Path(result["artifact_summary"]["markdown_path"]),
        json_path=Path(result["artifact_summary"]["json_path"]),
        snapshot_context=result["snapshot_context"],
        snapshot_hash=result["lineage"]["snapshot_hash"],
        case_id="synthetic-policy-event-001",
    )
    assert rejected["passed"] is False
    assert any(error["code"] == "forbidden_trading_field_detected" for error in rejected["errors"])

    credential = dict(artifact)
    credential["nested"] = {"api_key": "synthetic-negative-fixture"}
    rejected = evaluate_research_artifact(
        artifact=credential,
        markdown_path=Path(result["artifact_summary"]["markdown_path"]),
        json_path=Path(result["artifact_summary"]["json_path"]),
        snapshot_context=result["snapshot_context"],
        snapshot_hash=result["lineage"]["snapshot_hash"],
        case_id="synthetic-policy-event-001",
    )
    assert rejected["passed"] is False
    assert any(error["code"] == "credential_field_detected" for error in rejected["errors"])


def test_snapshot_failures_stop_before_artifact_generation(monkeypatch, tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)

    def fail_ingestion(*args: object, **kwargs: object) -> object:
        raise AssertionError("Stage 2 ingestion must not run after rejected snapshot")

    monkeypatch.setattr(
        "datang_extensions.evaluation.offline_research_pipeline.ingest_offline_report",
        fail_ingestion,
    )

    for mutate in ("qa", "schema", "path"):
        candidate = snapshot_path
        allowed_root = snapshot_path.parent
        if mutate == "qa":
            payload = _load_snapshot(snapshot_path)
            payload["data_quality"]["passed"] = False
            candidate = tmp_path / "snapshots" / "qa_failed.json"
            _write_snapshot(candidate, payload)
        elif mutate == "schema":
            payload = _load_snapshot(snapshot_path)
            payload["schema_version"] = "9.9"
            candidate = tmp_path / "snapshots" / "bad_schema.json"
            _write_snapshot(candidate, payload)
        else:
            outside = tmp_path / "outside"
            outside.mkdir()
            candidate = outside / "outside.json"
            candidate.write_text(snapshot_path.read_text(encoding="utf-8"), encoding="utf-8")

        result = run_offline_research_evaluation(
            candidate,
            allowed_root=allowed_root,
            output_root=tmp_path / f"out_{mutate}",
            case_id=f"case_{mutate}",
        )

        assert result["passed"] is False
        assert result["errors"]
        assert result["errors"][0]["code"] == "snapshot_rejected"
        assert not (tmp_path / f"out_{mutate}" / "artifacts").exists()


def test_missing_stage2_required_field_is_structured_failure(tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)
    payload = _load_snapshot(snapshot_path)
    payload.pop("research_opinion")
    _write_snapshot(snapshot_path, payload)

    result = _run_pipeline(snapshot_path, tmp_path)

    assert result["passed"] is False
    assert any(error["code"] == "stage2_input_mapping_failed" for error in result["errors"])


def test_repeated_runs_have_stable_normalized_hash_and_preserve_input(tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)
    before_hash = snapshot_path.read_bytes()
    before_mtime = snapshot_path.stat().st_mtime_ns

    first = _run_pipeline(snapshot_path, tmp_path / "first")
    second = _run_pipeline(snapshot_path, tmp_path / "second")

    assert first["passed"] is True
    assert second["passed"] is True
    assert first["lineage"]["normalized_artifact_hash"] == second["lineage"]["normalized_artifact_hash"]
    assert first["artifact_summary"]["excluded_volatile_fields"]
    assert snapshot_path.read_bytes() == before_hash
    assert snapshot_path.stat().st_mtime_ns == before_mtime

    tracked = subprocess.run(
        ["git", "ls-files", "data/exports"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout.strip() == ""
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_evaluation").exists()


def test_external_calls_are_blocked_by_design_and_monkeypatch(monkeypatch, tmp_path: Path) -> None:
    snapshot_path = _copy_fixture(tmp_path)

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in M2A")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = ("openai", "anthropic", "google_genai", "tushare", "qlib", "requests", "httpx", "websocket")
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = _run_pipeline(snapshot_path, tmp_path)

    assert result["passed"] is True
    assert result["external_calls"] == {
        "llm_called": False,
        "network_called": False,
        "market_data_called": False,
        "tushare_called": False,
        "qlib_called": False,
        "broker_called": False,
    }
