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
from datang_extensions.prompt_registry.pipeline import (  # noqa: E402
    build_expected_result,
    run_offline_prompt_research,
)
from datang_extensions.prompt_registry.registry import (  # noqa: E402
    PromptRegistryError,
    load_prompt_registry,
)
from datang_extensions.prompt_registry.renderer import (  # noqa: E402
    PromptRenderError,
    render_prompt,
)
from datang_extensions.prompt_registry.research_output import (  # noqa: E402
    ResearchContractError,
    validate_research_input,
    validate_research_output,
)

FIXTURES_ROOT = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2b"
REGISTRY_PATH = FIXTURES_ROOT / "registry.json"
VALID_INPUT_PATH = FIXTURES_ROOT / "valid_research_input.json"
EXPECTED_RESULT_PATH = FIXTURES_ROOT / "expected_result.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "datang_extensions" / "run_offline_prompt_research.py"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _copy_fixture_tree(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for source in FIXTURES_ROOT.rglob("*"):
        relative = source.relative_to(FIXTURES_ROOT)
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return destination


def _error_codes(exc: Exception) -> list[str]:
    return [str(error.get("code", "")) for error in getattr(exc, "errors", [])]


def _valid_output(evidence_ids: list[str] | None = None) -> dict[str, Any]:
    refs = evidence_ids or ["evidence-001", "evidence-002"]
    return {
        "output_schema_id": "institutional-research-output",
        "output_schema_version": "1.0",
        "summary": "Synthetic structured R2B output.",
        "facts": [{"claim": "Synthetic fact.", "evidence_refs": [refs[0]]}],
        "bull_case": [{"claim": "Synthetic bull claim.", "evidence_refs": [refs[0]]}],
        "bear_case": [{"claim": "Synthetic bear claim.", "evidence_refs": [refs[-1]]}],
        "key_risks": [{"claim": "Synthetic risk claim.", "evidence_refs": [refs[-1]]}],
        "uncertainties": ["Synthetic uncertainty."],
        "research_stance": "neutral",
        "confidence": "low",
        "research_only": True,
        "not_a_trading_signal": True,
        "no_trading_decision": True,
    }


def test_registry_loads_valid_prompt_and_prompt_hash_is_portable(tmp_path: Path) -> None:
    registry = load_prompt_registry(REGISTRY_PATH, registry_root=FIXTURES_ROOT)
    prompt = registry.get_prompt("institutional-research-brief", "1.0.0")
    copied_root = _copy_fixture_tree(tmp_path / "copied")
    copied = load_prompt_registry(copied_root / "registry.json", registry_root=copied_root)
    copied_prompt = copied.get_prompt("institutional-research-brief", "1.0.0")

    assert registry.registry_id == "datang-tradingagents-prompts"
    assert registry.registry_version == "1.0"
    assert prompt.prompt_id == "institutional-research-brief"
    assert prompt.prompt_version == "1.0.0"
    assert prompt.status == "approved"
    assert len(prompt.prompt_spec_hash) == 64
    assert prompt.prompt_spec_hash == copied_prompt.prompt_spec_hash
    assert str(FIXTURES_ROOT) not in stable_json_hash(prompt.prompt_spec)


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("unsupported registry version", lambda data: data.update({"registry_version": "9.9"}), "unsupported_prompt_registry_version"),
        ("duplicate prompt version", lambda data: data["prompts"].append(copy.deepcopy(data["prompts"][0])), "duplicate_prompt_version"),
        ("invalid prompt id", lambda data: data["prompts"][0].update({"prompt_id": "../bad"}), "invalid_prompt_id"),
        ("missing prompt version", lambda data: data["prompts"][0].pop("prompt_version"), "invalid_prompt_version"),
        ("unknown status", lambda data: data["prompts"][0].update({"status": "mystery"}), "invalid_prompt_registry"),
        ("draft status", lambda data: data["prompts"][0].update({"status": "draft"}), "prompt_not_approved"),
        ("absolute template", lambda data: data["prompts"][0].update({"system_template": str((FIXTURES_ROOT / "templates" / "system.txt").resolve())}), "unsafe_template_path"),
        ("parent traversal template", lambda data: data["prompts"][0].update({"system_template": "../outside.txt"}), "unsafe_template_path"),
        ("missing template", lambda data: data["prompts"][0].update({"system_template": "templates/missing.txt"}), "template_not_found"),
        ("template directory", lambda data: data["prompts"][0].update({"system_template": "templates"}), "template_not_file"),
    ],
)
def test_registry_fails_closed_for_invalid_registry_entries(
    tmp_path: Path,
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    root = _copy_fixture_tree(tmp_path / label.replace(" ", "_"))
    registry_payload = _load_json(root / "registry.json")
    mutate(registry_payload)
    _write_json(root / "registry.json", registry_payload)

    with pytest.raises(PromptRegistryError) as exc_info:
        load_prompt_registry(root / "registry.json", registry_root=root)

    assert expected_code in _error_codes(exc_info.value), label


def test_registry_rejects_latest_and_missing_exact_version() -> None:
    registry = load_prompt_registry(REGISTRY_PATH, registry_root=FIXTURES_ROOT)

    with pytest.raises(PromptRegistryError) as latest:
        registry.get_prompt("institutional-research-brief", "latest")
    with pytest.raises(PromptRegistryError) as missing:
        registry.get_prompt("institutional-research-brief", "2.0.0")

    assert "invalid_prompt_version" in _error_codes(latest.value)
    assert "prompt_not_found" in _error_codes(missing.value)


def test_registry_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path / "root")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_template = outside / "outside.txt"
    outside_template.write_text("escaped", encoding="utf-8")
    link = root / "templates" / "linked.txt"
    try:
        link.symlink_to(outside_template)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")
    registry_payload = _load_json(root / "registry.json")
    registry_payload["prompts"][0]["system_template"] = "templates/linked.txt"
    _write_json(root / "registry.json", registry_payload)

    with pytest.raises(PromptRegistryError) as exc_info:
        load_prompt_registry(root / "registry.json", registry_root=root)

    assert "unsafe_template_path" in _error_codes(exc_info.value)


def test_renderer_is_deterministic_and_hash_sensitive() -> None:
    registry = load_prompt_registry(REGISTRY_PATH, registry_root=FIXTURES_ROOT)
    prompt = registry.get_prompt("institutional-research-brief", "1.0.0")
    research_input = validate_research_input(_load_json(VALID_INPUT_PATH))
    variables = {
        "case_id": research_input["case_id"],
        "snapshot_id": research_input["snapshot_id"],
        "research_context_json": research_input["research_context_json"],
    }

    first = render_prompt(prompt, variables)
    second = render_prompt(prompt, variables)
    changed = render_prompt(prompt, {**variables, "case_id": "r2b-valid-002"})

    assert first == second
    assert first["prompt_id"] == "institutional-research-brief"
    assert first["prompt_version"] == "1.0.0"
    assert len(first["prompt_spec_hash"]) == 64
    assert len(first["system_prompt_hash"]) == 64
    assert len(first["user_prompt_hash"]) == 64
    assert len(first["rendered_prompt_hash"]) == 64
    assert len(first["variables_hash"]) == 64
    assert first["variables_hash"] != changed["variables_hash"]
    assert first["rendered_prompt_hash"] != changed["rendered_prompt_hash"]


@pytest.mark.parametrize(
    ("label", "template_text", "variables", "expected_code"),
    [
        ("missing variable", "case={case_id} snapshot={snapshot_id}", {"case_id": "case"}, "missing_prompt_variable"),
        ("unexpected variable", "case={case_id}", {"case_id": "case", "extra": "x"}, "unexpected_prompt_variable"),
        ("attribute expression", "case={case_id.upper}", {"case_id": "case"}, "invalid_template_variable"),
        ("format spec expression", "case={case_id:>10}", {"case_id": "case"}, "invalid_template_variable"),
    ],
)
def test_renderer_fails_closed_for_variable_errors(
    tmp_path: Path,
    label: str,
    template_text: str,
    variables: dict[str, str],
    expected_code: str,
) -> None:
    root = _copy_fixture_tree(tmp_path / label.replace(" ", "_"))
    (root / "templates" / "user.txt").write_text(template_text, encoding="utf-8")
    registry = load_prompt_registry(root / "registry.json", registry_root=root)
    prompt = registry.get_prompt("institutional-research-brief", "1.0.0")

    with pytest.raises(PromptRenderError) as exc_info:
        render_prompt(prompt, variables)

    assert expected_code in _error_codes(exc_info.value)


def test_prompt_hash_changes_when_template_content_changes(tmp_path: Path) -> None:
    root = _copy_fixture_tree(tmp_path / "changed_template")
    original = load_prompt_registry(root / "registry.json", registry_root=root).get_prompt("institutional-research-brief", "1.0.0")
    (root / "templates" / "system.txt").write_text(
        (root / "templates" / "system.txt").read_text(encoding="utf-8") + "\nAdditional deterministic instruction.\n",
        encoding="utf-8",
    )
    changed = load_prompt_registry(root / "registry.json", registry_root=root).get_prompt("institutional-research-brief", "1.0.0")

    assert original.prompt_spec_hash != changed.prompt_spec_hash


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("duplicate evidence", lambda data: data["research_context"]["evidence"].append(copy.deepcopy(data["research_context"]["evidence"][0])), "duplicate_evidence_id"),
        ("missing evidence text", lambda data: data["research_context"]["evidence"][0].pop("text"), "invalid_evidence"),
        ("credential evidence field", lambda data: data["research_context"]["evidence"][0].update({"api_key": "synthetic-placeholder"}), "credential_field_detected"),
        ("trading evidence field", lambda data: data["research_context"]["evidence"][0].update({"order_size": 1}), "forbidden_trading_field_detected"),
        ("bad artifact hash", lambda data: data.update({"input_artifact_hash": "bad"}), "invalid_research_input"),
    ],
)
def test_research_input_validation_rejects_bad_evidence(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    payload = _load_json(VALID_INPUT_PATH)
    mutate(payload)

    with pytest.raises(ResearchContractError) as exc_info:
        validate_research_input(payload)

    assert expected_code in _error_codes(exc_info.value), label


@pytest.mark.parametrize(
    ("label", "mutate", "expected_code"),
    [
        ("schema version", lambda data: data.update({"output_schema_version": "9.9"}), "unsupported_research_output_schema"),
        ("buy stance", lambda data: data.update({"research_stance": "BUY"}), "invalid_research_output"),
        ("bad confidence", lambda data: data.update({"confidence": "certain"}), "invalid_research_output"),
        ("missing research flag", lambda data: data.pop("research_only"), "research_policy_violation"),
        ("uncited fact", lambda data: data["facts"][0].update({"evidence_refs": []}), "uncited_research_claim"),
        ("unknown ref", lambda data: data["bull_case"][0].update({"evidence_refs": ["unknown-evidence"]}), "unknown_evidence_reference"),
        ("credential field", lambda data: data.update({"authorization": "synthetic-placeholder"}), "credential_field_detected"),
        ("trading field", lambda data: data.update({"position_size": 1}), "forbidden_trading_field_detected"),
        ("target price", lambda data: data["key_risks"][0].update({"target_price": 9.99}), "forbidden_trading_field_detected"),
    ],
)
def test_research_output_validation_rejects_contract_violations(
    label: str,
    mutate: Any,
    expected_code: str,
) -> None:
    research_input = validate_research_input(_load_json(VALID_INPUT_PATH))
    output = _valid_output(research_input["evidence_ids"])
    mutate(output)

    with pytest.raises(ResearchContractError) as exc_info:
        validate_research_output(output, allowed_evidence_ids=research_input["evidence_ids"])

    assert expected_code in _error_codes(exc_info.value), label


def test_valid_research_output_returns_coverage_metrics() -> None:
    research_input = validate_research_input(_load_json(VALID_INPUT_PATH))
    output = _valid_output(research_input["evidence_ids"])

    validated = validate_research_output(output, allowed_evidence_ids=research_input["evidence_ids"])

    assert validated["metrics"] == {"total_claims": 4, "cited_claims": 4, "coverage_ratio": 1.0}
    assert validated["output"]["research_only"] is True
    assert validated["output"]["not_a_trading_signal"] is True
    assert validated["output"]["no_trading_decision"] is True


def test_r2b_pipeline_runs_fake_gateway_and_matches_expected_result(tmp_path: Path) -> None:
    result = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "out",
    )
    expected = _load_json(EXPECTED_RESULT_PATH)

    assert result["passed"] is True
    assert result["stage"] == "tradingagents_r2b_offline_prompt_research"
    assert result["prompt_id"] == "institutional-research-brief"
    assert result["prompt_version"] == "1.0.0"
    assert result["gateway_result"]["passed"] is True
    assert result["gateway_result"]["provider_id"] == "fake"
    assert result["evidence_metrics"]["coverage_ratio"] == 1.0
    assert all(value is False for value in result["external_calls"].values())
    assert build_expected_result(result) == expected
    assert (tmp_path / "out" / "r2b_result.json").is_file()


def test_pipeline_is_deterministic_and_hash_sensitive(tmp_path: Path) -> None:
    first = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "first",
    )
    second = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "second",
    )
    changed_input = _load_json(VALID_INPUT_PATH)
    changed_input["research_context"]["notes"].append("Different synthetic note.")
    changed_input_path = _write_json(tmp_path / "changed_input.json", changed_input)
    changed = run_offline_prompt_research(
        changed_input_path,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "changed",
    )

    assert build_expected_result(first) == build_expected_result(second)
    assert first["result_hash"] == second["result_hash"]
    assert first["result_hash"] != changed["result_hash"]
    assert first["rendered_prompt_hash"] != changed["rendered_prompt_hash"]


def test_pipeline_reuses_r2a_gateway_and_structures_gateway_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datang_extensions.prompt_registry import pipeline as pipeline_module

    calls: list[dict[str, Any]] = []
    real_gateway = pipeline_module.run_llm_gateway

    def tracking_gateway(request: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(copy.deepcopy(request))
        return real_gateway(request, **kwargs)

    monkeypatch.setattr(pipeline_module, "run_llm_gateway", tracking_gateway)
    success = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "success",
    )
    failure_input = _load_json(VALID_INPUT_PATH)
    failure_input["fake_provider_mode"] = "raise"
    failure_path = _write_json(tmp_path / "failure_input.json", failure_input)
    failure = run_offline_prompt_research(
        failure_path,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "failure",
    )

    assert success["passed"] is True
    assert len(calls) == 2
    assert calls[0]["prompt_id"] == "institutional-research-brief"
    assert calls[0]["prompt_version"] == "1.0.0"
    assert failure["passed"] is False
    assert any(error["code"] == "gateway_execution_failed" for error in failure["errors"])
    assert all(value is False for value in failure["external_calls"].values())


def test_prompt_injection_text_remains_data_and_external_calls_stay_false(tmp_path: Path) -> None:
    result = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "out",
    )
    output_text = json.dumps(result["research_output"], ensure_ascii=False, sort_keys=True)

    assert result["passed"] is True
    assert "target_weight" not in output_text
    assert result["gateway_request"]["policy"]["allow_network"] is False
    assert result["output_schema_id"] == "institutional-research-output"
    assert all(value is False for value in result["external_calls"].values())


def test_pipeline_does_not_use_network_environment_or_real_model_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_socket(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in R2B")

    def fail_getenv(*args: object, **kwargs: object) -> object:
        raise AssertionError("environment credential lookup is not allowed in R2B")

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

    result = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "out",
    )

    assert result["passed"] is True
    assert all(value is False for value in result["external_calls"].values())


def test_pipeline_and_cli_do_not_mutate_fixtures_or_write_repo_outputs(tmp_path: Path) -> None:
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in [REGISTRY_PATH, VALID_INPUT_PATH, EXPECTED_RESULT_PATH, FIXTURES_ROOT / "templates" / "system.txt", FIXTURES_ROOT / "templates" / "user.txt"]
    }

    result = run_offline_prompt_research(
        VALID_INPUT_PATH,
        registry_path=REGISTRY_PATH,
        registry_root=FIXTURES_ROOT,
        prompt_id="institutional-research-brief",
        prompt_version="1.0.0",
        output_root=tmp_path / "out",
    )

    assert result["passed"] is True
    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime
    assert not (PROJECT_ROOT / "reports" / "tradingagents_astock" / "offline_prompt_registry").exists()
    assert subprocess.run(["git", "ls-files", "data/exports"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""
    assert subprocess.run(["git", "diff", "--", "tradingagents", "cli", "web"], cwd=PROJECT_ROOT, check=False, capture_output=True, text=True).stdout.strip() == ""


def test_cli_success_rejection_and_argument_error_exit_codes(tmp_path: Path) -> None:
    success = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(VALID_INPUT_PATH),
            "--registry",
            str(REGISTRY_PATH),
            "--registry-root",
            str(FIXTURES_ROOT),
            "--prompt-id",
            "institutional-research-brief",
            "--prompt-version",
            "1.0.0",
            "--output-root",
            str(tmp_path / "success"),
            "--expected-result",
            str(EXPECTED_RESULT_PATH),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    summary = json.loads(success.stdout)
    assert summary["passed"] is True
    assert summary["prompt_id"] == "institutional-research-brief"
    assert summary["prompt_version"] == "1.0.0"
    assert summary["provider_id"] == "fake"
    assert summary["evidence_metrics"]["coverage_ratio"] == 1.0
    assert all(value is False for value in summary["external_calls"].values())
    assert "target_weight" not in success.stdout

    rejected_input = _load_json(VALID_INPUT_PATH)
    rejected_input["research_context"]["evidence"].append(copy.deepcopy(rejected_input["research_context"]["evidence"][0]))
    rejected_path = _write_json(tmp_path / "rejected.json", rejected_input)
    rejected = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(rejected_path),
            "--registry",
            str(REGISTRY_PATH),
            "--registry-root",
            str(FIXTURES_ROOT),
            "--prompt-id",
            "institutional-research-brief",
            "--prompt-version",
            "1.0.0",
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

    argument_error = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input",
            str(VALID_INPUT_PATH),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert argument_error.returncode == 2
