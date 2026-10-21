"""v180: the next-open fill and its gap-aware single-leg walk (Turtle Soup).

The v1 market entry fills at the signal bar's close. A Turtle Soup alert is
entered as orders placed before the open, so its replay fills at ``Open[t+1]``,
the way live would:

- an open at or below the stop cancels the plan (``OPEN_THROUGH_STOP``);
- a stop farther than the plan's ceiling from the fill drops the plan
  (``RISK_CAP``) -- the stop is never squeezed to fit;
- a bar that opens beyond the stop or the target fills at that open
  (``plan_manager``'s live gap convention).

This is the v1 path only; ``exit_sim_v2`` is untouched.
"""
from __future__ import annotations

from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.risk_limits import planned_loss_pct
from .exit_sim import ExitResult, _acceptance_result, _not_triggered, _tenth_session_reached
from .plan_manager import gap_stop_fill, gap_target_fill
from .stop_scope import plan_stop_ceiling
from .time_exit import PROXY_BASIS, TIME_EXIT_REASON

#: Strategies whose replay fills at the next bar's open instead of the signal close.
NEXT_OPEN_STRATEGIES = frozenset({TURTLE_SOUP})

OPEN_THROUGH_STOP = "open_through_stop"
RISK_CAP = "risk_cap"
GAP_STOP_REASON = "gap_stop"
GAP_TARGET_REASON = "gap_target"


def uses_next_open_fill(plan) -> bool:
    return getattr(plan, "strategy", None) in NEXT_OPEN_STRATEGIES


def next_open_exit(df, signal_index: int, plan, max_holding_days: int) -> ExitResult:
    """Fill at Open[signal_index + 1], then walk one whole-position leg.

    ``max_holding_days`` is the walk length after the fill bar, as
    ``simulate_exit`` passes it (``_hold_cap_bars`` already applied)."""
    if plan.direction != "bullish":
        raise ValueError("next-open fill is long-only (v180 Turtle Soup)")
    j = signal_index + 1
    if j >= len(df):
        return _not_triggered()
    fill = float(df["Open"].values[j])
    if fill <= plan.stop_loss:
        return _not_triggered(OPEN_THROUGH_STOP)
    if planned_loss_pct(fill, plan.stop_loss) > plan_stop_ceiling(plan):
        return _not_triggered(RISK_CAP)
    return gap_aware_single_leg_walk(df, j, fill, plan, max_holding_days)


def _bar_exit(plan, bar_open, bar_high, bar_low, entry_price):
    """(outcome, exit_price, reason) for the first exit this bar makes, or None.
    Order: open through the stop, open through the target, low touches the stop
    (stop first, as everywhere in this engine), high touches the target."""
    if bar_open <= plan.stop_loss:
        return "loss", gap_stop_fill(bar_open, plan.stop_loss, "bullish"), GAP_STOP_REASON
    if bar_open >= plan.tp1:
        price = gap_target_fill(bar_open, plan.tp1, "bullish")
        return ("win" if price > entry_price else "scratch"), price, GAP_TARGET_REASON
    if bar_low <= plan.stop_loss:
        return "loss", plan.stop_loss, "stop"
    if bar_high >= plan.tp1:
        return "win", plan.tp1, "tp1"
    return None


def _booked(hit, entry_index: int, j: int, entry_price: float, risk: float) -> ExitResult:
    outcome, price, reason = hit
    r = round((price - entry_price) / risk, 3)
    return ExitResult(outcome, None, entry_index, j, entry_price, r,
                      [{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])


def _time_exit(plan, entry_index: int, end: int, entry_price: float, close_end: float,
               risk: float) -> ExitResult:
    """Timeout at the last scanned close. A walk that reached the hold cap is the
    tenth-session paper close (proxy-priced); a right-censored one stays plain."""
    r = round((close_end - entry_price) / risk, 3)
    leg = {"fraction": 1.0, "exit_price": close_end, "r": r, "reason": "timeout"}
    if _tenth_session_reached(plan, entry_index, end):
        leg["reason"], leg["price_basis"] = TIME_EXIT_REASON, PROXY_BASIS
    return ExitResult("timeout", None, entry_index, end, entry_price, r, [leg])


def gap_aware_single_leg_walk(df, entry_index: int, entry_price: float, plan,
                              max_holding_days: int) -> ExitResult:
    """Long-only whole-position walk from the fill bar (session 1) through
    entry_index + max_holding_days, with gap fills at the open."""
    risk = entry_price - plan.stop_loss
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None, entry_index=entry_index,
                          exit_index=None, entry_price=entry_price, r_total=0.0, legs=[])
    opens, highs, lows, closes = (df[col].values for col in ("Open", "High", "Low", "Close"))
    end = min(entry_index + max_holding_days, len(df) - 1)
    for j in range(entry_index, end + 1):          # the fill bar is session 1 and is walked
        hit = _bar_exit(plan, float(opens[j]), float(highs[j]), float(lows[j]), entry_price)
        if hit is not None:
            return _booked(hit, entry_index, j, entry_price, risk)
        accepted = _acceptance_result(plan, j, float(closes[j]), entry_index, entry_price, 1, risk)
        if accepted is not None:                    # v129, after stop and target
            return accepted
    return _time_exit(plan, entry_index, end, entry_price, float(closes[end]), risk)
