# Stage 3A Read-Only Research Snapshot Consumer

Stage 3A adds a TradingAgents-astock-side consumer for Datang research snapshot
JSON files. The consumer is read-only and converts an explicitly authorized
synthetic or exported snapshot into an in-memory research context.

Stage 3A does not prove research quality, strategy quality, or trading validity.
It does not implement Stage 3B.

## Boundary

The consumer may read one local JSON snapshot under an explicit `allowed_root`.
It must not:

- read Tushare tokens or any other credentials
- import Tushare or call provider APIs
- call Qlib, qrun, LLM services, market APIs, brokers, or network interfaces
- read raw parquet data or live market truth
- create factors, labels, formal signals, strategy recommendations, backtests,
  expected returns, positions, target weights, orders, or auto-trade actions
- write back to datang-quant-platform
- write snapshot JSON files, research artifacts, reports, or cache files

## Interface

```python
from pathlib import Path

from datang_extensions.ingestion.research_snapshot_reader import read_research_snapshot

result = read_research_snapshot(
    Path("synthetic_snapshots/snapshot.json"),
    allowed_root=Path("synthetic_snapshots"),
)
```

`allowed_root` is required. Calls without `allowed_root` fail closed with
`missing_allowed_root`; the reader does not treat the current working directory
as trusted.

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
        "snapshot_id": "synthetic-snapshot-001",
        "schema_version": "1.0",
        "source": "datang_quant_platform",
        "as_of_time": "2026-06-28T09:00:00+00:00",
        "data_quality": {"passed": True, "errors": [], "warnings": []},
        "warnings": [],
        "errors": [],
    },
    "error": None,
}
```

## Required Snapshot Fields

The current read-only contract requires:

- `snapshot_id`
- `schema_version`
- `source`
- `as_of_time`
- `data_quality`
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
- `warnings`
- `errors`

String identity fields must be actual strings and must be non-empty after
trimming. Missing values are not synthesized.

`source` and `source_platform` must both be `datang_quant_platform`.

## Schema Versions

Supported schema versions:

- `1.0`

Unknown, future, empty, or non-string schema versions fail closed with a
structured error. If both `snapshot_version` and `schema_version` are present,
they must match. A conflict is rejected and is not silently downgraded.

## Data Quality Gate

`data_quality` must be an object and `data_quality["passed"] is True`.

The following values are rejected:

- `False`
- `None`
- `0`
- `1`
- `"true"`
- `"false"`
- missing `passed`

If `data_quality.errors`, `data_quality.blockers`, or
`data_quality.critical_issues` is non-empty, the reader fails closed with
`data_quality_not_passed`. QA failures do not produce a usable research context.

## Time Fields

`as_of_time` must be a timezone-aware ISO-8601 string. `Z` is accepted as UTC.
Naive datetimes, empty strings, non-strings, and unparsable values are rejected.

If `generated_at` is present, it must also be timezone-aware ISO-8601 and must
not be earlier than `as_of_time`.

Stage 3A does not infer future returns and does not use content after
`as_of_time` as a trading signal.

## Path Security

The reader resolves both `snapshot_path` and `allowed_root`, then requires the
resolved snapshot path to stay under the resolved allowed root. This rejects
paths outside the root, `../` traversal, and symlink escapes when the platform
allows symlink tests.

The path must exist, be a regular file, and use the `.json` extension. Directory
paths, missing files, non-JSON files, and malformed JSON fail safely.

## Structured Errors

The reader returns structured errors instead of uncaught exceptions:

- `missing_allowed_root`
- `missing_snapshot_file`
- `path_outside_allowed_root`
- `snapshot_path_not_file`
- `invalid_snapshot_extension`
- `invalid_json`
- `invalid_snapshot_schema`
- `unsupported_schema_version`
- `data_quality_not_passed`
- `invalid_as_of_time`
- `invalid_generated_at`
- `forbidden_trading_field`
- `credential_field_detected`
- `snapshot_read_error`

No error path returns partial trusted context.

## Testing

Tests build synthetic JSON files with `tmp_path`. They do not depend on real
snapshot files under `data/exports/`, do not read tokens, and do not call live
market data, LLM APIs, Tushare, Qlib, brokers, or network services.

The tests verify:

- valid snapshots under `allowed_root` can be loaded
- missing identity fields fail closed
- unsupported schema versions fail closed
- QA failures fail closed
- timezone-aware time fields are enforced
- path traversal and root escape are rejected
- the input file hash and mtime are unchanged after reading
- no order, position, target-weight, or auto-trade fields are produced

## Acceptance Record

- `read_research_snapshot(snapshot_path, allowed_root=...)` returns a read-only
  research context only after schema, QA, time, and path gates pass.
- The returned context sets `read_only: true`, `allowed_usage:
  "research_context_only"`, and `no_trading_decision: true`.
- The reader preserves `warnings`, `errors`, and `data_quality`.
- `git ls-files data/exports` must remain empty.
- No real snapshot JSON, credentials, cache files, reports, or API outputs are
  tracked by Git.
- Forbidden field names in implementation and tests are guardrails for rejection
  checks only; they are not generated as trading decisions.
- Stage 3A does not connect to agent prompts, analyst pipelines, live APIs,
  Tushare, LLM services, Qlib, backtesting, portfolio management, or automatic
  trading.
