"""Run the R2B offline prompt registry research pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.prompt_registry.pipeline import build_expected_result, run_offline_prompt_research  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Synthetic R2B research input JSON path.")
    parser.add_argument("--registry", required=True, help="Prompt registry JSON path.")
    parser.add_argument("--registry-root", required=True, help="Prompt registry root directory.")
    parser.add_argument("--prompt-id", required=True, help="Explicit prompt ID.")
    parser.add_argument("--prompt-version", required=True, help="Explicit prompt version.")
    parser.add_argument("--output-root", required=True, help="Explicit output root for the R2B result.")
    parser.add_argument("--expected-result", help="Optional stable expected result fixture.")
    return parser.parse_args(argv)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _stdout_summary(result: dict[str, object]) -> dict[str, object]:
    gateway = result.get("gateway_result") if isinstance(result.get("gateway_result"), dict) else {}
    return {
        "stage": result.get("stage", ""),
        "passed": result.get("passed", False),
        "case_id": result.get("case_id", ""),
        "prompt_id": result.get("prompt_id", ""),
        "prompt_version": result.get("prompt_version", ""),
        "prompt_spec_hash": result.get("prompt_spec_hash", ""),
        "rendered_prompt_hash": result.get("rendered_prompt_hash", ""),
        "gateway_request_hash": result.get("gateway_request_hash", ""),
        "gateway_response_hash": result.get("gateway_response_hash", ""),
        "research_output_hash": result.get("research_output_hash", ""),
        "result_hash": result.get("result_hash", ""),
        "provider_id": gateway.get("provider_id", ""),
        "model_id": gateway.get("model_id", ""),
        "model_version": gateway.get("model_version", ""),
        "evidence_metrics": result.get("evidence_metrics", {}),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_offline_prompt_research(
            args.input,
            registry_path=args.registry,
            registry_root=args.registry_root,
            prompt_id=args.prompt_id,
            prompt_version=args.prompt_version,
            output_root=args.output_root,
        )
        if args.expected_result:
            expected = _load_json(args.expected_result)
            if build_expected_result(result) != expected:
                result = dict(result)
                result["passed"] = False
                result["errors"] = list(result.get("errors") or []) + [
                    {"code": "prompt_regression_detected", "message": "expected result fixture does not match", "field_path": "expected_result"}
                ]
                write_json_file(Path(args.output_root) / "r2b_result.json", result)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "passed": False,
            "errors": [{"code": "r2b_error", "message": type(exc).__name__, "field_path": ""}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(_stdout_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
