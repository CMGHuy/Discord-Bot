# v135 Headroom veto -- part 2: funnel tooling and measurement

> Part of `2026-10-06-v135-headroom-veto_0-index.md` (header, where to work, global constraints, file map, review focus and `## Parallelisation` live there). Read that index's Global Constraints with every task. Steps use `- [ ]` for tracking. All paths are relative to the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v135-headroom-veto` unless a step says `main`.

**Spec:** `docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md`

# Phase 3 — Funnel tooling

v122 built the Stage 1 judge, the clause-6 baseline reading for its own predicate, and the clause-5 arm-pair permutation. This phase adds only what the headroom predicate needs from that tooling. `permutation_test.py` is not edited.

### Task V135-8: Extract `scenarios_at` from `replay_scenarios` (no behaviour change)

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (new `bucket_bar`, new `scenarios_at`, and the head of the loop in `replay_scenarios`)
- Modify: `tests/backtesting/test_backtest_scenarios.py` (append tests)
- Modify: `tests/scripts/test_fvg_attribution.py` (`test_replay_still_has_the_shape_the_recorder_patches`, Step 3)

**Interfaces:**
- Consumes: `levels_asof`, `LEVEL_REFRESH_BARS`, `scenario_gate_inputs`, `dead_cat_bounce`, `levels.build_scenarios`, `levels.atr_floor_pct` (all already imported in the module); `_headroom_kept` (V135-5); the V135-3 witness.
- Produces:
  - `backtest_scenarios.bucket_bar(index: int, horizon_key: str) -> int`: the bar whose as-of map the replay loop has cached for `index`'s bucket
  - `backtest_scenarios.scenarios_at(ticker, df, i, horizon_key, params, cache, dcb_params=None) -> tuple`: `(window, price, supports, resistances, scenarios)` at bar `i`, before any admission gate
- Why: V135-10 must rebuild, for one baseline confluence trade, the exact scenario and the exact support/resistance lists the replay had at that bar. Extracting the replay's own code is the only way that rebuild cannot drift from it. `scripts/backtest/measure_fib_anchor_diagnostic.py` holds an older private copy of the bucket rule (`bucket_bar`, `scenario_map`); it is left alone.

**Cross-plan (audit 2026-10-10):** v146 V146-7 may have moved `replay_scenarios`' body into `replay_scenarios_detailed` and helpers. Check `git grep -n "def replay_scenarios_detailed\|def _bar_scenarios" -- swingbot/core/backtesting/backtest_scenarios.py`. **If both exist (v146 merged),** Step 3's `replay_scenarios` replacement does not apply: `scenarios_at` takes `_bar_scenarios`' pre-gate body (everything from `window = df.iloc[:i + 1]` through the `levels.build_scenarios(...)` call, with `scope.ticker` / `scope.horizon_key` / `scope.params` / `scope.h` read as the plain arguments), and `_bar_scenarios` becomes

```python
    window, price, supports, resistances, scenarios = scenarios_at(
        scope.ticker, df, i, scope.horizon_key, scope.params, cache, dcb_params)
    return window, price, (supports, resistances), _headroom_kept(_dryup_kept(scenarios, window), supports, resistances)
```

(it applies the dry-up and headroom gates, so it cannot simply wrap `scenarios_at`). Step 4's radon line then greps `_bar_scenarios|scenarios_at|bucket_bar` and expects all below 15. **Otherwise** as written. The Complexity gate (owner v149) applies to this extraction: if `scripts/dev/complexity_gate.py` exists, finish Step 4 with `python scripts/dev/complexity_gate.py`, then `--update`, and commit `scripts/dev/complexity_baseline.json` in Step 5 (`improved` expected; `new`/`risen` never).

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests** (append to `tests/backtesting/test_backtest_scenarios.py`)

```python
def test_bucket_bar_is_the_first_bar_the_replay_visits_in_the_bucket():
    from swingbot.core.market.strategy_types import MIN_BARS

    warmup = MIN_BARS["4w"]
    first_full = (warmup // bs.LEVEL_REFRESH_BARS + 1) * bs.LEVEL_REFRESH_BARS
    assert bs.bucket_bar(first_full, "4w") == first_full
    assert bs.bucket_bar(first_full + 4, "4w") == first_full
    assert bs.bucket_bar(first_full + 5, "4w") == first_full + 5
    assert bs.bucket_bar(warmup, "4w") == warmup          # never before warm-up
    assert bs.bucket_bar(warmup + 1, "4w") >= warmup


def test_scenarios_at_rebuilds_what_the_replay_saw_at_each_plan_bar():
    from swingbot.scan_params import ScanParams
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    frame = load_v74_fixture()["AAPL"]
    params = ScanParams.from_config()
    plans = bs.replay_scenarios("AAPL", frame, "4w", params=params)
    assert plans, "fixture must produce confluence plans or the test proves nothing"
    for index, plan in plans[:20]:
        cache = {}
        bs.levels_asof("AAPL", frame, bs.bucket_bar(index, "4w"), "4w", cache)   # prime the bucket
        window, price, supports, resistances, scenarios = bs.scenarios_at(
            "AAPL", frame, index, "4w", params, cache)
        assert len(window) == index + 1
        assert price == float(frame["Close"].iloc[index])
        assert all(level.price < price for level in supports)
        assert all(level.price > price for level in resistances)
        assert any(scenario.direction == plan.direction for scenario in scenarios)


def test_scenarios_at_ignores_every_later_bar():
    """NO-LOOKAHEAD: rewriting the frame after bar i leaves bar i's scenarios unchanged."""
    from swingbot.scan_params import ScanParams
    from tests.backtesting.test_v74_fixture import load_v74_fixture

    frame, params, index = load_v74_fixture()["AAPL"], ScanParams.from_config(), 300
    poisoned = frame.copy()
    poisoned.iloc[index + 1:] = poisoned.iloc[index + 1:] * 10.0
    clean = bs.scenarios_at("AAPL", frame, index, "4w", params, {})
    dirty = bs.scenarios_at("AAPL", poisoned, index, "4w", params, {})
    assert clean[1:] == dirty[1:]
```

If `tests/backtesting/test_backtest_scenarios.py` does not already import the module as `bs`, check its imports with `grep -n "^from\|^import" tests/backtesting/test_backtest_scenarios.py` and use the alias it has.

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`
Expected: FAIL with `AttributeError: ... has no attribute 'bucket_bar'`.

- [ ] **Step 3: Implement**

In `backtest_scenarios.py`, add directly below `levels_asof`:

```python
def bucket_bar(index: int, horizon_key: str) -> int:
    """The bar whose as-of map replay_scenarios has cached for `index`'s bucket: the first
    bar of that LEVEL_REFRESH_BARS bucket the loop visits (never before warm-up)."""
    return max(MIN_BARS[horizon_key], (index // LEVEL_REFRESH_BARS) * LEVEL_REFRESH_BARS)


def scenarios_at(ticker: str, df, i: int, horizon_key: str, params, cache: dict,
                 dcb_params: dict | None = None):
    """(window, price, supports, resistances, scenarios) at bar i, before any admission gate.

    NO-LOOKAHEAD: reads df.iloc[:i + 1] and levels_asof's as-of map only. The map is the one
    cached for i's bucket, re-split against this bar's own price because the bucket can lag.
    A caller that asks for one bar out of order must first prime the bucket the way the
    replay loop does: levels_asof(ticker, df, bucket_bar(i, horizon_key), horizon_key, cache).
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
    # v68. dcb_params=None is the baseline arm and must not pay for the detector at all.
    block_bullish = dcb_params is not None and bool(dead_cat_bounce(window, dcb_params)["detected"])
    scenarios = levels.build_scenarios(
        price, supports, resistances, gate_inputs["min_reward_pct"],
        atr_floor=floor_pct,
        min_stop_distance_pct=gate_inputs["min_stop_distance_pct"],
        max_stop_distance_pct=gate_inputs["max_stop_distance_pct"],
        min_risk_reward=gate_inputs["min_risk_reward"],
        block_bullish=block_bullish)
    return window, price, supports, resistances, scenarios
```

In `replay_scenarios`, replace everything from `window = df.iloc[:i + 1]` through the `scenarios = _headroom_kept(scenarios, supports, resistances)` line (the window, price, `levels_asof` call, the re-split, `floor_pct`, the `gates = scenario_gate_inputs(...)` rebinding, the `block_bullish` block, the `levels.build_scenarios(...)` call and the two gate lines) with:

```python
        window, price, supports, resistances, scenarios = scenarios_at(
            ticker, df, i, horizon_key, params, cache, dcb_params)
        scenarios = _dryup_kept(scenarios, window)
        scenarios = _headroom_kept(scenarios, supports, resistances)
```

Leave the lines above the loop (`h = HORIZONS[horizon_key]`, `warmup`, `cooldown`, `cache`, `out`, `last_accepted`) and the whole `for sc in scenarios:` body untouched: the body still reads `window`, `h`, `price`, `supports`, `resistances` and `i`. Move the two explanatory comments about the re-split into `scenarios_at`'s docstring rather than keeping a duplicate.

The recorder shape test reads `replay_scenarios`' own source, which no longer holds the `levels_asof(...)` call after this extraction. In `tests/scripts/test_fvg_attribution.py` (about lines 109-113), rewrite `test_replay_still_has_the_shape_the_recorder_patches` to read the whole module (v146 V146-7 makes the same update; if it is already updated this way, keep it):

```python
def test_replay_still_has_the_shape_the_recorder_patches():
    src = inspect.getsource(bs)
    assert "levels_asof(" in src
    assert "build_confluence_plan(" in src
    assert getattr(bs, "REPLAY_CONFLUENCE_TOLERANCE_PCT", 5.0) == 5.0 == fa.VOTE_TOLERANCE_PCT
```

- [ ] **Step 4: Run the narrow tests, both witnesses and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`, then `... file tests/backtesting/test_headroom_witness.py`, `... file tests/backtesting/test_pullback_dryup_witness.py`, `... file tests/backtesting/arms/test_confluence_engine.py`, `... file tests/backtesting/test_armed_replay.py`, `... file tests/scripts/test_fvg_attribution.py`, then `python -m radon cc -s swingbot/core/backtesting/backtest_scenarios.py | grep -E "replay_scenarios|scenarios_at|bucket_bar"`
Expected: all PASS with both witnesses byte-identical. `replay_scenarios` drops to C (14) or lower (it lost the `dcb_params` branch), `scenarios_at` A or B, `bucket_bar` A. A witness failure means the extraction changed behaviour: fix the extraction.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_backtest_scenarios.py tests/scripts/test_fvg_attribution.py
git commit -m "refactor(v135): extract scenarios_at from replay_scenarios, byte-identical"
```

### Task V135-9: A tie preference for `select_cell`

**Files:**
- Modify: `swingbot/core/backtesting/arms/selection.py` (`_selection_rank`, `select_cell`)
- Modify: `tests/backtesting/arms/test_selection.py` (append tests)

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `select_cell(cells, param_name, *, tie="larger")`. `tie="larger"` (the default) is v122's rule, where a larger `d` is the smaller cut. `tie="smaller"` is v135's rule, where a smaller `h` is the smaller cut. Any other value raises `ValueError`.
- Witness: the existing `test_tie_prefers_larger_value` and `tests/backtesting/test_validate_component_selection.py` already pin the default. They must pass unedited.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtesting/arms/test_selection.py`)

```python
def test_tie_can_prefer_the_smaller_value():
    """v135: a smaller h is the smaller cut, so the tie goes the other way from v122's d."""
    cells = [cell(.5), cell(.75), cell(1.0)]
    assert select_cell(cells, 'h', tie='smaller').selected == .5


def test_default_tie_still_prefers_the_larger_value():
    """v122 witness: the default rule is unchanged by the tie parameter."""
    cells = [cell(.5), cell(.75), cell(1.0)]
    assert select_cell(cells, 'd').selected == 1.0
    assert select_cell(cells, 'd', tie='larger').selected == 1.0


def test_tie_preference_never_overrides_a_larger_improvement():
    cells = [cell(.5, 1), cell(.75, 2), cell(1.0, 3)]
    assert select_cell(cells, 'h', tie='smaller').selected == 1.0


def test_an_unknown_tie_rule_is_refused():
    with pytest.raises(ValueError):
        select_cell([cell(.5), cell(.75)], 'h', tie='nearest')
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_selection.py`
Expected: FAIL with `TypeError: select_cell() got an unexpected keyword argument 'tie'`.

- [ ] **Step 3: Implement**

In `selection.py`, replace `_selection_rank` and `select_cell` with:

```python
_TIE_SIGN = {'larger': 1.0, 'smaller': -1.0}


def _selection_rank(candidate, tie_sign=1.0):
    cell, _ = candidate
    improvement = float('-inf') if cell.delta_win_rate_pp is None else cell.delta_win_rate_pp
    return improvement, tie_sign * cell.value


def select_cell(cells, param_name, *, tie='larger'):
    """Select maximum dWR among eligible adjacent plateaus. A tie goes to the smaller cut:
    the larger value by default (v122's d), the smaller one with tie='smaller' (v135's h)."""
    if tie not in _TIE_SIGN:
        raise ValueError(f"tie must be one of {sorted(_TIE_SIGN)}, got {tie!r}")
    ordered = sorted(cells, key=lambda cell: cell.value)
    if not any(cell.eligible for cell in ordered):
        return Selection(ordered, None, None, NO_ELIGIBLE)
    candidates = _plateau_candidates(ordered, param_name)
    if not candidates:
        return Selection(ordered, None, None, SPIKE)
    sign = _TIE_SIGN[tie]
    chosen, plateau = max(candidates, key=lambda candidate: _selection_rank(candidate, sign))
    return Selection(ordered, chosen.value, plateau, SELECTED)
```

- [ ] **Step 4: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_selection.py`, then `... file tests/backtesting/test_validate_component_selection.py`, then `python -m radon cc -s swingbot/core/backtesting/arms/selection.py | grep -E "select_cell|_selection_rank"`
Expected: all PASS, including the unedited v122 tie tests. `select_cell` A (5), `_selection_rank` A.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arms/selection.py tests/backtesting/arms/test_selection.py
git commit -m "feat(v135): select_cell tie preference; default keeps v122's larger-value rule"
```

### Task V135-10: The frozen clause-6 baseline reading for the headroom predicate

**Files:**
- Create: `swingbot/core/backtesting/arms/headroom_clauses.py`
- Modify: `swingbot/core/backtesting/arms/dryup_clauses.py` (one additive public alias, no behaviour change)
- Create: `tests/backtesting/arms/test_headroom_clauses.py`

**Interfaces:**
- Consumes: `gates.nearest_blocker`, `gates.blocker_inside`, `gates.planned_entry`, `gates.level_map_levels`, `gates.strategy_in_headroom_scope`, `gates.HEADROOM_SCOPES` (V135-2); `strategy_engine.level_map_at`, `StrategyEngine.iter_trades` (V135-5); `backtest_scenarios.bucket_bar`, `scenarios_at`, `levels_asof` (V135-8); `acceptance.arm_trade_from_plan`; `knobs.apply_knobs`; `ScanParams.from_config`; `dryup_clauses._mechanism_result`.
- Produces (`swingbot.core.backtesting.arms.headroom_clauses`):
  - `NotAHeadroomArm(ValueError)`
  - `Reading(blocker: tuple | None, n_levels: int)`: frozen dataclass. `blocker` is `gates.nearest_blocker`'s `(distance, risk)`; `n_levels` is the size of the level map the predicate was handed
  - `in_scope(trade, scope) -> bool`
  - `strategy_cell_readings(ticker, frame, strategy, horizon_key, signal_window, params) -> dict[key, Reading]`
  - `confluence_reading(trade, frame, params, level_cache) -> Reading | None`
  - `scoped_readings(trades, frame_for, scope, signal_window, cache=None, progress=None) -> dict[key, Reading | None]`; `None` means the baseline replay did not reproduce that trade
  - `no_map_share(readings, scope) -> dict`, `flagged_keys(readings, min_r) -> set`
  - `baseline_mechanism(baseline, flagged, scope) -> ClauseResult` named `"mechanism"`
  - `knob_context(blob) -> tuple[str, float] | None`, `signal_window(blob) -> tuple[str, str]`
- Produces (`dryup_clauses`): `mechanism_result = _mechanism_result`.

**How a baseline trade is read (frozen here; quoted in the V135-12 record).** A stamped arm row carries no entry or stop price, so the reading replays the baseline:
- *Strategy.* Each in-scope `(ticker, strategy, horizon)` cell is replayed through `StrategyEngine.iter_trades` with both knobs forced off. That is the baseline arm's own code, so every plan (entry, stop) is the baseline's plan exactly. The level map is built as of each trade's own signal bar with `level_map_at`, which is identical to the replay gate's map (V135-5 builds the veto's map with the same function at the same bar) and to live's map on its completed frame. The engine's 5-bar TP2 map plays no part in the veto or in this reading.
- *Confluence.* For each trade the bar's scenario and its support/resistance lists are rebuilt with `scenarios_at` after priming the bucket with `bucket_bar`, which reproduces the replay bar for bar, bucket lag included.
- Flags use `gates.blocker_inside`, the gate's own comparison. A trade the replay did not reproduce (`None`) is never flagged and is counted as `unreadable`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

```python
# tests/backtesting/arms/test_headroom_clauses.py
"""v135 frozen clause-6 reading: mechanism on the BASELINE arm, flagged vs unflagged."""
import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import dryup_clauses
from swingbot.core.backtesting.arms import headroom_clauses as hc
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
NEAR, FAR, CLEAR = hc.Reading((0.5, 2.0), 4), hc.Reading((3.0, 2.0), 4), hc.Reading(None, 4)


def _t(i, outcome, strategy="Fibonacci", source="strategy", ticker="T"):
    return ArmTrade(ticker, strategy, "4w", f"2019-02-{i + 1:02d}", outcome,
                    2.0 if outcome == "win" else -1.0, 2.0, source, "bullish")


def test_flagged_losers_pass_flagged_winners_fail():
    baseline = [_t(i, "win" if i < 4 else "loss") for i in range(10)]
    losers = {t.key for t in baseline[8:]}
    winners = {t.key for t in baseline[:2]}
    assert hc.baseline_mechanism(baseline, losers, "strategy").verdict == "PASS"
    assert hc.baseline_mechanism(baseline, winners, "strategy").verdict == "FAIL"
    assert hc.baseline_mechanism(baseline, set(), "strategy").verdict == "FAIL"   # nothing flagged
    assert hc.baseline_mechanism(baseline, losers, "strategy").name == "mechanism"


def test_out_of_scope_trades_are_in_neither_group():
    # In-scope flagged: 1 win + 1 loss (WR 50%). In-scope unflagged: all losses, so the
    # in-scope reading FAILS. If the MACD or confluence winners leaked into "retained" they
    # would lift retained WR above 50% and flip it to a wrong PASS.
    flagged_pair = [_t(0, "win"), _t(1, "loss")]
    unflagged = [_t(i, "loss") for i in range(2, 6)]
    macd = [_t(i, "win", strategy="MACD") for i in range(6, 16)]
    confluence = [_t(i, "win", strategy="confluence", source="confluence") for i in range(16, 26)]
    baseline = flagged_pair + unflagged + macd + confluence
    assert hc.baseline_mechanism(baseline, {t.key for t in flagged_pair}, "strategy").verdict == "FAIL"


@pytest.mark.parametrize("strategy,source,scope,expected", [
    ("Fibonacci", "strategy", "strategy", True),
    ("MACD", "strategy", "strategy", False),
    ("Volume Profile", "strategy", "strategy", False),
    ("Fibonacci", "strategy", "confluence", False),
    ("confluence", "confluence", "confluence", True),
    ("confluence", "confluence", "strategy", False),
])
def test_in_scope_keeps_the_two_components_apart(strategy, source, scope, expected):
    assert hc.in_scope(_t(0, "win", strategy=strategy, source=source), scope) is expected


def test_flags_use_the_gate_comparison_strictly():
    readings = {"at": hc.Reading((1.0, 2.0), 3), "in": hc.Reading((0.99, 2.0), 3),
                "clear": CLEAR, "missing": None}
    assert hc.flagged_keys(readings, 0.5) == {"in"}        # 1.0 is exactly 0.5 x 2.0: not inside
    assert hc.flagged_keys(readings, 0.75) == {"at", "in"}
    assert hc.flagged_keys(readings, 0.0) == set()


def test_no_map_share_counts_empty_maps_and_unreproduced_trades():
    readings = {"a": NEAR, "b": hc.Reading(None, 0), "c": None, "d": CLEAR}
    assert hc.no_map_share(readings, "strategy") == {
        "scope": "strategy", "n": 4, "no_map": 1, "unreadable": 1,
        "share": 0.25, "unreadable_share": 0.25}
    assert hc.no_map_share({}, "confluence")["share"] is None


def test_knob_context_and_window_read_the_stamp():
    blob = {"provenance": {"knob_delta": {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 0.75},
                           "signal_window": ["2018-06-01", "2022-12-31"]}}
    assert hc.knob_context(blob) == ("confluence", 0.75)
    assert hc.signal_window(blob) == ("2018-06-01", "2022-12-31")
    for delta in ({"MIN_REWARD_PCT": 4.0}, {"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.75},
                  {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 0.0},
                  {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": True},
                  {"HEADROOM_SCOPE": "strategy"}):
        assert hc.knob_context({"provenance": {"knob_delta": delta}}) is None


def test_scoped_readings_replay_each_cell_once_and_reuse_the_cache(monkeypatch):
    trades = [_t(0, "win"), _t(1, "loss"), _t(2, "loss", strategy="RSI"),
              _t(3, "win", strategy="MACD"), _t(4, "win", ticker="GONE")]
    calls, frames, ticks = [], [], []

    def fake_cell(ticker, frame, strategy, horizon_key, window, params):
        calls.append((ticker, strategy, horizon_key, window))
        return {t.key: NEAR for t in trades[:3] if t.strategy == strategy and t.entry_date != "2019-02-02"}

    def frame_for(ticker):
        frames.append(ticker)
        return None if ticker == "GONE" else object()
    monkeypatch.setattr(hc, "strategy_cell_readings", fake_cell)
    cache = {}
    readings = hc.scoped_readings(trades, frame_for, "strategy", WINDOW, cache=cache,
                                  progress=lambda done, total: ticks.append((done, total)))
    assert set(readings) == {t.key for t in (trades[0], trades[1], trades[2], trades[4])}
    assert readings[trades[0].key] == NEAR
    assert readings[trades[1].key] is None            # the replay did not reproduce it
    assert readings[trades[4].key] is None            # no cached frame for the ticker
    assert sorted(calls) == [("T", "Fibonacci", "4w", WINDOW), ("T", "RSI", "4w", WINDOW)]
    assert ticks == [(1, 2), (2, 2)]
    hc.scoped_readings(trades, frame_for, "strategy", WINDOW, cache=cache)
    assert len(calls) == 2                             # second pass served from the cache


def test_the_shared_mechanism_scorer_is_v122s_own():
    assert dryup_clauses.mechanism_result is dryup_clauses._mechanism_result


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


@pytest.mark.slow
def test_strategy_readings_reproduce_every_scoped_baseline_trade(frame):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    scoped = [t for t in base if hc.in_scope(t, "strategy")]
    assert scoped, "fixture must hold in-scope strategy trades or the test proves nothing"
    readings = hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW)
    assert set(readings) == {t.key for t in scoped}
    assert all(reading is not None for reading in readings.values())
    assert any(reading.n_levels > 0 for reading in readings.values())


@pytest.mark.slow
def test_confluence_readings_reproduce_every_baseline_trade(frame):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert base, "fixture must hold confluence trades or the test proves nothing"
    readings = hc.scoped_readings(base, lambda ticker: frame, "confluence", WINDOW)
    assert set(readings) == {t.key for t in base}
    assert all(reading is not None and reading.n_levels > 0 for reading in readings.values())


@pytest.mark.slow
def test_the_reading_replays_the_baseline_even_when_the_operator_has_the_gate_on(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    clean = hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW)
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 1.0)
    assert hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW) == clean
    assert config.HEADROOM_SCOPE == "strategy" and config.HEADROOM_MIN_R == 1.0   # restored
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_headroom_clauses.py`
Expected: FAIL with `ImportError: cannot import name 'headroom_clauses'`.

- [ ] **Step 3: Add the public alias to `dryup_clauses.py`**

Directly below the `_mechanism_result` function, add:

```python
#: Shared with headroom_clauses (v135): the removed-vs-retained scorer is predicate-agnostic.
mechanism_result = _mechanism_result
```

Nothing else in `dryup_clauses.py` changes.

- [ ] **Step 4: Implement `headroom_clauses.py`**

```python
"""Frozen v135 clause-6 baseline reading and the no-level-map disclosure.

A rejected entry frees the one-position slot (strategy) or the 5-bar cooldown (confluence),
so the component arm is not a subset of baseline and acceptance.py reports mechanism
SKIPPED. As for v122, the mechanism clause is scored on the BASELINE arm: in-scope trades
the predicate flags at h ("removed") against in-scope trades it does not flag ("retained").

A stamped arm row carries no entry or stop, so the reading replays the baseline with both
knobs forced off. Strategy: each in-scope cell goes through StrategyEngine.iter_trades (the
baseline's own plans), with the level map built at each trade's signal bar by level_map_at
-- the very map the replay gate and the live gate read. Confluence: each trade's scenario and lists are rebuilt with scenarios_at after
priming the level bucket, which reproduces the replay bar for bar.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.backtesting import backtest_scenarios as scenarios_mod
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms import dryup_clauses
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine, level_map_at
from swingbot.core.edge import gates
from swingbot.scan_params import ScanParams

#: The reading always replays the baseline, whatever the operator's .env says.
BASELINE_KNOBS = {"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.0}


class NotAHeadroomArm(ValueError):
    """The arm stamp does not identify an active headroom component."""


@dataclass(frozen=True)
class Reading:
    blocker: tuple | None    # gates.nearest_blocker's (distance, risk), or None
    n_levels: int            # size of the level map the predicate was handed


def in_scope(trade, scope) -> bool:
    """Keep the two registered components and the frozen strategy list separate."""
    if trade.source != scope:
        return False
    return scope == "confluence" or (scope == "strategy"
                                     and gates.strategy_in_headroom_scope(trade.strategy))


def _reading(entry, stop, direction, level_map) -> Reading:
    levels = gates.level_map_levels(level_map)
    return Reading(gates.nearest_blocker(entry, stop, direction, levels), len(levels))


def _bar_index(frame, date) -> int:
    """Position of the signal bar: the last bar at or before `date`."""
    return len(frame.loc[:date]) - 1


def strategy_cell_readings(ticker, frame, strategy, horizon_key, signal_window, params) -> dict:
    """Reading per baseline trade of one (ticker, strategy, horizon) cell. The cell is
    replayed through the baseline engine, so each plan is the baseline's own plan."""
    out = {}
    engine = StrategyEngine(strategies=(strategy,))
    for date, plan, result in engine.iter_trades(ticker, frame, strategy, horizon_key,
                                                 signal_window, params):
        trade = arm_trade_from_plan(plan, entry_date=date, outcome=result.outcome,
                                    r_multiple=result.r_total)
        level_map = level_map_at(frame, _bar_index(frame, date), horizon_key)
        out[trade.key] = _reading(gates.planned_entry(plan), plan.stop_loss, plan.direction,
                                  level_map)
    return out


def confluence_reading(trade, frame, params, level_cache) -> Reading | None:
    """The reading for one baseline confluence trade, from the scenario and the lists the
    replay had at its signal bar. None when that bar holds no scenario in its direction."""
    index, horizon_key = _bar_index(frame, trade.entry_date), trade.horizon_key
    scenarios_mod.levels_asof(trade.ticker, frame, scenarios_mod.bucket_bar(index, horizon_key),
                              horizon_key, level_cache)
    _window, _price, supports, resistances, scenarios = scenarios_mod.scenarios_at(
        trade.ticker, frame, index, horizon_key, params, level_cache)
    scenario = next((item for item in scenarios if item.direction == trade.direction), None)
    if scenario is None:
        return None
    return _reading(scenario.entry, scenario.stop_loss, trade.direction, (supports, resistances))


def _strategy_readings(trades, frame, signal_window, params, cache) -> dict:
    out = {}
    for ticker, strategy, horizon_key in sorted({(t.ticker, t.strategy, t.horizon_key)
                                                 for t in trades}):
        key = ("strategy", ticker, strategy, horizon_key, tuple(signal_window))
        if key not in cache:
            cache[key] = strategy_cell_readings(ticker, frame, strategy, horizon_key,
                                                signal_window, params)
        out.update(cache[key])
    return out


def _confluence_readings(trades, frame, params, cache) -> dict:
    out, level_cache = {}, {}
    for trade in trades:
        key = ("confluence", trade.key)
        if key not in cache:
            cache[key] = confluence_reading(trade, frame, params, level_cache)
        out[trade.key] = cache[key]
    return out


def _ticker_readings(trades, frame, scope, signal_window, params, cache) -> dict:
    if frame is None:
        return {}
    if scope == "strategy":
        return _strategy_readings(trades, frame, signal_window, params, cache)
    return _confluence_readings(trades, frame, params, cache)


def scoped_readings(trades, frame_for, scope, signal_window, cache=None, progress=None) -> dict:
    """Reading per in-scope baseline trade key. None means the baseline replay did not
    reproduce the trade (or its ticker has no frame). `cache` may be shared across arm files
    of one process: a reading depends on the frame and the trade, never on h.
    `progress(done, total)` is called once per ticker."""
    cache = {} if cache is None else cache
    by_ticker = defaultdict(list)
    for trade in trades:
        if in_scope(trade, scope):
            by_ticker[trade.ticker].append(trade)
    found = {}
    with apply_knobs(BASELINE_KNOBS):
        params = ScanParams.from_config()
        for done, ticker in enumerate(sorted(by_ticker), 1):
            found.update(_ticker_readings(by_ticker[ticker], frame_for(ticker), scope,
                                          signal_window, params, cache))
            if progress is not None:
                progress(done, len(by_ticker))
    return {trade.key: found.get(trade.key)
            for ticker in sorted(by_ticker) for trade in by_ticker[ticker]}


def no_map_share(readings, scope) -> dict:
    """Disclose how many scoped baseline plans were judged with no level map at all, and how
    many the replay did not reproduce. Neither can be flagged."""
    n = len(readings)
    unreadable = sum(reading is None for reading in readings.values())
    no_map = sum(reading is not None and reading.n_levels == 0 for reading in readings.values())
    return {"scope": scope, "n": n, "no_map": no_map, "unreadable": unreadable,
            "share": no_map / n if n else None,
            "unreadable_share": unreadable / n if n else None}


def flagged_keys(readings, min_r) -> set:
    """The gate's own strict comparison, including its None and off rules."""
    return {key for key, reading in readings.items()
            if reading is not None and gates.blocker_inside(reading.blocker, min_r)}


def baseline_mechanism(baseline, flagged, scope):
    """Compare flagged vs unflagged in-scope baseline outcomes only."""
    scoped = [trade for trade in baseline if in_scope(trade, scope)]
    removed = [trade for trade in scoped if trade.key in flagged]
    retained = [trade for trade in scoped if trade.key not in flagged]
    return dryup_clauses.mechanism_result(removed, retained, scope)


def knob_context(blob):
    """Return an active component only when both headroom knobs are stamped."""
    delta = (blob.get("provenance") or {}).get("knob_delta") or {}
    scope, min_r = delta.get("HEADROOM_SCOPE"), delta.get("HEADROOM_MIN_R")
    if scope not in gates.HEADROOM_SCOPES or isinstance(min_r, bool):
        return None
    if not isinstance(min_r, (int, float)) or not math.isfinite(min_r) or min_r <= 0:
        return None
    return scope, float(min_r)


def signal_window(blob) -> tuple:
    """The stamped signal window, which the strategy replay must reuse to reproduce the arm."""
    start, end = blob["provenance"]["signal_window"]
    return start, end
```

- [ ] **Step 5: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/arms/test_headroom_clauses.py`, then `... file tests/backtesting/arms/test_dryup_clauses.py`, then `python -m radon cc -s -n C swingbot/core/backtesting/arms/headroom_clauses.py swingbot/core/backtesting/arms/dryup_clauses.py`
Expected: all PASS; radon prints nothing. If `test_strategy_readings_reproduce_every_scoped_baseline_trade` or the confluence twin reports a `None` reading, the rebuild does not reproduce the baseline: stop and report which trade key is missing. Do not relax the assertion, and do not paper over it by counting the trade as retained.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/arms/headroom_clauses.py swingbot/core/backtesting/arms/dryup_clauses.py tests/backtesting/arms/test_headroom_clauses.py
git commit -m "feat(v135): frozen clause-6 baseline reading and no-map share for the headroom veto"
```

### Task V135-11: `--headroom-mechanism` in `validate_component.py`

**Files:**
- Modify: `scripts/backtest/validate_component.py`
- Create: `tests/backtesting/test_validate_component_headroom.py`

**Interfaces:**
- Consumes: `headroom_clauses` (V135-10), `select_cell(..., tie=)` (V135-9), the searchable knobs (V135-7; the test stamps arms with them).
- Produces: `validate_component.py --headroom-mechanism` for `--stage selection` and `--stage validation`. With it, clause 6 is the V135-10 baseline reading, the selection axis is `HEADROOM_MIN_R` printed as `h=`, and a tie goes to the smaller `h`. Without it, every output is unchanged. New module names: `_HEADROOM_CACHE`, `_headroom_progress`, `_baseline_headroom(baseline, scope, window)`, `_headroom_mechanism_for(path, baseline)`, `_refuse_not_headroom()`, `_selection_axis(args)`.
- Witness for v122: `tests/backtesting/test_validate_component_dryup.py` and `tests/backtesting/test_validate_component_selection.py` must pass unedited.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backtesting/test_validate_component_headroom.py
"""--headroom-mechanism: the v135 baseline reading replaces acceptance.py's mechanism
clause, selects on HEADROOM_MIN_R, and breaks a tie toward the smaller h."""
import json

import pytest

from swingbot.core.backtesting.arms.headroom_clauses import Reading
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.test_validate_component_stamps import UNIVERSE, rows, vc

NEAR, CLEAR = Reading((0.5, 2.0), 3), Reading(None, 3)   # 0.25R away: inside every grid value


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, '_full_universe', lambda: UNIVERSE)


@pytest.fixture
def losers_blocked(monkeypatch):
    seen = []

    def readings(baseline, scope, window):
        seen.append((scope, window))
        return {t.key: NEAR if t.outcome == 'loss' else CLEAR for t in baseline}
    monkeypatch.setattr(vc, '_baseline_headroom', readings)
    return seen


def stamped(tmp_path, stage, min_r=.75, headroom=True, replacement=True):
    baseline, component = rows()
    baseline = [dict(row, strategy='RSI') for row in baseline]
    component = [dict(row, strategy='RSI') for row in component]
    if replacement:
        component.append(dict(component[0], entry_date='2024-02-01'))
    knobs = {'HEADROOM_SCOPE': 'strategy', 'HEADROOM_MIN_R': min_r} if headroom else {'MIN_REWARD_PCT': 4}
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window,
                        universe=UNIVERSE, horizons=ALL_HORIZONS, engines=('strategy',),
                        knob_delta=knobs, engine_hash_baseline='h', engine_hash_component='h',
                        changed_outcomes=1)
    path = tmp_path / f'arms-{min_r}.json'
    path.write_text(json.dumps({'provenance': stamp, 'baseline': baseline, 'component': component}))
    return path


def args(path, stage='validation'):
    common = ['--stage', stage, '--title', 't', '--window', 'w', '--resamples', '50']
    return common + (['--grid-arms', f'.75={path}'] if stage == 'selection' else ['--arms', str(path)])


def _mechanism(path):
    return next(c for c in json.loads(path.read_text())['clauses'] if c['name'] == 'mechanism')['verdict']


def test_non_subset_validation_replaces_only_mechanism(tmp_path, losers_blocked, capsys):
    path, output = stamped(tmp_path, 'validation'), tmp_path / 'out.json'
    command = args(path) + ['--out-json', str(output)]
    vc.main(command)
    original = json.loads(output.read_text())
    assert _mechanism(output) == 'SKIPPED'
    vc.main(command + ['--headroom-mechanism'])
    changed = json.loads(output.read_text())
    assert _mechanism(output) == 'PASS'
    assert changed['clauses'][:5] == original['clauses'][:5]
    assert changed['split'] == original['split']
    printed = capsys.readouterr().out
    assert '"scope": "strategy"' in printed and '"no_map": 0' in printed
    assert losers_blocked == [('strategy', tuple(STAGES['validation'].signal_window))]


@pytest.mark.parametrize('stage', ['validation', 'selection'])
def test_refuses_an_arm_without_headroom_knobs(tmp_path, capsys, stage):
    path = stamped(tmp_path, stage, headroom=False)
    assert vc.main(args(path, stage) + ['--headroom-mechanism']) == 1
    assert 'refused:not-a-headroom-arm' in capsys.readouterr().err


def test_selection_ties_go_to_the_smaller_h(tmp_path, losers_blocked, capsys):
    command = ['--stage', 'selection', '--title', 'HEADROOM_MIN_R', '--window', 'train',
               '--resamples', '200', '--headroom-mechanism']
    for value in (.5, .75, 1.0):
        command += ['--grid-arms', f'{value}={stamped(tmp_path, "selection", value, replacement=False)}']
    output = tmp_path / 'stage1.json'
    assert vc.main(command + ['--out-json', str(output)]) == 0
    printed = capsys.readouterr().out
    assert all(f'h={value}' in printed for value in (.5, .75, 1.0))
    assert 'selected=0.5' in printed
    assert json.loads(output.read_text())['selected'] == .5


def test_the_two_mechanism_readings_are_mutually_exclusive(tmp_path):
    path = stamped(tmp_path, 'validation')
    with pytest.raises(SystemExit):
        vc.main(args(path) + ['--headroom-mechanism', '--dryup-mechanism'])


def test_selection_axis_defaults_to_v122s():
    import argparse
    assert vc._selection_axis(argparse.Namespace()) == ('PULLBACK_DRYUP_MAX_RATIO', 'd', 'larger')
    assert vc._selection_axis(argparse.Namespace(headroom_mechanism=True)) == ('HEADROOM_MIN_R', 'h', 'smaller')
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_headroom.py`
Expected: FAIL with `AttributeError: ... has no attribute '_baseline_headroom'` and an unrecognised `--headroom-mechanism` argument.

- [ ] **Step 3: Implement**

Change the import line `from swingbot.core.backtesting.arms import dryup_clauses, reachability  # noqa: E402` to:

```python
from swingbot.core.backtesting.arms import dryup_clauses, headroom_clauses, reachability  # noqa: E402
```

Add directly below `_refuse_not_dryup`:

```python
# One invocation's grid cells share readings: a reading depends on the frame and the trade
# key only, never on h. The cache lives and dies with the process.
_HEADROOM_CACHE: dict = {}


def _headroom_progress(done, total):
    print(f"headroom readings: {done}/{total} tickers ({done / total * 100:.0f}%)", flush=True)


def _baseline_headroom(baseline, scope, window):
    return headroom_clauses.scoped_readings(baseline, _frame_for, scope, window,
                                            cache=_HEADROOM_CACHE, progress=_headroom_progress)


def _headroom_mechanism_for(path, baseline):
    """The frozen v135 clause-6 reading for one stamped arm file, plus its no-map share."""
    blob = json.loads(Path(path).read_text())
    context = headroom_clauses.knob_context(blob)
    if context is None:
        raise headroom_clauses.NotAHeadroomArm(str(path))
    scope, min_r = context
    readings = _baseline_headroom(baseline, scope, headroom_clauses.signal_window(blob))
    print(json.dumps(headroom_clauses.no_map_share(readings, scope)))
    return headroom_clauses.baseline_mechanism(
        baseline, headroom_clauses.flagged_keys(readings, min_r), scope)


def _refuse_not_headroom():
    print('refused:not-a-headroom-arm -- active headroom knobs required. Budget intact.', file=sys.stderr)
    return 1


def _selection_axis(args):
    """(config attr, printed label, tie rule) of the grid the active mechanism selects on."""
    if getattr(args, 'headroom_mechanism', False):
        return 'HEADROOM_MIN_R', 'h', 'smaller'
    return 'PULLBACK_DRYUP_MAX_RATIO', 'd', 'larger'
```

Replace `_cell_mechanism` with:

```python
def _cell_mechanism(args, path, baseline, component, value):
    """Opt-in frozen baseline reading; replacements stay in clauses 1–5."""
    if getattr(args, 'dryup_mechanism', False):
        return _dryup_mechanism_for(path, baseline)
    if getattr(args, 'headroom_mechanism', False):
        return _headroom_mechanism_for(path, baseline)
    return None
```

In `_run_gate`, add a second `except` directly after the existing `except dryup_clauses.NotADryupArm:` pair:

```python
    except headroom_clauses.NotAHeadroomArm:
        return _refuse_not_headroom()
```

In `stage_selection`, add the same second `except` after the existing `except dryup_clauses.NotADryupArm:` pair, and replace the `result = select_cell(...)` line and the `for cell in result.cells:` print with:

```python
    name, label, tie = _selection_axis(args)
    result = select_cell(cells, name, tie=tie)
    for cell in result.cells:
        print(f"{label}={cell.value} eligible={cell.eligible} dWR={cell.delta_win_rate_pp} ExpR={cell.expectancy_r} failed={cell.failed} disclosure={cell.disclosure}")
```

In `main`, add after `parser.add_argument('--dryup-mechanism', action='store_true')`:

```python
    parser.add_argument('--headroom-mechanism', action='store_true')
```

and directly after `args = parser.parse_args(argv)`:

```python
    if args.dryup_mechanism and args.headroom_mechanism:
        parser.error("--dryup-mechanism and --headroom-mechanism are different clause-6 readings; pass one")
```

- [ ] **Step 4: Run the narrow tests and radon**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_headroom.py`, then `... file tests/backtesting/test_validate_component_dryup.py`, `... file tests/backtesting/test_validate_component_selection.py`, `... file tests/backtesting/test_validate_component_stamps.py`, then `python -m radon cc -s -n C scripts/backtest/validate_component.py`
Expected: all PASS, with the three v122 files unedited; radon prints nothing (`stage_selection` B (9), `_run_gate` B (7), `main` B (6)).

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_headroom.py
git commit -m "feat(v135): --headroom-mechanism clause-6 reading, h axis and smaller-h tie in the judge"
```

# Phase 4 — Pre-registration, measurement, close-out

Every command in this phase runs in the worktree. Each bash block starts by setting the cache path, because shell state does not persist between calls. If the pre-registration record is committed on a date later than 2026-10-06, use that date in its filename and in every `PREREG=` line and results filename below.

### Task V135-12: Pre-registration record, committed before any outcome is read

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v135-preregistration.md`

**Interfaces:**
- Consumes: every code task committed on the branch (V135-1..V135-11) and a clean `git status --short -- swingbot/ scripts/backtest/`.
- Produces: the frozen rule V135-13 and V135-14 execute and quote. It is committed before any arm file exists.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** if `python scripts/backtest/measure_arms.py --help` lists `--instrument` (v158 merged), the record's `## Instrument` section adds one line: "Arms are produced with `--instrument v1` (fills and costs of the v1 instrument); every measurement command in V135-13/14 carries it." Otherwise it states "instrument: v1 (the only one; `--instrument` not present at pre-registration)". (b) From this commit until the last stage of V135-14 has run, **do not merge `main` into the worktree**: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, and a merge between stages makes the judge refuse the arms.

- [ ] **Step 1: Invoke `backtest-gate`, confirm the tree is clean, then write the record**

Run `git status --short -- swingbot/ scripts/backtest/` (must print nothing) and `ls logs/v135 2>/dev/null` (must print nothing: no arm exists yet). Then write:

```markdown
# v135 pre-registration — headroom veto

**Committed before any v135 outcome is read and before any arm file exists.** Spec: `docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md`. Plan: `docs/superpowers/plans/2026-10-06-v135-headroom-veto_0-index.md` (parts `_1`, `_2`).

## Claim
Removing plans that have a multi-source opposing level nearer than `h` x their own risk raises win rate without costing expectancy, under the standard v72 funnel. A binary filter, not a score weight.

## Instrument
`gates.headroom_rejects(entry, stop, direction, levels, min_r)`. A blocker is a `levels.Level` strictly beyond entry on the target side, with `abs(level.price - entry) < h x abs(entry - stop)` (strict), confirmed by at least `HEADROOM_MIN_FAMILIES = 2` distinct `levels.strategy_family` families. No levels, zero risk or `h = 0` never reject. `HEADROOM_MIN_FAMILIES` is a frozen constant, not a grid axis. Planned prices only, never a fill: `Scenario.entry` / `Scenario.stop_loss` for confluence; the built plan's entry (filled price if set, else trigger) and `stop_loss` for strategy. Call sites: `analyze._apply_headroom` / `backtest_scenarios._headroom_kept` (confluence, on the lists the scenario was built from) and `strategy_pass._headroom_blocked` / `StrategyEngine._gated_plan` (strategy, after the plan is built). Parity is pinned by `tests/backtesting/test_headroom_parity.py`. The strategy veto reads a level map built at the signal bar itself in both paths (live: on the pass's completed frame; replay: on the frame truncated at the signal bar), never the engine's 5-bar TP2 map, so live, replay and the clause-6 reading judge a plan against the same map.

## Components (separate budgets, never pooled)
| Component | Knob delta | Population |
|---|---|---|
| confluence | `HEADROOM_SCOPE=confluence`, `HEADROOM_MIN_R=h` | every confluence-scan scenario, both directions |
| strategy | `HEADROOM_SCOPE=strategy`, `HEADROOM_MIN_R=h` | EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence |

MACD, Volume Profile and every `strategy_types.SHORT_STRATEGIES` name are never gated. Arms come from `scripts/backtest/measure_arms.py` with both default engines, so each component is judged against the whole replayed book it would ship into. Order: confluence fully through its funnel first, then strategy. One shot at a time.

## Frozen grid and selection rule (verbatim from the spec)
`h ∈ {0.5, 0.75, 1.0}` per component. No bucket table from v125 (`room_atr`) or v133 may move it.
1. **Stage −1 reachability** (pilot, `h = 1.0`, the widest cut): refuse on zero changed outcomes.
2. **Stage 0 MDE** (fold-train `selection` arms, paired bootstrap; arms share keys): run per cell with `--train-effect-pp` set to that cell's fold-train standardised ΔWR. A refused cell is ineligible at Stage 1. If all three are refused, the shot is refused with the budget intact.
3. **Stage 1 selection** (fold-train only): eligible cells pass clauses 2–4 and 6 (SKIPPED is not a pass); `plateau_report()` is mandatory and the chosen `h` needs an eligible grid neighbour. Among eligible plateau cells pick the largest ΔWR; tie → smaller `h` (smaller cut). Judge: `validate_component.py --stage selection --headroom-mechanism`.
4. **Stage 2 walk-forward**: `gate_win_rate`: ≥ 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30.
5. **Stage 3 VALIDATION** 2024-01-01..2025-12-31: one shot per component, all six clauses, missing permutation p = FAIL. Judge: `validate_component.py --stage validation --headroom-mechanism --permutation-p <p>`.

## Clause 6 reading (frozen, same as v122)
A rejected entry frees the one-position slot (strategy) or the 5-bar cooldown (confluence), so the component arm is not a strict subset of baseline. The mechanism clause is scored on the **baseline** arm: in-scope trades the predicate flags at `h` ("removed") vs in-scope trades it does not flag ("retained"); pass iff removed WR < retained WR **and** removed ExpR ≤ 0. Out-of-scope trades are in neither group. Replacement trades count fully in clauses 1–5 and their count is disclosed.

**How a baseline trade is read** (`swingbot/core/backtesting/arms/headroom_clauses.py`). An arm row carries no entry or stop, so the reading replays the baseline with both knobs forced off. Strategy: each in-scope `(ticker, strategy, horizon)` cell is replayed through `StrategyEngine.iter_trades`, giving the baseline's own plans; the level map is built at each trade's own signal bar, identical to the map the replay gate and the live gate read. Confluence: each trade's scenario and support/resistance lists are rebuilt with `backtest_scenarios.scenarios_at` after priming the level bucket, reproducing the replay bar for bar. Flags use `gates.blocker_inside`, the gate's own comparison. A trade the replay does not reproduce is never flagged and is disclosed as `unreadable`.

## Clause 5 instrument
`python scripts/backtest/permutation_test.py --arms <the stamped VALIDATION arm file> --n 200 --seed 42`, the arm-pair mode v122 added. No change to the script or its null. Its `p_value` is passed as `--permutation-p`; a null p is a FAIL.

## Disclosure (every stage reached)
Removed / added (replacements) / changed counts; per-direction ΔWR and ΔExpR; the top-2 horizon share of the removed trades; a statement when more than 80% of the removed trades are one direction; the `no_map` and `unreadable` shares of the scoped baseline population (the judge's JSON line); and the baseline-reading flagged WR, retained WR and flagged ExpR.

## Stop rules
A refusal or failure at any stage closes that component in `docs/claude/backtest-methodology.md`'s closed-pre-registrations table with its numbers; later stages are not run and an unspent VALIDATION budget stays unspent. The code stays merged and inert (defaults off). A component flips default-on only after its own VALIDATION passes all six clauses. Reopening needs a mechanism other than "an opposing level with ≥ 2 source families nearer than `h ∈ {0.5, 0.75, 1.0}` × risk".
```

- [ ] **Step 2: Commit the record alone**

```bash
git add docs/superpowers/results/2026-10-06-v135-preregistration.md
git commit -m "docs(v135): pre-registration -- headroom veto, two components, frozen grid, clause-5/6 instruments"
git log --oneline -1
```

Record the commit hash; both results docs quote it.

### Task V135-13: Confluence component funnel (Stage −1 → 0 → 1 → 2 → 3)

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v135-confluence.md` (appended at every stage reached), `docs/superpowers/results/2026-10-06-v135-confluence-stage1.json` (Stage 1 only)
- Create on Stage 2/3 only: `docs/superpowers/results/2026-10-06-v135-confluence-walkforward.json`, `docs/superpowers/results/2026-10-06-v135-confluence-validation.md` / `.json`
- Arms and logs (not committed): `logs/v135/confluence-*.json`, `logs/v135/confluence-*.log`

**Interfaces:**
- Consumes: the V135-12 record. Only verified flags are used:
  - `measure_arms.py --stage {pilot,selection,walkforward,validation} --knob A=v --out P [--preregistration P] [--workers N]`
  - `validate_component.py --stage {reachability,mde,selection,walkforward,validation} [--arms P] --title T --window W [--train-effect-pp X] [--grid-arms V=P] [--mde-refused V] [--headroom-mechanism] [--permutation-p P] [--out-md P] [--out-json P]`
  - `permutation_test.py --arms P --n 200 --seed 42`
- Produces: a verdict for the confluence component: `ship candidate h=<x>`, or closed at a named stage with its numbers.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `python scripts/backtest/measure_arms.py --help` and `python scripts/backtest/validate_component.py --help`; if either lists `--instrument` (v158 merged), append `--instrument v1` to every command of that script in this task, and the results doc names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V135-12 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judge refuse the arms.

**Rules for every step.** Invoke `backtest-gate` before each command. Confirm `git status --short -- swingbot/ scripts/backtest/` is empty before each producer run and make no edit there while it runs. Dispatch every `measure_arms.py` run to the `backtest-runner` subagent, **one invocation per dispatch, never two at once**, naming the worktree; its progress is the percent line in `logs/measure_arms.*.progress`. The Stage 1 judge prints its own `headroom readings: N/M tickers (P%)` line; if it is expected to run long, dispatch it to `backtest-runner` too. **Stop on the first refusing or failing stage**: append the numbers to the results doc, write its observations (Step 6), commit (Step 7) and go to V135-14. Never re-run a stage to get a different answer.

- [ ] **Step 1: Stage −1 reachability (pilot, `h = 1.0`)**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage pilot --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=1.0 --preregistration $PREREG --out logs/v135/confluence-pilot-1.0.json
python scripts/backtest/validate_component.py --stage reachability --arms logs/v135/confluence-pilot-1.0.json --title "v135 confluence h=1.0 pilot" --window "2018-06-01..2020-12-31"
```

Pass: `REACHABLE`. Copy the `knobs:` and `split` lines (baseline N, component N, removed / added / changed) into the results doc. **Stop rule:** `refused:zero-diff` closes the component as unreachable, budget intact.

- [ ] **Step 2: Fold-train arms for the three cells, then Stage 0 MDE per cell**

One dispatch per cell, serially:

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=0.5 --preregistration $PREREG --out logs/v135/confluence-selection-0.5.json
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=0.75 --preregistration $PREREG --out logs/v135/confluence-selection-0.75.json
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=1.0 --preregistration $PREREG --out logs/v135/confluence-selection-1.0.json
```

Then print each cell's fold-train standardised ΔWR and run the MDE gate with it:

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
for h in 0.5 0.75 1.0; do python -c "import sys; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.acceptance import delta_standardised_win_rate as dwr, delta_expectancy_r as dexp; b, c = vc.load_arms('logs/v135/confluence-selection-$h.json'); print('$h', 'N', len(b), len(c), 'dWR', dwr(b, c), 'dExpR', dexp(b, c))"; done
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/confluence-selection-0.5.json --train-effect-pp <dWR printed for 0.5> --title "v135 confluence h=0.5 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/confluence-mde-0.5.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/confluence-selection-0.75.json --train-effect-pp <dWR printed for 0.75> --title "v135 confluence h=0.75 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/confluence-mde-0.75.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/confluence-selection-1.0.json --train-effect-pp <dWR printed for 1.0> --title "v135 confluence h=1.0 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/confluence-mde-1.0.log
```

A zero or negative ΔWR is passed as printed; it is refused, which is correct. Record per cell: baseline / component rows, ΔWR, ΔExpR, paired and unpaired MDE, `RESOLVABLE` or `REFUSED`.

Record the disclosure for every cell, whatever the verdict (it is disclosure, it changes no verdict):

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
for h in 0.5 0.75 1.0; do python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; p = 'logs/v135/confluence-selection-$h.json'; b, c = vc.load_arms(p); print('$h', json.dumps(removed_disclosure(b, c))); print('$h', vc._headroom_mechanism_for(p, b))"; done | tee logs/v135/confluence-disclosure.log
```

**Stop rule:** if all three cells are `REFUSED`, the component closes at Stage 0, VALIDATION budget intact.

- [ ] **Step 3: Stage 1 selection (fold-train only, clause 6 per the frozen reading)**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
python scripts/backtest/validate_component.py --stage selection --headroom-mechanism --grid-arms 0.5=logs/v135/confluence-selection-0.5.json --grid-arms 0.75=logs/v135/confluence-selection-0.75.json --grid-arms 1.0=logs/v135/confluence-selection-1.0.json --title HEADROOM_MIN_R --window "2018-06-01..2022-12-31" --out-json docs/superpowers/results/2026-10-06-v135-confluence-stage1.json | tee logs/v135/confluence-stage1.log
```

Add one `--mde-refused <h>` per cell Stage 0 refused. Copy into the results doc every `h=` line (eligibility, failed clauses, ΔWR, ExpR, disclosure including `added`) and the `no_map` JSON line. Pass: `verdict=selected`; that `h` goes to Stage 2. **Stop rule:** `no-eligible-cell` or `spike` closes the component at Stage 1, budget intact.

- [ ] **Step 4: Stage 2 walk-forward (free)**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage walkforward --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=<selected h> --preregistration $PREREG --out logs/v135/confluence-walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --arms logs/v135/confluence-walkforward.json --title "v135 confluence h=<selected h> walk-forward" --window "2021..2023 folds" --out-json docs/superpowers/results/2026-10-06-v135-confluence-walkforward.json
```

Pass: `PASS`. Record the three fold rows. **Stop rule:** anything else closes the component at Stage 2, VALIDATION budget unspent.

- [ ] **Step 5: Stage 3 VALIDATION, the one shot**

Before running: re-read the record, confirm `git status --short -- swingbot/ scripts/backtest/` is empty, and confirm Stages −1 to 2 all passed for this component. This command spends the budget; it is never run twice.

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage validation --knob HEADROOM_SCOPE=confluence --knob HEADROOM_MIN_R=<selected h> --preregistration $PREREG --out logs/v135/confluence-validation.json
python scripts/backtest/permutation_test.py --arms logs/v135/confluence-validation.json --n 200 --seed 42 | tee logs/v135/confluence-permutation.log
python scripts/backtest/validate_component.py --stage validation --headroom-mechanism --arms logs/v135/confluence-validation.json --permutation-p <p_value printed above> --title "v135 confluence h=<selected h> VALIDATION" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-06-v135-confluence-validation.md --out-json docs/superpowers/results/2026-10-06-v135-confluence-validation.json
python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c = vc.load_arms('logs/v135/confluence-validation.json'); print(json.dumps(removed_disclosure(b, c), indent=1))"
```

If `permutation_test.py` prints a null `p_value`, omit `--permutation-p`: the missing p is a FAIL, as pre-registered. Record the result as it stands. `PASS` makes the component a ship candidate for V135-15. **Stop rule:** `FAIL` closes the component, budget spent and final.

- [ ] **Step 6: Write the results doc**

`docs/superpowers/results/2026-10-06-v135-confluence.md`, modelled on `docs/superpowers/results/2026-10-05-v122-confluence.md`: the record's path and commit hash; one section per stage reached with its source arm file, window, universe size and a table of the measured numbers; the pre-registered rule for that stage quoted verbatim; the disclosure block (removed / added / changed, per-direction ΔWR and ΔExpR, top-2 horizon share, the one-direction statement, `no_map` and `unreadable` shares, flagged vs retained WR and flagged ExpR per cell); the stage the component stopped at and why; and an honest observations section. Failures are recorded, not fixed. Do not quote a number from memory: every figure comes from a log under `logs/v135/` or a JSON written by the judge (`pooled-numbers`).

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/results/2026-10-06-v135-confluence*
git commit -m "docs(v135): confluence component funnel result"
```

### Task V135-14: Strategy component funnel (Stage −1 → 0 → 1 → 2 → 3)

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v135-strategy.md`, `docs/superpowers/results/2026-10-06-v135-strategy-stage1.json` (Stage 1 only)
- Create on Stage 2/3 only: `docs/superpowers/results/2026-10-06-v135-strategy-walkforward.json`, `docs/superpowers/results/2026-10-06-v135-strategy-validation.md` / `.json`
- Arms and logs (not committed): `logs/v135/strategy-*.json`, `logs/v135/strategy-*.log`

**Interfaces:**
- Consumes: the V135-12 record. This task starts only after V135-13's commit, never while a confluence shot runs. The confluence result changes no rule here: the budgets are separate and never pooled.
- Produces: a verdict for the strategy component.

**Cross-plan (audit 2026-10-10):** (a) **Instrument pin:** before the first command, run `python scripts/backtest/measure_arms.py --help` and `python scripts/backtest/validate_component.py --help`; if either lists `--instrument` (v158 merged), append `--instrument v1` to every command of that script in this task, and the results doc names the instrument `v1`. (b) **No merge of `main` into the worktree** between the V135-12 pre-registration commit and the last stage run: `measure_arms.py` stamps `code_hash()` over `swingbot/*.py`, so a merge mid-funnel makes the judge refuse the arms.

**Rules for every step:** the same as V135-13. `backtest-gate` before each command, a clean `swingbot/` and `scripts/backtest/` before each producer run, one `measure_arms.py` invocation per `backtest-runner` dispatch, stop on the first refusing or failing stage. The strategy clause-6 reading replays every in-scope cell, so the Stage 0 disclosure and the Stage 1 judge are the slow commands here: dispatch them to `backtest-runner` and read the `headroom readings: N/M tickers (P%)` line for progress.

- [ ] **Step 1: Stage −1 reachability (pilot, `h = 1.0`)**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage pilot --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=1.0 --preregistration $PREREG --out logs/v135/strategy-pilot-1.0.json
python scripts/backtest/validate_component.py --stage reachability --arms logs/v135/strategy-pilot-1.0.json --title "v135 strategy h=1.0 pilot" --window "2018-06-01..2020-12-31"
```

Pass: `REACHABLE`. Disclose the `split` line. **Stop rule:** `refused:zero-diff` closes the component, budget intact.

- [ ] **Step 2: Fold-train arms for the three cells, then Stage 0 MDE per cell**

One dispatch per cell, serially:

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=0.5 --preregistration $PREREG --out logs/v135/strategy-selection-0.5.json
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=0.75 --preregistration $PREREG --out logs/v135/strategy-selection-0.75.json
python scripts/backtest/measure_arms.py --stage selection --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=1.0 --preregistration $PREREG --out logs/v135/strategy-selection-1.0.json
```

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
for h in 0.5 0.75 1.0; do python -c "import sys; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.acceptance import delta_standardised_win_rate as dwr, delta_expectancy_r as dexp; b, c = vc.load_arms('logs/v135/strategy-selection-$h.json'); print('$h', 'N', len(b), len(c), 'dWR', dwr(b, c), 'dExpR', dexp(b, c))"; done
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/strategy-selection-0.5.json --train-effect-pp <dWR printed for 0.5> --title "v135 strategy h=0.5 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/strategy-mde-0.5.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/strategy-selection-0.75.json --train-effect-pp <dWR printed for 0.75> --title "v135 strategy h=0.75 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/strategy-mde-0.75.log
python scripts/backtest/validate_component.py --stage mde --arms logs/v135/strategy-selection-1.0.json --train-effect-pp <dWR printed for 1.0> --title "v135 strategy h=1.0 MDE" --window "2018-06-01..2022-12-31" | tee logs/v135/strategy-mde-1.0.log
```

Disclosure for every cell, whatever the verdict (one process, so the three cells share one replay of the baseline):

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
python -c "
import sys, json
sys.path.insert(0, 'scripts/backtest')
import validate_component as vc
from swingbot.core.backtesting.arms.selection import removed_disclosure
for h in ('0.5', '0.75', '1.0'):
    path = f'logs/v135/strategy-selection-{h}.json'
    baseline, component = vc.load_arms(path)
    print(h, json.dumps(removed_disclosure(baseline, component)), flush=True)
    print(h, vc._headroom_mechanism_for(path, baseline), flush=True)
" | tee logs/v135/strategy-disclosure.log
```

**Stop rule:** if all three cells are `REFUSED`, the component closes at Stage 0, VALIDATION budget intact.

- [ ] **Step 3: Stage 1 selection**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
python scripts/backtest/validate_component.py --stage selection --headroom-mechanism --grid-arms 0.5=logs/v135/strategy-selection-0.5.json --grid-arms 0.75=logs/v135/strategy-selection-0.75.json --grid-arms 1.0=logs/v135/strategy-selection-1.0.json --title HEADROOM_MIN_R --window "2018-06-01..2022-12-31" --out-json docs/superpowers/results/2026-10-06-v135-strategy-stage1.json | tee logs/v135/strategy-stage1.log
```

Add one `--mde-refused <h>` per cell Stage 0 refused. Pass: `verdict=selected`. **Stop rule:** `no-eligible-cell` or `spike` closes the component at Stage 1, budget intact.

- [ ] **Step 4: Stage 2 walk-forward**

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage walkforward --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=<selected h> --preregistration $PREREG --out logs/v135/strategy-walkforward.json
python scripts/backtest/validate_component.py --stage walkforward --arms logs/v135/strategy-walkforward.json --title "v135 strategy h=<selected h> walk-forward" --window "2021..2023 folds" --out-json docs/superpowers/results/2026-10-06-v135-strategy-walkforward.json
```

Pass: `PASS`. **Stop rule:** anything else closes the component at Stage 2, VALIDATION budget unspent.

- [ ] **Step 5: Stage 3 VALIDATION, the one shot**

Make the same pre-checks as V135-13 Step 5, then:

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PREREG=docs/superpowers/results/2026-10-06-v135-preregistration.md
python scripts/backtest/measure_arms.py --stage validation --knob HEADROOM_SCOPE=strategy --knob HEADROOM_MIN_R=<selected h> --preregistration $PREREG --out logs/v135/strategy-validation.json
python scripts/backtest/permutation_test.py --arms logs/v135/strategy-validation.json --n 200 --seed 42 | tee logs/v135/strategy-permutation.log
python scripts/backtest/validate_component.py --stage validation --headroom-mechanism --arms logs/v135/strategy-validation.json --permutation-p <p_value printed above> --title "v135 strategy h=<selected h> VALIDATION" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-06-v135-strategy-validation.md --out-json docs/superpowers/results/2026-10-06-v135-strategy-validation.json
python -c "import sys, json; sys.path.insert(0,'scripts/backtest'); import validate_component as vc; from swingbot.core.backtesting.arms.selection import removed_disclosure; b, c = vc.load_arms('logs/v135/strategy-validation.json'); print(json.dumps(removed_disclosure(b, c), indent=1))"
```

A null `p_value` means no `--permutation-p`, which is a FAIL. `PASS` makes the component a ship candidate for V135-15. **Stop rule:** `FAIL` closes the component, budget spent and final.

- [ ] **Step 6: Write the results doc and commit**

`docs/superpowers/results/2026-10-06-v135-strategy.md`, same contents as V135-13 Step 6, modelled on `docs/superpowers/results/2026-10-04-v122-strategy.md`. State that the strategy gate, live and replay, and the clause-6 reading all use the level map built at each trade's signal bar.

```bash
git add docs/superpowers/results/2026-10-06-v135-strategy*
git commit -m "docs(v135): strategy component funnel result"
```

### Task V135-15: Ship or close

**Files:**
- Modify only if exactly one component passed VALIDATION: `swingbot/config.py` (the two Field defaults and the scope's `help`), `.env.example`, `tests/test_config_headroom.py`, `tests/backtesting/test_headroom_witness.py`, `tests/backtesting/arms/test_reachability.py`

**Interfaces:**
- Consumes: the V135-13 and V135-14 verdicts.
- Produces: shipped defaults, or nothing (the gate stays inert).

**Cross-plan (audit 2026-10-10):** do not merge `main` into the worktree before this task's verdict is read from both components' records (the arms' `code_hash()` stamps must still match while any judge may re-read them); the merge happens only in V135-17.

- [ ] **Step 1: Branch on the verdicts**

- **Neither passed:** the defaults stay `off` / `0`. Skip to V135-16.
- **Both passed:** stop and ask the partner with `AskUserQuestion`. The spec defers "the scope type becomes a set" to that moment; do not change the field type from this plan.
- **Exactly one passed:** do Steps 2-4, with `<scope>` and `<h>` the passing component and its selected value.

- [ ] **Step 2: Make the witness pin "off" explicitly, since "off" is no longer the default**

In `tests/backtesting/test_headroom_witness.py`, replace the test function with:

```python
@pytest.mark.slow
def test_scope_off_replay_matches_the_pre_gate_witness(monkeypatch):
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "off")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 0.0)
    current = json.loads(json.dumps(witness()))
    assert current["rows"], "fixture must produce trades or the witness proves nothing"
    assert current["strategy_level_map_builds"] > 0, "fixture must exercise the TP2 map build"
    assert current == json.loads(WITNESS.read_text(encoding="utf-8"))
```

In `tests/test_config_headroom.py`, change the two default tests to the shipped values: `field.default == "<scope>"` with `config.HEADROOM_SCOPE == "<scope>"`, and `config._cast(field, field.default) == <h>` with `config.HEADROOM_MIN_R == <h>`; rename them `test_scope_ships_on_for_<scope>` and `test_min_r_ships_at_the_validated_value`. In `tests/backtesting/arms/test_reachability.py::test_headroom_knobs_are_threaded_through_scan_params`, change the assertion to `params.headroom_scope == "<scope>" and params.headroom_min_r == <h>`.

- [ ] **Step 3: Flip the defaults**

In `config.py`, set `default="<scope>"` on `HEADROOM_SCOPE` and `default="<h>"` on `HEADROOM_MIN_R`. Replace the scope help's sentence "Ships OFF: each scope is its own pre-registered measurement and flips on only if its one VALIDATION shot passes." with "ON for <scope> entries since v135's VALIDATION (`docs/superpowers/results/2026-10-06-v135-<scope>-validation.md`)." Set the same two values in `.env.example` and replace its "Ships OFF" comment line the same way.

- [ ] **Step 4: Run the narrow tests and commit**

Run: `python scripts/dev/testrun.py file tests/test_config_headroom.py`, `... file tests/backtesting/test_headroom_witness.py`, `... file tests/infra/test_env_example_sync.py`, `... file tests/backtesting/arms/test_reachability.py`, `... file tests/backtesting/arms/test_headroom_replay.py`, `... file tests/scanning/test_headroom_live.py`
Expected: all PASS. A test in the last two files that relied on the old default must set the knobs it needs explicitly; fix the test's setup, never the gate.

```bash
git add swingbot/config.py .env.example tests/test_config_headroom.py tests/backtesting/test_headroom_witness.py tests/backtesting/arms/test_reachability.py
git commit -m "feat(v135): headroom veto on for the <scope> scope at h=<h> after VALIDATION PASS"
```

This plan does not touch production `.env` overrides. If production pins either key, mirroring that is a `mirror-prod` task after merge.

### Task V135-16: Full-suite verification

**Files:** no new feature files. Fix only failures attributable to this plan, each with its narrow test.

- [ ] **Step 1: The one full run**

Run `python scripts/dev/testrun.py full` once in the worktree, or dispatch the `test-runner` subagent naming the worktree. Green means `0 failed` and `0 xfailed`; a changed pass count is not a failure. If it is red, fix forward from the failures the run names: they are this plan's regressions. Before blaming the plan, check the failing file is in the diff's reach and run it alone (`python scripts/dev/testrun.py file <test>`); the shared-DB suite is known to flake under load.

- [ ] **Step 2: Complexity over everything the plan touched**

```bash
python -m radon cc -s -n C swingbot/config.py swingbot/scan_params.py swingbot/core/edge/gates.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/analyze.py swingbot/core/scanning/scan_run.py swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/backtest_scenarios.py swingbot/core/backtesting/arms/reachability.py swingbot/core/backtesting/arms/selection.py swingbot/core/backtesting/arms/headroom_clauses.py swingbot/core/backtesting/arms/dryup_clauses.py scripts/backtest/validate_component.py
```

Expected: no block this plan wrote or changed at 15 or above. Legacy blocks may appear at their index-recorded scores or lower: `_scan_one` E (36), `replay_scenarios` C (14 after V135-8), `iter_trades` C (14), `_emit_signal` C (12). Any other C-or-worse line in a function this plan edited is a failure to fix here.

- [ ] **Step 3: Commit any fix**

Each fix is its own commit with its narrow test, `fix(v135): <what>`. If Step 1 was green and Step 2 clean, there is nothing to commit.

### Task V135-17: Close-out

**Files (all on `main`, after the merge):**
- Modify: `docs/claude/backtest-methodology.md` (two rows in "Closed pre-registrations")
- Modify if the mirror check reports drift: `AGENTS.md`
- Move: `docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md` → `docs/superpowers/specs/implemented/`; the three `docs/superpowers/plans/2026-10-06-v135-headroom-veto_*.md` files → `docs/superpowers/plans/implemented/`
- Modify: the moved index's `## Progress` block, `**Bump:**` and `**Edge:**` lines; the moved spec's `**Status:**` and `**Bump:**` lines; every reference to the old paths

**Interfaces:**
- Consumes: a green V135-16, both results docs committed on the branch.
- Produces: the code on `main` (inert, or one scope on), two closed-table rows, documents off the live list.

- [ ] **Step 1: Merge the branch**

Invoke `worktree-lifecycle`. From the main tree: confirm `git status --short` shows no change to any file the branch touches, then

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-06-v135-headroom-veto -m "merge(v135): headroom veto -- gate, call sites, funnel reading, measured results"
```

A conflict-free merge is not re-tested. If the merge resolved conflicts (most likely in `config.py`, `reachability.py` or `validate_component.py`, which v128 and v129 also edit), that resolution is unrun code: run `python scripts/dev/testrun.py full` once more and fix forward. Do not delete the branch or the worktree as part of this task; removal follows `document-lifecycle.md` and `git-safety.md` and is the partner's call if anything is unmerged.

- [ ] **Step 2: Add the two rows to the closed-pre-registrations table**

In `docs/claude/backtest-methodology.md`, insert directly under the "Closed pre-registrations — do not re-run these" table's header separator (newest first) one row per component, with the measured numbers copied from the results docs (`pooled-numbers`: read them from the files, never from memory):

```markdown
| Headroom veto, confluence scope (every confluence scenario, both directions; `HEADROOM_MIN_R` threshold), `h ∈ {0.5, 0.75, 1.0}` (v135) | **<PASS at VALIDATION / NO-LIFT at Stage n / FAILED at Stage 3>; VALIDATION <spent / not spent, remains available>.** <universe size, horizons, both engines; baseline → component rows per cell; fold-train ΔWR and paired MDE per cell; ΔExpR per cell; removed / replacement counts and cut % per cell; baseline-reading flagged WR vs retained WR and flagged ExpR per cell; `no_map` and `unreadable` shares; per-direction removals and the one-direction statement; top-two horizon shares; for stages reached: Stage 1 verdict, fold rows, permutation p and the six clauses>. `HEADROOM_SCOPE` <stays `off`; code remains inert / is `confluence` at `h=<x>`>. Reopening needs a mechanism other than "an opposing level with ≥ 2 source families nearer than `h ∈ {0.5, 0.75, 1.0}` × risk". | `results/2026-10-06-v135-preregistration.md`, `results/2026-10-06-v135-confluence.md` |
| Headroom veto, strategy scope (EMA Crossover, VWAP, Fibonacci, Support/Resistance, RSI, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence; `HEADROOM_MIN_R` threshold), `h ∈ {0.5, 0.75, 1.0}` (v135) | **<same shape, the strategy component's own stage and numbers>.** Gate (live and replay) and clause-6 flags all read the level map built at each trade's signal bar. `HEADROOM_SCOPE` <...>. Reopening needs a mechanism other than "an opposing level with ≥ 2 source families nearer than `h ∈ {0.5, 0.75, 1.0}` × risk". | `results/2026-10-06-v135-preregistration.md`, `results/2026-10-06-v135-strategy.md` |
```

The angle-bracket parts are the outcome, which does not exist until V135-13 and V135-14 have run; fill each from that component's results doc and leave none in the committed row. A passed component still gets its row: the shot is spent and must not be re-run.

- [ ] **Step 3: Mirror for Codex**

`docs/claude/` changed, so the Codex mirror ships in the same commit:

```bash
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: PASS. If the check names `AGENTS.md`, update its condensed text to match and re-run. `AGENTS.md` does not carry the closed table itself, so most likely nothing changes; the test is what decides.

- [ ] **Step 4: Move the documents and fix every reference**

```bash
git mv docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-10-06-v135-headroom-veto_0-index.md docs/superpowers/plans/2026-10-06-v135-headroom-veto_1-gate-and-call-sites.md docs/superpowers/plans/2026-10-06-v135-headroom-veto_2-funnel-and-measurement.md docs/superpowers/plans/implemented/
git grep -n "2026-10-06-v135-headroom-veto" -- . ":(exclude)docs/superpowers/plans/implemented" ":(exclude)docs/superpowers/specs/implemented"
```

Re-point every hit to the `implemented/` path (the three plan files' own `**Spec:**` lines and cross-references, the pre-registration and results docs, `config.py`'s help text if a scope shipped) and re-run the `git grep` until no old path remains. The code is on `main` in either outcome, so the destination is `implemented/`, not `no-lift/`.

In the moved index, write the `## Progress` block: the close date, tasks V135-1..V135-17 done, each component's stopping stage and verdict, whether its VALIDATION budget is spent, the shipped defaults, the results doc paths, and the full-suite verdict. Amend `**Bump:**` and `**Edge:**` in the same commit if the outcome differs from the prediction, with one clause saying why: `none` stays when nothing shipped; a shipped scope takes the level `working-conventions.md` § "The three levels" assigns, stated as a level only. In the moved spec, update `**Status:**` and amend `**Bump:**` the same way.

- [ ] **Step 5: Commit the close-out, and release only if a scope shipped**

```bash
git add docs/claude/backtest-methodology.md AGENTS.md docs/superpowers/specs docs/superpowers/plans docs/superpowers/results swingbot/config.py
git commit -m "docs(v135): close out -- headroom veto closed rows, spec and plan moved to implemented"
```

If a scope shipped, the release is its own commit after this one: read `VERSION.json` on disk, increment the line and level the amended `**Bump:**` names, set its `*_updated` stamp, run `python scripts/dev/build_version_matrix.py`, and commit the bump with the regenerated history. Never take a version number from this plan. If nothing shipped, there is no release commit.
