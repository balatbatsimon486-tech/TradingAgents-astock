from __future__ import annotations

import builtins
import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.trust_boundary.gate import (  # noqa: E402
    build_expected_trust_boundary_result,
    run_offline_trust_boundary_review,
)
from datang_extensions.llm_gateway.trust_boundary.identity import validate_identity_provider_contract  # noqa: E402
from datang_extensions.llm_gateway.trust_boundary.issuance import (  # noqa: E402
    UnavailableAuthorizationIssuer,
    UnavailableDetachedSignatureVerifier,
    UnavailableIdentityAssertionVerifier,
    UnavailableOneTimeNonceIssuer,
)
from datang_extensions.llm_gateway.trust_boundary.nonces import validate_nonce_issuer_contract  # noqa: E402
from datang_extensions.llm_gateway.trust_boundary.signatures import validate_signature_verifier_contract  # noqa: E402

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_e"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_trust_boundary_review.py"
SECRET_TEXT_MARKERS = [
    "Bearer ", "sk-", "Authorization", "Cookie", "private_key",
    "signature_value\"", "nonce_value\"", "\"credential_value\"",
    "TEST-ONLY-SECRET", "person@example.invalid",
]
FORBIDDEN_RESULT_FIELDS = {
    "future_return", "next_return", "forward_return", "target_return", "realized_return",
    "expected_return", "pnl", "profit", "sharpe", "max_drawdown", "win_rate",
    "position_size", "target_weight", "order_size", "buy", "sell", "hold",
    "recommendation", "target_price", "auto_trade",
}


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _run(
    review_result: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    identity: dict[str, Any] | None = None,
    signature: dict[str, Any] | None = None,
    nonce: dict[str, Any] | None = None,
    issuer: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_offline_trust_boundary_review(
        review_result or _load_json("r2c_d_review_result.json"),
        manifest or _load_json("trust_provider_manifest.json"),
        identity or _load_json("identity_provider_contract.json"),
        signature or _load_json("signature_verifier_contract.json"),
        nonce or _load_json("nonce_issuer_contract.json"),
        issuer or _load_json("authorization_issuer_contract.json"),
        evidence or _load_json("prerequisite_evidence.json"),
    )


def _codes(result: dict[str, Any]) -> list[str]:
    return [str(error.get("code", "")) for error in result.get("errors", [])]


def _assert_no_forbidden_key(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key).lower() not in FORBIDDEN_RESULT_FIELDS
            _assert_no_forbidden_key(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_key(item)


def _assert_no_secret_text(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for marker in SECRET_TEXT_MARKERS:
        assert marker not in text


def test_valid_trust_boundary_package_is_ready_for_integration_review_and_matches_expected_fixture() -> None:
    result = _run()
    expected = _load_json("expected_trust_boundary_result.json")

    assert result["stage"] == "tradingagents_r2c_e_offline_trust_boundary"
    assert result["passed"] is True
    assert result["decision"] == "ready_for_trust_service_integration_review"
    assert result["ready_for_trust_service_integration_review"] is True
    assert result["identity_provider_contract_ready"] is True
    assert result["signature_verifier_contract_ready"] is True
    assert result["nonce_issuer_contract_ready"] is True
    assert result["authorization_issuer_contract_ready"] is True
    for field in (
        "identity_service_configured", "identity_assertion_present",
        "identity_verification_performed", "reviewer_identity_verified",
        "signature_service_configured", "signature_value_present",
        "signature_verification_performed", "detached_signature_verified",
        "nonce_service_configured", "execution_nonce_issued",
        "execution_nonce_present", "nonce_commitment_present",
        "authorization_issuer_configured", "live_authorization_issued",
        "secret_resolution_authorized", "network_execution_authorized",
        "live_execution_authorized", "credential_value_resolved", "provider_transport_called",
    ):
        assert result[field] is False
    assert result["required_integration_actions"]
    assert result["blocking_findings"] == []
    assert all(value is False for value in result["external_calls"].values())
    for field in (
        "trust_provider_manifest_hash", "identity_contract_hash", "signature_contract_hash",
        "nonce_contract_hash", "issuer_contract_hash", "evidence_bundle_hash",
        "blocking_findings_hash", "required_integration_actions_hash",
        "trust_boundary_package_hash", "audit_hash",
    ):
        assert len(result[field]) == 64
    assert build_expected_trust_boundary_result(result) == expected
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    _assert_no_forbidden_key(result)
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unknown version", lambda data: data.update({"trust_provider_manifest_version": "9.9"}), "unsupported_trust_boundary_version"),
        ("baseline mismatch", lambda data: data.update({"stable_baseline": "bad"}), "stable_baseline_mismatch"),
        ("review mismatch", lambda data: data.update({"review_package_hash": "0" * 64}), "review_package_mismatch"),
        ("draft mismatch", lambda data: data.update({"authorization_draft_hash": "0" * 64}), "authorization_draft_mismatch"),
        ("duplicate id", lambda data: data.update({"signature_verifier_contract_id": data["identity_provider_contract_id"]}), "duplicate_trust_contract_id"),
        ("production", lambda data: data.update({"environment": "production"}), "invalid_trust_provider_manifest"),
        ("connections", lambda data: data.update({"real_service_connections_allowed": True}), "invalid_trust_provider_manifest"),
        ("wildcard", lambda data: data.update({"nonce_issuer_contract_id": "*"}), "invalid_trust_provider_manifest"),
    ],
)
def test_trust_provider_manifest_fails_closed_for_scope_or_binding_errors(label: str, mutate: Any, expected_code: str) -> None:
    manifest = _load_json("trust_provider_manifest.json")
    mutate(manifest)
    result = _run(manifest=manifest)
    assert result["passed"] is False, label
    assert result["decision"] == "blocked"
    assert expected_code in _codes(result)
    assert result["ready_for_trust_service_integration_review"] is False


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("configured", lambda data: data.update({"configuration_status": "configured"}), "identity_service_must_be_unconfigured"),
        ("assertion", lambda data: data.update({"identity_assertion_present": True}), "identity_assertion_must_be_absent"),
        ("performed", lambda data: data.update({"verification_performed": True}), "identity_verification_not_available"),
        ("succeeded", lambda data: data.update({"verification_succeeded": True}), "identity_verification_not_available"),
        ("no mfa", lambda data: data.update({"multi_factor_authentication_required": False}), "identity_provider_contract_invalid"),
        ("no fresh", lambda data: data.update({"fresh_authentication_required": False}), "identity_provider_contract_invalid"),
        ("age too long", lambda data: data.update({"maximum_assertion_age_seconds": 301}), "identity_provider_contract_invalid"),
        ("no audience", lambda data: data.update({"audience_binding_required": False}), "identity_provider_contract_invalid"),
        ("no nonce binding", lambda data: data.update({"nonce_binding_required": False}), "identity_provider_contract_invalid"),
        ("self review", lambda data: data.update({"requester_reviewer_separation_required": False}), "identity_provider_contract_invalid"),
        ("real email", lambda data: data.update({"email": "person@example.invalid"}), "identity_provider_contract_invalid"),
    ],
)
def test_identity_contract_is_policy_only_and_never_verifies_real_identity(label: str, mutate: Any, expected_code: str) -> None:
    identity = _load_json("identity_provider_contract.json")
    mutate(identity)
    identity_hash, errors = validate_identity_provider_contract(identity)
    result = _run(identity=identity)
    assert len(identity_hash) == 64
    assert expected_code in [error["code"] for error in errors]
    assert expected_code in _codes(result)
    assert result["identity_service_configured"] is False
    assert result["reviewer_identity_verified"] is False
    _assert_no_secret_text(result)

@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("configured", lambda data: data.update({"configuration_status": "configured"}), "signature_service_must_be_unconfigured"),
        ("value", lambda data: data.update({"signature_value_present": True}), "signature_value_must_be_absent"),
        ("performed", lambda data: data.update({"verification_performed": True}), "signature_verification_not_available"),
        ("succeeded", lambda data: data.update({"verification_succeeded": True}), "signature_verification_not_available"),
        ("attached", lambda data: data.update({"signature_format": "attached"}), "signature_verifier_contract_invalid"),
        ("weak", lambda data: data.update({"algorithm_policy": ["none"]}), "signature_verifier_contract_invalid"),
        ("no chain", lambda data: data.update({"certificate_chain_validation_required": False}), "signature_verifier_contract_invalid"),
        ("no key usage", lambda data: data.update({"key_usage_validation_required": False}), "signature_verifier_contract_invalid"),
        ("no revocation", lambda data: data.update({"revocation_check_required": False}), "signature_verifier_contract_invalid"),
        ("no root", lambda data: data.update({"trusted_root_policy_required": False}), "signature_verifier_contract_invalid"),
        ("no signer binding", lambda data: data.update({"signer_identity_binding_required": False}), "signature_verifier_contract_invalid"),
        ("real certificate", lambda data: data.update({"certificate": "TEST-ONLY-CERT"}), "signature_verifier_contract_invalid"),
    ],
)
def test_signature_contract_is_detached_policy_only_and_never_verifies(label: str, mutate: Any, expected_code: str) -> None:
    signature = _load_json("signature_verifier_contract.json")
    mutate(signature)
    signature_hash, errors = validate_signature_verifier_contract(signature)
    result = _run(signature=signature)
    assert len(signature_hash) == 64
    assert expected_code in [error["code"] for error in errors]
    assert expected_code in _codes(result)
    assert result["signature_service_configured"] is False
    assert result["detached_signature_verified"] is False
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("configured", lambda data: data.update({"configuration_status": "configured"}), "nonce_service_must_be_unconfigured"),
        ("value", lambda data: data.update({"nonce_value_present": True}), "nonce_value_must_be_absent"),
        ("commitment", lambda data: data.update({"nonce_commitment_present": True}), "nonce_value_must_be_absent"),
        ("issued", lambda data: data.update({"nonce_issued": True}), "nonce_generation_not_available"),
        ("consumed", lambda data: data.update({"nonce_consumed": True}), "nonce_generation_not_available"),
        ("low entropy", lambda data: data.update({"minimum_entropy_bits": 64}), "nonce_issuer_contract_invalid"),
        ("long ttl", lambda data: data.update({"maximum_lifetime_seconds": 301}), "nonce_issuer_contract_invalid"),
        ("not single", lambda data: data.update({"single_use_required": False}), "nonce_replay_control_incomplete"),
        ("no binding", lambda data: data.update({"binding_required": False}), "nonce_issuer_contract_invalid"),
        ("no atomic", lambda data: data.update({"atomic_consume_required": False}), "nonce_replay_control_incomplete"),
        ("no replay", lambda data: data.update({"replay_detection_required": False}), "nonce_replay_control_incomplete"),
        ("no revocation", lambda data: data.update({"revocation_required": False}), "nonce_replay_control_incomplete"),
        ("deterministic", lambda data: data.update({"nonce_kind": "deterministic_nonce"}), "nonce_issuer_contract_invalid"),
        ("auth id", lambda data: data.update({"authorization_id_as_nonce_forbidden": False}), "nonce_issuer_contract_invalid"),
    ],
)
def test_nonce_contract_requires_future_one_time_service_without_issuing_nonce(label: str, mutate: Any, expected_code: str) -> None:
    nonce = _load_json("nonce_issuer_contract.json")
    mutate(nonce)
    nonce_hash, errors = validate_nonce_issuer_contract(nonce)
    result = _run(nonce=nonce)
    assert len(nonce_hash) == 64
    assert expected_code in [error["code"] for error in errors]
    assert expected_code in _codes(result)
    assert result["nonce_service_configured"] is False
    assert result["execution_nonce_issued"] is False
    assert result["execution_nonce_present"] is False
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("configured", lambda data: data.update({"configuration_status": "configured"}), "authorization_issuer_must_be_unconfigured"),
        ("issued", lambda data: data.update({"authorization_issued": True}), "authorization_issuance_not_available"),
        ("value", lambda data: data.update({"authorization_value_present": True}), "authorization_issuance_not_available"),
        ("execution", lambda data: data.update({"execution_authorized": True}), "authorization_issuance_not_available"),
        ("manual", lambda data: data.update({"manual_issue_required": False}), "authorization_issuer_contract_invalid"),
        ("identity", lambda data: data.update({"identity_verification_required": False}), "authorization_issuer_contract_invalid"),
        ("signature", lambda data: data.update({"detached_signature_verification_required": False}), "authorization_issuer_contract_invalid"),
        ("nonce", lambda data: data.update({"nonce_issuance_required": False}), "authorization_issuer_contract_invalid"),
        ("freeze", lambda data: data.update({"change_freeze_revalidation_required": False}), "authorization_issuer_contract_invalid"),
        ("baseline", lambda data: data.update({"stable_baseline_revalidation_required": False}), "authorization_issuer_contract_invalid"),
        ("atomic", lambda data: data.update({"atomic_issue_required": False}), "authorization_issuer_contract_invalid"),
        ("duplicate", lambda data: data.update({"duplicate_issue_rejected": False}), "authorization_issuer_contract_invalid"),
        ("ttl", lambda data: data.update({"authorization_ttl_seconds_max": 901}), "authorization_issuer_contract_invalid"),
    ],
)
def test_authorization_issuer_contract_cannot_issue_or_execute(label: str, mutate: Any, expected_code: str) -> None:
    issuer = _load_json("authorization_issuer_contract.json")
    mutate(issuer)
    result = _run(issuer=issuer)
    assert result["passed"] is False, label
    assert expected_code in _codes(result)
    assert result["authorization_issuer_configured"] is False
    assert result["live_authorization_issued"] is False
    assert result["live_execution_authorized"] is False


def test_protocol_boundary_objects_are_unavailable_and_fail_closed() -> None:
    identity = UnavailableIdentityAssertionVerifier().verify({"request_id": "synthetic"})
    signature = UnavailableDetachedSignatureVerifier().verify({"request_id": "synthetic"})
    nonce = UnavailableOneTimeNonceIssuer().issue({"request_id": "synthetic"})
    authorization = UnavailableAuthorizationIssuer().issue({"request_id": "synthetic"})

    assert identity["passed"] is False
    assert "identity_verification_not_available" in _codes(identity)
    assert identity["verification_performed"] is False
    assert signature["passed"] is False
    assert "signature_verification_not_available" in _codes(signature)
    assert signature["verification_performed"] is False
    assert nonce["passed"] is False
    assert "nonce_generation_not_available" in _codes(nonce)
    assert nonce["nonce_issued"] is False
    assert authorization["passed"] is False
    assert "authorization_issuance_not_available" in _codes(authorization)
    assert authorization["authorization_issued"] is False


def test_decision_hashes_are_deterministic_and_input_changes_change_package_hash() -> None:
    first = _run()
    second = _run()
    changed = _load_json("trust_provider_manifest.json")
    changed["manifest_id"] = "r2c-e-trust-boundary-002"
    changed_result = _run(manifest=changed)

    assert first == second
    assert first["trust_boundary_package_hash"] == second["trust_boundary_package_hash"]
    assert changed_result["passed"] is True
    assert changed_result["trust_boundary_package_hash"] != first["trust_boundary_package_hash"]


def test_blocking_findings_keep_package_blocked_and_errors_structured() -> None:
    evidence = _load_json("prerequisite_evidence.json")
    evidence["no_network"] = False
    result = _run(evidence=evidence)

    assert result["passed"] is False
    assert result["decision"] == "blocked"
    assert result["ready_for_trust_service_integration_review"] is False
    assert result["blocking_findings"] == result["errors"]
    assert "trust_boundary_evidence_invalid" in _codes(result)
    for error in result["errors"]:
        assert set(error) == {"code", "message", "field_path"}


def test_external_call_isolation_fixture_integrity_and_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_paths = sorted(FIXTURES_ROOT.glob("*.json"))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in fixture_paths}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-E")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-E")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {
            "openai", "anthropic", "google_genai", "langchain", "tushare", "qlib",
            "requests", "httpx", "urllib", "websocket", "dotenv", "cryptography", "secrets",
        }
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        if name == "datang_extensions.llm_gateway.provider_adapters.chat_adapter":
            raise AssertionError("R2C-E must not call provider adapter transport")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    result = _run()
    assert result["passed"] is True
    assert all(value is False for value in result["external_calls"].values())
    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert subprocess.run(["git", "ls-files", "data/exports"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "trust_boundary").exists()


def test_trust_boundary_code_has_no_real_network_secret_crypto_or_provider_clients() -> None:
    package_root = PROJECT_ROOT / "datang_extensions" / "llm_gateway" / "trust_boundary"
    assert package_root.exists()
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(package_root.glob("*.py")))
    forbidden_snippets = [
        "requests", "httpx", "urllib", "socket", "os.environ", "getenv", "dotenv",
        "openai", "anthropic", "google_genai", "langchain", "tushare", "qlib",
        "secrets", "urandom", "shell=True", "os.system",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in text


def test_cli_success_blocked_schema_and_disallowed_live_args_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    success = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--r2c-d-review-result", str(FIXTURES_ROOT / "r2c_d_review_result.json"),
            "--trust-provider-manifest", str(FIXTURES_ROOT / "trust_provider_manifest.json"),
            "--identity-provider-contract", str(FIXTURES_ROOT / "identity_provider_contract.json"),
            "--signature-verifier-contract", str(FIXTURES_ROOT / "signature_verifier_contract.json"),
            "--nonce-issuer-contract", str(FIXTURES_ROOT / "nonce_issuer_contract.json"),
            "--authorization-issuer-contract", str(FIXTURES_ROOT / "authorization_issuer_contract.json"),
            "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
            "--output-root", str(success_root),
            "--expected-result", str(FIXTURES_ROOT / "expected_trust_boundary_result.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["decision"] == "ready_for_trust_service_integration_review"
    assert summary["ready_for_trust_service_integration_review"] is True
    assert all(value is False for value in summary["external_calls"].values())
    assert (success_root / "trust_boundary_result.json").is_file()

    blocked_manifest = _load_json("trust_provider_manifest.json")
    blocked_manifest["stable_baseline"] = "bad"
    blocked_path = _write_json(tmp_path / "blocked_manifest.json", blocked_manifest)
    blocked = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--r2c-d-review-result", str(FIXTURES_ROOT / "r2c_d_review_result.json"),
            "--trust-provider-manifest", str(blocked_path),
            "--identity-provider-contract", str(FIXTURES_ROOT / "identity_provider_contract.json"),
            "--signature-verifier-contract", str(FIXTURES_ROOT / "signature_verifier_contract.json"),
            "--nonce-issuer-contract", str(FIXTURES_ROOT / "nonce_issuer_contract.json"),
            "--authorization-issuer-contract", str(FIXTURES_ROOT / "authorization_issuer_contract.json"),
            "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
            "--output-root", str(tmp_path / "blocked"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["decision"] == "blocked"

    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text("[]", encoding="utf-8")
    schema_error = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--r2c-d-review-result", str(bad_schema),
            "--trust-provider-manifest", str(FIXTURES_ROOT / "trust_provider_manifest.json"),
            "--identity-provider-contract", str(FIXTURES_ROOT / "identity_provider_contract.json"),
            "--signature-verifier-contract", str(FIXTURES_ROOT / "signature_verifier_contract.json"),
            "--nonce-issuer-contract", str(FIXTURES_ROOT / "nonce_issuer_contract.json"),
            "--authorization-issuer-contract", str(FIXTURES_ROOT / "authorization_issuer_contract.json"),
            "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
            "--output-root", str(tmp_path / "schema_error"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert schema_error.returncode == 2

    disallowed_arg = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--verify-identity"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert disallowed_arg.returncode == 2
