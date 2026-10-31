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
