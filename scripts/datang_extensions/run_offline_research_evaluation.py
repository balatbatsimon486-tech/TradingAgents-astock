"""Run the M2A offline research evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.evaluation.offline_research_pipeline import (  # noqa: E402
    run_offline_research_evaluation,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Synthetic snapshot JSON path.")
    parser.add_argument("--allowed-root", required=True, help="Allowed root for the snapshot path.")
    parser.add_argument("--output-root", required=True, help="Synthetic output root.")
    parser.add_argument("--case-id", required=True, help="Synthetic case id.")
    parser.add_argument("--repeat", type=int, default=1, help="Optional deterministic repeat count.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repeat < 1:
        print(json.dumps({"passed": False, "errors": [{"code": "invalid_repeat"}]}, sort_keys=True))
        return 2

    results = []
    for index in range(args.repeat):
        output_root = Path(args.output_root)
        if args.repeat > 1:
            output_root = output_root / f"run_{index + 1}"
        results.append(
            run_offline_research_evaluation(
                args.snapshot,
                allowed_root=args.allowed_root,
                output_root=output_root,
                case_id=args.case_id,
            )
        )

    summary = results[0] if args.repeat == 1 else {"passed": all(item["passed"] for item in results), "runs": results}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
