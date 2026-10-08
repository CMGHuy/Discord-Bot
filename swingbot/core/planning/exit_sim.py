"""The v2 exit simulator -- shared, by construction, with the backtest.

backtesting/backtest.py's run_backtest(..., exit_model="v2", scale_out=True)
calls simulate_exit() here, which is what makes live behaviour equal
backtested behaviour. Any change here changes what VALIDATED badges mean.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingbot import config
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, HORIZONS
from swingbot.core.risk_limits import planned_loss_pct
from .stop_scope import plan_stop_ceiling
from .plan_types import TradePlanV2
from .params import RUNNER_FLOOR_FRACTION
from .lifecycle import (at_or_beyond_stop, fill_price, limit_fill_price, limit_hit,
                        pending_expired, pending_invalidated, stop_touched, trigger_hit)
from .targets import _safe_atr_value
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON

#: v121's pivot column names mapped to v123's. The ONLY place v121 column
#: names appear in v123; V123-1's gate step checks them against the merged module.
_V121_PIVOT_COLUMNS = {
    "sh_i": "last_sh_pos", "sh_px": "last_sh",
    "sh_prev_i": "prior_sh_pos", "sh_prev_px": "prior_sh",
    "sl_i": "last_sl_pos", "sl_px": "last_sl",
    "sl_prev_i": "prior_sl_pos", "sl_prev_px": "prior_sl",
}
PIVOT_K = 3                                      # v121 frozen fractal width


def _trend_ratio(series: pd.Series) -> pd.Series:
    """Per-bar mean(last SHORT_WINDOW) / mean(last LONG_WINDOW) -- the series
    form of v121's scalar _ratio_of_means. NaN before LONG_WINDOW bars; a zero
    long mean gives NaN, which no <= comparison passes."""
    from swingbot.core.market import structure
    short = series.rolling(structure.SHORT_WINDOW).mean()
    long = series.rolling(structure.LONG_WINDOW).mean()
    return (short / long).astype(float)


def runner_structure_frame(df) -> pd.DataFrame:
    """Per-bar confirmed pivots and range/volume trends for the v123 runner
    rules. Row j uses df.iloc[:j+1] only (v121 truncation contract; rolling
    windows are causal)."""
    from swingbot.core.market import structure
    pivots = structure.confirmed_pivots(df, k=PIVOT_K)
    out = pd.DataFrame(index=df.index)
    for ours, theirs in _V121_PIVOT_COLUMNS.items():
        out[ours] = pivots[theirs].astype(float).values
    out["range_trend_10_50"] = _trend_ratio(structure.true_range(df)).values
    out["vol_trend_10_50"] = _trend_ratio(df["Volume"].astype(float)).values
    return out


@dataclass
class ExitResult:
    outcome: str                 # "win"|"loss"|"scratch"|"timeout"|"not_triggered"|"no_trade"
    runner_outcome: str | None   # "runner_tp2"|"runner_trail"|"runner_be"|"runner_timeout"|
                                 # "runner_progress_stall"|None
    entry_index: int | None
    exit_index: int | None
    entry_price: float | None
    r_total: float               # sum over legs of fraction * signed_r
    legs: list                   # [{"fraction","exit_price","r","reason"}]
    # Why a not_triggered row was excluded ("risk_cap"|"expired"|"invalidated");
    # set only on the compression short's rows, None everywhere else.
    cancel_reason: str | None = None


def _not_triggered(cancel_reason: str | None = None) -> ExitResult:
    return ExitResult(
        outcome="not_triggered",
        runner_outcome=None,
        entry_index=None,
        exit_index=None,
        entry_price=None,
        r_total=0.0,
        legs=[],
        cancel_reason=cancel_reason,
    )


def acceptance_exit(plan: TradePlanV2, bar_close: float) -> bool:
    """v129: True when the plan carries an acceptance threshold and this bar
    CLOSED beyond it -- bullish strictly below, bearish strictly above. A
    wick through the threshold that closes back inside is not acceptance."""
    threshold = plan.acceptance_close_below
    if threshold is None:
        return False
    if plan.direction == "bullish":
        return bar_close < threshold
    return bar_close > threshold


def _acceptance_result(plan, j, close_j, entry_index, entry_price, sign, risk):
    """The v129 acceptance exit at close[j] as a full-position leg, or None."""
    if not acceptance_exit(plan, close_j):
        return None
    r = round((close_j - entry_price) * sign / risk, 3)
    return ExitResult(outcome="loss" if r < 0 else "scratch", runner_outcome=None,
                      entry_index=entry_index, exit_index=j, entry_price=entry_price,
                      r_total=r, legs=[{"fraction": 1.0, "exit_price": close_j,
                                        "r": r, "reason": "acceptance_exit"}])


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
        # v129: acceptance exit at this bar's close, after stop and target.
        accepted = _acceptance_result(plan, j, float(close[j]), entry_index,
                                      entry_price, sign, risk)
        if accepted is not None:
            return accepted
        if reached_trigger and not stop_moved:
            stop_moved = True

    if outcome == "timeout":
        exit_price, exit_index = float(close[end]), end

    r, leg = _single_leg_booking(outcome, rr, exit_price, entry_price, sign, risk, plan,
                                entry_index, exit_index)

    return ExitResult(
        outcome=outcome,
        runner_outcome=None,
        entry_index=entry_index,
        exit_index=exit_index,
        entry_price=entry_price,
        r_total=r,
        legs=[leg],
    )


_SINGLE_LEG_REASONS = {"win": "tp1", "loss": "stop", "scratch": "breakeven_stop"}


def _single_leg_booking(outcome: str, rr: float, exit_price: float, entry_price: float,
                        sign: int, risk: float, plan: TradePlanV2,
                        entry_index: int, exit_index: int) -> tuple[float, dict]:
    """(rounded r, the one leg) of a single-leg walk's outcome."""
    r = {"win": rr, "loss": -1.0, "scratch": 0.0}.get(outcome)
    if r is None:                    # timeout: marked to the last scanned close
        r = (exit_price - entry_price) * sign / risk
    r = round(r, 3)
    leg = {"fraction": 1.0, "exit_price": exit_price, "r": r,
           "reason": _SINGLE_LEG_REASONS.get(outcome, "timeout")}
    if outcome == "timeout" and _is_compression(plan) and _tenth_session_reached(plan, entry_index, exit_index):
        # v119: the compression short's timeout is the tenth-session paper
        # close; live prices it at the official auction, the replay at the
        # bar's Close, and says so. A walk cut short by the end of the data
        # (right-censored) keeps the plain "timeout" label and no price basis.
        leg["reason"], leg["price_basis"] = TIME_EXIT_REASON, PROXY_BASIS
    return r, leg


def _tenth_session_reached(plan: TradePlanV2, entry_index: int, exit_index: int) -> bool:
    """True only when the walk really ran to the plan's hold cap (fill session = session 1)."""
    if plan.hold_cap_bars is None:
        return True
    return exit_index == entry_index + int(plan.hold_cap_bars) - 1


def chandelier_stop(extreme_close_since_tp1: float, atr_value: float,
                    mult: float, direction: str) -> float:
    """Classic chandelier exit level for the runner leg: the extreme close
    since TP1 minus (bullish) / plus (bearish) mult x ATR."""
    if direction == "bullish":
        return extreme_close_since_tp1 - mult * atr_value
    return extreme_close_since_tp1 + mult * atr_value


def _effective_trail_mult(base_mult: float, runner_r: float) -> float:
    """R-adaptive tightening (v92 Hypothesis 1). Once the runner has banked
    TIGHTEN_TRIGGER_R since entry (measured off the same extreme_close the
    ratchet itself tracks, so this only ever tightens, never loosens on a
    pullback), trail at TIGHTEN_ATR_MULT instead of the strategy's base
    multiplier. `min()` guards a misconfigured TIGHTEN_ATR_MULT that is
    actually looser than base. Byte-identical to `base_mult` when the flag
    is off."""
    if not config.ADAPTIVE_RUNNER_TRAIL_ENABLED or runner_r < config.TIGHTEN_TRIGGER_R:
        return base_mult
    return min(base_mult, config.TIGHTEN_ATR_MULT)


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

STALL_VOLUME_MAX = 1.0   # v123 frozen: volume ratio ceiling, not gridded


def _post_entry(index, entry_index) -> bool:
    return index == index and index > entry_index        # NaN-safe


def _at_most(value, ceiling) -> bool:
    return value == value and value <= ceiling           # NaN never passes


def _pivot_cols(direction: str, swing: str) -> tuple[str, str, str, str]:
    """(last idx, last px, prior idx, prior px) for 'trail' (the protective
    swing) or 'progress' (the swing that should extend)."""
    bull_low = (direction == "bullish") == (swing == "trail")
    p = "sl" if bull_low else "sh"
    return f"{p}_i", f"{p}_px", f"{p}_prev_i", f"{p}_prev_px"


def structural_runner_stop(pivots_row, atr_value, b, direction, entry_index):
    """v123 hl_trail candidate: the latest confirmed post-entry swing low
    minus b x ATR (bearish: swing high plus). None without such a pivot.
    Row j holds only pivots confirmed by j (index <= j - PIVOT_K)."""
    idx, px, _, _ = _pivot_cols(direction, "trail")
    if not _post_entry(pivots_row[idx], entry_index):
        return None
    sign = -1 if direction == "bullish" else 1
    return float(pivots_row[px]) + sign * b * atr_value


def prev_post_entry_pivot(pivots_row, direction, entry_index):
    """The prior confirmed post-entry swing high (bearish: low), or None."""
    _, _, prev_idx, prev_px = _pivot_cols(direction, "progress")
    if not _post_entry(pivots_row[prev_idx], entry_index):
        return None
    return float(pivots_row[prev_px])


def progress_stall_fires(pivots_row, prev_post_entry_sh, features_row, c, direction,
                         entry_index, j) -> bool:
    """v123 progress_stall at bar j: a post-entry swing high confirmed AT j
    that fails to exceed the prior one, with range and volume both cooling."""
    idx, px, _, _ = _pivot_cols(direction, "progress")
    new_pivot = pivots_row[idx]
    if not (_post_entry(new_pivot, entry_index) and int(new_pivot) == j - PIVOT_K):
        return False
    if prev_post_entry_sh is None:
        return False
    high = float(pivots_row[px])
    failed = high <= prev_post_entry_sh if direction == "bullish" else high >= prev_post_entry_sh
    return bool(failed and _at_most(features_row["range_trend_10_50"], c)
                and _at_most(features_row["vol_trend_10_50"], STALL_VOLUME_MAX))


def runner_structure_step(frame, j, *, entry_index, direction, runner_stop, atr_value):
    """One completed runner bar under RUNNER_STRUCTURE_EXIT, shared by the
    replay walk and plan_manager: (stop for bar j+1, stall fired at j)."""
    mode, row = config.RUNNER_STRUCTURE_EXIT, frame.iloc[j]
    if mode == "hl_trail":
        cand = structural_runner_stop(row, atr_value, config.RUNNER_HL_TRAIL_ATR_BUFFER,
                                      direction, entry_index)
        if cand is None:
            return runner_stop, False
        return (max(runner_stop, cand) if direction == "bullish" else min(runner_stop, cand)), False
    if mode == "progress_stall":
        prev = prev_post_entry_pivot(row, direction, entry_index)
        return runner_stop, progress_stall_fires(row, prev, row, config.RUNNER_STALL_RANGE_MAX,
                                                 direction, entry_index, j)
    return runner_stop, False


@dataclass(frozen=True)
class _WalkCtx:
    high: object
    low: object
    close: object
    entry_index: int
    entry_price: float
    plan: TradePlanV2
    is_bull: bool
    sign: int
    risk: float
    end: int
    open_: object


def _no_trade(entry_index, entry_price) -> ExitResult:
    return ExitResult(outcome="no_trade", runner_outcome=None, entry_index=entry_index,
                      exit_index=None, entry_price=entry_price, r_total=0.0, legs=[])


def _full_leg(ctx, outcome, j, price, r, reason) -> ExitResult:
    return ExitResult(outcome=outcome, runner_outcome=None, entry_index=ctx.entry_index,
                      exit_index=j, entry_price=ctx.entry_price, r_total=r,
                      legs=[{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])


def _pre_tp1_touches(ctx, j, cur_stop, be_trigger):
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if ctx.is_bull:
        return lo <= cur_stop, hi >= ctx.plan.tp1, hi >= be_trigger
    return hi >= cur_stop, lo <= ctx.plan.tp1, lo <= be_trigger


def _stall_exit(ctx, j) -> ExitResult | None:
    """Task 12 stall exit (pre-TP1); stop/target already won any same-bar tie."""
    plan = ctx.plan
    if not (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
            and (j - ctx.entry_index) > plan.stall_exit_day):
        return None
    current_r = (float(ctx.close[j]) - ctx.entry_price) * ctx.sign / ctx.risk
    if not current_r < 0.5:
        return None
    r = round(current_r, 3)
    return _full_leg(ctx, "loss" if r < 0 else "scratch", j, float(ctx.close[j]), r, "stall_exit")


def _pre_tp1_phase(ctx) -> ExitResult | int:
    """Phase 1, identical to the single-leg walk: a terminal ExitResult, or the TP1 bar."""
    plan, stop_moved = ctx.plan, False
    target_dist = abs(plan.tp1 - ctx.entry_price)
    be_trigger = ctx.entry_price + ctx.sign * plan.breakeven_trigger_fraction * target_dist
    for j in range(ctx.entry_index + 1, ctx.end + 1):
        cur_stop = ctx.entry_price if stop_moved else plan.stop_loss
        hit_stop, hit_target, reached_trigger = _pre_tp1_touches(ctx, j, cur_stop, be_trigger)
        if hit_stop:  # conservative: stop first, exactly as single-leg
            return _full_leg(ctx, "scratch" if stop_moved else "loss", j, cur_stop,
                             round(0.0 if stop_moved else -1.0, 3),
                             "breakeven_stop" if stop_moved else "stop")
        if hit_target:
            return j
        early = (_acceptance_result(plan, j, float(ctx.close[j]), ctx.entry_index,
                                    ctx.entry_price, ctx.sign, ctx.risk)
                 or _stall_exit(ctx, j))     # v129: acceptance before stall
        if early is not None:
            return early
        if reached_trigger and not stop_moved:
            stop_moved = True
    exit_price = float(ctx.close[ctx.end])   # timeout before TP1
    return _full_leg(ctx, "timeout", ctx.end, exit_price,
                     round((exit_price - ctx.entry_price) * ctx.sign / ctx.risk, 3), "timeout")


def _runner_bar_exit(ctx, j, runner_stop, floor):
    """Runner stop first, then TP2; the stop checked is the one set BEFORE bar j."""
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if (lo <= runner_stop) if ctx.is_bull else (hi >= runner_stop):
        # v39: "runner_be" means "closed at its initial post-TP1 floor"; the
        # string is deliberately unchanged (~30 files pattern-match it).
        return runner_stop, j, ("runner_be" if runner_stop == floor else "runner_trail")
    tp2 = ctx.plan.tp2
    if tp2 is not None and ((hi >= tp2) if ctx.is_bull else (lo <= tp2)):
        return tp2, j, "runner_tp2"
    return None


def _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series) -> float:
    """Ratchet for the NEXT bar from THIS bar's close only -- no intrabar lookahead."""
    atr_val = _safe_atr_value(ctx.entry_price, float(atr_series.iloc[j]))
    runner_r = (extreme_close - ctx.entry_price) * ctx.sign / ctx.risk
    mult = _effective_trail_mult(ctx.plan.trail_atr_mult, runner_r)
    trail = chandelier_stop(extreme_close, atr_val, mult, ctx.plan.direction)
    return max(runner_stop, trail) if ctx.is_bull else min(runner_stop, trail)


def _runner_timeout(ctx, checked_stop) -> float:
    """Clamp to the level actually checked against the last bar walked."""
    exit_px = float(ctx.close[ctx.end])
    return max(exit_px, checked_stop) if ctx.is_bull else min(exit_px, checked_stop)


def _runner_phase(df, ctx, tp1_index, trace=None):
    """Phase 2: (exit price, exit index, runner reason) for the post-TP1 leg.
    v123: a structure rule (RUNNER_STRUCTURE_EXIT) updates after the chandelier,
    from this bar's close, effective next bar; a stall exits at the next open."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        # v129: the TP1 bar itself closed through the threshold -- TP1 banked
        # first (stop -> target -> acceptance), the remainder exits at that
        # close. Later runner bars need no check: the runner stop sits on the
        # profit side of entry, the threshold on the loss side.
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit"
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall"
        checked_stop = runner_stop
        hit = _runner_bar_exit(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop, atr_series)
        if trace is not None:
            trace.append((j, runner_stop))
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout"


def _structure_update(ctx, frame, j, runner_stop, atr_series):
    """runner_structure_step for bar j; a stall on the last walked bar is dropped
    so the timeout handles it (no bar j+1 inside the holding window)."""
    atr_val = _safe_atr_value(ctx.entry_price, float(atr_series.iloc[j]))
    stop, fires = runner_structure_step(frame, j, entry_index=ctx.entry_index,
                                        direction=ctx.plan.direction,
                                        runner_stop=runner_stop, atr_value=atr_val)
    return stop, fires and j < ctx.end


def _runner_result(ctx, runner) -> ExitResult:
    runner_exit, exit_index, reason = runner
    plan = ctx.plan
    rr = abs(plan.tp1 - ctx.entry_price) / ctx.risk
    frac1 = plan.tp1_fraction
    frac2 = 1.0 - frac1
    leg1 = {"fraction": frac1, "exit_price": plan.tp1, "r": round(rr, 3), "reason": "tp1"}
    r2 = round((runner_exit - ctx.entry_price) * ctx.sign / ctx.risk, 3)
    leg2 = {"fraction": frac2, "exit_price": runner_exit, "r": r2, "reason": reason}
    return ExitResult(outcome="win", runner_outcome=reason, entry_index=ctx.entry_index,
                      exit_index=exit_index, entry_price=ctx.entry_price,
                      r_total=round(frac1 * rr + frac2 * r2, 3), legs=[leg1, leg2])


def _scale_out_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
    *, trace=None,
) -> ExitResult:
    """Hybrid scale-out walk (spec Sec5). Phase 1 (pre-TP1) is byte-identical
    to _single_leg_exit_walk when the stall-exit flag is off; a stop/scratch/
    timeout before TP1 returns the same single full-fraction leg. (Task 12:
    with STALL_EXIT_ENABLED on and plan.stall_exit_day set, a plan still open
    and below +0.5R past that day closes early instead -- stop/target checks
    still win any same-bar tie.) TP1 touch banks tp1_fraction at tp1 and
    hands the rest to the runner: stop starts at the v39 runner floor
    (entry + 2/3 x (tp1 - entry), see runner_floor) and ratchets
    toward profit via a chandelier trail (Task 26) as the runner rides, with
    an optional TP2 target (Task 25). Task 27 still owes runner-timeout
    test coverage."""
    risk = abs(entry_price - plan.stop_loss)
    if risk <= 0:
        return _no_trade(entry_index, entry_price)
    is_bull = plan.direction == "bullish"
    ctx = _WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, entry_index,
                   entry_price, plan, is_bull, 1 if is_bull else -1, risk,
                   min(entry_index + max_holding_days, len(df) - 1), df["Open"].values)
    pre = _pre_tp1_phase(ctx)
    if isinstance(pre, ExitResult):
        return pre
    return _runner_result(ctx, _runner_phase(df, ctx, pre, trace))


def _walk_for(plan: TradePlanV2, scale_out: bool):
    """The exit walk for this plan. A whole-position target (tp1_fraction 1.0,
    v113 Part A) has no runner leg, so it always takes the single-leg walk --
    the scale-out walk's pre-TP1 phase, then out at TP1."""
    if scale_out and plan.tp1_fraction < 1.0:
        return _scale_out_exit_walk
    return _single_leg_exit_walk


def _fill_bar_exit(df, j: int, entry_price: float, plan: TradePlanV2) -> ExitResult | None:
    """v113 amendment 3: the bar that fills a limit can also reach the stop.
    Stop first, as everywhere in this engine. A fill at or through the stop (the
    bar gapped past it) exits flat at the fill -- a scratch, 0R, because the
    bracket stop triggers at once; otherwise a stop touch on the fill bar is a
    full loss at the stop. None when the fill bar is clean."""
    if at_or_beyond_stop(plan, entry_price):
        return ExitResult(outcome="scratch", runner_outcome=None, entry_index=j, exit_index=j,
                          entry_price=entry_price, r_total=0.0,
                          legs=[{"fraction": 1.0, "exit_price": entry_price, "r": 0.0,
                                 "reason": "gap_through_stop"}])
    if stop_touched(plan, float(df["High"].values[j]), float(df["Low"].values[j])):
        return ExitResult(outcome="loss", runner_outcome=None, entry_index=j, exit_index=j,
                          entry_price=entry_price, r_total=-1.0,
                          legs=[{"fraction": 1.0, "exit_price": plan.stop_loss, "r": -1.0,
                                 "reason": "stop"}])
    return None


def _is_compression(plan: TradePlanV2) -> bool:
    """The compression short alone gets the live-parity fill policy; every other
    strategy's stop-entry replay stays exactly as it was."""
    return plan.strategy == COMPRESSION_SHORT


def _compression_fill(df, j: int, entry_price: float, plan: TradePlanV2,
                      scale_out: bool, max_holding_days: int) -> ExitResult:
    """Fill policy for the compression short, mirroring PlanManager._step_pending:
    a gap fill whose planned loss exceeds the stop ceiling is cancelled (an
    excluded not_triggered row, never scored), otherwise the fill bar is checked
    against the stop (stop-first) before the normal exit walk."""
    if planned_loss_pct(entry_price, plan.stop_loss) > plan_stop_ceiling(plan):
        return _not_triggered("risk_cap")
    early = _fill_bar_exit(df, j, entry_price, plan)
    if early is not None:
        return early
    return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)


def _limit_entry_exit(df, signal_index: int, plan: TradePlanV2, scale_out: bool,
                      max_holding_days: int) -> ExitResult:
    """v113 §3: a resting limit at trigger_price, live for the plan's
    expiry_bars bars after the signal bar (Part A: 1, so bar t+1 only). Fills on
    the first bar that trades through it, at limit_fill_price; the fill bar is
    checked against the stop (_fill_bar_exit), then the normal exit walk runs
    from the fill bar, so the time stop counts bars after ENTRY."""
    high, low, open_ = df["High"].values, df["Low"].values, df["Open"].values
    last = min(signal_index + plan.expiry_bars, len(df) - 1)
    for j in range(signal_index + 1, last + 1):
        if not limit_hit(plan, float(high[j]), float(low[j])):
            continue
        entry_price = limit_fill_price(plan, float(open_[j]))
        early = _fill_bar_exit(df, j, entry_price, plan)
        if early is not None:
            return early
        return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)
    return _not_triggered()


def _hold_cap_bars(plan: TradePlanV2, max_holding_days: int) -> int:
    """The walkers' scan length after the plan's hold cap. They scan
    entry_index+1 .. entry_index+N; the compression short's fill session is
    session 1, so its cap of N sessions ends at entry_index + N - 1 (live: the
    tenth session). Every other strategy keeps entry_index + N."""
    hold_cap = getattr(plan, "hold_cap_bars", None)
    if hold_cap is None:
        return max_holding_days
    cap = int(hold_cap) - 1 if _is_compression(plan) else int(hold_cap)
    return min(max_holding_days, cap)


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

    ``limit`` entries (v113) are resting limits: see _limit_entry_exit. A plan
    whose tp1_fraction is 1.0 always takes the single-leg walk.
    """
    # Resolved eagerly per the interface contract -- both the single-leg
    # (Task 21) and scale-out (Task 24+) exit walks use it to bound the
    # timeout scan.
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]

    max_holding_days = _hold_cap_bars(plan, max_holding_days)

    if plan.entry_type == "limit":
        return _limit_entry_exit(df, signal_index, plan, scale_out, max_holding_days)

    if plan.entry_type == "market":
        entry_index = signal_index
        entry_price = float(df["Close"].values[signal_index])
        return _walk_for(plan, scale_out)(df, entry_index, entry_price, plan, max_holding_days)

    # stop_entry: scan signal_index+1 .. signal_index+plan.expiry_bars for a
    # trigger touch, watching for pre-fill invalidation along the way. df rows
    # are sessions, so a holiday between signal and next bar costs nothing.
    high = df["High"].values
    low = df["Low"].values
    open_ = df["Open"].values
    close = df["Close"].values
    n = len(df)
    strict = _is_compression(plan)

    j = signal_index + 1
    while j < n:
        bars_since_created = j - signal_index
        if pending_expired(plan, bars_since_created):
            break
        if trigger_hit(plan, float(high[j]), float(low[j])):
            entry_price = fill_price(plan, float(open_[j]))
            if strict:
                return _compression_fill(df, j, entry_price, plan, scale_out, max_holding_days)
            return _walk_for(plan, scale_out)(df, j, entry_price, plan, max_holding_days)
        if pending_invalidated(plan, float(close[j])):
            return _not_triggered("invalidated" if strict else None)
        j += 1

    return _not_triggered("expired" if strict else None)

