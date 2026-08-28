"""Target geometry and candidate selection for Plan Engine v2."""
from __future__ import annotations

import numpy as np

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.levels import MAX_TARGET2_LEG_MULTIPLE
from .params import SR_VOLUME_STRENGTH_CEILING
def select_structural_target(entry: float, stop_loss: float, is_bull: bool,
                             candidate_levels, min_rr: float,
                             max_rr: float) -> float | None:
    """THE target price for every plan this engine builds.

    Nearest real level beyond `entry` that pays at least `min_rr` times the
    plan's own risk, capped at `max_rr`. Returns None when no candidate
    clears the floor -- which means "there is no trade here", not "fall back
    to something smaller". There is deliberately no fallback: pricing a
    target off a fixed fraction of risk is exactly the arithmetic that made
    every posted plan risk 3x what it stood to make (plan v31).

    NEAREST-qualifying, not farthest: the floor already guarantees the
    payoff, and a closer target is reached more often. Beyond `max_rr` the
    result is a SYNTHETIC price at exactly `entry +/- risk * max_rr` -- not
    the level, not None. That level is still a real level, and select_tp2
    will pick it up as tp2 (the cap declines it as tp1, it does not delete
    it).

    `candidate_levels` is an iterable of plain prices; each caller supplies
    ITS OWN source (unified level map for the confluence path, the
    strategy's own native levels for the strategy builders -- see the
    sizing-builders comment block above). Nothing is looked up in here, for
    the same reason `_atr_plan` takes an injected `stop_mult`: this function
    is shared by the live path and the backtest, and a hidden lookup would
    price 2020 backtest bars off today's live data.
    """
    risk = abs(entry - stop_loss)
    if risk <= 0 or min_rr <= 0:
        return None
    if max_rr < min_rr:
        raise ValueError(f"max_rr {max_rr} < min_rr {min_rr}")

    # Relative epsilon: a level sitting EXACTLY at the floor must qualify,
    # and float arithmetic on a $600 stock does not land exactly.
    eps = 1e-9 * max(1.0, abs(entry))
    floor_dist, cap_dist = risk * min_rr, risk * max_rr

    beyond = [float(p) for p in candidate_levels
              if p and (p > entry if is_bull else p < entry)]
    qualifying = [p for p in beyond if abs(p - entry) >= floor_dist - eps]
    if not qualifying:
        return None

    nearest = min(qualifying, key=lambda p: abs(p - entry))
    if abs(nearest - entry) > cap_dist + eps:
        return entry + cap_dist if is_bull else entry - cap_dist
    return nearest


# ---------------------------------------------------------------------------
# Sizing builders — extracted verbatim from backtest._trade_plan_at so the
# backtest, live signals, and the plan manager all price identically.
# ---------------------------------------------------------------------------

# v31 Task 1 — candidate-level source for each of the six call sites that
# will feed select_structural_target() (Task 2). Confirmed against source,
# no production code changed here.
#
# 1. build_confluence_plan (:654+) — candidates come from the unified level
#    map. swingbot.core.market.levels.build_level_map already returns
#    (supports, resistances) as ordered Level lists, nearest-first (supports
#    sorted by -price, resistances by price — market/levels.py:505). The
#    ordered candidate list already exists: [lv.price for lv in resistances]
#    (bullish) or [lv.price for lv in supports] (bearish). No change needed
#    to build_level_map/build_scenarios, only threading (Task 4). Both
#    holders of that map confirmed: engine.ScanItem.level_map
#    (scanning/engine.py:173, consumed at :1248) and
#    backtesting/backtest_scenarios.py:82-88, which re-splits an as-of map
#    against the current bar's price.
# 2. _fibonacci_plan (:314) — receives only swing_high/swing_low. Its native
#    ladder is market.indicators.fibonacci_levels(df, h["fib_lookback"]):
#    retracements at 0.236/0.382/0.5/0.618/0.786 measured down from the
#    swing high (market/indicators.py:39-59). Confirmed: no extension ratios
#    exist in that function today. Decision: ADD 1.272/1.618 extensions of
#    the same swing as targets beyond swing_high — otherwise a bullish fib
#    plan entering near the swing high has at most one candidate and returns
#    None constantly.
# 3. _elliott_plan (:366) — receives only wave2.
#    market.indicators.elliott_wave3_entries (function at :215, docstring at
#    :235-239) already hands every caller
#    {wave0, wave1, wave2, wave0_idx, wave1_idx, wave2_idx} and its docstring
#    explicitly says callers may reuse these without recomputing pivots.
#    Native wave-3 targets are the classic projections off wave 2:
#    wave2 ± k * |wave1 - wave0| for k in (1.0, 1.618, 2.618), plus wave1
#    itself. Sign convention for the bearish branch (kind0 == "high",
#    p2 < p0) confirmed at the call site.
# 4. _sr_plan (:342) — takes no df at all; its target today is a pure
#    percentage band interpolated by volume strength
#    (h["sr_target_min_pct"]..h["sr_target_max_pct"]). It has no native
#    levels. Its natural candidates are the structure the strategy actually
#    trades: df["High"].rolling(h["sr_lookback"]).max().shift(1) and the
#    matching rolling low, plus the existing percentage-band prices as a
#    floor so the candidate list is never empty.
# 5. _atr_plan (:170) — the fallback for 8 of 11 strategies (EMA Crossover,
#    VWAP, RSI, MACD, MA Ribbon, Break & Retest, RSI Divergence, Volume
#    Profile). It has no price structure of any kind; its only native scale
#    is volatility. THE ONE OPEN DECISION IN THIS PLAN, now decided: an ATR
#    ladder, entry ± k * atr_val for k in (1, 2, 3, 4, 5, 6, 8, 10). Rejected
#    alternatives: borrowing the unified map (rejected by the spec's
#    per-strategy decision), returning None for all eight strategies
#    (rejected — empties !ticker, empties the backtest for those strategies,
#    and therefore empties the badge registry that stamp_badge reads).
#    Reason for the ladder: with atr_stop_multiple = 2.0 (confirmed above,
#    HORIZONS[*]["atr_stop_multiple"], strategy_types.py) the risk is 2 ATR,
#    so min_rr = 1.5 puts the floor at 3 ATR and max_rr = 2.5 at 5 ATR — the
#    ladder brackets the whole band, the nearest-qualifying rule lands on
#    3 ATR, and the answer is deterministic and honest ("this strategy's
#    structure is volatility").
# 6. apply_level_lifecycle (:233) — already builds or receives a classified
#    level list via _lifecycle_levels, which returns
#    market.levels_lifecycle.LevelState objects carrying .price (confirmed
#    at levels_lifecycle.py:68). Confirmed usable as selector candidates
#    directly (Task 13 uses .price); preferred_stop_anchor (:197) signature
#    confirmed in the same module. (The module also had a gatekeepers-between
#    helper at the time, used only by the targets_on branch Task 13 deleted;
#    Task 14 removed it.)
#
# NOTE on plan-doc drift: the plan text says these three modules live under
# swingbot.core.planning — they actually live under swingbot.core.market
# (market/levels.py, market/indicators.py, market/levels_lifecycle.py).
# Substance of every claim above is otherwise correct; only the package
# name was stale.

def _safe_atr_value(entry: float, atr_val: float) -> float:
    if not np.isfinite(atr_val) or atr_val <= 0:
        return entry * 0.02
    return float(atr_val)


ATR_TARGET_LADDER = (1, 2, 3, 4, 5, 6, 8, 10)


def atr_target_candidates(entry, atr_val, direction) -> list[float]:
    """Volatility IS the structure for the eight strategies that size
    through _atr_plan (EMA Crossover, VWAP, RSI, MACD, MA Ribbon,
    Break & Retest, RSI Divergence, Volume Profile). None of them produces
    a price level of its own, and borrowing the unified level map here was
    rejected (plan v31) -- a MACD plan targeting a Fibonacci level is not a
    MACD plan. So the candidates are this ticker's own ATR bands. At the
    horizon default (atr_stop_multiple 2.0) risk is 2 ATR, which puts the
    1.5R floor at 3 ATR and the 2.5R cap at 5 ATR: the ladder brackets the
    whole band and the nearest-qualifying rule lands on 3 ATR."""
    is_bull = direction == "bullish"
    return [entry + k * atr_val if is_bull else entry - k * atr_val
            for k in ATR_TARGET_LADDER]


def _tp2_from_r(entry: float, stop: float, tp1: float, direction: str,
                tp2_r: float) -> float | None:
    """Convert an MFE R-multiple into a TP2 PRICE, under the same two
    invariants select_tp2 enforces on a level-derived TP2: strictly beyond
    TP1 in the trade direction, and a TP1->TP2 leg no longer than
    MAX_TARGET2_LEG_MULTIPLE times the entry->TP1 leg. Returns None when
    either fails, so the caller keeps whatever TP2 it already had rather
    than replacing it with a nonsense number."""
    risk = abs(entry - stop)
    leg1 = abs(tp1 - entry)
    if risk <= 0 or leg1 <= 0:
        return None
    is_bull = direction == "bullish"
    candidate = entry + risk * tp2_r if is_bull else entry - risk * tp2_r
    if not (candidate > tp1 if is_bull else candidate < tp1):
        return None
    if abs(candidate - tp1) > leg1 * MAX_TARGET2_LEG_MULTIPLE:
        return None
    return float(candidate)


def fib_target_candidates(df, index, h, entry) -> list[float]:
    """The Fibonacci strategy's OWN levels on the target side: the swing
    high/low that anchors the retracement, the 0.236/0.382/0.5/0.618/0.786
    retracements themselves, and the 1.272/1.618 extensions of the same
    swing. NOT the unified multi-method level map -- a Fibonacci plan
    targets Fibonacci structure (plan v31).

    `df` is sliced to `index` BEFORE computing the swing -- the same trap
    `_lifecycle_levels` documents above: `df` here runs to the end of
    history in the backtest, and `indicators.fibonacci_levels` takes the
    trailing `lookback` bars of whatever it is given, so an unsliced call
    would draw the swing out of bars the trade cannot have seen.

    No `direction` param: candidates are returned unfiltered on both sides
    of `entry` (extensions in both directions), and select_structural_target
    is what picks the trade-direction side.
    """
    from swingbot.core.market import indicators
    hist = df.iloc[:index + 1]
    fib = indicators.fibonacci_levels(hist, h["fib_lookback"])
    swing_high, swing_low = fib["swing_high"], fib["swing_low"]
    diff = swing_high - swing_low
    candidates = [swing_high, swing_low] + list(fib["levels"].values())
    for ratio in (1.272, 1.618):
        candidates.append(swing_high + ratio * diff)
        candidates.append(swing_low - ratio * diff)
    return candidates


def sr_target_candidates(df, index, h, entry, volume_ratio) -> list[float]:
    """The S/R strategy's OWN target-side candidates: the rolling
    structural high/low over `h["sr_lookback"]` (`.shift(1)`, matching
    `collect_candidate_levels`' no-lookahead convention -- levels.py:227-228),
    plus the existing volume-strength percentage band. The band alone keeps
    this list non-empty on a ticker whose rolling structure sits the wrong
    side of entry: the same volume_ratio-interpolated point the old
    arithmetic used (`sr_target_min_pct`..`sr_target_max_pct`, by strength),
    plus both fixed band ENDS explicitly, in both directions -- v31 replaces
    "pick one point" with "offer every real S/R candidate and let
    select_structural_target choose the nearest-qualifying one."
    """
    from swingbot.core.market.strategy import SR_VOLUME_MULTIPLE

    high = df["High"].rolling(h["sr_lookback"]).max().shift(1).iloc[index]
    low = df["Low"].rolling(h["sr_lookback"]).min().shift(1).iloc[index]
    candidates = []
    if np.isfinite(high):
        candidates.append(float(high))
    if np.isfinite(low):
        candidates.append(float(low))

    if not np.isfinite(volume_ratio):
        volume_ratio = SR_VOLUME_MULTIPLE
    strength = (volume_ratio - SR_VOLUME_MULTIPLE) / (SR_VOLUME_STRENGTH_CEILING - SR_VOLUME_MULTIPLE)
    strength = max(0.0, min(1.0, strength))
    min_pct, max_pct = h["sr_target_min_pct"], h["sr_target_max_pct"]
    target_pct = min_pct + (max_pct - min_pct) * strength
    for pct in (target_pct, min_pct, max_pct):
        candidates.append(entry * (1 + pct / 100))
        candidates.append(entry * (1 - pct / 100))
    return candidates


def elliott_target_candidates(entry_level: dict, direction) -> list[float]:
    """The Elliott strategy's OWN wave-3 projections: wave1 itself, and the
    classic wave2 +/- k * |wave1 - wave0| projections for k in
    (1.0, 1.618, 2.618), signed by direction -- wave 3 continues the same
    way wave 1 did, so unlike a fib swing there is no mirror side to
    include. Reuses the pivots elliott_wave3_entries already published
    (indicators.py) -- callers must not recompute them."""
    wave0, wave1, wave2 = entry_level["wave0"], entry_level["wave1"], entry_level["wave2"]
    is_bull = direction == "bullish"
    amplitude = abs(wave1 - wave0)
    candidates = [wave1]
    for k in (1.0, 1.618, 2.618):
        candidates.append(wave2 + k * amplitude if is_bull else wave2 - k * amplitude)
    return candidates


# ---------------------------------------------------------------------------
# TP2 selection — the next structural level beyond TP1 (levels.py already
# does the clustering; this just picks a target and caps the leg).
# ---------------------------------------------------------------------------

def select_tp2(levels_above: list, levels_below: list, direction: str,
               entry: float, tp1: float) -> float | None:
    """
    First clustered level strictly beyond TP1 in the trade direction — the
    "if it keeps going" stretch target. `levels_above`/`levels_below` are
    plain price floats (already-clustered `Level.price` values, e.g. from
    `levels.build_level_map` — callers extract `.price` before calling this;
    reuse that clustering, don't reimplement it here).

    None if no level sits beyond TP1 on the trade-direction side, or if the
    TP1 -> candidate leg exceeds `MAX_TARGET2_LEG_MULTIPLE` times the
    entry -> TP1 leg — the same "don't show a wildly disproportionate
    runner" cap levels.py's own target-2 selection uses (see its docstring).
    """
    leg1 = abs(tp1 - entry)
    if leg1 <= 0:
        return None

    is_bull = direction == "bullish"
    candidates = levels_above if is_bull else levels_below
    beyond = [p for p in candidates if (p > tp1 if is_bull else p < tp1)]
    if not beyond:
        return None

    candidate = min(beyond) if is_bull else max(beyond)
    leg2 = abs(candidate - tp1)
    if leg2 > leg1 * MAX_TARGET2_LEG_MULTIPLE:
        return None
    return candidate


