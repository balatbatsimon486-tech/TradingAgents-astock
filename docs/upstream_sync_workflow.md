# TradingAgents-astock Upstream Sync Workflow

This document describes how to keep a personal fork of
`simonlin1212/TradingAgents-astock` synced with the official upstream while
preserving Datang custom work in `datang_extensions/`.

## Branch Roles

Recommended long-lived branches:

```text
main
official upstream mirror plus safe merge commits

datang/main
stable Datang-enhanced branch

datang/dev
integration branch for Datang changes before promotion

feature/*
small feature branches

upgrade/*
temporary upstream upgrade assessment branches
```

Rules:

- Do not place Datang custom code inside upstream core directories unless a
  tiny compatibility patch is unavoidable.
- Keep Datang adapters, prompts, evaluation, and platform glue under
  `datang_extensions/`.
- Treat TradingAgents-astock as an AI research layer, not as the core quant
  model, backtest engine, risk system, portfolio optimizer, or trading system.

## 1. View Current Remotes

```bash
git remote -v
```

Expected meaning:

- `origin`: your personal GitHub fork.
- `upstream`: the official TradingAgents-astock repository.

## 2. Add Official Upstream

Run this once if `upstream` is absent:

```bash
git remote add upstream https://github.com/simonlin1212/TradingAgents-astock.git
```

Verify:

```bash
git remote -v
```

## 3. Fetch Official Updates

```bash
git fetch upstream
```

Optional inspection before merging:

```bash
git log --oneline --decorate --graph main..upstream/main
git diff --stat main..upstream/main
```

## 4. Sync Official Main into Local Main

```bash
git checkout main
git merge upstream/main
git push origin main
```

`main` should stay close to official upstream. Avoid doing Datang product work
directly on this branch.

## 5. Merge Synced Main into Datang Enhanced Branch

```bash
git checkout datang/main
git merge main
git push origin datang/main
```

If the update is large, use a temporary branch first:

```bash
git checkout datang/main
git checkout -b upgrade/tradingagents-astock-YYYYMMDD
git merge main
```

After conflicts, tests, and review are complete, merge the upgrade branch back
into `datang/main`.

## 6. Conflict Handling

When conflicts occur:

1. Run `git status` to list conflicted files.
2. Prefer the upstream version for official core behavior.
3. Preserve Datang custom behavior by moving it into `datang_extensions/` when possible.
4. For prompt or output changes, update the adapter and tests together.
5. Do not resolve conflicts by deleting upstream features blindly.
6. After editing conflicts, run:

```bash
git add <resolved-files>
git commit
```

If a conflict touches output format, also update:

- `datang_extensions/adapters/json_schema.py`
- `datang_extensions/adapters/astock_report_adapter.py`
- `tests/test_datang_astock_adapter.py`
- `docs/upstream_sync_log.md`

## 7. Required Tests After Every Sync

Always run the Datang adapter tests:

```bash
python -m pytest tests/test_datang_astock_adapter.py -q
```

If the project has a full test suite, also run:

```bash
python -m pytest -q
```

If upstream introduces optional dependencies or network behavior, tests must use
mocks or dry-run mode. Do not require real LLM APIs, broker APIs, or real market
downloads for basic adapter acceptance.

## 8. Required Sync Record

After every upstream sync, append an entry to:

```text
docs/upstream_sync_log.md
```

Record at least:

- sync date
- upstream repository
- upstream commit
- local branch
- target Datang branch
- changed files
- conflicts and resolution
- tests run
- test result
- demo result if any
- breaking changes
- impact on `datang_extensions/`
- whether safe to use
- next action

## 9. Safety Gates

The synced branch is not ready for research use until:

- adapter tests pass
- full tests pass or failures are documented as unrelated
- Markdown and JSON report generation still works
- `error` fallback works for failed LLM/API calls
- `final_signal` remains a research-layer field, not an executable order
- no `.env`, API key, cache, or real generated report is committed

