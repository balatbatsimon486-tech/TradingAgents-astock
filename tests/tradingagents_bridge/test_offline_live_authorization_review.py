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

from datang_extensions.llm_gateway.live_authorization_review.envelope import (  # noqa: E402
    attempt_issue_live_authorization,
    consume_live_authorization_draft,
    mark_draft_superseded_if_mismatch,
    transition_authorization_state,
)
from datang_extensions.llm_gateway.live_authorization_review.gate import (  # noqa: E402
    build_expected_review_result,
    run_offline_live_authorization_review,
)

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c_d"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_live_authorization_review.py"
FIXED_NOW = "2030-01-01T00:10:00Z"
SECRET_TEXT_MARKERS = ["Bearer ", "sk-", "Authorization", "Cookie", "private_key", "signature_value", "secret_value", "TEST-ONLY-SECRET", "person@example.invalid"]
FORBIDDEN_RESULT_FIELDS = {"future_return", "expected_return", "pnl", "profit", "sharpe", "max_drawdown", "win_rate", "position_size", "target_weight", "order_size", "buy", "sell", "hold", "target_price", "auto_trade"}


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _readiness() -> dict[str, Any]:
    return _load_json("readiness_result.json")


def _manifest() -> dict[str, Any]:
    return _load_json("review_manifest.json")


def _records() -> dict[str, Any]:
    return _load_json("reviewer_records.json")


def _freeze() -> dict[str, Any]:
    return _load_json("change_freeze.json")


def _draft() -> dict[str, Any]:
    return _load_json("authorization_draft.json")


def _run(
    readiness: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    records: dict[str, Any] | None = None,
    freeze: dict[str, Any] | None = None,
    draft: dict[str, Any] | None = None,
    fixed_now: str = FIXED_NOW,
) -> dict[str, Any]:
    return run_offline_live_authorization_review(
        readiness or _readiness(),
        manifest or _manifest(),
        records or _records(),
        freeze or _freeze(),
        draft or _draft(),
        fixed_now=fixed_now,
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


def test_valid_review_package_is_ready_for_human_signoff_and_matches_expected_fixture() -> None:
    result = _run()
    expected = _load_json("expected_review_result.json")

    assert result["stage"] == "tradingagents_r2c_d_offline_live_authorization_review"
    assert result["passed"] is True
    assert result["decision"] == "ready_for_human_signoff"
    assert result["review_package_sealed"] is True
    assert result["ready_for_human_signoff"] is True
    assert result["live_authorization_contract_ready"] is True
    assert result["human_review_completed"] is False
    assert result["reviewer_identity_verified"] is False
    assert result["detached_signature_verified"] is False
    assert result["live_authorization_issued"] is False
    assert result["secret_resolution_authorized"] is False
    assert result["network_execution_authorized"] is False
    assert result["live_execution_authorized"] is False
    assert result["credential_value_resolved"] is False
    assert result["provider_transport_called"] is False
    assert result["required_real_world_actions"]
    assert all(value is False for value in result["external_calls"].values())
    for field in ("review_manifest_hash", "review_record_set_hash", "change_freeze_hash", "authorization_draft_hash", "review_package_hash", "audit_hash"):
        assert len(result[field]) == 64
    assert build_expected_review_result(result) == expected
    json.dumps(result, ensure_ascii=False, sort_keys=True)
    _assert_no_forbidden_key(result)
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("baseline mismatch", lambda data: data.update({"stable_baseline": "bad"}), "review_manifest_baseline_mismatch"),
        ("readiness hash mismatch", lambda data: data.update({"readiness_package_hash": "0" * 64}), "review_manifest_readiness_mismatch"),
        ("wildcard role", lambda data: data.update({"required_reviewer_roles": ["research_owner", "*"]}), "review_manifest_role_invalid"),
        ("duplicate role", lambda data: data.update({"required_reviewer_roles": ["research_owner", "research_owner"]}), "review_manifest_role_invalid"),
        ("quorum too low", lambda data: data.update({"required_role_quorum": 2}), "review_manifest_quorum_invalid"),
        ("requester may review", lambda data: data.update({"requester_may_review": True}), "review_manifest_requester_invalid"),
        ("secret material", lambda data: data.update({"credential_value": "TEST-ONLY-SECRET"}), "review_secret_material_detected"),
        ("real identity", lambda data: data.update({"email": "person@example.invalid"}), "review_identity_material_detected"),
    ],
)
def test_review_manifest_fails_closed_for_unsafe_scope_or_identity(label: str, mutate: Any, expected_code: str) -> None:
    manifest = _manifest()
    mutate(manifest)
    result = _run(manifest=manifest)
    assert result["passed"] is False, label
    assert result["decision"] == "blocked"
    assert expected_code in _codes(result)
    assert result["live_authorization_issued"] is False
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("missing role", lambda data: data["records"].pop(), "review_role_coverage_missing"),
        ("requester reviewer", lambda data: data["records"][0].update({"reviewer_id": "synthetic-requester"}), "requester_review_not_allowed"),
        ("duplicate reviewer", lambda data: data["records"][1].update({"reviewer_id": data["records"][0]["reviewer_id"]}), "reviewer_duplicate"),
        ("block wins", lambda data: data["records"][0].update({"recommendation": "recommend_block"}), "reviewer_recommended_block"),
        ("identity verified", lambda data: data["records"][0].update({"identity_verification_status": "verified"}), "real_identity_verification_unavailable"),
        ("signature verified", lambda data: data["records"][0].update({"signature_status": "verified"}), "detached_signature_verification_unavailable"),
        ("expired", lambda data: data["records"][0].update({"valid_until": "2030-01-01T00:09:00Z"}), "review_record_expired"),
        ("naive time", lambda data: data["records"][0].update({"recorded_at": "2030-01-01T00:05:00"}), "review_record_time_invalid"),
        ("forbidden identity", lambda data: data["records"][0].update({"real_name": "Synthetic Person"}), "review_identity_material_detected"),
    ],
)
def test_reviewer_records_only_prove_synthetic_role_coverage(label: str, mutate: Any, expected_code: str) -> None:
    records = _records()
    mutate(records)
    result = _run(records=records)
    assert result["passed"] is False, label
    assert expected_code in _codes(result)
    assert result["human_review_completed"] is False
    assert result["reviewer_identity_verified"] is False
    assert result["detached_signature_verified"] is False


def test_reviewer_record_set_hash_is_order_independent() -> None:
    result = _run()
    records = _records()
    records["records"] = list(reversed(records["records"]))
    reversed_result = _run(records=records)
    assert reversed_result["passed"] is True
    assert result["review_record_set_hash"] == reversed_result["review_record_set_hash"]


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("wrong state", lambda data: data.update({"freeze_state": "open"}), "change_freeze_invalid"),
        ("baseline mismatch", lambda data: data.update({"stable_baseline": "bad"}), "change_freeze_baseline_mismatch"),
        ("readiness mismatch", lambda data: data.update({"readiness_package_hash": "0" * 64}), "change_freeze_readiness_mismatch"),
        ("manifest hash mismatch", lambda data: data.update({"review_manifest_hash": "0" * 64}), "change_freeze_manifest_mismatch"),
        ("missing artifact", lambda data: data.update({"frozen_artifacts": data["frozen_artifacts"][:-1]}), "change_freeze_artifact_missing"),
        ("duplicate artifact", lambda data: data["frozen_artifacts"].append(copy.deepcopy(data["frozen_artifacts"][0])), "change_freeze_artifact_duplicate"),
        ("auto unfreeze", lambda data: data.update({"automatic_unfreeze_allowed": True}), "change_freeze_invalid"),
        ("reuse after change", lambda data: data.update({"changes_require_new_review": False}), "change_freeze_invalid"),
    ],
)
def test_change_freeze_seals_every_relevant_artifact(label: str, mutate: Any, expected_code: str) -> None:
    freeze = _freeze()
    mutate(freeze)
    result = _run(freeze=freeze)
    assert result["passed"] is False, label
    assert expected_code in _codes(result)


def test_change_freeze_hash_is_order_independent() -> None:
    result = _run()
    freeze = _freeze()
    freeze["frozen_artifacts"] = list(reversed(freeze["frozen_artifacts"]))
    reversed_result = _run(freeze=freeze)
    assert reversed_result["passed"] is True
    assert result["change_freeze_hash"] == reversed_result["change_freeze_hash"]


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("issued state", lambda data: data.update({"authorization_state": "issued"}), "live_authorization_issuance_not_available"),
        ("wrong mode", lambda data: data.update({"authorization_mode": "multi_call"}), "authorization_draft_mode_invalid"),
        ("too many calls", lambda data: data.update({"max_calls": 2}), "authorization_budget_exceeded"),
        ("already consumed", lambda data: data.update({"consumed_calls": 1}), "authorization_replay_not_allowed"),
        ("budget exceeded", lambda data: data["budget"].update({"max_output_tokens": 2048}), "authorization_budget_exceeded"),
        ("long window", lambda data: data.update({"proposed_window_end": "2030-01-01T02:00:00Z"}), "authorization_window_invalid"),
        ("expired window", lambda data: data.update({"proposed_window_end": "2030-01-01T00:09:00Z"}), "authorization_window_invalid"),
        ("scope mismatch", lambda data: data.update({"case_id": "other-case"}), "authorization_scope_mismatch"),
        ("nonce present", lambda data: data.update({"execution_nonce_present": True}), "execution_nonce_not_available"),
        ("identity verified", lambda data: data.update({"reviewer_identity_verified": True}), "real_identity_verification_unavailable"),
        ("signature verified", lambda data: data.update({"detached_signature_verified": True}), "detached_signature_verification_unavailable"),
        ("issued", lambda data: data.update({"live_authorization_issued": True}), "live_authorization_issuance_not_available"),
        ("secret resolution", lambda data: data.update({"secret_resolution_authorized": True}), "live_execution_not_authorized"),
        ("network", lambda data: data.update({"network_execution_authorized": True}), "live_execution_not_authorized"),
        ("live", lambda data: data.update({"live_execution_authorized": True}), "live_execution_not_authorized"),
        ("credential", lambda data: data.update({"credential_value_resolved": True}), "live_execution_not_authorized"),
        ("transport", lambda data: data.update({"provider_transport_called": True}), "live_execution_not_authorized"),
    ],
)
def test_authorization_draft_is_non_executable_review_ready_only(label: str, mutate: Any, expected_code: str) -> None:
    draft = _draft()
    mutate(draft)
    result = _run(draft=draft)
    assert result["passed"] is False, label
    assert expected_code in _codes(result)
    assert result["live_authorization_issued"] is False
    assert result["live_execution_authorized"] is False


def test_authorization_id_is_stable_and_not_a_bearer_token() -> None:
    result = _run()
    draft = _draft()
    changed = _draft()
    changed["authorization_id"] = "Bearer TEST-ONLY"
    bad = _run(draft=changed)
    assert result["authorization_id"] == draft["authorization_id"]
    assert len(result["authorization_id"]) == 64
    assert "bearer" not in result["authorization_id"].lower()
    assert bad["passed"] is False
    assert "authorization_id_invalid" in _codes(bad)


def test_state_machine_and_replay_attempts_are_fail_closed() -> None:
    assert transition_authorization_state("draft", "review_ready")["passed"] is True
    issue = transition_authorization_state("review_ready", "issued")
    assert issue["passed"] is False
    assert "live_authorization_issuance_not_available" in _codes(issue)
    consume_transition = transition_authorization_state("issued", "consumed")
    assert consume_transition["passed"] is False
    assert "live_execution_not_authorized" in _codes(consume_transition)

    issued = attempt_issue_live_authorization(_draft())
    consumed = consume_live_authorization_draft(_draft())
    assert issued["passed"] is False
    assert consumed["passed"] is False
    assert "live_authorization_issuance_not_available" in _codes(issued)
    assert "live_execution_not_authorized" in _codes(consumed)


def test_artifact_budget_or_window_change_supersedes_existing_draft() -> None:
    baseline = _draft()
    artifact_changed = copy.deepcopy(baseline)
    artifact_changed["input_artifact_hash"] = "9" * 64
    budget_changed = copy.deepcopy(baseline)
    budget_changed["budget"]["max_cost_usd"] = "0.09"
    window_changed = copy.deepcopy(baseline)
    window_changed["proposed_window_end"] = "2030-01-01T00:44:00Z"
    for changed in (artifact_changed, budget_changed, window_changed):
        result = mark_draft_superseded_if_mismatch(baseline, changed)
        assert result["authorization_state"] == "superseded"
        assert result["passed"] is False


def test_external_call_isolation_fixture_integrity_and_no_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_paths = sorted(FIXTURES_ROOT.glob("*.json"))
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in fixture_paths}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-D")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment lookup is not allowed in R2C-D")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = {"openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "requests", "httpx", "urllib", "websocket", "dotenv"}
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        if name == "datang_extensions.llm_gateway.provider_adapters.chat_adapter":
            raise AssertionError("R2C-D must not call the provider adapter transport layer")
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
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "live_authorization_review").exists()


def test_live_authorization_review_code_has_no_real_network_secret_or_sdk_clients() -> None:
    package_root = PROJECT_ROOT / "datang_extensions" / "llm_gateway" / "live_authorization_review"
    if not package_root.exists():
        pytest.fail("live_authorization_review package must exist")
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(package_root.glob("*.py")))
    forbidden_snippets = ["requests", "httpx", "urllib", "socket", "os.environ", "getenv", "dotenv", "openai", "anthropic", "google_genai", "langchain", "tushare", "qlib", "shell=True", "os.system"]
    for snippet in forbidden_snippets:
        assert snippet not in text


def test_cli_success_blocked_and_schema_error_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    success = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--readiness-result", str(FIXTURES_ROOT / "readiness_result.json"),
         "--review-manifest", str(FIXTURES_ROOT / "review_manifest.json"),
         "--reviewer-records", str(FIXTURES_ROOT / "reviewer_records.json"),
         "--change-freeze", str(FIXTURES_ROOT / "change_freeze.json"),
         "--authorization-draft", str(FIXTURES_ROOT / "authorization_draft.json"),
         "--fixed-now", FIXED_NOW,
         "--output-root", str(success_root),
         "--expected-result", str(FIXTURES_ROOT / "expected_review_result.json")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["decision"] == "ready_for_human_signoff"
    assert summary["review_package_sealed"] is True
    assert summary["ready_for_human_signoff"] is True
    assert summary["live_authorization_contract_ready"] is True
    assert summary["human_review_completed"] is False
    assert summary["reviewer_identity_verified"] is False
    assert summary["detached_signature_verified"] is False
    assert summary["live_authorization_issued"] is False
    assert summary["secret_resolution_authorized"] is False
    assert summary["network_execution_authorized"] is False
    assert summary["live_execution_authorized"] is False
    assert summary["credential_value_resolved"] is False
    assert summary["provider_transport_called"] is False
    assert all(value is False for value in summary["external_calls"].values())
    assert (success_root / "live_authorization_review_result.json").is_file()

    blocked_records = _records()
    blocked_records["records"][0]["recommendation"] = "recommend_block"
    blocked_path = _write_json(tmp_path / "blocked_records.json", blocked_records)
    blocked = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--readiness-result", str(FIXTURES_ROOT / "readiness_result.json"),
         "--review-manifest", str(FIXTURES_ROOT / "review_manifest.json"),
         "--reviewer-records", str(blocked_path),
         "--change-freeze", str(FIXTURES_ROOT / "change_freeze.json"),
         "--authorization-draft", str(FIXTURES_ROOT / "authorization_draft.json"),
         "--fixed-now", FIXED_NOW,
         "--output-root", str(tmp_path / "blocked")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["decision"] == "blocked"

    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text("[]", encoding="utf-8")
    schema_error = subprocess.run(
        [sys.executable, str(SCRIPT_PATH),
         "--readiness-result", str(FIXTURES_ROOT / "readiness_result.json"),
         "--review-manifest", str(FIXTURES_ROOT / "review_manifest.json"),
         "--reviewer-records", str(bad_schema),
         "--change-freeze", str(FIXTURES_ROOT / "change_freeze.json"),
         "--authorization-draft", str(FIXTURES_ROOT / "authorization_draft.json"),
         "--fixed-now", FIXED_NOW,
         "--output-root", str(tmp_path / "schema_error")],
        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
    )
    assert schema_error.returncode == 2
    assert json.loads(schema_error.stdout)["passed"] is False
