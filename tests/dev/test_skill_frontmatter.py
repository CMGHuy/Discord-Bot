"""scripts/dev/skill_frontmatter.py reads what the skill loader reads and
rejects what it rejects (v154 section 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import (  # noqa: E402
    FrontmatterError, parse_frontmatter, quote_value)

BROKEN_FIXTURE = ROOT / "tests" / "hooks" / "fixtures" / "broken_frontmatter_SKILL.md"


def _doc(*lines: str, body: str = "# Title\n") -> str:
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def test_text_without_an_opening_fence_has_no_frontmatter():
    assert parse_frontmatter("# Just a doc\n") == ({}, "# Just a doc\n")


def test_crlf_is_normalised_before_anything_else():
    meta, body = parse_frontmatter("---\r\nname: gate\r\n---\r\n# Gate\r\n")
    assert meta == {"name": "gate"}
    assert body == "# Gate\n"


def test_an_opening_fence_with_no_closing_fence_raises():
    with pytest.raises(FrontmatterError, match="line 1.*no closing ---"):
        parse_frontmatter("---\nname: gate\n# Gate\n")


def test_body_is_everything_after_the_closing_fence_line():
    text = _doc("name: gate", body="\n# Gate\n\n---\n\nrule below a rule\n")
    assert parse_frontmatter(text)[1] == "\n# Gate\n\n---\n\nrule below a rule\n"


def test_a_double_quoted_value_comes_back_without_its_quotes():
    meta, _ = parse_frontmatter(_doc(
        'description: "is it tradeable: fills, gaps #1 and a \\"quote\\" and a \\\\"'))
    assert meta["description"] == 'is it tradeable: fills, gaps #1 and a "quote" and a \\'


def test_an_unquoted_value_is_stripped():
    meta, _ = parse_frontmatter(_doc("name:    gate   ", "tools: Bash, Read, Grep"))
    assert meta == {"name": "gate", "tools": "Bash, Read, Grep"}


def test_every_value_is_a_string():
    meta, _ = parse_frontmatter(_doc(
        "disable-model-invocation: true", "context: fork",
        "skills: [superpowers:writing-plans, no-lookahead]", "empty:"))
    assert meta == {"disable-model-invocation": "true", "context": "fork",
                    "skills": "[superpowers:writing-plans, no-lookahead]",
                    "empty": ""}


def test_dash_items_fold_into_the_key_above_them():
    meta, _ = parse_frontmatter(_doc(
        "name: task-reviewer", "skills:", "  - no-lookahead",
        "  - senior-engineer", "model: sonnet"))
    assert meta["skills"] == "no-lookahead, senior-engineer"
    assert meta["model"] == "sonnet"


def test_blank_frontmatter_lines_are_skipped():
    assert parse_frontmatter(_doc("name: gate", "", "model: sonnet"))[0] == {
        "name": "gate", "model": "sonnet"}


@pytest.mark.parametrize("line, reason", [
    ("description: whether a setup is tradeable: fills and gaps", "': '"),
    ("description: follows the ### Task ids convention", "' #'"),
    ('description: "an unescaped "inner" quote"', "after the closing quote"),
    ('description: "closed" and then more', "after the closing quote"),
    ('description: "never closed', "no closing quote"),
    ('description: "a \\n newline escape"', "unsupported escape"),
    ("just some words", "not a `key: value` line"),
    ("  continued: on an indented line", "not a `key: value` line"),
    ("name:gate", "not a `key: value` line"),
])
def test_what_the_loader_rejects_or_misreads_raises(line, reason):
    with pytest.raises(FrontmatterError) as err:
        parse_frontmatter(_doc("name: x", line))
    assert "frontmatter line 3" in str(err.value)
    assert reason in str(err.value)


def test_a_dash_item_before_any_key_raises():
    with pytest.raises(FrontmatterError, match="line 2.*before any key"):
        parse_frontmatter(_doc("- orphan", "name: x"))


def test_quote_value_escapes_backslash_then_quote():
    assert quote_value('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'
    assert quote_value("") == '""'


@pytest.mark.parametrize("value", [
    "plain text",
    "is it tradeable: fills, gaps",
    "the ### Task ids convention",
    'a "quoted" word',
    "a back\\slash and a trailing one\\",
    "em dash — and a 2% cap",
    "",
])
def test_quote_value_round_trips_through_the_parser(value):
    text = f"---\ndescription: {quote_value(value)}\n---\n"
    assert parse_frontmatter(text)[0]["description"] == value


def test_the_frontmatter_that_shipped_broken_is_rejected():
    """Six role skills shipped with this shape in v145 and never triggered."""
    with pytest.raises(FrontmatterError) as err:
        parse_frontmatter(BROKEN_FIXTURE.read_text(encoding="utf-8"))
    assert "frontmatter line 3" in str(err.value)
    assert "': '" in str(err.value)


def test_quoting_the_broken_description_is_the_whole_repair():
    lines = BROKEN_FIXTURE.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    prefix = "description: "
    assert lines[2].startswith(prefix)
    value = lines[2][len(prefix):]
    lines[2] = prefix + quote_value(value)
    meta, body = parse_frontmatter("\n".join(lines))
    assert meta == {"name": "veteran-trader", "description": value}
    assert "tradeable: fills" in meta["description"]
    assert body.startswith("\n# Veteran trader\n")
