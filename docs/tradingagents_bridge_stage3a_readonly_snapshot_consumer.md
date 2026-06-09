# Stage 3A Read-Only Research Snapshot Consumer

Stage 3A adds a TradingAgents-astock-side consumer for Datang research snapshot
JSON files. The consumer is read-only and converts a snapshot into a research
context that future analysts can inspect.

## Boundary

The consumer may read a JSON snapshot exported by Datang's research platform.
It must not:

- read Tushare tokens or any other credentials
- import Tushare or call provider APIs
- read raw parquet data
- create strategy, signal, recommendation, backtest, expected return, position,
  or order fields
- write snapshot JSON files into the repository
- connect to automatic trading

## Interface

```python
from datang_extensions.ingestion.research_snapshot_reader import read_research_snapshot

result = read_research_snapshot("path/to/snapshot.json")
```

Successful results use this shape:

```python
{
    "ok": True,
    "passed": True,
    "context": {
        "read_only": True,
        "source_platform": "datang_quant_platform",
        "allowed_usage": "research_context_only",
        "no_trading_decision": True,
        "data_quality": {...},
        "warnings": [...],
        "errors": [...],
    },
    "error": None,
}
```

The context preserves `warnings`, `errors`, and `data_quality` so that downstream
research code cannot hide data-quality caveats.

## Structured Errors

The reader returns structured errors instead of uncaught exceptions:

- `missing_snapshot_file`: the input path does not exist
- `invalid_json`: the file is not valid JSON
- `invalid_snapshot_schema`: required fields are missing or invalid
- `forbidden_trading_field`: strategy or trading-decision fields are present
- `credential_field_detected`: credential-like fields are present
- `snapshot_read_error`: the file exists but cannot be read

## Required Snapshot Fields

The current read-only contract expects:

- `symbol`
- `trade_date`
- `source_platform`
- `data_source`
- `snapshot_version`
- `created_at_utc`
- `price_window`
- `latest_ohlcv`
- `adj_factor`
- `stock_basic`
- `data_quality`
- `warnings`
- `errors`

`source_platform` must be `datang_quant_platform`.

## Testing

Tests build temporary JSON files with `tmp_path`. They do not depend on real
snapshot files under `data/exports/`, do not read tokens, and do not call live
market data or LLM APIs.

## Current Repository Context

The Stage 3A review was performed on the `datang/main` branch of the
TradingAgents-astock fork. The relevant repository directories are:

- `datang_extensions/`
- `scripts/`
- `tests/`

This fork does not currently contain `src/` or `datang_adapters/` directories,
so compile checks for Stage 3A should target the existing directories only.

## Stage 3A Acceptance Record

- `read_research_snapshot(snapshot_path)` returns a read-only research context.
- The returned context sets `read_only: true`, `allowed_usage:
  "research_context_only"`, and `no_trading_decision: true`.
- The reader preserves `warnings`, `errors`, and `data_quality`.
- All expected failure paths return structured errors.
- Tests create only temporary JSON files through `tmp_path`.
- `git ls-files data/exports` must remain empty.
- No real snapshot JSON, credentials, cache files, reports, or API outputs are
  tracked by Git.
- Forbidden field names in the implementation and tests are guardrails for
  rejection checks only; they are not generated as trading decisions.
- Stage 3A does not connect to agent prompts, analyst pipelines, live APIs,
  Tushare, LLM services, backtesting, portfolio management, or automatic
  trading.

## Pre-Commit Checklist

Run these commands from the repository root before committing Stage 3A:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tradingagents_bridge -q
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m compileall datang_extensions scripts tests
.\.venv\Scripts\python.exe scripts\audit_datang_extension_boundary.py
git ls-files data/exports
git diff -- . ':!datang_extensions' ':!docs' ':!tests' ':!scripts' ':!.github' ':!reports' ':!.gitignore' ':!requirements-dev.txt' ':!pytest.ini'
```

The final `git diff` command must produce no output; any output means an
official core source file may have been modified and the commit should stop for
review.
