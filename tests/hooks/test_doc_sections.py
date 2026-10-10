"""v154: three docs/claude/ files carry the `##` headings skills read by name.

The headings were inserted between existing lines (nothing else in the docs
changed), so that `scripts/dev/doc_section.py` can print one section instead
of the whole file. This module pins that each heading is there, opens the
content it is named for, and that the heading arguments the skills pass match
exactly one heading each. It reads the docs directly and does not run
`doc_section.py`; that script has its own tests in tests/dev/.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "claude"
SKILLS = ROOT / ".claude" / "skills"

CLOSED = "### Closed pre-registrations — do not re-run these"
STAGE_MINUS_TWO = "- **Stage −2: the idea screen"

# doc -> [(inserted heading line, how the first line of its section starts)]
INSERTED = {
    "backtest-methodology.md": [
        ("## Windows", "- **Windows:** TRAIN = "),
        ("## Acceptance gate", "- **Acceptance gates (v72, "),
        ("## Badge scoring", "  **The surviving badge threshold, and its history**"),
        ("## Funnel stages", STAGE_MINUS_TWO),
        ("## Harvest gate", "- **`Edge: harvest` features are OUT OF SCOPE"),
        ("## Frozen constants", "- Frozen constants: `MIN_RISK_REWARD_RATIO"),
        ("## Evidence, registry and ledger", "- **Evidence age.**"),
    ],
    "known-traps.md": [
        ("## Two OHLCV caches", "- **Two parallel OHLCV cache subsystems"),
        ("## Legacy shims and silent no-ops", "- **The legacy shims are gone"),
        ("## Measured-empty tables", "- **An empty config table is not automatically"),
        ("## Re-exports, stale prices and plan closes",
         '- **An "unused import" here is often a deliberate re-export'),
        ("## Full-history cache and the live scan read",
         "- **`market_data/daily/{TICKER}.csv` holds each ticker's FULL history"),
        ("## Trade History, file sources and the write halt",
         "- **Trade History: filtering, sorting and paging must stay"),
    ],
    "architecture.md": [
        ("## Module map", "- `swingbot/core/` is business logic with **no Discord dependency**"),
        ("## Entry-signal single source", "- **Entry signals have a single source:**"),
        ("## NO-LOOKAHEAD", "- **NO-LOOKAHEAD RULE (law):**"),
        ("## Plan engine, registry and scan pipeline", "- **Plan Engine v2** ("),
    ],
}

# Headings that were already there and that skills also read by name.
EXISTING = {
    "backtest-methodology.md": [CLOSED],
    "known-traps.md": [
        "## Scan parameter and replay gate parity (v74)",
        "## The market_data cache never self-heals (v116 follow-up)",
    ],
}

# The heading arguments each skill's Step 1 passes to doc_section.py.
SKILL_READS = {
    "backtest-methodology.md": [
        "Acceptance gate", "Funnel stages", "Windows", "Frozen constants",
        "Closed pre-registrations", "Badge scoring",
    ],
    "known-traps.md": [
        "Two OHLCV caches", "Full-history cache", "Legacy shims",
        "Measured-empty tables", "Scan parameter and replay gate parity",
        "The market_data cache never self-heals",
    ],
    "architecture.md": ["NO-LOOKAHEAD", "Entry-signal single source"],
}

_HEADING_RE = re.compile(r"^#{2,3} (\S.*)$")
_COMMAND_RE = re.compile(r'doc_section\.py (docs/claude/[\w.-]+\.md)((?: "[^"\n]+")+)')


def _lines(doc: str) -> list[str]:
    return (DOCS / doc).read_text(encoding="utf-8").splitlines()


def _titles(doc: str) -> list[str]:
    """Titles of the doc's `##` and `###` headings, lower-cased."""
    found = (_HEADING_RE.match(line) for line in _lines(doc))
    return [m.group(1).strip().lower() for m in found if m]


def _matches(doc: str, argument: str) -> int:
    """How many headings a doc_section.py argument selects (prefix, any case)."""
    return sum(title.startswith(argument.lower()) for title in _titles(doc))


def _skill_commands() -> list[tuple[str, str, list[str]]]:
    """(skill, doc file name, heading arguments) for every doc_section.py
    command line written in a skill."""
    commands = []
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for doc, arguments in _COMMAND_RE.findall(text):
            commands.append((skill_md.parent.name, doc.rsplit("/", 1)[1],
                             re.findall(r'"([^"]+)"', arguments)))
    return commands


@pytest.mark.parametrize("doc", sorted(INSERTED))
def test_inserted_headings_appear_once_and_in_order(doc):
    lines = _lines(doc)
    headings = [heading for heading, _ in INSERTED[doc]]
    assert [lines.count(h) for h in headings] == [1] * len(headings)
    positions = [lines.index(h) for h in headings]
    assert positions == sorted(positions)


@pytest.mark.parametrize(
    "doc, heading, opens_with",
    [(doc, heading, start) for doc in sorted(INSERTED) for heading, start in INSERTED[doc]],
)
def test_inserted_heading_stands_alone_and_opens_its_content(doc, heading, opens_with):
    lines = _lines(doc)
    at = lines.index(heading)
    assert lines[at - 1] == "", "a blank line must precede the heading"
    assert lines[at + 1] == "", "a blank line must follow the heading"
    assert lines[at + 2].startswith(opens_with), lines[at + 2][:80]


def test_closed_preregistrations_heading_keeps_its_level_and_text():
    lines = _lines("backtest-methodology.md")
    text = "\n".join(lines)
    assert lines.count(CLOSED) == 1
    # test_guardrails splits the doc on this literal; a second occurrence, for
    # example inside an inserted heading, would move the split.
    assert text.count("### Closed pre-registrations") == 1
    closed_at = lines.index(CLOSED)
    assert [line for line in lines[closed_at:] if line.startswith("### ")] == [CLOSED]
    assert lines.index("## Evidence, registry and ledger") < closed_at
    assert not [line for line in lines[closed_at:] if line.startswith("## ")]


def test_stage_minus_two_stays_a_bullet_inside_funnel_stages():
    lines = _lines("backtest-methodology.md")
    bullets = [i for i, line in enumerate(lines) if line.startswith(STAGE_MINUS_TWO)]
    assert len(bullets) == 1
    assert not [line for line in lines if line.startswith("#") and "Stage" in line]
    funnel = lines.index("## Funnel stages")
    harvest = lines.index("## Harvest gate")
    assert funnel < bullets[0] < harvest
    assert any("measure_arms" in line for line in lines[funnel:harvest])


def test_known_traps_headings_go_in_the_preamble_only():
    lines = _lines("known-traps.md")
    last_inserted = max(lines.index(heading) for heading, _ in INSERTED["known-traps.md"])
    first_existing = min(lines.index(heading) for heading in EXISTING["known-traps.md"])
    assert last_inserted < first_existing


@pytest.mark.parametrize("doc", sorted(EXISTING))
def test_existing_headings_the_skills_read_are_still_there(doc):
    lines = _lines(doc)
    assert [lines.count(heading) for heading in EXISTING[doc]] == [1] * len(EXISTING[doc])


@pytest.mark.parametrize(
    "doc, argument",
    [(doc, argument) for doc in sorted(SKILL_READS) for argument in SKILL_READS[doc]],
)
def test_skill_heading_argument_selects_exactly_one_heading(doc, argument):
    assert _matches(doc, argument) == 1


def test_every_doc_section_command_in_a_skill_names_real_headings():
    """Drift guard for the skill text itself. It finds no command until the
    skills call doc_section.py; from then on a renamed heading or a mistyped
    argument in any skill fails here."""
    problems = [
        f"{skill}: {doc} {argument!r} selects {_matches(doc, argument)} headings"
        for skill, doc, arguments in _skill_commands()
        for argument in arguments
        if _matches(doc, argument) != 1
    ]
    assert problems == []
