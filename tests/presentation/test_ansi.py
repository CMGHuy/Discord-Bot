import pytest

from swingbot.core.presentation import ansi
from swingbot.core.presentation import tokens


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


def _plain(line):
    return ansi._ESCAPE_RE.sub("", line)


def test_plan_lines_are_side_levels_magnitudes():
    assert len(_plan()) == 3


def test_first_line_names_the_side_in_its_colour():
    assert _plan()[0] == ansi.paint("▲ LONG", "green")
    assert _plan(direction="bearish")[0] == ansi.paint("▼ SHORT", "red")


def test_unknown_direction_is_an_unpainted_dash():
    assert _plan(direction="sideways")[0] == "—"


def test_second_line_reads_entry_arrow_target_slash_stop():
    assert _plain(_plan()[1]) == "197.15 → 220.81 / 185.32"


def test_entry_is_cyan_target_green_stop_red():
    line = _plan()[1]
    assert ansi.paint("197.15", "cyan") in line
    assert ansi.paint("220.81", "green") in line
    assert ansi.paint("185.32", "red") in line


def test_third_line_carries_the_magnitudes_with_r_in_yellow():
    line = _plan()[2]
    assert "+12.0%" in _plain(line) and "−6.0%" in _plain(line)
    assert ansi.paint("2.4R", "yellow") in line


def test_a_missing_entry_still_produces_three_readable_lines():
    lines = _plan(entry=None, r=None)
    assert len(lines) == 3
    assert "—" in _plain(lines[1])


def test_no_plan_line_exceeds_width():
    lines = ansi.plan_lines(direction="bearish", entry=99999.99, target=88888.88,
                            stop=11111.11, target_pct=-123.4, stop_pct=45.6, r=-12.3)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
    ansi.block(lines)


def test_r_multiple_is_reward_over_risk():
    assert ansi.r_multiple(100.0, 95.0, 110.0) == 2.0
    assert ansi.r_multiple(100.0, 100.0, 110.0) is None
    assert ansi.r_multiple(None, 95.0, 110.0) is None


def test_levels_lines_paint_every_level():
    lines = ansi.levels_lines(direction="bullish", entry=100.0, stop=95.0, tp1=110.0, tp2=120.0)
    assert [_plain(line) for line in lines] == [
        "▲ LONG", "entry 100.00", "stop  95.00", "TP1   110.00 2.0R", "TP2   120.00 4.0R"]
    assert ansi.paint("100.00", "cyan") in lines[1]
    assert ansi.paint("95.00", "red") in lines[2]
    assert ansi.paint("110.00", "green") in lines[3]
    assert ansi.paint("2.0R", "yellow") in lines[3]


def test_levels_lines_omit_a_missing_tp2_and_an_undefined_r():
    lines = ansi.levels_lines(direction="bearish", entry=100.0, stop=100.0, tp1=90.0)
    assert len(lines) == 4
    assert _plain(lines[3]) == "TP1   90.00"


def test_levels_lines_stay_phone_safe():
    lines = ansi.levels_lines(direction="bearish", entry=99999.99, stop=11111.11,
                              tp1=88888.88, tp2=77777.77)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
    ansi.block(lines)


@pytest.mark.parametrize("r,colour", [(1.8, "green"), (-1.0, "red"), (0.0, "white"), (None, "white")])
def test_result_lines_paint_the_realised_r_by_sign(r, colour):
    lines = ansi.result_lines(direction="bullish", entry=100.0, exit_price=109.0,
                              stop=95.0, pct=9.0, r=r)
    assert len(lines) == 3
    assert ansi.paint(tokens.fmt_r(r), colour) in lines[2]
    assert _plain(lines[1]) == "100.00 → 109.00 / 95.00"


def test_result_lines_stay_phone_safe():
    lines = ansi.result_lines(direction="bearish", entry=99999.99, exit_price=88888.88,
                              stop=11111.11, pct=-123.4, r=-12.3)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
