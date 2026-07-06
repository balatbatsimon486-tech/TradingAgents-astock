from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datang_extensions.llm_gateway.trust_boundary.gate import require_json_object, run_offline_trust_boundary_review, schema_error_result


def _load_json(path: Path, field_path: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return require_json_object(value, field_path=field_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline R2C-E trust-boundary review.")
    parser.add_argument("--r2c-d-review-result", required=True, type=Path)
    parser.add_argument("--trust-provider-manifest", required=True, type=Path)
    parser.add_argument("--identity-provider-contract", required=True, type=Path)
    parser.add_argument("--signature-verifier-contract", required=True, type=Path)
    parser.add_argument("--nonce-issuer-contract", required=True, type=Path)
    parser.add_argument("--authorization-issuer-contract", required=True, type=Path)
    parser.add_argument("--prerequisite-evidence", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-result", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = run_offline_trust_boundary_review(
            _load_json(args.r2c_d_review_result, "r2c_d_review_result"),
            _load_json(args.trust_provider_manifest, "trust_provider_manifest"),
            _load_json(args.identity_provider_contract, "identity_provider_contract"),
            _load_json(args.signature_verifier_contract, "signature_verifier_contract"),
            _load_json(args.nonce_issuer_contract, "nonce_issuer_contract"),
            _load_json(args.authorization_issuer_contract, "authorization_issuer_contract"),
            _load_json(args.prerequisite_evidence, "prerequisite_evidence"),
        )
    except Exception as exc:
        result = schema_error_result(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        args.output_root.mkdir(parents=True, exist_ok=True)
        output_path = args.output_root / "trust_boundary_result.json"
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.expected_result is not None:
            expected = _load_json(args.expected_result, "expected_result")
            if result != expected:
                print(json.dumps(result, ensure_ascii=False, sort_keys=True))
                return 1
    except Exception as exc:
        result = schema_error_result(exc)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
