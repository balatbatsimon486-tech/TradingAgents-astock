"""Run the R2C-A offline fake provider adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.provider_adapters.chat_adapter import run_provider_adapter  # noqa: E402
from datang_extensions.llm_gateway.provider_adapters.contracts import ProviderAdapterContractError  # noqa: E402
from datang_extensions.llm_gateway.provider_adapters.fake_transport import load_fake_transport_from_directory  # noqa: E402
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Synthetic R2A request JSON path.")
    parser.add_argument("--provider-config", required=True, help="Synthetic provider adapter config JSON path.")
    parser.add_argument("--fixture-map", required=True, help="Fake transport response fixture directory.")
    parser.add_argument("--output-root", required=True, help="Explicit output root for adapter_result.json.")
    return parser.parse_args(argv)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "stage": result.get("stage", ""),
        "passed": result.get("passed", False),
        "request_id": result.get("request_id", ""),
        "provider_id": result.get("provider_id", ""),
        "model_id": result.get("model_id", ""),
        "adapter_id": result.get("adapter_id", ""),
        "transport_kind": result.get("transport_kind", ""),
        "live_mode_enabled": result.get("live_mode_enabled", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "wire_request_hash": result.get("wire_request_hash", ""),
        "idempotency_key": result.get("idempotency_key", ""),
        "wire_response_hash": result.get("wire_response_hash", ""),
        "normalized_response_hash": result.get("normalized_response_hash", ""),
        "retry_count": result.get("retry_count", 0),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        request = _load_json(args.request)
        config = _load_json(args.provider_config)
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        if not isinstance(config, dict):
            raise ValueError("provider config must be an object")
        transport = load_fake_transport_from_directory(args.fixture_map)
        result = run_provider_adapter(request, provider_config=config, transport=transport)
    except (OSError, json.JSONDecodeError, ValueError, ProviderAdapterContractError) as exc:
        payload = {
            "passed": False,
            "errors": [{"code": "provider_adapter_config_error", "message": type(exc).__name__, "field_path": ""}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        write_json_file(Path(args.output_root) / "adapter_result.json", result)
    except OSError as exc:
        payload = {
            "passed": False,
            "errors": [{"code": "provider_adapter_output_error", "message": type(exc).__name__, "field_path": ""}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
