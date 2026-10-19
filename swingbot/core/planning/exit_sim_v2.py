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
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.risk_limits import planned_loss_pct
from .exit_sim import (ExitResult, _chandelier_ratchet, _giveback_extreme, _giveback_ratchet,
                       _hold_cap_bars, _is_compression, _limit_unfilled, _no_trade,
                       _not_triggered, _runner_timeout, _stop_source, _structure_update,
                       _tenth_session_reached, acceptance_exit, runner_floor,
                       runner_structure_frame)
from .lifecycle import limit_cancelled, pending_expired, pending_invalidated
from .plan_types import TradePlanV2
from .stop_scope import plan_stop_ceiling
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON

#: A market entry whose next open is at or beyond the stop: cancelled, never counted.
GAP_CANCEL = "gap_through_stop"
#: A limit or stop entry filled at or beyond the stop: a 0R scratch at the fill
#: (v1's leg reason for it is "gap_through_stop"; v2 keeps that string for the cancel).
ENTRY_GAP_SCRATCH = "entry_gap_scratch"


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
            runner_outcome: str | None = None,
            runner_stop_source: str | None = None) -> ExitResult:
    """The trade's ExitResult, its raw legs booked once through costs.book.
    v176: ``runner_stop_source`` rides on the result, never on a leg."""
    r_total, booked = costs.book(ctx.costs, direction=ctx.plan.direction,
                                 entry_price=ctx.entry_price, stop_loss=ctx.plan.stop_loss,
                                 legs=legs)
    for raw, leg in zip(legs, booked):
        if "price_basis" in raw:
            leg["price_basis"] = raw["price_basis"]
    return ExitResult(outcome=outcome, runner_outcome=runner_outcome,
                      entry_index=ctx.entry_index, exit_index=exit_index,
                      entry_price=ctx.entry_price, r_total=r_total, legs=booked,
                      runner_stop_source=runner_stop_source)


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


def _runner_bar_v2(ctx, j: int, runner_stop: float, floor: float, gb_extreme=None):
    """Runner stop first, then TP2, each filled through fills.exit_fill:
    (price, index, reason, kind, stop_source) or None; stop_source is None for TP2."""
    hi, lo, op = float(ctx.high[j]), float(ctx.low[j]), float(ctx.open_[j])
    direction = ctx.plan.direction
    if fills.stop_touched(hi, lo, runner_stop, direction):
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return (fills.exit_fill(ctx.fills, "stop", runner_stop, op, direction), j, reason,
                "stop", _stop_source(ctx, runner_stop, floor, gb_extreme))
    tp2 = ctx.plan.tp2
    if tp2 is not None and fills.target_touched(hi, lo, tp2, direction):
        return (fills.exit_fill(ctx.fills, "target", tp2, op, direction), j, "runner_tp2",
                "target", None)
    return None


def _runner_v2(df, ctx, tp1_index: int):
    """exit_sim._runner_phase on fills.py's compares: (price, index, reason,
    kind, stop_source) of the post-TP1 leg. The trailing stop set from bar j's
    close is first checked on bar j + 1; v176's give-back ratchets after the
    chandelier and before the structure rule, as in exit_sim."""
    if acceptance_exit(ctx.plan, float(ctx.close[tp1_index])):
        return float(ctx.close[tp1_index]), tp1_index, "acceptance_exit", "close", None
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    gb_extreme = _giveback_extreme(ctx, tp1_index, None)
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close", None
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor, gb_extreme)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        gb_extreme = _giveback_extreme(ctx, j, gb_extreme)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        runner_stop = _giveback_ratchet(ctx, gb_extreme, runner_stop)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close", None


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
    price, exit_index, reason, kind, stop_source = _runner_v2(df, ctx, pre)
    legs = [_leg(plan.tp1_fraction, tp1_fill, "tp1", "target"),
            _leg(1.0 - plan.tp1_fraction, price, reason, kind)]
    return _booked(ctx, "win", exit_index, legs, runner_outcome=reason,
                   runner_stop_source=stop_source)


def _entry_gap_scratch(j: int, fill: float) -> ExitResult:
    """The fill sits at or through the stop, so the bracket stop fires at once:
    a flat 0R scratch at the fill (controller decision 3 keeps today's 0R). No
    cost is booked: the trade has no risk on the right side of its stop, so it
    has no R to convert costs into."""
    return ExitResult(outcome="scratch", runner_outcome=None, entry_index=j, exit_index=j,
                      entry_price=fill, r_total=0.0,
                      legs=[{"fraction": 1.0, "exit_price": fill, "r": 0.0,
                             "reason": ENTRY_GAP_SCRATCH}])


def _fill_bar_v2(df, j: int, fill: float, plan: TradePlanV2,
                 instrument: InstrumentSpec) -> ExitResult | None:
    """Every v2 fill bar is checked for the stop, never the target: the path
    after the fill is unknown, so stop first. The open came before the fill,
    so a stop reached later on the bar fills at the stop itself."""
    direction = plan.direction
    if fills.at_or_beyond_stop(fill, plan.stop_loss, direction):
        return _entry_gap_scratch(j, fill)
    if not fills.stop_touched(float(df["High"].values[j]), float(df["Low"].values[j]),
                              plan.stop_loss, direction):
        return None
    ctx = _context(df, j, fill, plan, 0, instrument, False)
    return _booked(ctx, "loss", j, [_leg(1.0, plan.stop_loss, "stop", "stop")])


def _filled(df, j: int, fill: float, plan: TradePlanV2, instrument: InstrumentSpec,
            scale_out: bool, max_holding_days: int) -> ExitResult:
    early = _fill_bar_v2(df, j, fill, plan, instrument)
    if early is not None:
        return early
    return walk_v2(df, j, fill, plan, max_holding_days, instrument, scale_out=scale_out)


def _market_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """The alert goes out after the signal close; the order fills at the next
    open. An open at or beyond the stop cancels it (GAP_CANCEL)."""
    j = signal_index + 1
    if j >= len(df):
        return _not_triggered()
    fill = fills.entry_fill(instrument.fill_model, "market", plan.direction,
                            bar_open=float(df["Open"].values[j]))
    if fills.at_or_beyond_stop(fill, plan.stop_loss, plan.direction):
        return _not_triggered(GAP_CANCEL)
    return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)


def _limit_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """exit_sim._limit_entry_exit on fills.py's touch and fill rules: the fill
    is checked first, then the v131 cancel level; unfilled rows keep v1's reasons."""
    high, low, open_ = df["High"].values, df["Low"].values, df["Open"].values
    last = min(signal_index + plan.expiry_bars, len(df) - 1)
    for j in range(signal_index + 1, last + 1):
        bar_high, bar_low = float(high[j]), float(low[j])
        if not fills.entry_touched("limit", plan.direction, bar_high, bar_low,
                                   plan.trigger_price, strict=bool(plan.limit_strict_fill)):
            if limit_cancelled(plan, bar_high, bar_low):
                return _limit_unfilled(plan, cancelled=True)
            continue
        fill = fills.entry_fill(instrument.fill_model, "limit", plan.direction,
                                bar_open=float(open_[j]), level=plan.trigger_price)
        return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)
    return _limit_unfilled(plan, cancelled=False)


def _stop_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days):
    """exit_sim's stop-entry scan on fills.py's touch and fill rules. The
    compression short keeps its risk-cap cancel on the actual fill and its
    strict not_triggered reasons."""
    high, low = df["High"].values, df["Low"].values
    open_, close = df["Open"].values, df["Close"].values
    strict = _is_compression(plan)
    for j in range(signal_index + 1, len(df)):
        if pending_expired(plan, j - signal_index):
            break
        if fills.entry_touched("stop_entry", plan.direction, float(high[j]), float(low[j]),
                               plan.trigger_price):
            fill = fills.entry_fill(instrument.fill_model, "stop_entry", plan.direction,
                                    bar_open=float(open_[j]), level=plan.trigger_price)
            if strict and planned_loss_pct(fill, plan.stop_loss) > plan_stop_ceiling(plan):
                return _not_triggered("risk_cap")
            return _filled(df, j, fill, plan, instrument, scale_out, max_holding_days)
        if pending_invalidated(plan, float(close[j])):
            return _not_triggered("invalidated" if strict else None)
    return _not_triggered("expired" if strict else None)


_ENTRIES = {"market": _market_entry_v2, "limit": _limit_entry_v2}


def simulate_exit_v2(df, signal_index: int, plan: TradePlanV2, instrument: InstrumentSpec,
                     *, scale_out: bool = False,
                     max_holding_days: int | None = None) -> ExitResult:
    """exit_sim.simulate_exit under a v2 instrument: the entry (market at the
    next open, limit, stop entry -- any other entry_type is a stop entry, as
    in v1), the fill-bar stop check, then walk_v2. Same hold-cap resolution
    as v1."""
    fills.require_supported(instrument.fill_model)
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]
    max_holding_days = _hold_cap_bars(plan, max_holding_days)
    entry = _ENTRIES.get(plan.entry_type, _stop_entry_v2)
    return entry(df, signal_index, plan, instrument, scale_out, max_holding_days)
