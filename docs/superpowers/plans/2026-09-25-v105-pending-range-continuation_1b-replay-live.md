# v105 PENDING daily range continuation — Part 1b: replay and live source (Tasks 4–5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Header, global constraints, review focus and parallelisation live in
`2026-09-25-v105-pending-range-continuation_0-index.md`. Read them first. Part 1a (Tasks 1–3) must be done first; the file map is in Part 1a.

# Phase 1 — Candidate and PENDING lifecycle (continued)

### Task 4: Replay trigger, gap and expiry through the shared source

**Files:**
- Create: `swingbot/core/backtesting/range_replay.py`
- Test: `tests/backtesting/test_pending_range_replay.py`

**Interfaces:**
- Consumes: `range_candidate`, `min_bars`, `ATR_PERIOD` (Task 2);
  `range_source.screen`, `first_issuable`, `range_plan_at` (Task 3);
  `exit_sim.simulate_exit(df, signal_index, plan, *, scale_out=False, max_holding_days=None) -> ExitResult`;
  `acceptance.planned_rr(entry, stop, target)`; `plan_types.plan_to_dict`.
- Produces:
  - `EXIT_SCALE_OUT = True`, `EXIT_LIMITATION: str`, `SCORABLE = ("win","loss","scratch","timeout","not_triggered")`
  - `@dataclass(frozen=True) ReplayRow(ticker, horizon_key, n, d, require_pressure, direction, signal_index, signal_date, range_start, identity, pressure, outcome, r_multiple, planned_rr, entry_date, entry_price, gap_fill, close_back_inside, entry_bar_stop_touch, plan)` with `.to_dict()`
  - `@dataclass ReplayResult(rows, counts: Counter, limitation)`
  - `candidates_by_index(ticker, df, n) -> dict[int, RangeCandidate]`
  - `entry_bar_diagnostics(df, entry_index, plan, candidate) -> dict`
  - `resolve_outcome(df, i, plan, candidate) -> dict` with keys
    `outcome, r_multiple, entry_index, entry_date, entry_price, gap_fill, close_back_inside, entry_bar_stop_touch, unresolved`
  - `replay_ranges(ticker, df, horizons, *, n, d, require_pressure, params=None, candidates=None, build_cache=None) -> ReplayResult`
  - outcomes beyond exit_sim's: `cancelled_risk_cap`, `unresolved`

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/test_pending_range_replay.py`:

```python
"""v105 Task 4: daily replay through the shared live builder."""
import pytest

from swingbot.core.backtesting import range_replay as rr
from swingbot.core.market import range_candidate as rc
from swingbot.core.planning import range_source
from swingbot.core.planning.plan_types import plan_to_dict
from tests.market.range_fixtures import FLAT, fixed_levels, long_frame, short_frame

# Bars written in LONG terms; the trigger sits near 106.15, the stop near
# 104.85, TP1 near 108.8 and the risk-cap fill near 107.0.
TRIGGER_CLOSE_INSIDE = (105.8, 106.6, 105.6, 105.9)
GAP_THROUGH = (106.8, 107.2, 106.5, 107.0)
GAP_PAST_CAP = (108.0, 108.3, 107.6, 108.1)
BOTH_TOUCHED = (105.8, 109.5, 104.5, 106.0)
BOOM = (106.0, 140.0, 105.9, 139.0)


@pytest.fixture(autouse=True)
def _levels(monkeypatch):
    monkeypatch.setattr(range_source, "range_target_levels", fixed_levels)


def _issued_at_end(extra, frame_fn=long_frame):
    i = len(frame_fn()) - 1
    df = frame_fn(extra)
    build = range_source.range_plan_at(df.iloc[: i + 1], ticker="AAA", horizon_key="4w", n=20)
    assert build.plan is not None, build.reason
    return df, i, build


def _resolve(extra, frame_fn=long_frame):
    df, i, build = _issued_at_end(extra, frame_fn)
    return i, build, rr.resolve_outcome(df, i, build.plan, build.candidate)


def test_intrabar_trigger_that_closes_back_inside():
    i, build, out = _resolve([TRIGGER_CLOSE_INSIDE] + [FLAT] * 3)
    assert out["entry_index"] == i + 1
    assert out["entry_price"] == build.plan.trigger_price
    assert (out["close_back_inside"], out["gap_fill"]) == (True, False)


def test_gap_through_trigger_fills_at_the_open():
    _, _, out = _resolve([GAP_THROUGH] + [FLAT] * 3)
    assert out["entry_price"] == 106.8
    assert (out["gap_fill"], out["close_back_inside"]) == (True, False)


def test_gap_past_the_risk_cap_is_a_paper_cancellation():
    _, _, out = _resolve([GAP_PAST_CAP] + [FLAT] * 3)
    assert (out["outcome"], out["r_multiple"]) == ("cancelled_risk_cap", None)
    assert out["gap_fill"] is True


def test_no_fill_inside_the_window():
    _, _, out = _resolve([FLAT] * 7)
    assert (out["outcome"], out["entry_index"], out["r_multiple"]) == ("not_triggered", None, None)


def test_fifth_session_fill_counts():
    i, _, out = _resolve([FLAT] * 4 + [TRIGGER_CLOSE_INSIDE] + [FLAT] * 2)
    assert out["entry_index"] == i + 5


def test_sixth_session_is_refused():
    _, _, out = _resolve([FLAT] * 5 + [TRIGGER_CLOSE_INSIDE] + [FLAT])
    assert out["outcome"] == "not_triggered"


def test_entry_bar_both_touched_is_unresolved():
    _, _, out = _resolve([BOTH_TOUCHED] + [FLAT] * 2)
    assert (out["outcome"], out["r_multiple"]) == ("unresolved", None)
    assert out["entry_bar_stop_touch"] is True


def test_short_gap_mirrors_long():
    _, _, out = _resolve([GAP_THROUGH] + [FLAT] * 3, frame_fn=short_frame)
    assert out["entry_price"] == pytest.approx(200 - 106.8)
    assert out["gap_fill"] is True


def test_overlap_suppression_one_plan_per_range():
    res = rr.replay_ranges("AAA", long_frame([FLAT] * 6), ("4w",), n=20, d=0.75, require_pressure=True)
    assert res.counts["issued"] >= 1
    assert res.counts["rearm_blocked"] >= 1
    for earlier, later in zip(res.rows, res.rows[1:]):
        assert later.range_start > earlier.signal_date


def test_replay_plans_equal_the_live_builder_on_the_truncated_frame():
    df = long_frame([FLAT] * 6)
    res = rr.replay_ranges("AAA", df, ("4w",), n=20, d=0.75, require_pressure=True)
    assert res.rows
    for row in res.rows:
        live = range_source.range_plan_at(df.iloc[: row.signal_index + 1], ticker="AAA",
                                          horizon_key=row.horizon_key, n=20)
        want, got = plan_to_dict(live.plan), dict(row.plan)
        want.pop("plan_id"), got.pop("plan_id")
        assert got == want


def test_replay_candidates_equal_truncated_calls():
    df = long_frame([FLAT] * 3 + [BOOM] * 3)
    for n in rc.N_GRID:
        cached = rr.candidates_by_index("AAA", df, n)
        for i in range(rc.min_bars(n) - 1, len(df) - 1):
            assert cached.get(i) == rc.range_candidate(df.iloc[: i + 1], n=n, ticker="AAA")


def test_pressure_arms_share_plan_arithmetic():
    df = long_frame([FLAT] * 6)
    cands, cache = rr.candidates_by_index("AAA", df, 20), {}
    kw = dict(n=20, d=0.75, candidates=cands, build_cache=cache)
    off = rr.replay_ranges("AAA", df, ("4w",), require_pressure=False, **kw)
    on = rr.replay_ranges("AAA", df, ("4w",), require_pressure=True, **kw)
    off_by_key = {(r.horizon_key, r.signal_date): r for r in off.rows}
    shared = [r for r in on.rows if (r.horizon_key, r.signal_date) in off_by_key]
    assert shared
    for row in shared:
        twin = off_by_key[(row.horizon_key, row.signal_date)]
        assert (row.plan, row.outcome, row.r_multiple) == (twin.plan, twin.outcome, twin.r_multiple)


def test_limitation_is_explicit_in_the_output():
    res = rr.replay_ranges("AAA", long_frame([FLAT] * 6), ("4w",), n=20, d=0.75, require_pressure=True)
    assert "entry_index + 1" in res.limitation and "NOT measured" in res.limitation
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_replay.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'swingbot.core.backtesting.range_replay'`.

- [ ] **Step 3: Implement the replay**

`swingbot/core/backtesting/range_replay.py`:

```python
"""v105: daily replay of the range source through the shared live builder.

Clock: the candidate at index i reads bars 0..i, which are completed through
t-1 for session t = i+1. Proximity is judged against Close[i], the price a
user sees when placing the overnight stop-market order. exit_sim examines
fills and expiry on bars i+1..i+5, counted the way PlanManager counts them.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from swingbot.core.backtesting.acceptance import planned_rr
from swingbot.core.market.indicators import atr
from swingbot.core.market.range_candidate import ATR_PERIOD, min_bars, range_candidate
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.planning.range_source import first_issuable, range_plan_at, screen
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

EXIT_SCALE_OUT = True
EXIT_LIMITATION = (
    "exit_sim walks exits from entry_index + 1: the fill bar itself is never "
    "stop/target-checked, so entry-day stops are NOT measured here. "
    "close_back_inside and unresolved are diagnostics, not outcomes.")
SCORABLE = ("win", "loss", "scratch", "timeout", "not_triggered")


@dataclass(frozen=True)
class ReplayRow:
    ticker: str
    horizon_key: str
    n: int
    d: float
    require_pressure: bool
    direction: str
    signal_index: int
    signal_date: str
    range_start: str
    identity: str
    pressure: bool
    outcome: str
    r_multiple: float | None
    planned_rr: float | None
    entry_date: str | None
    entry_price: float | None
    gap_fill: bool
    close_back_inside: bool | None
    entry_bar_stop_touch: bool | None
    plan: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReplayResult:
    rows: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    limitation: str = EXIT_LIMITATION


def candidates_by_index(ticker, df, n) -> dict:
    """{i: RangeCandidate} for every bar that leaves at least one bar to fill.
    ATR comes off one full-series pass; test_replay_candidates_equal_truncated_calls
    proves that equals the truncated computation."""
    atr_series = atr(df, ATR_PERIOD)
    out = {}
    for i in range(min_bars(n) - 1, len(df) - 1):
        cand = range_candidate(df.iloc[: i + 1], n=n, ticker=ticker, atr_value=float(atr_series.iloc[i]))
        if cand is not None:
            out[i] = cand
    return out


def entry_bar_diagnostics(df, entry_index, plan, candidate) -> dict:
    if entry_index is None:
        return {"gap_fill": False, "close_back_inside": None,
                "entry_bar_stop_touch": None, "unresolved": False}
    bar = df.iloc[entry_index]
    if plan.direction == "bullish":
        gap = bar["Open"] > plan.trigger_price
        back = bar["Close"] < candidate.upper
        stop_touch, target_touch = bar["Low"] <= plan.stop_loss, bar["High"] >= plan.tp1
    else:
        gap = bar["Open"] < plan.trigger_price
        back = bar["Close"] > candidate.lower
        stop_touch, target_touch = bar["High"] >= plan.stop_loss, bar["Low"] <= plan.tp1
    return {"gap_fill": bool(gap), "close_back_inside": bool(back),
            "entry_bar_stop_touch": bool(stop_touch),
            "unresolved": bool(stop_touch and target_touch)}


def resolve_outcome(df, i, plan, candidate) -> dict:
    """Outcome of one issued plan. Mirrors PlanManager._step_pending: a fill
    whose planned loss exceeds the hard cap is a paper cancellation. A fill
    bar touching both the stop and TP1 is `unresolved`, never guessed."""
    result = simulate_exit(df, i, plan, scale_out=EXIT_SCALE_OUT)
    diag = entry_bar_diagnostics(df, result.entry_index, plan, candidate)
    outcome, r = result.outcome, result.r_total
    if result.entry_index is not None:
        if planned_loss_pct(result.entry_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT:
            outcome, r = "cancelled_risk_cap", None
        elif diag["unresolved"]:
            outcome, r = "unresolved", None
    if outcome not in SCORABLE[:4]:
        r = None
    entry_date = None if result.entry_index is None else df.index[result.entry_index].date().isoformat()
    return {"outcome": outcome, "r_multiple": r, "entry_index": result.entry_index,
            "entry_date": entry_date, "entry_price": result.entry_price, **diag}


def _memo_build(frame, cand, i, params, cache):
    def build(hk):
        key = (cand.n, i, hk)
        if key not in cache:
            cache[key] = range_plan_at(frame, ticker=cand.ticker, horizon_key=hk, n=cand.n,
                                       params=params, candidate=cand, plan_id=f"{cand.identity}:{hk}")
        return cache[key]
    return build


def _row(df, i, hk, plan, cand, *, d, require_pressure) -> ReplayRow:
    plan_dict = plan_to_dict(plan)            # before simulate_exit touches anything
    out = resolve_outcome(df, i, plan, cand)
    return ReplayRow(
        ticker=plan.ticker, horizon_key=hk, n=cand.n, d=d, require_pressure=require_pressure,
        direction=cand.direction, signal_index=i, signal_date=cand.asof,
        range_start=cand.range_start, identity=cand.identity, pressure=cand.pressure,
        outcome=out["outcome"], r_multiple=out["r_multiple"],
        planned_rr=planned_rr(plan.trigger_price, plan.stop_loss, plan.tp1),
        entry_date=out["entry_date"], entry_price=out["entry_price"],
        gap_fill=out["gap_fill"], close_back_inside=out["close_back_inside"],
        entry_bar_stop_touch=out["entry_bar_stop_touch"], plan=plan_dict)


def replay_ranges(ticker, df, horizons, *, n, d, require_pressure, params=None,
                  candidates=None, build_cache=None) -> ReplayResult:
    """One (N, d, pressure) arm. Pass one horizon for per-horizon measurement,
    or every horizon in HORIZONS order for the live path, which issues the
    first horizon whose plan builds. Share `candidates` (per n) and
    `build_cache` across arms, so a shared candidate's plan is one object."""
    candidates = candidates if candidates is not None else candidates_by_index(ticker, df, n)
    build_cache = {} if build_cache is None else build_cache
    result, last_created = ReplayResult(), None
    for i in sorted(candidates):
        cand = candidates[i]
        blocked = screen(cand, last_created, require_pressure)
        if blocked:
            result.counts[blocked] += 1
            continue
        frame = df.iloc[: i + 1]
        issued = first_issuable(frame, cand, horizons, price=float(df["Close"].iloc[i]), d=d,
                                params=params, counts=result.counts,
                                build=_memo_build(frame, cand, i, params, build_cache))
        if issued is None:
            continue
        hk, plan = issued
        last_created = cand.asof
        result.counts["issued"] += 1
        result.rows.append(_row(df, i, hk, plan, cand, d=d, require_pressure=require_pressure))
    return result
```

`SCORABLE[:4]` is the closed outcomes (`win, loss, scratch, timeout`). Only
they carry an R.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_replay.py`
Expected: `0 failed`, `0 xfailed`. If `test_pressure_arms_share_plan_arithmetic`
fails on `assert shared`, the fixture issued on a different bar per arm. Print
`off.rows` / `on.rows` signal dates and fix the **fixture** (`range_fixtures.py`),
never the replay.

- [ ] **Step 5: Check complexity and commit**

```bash
python -m radon cc -s -n C swingbot/core/backtesting/range_replay.py
git status --short
git add swingbot/core/backtesting/range_replay.py tests/backtesting/test_pending_range_replay.py
git commit -m "feat(v105): range replay -- worse-of fills, 5-session expiry, rearm identity, entry-bar diagnostics"
```

**Verification:** narrow run, radon, and the no-lookahead cases
(`test_replay_candidates_equal_truncated_calls`,
`test_replay_plans_equal_the_live_builder_on_the_truncated_frame`) green.

### Task 5: Wire a masked watchlist source and reliable PENDING notices

**Files:**
- Modify: `swingbot/config.py` (three `Field`s next to `STRATEGY_ALERTS_MODE`, around L823; `_cast` branch around L1085)
- Modify: `.env.example` (after `STRATEGY_ALERTS_LIVE_STRATEGIES=`, around L194)
- Modify: `swingbot/core/planning/plan_manager.py:59-61` (`NOTICE_EVENTS`)
- Modify: `swingbot/core/presentation/instructions.py` (`instruction_for`, cancel branch at ~L256)
- Create: `swingbot/core/scanning/range_pass.py`
- Create: `swingbot/core/scanning/range_embeds.py`
- Modify: `swingbot/core/scanning/scan_run.py` (new `_maybe_run_range_pass`; call after L938)
- Test: `tests/scanning/test_pending_range_alerts.py`
- Test: `tests/test_config_flags.py` (one new test)

**Interfaces:**
- Consumes: Tasks 2–3 (`range_candidate`, `screen`, `first_issuable`, `SOURCE_ID`, `N_GRID`, `D_GRID`);
  `strategy_pass.completed_frame(df, now)`; `data.get_current_price_detail(ticker, ttl_seconds=15, *, allow_stale=True) -> PriceQuote | None`;
  `TradeLog.log_trade(...)` / `open_trade_for_ticker(ticker)`; `PlanStore.add/all/update/get`;
  `instructions.approx_last_trigger_session(created_at, expiry_bars)`.
- Produces:
  - `plan_manager.RANGE_PENDING = "range_pending"` (member of `NOTICE_EVENTS`)
  - `range_pass.RangeCell(n, d, require_pressure)` with `.cell_id` (`"N20-d0.50-P1"`)
  - `range_pass.parse_cell(text) -> RangeCell | None`
  - `range_pass.fresh_quote(ticker) -> float | None`
  - `range_pass.RangePassResult(plans, shadow, alerts, counts)`, where `shadow` is a list of `(plan, cell_id, quote)`
  - `range_pass.run_range_pass(tickers, fresh_data, *, now, mode, cell, live_directions, trade_log, plan_store, sector_of, quote_fn=fresh_quote, params=None) -> RangePassResult`
  - `range_pass.group_by_sector(plans, sector_of) -> list[dict]` (`{"sector", "ranked": False, "members"}`)
  - `range_embeds.build_range_alert_embed(plan, group) -> discord.Embed`
  - `scan_run._maybe_run_range_pass(*, tickers, fresh_data, sector_of_ticker, trade_log, alerts, require_confirmation) -> dict`
  - config `RANGE_ALERTS_MODE` (`off|shadow|live`, default `off`), `RANGE_ALERTS_CELL` (default `""`), `RANGE_ALERTS_LIVE_DIRECTIONS` (default `""` = none)

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_pending_range_alerts.py`:

```python
"""v105 Task 5: masked range source, PENDING notices and broker divergence."""
import asyncio
import types
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.market import range_candidate as rc
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning import range_source
from swingbot.core.planning.plan_manager import Delivery, PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import PlanStatus, record_transition
from swingbot.core.planning.range_builder import range_prices
from swingbot.core.presentation.instructions import CANCEL, PLACE, instruction_for
from swingbot.core.scanning import execution_embeds, lifecycle_embeds, scan_run
from swingbot.core.scanning import range_pass as rp
from swingbot.core.scanning.lifecycle_embeds import notify_plan_events
from tests.market.range_fixtures import fixed_levels, long_frame
from tests.planning.test_plan_engine_model import _plan
from tests.scanning.test_execution_feed_routing import FakeChannel

NOW = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)   # after the close
CELL = rp.RangeCell(20, 0.75, True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    monkeypatch.setattr(range_source, "range_target_levels", fixed_levels)
    calls = []
    trade_log = types.SimpleNamespace(open_trade_for_ticker=lambda t: None,
                                      log_trade=lambda **kw: calls.append(kw) or "t1")
    return types.SimpleNamespace(store=PlanStore(), trade_log=trade_log, calls=calls)


def _trigger(frame):
    cand = rc.range_candidate(frame, n=20, ticker="AAA")
    return range_prices(cand, "2w")[0].trigger


def _run(env, frame, *, quote, mode="live", directions=("bullish",), cell=CELL, tickers=("AAA",)):
    return rp.run_range_pass(list(tickers), {t: frame for t in tickers}, now=NOW, mode=mode,
                             cell=cell, live_directions=set(directions), trade_log=env.trade_log,
                             plan_store=env.store, sector_of=lambda t: "Tech",
                             quote_fn=lambda t: quote)


def _issue(env):
    frame = long_frame()
    trig = _trigger(frame)
    [plan] = _run(env, frame, quote=trig - 0.3).plans
    return frame, trig, plan


def test_pre_break_notice_is_queued_for_the_feed(env):
    frame, trig, plan = _issue(env)
    stored = env.store.get(plan.plan_id)
    assert (stored.status, stored.entry_type, stored.horizon_key) == (PlanStatus.PENDING, "stop_entry", "2w")
    assert stored.pending_notice["transition"] == pm.RANGE_PENDING
    assert stored.first_seen_price == pytest.approx(trig - 0.3)
    assert env.calls[0]["source"] == rc.SOURCE_ID
    assert env.calls[0]["entry"] == stored.trigger_price
    instr = instruction_for(stored, PlanEvent(stored.plan_id, pm.RANGE_PENDING, {}))
    assert instr.verb == PLACE and "BUY STOP" in instr.headline
    assert any("never places" in line for line in instr.lines)


def test_research_alert_rides_the_existing_alert_path(env):
    frame = long_frame()
    res = _run(env, frame, quote=_trigger(frame) - 0.3)
    [(embed, chart, plan, simple)] = res.alerts
    assert (chart, simple) == (None, None)
    assert plan is res.plans[0]
    assert "PENDING" in embed.title


def test_already_crossed_refusal(env):
    frame = long_frame()
    res = _run(env, frame, quote=_trigger(frame) + 0.01)
    assert res.plans == [] and res.counts["proximity_crossed"] == 1


def test_stale_quote_refuses_notice(env, monkeypatch):
    res = _run(env, long_frame(), quote=None)
    assert res.plans == [] and res.counts["proximity_no_quote"] == 1
    from swingbot.core.marketdata import data
    seen = {}

    def fake(ticker, ttl_seconds=15, *, allow_stale=True):
        seen["allow_stale"] = allow_stale
        return data.PriceQuote(price=105.9, stale=True)

    monkeypatch.setattr(data, "get_current_price_detail", fake)
    assert rp.fresh_quote("AAA") is None
    assert seen["allow_stale"] is False


def test_disallowed_direction_stays_shadow(env):
    frame = long_frame()
    res = _run(env, frame, quote=_trigger(frame) - 0.3, directions=())
    assert res.plans == [] and env.store.all() == [] and env.calls == []
    assert len(res.shadow) == 1


def test_shadow_mode_touches_nothing(env):
    frame = long_frame()
    res = _run(env, frame, quote=_trigger(frame) - 0.3, mode="shadow")
    assert (res.plans, res.alerts, env.store.all(), env.calls) == ([], [], [], [])
    assert {cell_id for _, cell_id, _ in res.shadow} <= {f"N{n}-d0.75-P0" for n in rc.N_GRID}
    assert res.shadow


def test_fifth_session_expiry_notice(env):
    _, trig, plan = _issue(env)
    manager = PlanManager(env.store, lambda t: trig - 0.5, bar_count_fn=lambda t, created: 6)
    events = manager.poll()
    assert [e.transition for e in events] == ["cancelled_expired"]
    instr = instruction_for(env.store.get(plan.plan_id), events[0])
    assert instr.verb == CANCEL and f"{plan.trigger_price:.2f}" in instr.headline


def test_new_range_rearm_only(env):
    frame, trig, plan = _issue(env)
    assert _run(env, frame, quote=trig - 0.3).counts["open_range_plan"] == 1
    record_transition(plan, PlanStatus.CANCELLED, reason="expired")
    env.store.update(plan)
    again = _run(env, frame, quote=trig - 0.3)
    assert again.plans == [] and again.counts["rearm_blocked"] == 1


def test_same_sector_grouping_is_unranked_and_deterministic():
    def p(ticker):
        return types.SimpleNamespace(ticker=ticker, plan_id=ticker)

    sectors = {"GS": "Financials", "MS": "Financials", "JPM": "Financials"}
    groups = rp.group_by_sector([p("MS"), p("XYZ"), p("GS"), p("JPM")], sectors.get)
    assert groups[0]["sector"] == "Financials" and groups[0]["ranked"] is False
    assert [m.ticker for m in groups[0]["members"]] == ["GS", "JPM", "MS"]
    assert [(g["sector"], [m.ticker for m in g["members"]]) for g in groups[1:]] == [(None, ["XYZ"])]


def test_same_sector_alert_lists_the_alternatives(env):
    frame = long_frame()
    res = _run(env, frame, quote=_trigger(frame) - 0.3, tickers=("AAA", "BBB"))
    embeds = {plan.ticker: embed for embed, _, plan, _ in res.alerts}
    field = next(f for f in embeds["AAA"].fields if "unranked" in f.name)
    assert "BBB" in field.value and "independent" in field.value


def test_failed_send_is_retried_until_acknowledged(env, monkeypatch):
    _, _, plan = _issue(env)
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(lifecycle_embeds, "_last_warned", {})
    feed, history = FakeChannel(), FakeChannel()
    feed.fail = history.fail = True
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "222")
    bot = types.SimpleNamespace(get_channel=lambda cid: {"111": feed, "222": history}.get(str(cid)))
    manager = PlanManager(PlanStore(), lambda t: None)
    events = manager.resend_notices()
    assert [e.transition for e in events] == [pm.RANGE_PENDING]
    assert asyncio.run(notify_plan_events(bot, events)) == []
    feed.fail = history.fail = False
    deliveries = asyncio.run(notify_plan_events(bot, manager.resend_notices()))
    assert deliveries == [Delivery(plan.plan_id, "notice", pm.RANGE_PENDING)]
    monkeypatch.setattr(pm, "_MANAGER", manager)
    pm.ack_notified(deliveries)
    assert PlanStore().get(plan.plan_id).pending_notice is None
    assert manager.resend_notices() == []


def test_gap_fill_risk_cap_marks_broker_status_unknown(env):
    _, _, plan = _issue(env)
    gap_price = plan.entry_context["risk_cap_fill"] + 1.0
    [event] = PlanManager(env.store, lambda t: gap_price).poll()
    assert event.transition == "cancelled_risk_cap"
    instr = instruction_for(env.store.get(plan.plan_id), event)
    assert instr.verb == CANCEL and "EXIT" in instr.headline
    assert any("UNKNOWN" in w for w in instr.warnings)
    assert not any("never filled" in line for line in instr.lines)


def test_confluence_risk_cap_text_is_out_of_scope_and_unchanged():
    plan = _plan(source="confluence", entry_type="stop_entry", status="CANCELLED")
    detail = {"entry_price": 103.0, "stop_loss": 95.0, "planned_loss_pct": 7.8,
              "max_planned_loss_pct": 2.0}
    instr = instruction_for(plan, PlanEvent("p1", "cancelled_risk_cap", detail))
    assert any("never filled" in line for line in instr.lines)


@pytest.mark.parametrize("text, cell", [
    ("N20-d0.50-P1", rp.RangeCell(20, 0.5, True)),
    ("N10-d0.25-P0", rp.RangeCell(10, 0.25, False)),
    ("", None), ("N12-d0.50-P1", None), ("N20-d0.40-P1", None), ("junk", None), (None, None)])
def test_parse_cell(text, cell):
    assert rp.parse_cell(text) == cell


def test_mode_off_does_no_work(monkeypatch):
    monkeypatch.setattr(config, "RANGE_ALERTS_MODE", "off")

    def boom(*a, **k):
        raise AssertionError("range pass must not run when off")

    monkeypatch.setattr(rp, "run_range_pass", boom)
    alerts = []
    out = scan_run._maybe_run_range_pass(tickers=["AAA"], fresh_data={}, sector_of_ticker={},
                                         trade_log=None, alerts=alerts, require_confirmation=True)
    assert out == {"range_plans": 0, "range_shadow": 0} and alerts == []


def test_manual_check_and_missing_cell_force_shadow(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))   # Task 7 writes shadow state here
    monkeypatch.setattr(config, "RANGE_ALERTS_MODE", "live")
    monkeypatch.setattr(config, "RANGE_ALERTS_LIVE_DIRECTIONS", "bullish")
    monkeypatch.setattr(rp, "run_range_pass",
                        lambda *a, **k: seen.append(k["mode"]) or rp.RangePassResult())
    for cell, confirm in (("N20-d0.50-P1", False), ("", True)):
        monkeypatch.setattr(config, "RANGE_ALERTS_CELL", cell)
        scan_run._maybe_run_range_pass(tickers=[], fresh_data={}, sector_of_ticker={},
                                       trade_log=None, alerts=[], require_confirmation=confirm)
    assert seen == ["shadow", "shadow"]
```

Append to `tests/test_config_flags.py`:

```python
def test_v105_range_alert_fields():
    fields = {f.key: f for f in config.FIELDS}
    mode = fields["RANGE_ALERTS_MODE"]
    assert (mode.default, fields["RANGE_ALERTS_CELL"].default,
            fields["RANGE_ALERTS_LIVE_DIRECTIONS"].default) == ("off", "", "")
    assert config._cast(mode, "banana") == "off"
    assert config._cast(mode, "LIVE") == "live"
```

(If `tests/test_config_flags.py` imports `config` under another name, match
the existing `test_v93_strategy_alert_fields` at L115.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py`
Expected: FAIL, `ImportError: cannot import name 'range_pass'`.

- [ ] **Step 3: Add the config fields and `.env.example` lines**

In `swingbot/config.py`, directly after the `STRATEGY_ALERTS_LIVE_STRATEGIES` `Field(...)`:

```python
    Field("RANGE_ALERTS_MODE", "RANGE_ALERTS_MODE", "Universe & Scanning",
          "PENDING range continuation (v105)",
          type="select", default="off",
          options=[("off", "Off"),
                   ("shadow", "Shadow -- candidates and telemetry only, no plan, no alert"),
                   ("live", "Live -- PENDING plans, alerts and paper trades for allowed directions")],
          help="v105. Masked until its evidence gate passes. Manual !check runs are always shadow."),
    Field("RANGE_ALERTS_CELL", "RANGE_ALERTS_CELL", "Universe & Scanning",
          "Range cell selected on TRAIN (v105)", default="",
          help="v105. N{10|15|20}-d{0.25|0.50|0.75}-P{0|1}. Empty keeps live mode shadow-only."),
    Field("RANGE_ALERTS_LIVE_DIRECTIONS", "RANGE_ALERTS_LIVE_DIRECTIONS", "Universe & Scanning",
          "Range directions allowed live (v105)", default="",
          help="v105. Comma-separated bullish,bearish. Empty means none, not all."),
```

Generalise the existing `STRATEGY_ALERTS_MODE` `_cast` branch. The behaviour
is identical for the old key. Add a module constant above `_cast`:

```python
_TRI_STATE_MODES = ("STRATEGY_ALERTS_MODE", "RANGE_ALERTS_MODE")
```

and replace `if f.attr == "STRATEGY_ALERTS_MODE":` … `return v` with:

```python
    if f.attr in _TRI_STATE_MODES:
        v = str(raw).lower()
        if v not in ("off", "shadow", "live"):
            logging.getLogger("swingbot.config").warning(
                "invalid %s=%r, falling back to 'off'", f.attr, raw)
            return "off"
        return v
```

In `.env.example`, after `STRATEGY_ALERTS_LIVE_STRATEGIES=`:

```
# v105 PENDING range continuation. off = scan unchanged; shadow = candidates +
# telemetry only (no plan, no alert, no paper trade); live = PENDING plans for
# RANGE_ALERTS_LIVE_DIRECTIONS only. Masked until the v105 evidence gate passes.
RANGE_ALERTS_MODE=off
# TRAIN-selected cell, e.g. N20-d0.50-P1. Empty keeps live mode shadow-only.
RANGE_ALERTS_CELL=
# Comma-separated bullish,bearish allowed live. Empty = none.
RANGE_ALERTS_LIVE_DIRECTIONS=
```

Do not add these keys to `_SEARCH_CLASSES`. They stay `"excluded"`, so
`tests/test_scan_params_coverage.py` requires no `ScanParams` field.

- [ ] **Step 4: Add the feed transition**

In `swingbot/core/planning/plan_manager.py`, above `NOTICE_EVENTS`:

```python
#: v105: a new PENDING range plan's broker instruction. Queued as the plan's
#: pending_notice at creation, so resend_notices -> notify_plan_events ->
#: ack_notified retries it until the execution feed acknowledges delivery.
RANGE_PENDING = "range_pending"
```

and add `RANGE_PENDING` to the `NOTICE_EVENTS` frozenset. Update the
`PlanEvent.transition` comment at L50 to list `"range_pending"`.

- [ ] **Step 5: Add the instructions**

In `swingbot/core/presentation/instructions.py`, add imports:

```python
from swingbot.core.market.range_candidate import SOURCE_ID as RANGE_SOURCE_ID
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT
```

Add these helpers above `instruction_for`:

```python
def _range_pending(plan, side: dict, common: dict) -> Instruction:
    """v105: the resting order a PENDING range plan asks for, before the break."""
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    lines = [f"Stop-market, good through {last.isoformat()} "
             "(≈; a market holiday moves it one session later)",
             f"Once filled: {side['stop']} {_price(plan.stop_loss)} · "
             f"TP1 {side['limit']} {_price(plan.tp1)}",
             "Paper plan only: the bot never places, changes or cancels a broker order"]
    cap_fill = (plan.entry_context or {}).get("risk_cap_fill")
    if cap_fill is not None:
        lines.append(f"A fill beyond {_price(cap_fill)} breaks the "
                     f"{HARD_MAX_PLANNED_LOSS_PCT:.0f}% risk cap: the paper plan cancels, "
                     "your broker order does not")
    return Instruction(verb=PLACE, headline=f"PLACE {side['entry_stop']} {_price(plan.trigger_price)}",
                       lines=tuple(lines), **common)


def _risk_cap_divergence(plan, detail: dict, side: dict, common: dict) -> Instruction:
    """v105: a resting stop order can fill on a gap before the paper plan
    cancels, so the broker's state is unknown, not 'never filled'."""
    return Instruction(
        verb=CANCEL,
        headline=f"CANCEL {side['entry_stop']} {_price(plan.trigger_price)} — or EXIT if it filled",
        warnings=("⚠ broker order status UNKNOWN — a resting stop order may already "
                  "have filled on the gap",),
        lines=(f"paper plan cancelled: the fill at {_price(detail['entry_price'])} risked "
               f"{detail['planned_loss_pct']:.1f}% against stop {_price(detail['stop_loss'])}, "
               f"above the {detail['max_planned_loss_pct']:.1f}% cap",
               f"If you hold it: {side['exit']}, or protect it with {side['stop']} "
               f"{_price(plan.stop_loss)} — the bot is not tracking it"),
        tone="bad", **common)


def _cancelled(plan, transition: str, detail: dict, side: dict, common: dict) -> Instruction:
    if transition == "cancelled_risk_cap" and plan.source == RANGE_SOURCE_ID:
        return _risk_cap_divergence(plan, detail, side, common)
    if transition == "cancelled_expired":
        why = f"not triggered within {plan.expiry_bars} sessions"
    elif transition == "cancelled_invalidated":
        why = f"price reached the stop {_price(plan.stop_loss)} before triggering"
    else:
        why = (f"triggered at {_price(detail['entry_price'])} but risked "
               f"{detail['planned_loss_pct']:.1f}% against stop "
               f"{_price(detail['stop_loss'])} -- above the "
               f"{detail['max_planned_loss_pct']:.1f}% cap; never filled")
    return Instruction(
        verb=CANCEL, headline=f"CANCEL {side['entry_stop']} {_price(plan.trigger_price)}",
        lines=(why,), tone="inert", **common)
```

In `instruction_for`, replace the whole `if transition in ("cancelled_expired", …):`
block with the lines below, and add the `range_pending` branch directly
before it:

```python
    if transition == "range_pending":
        return _range_pending(plan, side, common)
    if transition in ("cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap"):
        return _cancelled(plan, transition, detail, side, common)
```

The confluence text is byte-identical. `_cancelled` moves the old block
verbatim, and `test_confluence_risk_cap_text_is_out_of_scope_and_unchanged`
pins it.

- [ ] **Step 6: Implement the pass and the embed**

`swingbot/core/scanning/range_pass.py`:

```python
"""v105: the masked PENDING range source on the watchlist scan.

Runs after the confluence and strategy passes, so open-position monitoring,
data fetch and the liquidity/data-quality screens have already run for every
ticker (analyze._scan_one). Geometry reads completed bars only. The quote is
fetched fresh here (allow_stale=False) and used for proximity alone.
`off` never reaches this module (scan_run returns first). `shadow` builds
and returns candidates without touching PlanStore, the trade log or any
channel. `live` issues a PENDING plan only for an allowed direction, and
queues its broker instruction as the plan's pending_notice so
PlanManager.resend_notices retries it until the execution feed
acknowledges delivery.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from swingbot.core.market.range_candidate import D_GRID, N_GRID, SOURCE_ID, range_candidate
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_manager import RANGE_PENDING
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.range_source import first_issuable, screen
from swingbot.core.scanning.strategy_pass import completed_frame

log = logging.getLogger(__name__)

OPEN_STATUSES = (PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL)
SHADOW_D = max(D_GRID)       # the widest d observes every cell's candidates
_UNSET = object()


@dataclass(frozen=True)
class RangeCell:
    n: int
    d: float
    require_pressure: bool

    @property
    def cell_id(self) -> str:
        return f"N{self.n}-d{self.d:.2f}-P{int(self.require_pressure)}"


def parse_cell(text: str | None) -> RangeCell | None:
    """'N20-d0.50-P1' -> RangeCell; None for empty or anything off-grid."""
    try:
        n_part, d_part, p_part = (text or "").strip().split("-")
        cell = RangeCell(int(n_part[1:]), float(d_part[1:]), p_part == "P1")
    except (ValueError, IndexError):
        return None
    valid = n_part[0] == "N" and d_part[0] == "d" and p_part in ("P0", "P1")
    return cell if valid and cell.n in N_GRID and cell.d in D_GRID else None


def fresh_quote(ticker: str) -> float | None:
    """A quote no older than the 15 s price TTL, or None. Never the scan's
    live_prices map, which can serve a last-good price up to 15 min old."""
    from swingbot.core.marketdata.data import get_current_price_detail
    quote = get_current_price_detail(ticker, allow_stale=False)
    if quote is None or quote.stale:
        return None
    return float(quote.price)


@dataclass
class RangePassResult:
    plans: list = field(default_factory=list)       # live PENDING plans issued this scan
    shadow: list = field(default_factory=list)      # (plan, cell_id, quote), observed only
    alerts: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)


def group_by_sector(plans, sector_of) -> list[dict]:
    """Same-sector plans on one scan form one correlated idea. No calibrated
    ranking exists yet, so members sit in ticker order and the group says
    unranked: the first member is NOT a recommendation. A ticker with no
    known sector is its own group, never lumped with other unknowns."""
    groups: dict[tuple, list] = {}
    for plan in plans:
        sector = sector_of(plan.ticker)
        key = (0, sector) if sector else (1, plan.ticker)
        groups.setdefault(key, []).append(plan)
    return [{"sector": key[1] if key[0] == 0 else None, "ranked": False,
             "members": sorted(members, key=lambda p: p.ticker)}
            for key, members in sorted(groups.items())]


def _prior_state(plan_store, ticker) -> tuple[bool, str | None]:
    mine = [p for p in plan_store.all() if p.source == SOURCE_ID and p.ticker == ticker]
    return (any(p.status in OPEN_STATUSES for p in mine),
            max((p.created_at for p in mine), default=None))


def _ticker_plans(ticker, raw, *, now, cells, quote_fn, params, plan_store, counts) -> list:
    """[(cell, plan, quote)] issuable for one ticker; the quote is fetched
    only once a candidate has survived every bar-only refusal."""
    frame = completed_frame(raw, now)
    if frame is None or len(frame) == 0:
        counts["no_data"] += 1
        return []
    open_now, prior = _prior_state(plan_store, ticker)
    if open_now:
        counts["open_range_plan"] += 1
        return []
    out, quote = [], _UNSET
    for cell in cells:
        cand = range_candidate(frame, n=cell.n, ticker=ticker)
        if cand is None:
            counts["no_candidate"] += 1
            continue
        blocked = screen(cand, prior, cell.require_pressure)
        if blocked:
            counts[blocked] += 1
            continue
        quote = quote_fn(ticker) if quote is _UNSET else quote
        issued = first_issuable(frame, cand, tuple(HORIZONS), price=quote, d=cell.d,
                                params=params, counts=counts)
        if issued is not None:
            out.append((cell, issued[1], quote))
    return out


def _issue(plan, quote, *, now, trade_log, plan_store, result) -> None:
    if trade_log.open_trade_for_ticker(plan.ticker) is not None:
        result.counts["open_trade"] += 1
        return
    at = now.isoformat()
    plan.first_seen_price = quote
    plan.issued_at = at
    plan.pending_notice = {"transition": RANGE_PENDING,
                           "detail": {"trigger": plan.trigger_price, "quote": quote}, "at": at}
    plan_store.add(plan)
    trade_log.log_trade(
        ticker=plan.ticker, strategy=plan.strategy, horizon_key=plan.horizon_key,
        direction=plan.direction, confidence_level=None, confidence_label="range continuation",
        entry=plan.trigger_price, stop_loss=plan.stop_loss, take_profit=plan.tp1,
        target2=plan.tp2, plan_id=plan.plan_id, badge=plan.badge,
        quality_score=plan.quality_score, source=plan.source, cohort_label=plan.cohort_label,
        cohort_stats=plan.cohort_stats, risk_features=plan.risk_features,
        ledger=plan.ledger, entry_context=plan.entry_context)
    result.plans.append(plan)
    result.counts["issued"] += 1


def run_range_pass(tickers, fresh_data, *, now, mode, cell, live_directions, trade_log,
                   plan_store, sector_of, quote_fn=fresh_quote, params=None) -> RangePassResult:
    from swingbot.core.scanning.range_embeds import build_range_alert_embed
    result = RangePassResult()
    live = mode == "live" and cell is not None
    cells = [cell] if live else [RangeCell(n, SHADOW_D, False) for n in N_GRID]
    for ticker in tickers:
        try:
            issued = _ticker_plans(ticker, fresh_data.get(ticker), now=now, cells=cells,
                                   quote_fn=quote_fn, params=params, plan_store=plan_store,
                                   counts=result.counts)
        except Exception:
            log.warning("range pass: %s failed -- continuing", ticker, exc_info=True)
            continue
        for issued_cell, plan, quote in issued:
            if live and plan.direction in live_directions:
                _issue(plan, quote, now=now, trade_log=trade_log, plan_store=plan_store, result=result)
            else:
                result.shadow.append((plan, issued_cell.cell_id, quote))
    result.alerts = [(build_range_alert_embed(plan, group), None, plan, None)
                     for group in group_by_sector(result.plans, sector_of)
                     for plan in group["members"]]
    return result
```

The 4th tuple element is `None` on purpose. `_send_alerts` mirrors a
non-empty simple text to the simple channel, and that channel is also the
execution feed, which already receives the `range_pending` instruction.

`swingbot/core/scanning/range_embeds.py`:

```python
"""v105: the research alert for one PENDING range plan.

The actionable broker instruction is the execution-feed `range_pending`
notice (presentation/instructions.py). This embed is the context around it:
the frozen range, the trigger's expiry and any same-sector alternatives.
"""
from __future__ import annotations

import discord

from swingbot.core import presentation as ui
from swingbot.core.presentation.instructions import approx_last_trigger_session


def build_range_alert_embed(plan, group) -> discord.Embed:
    long_side = plan.direction == "bullish"
    rng = (plan.entry_context or {}).get("range", {})
    last = approx_last_trigger_session(plan.created_at, plan.expiry_bars)
    embed = discord.Embed(title=f"⏳ PENDING range break — {plan.ticker} {'LONG' if long_side else 'SHORT'}")
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"), plan_id=plan.plan_id)
    embed.add_field(name="Order", value=f"{'BUY' if long_side else 'SELL'} STOP {plan.trigger_price:.2f} (stop-market)")
    embed.add_field(name="Stop", value=f"{plan.stop_loss:.2f}")
    embed.add_field(name="TP1", value=f"{plan.tp1:.2f}")
    embed.add_field(name="Range", inline=False, value=(
        f"{rng.get('lower', 0.0):.2f}–{rng.get('upper', 0.0):.2f} over {rng.get('n')} "
        f"completed sessions, as of {plan.created_at}"))
    embed.add_field(name="Expires", value=f"after {last.isoformat()} (≈)")
    embed.add_field(name="Issued", value=plan.issued_at or "—")
    embed.add_field(name="Broker", inline=False, value=(
        f"{plan.badge} source. The bot tracks a paper plan; it never places, "
        "changes or cancels your order."))
    others = [p.ticker for p in group["members"] if p.plan_id != plan.plan_id]
    if others:
        embed.add_field(name=f"Same sector ({group['sector']}, unranked)", inline=False,
                        value=", ".join(others) + " — one correlated idea; each order is independent")
    return embed
```

- [ ] **Step 7: Wire the pass into the scan**

In `swingbot/core/scanning/scan_run.py`, add below `_maybe_run_strategy_pass`:

```python
def _maybe_run_range_pass(*, tickers, fresh_data, sector_of_ticker, trade_log, alerts,
                          require_confirmation) -> dict:
    """v105's masked range source; manual checks are strictly shadow-only."""
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.scanning import range_pass
    mode = config.RANGE_ALERTS_MODE
    if mode == "off":
        return {"range_plans": 0, "range_shadow": 0}
    cell = range_pass.parse_cell(config.RANGE_ALERTS_CELL)
    if mode == "live" and cell is None:
        log.warning("RANGE_ALERTS_MODE=live without a valid RANGE_ALERTS_CELL -- running shadow")
    if not require_confirmation or cell is None:
        mode = "shadow"
    directions = {d.strip() for d in (config.RANGE_ALERTS_LIVE_DIRECTIONS or "").split(",") if d.strip()}
    sectors = sector_of_ticker or {}
    result = range_pass.run_range_pass(
        tickers, fresh_data, now=datetime.now(timezone.utc), mode=mode, cell=cell,
        live_directions=directions, trade_log=trade_log, plan_store=PlanStore(),
        sector_of=sectors.get)
    alerts.extend(result.alerts)
    log.info("range pass (%s): %s", mode, dict(result.counts))
    return {"range_plans": len(result.plans), "range_shadow": len(result.shadow)}
```

Match `scan_run.py`'s existing names for `log`, `datetime` and `timezone`.
If the module imports `datetime` as a module, write
`datetime.datetime.now(datetime.timezone.utc)`. If `PlanStore` is already
imported at module level, drop the local import.

Directly after the `strategy_counts = _maybe_run_strategy_pass(...)` call
(L934-938):

```python
    strategy_counts.update(_maybe_run_range_pass(
        tickers=tickers, fresh_data=fresh_data, sector_of_ticker=sector_of_ticker,
        trade_log=trade_log, alerts=alerts, require_confirmation=require_confirmation))
```

`progress.funnel` is a plain dict, so the two extra keys are safe.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py
python scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py
python scripts/dev/testrun.py file tests/test_config_flags.py
python scripts/dev/testrun.py file tests/test_env_example_sync.py
python scripts/dev/testrun.py file tests/test_scan_params_coverage.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py
python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py
```

Expected: every run `0 failed`, `0 xfailed`.

- [ ] **Step 9: Check complexity and commit**

```bash
python -m radon cc -s -n C swingbot/core/scanning/range_pass.py swingbot/core/scanning/range_embeds.py swingbot/core/presentation/instructions.py swingbot/core/scanning/scan_run.py swingbot/config.py swingbot/core/planning/plan_manager.py
```

Expected: no NEW entry at ≥ C, and `instruction_for` lower than before
(its cancel branch moved out). Any pre-existing ≥ 15 function must not have
grown: compare against `git stash; radon …; git stash pop`.

```bash
git status --short
git add swingbot/config.py .env.example swingbot/core/planning/plan_manager.py swingbot/core/presentation/instructions.py swingbot/core/scanning/range_pass.py swingbot/core/scanning/range_embeds.py swingbot/core/scanning/scan_run.py tests/scanning/test_pending_range_alerts.py tests/test_config_flags.py
git commit -m "feat(v105): masked range source on the watchlist scan, PENDING feed notice with retry, broker-unknown risk-cap notice"
```

**Verification:** the seven narrow runs in Step 8, radon, and
`python -m py_compile swingbot/core/scanning/scan_run.py swingbot/config.py`.
