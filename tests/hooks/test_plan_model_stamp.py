"""v145 § 4: in every plan numbered v146 or above, the first non-blank line
under each `### Task` heading is `**Model:** <haiku|sonnet|opus> — <reason>`.

The controller passes that tier as the `model` override when it dispatches
task-implementer; the rubric is docs/claude/model-routing.md. v145 and earlier
are exempt by number. Every part of a split plan is checked, since tasks live
in the parts. Headings inside fenced code blocks are examples, not tasks. See
docs/superpowers/specs/2026-10-09-v145-expert-roles-model-routing.md
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = ROOT / "docs/superpowers/plans"
LAST_EXEMPT = 145

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_TASK = re.compile(r"^### Task ")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_STAMP = re.compile(r"^\*\*Model:\*\* (haiku|sonnet|opus) (—|--) \S")


def plan_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def checked_plans(plans_dir: Path = PLANS_DIR) -> list:
    return sorted(p for p in Path(plans_dir).rglob("*.md")
                  if (plan_number(p) or 0) > LAST_EXEMPT)


def _fence_after(fence: str | None, marker: str) -> str | None:
    """The open fence after a fence line: a closing marker must use the
    opening character and be at least as long (CommonMark)."""
    if fence is None:
        return marker
    return None if marker[0] == fence[0] and len(marker) >= len(fence) else fence


def task_headings(lines: list) -> list:
    """Indexes of `### Task` lines outside fenced code blocks."""
    found, fence = [], None
    for i, line in enumerate(lines):
        match = _FENCE.match(line)
        if match:
            fence = _fence_after(fence, match.group(1))
        elif fence is None and _TASK.match(line):
            found.append(i)
    return found


def _first_line_after(lines: list, index: int) -> str:
    return next((line for line in lines[index + 1:] if line.strip()), "")


def stamp_problems(text: str) -> list:
    lines = text.replace("\r\n", "\n").split("\n")
    return [f"{lines[i].strip()}: first line is not a valid **Model:** stamp"
            for i in task_headings(lines)
            if not _STAMP.match(_first_line_after(lines, i))]


# -- unit tests -------------------------------------------------------------

def _plan(*stamps):
    body = ["# v999 plan", "", "**Bump:** none", ""]
    for n, stamp in enumerate(stamps, 1):
        body += [f"### Task V999-{n}: thing {n}", ""]
        if stamp is not None:
            body.append(stamp)
        body += ["", "- [ ] **Step 1: do it**", ""]
    return "\n".join(body)


def test_every_tier_with_a_reason_passes():
    text = _plan("**Model:** haiku — doc edit", "**Model:** sonnet -- one module",
                 "**Model:** opus — entry signal")
    assert stamp_problems(text) == []


def test_a_missing_stamp_names_the_task():
    problems = stamp_problems(_plan("**Model:** sonnet — fine", None))
    assert problems == ["### Task V999-2: thing 2: first line is not a valid **Model:** stamp"]


def test_an_unknown_tier_fails():
    assert stamp_problems(_plan("**Model:** gpt — no")) != []


def test_a_stamp_without_a_reason_fails():
    assert stamp_problems(_plan("**Model:** opus")) != []


def test_the_stamp_must_be_the_first_line():
    text = "### Task V999-1: x\n\n**Files:** a.py\n**Model:** sonnet — late\n"
    assert stamp_problems(text) != []


def test_task_headings_inside_fences_are_ignored():
    text = _plan("**Model:** haiku — x") + "\n```markdown\n### Task A9: example\n```\n"
    assert stamp_problems(text) == []


def test_a_longer_fence_is_not_closed_by_a_shorter_one():
    text = (_plan("**Model:** haiku — x")
            + "\n````markdown\n```bash\n### Task A9: example\n````\n")
    assert stamp_problems(text) == []


def test_crlf_text_is_read_like_lf():
    assert stamp_problems(_plan("**Model:** haiku — x").replace("\n", "\r\n")) == []


def test_exempt_plans_are_skipped_and_parts_are_checked(tmp_path):
    names = ["2026-10-09-v145-roles_1-skills.md", "2026-10-10-v146-a.md",
             "implemented/2026-10-11-v147-b.md", "2026-10-12-v148-c_0-index.md",
             "2026-10-12-v148-c_1-detail.md", "notes.md"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert {p.name for p in checked_plans(tmp_path)} == {
        "2026-10-10-v146-a.md", "2026-10-11-v147-b.md",
        "2026-10-12-v148-c_0-index.md", "2026-10-12-v148-c_1-detail.md"}


# -- the repository gate ----------------------------------------------------

def test_every_plan_above_v145_stamps_a_model_on_every_task():
    problems = {p.relative_to(ROOT).as_posix(): stamp_problems(p.read_text(encoding="utf-8"))
                for p in checked_plans()}
    assert {path: found for path, found in problems.items() if found} == {}
