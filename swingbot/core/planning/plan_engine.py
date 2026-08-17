"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/implemented/2026-07-11-v2-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass, field

import numpy as np

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.levels import MAX_TARGET2_LEG_MULTIPLE
from swingbot.core.backtesting.registry import Badge, get_badge
from swingbot.core.market.strategy_types import (
    BREAKEVEN_TRIGGER_FRACTION,
    HORIZONS,
    STRATEGY_RR_OVERRIDE,
)

log = logging.getLogger("swing-bot.plan_engine")

# Same numbers backtest.py used before the extraction (parity-critical).
STRUCTURE_BUFFER_ATR = 0.25   # cushion beyond swing high/low, in ATR units
SR_VOLUME_STRENGTH_CEILING = 3.0
RR_FLOOR = 0.30               # break-even WR at 0.30 is 76.9% (strategy_types.py:211)
TRAIL_ATR_MULT = 2.5          # chandelier default; finalized by the Task 30 TRAIN grid
TP1_FRACTION = 0.5            # fixed by spec §5
DEFAULT_EXPIRY_BARS = 5

# Per-strategy exit-v2 overrides chosen by the Task 30 TRAIN grid under the
# pre-registered rule "WR>=80 and ExpR>0 and N>=30 and excl<=50%; max ExpR
# wins; else keep defaults" (docs/superpowers/results/2026-07-exit-v2-train-grid.txt).
# Missing key = defaults (trail 2.5, tp2 on). NEVER edit from validation data.
# Support/Resistance's winner (trail=2.5, tp2=levels) equals the defaults;
# EMA Crossover and Elliott Wave had no qualifying config. stop_entry won for
# no breakout-class strategy, so STRATEGY_ENTRY_TYPE stays empty.
# Applies to strategy-source plans only: the confluence pipeline ran its
# one-shot OOS validation (Task 41) with the defaults, so its behavior is
# pinned — build_confluence_plan deliberately does not read this table.
EXIT_V2_PARAMS: dict[str, dict] = {
    "VWAP":           {"trail_atr_mult": 2.5, "tp2": False},  # N=136  WR=83.1 ExpR=+0.216
    "Fibonacci":      {"trail_atr_mult": 3.0, "tp2": False},  # N=279  WR=81.7 ExpR=+0.183
    "RSI":            {"trail_atr_mult": 2.0, "tp2": False},  # N=608  WR=85.2 ExpR=+0.218
    "MACD":           {"trail_atr_mult": 2.0, "tp2": True},   # N=145  WR=83.4 ExpR=+0.090
    "MA Ribbon":      {"trail_atr_mult": 2.5, "tp2": False},  # N=259  WR=81.1 ExpR=+0.186
    "Break & Retest": {"trail_atr_mult": 3.0, "tp2": False},  # N=355  WR=80.3 ExpR=+0.085
    "RSI Divergence": {"trail_atr_mult": 2.0, "tp2": False},  # N=1702 WR=81.0 ExpR=+0.218
    "Volume Profile": {"trail_atr_mult": 3.0, "tp2": False},  # N=73   WR=82.2 ExpR=+0.180
}


def exit_params_for(strategy: str) -> dict:
    p = EXIT_V2_PARAMS.get(strategy, {})
    return {"trail_atr_mult": p.get("trail_atr_mult", TRAIL_ATR_MULT),
            "tp2": p.get("tp2", True)}


class PlanStatus:
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


_LEGAL_TRANSITIONS = {
    PlanStatus.PENDING: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.ACTIVE: {PlanStatus.PARTIAL, PlanStatus.CLOSED},
    PlanStatus.PARTIAL: {PlanStatus.CLOSED},
}


@dataclass
class TradePlanV2:
    plan_id: str
    ticker: str
    created_at: str            # ISO date of the bar/scan that created the plan
    source: str                # "strategy" | "confluence"
    strategy: str              # exact ALL_STRATEGIES string of the generating strategy
    horizon_key: str
    direction: str             # "bullish" | "bearish"
    entry_type: str            # "stop_entry" | "market"
    trigger_price: float
    entry_price: float | None
    expiry_bars: int
    stop_loss: float
    tp1: float
    tp1_fraction: float
    tp2: float | None
    breakeven_trigger_fraction: float
    trail_atr_mult: float
    quality_score: int
    quality_breakdown: list
    tier: str                  # "A" | "B" | "C"
    badge: str                 # "VALIDATED" | "WEAK"
    badge_stats: dict
    status: str
    status_history: list = field(default_factory=list)
    working_stop: float | None = None   # None = "use stop_loss"; live BE/trail floor
    legs_realized: list = field(default_factory=list)  # [{fraction, exit_price, r, reason}]
    runner_high_close: float | None = None  # extreme price since TP1 (bearish: extreme LOW)
    # E31: the MAE-informed factor this plan's ATR stop was actually scaled
    # by, or None when it wasn't (flag off / too few journaled winners /
    # a structure-derived stop). Its own field rather than a
    # quality_breakdown row because it is NOT a scored component -- that
    # list is strictly (name, points) tuples, rendered as `{pts:+d}` by
    # embeds.py and views.py and flattened by plan_to_dict, so a note
    # smuggled in there would crash both renderers and corrupt the
    # persisted JSON. Kept on the plan so E33's folds and E40's shadow
    # gate can audit which plans were sized with it, after the fact.
    stop_mult_applied: float | None = None
    # E32, same rationale: the MFE-derived R-multiple this plan's TP2 was
    # priced at (None when the level-based TP2 stood), and the day by
    # which most of this strategy's winners had already reached +0.5R.
    # time_stop_days is ADVISORY -- nothing here closes a position on it;
    # E48's recycler is the intended consumer.
    tp2_r_applied: float | None = None
    time_stop_days: int | None = None
    # E38: the one pyramid SUGGESTION emitted for this plan, or None. Its
    # presence is what makes the add fire at most once. The bot never sizes
    # real money -- this records what was suggested, not a position.
    pyramid_add: dict | None = None


def effective_stop(plan: TradePlanV2) -> float:
    return plan.working_stop if plan.working_stop is not None else plan.stop_loss


_PLAN_FIELDS = None   # cached field list


def plan_to_dict(plan: TradePlanV2) -> dict:
    d = dataclasses.asdict(plan)
    # tuples (quality_breakdown rows) -> lists so json round-trips cleanly
    d["quality_breakdown"] = [list(row) for row in d.get("quality_breakdown", [])]
    return d


def plan_from_dict(d: dict) -> TradePlanV2:
    global _PLAN_FIELDS
    if _PLAN_FIELDS is None:
        _PLAN_FIELDS = {f.name for f in dataclasses.fields(TradePlanV2)}
    known = {k: v for k, v in d.items() if k in _PLAN_FIELDS}
    return TradePlanV2(**known)   # missing fields use dataclass defaults


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
#    directly (Task 13 uses .price); preferred_stop_anchor (:197) and
#    gatekeepers_between (:184) signatures confirmed in the same module.
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


def _rr_for(strategy: str, horizon_key: str) -> float:
    rr_override = STRATEGY_RR_OVERRIDE.get(strategy)
    rr = rr_override if rr_override is not None else HORIZONS[horizon_key]["reward_risk_ratio"]
    return max(rr, RR_FLOOR)


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


def _atr_plan(entry, atr_val, direction, horizon_key, strategy, stop_mult=None,
             candidate_levels=None):
    """Default volatility sizing: ATR-multiple stop; target is the nearest
    ATR-ladder candidate (atr_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31). Returns
    None when nothing clears the floor.

    `stop_mult` (edge E31) is an INJECTED MAE-informed adjustment factor,
    never looked up here. That is deliberate: this function is the shared
    sizing source for both live plans (build_strategy_plan) and the
    backtest (backtest._trade_plan_at), so a journal read hidden in here
    would silently price 2020 backtest trades off today's live journal.
    Callers that legitimately have a multiplier pass it in; the E33 fold
    harness will pass its own fold-train-derived value.

    Scaling `risk_distance` (rather than the stop price) keeps the stop's
    ATR-multiple exact -- the same distance feeds both the stop and, via
    select_structural_target's own risk argument, the target floor/cap.
    `strategy` is accepted but unused: the ladder is identical for all
    eight fallback strategies (kept for call-site signature parity, not
    because a per-strategy R:R table survives here -- that table is
    deleted in Task 14).
    """
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    risk_distance = h["atr_stop_multiple"] * atr_val
    if stop_mult is not None:
        risk_distance *= stop_mult
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if risk_distance > max_risk_amount:
        risk_distance = max_risk_amount
    stop_loss = entry - risk_distance if is_bull else entry + risk_distance

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit


# --- level lifecycle (P1) ---------------------------------------------------
#
# Deliberately lives HERE, next to the sizing builders, and not in either
# caller. backtest._trade_plan_at and build_strategy_plan are two separate
# plan paths, and edge-engine-v4's DATA_DRIVEN_STOPS_ENABLED scored exactly
# 0.0000 -- burning its one pre-registered validation shot -- because it
# reached only build_strategy_plan while the backtest sized through
# _trade_plan_at. Anything that touches stop/target must be shared by both or
# it is unmeasurable by construction.

def _lifecycle_levels(df, index, horizon_key, entry, level_map=None):
    """Classified levels at `index`, from the caller's level_map when it has
    one (live already builds it) or built on the spot (the backtest does not).

    The backtest branch slices df to `index` BEFORE building levels: `df`
    there runs to the end of history, so an unsliced build_level_map would
    draw levels out of bars the trade cannot have seen.
    """
    from swingbot.core.market import levels_lifecycle

    if level_map is not None:
        supports, resistances = level_map
        raw = list(supports) + list(resistances)
    else:
        from swingbot.core.market import levels as levels_mod
        hist = df.iloc[:index + 1]
        supports, resistances = levels_mod.build_level_map(
            hist, HORIZONS[horizon_key], entry)
        raw = list(supports) + list(resistances)

    return levels_lifecycle.classify_levels(df, index, raw, horizon_key=horizon_key)


def apply_level_lifecycle(df, index, *, entry, stop, tp1, atr_val, direction,
                          strategy, horizon_key, level_map=None):
    """Re-price (stop, tp1) against what price has actually done to nearby levels.

    Two independent, independently-flagged adjustments:

      * stop anchoring -- move the stop beyond a level that has been *tested*
        rather than leaving it inside the noise a fresh level implies. The
        target is re-derived from the new risk distance so the frozen R:R
        table is preserved exactly (same arithmetic as _atr_plan).
      * target realism -- pull TP1 back inside the nearest undelivered
        "gatekeeper" standing between entry and target.

    Both are capped by the frozen constants: max_risk_pct bounds the stop, and
    an adjustment that would push R:R under RR_FLOOR is discarded rather than
    applied. Returns (stop, tp1, meta).

    COST NOTE: with a flag on and no level_map (i.e. in the backtest), this
    builds a level map per entry bar. Entries are sparse -- single digits per
    ticker/strategy/horizon -- but a full grid still pays it thousands of
    times. Flags off is a bit-identical zero-cost fast path, which is why the
    check comes first.
    """
    stops_on = getattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    targets_on = getattr(config, "LEVEL_LIFECYCLE_TARGETS_ENABLED", False)
    if not (stops_on or targets_on):
        return stop, tp1, {}

    try:
        levels = _lifecycle_levels(df, index, horizon_key, entry, level_map)
    except Exception:
        log.debug("level lifecycle unavailable at %s/%s", strategy, horizon_key, exc_info=True)
        return stop, tp1, {}
    if not levels:
        return stop, tp1, {}

    from swingbot.core.market import levels_lifecycle

    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    rr = _rr_for(strategy, horizon_key)
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    meta: dict = {}

    if stops_on:
        anchor = levels_lifecycle.preferred_stop_anchor(levels, direction=direction)
        # Only a level that has actually held is worth moving a stop for; a
        # fresh one is an untested guess and the ATR stop is already that.
        if anchor is not None and anchor.state == "tested":
            candidate = anchor.price - buffer if is_bull else anchor.price + buffer
            risk = entry - candidate if is_bull else candidate - entry
            # Widen only. Tightening onto a level would put the stop inside
            # the very structure it is meant to sit behind.
            if 0 < risk <= max_risk_amount and risk > abs(entry - stop):
                stop = candidate
                tp1 = entry + risk * rr if is_bull else entry - risk * rr
                meta["lifecycle_stop"] = {"price": round(anchor.price, 4),
                                          "state": anchor.state,
                                          "touches": anchor.touches}

    if targets_on:
        blockers = levels_lifecycle.gatekeepers_between(levels, entry=entry, target=tp1)
        if blockers:
            gk = blockers[0]
            candidate = gk.price - buffer if is_bull else gk.price + buffer
            reward = candidate - entry if is_bull else entry - candidate
            risk = abs(entry - stop)
            if reward > 0 and risk > 0 and reward / risk >= RR_FLOOR:
                tp1 = candidate
                meta["lifecycle_target"] = {"price": round(gk.price, 4),
                                            "state": gk.state,
                                            "blockers": len(blockers)}
            else:
                # Recorded, not applied: pulling in here would break the frozen
                # R:R floor, and that floor outranks this heuristic.
                meta["lifecycle_target_skipped"] = len(blockers)

    return stop, tp1, meta


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


def _fibonacci_plan(entry, atr_val, swing_high, swing_low, direction, horizon_key,
                    candidate_levels=None):
    """Structural sizing off the fib swing, risk-capped. Target is the
    nearest real Fibonacci level (fib_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31) -- see
    select_structural_target. Returns None when no candidate clears the
    floor: no fallback to a fixed fraction of risk."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    if is_bull:
        stop_loss = swing_low - buffer
    else:
        stop_loss = swing_high + buffer

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit


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


def _sr_plan(entry, volume_ratio, direction, horizon_key, candidate_levels=None):
    """Fixed-percent stop. Target is the nearest real S/R candidate
    (sr_target_candidates) that pays at least MIN_RISK_REWARD_RATIO, capped
    at MAX_RISK_REWARD_RATIO (v31). Returns None when no candidate clears
    the floor."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    stop_pct = h["sr_stop_pct"]
    stop_loss = entry * (1 - stop_pct / 100) if is_bull else entry * (1 + stop_pct / 100)

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit


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


def _elliott_plan(entry, atr_val, wave2, direction, horizon_key, candidate_levels=None):
    """Stop beyond wave-2 (buffered, risk-capped). Target is the nearest
    real wave-3 projection (elliott_target_candidates) that pays at least
    MIN_RISK_REWARD_RATIO, capped at MAX_RISK_REWARD_RATIO (v31). Returns
    None when no candidate clears the floor."""
    h = HORIZONS[horizon_key]
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    stop_loss = wave2 - buffer if is_bull else wave2 + buffer

    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount

    take_profit = select_structural_target(
        entry, stop_loss, is_bull, candidate_levels or [],
        config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if take_profit is None:
        return None
    return stop_loss, take_profit


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


def _journal_entries() -> list:
    """Every journal entry, for the MAE-informed stop lookup (edge E31).
    Split out as a module-level seam so the lookup can be stubbed in tests
    without touching disk, and so the import stays lazy -- plan_engine has
    no business depending on the analytics package at import time."""
    from swingbot.core.analytics.journal import JournalStore
    return JournalStore().entries()


def _resolve_stop_mult(strategy: str) -> float | None:
    """Live-path resolution of E31's MAE-informed stop factor. Returns None
    -- meaning "size exactly as before" -- when the flag is off, when the
    strategy has fewer than stops.MIN_SAMPLE journaled winners, or when
    reading the journal fails at all. Sizing must never depend on an
    analytics file being readable."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import mae_informed_stop_mult
        return mae_informed_stop_mult(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("MAE-informed stop lookup failed for %s: %s -- sizing unchanged",
                    strategy, exc)
        return None


def _resolve_tp2_r(strategy: str) -> float | None:
    """Live-path resolution of E32's MFE-informed TP2 R-multiple. Same
    flag, same degrade-to-None contract as _resolve_stop_mult."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import mfe_informed_tp2_r
        return mfe_informed_tp2_r(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("MFE-informed TP2 lookup failed for %s: %s -- TP2 unchanged",
                    strategy, exc)
        return None


def _resolve_time_stop_days(strategy: str) -> int | None:
    """Live-path resolution of E32's time stop. Recorded on the plan for
    E48's recycler; it closes nothing by itself."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import optimal_time_stop_days
        return optimal_time_stop_days(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("Time-stop lookup failed for %s: %s -- not recorded", strategy, exc)
        return None


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


def build_strategy_plan(df, index, *, ticker, strategy, horizon_key,
                        direction, level_map=None, quality_inputs=None,
                        stop_mult=None, tp2_r=None,
                        time_stop_days=None) -> TradePlanV2 | None:
    """THE constructor for strategy-source plans. Returns None when the
    strategy has no valid structure at this bar (same conditions as the
    backtest reference).

    `stop_mult` (edge E31), `tp2_r` and `time_stop_days` (edge E32): the
    MAE/MFE-derived overrides. Left None, each is resolved from the live
    journal iff config.DATA_DRIVEN_STOPS_ENABLED -- so the flag-off path
    is bit-identical to before and never opens the journal at all."""
    from swingbot.core.market.indicators import atr as atr_indicator
    from swingbot.core.market.indicators import elliott_wave3_entries

    close = float(df["Close"].iloc[index])
    atr_series = atr_indicator(df, 14)
    atr_val = _safe_atr_value(close, float(atr_series.iloc[index]))
    h = HORIZONS[horizon_key]
    applied_stop_mult = None

    if strategy == "Fibonacci":
        lookback = h["fib_lookback"]
        swing_high = float(df["High"].rolling(lookback).max().iloc[index])
        swing_low = float(df["Low"].rolling(lookback).min().iloc[index])
        if not (np.isfinite(swing_high) and np.isfinite(swing_low)):
            return None
        candidates = fib_target_candidates(df, index, h, close)
        result = _fibonacci_plan(close, atr_val, swing_high, swing_low, direction, horizon_key,
                                 candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    elif strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        ratio = float((df["Volume"] / vol_avg20).iloc[index])
        candidates = sr_target_candidates(df, index, h, close, ratio)
        result = _sr_plan(close, ratio, direction, horizon_key, candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    elif strategy == "Elliott Wave":
        _, _, entry_levels = elliott_wave3_entries(df, h["max_risk_pct"])
        if not entry_levels or index not in entry_levels:
            return None
        candidates = elliott_target_candidates(entry_levels[index], direction)
        result = _elliott_plan(close, atr_val, entry_levels[index]["wave2"], direction, horizon_key,
                               candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result
    else:
        # Only the genuine ATR-multiple path takes the MAE adjustment
        # (edge E31). The three branches above put their stop behind real
        # structure -- a fib swing, an Elliott wave-2 low, an S/R shelf --
        # and scaling those would slide the stop off the very structure it
        # exists to hide behind. That's a different, unvalidated idea from
        # "give the ATR stop the room this strategy's winners actually
        # used", so they stay structure-derived on purpose.
        applied_stop_mult = stop_mult if stop_mult is not None else _resolve_stop_mult(strategy)
        candidates = atr_target_candidates(close, atr_val, direction)
        result = _atr_plan(close, atr_val, direction, horizon_key, strategy,
                           stop_mult=applied_stop_mult, candidate_levels=candidates)
        if result is None:
            return None
        stop, tp1 = result

    # P1: the same adjuster backtest._trade_plan_at calls, with the level_map
    # this path already has (so it costs no extra level build here).
    # meta is intentionally unused for now: surfacing which level drove the
    # plan means a TradePlanV2 field, which is a persisted-schema change and a
    # separate piece of work from wiring the adjuster in.
    stop, tp1, _lifecycle_meta = apply_level_lifecycle(
        df, index, entry=close, stop=stop, tp1=tp1, atr_val=atr_val,
        direction=direction, strategy=strategy, horizon_key=horizon_key,
        level_map=level_map)

    if abs(close - stop) <= 0:
        return None

    entry_type = entry_type_for(strategy, "strategy")
    created_at = df.index[index].date().isoformat()
    exit_params = exit_params_for(strategy)
    tp2 = None
    applied_tp2_r = None
    if exit_params["tp2"]:
        if level_map is not None:
            supports, resistances = level_map
            levels_above = [lv.price for lv in resistances]
            levels_below = [lv.price for lv in supports]
            tp2 = select_tp2(levels_above, levels_below, direction, close, tp1)
        # MFE-informed TP2 (edge E32): re-price the runner target at the
        # R-multiple this strategy's winners actually reached, when that
        # produces a valid TP2. Deliberately does NOT switch TP2 on for a
        # strategy whose exit params have none -- that on/off table is a
        # frozen TRAIN-grid result, and forcing it would be a different
        # exit model than E33 is set up to judge.
        resolved_tp2_r = tp2_r if tp2_r is not None else _resolve_tp2_r(strategy)
        if resolved_tp2_r is not None:
            candidate = _tp2_from_r(close, stop, tp1, direction, resolved_tp2_r)
            if candidate is not None:
                tp2, applied_tp2_r = candidate, resolved_tp2_r
    plan = TradePlanV2(
        plan_id=str(uuid.uuid4()), ticker=ticker, created_at=created_at,
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=direction, entry_type=entry_type, trigger_price=close,
        entry_price=close if entry_type == "market" else None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=stop, tp1=tp1,
        tp1_fraction=TP1_FRACTION, tp2=tp2,
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=exit_params["trail_atr_mult"],
        quality_score=0, quality_breakdown=[],
        tier="C", badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    stamp_badge(plan)
    _apply_quality(plan, quality_inputs)
    plan.stop_mult_applied = applied_stop_mult
    plan.tp2_r_applied = applied_tp2_r
    plan.time_stop_days = (time_stop_days if time_stop_days is not None
                           else _resolve_time_stop_days(strategy))
    return plan


def _apply_quality(plan: TradePlanV2, quality_inputs: dict | None) -> None:
    if quality_inputs is None:
        return
    from swingbot.core.planning.quality import score_plan
    q = score_plan(direction=plan.direction, badge_status=plan.badge, **quality_inputs)
    plan.quality_score, plan.tier = q.score, q.tier
    plan.quality_breakdown = q.breakdown


# ---------------------------------------------------------------------------
# Confluence-source plans — built from a levels.build_scenarios() Scenario
# rather than a per-bar strategy signal.
# ---------------------------------------------------------------------------

CONFLUENCE_BREAKOUT_LOOKBACK = 20  # same fixed window levels.py's own Donchian candidate uses


def scenario_is_breakout(scenario, df) -> bool:
    """
    True when hitting the scenario's own target requires price to make a
    new local extreme -- i.e. the target sits beyond the recent N-bar
    trading range (the same 20-bar Donchian-style window levels.py already
    sources a candidate level from; see collect_candidate_levels), rather
    than just completing a move inside a range that already contains it.
    Breakout-direction scenarios get a stop-entry trigger instead of an
    immediate market fill (see build_confluence_plan).

    The lookback excludes the in-progress last bar (`.shift(1)`), matching
    collect_candidate_levels's own Donchian computation.
    """
    is_bull = scenario.direction == "bullish"
    if is_bull:
        recent_extreme = df["High"].rolling(CONFLUENCE_BREAKOUT_LOOKBACK).max().shift(1).iloc[-1]
        if not np.isfinite(recent_extreme):
            return False
        return scenario.take_profit > float(recent_extreme)
    recent_extreme = df["Low"].rolling(CONFLUENCE_BREAKOUT_LOOKBACK).min().shift(1).iloc[-1]
    if not np.isfinite(recent_extreme):
        return False
    return scenario.take_profit < float(recent_extreme)


def primary_strategy_for(scenario) -> str:
    """Real strategy attribution for a confluence scenario: the highest-
    priority confirming method behind its target (falling back to the stop's
    methods, then the legacy literal). Delegates the ranking to
    chart_geometry._pick_primary_source -- ONE priority list for charts,
    trade rows, and plan attribution. Imported lazily (matplotlib chain)."""
    from swingbot.core.charts.chart_geometry import _pick_primary_source
    sources = list(getattr(scenario, "target_sources", []) or []) \
        + list(getattr(scenario, "stop_sources", []) or [])
    return _pick_primary_source(sources) or "S/R Confluence"


def build_confluence_plan(scenario, df, *, ticker, horizon_key,
                          primary_strategy, level_map=None,
                          quality_inputs=None) -> TradePlanV2 | None:
    """THE constructor for confluence-source plans (a levels.build_scenarios
    Scenario). TP1 is a real structural level -- select_structural_target
    picks the nearest candidate that pays at least MIN_RISK_REWARD_RATIO,
    capped at MAX_RISK_REWARD_RATIO (v31). Returns None when nothing
    qualifies: there is deliberately no fallback to a fixed fraction of
    risk, since that arithmetic is exactly the bug this plan fixes.
    `primary_strategy` is the real per-scenario attribution (see
    primary_strategy_for). `level_map` is an optional (supports, resistances)
    pair from levels.build_level_map -- when absent, the only honest
    candidate is the scenario's own real target."""
    entry = scenario.entry
    is_bull = scenario.direction == "bullish"

    if level_map is not None:
        candidates = levels.target_candidates(*level_map, scenario.direction)
    else:
        candidates = [scenario.take_profit] if scenario.take_profit is not None else []

    tp1 = select_structural_target(entry, scenario.stop_loss, is_bull, candidates,
                                   config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
    if tp1 is None:
        return None

    if level_map is not None:
        supports, resistances = level_map
        resistances_prices = [float(lv.price) for lv in resistances]
        supports_prices = [float(lv.price) for lv in supports]
        tp2 = select_tp2(resistances_prices, supports_prices, scenario.direction, entry, tp1)
    else:
        tp2 = None
        if scenario.take_profit is not None:
            beyond_tp1 = scenario.take_profit > tp1 if is_bull else scenario.take_profit < tp1
            if beyond_tp1:
                tp2 = scenario.take_profit

    entry_type = "stop_entry" if scenario_is_breakout(scenario, df) else "market"
    created_at = df.index[-1].date().isoformat()

    plan = TradePlanV2(
        plan_id=str(uuid.uuid4()), ticker=ticker, created_at=created_at,
        source="confluence", strategy=primary_strategy, horizon_key=horizon_key,
        direction=scenario.direction, entry_type=entry_type, trigger_price=entry,
        entry_price=entry if entry_type == "market" else None,
        expiry_bars=DEFAULT_EXPIRY_BARS, stop_loss=scenario.stop_loss, tp1=tp1,
        tp1_fraction=TP1_FRACTION, tp2=tp2,
        breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=TRAIL_ATR_MULT, quality_score=0, quality_breakdown=[],
        tier="C", badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
    )
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
    stamp_badge(plan)
    _apply_quality(plan, quality_inputs)
    return plan


# Strategy-source plans enter at the signal close ("market") — this is the
# entry the round-1 validation measured. Task 30's TRAIN grid may flip
# breakout-class strategies to stop_entry iff it clears the acceptance gates.
STRATEGY_ENTRY_TYPE: dict[str, str] = {}

# Rendered verbatim by embeds for plans whose source failed the 80% OOS bar.
WEAK_CAUTION_TEXT = (
    "⚠️ WEAK: this setup did not reach 80% win rate out-of-sample "
    "(WR {win_rate:.1f}%, N={n}). Treat with extra care — reduced size, "
    "manual confirmation recommended."
)


def entry_type_for(strategy: str, source: str) -> str:
    if source == "confluence":
        return "stop_entry"
    return STRATEGY_ENTRY_TYPE.get(strategy, "market")


def stamp_badge(plan: TradePlanV2) -> None:
    """Set badge + badge_stats from the committed validation registry."""
    b = get_badge(plan.source, plan.strategy, plan.horizon_key)
    plan.badge = b.status
    plan.badge_stats = {"status": b.status, "n": b.n, "win_rate": b.win_rate,
                        "expectancy_r": b.expectancy_r, "window": b.window}


def badge_stats_line(badge: Badge) -> str:
    window = badge.window.replace("-01-01..", "-").replace("-12-31", "") or "n/a"
    return (f"OOS {window}: N={badge.n}, WR {badge.win_rate:.1f}%, "
            f"ExpR {badge.expectancy_r:+.3f}")


def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine."""
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    plan.status_history.append({"status": new_status, "reason": reason, "at": at})


# ---------------------------------------------------------------------------
# Stop-entry trigger + expiry semantics -- single source of truth for a
# pending stop_entry plan's bar-by-bar fate. Phase 2's exit simulator and
# Phase 5's live plan manager both call these instead of re-deriving the
# comparisons, so keep the boundary-equality behavior exactly as documented
# below (each one was a deliberate spec choice, not an oversight).
# ---------------------------------------------------------------------------

def trigger_hit(plan: TradePlanV2, bar_high: float, bar_low: float) -> bool:
    """True when this bar touched the stop_entry trigger. Bullish triggers
    are breakouts above trigger_price (bar_high >= trigger_price); bearish
    triggers are breakdowns below it (bar_low <= trigger_price). Touching
    the trigger exactly counts as a hit."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return bar_high >= plan.trigger_price
    return bar_low <= plan.trigger_price


def fill_price(plan: TradePlanV2, bar_open: float) -> float:
    """Worst-of fill for the bar that triggered: if the open already gapped
    through the trigger, you fill at the (worse) open; otherwise you fill
    at the trigger itself -- never better than trigger_price."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return max(bar_open, plan.trigger_price)
    return min(bar_open, plan.trigger_price)


def pending_expired(plan: TradePlanV2, bars_since_created: int) -> bool:
    """True once a still-pending stop_entry plan has waited longer than its
    expiry_bars window. Equality does not count as expired -- the plan gets
    the full expiry_bars-th bar to still trigger."""
    return bars_since_created > plan.expiry_bars


def pending_invalidated(plan: TradePlanV2, bar_close: float) -> bool:
    """True when price closes through the stop while the plan is still
    pending (trigger never fired) -- the setup's thesis broke before entry.
    Bullish: close <= stop_loss; bearish: close >= stop_loss. Closing
    exactly on the stop counts as invalidated."""
    is_bull = plan.direction == "bullish"
    if is_bull:
        return bar_close <= plan.stop_loss
    return bar_close >= plan.stop_loss


# ---------------------------------------------------------------------------
# Phase 2: exit model v2 (hybrid scale-out). simulate_exit is the shared
# bar-by-bar walk that backtest.py and (eventually) the live plan manager
# both call. Task 20 built the ENTRY phase -- how a signal becomes a filled
# trade (or a not_triggered stop_entry) -- reusing the Task 18 trigger/fill/
# expiry/invalidation helpers above rather than re-deriving them. Task 21
# adds the single-leg (scale_out=False) exit walk's win/loss cases, extracted
# verbatim from backtest.py's run_backtest loop so scale_out=False reproduces
# that reference exactly. Scratch/timeout polish and same-bar-ordering edge
# cases beyond what falls out of the verbatim extraction, plus scale-out legs,
# are Task 22+.
# ---------------------------------------------------------------------------

@dataclass
class ExitResult:
    outcome: str                 # "win"|"loss"|"scratch"|"timeout"|"not_triggered"|"no_trade"
    runner_outcome: str | None   # "runner_tp2"|"runner_trail"|"runner_be"|"runner_timeout"|None
    entry_index: int | None
    exit_index: int | None
    entry_price: float | None
    r_total: float               # sum over legs of fraction * signed_r
    legs: list                   # [{"fraction","exit_price","r","reason"}]


def _not_triggered() -> ExitResult:
    return ExitResult(
        outcome="not_triggered",
        runner_outcome=None,
        entry_index=None,
        exit_index=None,
        entry_price=None,
        r_total=0.0,
        legs=[],
    )


def _single_leg_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
) -> ExitResult:
    """Round-1 (scale_out=False) exit walk: extracted verbatim from
    backtest.py's run_backtest loop. Walks bars entry_index+1 .. min(entry_index
    + max_holding_days, n-1), tracking a break-even stop move once favorable
    excursion reaches breakeven_trigger_fraction * |tp1 - entry| (the moved
    stop only protects bars AFTER the trigger bar -- not the trigger bar
    itself). Same-bar ordering is conservative: stop is checked before target.
    win -> r = +rr where rr = |tp1 - entry| / risk; loss (stop hit pre-BE
    move) -> r = -1.0; scratch (stop hit post-BE move) -> r = 0.0; timeout ->
    r marked to the last scanned bar's close. Single leg always carries
    fraction=1.0 (round-1 has no partial exits)."""
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    stop_loss = plan.stop_loss
    tp1 = plan.tp1
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None,
                          entry_index=entry_index, exit_index=None,
                          entry_price=entry_price, r_total=0.0, legs=[])
    target_dist = abs(tp1 - entry_price)
    rr = target_dist / risk

    if is_bull:
        be_trigger = entry_price + plan.breakeven_trigger_fraction * target_dist
    else:
        be_trigger = entry_price - plan.breakeven_trigger_fraction * target_dist
    stop_moved = False

    end = min(entry_index + max_holding_days, n - 1)
    outcome, exit_price, exit_index = "timeout", None, None

    for j in range(entry_index + 1, end + 1):
        hi, lo = float(high[j]), float(low[j])
        cur_stop = entry_price if stop_moved else stop_loss
        if is_bull:
            hit_stop = lo <= cur_stop
            hit_target = hi >= tp1
            reached_trigger = hi >= be_trigger
        else:
            hit_stop = hi >= cur_stop
            hit_target = lo <= tp1
            reached_trigger = lo <= be_trigger

        # Conservative ordering: stop first (original stop still governs the
        # bar that first reaches the trigger), then target. The moved stop
        # only protects bars AFTER the trigger bar.
        if hit_stop:
            outcome = "scratch" if stop_moved else "loss"
            exit_price, exit_index = cur_stop, j
            break
        if hit_target:
            outcome, exit_price, exit_index = "win", tp1, j
            break
        if reached_trigger and not stop_moved:
            stop_moved = True

    if outcome == "timeout":
        exit_price, exit_index = float(close[end]), end

    if outcome == "win":
        r, reason = rr, "tp1"
    elif outcome == "loss":
        r, reason = -1.0, "stop"
    elif outcome == "scratch":
        r, reason = 0.0, "breakeven_stop"
    else:  # timeout
        r = (exit_price - entry_price) * sign / risk
        reason = "timeout"

    r = round(r, 3)

    return ExitResult(
        outcome=outcome,
        runner_outcome=None,
        entry_index=entry_index,
        exit_index=exit_index,
        entry_price=entry_price,
        r_total=r,
        legs=[{"fraction": 1.0, "exit_price": exit_price, "r": r, "reason": reason}],
    )


def chandelier_stop(extreme_close_since_tp1: float, atr_value: float,
                    mult: float, direction: str) -> float:
    """Classic chandelier exit level for the runner leg: the extreme close
    since TP1 minus (bullish) / plus (bearish) mult x ATR."""
    if direction == "bullish":
        return extreme_close_since_tp1 - mult * atr_value
    return extreme_close_since_tp1 + mult * atr_value


def _scale_out_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
) -> ExitResult:
    """Hybrid scale-out walk (spec Sec5). Phase 1 (pre-TP1) is byte-identical
    to _single_leg_exit_walk; a stop/scratch/timeout before TP1 returns the
    same single full-fraction leg. TP1 touch banks tp1_fraction at tp1 and
    hands the rest to the runner: stop starts at entry (BE) and ratchets
    toward profit via a chandelier trail (Task 26) as the runner rides, with
    an optional TP2 target (Task 25). Task 27 still owes runner-timeout
    test coverage."""
    from swingbot.core.market.indicators import atr as atr_indicator

    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    stop_loss, tp1 = plan.stop_loss, plan.tp1
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None,
                          entry_index=entry_index, exit_index=None,
                          entry_price=entry_price, r_total=0.0, legs=[])
    target_dist = abs(tp1 - entry_price)
    rr = target_dist / risk
    frac1 = plan.tp1_fraction
    frac2 = 1.0 - frac1

    be_trigger = entry_price + sign * plan.breakeven_trigger_fraction * target_dist
    stop_moved = False
    end = min(entry_index + max_holding_days, n - 1)

    # ---- phase 1: identical to the single-leg walk until TP1 touches ----
    tp1_index = None
    for j in range(entry_index + 1, end + 1):
        hi, lo = float(high[j]), float(low[j])
        cur_stop = entry_price if stop_moved else stop_loss
        if is_bull:
            hit_stop, hit_target = lo <= cur_stop, hi >= tp1
            reached_trigger = hi >= be_trigger
        else:
            hit_stop, hit_target = hi >= cur_stop, lo <= tp1
            reached_trigger = lo <= be_trigger

        if hit_stop:  # conservative: stop first, exactly as single-leg
            outcome = "scratch" if stop_moved else "loss"
            r = round(0.0 if stop_moved else -1.0, 3)
            reason = "breakeven_stop" if stop_moved else "stop"
            return ExitResult(outcome=outcome, runner_outcome=None,
                              entry_index=entry_index, exit_index=j,
                              entry_price=entry_price, r_total=r,
                              legs=[{"fraction": 1.0, "exit_price": cur_stop,
                                     "r": r, "reason": reason}])
        if hit_target:
            tp1_index = j
            break
        if reached_trigger and not stop_moved:
            stop_moved = True

    if tp1_index is None:   # timeout before TP1 -- identical to single-leg
        exit_price = float(close[end])
        r = round((exit_price - entry_price) * sign / risk, 3)
        return ExitResult(outcome="timeout", runner_outcome=None,
                          entry_index=entry_index, exit_index=end,
                          entry_price=entry_price, r_total=r,
                          legs=[{"fraction": 1.0, "exit_price": exit_price,
                                 "r": r, "reason": "timeout"}])

    leg1 = {"fraction": frac1, "exit_price": tp1, "r": round(rr, 3), "reason": "tp1"}

    # ---- phase 2: runner. Stop starts at entry (BE); protects bars AFTER
    # the TP1 bar (same "subsequent bars only" convention as the BE move).
    # Task 25 added the TP2 branch; Task 26 adds the chandelier ratchet: the
    # stop trails the extreme close since TP1 by trail_atr_mult x ATR(14),
    # only ever moving toward profit (never back down toward BE).
    runner_stop = entry_price
    runner_exit = runner_reason = None
    exit_index = None
    tp2 = plan.tp2
    extreme_close = float(close[tp1_index])
    atr_series = atr_indicator(df, 14)
    checked_stop = runner_stop   # the level checked against the CURRENT bar; stays
                                 # at the initial BE value if the loop below never runs

    for j in range(tp1_index + 1, end + 1):
        checked_stop = runner_stop   # snapshot BEFORE this bar's own ratchet
        hi, lo = float(high[j]), float(low[j])
        if (lo <= runner_stop) if is_bull else (hi >= runner_stop):
            runner_exit, exit_index = runner_stop, j
            runner_reason = "runner_be" if runner_stop == entry_price else "runner_trail"
            break
        if tp2 is not None and ((hi >= tp2) if is_bull else (lo <= tp2)):
            runner_exit, exit_index, runner_reason = tp2, j, "runner_tp2"
            break
        # No exit this bar: ratchet the stop for the NEXT iteration using
        # THIS bar's close only -- no intrabar lookahead.
        extreme_close = (max(extreme_close, float(close[j])) if is_bull
                          else min(extreme_close, float(close[j])))
        atr_val = _safe_atr_value(entry_price, float(atr_series.iloc[j]))
        trail = chandelier_stop(extreme_close, atr_val, plan.trail_atr_mult, plan.direction)
        runner_stop = max(runner_stop, trail) if is_bull else min(runner_stop, trail)

    if runner_exit is None:   # Task 27 pins the runner-timeout case with tests
        # Clamp to checked_stop (the level actually checked against the last
        # bar walked, or the initial BE if the loop never ran) -- NOT the
        # live runner_stop, which may already be ratcheted past what that
        # bar's own low/high were ever tested against.
        exit_px = float(close[end])
        runner_exit = max(exit_px, checked_stop) if is_bull else min(exit_px, checked_stop)
        exit_index, runner_reason = end, "runner_timeout"

    r2 = round((runner_exit - entry_price) * sign / risk, 3)
    leg2 = {"fraction": frac2, "exit_price": runner_exit, "r": r2,
            "reason": runner_reason}
    return ExitResult(outcome="win", runner_outcome=runner_reason,
                      entry_index=entry_index, exit_index=exit_index,
                      entry_price=entry_price,
                      r_total=round(frac1 * rr + frac2 * r2, 3),
                      legs=[leg1, leg2])


def simulate_exit(
    df,
    signal_index: int,
    plan: TradePlanV2,
    *,
    scale_out: bool = False,
    max_holding_days: int | None = None,
) -> ExitResult:
    """Shared entry + exit simulator (Tasks 18/20/21/24).

    ``market`` entries fill immediately at the signal bar's close.
    ``stop_entry`` entries scan forward from signal_index + 1 through the
    plan's expiry window looking for a trigger touch (Task 18's
    ``trigger_hit``/``fill_price``). If the plan invalidates (closes through
    the stop) or expires before triggering, this returns a terminal
    ``ExitResult("not_triggered", ...)``.

    Once entry is established, ``scale_out=False`` (the default) walks the
    single-leg round-1 exit (Task 21): win (TP1 touched), loss (stop hit
    before the break-even move), scratch (stop hit after the break-even
    move), or timeout -- extracted verbatim from backtest.py's run_backtest
    loop. ``scale_out=True`` walks the hybrid scale-out exit (Task 24+):
    pre-TP1 phase is identical to the single-leg walk; TP1 touch banks
    tp1_fraction and hands the rest to a runner whose stop starts at
    break-even, ratchets via a chandelier ATR trail (Task 26), and can also
    exit at an optional TP2 (Task 25).
    """
    # Resolved eagerly per the interface contract -- both the single-leg
    # (Task 21) and scale-out (Task 24+) exit walks use it to bound the
    # timeout scan.
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]

    if plan.entry_type == "market":
        entry_index = signal_index
        entry_price = float(df["Close"].values[signal_index])
        if not scale_out:
            return _single_leg_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
        return _scale_out_exit_walk(df, entry_index, entry_price, plan, max_holding_days)

    # stop_entry: scan signal_index+1 .. signal_index+plan.expiry_bars for a
    # trigger touch, watching for pre-fill invalidation along the way.
    high = df["High"].values
    low = df["Low"].values
    open_ = df["Open"].values
    close = df["Close"].values
    n = len(df)

    j = signal_index + 1
    while j < n:
        bars_since_created = j - signal_index
        if pending_expired(plan, bars_since_created):
            break
        if trigger_hit(plan, float(high[j]), float(low[j])):
            entry_index = j
            entry_price = fill_price(plan, float(open_[j]))
            if not scale_out:
                return _single_leg_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
            return _scale_out_exit_walk(df, entry_index, entry_price, plan, max_holding_days)
        if pending_invalidated(plan, float(close[j])):
            return _not_triggered()
        j += 1

    return _not_triggered()
