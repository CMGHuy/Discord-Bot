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


def _plan(**kw):
    base = dict(direction="bullish", entry=197.15, target=220.81, stop=185.32,
                target_pct=12.0, stop_pct=-6.0, r=2.4)
    base.update(kw)
    return ansi.plan_lines(**base)


def test_plan_lines_are_two_lines():
    assert len(_plan()) == 2


def test_first_line_reads_entry_arrow_target_slash_stop():
    assert ansi._ESCAPE_RE.sub("", _plan()[0]) == "▲ 197.15 → 220.81 / 185.32"


def test_a_short_plan_leads_with_the_down_triangle():
    assert ansi._ESCAPE_RE.sub("", _plan(direction="bearish")[0]).startswith("▼ ")


def test_target_is_green_and_stop_is_red():
    line = _plan()[0]
    assert ansi.paint("220.81", "green") in line
    assert ansi.paint("185.32", "red") in line


def test_second_line_carries_the_magnitudes():
    plain = ansi._ESCAPE_RE.sub("", _plan()[1])
    assert "+12.0%" in plain and "−6.0%" in plain and "2.4R" in plain


def test_a_missing_second_target_still_produces_two_lines():
    lines = _plan(entry=None, r=None)
    assert len(lines) == 2
    assert "—" in ansi._ESCAPE_RE.sub("", lines[0])


def test_no_builder_exceeds_width():
    lines = ansi.plan_lines(direction="bearish", entry=99999.99, target=88888.88,
                            stop=11111.11, target_pct=-123.4, stop_pct=45.6, r=-12.3)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
    ansi.block(lines)
