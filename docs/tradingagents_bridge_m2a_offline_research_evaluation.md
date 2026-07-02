# M2A Offline Research Evaluation

M2A adds a fully offline, single-case evaluation skeleton for TradingAgents-astock
research artifacts. It connects a synthetic frozen Datang research snapshot to
the Stage 3A read-only snapshot reader, the Stage 2 offline ingestion path, and
a deterministic evaluator.

M2A does not implement M2B. It does not call real LLMs, market data, Tushare,
Qlib, brokers, or any network service.

## Goals

- prove that one synthetic snapshot can flow through the offline chain
- preserve snapshot identity, schema, source, time, QA, and lineage
- generate standard Stage 2 Markdown and JSON research artifacts
- evaluate structure, boundaries, forbidden fields, lineage, hashes, and
  reproducibility
- fail closed before artifact generation when snapshot contract, QA, schema, or
  path gates fail

## Non-Goals

M2A does not judge natural-language truth, prediction accuracy, stock direction,
returns, strategy quality, factor effectiveness, backtest quality, portfolio
performance, or investment advice quality.

It does not generate formal signals, recommendations, strategies, positions,
orders, target weights, or broker instructions.

## Relationship To Stage 3A

Stage 3A owns snapshot identity, schema allowlist, QA fail-closed, timezone-aware
time validation, `allowed_root` path safety, and read-only guarantees.

M2A calls:

```python
read_research_snapshot(snapshot_path, allowed_root=allowed_root)
```

It does not copy or replace Stage 3A validation.

## Relationship To Stage 2

Stage 2 owns the standard TradingAgents-astock offline report schema and writes
Markdown, JSON, and metadata. M2A maps a validated synthetic snapshot into the
minimal Stage 2 offline input and calls `ingest_offline_report`.

The Stage 2 JSON artifact keeps its existing standard field set. M2A records
additional lineage in the evaluation summary and embeds the snapshot lineage in
research text fields without adding non-standard fields to the Stage 2 JSON.

## Offline Chain

```text
synthetic frozen snapshot
-> read_research_snapshot
-> readonly research context
-> Stage 2 offline input mapping
-> ingest_offline_report
-> standard Markdown / JSON artifact
-> deterministic evaluator
-> structured evaluation summary
```

## Snapshot To Stage 2 Mapping

The mapping is deterministic and uses only snapshot content:

- `snapshot_id` -> lineage text and evaluation summary
- `schema_version` -> lineage text and evaluation summary
- `source` -> lineage text and evaluation summary
- `as_of_time` -> lineage text and evaluation summary
- `data_quality` -> evaluation summary and QA check
- `symbol` -> Stage 2 `symbol`
- `trade_date` -> Stage 2 `trade_date`
- `research_opinion` -> Stage 2 `final_signal`
- `summary`, `key_points`, `risks`, `source_references` -> fixed research text

Missing `symbol`, `trade_date`, or `research_opinion` fails with
`stage2_input_mapping_failed`. M2A does not infer symbols, dates, current time,
or missing research opinions.

## Evaluation Summary

The summary contains:

- `stage`
- `evaluation_version`
- `evaluation_id`
- `case_id`
- `snapshot_id`
- `snapshot_schema_version`
- `passed`
- `score`
- `threshold`
- `checks`
- `artifact_summary`
- `lineage`
- `external_calls`
- `warnings`
- `errors`

Each check has `name`, `passed`, `severity`, and `details`.

Allowed severities are:

- `critical`
- `warning`
- `info`

## Critical Checks

M2A uses these critical checks:

- `snapshot_contract`
- `snapshot_qa`
- `artifact_exists`
- `artifact_schema`
- `research_only_boundary`
- `no_forbidden_trading_fields`
- `no_credential_fields`
- `lineage_preserved`
- `temporal_metadata`
- `deterministic_output`
- `no_external_calls`

Any failed critical check makes `passed=false`.

`score` is a completion indicator, not an average that can hide a critical
failure. All critical checks passing yields `score=100` and `passed=true`.

## Lineage

The summary records:

- `snapshot_id`
- `source`
- `schema_version`
- `as_of_time`
- `snapshot_hash`
- `raw_artifact_hash`
- `normalized_artifact_hash`

Hashes use SHA-256.

## Determinism

M2A computes a normalized artifact hash after excluding volatile fields:

- `evaluation_id`
- `generated_at`
- `created_at`
- `created_at_utc`
- `generated_at_utc`
- `run_time_utc`
- `output_path`
- `output_dir`
- `input_path`
- `duration`
- `raw_report_path`
- `json_report_path`
- `markdown_path`
- `metadata_path`

Repeated runs over the same synthetic snapshot must produce the same normalized
artifact hash.

## External Call Isolation

The summary records:

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

Tests monkeypatch network and common external dependency imports so accidental
calls fail immediately.

## Synthetic Fixture

The fixture lives at:

```text
tests/tradingagents_bridge/fixtures/m2a_valid_snapshot.json
```

It is synthetic only. It contains a fixed `snapshot_id`,
`schema_version=1.0`, timezone-aware `as_of_time`, QA passed metadata, synthetic
research text, and `synthetic://` references. It contains no real market data,
API keys, private data, positions, orders, or real research conclusions.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_research_evaluation.py `
  --snapshot tests\tradingagents_bridge\fixtures\m2a_valid_snapshot.json `
  --allowed-root tests\tradingagents_bridge\fixtures `
  --output-root reports\tradingagents_astock\offline_evaluation `
  --case-id synthetic-policy-event-001
```

The CLI writes JSON summary to stdout.

Exit codes:

- `0`: `passed=true`
- `1`: `passed=false`
- `2`: argument error

The default smoke output root is under `reports/tradingagents_astock/`, which is
ignored by Git. Generated outputs must not be committed.

## Windows Test Command

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$testRoot = "C:\Users\22567\Documents\pytest_tmp_tradingagents_m2a\$stamp"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

.\.venv\Scripts\python.exe -m pytest `
  tests\tradingagents_bridge\test_offline_research_evaluation.py -q `
  --basetemp "$testRoot\m2a" `
  -p no:cacheprovider
```

## M2B Entry Criteria

Before M2B:

- M2A tests pass locally and in CI
- Stage 2 and Stage 3A regressions still pass
- no official core source diff exists
- no real snapshots or reports are tracked
- no external LLM, market, Tushare, Qlib, or broker calls are introduced
