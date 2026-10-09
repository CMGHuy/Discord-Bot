"""v145 § 3: every spec numbered v146 or above carries a **Panel:** line
directly below **Screen:**, naming one to three expert role skills.

A role skill is a `.claude/skills/<role>/SKILL.md` that declares `## Lens`
(tests/hooks/test_role_skills.py pins the roster). v145 and earlier are
exempt by number. A split spec carries the line in its _0-index part. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "docs/superpowers/specs"
SKILLS_DIR = ROOT / ".claude/skills"
LAST_EXEMPT = 145
MAX_ROLES = 3
PANEL = "**Panel:**"
SCREEN = "**Screen:**"

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_PART = re.compile(r"_(\d+)[a-z]?(?:-[^.]*)?\.md$")


def spec_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def carries_header(path: Path) -> bool:
    part = _PART.search(path.name)
    return part is None or part.group(1) == "0"


def checked_specs(specs_dir: Path = SPECS_DIR) -> list:
    return sorted(p for p in Path(specs_dir).rglob("*.md")
                  if (spec_number(p) or 0) > LAST_EXEMPT and carries_header(p))


def role_skills(skills_dir: Path = SKILLS_DIR) -> set:
    return {p.parent.name for p in Path(skills_dir).glob("*/SKILL.md")
            if "\n## Lens\n" in p.read_text(encoding="utf-8").replace("\r\n", "\n")}


def panel_roles(line: str) -> list:
    value = line[len(PANEL):]
    return [name.strip().strip("`") for name in value.split(",") if name.strip()]


def panel_problems(text: str, *, roles: set) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    at = next((i for i, line in enumerate(lines) if line.startswith(PANEL)), None)
    if at is None:
        return [f"missing {PANEL} line"]
    if at == 0 or not lines[at - 1].startswith(SCREEN):
        return [f"{PANEL} is not directly below {SCREEN}"]
    names = panel_roles(lines[at])
    if not 1 <= len(names) <= MAX_ROLES:
        return [f"{PANEL} names {len(names)} roles; 1 to {MAX_ROLES} allowed"]
    return [f"`{name}` is not a role skill" for name in names if name not in roles]


# -- unit tests -------------------------------------------------------------

ROLES = {"quant-researcher", "risk-manager", "veteran-trader", "staff-engineer"}


def _spec(panel=None, *, below_screen=True):
    lines = ["# v999 demo", "", "**Bump:** none", "**Edge:** none (integrity)"]
    if panel is not None and not below_screen:
        lines.append(f"{PANEL} {panel}")
    lines.append(f"{SCREEN} exempt (integrity)")
    if panel is not None and below_screen:
        lines.append(f"{PANEL} {panel}")
    return "\n".join(lines + ["", "## Why", "text"]) + "\n"


def test_one_to_three_known_roles_pass():
    assert panel_problems(_spec("staff-engineer"), roles=ROLES) == []
    text = _spec("quant-researcher, `risk-manager`, veteran-trader")
    assert panel_problems(text, roles=ROLES) == []


def test_a_missing_panel_line_fails():
    assert panel_problems(_spec(), roles=ROLES) == ["missing **Panel:** line"]


def test_a_panel_line_not_directly_below_screen_fails():
    problems = panel_problems(_spec("staff-engineer", below_screen=False), roles=ROLES)
    assert problems == ["**Panel:** is not directly below **Screen:**"]


def test_four_roles_fail():
    text = _spec("quant-researcher, risk-manager, veteran-trader, staff-engineer")
    assert "names 4 roles" in panel_problems(text, roles=ROLES)[0]


def test_an_empty_panel_fails():
    assert "names 0 roles" in panel_problems(_spec(""), roles=ROLES)[0]


def test_an_unknown_role_fails():
    problems = panel_problems(_spec("staff-engineer, gate"), roles=ROLES)
    assert problems == ["`gate` is not a role skill"]


def test_crlf_text_is_read_like_lf():
    assert panel_problems(_spec("staff-engineer").replace("\n", "\r\n"), roles=ROLES) == []


def test_role_skills_are_the_skills_that_declare_a_lens(tmp_path):
    for name, body in (("risk-manager", "# x\n\n## Lens\n\ntext\n"),
                       ("gate", "# x\n\n## Step 1\n\ntext\n")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}",
                                                  encoding="utf-8")
    assert role_skills(tmp_path) == {"risk-manager"}


def test_exempt_and_non_index_specs_are_skipped(tmp_path):
    names = ["2026-10-09-v145-roles.md", "2026-10-10-v146-a-design.md",
             "implemented/2026-10-11-v147-b-design.md",
             "2026-10-12-v148-c_0-index.md", "2026-10-12-v148-c_1-detail.md"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert {p.name for p in checked_specs(tmp_path)} == {
        "2026-10-10-v146-a-design.md", "2026-10-11-v147-b-design.md",
        "2026-10-12-v148-c_0-index.md"}


# -- the repository gate ----------------------------------------------------

def test_every_spec_above_v145_carries_a_valid_panel_line():
    roles = role_skills()
    problems = {p.relative_to(ROOT).as_posix():
                panel_problems(p.read_text(encoding="utf-8"), roles=roles)
                for p in checked_specs()}
    assert {path: found for path, found in problems.items() if found} == {}
