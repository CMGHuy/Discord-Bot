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
