"""Shape contract for .claude/skills/*/SKILL.md -- v96.

Keeps the skills layer from becoming a third source of truth. The budget and
the no-threshold rule are the spec's, not pytest's; this file only makes them
mechanical. See docs/superpowers/specs/implemented/2026-09-18-v96-claude-skills-layer-design.md
"""
import pathlib
import re
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev"))

from skill_frontmatter import FrontmatterError, parse_frontmatter  # noqa: E402

SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"

# Predate v96's 80-line budget. Not exemptions to copy -- the list never grows.
GRANDFATHERED = {"gate", "task-brief"}

# Third-party skills kept verbatim from their vendor (partner-approved
# exception, 2026-10-10): exempt from the line budget and threshold rules,
# since trimming would fork the vendor file. Never add repo-authored skills.
VENDORED = {"etoro-public-api-operations"}

MAX_SKILL_LINES = 80

# Tier 1 and Tier 3 are model-invocable, so they carry a trigger table.
# Tier 2 is slash-only and carries disable-model-invocation instead.
TIER_1_AND_3 = {"backtest-gate", "no-lookahead", "pooled-numbers", "mirror-prod", "edge-module", "alert-surface", "schema-change", "worktree-lifecycle",
                "quant-researcher", "risk-manager", "financial-advisor",
                "veteran-trader", "technical-analyst", "fundamental-analyst",
                "staff-engineer", "quant-engineer", "senior-engineer"}   # each skill task appends its own name
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest", "handoff", "screen", "prereg", "data-check"}        # each ritual task appends its own name
# Rituals the partner lets Claude run on its own (2026-10-08). Still checklists
# with no Trigger table; their description names the moment they run.
MODEL_RUN_RITUALS = {"close-out", "new-doc", "panel"}

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
    """Return (frontmatter dict, body) for one skill, through the strict
    reader the Codex mirror also uses: frontmatter the real loader rejects
    raises FrontmatterError here instead of passing quietly."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    return parse_frontmatter(text)


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_skill_declares_name_and_description(path):
    meta, _ = _read_skill(path.name)
    assert meta.get("name") == path.name
    assert len(meta.get("description", "")) >= 40


def _new_skill_dirs():
    """Skills the v96 budget and no-restatement rules apply to."""
    return [p for p in _skill_dirs() if p.name not in GRANDFATHERED | VENDORED]


@pytest.mark.parametrize("path", _new_skill_dirs(), ids=lambda p: p.name)
def test_new_skills_stay_within_the_line_budget(path):
    lines = (path / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES


@pytest.mark.parametrize("path", _new_skill_dirs(), ids=lambda p: p.name)
def test_new_skills_restate_no_thresholds(path):
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


# v107: mechanical slash skills run forked on a cheaper model. task-brief is
# sonnet, not the spec's haiku: its trap preflight is judgement, and a missed
# trap costs a whole implement/review loop. v154: result-digest runs one
# script and returns its output untouched, which needs no judgement: haiku.
# v155: data-check runs one script and reads its last line, which needs no
# judgement: haiku.
FORKED = {"gate": "sonnet", "task-brief": "sonnet", "result-digest": "haiku",
          "data-check": "haiku"}


@pytest.mark.parametrize("name", sorted(FORKED))
def test_mechanical_skills_run_forked(name):
    meta, _ = _read_skill(name)
    assert meta.get("context") == "fork"
    assert meta.get("model") == FORKED[name]


def test_ritual_skills_are_slash_only():
    for name in sorted(TIER_2 - MODEL_RUN_RITUALS):
        meta, _ = _read_skill(name)
        assert meta.get("disable-model-invocation") == "true"


def test_model_run_rituals_are_invocable_and_say_when():
    for name in sorted(MODEL_RUN_RITUALS):
        meta, _ = _read_skill(name)
        assert "disable-model-invocation" not in meta
        assert f"Run as /{name}, or by Claude itself" in meta["description"]


def test_every_skill_is_registered_in_exactly_one_tier():
    on_disk = {p.name for p in _skill_dirs()}
    assert on_disk == GRANDFATHERED | VENDORED | TIER_1_AND_3 | TIER_2
    assert not (TIER_1_AND_3 & TIER_2)


def test_backup_skills_match_the_v120_final_fixes():
    snap = (SKILLS_DIR / "stable-snapshot" / "SKILL.md").read_text(encoding="utf-8")
    pull = (SKILLS_DIR / "backup-pull" / "SKILL.md").read_text(encoding="utf-8")
    # every ssh command that runs git does so as the deploy user
    assert "runuser -u deploy -- git -C /opt/swing-bot rev-parse HEAD" in snap
    for line in snap.splitlines():
        if "ssh-hetzner.sh" in line or "/opt/swing-bot" in line:
            assert not re.search(r"(?<!-- )git -C", line), line
    # Step 4: a failed snapshot is never tagged
    assert "do NOT tag" in snap
    # Step 5: image references, by their manifest field names, not digests
    assert "digest" not in snap.lower()
    assert "`bot_image`" in snap and "`db_image`" in snap and "image references" in snap
    # Step 6: recovery for a leftover .partial
    assert "deletes the .partial by hand" in snap and "re-runs Step 6 only" in snap
    # the off-VM copy lives in the main tree's backups/
    assert "main tree's `backups/" in snap and "main tree's `backups/" in pull
    # FAIL wording matches the script's stderr line
    assert "pull_backups: FAIL" in pull


# v154: the reader is scripts/dev/skill_frontmatter.py, which rejects what the
# real loader rejects. The fixture is the frontmatter six role skills shipped
# with in v145 -- they listed under their title-cased name and never triggered
# while the old colon splitter here kept the suite green.
BROKEN_FIXTURE = _REPO_ROOT / "tests" / "hooks" / "fixtures" / "broken_frontmatter_SKILL.md"


def test_the_reader_rejects_the_frontmatter_that_shipped_broken():
    with pytest.raises(FrontmatterError, match="frontmatter line 3"):
        parse_frontmatter(BROKEN_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_description_is_read_without_its_quotes(path):
    description = _read_skill(path.name)[0]["description"]
    assert description and description[0] != '"' and description[-1] != '"'


# v154: the fixed line /result-digest ends every reply with. The figures it
# hands back are derived from two files, never the live book.
DIGEST_DISCLAIMER = ("Derived by compare_backtest_json.py from the named files; "
                     "not live-book figures — re-derive per pooled-numbers before "
                     "quoting in a spec, plan or commit.")


def test_result_digest_returns_the_script_output_verbatim():
    """v154: a small model paraphrases figures. The skill runs the one script
    on both files, hands its output back untouched, explains the script's
    hard-coded header and missing window, and ends with the disclaimer."""
    _, body = _read_skill("result-digest")
    assert "python scripts/backtest/compare_backtest_json.py <a.json> <b.json>" in body
    assert "$ARGUMENTS" in body
    assert "**verbatim**" in body
    assert "never call a result a" in body
    assert '"=== v35 AVWAP comparison ===" line is the script\'s own' in body
    assert "the script prints none" in body
    assert "no figures anywhere in the reply" in body
    assert DIGEST_DISCLAIMER in body


def test_handoff_writes_the_plan_handoff_block_in_the_main_context():
    """v154: /handoff records decisions taken in the conversation, so it
    never forks, and it writes the block skills-tools.md § Plan writing
    defines -- appending to it, never rewriting what is already there."""
    meta, body = _read_skill("handoff")
    assert "context" not in meta and "model" not in meta
    assert "`## Handoff`" in body
    assert "docs/claude/skills-tools.md" in body
    assert "Handing a plan to another session or account" in body
    assert "AskUserQuestion" in body
    assert "never rewrite, renumber or delete" in body
    assert "write nothing" in body
