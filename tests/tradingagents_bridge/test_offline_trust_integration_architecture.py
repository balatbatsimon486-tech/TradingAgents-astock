
from __future__ import annotations

import builtins, copy, json, os, socket, subprocess, sys
from pathlib import Path
from typing import Any
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.trust_integration_architecture.gate import build_expected_architecture_result, run_offline_trust_integration_architecture  # noqa: E402

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_f"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_trust_integration_architecture.py"
SECRET_TEXT_MARKERS = ["Bearer ", "sk-", "Authorization", "Cookie", "private_key", "signature_value\"", "nonce_value\"", "credential_value\"", "TEST-ONLY-SECRET", "person@example.invalid"]
REAL_VENDOR_MARKERS: list[str] = []
FALSE_FIELDS = ("real_vendor_selected", "procurement_approved", "deployment_approved", "change_request_approved", "rollback_test_executed", "network_configuration_applied", "identity_service_configured", "signature_service_configured", "nonce_service_configured", "authorization_issuer_configured", "real_integration_started", "secret_resolution_authorized", "network_execution_authorized", "live_execution_authorized", "credential_value_resolved", "provider_transport_called")
HASH_FIELDS = ("candidate_catalog_hash", "evaluation_policy_hash", "assessment_result_hash", "recommendation_set_hash", "deployment_topology_hash", "trust_zone_model_hash", "data_flow_set_hash", "ownership_matrix_hash", "change_control_hash", "rollback_plan_hash", "drill_plan_hash", "evidence_bundle_hash", "blocking_findings_hash", "required_real_world_actions_hash", "architecture_package_hash", "audit_hash")
FORBIDDEN_RESULT_FIELDS = {"future_return", "expected_return", "pnl", "profit", "sharpe", "max_drawdown", "win_rate", "position_size", "target_weight", "order_size", "buy", "sell", "hold", "target_price", "auto_trade"}

def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))

def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path

def _run(**overrides: dict[str, Any]) -> dict[str, Any]:
    names = {
        "trust_boundary": "r2c_e_trust_boundary_result.json",
        "catalog": "candidate_catalog.json",
        "policy": "evaluation_policy.json",
        "topology": "deployment_topology.json",
        "ownership": "ownership_matrix.json",
        "change": "change_control_plan.json",
        "rollback": "rollback_plan.json",
        "drill": "drill_plan.json",
        "evidence": "prerequisite_evidence.json",
    }
    data = {key: overrides.get(key) or _load_json(name) for key, name in names.items()}
    return run_offline_trust_integration_architecture(data["trust_boundary"], data["catalog"], data["policy"], data["topology"], data["ownership"], data["change"], data["rollback"], data["drill"], data["evidence"])

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

def _assert_no_secret_or_vendor_text(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for marker in SECRET_TEXT_MARKERS + REAL_VENDOR_MARKERS:
        assert marker not in text

def _assert_ready_result(result: dict[str, Any]) -> None:
    assert result["stage"] == "tradingagents_r2c_f_offline_trust_integration_architecture"
    assert result["passed"] is True
    assert result["decision"] == "ready_for_architecture_review"
    assert result["architecture_package_sealed"] is True
    assert result["ready_for_architecture_review"] is True
    for field in ("candidate_assessment_ready", "candidate_recommendation_ready", "deployment_topology_contract_ready", "trust_zone_model_ready", "ownership_matrix_ready", "change_control_plan_ready", "rollback_plan_ready", "operational_drill_plan_ready"):
        assert result[field] is True
    for field in FALSE_FIELDS:
        assert result[field] is False
    assert result["required_real_world_actions"]
    assert result["blocking_findings"] == []
    assert all(value is False for value in result["external_calls"].values())
    for field in HASH_FIELDS:
        assert len(result[field]) == 64, field
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    _assert_no_forbidden_key(result)
    _assert_no_secret_or_vendor_text(result)

def test_valid_architecture_package_is_ready_and_matches_expected_fixture() -> None:
    result = _run()
    _assert_ready_result(result)
    assert build_expected_architecture_result(result) == _load_json("expected_architecture_result.json")

def test_candidate_recommendations_are_synthetic_stable_and_not_procurement() -> None:
    result = _run()
    assert [item["recommended_candidate_id"] for item in result["recommendations"]] == ["identity-candidate-a", "issuer-candidate-a", "nonce-candidate-a", "signature-candidate-a"]
    for item in result["recommendations"]:
        assert item["recommendation_ready"] is True
        assert item["vendor_selected"] is False
        assert item["procurement_approved"] is False
        assert item["candidate_score"] >= "85.00"

def test_order_independence_for_candidates_topology_ownership_and_drills() -> None:
    first = _run()
    catalog = _load_json("candidate_catalog.json"); catalog["candidates"] = list(reversed(catalog["candidates"]))
    topology = _load_json("deployment_topology.json"); topology["nodes"] = list(reversed(topology["nodes"])); topology["edges"] = list(reversed(topology["edges"])); topology["data_flows"] = list(reversed(topology["data_flows"]))
    ownership = _load_json("ownership_matrix.json"); ownership["assignments"] = list(reversed(ownership["assignments"]))
    drill = _load_json("drill_plan.json"); drill["drills"] = list(reversed(drill["drills"]))
    second = _run(catalog=catalog, topology=topology, ownership=ownership, drill=drill)
    assert second["passed"] is True
    for field in ("assessment_result_hash", "recommendation_set_hash", "deployment_topology_hash", "trust_zone_model_hash", "data_flow_set_hash", "ownership_matrix_hash", "drill_plan_hash", "architecture_package_hash"):
        assert first[field] == second[field]


@pytest.mark.parametrize(("fixture", "component", "expected_code"), [
    ("real_vendor_name_negative.json", "catalog", "real_vendor_identifier_not_allowed"),
    ("missing_service_class_negative.json", "catalog", "candidate_service_class_missing"),
    ("mandatory_control_failure_negative.json", "catalog", "mandatory_control_failed"),
    ("invalid_weight_total_negative.json", "policy", "evaluation_weight_total_invalid"),
    ("real_endpoint_negative.json", "topology", "real_endpoint_not_allowed"),
    ("network_enabled_negative.json", "topology", "network_connection_must_be_disabled"),
    ("undeclared_data_flow_negative.json", "topology", "undeclared_data_flow"),
    ("duplicate_accountable_negative.json", "ownership", "accountable_role_not_unique"),
    ("separation_of_duties_negative.json", "ownership", "separation_of_duties_violation"),
    ("change_approved_negative.json", "change", "change_approval_not_available"),
    ("deployment_approved_negative.json", "topology", "invalid_deployment_topology"),
    ("rollback_executed_negative.json", "rollback", "rollback_execution_not_available"),
    ("drill_executed_negative.json", "drill", "drill_execution_not_available"),
    ("real_integration_started_negative.json", "evidence", "architecture_evidence_invalid"),
    ("baseline_mismatch_negative.json", "evidence", "architecture_evidence_invalid"),
    ("trust_package_mismatch_negative.json", "evidence", "architecture_evidence_invalid"),
])
def test_negative_fixtures_fail_closed(fixture: str, component: str, expected_code: str) -> None:
    result = _run(**{component: _load_json(fixture)})
    assert result["passed"] is False, fixture
    assert result["decision"] == "blocked"
    assert result["ready_for_architecture_review"] is False
    assert expected_code in _codes(result)
    for field in FALSE_FIELDS:
        assert result[field] is False
    _assert_no_secret_or_vendor_text(result)

@pytest.mark.parametrize(("mutate", "expected_code"), [
    (lambda d: d.update({"synthetic_only": False}), "candidate_catalog_must_be_synthetic"),
    (lambda d: d["candidates"].append(copy.deepcopy(d["candidates"][0])), "duplicate_candidate_id"),
    (lambda d: d["candidates"][0].update({"status": "selected"}), "invalid_candidate_catalog"),
    (lambda d: d["candidates"][0].update({"capability_claims_verified": True}), "invalid_candidate_catalog"),
    (lambda d: d["candidates"][0].update({"endpoint": "synthetic-endpoint"}), "real_endpoint_not_allowed"),
    (lambda d: d["candidates"][0]["scored_attributes"].update({"security_controls": "-1"}), "candidate_score_invalid"),
    (lambda d: d["candidates"][0]["scored_attributes"].update({"security_controls": "11"}), "candidate_score_invalid"),
])
def test_candidate_catalog_validation_edges(mutate: Any, expected_code: str) -> None:
    catalog = _load_json("candidate_catalog.json")
    mutate(catalog)
    result = _run(catalog=catalog)
    assert result["passed"] is False
    assert expected_code in _codes(result)

def test_recommendation_threshold_blocks_unqualified_service_class() -> None:
    policy = _load_json("evaluation_policy.json")
    policy["recommendation_threshold"] = "99.00"
    result = _run(policy=policy)
    assert result["passed"] is False
    assert "candidate_recommendation_unavailable" in _codes(result)
    assert result["candidate_recommendation_ready"] is False

def test_blocking_findings_are_structured_and_keep_package_blocked() -> None:
    change = _load_json("change_control_plan.json")
    change["abort_conditions"] = []
    result = _run(change=change)
    assert result["passed"] is False
    assert result["decision"] == "blocked"
    assert result["blocking_findings"] == result["errors"]
    assert "invalid_change_control_plan" in _codes(result)
    for error in result["errors"]:
        assert set(error) == {"code", "message", "field_path"}

def test_external_call_isolation_fixture_integrity_and_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_paths = sorted(FIXTURES_ROOT.glob("*.json"))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in fixture_paths}
    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-F")
    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-F")
    real_import = builtins.__import__
    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {"openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "requests", "httpx", "urllib", "websocket", "dotenv", "cryptography", "secrets"}
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        if name == "datang_extensions.llm_gateway.provider_adapters.chat_adapter":
            raise AssertionError("R2C-F must not call provider adapter transport")
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
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "trust_integration_architecture").exists()

def test_trust_integration_code_has_no_real_network_secret_crypto_deploy_or_provider_clients() -> None:
    package_root = PROJECT_ROOT / "datang_extensions" / "llm_gateway" / "trust_integration_architecture"
    assert package_root.exists()
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(package_root.glob("*.py")))
    for snippet in ["requests", "httpx", "urllib", "socket", "os.environ", "getenv", "dotenv", "openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "secrets", "urandom", "terraform", "pulumi", "cloudformation", "kubernetes", "docker", "shell=True", "os.system"]:
        assert snippet not in text

def test_cli_success_blocked_schema_and_disallowed_live_args_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    args = [sys.executable, str(SCRIPT_PATH), "--r2c-e-trust-boundary-result", str(FIXTURES_ROOT / "r2c_e_trust_boundary_result.json"), "--candidate-catalog", str(FIXTURES_ROOT / "candidate_catalog.json"), "--evaluation-policy", str(FIXTURES_ROOT / "evaluation_policy.json"), "--deployment-topology", str(FIXTURES_ROOT / "deployment_topology.json"), "--ownership-matrix", str(FIXTURES_ROOT / "ownership_matrix.json"), "--change-control-plan", str(FIXTURES_ROOT / "change_control_plan.json"), "--rollback-plan", str(FIXTURES_ROOT / "rollback_plan.json"), "--drill-plan", str(FIXTURES_ROOT / "drill_plan.json"), "--prerequisite-evidence", str(FIXTURES_ROOT / "prerequisite_evidence.json"), "--output-root", str(success_root), "--expected-result", str(FIXTURES_ROOT / "expected_architecture_result.json")]
    success = subprocess.run(args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert success.returncode == 0, success.stderr + success.stdout
    summary = json.loads(success.stdout)
    _assert_ready_result(summary)
    assert (success_root / "trust_integration_architecture_result.json").is_file()
    blocked_catalog = _load_json("candidate_catalog.json"); blocked_catalog["synthetic_only"] = False
    blocked_path = _write_json(tmp_path / "blocked_catalog.json", blocked_catalog)
    blocked_args = list(args); blocked_args[blocked_args.index(str(FIXTURES_ROOT / "candidate_catalog.json"))] = str(blocked_path); blocked_args[blocked_args.index(str(success_root))] = str(tmp_path / "blocked"); blocked_args = blocked_args[:-2]
    blocked = subprocess.run(blocked_args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["decision"] == "blocked"
    bad_schema = tmp_path / "bad_schema.json"; bad_schema.write_text("[]", encoding="utf-8")
    schema_args = list(args); schema_args[schema_args.index(str(FIXTURES_ROOT / "r2c_e_trust_boundary_result.json"))] = str(bad_schema); schema_args[schema_args.index(str(success_root))] = str(tmp_path / "schema_error"); schema_args = schema_args[:-2]
    schema_error = subprocess.run(schema_args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert schema_error.returncode == 2
    assert subprocess.run([sys.executable, str(SCRIPT_PATH), "--deploy"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).returncode == 2
