"""Lint an implementation plan in one call -- replaces the ad-hoc validation
scripts plan writers used to improvise (see docs/claude/skills-tools.md,
Plan writing).

    python scripts/dev/plan_lint.py docs/superpowers/plans/<any file of the plan>

Checks the whole plan (a split plan's index and every part):
  * header: **Bump:**, **Edge:** (one of the four classes), **Spec:**
  * ## Parallelisation present
  * no file over 1500 lines
  * task ids unique; every ledger id has a ### Task and vice versa
  * plans above v145: **Model:** <tier> is the first line under every task
  * every `Modify:` path exists (tracked or on disk) or is created by an earlier task
  * no leftover heredoc delimiter, no TBD / "similar to Task" placeholders

Prints one line per problem and a verdict; exit code 1 when anything failed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MAX_LINES = 1500
EDGES = ("expectancy", "harvest", "volume", "none (integrity)")
MODEL_TIERS = ("haiku", "sonnet", "opus")
TASK_RE = re.compile(r"^### Task ([A-Za-z0-9-]+)")
LEDGER_ROW_RE = re.compile(r"^\|\s*`?([A-Z][A-Za-z0-9-]*\d[a-z]?)`?\s*\|")
PATH_RE = re.compile(r"^- (Create|Modify):\s*`([^`:]+)")
PLACEHOLDER_RE = re.compile(r"\bTBD\b|[Ss]imilar to Task|^PLAN_TASK_EOF$")
PART_SUFFIX_RE = re.compile(r"_\d+[a-z]?(-[^.]*)?\.md$")


def plan_files(any_file: Path) -> list[Path]:
    """Every file of the plan `any_file` belongs to, index first."""
    base = PART_SUFFIX_RE.sub("", any_file.name).removesuffix(".md")
    siblings = [p for p in any_file.parent.glob("*.md")
                if PART_SUFFIX_RE.sub("", p.name).removesuffix(".md") == base]
    return sorted(siblings)


def plan_number(files: list[Path]) -> int:
    m = re.search(r"-v(\d+)-", files[0].name)
    return int(m.group(1)) if m else 0


def tracked_paths() -> set[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         check=False).stdout
    return set(out.splitlines())


def check_header(text: str) -> list[str]:
    problems = [f"header: missing **{field}:**"
                for field in ("Bump", "Edge", "Spec")
                if f"**{field}:**" not in text]
    edge = re.search(r"^\*\*Edge:\*\*\s*(.+)$", text, re.M)
    if edge and not edge.group(1).strip().startswith(EDGES):
        problems.append(f"header: Edge '{edge.group(1).strip()}' is not one of {EDGES}")
    if "## Parallelisation" not in text:
        problems.append("missing ## Parallelisation")
    return problems


def ledger_ids(text: str) -> list[str]:
    ids, section = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif section == "Task ledger":
            m = LEDGER_ROW_RE.match(line)
            if m:
                ids.append(m.group(1))
    return ids


def first_content_line(lines: list[str], start: int) -> str:
    for line in lines[start:]:
        if line.strip():
            return line.strip()
    return ""


def check_model_line(name: str, lines: list[str], i: int, task: str) -> list[str]:
    line = first_content_line(lines, i + 1)
    m = re.match(r"\*\*Model:\*\*\s*(\w+)", line)
    if not m or m.group(1) not in MODEL_TIERS:
        return [f"{name}: Task {task} -- first line is not **Model:** <haiku|sonnet|opus>"]
    return []


def check_paths(name: str, line: str, created: set[str], tracked: set[str]) -> list[str]:
    m = PATH_RE.match(line)
    if not m:
        return []
    kind, path = m.group(1), m.group(2).strip()
    if kind == "Create":
        created.add(path)
        return []
    if path not in tracked and path not in created and not Path(path).exists():
        return [f"{name}: Modify `{path}` is neither tracked nor created by an earlier task"]
    return []


def scan_file(path: Path, ctx: dict) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    problems = []
    if len(lines) > MAX_LINES:
        problems.append(f"{path.name}: {len(lines)} lines (cap {MAX_LINES}) -- split, never compress")
    for i, line in enumerate(lines):
        m = TASK_RE.match(line)
        if m:
            problems += record_task(path.name, m.group(1), ctx)
            if ctx["needs_model"]:
                problems += check_model_line(path.name, lines, i, m.group(1))
        problems += check_paths(path.name, line, ctx["created"], ctx["tracked"])
        if PLACEHOLDER_RE.search(line):
            problems.append(f"{path.name}:{i + 1}: placeholder or leftover delimiter: {line.strip()[:60]}")
    return problems


def record_task(name: str, task: str, ctx: dict) -> list[str]:
    if task in ctx["tasks"]:
        return [f"{name}: Task {task} appears twice"]
    ctx["tasks"].append(task)
    return []


def check_ledger(ledger: list[str], tasks: list[str]) -> list[str]:
    if not ledger:
        return []
    missing = [t for t in ledger if t not in tasks]
    extra = [t for t in tasks if t not in ledger]
    problems = [f"ledger: no ### Task yet for {', '.join(missing)}"] if missing else []
    if extra:
        problems.append(f"ledger: tasks not in the ledger: {', '.join(extra)}")
    return problems


def lint(any_file: Path) -> list[str]:
    files = plan_files(any_file)
    head = files[0].read_text(encoding="utf-8")
    ctx = {"tasks": [], "created": set(), "tracked": tracked_paths(),
           "needs_model": plan_number(files) > 145}
    problems = check_header(head)
    for path in files:
        problems += scan_file(path, ctx)
    problems += check_ledger(ledger_ids(head), ctx["tasks"])
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_file():
        print(__doc__.strip().splitlines()[3].strip())
        return 2
    problems = lint(Path(argv[1]))
    for p in problems:
        print(f"  {p}")
    files = plan_files(Path(argv[1]))
    verdict = "FAIL" if problems else "PASS"
    print(f"PLAN LINT: {verdict}  {len(files)} file(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
