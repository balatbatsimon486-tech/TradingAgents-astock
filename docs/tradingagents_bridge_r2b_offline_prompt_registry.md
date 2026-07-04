# R2B Offline Prompt Registry And Structured Research Output

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R2A is sealed on stable main at:

```text
bd7279e127c815c43ac760c2aa86a5ccf50fb1f5
```

R2A completed the provider-neutral offline LLM gateway, deterministic fake
provider, versioned request/response contract, audit hashes, structured errors,
credential and trading-field rejection, and dev/main CI gates.

R2B adds the next offline layer: prompt registry and structured research output
contracts. R2B does not call a real LLM and does not establish a multi-agent
workflow.

## Position In R2

R2A defines the model-call boundary. R2B controls which prompt may enter that
boundary and how the fake-provider output is normalized into a versioned
research-only result.

The offline chain is:

```text
validated synthetic research input
-> explicit prompt_id and prompt_version
-> prompt registry validation
-> deterministic prompt rendering
-> R2A fake gateway request
-> deterministic fake provider
-> structured research output validation
-> evidence-reference validation
-> prompt/output/audit hashes
-> versioned R2B result
```

## Goals

- keep prompts out of scattered code strings
- require explicit prompt IDs and versions
- require approved prompt status before execution
- compute stable prompt spec and rendered prompt hashes
- keep template paths inside the registry root
- reject implicit `latest` or `current` prompt versions
- treat research context as untrusted data
- validate evidence references for each claim
- reject credential and trading-execution fields recursively
- reuse the R2A gateway and deterministic fake provider
- produce a JSON-serializable stable result and expected-result regression

## Non-Goals

R2B does not:

- call a real provider or real LLM
- install or import model SDKs
- read API keys, tokens, auth files, or `.env`
- access the network
- call market data, Tushare, Qlib, or broker systems
- build Bull/Bear/Risk/Reviewer agents
- optimize prompts automatically
- choose a best prompt automatically
- evaluate returns, backtests, or prediction accuracy
- output BUY, SELL, HOLD, target prices, positions, weights, or orders

## Prompt Registry Schema

The registry is a single versioned JSON document:

```json
{
  "registry_id": "datang-tradingagents-prompts",
  "registry_version": "1.0",
  "prompts": [
    {
      "prompt_id": "institutional-research-brief",
      "prompt_version": "1.0.0",
      "status": "approved",
      "task_type": "research_generation",
      "system_template": "templates/system.txt",
      "user_template": "templates/user.txt",
      "required_variables": ["case_id", "snapshot_id", "research_context_json"],
      "optional_variables": [],
      "output_schema_id": "institutional-research-output",
      "output_schema_version": "1.0",
      "gateway_policy": {
        "provider_id": "fake",
        "model_id": "fake-deterministic-v1",
        "model_version": "1.0",
        "temperature": 0,
        "max_output_tokens": 512,
        "seed": 0
      },
      "metadata": {
        "research_only": true,
        "owner": "datang",
        "description": "Synthetic offline research prompt"
      }
    }
  ]
}
```

Supported `registry_version` is `1.0`. Unknown versions fail closed.

## Prompt Version Rules

Callers must pass both `prompt_id` and `prompt_version`. The registry performs
an exact lookup and never guesses.

Forbidden versions:

- empty version
- `latest`
- `current`
- automatic highest-version selection
- fallback to an older version

Missing exact versions return `prompt_not_found`.

## Prompt Approval Status

Only `status = approved` prompts can execute. Draft or retired prompts fail
closed with `prompt_not_approved`.

Prompt upgrades must create a new version. R2B treats silent in-place mutation
as a regression because the prompt spec hash changes.

## Template Path Safety

Templates must be relative UTF-8 text files under the registry root. R2B rejects:

- absolute paths
- `..` path traversal
- resolved paths outside the registry root
- symlink escape
- missing template files
- directories
- non-UTF-8 template files
- oversized templates

Prompt hashes never include absolute paths, mtime, load time, or the current
working directory.

## Safe Rendering

R2B uses Python `string.Formatter` only for simple placeholders such as:

```text
{case_id}
{snapshot_id}
{research_context_json}
```

R2B rejects:

- missing required variables
- unexpected variables
- attribute traversal
- format specs
- conversion flags
- nested expressions
- oversized rendered prompts

It does not support Python expressions, function calls, file include, loops,
conditionals, filters, macros, imports, shell, `eval`, or `exec`.

## Untrusted Research Data

`research_context_json` is canonical JSON generated from already validated
synthetic input. It is embedded as a data block. It cannot alter:

- provider policy
- prompt ID or version
- output schema
- gateway allowlists
- external-call flags

Prompt-injection text inside evidence is preserved as untrusted input data but
is not executed and is not allowed to create forbidden output fields.

R2B proves contract-level isolation only. It does not claim that a real model is
fully resistant to prompt injection.

## Prompt Hashes

`prompt_spec_hash` covers:

- registry version
- prompt ID and version
- approval status
- task type
- system and user template contents
- required and optional variables
- output schema identity
- gateway policy
- stable metadata

Canonical hashing uses sorted compact JSON encoded as UTF-8. The same content
loaded from different absolute directories produces the same prompt hash.

## Rendered Prompt Hashes

Rendered prompt output records:

- `prompt_id`
- `prompt_version`
- `prompt_spec_hash`
- `system_prompt`
- `user_prompt`
- `system_prompt_hash`
- `user_prompt_hash`
- `rendered_prompt_hash`
- `variables_hash`

`rendered_prompt_hash` covers prompt identity, prompt spec hash, rendered system
and user prompts, variables hash, and output schema identity.

## Structured Research Output Schema

R2B uses:

```text
output_schema_id = institutional-research-output
output_schema_version = 1.0
```

The output includes:

- `summary`
- `facts`
- `bull_case`
- `bear_case`
- `key_risks`
- `uncertainties`
- `research_stance`
- `confidence`
- `research_only`
- `not_a_trading_signal`
- `no_trading_decision`

`research_stance` is limited to:

- `positive`
- `neutral`
- `negative`
- `insufficient_evidence`

BUY, SELL, HOLD, STRONG_BUY, and STRONG_SELL are forbidden.

`confidence` is limited to `low`, `medium`, or `high`. It describes research
completeness only, not expected returns.

## Evidence Contract

Synthetic research input must include unique evidence records:

```json
{
  "evidence_id": "evidence-001",
  "text": "Synthetic positive evidence.",
  "source_ref": "synthetic://r2b/evidence-001"
}
```

R2B validates:

- safe unique `evidence_id`
- non-empty text
- non-empty source reference
- no credential-like fields
- no trading-execution fields
- bounded evidence count and text size

## Evidence Coverage

Each item in these sections must cite at least one known evidence ID:

- `facts`
- `bull_case`
- `bear_case`
- `key_risks`

Unknown references return `unknown_evidence_reference`. Empty references return
`uncited_research_claim`. Passing R2B output requires 100 percent claim citation
coverage.

## Credential And Trading Field Rejection

R2B recursively scans input and output keys. It rejects credential-like fields
such as:

- `token`
- `api_key`
- `secret`
- `password`
- `authorization`

It rejects trading-execution fields such as:

- `order`
- `order_size`
- `position_size`
- `target_weight`
- `portfolio_weight`
- `target_price`
- `execution_price`
- `broker`
- `auto_trade`

Errors report safe field paths and do not echo values.

## R2A Gateway Integration

R2B reuses `run_llm_gateway` and `DeterministicFakeProvider`. It does not create
a second provider interface and does not change the R2A request or response
semantics.

The R2B-built gateway request uses:

- `provider_id = fake`
- `model_id = fake-deterministic-v1`
- `temperature = 0`
- `allow_network = false`
- `allow_tools = false`
- `allow_market_data = false`
- `allow_trading_actions = false`

## R2B Result Schema

The result includes:

- `stage`
- `registry_version`
- pass/fail
- input lineage
- prompt identity and hashes
- output schema identity
- gateway request and response hashes
- structured research output hash
- result hash
- gateway request and result
- evidence metrics
- structured research output
- external-call flags
- warnings
- structured errors

`passed=true` requires registry validation, exact approved prompt lookup,
safe rendering, R2A gateway success, structured output validation, full evidence
coverage, research-only flags, no credential/trading fields, external-call flags
all false, and stable hashes.

## Expected Result Regression

`tests/tradingagents_bridge/fixtures/r2b/expected_result.json` stores stable
fields only:

- prompt identity and hashes
- gateway hashes
- output schema identity
- research output hash
- evidence metrics
- research output
- external-call flags
- pass/fail

It excludes output paths, timestamps, durations, machine paths, and temporary
IDs. Repeated runs with the same input must match this fixture.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_prompt_research.py `
  --input tests\tradingagents_bridge\fixtures\r2b\valid_research_input.json `
  --registry tests\tradingagents_bridge\fixtures\r2b\registry.json `
  --registry-root tests\tradingagents_bridge\fixtures\r2b `
  --prompt-id institutional-research-brief `
  --prompt-version 1.0.0 `
  --output-root "$smokeRoot" `
  --expected-result tests\tradingagents_bridge\fixtures\r2b\expected_result.json
```

Exit codes:

- `0`: R2B passed
- `1`: R2B rejected the input, registry, prompt, output, or regression
- `2`: CLI argument, JSON, or write error

The CLI does not accept real-provider parameters and does not read environment
model configuration.

## Windows Basetemp

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$testRoot = "C:\Users\22567\Documents\pytest_tmp_tradingagents_r2b\$stamp"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

.\.venv\Scripts\python.exe -m pytest `
  tests\tradingagents_bridge\test_offline_prompt_registry.py -q `
  --basetemp "$testRoot\r2b" `
  -p no:cacheprovider
```

## Synthetic Fixtures

R2B fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2b/
```

They are synthetic, deterministic, and contain no real market data, API keys,
private credentials, orders, positions, or actionable trading instructions.

## Explicit Prohibitions

R2B does not call a real LLM, read credentials, access the network, call market
data, call Tushare, call Qlib, call a broker, create multi-agent workflows, or
generate signals, target prices, positions, weights, or orders.

## R2C Status

R2C is not implemented. Real provider selection, prompt experiments,
multi-agent orchestration, and live research workflows remain blocked.

## Real Provider Go / No-Go

Before any real provider:

- R2A and R2B must pass local and CI gates
- credentials must have a separate non-printing secret boundary
- provider SDK imports must be isolated behind the gateway protocol
- provider calls must be disabled by default
- prompt registry approval must remain explicit
- logs must not echo credentials
- no trading execution fields may be introduced
- real LLM use must receive separate authorization
