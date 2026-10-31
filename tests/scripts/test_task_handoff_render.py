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
