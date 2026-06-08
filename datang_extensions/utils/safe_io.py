"""Small path and file helpers used by the extension layer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_WINDOWS_UNSAFE_CHARS = r'[<>:"/\\|?*\x00-\x1f]+'


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def safe_filename_part(value: object, default: str = "report") -> str:
    text = str(value or "").strip() or default
    text = re.sub(_WINDOWS_UNSAFE_CHARS, "_", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("._ ") or default


def write_json_file(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def write_text_file(path: str | Path, content: str) -> Path:
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(content, encoding="utf-8")
    return target

