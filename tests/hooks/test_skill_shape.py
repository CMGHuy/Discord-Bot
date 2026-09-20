"""Shape contract for .claude/skills/*/SKILL.md -- v96.

Keeps the skills layer from becoming a third source of truth. The budget and
the no-threshold rule are the spec's, not pytest's; this file only makes them
mechanical. See docs/superpowers/specs/2026-09-18-v96-claude-skills-layer-design.md
"""
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"

# Predate v96's 80-line budget. Not exemptions to copy -- the list never grows.
GRANDFATHERED = {"gate", "task-brief"}

MAX_SKILL_LINES = 80

# Tier 1 and Tier 3 are model-invocable, so they carry a trigger table.
# Tier 2 is slash-only and carries disable-model-invocation instead.
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle"}   # each skill task appends its own name
TIER_2 = {"close-out", "new-doc", "deploy"}        # each ritual task appends its own name

# A bare threshold in a SKILL.md is content that belongs in docs/claude/.
# Dates, version numbers and step numbers are not thresholds.
_THRESHOLD_RE = re.compile(
    r"(?<![\w.-])(?:>=|<=|>|<|=)\s*\d+(?:\.\d+)?%?|"
    r"\b\d+(?:\.\d+)?\s*(?:pp|R)\b"
)


def _skill_dirs():
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


def _read_skill(name):
    """Return (frontmatter dict, body) for one skill. Frontmatter is the
    simple `key: value` subset this repo's skills actually use."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_skill_declares_name_and_description(path):
    meta, _ = _read_skill(path.name)
    assert meta.get("name") == path.name
    assert len(meta.get("description", "")) >= 40


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_new_skills_stay_within_the_line_budget(path):
    if path.name in GRANDFATHERED:
        pytest.skip("predates the v96 budget")
    lines = (path / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_new_skills_restate_no_thresholds(path):
    if path.name in GRANDFATHERED:
        pytest.skip("predates the v96 no-restatement rule")
    _, body = _read_skill(path.name)
    hits = _THRESHOLD_RE.findall(body)
    assert not hits, f"{path.name} restates {hits}; cite docs/claude/ instead"


def test_model_invocable_skills_carry_a_trigger_table():
    for name in sorted(TIER_1_AND_3):
        meta, body = _read_skill(name)
        assert "disable-model-invocation" not in meta
        assert "## Trigger table" in body
        assert body.count("Should fire:") >= 3
        assert body.count("Should not fire:") >= 3


def test_ritual_skills_are_slash_only():
    for name in sorted(TIER_2):
        meta, _ = _read_skill(name)
        assert meta.get("disable-model-invocation") == "true"
