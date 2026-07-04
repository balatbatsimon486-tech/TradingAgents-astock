"""Run the R2C-B offline provider authorization gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.provider_authorization.clock import FixedAuthorizationClock  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.contracts import AuthorizationContractError  # noqa: E402
from datang_extensions.llm_gateway.provider_authorization.gate import (  # noqa: E402
    build_expected_authorization_result,
    run_offline_authorization,
)
from datang_extensions.utils.safe_io import write_json_file  # noqa: E402

DEFAULT_PROVIDER_CONFIG = PROJECT_ROOT / "tests" / "tradingagents_bridge" / "fixtures" / "r2c" / "provider_config.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding-registry", required=True, help="R2C-B binding registry JSON path.")
    parser.add_argument("--policy", required=True, help="R2C-B authorization policy JSON path.")
    parser.add_argument("--request", required=True, help="R2C-B authorization request JSON path.")
    parser.add_argument("--approvals", required=True, help="R2C-B approval set JSON path.")
    parser.add_argument("--fixed-now", required=True, help="Fixed UTC timestamp used for deterministic authorization.")
    parser.add_argument("--output-root", required=True, help="Explicit output root for authorization_result.json.")
    parser.add_argument("--provider-config", default=str(DEFAULT_PROVIDER_CONFIG), help="R2C-A fake provider config JSON path.")
    parser.add_argument("--expected-result", help="Optional expected result fixture for deterministic comparison.")
    return parser.parse_args(argv)


def _load_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "stage": result.get("stage", ""),
        "passed": result.get("passed", False),
        "decision": result.get("decision", "deny"),
        "preflight_authorized": result.get("preflight_authorized", False),
        "live_execution_authorized": result.get("live_execution_authorized", False),
        "credential_value_resolved": result.get("credential_value_resolved", False),
        "provider_transport_called": result.get("provider_transport_called", False),
        "authorization_request_id": result.get("authorization_request_id", ""),
        "binding_id": result.get("binding_id", ""),
        "policy_id": result.get("policy_id", ""),
        "provider_id": result.get("provider_id", ""),
        "model_id": result.get("model_id", ""),
        "adapter_id": result.get("adapter_id", ""),
        "decision_hash": result.get("decision_hash", ""),
        "audit_hash": result.get("audit_hash", ""),
        "external_calls": result.get("external_calls", {}),
        "errors": result.get("errors", []),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        registry = _load_json(args.binding_registry)
        policy = _load_json(args.policy)
        request = _load_json(args.request)
        approvals = _load_json(args.approvals)
        provider_config = _load_json(args.provider_config)
        if not all(isinstance(value, dict) for value in (registry, policy, request, approvals, provider_config)):
            raise ValueError("all input fixtures must be JSON objects")
        clock = FixedAuthorizationClock.from_iso8601(args.fixed_now)
        result = run_offline_authorization(registry, policy, request, approvals, adapter_config=provider_config, clock=clock)
        write_json_file(Path(args.output_root) / "authorization_result.json", result)
        if args.expected_result:
            expected = _load_json(args.expected_result)
            if build_expected_authorization_result(result) != expected:
                mismatch = dict(result)
                mismatch["errors"] = [{"code": "expected_authorization_result_mismatch", "message": "deterministic fixture mismatch", "field_path": "expected_result"}]
                print(json.dumps(_summary(mismatch), ensure_ascii=False, sort_keys=True))
                return 1
    except (OSError, json.JSONDecodeError, ValueError, AuthorizationContractError) as exc:
        payload = {
            "passed": False,
            "decision": "deny",
            "preflight_authorized": False,
            "live_execution_authorized": False,
            "credential_value_resolved": False,
            "provider_transport_called": False,
            "errors": [{"code": "offline_provider_authorization_config_error", "message": type(exc).__name__, "field_path": ""}],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(_summary(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
