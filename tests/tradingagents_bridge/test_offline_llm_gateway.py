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
from datang_extensions.llm_gateway.fake_provider import DeterministicFakeProvider  # noqa: E402
from datang_extensions.llm_gateway.gateway import run_llm_gateway  # noqa: E402

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2a"
VALID_REQUEST_PATH = FIXTURES_ROOT / "valid_request.json"
FAKE_RESPONSE_PATH = FIXTURES_ROOT / "fake_response.json"
CREDENTIAL_REQUEST_PATH = FIXTURES_ROOT / "credential_request.json"
INVALID_PROVIDER_REQUEST_PATH = FIXTURES_ROOT / "invalid_provider_request.json"
FORBIDDEN_TRADING_RESPONSE_PATH = FIXTURES_ROOT / "forbidden_trading_response.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_fake_llm_gateway.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_request() -> dict[str, Any]:
    return _load_json(VALID_REQUEST_PATH)


def _fake_response() -> dict[str, Any]:
    return _load_json(FAKE_RESPONSE_PATH)


def _error_codes(result: dict[str, Any]) -> list[str]:
    return [str(error.get("code", "")) for error in result.get("errors", [])]


def _run(request: dict[str, Any], provider: Any | None = None) -> dict[str, Any]:
    return run_llm_gateway(request, provider=provider)


class StaticProvider:
    provider_id = "fake"

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(self.response)


class MismatchedProvider:
    provider_id = "wrong-provider"

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        return _fake_response()


def test_valid_request_runs_gateway_and_returns_auditable_result() -> None:
    request = _valid_request()

    result = _run(request)

    assert result["stage"] == "tradingagents_r2a_offline_llm_gateway"
    assert result["gateway_contract_version"] == "1.0"
    assert result["passed"] is True
    assert result["request_id"] == request["request_id"]
    assert result["provider_id"] == "fake"
    assert result["model_id"] == "fake-deterministic-v1"
    assert result["model_version"] == "1.0"
    assert result["prompt_id"] == request["prompt_id"]
    assert result["prompt_version"] == request["prompt_version"]
    assert result["snapshot_id"] == request["snapshot_id"]
    assert result["input_artifact_id"] == request["input_artifact_id"]
    assert result["input_artifact_hash"] == request["input_artifact_hash"]
    assert len(result["request_hash"]) == 64
    assert len(result["response_hash"]) == 64
    assert len(result["normalized_response_hash"]) == 64
    assert result["usage"]["total_tokens"] == result["usage"]["input_tokens"] + result["usage"]["output_tokens"]
    assert result["cost"] == {"currency": "USD", "amount": 0}
    assert result["latency"] == {"duration_ms": 0}
    assert result["retry_count"] == 0
    assert result["finish_reason"] == "stop"
    assert all(value is False for value in result["external_calls"].values())
    assert result["response"]["content"]["research_only"] is True
    assert result["response"]["content"]["not_a_trading_signal"] is True
    assert result["response"]["content"]["no_trading_decision"] is True
    assert result["audit"]["request_hash"] == result["request_hash"]
    assert result["audit"]["response_hash"] == result["response_hash"]
    assert result["audit"]["error_codes"] == []
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("missing request id", lambda data: data.pop("request_id"), "invalid_gateway_request"),
        ("unsafe request id", lambda data: data.update({"request_id": "../bad"}), "invalid_gateway_request"),
        ("unsafe case id", lambda data: data.update({"case_id": "case/subdir"}), "invalid_gateway_request"),
        ("unsupported gateway version", lambda data: data.update({"gateway_contract_version": "9.9"}), "unsupported_gateway_contract_version"),
        ("unsupported request version", lambda data: data.update({"request_schema_version": "9.9"}), "unsupported_request_schema_version"),
        ("provider not allowed", lambda data: data.update({"provider_id": "openai"}), "provider_not_allowed"),
        ("model not allowed", lambda data: data.update({"model_id": "real-model"}), "model_not_allowed"),
        ("bad artifact hash", lambda data: data.update({"input_artifact_hash": "not-a-sha"}), "invalid_input_artifact_hash"),
        ("temperature not deterministic", lambda data: data["parameters"].update({"temperature": 0.1}), "invalid_model_parameters"),
        ("max tokens too small", lambda data: data["parameters"].update({"max_output_tokens": 0}), "invalid_model_parameters"),
        ("max tokens too large", lambda data: data["parameters"].update({"max_output_tokens": 100000}), "invalid_model_parameters"),
        ("network allowed", lambda data: data["policy"].update({"allow_network": True}), "invalid_gateway_request"),
        ("tools allowed", lambda data: data["policy"].update({"allow_tools": True}), "invalid_gateway_request"),
        ("market data allowed", lambda data: data["policy"].update({"allow_market_data": True}), "invalid_gateway_request"),
        ("trading allowed", lambda data: data["policy"].update({"allow_trading_actions": True}), "invalid_gateway_request"),
        ("research only false", lambda data: data["policy"].update({"research_only": False}), "invalid_gateway_request"),
        ("credential in payload", lambda data: data["input_payload"].update({"api_key": "synthetic-test-placeholder"}), "credential_field_detected"),
        ("trading field in payload", lambda data: data["input_payload"].update({"order_size": 100}), "forbidden_trading_field_detected"),
    ],
)
def test_request_contract_fails_closed_for_invalid_inputs(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    request = _valid_request()
    mutate(request)

    result = _run(request)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["response"] == {}
    assert all(value is False for value in result["external_calls"].values())


def test_fixture_requests_cover_provider_and_credential_rejections() -> None:
    invalid_provider = _load_json(INVALID_PROVIDER_REQUEST_PATH)
    credential = _load_json(CREDENTIAL_REQUEST_PATH)

    provider_result = _run(invalid_provider)
    credential_result = _run(credential)

    assert provider_result["passed"] is False
    assert "provider_not_allowed" in _error_codes(provider_result)
    assert credential_result["passed"] is False
    assert "credential_field_detected" in _error_codes(credential_result)


def test_provider_identity_mismatch_fails_before_response_is_trusted() -> None:
    result = _run(_valid_request(), provider=MismatchedProvider())

    assert result["passed"] is False
    assert "provider_identity_mismatch" in _error_codes(result)
    assert result["response"] == {}


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unsupported response version", lambda data: data.update({"response_schema_version": "9.9"}), "unsupported_response_schema_version"),
        ("request id mismatch", lambda data: data.update({"request_id": "other-request"}), "request_id_mismatch"),
        ("provider mismatch", lambda data: data.update({"provider_id": "wrong"}), "provider_identity_mismatch"),
        ("model mismatch", lambda data: data.update({"model_id": "wrong-model"}), "model_identity_mismatch"),
        ("negative usage", lambda data: data["usage"].update({"input_tokens": -1, "total_tokens": 17}), "usage_validation_failed"),
        ("bad usage total", lambda data: data["usage"].update({"total_tokens": 999}), "usage_validation_failed"),
        ("unknown finish reason", lambda data: data.update({"finish_reason": "mystery"}), "provider_response_invalid"),
        ("credential in content", lambda data: data["content"].update({"secret": "synthetic-test-placeholder"}), "credential_field_detected"),
        ("trading field in content", lambda data: data["content"].update({"position_size": 1}), "forbidden_trading_field_detected"),
        ("missing research flag", lambda data: data["content"].pop("not_a_trading_signal"), "provider_response_invalid"),
        ("credential metadata", lambda data: data["provider_metadata"].update({"authorization": "synthetic-test-placeholder"}), "credential_field_detected"),
    ],
)
def test_response_contract_fails_closed_for_invalid_provider_outputs(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    response = _fake_response()
    mutate(response)

    result = _run(_valid_request(), provider=StaticProvider(response))

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)


def test_forbidden_trading_response_fixture_is_rejected() -> None:
    response = _load_json(FORBIDDEN_TRADING_RESPONSE_PATH)

    result = _run(_valid_request(), provider=StaticProvider(response))

    assert result["passed"] is False
    assert "forbidden_trading_field_detected" in _error_codes(result)


def test_fake_provider_is_deterministic_and_hashes_are_sensitive_to_inputs() -> None:
    request = _valid_request()
    changed = _valid_request()
    changed["input_payload"]["research_context"] = "Different synthetic input."

    first = _run(request)
    second = _run(request)
    changed_result = _run(changed)

    assert first == second
    assert first["request_hash"] == second["request_hash"]
    assert first["response_hash"] == second["response_hash"]
    assert first["normalized_response_hash"] == second["normalized_response_hash"]
    assert first["response"] == second["response"]
    assert first["request_hash"] != changed_result["request_hash"]
    assert first["response_hash"] != changed_result["response_hash"]
    assert stable_json_hash(request) == first["request_hash"]


def test_fake_provider_does_not_use_network_environment_or_real_model_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _valid_request()

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2A")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment credential lookup is not allowed in R2A")

    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        forbidden = (
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
        )
        if name.split(".")[0] in forbidden:
            raise AssertionError(f"external dependency import is not allowed: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(os, "getenv", fail_getenv)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = _run(request, provider=DeterministicFakeProvider())

    assert result["passed"] is True
    assert all(value is False for value in result["external_calls"].values())


def test_provider_exception_and_controlled_invalid_response_are_structured_failures() -> None:
    exception_request = _valid_request()
    exception_request["input_payload"]["fake_provider_mode"] = "raise"
    invalid_response_request = _valid_request()
    invalid_response_request["input_payload"]["fake_provider_mode"] = "invalid_response"

    exception_result = _run(exception_request)
    invalid_response_result = _run(invalid_response_request)

    assert exception_result["passed"] is False
    assert "provider_execution_failed" in _error_codes(exception_result)
    assert invalid_response_result["passed"] is False
    assert "provider_response_invalid" in _error_codes(invalid_response_result)


def test_audit_record_lineage_prompt_identity_and_external_call_flags_are_complete() -> None:
    request = _valid_request()

    result = _run(request)
    audit = result["audit"]

    assert audit["request_id"] == request["request_id"]
    assert audit["request_hash"] == result["request_hash"]
    assert audit["response_hash"] == result["response_hash"]
    assert audit["normalized_response_hash"] == result["normalized_response_hash"]
    assert audit["provider_id"] == request["provider_id"]
    assert audit["model_id"] == request["model_id"]
    assert audit["model_version"] == request["model_version"]
    assert audit["prompt_id"] == request["prompt_id"]
    assert audit["prompt_version"] == request["prompt_version"]
    assert audit["snapshot_id"] == request["snapshot_id"]
    assert audit["input_artifact_id"] == request["input_artifact_id"]
    assert audit["input_artifact_hash"] == request["input_artifact_hash"]
    assert audit["usage"] == result["usage"]
    assert audit["cost"] == result["cost"]
    assert audit["retry_count"] == 0
    assert audit["finish_reason"] == "stop"
    assert audit["passed"] is True
    assert audit["error_codes"] == []
    assert all(value is False for value in audit["external_calls"].values())


def test_gateway_does_not_modify_request_fixture_or_write_repo_outputs(tmp_path: Path) -> None:
    before_content = VALID_REQUEST_PATH.read_bytes()
    before_mtime = VALID_REQUEST_PATH.stat().st_mtime_ns

    result = _run(_valid_request())

    assert result["passed"] is True
    assert VALID_REQUEST_PATH.read_bytes() == before_content
    assert VALID_REQUEST_PATH.stat().st_mtime_ns == before_mtime
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_llm_gateway").exists()
    assert subprocess.run(
        ["git", "ls-files", "data/exports"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip() == ""


def test_cli_success_rejection_and_argument_error_exit_codes(tmp_path: Path) -> None:
    success_root = tmp_path / "success"
    success = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(VALID_REQUEST_PATH),
            "--output-root",
            str(success_root),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    success_summary = json.loads(success.stdout)
    assert success_summary["passed"] is True
    assert success_summary["provider_id"] == "fake"
    assert success_summary["cost"]["amount"] == 0
    assert all(value is False for value in success_summary["external_calls"].values())
    assert len(success_summary["request_hash"]) == 64
    assert len(success_summary["response_hash"]) == 64
    assert (success_root / "gateway_result.json").is_file()

    rejection = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(CREDENTIAL_REQUEST_PATH),
            "--output-root",
            str(tmp_path / "rejection"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejection.returncode == 1
    assert "synthetic-test-placeholder-not-a-real-key" not in rejection.stdout
    assert json.loads(rejection.stdout)["passed"] is False

    argument_error = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(VALID_REQUEST_PATH),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert argument_error.returncode == 2
