"""testrun.py changed must reach the scout tests (v161 TS12).

DATA_READERS is first-match-wins: a narrow row placed before a broad one
must repeat the broad row's targets. Pinned here for every file the scout
tests read, plus one untouched neighbour per broad row."""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("select_tests_scout", ROOT / "scripts" / "dev" / "select_tests.py")
sel = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sel        # @dataclass resolves annotations through sys.modules
_spec.loader.exec_module(sel)

DOCS_CLAUDE = ("tests/hooks/test_guardrails.py", "tests/hooks/test_codex_mirror.py",
               "tests/hooks/test_role_skills.py", "tests/hooks/test_doc_sections.py",
               "tests/dev/test_doc_section.py")
LEDGER_READERS = ("tests/backtesting/test_preregistration_ledger_file.py",
                  "tests/backtesting/test_instrument_stats_ledger.py",
                  "tests/scripts/test_preregistration_ledger_cli.py",
                  "tests/admin/test_api_v1_research.py")

CASES = {
    "docs/superpowers/results/preregistration-ledger.jsonl": LEDGER_READERS + ("tests/scout/",),
    "docs/claude/backtest-methodology.md": DOCS_CLAUDE + ("tests/scout/test_scout_merge_parse.py",
                                                          "tests/scout/test_scout_merge.py"),
    "docs/claude/skills-tools.md": DOCS_CLAUDE + ("tests/scout/test_trade_scout_skill.py",),
    ".claude/skills/setup-scout/references/playbook.md": ("tests/hooks/",
                                                          "tests/scout/test_generator_roles.py",
                                                          "tests/scout/test_trade_scout_skill.py"),
    ".claude/agents/scout.md": ("tests/hooks/", "tests/scout/test_trade_scout_skill.py"),
    ".agents/skills/regime-desk/SKILL.md": ("tests/hooks/", "tests/scout/test_generator_roles.py"),
    "AGENTS.md": ("tests/hooks/", "tests/scout/test_generator_roles.py"),
}

UNCHANGED = {
    "docs/claude/persona.md": DOCS_CLAUDE,
    ".claude/settings.json": ("tests/hooks/",),
    ".codex/hooks.json": ("tests/hooks/",),
    "docs/superpowers/results/2026-10-08-screen-high52w.md": ("tests/hooks/test_guardrails.py",),
}


@pytest.mark.parametrize("path", sorted(CASES))
def test_a_file_the_scout_tests_read_selects_them(path):
    assert set(sel._readers_of(path)) == set(CASES[path])


@pytest.mark.parametrize("path", sorted(UNCHANGED))
def test_broad_rows_still_route_their_neighbours(path):
    assert set(sel._readers_of(path)) == set(UNCHANGED[path])


def test_every_scout_target_exists():
    targets = {t for readers in CASES.values() for t in readers}
    missing = [t for t in sorted(targets) if not (ROOT / t).exists()]
    assert not missing, missing
