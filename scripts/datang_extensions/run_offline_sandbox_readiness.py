"""Run the R2C-C offline sandbox readiness gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.sandbox_readiness.contracts import ReadinessContractError  # noqa: E402
from datang_extensions.llm_gateway.sandbox_readiness.gate import build_expected_readiness_result, run_offline_sandbox_readiness  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-profile", required=True)
    parser.add_argument("--secret-storage-proposal", required=True)
    parser.add_argument("--egress-policy", required=True)
    parser.add_argument("--run-manifest", required=True)
    parser.add_argument("--threat-model", required=True)
    parser.add_argument("--prerequisite-evidence", required=True)
    parser.add_argument("--incident-response", required=True)
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
        "ready_for_human_review": result.get("ready_for_human_review", False),
        "human_review_completed": result.get("human_review_completed", False),
        "secret_resolution_authorized": result.get("secret_resolution_authorized", False),
        "network_execution_authorized": result.get("network_execution_authorized", False),
        "live_execution_authorized": result.get("live_execution_authorized", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "provider_transport_called": result.get("provider_transport_called", False),
        "profile_hash": result.get("profile_hash", ""),
        "secret_proposal_hash": result.get("secret_proposal_hash", ""),
        "egress_policy_hash": result.get("egress_policy_hash", ""),
        "manifest_hash": result.get("manifest_hash", ""),
        "threat_model_hash": result.get("threat_model_hash", ""),
        "evidence_hash": result.get("evidence_hash", ""),
        "incident_plan_hash": result.get("incident_plan_hash", ""),
        "readiness_package_hash": result.get("readiness_package_hash", ""),
        "audit_hash": result.get("audit_hash", ""),
        "manual_review_requirements": result.get("manual_review_requirements", []),
        "blocking_findings": result.get("blocking_findings", []),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def _schema_error_result(exc: Exception) -> dict[str, object]:
    errors = getattr(exc, "errors", None)
    if not errors:
        errors = [{"code": "sandbox_readiness_config_error", "message": type(exc).__name__, "field_path": ""}]
    return {
        "passed": False,
        "decision": "blocked",
        "ready_for_human_review": False,
        "human_review_completed": False,
        "secret_resolution_authorized": False,
        "network_execution_authorized": False,
        "live_execution_authorized": False,
        "credential_value_resolved": False,
        "provider_transport_called": False,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payloads = [
            _load_json(args.sandbox_profile),
            _load_json(args.secret_storage_proposal),
            _load_json(args.egress_policy),
            _load_json(args.run_manifest),
            _load_json(args.threat_model),
            _load_json(args.prerequisite_evidence),
            _load_json(args.incident_response),
        ]
        if not all(isinstance(value, dict) for value in payloads):
            raise ValueError("all readiness inputs must be JSON objects")
        result = run_offline_sandbox_readiness(*payloads)
        schema_codes = {str(error.get("code", "")) for error in result.get("errors", []) if isinstance(error, dict)}
        if "run_manifest_schema_error" in schema_codes:
            raise ReadinessContractError(list(result.get("errors", [])))
        write_json_file(Path(args.output_root) / "sandbox_readiness_result.json", result)
        if args.expected_result:
            expected = _load_json(args.expected_result)
            if build_expected_readiness_result(result) != expected:
                mismatch = dict(result)
                mismatch["errors"] = [{"code": "expected_readiness_result_mismatch", "message": "deterministic fixture mismatch", "field_path": "expected_result"}]
                print(json.dumps(_summary(mismatch), ensure_ascii=False, sort_keys=True))
                return 1
    except (OSError, json.JSONDecodeError, ValueError, ReadinessContractError) as exc:
        print(json.dumps(_schema_error_result(exc), ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
