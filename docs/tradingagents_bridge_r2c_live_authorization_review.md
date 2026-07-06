# R2C-D Offline Live Authorization Review Contract

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R2A, R2B, R2C-A, R2C-B, and R2C-C are sealed on stable main. The stable baseline for this review contract is:

```text
ef9a37abaf6586bf31f436d9a07ca8edb601c77d
```

R2C-D adds an offline contract for human-review evidence sealing, change freeze, and a one-time live authorization draft. It does not issue a real live authorization and does not perform a provider call.

## Position In R2

R2C-D consumes the R2C-C readiness result and adds a final offline gate before any future real sandbox work.

The highest allowed state is:

```text
ready_for_human_signoff
```

The following states remain false:

```text
human_review_completed
reviewer_identity_verified
detached_signature_verified
live_authorization_issued
secret_resolution_authorized
network_execution_authorized
live_execution_authorized
credential_value_resolved
provider_transport_called
```

## Inputs

The gate accepts only JSON objects supplied by tests, fixtures, or a controlled CLI invocation:

- R2C-C readiness result
- review manifest
- reviewer records
- change freeze record
- one-time live authorization draft

The gate does not read secrets, environment variables, auth files, provider SDKs, market data, production data, or TradingAgents runtime state.

## Review Manifest

The review manifest records the draft review scope:

- stable baseline commit
- readiness package hash
- review manifest id
- case id
- provider id
- model id
- adapter id and version
- binding id
- authorization policy id
- prompt id and prompt version
- input artifact hash
- required reviewer roles
- required role quorum
- requester id

The requester cannot review the package. Reviewer roles must be explicit safe ids. Wildcards and duplicate roles fail closed.

## Reviewer Records

Reviewer records are synthetic offline attestations. They prove only that a complete set of required roles is represented in the fixture package.

They do not prove real identity. They do not verify detached signatures. They do not mark human review completed.

Each record must include:

- review manifest id
- reviewer id
- reviewer role
- recommendation
- synthetic flag
- identity verification status
- signature status
- recorded-at UTC timestamp
- valid-until UTC timestamp
- reviewed artifact hashes

Any reviewer block recommendation blocks the whole package. Expired records, duplicate reviewer ids, requester-as-reviewer, missing roles, verified identity, or verified signature all fail closed.

## Change Freeze

The change freeze record seals the exact review package before human signoff. It binds:

- stable baseline
- readiness package hash
- review manifest hash
- reviewer record set hash
- frozen artifact ids, kinds, versions, and hashes
- sealed-at UTC timestamp

The freeze must be `sealed_for_review`. Automatic unfreeze is forbidden. Any artifact, budget, scope, or window change requires a new review.

Artifact ordering is canonicalized before hashing. The same artifact set produces the same freeze hash regardless of list order.

## One-Time Live Authorization Draft

The draft is not an issued authorization. It is a non-executable contract envelope for a future manual decision.

The draft must be `review_ready` and `single_sandbox_call`. It must bind:

- review package hash
- change freeze hash
- readiness package hash
- stable baseline
- case id
- provider id
- model id
- adapter id and version
- binding id
- authorization policy id
- prompt id and prompt version
- input artifact hash
- max calls
- token and cost budgets
- proposed UTC execution window

The execution nonce is absent in R2C-D. Real identity verification, detached signature verification, secret resolution, network execution, provider transport, and live execution all remain false.

The authorization id is deterministic and derived from draft content. It is a fingerprint, not a bearer credential.

## Replay And Supersession

R2C-D blocks issuance and consumption attempts:

- draft to review-ready is allowed
- review-ready to issued is blocked
- issued to consumed is blocked
- replay consumption is blocked

If artifacts, budget, or execution window change, the draft is marked superseded and the package must be reviewed again.

## Hashes And Audit

The gate emits deterministic hashes for:

- review manifest
- reviewer record set
- change freeze
- review package
- authorization draft
- audit record

The review package hash binds the readiness hash, manifest hash, reviewer record hash, change freeze hash, decision ceiling, and `live_authorized=false`.

The audit record is JSON-serializable and repeats the critical false execution flags so the package can be inspected without running live code.

## Structured Errors

Errors use the standard shape:

```json
{
  "code": "...",
  "message": "...",
  "field_path": "..."
}
```

Errors may name rejected field paths. They must not echo secret material, auth headers, real provider credentials, real reviewer identity, or provider response content.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_live_authorization_review.py `
  --readiness-result tests\tradingagents_bridge\fixtures\r2c_d\readiness_result.json `
  --review-manifest tests\tradingagents_bridge\fixtures\r2c_d\review_manifest.json `
  --reviewer-records tests\tradingagents_bridge\fixtures\r2c_d\reviewer_records.json `
  --change-freeze tests\tradingagents_bridge\fixtures\r2c_d\change_freeze.json `
  --authorization-draft tests\tradingagents_bridge\fixtures\r2c_d\authorization_draft.json `
  --fixed-now 2030-01-01T00:10:00Z `
  --output-root "$smokeRoot" `
  --expected-result tests\tradingagents_bridge\fixtures\r2c_d\expected_review_result.json
```

Exit codes:

- `0`: offline package passed and is ready for human signoff
- `1`: package is blocked or expected fixture comparison failed
- `2`: JSON, schema, load, or output error

The CLI writes `live_authorization_review_result.json` only to the explicit output root.

## Synthetic Fixtures

Fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2c_d/
```

They are synthetic and contain no real credential material, no real provider endpoint, no production data, no market data, no model output, and no trading execution output.

## Real Sandbox No-Go Conditions

A future real sandbox call remains blocked until all of these are separately completed outside R2C-D:

- real reviewer identity verification
- detached signature verification
- approved secret backend
- reviewed secret resolver design
- approved real endpoint and egress control
- budget and execution window approval
- out-of-band execution nonce creation
- kill-switch drill
- incident owner confirmation
- manual one-time live authorization issuance
- green dev CI after R2C-D push
- stable main promotion and green main CI
- clean working tree
- no secrets in repository

R2C-D does not mark any of these live prerequisites as completed.

## Boundaries

R2C-D does not modify `tradingagents/`, `cli/`, or `web/`. It does not write `data/exports`, reports, experiments, provider outputs, or production data artifacts.

It does not implement real identity verification, detached signature verification, a secret resolver, provider transport, network access, SDK calls, real LLM calls, Tushare calls, Qlib calls, broker calls, orders, positions, target prices, forecasts, or trading recommendations.

The next step after local sealing is a separate dev push and remote CI gate. Only after that may a stable main promotion gate be considered. Real live sandbox execution remains blocked.