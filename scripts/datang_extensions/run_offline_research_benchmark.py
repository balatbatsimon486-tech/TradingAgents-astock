"""Run the M2B offline research benchmark suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.evaluation.offline_research_benchmark import (  # noqa: E402
    BenchmarkManifestError,
    run_offline_research_benchmark,
)
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON path.")
    parser.add_argument("--fixtures-root", required=True, help="Root containing synthetic benchmark fixtures.")
    parser.add_argument("--output-root", required=True, help="Explicit synthetic benchmark output root.")
    parser.add_argument("--baseline", help="Optional expected baseline JSON path.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first unexpected case.")
    parser.add_argument("--write-summary", help="Optional path for writing the benchmark summary JSON.")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write a new baseline to --baseline when the file does not already exist.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_offline_research_benchmark(
            args.manifest,
            fixtures_root=args.fixtures_root,
            output_root=args.output_root,
            baseline_path=args.baseline if args.baseline and not args.write_baseline else None,
            fail_fast=args.fail_fast,
            write_baseline=args.write_baseline,
            baseline_output_path=args.baseline if args.write_baseline else None,
        )
    except (BenchmarkManifestError, FileExistsError, OSError, json.JSONDecodeError) as exc:
        payload = {
            "passed": False,
            "errors": [
                {
                    "code": getattr(exc, "code", type(exc).__name__),
                    "message": str(exc),
                }
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2

    if args.write_summary:
        write_json_file(args.write_summary, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
