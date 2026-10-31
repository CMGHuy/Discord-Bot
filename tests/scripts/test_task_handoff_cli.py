"""task_handoff.py writes the handoff under the main checkout and exits 2 with a reason (V199-6b)."""
from __future__ import annotations

import importlib.util
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "task_handoff", ROOT / "scripts" / "dev" / "task_handoff.py")
task_handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_handoff)

ATTRIBUTION = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PLAN_BASE = "2026-10-28-v198-risk-reporting-correctness"
PART = textwrap.dedent("""\
    # Risk reporting correctness — collector and API

    ### Task V198-1: Decompose portfolio collection without changing behavior
    **Model:** opus — splits a legacy collector currently at complexity 20.

    **Files:** Modify `swingbot/core/edge/portfolio_state.py`; create `tests/edge/test_portfolio_state_collection.py`.

    - [ ] Fetch/status and inspect recent commits.

    ### Task V198-9: Prose only
    **Model:** haiku — nothing derivable.

    Nothing to do.
    """)


def _git(*args: str) -> None:
    subprocess.run(["git", *args], capture_output=True, text=True, check=True)


@pytest.fixture
def checkout(tmp_path):
    """(main checkout, linked worktree on branch `feat`, plan part file)."""
    main = tmp_path / "main"
    main.mkdir()
    _git("-C", str(main), "init", "-q")
    _git("-C", str(main), "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init")
    _git("-C", str(main), "worktree", "add", "-q", "-b", "feat", str(tmp_path / "wt"))
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / f"{PLAN_BASE}_0-index.md").write_text("# Index\n", encoding="utf-8")
    part = plans / f"{PLAN_BASE}_1-collector-and-api.md"
    part.write_text(PART, encoding="utf-8")
    return main, tmp_path / "wt", part


def _run(part: Path, task_id: str, wt: Path, capsys) -> tuple[int, str]:
    code = task_handoff.main([str(part), task_id, "--worktree", str(wt), "--attribution", ATTRIBUTION])
    return code, capsys.readouterr().out


def _target(main: Path) -> Path:
    return main.resolve() / ".superpowers" / "sdd" / PLAN_BASE / "task-V198-1-handoff.md"


def test_main_checkout_resolves_from_main_and_from_a_worktree(checkout):
    main, wt, _ = checkout
    assert task_handoff.main_checkout(wt).resolve() == main.resolve()
    assert task_handoff.main_checkout(main).resolve() == main.resolve()


def test_main_checkout_outside_git_is_a_handoff_error(tmp_path):
    with pytest.raises(task_handoff.HandoffError, match="not a git checkout"):
        task_handoff.main_checkout(tmp_path)


def test_cli_writes_the_handoff_and_prints_its_path_last(checkout, capsys):
    main, wt, part = checkout
    code, out = _run(part, "V198-1", wt, capsys)
    assert code == 0
    assert Path(out.splitlines()[-1]) == _target(main)
    text = _target(main).read_text(encoding="utf-8")
    assert text.startswith("# Handoff: Task V198-1\n")
    assert "`feat`" in text and ATTRIBUTION in text
    assert "- D1 Modify `swingbot/core/edge/portfolio_state.py`" in text
    assert task_handoff.PREFLIGHT_SLOT in text and task_handoff.CODE_SLOT in text
    assert not (wt / ".superpowers").exists()


def test_cli_regenerates_an_unfilled_handoff(checkout, capsys):
    main, wt, part = checkout
    assert _run(part, "V198-1", wt, capsys)[0] == 0
    assert _run(part, "V198-1", wt, capsys)[0] == 0


def test_cli_never_overwrites_a_filled_handoff(checkout, capsys):
    main, wt, part = checkout
    target = _target(main)
    target.parent.mkdir(parents=True)
    target.write_text("# Handoff: Task V198-1\n\n## Preflight\n\nfilled\n", encoding="utf-8")
    code, out = _run(part, "V198-1", wt, capsys)
    assert code == 2 and "already filled" in out
    assert target.read_text(encoding="utf-8").endswith("filled\n")


@pytest.mark.parametrize(("task_id", "message"), [
    ("V198-7", "task V198-7 not found"),
    ("V198-9", "no deliverables derivable for V198-9"),
])
def test_cli_exits_2_with_the_reason(checkout, capsys, task_id, message):
    _, wt, part = checkout
    code, out = _run(part, task_id, wt, capsys)
    assert code == 2
    assert out.startswith("task_handoff: ") and message in out


def test_cli_rejects_a_missing_plan_file(checkout, capsys):
    _, wt, part = checkout
    code, out = _run(part.with_name("nope.md"), "V198-1", wt, capsys)
    assert code == 2 and "plan file not found" in out
