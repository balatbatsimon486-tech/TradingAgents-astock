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
- The extension layer does not modify official core source under `tradingagents/`, `cli/`, or `web/`.
- The extension layer does not connect to broker APIs, automatic trading, portfolio execution, or core backtesting.

## Stage 1A-1C Status

Stage 1A through Stage 1C are complete at commit `113023c`.

- Stage 1A: verified the real TradingAgents-astock fork, remotes, upstream tracking, and branch hygiene.
- Stage 1B: migrated the Datang extension layer into allowed governance paths only.
- Stage 1C: established reproducible test environment documentation, CI install strategy, boundary audit, and pytest coverage.

Branch status:

- `datang/dev` is pushed to `origin/datang/dev` at `113023c`; CI passed.
- `datang/main` is pushed to `origin/datang/main` at `113023c` and is aligned with `datang/dev`.
- `main` remains the upstream-aligned baseline branch.

Current branch strategy:

- Use `datang/dev` for ongoing Datang extension work.
- Promote to `datang/main` only after audit, targeted tests, full pytest, and CI pass.
- Keep upstream syncs explicit and review their impact on `datang_extensions/` before promotion.

Current enhancement scope:

- output adaptation
- governance documentation
- boundary audit and tests
- future adapter integration into the main Datang quant platform

Explicit non-goals:

- no automatic trading
- no core market-truth data ownership
- no factor engine ownership
- no core backtesting system
- no portfolio optimization or risk execution
- no treating AI Buy/Hold/Sell output as a verified tradable signal

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
