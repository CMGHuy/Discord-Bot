"""The v2 instrument's exit simulator (v136 spec section 2, plan v157).

``exit_sim.simulate_exit(..., instrument=spec)`` hands every non-v1 spec here,
so the v1 walk in exit_sim.py is never edited (spec rule 1). This module keeps
exit_sim's bar order and reuses its pure helpers unchanged; what differs is
that every price-vs-level comparison and every fill price comes from
``instrument/fills.py`` (gaps fill at the open, in both directions, stop
first), and every trade's r is booked once through ``instrument/costs.py``.

Legs are recorded raw -- ``{"fraction", "exit_price", "reason", "kind"}``
with ``kind`` one of ``costs.EXIT_KINDS`` -- and ``_booked`` turns them into
the usual ``ExitResult`` with net ``r``. Outcome labels follow the event (a
stop before the breakeven move is a loss, after it a scratch, a TP1 touch a
win) whatever the net r; r itself is always price-derived.
"""
from __future__ import annotations

from dataclasses import dataclass

from swingbot import config
from swingbot.core.backtesting.instrument import costs, fills
from swingbot.core.backtesting.instrument.contract import CostModel, FillModel, InstrumentSpec
from .exit_sim import (ExitResult, _chandelier_ratchet, _is_compression, _no_trade,
                       _runner_timeout, _structure_update, _tenth_session_reached,
                       acceptance_exit, runner_floor, runner_structure_frame)
from .plan_types import TradePlanV2
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON


@dataclass(frozen=True)
class _V2Ctx:
    """exit_sim._WalkCtx's fields (the reused helpers read them by name), plus
    the instrument's fill and cost models and whether this is the scale-out
    walk (pre-TP1 stall exit, runner after TP1)."""
    high: object
    low: object
    close: object
    open_: object
    entry_index: int
    entry_price: float
    plan: TradePlanV2
    is_bull: bool
    sign: int
    risk: float
    end: int
    fills: FillModel
    costs: CostModel
    stall: bool


def _context(df, entry_index: int, entry_price: float, plan: TradePlanV2,
             max_holding_days: int, instrument: InstrumentSpec, scale_out: bool) -> _V2Ctx:
    is_bull = plan.direction == "bullish"
    return _V2Ctx(high=df["High"].values, low=df["Low"].values, close=df["Close"].values,
                  open_=df["Open"].values, entry_index=entry_index,
                  entry_price=float(entry_price), plan=plan, is_bull=is_bull,
                  sign=1 if is_bull else -1, risk=abs(entry_price - plan.stop_loss),
                  end=min(entry_index + max_holding_days, len(df) - 1),
                  fills=instrument.fill_model, costs=instrument.cost_model,
                  stall=bool(scale_out and plan.tp1_fraction < 1.0))


def _leg(fraction: float, exit_price: float, reason: str, kind: str) -> dict:
    return {"fraction": fraction, "exit_price": float(exit_price), "reason": reason,
            "kind": kind}


def _booked(ctx, outcome: str, exit_index: int, legs: list[dict],
            runner_outcome: str | None = None) -> ExitResult:
    """The trade's ExitResult, its raw legs booked once through costs.book."""
    r_total, booked = costs.book(ctx.costs, direction=ctx.plan.direction,
                                 entry_price=ctx.entry_price, stop_loss=ctx.plan.stop_loss,
                                 legs=legs)
    for raw, leg in zip(legs, booked):
        if "price_basis" in raw:
            leg["price_basis"] = raw["price_basis"]
    return ExitResult(outcome=outcome, runner_outcome=runner_outcome,
                      entry_index=ctx.entry_index, exit_index=exit_index,
                      entry_price=ctx.entry_price, r_total=r_total, legs=booked)


def _gross_r(ctx, price: float) -> float:
    return (price - ctx.entry_price) * ctx.sign / ctx.risk


def _stall_due(ctx, j: int) -> bool:
    """exit_sim._stall_exit's condition: flag on, past the plan's stall day,
    and still short of +0.5R (gross) at this close."""
    plan = ctx.plan
    if not (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
            and (j - ctx.entry_index) > plan.stall_exit_day):
        return False
    return _gross_r(ctx, float(ctx.close[j])) < 0.5


def _close_exit(ctx, j: int) -> ExitResult | None:
    """A full-position exit at close[j]: acceptance first, then (scale-out
    walk only) the stall exit -- after stop and target, as in v1."""
    close_j = float(ctx.close[j])
    if acceptance_exit(ctx.plan, close_j):
        reason = "acceptance_exit"
    elif ctx.stall and _stall_due(ctx, j):
        reason = "stall_exit"
    else:
        return None
    outcome = "loss" if round(_gross_r(ctx, close_j), 3) < 0 else "scratch"
    return _booked(ctx, outcome, j, [_leg(1.0, close_j, reason, "close")])


def _stop_out(ctx, j: int, cur_stop: float, stop_moved: bool) -> ExitResult:
    price = fills.exit_fill(ctx.fills, "stop", cur_stop, float(ctx.open_[j]),
                            ctx.plan.direction)
    outcome, reason = ("scratch", "breakeven_stop") if stop_moved else ("loss", "stop")
    return _booked(ctx, outcome, j, [_leg(1.0, price, reason, "stop")])


def _timeout(ctx) -> ExitResult:
    """Out at the last walked close. The compression short's single-leg
    timeout keeps v119's tenth-session label and price basis."""
    leg = _leg(1.0, float(ctx.close[ctx.end]), "timeout", "close")
    if (not ctx.stall and _is_compression(ctx.plan)
            and _tenth_session_reached(ctx.plan, ctx.entry_index, ctx.end)):
        leg["reason"], leg["price_basis"] = TIME_EXIT_REASON, PROXY_BASIS
    return _booked(ctx, "timeout", ctx.end, [leg])


def _pre_tp1_v2(ctx) -> ExitResult | int:
    """exit_sim's pre-TP1 bar order (stop, TP1, acceptance, stall, then the
    breakeven move, effective next bar) on fills.py's compares: a terminal
    ExitResult, or the TP1 bar's index."""
    plan, direction, stop_moved = ctx.plan, ctx.plan.direction, False
    be_trigger = ctx.entry_price + ctx.sign * plan.breakeven_trigger_fraction * abs(
        plan.tp1 - ctx.entry_price)
    for j in range(ctx.entry_index + 1, ctx.end + 1):
        cur_stop = ctx.entry_price if stop_moved else plan.stop_loss
        hi, lo = float(ctx.high[j]), float(ctx.low[j])
        if fills.stop_touched(hi, lo, cur_stop, direction):
            return _stop_out(ctx, j, cur_stop, stop_moved)
        if fills.target_touched(hi, lo, plan.tp1, direction):
            return j
        early = _close_exit(ctx, j)
        if early is not None:
            return early
        if not stop_moved and fills.target_touched(hi, lo, be_trigger, direction):
            stop_moved = True
    return _timeout(ctx)


def _runner_bar_v2(ctx, j: int, runner_stop: float, floor: float):
    """Runner stop first, then TP2, each filled through fills.exit_fill:
    (price, index, reason, kind) or None."""
    hi, lo, op = float(ctx.high[j]), float(ctx.low[j]), float(ctx.open_[j])
    direction = ctx.plan.direction
    if fills.stop_touched(hi, lo, runner_stop, direction):
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return fills.exit_fill(ctx.fills, "stop", runner_stop, op, direction), j, reason, "stop"
    tp2 = ctx.plan.tp2
    if tp2 is not None and fills.target_touched(hi, lo, tp2, direction):
        return fills.exit_fill(ctx.fills, "target", tp2, op, direction), j, "runner_tp2", "target"
    return None


def _runner_v2(df, ctx, tp1_index: int):
    """exit_sim._runner_phase on fills.py's compares: (price, index, reason,
    kind) of the post-TP1 leg. The trailing stop set from bar j's close is
    first checked on bar j + 1."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", "close"
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close"
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close"


def walk_v2(df, entry_index: int, entry_price: float, plan: TradePlanV2,
            max_holding_days: int, instrument: InstrumentSpec, *,
            scale_out: bool) -> ExitResult:
    """The v2 exit walk from a filled entry: bars entry_index + 1 .. entry_index
    + max_holding_days (capped at the data). Single-leg unless `scale_out` and
    the plan keeps a runner (tp1_fraction < 1.0), as exit_sim._walk_for."""
    if abs(entry_price - plan.stop_loss) <= 0:
        return _no_trade(entry_index, entry_price)
    ctx = _context(df, entry_index, entry_price, plan, max_holding_days, instrument, scale_out)
    pre = _pre_tp1_v2(ctx)
    if isinstance(pre, ExitResult):
        return pre
    tp1_fill = fills.exit_fill(ctx.fills, "target", plan.tp1, float(ctx.open_[pre]),
                               plan.direction)
    if not ctx.stall:
        return _booked(ctx, "win", pre, [_leg(1.0, tp1_fill, "tp1", "target")])
    price, exit_index, reason, kind = _runner_v2(df, ctx, pre)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason)
