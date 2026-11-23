# v239 — Bear-regime engine (shadow): Part 3 — stamp, scan lanes, alert lines, admin API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-10" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md) — Global Constraints, Parallelisation, the task ledger and the eight "Decisions this index fixes" apply here.

Tasks: V239-9 (stamp, needs V239-2/2b), V239-10 (scan wiring, needs V239-8 and V239-9), V239-11 (alert lines and outlook stamp, needs V239-3, V239-8 and V239-9), V239-12 (API, needs V239-3, 4, 5, 6b).

# Phase 3 — Stamp, lanes, surfaces on the bot side

### Task V239-9: Stamp `bear_regime` / `regime_action`; thread `regime_day`; wire keys

**Model:** opus — touches the shared plan stamp every lane runs through; the `off` arm must stay byte-identical and the action must follow the plan's own direction.

**Files:**
- Modify: `swingbot/core/planning/params.py` (`regime_asof`, `_merge_regime`, one call in `stamp_entry_context`)
- Modify: `swingbot/core/scanning/analyze.py` (`attach_plan_v2` gains `regime_day=None` and one dict splat; no branch)
- Modify: `swingbot/core/scanning/qualify.py` (`QualifyContext.regime_day`, forwarded by `_attach_plan`)
- Modify: `swingbot/admin/trade_why.py` (`WIRE_CONTEXT_KEYS` gains two keys)
- Modify: `tests/admin/test_api_v1_trade_detail.py` (two wire tests)
- Modify: `tests/scanning/test_shock_short_lane.py` (one assertion: `shock_state` is no longer the last `QualifyContext` field; no test added)
- Test: `tests/regime/test_regime_stamp.py` (create; suite `market-signals`)

**Interfaces:**
- Consumes (V239-2/2b `swingbot/core/market/bear_regime.py`): `RegimeDay` (fields `state`, `stress`, `pullback_trigger`), the state constants `BEAR`/`CORRECTION`/`NORMAL`/`UNKNOWN`, `shadow_action(state, stress, pullback_trigger, direction) -> str` (`"bullish"`/`"bearish"`; any other direction gives `"none"`).
- Produces (ledger contract, final):
  - `params.regime_asof(day: RegimeDay | None) -> dict`: `{}` for `None`, else `{"bear_regime_day": day}`. The `RegimeDay` object lives only in the asof dict. `edge.context.entry_context` reads `FEATURE_KEYS` from the asof and nothing else, so the object never reaches a record.
  - `params._merge_regime(plan, asof) -> None`: adds `bear_regime` (the state string) and `regime_action` (`shadow_action(..., plan.direction)`) to `plan.entry_context` when the asof carries a day. It adds them after a feature-build failure too, and adds nothing when there is no day.
  - `analyze.attach_plan_v2(..., shock_state=None, regime_day=None)`.
  - `qualify.QualifyContext.regime_day: RegimeDay | None = None` (the field after `shock_state`).
  - `trade_why.WIRE_CONTEXT_KEYS` ends with `"bear_regime", "regime_action"`.
  - V239-10 threads `regime_day` from the pass into these. V239-11 and V239-14 read the two keys by name.

**Why an `UNKNOWN` day still stamps:** index decision 1. A stale or short-history day is stamped `bear_regime = "UNKNOWN"`, `regime_action = "none"`. The record then shows the engine ran and had no reading, which is different from `off` (no key).

- [ ] **Step 1: Write the failing stamp test**

Create `tests/regime/test_regime_stamp.py`:

```python
"""v239 V239-9: entry_context gains bear_regime and regime_action; regime_day reaches the stamp."""
import dataclasses
import inspect
import json
from datetime import date
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.planning import params
from swingbot.core.scanning import analyze, qualify
from tests.helpers import make_ohlcv
from tests.scanning.test_live_context_stamp import _plan

FRAME = make_ohlcv([100.0 + i * 0.1 for i in range(300)], start="2025-06-02")
S, D = date(2026, 11, 18), date(2026, 11, 19)
KEYS = {"bear_regime", "regime_action"}
PRE_V239 = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": 55.0,
            "rs_combined": 61.0}


def _day(state=br.CORRECTION, stress=True, pullback=False):
    return br.RegimeDay(session_date=D, last_bar_date=S, state=state, stress=stress,
                        pullback_trigger=pullback)


def _stamped(day, direction="bullish", asof=None):
    plan = dataclasses.replace(_plan(), direction=direction)
    params.stamp_entry_context(plan, FRAME, {**(asof or {}), **params.regime_asof(day)})
    return plan.entry_context


def test_regime_asof_is_empty_without_a_day():
    day = _day()
    assert params.regime_asof(None) == {}
    assert params.regime_asof(day) == {"bear_regime_day": day}


@pytest.mark.parametrize("state, stress, pullback, direction, action", [
    (br.BEAR, None, False, "bullish", "would_veto"),
    (br.BEAR, False, False, "bullish", "would_veto"),
    (br.CORRECTION, True, False, "bullish", "would_veto"),
    (br.CORRECTION, False, False, "bullish", "caution"),
    (br.CORRECTION, None, False, "bullish", "caution"),       # missing VIX never reads as stress
    (br.CORRECTION, True, True, "bullish", "pullback_watch"),  # pullback wins over would_veto
    (br.NORMAL, False, False, "bullish", "none"),
    (br.UNKNOWN, None, False, "bullish", "none"),
    (br.BEAR, True, False, "bearish", "aligned"),
    (br.CORRECTION, False, True, "bearish", "aligned"),
    (br.NORMAL, None, False, "bearish", "none"),
    (br.UNKNOWN, None, False, "bearish", "none")])
def test_the_stamp_carries_the_state_and_the_action_for_the_plan_direction(
        state, stress, pullback, direction, action):
    ctx = _stamped(_day(state, stress, pullback), direction)
    assert (ctx["bear_regime"], ctx["regime_action"]) == (state, action)


def test_without_a_day_the_stamp_is_the_pre_v239_dict():
    plain = _plan()
    params.stamp_entry_context(plain, FRAME, {"rs_pctile": 64.0})
    assert not KEYS & set(plain.entry_context)
    same = _stamped(None, asof={"rs_pctile": 64.0})
    assert json.dumps(same, sort_keys=True, default=str) ==         json.dumps(plain.entry_context, sort_keys=True, default=str)   # NaN-safe


def test_only_strings_reach_the_record():
    ctx = _stamped(_day())
    assert "bear_regime_day" not in ctx
    assert {k: ctx[k] for k in KEYS} == {"bear_regime": "CORRECTION", "regime_action": "would_veto"}
    assert json.loads(json.dumps(ctx, default=str))["bear_regime"] == "CORRECTION"


def test_the_keys_survive_a_feature_build_failure(monkeypatch):
    import swingbot.core.edge.context as edge_context

    def boom(*args, **kwargs):
        raise RuntimeError("features down")

    monkeypatch.setattr(edge_context, "entry_context", boom)
    assert _stamped(_day(br.BEAR)) == {"bear_regime": "BEAR", "regime_action": "would_veto"}


def test_the_regime_keys_sit_beside_the_shock_label():
    ctx = _stamped(_day(), asof={"shock_state": "NORMAL"})
    assert (ctx["shock_state"], ctx["bear_regime"]) == ("NORMAL", "CORRECTION")


def test_an_unknown_direction_is_action_none():
    assert _stamped(_day(br.BEAR), direction="neutral")["regime_action"] == "none"


def _attach_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    seen = []
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: seen.append(asof))
    return seen


def _attach(**kwargs):
    item = SimpleNamespace(rs_combined=61.0, sector_rs_percentile=55.0, conf=None, htf_bias=None,
                           target_confluence=None)
    analyze.attach_plan_v2(item, SimpleNamespace(direction="bullish", entry=100.0), FRAME, "AAPL",
                           "3m", rs_percentile=64.0, regime2_state="bull_quiet", **kwargs)


def test_attach_plan_v2_adds_the_day_to_the_asof(monkeypatch):
    seen, day = _attach_env(monkeypatch), _day()
    _attach(shock_state="NORMAL", regime_day=day)
    assert seen == [{**PRE_V239, "shock_state": "NORMAL", "bear_regime_day": day}]


@pytest.mark.parametrize("kwargs", [{}, {"regime_day": None}])
def test_attach_plan_v2_without_a_day_hands_over_the_pre_v239_asof(monkeypatch, kwargs):
    seen = _attach_env(monkeypatch)
    _attach(**kwargs)
    assert seen == [PRE_V239]


def _context(**over):
    return qualify.QualifyContext(frames={}, spy=None, sector_of={}, etf_symbol_of={},
                                  sector_frames={}, regime=None, regimes=None, **over)


def test_the_context_carries_a_day_after_the_shock_label_defaulting_to_none():
    names = [f.name for f in dataclasses.fields(qualify.QualifyContext)]
    assert names[-2:] == ["shock_state", "regime_day"]
    assert _context().regime_day is None


@pytest.mark.parametrize("day", [None, _day()])
def test_the_short_attach_forwards_the_context_day(monkeypatch, day):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("regime_day", "MISSING")))
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend="bearish",
                                                  state_key="k", state_value="v"),
                           plan="scenario", level_map=None, rs_percentile=None, htf_info=None,
                           plan_v2=None, plan_v2_rejected=None)
    qualify._attach_plan(item, _context(regime_day=day))
    assert calls == [day]


def test_planning_never_reads_the_regime_store_or_runs_the_pass():
    for module in (qualify, params, analyze):
        source = inspect.getsource(module)
        assert "regime_scan" not in source and "regime_for_pass" not in source, module
        assert "market_regime_repo" not in source, module
```

- [ ] **Step 2: Add the wire tests and move one v209 assertion**

In `tests/admin/test_api_v1_trade_detail.py`, directly after `test_plan_entry_context_wins_and_is_filtered_to_the_wire_keys`, add:

```python
def test_the_bear_regime_stamp_reaches_the_wire(seed, logged_in, fixed_today):
    ctx = {**_why_plan()["entry_context"], "bear_regime": "CORRECTION", "regime_action": "aligned"}
    seed(plans=[_why_plan(entry_context=ctx)], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    wire = _detail(logged_in, _PLAN_ID)["entry_context"]
    assert (wire["bear_regime"], wire["regime_action"]) == ("CORRECTION", "aligned")
    assert trade_why.WIRE_CONTEXT_KEYS[-2:] == ("bear_regime", "regime_action")


def test_a_legacy_plan_without_the_stamp_gets_no_regime_keys(seed, logged_in, fixed_today):
    seed(plans=[_why_plan()], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    wire = _detail(logged_in, _PLAN_ID)["entry_context"]
    assert "bear_regime" not in wire and "regime_action" not in wire   # never upcast
```

In `tests/scanning/test_shock_short_lane.py`, `test_the_label_is_the_last_context_field_and_defaults_to_none`, replace

```python
    assert fields[-1].name == "shock_state" and fields[-1].default is None
```

with

```python
    shock = next(f for f in fields if f.name == "shock_state")
    assert fields[-2] is shock and shock.default is None   # v239: regime_day follows it
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_stamp.py`
Expected: failures with `AttributeError: module 'swingbot.core.planning.params' has no attribute 'regime_asof'` and `TypeError: ... unexpected keyword argument 'regime_day'`.

- [ ] **Step 4: Implement the stamp in `swingbot/core/planning/params.py`**

Add `from swingbot.core.market import bear_regime` to the imports. `bear_regime` is pure (pandas/numpy/dataclasses) and imports nothing from `planning`. Directly after `shock_asof`, add:

```python
#: v239: the asof key carrying the pass's RegimeDay. entry_context() reads only
#: FEATURE_KEYS from the asof, so the object itself never reaches a record.
REGIME_ASOF_KEY = "bear_regime_day"


def regime_asof(day: "bear_regime.RegimeDay | None") -> dict:
    """v239: the asof fragment carrying the bear-regime day. Empty for None, so an
    `off` pass hands stamp_entry_context exactly the pre-v239 dict."""
    return {} if day is None else {REGIME_ASOF_KEY: day}
```

In `stamp_entry_context`, add `_merge_regime(plan, asof)` as the last line (after `_merge_shock_state(plan, asof)`). After the `_merge_shock_state` function, add:

```python
def _merge_regime(plan: TradePlanV2, asof: dict | None) -> None:
    """v239 shadow: the day's state and what the engine WOULD do with a plan of this
    direction. Beside the feature dict like shock_state; absent when no day."""
    day = (asof or {}).get(REGIME_ASOF_KEY)
    if day is None:
        return
    action = bear_regime.shadow_action(day.state, day.stress, day.pullback_trigger, plan.direction)
    plan.entry_context = {**(plan.entry_context or {}), "bear_regime": day.state,
                          "regime_action": action}
```

- [ ] **Step 5: Thread `regime_day` through `analyze.py` and `qualify.py`**

`swingbot/core/scanning/analyze.py`:
1. Change the import to `from swingbot.core.planning.params import regime_asof, shock_asof, stamp_entry_context`.
2. In the `attach_plan_v2` signature, change `issued_at=None, now=None, shock_state=None):` to `issued_at=None, now=None, shock_state=None, regime_day=None):`. Append one sentence to its docstring: `regime_day` (v239) is the pass's RegimeDay; None (BEAR_REGIME_MODE off, or a failed pass) leaves entry_context without bear_regime / regime_action.
3. In the `stamp_entry_context(plan, df, {...})` call, add `**regime_asof(regime_day),` on the line after `**shock_asof(shock_state),`.

`swingbot/core/scanning/qualify.py`:
1. Add `from swingbot.core.market.bear_regime import RegimeDay` to the imports.
2. In `QualifyContext`, directly after the `shock_state: str | None = None` line, add
   `regime_day: RegimeDay | None = None   # v239: the run's bear-regime day; None = no key`.
3. In `_attach_plan`, change `issued_at=context.issued_at, now=context.now, shock_state=context.shock_state)` to `issued_at=context.issued_at, now=context.now, shock_state=context.shock_state,` followed by a new line `regime_day=context.regime_day)`.

- [ ] **Step 6: Put the two keys on the wire**

In `swingbot/admin/trade_why.py`, replace the `WIRE_CONTEXT_KEYS` tuple with:

```python
WIRE_CONTEXT_KEYS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined",
                     "htf_aligned", "gap_p90_pct", "gap_fragile",
                     "bear_regime", "regime_action")   # v239: the chip reads the stamp
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_stamp.py`
Expected: `0 failed`.

The v209 lanes stay pinned, because a `None` day hands over the pre-v239 asof. Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_state_stamp.py`,
`python scripts/dev/testrun.py file tests/scanning/test_shock_short_lane.py`,
`python scripts/dev/testrun.py file tests/scanning/test_shock_plans_byte_identical.py`,
`python scripts/dev/testrun.py file tests/scanning/test_live_context_stamp.py`.
Expected: `0 failed` each.

Run `/replicate-prod-db` first (the trade-detail tests seed Postgres in the shared `swing-db` container), then:
`python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`
Expected: `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/planning/params.py swingbot/core/scanning/qualify.py`
Expected: no output. `attach_plan_v2` stays at C 12 (`python -m radon cc -s swingbot/core/scanning/analyze.py | grep attach_plan_v2`).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/planning/params.py swingbot/core/scanning/analyze.py swingbot/core/scanning/qualify.py swingbot/admin/trade_why.py tests/regime/test_regime_stamp.py tests/admin/test_api_v1_trade_detail.py tests/scanning/test_shock_short_lane.py
git commit -m "feat(v239): stamp bear_regime and regime_action on entry_context, keys on the wire"
```

### Task V239-10: Scan wiring on every lane, and the `off` byte-identical pins

**Model:** opus — threads one value through the F 94 legacy `_sync_run_scan` and the SHORT lane without adding a branch, and pins byte identity on six build routes.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (one unconditional pass call in `_sync_run_scan`; a `regime_day` kwarg on `_attach_item_plan`, `_rebuild_item` and `_maybe_run_strategy_pass`)
- Modify: `swingbot/core/scanning/short_run.py` (`_lane_state` runs the pass once per SHORT run; `_qualify_context` and `_bare_context` carry the day)
- Modify: `tests/conftest.py` (`_pin_dotenv_settings` pins `BEAR_REGIME_MODE = "off"` for every test)
- Modify: `tests/scanning/test_shock_short_lane.py` (the exact lane dict gains `"regime_day": None`; no test added)
- Test: `tests/regime/test_regime_wiring.py`, `tests/regime/test_regime_off_byte_identical.py` (create both; suite `market-signals`)

**Interfaces:**
- Consumes: V239-8 `regime_scan.regime_for_pass(*, now=None, repo=None, fetch=None, plans=None, trades=None) -> RegimeDay | None` (never raises; `None` under `off`, under an unknown mode, or on failure). `regime_scan.get_daily_data` and `regime_scan.market_regime_repo` are module globals it resolves at call time. V239-9: `params.regime_asof(day) -> dict`, `attach_plan_v2(..., regime_day=None)`, `QualifyContext.regime_day`, the `bear_regime` / `regime_action` keys.
- Produces (ledger contract, final): `scan_run._attach_item_plan(item, scenario, df, regimes, regime, shock_state=None, regime_day=None)`; `scan_run._rebuild_item(item, price, *, fresh_data, regimes, regime, require_confirmation, shock_state=None, regime_day=None)`; `scan_run._maybe_run_strategy_pass(..., shock_state=None, regime_day=None)` whose `asof_of(ticker)` is `{**rs_asof, **shock_asof, **regime_asof}`; `short_run._bare_context(frames, shock_state=None, regime_day=None)`; `short_run._lane_state(...)` returns the v209 dict plus key `"regime_day"`.

**Why the test-wide pin:** the shipped default is `shadow` (V239-5). Without the pin, every existing test that drives `_sync_run_scan` or `short_run._lane_state` would run the real pass: a yfinance fetch of SPY and ^VIX, plus a `market_regime_days` read and write. A test that never touched Postgres would then skip whenever `db-test` is down. The pin goes in `_pin_dotenv_settings` (per test and session-wide). V239-8 and V239-12 set the mode themselves.

**No new branch:** `_sync_run_scan` (F 94) gains one assignment and three keyword arguments. `_lane_state` gains one dict entry. `asof_of` gains one splat. Complexity is unchanged everywhere except the new test helpers.

- [ ] **Step 1: Write the failing wiring test**

Create `tests/regime/test_regime_wiring.py`:

```python
"""v239 V239-10: one regime pass per scan pass and per SHORT run; its day reaches every lane.

Planning never runs the pass: the scan entry points do, once, and hand the day down
the same routes v209's shock label takes."""
import ast
import inspect
from datetime import date
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.planning.rebuild import RebuildPrice
from swingbot.core.scanning import analyze, regime_scan, scan_replay, scan_run, short_run
from tests.scanning.test_shock_plans_byte_identical import _attach_on_rebuild
from tests.scanning.test_shock_short_lane import _calls, _functions, _lane_inputs
from tests.scanning.test_shock_state_stamp import _strategy, strategy_env  # noqa: F401  (fixture)

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-11-05T15:00:00+00:00", 1000.0, True, "regular")
DAY = br.RegimeDay(session_date=date(2026, 11, 19), last_bar_date=date(2026, 11, 18),
                   state=br.CORRECTION, stress=True)
LANE = {"sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": None,
        "regime": None, "regimes": None}


def _item(trend="bullish"):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAA", horizon_key="4w", trend=trend, state_key="k",
                               state_value="v"),
        level_map=None, rs_percentile=None, breadth=None, htf_info=None,
        plan_v2=None, plan_v2_rejected=None, plan="scenario")


def _capture_attach(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "attach_plan_v2",
                        lambda *a, **k: calls.append(k.get("regime_day", "MISSING")))
    return calls


def test_the_test_session_runs_no_regime_pass():
    assert config.BEAR_REGIME_MODE == "off"      # tests/conftest.py pin


@pytest.mark.parametrize("day", [None, DAY])
def test_attach_item_plan_forwards_the_day(monkeypatch, day):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_item(), "scenario", None, None, None, regime_day=day)
    assert calls == [day]


def test_attach_item_plan_defaults_to_no_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    scan_run._attach_item_plan(_item(), "scenario", None, None, None, shock_state="SHOCK")
    assert calls == [None]


def test_the_requote_rebuild_attaches_with_the_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")
    out = scan_run._rebuild_item(_item(), PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True, shock_state=None, regime_day=DAY)
    assert out.kept and calls == [DAY]


@pytest.mark.parametrize("extra, expected", [
    ({}, {}), ({"regime_day": None}, {}), ({"regime_day": DAY}, {"bear_regime_day": DAY}),
    ({"shock_state": "SHOCK", "regime_day": DAY}, {"shock_state": "SHOCK", "bear_regime_day": DAY})])
def test_the_strategy_asof_carries_the_day(strategy_env, extra, expected):
    _strategy(**extra)
    assert strategy_env["asof_of"]("AAA") == expected


def test_the_scan_runs_the_pass_once_and_threads_its_day_into_every_builder():
    fns = _functions(scan_run)
    runners = [name for name, fn in fns.items() if _calls(fn, "regime_for_pass")]
    assert runners == ["_sync_run_scan"]
    (call,) = _calls(fns["_sync_run_scan"], "regime_for_pass")
    assert ast.unparse(call) == "regime_scan.regime_for_pass()"
    wanted = {"_attach_item_plan", "_maybe_run_strategy_pass", "partial"}
    seen = {}
    for node in (n for n in ast.walk(fns["_sync_run_scan"]) if isinstance(n, ast.Call)):
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in wanted:
            seen[name] = {k.arg: ast.unparse(k.value) for k in node.keywords}.get("regime_day")
    assert seen == {name: "regime_day" for name in wanted}


def test_the_bare_context_carries_the_day():
    assert short_run._bare_context({}).regime_day is None
    assert short_run._bare_context({}, regime_day=DAY).regime_day is DAY


def test_the_lane_state_runs_the_pass_once(monkeypatch):
    runs = []
    monkeypatch.setattr(short_run.shock_scan, "current_label", lambda **k: None)
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: runs.append(k) or DAY)
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert runs == [{}] and lane["regime_day"] is DAY


@pytest.mark.parametrize("lane, expected", [({**LANE, "regime_day": DAY}, DAY),
                                            ({**LANE, "regime_day": None}, None), (LANE, None)])
def test_the_qualify_context_takes_the_day_from_the_lane(lane, expected):
    assert short_run._qualify_context(False, {}, lane).regime_day is expected


def test_the_short_requote_rebuild_keeps_the_day(monkeypatch):
    calls = _capture_attach(monkeypatch)
    _attach_on_rebuild(monkeypatch, short_run, lambda item: "rebuilt")
    item = _item("bearish")
    out = short_run._rebuild_fn({}, short_run._bare_context({}, regime_day=DAY))(item, PRICE)
    assert out.kept and calls == [DAY]


def test_the_short_run_runs_the_pass_only_at_its_lane_entry():
    fns = _functions(short_run)
    assert [name for name, fn in fns.items() if _calls(fn, "regime_for_pass")] == ["_lane_state"]
    assert len(_calls(fns["_sync_run_short_scan"], "_lane_state")) == 1


def test_replay_contexts_never_carry_a_day():
    for call in _calls(ast.parse(inspect.getsource(scan_replay)), "QualifyContext"):
        assert "regime_day" not in {k.arg for k in call.keywords}
```

- [ ] **Step 2: Write the failing `off` byte-identical test**

Create `tests/regime/test_regime_off_byte_identical.py`:

```python
"""v239 index Global Constraints: under BEAR_REGIME_MODE=off nothing changes.

Every lane (confluence, its requote rebuild, strategy, SHORT, the SHORT lane dict
route, the SHORT requote rebuild) is built three ways: the pre-v239 call (no day
argument), `off` (day None) and `shadow` (a CORRECTION + stress day). `off` must
equal pre-v239 byte for byte with no regime key; `shadow` must equal it once its
two keys are removed. An `off` (or unknown) mode fetches nothing and never opens
the market_regime_days store. Embed bytes are pinned in test_regime_embeds.py."""
from datetime import date

import pytest

from swingbot import config
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.market import bear_regime as br
from swingbot.core.planning import params
from swingbot.core.scanning import analyze, qualify, regime_scan, scan_run, short_run, strategy_pass
from tests.scanning.test_shock_plans_byte_identical import (FRAME, PRICE, RS, _attach_on_rebuild,
                                                            _canon, _long_item, _long_plan)
from tests.scanning.test_shock_short_lane import _lane_inputs
from tests.scanning.test_short_qualify import (  # noqa: F401  (offline, sealed, autouse are fixtures)
    CANDIDATE, _context, _items, _lane, _no_notice_queue_write, _stock, offline, sealed)

DAY = br.RegimeDay(session_date=date(2026, 11, 19), last_bar_date=date(2026, 11, 18),
                   state=br.CORRECTION, stress=True)
ARMS = {"pre_v239": {}, "off": {"regime_day": None}, "shadow": {"regime_day": DAY}}
REGIME_KEYS = {"bear_regime", "regime_action"}


def _assert_pinned(build, action, *, features=True):
    plans = {arm: build(dict(kwargs)) for arm, kwargs in ARMS.items()}
    assert all(plan is not None for plan in plans.values()), plans
    for arm in ("pre_v239", "off"):
        assert not REGIME_KEYS & set(plans[arm].entry_context), arm
    if features:
        assert set(plans["off"].entry_context) == set(FEATURE_KEYS)
    assert _canon(plans["off"]) == _canon(plans["pre_v239"])
    ctx = plans["shadow"].entry_context
    assert (ctx.pop("bear_regime"), ctx.pop("regime_action")) == ("CORRECTION", action)
    assert _canon(plans["shadow"]) == _canon(plans["pre_v239"])


@pytest.fixture
def long_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")


def test_the_confluence_long_plan_is_pinned(long_env):
    def build(kwargs):
        item = _long_item()
        scan_run._attach_item_plan(item, "scenario", FRAME, None, None, **kwargs)
        return item.plan_v2

    _assert_pinned(build, "would_veto")


def test_the_confluence_requote_rebuild_is_pinned(long_env, monkeypatch):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")

    def build(kwargs):
        item = _long_item()
        out = scan_run._rebuild_item(item, PRICE, fresh_data={"AAPL": FRAME}, regimes=None,
                                     regime=None, require_confirmation=True, **kwargs)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build, "would_veto")


def test_the_strategy_long_plan_is_pinned(monkeypatch):
    monkeypatch.setattr(strategy_pass, "build_strategy_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(strategy_pass, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(strategy_pass, "stamp_cohort", lambda plan, state: None)

    def build(kwargs):
        # what scan_run's asof_of hands the pass: RS readings + regime_asof
        asof = {**RS, **params.regime_asof(kwargs["regime_day"])} if kwargs else dict(RS)
        return strategy_pass.build_strategy_plan_at(
            FRAME, ticker="AAPL", strategy="MACD", horizon_key="3m", direction="bullish",
            regime2_state="bull_quiet", asof=asof)

    _assert_pinned(build, "would_veto")


def test_the_short_plan_is_pinned(sealed):  # noqa: F811
    def build(kwargs):
        verdict = qualify.qualify_short_item(CANDIDATE, _items()[0], _context(**kwargs))
        assert isinstance(verdict, qualify.Accepted), verdict
        return verdict.item.plan_v2

    _assert_pinned(build, "aligned", features=False)


def test_the_short_lane_dict_route_is_pinned(offline):  # noqa: F811
    def build(kwargs):
        kept = short_run._qualified_items(_items(), False, {"AAA": _stock()}, {**_lane(), **kwargs})
        return next(item.plan_v2 for item in kept if item.plan_v2 is not None)

    _assert_pinned(build, "aligned", features=False)


def test_the_short_requote_rebuild_is_pinned(sealed, monkeypatch):  # noqa: F811
    _attach_on_rebuild(monkeypatch, short_run, lambda item: item.plan)

    def build(kwargs):
        item = _items()[0]
        out = short_run._rebuild_fn({"AAA": _stock()}, _context(**kwargs))(item, PRICE)
        assert out.kept
        return item.plan_v2

    _assert_pinned(build, "aligned", features=False)


def _no_io(monkeypatch):
    monkeypatch.setattr(regime_scan, "get_daily_data",
                        lambda *a, **k: pytest.fail("the regime pass fetched under off"))
    monkeypatch.setattr(regime_scan, "market_regime_repo",
                        lambda: pytest.fail("the regime pass opened its store under off"))


@pytest.mark.parametrize("mode", ["off", "OFF", "bogus", ""])
def test_off_fetches_nothing_and_never_opens_the_store(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    _no_io(monkeypatch)
    assert regime_scan.regime_for_pass() is None


def test_off_short_lane_carries_no_day_and_touches_nothing(monkeypatch):
    _no_io(monkeypatch)
    monkeypatch.setattr(short_run.shock_scan, "current_label", lambda **k: None)
    lane = short_run._lane_state(*_lane_inputs(monkeypatch), None)
    assert lane["regime_day"] is None
    assert short_run._qualify_context(False, {}, lane).regime_day is None
```

- [ ] **Step 3: Pin the mode for the test session and update the v209 lane dict**

In `tests/conftest.py`, inside `_pin_dotenv_settings`, directly after the `FEED_POSTS_ENABLED` line, add:

```python
    # v239: the bear-regime pass fetches SPY/^VIX and writes market_regime_days;
    # off for every test, the regime tests switch it on with their own fakes.
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "off")
```

In `tests/scanning/test_shock_short_lane.py`, `test_the_lane_state_reads_the_stored_label_once`, the expected dict's last entry `"regimes": "series", "shock_state": "SHOCK"}` becomes `"regimes": "series", "shock_state": "SHOCK", "regime_day": None}`.

- [ ] **Step 4: Run both new files to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_wiring.py`
Expected: failures with `TypeError: _attach_item_plan() got an unexpected keyword argument 'regime_day'` and `AssertionError` on the AST checks (no `regime_for_pass` call yet).

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_off_byte_identical.py`
Expected: the six lane tests fail on `regime_day`; the off-mode `regime_for_pass` tests already pass (V239-8's guard).

- [ ] **Step 5: Wire `scan_run.py`**

1. Add `regime_scan` to `from . import (analyze, dedup, fetch, lane_overlap, progress_store, rejection_recorder, runstate, shock_scan, short_funnel, strategy_pass, telemetry)`, in alphabetical order after `progress_store`.
2. Change `from swingbot.core.planning.params import shock_asof` to `from swingbot.core.planning.params import regime_asof, shock_asof`.
3. `_maybe_run_strategy_pass`: its signature ends `require_confirmation, shock_state: str | None = None, regime_day=None) -> dict:`. In `asof_of`, the comment becomes `# v209/v239: the scan's shock label and regime day ride on every strategy plan's asof.` and the return becomes `return {**rs_asof(ticker), **shock_asof(shock_state), **regime_asof(regime_day)}`.
4. `_attach_item_plan(item, scenario, df, regimes, regime, shock_state=None, regime_day=None)`: pass `regime_day=regime_day` to `analyze.attach_plan_v2` after `shock_state=shock_state`, and add to its docstring: `regime_day` is the pass's RegimeDay (v239), None under BEAR_REGIME_MODE=off.
5. `_rebuild_item(..., require_confirmation, shock_state=None, regime_day=None)`: the attach lambda becomes `attach=lambda s: _attach_item_plan(item, s, df, regimes, regime, shock_state, regime_day)`.
6. In `_sync_run_scan`, directly after the `shock_state = _shock_state_for_pass(...)` statement, add:

```python
    # v239: the bear-regime day for the next session (compute or read, written once,
    # notice only from the winning insert). Never raises; None under
    # BEAR_REGIME_MODE=off or on any failure, and then no plan carries the keys.
    regime_day = regime_scan.regime_for_pass()
```

7. Add `regime_day=regime_day` to the three call sites in `_sync_run_scan`: `_attach_item_plan(..., shock_state=shock_state, regime_day=regime_day)` (confluence merge loop), the `functools.partial(_rebuild_item, ..., shock_state=shock_state, regime_day=regime_day)` (requote), and `_maybe_run_strategy_pass(..., shock_state=shock_state, regime_day=regime_day)`.

- [ ] **Step 6: Wire `short_run.py`**

1. Add `regime_scan` to `from . import (analyze, dedup, fetch, lane_overlap, qualify, rejection_recorder, runstate, scan_run, shock_scan, short_funnel, telemetry)`, after `qualify`.
2. `_qualify_context`: after `shock_state=lane.get("shock_state")`, add `regime_day=lane.get("regime_day")` (same call).
3. `_bare_context(frames, shock_state=None, regime_day=None)`: pass `shock_state=shock_state, regime_day=regime_day`.
4. `_lane_state`: add `"regime_day": regime_scan.regime_for_pass()` as the last entry of the returned dict. The docstring gains: `v239: the bear-regime pass runs here too, once per SHORT run (it reads D's stored row after the scan pass wrote it); None under off or on failure.`

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_wiring.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_off_byte_identical.py`
Expected: `0 failed`.

The v209 neighbours and the scan-wide tests that drive `_sync_run_scan` / the SHORT lane run under the new pin. Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_short_lane.py`,
`python scripts/dev/testrun.py file tests/scanning/test_shock_state_stamp.py`,
`python scripts/dev/testrun.py file tests/scanning/test_shock_plans_byte_identical.py`,
`python scripts/dev/testrun.py file tests/scanning/test_short_lane_split.py`,
`python scripts/dev/testrun.py file tests/scanning/test_run_scan_scan_id.py`.
Expected: `0 failed` each.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `_sync_run_scan` holds at its F 94 baseline, and every other touched function stays under 15.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py tests/conftest.py tests/scanning/test_shock_short_lane.py tests/regime/test_regime_wiring.py tests/regime/test_regime_off_byte_identical.py
git commit -m "feat(v239): run the regime pass on every scan lane and pin the off arm byte-identical"
```

### Task V239-11: Regime line on every alert builder; outlook plans stamped

**Model:** sonnet — one pure helper and four call sites in the alert surface, plus one keyword argument in the outlook context, with placement and byte identity pinned by tests; no decision is left open.

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` (`REGIME_FIELD`, `regime_fields`, `_add_regime_field`; one call in each of `build_embed`, `build_simple_alert`, `build_strategy_alert_embed`, `build_strategy_simple_embed`)
- Modify: `swingbot/core/scanning/outlook_run.py` (`_context` passes `regime_day=regime_scan.regime_for_pass(now=now)` to `QualifyContext`; partner, 2026-11-23: the spec's "every new plan" covers the 23:30 outlook)
- Test: `tests/regime/test_regime_embeds.py`, `tests/regime/test_regime_outlook.py` (create both; suite `market-signals`)

**Interfaces:**
- Consumes (outlook): V239-8 `regime_scan.regime_for_pass(*, now=None, ...) -> RegimeDay | None` (never raises; `None` under `off`/unknown mode, with no fetch and no store); V239-9 `QualifyContext.regime_day` and the stamp it drives through `qualify._attach_plan` -> `attach_plan_v2(regime_day=...)`.
- Consumes: V239-3 `regime_text.alert_line(state: str | None, action: str | None) -> str | None` (the six spec lines, each ≤ `regime_text.MAX_LINE = 80`; `None` for every other pair). V239-9 stamps `entry_context["bear_regime"]` / `["regime_action"]`. This task reads them by name and does not import V239-9.
- Produces (outlook): `outlook_run._context(frames, spy, regime, breadth, bar_date, now)` keeps its signature and returns a context whose `regime_day` is the pass's day for `now`. At 23:30 Berlin, `session_pair(now)` gives D = the outlook's target session.
- Produces (ledger contract, final): `alert_embeds.REGIME_FIELD = "Trend"`; `alert_embeds.regime_fields(plan) -> list[tuple[str, str, bool]]`, which returns `[("Trend", line, False)]` from `getattr(plan, "entry_context", None)` when `alert_line` gives a line, else `[]` (no plan, no context, a non-mapping context, a legacy record, `NORMAL`/`UNKNOWN`, action `none`).

**Placement (spec § Discord alert line, reconciliation 6, index decision 7):**
- `build_embed`: appended to `sections["plan"]` after `_market_on_open_fields(plan_v2)`. It is the last field of the plan section, so it renders under the plan table and above the image and the disclaimer footer. This is one unconditional call in the E 33 legacy function, with no new branch.
- `build_simple_alert`: covers both branches (the v2 ticket and `_legacy_simple_alert`), as the last field after the quote field. `build_ticket_embed`'s own body is untouched (out of scope).
- `build_strategy_alert_embed`: directly after the `Ledger` field.
- `build_strategy_simple_embed`: the last line of the description. It has no fields and still gets none.

The line reads the plan's **own** stamp, never today's state, so a re-posted or old plan keeps the regime it was issued under. Under `off` no plan carries the keys (V239-10), so `regime_fields` is `[]` and every builder's bytes match the pre-v239 output. The last test pins that.

- [ ] **Step 1: Write the failing embed test**

Create `tests/regime/test_regime_embeds.py`:

```python
"""v239 V239-11: one Trend line on every alert builder, under the plan table, <= 80 chars."""
import itertools
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.presentation import ansi, regime_text
from swingbot.core.scanning import alert_embeds, snapshots
from swingbot.core.scanning.alert_embeds import (REGIME_FIELD, build_embed, build_simple_alert,
                                                 build_strategy_alert_embed,
                                                 build_strategy_simple_embed, regime_fields)
from tests.scanning.test_embeds_v3 import PERF_STATS_EMPTY, make_item, make_plan_v2

CASES = [  # (bear_regime, regime_action, plan direction, the spec's line)
    ("BEAR", "would_veto", "bullish", "Regime: Bear (shadow) — engine would skip this long"),
    ("CORRECTION", "would_veto", "bullish", "Regime: Correction · Stress (shadow) — would skip long"),
    ("CORRECTION", "caution", "bullish", "Regime: Correction — dip in an uptrend"),
    ("CORRECTION", "pullback_watch", "bullish", "Regime: Pullback watch — panic easing in a correction"),
    ("BEAR", "aligned", "bearish", "Regime: Bear — with the tape; squeeze risk on rebounds"),
    ("CORRECTION", "aligned", "bearish", "Regime: Correction — short in a dip; uptrend intact"),
]
SILENT = [("NORMAL", "none"), ("UNKNOWN", "none"), ("BEAR", None), (None, None),
          ("CORRECTION", "none"), ("garbage", "would_veto")]
_paths = itertools.count()


def _v2(state=None, action=None, direction="bullish"):
    plan = make_plan_v2(direction=direction)
    plan.entry_context = {"atr_pct": 3.1}
    if state is not None or action is not None:
        plan.entry_context.update(bear_regime=state, regime_action=action)
    return plan


def _strategy_plan(ctx=None):
    plan = SimpleNamespace(plan_id="0123456789ab", ticker="AAPL", strategy="Fibonacci",
                           direction="bullish", horizon_key="4w", trigger_price=100.0,
                           stop_loss=94.0, tp1=110.0, tp2=None, badge="WEAK", ledger="weak",
                           confidence_level=4)
    if ctx is not None:
        plan.entry_context = ctx
    return plan


def _full(plan, monkeypatch, tmp_path):
    # a fresh snapshot file per build, so no "what changed" field appears
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / f"s{next(_paths)}.json"))
    return build_embed(make_item(plan_v2=plan), "why", PERF_STATS_EMPTY, None, None)


def _fields(embed):
    return [(f.name, f.value) for f in embed.fields]


def _bytes(embed):
    doc = embed.to_dict()
    doc.pop("timestamp", None)     # apply_chrome stamps the wall clock
    return doc


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_each_case_gives_its_line_within_the_cap(state, action, direction, line):
    assert regime_fields(_v2(state, action, direction)) == [(REGIME_FIELD, line, False)]
    assert REGIME_FIELD == "Trend" and len(line) <= regime_text.MAX_LINE == 80


@pytest.mark.parametrize("state, action", SILENT)
def test_no_line_outside_the_table(state, action):
    assert regime_fields(_v2(state, action)) == []


@pytest.mark.parametrize("plan", [None, SimpleNamespace(), SimpleNamespace(entry_context=None),
                                  SimpleNamespace(entry_context="CORRECTION"), _v2()])
def test_no_line_without_a_readable_stamp(plan):
    assert regime_fields(plan) == []


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_full_embed_adds_one_field_at_the_end_of_the_plan_section(
        monkeypatch, tmp_path, state, action, direction, line):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(alert_embeds, "_market_on_open_fields", lambda plan: [("MOO", "x", False)])
    plain = _full(_v2(direction=direction), monkeypatch, tmp_path)
    stamped = _full(_v2(state, action, direction), monkeypatch, tmp_path)
    names = [name for name, _ in _fields(stamped)]
    assert names.index(REGIME_FIELD) == names.index("MOO") + 1      # directly under the plan table
    assert [f for f in _fields(stamped) if f[0] != REGIME_FIELD] == _fields(plain)
    assert (REGIME_FIELD, line) in _fields(stamped)
    assert stamped.description == plain.description and stamped.footer.text == plain.footer.text
    assert stamped.to_dict().get("image") == plain.to_dict().get("image")


@pytest.mark.parametrize("engine", ["on", "shadow"])          # the v2 ticket, the legacy mirror
@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_simple_alert_ends_with_the_line_on_both_branches(
        monkeypatch, engine, state, action, direction, line):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", engine)
    plain = build_simple_alert(make_item(plan_v2=_v2(direction=direction)))
    stamped = build_simple_alert(make_item(plan_v2=_v2(state, action, direction)))
    assert _fields(stamped) == [*_fields(plain), (REGIME_FIELD, line)]
    assert stamped.description == plain.description


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_strategy_embed_puts_the_line_after_the_ledger(state, action, direction, line):
    embed = build_strategy_alert_embed(_strategy_plan({"bear_regime": state, "regime_action": action}))
    assert _fields(embed)[-2:] == [("Ledger", "weak — P&L tracked separately, never summed into main"),
                                   (REGIME_FIELD, line)]


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_strategy_simple_embed_ends_its_description_with_the_line(state, action, direction, line):
    plain = build_strategy_simple_embed(_strategy_plan())
    embed = build_strategy_simple_embed(_strategy_plan({"bear_regime": state, "regime_action": action}))
    assert embed.description == f"{plain.description}\n{line}"
    assert ansi._ESCAPE_RE.sub("", embed.description).splitlines()[-1] == line
    assert not embed.fields


@pytest.mark.parametrize("engine", ["on", "shadow"])
@pytest.mark.parametrize("ctx", [None, {}, {"atr_pct": 3.1}, {"bear_regime": "NORMAL", "regime_action": "none"}])
def test_without_a_line_every_builder_is_byte_identical_to_pre_v239(monkeypatch, tmp_path, engine, ctx):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", engine)

    def build_all():
        v2 = make_plan_v2()
        if ctx is not None:
            v2.entry_context = dict(ctx)
        strategy = _strategy_plan(None if ctx is None else dict(ctx))
        return [_bytes(_full(v2, monkeypatch, tmp_path)), _bytes(build_simple_alert(make_item(plan_v2=v2))),
                _bytes(build_strategy_alert_embed(strategy)), _bytes(build_strategy_simple_embed(strategy))]

    now = build_all()
    monkeypatch.setattr(alert_embeds, "regime_fields", lambda plan: [])     # the pre-v239 builders
    assert now == build_all()
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_embeds.py`
Expected: collection error, `ImportError: cannot import name 'REGIME_FIELD' from 'swingbot.core.scanning.alert_embeds'`.

- [ ] **Step 3: Add the helper to `swingbot/core/scanning/alert_embeds.py`**

Add `from collections.abc import Mapping` to the standard-library imports, and `from swingbot.core.presentation import regime_text` beside `from swingbot.core.presentation import kinds`. Directly after `_market_on_open_fields`, add:

```python
#: v239: the alert's regime line (shadow): what the engine WOULD do, never an order.
REGIME_FIELD = "Trend"


def regime_fields(plan) -> list:
    """``[("Trend", line, False)]`` from the plan's OWN entry_context stamp, else [].

    Never today's state: an old plan keeps the regime it was issued under. A plan
    without the keys (BEAR_REGIME_MODE off, or a record from before v239) gets
    nothing, so every builder renders exactly as before."""
    ctx = getattr(plan, "entry_context", None)
    if not isinstance(ctx, Mapping):
        return []
    line = regime_text.alert_line(ctx.get("bear_regime"), ctx.get("regime_action"))
    return [(REGIME_FIELD, line, False)] if line else []


def _add_regime_field(embed, plan) -> None:
    for name, value, inline in regime_fields(plan):
        embed.add_field(name=name, value=value, inline=inline)
```

`regime_fields` must be called through the module global (as written), so the byte-identity test can stand in the pre-v239 `[]`.

- [ ] **Step 4: Wire the four builders**

1. `build_strategy_alert_embed`: after the `embed.add_field(name="Ledger", ...)` statement and before `return embed`, add `_add_regime_field(embed, plan)   # v239: after the ledger`.
2. `build_strategy_simple_embed`: change `description = "\n".join([description, *market_on_open_lines(plan)])` to
   `description = "\n".join([description, *market_on_open_lines(plan), *(line for _, line, _ in regime_fields(plan))])`.
3. `build_embed`: directly after `sections["plan"].extend(_market_on_open_fields(plan_v2))`, add
   `sections["plan"].extend(regime_fields(plan_v2))   # v239: the last plan-table field`.
4. `build_simple_alert`: after `_add_quote_field(embed, item)` and before `return embed`, add `_add_regime_field(embed, plan_v2)   # v239: both branches`.

- [ ] **Step 5: Stamp the 23:30 outlook plans**

Create `tests/regime/test_regime_outlook.py`:

```python
"""v239 V239-11 (partner): the 23:30 outlook plans carry the regime stamp too; off stamps nothing."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.scanning import analyze, outlook_run as orun, qualify, regime_scan
from tests.scanning.test_shock_plans_byte_identical import FRAME, _canon, _long_item, _long_plan

FRIDAY = dt.date(2026, 10, 9)
NOW = dt.datetime(2026, 10, 11, 21, 30, tzinfo=dt.timezone.utc)      # Sunday 23:30 Berlin
DAY = br.RegimeDay(session_date=dt.date(2026, 10, 12), last_bar_date=FRIDAY,
                   state=br.CORRECTION, stress=False)


@pytest.fixture(autouse=True)
def _gate_inputs(monkeypatch):
    monkeypatch.setattr(orun, "_sector_inputs", lambda tickers, bar, now: ({}, {}, {}))
    monkeypatch.setattr(orun, "_regimes", lambda spy: None)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")


def _no_io(monkeypatch):
    monkeypatch.setattr(regime_scan, "get_daily_data",
                        lambda *a, **k: pytest.fail("the outlook fetched under off"))
    monkeypatch.setattr(regime_scan, "market_regime_repo",
                        lambda: pytest.fail("the outlook opened the regime store under off"))


def _context():
    return orun._context({"AAPL": FRAME}, "spy", None, None, FRIDAY, NOW)


def _plan_from(context):
    item = _long_item()
    qualify._attach_plan(item, context)
    return item.plan_v2


def test_shadow_runs_the_pass_once_at_the_outlook_clock_and_stamps_the_plan(monkeypatch):
    calls = []
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: calls.append(k) or DAY)
    context = _context()
    assert calls == [{"now": NOW}] and context.regime_day is DAY
    ctx = _plan_from(context).entry_context
    assert (ctx["bear_regime"], ctx["regime_action"]) == ("CORRECTION", "caution")


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_fetches_nothing_and_the_plan_differs_only_by_the_two_keys(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    with monkeypatch.context() as m:
        _no_io(m)
        context = _context()
        assert context.regime_day is None
        off = _plan_from(context)
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: DAY)
    shadow = _plan_from(_context())
    assert not {"bear_regime", "regime_action"} & set(off.entry_context)
    assert shadow.entry_context.pop("bear_regime") == "CORRECTION"
    assert shadow.entry_context.pop("regime_action") == "caution"
    assert _canon(off) == _canon(shadow)
```

In `swingbot/core/scanning/outlook_run.py`:
1. Add `regime_scan` to `from . import (analyze, dedup, fetch, lane_overlap, outlook_context, outlook_embeds, outlook_session, qualify, scan_run, short_run)`, after `qualify`.
2. In `_context`, add `regime_day=regime_scan.regime_for_pass(now=now)` as the last keyword of the `qualify.QualifyContext(...)` call, with the comment `# v239: outlook plans carry the bear-regime stamp; None under off (no fetch, no store)`.

`_fill` calls `_context` once per run, so the pass runs once per outlook. At 23:30 it usually reads D's row, which the after-close scan pass has already written.

- [ ] **Step 6: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_embeds.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_outlook.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_run.py`
Expected: `0 failed`. V239-10's test-wide `off` pin keeps `regime_day` None, so the existing context assertions hold.

The existing builder tests run on records with no stamp, so their output is unchanged. Run each:
`python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`,
`python scripts/dev/testrun.py file tests/scanning/test_embed_quote_line.py`,
`python scripts/dev/testrun.py file tests/scanning/test_strategy_embeds.py`,
`python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py`,
`python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py`.
Expected: `0 failed` each.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. `build_embed` holds at its E 33 baseline, and the three other builders stay at A.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/outlook_run.py tests/regime/test_regime_embeds.py tests/regime/test_regime_outlook.py
git commit -m "feat(v239): Trend line on every alert builder, regime stamp on outlook plans"
```

### Task V239-12: `GET /api/v1/market/regime` and its access row

**Model:** sonnet — a read-only endpoint on the `api_v1` pattern over a fixed wire shape; every value comes from functions earlier tasks own.

**Files:**
- Create: `swingbot/admin/api_v1/market_regime.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (add `market_regime` to the endpoint-module import list in `register()`)
- Modify: `tests/admin/access_expectations.py` (`"/market/regime"` in `_VIEWER_GET`)
- Test: `tests/admin/test_api_v1_market_regime.py` (create; suite `admin`)

**Interfaces:**
- Consumes: V239-2 `bear_regime.RegimeDay.from_row(row)`, `ROW_COLUMNS` (the 16 columns: `session_date`, `last_bar_date`, `state`, `stress`, `pullback_trigger`, `pullback_reason`, eight floats, `spy_provider`, `vix_provider`); V239-3 `regime_episodes.episode_key(state, stress)`, `current_episode(days) -> Episode | None` (`.key`, `.sessions`), `regime_text.LABELS`, `regime_text.display(day) -> {"label", "words", "numbers"}`; V239-4 `regime_calendar.session_pair(now) -> (s, D)`; V239-5 `regime_scan.regime_mode()`; V239-6b `market_regime.market_regime_repo().recent(limit) -> list[dict]` (oldest first; each row is the 16 columns + `computed_at` (aware datetime) + `doc`); `api_v1.iso(datetime | None) -> str | None`; `auth.require_auth`.
- Produces (ledger contract, final; V239-13 types it in the SPA):
  - `GET /api/v1/market/regime` returns JSON `{mode: str, today: RegimeDayWire | null, history: RegimeDayWire[≤60] (oldest first), episode: {label: str, since_sessions: int} | null}`.
  - `RegimeDayWire` = the 16 `ROW_COLUMNS` (dates as ISO strings) + `computed_at` (ISO) + `display: {label: str, words: str, numbers: str | null}`. It has no `doc`.
  - `market_regime.HISTORY_LIMIT = 60`; `market_regime.EPISODE_ROWS = 500`; `regime_payload(now=None, repo=None) -> dict`.

**Rules (spec § API, index decision 5, Global Constraints):**
- `off` or an unknown mode returns `{mode: "off", today: null, history: [], episode: null}` without opening the store. `live` reports `"live"` and otherwise behaves like `shadow`.
- `today` is the stored row whose `session_date` equals the current `D` from `session_pair(now)`, else `null`. The admin process never fetches or computes a label.
- An unreadable store (or a `session_pair` failure past the frozen calendar) returns the empty shape under the real mode and is logged as `admin.market_regime.read`. The banner then hides and never shows a stale label.
- `episode` is the confirmed episode over the last `EPISODE_ROWS` stored rows, not just the 60 history rows. A BEAR longer than 60 sessions still counts "since" from its first day. Rows are one per session, so 500 rows is about two years; an episode longer than that reads as 500. The label comes from `regime_text.LABELS` (`"Correction · Stress"`, `"Bear"`, `"Normal"`, `"No reading"`).

- [ ] **Step 1: Write the failing API test**

Create `tests/admin/test_api_v1_market_regime.py`:

```python
"""v239 V239-12: GET /api/v1/market/regime -- the stored day for D, 60 sessions, the episode."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.admin.api_v1 import iso
from swingbot.core.db.repositories import market_regime as regime_repo
from swingbot.core.market import bear_regime as br
from swingbot.core.presentation import regime_text
from swingbot.core.scanning import regime_calendar
from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape

URL = "/api/v1/market/regime"
NOW = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)     # after the 11-18 close: D = 11-19
D = date(2026, 11, 19)
T0 = datetime(2026, 11, 18, 21, 5, 30, tzinfo=timezone.utc)
EMPTY_OFF = {"mode": "off", "today": None, "history": [], "episode": None}
FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
          "vix_close", "vix_max5")
WIRE = {"session_date": str, "last_bar_date": NULLABLE_STR, "state": str,
        "stress": (bool, type(None)), "pullback_trigger": bool, "pullback_reason": NULLABLE_STR,
        **{name: NULLABLE_NUMBER for name in FLOATS}, "spy_provider": NULLABLE_STR,
        "vix_provider": NULLABLE_STR, "computed_at": str, "display": dict}
NUMBERS = dict(spy_close=650.0, sma50=716.0, sma200=690.0, vix_close=37.6)


def _row(day, state="CORRECTION", stress=True, **over):
    row = {name: None for name in br.ROW_COLUMNS}
    row.update(session_date=day, last_bar_date=day - timedelta(days=1), state=state, stress=stress,
               pullback_trigger=False, spy_provider="alpaca", vix_provider="yfinance",
               computed_at=T0, doc={"unknown_reason": None}, **NUMBERS)
    row.update(over)
    return row


def _rows(states, end=D):
    """One row per state, oldest first, the last dated ``end`` (calendar days are enough here)."""
    return [_row(end - timedelta(days=len(states) - 1 - i), *state)
            for i, state in enumerate(states)]


class _Repo:
    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.calls = list(rows), fail, []

    def recent(self, limit=60, *, conn=None):
        self.calls.append(limit)
        if self.fail:
            raise RuntimeError("db down")
        return self.rows[-limit:]


@pytest.fixture
def shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "shadow")


@pytest.fixture(autouse=True)
def _app_loaded(admin_app):
    """app.py's body runs first, so register() imports the endpoint module whole."""
    yield


def _api():
    # endpoint modules load after app.py's body (circular-import note in api_v1/__init__.py)
    from swingbot.admin.api_v1 import market_regime
    return market_regime


def _payload(repo, now=NOW):
    return _api().regime_payload(now=now, repo=repo)


def test_the_wire_restates_the_classifier_row():
    assert set(WIRE) - {"computed_at", "display"} == set(br.ROW_COLUMNS)
    assert (_api().HISTORY_LIMIT, _api().EPISODE_ROWS) == (60, 500)


@pytest.mark.parametrize("mode", ["off", "bogus", ""])
def test_off_or_an_unknown_mode_sends_the_empty_shape_and_reads_nothing(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    repo = _Repo(_rows([("CORRECTION", True)]))
    assert _payload(repo) == EMPTY_OFF and repo.calls == []


def test_an_empty_table_sends_no_day_and_no_history(shadow):
    assert _payload(_Repo()) == {"mode": "shadow", "today": None, "history": [], "episode": None}


def test_today_is_the_stored_row_for_d_with_its_display(shadow):
    body = _payload(_Repo(_rows([("CORRECTION", True)] * 3)))
    today = body["today"]
    assert (today["session_date"], today["last_bar_date"]) == ("2026-11-19", "2026-11-18")
    assert today["computed_at"] == iso(T0) and "doc" not in today
    assert today["display"] == {"label": "Correction · Stress", "words": "dip in an uptrend, high volatility",
                                "numbers": regime_text.number_line(**NUMBERS)}


def test_no_row_for_d_means_no_today_and_never_the_prior_label(shadow):
    body = _payload(_Repo(_rows([("BEAR", None)] * 3, end=D - timedelta(days=1))))
    assert body["today"] is None and len(body["history"]) == 3


def test_an_unknown_day_reads_no_reading(shadow):
    row = _row(D, "UNKNOWN", None, **{name: None for name in FLOATS})
    today = _payload(_Repo([row]))["today"]
    assert today["display"] == {"label": "No reading", "words": "—", "numbers": None}
    assert all(today[name] is None for name in FLOATS)


def test_history_is_the_last_60_oldest_first(shadow):
    rows = _rows([("NORMAL", False)] * 70)
    history = _payload(_Repo(rows))["history"]
    assert len(history) == 60
    assert history[0]["session_date"] == rows[10]["session_date"].isoformat()
    assert [h["session_date"] for h in history] == sorted(h["session_date"] for h in history)


@pytest.mark.parametrize("states, episode", [
    ([("NORMAL", False)] * 3 + [("CORRECTION", True)] * 4, {"label": "Correction · Stress", "since_sessions": 4}),
    ([("NORMAL", False)] * 3 + [("CORRECTION", False)] + [("NORMAL", False)] * 3,   # flicker merges
     {"label": "Normal", "since_sessions": 7}),
    ([("CORRECTION", False)] * 2 + [("CORRECTION", True)] * 2, {"label": "Correction · Stress", "since_sessions": 2}),
    ([("BEAR", None)], None)])                                                      # one session: unconfirmed
def test_the_episode_is_the_confirmed_run(shadow, states, episode):
    assert _payload(_Repo(_rows(states)))["episode"] == episode


def test_the_episode_counts_past_the_history_window(shadow):
    repo = _Repo(_rows([("BEAR", None)] * 100))
    body = _payload(repo)
    assert repo.calls == [_api().EPISODE_ROWS]
    assert len(body["history"]) == 60 and body["episode"] == {"label": "Bear", "since_sessions": 100}


def test_live_reports_live(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "live")
    assert _payload(_Repo(_rows([("BEAR", None)] * 2)))["mode"] == "live"


@pytest.mark.parametrize("breakage", ["store", "calendar"])
def test_an_unreadable_store_or_calendar_sends_nothing_stale(shadow, monkeypatch, breakage):
    repo = _Repo(_rows([("BEAR", None)] * 3), fail=breakage == "store")
    if breakage == "calendar":
        def past_the_calendar(now):
            raise ValueError("no NYSE session after 2030-12-31 in the frozen calendar")
        monkeypatch.setattr(regime_calendar, "session_pair", past_the_calendar)
    assert _payload(repo) == {"mode": "shadow", "today": None, "history": [], "episode": None}


def test_the_endpoint_requires_auth(client):
    assert_error(client.get(URL), "auth", 401)


def test_the_endpoint_shape(client, auth, shadow, monkeypatch):
    monkeypatch.setattr(regime_repo, "market_regime_repo", lambda: _Repo(_rows([("CORRECTION", True)] * 3)))
    monkeypatch.setattr(regime_calendar, "session_pair", lambda now: (D - timedelta(days=1), D))
    response = client.get(URL, headers=auth)
    assert response.status_code == 200
    body = response.get_json()
    assert_shape(body, {"mode": str, "today": dict, "history": list, "episode": dict})
    for day in (body["today"], *body["history"]):
        assert_shape(day, WIRE, where="day")
        assert_shape(day["display"], {"label": str, "words": str, "numbers": NULLABLE_STR}, where="display")
    assert_shape(body["episode"], {"label": str, "since_sessions": int}, where="episode")


def test_the_endpoint_under_off_reads_nothing(client, auth, monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "off")
    monkeypatch.setattr(regime_repo, "market_regime_repo", lambda: pytest.fail("off read the store"))
    assert client.get(URL, headers=auth).get_json() == EMPTY_OFF
```

- [ ] **Step 2: Run it to see it fail**

Run `/replicate-prod-db` first, if no earlier task in this session has synced the shared `swing-db` container (the admin app fixture can reach Postgres). Then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_market_regime.py`
Expected: collection error, `ImportError: cannot import name 'market_regime' from 'swingbot.admin.api_v1'`.

- [ ] **Step 3: Write `swingbot/admin/api_v1/market_regime.py`**

Module docstring: `v239: GET /market/regime -- the bear-regime day for the next session, the last 60 stored sessions and the confirmed episode, in the shared vocabulary. Read-only: the admin process never fetches market data or computes a label (index decision 5). Core imports live inside the functions (the circular-import note in api_v1/__init__.py).`

```python
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from flask import jsonify

from . import api_v1, iso
from .auth import require_auth

log = logging.getLogger(__name__)

HISTORY_LIMIT = 60
#: Stored rows read for the episode's "since" count (about two years of sessions),
#: so an episode longer than the 60-row history still counts from its first day.
EPISODE_ROWS = 500


def _empty(mode: str) -> dict:
    return {"mode": mode, "today": None, "history": [], "episode": None}


def _wire(row: Mapping) -> dict:
    from swingbot.core.market import bear_regime as br
    from swingbot.core.presentation import regime_text

    day = br.RegimeDay.from_row(row)
    wire = {name: getattr(day, name) for name in br.ROW_COLUMNS}
    for name in ("session_date", "last_bar_date"):
        wire[name] = None if wire[name] is None else wire[name].isoformat()
    return {**wire, "computed_at": iso(row.get("computed_at")), "display": regime_text.display(day)}


def _episode(rows: Sequence[Mapping]) -> dict | None:
    from swingbot.core.market import bear_regime as br
    from swingbot.core.market import regime_episodes as ep
    from swingbot.core.presentation import regime_text

    days = [(br.RegimeDay.from_row(row).session_date, ep.episode_key(row["state"], row.get("stress")))
            for row in rows]
    current = ep.current_episode(days)
    if current is None:
        return None
    return {"label": regime_text.LABELS[current.key], "since_sessions": current.sessions}


def regime_payload(now: datetime | None = None, repo=None) -> dict:
    """The /market/regime body. `off` (or an unknown mode) reads nothing; an
    unreadable store answers the empty shape, never a stale label."""
    from swingbot.core.db.repositories import market_regime as regime_repo
    from swingbot.core.infra.swallowed import swallowed
    from swingbot.core.scanning import regime_calendar
    from swingbot.core.scanning.regime_scan import regime_mode

    mode = regime_mode()
    if mode == "off":
        return _empty("off")
    try:
        rows = list((repo or regime_repo.market_regime_repo()).recent(EPISODE_ROWS))
        _, target = regime_calendar.session_pair(now or datetime.now(timezone.utc))
    except Exception as exc:
        swallowed(log, "admin.market_regime.read", exc, "regime: store or calendar unreadable: %s", exc)
        return _empty(mode)
    history = [_wire(row) for row in rows[-HISTORY_LIMIT:]]
    today = next((day for day in history if day["session_date"] == target.isoformat()), None)
    return {"mode": mode, "today": today, "history": history, "episode": _episode(rows)}


@api_v1.route("/market/regime", methods=["GET"])
@require_auth
def market_regime_view():
    return jsonify(regime_payload())
```

`regime_repo.market_regime_repo` and `regime_calendar.session_pair` are reached through their modules at call time, so the tests' `monkeypatch` on those modules takes effect.

- [ ] **Step 4: Register the module and the access row**

1. In `swingbot/admin/api_v1/__init__.py`, `register()`: in the `from . import (access_hook, analytics, ..., market, market_updates, ...)` list, add `market_regime` after `market`.
2. In `tests/admin/access_expectations.py`, `_VIEWER_GET`: change `"/market/chart/<ticker>", "/market/tape", "/market/updates",` to `"/market/chart/<ticker>", "/market/regime", "/market/tape", "/market/updates",`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_market_regime.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/admin/test_access_contract.py`
Expected: `0 failed`. The new viewer GET is declared, so the v207 contract passes.

Run: `python -m radon cc -s -n C swingbot/admin/api_v1/market_regime.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/api_v1/market_regime.py swingbot/admin/api_v1/__init__.py tests/admin/access_expectations.py tests/admin/test_api_v1_market_regime.py
git commit -m "feat(v239): GET /api/v1/market/regime -- stored day for D, 60 sessions, confirmed episode"
```

