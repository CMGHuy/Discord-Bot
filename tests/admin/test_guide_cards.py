"""v237 V237-4: strategy card files under docs/guide/strategies/."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from swingbot.admin.guide import cards, chapters
from swingbot.admin.guide.chapters import GuideFormatError

_SOURCE = "swingbot/core/market/entry_filters.py:break_retest_entries"


def _card(folder: Path, name: str, *, front: str | None = None,
          body: str = "**Idea.** Buy the retest of a broken high.\n",
          strategy: str = "Break & Retest", reviewed_for: str = "2.19.2",
          sources=(_SOURCE,)) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    if front is None:
        src = "".join(f"  - {s}\n" for s in sources)
        front = f'strategy: "{strategy}"\nreviewed_for: {reviewed_for}\nsources:\n{src}'
    path = folder / name
    path.write_text(f"---\n{front}---\n{body}", encoding="utf-8")
    return path


# --- parse_card ------------------------------------------------------------------

def test_parse_card_reads_every_field(tmp_path):
    path = _card(tmp_path, "break-retest.md", body="\n**Idea.** Retest.\n\n- one\n\n")
    card = cards.parse_card(path)
    assert card == cards.StrategyCard(path=path, strategy="Break & Retest",
                                      reviewed_for="2.19.2", sources=(_SOURCE,),
                                      body="**Idea.** Retest.\n\n- one")


def test_parse_card_accepts_crlf_and_a_slash_in_the_key(tmp_path):
    path = _card(tmp_path, "supportresistance.md", strategy="Support/Resistance")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    card = cards.parse_card(path)
    assert card.strategy == "Support/Resistance" and "\r" not in card.body


def test_strategy_card_is_frozen(tmp_path):
    card = cards.parse_card(_card(tmp_path, "break-retest.md"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.strategy = "RSI"


@pytest.mark.parametrize("front, message", [
    ("reviewed_for: 2.19.2\nsources:\n  - a.py\n", "front matter lacks 'strategy'"),
    ('strategy: ""\nreviewed_for: 2.19.2\nsources:\n  - a.py\n', "'strategy' must be a non-empty string"),
    ("strategy: 7\nreviewed_for: 2.19.2\nsources:\n  - a.py\n", "'strategy' must be a non-empty string"),
    ("strategy: RSI\nsources:\n  - a.py\n", "front matter lacks 'reviewed_for'"),
    ("strategy: RSI\nreviewed_for: 2.19\nsources:\n  - a.py\n", "'reviewed_for' must be an X.Y.Z version string"),
    ("strategy: RSI\nreviewed_for: 2.19.2\n", "front matter lacks 'sources'"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources: []\n", "'sources' must be a non-empty list"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources: a.py\n", "'sources' must be a non-empty list"),
    ("strategy: RSI\nreviewed_for: 2.19.2\nsources:\n  - ''\n", "'sources' must be a non-empty list"),
])
def test_parse_card_rejects_bad_front_matter(tmp_path, front, message):
    path = _card(tmp_path, "rsi.md", front=front)
    with pytest.raises(GuideFormatError, match=message) as info:
        cards.parse_card(path)
    assert str(info.value).startswith("rsi.md: ")


def test_parse_card_requires_front_matter(tmp_path):
    path = tmp_path / "rsi.md"
    path.write_text("**Idea.** No front matter.\n", encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md: must open with a '---'"):
        cards.parse_card(path)


def test_parse_card_requires_the_file_name_to_match_the_key(tmp_path):
    path = _card(tmp_path, "break-and-retest.md")
    with pytest.raises(GuideFormatError,
                       match="break-and-retest.md: file name must be break-retest.md"):
        cards.parse_card(path)


@pytest.mark.parametrize("body, message", [
    ("", "body is empty"),
    ("\n\n  \n", "body is empty"),
    ("**Idea.** x\n## Entry rule\n- y\n", "line 2 is a heading"),
    ("# Title\n**Idea.** x\n", "line 1 is a heading"),
    ("**Idea.** Risk {{RISK_PER_TRADE_PCT}}.\n", "may not contain a placeholder"),
])
def test_parse_card_rejects_bad_bodies(tmp_path, body, message):
    path = _card(tmp_path, "break-retest.md", body=body)
    with pytest.raises(GuideFormatError, match=message):
        cards.parse_card(path)


def test_a_hash_inside_a_line_is_not_a_heading(tmp_path):
    card = cards.parse_card(_card(tmp_path, "break-retest.md", body="**Idea.** Rank #1 setup.\n"))
    assert card.body == "**Idea.** Rank #1 setup."


# --- load_cards ------------------------------------------------------------------

def test_load_cards_sorted_by_file_name_and_md_only(tmp_path):
    folder = tmp_path / "strategies"
    _card(folder, "rsi.md", strategy="RSI")
    _card(folder, "break-retest.md")
    (folder / "notes.txt").write_text("not a card", encoding="utf-8")
    assert [c.path.name for c in cards.load_cards(tmp_path)] == ["break-retest.md", "rsi.md"]


def test_load_cards_missing_folder_is_empty(tmp_path):
    assert cards.load_cards(tmp_path) == []
    assert cards.load_cards(tmp_path / "absent") == []


def test_load_cards_raises_on_the_first_malformed_card(tmp_path):
    folder = tmp_path / "strategies"
    _card(folder, "break-retest.md")
    (folder / "rsi.md").write_text("no front matter\n", encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md"):
        cards.load_cards(tmp_path)


def test_cards_dir_defaults_to_the_guide_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(chapters, "guide_dir", lambda: tmp_path)
    assert cards.cards_dir() == tmp_path / "strategies"
    assert cards.cards_dir(tmp_path / "x") == tmp_path / "x" / "strategies"
    _card(tmp_path / "strategies", "break-retest.md")
    assert [c.strategy for c in cards.load_cards()] == ["Break & Retest"]
