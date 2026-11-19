"""v235 V235-2/V235-2b: the guide chapter loader (docs/guide/NN-<slug>.md)."""
from pathlib import Path

import pytest

from swingbot import config
from swingbot.admin.guide import chapters as ch


# --- anchors -----------------------------------------------------------------

@pytest.mark.parametrize("text, anchor", [
    ("What the bot is (and isn't)", "what-the-bot-is-and-isnt"),
    ("Sizing & risk", "sizing-risk"),
    ("Break & Retest", "break-retest"),
    ("Support/Resistance", "supportresistance"),
    ("  --Hello__World--  ", "hello__world"),
    ("The 2% rule — three limits", "the-2-rule-three-limits"),
    ("`MAX_STOP_LOSS_PCT`", "max_stop_loss_pct"),
    ("!!!", "section"),
    ("", "section"),
])
def test_anchor_algorithm(text, anchor):
    assert ch.anchor_for(text, {}) == anchor


def test_repeated_anchor_gets_numbered_suffixes():
    seen: dict[str, int] = {}
    assert [ch.anchor_for("Notes", seen) for _ in range(3)] == ["notes", "notes-2", "notes-3"]
    assert ch.anchor_for("Other", seen) == "other"


# --- headings ----------------------------------------------------------------

def test_extract_headings_takes_h2_and_h3_outside_fences_only():
    md = (
        "# Title is not a section\n"
        "## First\n"
        "Text ## not a heading\n"
        "### Sub one ###\n"
        "#### Too deep\n"
        "```\n## inside a fence\n```\n"
        "~~~md\n### also fenced\n~~~\n"
        "## First\n"
        "##No space is not a heading\n"
    )
    assert ch.extract_headings(md) == (
        ch.Heading(2, "First", "first"),
        ch.Heading(3, "Sub one", "sub-one"),
        ch.Heading(2, "First", "first-2"),
    )


def test_extract_headings_keeps_a_hash_inside_the_text():
    assert ch.extract_headings("## Notes on C#\n") == (ch.Heading(2, "Notes on C#", "notes-on-c"),)


def test_extract_headings_empty_body():
    assert ch.extract_headings("") == ()


# --- sources, figures, location ----------------------------------------------

def test_split_source():
    assert ch.split_source("swingbot/config.py:RISK_PER_TRADE_PCT") == (
        "swingbot/config.py", "RISK_PER_TRADE_PCT")
    assert ch.split_source("swingbot/core/edge/sizing.py") == ("swingbot/core/edge/sizing.py", None)
    assert ch.split_source(" swingbot/config.py : X ") == ("swingbot/config.py", "X")


def test_figure_marker_regex():
    md = "Intro\n<!-- figure:pipeline -->\nMore\n  <!-- figure:indented -->\n"
    assert ch.FIGURE_RE.findall(md) == ["pipeline"]


def test_guide_dir_reads_the_project_root_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    assert ch.guide_dir() == Path(tmp_path) / "docs" / "guide"


def test_chapter_is_frozen():
    chapter = ch.Chapter(slug="a", title="A", order=1, reviewed_for="2.19.2", sources=(),
                         body="", headings=(), path=Path("01-a.md"))
    with pytest.raises(AttributeError):
        chapter.slug = "b"
