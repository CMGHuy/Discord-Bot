# v193 — Plan-writer pipeline, part 2: ledger check, slice, agents, docs, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V193-6:" -A 300 <this file>`.

**Spec:** [2026-10-25-v193-plan-writer-pipeline.md](../../specs/implemented/2026-10-25-v193-plan-writer-pipeline.md)
**Index:** [2026-10-25-v193-plan-writer-pipeline_0-index.md](2026-10-25-v193-plan-writer-pipeline_0-index.md) — Global Constraints, `### Standard task close`, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V193-5..V193-9. Every task runs in the worktree
`.claude/worktrees/2026-10-25-v193-plan-writer-pipeline`; V193-9 merges it.

# Phase 2 — Contracts and slice

### Task V193-5: `plan_lint.py --ledger <index>` contract check

**Model:** sonnet — a normal TDD task inside one script, behaviour fixed by the spec and the ledger.

Spec § C: after `mode=index`, before any part is dispatched, every consumed
symbol exists (`git grep`) or is created by an earlier ledger row, no row
consumes a symbol from a later row, and every `Spec §` resolves to a heading.

**Files:**
- Modify: `scripts/dev/plan_lint.py` (as left by V193-4: `import plan_doc`; one docstring line and one `USAGE` line; new helpers and `cmd_ledger` above `COMMANDS`; one `COMMANDS` entry)
- Create: `tests/dev/test_plan_lint_ledger.py`

**Interfaces:**
- Consumes (V193-1, `scripts/dev/plan_doc.py`): `ledger_rows(text) -> list[dict[str, str]]`, `sections(text, level) -> dict[str, str]`, `spec_refs(cell) -> list[str]`, `resolve_ref(ref, headings) -> str | None`, `spec_path(index, index_text) -> Path | None`, `backticked(cell) -> list[str]`, `symbol_name(token) -> str`, `COL_TASK`, `COL_SPEC`, `COL_FILES`, `COL_CREATES`, `COL_CONSUMES`.
- Consumes (V193-3): `COMMANDS: dict[str, Callable[[list[str]], int]]` — `main(argv)` calls `COMMANDS[argv[1]](argv[2:])` when `argv[1]` is a key, and sends anything else (an unknown flag included) to `cmd_lint`, exit 2; `USAGE` (the multi-line usage string every handler prints on bad arguments). Existing `tracked_paths()` (`scripts/dev/plan_lint.py:48`).
- Produces: `cmd_ledger(args: list[str]) -> int` (0 PASS, 1 FAIL, 2 usage); `check_contracts(index: Path) -> list[str]`; stdout `LEDGER CHECK: PASS|FAIL  N row(s), M problem(s)`, one `  ledger: …` line per problem above it. V193-7/V193-8 quote the command and that verdict line verbatim.

**Problem lines (exact text; tests assert them):**

| Condition | Line |
|---|---|
| no data rows under `## Task ledger` | `ledger: no rows under ## Task ledger` |
| a required header cell is absent | ``ledger: no `<column>` column`` (one per column; nothing else is checked) |
| `**Spec:**` link missing or file absent | `ledger: spec file not found (<path or None>)` |
| `Spec §` cell empty or `—` | `ledger: <task> has no Spec § reference` |
| a ref resolves to no spec heading | `ledger: <task> Spec § '<ref>' matches no heading in <spec file name>` |
| consumed name only provided by a later row | ``ledger: <task> consumes `<name>`, created only by later row <task>`` |
| consumed name nowhere | ``ledger: <task> consumes `<name>`: neither in the repo nor created by an earlier row`` |

A name is **provided** by a row when it is `symbol_name(token)`, the
leading identifier of a token, or a `-`-prefixed word inside a token, for any
backticked token in that row's `Title`, `Files created / modified` or
`Creates` cell (so `` `plan_lint.py --stats` `` in V193-3's title provides
`--stats`, and `` `COMMANDS: dict[...]` `` provides `COMMANDS`). A name is
**in the repo** when it contains `/` and is tracked or on disk, or otherwise
when `git grep -q -F -e <name> -- . ":(exclude)docs/superpowers"` exits 0
(plans and specs mention every planned name, so they never count).

- [ ] **Step 1: Write the failing tests** — create `tests/dev/test_plan_lint_ledger.py`:

```python
"""plan_lint --ledger: the index's contracts hold before any part is written (v193)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_lint.py"
INDEX = "2026-10-25-v900-demo_0-index.md"
SPEC = "# v900 spec\n\n## A. Alpha\n\nalpha body\n\n## Testing\n\nunit tests\n"
LEDGER_HEAD = ("| Task | Title | Part | Model | Spec § | Files created / modified "
               "| Creates | Consumes |\n|---|---|---|---|---|---|---|---|\n")
# Built at run time so `git grep` never finds these names in this very file.
GHOST = "ghost" + "_v900_" + "symbol"
FLAG = "--" + "frob" + "v900"


def _row(task, spec="A", files="—", creates="—", consumes="—", title="t"):
    return f"| {task} | {title} | 1 | sonnet | {spec} | {files} | {creates} | {consumes} |\n"


def _index(rows: str, spec_link: str = "spec.md", head: str = LEDGER_HEAD) -> str:
    return ("# v900 Demo (index)\n\n**Bump:** none\n**Edge:** none (integrity)\n"
            f"**Spec:** [spec]({spec_link})\n\n## Parallelisation\n\nSerial.\n\n"
            "## Task ledger\n\n" + head + rows + "\n")


def _check(tmp_path, rows: str, spec_link: str = "spec.md",
           head: str = LEDGER_HEAD) -> tuple[int, str]:
    (tmp_path / "spec.md").write_text(SPEC, encoding="utf-8")
    index = tmp_path / INDEX
    index.write_text(_index(rows, spec_link, head), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(index)],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


def test_ledger_passes_when_contracts_hold(tmp_path):
    rows = (_row("V900-1", files="C `scripts/dev/v900_tool.py`",
                 creates="`alpha_fn(x: int) -> Path \\| None`; `TABLE: dict[str, int]`")
            + _row("V900-2", spec="A; Testing",
                   consumes="`alpha_fn`, `TABLE`, `plan_lint.plan_files`, "
                            "`scripts/dev/v900_tool.py`"))
    code, out = _check(tmp_path, rows)
    assert code == 0, out
    assert "LEDGER CHECK: PASS  2 row(s), 0 problem(s)" in out


def test_ledger_flag_named_in_earlier_title_counts(tmp_path):
    rows = (_row("V900-1", title=f"`v900_tool.py {FLAG} <x>`")
            + _row("V900-2", consumes=f"`{FLAG}`"))
    code, out = _check(tmp_path, rows)
    assert code == 0, out


def test_ledger_consumed_before_creation(tmp_path):
    rows = (_row("V900-1", consumes=f"`{GHOST}`")
            + _row("V900-2", creates=f"`{GHOST}() -> None`"))
    code, out = _check(tmp_path, rows)
    assert code == 1
    assert f"ledger: V900-1 consumes `{GHOST}`, created only by later row V900-2" in out
    assert "LEDGER CHECK: FAIL  2 row(s), 1 problem(s)" in out


def test_ledger_unknown_symbol(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", consumes=f"`{GHOST}`"))
    assert code == 1
    assert (f"ledger: V900-1 consumes `{GHOST}`: neither in the repo nor "
            "created by an earlier row") in out


def test_ledger_unresolved_spec_ref(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", spec="A; Q"))
    assert code == 1
    assert "ledger: V900-1 Spec § 'Q' matches no heading in spec.md" in out
    assert "1 problem(s)" in out


def test_ledger_empty_spec_cell(tmp_path):
    code, out = _check(tmp_path, _row("V900-1", spec="—"))
    assert code == 1
    assert "ledger: V900-1 has no Spec § reference" in out


def test_ledger_without_rows(tmp_path):
    code, out = _check(tmp_path, "")
    assert code == 1
    assert "ledger: no rows under ## Task ledger" in out
    assert "LEDGER CHECK: FAIL  0 row(s), 1 problem(s)" in out


def test_ledger_spec_file_not_found(tmp_path):
    code, out = _check(tmp_path, _row("V900-1"), spec_link="missing.md")
    assert code == 1
    assert "ledger: spec file not found" in out


def test_ledger_pre_v193_columns(tmp_path):
    old = ("| Task | Title | Part | Model | Files created / modified "
           "| Creates (consumed later) |\n|---|---|---|---|---|---|\n")
    code, out = _check(tmp_path, "| V900-1 | t | 1 | sonnet | — | — |\n", head=old)
    assert code == 1
    for column in ("Spec §", "Creates", "Consumes"):
        assert f"ledger: no `{column}` column" in out


def test_ledger_usage(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--ledger"],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 2
    assert "--ledger <index>" in proc.stdout
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_ledger.py`
Expected: every test fails (`--ledger` is not a `COMMANDS` key yet, so the
lint usage path answers with exit 2).

- [ ] **Step 3: Implement in `scripts/dev/plan_lint.py`**

V193-5 is the first `plan_lint.py` task that needs `plan_doc` (V193-2..V193-4
do not import it). Add after the stdlib imports (the index's Architecture: one
ledger parser):

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_doc  # noqa: E402  (scripts/dev has no __init__.py)
```

Add one line to the module docstring, below V193-4's `--fix-parts` line:

```
    python scripts/dev/plan_lint.py --ledger <index>      # check the ledger's contracts before parts are written
```

and one line at the end of the `USAGE` string (V193-3), after V193-4's
`--fix-parts` line, so the closing `"""` follows it:

```
  python scripts/dev/plan_lint.py --ledger <index>       check the index's ledger contracts before parts are written
```

New code, above the `COMMANDS` dict (each function stays well under
complexity 15):

```python
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
```

Register it — the one change to the dict V193-3 created:

```python
    "--ledger": cmd_ledger,
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint_ledger.py`
Expected: 10 passed, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Dogfood on this plan's own index and keep the old lint green**

Run: `python scripts/dev/plan_lint.py --ledger docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md`
Expected: `LEDGER CHECK: PASS  9 row(s), 0 problem(s)`. A FAIL here is a
ledger or parser defect: stop and report the problem lines to the controller;
do not edit the index.

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_lint.py`
Expected: `0 failed` (the single-positional lint is untouched).

Close: standard (test: tests/dev/test_plan_lint_ledger.py); commit `feat(v193): plan_lint --ledger checks the index's contracts before parts (V193-5)`.

### Task V193-6: `scripts/dev/plan_slice.py <index> <part>`

**Model:** sonnet — a new self-contained script with its own tests; the output shape is fixed by the spec and the ledger.

Spec § C: a part writer reads one slice instead of the whole spec, brief and
index — the index preamble, `## Global Constraints` (with its
`### Standard task close`), `## Handoff` if present and the full
`## Task ledger`; the spec sections the part's rows cite; the brief sections
for the files the rows **modify**, plus `## Traps`. Anything not found is a
trailing `MISSING:` line, never a crash. May run in parallel with
V193-2..V193-5 (own files; consumes only V193-1).

**Files:**
- Create: `scripts/dev/plan_slice.py`
- Create: `tests/dev/test_plan_slice.py`

**Interfaces:**
- Consumes (V193-1, `scripts/dev/plan_doc.py`): `ledger_rows`, `sections(text, level) -> dict[str, str]` (heading text → section including its heading line, up to the next heading of the same or higher level), `spec_refs`, `resolve_ref(ref, headings) -> str | None`, `spec_path(index, index_text) -> Path | None`, `backticked`, `COL_TASK`, `COL_PART`, `COL_SPEC`, `COL_FILES`.
- Produces: `slice_part(index: Path, part: str, brief: Path | None = None) -> tuple[str, list[str]]` (slice text, `MISSING:` lines; raises `ValueError("plan_slice: no ledger rows for part '<part>' in <index name>")`); `default_brief(index: Path) -> Path` (`<repo>/.superpowers/briefs/<plan base>.md`, part suffix stripped); `main(argv: list[str]) -> int` (`argv` includes the program name, as `plan_lint.main`). Output lines V193-7 quotes: `MISSING: spec section '<ref>'`, `MISSING: brief section '<path>'`, `MISSING: brief file <path>`; also `MISSING: spec file <path>` and `MISSING: index section '<name>'`.

Decisions the tests pin:
- Rows match on the `Part` cell exactly (`"2"` never pulls `"2b"`; a spill
  file keeps its rows under the original part number, because a writer never
  edits the index).
- A `Files` cell is read as items `C \`path\`` / `M \`path\``, a marker
  applying to every following path until the next marker. Only `M` paths
  (and paths with no marker) are looked up in the brief: a file a task
  creates has nothing to brief, so it never yields `MISSING:`. A
  `path:120-180` item is looked up as `path`.
- A brief section matches a path when its `##` heading is the path or starts
  with the path and a space (`## scripts/dev/plan_lint.py (167 lines)`), via
  `plan_doc.resolve_ref`.
- `Spec §` refs are printed once each, in ledger order; `—` / empty refs are
  skipped (the `--ledger` check owns that error).

- [ ] **Step 1: Write the failing tests** — create `tests/dev/test_plan_slice.py`:

```python
"""plan_slice.py: one part writer's whole context in one read (v193, spec § C)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "plan_slice.py"
INDEX = "2026-10-25-v900-demo_0-index.md"
HEAD = ("| Task | Title | Part | Model | Spec § | Files created / modified | Creates "
        "| Consumes |\n|---|---|---|---|---|---|---|---|\n")
ROWS = ("| V900-1 | one | 1 | sonnet | A | M `scripts/dev/x.py` | — | — |\n"
        "| V900-2 | two | 2 | sonnet | B | M `scripts/dev/y.py:10-20`; "
        "C `scripts/dev/new_tool.py` | — | — |\n")
SPEC = ("# v900 spec\n\n## A. Alpha\n\nalpha-body\n\n## B. Beta\n\nbeta-body\n\n"
        "### B.1 Detail\n\nbeta-detail\n\n## Testing\n\ntesting-body\n")
BRIEF = ("# Brief\n\n## scripts/dev/x.py\n\nx-brief\n\n## scripts/dev/y.py (120 lines)\n\n"
         "y-brief\n\n## Traps\n\ntrap-line\n")


def _index(rows: str = ROWS, extra: str = "") -> str:
    return ("# v900 Demo (index)\n\n**Bump:** none\n**Edge:** none (integrity)\n"
            "**Spec:** [spec](spec.md)\n\n## Goal\n\ngoal-text-not-sliced\n\n"
            "## Global Constraints\n\n- constraint-one\n\n### Standard task close\n\n"
            "close-steps-here\n\n## Parallelisation\n\nparallel-not-sliced\n\n" + extra
            + "## Task ledger\n\n" + HEAD + rows + "\n")


def _slice(tmp_path, part="2", rows=ROWS, extra="", brief="brief.md"):
    (tmp_path / "spec.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "brief.md").write_text(BRIEF, encoding="utf-8")
    index = tmp_path / INDEX
    index.write_text(_index(rows, extra), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), str(index), part,
                           "--brief", str(tmp_path / brief)],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=ROOT, timeout=60)
    return proc.returncode, proc.stdout


def test_slice_prints_only_this_parts_context(tmp_path):
    code, out = _slice(tmp_path)
    assert code == 0, out
    for wanted in ("**Bump:** none", "constraint-one", "close-steps-here",
                   "| V900-1 |", "| V900-2 |", "beta-body", "beta-detail",
                   "y-brief", "trap-line"):
        assert wanted in out, wanted
    for unwanted in ("alpha-body", "testing-body", "x-brief",
                     "goal-text-not-sliced", "parallel-not-sliced", "MISSING"):
        assert unwanted not in out, unwanted


def test_slice_includes_handoff(tmp_path):
    code, out = _slice(tmp_path, extra="## Handoff\n\npartner-decision\n\n")
    assert code == 0, out
    assert "partner-decision" in out


def test_slice_missing_spec_section(tmp_path):
    rows = "| V900-2 | two | 2 | sonnet | B; Q | M `scripts/dev/y.py` | — | — |\n"
    code, out = _slice(tmp_path, rows=rows)
    assert code == 0, out
    assert "MISSING: spec section 'Q'" in out
    assert "beta-body" in out


def test_slice_missing_brief_section(tmp_path):
    rows = "| V900-2 | two | 2 | sonnet | B | M `scripts/dev/z.py` | — | — |\n"
    code, out = _slice(tmp_path, rows=rows)
    assert code == 0, out
    assert "MISSING: brief section 'scripts/dev/z.py'" in out


def test_slice_without_brief(tmp_path):
    code, out = _slice(tmp_path, brief="absent.md")
    assert code == 0, out
    assert "MISSING: brief file" in out
    assert "constraint-one" in out and "beta-body" in out


def test_slice_unknown_part(tmp_path):
    code, out = _slice(tmp_path, part="7")
    assert code == 2
    assert out.strip() == f"plan_slice: no ledger rows for part '7' in {INDEX}"


def test_slice_part_label_is_exact(tmp_path):
    code, out = _slice(tmp_path, part="2b")
    assert code == 2


def test_slice_usage():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                          text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 2
    assert proc.stdout.startswith("usage:")


def test_default_brief_strips_part_suffix():
    spec = importlib.util.spec_from_file_location("plan_slice", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = ROOT / ".superpowers" / "briefs" / "2026-10-25-v900-demo.md"
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo_0-index.md")) == want
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo_2b-spill.md")) == want
    assert mod.default_brief(Path("docs/p/2026-10-25-v900-demo.md")) == want
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_slice.py`
Expected: every test fails (`scripts/dev/plan_slice.py` does not exist).

- [ ] **Step 3: Create `scripts/dev/plan_slice.py`**

```python
"""Print one plan part writer's whole context (v193, spec section C).

    python scripts/dev/plan_slice.py <index> <part> [--brief <path>]

Prints the index preamble, ## Global Constraints, ## Handoff (if any) and
## Task ledger; the spec sections the part's ledger rows cite; the brief
sections (## <repo path>) for the files those rows modify, plus ## Traps.
Whatever it cannot find is a trailing `MISSING:` line. Exit 2 on bad usage
or a part with no ledger rows.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_doc  # noqa: E402  (scripts/dev has no __init__.py)

ROOT = Path(__file__).resolve().parents[2]
PART_SUFFIX_RE = re.compile(r"_\d+[a-z]?(-[^.]*)?\.md$")
FILE_ITEM_RE = re.compile(r"(?:\b([CM])\s+)?`([^`]+)`")
INDEX_SECTIONS = ("Global Constraints", "Handoff", "Task ledger")
OPTIONAL_INDEX = ("Handoff",)
EMPTY_REFS = ("", "—", "-")
USAGE = "usage: python scripts/dev/plan_slice.py <index> <part> [--brief <path>]"


def default_brief(index: Path) -> Path:
    base = PART_SUFFIX_RE.sub("", index.name).removesuffix(".md")
    return ROOT / ".superpowers" / "briefs" / f"{base}.md"


def ordered_unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def all_sections(text: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for level in (4, 3, 2, 1):
        merged.update(plan_doc.sections(text, level))
    return merged


def index_blocks(text: str, missing: list[str]) -> list[str]:
    secs = plan_doc.sections(text, 2)
    blocks = [text.split("\n## ", 1)[0]]
    for name in INDEX_SECTIONS:
        if name in secs:
            blocks.append(secs[name])
        elif name not in OPTIONAL_INDEX:
            missing.append(f"MISSING: index section '{name}'")
    return blocks


def spec_blocks(index: Path, text: str, rows: list[dict[str, str]],
                missing: list[str]) -> list[str]:
    spec = plan_doc.spec_path(index, text)
    if spec is None or not spec.is_file():
        missing.append(f"MISSING: spec file {spec}")
        return []
    secs = all_sections(spec.read_text(encoding="utf-8"))
    refs = ordered_unique(r.strip() for row in rows
                          for r in plan_doc.spec_refs(row.get(plan_doc.COL_SPEC, ""))
                          if r.strip() not in EMPTY_REFS)
    headings: list[str] = []
    for ref in refs:
        heading = plan_doc.resolve_ref(ref, list(secs))
        if heading is None:
            missing.append(f"MISSING: spec section '{ref}'")
        else:
            headings.append(heading)
    return [f"===== spec: {spec.name} ====="] + [secs[h] for h in ordered_unique(headings)]


def modified_paths(rows: list[dict[str, str]]) -> list[str]:
    paths = []
    for row in rows:
        kind = "M"
        for m in FILE_ITEM_RE.finditer(row.get(plan_doc.COL_FILES, "")):
            kind = m.group(1) or kind
            path = m.group(2).split(":")[0].strip()
            if kind == "M" and "/" in path:
                paths.append(path)
    return ordered_unique(paths)


def brief_blocks(brief: Path, rows: list[dict[str, str]], missing: list[str]) -> list[str]:
    if not brief.is_file():
        missing.append(f"MISSING: brief file {brief}")
        return []
    secs = plan_doc.sections(brief.read_text(encoding="utf-8"), 2)
    blocks = [f"===== brief: {brief.name} ====="]
    for ref in modified_paths(rows) + ["Traps"]:
        heading = plan_doc.resolve_ref(ref, list(secs))
        if heading is None:
            missing.append(f"MISSING: brief section '{ref}'")
        else:
            blocks.append(secs[heading])
    return blocks


def slice_part(index: Path, part: str, brief: Path | None = None) -> tuple[str, list[str]]:
    text = index.read_text(encoding="utf-8")
    rows = [r for r in plan_doc.ledger_rows(text)
            if r.get(plan_doc.COL_PART, "").strip() == part]
    if not rows:
        raise ValueError(f"plan_slice: no ledger rows for part '{part}' in {index.name}")
    missing: list[str] = []
    ids = ", ".join(r.get(plan_doc.COL_TASK, "?") for r in rows)
    blocks = [f"===== slice: {index.name}, part {part}: {ids} ====="]
    blocks += index_blocks(text, missing)
    blocks += spec_blocks(index, text, rows, missing)
    blocks += brief_blocks(brief or default_brief(index), rows, missing)
    return "".join(b.rstrip("\n") + "\n\n" for b in blocks), missing


def parse_args(argv: list[str]) -> tuple[Path, str, Path | None] | None:
    args, brief = list(argv[1:]), None
    if "--brief" in args:
        k = args.index("--brief")
        if k + 1 >= len(args):
            return None
        brief = Path(args[k + 1])
        del args[k:k + 2]
    if len(args) != 2 or not Path(args[0]).is_file():
        return None
    return Path(args[0]), args[1], brief


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parsed = parse_args(argv)
    if parsed is None:
        print(USAGE)
        return 2
    try:
        text, missing = slice_part(*parsed)
    except ValueError as exc:
        print(exc)
        return 2
    print(text, end="")
    for line in missing:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_slice.py`
Expected: 9 passed, `0 failed`, `0 xfailed`.

- [ ] **Step 5: Smoke-run on this plan's index**

Run: `python scripts/dev/plan_slice.py docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md 2`
Expected: exit 0; the output starts with
`===== slice: 2026-10-25-v193-plan-writer-pipeline_0-index.md, part 2: V193-5, V193-6, V193-7, V193-8, V193-9 =====`,
carries `### Standard task close` and the spec sections `C. Stable
contracts…`, `A. Split right…`, `B. Shorter tasks…`, `D. Write-as-you-go…`,
`Model tier for prose parts` and `Testing`, and ends with
`MISSING: brief file …` (the brief is gitignored, absent from the worktree —
Review Focus 5). No traceback.

Close: standard (test: tests/dev/test_plan_slice.py); commit `feat(v193): plan_slice.py prints one part writer's context (V193-6)`.

# Phase 3 — Agents, docs, release

### Task V193-7: plan-writer and plan-briefer agents adopt the pipeline; Codex mirror

**Model:** sonnet — prose edits to two agent files whose wording becomes every later plan's contract, plus the mirror regeneration.

Spec § A, B, C, D and Model tier: the writer sizes from `--stats`, spills
into `_<N>b` itself, ends tasks with `Close:`, cites instead of pasting,
respects the ~400-line ceiling, reads one slice, and writes the
`Spec §`/`Consumes` ledger and gets `--ledger` to PASS; the briefer keys the
brief by `## <repo path>`. Spec D keeps **one append per task** — the
"Write as you go" heredoc rule stays as it is. Starts after V193-3..V193-6 are
in the worktree branch (it quotes their flags and output lines).

**Files:**
- Modify: `.claude/agents/plan-writer.md`
- Modify: `.claude/agents/plan-briefer.md`
- Modify: `.codex/agents/plan-writer.toml` (regenerated, never hand-edited)
- Modify: `.codex/agents/plan-briefer.toml` (regenerated, never hand-edited)
- Modify: `AGENTS.md` (the role-agent paragraph, `AGENTS.md:394-410`)
- Create: `tests/dev/test_plan_pipeline_docs.py`

The new test file is not in the index ledger's Files cell for this row (the
ledger lists only the prose files); it is this task's own test, no other task
creates it, and V193-8 extends it.

**Interfaces:**
- Consumes: `python scripts/dev/plan_lint.py --stats` (V193-3, prints `p90`), `--fix-parts <index>` (V193-4), `--ledger <index>` → `LEDGER CHECK: PASS` (V193-5), `python scripts/dev/plan_slice.py <index> <N>` and its `MISSING:` lines (V193-6), `TASK_CEILING = 400` (V193-2).
- Produces: `tests/dev/test_plan_pipeline_docs.py` with `_read(rel: str) -> str`; V193-8 appends its doc tests to it.

- [ ] **Step 1: Write the failing tests** — create `tests/dev/test_plan_pipeline_docs.py`:

```python
"""The plan-writing pipeline's rules stay written where agents and controllers
read them (v193). Pins phrases, not prose: reword freely, keep the commands."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


WRITER_MUST_SAY = (
    "plan_lint.py --stats", "p90", "plan_lint.py --ledger", "LEDGER CHECK: PASS",
    "scripts/dev/plan_slice.py", "MISSING:", "_<N>b-<slug>.md", "~1400",
    "--fix-parts", "### Standard task close", "Close: standard (test:", "~400",
    "| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |",
    "never the brief", "one task per tool call",
)


@pytest.mark.parametrize("phrase", WRITER_MUST_SAY)
def test_plan_writer_states_pipeline_rule(phrase):
    assert phrase in _read(".claude/agents/plan-writer.md")


@pytest.mark.parametrize("stale", ("150–300", "Full code stays",
                                   "Read the spec, the index and the brief"))
def test_plan_writer_drops_superseded_rule(stale):
    assert stale not in _read(".claude/agents/plan-writer.md")


@pytest.mark.parametrize("phrase", ("## <repo path>", "## Traps", "plan_slice.py"))
def test_plan_briefer_keys_brief_by_file(phrase):
    assert phrase in _read(".claude/agents/plan-briefer.md")


@pytest.mark.parametrize("phrase", ("plan_slice.py", "plan_lint.py --ledger",
                                    "plan_lint.py --stats", "_<N>b-<slug>.md",
                                    "`Close:`", "## <repo path>"))
def test_agents_md_mirrors_writer_rules(phrase):
    assert phrase in _read("AGENTS.md")
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_pipeline_docs.py`
Expected: FAIL on the plan-writer, plan-briefer and AGENTS.md phrases (the
`one task per tool call` and `## Traps` cases may already pass).

- [ ] **Step 3: Edit `.claude/agents/plan-writer.md`** (frontmatter untouched; `tests/hooks/test_agent_shape.py` pins `model: opus` and the skill)

`Modify: .claude/agents/plan-writer.md:20-21` — the File bullet gains the spill name:

```
- File: `docs/superpowers/plans/<spec's date>-v<spec's N>-<spec's name>.md` — reuses the spec's `vN`.
  Split plans: `..._0-index.md`, then `..._1-<slug>.md`, `..._2-<slug>.md`, …; a part that runs long spills into `..._<N>b-<slug>.md` (see Self-spill).
```

`Modify: .claude/agents/plan-writer.md:24-25` — replace both bullets with:

```
- `### Task <PREFIX><n>:` headings, `# Phase` sections. **No file over 1500 lines**; a part aims at ≤ ~1400, a task is never split across files, never compressed to fit.
- **Task ceiling ~400 lines** (`plan_lint.py`'s `TASK_CEILING`). A task that would run longer becomes two ledger rows in `mode=index` — split, never compress.
- Every new function, class and test body stays in full, with exact paths and commands (`superpowers:writing-plans`). **Existing code is cited, not pasted:** `Modify: path:120-180 (fn_name)` plus the old → new snippet of the edited lines only. Cite the repo file, never the brief (gitignored, absent from worktrees).
```

`Modify: .claude/agents/plan-writer.md:28` — replace the per-task verification bullet with:

```
- The index carries `### Standard task close` at the end of `## Global Constraints`: worktree check, the narrow run (`python scripts/dev/testrun.py file <test>`), complexity gate, commit shape. Every task ends with `Close: standard (test: <path>)` and spells out only its deviations; one full-suite run is the final task. From v194, `plan_lint.py` fails a task with no `Close:` line, one over the ceiling, or a `Modify:` range past the file's end.
```

After line 46 (end of "Write as you go", which keeps one task per tool call) add:

```
### Self-spill

Before each append, check `wc -l` of your file. If the file plus the next
task would pass ~1400 lines, create `<plan base>_<N>b-<slug>.md` (the same
short header as any part) and append there from that task on; a second spill
is `_<N>c-<slug>.md`. List every file in `FILES:`. **Never edit the index**:
the controller runs `python scripts/dev/plan_lint.py --fix-parts <index>`,
which rebuilds the `## Parts` table from the files on disk.
```

`Modify: .claude/agents/plan-writer.md:48-54` — replace the "Read the brief, don't re-explore" section with:

```
## Read one context, don't re-explore

`plan-briefer` has already gathered signatures, excerpts with line ranges,
test patterns and symbol verdicts into the brief — one `## <repo path>`
section per file, then `## Traps`.

- `mode=index` reads the spec whole and the brief.
- `mode=part <N>` reads **one slice** instead of the spec, the index and the
  brief: `python scripts/dev/plan_slice.py <index> <N>` prints the index
  header, `## Global Constraints`, `## Handoff`, the full ledger, the spec
  sections your rows cite and the brief sections for the files they modify.
  Each `MISSING:` line at its end (`spec section '<ref>'`,
  `brief section '<path>'`, `brief file <path>`) names a gap: `sed -n` the
  range you need from the repo file or the spec, never a whole document.

Read code yourself only for what the slice or brief does not cover, in a few
batched commands — every call re-reads your whole context. No brief in your
prompt? Ask for one (`BLOCKED:`) rather than exploring.
```

`Modify: .claude/agents/plan-writer.md:64-79` — replace the `mode=index` steps with (the Goal clause in step 3 is kept word for word):

```
1. Read the spec whole and the brief.
2. Size from measured numbers: run `python scripts/dev/plan_lint.py --stats`
   and estimate every task at its `p90` lines per task (measured on
   `plans/implemented/` in v193: median 254, p90 489). A task estimated past
   ~400 lines is two tasks.
   **≤ ~1300 lines total → single file; otherwise parts of ≤ ~1400 lines.**
3. Write the index **before any task body** — this is your first file write:
   the header block, goal (a short explanatory paragraph block, not one sentence: why the work exists, what changes once shipped, how it works in idea, what it leaves alone, how success is measured; `document-conventions.md` § The plan's Goal section), architecture, `## Global Constraints`
   ending in `### Standard task close`, `## Parallelisation`, and a **task
   ledger** with exactly these columns:
   `| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |`
   — `Spec §`: the spec heading(s) the row implements, `;`-separated and
   matched as a heading prefix (`A; Testing`); `Files`: `C \`path\`` /
   `M \`path\`` items; `Creates` / `Consumes`: the backticked names,
   signatures or flags that cross tasks (a literal `|` is written `\|`).
   Put it under the exact heading `## Task ledger`, task id in the first
   column — the SessionStart hook parses it to detect an unfinished plan. The
   ledger is the contract that lets parts be written independently — make
   every cross-task name, signature and file path final here.
   - Split plan: this is `_0-index.md`, plus a `## Parts` table
     (`| Part | File | Tasks | Scope |`, one row per part).
   - Single file: this is the top of the plan file itself.
4. Run `python scripts/dev/plan_lint.py --ledger <index>` and fix the ledger
   until it prints `LEDGER CHECK: PASS` (a name consumed before the row that
   creates it, a name neither in the repo nor created, a `Spec §` with no
   heading). Never return `PARTS` on a FAIL. Then: split plan → stop and
   return `PARTS`; single file → carry straight on with the `mode=part` steps
   below for every task, appending as you go.
```

`Modify: .claude/agents/plan-writer.md:83-84` — old:

```
Read the spec, the index and the brief; read code only where the brief
falls short for your part's tasks.
```

new:

```
Run `python scripts/dev/plan_slice.py <index> <N>` and read that slice (see
above); read code only where it falls short for your part's tasks.
```

`Modify: .claude/agents/plan-writer.md:95-96` — old `list its \`### Task\` ids
(\`grep -n "^### Task" <file>\`)`, new `list its \`### Task\` ids and those of
its spill files (\`grep -n "^### Task" <plan base>_<N>*.md\`)`.

`Modify: .claude/agents/plan-writer.md:108` — the `FILES:` line of the return shape becomes:

```
FILES: <plan path(s)> (<line count> each; a spill file follows its part)
```

- [ ] **Step 4: Edit `.claude/agents/plan-briefer.md`**

`Modify: .claude/agents/plan-briefer.md:20-42` — replace the "The brief" section with:

```
## The brief

Write it to the path you were given. **Key it by file**: part writers read it
through `scripts/dev/plan_slice.py`, which pulls the `## <repo path>` section
of each file their ledger rows modify, plus `## Traps`.

1. `## Files to change` — one table: file, its role in one line, its line
   count, the spec section(s) it serves.
2. One `## <repo path>` section per file a task will modify or call into —
   the heading is the repo-relative path alone, optionally followed by a
   space and a note (`## scripts/dev/plan_lint.py (167 lines)`). Inside:
   - **Signatures** — every function, class, dataclass field, config `Field`
     and table the spec names or the change must touch: `path:line` plus the
     exact signature or definition line.
   - **Excerpts** — the code a task will edit or call, ≤ 60 lines each, with
     `path:start-end` so a writer can cite line ranges. Current complexity of
     any function to be changed (`python -m radon cc -s <file>`) — note which
     are already ≥ 15.
   A test file a task will extend or mirror gets its own `## tests/...`
   section: fixtures and helpers used, one representative test verbatim.
3. `## Symbols` — table `Symbol | EXISTS path:line / MISSING (spec creates it) /
   WRONG MODULE (real location)`. Report only what `git grep` shows.
4. `## Traps` — last; only those that apply, one line each with the source
   doc (`docs/claude/known-traps.md`, `schema-evolution.md`, `no-lookahead`).

Budget: **≤ 60 KB**. Prefer a signature over an excerpt, an excerpt over a
whole file. Write the brief section by section as you go (append), never all
at the end. Never put two files under one `##` heading — the slice would miss
the second.
```

- [ ] **Step 5: Edit `AGENTS.md` (the condensed mirror, by hand)**

In the role-agent paragraph (`AGENTS.md:399-405`), old:

```
from a `task-brief`), `plan-briefer` (gathers a spec's code context into
`.superpowers/briefs/<plan base>.md` first), `plan-writer` (a plan from an
approved spec and that brief: `mode=index` (index and task ledger) first,
then one `mode=part <N>` per part, one at a time here, each appending task by
task to disk; at most 2 plans in progress per session; a plan cut off
```

new:

```
from a `task-brief`), `plan-briefer` (gathers a spec's code context into
`.superpowers/briefs/<plan base>.md` first, one `## <repo path>` section per
file plus `## Traps`), `plan-writer` (a plan from an approved spec and that
brief: `mode=index` (index and task ledger) first, sizing tasks at the p90 of
`python scripts/dev/plan_lint.py --stats` and fixing the ledger until
`python scripts/dev/plan_lint.py --ledger <index>` prints PASS; then one
`mode=part <N>` per part, one at a time here, each reading
`python scripts/dev/plan_slice.py <index> <N>` instead of the spec, index and
brief and appending task by task to disk: every task ends with a `Close:`
line, cites existing code by repo path and line range, stays under ~400
lines, and a part past ~1400 lines spills into `_<N>b-<slug>.md`;
at most 2 plans in progress per session; a plan cut off
```

- [ ] **Step 6: Regenerate the Codex agents**

Run: `python scripts/dev/sync_codex.py`
Expected: last line `Codex mirror is current.`; `git status --short` shows
`.codex/agents/plan-writer.toml` and `.codex/agents/plan-briefer.toml`
modified and no other `.codex/` file.

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_pipeline_docs.py`
Expected: all passed, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
and `python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py`
Expected: `0 failed` each.

Close: standard (test: tests/dev/test_plan_pipeline_docs.py) — deviations:
step 2 also runs the two `tests/hooks/` files above; skip the complexity gate
(no Python function changes). One commit with all six files (Codex mirror
rule): `docs(v193): plan-writer and plan-briefer adopt slice, stats, ledger check, Close: and self-spill (V193-7)`.

### Task V193-8: Controller docs: skills-tools, document-conventions, model-routing; `AGENTS.md`

**Model:** haiku — fully specified doc edits; every inserted paragraph is given below.

Spec § A, B, C and Model tier, controller side: `--ledger` after
`mode=index` and before parts; `--fix-parts` before committing parts; parts
read `plan_slice.py`; prose-only parts run their writer on sonnet; the new
ledger columns, standard close and spill naming in the conventions doc.
Runs after V193-7 (both edit `AGENTS.md` and `tests/dev/test_plan_pipeline_docs.py`).

**Files:**
- Modify: `docs/claude/skills-tools.md` (§ Plan writing (two phases), lines 333-355)
- Modify: `docs/claude/document-conventions.md` (§ Splitting, after line 349)
- Modify: `docs/claude/model-routing.md` (new section before line 41, `## The escalation ladder`)
- Modify: `AGENTS.md` (the sentence ending `committed as finished), and`)
- Modify: `tests/dev/test_plan_pipeline_docs.py` (created by V193-7)

**Interfaces:**
- Consumes: `_read(rel: str) -> str` in `tests/dev/test_plan_pipeline_docs.py` (V193-7); the commands `plan_lint.py --ledger <index>` / `LEDGER CHECK: PASS` (V193-5), `plan_lint.py --fix-parts <index>` (V193-4), `plan_lint.py --stats` (V193-3), `scripts/dev/plan_slice.py` (V193-6).
- Produces: nothing code consumes.

- [ ] **Step 1: Append the failing tests** to `tests/dev/test_plan_pipeline_docs.py`:

```python
CONTROLLER_DOCS = {
    "docs/claude/skills-tools.md": (
        "plan_lint.py --ledger <index>", "LEDGER CHECK: PASS",
        "plan_lint.py --fix-parts <index>", "scripts/dev/plan_slice.py",
        "model: sonnet", "_<N>b-<slug>.md", "### Standard task close"),
    "docs/claude/document-conventions.md": (
        "plan_lint.py --stats", "plan_lint.py --fix-parts <index>", "Spec §",
        "| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |",
        "### Standard task close", "_<N>b-<slug>.md", "~400"),
    "docs/claude/model-routing.md": ("## Plan-writer tier for prose parts", "model: sonnet",
                                     "docs, runs or release"),
    "AGENTS.md": ("--fix-parts <index>", "model: sonnet", "--ledger <index>` must PASS"),
}


@pytest.mark.parametrize(("rel", "phrase"),
                         [(rel, p) for rel, phrases in CONTROLLER_DOCS.items() for p in phrases])
def test_controller_docs_state_pipeline_step(rel, phrase):
    assert phrase in _read(rel)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_pipeline_docs.py`
Expected: the new `test_controller_docs_state_pipeline_step` cases fail (the
`Spec §` case for document-conventions may already fail or pass by accident —
either is fine); V193-7's cases still pass.

- [ ] **Step 3: Edit `docs/claude/skills-tools.md` § Plan writing (two phases)**

After line 336 (the end of step 1, `comes back \`DONE\` from this one run.`) add, indented as step 1:

```
   Then run `python scripts/dev/plan_lint.py --ledger <index>`: it must print
   `LEDGER CHECK: PASS` before any part is dispatched (every consumed name
   exists in the repo or comes from an earlier ledger row; every `Spec §`
   names a spec heading). A FAIL goes back to the index writer (`SendMessage`
   it the problem lines), never to the part writers.
```

After line 343 (`incomplete parts are re-dispatched two at a time.`) add, indented as step 2:

```
   Each part writer reads `python scripts/dev/plan_slice.py <index> <N>`
   instead of the spec, the index and the brief. A part whose ledger rows are
   all docs, runs or release tasks is dispatched with `model: sonnet`
   (`model-routing.md` § Plan-writer tier for prose parts). A writer whose
   file would pass ~1400 lines spills into `_<N>b-<slug>.md` itself.
```

`Modify: docs/claude/skills-tools.md:344-346` — old:

```
   **Commit the index as soon as phase 1 returns**
   (`docs(vN): plan index -- parts pending`), and each part as it returns, so
   a session that runs out of tokens leaves committed, resumable work.
```

new:

```
   **Commit the index as soon as phase 1 returns**
   (`docs(vN): plan index -- parts pending`), and each part as it returns, so
   a session that runs out of tokens leaves committed, resumable work. Before
   committing a part, run `python scripts/dev/plan_lint.py --fix-parts <index>`:
   it rebuilds the index's `## Parts` table from the files on disk (spill
   files included) and keeps each Scope cell; commit the index with the part
   when it changed. Never hand-edit that table.
```

`Modify: docs/claude/skills-tools.md:353-355` — append to that paragraph:

```
Tasks stay short so each append lands sooner and re-reads less: the
standard close is stated once in the index (`### Standard task close`, each
task ends `Close: standard (test: <path>)`), existing code is cited by repo
path and line range, and a task over ~400 lines is split into two.
```

- [ ] **Step 4: Edit `docs/claude/document-conventions.md` § Splitting** — after line 349 (the paragraph ending `version.`) insert:

```
**Parts are sized from measurements and spill themselves (v193).**
`python scripts/dev/plan_lint.py --stats` reports median and p90 lines per
task over the last five implemented plans; the index writer sizes parts at
p90, and a part writer whose file would pass ~1400 lines opens
`_<N>b-<slug>.md` itself (v189, v191 and v192 were re-split by hand). The
index's `## Parts` table (`| Part | File | Tasks | Scope |`) is never
hand-edited: `python scripts/dev/plan_lint.py --fix-parts <index>` rebuilds
it from the files on disk and keeps each Scope cell by part label. The task
ledger is
`| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |`,
checked by `plan_lint.py --ledger <index>` before any part is written. The
index ends `## Global Constraints` with `### Standard task close` and every
task ends `Close: standard (test: <path>)`. Citing existing code by line
range and lifting the shared close are not thinning — every new function
and test body stays in full; a task over ~400 lines is split, never
compressed. From v194, `plan_lint.py` enforces the `Close:` line, the task
ceiling and `Modify:` ranges.
```

- [ ] **Step 5: Edit `docs/claude/model-routing.md`** — before line 41 (`## The escalation ladder`) insert:

```
## Plan-writer tier for prose parts

The `Model:` stamps route implementers. The plan writers themselves run on
`plan-writer`'s pinned `opus`, with one exception (v193): a part whose ledger
rows are all docs, runs or release tasks — every row's `Model:` is haiku or
sonnet and no row's `Files created / modified` cell creates or modifies code
(`.py`, `.ts`, `.html`, `.scss`) — is dispatched with `model: sonnet`.
`mode=index` always runs on opus.

```

- [ ] **Step 6: Edit `AGENTS.md`** — old:

```
`python scripts/dev/plan_lint.py <index>` must print PASS before the plan is
committed as finished), and
```

new:

```
`python scripts/dev/plan_lint.py <index>` must print PASS before the plan is
committed as finished; `python scripts/dev/plan_lint.py --ledger <index>` must PASS
before any part is dispatched, `python scripts/dev/plan_lint.py --fix-parts <index>`
rebuilds the parts table before parts are committed, and a part whose rows
are all docs, runs or release tasks runs its writer with `model: sonnet`), and
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_plan_pipeline_docs.py`
Expected: all passed, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: `0 failed` (AGENTS.md still names every agent, skill and reference doc).

Run: `python scripts/dev/doc_section.py docs/claude/model-routing.md "Plan-writer tier for prose parts"`
Expected: prints the new section (the heading is addressable).

Close: standard (test: tests/dev/test_plan_pipeline_docs.py) — deviations:
step 2 also runs `tests/hooks/test_codex_mirror.py`; skip the complexity gate
(no Python function changes); commit `docs(v193): controller steps for --ledger, --fix-parts, plan_slice and sonnet prose parts (V193-8)`.

### Task V193-9: Full suite; merge to `main`

**Model:** haiku — runs fixed commands and a merge; no code is written.

Spec § Testing: the whole branch is green once, then merged. This is the
plan's only full-suite run (CLAUDE.md: no full suite after the merge).

**Files:** none created or modified (a defect found here goes back to the
task that owns the file, as a fix commit on the branch).

**Interfaces:**
- Consumes: everything V193-1..V193-8 committed on branch `2026-10-25-v193-plan-writer-pipeline`.
- Produces: the merge commit on `main`.

- [ ] **Step 1: Mirror and plan checks (in the worktree)**

Run: `python scripts/dev/sync_codex.py --check`
Expected: `Codex mirror is current.`, exit 0.

Run: `python scripts/dev/plan_lint.py docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md`
Expected: `PLAN LINT: PASS  3 file(s), 0 problem(s)` (v193 is below
`NEW_RULES_FROM = 194`, so it lints exactly as before; Review Focus 1).

Run: `python scripts/dev/plan_lint.py --ledger docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md`
Expected: `LEDGER CHECK: PASS  9 row(s), 0 problem(s)`.

Run: `python scripts/dev/plan_lint.py --fix-parts docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md`
then `git diff --exit-code -- docs/superpowers/plans/2026-10-25-v193-plan-writer-pipeline_0-index.md`
Expected: exit 0 from both — the table already matches the files on disk,
so the rebuild is byte-identical (Review Focus 3). Should the diff be
non-empty, restore the file with `git checkout -- <index>` and report the
diff to the controller as a V193-4 defect; do not commit it.

Run: `python scripts/dev/plan_lint.py --stats`
Expected: exit 0 and one `PLAN STATS:` line naming five plans.

- [ ] **Step 2: Full suite, through the `test-runner` agent**

Dispatch `test-runner` in the worktree with `python scripts/dev/testrun.py full`
(this includes `scripts/dev/complexity_gate.py`).
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure
(`docs/claude/testing-cost.md`). A failure is fixed in the owning task's
files, re-run alone with `python scripts/dev/testrun.py file <test>`, and
committed as `fix(v193): <summary> (V193-<n>)`; the full suite is not re-run
for it.

- [ ] **Step 3: Merge to `main` (follow the `worktree-lifecycle` skill)**

From the main tree `E:/Documents/Private/Projects/Discord-Bot`:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot status --short
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -5 main
git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count 2026-10-25-v193-plan-writer-pipeline..main
```

Expected: no uncommitted change to any file this plan touched. When the last
count is non-zero (another session committed to `main` since the branch was
cut), pause and confirm with the partner before merging (concurrent
sessions share this tree). Then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-25-v193-plan-writer-pipeline -m "merge(v193): plan-writer pipeline -- ledger check, slice, stats, fix-parts, Close: lines" -m "Co-Authored-By: <the trailer from the session's attribution reminder>"
```

Expected: a clean merge (no conflict — the branch touches only
`scripts/dev/`, `tests/dev/`, `.claude/agents/`, `.codex/agents/`,
`docs/claude/` and `AGENTS.md`). No full suite after the merge.

- [ ] **Step 4: Close out**

Run `/close-out` for v193 (standing permission, `docs/claude/document-lifecycle.md`):
`Bump: none`, so no `VERSION.json` change; it moves the spec-linked plan
files to `implemented/` and removes the worktree. The branch name contains
no `backup`; `git rev-list --count main..2026-10-25-v193-plan-writer-pipeline`
must print `0` before the branch is deleted.

Close: deviations only — no test file of its own: step 2 is the full suite,
and the only commit is the merge commit of step 3 (plus `/close-out`'s own).

