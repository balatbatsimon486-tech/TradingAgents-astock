# R2A Offline Auditable LLM Gateway

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R1 is sealed on stable main at:

```text
5ff7c00784d09a662f6b31117fc5e88bb147963d
```

Completed R1 stages:

- Stage 1 extension governance and boundaries
- Stage 2 offline report ingestion
- Stage 3A read-only research snapshot consumer
- M2A single-case offline research evaluation
- M2B multi-case offline benchmark
- dev and stable-main CI gates

R2A starts R2 by defining the offline model-call boundary. It does not call a
real model.

## Position In R2

R2A is the first R2 layer. It defines the request, response, audit, hash, error,
and provider protocol that any later real model provider must obey.

R2B is not implemented. Multi-agent workflows are not implemented.

## Goals

- define a provider-neutral gateway contract
- validate versioned requests and responses
- enforce provider and model allowlists
- preserve prompt, snapshot, and input artifact lineage
- produce stable SHA-256 hashes
- return deterministic fake-provider output
- represent provider failures as structured errors
- reject credential and trading-execution fields recursively
- prove the gateway is offline, research-only, and auditable

## Non-Goals

R2A does not:

- call OpenAI, Anthropic, Google, or any real LLM
- install or import real model SDKs
- read API keys, tokens, auth files, or `.env`
- access the network
- call market data, Tushare, Qlib, or broker systems
- build multi-agent workflows
- generate real research conclusions
- generate signals, recommendations, positions, weights, or orders

## Gateway Architecture

```text
validated research input
-> versioned LLM request
-> gateway policy validation
-> deterministic fake provider
-> versioned provider response
-> response validation
-> request/response hashes
-> audit record
-> structured gateway result
```

The gateway receives an in-memory request object. It does not read snapshots,
does not create a second Stage 3A reader, does not run M2A evaluation, and does
not run the M2B benchmark.

## Request Schema

Required request fields:

- `gateway_contract_version`
- `request_schema_version`
- `request_id`
- `task_type`
- `case_id`
- `snapshot_id`
- `input_artifact_id`
- `input_artifact_hash`
- `prompt_id`
- `prompt_version`
- `provider_id`
- `model_id`
- `model_version`
- `parameters`
- `input_payload`
- `policy`

The fake-provider stage requires:

- `gateway_contract_version = "1.0"`
- `request_schema_version = "1.0"`
- `provider_id = "fake"`
- `model_id = "fake-deterministic-v1"`
- `temperature = 0`
- fixed integer `seed`
- safe `max_output_tokens`
- `policy.research_only = true`
- all external capability policy flags set to false

Unknown versions fail closed.

## Response Schema

Required response fields:

- `response_schema_version`
- `provider_id`
- `model_id`
- `model_version`
- `request_id`
- `content`
- `usage`
- `finish_reason`
- `provider_metadata`

The structured content must include:

- `summary`
- `bull_case`
- `bear_case`
- `key_risks`
- `uncertainties`
- `evidence_refs`
- `research_only = true`
- `not_a_trading_signal = true`
- `no_trading_decision = true`

The response is a contract fixture. It is not a real research report.

## Provider Protocol

The gateway depends only on a minimal provider protocol:

```python
class LLMProvider(Protocol):
    provider_id: str

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...
```

Provider identity must match the request. Provider exceptions are converted into
structured gateway errors.

## Fake Provider

`DeterministicFakeProvider` is fully offline and deterministic. It derives fixed
content from the canonical request hash and optional synthetic fixture-map
entries. It does not read the current time, environment variables, user paths,
network state, or real model SDKs.

Controlled test modes:

- `fake_provider_mode = "raise"` returns `provider_execution_failed`
- `fake_provider_mode = "invalid_response"` returns a response that fails
  response validation

## Gateway Result

The public result includes:

- `stage`
- `gateway_contract_version`
- `passed`
- `request_id`
- `request_hash`
- `response_hash`
- `normalized_response_hash`
- provider/model identity
- prompt identity
- snapshot lineage
- input artifact lineage
- `usage`
- fake `cost`
- fixed `latency`
- `retry_count`
- `finish_reason`
- `external_calls`
- `response`
- `audit`
- `warnings`
- `errors`

For R2A, cost is always zero and latency is a fixed contract field, not a real
performance measurement.

## Audit Record

The audit record includes:

- `audit_schema_version`
- request id and hashes
- provider and model identity
- prompt id and version
- snapshot id
- input artifact id and hash
- usage
- fake cost
- retry count
- finish reason
- pass/fail
- error codes
- external-call flags

No database is required for R2A. The audit record is embedded in the result.

## Provider And Model Allowlist

R2A allows only:

```text
provider_id = fake
model_id = fake-deterministic-v1
```

Unknown providers and models fail closed. The gateway never guesses a provider
from a model name.

## Prompt Identity

Every request must include `prompt_id` and `prompt_version`. The gateway records
both in the result and audit record. Missing or unsafe identifiers fail closed.

## Snapshot Lineage

Every request must include `snapshot_id`. R2A does not read the snapshot file.
The caller must provide already validated lineage from an upstream R1 artifact or
research input.

## Artifact Lineage

Every request must include `input_artifact_id` and `input_artifact_hash`.
`input_artifact_hash` must be a lowercase SHA-256 string.

## Hash And Normalization

Hashes use canonical JSON:

- UTF-8
- sorted keys
- compact separators
- deterministic dictionaries
- no current time
- no temporary paths
- no generated request ids

Recorded hashes:

- canonical request hash
- raw response hash
- normalized response hash

Normalized response hashing excludes known volatile fields such as duration and
generated time fields. The fake provider avoids volatile fields by design.

## Usage, Cost, Latency, Retry

`usage` requires non-negative integer `input_tokens`, `output_tokens`, and
`total_tokens`. `total_tokens` must equal input plus output.

R2A fake provider uses:

- `cost.currency = "USD"`
- `cost.amount = 0`
- `latency.duration_ms = 0`
- `retry_count = 0`

## Error Codes

R2A structured error codes include:

- `invalid_gateway_request`
- `unsupported_gateway_contract_version`
- `unsupported_request_schema_version`
- `unsupported_response_schema_version`
- `provider_not_allowed`
- `model_not_allowed`
- `provider_identity_mismatch`
- `model_identity_mismatch`
- `request_id_mismatch`
- `invalid_model_parameters`
- `invalid_input_artifact_hash`
- `credential_field_detected`
- `forbidden_trading_field_detected`
- `provider_execution_failed`
- `provider_response_invalid`
- `usage_validation_failed`
- `lineage_validation_failed`
- `external_call_detected`
- `gateway_error`

Errors record field paths and safe context only. They do not echo secret values.

## Credential And Trading Field Rejection

The gateway recursively rejects credential-like fields in request payloads,
provider content, provider metadata, and audit-adjacent structures. Examples:

- `token`
- `api_key`
- `secret`
- `password`
- `access_key`
- `private_key`
- `authorization`
- `cookie`
- `credential`

It also recursively rejects trading-execution fields such as:

- `order`
- `order_size`
- `position`
- `position_size`
- `target_weight`
- `portfolio_weight`
- `execution_price`
- `broker`
- `auto_trade`
- `stop_loss_order`
- `take_profit_order`

Synthetic negative fixtures may include placeholder keys to prove rejection.
They are not real credentials.

## External Call Isolation

Gateway results always record:

```json
{
  "network_called": false,
  "market_data_called": false,
  "tushare_called": false,
  "qlib_called": false,
  "broker_called": false
}
```

Tests block sockets, common network libraries, model SDK imports, Tushare, Qlib,
and broker-like dependencies. The production gateway does not import those
dependencies.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_fake_llm_gateway.py `
  --request tests\tradingagents_bridge\fixtures\r2a\valid_request.json `
  --output-root "$smokeRoot"
```

Exit codes:

- `0`: gateway `passed=true`
- `1`: gateway rejection
- `2`: argument, request, fixture-map, or output write error

The CLI writes `gateway_result.json` only under the explicit output root and
prints a JSON summary to stdout.

## Windows Basetemp

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$testRoot = "C:\Users\22567\Documents\pytest_tmp_tradingagents_r2a\$stamp"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null

.\.venv\Scripts\python.exe -m pytest `
  tests\tradingagents_bridge\test_offline_llm_gateway.py -q `
  --basetemp "$testRoot\r2a" `
  -p no:cacheprovider
```

## Synthetic Fixtures

R2A fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2a/
```

They are fully synthetic, deterministic, and not real research. They contain no
real API keys, private data, live market data, positions, orders, or actionable
trading instructions.

## Explicit Prohibitions

R2A does not call a real LLM, read API keys, access the network, create
multi-agent workflows, produce signals, produce positions, or produce orders.

## R2B Status

R2B is not implemented. Real provider selection, prompt experiments,
multi-agent orchestration, and quality ranking remain blocked.

## Real Provider Go / No-Go

Before any real provider:

- R2A must pass local and CI gates
- credentials must have a separate non-printing secret boundary
- provider SDK imports must be isolated behind the gateway protocol
- provider calls must be disabled by default
- model/provider allowlists must be explicit
- logging must not echo prompts containing credentials
- no trading execution fields may be introduced
- real LLM use must receive separate authorization
