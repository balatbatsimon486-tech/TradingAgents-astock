# R2C-E Offline Trust Boundary Contracts

## Current Progress

Project: TradingAgents-astock

Milestone: R2 Auditable AI Research MVP

R1, R2A, R2B, R2C-A, R2C-B, R2C-C, and R2C-D are sealed on stable main. R2C-D sealed the human-review evidence package, change freeze, and one-time live authorization draft contract at baseline:

```text
45492693d586df1f1cb4ca715a608bbad0c754d1
```

R2C-E adds offline trust-boundary contracts for future real trust services. It does not connect to those services and it does not issue any live authorization.

The highest allowed state is:

```text
ready_for_trust_service_integration_review=true
```

## Position In R2

R2C-E consumes the R2C-D sealed review result and synthetic trust-boundary fixtures:

- trust provider manifest
- identity provider boundary contract
- detached signature verifier boundary contract
- one-time nonce issuer boundary contract
- live authorization issuer boundary contract
- prerequisite evidence bundle

The output is an offline decision package. It can be ready for trust-service integration review, or blocked. It cannot be identity verified, signature verified, nonce issued, authorization issued, or live authorized.

## Contract Ready Is Not Service Configured

`contract_ready` means the future integration boundary is documented, versioned, hash-bound, and internally consistent. It does not mean a service exists.

The following remain false in a passing R2C-E result:

```text
identity_service_configured
identity_assertion_present
identity_verification_performed
reviewer_identity_verified
signature_service_configured
signature_value_present
signature_verification_performed
detached_signature_verified
nonce_service_configured
execution_nonce_issued
execution_nonce_present
nonce_commitment_present
authorization_issuer_configured
live_authorization_issued
secret_resolution_authorized
network_execution_authorized
live_execution_authorized
credential_value_resolved
provider_transport_called
```

## Identity Provider Boundary

The identity provider contract records future requirements only:

- opaque subject reference
- requester/reviewer separation
- MFA
- fresh authentication
- maximum assertion age
- audience binding
- nonce binding
- issuer allowlist
- subject uniqueness
- bounded clock skew
- fail closed behavior

The identity service is `not_configured`. The protocol is `not_selected`. No identity assertion is present. No verification is performed or succeeded.

The contract must not contain real names, email addresses, employee IDs, tenant IDs, client IDs, issuer URLs, access tokens, ID tokens, or assertion bodies.

## Detached Signature Verifier Boundary

The signature verifier contract records detached-signature policy requirements only:

- detached format
- placeholder asymmetric policy label
- SHA-256 payload hash policy
- certificate chain validation requirement
- key usage validation requirement
- revocation check requirement
- trusted root policy requirement
- signer identity binding requirement
- payload binding requirement

The algorithm label is a policy placeholder, not an implemented algorithm. R2C-E imports no signature library, reads no certificate, reads no key, reads no signature value, and performs no signature verification.

A hash is not a detached signature.

## One-Time Nonce Issuer Boundary

The nonce issuer contract records future nonce requirements only:

- single-use challenge
- minimum entropy
- maximum lifetime
- binding requirement
- storage requirement
- atomic consume requirement
- replay detection
- revocation
- prohibition on using an authorization id as a nonce

R2C-E does not generate a nonce, does not store a nonce, does not persist a nonce registry, and does not create a nonce commitment.

A hash, UUID, authorization id, or deterministic value is not a live nonce.

## Live Authorization Issuer Boundary

The issuer contract records future issuance prerequisites only:

- manual issue required
- identity verification required
- detached signature verification required
- nonce issuance required
- change freeze revalidation required
- stable baseline revalidation required
- atomic issue required
- duplicate issue rejected
- bounded authorization TTL

R2C-E does not issue an authorization value and does not authorize execution.

## Trust Provider Manifest

The manifest binds the trust-boundary package to:

- stable baseline
- R2C-D review package hash
- R2C-D authorization draft hash
- identity provider contract id
- signature verifier contract id
- nonce issuer contract id
- authorization issuer contract id
- sandbox environment
- single-call-only scope
- real service connections disabled

Contract IDs must be unique, explicit, non-wildcard, and must match their respective contract payloads.

## Stable Baseline And Review Package Binding

R2C-E validates that:

- the stable baseline is exactly `45492693d586df1f1cb4ca715a608bbad0c754d1`
- the R2C-D review result is passed and `ready_for_human_signoff`
- the review package is sealed
- the authorization draft remains `review_ready`
- review package hash, authorization draft hash, change freeze hash, and audit hash are present
- R2C-D false execution flags remain false

## Required Integration Actions

A passing result includes non-empty required integration actions. These actions are not complete in R2C-E. They are future work for a separately approved real integration stage:

- approve an enterprise identity provider
- approve protocol and issuer allowlist
- configure MFA and fresh auth
- define opaque subject role mapping
- approve detached signature format and policies
- configure revocation checks
- deploy nonce issuer and atomic nonce registry
- verify nonce entropy and TTL
- deploy authorization issuer
- define atomic issuance and duplicate rejection
- define real audit sink
- drill outage, signature failure, replay, and duplicate issuance paths
- reconfirm stable baseline and freeze
- complete real security review
- separately approve real integration

## Structured Errors

Errors use the standard shape:

```json
{
  "code": "...",
  "message": "...",
  "field_path": "..."
}
```

Supported error codes include manifest, baseline, review package, authorization draft, identity, signature, nonce, issuer, evidence, and generic trust-boundary failures.

Errors may identify rejected field paths but must not echo real identity material, assertions, certificate material, keys, signatures, nonce values, credentials, endpoints, authorization headers, or unnecessary absolute paths.

## Deterministic Hashes

R2C-E emits deterministic hashes for:

- trust provider manifest
- identity contract
- signature contract
- nonce contract
- issuer contract
- evidence bundle
- blocking findings
- required integration actions
- trust-boundary package
- audit

Hashes use the existing canonical JSON helper. They do not depend on machine name, mtime, environment variables, current system time, random values, absolute paths, credentials, identity assertions, signatures, nonce values, or provider responses.

A hash is not a signature, nonce, credential, bearer token, or execution authorization.

## CLI

```powershell
.\.venv\Scripts\python.exe scripts\datang_extensions\run_offline_trust_boundary_review.py `
  --r2c-d-review-result tests\tradingagents_bridge\fixtures\r2c_e\r2c_d_review_result.json `
  --trust-provider-manifest tests\tradingagents_bridge\fixtures\r2c_e\trust_provider_manifest.json `
  --identity-provider-contract tests\tradingagents_bridge\fixtures\r2c_e\identity_provider_contract.json `
  --signature-verifier-contract tests\tradingagents_bridge\fixtures\r2c_e\signature_verifier_contract.json `
  --nonce-issuer-contract tests\tradingagents_bridge\fixtures\r2c_e\nonce_issuer_contract.json `
  --authorization-issuer-contract tests\tradingagents_bridge\fixtures\r2c_e\authorization_issuer_contract.json `
  --prerequisite-evidence tests\tradingagents_bridge\fixtures\r2c_e\prerequisite_evidence.json `
  --output-root "$smokeRoot" `
  --expected-result tests\tradingagents_bridge\fixtures\r2c_e\expected_trust_boundary_result.json
```

Exit codes:

- `0`: package passed and is ready for trust-service integration review
- `1`: package is blocked or expected fixture comparison failed
- `2`: JSON, schema, argument, load, or output error

The CLI accepts only explicit file paths and output root. It does not provide verify, issue, live, assertion, certificate, signature, nonce, secret, or resolver arguments. It writes `trust_boundary_result.json` only to the explicit output root.

## Synthetic Fixtures

Fixtures live under:

```text
tests/tradingagents_bridge/fixtures/r2c_e/
```

They are synthetic. They contain no real identity assertion, no real certificate, no real signature value, no real nonce, no real credential, no real provider endpoint, no real market data, no model output, and no trading execution output.

## Real Integration No-Go Conditions

Any one of the following blocks real trust-service integration:

1. Enterprise identity provider not approved.
2. Issuer allowlist not approved.
3. MFA or fresh-auth policy not configured.
4. Subject-role mapping not approved.
5. Signature format or algorithm policy not approved.
6. Trusted root policy not approved.
7. Certificate revocation checks not configured.
8. Nonce issuer not security reviewed.
9. Nonce entropy not verified.
10. Atomic consume not verified.
11. Replay detection not verified.
12. Authorization issuer not security reviewed.
13. Atomic issue not verified.
14. Duplicate issue rejection not verified.
15. Audit sink not verified.
16. Stable baseline changed.
17. Review package superseded.
18. Change freeze changed.
19. Incident response not drilled.
20. Explicit real integration approval missing.

R2C-E does not mark any of these items complete.

## Boundaries

R2C-E does not modify `tradingagents/`, `cli/`, or `web/`. It does not write `data/exports`, reports, experiments, provider outputs, production data artifacts, or market data.

R2C-E does not implement real identity verification, real detached signature verification, nonce generation, nonce storage, live authorization issuance, secret resolution, provider transport, network access, SDK calls, real LLM calls, Tushare calls, Qlib calls, broker calls, orders, positions, target prices, forecasts, or trading recommendations.

The next step after local acceptance is a separate dev push and remote CI gate. Real service integration remains blocked until separately approved.
