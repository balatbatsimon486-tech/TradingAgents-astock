"""R2B offline prompt registry to R2A fake gateway pipeline."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from datang_extensions.llm_gateway.contracts import GATEWAY_CONTRACT_VERSION, REQUEST_SCHEMA_VERSION, stable_json_hash
from datang_extensions.llm_gateway.fake_provider import DeterministicFakeProvider
from datang_extensions.llm_gateway.gateway import run_llm_gateway
from datang_extensions.prompt_registry.contracts import (
    R2B_STAGE,
    R2BContractError,
    external_calls_from,
    r2b_error,
)
from datang_extensions.prompt_registry.registry import PromptRegistryError, load_prompt_registry
from datang_extensions.prompt_registry.renderer import PromptRenderError, render_prompt
from datang_extensions.prompt_registry.research_output import (
    ResearchContractError,
    structured_output_from_gateway_content,
    validate_research_input,
    validate_research_output,
)
from datang_extensions.utils.safe_io import write_json_file

GatewayRunner = Callable[[Mapping[str, Any]], dict[str, Any]]


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def public_gateway_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return an audit-safe request view without rendered prompt text."""

    public = copy.deepcopy(dict(request))
    payload = public.get("input_payload")
    if isinstance(payload, dict):
        payload.pop("system_prompt", None)
        payload.pop("user_prompt", None)
    return public


def _base_failure(errors: list[dict[str, str]], *, output_root: str | Path | None = None, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context_map = context or {}
    result = {
        "stage": R2B_STAGE,
        "registry_version": str(context_map.get("registry_version", "")),
        "passed": False,
        "case_id": str(context_map.get("case_id", "")),
        "snapshot_id": str(context_map.get("snapshot_id", "")),
        "input_artifact_id": str(context_map.get("input_artifact_id", "")),
        "input_artifact_hash": str(context_map.get("input_artifact_hash", "")),
        "prompt_id": str(context_map.get("prompt_id", "")),
        "prompt_version": str(context_map.get("prompt_version", "")),
        "prompt_spec_hash": str(context_map.get("prompt_spec_hash", "")),
        "system_prompt_hash": str(context_map.get("system_prompt_hash", "")),
        "user_prompt_hash": str(context_map.get("user_prompt_hash", "")),
        "rendered_prompt_hash": str(context_map.get("rendered_prompt_hash", "")),
        "variables_hash": str(context_map.get("variables_hash", "")),
        "output_schema_id": str(context_map.get("output_schema_id", "")),
        "output_schema_version": str(context_map.get("output_schema_version", "")),
        "gateway_request_hash": str(context_map.get("gateway_request_hash", "")),
        "gateway_response_hash": str(context_map.get("gateway_response_hash", "")),
        "gateway_normalized_response_hash": str(context_map.get("gateway_normalized_response_hash", "")),
        "research_output_hash": "",
        "result_hash": "",
        "gateway_request": dict(context_map.get("gateway_request", {})) if isinstance(context_map.get("gateway_request"), Mapping) else {},
        "gateway_result": dict(context_map.get("gateway_result", {})) if isinstance(context_map.get("gateway_result"), Mapping) else {},
        "evidence_metrics": {"total_claims": 0, "cited_claims": 0, "coverage_ratio": 0},
        "research_output": {},
        "external_calls": external_calls_from(context_map.get("external_calls") if isinstance(context_map.get("external_calls"), Mapping) else None),
        "warnings": [],
        "errors": errors,
    }
    result["result_hash"] = stable_json_hash(build_expected_result(result))
    if output_root is not None:
        write_json_file(Path(output_root) / "r2b_result.json", result)
    return result


def _build_gateway_request(research_input: Mapping[str, Any], prompt: Any, rendered: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "prompt_spec_hash": rendered["prompt_spec_hash"],
        "system_prompt_hash": rendered["system_prompt_hash"],
        "user_prompt_hash": rendered["user_prompt_hash"],
        "rendered_prompt_hash": rendered["rendered_prompt_hash"],
        "variables_hash": rendered["variables_hash"],
        "system_prompt": rendered["system_prompt"],
        "user_prompt": rendered["user_prompt"],
        "research_context_hash": research_input["research_context_hash"],
        "evidence_refs": list(research_input["evidence_ids"]),
        "output_schema_id": prompt.output_schema_id,
        "output_schema_version": prompt.output_schema_version,
        "research_only": True,
    }
    if research_input.get("fake_provider_mode"):
        payload["fake_provider_mode"] = research_input["fake_provider_mode"]
    return {
        "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "request_id": f"r2b-{research_input['case_id']}-{rendered['rendered_prompt_hash'][:12]}",
        "task_type": prompt.task_type,
        "case_id": research_input["case_id"],
        "snapshot_id": research_input["snapshot_id"],
        "input_artifact_id": research_input["input_artifact_id"],
        "input_artifact_hash": research_input["input_artifact_hash"],
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.prompt_version,
        "provider_id": prompt.gateway_policy["provider_id"],
        "model_id": prompt.gateway_policy["model_id"],
        "model_version": prompt.gateway_policy["model_version"],
        "parameters": {
            "temperature": prompt.gateway_policy["temperature"],
            "max_output_tokens": prompt.gateway_policy["max_output_tokens"],
            "seed": prompt.gateway_policy["seed"],
        },
        "policy": {
            "research_only": True,
            "allow_network": False,
            "allow_tools": False,
            "allow_market_data": False,
            "allow_trading_actions": False,
        },
        "input_payload": payload,
    }


def build_expected_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": result.get("stage", ""),
        "registry_version": result.get("registry_version", ""),
        "passed": result.get("passed", False),
        "case_id": result.get("case_id", ""),
        "snapshot_id": result.get("snapshot_id", ""),
        "input_artifact_id": result.get("input_artifact_id", ""),
        "input_artifact_hash": result.get("input_artifact_hash", ""),
        "prompt_id": result.get("prompt_id", ""),
        "prompt_version": result.get("prompt_version", ""),
        "prompt_spec_hash": result.get("prompt_spec_hash", ""),
        "system_prompt_hash": result.get("system_prompt_hash", ""),
        "user_prompt_hash": result.get("user_prompt_hash", ""),
        "rendered_prompt_hash": result.get("rendered_prompt_hash", ""),
        "variables_hash": result.get("variables_hash", ""),
        "gateway_request_hash": result.get("gateway_request_hash", ""),
        "gateway_response_hash": result.get("gateway_response_hash", ""),
        "gateway_normalized_response_hash": result.get("gateway_normalized_response_hash", ""),
        "output_schema_id": result.get("output_schema_id", ""),
        "output_schema_version": result.get("output_schema_version", ""),
        "research_output_hash": result.get("research_output_hash", ""),
        "result_hash": result.get("result_hash", ""),
        "evidence_metrics": dict(result.get("evidence_metrics", {})) if isinstance(result.get("evidence_metrics"), Mapping) else {},
        "research_output": copy.deepcopy(result.get("research_output", {})),
        "external_calls": dict(result.get("external_calls", {})) if isinstance(result.get("external_calls"), Mapping) else {},
        "errors": list(result.get("errors", [])),
    }


def _stable_result_hash_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = build_expected_result(result)
    payload.pop("result_hash", None)
    return payload


def run_offline_prompt_research(
    research_input_path: str | Path,
    *,
    registry_path: str | Path,
    registry_root: str | Path,
    prompt_id: str,
    prompt_version: str,
    output_root: str | Path,
    gateway: GatewayRunner | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"prompt_id": prompt_id, "prompt_version": prompt_version}
    try:
        payload = _read_json(research_input_path)
        if not isinstance(payload, Mapping):
            raise ResearchContractError([r2b_error("invalid_research_input", "research input must be an object")])
        research_input = validate_research_input(payload)
        context.update(research_input)
        registry = load_prompt_registry(registry_path, registry_root=registry_root)
        context["registry_version"] = registry.registry_version
        prompt = registry.get_prompt(prompt_id, prompt_version)
        context.update(
            {
                "prompt_spec_hash": prompt.prompt_spec_hash,
                "output_schema_id": prompt.output_schema_id,
                "output_schema_version": prompt.output_schema_version,
            }
        )
        rendered = render_prompt(
            prompt,
            {
                "case_id": research_input["case_id"],
                "snapshot_id": research_input["snapshot_id"],
                "research_context_json": research_input["research_context_json"],
            },
        )
        context.update(rendered)
        gateway_request = _build_gateway_request(research_input, prompt, rendered)
        context["gateway_request"] = public_gateway_request(gateway_request)
        context["gateway_request_hash"] = stable_json_hash(gateway_request)
        gateway_runner = gateway or run_llm_gateway
        if gateway is None:
            gateway_result = gateway_runner(gateway_request, provider=DeterministicFakeProvider())  # type: ignore[misc]
        else:
            gateway_result = gateway_runner(gateway_request)
        context["gateway_result"] = gateway_result
        context["external_calls"] = external_calls_from(gateway_result.get("external_calls") if isinstance(gateway_result, Mapping) else None)
        context["gateway_response_hash"] = str(gateway_result.get("response_hash", ""))
        context["gateway_normalized_response_hash"] = str(gateway_result.get("normalized_response_hash", ""))
        if gateway_result.get("passed") is not True:
            errors = [r2b_error("gateway_execution_failed", "R2A gateway did not pass")]
            for error in gateway_result.get("errors") or []:
                if isinstance(error, Mapping):
                    errors.append({"code": str(error.get("code", "")), "message": str(error.get("message", "")), "field_path": str(error.get("field_path", ""))})
            return _base_failure(errors, output_root=output_root, context=context)
        response = gateway_result.get("response")
        content = response.get("content") if isinstance(response, Mapping) else {}
        if not isinstance(content, Mapping):
            return _base_failure([r2b_error("invalid_research_output", "gateway content must be an object")], output_root=output_root, context=context)
        output = structured_output_from_gateway_content(content, evidence_ids=research_input["evidence_ids"], evidence_by_id=research_input["evidence_by_id"])
        validated_output = validate_research_output(output, allowed_evidence_ids=research_input["evidence_ids"])
        result = {
            "stage": R2B_STAGE,
            "registry_version": registry.registry_version,
            "passed": True,
            "case_id": research_input["case_id"],
            "snapshot_id": research_input["snapshot_id"],
            "input_artifact_id": research_input["input_artifact_id"],
            "input_artifact_hash": research_input["input_artifact_hash"],
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.prompt_version,
            "prompt_spec_hash": prompt.prompt_spec_hash,
            "system_prompt_hash": rendered["system_prompt_hash"],
            "user_prompt_hash": rendered["user_prompt_hash"],
            "rendered_prompt_hash": rendered["rendered_prompt_hash"],
            "variables_hash": rendered["variables_hash"],
            "output_schema_id": prompt.output_schema_id,
            "output_schema_version": prompt.output_schema_version,
            "gateway_request_hash": gateway_result["request_hash"],
            "gateway_response_hash": gateway_result["response_hash"],
            "gateway_normalized_response_hash": gateway_result["normalized_response_hash"],
            "research_output_hash": validated_output["output_hash"],
            "result_hash": "",
            "gateway_request": public_gateway_request(gateway_request),
            "gateway_result": gateway_result,
            "evidence_metrics": validated_output["metrics"],
            "research_output": validated_output["output"],
            "external_calls": external_calls_from(gateway_result.get("external_calls")),
            "warnings": [],
            "errors": [],
        }
        result["result_hash"] = stable_json_hash(_stable_result_hash_payload(result))
        write_json_file(Path(output_root) / "r2b_result.json", result)
        return result
    except json.JSONDecodeError:
        return _base_failure([r2b_error("invalid_json", "input JSON is invalid")], output_root=output_root, context=context)
    except OSError as exc:
        return _base_failure([r2b_error("r2b_error", type(exc).__name__)], output_root=output_root, context=context)
    except (PromptRegistryError, PromptRenderError, ResearchContractError, R2BContractError) as exc:
        return _base_failure(list(exc.errors), output_root=output_root, context=context)
