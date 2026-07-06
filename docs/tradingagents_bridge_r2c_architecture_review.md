# R2C-G Offline Architecture Review Evidence Sealing

## Current Progress

TradingAgents-astock is in the R2 Auditable AI Research MVP. R1, R2A, R2B, R2C-A, R2C-B, R2C-C, R2C-D, R2C-E, and R2C-F are sealed. The current stable baseline is `1330d21562e43346502bbee5816236b4e806168d`.

R2C-G adds a fully offline architecture-review evidence gate. It seals an architecture review charter, synthetic reviewer-role coverage, structured findings, dissent, remediation, risk-acceptance request contracts, waiver request contracts, an architecture decision record draft, and supersede rules.

## Position

Review evidence sealed is not review completed. Synthetic reviewers are not real reviewers. A synthetic recommendation is not approval. Finding resolved offline is not proof that real deployment risk is closed. Risk acceptance request is not approved risk acceptance. Waiver request is not approved waiver. Decision record draft is not an approved ADR.

The highest allowed state is `ready_for_architecture_signoff=true`. These remain false: architecture review completed, reviewer identity verified, review signatures verified, architecture decision approved, risk acceptance approved, waiver approved, vendor selected, procurement approved, deployment authorized, network change authorized, real integration started, and secret/network/live/transport flags.

## Review Charter

The charter binds the stable baseline, R2C-F architecture package hash, required reviewer roles, quorum, requester separation, and review scope. Required roles are security architecture, platform architecture, operations, data governance, and incident response. Quorum must cover every required role. Wildcard scope and real reviewer assignment are rejected.

## Review Records

Review records are synthetic opaque records only. They include reviewer role, reviewed components, finding references, synthetic status, unavailable identity verification, unavailable signature status, recorded-at UTC, and valid-until UTC. Abstain does not count toward quorum. Recommend block blocks. Request changes blocks if offline remediation has not closed the requested changes.

## Findings And Dissent

Findings use critical, high, medium, low, or informational severity. Unresolved critical or high findings block. Medium findings require remediation. Dissent is preserved and cannot be hidden by majority recommendation. Unresolved formal objection blocks. Conditional objection requires remediation or a signoff precondition.

## Remediation, Risk Acceptance, And Waiver

Remediation is a draft offline plan; it does not mark real deployment remediation complete. Risk acceptance and waiver records are requests only. They require expiry, compensating controls, requester/approver separation, and `not_approved` state. Non-waivable controls include requester/reviewer separation, identity verification, signature verification, nonce replay protection, duplicate issuance rejection, kill switch, audit sink, and no-secret/no-network boundaries.

## Decision Record And Supersede

The decision record remains a draft with only a proposed decision. Approved decision is null. Real signoff and architecture approval remain false. Supersede rules require re-review when baseline, architecture package, candidate, topology, trust zone, data flow, ownership, change, rollback, drill, required actions, findings, risk/waiver requests, charter roles, expiry, or real-world locator contamination changes.

## Hashes, Errors, CLI, And Fixtures

The gate emits deterministic hashes for charter, review records, findings, dissent, remediation, risk requests, waiver requests, decision draft, supersede policy, evidence, blocking findings, required actions, review package, and audit. Hashes use canonical JSON and do not include absolute paths, mtime, machine names, real identity, signatures, suppliers, endpoints, secrets, random values, or system time.

Errors are structured as `{code, message, field_path}` and must not echo sensitive material. The CLI is `scripts/datang_extensions/run_offline_architecture_review.py`; it requires explicit input paths and `--fixed-now`, returns 0 for ready, 1 for blocked or expected mismatch, and 2 for schema or argument errors. Synthetic fixtures live under `tests/tradingagents_bridge/fixtures/r2c_g/`.

## Explicit Non-Goals

R2C-G does not use real people, verify real signatures, choose suppliers, approve procurement or deployment, access networks, call real LLMs, connect Qlib, run backtests, or produce trading output. Future real signoff and future real deployment each require a separate explicit approval.

## Real Signoff No-Go Conditions

Real signoff remains blocked if real reviewers are not assigned, reviewer identity or role is not verified, detached signatures are not verified, stable baseline or architecture package changed, review package is superseded or expired, critical/high finding is open, formal objection is unresolved, medium finding lacks remediation, risk acceptance or waiver request is not approved, non-waivable control is requested for waiver, supplier due diligence is incomplete, legal/procurement/data-protection review is incomplete, topology/rollback/drill are not truly reviewed, audit and kill switch are not verified, or explicit real signoff authorization is absent.
