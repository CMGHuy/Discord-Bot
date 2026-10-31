"""Write the task-implementer handoff file for one plan task (v199 spec, section 1).

    python scripts/dev/task_handoff.py <plan file> <task id> --worktree <path> --attribution "<line>"

The handoff carries the task text verbatim, numbered deliverables D1..Dn
derived from the task's **Files:** clause and `- [ ]` steps, the environment
facts implementers used to probe for, and two slots /task-brief fills.
Prints the handoff's absolute path as its last line. Exit code 2, with a
one-line reason, when the task is missing, duplicated, or yields no
deliverables.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# scripts/dev is sys.path[0] when run directly, but not when a test loads this
# file via spec_from_file_location (same reason as testrun.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_lint  # noqa: E402

SECTIONS = ("Task", "Deliverables", "Environment", "Preflight", "Code")
PREFLIGHT_SLOT = "<!-- task-brief: fill Preflight -->"
CODE_SLOT = "<!-- task-brief: fill Code -->"
REPORT_PREFIX = "DELIVERABLES:"
IMPLEMENTER_STATES = ("done", "deviated")
REVIEWER_STATES = ("done", "missing", "different")
NO_HANDOFF_LINE = f"{REPORT_PREFIX} n/a (no handoff)"
SECTION_ENDS = ("### Task ", "# ", "## ")


class HandoffError(Exception):
    """A plan or task no handoff can be built from; main() exits 2 with it."""


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split("\n")


def _fenced(lines: list[str]) -> list[bool]:
    """Per line: True while it opens, sits in or closes a fenced block."""
    state = {"fence": None}
    return [plan_lint.update_fence(line, state) for line in lines]


def _starts(lines: list[str], fenced: list[bool], task_id: str) -> list[int]:
    heading = re.compile(rf"^### Task {re.escape(task_id)}:")
    return [i for i, line in enumerate(lines) if not fenced[i] and heading.match(line)]


def task_section(text: str, task_id: str) -> str | None:
    """The `### Task <id>:` section of one plan file, or None; first match wins."""
    lines = _lines(text)
    fenced = _fenced(lines)
    starts = _starts(lines, fenced, task_id)
    if not starts:
        return None
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines))
                if not fenced[i] and lines[i].startswith(SECTION_ENDS)), len(lines))
    return "\n".join(lines[start:end]).rstrip("\n") + "\n"


def _hits(path: Path, task_id: str) -> int:
    lines = _lines(path.read_text(encoding="utf-8"))
    return len(_starts(lines, _fenced(lines), task_id))


def find_task(files: list[Path], task_id: str) -> tuple[Path, str]:
    """The one file holding `### Task <id>:` and its section; HandoffError otherwise."""
    holders = [path for path in files for _ in range(_hits(path, task_id))]
    if not holders:
        names = ", ".join(path.name for path in files)
        raise HandoffError(f"task {task_id} not found in: {names}")
    if len(holders) > 1:
        names = ", ".join(path.name for path in holders)
        raise HandoffError(f"task {task_id} appears {len(holders)} times, in: {names}")
    path = holders[0]
    return path, task_section(path.read_text(encoding="utf-8"), task_id)


def plan_base(plan: Path) -> str:
    """The plan's file stem without a split-plan `_<n>-<slug>` suffix."""
    return plan_lint.PART_SUFFIX_RE.sub("", plan.name).removesuffix(".md")
