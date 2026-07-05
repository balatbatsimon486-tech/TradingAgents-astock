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

from datang_extensions.llm_gateway.sandbox_readiness.gate import build_expected_readiness_result, run_offline_sandbox_readiness  # noqa: E402

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_c"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_sandbox_readiness.py"
FORBIDDEN_RESULT_FIELDS = {
    "future_return", "next_return", "forward_return", "target_return", "realized_return",
    "expected_return", "pnl", "profit", "sharpe", "max_drawdown", "win_rate",
    "position_size", "target_weight", "order_size", "buy", "sell", "hold",
    "recommendation", "target_price", "order", "auto_trade",
}
SECRET_TEXT_MARKERS = [
    "TEST-ONLY-SECRET-MUST-BE-REJECTED", "Bearer ", "sk-", "Authorization",
    "Cookie", "Set-Cookie", "private_key", "\"credential_value\"", "\"secret_value\"",
]


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _profile() -> dict[str, Any]:
    return _load_json("sandbox_profile.json")


def _secret_proposal() -> dict[str, Any]:
    return _load_json("secret_storage_proposal.json")


def _egress_policy() -> dict[str, Any]:
    return _load_json("egress_policy.json")


def _manifest() -> dict[str, Any]:
    return _load_json("run_manifest.json")


def _threat_model() -> dict[str, Any]:
    return _load_json("threat_model.json")


def _evidence() -> dict[str, Any]:
    return _load_json("prerequisite_evidence.json")


def _incident_response() -> dict[str, Any]:
    return _load_json("incident_response.json")


def _run(
    profile: dict[str, Any] | None = None,
    secret_proposal: dict[str, Any] | None = None,
    egress_policy: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    threat_model: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    incident_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_offline_sandbox_readiness(
        profile or _profile(),
        secret_proposal or _secret_proposal(),
        egress_policy or _egress_policy(),
        manifest or _manifest(),
        threat_model or _threat_model(),
        evidence or _evidence(),
        incident_response or _incident_response(),
    )


def _error_codes(result: dict[str, Any]) -> list[str]:
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


def test_valid_readiness_package_is_ready_for_human_review_and_matches_expected_fixture() -> None:
    result = _run()
    expected = _load_json("expected_readiness_result.json")

    assert result["stage"] == "tradingagents_r2c_c_offline_sandbox_readiness"
    assert result["passed"] is True
    assert result["decision"] == "ready_for_human_review"
    assert result["ready_for_human_review"] is True
    assert result["human_review_completed"] is False
    assert result["secret_resolution_authorized"] is False
    assert result["network_execution_authorized"] is False
    assert result["live_execution_authorized"] is False
    assert result["credential_value_resolved"] is False
    assert result["provider_transport_called"] is False
    assert result["blocking_findings"] == []
    assert result["manual_review_requirements"]
    assert all(value is False for value in result["external_calls"].values())
    for field in (
        "profile_hash", "secret_proposal_hash", "egress_policy_hash", "manifest_hash",
        "threat_model_hash", "evidence_hash", "incident_plan_hash", "readiness_package_hash", "audit_hash",
    ):
        assert len(result[field]) == 64
    assert build_expected_readiness_result(result) == expected
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    _assert_no_forbidden_key(result)
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unknown version", lambda data: data.update({"sandbox_profile_contract_version": "9.9"}), "unsupported_sandbox_profile_version"),
        ("production environment", lambda data: data.update({"environment": "production"}), "sandbox_profile_invalid"),
        ("wildcard provider", lambda data: data.update({"provider_id": "*"}), "sandbox_profile_invalid"),
        ("model mismatch", lambda data: data.update({"model_id": "other-model"}), "readiness_identity_mismatch"),
        ("max calls", lambda data: data.update({"max_calls": 2}), "sandbox_profile_invalid"),
        ("tools enabled", lambda data: data.update({"tools_enabled": True}), "sandbox_profile_capability_not_allowed"),
        ("streaming enabled", lambda data: data.update({"streaming_enabled": True}), "sandbox_profile_capability_not_allowed"),
        ("fallback enabled", lambda data: data.update({"fallback_enabled": True}), "sandbox_profile_capability_not_allowed"),
        ("production data", lambda data: data.update({"production_data_allowed": True}), "sandbox_profile_capability_not_allowed"),
        ("trading actions", lambda data: data.update({"trading_actions_allowed": True}), "sandbox_profile_capability_not_allowed"),
        ("secret material", lambda data: data.update({"credential_value": "TEST-ONLY-SECRET-MUST-BE-REJECTED"}), "secret_material_field_detected"),
    ],
)
def test_sandbox_profile_fails_closed_for_live_or_unsafe_capabilities(label: str, mutate: Any, expected_code: str) -> None:
    profile = _profile()
    mutate(profile)
    result = _run(profile=profile)
    assert result["passed"] is False, label
    assert result["decision"] == "blocked"
    assert result["ready_for_human_review"] is False
    assert expected_code in _error_codes(result)
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("material present", lambda data: data.update({"secret_material_present": True}), "secret_storage_proposal_invalid"),
        ("resolver implemented", lambda data: data.update({"resolver_implemented": True}), "secret_storage_proposal_invalid"),
        ("backend configured", lambda data: data.update({"backend_status": "configured"}), "secret_storage_proposal_invalid"),
        ("plaintext export", lambda data: data.update({"plaintext_export_allowed": True}), "secret_storage_proposal_invalid"),
        ("environment fallback", lambda data: data.update({"environment_variable_fallback_allowed": True}), "secret_storage_proposal_invalid"),
        ("local file fallback", lambda data: data.update({"local_file_fallback_allowed": True}), "secret_storage_proposal_invalid"),
        ("git storage", lambda data: data.update({"git_storage_allowed": True}), "secret_storage_proposal_invalid"),
        ("real secret alias", lambda data: data.update({"secret_name": "prod/provider/key"}), "secret_material_field_detected"),
    ],
)
def test_secret_storage_proposal_never_resolves_or_describes_real_secret_material(label: str, mutate: Any, expected_code: str) -> None:
    proposal = _secret_proposal()
    mutate(proposal)
    result = _run(secret_proposal=proposal)
    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["secret_resolution_authorized"] is False
    assert result["credential_value_resolved"] is False
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("network execution", lambda data: data.update({"network_execution_enabled": True}), "egress_policy_invalid"),
        ("http scheme", lambda data: data.update({"allowed_scheme": "http"}), "egress_policy_invalid"),
        ("real host", lambda data: data.update({"allowed_hosts": ["api.provider.example"]}), "egress_policy_invalid"),
        ("wildcard host", lambda data: data.update({"allowed_hosts": ["*.invalid"]}), "egress_policy_invalid"),
        ("localhost", lambda data: data.update({"localhost_allowed": True}), "egress_policy_invalid"),
        ("ip literal", lambda data: data.update({"allowed_hosts": ["127.0.0.1"]}), "egress_policy_invalid"),
        ("wrong port", lambda data: data.update({"allowed_ports": [80]}), "egress_policy_invalid"),
        ("redirects", lambda data: data.update({"redirects_allowed": True}), "egress_policy_invalid"),
        ("proxy", lambda data: data.update({"proxy_allowed": True}), "egress_policy_invalid"),
        ("private network", lambda data: data.update({"private_network_allowed": True}), "egress_policy_invalid"),
        ("host with path", lambda data: data.update({"allowed_hosts": ["provider.invalid/path"]}), "egress_policy_invalid"),
    ],
)
def test_egress_policy_is_offline_and_synthetic_only(label: str, mutate: Any, expected_code: str) -> None:
    egress = _egress_policy()
    mutate(egress)
    result = _run(egress_policy=egress)
    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["network_execution_authorized"] is False
    assert result["provider_transport_called"] is False

@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("live mode", lambda data: data.update({"run_mode": "live_single_call"}), "run_manifest_invalid"),
        ("too many calls", lambda data: data.update({"max_calls": 2}), "run_manifest_invalid"),
        ("output tokens exceed profile", lambda data: data.update({"max_output_tokens": 4096}), "run_manifest_budget_exceeded"),
        ("cost exceed", lambda data: data.update({"max_cost_usd": "9.99"}), "run_manifest_budget_exceeded"),
        ("long window", lambda data: data.update({"proposed_window_end": "2026-07-06T01:00:00Z"}), "run_manifest_window_invalid"),
        ("bad utc", lambda data: data.update({"proposed_window_start": "2026-07-06T00:00:00"}), "run_manifest_window_invalid"),
        ("tools", lambda data: data.update({"tools": True}), "run_manifest_capability_not_allowed"),
        ("streaming", lambda data: data.update({"streaming": True}), "run_manifest_capability_not_allowed"),
        ("fallback", lambda data: data.update({"fallback": True}), "run_manifest_capability_not_allowed"),
        ("production data", lambda data: data.update({"production_data": True}), "run_manifest_capability_not_allowed"),
        ("trading actions", lambda data: data.update({"trading_actions": True}), "run_manifest_capability_not_allowed"),
        ("empty manual review", lambda data: data.update({"manual_review_requirements": []}), "manual_review_required"),
    ],
)
def test_run_manifest_keeps_budget_window_and_manual_review_bounded(label: str, mutate: Any, expected_code: str) -> None:
    manifest = _manifest()
    mutate(manifest)
    result = _run(manifest=manifest)
    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["live_execution_authorized"] is False


def test_threat_model_requires_coverage_controls_and_order_independent_hash() -> None:
    result = _run()
    reversed_model = _threat_model()
    reversed_model["threats"] = list(reversed(reversed_model["threats"]))
    reversed_result = _run(threat_model=reversed_model)
    assert result["passed"] is True
    assert reversed_result["passed"] is True
    assert result["threat_model_hash"] == reversed_result["threat_model_hash"]

    missing = _threat_model()
    missing["threats"] = missing["threats"][1:]
    assert "threat_model_missing_required_threat" in _error_codes(_run(threat_model=missing))

    unsafe = _threat_model()
    unsafe["threats"][0]["review_status"] = "risk_accepted_for_live"
    assert "threat_model_invalid" in _error_codes(_run(threat_model=unsafe))

    no_controls = _threat_model()
    no_controls["threats"][0]["required_controls"] = []
    assert "threat_model_invalid" in _error_codes(_run(threat_model=no_controls))


def test_prerequisite_evidence_references_all_sealed_milestones_and_order_independent_hash() -> None:
    result = _run()
    reversed_evidence = _evidence()
    reversed_evidence["milestones"] = list(reversed(reversed_evidence["milestones"]))
    reversed_evidence["evidence_refs"] = list(reversed(reversed_evidence["evidence_refs"]))
    reversed_result = _run(evidence=reversed_evidence)
    assert result["passed"] is True
    assert reversed_result["passed"] is True
    assert result["evidence_hash"] == reversed_result["evidence_hash"]

    baseline_mismatch = _evidence()
    baseline_mismatch["stable_baseline"] = "bad"
    assert "evidence_baseline_mismatch" in _error_codes(_run(evidence=baseline_mismatch))

    missing_milestone = _evidence()
    missing_milestone["milestones"] = [item for item in missing_milestone["milestones"] if item["milestone"] != "R2A"]
    assert "evidence_missing_milestone" in _error_codes(_run(evidence=missing_milestone))

    missing_category = _evidence()
    missing_category["evidence_refs"] = [item for item in missing_category["evidence_refs"] if item["evidence_id"] != "no-network-evidence"]
    assert "evidence_missing_required_ref" in _error_codes(_run(evidence=missing_category))


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("default not blocked", lambda data: data.update({"default_state": "enabled"}), "incident_response_invalid"),
        ("live enabled", lambda data: data.update({"live_execution_enabled": True}), "incident_response_invalid"),
        ("auto enable", lambda data: data.update({"automatic_enable_allowed": True}), "incident_response_invalid"),
        ("not fail closed", lambda data: data.update({"fail_closed": False}), "incident_response_invalid"),
        ("missing rotation", lambda data: data.pop("secret_exposure_rotation_plan"), "incident_response_invalid"),
        ("missing network stop", lambda data: data.pop("unauthorized_network_shutdown_plan"), "incident_response_invalid"),
        ("auto retry", lambda data: data.update({"automatic_retry_after_incident": True}), "incident_response_invalid"),
        ("missing condition", lambda data: data.update({"stop_conditions": data["stop_conditions"][1:]}), "incident_stop_condition_missing"),
    ],
)
def test_incident_response_and_kill_switch_fail_closed(label: str, mutate: Any, expected_code: str) -> None:
    incident = _incident_response()
    mutate(incident)
    result = _run(incident_response=incident)
    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["live_execution_authorized"] is False


def test_external_call_isolation_fixture_integrity_and_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_paths = sorted(FIXTURES_ROOT.glob("*.json"))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in fixture_paths}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-C")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-C")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {"openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "requests", "httpx", "urllib", "websocket", "dotenv"}
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        if name == "datang_extensions.llm_gateway.provider_adapters.chat_adapter":
            raise AssertionError("R2C-C must not call the provider adapter transport layer")
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
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "sandbox_readiness").exists()


def test_sandbox_readiness_code_has_no_real_network_secret_or_sdk_clients() -> None:
    package_root = PROJECT_ROOT / "datang_extensions" / "llm_gateway" / "sandbox_readiness"
    if not package_root.exists():
        pytest.fail("sandbox_readiness package must exist")
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(package_root.glob("*.py")))
    forbidden_snippets = ["requests", "httpx", "urllib", "socket", "os.environ", "getenv", "dotenv", "openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "shell=True", "os.system"]
    for snippet in forbidden_snippets:
        assert snippet not in text


def test_cli_success_blocked_and_schema_error_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    success = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--sandbox-profile", str(FIXTURES_ROOT / "sandbox_profile.json"),
         "--secret-storage-proposal", str(FIXTURES_ROOT / "secret_storage_proposal.json"),
         "--egress-policy", str(FIXTURES_ROOT / "egress_policy.json"),
         "--run-manifest", str(FIXTURES_ROOT / "run_manifest.json"),
         "--threat-model", str(FIXTURES_ROOT / "threat_model.json"),
         "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
         "--incident-response", str(FIXTURES_ROOT / "incident_response.json"),
         "--output-root", str(success_root),
         "--expected-result", str(FIXTURES_ROOT / "expected_readiness_result.json")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["decision"] == "ready_for_human_review"
    assert summary["ready_for_human_review"] is True
    assert summary["human_review_completed"] is False
    assert summary["secret_resolution_authorized"] is False
    assert summary["network_execution_authorized"] is False
    assert summary["live_execution_authorized"] is False
    assert summary["credential_value_resolved"] is False
    assert summary["provider_transport_called"] is False
    assert all(value is False for value in summary["external_calls"].values())
    assert (success_root / "sandbox_readiness_result.json").is_file()

    blocked_egress = _egress_policy()
    blocked_egress["allowed_hosts"] = ["api.provider.example"]
    blocked_path = _write_json(tmp_path / "blocked_egress.json", blocked_egress)
    blocked = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--sandbox-profile", str(FIXTURES_ROOT / "sandbox_profile.json"),
         "--secret-storage-proposal", str(FIXTURES_ROOT / "secret_storage_proposal.json"),
         "--egress-policy", str(blocked_path),
         "--run-manifest", str(FIXTURES_ROOT / "run_manifest.json"),
         "--threat-model", str(FIXTURES_ROOT / "threat_model.json"),
         "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
         "--incident-response", str(FIXTURES_ROOT / "incident_response.json"),
         "--output-root", str(tmp_path / "blocked")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["decision"] == "blocked"

    bad_manifest = _manifest()
    bad_manifest["proposed_window_start"] = "not-a-time"
    bad_manifest_path = _write_json(tmp_path / "bad_manifest.json", bad_manifest)
    schema_error = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--sandbox-profile", str(FIXTURES_ROOT / "sandbox_profile.json"),
         "--secret-storage-proposal", str(FIXTURES_ROOT / "secret_storage_proposal.json"),
         "--egress-policy", str(FIXTURES_ROOT / "egress_policy.json"),
         "--run-manifest", str(bad_manifest_path),
         "--threat-model", str(FIXTURES_ROOT / "threat_model.json"),
         "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"),
         "--incident-response", str(FIXTURES_ROOT / "incident_response.json"),
         "--output-root", str(tmp_path / "schema_error")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert schema_error.returncode == 2
    assert json.loads(schema_error.stdout)["passed"] is False
