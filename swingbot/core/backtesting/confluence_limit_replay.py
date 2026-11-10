"""v212 confluence limit entry: paired reference/arm replay (spec § The rule,
§ Pass rule; plan V212-11 and V212-11b).

Every arm plan is derived from the knob-0 reference plan replay_scenarios
yields, so both arms see the same alert stream and the same cooldown. The
frictions of edge/frictions.py are applied here, at scoring, on the sizing
risk |trigger_price - stop| -- the R the account books. Two row shapes ship:
census rows (census_row / census) read no outcome (Stage -1); entry rows
(entry_rows / replay_entries) carry one reference row and one row per cell,
each with its fill, exit and gross/net R (Stages 0-3). Both arms simulate under
REPLAY_INSTRUMENT (v2 fills, zero costs). Reads whatever frame the caller
passes (the measure script: data/backtest_cache_ext).
"""
from __future__ import annotations

import dataclasses
import math

from swingbot import config
from swingbot.core.backtesting.acceptance import planned_rr
from swingbot.core.backtesting.backtest_scenarios import _replay_params, replay_scenarios
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r
from swingbot.core.market.indicators import atr
from swingbot.core.planning.builders import apply_confluence_limit, clamped_distance
from swingbot.core.planning.exit_sim_v2 import FILLED_STOPPED_GAP, simulate_exit_v2
from swingbot.core.planning.limit_entry_rule import bar_outcome
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

#: PRE-REGISTERED grid (spec § The rule). Changing it is a new pre-registration.
F_GRID = (1 / 3, 1 / 2, 2 / 3)
GUARDED_KNOBS = ("CONFLUENCE_LIMIT_ENTRY_F", "CONFLUENCE_STRUCTURAL_STOP_PCT",
                 "CONFLUENCE_STOP_DROP_PCT", "CONFLUENCE_ATR_STOP_FLOOR")
EARLY_STOP_BARS = 3
#: v2 fills (market at the next open, gap-through) with zero costs: the sim
#: stays frictionless and net_r applies edge/frictions.py at scoring.
REPLAY_INSTRUMENT = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
UNTRIGGERED = ("not_triggered", "no_trade")
_TOL = 1e-9


def cell_key(f) -> str:
    """'f0.333', 'f0.5', 'f0.667'."""
    return f"f{round(float(f), 3):g}"


CELLS = tuple(cell_key(f) for f in F_GRID)


def _check_knobs_off() -> None:
    live = [attr for attr in GUARDED_KNOBS if getattr(config, attr, 0)]
    if live:
        raise RuntimeError(f"{', '.join(live)} must be 0 while measuring: the reference "
                           "is today's plan and every cell is applied explicitly")


def _is_bull(plan) -> bool:
    return plan.direction == "bullish"


def in_scope(plan) -> bool:
    """Spec § The rule, Scope: a confluence market plan whose pre-clamp level
    lies more than 2% from M (builders.clamped_distance)."""
    if plan.source != "confluence" or plan.entry_type != "market":
        return False
    return clamped_distance(plan.trigger_price, plan.acceptance_level, _is_bull(plan)) is not None


def _checked(arm):
    """Rule 7: every kept plan risks at most 2% of its limit."""
    if not isinstance(arm, str) and \
            planned_loss_pct(arm.trigger_price, arm.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + _TOL:
        raise ValueError(f"v212 arm plan {arm.ticker} risks more than 2% of its limit")
    return arm


def arm_plans(ref, *, cells=F_GRID, min_rr) -> dict:
    """{cell_key: limit plan | drop reason} for one in-scope reference plan."""
    out = {}
    for f in cells:
        arm = apply_confluence_limit(ref, ref.acceptance_level, float(f), min_rr)
        if arm is ref:
            raise RuntimeError(f"{ref.ticker}: in_scope and apply_confluence_limit disagree")
        out[cell_key(f)] = _checked(arm)
    return out


def paired_alerts(ticker, df, horizon_key, *, cells=F_GRID, gates=None) -> list:
    """[(signal_index, reference_plan, {cell: arm plan | reason})], in-scope only.
    The arms' R:R floor comes from the params replay_scenarios builds the
    reference with (a `gates` dict overrides it), so both arms share one floor."""
    _check_knobs_off()
    min_rr = _replay_params(None, gates)[0].min_risk_reward_ratio
    plans = replay_scenarios(ticker, df, horizon_key, gates=gates)
    return [(int(i), ref, arm_plans(ref, cells=cells, min_rr=min_rr))
            for i, ref in plans if in_scope(ref)]


def _date(df, j) -> str | None:
    return None if j is None else str(df.index[int(j)].date())


def _identity(df, i, ref) -> dict:
    entry_date = _date(df, i)
    return {"key": f"{ref.ticker}|{ref.horizon_key}|{entry_date}|{ref.direction}",
            "ticker": ref.ticker, "horizon_key": ref.horizon_key, "strategy": ref.strategy,
            "direction": ref.direction, "entry_date": entry_date,
            "d_pct": clamped_distance(ref.trigger_price, ref.acceptance_level, _is_bull(ref))}


def _fill_state(df, i, plan) -> str:
    """The limit's fate over its expiry window, from bar_outcome alone -- no
    exit is walked, so the census stays outcome-blind."""
    last = min(i + plan.expiry_bars, len(df) - 1)
    for j in range(i + 1, last + 1):
        out = bar_outcome(plan, open_=float(df["Open"].iloc[j]), high=float(df["High"].iloc[j]),
                          low=float(df["Low"].iloc[j]))
        if out.kind == "fill":
            return "gap_stopped" if out.gap_stopped else "filled"
        if out.kind == "cancel":
            return "tp1_cancel"
    return "expired"


def census_row(df, i, ref, arms) -> dict:
    """Plans and fills only (Stage -1)."""
    states = {key: None if isinstance(arm, str) else _fill_state(df, i, arm)
              for key, arm in arms.items()}
    return {**_identity(df, i, ref),
            "drops": {key: arm if isinstance(arm, str) else None for key, arm in arms.items()},
            "fill_state": states,
            "filled": {key: state in ("filled", "gap_stopped") for key, state in states.items()}}


def net_r(direction, entry, exit_legs, risk, days) -> float:
    """R after frictions: entry and every exit slipped against the trade,
    round-trip commission, and a short's borrow over `days` calendar days.
    `risk` is the sizing risk |trigger_price - stop|."""
    if not risk or risk <= 0:
        raise ValueError("net_r needs a positive risk")
    bull = direction == "bullish"
    sign = 1.0 if bull else -1.0
    entry_net = apply_frictions(entry, "buy" if bull else "sell")
    exit_side = "sell" if bull else "buy"
    gross = sum(frac * sign * (apply_frictions(px, exit_side) - entry_net)
                for frac, px in exit_legs)
    r = gross / risk - commission_r()
    return r if bull else r - borrow_r(entry, risk, days)


def _in_window(signal_date, window) -> bool:
    start, end = window
    return not ((start and signal_date < start) or (end and signal_date > end))


def _alerts(ticker, frame, horizons, window, cells):
    for horizon_key in horizons:
        for i, ref, arms in paired_alerts(ticker, frame, horizon_key, cells=cells):
            if _in_window(_date(frame, i), window):
                yield i, ref, arms


def census(ticker, frame, horizons, window, *, cells=F_GRID) -> list:
    """Stage -1 rows for one ticker."""
    return [census_row(frame, i, ref, arms)
            for i, ref, arms in _alerts(ticker, frame, horizons, window, tuple(cells))]


def _gross_r(direction, entry, exit_legs, risk) -> float:
    sign = 1.0 if direction == "bullish" else -1.0
    return sum(frac * sign * (px - entry) for frac, px in exit_legs) / risk


def _atr14_pct(df, i) -> float | None:
    """ATR14 (indicators.atr, Wilder) as % of the signal close, bars <= i only."""
    value = float(atr(df.iloc[:i + 1], 14).iloc[-1])
    return None if math.isnan(value) else value / float(df["Close"].iloc[i]) * 100.0


def _wick_through(df, plan, res) -> bool:
    """Stopped on a wick: the stop bar closed back on the trade's side."""
    if not res.legs or res.legs[-1].get("reason") != "stop":
        return False
    close = float(df["Close"].iloc[res.exit_index])
    return close > plan.stop_loss if _is_bull(plan) else close < plan.stop_loss


def _days(df, res) -> int:
    start, end = df.index[res.entry_index].date(), df.index[res.exit_index].date()
    return max((end - start).days, 0)


def _scores(df, plan, res) -> dict:
    """Both R readings on the sizing risk, plus the stop diagnostics. stop_pct
    is the planned distance from the trigger: a gap fill's open lies past the
    stop, so measuring from it would read as a tight stop."""
    risk = abs(plan.trigger_price - plan.stop_loss)
    legs = [(leg["fraction"], leg["exit_price"]) for leg in res.legs]
    return {"r_gross": _gross_r(plan.direction, res.entry_price, legs, risk),
            "r_net": net_r(plan.direction, res.entry_price, legs, risk, _days(df, res)),
            "stop_pct": planned_loss_pct(plan.trigger_price, plan.stop_loss),
            "early_stop": res.outcome == "loss"
            and res.exit_index - res.entry_index < EARLY_STOP_BARS,
            "wick_through": _wick_through(df, plan, res)}


_EMPTY_SCORES = {"r_gross": None, "r_net": None, "stop_pct": None, "early_stop": False,
                 "wick_through": False}


def _fill_rule(touch) -> str:
    return "touch" if touch else "trade_through"


def _row(df, i, ref, arm_name, plan, res, touch) -> dict:
    filled = res.outcome not in UNTRIGGERED
    reason = getattr(res, "exit_reason", None)
    return {**_identity(df, i, ref), "arm": arm_name, "dropped": None, "filled": filled,
            "market": ref.trigger_price, "limit": None if arm_name == "ref" else plan.trigger_price,
            "stop_loss": plan.stop_loss, "outcome": res.outcome,
            "entry": res.entry_price if filled else None,
            "fill_date": _date(df, res.entry_index) if filled else None,
            "exit_date": _date(df, res.exit_index) if filled else None,
            "expiry_date": _date(df, min(i + plan.expiry_bars, len(df) - 1)),
            "exit_reason": reason, "gap_stopped": reason == FILLED_STOPPED_GAP,
            "gap_stop_r_from_limit": getattr(res, "gap_stop_r_from_limit", None),
            "planned_rr": planned_rr(plan.trigger_price, plan.stop_loss, plan.tp1),
            "atr14_pct": _atr14_pct(df, i), "fill_rule": _fill_rule(touch),
            **(_scores(df, plan, res) if filled else _EMPTY_SCORES)}


def _dropped_row(df, i, ref, arm_name, reason, touch) -> dict:
    return {**_identity(df, i, ref), "arm": arm_name, "dropped": reason, "filled": False,
            "market": ref.trigger_price, "limit": None, "stop_loss": None, "outcome": "dropped",
            "entry": None, "fill_date": None, "exit_date": None, "expiry_date": None,
            "exit_reason": None, "gap_stopped": False, "gap_stop_r_from_limit": None,
            "planned_rr": None, "atr14_pct": _atr14_pct(df, i), "fill_rule": _fill_rule(touch),
            **_EMPTY_SCORES}


def _simulate(df, i, plan, touch):
    return simulate_exit_v2(df, i, plan, REPLAY_INSTRUMENT, scale_out=True, touch_fill=touch)


def entry_rows(df, i, ref, arms, *, touch=False) -> list:
    """The reference row, then one row per cell (dropped, unfilled or filled).
    The reference never reads `touch` for its fill: touch is arm-only."""
    rows = [_row(df, i, ref, "ref", ref, _simulate(df, i, ref, False), touch)]
    for key, arm in arms.items():
        if isinstance(arm, str):
            rows.append(_dropped_row(df, i, ref, key, arm, touch))
        else:
            rows.append(_row(df, i, ref, key, arm, _simulate(df, i, arm, touch), touch))
    return rows


def replay_entries(ticker, frame, horizons, window, *, touch=False, cells=F_GRID) -> list:
    """Outcome rows for one ticker; the exit walk may run past `window`'s end."""
    return [row for i, ref, arms in _alerts(ticker, frame, horizons, window, tuple(cells))
            for row in entry_rows(frame, i, ref, arms, touch=touch)]
