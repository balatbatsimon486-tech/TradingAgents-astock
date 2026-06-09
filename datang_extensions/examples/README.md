# Offline Examples

This directory contains small synthetic fixtures for Datang extension smoke
tests. They do not contain API keys, private data, live market data, or real
research conclusions.

`offline_sample_input.json` mimics a TradingAgents-astock multi-agent result and
is used to validate the Markdown and JSON output adapters without calling an
LLM, a market data provider, Tushare, or a broker.
