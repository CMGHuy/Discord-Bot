"""Shape of the three generator role skills and the setup-scout playbook (v161 TS10).

Generators mirror the reviewer roles' file shape but open with
`## Generator lens`, so test_role_skills.py's lens_skills() never treats
them as reviewers. What is pinned is what a careless edit would remove:
the boundary sentences, the five-row cap, the Row format keys and order,
and each role's red-flag names (spec § 2)."""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

SKILLS_DIR = ROOT / ".claude" / "skills"
GENERATORS = ("exit-harvester", "setup-scout", "regime-desk")
SECTIONS = ("## Generator lens", "## Checklist", "## Red flags", "## Out of scope",
            "## Row format", "## Trigger table")
BOUNDARIES = ("never decide", "never lower a gate", "`pooled-numbers`", "`backtest-gate`",
              "at most 5 rows", "exploratory: yes", "`SCREEN-PASS`",
              "`docs/claude/skills-tools.md` § Generator roles (v161)")
ROW_KEYS = ("idea", "claim", "evidence", "exploratory", "edge", "mechanism", "order_form",
            "manual_actions", "pairs_with", "divergence", "route")
RED_FLAGS = {
    "exit-harvester": ("v129", "arm Z", "arm B", "v139", "`DATA_DRIVEN_STOPS_ENABLED`",
                       "tighter or wider", "fixed 2% risk", "R-unit inflation", "`manual_actions`"),
    "setup-scout": ("`high52w`", "`gap_volume`", "`turn_of_month`", "v122", "v127", "v128",
                    "v131", "v135", "v143", "v36", "v49", "v68"),
    "regime-desk": ("`REGIME_ALLOW`", "v17 P2a", "`EARNINGS_BLACKOUT_SESSIONS`", "v82",
                    "point-in-time", "`pairs_with`"),
}
PLAYBOOK = SKILLS_DIR / "setup-scout" / "references" / "playbook.md"
PLAYBOOK_IDS = ("gap-and-hold", "gap-fill-reversal", "tight-base-breakout",
                "rs-leader-index-pullback", "failed-breakdown-reclaim",
                "atr-reentry-after-stop", "three-bar-weekly-reversal")
AGENTS_MD = ROOT / "AGENTS.md"
CODEX_CAP_BYTES = 32 * 1024


def _text(path):
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(name):
    return parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))[1]


def _section(body, heading):
    start = body.index(heading + "\n") + len(heading)
    end = body.find("\n## ", start)
    return body[start:] if end == -1 else body[start:end]


@pytest.mark.parametrize("name", GENERATORS)
def test_frontmatter_names_the_skill(name):
    meta, _ = parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))
    assert meta["name"] == name
    assert len(meta["description"]) >= 40


@pytest.mark.parametrize("name", GENERATORS)
def test_sections_in_order_and_generator_lens_first(name):
    body = _body(name)
    positions = [body.find(h + "\n") for h in SECTIONS]
    assert -1 not in positions, dict(zip(SECTIONS, positions))
    assert positions == sorted(positions)
    assert re.search(r"^## .*$", body, re.M).group(0) == "## Generator lens"
    assert "\n## Lens\n" not in body          # never a reviewer role


@pytest.mark.parametrize("name", GENERATORS)
def test_boundary_sentences(name):
    body = _body(name)
    missing = [b for b in BOUNDARIES if b not in body]
    assert not missing, missing


@pytest.mark.parametrize("name", GENERATORS)
def test_row_format_lists_every_key_in_order(name):
    block = _section(_body(name), "## Row format")
    positions = [block.find(f"  {key}: ") if key != "idea" else block.find("- idea: ") for key in ROW_KEYS]
    assert -1 not in positions, dict(zip(ROW_KEYS, positions))
    assert positions == sorted(positions)
    assert "NO ROWS" in block


@pytest.mark.parametrize("name", GENERATORS)
def test_red_flags_name_the_closed_rows(name):
    flags = _section(_body(name), "## Red flags")
    missing = [f for f in RED_FLAGS[name] if f not in flags]
    assert not missing, missing


def test_setup_scout_cites_its_playbook_by_repo_path():
    assert "`.claude/skills/setup-scout/references/playbook.md`" in _body("setup-scout")


def test_playbook_has_every_seed_entry_with_an_order_form():
    text = _text(PLAYBOOK)
    for entry in PLAYBOOK_IDS:
        assert f"## `{entry}`" in text, entry
    for part in text.split("\n## `")[1:]:
        for field in ("Rule:", "Horizon:", "Order form:", "Failure mode:", "Must not duplicate:"):
            assert f"**{field}**" in part, (part.splitlines()[0], field)


@pytest.mark.parametrize("name", GENERATORS)
def test_codex_copy_exists(name):
    assert (ROOT / ".agents" / "skills" / name / "SKILL.md").is_file()


def test_agents_md_names_the_scout_tooling_and_stays_under_the_codex_cap():
    text = _text(AGENTS_MD)
    for name in ("trade-scout", "exit-harvester", "setup-scout", "regime-desk", "scout"):
        assert f"`{name}`" in text, name
    assert len(AGENTS_MD.read_bytes()) < CODEX_CAP_BYTES
