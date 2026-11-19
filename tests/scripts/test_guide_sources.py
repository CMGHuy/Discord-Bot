"""v235 V235-7: guide_sources.py names the guide chapters a diff touches."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import guide_sources as gs  # noqa: E402
from swingbot.admin.guide.chapters import GuideFormatError, load_chapters  # noqa: E402


def _front(slug: str, order: int | None, sources: list[str]) -> str:
    listed = "".join(f"\n  - {s}" for s in sources) if sources else " []"
    order_line = f"order: {order}\n" if order is not None else ""
    return (f"---\ntitle: T {slug}\nslug: {slug}\n{order_line}"
            f"reviewed_for: 2.19.2\nsources:{listed}\n---\nBody.\n")


def _chapter(root: Path, order: int, slug: str, sources: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{order:02d}-{slug}.md").write_text(_front(slug, order, sources), encoding="utf-8")


def _card(root: Path, name: str, sources: list[str]) -> None:
    folder = root / "strategies"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(_front(name, None, sources), encoding="utf-8")


def test_touched_matches_exact_paths_and_directories(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/core/market/strategy_types.py:HORIZONS",
                                         "VERSION.json"])
    _chapter(tmp_path, 3, "pipeline", ["swingbot/core/scanning/", "swingbot/core/planning"])
    changed = ["swingbot/core/scanning/scan_run.py", "swingbot/core/planning/builders.py",
               "swingbot/core/market/strategy_types.py", "README.md",
               "swingbot/core/planning_extra.py"]
    result = gs.touched(changed, load_chapters(tmp_path))
    assert [(c.slug, paths) for c, paths in result] == [
        ("what-it-is", ["swingbot/core/market/strategy_types.py"]),
        ("pipeline", ["swingbot/core/planning/builders.py", "swingbot/core/scanning/scan_run.py"])]


def test_touched_normalises_paths_and_ignores_blanks(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py:MAX_STOP_LOSS_PCT",
                                         "swingbot/config.py:RISK_PER_TRADE_PCT", "VERSION.json"])
    result = gs.touched(["swingbot\\config.py", "", "  ", "./VERSION.json"], load_chapters(tmp_path))
    assert [paths for _, paths in result] == [["VERSION.json", "swingbot/config.py"]]


def test_touched_is_empty_when_no_source_changes(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py"])
    assert gs.touched(["frontend/src/app/app.ts"], load_chapters(tmp_path)) == []
    assert gs.touched([], load_chapters(tmp_path)) == []


def test_strategy_cards_are_scanned(tmp_path):
    assert gs.load_cards(tmp_path) == []
    _card(tmp_path, "rsi", ["swingbot/core/market/strategy.py:STRATEGY_FUNCS"])
    _card(tmp_path, "break-retest", [])
    cards = gs.load_cards(tmp_path)
    assert [c.path.name for c in cards] == ["break-retest.md", "rsi.md"]
    assert cards[1].sources == ("swingbot/core/market/strategy.py:STRATEGY_FUNCS",)
    result = gs.touched(["swingbot/core/market/strategy.py"], cards)
    assert [(c.path.name, paths) for c, paths in result] == [
        ("rsi.md", ["swingbot/core/market/strategy.py"])]


@pytest.mark.parametrize("text", ["no front matter\n", "---\nsources: nope\n---\nBody.\n",
                                  "---\ntitle: open front matter\n"])
def test_malformed_card_is_a_format_error(tmp_path, text):
    (tmp_path / "strategies").mkdir()
    (tmp_path / "strategies" / "rsi.md").write_text(text, encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md"):
        gs.load_cards(tmp_path)


def test_card_fence_is_a_whole_line_not_a_prefix(tmp_path):
    folder = tmp_path / "strategies"
    folder.mkdir()
    card = folder / "rsi.md"
    card.write_text("---\nsources: []\n----\nBody.\n", encoding="utf-8")   # '----' is no fence
    with pytest.raises(GuideFormatError, match="rsi.md"):
        gs.load_cards(tmp_path)
    card.write_text("---\nsources:\n  - a.py\n---\nBody.\n\n---\n\nMore.\n", encoding="utf-8")
    assert gs.load_cards(tmp_path)[0].sources == ("a.py",)   # a body rule is fine


def test_unreadable_card_is_a_format_error_and_main_exits_2(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "strategies"
    folder.mkdir()
    (folder / "rsi.md").write_bytes(b"---\nsources: []\n---\n\xff\xfe\n")
    with pytest.raises(GuideFormatError, match="rsi.md"):
        gs.load_cards(tmp_path)
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: [])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "rsi.md" in err and len(err.strip().splitlines()) == 1


def test_main_prints_chapters_then_cards(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: [
        "swingbot/config.py", "swingbot/core/market/strategy.py", "docs/notes.md"])
    _chapter(tmp_path, 3, "pipeline", ["swingbot/core/market/"])
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py:MAX_STOP_LOSS_PCT"])
    _card(tmp_path, "rsi", ["swingbot/core/market/strategy.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "01-what-it-is.md: swingbot/config.py",
        "03-pipeline.md: swingbot/core/market/strategy.py",
        "strategies/rsi.md: swingbot/core/market/strategy.py"]


def test_main_says_when_nothing_is_touched(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: ["README.md"])
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == gs.NONE_TOUCHED == "guide: no chapter sources touched"


def test_main_with_an_absent_guide_touches_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: ["swingbot/config.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path / "missing")]) == 0
    assert capsys.readouterr().out.strip() == gs.NONE_TOUCHED


def test_main_reports_a_malformed_chapter(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: [])
    (tmp_path / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 2
    assert "01-what-it-is.md" in capsys.readouterr().err


@pytest.mark.parametrize("rev_range", ["HEAD", "main", "-x..HEAD"])
def test_a_range_without_two_dots_is_rejected(rev_range):
    with pytest.raises(ValueError, match="<base>..<head>"):
        gs.changed_paths(rev_range)


def test_bad_range_exits_2(capsys):
    assert gs.main(["not-a-range"]) == 2
    assert "<base>..<head>" in capsys.readouterr().err


def test_unknown_revision_exits_2(capsys):
    assert gs.main(["no-such-rev-v235..HEAD"]) == 2
    assert capsys.readouterr().err.startswith("guide_sources: ")


def test_an_empty_range_has_no_changed_paths():
    assert gs.changed_paths("HEAD..HEAD") == []
