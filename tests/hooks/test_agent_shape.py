"""Shape contract for .claude/agents/*.md -- v107.

Pins each role agent's model and preloaded skills so a cost decision made in
the v107 spec cannot drift silently. See
docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
"""
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"

# Each v107 agent task appends its own entry.
EXPECTED = {
    "task-implementer": {
        "model": "sonnet",
        "skills": {"superpowers:test-driven-development",
                   "superpowers:verification-before-completion"},
    },
    "task-reviewer": {
        "model": "sonnet",
        "skills": {"no-lookahead", "senior-engineer"},
    },
    # plan-writer inlines new-doc's rules rather than preloading the skill.
    "plan-writer": {
        "model": "opus",
        "skills": {"superpowers:writing-plans"},
    },
    "prod-inspector": {
        "model": "haiku",
        "skills": set(),
    },
    "backtest-runner": {
        "model": "sonnet",
        "skills": {"backtest-gate"},
    },
    # The code brief plan-writer reads instead of exploring (skills-tools.md,
    # Plan writing). Sonnet: it reads and excerpts, it does not design.
    "plan-briefer": {
        "model": "sonnet",
        "skills": set(),
    },
    # v145: one read-only reviewer parameterised by role. It loads the role
    # skill at run time, so it preloads none.
    "expert-reviewer": {
        "model": "sonnet",
        "skills": set(),
    },
}

VALID_MODELS = {"haiku", "sonnet", "opus"}


def _agent_files():
    if not AGENTS_DIR.is_dir():
        return []
    return sorted(AGENTS_DIR.glob("*.md"))


def _read_agent(name):
    """Return (frontmatter dict, body) for one agent, through the strict
    reader skills use. `- item` lines fold into the key above them, joined
    with ", "; an inline `[a, b]` list stays that literal text."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return parse_frontmatter(text)


def _skills(meta):
    raw = meta.get("skills", "").strip("[]")
    return {s.strip().strip("'\"") for s in raw.split(",") if s.strip()}


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_every_agent_declares_name_description_model(path):
    meta, _ = _read_agent(path.stem)
    assert meta.get("name") == path.stem
    assert len(meta.get("description", "")) >= 40
    assert meta.get("model") in VALID_MODELS


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_role_agent_pins_model_and_skills(name):
    meta, _ = _read_agent(name)
    assert meta.get("model") == EXPECTED[name]["model"]
    assert _skills(meta) == EXPECTED[name]["skills"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_role_agent_has_fixed_return_shape(name):
    _, body = _read_agent(name)
    assert "## Return shape" in body
    assert "BLOCKED:" in body


def test_prod_inspector_is_read_only():
    meta, body = _read_agent("prod-inspector")
    assert "Edit" not in meta.get("tools", "")
    assert "Write" not in meta.get("tools", "")
    for forbidden in ("restart", ".env", "docker compose up", "sed -i"):
        assert forbidden in body, f"body must name {forbidden!r} as forbidden"

# v145: the nine role skills expert-reviewer must name (spec § 1).
EXPERT_ROLES = ("quant-researcher", "staff-engineer", "veteran-trader",
                "risk-manager", "financial-advisor", "technical-analyst",
                "fundamental-analyst", "quant-engineer", "senior-engineer")


def test_expert_reviewer_is_read_only_and_knows_every_role():
    meta, body = _read_agent("expert-reviewer")
    tools = {t.strip() for t in meta.get("tools", "").split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash", "Skill"}
    missing = [role for role in EXPERT_ROLES if f"`{role}`" not in body]
    assert not missing, missing
    for word in ("BLOCKING", "ADVISORY", "CLEAN", "UNKNOWN ROLE"):
        assert word in body, word


# v154: agents are read through the same strict reader as skills.
@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_every_agent_description_is_read_without_its_quotes(path):
    description = _read_agent(path.stem)[0]["description"]
    assert description and description[0] != '"' and description[-1] != '"'


def test_dash_item_skills_fold_into_one_value():
    meta, _ = parse_frontmatter(
        "---\nname: x\nskills:\n  - no-lookahead\n  - senior-engineer\n---\n")
    assert _skills(meta) == {"no-lookahead", "senior-engineer"}
