from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_datang_extension_boundary import _is_allowed_change, run_audit  # noqa: E402


AUDIT_SCRIPT = PROJECT_ROOT / "scripts" / "audit_datang_extension_boundary.py"
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"


def test_audit_script_gracefully_fails_outside_git_repo(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--repo", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "not a Git repository" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr

    audit_result = run_audit(tmp_path)
    assert audit_result.is_git_repo is False
    assert audit_result.repo_root is None


def test_audit_script_has_no_hardcoded_absolute_paths() -> None:
    source = AUDIT_SCRIPT.read_text(encoding="utf-8")
    forbidden_fragments = ("C:\\", "D:\\", "/Users/", "/home/", "Desktop")

    assert not any(fragment in source for fragment in forbidden_fragments)


def test_dotfiles_are_allowed_by_boundary_audit() -> None:
    assert _is_allowed_change(".gitignore")
    assert _is_allowed_change(".github/workflows/tests.yml")
    assert _is_allowed_change("requirements-dev.txt")


def test_github_actions_workflow_exists() -> None:
    assert WORKFLOW_FILE.exists()


def test_github_actions_workflow_runs_required_pytest_commands() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")

    assert "python -m pip install -e ." in workflow
    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python scripts/audit_datang_extension_boundary.py" in workflow
    assert "python -m pytest tests/test_datang_astock_adapter.py -q" in workflow
    assert "python -m pytest tests/test_git_governance.py -q" in workflow
    assert "python -m pytest -q" in workflow
    assert ".[dev]" not in workflow


def test_ci_does_not_call_real_llm_or_market_interfaces() -> None:
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8").lower()
    forbidden_fragments = (
        "openai_api_key",
        "dashscope_api_key",
        "anthropic_api_key",
        "tushare_token",
        "akshare",
        "yfinance.download",
        "broker",
        "order",
        "tradeapi",
    )

    assert not any(fragment in workflow for fragment in forbidden_fragments)



