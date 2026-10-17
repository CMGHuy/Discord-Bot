"""Historical replay of the confluence scan (spec §4): rebuild the level
map as of each bar, run levels.build_scenarios with that bar's close, and
feed the qualifying scenarios through the SAME plan constructor and exit
simulator the live scan uses. No lookahead: every computation sees
df.iloc[:i+1] only."""
from __future__ import annotations

import dataclasses
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from typing import NamedTuple

import numpy as np

from swingbot import config
from swingbot.core.edge import gates as edge_gates
from swingbot.core.market import levels
from swingbot.core.market.chart_patterns import dead_cat_bounce
from swingbot.core.planning.plan_engine import build_confluence_plan, primary_strategy_for, simulate_exit
from swingbot.core.planning.params import stamp_entry_context
from swingbot.core.backtesting.asof_context import asof_row
from swingbot.core.marketdata.pit_membership import is_member
from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS, MIN_BARS
from swingbot.core.scanning.gating import passes_confluence, scenario_gate_inputs
from swingbot.scan_params import ScanParams

log = logging.getLogger(__name__)

# Levels move slowly; recomputing the full multi-source level map every bar
# is ~5x the cost for near-identical output. One recompute per 5 bars is the
# fidelity/cost tradeoff -- the same granularity the Task 28 backtest tp2
# lookup uses.
LEVEL_REFRESH_BARS = 5

# TRAIN grid found no qualifying config (Task 39); these are unvalidated
# defaults, not a tuned winner. The pre-registered selection rule (per
# horizon: win_rate>=80, expectancy_r>0, N>=30, excl<=50%; pair with the
# best pooled ExpR among pairs with >=2 qualifying horizons) failed at every
# one of the 6 (min_confluence, min_risk_reward) grid points tested -- best
# observed win_rate was 66.4% (need >=80%) and every expectancy_r was
# negative (need >0). Zero qualifying horizons anywhere, so there was no
# pair to even rank. Full grid + the rule applied by hand:
# docs/superpowers/results/2026-07-confluence-train-grid.txt; narrative +
# table: docs/superpowers/results/2026-07-confluence-train.md.
#
# Per the plan's pre-registered fallback ("if no pair qualifies, confluence
# source stays WEAK everywhere and Tasks 41-42 record that honestly"), this
# is NOT the grid winner -- there wasn't one. min_reward_pct/min_stop_
# distance_pct/max_stop_distance_pct/min_risk_reward mirror the pre-existing
# SCENARIO_GATES in scripts/backtest/run_backtest_range.py (the closest existing
# precedent, itself never grid-validated). min_confluence uses the least
# restrictive value the Task 39 grid tested (2), not a tuned choice. horizons
# lists every horizon the grid covered -- NOT a "qualifying" subset, since
# none qualified.
CONFLUENCE_GATES = {
    "min_reward_pct": 3.0,
    "min_stop_distance_pct": 2.0,
    "max_stop_distance_pct": 7.0,
    "min_risk_reward": 1.5,
    "min_confluence": 2,
    "cooldown_bars": 5,
    "horizons": ["4w", "2m", "3m", "4m", "6m"],  # grid coverage, not a pass
}


#: Tolerance the replay counts confirming strategies with (the live default,
#: CONFLUENCE_DEVIATION_PCT, is also 5.0). Named in v146 so the TRAIN
#: score's stop confluence (scenario_rows) uses the same one.
REPLAY_CONFLUENCE_TOLERANCE_PCT = 5.0
_REPLAY_COOLDOWN_BARS = 5


class ReplayHit(NamedTuple):
    """One accepted replay signal. The first two fields are the legacy
    (signal_index, plan) pair, so hit[0] / hit[1] read like the old tuples;
    scenario and target_confluence are what v146's TRAIN row needs."""
    i: int
    plan: object
    scenario: object
    target_confluence: tuple


@dataclasses.dataclass
class _ReplayScope:
    """Per-call constants of one replay, so the helpers stay small."""
    ticker: str
    horizon_key: str
    h: dict
    params: ScanParams
    legacy_gates: bool
    asof: object


def levels_asof(ticker: str, df, bar_index: int, horizon_key: str, cache: dict):
    """(supports, resistances) as they looked at bar_index -- computed on
    df.iloc[:bar_index+1] so the map can never see future bars."""
    key = (ticker, horizon_key, bar_index // LEVEL_REFRESH_BARS)
    if key in cache:
        return cache[key]
    window = df.iloc[:bar_index + 1]
    price = float(window["Close"].iloc[-1])
    result = levels.build_level_map(window, HORIZONS[horizon_key], price)
    cache[key] = result
    return result


def bucket_bar(index: int, horizon_key: str) -> int:
    """The bar whose as-of map replay_scenarios has cached for `index`'s bucket: the first
    bar of that LEVEL_REFRESH_BARS bucket the loop visits (never before warm-up)."""
    return max(MIN_BARS[horizon_key], (index // LEVEL_REFRESH_BARS) * LEVEL_REFRESH_BARS)


def scenarios_at(ticker: str, df, i: int, horizon_key: str, params, cache: dict,
                 dcb_params: dict | None = None):
    """(window, price, supports, resistances, scenarios) at bar i, before any admission gate.

    NO-LOOKAHEAD: reads df.iloc[:i + 1] and levels_asof's as-of map only. The map is the one
    cached for i's bucket, re-split against this bar's own price because the bucket can lag
    (the map's supports/resistances were split against ITS OWN price).
    A caller that asks for one bar out of order must first prime the bucket the way the
    replay loop does: levels_asof(ticker, df, bucket_bar(i, horizon_key), horizon_key, cache).
    `window` is the harness's no-lookahead slice -- the same frame the live scan hands to
    veto_bullish_for (v68); dcb_params=None is the baseline arm and must not pay for the detector.
    """
    h = HORIZONS[horizon_key]
    window = df.iloc[:i + 1]
    price = float(window["Close"].iloc[-1])
    supports, resistances = levels_asof(ticker, df, i, horizon_key, cache)
    all_levels = sorted(supports + resistances, key=lambda lv: lv.price)
    supports = [lv for lv in all_levels if lv.price < price][::-1]
    resistances = [lv for lv in all_levels if lv.price > price]
    floor_pct = levels.atr_floor_pct(window, price, h)
    gate_inputs = scenario_gate_inputs(params, h)
    block_bullish = dcb_params is not None and bool(dead_cat_bounce(window, dcb_params)["detected"])
    scenarios = levels.build_scenarios(
        price, supports, resistances, gate_inputs["min_reward_pct"],
        atr_floor=floor_pct,
        min_stop_distance_pct=gate_inputs["min_stop_distance_pct"],
        max_stop_distance_pct=gate_inputs["max_stop_distance_pct"],
        min_risk_reward=gate_inputs["min_risk_reward"],
        block_bullish=block_bullish)
    return window, price, supports, resistances, scenarios


def _dryup_kept(scenarios, window) -> list:
    """Admit scenarios on the completed as-of window before planning or cooldown."""
    return edge_gates.filter_pullback_dryup(scenarios, window)[0]


def _headroom_kept(scenarios, supports, resistances) -> list:
    """v135: the confluence-scope headroom veto at analyze._apply_headroom's point, on the
    re-split lists the scenarios were just built from. A rejection sets no cooldown."""
    return edge_gates.filter_headroom(scenarios, supports, resistances)[0]


def _replay_params(params: ScanParams | None, gates: dict | None) -> tuple:
    """(params, legacy_gates): a legacy gates dict overrides the admission
    fields of ScanParams, exactly as before the v146 split."""
    if params is None:
        params = ScanParams.from_config()
    if gates is None:
        return params, False
    return dataclasses.replace(
        params,
        min_reward_pct=gates.get("min_reward_pct", params.min_reward_pct),
        min_stop_distance_pct=gates.get("min_stop_distance_pct", params.min_stop_distance_pct),
        max_stop_loss_pct=gates.get("max_stop_distance_pct", params.max_stop_loss_pct),
        min_risk_reward_ratio=gates.get("min_risk_reward", params.min_risk_reward_ratio),
        min_target_confluence_count=gates.get("min_confluence", params.min_target_confluence_count),
    ), True


def _note_blocked(blocked: list | None, index: int, scenario) -> None:
    """v147 record-only: remember a scenario whose plan build found no qualifying target.
    A helper so `replay_scenarios` (C 15, legacy) gains no branch."""
    if blocked is not None:
        blocked.append((index, scenario))


def _bar_scenarios(scope: _ReplayScope, df, i: int, cache: dict, dcb_params: dict | None) -> tuple:
    """(window, price, level_map, scenarios) for bar i after the dry-up and
    headroom gates -- every computation on window = df.iloc[:i+1]
    (scenarios_at / levels_asof enforce the same slice)."""
    window, price, supports, resistances, scenarios = scenarios_at(
        scope.ticker, df, i, scope.horizon_key, scope.params, cache, dcb_params)
    scenarios = _headroom_kept(_dryup_kept(scenarios, window), supports, resistances)
    return window, price, (supports, resistances), scenarios


def _accept_scenario(scope: _ReplayScope, i: int, window, price: float, level_map: tuple,
                     sc, last_accepted: dict, blocked: list | None = None) -> ReplayHit | None:
    """The confluence gate, the per-direction cooldown and the plan build
    for one scenario; None when any of them says no. A scenario whose plan
    build finds no qualifying target is noted in `blocked` (v147)."""
    n_confl, families = levels.count_confirming_strategies(
        window, scope.h, price, sc.take_profit, tolerance_pct=REPLAY_CONFLUENCE_TOLERANCE_PCT)
    if not passes_confluence(n_confl, scope.params):
        return None
    last = last_accepted.get(sc.direction)
    if last is not None and i - last < _REPLAY_COOLDOWN_BARS:
        return None
    plan = build_confluence_plan(
        sc, window, ticker=scope.ticker, horizon_key=scope.horizon_key,
        primary_strategy=primary_strategy_for(sc),
        level_map=level_map,
        # Legacy callers historically used their dict only for
        # scenario admission; target construction still read config.
        # Keep that compatibility while callers migrate to params.
        params=ScanParams.from_config() if scope.legacy_gates else scope.params)
    if plan is None:
        _note_blocked(blocked, i, sc)
        return None          # no qualifying target -> no trade, same as live
    stamp_entry_context(plan, window, asof_row(scope.asof, window.index[-1]))
    return ReplayHit(i, plan, sc, (n_confl, families))


def replay_scenarios_detailed(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                              gates: dict | None = None, dcb_params: dict | None = None,
                              asof=None, blocked: list | None = None) -> list[ReplayHit]:
    """A ReplayHit for every bar where the confluence scan WOULD have emitted
    a plan, under `gates`, with a per-direction cooldown.

    No lookahead: every computation is scoped to `window = df.iloc[:i+1]`
    (or `levels_asof`, which enforces the same slice internally) -- never
    `df.iloc[-1]` or any index beyond `i`.

    `dcb_params`: v68's dead-cat-bounce veto params. Taken directly rather
    than read from config -- the TRAIN grid runs twelve different parameter
    sets in one process, and a config read would make them a global the
    workers fight over. `None` is the baseline arm and must not pay for the
    detector at all.

    `blocked` (v147, record-only): when a list, every scenario whose
    `build_confluence_plan` returned None is appended as `(signal_index,
    scenario)` -- the confluence `no_qualifying_target` block. The return
    value, the cooldown state and every plan are unchanged.
    """
    params, legacy_gates = _replay_params(params, gates)
    scope = _ReplayScope(ticker, horizon_key, HORIZONS[horizon_key], params, legacy_gates, asof)
    cache: dict = {}
    out: list[ReplayHit] = []
    last_accepted: dict = {}   # direction -> bar index
    for i in range(MIN_BARS[horizon_key], len(df)):
        window, price, level_map, scenarios = _bar_scenarios(scope, df, i, cache, dcb_params)
        for sc in scenarios:
            hit = _accept_scenario(scope, i, window, price, level_map, sc, last_accepted,
                                   blocked)
            if hit is not None:
                last_accepted[sc.direction] = i
                out.append(hit)
    return out


def replay_scenarios(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                     gates: dict | None = None,
                     dcb_params: dict | None = None, asof=None,
                     blocked: list | None = None) -> list:
    """(signal_index, TradePlanV2) for every bar where the confluence scan
    WOULD have emitted a plan -- the projection of replay_scenarios_detailed
    that every pre-v146 caller unpacks. Same arguments (v147's `blocked`
    included), same no-lookahead contract."""
    return [(hit.i, hit.plan) for hit in replay_scenarios_detailed(
        ticker, df, horizon_key, params=params, gates=gates, dcb_params=dcb_params, asof=asof,
        blocked=blocked)]


def _aggregate(results: list) -> dict:
    """Win/loss/scratch/timeout/runner stats -- same shape family as
    run_backtest_range.py's `pool()`, but keyed to ExitResult's outcome
    vocabulary (Task 37)."""
    closed = [r for r in results if r.outcome != "not_triggered"]
    ev = [r for r in closed if r.outcome in ("win", "loss")]
    wins = [r for r in ev if r.outcome == "win"]
    runner = {}
    for r in closed:
        if r.runner_outcome:
            runner[r.runner_outcome] = runner.get(r.runner_outcome, 0) + 1
    return {
        "n": len(ev),
        "wins": len(wins),
        "losses": len(ev) - len(wins),
        "scratches": sum(1 for r in closed if r.outcome == "scratch"),
        "timeouts": sum(1 for r in closed if r.outcome == "timeout"),
        "not_triggered": sum(1 for r in results if r.outcome == "not_triggered"),
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([r.r_total for r in closed])) if closed else None,
        "runner": runner,
    }


def _replay_ticker(args) -> dict:
    """All horizons for ONE ticker: {horizon_key: [exit_result, ...]} (see `_replay_ticker_gate_rows`)."""
    return _replay_ticker_gate_rows(args)[0]


def _replay_ticker_gate_rows(args) -> tuple[dict, list]:
    """All horizons for ONE ticker -- the process-pool entry point, so it must
    be module-level and take a single picklable argument.

    Grouped per ticker rather than per (ticker, horizon) pair on purpose: the
    OHLCV frame is the expensive thing to move across a process boundary (~2MB
    for a ten-year daily history), and a per-pair split would ship the same
    frame once per horizon -- ten times the IPC for parallelism a 2-4 core box
    cannot use anyway. At 300-500 tickers there are already far more tasks
    than cores.

    Returns ({horizon_key: [exit_result, ...]}, gate_rows). The horizon travels
    in the RESULT rather than being inferred from completion order, which is what
    makes the pooled path order-independent. `args[11]` (v147, optional) asks for
    the record-only gate rows; without it the row list is always empty. `args[10]`
    is v146's SPY slot and is not read here.
    """
    exits, gate_rows = _replay_exits(args, replay_scenarios)
    return _results_only(exits), gate_rows


def _results_only(exits: dict) -> dict:
    """{horizon_key: [(hit, ExitResult), ...]} -> {horizon_key: [ExitResult, ...]}."""
    return {hk: [result for _, result in pairs] for hk, pairs in exits.items()}


def _replay_exits(args, replay) -> tuple:
    """({horizon_key: [(hit, ExitResult), ...]}, gate_rows) for one ticker --
    the loop _replay_ticker_gate_rows and _replay_ticker_rows share. `replay`
    yields (i, plan) pairs or ReplayHits; both read as hit[0], hit[1].
    args[10] (SPY) is not read here: only the row builder needs it; args[11]
    asks for v147's record-only gate rows."""
    ticker, df, horizons, start, end, gates, scale_out, dcb_params = args[:8]
    asof_df = args[8] if len(args) > 8 else None
    member_spans = args[9] if len(args) > 9 else None
    record = bool(args[11]) if len(args) > 11 else False
    out = {hk: [] for hk in horizons}
    rows: list = []
    for hk in horizons:
        blocked = [] if record else None
        for hit in replay(ticker, df, hk, gates=gates, dcb_params=dcb_params, asof=asof_df,
                          blocked=blocked):
            if not _signal_in_scope(_bar_date(df, hit[0]), start, end, member_spans):
                continue
            out[hk].append((hit, simulate_exit(df, hit[0], hit[1], scale_out=scale_out)))
        if record:
            taken = [(hit[0], hit[1], result) for hit, result in out[hk]]
            rows.extend(_safe_gate_rows(ticker, df, hk, taken, blocked, (start, end, member_spans)))
    return out, rows


def _bar_date(df, index: int) -> str:
    return str(df.index[index].date())


def _safe_gate_rows(ticker, df, horizon_key, taken, blocked, scope) -> list[dict]:
    """Measurement only: a failing row builder costs this (ticker, horizon)'s rows, never the replay."""
    try:
        return _horizon_gate_rows(ticker, df, horizon_key, taken, blocked, scope)
    except Exception as exc:  # noqa: BLE001 -- record-only path must never change replay results
        log.warning("v147 gate rows skipped for %s/%s: %s", ticker, horizon_key, exc, exc_info=True)
        return []


def _horizon_gate_rows(ticker, df, horizon_key, taken, blocked, scope) -> list[dict]:
    """v147 T2 + T3 for one (ticker, horizon): in-scope no-target scenarios, then every replayed plan."""
    start, end, member_spans = scope
    rows = [_no_target_row(ticker, df, horizon_key, i, sc) for i, sc in blocked
            if _signal_in_scope(_bar_date(df, i), start, end, member_spans)]
    rows.extend(_plan_gate_row(ticker, df, horizon_key, i, plan, result) for i, plan, result in taken)
    return rows


def _no_target_row(ticker, df, horizon_key, index, scenario) -> dict:
    """T2: `build_confluence_plan` returned None -- nothing to simulate, so `no-plan`."""
    from swingbot.core.backtesting import blocked_recorder
    return blocked_recorder.gate_row(
        population="train", arm="blocked", source="confluence", ticker=ticker,
        strategy=primary_strategy_for(scenario), horizon=horizon_key, direction=scenario.direction,
        signal_date=_bar_date(df, index), gate="plan_rejected", reason="no_qualifying_target",
        margin=None, cf_status="no-plan", cf_r=None, win=None)


def _plan_gate_row(ticker, df, horizon_key, index, plan, result) -> dict:
    """T3: the record-only shadow of attach_plan_v2's plan-time 2% check on one replayed plan.
    Over the cap -> `blocked`/`risk_cap` (an over-cap counterfactual, never tradable); else `taken`.
    The outcome is the replay's own ExitResult -- nothing is re-simulated."""
    from swingbot.core.backtesting import blocked_recorder
    from swingbot.core.risk_limits import planned_loss_pct
    capped = blocked_recorder.over_cap(plan)
    return blocked_recorder.row_from_exit(
        result, plan, population="train", arm="blocked" if capped else "taken", source="confluence",
        ticker=ticker, strategy=plan.strategy, horizon=horizon_key, direction=plan.direction,
        signal_date=_bar_date(df, index), gate="plan_rejected",
        reason="risk_cap" if capped else None,
        margin=blocked_recorder.risk_cap_margin(plan) if capped else None,
        planned_loss_pct=planned_loss_pct(plan.trigger_price, plan.stop_loss) if capped else None,
        in_sample=False)


def _replay_ticker_rows(args) -> tuple:
    """_replay_ticker_gate_rows plus one v146 TRAIN row per CLOSED exit:
    (exits, rows, gate_rows). args is the same task tuple with the benchmark
    frame in args[10]. The whole SPY frame travels; scenario_rows slices it
    to each signal bar (no lookahead), and nothing here indexes it."""
    # Imported here: scenario_rows imports this module.
    from swingbot.core.backtesting import scenario_rows
    ticker, df = args[0], args[1]
    spy_df = args[10] if len(args) > 10 else None
    exits, gate_rows = _replay_exits(args, replay_scenarios_detailed)
    rows = [scenario_rows.scenario_trade_row(ticker, hk, df, hit, result, spy_df)
            for hk, pairs in exits.items() for hit, result in pairs
            if result.outcome != "not_triggered"]
    return _results_only(exits), rows, gate_rows


def _signal_in_scope(signal_date: str, start, end, member_spans) -> bool:
    """Inside the [start, end] signal window AND, for a point-in-time
    universe, on a date the ticker was actually an index member. The
    membership check runs on the signal bar only -- the exit walk may
    continue past a removal date, same as it may run past `end`."""
    if start and signal_date < start:
        return False
    if end and signal_date > end:
        return False
    return is_member(signal_date, member_spans)


def _resolve_replay_workers(workers: int | None) -> int:
    if workers is not None:
        return max(1, int(workers))
    configured = int(getattr(config, "FETCH_WORKERS", 0) or 0)
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2) - 1)


def _run_replay_tasks(worker, tasks: list, workers, on_ticker_done=None) -> list:
    """worker over every task, sequentially or across the process pool, in
    task order. on_ticker_done(done, total) fires as each result arrives
    (pool.map yields in task order, so the count is monotone but can lag a
    slow early ticker)."""
    n = _resolve_replay_workers(workers)
    if n <= 1 or len(tasks) <= 1:
        return _drain(map(worker, tasks), len(tasks), on_ticker_done)
    with ProcessPoolExecutor(max_workers=n) as pool:
        return _drain(pool.map(worker, tasks), len(tasks), on_ticker_done)


def _drain(results, total: int, on_ticker_done) -> list:
    out = []
    for result in results:
        out.append(result)
        if on_ticker_done is not None:
            on_ticker_done(len(out), total)
    return out


def _replay_with_rows(tasks: list, workers, on_ticker_done) -> tuple:
    """(per-ticker (exits, gate_rows) pairs, flat trade rows): the
    row-collecting twin of the plain run. SPY already rides in args[10]."""
    results = _run_replay_tasks(_replay_ticker_rows, tasks, workers, on_ticker_done)
    return ([(exits, gate_rows) for exits, _, gate_rows in results],
            [row for _, ticker_rows, _ in results for row in ticker_rows])


def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None, workers=None,
                          dcb_params: dict | None = None, asof_map: dict | None = None,
                          membership: dict | None = None, spy_df=None,
                          collect_rows: bool = False, on_ticker_done=None,
                          record_blocked: bool = False) -> dict:
    """frames: {ticker: OHLCV df}. start/end (ISO or None) restrict SIGNAL
    dates -- the exit walk may run past `end`, same convention as
    run_backtest_daterange.

    v47: each ticker is replayed across a process pool, all horizons inside
    one task. Every task is fully independent -- it reads one frame and
    contributes only to its own result lists -- and aggregation happens
    strictly after every task returns, so the output is identical to the
    sequential walk. `workers=1` forces the sequential path; None resolves
    FETCH_WORKERS (0 = auto).

    This is CPU-bound work on in-memory frames with no network and no yfinance
    involvement, so it carries none of the crawl's thread-safety constraints --
    processes are used here purely because the work is GIL-bound Python.

    `membership` ({ticker: [(start, end_exclusive), ...]}, from
    pit_membership.membership_map) masks signals to the dates each ticker was
    an index member; None (every non-`_pit` universe) leaves them unmasked.

    v146: `collect_rows=True` adds "rows" -- one TRAIN row per closed exit
    (scenario_rows.scenario_trade_row) -- and ships `spy_df` to the workers
    in args[10] (None otherwise); "pooled" and "by_horizon" are identical either way.
    `on_ticker_done(done, total)` is called after each ticker returns.

    `record_blocked` (v147): also return "gate_rows", the record-only TRAIN gate
    rows (`_horizon_gate_rows`); "pooled"/"by_horizon" are identical either way.
    """
    horizons = horizons or list(LEGACY_HORIZONS)

    tasks = [
        (ticker, df, horizons, start, end, gates, scale_out, dcb_params,
         asof_map.get(ticker) if asof_map else None,
         membership.get(ticker, []) if membership is not None else None,
         spy_df if collect_rows else None,   # args[10]: v146's SPY frame (row worker only)
         record_blocked)                     # args[11]: v147 record flag
        for ticker, df in frames.items()
    ]

    if collect_rows:
        per_ticker_results, rows = _replay_with_rows(tasks, workers, on_ticker_done)
    else:
        per_ticker_results, rows = _run_replay_tasks(
            _replay_ticker_gate_rows, tasks, workers, on_ticker_done), None
    stats = _scenario_result(per_ticker_results, horizons, record_blocked)
    if rows is not None:
        stats["rows"] = rows
    return stats


def _scenario_result(per_ticker_results, horizons, record_blocked: bool) -> dict:
    """Merge the per-ticker (results, rows) pairs strictly after every task returned."""
    results_by_hz: dict = {hk: [] for hk in horizons}
    gate_rows: list = []
    for per_ticker, rows in per_ticker_results:
        gate_rows.extend(rows)
        for hk, results in per_ticker.items():
            results_by_hz[hk].extend(results)
    all_results = [r for rs in results_by_hz.values() for r in rs]
    out = {"pooled": _aggregate(all_results),
           "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
    if record_blocked:
        out["gate_rows"] = gate_rows
    return out
