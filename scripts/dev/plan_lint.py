"""Lint an implementation plan in one call -- replaces the ad-hoc validation
scripts plan writers used to improvise (see docs/claude/skills-tools.md,
Plan writing).

    python scripts/dev/plan_lint.py docs/superpowers/plans/<any file of the plan>
    python scripts/dev/plan_lint.py --stats [dir]   # median/p90 lines per task, newest 5 plans
    python scripts/dev/plan_lint.py --fix-parts <index>   # regenerate the index's ## Parts table
    python scripts/dev/plan_lint.py --ledger <index>      # check the ledger's contracts before parts are written

Checks the whole plan (a split plan's index and every part):
  * header: **Bump:**, **Edge:** (one of the four classes), **Spec:**
  * ## Parallelisation present
  * no file over 1500 lines
  * task ids unique; every ledger id has a ### Task and vice versa
  * plans above v145: **Model:** <tier> is the first line under every task
  * every `Modify:` path exists (tracked or on disk) or is created by an earlier task
  * plans from v194 (NEW_RULES_FROM): every task has a Close: line, no task runs
    over TASK_CEILING (400) lines, every `Modify: path:a-b` range ends inside the file
  * no leftover heredoc delimiter, no TBD / "similar to Task" placeholders

Prints one line per problem and a verdict; exit code 1 when anything failed.
"""
from __future__ import annotations

import math
import re
import statistics
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_doc  # noqa: E402  (scripts/dev has no __init__.py)

MAX_LINES = 1500
EDGES = ("expectancy", "harvest", "volume", "none (integrity)")
MODEL_TIERS = ("haiku", "sonnet", "opus")
TASK_RE = re.compile(r"^### Task ([A-Za-z0-9-]+)")
LEDGER_ROW_RE = re.compile(r"^\|\s*`?([A-Z][A-Za-z0-9-]*\d[a-z]?)`?\s*\|")
PATH_RE = re.compile(r"^- (Create|Modify):\s*`([^`:]+)")
PLACEHOLDER_RE = re.compile(r"\bTBD\b|[Ss]imilar to Task|^PLAN_TASK_EOF$")
PART_SUFFIX_RE = re.compile(r"_\d+[a-z]?(-[^.]*)?\.md$")
NEW_RULES_FROM = 194
TASK_CEILING = 400
CLOSE_RE = re.compile(r"^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?)?(?:\*\*)?Close:(?:\*\*)?\s*\S")
MODIFY_RANGE_RE = re.compile(r"^- Modify:\s*`([^`:]+):(\d+)(?:-(\d+))?")
STATS_DIR = Path("docs/superpowers/plans/implemented")
PART_BUDGET = 1400
DATED_PLAN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-v(\d+)-")
PART_LABEL_RE = re.compile(r"_(\d+)([a-z]?)-([^.]*)\.md$")
PARTS_END_RE = re.compile(r"#{1,2} ")
USAGE = """usage:
  python scripts/dev/plan_lint.py <any file of a plan>   lint the whole plan
  python scripts/dev/plan_lint.py --stats [dir]          lines per task, newest 5 plans in dir (default plans/implemented)
  python scripts/dev/plan_lint.py --fix-parts <index>    regenerate the index's ## Parts table from the part files
  python scripts/dev/plan_lint.py --ledger <index>       check the index's ledger contracts before parts are written"""


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


def task_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """(task id, start, end exclusive): a task runs to the next ### Task or EOF."""
    starts = [(i, m.group(1)) for i, line in enumerate(lines) if (m := TASK_RE.match(line))]
    ends = [i for i, _ in starts[1:]] + [len(lines)]
    return [(task, i, end) for (i, task), end in zip(starts, ends)]


def check_task_body(name: str, task: str, body: list[str]) -> list[str]:
    problems = []
    if not any(CLOSE_RE.match(line) for line in body):
        problems.append(f"{name}: Task {task} -- no Close: line (index ### Standard task close)")
    if len(body) > TASK_CEILING:
        problems.append(f"{name}: Task {task} -- {len(body)} lines (ceiling {TASK_CEILING})"
                        " -- split into two tasks, never compress")
    return problems


def check_modify_range(name: str, line: str, created: set[str]) -> list[str]:
    m = MODIFY_RANGE_RE.match(line)
    if not m:
        return []
    path, start = m.group(1).strip(), int(m.group(2))
    end = int(m.group(3) or start)
    if path in created or not Path(path).is_file():
        return []
    length = len(Path(path).read_text(encoding="utf-8", errors="replace").splitlines())
    if end <= length:
        return []
    return [f"{name}: Modify `{path}:{start}-{end}` ends past line {length} of the file"]


def scan_file(path: Path, ctx: dict) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    problems = []
    if len(lines) > MAX_LINES:
        problems.append(f"{path.name}: {len(lines)} lines (cap {MAX_LINES}) -- split, never compress")
    for i in range(len(lines)):
        problems += scan_line(path.name, lines, i, ctx)
    if ctx["new_rules"]:
        for task, start, end in task_spans(lines):
            problems += check_task_body(path.name, task, lines[start:end])
    return problems


def scan_line(name: str, lines: list[str], i: int, ctx: dict) -> list[str]:
    line, problems = lines[i], []
    m = TASK_RE.match(line)
    if m:
        problems += record_task(name, m.group(1), ctx)
        if ctx["needs_model"]:
            problems += check_model_line(name, lines, i, m.group(1))
    problems += check_paths(name, line, ctx["created"], ctx["tracked"])
    if ctx["new_rules"]:
        problems += check_modify_range(name, line, ctx["created"])
    if PLACEHOLDER_RE.search(line):
        problems.append(f"{name}:{i + 1}: placeholder or leftover delimiter: {line.strip()[:60]}")
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
    number = plan_number(files)
    ctx = {"tasks": [], "created": set(), "tracked": tracked_paths(),
           "needs_model": number > 145, "new_rules": number >= NEW_RULES_FROM}
    problems = check_header(head)
    for path in files:
        problems += scan_file(path, ctx)
    problems += check_ledger(ledger_ids(head), ctx["tasks"])
    return problems


def task_line_counts(files: list[Path]) -> list[int]:
    counts = []
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        counts += [end - start for _, start, end in task_spans(lines)]
    return counts


def _plan_key(files: list[Path]) -> tuple[str, int]:
    m = DATED_PLAN_RE.match(files[0].name)
    return m.group(1), int(m.group(2))


def recent_plans(directory: Path, n: int = 5) -> list[list[Path]]:
    """The newest n dated plans under directory that have tasks, newest first."""
    groups: dict[str, list[Path]] = {}
    for path in directory.glob("*.md"):
        if DATED_PLAN_RE.match(path.name):
            base = PART_SUFFIX_RE.sub("", path.name).removesuffix(".md")
            groups.setdefault(base, []).append(path)
    ordered = sorted((sorted(files) for files in groups.values()), key=_plan_key, reverse=True)
    picked: list[list[Path]] = []
    for files in ordered:
        if len(picked) == n:
            break
        if task_line_counts(files):
            picked.append(files)
    return picked


def plan_stats(directory: Path, n: int = 5) -> dict[str, int]:
    plans = recent_plans(directory, n)
    counts = sorted(c for files in plans for c in task_line_counts(files))
    if not counts:
        return {"plans": 0, "tasks": 0, "median": 0, "p90": 0, "per_part": 0}
    p90 = counts[math.ceil(0.9 * len(counts)) - 1]
    return {"plans": len(plans), "tasks": len(counts), "median": int(statistics.median(counts)),
            "p90": p90, "per_part": max(1, PART_BUDGET // p90)}


def cmd_stats(args: list[str]) -> int:
    directory = Path(args[0]) if args else STATS_DIR
    if len(args) > 1 or not directory.is_dir():
        print(USAGE)
        return 2
    s = plan_stats(directory)
    if not s["tasks"]:
        print(f"PLAN STATS: no dated plan with ### Task headings under {directory}")
        return 1
    print(f"PLAN STATS: {s['plans']} plan(s), {s['tasks']} task(s) -- median {s['median']}, "
          f"p90 {s['p90']} lines/task; {s['per_part']} task(s) per part at p90 (budget {PART_BUDGET})")
    return 0


def _part_files(index: Path) -> list[tuple[str, str, Path]]:
    """(label, slug, path) of every part file of index's plan, in part order."""
    found = []
    for path in plan_files(index):
        m = PART_LABEL_RE.search(path.name)
        if path.name != index.name and m and m.group(1) != "0":
            found.append((int(m.group(1)), m.group(2), m.group(3), path))
    found.sort(key=lambda t: (t[0], t[1]))
    return [(f"{num}{letter}", slug, path) for num, letter, slug, path in found]


def _task_range(path: Path) -> str:
    ids = [task for task, _, _ in task_spans(path.read_text(encoding="utf-8").splitlines())]
    if not ids:
        return "—"
    return ids[0] if len(ids) == 1 else f"{ids[0]}..{ids[-1]}"


def _label_key(label: str) -> tuple[int, str]:
    m = re.fullmatch(r"(\d+)([a-z]?)", label)
    return (int(m.group(1)), m.group(2)) if m else (10**9, label)


def parts_table(index: Path, old_rows: dict[str, tuple[str, str]]) -> list[str]:
    """Rows from the part files on disk; a planned part with no file yet keeps its old row."""
    rows = {}
    for label, slug, path in _part_files(index):
        scope = old_rows.get(label, ("", ""))[0] or slug.replace("-", " ")
        rows[label] = f"| {label} | `{path.name}` | {_task_range(path)} | {scope} |"
    for label, (_, line) in old_rows.items():
        rows.setdefault(label, line)
    ordered = [rows[label] for label in sorted(rows, key=_label_key)]
    return ["| Part | File | Tasks | Scope |", "|---|---|---|---|"] + ordered


def _old_rows(table: list[str]) -> dict[str, tuple[str, str]]:
    """Part label -> (raw Scope cell, raw row) of an existing parts table (header and separator skipped)."""
    old = {}
    for line in table[2:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if len(cells) >= 4:
            old[cells[0]] = (cells[-1], line.strip())
    return old


def _parts_block(lines: list[str]) -> tuple[int, int] | None:
    """(start, end exclusive) of the ## Parts table; start == end when it has none."""
    head = next((i for i, line in enumerate(lines) if line.strip() == "## Parts"), None)
    if head is None:
        return None
    end = next((i for i in range(head + 1, len(lines)) if PARTS_END_RE.match(lines[i])), len(lines))
    rows = [i for i in range(head + 1, end) if lines[i].lstrip().startswith("|")]
    return (rows[0], rows[-1] + 1) if rows else (head + 1, head + 1)


def fix_parts(index: Path) -> int:
    text = index.read_text(encoding="utf-8")
    lines = text.split("\n")
    block = _parts_block(lines)
    if block is None:
        return -1
    start, end = block
    table = parts_table(index, _old_rows(lines[start:end]))
    pad = [""] if start == end else []
    new = "\n".join(lines[:start] + pad + table + lines[end:])
    if new != text:
        index.write_text(new, encoding="utf-8", newline="\n")
    return len(table) - 2


def cmd_fix_parts(args: list[str]) -> int:
    if len(args) != 1 or not Path(args[0]).is_file():
        print(USAGE)
        return 2
    index = Path(args[0])
    written = fix_parts(index)
    if written < 0:
        print(f"PARTS TABLE: no ## Parts section in {index.name}")
        return 1
    print(f"PARTS TABLE: {written} part(s) in {index.name}")
    return 0


def cmd_lint(args: list[str]) -> int:
    if len(args) != 1 or not Path(args[0]).is_file():
        print(USAGE)
        return 2
    problems = lint(Path(args[0]))
    for p in problems:
        print(f"  {p}")
    files = plan_files(Path(args[0]))
    verdict = "FAIL" if problems else "PASS"
    print(f"PLAN LINT: {verdict}  {len(files)} file(s), {len(problems)} problem(s)")
    return 1 if problems else 0


LEDGER_TITLE = "Title"
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def required_columns() -> tuple[str, ...]:
    return (plan_doc.COL_TASK, plan_doc.COL_SPEC, plan_doc.COL_FILES,
            plan_doc.COL_CREATES, plan_doc.COL_CONSUMES)


def spec_headings(spec_text: str) -> list[str]:
    return [h for level in (1, 2, 3, 4) for h in plan_doc.sections(spec_text, level)]


def row_provides(row: dict[str, str]) -> set[str]:
    """Names a ledger row makes available to later rows."""
    names: set[str] = set()
    for column in (LEDGER_TITLE, plan_doc.COL_FILES, plan_doc.COL_CREATES):
        for token in plan_doc.backticked(row.get(column, "")):
            names.add(plan_doc.symbol_name(token))
            ident = IDENT_RE.match(token)
            if ident:
                names.add(ident.group(0))
            names.update(w for w in token.split() if w.startswith("-"))
    return names


def in_repo(name: str, tracked: set[str]) -> bool:
    if "/" in name:
        return name in tracked or Path(name).exists()
    proc = subprocess.run(["git", "grep", "-q", "-F", "-e", name, "--", ".",
                           ":(exclude)docs/superpowers"],
                          capture_output=True, check=False)
    return proc.returncode == 0


def check_spec_refs(row: dict[str, str], headings: list[str], spec_name: str) -> list[str]:
    task = row.get(plan_doc.COL_TASK, "?")
    refs = plan_doc.spec_refs(row.get(plan_doc.COL_SPEC, ""))  # drops '—' / empty
    if not refs:
        return [f"ledger: {task} has no Spec § reference"]
    return [f"ledger: {task} Spec § '{r}' matches no heading in {spec_name}"
            for r in refs if plan_doc.resolve_ref(r, headings) is None]


def check_consumes(i: int, rows: list[dict[str, str]], provides: list[set[str]],
                   tracked: set[str]) -> list[str]:
    task = rows[i].get(plan_doc.COL_TASK, "?")
    earlier = set().union(*provides[:i])
    problems = []
    for token in plan_doc.backticked(rows[i].get(plan_doc.COL_CONSUMES, "")):
        name = plan_doc.symbol_name(token)
        if name in earlier or in_repo(name, tracked):
            continue
        later = [rows[j].get(plan_doc.COL_TASK, "?")
                 for j in range(i + 1, len(rows)) if name in provides[j]]
        problems.append(
            f"ledger: {task} consumes `{name}`, created only by later row {later[0]}"
            if later else
            f"ledger: {task} consumes `{name}`: neither in the repo nor created by an earlier row")
    return problems


def check_contracts(index: Path) -> list[str]:
    text = index.read_text(encoding="utf-8")
    rows = plan_doc.ledger_rows(text)
    if not rows:
        return ["ledger: no rows under ## Task ledger"]
    missing = [f"ledger: no `{c}` column" for c in required_columns() if c not in rows[0]]
    if missing:
        return missing
    problems: list[str] = []
    spec = plan_doc.spec_path(index, text)
    if spec is None or not spec.is_file():
        problems.append(f"ledger: spec file not found ({spec})")
    else:
        headings = spec_headings(spec.read_text(encoding="utf-8"))
        for row in rows:
            problems += check_spec_refs(row, headings, spec.name)
    provides = [row_provides(r) for r in rows]
    tracked = tracked_paths()
    for i in range(len(rows)):
        problems += check_consumes(i, rows, provides, tracked)
    return problems


def cmd_ledger(args: list[str]) -> int:
    if len(args) != 1 or not Path(args[0]).is_file():
        print(USAGE)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    index = Path(args[0])
    rows = plan_doc.ledger_rows(index.read_text(encoding="utf-8"))
    problems = check_contracts(index)
    for p in problems:
        print(f"  {p}")
    verdict = "FAIL" if problems else "PASS"
    print(f"LEDGER CHECK: {verdict}  {len(rows)} row(s), {len(problems)} problem(s)")
    return 1 if problems else 0


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "--stats": cmd_stats,
    "--fix-parts": cmd_fix_parts,
    "--ledger": cmd_ledger,
}


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in COMMANDS:
        return COMMANDS[argv[1]](argv[2:])
    return cmd_lint(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
