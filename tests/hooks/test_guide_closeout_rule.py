"""v235 V235-8: the guide freshness rule (spec v215 § Freshness gate, layer 3)
is wired into /close-out, its Codex mirror, document-lifecycle.md, CLAUDE.md
and AGENTS.md, and CLAUDE.md stays under its 200-line cap."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NO_CHANGE = "guide: no reader-visible change"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end >= 0 else len(text)]


def test_close_out_step_5b_runs_guide_sources():
    step = _section(_read(".claude/skills/close-out/SKILL.md"), "## Step 5b")
    assert "python scripts/dev/guide_sources.py" in step
    assert "reviewed_for" in step
    assert NO_CHANGE in step


def test_codex_close_out_skill_carries_the_rule():
    assert "python scripts/dev/guide_sources.py" in _read(".agents/skills/close-out/SKILL.md")


def test_document_lifecycle_explains_the_rule():
    section = _section(_read("docs/claude/document-lifecycle.md"),
                       "## Implemented plans keep the skills aligned")
    assert "guide_sources.py" in section and NO_CHANGE in section


@pytest.mark.parametrize("rel", ["CLAUDE.md", "AGENTS.md"])
def test_operator_files_state_the_rule(rel):
    text = _read(rel)
    assert "guide_sources.py" in text and NO_CHANGE in text


def test_claude_md_stays_under_200_lines():
    assert len(_read("CLAUDE.md").splitlines()) < 200


def test_the_moved_readme_rule_keeps_its_detail():
    assert "read the one topic file it points at" in _read("docs/claude/working-conventions.md")
    assert "**README.md is only an index" in _read("CLAUDE.md")
