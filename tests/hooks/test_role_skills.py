"""v145 § 1: the expert role skills -- one shape for nine lenses.

Each role skill carries Lens, Checklist, Red flags and Out of scope in that
order, states the hard boundaries every seat shares, and ships trigger cases
in the v96 format. Its reviewer model is recorded once, in the roles table of
docs/claude/skills-tools.md, which /panel reads. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".claude" / "skills"
SKILLS_TOOLS = ROOT / "docs/claude/skills-tools.md"

# role -> reviewer model (spec § 1). Each role-skill task adds its own rows.
ROLES = {
    "quant-researcher": "opus",
    "risk-manager": "sonnet",
    "financial-advisor": "sonnet",
}

SECTIONS = ("## Lens", "## Checklist", "## Red flags", "## Out of scope")
BOUNDARIES = ("never decide", "never lower a gate", "`pooled-numbers`",
              "`backtest-gate`", "BLOCKING", "ADVISORY")
MIN_CHECKS, MAX_CHECKS = 8, 15
REVIEWER_MODELS = {"sonnet", "opus"}   # no reviewer runs on haiku
CASE_FILES = ("prompt.md", "graders/skill-fired.md")


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(name):
    return _text(SKILLS_DIR / name / "SKILL.md").split("---", 2)[2]


def _section(body, heading):
    start = body.index(heading + "\n") + len(heading)
    end = body.find("\n## ", start)
    return body[start:] if end == -1 else body[start:end]


def lens_skills(skills_dir=SKILLS_DIR):
    """Every skill that declares a Lens is a role skill."""
    return {p.parent.name for p in pathlib.Path(skills_dir).glob("*/SKILL.md")
            if "\n## Lens\n" in _text(p)}


def _cases(role):
    root = SKILLS_DIR / role / "evals"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


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
