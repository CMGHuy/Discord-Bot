"""v192: the replay's next-open market fill, both measurement arms.

A market plan built under MARKET_ENTRY_NEXT_OPEN (gap_reclaim.waits_for_open)
fills at Open[t+1], or cancels on an open at or through the stop or a stop past
the plan's ceiling from the open (gap_reclaim.decide_at_open, the same function
the live PlanManager calls). The fill bar is checked before the plan's normal
exit walk (``next_open_fill_bar``): an open beyond TP1 first (v180's gap-target
convention), then the stop (stop-first), then TP1 -- banked whole, or as the
scale-out TP1 leg with the runner continuing from the fill bar. With the gap
veto armed (a stored reclaim_level) the plan rests at E for that session instead
(``_reclaim_exit``: one tick through E fills, else ``gap_no_reclaim``).

Every next-open decision is reported to the callbacks registered with
``observing`` -- the census (V192-15) reads them; nothing else does. v1 only;
exit_sim_v2 is untouched.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from . import exit_sim
from . import gap_reclaim
from .exit_sim import ExitResult
from .lifecycle import stop_touched
from .next_open_entry import GAP_TARGET_REASON
from .plan_manager import gap_target_fill

NO_BAR = "no_bar"


@dataclass(frozen=True)
class NextOpenDecision:
    ticker: str
    strategy: str
    horizon_key: str
    source: str
    direction: str
    signal_date: str
    entry: float
    stop: float
    open_price: float | None
    atr: float | None
    reclaim_level: float | None
    gap_atr: float | None
    decision: str            # gap_reclaim.FILL_OPEN | RECLAIM_WAIT | OPEN_THROUGH_STOP | RISK_CAP | "no_bar"
    reclaimed: bool
    ambiguous: bool
    fill_price: float | None


_OBSERVERS: list = []


@contextlib.contextmanager
def observing(callback):
    """Call ``callback(NextOpenDecision)`` for every next-open market plan simulated inside."""
    _OBSERVERS.append(callback)
    try:
        yield
    finally:
        _OBSERVERS.remove(callback)


def _emit(decision: NextOpenDecision) -> None:
    for callback in tuple(_OBSERVERS):
        callback(decision)


def _gap_atr(plan, open_price: float | None) -> float | None:
    atr = getattr(plan, "reclaim_atr", None)
    if open_price is None or not atr:
        return None
    return gap_reclaim.gap_toward_stop(plan, open_price) / atr


def _decision(plan, df, signal_index: int, open_price, decision: str, *, fill_price=None,
              reclaimed: bool = False, ambiguous: bool = False) -> NextOpenDecision:
    return NextOpenDecision(
        ticker=plan.ticker, strategy=plan.strategy, horizon_key=plan.horizon_key,
        source=plan.source, direction=plan.direction,
        signal_date=str(df.index[signal_index].date()), entry=plan.trigger_price,
        stop=plan.stop_loss, open_price=open_price, atr=getattr(plan, "reclaim_atr", None),
        reclaim_level=getattr(plan, "reclaim_level", None),
        gap_atr=_gap_atr(plan, open_price), decision=decision, reclaimed=reclaimed,
        ambiguous=ambiguous, fill_price=fill_price)


def _open_beyond_tp1(plan, bar_open: float) -> bool:
    return bar_open >= plan.tp1 if plan.direction == "bullish" else bar_open <= plan.tp1


def _tp1_touched(plan, high: float, low: float) -> bool:
    return high >= plan.tp1 if plan.direction == "bullish" else low <= plan.tp1


def _one_leg(j: int, fill: float, outcome: str, price: float, r: float, reason: str) -> ExitResult:
    return ExitResult(outcome, None, j, j, fill, r,
                      [{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])


def _gap_target_exit(df, j: int, fill: float, plan, sign: int, risk: float) -> ExitResult:
    price = gap_target_fill(float(df["Open"].values[j]), plan.tp1, plan.direction)
    r = round((price - fill) * sign / risk, 3)
    return _one_leg(j, fill, "win" if r > 0 else "scratch", price, r, GAP_TARGET_REASON)


def _tp1_exit(df, j: int, fill: float, plan, scale_out: bool, max_holding_days: int,
              sign: int, risk: float) -> ExitResult:
    if scale_out and plan.tp1_fraction < 1.0:      # _walk_for's scale-out rule
        ctx = exit_sim._WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, j,
                                fill, plan, sign == 1, sign, risk,
                                min(j + max_holding_days, len(df) - 1), df["Open"].values)
        return exit_sim._runner_result(ctx, exit_sim._runner_phase(df, ctx, j))
    rr = abs(plan.tp1 - fill) / risk
    r, leg = exit_sim._single_leg_booking("win", rr, plan.tp1, fill, sign, risk, plan, j, j)
    return ExitResult("win", None, j, j, fill, r, [leg])


def next_open_fill_bar(df, j: int, fill: float, plan, scale_out: bool,
                       max_holding_days: int) -> ExitResult | None:
    """The fill bar's own exit, or None when it is clean (the walk then runs from j).
    Order: open beyond TP1 (v180 gap target), the stop (stop-first, -1R), TP1."""
    risk = abs(fill - plan.stop_loss)
    if risk <= 0:
        return None                                 # the walker books no_trade
    sign = 1 if plan.direction == "bullish" else -1
    high, low = float(df["High"].values[j]), float(df["Low"].values[j])
    if _open_beyond_tp1(plan, float(df["Open"].values[j])):
        return _gap_target_exit(df, j, fill, plan, sign, risk)
    if stop_touched(plan, high, low):
        return _one_leg(j, fill, "loss", plan.stop_loss, -1.0, "stop")
    if _tp1_touched(plan, high, low):
        return _tp1_exit(df, j, fill, plan, scale_out, max_holding_days, sign, risk)
    return None


def _filled(df, j: int, fill: float, plan, scale_out: bool, max_holding_days: int) -> ExitResult:
    early = next_open_fill_bar(df, j, fill, plan, scale_out, max_holding_days)
    if early is not None:
        return early
    return exit_sim._walk_for(plan, scale_out)(df, j, fill, plan, max_holding_days)


def _reclaim_exit(df, signal_index: int, open_price: float, plan, scale_out: bool,
                  max_holding_days: int) -> ExitResult:
    """The armed veto: the open sat at or beyond X toward the stop, so the plan rests
    as a DAY stop order at E for session t+1 only. One tick through E fills at
    reclaim_fill_price (E +/- one adverse tick, the stop order's slippage) and walks
    exactly as an open fill; no reclaim cancels gap_no_reclaim. A reclaim bar that
    also reaches the stop is ambiguous: filled, then stopped at -1R by
    next_open_fill_bar's stop-first rule."""
    j = signal_index + 1
    high, low = float(df["High"].values[j]), float(df["Low"].values[j])
    if not gap_reclaim.reclaim_touched(plan, high, low):
        _emit(_decision(plan, df, signal_index, open_price, gap_reclaim.RECLAIM_WAIT))
        return exit_sim._not_triggered(gap_reclaim.GAP_NO_RECLAIM)
    fill = gap_reclaim.reclaim_fill_price(plan)
    _emit(_decision(plan, df, signal_index, open_price, gap_reclaim.RECLAIM_WAIT,
                    fill_price=fill, reclaimed=True, ambiguous=stop_touched(plan, high, low)))
    return _filled(df, j, fill, plan, scale_out, max_holding_days)


def next_open_market_exit(df, signal_index: int, plan, scale_out: bool,
                          max_holding_days: int) -> ExitResult:
    """A waiting market plan: decide at Open[signal_index + 1], then fill and walk.
    ``max_holding_days`` is the walk length after the fill bar, as simulate_exit
    passes it (_hold_cap_bars already applied)."""
    j = signal_index + 1
    if j >= len(df):
        _emit(_decision(plan, df, signal_index, None, NO_BAR))
        return exit_sim._not_triggered()
    open_price = float(df["Open"].values[j])
    decision = gap_reclaim.decide_at_open(plan, open_price)
    if decision == gap_reclaim.RECLAIM_WAIT:
        return _reclaim_exit(df, signal_index, open_price, plan, scale_out, max_holding_days)
    if decision != gap_reclaim.FILL_OPEN:
        _emit(_decision(plan, df, signal_index, open_price, decision))
        return exit_sim._not_triggered(decision)
    _emit(_decision(plan, df, signal_index, open_price, decision, fill_price=open_price))
    return _filled(df, j, open_price, plan, scale_out, max_holding_days)
