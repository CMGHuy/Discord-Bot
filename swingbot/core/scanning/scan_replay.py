"""V118-7: a whole-scan historical replay of the base lane and the SHORT extra lane.

One replay "scan" per decision date: the completed daily bar of that date. At
decision date D every value is computed from frames truncated to bars dated
<= D (stock, SPY, sector ETF, the reference panel), membership and sector are
the point-in-time intervals as of D (`universe.short_snapshot(D, live=False)`),
and only `simulate_exit` walks the bars after D to score the outcome.

It runs the live code, not a copy:

* candidates -- `scan_run.build_extra_candidates` over a `ShortReference` built
  by `scan_run._short_reference`;
* scenario scoring -- `analyze._scan_one` / `analyze.scan_extra_candidate`,
  with a `ScanIO` that has no stop flag, no open-trade monitoring and an
  explicit confidence track record (`ReplaySpec.track_record`);
* per-item gates -- `qualify.qualify_short_item` with an in-memory
  confirmation store, the prior-open set and the decision-date clock;
* `dedup.dedup_scan_items`, the live sort, then the one-open-trade-per-ticker
  rule applied in posting order, as `short_run._build_alerts` does.

Instrument conventions (each is recorded in the pre-registration):

* one scan per completed bar, so SIGNAL_CONFIRMATION_SCANS counts daily bars;
* no live price: the scenario's current price is the decision bar's close;
* the confidence track record is `ReplaySpec.track_record` (default: none,
  i.e. confidence.py's assumed win rate) -- the live journal has no history;
* a trade keeps its ticker "open" through its exit bar; a plan that never
  triggers blocks nothing after its decision date;
* the base lane's sector map is the point-in-time snapshot's, never today's
  `sp500.json`; with no snapshot the base falls back to ticker-only RS;
* the strategy-sourced pass and MAX_ALERTS_PER_SCAN (a delivery cap) are
  outside the replay.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade, planned_rr
from swingbot.core.edge import factors as rs_factors
from swingbot.core.edge import regime2
from swingbot.core.infra.state import StateStore
from swingbot.core.market import opex
from swingbot.core.marketdata import universe
from swingbot.core.planning.plan_engine import simulate_exit

from . import analyze, dedup, fetch, qualify, scan_run, short_run
from .short_candidates import extra_symbols
from .short_reference import etf_for_sector

LANE_BASE = "base"
LANE_EXTRA = "short_universe"
MODES = ("broad", "isolated")


def no_track_record(_base_level: int) -> tuple:
    """No journal history: confidence.py falls back to its assumed win rate."""
    return (None, 0)


def _historical_snapshot(day: str):
    return universe.short_snapshot(day, live=False)


@dataclass(frozen=True)
class ReplaySpec:
    base_tickers: tuple
    horizons: tuple
    snapshot_fn: Callable = _historical_snapshot
    track_record: Callable = no_track_record


@dataclass(frozen=True)
class ReplayAlert:
    lane: str
    ticker: str
    direction: str
    source: str              # the plan's source: confluence
    mode: str | None         # broad | isolated for the extra lane, None for base
    decision_date: str
    horizon_key: str
    strategy: str
    entry: float
    stop: float
    target: float
    planned_rr: float | None
    outcome: str
    r_multiple: float | None

    def arm_trade(self) -> ArmTrade:
        return ArmTrade(ticker=self.ticker, strategy=self.strategy, horizon_key=self.horizon_key,
                        entry_date=self.decision_date, outcome=self.outcome,
                        r_multiple=self.r_multiple, planned_rr=self.planned_rr,
                        source=self.source, direction=self.direction)


@dataclass(frozen=True)
class ReplayExclusion:
    lane: str
    decision_date: str
    ticker: str | None
    mode: str | None
    stage: str
    reason: str


@dataclass
class ScanReplay:
    base_alerts: list = field(default_factory=list)
    added: list = field(default_factory=list)
    excluded: list = field(default_factory=list)


class MemoryState(StateStore):
    """The live confirm/revoke state machine, held in memory for one replay."""

    def __init__(self):
        self.entries: dict = {}

    def _read(self, key):
        return dict(self.entries.get(key, {}))

    def _write(self, key, entry):
        self.entries[key] = dict(entry)


@dataclass
class _Lane:
    name: str
    confirmations: MemoryState = field(default_factory=MemoryState)
    open_until: dict = field(default_factory=dict)      # ticker -> last ISO date still open
    alerts: list = field(default_factory=list)
    excluded: list = field(default_factory=list)

    def open_on(self, day: str) -> frozenset:
        return frozenset(t for t, until in self.open_until.items() if day <= until)

    def exclude(self, day, ticker, mode, stage, reason) -> None:
        self.excluded.append(ReplayExclusion(self.name, day, ticker, mode, stage, reason))


# --- per-date inputs --------------------------------------------------------------

def decision_now(day: str) -> dt.datetime:
    """22:00 UTC on the decision date: after the US close, so no bar is forming."""
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(22, 0), tzinfo=dt.timezone.utc)


def decision_dates(spy: pd.DataFrame, window: tuple[str, str]) -> list[str]:
    start, end = window
    return [d for d in (ts.date().isoformat() for ts in spy.index) if start <= d <= end]


def _asof(frames: dict, day: str) -> dict:
    return {symbol: frame.loc[:day] for symbol, frame in frames.items()}


def _offline_io(spec: ReplaySpec) -> analyze.ScanIO:
    return analyze.ScanIO(stop_requested=lambda: False, monitor_scan=lambda *a: ([], []),
                          monitor_open=lambda *a: ([], []), track_record=spec.track_record)


def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception:
        return None


@dataclass(frozen=True)
class _Day:
    day: str
    now: dt.datetime
    asof: dict
    spy: pd.DataFrame
    regime: object
    regimes: object
    snapshot: object
    tier: object


def _day_inputs(frames, day, spy_ticker, spec) -> _Day:
    asof = _asof(frames, day)
    spy = asof[spy_ticker]
    now = decision_now(day)
    return _Day(day, now, asof, spy, scan_run.get_regime(spy), _regimes(spy),
                spec.snapshot_fn(day), opex.current_tier(now))


def _sector_frames(inputs: _Day, sector_of: dict, tickers) -> dict:
    etfs = {etf_for_sector(sector_of.get(t)) for t in tickers} - {None}
    return {etf: inputs.asof[etf] for etf in sorted(etfs) if etf in inputs.asof}


def _qualify_context(inputs: _Day, lane: _Lane, frames, sector_of, sector_frames,
                     breadth=None) -> qualify.QualifyContext:
    return qualify.QualifyContext(
        frames=frames, spy=inputs.spy, sector_of=sector_of,
        etf_symbol_of=fetch._etf_symbol_of_sector(), sector_frames=sector_frames,
        regime=inputs.regime, regimes=inputs.regimes, breadth=breadth,
        confirmations=lane.confirmations,
        required_confirmations=config.SIGNAL_CONFIRMATION_SCANS,
        open_tickers=lane.open_on(inputs.day), issued_at=inputs.now.isoformat(), now=inputs.now)


# --- gates and posting (shared by both lanes) -------------------------------------

def _mode_of(item):
    return (getattr(item, "candidate_context", None) or {}).get("mode")


def _qualified(items, context, lane: _Lane, day: str) -> list:
    kept = []
    for item in items:
        verdict = qualify.qualify_short_item(item.candidate_context, item, context)
        if isinstance(verdict, qualify.Accepted):
            kept.append(item)
        else:
            lane.exclude(day, item.result.ticker, _mode_of(item), verdict.stage, verdict.reason)
    return kept


def _alert(lane: _Lane, day: str, item, full: pd.DataFrame) -> ReplayAlert | None:
    plan = item.plan_v2
    if plan is None:
        lane.exclude(day, item.result.ticker, _mode_of(item), "plan", "no_plan_v2")
        return None
    index = full.index.get_loc(pd.Timestamp(day))
    result = simulate_exit(full, index, plan, scale_out=True)
    exit_day = day if result.exit_index is None else full.index[result.exit_index].date().isoformat()
    lane.open_until[item.result.ticker] = exit_day
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    return ReplayAlert(
        lane=lane.name, ticker=item.result.ticker, direction=plan.direction, source=plan.source,
        mode=_mode_of(item), decision_date=day, horizon_key=plan.horizon_key, strategy=plan.strategy,
        entry=float(entry), stop=float(plan.stop_loss), target=float(plan.tp1),
        planned_rr=planned_rr(entry, plan.stop_loss, plan.tp1), outcome=result.outcome,
        r_multiple=result.r_total)


def _post(lane: _Lane, day: str, qualified: list, frames: dict) -> None:
    """Dedup, the live sort, then one open trade per ticker in posting order."""
    deduped = dedup.dedup_scan_items(qualified)
    deduped.sort(key=lambda item: (item.all_requirements_met, item.conf.score), reverse=True)
    for item in deduped:
        if item.result.ticker in lane.open_on(day):
            lane.exclude(day, item.result.ticker, _mode_of(item), "trade_decision", "existing_trade")
            continue
        alert = _alert(lane, day, item, frames[item.result.ticker])
        if alert is not None:
            lane.alerts.append(alert)


def _scan_params(inputs: _Day, params) -> dict:
    return {"min_confluence": opex.effective_min_confluence(params.min_target_confluence_count, inputs.tier),
            "min_confidence": opex.effective_min_confidence_level(inputs.tier),
            "hard_filters": scan_run._hard_filters_snapshot(params)}


# --- the base lane ----------------------------------------------------------------

def _base_day(lane: _Lane, inputs: _Day, frames: dict, params, spec: ReplaySpec) -> None:
    base = {t: inputs.asof[t] for t in spec.base_tickers if t in inputs.asof}
    stamped = short_run._stamp_context(base, inputs.spy)
    rs_cache = {"rels": {t: rs_factors.relative_return(f, inputs.spy) for t, f in base.items()}}
    breadth = rs_factors.breadth_pct_above_50ema(base)
    sector_of = dict(inputs.snapshot.sector_of) if inputs.snapshot is not None else {}
    gates = _scan_params(inputs, params)
    items = []
    for ticker, frame in stamped.items():
        items.extend(analyze._scan_one(
            ticker, frame, list(spec.horizons), None, inputs.regime, gates["min_confluence"],
            gates["min_confidence"], rs_cache=rs_cache, spy_df=inputs.spy, breadth=breadth,
            live_prices={}, hard_filters=gates["hard_filters"], opex_tier_today=inputs.tier,
            io=_offline_io(spec))["items"])
    context = _qualify_context(inputs, lane, stamped, sector_of,
                               _sector_frames(inputs, sector_of, base), breadth)
    _post(lane, inputs.day, _qualified(items, context, lane, inputs.day), frames)


# --- the extra lane ---------------------------------------------------------------

def _extra_reference(inputs: _Day, spec: ReplaySpec, lane: _Lane):
    snapshot = inputs.snapshot
    queue = extra_symbols(snapshot, spec.base_tickers)
    extra = {s: inputs.asof[s] for s in queue if s in inputs.asof}
    for symbol in queue:
        if symbol not in extra:
            lane.exclude(inputs.day, symbol, None, "candidate", "missing_frame")
    base = {t: inputs.asof[t] for t in spec.base_tickers if t in inputs.asof}
    return scan_run._short_reference(inputs.day, snapshot, extra, base, inputs.spy, inputs.now,
                                     sector_frames=inputs.asof)


def _candidates(inputs: _Day, reference, spec, lane: _Lane, allowed_modes) -> list:
    rejected: list = []
    found = scan_run.build_extra_candidates(spec.base_tickers, decision_date=inputs.day,
                                            snapshot=inputs.snapshot, reference=reference,
                                            rejected=rejected)
    for symbol, reason in rejected:
        lane.exclude(inputs.day, symbol, None, "candidate", reason)
    kept = [c for c in found if c.mode in allowed_modes]
    for candidate in found:
        if candidate.mode not in allowed_modes:
            lane.exclude(inputs.day, candidate.ticker, candidate.mode, "candidate", "mode_not_allowed")
    return kept


def _extra_day(lane: _Lane, inputs: _Day, frames: dict, params, spec: ReplaySpec,
               allowed_modes) -> None:
    if inputs.snapshot is None:
        lane.exclude(inputs.day, None, None, "candidate", "no_snapshot")
        return
    reference = _extra_reference(inputs, spec, lane)
    candidates = _candidates(inputs, reference, spec, lane, allowed_modes)
    stamped = short_run._stamp_context(dict(reference.frames), reference.spy)
    gates = _scan_params(inputs, params)
    ctx = analyze.ExtraScanContext(
        regime=inputs.regime, min_confluence=gates["min_confluence"],
        min_confidence=gates["min_confidence"], rs_cache={"rels": dict(enumerate(reference.reference_rels))},
        spy_df=reference.spy, live_prices={}, hard_filters=gates["hard_filters"],
        opex_tier=inputs.tier, now=inputs.now, io=_offline_io(spec))
    items = []
    for candidate in candidates:
        items.extend(analyze.scan_extra_candidate(candidate, stamped.get(candidate.ticker), ctx,
                                                  list(spec.horizons)))
    context = _qualify_context(inputs, lane, stamped, inputs.snapshot.sector_of,
                               dict(reference.sector_frames))
    _post(lane, inputs.day, _qualified(items, context, lane, inputs.day), frames)


# --- entry points -----------------------------------------------------------------

def _run_lane(lane: _Lane, step, frames, window, spec) -> _Lane:
    spy_ticker = config.MARKET_REGIME_TICKER
    for day in decision_dates(frames[spy_ticker], window):
        step(lane, _day_inputs(frames, day, spy_ticker, spec))
    return lane


def replay_base_scan(frames: dict, window: tuple[str, str], params, *, spec: ReplaySpec) -> _Lane:
    """The base lane only: its alerts never depend on the extra lane's flag."""
    return _run_lane(_Lane(LANE_BASE), lambda lane, inputs: _base_day(lane, inputs, frames, params, spec),
                     frames, window, spec)


def replay_extra_short_scan(frames: dict, window: tuple[str, str], params, *, spec: ReplaySpec,
                            allowed_modes) -> _Lane:
    """The SHORT extra lane: bearish-only, PIT members outside the base lane."""
    allowed = frozenset(allowed_modes)
    unknown = allowed - set(MODES)
    if unknown:
        raise ValueError(f"unknown SHORT mode(s) {sorted(unknown)}; expected {MODES}")
    return _run_lane(
        _Lane(LANE_EXTRA),
        lambda lane, inputs: _extra_day(lane, inputs, frames, params, spec, allowed),
        frames, window, spec)


def replay_short_universe(frames: dict, window: tuple[str, str], params, *, mode: str,
                          spec: ReplaySpec) -> ScanReplay:
    """Base alerts, plus the extra lane's alerts in `mode` ("off" adds none)."""
    base = replay_base_scan(frames, window, params, spec=spec)
    out = ScanReplay(base_alerts=list(base.alerts), excluded=list(base.excluded))
    if mode != "off":
        extra = replay_extra_short_scan(frames, window, params, spec=spec, allowed_modes={mode})
        out.added, out.excluded = list(extra.alerts), out.excluded + extra.excluded
    return out
