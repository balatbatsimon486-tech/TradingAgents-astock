"""Multi-case offline research benchmark runner for M2B."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from datang_extensions.evaluation.offline_research_evaluator import (
    CRITICAL_CHECKS,
    EXTERNAL_CALLS_FALSE,
    sha256_file,
    stable_json_hash,
)
from datang_extensions.evaluation.offline_research_pipeline import run_offline_research_evaluation
from datang_extensions.utils.safe_io import write_json_file

BENCHMARK_STAGE = "tradingagents_m2b_offline_research_benchmark"
BENCHMARK_ID = "tradingagents-m2b-offline-benchmark"
SUPPORTED_BENCHMARK_VERSIONS = frozenset({"1.0"})
SUPPORTED_EVALUATION_VERSIONS = frozenset({"1.0"})
ALLOWED_CATEGORIES = frozenset(
    {
        "valid",
        "snapshot_contract_rejection",
        "security_rejection",
        "stage2_mapping_rejection",
        "evaluation_rejection",
    }
)
ALLOWED_EXPECTED_STATUSES = frozenset({"passed", "rejected"})
MAX_REPEAT = 5
KNOWN_ERROR_CODES = frozenset(
    {
        "data_quality_not_passed",
        "unsupported_schema_version",
        "invalid_snapshot_schema",
        "invalid_as_of_time",
        "invalid_json",
        "credential_field_detected",
        "forbidden_trading_field",
        "stage2_input_mapping_failed",
        "lineage_mismatch",
        "forbidden_trading_field_detected",
        "determinism_failed",
        "benchmark_execution_error",
    }
)

PipelineRunner = Callable[..., dict[str, Any]]


class BenchmarkManifestError(ValueError):
    """Raised when a benchmark manifest fails closed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _relative_fixture_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkManifestError("missing_fixture", "case fixture must be a non-empty relative path")
    if "\\" in value:
        raise BenchmarkManifestError("unsafe_fixture_path", "case fixture must use portable relative separators")
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise BenchmarkManifestError("unsafe_fixture_path", "case fixture must stay inside fixtures_root")
    return path


def _require_non_empty_string(payload: Mapping[str, Any], field: str, code: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkManifestError(code, f"{field} must be a non-empty string")
    return value.strip()


def _validate_case(case: Any, *, fixtures_root: Path, seen: set[str]) -> dict[str, Any]:
    if not isinstance(case, Mapping):
        raise BenchmarkManifestError("invalid_case", "benchmark cases must be objects")

    case_id = _require_non_empty_string(case, "case_id", "missing_case_id")
    if case_id in seen:
        raise BenchmarkManifestError("duplicate_case_id", f"duplicate case_id: {case_id}")
    seen.add(case_id)

    fixture_rel = _relative_fixture_path(case.get("fixture"))
    fixture_path = (fixtures_root / fixture_rel).resolve(strict=False)
    try:
        fixture_path.relative_to(fixtures_root.resolve(strict=False))
    except ValueError as exc:
        raise BenchmarkManifestError("unsafe_fixture_path", "case fixture resolves outside fixtures_root") from exc

    category = _require_non_empty_string(case, "category", "missing_category")
    if category not in ALLOWED_CATEGORIES:
        raise BenchmarkManifestError("unknown_category", f"unknown benchmark category: {category}")

    expected_status = _require_non_empty_string(
        case,
        "expected_pipeline_status",
        "missing_expected_status",
    )
    if expected_status not in ALLOWED_EXPECTED_STATUSES:
        raise BenchmarkManifestError("unknown_expected_status", f"unknown expected status: {expected_status}")

    expected_error_code = case.get("expected_error_code")
    if expected_status == "passed" and expected_error_code is not None:
        raise BenchmarkManifestError(
            "invalid_expected_error_code",
            "passed cases must not declare an expected_error_code",
        )
    if expected_status == "rejected" and not isinstance(expected_error_code, str):
        raise BenchmarkManifestError(
            "invalid_expected_error_code",
            "rejected cases must declare an expected_error_code",
        )

    required_checks = case.get("required_checks")
    if not isinstance(required_checks, list) or not required_checks:
        raise BenchmarkManifestError("missing_required_checks", "required_checks must be a non-empty list")
    unknown_checks = [check for check in required_checks if check not in CRITICAL_CHECKS]
    if unknown_checks:
        raise BenchmarkManifestError("unknown_required_check", f"unknown required checks: {unknown_checks}")

    tags = case.get("tags", [])
    if not isinstance(tags, list):
        raise BenchmarkManifestError("invalid_tags", "case tags must be a list")

    return {
        "case_id": case_id,
        "fixture": fixture_rel.as_posix(),
        "fixture_path": fixture_path,
        "category": category,
        "expected_pipeline_status": expected_status,
        "expected_error_code": expected_error_code,
        "required_checks": list(required_checks),
        "tags": [str(tag) for tag in tags],
    }


def load_benchmark_manifest(manifest_path: str | Path, *, fixtures_root: str | Path) -> dict[str, Any]:
    """Load and validate a versioned M2B benchmark manifest."""

    manifest_file = Path(manifest_path)
    root = Path(fixtures_root).resolve(strict=False)
    try:
        payload = _load_json(manifest_file)
    except json.JSONDecodeError as exc:
        raise BenchmarkManifestError("invalid_manifest_json", str(exc)) from exc
    except OSError as exc:
        raise BenchmarkManifestError("manifest_read_error", str(exc)) from exc

    if not isinstance(payload, Mapping):
        raise BenchmarkManifestError("invalid_manifest", "benchmark manifest must be a JSON object")

    benchmark_id = _require_non_empty_string(payload, "benchmark_id", "missing_benchmark_id")
    benchmark_version = _require_non_empty_string(payload, "benchmark_version", "missing_benchmark_version")
    if benchmark_version not in SUPPORTED_BENCHMARK_VERSIONS:
        raise BenchmarkManifestError(
            "unsupported_benchmark_version",
            f"unsupported benchmark_version: {benchmark_version}",
        )
    evaluation_version = _require_non_empty_string(payload, "evaluation_version", "missing_evaluation_version")
    if evaluation_version not in SUPPORTED_EVALUATION_VERSIONS:
        raise BenchmarkManifestError(
            "unsupported_evaluation_version",
            f"unsupported evaluation_version: {evaluation_version}",
        )

    repeat = payload.get("repeat")
    if not isinstance(repeat, int) or repeat < 1 or repeat > MAX_REPEAT:
        raise BenchmarkManifestError("invalid_repeat", f"repeat must be an integer between 1 and {MAX_REPEAT}")

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkManifestError("missing_cases", "cases must be a non-empty list")

    seen: set[str] = set()
    validated_cases = [_validate_case(case, fixtures_root=root, seen=seen) for case in cases]
    return {
        "benchmark_id": benchmark_id,
        "benchmark_version": benchmark_version,
        "evaluation_version": evaluation_version,
        "description": str(payload.get("description", "")),
        "repeat": repeat,
        "cases": validated_cases,
    }


def _error_codes(summary: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    for error in summary.get("errors") or []:
        if isinstance(error, Mapping):
            code = str(error.get("code", ""))
            if code and code not in codes:
                codes.append(code)
            message = str(error.get("message", ""))
            if message in KNOWN_ERROR_CODES and message not in codes:
                codes.append(message)
    return codes


def _external_calls(summary: Mapping[str, Any]) -> dict[str, bool]:
    merged = dict(EXTERNAL_CALLS_FALSE)
    value = summary.get("external_calls")
    if isinstance(value, Mapping):
        for key in merged:
            merged[key] = bool(value.get(key, merged[key]))
    return merged


def _check_names(summary: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for check in summary.get("checks") or []:
        if isinstance(check, Mapping) and check.get("passed") is True:
            names.add(str(check.get("name", "")))
    return names


def _normalized_hash(summary: Mapping[str, Any]) -> str:
    lineage = summary.get("lineage")
    if isinstance(lineage, Mapping) and lineage.get("normalized_artifact_hash"):
        return str(lineage["normalized_artifact_hash"])
    artifact_summary = summary.get("artifact_summary")
    if isinstance(artifact_summary, Mapping) and artifact_summary.get("normalized_artifact_hash"):
        return str(artifact_summary["normalized_artifact_hash"])
    return ""


def _execution_error_case(case: Mapping[str, Any], fixture_hash: str, message: str) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "fixture": case["fixture"],
        "fixture_hash": fixture_hash,
        "expected_pipeline_status": case["expected_pipeline_status"],
        "actual_pipeline_status": "execution_error",
        "expected_error_code": case["expected_error_code"],
        "actual_error_codes": ["benchmark_execution_error"],
        "expectation_matched": False,
        "required_checks_matched": False,
        "deterministic": False,
        "normalized_hashes": [],
        "benchmark_case_passed": False,
        "warnings": [],
        "errors": [{"code": "benchmark_execution_error", "message": message}],
    }


def _run_case(
    *,
    case: Mapping[str, Any],
    fixtures_root: Path,
    output_root: Path,
    repeat: int,
    pipeline_runner: PipelineRunner,
) -> dict[str, Any]:
    fixture_path = Path(case["fixture_path"])
    fixture_hash = sha256_file(fixture_path) if fixture_path.exists() and fixture_path.is_file() else ""
    summaries: list[dict[str, Any]] = []
    normalized_hashes: list[str] = []

    for run_index in range(1, repeat + 1):
        run_root = output_root / str(case["case_id"]) / f"run-{run_index}"
        run_root.mkdir(parents=True, exist_ok=True)
        try:
            summary = pipeline_runner(
                fixture_path,
                allowed_root=fixtures_root,
                output_root=run_root,
                case_id=str(case["case_id"]),
            )
        except Exception as exc:
            return _execution_error_case(case, fixture_hash, type(exc).__name__)
        summaries.append(summary)
        normalized_hashes.append(_normalized_hash(summary))

    first = summaries[0] if summaries else {}
    actual_status = "passed" if first.get("passed") is True else "rejected"
    actual_error_codes = _error_codes(first)
    expected_status = str(case["expected_pipeline_status"])
    expected_error_code = case.get("expected_error_code")
    expectation_matched = actual_status == expected_status and (
        expected_status == "passed" or expected_error_code in actual_error_codes
    )

    passed_check_names = _check_names(first)
    required_checks = set(case["required_checks"])
    required_checks_matched = required_checks.issubset(passed_check_names)
    if expected_status == "rejected":
        required_checks_matched = True

    deterministic = bool(normalized_hashes) and len(set(normalized_hashes)) == 1
    calls = _external_calls(first)
    no_external_calls = not any(calls.values())
    benchmark_case_passed = (
        expectation_matched
        and required_checks_matched
        and deterministic
        and no_external_calls
    )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "fixture": case["fixture"],
        "fixture_hash": fixture_hash,
        "expected_pipeline_status": expected_status,
        "actual_pipeline_status": actual_status,
        "expected_error_code": expected_error_code,
        "actual_error_codes": actual_error_codes,
        "expectation_matched": expectation_matched,
        "required_checks_matched": required_checks_matched,
        "deterministic": deterministic,
        "normalized_hashes": normalized_hashes,
        "external_calls": calls,
        "benchmark_case_passed": benchmark_case_passed,
        "warnings": list(first.get("warnings") or []),
        "errors": list(first.get("errors") or []),
    }


def build_expected_baseline(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a stable baseline payload from a benchmark result."""

    return {
        "benchmark_id": result.get("benchmark_id", ""),
        "benchmark_version": result.get("benchmark_version", ""),
        "evaluation_version": result.get("evaluation_version", ""),
        "manifest_hash": result.get("manifest_hash", ""),
        "cases": [
            {
                "case_id": case.get("case_id", ""),
                "expected_pipeline_status": case.get("expected_pipeline_status", ""),
                "actual_pipeline_status": case.get("actual_pipeline_status", ""),
                "expected_error_code": case.get("expected_error_code"),
                "actual_error_codes": list(case.get("actual_error_codes") or []),
                "required_checks_matched": bool(case.get("required_checks_matched")),
                "normalized_artifact_hash": (case.get("normalized_hashes") or [""])[0],
                "benchmark_case_passed": bool(case.get("benchmark_case_passed")),
            }
            for case in result.get("case_results", [])
        ],
    }


def _compare_baseline(result: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    current = {case["case_id"]: case for case in build_expected_baseline(result)["cases"]}
    expected = {case.get("case_id", ""): case for case in baseline.get("cases", []) if isinstance(case, Mapping)}
    new_failures: list[str] = []
    changed_outcomes: list[str] = []
    changed_error_codes: list[str] = []
    changed_hashes: list[str] = []

    for case_id, baseline_case in expected.items():
        current_case = current.get(case_id)
        if current_case is None:
            new_failures.append(case_id)
            continue
        if baseline_case.get("benchmark_case_passed") is True and current_case.get("benchmark_case_passed") is not True:
            new_failures.append(case_id)
        if baseline_case.get("actual_pipeline_status") != current_case.get("actual_pipeline_status"):
            changed_outcomes.append(case_id)
        if baseline_case.get("actual_error_codes") != current_case.get("actual_error_codes"):
            changed_error_codes.append(case_id)
        if baseline_case.get("normalized_artifact_hash") != current_case.get("normalized_artifact_hash"):
            changed_hashes.append(case_id)
    for case_id in current:
        if case_id not in expected:
            new_failures.append(case_id)

    passed = not (new_failures or changed_outcomes or changed_error_codes or changed_hashes)
    return {
        "compared": True,
        "passed": passed,
        "new_failures": new_failures,
        "changed_outcomes": changed_outcomes,
        "changed_error_codes": changed_error_codes,
        "changed_normalized_hashes": changed_hashes,
    }


def _empty_regression() -> dict[str, Any]:
    return {
        "compared": False,
        "passed": False,
        "new_failures": [],
        "changed_outcomes": [],
        "changed_error_codes": [],
        "changed_normalized_hashes": [],
    }


def run_offline_research_benchmark(
    manifest_path: str | Path,
    *,
    fixtures_root: str | Path,
    output_root: str | Path,
    baseline_path: str | Path | None = None,
    fail_fast: bool = False,
    write_baseline: bool = False,
    baseline_output_path: str | Path | None = None,
    pipeline_runner: PipelineRunner = run_offline_research_evaluation,
) -> dict[str, Any]:
    """Run the fixed synthetic M2B offline research benchmark suite."""

    manifest_file = Path(manifest_path)
    root = Path(fixtures_root).resolve(strict=False)
    manifest = load_benchmark_manifest(manifest_file, fixtures_root=root)
    manifest_hash = sha256_file(manifest_file)
    benchmark_root = Path(output_root) / manifest["benchmark_id"]

    case_results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        case_result = _run_case(
            case=case,
            fixtures_root=root,
            output_root=benchmark_root,
            repeat=int(manifest["repeat"]),
            pipeline_runner=pipeline_runner,
        )
        case_results.append(case_result)
        if fail_fast and not case_result["benchmark_case_passed"]:
            break

    matched_cases = sum(1 for case in case_results if case["benchmark_case_passed"])
    execution_error_cases = sum(1 for case in case_results if case["actual_pipeline_status"] == "execution_error")
    unexpected_cases = len(case_results) - matched_cases
    external_calls = dict(EXTERNAL_CALLS_FALSE)
    warnings: list[str] = []
    errors: list[dict[str, str]] = []
    if fail_fast and len(case_results) < len(manifest["cases"]):
        warnings.append("fail_fast stopped benchmark before all cases ran")
    for case in case_results:
        for key in external_calls:
            calls = case.get("external_calls")
            if isinstance(calls, Mapping):
                external_calls[key] = external_calls[key] or bool(calls.get(key, False))
        for error in case.get("errors") or []:
            if isinstance(error, Mapping) and error.get("code") == "benchmark_execution_error":
                errors.append({"code": "benchmark_execution_error", "message": str(error.get("message", ""))})

    result: dict[str, Any] = {
        "stage": BENCHMARK_STAGE,
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_version": manifest["benchmark_version"],
        "evaluation_version": manifest["evaluation_version"],
        "manifest_hash": manifest_hash,
        "baseline_hash": sha256_file(baseline_path) if baseline_path else "",
        "passed": False,
        "total_cases": len(manifest["cases"]),
        "matched_cases": matched_cases,
        "unexpected_cases": unexpected_cases,
        "execution_error_cases": execution_error_cases,
        "aggregate_score": int((matched_cases / len(manifest["cases"])) * 100) if manifest["cases"] else 0,
        "case_results": case_results,
        "regression": _empty_regression(),
        "external_calls": external_calls,
        "warnings": warnings,
        "errors": errors,
    }

    if baseline_path is not None:
        baseline = _load_json(baseline_path)
        if not isinstance(baseline, Mapping):
            raise BenchmarkManifestError("invalid_baseline", "baseline must be a JSON object")
        result["regression"] = _compare_baseline(result, baseline)

    if write_baseline:
        if baseline_output_path is None:
            raise BenchmarkManifestError("missing_baseline_output_path", "baseline_output_path is required")
        baseline_target = Path(baseline_output_path)
        if baseline_target.exists():
            raise FileExistsError(str(baseline_target))
        write_json_file(baseline_target, build_expected_baseline(result))

    regression_ok = (not result["regression"]["compared"]) or result["regression"]["passed"]
    result["passed"] = (
        matched_cases == len(manifest["cases"])
        and unexpected_cases == 0
        and execution_error_cases == 0
        and not any(result["external_calls"].values())
        and regression_ok
    )
    result["output_hash"] = stable_json_hash(
        {
            "benchmark_id": result["benchmark_id"],
            "benchmark_version": result["benchmark_version"],
            "manifest_hash": result["manifest_hash"],
            "case_results": build_expected_baseline(result)["cases"],
            "regression": result["regression"],
            "passed": result["passed"],
        }
    )
    return result
