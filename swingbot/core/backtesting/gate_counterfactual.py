"""v147: what a candidate thrown away by a gate would have done.

One pure function, ``simulate_blocked(candidate, bars)``, shared unchanged by
the TRAIN recorders and the live resolver. It finds the signal bar by exact
date, re-anchors stored prices when the bar basis moved (split/dividend), takes
the stored plan (V147-3 adds the truncated rebuild), and walks it through
``exit_sim.simulate_exit(..., scale_out=True)`` -- the exact call the replays
make (``arms/strategy_engine.py``, ``backtest_scenarios.py``), with
``max_holding_days`` left None so it resolves to the horizon's value.

NO-LOOKAHEAD: the plan reads ``bars.iloc[:signal_index + 1]`` only; the walk
reads bars strictly after the signal bar (simulate_exit's own contract).
``not_triggered`` is ``no-fill`` and never a 0R trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import TradePlanV2, plan_from_dict, plan_to_dict

log = logging.getLogger(__name__)

CF_STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")
REANCHOR_TOLERANCE = 0.005
OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
PLAN_PRICE_FIELDS = (
    "trigger_price", "entry_price", "stop_loss", "tp1", "tp2", "working_stop",
    "notified_stop", "acceptance_level", "acceptance_close_below",
    "limit_cancel_level", "runner_high_close", "first_seen_price",
)
SCENARIO_PRICE_FIELDS = ("entry", "market_price", "stop_loss", "take_profit", "target2_price")


@dataclass(frozen=True)
class BlockedCandidate:
    """One blocked candidate, as recorded at the gate (all prices in the signal-day basis)."""

    ticker: str
    gate: str
    reason: str | None
    source: str                      # "strategy" | "confluence" | "short_lane"
    strategy: str
    horizon: str
    direction: str
    signal_date: str                 # YYYY-MM-DD, the completed signal bar
    plan: dict | None = None         # plan_to_dict of a plan that existed at the gate
    scenario: dict | None = None     # scenario_to_dict, confluence / short lane
    scan_params: dict | None = None  # pinned overrides + ScanParams fields (V147-3)
    signal_close: float | None = None
    margin: float | None = None


@dataclass(frozen=True)
class CounterfactualResult:
    cf_status: str                   # one of CF_STATUSES
    cf_r: float | None               # None unless filled
    win: bool | None                 # None unless filled; True = TP1 touched
    exit_index: int | None
    last_bar_date: str | None
    bars_sha256: str | None
    reanchored: bool
    plan: dict | None


def result_from_exit(exit_result) -> tuple[str, float | None, bool | None]:
    """(cf_status, cf_r, win) of one ExitResult under the one population rule.

    ``not_triggered`` carries a placeholder r_total of 0.0 -- it is no-fill,
    never a 0R trade. ``no_trade`` (risk_per_share <= 0) means no valid plan."""
    if exit_result.outcome == "not_triggered":
        return "no-fill", None, None
    if exit_result.outcome == "no_trade":
        return "no-plan", None, None
    legs = exit_result.legs or []
    won = exit_result.outcome == "win" or any(leg.get("reason") == "tp1" for leg in legs)
    return "filled", float(exit_result.r_total), bool(won)


def bars_sha256(frame) -> str:
    """Reproducible hash of the exact OHLCV slice a resolution used."""
    columns = [c for c in OHLCV_COLUMNS if c in frame.columns]
    payload = frame[columns].to_csv(date_format="%Y-%m-%d", float_format="%.10g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _session_dates(frame) -> pd.Index:
    """The frame's bar dates as tz-naive YYYY-MM-DD strings."""
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.strftime("%Y-%m-%d")


def _completed(bars, last_session: str | None):
    """Drop every bar after the last completed session (no-op when None)."""
    if last_session is None:
        return bars
    return bars.loc[np.asarray(_session_dates(bars) <= last_session)]


def _signal_index(frame, signal_date: str) -> int | None:
    """Positional index of the bar dated exactly signal_date; no nearest-bar fallback."""
    hits = np.flatnonzero(np.asarray(_session_dates(frame) == signal_date))
    return int(hits[0]) if len(hits) else None


def _reanchor_ratio(candidate: BlockedCandidate, frame, index: int) -> float | None:
    """cache close / stored close when they drift past REANCHOR_TOLERANCE, else None."""
    stored = candidate.signal_close
    if stored is None or not float(stored) > 0:
        return None
    ratio = float(frame["Close"].iloc[index]) / float(stored)
    return ratio if abs(ratio - 1.0) > REANCHOR_TOLERANCE else None


def _scaled(record: dict | None, fields: tuple, ratio: float) -> dict | None:
    if record is None:
        return None
    out = dict(record)
    for name in fields:
        if out.get(name) is not None:
            out[name] = float(out[name]) * ratio
    return out


def _rebased(candidate: BlockedCandidate, ratio: float | None) -> BlockedCandidate:
    """The candidate with every stored price level moved onto the cache's basis."""
    if ratio is None:
        return candidate
    return dataclasses.replace(
        candidate,
        plan=_scaled(candidate.plan, PLAN_PRICE_FIELDS, ratio),
        scenario=_scaled(candidate.scenario, SCENARIO_PRICE_FIELDS, ratio),
        signal_close=float(candidate.signal_close) * ratio,
    )


def bars_needed(plan: TradePlanV2) -> int:
    """Bars after the signal bar the walk can read: pending window + horizon hold."""
    hold = int(HORIZONS[plan.horizon_key]["max_holding_days"])
    return hold if plan.entry_type == "market" else int(plan.expiry_bars) + hold


def _last_date(frame) -> str | None:
    return str(_session_dates(frame)[-1]) if len(frame) else None


def _status_only(status: str, *, reanchored: bool = False, last_bar_date: str | None = None,
                 plan: dict | None = None) -> CounterfactualResult:
    return CounterfactualResult(status, None, None, None, last_bar_date, None, reanchored, plan)


def _outcome(frame, index: int, plan: TradePlanV2, reanchored: bool) -> CounterfactualResult:
    """Walk the plan, or ``pending`` while the bars it can read are not all in."""
    end = index + bars_needed(plan)
    if len(frame) - 1 < end:
        return _status_only("pending", reanchored=reanchored, last_bar_date=_last_date(frame),
                            plan=plan_to_dict(plan))
    used = frame.iloc[:end + 1]
    exit_result = simulate_exit(used, index, plan, scale_out=True)
    status, cf_r, win = result_from_exit(exit_result)
    return CounterfactualResult(status, cf_r, win, exit_result.exit_index, _last_date(used),
                                bars_sha256(used), reanchored, plan_to_dict(plan))


def _plan_for(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The stored plan as stored. V147-3 adds the truncated rebuild from ``window``."""
    if candidate.plan is not None:
        return plan_from_dict(candidate.plan)
    return None


def simulate_blocked(candidate: BlockedCandidate, bars, *,
                     last_session: str | None = None) -> CounterfactualResult:
    """What ``candidate`` would have done on ``bars`` (one ticker, daily OHLCV)."""
    if bars is None or len(bars) == 0:
        return _status_only("no-data")
    frame = _completed(bars, last_session)
    index = _signal_index(frame, candidate.signal_date)
    if index is None:
        return _status_only("no-data")
    ratio = _reanchor_ratio(candidate, frame, index)
    plan = _plan_for(_rebased(candidate, ratio), frame.iloc[:index + 1])
    if plan is None:
        return _status_only("no-plan", reanchored=ratio is not None)
    return _outcome(frame, index, plan, ratio is not None)
