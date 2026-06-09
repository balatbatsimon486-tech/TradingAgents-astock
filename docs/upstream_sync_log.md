# TradingAgents-astock Upstream Sync Log

Append a new entry after every upstream sync or upgrade assessment.

## 2026-06-09 Stage 1A-1C governance checkpoint

- upstream repo: `https://github.com/simonlin1212/TradingAgents-astock.git`
- upstream commit: `72aa2d20020b824817a3b125e11b9a210c9d424b`
- local governance commit: `113023c`
- local branch at documentation update: `datang/main`
- branch status:
  - `datang/dev`: pushed to `origin/datang/dev` at `113023c`; CI passed.
  - `datang/main`: pushed to `origin/datang/main` at `113023c`; aligned with `datang/dev`.
  - `main`: remains the fork's upstream-aligned baseline branch.
- current branch strategy:
  - Keep official TradingAgents-astock core changes isolated from Datang governance work.
  - Use `datang/dev` for Datang extension development and validation.
  - Promote to `datang/main` only after audit, targeted pytest, full pytest, and CI pass.
  - Do not directly merge upstream into Datang branches without a review of extension impact.
- completed stages:
  - Stage 1A: verified real fork repository, remotes, upstream tracking, and branch hygiene.
  - Stage 1B: migrated the Datang extension governance layer into allowed paths only.
  - Stage 1C: established reproducible test environment, CI install strategy, audit coverage, and tests.
- changed files scope:
  - `datang_extensions/`
  - `docs/`
  - `scripts/audit_datang_extension_boundary.py`
  - `.github/workflows/tests.yml`
  - `requirements-dev.txt`
  - `tests/`
  - `reports/tradingagents_astock/.gitkeep`
  - `.gitignore`
- official core source status: not modified (`tradingagents/`, `cli/`, and `web/` left untouched).
- extension responsibility:
  - output adaptation
  - governance documentation
  - boundary audit and tests
  - future adapter path into the main Datang quant platform
- explicit non-goals:
  - no automatic trading
  - no core backtesting engine
  - no portfolio execution or risk execution
  - no treating AI Buy/Hold/Sell conclusions as verified tradable signals
- tests recorded at Stage 1C:
  - `.\.venv\Scripts\python.exe scripts\audit_datang_extension_boundary.py` -> `Boundary check: OK`
  - `.\.venv\Scripts\python.exe -m pytest tests\test_datang_astock_adapter.py -q` -> `6 passed`
  - `.\.venv\Scripts\python.exe -m pytest tests\test_git_governance.py -q` -> `6 passed`
  - `.\.venv\Scripts\python.exe -m pytest -q` -> `119 passed, 1 skipped, 44 subtests passed`
- whether safe to use: safe as a research-output governance layer; not safe as a trading signal source.
- next action: continue future Datang work on `datang/dev`, keep upstream sync reviews explicit, and re-run audit plus pytest before promotion.

```text
## YYYY-MM-DD upstream sync

- upstream repo:
- upstream commit:
- local branch:
- merged into:
- changed files:
- conflicts:
- resolved by:
- tests run:
- test result:
- demo result:
- breaking changes:
- impact on datang_extensions:
- whether safe to use:
- next action:
```
