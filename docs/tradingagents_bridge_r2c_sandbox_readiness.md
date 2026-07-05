# R2C-C Offline Sandbox Readiness Gate

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R2A, R2B, R2C-A, and R2C-B are sealed on dev and stable main. The stable baseline for this readiness review is:

```text
65a396120a5734b7e06855000c84e7a2e581b617
```

R2C-C adds a fully offline safety review and readiness package for a future provider sandbox. It does not perform a real provider call.

## Position In R2

R2C-C combines evidence from:

- R2A offline gateway contract
- R2B prompt registry and structured research output contract
- R2C-A provider adapter contract and fake transport controls
- R2C-B secret binding, policy, approval, grant, and audit controls

The output can only reach:

```text
ready_for_human_review
```

It cannot reach:

```text
human_review_completed
secret_resolution_authorized
network_execution_authorized
live_execution_authorized
```

## Readiness Is Not Live Authorization

A passed readiness package means the proposed sandbox profile, secret storage proposal, egress policy, run manifest, threat model, evidence bundle, kill switch, and incident plan are internally consistent and auditable.

It does not authorize a live call, resolve a credential, access a real endpoint, call a provider SDK, call a real LLM, or consume an R2C-B grant.

The required success booleans are:

```json
{
  "ready_for_human_review": true,
  "human_review_completed": false,
  "secret_resolution_authorized": false,
  "network_execution_authorized": false,
  "live_execution_authorized": false,
  "credential_value_resolved": false,
  "provider_transport_called": false
}
```

## Sandbox Profile

The sandbox profile is a draft-for-review profile. It records only identities and constraints:

- provider id
- model id
- adapter id and version
- binding id
- authorization policy id
- sandbox environment
- single-case purpose
- research-generation task type
- single-call maximum

It must keep tools, streaming, fallback, production data, and trading actions disabled.

## Secret Storage Proposal

The secret storage proposal describes a future externally managed secret store requirement. It intentionally records:

- `backend_status=not_configured`
- `secret_material_present=false`
- `resolver_implemented=false`
- plaintext export disabled
- environment-variable fallback disabled
- local-file fallback disabled
- Git storage disabled

R2C-C does not implement a resolver, does not read environment variables, does not read local auth files, and does not store secret values.

## Egress Policy

The egress policy is an offline proposal. It validates that network execution remains disabled and the only synthetic host identity is `provider.invalid` on HTTPS port 443.

Redirects, proxy use, private network access, localhost access, IP literal access, and wildcard hosts are rejected. A real endpoint must be separately approved in a later gate and is not present in this package.

## Run Manifest

The run manifest defines a proposed single-call review window. It includes:

- case id
- prompt id and version
- provider and model ids
- max calls
- token budget
- cost budget
- timeout
- UTC review window
- manual review requirements

The manifest does not schedule a call. It only records the proposed bounds for later human review.

## Budget And Window

R2C-C caps the proposal at one call, 1024 input tokens, 512 output tokens, 1536 total tokens, USD 0.10 synthetic cost, and a 15-minute UTC window.

Budget checks are deterministic contract checks. They are not provider billing queries.

## Kill Switch

The kill switch proposal defaults to blocked, requires manual enablement, forbids automatic enablement, and fails closed.

Required stop conditions include secret exposure, binding mismatch, expired approval or grant, identity drift, endpoint mismatch, redirect or proxy request, private network request, budget breach, response-size breach, token-limit breach, tools or streaming request, trading field detection, parse failure, 401/403, repeated rate limits or 5xx, redaction failure, audit write failure, and unclear kill-switch state.

## Threat Model

The versioned threat model covers secret leakage, environment reads, prompt injection, endpoint injection, redirect bypass, DNS rebinding, proxy bypass, private network access, provider/model identity drift, response schema drift, retry cost loss, grant replay, approval failure, audit loss, redaction failure, production data leakage, sandbox credential misuse, kill-switch failure, and unclear incident ownership.

Each threat records:

- threat id
- category
- description
- severity
- required controls
- evidence references
- residual risk
- review status

The allowed review statuses are:

```text
covered_by_offline_control
requires_human_review
blocked
```

R2C-C never records `risk_accepted_for_live`.

## Evidence Bundle

The evidence bundle references sealed milestones rather than copying their full outputs:

- R2A sealed at `bd7279e127c815c43ac760c2aa86a5ccf50fb1f5`
- R2B sealed at `16da82868393b499b1c07ccce2fc0e13e4ac00d0`
- R2C-A sealed at `084ab293b5c190d4219ab72ac01eea3aa9fa90d5`
- R2C-B sealed at `65a396120a5734b7e06855000c84e7a2e581b617`

It also references no-network, no-secret, redaction, replay protection, boundary audit, main CI, and readiness package evidence.

## Incident Response

The incident response proposal requires:

- secret exposure rotation plan
- unauthorized network shutdown plan
- audit failure plan
- rollback plan
- incident owner role
- automatic retry disabled

It does not execute any operational action. It is a versioned checklist for human review.

## Hashes And Audit

The gate emits deterministic hashes for:

- sandbox profile
- secret proposal
- egress policy
- run manifest
- threat model
- evidence bundle
- incident plan
- readiness package
- audit record

Threats and evidence references are canonicalized by id before hashing, so order changes do not alter the hash.

Hashes are evidence fingerprints, not identity signatures and not execution credentials.

## Structured Errors

Errors use the standard shape:

```json
{
  "code": "...",
  "message": "...",
  "field_path": "..."
}
```

Errors must not echo secret values, provider credentials, auth headers, or real endpoint material.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_sandbox_readiness.py `
  --sandbox-profile tests\tradingagents_bridge\fixtures\r2c_c\sandbox_profile.json `
  --secret-storage-proposal tests\tradingagents_bridge\fixtures\r2c_c\secret_storage_proposal.json `
  --egress-policy tests\tradingagents_bridge\fixtures\r2c_c\egress_policy.json `
  --run-manifest tests\tradingagents_bridge\fixtures\r2c_c\run_manifest.json `
  --threat-model tests\tradingagents_bridge\fixtures\r2c_c\threat_model.json `
  --prerequisite-evidence tests\tradingagents_bridge\fixtures\r2c_c\prerequisite_evidence.json `
  --incident-response tests\tradingagents_bridge\fixtures\r2c_c\incident_response.json `
  --output-root "$smokeRoot" `
  --expected-result tests\tradingagents_bridge\fixtures\r2c_c\expected_readiness_result.json
```

Exit codes:

- `0`: readiness package passed and is ready for human review
- `1`: package is blocked or expected fixture comparison failed
- `2`: JSON, schema, load, or output error

The CLI writes `sandbox_readiness_result.json` only to the explicit output root.

## Synthetic Fixtures

Fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2c_c/
```

They are synthetic and contain no real credential material, no real provider endpoint, no production data, no market data, and no trading execution output.

## Real Sandbox No-Go Conditions

A future real sandbox call remains blocked if any of the following are missing:

- approved secret backend
- separately reviewed resolver
- approved real endpoint
- deployed egress allowlist
- kill-switch drill
- redaction drill
- confirmed incident owner
- confirmed real operator and approver identities
- separately issued one-time grant
- approved budget
- approved call window
- pinned model version
- disabled tools and streaming
- isolated production data
- verified audit path
- verified secret rotation and revocation
- green stable main CI
- clean working tree
- no secret in repository
- passing trading-field boundary tests
- explicit human authorization

R2C-C does not mark any of these live prerequisites as completed.

## Boundaries

R2C-C does not modify `tradingagents/`, `cli/`, or `web/`. It does not write `data/exports`, reports, experiments, provider outputs, or production data artifacts.

It does not implement a secret resolver, read auth material, open a real network connection, call provider transport, install or call a model SDK, call Tushare, enter Qlib, call broker systems, create a multi-agent workflow, or generate trading signals, target prices, positions, weights, or orders.
