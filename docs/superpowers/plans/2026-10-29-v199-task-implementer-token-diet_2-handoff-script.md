# Task-implementer token diet, part 2: the handoff script

**Spec:** [Task-implementer token diet](../specs/2026-10-29-v199-task-implementer-token-diet.md)
**Index:** [Plan index](2026-10-29-v199-task-implementer-token-diet_0-index.md) (Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below)

This part builds `scripts/dev/task_handoff.py` in three seams: locating one
task exactly across a plan's files (V199-4), deriving the numbered
deliverables by the spec's § Deliverable grammar (V199-5), and the
environment block, handoff rendering and CLI (V199-6). All three edit the
same script, so they run in order. V199-6 also needs V199-3 merged.

Fixture note for implementers: every plan-shaped fixture below is an
indented `textwrap.dedent` string, so its `### Task` and `- Create:` lines
never start a line of this plan file (`plan_lint.py` would count them as
tasks). The test code blocks use four-backtick fences because the fixtures
carry their own three-backtick fences. Copy the fixtures exactly.

# Phase 2 — the handoff script

### Task V199-4: Locate a task exactly across a plan's files
**Model:** sonnet — new pure-function module with a fence-aware parser and a cross-file contract; no legacy code touched.

**Files:**
- Create: `scripts/dev/task_handoff.py`
- Create: `tests/scripts/test_task_handoff_locate.py`

**Interfaces:**
- Consumes (existing, `scripts/dev/plan_lint.py`): `plan_files(any_file: Path) -> list[Path]` (index first, then every sibling part, sorted), `update_fence(line: str, state: dict) -> bool` (state needs only the key `"fence"`; True while a line opens, sits in or closes a fence), `PART_SUFFIX_RE`. Import `plan_lint` by putting `scripts/dev` on `sys.path`, as `scripts/dev/testrun.py:56` does. The ledger names `FENCE_RE`; `update_fence` is its wrapper and is what this module uses, so fence semantics stay identical to `plan_lint.py`'s task byte count.
- Produces (final names; V199-5, V199-6, V199-8 and V199-10 import them): `class HandoffError(Exception)`; `task_section(text: str, task_id: str) -> str | None`; `find_task(files: list[Path], task_id: str) -> tuple[Path, str]`; `plan_base(plan: Path) -> str`; constants `SECTIONS = ("Task", "Deliverables", "Environment", "Preflight", "Code")`, `PREFLIGHT_SLOT = "<!-- task-brief: fill Preflight -->"`, `CODE_SLOT = "<!-- task-brief: fill Code -->"`, `REPORT_PREFIX = "DELIVERABLES:"`, `IMPLEMENTER_STATES = ("done", "deviated")`, `REVIEWER_STATES = ("done", "missing", "different")`, `NO_HANDOFF_LINE = "DELIVERABLES: n/a (no handoff)"`. Private helpers `_lines(text) -> list[str]` and `_fenced(lines) -> list[bool]` are reused by V199-5.

Rules this task pins (spec § 1): the heading is matched by the exact regex `^### Task <id>:` (`re.escape(id)`), so `E5` never matches `E53` and `V198-2` never matches `V198-2b`. A section runs from its heading to the next `### Task ` line, `# ` line or `## ` line **outside a fenced block**, or end of file — the same span `plan_lint.py` measures. Headings inside fences never start or end a section. `\r\n` is normalised to `\n` before parsing. `find_task` raises `HandoffError` naming the searched files when the id is in none, and naming every file holding it when it appears more than once (two parts, or twice in one file).

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_task_handoff_locate.py`. The fixtures are trimmed copies of real headings: V198-1/V198-2/V198-2b from `docs/superpowers/plans/2026-10-28-v198-risk-reporting-correctness_1-collector-and-api.md`, E5/E53 from `docs/superpowers/plans/implemented/2026-07-11-v4-edge-engine.md`.

````python
"""task_handoff.py locates exactly one ### Task section across a plan's files (V199-4)."""
from __future__ import annotations

import importlib
import importlib.util
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "task_handoff", ROOT / "scripts" / "dev" / "task_handoff.py")
task_handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_handoff)
plan_lint = importlib.import_module("plan_lint")  # on sys.path once task_handoff loaded

PART_1 = textwrap.dedent("""\
    # Risk reporting correctness — collector and API

    **Spec:** [spec](../specs/x.md)

    # Phase 1 — establish the collector seam

    ### Task V198-1: Decompose portfolio collection without changing behavior
    **Model:** opus — splits a legacy collector currently at complexity 20.

    **Files:** Modify `swingbot/core/edge/portfolio_state.py`; create `tests/edge/test_portfolio_state_collection.py`.

    - [ ] Add these isolated characterization tests before extraction.

    ```python
    PLAN = '''
    ### Task V198-9: a heading inside a fence
    ## not a section break either
    '''
    ```

    - [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py`.

    ### Task V198-2: Project collector availability and render it in Discord
    **Model:** sonnet — projection plus embed copy.

    - [ ] Step of V198-2.

    ### Task V198-2b: Expose shared Risk snapshots and fresh killswitch observations
    **Model:** sonnet — API seam.

    - [ ] Step of V198-2b.

    # Phase 2 — consume truthful state

    Phase prose that belongs to no task.
    """)

PART_2 = textwrap.dedent("""\
    # Risk reporting correctness — UI and signed weights

    ### Task V198-3: Consume truthful state in the Risk page
    **Model:** sonnet — UI.

    - [ ] Step of V198-3.
    """)

V4 = textwrap.dedent("""\
    ### Task E5: Volatility-targeted sizing
    **Model:** sonnet — sizing.

    - [ ] E5 step.

    ### Task E53: Weekly risk report
    **Model:** sonnet — report.

    - [ ] E53 step.
    """)


def _split_plan(tmp_path: Path, part_2: str = PART_2) -> list[Path]:
    base = "2026-10-28-v198-risk-reporting-correctness"
    (tmp_path / f"{base}_0-index.md").write_text("# Index\n\n## Task ledger\n", encoding="utf-8")
    (tmp_path / f"{base}_1-collector-and-api.md").write_text(PART_1, encoding="utf-8")
    (tmp_path / f"{base}_2-ui-and-weights.md").write_text(part_2, encoding="utf-8")
    return plan_lint.plan_files(tmp_path / f"{base}_0-index.md")


def test_constants_pin_the_handoff_contract():
    assert task_handoff.SECTIONS == ("Task", "Deliverables", "Environment", "Preflight", "Code")
    assert task_handoff.PREFLIGHT_SLOT == "<!-- task-brief: fill Preflight -->"
    assert task_handoff.CODE_SLOT == "<!-- task-brief: fill Code -->"
    assert task_handoff.REPORT_PREFIX == "DELIVERABLES:"
    assert task_handoff.IMPLEMENTER_STATES == ("done", "deviated")
    assert task_handoff.REVIEWER_STATES == ("done", "missing", "different")
    assert task_handoff.NO_HANDOFF_LINE == "DELIVERABLES: n/a (no handoff)"
    assert task_handoff.NO_HANDOFF_LINE.startswith(task_handoff.REPORT_PREFIX)


def test_single_file_plan_finds_the_section(tmp_path):
    plan = tmp_path / "2026-07-11-v4-edge-engine.md"
    plan.write_text(V4, encoding="utf-8")
    path, section = task_handoff.find_task(plan_lint.plan_files(plan), "E5")
    assert path == plan
    assert section.startswith("### Task E5: Volatility-targeted sizing\n")
    assert "- [ ] E5 step." in section
    assert "E53" not in section


def test_e5_never_matches_e53():
    section = task_handoff.task_section(V4, "E53")
    assert section.startswith("### Task E53: Weekly risk report\n")
    assert task_handoff.task_section(V4, "E") is None
    assert task_handoff.task_section(V4, "E5").count("### Task") == 1


def test_b_suffix_is_not_a_prefix_match():
    plain = task_handoff.task_section(PART_1, "V198-2")
    split = task_handoff.task_section(PART_1, "V198-2b")
    assert plain.startswith("### Task V198-2: Project collector availability")
    assert "V198-2b" not in plain
    assert split.startswith("### Task V198-2b: Expose shared Risk snapshots")


def test_heading_inside_a_fence_neither_starts_nor_ends_a_section():
    section = task_handoff.task_section(PART_1, "V198-1")
    assert "### Task V198-9: a heading inside a fence" in section
    assert "## not a section break either" in section
    assert section.rstrip().endswith("tests/edge/test_portfolio_state_collection.py`.")
    assert task_handoff.task_section(PART_1, "V198-9") is None


def test_phase_heading_ends_the_last_task_of_a_phase():
    section = task_handoff.task_section(PART_1, "V198-2b")
    assert "- [ ] Step of V198-2b." in section
    assert "# Phase 2" not in section
    assert "Phase prose" not in section


def test_split_plan_searches_every_part(tmp_path):
    files = _split_plan(tmp_path)
    assert files[0].name.endswith("_0-index.md")
    path, section = task_handoff.find_task(files, "V198-3")
    assert path.name.endswith("_2-ui-and-weights.md")
    assert section.startswith("### Task V198-3: Consume truthful state")


def test_duplicate_id_across_parts_names_both_files(tmp_path):
    duplicate = PART_2 + "\n### Task V198-1: Same id again\n**Model:** haiku — dup.\n"
    files = _split_plan(tmp_path, duplicate)
    with pytest.raises(task_handoff.HandoffError) as err:
        task_handoff.find_task(files, "V198-1")
    message = str(err.value)
    assert "V198-1" in message
    assert "_1-collector-and-api.md" in message and "_2-ui-and-weights.md" in message


def test_duplicate_id_inside_one_file_is_an_error(tmp_path):
    plan = tmp_path / "2026-07-11-v4-edge-engine.md"
    plan.write_text(V4 + "\n### Task E5: Again\n", encoding="utf-8")
    with pytest.raises(task_handoff.HandoffError, match="E5"):
        task_handoff.find_task([plan], "E5")


def test_missing_id_names_the_searched_files(tmp_path):
    files = _split_plan(tmp_path)
    with pytest.raises(task_handoff.HandoffError) as err:
        task_handoff.find_task(files, "V198-7")
    message = str(err.value)
    assert "V198-7" in message
    for path in files:
        assert path.name in message


def test_crlf_plan_extracts_the_same_section(tmp_path):
    crlf = PART_1.replace("\n", "\r\n")
    assert task_handoff.task_section(crlf, "V198-1") == task_handoff.task_section(PART_1, "V198-1")
    plan = tmp_path / "2026-07-11-v4-edge-engine.md"
    plan.write_bytes(V4.replace("\n", "\r\n").encode("utf-8"))
    _, section = task_handoff.find_task([plan], "E53")
    assert "\r" not in section


def test_plan_base_strips_the_part_suffix():
    plans = Path("docs/superpowers/plans")
    assert task_handoff.plan_base(plans / "2026-10-28-v198-risk-reporting-correctness_1-collector-and-api.md") \
        == "2026-10-28-v198-risk-reporting-correctness"
    assert task_handoff.plan_base(plans / "2026-10-29-v199-task-implementer-token-diet_0-index.md") \
        == "2026-10-29-v199-task-implementer-token-diet"
    assert task_handoff.plan_base(plans / "2026-10-25-v195-graphite-frontend-redesign_3b-local-formatters.md") \
        == "2026-10-25-v195-graphite-frontend-redesign"
    assert task_handoff.plan_base(plans / "2026-07-11-v4-edge-engine.md") == "2026-07-11-v4-edge-engine"
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_locate.py`
Expected: FAIL — collection error, `scripts/dev/task_handoff.py` does not exist.

- [ ] **Step 3: Implement `scripts/dev/task_handoff.py`** in the `scripts/dev/doc_section.py` style: module docstring (purpose, the usage line V199-6 makes real, exit codes), `from __future__ import annotations`, small pure functions, no top-level side effect beyond the `sys.path` insert. V199-6 adds `main()`; until then the module has no `__main__` block.

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_locate.py`
Expected: PASS, 12 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `git -C <wt> add scripts/dev/task_handoff.py tests/scripts/test_task_handoff_locate.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/task_handoff.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/task_handoff.py tests/scripts/test_task_handoff_locate.py
git -C <wt> commit -m "feat(dev): task_handoff.py locates one plan task exactly (V199-4)" -m "<attribution lines from the controller>"
```

### Task V199-5: Derive numbered deliverables by the spec grammar
**Model:** sonnet — a small text grammar with negative clauses and fence awareness; precise but pure.

**Files:**
- Modify: `scripts/dev/task_handoff.py`
- Create: `tests/scripts/test_task_handoff_deliverables.py`

**Interfaces:**
- Consumes (V199-4, same module): `HandoffError`, `_lines(text) -> list[str]`, `_fenced(lines) -> list[bool]`; existing `plan_lint.FENCE_RE` (group 2 is the fence info string) and `plan_lint.update_fence(line, state) -> bool`.
- Produces (V199-6 consumes): `class Deliverable(NamedTuple): id: str; text: str` (`"D3"`, `"D3.2"`); `FILES_VERBS = ("modify", "create", "update", "test", "delete")`; `files_paths(section: str) -> list[tuple[str, str]]` (verb as written, path); `derive_deliverables(section: str, task_id: str) -> list[Deliverable]`, raising `HandoffError("no deliverables derivable for <id>")`.

The grammar, from spec § Deliverable grammar, made exact:

- **Files block.** The first line outside a fence that starts with `**Files:**`, plus the following lines up to a blank line, a fenced line or a line starting `**`. A following line that starts `- ` (the bullet form, `- Create: \`x\``) begins a new clause; any other continuation line joins the sentence with a space.
- **Clauses.** The block splits at every `;` and every `.` followed by whitespace or end of text, never inside a backticked span. A clause whose prose (backticked spans removed, leading `- ` stripped) starts with `Existing`, or contains `remain` or `unchanged` (all case-insensitive), contributes nothing.
- **Paths.** Within a clause, a verb from `FILES_VERBS` (whole word, case-insensitive, outside backticks) opens a run; every following backticked span up to the next verb or clause end is a path if, with a trailing `:<line>` or `:<line>-<line>` removed, it consists only of word characters, `.`, `-`, `/`, `\` and contains a `/` or a `.`. So `helper()` or `--flag` after a verb is not a deliverable. Paths are kept in order, verb as written (`Modify`, `create`), no de-duplication.
- **Steps.** One deliverable per line outside a fence whose stripped form starts `- [ ]`; its text is the rest of that line, stripped, verbatim.
- **Test sub-items.** Inside a fence whose info string's first word is `python` or `py`, every line matching `^\s*(async\s+)?def (test_\w+)\s*\(` that sits after a step becomes sub-item `D<n>.<k>` of the most recent step, in order. Any other fence language contributes nothing.
- **Numbering.** File deliverables first (`D1`…), then steps continue the count; sub-items do not advance it. Nothing derivable raises `HandoffError(f"no deliverables derivable for {task_id}")`.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_task_handoff_deliverables.py`. `V198_1` is the real task from `docs/superpowers/plans/2026-10-28-v198-risk-reporting-correctness_1-collector-and-api.md` with code bodies trimmed to `...`; every prose line and every `- [ ]` line is verbatim.

````python
"""task_handoff.py derives D1..Dn deliverables by the v199 spec grammar (V199-5)."""
from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "task_handoff", ROOT / "scripts" / "dev" / "task_handoff.py")
task_handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_handoff)

V198_1 = textwrap.dedent("""\
    ### Task V198-1: Decompose portfolio collection without changing behavior
    **Model:** opus — splits a legacy collector currently at complexity 20.

    **Files:** Modify `swingbot/core/edge/portfolio_state.py`; create `tests/edge/test_portfolio_state_collection.py`; update `scripts/dev/complexity_baseline.json` only through the shrinking gate. Existing `tests/edge/test_portfolio_state_sectors.py` and `tests/edge/test_edge_heat.py` remain behaviorally unchanged in this task.

    **Interfaces:** Preserve `collect_portfolio_state() -> dict`, `_load_sector_map() -> dict` and `_unmapped_count(open_trades, sectors) -> int`. Create private `_cluster_groups(open_trades: list, balance, sectors: dict, dfs: dict) -> list` and `_cluster_state(open_trades: list, balance, sectors: dict) -> list`. V198-2 retains `_cluster_groups` while replacing the failure-default collection wrapper. No availability metadata or nullable values yet.

    - [ ] Add these isolated characterization tests before extraction. They pin current behavior, including the incorrect safe defaults that the next task deliberately changes. Add them to the new test file; its existing `tests/edge` directory already belongs to its feature suite.

    ```python
    import pytest

    from swingbot.core.edge import portfolio_state as ps


    @pytest.fixture
    def collected(monkeypatch):
        ...


    def test_characterized_success_has_original_fields(collected):
        ...


    def test_characterized_failed_trade_read_is_empty(monkeypatch, collected):
        ...


    def test_characterized_failed_controls_use_legacy_defaults(monkeypatch, collected):
        ...


    def test_characterized_cluster_failure_does_not_blank_heat(monkeypatch, collected):
        ...
    ```

    - [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py` before editing production code. Expected: all four characterization tests pass. This is a behavior-preserving refactor, so a deliberately failing behavior assertion would be wrong here.

    - [ ] Extract only the existing cluster block into these two helpers, preserving duplicate suppression, sorting, per-ticker failed-fetch skipping and outer exception fallback exactly. Move the correlation and get_daily_data imports into their owning helpers. Replace the collector's final cluster try/except block with the one assignment shown below; retain every preceding statement, including sector warning logs, unchanged.

    ```python
    def _cluster_groups(open_trades: list, balance, sectors: dict, dfs: dict) -> list:
        ...
    ```

    Inside `collect_portfolio_state`, replace the entire last try/except from `clusters: list = []` through its `state["clusters"] = []` fallback, including the surrounding try, with:

    ```python
        state["clusters"] = _cluster_state(open_trades, balance, sectors)
    ```

    - [ ] Run `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_collection.py` and `python scripts/dev/testrun.py file tests/edge/test_portfolio_state_sectors.py`. Run the account failure characterization alone with `python -m pytest tests/edge/test_edge_heat.py::test_collect_portfolio_state_degrades_on_account_config_failure -v` only after its database prerequisites if applicable. Expected: unchanged assertions pass, including old zero fallback. Run `python scripts/dev/complexity_gate.py --update`, then `python scripts/dev/complexity_gate.py`; confirm collector and each new helper are below 15 and the baseline only shrinks. Do not combine the next task's behavior change into this commit.

    - [ ] Fetch/status and inspect recent commits through the controller's repository-safe workflow. Stage only the three owned paths (baseline only if changed), and commit `refactor(risk): isolate portfolio cluster collection`. Record the narrow verification results before continuing.
    """)

BULLETS = textwrap.dedent("""\
    ### Task X-1: Superpowers template
    **Model:** haiku — template.

    **Files:**
    - Create: `exact/path/to/file.py`
    - Modify: `exact/path/to/existing.py:123-145`
    - Test: `tests/exact/path/to/test.py`

    **Interfaces:**
    - Consumes: `other/module.py`
    """)

FENCED = textwrap.dedent("""\
    ### Task X-2: Fenced look-alikes
    **Model:** haiku — fences.

    ```markdown
    **Files:** Modify `fake/inside.py`
    - [ ] a checkbox inside a fence
    ```

    **Files:** Create `real/outside.py`

    - [ ] The only real step.

    ```text
    def test_not_python():
    ```

    ```py
    class TestThing:
        def test_method(self):
            ...

    async def test_async_case():
        ...
    ```
    """)


def _files(text: str) -> list[tuple[str, str]]:
    return task_handoff.files_paths(f"### Task X-9: t\n\n**Files:** {text}\n\n- [ ] step\n")


def test_grammar_constants():
    assert task_handoff.FILES_VERBS == ("modify", "create", "update", "test", "delete")
    assert task_handoff.Deliverable._fields == ("id", "text")


def test_v198_1_files_sentence_yields_three_paths():
    assert task_handoff.files_paths(V198_1) == [
        ("Modify", "swingbot/core/edge/portfolio_state.py"),
        ("create", "tests/edge/test_portfolio_state_collection.py"),
        ("update", "scripts/dev/complexity_baseline.json"),
    ]


def test_v198_1_derives_files_then_steps_with_test_sub_items():
    items = task_handoff.derive_deliverables(V198_1, "V198-1")
    assert [d.id for d in items] == [
        "D1", "D2", "D3", "D4", "D4.1", "D4.2", "D4.3", "D4.4", "D5", "D6", "D7", "D8"]
    by_id = {d.id: d.text for d in items}
    assert by_id["D1"] == "Modify `swingbot/core/edge/portfolio_state.py`"
    assert by_id["D3"] == "update `scripts/dev/complexity_baseline.json`"
    assert by_id["D4"].startswith("Add these isolated characterization tests before extraction.")
    assert by_id["D4.1"] == "test_characterized_success_has_original_fields"
    assert by_id["D4.4"] == "test_characterized_cluster_failure_does_not_blank_heat"
    assert by_id["D6"].startswith("Extract only the existing cluster block")
    assert by_id["D8"].startswith("Fetch/status and inspect recent commits")
    assert not any("tests/edge/test_edge_heat.py" in d.text for d in items[:3])


def test_bullet_files_block_yields_one_deliverable_per_path():
    assert task_handoff.files_paths(BULLETS) == [
        ("Create", "exact/path/to/file.py"),
        ("Modify", "exact/path/to/existing.py"),
        ("Test", "tests/exact/path/to/test.py"),
    ]


def test_negative_clauses_contribute_nothing():
    text = ("Modify `a/x.py`. Existing tests that modify `a/y.py` keep passing; "
            "test fixtures in `a/t.py` remain as they are; update `a/z.py` so `a/w.py` "
            "stays unchanged; delete `a/old.py`.")
    assert _files(text) == [("Modify", "a/x.py"), ("delete", "a/old.py")]


def test_paths_run_until_the_next_verb_or_clause_end():
    text = ("Modify `a/one.py`, `a/two.py` and `a/three.py`; create `b/new.py` "
            "and update `VERSION.json`. Then `c/after_sentence.py` has no verb.")
    assert _files(text) == [
        ("Modify", "a/one.py"), ("Modify", "a/two.py"), ("Modify", "a/three.py"),
        ("create", "b/new.py"), ("update", "VERSION.json")]


def test_non_path_spans_after_a_verb_are_not_deliverables():
    assert _files("Modify `a/x.py` so it calls `helper()` with `--flag`.") == [("Modify", "a/x.py")]


def test_fenced_files_label_and_checkbox_are_ignored():
    assert task_handoff.files_paths(FENCED) == [("Create", "real/outside.py")]
    items = task_handoff.derive_deliverables(FENCED, "X-2")
    assert [d.id for d in items] == ["D1", "D2", "D2.1", "D2.2"]
    assert items[1].text == "The only real step."


def test_def_test_counts_only_in_python_fences():
    items = task_handoff.derive_deliverables(FENCED, "X-2")
    assert [d.text for d in items if "." in d.id] == ["test_method", "test_async_case"]


def test_task_without_deliverables_fails_loudly():
    prose = "### Task X-3: prose only\n**Model:** haiku — x.\n\nJust prose, no files, no steps.\n"
    with pytest.raises(task_handoff.HandoffError, match="no deliverables derivable for X-3"):
        task_handoff.derive_deliverables(prose, "X-3")
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_deliverables.py`
Expected: FAIL — `AttributeError: module 'task_handoff' has no attribute 'FILES_VERBS'` (or `files_paths`).

- [ ] **Step 3: Add the grammar to `scripts/dev/task_handoff.py`**, below `find_task`. Add `from typing import NamedTuple` to the imports. Keep each function small; no function reaches complexity 10.

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_deliverables.py`
Expected: PASS, 10 passed, 0 failed.

Then `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_locate.py` — still 12 passed.

- [ ] **Step 5: Check complexity**

Run: `git -C <wt> add tests/scripts/test_task_handoff_deliverables.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/task_handoff.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/task_handoff.py tests/scripts/test_task_handoff_deliverables.py
git -C <wt> commit -m "feat(dev): task_handoff.py derives numbered deliverables (V199-5)" -m "<attribution lines from the controller>"
```

### Task V199-6: Environment block and handoff rendering
**Model:** sonnet — pure rendering against a fixed layout contract and two prefix tables; no legacy code.

**Files:**
- Modify: `scripts/dev/task_handoff.py`
- Create: `tests/scripts/test_task_handoff_render.py`

**Interfaces:**
- Consumes (V199-4/5, same module): `HandoffError`, `SECTIONS`, `PREFLIGHT_SLOT`, `CODE_SLOT`, `plan_base`, `task_section`, `Deliverable`, `derive_deliverables`. Existing: `scripts/dev/testrun.py:64` `TEST_DB_URL_DEFAULT` (import `testrun` from the same `sys.path` entry as `plan_lint`; importing it has no side effects). V199-3: `frontend/scripts/ng-test.mjs` must exist (merge V199-3 first), CLI `node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend [--include <spec>]...`. V199-2: `browse.mjs shots --path <p> --clip <sel>`.
- Produces (V199-6b, V199-10, V199-11, V199-12 rely on): `DB_PREFIXES`, `FRONTEND_PREFIXES = ("frontend/",)`; `needs_db(paths) -> bool`; `needs_frontend(paths) -> bool`; `TEST_DB_URL` (= `testrun.TEST_DB_URL_DEFAULT`), `TEST_DB_CONTAINER = "swing-db-test"`, `TEST_DB_SERVICE = "db-test"`, `NG_TEST_WRAPPER = "frontend/scripts/ng-test.mjs"`, `MAX_IMAGE_READS = 4`; `environment_block(worktree: Path, branch: str, paths: list[str], attribution: str) -> str`; `render_handoff(task_text: str, deliverables: list[Deliverable], environment: str) -> str`; `handoff_path(main_root: Path, plan: Path, task_id: str) -> Path` = `<main_root>/.superpowers/sdd/<plan_base(plan)>/task-<id>-handoff.md`. (This task was split at 20 KB: `main_checkout`, `build_handoff` and the CLI are V199-6b.)

Decisions fixed here:

- **`DB_PREFIXES`** (controller-confirmed): `alembic` (no slash: matches `alembic.ini` and any `alembic/` tree), `swingbot/core/db/`, the six store modules `swingbot/core/infra/expectancy_attribution_store.py`, `swingbot/core/infra/gate_counterfactual_store.py`, `swingbot/core/marketdata/data_store.py`, `swingbot/core/marketdata/history_store.py`, `swingbot/core/planning/plan_store.py`, `swingbot/core/scanning/progress_store.py`, and `tests/db/`. Paths are matched after `\` → `/` with a leading `./` dropped. The task's prose is never keyword-scanned (spec, Author's calls).
- **Test database:** the URL comes from `testrun.TEST_DB_URL_DEFAULT`, the one source `tests/db/conftest.py` is already pinned to. Container `swing-db-test`, service `db-test`, profile `test` (`docker-compose.yml:83-94`), pinned against the compose text by a test. The handoff never tells the implementer to create a container or database; an unreachable server is `BLOCKED:` (the controller owns `/replicate-prod-db` and the containers).
- **Layout** (index § Cross-task contracts): `# Handoff: Task <id>`, then `## Task`, `## Deliverables`, `## Environment`, `## Preflight`, `## Code` in `SECTIONS` order, a blank line around each heading. Deliverable lines are `- D<n> <text>`; sub-items `  - D<n>.<k> <test name>`. Preflight and Code hold only their slot marker. The environment wording below is fixed copy; the tests pin its key phrases.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_task_handoff_render.py`.

````python
"""task_handoff.py renders the Environment block and the handoff layout (V199-6)."""
from __future__ import annotations

import importlib
import importlib.util
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "task_handoff", ROOT / "scripts" / "dev" / "task_handoff.py")
task_handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_handoff)
testrun = importlib.import_module("testrun")  # on sys.path once task_handoff loaded

WT = Path("C:/wt/v199")
ATTRIBUTION = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
PART = textwrap.dedent("""\
    ### Task V198-1: Decompose portfolio collection without changing behavior
    **Model:** opus — splits a legacy collector currently at complexity 20.

    **Files:** Modify `swingbot/core/edge/portfolio_state.py`; create `tests/edge/test_portfolio_state_collection.py`.

    - [ ] Add these isolated characterization tests before extraction.

    ```python
    def test_characterized_success_has_original_fields(collected):
        ...
    ```

    - [ ] Fetch/status and inspect recent commits.
    """)


def test_prefix_tables_are_the_confirmed_ones():
    assert task_handoff.DB_PREFIXES == (
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
    assert task_handoff.FRONTEND_PREFIXES == ("frontend/",)
    for prefix in task_handoff.DB_PREFIXES + task_handoff.FRONTEND_PREFIXES:
        assert any(ROOT.glob(prefix.rstrip("/") + "*")), f"{prefix} names nothing in the repo"


def test_needs_db_and_needs_frontend_match_by_prefix_only():
    assert task_handoff.needs_db(["swingbot/core/db/models.py"])
    assert task_handoff.needs_db(["alembic.ini"])
    assert task_handoff.needs_db(["swingbot\\core\\planning\\plan_store.py"])
    assert task_handoff.needs_db(["./tests/db/test_x.py"])
    assert not task_handoff.needs_db(["swingbot/core/planning/plan_builder.py", "tests/dbx/test_x.py"])
    assert not task_handoff.needs_db([])
    assert task_handoff.needs_frontend(["frontend/src/app/risk/risk.component.ts"])
    assert not task_handoff.needs_frontend(["scripts/dev/task_handoff.py"])
    assert not task_handoff.needs_frontend([])


def test_test_db_facts_come_from_testrun_and_match_compose():
    assert task_handoff.TEST_DB_URL == testrun.TEST_DB_URL_DEFAULT
    assert ":55432/" in task_handoff.TEST_DB_URL
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert f"container_name: {task_handoff.TEST_DB_CONTAINER}" in compose
    assert f"\n  {task_handoff.TEST_DB_SERVICE}:\n" in compose


def test_ng_test_wrapper_exists():
    assert (ROOT / task_handoff.NG_TEST_WRAPPER).is_file()


def test_environment_block_always_carries_the_base_facts():
    block = task_handoff.environment_block(WT, "v199-branch", ["scripts/dev/x.py"], ATTRIBUTION)
    assert "`C:/wt/v199`" in block and "`v199-branch`" in block
    assert "never `cd`" in block
    assert "python C:/wt/v199/scripts/dev/testrun.py file" in block
    assert "python -m radon cc -s -n C" in block
    assert ATTRIBUTION in block
    assert "TEST_DATABASE_URL" not in block and "ng-test.mjs" not in block


def test_environment_block_adds_database_lines_only_for_db_paths():
    block = task_handoff.environment_block(WT, "b", ["swingbot/core/db/models.py"], ATTRIBUTION)
    assert f"TEST_DATABASE_URL={task_handoff.TEST_DB_URL}" in block
    assert "swing-db-test" in block and "`db-test`" in block
    assert "never create a container" in block
    assert "BLOCKED:" in block
    assert "ng-test.mjs" not in block


def test_environment_block_adds_frontend_lines_only_for_frontend_paths():
    block = task_handoff.environment_block(WT, "b", ["frontend/src/app/x.ts"], ATTRIBUTION)
    assert f"node C:/wt/v199/{task_handoff.NG_TEST_WRAPPER} C:/wt/v199/frontend" in block
    assert "layout-audit.mjs" in block
    assert "--clip <css selector>" in block
    assert "At most 4 image reads" in block
    assert "TEST_DATABASE_URL" not in block


def test_render_handoff_has_the_contract_layout():
    section = task_handoff.task_section(PART, "V198-1")
    items = task_handoff.derive_deliverables(section, "V198-1")
    text = task_handoff.render_handoff(section, items, "- env line\n")
    lines = text.splitlines()
    assert lines[0] == "# Handoff: Task V198-1"
    assert [line for line in lines if line.startswith("## ")] == [f"## {s}" for s in task_handoff.SECTIONS]
    assert "- D1 Modify `swingbot/core/edge/portfolio_state.py`" in lines
    assert "  - D3.1 test_characterized_success_has_original_fields" in lines
    assert "- D4 Fetch/status and inspect recent commits." in lines
    assert f"## Preflight\n\n{task_handoff.PREFLIGHT_SLOT}\n\n## Code" in text
    assert text.endswith(f"## Code\n\n{task_handoff.CODE_SLOT}\n")
    assert section.rstrip("\n") in text


def test_render_rejects_text_without_a_task_heading():
    with pytest.raises(task_handoff.HandoffError):
        task_handoff.render_handoff("no heading\n", [], "")


def test_handoff_path_is_under_the_main_checkout():
    part = Path("docs/superpowers/plans/2026-10-29-v199-task-implementer-token-diet_2-handoff-script.md")
    assert task_handoff.handoff_path(Path("/m"), part, "V199-5") == Path(
        "/m/.superpowers/sdd/2026-10-29-v199-task-implementer-token-diet/task-V199-5-handoff.md")
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_render.py`
Expected: FAIL — `AttributeError: module 'task_handoff' has no attribute 'DB_PREFIXES'`.

- [ ] **Step 3: Add the environment and rendering code to `scripts/dev/task_handoff.py`**, below `derive_deliverables`, and `import testrun  # noqa: E402` beside `import plan_lint`.

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_render.py`
Expected: PASS, 10 passed, 0 failed. Re-run `test_task_handoff_locate.py` (12 passed) and `test_task_handoff_deliverables.py` (10 passed) the same way.

- [ ] **Step 5: Check complexity**

Run: `git -C <wt> add tests/scripts/test_task_handoff_render.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/task_handoff.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/dev/task_handoff.py tests/scripts/test_task_handoff_render.py
git -C <wt> commit -m "feat(dev): task_handoff.py renders the environment and handoff layout (V199-6)" -m "<attribution lines from the controller>"
```

### Task V199-6b: Write the handoff under the main checkout, and the CLI
**Model:** sonnet — git plumbing, a write guard and an argparse CLI composed from V199-4/5/6; exercised against a throwaway repo.

**Files:**
- Modify: `scripts/dev/task_handoff.py`
- Create: `tests/scripts/test_task_handoff_cli.py`

**Interfaces:**
- Consumes (V199-4/5/6, same module): `HandoffError`, `PREFLIGHT_SLOT`, `CODE_SLOT`, `find_task`, `derive_deliverables`, `files_paths`, `environment_block`, `render_handoff`, `handoff_path`; existing `plan_lint.plan_files`.
- Produces (V199-10, V199-11, V199-12, V199-13 rely on): `main_checkout(start: Path) -> Path`; `build_handoff(plan: Path, task_id: str, worktree: Path, attribution: str) -> Path`; `main(argv: list[str] | None = None) -> int`. CLI: `python scripts/dev/task_handoff.py <plan file> <task id> --worktree <path> --attribution "<line>"` — prints the absolute handoff path as its last line and exits 0; on `HandoffError` prints `task_handoff: <message>` and exits 2 (argparse usage errors also exit 2).

Decisions fixed here (spec § 1):

- The main checkout is the parent of `git -C <worktree> rev-parse --git-common-dir` (relative output is resolved against the worktree), whichever checkout runs the script. A directory outside git raises `HandoffError("not a git checkout: <path>")`.
- The branch is `git -C <worktree> rev-parse --abbrev-ref HEAD`.
- A re-run overwrites a handoff that still holds both slot markers. A handoff missing either marker has been filled by `/task-brief` and is never overwritten (Global Constraints: never edited after it is filled): exit 2 naming it.
- A plan path that is not a file exits 2 with `plan file not found: <path>`, before any git call.

- [ ] **Step 1: Write the failing tests** in `tests/scripts/test_task_handoff_cli.py`. The fixture builds a throwaway repository and a linked worktree under `tmp_path` (git is already a dev requirement; no network).

````python
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
````

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_cli.py`
Expected: FAIL — `AttributeError: module 'task_handoff' has no attribute 'main_checkout'` (and `main`).

- [ ] **Step 3: Add the git, write and CLI code to `scripts/dev/task_handoff.py`**, below `handoff_path`, with `import argparse` and `import subprocess` added to the imports. The `__main__` block goes last in the file.

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file <wt>/tests/scripts/test_task_handoff_cli.py`
Expected: PASS, 8 passed, 0 failed. Re-run the three earlier files (`test_task_handoff_locate.py` 12, `test_task_handoff_deliverables.py` 10, `test_task_handoff_render.py` 10 passed).

- [ ] **Step 5: Smoke-run the CLI on a real plan task**

Run: `python <wt>/scripts/dev/task_handoff.py <wt>/docs/superpowers/plans/2026-10-28-v198-risk-reporting-correctness_0-index.md V198-1 --worktree <wt> --attribution "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` (if v198 has moved to `implemented/` by then, use its path there).
Expected: exit 0; the last line is `<main checkout>/.superpowers/sdd/2026-10-28-v198-risk-reporting-correctness/task-V198-1-handoff.md`; that file lists `D1`…`D8` with `D4.1`…`D4.4` under `D4`, and its Environment has no database or frontend line. Delete that file afterwards; it is a smoke artefact.

- [ ] **Step 6: Check complexity**

Run: `git -C <wt> add tests/scripts/test_task_handoff_cli.py`, then `python -m radon cc -s -n C <wt>/scripts/dev/task_handoff.py` (prints nothing) and `python <wt>/scripts/dev/complexity_gate.py` (exit 0).

- [ ] **Step 7: Commit**

```bash
git -C <wt> add scripts/dev/task_handoff.py tests/scripts/test_task_handoff_cli.py
git -C <wt> commit -m "feat(dev): task_handoff.py CLI writes the handoff under the main checkout (V199-6b)" -m "<attribution lines from the controller>"
```

