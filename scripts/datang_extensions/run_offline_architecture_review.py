"""Run the R2C-G offline architecture review evidence sealing gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.architecture_review.contracts import ArchitectureReviewError, parse_utc, require_json_object  # noqa: E402
from datang_extensions.llm_gateway.architecture_review.gate import build_expected_architecture_review_result, run_offline_architecture_review, schema_error_result  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline R2C-G architecture review gate.")
    parser.add_argument("--r2c-f-architecture-result", required=True, type=Path)
    parser.add_argument("--review-charter", required=True, type=Path)
    parser.add_argument("--review-records", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--dissent-records", required=True, type=Path)
    parser.add_argument("--remediation-plan", required=True, type=Path)
    parser.add_argument("--risk-acceptance-requests", required=True, type=Path)
    parser.add_argument("--waiver-requests", required=True, type=Path)
    parser.add_argument("--decision-record-draft", required=True, type=Path)
    parser.add_argument("--supersede-policy", required=True, type=Path)
    parser.add_argument("--prerequisite-evidence", required=True, type=Path)
    parser.add_argument("--fixed-now", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-result", type=Path)
    return parser


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": result.get("stage", ""),
        "passed": result.get("passed", False),
        "decision": result.get("decision", "blocked"),
        "architecture_review_evidence_sealed": result.get("architecture_review_evidence_sealed", False),
        "review_role_coverage_complete": result.get("review_role_coverage_complete", False),
        "review_findings_catalog_ready": result.get("review_findings_catalog_ready", False),
        "remediation_plan_ready": result.get("remediation_plan_ready", False),
        "architecture_decision_record_ready": result.get("architecture_decision_record_ready", False),
        "supersede_policy_ready": result.get("supersede_policy_ready", False),
        "ready_for_architecture_signoff": result.get("ready_for_architecture_signoff", False),
        "architecture_review_completed": result.get("architecture_review_completed", False),
        "reviewer_identity_verified": result.get("reviewer_identity_verified", False),
        "review_signatures_verified": result.get("review_signatures_verified", False),
        "architecture_decision_approved": result.get("architecture_decision_approved", False),
        "risk_acceptance_approved": result.get("risk_acceptance_approved", False),
        "waiver_approved": result.get("waiver_approved", False),
        "vendor_selection_approved": result.get("vendor_selection_approved", False),
        "procurement_approved": result.get("procurement_approved", False),
        "deployment_authorized": result.get("deployment_authorized", False),
        "network_change_authorized": result.get("network_change_authorized", False),
        "real_integration_started": result.get("real_integration_started", False),
        "secret_resolution_authorized": result.get("secret_resolution_authorized", False),
        "network_execution_authorized": result.get("network_execution_authorized", False),
        "live_execution_authorized": result.get("live_execution_authorized", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "provider_transport_called": result.get("provider_transport_called", False),
        "review_charter_hash": result.get("review_charter_hash", ""),
        "review_record_set_hash": result.get("review_record_set_hash", ""),
        "findings_set_hash": result.get("findings_set_hash", ""),
        "dissent_set_hash": result.get("dissent_set_hash", ""),
        "remediation_plan_hash": result.get("remediation_plan_hash", ""),
        "risk_acceptance_request_set_hash": result.get("risk_acceptance_request_set_hash", ""),
        "waiver_request_set_hash": result.get("waiver_request_set_hash", ""),
        "decision_record_draft_hash": result.get("decision_record_draft_hash", ""),
        "supersede_policy_hash": result.get("supersede_policy_hash", ""),
        "evidence_bundle_hash": result.get("evidence_bundle_hash", ""),
        "architecture_review_package_hash": result.get("architecture_review_package_hash", ""),
        "audit_hash": result.get("audit_hash", ""),
        "required_real_world_actions": result.get("required_real_world_actions", []),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        parse_utc(args.fixed_now)
        result = run_offline_architecture_review(
            require_json_object(_load_json(args.r2c_f_architecture_result), field_path="r2c_f_architecture_result"),
            require_json_object(_load_json(args.review_charter), field_path="review_charter"),
            require_json_object(_load_json(args.review_records), field_path="review_records"),
            require_json_object(_load_json(args.findings), field_path="findings"),
            require_json_object(_load_json(args.dissent_records), field_path="dissent_records"),
            require_json_object(_load_json(args.remediation_plan), field_path="remediation_plan"),
            require_json_object(_load_json(args.risk_acceptance_requests), field_path="risk_acceptance_requests"),
            require_json_object(_load_json(args.waiver_requests), field_path="waiver_requests"),
            require_json_object(_load_json(args.decision_record_draft), field_path="decision_record_draft"),
            require_json_object(_load_json(args.supersede_policy), field_path="supersede_policy"),
            require_json_object(_load_json(args.prerequisite_evidence), field_path="prerequisite_evidence"),
            fixed_now=args.fixed_now,
        )
        write_json_file(args.output_root / "architecture_review_result.json", result)
        if args.expected_result:
            expected = require_json_object(_load_json(args.expected_result), field_path="expected_result")
            if build_expected_architecture_review_result(result) != expected:
                mismatch = dict(result)
                mismatch["passed"] = False
                mismatch["decision"] = "blocked"
                mismatch["ready_for_architecture_signoff"] = False
                mismatch["errors"] = [{"code": "expected_review_result_mismatch", "message": "deterministic fixture mismatch", "field_path": "expected_result"}]
                print(json.dumps(_summary(mismatch), ensure_ascii=False, sort_keys=True))
                return 1
    except (ArchitectureReviewError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(_summary(schema_error_result(exc)), ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
