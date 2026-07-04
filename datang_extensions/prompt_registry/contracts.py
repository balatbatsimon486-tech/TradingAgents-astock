"""Shared contracts for the R2B offline prompt registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.contracts import (
    CREDENTIAL_FIELDS,
    EXTERNAL_CALLS,
    FORBIDDEN_TRADING_FIELDS,
    SAFE_ID_RE,
    SHA256_RE,
    find_forbidden_key,
    is_safe_identifier,
)
from datang_extensions.llm_gateway.errors import gateway_error

R2B_STAGE = "tradingagents_r2b_offline_prompt_research"
PROMPT_REGISTRY_VERSION = "1.0"
SUPPORTED_PROMPT_REGISTRY_VERSIONS = frozenset({PROMPT_REGISTRY_VERSION})
OUTPUT_SCHEMA_ID = "institutional-research-output"
OUTPUT_SCHEMA_VERSION = "1.0"
SUPPORTED_OUTPUT_SCHEMAS = frozenset({(OUTPUT_SCHEMA_ID, OUTPUT_SCHEMA_VERSION)})
ALLOWED_PROMPT_STATUSES = frozenset({"approved", "draft", "retired"})
EXECUTABLE_PROMPT_STATUS = "approved"
ALLOWED_TASK_TYPES = frozenset({"research_generation"})
ALLOWED_STANCES = frozenset({"positive", "neutral", "negative", "insufficient_evidence"})
ALLOWED_CONFIDENCE = frozenset({"low", "medium", "high"})
MAX_TEMPLATE_BYTES = 64_000
MAX_RENDERED_PROMPT_CHARS = 200_000
MAX_EVIDENCE_COUNT = 50
MAX_EVIDENCE_TEXT_CHARS = 20_000

R2B_CREDENTIAL_FIELDS = frozenset(set(CREDENTIAL_FIELDS))
R2B_FORBIDDEN_TRADING_FIELDS = frozenset(
    set(FORBIDDEN_TRADING_FIELDS)
    | {
        "target_price",
        "execution_price",
        "portfolio_weight",
        "recommendation",
        "strategy",
        "signal",
    }
)


class R2BContractError(ValueError):
    """Raised when an R2B contract fails closed."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("; ".join(error["code"] for error in errors))
        self.errors = errors


def r2b_error(code: str, message: str, *, field_path: str = "") -> dict[str, str]:
    return gateway_error(code, message, field_path=field_path)


def raise_r2b(code: str, message: str, *, field_path: str = "") -> None:
    raise R2BContractError([r2b_error(code, message, field_path=field_path)])


def safe_identifier(value: Any) -> bool:
    return is_safe_identifier(value) and str(value) not in {"latest", "current"}


def safe_variable_name(value: Any) -> bool:
    return isinstance(value, str) and bool(SAFE_ID_RE.fullmatch(value)) and "." not in value and "[" not in value


def scan_security_fields(value: Any, prefix: str = "") -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    credential_path = find_forbidden_key(value, R2B_CREDENTIAL_FIELDS, prefix)
    if credential_path:
        errors.append(r2b_error("credential_field_detected", "credential-like field is not allowed", field_path=credential_path))
    trading_path = find_forbidden_key(value, R2B_FORBIDDEN_TRADING_FIELDS, prefix)
    if trading_path:
        errors.append(r2b_error("forbidden_trading_field_detected", "trading execution field is not allowed", field_path=trading_path))
    return errors


def external_calls_false() -> dict[str, bool]:
    return dict(EXTERNAL_CALLS)


def external_calls_from(value: Mapping[str, Any] | None) -> dict[str, bool]:
    calls = external_calls_false()
    if isinstance(value, Mapping):
        for key in calls:
            calls[key] = bool(value.get(key, calls[key]))
    return calls
