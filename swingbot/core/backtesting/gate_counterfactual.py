"""v147: what a candidate thrown away by a gate would have done.

One pure function, ``simulate_blocked(candidate, bars)``, shared unchanged by
the TRAIN recorders and the live resolver. It finds the signal bar by exact
date, re-anchors stored prices when the bar basis moved (split/dividend), takes
the stored plan or rebuilds it on the frame truncated at the signal bar
(overrides pinned to the stored scan params), and walks it through
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

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import params as plan_params
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
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


class UnpinnableBuild(RuntimeError):
    """A strategy rebuild would read live state (journal / wall clock) no stored field pins."""


PIN_KEYS = ("stop_mult", "tp2_r", "time_stop_days")
_WALL_CLOCK_FLAGS = ("STALL_EXIT_ENABLED", "OPEX_CAUTION_ENABLED")


def scenario_to_dict(scenario) -> dict:
    """JSON-safe dict of a levels.Scenario (sources kept as plain strings)."""
    out = dataclasses.asdict(scenario)
    for key in ("stop_sources", "target_sources", "target2_sources"):
        if out.get(key) is not None:
            out[key] = [str(s) for s in out[key]]
    return out


def scenario_from_dict(d: dict) -> levels.Scenario:
    """Inverse of scenario_to_dict; unknown keys are ignored."""
    known = {f.name for f in dataclasses.fields(levels.Scenario)}
    return levels.Scenario(**{k: v for k, v in d.items() if k in known})


def pinned_scan_params(strategy: str, *, plan: TradePlanV2 | None = None, params=None) -> dict:
    """The candidate's ``scan_params``: the three data-driven-stops overrides as they
    stood at the gate, plus the ScanParams fields. Read off the plan when one
    exists, else resolved now (the block time) through the live resolvers."""
    if plan is not None:
        pins = {"stop_mult": plan.stop_mult_applied, "tp2_r": plan.tp2_r_applied,
                "time_stop_days": plan.time_stop_days}
    else:
        pins = {"stop_mult": plan_params._resolve_stop_mult(strategy),
                "tp2_r": plan_params._resolve_tp2_r(strategy),
                "time_stop_days": plan_params._resolve_time_stop_days(strategy)}
    pins["params"] = dataclasses.asdict(params) if params is not None else None
    return pins


def _scan_params_of(candidate: BlockedCandidate):
    """The stored ScanParams, or None (the builder's own default)."""
    stored = (candidate.scan_params or {}).get("params")
    if not stored:
        return None
    from swingbot.scan_params import ScanParams
    known = {f.name for f in dataclasses.fields(ScanParams)}
    return ScanParams(**{k: v for k, v in stored.items() if k in known})


def _strategy_pins(candidate: BlockedCandidate) -> dict:
    """The pinned overrides; raises UnpinnableBuild when the build would read live state."""
    on = [name for name in _WALL_CLOCK_FLAGS if getattr(config, name, False)]
    if on:
        raise UnpinnableBuild(f"{', '.join(on)} on: the rebuild would read live state")
    stored = candidate.scan_params or {}
    pins = {key: stored.get(key) for key in PIN_KEYS}
    if config.DATA_DRIVEN_STOPS_ENABLED and any(v is None for v in pins.values()):
        raise UnpinnableBuild("DATA_DRIVEN_STOPS_ENABLED on and an override is not pinned")
    return pins


def _strategy_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The live strategy constructor on the truncated frame, overrides pinned."""
    pins = _strategy_pins(candidate)
    return build_strategy_plan(
        window, len(window) - 1, ticker=candidate.ticker, strategy=candidate.strategy,
        horizon_key=candidate.horizon, direction=candidate.direction,
        stop_mult=pins["stop_mult"], tp2_r=pins["tp2_r"],
        time_stop_days=pins["time_stop_days"], scan_params=_scan_params_of(candidate))


def _confluence_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The live confluence constructor; level_map from the truncated frame."""
    if candidate.scenario is None:
        return None
    price = float(window["Close"].iloc[-1])
    level_map = levels.build_level_map(window, HORIZONS[candidate.horizon], price)
    return build_confluence_plan(
        scenario_from_dict(candidate.scenario), window, ticker=candidate.ticker,
        horizon_key=candidate.horizon, primary_strategy=candidate.strategy,
        level_map=level_map, quality_inputs=None, params=_scan_params_of(candidate))


def build_candidate_plan(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """Rebuild the plan the gate threw away, from ``window`` (bars <= signal) only."""
    if candidate.source == "strategy":
        return _strategy_plan(candidate, window)
    return _confluence_plan(candidate, window)


def _plan_for(candidate: BlockedCandidate, window) -> TradePlanV2 | None:
    """The stored plan as stored; otherwise the truncated rebuild."""
    if candidate.plan is not None:
        return plan_from_dict(candidate.plan)
    return build_candidate_plan(candidate, window)


def _built_plan(candidate: BlockedCandidate, window) -> tuple[TradePlanV2 | None, bool]:
    """(plan | None, unpinnable)."""
    try:
        return _plan_for(candidate, window), False
    except UnpinnableBuild as exc:
        log.warning("gate counterfactual: %s %s %s -- %s; no-data", candidate.ticker,
                    candidate.strategy, candidate.signal_date, exc, exc_info=True)
        return None, True


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
    plan, unpinnable = _built_plan(_rebased(candidate, ratio), frame.iloc[:index + 1])
    if unpinnable:
        return _status_only("no-data", reanchored=ratio is not None)
    if plan is None:
        return _status_only("no-plan", reanchored=ratio is not None)
    return _outcome(frame, index, plan, ratio is not None)
