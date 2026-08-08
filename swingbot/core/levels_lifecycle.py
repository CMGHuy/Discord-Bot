"""Level lifecycle -- how much a support/resistance level has actually proven.

Adapted from dsgex.ai's "Sigils and Spectrum": strikes tagged King / Floor /
Ceiling / Gatekeeper, each carrying a lifecycle marker (Fresh, Tested,
Delivered, Decaying). Their version reads dealer option positioning; ours reads
price, because swingbot has no options data. The *classification idea* is what
transfers, and it transfers whole: a level price has touched and respected three
times is not the same object as one drawn from a single pivot last week, and
`levels.build_level_map` currently hands both to the planner as equals.

WHAT THIS IS FOR
----------------
Two plan-quality uses and one trade-selection use:
  * stop anchoring   -- prefer a `tested` floor to a `fresh` one, never anchor
                        to a `delivered` one (the level isn't there any more)
  * target realism   -- count the undelivered ceilings standing between entry
                        and target; that is dsgex's Gatekeeper, and it is the
                        most direct translation in the whole design
  * entry filtering  -- skip setups whose path to TP1 runs through a `king`

NO-LOOKAHEAD
------------
`classify_levels(df, i, ...)` reads bars 0..i only, never past `i`. The frame
is sliced to `i` on entry so a future bar cannot be reached even by accident,
and `test_classification_is_truncation_invariant` asserts the property rather
than trusting the convention.

WIRING NOTE (read before adding a consumer)
-------------------------------------------
There are two plan paths: `backtest._trade_plan_at` (what the backtest sizes
through) and `plan_engine.build_strategy_plan` (what live builds through).
edge-engine-v4's `DATA_DRIVEN_STOPS_ENABLED` scored exactly 0.0000 and burned
its pre-registered validation shot because it reached only the second one. Any
consumer added here must be routed through BOTH or it is unmeasurable by
construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from swingbot.core.indicators import atr
from swingbot.core.strategy_types import HORIZONS

STATES = ("fresh", "tested", "delivered", "decaying")

# A touch counts when the bar's extreme comes within this multiple of ATR of
# the level. ATR-relative rather than a fixed percentage so the same structure
# classifies identically on a $9 ETF and a $900 stock -- the convention
# entry_filters already follows (ATR_FLOOR_PCT, atr_calm).
TOUCH_ATR_MULT = 0.25

# A close this far beyond the level counts as consuming it. Wider than a touch
# so that ordinary noise around a level reads as a test, not a break.
BREAK_ATR_MULT = 1.0

# Window and decay are scaled off the horizon's own sr_lookback so a 2w level
# and a 9m level are not judged on the same memory.
WINDOW_LOOKBACK_MULT = 6
DECAY_LOOKBACK_MULT = 3

_MIN_BARS = 30          # below this there is no lifecycle to speak of


@dataclass(frozen=True)
class LevelState:
    """One level, with what price has actually done to it.

    Named LevelState rather than Level because `levels.Level` (price+sources)
    already exists and means something narrower; these two get passed around
    the same call sites and must stay tellable apart.
    """
    price: float
    role: str                 # "floor" (below spot) | "ceiling" (above spot)
    state: str                # one of STATES
    touches: int
    bars_since_touch: int
    strength: float
    is_king: bool = False
    sources: list = field(default_factory=list)


def _level_price(lv) -> float:
    return float(getattr(lv, "price", lv))


def _level_sources(lv) -> list:
    return list(getattr(lv, "sources", []) or [])


def _touch_and_break_bars(win: pd.DataFrame, price: float, role: str,
                          tol: float, brk: float):
    """Bar positions (within `win`) where the level was touched, and broken.

    A touch requires the bar to reach the level AND close on its own side of
    it -- reaching and closing through is a break, not a test. That
    distinction is the whole difference between `tested` and `delivered`.
    """
    close = win["Close"].to_numpy(dtype=float)
    if role == "floor":
        reached = win["Low"].to_numpy(dtype=float) <= price + tol
        held = close >= price - tol
        broken = close < price - brk
    else:
        reached = win["High"].to_numpy(dtype=float) >= price - tol
        held = close <= price + tol
        broken = close > price + brk

    return np.flatnonzero(reached & held & ~broken), np.flatnonzero(broken)


def classify_levels(df: pd.DataFrame, i: int, raw_levels,
                    *, horizon_key: str) -> list[LevelState]:
    """Classify each level by what bars 0..i show price doing to it.

    `raw_levels` accepts floats or anything with a `.price` (e.g.
    `levels.Level`), so callers can pass `build_level_map`'s output directly.
    Returns [] when there is too little history to judge anything.
    """
    if not len(raw_levels) or i < _MIN_BARS or i >= len(df):
        return []

    # Slice first: nothing downstream can reach a future bar even by mistake.
    hist = df.iloc[:i + 1]
    h = HORIZONS.get(horizon_key) or {}
    lookback = int(h.get("sr_lookback", 20))
    window = min(len(hist), lookback * WINDOW_LOOKBACK_MULT)
    decay_after = lookback * DECAY_LOOKBACK_MULT

    win = hist.iloc[-window:]
    spot = float(hist["Close"].iloc[-1])

    atr_now = float(atr(hist, 14).iloc[-1])
    if not np.isfinite(atr_now) or atr_now <= 0:
        atr_now = max(spot * 0.01, 1e-9)
    tol, brk = atr_now * TOUCH_ATR_MULT, atr_now * BREAK_ATR_MULT

    out: list[LevelState] = []
    for raw in raw_levels:
        price = _level_price(raw)
        if not np.isfinite(price) or price <= 0:
            continue
        role = "floor" if price < spot else "ceiling"
        touch_bars, break_bars = _touch_and_break_bars(win, price, role, tol, brk)

        last_touch = int(touch_bars[-1]) if touch_bars.size else None
        last_break = int(break_bars[-1]) if break_bars.size else None
        bars_since_touch = (len(win) - 1 - last_touch) if last_touch is not None else len(win)

        # The most recent decisive event wins, so a level that broke and was
        # later reclaimed stops being "delivered".
        if last_break is not None and (last_touch is None or last_break > last_touch):
            state = "delivered"
        elif last_touch is None:
            state = "fresh"
        elif bars_since_touch > decay_after:
            state = "decaying"
        else:
            state = "tested"

        # Conviction: how often it held, discounted by how long ago. A
        # delivered level keeps no conviction -- it is not there any more.
        recency = 1.0 / (1.0 + bars_since_touch / max(decay_after, 1))
        strength = 0.0 if state == "delivered" else len(touch_bars) * recency

        out.append(LevelState(
            price=price, role=role, state=state, touches=int(touch_bars.size),
            bars_since_touch=int(bars_since_touch), strength=round(float(strength), 4),
            sources=_level_sources(raw),
        ))

    if out:
        best = max(range(len(out)), key=lambda k: (out[k].strength, -out[k].price))
        if out[best].strength > 0:
            out[best] = LevelState(**{**out[best].__dict__, "is_king": True})

    return out


# --- consumers --------------------------------------------------------------

def gatekeepers_between(levels, *, entry: float, target: float) -> list[LevelState]:
    """Undelivered levels standing between entry and target, nearest first.

    dsgex's Gatekeeper: the level that has to break for the plan to work. Two
    of these in the path is a materially different trade from none, and the
    planner currently cannot tell the difference.
    """
    lo, hi = (entry, target) if target >= entry else (target, entry)
    blockers = [lv for lv in levels
                if lv.state != "delivered" and lo < lv.price < hi]
    return sorted(blockers, key=lambda lv: abs(lv.price - entry))


def preferred_stop_anchor(levels, *, direction: str) -> LevelState | None:
    """The level a stop should sit beyond, or None if none has earned it.

    Prefers proven structure: tested over decaying over fresh, then by
    conviction. `delivered` levels are never returned -- anchoring a stop to a
    level price has already closed through is how a stop ends up inside the
    noise it was meant to sit outside.
    """
    want = "floor" if direction == "bullish" else "ceiling"
    rank = {"tested": 3, "decaying": 2, "fresh": 1}

    usable = [lv for lv in levels if lv.role == want and lv.state != "delivered"]
    if not usable:
        return None
    return max(usable, key=lambda lv: (rank.get(lv.state, 0), lv.strength, lv.touches))
