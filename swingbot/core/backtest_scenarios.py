"""Historical replay of the confluence scan (spec §4): rebuild the level
map as of each bar, run levels.build_scenarios with that bar's close, and
feed the qualifying scenarios through the SAME plan constructor and exit
simulator the live scan uses. No lookahead: every computation sees
df.iloc[:i+1] only."""
from __future__ import annotations

from swingbot.core import levels
from swingbot.core.strategy_types import HORIZONS

# Levels move slowly; recomputing the full multi-source level map every bar
# is ~5x the cost for near-identical output. One recompute per 5 bars is the
# fidelity/cost tradeoff -- the same granularity the Task 28 backtest tp2
# lookup uses.
LEVEL_REFRESH_BARS = 5


def levels_asof(ticker: str, df, bar_index: int, horizon_key: str, cache: dict):
    """(supports, resistances) as they looked at bar_index -- computed on
    df.iloc[:bar_index+1] so the map can never see future bars."""
    key = (ticker, horizon_key, bar_index // LEVEL_REFRESH_BARS)
    if key in cache:
        return cache[key]
    window = df.iloc[:bar_index + 1]
    price = float(window["Close"].iloc[-1])
    result = levels.build_level_map(window, HORIZONS[horizon_key], price)
    cache[key] = result
    return result
