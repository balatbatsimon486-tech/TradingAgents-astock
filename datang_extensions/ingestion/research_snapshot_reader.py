"""Read-only Datang research snapshot consumer for TradingAgents-astock."""

from __future__ import annotations

import json
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping

REQUIRED_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "snapshot_id",
    "schema_version",
    "source",
    "as_of_time",
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

IDENTITY_FIELDS: tuple[str, ...] = (
    "snapshot_id",
    "schema_version",
    "source",
    "as_of_time",
)

SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})

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


def _is_blank_string(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def _resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _parse_aware_datetime(value: Any) -> datetime | None:
    if _is_blank_string(value):
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _validate_path(
    snapshot_path: str | Path,
    allowed_root: str | Path | None,
) -> tuple[Path | None, dict[str, Any] | None]:
    if allowed_root is None:
        return None, _structured_error(
            "missing_allowed_root",
            "allowed_root is required for reading research snapshots",
            path=snapshot_path,
            field="allowed_root",
        )

    resolved_root = _resolve_path(allowed_root)
    resolved_path = _resolve_path(snapshot_path)

    if not _is_relative_to(resolved_path, resolved_root):
        return None, _structured_error(
            "path_outside_allowed_root",
            "research snapshot path must stay within allowed_root",
            path=resolved_path,
            field="snapshot_path",
        )

    if not resolved_path.exists():
        return None, _structured_error(
            "missing_snapshot_file",
            "research snapshot file does not exist",
            path=resolved_path,
        )

    if not resolved_path.is_file():
        return None, _structured_error(
            "snapshot_path_not_file",
            "research snapshot path must be a regular JSON file",
            path=resolved_path,
            field="snapshot_path",
        )

    if resolved_path.suffix.lower() != ".json":
        return None, _structured_error(
            "invalid_snapshot_extension",
            "research snapshot file extension must be .json",
            path=resolved_path,
            field="snapshot_path",
        )

    return resolved_path, None


def _validate_identity_fields(snapshot: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    missing = _missing_required_fields(snapshot)
    if missing:
        return _structured_error(
            "invalid_snapshot_schema",
            f"research snapshot missing required fields: {', '.join(missing)}",
            path=path,
            field=",".join(missing),
        )

    for field in ("snapshot_id", "source"):
        if _is_blank_string(snapshot.get(field)):
            return _structured_error(
                "invalid_snapshot_schema",
                f"{field} must be a non-empty string",
                path=path,
                field=field,
            )

    if not isinstance(snapshot.get("schema_version"), str):
        return _structured_error(
            "invalid_snapshot_schema",
            "schema_version must be a string",
            path=path,
            field="schema_version",
        )

    data_quality = snapshot.get("data_quality")
    if not isinstance(data_quality, Mapping):
        return _structured_error(
            "invalid_snapshot_schema",
            "data_quality must be an object",
            path=path,
            field="data_quality",
        )

    return None


def _validate_schema_version(snapshot: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    schema_version = snapshot.get("schema_version")
    if not isinstance(schema_version, str):
        return _structured_error(
            "invalid_snapshot_schema",
            "schema_version must be a string",
            path=path,
            field="schema_version",
        )

    if schema_version.strip() not in SUPPORTED_SCHEMA_VERSIONS:
        return _structured_error(
            "unsupported_schema_version",
            "schema_version is not supported",
            path=path,
            field="schema_version",
        )

    snapshot_version = snapshot.get("snapshot_version")
    if snapshot_version is not None:
        if not isinstance(snapshot_version, str) or not snapshot_version.strip():
            return _structured_error(
                "invalid_snapshot_schema",
                "snapshot_version must be a non-empty string when present",
                path=path,
                field="snapshot_version",
            )
        if snapshot_version.strip() != schema_version.strip():
            return _structured_error(
                "unsupported_schema_version",
                "snapshot_version must match schema_version when both are present",
                path=path,
                field="snapshot_version",
            )

    return None


def _validate_data_quality(snapshot: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    data_quality = snapshot.get("data_quality")
    if not isinstance(data_quality, Mapping):
        return _structured_error(
            "invalid_snapshot_schema",
            "data_quality must be an object",
            path=path,
            field="data_quality",
        )

    if data_quality.get("passed") is not True:
        return _structured_error(
            "data_quality_not_passed",
            "data_quality.passed must be boolean True",
            path=path,
            field="data_quality.passed",
        )

    for field in ("errors", "blockers", "critical_issues"):
        value = data_quality.get(field)
        if value:
            return _structured_error(
                "data_quality_not_passed",
                f"data_quality.{field} must be empty",
                path=path,
                field=f"data_quality.{field}",
            )

    return None


def _validate_times(snapshot: Mapping[str, Any], path: Path) -> dict[str, Any] | None:
    as_of_time = _parse_aware_datetime(snapshot.get("as_of_time"))
    if as_of_time is None:
        return _structured_error(
            "invalid_as_of_time",
            "as_of_time must be a timezone-aware ISO-8601 string",
            path=path,
            field="as_of_time",
        )

    generated_at_value = snapshot.get("generated_at")
    if generated_at_value is not None:
        generated_at = _parse_aware_datetime(generated_at_value)
        if generated_at is None:
            return _structured_error(
                "invalid_generated_at",
                "generated_at must be a timezone-aware ISO-8601 string",
                path=path,
                field="generated_at",
            )
        if generated_at < as_of_time:
            return _structured_error(
                "invalid_generated_at",
                "generated_at must not be earlier than as_of_time",
                path=path,
                field="generated_at",
            )

    return None


def _readonly_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    consumable_snapshot = {field: snapshot.get(field) for field in REQUIRED_SNAPSHOT_FIELDS}
    return {
        "read_only": True,
        "source_platform": SOURCE_PLATFORM,
        "allowed_usage": CONTEXT_USAGE,
        "no_trading_decision": True,
        "snapshot_id": snapshot.get("snapshot_id", ""),
        "schema_version": snapshot.get("schema_version", ""),
        "source": snapshot.get("source", ""),
        "as_of_time": snapshot.get("as_of_time", ""),
        "generated_at": snapshot.get("generated_at", ""),
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
    allowed_root: str | Path | None = None,
    expected_source_platform: str = SOURCE_PLATFORM,
) -> dict[str, Any]:
    """Read a Datang research snapshot as a read-only research context."""

    path, path_error = _validate_path(snapshot_path, allowed_root)
    if path_error is not None:
        return path_error
    assert path is not None

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

    validation_error = _validate_identity_fields(snapshot, path)
    if validation_error is not None:
        return validation_error

    validation_error = _validate_schema_version(snapshot, path)
    if validation_error is not None:
        return validation_error

    validation_error = _validate_data_quality(snapshot, path)
    if validation_error is not None:
        return validation_error

    validation_error = _validate_times(snapshot, path)
    if validation_error is not None:
        return validation_error

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
