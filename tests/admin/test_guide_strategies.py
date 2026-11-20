"""v237 V237-5: the strategies.cards placeholder (chapter 5's live cards)."""
from __future__ import annotations

from pathlib import Path

import pytest

from swingbot.admin.guide import cards, live_market as lm, live_strategies as lst, placeholders as ph
from swingbot.admin.guide.chapters import GuideFormatError
from swingbot.core.backtesting.registry import Badge
from swingbot.core.market import strategy_types

_ROWS = {
    "MACD": Badge("VALIDATED", 112, 50.0, 0.219, window="2024-01-01..2025-12-31",
                  run_date="2026-08-17"),
    "Fibonacci": Badge("WEAK", 246, 35.4, 0.232, window="2020-01-01..2023-12-31",
                       run_date="2026-09-10"),
    "RSI": Badge("WEAK", 38, 23.7, -0.12, window="2020-01-01..2023-12-31", run_date="2026-09-10"),
}


def _fake_card(key: str) -> cards.StrategyCard:
    return cards.StrategyCard(path=Path(f"{lm.strategy_file_slug(key)}.md"), strategy=key,
                              reviewed_for="2.19.2", sources=("swingbot/core/market/entry_filters.py",),
                              body=f"**Idea.** Card for {key}.")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(lst, "_load_cards",
                        lambda: [_fake_card(k) for k in lm.registered_strategy_keys()])
    monkeypatch.setattr(lst, "_badge", lambda key: _ROWS.get(key, Badge("WEAK", 0, 0.0, 0.0)))


def _render() -> str:
    return ph.resolve("{{strategies.cards}}")


def _block(key: str) -> str:
    text = _render()
    start = text.index(f"### {key}\n")
    end = text.find("\n### ", start + 1)
    return (text[start:] if end < 0 else text[start:end]).rstrip("\n")


def _live() -> tuple[str, ...]:
    return tuple(strategy_types.live_horizons())


def test_strategy_table_has_exactly_one_name():
    assert set(lst.STRATEGY_PLACEHOLDERS) == {"strategies.cards"}
    assert "strategies.cards" in ph.PLACEHOLDERS


def test_one_block_per_registered_key_in_order():
    headings = [line for line in _render().splitlines() if line.startswith("### ")]
    assert headings == [f"### {key}" for key in lm.registered_strategy_keys()]
    assert "{{" not in _render()


def test_a_validated_row_renders_with_its_full_provenance():
    long_cell = lm._side_cell("MACD", "bullish", _live())
    assert _block("MACD").split("\n\n") == [
        "### MACD",
        "**Status:** live",
        f"**Long:** {long_cell} · **Short:** —",
        "**Badge:** VALIDATED — ExpR +0.219R, win rate 50.0%; Source: validation-window "
        "backtest 2024-01-01..2025-12-31; N = 112; as of 2026-08-17; costs not recorded; "
        "before tax",
        "**Idea.** Card for MACD.",
    ]


def test_a_train_window_row_says_so_and_a_negative_expr_keeps_its_sign():
    assert ("**Badge:** WEAK — ExpR +0.232R, win rate 35.4%; Source: TRAIN-window backtest "
            "2020-01-01..2023-12-31; N = 246") in _block("Fibonacci")
    assert "ExpR -0.120R, win rate 23.7%" in _block("RSI")


def test_side_cells_come_from_admits():
    assert "**Long:** 4w · **Short:** —" in _block("VWAP")
    assert "**Long:** every live horizon · **Short:** every live horizon" in _block("EMA Crossover")


def test_a_masked_key_without_a_row_never_prints_weak():
    block = _block("Turtle Soup")
    assert "**Status:** masked — research only" in block
    assert "**Long:** — · **Short:** —" in block
    assert f"**Badge:** {lst.NO_ROW_MASKED}" in block
    assert "WEAK" not in block and "N = 0" not in block


def test_a_live_key_without_a_row_prints_no_registry_row():
    block = _block("VWAP")
    assert f"**Badge:** {lst.NO_ROW}\n\n" in block
    assert "WEAK" not in block and "masked" not in block


def test_every_badge_carries_n_and_a_date():
    for line in (l for l in _render().splitlines() if l.startswith("**Badge:** ")):
        if lst.NO_ROW in line:
            continue
        assert "; N = " in line and "; as of " in line and line.endswith("; before tax"), line


def test_a_row_without_a_run_date_says_unknown_date(monkeypatch):
    monkeypatch.setattr(lst, "_badge", lambda key: Badge("WEAK", 9, 40.0, 0.1,
                                                         window="2024-01-01..2025-12-31"))
    assert "N = 9; as of unknown date;" in lst.badge_line("MACD", masked=False)


def test_a_masked_key_with_a_row_shows_the_row(monkeypatch):
    monkeypatch.setattr(lst, "_badge", lambda key: _ROWS["MACD"])
    assert lst.badge_line("Turtle Soup", masked=True).startswith("VALIDATED — ExpR +0.219R")


@pytest.mark.parametrize("window, kind", [
    ("2020-01-01..2023-12-31", "TRAIN-window"),
    ("2015-01-01..2022-12-31", "TRAIN-window"),
    ("2024-01-01..2025-12-31", "validation-window"),
    ("2020-01-01..2024-06-30", "validation-window"),
    ("", "validation-window"),
])
def test_window_kind(window, kind):
    assert lst.window_kind(window) == kind


def test_a_registered_key_without_a_card_fails(monkeypatch):
    keep = [k for k in lm.registered_strategy_keys() if k != "RSI"]
    monkeypatch.setattr(lst, "_load_cards", lambda: [_fake_card(k) for k in keep])
    with pytest.raises(GuideFormatError, match="strategies/: no card for RSI"):
        _render()


def test_a_card_for_an_unregistered_strategy_fails(monkeypatch):
    stray = cards.StrategyCard(path=Path("moon-phase.md"), strategy="Moon Phase",
                               reviewed_for="2.19.2", sources=("x.py",), body="**Idea.** No.")
    monkeypatch.setattr(lst, "_load_cards",
                        lambda: [_fake_card(k) for k in lm.registered_strategy_keys()] + [stray])
    with pytest.raises(GuideFormatError,
                       match="moon-phase.md: strategy 'Moon Phase' is not a registered strategy"):
        _render()


def test_the_default_badge_reader_asks_for_the_strategy_source(monkeypatch):
    from swingbot.core.backtesting import registry
    monkeypatch.undo()   # drops _offline's patches: lst._badge is the module's own function again
    calls = []
    monkeypatch.setattr(registry, "get_badge",
                        lambda source, strategy, horizon_key=None: calls.append((source, strategy))
                        or Badge("WEAK", 0, 0.0, 0.0))
    assert lst._badge("MACD").n == 0
    assert calls == [("strategy", "MACD")]
