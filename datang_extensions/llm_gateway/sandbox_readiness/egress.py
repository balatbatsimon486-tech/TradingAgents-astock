"""Offline egress policy validation for R2C-C."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.sandbox_readiness.contracts import SUPPORTED_VERSION, hash_value, readiness_error, require_false, require_safe_id, scan_forbidden_surface


def validate_egress_policy(policy: Mapping[str, Any]) -> tuple[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    secret_error = scan_forbidden_surface(policy, prefix="egress_policy")
    if secret_error:
        errors.append(secret_error)
        return hash_value(policy), errors
    if policy.get("egress_policy_version") not in SUPPORTED_VERSION:
        errors.append(readiness_error("egress_policy_invalid", "unsupported egress policy version", field_path="egress_policy_version"))
    require_safe_id(policy.get("policy_id"), errors, "egress_policy_invalid", "policy_id")
    if policy.get("status") != "draft_for_review":
        errors.append(readiness_error("egress_policy_invalid", "egress policy must be draft_for_review", field_path="status"))
    if policy.get("network_execution_enabled") is not False:
        errors.append(readiness_error("egress_policy_invalid", "network execution must remain disabled", field_path="network_execution_enabled"))
    if policy.get("allowed_scheme") != "https":
        errors.append(readiness_error("egress_policy_invalid", "scheme must be https", field_path="allowed_scheme"))
    hosts = policy.get("allowed_hosts")
    if not isinstance(hosts, list) or not hosts:
        errors.append(readiness_error("egress_policy_invalid", "allowed_hosts must be explicit", field_path="allowed_hosts"))
        hosts = []
    for host in hosts:
        text = str(host)
        if text != "provider.invalid" or "*" in text or "/" in text or "?" in text or "@" in text or ":" in text:
            errors.append(readiness_error("egress_policy_invalid", "host must be the synthetic provider.invalid identity", field_path="allowed_hosts"))
            continue
        try:
            ipaddress.ip_address(text)
        except ValueError:
            pass
        else:
            errors.append(readiness_error("egress_policy_invalid", "IP literal hosts are not allowed", field_path="allowed_hosts"))
    if policy.get("allowed_ports") != [443]:
        errors.append(readiness_error("egress_policy_invalid", "only port 443 may be proposed", field_path="allowed_ports"))
    require_false(policy, ("redirects_allowed", "proxy_allowed", "private_network_allowed", "localhost_allowed", "ip_literal_allowed", "wildcard_hosts_allowed"), "egress_policy_invalid", errors)
    if policy.get("dns_rebinding_controls_required") is not True or policy.get("tls_verification_required") is not True:
        errors.append(readiness_error("egress_policy_invalid", "network controls must be required", field_path="network_controls"))
    if policy.get("certificate_pinning_required") is not False:
        errors.append(readiness_error("egress_policy_invalid", "certificate pinning is not part of this offline proposal", field_path="certificate_pinning_required"))
    return hash_value(policy), errors
