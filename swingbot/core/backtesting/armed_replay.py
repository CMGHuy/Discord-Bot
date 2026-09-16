"""v88 A1: the armed confluence replay (spec §3).

A confluence scenario no longer becomes a plan on the bar it appears. It
ARMS, and only a test of its stop level followed by a price reaction there
(market/reaction.py) turns it into a plan -- rebuilt at the confirmation
bar through the same constructor, target selection and gates the live scan
uses, with the stop re-anchored under the reaction.

NO-LOOKAHEAD: every decision at bar j reads df.iloc[:j+1] only.
levels_asof caches its map per 5-bar bucket, built at the FIRST bar that
asks -- so arm_candidates must walk bars in order and fill the cache before
anything reads a bucket out of order (plan construction at a later
confirmation bar, the permutation's random bars).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from swingbot.core.backtesting.backtest_scenarios import levels_asof
from swingbot.core.market import levels, reaction
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.planning.plan_engine import PlanStatus, build_confluence_plan, primary_strategy_for
from swingbot.core.planning.plan_types import record_transition
from swingbot.core.scanning.gating import passes_confluence, scenario_gate_inputs
from swingbot.scan_params import ScanParams

COOLDOWN_BARS = 5                 # replay_scenarios' own per-direction cooldown
STOP_ENTRY_EXPIRY_BARS = 2        # spec §3.4, pre-registered
CONFLUENCE_TOLERANCE_PCT = 5.0    # replay_scenarios' count_confirming_strategies tolerance


@dataclass(frozen=True)
class Cell:
    mode: str      # "M1" | "M2"
    n: int         # arm window, bars
    k: float       # test proximity, ATR
    b: float       # stop buffer, ATR

    @property
    def cell_id(self) -> str:
        return f"{self.mode}-N{self.n}-k{self.k:.2f}-b{self.b:.2f}"


@dataclass(frozen=True)
class ArmCandidate:
    index: int
    direction: str
    level: float       # the scenario's stop price at arm time
    target: float      # the scenario's target 1 at arm time
    scenario: object   # levels.Scenario


@dataclass(frozen=True)
class ArmOutcome:
    status: str                    # confirmed | expired | cancelled_target | cancelled_closed_through | unresolved
    resolved_index: int | None
    kind: str | None = None
    first_test_index: int | None = None


def arm_candidates(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                   level_cache: dict | None = None) -> dict[int, list[ArmCandidate]]:
    """Every bar's arm-eligible scenarios: replay_scenarios' construction
    with ONE gate relaxed -- min_stop_distance_pct is 0 at arm time (spec
    §3.1) and re-applied at confirmation. Walks bars in order, which is
    what makes `level_cache` safe to read out of order afterwards."""
    if params is None:
        params = ScanParams.from_config()
    cache = {} if level_cache is None else level_cache
    h = HORIZONS[horizon_key]
    gates = scenario_gate_inputs(params, h)
    out: dict[int, list[ArmCandidate]] = {}
    for i in range(MIN_BARS[horizon_key], len(df)):
        window = df.iloc[:i + 1]
        price = float(window["Close"].iloc[-1])
        supports, resistances = levels_asof(ticker, df, i, horizon_key, cache)
        all_levels = sorted(supports + resistances, key=lambda lv: lv.price)
        supports = [lv for lv in all_levels if lv.price < price][::-1]
        resistances = [lv for lv in all_levels if lv.price > price]
        scenarios = levels.build_scenarios(
            price, supports, resistances, gates["min_reward_pct"],
            atr_floor=levels.atr_floor_pct(window, price, h),
            min_stop_distance_pct=0.0,
            max_stop_distance_pct=gates["max_stop_distance_pct"],
            min_risk_reward=gates["min_risk_reward"])
        found = []
        for sc in scenarios:
            n_confl, _ = levels.count_confirming_strategies(
                window, h, price, sc.take_profit, tolerance_pct=CONFLUENCE_TOLERANCE_PCT)
            if passes_confluence(n_confl, params):
                found.append(ArmCandidate(i, sc.direction, float(sc.stop_loss),
                                          float(sc.take_profit), sc))
        if found:
            out[i] = found
    return out


def walk_arm(bars: reaction.Bars, atr_values: np.ndarray, cand: ArmCandidate,
             cell: Cell) -> ArmOutcome:
    """Walk one armed scenario across [i, i + N] (spec §3.2).

    Per bar t, in this order: the target check (bars after the arm bar
    only; a bar that both reaches the target and reacts is a cancel), the
    test, the reaction, then the close-through-not-reclaimed cancel. Every
    check at t reads bars <= t.
    """
    n_bars = len(bars.close)
    i, last = cand.index, cand.index + cell.n
    bull = cand.direction == "bullish"
    first_test = None
    breach_start = None
    for t in range(i, min(last, n_bars - 1) + 1):
        if t > i and ((bars.high[t] >= cand.target) if bull else (bars.low[t] <= cand.target)):
            return ArmOutcome("cancelled_target", t)
        tested_now = reaction.is_test(bars, t, cand.level, cand.direction, cell.k, atr_values[t])
        if tested_now and first_test is None:
            first_test = t
        tested_prev = t - 1 >= i and reaction.is_test(
            bars, t - 1, cand.level, cand.direction, cell.k, atr_values[t - 1])
        if first_test is not None:
            kind = reaction.reaction_kind(bars, t, cand.level, cand.direction,
                                          tested_now=tested_now, tested_prev=tested_prev,
                                          floor_index=i)
            if kind is not None:
                return ArmOutcome("confirmed", t, kind, first_test)
        through = bars.close[t] < cand.level if bull else bars.close[t] > cand.level
        if through:
            if breach_start is None:
                breach_start = t
            elif t - breach_start >= reaction.RECLAIM_BARS:
                return ArmOutcome("cancelled_closed_through", t)
        else:
            breach_start = None
    if last <= n_bars - 1:
        return ArmOutcome("expired", last)
    return ArmOutcome("unresolved", None)


def plan_at(ticker: str, df, horizon_key: str, cand: ArmCandidate, *, j: int,
            first_test_index: int, kind: str, cell: Cell, bars: reaction.Bars,
            atr_values: np.ndarray, params: ScanParams, level_map_at, confluence_at):
    """The plan an armed scenario becomes if bar j is its confirmation
    (spec §3.3-3.4). Returns (plan, "issued") or (None, the gate that
    refused it). A plan is never adjusted to fit a gate.

    `level_map_at(j)` -> (supports, resistances) as of bar j; `confluence_at
    (j, entry, target)` -> confirming-strategy count. Injected so the
    permutation (AR6) and the tests share this exact path.
    """
    h = HORIZONS[horizon_key]
    gates = scenario_gate_inputs(params, h)
    bull = cand.direction == "bullish"
    atr_j = float(atr_values[j])
    if not np.isfinite(atr_j):
        return None, "regate_invalid_atr"

    if bull:
        stop = min(cand.level, float(bars.low[first_test_index:j + 1].min())) - cell.b * atr_j
    else:
        stop = max(cand.level, float(bars.high[first_test_index:j + 1].max())) + cell.b * atr_j
    market = cell.mode == "M2" and kind in (reaction.R2, reaction.R3)
    if market:
        entry = float(bars.close[j])
    else:
        entry = float(bars.high[j] if bull else bars.low[j])

    if (bull and stop >= entry) or (not bull and stop <= entry):
        return None, "regate_stop_distance"
    risk_pct = abs(entry - stop) / entry * 100.0
    if risk_pct < gates["min_stop_distance_pct"] or risk_pct > gates["max_stop_distance_pct"]:
        return None, "regate_stop_distance"

    supports, resistances = level_map_at(j)
    all_levels = sorted(list(supports) + list(resistances), key=lambda lv: lv.price)
    supports = [lv for lv in all_levels if lv.price < entry][::-1]
    resistances = [lv for lv in all_levels if lv.price > entry]
    scenario = dataclasses.replace(cand.scenario, entry=entry, market_price=entry,
                                   stop_loss=stop, stop_distance_pct=risk_pct)
    plan = build_confluence_plan(
        scenario, df.iloc[:j + 1], ticker=ticker, horizon_key=horizon_key,
        primary_strategy=primary_strategy_for(cand.scenario),
        level_map=(supports, resistances), params=params)
    if plan is None:
        return None, "regate_no_target"
    if abs(plan.tp1 - entry) / entry * 100.0 < gates["min_reward_pct"]:
        return None, "regate_reward"
    if not passes_confluence(confluence_at(j, entry, plan.tp1), params):
        return None, "regate_confluence"

    plan = dataclasses.replace(
        plan, entry_type="market" if market else "stop_entry", trigger_price=entry,
        entry_price=entry if market else None,
        expiry_bars=plan.expiry_bars if market else STOP_ENTRY_EXPIRY_BARS,
        status=PlanStatus.PENDING, status_history=[])
    if market:
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=plan.created_at)
    return plan, "issued"


def build_armed_plan(ticker: str, df, horizon_key: str, cand: ArmCandidate,
                     outcome: ArmOutcome, cell: Cell, *, bars, atr_values, params,
                     level_map_at, confluence_at):
    """plan_at for a real confirmation."""
    return plan_at(ticker, df, horizon_key, cand, j=outcome.resolved_index,
                   first_test_index=outcome.first_test_index, kind=outcome.kind, cell=cell,
                   bars=bars, atr_values=atr_values, params=params,
                   level_map_at=level_map_at, confluence_at=confluence_at)
