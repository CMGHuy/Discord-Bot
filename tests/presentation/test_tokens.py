import discord

from swingbot.core.presentation import tokens as t


def test_accent_ramp_is_monotonic_worse_to_better():
    """The ordinal ramp must not contain a categorical information hue."""
    assert t.accent_for_level(1).value == 0xFF5470
    assert t.accent_for_level(2).value == 0xFFB43D
    assert t.accent_for_level(3).value == 0x9BA3BD
    assert t.accent_for_level(4).value == 0x9ACD32
    assert t.accent_for_level(5).value == 0x17C98E


def test_unknown_level_falls_back_to_the_bottom_of_the_ramp():
    assert t.accent_for_level(None).value == 0xFF5470
    assert t.accent_for_level(0).value == 0xFF5470
    assert t.accent_for_level(9).value == 0xFF5470


def test_outcome_accents_are_the_same_three_colours_as_the_ramp_ends():
    assert t.accent_for_outcome("win").value == 0x17C98E
    assert t.accent_for_outcome("loss").value == 0xFF5470
    assert t.accent_for_outcome("scratch").value == 0x9BA3BD


def test_unknown_outcome_is_grey_not_a_crash():
    assert t.accent_for_outcome("").value == 0x9BA3BD
    assert t.accent_for_outcome("garbage").value == 0x9BA3BD


def test_blocked_accent_is_the_neutral_grey():
    assert t.ACCENT_BLOCKED == 0x9BA3BD


def test_direction_glyph_is_shape_never_colour():
    assert t.direction_glyph("bullish") == "▲"
    assert t.direction_glyph("bearish") == "▼"


def test_direction_glyph_of_something_unknown_is_an_em_dash():
    assert t.direction_glyph("") == "—"
    assert t.direction_glyph("sideways") == "—"


def test_confidence_label_is_level_and_score():
    assert t.confidence_label(5, 91) == "Lv5 · 91"
    assert t.confidence_label(1, 0) == "Lv1 · 0"


def test_confidence_label_without_a_score_shows_the_level_alone():
    assert t.confidence_label(5, None) == "Lv5"


def test_confidence_label_without_a_level_is_an_em_dash():
    assert t.confidence_label(None, 91) == "—"


def test_follow_meter_is_a_five_block_bar_plus_the_number():
    assert t.follow_meter(82.0) == "▰▰▰▰▱ 82"
    assert t.follow_meter(0.0) == "▱▱▱▱▱ 0"
    assert t.follow_meter(100.0) == "▰▰▰▰▰ 100"


def test_follow_meter_clamps_out_of_range_scores():
    assert t.follow_meter(-30.0) == "▱▱▱▱▱ 0"
    assert t.follow_meter(400.0) == "▰▰▰▰▰ 100"


def test_fmt_price_keeps_four_decimals_below_one():
    assert t.fmt_price(1234.5) == "1234.50"
    assert t.fmt_price(0.4321) == "0.4321"
    assert t.fmt_price(12.5, "€") == "€12.50"


def test_fmt_price_of_none_is_an_em_dash_not_zero():
    assert t.fmt_price(None) == "—"


def test_fmt_pct_always_carries_its_sign():
    assert t.fmt_pct(12.0) == "+12.0%"
    assert t.fmt_pct(-6.0) == "−6.0%"
    assert t.fmt_pct(0.0) == "0.0%"
    assert t.fmt_pct(None) == "—"


def test_fmt_pct_uses_a_real_minus_sign_not_a_hyphen():
    assert "−" in t.fmt_pct(-6.0)
    assert "-" not in t.fmt_pct(-6.0)


def test_fmt_r_names_its_unit():
    assert t.fmt_r(2.4) == "2.4R"
    assert t.fmt_r(-1.0) == "−1.0R"
    assert t.fmt_r(None) == "—"
