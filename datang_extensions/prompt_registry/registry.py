"""Versioned prompt registry loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from datang_extensions.llm_gateway.contracts import ALLOWED_MODELS, ALLOWED_PROVIDERS, stable_json_hash
from datang_extensions.prompt_registry.contracts import (
    ALLOWED_PROMPT_STATUSES,
    ALLOWED_TASK_TYPES,
    EXECUTABLE_PROMPT_STATUS,
    MAX_TEMPLATE_BYTES,
    OUTPUT_SCHEMA_ID,
    OUTPUT_SCHEMA_VERSION,
    R2BContractError,
    SUPPORTED_PROMPT_REGISTRY_VERSIONS,
    r2b_error,
    safe_identifier,
    safe_variable_name,
)


class PromptRegistryError(R2BContractError):
    """Raised when prompt registry validation fails closed."""


@dataclass(frozen=True)
class PromptSpec:
    registry_version: str
    prompt_id: str
    prompt_version: str
    status: str
    task_type: str
    system_template: str
    user_template: str
    system_template_content: str
    user_template_content: str
    required_variables: tuple[str, ...]
    optional_variables: tuple[str, ...]
    output_schema_id: str
    output_schema_version: str
    gateway_policy: dict[str, Any]
    metadata: dict[str, Any]
    prompt_spec: dict[str, Any]
    prompt_spec_hash: str


class PromptRegistry:
    def __init__(self, *, registry_id: str, registry_version: str, prompts: list[PromptSpec]) -> None:
        self.registry_id = registry_id
        self.registry_version = registry_version
        self.prompts = list(prompts)
        self._by_identity = {(prompt.prompt_id, prompt.prompt_version): prompt for prompt in prompts}

    def get_prompt(self, prompt_id: str, prompt_version: str) -> PromptSpec:
        if not safe_identifier(prompt_id):
            raise PromptRegistryError([r2b_error("invalid_prompt_id", "prompt_id must be a safe explicit identifier", field_path="prompt_id")])
        if not safe_identifier(prompt_version):
            raise PromptRegistryError([r2b_error("invalid_prompt_version", "prompt_version must be explicit and not latest/current", field_path="prompt_version")])
        prompt = self._by_identity.get((prompt_id, prompt_version))
        if prompt is None:
            raise PromptRegistryError([r2b_error("prompt_not_found", "exact prompt_id/version was not found", field_path="prompt_version")])
        if prompt.status != EXECUTABLE_PROMPT_STATUS:
            raise PromptRegistryError([r2b_error("prompt_not_approved", "prompt is not approved", field_path="status")])
        return prompt


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "registry JSON is invalid")]) from exc
    except OSError as exc:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", type(exc).__name__)]) from exc


def _read_template(path_value: Any, *, registry_root: Path, field_path: str) -> tuple[str, str]:
    if not isinstance(path_value, str) or not path_value.strip():
        raise PromptRegistryError([r2b_error("unsafe_template_path", "template path must be a non-empty relative path", field_path=field_path)])
    template_rel = Path(path_value)
    if template_rel.is_absolute() or any(part == ".." for part in template_rel.parts):
        raise PromptRegistryError([r2b_error("unsafe_template_path", "template path must stay inside registry root", field_path=field_path)])
    template_path = registry_root / template_rel
    if not template_path.exists():
        raise PromptRegistryError([r2b_error("template_not_found", "template file does not exist", field_path=field_path)])
    try:
        resolved_root = registry_root.resolve(strict=True)
        resolved_template = template_path.resolve(strict=True)
        resolved_template.relative_to(resolved_root)
    except ValueError as exc:
        raise PromptRegistryError([r2b_error("unsafe_template_path", "template resolves outside registry root", field_path=field_path)]) from exc
    except OSError as exc:
        raise PromptRegistryError([r2b_error("template_not_found", type(exc).__name__, field_path=field_path)]) from exc
    if not resolved_template.is_file():
        raise PromptRegistryError([r2b_error("template_not_file", "template path must be a regular file", field_path=field_path)])
    if resolved_template.stat().st_size > MAX_TEMPLATE_BYTES:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "template is too large", field_path=field_path)])
    try:
        content = resolved_template.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PromptRegistryError([r2b_error("invalid_template_encoding", "template must be UTF-8", field_path=field_path)]) from exc
    return path_value, content


def _variable_tuple(value: Any, *, field_path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "variables must be a list", field_path=field_path)])
    variables = tuple(str(item) for item in value)
    if len(set(variables)) != len(variables) or any(not safe_variable_name(item) for item in variables):
        raise PromptRegistryError([r2b_error("invalid_template_variable", "variables must be unique safe identifiers", field_path=field_path)])
    return variables


def _validate_prompt(prompt: Mapping[str, Any], *, registry_version: str, registry_root: Path, seen: set[tuple[str, str]]) -> PromptSpec:
    prompt_id = str(prompt.get("prompt_id", ""))
    prompt_version = str(prompt.get("prompt_version", ""))
    if not safe_identifier(prompt_id):
        raise PromptRegistryError([r2b_error("invalid_prompt_id", "prompt_id must be safe", field_path="prompt_id")])
    if not safe_identifier(prompt_version):
        raise PromptRegistryError([r2b_error("invalid_prompt_version", "prompt_version must be explicit", field_path="prompt_version")])
    identity = (prompt_id, prompt_version)
    if identity in seen:
        raise PromptRegistryError([r2b_error("duplicate_prompt_version", "duplicate prompt_id/version", field_path="prompts")])
    seen.add(identity)

    status = str(prompt.get("status", ""))
    if status not in ALLOWED_PROMPT_STATUSES:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "prompt status is not allowlisted", field_path="status")])
    if status != EXECUTABLE_PROMPT_STATUS:
        raise PromptRegistryError([r2b_error("prompt_not_approved", "only approved prompts can execute", field_path="status")])
    task_type = str(prompt.get("task_type", ""))
    if task_type not in ALLOWED_TASK_TYPES:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "task_type is not allowlisted", field_path="task_type")])

    required_variables = _variable_tuple(prompt.get("required_variables"), field_path="required_variables")
    optional_variables = _variable_tuple(prompt.get("optional_variables", []), field_path="optional_variables")
    if set(required_variables) & set(optional_variables):
        raise PromptRegistryError([r2b_error("invalid_template_variable", "required and optional variables overlap", field_path="optional_variables")])

    output_schema_id = str(prompt.get("output_schema_id", ""))
    output_schema_version = str(prompt.get("output_schema_version", ""))
    if output_schema_id != OUTPUT_SCHEMA_ID or output_schema_version != OUTPUT_SCHEMA_VERSION:
        raise PromptRegistryError([r2b_error("unsupported_research_output_schema", "unsupported output schema", field_path="output_schema_version")])

    gateway_policy = prompt.get("gateway_policy")
    if not isinstance(gateway_policy, Mapping):
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "gateway_policy must be an object", field_path="gateway_policy")])
    policy = dict(gateway_policy)
    if policy.get("provider_id") not in ALLOWED_PROVIDERS or policy.get("model_id") not in ALLOWED_MODELS:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "provider/model is not allowlisted", field_path="gateway_policy")])
    if policy.get("temperature") != 0:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "temperature must be zero", field_path="gateway_policy.temperature")])
    if not isinstance(policy.get("seed"), int) or not isinstance(policy.get("max_output_tokens"), int):
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "seed and max_output_tokens must be integers", field_path="gateway_policy")])

    metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), Mapping) else {}
    if metadata.get("research_only") is not True:
        raise PromptRegistryError([r2b_error("research_policy_violation", "metadata.research_only must be true", field_path="metadata.research_only")])

    system_template, system_content = _read_template(prompt.get("system_template"), registry_root=registry_root, field_path="system_template")
    user_template, user_content = _read_template(prompt.get("user_template"), registry_root=registry_root, field_path="user_template")

    prompt_spec = {
        "registry_version": registry_version,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "status": status,
        "task_type": task_type,
        "system_template_content": system_content,
        "user_template_content": user_content,
        "required_variables": list(required_variables),
        "optional_variables": list(optional_variables),
        "output_schema_id": output_schema_id,
        "output_schema_version": output_schema_version,
        "gateway_policy": policy,
        "metadata": dict(metadata),
    }
    return PromptSpec(
        registry_version=registry_version,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        status=status,
        task_type=task_type,
        system_template=system_template,
        user_template=user_template,
        system_template_content=system_content,
        user_template_content=user_content,
        required_variables=required_variables,
        optional_variables=optional_variables,
        output_schema_id=output_schema_id,
        output_schema_version=output_schema_version,
        gateway_policy=policy,
        metadata=dict(metadata),
        prompt_spec=prompt_spec,
        prompt_spec_hash=stable_json_hash(prompt_spec),
    )


def load_prompt_registry(registry_path: str | Path, *, registry_root: str | Path) -> PromptRegistry:
    root = Path(registry_root).resolve(strict=False)
    payload = _load_json(Path(registry_path))
    if not isinstance(payload, Mapping):
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "registry must be a JSON object")])
    registry_id = str(payload.get("registry_id", ""))
    registry_version = str(payload.get("registry_version", ""))
    if not safe_identifier(registry_id):
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "registry_id must be safe", field_path="registry_id")])
    if registry_version not in SUPPORTED_PROMPT_REGISTRY_VERSIONS:
        raise PromptRegistryError([r2b_error("unsupported_prompt_registry_version", "unsupported registry version", field_path="registry_version")])
    prompts_payload = payload.get("prompts")
    if not isinstance(prompts_payload, list) or not prompts_payload:
        raise PromptRegistryError([r2b_error("invalid_prompt_registry", "prompts must be a non-empty list", field_path="prompts")])
    seen: set[tuple[str, str]] = set()
    prompts: list[PromptSpec] = []
    for item in prompts_payload:
        if not isinstance(item, Mapping):
            raise PromptRegistryError([r2b_error("invalid_prompt_registry", "prompt entries must be objects", field_path="prompts")])
        prompts.append(_validate_prompt(item, registry_version=registry_version, registry_root=root, seen=seen))
    return PromptRegistry(registry_id=registry_id, registry_version=registry_version, prompts=prompts)
