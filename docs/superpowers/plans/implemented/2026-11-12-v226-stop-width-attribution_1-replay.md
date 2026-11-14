# v226 — Stop-width attribution, part 1: replay plumbing (V226-1..V226-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v226 — Stop-width attribution](../specs/2026-11-12-v226-stop-width-attribution-design.md) (§ The grouping, § Data: Provenance and Checkpointing, § Tests)
**Index:** [`_0-index.md`](2026-11-12-v226-stop-width-attribution_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and its cross-task contracts. Every task below implicitly includes the index's Global Constraints.

This part makes the TRAIN replay trustworthy before the study reads it: a
truncation test proving `entry_context["stop_atr"]` is point-in-time on the
replay path (V226-1), a per-ticker result hook in the scenario replay
(V226-2), a run sidecar `<path>.run.json` (V226-3), and per-ticker row
persistence with skip-on-restart whose printed table after a restart equals
an uninterrupted run (V226-4).

All work happens in worktree `.claude/worktrees/2026-11-12-v226-stop-width-attribution`
(branch of the same name). Run every command below from that worktree root.

# Phase 1 — Point-in-time check and replay plumbing

### Task V226-1: `entry_context["stop_atr"]` truncation test on the replay path

**Model:** opus — a no-lookahead proof on the replay path whose failure is a research finding to report, not a bug to patch.

**Files:**
- Create: `tests/backtesting/test_scenario_stop_atr_pit.py`

**Interfaces:**
- Consumes: `bs.replay_scenarios_detailed(ticker, df, horizon_key, *, gates=...) -> list[ReplayHit]` (`swingbot/core/backtesting/backtest_scenarios.py:219`, hit fields `i`, `plan`, `scenario`, `target_confluence`); `entry_context(df, *, direction, horizon_key, stop, target, asof=None, entry=None) -> dict` (`swingbot/core/edge/context.py:79`); `atr(df, period)` (`swingbot/core/market/indicators.py`, imported by `context.py:8`).
- Produces: nothing for later tasks (test only).

Why: the spec defines `stop_atr` as `abs(signal close − stop) / ATR14` on the
signal bar and says it is point-in-time because the replay stamps it on
`window = df.iloc[:i+1]` (`backtest_scenarios.py:215`,
`stamp_entry_context(plan, window, ...)`). No test proves it:
`test_signal_fields_ignore_every_bar_after_the_signal` covers
`scenario_rows.signal_fields` only. This task adds the proof. **No production
code changes in this task.** If a test below fails (other than the control
test failing to detect a change), stop: that is a lookahead finding for the
controller, not something to patch inside this task.

- [ ] **Step 1: Write the test file**

Create `tests/backtesting/test_scenario_stop_atr_pit.py`:

```python
"""v226 V226-1: a replayed plan's entry_context["stop_atr"] (and stop_pct)
is point-in-time -- multiplying every bar after the signal leaves it
unchanged, and it equals abs(signal close - stop) / ATR14 on the frame cut
at the signal bar (spec § The grouping: measured from the SIGNAL CLOSE, not
the planned entry or trigger)."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import entry_context
from swingbot.core.market.indicators import atr
from tests.helpers import make_ohlcv

# The replay is the slow part (same tier as test_scenario_rows.py).
pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}
PRICES = ["Open", "High", "Low", "Close"]


def _structured_df():
    """Trend up, then a 60-bar box -- the test_scenario_rows.py fixture,
    copied so the files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.fixture(autouse=True)
def _legacy_scorer(monkeypatch):
    # Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false).
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)


@pytest.fixture(scope="module")
def df():
    return _structured_df()


@pytest.fixture(scope="module")
def hits(df):
    out = bs.replay_scenarios_detailed("AAPL", df, "4w", gates=GATES)
    assert len(out) >= 2, "fixture must produce at least two hits"
    return out


def _cut(df, hits) -> int:
    """The bar after the middle hit: hits before it are compared, every bar
    from it on is spiked."""
    return min(hits[len(hits) // 2].i + 1, len(df) - 1)


def _spiked(df, start: int, factor: float = 3.0):
    out = df.copy()
    out.loc[out.index >= out.index[start], PRICES] *= factor
    return out


def _stop_fields(hits, cut: int) -> dict:
    """{(bar, direction): (stop_atr, stop_pct)} for every hit before `cut`."""
    return {(hit.i, hit.plan.direction): (hit.plan.entry_context.get("stop_atr"),
                                          hit.plan.entry_context.get("stop_pct"))
            for hit in hits if hit.i < cut}


def _direct(frame, hit) -> dict:
    plan = hit.plan
    return entry_context(frame, direction=plan.direction, horizon_key="4w",
                         stop=plan.stop_loss, target=plan.tp1, entry=plan.trigger_price)


def test_replayed_stop_atr_ignores_every_bar_after_the_signal(df, hits):
    cut = _cut(df, hits)
    before = _stop_fields(hits, cut)
    assert before, "fixture must produce a hit before the cut"
    assert all(atr_v is not None and pct is not None for atr_v, pct in before.values())

    spiked_hits = bs.replay_scenarios_detailed("AAPL", _spiked(df, cut), "4w", gates=GATES)

    assert _stop_fields(spiked_hits, cut) == before


def test_stop_atr_is_the_signal_close_distance_in_atr14_units(df, hits):
    hit = hits[len(hits) // 2]
    window = df.iloc[:hit.i + 1]
    close = float(window["Close"].iloc[-1])
    expected = abs(close - hit.plan.stop_loss) / float(atr(window, 14).iloc[-1])

    assert hit.plan.entry_context["stop_atr"] == pytest.approx(expected, abs=1e-6)


def test_stop_atr_from_the_truncated_spiked_frame_matches_the_replay(df, hits):
    hit = hits[len(hits) // 2]
    spiked = _spiked(df, min(hit.i + 1, len(df) - 1))

    direct = _direct(spiked.iloc[:hit.i + 1], hit)

    assert direct["stop_atr"] == hit.plan.entry_context["stop_atr"]
    assert direct["stop_pct"] == hit.plan.entry_context["stop_pct"]


def test_the_check_is_sensitive_to_the_signal_bar_itself(df, hits):
    """Control: spiking FROM the signal bar (inclusive) must move stop_atr,
    so the two tests above would catch a frame that leaked."""
    hit = hits[len(hits) // 2]
    spiked = _spiked(df, hit.i)

    direct = _direct(spiked.iloc[:hit.i + 1], hit)

    assert direct["stop_atr"] != hit.plan.entry_context["stop_atr"]
```

- [ ] **Step 2: Run the new test file**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_stop_atr_pit.py`
Expected: 4 passed.

If `test_replayed_stop_atr_ignores_every_bar_after_the_signal` or
`test_stop_atr_from_the_truncated_spiked_frame_matches_the_replay` fails:
**stop**, do not change production code, and report the failing assertion
(the differing keys and values) to the controller as a lookahead finding.
If `test_stop_atr_is_the_signal_close_distance_in_atr14_units` fails by more
than rounding, report it the same way (the stored value is not the spec's
definition). If only the control test fails, the fixture's spike did not
reach the signal bar's close: raise `factor` to 5.0 in that test and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/backtesting/test_scenario_stop_atr_pit.py
git commit -m "test(v226): entry_context stop_atr is point-in-time on the replay path (V226-1)"
```

### Task V226-2: Per-ticker result hook in the scenario replay

**Model:** sonnet — an additive keyword threaded through three private helpers with a clear contract and stub-driven tests.

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`_run_replay_tasks` :435, `_drain` :447, `_replay_with_rows` :456, `run_scenario_backtest` :464)
- Create: `tests/backtesting/test_scenario_ticker_hook.py`

**Interfaces:**
- Consumes: the existing task tuple (`tasks[i][0]` is the ticker) and `_replay_ticker_rows(args) -> (exits, rows, gate_rows)` where `exits` is `{horizon_key: [ExitResult, ...]}` (already `_results_only`).
- Produces (ledger contract, final):
  - `run_scenario_backtest(..., on_ticker_result=None)`: callable `on_ticker_result(ticker: str, exits: dict[str, list[ExitResult]], rows: list[dict]) -> None`, fired in task order after each ticker, **only when `collect_rows=True`** (ignored otherwise).
  - `_drain(results, total, on_ticker_done, on_result=None)` with `on_result(index: int, result) -> None`, fired **before** `on_ticker_done(done, total)` for the same result, so a progress line never counts a ticker whose rows were not handed over yet.
  - `_run_replay_tasks(worker, tasks, workers, on_ticker_done=None, on_result=None)`.
  - `_replay_with_rows(tasks, workers, on_ticker_done, on_ticker_result=None)`.
  - `on_ticker_done(done, total)` keeps its signature; `pooled`, `by_horizon` and `rows` are unchanged with or without the hook.

Why: `run_backtest_range.py` keeps every row in memory and writes the
`--trades-jsonl` file once at the end, because `on_ticker_done(done, total)`
carries neither the ticker nor its rows. V226-4 persists each ticker as it
finishes through this hook. `pool.map` yields in task order, so the index
passed to `on_result` is the task index.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_scenario_ticker_hook.py`:

```python
"""v226 V226-2: run_scenario_backtest's per-ticker result hook. Fires in
task order with (ticker, exits, rows) only when rows are collected, before
the progress callback for the same ticker, and leaves every stat unchanged."""
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from tests.helpers import make_ohlcv

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _exit(outcome, r_total=0.0, runner=None):
    return SimpleNamespace(outcome=outcome, runner_outcome=runner, r_total=r_total)


def _fake_rows_worker(monkeypatch):
    """Each ticker: one closed and one untriggered exit on 4w, one row per closed exit."""
    def fake_rows(args):
        ticker = args[0]
        r = 2.0 if ticker == "AAA" else -1.0
        exits = {"4w": [_exit("win" if r > 0 else "loss", r), _exit("not_triggered")]}
        return exits, [{"ticker": ticker, "r_total": r}], []

    monkeypatch.setattr(bs, "_replay_ticker_rows", fake_rows)


def test_the_hook_fires_in_task_order_with_ticker_exits_and_rows(monkeypatch):
    _fake_rows_worker(monkeypatch)
    calls = []
    frames = {"BBB": "frame-b", "AAA": "frame-a", "CCC": "frame-c"}

    out = bs.run_scenario_backtest(
        frames, None, None, gates=GATES, horizons=["4w"], workers=1, collect_rows=True,
        on_ticker_result=lambda ticker, exits, rows: calls.append((ticker, exits, rows)))

    assert [ticker for ticker, _, _ in calls] == list(frames)
    assert [rows for _, _, rows in calls] == [[row] for row in out["rows"]]
    assert all(list(exits) == ["4w"] and len(exits["4w"]) == 2 for _, exits, _ in calls)


def test_stats_and_rows_are_identical_with_and_without_the_hook(monkeypatch):
    _fake_rows_worker(monkeypatch)
    frames = {"AAA": "frame-a", "BBB": "frame-b"}
    kwargs = dict(gates=GATES, horizons=["4w"], workers=1, collect_rows=True)

    plain = bs.run_scenario_backtest(frames, None, None, **kwargs)
    hooked = bs.run_scenario_backtest(frames, None, None, on_ticker_result=lambda *a: None, **kwargs)

    assert hooked == plain


def test_the_hook_is_ignored_when_rows_are_not_collected(monkeypatch):
    monkeypatch.setattr(bs, "_replay_ticker_gate_rows", lambda args: ({"4w": []}, []))
    calls = []

    bs.run_scenario_backtest({"AAA": "frame-a"}, None, None, gates=GATES, horizons=["4w"],
                             workers=1, on_ticker_result=lambda *a: calls.append(a))

    assert calls == []


def test_on_result_fires_before_the_progress_callback_for_each_result():
    events = []

    out = bs._drain(iter(["r0", "r1"]), 2,
                    lambda done, total: events.append(("done", done, total)),
                    on_result=lambda index, result: events.append(("result", index, result)))

    assert out == ["r0", "r1"]
    assert events == [("result", 0, "r0"), ("done", 1, 2), ("result", 1, "r1"), ("done", 2, 2)]


def test_drain_without_on_result_keeps_its_old_behaviour():
    events = []

    assert bs._drain(iter([1, 2]), 2, lambda done, total: events.append((done, total))) == [1, 2]
    assert events == [(1, 2), (2, 2)]


@pytest.mark.slow
def test_the_pool_path_passes_task_indices_in_order():
    """Two processes; `abs` is a picklable builtin worker."""
    seen = []

    out = bs._run_replay_tasks(abs, [-1, -2, -3], 2,
                               on_result=lambda index, result: seen.append((index, result)))

    assert out == [1, 2, 3]
    assert seen == [(0, 1), (1, 2), (2, 3)]


def _structured_df(seed=7):
    """Trend up, then a 60-bar box (test_scenario_rows.py's fixture family)."""
    rng = np.random.RandomState(seed)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_on_a_real_replay_the_hooked_rows_concatenate_to_the_collected_rows(monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    frames = {"AAPL": _structured_df(7), "MSFT": _structured_df(11)}
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    calls = []

    out = bs.run_scenario_backtest(
        frames, None, None, gates=GATES, horizons=["4w"], workers=1, spy_df=spy,
        collect_rows=True, on_ticker_result=lambda t, exits, rows: calls.append((t, exits, rows)))

    assert [t for t, _, _ in calls] == ["AAPL", "MSFT"]
    assert [row for _, _, rows in calls for row in rows] == out["rows"]
    closed = [r for _, exits, _ in calls for r in exits["4w"] if r.outcome != "not_triggered"]
    assert len(closed) == len(out["rows"])
    assert bs._aggregate([r for _, exits, _ in calls for r in exits["4w"]]) == out["by_horizon"]["4w"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_ticker_hook.py`
Expected: FAIL — `TypeError: run_scenario_backtest() got an unexpected keyword argument 'on_ticker_result'` and `TypeError: _drain() got an unexpected keyword argument 'on_result'`; `test_drain_without_on_result_keeps_its_old_behaviour` already passes.

- [ ] **Step 3: Implement the hook**

In `swingbot/core/backtesting/backtest_scenarios.py`, replace `_run_replay_tasks`, `_drain` and `_replay_with_rows` (currently :435-461) with:

```python
def _run_replay_tasks(worker, tasks: list, workers, on_ticker_done=None, on_result=None) -> list:
    """worker over every task, sequentially or across the process pool, in
    task order. on_ticker_done(done, total) fires as each result arrives
    (pool.map yields in task order, so the count is monotone but can lag a
    slow early ticker). v226: on_result(index, result) fires first, with the
    task index of that result."""
    n = _resolve_replay_workers(workers)
    if n <= 1 or len(tasks) <= 1:
        return _drain(map(worker, tasks), len(tasks), on_ticker_done, on_result)
    with ProcessPoolExecutor(max_workers=n) as pool:
        return _drain(pool.map(worker, tasks), len(tasks), on_ticker_done, on_result)


def _drain(results, total: int, on_ticker_done, on_result=None) -> list:
    """Collect the results in arrival (= task) order. on_result(index, result)
    fires before on_ticker_done(done, total) for the same result, so progress
    never counts a ticker whose result was not handed over yet."""
    out = []
    for result in results:
        if on_result is not None:
            on_result(len(out), result)
        out.append(result)
        if on_ticker_done is not None:
            on_ticker_done(len(out), total)
    return out


def _replay_with_rows(tasks: list, workers, on_ticker_done, on_ticker_result=None) -> tuple:
    """(per-ticker (exits, gate_rows) pairs, flat trade rows): the
    row-collecting twin of the plain run. SPY already rides in args[10].
    v226: on_ticker_result(ticker, exits, rows) fires per ticker in task order."""
    on_result = None
    if on_ticker_result is not None:
        def on_result(index, result):
            on_ticker_result(tasks[index][0], result[0], result[1])
    results = _run_replay_tasks(_replay_ticker_rows, tasks, workers, on_ticker_done, on_result)
    return ([(exits, gate_rows) for exits, _, gate_rows in results],
            [row for _, ticker_rows, _ in results for row in ticker_rows])
```

In `run_scenario_backtest`, add the keyword last and pass it through:

```python
def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None, workers=None,
                          dcb_params: dict | None = None, asof_map: dict | None = None,
                          membership: dict | None = None, spy_df=None,
                          collect_rows: bool = False, on_ticker_done=None,
                          record_blocked: bool = False, on_ticker_result=None) -> dict:
```

Append to its docstring, right after the sentence
"`on_ticker_done(done, total)` is called after each ticker returns.":

```
    v226: with `collect_rows=True`, `on_ticker_result(ticker, exits, rows)`
    fires as each ticker's result arrives, in task order, before
    `on_ticker_done` for that ticker; `exits` is {horizon_key: [ExitResult]}
    and `rows` that ticker's closed-exit rows. Ignored without collect_rows.
    Every returned value is identical with or without it.
```

and change the row branch:

```python
    if collect_rows:
        per_ticker_results, rows = _replay_with_rows(tasks, workers, on_ticker_done,
                                                     on_ticker_result)
```

Nothing else in the function changes. The parameter is keyword-only and
last, so every existing caller is untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_ticker_hook.py`
Expected: 7 passed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_trade_rows_cli.py`
Expected: all pass (the existing `on_ticker_done` and SPY-slot tests are unchanged).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (no new or changed function in `backtest_scenarios.py` at 15 or above, none worse than its baseline).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py tests/backtesting/test_scenario_ticker_hook.py
git commit -m "feat(v226): per-ticker result hook on the row-collecting scenario replay (V226-2)"
```

### Task V226-3: Run sidecar `<path>.run.json`

**Model:** sonnet — pure helper functions with deterministic inputs; the only side effects are one file write and one `git rev-parse`.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (imports; new helpers after `_scenario_progress`, which ends near :101)
- Create: `tests/backtesting/test_scenario_run_sidecar.py`

**Interfaces:**
- Consumes: `swingbot.config` attributes `CLAMP_STOP_TO_HARD_CAP`, `MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT` (`swingbot/config.py:191, :183, :187`; module globals, hot-reloaded, so read with `getattr` at call time); the PIT membership map shape `{ticker: [(start, end_exclusive), ...]}` from `_membership_for_run` (`end` may be None), or None for a non-PIT universe.
- Produces (ledger contract, final; V226-4 consumes all of them):
  - `STOP_SETTING_NAMES = ("CLAMP_STOP_TO_HARD_CAP", "MIN_STOP_DISTANCE_PCT", "MAX_STOP_LOSS_PCT")`
  - `stop_settings() -> dict` — `{name: getattr(config, name) for name in STOP_SETTING_NAMES}`
  - `RUN_SIDECAR_KEYS = ("git_head", "window", "watchlist", "membership_asof", "command", "stop_settings")`
  - `_run_sidecar_path(trades_jsonl) -> Path` — `<path>.run.json`
  - `_git_head() -> str | None` — `git rev-parse HEAD` in the repo root; None on any failure
  - `_membership_asof(membership: dict | None, today: str) -> str` — the latest non-None span boundary of a PIT map; `today` for None or a map with no boundary
  - `run_sidecar(*, date_from: str, date_to: str, tickers: list[str], universe: str | None, membership: dict | None, argv: list[str], today: str) -> dict` — keys exactly `RUN_SIDECAR_KEYS` in that order; `window={"from": date_from, "to": date_to}`, `watchlist={"universe": universe or "watchlist", "tickers": sorted(tickers)}`, `command=list(argv)`
  - `write_run_sidecar(trades_jsonl, sidecar: dict) -> Path` — writes `json.dumps(sidecar, indent=1, sort_keys=True) + "\n"`, creating the parent directory; returns the path

Why: `_write_provenance` (:648) records only the training-data store snapshot
(`training_data.write_provenance`: data source, feed, adjustment, manifest
hash, integrity sha). The spec (§ Data, Provenance) needs the run itself on
record: git HEAD, window, universe (watchlist and membership as-of), the
command line and the three stop settings, so the results doc can quote what
ran. The sidecar is a **second** file beside the store sidecar; the existing
`<path>.provenance.json` format (pinned by
`tests/backtesting/test_backtest_provenance.py` and
`test_replay_provenance.py`) is untouched. This task only adds the helpers;
V226-4's `_resume_checkpoint` writes the sidecar on a fresh start. **No `.env`
value other than the three stop settings ever enters the sidecar.**

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_scenario_run_sidecar.py`:

```python
"""v226 V226-3: the run sidecar <trades_jsonl>.run.json -- git HEAD, window,
universe (watchlist + membership as-of), command line and the three stop
settings, beside the store provenance sidecar."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from swingbot import config

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import run_backtest_range as rr  # noqa: E402


@pytest.fixture
def stops(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.75)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)


def _sidecar(**over):
    kwargs = dict(date_from="2020-01-06", date_to="2023-12-29", tickers=["MSFT", "AAPL"],
                  universe=None, membership=None,
                  argv=["--scenarios", "--train", "--trades-jsonl", "rows.jsonl"],
                  today="2026-11-12")
    kwargs.update(over)
    return rr.run_sidecar(**kwargs)


def test_the_sidecar_carries_exactly_its_six_fields_in_order(monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: "a" * 40)

    sidecar = _sidecar()

    assert tuple(sidecar) == rr.RUN_SIDECAR_KEYS == (
        "git_head", "window", "watchlist", "membership_asof", "command", "stop_settings")
    assert sidecar == {
        "git_head": "a" * 40,
        "window": {"from": "2020-01-06", "to": "2023-12-29"},
        "watchlist": {"universe": "watchlist", "tickers": ["AAPL", "MSFT"]},
        "membership_asof": "2026-11-12",
        "command": ["--scenarios", "--train", "--trades-jsonl", "rows.jsonl"],
        "stop_settings": {"CLAMP_STOP_TO_HARD_CAP": True, "MIN_STOP_DISTANCE_PCT": 1.75,
                          "MAX_STOP_LOSS_PCT": 2.0},
    }
    json.dumps(sidecar)          # serialisable as written


def test_a_named_universe_and_a_pit_map_are_recorded(monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: None)
    membership = {"AAA": [("2019-01-01", "2021-06-30"), ("2022-01-03", None)],
                  "BBB": [], "CCC": [["2018-05-01", "2020-02-01"]]}

    sidecar = _sidecar(universe="sp500_pit", membership=membership)

    assert sidecar["git_head"] is None
    assert sidecar["watchlist"]["universe"] == "sp500_pit"
    assert sidecar["membership_asof"] == "2022-01-03"


@pytest.mark.parametrize("membership", [None, {}, {"AAA": []}, {"AAA": [(None, None)]}])
def test_membership_asof_falls_back_to_today(membership):
    assert rr._membership_asof(membership, "2026-11-12") == "2026-11-12"


def test_stop_settings_reads_config_at_call_time(monkeypatch, stops):
    first = rr.stop_settings()
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 2.5)

    assert tuple(first) == rr.STOP_SETTING_NAMES
    assert rr.stop_settings()["MIN_STOP_DISTANCE_PCT"] == 2.5
    assert first["MIN_STOP_DISTANCE_PCT"] == 1.75


def test_write_run_sidecar_writes_beside_the_rows_and_round_trips(tmp_path, monkeypatch, stops):
    monkeypatch.setattr(rr, "_git_head", lambda: "b" * 40)
    target = tmp_path / "reports" / "rows.jsonl"            # the directory does not exist yet
    sidecar = _sidecar()

    path = rr.write_run_sidecar(target, sidecar)

    assert path == rr._run_sidecar_path(target) == Path(str(target) + ".run.json")
    assert path.read_text(encoding="utf-8") == json.dumps(sidecar, indent=1, sort_keys=True) + "\n"
    assert json.loads(path.read_text(encoding="utf-8")) == sidecar
    assert not target.exists()                              # the rows file is not touched


def test_git_head_reads_the_repository_head():
    head = rr._git_head()
    assert head is None or re.fullmatch(r"[0-9a-f]{40}", head)


def test_git_head_is_none_when_git_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(rr.subprocess, "run", boom)
    assert rr._git_head() is None

    def bad_exit(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(rr.subprocess, "run", bad_exit)
    assert rr._git_head() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_run_sidecar.py`
Expected: FAIL — `AttributeError: module 'run_backtest_range' has no attribute 'run_sidecar'` (and the other new names).

- [ ] **Step 3: Implement the helpers**

In `scripts/backtest/run_backtest_range.py`, add `import subprocess` to the
stdlib imports (keep them alphabetical: after `import math`, before
`import sys`):

```python
import argparse
import dataclasses
import json
import math
import subprocess
import sys
import warnings
```

Then insert right after `_scenario_progress` (before `_context_symbols`):

```python
#: v226: the three settings that decide every replayed stop; the run sidecar
#: records them so the results doc can show the replay ran today's live stops.
STOP_SETTING_NAMES = ("CLAMP_STOP_TO_HARD_CAP", "MIN_STOP_DISTANCE_PCT", "MAX_STOP_LOSS_PCT")

#: v226: the run sidecar's fields, in order.
RUN_SIDECAR_KEYS = ("git_head", "window", "watchlist", "membership_asof", "command", "stop_settings")


def stop_settings() -> dict:
    """The three stop settings as the replay reads them (config is
    hot-reloaded, so read at call time). Nothing else from .env."""
    return {name: getattr(config, name) for name in STOP_SETTING_NAMES}


def _run_sidecar_path(trades_jsonl) -> Path:
    return Path(str(trades_jsonl) + ".run.json")


def _git_head() -> str | None:
    """The repository HEAD the replay ran at; None when git is unavailable."""
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                              text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def _membership_asof(membership: dict | None, today: str) -> str:
    """The as-of date of the ticker universe: for a point-in-time map the
    latest span boundary it knows, else `today` (the day the watchlist was read)."""
    bounds = [str(bound) for spans in (membership or {}).values()
              for span in spans for bound in span if bound is not None]
    return max(bounds) if bounds else today


def run_sidecar(*, date_from: str, date_to: str, tickers: list[str], universe: str | None,
                membership: dict | None, argv: list[str], today: str) -> dict:
    """v226: what ran -- HEAD, signal window, universe, membership as-of,
    command line and the stop settings (keys: RUN_SIDECAR_KEYS, in order)."""
    return {
        "git_head": _git_head(),
        "window": {"from": date_from, "to": date_to},
        "watchlist": {"universe": universe or "watchlist", "tickers": sorted(tickers)},
        "membership_asof": _membership_asof(membership, today),
        "command": list(argv),
        "stop_settings": stop_settings(),
    }


def write_run_sidecar(trades_jsonl, sidecar: dict) -> Path:
    """<trades_jsonl>.run.json, beside the store's <trades_jsonl>.provenance.json."""
    path = _run_sidecar_path(trades_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path
```

`ROOT` is already defined at the top of the script
(`Path(__file__).resolve().parent.parent.parent`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_run_sidecar.py`
Expected: 10 passed (the parametrised fallback counts 4).

Run: `python scripts/dev/testrun.py file tests/backtesting/test_backtest_provenance.py`
Expected: all pass (store provenance format untouched).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/run_backtest_range.py tests/backtesting/test_scenario_run_sidecar.py
git commit -m "feat(v226): run sidecar helpers for the scenario replay -- HEAD, window, universe, command, stop settings (V226-3)"
```

### Task V226-4: Checkpoint helpers — done-list, resume, per-ticker writer, rebuilt table

**Model:** opus — the rebuilt table must equal the replay's own aggregate and a resume must never keep a half-written ticker; a subtle error silently changes the TRAIN rows the verdict reads.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (imports; new helpers after V226-3's `write_run_sidecar`)
- Create: `tests/backtesting/test_scenario_checkpoint_cli.py`

**Interfaces:**
- Consumes: V226-3 `run_sidecar(...)`, `write_run_sidecar(trades_jsonl, sidecar)`, `_run_sidecar_path(trades_jsonl)`, `RUN_SIDECAR_KEYS`; existing `_jsonable`; `backtest_scenarios._aggregate(results)` (reads only `.outcome`, `.runner_outcome`, `.r_total`); V226-2's hook shape `on_ticker_result(ticker, exits, rows)` with `exits = {horizon_key: [ExitResult]}`.
- Produces (ledger contract, final; V226-4b consumes them):
  - `_done_path(trades_jsonl) -> Path` — `<path>.done.jsonl`; one line per finished ticker `{"ticker": str, "rows": int, "not_triggered": {horizon_key: int}}`
  - `_resume_checkpoint(trades_jsonl, sidecar: dict) -> dict[str, dict]` — done entries by ticker. No done file: fresh start (empties `<path>`, writes the sidecar, returns `{}`). Done file and a sidecar that differs on `RESUME_KEYS`, or no sidecar: `SystemExit(2)`, nothing touched. Otherwise cuts `<path>` to the lines of done tickers and the done-list to its complete lines (drops a half-written tail) and returns the entries.
  - `_checkpoint_writer(trades_jsonl) -> Callable[[str, dict, list], None]` — appends the ticker's rows (flush + `os.fsync`), then its done line (flush + `os.fsync`)
  - `_stats_from_checkpoint(trades_jsonl, horizons: list[str]) -> dict` — `{"pooled", "by_horizon"}` through `_aggregate`
  - `RESUME_KEYS` (`RUN_SIDECAR_KEYS` minus `membership_asof`), `_utc_today() -> str` (UTC ISO date), `_jsonl_lines(path) -> list[tuple[str, dict]]`
  - internal: `_read_run_sidecar`, `_same_run`, `_rewrite_lines`, `_append_synced`, `_NOT_TRIGGERED`

Why: today the TRAIN replay holds every row in memory and writes once at the
end (:281-285), so an interruption loses the run (CLAUDE.md: long runs must
checkpoint). This task builds the pieces; V226-4b wires them into
`_scenario_stats`. Two properties carry the task:

- **The rebuilt table equals the replay's own table.** The rows are exactly
  the closed exits (`scenario_rows.scenario_trade_row` stores
  `float(result.r_total)`, exact through JSON), written ticker by ticker in
  task order, so filtering them by `horizon_key` gives each horizon's closed
  exits in the replay's order; the done-list adds each ticker's
  `not_triggered` count per horizon. `_aggregate` reads nothing else.
- **`membership_asof` is not compared on resume** (`RESUME_KEYS`): for a
  watchlist run it is the day the run started, and a long run may cross
  midnight UTC. Every other sidecar field must match, and the resumed run
  keeps the original sidecar on disk.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_scenario_checkpoint_cli.py`:

```python
"""v226 V226-4/4b: --trades-jsonl checkpointing. Each finished ticker's rows
and a done-list line reach disk as it completes; a restart with the same
arguments replays only the rest, and the rows and the rebuilt table equal an
uninterrupted run."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.marketdata import training_data
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import run_backtest_range as rr  # noqa: E402

HK1, HK2 = LEGACY_HORIZONS[0], LEGACY_HORIZONS[1]
TICKERS = ["AAA", "BBB", "CCC"]


def _exit(outcome, r_total=0.0, runner=None):
    return SimpleNamespace(outcome=outcome, runner_outcome=runner, r_total=r_total)


FAKE_EXITS = {
    "AAA": {HK1: [_exit("win", 2.5, "tp2"), _exit("not_triggered")], HK2: [_exit("loss", -1.0)]},
    "BBB": {HK1: [_exit("not_triggered"), _exit("not_triggered")], HK2: []},   # no rows, still done
    "CCC": {HK1: [_exit("scratch", 0.1)],
            HK2: [_exit("timeout", -0.3), _exit("win", 1.75, "runner_stop")]},
}


def _rows(ticker):
    return [{"ticker": ticker, "horizon_key": hk, "outcome": e.outcome,
             "runner_outcome": e.runner_outcome, "r_total": e.r_total}
            for hk, exits in FAKE_EXITS[ticker].items() for e in exits
            if e.outcome != "not_triggered"]


def _lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture(autouse=True)
def _fixed_run(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--scenarios", "--train",
                                      "--trades-jsonl", "out/rows.jsonl"])
    monkeypatch.setattr(rr, "_git_head", lambda: "c" * 40)
    monkeypatch.setattr(rr, "_utc_today", lambda: "2026-11-12")


def _sidecar(**over):
    kwargs = dict(date_from="2020-01-06", date_to="2023-12-29", tickers=list(TICKERS),
                  universe=None, membership=None, argv=sys.argv[1:], today=rr._utc_today())
    kwargs.update(over)
    return rr.run_sidecar(**kwargs)


def _write(target, tickers=TICKERS):
    writer = rr._checkpoint_writer(target)
    for ticker in tickers:
        writer(ticker, FAKE_EXITS[ticker], _rows(ticker))


# --- helpers (V226-4) -----------------------------------------------------------

def test_the_writer_appends_rows_then_a_done_line_per_ticker(tmp_path):
    target = tmp_path / "rows.jsonl"

    _write(target)

    assert _lines(target) == [row for ticker in TICKERS for row in _rows(ticker)]
    assert _lines(rr._done_path(target)) == [
        {"ticker": "AAA", "rows": 2, "not_triggered": {HK1: 1, HK2: 0}},
        {"ticker": "BBB", "rows": 0, "not_triggered": {HK1: 2, HK2: 0}},
        {"ticker": "CCC", "rows": 3, "not_triggered": {HK1: 0, HK2: 0}}]


def test_the_rebuilt_table_equals_the_aggregate_of_every_exit(tmp_path):
    target = tmp_path / "rows.jsonl"
    _write(target)
    by_hz = {hk: [] for hk in LEGACY_HORIZONS}
    for ticker in TICKERS:
        for hk, exits in FAKE_EXITS[ticker].items():
            by_hz[hk].extend(exits)
    every = [result for results in by_hz.values() for result in results]

    stats = rr._stats_from_checkpoint(target, list(LEGACY_HORIZONS))

    assert stats == {"pooled": bs._aggregate(every),
                     "by_horizon": {hk: bs._aggregate(rs) for hk, rs in by_hz.items()}}


def test_a_fresh_start_empties_stale_rows_and_writes_the_sidecar(tmp_path):
    target = tmp_path / "out" / "rows.jsonl"
    target.parent.mkdir()
    target.write_text('{"ticker": "OLD"}\n', encoding="utf-8")
    sidecar = _sidecar()

    assert rr._resume_checkpoint(target, sidecar) == {}
    assert target.read_text(encoding="utf-8") == ""
    assert json.loads(rr._run_sidecar_path(target).read_text(encoding="utf-8")) == sidecar


def test_a_resume_keeps_only_done_tickers_and_cuts_half_written_tails(tmp_path):
    target, full = tmp_path / "rows.jsonl", tmp_path / "full.jsonl"
    rr._resume_checkpoint(target, _sidecar())                 # fresh start writes the sidecar
    _write(target, ["AAA"])
    with target.open("a", encoding="utf-8") as handle:        # BBB's rows flushed, done line not
        handle.write(json.dumps({"ticker": "BBB", "horizon_key": HK1}) + "\n" + '{"ticker": "BB')
    with rr._done_path(target).open("a", encoding="utf-8") as handle:
        handle.write('{"ticker": "BB')

    done = rr._resume_checkpoint(target, _sidecar())

    assert list(done) == ["AAA"] and done["AAA"]["rows"] == 2
    assert _lines(target) == _rows("AAA")
    assert _lines(rr._done_path(target)) == [done["AAA"]]
    _write(target, ["BBB", "CCC"])                             # appends cleanly after the cut
    _write(full)
    assert target.read_bytes() == full.read_bytes()
    assert rr._done_path(target).read_bytes() == rr._done_path(full).read_bytes()


@pytest.mark.parametrize("change", ["window", "command", "stop_setting", "no_sidecar"])
def test_a_done_list_from_another_run_is_refused(tmp_path, monkeypatch, change):
    target = tmp_path / "rows.jsonl"
    rr._resume_checkpoint(target, _sidecar())
    _write(target, ["AAA"])
    before = (target.read_bytes(), rr._done_path(target).read_bytes())
    over = {"window": {"date_to": "2022-12-30"},
            "command": {"argv": ["--scenarios", "--validation"]}}.get(change, {})
    if change == "stop_setting":
        monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 9.9)
    if change == "no_sidecar":
        rr._run_sidecar_path(target).unlink()

    with pytest.raises(SystemExit) as exc:
        rr._resume_checkpoint(target, _sidecar(**over))

    assert exc.value.code == 2
    assert (target.read_bytes(), rr._done_path(target).read_bytes()) == before


def test_a_resume_on_another_day_ignores_membership_asof(tmp_path):
    target = tmp_path / "rows.jsonl"
    first = _sidecar()
    rr._resume_checkpoint(target, first)
    _write(target, ["AAA"])

    assert list(rr._resume_checkpoint(target, _sidecar(today="2026-11-13"))) == ["AAA"]
    assert json.loads(rr._run_sidecar_path(target).read_text(encoding="utf-8")) == first
    assert "membership_asof" not in rr.RESUME_KEYS


GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Trend up, then a 60-bar box (test_scenario_trade_rows_cli.py's fixture)."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_the_rebuilt_table_equals_the_real_replays_own_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)
    spy = make_ohlcv([300.0 + 0.1 * k for k in range(500)], start="2023-01-02")
    target = tmp_path / "rows.jsonl"

    stats = bs.run_scenario_backtest({"AAPL": _structured_df()}, None, None, gates=GATES,
                                     horizons=["4w"], workers=1, spy_df=spy, collect_rows=True,
                                     on_ticker_result=rr._checkpoint_writer(target))

    assert stats["rows"], "fixture must close at least one trade"
    assert rr._stats_from_checkpoint(target, ["4w"]) == {"pooled": stats["pooled"],
                                                          "by_horizon": stats["by_horizon"]}
    assert _lines(target) == json.loads(json.dumps(stats["rows"], default=rr._jsonable))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_checkpoint_cli.py`
Expected: FAIL — `AttributeError: <module 'run_backtest_range'> does not have the attribute '_utc_today'` (autouse fixture), then the other new names.

- [ ] **Step 3: Implement the helpers**

In `scripts/backtest/run_backtest_range.py`, add to the stdlib imports
(alphabetical order) `import os`, `from datetime import datetime, timezone`
and `from types import SimpleNamespace`, and widen the replay import:

```python
from swingbot.core.backtesting.backtest_scenarios import CONFLUENCE_GATES, _aggregate, run_scenario_backtest
```

Insert after V226-3's `write_run_sidecar`:

```python
#: v226: the sidecar fields a restart must match. membership_asof is left out:
#: for a watchlist run it is the day the run started, and a run may cross midnight.
RESUME_KEYS = tuple(key for key in RUN_SIDECAR_KEYS if key != "membership_asof")

_NOT_TRIGGERED = SimpleNamespace(outcome="not_triggered", runner_outcome=None, r_total=0.0)


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _done_path(trades_jsonl) -> Path:
    return Path(str(trades_jsonl) + ".done.jsonl")


def _jsonl_lines(path: Path) -> list[tuple[str, dict]]:
    """(raw line, parsed) per complete line; stops at a half-written tail."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append((line, json.loads(line)))
        except json.JSONDecodeError:
            break
    return out


def _read_run_sidecar(trades_jsonl) -> dict | None:
    try:
        return json.loads(_run_sidecar_path(trades_jsonl).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _same_run(old: dict | None, new: dict) -> bool:
    return old is not None and all(old.get(key) == new[key] for key in RESUME_KEYS)


def _rewrite_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _resume_checkpoint(trades_jsonl, sidecar: dict) -> dict[str, dict]:
    """{ticker: done entry} that a previous run of the SAME replay finished.
    No done-list: a fresh start (rows emptied, sidecar written). A done-list
    from another run, or without its sidecar: refused (exit 2). Otherwise the
    rows and the done-list are cut back to their complete, done lines."""
    target, done_file = Path(trades_jsonl), _done_path(trades_jsonl)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not done_file.exists():
        _rewrite_lines(target, [])
        write_run_sidecar(trades_jsonl, sidecar)
        return {}
    if not _same_run(_read_run_sidecar(trades_jsonl), sidecar):
        print(f"refused: {done_file} belongs to a different run than {_run_sidecar_path(trades_jsonl)} "
              "describes; delete the done-list to start over", file=sys.stderr)
        raise SystemExit(2)
    entries = _jsonl_lines(done_file)
    done = {entry["ticker"]: entry for _, entry in entries}
    _rewrite_lines(done_file, [line for line, _ in entries])
    _rewrite_lines(target, [line for line, row in _jsonl_lines(target) if row.get("ticker") in done])
    print(f"resuming {trades_jsonl}: {len(done)} ticker(s) already done", flush=True)
    return done


def _append_synced(path: Path, lines: list[str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("".join(line + "\n" for line in lines))
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint_writer(trades_jsonl):
    """on_ticker_result for run_scenario_backtest: the ticker's rows reach
    disk first, then its done-list line (with its per-horizon not_triggered
    counts), each flushed and fsynced."""
    target, done_file = Path(trades_jsonl), _done_path(trades_jsonl)

    def on_ticker_result(ticker: str, exits: dict, rows: list) -> None:
        _append_synced(target, [json.dumps(row, default=_jsonable) for row in rows])
        not_triggered = {hk: sum(1 for result in results if result.outcome == "not_triggered")
                         for hk, results in exits.items()}
        _append_synced(done_file, [json.dumps({"ticker": ticker, "rows": len(rows),
                                               "not_triggered": not_triggered})])

    return on_ticker_result


def _stats_from_checkpoint(trades_jsonl, horizons: list[str]) -> dict:
    """pooled/by_horizon rebuilt from the persisted rows (the closed exits, in
    the replay's per-horizon ticker order) plus the done-list's not_triggered
    counts: equal to run_scenario_backtest's own table."""
    by_hz = {hk: [] for hk in horizons}
    for _, row in _jsonl_lines(Path(trades_jsonl)):
        by_hz[row["horizon_key"]].append(SimpleNamespace(
            outcome=row["outcome"], runner_outcome=row["runner_outcome"], r_total=row["r_total"]))
    for _, entry in _jsonl_lines(_done_path(trades_jsonl)):
        for hk, count in entry["not_triggered"].items():
            by_hz[hk].extend([_NOT_TRIGGERED] * count)
    every = [result for results in by_hz.values() for result in results]
    return {"pooled": _aggregate(every),
            "by_horizon": {hk: _aggregate(results) for hk, results in by_hz.items()}}
```

Nothing calls these yet; V226-4b wires them in.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_checkpoint_cli.py`
Expected: 10 passed (the refusal test is parametrised four ways).

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_run_sidecar.py`
Expected: all pass.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new helper below 15).

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/run_backtest_range.py tests/backtesting/test_scenario_checkpoint_cli.py
git commit -m "feat(v226): checkpoint helpers -- done-list, resume, per-ticker writer, rebuilt table (V226-4)"
```

### Task V226-4b: Wire checkpointing into `--trades-jsonl`; a restart equals an uninterrupted run

**Model:** opus — restart parity across a cross-sectional as-of map; building it on the remaining tickers would silently change `rs_pctile` for every ticker replayed after a restart.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (`_scenario_stats` :265 delegates; new `_checkpointed_stats` after V226-4's `_stats_from_checkpoint`)
- Modify: `tests/backtesting/test_scenario_trade_rows_cli.py` (`_stub_scenario_mode` fires `on_ticker_result`; one assertion updated)
- Modify: `tests/backtesting/test_scenario_checkpoint_cli.py` (append the CLI restart tests)

**Interfaces:**
- Consumes: V226-2 `run_scenario_backtest(..., on_ticker_result=None)`; V226-3 `run_sidecar(...)`; V226-4 `_resume_checkpoint`, `_checkpoint_writer`, `_stats_from_checkpoint`, `_done_path`, `_utc_today`, `_jsonl_lines`; existing `_build_asof_map(tickers, frames, universe)`, `_market_frame()`, `_scenario_progress(trades_jsonl)`, `_progress_path(trades_jsonl)`.
- Produces (ledger contract, final): `_checkpointed_stats(frames, date_from, date_to, *, scale_out, universe, membership, trades_jsonl) -> dict` (`{"pooled", "by_horizon"}`); `_scenario_stats` with `trades_jsonl` returns it. V226-12 runs the script through this path.

Why: V226-4 built the pieces; this task routes `--trades-jsonl` through them.
Order inside `_checkpointed_stats`: the sidecar for this run → resume (or
fresh start) → **the as-of map on the full frame set** (cross-sectional:
`rs_pctile` ranks across tickers) → replay only the tickers not yet done,
each written by the checkpoint writer → the table rebuilt from disk → the
progress file removed. Without `--trades-jsonl` the replay call passes the
same values as before (no SPY, no rows, no progress, `record_blocked`
honoured); `_check_record_blocked` already refuses `--record-blocked` with
`--trades-jsonl`. `run_scenario_mode` (C 19) and `main` (F 62) are not edited.

- [ ] **Step 1: Update the existing CLI stub**

In `tests/backtesting/test_scenario_trade_rows_cli.py`, add above
`_stub_scenario_mode`:

```python
def _row(ticker):
    """A minimal checkpointed row: the fields the rebuilt table reads."""
    return {"ticker": ticker, "horizon_key": LEGACY_HORIZONS[0], "outcome": "win",
            "runner_outcome": None, "r_total": 1.0}
```

Replace `fake_backtest` inside `_stub_scenario_mode` with:

```python
    def fake_backtest(frames, start, end, **kwargs):
        seen.update(kwargs, frames=frames)
        if kwargs["on_ticker_done"] is not None:
            kwargs["on_ticker_done"](1, 2)
            seen["progress_text"] = (tmp_path / "out" / "rows.jsonl.progress").read_text(encoding="utf-8")
        if kwargs.get("on_ticker_result") is not None:      # v226: rows reach disk per ticker
            for ticker in frames:
                kwargs["on_ticker_result"](ticker, {}, [_row(ticker)])
        empty = bs._aggregate([])
        stats = {"pooled": empty, "by_horizon": {hk: empty for hk in LEGACY_HORIZONS}}
        if kwargs["collect_rows"]:
            stats["rows"] = [_row(ticker) for ticker in frames]
        return stats
```

In `test_scenario_mode_writes_rows_and_clears_the_progress_file`, replace the
rows assertion with:

```python
    assert [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()] == [
        _row("AAA"), _row("BBB")]
    assert seen["on_ticker_result"] is not None
```

- [ ] **Step 2: Append the restart tests**

Append to `tests/backtesting/test_scenario_checkpoint_cli.py` (it already
defines `TICKERS`, `FAKE_EXITS`, `_rows`, `_lines`, `HK1`, `HK2` and the
autouse `_legacy_source` / `_fixed_run` fixtures):

```python
# --- run_scenario_mode --trades-jsonl (V226-4b) ----------------------------------

def _stub(monkeypatch, seen, interrupt_after=None):
    """run_scenario_mode with the loaders faked and a replay that fires the
    hook per ticker; Ctrl-C after `interrupt_after` is already on disk."""
    monkeypatch.setattr(rr, "_tickers_for_run", lambda universe, tickers_file=None: list(TICKERS))
    monkeypatch.setattr(rr, "_membership_for_run", lambda universe, tickers: None)
    monkeypatch.setattr(rr, "load_cached", lambda ticker: f"frame-{ticker}")
    monkeypatch.setattr(rr, "_with_context", lambda df, **kw: df)
    monkeypatch.setattr(rr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rr, "_market_frame", lambda: "SPY")

    def fake_asof(tickers, frames, universe):
        seen.setdefault("asof_tickers", []).append(list(tickers))
        return {ticker: f"asof-{ticker}" for ticker in tickers}

    def fake_backtest(frames, start, end, **kwargs):
        seen.setdefault("replayed", []).append(list(frames))
        seen["asof_map"] = kwargs["asof_map"]
        for done, ticker in enumerate(frames, 1):
            kwargs["on_ticker_result"](ticker, FAKE_EXITS[ticker], _rows(ticker))
            kwargs["on_ticker_done"](done, len(frames))
            if ticker == interrupt_after:
                raise KeyboardInterrupt
        return {"pooled": None, "by_horizon": None, "rows": []}   # ignored by the checkpoint path

    monkeypatch.setattr(rr, "_build_asof_map", fake_asof)
    monkeypatch.setattr(rr, "run_scenario_backtest", fake_backtest)


def _run(directory, monkeypatch, date_to="2023-12-29"):
    directory.mkdir(exist_ok=True)
    monkeypatch.chdir(directory)                # backtest_range_summary.txt lands in cwd
    target = directory / "out" / "rows.jsonl"
    rr.run_scenario_mode("2020-01-06", date_to, 30, "TRAIN", scale_out=True,
                         trades_jsonl=str(target))
    return target


def _interrupted(directory, monkeypatch, seen, after="AAA"):
    _stub(monkeypatch, seen, interrupt_after=after)
    with pytest.raises(KeyboardInterrupt):
        _run(directory, monkeypatch)
    return directory / "out" / "rows.jsonl"


def _files(target):
    """Rows, done-list, run sidecar and the printed table, as bytes."""
    summary = target.parent.parent / "backtest_range_summary.txt"
    return [path.read_bytes() for path in
            (target, rr._done_path(target), rr._run_sidecar_path(target), summary)]


def _full_run(tmp_path, monkeypatch):
    _stub(monkeypatch, {})
    return _run(tmp_path / "full", monkeypatch)


def test_an_uninterrupted_run_writes_rows_done_list_sidecar_and_table(tmp_path, monkeypatch):
    target = _full_run(tmp_path, monkeypatch)

    assert _lines(target) == [row for ticker in TICKERS for row in _rows(ticker)]
    assert [entry["ticker"] for entry in _lines(rr._done_path(target))] == TICKERS
    sidecar = json.loads(rr._run_sidecar_path(target).read_text(encoding="utf-8"))
    assert tuple(sorted(sidecar)) == tuple(sorted(rr.RUN_SIDECAR_KEYS))
    assert sidecar["watchlist"]["tickers"] == TICKERS and sidecar["git_head"] == "c" * 40
    assert not rr._progress_path(target).exists()
    summary = (tmp_path / "full" / "backtest_range_summary.txt").read_text(encoding="utf-8")
    pooled = rr._scenario_row_stats(rr._stats_from_checkpoint(target, list(LEGACY_HORIZONS))["pooled"])
    assert f"{'confluence/pooled':22s} {pooled['n_eval']:5d}" in summary


def test_a_restart_skips_finished_tickers_and_equals_an_uninterrupted_run(tmp_path, monkeypatch):
    full = _files(_full_run(tmp_path, monkeypatch))
    seen = {}
    target = _interrupted(tmp_path / "part", monkeypatch, seen)
    assert [entry["ticker"] for entry in _lines(rr._done_path(target))] == ["AAA"]

    _stub(monkeypatch, seen)
    _run(tmp_path / "part", monkeypatch)

    assert seen["replayed"] == [TICKERS, ["BBB", "CCC"]]
    assert seen["asof_tickers"] == [TICKERS, TICKERS]          # full set on the restart too
    assert set(seen["asof_map"]) == set(TICKERS)
    assert _files(target) == full


def test_a_restart_after_every_ticker_finished_replays_nothing(tmp_path, monkeypatch):
    full = _files(_full_run(tmp_path, monkeypatch))
    seen = {}
    target = _interrupted(tmp_path / "part", monkeypatch, seen, after="CCC")

    _stub(monkeypatch, seen)
    _run(tmp_path / "part", monkeypatch)

    assert seen["replayed"][-1] == []
    assert _files(target) == full


def test_a_restart_with_another_window_is_refused_before_any_replay(tmp_path, monkeypatch):
    seen = {}
    target = _interrupted(tmp_path / "part", monkeypatch, seen)
    rows_before = target.read_bytes()

    _stub(monkeypatch, seen)
    with pytest.raises(SystemExit) as exc:
        _run(tmp_path / "part", monkeypatch, date_to="2022-12-30")

    assert exc.value.code == 2
    assert target.read_bytes() == rows_before
    assert len(seen["replayed"]) == 1 and len(seen["asof_tickers"]) == 1
```

`_scenario_row_stats` exists in `run_backtest_range.py` (used by
`run_scenario_mode` to print each table line); the summary assertion matches
the pooled line's label and N column exactly as `run_scenario_mode` formats
it (`f"{'confluence/pooled':22s} {n:5d}"`, the label padded to 22).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_checkpoint_cli.py`
Expected: the four new tests FAIL (`KeyError: 'on_ticker_result'` from the stub: `_scenario_stats` still runs the in-memory path); V226-4's ten tests still pass.

- [ ] **Step 4: Implement `_checkpointed_stats` and the delegation**

In `scripts/backtest/run_backtest_range.py`, insert after `_stats_from_checkpoint`:

```python
def _checkpointed_stats(frames, date_from, date_to, *, scale_out, universe, membership,
                        trades_jsonl) -> dict:
    """v226: the --trades-jsonl replay, one ticker at a time onto disk. The
    as-of map is built on the FULL frame set even on a restart: it is
    cross-sectional (rs_pctile ranks across tickers)."""
    sidecar = run_sidecar(date_from=date_from, date_to=date_to, tickers=list(frames),
                          universe=universe, membership=membership, argv=sys.argv[1:],
                          today=_utc_today())
    done = _resume_checkpoint(trades_jsonl, sidecar)
    asof_map = _build_asof_map(list(frames), frames, universe)
    remaining = {ticker: df for ticker, df in frames.items() if ticker not in done}
    run_scenario_backtest(
        remaining, date_from, date_to, gates=CONFLUENCE_GATES, scale_out=scale_out,
        horizons=list(LEGACY_HORIZONS), membership=membership, asof_map=asof_map,
        spy_df=_market_frame(), collect_rows=True,
        on_ticker_done=_scenario_progress(trades_jsonl),
        on_ticker_result=_checkpoint_writer(trades_jsonl))
    stats = _stats_from_checkpoint(trades_jsonl, list(LEGACY_HORIZONS))
    _progress_path(trades_jsonl).unlink(missing_ok=True)
    print(f"Wrote {len(_jsonl_lines(Path(trades_jsonl)))} trade rows to {trades_jsonl}", flush=True)
    return stats
```

Replace `_scenario_stats` (:265-286) with:

```python
def _scenario_stats(frames, date_from, date_to, *, scale_out, universe, membership, trades_jsonl,
                    record_blocked=None) -> dict:
    """run_scenario_mode's replay call. v146 I3: every scenario run builds
    the as-of map, so entry_context carries rs_pctile / regime2_state (it
    feeds stamp_entry_context only -- the table cannot move). v226: with
    --trades-jsonl the replay is checkpointed per ticker (_checkpointed_stats).
    v147's --record-blocked rides the plain call (gate rows written by
    _write_blocked); it is refused together with --trades-jsonl."""
    if trades_jsonl:
        return _checkpointed_stats(frames, date_from, date_to, scale_out=scale_out,
                                   universe=universe, membership=membership,
                                   trades_jsonl=trades_jsonl)
    stats = run_scenario_backtest(
        frames, date_from, date_to, gates=CONFLUENCE_GATES, scale_out=scale_out,
        horizons=list(LEGACY_HORIZONS), membership=membership,
        asof_map=_build_asof_map(list(frames), frames, universe),
        spy_df=None, collect_rows=False, on_ticker_done=None,
        record_blocked=bool(record_blocked))
    _write_blocked(stats, record_blocked)
    return stats
```

The plain branch passes the same values as before: with `trades_jsonl`
falsy, `_market_frame() if trades_jsonl else None` was None,
`bool(trades_jsonl)` was False and `_scenario_progress(None)` was None.
`write_scenario_trades_jsonl` stays (its round-trip test still covers it).
`run_scenario_mode` still calls `_write_provenance(trades_jsonl)` after the
replay, so `<path>.provenance.json` is written exactly as before.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_checkpoint_cli.py`
Expected: 14 passed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_scenario_trade_rows_cli.py`
Expected: all pass (the updated stub test and `test_scenario_mode_without_the_flag_collects_nothing` included).

Run: `python scripts/dev/testrun.py file tests/backtesting/test_replay_provenance.py`
Expected: all pass.

- [ ] **Step 6: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `run_scenario_mode` (19) and `main` (62) unchanged, `_scenario_stats` and `_checkpointed_stats` below 15.

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git add scripts/backtest/run_backtest_range.py tests/backtesting/test_scenario_trade_rows_cli.py
git commit -m "feat(v226): --trades-jsonl replays per ticker onto disk and skips finished tickers on restart (V226-4b)"
git add tests/backtesting/test_scenario_checkpoint_cli.py
git commit -m "test(v226): restart equals an uninterrupted run; as-of map sees every ticker (V226-4b)"
```

