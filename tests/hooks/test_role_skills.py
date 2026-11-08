"""v145 § 1: the expert role skills -- one shape for ten lenses (v213 adds ux-designer).

Each role skill carries Lens, Checklist, Red flags and Out of scope in that
order, states the hard boundaries every seat shares, and ships trigger cases
in the v96 format. Its reviewer model is recorded once, in the roles table of
docs/claude/skills-tools.md, which /panel reads. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

SKILLS_DIR = ROOT / ".claude" / "skills"
SKILLS_TOOLS = ROOT / "docs/claude/skills-tools.md"

# role -> reviewer model (spec § 1). Each role-skill task adds its own rows.
ROLES = {
    "quant-researcher": "opus",
    "risk-manager": "sonnet",
    "financial-advisor": "sonnet",
    "veteran-trader": "sonnet",
    "technical-analyst": "sonnet",
    "fundamental-analyst": "sonnet",
    "staff-engineer": "opus",
    "quant-engineer": "sonnet",
    "senior-engineer": "sonnet",
    "ux-designer": "sonnet",
}

SECTIONS = ("## Lens", "## Checklist", "## Red flags", "## Out of scope")
BOUNDARIES = ("never decide", "never lower a gate", "`pooled-numbers`",
              "`backtest-gate`", "BLOCKING", "ADVISORY")
MIN_CHECKS, MAX_CHECKS = 8, 15
REVIEWER_MODELS = {"sonnet", "opus"}   # no reviewer runs on haiku
CASE_FILES = ("prompt.md", "graders/skill-fired.md")
# Characters of the parsed description value -- the text inside the quotes.
MAX_ROLE_DESCRIPTION = 260

# v213 § C: the boundary paragraph every seat opens with, pinned whole. It
# stays inside each skill because a role skill also loads on its own, without
# expert-reviewer. Wrapped in the files exactly as these six lines.
BOUNDARY = " ".join((
    "You are one seat on a review panel. You raise findings; you never decide, and",
    "you never lower a gate (`docs/claude/persona.md`). No seat's intuition",
    "overrides the `backtest-gate` skill, the `pooled-numbers` skill or a closed",
    "pre-registration, and you quote no pooled figure you did not re-derive. Every",
    "finding cites `file:line`, a git range or a doc section, and is tagged",
    "`BLOCKING` (it matches a red flag below) or `ADVISORY`.",
))

# v213 § C: a cross-cutting checklist item opens with one shared lead, then
# the seat's own angle, so /panel can merge the same concern across seats.
LEADS = {
    "Shorts:": "Shorts: long plans stay byte-identical; ",
    "eToro:": "eToro: demo only, never `account: real`; ",
}
# role -> the LEADS keys its checklist must carry (one item each).
CROSS_CUTTING: dict[str, frozenset[str]] = {
    "risk-manager": frozenset({"Shorts:", "eToro:"}),
    "veteran-trader": frozenset({"Shorts:", "eToro:"}),
    "quant-researcher": frozenset({"Shorts:"}),
    "staff-engineer": frozenset({"eToro:"}),
    "financial-advisor": frozenset({"eToro:"}),
}

# v213 § C: the anchors each seat's new checklist items must carry -- words
# and paths, never whole sentences, so a reword inside the item still passes.
COVERAGE: dict[str, tuple[str, ...]] = {
    "risk-manager": ("level-lifecycle", "current stop",
                     "`swingbot/core/planning/gap_sizing.py`",
                     "squeeze notice", "`swingbot/core/market/short_interest.py`",
                     "without its stop"),
    "veteran-trader": ("act on before the open", "half-days",
                       "frozen weekend bar", "partial fill", "hard-to-borrow",
                       "CFD"),
    "quant-researcher": ("badge tier", "`swingbot/core/backtesting/validation_registry.json`",
                         "Total R", "trade count", "live-book gap"),
    "quant-engineer": ("§ Long runs must checkpoint", "skips finished units on restart",
                       "`swingbot/core/marketdata/providers/router.py`",
                       "`swingbot/core/marketdata/training_data.py`"),
    "staff-engineer": ("`deploy/gunicorn.conf.py`", "`tests/suites.toml`",
                       "`scripts/ops/pitr_backup.sh`", "§ Scheduling far-off work",
                       "idempotent"),
    "senior-engineer": ("`tests/suites.toml`", "Vitest", "Mutating the fix"),
    "financial-advisor": ("overnight fees", "minimum position size"),
    "technical-analyst": ("`confirmed_pivots`", "BOS/CHoCH", "significance tier",
                          "`swingbot/core/market/turtle_soup.py`",
                          "`swingbot/core/market/atr_band.py`",
                          "Volume counts as confirmation",
                          "`swingbot/core/market/explain.py`"),
}


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(name):
    return _text(SKILLS_DIR / name / "SKILL.md").split("---", 2)[2]


def _description(name):
    return parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))[0]["description"]


def _section(body, heading):
    start = body.index(heading + "\n") + len(heading)
    end = body.find("\n## ", start)
    return body[start:] if end == -1 else body[start:end]


def _boundary(role):
    """The first paragraph after the `# ` title line, lines joined by spaces."""
    lines = _body(role).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("# ")) + 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    paragraph = []
    for line in lines[start:]:
        if not line.strip():
            break
        paragraph.append(line.strip())
    return " ".join(paragraph)


def _checklist(role):
    return [line for line in _section(_body(role), "## Checklist").splitlines()
            if line.startswith("- ")]


def _lead_problems(item):
    """Why a checklist item that opens with a lead word misuses the lead."""
    for key, lead in LEADS.items():
        if not item.startswith("- " + key.rstrip(":")):
            continue
        if not item.startswith("- " + lead):
            return [f"lead not exact: {item[:60]!r}"]
        angle = item[len("- " + lead):]
        if not angle.strip() or not item.endswith("."):
            return [f"no angle or no full stop: {item[:60]!r}"]
    return []


def lens_skills(skills_dir=SKILLS_DIR):
    """Every skill that declares a Lens is a role skill."""
    return {p.parent.name for p in pathlib.Path(skills_dir).glob("*/SKILL.md")
            if "\n## Lens\n" in _text(p)}


def _cases(role):
    root = SKILLS_DIR / role / "evals"
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name != "results") if root.is_dir() else []


def _case_problems(role, case):
    missing = [rel for rel in CASE_FILES if not (case / rel).is_file()]
    if missing:
        return [f"{case.name}: missing {missing}"]
    grader = _text(case / "graders/skill-fired.md")
    expected = [f"input_match: {role}\n"]
    expected += ["min: 0", "max: 0"] if case.name.startswith("no-fire-") else ["min: 1"]
    return [f"{case.name}: grader lacks {line!r}" for line in expected if line not in grader]


def test_every_lens_skill_is_a_registered_role():
    assert lens_skills() == set(ROLES)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_has_the_four_sections_in_order(role):
    body = _body(role)
    positions = [body.find(heading + "\n") for heading in SECTIONS]
    assert -1 not in positions, dict(zip(SECTIONS, positions))
    assert positions == sorted(positions)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_checklist_has_eight_to_fifteen_items(role):
    items = [line for line in _section(_body(role), "## Checklist").splitlines()
             if line.startswith("- ")]
    assert MIN_CHECKS <= len(items) <= MAX_CHECKS, len(items)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_states_the_hard_boundaries(role):
    body = _body(role)
    missing = [phrase for phrase in BOUNDARIES if phrase not in body]
    assert not missing, missing


def test_financial_advisor_is_educational_not_personal_advice():
    assert "educational, not personalised financial advice" in _body("financial-advisor")


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_ships_fire_and_no_fire_cases(role):
    cases = _cases(role)
    fire = [c.name for c in cases if c.name.startswith("fire-")]
    quiet = [c.name for c in cases if c.name.startswith("no-fire-")]
    assert fire and quiet, [c.name for c in cases]
    assert len(fire) + len(quiet) == len(cases), "every case is fire-* or no-fire-*"
    assert [problem for case in cases for problem in _case_problems(role, case)] == []


@pytest.mark.parametrize("role", sorted(ROLES))
def test_reviewer_model_is_recorded_in_the_roles_table(role):
    assert ROLES[role] in REVIEWER_MODELS
    assert f"| `{role}` | {ROLES[role]} |" in _text(SKILLS_TOOLS)


PANEL_PHRASES = ("expert-reviewer", "serially", "skills-tools.md", "BLOCKING",
                 "## Panel review", "applied", "rejected: <why>", "/close-out",
                 "Model tiers", "`Shorts:`", "`eToro:`")


def test_panel_dispatches_the_expert_reviewer_serially():
    body = _body("panel")
    missing = [phrase for phrase in PANEL_PHRASES if phrase not in body]
    assert not missing, missing


def test_close_out_stops_on_an_unresolved_blocking_finding():
    body = _body("close-out")
    missing = [p for p in ("/panel", "**Panel:**", "BLOCKING", "main...<branch>")
               if p not in body]
    assert not missing, missing


def test_the_escalation_ladder_replaced_fails_review_twice():
    text = _text(SKILLS_TOOLS)
    assert "fails review twice" not in text
    assert "model-routing.md" in text and "one tier up" in text


# v154 section 2: a role description is listed in every session and every
# subagent, so it is capped. A missed fire case is fixed by rewording inside
# the cap, never by raising it.
@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_description_fits_the_listing_cap(role):
    value = _description(role)
    assert len(value) <= MAX_ROLE_DESCRIPTION, len(value)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_description_keeps_its_seat_and_a_hand_off(role):
    value = _description(role)
    assert f"the {role} seat" in value
    assert "Not for" in value
    assert [other for other in ROLES if other != role and f"({other})" in value]
    # expert-reviewer invokes the skill by name; the clause bought nothing.
    assert "expert-reviewer" not in value


@pytest.mark.parametrize("role", sorted(ROLES))
def test_boundary_paragraph_is_canonical(role):
    assert _boundary(role) == BOUNDARY


@pytest.mark.parametrize("role", sorted(ROLES))
def test_cross_cutting_items_use_the_shared_lead(role):
    assert [p for item in _checklist(role) for p in _lead_problems(item)] == []


def test_cross_cutting_seats_carry_their_leads():
    assert set(CROSS_CUTTING) <= set(ROLES)
    wrong = {}
    for role, keys in sorted(CROSS_CUTTING.items()):
        assert keys <= set(LEADS), (role, keys)
        for key in sorted(keys):
            hits = [i for i in _checklist(role) if i.startswith("- " + LEADS[key])]
            if len(hits) != 1:
                wrong[f"{role} {key}"] = len(hits)
    assert wrong == {}, "each listed seat carries each lead exactly once"


@pytest.mark.parametrize("role", sorted(COVERAGE))
def test_seat_names_its_coverage_items(role):
    checklist = "\n".join(_checklist(role))
    assert [a for a in COVERAGE[role] if a not in checklist] == []


def test_dropped_items_stay_with_their_owners():
    """v213 § C: these checks moved to the skill that owns them."""
    assert "`Bump:`" not in "\n".join(_checklist("staff-engineer"))      # /close-out
    assert "Every symbol the brief names" not in "\n".join(_checklist("senior-engineer"))  # task-brief


# v213 § D: /panel suggests seats from the target's type, so the area seats
# (technical-analyst, ux-designer) are picked when their area is touched.
PANEL_STEP_2 = "## Step 2 — Resolve the roles and the target"


def _panel_seat_rows():
    """Target cell -> seats cell of the seat-picking table in /panel Step 2."""
    rows = {}
    for line in _section(_body("panel"), PANEL_STEP_2).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 2 and set(cells[0]) - set("-: "):
            rows[cells[0]] = cells[1]
    rows.pop("Target", None)
    return rows


def test_panel_seat_table_names_area_seats():
    rows = _panel_seat_rows()
    named = {seat for cell in rows.values()
             for seat in re.findall(r"`([a-z-]+)`", cell)}
    assert named and named <= set(ROLES), sorted(named - set(ROLES))

    def seats_for(area):
        return " ".join(cell for target, cell in rows.items() if area in target)

    assert "`ux-designer`" in seats_for("`frontend/`")
    assert "`ux-designer`" in seats_for("embed")
    assert "`technical-analyst`" in seats_for("`swingbot/core/market/`")
    assert "`quant-researcher`" in seats_for("Backtest")
    assert "**Panel:**" in seats_for("Spec") and "`Edge:`" in seats_for("Spec")
