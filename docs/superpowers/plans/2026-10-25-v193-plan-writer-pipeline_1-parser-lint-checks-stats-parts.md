# v193 — Plan-writer pipeline, Part 1: shared parser, per-task lint checks, `--stats`, `--fix-parts`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** none
**Edge:** none (integrity) — see the index.
**Spec:** [2026-10-25-v193-plan-writer-pipeline.md](../specs/2026-10-25-v193-plan-writer-pipeline.md)
**Index:** [2026-10-25-v193-plan-writer-pipeline_0-index.md](2026-10-25-v193-plan-writer-pipeline_0-index.md) — Goal, Architecture (ledger shape), Global Constraints, `### Standard task close`, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V193-3:" -A 300 <this file>`.

**Scope of this part (V193-1..V193-4):** the worktree; `scripts/dev/plan_doc.py`, the one markdown/ledger parser `plan_lint.py` and `plan_slice.py` share; the per-task lint checks (`Close:` line, task ceiling, `Modify:` range) gated to plans numbered 194 and up; `plan_lint.py --stats` with the table-driven `COMMANDS` dispatch; `plan_lint.py --fix-parts <index>`.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-25-v193-plan-writer-pipeline` (created in V193-1, Step 1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-25-v193-plan-writer-pipeline &&`. Never edit the main tree's files from a task.

**Close:** every task ends with `Close: standard (test: <path>)` — the four steps of the index's `### Standard task close`; a task spells out only its deviations.

### Task V193-1: Worktree; shared plan-document parser `plan_doc.py`
**Model:** sonnet — a new side-effect-free module with its tests; every function's contract is pinned in the ledger and the tests below.

**Files:**
- Create: `scripts/dev/plan_doc.py`
- Create: `tests/dev/test_plan_doc.py`

**Interfaces:**
- Consumes: nothing (standard library only).
- Produces (ledger row V193-1; V193-5 and V193-6 import these names, never re-implement them):
  - `backticked(cell: str) -> list[str]` — the stripped contents of every `` `…` `` span, empty spans dropped.
  - `sections(text: str, level: int = 2) -> dict[str, str]` — heading text → the section text including its heading line, up to the next heading of the same or higher level (fewer or equal `#`). Lines inside ```` ``` ```` fences are never headings. First occurrence wins on a duplicate heading. Each value ends with exactly one `\n`.
  - `ledger_rows(text: str) -> list[dict[str, str]]` — the table under `## Task ledger`, one dict per body row keyed by the stripped header cells; the separator row is skipped; `\|` inside a cell does not split and is unescaped to `|`; a short row is padded with `""`.
  - `spec_refs(cell: str) -> list[str]` — split on `;` and `,`, strip whitespace and a leading `§`, drop empty and dash cells (`—`, `–`, `-`).
  - `resolve_ref(ref: str, headings: list[str]) -> str | None` — the heading equal to `ref`, else the first heading starting with `ref + "."` or `ref + " "`, else `None`.
  - `spec_path(index: Path, index_text: str) -> Path | None` — the target of the `**Spec:**` line (markdown link or backticked path, `#anchor` dropped), tried against the index's folder, then repo-relative (cwd); the first existing file, resolved, else `None`.
  - `symbol_name(token: str) -> str` — see Step 4.
  - Constants `COL_TASK = "Task"`, `COL_PART = "Part"`, `COL_SPEC = "Spec §"`, `COL_FILES = "Files created / modified"`, `COL_CREATES = "Creates"`, `COL_CONSUMES = "Consumes"` (the exact ledger header cells in the index's Architecture).
  - The worktree and branch `2026-10-25-v193-plan-writer-pipeline`.

Importing: `plan_lint.py` and `plan_slice.py` (later tasks) do `sys.path.insert(0, str(Path(__file__).resolve().parent))` then `import plan_doc`. Tests load the module by path (pattern below), never via `sys.path`.

- [ ] **Step 1: Create the worktree** (skill `worktree-lifecycle`; run from the main tree)

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git worktree add .claude/worktrees/2026-10-25-v193-plan-writer-pipeline -b 2026-10-25-v193-plan-writer-pipeline main
git -C .claude/worktrees/2026-10-25-v193-plan-writer-pipeline log --oneline -1
```

Expected: the new branch at `main`'s HEAD (the v193 plan commits or later). Every command from here on runs inside that worktree.

- [ ] **Step 2: Write the failing tests** — `tests/dev/test_plan_doc.py`

```python
"""plan_doc: the one markdown/ledger parser plan_lint.py and plan_slice.py share (v193)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("plan_doc", ROOT / "scripts" / "dev" / "plan_doc.py")
plan_doc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plan_doc)

LEDGER = (
    "# v900 Demo\n\n## Goal\n\nWhy.\n\n## Task ledger\n\n"
    "| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "| V900-1 | Parser | 1 | sonnet | C | C `scripts/dev/x.py` | `f(x) -> Path \\| None`; `K = 1` | — |\n"
    "| V900-2 | Use it | 2 | haiku | A; § Model tier | M `scripts/dev/x.py` | — | `f` |\n"
    "| V900-3 | Short |\n"
    "\n## After\n\ntext\n"
)


def test_backticked():
    assert plan_doc.backticked("C `a/b.py`, `c.py`, ` d ` and ` `") == ["a/b.py", "c.py", "d"]
    assert plan_doc.backticked("no ticks") == []


def test_sections_level2_stops_at_same_or_higher_and_skips_fences():
    text = ("# Title\n\n## A. One\n\nbody\n\n```bash\n# not a heading\n## nor this\n```\n\n"
            "### Sub\n\nsub body\n\n## B\n\nb body\n\n# Phase 2\n\n## C\n")
    got = plan_doc.sections(text)
    assert list(got) == ["A. One", "B", "C"]
    assert got["A. One"].startswith("## A. One\n")
    assert "# not a heading" in got["A. One"] and "sub body" in got["A. One"]
    assert "## B" not in got["A. One"]
    assert got["B"] == "## B\n\nb body\n"
    assert got["C"] == "## C\n"


def test_sections_other_level_and_duplicate_heading():
    text = "## X\n\n### Sub\n\none\n\n### Sub\n\ntwo\n\n## Y\n"
    got = plan_doc.sections(text, level=3)
    assert got == {"Sub": "### Sub\n\none\n"}


def test_ledger_rows_keyed_by_header():
    rows = plan_doc.ledger_rows(LEDGER)
    assert [r[plan_doc.COL_TASK] for r in rows] == ["V900-1", "V900-2", "V900-3"]
    assert rows[1][plan_doc.COL_SPEC] == "A; § Model tier"
    assert rows[1][plan_doc.COL_FILES] == "M `scripts/dev/x.py`"
    assert rows[1][plan_doc.COL_CONSUMES] == "`f`"
    assert rows[2][plan_doc.COL_PART] == "" and rows[2][plan_doc.COL_CONSUMES] == ""


def test_ledger_rows_escaped_pipe():
    row = plan_doc.ledger_rows(LEDGER)[0]
    assert row[plan_doc.COL_CREATES] == "`f(x) -> Path | None`; `K = 1`"
    assert row[plan_doc.COL_CONSUMES] == "—"


def test_ledger_rows_empty_when_no_ledger_or_no_table():
    assert plan_doc.ledger_rows("# v900\n\n## Goal\n\nx\n") == []
    assert plan_doc.ledger_rows("## Task ledger\n\nnone yet\n") == []


def test_spec_refs():
    assert plan_doc.spec_refs("A; § Model tier, C") == ["A", "Model tier", "C"]
    assert plan_doc.spec_refs("§Testing") == ["Testing"]
    for empty in ("", "—", "-", " – "):
        assert plan_doc.spec_refs(empty) == []


HEADINGS = ["Why", "A. Split right the first time (agreed 2026-10-25)",
            "Model tier for prose parts", "Testing", "AB. Other"]


@pytest.mark.parametrize("ref, want", [
    ("Testing", "Testing"),
    ("A", "A. Split right the first time (agreed 2026-10-25)"),
    ("Model tier", "Model tier for prose parts"),
    ("AB", "AB. Other"),
    ("B", None),
    ("Test", None),
])
def test_resolve_ref(ref, want):
    assert plan_doc.resolve_ref(ref, HEADINGS) == want


def test_spec_path_link_relative_backticked_and_missing(tmp_path, monkeypatch):
    plans, specs = tmp_path / "plans", tmp_path / "specs"
    plans.mkdir()
    specs.mkdir()
    (specs / "s.md").write_text("# s\n", encoding="utf-8")
    index = plans / "i.md"
    link = "**Bump:** none\n**Spec:** [s.md](../specs/s.md#why)\n"
    assert plan_doc.spec_path(index, link) == (specs / "s.md").resolve()
    monkeypatch.chdir(tmp_path)
    assert plan_doc.spec_path(index, "**Spec:** `specs/s.md`\n") == (specs / "s.md").resolve()
    assert plan_doc.spec_path(index, "**Spec:** [x](../specs/gone.md)\n") is None
    assert plan_doc.spec_path(index, "no spec line\n") is None


@pytest.mark.parametrize("token, want", [
    ("backticked(cell: str) -> list[str]", "backticked"),
    ("plan_lint.plan_number", "plan_number"),
    ("tests/dev/test_x.py::test_a", "tests/dev/test_x.py::test_a"),
    ("scripts/dev/plan_slice.py <index> <part>", "scripts/dev/plan_slice.py"),
    ("--ledger <index>", "--ledger"),
    ("--stats", "--stats"),
    ("COMMANDS: dict[str, Callable[[list[str]], int]]", "COMMANDS"),
    ("NEW_RULES_FROM = 194", "NEW_RULES_FROM"),
    ("mod::Cls.method(x)", "method"),
    ("f(x) -> Path | None", "f"),
    ("  ", ""),
])
def test_symbol_name(token, want):
    assert plan_doc.symbol_name(token) == want


def test_real_v193_index_ledger_resolves_against_its_spec():
    index = ROOT / "docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md"
    text = index.read_text(encoding="utf-8")
    rows = plan_doc.ledger_rows(text)
    assert [r[plan_doc.COL_TASK] for r in rows][:2] == ["V193-1", "V193-2"]
    spec = plan_doc.spec_path(index, text)
    assert spec is not None and spec.name == "2026-10-25-v193-plan-writer-pipeline.md"
    headings = list(plan_doc.sections(spec.read_text(encoding="utf-8")))
    for row in rows:
        for ref in plan_doc.spec_refs(row[plan_doc.COL_SPEC]):
            assert plan_doc.resolve_ref(ref, headings), (row[plan_doc.COL_TASK], ref)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_doc.py`
Expected: collection error — `FileNotFoundError` for `scripts/dev/plan_doc.py`.

- [ ] **Step 4: Implement `scripts/dev/plan_doc.py`**

```python
"""Side-effect-free parsing of plan and spec markdown (v193).

One parser for plan_lint.py (--ledger) and plan_slice.py: ledger rows keyed
by header cell, ## sections, backticked tokens, Spec § references and the
symbol name a ledger token stands for. Import with scripts/dev on sys.path.
"""
from __future__ import annotations

import re
from pathlib import Path

COL_TASK = "Task"
COL_PART = "Part"
COL_SPEC = "Spec §"
COL_FILES = "Files created / modified"
COL_CREATES = "Creates"
COL_CONSUMES = "Consumes"

BACKTICK_RE = re.compile(r"`([^`]+)`")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}")
SPEC_LINE_RE = re.compile(r"^\*\*Spec:\*\*\s*(?:\[[^\]]*\]\(([^)]+)\)|`([^`]+)`)", re.M)
REF_SPLIT_RE = re.compile(r"[;,]")
SYMBOL_SPLIT_RE = re.compile(r"::|\.")
NO_REF = {"", "—", "–", "-"}


def backticked(cell: str) -> list[str]:
    return [t.strip() for t in BACKTICK_RE.findall(cell) if t.strip()]


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, text) of every heading outside fenced code."""
    found, fenced = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else HEADING_RE.match(line)
        if m:
            found.append((i, len(m.group(1)), m.group(2)))
    return found


def sections(text: str, level: int = 2) -> dict[str, str]:
    lines = text.splitlines()
    heads = _headings(lines)
    out: dict[str, str] = {}
    for k, (i, lvl, title) in enumerate(heads):
        if lvl != level or title in out:
            continue
        end = next((j for j, other, _ in heads[k + 1:] if other <= level), len(lines))
        out[title] = "\n".join(lines[i:end]).rstrip() + "\n"
    return out


def _cells(line: str) -> list[str]:
    cells = CELL_SPLIT_RE.split(line.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.replace("\\|", "|").strip() for c in cells]


def ledger_rows(text: str) -> list[dict[str, str]]:
    section = sections(text).get("Task ledger", "")
    table = [line for line in section.splitlines() if line.lstrip().startswith("|")]
    if not table:
        return []
    header = _cells(table[0])
    rows = []
    for line in table[1:]:
        if SEPARATOR_RE.match(line.strip()):
            continue
        cells = _cells(line)
        rows.append({h: cells[k] if k < len(cells) else "" for k, h in enumerate(header)})
    return rows


def spec_refs(cell: str) -> list[str]:
    refs = [part.strip().lstrip("§").strip() for part in REF_SPLIT_RE.split(cell)]
    return [r for r in refs if r not in NO_REF]


def resolve_ref(ref: str, headings: list[str]) -> str | None:
    if ref in headings:
        return ref
    return next((h for h in headings if h.startswith((ref + ".", ref + " "))), None)


def spec_path(index: Path, index_text: str) -> Path | None:
    m = SPEC_LINE_RE.search(index_text)
    if not m:
        return None
    target = (m.group(1) or m.group(2)).split("#", 1)[0].strip()
    for candidate in (index.parent / target, Path(target)):
        if candidate.is_file():
            return candidate.resolve()
    return None


def symbol_name(token: str) -> str:
    """The name a ledger token stands for: a repo path (contains '/') or a
    flag (starts with '-') as its first word; otherwise the last '.'/'::'
    segment of the first word before any '(' with a trailing ':' dropped."""
    words = token.split("(", 1)[0].split()
    if not words:
        return ""
    first = words[0]
    if "/" in first or first.startswith("-"):
        return first
    return SYMBOL_SPLIT_RE.split(first.rstrip(":"))[-1]
```

`tests/dev/test_x.py::test_a` keeps its `::test_a` because the `/` branch returns before the segment split, as the test pins. `_cells` drops only the empty edge cells the outer pipes produce, so an empty interior cell stays `""`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_doc.py`
Expected: all pass, `0 failed`, `0 xfailed`. If `test_real_v193_index_ledger_resolves_against_its_spec` fails on a ref, the index's `Spec §` cell is wrong — report it to the controller (a shared contract); do not edit the index from this task.

- [ ] **Step 6: Complexity spot check**

Run: `python -m radon cc -s scripts/dev/plan_doc.py`
Expected: every function grade A or B (all < 15).

Close: standard (test: tests/dev/test_plan_doc.py) — commit `feat(v193): shared plan-document parser plan_doc.py (V193-1)`.

### Task V193-2: Per-task lint checks: `Close:` line, task ceiling, `Modify:` range (from v194)
**Model:** sonnet — three small checks wired into the existing scan loop, gated by plan number like `needs_model`; the regexes and messages are pinned below.

**Files:**
- Modify: `scripts/dev/plan_lint.py:1-32` (docstring, constants), `:106-121` (`scan_file`), `:141-150` (`lint`)
- Modify: `tests/dev/test_plan_lint.py:14` (`TASK`), `:45-49` (`test_created_earlier_then_modified_is_fine`), append new tests

**Interfaces:**
- Consumes: `plan_lint.plan_number(files)` (`scripts/dev/plan_lint.py:43`), `plan_lint.scan_file(path, ctx)` (`:106`), `TASK_RE`, `PATH_RE`, `check_paths`, `record_task`, `check_model_line` (all existing).
- Produces (ledger row V193-2):
  - `NEW_RULES_FROM = 194`, `TASK_CEILING = 400`, `CLOSE_RE`, `MODIFY_RANGE_RE` (module constants).
  - `task_spans(lines: list[str]) -> list[tuple[str, int, int]]` — `(task id, start index, end index exclusive)` per `### Task` line; a task runs to the next `### Task` line or EOF. V193-3 (`task_line_counts`) and V193-4 (`parts_table`) reuse it; it is the one definition of "task length".
  - `check_task_body(name: str, task: str, body: list[str]) -> list[str]`
  - `check_modify_range(name: str, line: str, created: set[str]) -> list[str]`
  - `scan_line(name: str, lines: list[str], i: int, ctx: dict) -> list[str]` (private to this file; split out of `scan_file` to keep it < 15).
  - ctx key `new_rules: bool` (= `plan_number(files) >= NEW_RULES_FROM`).
  - Problem messages (later docs quote them): `"<file>: Task <id> -- no Close: line (index ### Standard task close)"`, `"<file>: Task <id> -- <n> lines (ceiling 400) -- split into two tasks, never compress"`, ``"<file>: Modify `<path>:<a>-<b>` ends past line <n> of the file"``.

Rules the tests pin (Review Focus 1 and 2):
- A plan numbered below 194 lints exactly as today: no `Close:`, ceiling or range check.
- A `Close:` line is any body line matching `CLOSE_RE`: `Close: …`, `**Close:** …`, or either behind a list marker / checkbox (`- `, `- [ ] `). Its position in the task is not checked.
- The ceiling counts the task's lines from its `### Task` line (inclusive) to the next `### Task` line or EOF (exclusive); `400` passes, `401` fails.
- `Modify:` range variants: `` `path` `` (no range) → no range check; `` `path:120` `` → end 120; `` `path:120-180 (fn)` `` and `` `path:120-180` (fn) `` → end 180; a path created by an earlier task (`created`) or not on disk → no length check (`check_paths` already reports a missing path). The length is `len(read_text(...).splitlines())`.

- [ ] **Step 1: Write the failing tests** — `tests/dev/test_plan_lint.py`

Old → new, line 14 (existing fixtures gain a `Close:` line so they keep passing under v900 > 194; Review Focus 1):

```python
TASK = "### Task {id}: t\n\n**Model:** sonnet — mechanical\n\n- Modify: `bot.py`\n\n"
```
```python
TASK = ("### Task {id}: t\n\n**Model:** sonnet — mechanical\n\n- Modify: `bot.py`\n\n"
        "Close: standard (test: tests/dev/test_x.py)\n\n")
```

Old → new, lines 46-47 (inside `test_created_earlier_then_modified_is_fine`):

```python
    body = (HEADER + "### Task V900-1: t\n\n**Model:** haiku — docs\n\n- Create: `new/mod.py`\n\n"
            + "### Task V900-2: t\n\n**Model:** sonnet — code\n\n- Modify: `new/mod.py`\n")
```
```python
    body = (HEADER + "### Task V900-1: t\n\n**Model:** haiku — docs\n\n- Create: `new/mod.py`\n\n"
            + "Close: standard (test: tests/dev/test_x.py)\n\n"
            + "### Task V900-2: t\n\n**Model:** sonnet — code\n\n- Modify: `new/mod.py`\n\n"
            + "**Close:** standard (test: tests/dev/test_x.py)\n")
```

Append at the end of the file:

```python
CLOSE = "Close: standard (test: tests/dev/test_x.py)"


def _task(task_id: str, n_lines: int, *, close: str | None = CLOSE,
          modify: tuple[str, ...] = ("`bot.py`",)) -> str:
    """A task exactly n_lines long, its ### Task line included."""
    lines = [f"### Task {task_id}: t", "", "**Model:** sonnet — mechanical", ""]
    lines += [f"- Modify: {m}" for m in modify] + [""]
    if close:
        lines.append(close)
    lines += ["x"] * (n_lines - len(lines))
    return "\n".join(lines) + "\n"


def _bot_py_lines() -> int:
    return len((ROOT / "bot.py").read_text(encoding="utf-8").splitlines())


def test_v192_plan_skips_new_rules(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-24-v192-demo_0-index.md": HEADER,
        "2026-10-24-v192-demo_1-a.md": _task("V900-1", 709, close=None,
                                             modify=("`bot.py:1-999999`",)),
        "2026-10-24-v192-demo_2-b.md": _task("V900-2", 20, close=None),
    })
    assert code == 0, out
    assert "PLAN LINT: PASS  3 file(s)" in out


def test_new_rules_close_line_and_ceiling(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-25-v900-demo_0-index.md": HEADER,
        "2026-10-25-v900-demo_1-a.md": _task("V900-1", 401),
        "2026-10-25-v900-demo_2-b.md": _task("V900-2", 400, close=None),
    })
    assert code == 1
    assert "Task V900-1 -- 401 lines (ceiling 400) -- split into two tasks" in out
    assert "Task V900-2 -- no Close: line" in out
    assert "V900-2 -- 400 lines" not in out
    assert "V900-1 -- no Close: line" not in out


def test_close_line_variants_pass(tmp_path):
    code, out = _lint(tmp_path, {
        "2026-10-25-v900-demo_0-index.md": HEADER,
        "2026-10-25-v900-demo_1-a.md": _task("V900-1", 30, close="**Close:** standard (test: t.py)"),
        "2026-10-25-v900-demo_2-b.md": _task("V900-2", 30, close="- [ ] Close: standard; no commit"),
    })
    assert code == 0, out


def test_modify_range_variants(tmp_path):
    n = _bot_py_lines()
    first = ("### Task V900-1: t\n\n**Model:** sonnet — code\n\n- Create: `new/mod.py`\n\n"
             f"{CLOSE}\n\n")
    second = _task("V900-2", 30, modify=(
        "`bot.py`", "`bot.py:1`", f"`bot.py:1-{n} (main)`", f"`bot.py:1-{n}` (main)",
        "`new/mod.py:120-180` (created by V900-1)"))
    code, out = _lint(tmp_path, {"2026-10-25-v900-demo.md": HEADER + first + second})
    assert code == 0, out


def test_modify_range_past_end_fails(tmp_path):
    n = _bot_py_lines()
    body = HEADER + _task("V900-1", 30) + _task("V900-2", 30, modify=(f"`bot.py:{n}-{n + 1}` (main)",))
    code, out = _lint(tmp_path, {"2026-10-25-v900-demo.md": body})
    assert code == 1
    assert f"Modify `bot.py:{n}-{n + 1}` ends past line {n} of the file" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint.py`
Expected: `test_new_rules_close_line_and_ceiling` and `test_modify_range_past_end_fails` FAIL (no such problems reported yet); the other seven pass.

- [ ] **Step 3: Implement in `scripts/dev/plan_lint.py`**

Docstring: insert two bullets after the last bullet of the checks list (line 14, the placeholder bullet), before the blank line:

```python
  * plans from v194 (NEW_RULES_FROM): every task has a Close: line, no task runs
    over TASK_CEILING (400) lines, every `Modify: path:a-b` range ends inside the file
```

Constants: insert after line 32 (`PART_SUFFIX_RE = …`):

```python
NEW_RULES_FROM = 194
TASK_CEILING = 400
CLOSE_RE = re.compile(r"^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?)?(?:\*\*)?Close:(?:\*\*)?\s*\S")
MODIFY_RANGE_RE = re.compile(r"^- Modify:\s*`([^`:]+):(\d+)(?:-(\d+))?")
```

New functions, inserted after `check_paths` (line 103):

```python
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
```

`scan_file` (lines 106-120), old → new — the per-line body moves into `scan_line` unchanged in order (task, model, paths, placeholder), with the range check after `check_paths` so a `Create:` on an earlier line is already in `created`; the per-task checks run once per file after the loop:

```python
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
```
```python
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
```

`lint` (lines 144-145), old → new:

```python
    ctx = {"tasks": [], "created": set(), "tracked": tracked_paths(),
           "needs_model": plan_number(files) > 145}
```
```python
    number = plan_number(files)
    ctx = {"tasks": [], "created": set(), "tracked": tracked_paths(),
           "needs_model": number > 145, "new_rules": number >= NEW_RULES_FROM}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint.py`
Expected: 9 passed, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Old plans still lint as before**

Run:
```bash
python scripts/dev/plan_lint.py docs/superpowers/plans/2026-10-24-v192-gap-toward-stop-reclaim_0-index.md
python scripts/dev/plan_lint.py docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md
```
Expected: both print `PLAN LINT: PASS` (v192 has 709-line tasks and no `Close:` lines; v193 is below `NEW_RULES_FROM`). If either plan has moved to `plans/implemented/`, run it from there.

Close: standard (test: tests/dev/test_plan_lint.py) — commit `feat(v193): plan_lint per-task checks -- Close: line, task ceiling, Modify: range, from v194 (V193-2)`.

### Task V193-3: `plan_lint.py --stats` and the `COMMANDS` flag dispatch
**Model:** sonnet — a table-driven dispatch replacing a 6-line `main` plus one read-only statistics command; the grouping, ordering and percentile rules are pinned below.

**Files:**
- Modify: `scripts/dev/plan_lint.py` (imports, constants, `main`; as left by V193-2)
- Create: `tests/dev/test_plan_lint_stats.py`

**Interfaces:**
- Consumes: `task_spans(lines)` (V193-2), `plan_lint.plan_files`, `PART_SUFFIX_RE`, `lint` (existing).
- Produces (ledger row V193-3):
  - `COMMANDS: dict[str, Callable[[list[str]], int]]` — flag → handler taking the arguments after the flag. V193-4 adds `"--fix-parts"`, V193-5 adds `"--ledger"`, each as one dict entry plus one `USAGE` line; `main` never grows.
  - `cmd_lint(args: list[str]) -> int` — today's `main` body for `args == [file]`; exit 0/1, 2 with `USAGE` on bad arguments.
  - `cmd_stats(args: list[str]) -> int` — `--stats [dir]`.
  - `recent_plans(directory: Path, n: int = 5) -> list[list[Path]]` — newest first.
  - `task_line_counts(files: list[Path]) -> list[int]` — `end - start` of every `task_spans` entry, file by file.
  - `plan_stats(directory: Path, n: int = 5) -> dict[str, int]` — keys `plans`, `tasks`, `median`, `p90`, `per_part`.
  - `STATS_DIR = Path("docs/superpowers/plans/implemented")` (cwd-relative, like `tracked_paths`), `PART_BUDGET = 1400`, `DATED_PLAN_RE`, `USAGE`.
  - Output (V193-7's agent text quotes it): `PLAN STATS: <plans> plan(s), <tasks> task(s) -- median <m>, p90 <p> lines/task; <k> task(s) per part at p90 (budget 1400)`; with no tasks found: `PLAN STATS: no dated plan with ### Task headings under <dir>` and exit 1.

Rules the tests pin:
- A plan is a group of `*.md` files in `directory` sharing a base name (`PART_SUFFIX_RE` stripped), counted only when the name starts `YYYY-MM-DD-v<N>-` (`DATED_PLAN_RE`); undated files (`v32-…md`) are ignored. Groups sort by `(date, N)` descending; groups with no `### Task` heading are skipped **without taking a slot**; the first `n` remaining are returned, each group's files sorted.
- `median = int(statistics.median(counts))` (truncates `.5`); `p90` is nearest-rank: `sorted(counts)[ceil(0.9 * len) - 1]`; `per_part = max(1, PART_BUDGET // p90)`; with no tasks every key is `0`.
- The v192 calibration (26 tasks, brief) gives `median 306, p90 522, per_part 2`.
- `main`: an `argv[1]` in `COMMANDS` dispatches with `argv[2:]`; anything else (including an unknown flag such as `--bogus`) goes to `cmd_lint(argv[1:])`, which prints `USAGE` and exits 2 when it is not exactly one existing file. `USAGE` replaces today's `__doc__.strip().splitlines()[3]` print (which printed an empty line).

- [ ] **Step 1: Write the failing tests** — `tests/dev/test_plan_lint_stats.py`

```python
"""plan_lint --stats: measured lines per task over the newest plans (v193)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"

# v192 measured task sizes (2026-10-24-v192-*, 26 tasks)
V192_SIZES = [288, 364, 153, 497, 236, 522, 242, 709, 202, 393, 313, 232, 379,
              446, 495, 428, 449, 693, 202, 168, 274, 235, 300, 175, 380, 153]


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, cwd=ROOT, timeout=120)
    return proc.returncode, proc.stdout


def _task(task_id: str, n_lines: int) -> str:
    """A task exactly n_lines long, its ### Task line included."""
    return "\n".join([f"### Task {task_id}: t", ""] + ["x"] * (n_lines - 2)) + "\n"


def _write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text, encoding="utf-8")


def _corpus(d: Path) -> None:
    _write(d, "v32-old-undated.md", _task("V32-1", 900))
    for k in range(1, 6):  # v801..v805 dated 2026-01-01..05, one task of 10*k lines
        _write(d, f"2026-01-0{k}-v80{k}-p.md", "# plan\n\n" + _task(f"V80{k}-1", 10 * k))
    _write(d, "2026-01-06-v806-split_0-index.md", "# index, no tasks\n")
    _write(d, "2026-01-06-v806-split_1-a.md", _task("V806-1", 60) + _task("V806-2", 70))
    _write(d, "2026-01-07-v807-notasks.md", "# newest, but no ### Task headings\n")


def test_stats_newest_five_dated_plans_with_tasks(tmp_path):
    _corpus(tmp_path)
    code, out = _run("--stats", str(tmp_path))
    assert code == 0, out
    # v807 has no tasks (skipped, takes no slot); v801 is the sixth-newest; v32 is undated
    assert out.strip() == ("PLAN STATS: 5 plan(s), 6 task(s) -- median 45, p90 70 lines/task; "
                           "20 task(s) per part at p90 (budget 1400)")


def test_stats_matches_v192_calibration(tmp_path):
    body = "".join(_task(f"V192-{k}", n) for k, n in enumerate(V192_SIZES, start=1))
    _write(tmp_path, "2026-10-24-v192-demo.md", "# v192\n\n" + body)
    code, out = _run("--stats", str(tmp_path))
    assert code == 0, out
    assert "1 plan(s), 26 task(s) -- median 306, p90 522 lines/task; 2 task(s) per part" in out


def test_stats_no_dated_plan_with_tasks(tmp_path):
    _write(tmp_path, "v32-old.md", _task("V32-1", 50))
    _write(tmp_path, "2026-01-07-v807-notasks.md", "# no tasks\n")
    code, out = _run("--stats", str(tmp_path))
    assert code == 1
    assert "PLAN STATS: no dated plan with ### Task headings under" in out


def test_stats_bad_arguments_print_usage(tmp_path):
    for args in (("--stats", str(tmp_path / "missing")), ("--stats", str(tmp_path), "extra")):
        code, out = _run(*args)
        assert code == 2, args
        assert "usage:" in out and "--stats [dir]" in out


def test_unknown_flag_and_no_argument_fall_back_to_lint_usage():
    for args in (("--bogus",), ()):
        code, out = _run(*args)
        assert code == 2, args
        assert "usage:" in out


def test_stats_real_corpus_defaults_to_implemented():
    code, out = _run("--stats")
    assert code == 0, out
    assert out.startswith("PLAN STATS: 5 plan(s), ")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_stats.py`
Expected: all six FAIL (`--stats` is read as a plan path and prints the docstring's empty line; no `usage:` text yet).

- [ ] **Step 3: Implement in `scripts/dev/plan_lint.py`**

Docstring: after the `python scripts/dev/plan_lint.py docs/superpowers/plans/<any file of the plan>` line add

```python
    python scripts/dev/plan_lint.py --stats [dir]   # median/p90 lines per task, newest 5 plans
```

Imports, old → new:

```python
import re
import subprocess
import sys
from pathlib import Path
```
```python
import math
import re
import statistics
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
```

Constants: append after `MODIFY_RANGE_RE` (V193-2):

```python
STATS_DIR = Path("docs/superpowers/plans/implemented")
PART_BUDGET = 1400
DATED_PLAN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-v(\d+)-")
USAGE = """usage:
  python scripts/dev/plan_lint.py <any file of a plan>   lint the whole plan
  python scripts/dev/plan_lint.py --stats [dir]          lines per task, newest 5 plans in dir (default plans/implemented)"""
```

`main` (the last function), old → new: today's body becomes `cmd_lint`; the statistics helpers and `COMMANDS` sit between `lint` and `main`:

```python
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
```
```python
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


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "--stats": cmd_stats,
}


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in COMMANDS:
        return COMMANDS[argv[1]](argv[2:])
    return cmd_lint(argv[1:])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_stats.py` and `python scripts/dev/testrun.py file tests/dev/test_plan_lint.py`
Expected: 6 passed and 9 passed, `0 failed`, `0 xfailed` (the lint path is unchanged).

- [ ] **Step 5: Real corpus**

Run: `python scripts/dev/plan_lint.py --stats`
Expected: one `PLAN STATS: 5 plan(s), …` line, exit 0. Quote the line in the task's report — V193-7 and the controller use the measured p90.

Close: standard (test: tests/dev/test_plan_lint_stats.py) — also run `tests/dev/test_plan_lint.py` in close step 2; commit `feat(v193): plan_lint --stats and the COMMANDS flag dispatch (V193-3)`.

### Task V193-4: `plan_lint.py --fix-parts <index>` regenerates the parts table
**Model:** sonnet — one surgical file rewrite (only the `## Parts` table) with idempotence and scope preservation pinned by tests.

**Files:**
- Modify: `scripts/dev/plan_lint.py` (constants, `USAGE`, `COMMANDS`; as left by V193-3)
- Create: `tests/dev/test_plan_lint_fix_parts.py`

**Interfaces:**
- Consumes: `COMMANDS`, `USAGE` (V193-3), `task_spans(lines)` (V193-2), `plan_lint.plan_files` (existing).
- Produces (ledger row V193-4):
  - `parts_table(index: Path, old_scopes: dict[str, str]) -> list[str]` — the header row, the separator and one row per part file, as lines.
  - `fix_parts(index: Path) -> int` — rewrites the table in place; returns the number of part rows written, `-1` when the index has no `## Parts` heading.
  - `cmd_fix_parts(args: list[str]) -> int` — `--fix-parts <index>`.
  - `PART_LABEL_RE` (module constant).
  - Output (V193-7 and V193-8 quote it): `PARTS TABLE: <n> part(s) in <index name>` (exit 0); `PARTS TABLE: no ## Parts section in <index name>` (exit 1); `USAGE` and exit 2 on bad arguments.

Rules the tests pin (Review Focus 3):
- Part files are the plan's files (`plan_files(index)`) whose name matches `_<num><letter>-<slug>.md` with `num != 0`; rows order by `(int(num), letter)`, so `_1`, `_1b`, `_2`, …, `_10`.
- Row: `| <num><letter> | `<file name>` | <tasks> | <scope> |`. Tasks: `—` with no `### Task`, the id with one, `<first>..<last>` with more (ids in file order, from `task_spans`).
- Scope: the existing row's last cell for the same part label, kept raw (an escaped `\|` survives); a part with no existing row (a self-spill `_2b`) gets its slug with `-` → space.
- Only the table changes: the `## Parts` section is the lines from `## Parts` to the next `#`/`##` heading; the table is the first through last line starting with `|` inside it. No table → one blank line plus the table are inserted right after the heading. Everything else is byte-identical; the file is written only when the text changed, with `\n` line endings.
- A second run leaves the index byte-identical.

- [ ] **Step 1: Write the failing tests** — `tests/dev/test_plan_lint_fix_parts.py`

```python
"""plan_lint --fix-parts: the index's parts table is generated, never hand-edited (v193)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"
BASE = "2026-10-25-v900-demo"

BEFORE = "# v900 Demo\n\n**Bump:** none\n\n## Goal\n\nWhy.\n\n"
PARTS = ("## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
         "| 1 | `old-name.md` | V900-1 | alpha \\| beta |\n"
         f"| 2 | `{BASE}_2-second.md` | V900-9 | gamma |\n\n")
AFTER = "## Task ledger\n\n| Task | Title |\n|---|---|\n| V900-1 | a |\n"


def _task(task_id: str) -> str:
    return f"### Task {task_id}: t\n\nbody\n\n"


def _plan(d: Path, index_text: str, parts: dict[str, str]) -> Path:
    index = d / f"{BASE}_0-index.md"
    index.write_text(index_text, encoding="utf-8")
    for suffix, text in parts.items():
        (d / f"{BASE}_{suffix}.md").write_text(text, encoding="utf-8")
    return index


def _run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


SPLIT = {"1-first": _task("V900-1") + _task("V900-2"),
         "1b-spill-over": _task("V900-3"),
         "2-second": _task("V900-4")}


def test_fix_parts_regenerates_table_and_keeps_scopes(tmp_path):
    index = _plan(tmp_path, BEFORE + PARTS + AFTER, SPLIT)
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert f"PARTS TABLE: 3 part(s) in {index.name}" in out
    want = ("## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
            f"| 1 | `{BASE}_1-first.md` | V900-1..V900-2 | alpha \\| beta |\n"
            f"| 1b | `{BASE}_1b-spill-over.md` | V900-3 | spill over |\n"
            f"| 2 | `{BASE}_2-second.md` | V900-4 | gamma |\n\n")
    assert index.read_bytes().decode("utf-8") == BEFORE + want + AFTER


def test_fix_parts_idempotent(tmp_path):
    index = _plan(tmp_path, BEFORE + PARTS + AFTER, SPLIT)
    assert _run("--fix-parts", str(index))[0] == 0
    first = index.read_bytes()
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert index.read_bytes() == first


def test_fix_parts_inserts_table_under_an_empty_section(tmp_path):
    index = _plan(tmp_path, BEFORE + "## Parts\n\n" + AFTER, {"1-only": _task("V900-1")})
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    assert index.read_text(encoding="utf-8") == (
        BEFORE + "## Parts\n\n| Part | File | Tasks | Scope |\n|---|---|---|---|\n"
        f"| 1 | `{BASE}_1-only.md` | V900-1 | only |\n\n" + AFTER)
    first = index.read_bytes()
    assert _run("--fix-parts", str(index))[0] == 0
    assert index.read_bytes() == first


def test_fix_parts_numeric_order_and_part_without_tasks(tmp_path):
    index = _plan(tmp_path, BEFORE + "## Parts\n\n" + AFTER,
                  {"10-ten": "# no tasks yet\n", "2-two": _task("V900-1")})
    code, out = _run("--fix-parts", str(index))
    assert code == 0, out
    text = index.read_text(encoding="utf-8")
    two = text.index(f"| 2 | `{BASE}_2-two.md` | V900-1 | two |")
    ten = text.index(f"| 10 | `{BASE}_10-ten.md` | — | ten |")
    assert two < ten


def test_fix_parts_without_parts_section(tmp_path):
    index = _plan(tmp_path, BEFORE + AFTER, SPLIT)
    code, out = _run("--fix-parts", str(index))
    assert code == 1
    assert f"PARTS TABLE: no ## Parts section in {index.name}" in out
    assert index.read_text(encoding="utf-8") == BEFORE + AFTER


def test_fix_parts_bad_arguments(tmp_path):
    for args in (("--fix-parts",), ("--fix-parts", str(tmp_path / "missing.md"))):
        code, out = _run(*args)
        assert code == 2, args
        assert "--fix-parts <index>" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_fix_parts.py`
Expected: all six FAIL (`--fix-parts` falls through to `cmd_lint`, which prints `USAGE` without a `--fix-parts` line and exits 2).

- [ ] **Step 3: Implement in `scripts/dev/plan_lint.py`**

Docstring: after the `--stats [dir]` usage line (V193-3) add

```python
    python scripts/dev/plan_lint.py --fix-parts <index>   # regenerate the index's ## Parts table
```

Constants: add after `DATED_PLAN_RE` (V193-3)

```python
PART_LABEL_RE = re.compile(r"_(\d+)([a-z]?)-([^.]*)\.md$")
PARTS_END_RE = re.compile(r"#{1,2} ")
```

`USAGE`: append one line inside the string (after the `--stats` line)

```python
  python scripts/dev/plan_lint.py --fix-parts <index>    regenerate the index's ## Parts table from the part files
```

New functions, inserted after `cmd_stats` (before `cmd_lint`):

```python
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


def parts_table(index: Path, old_scopes: dict[str, str]) -> list[str]:
    rows = ["| Part | File | Tasks | Scope |", "|---|---|---|---|"]
    for label, slug, path in _part_files(index):
        scope = old_scopes.get(label) or slug.replace("-", " ")
        rows.append(f"| {label} | `{path.name}` | {_task_range(path)} | {scope} |")
    return rows


def _old_scopes(table: list[str]) -> dict[str, str]:
    """Part label -> raw Scope cell of an existing parts table (header and separator skipped)."""
    scopes = {}
    for line in table[2:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if len(cells) >= 4:
            scopes[cells[0]] = cells[-1]
    return scopes


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
    table = parts_table(index, _old_scopes(lines[start:end]))
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
```

`COMMANDS`, old → new:

```python
COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "--stats": cmd_stats,
}
```
```python
COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "--stats": cmd_stats,
    "--fix-parts": cmd_fix_parts,
}
```

Why `split("\n")`/`"\n".join` rather than `splitlines()`: it keeps the trailing newline and every blank line exactly, which is what makes the rewrite byte-identical outside the table.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_fix_parts.py`, then `tests/dev/test_plan_lint_stats.py` and `tests/dev/test_plan_lint.py`
Expected: 6, 6 and 9 passed, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Dogfood on this plan, read-only**

Copy the v193 plan files to a scratch folder and run the command there — never on the committed index from a task:

```bash
mkdir -p "$TMP/v193-parts" && cp docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_*.md "$TMP/v193-parts/"
python scripts/dev/plan_lint.py --fix-parts "$TMP/v193-parts/2026-10-25-v193-plan-writer-pipeline_0-index.md"
diff docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md "$TMP/v193-parts/2026-10-25-v193-plan-writer-pipeline_0-index.md"
```

Expected: `PARTS TABLE: <n> part(s) in …`; the diff touches only `## Parts` rows (none, if the committed table already matches the part files on `main`). Report any diff to the controller; the index is fixed on `main`, not in the worktree.

Close: standard (test: tests/dev/test_plan_lint_fix_parts.py) — also run `tests/dev/test_plan_lint_stats.py` and `tests/dev/test_plan_lint.py` in close step 2; commit `feat(v193): plan_lint --fix-parts regenerates the index parts table (V193-4)`.

