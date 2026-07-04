"""Offline secret binding authorization gate for R2C-B."""

from __future__ import annotations

from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock
from datang_extensions.llm_gateway.provider_authorization.gate import (
    build_expected_authorization_result,
    consume_offline_preflight_grant,
    run_offline_authorization,
)

__all__ = [
    "FixedAuthorizationClock",
    "build_expected_authorization_result",
    "consume_offline_preflight_grant",
    "run_offline_authorization",
]
