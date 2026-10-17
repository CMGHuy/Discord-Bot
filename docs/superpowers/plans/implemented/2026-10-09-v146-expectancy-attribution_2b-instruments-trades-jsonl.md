# v146 Expectancy attribution: Implementation Plan, part 2b -- instruments I3, the trades file

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: pull one task with `/task-brief V146-8` or `grep -n "^### Task V146-8:" -A 460 docs/superpowers/plans/2026-10-09-v146-expectancy-attribution_2b-instruments-trades-jsonl.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`](../specs/2026-10-09-v146-expectancy-attribution-design.md)
**Index:** [`2026-10-09-v146-expectancy-attribution_0-index.md`](2026-10-09-v146-expectancy-attribution_0-index.md) -- Global Constraints, Handoff decisions, `## Parallelisation` and the task ledger live there and bind the task below.
**Part 2 header:** [`_2a-instruments`](2026-10-09-v146-expectancy-attribution_2a-instruments.md) -- the working directory rule and the seven part-2 decisions (3, 4 and 7 govern V146-8) are stated there once and bind this file. The letter is a file boundary only.

**Scope of this file:** V146-8 (I3: `--trades-jsonl` with `--scenarios`, the as-of map and SPY plumbing).

---

# Phase 3 -- I3: TRAIN per-trade rows for the confluence replay (continued)

### Task V146-8: `--trades-jsonl` with `--scenarios`, as-of map and SPY plumbing

**Model:** opus -- widens a process-pool worker contract that closed pre-registrations depend on (the aggregate must stay identical), ships a benchmark frame into a no-lookahead path, and edits two legacy functions (C19, F65) that may not grow.

**Cross-plan (audit 2026-10-10):** task-tuple slots are fixed across plans: `args[10]` is `spy_df` (this task; `None` when absent) and `args[11]` is v147's `record_blocked`. If `_replay_ticker_gate_rows` exists in `backtest_scenarios.py` (v147 merged), keep task-tuple `args[11]` (`record_blocked`), v147's pool entry point and the `"gate_rows"` output key untouched: whenever a task tuple carries `args[11]`, it also carries `args[10]` (`None` when SPY is not shipped), and `_replay_ticker_rows` reads `args[10]` only. Keep v147's `--record-blocked` argument and dispatch keywords in `run_scenario_mode` when adding `trades_jsonl`.

**Depends on:** V146-7 (shared file `swingbot/core/backtesting/backtest_scenarios.py`; this task consumes `ReplayHit`, `replay_scenarios_detailed` and `scenario_rows.scenario_trade_row`). Read the `no-lookahead` skill before starting (Step 1).

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`_replay_ticker` and `run_scenario_backtest`, lines 192-287 before V146-7 shifted them; find them with `git grep -n "def _replay_ticker\|def run_scenario_backtest" swingbot/core/backtesting/backtest_scenarios.py`)
- Modify: `scripts/backtest/run_backtest_range.py` (`write_trades_jsonl` line 39; `run_scenario_mode` line 166; the `--trades-jsonl` argument line 377; the `--scenarios` dispatch lines 436-437)
- Create: `tests/backtesting/test_scenario_trade_rows_cli.py`

**Interfaces:**
- Consumes (V146-7, this file): `backtest_scenarios.ReplayHit(i, plan, scenario, target_confluence)`; `replay_scenarios_detailed(ticker, df, horizon_key, *, params=None, gates=None, dcb_params=None, asof=None) -> list[ReplayHit]`; `scenario_rows.scenario_trade_row(ticker, horizon_key, df, hit, result, spy_df) -> dict` (keys `scenario_rows.ROW_KEYS`); `scenario_rows` slices SPY to the signal bar itself (`_regime_trend`). Existing: `_build_asof_map(tickers, frames, universe)` and `_market_frame()` in `run_backtest_range.py`; `ExitResult.outcome` (`"not_triggered"` is the only unclosed value, as in `_aggregate`).
- Produces (ledger contract; V146-13 runs it through the CLI):
  - `backtest_scenarios._replay_ticker_rows(args) -> tuple[dict[str, list[ExitResult]], list[dict]]` -- `args` is `_replay_ticker`'s 10-tuple plus `spy_df` as `args[10]`; one row per exit with `outcome != "not_triggered"`.
  - `run_scenario_backtest(..., spy_df=None, collect_rows: bool = False, on_ticker_done=None)` -- with `collect_rows=True` the returned dict gains `"rows": list[dict]` (task order, then horizon, then signal order); `"pooled"` and `"by_horizon"` are identical either way. `on_ticker_done(done: int, total: int)` is an optional per-ticker callback (an addition to the ledger signature that no other task calls; it is how the progress file gets its percent).
  - `run_backtest_range.write_scenario_trades_jsonl(rows: list[dict], path) -> None` (creates the parent directory).
  - `run_scenario_mode(date_from, date_to, min_n, label, *, scale_out, universe=None, trades_jsonl: str | None = None)`; while it runs, `<trades_jsonl>.progress` holds `"<pct>% (<done>/<total> tickers)"`; it is deleted once the rows are written.

**Decisions (inside the spec and the part-2 decisions above):**
- `_replay_ticker` and `_replay_ticker_rows` share one loop, `_replay_exits(args, replay)`, which reads hits as `hit[0]`, `hit[1]`. `_replay_ticker` passes `replay_scenarios` *looked up by name at call time* (the monkeypatch in `tests/scripts/test_training_universe.py` must keep working) and returns the same dict as today.
- `scenario_rows` imports `backtest_scenarios`, so `_replay_ticker_rows` imports `scenario_rows` inside the function (no import cycle).
- The as-of map is built for **every** `--scenarios` run (spec I3: "it gains the same `_build_asof_map` call"). It only feeds `stamp_entry_context`; neither `simulate_exit` nor `_aggregate` reads `entry_context`, so the printed table cannot move. SPY is shipped to the workers only when rows are collected (part-2 decision 4).
- `--context off` is not consulted in scenario mode (it never was; the spec adds no such switch).

- [ ] **Step 1: Read the no-lookahead skill and record the complexity baseline**

Invoke the `no-lookahead` skill (Skill tool) and keep its checklist open: this task hands the **whole** SPY frame and the as-of frame to a worker, and the only code allowed to look at them is `scenario_rows._regime_trend` (slices `spy_df.index <= signal_ts`) and `asof_row(asof, window.index[-1])`. Nothing written in this task may index SPY, `df` beyond `df.index[hit[0]]`, or the as-of frame itself.

Run: `python -m radon cc -s scripts/backtest/run_backtest_range.py swingbot/core/backtesting/backtest_scenarios.py | grep -E " main | run_scenario_mode | run_scenario_backtest | _replay_ticker "`
Expected today: `main - F (65)`, `run_scenario_mode - C (19)`, `run_scenario_backtest - C (14)`, `_replay_ticker - B (7)`. Write the four numbers down; Step 7 compares against them.

- [ ] **Step 2: Write the failing tests**

Create `tests/backtesting/test_scenario_trade_rows_cli.py`:

```python
"""v146 I3: --trades-jsonl with --scenarios -- the row-collecting replay
worker, the SPY task slot, the JSONL writer and the progress file."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting import scenario_rows
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box (the test_backtest_scenarios.py fixture
    family): 16 hits on 4w, all of them closed (measured 2026-10-10)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


# --- the worker ---------------------------------------------------------------

@pytest.mark.slow
def test_replay_ticker_rows_one_row_per_closed_exit():
    df = _structured_df()
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    task = ("AAPL", df, ["4w"], None, None, GATES, True, None, None, None)

    exits, rows = bs._replay_ticker_rows(task + (spy,))

    assert exits == bs._replay_ticker(task)        # the aggregate's input is untouched
    closed = [r for r in exits["4w"] if r.outcome != "not_triggered"]
    assert closed, "fixture must close at least one trade"
    assert len(rows) == len(closed)
    assert [tuple(row) for row in rows] == [scenario_rows.ROW_KEYS] * len(rows)
    assert [(row["outcome"], row["r_total"]) for row in rows] == [(r.outcome, r.r_total) for r in closed]
    assert {(row["ticker"], row["horizon_key"]) for row in rows} == {("AAPL", "4w")}
    assert all(row["confidence_points"] for row in rows)


def test_replay_ticker_rows_skips_untriggered_exits(monkeypatch):
    class _Exit:
        def __init__(self, outcome):
            self.outcome = outcome

    df = make_ohlcv([100.0, 101.0, 102.0])
    hits = [bs.ReplayHit(0, "p0", "s0", (1, [])), bs.ReplayHit(1, "p1", "s1", (2, []))]
    monkeypatch.setattr(bs, "replay_scenarios_detailed", lambda *a, **k: hits)
    monkeypatch.setattr(bs, "simulate_exit",
                        lambda df, i, plan, scale_out: _Exit("win" if i == 0 else "not_triggered"))
    monkeypatch.setattr(scenario_rows, "scenario_trade_row",
                        lambda ticker, hk, df, hit, result, spy_df: {"i": hit.i, "spy": spy_df})

    exits, rows = bs._replay_ticker_rows(("AAPL", df, ["2w"], None, None, {}, True, None, None, None, "SPY"))

    assert [r.outcome for r in exits["2w"]] == ["win", "not_triggered"]
    assert rows == [{"i": 0, "spy": "SPY"}]


# --- run_scenario_backtest ----------------------------------------------------

def test_spy_rides_only_on_the_row_collecting_tasks(monkeypatch):
    seen, calls = {}, []

    def fake_plain(args):
        seen["plain"] = len(args)
        return {"4w": []}

    def fake_rows(args):
        seen["rows"] = (len(args), args[10])
        return {"4w": []}, [{"ticker": args[0]}]

    monkeypatch.setattr(bs, "_replay_ticker", fake_plain)
    monkeypatch.setattr(bs, "_replay_ticker_rows", fake_rows)
    frames = {"AAA": "frame-a", "BBB": "frame-b"}

    plain = bs.run_scenario_backtest(frames, None, None, gates=GATES, horizons=["4w"],
                                     workers=1, spy_df="SPY")
    out = bs.run_scenario_backtest(frames, None, None, gates=GATES, horizons=["4w"], workers=1,
                                   spy_df="SPY", collect_rows=True,
                                   on_ticker_done=lambda done, total: calls.append((done, total)))

    assert "rows" not in plain and seen["plain"] == 10      # today's 10-tuple, no SPY shipped
    assert seen["rows"] == (11, "SPY")
    assert out["rows"] == [{"ticker": "AAA"}, {"ticker": "BBB"}]
    assert calls == [(1, 2), (2, 2)]
    assert (out["pooled"], out["by_horizon"]) == (plain["pooled"], plain["by_horizon"])


# --- the writer and the mode --------------------------------------------------

def test_write_scenario_trades_jsonl_round_trips(tmp_path):
    import run_backtest_range as rr

    rows = [{"ticker": "AAPL", "r_total": np.float64(1.5), "legs": [],
             "entry_context": {"rs_pctile": np.int64(80)}},
            {"ticker": "MSFT", "r_total": -1.0, "legs": [], "entry_context": {}}]
    target = tmp_path / "reports" / "rows.jsonl"            # the directory does not exist yet

    rr.write_scenario_trades_jsonl(rows, target)

    assert [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()] == [
        {"ticker": "AAPL", "r_total": 1.5, "legs": [], "entry_context": {"rs_pctile": 80}},
        {"ticker": "MSFT", "r_total": -1.0, "legs": [], "entry_context": {}}]


def _stub_scenario_mode(monkeypatch, rr, tmp_path, seen):
    """run_scenario_mode with every loader and the replay itself faked."""
    monkeypatch.chdir(tmp_path)                 # it writes backtest_range_summary.txt to cwd
    monkeypatch.setattr(rr, "_tickers_for_run", lambda universe: ["AAA", "BBB"])
    monkeypatch.setattr(rr, "_membership_for_run", lambda universe, tickers: None)
    monkeypatch.setattr(rr, "load_cached", lambda ticker: f"frame-{ticker}")
    monkeypatch.setattr(rr, "_with_context", lambda df, **kw: df)
    monkeypatch.setattr(rr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rr, "_build_asof_map", lambda tickers, frames, universe: {"AAA": "asof-a"})
    monkeypatch.setattr(rr, "_market_frame", lambda: "SPY")

    def fake_backtest(frames, start, end, **kwargs):
        seen.update(kwargs, frames=frames)
        if kwargs["on_ticker_done"] is not None:
            kwargs["on_ticker_done"](1, 2)
            seen["progress_text"] = (tmp_path / "out" / "rows.jsonl.progress").read_text(encoding="utf-8")
        empty = bs._aggregate([])
        stats = {"pooled": empty, "by_horizon": {hk: empty for hk in LEGACY_HORIZONS}}
        if kwargs["collect_rows"]:
            stats["rows"] = [{"ticker": "AAA"}, {"ticker": "BBB"}]
        return stats

    monkeypatch.setattr(rr, "run_scenario_backtest", fake_backtest)


def test_scenario_mode_writes_rows_and_clears_the_progress_file(monkeypatch, tmp_path):
    import run_backtest_range as rr

    seen = {}
    _stub_scenario_mode(monkeypatch, rr, tmp_path, seen)
    target = tmp_path / "out" / "rows.jsonl"

    rr.run_scenario_mode("2020-01-01", "2023-12-31", 30, "TRAIN", scale_out=True,
                         trades_jsonl=str(target))

    assert seen["collect_rows"] is True and seen["spy_df"] == "SPY"
    assert seen["asof_map"] == {"AAA": "asof-a"}
    assert seen["progress_text"].startswith("50.0% (1/2 tickers)")
    assert [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()] == [
        {"ticker": "AAA"}, {"ticker": "BBB"}]
    assert not Path(str(target) + ".progress").exists()     # deleted on completion


def test_scenario_mode_without_the_flag_collects_nothing(monkeypatch, tmp_path):
    import run_backtest_range as rr

    seen = {}
    _stub_scenario_mode(monkeypatch, rr, tmp_path, seen)

    rr.run_scenario_mode("2020-01-01", "2023-12-31", 30, "TRAIN", scale_out=True)

    assert seen["collect_rows"] is False and seen["spy_df"] is None
    assert seen["on_ticker_done"] is None
    assert seen["asof_map"] == {"AAA": "asof-a"}            # spec I3: built for every scenario run
    assert sorted(p.name for p in tmp_path.iterdir()) == ["backtest_range_summary.txt"]
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_trade_rows_cli.py`
Expected: FAIL -- `AttributeError: ... has no attribute '_replay_ticker_rows'`, `TypeError: run_scenario_backtest() got an unexpected keyword argument 'spy_df'`, `AttributeError: ... 'write_scenario_trades_jsonl'` and `TypeError: run_scenario_mode() got an unexpected keyword argument 'trades_jsonl'`.

- [ ] **Step 4: The row-collecting worker and the task slot**

In `swingbot/core/backtesting/backtest_scenarios.py`, keep `_replay_ticker`'s docstring and replace its **body** (the eleven lines from `ticker, df, horizons, ... = args[:8]` to `return out`) with:

```python
    return {hk: [result for _, result in pairs]
            for hk, pairs in _replay_exits(args, replay_scenarios).items()}
```

Directly below `_replay_ticker` add:

```python
def _replay_exits(args, replay) -> dict:
    """{horizon_key: [(hit, ExitResult), ...]} for one ticker -- the loop
    _replay_ticker and _replay_ticker_rows share. `replay` yields (i, plan)
    pairs or ReplayHits; both read as hit[0], hit[1]. args[10] (SPY) is not
    read here: only the row builder needs it."""
    ticker, df, horizons, start, end, gates, scale_out, dcb_params = args[:8]
    asof_df = args[8] if len(args) > 8 else None
    member_spans = args[9] if len(args) > 9 else None
    out = {hk: [] for hk in horizons}
    for hk in horizons:
        for hit in replay(ticker, df, hk, gates=gates, dcb_params=dcb_params, asof=asof_df):
            if not _signal_in_scope(str(df.index[hit[0]].date()), start, end, member_spans):
                continue
            out[hk].append((hit, simulate_exit(df, hit[0], hit[1], scale_out=scale_out)))
    return out


def _replay_ticker_rows(args) -> tuple:
    """_replay_ticker plus one v146 TRAIN row per CLOSED exit: (exits, rows).
    args is _replay_ticker's tuple with the benchmark frame appended as
    args[10]. The whole SPY frame travels; scenario_rows slices it to each
    signal bar (no lookahead), and nothing here indexes it."""
    # Imported here: scenario_rows imports this module.
    from swingbot.core.backtesting import scenario_rows
    ticker, df = args[0], args[1]
    spy_df = args[10] if len(args) > 10 else None
    exits = _replay_exits(args, replay_scenarios_detailed)
    rows = [scenario_rows.scenario_trade_row(ticker, hk, df, hit, result, spy_df)
            for hk, pairs in exits.items() for hit, result in pairs
            if result.outcome != "not_triggered"]
    return {hk: [result for _, result in pairs] for hk, pairs in exits.items()}, rows
```

Below `_resolve_replay_workers` add:

```python
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


def _replay_with_rows(tasks: list, spy_df, workers, on_ticker_done) -> tuple:
    """(per-ticker exits, flat rows): the row-collecting twin of the plain
    run. SPY rides as args[10] of every task."""
    results = _run_replay_tasks(_replay_ticker_rows, [t + (spy_df,) for t in tasks],
                                workers, on_ticker_done)
    return ([exits for exits, _ in results],
            [row for _, ticker_rows in results for row in ticker_rows])
```

In `run_scenario_backtest`, change the signature's last line from `membership: dict | None = None) -> dict:` to:

```python
                          membership: dict | None = None, spy_df=None,
                          collect_rows: bool = False, on_ticker_done=None) -> dict:
```

append this paragraph to its docstring:

```python
    v146: `collect_rows=True` adds "rows" -- one TRAIN row per closed exit
    (scenario_rows.scenario_trade_row) -- and ships `spy_df` to the workers
    as args[10]; "pooled" and "by_horizon" are identical either way.
    `on_ticker_done(done, total)` is called after each ticker returns.
```

replace the six lines from `n = _resolve_replay_workers(workers)` through `per_ticker_results = list(pool.map(_replay_ticker, tasks))` with:

```python
    if collect_rows:
        per_ticker_results, rows = _replay_with_rows(tasks, spy_df, workers, on_ticker_done)
    else:
        per_ticker_results, rows = _run_replay_tasks(_replay_ticker, tasks, workers, on_ticker_done), None
```

and replace the final `return {"pooled": ..., "by_horizon": ...}` statement with:

```python
    stats = {"pooled": _aggregate(all_results),
             "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
    if rows is not None:
        stats["rows"] = rows
    return stats
```

The `tasks = [...]` 10-tuple comprehension and the `results_by_hz` merge loop stay exactly as they are. `_replay_ticker` and `_replay_ticker_rows` are named inside the function bodies, so they resolve from the module at call time and the tests' monkeypatches reach them.

- [ ] **Step 5: The writer, the progress file and the mode**

In `scripts/backtest/run_backtest_range.py`, directly below `write_trades_jsonl` add:

```python
def _jsonable(value):
    """numpy scalars become Python numbers (default=str would write an
    np.int64 as a string); anything else falls back to str."""
    return value.item() if isinstance(value, np.generic) else str(value)


def write_scenario_trades_jsonl(rows, path) -> None:
    """Write one self-contained TRAIN row per closed confluence-replay exit
    (v146 I3; row shape: scenario_rows.ROW_KEYS)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=_jsonable) + "\n")


def _progress_path(trades_jsonl) -> Path:
    return Path(str(trades_jsonl) + ".progress")


def _scenario_progress(trades_jsonl):
    """Per-ticker progress for the long row-collecting replay: a flushed
    line and a percent figure in <trades_jsonl>.progress, which
    _scenario_stats deletes on completion. None when no rows are collected."""
    if not trades_jsonl:
        return None
    target = _progress_path(trades_jsonl)
    target.parent.mkdir(parents=True, exist_ok=True)

    def on_ticker_done(done: int, total: int) -> None:
        pct = 100.0 * done / total
        target.write_text(f"{pct:.1f}% ({done}/{total} tickers)\n", encoding="utf-8")
        print(f"  replay {done}/{total} tickers ({pct:.1f}%)", flush=True)

    return on_ticker_done
```

Directly above `run_scenario_mode` add:

```python
def _scenario_stats(frames, date_from, date_to, *, scale_out, universe, membership, trades_jsonl) -> dict:
    """run_scenario_mode's replay call. v146 I3: every scenario run builds
    the as-of map, so entry_context carries rs_pctile / regime2_state (it
    feeds stamp_entry_context only -- the table cannot move). With
    --trades-jsonl it also ships SPY to the workers, collects one row per
    closed exit, writes them and deletes the progress file."""
    stats = run_scenario_backtest(
        frames, date_from, date_to, gates=CONFLUENCE_GATES, scale_out=scale_out,
        horizons=list(LEGACY_HORIZONS), membership=membership,
        asof_map=_build_asof_map(list(frames), frames, universe),
        spy_df=_market_frame() if trades_jsonl else None,
        collect_rows=bool(trades_jsonl), on_ticker_done=_scenario_progress(trades_jsonl))
    if trades_jsonl:
        rows = stats.pop("rows")
        write_scenario_trades_jsonl(rows, trades_jsonl)
        _progress_path(trades_jsonl).unlink(missing_ok=True)
        print(f"Wrote {len(rows)} trade rows to {trades_jsonl}", flush=True)
    return stats
```

In `run_scenario_mode`, change the signature to

```python
def run_scenario_mode(date_from, date_to, min_n, label, *, scale_out, universe=None, trades_jsonl=None):
```

and replace the three-line `stats = run_scenario_backtest(frames, date_from, date_to, gates=CONFLUENCE_GATES, ...)` statement with one call (a statement for a statement: no branch is added to the C19 function):

```python
    stats = _scenario_stats(frames, date_from, date_to, scale_out=scale_out, universe=universe,
                            membership=membership, trades_jsonl=trades_jsonl)
```

In `main`, change the `--trades-jsonl` help text to `"write one JSONL training row per windowed trade (with --scenarios: one row per closed confluence-replay exit)"`, and the dispatch to (an added keyword, no branch in the F65 function):

```python
    if args.scenarios:
        run_scenario_mode(date_from, date_to, min_n, label, scale_out=args.scale_out,
                          universe=args.universe, trades_jsonl=args.trades_jsonl)
        return
```

A run that dies mid-replay leaves the `.progress` file behind with its last percent; that is intended (it says how far the run got), and the next run overwrites it.

- [ ] **Step 6: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_trade_rows_cli.py`
Expected: PASS, `0 failed` (six tests; the slow-marked one runs too, since `file` does not skip the slow tier).

Then the files that pin the code this task rewired, one run each:

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_parallel.py`
Expected: PASS -- parallel equals sequential, the out-of-order fake pool (it only implements `map`, which `_run_replay_tasks` still calls) and `workers=1` never building a pool.

Run: `python scripts/dev/testrun.py file tests/scripts/test_training_universe.py`
Expected: PASS -- `_replay_ticker` still returns `["p0", "p1", "p2"]` through the monkeypatched `bs.replay_scenarios` for 9- and 10-tuples.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scripts/test_range_trades_jsonl.py`
Expected: PASS (`write_trades_jsonl` is untouched).

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s scripts/backtest/run_backtest_range.py swingbot/core/backtesting/backtest_scenarios.py | grep -E " main | run_scenario_mode | run_scenario_backtest | _replay_ticker | _replay_ticker_rows | _replay_exits | _run_replay_tasks | _drain | _replay_with_rows | _scenario_stats | _scenario_progress | write_scenario_trades_jsonl | _jsonable | _progress_path "`
Expected, against the Step 1 numbers: `main` still F (65) and `run_scenario_mode` still C (19) -- neither may be higher; `run_scenario_backtest` at or below its 14 (the pool branch moved out; if it reads 15 or more, move the `stats["rows"]` assignment into a two-line helper rather than accept it); `_replay_ticker` at or below 7; every new function A or B, below 15.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py scripts/backtest/run_backtest_range.py tests/backtesting/test_scenario_trade_rows_cli.py
git commit -m "feat(v146): --trades-jsonl with --scenarios writes one TRAIN row per closed replay exit (V146-8)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```
