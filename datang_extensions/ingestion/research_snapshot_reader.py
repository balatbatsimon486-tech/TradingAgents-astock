"""Read-only Datang research snapshot consumer for TradingAgents-astock."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping

REQUIRED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "symbol",
    "trade_date",
    "source_platform",
    "data_source",
    "snapshot_version",
    "created_at_utc",
    "price_window",
    "latest_ohlcv",
    "adj_factor",
    "stock_basic",
    "data_quality",
    "warnings",
    "errors",
)

FORBIDDEN_TRADING_FIELDS: frozenset[str] = frozenset(
    {
        "signal",
        "recommendation",
        "strategy",
        "backtest",
        "expected_return",
        "target_price",
        "position_size",
        "portfolio_weight",
        "trade_order",
    }
)

FORBIDDEN_CREDENTIAL_FIELDS: frozenset[str] = frozenset(
    {
        "token",
        "api_key",
        "secret",
        "password",
        "access_token",
        "refresh_token",
    }
)

CONTEXT_USAGE = "research_context_only"
SOURCE_PLATFORM = "datang_quant_platform"


def _structured_error(
    code: str,
    message: str,
    *,
    path: str | Path | None = None,
    field: str = "",
) -> dict[str, Any]:
    return {
        "ok": False,
        "passed": False,
        "context": None,
        "error": {
            "code": code,
            "message": message,
            "path": "" if path is None else str(path),
            "field": field,
        },
    }


def _normalized_key(key: object) -> str:
    return str(key).strip().lower()


def _find_forbidden_key(payload: Any, forbidden: frozenset[str]) -> str:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = _normalized_key(key)
            if normalized in forbidden:
                return str(key)
            nested = _find_forbidden_key(value, forbidden)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _find_forbidden_key(item, forbidden)
            if nested:
                return nested
    return ""


def _missing_required_fields(snapshot: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_SNAPSHOT_FIELDS:
        if field not in snapshot:
            missing.append(field)
    return missing


def _readonly_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    consumable_snapshot = {field: snapshot.get(field) for field in REQUIRED_SNAPSHOT_FIELDS}
    return {
        "read_only": True,
        "source_platform": SOURCE_PLATFORM,
        "allowed_usage": CONTEXT_USAGE,
        "no_trading_decision": True,
        "symbol": snapshot.get("symbol", ""),
        "trade_date": snapshot.get("trade_date", ""),
        "snapshot_version": snapshot.get("snapshot_version", ""),
        "data_source": snapshot.get("data_source", ""),
        "price_window": snapshot.get("price_window"),
        "latest_ohlcv": snapshot.get("latest_ohlcv"),
        "adj_factor": snapshot.get("adj_factor"),
        "stock_basic": snapshot.get("stock_basic"),
        "data_quality": snapshot.get("data_quality"),
        "warnings": snapshot.get("warnings"),
        "errors": snapshot.get("errors"),
        "snapshot": consumable_snapshot,
    }


def read_research_snapshot(
    snapshot_path: str | Path,
    *,
    expected_source_platform: str = SOURCE_PLATFORM,
) -> dict[str, Any]:
    """Read a Datang research snapshot as a read-only research context."""

    path = Path(snapshot_path)
    if not path.exists():
        return _structured_error(
            "missing_snapshot_file",
            "research snapshot file does not exist",
            path=path,
        )

    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        return _structured_error("invalid_json", str(exc), path=path)
    except OSError as exc:
        return _structured_error("snapshot_read_error", str(exc), path=path)

    if not isinstance(snapshot, dict):
        return _structured_error(
            "invalid_snapshot_schema",
            "research snapshot must be a JSON object",
            path=path,
        )

    forbidden_trading_field = _find_forbidden_key(snapshot, FORBIDDEN_TRADING_FIELDS)
    if forbidden_trading_field:
        return _structured_error(
            "forbidden_trading_field",
            "research snapshot contains a trading decision field",
            path=path,
            field=forbidden_trading_field,
        )

    forbidden_credential_field = _find_forbidden_key(snapshot, FORBIDDEN_CREDENTIAL_FIELDS)
    if forbidden_credential_field:
        return _structured_error(
            "credential_field_detected",
            "research snapshot contains a credential-like field",
            path=path,
            field=forbidden_credential_field,
        )

    missing = _missing_required_fields(snapshot)
    if missing:
        return _structured_error(
            "invalid_snapshot_schema",
            f"research snapshot missing required fields: {', '.join(missing)}",
            path=path,
            field=",".join(missing),
        )

    if snapshot.get("source_platform") != expected_source_platform:
        return _structured_error(
            "invalid_snapshot_schema",
            f"source_platform must be {expected_source_platform}",
            path=path,
            field="source_platform",
        )

    return {
        "ok": True,
        "passed": True,
        "context": _readonly_context(snapshot),
        "error": None,
    }
