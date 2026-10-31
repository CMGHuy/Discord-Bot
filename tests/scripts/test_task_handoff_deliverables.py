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
