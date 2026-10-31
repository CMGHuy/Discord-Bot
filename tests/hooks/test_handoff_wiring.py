"""Agent files, /task-brief and the docs name the handoff contract task_handoff.py exports (v199).

Renaming a section, a report prefix or a deliverable state on one side
without the other fails here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "task_handoff", ROOT / "scripts" / "dev" / "task_handoff.py")
task_handoff = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task_handoff)

AGENTS = ("task-implementer", "task-reviewer")


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _agent(name: str) -> str:
    return _text(f".claude/agents/{name}.md")


@pytest.mark.parametrize("name", AGENTS)
def test_agent_names_every_handoff_section(name):
    body = _agent(name)
    missing = [s for s in task_handoff.SECTIONS if f"`## {s}`" not in body]
    assert not missing, missing


@pytest.mark.parametrize("name", AGENTS)
def test_agent_names_the_no_handoff_fallback(name):
    assert task_handoff.NO_HANDOFF_LINE in _agent(name)


def test_implementer_report_line_uses_the_exported_states():
    done, deviated = task_handoff.IMPLEMENTER_STATES
    prefix = task_handoff.REPORT_PREFIX
    assert f"{prefix} D1 {done} | D2 {done} | D3 {deviated}: <why>" in _agent("task-implementer")


def test_implementer_carries_the_handoff_ui_and_plan_rules():
    body = _agent("task-implementer")
    assert "task_handoff.py" in body
    assert "Never open a plan file" in body
    assert "Never edit the handoff file" in body
    assert "layout-audit.mjs" in body and "--clip <css selector>" in body
    assert f"at most {task_handoff.MAX_IMAGE_READS} image reads per task" in body.lower()
    assert "verification-before-completion" not in body


def test_reviewer_lines_use_the_exported_states():
    body = _agent("task-reviewer")
    done, missing, different = task_handoff.REVIEWER_STATES
    for state in task_handoff.REVIEWER_STATES:
        assert f"`D<n> {state}" in body, state
    assert f"D1 {done}\nD2 {missing} -- <what>\nD3 {different} -- <what>\n" in body


def test_reviewer_reads_the_handoff_not_the_report():
    body = _agent("task-reviewer")
    assert "never the implementer's report" in body
    assert "`[spec]` finding" in body
