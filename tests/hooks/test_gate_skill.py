"""v213 § B: /gate is the pre-push gate -- pinned by structure, not wording.

The seven `## Step` headings come in the spec's order, and their bodies name
the complexity gate, the diff-selected run and the CI watch in that order.
`testrun.py full` may appear only on a line that says it is never run here or
is CI's; the description never mentions a full suite.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

GATE = ROOT / ".claude" / "skills" / "gate" / "SKILL.md"
STEP_RE = re.compile(r"^## Step (\d+) — (.+)$", re.MULTILINE)
# One word each step title must carry, in the spec's order.
TITLE_WORDS = ("cpu", "syntax", "complexity", "tests", "frontend", "commit", "ci")
# What the step bodies must name, in this order (spec § B, gate steps 3, 4, 7).
ORDERED_MARKERS = ("complexity_gate.py", "testrun.py changed", "§ Pipeline watch")


def _gate() -> tuple[dict[str, str], str]:
    return parse_frontmatter(GATE.read_text(encoding="utf-8"))


def _steps(body: str) -> list[tuple[int, str, str]]:
    """(number, title, heading plus body) per `## Step` heading, in file order."""
    matches = list(STEP_RE.finditer(body))
    steps = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        steps.append((int(match.group(1)), match.group(2), body[match.start():end]))
    return steps


def test_seven_steps_numbered_in_order():
    assert [number for number, _, _ in _steps(_gate()[1])] == list(range(1, 8))


def test_step_titles_follow_the_spec_order():
    titles = [title.lower() for _, title, _ in _steps(_gate()[1])]
    for title, word in zip(titles, TITLE_WORDS, strict=True):
        assert word in title, (title, word)


def test_gate_commands_appear_in_step_order():
    steps = _steps(_gate()[1])
    firsts = []
    for marker in ORDERED_MARKERS:
        hits = [number for number, _, text in steps if marker in text]
        assert hits, f"no step names {marker}"
        firsts.append(hits[0])
    assert firsts == sorted(set(firsts)), firsts


def test_full_suite_appears_only_as_never_or_ci():
    for line in GATE.read_text(encoding="utf-8").splitlines():
        if "testrun.py full" in line:
            assert "never" in line.lower() or "CI" in line, line


def test_description_does_not_mention_a_full_suite():
    description = _gate()[0]["description"].lower()
    assert "full" not in description, description


def test_frontend_step_runs_the_specs_without_cd():
    (_, _, text), = [step for step in _steps(_gate()[1]) if step[0] == 5]
    assert "ng-test.mjs" in text and "--include" in text
    assert "cd frontend" not in text


def test_gate_stays_slash_only_and_forked():
    meta, _ = _gate()
    assert meta["disable-model-invocation"] == "true"
    assert meta["context"] == "fork"
