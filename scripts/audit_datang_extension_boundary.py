"""Audit whether Datang extension changes stay outside upstream core code."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOWED_PREFIXES: tuple[str, ...] = (
    "datang_extensions/",
    "docs/",
    "tests/",
    ".github/",
    "scripts/",
)

ALLOWED_FILES: frozenset[str] = frozenset(
    {
        ".gitignore",
        "requirements-dev.txt",
        "reports/tradingagents_astock/.gitkeep",
    }
)


@dataclass(frozen=True)
class AuditResult:
    is_git_repo: bool
    repo_root: Path | None
    branch: str
    changed_files: tuple[str, ...]
    boundary_violations: tuple[str, ...]
    message: str = ""

    @property
    def has_boundary_violations(self) -> bool:
        return bool(self.boundary_violations)


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _normalize_git_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_allowed_change(path: str) -> bool:
    normalized = _normalize_git_path(path)
    return normalized in ALLOWED_FILES or normalized.startswith(ALLOWED_PREFIXES)


def _parse_status_paths(status_output: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in status_output.splitlines():
        if not line:
            continue
        raw_path = line[3:].strip()
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", 1)[-1]
        normalized = _normalize_git_path(raw_path)
        if normalized:
            paths.append(normalized)
    return tuple(paths)


def find_repo_root(start_dir: str | Path = ".") -> Path | None:
    cwd = Path(start_dir)
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def current_branch(repo_root: Path) -> str:
    result = _run_git(["branch", "--show-current"], cwd=repo_root)
    branch = result.stdout.strip()
    if result.returncode == 0 and branch:
        return branch

    fallback = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    if fallback.returncode != 0:
        return ""
    return fallback.stdout.strip()


def changed_files(repo_root: Path) -> tuple[str, ...]:
    result = _run_git(["status", "--porcelain=v1", "-uall"], cwd=repo_root)
    if result.returncode != 0:
        return ()
    return _parse_status_paths(result.stdout)


def run_audit(start_dir: str | Path = ".") -> AuditResult:
    repo_root = find_repo_root(start_dir)
    if repo_root is None:
        return AuditResult(
            is_git_repo=False,
            repo_root=None,
            branch="",
            changed_files=(),
            boundary_violations=(),
            message=f"not a Git repository: {Path(start_dir)}",
        )

    files = changed_files(repo_root)
    violations = tuple(path for path in files if not _is_allowed_change(path))
    return AuditResult(
        is_git_repo=True,
        repo_root=repo_root,
        branch=current_branch(repo_root),
        changed_files=files,
        boundary_violations=violations,
    )


def print_audit(result: AuditResult) -> None:
    if not result.is_git_repo:
        print(f"ERROR: {result.message}")
        return

    print(f"Git repository root: {result.repo_root}")
    print(f"Current branch: {result.branch or '(detached or unknown)'}")
    print("Changed files:")
    if result.changed_files:
        for path in result.changed_files:
            print(f"- {path}")
    else:
        print("- none")

    if result.boundary_violations:
        print("WARNING: possible upstream core source pollution detected:")
        for path in result.boundary_violations:
            print(f"- {path}")
    else:
        print("Boundary check: OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository or subdirectory to audit. Defaults to the current directory.",
    )
    args = parser.parse_args(argv)

    result = run_audit(args.repo)
    print_audit(result)
    if not result.is_git_repo:
        return 2
    if result.has_boundary_violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


