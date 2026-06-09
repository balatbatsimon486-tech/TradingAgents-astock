"""Run the offline TradingAgents-astock report ingestion smoke test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.ingestion.offline_report_ingestion import (  # noqa: E402
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_DIR,
    ingest_offline_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH), help="Offline JSON input path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory.")
    parser.add_argument("--upstream-commit", default="", help="Optional upstream commit marker.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = ingest_offline_report(
        args.input,
        args.output_dir,
        upstream_commit=args.upstream_commit,
    )
    report = result["report"]
    metadata = result["metadata"]

    print("Offline TradingAgents-astock ingestion smoke complete.")
    print(f"status: {metadata['status']}")
    print(f"markdown_report_path: {metadata['markdown_report_path']}")
    print(f"json_report_path: {metadata['json_report_path']}")
    print(f"metadata_path: {metadata['metadata_path']}")
    print(f"final_signal: {report['final_signal']} (research output only, not a trade order)")
    return 0 if metadata["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
