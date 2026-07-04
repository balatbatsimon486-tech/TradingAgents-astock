"""Deterministic prompt rendering for R2B."""

from __future__ import annotations

import string
from typing import Any, Mapping

from datang_extensions.llm_gateway.contracts import stable_json_hash
from datang_extensions.prompt_registry.contracts import (
    MAX_RENDERED_PROMPT_CHARS,
    R2BContractError,
    r2b_error,
    safe_variable_name,
)
from datang_extensions.prompt_registry.registry import PromptSpec


class PromptRenderError(R2BContractError):
    """Raised when prompt rendering fails closed."""


def _template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    formatter = string.Formatter()
    try:
        parsed = formatter.parse(template)
        for _, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if not safe_variable_name(field_name) or format_spec or conversion:
                raise PromptRenderError([r2b_error("invalid_template_variable", "only simple placeholders are allowed", field_path=field_name)])
            fields.add(field_name)
    except ValueError as exc:
        raise PromptRenderError([r2b_error("invalid_template_variable", type(exc).__name__)]) from exc
    return fields


def render_prompt(prompt: PromptSpec, variables: Mapping[str, Any]) -> dict[str, Any]:
    allowed = set(prompt.required_variables) | set(prompt.optional_variables)
    provided = set(str(key) for key in variables.keys())
    template_fields = _template_fields(prompt.system_template_content) | _template_fields(prompt.user_template_content)
    unknown_fields = sorted(template_fields - allowed)
    if unknown_fields:
        raise PromptRenderError([r2b_error("invalid_template_variable", "template references an unknown variable", field_path=unknown_fields[0])])
    unexpected = sorted(provided - allowed)
    if unexpected:
        raise PromptRenderError([r2b_error("unexpected_prompt_variable", "unknown variable was provided", field_path=unexpected[0])])
    missing = [name for name in prompt.required_variables if name not in provided]
    if missing:
        raise PromptRenderError([r2b_error("missing_prompt_variable", "required variable is missing", field_path=missing[0])])
    safe_variables: dict[str, str] = {}
    for key, value in variables.items():
        if not safe_variable_name(str(key)) or not isinstance(value, str):
            raise PromptRenderError([r2b_error("invalid_template_variable", "variables must be strings with safe names", field_path=str(key))])
        safe_variables[str(key)] = value

    missing_fields = sorted(template_fields - provided)
    if missing_fields:
        raise PromptRenderError([r2b_error("missing_prompt_variable", "template variable is missing", field_path=missing_fields[0])])

    system_prompt = prompt.system_template_content.format(**safe_variables)
    user_prompt = prompt.user_template_content.format(**safe_variables)
    if len(system_prompt) + len(user_prompt) > MAX_RENDERED_PROMPT_CHARS:
        raise PromptRenderError([r2b_error("rendered_prompt_too_large", "rendered prompt is too large")])
    variables_hash = stable_json_hash(safe_variables)
    rendered_payload = {
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.prompt_version,
        "prompt_spec_hash": prompt.prompt_spec_hash,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "variables_hash": variables_hash,
        "output_schema_id": prompt.output_schema_id,
        "output_schema_version": prompt.output_schema_version,
    }
    return {
        "prompt_id": prompt.prompt_id,
        "prompt_version": prompt.prompt_version,
        "prompt_spec_hash": prompt.prompt_spec_hash,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "system_prompt_hash": stable_json_hash(system_prompt),
        "user_prompt_hash": stable_json_hash(user_prompt),
        "rendered_prompt_hash": stable_json_hash(rendered_payload),
        "variables_hash": variables_hash,
    }
