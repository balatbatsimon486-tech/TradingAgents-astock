# Datang TradingAgents-astock Extensions

`datang_extensions/` is the only long-lived customization layer for the fork of
`simonlin1212/TradingAgents-astock`.

Scope:

- Convert TradingAgents-astock research output into stable Markdown and JSON.
- Add Datang-specific prompt overlays, evaluation helpers, and platform adapters.
- Keep AI research separated from core market data, factor calculation, backtest,
  portfolio construction, risk execution, and trading.

Non-goals:

- No automatic trading.
- No replacement of the main Datang quant data pipeline.
- No direct use of LLM output as a validated alpha or executable signal.

Directory roles:

- `adapters/`: output contracts and integration adapters.
- `prompts/`: Datang prompt overlays and version records.
- `evaluation/`: cost tracking and signal audit helpers.
- `utils/`: safe IO and run metadata helpers.

Default report output path:

```text
reports/tradingagents_astock/
```

The report output directory should stay ignored by Git except for placeholders.

