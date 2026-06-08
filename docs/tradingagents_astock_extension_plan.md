# TradingAgents-astock Datang Extension Plan

## Positioning

TradingAgents-astock is used only as an A-share AI multi-agent research layer.
It may support individual stock analysis, policy interpretation, sentiment
review, hot-money review, lockup risk notes, research-style writing, and
hypothesis generation.

It does not own market truth data, factor calculation, backtesting, portfolio
optimization, position sizing, risk execution, or automatic trading.

## Engineering Boundaries

- Official TradingAgents-astock code should remain as close to upstream as possible.
- Datang custom code lives under `datang_extensions/`.
- Output is normalized into Markdown and JSON before entering the main platform.
- LLM/API failures are converted into structured `error` reports.
- LLM conclusions are research evidence only and must not be treated as verified alpha.

## Data Flow

```text
TradingAgents-astock raw result
        |
        v
datang_extensions.adapters.astock_report_adapter
        |
        +--> Markdown research report
        |
        +--> Standard JSON report
                    |
                    v
datang_extensions.adapters.quant_platform_adapter
                    |
                    v
future datang-quant-platform research ingestion
```

## Standard Output Contract

The JSON report must contain the fields defined in
`datang_extensions/adapters/json_schema.py`.

`final_signal` uses research-layer values:

- `research_buy`
- `research_hold`
- `research_sell`
- `no_actionable_signal`
- `analysis_failed`

These values are not executable trading signals. The platform adapter always
sets `execution_policy.is_trade_order` to `false`.

## Next Integration Stage

Before connecting to `datang-quant-platform`, define:

- report ingestion location
- research report registry table or manifest
- allowed symbol/date universe
- offline evaluation samples
- cost budget policy
- human review workflow

