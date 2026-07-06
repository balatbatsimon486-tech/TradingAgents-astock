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

from datang_extensions.llm_gateway.architecture_review.gate import (  # noqa: E402
    build_expected_architecture_review_result,
    run_offline_architecture_review,
)
from datang_extensions.llm_gateway.architecture_review.supersede import evaluate_supersede_state  # noqa: E402

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_g"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_architecture_review.py"
FALSE_FIELDS = (
    "architecture_review_completed",
    "reviewer_identity_verified",
    "review_signatures_verified",
    "architecture_decision_approved",
    "risk_acceptance_approved",
    "waiver_approved",
    "vendor_selection_approved",
    "procurement_approved",
    "deployment_authorized",
    "network_change_authorized",
    "real_integration_started",
    "secret_resolution_authorized",
    "network_execution_authorized",
    "live_execution_authorized",
    "credential_value_resolved",
    "provider_transport_called",
)
HASH_FIELDS = (
    "review_charter_hash",
    "review_record_set_hash",
    "findings_set_hash",
    "dissent_set_hash",
    "remediation_plan_hash",
    "risk_acceptance_request_set_hash",
    "waiver_request_set_hash",
    "decision_record_draft_hash",
    "supersede_policy_hash",
    "evidence_bundle_hash",
    "blocking_findings_hash",
    "required_real_world_actions_hash",
    "architecture_review_package_hash",
    "audit_hash",
)
FORBIDDEN_RESULT_FIELDS = {
    "real_name",
    "email",
    "employee_id",
    "signature_value",
    "certificate",
    "private_key",
    "public_key",
    "vendor_selected",
    "endpoint",
    "cidr",
    "api_key",
    "token",
    "target_price",
    "target_weight",
    "position_size",
    "buy",
    "sell",
    "hold",
    "recommendation",
}


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _payloads(**overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names = {
        "architecture_result": "r2c_f_architecture_result.json",
        "review_charter": "review_charter.json",
        "review_records": "review_records.json",
        "findings": "findings.json",
        "dissent_records": "dissent_records.json",
        "remediation_plan": "remediation_plan.json",
        "risk_acceptance_requests": "risk_acceptance_requests.json",
        "waiver_requests": "waiver_requests.json",
        "decision_record_draft": "decision_record_draft.json",
        "supersede_policy": "supersede_policy.json",
        "prerequisite_evidence": "prerequisite_evidence.json",
    }
    return {key: copy.deepcopy(overrides.get(key) or _load_json(name)) for key, name in names.items()}


def _run(**overrides: dict[str, Any]) -> dict[str, Any]:
    p = _payloads(**overrides)
    return run_offline_architecture_review(
        p["architecture_result"],
        p["review_charter"],
        p["review_records"],
        p["findings"],
        p["dissent_records"],
        p["remediation_plan"],
        p["risk_acceptance_requests"],
        p["waiver_requests"],
        p["decision_record_draft"],
        p["supersede_policy"],
        p["prerequisite_evidence"],
        fixed_now="2030-01-01T00:10:00Z",
    )


def _codes(result: dict[str, Any]) -> list[str]:
    return [str(error.get("code", "")) for error in result.get("errors", [])]


def _assert_no_forbidden_key(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            assert lowered not in FORBIDDEN_RESULT_FIELDS, lowered
            _assert_no_forbidden_key(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_key(item)


def _assert_ready_result(result: dict[str, Any]) -> None:
    assert result["stage"] == "tradingagents_r2c_g_offline_architecture_review"
    assert result["architecture_review_contract_version"] == "1.0"
    assert result["passed"] is True
    assert result["decision"] == "ready_for_architecture_signoff"
    assert result["architecture_review_evidence_sealed"] is True
    assert result["review_role_coverage_complete"] is True
    assert result["review_findings_catalog_ready"] is True
    assert result["remediation_plan_ready"] is True
    assert result["architecture_decision_record_ready"] is True
    assert result["supersede_policy_ready"] is True
    assert result["ready_for_architecture_signoff"] is True
    for field in FALSE_FIELDS:
        assert result[field] is False, field
    assert result["required_real_world_actions"]
    assert all(value is False for value in result["external_calls"].values())
    assert result["errors"] == []
    assert result["blocking_findings"] == []
    for field in HASH_FIELDS:
        assert len(result[field]) == 64, field
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    _assert_no_forbidden_key(result)


def test_valid_review_package_is_ready_and_matches_expected_fixture() -> None:
    result = _run()
    _assert_ready_result(result)
    assert build_expected_architecture_review_result(result) == _load_json("expected_review_result.json")


def test_review_charter_validates_baseline_hash_roles_quorum_and_real_flags() -> None:
    result = _run()
    assert result["review_charter"]["stable_baseline"] == "1330d21562e43346502bbee5816236b4e806168d"
    assert result["review_charter"]["architecture_package_hash"] == "7f5c95724b82724138a9b7a173bd5a5dbc7a6260f02cf962806bbed89e4e0682"
    assert result["required_reviewer_roles"] == [
        "data_governance_reviewer",
        "incident_response_reviewer",
        "operations_reviewer",
        "platform_architecture_reviewer",
        "security_architecture_reviewer",
    ]
    assert result["covered_reviewer_roles"] == result["required_reviewer_roles"]
    assert result["review_charter"]["real_reviewers_assigned"] is False
    assert result["review_charter"]["real_signatures_present"] is False


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d.update({"review_charter_version": "9.9"}), "unsupported_architecture_review_version"),
        (lambda d: d.update({"stable_baseline": "bad-baseline"}), "stable_baseline_mismatch"),
        (lambda d: d.update({"architecture_package_hash": "0" * 64}), "architecture_package_mismatch"),
        (lambda d: d["required_reviewer_roles"].pop(), "required_reviewer_role_missing"),
        (lambda d: d.update({"required_role_quorum": 4}), "review_quorum_not_met"),
        (lambda d: d.update({"requester_may_review": True}), "requester_cannot_review"),
        (lambda d: d["review_scope"].append("*"), "invalid_review_charter"),
        (lambda d: d.update({"real_reviewers_assigned": True}), "invalid_review_charter"),
        (lambda d: d.update({"real_signatures_present": True}), "invalid_review_charter"),
    ],
)
def test_review_charter_negative_edges(mutate: Any, expected_code: str) -> None:
    charter = _load_json("review_charter.json")
    mutate(charter)
    result = _run(review_charter=charter)
    assert result["passed"] is False
    assert expected_code in _codes(result)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["records"][0].update({"reviewer_id": d["records"][1]["reviewer_id"]}), "duplicate_reviewer"),
        (lambda d: d["records"][0].update({"reviewer_role": "research_owner"}), "requester_cannot_review"),
        (lambda d: d["records"][0].update({"valid_until": "2030-01-01T00:01:00Z"}), "review_record_expired"),
        (lambda d: d["records"][0].update({"recorded_at": "2030-01-01T00:05:00"}), "architecture_review_error"),
        (lambda d: d["records"][0].update({"recommendation": "recommend_block"}), "review_block_recommendation_present"),
        (lambda d: d["records"][0].update({"identity_verification_status": "verified"}), "reviewer_identity_verification_unavailable"),
        (lambda d: d["records"][0].update({"signature_status": "verified"}), "review_signature_verification_unavailable"),
        (lambda d: d["records"][0].update({"recommendation": "abstain"}), "review_quorum_not_met"),
    ],
)
def test_review_record_negative_edges(mutate: Any, expected_code: str) -> None:
    records = _load_json("review_records.json")
    mutate(records)
    result = _run(review_records=records)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_review_record_order_does_not_change_hash() -> None:
    first = _run()
    records = _load_json("review_records.json")
    records["records"] = list(reversed(records["records"]))
    second = _run(review_records=records)
    assert second["passed"] is True
    assert first["review_record_set_hash"] == second["review_record_set_hash"]
    assert first["architecture_review_package_hash"] == second["architecture_review_package_hash"]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["findings"].append(copy.deepcopy(d["findings"][0])), "duplicate_finding"),
        (lambda d: d["findings"][0].update({"severity": "critical", "status": "open"}), "critical_finding_unresolved"),
        (lambda d: d["findings"][0].update({"severity": "high", "status": "open"}), "high_finding_unresolved"),
        (lambda d: d["findings"][0].update({"remediation_id": ""}), "remediation_missing"),
        (lambda d: d["findings"][0].update({"affected_component": ""}), "invalid_finding"),
    ],
)
def test_findings_negative_edges(mutate: Any, expected_code: str) -> None:
    findings = _load_json("findings.json")
    mutate(findings)
    result = _run(findings=findings)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_findings_order_does_not_change_hash_and_requests_do_not_approve() -> None:
    first = _run()
    findings = _load_json("findings.json")
    findings["findings"] = list(reversed(findings["findings"]))
    second = _run(findings=findings)
    assert second["passed"] is True
    assert first["findings_set_hash"] == second["findings_set_hash"]
    assert second["risk_acceptance_approved"] is False
    assert second["waiver_approved"] is False


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["records"][0].update({"position": "formal_objection", "resolution_status": "unresolved"}), "formal_objection_unresolved"),
        (lambda d: d["records"][0].pop("signoff_precondition", None), "formal_objection_unresolved"),
    ],
)
def test_dissent_negative_edges(mutate: Any, expected_code: str) -> None:
    dissent = _load_json("dissent_records.json")
    mutate(dissent)
    result = _run(dissent_records=dissent)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_dissent_order_does_not_change_hash_and_cannot_be_hidden_by_majority() -> None:
    first = _run()
    dissent = _load_json("dissent_records.json")
    dissent["records"] = list(reversed(dissent["records"]))
    second = _run(dissent_records=dissent)
    assert second["passed"] is True
    assert first["dissent_set_hash"] == second["dissent_set_hash"]
    assert second["dissent_records"]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["items"].pop(), "remediation_missing"),
        (lambda d: d["items"][0].update({"owner_role": ""}), "remediation_missing"),
        (lambda d: d["items"][0].update({"completion_state": "completed_in_real_deployment"}), "remediation_missing"),
        (lambda d: d["items"][0].update({"blocks_real_integration": False}), "remediation_missing"),
    ],
)
def test_remediation_negative_edges(mutate: Any, expected_code: str) -> None:
    plan = _load_json("remediation_plan.json")
    mutate(plan)
    result = _run(remediation_plan=plan)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_request_changes_with_unfinished_remediation_blocks() -> None:
    records = _load_json("review_records.json")
    records["records"][0]["recommendation"] = "request_changes"
    result = _run(review_records=records)
    assert result["passed"] is False
    assert "review_changes_requested" in _codes(result)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["requests"][0].update({"approval_state": "approved"}), "risk_acceptance_not_approved"),
        (lambda d: d["requests"][0].update({"approval_required_roles": [d["requests"][0]["requested_by_role"]]}), "invalid_risk_acceptance_request"),
        (lambda d: d["requests"][0].pop("requested_expiry", None), "invalid_risk_acceptance_request"),
        (lambda d: d["requests"][0].update({"requested_expiry": "2035-01-01T00:00:00Z"}), "invalid_risk_acceptance_request"),
        (lambda d: d["requests"][0].update({"compensating_controls": []}), "invalid_risk_acceptance_request"),
        (lambda d: d["requests"][0].update({"requested_scope": "real_deployment"}), "invalid_risk_acceptance_request"),
    ],
)
def test_risk_acceptance_request_negative_edges(mutate: Any, expected_code: str) -> None:
    requests_payload = _load_json("risk_acceptance_requests.json")
    mutate(requests_payload)
    result = _run(risk_acceptance_requests=requests_payload)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_critical_finding_cannot_request_risk_acceptance() -> None:
    findings = _load_json("findings.json")
    findings["findings"][1].update({"severity": "critical", "status": "risk_acceptance_requested"})
    result = _run(findings=findings)
    assert result["passed"] is False
    assert "critical_risk_acceptance_not_allowed" in _codes(result)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d["requests"][0].update({"approval_state": "approved"}), "waiver_not_approved"),
        (lambda d: d["requests"][0].pop("requested_expiry", None), "invalid_waiver_request"),
        (lambda d: d["requests"][0].update({"control_id": "identity_verification"}), "non_waivable_control"),
        (lambda d: d["requests"][0].update({"approval_required_roles": [d["requests"][0]["requested_by_role"]]}), "invalid_waiver_request"),
        (lambda d: d["requests"][0].update({"compensating_controls": []}), "invalid_waiver_request"),
    ],
)
def test_waiver_request_negative_edges(mutate: Any, expected_code: str) -> None:
    waivers = _load_json("waiver_requests.json")
    mutate(waivers)
    result = _run(waiver_requests=waivers)
    assert result["passed"] is False
    assert expected_code in _codes(result)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda d: d.update({"approved_decision": "approved"}), "architecture_approval_not_available"),
        (lambda d: d.update({"architecture_decision_approved": True}), "architecture_approval_not_available"),
        (lambda d: d.update({"real_signoff_completed": True}), "architecture_approval_not_available"),
        (lambda d: d.update({"vendor_selection_approved": True}), "architecture_approval_not_available"),
        (lambda d: d.update({"procurement_approved": True}), "architecture_approval_not_available"),
        (lambda d: d.update({"deployment_authorized": True}), "architecture_approval_not_available"),
    ],
)
def test_decision_record_draft_rejects_real_approval_claims(mutate: Any, expected_code: str) -> None:
    decision = _load_json("decision_record_draft.json")
    mutate(decision)
    result = _run(decision_record_draft=decision)
    assert result["passed"] is False
    assert expected_code in _codes(result)


def test_supersede_policy_blocks_changed_or_expired_packages() -> None:
    policy = _load_json("supersede_policy.json")
    assert evaluate_supersede_state(policy, {"stable_baseline": "old"}, {"stable_baseline": "new"}, fixed_now="2030-01-01T00:10:00Z")["state"] == "superseded"
    assert evaluate_supersede_state(policy, {"architecture_package_hash": "a"}, {"architecture_package_hash": "b"}, fixed_now="2030-01-01T00:10:00Z")["state"] == "superseded"
    expired = copy.deepcopy(policy)
    expired["evidence_valid_until"] = "2030-01-01T00:01:00Z"
    result = _run(supersede_policy=expired)
    assert result["passed"] is False
    assert "architecture_review_evidence_expired" in _codes(result)


@pytest.mark.parametrize(
    ("fixture", "component", "expected_code"),
    [
        ("missing_role_negative.json", "review_records", "required_reviewer_role_missing"),
        ("requester_review_negative.json", "review_records", "requester_cannot_review"),
        ("duplicate_reviewer_negative.json", "review_records", "duplicate_reviewer"),
        ("expired_review_negative.json", "review_records", "review_record_expired"),
        ("recommend_block_negative.json", "review_records", "review_block_recommendation_present"),
        ("request_changes_negative.json", "review_records", "review_changes_requested"),
        ("critical_finding_negative.json", "findings", "critical_finding_unresolved"),
        ("high_finding_negative.json", "findings", "high_finding_unresolved"),
        ("missing_remediation_negative.json", "remediation_plan", "remediation_missing"),
        ("formal_objection_negative.json", "dissent_records", "formal_objection_unresolved"),
        ("risk_acceptance_approved_negative.json", "risk_acceptance_requests", "risk_acceptance_not_approved"),
        ("critical_risk_acceptance_negative.json", "findings", "critical_risk_acceptance_not_allowed"),
        ("waiver_approved_negative.json", "waiver_requests", "waiver_not_approved"),
        ("non_waivable_control_negative.json", "waiver_requests", "non_waivable_control"),
        ("architecture_approved_negative.json", "decision_record_draft", "architecture_approval_not_available"),
        ("vendor_selected_negative.json", "decision_record_draft", "architecture_approval_not_available"),
        ("deployment_authorized_negative.json", "decision_record_draft", "architecture_approval_not_available"),
        ("baseline_mismatch_negative.json", "prerequisite_evidence", "stable_baseline_mismatch"),
        ("architecture_package_mismatch_negative.json", "prerequisite_evidence", "architecture_package_mismatch"),
        ("superseded_negative.json", "supersede_policy", "architecture_review_package_superseded"),
    ],
)
def test_negative_fixtures_fail_closed(fixture: str, component: str, expected_code: str) -> None:
    result = _run(**{component: _load_json(fixture)})
    assert result["passed"] is False, fixture
    assert result["decision"] == "blocked"
    assert result["ready_for_architecture_signoff"] is False
    assert expected_code in _codes(result)
    for field in FALSE_FIELDS:
        assert result[field] is False


def test_input_change_changes_package_hash() -> None:
    first = _run()
    findings = _load_json("findings.json")
    findings["findings"][0]["due_condition"] = "before-real-sandbox-approval"
    second = _run(findings=findings)
    assert second["passed"] is True
    assert first["architecture_review_package_hash"] != second["architecture_review_package_hash"]


def test_external_call_isolation_fixture_integrity_and_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_paths = sorted(FIXTURES_ROOT.glob("*.json"))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in fixture_paths}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-G")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-G")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {"openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "requests", "httpx", "urllib", "websocket", "dotenv", "cryptography", "secrets"}
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        if name == "datang_extensions.llm_gateway.provider_adapters.chat_adapter":
            raise AssertionError("R2C-G must not call provider adapter transport")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    result = _run()
    assert result["passed"] is True
    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert subprocess.run(["git", "ls-files", "data/exports"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "architecture_review").exists()


def test_architecture_review_code_has_no_real_clients_or_deploy_logic() -> None:
    package_root = PROJECT_ROOT / "datang_extensions" / "llm_gateway" / "architecture_review"
    assert package_root.exists()
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(package_root.glob("*.py")))
    for snippet in ["import requests", "from requests", "import httpx", "from httpx", "import urllib", "from urllib", "import socket", "os.environ", "getenv", "dotenv", "import openai", "from openai", "import anthropic", "from anthropic", "google_genai", "langchain", "import tushare", "from tushare", "import qlib", "from qlib", "secrets", "urandom", "terraform", "pulumi", "cloudformation", "kubernetes", "docker", "shell=True", "os.system"]:
        assert snippet not in text


def test_cli_success_blocked_schema_and_disallowed_live_args_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    args = [
        sys.executable,
        str(SCRIPT_PATH),
        "--r2c-f-architecture-result",
        str(FIXTURES_ROOT / "r2c_f_architecture_result.json"),
        "--review-charter",
        str(FIXTURES_ROOT / "review_charter.json"),
        "--review-records",
        str(FIXTURES_ROOT / "review_records.json"),
        "--findings",
        str(FIXTURES_ROOT / "findings.json"),
        "--dissent-records",
        str(FIXTURES_ROOT / "dissent_records.json"),
        "--remediation-plan",
        str(FIXTURES_ROOT / "remediation_plan.json"),
        "--risk-acceptance-requests",
        str(FIXTURES_ROOT / "risk_acceptance_requests.json"),
        "--waiver-requests",
        str(FIXTURES_ROOT / "waiver_requests.json"),
        "--decision-record-draft",
        str(FIXTURES_ROOT / "decision_record_draft.json"),
        "--supersede-policy",
        str(FIXTURES_ROOT / "supersede_policy.json"),
        "--prerequisite-evidence",
        str(FIXTURES_ROOT / "prerequisite_evidence.json"),
        "--fixed-now",
        "2030-01-01T00:10:00Z",
        "--output-root",
        str(success_root),
        "--expected-result",
        str(FIXTURES_ROOT / "expected_review_result.json"),
    ]
    success = subprocess.run(args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert success.returncode == 0, success.stderr + success.stdout
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["decision"] == "ready_for_architecture_signoff"
    assert (success_root / "architecture_review_result.json").is_file()

    blocked_records = _load_json("review_records.json")
    blocked_records["records"][0]["recommendation"] = "recommend_block"
    blocked_path = _write_json(tmp_path / "blocked_records.json", blocked_records)
    blocked_args = list(args)
    blocked_args[blocked_args.index(str(FIXTURES_ROOT / "review_records.json"))] = str(blocked_path)
    blocked_args[blocked_args.index(str(success_root))] = str(tmp_path / "blocked")
    blocked_args = blocked_args[:-2]
    blocked = subprocess.run(blocked_args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["decision"] == "blocked"

    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text("[]", encoding="utf-8")
    schema_args = list(args)
    schema_args[schema_args.index(str(FIXTURES_ROOT / "review_charter.json"))] = str(bad_schema)
    schema_args[schema_args.index(str(success_root))] = str(tmp_path / "schema")
    schema_args = schema_args[:-2]
    schema_error = subprocess.run(schema_args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True)
    assert schema_error.returncode == 2
    for forbidden in ["--approve", "--sign", "--accept-risk", "--approve-waiver", "--select-vendor", "--procure", "--deploy", "--apply-network", "--live"]:
        assert subprocess.run([sys.executable, str(SCRIPT_PATH), forbidden], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).returncode == 2
