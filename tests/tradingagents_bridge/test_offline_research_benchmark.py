from __future__ import annotations

import builtins
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.evaluation.offline_research_benchmark import (  # noqa: E402
    BENCHMARK_STAGE,
    BenchmarkManifestError,
    build_expected_baseline,
    load_benchmark_manifest,
    run_offline_research_benchmark,
)
from datang_extensions.evaluation.offline_research_evaluator import (  # noqa: E402
    CRITICAL_CHECKS,
)

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "m2b"
MANIFEST_PATH = FIXTURES_ROOT / "benchmark_manifest.json"
BASELINE_PATH = FIXTURES_ROOT / "expected_baseline.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_research_benchmark.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _copy_fixture_tree(tmp_path: Path) -> Path:
    target = tmp_path / "fixtures"
    for source in FIXTURES_ROOT.rglob("*"):
        relative = source.relative_to(FIXTURES_ROOT)
        destination = target / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
    return target


def _run(tmp_path: Path, fixtures_root: Path | None = None, **kwargs: Any) -> dict[str, Any]:
    root = fixtures_root or FIXTURES_ROOT
    return run_offline_research_benchmark(
        root / "benchmark_manifest.json",
        fixtures_root=root,
        output_root=tmp_path / "outputs",
        **kwargs,
    )


def _case(result: dict[str, Any], case_id: str) -> dict[str, Any]:
    for item in result["case_results"]:
        if item["case_id"] == case_id:
            return item
    raise AssertionError(f"case not found: {case_id}")


def _error_codes(result: dict[str, Any]) -> list[str]:
    return [error.get("code", "") for error in result.get("errors", [])]


def test_manifest_loader_accepts_fixed_manifest_and_rejects_unsafe_variants(tmp_path: Path) -> None:
    manifest = load_benchmark_manifest(MANIFEST_PATH, fixtures_root=FIXTURES_ROOT)
    assert manifest["benchmark_id"] == "tradingagents-m2b-offline-benchmark"
    assert manifest["benchmark_version"] == "1.0"
    assert manifest["repeat"] == 2
    assert len(manifest["cases"]) >= 12
    assert [case["case_id"] for case in manifest["cases"]][:3] == [
        "valid-complete-001",
        "valid-conflicting-evidence-001",
        "valid-insufficient-evidence-001",
    ]

    invalid_cases: list[tuple[str, Any, str]] = [
        ("missing benchmark id", lambda data: data.pop("benchmark_id"), "missing_benchmark_id"),
        ("unsupported version", lambda data: data.update({"benchmark_version": "9.9"}), "unsupported_benchmark_version"),
        ("duplicate case id", lambda data: data["cases"].append(dict(data["cases"][0])), "duplicate_case_id"),
        ("absolute fixture", lambda data: data["cases"][0].update({"fixture": str(MANIFEST_PATH)}), "unsafe_fixture_path"),
        ("parent traversal", lambda data: data["cases"][0].update({"fixture": "../m2a_valid_snapshot.json"}), "unsafe_fixture_path"),
        ("unknown status", lambda data: data["cases"][0].update({"expected_pipeline_status": "maybe"}), "unknown_expected_status"),
        ("unknown check", lambda data: data["cases"][0].update({"required_checks": ["not_a_real_check"]}), "unknown_required_check"),
        ("repeat too high", lambda data: data.update({"repeat": 9}), "invalid_repeat"),
    ]
    for label, mutate, code in invalid_cases:
        candidate = _load_json(MANIFEST_PATH)
        mutate(candidate)
        path = tmp_path / f"{label.replace(' ', '_')}.json"
        _write_json(path, candidate)
        with pytest.raises(BenchmarkManifestError) as exc:
            load_benchmark_manifest(path, fixtures_root=FIXTURES_ROOT)
        assert exc.value.code == code


def test_benchmark_executes_all_cases_with_stable_order_and_isolated_outputs(tmp_path: Path) -> None:
    result = _run(tmp_path)
    replayed = _run(tmp_path / "replayed")

    assert result["stage"] == BENCHMARK_STAGE
    assert result["passed"] is True
    assert result["manifest_hash"] == replayed["manifest_hash"]
    assert result["output_hash"] == replayed["output_hash"]
    assert result["total_cases"] == 12
    assert result["matched_cases"] == 12
    assert result["unexpected_cases"] == 0
    assert result["execution_error_cases"] == 0
    assert result["aggregate_score"] == 100
    assert [case["case_id"] for case in result["case_results"]] == [
        case["case_id"] for case in load_benchmark_manifest(MANIFEST_PATH, fixtures_root=FIXTURES_ROOT)["cases"]
    ]
    assert all(case["benchmark_case_passed"] for case in result["case_results"])
    assert all(case["expectation_matched"] for case in result["case_results"])
    assert all(case["required_checks_matched"] for case in result["case_results"])
    assert all(case["deterministic"] for case in result["case_results"])
    assert all(value is False for value in result["external_calls"].values())

    benchmark_root = tmp_path / "outputs" / "tradingagents-m2b-offline-benchmark"
    for case in result["case_results"]:
        assert (benchmark_root / case["case_id"] / "run-1").is_dir()
        assert (benchmark_root / case["case_id"] / "run-2").is_dir()
        assert not str(case["fixture"]).startswith(str(PROJECT_ROOT))


def test_expected_rejections_count_as_benchmark_case_passed(tmp_path: Path) -> None:
    result = _run(tmp_path)

    expectations = {
        "qa-failed-001": "data_quality_not_passed",
        "unsupported-schema-001": "unsupported_schema_version",
        "missing-snapshot-identity-001": "invalid_snapshot_schema",
        "invalid-as-of-time-001": "invalid_as_of_time",
        "malformed-json-001": "invalid_json",
        "credential-field-001": "credential_field_detected",
        "forbidden-trading-field-001": "forbidden_trading_field",
        "stage2-required-field-missing-001": "stage2_input_mapping_failed",
    }
    for case_id, expected_code in expectations.items():
        case = _case(result, case_id)
        assert case["expected_pipeline_status"] == "rejected"
        assert case["actual_pipeline_status"] == "rejected"
        assert expected_code in case["actual_error_codes"]
        assert case["benchmark_case_passed"] is True


def test_unexpected_acceptance_error_code_mismatch_and_required_check_gap_are_reported(
    tmp_path: Path,
) -> None:
    fixtures_root = _copy_fixture_tree(tmp_path)
    manifest_path = fixtures_root / "benchmark_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["cases"] = [
        {
            "case_id": "expected-rejection-but-accepted",
            "fixture": "cases/valid_complete_001.json",
            "category": "security_rejection",
            "expected_pipeline_status": "rejected",
            "expected_error_code": "credential_field_detected",
            "required_checks": list(CRITICAL_CHECKS),
            "tags": ["synthetic"],
        },
        {
            "case_id": "wrong-error-code",
            "fixture": "cases/qa_failed_001.json",
            "category": "snapshot_contract_rejection",
            "expected_pipeline_status": "rejected",
            "expected_error_code": "unsupported_schema_version",
            "required_checks": list(CRITICAL_CHECKS),
            "tags": ["synthetic"],
        },
        {
            "case_id": "missing-required-check",
            "fixture": "cases/valid_complete_001.json",
            "category": "valid",
            "expected_pipeline_status": "passed",
            "expected_error_code": None,
            "required_checks": list(CRITICAL_CHECKS),
            "tags": ["synthetic"],
        },
    ]
    manifest["repeat"] = 1
    _write_json(manifest_path, manifest)

    def runner(snapshot_path: Path, *, allowed_root: Path, output_root: Path, case_id: str) -> dict[str, Any]:
        if case_id == "missing-required-check":
            checks = [{"name": name, "passed": True, "severity": "critical", "details": []} for name in CRITICAL_CHECKS]
            checks = [check for check in checks if check["name"] != "no_external_calls"]
            return {
                "passed": True,
                "score": 100,
                "checks": checks,
                "lineage": {"normalized_artifact_hash": "a" * 64},
                "artifact_summary": {"normalized_artifact_hash": "a" * 64},
                "external_calls": {
                    "llm_called": False,
                    "network_called": False,
                    "market_data_called": False,
                    "tushare_called": False,
                    "qlib_called": False,
                    "broker_called": False,
                },
                "errors": [],
            }
        from datang_extensions.evaluation.offline_research_pipeline import run_offline_research_evaluation

        return run_offline_research_evaluation(
            snapshot_path,
            allowed_root=allowed_root,
            output_root=output_root,
            case_id=case_id,
        )

    result = run_offline_research_benchmark(
        manifest_path,
        fixtures_root=fixtures_root,
        output_root=tmp_path / "outputs",
        pipeline_runner=runner,
    )

    assert result["passed"] is False
    assert result["unexpected_cases"] == 3
    assert _case(result, "expected-rejection-but-accepted")["benchmark_case_passed"] is False
    assert _case(result, "wrong-error-code")["benchmark_case_passed"] is False
    assert _case(result, "missing-required-check")["required_checks_matched"] is False


def test_fail_fast_is_optional_and_default_keeps_batch_running(tmp_path: Path) -> None:
    fixtures_root = _copy_fixture_tree(tmp_path)
    manifest_path = fixtures_root / "benchmark_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["cases"] = manifest["cases"][:3]
    _write_json(manifest_path, manifest)

    def runner(snapshot_path: Path, *, allowed_root: Path, output_root: Path, case_id: str) -> dict[str, Any]:
        if case_id == "valid-conflicting-evidence-001":
            raise RuntimeError("synthetic case execution error")
        from datang_extensions.evaluation.offline_research_pipeline import run_offline_research_evaluation

        return run_offline_research_evaluation(
            snapshot_path,
            allowed_root=allowed_root,
            output_root=output_root,
            case_id=case_id,
        )

    continued = run_offline_research_benchmark(
        manifest_path,
        fixtures_root=fixtures_root,
        output_root=tmp_path / "continued",
        pipeline_runner=runner,
    )
    stopped = run_offline_research_benchmark(
        manifest_path,
        fixtures_root=fixtures_root,
        output_root=tmp_path / "stopped",
        pipeline_runner=runner,
        fail_fast=True,
    )

    assert continued["total_cases"] == 3
    assert continued["execution_error_cases"] == 1
    assert len(continued["case_results"]) == 3
    assert stopped["total_cases"] == 3
    assert stopped["execution_error_cases"] == 1
    assert len(stopped["case_results"]) == 2


def test_repeat_detects_nondeterministic_artifact_hash(tmp_path: Path) -> None:
    fixtures_root = _copy_fixture_tree(tmp_path)
    manifest_path = fixtures_root / "benchmark_manifest.json"
    manifest = _load_json(manifest_path)
    manifest["cases"] = [manifest["cases"][0]]
    manifest["repeat"] = 2
    _write_json(manifest_path, manifest)
    calls = 0

    def runner(snapshot_path: Path, *, allowed_root: Path, output_root: Path, case_id: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "passed": True,
            "score": 100,
            "checks": [{"name": name, "passed": True, "severity": "critical", "details": []} for name in CRITICAL_CHECKS],
            "lineage": {"normalized_artifact_hash": f"{calls:064x}"},
            "artifact_summary": {"normalized_artifact_hash": f"{calls:064x}"},
            "external_calls": {
                "llm_called": False,
                "network_called": False,
                "market_data_called": False,
                "tushare_called": False,
                "qlib_called": False,
                "broker_called": False,
            },
            "errors": [],
        }

    result = run_offline_research_benchmark(
        manifest_path,
        fixtures_root=fixtures_root,
        output_root=tmp_path / "outputs",
        pipeline_runner=runner,
    )

    case = _case(result, "valid-complete-001")
    assert result["passed"] is False
    assert case["deterministic"] is False
    assert case["benchmark_case_passed"] is False
    assert len(case["normalized_hashes"]) == 2


def test_baseline_comparison_detects_regressions_and_default_does_not_overwrite(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path / "fresh")
    baseline = build_expected_baseline(result)
    baseline_path = tmp_path / "baseline.json"
    _write_json(baseline_path, baseline)

    clean = _run(tmp_path / "clean", baseline_path=baseline_path)
    assert clean["passed"] is True
    assert clean["regression"]["compared"] is True
    assert clean["regression"]["passed"] is True

    mutated = json.loads(json.dumps(baseline))
    mutated["cases"][0]["actual_pipeline_status"] = "rejected"
    mutated["cases"][1]["actual_error_codes"] = ["synthetic_changed_error"]
    mutated["cases"][2]["normalized_artifact_hash"] = "b" * 64
    _write_json(baseline_path, mutated)
    regressed = _run(tmp_path / "regressed", baseline_path=baseline_path)

    assert regressed["passed"] is False
    assert regressed["regression"]["passed"] is False
    assert regressed["regression"]["changed_outcomes"]
    assert regressed["regression"]["changed_error_codes"]
    assert regressed["regression"]["changed_normalized_hashes"]

    existing = tmp_path / "existing_baseline.json"
    _write_json(existing, baseline)
    with pytest.raises(FileExistsError):
        run_offline_research_benchmark(
            MANIFEST_PATH,
            fixtures_root=FIXTURES_ROOT,
            output_root=tmp_path / "write_baseline",
            write_baseline=True,
            baseline_output_path=existing,
        )


def test_external_calls_blocked_fixture_unchanged_and_no_repo_reports_or_exports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture_stats = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in FIXTURES_ROOT.rglob("*.json")}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in M2B")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = ("openai", "anthropic", "google_genai", "tushare", "qlib", "requests", "httpx", "websocket")
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = _run(tmp_path)

    assert result["passed"] is True
    assert all(value is False for value in result["external_calls"].values())
    for path, (content, mtime_ns) in fixture_stats.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime_ns
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_benchmark").exists()
    assert subprocess.run(
        ["git", "ls-files", "data/exports"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip() == ""


def test_cli_smoke_outputs_summary_and_uses_explicit_paths_only(tmp_path: Path) -> None:
    smoke_root = tmp_path / "smoke"
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--manifest",
        str(MANIFEST_PATH),
        "--fixtures-root",
        str(FIXTURES_ROOT),
        "--output-root",
        str(smoke_root),
        "--baseline",
        str(BASELINE_PATH),
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["passed"] is True
    assert summary["total_cases"] == 12
    assert summary["unexpected_cases"] == 0
    assert all(value is False for value in summary["external_calls"].values())
    assert smoke_root.exists()
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_benchmark").exists()
    assert "OPENAI_API_KEY" not in completed.stdout
