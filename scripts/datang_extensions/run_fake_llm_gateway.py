"""Run the R2A offline fake LLM gateway."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.fake_provider import DeterministicFakeProvider  # noqa: E402
from datang_extensions.llm_gateway.gateway import run_llm_gateway  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Synthetic R2A request JSON path.")
    parser.add_argument("--output-root", required=True, help="Explicit output root for the gateway result.")
    parser.add_argument("--fixture-map", help="Optional fake-provider response fixture map JSON path.")
    return parser.parse_args(argv)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_fixture_map(path: str | Path | None) -> dict[str, dict[str, object]]:
    if not path:
        return {}
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("fixture map must be a JSON object")
    return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request = _load_json(args.request)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        fixture_map = _load_fixture_map(args.fixture_map)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "passed": False,
            "errors": [{"code": "invalid_gateway_request", "message": type(exc).__name__}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2

    result = run_llm_gateway(request, provider=DeterministicFakeProvider(fixture_map=fixture_map))
    output_root = Path(args.output_root)
    try:
        write_json_file(output_root / "gateway_result.json", result)
    except OSError as exc:
        payload = {
            "passed": False,
            "errors": [{"code": "gateway_error", "message": type(exc).__name__}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
