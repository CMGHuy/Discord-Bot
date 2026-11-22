"""v237: the strategies.cards placeholder -- one block per registered strategy.

Each block joins three sources: the card file (idea, entry rule, where it
fires), admits() (the directions and horizons the live scan allows, so a
masked strategy says so) and the registry row (status, ExpR, win rate, with
the row's own window, N and run date, "costs not recorded" and "before tax").
A strategy with no row says "no registry row" -- never the WEAK / N = 0
default get_badge falls back to.
"""
from __future__ import annotations

from typing import Callable

from swingbot.admin.guide import cards, live_market
from swingbot.admin.guide.chapters import GuideFormatError
from swingbot.core.backtesting import registry
from swingbot.core.market import strategy_types

NO_ROW = "no registry row"
NO_ROW_MASKED = "no registry row — masked, research only"
_MASKED = "masked — research only"
#: Start of the validation window (docs/claude/backtest-methodology.md): a row
#: whose window ends before it was measured on TRAIN data.
_VALIDATION_FROM = "2024-01-01"

_load_cards: Callable[[], list[cards.StrategyCard]] = cards.load_cards


def _badge(key: str) -> registry.Badge:
    """The pooled strategy-source registry row (patched in unit tests)."""
    return registry.get_badge("strategy", key)


def window_kind(window: str) -> str:
    end = window.rpartition("..")[2]
    return "TRAIN-window" if end and end < _VALIDATION_FROM else "validation-window"


def badge_line(key: str, masked: bool) -> str:
    from swingbot.admin.guide.placeholders import provenance_label   # placeholders imports us
    badge = _badge(key)
    if badge.n == 0 and not badge.run_date:
        return NO_ROW_MASKED if masked else NO_ROW
    label = provenance_label(source=f"{window_kind(badge.window)} backtest {badge.window}",
                             n=badge.n, run_date=badge.run_date or "unknown date",
                             costs_included=None)
    return (f"{badge.status} — ExpR {badge.expectancy_r:+.3f}R, "
            f"win rate {badge.win_rate:.1f}%; {label}")


def _cards_by_key(keys: tuple[str, ...]) -> dict[str, cards.StrategyCard]:
    found: dict[str, cards.StrategyCard] = {}
    for card in _load_cards():
        if card.strategy not in keys:
            raise GuideFormatError(f"{card.path.name}: strategy {card.strategy!r} "
                                   "is not a registered strategy")
        found[card.strategy] = card
    missing = [key for key in keys if key not in found]
    if missing:
        raise GuideFormatError(f"strategies/: no card for {', '.join(missing)}")
    return found


def _card_block(key: str, card: cards.StrategyCard, live: tuple[str, ...]) -> str:
    long_cell = live_market._side_cell(key, "bullish", live)
    short_cell = live_market._side_cell(key, "bearish", live)
    masked = long_cell == short_cell == live_market._NONE
    return "\n\n".join([
        f"### {key}",
        f"**Status:** {_MASKED if masked else 'live'}",
        f"**Long:** {long_cell} · **Short:** {short_cell}",
        f"**Badge:** {badge_line(key, masked)}",
        card.body,
    ])


def _strategy_cards() -> str:
    keys = live_market.registered_strategy_keys()
    by_key = _cards_by_key(keys)
    live = tuple(strategy_types.live_horizons())
    return "\n\n".join(_card_block(key, by_key[key], live) for key in keys)


STRATEGY_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "strategies.cards": _strategy_cards,
}
