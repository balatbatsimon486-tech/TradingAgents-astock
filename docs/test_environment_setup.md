# Test Environment Setup

This fork uses `pyproject.toml` as the source of truth for runtime
dependencies. The base install is editable because the repository is a Python
package with a PEP 517 build backend and package discovery configured in
`pyproject.toml`.

`requirements-dev.txt` is intentionally minimal. It only adds test tooling. It
does not replace the runtime dependency list in `pyproject.toml`.

Google Gemini support is an optional runtime extra in `pyproject.toml`. It is
not installed by default for CI because its current SDK stack requires
`httpx>=0.28`, while `mootdx` requires `httpx<0.26`. Google-specific tests use
`pytest.importorskip` and should be run in a separate optional-provider
environment when that compatibility tradeoff is intentional.

## Windows Local Environment

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If the Windows `py` launcher is not available, use any installed Python 3.10+
interpreter:

```powershell
C:\Path\To\Python\python.exe -m venv .venv
```

The local `.venv` directory is ignored by Git and must not be committed.

## Required Checks

Run the boundary audit first:

```powershell
.\.venv\Scripts\python.exe scripts\audit_datang_extension_boundary.py
```

Run the Datang A-stock adapter tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_datang_astock_adapter.py -q
```

Run the Git governance tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_git_governance.py -q
```

Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## API Keys And External Services

Unit tests must not require real LLM API keys, broker credentials, or live
market data. `tests/conftest.py` injects placeholder API keys so constructors
can be tested without reaching real providers.

If a future test genuinely needs a real LLM, real market data, or any external
service, mark it with `@pytest.mark.integration` and keep it out of the default
CI path until it has a mock, fixture recording, or explicit integration-test
job. Do not delete upstream tests just to make the suite pass.

Google provider constructor tests do not call the real Google API. They are
skipped unless the optional Google dependency is installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[google]"
.\.venv\Scripts\python.exe -m pytest tests\test_google_api_key.py -q
```

Use a separate environment for this optional check if you also need to validate
the default A-stock data stack, because the Google SDK and `mootdx` currently
disagree on the supported `httpx` range.

To run only non-integration tests when investigating external-service failures:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not integration"
```

## Diagnosing Failures

Use this split before changing code:

- Dependency issue: collection fails with `ModuleNotFoundError` for packages
  declared in `pyproject.toml` or `requirements-dev.txt`. Reinstall the
  environment before editing source.
- API key issue: a test asks for a real provider key or fails with provider
  authentication. Unit tests should mock this path or use placeholders.
- External service issue: failures mention network timeouts, rate limits, live
  quote downloads, or provider HTTP responses. Mark the test as integration or
  replace the live call with a fixture or mock.
- Code issue: dependencies are installed, no live service is involved, and an
  assertion or exception points to local behavior. Fix the narrow code path and
  add or update a focused test.

## Research Signal Boundary

TradingAgents-astock output is research evidence only. AI-generated
Buy/Hold/Sell text must not be treated as a verified trading signal, factor
input, portfolio order, risk-control action, or automatic trading instruction.

