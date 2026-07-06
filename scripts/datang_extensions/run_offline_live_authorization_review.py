"""Run the R2C-D offline live authorization review gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.live_authorization_review.gate import (  # noqa: E402
    build_expected_review_result,
    require_json_object,
    run_offline_live_authorization_review,
    schema_error_result,
)
from datang_extensions.llm_gateway.live_authorization_review.contracts import LiveAuthorizationReviewError  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.clock import parse_utc_datetime  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-result", required=True)
    parser.add_argument("--review-manifest", required=True)
    parser.add_argument("--reviewer-records", required=True)
    parser.add_argument("--change-freeze", required=True)
    parser.add_argument("--authorization-draft", required=True)
    parser.add_argument("--fixed-now", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--expected-result")
    return parser.parse_args(argv)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "stage": result.get("stage", ""),
        "passed": result.get("passed", False),
        "decision": result.get("decision", "blocked"),
        "review_package_sealed": result.get("review_package_sealed", False),
        "ready_for_human_signoff": result.get("ready_for_human_signoff", False),
        "live_authorization_contract_ready": result.get("live_authorization_contract_ready", False),
        "human_review_completed": result.get("human_review_completed", False),
        "reviewer_identity_verified": result.get("reviewer_identity_verified", False),
        "detached_signature_verified": result.get("detached_signature_verified", False),
        "live_authorization_issued": result.get("live_authorization_issued", False),
        "secret_resolution_authorized": result.get("secret_resolution_authorized", False),
        "network_execution_authorized": result.get("network_execution_authorized", False),
        "live_execution_authorized": result.get("live_execution_authorized", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "provider_transport_called": result.get("provider_transport_called", False),
        "authorization_id": result.get("authorization_id", ""),
        "review_manifest_hash": result.get("review_manifest_hash", ""),
        "review_record_set_hash": result.get("review_record_set_hash", ""),
        "change_freeze_hash": result.get("change_freeze_hash", ""),
        "authorization_draft_hash": result.get("authorization_draft_hash", ""),
        "review_package_hash": result.get("review_package_hash", ""),
        "audit_hash": result.get("audit_hash", ""),
        "required_real_world_actions": result.get("required_real_world_actions", []),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        parse_utc_datetime(args.fixed_now)
        readiness = require_json_object(_load_json(args.readiness_result), field_path="readiness_result")
        manifest = require_json_object(_load_json(args.review_manifest), field_path="review_manifest")
        records = require_json_object(_load_json(args.reviewer_records), field_path="reviewer_records")
        freeze = require_json_object(_load_json(args.change_freeze), field_path="change_freeze")
        draft = require_json_object(_load_json(args.authorization_draft), field_path="authorization_draft")
        result = run_offline_live_authorization_review(readiness, manifest, records, freeze, draft, fixed_now=args.fixed_now)
        write_json_file(Path(args.output_root) / "live_authorization_review_result.json", result)
        if args.expected_result:
            expected = require_json_object(_load_json(args.expected_result), field_path="expected_result")
            if build_expected_review_result(result) != expected:
                mismatch = dict(result)
                mismatch["errors"] = [{"code": "expected_review_result_mismatch", "message": "deterministic fixture mismatch", "field_path": "expected_result"}]
                print(json.dumps(_summary(mismatch), ensure_ascii=False, sort_keys=True))
                return 1
    except (OSError, json.JSONDecodeError, ValueError, LiveAuthorizationReviewError) as exc:
        print(json.dumps(_summary(schema_error_result(exc)), ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
