"""The v2 exit simulator -- shared, by construction, with the backtest.

backtesting/backtest.py's run_backtest(..., exit_model="v2", scale_out=True)
calls simulate_exit() here, which is what makes live behaviour equal
backtested behaviour. Any change here changes what VALIDATED badges mean.
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot.core.market.strategy_types import HORIZONS
from .plan_types import TradePlanV2
from .params import RUNNER_FLOOR_FRACTION
from .lifecycle import trigger_hit, fill_price, pending_expired, pending_invalidated
from .targets import _safe_atr_value
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


def runner_floor(entry: float, tp1: float) -> float:
    """The runner leg's stop the instant TP1 fires (v39).

    ``entry + RUNNER_FLOOR_FRACTION * (tp1 - entry)`` -- 2/3 of the
    entry->TP1 move locked in, so a reversal right after TP1 gives back at
    most a third of that leg's gain instead of all of it. Replaces the plain
    breakeven (``entry``) floor the scale-out model shipped with.

    One formula, both directions: ``tp1 - entry`` is already signed per
    direction (positive for a bullish plan, negative for a bearish one), so
    no ``is_bull`` branch is needed at any call site.

    Single source of truth. ``plan_manager.py`` imports this rather than
    re-declaring the expression, exactly as it already does for
    ``chandelier_stop`` -- the live poll path, the overnight bar-check path
    and this module's backtest walk must never drift apart.
    """
    return entry + RUNNER_FLOOR_FRACTION * (tp1 - entry)


def _scale_out_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
) -> ExitResult:
    """Hybrid scale-out walk (spec Sec5). Phase 1 (pre-TP1) is byte-identical
    to _single_leg_exit_walk; a stop/scratch/timeout before TP1 returns the
    same single full-fraction leg. TP1 touch banks tp1_fraction at tp1 and
    hands the rest to the runner: stop starts at the v39 runner floor
    (entry + 2/3 x (tp1 - entry), see runner_floor) and ratchets
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

    # ---- phase 2: runner. Stop starts at the v39 runner floor (entry +
    # RUNNER_FLOOR_FRACTION x (tp1 - entry)), NOT at plain breakeven; it
    # protects bars AFTER the TP1 bar (same "subsequent bars only"
    # convention as the BE move). Task 25 added the TP2 branch; Task 26 adds
    # the chandelier ratchet: the stop trails the extreme close since TP1 by
    # trail_atr_mult x ATR(14), only ever moving toward profit (never back
    # down toward the floor).
    runner_stop = runner_floor(entry_price, tp1)
    runner_exit = runner_reason = None
    exit_index = None
    tp2 = plan.tp2
    extreme_close = float(close[tp1_index])
    atr_series = atr_indicator(df, 14)
    checked_stop = runner_stop   # the level checked against the CURRENT bar; stays
                                 # at the initial runner-floor value if the loop
                                 # below never runs

    for j in range(tp1_index + 1, end + 1):
        checked_stop = runner_stop   # snapshot BEFORE this bar's own ratchet
        hi, lo = float(high[j]), float(low[j])
        if (lo <= runner_stop) if is_bull else (hi >= runner_stop):
            runner_exit, exit_index = runner_stop, j
            # v39: "runner_be" now means "closed at its initial post-TP1
            # floor", not literally at entry. The STRING is deliberately
            # unchanged -- ~30 files pattern-match it, including frozen
            # result JSONs under docs/superpowers/results/ and
            # performance.py's reason.startswith("tp1_") classifier.
            runner_reason = ("runner_be"
                             if runner_stop == runner_floor(entry_price, tp1)
                             else "runner_trail")
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
    tp1_fraction and hands the rest to a runner whose stop starts at the
    v39 runner floor (runner_floor: entry + 2/3 of the entry->TP1 move),
    ratchets via a chandelier ATR trail (Task 26), and can also
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

