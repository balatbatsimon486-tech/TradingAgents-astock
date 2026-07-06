"""CLI for the R2C-F offline trust integration architecture gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.trust_integration_architecture.gate import (  # noqa: E402
    ArchitectureError,
    build_expected_architecture_result,
    run_offline_trust_integration_architecture,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ArchitectureError([{"code": "trust_integration_architecture_error", "message": "input must be a JSON object", "field_path": str(path.name)}])
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline R2C-F trust integration architecture gate.")
    parser.add_argument("--r2c-e-trust-boundary-result", required=True, type=Path)
    parser.add_argument("--candidate-catalog", required=True, type=Path)
    parser.add_argument("--evaluation-policy", required=True, type=Path)
    parser.add_argument("--deployment-topology", required=True, type=Path)
    parser.add_argument("--ownership-matrix", required=True, type=Path)
    parser.add_argument("--change-control-plan", required=True, type=Path)
    parser.add_argument("--rollback-plan", required=True, type=Path)
    parser.add_argument("--drill-plan", required=True, type=Path)
    parser.add_argument("--prerequisite-evidence", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-result", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_offline_trust_integration_architecture(
            _load_json(args.r2c_e_trust_boundary_result),
            _load_json(args.candidate_catalog),
            _load_json(args.evaluation_policy),
            _load_json(args.deployment_topology),
            _load_json(args.ownership_matrix),
            _load_json(args.change_control_plan),
            _load_json(args.rollback_plan),
            _load_json(args.drill_plan),
            _load_json(args.prerequisite_evidence),
        )
        if args.expected_result is not None:
            expected = _load_json(args.expected_result)
            if build_expected_architecture_result(result) != expected:
                result = dict(result)
                result["passed"] = False
                result["decision"] = "blocked"
                result["ready_for_architecture_review"] = False
                result["errors"] = result.get("errors", []) + [{"code": "expected_result_mismatch", "message": "expected fixture does not match", "field_path": "expected_result"}]
                result["blocking_findings"] = result["errors"]
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "trust_integration_architecture_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("passed") is True else 1
    except (ArchitectureError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"passed": False, "decision": "blocked", "errors": [{"code": "trust_integration_architecture_error", "message": str(exc), "field_path": "input"}]}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
