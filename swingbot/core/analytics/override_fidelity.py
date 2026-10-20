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

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.planning.plan_types import PlanStatus

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
