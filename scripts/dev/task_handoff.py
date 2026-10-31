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
from typing import NamedTuple

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


FILES_LABEL = "**Files:**"
FILES_VERBS = ("modify", "create", "update", "test", "delete")
STEP_MARK = "- [ ]"
NEGATIVE_WORDS = ("remain", "unchanged")
PYTHON_FENCES = ("python", "py")
_BACKTICK_RE = re.compile(r"`[^`]*`")
_CLAUSE_BREAK_RE = re.compile(r"`[^`]*`|;|\.(?=\s|$)")
_VERB_OR_SPAN_RE = re.compile(r"`([^`]+)`|\b(" + "|".join(FILES_VERBS) + r")\b", re.IGNORECASE)
_LINE_RANGE_RE = re.compile(r":\d+(?:-\d+)?$")
_PATH_CHARS_RE = re.compile(r"[\w.\-/\\]+")
_TEST_DEF_RE = re.compile(r"^\s*(?:async\s+)?def (test_\w+)\s*\(")


class Deliverable(NamedTuple):
    id: str    # "D3", or "D3.2" for the second test of step D3
    text: str


def _files_text(lines: list[str], fenced: list[bool]) -> str:
    """The first **Files:** paragraph outside a fence as one string; bullets start clauses."""
    for i, line in enumerate(lines):
        if fenced[i] or not line.startswith(FILES_LABEL):
            continue
        parts = [line[len(FILES_LABEL):]]
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if fenced[j] or not nxt.strip() or nxt.startswith("**"):
                break
            parts.append(("; " if nxt.lstrip().startswith("- ") else " ") + nxt.strip())
        return "".join(parts)
    return ""


def _clauses(text: str) -> list[str]:
    """Split at `;` and sentence ends, never inside a backticked span."""
    clauses, start = [], 0
    for m in _CLAUSE_BREAK_RE.finditer(text):
        if m.group(0).startswith("`"):
            continue
        clauses.append(text[start:m.start()])
        start = m.end()
    clauses.append(text[start:])
    return [c.strip() for c in clauses if c.strip()]


def _is_negative(clause: str) -> bool:
    """`Existing ...` or `... remain/unchanged ...` names files the task must not change."""
    prose = _BACKTICK_RE.sub("", clause).lstrip("- ").strip().lower()
    return prose.startswith("existing") or any(word in prose for word in NEGATIVE_WORDS)


def _as_path(span: str) -> str | None:
    path = _LINE_RANGE_RE.sub("", span.strip())
    if _PATH_CHARS_RE.fullmatch(path) and ("/" in path or "." in path):
        return path
    return None


def _clause_paths(clause: str) -> list[tuple[str, str]]:
    if _is_negative(clause):
        return []
    verb, found = None, []
    for m in _VERB_OR_SPAN_RE.finditer(clause):
        if m.group(2):
            verb = m.group(2)
        elif verb and _as_path(m.group(1)):
            found.append((verb, _as_path(m.group(1))))
    return found


def files_paths(section: str) -> list[tuple[str, str]]:
    """(verb as written, path) for every path the task's **Files:** clause names."""
    lines = _lines(section)
    text = _files_text(lines, _fenced(lines))
    return [pair for clause in _clauses(text) for pair in _clause_paths(clause)]


def _is_python(info: str) -> bool:
    words = info.split()
    return bool(words) and words[0].lower() in PYTHON_FENCES


def _steps(lines: list[str]) -> list[tuple[str, list[str]]]:
    """(step text, [test names]) for every `- [ ]` line outside a fence."""
    state, info, steps = {"fence": None}, "", []
    for line in lines:
        opening = plan_lint.FENCE_RE.match(line) if state["fence"] is None else None
        in_fence = plan_lint.update_fence(line, state)
        if opening:
            info = opening.group(2)
        elif not in_fence and line.lstrip().startswith(STEP_MARK):
            steps.append((line.lstrip()[len(STEP_MARK):].strip(), []))
        elif in_fence and steps and _is_python(info):
            match = _TEST_DEF_RE.match(line)
            if match:
                steps[-1][1].append(match.group(1))
    return steps


def derive_deliverables(section: str, task_id: str) -> list[Deliverable]:
    """D1..Dn: Files paths first, then steps, each step's tests as Dn.k sub-items."""
    items = [Deliverable(f"D{n}", f"{verb} `{path}`")
             for n, (verb, path) in enumerate(files_paths(section), 1)]
    number = len(items)
    for text, tests in _steps(_lines(section)):
        number += 1
        items.append(Deliverable(f"D{number}", text))
        items += [Deliverable(f"D{number}.{k}", name) for k, name in enumerate(tests, 1)]
    if not items:
        raise HandoffError(f"no deliverables derivable for {task_id}")
    return items
