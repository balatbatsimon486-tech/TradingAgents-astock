# M2B Offline Research Benchmark

## Current Progress

Project: TradingAgents-astock

Milestone: R1 Research Evaluation Foundation

Completed stages:

- Stage 1 extension governance and boundary checks
- Stage 2 offline report ingestion
- Stage 3A read-only Datang research snapshot consumer and safety contract
- M2A single-case offline end-to-end evaluation

M2B adds the fixed multi-case synthetic benchmark required before R1 can enter
its release gate. R2 real LLM work is not implemented in this stage.

## Position In R1

M2A proves one legal synthetic snapshot can flow through Stage 3A, Stage 2, and
the deterministic evaluator. M2B turns that single-case path into a stable
benchmark suite that future schema, prompt, model, and agent changes must pass.

## Goals

- run multiple fixed synthetic cases in a deterministic order
- distinguish pipeline pass/rejection from benchmark case pass/fail
- verify expected error codes for rejection controls
- keep one case failure from stopping the whole batch by default
- compare the current result against a fixed baseline
- detect changed outcomes, error codes, hashes, and missing cases
- prove the benchmark is offline and research-only

## Non-Goals

M2B does not call real LLMs, market data, Tushare, Qlib, brokers, or network
services. It does not evaluate prediction accuracy, returns, backtests, strategy
quality, positions, weights, or orders. It does not modify the upstream
TradingAgents core directories.

## Relationship To M2A

The benchmark runner reuses:

- `run_offline_research_evaluation(...)`
- M2A `CRITICAL_CHECKS`
- M2A SHA-256 helpers
- Stage 3A snapshot reader through the M2A pipeline
- Stage 2 offline ingestion through the M2A pipeline

It does not create a second snapshot reader, a second artifact evaluator, or a
second Stage 2 ingestion implementation.

## Manifest Schema

The fixed manifest lives at:

```text
tests/tradingagents_bridge/fixtures/m2b/benchmark_manifest.json
```

Required fields:

- `benchmark_id`
- `benchmark_version`
- `evaluation_version`
- `description`
- `repeat`
- `cases`

Each case declares:

- `case_id`
- `fixture`
- `category`
- `expected_pipeline_status`
- `expected_error_code`
- `required_checks`
- `tags`

The runner fails closed when the benchmark version is unsupported, the repeat
count is outside `1..5`, case ids are duplicated, fixture paths are absolute or
contain `..`, categories are unknown, expected statuses are unknown, or required
checks are not part of M2A `CRITICAL_CHECKS`.

## Case Schema

All cases are fully synthetic JSON fixtures under:

```text
tests/tradingagents_bridge/fixtures/m2b/cases/
```

Fixtures use test symbols only for schema coverage. Their content is not a real
security fact, real market observation, real research conclusion, or investment
view.

## Pipeline Status And Benchmark Status

Pipeline status describes what M2A did:

- `passed`: M2A returned `passed=true`
- `rejected`: M2A returned `passed=false`
- `execution_error`: the benchmark runner caught an unexpected exception

Benchmark case status means the actual result matched the manifest expectation.
A fixture that is expected to be rejected is a benchmark pass when M2A rejects it
with the expected error code.

## First Case Matrix

The first benchmark contains 12 fixed cases:

- `valid-complete-001`: expected pipeline passed
- `valid-conflicting-evidence-001`: expected pipeline passed
- `valid-insufficient-evidence-001`: expected pipeline passed
- `valid-timezone-offset-001`: expected pipeline passed
- `qa-failed-001`: expected rejected, `data_quality_not_passed`
- `unsupported-schema-001`: expected rejected, `unsupported_schema_version`
- `missing-snapshot-identity-001`: expected rejected, `invalid_snapshot_schema`
- `invalid-as-of-time-001`: expected rejected, `invalid_as_of_time`
- `malformed-json-001`: expected rejected, `invalid_json`
- `credential-field-001`: expected rejected, `credential_field_detected`
- `forbidden-trading-field-001`: expected rejected, `forbidden_trading_field`
- `stage2-required-field-missing-001`: expected rejected,
  `stage2_input_mapping_failed`

## Aggregate Summary

`run_offline_research_benchmark(...)` returns a JSON-serializable dictionary with:

- `stage`
- `benchmark_id`
- `benchmark_version`
- `evaluation_version`
- `manifest_hash`
- `baseline_hash`
- `passed`
- `total_cases`
- `matched_cases`
- `unexpected_cases`
- `execution_error_cases`
- `aggregate_score`
- `case_results`
- `regression`
- `external_calls`
- `warnings`
- `errors`
- `output_hash`

`aggregate_score` is informational. A single unexpected case keeps
`passed=false`.

## Case Result

Each case result includes:

- `case_id`
- `category`
- `fixture`
- `fixture_hash`
- `expected_pipeline_status`
- `actual_pipeline_status`
- `expected_error_code`
- `actual_error_codes`
- `expectation_matched`
- `required_checks_matched`
- `deterministic`
- `normalized_hashes`
- `benchmark_case_passed`
- `warnings`
- `errors`

Fixture paths are stored as manifest-relative paths, not absolute local paths.

## Baseline Rules

The fixed baseline lives at:

```text
tests/tradingagents_bridge/fixtures/m2b/expected_baseline.json
```

It records stable fields only: benchmark id/version, evaluation version,
manifest hash, case id, expected status, actual status, expected error code,
actual error codes, required-check status, normalized artifact hash, and case
pass status.

It excludes run time, duration, temporary directories, generated artifact paths,
absolute paths, volatile ids, and timestamps.

Baseline generation is explicit. The CLI never overwrites an existing baseline by
default.

## Regression Comparison

When `baseline_path` is provided, the runner reports:

- `new_failures`
- `changed_outcomes`
- `changed_error_codes`
- `changed_normalized_hashes`

Any baseline regression keeps `passed=false`. Changes must be reviewed and
accepted through a deliberate baseline update.

## Determinism

The manifest repeat count is `2`. Each case runs twice. The case is deterministic
only when both normalized artifact hashes match. For rejected cases that stop
before artifact generation, both normalized hashes are empty and stable.

The manifest and fixture files are hashed with SHA-256 and are not modified by
the runner.

## Case Isolation

Each run uses an isolated output directory:

```text
<output_root>/<benchmark_id>/<case_id>/run-1/
<output_root>/<benchmark_id>/<case_id>/run-2/
```

M2A writes its own per-case artifacts under that run directory. A rejected case
still gets its run directory so the batch is auditable.

## External-Call Isolation

The benchmark summary records all external call flags as false:

```json
{
  "llm_called": false,
  "network_called": false,
  "market_data_called": false,
  "tushare_called": false,
  "qlib_called": false,
  "broker_called": false
}
```

Tests monkeypatch socket and common external imports. The production runner does
not import external LLM, network, market, Tushare, Qlib, or broker clients.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_research_benchmark.py `
  --manifest tests\tradingagents_bridge\fixtures\m2b\benchmark_manifest.json `
  --fixtures-root tests\tradingagents_bridge\fixtures\m2b `
  --output-root "$smokeRoot" `
  --baseline tests\tradingagents_bridge\fixtures\m2b\expected_baseline.json
```

Exit codes:

- `0`: benchmark `passed=true`
- `1`: benchmark mismatch or regression
- `2`: arguments, manifest, baseline, or write-baseline error

## Windows Basetemp

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$testRoot = "C:\Users\22567\Documents\pytest_tmp_tradingagents_m2b\$stamp"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

.\.venv\Scripts\python.exe -m pytest `
  tests\tradingagents_bridge\test_offline_research_benchmark.py -q `
  --basetemp "$testRoot\m2b" `
  -p no:cacheprovider
```

## Synthetic Fixture Notice

The fixtures are fixed synthetic control cases. They contain no real credentials,
personal data, live market data, live news, live policy interpretation, position,
weight, order, or actionable trading instruction.

## R1 Release Gate

R1 can enter the release gate when:

- M2A and M2B pass locally
- the bridge, adapter, governance, and Stage 2 regression suites pass
- the boundary audit passes
- compileall passes
- no official core source diff exists
- no real data, reports, credentials, or cache files are tracked
- remote CI passes on `datang/dev`

## R2 Go / No-Go

R2 real LLM work remains blocked until R1 has passed local and remote CI gates
and the stable branch is deliberately advanced. R2 must not inherit real API
keys, live market calls, or trading execution behavior from M2B.
