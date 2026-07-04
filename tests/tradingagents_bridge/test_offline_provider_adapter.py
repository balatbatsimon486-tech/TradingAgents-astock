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
from datang_extensions.llm_gateway.gateway import run_llm_gateway  # noqa: E402
from datang_extensions.llm_gateway.provider_adapters.chat_adapter import (  # noqa: E402
    ChatProviderAdapter,
    build_expected_adapter_result,
    run_provider_adapter,
)
from datang_extensions.llm_gateway.provider_adapters.contracts import (  # noqa: E402
    ProviderAdapterContractError,
    load_provider_adapter_config,
)
from datang_extensions.llm_gateway.provider_adapters.fake_transport import (  # noqa: E402
    FakeProviderTransport,
    load_fake_transport_from_directory,
)
from datang_extensions.prompt_registry.pipeline import run_offline_prompt_research  # noqa: E402

R2C_STAGE = "tradingagents_r2c_offline_provider_adapter"
FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c"
R2B_FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2b"
REQUEST_PATH = FIXTURES_ROOT / "gateway_request.json"
CONFIG_PATH = FIXTURES_ROOT / "provider_config.json"
WIRE_RESPONSES_ROOT = FIXTURES_ROOT / "wire_responses"
EXPECTED_RESULT_PATH = FIXTURES_ROOT / "expected_adapter_result.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_fake_provider_adapter.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _valid_request() -> dict[str, Any]:
    return _load_json(REQUEST_PATH)


def _valid_config() -> dict[str, Any]:
    return _load_json(CONFIG_PATH)


def _success_wire_response() -> dict[str, Any]:
    return _load_json(WIRE_RESPONSES_ROOT / "default.json")


def _transport(*responses: dict[str, Any]) -> FakeProviderTransport:
    return FakeProviderTransport({"default": [copy.deepcopy(response) for response in responses]})


def _run(
    request: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    transport: FakeProviderTransport | None = None,
) -> dict[str, Any]:
    return run_provider_adapter(
        request or _valid_request(),
        provider_config=config or _valid_config(),
        transport=transport or _transport(_success_wire_response()),
    )


def _error_codes(result_or_exc: Any) -> list[str]:
    errors = getattr(result_or_exc, "errors", None)
    if errors is None:
        errors = result_or_exc.get("errors", [])
    return [str(error.get("code", "")) for error in errors]


def _assert_no_key(value: Any, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key).lower() not in forbidden
            _assert_no_key(nested, forbidden)
    elif isinstance(value, list):
        for item in value:
            _assert_no_key(item, forbidden)


def _assert_no_secret_text(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert "synthetic-placeholder-should-be-redacted" not in text
    assert "Bearer " not in text
    assert "Set-Cookie" not in text
    assert "Cookie" not in text
    assert "sk-" not in text


def test_valid_provider_config_loads_with_fake_transport_only() -> None:
    config = load_provider_adapter_config(_valid_config())

    assert config.adapter_contract_version == "1.0"
    assert config.adapter_id == "chat-provider-adapter"
    assert config.adapter_version == "1.0"
    assert config.provider_id == "provider-sandbox"
    assert config.model_id == "provider-model-sandbox-v1"
    assert config.enabled is True
    assert config.live_mode_enabled is False
    assert config.transport_kind == "fake"
    assert config.credential_binding_id == "provider-credential-slot-test"
    assert config.limits.max_attempts == 2


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unknown contract version", lambda data: data.update({"adapter_contract_version": "9.9"}), "unsupported_adapter_contract_version"),
        ("disabled adapter", lambda data: data.update({"enabled": False}), "adapter_disabled"),
        ("missing enabled flag", lambda data: data.pop("enabled"), "adapter_disabled"),
        ("live mode", lambda data: data.update({"live_mode_enabled": True}), "live_mode_not_allowed"),
        ("http transport", lambda data: data.update({"transport_kind": "http"}), "transport_not_allowed"),
        ("sdk transport", lambda data: data.update({"transport_kind": "sdk"}), "transport_not_allowed"),
        ("http scheme", lambda data: data["endpoint_policy"].update({"scheme": "http"}), "endpoint_policy_rejected"),
        ("localhost", lambda data: data["endpoint_policy"].update({"host": "localhost"}), "endpoint_policy_rejected"),
        ("private ip", lambda data: data["endpoint_policy"].update({"host": "10.1.2.3"}), "endpoint_policy_rejected"),
        ("file scheme", lambda data: data["endpoint_policy"].update({"scheme": "file"}), "endpoint_policy_rejected"),
        ("redirects", lambda data: data["endpoint_policy"].update({"allow_redirects": True}), "endpoint_policy_rejected"),
        ("proxy", lambda data: data["endpoint_policy"].update({"allow_proxy": True}), "endpoint_policy_rejected"),
        ("missing credential binding", lambda data: data.pop("credential_binding_id"), "credential_binding_invalid"),
        ("env credential binding", lambda data: data.update({"credential_binding_id": "env:OPENAI_API_KEY"}), "credential_binding_invalid"),
        ("secret credential binding", lambda data: data.update({"credential_binding_id": "sk-synthetic-placeholder"}), "credential_binding_invalid"),
        ("path credential binding", lambda data: data.update({"credential_binding_id": "C:\\secret.txt"}), "credential_binding_invalid"),
        ("too many attempts", lambda data: data["limits"].update({"max_attempts": 9}), "limit_out_of_range"),
        ("zero timeout", lambda data: data["limits"].update({"timeout_ms": 0}), "limit_out_of_range"),
        ("unsafe cost", lambda data: data["limits"].update({"max_cost_usd": "1000000.00"}), "limit_out_of_range"),
    ],
)
def test_provider_config_fails_closed_for_unsafe_values(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    config = _valid_config()
    mutate(config)

    with pytest.raises(ProviderAdapterContractError) as exc_info:
        load_provider_adapter_config(config)

    assert expected_code in _error_codes(exc_info.value), label


def test_wire_request_mapping_hash_and_idempotency_are_deterministic() -> None:
    config = load_provider_adapter_config(_valid_config())
    adapter = ChatProviderAdapter(config, _transport(_success_wire_response()))
    request = _valid_request()

    first = adapter.build_wire_request(request, attempt_number=1)
    second = adapter.build_wire_request(request, attempt_number=1)
    changed = copy.deepcopy(request)
    changed["input_payload"]["user_prompt"] = "Changed synthetic prompt."
    changed_wire = adapter.build_wire_request(changed, attempt_number=1)

    assert first == second
    assert first["method"] == "POST"
    assert first["endpoint"]["scheme"] == "https"
    assert first["endpoint"]["host"] == "provider.invalid"
    assert first["canonical_body"]["model"] == "provider-model-sandbox-v1"
    assert first["canonical_body"]["temperature"] == 0
    assert first["canonical_body"]["max_tokens"] == 512
    assert len(first["wire_request_hash"]) == 64
    assert len(first["idempotency_key"]) == 64
    assert first["wire_request_hash"] != changed_wire["wire_request_hash"]
    assert first["idempotency_key"] != changed_wire["idempotency_key"]
    assert "Authorization" not in json.dumps(first, sort_keys=True)
    assert first["headers"]["content-type"] == "application/json"


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("caller endpoint", lambda data: data.update({"endpoint": "https://provider.invalid"}), "provider_request_rejected"),
        ("caller headers", lambda data: data.update({"headers": {"Authorization": "Bearer synthetic"}}), "provider_request_rejected"),
        ("tools", lambda data: data["input_payload"].update({"tools": []}), "provider_request_rejected"),
        ("functions", lambda data: data["input_payload"].update({"functions": []}), "provider_request_rejected"),
        ("streaming", lambda data: data["parameters"].update({"stream": True}), "unknown_provider_parameter"),
        ("unknown parameter", lambda data: data["parameters"].update({"top_p": 0.5}), "unknown_provider_parameter"),
    ],
)
def test_wire_request_mapping_rejects_caller_controlled_transport_surface(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    request = _valid_request()
    mutate(request)

    result = _run(request=request)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    assert result["wire_request_hash"] == ""
    assert all(value is False for value in result["external_calls"].values())


def test_successful_wire_response_normalizes_to_r2a_provider_response_and_expected_fixture() -> None:
    result = _run()
    expected = _load_json(EXPECTED_RESULT_PATH)

    assert result["stage"] == R2C_STAGE
    assert result["passed"] is True
    assert result["provider_id"] == "provider-sandbox"
    assert result["model_id"] == "provider-model-sandbox-v1"
    assert result["transport_kind"] == "fake"
    assert result["live_mode_enabled"] is False
    assert result["credential_value_resolved"] is False
    assert len(result["wire_request_hash"]) == 64
    assert len(result["idempotency_key"]) == 64
    assert len(result["wire_response_hash"]) == 64
    assert len(result["normalized_response_hash"]) == 64
    assert result["retry_count"] == 0
    assert result["usage"] == {"input_tokens": 14, "output_tokens": 18, "total_tokens": 32}
    assert result["provider_response"]["request_id"] == "r2c-request-001"
    assert result["provider_response"]["content"]["research_only"] is True
    assert result["provider_response"]["content"]["not_a_trading_signal"] is True
    assert result["provider_response"]["content"]["no_trading_decision"] is True
    assert all(value is False for value in result["external_calls"].values())
    assert build_expected_adapter_result(result) == expected
    _assert_no_key(result, {"authorization", "cookie", "set-cookie", "api_key", "target_price", "position_size", "order"})
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, "provider_invalid_request", False),
        (401, "provider_authentication_failed", False),
        (403, "provider_permission_denied", False),
        (404, "provider_not_found", False),
        (408, "provider_retry_exhausted", True),
        (429, "provider_retry_exhausted", True),
        (500, "provider_retry_exhausted", True),
        (502, "provider_retry_exhausted", True),
        (503, "provider_retry_exhausted", True),
        (504, "provider_retry_exhausted", True),
    ],
)
def test_status_errors_are_classified_and_retry_bounded(
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    response = _success_wire_response()
    response["status_code"] = status_code
    response["body"] = {"error": {"message": "synthetic sensitive Bearer value", "code": "synthetic_error"}}

    result = _run(transport=_transport(response))

    assert result["passed"] is False
    assert expected_code in _error_codes(result)
    assert result["retry_count"] == (1 if retryable else 0)
    assert len(result["attempts"]) == (2 if retryable else 1)
    _assert_no_secret_text(result)


def test_retryable_failure_can_succeed_on_second_fixture_without_real_sleep() -> None:
    retry = _success_wire_response()
    retry["status_code"] = 429
    retry["body"] = {"error": {"message": "retry later"}}
    success = _success_wire_response()

    result = _run(transport=_transport(retry, success))

    assert result["passed"] is True
    assert result["retry_count"] == 1
    assert [attempt["status_code"] for attempt in result["attempts"]] == [429, 200]
    assert result["attempts"][0]["planned_delay_ms"] == 0


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("timeout", lambda data: data.update({"timeout": True, "transport_error": "timeout"}), "provider_retry_exhausted"),
        ("malformed json", lambda data: data.update({"body": "{not-json"}), "provider_malformed_json"),
        ("wrong model", lambda data: data["body"].update({"model": "wrong-model"}), "model_identity_mismatch"),
        ("oversized response", lambda data: data.update({"body": "x" * 1048577}), "response_size_exceeded"),
        ("invalid usage", lambda data: data["body"]["usage"].update({"total_tokens": 999}), "usage_validation_failed"),
        ("credential content", lambda data: data["body"]["choices"][0]["message"]["content"].update({"api_key": "synthetic-placeholder"}), "credential_field_detected"),
        ("target price", lambda data: data["body"]["choices"][0]["message"]["content"].update({"target_price": 9.99}), "forbidden_trading_field_detected"),
        ("broker order", lambda data: data["body"]["choices"][0]["message"]["content"].update({"broker": "synthetic", "order": "synthetic"}), "forbidden_trading_field_detected"),
    ],
)
def test_response_normalization_rejects_bad_wire_response_shapes(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    response = _success_wire_response()
    mutate(response)

    result = _run(transport=_transport(response))

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)
    _assert_no_secret_text(result)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("input token budget", lambda data: data["limits"].update({"max_input_tokens": 1}), "token_budget_exceeded"),
        ("output token budget", lambda data: data["limits"].update({"max_output_tokens": 1}), "token_budget_exceeded"),
        ("total token budget", lambda data: data["limits"].update({"max_total_tokens": 2}), "token_budget_exceeded"),
        ("response size budget", lambda data: data["limits"].update({"max_response_bytes": 10}), "response_size_exceeded"),
        ("cost budget", lambda data: data["limits"].update({"max_cost_usd": "0.000001"}), "cost_budget_exceeded"),
        ("attempt budget", lambda data: data["limits"].update({"max_attempts": 0}), "limit_out_of_range"),
    ],
)
def test_budget_limits_fail_closed_before_or_during_adapter_run(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    config = _valid_config()
    mutate(config)
    if expected_code == "limit_out_of_range":
        with pytest.raises(ProviderAdapterContractError) as exc_info:
            load_provider_adapter_config(config)
        assert expected_code in _error_codes(exc_info.value)
        return

    result = _run(config=config)

    assert result["passed"] is False, label
    assert expected_code in _error_codes(result)


def test_fake_transport_does_not_mutate_fixtures_or_use_external_systems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in [REQUEST_PATH, CONFIG_PATH, WIRE_RESPONSES_ROOT / "default.json", EXPECTED_RESULT_PATH]}

    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2C-A")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment credential lookup is not allowed in R2C-A")

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
    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_provider_adapter").exists()
    assert subprocess.run(["git", "ls-files", "data/exports"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""


def test_adapter_implements_r2a_provider_protocol_and_gateway_can_call_it() -> None:
    config = load_provider_adapter_config(_valid_config())
    adapter = ChatProviderAdapter(config, _transport(_success_wire_response()))

    result = run_llm_gateway(_valid_request(), provider=adapter)

    assert result["passed"] is True
    assert result["provider_id"] == "provider-sandbox"
    assert result["model_id"] == "provider-model-sandbox-v1"
    assert result["response"]["provider_metadata"]["adapter_id"] == "chat-provider-adapter"
    assert all(value is False for value in result["external_calls"].values())


def test_r2b_pipeline_can_use_adapter_through_controlled_gateway_injection(tmp_path: Path) -> None:
    config = load_provider_adapter_config(_valid_config())

    def adapter_gateway(r2b_request: dict[str, Any]) -> dict[str, Any]:
        adapted = copy.deepcopy(r2b_request)
        adapted["provider_id"] = "provider-sandbox"
        adapted["model_id"] = "provider-model-sandbox-v1"
        adapted["model_version"] = "1.0"
        return run_llm_gateway(adapted, provider=ChatProviderAdapter(config, _transport(_success_wire_response())))

    result = run_offline_prompt_research(
        R2B_FIXTURES_ROOT / "valid_research_input.json",
        registry_path=R2B_FIXTURES_ROOT / "registry.json",
        registry_root=R2B_FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "r2b-adapter",
        gateway=adapter_gateway,
    )

    assert result["passed"] is True
    assert result["gateway_result"]["provider_id"] == "provider-sandbox"
    assert result["evidence_metrics"]["coverage_ratio"] == 1.0
    assert all(value is False for value in result["external_calls"].values())


def test_cli_success_rejection_and_config_error_exit_codes(tmp_path: Path) -> None:
    success = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(REQUEST_PATH),
            "--provider-config",
            str(CONFIG_PATH),
            "--fixture-map",
            str(WIRE_RESPONSES_ROOT),
            "--output-root",
            str(tmp_path / "success"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["transport_kind"] == "fake"
    assert summary["live_mode_enabled"] is False
    assert summary["credential_value_resolved"] is False
    assert len(summary["wire_request_hash"]) == 64
    assert len(summary["idempotency_key"]) == 64
    assert len(summary["normalized_response_hash"]) == 64
    assert summary["provider_id"] == "provider-sandbox"
    assert summary["model_id"] == "provider-model-sandbox-v1"
    assert all(value is False for value in summary["external_calls"].values())
    assert (tmp_path / "success" / "adapter_result.json").is_file()
    _assert_no_secret_text(summary)

    rejected_response = _success_wire_response()
    rejected_response["status_code"] = 401
    rejected_transport = tmp_path / "rejected_transport"
    _write_json(rejected_transport / "default.json", rejected_response)
    rejected = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(REQUEST_PATH),
            "--provider-config",
            str(CONFIG_PATH),
            "--fixture-map",
            str(rejected_transport),
            "--output-root",
            str(tmp_path / "rejected"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["passed"] is False

    bad_config = _valid_config()
    bad_config["live_mode_enabled"] = True
    bad_config_path = _write_json(tmp_path / "bad_config.json", bad_config)
    config_error = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--request",
            str(REQUEST_PATH),
            "--provider-config",
            str(bad_config_path),
            "--fixture-map",
            str(WIRE_RESPONSES_ROOT),
            "--output-root",
            str(tmp_path / "config_error"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert config_error.returncode == 2
    assert json.loads(config_error.stdout)["passed"] is False
