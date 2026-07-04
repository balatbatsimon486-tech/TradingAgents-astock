# R2C-B Offline Secret Binding Authorization Gate

This document defines the R2C-B offline secret binding and authorization gate for the TradingAgents-astock bridge. It extends the R2A offline gateway, R2B prompt registry, and R2C-A fake provider adapter without enabling live provider execution.

## Goal

R2C-B proves that a provider/model request can be checked against an opaque binding registry, an approved authorization policy, a two-person approval set, deterministic time windows, and the R2C-A fake adapter identity before any provider transport is allowed.

The stage is offline only. It does not resolve credentials, does not read environment variables, does not call a provider SDK, does not call Tushare, does not enter Qlib, and does not emit trading actions or strategy recommendations.

## Binding Registry

The registry records opaque binding IDs only. A binding may identify provider, model, adapter, environment, allowed purpose, task type, state, validity window, and single-call grant constraints.

Allowed lifecycle states are:

- `registered`
- `active`
- `suspended`
- `revoked`
- `expired`

Only `active` bindings inside their validity window can authorize an offline preflight grant. Suspended, revoked, expired, future, missing, wildcard, production, resolver-backed, or material-bearing bindings fail closed. State transitions are represented as deterministic audit records with `transition_hash`; terminal states cannot transition back to active.

## Authorization Policy

The only supported grant mode is `offline_preflight`. The policy must be approved, sandbox scoped, single-call, and bounded by token, cost, and lifetime limits.

The requester may not approve their own request. Quorum must be at least two and must satisfy explicit roles, currently `research_owner` and `risk_reviewer` in the test fixture.

The following capabilities must remain false:

- network execution
- tools
- streaming
- trading actions
- live execution
- credential resolution
- provider transport

## Approval Records

Approval validation enforces unique approvers, requester separation, request identity match, valid time windows, non-revoked records, reject priority, quorum, and required roles. The approval set hash is order independent.

## Authorization Request

The request must match the binding and R2C-A adapter identity for provider, model, adapter, version, environment, purpose, task type, and budget. It must include stable lineage hashes for the upstream gateway request, prompt spec, and input artifact.

Caller-supplied transport surface such as `endpoint`, `headers`, `tools`, `stream`, proxy, or URL is rejected. Secret-like fields and trading/performance fields are rejected without echoing values or sensitive field names into the result.

## Grant And Audit

A successful decision produces one JSON-serializable `offline_preflight` grant with:

- `max_calls = 1`
- `grant_state = issued`
- `live_execution_authorized = false`
- `credential_resolution_authorized = false`
- `provider_transport_authorized = false`

Consuming the grant is also offline and one-time. The consumption check verifies request hash, expiry, revocation, and consumed state. It does not call transport or resolve credentials.

The authorization result records canonical hashes for request, binding, policy, approval set, decision, grant, audit, and transition events. The audit record contains only IDs, hashes, decisions, booleans, counts, roles, and error codes. It never contains secret material.

## CLI Smoke

`scripts/datang_extensions/run_offline_provider_authorization.py` loads JSON fixtures, injects a fixed clock, runs the offline gate, writes `authorization_result.json` to an explicit output root, and prints a compact summary. It returns:

- `0` for an allowed offline preflight grant
- `1` for policy/contract denial or expected fixture mismatch
- `2` for schema/config/load errors

## Boundaries

R2C-B does not modify `tradingagents/`, `cli/`, or `web/`. It does not write `data/exports`. It does not push branches, update `datang/main`, or call remote services.
