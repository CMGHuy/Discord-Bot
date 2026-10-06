# v134 FVG context diagnostic, Part 3: Table B, report, pre-registration, the run, close-out (V134-10 .. V134-15)

> Header, "Dependencies: what is blocked on what", Global Constraints, the frozen readings (F1–F15), the spec gaps (G1–G3), the file map and `## Parallelisation` live in `2026-10-06-v134-fvg-context-diagnostic_0-index.md`. Every task here implicitly includes them. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v134-fvg-context-diagnostic`; all paths below are relative to it.

# Phase 4 — Table B, report and CLI

### Task V134-10: Table B collector: baseline FVG-tagged plans

**Files:**
- Modify: `scripts/backtest/measure_fvg_context_diagnostic.py`
- Modify: `tests/scripts/test_measure_fvg_context_diagnostic.py` (append)

**Interfaces:**
- Consumes (v128, V128-5, `scripts/backtest/fvg_attribution.py`):
  - `record_ticker(ticker, df, horizons, signal_window) -> list[dict]`, one row per accepted baseline confluence plan: `{"key": [ticker, strategy, horizon, "YYYY-MM-DD", "confluence", direction], "fvg_family": bool, "candidates": {...}}`. Its body is three lines: open `_recording(log, level_bars)`, run `ConfluenceEngine().run_ticker(ticker, df, tuple(horizons), tuple(signal_window), ScanParams.from_config())`, then build `_provenance_row(ticker, df, record, level_bars, memo)` per log record.
  - `_recording(log: list, level_bars: dict)`: context manager; each accepted plan appends `{"signal_index", "horizon_key", "take_profit", "stop_level", "tp1", "strategy", "direction"}` to `log`.
  - `_provenance_row(ticker, df, record, level_bars, memo) -> dict`: the row above for one log record.
  - `VOTE_TOLERANCE_PCT = 5.0`.
- Consumes (existing): `ConfluenceEngine.run_ticker` returns `ArmTrade`s; `ArmTrade.key == (ticker, strategy, horizon_key, entry_date, source, direction)`; `arms.knobs.apply_knobs(delta)`; `acceptance.CLOSED`, `win_rate`, `expectancy_r`; `fvg.find_fair_value_gaps_detailed(window)`.
- Consumes (this plan): `fc.formation_tags`, `fc.touch_tags`, `TAG_BUCKETS`, `THIN_N`.
- Produces:
  - `plan_gap(window, take_profit) -> dict | None`.
  - `replay_plans(ticker, df, horizons, window) -> tuple[list[tuple[dict, dict]], list[ArmTrade]]`: `(recorder row, recorder log record)` pairs and the closed trades.
  - `plan_row(df, record, trade) -> dict | None`, `collect_plans(ticker, df, horizons, window) -> {"rows": [...], "census": {"plans", "fvg_family", "unmatched"}}`.
  - `trade_stats(rows) -> {"n", "thin", "win_rate", "exp_r"}`, `table_b(rows) -> {tag: {bucket: {"confluence": trade_stats, "strategy": trade_stats}}}`.
  - **Plan row contract:** the four formation keys, the five touch keys (read at the signal bar), `direction` (the gap's), `source`, `outcome`, `r_multiple`, `ticker`.

**Blocked on: v128 (V128-5).** Spec gaps G1 and G2 and frozen readings F13 and F14 apply; read them in the index before writing code. `fvg_attribution` is imported inside the functions, never at module top, so the script still imports on a tree without it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fvg_context_diagnostic.py`:

```python
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from tests.market.fvg_context_frames import GAP_I  # noqa: E402


def _trade(day, outcome="win", r=2.0):
    return ArmTrade("T", "S/R Confluence", "3m", day, outcome, r, 2.0, "confluence", "bullish")


def _pair(day, signal_index, *, fvg_family=True, take_profit=104.0):
    row = {"key": ["T", "S/R Confluence", "3m", day, "confluence", "bullish"], "fvg_family": fvg_family,
           "candidates": {}}
    return row, {"signal_index": signal_index, "take_profit": take_profit, "horizon_key": "3m"}


def test_plan_gap_is_the_unfilled_gap_within_the_vote_tolerance_of_the_take_profit():
    frame = gap_frame([ABOVE] * 3)                                  # the gap 101.0..101.5 is still unfilled
    assert mfc.plan_gap(frame, 104.0)["bar_index"] == GAP_I         # mid 101.25 is 2.6% from 104.0
    assert mfc.plan_gap(frame, 110.0) is None                       # 8.0%: outside v128's 5% vote tolerance
    assert mfc.plan_gap(gap_frame([TOUCH]), 104.0) is None          # a touched gap no longer votes


def test_plan_gap_takes_the_most_recently_formed_of_several():
    stairs = bar_frame([(100.0 + 2 * k, 101.0 + 2 * k, 99.5 + 2 * k, 100.5 + 2 * k) for k in range(10)])
    assert mfc.plan_gap(stairs, 118.0)["bar_index"] == 9


def test_collect_plans_keeps_closed_fvg_tagged_plans_and_tags_them_at_the_signal_bar(monkeypatch):
    frame = gap_frame([ABOVE] * 8)
    days = [str(frame.index[k].date()) for k in (25, 26, 27, 28)]
    pairs = [_pair(days[0], 25), _pair(days[1], 26, fvg_family=False), _pair(days[2], 27),
             _pair(days[3], 28, take_profit=130.0)]
    trades = [_trade(days[0]), _trade(days[1]), _trade(days[3], "loss", -1.0)]      # days[2]: never closed
    monkeypatch.setattr(mfc, "replay_plans", lambda *args: (pairs, trades))
    out = mfc.collect_plans("T", frame, ("3m",), ("2020-01-01", "2023-12-31"))
    assert out["census"] == {"plans": 3, "fvg_family": 2, "unmatched": 1}
    (row,) = out["rows"]
    assert (row["ticker"], row["source"], row["outcome"], row["r_multiple"]) == ("T", "confluence", "win", 2.0)
    assert (row["direction"], row["origin"], row["touch_close"], row["approach"]) == ("bullish", "intrabar", "above", "short")
    assert row["size_atr"] == pytest.approx(0.25)


def test_plan_tags_read_nothing_after_the_signal_bar(monkeypatch):
    frame = gap_frame([ABOVE] * 8)
    pairs, trades = [_pair(str(frame.index[25].date()), 25)], [_trade(str(frame.index[25].date()))]
    monkeypatch.setattr(mfc, "replay_plans", lambda *args: (pairs, trades))
    whole = mfc.collect_plans("T", frame, ("3m",), ("2020-01-01", "2023-12-31"))
    cut = mfc.collect_plans("T", frame.iloc[:26], ("3m",), ("2020-01-01", "2023-12-31"))
    assert whole["rows"] == cut["rows"]


def test_trade_stats_print_thin_under_30_closed_trades():
    rows = [{"outcome": "win", "r_multiple": 2.0}] * 20 + [{"outcome": "loss", "r_multiple": -1.0}] * 9 \
        + [{"outcome": "not_triggered", "r_multiple": None}] * 5
    assert mfc.trade_stats(rows) == {"n": 29, "thin": True, "win_rate": None, "exp_r": None}
    stats = mfc.trade_stats(rows + [{"outcome": "timeout", "r_multiple": 0.0}])
    assert (stats["n"], stats["thin"]) == (30, False)
    assert stats["win_rate"] == pytest.approx(100.0 * 20 / 29) and stats["exp_r"] == pytest.approx(31.0 / 30)


def test_table_b_splits_each_bucket_by_source_and_the_strategy_side_is_empty():
    rows = [{**row, "source": "confluence", "r_multiple": row["r"]} for row in mfc.with_size(
        _rows(31, "win", approach="slowing"), {"bullish": None, "bearish": None})]
    table = mfc.table_b(rows)
    assert table["approach"]["slowing"]["confluence"]["n"] == 31
    assert table["approach"]["slowing"]["strategy"] == {"n": 0, "thin": True, "win_rate": None, "exp_r": None}


@pytest.mark.slow
def test_replay_plans_returns_record_tickers_rows_plus_the_log_and_the_trades():
    import fvg_attribution as fa
    from swingbot.core.backtesting.arms.knobs import apply_knobs
    from tests.backtesting.test_v74_fixture import load_v74_fixture
    ticker, frame = sorted(load_v74_fixture().items())[0]
    window = ("1900-01-01", "2100-12-31")
    pairs, trades = mfc.replay_plans(ticker, frame, ("3m",), window)
    with apply_knobs({"FVG_LEVELS_MODE": "all"}):
        expected = fa.record_ticker(ticker, frame, ("3m",), window)
    assert pairs, "the fixture must produce confluence plans or this test proves nothing"
    assert [row for row, _ in pairs] == expected
    assert all({"signal_index", "take_profit"} <= set(record) for _, record in pairs)
    assert {trade.key for trade in trades} <= {tuple(row["key"]) for row, _ in pairs}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: the new tests FAIL with `AttributeError: module 'measure_fvg_context_diagnostic' has no attribute 'plan_gap'` (and `collect_plans`, `trade_stats`, `table_b`, `replay_plans`); every earlier test still passes.

- [ ] **Step 3: Implement**

In `scripts/backtest/measure_fvg_context_diagnostic.py`, add `from types import SimpleNamespace` below `from pathlib import Path`, and replace the `swingbot` import lines with:

```python
from swingbot.core.backtesting import acceptance  # noqa: E402
from swingbot.core.backtesting.arms import windows  # noqa: E402
from swingbot.core.market import fvg, fvg_context as fc  # noqa: E402
```

Append at the end of the file:

```python
# --- Table B collector (needs v128's fvg_attribution.py) --------------------------

def plan_gap(window, take_profit: float) -> dict | None:
    """The most recently formed unfilled gap that casts the plan's FVG vote: its mid is
    within v128's vote tolerance of the take-profit at the signal bar."""
    import fvg_attribution as fa
    near = [gap for gap in fvg.find_fair_value_gaps_detailed(window)
            if gap["mid"] > 0 and abs(gap["mid"] - take_profit) / take_profit * 100 <= fa.VOTE_TOLERANCE_PCT]
    return max(near, key=lambda gap: gap["bar_index"]) if near else None


def replay_plans(ticker: str, df, horizons, window) -> tuple:
    """([(recorder row, recorder log record)], closed ArmTrades) for the baseline ``all`` arm.

    This is fvg_attribution.record_ticker's body, kept open: the rows are exactly
    what record_ticker returns, but its row shape drops the take-profit and the
    signal bar, which identifying the plan's gap needs, and its caller drops the trades."""
    import fvg_attribution as fa
    from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
    from swingbot.core.backtesting.arms.knobs import apply_knobs
    from swingbot.scan_params import ScanParams
    log, level_bars, memo = [], {}, {}
    with apply_knobs({"FVG_LEVELS_MODE": "all"}), fa._recording(log, level_bars):
        trades = ConfluenceEngine().run_ticker(ticker, df, tuple(horizons), tuple(window), ScanParams.from_config())
        rows = [fa._provenance_row(ticker, df, record, level_bars, memo) for record in log]
    return list(zip(rows, log)), trades


def plan_row(df, record: dict, trade) -> dict | None:
    """One Table B row: the plan's gap tagged at formation and at the SIGNAL bar. None if no gap matches."""
    signal = int(record["signal_index"])
    gap = plan_gap(df.iloc[:signal + 1], record["take_profit"])
    if gap is None:
        return None
    return {**fc.formation_tags(df, gap), **fc.touch_tags(df, gap, {"status": "touch", "bar_index": signal}),
            "direction": gap["direction"], "source": trade.source or "confluence",
            "outcome": trade.outcome, "r_multiple": trade.r_multiple}


def collect_plans(ticker: str, df, horizons, window) -> dict:
    """FVG-tagged baseline plans of one ticker, joined to their closed trades by ArmTrade.key."""
    pairs, trades = replay_plans(ticker, df, horizons, window)
    by_key = {trade.key: trade for trade in trades}
    census, rows = Counter(), []
    for row, record in pairs:
        trade = by_key.get(tuple(row["key"]))
        if trade is None:
            continue                                    # outside the signal window, or never triggered
        census["plans"] += 1
        if not row["fvg_family"]:
            continue
        census["fvg_family"] += 1
        tagged = plan_row(df, record, trade)
        if tagged is None:
            census["unmatched"] += 1
            continue
        rows.append({**tagged, "ticker": ticker})
    return {"rows": rows, "census": dict(census)}


def trade_stats(rows) -> dict:
    """N (closed trades), win rate and ExpR; ``thin`` under THIN_N, where no ExpR is given."""
    trades = [SimpleNamespace(outcome=row["outcome"], r_multiple=row["r_multiple"]) for row in rows]
    n = sum(1 for trade in trades if trade.outcome in acceptance.CLOSED)
    thin = n < THIN_N
    return {"n": n, "thin": thin, "win_rate": None if thin else acceptance.win_rate(trades),
            "exp_r": None if thin else acceptance.expectancy_r(trades)}


def table_b(rows) -> dict:
    """{tag: {bucket: {source: trade_stats}}}. No strategy-sourced plan can reach it: see STRATEGY_NOTE."""
    return {tag: {bucket: {source: trade_stats([row for row in rows if row[tag] == bucket and row["source"] == source])
                           for source in ("confluence", "strategy")}
                  for bucket in buckets}
            for tag, buckets in TAG_BUCKETS.items()}
```

`STRATEGY_NOTE` is defined in V134-11; `table_b`'s docstring only names it.

- [ ] **Step 4: Run the tests to verify they pass, then measure complexity**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: PASS, `0 failed`, including the `slow` replay test (the `file` profile does not deselect `slow`). If that one test fails on row equality, the recorder's body in v128 differs from the three lines quoted under "Consumes": stop and report `BLOCKED` with the diff; do not loosen the assertion.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fvg_context_diagnostic.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fvg_context_diagnostic.py tests/scripts/test_measure_fvg_context_diagnostic.py
git commit -m "feat(v134): diagnostic script -- Table B collector over v128's baseline recorder"
```

### Task V134-11: Report, progress and CLI

**Files:**
- Modify: `scripts/backtest/measure_fvg_context_diagnostic.py`
- Modify: `tests/scripts/test_measure_fvg_context_diagnostic.py` (append)

**Interfaces:**
- Consumes: everything V134-6, V134-9 and V134-10 produce; `measure_arms.load_frame(ticker)`, `measure_arms.cached_universe()`; `backtest_scenarios._resolve_replay_workers(workers)`; `windows.ALL_HORIZONS`.
- Produces:
  - `STRATEGY_NOTE`, `CONFOUNDED`, `DISCLAIMER` (strings the report must contain).
  - `render(report) -> str` and its parts `render_census`, `render_table_a`, `render_table_b`, `render_verdicts`.
  - `_worker(task) -> {"ticker", "gaps": collect_gaps(...), "plans": collect_plans(...)}` with `task = (ticker, start, end, horizons)`; it truncates with `train_frame` before either collector runs.
  - `run_all(tickers, start, end, horizons, workers) -> list`, `build_report(results, *, start, end, preregistration) -> dict`, `main(argv=None) -> int`.
  - CLI: `--start`, `--end` (default TRAIN), `--tickers` (comma list; tests only), `--workers`, `--preregistration P` (required, must exist), `--out-md P` (required, never overwritten). Refusals go to stderr with exit 1: the three window tokens, `refused:no-preregistration`, `refused:result-exists`.
  - Progress: one flushed line per ticker, `  [v134] <done>/<total> tickers (<pct>%) <TICKER>`, and the same percent in `logs/measure_fvg_context_diagnostic.<id>.progress`, deleted on completion.

**Blocked on:** V134-9 and V134-10 (so, transitively, both dependencies).

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fvg_context_diagnostic.py`:

```python
def _result(ticker="T"):
    gaps = {"rows": [{**row, "ticker": ticker} for row in _earning()], "census": {"formed": 300, "touched": 254,
            "gapped_through": 6, "untouched": 20, "censored": 15, "no_atr": 5},
            "sizes": {"bullish": [0.1 * k for k in range(1, 11)], "bearish": []}, "months": [f"{ticker}:2020-06", f"{ticker}:2022-06"]}
    plan = {**_rows(1, "win")[0], "size_atr": 0.25, "source": "confluence", "r_multiple": 2.0, "ticker": ticker}
    return {"ticker": ticker, "gaps": gaps, "plans": {"rows": [plan] * 31, "census": {"plans": 80, "fvg_family": 31}}}


def test_build_report_pools_tickers_and_renders_both_tables_and_the_verdict():
    report = mfc.build_report([_result("A"), _result("B")], start="2020-01-01", end="2023-12-31", preregistration="pre.md")
    assert (report["tickers"], report["census"]["formed"], report["ticker_months"]) == (2, 600, 4)
    assert report["verdicts"]["displacement"]["verdict"] == mfc.EARNS
    assert report["edges"]["bearish"] is None and len(report["edges"]["bullish"]) == 4
    text = mfc.render(report)
    for needle in ("## Table A: gap level (primary)", "## Table B: trade level (secondary)", mfc.CONFOUNDED,
                   mfc.STRATEGY_NOTE, mfc.DISCLAIMER, "| 600 | 508 | 12 | 40 | 30 | 10 | 4 |", "`pre.md`",
                   "| displacement | 240 | 240 | 66.7% / 41.7% |", "**earns a follow-on spec**", "**no-lift**",
                   "| yes | bullish | 240 | 66.7% | +0.667 | 3.2% |", "| 62 | 100.0% | +2.000 |", "| 0 | thin | thin |"):
        assert needle in text, needle


def _args(tmp_path, *extra):
    pre = tmp_path / "pre.md"
    pre.write_text("frozen", encoding="utf-8")
    return ["--preregistration", str(pre), "--out-md", str(tmp_path / "out.md"), *extra]


@pytest.mark.parametrize("extra,token", [(["--end", "2024-01-01"], "refused:window-touches-holdout"),
                                         (["--start", "2019-01-01"], "refused:window-outside-train")])
def test_main_refuses_a_bad_window_before_reading_anything(tmp_path, capsys, monkeypatch, extra, token):
    monkeypatch.setattr(mfc, "run_all", lambda *args: pytest.fail("a refused window must not run"))
    assert mfc.main(_args(tmp_path, *extra)) == 1
    assert token in capsys.readouterr().err and not (tmp_path / "out.md").exists()


def test_main_refuses_without_a_preregistration_record(tmp_path, capsys):
    assert mfc.main(["--preregistration", str(tmp_path / "missing.md"), "--out-md", str(tmp_path / "out.md")]) == 1
    assert "refused:no-preregistration" in capsys.readouterr().err


def test_main_never_overwrites_a_result(tmp_path, capsys):
    (tmp_path / "out.md").write_text("spent", encoding="utf-8")
    assert mfc.main(_args(tmp_path)) == 1
    assert "refused:result-exists" in capsys.readouterr().err
    assert (tmp_path / "out.md").read_text(encoding="utf-8") == "spent"


def test_main_writes_the_document_prints_flushed_progress_and_removes_its_progress_log(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(mfc, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(mfc, "_worker", lambda task: _result(task[0]))
    assert mfc.main(_args(tmp_path, "--tickers", "A,B", "--workers", "1")) == 0
    out = capsys.readouterr().out
    assert "[v134] 1/2 tickers (50%) A" in out and "[v134] 2/2 tickers (100%) B" in out
    assert "VERDICT displacement: earns a follow-on spec" in out and "VERDICT approach: no-lift" in out
    assert "## Table A: gap level (primary)" in (tmp_path / "out.md").read_text(encoding="utf-8")
    assert list((tmp_path / "logs").glob("*.progress")) == []


def test_the_worker_truncates_before_either_collector_sees_the_frame(monkeypatch):
    import measure_arms
    frame = pd.DataFrame({"Close": 1.0}, index=pd.bdate_range("2023-12-20", "2024-01-10"))
    seen = []
    monkeypatch.setattr(measure_arms, "load_frame", lambda ticker: frame)
    monkeypatch.setattr(mfc, "collect_gaps", lambda ticker, df, start: seen.append(df.index[-1]) or {})
    monkeypatch.setattr(mfc, "collect_plans", lambda ticker, df, horizons, window: seen.append(df.index[-1]) or {})
    mfc._worker(("T", "2020-01-01", "2023-12-31", ("3m",)))
    assert [str(stamp.date()) for stamp in seen] == ["2023-12-29", "2023-12-29"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: the new tests FAIL with `AttributeError: module 'measure_fvg_context_diagnostic' has no attribute 'build_report'` (and `main`, `_worker`); every earlier test still passes.

- [ ] **Step 3: Implement**

In `scripts/backtest/measure_fvg_context_diagnostic.py`, replace the standard-library import block with:

```python
import argparse
import sys
import uuid
from bisect import bisect_right
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from types import SimpleNamespace
```

Append at the end of the file:

```python
# --- rendering --------------------------------------------------------------------

STRATEGY_NOTE = ("strategy-sourced: n/a. fvg_attribution.record_ticker replays confluence plans only; a "
                 "strategy plan has no confluence vote, so none can carry fvg_family (v128 resolution A6).")
CONFOUNDED = ("CONFOUNDED, NO VERDICT. FVG-tagged plans carry more families by construction, and every one "
              "passed every other gate. Tags are read at the signal bar, not at a first touch.")
DISCLAIMER = ("Gap statistics. Not the bot's ExpR and never quoted as it. No statistic here is inferential; "
              "nothing outside the four declared claims may be promoted to a claim afterwards.")


def _pct(value) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _stats_cells(stats: dict) -> str:
    return f"{stats['n']} | {_pct(stats['hold_rate'])} | {_num(stats['mean_r'])} | {_pct(stats['failed_share'])}"


def render_census(census: dict, months: int) -> list:
    head = " | ".join(CENSUS_KEYS) + " | ticker-months"
    cells = " | ".join(str(census.get(key, 0)) for key in CENSUS_KEYS)
    return ["### Census", "", f"| {head} |", "|" + "---|" * (len(CENSUS_KEYS) + 1), f"| {cells} | {months} |", ""]


def render_table_a(table: dict, edges: dict) -> list:
    lines = []
    for tag, buckets in TAG_BUCKETS.items():
        lines += [f"### {tag}", ""]
        if tag == "size":
            lines += [f"Quintile edges (zone width / ATR14, per direction): `{edges}`", ""]
        lines += ["| bucket | direction | N scored | hold rate | mean R | failed-on-touch share |", "|---|---|---|---|---|---|"]
        lines += [f"| {bucket} | {direction} | {_stats_cells(table[tag][direction][bucket])} |"
                  for bucket in buckets for direction in DIRECTIONS]
        lines.append("")
    return lines


def _trade_cells(stats: dict) -> str:
    if stats["thin"]:
        return f"{stats['n']} | thin | thin"
    return f"{stats['n']} | {stats['win_rate']:.1f}% | {_num(stats['exp_r'])}"


def render_table_b(table: dict, census: dict) -> list:
    lines = [CONFOUNDED, "", STRATEGY_NOTE, "",
             f"Closed baseline confluence plans: {census.get('plans', 0)}; with FVG among the families: "
             f"{census.get('fvg_family', 0)}; no matching gap: {census.get('unmatched', 0)}.", ""]
    for tag, buckets in TAG_BUCKETS.items():
        lines += [f"### {tag}", "", "| bucket | N closed | win rate | ExpR |", "|---|---|---|---|"]
        lines += [f"| {bucket} | {_trade_cells(table[tag][bucket]['confluence'])} |" for bucket in buckets]
        lines.append("")
    return lines


def render_verdicts(results: dict) -> list:
    lines = ["| claim | favourable N | against N | hold rate (fav / against) | mean R (fav / against) | "
             "failed share (fav / against) | failed clauses | verdict |", "|---|---|---|---|---|---|---|---|"]
    for claim, result in results.items():
        fav, against = result["bullish"]["favourable"], result["bullish"]["against"]
        failed = ", ".join(name for name, ok in result["clauses"].items() if not ok) or "none"
        lines.append(f"| {claim} | {fav['n']} | {against['n']} | {_pct(fav['hold_rate'])} / {_pct(against['hold_rate'])} | "
                     f"{_num(fav['mean_r'])} / {_num(against['mean_r'])} | "
                     f"{_pct(fav['failed_share'])} / {_pct(against['failed_share'])} | {failed} | **{result['verdict']}** |")
    lines.append("")
    for claim, result in results.items():
        for label, half in result["halves"].items():
            lines.append(f"- {claim} {label}: favourable {_stats_cells(half['favourable'])}; "
                         f"against {_stats_cells(half['against'])}; {'ok' if half['ok'] else 'FAILS clause 5'}")
        bear = result["bearish"]
        lines.append(f"- {claim} bearish: favourable {_stats_cells(bear['favourable'])}; "
                     f"against {_stats_cells(bear['against'])}")
    return lines + [""]


def render(report: dict) -> str:
    lines = ["# v134 FVG context diagnostic: results", "",
             f"**Window:** {report['start']}..{report['end']} (TRAIN; no bar after {report['end']} was read)",
             f"**Universe:** {report['tickers']} cached tickers",
             f"**Pre-registration:** `{report['preregistration']}`", "", DISCLAIMER, "",
             "## Table A: gap level (primary)", ""]
    lines += render_census(report["census"], report["ticker_months"])
    lines += render_table_a(report["table_a"], report["edges"])
    lines += ["## Pre-registered verdict (bullish gaps, Table A)", ""] + render_verdicts(report["verdicts"])
    lines += ["## Table B: trade level (secondary)", ""] + render_table_b(report["table_b"], report["plan_census"])
    return "\n".join(lines) + "\n"


# --- run --------------------------------------------------------------------------

def cached_universe() -> list:
    from measure_arms import cached_universe as universe
    return universe()


def _worker(task) -> dict:
    ticker, start, end, horizons = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        raise RuntimeError(f"{ticker}: no cached frame")
    frame = train_frame(frame, end)
    return {"ticker": ticker, "gaps": collect_gaps(ticker, frame, start),
            "plans": collect_plans(ticker, frame, horizons, (start, end))}


def _progress(path: Path, done: int, total: int, ticker: str) -> None:
    print(f"  [v134] {done}/{total} tickers ({100.0 * done / total:.0f}%) {ticker}", flush=True)
    try:
        path.write_text(f"{100.0 * done / total:.0f}% ({done}/{total} tickers)\n", encoding="utf-8")
    except OSError:
        pass


def _results(tasks, workers: int):
    if workers <= 1:
        yield from map(_worker, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(_worker, task) for task in tasks]):
            yield future.result()


def run_all(tickers, start: str, end: str, horizons, workers: int) -> list:
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_fvg_context_diagnostic.{uuid.uuid4().hex[:8]}.progress"
    tasks = [(ticker, start, end, tuple(horizons)) for ticker in tickers]
    out = []
    for done, result in enumerate(_results(tasks, workers), start=1):
        out.append(result)
        _progress(progress, done, len(tasks), result["ticker"])
    progress.unlink(missing_ok=True)
    return sorted(out, key=lambda result: result["ticker"])


def _sum_census(parts) -> dict:
    total = Counter()
    for part in parts:
        total.update(part["census"])
    return dict(total)


def _pooled(parts, key: str) -> list:
    return [item for part in parts for item in part[key]]


def _size_edges(gaps) -> dict:
    """Quintile edges per direction over every resolved (non-censored) gap with a size."""
    return {direction: quintile_edges([size for part in gaps for size in part["sizes"][direction]])
            for direction in DIRECTIONS}


def build_report(results, *, start: str, end: str, preregistration: str) -> dict:
    """Pool the per-ticker results into the census, both tables and the four verdicts."""
    gaps = [result["gaps"] for result in results]
    plans = [result["plans"] for result in results]
    edges = _size_edges(gaps)
    rows = with_size(_pooled(gaps, "rows"), edges)
    return {"start": start, "end": end, "tickers": len(results), "preregistration": preregistration,
            "census": _sum_census(gaps), "ticker_months": len(set(_pooled(gaps, "months"))),
            "edges": edges, "table_a": table_a(rows), "verdicts": verdicts(rows),
            "table_b": table_b(with_size(_pooled(plans, "rows"), edges)), "plan_census": _sum_census(plans)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default=TRAIN_START)
    parser.add_argument("--end", default=TRAIN_END)
    parser.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--preregistration", required=True, help="the committed pre-registration record")
    parser.add_argument("--out-md", required=True, help="results document; never overwritten")
    return parser


def _refusal(args) -> str | None:
    refusal = window_refusal(args.start, args.end)
    if refusal:
        return refusal
    if not Path(args.preregistration).is_file():
        return f"refused:no-preregistration -- {args.preregistration} does not exist"
    if Path(args.out_md).exists():
        return f"refused:result-exists -- {args.out_md} is already written; the measurement runs once"
    return None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    refusal = _refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    tickers = args.tickers.split(",") if args.tickers else cached_universe()
    results = run_all(tickers, args.start, args.end, windows.ALL_HORIZONS, _resolve_replay_workers(args.workers))
    report = build_report(results, start=args.start, end=args.end, preregistration=args.preregistration)
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(render(report), encoding="utf-8")
    for claim, result in report["verdicts"].items():
        print(f"VERDICT {claim}: {result['verdict']}", flush=True)
    print(f"v134 diagnostic done -> {args.out_md}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass, then measure complexity and syntax**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fvg_context_diagnostic.py`
Expected: PASS, `0 failed`.
Run: `python -m radon cc -s -n C scripts/backtest/measure_fvg_context_diagnostic.py swingbot/core/market/fvg_context.py`
Expected: no output.
Run: `python -m py_compile scripts/backtest/measure_fvg_context_diagnostic.py swingbot/core/market/fvg_context.py && python scripts/backtest/measure_fvg_context_diagnostic.py --preregistration nope.md --out-md nope-out.md --end 2024-01-01; echo "exit $?"`
Expected: one `refused:window-touches-holdout` line and `exit 1`. No file is created.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_fvg_context_diagnostic.py tests/scripts/test_measure_fvg_context_diagnostic.py
git commit -m "feat(v134): diagnostic script -- report, per-ticker progress, one-shot CLI"
```

# Phase 5 — Pre-registration and the one run

### Task V134-12: Pre-registration record, committed before the run

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md`

**Interfaces:**
- Consumes: the CLI from V134-11; the frozen readings F1–F15 and the gaps G1–G3 in the index.
- Produces: the committed record and its hash (`git log -1 --format=%h -- <record>`), which the results document and the closed-table rows cite.

**Blocked on:** v128 **closed** (its row in `docs/claude/backtest-methodology.md`) and v130 on `main`. Nothing here may be written before v128's grid and selection are final.

- [ ] **Step 1: Confirm the gate, the code and that no result exists**

Re-run V134-1 Step 2. Expected: both `PRESENT` and a v128 row count of `1` or more. Otherwise stop.
Run `git status --short` (expect clean) and each of the seven test files once:

```bash
for f in tests/market/test_fvg_context_gaps.py tests/market/test_fvg_context_tags.py tests/market/test_fvg_context_confluence.py tests/market/test_fvg_context_outcome.py tests/market/test_fvg_context_displacement.py tests/market/test_fvg_context_structure.py tests/scripts/test_measure_fvg_context_diagnostic.py; do
  python scripts/dev/testrun.py file "$f" || echo "STOP: $f is red"
done
ls docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md 2>/dev/null && echo "STOP: a result already exists -- this is no longer a pre-registration"
```

Expected: seven PASS verdicts and no `STOP` line.

- [ ] **Step 2: Read v128's closed row** and note its outcome for the displacement mechanism (`grep -n "(v128)" docs/claude/backtest-methodology.md`). It fills one field below and changes nothing else.

- [ ] **Step 3: Write the record**

Write exactly this. Fill the `<...>` fields from `git rev-parse --short HEAD`, the UTC time, and Step 2. Leave no other field open.

~~~markdown
# v134 pre-registration — FVG context diagnostic: structure, confluence, approach

**Status:** frozen before any run. Recorded at worktree HEAD `<short sha>` on `<YYYY-MM-DD HH:MM> UTC`.
**Spec:** `docs/superpowers/specs/2026-10-06-v134-fvg-context-diagnostic-design.md`
**Plan:** `docs/superpowers/plans/2026-10-06-v134-fvg-context-diagnostic_0-index.md`
**Edge:** none (integrity). Descriptive measurement on TRAIN. It gates nothing and spends no VALIDATION budget. Not a re-run of v128 (plan-level FVG vote), v122 (volume dry-up), v121 (impulse-leg shape) or v130 (structure tiers on trades).
**v128 at freeze:** `<the outcome in v128's closed row, verbatim>`.

## Window and population

Daily bars, the standard backtest cache, every cached ticker. A gap is in the population only if its third candle is dated 2020-01-01 or later and its formation, first touch and outcome all end on or before 2023-12-31. Every frame is cut at 2023-12-31 before the instrument sees it; the script refuses a window touching 2024-01-01. A gap the cut leaves unresolved is `censored`. A gap whose ATR14 is not a finite positive number at its third candle or at its touch bar is `no_atr`. Both are dropped and counted.

## Instrument (bullish; bearish mirrors every comparison)

- Gap at bar `i`: `Low[i] > High[i − 2]`; `bottom = High[i − 2]`, `top = Low[i]`, `mid` their mean.
- First touch `τ`: first bar after `i`, within 60 bars, with `Low ≤ top`. `High ≥ bottom` is a touch; `High < bottom` is gapped through (not scored); none in 60 bars is untouched (not scored).
- Outcome, `a = ATR14[τ]`: `stop = bottom − 0.25a`. `Close[τ] ≤ stop` is failed on touch. Else `entry = Close[τ]`, `risk = entry − stop`, `target = entry + 1.5 × risk`; bars `τ+1 … τ+20`: loss at the first `Low ≤ stop`, win at the first `High ≥ target`, stop first on a shared bar; neither is a timeout marked at `Close[τ+20]`.
- Constants `0.25`, `1.5`, `20`, `60`, displacement `k = 1.5`, structure event age `≤ 1` and the `4w` confluence horizon are frozen and were not searched.

| Tag | Known at | Definition | Buckets |
|---|---|---|---|
| displacement | `i` | `fvg.is_displacement_gap(df[:i+1], gap, 1.5)` | `yes`, `no` |
| structure | `i` | `structure.major_structure_features(df[:i+1], gap direction)`: `struct_event_last` is `bos_with` / `choch_with` and `struct_event_bars_ago ≤ 1` | `bos`, `choch`, `none` |
| confluence | `τ` | distinct non-FVG families within `CLUSTER_TOLERANCE_PCT` (1.5%) of `mid`, from `collect_candidate_levels(df[:τ+1], HORIZONS["4w"], Close[τ])` | `0`, `1-2`, `3+` |
| approach | `τ` | mean true range of the last third of bars `i+1 … τ` over the first third; undefined under 6 bars or on a zero first third | `slowing` (< 1), `not_slowing` (≥ 1), `short` |
| origin | `i` | share of the zone the middle candle never traded in | `intrabar`, `partial`, `true_gap` |
| size | `i` | `(top − bottom) / ATR14[i]`; quintiles per direction over every resolved gap | `q1` … `q5` |
| touch_close | `τ` | `Close[τ]` against the zone, geometric, not mirrored | `above`, `inside`, `below` |

## Claims and verdict (Table A, fixed before any run)

| Claim | Favourable | Against |
|---|---|---|
| displacement | `yes` | `no` |
| structure | `bos` or `choch` | `none` |
| confluence | `3+` | `0` and `1-2` |
| approach | `slowing` | `not_slowing` (`short` excluded) |

`N` is scored gaps (win + loss + timeout). Hold rate is `wins / (wins + losses)`. Mean R is over scored gaps. Failed-on-touch share is `failed / (scored + failed)`. A claim **earns a follow-on spec** only if, on bullish gaps, all six hold:

1. Hold rate is higher in the favourable bucket.
2. Mean R is no lower in the favourable bucket.
3. Failed-on-touch share is no higher in the favourable bucket.
4. Both sides have `N ≥ 100`.
5. Clauses 1 and 2 hold separately in 2020–21 and in 2022–23 (split on the gap's formation date), with `N ≥ 50` per side in each half.
6. On bearish gaps the hold-rate gap has the same sign, or a bearish side is under `N = 100`.

A clause whose statistic cannot be computed fails. Otherwise the claim closes as a no-lift row. `origin`, `size` and `touch_close` are descriptive and carry no verdict. No statistic is inferential. Nothing else in either table may be promoted to a claim afterwards. These are gap statistics, never the bot's ExpR.

## Table B (secondary, confounded, no verdict)

Baseline `FVG_LEVELS_MODE=all` confluence plans, all horizons, signal window 2020-01-01..2023-12-31, replayed through `fvg_attribution.py`'s recorder on the same truncated frames. A plan is in the table when the recorder's `fvg_family` is true and it closed. Buckets under `N = 30` closed trades print `thin`.

- **G1.** `record_ticker`'s row carries neither the take-profit nor the signal bar. The script runs the recorder's own body (`_recording`, `_provenance_row`) and keeps its log record. The plan's gap is the most recently formed unfilled gap whose mid is within 5.0% (`VOTE_TOLERANCE_PCT`, v128's vote definition) of the take-profit at the signal bar. `confluence`, `approach` and `touch_close` are read at the signal bar.
- **G2.** The recorder replays confluence plans only, so the strategy-sourced side is structurally empty and is printed as `n/a`.

## The run

One run, through the `backtest-runner` agent:

```
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python scripts/backtest/measure_fvg_context_diagnostic.py --preregistration docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md --out-md docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md
```

The script refuses to overwrite the results document. A crash before the document is written has spent nothing and may be fixed and re-run; a written document is final.

## Outcomes

Per claim: `earns a follow-on spec` or `no-lift`, each a row in `docs/claude/backtest-methodology.md`. A claim that earns one gets a separate `expectancy` spec that freezes its grid without reading this report's buckets and clears the v72 and v92 gates under its own pre-registration. Displacement: v128 owns the displacement vote; a pass here does not reopen a mechanism v128 closed, and a follow-on must name one outside v128's row (a zone entry, not the vote). Approach: a follow-on must state its difference from v122 and from v121's leg-shape keys.
~~~

- [ ] **Step 4: Commit before any run**

```bash
git add docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md
git commit -m "docs(v134): pre-registration -- FVG context diagnostic, four claims, six clauses"
git log -1 --format=%h -- docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md
```

Expected: one short hash. Make no edit under `swingbot/` or to the script after this commit and before V134-13 finishes.

### Task V134-13: The one TRAIN run

**Files:**
- Create: `docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md` (written by the script; keep the spec's date in the name whatever day the run happens)

**Interfaces:**
- Consumes: the script (V134-11) and the committed record (V134-12).
- Produces: the results document, with four `VERDICT <claim>: <earns a follow-on spec | no-lift>` lines that V134-14 turns into rows.

**Blocked on:** V134-12.

- [ ] **Step 1:** Invoke the `backtest-gate` skill. Confirm out loud: the stage is a TRAIN-only descriptive diagnostic; the window is `2020-01-01..2023-12-31`; no VALIDATION bar is read; no closed row is re-run; the cache is populated (`ls E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache | wc -l` prints the ticker count).
- [ ] **Step 2:** Confirm the record is committed and no result exists: `git log -1 --format=%h -- docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md` prints a hash, `git status --short` is clean, and `ls docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md` fails. If the result exists, the measurement is spent: read it and go to V134-14. Never delete it to re-run.
- [ ] **Step 3:** Dispatch the `backtest-runner` agent, naming the worktree, with exactly this command:

```bash
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache \
python scripts/backtest/measure_fvg_context_diagnostic.py \
  --preregistration docs/superpowers/results/2026-10-06-v134-fvg-context-preregistration.md \
  --out-md docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md
```

Do not pass `--tickers`, `--start` or `--end`. Progress is one flushed `[v134] <done>/<total> tickers (<pct>%)` line per ticker and the percent in `logs/measure_fvg_context_diagnostic.*.progress` (deleted on completion). Budget: the gap scan is about 330 gaps per ticker (measured on two tickers at planning; counts only), and the Table B replay is one baseline confluence replay per ticker over ten horizons, which dominates. Ask the agent to return only: the exit code, the four `VERDICT` lines and the final `done` line.

If the run crashes before writing the document, fix the crash with a narrow test, commit, and run again; a run that wrote no document has spent nothing. If the fix changes what a tag or the outcome computes, that is a change to the instrument after the freeze: stop and report `BLOCKED` to the partner instead.

- [ ] **Step 4: Sanity-check the population before trusting any verdict.** Read only the header, the census and the Table B census line of the document:

- `formed` equals the sum of the other five census cells.
- `touched` is in the thousands and `censored` is well under `formed`.
- The `structure` block has a non-zero `N` in `bos` or `choch` for at least one direction, and the `displacement` block has a non-zero `yes`.
- Table B reports a non-zero count of closed baseline plans.

A zero in the third or fourth check is a wiring fault (v130's keys or v128's recorder did not reach the script), not a no-lift result. Report `BLOCKED`, delete nothing, and ask the partner whether the document stands.

- [ ] **Step 5: Commit the document.** Quote the four verdict lines in the commit body exactly as printed (`pooled-numbers` skill: copy from the file, never retype).

```bash
git add docs/superpowers/results/2026-10-06-v134-fvg-context-diagnostic.md
git commit -m "docs(v134): record the TRAIN FVG context diagnostic"
```

# Phase 6 — Close-out

### Task V134-14: Closed-table rows and the Codex mirror check

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (four rows in § "Closed pre-registrations — do not re-run these")

**Interfaces:**
- Consumes: the committed results document and the record's hash.
- Produces: one row per claim, and the outcome list for the hand-off.

**Blocked on:** V134-13.

- [ ] **Step 1: Append four rows**, one per claim, at the end of the table. Use the shape that matches each claim's verdict, with numbers copied from the results document only.

For a claim that printed `no-lift`:

```markdown
| FVG context, <claim> claim: gaps tagged `<favourable>` vs `<against>` at first touch (v134) | **NO-LIFT on TRAIN, descriptive diagnostic; no budget spent.** TRAIN 2020-01-01..2023-12-31, <tickers> cached tickers, <formed> gaps formed, <touched> touched. Bullish favourable vs against: N <n> / <n>, hold rate <x>% / <y>%, mean R <a> / <b>, failed-on-touch <p>% / <q>%. Failed clauses: <names as printed>. Gap statistics, not the bot's ExpR. Reopening needs a mechanism other than <the tag's definition in one clause> | `results/2026-10-06-v134-fvg-context-preregistration.md` (`<hash>`), `results/2026-10-06-v134-fvg-context-diagnostic.md` |
```

For a claim that printed `earns a follow-on spec`:

```markdown
| FVG context, <claim> claim: gaps tagged `<favourable>` vs `<against>` at first touch (v134) | **EARNED A FOLLOW-ON SPEC on TRAIN; nothing ships and no budget is spent by this row.** TRAIN 2020-01-01..2023-12-31, <tickers> cached tickers, <formed> gaps formed, <touched> touched. Bullish favourable vs against: N <n> / <n>, hold rate <x>% / <y>%, mean R <a> / <b>, failed-on-touch <p>% / <q>%; all six clauses held, both halves included. Gap statistics, not the bot's ExpR. The follow-on is a separate `expectancy` spec that freezes its grid without reading this report's buckets and clears the v72 and v92 gates under its own pre-registration<displacement only: ; v128 owns the displacement vote, so the follow-on must name a mechanism outside v128's row><approach only: ; it must state its difference from v122 and from v121's leg-shape keys>. **Do not re-run this diagnostic at another window, constant or bucket** | `results/2026-10-06-v134-fvg-context-preregistration.md` (`<hash>`), `results/2026-10-06-v134-fvg-context-diagnostic.md` |
```

- [ ] **Step 2: Codex mirror check**

Run: `grep -n "Closed pre-registrations\|AVWAP_LEVELS_ENABLED (v35)" AGENTS.md`
Expected: no output. On 2026-10-06 `AGENTS.md` does not mirror the closed table, so there is no mirror edit. If the command prints a match (the table has since been mirrored), add one condensed line per claim to `AGENTS.md`, include it in the commit, and run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` (expect PASS).

- [ ] **Step 3: Commit**

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v134): close the FVG context diagnostic -- <n> claims earned a follow-on spec, <m> no-lift"
```

(Add `AGENTS.md` to the `git add` only if Step 2 edited it.)

### Task V134-15: Lookahead review, complexity, full-suite verification and hand-off

**Files:**
- None new. Fix only failures attributable to this plan, each with its narrow test.

**Interfaces:**
- Consumes: everything this plan committed on the branch.
- Produces: a green branch ready for the controller to merge.

**Blocked on:** V134-14.

- [ ] **Step 1: Lookahead review.** Invoke the `no-lookahead` skill and read `swingbot/core/market/fvg_context.py` once against it. Confirm: `formation_tags` and `touch_tags` each slice `df.iloc[:i + 1]` / `df.iloc[:tau + 1]` before any read; `gap_outcome` reads `_atr_at(df, tau)` and `Close[tau]` for its levels and reads forward only inside `_first_exit` and the timeout mark; no function reads `df.iloc[-1]` of the unsliced frame.

- [ ] **Step 2: Complexity.**

Run: `python -m radon cc -s -n C swingbot/core/market/fvg_context.py scripts/backtest/measure_fvg_context_diagnostic.py`
Expected: no output.

- [ ] **Step 3: One full-suite run.** Dispatch the `test-runner` subagent in the worktree to run `python scripts/dev/testrun.py full` once, over everything V134-2..V134-14 changed. Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). **If it is not green, fix forward from the failures it names**; they are this plan's regressions. A fix that cannot change what a tag or the outcome computes (an import, a lint finding, a test helper) is noted in one line at the end of the results document. A fix that would change one means the committed result was produced by a different instrument: stop and report `BLOCKED` to the partner; do not re-run on your own.

- [ ] **Step 4: Hand off.** Report to the controller: the branch name, the last commit, the four verdicts with their closed-row text, and the state of G1–G3. The branch merges on any outcome (the instrument and the script are inert: no live path imports them), following `worktree-lifecycle` and `superpowers:finishing-a-development-branch`. `Bump:` stays `none`: no `VERSION.json` change. Do not run the suite again after a conflict-free merge. Moving the spec and the four plan files to `implemented/` happens at `/close-out` (`document-lifecycle.md`), which the partner types. For each claim that earned a follow-on, tell the partner a separate `expectancy` spec is now permitted; it is not part of this plan.
