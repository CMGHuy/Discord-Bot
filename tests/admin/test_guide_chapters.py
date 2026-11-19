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


def _write(root: Path, name: str, *, front: str | None = None, body: str = "Text.\n",
           title="Title", slug="what-it-is", order=1, reviewed_for="2.19.2",
           sources=("swingbot/config.py",)) -> Path:
    if front is None:
        src = "".join(f"  - {s}\n" for s in sources)
        front = (f"title: {title}\nslug: {slug}\norder: {order}\n"
                 f"reviewed_for: {reviewed_for}\nsources:\n{src}")
    path = root / name
    path.write_text(f"---\n{front}---\n{body}", encoding="utf-8")
    return path


# --- parse_chapter -----------------------------------------------------------

def test_parse_chapter_reads_front_matter_body_and_headings(tmp_path):
    path = _write(tmp_path, "01-what-it-is.md", title="What the bot is",
                  sources=("swingbot/config.py:MAX_STOP_LOSS_PCT", "swingbot/core/edge/sizing.py"),
                  body="\n> **In plain words** paper only.\n\n## The notice\n\nText.\n")
    chapter = ch.parse_chapter(path)
    assert chapter.slug == "what-it-is"
    assert chapter.title == "What the bot is"
    assert chapter.order == 1
    assert chapter.reviewed_for == "2.19.2"
    assert chapter.sources == ("swingbot/config.py:MAX_STOP_LOSS_PCT", "swingbot/core/edge/sizing.py")
    assert chapter.body.startswith("> **In plain words**")
    assert chapter.headings == (ch.Heading(2, "The notice", "the-notice"),)
    assert chapter.path == path


def test_parse_chapter_accepts_crlf_and_empty_sources(tmp_path):
    path = tmp_path / "03-pipeline.md"
    path.write_bytes(b"---\r\ntitle: Pipeline\r\nslug: pipeline\r\norder: 3\r\n"
                     b"reviewed_for: 2.19.2\r\nsources: []\r\n---\r\n## Boxes\r\n")
    chapter = ch.parse_chapter(path)
    assert chapter.sources == ()
    assert chapter.headings == (ch.Heading(2, "Boxes", "boxes"),)


@pytest.mark.parametrize("front, message", [
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\n", "sources"),
    ("title: ''\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n", "title"),
    ("title: T\nslug: What It Is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n", "slug"),
    ("title: T\nslug: what-it-is\norder: true\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: '1'\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: 0\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19\nsources: []\n", "reviewed_for"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: a.py\n", "sources"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: ['']\n", "sources"),
    ("- just\n- a list\n", "mapping"),
    ("title: [unclosed\n", "YAML"),
])
def test_parse_chapter_rejects_bad_front_matter(tmp_path, front, message):
    path = _write(tmp_path, "01-what-it-is.md", front=front)
    with pytest.raises(ch.GuideFormatError, match=message) as info:
        ch.parse_chapter(path)
    assert str(info.value).startswith("01-what-it-is.md: ")


def test_parse_chapter_requires_opening_and_closing_markers(tmp_path):
    no_open = tmp_path / "01-what-it-is.md"
    no_open.write_text("title: T\n", encoding="utf-8")
    with pytest.raises(ch.GuideFormatError, match="must open"):
        ch.parse_chapter(no_open)
    unclosed = tmp_path / "02-reading-an-alert.md"
    unclosed.write_text("---\ntitle: T\n", encoding="utf-8")
    with pytest.raises(ch.GuideFormatError, match="closing"):
        ch.parse_chapter(unclosed)


def test_parse_chapter_requires_the_file_name_to_match(tmp_path):
    path = _write(tmp_path, "02-what-it-is.md", order=1)
    with pytest.raises(ch.GuideFormatError, match="01-what-it-is.md"):
        ch.parse_chapter(path)


# --- load_chapters -----------------------------------------------------------

def test_load_chapters_sorts_by_order_and_skips_non_chapters(tmp_path):
    _write(tmp_path, "12-glossary.md", slug="glossary", order=12)
    _write(tmp_path, "03-pipeline.md", slug="pipeline", order=3)
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    (tmp_path / "README.md").write_text("not a chapter", encoding="utf-8")
    (tmp_path / "strategies").mkdir()
    _write(tmp_path / "strategies", "01-rsi.md", slug="rsi", order=1)
    assert [c.slug for c in ch.load_chapters(tmp_path)] == ["what-it-is", "pipeline", "glossary"]


def test_load_chapters_missing_directory_is_empty(tmp_path):
    assert ch.load_chapters(tmp_path / "absent") == []


def test_load_chapters_rejects_duplicate_slug(tmp_path):
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    _write(tmp_path, "02-what-it-is.md", slug="what-it-is", order=2)
    with pytest.raises(ch.GuideFormatError, match="slug 'what-it-is'"):
        ch.load_chapters(tmp_path)


def test_load_chapters_rejects_duplicate_order(tmp_path):
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    _write(tmp_path, "01-pipeline.md", slug="pipeline", order=1)
    with pytest.raises(ch.GuideFormatError, match="order 1 already used"):
        ch.load_chapters(tmp_path)


def test_load_chapters_defaults_to_guide_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    folder = tmp_path / "docs" / "guide"
    folder.mkdir(parents=True)
    _write(folder, "01-what-it-is.md")
    assert [c.slug for c in ch.load_chapters()] == ["what-it-is"]


# --- runtime dependency ------------------------------------------------------

def test_pyyaml_is_a_pinned_runtime_dependency():
    text = (Path(config._PROJECT_ROOT) / "requirements.txt").read_text(encoding="utf-8")
    runtime, _, test_only = text.partition("# Test-only dependencies")
    assert "PyYAML==6.0.3" in runtime.splitlines()
    assert "PyYAML" not in test_only
