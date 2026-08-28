"""Plan-level lifecycle adjustment and stop-entry transition primitives."""
from __future__ import annotations

import logging

from swingbot import config
from swingbot.core.market.strategy_types import HORIZONS
from .plan_types import TradePlanV2
from .params import STRUCTURE_BUFFER_ATR
from .targets import select_structural_target

log = logging.getLogger("swing-bot.plan_engine")
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
                          strategy, horizon_key, level_map=None, candidate_levels=None):
    """Re-price `stop` against what price has actually done to nearby levels --
    move it beyond a level that has been *tested* rather than leaving it
    inside the noise a fresh level implies. (The old "target realism"
    adjustment -- pulling TP1 back inside a gatekeeper level -- was measured
    inert, rejected 248/248; its flag and branch, and the gatekeeper-lookup
    helper it was the only caller of, are gone as of v31 Task 14.)

    Widening the stop changes risk, so `tp1` is RE-SELECTED against the new
    risk from the same `candidate_levels` the caller's builder used -- there
    is no longer a frozen R:R formula to recompute it from (v31). If nothing
    on that candidate list clears MIN_RISK_REWARD_RATIO against the wider
    stop, the widening is rolled back entirely and the original (stop, tp1)
    pair is returned untouched: a wider stop with no target that pays for it
    is strictly worse than the tighter stop this function started with, and
    the reward:risk guarantee is the contract, not the widening. Returns
    (stop, tp1, meta).

    COST NOTE: with the flag on and no level_map (i.e. in the backtest), this
    builds a level map per entry bar. Entries are sparse -- single digits per
    ticker/strategy/horizon -- but a full grid still pays it thousands of
    times. Flag off is a bit-identical zero-cost fast path, which is why the
    check comes first.
    """
    stops_on = getattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    if not stops_on:
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
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    meta: dict = {}

    anchor = levels_lifecycle.preferred_stop_anchor(levels, direction=direction)
    # Only a level that has actually held is worth moving a stop for; a
    # fresh one is an untested guess and the ATR stop is already that.
    if anchor is not None and anchor.state == "tested":
        candidate = anchor.price - buffer if is_bull else anchor.price + buffer
        risk = entry - candidate if is_bull else candidate - entry
        # Widen only. Tightening onto a level would put the stop inside
        # the very structure it is meant to sit behind.
        if 0 < risk <= max_risk_amount and risk > abs(entry - stop):
            new_tp1 = select_structural_target(
                entry, candidate, is_bull, candidate_levels or [],
                config.MIN_RISK_REWARD_RATIO, config.MAX_RISK_REWARD_RATIO)
            if new_tp1 is None:
                # ROLL BACK. Widening the stop is a refinement; the
                # reward:risk guarantee is the contract. A wider stop with
                # no target that pays for it is strictly worse than the
                # tighter stop we already had, so keep the original pair
                # untouched -- do NOT keep the wide stop with the old
                # target, which is exactly the inverted-R:R plan this
                # change exists to stop shipping.
                meta["lifecycle_stop_rolled_back"] = {
                    "price": round(anchor.price, 4), "state": anchor.state}
            else:
                stop, tp1 = candidate, new_tp1
                meta["lifecycle_stop"] = {"price": round(anchor.price, 4),
                                          "state": anchor.state,
                                          "touches": anchor.touches}

    return stop, tp1, meta


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


