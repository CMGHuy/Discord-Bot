# v158 Instrument v2, phase 3: window contract and folds. Implementation Plan, part 3 (fold-selected tuner, the flag on every live script, date-literal guard, full suite)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief WC9` or `grep -n "^### Task WC9" -A 500 docs/superpowers/plans/2026-10-10-v158-instrument-v2-window-contract_3-tuner-scripts-guard.md`.

**Spec:** [`docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md`](../specs/2026-10-06-v136-backtest-instrument-v2-design.md) (cross-cutting rules 1 and 2; section 1 "Folds" and "Universe"; "Testing": date-literal guard)
**Index:** [`2026-10-10-v158-instrument-v2-window-contract_0-index.md`](2026-10-10-v158-instrument-v2-window-contract_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 1 and 2.

**Tasks in this part:** WC9, WC10, WC11, WC12. WC9 needs WC4 (folds), WC5 (universe gate), WC6 (CLI helper) and WC7 (aliases); WC10 needs WC6 and WC7. WC9 and WC10 may run in parallel with each other and with WC8 (disjoint files), at most 2 implementers at once. WC11 needs WC7–WC10 (it asserts the end state of every script). WC12 is the plan's single full-suite run and its final task.

Conventions used in every task (from the index's `## Where to work`):

- `$R` = `/home/user/Discord-Bot` (main tree, never edited by a task). `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract` (branch `2026-10-10-v158-instrument-v2-window-contract`).
- Never `cd`. Use `git -C $WT ...` and `python $WT/scripts/dev/testrun.py file tests/...` (test paths resolve against `$WT`).
- After every commit: `git -C $R status --short` must print nothing new (the main tree is unchanged).
- Every new or changed function stays < complexity 15: `python -m radon cc -s -n C <files>`. Legacy functions never get worse (measured on `main` at `085f7ce6`: `tune_strategy.main` D 29, `tune_strategy.run_config` C 17, `tune_exit_v2.main` C 15, `tune_confluence_gates.main` C 16, `wf_run.main` C 19, `measure_arms.main` C 14).
- Names used here from earlier parts (verify with `git -C $WT grep -n` before starting a task):
  - WC1: `InstrumentSpec.universe`, `.research_span`, `.purge`, `.embargo_days`, `.liquidity_floor`, `.fold_test_years`; `contract.resolve`, `contract.VERSIONS`.
  - WC4 (`instrument/folds.py`): `anchored_folds(spec) -> tuple[Fold, ...]`; `out_of_fold(trades_by_config, folds, select, *, embargo_days, purge=True) -> OutOfFold(choices, trades)`; `select` receives `{config: train trades}` and returns a config key.
  - WC5 (`instrument/universe_gate.py`): `eligible_trades(trades, spans, df, floor) -> list`; `watchlist_slice_verdict(n, expectancy_r) -> SliceVerdict(status, n, expectancy_r)`; `WATCHLIST_SLICE_MIN_N`.
  - WC6 (`instrument/cli.py`): `add_instrument_arg(parser)`; `spec_from_args(args)`; `window_for(spec, stage)`; `require_v1(spec, script, owner)` (SystemExit naming `script`, `--instrument v2` and `owner`).
  - WC7: `tune_strategy.TRAIN`, `tune_exit_v2.TRAIN`, `tune_confluence_gates.TRAIN` are `resolve_instrument("v1").train_window`, imported as `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument`.
  - Pre-existing `run_backtest_range` helpers WC9 calls (signatures unchanged by WC8): `window_trades(summary, date_from, date_to)`, `_tickers_for_run(universe)`, `_membership_for_run(universe, tickers)`, `_spans_for(membership, ticker)`, `_exclusion_reason(df, ticker, pit)`.

# Phase C (continued): tuner folds, the flag on every live script, the guard

### Task WC9: `tune_strategy.py --instrument`, fold-selected under v2

**Model:** opus — wires purged per-fold selection and pooled out-of-fold ExpR into the strategy tuner while its v1 stdout and JSON stay byte-identical, and lowers a D-29 `main`.

**Files:**
- Modify: `scripts/backtest/tune_strategy.py`
- Create: `tests/scripts/test_tune_strategy_instrument.py`

**Why:** spec rule 2 (every backtest script takes `--instrument`, windows from the contract) and section 1 "Folds": "Anything tuned (a grid, a threshold) is selected on the fold's train data only. The verdict statistic is pooled out-of-fold ExpR: each trade counts once, in its own test year. A strategy with nothing tuned skips the folds; its research-span ExpR is its out-of-fold ExpR." `tune_strategy.py` is the grid tuner, so it is the one script whose v2 path does the selection. Under v2:

- Every config is run once over the **research span** (`cli.window_for(spec, "train")`, 2010-01-01..2025-12-31) on the contract's **PIT universe** (`sp500_pit`, through the pre-existing `run_backtest_range` seams `_tickers_for_run` / `_membership_for_run` / `_spans_for` / `_exclusion_reason`), with `run_backtest(..., exit_model="v2", tp2_mode="none", instrument=spec)`. Trades are windowed by **entry** date, then kept only when PIT membership and the causal liquidity floor pass on the **signal** day (`universe_gate.eligible_trades`, WC5).
- The in-sample grid table and `best` are still printed (research-span numbers), and labelled as in-sample.
- Per fold (`folds.anchored_folds(spec)`, 2014..2025), the config is chosen by today's selection rule applied to that fold's **purged train trades only** (`folds.out_of_fold`, WC4). The chosen configs' test trades are pooled; their stats are the verdict statistic. A one-config grid ("nothing tuned") skips the folds and reports its research-span trades as its out-of-fold trades.
- The tuner pools every horizon into one config, so the embargo is the contract's global maximum, `spec.embargo_days` (partner decision 2). Under anchored folds it never fires anyway (index, "Embargo under anchored folds").
- The watchlist slice is scored on the **out-of-fold pool** (the verdict statistic's own trades), with WC5's `watchlist_slice_verdict`.
- `run_backtest`'s v2 refusals (`exit_model` must be `"v2"`, no live-state flag on) are checked **once, before any ticker loads**: `run_config`-style loops swallow every per-run exception, so a refusal inside them would silently empty the grid. The tuner has no `--tp2` flag; v2 always runs `tp2_mode="none"` (TP2 built exactly as live).
- `--json` gains four top-level keys: `"instrument"`, `"research_span"`, `"out_of_fold"` (`{"folds": [{"test_year", "params"}], n_eval, win_rate, expectancy_r, excluded_share}`) and `"watchlist_slice"` (`{status, n, expectancy_r}`).

Under v1 (the default) every path is today's: watchlist frames, `run_config` with its TRAIN alias (WC7), the same selection rule, the same stdout and the same JSON keys. `_fold_report` returns `{}` and prints nothing under v1.

**Scope notes:**
- The admin Tuning page launches this script through `swingbot/admin/jobs.py`'s argv whitelist (`build_tune_args`), which does not pass `--instrument`, so admin tuning stays v1. That is intended and not changed here.
- `run_config`'s statistics block moves verbatim into `_stats(trades)` (behaviour-preserving refactor), so v2's per-fold selection scores trades exactly as v1 does; the selection rule's gate and ranking move into `_qualifies` / `_rank` for the same reason. `tests/scripts/test_tune_strategy.py` (which stubs `run_config` with the signature `(strategy, dfs, exit_model="v1", scale_out=False)`) keeps passing because `main` still calls `run_config` with those keywords under v1.
- **Complexity:** `main` measures D 29 and `run_config` C 17 at `085f7ce6`. After this task `main` is C 20 (the dfs comprehension, the qualifying `and` chain and the ranking `or` move into helpers) and `run_config` is B 7. `_stats` is C 11: that is the block moved out of `run_config`, unchanged.
- WC9 imports no helper WC8 creates (only pre-existing `run_backtest_range` functions whose signatures WC8 leaves unchanged), so it can run in parallel with WC8.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scripts/test_tune_strategy_instrument.py`:

```python
"""v158 WC9: tune_strategy.py --instrument v1|v2 (v136 rule 1: v1 byte-identical;
section 1: research span, PIT universe gated on the signal day, per-fold
selection on train data only, pooled out-of-fold ExpR, watchlist slice)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import tune_strategy as ts  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402

V1, V2 = resolve("v1"), resolve("v2")
ALWAYS = [("2009-01-01", "9999-12-31")]


def _trade(entry, r=1.0, outcome=None, exit_=None):
    return BacktestTrade(entry_date=entry, exit_date=exit_ or entry, direction="bullish",
                         entry=50.0, stop_loss=48.0, take_profit=54.0,
                         outcome=outcome or ("win" if r > 0 else "loss"), exit_price=54.0,
                         return_pct=8.0, r_multiple=r, holding_days=3)


def _frame(volume=1_000_000, start="2009-06-01", end="2025-12-31"):
    index = pd.bdate_range(start, end)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": volume}, index=index)


def _rows(r_by_year, tickers=("AAA",)):
    return [(tk, _trade(f"{y}-03-02", r_by_year(y), exit_=f"{y}-03-10"))
            for tk in tickers for y in range(2010, 2026)]


def STEADY(year):
    return 0.5


def FADES(year):
    return 3.0 if year <= 2013 else -1.0


def LOSES(year):
    return -1.0


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- the v1 rule, moved into helpers unchanged -------------------------------------

def test_run_config_statistics_are_unchanged(monkeypatch):
    trades = [_trade("2019-12-31", 5.0), _trade("2020-01-02", 2.0), _trade("2021-06-01", -1.0),
              _trade("2023-12-31", 0.0, outcome="scratch"), _trade("2024-01-02", 9.0)]
    monkeypatch.setattr(ts.bt, "run_backtest", lambda *a, **k: SimpleNamespace(trades=trades))
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    assert ts.run_config("RSI", {"AAA": None}) == {
        "n_eval": 2, "win_rate": 50.0, "expectancy_r": pytest.approx(1 / 3),
        "excluded_share": pytest.approx(1 / 3)}


def test_rank_prefers_qualifying_rows_then_falls_back_to_the_argmax():
    good = {"n_eval": 30, "win_rate": 80.0, "expectancy_r": 0.1, "excluded_share": 0.5}
    loud = {"n_eval": 29, "win_rate": 99.0, "expectancy_r": 9.0, "excluded_share": 0.0}
    assert ts._qualifies(good) and not ts._qualifies(loud)
    assert [k for k, _ in ts._rank([("loud", loud), ("good", good)])] == ["good"]
    unscored = dict(loud, expectancy_r=None)
    assert [k for k, _ in ts._rank([("b", unscored), ("a", loud)])] == ["a", "b"]


def test_rank_keeps_grid_order_on_ties():
    s = {"n_eval": 1, "win_rate": 100.0, "expectancy_r": 0.5, "excluded_share": 0.0}
    assert [k for k, _ in ts._rank([(0, s), (1, dict(s)), (2, dict(s))])] == [0, 1, 2]


# --- guards ---------------------------------------------------------------------------

def _ns(exit_model):
    return SimpleNamespace(exit_model=exit_model, scale_out=False)


def test_v1_guards_are_a_no_op():
    ts._instrument_guards(_ns("v1"), V1)


def test_v2_refuses_the_v1_exit_model(live_flags_off):
    with pytest.raises(SystemExit, match="needs exit_model='v2'"):
        ts._instrument_guards(_ns("v1"), V2)


def test_v2_refuses_a_live_state_flag(monkeypatch, live_flags_off):
    monkeypatch.setattr(config, backtest._LIVE_STATE_FLAGS[0], True, raising=False)
    with pytest.raises(SystemExit, match="refuses lookahead"):
        ts._instrument_guards(_ns("v2"), V2)


def test_v2_accepts_exit_model_v2(live_flags_off):
    ts._instrument_guards(_ns("v2"), V2)


# --- universe ---------------------------------------------------------------------------

def test_v1_loads_the_watchlist_exactly_as_today(monkeypatch):
    monkeypatch.setattr(ts, "load_watchlist", lambda: ["BBB", "AAA", "CCC"])
    monkeypatch.setattr(ts, "load_cached", lambda t: None if t == "CCC" else t.lower())
    assert ts._load_universe(V1) == ({"AAA": "aaa", "BBB": "bbb"}, {})


def test_v2_loads_the_contract_pit_universe_with_spans(monkeypatch):
    seen, pits = {}, []

    def tickers(universe):
        seen["tickers"] = universe
        return ["AAA", "BBB", "CCC", "DDD"]

    def membership(universe, symbols):
        seen["membership"] = (universe, list(symbols))
        return {"AAA": ALWAYS, "CCC": ALWAYS}

    def exclusion(df, ticker, pit):
        pits.append(pit)
        return ("data_quality", "bad bars") if ticker == "CCC" else None

    monkeypatch.setattr(ts.rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(ts.rbr, "_membership_for_run", membership)
    monkeypatch.setattr(ts.rbr, "_exclusion_reason", exclusion)
    monkeypatch.setattr(ts, "load_cached", lambda t: None if t == "DDD" else t)
    frames, spans = ts._load_universe(V2)
    assert seen == {"tickers": "sp500_pit",
                    "membership": ("sp500_pit", ["AAA", "BBB", "CCC", "DDD"])}
    assert pits == [True, True, True]          # the PIT branch: no non-causal floor
    assert frames == {"AAA": "AAA", "BBB": "BBB"}
    assert spans == {"AAA": ALWAYS, "BBB": []}  # no membership row = never a member


# --- _v2_trades -----------------------------------------------------------------------------

def test_v2_trades_run_the_v2_instrument_over_the_research_span(monkeypatch):
    calls = []

    def fake(ticker, df, strategy, hk, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(trades=[_trade("2009-12-31"), _trade("2010-01-04"),
                                       _trade("2025-12-31"), _trade("2026-01-02")])

    monkeypatch.setattr(ts.bt, "run_backtest", fake)
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    rows = ts._v2_trades("RSI", {"AAA": _frame()}, {"AAA": ALWAYS}, V2, True)
    assert [(tk, t.entry_date) for tk, t in rows] == [("AAA", "2010-01-04"), ("AAA", "2025-12-31")]
    assert calls == [{"one_at_a_time": True, "exit_model": "v2", "scale_out": True,
                      "tp2_mode": "none", "instrument": V2}]


def test_v2_trades_gate_membership_and_the_floor_on_the_signal_day(monkeypatch):
    signal_inside = SimpleNamespace(entry_date="2021-03-01", signal_date="2021-02-26",
                                    exit_date="2021-03-05", outcome="win", r_multiple=1.0)
    entry_inside = SimpleNamespace(entry_date="2021-02-01", signal_date="2021-01-29",
                                   exit_date="2021-02-05", outcome="win", r_multiple=1.0)
    monkeypatch.setattr(ts.bt, "run_backtest",
                        lambda *a, **k: SimpleNamespace(trades=[signal_inside, entry_inside]))
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    spans = {"AAA": [("2021-02-01", "2021-03-01")]}        # [start, end)
    rows = ts._v2_trades("RSI", {"AAA": _frame()}, spans, V2, False)
    assert [t for _, t in rows] == [signal_inside]
    assert ts._v2_trades("RSI", {"AAA": _frame(volume=1_000)}, {"AAA": ALWAYS}, V2, False) == []


# --- out of fold ------------------------------------------------------------------------------

def test_out_of_fold_selects_per_fold_on_train_trades_only():
    """FADES leads STEADY in train while (12 - m) / (4 + m) > 0.5, i.e. for the
    folds 2014..2020 (m = 0..6 earlier test years in train); STEADY after."""
    oof = ts._out_of_fold({0: _rows(STEADY), 1: _rows(FADES)}, V2)
    assert oof.choices == tuple((y, 1 if y <= 2020 else 0) for y in range(2014, 2026))
    assert [t.r_multiple for t in oof.trades] == [-1.0] * 7 + [0.5] * 5


def test_nothing_tuned_skips_the_folds():
    rows = _rows(FADES)
    oof = ts._out_of_fold({0: rows}, V2)
    assert oof.choices == ()
    assert oof.trades == [t for _, t in rows]


def test_fold_report_is_empty_and_silent_under_v1(capsys):
    assert ts._fold_report([], {}, V1) == {}
    assert capsys.readouterr().out == ""


# --- main, end to end on a stubbed engine ------------------------------------------------------

GRID = {0.75: STEADY, 1.0: FADES, 1.5: LOSES}     # MACD's built-in ext_atr grid


@pytest.fixture
def harness(monkeypatch, tmp_path, live_flags_off):
    calls, frame = [], _frame()

    def fake_run_backtest(ticker, df, strategy, hk, **kwargs):
        calls.append(dict(kwargs, ticker=ticker))
        r_by_year = GRID[ts.ef.DEFAULT_PARAMS[strategy]["ext_atr"]]
        return SimpleNamespace(trades=[_trade(f"{y}-03-02", r_by_year(y), exit_=f"{y}-03-10")
                                       for y in range(2010, 2026)])

    monkeypatch.setitem(ts.PARAM_GRID, "MACD", ts.PARAM_GRID["MACD"])   # --grid rewrites it
    monkeypatch.setattr(ts.bt, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(ts, "LEGACY_HORIZONS", ("3m",))
    monkeypatch.setattr(ts, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(ts, "load_cached", lambda ticker: frame)
    monkeypatch.setattr(ts.rbr, "_tickers_for_run", lambda universe: ["AAA", "BBB"])
    monkeypatch.setattr(ts.rbr, "_membership_for_run",
                        lambda universe, tickers: {t: ALWAYS for t in tickers})
    monkeypatch.setattr(ts.rbr, "_exclusion_reason", lambda df, ticker, pit: None)

    def run(*argv):
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["tune_strategy.py", "--strategy", "MACD",
                                          "--json", str(out), *argv])
        ts.main()
        return json.loads(out.read_text(encoding="utf-8"))

    return SimpleNamespace(run=run, calls=calls)


V2_FLAGS = ("--instrument", "v2", "--exit-model", "v2")


def test_v1_payload_and_output_are_todays(harness, capsys):
    payload = harness.run()
    assert list(payload) == ["strategy", "gate", "grid", "best"]
    assert len(harness.calls) == 3                    # 3 configs x 1 watchlist ticker x 1 horizon
    assert all("instrument" not in call and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["grid"][0]["n_eval"] == 4          # TRAIN 2020..2023 only
    out = capsys.readouterr().out
    assert "1 tickers loaded from cache" in out
    assert "instrument" not in out and "out-of-fold" not in out


def test_explicit_v1_is_identical_to_the_default(harness, capsys):
    default = harness.run()
    default_out = capsys.readouterr().out
    assert harness.run("--instrument", "v1") == default
    assert capsys.readouterr().out == default_out


def test_v2_selects_per_fold_and_reports_pooled_out_of_fold_expectancy(harness, capsys):
    payload = harness.run(*V2_FLAGS)
    assert len(harness.calls) == 6                    # 3 configs x 2 PIT tickers x 1 horizon
    assert all(call["instrument"] is V2 and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["instrument"] == "v2"
    assert payload["research_span"] == ["2010-01-01", "2025-12-31"]
    assert payload["grid"][0]["n_eval"] == 32         # research span: 16 years x 2 tickers
    assert payload["best"]["params"] == {"ext_atr": 0.75}
    oof = payload["out_of_fold"]
    assert [f["test_year"] for f in oof["folds"]] == list(range(2014, 2026))
    assert [f["params"]["ext_atr"] for f in oof["folds"]] == [1.0] * 7 + [0.75] * 5
    assert oof["n_eval"] == 24
    assert oof["expectancy_r"] == -0.375
    assert payload["watchlist_slice"] == {"status": "thin", "n": 12, "expectancy_r": -0.375}
    out = capsys.readouterr().out
    assert "Pooled out-of-fold: N=24" in out
    assert "-> THIN" in out


def test_v2_with_nothing_tuned_reports_the_research_span_as_out_of_fold(harness):
    payload = harness.run(*V2_FLAGS, "--grid", "ext_atr=1.0")
    assert payload["out_of_fold"]["folds"] == []
    assert payload["out_of_fold"]["n_eval"] == 32
    assert payload["out_of_fold"]["expectancy_r"] == 0.0


def test_v2_with_the_default_exit_model_exits_before_any_ticker(harness):
    with pytest.raises(SystemExit, match="needs exit_model='v2'"):
        harness.run("--instrument", "v2")
    assert harness.calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_tune_strategy_instrument.py`
Expected: FAIL. `AttributeError: module 'tune_strategy' has no attribute 'rbr'` / `'_stats'` / `'_rank'` (and the other new helpers); the `main` tests fail with `unrecognized arguments: --instrument`.

- [ ] **Step 3: Implement**

All edits are in `$WT/scripts/backtest/tune_strategy.py`.

1. Module docstring: append this paragraph before the closing `"""`:

```text

--instrument v2 (v158): every config runs over the contract's research span on
its point-in-time universe (membership and a causal liquidity floor checked on
the signal day). The grid table and "best" are in-sample; the verdict
statistic is the pooled out-of-fold ExpR of a per-fold selection made on each
fold's purged train trades only, reported with its watchlist slice. Needs
--exit-model v2.
```

2. Path and imports. After `sys.path.insert(0, str(ROOT / "scripts" / "data"))` add:

```python
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
```

After `from fetch_backtest_data import load_cached, load_watchlist` add:

```python
import run_backtest_range as rbr
```

After the WC7 line `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli
from swingbot.core.backtesting.instrument import folds as instrument_folds
from swingbot.core.backtesting.instrument import universe_gate
```

3. Replace the tail of `run_config`, from its `trades.extend(...)` line to the end of the function:

```python
            trades.extend(t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1])
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))
    return {
        "n_eval": len(ev),
        "win_rate": wins / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }
```

with the following (the `run_config` tail, then every new helper; they sit between `run_config` and `_parse_grid_value`):

```python
            trades.extend(t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1])
    return _stats(trades)


def _stats(trades) -> dict:
    """The tuner's four numbers over one trade list: run_config's tail, moved
    here unchanged so v2's per-fold selection scores trades exactly as v1 does."""
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))
    return {
        "n_eval": len(ev),
        "win_rate": wins / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }


def _qualifies(stats) -> bool:
    """The selection rule's gate (module docstring): WR>=80, ExpR>0, N>=30, excl<=50%."""
    return (stats["n_eval"] >= 30 and (stats["win_rate"] or 0) >= 80
            and (stats["expectancy_r"] or 0) > 0 and stats["excluded_share"] <= 0.5)


def _rank(rows) -> list:
    """(key, stats) rows best first: the qualifying rows by ExpR, else every row
    (the UNGATED full-grid argmax). sorted() is stable, so ties keep grid order."""
    qualifying = [row for row in rows if _qualifies(row[1])]
    return sorted(qualifying or rows, key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)


def _instrument_guards(args, spec) -> None:
    """Under v2, check run_backtest's v2 refusals ONCE, before any ticker loads:
    run_config-style loops swallow every per-run exception, so a refusal there
    would silently empty the grid. v2 runs tp2_mode="none" (TP2 built as live).
    Under v1: no-op."""
    if spec.version == "v1":
        return
    try:
        bt._uses_live_constructor(spec, args.exit_model, "none")
    except ValueError as exc:
        raise SystemExit(f"--instrument {spec.version}: {exc}") from None


def _load_universe(spec) -> tuple[dict, dict]:
    """(frames, spans). v1: today's watchlist frames, no spans. v2: the
    contract's point-in-time universe through run_backtest_range's seams, minus
    missing frames and frames failing its data-quality checks (the non-causal
    liquidity floor is skipped for PIT runs there), with membership spans."""
    if spec.version == "v1":
        return {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}, {}
    tickers = rbr._tickers_for_run(spec.universe)
    membership = rbr._membership_for_run(spec.universe, tickers)
    frames, spans = {}, {}
    for ticker in tickers:
        df = load_cached(ticker)
        if df is None or rbr._exclusion_reason(df, ticker, pit=membership is not None):
            continue
        frames[ticker], spans[ticker] = df, rbr._spans_for(membership, ticker)
    return frames, spans


def _v2_trades(strategy, frames, spans, spec, scale_out) -> list:
    """(ticker, trade) rows of the current config under v2: entry date inside
    the research span, then PIT membership and the causal liquidity floor on
    the SIGNAL day (universe_gate, v136 section 1)."""
    date_from, date_to = instrument_cli.window_for(spec, "train")
    rows = []
    for ticker, df in frames.items():
        for hk in LEGACY_HORIZONS:
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model="v2", scale_out=scale_out, tp2_mode="none",
                                    instrument=spec)
            except Exception:
                continue
            kept = universe_gate.eligible_trades(rbr.window_trades(s, date_from, date_to),
                                                 spans.get(ticker), df, spec.liquidity_floor)
            rows.extend((ticker, t) for t in kept)
    return rows


def _evaluate(strategy, universe, args, spec) -> tuple[dict, list | None]:
    """(stats, rows) for the current DEFAULT_PARAMS. v1: run_config exactly as
    today and no rows kept. v2: research-span stats and the (ticker, trade) rows."""
    frames, spans = universe
    if spec.version == "v1":
        return run_config(strategy, frames, exit_model=args.exit_model,
                          scale_out=args.scale_out), None
    rows = _v2_trades(strategy, frames, spans, spec, args.scale_out)
    return _stats([t for _, t in rows]), rows


def _fold_select(train) -> int:
    """One fold's config index, chosen on that fold's train trades only, by the
    same rule the in-sample ranking uses."""
    return _rank([(i, _stats(trades)) for i, trades in sorted(train.items())])[0][0]


def _out_of_fold(rows_by_config, spec):
    """Per-fold selection and the pooled out-of-fold trades (v136 section 1).
    One config means nothing was tuned: its research-span trades are its
    out-of-fold trades and the folds are skipped. The tuner pools every
    horizon, so the embargo is the contract's global maximum (decision 2)."""
    trades_by_config = {i: [t for _, t in rows] for i, rows in rows_by_config.items()}
    if len(trades_by_config) == 1:
        (only,) = trades_by_config.values()
        return instrument_folds.OutOfFold(choices=(), trades=only)
    return instrument_folds.out_of_fold(trades_by_config, instrument_folds.anchored_folds(spec),
                                        _fold_select, embargo_days=spec.embargo_days,
                                        purge=spec.purge)


def _watchlist_slice(trades, rows_by_config) -> dict:
    """The out-of-fold pool's watchlist slice and its verdict (v136 section 1)."""
    owner = {id(t): ticker for rows in rows_by_config.values() for ticker, t in rows}
    members = set(load_watchlist())
    stats = _stats([t for t in trades if owner[id(t)] in members])
    verdict = universe_gate.watchlist_slice_verdict(stats["n_eval"], stats["expectancy_r"])
    return {"status": verdict.status, "n": verdict.n, "expectancy_r": verdict.expectancy_r}


def _fmt(value, fmt: str) -> str:
    return "n/a" if value is None else format(value, fmt)


def _fold_report(rows, rows_by_config, spec) -> dict:
    """Print the v2 verdict block and return its JSON keys. v1: {} and silent,
    so v1's stdout and JSON stay byte-identical."""
    if spec.version == "v1":
        return {}
    oof = _out_of_fold(rows_by_config, spec)
    stats = _stats(oof.trades)
    folds = [{"test_year": year, "params": rows[i][0]} for year, i in oof.choices]
    slice_ = _watchlist_slice(oof.trades, rows_by_config)
    start, end = spec.research_span
    print(f"\n== instrument {spec.version}: research span {start}..{end}, universe "
          f"{spec.universe}; PIT membership and the causal liquidity floor on the signal day")
    print("The grid and 'best' above are in-sample over the research span; the verdict "
          "statistic is the pooled out-of-fold ExpR below.")
    if not folds:
        print("Nothing tuned (one config): its research-span trades are its out-of-fold trades.")
    for fold in folds:
        print(f"  fold {fold['test_year']}: selected on train data only -> {fold['params']}")
    print(f"Pooled out-of-fold: N={stats['n_eval']} WR={_fmt(stats['win_rate'], '.1f')} "
          f"ExpR={_fmt(stats['expectancy_r'], '+.3f')} "
          f"(purge={spec.purge}, embargo={spec.embargo_days}d)")
    print(f"Watchlist slice of the out-of-fold pool: N={slice_['n']} "
          f"ExpR={_fmt(slice_['expectancy_r'], '+.3f')} -> {slice_['status'].upper()} "
          f"(ExpR < 0 with N >= {universe_gate.WATCHLIST_SLICE_MIN_N} fails the verdict; "
          f"fewer is THIN)")
    return {"instrument": spec.version, "research_span": [start, end],
            "out_of_fold": {"folds": folds, **stats}, "watchlist_slice": slice_}
```

4. In `main`:

a. Replace

```python
    ap.add_argument("--json", type=str, default=None,
                    help="Write results (grid + best) as JSON to this path.")
    args = ap.parse_args()
```

with

```python
    ap.add_argument("--json", type=str, default=None,
                    help="Write results (grid + best) as JSON to this path.")
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args()
    instrument = instrument_cli.spec_from_args(args)
    _instrument_guards(args, instrument)
```

(The local is named `instrument`, not `spec`: `main` already uses `spec` as the `--grid` loop variable.)

b. Replace

```python
    dfs = {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}
    print(f"{len(dfs)} tickers loaded from cache")
```

with

```python
    universe = _load_universe(instrument)
    print(f"{len(universe[0])} tickers loaded from cache")
```

c. Replace `    rows = []` (directly above `    try:`) with `    rows, rows_by_config = [], {}`, and inside the grid loop replace

```python
            stats = run_config(strategy, dfs, exit_model=args.exit_model,
                               scale_out=args.scale_out)
            rows.append((params, stats))
```

with

```python
            stats, trade_rows = _evaluate(strategy, universe, args, instrument)
            rows_by_config[len(rows)] = trade_rows
            rows.append((params, stats))
```

d. Replace

```python
    qualifying = [(p, s) for p, s in rows
                  if s["n_eval"] >= 30 and (s["win_rate"] or 0) >= 80
                  and (s["expectancy_r"] or 0) > 0 and s["excluded_share"] <= 0.5]
```

with `    qualifying = [(p, s) for p, s in rows if _qualifies(s)]`, and replace

```python
    ranked = sorted(qualifying or rows,
                    key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)
```

with `    ranked = _rank(rows)`.

e. Directly before `    if args.json:` insert

```python
    fold_json = _fold_report(rows, rows_by_config, instrument)

```

and in the `payload` dict, after the `"best": ...` entry, add the line `            **fold_json,` (under v1 it is `{}`, so the dumped JSON is byte-identical).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_tune_strategy_instrument.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity went down; v1 consumers still pass**

Run: `python -m radon cc -s -n C $WT/scripts/backtest/tune_strategy.py`
Expected: exactly two lines, `main - C (20)` (was D 29) and `_stats - C (11)` (the block moved out of `run_config`, which no longer appears). If `main` is at or above 29, a branch was inlined instead of living in a helper: stop and fix.

Run each:

```bash
python $WT/scripts/dev/testrun.py file tests/scripts/test_tune_strategy.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_tuner_gate_loudness.py
python $WT/scripts/dev/testrun.py file tests/admin/test_jobs.py
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/
```

Expected: every run PASS, `0 failed`, `0 xfailed`.

Smoke the flag without a cache (none exists on the dev machine):

```bash
python $WT/scripts/backtest/tune_strategy.py --help | grep -A1 -- "--instrument"
python $WT/scripts/backtest/tune_strategy.py --strategy MACD --instrument v2; echo "exit=$?"
```

Expected: the help shows `--instrument {v1,v2}`; the second command prints `--instrument v2: instrument v2 needs exit_model='v2'; ...` and `exit=1` before any ticker loads.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/backtest/tune_strategy.py tests/scripts/test_tune_strategy_instrument.py
git -C $WT commit -m "feat(backtest): v158 WC9 tune_strategy --instrument v2 selects per purged fold and reports pooled out-of-fold ExpR"
git -C /home/user/Discord-Bot status --short
```

### Task WC10: `--instrument` on the remaining live scripts

**Model:** sonnet — the same two-line flag-and-guard insertion in ten scripts plus one behaviour-preserving wrap of `ablation.py`, proven by one parametrised test.

**Files:**
- Modify: `scripts/backtest/tune_exit_v2.py`
- Modify: `scripts/backtest/tune_confluence_gates.py`
- Modify: `scripts/backtest/measure_arms.py`
- Modify: `scripts/backtest/wf_run.py`
- Modify: `scripts/backtest/wf_components.py`
- Modify: `scripts/backtest/permutation_test.py`
- Modify: `scripts/backtest/quarterly_revalidation.py`
- Modify: `scripts/backtest/emit_cohort_registry.py`
- Modify: `scripts/backtest/ablation.py`
- Modify: `scripts/backtest/measure_strategy_arm.py`
- Create: `tests/scripts/test_instrument_flag_scripts.py`

**Why:** spec rule 2: "Every backtest script takes `--instrument v1|v2`." These ten are the live scripts whose v2 path a later phase owns (index Global Constraints, "Out of scope"). Each one now parses `--instrument` (default `v1`) and calls `cli.require_v1` right after parsing: under v1 that call is silent and the script runs exactly as before; under v2 it exits before any work, naming the script and the phase that wires it. WC11's census then fails if any live script stops taking the flag.

**Owners named in the v2 refusals** (index "Out of scope" assigns these paths to phases 5 and 6):

| Script | Owner string | Why that phase |
|---|---|---|
| `tune_exit_v2.py` | `phase 6 (cutover: v2 exit tuning on the purged folds)` | Its v2 exits need v157's fills and costs; v2 tuning runs on the folds |
| `tune_confluence_gates.py` | `phase 5 (scan replay under v2)` | It replays the confluence scenarios (`replay_scenarios`), the scan replay phase 5 builds |
| `measure_arms.py` | `phase 5 (v2 stage table)` | `arms/windows.STAGES` stays v1-only here (the same owner WC6's test names) |
| `wf_run.py`, `wf_components.py`, `permutation_test.py`, `quarterly_revalidation.py`, `ablation.py`, `measure_strategy_arm.py` | `phase 6 (cutover: walk-forward on the v2 folds)` | All run `backtest_wf`'s v1 `ANCHORED_FOLDS` (2018-06 machinery, out of scope here) |
| `emit_cohort_registry.py` | `phase 6 (registry instrument_version column)` | Same owner WC8 names for `--emit-registry` |

**Scope notes:**
- `tune_exit_v2.py`, `tune_confluence_gates.py` and `ablation.py` have no argparse today. `tune_exit_v2` reads `sys.argv[1:]` as an optional strategy list; it becomes a `strategies` positional (`nargs="*"`), so `python scripts/backtest/tune_exit_v2.py RSI MACD` behaves as before. `ablation.py` runs at module level; its body moves verbatim into `main(argv=None)`.
- In `tune_exit_v2.main` the guard runs **before** `plan_engine.EXIT_V2_PARAMS.clear()`, so a refused v2 run mutates no global.
- `quarterly_revalidation.py` launches `wf_run.py` and `permutation_test.py` as subprocesses without the flag, so they run v1 (the default), as today.
- No `run_backtest` call changes and no window changes; each `main`'s complexity is unchanged (straight-line calls only).
- WC7 already put `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument` in `tune_exit_v2.py` and `tune_confluence_gates.py`; the `cli` import goes directly after it.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scripts/test_instrument_flag_scripts.py`:

```python
"""v158 WC10: every live backtest script takes --instrument (v136 rule 2).

v1, the default, runs exactly as before: the only new step is the guard, which
is silent under v1. v2 exits before any work, naming the script and the phase
that wires its v2 path (cli.require_v1)."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.backtesting.instrument import cli

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

WALK_FORWARD = "phase 6 (cutover: walk-forward on the v2 folds)"

# script module -> (the argv it requires besides --instrument, the owner its v2 refusal names)
SCRIPTS = {
    "tune_exit_v2": ([], "phase 6 (cutover: v2 exit tuning on the purged folds)"),
    "tune_confluence_gates": ([], "phase 5 (scan replay under v2)"),
    "measure_arms": (["--knob", "X=1", "--stage", "pilot", "--out", "arms.json"],
                     "phase 5 (v2 stage table)"),
    "wf_run": ([], WALK_FORWARD),
    "wf_components": ([], WALK_FORWARD),
    "permutation_test": ([], WALK_FORWARD),
    "quarterly_revalidation": ([], WALK_FORWARD),
    "emit_cohort_registry": (["--backtest", "replay.json"],
                             "phase 6 (registry instrument_version column)"),
    "ablation": ([], WALK_FORWARD),
    "measure_strategy_arm": (["--strategy", "RSI", "--component-json", '{"X": 1}',
                              "--out", "arms.json"], WALK_FORWARD),
}


class _Reached(Exception):
    """Raised by the spy standing in for cli.require_v1: main got that far."""


def _main(monkeypatch, module, *extra):
    mod = importlib.import_module(module)
    monkeypatch.setattr(sys, "argv", [f"{module}.py", *SCRIPTS[module][0], *extra])
    return mod.main()


@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_help_lists_the_flag(module, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, module, "--help")
    assert exc.value.code == 0
    assert "--instrument {v1,v2}" in capsys.readouterr().out


@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_v2_exits_naming_the_script_and_the_owning_phase(module, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, module, "--instrument", "v2")
    message = str(exc.value)
    assert f"{module}.py: --instrument v2 is not wired yet" in message
    assert SCRIPTS[module][1] in message


@pytest.mark.parametrize("extra", [(), ("--instrument", "v1")], ids=["default", "explicit-v1"])
@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_v1_is_handed_to_the_guard_right_after_parsing(module, extra, monkeypatch):
    """The spy stops main at the guard, so nothing after it ran; under v1 (the
    default and explicit) the guard receives v1, and the real guard is silent
    for v1 (test_instrument_cli.py)."""
    seen = []

    def spy(spec, script, owner):
        seen.append((spec.version, script, owner))
        raise _Reached

    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "instrument_cli", SimpleNamespace(
        add_instrument_arg=cli.add_instrument_arg, spec_from_args=cli.spec_from_args,
        require_v1=spy))
    with pytest.raises(_Reached):
        _main(monkeypatch, module, *extra)
    assert seen == [("v1", f"{module}.py", SCRIPTS[module][1])]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_instrument_flag_scripts.py`
Expected: FAIL. No help text lists `--instrument` (`ablation` has no `main` at all); the v2 tests fail on argparse's `unrecognized arguments: --instrument` (exit code 2, not the refusal); the spy tests fail with `AttributeError: ... has no attribute 'instrument_cli'`.

- [ ] **Step 3: Add the flag and the guard**

The guard line is the same in every script: `instrument_cli.require_v1(instrument_cli.spec_from_args(args), "<script>.py", "<owner>")`, placed directly after `parse_args`. Edits, file by file:

1. `$WT/scripts/backtest/tune_exit_v2.py`.

   Before the line `import itertools` add:

```python
import argparse
```

   After the line `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli
```

   Replace

```python
def main():
    # The grid explores
```

   with

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("strategies", nargs="*",
                    help="optional strategy filter (operational: run the grid in "
                         "per-strategy chunks); default every strategy")
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "tune_exit_v2.py",
                              "phase 6 (cutover: v2 exit tuning on the purged folds)")
    # The grid explores
```

   Replace

```python
    strategies = sys.argv[1:] or list(ALL_STRATEGIES)
```

   with

```python
    strategies = args.strategies or list(ALL_STRATEGIES)
```

2. `$WT/scripts/backtest/tune_confluence_gates.py`.

   Before the line `import itertools` add:

```python
import argparse
```

   After the line `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli
```

   Replace

```python
def main():
    all_paths
```

   with

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "tune_confluence_gates.py",
                              "phase 5 (scan replay under v2)")
    all_paths
```

3. `$WT/scripts/backtest/measure_arms.py`.

   After the line `from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    parser.add_argument("--preregistration", type=Path, default=None)
    args = parser.parse_args(argv)
```

   with

```python
    parser.add_argument("--preregistration", type=Path, default=None)
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_arms.py",
                              "phase 5 (v2 stage table)")
```

4. `$WT/scripts/backtest/wf_run.py`.

   Replace

```python
    portfolio_replay, run_folds,
)
```

   with

```python
    portfolio_replay, run_folds,
)
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
                        "pass the same path you're appending results into.")
    args = p.parse_args()
```

   with

```python
                        "pass the same path you're appending results into.")
    instrument_cli.add_instrument_arg(p)
    args = p.parse_args()
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "wf_run.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
```

5. `$WT/scripts/backtest/wf_components.py`.

   After the line `from swingbot.core.marketdata.watchlist import load_watchlist  # noqa: E402` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    ap.add_argument("--out", default="docs/superpowers/results/2026-07-26-edge-folds.md")
    args = ap.parse_args()
```

   with

```python
    ap.add_argument("--out", default="docs/superpowers/results/2026-07-26-edge-folds.md")
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args()
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "wf_components.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
```

6. `$WT/scripts/backtest/permutation_test.py`.

   Replace

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
```

   with

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    p.add_argument("--seed", type=int, default=42)
    return p
```

   with

```python
    p.add_argument("--seed", type=int, default=42)
    instrument_cli.add_instrument_arg(p)
    return p
```

   Replace

```python
    args = _parser().parse_args(argv)
```

   with

```python
    args = _parser().parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "permutation_test.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
```

7. `$WT/scripts/backtest/quarterly_revalidation.py`.

   Replace

```python
sys.path.insert(0, str(ROOT))
```

   with

```python
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    p.add_argument("--permutation-n", type=int, default=200)
    args = p.parse_args()
```

   with

```python
    p.add_argument("--permutation-n", type=int, default=200)
    instrument_cli.add_instrument_arg(p)
    args = p.parse_args()
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "quarterly_revalidation.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
```

8. `$WT/scripts/backtest/emit_cohort_registry.py`.

   After the line `from swingbot.core.market.session import now_et  # noqa: E402` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    parser.add_argument("--out", default="swingbot/core/backtesting/cohort_registry.json")
    args = parser.parse_args()
```

   with

```python
    parser.add_argument("--out", default="swingbot/core/backtesting/cohort_registry.json")
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args()
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "emit_cohort_registry.py",
                              "phase 6 (registry instrument_version column)")
```

9. `$WT/scripts/backtest/measure_strategy_arm.py`.

   After the line `from swingbot.core.marketdata.universe import liquidity_ok  # noqa: E402` add:

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
```

   Replace

```python
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
```

   with

```python
    ap.add_argument("--out", required=True)
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args()
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_strategy_arm.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
```

10. `$WT/scripts/backtest/ablation.py`: today all its work runs at module level under `if __name__ == "__main__":`, so there is nowhere to parse a flag. Replace the whole file with the version below; the body of `main` is the old `__main__` block verbatim, indented one level, plus `return 0` (the exit status stays 0).

```python
# scripts/backtest/ablation.py
"""Leave-one-out ablation over the adopted component set.
Run: python scripts/backtest/ablation.py"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.backtesting.backtest_wf import run_folds  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402

ADOPTED_PATH = "docs/superpowers/results/adopted_components.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    instrument_cli.add_instrument_arg(ap)
    args = ap.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "ablation.py",
                              "phase 6 (cutover: walk-forward on the v2 folds)")
    with open(ADOPTED_PATH, encoding="utf-8") as f:
        adopted: dict = json.load(f)          # {"REGIME_GATES_ENABLED": true, ...}

    full = run_folds(adopted)
    print(f"full system pooled Δ: {full['pooled_delta_expectancy_r']:+.4f}R")
    rows = []
    for key in adopted:
        subset = {k: v for k, v in adopted.items() if k != key}
        r = run_folds(subset)
        contribution = full["pooled_delta_expectancy_r"] - r["pooled_delta_expectancy_r"]
        rows.append((key, contribution))
        print(f"without {key:<32} contribution {contribution:+.4f}R")
    rows.sort(key=lambda x: x[1])
    weak = [k for k, c in rows if c < 0.01]
    print("\nremoval candidates (<0.01R):", weak or "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_instrument_flag_scripts.py`
Expected: PASS, `0 failed` (40 tests: 10 help, 10 v2 refusals, 20 v1 spy cases).

- [ ] **Step 5: Existing consumers pass and complexity is unchanged**

Run each:

```bash
python $WT/scripts/dev/testrun.py file tests/scripts/test_wf_run.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_quarterly_revalidation.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_emit_cohort_registry.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_arms.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_measure_strategy_arm.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_wf_engine.py
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/
```

Expected: every run PASS, `0 failed`, `0 xfailed`.

Run: `python -m radon cc -s -n C $WT/scripts/backtest/{tune_exit_v2,tune_confluence_gates,measure_arms,wf_run,wf_components,permutation_test,quarterly_revalidation,emit_cohort_registry,ablation,measure_strategy_arm}.py`
Expected: exactly the legacy lines, unchanged: `tune_exit_v2.main` C 15, `tune_exit_v2._pool` C 13, `tune_confluence_gates.main` C 16, `measure_arms.main` C 14, `wf_run.main` C 19, `wf_components._collect_leg` C 11. Nothing else.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/backtest/tune_exit_v2.py scripts/backtest/tune_confluence_gates.py scripts/backtest/measure_arms.py scripts/backtest/wf_run.py scripts/backtest/wf_components.py scripts/backtest/permutation_test.py scripts/backtest/quarterly_revalidation.py scripts/backtest/emit_cohort_registry.py scripts/backtest/ablation.py scripts/backtest/measure_strategy_arm.py tests/scripts/test_instrument_flag_scripts.py
git -C $WT commit -m "feat(backtest): v158 WC10 --instrument on every remaining live script; v2 refuses naming its phase"
git -C /home/user/Discord-Bot status --short
```

### Task WC11: Date-literal guard and flag census

**Model:** sonnet — one AST-walking test file with explicit allow-lists, modelled on `test_one_constructor_guard.py`; no production code changes expected.

**Files:**
- Create: `tests/backtesting/instrument/test_date_literal_guard.py`

**Why:** spec rule 2: "A guard test fails on a date literal under `scripts/backtest/` (an allow-list covers closed, historical scripts that must keep reproducing their committed results)", and spec "Testing": "date-literal guard (phase 3)". Partner decision 3: the guard also catches year-only constants (`range(2013, 2026)`, tuples of year strings), and closed scripts stay v1-only without the flag. The same file runs the census: every script that is neither closed (`ALLOW`) nor a non-replay utility (`NO_REPLAY`) must call `cli.add_instrument_arg`.

**What it flags:** a constant outside a docstring that **is** a date or a year: a string fully matching `^(19|20)\d{2}(-\d{2}){0,2}$`, or an int in 2005..2035. It does not flag dates inside longer strings: `wf_components.py`'s `--out` results path and `wf_run.py`'s `--window` help example are not windows. Comments never reach the AST. The int range stops at 2005 so slice bounds like `quarterly_revalidation.py`'s `stderr[-2000:]` stay clear.

**Expected end state** (measured on a scratch tree with WC7–WC10 applied): no live script has a hit, all 12 wired scripts take the flag, and no `ALLOW`/`NO_REPLAY` script does. If the scan surfaces a literal in a live script, replace it with the contract value in that script (a one-line fix inside this task) instead of allow-listing a live script.

- [ ] **Step 1: Write the guard**

Create `$WT/tests/backtesting/instrument/test_date_literal_guard.py`:

```python
"""v158 WC11: the date-literal guard (v136 rule 2, "Scripts never define
dates") and the --instrument census over scripts/backtest/.

A live script holds no date or year literal: its windows come from the
instrument contract. Closed, historical scripts that must keep reproducing
their committed results sit on ALLOW: they stay v1-only and take no flag
(partner decision 3). Utilities that never run a backtest sit on NO_REPLAY and
take no flag. Every other script must take --instrument."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKTEST = ROOT / "scripts" / "backtest"

#: A string constant that IS a date or a year: "2020-01-01", "2020-01", "2021".
DATE_TEXT = re.compile(r"^(19|20)\d{2}(-\d{2}){0,2}$")
#: An int constant that reads as a year, e.g. range(2013, 2026). Slice bounds
#: such as stderr[-2000:] stay below it.
YEARS = range(2005, 2036)

#: Closed, historical scripts (rel path -> why it keeps its own windows).
ALLOW = {
    "scripts/backtest/funnel.py": "v102-v104 funnel; its FOLD_YEARS reproduce those committed results",
    "scripts/backtest/fvg_attribution.py": "v128 FVG attribution; closed pre-registration",
    "scripts/backtest/fvg_select.py": "v128 Stage 0/1 FVG judge; closed pre-registration",
    "scripts/backtest/make_v68_fixture.py": "regenerates v68's committed VALIDATION fixture",
    "scripts/backtest/measure_acceptance_exits.py": "v129 acceptance-exit funnel; closed pre-registration",
    "scripts/backtest/measure_adaptive_trail.py": "v92 hypothesis 1 TRAIN grid; closed",
    "scripts/backtest/measure_adjacent_gate_effect.py": "v33 adjacent-horizon gate measurement; closed",
    "scripts/backtest/measure_alert_density.py": "v51 alert-density measurement; closed, TRAIN-only by its plan",
    "scripts/backtest/measure_armed_entries.py": "v88 armed-entry grid; closed pre-registration",
    "scripts/backtest/measure_avwap_confluence.py": "v35 AVWAP confluence check; closed TRAIN measurement",
    "scripts/backtest/measure_bearish_arms.py": "bearish-arm TRAIN measurement; closed",
    "scripts/backtest/measure_dcb_veto.py": "v68 dead-cat-bounce veto grid; closed TRAIN and VALIDATION shots",
    "scripts/backtest/measure_earnings_blackout.py": "v82 earnings-blackout table; closed pre-registration",
    "scripts/backtest/measure_factor_lift.py": "v32 per-factor lift; closed TRAIN measurement",
    "scripts/backtest/measure_fib_anchor_diagnostic.py": "v124 anchor diagnostic; reproduces v103 on frozen windows",
    "scripts/backtest/measure_fib_confluence.py": "v102 Fibonacci x S/R confluence on the extended cache; closed",
    "scripts/backtest/measure_fib_diagnostic.py": "v101 Fibonacci diagnostic; closed",
    "scripts/backtest/measure_fib_extension.py": "v84 Fibonacci 1.0 extension arms; closed",
    "scripts/backtest/measure_fib_limit.py": "v131 Fibonacci limit; its holdout shot is spent, windows frozen",
    "scripts/backtest/measure_fib_v103.py": "v103/v108 measurement funnel; closed",
    "scripts/backtest/measure_fvg_bullish_diagnostic.py": "v143 FVG bullish diagnostic; its one TRAIN replay is closed",
    "scripts/backtest/measure_rs_gate_effect.py": "v34 relative-strength gate measurement; closed",
    "scripts/backtest/measure_stall_exit.py": "v92 hypothesis 2 stall exit; closed TRAIN comparison",
    "scripts/backtest/measure_structure_arm.py": "v127 structure-break armed entry; closed pre-registration",
    "scripts/backtest/measure_trend_signal_overlap.py": "v33 trend-signal overlap; closed TRAIN measurement",
    "scripts/backtest/measure_v104.py": "v104 measurement; its holdout end is frozen",
    "scripts/backtest/measure_v113.py": "v113 measurement; its holdout end is frozen",
    "scripts/backtest/reversal_ab.py": "reversal-rule A/B on one shared signal set; closed",
    "scripts/backtest/run_confluence_validation.py": "plan Task 41 one-shot confluence VALIDATION run; spent",
    "scripts/backtest/screen_idea.py": "v140 Stage -2 screen; its window is part of the pre-registration",
    "scripts/backtest/v32_factor_correlation.py": "v32 factor correlation; closed TRAIN measurement",
    "scripts/backtest/v32_validation.py": "v32 one-shot VALIDATION run; spent",
}

#: Utilities that run no backtest and choose no window.
NO_REPLAY = {
    "scripts/backtest/compare_backtest_json.py": "diffs two run_backtest_range --json outputs; runs no backtest",
    "scripts/backtest/harvest_select.py": "v123 harvest selection over stamped arm files; runs no backtest",
    "scripts/backtest/validate_component.py": "v100 acceptance funnel over stamped arm files; runs no backtest",
}

#: The live scripts this plan wired (WC8, WC9, WC10).
WIRED = {f"scripts/backtest/{name}.py" for name in (
    "run_backtest_range", "tune_strategy", "tune_exit_v2", "tune_confluence_gates",
    "measure_arms", "wf_run", "wf_components", "permutation_test", "quarterly_revalidation",
    "emit_cohort_registry", "ablation", "measure_strategy_arm")}


def _docstrings(tree) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
    return found


def _is_date(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in YEARS
    return isinstance(value, str) and DATE_TEXT.match(value) is not None


def date_literals(text: str) -> list[tuple[int, object]]:
    """(line, value) of every date or year constant outside docstrings. Comments
    never reach the AST; a date inside a longer string (a results-doc path,
    help prose) is not a window and is not flagged."""
    tree = ast.parse(text)
    skip = _docstrings(tree)
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and id(node) not in skip and _is_date(node.value)]


def takes_instrument_flag(text: str) -> bool:
    """True when the script calls add_instrument_arg (bare or as an attribute)."""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "add_instrument_arg":
                return True
    return False


def _scripts() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(BACKTEST.glob("*.py"))}


def test_the_scanner_flags_iso_dates_year_ranges_and_year_strings():
    source = (
        'TRAIN = ("2020-01-01", "2023-12-31")\n'
        "FOLD_YEARS = tuple(range(2013, 2026))\n"
        'LABELS = ("2021", "2022")\n'
        'MONTH = "2024-06"\n'
    )
    assert {value for _, value in date_literals(source)} == {
        "2020-01-01", "2023-12-31", 2013, 2026, "2021", "2022", "2024-06"}


def test_the_scanner_ignores_docstrings_comments_prose_and_other_numbers():
    source = (
        '"""Window 2020-01-01..2023-12-31; see 2024-01-01."""\n'
        '# TRAIN = ("2020-01-01", "2023-12-31")\n'
        'OUT = "docs/superpowers/results/2026-07-26-edge-folds.md"\n'
        "HELP = \"e.g. '2024-01-01:2025-12-31'\"\n"
        "TAIL = text[-2000:]\n"
        "BARS, PCT, FLAG, OLD = 260, 0.5, True, 1999\n"
        "\n"
        "def f():\n"
        '    """Docstring 2021-01-01."""\n'
        "    return 4096\n"
    )
    assert date_literals(source) == []


def test_no_live_script_holds_a_date_literal():
    offenders = {rel: hits for rel, text in _scripts().items()
                 if rel not in ALLOW and (hits := date_literals(text))}
    assert offenders == {}, ("a live script defines a date: read it from the instrument "
                             "contract (v136 rule 2), or allow-list a closed script with a reason")


def test_every_live_script_takes_the_instrument_flag():
    missing = [rel for rel, text in _scripts().items()
               if rel not in ALLOW and rel not in NO_REPLAY and not takes_instrument_flag(text)]
    assert missing == [], "call instrument.cli.add_instrument_arg (v136 rule 2)"


def test_closed_and_non_replay_scripts_stay_v1_only():
    flagged = [rel for rel, text in _scripts().items()
               if (rel in ALLOW or rel in NO_REPLAY) and takes_instrument_flag(text)]
    assert flagged == []


def test_each_listed_script_exists_with_a_one_line_reason():
    scripts = _scripts()
    for listing in (ALLOW, NO_REPLAY):
        for rel, reason in listing.items():
            assert rel in scripts, f"stale entry: {rel}"
            assert reason.strip() and "\n" not in reason, rel
    assert not set(ALLOW) & set(NO_REPLAY)


def test_no_wired_script_is_listed_away():
    live = {rel for rel in _scripts() if rel not in ALLOW and rel not in NO_REPLAY}
    assert WIRED <= live
```

- [ ] **Step 2: Run it**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`
Expected: PASS, `0 failed` (7 tests). This test is written after WC7–WC10, so it passes on first run. Prove it bites: temporarily put `TRAIN = ("2020-01-01", "2023-12-31")` back into `$WT/scripts/backtest/tune_strategy.py`, re-run, and see `test_no_live_script_holds_a_date_literal` FAIL naming `scripts/backtest/tune_strategy.py`; then delete `instrument_cli.add_instrument_arg(ap)` from `tune_strategy.main` and see `test_every_live_script_takes_the_instrument_flag` FAIL. Restore both with `git -C $WT checkout -- scripts/backtest/tune_strategy.py` and re-run: PASS.

If a live script fails `test_no_live_script_holds_a_date_literal` on the real tree, fix the literal in that script (contract value via `cli.window_for` / `resolve_instrument`), re-run its own test file, and add the script to this task's commit.

- [ ] **Step 3: Commit**

```bash
git -C $WT add tests/backtesting/instrument/test_date_literal_guard.py
git -C $WT commit -m "test(instrument): v158 WC11 date-literal guard and --instrument census over scripts/backtest"
git -C /home/user/Discord-Bot status --short
```

# Phase D: Full suite

### Task WC12: Full suite

**Model:** haiku — runs the one full-suite gate and the closing checks; no code is written.

**Files:** none (verification only; a failure found here is fixed in the task that owns the file, then this task re-runs).

**Why:** CLAUDE.md: "Full suite once per plan, as its final task." Green means `0 failed` and `0 xfailed`.

- [ ] **Step 1: Every task is committed on the branch**

Run: `git -C $WT log --oneline main..HEAD`
Expected: one commit each for WC1, WC2, WC4–WC11, plus WC3's results doc and wrapper commit(s). `git -C $WT status --short` prints nothing.

- [ ] **Step 2: Full suite (dispatch the `test-runner` subagent so the output stays out of context)**

Run: `python $WT/scripts/dev/testrun.py full`
Expected: one verdict line with `0 failed` and `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). This run includes the slow-tier `tests/backtesting/instrument/test_v1_golden.py` (rule 1: v1 byte-identical) and WC11's guard.

- [ ] **Step 3: Complexity over every file this plan touched**

Run:

```bash
python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/ $WT/scripts/data/check_cache_coverage.py $WT/swingbot/admin/jobs.py $WT/swingbot/core/backtesting/arms/windows.py $WT/scripts/backtest/{run_backtest_range,tune_strategy,tune_exit_v2,tune_confluence_gates,measure_arms,wf_run,wf_components,permutation_test,quarterly_revalidation,emit_cohort_registry,ablation,measure_strategy_arm}.py
```

Expected: no line for any `instrument/` module, `check_cache_coverage.py`, `jobs.py` or `windows.py`; for the scripts, only the legacy lines at or below their measured scores (`run_backtest_range.main` below 65, `run_scenario_mode` 19, `pool` 15; `tune_strategy.main` C 20 and `_stats` C 11; `tune_exit_v2.main` 15 and `_pool` 13; `tune_confluence_gates.main` 16; `measure_arms.main` 14; `wf_run.main` 19; `wf_components._collect_leg` 11). Nothing at 15 or above that is new.

- [ ] **Step 4: The main tree is untouched and the plan is on `main`**

Run: `git -C /home/user/Discord-Bot status --short`
Expected: nothing from this plan (the plan files were committed on `main` before implementation).

- [ ] **Step 5: Close-out notes for the controller**

- **WC3's refetch may still be running.** If WC3 returned `WAITING: ext-cache refetch running on Hetzner, log /opt/swing-bot/logs/refetch_ext_2009.log`, WC12 does not wait on it: the suite never reads the real cache (every test builds synthetic frames). WC3 Step 6 (re-check the refetched cache and append `## Refetch` to `docs/superpowers/results/2026-10-10-v158-cache-coverage.md`) stays open and runs in the next session once the log shows `DONE`. Record it under the index's `## Progress` as "WC3 Step 6 pending (refetch running)" so the open step is visible.
- The `bot` minor bump, the plan move to `implemented/` and the worktree removal are `/close-out`'s, after this task is green (index, `## Where to work`). No task edited `VERSION.json`.
- Expect a trivial merge with v157 in `contract.py` / `test_contract.py` if v157 merged first (index Global Constraints); the later-merging plan resolves it and re-runs `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/`.
- No commit in this task: if Steps 2–4 are green, report `DONE` with the verdict line.
