# v133 — Liquidity pools and four-role coverage: Part 2 (report, measurement, close-out)

> Header block, goal, preconditions, frozen readings, global constraints and the parallelisation map live in [`2026-10-06-v133-liquidity-role-coverage_0-index.md`](2026-10-06-v133-liquidity-role-coverage_0-index.md). Read that file first; pull single tasks from this one (`/task-brief V133-7`).

# Phase 3 — Descriptive report

### Task V133-6: Report-only row facts — the target vote count and an `annotate` hook

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`replay_scenarios` signature, one call, one new helper)
- Modify: `scripts/reports/volume_context_report.py` (`_row`, `confluence_rows`, `strategy_rows`, `replay_ticker`, `replay_all`; one new helper)
- Test: `tests/backtesting/test_replay_confluence_counts.py`, `tests/scripts/test_volume_context_report_annotate.py`

**Interfaces:**
- Consumes: `replay_scenarios(ticker, df, horizon_key, *, params=None, gates=None, dcb_params=None, asof=None) -> [(index, TradePlanV2)]`; `volume_context_report.ReportRow(source, direction, outcome, r_multiple, context)`.
- Produces: `replay_scenarios(..., confluence_counts: dict | None = None)`, filled `{plan.plan_id: int}`; `volume_context_report.confluence_rows(..., *, annotate=None)`, `strategy_rows(..., *, annotate=None)`, `replay_all(tickers, horizons, window, *, workers=1, annotate=None)`. An `annotate` hook has the signature `annotate(df, plan, result, votes) -> dict`; its dict is merged into the **row's** context. `votes` is the target vote count for confluence rows and `None` for strategy rows. V133-7 passes `annotate=report_facts`.

**Cross-plan (audit 2026-10-10):** v146 V146-7 moves `replay_scenarios`' body into `replay_scenarios_detailed(ticker, df, horizon_key, *, params=None, gates=None, dcb_params=None, asof=None) -> list[ReplayHit]` in `swingbot/core/backtesting/backtest_scenarios.py`; `ReplayHit` is `(i, plan, scenario, target_confluence)` and `target_confluence` is `(n_confl, families)`. Check first: `git grep -n "def replay_scenarios_detailed" -- swingbot/core/backtesting/backtest_scenarios.py`.
- **If it exists (v146 merged):** do **not** add `confluence_counts` to `replay_scenarios` and do **not** write `_note_votes` — skip Step 5 and the `confluence_counts` tests in Step 2 (write `tests/backtesting/test_replay_confluence_counts.py` instead as one test that `replay_scenarios_detailed(...)` yields hits whose `target_confluence[0]` is an `int >= GATES["min_confluence"]`), and leave `backtest_scenarios.py` out of Files and the Step 9 commit. In Step 1, drop the check that "`n_confl` appears only as a local in `replay_scenarios`" (it now lives on `ReplayHit.target_confluence`); the other three checks stand. In Step 6's `confluence_rows`, iterate `replay_scenarios_detailed(ticker, df.loc[:end], horizon_key, params=params)`, take `index, plan = hit.i, hit.plan`, and fill `votes[hit.plan.plan_id] = hit.target_confluence[0]` before the date filter; everything after (`_extra(annotate, df, plan, result, votes.get(plan.plan_id))`) is unchanged. Step 3's fake must then patch `replay_scenarios_detailed` returning `ReplayHit`-shaped tuples instead of `replay_scenarios` with `confluence_counts`. Step 8 expects `replay_scenarios_detailed`'s helpers all below `C`, with only `_aggregate - C (18)` pre-existing.
- **Otherwise:** as written below.

**First, verify the finding this task rests on (index, frozen reading 9).** Do not skip it: if it no longer holds, the design below is wrong.

- [ ] **Step 1: Verify where the count lives today**

```bash
git grep -n "n_confl" -- swingbot/core/backtesting/backtest_scenarios.py
git grep -n "tp1 = select_structural_target" -- swingbot/core/planning/builders.py
git grep -n "confluence_count\|n_confl\|target_votes" -- swingbot/core/planning/plan_types.py
python -m radon cc -s swingbot/core/backtesting/backtest_scenarios.py
```

Expected: `n_confl` appears only as a local in `replay_scenarios` (assigned from `levels.count_confirming_strategies(window, h, price, sc.take_profit, tolerance_pct=5.0)` and read by `passes_confluence`); `build_confluence_plan` picks `tp1` with `select_structural_target`, so `plan.tp1` is not necessarily `sc.take_profit` and the count cannot be recomputed from the plan; `plan_types.py` has no field for it (no output); `replay_scenarios` is `C (15)`.

Say so concretely in the task report: "the count is a local at `backtest_scenarios.py:<line>`, keyed to the scenario target, absent from `TradePlanV2`; it reaches the row through `confluence_counts` → `votes` → `annotate`". **If any of the four checks differs** (for example a later plan added the count to the plan object), stop and report BLOCKED with what you found: a field already on the plan makes the `confluence_counts` parameter unnecessary.

- [ ] **Step 2: Write the failing replay test**

`tests/backtesting/test_replay_confluence_counts.py`:

```python
"""v133: replay_scenarios can hand out the target-vote count it already computes per scenario."""
import dataclasses
import inspect

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(index / 4)) for index in range(60)]
    return make_ohlcv(trend + box)


def _shape(plan) -> dict:
    shape = dataclasses.asdict(plan)
    shape.pop("plan_id")              # a fresh uuid per run
    return shape


def test_counts_are_handed_out_per_accepted_plan_and_change_nothing():
    df = _structured_df()
    votes: dict = {}
    counted = bs.replay_scenarios("AAPL", df, "4w", gates=GATES, confluence_counts=votes)
    plain = bs.replay_scenarios("AAPL", df, "4w", gates=GATES)
    assert counted, "fixture must yield at least one plan"
    assert [(index, _shape(plan)) for index, plan in counted] == [(index, _shape(plan)) for index, plan in plain]
    assert set(votes) == {plan.plan_id for _, plan in counted}
    assert all(type(count) is int and count >= GATES["min_confluence"] for count in votes.values())
    assert all("report_target_votes" not in plan.entry_context for _, plan in counted)     # never stored


def test_the_count_is_the_one_computed_for_the_scenario_target(monkeypatch):
    monkeypatch.setattr(bs.levels, "count_confirming_strategies", lambda *args, **kwargs: (7, ["x"]))
    votes: dict = {}
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES, confluence_counts=votes)
    assert out and set(votes.values()) == {7}


def test_the_parameter_is_optional_and_keyword_only():
    parameter = inspect.signature(bs.replay_scenarios).parameters["confluence_counts"]
    assert parameter.default is None and parameter.kind is parameter.KEYWORD_ONLY
```

- [ ] **Step 3: Write the failing hook test**

`tests/scripts/test_volume_context_report_annotate.py`:

```python
"""v133: the v121 replay row builders accept an optional ``annotate`` hook for report-only facts."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import volume_context_report as vcr  # noqa: E402

from tests.conftest import make_ohlcv  # noqa: E402

WINDOW = ("2019-01-01", "2023-12-31")


def _frame():
    return make_ohlcv(np.linspace(100, 130, 120), spread_pct=1.0)


def _plan(**extra):
    return SimpleNamespace(source="confluence", direction="bullish", horizon_key="2w", stop_loss=110.0,
                           tp1=140.0, entry_context={"vol_ratio_20": 1.2}, plan_id="p1", **extra)


def _fake_confluence(monkeypatch, plan, result, votes):
    import swingbot.core.backtesting.backtest_scenarios as bs
    import swingbot.core.planning.plan_engine as plan_engine

    def replay_scenarios(ticker, df, horizon_key, *, params=None, confluence_counts=None):
        if confluence_counts is not None:
            confluence_counts.update(votes)
        return [(90, plan)]

    monkeypatch.setattr(bs, "replay_scenarios", replay_scenarios)
    monkeypatch.setattr(plan_engine, "simulate_exit", lambda df, index, plan, scale_out: result)


def test_confluence_rows_hand_frame_plan_result_and_votes_to_the_hook(monkeypatch):
    df, plan, result = _frame(), _plan(), SimpleNamespace(outcome="loss", r_total=-1.0, exit_index=95)
    _fake_confluence(monkeypatch, plan, result, {"p1": 3})
    seen = []

    def annotate(frame, a_plan, a_result, votes):
        seen.append((frame is df, a_plan is plan, a_result is result, votes))
        return {"report_fact": votes * 10}

    rows = vcr.confluence_rows("TEST", df, ("2w",), WINDOW, None, annotate=annotate)
    assert seen == [(True, True, True, 3)]
    assert rows == [vcr.ReportRow("confluence", "bullish", "loss", -1.0, {"vol_ratio_20": 1.2, "report_fact": 30})]
    assert plan.entry_context == {"vol_ratio_20": 1.2}           # the fact is on the row, never on the plan


def test_without_a_hook_confluence_rows_are_what_they_were(monkeypatch):
    plan, result = _plan(), SimpleNamespace(outcome="win", r_total=1.5, exit_index=95)
    _fake_confluence(monkeypatch, plan, result, {"p1": 3})
    rows = vcr.confluence_rows("TEST", _frame(), ("2w",), WINDOW, None)
    assert rows == [vcr.ReportRow("confluence", "bullish", "win", 1.5, {"vol_ratio_20": 1.2})]


def test_strategy_rows_call_the_hook_with_no_vote_count(monkeypatch):
    df = _frame()
    plan = SimpleNamespace(source="strategy", direction="bearish", horizon_key="2w", stop_loss=135.0,
                           tp1=90.0, entry_context={})
    result = SimpleNamespace(outcome="loss", r_total=-1.0, exit_index=95)

    class FakeEngine:
        strategies = ("RSI",)

        def iter_trades(self, *args):
            yield str(df.index[90].date()), plan, result

    import swingbot.core.backtesting.arms.strategy_engine as strategy_engine
    import swingbot.core.planning.params as params
    monkeypatch.setattr(strategy_engine, "StrategyEngine", FakeEngine)
    monkeypatch.setattr(params, "stamp_entry_context", lambda p, window, asof: setattr(p, "entry_context", {"ok": 1}))
    rows = vcr.strategy_rows("TEST", df, ("2w",), WINDOW, None,
                             annotate=lambda frame, a_plan, a_result, votes: {"votes": votes, "exit": a_result.exit_index})
    assert rows == [vcr.ReportRow("strategy", "bearish", "loss", -1.0, {"ok": 1, "votes": None, "exit": 95})]


def test_replay_all_threads_the_hook_to_every_ticker(tmp_path, monkeypatch):
    tasks = []
    monkeypatch.setattr(vcr, "PROGRESS", tmp_path / "progress")
    monkeypatch.setattr(vcr, "replay_ticker", lambda task: tasks.append(task) or [])
    hook = lambda *a: {}  # noqa: E731
    assert vcr.replay_all(["AAA", "BBB"], ("2w",), WINDOW, annotate=hook) == []
    assert tasks == [("AAA", ("2w",), WINDOW, hook), ("BBB", ("2w",), WINDOW, hook)]
    tasks.clear()
    vcr.replay_all(["AAA"], ("2w",), WINDOW)
    assert tasks == [("AAA", ("2w",), WINDOW, None)]


def test_replay_ticker_accepts_the_old_three_field_task(monkeypatch):
    seen = {}

    def builder(name):
        def rows(ticker, df, horizons, window, params, *, annotate=None):
            seen[name] = annotate
            return []
        return rows

    monkeypatch.setattr(vcr, "load_frame", lambda ticker: _frame())
    monkeypatch.setattr(vcr, "confluence_rows", builder("confluence"))
    monkeypatch.setattr(vcr, "strategy_rows", builder("strategy"))
    assert vcr.replay_ticker(("AAA", ("2w",), WINDOW)) == []
    assert seen == {"confluence": None, "strategy": None}
    hook = lambda *a: {}  # noqa: E731
    vcr.replay_ticker(("AAA", ("2w",), WINDOW, hook))
    assert seen == {"confluence": hook, "strategy": hook}
```

- [ ] **Step 4: Run both to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_replay_confluence_counts.py`
Expected: FAIL with `TypeError: replay_scenarios() got an unexpected keyword argument 'confluence_counts'`.
Run: `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report_annotate.py`
Expected: FAIL with `TypeError: confluence_rows() got an unexpected keyword argument 'annotate'`.

- [ ] **Step 5: Implement the out-parameter in `backtest_scenarios.py`**

Add this helper directly above `def replay_scenarios`:

```python
def _note_votes(sink: dict | None, plan, n_confl: int) -> None:
    """v133: hand the target-vote count computed for this scenario to a report
    that asked for it, keyed by plan_id. It is never stored on the plan."""
    if sink is not None:
        sink[plan.plan_id] = int(n_confl)
```

Change the signature (one new keyword, last):

```python
def replay_scenarios(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                     gates: dict | None = None,
                     dcb_params: dict | None = None, asof=None,
                     confluence_counts: dict | None = None) -> list:
```

Add one sentence to the docstring, after the `dcb_params` paragraph:

```python
    `confluence_counts`: v133. When a dict is passed, it receives
    {plan_id: target-vote count} for every plan returned -- the number this
    loop already computes for `passes_confluence`. Report-only; None (the
    default) changes nothing.
```

And add one unconditional call directly after the existing `stamp_entry_context(plan, window, asof_row(asof, window.index[-1]))` line:

```python
            _note_votes(confluence_counts, plan, n_confl)
```

The branch lives in the helper, so `replay_scenarios` stays at `C (15)`.

- [ ] **Step 6: Implement the hook in `volume_context_report.py`**

Replace `_row` and add `_extra` below it:

```python
def _row(plan, result, extra=None) -> ReportRow:
    return ReportRow(source=plan.source or "unknown", direction=plan.direction,
                     outcome=result.outcome, r_multiple=result.r_total,
                     context={**(plan.entry_context or {}), **(extra or {})})


def _extra(annotate, df, plan, result, votes) -> dict | None:
    """Report-only facts a caller wants beside the stamped snapshot (v133). They
    go on the ROW, never on the plan, so nothing here is ever stored."""
    return None if annotate is None else annotate(df, plan, result, votes)
```

In `confluence_rows`, change the signature to end `params, *, annotate=None) -> list[ReportRow]:` and replace the loop body with:

```python
    for horizon_key in horizons:
        votes: dict = {}        # plan_id -> target-vote count, filled by replay_scenarios (v133)
        for index, plan in replay_scenarios(ticker, df.loc[:end], horizon_key, params=params,
                                            confluence_counts=votes):
            if str(df.index[index].date()) < start:
                continue
            result = simulate_exit(df, index, plan, scale_out=True)
            if result.outcome not in SKIPPED:
                out.append(_row(plan, result, _extra(annotate, df, plan, result, votes.get(plan.plan_id))))
    return out
```

In `strategy_rows`, change the signature the same way and the append to:

```python
                out.append(_row(plan, result, _extra(annotate, df, plan, result, None)))
```

In `replay_ticker`, replace `ticker, horizons, window = task` with

```python
    ticker, horizons, window, *rest = task
    annotate = rest[0] if rest else None
```

and pass `annotate=annotate` to both `confluence_rows(...)` and `strategy_rows(...)` in its return statement.

In `replay_all`, change the first two lines to:

```python
def replay_all(tickers, horizons, window, *, workers: int = 1, annotate=None) -> list[ReportRow]:
    tasks = [(ticker, tuple(horizons), window, annotate) for ticker in tickers]
```

The hook crosses the process pool inside the task tuple, so it must be a module-level function (V133-7's `report_facts` is).

- [ ] **Step 7: Run the tests to verify they pass**

Expecting `0 failed` on each:

```bash
python scripts/dev/testrun.py file tests/backtesting/test_replay_confluence_counts.py
python scripts/dev/testrun.py file tests/scripts/test_volume_context_report_annotate.py
python scripts/dev/testrun.py file tests/scripts/test_volume_context_report.py
python scripts/dev/testrun.py file tests/scripts/test_volume_context_report_v125.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py
python scripts/dev/testrun.py file tests/backtesting/test_replay_dcb_veto.py
```

The last four are the existing guards on the two edited files.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/backtest_scenarios.py scripts/reports/volume_context_report.py`
Expected: exactly the two pre-existing lines, `_aggregate - C (18)` and `replay_scenarios - C (15)`. A higher number on `replay_scenarios` means a branch leaked out of `_note_votes`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_replay_confluence_counts.py
git commit -m "feat(v133): replay_scenarios can hand out the target-vote count per plan"
git add scripts/reports/volume_context_report.py tests/scripts/test_volume_context_report_annotate.py
git commit -m "feat(v133): optional annotate hook on the v121 replay row builders"
```

### Task V133-7: `role_coverage_report.py` — six tables and the pre-registered verdict

**Files:**
- Create: `scripts/reports/role_coverage_report.py`
- Modify: `.gitignore` (one line)
- Test: `tests/scripts/test_role_coverage_report.py`

**Interfaces:**
- Consumes (imported, never copied) from `volume_context_report`: `ReportRow`, `TRAIN_START`, `TRAIN_END`, `window_refusal(start, end)`, `quintile_edges(rows, key)`, `bucket_table(rows, key, edges)`, `_fmt`, `replay_all(..., annotate=)` (V133-6), `cached_universe()`, `live_rows(trades)`, `load_live_trades()`. From this plan: `liquidity.SWEEP_RECLAIM_BARS` (V133-1), `roles.ROLE_FLAGS` (V133-4), the ten snapshot keys (V133-5).
- Produces: the CLI V133-9 runs; `verdict(rows) -> dict` whose `"verdict"` is `role coverage more informative` or `not more informative`; the JSON record V133-10 branches on; `report_facts(df, plan, result, votes)`, the `annotate` hook.

`bucket_table` already groups by `(source, direction, bucket)`, so confluence-sourced and strategy-sourced trades and both directions are printed separately with no extra code. Fixed buckets are produced by relabelling the key before calling it. The verdict clauses are index frozen reading 15; do not alter them.

- [ ] **Step 1: Write the failing tests**

`tests/scripts/test_role_coverage_report.py`:

```python
"""v133: the role-coverage report -- fixed buckets, six tables, the pre-registered verdict."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import role_coverage_report as rcr  # noqa: E402
import volume_context_report as vcr  # noqa: E402

from swingbot.core.edge.context import FEATURE_KEYS  # noqa: E402
from tests.market import liquidity_fixtures as fx  # noqa: E402


def _rows(n, r, *, direction="bullish", source="confluence", coverage=None, votes=None, **context):
    """n closed trades of R = r each (a win when r > 0)."""
    context = {"role_coverage": coverage, rcr.VOTES_KEY: votes, "horizon_key": "2w", **context}
    return [vcr.ReportRow(source, direction, "win" if r > 0 else "loss", r, dict(context)) for _ in range(n)]


def _population(direction="bullish", *, low=-0.5, mid=0.0, high=0.5, votes_low=0.0, votes_high=0.2, n=30):
    """Coverage ExpR low / mid / high and vote-count ExpR votes_low / votes_high, n trades per bucket."""
    return (_rows(n, low, direction=direction, coverage=1) + _rows(n, mid, direction=direction, coverage=2)
            + _rows(n, high, direction=direction, coverage=3)
            + _rows(n, votes_low, direction=direction, votes=2) + _rows(n, votes_high, direction=direction, votes=5))


@pytest.mark.parametrize("value,bucket", [(None, None), (0, "0-1"), (1, "0-1"), (2, "2"), (3, "3-4"), (4, "3-4")])
def test_coverage_buckets_are_fixed(value, bucket):
    assert rcr.coverage_bucket(value) == bucket


@pytest.mark.parametrize("value,bucket", [(None, None), (1, "<2"), (2, "2"), (3, "3"), (4, "4+"), (9, "4+")])
def test_vote_buckets_are_fixed(value, bucket):
    assert rcr.votes_bucket(value) == bucket


def test_the_report_only_facts_are_in_no_snapshot_key_list():
    from swingbot.core.market.liquidity import LIQUIDITY_KEYS
    from swingbot.core.market.roles import ROLE_KEYS
    for key in rcr.REPORT_ONLY_KEYS:
        assert key not in FEATURE_KEYS and key not in LIQUIDITY_KEYS and key not in ROLE_KEYS


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-06-30"),
                                       ("2023-06-01", "2024-03-29"), ("2019-06-01", "2023-12-31")])
def test_replay_refuses_any_window_outside_train(start, end, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    code = rcr.main(["--source", "replay", "--start", start, "--end", end, "--edges", str(tmp_path / "e.json")])
    assert code == 1 and "refused" in capsys.readouterr().out


def test_a_bucket_under_30_prints_thin_and_no_expectancy():
    out = rcr.render(_rows(29, 1.0, coverage=4) + _rows(30, -1.0, coverage=0), None, source="replay", result=None)
    block = out.split("== 1. role_coverage ==")[1].split("==")[0]
    thin, full = [line for line in block.splitlines() if "confluence" in line][::-1]
    assert "3-4" in thin and thin.rstrip().endswith("N=   29  thin") and "ExpR" not in thin
    assert "0-1" in full and "N=   30" in full and "ExpR -1.0000" in full


def test_the_control_table_holds_confluence_rows_only():
    rows = _rows(30, 1.0, votes=2) + _rows(30, 1.0, source="strategy", votes=None)
    block = rcr.render(rows, None, source="replay", result=None).split("== 2. control")[1].split("\n==")[0]
    assert "confluence" in block and "strategy" not in block


def test_spread_is_none_when_either_bucket_is_thin():
    stats = {"0-1": (29, -0.5), "3-4": (30, 0.5)}
    assert rcr.spread(stats, "0-1", "3-4") is None
    assert rcr.spread({"0-1": (30, -0.5), "3-4": (30, 0.5)}, "0-1", "3-4") == pytest.approx(1.0)
    assert rcr.spread({"0-1": (30, -0.5)}, "0-1", "3-4") is None


def test_verdict_is_more_informative_when_all_four_clauses_hold():
    result = rcr.verdict(_population("bullish") + _population("bearish"))
    assert result["verdict"] == rcr.MORE
    assert result["bullish"]["spread_roles"] == pytest.approx(1.0)
    assert result["bullish"]["spread_votes"] == pytest.approx(0.2)
    assert (result["bullish"]["clause_1"], result["bullish"]["clause_2"], result["bullish"]["clause_3"]) == (True,) * 3


def test_clause_1_fails_when_the_middle_bucket_is_out_of_order():
    result = rcr.verdict(_population(mid=0.9) + _population("bearish"))
    assert result["bullish"]["clause_1"] is False and result["verdict"] == rcr.NOT_MORE


def test_clause_2_fails_when_the_vote_spread_is_at_least_as_wide():
    result = rcr.verdict(_population(votes_low=-0.5, votes_high=0.5) + _population("bearish"))
    assert result["bullish"]["clause_2"] is False and result["verdict"] == rcr.NOT_MORE


@pytest.mark.parametrize("thin_bucket", ["coverage", "votes"])
def test_clause_3_fails_when_any_of_the_five_buckets_is_thin(thin_bucket):
    rows = _population() + _population("bearish")
    drop = (lambda row: row.context["role_coverage"] == 2) if thin_bucket == "coverage" \
        else (lambda row: row.context[rcr.VOTES_KEY] == 5)
    victim = next(row for row in rows if row.direction == "bullish" and drop(row))
    rows.remove(victim)
    result = rcr.verdict(rows)
    assert result["bullish"]["clause_3"] is False and result["verdict"] == rcr.NOT_MORE


def test_clause_4_passes_when_the_bearish_side_is_thin():
    result = rcr.verdict(_population("bullish") + _population("bearish", n=29))
    assert result["bearish"]["thin"] is True and result["clause_4"] is True and result["verdict"] == rcr.MORE


def test_clause_4_fails_when_the_bearish_spread_has_the_other_sign():
    result = rcr.verdict(_population("bullish") + _population("bearish", low=0.5, high=-0.5))
    assert result["clause_4"] is False and result["verdict"] == rcr.NOT_MORE


def test_a_thin_bullish_side_is_never_more_informative():
    result = rcr.verdict(_population("bullish", n=29) + _population("bearish"))
    assert result["verdict"] == rcr.NOT_MORE and result["clause_4"] is False


def test_strategy_rows_never_enter_the_verdict():
    noise = _rows(200, -3.0, source="strategy", coverage=4) + _rows(200, 3.0, source="strategy", coverage=0)
    assert rcr.verdict(_population() + _population("bearish") + noise)["verdict"] == rcr.MORE


@pytest.mark.parametrize("mirror", [False, True], ids=["bullish", "bearish"])
@pytest.mark.parametrize("closes_after,expected", [((98.0, 99.5), True),          # back beyond the stop next bar
                                                   ((98.0, 98.0, 98.0, 98.9), False),
                                                   ((99.5,), True)],              # the stop bar itself closes back
                         ids=["next-bar", "never", "same-bar"])
def test_swept_stop_out_reads_the_stop_bar_and_three_more(mirror, closes_after, expected):
    df = fx.build(fx.walk([105, 100]) + list(closes_after) + [99.9] * 3, mirror=mirror)   # the late 99.9s are too late
    plan = SimpleNamespace(direction=fx.side(mirror), stop_loss=fx.m(99.0, mirror))
    result = SimpleNamespace(outcome="loss", exit_index=6)
    assert rcr.swept_stop_out(df, plan, result) is expected


def test_swept_stop_out_is_none_unless_the_trade_lost():
    df = fx.build(fx.walk([105, 100]))
    plan = SimpleNamespace(direction="bullish", stop_loss=99.0)
    assert rcr.swept_stop_out(df, plan, SimpleNamespace(outcome="win", exit_index=3)) is None
    assert rcr.swept_stop_out(df, plan, SimpleNamespace(outcome="loss", exit_index=None)) is None
    assert rcr.report_facts(df, plan, SimpleNamespace(outcome="win", exit_index=3), 3) == {
        rcr.VOTES_KEY: 3, rcr.SWEPT_KEY: None}


def test_sweep_table_counts_losses_per_source_and_direction():
    rows = (_rows(30, -1.0, **{rcr.SWEPT_KEY: True}) + _rows(10, -1.0, **{rcr.SWEPT_KEY: False})
            + _rows(5, 1.0) + _rows(4, -1.0, source="strategy", **{rcr.SWEPT_KEY: True}))
    table = {(line["source"], line["direction"]): line for line in rcr.sweep_table(rows)}
    assert table[("confluence", "bullish")] == {"source": "confluence", "direction": "bullish",
                                                "losses": 40, "swept_share": 75.0}
    out = rcr.render(rows, None, source="replay", result=None)
    assert "losses=   40  swept  75.00%" in out and "losses=    4  thin" in out


def test_census_is_per_horizon():
    rows = (_rows(3, 1.0, liq_stop_side_atr=2.0, role_context=True, role_location=True, role_path=True,
                  role_trigger=None)
            + _rows(1, 1.0, liq_stop_side_atr=None, role_context=None, role_location=True, role_path=True,
                    role_trigger=None))
    rows += [vcr.ReportRow("strategy", "bearish", "loss", -1.0, {"horizon_key": "4w"})]
    lines = {line["horizon"]: line for line in rcr.census(rows)}
    assert (lines["2w"]["n"], lines["2w"]["live_stop_pool"]) == (4, 75.0)
    assert (lines["2w"]["role_context_none"], lines["2w"]["role_trigger_none"]) == (25.0, 100.0)
    assert lines["4w"]["role_path_none"] == 100.0 and lines["4w"]["live_stop_pool"] == 0.0


def test_a_full_train_replay_prints_and_records_the_verdict(tmp_path, monkeypatch, capsys):
    rows = _population("bullish") + _population("bearish")
    seen = {}
    monkeypatch.setattr(vcr, "cached_universe", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(vcr, "replay_all", lambda tickers, *a, **k: (seen.update(k, tickers=tickers), rows)[1])
    monkeypatch.setattr(rcr, "DEFAULT_EDGES", tmp_path / "edges.json")
    record = tmp_path / "verdict.json"
    assert rcr.main(["--source", "replay", "--edges", str(tmp_path / "edges.json"), "--json", str(record)]) == 0
    out = capsys.readouterr().out
    assert f"VERDICT: {rcr.MORE}" in out and "p=" not in out
    assert seen["annotate"] is rcr.report_facts and seen["tickers"] == ["AAA", "BBB"]
    blob = json.loads(record.read_text(encoding="utf-8"))
    assert blob["verdict"] == rcr.MORE and blob["closed"] == len(rows) and blob["window"] == ["2020-01-01", "2023-12-31"]
    assert json.loads((tmp_path / "edges.json").read_text(encoding="utf-8"))["window"] == ["2020-01-01", "2023-12-31"]


def test_a_recorded_verdict_is_never_overwritten(tmp_path, monkeypatch, capsys):
    record = tmp_path / "verdict.json"
    record.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert rcr.main(["--source", "replay", "--edges", str(tmp_path / "e.json"), "--json", str(record)]) == 1
    assert "runs once" in capsys.readouterr().out and record.read_text(encoding="utf-8") == "{}"


def test_a_partial_replay_prints_no_verdict_and_cannot_record_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: _population())
    edges = str(tmp_path / "e.json")
    assert rcr.main(["--source", "replay", "--tickers", "AAA", "--edges", edges]) == 0
    out = capsys.readouterr().out
    assert rcr.NOT_EVALUATED in out and "VERDICT:" not in out
    assert rcr.main(["--source", "replay", "--tickers", "AAA", "--edges", edges, "--json", str(tmp_path / "v.json")]) == 1
    assert rcr.main(["--source", "replay", "--tickers", "AAA"]) == 1          # would overwrite the default edges
    assert capsys.readouterr().out.count("refused") == 2


def test_live_prints_the_holdout_warning_and_no_verdict(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": [1.0, 2.0, 3.0, 4.0]}', encoding="utf-8")
    old_record = {"status": "win", "source": "confluence", "direction": "bullish", "entry": 100.0,
                  "stop_loss": 95.0, "exit_price": 110.0, "entry_context": {"vol_ratio_20": 1.2}}
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [old_record])
    assert rcr.main(["--source", "live", "--edges", str(edges)]) == 0
    out = capsys.readouterr().out
    assert "holdout" in out and "VERDICT" not in out and "p=" not in out
    assert "None" in out.split("== 1. role_coverage ==")[1].split("\n==")[0]      # an old record buckets as None


def test_live_refuses_without_full_train_edges(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "load_live_trades", lambda: pytest.fail("read the book"))
    assert rcr.main(["--source", "live", "--edges", str(tmp_path / "missing.json")]) == 1
    partial = tmp_path / "partial.json"
    partial.write_text('{"window": ["2022-01-01", "2023-12-31"], "edges": null}', encoding="utf-8")
    assert rcr.main(["--source", "live", "--edges", str(partial)]) == 1
    assert capsys.readouterr().out.count("refused") == 2


def test_liquidity_distance_uses_the_fixed_train_edges():
    rows = [row for value in (0.5, 1.5, 2.5, 3.5, 4.5) for row in _rows(30, 1.0, liq_stop_side_atr=value)]
    edges = vcr.quintile_edges(rows, rcr.QUINTILE_KEY)
    out = rcr.render(rows + _rows(30, 1.0, liq_stop_side_atr=None), edges, source="replay", result=None)
    block = out.split(f"== 4. {rcr.QUINTILE_KEY}")[1].split("\n==")[0]
    assert [name in block for name in ("Q1", "Q5", "None")] == [True] * 3
    no_edges = rcr.render(rows, None, source="replay", result=None).split(f"== 4. {rcr.QUINTILE_KEY}")[1]
    assert "no-edges" in no_edges.split("\n==")[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_role_coverage_report.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'role_coverage_report'`.

- [ ] **Step 3: Write the script**

`scripts/reports/role_coverage_report.py`:

```python
#!/usr/bin/env python3
"""v133 descriptive report: do distinct ROLES separate outcomes better than level VOTES?

Buckets closed trades by ``role_coverage`` (how many of context / location /
path / trigger a setup covered) and, as the control, by the target confluence
count (how many level families voted for the target). Six tables and one
pre-registered verdict. DESCRIPTIVE ONLY: the verdict decides whether a
follow-on expectancy spec is written, never that spec's thresholds, and no
inferential statistic is printed.

``--source replay`` is TRAIN-only (2020-01-01..2023-12-31) and refuses any
window touching 2024-01-01 or later. The verdict is printed only for the full
cached universe over the full TRAIN window, and ``--json`` refuses to
overwrite a recorded verdict: the measurement runs once.
``--source live`` reads the production book, which overlaps the 2026 holdout:
monitoring only, no verdict.

    python scripts/reports/role_coverage_report.py --source replay --workers 4 \\
        --json docs/superpowers/results/2026-10-06-v133-role-coverage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import volume_context_report as vcr  # noqa: E402  v121's bucketing and replay helpers: imported, never copied
from swingbot.core.market.liquidity import SWEEP_RECLAIM_BARS  # noqa: E402
from swingbot.core.market.roles import ROLE_FLAGS  # noqa: E402

MIN_N = 30                                # a bucket under this prints `thin` and no ExpR
VOTES_KEY = "report_target_votes"         # report-only row fact; never a snapshot key
SWEPT_KEY = "report_swept_stop_out"       # report-only row fact; reads bars AFTER the exit
REPORT_ONLY_KEYS = (VOTES_KEY, SWEPT_KEY)
LOW_COVERAGE, MID_COVERAGE, HIGH_COVERAGE = "0-1", "2", "3-4"
LOW_VOTES, HIGH_VOTES = "2", "4+"
QUINTILE_KEY = "liq_stop_side_atr"
POOL_FLAGS = ("stop_in_pool", "target_past_pool")
DEFAULT_EDGES = ROOT / "data" / "v133_train_quintiles.json"
MORE, NOT_MORE = "role coverage more informative", "not more informative"
NOT_EVALUATED = "not evaluated"
HEADER = ("v133 role-coverage report -- DESCRIPTIVE ONLY. The verdict decides whether a follow-on spec is "
          "written, never its thresholds. No inferential statistic is printed.")
LIVE_WARNING = ("source: local TradeLog book. --source live overlaps the 2026 holdout that open pre-registrations "
                "are waiting on: monitoring only, no verdict. Tables 2 and 5 need replay rows and are empty here.")


def coverage_bucket(value) -> str | None:
    if value is None:
        return None
    return LOW_COVERAGE if value <= 1 else (MID_COVERAGE if value == 2 else HIGH_COVERAGE)


def votes_bucket(value) -> str | None:
    if value is None:
        return None
    if value < 2:
        return "<2"
    return str(int(value)) if value < 4 else HIGH_VOTES


def relabel(rows, key: str, label) -> list:
    """The same rows with ``key`` mapped through ``label``, so vcr.bucket_table
    groups them into fixed buckets instead of raw values."""
    return [vcr.ReportRow(row.source, row.direction, row.outcome, row.r_multiple,
                          {key: label(row.context.get(key))}) for row in rows]


def swept_stop_out(df, plan, result) -> bool | None:
    """Table 5: did a losing trade's stop bar, or one of the SWEEP_RECLAIM_BARS
    bars after it, close back beyond the stop price? None unless the trade lost.
    Reads bars after the exit, so it is a report fact and never a snapshot key."""
    if result.outcome != "loss" or result.exit_index is None:
        return None
    start = int(result.exit_index)
    closes = df["Close"].to_numpy(dtype=float)[start:start + SWEEP_RECLAIM_BARS + 1]
    stop = float(plan.stop_loss)
    return bool((closes > stop).any() if plan.direction == "bullish" else (closes < stop).any())


def report_facts(df, plan, result, votes) -> dict:
    """The ``annotate`` hook handed to vcr.replay_all: two facts per replay row."""
    return {VOTES_KEY: votes, SWEPT_KEY: swept_stop_out(df, plan, result)}


def _stat(line: dict) -> str:
    if line["n"] < MIN_N:
        return f"N={line['n']:>5}  thin"
    return (f"N={line['n']:>5}  WR {vcr._fmt(line['win_rate'], '6.2f')}%  "
            f"ExpR {vcr._fmt(line['expectancy_r'], '+.4f')}")


def _bucket_lines(title: str, table) -> list[str]:
    lines = [f"\n== {title} =="]
    lines += [f"{line['source']:<10} {line['direction']:<8} {line['bucket']:<8} {_stat(line)}" for line in table]
    return lines


def _confluence(rows) -> list:
    return [row for row in rows if row.source == "confluence"]


def _quintile_table(rows, edges) -> list[dict]:
    if edges is None:
        return vcr.bucket_table(relabel(rows, QUINTILE_KEY, lambda v: None if v is None else "no-edges"),
                                QUINTILE_KEY, None)
    return vcr.bucket_table(rows, QUINTILE_KEY, edges)


def sweep_table(rows) -> list[dict]:
    """Table 5: per (source, direction), the losing trades and the share that were swept."""
    groups: dict[tuple, list] = {}
    for row in rows:
        if row.context.get(SWEPT_KEY) is not None:
            groups.setdefault((row.source, row.direction), []).append(bool(row.context[SWEPT_KEY]))
    return [{"source": source, "direction": direction, "losses": len(flags),
             "swept_share": 100.0 * sum(flags) / len(flags)}
            for (source, direction), flags in sorted(groups.items())]


def _share(members, test) -> float:
    return 100.0 * sum(1 for row in members if test(row.context)) / len(members)


def census(rows) -> list[dict]:
    """Table 6: per horizon, how often an entry bar had a live stop-side pool, and how often each flag was None."""
    by_horizon: dict[str, list] = {}
    for row in rows:
        by_horizon.setdefault(str(row.context.get("horizon_key") or "unknown"), []).append(row)
    out = []
    for horizon, members in sorted(by_horizon.items()):
        line = {"horizon": horizon, "n": len(members),
                "live_stop_pool": _share(members, lambda context: context.get(QUINTILE_KEY) is not None)}
        for flag in ROLE_FLAGS:
            line[f"{flag}_none"] = _share(members, lambda context, flag=flag: context.get(flag) is None)
        out.append(line)
    return out


def _sweep_lines(rows) -> list[str]:
    lines = [f"\n== 5. sweep stop-outs: losing trades whose stop bar or the next {SWEEP_RECLAIM_BARS} bars "
             "closed back beyond the stop =="]
    for line in sweep_table(rows):
        stat = "thin" if line["losses"] < MIN_N else f"swept {line['swept_share']:6.2f}%"
        lines.append(f"{line['source']:<10} {line['direction']:<8} losses={line['losses']:>5}  {stat}")
    return lines


def _census_lines(rows) -> list[str]:
    lines = ["\n== 6. census per horizon: share of entry bars (percent) =="]
    for line in census(rows):
        nones = "  ".join(f"{flag}=None {line[f'{flag}_none']:5.1f}" for flag in ROLE_FLAGS)
        lines.append(f"{line['horizon']:<8} N={line['n']:>5}  live stop-side pool {line['live_stop_pool']:5.1f}  {nones}")
    return lines


def bucket_stats(rows, direction: str, key: str, label) -> dict[str, tuple]:
    """Confluence-sourced rows of one direction: bucket -> (N, ExpR)."""
    members = [row for row in _confluence(rows) if row.direction == direction]
    return {line["bucket"]: (line["n"], line["expectancy_r"])
            for line in vcr.bucket_table(relabel(members, key, label), key, None)}


def spread(stats: dict, low: str, high: str) -> float | None:
    """ExpR(high) - ExpR(low). None when either bucket is thin or has no closed R,
    so a thin bucket can never leak an ExpR into the verdict."""
    (n_low, exp_low), (n_high, exp_high) = stats.get(low, (0, None)), stats.get(high, (0, None))
    if min(n_low, n_high) < MIN_N or exp_low is None or exp_high is None:
        return None
    return exp_high - exp_low


def _monotone(coverage: dict, spread_roles: float | None) -> bool:
    n_mid, exp_mid = coverage.get(MID_COVERAGE, (0, None))
    if spread_roles is None or n_mid < MIN_N or exp_mid is None:
        return False
    return bool(coverage[LOW_COVERAGE][1] <= exp_mid <= coverage[HIGH_COVERAGE][1] and spread_roles > 0)


def direction_reading(rows, direction: str) -> dict:
    """Clauses 1-3 of the pre-registered verdict for one direction of the confluence population."""
    coverage = bucket_stats(rows, direction, "role_coverage", coverage_bucket)
    votes = bucket_stats(rows, direction, VOTES_KEY, votes_bucket)
    spread_roles = spread(coverage, LOW_COVERAGE, HIGH_COVERAGE)
    spread_votes = spread(votes, LOW_VOTES, HIGH_VOTES)
    five = ([coverage.get(b, (0, None))[0] for b in (LOW_COVERAGE, MID_COVERAGE, HIGH_COVERAGE)]
            + [votes.get(b, (0, None))[0] for b in (LOW_VOTES, HIGH_VOTES)])
    return {"direction": direction, "coverage": coverage, "votes": votes,
            "spread_roles": spread_roles, "spread_votes": spread_votes,
            "clause_1": _monotone(coverage, spread_roles),
            "clause_2": bool(spread_roles is not None and spread_votes is not None and spread_roles > spread_votes),
            "clause_3": min(five) >= MIN_N,
            "thin": min(coverage.get(b, (0, None))[0] for b in (LOW_COVERAGE, HIGH_COVERAGE)) < MIN_N}


def verdict(rows) -> dict:
    """The spec's four clauses. 1-3 are read on bullish confluence trades; 4 asks the
    bearish side to agree in sign unless it is thin (see the plan's frozen readings)."""
    bullish, bearish = direction_reading(rows, "bullish"), direction_reading(rows, "bearish")
    if bearish["thin"]:
        clause_4 = True
    else:
        clause_4 = bool(bullish["spread_roles"] is not None
                        and np.sign(bullish["spread_roles"]) == np.sign(bearish["spread_roles"]))
    more = bullish["clause_1"] and bullish["clause_2"] and bullish["clause_3"] and clause_4
    return {"verdict": MORE if more else NOT_MORE, "clause_4": clause_4, "bullish": bullish, "bearish": bearish}


def _verdict_lines(result: dict | None) -> list[str]:
    if result is None:
        return [f"\n== VERDICT ==\n{NOT_EVALUATED}: a verdict needs the full cached universe over the full TRAIN window"]
    lines = ["\n== VERDICT (confluence-sourced, pre-registered in the v133 spec) =="]
    for name in ("bullish", "bearish"):
        reading = result[name]
        lines.append(f"{name:<8} spread_roles {vcr._fmt(reading['spread_roles'], '+.4f')}  "
                     f"spread_votes {vcr._fmt(reading['spread_votes'], '+.4f')}  "
                     f"clause1={reading['clause_1']} clause2={reading['clause_2']} "
                     f"clause3={reading['clause_3']} thin={reading['thin']}")
    lines.append(f"clause4 (bearish agrees in sign, or is thin) = {result['clause_4']}")
    lines.append(f"VERDICT: {result['verdict']}")
    return lines


def render(rows, edges, *, source: str, result: dict | None) -> str:
    lines = [HEADER] + ([LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
    lines += _bucket_lines("1. role_coverage", vcr.bucket_table(relabel(rows, "role_coverage", coverage_bucket),
                                                                 "role_coverage", None))
    lines += _bucket_lines("2. control: target confluence count (confluence-sourced only)",
                           vcr.bucket_table(relabel(_confluence(rows), VOTES_KEY, votes_bucket), VOTES_KEY, None))
    for flag in ROLE_FLAGS:
        lines += _bucket_lines(f"3. {flag}", vcr.bucket_table(rows, flag, None))
    for flag in POOL_FLAGS:
        lines += _bucket_lines(f"4. {flag}", vcr.bucket_table(rows, flag, None))
    lines += _bucket_lines(f"4. {QUINTILE_KEY}  TRAIN quintile edges={edges}", _quintile_table(rows, edges))
    lines += _sweep_lines(rows) + _census_lines(rows)
    if source == "replay":
        lines += _verdict_lines(result)
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("replay", "live"), required=True)
    ap.add_argument("--start", default=vcr.TRAIN_START)
    ap.add_argument("--end", default=vcr.TRAIN_END)
    ap.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    ap.add_argument("--edges", default=str(DEFAULT_EDGES),
                    help="TRAIN quintile edges for liq_stop_side_atr: written by replay, required by live")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", default=None, help="replay only: record the tables' inputs and the verdict, once")
    return ap


def _replay_refusal(args, partial: bool) -> str | None:
    refusal = vcr.window_refusal(args.start, args.end)
    if refusal:
        return refusal
    if partial and Path(args.edges).resolve() == DEFAULT_EDGES.resolve():
        return ("refused: a --tickers subset or a TRAIN sub-window needs an explicit --edges path other than "
                f"the default {DEFAULT_EDGES.name} (it must not overwrite the full-TRAIN edges)")
    if partial and args.json:
        return "refused: --json records the one full-universe verdict; a partial run has none"
    if args.json and Path(args.json).exists():
        return f"refused: {args.json} already holds a recorded verdict; the measurement runs once"
    return None


def _write_json(path: str, args, rows, edges, result: dict) -> None:
    payload = {"window": [args.start, args.end], "closed": len(rows), "edges": edges, "verdict": result["verdict"],
               "clause_4": result["clause_4"], "bullish": result["bullish"], "bearish": result["bearish"],
               "sweep_stop_outs": sweep_table(rows), "census": census(rows)}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def _run_replay(args) -> tuple | None:
    partial = bool(args.tickers) or (args.start, args.end) != (vcr.TRAIN_START, vcr.TRAIN_END)
    refusal = _replay_refusal(args, partial)
    if refusal:
        print(refusal)
        return None
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    tickers = args.tickers.split(",") if args.tickers else vcr.cached_universe()
    rows = vcr.replay_all(tickers, ALL_HORIZONS, (args.start, args.end), workers=args.workers,
                          annotate=report_facts)
    edges = vcr.quintile_edges(rows, QUINTILE_KEY)
    path = Path(args.edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"window": [args.start, args.end], "edges": edges}, indent=1), encoding="utf-8")
    result = None if partial else verdict(rows)
    if args.json and result is not None:
        _write_json(args.json, args, rows, edges, result)
    return rows, edges, result


def _run_live(args) -> tuple | None:
    path = Path(args.edges)
    if not path.exists():
        print(f"refused: live needs TRAIN quintile edges at {path}; run --source replay first")
        return None
    blob = json.loads(path.read_text(encoding="utf-8"))
    if list(blob.get("window") or ()) != [vcr.TRAIN_START, vcr.TRAIN_END]:
        print(f"refused: edges at {path} were built from window {blob.get('window')}, "
              f"not the full TRAIN {vcr.TRAIN_START}..{vcr.TRAIN_END}")
        return None
    return vcr.live_rows(vcr.load_live_trades()), blob.get("edges"), None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    outcome = (_run_replay if args.source == "replay" else _run_live)(args)
    if outcome is None:
        return 1
    rows, edges, result = outcome
    print(render(rows, edges, source=args.source, result=result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Ignore the edges dump**

In `.gitignore`, directly below the `data/v121_*.json` line, add:

```
data/v133_*.json
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_role_coverage_report.py`
Expected: `0 failed`.

- [ ] **Step 6: Complexity and a refusal smoke check**

Run: `python -m radon cc -s -n C scripts/reports/role_coverage_report.py`
Expected: no output (`_replay_refusal` is the largest at `B (8)`).

Run: `python scripts/reports/role_coverage_report.py --source replay --end 2024-01-01`
Expected: one line starting `refused: replay window 2020-01-01..2024-01-01 is outside TRAIN`, exit code 1, and no replay started. **Do not run a real replay here**, not even on one ticker: `replay_scenarios` costs about 30 s per ticker-horizon and the one measurement is V133-9's.

- [ ] **Step 7: Commit**

```bash
git add scripts/reports/role_coverage_report.py tests/scripts/test_role_coverage_report.py .gitignore
git commit -m "feat(v133): role-coverage report -- six tables and the pre-registered verdict"
```

# Phase 4 — Review, measurement and close-out

### Task V133-8: No-lookahead review and complexity check

**Files:** No new feature files. Fix only what the review finds, each fix with a failing test first in the matching test file from V133-1, V133-2, V133-4 or V133-5.

**Interfaces:** Consumes everything V133-1 .. V133-7 produced. Produces a reviewed branch: V133-9's run is only as good as this task.

This task comes **before** the measurement on purpose. A lookahead bug found after the one TRAIN run would taint a record that cannot be re-run.

- [ ] **Step 1: Invoke the `no-lookahead` skill** over `swingbot/core/market/liquidity.py`, `swingbot/core/market/roles.py` and `swingbot/core/edge/context.py`. For each value, name the bar it may see in one sentence, then trace every slice against that sentence. The slices to walk, by name:

| Where | Operation | Why it is safe (verify, do not assume) |
|---|---|---|
| `structure.pivot_confirmations` | `shift(k)`, `rolling(k)` | row `j` reads `j − 2k .. j`; the pivot at `i` is flagged at `i + 3` |
| `liquidity._side_pools` | `atr_arr[i2 + k]` | ATR at the confirmation bar, which is `≤` the bar the pool exists from |
| `liquidity._is_pool` | `ext[i1 + 1:i2]`, `ext[i2 + 1:i2 + k + 1]` | ends at `i2 + 3`, the pool's own first bar |
| `liquidity._fate` | `ext[exists + 1:]`, `close[dead:dead + 4]` | **reads the future by design**: it builds the event table. Safe only because every reader goes through `pools_asof` |
| `liquidity.pools_asof` | `exists_pos <= t`, `.where(column <= t)` | the single as-of filter; a death or sweep dated after `t` is blanked |
| `liquidity.features_at` | first statement is `pools_asof(table, t)` | confirm no line reads `table` directly |
| `liquidity.liquidity_features` | `df` only, `t = len(df) - 1` | the caller's slice is the time boundary |
| `roles._trigger` | `atr_arr[t]`, `atr_arr[t - 1]`, `reaction_kind(..., floor_index=t - 2)` | `reaction.py` indexes `t` and earlier only |
| `roles.role_features` | `confirmed_pivots(df)[column].iloc[-1]` | v121's truncation-stable last pivot |
| `context._liquidity_and_roles` | passes `df`, `stop`, `target`, `structure` | no bar index of its own |
| `role_coverage_report.swept_stop_out` | `closes[exit:exit + 4]` | **reads bars after the exit**: legal in a report, never in a snapshot. Confirm `SWEPT_KEY` is in no `*_KEYS` tuple |

- [ ] **Step 2: Re-run the tests that are the lookahead contract**

```bash
python scripts/dev/testrun.py file tests/market/test_liquidity_pools.py
python scripts/dev/testrun.py file tests/market/test_liquidity_features.py
python scripts/dev/testrun.py file tests/market/test_roles.py
```

Expected: `0 failed` on each, **with the `slow` every-cut tests run, not deselected**. If the verdict line shows them skipped, run them directly: `python -m pytest tests/market/test_liquidity_pools.py tests/market/test_liquidity_features.py tests/market/test_roles.py -m slow -q`.

- [ ] **Step 3: Prove no production reader bypasses the as-of filter**

```bash
git grep -n "_pool_table(\|pools(\|pools_asof(" -- swingbot scripts
```

Expected: `_pool_table(` is called only by `pools` and `liquidity_features`; the only reader of a pool table is `features_at`, whose first statement is `pools_asof(table, t)`; no file under `scripts/` or elsewhere in `swingbot/` calls `pools(` or indexes a pool table. Any other hit is a finding: route it through `features_at`.

- [ ] **Step 4: Complexity over every file this plan wrote or changed**

```bash
python -m radon cc -s -n C swingbot/core/market/liquidity.py swingbot/core/market/roles.py swingbot/core/edge/context.py swingbot/core/backtesting/backtest_scenarios.py scripts/reports/volume_context_report.py scripts/reports/role_coverage_report.py
```

Expected: exactly three lines, all pre-existing and none higher than today: `entry_context - C (17)`, `_aggregate - C (18)`, `replay_scenarios - C (15)`. Any other line is a function this plan wrote at 11 or more: confirm it is under 15 with `python -m radon cc -s <file>`, and split it if it is not (`code-complexity.md`).

- [ ] **Step 5: Optional second reader.** Dispatch the `task-reviewer` agent on the branch diff with the index's "Review Focus" list as its brief. Fix findings test-first.

- [ ] **Step 6: Commit** any fix as `fix(v133): <what the review found>`. If the review found nothing, write that in the task report; there is nothing to commit.

### Task V133-9: The one TRAIN replay run and its results doc

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v133-role-coverage.txt` (the report's stdout), `docs/superpowers/results/2026-10-06-v133-role-coverage.json` (the recorded verdict), `docs/superpowers/results/2026-10-06-v133-role-coverage.md` (the results doc). Keep the spec's date in the names whatever day the run happens, so they sort beside the spec.

**Interfaces:** Consumes `scripts/reports/role_coverage_report.py` (V133-7) on the reviewed branch (V133-8). Produces the verdict string V133-10 branches on: the JSON's `"verdict"` field, `role coverage more informative` or `not more informative`.

This is a pre-registered measurement. It runs **once**, on TRAIN `2020-01-01..2023-12-31`, over the full cached universe and every horizon. The verdict rule is frozen in the spec and in index frozen reading 15; nothing in it may change after this task starts.

- [ ] **Step 1: Invoke the `backtest-gate` skill.** Confirm: the window is `2020-01-01..2023-12-31`; no VALIDATION or 2026 bar is used to select anything; the CSV cache is populated (`python scripts/data/fetch_backtest_data.py` if not, once, network); the branch is clean and V133-8 is done.

- [ ] **Step 2: Confirm the measurement has not been spent**

Run: `ls docs/superpowers/results/2026-10-06-v133-role-coverage.json`
Expected: `No such file or directory`. If it exists, the run has already happened: read it and go to Step 5. Never delete it to re-run.

- [ ] **Step 3: Confirm nothing else heavy is running.** Another session's backtest may be live:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300 | Select-Object Id, StartTime, CPU
```

If one is, wait for it. Two competing runs make both slower and have been killed mid-run before.

- [ ] **Step 4: Dispatch the `backtest-runner` agent** with exactly this command, from the v133 worktree, in the background (**cross-plan, audit 2026-10-10:** if `python scripts/reports/role_coverage_report.py --help` lists `--instrument` (v158 merged), append `--instrument v1` to the command, and the results doc and JSON record name the instrument `v1`):

```bash
python scripts/reports/role_coverage_report.py --source replay --workers 4 \
  --json docs/superpowers/results/2026-10-06-v133-role-coverage.json \
  > docs/superpowers/results/2026-10-06-v133-role-coverage.txt 2> logs/v133-role-coverage.err
```

Expect hours, not minutes (about 30 s per ticker-horizon across roughly 72 tickers and ten horizons, divided by the workers). Progress, per `working-conventions.md` § Long-running scripts:

- one flushed line per finished ticker in the `.txt` (`[37/72] 51.4%`), printed by `volume_context_report._progress`;
- the percent-complete file `logs/volume_context_report.progress`, rewritten per ticker and deleted when the run ends. Answer "how far along" from that file, never from a paraphrase;
- the agent keeps its own progress file and updates it **before** it starts waiting, not only after.

Ask the agent to return only: the exit code, the `closed trades:` line, Table 5's lines, and the whole `== VERDICT` block. If the run crashes before writing the JSON, fix the crash (test first) and run again: a run that produced no verdict has spent nothing. If it wrote the JSON, it is final.

- [ ] **Step 5: Sanity-check the population before trusting the verdict**

Read the `.txt`. Required, all of them:

- `closed trades:` is in the thousands;
- Table 1 shows both `confluence` and `strategy` rows, and its `None` bucket is not the whole population;
- Table 2 shows `confluence` rows in bucket `2` or higher (a table that is all `None` means the vote count never reached the rows: a V133-6 wiring bug);
- Table 6 shows a non-zero `live stop-side pool` share on at least one horizon.

A run that fails one of these is **not** a "not more informative" result. Report BLOCKED, delete nothing, and ask the partner whether the record stands.

- [ ] **Step 6: Write the results doc**

`docs/superpowers/results/2026-10-06-v133-role-coverage.md`, with these sections and nothing invented. The `pooled-numbers` skill applies: copy every figure from the `.txt` or `.json`, do not retype from memory.

```markdown
# v133 — role coverage vs level-vote count: TRAIN measurement

**Spec:** `docs/superpowers/specs/2026-10-06-v133-liquidity-role-coverage-design.md`
**Plan:** `docs/superpowers/plans/2026-10-06-v133-liquidity-role-coverage_0-index.md`
**Run:** <date of the run>, branch `2026-10-06-v133-liquidity-role-coverage` at <commit>, `--workers 4`
**Window:** TRAIN 2020-01-01..2023-12-31, full cached universe (<N> tickers), all horizons
**Raw output:** `2026-10-06-v133-role-coverage.txt`, `2026-10-06-v133-role-coverage.json`

## Verdict

<the VERDICT line, verbatim>

| | spread_roles | spread_votes | clause 1 | clause 2 | clause 3 | thin |
|---|---|---|---|---|---|---|
| bullish | ... | ... | ... | ... | ... | ... |
| bearish | ... | ... | ... | ... | ... | ... |

Clause 4 (bearish agrees in sign, or is thin): <True/False>

The verdict decides only whether a follow-on expectancy spec is written. It picks none of that spec's thresholds.

## Tables 1 and 2 (the two that enter the verdict)

<the two blocks from the .txt, verbatim, in a code fence>

## Tables 3 to 6 (descriptive, no verdict)

<the blocks from the .txt, verbatim, in a code fence>

## What this does and does not show

<three to six plain sentences: what separated, what did not, which buckets were thin.
No claim beyond the tables. No threshold proposed.>
```

Every `<...>` and `...` above is a slot to fill from the run's two files; none may remain in the committed doc.

- [ ] **Step 7: Commit the three files on the branch**

```bash
git add docs/superpowers/results/2026-10-06-v133-role-coverage.txt docs/superpowers/results/2026-10-06-v133-role-coverage.json docs/superpowers/results/2026-10-06-v133-role-coverage.md
git commit -m "docs(v133): record the TRAIN role-coverage verdict"
```

Quote the verdict line and the two bullish spreads in the commit body exactly as printed.

### Task V133-10: Full-suite verification and verdict-dependent close-out

**Files:** No new feature files; fix only failures attributable to this plan, with their narrow tests. Branch A's release touches `VERSION.json` and `swingbot/admin/version_history.json`. Branch B edits `docs/claude/backtest-methodology.md` and the plan and spec headers.

- [ ] **Step 1: The one full-suite run.** Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` subagent) over everything this plan implemented. Wait first if another session's backtest is running. Green requires `0 failed`, `0 xfailed`. **If it is not green, fix forward from the failures it names**: they are this plan's regressions. A changed pass count alone is not a failure. Before blaming this plan for an unrelated red test, check the diff scope and run that file alone (`testing-cost.md`).

- [ ] **Step 2: Watch replay-heavy tests.** Every stamped plan now also builds the pool table (about 5 ms on a 700-bar frame). If a test's runtime regresses noticeably, measure before optimising, and never change a pool, sweep or role definition to save time. The safe optimisation, if one is needed, is to compute `atr(df, 14)` once in `entry_context` and pass it down: a refactor with its own witness run, not part of this task.

- [ ] **Step 3: Read the verdict** from `docs/superpowers/results/2026-10-06-v133-role-coverage.json` and follow exactly one branch. Read `document-lifecycle.md` and `working-conventions.md` § Versioning before either.

**Branch A — `role coverage more informative`:**

- [ ] Merge the branch to `main` with the `worktree-lifecycle` skill (check no other session is in the worktree first). Do not re-run the suite after a conflict-free merge; a merge that resolved conflicts in `context.py`, `backtest_scenarios.py` or `volume_context_report.py` gets one more full run.
- [ ] Release per `working-conventions.md` § Versioning. Read `VERSION.json` **as it is on disk at that moment** (never this plan, never memory), bump the **bot** line at **patch** level, set `bot_updated` (UTC, `YYYY-MM-DD HH-MM-SS`), and commit `release(bot): <new> -- v133 liquidity and role-coverage snapshot keys`. Then run `python scripts/dev/build_version_matrix.py`, commit `swingbot/admin/version_history.json` as `chore(bot): <new> -- v133 liquidity and role-coverage snapshot keys`, and run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`.
- [ ] Close out with `/close-out`: `git mv` the three plan files into `docs/superpowers/plans/implemented/`. **The spec stays at the top level of `docs/superpowers/specs/`**: it is live until its follow-on spec is written (`document-lifecycle.md`: a spec moves only when nothing live still builds from it). Add one line under the spec's header saying so, with the verdict and the results path. Re-point every reference to the moved plan files. Remove the worktree and its merged branch as part of the same close-out.
- [ ] No row is added to the closed pre-registrations table: nothing closed. Tell the partner the verdict permits a follow-on `expectancy` spec (for example a minimum `role_coverage` on confluence scenarios). That spec is **not** part of this plan. It must freeze its grid without reading this report's buckets, state why a conjunction across roles is not a re-run of v17 or v33, and clear the v72 gate through the standard funnel (`measure_arms.py`, Stage −1 to Stage 3). Table 5 may separately motivate a `harvest` spec on stop placement, under the v92 gate.

**Branch B — `not more informative`:**

- [ ] Do **not** merge. On the branch, add a closing commit whose body states the verdict and that the branch is deliberately left unmerged. Never delete the branch: it is the only copy of tested code.
- [ ] On `main`: copy the three results files from the worktree into `docs/superpowers/results/`. Amend the `Bump:` line of the plan index and of the spec to `none` with one clause ("measurement closed not-more-informative; no code reached main"). Add a closing note at the end of the index file naming the branch `2026-10-06-v133-liquidity-role-coverage`, the verdict, and that not merging was a considered decision. Then `git mv` the three plan files and the spec into `docs/superpowers/plans/no-lift/` and `docs/superpowers/specs/no-lift/`, and re-point every reference to them.
- [ ] Add one row at the top of the "Closed pre-registrations — do not re-run these" table in `docs/claude/backtest-methodology.md`. Copy each figure from the JSON:

```markdown
| Role coverage vs level-vote count, descriptive (v133): does `role_coverage` (0-1 / 2 / 3-4) separate confluence outcomes better than the target confluence count (2 / 3 / 4+)? | **NOT MORE INFORMATIVE on TRAIN; measurement only, no VALIDATION budget involved, NOT merged to `main`.** TRAIN 2020-01-01..2023-12-31, <N> tickers, <closed> closed trades. Bullish confluence: `spread_roles` <x>R against `spread_votes` <y>R; clauses 1 / 2 / 3 = <...>; bearish <thin or its spread>; clause 4 = <...>. <one sentence naming the clause that failed>. The ten snapshot keys and the report stay on the branch. Do not re-run; a follow-on needs a different role definition or a different control, pre-registered on its own | `results/2026-10-06-v133-role-coverage.md`, `plans/no-lift/2026-10-06-v133-liquidity-role-coverage_0-index.md`, branch `2026-10-06-v133-liquidity-role-coverage` |
```

Every `<...>` is filled from the JSON before the commit. `docs/claude/` changed, so the Codex mirror rule applies: update `AGENTS.md` only if it carries a condensed copy of that table (`git grep -n "Closed pre-registrations" -- AGENTS.md`); `tests/hooks/test_codex_mirror.py` is the check.
- [ ] One commit on `main`: `docs(v133): close out not-more-informative into no-lift/`. No release, no version bump, no follow-on spec. Remove the worktree per `document-lifecycle.md`; the branch stays.

- [ ] **Step 4: Append the outcome** to `.superpowers/sdd/progress.md` (verdict, branch taken, commits).
