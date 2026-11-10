"""v212 confluence limit entry: paired reference/arm replay (spec § The rule,
§ Pass rule; plan V212-11 and V212-11b).

Every arm plan is derived from the knob-0 reference plan replay_scenarios
yields, so both arms see the same alert stream and the same cooldown. The
frictions of edge/frictions.py are applied here, at scoring, on the sizing
risk |trigger_price - stop| -- the R the account books. Census rows read no
outcome (Stage -1); entry rows (V212-11b) carry outcomes (Stages 0-3). Reads
whatever frame the caller passes (the measure script: data/backtest_cache_ext).
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r
from swingbot.core.planning.builders import apply_confluence_limit, clamped_distance
from swingbot.core.planning.limit_entry_rule import bar_outcome
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.scan_params import ScanParams

#: PRE-REGISTERED grid (spec § The rule). Changing it is a new pre-registration.
F_GRID = (1 / 3, 1 / 2, 2 / 3)
GUARDED_KNOBS = ("CONFLUENCE_LIMIT_ENTRY_F", "CONFLUENCE_STRUCTURAL_STOP_PCT",
                 "CONFLUENCE_STOP_DROP_PCT", "CONFLUENCE_ATR_STOP_FLOOR")
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
    """[(signal_index, reference_plan, {cell: arm plan | reason})], in-scope only."""
    _check_knobs_off()
    min_rr = ScanParams.from_config().min_risk_reward_ratio
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
