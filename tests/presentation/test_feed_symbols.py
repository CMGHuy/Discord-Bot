"""v170: the execution feed's money format and its one table of symbols."""
import pytest

from swingbot.core.presentation import tokens
from swingbot.core.scanning import plan_table

KEYS = ("entry", "stop", "tp1", "runner", "tp2", "trail", "breakeven", "expiry",
        "invalid", "if_fills", "pnl", "win", "loss", "flat", "at_or_above", "at_or_below")


@pytest.mark.parametrize("amount,expected", [
    (250.0, "+$250.00"),
    (-248.4, "-$248.40"),          # ASCII hyphen-minus, never U+2212 (A9)
    (0.0, "+$0.00"),               # zero and above carry '+'
    (12345.678, "+$12,345.68"),
    (-0.004, "-$0.00"),
])
def test_fmt_money_is_signed_with_an_ascii_minus(amount, expected):
    assert tokens.fmt_money(amount, "$") == expected


def test_signed_money_is_the_same_object_as_fmt_money():
    # instructions.py may not import scanning, so the helper moved to tokens;
    # every old importer keeps the name and the exact behaviour.
    assert plan_table.signed_money is tokens.fmt_money


def test_fmt_r_keeps_its_unicode_minus():
    assert tokens.fmt_r(-1.0) == "−1.0R"


def test_feed_symbols_has_every_key_in_order():
    assert tuple(tokens.FEED_SYMBOLS) == KEYS
    assert tokens.FEED_SYMBOLS == {
        "entry": "▶", "stop": "\U0001f6d1", "tp1": "\U0001f4b0",
        "runner": "\U0001f3c3", "tp2": "\U0001f3af", "trail": "〜",
        "breakeven": "⚖", "expiry": "⏳", "invalid": "⛔",
        "if_fills": "\U0001f512", "pnl": "\U0001f9fe", "win": "✅",
        "loss": "❌", "flat": "➖", "at_or_above": "≥",
        "at_or_below": "≤",
    }


def test_every_glyph_has_one_meaning():
    glyphs = list(tokens.FEED_SYMBOLS.values())
    assert len(glyphs) == len(set(glyphs))


def test_warning_glyph_stays_reserved():
    # the heat/cluster/kill-switch warnings own the warning sign (panel finding)
    assert "⚠" not in tokens.FEED_SYMBOLS.values()


def test_every_symbol_has_a_legend_word():
    assert tuple(tokens.FEED_SYMBOL_WORDS) == KEYS
    assert all(word.strip() for word in tokens.FEED_SYMBOL_WORDS.values())


def test_cost_basis_strings():
    assert tokens.COST_BASIS == "(paper, gross)"
    assert tokens.COST_BASIS_SENTENCE == (
        "Feed dollars: paper account, before fees, slippage and tax.")


def test_legend_is_generated_from_the_table():
    legend = tokens.feed_legend()
    assert legend.startswith("Feed symbols: ")
    assert legend.endswith(". " + tokens.COST_BASIS_SENTENCE)
    for key, glyph in tokens.FEED_SYMBOLS.items():
        assert f"{glyph} {tokens.FEED_SYMBOL_WORDS[key]}" in legend
    assert legend.count(" · ") == len(KEYS) - 1
