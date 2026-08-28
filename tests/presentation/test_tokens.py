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
