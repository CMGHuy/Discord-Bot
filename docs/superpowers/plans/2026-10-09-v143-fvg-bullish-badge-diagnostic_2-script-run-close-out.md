# v143 FVG (bullish) badge diagnostic: Implementation Plan, part 2 — script, the one replay, close-out, full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Frozen readings, Review Focus and Parallelisation live in [`_0-index`](2026-10-09-v143-fvg-bullish-badge-diagnostic_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`](../specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md)

# Phase 2 — Driver, the one replay, close-out, full suite

**Sequential throughout:** the replay needs the finished script, the close-out copies numbers out of the replay's document, and the full suite runs over all of it.

**What the replay may and may not do once it starts:**
- A crash or traceback **before** `logs/v143-fvg-bullish-rows.json` exists recorded nothing. Fix the cause with a failing test first (a normal TDD fix on this branch, committed), then dispatch the same run again. Never change a threshold, a favourable side, the tolerance, a geometry, the window or `EXPECTED_N` to make it run.
- Once the rows file exists the replay is spent. A crash after that point is a render bug: fix it with a failing test, then re-render with `--from-rows logs/v143-fvg-bullish-rows.json`. The script refuses a second replay while the rows file exists; do not delete the file to get around that.
- `refused:population` means the engine moved since 2026-10-09. Stop and take it to the partner (`AskUserQuestion`). The diagnostic has no result until that is understood.
- Once the results document is committed, its numbers are never edited and the replay is never re-run.

### Task V143-5: Driver script, its tests, and a two-ticker smoke run

**Files:**
- Create: `scripts/backtest/measure_fvg_bullish_diagnostic.py`
- Test: `tests/scripts/test_measure_fvg_bullish_diagnostic.py`

**Interfaces:**
- Consumes: from `fvg_diagnostic` (part 1): `STRATEGY`, `TRAIN`, `UNTRIGGERED`, `EXPECTED_N`, `YEARS`, `earnings_distance(signal_pos, reaction_positions)`, `target_confluence_count(df, i, horizon_key, target, tolerance_pct)`, `SignalContext`, `trade_row(df, i, plan, ctx)`, `population_ok(n)`, `build_report(rows)` (its `coverage` key), `render(report, *, run_date, tickers, tolerance_pct)`. Existing: `backtest_scenarios.replay_scenarios(ticker, df, horizon_key) -> [(signal_index, TradePlanV2)]`, which calls the module attributes `backtest_scenarios.levels_asof(ticker, df, bar_index, horizon_key, cache)` (it adds one entry to `cache` when it builds a map) and `backtest_scenarios.build_confluence_plan(scenario, window, **kwargs)` (the scenario is a `levels.Scenario` and carries `take_profit`, `target_sources`, `stop_loss`, `stop_sources`), `backtest_scenarios._resolve_replay_workers(workers) -> int`, `ScanParams.from_config().confluence_deviation_pct`, `exit_sim.simulate_exit`, `acceptance_levels.enabled_arms()`, `strategy_types.LEGACY_HORIZONS`, `earnings_calendar.EARNINGS_CSV_DIR` / `CsvSource(directory)`, `session.SessionCalendar.position_on_or_before(date) -> int | None`, `universe.is_etf(symbol)`, `backtest_cache.CACHE_DIR`; from `scripts/backtest/`: `measure_arms.load_frame(ticker)`, `measure_acceptance_exits.cache_universe() -> list[str]`, `measure_earnings_blackout.load_calendar(cache_dir)` and `reaction_positions(ticker, source, calendar)`. Test helper `row` from `tests/backtesting/fvg_diagnostic_rows.py` (V143-3).
- Produces: the CLI V143-6 runs. Flags: `--date` (default today), `--out-dir` (default `docs/superpowers/results`), `--earnings-dir`, `--tickers N` (smoke; refuses the results directory), `--workers N`, `--from-rows PATH`. Exit 0 = document written; exit 2 = a `refused:` line on stderr. Last three stdout lines: `population: ...`, `coverage: unidentified=<u> of <n>; role target=<t> stop=<s>; gap open=<o> filled=<f>; computable: <feature share>, ...` (a feature under the floor is tagged `NOT TESTED`), and `v143: <k> candidate(s) of 27 looks, N=<n>, unidentified=<u> -> <document path>`. Rows file: `logs/v143-fvg-bullish-rows.json` (`{"rows", "other_triggered", "tickers", "confluence_tolerance_pct"}`). Also `replay_with_scenarios(ticker, frame, horizon_key, **replay_kwargs) -> [(signal_index, plan, scenario, map_bar)]` and `signal_context(frame, i, plan, (scenario, map_bar), ticker_context) -> fd.SignalContext`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_measure_fvg_bullish_diagnostic.py`:

```python
"""v143 driver: refusals, the per-ticker collector, the population gate and
the render-from-rows path. No real replay runs here."""
import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_fvg_bullish_diagnostic as mf  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting import fvg_diagnostic as fd  # noqa: E402
from swingbot.core.market.session import SessionCalendar  # noqa: E402
from swingbot.core.market.strategy_types import MIN_BARS  # noqa: E402
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df  # noqa: E402
from tests.backtesting.fvg_diagnostic_rows import row  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402
from tests.planning.test_exit_sim_single import _plan  # noqa: E402

SCRIPT = ROOT / "scripts" / "backtest" / "measure_fvg_bullish_diagnostic.py"


class Scenario:
    """The four levels.Scenario attributes the driver reads."""
    take_profit = 123.0
    target_sources = ["FVG (bullish)", "EMA 50"]
    stop_loss = 95.0
    stop_sources = ["Swing Low"]


SCENARIO = Scenario()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Scratch out-dir, an earnings dir with one CSV, logs under tmp."""
    earnings = tmp_path / "earnings"
    earnings.mkdir()
    (earnings / "AAA.csv").write_text("report_date,timing,report_ts_et\n", encoding="utf-8")
    monkeypatch.setattr(mf, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(mf, "PROGRESS", tmp_path / "logs" / "p.progress")
    monkeypatch.setattr(mf, "enabled_arms", lambda: ())
    out = tmp_path / "out"
    return {"out": out, "earnings": earnings,
            "argv": ["--date", "2026-10-10", "--out-dir", str(out),
                     "--earnings-dir", str(earnings)]}


def test_the_script_has_a_main_guard():
    """Windows spawns pool workers by re-importing the script; without the
    guard every worker would start its own replay."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    guards = [node for node in tree.body if isinstance(node, ast.If)
              and "__main__" in ast.unparse(node.test)]
    assert len(guards) == 1


def test_ticker_rows_keeps_fvg_bullish_plans_inside_train(monkeypatch):
    bars = [100.0, 100.0, (100.0, 111.0, 99.5, 110.5), 110.0]
    frame = make_ohlcv(bars, start="2021-03-01")           # signal bar 1 = 2021-03-02
    fvg_plan = _plan(strategy=fd.STRATEGY, source="confluence")
    other = _plan(strategy="Fib 38.2%", source="confluence")
    unfilled = _plan(strategy=fd.STRATEGY, source="confluence", entry_type="stop_entry",
                     trigger_price=500.0)
    monkeypatch.setattr(mf, "replay_with_scenarios", lambda ticker, f, hk: [
        (1, fvg_plan, SCENARIO, 0), (1, other, SCENARIO, 0), (1, unfilled, SCENARIO, 0)])
    seen = []
    monkeypatch.setattr(fd, "target_confluence_count",
                        lambda df, i, hk, target, tol: seen.append((i, hk, target, tol)) or 3)
    calendar = SessionCalendar.from_bar_index(frame.index)
    rows, others = mf.ticker_rows("AAA", frame, [0, 3], calendar, 2.0, horizons=("2w",))
    assert seen[0] == (1, "2w", 123.0, 2.0)                 # the SCENARIO target, live tolerance
    assert isinstance(rows[0]["features"]["quality"], int)  # scored, not the replay's 0
    assert len(rows) == 1 and others == 1                   # the unfilled plan is no trade
    assert rows[0]["signal_date"] == "2021-03-02"
    assert rows[0]["features"]["earnings_distance"] == 2    # reaction at session 3
    assert rows[0]["outcomes"]["live"]["outcome"] == "win"
    late = make_ohlcv(bars, start="2024-01-02")             # VALIDATION dates: never kept
    assert mf.ticker_rows("AAA", late, [], SessionCalendar.from_bar_index(late.index), 2.0,
                          horizons=("2w",)) == ([], 0)


def test_signal_context_carries_the_scenario_levels_and_sources(monkeypatch):
    frame = make_ohlcv([100.0, 100.0, 100.0, 100.0], start="2021-03-01")
    monkeypatch.setattr(fd, "target_confluence_count", lambda *a: 4)
    calendar = SessionCalendar.from_bar_index(frame.index)
    context = mf.signal_context(frame, 1, _plan(), (SCENARIO, 0), ([0, 3], calendar, 5.0))
    assert context == fd.SignalContext(
        target=123.0, target_sources=("FVG (bullish)", "EMA 50"), stop=95.0,
        stop_sources=("Swing Low",), tolerance_pct=5.0, map_bar=0, earnings_distance=2,
        confluence_count=4)


def test_replay_with_scenarios_restores_both_wrapped_functions(monkeypatch):
    built = _plan(strategy=fd.STRATEGY, source="confluence")

    def builder(scenario, window, **kwargs):
        return built

    def fake_asof(ticker, df, bar_index, horizon_key, cache):
        cache.setdefault(bar_index // 5, bar_index)
        return [], []

    def fake_replay(ticker, frame, hk):
        cache: dict = {}
        for bar in (12, 13, 14, 15, 16):             # maps are built at 12 and at 15
            bs.levels_asof(ticker, frame, bar, hk, cache)
        return [(16, bs.build_confluence_plan(SCENARIO, frame, ticker=ticker))]

    monkeypatch.setattr(bs, "build_confluence_plan", builder)
    monkeypatch.setattr(bs, "levels_asof", fake_asof)
    monkeypatch.setattr(bs, "replay_scenarios", fake_replay)
    assert mf.replay_with_scenarios("AAA", None, "2w") == [(16, built, SCENARIO, 15)]
    assert bs.build_confluence_plan is builder and bs.levels_asof is fake_asof

    def boom(ticker, frame, hk):
        raise RuntimeError("replay died")

    monkeypatch.setattr(bs, "replay_scenarios", boom)
    with pytest.raises(RuntimeError):
        mf.replay_with_scenarios("AAA", None, "2w")
    assert bs.build_confluence_plan is builder and bs.levels_asof is fake_asof


def test_the_map_bar_is_the_bar_the_real_replay_built_its_level_map_on(monkeypatch):
    """Pinned against replay_scenarios itself. Its loop asks levels_asof for
    every bar from MIN_BARS on, and the cache is keyed by bar // 5, so a map
    is built on the warm-up bar and then on every multiple of 5. A spy on
    levels.build_level_map confirms a map really was built on each map_bar."""
    built_on = set()
    real = bs.levels.build_level_map

    def spying(window, h, price, *args, **kwargs):
        built_on.add(len(window) - 1)
        return real(window, h, price, *args, **kwargs)

    monkeypatch.setattr(bs.levels, "build_level_map", spying)
    out = mf.replay_with_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    refresh = bs.LEVEL_REFRESH_BARS
    for i, plan, scenario, map_bar in out:
        assert map_bar == max(MIN_BARS["4w"], refresh * (i // refresh))
        assert map_bar <= i and map_bar in built_on
        assert scenario.direction == plan.direction
    assert {i - map_bar for i, _plan_, _scenario, map_bar in out} - {0}, "no stale map exercised"


def test_smoke_run_refuses_the_results_directory(env, capsys):
    assert mf.main(["--tickers", "2", "--earnings-dir", str(env["earnings"])]) == 2
    assert "refused:smoke-run" in capsys.readouterr().err


def test_refuses_without_earnings_csvs(env, tmp_path, capsys):
    empty = tmp_path / "none"
    empty.mkdir()
    assert mf.main(["--date", "2026-10-10", "--out-dir", str(env["out"]),
                    "--earnings-dir", str(empty)]) == 2
    assert "refused:no-earnings" in capsys.readouterr().err


def test_refuses_when_an_acceptance_arm_is_enabled(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "enabled_arms", lambda: ("Z",))
    assert mf.main(env["argv"]) == 2
    assert "refused:acceptance-exit-enabled" in capsys.readouterr().err


def test_a_population_off_by_more_than_two_percent_writes_no_document(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "run_replay", lambda universe, earnings_dir, workers=None: {
        "rows": [row()] * 3, "other_triggered": 5, "tickers": 1,
        "confluence_tolerance_pct": 2.0})
    monkeypatch.setattr("measure_acceptance_exits.cache_universe", lambda: ["AAA"])
    assert mf.main(env["argv"]) == 2
    captured = capsys.readouterr()
    assert "population: N=3 FVG (bullish) of 8 triggered confluence plans" in captured.out
    assert "refused:population" in captured.err
    assert not mf.doc_path(env["out"], "2026-10-10").exists()
    assert json.loads(mf.rows_path(env["out"]).read_text(encoding="utf-8"))["tickers"] == 1


def test_the_replay_never_runs_twice(env, monkeypatch, capsys):
    env["out"].mkdir()
    mf.rows_path(env["out"]).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mf, "run_replay", lambda *a, **k: pytest.fail("replayed twice"))
    assert mf.main(env["argv"]) == 2
    assert "refused:already-run" in capsys.readouterr().err


def test_from_rows_renders_without_replaying(env, monkeypatch, tmp_path, capsys):
    saved = tmp_path / "rows.json"
    rows = [row(year) for year in fd.YEARS for _ in range(320)]       # 1280: inside 2%
    saved.write_text(json.dumps({"rows": rows, "other_triggered": 6800, "tickers": 75,
                                 "confluence_tolerance_pct": 2.0}), encoding="utf-8")
    monkeypatch.setattr(mf, "run_replay", lambda *a, **k: pytest.fail("replayed"))
    assert mf.main(env["argv"] + ["--from-rows", str(saved)]) == 0
    doc = mf.doc_path(env["out"], "2026-10-10")
    text = doc.read_text(encoding="utf-8")
    assert "**Population N = 1280** (expected 1278)" in text
    assert "within 2% of the scenario target" in text
    out = capsys.readouterr().out
    assert f"-> {doc}" in out and "27 looks" in out
    assert ("coverage: unidentified=0 of 1280; role target=1280 stop=0; "
            "gap open=1280 filled=0; computable: gap_age 100.0%") in out
    assert mf.main(env["argv"] + ["--from-rows", str(saved)]) == 2     # the doc now exists
    assert "refused:already-written" in capsys.readouterr().err


def test_run_replay_is_ticker_ordered_and_clears_its_progress_file(env, monkeypatch, capsys):
    monkeypatch.setattr(mf, "_worker", lambda task: (task[0], [{"t": task[0]}], 2))
    blob = mf.run_replay(["BBB", "AAA"], env["earnings"], workers=1)
    tolerance = blob.pop("confluence_tolerance_pct")
    assert tolerance == float(mf.ScanParams.from_config().confluence_deviation_pct)
    assert blob == {"rows": [{"t": "AAA"}, {"t": "BBB"}], "other_triggered": 4, "tickers": 2}
    assert not mf.PROGRESS.exists()
    assert "1/2 BBB: 1 FVG (bullish) trades, 2 other" in capsys.readouterr().out


def test_rows_file_never_lands_in_the_results_directory(tmp_path):
    assert mf.rows_path(mf.RESULTS) == mf.LOG_DIR / mf.ROWS_NAME
    assert mf.rows_path(tmp_path) == tmp_path / mf.ROWS_NAME
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/scripts/test_measure_fvg_bullish_diagnostic.py -q -x`
Expected: a collection error, `ModuleNotFoundError: No module named 'measure_fvg_bullish_diagnostic'`.

- [ ] **Step 3: Write the script**

Create `scripts/backtest/measure_fvg_bullish_diagnostic.py`:

```python
#!/usr/bin/env python3
"""v143 FVG (bullish) badge diagnostic: the one TRAIN replay and its tables.

Read-only. Replays the baseline confluence book on TRAIN 2020-01-01..2023-12-31
(signal date) over every cached ticker and all ten LEGACY_HORIZONS, keeps the
plans whose primary strategy is "FVG (bullish)" and whose exit triggers, and
writes one results document. VALIDATION is never read; nothing live changes.
All arithmetic lives in swingbot/core/backtesting/fvg_diagnostic.py.

replay_scenarios is not changed. Gap matching and the replay quality score
need each plan's SCENARIO (its clustered target and stop levels and their
sources; plan.tp1 is re-selected structurally and may differ), which
replay_scenarios does not return, and the bar its cached level map was built
on (levels_asof reuses one map for up to LEVEL_REFRESH_BARS bars). So
`replay_with_scenarios` wraps backtest_scenarios.build_confluence_plan and
backtest_scenarios.levels_asof for the one call and records both -- the
acceptance_replay._break_retest_plans pattern.

The replay runs ONCE (about 70 minutes at 6 workers). Its rows are saved to
logs/v143-fvg-bullish-rows.json before anything is rendered, so a crash while
rendering is repaired with --from-rows, never with a second replay.

PROGRESS: a flushed line per ticker, plus
logs/measure_fvg_bullish_diagnostic.progress (percent, rewritten per ticker,
deleted on completion).

Run: python scripts/backtest/measure_fvg_bullish_diagnostic.py --date 2026-10-10 --earnings-dir <dir>
Smoke: ... --tickers 2 --out-dir <scratch dir>   (never the results directory)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting import fvg_diagnostic as fd  # noqa: E402
from swingbot.core.market.earnings_calendar import EARNINGS_CSV_DIR, CsvSource  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402
from swingbot.core.planning.acceptance_levels import enabled_arms  # noqa: E402
from swingbot.core.planning.exit_sim import simulate_exit  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results"
LOG_DIR = ROOT / "logs"
PROGRESS = LOG_DIR / "measure_fvg_bullish_diagnostic.progress"
ROWS_NAME = "v143-fvg-bullish-rows.json"
DOC_SUFFIX = "v143-fvg-bullish-diagnostic.md"
#: Triggered confluence plans of every primary on TRAIN (spec § Why). Printed
#: beside the measured figure as a disclosure; only EXPECTED_N gates.
EXPECTED_ALL = 8089


# --- replay ------------------------------------------------------------------

def replay_with_scenarios(ticker, frame, horizon_key, **replay_kwargs) -> list:
    """(signal_index, plan, scenario, map_bar) for every plan replay_scenarios
    emits. `map_bar` is the bar the level map behind the plan was built on:
    the last bar whose levels_asof call ADDED a map to the replay's cache, so
    it follows the real cache whatever the warm-up or bucket alignment. Both
    are captured by wrapping the two module attributes for this one call; the
    replay itself runs unchanged."""
    captured: dict = {}
    state = {"map_bar": None}
    build, asof = bs.build_confluence_plan, bs.levels_asof

    def recording_asof(ticker_, df, bar_index, horizon_key_, cache):
        before = len(cache)
        result = asof(ticker_, df, bar_index, horizon_key_, cache)
        if len(cache) > before:
            state["map_bar"] = bar_index
        return result

    def recording_build(scenario, window, **kwargs):
        plan = build(scenario, window, **kwargs)
        if plan is not None:
            captured[id(plan)] = (scenario, state["map_bar"])
        return plan

    bs.build_confluence_plan, bs.levels_asof = recording_build, recording_asof
    try:
        plans = bs.replay_scenarios(ticker, frame, horizon_key, **replay_kwargs)
    finally:
        bs.build_confluence_plan, bs.levels_asof = build, asof
    return [(i, plan, *captured[id(plan)]) for i, plan in plans]


def signal_context(frame, i, plan, captured, ticker_context) -> fd.SignalContext:
    """The scenario's levels and sources, the map bar, and this trade's two
    readings. `captured` is (scenario, map_bar)."""
    scenario, map_bar = captured
    positions, calendar, tolerance_pct = ticker_context
    signal = frame.index[i].date()
    return fd.SignalContext(
        target=scenario.take_profit, target_sources=tuple(scenario.target_sources or ()),
        stop=scenario.stop_loss, stop_sources=tuple(scenario.stop_sources or ()),
        tolerance_pct=tolerance_pct, map_bar=map_bar,
        earnings_distance=fd.earnings_distance(
            calendar.position_on_or_before(signal), positions),
        confluence_count=fd.target_confluence_count(
            frame, i, plan.horizon_key, scenario.take_profit, tolerance_pct))


def ticker_rows(ticker, frame, positions, calendar, tolerance_pct,
                horizons=LEGACY_HORIZONS) -> tuple:
    """(FVG (bullish) trade rows, count of other triggered plans) for one
    ticker, signal dates inside TRAIN. The exit walk may run past the window,
    the run_backtest_range convention."""
    rows, others = [], 0
    context = (positions, calendar, tolerance_pct)
    for horizon_key in horizons:
        for i, plan, *captured in replay_with_scenarios(ticker, frame, horizon_key):
            if not fd.TRAIN[0] <= str(frame.index[i].date()) <= fd.TRAIN[1]:
                continue
            if plan.strategy != fd.STRATEGY:
                result = simulate_exit(frame, i, plan, scale_out=True)
                others += result.outcome not in fd.UNTRIGGERED
                continue
            row = fd.trade_row(frame, i, plan,
                               signal_context(frame, i, plan, captured, context))
            if row is not None:
                rows.append(row)
    return rows, others


def _worker(task) -> tuple:
    """One ticker, every horizon -- the process-pool entry point."""
    ticker, earnings_dir, tolerance_pct = task
    from measure_arms import load_frame
    from measure_earnings_blackout import load_calendar, reaction_positions
    from swingbot.core.marketdata import backtest_cache
    from swingbot.core.marketdata.universe import is_etf
    frame = load_frame(ticker)
    if frame is None:
        return ticker, [], 0
    calendar = load_calendar(backtest_cache.CACHE_DIR)
    positions = [] if is_etf(ticker) else reaction_positions(
        ticker, CsvSource(earnings_dir), calendar)
    rows, others = ticker_rows(ticker, frame, positions, calendar, tolerance_pct)
    return ticker, rows, others


def _write_progress(done, total) -> None:
    try:
        PROGRESS.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                            encoding="utf-8")
    except OSError:
        pass


def run_replay(universe, earnings_dir, workers=None) -> dict:
    """Replay `universe` and return {"rows", "other_triggered", "tickers",
    "confluence_tolerance_pct"}, rows in ticker order so the output is
    identical whatever order the pool finishes in."""
    tolerance_pct = float(ScanParams.from_config().confluence_deviation_pct)
    tasks = [(ticker, str(earnings_dir), tolerance_pct) for ticker in universe]
    LOG_DIR.mkdir(exist_ok=True)
    by_ticker: dict = {}

    def record(ticker, rows, others):
        by_ticker[ticker] = (rows, others)
        print(f"  [v143 {fd.TRAIN[0]}..{fd.TRAIN[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(rows)} FVG (bullish) trades, {others} other", flush=True)
        _write_progress(len(by_ticker), len(tasks))

    n_workers = bs._resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    PROGRESS.unlink(missing_ok=True)
    ordered = sorted(by_ticker)
    return {"rows": [row for ticker in ordered for row in by_ticker[ticker][0]],
            "other_triggered": sum(by_ticker[ticker][1] for ticker in ordered),
            "tickers": len(ordered), "confluence_tolerance_pct": tolerance_pct}


# --- CLI ---------------------------------------------------------------------

def rows_path(out_dir) -> Path:
    """The committed results directory never holds the rows file: a full run
    keeps it under logs/ (gitignored), a smoke run beside its scratch doc."""
    out_dir = Path(out_dir)
    return LOG_DIR / ROWS_NAME if out_dir.resolve() == RESULTS.resolve() else out_dir / ROWS_NAME


def doc_path(out_dir, run_date) -> Path:
    return Path(out_dir) / f"{run_date}-{DOC_SUFFIX}"


def _replay_refusal(args) -> str | None:
    if enabled_arms():
        return ("refused:acceptance-exit-enabled -- ACCEPTANCE_EXIT_ENABLED must be off: "
                "the baseline book is measured with today's exits")
    if not any(Path(args.earnings_dir).glob("*.csv")):
        return (f"refused:no-earnings -- no earnings CSVs in {args.earnings_dir}; "
                "pass --earnings-dir <main tree>/market_data/earnings")
    if rows_path(args.out_dir).exists():
        return (f"refused:already-run -- {rows_path(args.out_dir)} exists; the replay "
                "runs once. Re-render with --from-rows")
    return None


def cli_refusal(args) -> str | None:
    """Why this invocation must not run, or None."""
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if doc_path(args.out_dir, args.date).exists():
        return f"refused:already-written -- {doc_path(args.out_dir, args.date)} exists"
    if args.from_rows:
        return None if args.from_rows.exists() else f"refused:no-rows -- {args.from_rows} is missing"
    return _replay_refusal(args)


def load_or_replay(args) -> dict:
    """The saved rows (--from-rows) or one fresh replay, saved before rendering."""
    if args.from_rows:
        return json.loads(args.from_rows.read_text(encoding="utf-8"))
    from measure_acceptance_exits import cache_universe
    universe = cache_universe()
    blob = run_replay(universe[:args.tickers] if args.tickers else universe,
                      args.earnings_dir, args.workers)
    target = rows_path(args.out_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(blob), encoding="utf-8")
    return blob


def coverage_line(report) -> str:
    """Role split, open/filled split and every feature's computable share."""
    split = report["gap_split"]
    shares = ", ".join(f"{key} {cov['share'] * 100:.1f}%" + ("" if cov["tested"] else " NOT TESTED")
                       for key, cov in report["coverage"].items())
    return (f"coverage: unidentified={report['unidentified']} of {report['n']}; "
            f"role target={split['target']} stop={split['stop']}; "
            f"gap open={split['open']} filled={split['filled']}; computable: {shares}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--earnings-dir", type=Path, default=EARNINGS_CSV_DIR)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--from-rows", type=Path, default=None)
    args = parser.parse_args(argv)
    refusal = cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    blob = load_or_replay(args)
    rows = blob["rows"]
    print(f"population: N={len(rows)} FVG (bullish) of {len(rows) + blob['other_triggered']} "
          f"triggered confluence plans, {blob['tickers']} tickers "
          f"(expected {fd.EXPECTED_N} of {EXPECTED_ALL})", flush=True)
    if not args.tickers and not fd.population_ok(len(rows)):
        print(f"refused:population -- N={len(rows)} is more than 2% from {fd.EXPECTED_N}; "
              "the engine moved. No results document written.", file=sys.stderr)
        return 2
    report = fd.build_report(rows)
    print(coverage_line(report), flush=True)
    target = doc_path(args.out_dir, args.date)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fd.render(report, run_date=args.date, tickers=blob["tickers"],
                                tolerance_pct=blob.get("confluence_tolerance_pct")),
                      encoding="utf-8")
    print(f"v143: {len(report['candidates'])} candidate(s) of {len(report['cells'])} looks, "
          f"N={report['n']}, unidentified={report['unidentified']} -> {target}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`_worker` imports `measure_arms`, `measure_earnings_blackout` and `universe` inside the function on purpose: a spawned worker re-imports this script, and those modules pull in the whole arms engine, which the parent process never needs.

`replay_with_scenarios` is the only place this plan touches a live module's state, and it does so at runtime only: it swaps `backtest_scenarios.build_confluence_plan` and `backtest_scenarios.levels_asof` for recording wrappers during one `replay_scenarios` call and puts both originals back in a `finally`. `replay_scenarios` looks both names up in its own module globals at call time, which is why the swap is seen. The `levels_asof` wrapper learns the map bar from the cache itself (the call that made `len(cache)` grow), so it holds whatever the warm-up bar or bucket alignment is. Do not edit `backtest_scenarios.py` to return the scenario instead.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_bullish_diagnostic.py`
Expected: 13 passed, 0 failed (one of them runs the real `replay_scenarios` on a 180-bar fixture, a few seconds).

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: 0 failed. (`test_no_path_a_test_reads_is_classified_inert` scans every test's path literals. The new tests name no `docs/` path, so `DATA_READERS` in `scripts/dev/select_tests.py` needs no entry; if this test fails anyway, add the path it names to `DATA_READERS` in the same commit.)

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C scripts/backtest/measure_fvg_bullish_diagnostic.py tests/scripts/test_measure_fvg_bullish_diagnostic.py`
Expected: no output (`run_replay` scores 10).

- [ ] **Step 6: Smoke-run two tickers through the real process pool**

Invoke the `backtest-gate` skill first. Confirm no other heavy python run is live. Then, from the worktree root, with `run_in_background: true` (about 15 minutes; the second ticker is AAPL with a full history):

```bash
mkdir -p logs/v143-smoke
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_fvg_bullish_diagnostic.py --date smoke --tickers 2 --workers 2 --out-dir logs/v143-smoke --earnings-dir E:/Documents/Private/Projects/Discord-Bot/market_data/earnings > logs/v143-smoke.log 2>&1
```

Poll with `tail -3 logs/v143-smoke.log` and `cat logs/measure_fvg_bullish_diagnostic.progress`. Note the wall time: V143-6's poll interval is sized from it.

Expected, exit 0, the log's five lines (ticker order may differ):

```text
  [v143 2020-01-01..2023-12-31] 1/2 ABNB: 10 FVG (bullish) trades, 62 other
  [v143 2020-01-01..2023-12-31] 2/2 AAPL: 10 FVG (bullish) trades, 34 other
population: N=20 FVG (bullish) of 116 triggered confluence plans, 2 tickers (expected 1278 of 8089)
coverage: unidentified=0 of 20; role target=15 stop=5; gap open=15 filled=5; computable: gap_age 100.0%, gap_height_atr 100.0%, displacement 100.0%, stop_atr 100.0%, quality 100.0%, trend_aligned 100.0%, volatility 100.0%, earnings_distance 100.0%, gap_open 100.0%
v143: 0 candidate(s) of 27 looks, N=20, unidentified=0 -> logs\v143-smoke\smoke-v143-fvg-bullish-diagnostic.md
```

Those counts are what the prototype of this exact script printed on `main` at `c29e2e12`. Different counts mean the worktree is reading a different cache or config than the expected 1,278 was measured with: stop and report it; do not go on to V143-6. A `BrokenProcessPool` or a second `population:` line means the `__main__` guard is gone.

- [ ] **Step 7: Confirm the replay quality score varies, then clean up**

```bash
python -c "import json, collections as c; f = [r['features'] for r in json.load(open('logs/v143-smoke/v143-fvg-bullish-rows.json'))['rows']]; print(len(f), c.Counter(x['fvg_role'] for x in f), c.Counter(x['gap_open'] for x in f)); print(sorted(c.Counter(x['quality'] for x in f).items())); print(sum(x['earnings_distance'] is not None for x in f))"
```

Expected: 20 rows; roles `target 15, stop 5, unidentified 0`; gap at the signal bar `open (True) 15, filled (False) 5`; the replay quality distribution the prototype measured, `[(38, 3), (48, 1), (56, 3), (59, 1), (62, 1), (63, 6), (66, 1), (67, 4)]` (score: count); `earnings_distance` computable on all 20. A quality score that is `None` or one constant value on every row, or any unidentified row, means the capture or the scorer wiring is broken: stop and fix it with a failing test before V143-6. Report the role split, the open/filled split and the distribution to the controller.

Then:

```bash
rm -r logs/v143-smoke logs/v143-smoke.log
ls logs/v143-fvg-bullish-rows.json logs/measure_fvg_bullish_diagnostic.progress
```

Expected: `ls` reports both files missing (the smoke run wrote its rows beside its scratch document, and the progress file is deleted on completion).

- [ ] **Step 8: Commit**

```bash
git add scripts/backtest/measure_fvg_bullish_diagnostic.py tests/scripts/test_measure_fvg_bullish_diagnostic.py
git commit -m "feat(v143): FVG (bullish) diagnostic driver, pooled replay with target capture (V143-5)"
```

### Task V143-6: The one TRAIN replay (`backtest-runner`)

**Files:**
- Create (written by the script): `docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`
- Uncommitted (written by the script, gitignored): `logs/v143-fvg-bullish-rows.json`

**Interfaces:**
- Consumes: `scripts/backtest/measure_fvg_bullish_diagnostic.py` (V143-5) and the smoke run's wall time.
- Produces: the results document. V143-7 copies every number it writes from this file.

**Preconditions:**
- V143-1..5 committed on the branch; `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic status --short` is empty.
- `ls logs/v143-fvg-bullish-rows.json docs/superpowers/results/*-v143-fvg-bullish-diagnostic.md` in the worktree reports both missing. If either exists the replay already ran: this task is done or must not run.

- [ ] **Step 1: Invoke `backtest-gate`**

- [ ] **Step 2: Dispatch the `backtest-runner` agent with exactly this brief**

Replace `<POLL>` with an interval sized from the smoke run (about 10 minutes for a 70-minute run).

```text
Worktree: E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic
(branch 2026-10-09-v143-fvg-bullish-badge-diagnostic). Work only there. The only
main-tree paths you may touch, read-only, are
E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache and
E:/Documents/Private/Projects/Discord-Bot/market_data/earnings.

Job: the v143 FVG (bullish) badge diagnostic replay. Run it exactly once.

This is a read-only TRAIN diagnostic (2020-01-01..2023-12-31, fixed inside the
script) with its own pre-registered rule. Do not apply the win-rate gates from
your instructions, and do not pass --tickers, --from-rows, --out-dir or
--dry-run. Never read 2024-2025.

1. Your "Before you start" step 1: if another heavy python run is live, stop
   and return BLOCKED.
2. From the worktree root, with run_in_background: true:
     mkdir -p logs
     BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_fvg_bullish_diagnostic.py --date $(date -u +%Y-%m-%d) --workers 6 --earnings-dir E:/Documents/Private/Projects/Discord-Bot/market_data/earnings > logs/v143-replay.log 2>&1
   Expected about 70 minutes for 75 tickers at 6 workers (about 7.7 minutes per
   ticker serial). The log prints one flushed line per finished ticker:
     [v143 2020-01-01..2023-12-31] i/75 TICKER: n FVG (bullish) trades, m other
   and logs/measure_fvg_bullish_diagnostic.progress holds "i/75 tickers (P%)"
   until the run completes. Poll `cat logs/measure_fvg_bullish_diagnostic.progress`
   every <POLL>; do not tail the log into your context more than 3 lines at a time.
3. Exit 0: the last three log lines are
     population: N=... FVG (bullish) of ... triggered confluence plans, 75 tickers (expected 1278 of 8089)
     coverage: unidentified=... of ...; role target=... stop=...; gap open=... filled=...; computable: gap_age ...%, ... (NOT TESTED after any share under 80%)
     v143: K candidate(s) of 27 looks, N=..., unidentified=... -> <results path>
   Do not edit, delete or commit anything.
4. Exit 2 with "refused:population": do NOT re-run and do NOT change any flag.
   The rows are in logs/v143-fvg-bullish-rows.json; leave them.
5. Any other "refused:" line, or a traceback: do NOT re-run and do NOT change
   any flag. Say whether logs/v143-fvg-bullish-rows.json exists.

Return (under 25 lines): exit code, wall time, the `population:`, `coverage:`
and final `v143:` lines verbatim, the results-document path, the absolute log path,
whether logs/v143-fvg-bullish-rows.json exists, and any anomaly (a ticker
count other than 75, a ticker line that looks wrong, a leftover progress file).
```

- [ ] **Step 3: Verify what the run wrote**

Run, in the worktree:
- `git status --short`. Expected: exactly `?? docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`.
- `grep -n "^\*\*Verdict" docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: one line, the same candidate count as the runner's final line.
- `grep -n "^\*\*Gap role" docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: one line whose target / stop / unidentified and open / filled counts equal the runner's `coverage:` line.
- `grep -n "^\*\*Population N = \|^\*\*Not tested" docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: N between 1,253 and 1,303 with the unidentified count and share; and a `Not tested:` line exactly when the runner's `coverage:` line tagged a feature `NOT TESTED`.
- `grep -n "^## Feature coverage" -A 10 docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: nine rows, shares equal to the `coverage:` line.
- `grep -c "| live |\|| g125 |\|| g100 |" docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: `30` (27 candidate-table rows plus the three whole-population rows).
- `grep -n "27 looks\|not testable on this population\|not the live one" docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`. Expected: three lines (the multiple-looks warning above the tables, and the two notes).
- `ls logs/measure_fvg_bullish_diagnostic.progress`. Expected: missing.

If the run stopped early, follow the phase rule at the top of this part; this task is not done until the document exists. Leave `logs/v143-fvg-bullish-rows.json` in place until V143-8 is green. Delete `logs/v143-replay.log`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/*-v143-fvg-bullish-diagnostic.md
git commit -m "results(v143): FVG (bullish) badge diagnostic, <K> candidate(s) of 27 looks on TRAIN (V143-6)"
```

Replace `<K>` with the count in the document's verdict line before committing.

### Task V143-7: Close-out: closed-table row, `EXEMPT`, spec status

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (one row at the top of "Closed pre-registrations — do not re-run these")
- Modify: `tests/backtesting/test_preregistration_ledger_file.py` (`EXEMPT`)
- Modify: `docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md` (`**Status:**` line only)
- Modify, only if the mirror test asks for it: `AGENTS.md`

**Interfaces:**
- Consumes: the results document committed by V143-6.
- Produces: the row that makes the diagnostic un-re-runnable by convention, and the exemption that keeps the ledger test green.

- [ ] **Step 1: Collect the numbers from the file, not from memory**

Run, in the worktree, with `DOC=docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`:
- `grep -n "^\*\*Run:\|^\*\*Verdict\|^\*\*Not tested\|^\*\*Population N = " $DOC`
- `grep -n "^## Feature coverage" -A 10 $DOC`
- `grep -n "^## Whole population" -A 6 $DOC`
- `grep -n "^\*\*Gap role" $DOC` (target / stop / unidentified, and open / filled at the signal bar)
- `grep -n "CANDIDATE\*\*" $DOC` (the candidate rows, if any)

Every number written below is copied from those lines.

- [ ] **Step 2: Add the closed-table row**

In `docs/claude/backtest-methodology.md`, insert directly below the `|---|---|---|` line of "### Closed pre-registrations — do not re-run these" one row in this exact shape (fill every `<...>` from Step 1):

```markdown
| FVG (bullish) primary — nine signal-bar features, one split each, at the live geometry and at first targets of 1.25R and 1.00R (v143 read-only diagnostic) | **<VERDICT> in a read-only diagnostic; no budget spent.** TRAIN 2020-2023, <tickers> tickers, N=<n> triggered plans, gap role <t> target / <s> stop / <u> (<share>%) unidentified; the gap was still open at the signal bar on <o> and already filled on <f> (the replay reuses a level map for up to 5 bars; the live scan builds it fresh and would not label those). Whole population <wr>% / <expr>R as built, <wr>% / <expr>R at 1.25R, <wr>% / <expr>R at 1.00R. Rule per pair, on the favourable side: N >= 150, win rate >= 50%, ExpR > 0, at least +0.10R above the other side, positive in 3 of 4 years; 27 looks, so one or two chance hits are expected. <NOT TESTED> Share of gap filled was dropped before the run as not testable on this population (the live finder drops any touched gap), and the quality feature is a replay score from causal per-ticker inputs, not the live one. <CLOSING SENTENCE> | `results/<run-date>-v143-fvg-bullish-diagnostic.md` |
```

- `<VERDICT>` is `NO CANDIDATE` or `<k> CANDIDATE(S): <feature at geometry, ...>`.
- `<NOT TESTED>` is empty when the document has no `Not tested:` line. Otherwise it is: `Not tested, so neither candidates nor closed: <feature names> (computable for under 80% of the population).`
- `<CLOSING SENTENCE>` for no candidate: `Closed for the tested features: FVG (bullish) stays WEAK and no filter on a tested feature of this list is proposed again under another name. Skipping FVG (bullish)-primary plans to lift the rest of the book is a separate question and stays open.` For one or more candidates: `Each candidate has earned a spec, nothing more: Edge expectancy, its own Stage −2 screen, then the funnel and one VALIDATION shot; a candidate at 1.25R or 1.00R must also argue a per-primary target rule against the structural target selection.`

Two tests read this table, so keep to the shape:
- `tests/backtesting/test_preregistration_ledger_file.py` collects every `(vNNN` in a row. The row must contain `(v143` exactly once and no other parenthesised version tag. Write other versions without an opening parenthesis in front of them, or leave them out.
- `tests/hooks/test_guardrails.py` treats any backticked ALL-CAPS token of five or more characters in the table as a closed config knob. Do not put `VALIDATED`, `TRAIN` or any other such word in backticks in this row.

- [ ] **Step 3: Exempt v143 from the ledger**

In `tests/backtesting/test_preregistration_ledger_file.py`, add one entry to `EXEMPT`, after the `"v127"` line:

```python
    "v143": "read-only diagnostic, nine features at three geometries, no budget spent",
```

- [ ] **Step 4: Update the spec's Status line**

In `docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`, replace the `**Status:**` line with:

```markdown
**Status:** implemented <date>; measured once on TRAIN: <NO CANDIDATE | k candidate(s): feature at geometry, ...><; not tested: feature names, when any>. Result: `docs/superpowers/results/<run-date>-v143-fvg-bullish-diagnostic.md`.
```

- [ ] **Step 5: Run the gates these three files sit behind**

- `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`. Expected: 0 failed.
- `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`. Expected: 0 failed.
- `python scripts/dev/testrun.py file tests/hooks/test_spec_screen_header.py`. Expected: 0 failed.
- `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`. Expected: 0 failed. A table row does not change what `AGENTS.md` mirrors, so no edit is expected. If it reports drift, run `python scripts/dev/sync_codex.py`, fix `AGENTS.md` as its message says, re-run this test, and add `AGENTS.md` to the commit below.

- [ ] **Step 6: Commit**

```bash
git add docs/claude/backtest-methodology.md tests/backtesting/test_preregistration_ledger_file.py docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md
git commit -m "docs(v143): close out the FVG (bullish) diagnostic, <VERDICT> (V143-7)"
```

Replace `<VERDICT>` before committing.

### Task V143-8: Full-suite verification

**Files:** none (fix-forward edits only if the run is red).

- [ ] **Step 1: Run the full suite once**

Dispatch the `test-runner` agent (worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic`) to run `python scripts/dev/testrun.py full` once, over everything V143-1..7 implemented.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 2: If it is not green, fix forward**

The failures it names are this plan's regressions. Fix each with a failing test first, commit, and re-dispatch the one run. The task is not done until the run is green. A fix never touches the committed results document's numbers and never re-runs the replay.

- [ ] **Step 3: Hand back for merge and close-out**

Report the one-line verdict to the controller. Delete `logs/v143-fvg-bullish-rows.json`. Merging the branch to `main` (`worktree-lifecycle`; no second suite run unless the merge resolved conflicts) and `/close-out` (`Bump: none`; the plan and spec move to `implemented/`) are the controller's.
