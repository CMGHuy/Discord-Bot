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

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# scripts/dev is sys.path[0] when run directly, but not when a test loads this
# file via spec_from_file_location (same reason as testrun.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_lint  # noqa: E402
import testrun  # noqa: E402

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


DB_PREFIXES = (
    "alembic",
    "swingbot/core/db/",
    "swingbot/core/infra/expectancy_attribution_store.py",
    "swingbot/core/infra/gate_counterfactual_store.py",
    "swingbot/core/marketdata/data_store.py",
    "swingbot/core/marketdata/history_store.py",
    "swingbot/core/planning/plan_store.py",
    "swingbot/core/scanning/progress_store.py",
    "tests/db/",
)
FRONTEND_PREFIXES = ("frontend/",)
TEST_DB_URL = testrun.TEST_DB_URL_DEFAULT
TEST_DB_CONTAINER = "swing-db-test"
TEST_DB_SERVICE = "db-test"
NG_TEST_WRAPPER = "frontend/scripts/ng-test.mjs"
MAX_IMAGE_READS = 4
_TASK_HEADING_RE = re.compile(r"^### Task ([A-Za-z0-9-]+):")


def _normal(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def needs_db(paths) -> bool:
    return any(_normal(p).startswith(DB_PREFIXES) for p in paths)


def needs_frontend(paths) -> bool:
    return any(_normal(p).startswith(FRONTEND_PREFIXES) for p in paths)


def _base_lines(wt: str, branch: str, attribution: str) -> list[str]:
    return [
        f"- Worktree: `{wt}` on branch `{branch}`. Use absolute paths and `git -C {wt}`; never `cd`.",
        f"- Tests: `python {wt}/scripts/dev/testrun.py file {wt}/<test file>`; never the full suite, never `fast`.",
        "- Complexity: `python -m radon cc -s -n C <changed .py files>` prints nothing; "
        f"`git -C {wt} add` new files, then `python {wt}/scripts/dev/complexity_gate.py` exits 0.",
        f"- Every commit message ends with: `{attribution}`",
        "- These facts are settled; do not probe them again.",
    ]


def _db_lines() -> list[str]:
    return [
        f"- Database: tests use `TEST_DATABASE_URL={TEST_DB_URL}`, the one shared test server "
        f"(compose service `{TEST_DB_SERVICE}`, container `{TEST_DB_CONTAINER}`, profile `test`). "
        "The test fixtures create their own databases on it; never create a container or a database by hand.",
        "- If that server is unreachable, return `BLOCKED:`; the controller owns the containers and `/replicate-prod-db`.",
    ]


def _frontend_lines(wt: str) -> list[str]:
    return [
        f"- Frontend tests: `node {wt}/{NG_TEST_WRAPPER} {wt}/frontend --include <spec path under frontend/>` "
        "(no `cd`, no `npx`). A 60 s start timeout under load is cured by one re-run.",
        f"- UI checks: run `node {wt}/frontend/scripts/layout-audit.mjs --base http://localhost:1234` first and "
        "work from its findings. Screenshots are clipped to a named element: "
        f"`node {wt}/frontend/scripts/browse.mjs shots --path <route> --clip <css selector>`. "
        f"At most {MAX_IMAGE_READS} image reads per task; needing more is `BLOCKED:` with the reason.",
    ]


def environment_block(worktree: Path, branch: str, paths: list[str], attribution: str) -> str:
    """The handoff's Environment body: base facts, plus DB/frontend lines by path prefix."""
    wt = worktree.as_posix()
    lines = _base_lines(wt, branch, attribution)
    if needs_db(paths):
        lines += _db_lines()
    if needs_frontend(paths):
        lines += _frontend_lines(wt)
    return "\n".join(lines) + "\n"


def _deliverable_line(item: Deliverable) -> str:
    indent = "  " if "." in item.id else ""
    return f"{indent}- {item.id} {item.text}"


def render_handoff(task_text: str, deliverables: list[Deliverable], environment: str) -> str:
    """The handoff file: heading, then the SECTIONS in order; slots left for /task-brief."""
    heading = _TASK_HEADING_RE.match(task_text)
    if not heading:
        raise HandoffError("task text does not start with a `### Task <id>:` heading")
    bodies = {
        "Task": task_text.rstrip("\n"),
        "Deliverables": "\n".join(_deliverable_line(d) for d in deliverables),
        "Environment": environment.rstrip("\n"),
        "Preflight": PREFLIGHT_SLOT,
        "Code": CODE_SLOT,
    }
    blocks = [f"# Handoff: Task {heading.group(1)}"] + [f"## {name}\n\n{bodies[name]}" for name in SECTIONS]
    return "\n\n".join(blocks) + "\n"


def handoff_path(main_root: Path, plan: Path, task_id: str) -> Path:
    """Where a task's handoff lives: the main checkout's gitignored .superpowers/sdd/."""
    return main_root / ".superpowers" / "sdd" / plan_base(plan) / f"task-{task_id}-handoff.md"


def _git(start: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(start), *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise HandoffError(f"not a git checkout: {start}")
    return done.stdout.strip()


def main_checkout(start: Path) -> Path:
    """The main checkout's root, from any of its worktrees (via --git-common-dir)."""
    common = Path(_git(start, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = start / common
    return common.resolve().parent


def _refuse_filled(target: Path) -> None:
    if not target.exists():
        return
    text = target.read_text(encoding="utf-8")
    if PREFLIGHT_SLOT not in text or CODE_SLOT not in text:
        raise HandoffError(f"{target} is already filled by /task-brief; delete it to regenerate")


def build_handoff(plan: Path, task_id: str, worktree: Path, attribution: str) -> Path:
    """Locate, derive, render and write one task's handoff; returns its path."""
    if not plan.is_file():
        raise HandoffError(f"plan file not found: {plan}")
    _, section = find_task(plan_lint.plan_files(plan.resolve()), task_id)
    deliverables = derive_deliverables(section, task_id)
    paths = [path for _, path in files_paths(section)]
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    environment = environment_block(worktree.resolve(), branch, paths, attribution)
    target = handoff_path(main_checkout(worktree), plan, task_id)
    _refuse_filled(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_handoff(section, deliverables, environment), encoding="utf-8")
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task_handoff.py", description="Write one task's handoff file.")
    parser.add_argument("plan", type=Path, help="any file of the plan (index or part)")
    parser.add_argument("task_id", help="exact task id, e.g. V199-5")
    parser.add_argument("--worktree", type=Path, required=True, help="the implementer's worktree")
    parser.add_argument("--attribution", required=True, help="commit attribution line")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        target = build_handoff(args.plan, args.task_id, args.worktree, args.attribution)
    except HandoffError as exc:
        print(f"task_handoff: {exc}")
        return 2
    print(target.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
