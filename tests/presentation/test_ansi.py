import pytest

from swingbot.core.presentation import ansi


def test_paint_wraps_text_in_an_escape_pair():
    assert ansi.paint("LONG", "green") == "\x1b[1;32mLONG\x1b[0m"


def test_paint_without_bold_uses_the_plain_intensity():
    assert ansi.paint("x", "red", bold=False) == "\x1b[0;31mx\x1b[0m"


def test_palette_is_the_eight_discord_actually_renders():
    assert set(ansi.FG.values()) <= set(range(30, 38))


def test_block_fences_with_the_ansi_language_tag():
    out = ansi.block(["one", "two"])
    assert out.startswith("```ansi\n")
    assert out.endswith("\n```")
    assert "one\ntwo" in out


def test_block_rejects_a_line_over_the_width_cap():
    with pytest.raises(ValueError, match="exceeds"):
        ansi.block(["x" * (ansi.MAX_LINE_WIDTH + 1)])


def test_width_is_measured_on_visible_text_not_escape_bytes():
    line = ansi.paint("x" * 30, "green")
    assert len(line) > ansi.MAX_LINE_WIDTH
    ansi.block([line])


def test_max_line_width_is_32():
    assert ansi.MAX_LINE_WIDTH == 32
