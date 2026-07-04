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

from datang_extensions.llm_gateway.contracts import stable_json_hash  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.approvals import validate_approvals  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.gate import (  # noqa: E402
    build_expected_authorization_result,
    consume_offline_preflight_grant,
    run_offline_authorization,
)
from datang_extensions.llm_gateway.provider_authorization.policy import load_authorization_policy  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.registry import (  # noqa: E402
    load_binding_registry,
    transition_binding_state,
)

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_b"
R2C_CONFIG_PATH = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c" / "provider_config.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_provider_authorization.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _registry() -> dict[str, Any]:
    return _load_json(FIXTURES_ROOT / "binding_registry.json")


def _policy() -> dict[str, Any]:
    return _load_json(FIXTURES_ROOT / "authorization_policy.json")


def _request() -> dict[str, Any]:
    return _load_json(FIXTURES_ROOT / "authorization_request.json")


def _approvals() -> dict[str, Any]:
    return _load_json(FIXTURES_ROOT / "approvals.json")


def _adapter_config() -> dict[str, Any]:
    return _load_json(R2C_CONFIG_PATH)


def _clock(value: str = "2026-07-04T00:10:00Z") -> FixedAuthorizationClock:
    return FixedAuthorizationClock.from_iso8601(value)


def _run(
    registry: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
    approvals: dict[str, Any] | None = None,
    adapter_config: dict[str, Any] | None = None,
    *,
    now: str = "2026-07-04T00:10:00Z",
) -> dict[str, Any]:
    return run_offline_authorization(
        registry or _registry(),
        policy or _policy(),
        request or _request(),
        approvals or _approvals(),
        adapter_config=adapter_config or _adapter_config(),
        clock=_clock(now),
    )


def _error_codes(result_or_exc: Any) -> list[str]:
    errors = getattr(result_or_exc, "errors", None)
    if errors is None:
        errors = result_or_exc.get("errors", [])
    return [str(error.get("code", "")) for error in errors]


def _assert_no_secret_text(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    forbidden = [
        "TEST-ONLY-SECRET-MUST-BE-REJECTED",
        "Bearer ",
        "sk-",
        "Authorization",
        "Cookie",
        "Set-Cookie",
        "\"credential_value\"",
        "\"secret_value\"",
        "private_key",
    ]
    for marker in forbidden:
        assert marker not in text


def test_valid_authorization_generates_offline_preflight_grant_and_matches_expected_fixture() -> None:
    result = _run()
    expected = _load_json(FIXTURES_ROOT / "expected_authorization_result.json")

    assert result["stage"] == "tradingagents_r2c_b_offline_authorization"
    assert result["passed"] is True
    assert result["decision"] == "allow"
    assert result["preflight_authorized"] is True
    assert result["live_execution_authorized"] is False
    assert result["credential_value_resolved"] is False
    assert result["provider_transport_called"] is False
    assert result["grant"]["grant_mode"] == "offline_preflight"
    assert result["grant"]["max_calls"] == 1
    assert result["grant"]["live_execution_authorized"] is False
    assert result["grant"]["credential_resolution_authorized"] is False
    assert result["approval_quorum_required"] == 2
    assert result["approval_quorum_satisfied"] == 2
    assert result["required_roles_satisfied"] == ["research_owner", "risk_reviewer"]
    assert all(value is False for value in result["external_calls"].values())
    for field in (
        "authorization_request_hash",
        "binding_hash",
        "policy_hash",
        "approval_set_hash",
        "decision_hash",
        "audit_hash",
    ):
        assert len(result[field]) == 64
    assert len(result["grant"]["grant_id"]) == 64
    assert len(result["grant"]["grant_hash"]) == 64
    assert build_expected_authorization_result(result) == expected
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unknown registry version", lambda data: data.update({"binding_registry_version": "9.9"}), "unsupported_binding_registry_version"),
        ("duplicate binding id", lambda data: data["bindings"].append(copy.deepcopy(data["bindings"][0])), "duplicate_binding_id"),
        ("unsafe binding id", lambda data: data["bindings"][0].update({"binding_id": "../bad"}), "invalid_binding_registry"),
        ("production environment", lambda data: data["bindings"][0].update({"environment": "production"}), "invalid_binding_registry"),
        ("wildcard provider", lambda data: data["bindings"][0].update({"provider_id": "*"}), "invalid_binding_registry"),
        ("wildcard model", lambda data: data["bindings"][0].update({"model_ids": ["*"]}), "invalid_binding_registry"),
        ("wildcard purpose", lambda data: data["bindings"][0].update({"allowed_purposes": ["*"]}), "invalid_binding_registry"),
        ("resolver mode", lambda data: data["bindings"][0].update({"resolution_mode": "env"}), "secret_resolution_not_available"),
        ("material present", lambda data: data["bindings"][0].update({"material_present": True}), "secret_material_field_detected"),
        ("secret value", lambda data: data["bindings"][0].update({"secret_value": "TEST-ONLY-SECRET-MUST-BE-REJECTED"}), "secret_material_field_detected"),
        ("bad validity", lambda data: data["bindings"][0].update({"valid_until": "2026-01-01T00:00:00Z"}), "invalid_binding_registry"),
        ("no valid_until", lambda data: data["bindings"][0].pop("valid_until"), "invalid_binding_registry"),
        ("max calls not one", lambda data: data["bindings"][0].update({"max_calls_per_grant": 2}), "invalid_binding_registry"),
    ],
)
def test_binding_registry_fails_closed_for_unsafe_values(label: str, mutate: Any, expected_code: str) -> None:
    registry = _registry()
    mutate(registry)

    result = _run(registry=registry)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["grant"] is None
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("state", "expected_code"),
    [
        ("registered", "binding_not_active"),
        ("suspended", "binding_suspended"),
        ("revoked", "binding_revoked"),
        ("expired", "binding_expired"),
    ],
)
def test_binding_state_must_be_active_and_current(state: str, expected_code: str) -> None:
    registry = _registry()
    registry["bindings"][0]["state"] = state
    if state == "expired":
        registry["bindings"][0]["valid_until"] = "2026-07-03T00:00:00Z"

    result = _run(registry=registry)

    assert result["passed"] is False
    assert expected_code in _error_codes(result)


def test_binding_state_transitions_are_audited_and_fail_closed_for_invalid_reverse_transition() -> None:
    binding = _registry()["bindings"][0]

    transition = transition_binding_state(
        binding,
        new_state="suspended",
        transition_id="binding-transition-001",
        reason_code="synthetic_pause",
        event_time="2026-07-04T00:10:00Z",
        clock=_clock(),
    )
    repeated = transition_binding_state(
        binding,
        new_state="suspended",
        transition_id="binding-transition-001",
        reason_code="synthetic_pause",
        event_time="2026-07-04T00:10:00Z",
        clock=_clock(),
    )

    assert transition == repeated
    assert transition["previous_state"] == "active"
    assert transition["new_state"] == "suspended"
    assert len(transition["transition_hash"]) == 64

    revoked = copy.deepcopy(binding)
    revoked["state"] = "revoked"
    with pytest.raises(ValueError) as exc_info:
        transition_binding_state(
            revoked,
            new_state="active",
            transition_id="binding-transition-002",
            reason_code="invalid_reverse",
            event_time="2026-07-04T00:10:00Z",
            clock=_clock(),
        )
    assert "invalid_binding_transition" in str(exc_info.value)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unknown version", lambda data: data.update({"authorization_policy_version": "9.9"}), "unsupported_authorization_policy_version"),
        ("draft", lambda data: data.update({"status": "draft"}), "authorization_policy_not_approved"),
        ("live grant", lambda data: data.update({"grant_mode": "sandbox_live"}), "unsupported_grant_mode"),
        ("low quorum", lambda data: data.update({"required_approval_quorum": 1}), "invalid_authorization_policy"),
        ("requester approver", lambda data: data.update({"requester_may_approve": True}), "invalid_authorization_policy"),
        ("network", lambda data: data.update({"allow_network_execution": True}), "authorization_capability_not_allowed"),
        ("tools", lambda data: data.update({"allow_tools": True}), "authorization_capability_not_allowed"),
        ("streaming", lambda data: data.update({"allow_streaming": True}), "authorization_capability_not_allowed"),
        ("trading", lambda data: data.update({"allow_trading_actions": True}), "authorization_capability_not_allowed"),
        ("no lifetime", lambda data: data.update({"max_grant_lifetime_seconds": 0}), "invalid_authorization_policy"),
        ("too many calls", lambda data: data.update({"max_calls": 2}), "invalid_authorization_policy"),
        ("wildcard purpose", lambda data: data.update({"allowed_purposes": ["*"]}), "invalid_authorization_policy"),
    ],
)
def test_policy_fails_closed_for_live_or_unbounded_capabilities(label: str, mutate: Any, expected_code: str) -> None:
    policy = _policy()
    mutate(policy)

    result = _run(policy=policy)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("provider mismatch", lambda data: data.update({"provider_id": "fake"}), "authorization_identity_mismatch"),
        ("model mismatch", lambda data: data.update({"model_id": "other-model"}), "authorization_identity_mismatch"),
        ("adapter mismatch", lambda data: data.update({"adapter_id": "other-adapter"}), "authorization_identity_mismatch"),
        ("environment mismatch", lambda data: data.update({"environment": "production"}), "authorization_environment_mismatch"),
        ("purpose not allowed", lambda data: data.update({"purpose": "broad_research"}), "authorization_purpose_not_allowed"),
        ("task type not allowed", lambda data: data.update({"task_type": "trading"}), "authorization_task_type_not_allowed"),
        ("bad gateway hash", lambda data: data.update({"gateway_request_hash": "not-sha"}), "authorization_lineage_invalid"),
        ("bad artifact hash", lambda data: data.update({"input_artifact_hash": "not-sha"}), "authorization_lineage_invalid"),
        ("bad prompt hash", lambda data: data.update({"prompt_spec_hash": "not-sha"}), "authorization_lineage_invalid"),
        ("missing lineage", lambda data: data.pop("snapshot_id"), "authorization_lineage_invalid"),
        ("budget exceeded", lambda data: data["requested_budget"].update({"max_total_tokens": 999999}), "authorization_budget_exceeded"),
        ("tools", lambda data: data["requested_capabilities"].update({"tools": True}), "authorization_capability_not_allowed"),
        ("streaming", lambda data: data["requested_capabilities"].update({"streaming": True}), "authorization_capability_not_allowed"),
        ("network", lambda data: data["requested_capabilities"].update({"network_execution": True}), "authorization_capability_not_allowed"),
        ("trading", lambda data: data["requested_capabilities"].update({"trading_actions": True}), "authorization_capability_not_allowed"),
        ("secret field", lambda data: data.update({"secret_value": "TEST-ONLY-SECRET-MUST-BE-REJECTED"}), "secret_material_field_detected"),
        ("endpoint injection", lambda data: data.update({"endpoint": "https://provider.invalid"}), "authorization_request_invalid"),
        ("headers injection", lambda data: data.update({"headers": {"Authorization": "TEST-ONLY-SECRET-MUST-BE-REJECTED"}}), "authorization_request_invalid"),
    ],
)
def test_authorization_request_fails_closed_for_scope_identity_lineage_budget_and_secret_fields(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    request = _request()
    mutate(request)

    result = _run(request=request)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["grant"] is None
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("quorum missing", lambda data: data.update(_load_json(FIXTURES_ROOT / "approval_quorum_missing.json")), "approval_quorum_not_met"),
        ("required role missing", lambda data: data["approvals"][1].update({"approver_role": "research_owner"}), "required_approval_role_missing"),
        ("duplicate approver", lambda data: data["approvals"][1].update({"approver_id": "synthetic-research-owner"}), "duplicate_approver"),
        ("requester as approver", lambda data: data["approvals"][0].update({"approver_id": "synthetic-research-runner"}), "requester_cannot_approve"),
        ("expired approval", lambda data: data["approvals"][0].update({"valid_until": "2026-07-03T00:00:00Z"}), "approval_expired"),
        ("revoked approval", lambda data: data["approvals"][0].update({"revoked": True}), "approval_revoked"),
        ("reject", lambda data: data.update(_load_json(FIXTURES_ROOT / "approval_rejected.json")), "approval_rejected"),
        ("request mismatch", lambda data: data["approvals"][0].update({"authorization_request_id": "other-request"}), "approval_invalid"),
    ],
)
def test_approval_records_enforce_quorum_roles_reject_priority_and_requester_separation(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    approvals = _approvals()
    mutate(approvals)

    result = _run(approvals=approvals)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)


def test_approval_set_hash_is_order_independent() -> None:
    context = {
        "authorization_request_id": _request()["authorization_request_id"],
        "requester_id": _request()["requester_id"],
        "required_roles": _policy()["required_approval_roles"],
        "quorum": _policy()["required_approval_quorum"],
    }
    first = validate_approvals(_approvals(), context=context, clock=_clock())
    reversed_payload = {"approval_set_version": "1.0", "approvals": list(reversed(_approvals()["approvals"]))}
    second = validate_approvals(reversed_payload, context=context, clock=_clock())

    assert first["approval_set_hash"] == second["approval_set_hash"]
    assert first["required_roles_satisfied"] == ["research_owner", "risk_reviewer"]


def test_fixed_clock_is_required_and_time_windows_are_enforced() -> None:
    with pytest.raises(ValueError):
        FixedAuthorizationClock.from_iso8601("2026-07-04T00:10:00")

    before = _run(now="2026-06-30T23:59:00Z")
    after = _run(now="2027-01-01T00:00:00Z")
    valid = _run(now="2026-07-04T00:10:00Z")
    repeated = _run(now="2026-07-04T00:10:00Z")

    assert "binding_expired" in _error_codes(before) or "binding_not_active" in _error_codes(before)
    assert "binding_expired" in _error_codes(after)
    assert valid == repeated
    assert valid["grant"]["issued_at"] == "2026-07-04T00:10:00Z"
    assert valid["grant"]["expires_at"] == "2026-07-04T00:25:00Z"


def test_grant_identity_budget_hash_and_one_time_consumption_are_enforced() -> None:
    result = _run()
    grant = result["grant"]

    first = consume_offline_preflight_grant(grant, _request(), clock=_clock())
    second = consume_offline_preflight_grant(first["grant"], _request(), clock=_clock())
    changed_request = _request()
    changed_request["model_id"] = "other-model"
    mismatch = consume_offline_preflight_grant(grant, changed_request, clock=_clock())
    expired = consume_offline_preflight_grant(grant, _request(), clock=_clock("2026-07-04T00:26:00Z"))
    revoked = copy.deepcopy(grant)
    revoked["grant_state"] = "revoked"
    revoked_result = consume_offline_preflight_grant(revoked, _request(), clock=_clock())

    assert first["passed"] is True
    assert first["grant"]["grant_state"] == "consumed"
    assert first["grant"]["consumed_calls"] == 1
    assert second["passed"] is False
    assert "authorization_grant_already_consumed" in _error_codes(second)
    assert mismatch["passed"] is False
    assert "authorization_grant_mismatch" in _error_codes(mismatch)
    assert expired["passed"] is False
    assert "authorization_grant_expired" in _error_codes(expired)
    assert revoked_result["passed"] is False
    assert "authorization_grant_revoked" in _error_codes(revoked_result)
    assert all(value is False for value in first["external_calls"].values())


def test_audit_is_complete_and_external_call_isolation_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in [
            FIXTURES_ROOT / "binding_registry.json",
            FIXTURES_ROOT / "authorization_policy.json",
            FIXTURES_ROOT / "authorization_request.json",
            FIXTURES_ROOT / "approvals.json",
        ]
    }

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-B")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-B")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {
            "openai",
            "anthropic",
            "google_genai",
            "langchain",
            "tushare",
            "qlib",
            "requests",
            "httpx",
            "urllib",
            "websocket",
        }
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = _run()

    assert result["passed"] is True
    assert result["audit"]["binding_id"] == "provider-sandbox-binding-001"
    assert result["audit"]["policy_id"] == "r2c-b-sandbox-single-case"
    assert result["audit"]["approval_quorum_satisfied"] == 2
    assert result["audit"]["live_execution_authorized"] is False
    assert result["audit"]["credential_value_resolved"] is False
    assert result["audit"]["provider_transport_called"] is False
    assert all(value is False for value in result["audit"]["external_calls"].values())
    _assert_no_secret_text(result)
    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert subprocess.run(["git", "ls-files", "data/exports"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_provider_authorization").exists()


def test_provider_config_identity_and_limits_are_reused_without_mutating_r2c_a_adapter() -> None:
    result = _run(adapter_config=_adapter_config())

    assert result["passed"] is True
    assert result["provider_id"] == _adapter_config()["provider_id"]
    assert result["model_id"] == _adapter_config()["model_id"]
    assert result["adapter_id"] == _adapter_config()["adapter_id"]
    assert result["grant"]["budget"]["max_total_tokens"] <= _adapter_config()["limits"]["max_total_tokens"]


def test_cli_success_policy_denial_and_schema_error_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    success = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--binding-registry",
            str(FIXTURES_ROOT / "binding_registry.json"),
            "--policy",
            str(FIXTURES_ROOT / "authorization_policy.json"),
            "--request",
            str(FIXTURES_ROOT / "authorization_request.json"),
            "--approvals",
            str(FIXTURES_ROOT / "approvals.json"),
            "--fixed-now",
            "2026-07-04T00:10:00Z",
            "--output-root",
            str(success_root),
            "--expected-result",
            str(FIXTURES_ROOT / "expected_authorization_result.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["decision"] == "allow"
    assert summary["preflight_authorized"] is True
    assert summary["live_execution_authorized"] is False
    assert summary["credential_value_resolved"] is False
    assert summary["provider_transport_called"] is False
    assert all(value is False for value in summary["external_calls"].values())
    assert (success_root / "authorization_result.json").is_file()

    denied_policy = _policy()
    denied_policy["status"] = "draft"
    denied_policy_path = _write_json(tmp_path / "denied_policy.json", denied_policy)
    denial = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--binding-registry",
            str(FIXTURES_ROOT / "binding_registry.json"),
            "--policy",
            str(denied_policy_path),
            "--request",
            str(FIXTURES_ROOT / "authorization_request.json"),
            "--approvals",
            str(FIXTURES_ROOT / "approvals.json"),
            "--fixed-now",
            "2026-07-04T00:10:00Z",
            "--output-root",
            str(tmp_path / "denial"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert denial.returncode == 1
    assert json.loads(denial.stdout)["passed"] is False

    schema_error = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--binding-registry",
            str(FIXTURES_ROOT / "binding_registry.json"),
            "--policy",
            str(FIXTURES_ROOT / "authorization_policy.json"),
            "--request",
            str(FIXTURES_ROOT / "authorization_request.json"),
            "--approvals",
            str(FIXTURES_ROOT / "approvals.json"),
            "--fixed-now",
            "2026-07-04T00:10:00",
            "--output-root",
            str(tmp_path / "schema_error"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert schema_error.returncode == 2
