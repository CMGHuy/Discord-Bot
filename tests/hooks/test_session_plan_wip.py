"""SessionStart hook flags a plan whose ledger names tasks not yet on disk,
so a plan cut off by tokens is resumed by the next session or account."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-cursor.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not on PATH")

LEDGER = """# v900 Demo: Implementation Plan

## Task ledger

| Id | Title | Part |
|---|---|---|
| V900-1 | first | 1 |
| V900-2 | second | 1 |
| `V900-3` | third | 2 |

## Parallelisation
"""


def _run(plans: Path) -> list[str]:
    env = dict(os.environ, SWINGBOT_PLANS_DIR=str(plans))
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(HOOK)],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return [ln for ln in proc.stdout.splitlines() if ln.startswith("PLAN WIP")
            or ln.strip().startswith(("Resume it", "Handoff notes"))]


def test_split_plan_with_missing_tasks_is_flagged(tmp_path):
    (tmp_path / "2026-10-09-v900-demo_0-index.md").write_text(
        LEDGER + "\n## Handoff\n\nPartner chose the cache universe.\n", encoding="utf-8")
    (tmp_path / "2026-10-09-v900-demo_1-first.md").write_text(
        "### Task V900-1: first\n\n### Task V900-2: second\n", encoding="utf-8")
    lines = _run(tmp_path)
    assert "2026-10-09-v900-demo -- 2/3 tasks written, missing V900-3" in lines[0]
    assert "mode=part" in lines[1]
    assert "_0-index.md" in lines[2]


def test_single_file_plan_reports_missing_span(tmp_path):
    (tmp_path / "2026-10-09-v900-demo.md").write_text(
        LEDGER + "\n### Task V900-1: first\n", encoding="utf-8")
    lines = _run(tmp_path)
    assert "1/3 tasks written, missing V900-2..V900-3" in lines[0]
    assert not any("Handoff" in ln for ln in lines)


def test_finished_and_legacy_plans_are_silent(tmp_path):
    (tmp_path / "2026-10-09-v900-demo.md").write_text(
        LEDGER + "### Task V900-1: a\n### Task V900-2: b\n### Task V900-3: c\n",
        encoding="utf-8")
    (tmp_path / "2026-10-01-v800-old.md").write_text(
        "# old plan, no ledger\n\n### Task V800-1: a\n", encoding="utf-8")
    assert _run(tmp_path) == []
