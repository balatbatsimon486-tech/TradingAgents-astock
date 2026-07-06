# R2C-F Offline Trust Integration Architecture

## Scope

R2C-F defines an offline architecture gate for future trust service integration. It evaluates synthetic service-class candidates, planned topology boundaries, data-flow classes, ownership, change control, rollback, drills, and prerequisite R2C-D/R2C-E evidence. It does not select a real vendor, configure a service, execute a connection, read credentials, or authorize live operation.

## Inputs

The gate accepts JSON objects supplied by tests or a local CLI invocation:

- R2C-E trust boundary result
- synthetic candidate catalog
- evaluation policy
- deployment topology draft
- ownership matrix
- change-control plan
- rollback and exit plan
- operational drill plan
- prerequisite evidence bundle

All inputs are offline contract fixtures. Real product names, commercial terms, endpoints, network locations, accounts, tenants, and credential material are outside this stage.

## Candidate Assessment

Candidates are grouped by service class:

- identity provider boundary
- detached signature verifier boundary
- nonce issuer boundary
- authorization issuer boundary

The gate scores only synthetic candidates against mandatory controls and weighted attributes. A recommendation means the candidate is ready for architecture review only. It is not procurement approval, deployment approval, or product selection.

## Topology and Data Flow

The topology describes logical trust zones and planned disabled paths. Required boundaries include research orchestration, trust control plane, identity, signature verification, nonce, authorization issuer, audit sink, kill switch, and provider sandbox. Data-flow records must be declared, redacted, and limited to permitted classes. Secret material, signature material, and nonce material are not allowed to flow through the R2C-F package.

## Ownership and Change Control

Ownership rows define responsible, accountable, consulted, and informed roles by control. Separation of duties keeps request, approval, incident command, rollback, and service-owner responsibilities distinct. Change control remains draft-only: no implementation authorization, no production change, no network change, and no approval bypass.

## Rollback, Exit, and Drills

Rollback is an offline plan with disabled connections, no configured service state, audit preservation, dependency removal, credential rotation requirement, authorization revocation requirement, nonce isolation requirement, data-deletion verification, and portability requirements. Drill scenarios are planned for tabletop review only and must remain not executed.

## Evidence and Hashes

The gate records stable hashes for candidate catalog, policy, assessment, recommendations, topology, trust-zone model, data flows, ownership, change control, rollback, drills, evidence, blocking findings, required real-world actions, architecture package, and audit. Reordered equivalent inputs produce the same core hashes.

## CLI

The local CLI is:

```powershell
python scripts/datang_extensions/run_offline_trust_integration_architecture.py `
  --r2c-e-trust-boundary-result tests/tradingagents_bridge/fixtures/r2c_f/r2c_e_trust_boundary_result.json `
  --candidate-catalog tests/tradingagents_bridge/fixtures/r2c_f/candidate_catalog.json `
  --evaluation-policy tests/tradingagents_bridge/fixtures/r2c_f/evaluation_policy.json `
  --deployment-topology tests/tradingagents_bridge/fixtures/r2c_f/deployment_topology.json `
  --ownership-matrix tests/tradingagents_bridge/fixtures/r2c_f/ownership_matrix.json `
  --change-control-plan tests/tradingagents_bridge/fixtures/r2c_f/change_control_plan.json `
  --rollback-plan tests/tradingagents_bridge/fixtures/r2c_f/rollback_plan.json `
  --drill-plan tests/tradingagents_bridge/fixtures/r2c_f/drill_plan.json `
  --prerequisite-evidence tests/tradingagents_bridge/fixtures/r2c_f/prerequisite_evidence.json `
  --output-root <ignored-test-temp-dir>
```

The CLI returns 0 for a passed offline architecture review package, 1 for fail-closed blocked results, and 2 for invalid input schema or command usage.

## Explicit Non-Goals

R2C-F does not perform real vendor research, deploy services, configure identity, configure signatures, issue nonces, issue authorizations, read secrets, call provider transports, run model training, run market-data ingestion, execute trades, or produce investment advice. Any transition to real sandbox integration requires a later separately approved stage with fresh security, legal, procurement, and operational review.
