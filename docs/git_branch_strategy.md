# TradingAgents-astock Git Branch Strategy

This document defines the branch policy for the Datang fork of
`simonlin1212/TradingAgents-astock`.

## Branch Roles

```text
main
```

`main` is used only to sync official upstream changes. Do not develop Datang
features directly on `main`.

```text
datang/main
```

`datang/main` is the stable Datang-enhanced branch. It contains upstream code
plus approved Datang extension work under `datang_extensions/`, supporting
docs, tests, scripts, and CI.

```text
datang/dev
```

`datang/dev` is the development integration branch for Datang-specific changes
before they are promoted to `datang/main`.

```text
feature/*
```

`feature/*` branches are used for small single-purpose changes, such as one
adapter improvement, one prompt version, or one test group.

```text
upgrade/*
```

`upgrade/*` branches are used to validate new upstream versions before they are
merged into `datang/main`.

## Remote Policy

Expected remotes:

```text
origin
your personal fork

upstream
https://github.com/simonlin1212/TradingAgents-astock.git
```

Check remotes:

```bash
git remote -v
```

Add upstream when missing:

```bash
git remote add upstream https://github.com/simonlin1212/TradingAgents-astock.git
```

Fetch upstream without merging:

```bash
git fetch upstream
```

## Bootstrap When Current Directory Is Not a Git Repository

Do not run `git init` inside an unrelated platform workspace just to make sync
commands work. Create or clone the TradingAgents-astock fork as its own Git
repository:

```bash
git clone https://github.com/<YOUR_USERNAME>/TradingAgents-astock.git
cd TradingAgents-astock
git remote add upstream https://github.com/simonlin1212/TradingAgents-astock.git
git remote -v
git fetch upstream
```

Then create the Datang branches:

```bash
git checkout main
git checkout -b datang/main
git checkout -b datang/dev
```

After the fork repository exists, copy or cherry-pick the Datang extension
files into that repository and run tests before pushing.

## Safe Upgrade Flow

```bash
git checkout main
git fetch upstream
git merge upstream/main
git push origin main

git checkout datang/main
git checkout -b upgrade/tradingagents-astock-YYYYMMDD
git merge main
python scripts/audit_datang_extension_boundary.py
python -m pytest tests/test_datang_astock_adapter.py -q
python -m pytest -q
```

Only merge the upgrade branch back to `datang/main` after conflicts are resolved
and tests pass.

## Boundary Rule

Datang custom work should stay in:

- `datang_extensions/`
- `docs/`
- `tests/`
- `.github/`
- `scripts/`
- `.gitignore`
- `reports/tradingagents_astock/.gitkeep`

Run the boundary audit before merging:

```bash
python scripts/audit_datang_extension_boundary.py
```

If the script prints `WARNING`, inspect the changed files before merging. A
warning usually means upstream core source may have been modified.

## Forbidden Changes

- Do not add real LLM API calls to tests or CI.
- Do not add real market data downloads to tests or CI.
- Do not add broker, order, or automatic trading interfaces.
- Do not commit `.env`, API keys, caches, or generated research reports.
