"""Runtime metadata helpers for report generation."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from datang_extensions import __version__


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_git_commit(repo_dir: str | Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repo_dir) if repo_dir else None,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def build_run_metadata(
    *,
    repo_dir: str | Path | None = None,
    upstream_commit: str | None = None,
    llm_model: str = "",
    analysis_mode: str = "",
) -> dict[str, str]:
    return {
        "upstream_commit": upstream_commit if upstream_commit is not None else safe_git_commit(repo_dir),
        "datang_extension_version": __version__,
        "run_time_utc": utc_now_iso(),
        "llm_model": llm_model,
        "analysis_mode": analysis_mode,
    }

