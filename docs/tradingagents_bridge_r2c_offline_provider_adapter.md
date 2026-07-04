# R2C-A Offline Provider Adapter Contract

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R2A and R2B are sealed on dev and stable main at:

```text
16da82868393b499b1c07ccce2fc0e13e4ac00d0
```

R2C-A adds the offline provider adapter contract. It defines how a future real
provider must be configured, mapped, normalized, redacted, budgeted, retried,
and audited. It still does not call a real provider.

## Position In R2

R2A defines the provider-neutral gateway boundary. R2B controls prompt registry
and structured research output. R2C-A sits behind the R2A provider protocol and
proves that an adapter can map an R2A request into a provider-shaped wire
request, receive a provider-shaped fake transport response, and normalize it
back into an R2A provider response.

The offline chain is:

```text
R2B structured prompt request
-> R2A gateway request
-> provider adapter policy validation
-> provider wire request mapping
-> fake transport
-> provider-shaped wire response
-> response normalization
-> R2A provider response
-> audit, redaction, budget, and retry result
```

## Goals

- implement the existing R2A `LLMProvider` protocol
- keep transport as a separate `ProviderTransport` boundary
- allow only fake transport in this stage
- validate provider adapter config before use
- keep live mode fail-closed
- map requests deterministically
- compute stable wire request, wire response, and normalized response hashes
- use a deterministic idempotency key
- normalize provider-shaped responses into R2A provider responses
- classify retryable and non-retryable errors
- enforce attempt, token, cost, and response-size budgets
- redact sensitive headers and error messages
- keep audit records free of credential values

## Non-Goals

R2C-A does not:

- install, import, or call OpenAI, Anthropic, Google, or any model SDK
- read API keys, tokens, auth files, cookies, or `.env`
- read `os.environ` or use `os.getenv`
- create a real HTTP transport
- open sockets or perform DNS, TLS, proxy, or OAuth work
- call market data, Tushare, Qlib, or broker systems
- create multi-agent workflows
- generate signals, recommendations, target prices, positions, weights, or orders

## Adapter And R2A Provider Relationship

`ChatProviderAdapter` implements the same shape consumed by the R2A gateway:

```python
class LLMProvider(Protocol):
    provider_id: str

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        ...
```

The adapter may be injected into `run_llm_gateway`. On success, it returns an
R2A provider response. On failure, the direct R2C runner exposes structured
adapter errors; through R2A, provider failures remain gateway-controlled.

## Adapter And Transport Layering

The adapter owns:

- provider config validation
- request mapping
- budget checks
- retry classification
- response normalization
- redaction and audit summaries

The transport owns only:

- accepting a sanitized provider wire request
- returning a provider-shaped fake transport result

No transport in R2C-A can access real network resources.

## Fake Provider Versus Fake Transport

R2A `DeterministicFakeProvider` directly simulates the internal provider
response expected by the gateway.

R2C-A `FakeProviderTransport` simulates an external provider's wire protocol:
status code, headers, body, elapsed milliseconds, timeout flag, and transport
error category. The adapter must then perform the real mapping and
normalization work.

## Provider Config Schema

The provider adapter config includes:

- `adapter_contract_version`
- `adapter_id`
- `adapter_version`
- `provider_id`
- `model_id`
- `model_version`
- `enabled`
- `live_mode_enabled`
- `transport_kind`
- `endpoint_policy`
- `credential_binding_id`
- `limits`

Unknown contract versions fail closed. `enabled` must be explicitly true for
this conformance fixture. `live_mode_enabled` must be false. `transport_kind`
must be `fake`.

## Credential Binding Rules

R2C-A records only an opaque `credential_binding_id`, such as:

```text
provider-credential-slot-test
```

It rejects environment references, path-like values, URL-like values, bearer
tokens, and secret-looking prefixes. R2C-A does not provide a credential
resolver and never attempts to read the real credential value.

All audit and CLI outputs record:

- whether a binding exists
- `credential_value_resolved=false`

They do not record credential values, Authorization headers, cookies, or full
request headers.

## Endpoint Policy

Endpoint policy is validated but never used to connect. It must declare:

- `scheme=https`
- a synthetic `.invalid` host
- an absolute path identity
- redirects disabled
- proxy disabled

The validator rejects localhost, private IPs, file schemes, redirects, proxy
use, relative endpoints, and caller-injected endpoints.

## Live Kill Switch

`live_mode_enabled=true` fails closed. R2C-A has no live provider mode and no
real HTTP transport. This is a contract gate for future R2C stages, not a live
sandbox.

## Wire Request Mapping

The adapter maps an R2A request into a provider-shaped request with:

- method `POST`
- synthetic endpoint identity
- sanitized headers
- canonical body
- timeout limit
- attempt number
- stable `wire_request_hash`
- stable `idempotency_key`

The canonical body contains:

- `model`
- system and user messages
- `temperature`
- `max_tokens`
- `seed`

Unknown provider parameters fail closed. Callers cannot inject endpoints,
headers, tools, function calling, streaming, response-format escape hatches,
timeouts, retry policy, or endpoint policy.

## Idempotency

The idempotency key is deterministic:

```text
sha256(adapter_id + adapter_version + wire_request_hash)
```

It does not use current time, random UUIDs, user paths, or process state.

## Wire Response Contract

Fake transport results include:

- `status_code`
- `headers`
- `body`
- `elapsed_ms`
- `timeout`
- `transport_error`

Successful provider-shaped bodies include:

- response id
- model id
- exactly one assistant choice
- object content
- finish reason
- usage

Fixtures are synthetic and do not represent a real provider.

## Response Normalization

The adapter normalizes a provider-shaped response into the R2A response schema:

- `response_schema_version`
- provider and model identity
- request id
- structured content
- usage
- finish reason
- safe provider metadata

It records raw wire response and normalized response hashes. It strips
Authorization, Cookie, Set-Cookie, and secret-like error text.

## Redaction Rules

R2C-A redacts:

- Authorization headers
- Cookie and Set-Cookie
- secret-looking string values
- sensitive provider errors

It preserves safe metadata such as `content-type`, `x-request-id`,
`adapter_id`, `adapter_version`, and `transport_kind`.

## Retry Classification

Retryable:

- timeout
- 408
- 429
- 500
- 502
- 503
- 504

Non-retryable:

- 400 invalid request
- 401 authentication failed
- 403 permission denied
- 404 model or endpoint not found
- malformed successful response
- credential or trading field detected
- budget exceeded
- provider/model identity mismatch

Retries are bounded by config. R2C-A records planned delay only and performs no
real sleep or backoff wait.

## Budget And Cost

R2C-A enforces:

- max attempts
- timeout upper bound
- max input tokens
- max output tokens
- max total tokens
- max response bytes
- max synthetic cost

Token and cost estimates are deterministic contract checks. They are not real
provider billing queries.

## Adapter Audit

The adapter result records:

- request id and hash
- provider/model identity
- adapter identity
- transport kind
- live mode disabled
- credential binding presence
- `credential_value_resolved=false`
- wire request hash
- idempotency key
- wire response hash
- normalized response hash
- retry count and attempt count
- error codes
- external-call flags

External-call flags remain false:

```json
{
  "network_called": false,
  "market_data_called": false,
  "tushare_called": false,
  "qlib_called": false,
  "broker_called": false
}
```

## Structured Errors

R2C-A returns safe errors with:

- `code`
- `message`
- `field_path`

Representative codes include:

- `unsupported_adapter_contract_version`
- `adapter_disabled`
- `live_mode_not_allowed`
- `transport_not_allowed`
- `endpoint_policy_rejected`
- `credential_binding_invalid`
- `limit_out_of_range`
- `provider_request_rejected`
- `unknown_provider_parameter`
- `token_budget_exceeded`
- `cost_budget_exceeded`
- `response_size_exceeded`
- `provider_retry_exhausted`
- `provider_authentication_failed`
- `provider_permission_denied`
- `provider_malformed_json`
- `usage_validation_failed`
- `credential_field_detected`
- `forbidden_trading_field_detected`

Errors never echo credential values.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_fake_provider_adapter.py `
  --request tests\tradingagents_bridge\fixtures\r2c\gateway_request.json `
  --provider-config tests\tradingagents_bridge\fixtures\r2c\provider_config.json `
  --fixture-map tests\tradingagents_bridge\fixtures\r2c\wire_responses `
  --output-root "$smokeRoot"
```

Exit codes:

- `0`: adapter passed
- `1`: adapter rejected request or response
- `2`: argument, config, fixture, JSON, or output error

The CLI prints a safe summary to stdout and writes `adapter_result.json` only to
the explicit output root.

## Synthetic Fixtures

R2C fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2c/
```

They are synthetic and contain no real credentials, provider endpoints, market
data, orders, positions, target prices, or actionable trading instructions.

## External-Call Isolation

Tests block sockets, environment credential lookup, common network libraries,
model SDK imports, Tushare, Qlib, and broker-like dependencies. Production R2C-A
does not import real SDKs, HTTP clients, dotenv, socket, shell helpers, or
credential resolvers.

## R2C-B And R2C-C

R2C-B and R2C-C are not implemented. Real sandbox access, real credential
binding, endpoint allowlists, model-specific SDK adapters, and live request
windows remain blocked.

## Real Sandbox Go / No-Go

Real provider sandbox access requires a separate authorization after all of the
following are complete:

- R2C-A local Dev Gate
- Dev CI
- Stable Main Gate
- manual review of secret binding design
- manual approval of endpoint allowlist
- manual approval of token and cost budgets
- kill switch tests
- redaction tests
- 401/403/429/5xx classification tests
- no-network tests
- separate non-production credentials
- hard spend limit
- single-case sandbox scope
- no tools
- no streaming
- no production platform data
- no trading or order impact
- manually approved live-call window

R2C-A cannot satisfy these conditions by itself and cannot enter live mode.
