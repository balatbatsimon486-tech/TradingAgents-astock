"""Audit helpers for R2C-D offline review sealing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datang_extensions.llm_gateway.live_authorization_review.contracts import REVIEW_STAGE, hash_value


def build_review_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = {
        "audit_schema_version": "1.0",
        "stage": REVIEW_STAGE,
        "decision": payload.get("decision", "blocked"),
        "review_package_sealed": bool(payload.get("review_package_sealed", False)),
        "ready_for_human_signoff": bool(payload.get("ready_for_human_signoff", False)),
        "human_review_completed": False,
        "reviewer_identity_verified": False,
        "detached_signature_verified": False,
        "live_authorization_contract_ready": bool(payload.get("live_authorization_contract_ready", False)),
        "live_authorization_issued": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "authorization_id": str(payload.get("authorization_id", "")),
        "review_manifest_hash": str(payload.get("review_manifest_hash", "")),
        "review_record_set_hash": str(payload.get("review_record_set_hash", "")),
        "change_freeze_hash": str(payload.get("change_freeze_hash", "")),
        "authorization_draft_hash": str(payload.get("authorization_draft_hash", "")),
        "review_package_hash": str(payload.get("review_package_hash", "")),
        "required_real_world_action_count": len(payload.get("required_real_world_actions", [])) if isinstance(payload.get("required_real_world_actions"), list) else 0,
        "external_calls": dict(payload.get("external_calls", {})) if isinstance(payload.get("external_calls"), Mapping) else {},
        "error_codes": [str(error.get("code", "")) for error in payload.get("errors", []) if isinstance(error, Mapping)],
    }
    audit["audit_hash"] = hash_value({key: value for key, value in audit.items() if key != "audit_hash"})
    return audit
