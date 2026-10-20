"""v173 §3: what a manual override did against the engine -- the pure core.

A manual close (`_close_plan`, reason "manual" or "manual_bulk") ends a plan
the engine would otherwise have kept managing. This module replays that plan
through the v2 exit engine from its real fill and compares the two arms on one
cost basis. It is pure: no store, no network, no file reads. Plans, bars
(`runner_path.cached_daily_bars`, read by override_io) and linked trades come
in as arguments.

This first block holds the frozen constants, the timestamp-to-session rule,
the plan readers, the stamp kinds and the row shape. The engine path and the
two arms follow (V173-8); `replay_override` and its data admission (V173-9,
V173-22, V173-23) and `summarise` (V173-10) close the module. The constants
are pre-registered (spec §4): changing any of them is a new spec, never an
edit.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.instrument import contract, costs
from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.exit_sim_v2 import fill_bar_exit, walk_v2
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.time_exit import TIME_EXIT_REASON

#: The terminal reasons of a manual close; "manual_bulk" rows are shown, never summed.
MANUAL_REASONS = ("manual", "manual_bulk")
#: Every row carries exactly one of these (spec §3 status table, eight since
#: the plan panel added "unstamped").
STATUSES = ("resolved", "open", "unstamped", "stale", "ambiguous", "parity_mismatch",
            "split_affected", "unreplayable")
#: Statuses left out of the sums and capped at EXCLUDED_CAP for the verdict.
EXCLUDED_STATUSES = ("unstamped", "stale", "ambiguous", "parity_mismatch", "split_affected",
                     "unreplayable")
#: walk_v2's reasons for stopping at ctx.end -- the hold cap, or the data end.
TIMEOUT_REASONS = ("timeout", "runner_timeout")
#: What the CLOSED entry's `override` key says (stamp_kind).
STAMP_KINDS = ("missing", "failed", "stamped")
#: Frozen (spec §3, §4).
DEAD_BAND = 0.05
VERDICT_FLOOR = 30
WEEK_FLOOR = 10
EXCLUDED_CAP = 0.20
SPLIT_TOLERANCE = 0.02
LEDGER_ID = "v173-override-fidelity"

#: Longest run of calendar days with no NYSE session in the covered years is
#: four; two weeks of look-back always reaches the previous session.
_LOOKBACK = dt.timedelta(days=14)


@dataclass(frozen=True)
class SessionHit:
    """The NYSE session a timestamp belongs to, and which of its prices a
    pre-v173 close is priced from: "open" (before 09:30 ET) or "close"."""
    session: dt.date
    price_kind: str


def _to_et(moment: dt.datetime) -> dt.datetime:
    if moment.tzinfo is None:          # status_history stamps are written in UTC
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(US_MARKET_TZ)


def _parse_et(at_iso) -> dt.datetime | None:
    if not at_iso:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(at_iso))
    except ValueError:
        return None
    return _to_et(moment)


def _session_on_or_before(day: dt.date) -> dt.date | None:
    """The last NYSE session on or before `day`; None outside the calendar."""
    cal = nyse_calendar()
    if day < cal.first or day > cal.last:
        return None
    prior = cal.sessions(day - _LOOKBACK, day)
    return prior[-1] if prior else None


def assign_session(at_iso: str | None) -> SessionHit | None:
    """The override session of an ISO timestamp, in America/New_York.

    Session day before 09:30 -> that day, "open"; from 09:30 on (regular
    hours or after the close, early closes included) -> that day, "close";
    a non-session day -> the last session before it, "close". None when the
    stamp is missing, unparseable or outside the calendar."""
    local = _parse_et(at_iso)
    if local is None:
        return None
    day = local.date()
    prior = _session_on_or_before(day)
    if prior is None:
        return None
    if prior == day:
        return SessionHit(day, "open" if local.time() < RTH_OPEN else "close")
    return SessionHit(prior, "close")


def latest_completed_session(now: dt.datetime) -> dt.date:
    """The last NYSE session whose regular close (ET) is at or before `now`:
    the newest bar a fresh daily cache can hold settled."""
    local = _to_et(now)
    day = local.date()
    if nyse_calendar().is_session(day) and local.time() >= session_close(day):
        return day
    prior = _session_on_or_before(day - dt.timedelta(days=1))
    if prior is None:
        raise ValueError(f"{now.isoformat()} lies outside the NYSE calendar")
    return prior


def session_index(df, day: dt.date | None) -> int | None:
    """Positional index of the bar dated `day`; None when absent."""
    if df is None or len(df) == 0 or day is None:
        return None
    hits = np.flatnonzero(pd.DatetimeIndex(df.index).date == day)
    return int(hits[0]) if hits.size else None


def transition_at(plan, status: str) -> str | None:
    """`at` of the first status_history entry with `status`."""
    return next((entry.get("at") for entry in plan.status_history or []
                 if entry.get("status") == status), None)


def override_entry(plan) -> dict | None:
    """The terminal CLOSED entry of a manual close; None for any other plan."""
    history = plan.status_history or []
    if plan.status != PlanStatus.CLOSED or not history:
        return None
    last = history[-1]
    if last.get("status") == PlanStatus.CLOSED and last.get("reason") in MANUAL_REASONS:
        return last
    return None


def is_override(plan) -> bool:
    return override_entry(plan) is not None


def state_at_close(plan) -> str:
    """"PARTIAL" when TP1 had filled before the override, else "ACTIVE"."""
    partial = any(entry.get("status") == PlanStatus.PARTIAL
                  for entry in plan.status_history or [])
    return PlanStatus.PARTIAL if partial else PlanStatus.ACTIVE


def stamp_kind(entry: dict | None) -> str:
    """What the CLOSED entry's `override` key says, read from the key alone.

    "missing": no key (a close made before v173 shipped; priced from its
    session bar, approx). "failed": the key is there but holds None, a
    non-dict, or a stamp with price_source "none" (a v173 close nothing could
    price; V173-9 makes an individual one `unstamped`). "stamped": a priced
    stamp. A missing key is never inferred to be anything else."""
    if not entry or "override" not in entry:
        return "missing"
    stamp = entry["override"]
    if not isinstance(stamp, dict) or stamp.get("price_source") == "none":
        return "failed"
    return "stamped"


@dataclass(frozen=True)
class OverrideRow:
    """One override against the engine. R is on the plan's initial risk, net
    of modelled costs and pre-tax (`delta_r_gross`: the same delta before
    costs, descriptive only); the *_usd fields are None without a dollar
    risk. Only `resolved` rows that are neither bulk nor approx are summed."""
    plan_id: str
    ticker: str
    horizon: str
    direction: str
    state_at_close: str
    close_date: dt.date | None
    bulk: bool
    approx: bool
    price_source: str
    status: str
    actual_r: float | None = None
    engine_r: float | None = None
    delta_r: float | None = None
    delta_r_gross: float | None = None
    actual_usd: float | None = None
    engine_usd: float | None = None
    delta_usd: float | None = None
    engine_exit_reason: str | None = None
    outcome: str | None = None
    source: str = "manual"

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"unknown override status {self.status!r}")

    @property
    def entry_date(self) -> dt.date | None:
        """The close date, under the name stats.group_by_week reads."""
        return self.close_date

    def to_dict(self) -> dict:
        body = asdict(self)
        body["close_date"] = self.close_date.isoformat() if self.close_date else None
        return body


#: The row keys of the report payload, in order.
ROW_FIELDS = tuple(OverrideRow.__dataclass_fields__)


def outcome_of(delta_r: float | None) -> str | None:
    """helped / hurt / neutral under the frozen ±DEAD_BAND (edges are neutral)."""
    if delta_r is None:
        return None
    if delta_r > DEAD_BAND:
        return "helped"
    if delta_r < -DEAD_BAND:
        return "hurt"
    return "neutral"


# --- the engine path and the two arms (V173-8) ---------------------------------

#: The instrument every arm is booked on: v2 fills and costs, as the sim.
INSTRUMENT = contract.resolve("v2")
#: "Before costs": the same legs with no slippage and no commission. Shown
#: next to the net figure, never used by the verdict decision (spec §4).
GROSS_COST_MODEL = contract.CostModel(commission_per_share=0.0, slippage_bps=0.0,
                                      stop_slippage_bps=0.0)

_TARGET_REASONS = frozenset({"tp1", "runner_tp2"})
_CLOSE_REASONS = frozenset({"timeout", "runner_timeout", "acceptance_exit", "stall_exit",
                            "runner_progress_stall", TIME_EXIT_REASON})


def hold_cap_bars(plan) -> int:
    """The walk length simulate_exit_v2 gives this plan."""
    return exit_sim._hold_cap_bars(plan, HORIZONS[plan.horizon_key]["max_holding_days"])


def engine_frame(df: pd.DataFrame, ov_idx: int) -> pd.DataFrame:
    """`df` with the override session's range shrunk to its open-close body.

    The human acted somewhere inside that session; the engine is never shown
    the session's high or low as a later path (spec §3, no lookahead). A
    touch of the real range is caught as `ambiguous` instead. Walk the result
    with `indicator_df=df` so ATR and structure still read the real bar."""
    frame = df.copy()
    open_, close = float(frame["Open"].iat[ov_idx]), float(frame["Close"].iat[ov_idx])
    frame.iloc[ov_idx, frame.columns.get_loc("High")] = max(open_, close)
    frame.iloc[ov_idx, frame.columns.get_loc("Low")] = min(open_, close)
    return frame


def engine_path(plan, df: pd.DataFrame, fill_idx: int, *,
                indicator_df: pd.DataFrame | None = None) -> ExitResult:
    """The plan left alone: the fill-bar stop check, then the v2 walk, from
    the live fill bar at the live fill price with the original stop. Never a
    mid-trade resume: the engine is deterministic, so replaying the whole
    trade is the counterfactual. `indicator_df` (same index as `df`) feeds
    only the runner's ATR and structure: the engine arm passes the real
    frame while walking the clamped one."""
    # tp1_index guard (v173): ExitResult.tp1_index is a plain class attribute,
    # not a dataclass field, so dataclasses.replace() returns a copy with the
    # default None and asdict() leaves it out. Callers read it from the object
    # returned here; never copy, re-build or serialise the result first.
    entry = float(plan.entry_price)
    early = fill_bar_exit(df, fill_idx, entry, plan, INSTRUMENT)
    if early is not None:
        return early
    return walk_v2(df, fill_idx, entry, plan, hold_cap_bars(plan), INSTRUMENT,
                   scale_out=plan.tp1_fraction < 1.0, indicator_df=indicator_df)


def leg_kind(reason: str) -> str:
    """The costs.EXIT_KINDS kind walk_v2 books a leg of this reason with."""
    if reason in _TARGET_REASONS:
        return "target"
    return "close" if reason in _CLOSE_REASONS else "stop"


def live_tp1_leg(plan) -> dict | None:
    """The realised TP1 leg as a raw costs.book leg; both arms share it."""
    leg = next((leg for leg in plan.legs_realized or [] if leg.get("reason") == "tp1"), None)
    if leg is None or leg.get("exit_price") is None:
        return None
    return {"fraction": float(plan.tp1_fraction), "exit_price": float(leg["exit_price"]),
            "reason": "tp1", "kind": "target"}


def _remainder(plan, state: str) -> float:
    """The position the override closed (plan_manager.py:1115)."""
    return 1.0 - float(plan.tp1_fraction) if state == PlanStatus.PARTIAL else 1.0


def _tp1_legs(plan, state: str) -> list[dict]:
    if state != PlanStatus.PARTIAL:
        return []
    leg = live_tp1_leg(plan)
    if leg is None:
        raise ValueError(f"{plan.plan_id}: PARTIAL at close but no realised tp1 leg")
    return [leg]


def _book(plan, legs: list[dict], cost_model=None) -> float:
    """One costs.book call: the plan's entry and original stop, every leg.
    `cost_model` None is the v2 model; GROSS_COST_MODEL gives before costs."""
    entry, stop = float(plan.entry_price), float(plan.stop_loss)
    sign = 1 if plan.direction == "bullish" else -1
    if (entry - stop) * sign <= 0:
        raise ValueError(f"{plan.plan_id}: entry {entry} is at or beyond the stop {stop}")
    model = INSTRUMENT.cost_model if cost_model is None else cost_model
    r_total, _ = costs.book(model, direction=plan.direction,
                            entry_price=entry, stop_loss=stop, legs=legs)
    return r_total


def actual_r(plan, exit_price: float, state: str, *, cost_model=None) -> float:
    """The override as booked: the live TP1 leg (PARTIAL) plus the closed
    remainder at `exit_price`, a stop-kind exit (a market order by hand)."""
    manual = {"fraction": _remainder(plan, state), "exit_price": float(exit_price),
              "reason": "manual", "kind": "stop"}
    return _book(plan, [*_tp1_legs(plan, state), manual], cost_model)


def engine_r(plan, result: ExitResult, state: str, *, cost_model=None) -> float:
    """The replay as booked: the live TP1 leg (PARTIAL; the replay's own tp1
    leg is dropped) plus the replay's remainder legs, re-scaled to the
    remainder, each with the kind the engine books its reason with."""
    partial = state == PlanStatus.PARTIAL
    own = [leg for leg in result.legs if not (partial and leg.get("reason") == "tp1")]
    total = sum(float(leg["fraction"]) for leg in own)
    if total <= 0:
        raise ValueError(f"{plan.plan_id}: the engine result has no leg to book")
    scale = _remainder(plan, state) / total
    legs = [{"fraction": float(leg["fraction"]) * scale, "exit_price": float(leg["exit_price"]),
             "reason": leg["reason"], "kind": leg_kind(leg["reason"])} for leg in own]
    return _book(plan, [*_tp1_legs(plan, state), *legs], cost_model)


def dollar_risk(plan, trade: dict | None) -> float | None:
    """Dollars at risk at the fill: the linked paper trade's record shares
    times the initial risk per share (the v170 convention). None when the
    trade or its shares are missing: the row then shows R only."""
    if not trade or trade.get("shares") is None:
        return None
    if plan.entry_price is None or plan.stop_loss is None:
        return None
    try:
        shares = float(trade["shares"])
    except (TypeError, ValueError):
        return None
    risk = shares * abs(float(plan.entry_price) - float(plan.stop_loss))
    return risk if risk > 0 else None


def to_usd(r: float | None, risk: float | None) -> float | None:
    """R in dollars; None when either side is unknown."""
    if r is None or risk is None:
        return None
    return round(r * risk, 2)
