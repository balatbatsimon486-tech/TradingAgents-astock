"""Fixed-clock helpers for deterministic R2C-B authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc_datetime(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("fixed UTC timestamps must end with Z")
    try:
        return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid fixed UTC timestamp") from exc


def format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime(UTC_FORMAT)


@dataclass(frozen=True)
class FixedAuthorizationClock:
    """A deterministic clock injected by tests and CLI fixtures."""

    fixed_now: datetime

    @classmethod
    def from_iso8601(cls, value: str) -> "FixedAuthorizationClock":
        return cls(parse_utc_datetime(value))

    def now(self) -> datetime:
        return self.fixed_now

    def now_iso(self) -> str:
        return format_utc(self.fixed_now)

    def plus_seconds_iso(self, seconds: int) -> str:
        return format_utc(self.fixed_now + timedelta(seconds=seconds))
