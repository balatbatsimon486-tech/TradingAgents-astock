# Stage 2 Offline Report Ingestion

Stage 2 adds an end-to-end offline smoke path for Datang's
TradingAgents-astock extension layer. It validates that a synthetic
TradingAgents-style result can be converted into standard Markdown, JSON, and
smoke metadata without calling any external service.

## Scope

This stage is limited to offline adapter validation:

- no real LLM API calls
- no live market data calls
- no Tushare calls
- no broker or automatic trading integration
- no production connection to the main Datang quant platform

The generated output is a research artifact only. AI Buy/Hold/Sell text is
normalized into research-layer values and must not be treated as a tradable
signal.

## Offline Input

Default input:

```text
datang_extensions/examples/offline_sample_input.json
```

The fixture is synthetic and contains fields such as:

- `symbol`
- `trade_date`
- `policy_summary`
- `sentiment_summary`
- `technical_summary`
- `fundamental_summary`
- `hot_money_summary`
- `lockup_summary`
- `raw_text`
- `model_name`
- `analysis_mode`
- `final_signal`

It contains no API keys, private data, live market data, or real research
conclusions.

## Outputs

Default output directory:

```text
reports/tradingagents_astock/offline_smoke/
```

The smoke path writes:

- Markdown research report
- standard JSON report
- smoke metadata JSON

This directory is ignored by Git through the existing
`reports/tradingagents_astock/*` rule. Only
`reports/tradingagents_astock/.gitkeep` should be committed.

## JSON Contract

The standard report JSON must contain exactly the fields defined by
`datang_extensions/adapters/json_schema.py`:

```text
symbol
trade_date
source
upstream_commit
datang_extension_version
run_time_utc
llm_model
analysis_mode
final_signal
confidence
risk_flags
policy_summary
sentiment_summary
technical_summary
fundamental_summary
hot_money_summary
lockup_summary
raw_report_path
json_report_path
error
```

`final_signal` is normalized to one of:

- `research_buy`
- `research_hold`
- `research_sell`
- `no_actionable_signal`
- `analysis_failed`

These values are research labels only. They are not orders, strategy signals,
factor values, or risk-control instructions.

## Run The Smoke

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_report_smoke.py
```

Optional paths:

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_report_smoke.py `
  --input datang_extensions\examples\offline_sample_input.json `
  --output-dir reports\tradingagents_astock\offline_smoke
```

## Failure Behavior

Missing required input fields do not crash the smoke path. They produce a
standard JSON report with an `error` field and a non-tradable `final_signal`.

Output failures are surfaced as structured Python results during tests. The
smoke metadata records whether an LLM, market data provider, Tushare, broker,
or trade order path was used. For Stage 2 all of those flags must remain false.

## Future Platform Adapter

Future work may add a Datang quant platform ingestion adapter that reads the
standard JSON report. Stage 2 does not connect to that production path; it only
proves that the offline report contract is readable and stable.
