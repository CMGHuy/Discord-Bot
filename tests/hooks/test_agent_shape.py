"""Shape contract for .claude/agents/*.md -- v107.

Pins each role agent's model and preloaded skills so a cost decision made in
the v107 spec cannot drift silently. See
docs/superpowers/specs/2026-09-27-v107-token-budget-agents.md
"""
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
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
        "skills": {"no-lookahead"},
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
}

VALID_MODELS = {"haiku", "sonnet", "opus"}


def _agent_files():
    if not AGENTS_DIR.is_dir():
        return []
    return sorted(AGENTS_DIR.glob("*.md"))


def _read_agent(name):
    """Return (frontmatter dict, body) -- the simple `key: value` subset,
    plus YAML `- item` lines collected under the preceding list key."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, fm, body = text.split("---", 2)
    meta, key = {}, None
    for line in fm.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and key:
            meta[key] = ", ".join(filter(None, [meta[key], stripped[2:]]))
        elif ":" in line and not line.startswith(" "):
            key, v = (s.strip() for s in line.split(":", 1))
            meta[key] = v
    return meta, body


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
