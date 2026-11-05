# v190 — Instrument v3 on the PIT Alpaca store: Implementation Plan, Part 2 — backtest wiring (V190-7..V190-11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V190-8:" -A 300 <this file>`.

**Spec:** [2026-10-24-v190-pit-alpaca-universe-design.md](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Index:** [2026-10-24-v190-pit-alpaca-universe_0-index.md](2026-10-24-v190-pit-alpaca-universe_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Contracts`, `## Review Focus`, `## Parallelisation` and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: `run_backtest_range` applies the integrity report's signal-date cuts and is pinned end to end on a fixture PIT store (V190-7); every instrument branch site is audited for v3 (V190-8); the coverage gate reads the PIT store layout (V190-9); the calibration label and the ledger vocabulary grow additively (V190-10); the funnel refuses v3 (V190-11).

Consumed from Part 1 (exact names in the index's `## Contracts`): `resolve("v3")` with `store="pit"` (V190-1); `history_store.store_root(store=None)`, `PIT`, `safe_symbol` file naming (V190-2); `_integrity.json` shape and `pit_integrity.load_integrity` (V190-3); `training_data.select(name, store, until)`, `active_store()`, `signal_cuts()`, `load_intraday(...)`, provenance keys `store` / `integrity_sha256` (V190-4); `pit_membership.membership_map(universe, symbols, cuts=None)` (V190-5); `fetch_backtest_data.apply_data_source(args)` selecting the PIT store for a spec with `store="pit"` and `require_context_frames()` (V190-6).

All work happens in the worktree `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe`; every path below is relative to it. **Do not commit on `main`.** Each task's last step commits on the worktree branch.

# Phase: backtest wiring (V190-7..V190-11)

### Task V190-7: `run_backtest_range` v3 path, signal cuts, byte-identity pins

**Model:** opus — end-to-end holdout and byte-identity pins across the store, integrity and membership seams; a wrong fixture silently proves nothing.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (`_membership_for_run` only, plus one new helper `_print_signal_cuts` beside it; `main` is F(62) legacy and gains no line)
- Create: `tests/backtest_scripts/test_run_backtest_range_v3.py` (suite `backtest-scripts`; no new directory)

**Interfaces:**
- Consumes: `resolve("v3")` (V190-1); `training_data.select(name, store, until)`, `active_store()`, `signal_cuts() -> dict[str, list[tuple[str, str]]] | None`, `load_intraday(ticker, timeframe, session="rth")`, `provenance_path(out)`, provenance keys `store` / `integrity_sha256` (V190-4); `pit_membership.membership_map(universe, symbols, cuts=None)` (V190-5); `fetch_backtest_data.apply_data_source(args)` selecting `training_data.select("alpaca", "pit", spec.research_end)` for a spec with `store="pit"`, refusing `--data-source yfinance`, and refusing (`SystemExit` naming the symbol) a store missing the regime ticker or an `etfs.json` symbol (V190-6). The `_integrity.json` shape is the index's `## Contracts` block.
- Produces: `_membership_for_run(universe: str | None, tickers: list) -> dict | None` — same signature; under the PIT store it subtracts `training_data.signal_cuts()`; under any other selection it passes `cuts=None` and is byte-identical. `tune_strategy._load_universe` calls it too, so a v3 tuning run inherits the cuts with no change there.

What already holds once Part 1 is in, and what this task adds: ticker frames are cut at `research_end` by `_instrument_frame` (v2 path, unchanged); SPY and the ETF frames are cut because they load through `training_data.load_daily` with V190-4's `until` cut; frame trims apply inside `history_store.load(..., store="pit")` (V190-3). The only code change is the signal-date cut in `_membership_for_run`. The test file pins the whole v3 path end to end on a fixture PIT store, so a later edit to any of those seams fails here.

- [ ] **Step 1: Write the failing test file `tests/backtest_scripts/test_run_backtest_range_v3.py`**

```python
"""v190 V190-7: run_backtest_range --instrument v3 on a fixture PIT store.

Pins (spec §3, §4): v3 reads the PIT store with one frame trim (MON) and one
signal-span cut (AAA) applied; no ticker, context or intraday bar on or after
2026-01-01 is reachable; a v3 run refuses the holdout, yfinance, a missing
context ETF and a missing integrity report before any backtest; v1 and v2 are
byte-identical with a PIT store on disk."""
import hashlib
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

import run_backtest_range as rbr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import asof_context, backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.cli import HOLDOUT_SEALED  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402
from swingbot.core.marketdata.pit_membership import OPEN_END, membership_map  # noqa: E402
from swingbot.core.marketdata.universe import sector_map  # noqa: E402

V3 = resolve("v3")
RESEARCH_END = pd.Timestamp("2025-12-31")
HOLDOUT = pd.Timestamp("2026-01-01")
MEMBERS = ("AAA", "BBB", "MON")
CONTEXT = tuple(sorted({config.MARKET_REGIME_TICKER, *sector_map("etfs")}))
MEMBERSHIP = ("ticker,start_date,end_date\n"
              "AAA,2010-01-04,\n"
              "BBB,2010-01-04,\n"
              "MON,2010-01-04,2018-06-08\n")
CUT = ("2019-03-01", "2019-04-01")   # AAA: a missing run, cut from the signal mask
TRIM_BEFORE = "2018-06-08"           # MON: a reused symbol's bars from here on
DAYS = pd.bdate_range("2016-01-04", "2026-03-31")
#: entry days the stubbed engine returns per ticker. Kept under v3: AAA 02-15
#: and 05-15 (03-15 is inside CUT), BBB 03-15 (the cut is AAA's alone), MON
#: 2017-06-01 (2019-01-15 is after MON left the index) -> n_eval 4.
TRADES = {"AAA": ("2019-02-15", "2019-03-15", "2019-05-15"),
          "BBB": ("2019-03-15",),
          "MON": ("2017-06-01", "2019-01-15")}
V2_KNOBS = ("--exit-model", "v2", "--tp2", "none")
V3_FLAGS = ("--instrument", "v3", *V2_KNOBS)


def _trade(entry):
    return BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                         stop_loss=48.0, take_profit=54.0, outcome="win", exit_price=54.0,
                         return_pct=8.0, r_multiple=1.0, holding_days=3)


def _intraday(stamps):
    return pd.DatetimeIndex([day + pd.Timedelta(hours=h, minutes=m)
                             for day in DAYS[-300:] for h, m in stamps], name="Datetime")


INDEXES = {"daily": lambda: pd.DatetimeIndex(DAYS, name="Date"),
           "hourly": lambda: _intraday(((10, 0), (14, 0))),
           "15min": lambda: _intraday(((9, 30), (15, 45)))}


def _write_timeframe(root: Path, timeframe: str, tickers, close: float) -> str:
    """One timeframe's CSVs and manifest; returns the manifest file's sha256
    (the value `_integrity.json` freezes and V190-4's staleness check compares)."""
    folder = root / timeframe
    folder.mkdir(parents=True)
    index = INDEXES[timeframe]()
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                          "Volume": 1_000_000.0}, index=index)
    for ticker in tickers:
        frame.to_csv(folder / f"{safe_symbol(ticker)}.csv")
    manifest = folder / "_manifest.json"
    manifest.write_text(json.dumps({
        "timeframe": timeframe, "feed": "sip", "adjustment": "all", "hash": f"h-{timeframe}",
        "tickers": {t: {"status": "ok", "sha256": "x"} for t in tickers}}), encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _entry(**over) -> dict:
    entry = {"admitted": True, "reason": None, "identity": "ok", "identity_manifest": "ok",
             "reference": {"source": "backtest_cache_ext", "sha256": "r"}, "dropped_before": 0,
             "first_bar": "2016-01-04", "last_bar": "2026-03-31", "coverage": [],
             "signal_cuts": [], "trim": {"keep_from": None, "keep_before": None, "reason": None},
             "breaks": []}
    entry.update(over)
    return entry


def build_pit_store(data_dir: Path, *, close: float = 50.0, context=CONTEXT) -> Path:
    """A fixture PIT store under <data_dir>/market_data_pit: members plus context
    symbols, all three timeframes, and an `_integrity.json` carrying one frame
    trim (MON) and one signal-date cut (AAA)."""
    root = data_dir / "market_data_pit"
    tickers = (*MEMBERS, *context)
    shas = {tf: _write_timeframe(root, tf, tickers, close) for tf in ("daily", "hourly", "15min")}
    entries = {t: _entry() for t in tickers}
    entries["AAA"] = _entry(signal_cuts=[[*CUT, "missing run of 6 sessions"]])
    entries["MON"] = _entry(
        trim={"keep_from": None, "keep_before": TRIM_BEFORE,
              "reason": "reused symbol: break after the last membership end"},
        breaks=[{"date": TRIM_BEFORE, "kind": "close+volume", "resolution": "trim_after"}])
    doc = {"schema": 1, "generated_at": "2026-10-25T00:00:00+00:00",
           "store_start": "2016-01-04", "store_end": "2025-12-31",
           "thresholds": {"max_missing_run": 5, "trailing_sessions": 60,
                          "min_trailing_share": 0.95, "break_move": 0.5, "break_ratio": 10.0,
                          "revert_sessions": 20, "gap_sessions": 20, "edge_sessions": 20},
           "detector_sha": {}, "manifest_sha256": shas, "no_bars": [], "tickers": entries}
    (root / "_integrity.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """config.DATA_DIR -> tmp (membership CSV, PIT root); HISTORY_STORE_DIR -> a
    watchlist store holding AAA, BBB and the regime ticker, which v3 must never read."""
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    watchlist = tmp_path / "watchlist_store"
    _write_timeframe(watchlist, "daily", ("AAA", "BBB", config.MARKET_REGIME_TICKER), 40.0)
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watchlist))
    monkeypatch.chdir(tmp_path)          # main writes backtest_range_summary.txt to cwd
    rbr._SPY_CACHE.clear()
    training_data.reset()
    yield data
    rbr._SPY_CACHE.clear()
    training_data.reset()


@pytest.fixture
def harness(data_dir, monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run_backtest(ticker, df, strat, hk, **kwargs):
        calls.append({"ticker": ticker, "first": df.index.min(), "last": df.index.max(),
                      "rows": len(df), "digest": int(pd.util.hash_pandas_object(df).sum()),
                      "instrument": kwargs.get("instrument")})
        return SimpleNamespace(trades=[_trade(day) for day in TRADES.get(ticker, ())])

    monkeypatch.setattr(rbr, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(rbr, "_tickers_for_run",
                        lambda universe, tickers_file=None: list(MEMBERS) if universe else ["AAA", "BBB"])
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(rbr, "LEGACY_HORIZONS", ("3m",))

    def run(*argv, context="off"):
        calls.clear()
        rbr._SPY_CACHE.clear()
        training_data.reset()
        capsys.readouterr()
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--strategy", "RSI",
                                          "--context", context, "--json", str(out), *argv])
        rbr.main()
        return SimpleNamespace(
            payload=json.loads(out.read_text(encoding="utf-8")),
            report=(tmp_path / "backtest_range_summary.txt").read_text(encoding="utf-8"),
            provenance=json.loads(training_data.provenance_path(out).read_text(encoding="utf-8")),
            stdout=capsys.readouterr().out, calls=list(calls))

    return SimpleNamespace(run=run, calls=calls)


# --- v3 end to end ------------------------------------------------------------------

def test_v3_runs_on_the_pit_store_with_one_trim_and_one_cut(harness, data_dir):
    build_pit_store(data_dir)
    result = harness.run("--train", *V3_FLAGS)
    by_ticker = {call["ticker"]: call for call in result.calls}
    assert set(by_ticker) == set(MEMBERS)
    assert all(call["instrument"] == V3 for call in result.calls)
    assert by_ticker["MON"]["last"] < pd.Timestamp(TRIM_BEFORE)    # the frame trim
    assert by_ticker["AAA"]["last"] <= RESEARCH_END
    assert by_ticker["AAA"]["first"] == pd.Timestamp("2016-01-04")
    assert result.payload["RSI"]["n_eval"] == 4                     # the span cut drops AAA 03-15
    assert "== TRAIN 2017-01-01 .. 2025-12-31" in result.report
    assert "instrument v3: universe sp500_pit" in result.report
    assert ("signal-date cuts ON from the PIT integrity report: 1 cut range(s) on 1 ticker(s)"
            in result.stdout)


def test_v3_provenance_names_the_store_and_the_integrity_sha(harness, data_dir):
    root = build_pit_store(data_dir)
    result = harness.run("--train", *V3_FLAGS)
    assert result.provenance["data_source"] == "alpaca"
    assert result.provenance["store"] == "pit"
    assert result.provenance["integrity_sha256"] == \
        hashlib.sha256((root / "_integrity.json").read_bytes()).hexdigest()


def test_v3_context_frames_stop_at_research_end(harness, data_dir, monkeypatch):
    build_pit_store(data_dir)
    seen = {}

    def capture(frames, spy_df, *, sector_of_ticker, sector_etf_frames, sector_of_etf, **kwargs):
        seen.update(frames=frames, spy=spy_df, etfs=sector_etf_frames)
        return {}

    monkeypatch.setattr(asof_context, "build_asof", capture)
    harness.run("--train", *V3_FLAGS, context="on")
    assert seen["spy"].index.max() <= RESEARCH_END
    assert set(seen["etfs"]) == set(sector_map("etfs"))
    assert all(frame.index.max() <= RESEARCH_END for frame in seen["etfs"].values())
    assert all(frame.index.max() <= RESEARCH_END for frame in seen["frames"].values())
    assert rbr._market_frame().index.max() <= RESEARCH_END


def test_v3_leaves_no_intraday_bar_on_or_after_the_holdout(harness, data_dir):
    build_pit_store(data_dir)
    harness.run("--train", *V3_FLAGS)
    assert training_data.active_store() == "pit"
    for ticker in ("AAA", config.MARKET_REGIME_TICKER):
        for timeframe in ("hourly", "15min"):
            frame = training_data.load_intraday(ticker, timeframe)
            assert frame is not None and frame.index.max() < HOLDOUT
    # MON's stored intraday bars all lie after its trim: trimmed to nothing is None
    assert training_data.load_intraday("MON", "hourly") is None
    assert training_data.load_daily("AAA").index.max() <= RESEARCH_END


# --- v3 refusals: before any backtest ------------------------------------------------

def test_v3_validation_is_the_sealed_holdout(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit) as exc:
        harness.run("--validation", *V3_FLAGS)
    assert HOLDOUT_SEALED in str(exc.value)
    assert harness.calls == []


def test_v3_refuses_a_window_reaching_into_2026(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit, match="research span"):
        harness.run("--from", "2025-06-01", "--to", "2026-02-27", *V3_FLAGS)
    assert harness.calls == []


def test_v3_refuses_yfinance(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit):
        harness.run("--train", *V3_FLAGS, "--data-source", "yfinance")
    assert harness.calls == []


def test_v3_refuses_a_store_missing_a_context_symbol(harness, data_dir):
    build_pit_store(data_dir, context=CONTEXT[:-1])
    with pytest.raises(SystemExit) as exc:
        harness.run("--train", *V3_FLAGS)
    assert CONTEXT[-1] in str(exc.value)
    assert harness.calls == []


def test_v3_refuses_a_store_without_an_integrity_report(harness, data_dir):
    root = build_pit_store(data_dir)
    (root / "_integrity.json").unlink()
    with pytest.raises(SystemExit):
        harness.run("--train", *V3_FLAGS)
    assert harness.calls == []


# --- _membership_for_run ------------------------------------------------------------

def test_membership_for_run_subtracts_the_integrity_cuts_under_the_pit_store(data_dir, capsys):
    build_pit_store(data_dir)
    training_data.select("alpaca", "pit", V3.research_end)
    membership = rbr._membership_for_run("sp500_pit", list(MEMBERS))
    assert membership["AAA"] == [("2010-01-04", CUT[0]), (CUT[1], OPEN_END)]
    assert membership["BBB"] == [("2010-01-04", OPEN_END)]
    assert membership["MON"] == [("2010-01-04", "2018-06-08")]
    assert "1 cut range(s) on 1 ticker(s)" in capsys.readouterr().out


@pytest.mark.parametrize("source", ["alpaca", "yfinance"])
def test_membership_for_run_is_unchanged_off_the_pit_store(data_dir, capsys, source):
    build_pit_store(data_dir)                 # on disk, never selected
    training_data.select(source)
    assert training_data.signal_cuts() is None
    assert rbr._membership_for_run("sp500_pit", list(MEMBERS)) == \
        membership_map("sp500_pit", list(MEMBERS))
    assert rbr._membership_for_run(None, ["AAA"]) is None
    assert "signal-date cuts" not in capsys.readouterr().out


# --- v1 and v2: byte-identical with a PIT store on disk (spec §3 regression pins) -----

def test_the_default_selection_ignores_a_pit_store_on_disk(data_dir):
    training_data.select()
    before = (training_data.active_store(), training_data.available_tickers(),
              training_data.provenance())
    build_pit_store(data_dir, close=99.0)
    training_data.reset()
    training_data.select()
    after = (training_data.active_store(), training_data.available_tickers(),
             training_data.provenance())
    assert after == before
    assert before[0] == "watchlist"
    assert before[1] == sorted(["AAA", "BBB", config.MARKET_REGIME_TICKER])


@pytest.mark.parametrize("flags", [("--train",), ("--train", "--instrument", "v1"),
                                   ("--train", "--instrument", "v2", *V2_KNOBS)],
                         ids=["default", "v1", "v2"])
def test_v1_and_v2_are_byte_identical_with_a_pit_store_on_disk(harness, data_dir, flags):
    before = harness.run(*flags)
    build_pit_store(data_dir, close=99.0)     # different prices: any leak changes the digest
    after = harness.run(*flags)
    assert after.calls == before.calls
    assert after.payload == before.payload
    assert after.report == before.report
    assert after.provenance == before.provenance
    assert after.stdout == before.stdout
    assert after.provenance["store"] == "watchlist"
    assert "signal-date cuts" not in after.stdout
```

- [ ] **Step 2: Run it and confirm the cut tests fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_run_backtest_range_v3.py`
Expected: FAIL in `test_v3_runs_on_the_pit_store_with_one_trim_and_one_cut` (`n_eval` 5, not 4, and no "signal-date cuts ON" line) and in `test_membership_for_run_subtracts_the_integrity_cuts_under_the_pit_store` (AAA's span uncut). The other tests exercise Part 1's seams and pass already. If one of them fails, the Part 1 seam it names is wrong: stop and report it rather than patch around it here. The one allowed adjustment: if V190-6 pins a different exception type for `--data-source yfinance` or a missing integrity report, match the test to V190-6's pinned type; the requirement it guards is "no backtest call" (`harness.calls == []`), which stays.

- [ ] **Step 3: Implement the cut in `_membership_for_run` (`scripts/backtest/run_backtest_range.py`)**

Replace the function and add the helper directly below it:

```python
def _membership_for_run(universe: str | None, tickers: list) -> dict | None:
    """{ticker: spans} for a point-in-time `*_pit` universe, else None
    (unmasked -- every existing universe name behaves exactly as before).
    v190: under the PIT store (instrument v3) the integrity report's
    signal-date cuts are subtracted from the spans, so the signal mask
    `_spans_for` applies never admits a cut date; every other selection
    passes cuts=None, byte-identical to before."""
    from swingbot.core.marketdata.pit_membership import membership_map
    cuts = training_data.signal_cuts()
    membership = membership_map(universe, tickers, cuts=cuts)
    if membership is not None:
        print(f"point-in-time membership mask ON for universe '{universe}': "
              f"{sum(1 for s in membership.values() if s)}/{len(tickers)} tickers "
              f"have membership rows", flush=True)
        _print_signal_cuts(cuts, tickers)
    return membership


def _print_signal_cuts(cuts: dict | None, tickers: list) -> None:
    """One line naming how many integrity cuts the run's mask carries; silent
    off the PIT store (cuts is None), so v1/v2 stdout is unchanged."""
    if cuts is None:
        return
    hit = {ticker: cuts[ticker] for ticker in tickers if cuts.get(ticker)}
    print(f"signal-date cuts ON from the PIT integrity report: "
          f"{sum(len(ranges) for ranges in hit.values())} cut range(s) on "
          f"{len(hit)} ticker(s)", flush=True)
```

No other line of `run_backtest_range.py` changes.

- [ ] **Step 4: Run the new file and the neighbours it must not move**

Run:
```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_run_backtest_range_v3.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_run_backtest_range_instrument.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_tune_strategy_instrument.py
python scripts/dev/testrun.py file tests/history_store/test_rbr_data_source.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py
```
Expected: every file `0 failed`, `0 xfailed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `_membership_for_run` and `_print_signal_cuts` both rank A; `main` stays at its baseline.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/run_backtest_range.py tests/backtest_scripts/test_run_backtest_range_v3.py
git commit -m "feat(backtest): v190 V190-7 -- v3 signal-date cuts in run_backtest_range; v3 end-to-end and v1/v2 byte-identity pins"
```

### Task V190-8: Instrument branch audit: v3 takes the v2 path at all 17 sites

**Model:** sonnet — tests only plus two comments; the site list and every assertion are given.

**Files:**
- Create: `tests/backtesting/instrument/test_v3_branch_audit.py` (suite `backtesting-arms`; no new directory)
- Modify: `swingbot/core/analytics/override_fidelity.py` (one comment above `INSTRUMENT = contract.resolve("v2")`, line 240)
- Modify: `swingbot/core/analytics/override_verdict.py` (one comment above the `mirror_ledger_row` entry dict carrying `"instrument": "v2"`, line 241)

**Interfaces:**
- Consumes: `resolve("v3")` (V190-1: `version="v3"`, `universe="sp500_pit"`, research `2017-01-01..2025-12-31`, `holdout_start="2026-01-01"`, `train_window=None`, v2's fills, costs, floor, purge and embargo).
- Produces: nothing a later task imports. The audit's `LITERAL_SITES` table is the standing record: a new `.version == "vN"` comparison anywhere in `swingbot/` or `scripts/` fails `test_every_instrument_comparison_is_against_v1_and_is_audited` until it is added here with a v3 behaviour test.

The 17 sites (brief § 3, re-verified at HEAD 668fc59f): 14 literal comparisons, all against `"v1"` — `run_backtest_range` `_instrument_frame` (427), `_windowed_trades` (442), `_instrument_guards` (477), `_missing_frames` (503), `_instrument_report` (538); `tune_strategy` `_instrument_guards` (127), `_load_universe` (151), `_evaluate` (193), `_fold_report` (236); `backtest_wf._exit_kwargs` (122); `instrument/cli.run_instrument` (38), `require_v1` (74); `planning/exit_sim.simulate_exit` (887); `contract.InstrumentSpec.live_constructor` (86) — plus three branches on a field v3 shares with v2: `backtest._uses_live_constructor` (`live_constructor`, 410; `run_backtest` routes through it at 597), `cli._has_v1_split` (`train_window`, behind `window_for` / `check_inside_research`) and `coverage._intervals` (`universe`). None means "v2 alone", so no branch changes. The two `resolve("v2")` / `"instrument": "v2"` hard-codes in analytics do mean v2 alone (v173 books override fidelity on v2 fills); they stay and get a comment. The 13 `require_v1` callers keep refusing v3 as they refuse v2.

- [ ] **Step 1: Write the test file `tests/backtesting/instrument/test_v3_branch_audit.py`**

```python
"""v190 V190-8: the instrument branch audit (spec §4).

Every instrument comparison in swingbot/ and scripts/ is `== "v1"` or
`!= "v1"`, so v3 takes v2's path at each. The scan pins the 14 literal sites;
three more branch on a field v3 shares with v2 (`live_constructor`,
`train_window`, `universe`). One behaviour test per site runs v3 beside v2
(and v1 where the contrast matters). A new literal site fails the scan until
it is added here with its v3 test."""
import ast
import inspect
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import run_backtest_range as rbr  # noqa: E402
import tune_strategy as tune  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.analytics import override_fidelity, override_verdict  # noqa: E402
from swingbot.core.backtesting import backtest, backtest_wf  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument import cli, coverage  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.planning import exit_sim, exit_sim_v2  # noqa: E402

V1, V2, V3 = resolve("v1"), resolve("v2"), resolve("v3")
ALWAYS = [("2010-01-01", "9999-12-31")]
RESEARCH_END = pd.Timestamp("2025-12-31")
VERSION = re.compile(r"^v\d+$")
RBR, TUNE = "scripts/backtest/run_backtest_range.py", "scripts/backtest/tune_strategy.py"

#: (file, enclosing function) -> the literal it compares `.version` against.
LITERAL_SITES = {
    (RBR, "_instrument_frame"): "v1",
    (RBR, "_windowed_trades"): "v1",
    (RBR, "_instrument_guards"): "v1",
    (RBR, "_missing_frames"): "v1",
    (RBR, "_instrument_report"): "v1",
    (TUNE, "_instrument_guards"): "v1",
    (TUNE, "_load_universe"): "v1",
    (TUNE, "_evaluate"): "v1",
    (TUNE, "_fold_report"): "v1",
    ("swingbot/core/backtesting/backtest_wf.py", "_exit_kwargs"): "v1",
    ("swingbot/core/backtesting/instrument/cli.py", "run_instrument"): "v1",
    ("swingbot/core/backtesting/instrument/cli.py", "require_v1"): "v1",
    ("swingbot/core/planning/exit_sim.py", "simulate_exit"): "v1",
    ("swingbot/core/backtesting/instrument/contract.py", "live_constructor"): "v1",
}
#: (function, the field it branches on) -- the three sites with no literal.
INDIRECT_SITES = ((backtest._uses_live_constructor, "live_constructor"),
                  (cli._has_v1_split, "train_window"),
                  (coverage._intervals, "universe"))
REQUIRE_V1_SCRIPTS = (
    "ablation", "emit_cohort_registry", "measure_arms", "measure_giveback_levels",
    "measure_runner_giveback", "measure_strategy_arm", "permutation_test",
    "quarterly_revalidation", "tune_confluence_gates", "tune_exit_v2", "wf_components",
    "wf_run", "run_backtest_range")


def _version_literals(nodes):
    for node in nodes:
        elements = node.elts if isinstance(node, (ast.Tuple, ast.List, ast.Set)) else [node]
        for element in elements:
            if (isinstance(element, ast.Constant) and isinstance(element.value, str)
                    and VERSION.match(element.value)):
                yield element.value


class _Comparisons(ast.NodeVisitor):
    """(enclosing function, literal) of every `<x>.version <op> "vN"` compare."""

    def __init__(self):
        self.stack, self.found = [], []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Compare(self, node):
        operands = [node.left, *node.comparators]
        if any(isinstance(o, ast.Attribute) and o.attr == "version" for o in operands):
            others = [o for o in operands if not (isinstance(o, ast.Attribute) and o.attr == "version")]
            function = self.stack[-1] if self.stack else "<module>"
            self.found.extend((function, value) for value in _version_literals(others))
        self.generic_visit(node)


def instrument_comparisons() -> dict:
    found = {}
    for base in ("swingbot", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            visitor = _Comparisons()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            rel = path.relative_to(ROOT).as_posix()
            found.update({(rel, function): value for function, value in visitor.found})
    return found


def _frame(periods=2600, start="2016-01-04"):
    index = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": 1_000_000}, index=index)


def _trade(entry, signal=None):
    trade = BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                          stop_loss=48.0, take_profit=54.0, outcome="win", exit_price=54.0,
                          return_pct=8.0, r_multiple=1.0, holding_days=3)
    if signal is not None:
        trade.signal_date = signal
    return trade


def _args(**over):
    base = dict(train=False, validation=False, date_from=None, date_to=None, universe=None,
                scenarios=False, emit_registry=None, from_json=None, tickers_file=None,
                exit_model="v2", tp2="none")
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- the scan -------------------------------------------------------------------------

def test_every_instrument_comparison_is_against_v1_and_is_audited():
    assert instrument_comparisons() == LITERAL_SITES
    assert set(LITERAL_SITES.values()) == {"v1"}
    assert len(LITERAL_SITES) + len(INDIRECT_SITES) == 17


@pytest.mark.parametrize("function, field", INDIRECT_SITES)
def test_each_indirect_site_still_branches_on_its_field(function, field):
    assert field in inspect.getsource(function)


def test_v3_shares_every_field_the_indirect_sites_read_with_v2():
    assert V3.live_constructor is V2.live_constructor is True
    assert V3.train_window is V2.train_window is None
    assert V3.universe == V2.universe == "sp500_pit"


# --- run_backtest_range ---------------------------------------------------------------

def test_rbr_instrument_frame_cuts_v3_at_research_end_like_v2():
    df = _frame()
    assert rbr._instrument_frame(df, V3).equals(rbr._instrument_frame(df, V2))
    assert rbr._instrument_frame(df, V3).index.max() <= RESEARCH_END
    assert rbr._instrument_frame(df, V1) is df


def test_rbr_windowed_trades_take_the_signal_day_gate_under_v3():
    crosses_out = _trade("2021-03-01", signal="2021-02-26")
    summary = SimpleNamespace(trades=[crosses_out])
    spans = [("2021-01-01", "2021-03-01")]
    for spec in (V2, V3):
        assert rbr._windowed_trades(summary, "2017-01-01", "2025-12-31", spans, _frame(), spec) \
            == [crosses_out]
    assert rbr._windowed_trades(summary, "2017-01-01", "2025-12-31", spans, _frame(), V1) == []


def test_rbr_guards_pin_the_universe_and_name_v3(live_flags_off):
    args = _args()
    rbr._instrument_guards(args, V3)
    assert args.universe == "sp500_pit"
    with pytest.raises(SystemExit) as exc:
        rbr._instrument_guards(_args(scenarios=True), V3)
    assert "--instrument v3" in str(exc.value)


def test_rbr_lists_a_missing_frame_under_v3_and_not_under_v1(capsys):
    assert rbr._missing_frames(["AAA", "BBB"], {"AAA": _frame()}, V3) == ["BBB"]
    assert rbr._missing_frames(["AAA", "BBB"], {"AAA": _frame()}, V1) == []


def test_rbr_instrument_report_names_v3(monkeypatch):
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA"])
    lines, extra = rbr._instrument_report(V3, [], ["RSI"], ["AAA"])
    assert any("instrument v3: universe sp500_pit" in line for line in lines)
    assert set(extra) == {"_watchlist_slice"}
    assert rbr._instrument_report(V1, [], ["RSI"], ["AAA"]) == ([], {})


# --- tune_strategy --------------------------------------------------------------------

def test_tune_guards_refuse_the_v1_exit_loop_under_v3(live_flags_off):
    with pytest.raises(SystemExit, match="--instrument v3"):
        tune._instrument_guards(SimpleNamespace(exit_model="v1"), V3)
    assert tune._instrument_guards(SimpleNamespace(exit_model="v2"), V3) is None
    assert tune._instrument_guards(SimpleNamespace(exit_model="v1"), V1) is None


def test_tune_load_universe_takes_the_pit_path_under_v3(monkeypatch):
    seen = {}

    def tickers(universe, tickers_file=None):
        seen["universe"] = universe
        return ["AAA"]

    monkeypatch.setattr(rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(rbr, "_membership_for_run", lambda universe, symbols: {s: ALWAYS for s in symbols})
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(tune, "load_cached", lambda ticker: _frame())
    frames, spans = tune._load_universe(V3)
    assert seen["universe"] == "sp500_pit"
    assert list(frames) == ["AAA"] and spans == {"AAA": ALWAYS}
    assert frames["AAA"].index.max() <= RESEARCH_END


def test_tune_evaluate_keeps_rows_under_v3(monkeypatch):
    rows = [("AAA", _trade("2021-02-02"))]
    monkeypatch.setattr(tune, "_v2_trades", lambda strategy, frames, spans, spec, scale_out: rows)
    stats, kept = tune._evaluate("RSI", ({}, {}), SimpleNamespace(exit_model="v2", scale_out=True), V3)
    assert kept == rows
    assert stats["n_eval"] == 1


def test_tune_fold_report_reports_v3(monkeypatch, capsys):
    monkeypatch.setattr(tune, "_out_of_fold",
                        lambda rows_by_config, spec: SimpleNamespace(trades=[], choices=[]))
    monkeypatch.setattr(tune, "_watchlist_slice", lambda trades, rows_by_config:
                        {"status": "thin", "n": 0, "expectancy_r": None})
    report = tune._fold_report([], {}, V3)
    assert report["instrument"] == "v3"
    assert report["research_span"] == ["2017-01-01", "2025-12-31"]
    assert tune._fold_report([], {}, V1) == {}


# --- engine, cli, contract, coverage --------------------------------------------------

def test_wf_exit_kwargs_give_v3_its_own_fills_and_costs():
    assert backtest_wf._exit_kwargs(V3) == {"exit_model": "v2", "scale_out": True,
                                            "tp2_mode": "none", "instrument": V3}
    assert backtest_wf._exit_kwargs(V1) == backtest_wf._exit_kwargs(None)


def test_cli_run_instrument_passes_v3_through():
    assert cli.run_instrument(V3) is V3
    assert cli.run_instrument(V1) is None


def test_cli_require_v1_refuses_v3():
    with pytest.raises(SystemExit, match="--instrument v3 is not wired yet"):
        cli.require_v1(V3, "x.py", "a later phase")


def test_exit_sim_routes_v3_to_the_v2_walk(monkeypatch):
    monkeypatch.setattr(exit_sim_v2, "simulate_exit_v2",
                        lambda df, signal_index, plan, instrument, **kwargs: ("v2-walk", instrument))
    assert exit_sim.simulate_exit(None, 0, SimpleNamespace(), instrument=V3) == ("v2-walk", V3)


def test_contract_builds_v3_through_the_live_constructor():
    assert V3.live_constructor is True
    assert V1.live_constructor is False


def test_uses_live_constructor_under_v3(live_flags_off):
    assert backtest._uses_live_constructor(V3, "v2", "none") is True
    with pytest.raises(ValueError, match="instrument v3 needs exit_model='v2'"):
        backtest._uses_live_constructor(V3, "v1", "none")
    with pytest.raises(ValueError, match="tp2_mode='levels'"):
        backtest._uses_live_constructor(V3, "v2", "levels")


def test_cli_windows_seal_the_v3_holdout():
    assert cli.window_for(V3, "train") == ("2017-01-01", "2025-12-31")
    with pytest.raises(SystemExit, match="holdout starts 2026-01-01"):
        cli.window_for(V3, "validation")
    with pytest.raises(SystemExit, match="research span"):
        cli.check_inside_research(V3, "2025-06-01", "2026-02-27")
    cli.check_inside_research(V3, "2021-01-04", "2021-12-31")


def test_coverage_members_follow_the_v3_research_span(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(
        "ticker,start_date,end_date\nAAA,2005-01-03,\nCCC,2012-03-01,2015-01-02\n"
        "DDD,2026-02-02,\n", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    assert coverage.research_members(V3) == ["AAA"]
    assert coverage.research_members(V2) == ["AAA", "CCC"]
    with pytest.raises(ValueError, match="no point-in-time universe"):
        coverage.research_members(V1)


# --- what stays v2 alone, and the scripts that refuse v3 --------------------------------

def test_the_two_analytics_hard_codes_stay_v2_alone():
    assert override_fidelity.INSTRUMENT == V2
    assert '"instrument": "v2"' in inspect.getsource(override_verdict.mirror_ledger_row)
    for module in (override_fidelity, override_verdict):
        assert "v2 alone" in Path(module.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("script", REQUIRE_V1_SCRIPTS)
def test_require_v1_scripts_keep_refusing_every_instrument_but_v1(script):
    tree = ast.parse((ROOT / "scripts" / "backtest" / f"{script}.py").read_text(encoding="utf-8"))
    called = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
              for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "require_v1" in called
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_v3_branch_audit.py`
Expected: every test passes except `test_the_two_analytics_hard_codes_stay_v2_alone` (FAIL: `"v2 alone"` not in the module text). If `test_every_instrument_comparison_is_against_v1_and_is_audited` fails, print `instrument_comparisons()` and compare: a site the brief missed is added to `LITERAL_SITES` with its own behaviour test in this file, and the count assertion and the task text are corrected — never a branch edit to make the scan pass. If `BacktestTrade` refuses the `signal_date` assignment (frozen or slotted), build it with `dataclasses.replace(trade, signal_date=signal)` instead.

- [ ] **Step 3: Add the two comments**

In `swingbot/core/analytics/override_fidelity.py`, directly above `INSTRUMENT = contract.resolve("v2")`:

```python
#: v190 audit: v2 alone -- v173 books override fidelity on v2 fills and costs;
#: instrument v3 (the PIT Alpaca store) does not move this.
```

In `swingbot/core/analytics/override_verdict.py`, directly above the `entry = {"id": record["ledger_id"], ...` line in `mirror_ledger_row`:

```python
    # v190 audit: v2 alone -- the v173 ledger row names the instrument it was
    # measured on (v2 fills); v3 does not move it.
```

- [ ] **Step 4: Run the audit and the two analytics test files**

Run:
```bash
python scripts/dev/testrun.py file tests/backtesting/instrument/test_v3_branch_audit.py
python scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
python scripts/dev/testrun.py file tests/analytics/test_override_io.py
```
Expected: `0 failed`, `0 xfailed` in each.

- [ ] **Step 5: Commit**

```bash
git add tests/backtesting/instrument/test_v3_branch_audit.py swingbot/core/analytics/override_fidelity.py swingbot/core/analytics/override_verdict.py
git commit -m "test(instrument): v190 V190-8 -- v3 takes the v2 path at all 17 instrument branch sites; v2-alone hard-codes commented"
```

### Task V190-9: v3 coverage gate on the store layout

**Model:** sonnet — one reader and one dispatch over an existing, well-tested module; values and layout are given.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/coverage.py` (add `store_first_bar`, `check_store_coverage`; `check_coverage` keeps its behaviour through a shared `_classify`)
- Modify: `scripts/data/check_cache_coverage.py` (`--store-root`; v3 reads the PIT store)
- Modify: `tests/backtesting/instrument/test_window_coverage.py` (append tests; existing tests untouched)

**Interfaces:**
- Consumes: `resolve("v3")` with `store="pit"`, `warmup_start="2016-01-04"`, research `2017-01-01..2025-12-31` (V190-1); `history_store.store_root(store)` — `"pit"` is `<DATA_DIR>/market_data_pit` (worktree-aware, never reads `HISTORY_STORE_DIR`) (V190-2); `data_store.safe_symbol` (exists, `swingbot/core/marketdata/data_store.py:112`).
- Produces (consumed by V190-22's gate run):
  - `coverage.store_first_bar(root: Path, symbol: str) -> pd.Timestamp | None` — first dated row of `<root>/daily/<safe_symbol(symbol)>.csv`; None when the file is absent or holds no dated row.
  - `coverage.check_store_coverage(symbols, required_start: str, root: Path) -> CoverageReport` — same classification as `check_coverage` (covered / late `(symbol, iso day)` / missing), read from the store layout.
  - `python scripts/data/check_cache_coverage.py --instrument v3 [--store-root PATH] [--out PATH]` — default root `history_store.store_root("pit")`; exit 0 covered, 1 gaps, 2 nothing to check or a wrong flag pairing (`--cache-dir` with v3, `--store-root` with v2).

The gate reads the raw stored file, like v2's reads the raw cache: a frame trim in `_integrity.json` applies on load and is listed by the integrity report (V190-15), not here. The required day is `spec.warmup_start` for every member, exactly as v2; a member that joined after 2016 is listed late beside its first membership date, never dropped.

- [ ] **Step 1: Append the failing tests to `tests/backtesting/instrument/test_window_coverage.py`**

Add `import pandas as pd` to the imports, then append:

```python
# --- v190: the PIT store layout (<root>/daily/<SAFE>.csv) -------------------------------

def _store_csv(root: Path, name: str, first_day: str | None) -> None:
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    _csv(folder, name, first_day)


def test_store_first_bar_reads_the_store_daily_layout(tmp_path):
    _store_csv(tmp_path, "BRK-B", "2016-01-04")
    _store_csv(tmp_path, "GC_F", "2016-02-01")
    assert coverage.store_first_bar(tmp_path, "BRK-B") == pd.Timestamp("2016-01-04")
    assert coverage.store_first_bar(tmp_path, "GC=F") == pd.Timestamp("2016-02-01")
    assert coverage.store_first_bar(tmp_path, "NOPE") is None


def test_store_first_bar_is_none_for_a_file_with_no_dated_row(tmp_path):
    _store_csv(tmp_path, "EMPTY", None)
    assert coverage.store_first_bar(tmp_path, "EMPTY") is None


def test_check_store_coverage_sorts_covered_late_and_missing(tmp_path):
    _store_csv(tmp_path, "AAA", "2016-01-04")
    _store_csv(tmp_path, "CCC", "2018-03-01")
    report = coverage.check_store_coverage(["CCC", "AAA", "ZZZ", "AAA"], "2016-01-04", tmp_path)
    assert report == CoverageReport("2016-01-04", ("AAA",), (("CCC", "2018-03-01"),), ("ZZZ",))


def test_check_store_coverage_ignores_a_cache_style_file_at_the_root(tmp_path):
    _csv(tmp_path, "AAA", "2016-01-04")          # backtest-cache layout, not daily/
    assert coverage.check_store_coverage(["AAA"], "2016-01-04", tmp_path).missing == ("AAA",)


def test_check_store_coverage_of_an_empty_store_lists_every_member_missing(tmp_path):
    report = coverage.check_store_coverage(["AAA", "BRK-B"], "2016-01-04", tmp_path)
    assert report.missing == ("AAA", "BRK-B") and report.gaps == 2


def test_cli_v3_checks_the_pit_store_from_2016(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    store = tmp_path / "pit"
    _store_csv(store, "AAA", "2016-01-04")
    _store_csv(store, "BRK-B", "2017-05-01")
    out = tmp_path / "coverage.md"
    code = cli.run(["--instrument", "v3", "--store-root", str(store), "--out", str(out)])
    assert code == 1
    text = out.read_text(encoding="utf-8")
    assert "Instrument: v3 (universe sp500_pit, research 2017-01-01..2025-12-31)" in text
    assert f"Store: `{store}`" in text
    assert "Members checked: 2" in text                 # CCC left in 2015, DDD joins in 2026
    assert "Required first bar: 2016-01-04" in text
    assert "| BRK-B | 2017-05-01 | 2008-02-01 |" in text
    assert f"COVERAGE: GAPS  1 gap(s), store {store}" in capsys.readouterr().err


def test_cli_v3_exits_zero_when_the_store_covers_every_member(universe_dir, tmp_path):
    from scripts.data import check_cache_coverage as cli
    store = tmp_path / "pit"
    for name in ("AAA", "BRK-B"):
        _store_csv(store, name, "2016-01-04")
    assert cli.run(["--instrument", "v3", "--store-root", str(store)]) == 0


def test_cli_v3_defaults_to_the_pit_root_and_ignores_history_store_dir(universe_dir, tmp_path,
                                                                        monkeypatch):
    from scripts.data import check_cache_coverage as cli
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    for name in ("AAA", "BRK-B"):
        _store_csv(universe_dir / "market_data_pit", name, "2016-01-04")
    assert cli.run(["--instrument", "v3"]) == 0


def test_cli_refuses_a_cache_dir_with_v3_and_a_store_root_with_v2(universe_dir, tmp_path, capsys):
    from scripts.data import check_cache_coverage as cli
    assert cli.run(["--instrument", "v3", "--cache-dir", str(tmp_path)]) == 2
    assert "--store-root" in capsys.readouterr().err
    assert cli.run(["--instrument", "v2", "--store-root", str(tmp_path)]) == 2
    assert "--cache-dir" in capsys.readouterr().err
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/instrument/test_window_coverage.py`
Expected: the nine new tests FAIL (`AttributeError: module ... has no attribute 'store_first_bar'`; the CLI tests on the unknown `--store-root` argument, exit 2 from argparse); every existing test passes.

- [ ] **Step 3: Implement in `swingbot/core/backtesting/instrument/coverage.py`**

Add `import pandas as pd` and `from swingbot.core.marketdata.data_store import safe_symbol`. Extend the module docstring by one paragraph: v190 adds the PIT store reader (`<root>/daily/<SAFE>.csv`, the history-store layout) for instrument v3; the backtest-cache reader is unchanged.

Move `check_coverage`'s loop into a private classifier taking the per-symbol reader, and add the two store functions:

```python
def _classify(symbols, required_start: str, first_of) -> CoverageReport:
    """Each distinct symbol into covered / late / missing by `first_of(symbol)`,
    an ISO day or None."""
    covered, late, missing = [], [], []
    for sym in sorted(set(symbols)):
        first = first_of(sym)
        if first is None:
            missing.append(sym)
        elif first > required_start:
            late.append((sym, first))
        else:
            covered.append(sym)
    return CoverageReport(required_start, tuple(covered), tuple(late), tuple(missing))


def check_coverage(symbols, required_start: str, cache_dir: Path) -> CoverageReport:
    """Classify each distinct symbol by its cached first bar against `required_start`."""
    return _classify(symbols, required_start, lambda sym: first_bar_date(
        Path(cache_dir) / backtest_cache.cache_path(sym).name))


def store_first_bar(root: Path, symbol: str) -> pd.Timestamp | None:
    """First dated bar of a history store's daily file, `<root>/daily/<SAFE>.csv`
    (the layout `history_store.file_path` writes), or None when the file is
    absent or holds no dated row. The raw file: frame trims apply on load."""
    day = first_bar_date(Path(root) / "daily" / f"{safe_symbol(symbol)}.csv")
    return None if day is None else pd.Timestamp(day)


def check_store_coverage(symbols, required_start: str, root: Path) -> CoverageReport:
    """`check_coverage` against a history store's daily files (instrument v3's
    PIT store) instead of the backtest cache."""
    def first_of(sym):
        bar = store_first_bar(root, sym)
        return None if bar is None else bar.date().isoformat()
    return _classify(symbols, required_start, first_of)
```

- [ ] **Step 4: Implement in `scripts/data/check_cache_coverage.py`**

Import `history_store` beside `backtest_cache` (`from swingbot.core.marketdata import backtest_cache, history_store`). Add to the module docstring one usage line, `python scripts/data/check_cache_coverage.py --instrument v3 [--store-root data/market_data_pit]`, and one sentence: an instrument with a `store` (v3) is checked against that store's daily files, default `history_store.store_root(store)`. Then:

```python
    # in _parser(), after --cache-dir:
    ap.add_argument("--store-root", default=None,
                    help="v190: the store an instrument with store='pit' (v3) is checked "
                         "against (default: history_store.store_root('pit'))")
```

```python
_CHECKS = {"Cache": coverage.check_coverage, "Store": coverage.check_store_coverage}


def _source(args, spec) -> tuple[Path, str]:
    """(directory, label) the check reads: the instrument's store when it names
    one (v3), else the backtest cache, exactly as before. ValueError on a flag
    that belongs to the other kind."""
    if spec.store is None:
        if args.store_root:
            raise ValueError(f"--instrument {spec.version} reads the backtest cache; "
                             f"use --cache-dir, not --store-root")
        return (Path(args.cache_dir) if args.cache_dir else backtest_cache.CACHE_DIR), "Cache"
    if args.cache_dir:
        raise ValueError(f"--instrument {spec.version} reads the {spec.store} store; "
                         f"use --store-root, not --cache-dir")
    root = Path(args.store_root) if args.store_root else history_store.store_root(spec.store)
    return root, "Store"


def _report_text(spec, source: Path, label: str) -> tuple[str, int]:
    symbols = coverage.research_members(spec)
    report = _CHECKS[label](symbols, spec.warmup_start, source)
    start, end = spec.research_span
    head = [f"Instrument: {spec.version} (universe {spec.universe}, research {start}..{end})",
            f"{label}: `{source}`", f"Members checked: {len(symbols)}", ""]
    firsts = coverage.first_membership(spec, _gap_symbols(report))
    body = coverage.render_markdown(report, firsts)
    return "\n".join(head) + body, report.gaps
```

In `run()`, replace the `cache_dir = ...` line and the `_report_text(spec, cache_dir)` call with:

```python
    try:
        source, label = _source(args, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text, gaps = _report_text(spec, source, label)
```

and the final stderr line with `print(f"COVERAGE: {'GAPS' if gaps else 'OK'}  {gaps} gap(s), {label.lower()} {source}", file=sys.stderr)` — for v2 that is the same text as today (`cache <dir>`). The default `--instrument` stays `v2`.

- [ ] **Step 5: Run the file and the complexity gate**

Run:
```bash
python scripts/dev/testrun.py file tests/backtesting/instrument/test_window_coverage.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`, `0 xfailed` (the existing v2 CLI tests prove the v2 report is unchanged); the gate exits 0, `run` and `_source` both below 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/instrument/coverage.py scripts/data/check_cache_coverage.py tests/backtesting/instrument/test_window_coverage.py
git commit -m "feat(instrument): v190 V190-9 -- v3 coverage gate reads the PIT store layout from 2016-01-04"
```

### Task V190-10: Additive calibration label; ledger `v3` and `DESCRIPTION`

**Model:** opus — touches a production-read label map and a closed, append-only ledger vocabulary; an ordering or rule slip moves live rows or the BH family.

**Files:**
- Modify: `swingbot/core/analytics/calibration.py` (`_WINDOW_KINDS`, lines 282-285, and the `registry_window_kind` docstring)
- Modify: `swingbot/core/backtesting/instrument/stats.py` (`VERDICTS`, `INSTRUMENTS`, new `DESCRIPTION` constant and `_row_rule_errors`, one call in `validate_ledger_row`)
- Modify: `tests/analytics/test_calibration.py` (append)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py` (update the vocabulary pin, append)
- Modify: `tests/analytics/test_override_verdict.py` (line 91 only: `VERDICTS[-3:]` becomes a fixed slice, since `DESCRIPTION` is appended after v173's three outcomes)

**Interfaces:**
- Consumes: `resolve("v3").research_span == ("2017-01-01", "2025-12-31")` (V190-1), used only by a test.
- Produces (consumed by V190-16's `ledger_row` and V190-24's ledger append):
  - `calibration._WINDOW_KINDS["2017-01-01..2025-12-31"] == "RESEARCH"`; the two existing entries unchanged.
  - `stats.INSTRUMENTS == ("v1", "v2", "screen-v1", "v3")`; `stats.VERDICTS` ends `(..., "COST", "SAVED", "INCONCLUSIVE", "DESCRIPTION")`; `stats.DESCRIPTION == "DESCRIPTION"`.
  - The DESCRIPTION-row rule in `validate_ledger_row`: a row with `verdict == "DESCRIPTION"` must carry `p: null` (ValueError naming `DESCRIPTION` and `p` otherwise); `exp_r: null` is allowed, as for every row (`_real` already accepts None). `ledger_qvalues` leaves it out of the BH family because `bh_qvalues` already skips `None` — pinned, not changed.

Both vocabularies are append-only (stats.py comment: "v140 appends ... v173 appends"); existing rows are never rewritten (`docs/claude/schema-evolution.md`). Consumers read the tuples dynamically: `swingbot/admin/api_v1/research.py:78-79` serves them, `scripts/reports/preregistration_ledger.py` takes them as `choices`, and the Research page colours an unknown verdict `neutral` (`research.ts:290`), so no other code changes. The frontend `registry_window_kind` type union (`frontend/src/app/api/models.ts:701`) stays `'TRAIN' | 'VALIDATION' | null`: no registry row can carry the v3 window, because `--emit-registry` is refused under every non-v1 instrument (`run_backtest_range._V2_UNWIRED`).

- [ ] **Step 1: Append the failing calibration tests to `tests/analytics/test_calibration.py`**

Add `import pytest`, `from swingbot.core.analytics import calibration` and `from swingbot.core.backtesting.instrument.contract import resolve` to the imports, then append:

```python
# --- v190: registry window labels grow additively ---------------------------------------

def test_registry_window_kind_keeps_the_two_methodology_labels():
    assert calibration.registry_window_kind("2020-01-01..2023-12-31") == "TRAIN"
    assert calibration.registry_window_kind("2024-01-01..2025-12-31") == "VALIDATION"


def test_registry_window_kind_labels_the_v3_research_span():
    assert "..".join(resolve("v3").research_span) == "2017-01-01..2025-12-31"
    assert calibration.registry_window_kind("2017-01-01..2025-12-31") == "RESEARCH"


@pytest.mark.parametrize("window", [None, "", "2010-01-01..2025-12-31", "2018-06-01..2022-12-31"])
def test_any_other_window_stays_unlabelled(window):
    assert calibration.registry_window_kind(window) is None


def test_window_kinds_only_grew():
    assert calibration._WINDOW_KINDS == {"2020-01-01..2023-12-31": "TRAIN",
                                         "2024-01-01..2025-12-31": "VALIDATION",
                                         "2017-01-01..2025-12-31": "RESEARCH"}


@pytest.mark.parametrize("window, kind", [("2020-01-01..2023-12-31", "TRAIN"),
                                          ("2024-01-01..2025-12-31", "VALIDATION"),
                                          ("2018-06-01..2022-12-31", None),
                                          (None, None)])
def test_an_existing_registry_row_keeps_its_label(window, kind):
    entry = {"source": "strategy", "strategy": "RSI", "horizon": "3m", "status": "WEAK",
             "window": window, "run_date": "2026-05-01", "expectancy_r": -0.05}
    assert calibration.live_loss_row(entry, [])["registry_window_kind"] == kind
```

- [ ] **Step 2: Update and append the ledger tests in `tests/backtesting/test_instrument_stats_ledger.py`**

Replace the two vocabulary lines of `test_fields_and_vocabularies_are_the_plan_set` with:

```python
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED", "COST", "SAVED", "INCONCLUSIVE",
                              "DESCRIPTION")
    assert stats.INSTRUMENTS == ("v1", "v2", "screen-v1", "v3")
```

Append:

```python
# --- v190: the v3 instrument and the DESCRIPTION row ------------------------------------

def _description(**over):
    row = _row(id="v190-v3-rebaseline", instrument="v3", verdict="DESCRIPTION",
               n=91234, exp_r=None, p=None,
               hypothesis="Instrument v3 re-baseline: describes an instrument change; "
                          "never a lift; selects nothing",
               record="docs/superpowers/results/2026-10-v190-v3-rebaseline.md")
    row.update(over)
    return row


def test_v3_is_a_ledger_instrument():
    stats.validate_ledger_row(_row(instrument="v3"))


def test_a_description_row_validates_with_null_p_and_null_exp_r():
    stats.validate_ledger_row(_description())
    stats.validate_ledger_row(_description(exp_r=0.04))
    stats.validate_ledger_row(_description(data_source="alpaca"))


@pytest.mark.parametrize("p", [0.0, 0.2, 1.0])
def test_a_description_row_refuses_any_p_value(p):
    with pytest.raises(ValueError, match="DESCRIPTION.*p"):
        stats.validate_ledger_row(_description(p=p))


def test_p_null_stays_allowed_on_every_other_verdict():
    stats.validate_ledger_row(_row(p=None))
    stats.validate_ledger_row(_row(verdict="NO-LIFT", p=None, exp_r=None))


def test_a_description_row_is_outside_the_bh_family():
    rows = [_row(id="a", p=0.01), _description(id="d"), _row(id="c", p=0.04)]
    assert stats.ledger_qvalues(rows) == {"a": pytest.approx(0.02), "d": None,
                                          "c": pytest.approx(0.04)}


def test_a_description_row_appends_in_field_order(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_description(data_source="alpaca"), path)
    stored = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert list(stored) == [*stats.LEDGER_FIELDS, "data_source"]
    assert (stored["verdict"], stored["instrument"], stored["p"]) == ("DESCRIPTION", "v3", None)
    assert stats.load_ledger(path) == [stored]
```

In `tests/analytics/test_override_verdict.py`, line 91 becomes:

```python
    assert stats.VERDICTS[9:12] == ("COST", "SAVED", "INCONCLUSIVE")
```

- [ ] **Step 3: Run the three files and confirm the new tests fail**

Run:
```bash
python scripts/dev/testrun.py file tests/analytics/test_calibration.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
```
Expected: FAIL in `test_registry_window_kind_labels_the_v3_research_span`, `test_window_kinds_only_grew`, `test_fields_and_vocabularies_are_the_plan_set`, `test_v3_is_a_ledger_instrument`, the three `test_a_description_row_*` validation tests and the append test (`ValueError: invalid field(s) ['instrument', 'verdict']`); `test_a_description_row_refuses_any_p_value` fails too until the rule exists. The label-keeping and BH tests already pass.

- [ ] **Step 4: Implement the calibration label (`swingbot/core/analytics/calibration.py`)**

```python
#: backtest-methodology.md windows, matched by exact string; never guessed.
#: v190 adds instrument v3's research span (additive: the two v1 strings keep
#: their labels, so no stored registry row changes label on deploy).
_WINDOW_KINDS = {
    "2020-01-01..2023-12-31": "TRAIN",
    "2024-01-01..2025-12-31": "VALIDATION",
    "2017-01-01..2025-12-31": "RESEARCH",
}
```

Docstring of `registry_window_kind`: `"""TRAIN / VALIDATION for the two v1 methodology windows, RESEARCH for instrument v3's research span (v190), else None."""`

- [ ] **Step 5: Implement the ledger vocabulary and rule (`swingbot/core/backtesting/instrument/stats.py`)**

Extend the comment above `VERDICTS` with one sentence — "v190 appends DESCRIPTION: a recorded description of an instrument change (the v3 re-baseline); it decides nothing, so it carries `p: null` and stays out of the BH family." — then:

```python
VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN",
            "SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED",
            "COST", "SAVED", "INCONCLUSIVE", "DESCRIPTION")
INSTRUMENTS = ("v1", "v2", "screen-v1", "v3")
DESCRIPTION = "DESCRIPTION"
```

Below `_FIELD_CHECKS`:

```python
def _row_rule_errors(row: dict) -> list[str]:
    """Cross-field rules one field check cannot see. A DESCRIPTION row decides
    nothing, so it may not carry a p-value (exp_r may be null, as anywhere)."""
    if row["verdict"] == DESCRIPTION and row["p"] is not None:
        return ["a DESCRIPTION row decides nothing: p must be null"]
    return []
```

At the end of `validate_ledger_row`, after the `bad` check raises:

```python
    rules = _row_rule_errors(row)
    if rules:
        raise ValueError(f"ledger row {row.get('id')!r}: {'; '.join(rules)}")
```

The message contains `DESCRIPTION` then `p`, which the test's `match="DESCRIPTION.*p"` reads.

- [ ] **Step 6: Run every file that reads these vocabularies, then the complexity gate**

Run:
```bash
python scripts/dev/testrun.py file tests/analytics/test_calibration.py
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`, `0 xfailed` in each file (the committed ledger still loads unchanged); the gate exits 0, `validate_ledger_row` below 15.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/analytics/calibration.py swingbot/core/backtesting/instrument/stats.py tests/analytics/test_calibration.py tests/backtesting/test_instrument_stats_ledger.py tests/analytics/test_override_verdict.py
git commit -m "feat(ledger): v190 V190-10 -- additive RESEARCH window label; ledger instrument v3 and DESCRIPTION verdict (p must be null)"
```

### Task V190-11: `validate_component --instrument`, refusing v3

**Model:** sonnet — one flag, one table-driven refusal and a guard-list edit; the message and the ordering are given.

**Files:**
- Modify: `scripts/backtest/validate_component.py` (imports, `V3_FUNNEL_REFUSAL`, `_FUNNEL_REFUSALS`, `_instrument_gate`, two lines in `main`)
- Modify: `tests/backtesting/instrument/test_date_literal_guard.py` (delete the `validate_component.py` entry from `NO_REPLAY`: the script now takes and reads `--instrument`, and `test_closed_and_non_replay_scripts_stay_v1_only` forbids a `NO_REPLAY` script calling `add_instrument_arg`)
- Create: `tests/backtest_scripts/test_validate_component_instrument.py` (suite `backtest-scripts`; no new directory)

**Interfaces:**
- Consumes: `contract.VERSIONS == ("v1", "v2", "v3")` and `resolve("v3").fold_test_years == (2021, ..., 2025)` (V190-1); `instrument_cli.add_instrument_arg`, `spec_from_args`, `require_v1` (exist, `swingbot/core/backtesting/instrument/cli.py:23/31/71`).
- Produces: `validate_component.V3_FUNNEL_REFUSAL: str` — names what is missing (Stage 2 wired for exactly three folds with an absolute `GATE_MIN_IMPROVING_FOLDS = 2`, Stage 3 on v1's VALIDATION window) and the follow-up methodology spec that must map Stage 2 and Stage 3 to five folds. CLI: `--instrument {v1,v2,v3}`, default `v1`, behaviour unchanged for v1.

**Ordering matters.** `cache_dir_source.resolve(args)` calls `fetch_backtest_data.apply_data_source(args)`, which after V190-6 selects the PIT store for an instrument with `store="pit"`. The refusal therefore runs **before** `cache_dir_source.resolve`, so a refused v3 call never selects or reads a store. The refusal is a dict lookup on `spec.version`, not a `.version ==` comparison, so V190-8's audit scan is unaffected.

- [ ] **Step 1: Write the failing test file `tests/backtest_scripts/test_validate_component_instrument.py`**

```python
"""v190 V190-11: validate_component --instrument (spec §4: the funnel does not
accept v3 until a methodology spec maps Stage 2/3 to five folds)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import validate_component as vc  # noqa: E402

BASE = ["--stage", "mde", "--arms", "arms.json", "--title", "t", "--window", "w",
        "--bespoke-instrument", "test fixture"]


@pytest.fixture
def funnel(monkeypatch):
    """Stubs the data selection and the mde stage; records what ran."""
    seen = {"resolved": 0, "stages": []}

    def resolve(args):
        seen["resolved"] += 1

    def stage_mde(args):
        seen["stages"].append(args.instrument)
        return 0

    monkeypatch.setattr(vc.cache_dir_source, "resolve", resolve)
    monkeypatch.setattr(vc, "stage_mde", stage_mde)
    return seen


def test_the_default_instrument_is_v1_and_runs_as_before(funnel):
    assert vc.main(BASE) == 0
    assert funnel == {"resolved": 1, "stages": ["v1"]}


def test_explicit_v1_is_identical_to_the_default(funnel):
    assert vc.main([*BASE, "--instrument", "v1"]) == 0
    assert funnel == {"resolved": 1, "stages": ["v1"]}


def test_v3_is_refused_before_any_data_is_selected(funnel):
    with pytest.raises(SystemExit) as exc:
        vc.main([*BASE, "--instrument", "v3"])
    assert str(exc.value) == vc.V3_FUNNEL_REFUSAL
    assert funnel == {"resolved": 0, "stages": []}


def test_v3_is_refused_on_the_selection_stage_too(funnel, monkeypatch):
    monkeypatch.setattr(vc, "stage_selection", lambda args: pytest.fail("selection ran"))
    with pytest.raises(SystemExit) as exc:
        vc.main(["--stage", "selection", "--title", "t", "--window", "w", "--instrument", "v3"])
    assert str(exc.value) == vc.V3_FUNNEL_REFUSAL
    assert funnel["resolved"] == 0


def test_the_v3_refusal_names_what_is_missing_and_who_maps_it():
    for needle in ("--instrument v3", "Stage 2", "Stage 3", "three folds",
                   "GATE_MIN_IMPROVING_FOLDS = 2", "five folds", "2021-2025",
                   "methodology spec", "--instrument v1"):
        assert needle in vc.V3_FUNNEL_REFUSAL, needle


def test_v2_exits_through_require_v1(funnel):
    with pytest.raises(SystemExit,
                       match="validate_component.py: --instrument v2 is not wired yet"):
        vc.main([*BASE, "--instrument", "v2"])
    assert funnel == {"resolved": 0, "stages": []}


def test_an_unknown_instrument_is_an_argparse_error(funnel):
    with pytest.raises(SystemExit) as exc:
        vc.main([*BASE, "--instrument", "v9"])
    assert exc.value.code == 2
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_validate_component_instrument.py`
Expected: FAIL — `AttributeError: ... has no attribute 'V3_FUNNEL_REFUSAL'`, the `--instrument` tests on argparse's `unrecognized arguments` (exit 2), and the default test on `args.instrument` missing.

- [ ] **Step 3: Implement in `scripts/backtest/validate_component.py`**

Beside the other `swingbot` imports (they carry `# noqa: E402`):

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli, contract  # noqa: E402
```

Below `DECIDED = ("win", "loss")`:

```python
_V3_YEARS = contract.resolve("v3").fold_test_years
#: v190 spec §4: Stage 2 is wired for exactly three folds with an absolute
#: GATE_MIN_IMPROVING_FOLDS = 2 (backtest_wf.py), and "2 improving" on five
#: folds would be looser than "2 of 3". No v3 stage threshold is frozen here.
V3_FUNNEL_REFUSAL = (
    "validate_component.py: --instrument v3 is refused. The funnel's Stage 2 is wired for "
    "exactly three folds with an absolute GATE_MIN_IMPROVING_FOLDS = 2, and Stage 3 reads "
    "v1's VALIDATION window; v3 has five folds "
    f"(test years {_V3_YEARS[0]}-{_V3_YEARS[-1]}) and a sealed holdout. A follow-up "
    "methodology spec must map Stage 2 and Stage 3 to five folds before the funnel accepts "
    "v3 (v190 spec §4). Run with --instrument v1 (the default).")
#: Instruments the funnel refuses outright, each with its own reason; any other
#: non-v1 instrument exits through require_v1.
_FUNNEL_REFUSALS = {"v3": V3_FUNNEL_REFUSAL}


def _instrument_gate(args) -> None:
    """Refuse every instrument but v1 before any data is selected (v190)."""
    spec = instrument_cli.spec_from_args(args)
    refusal = _FUNNEL_REFUSALS.get(spec.version)
    if refusal:
        raise SystemExit(refusal)
    instrument_cli.require_v1(spec, "validate_component.py", "a later methodology spec")
```

In `main`, two lines: `instrument_cli.add_instrument_arg(parser)` directly after `cache_dir_source.add_args(parser)`, and `_instrument_gate(args)` directly after `args = parser.parse_args(argv)` (before `cache_dir_source.resolve(args)`). Nothing else in `main` changes.

In `tests/backtesting/instrument/test_date_literal_guard.py`, delete the line
`"scripts/backtest/validate_component.py": "v100 acceptance funnel over stamped arm files; runs no backtest",`
from `NO_REPLAY`. The script now passes the live-script checks: it calls `add_instrument_arg` and reads the flag through `spec_from_args` / `require_v1`, and its only date-like text sits inside the refusal prose, which the scanner does not flag (it matches whole constants only; the year range is computed from the contract).

- [ ] **Step 4: Run the new file, the guard, the funnel's neighbours and the gate**

Run:
```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_validate_component_instrument.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_funnel.py
python scripts/dev/testrun.py changed --dry-run
python scripts/dev/complexity_gate.py
```
Expected: the three files `0 failed`, `0 xfailed`. Run every test file `changed --dry-run` lists that reaches `validate_component.py` with `testrun.py file` (its existing stage tests call `main` with no `--instrument` and must stay green). The gate exits 0; `main` does not grow (two plain calls), `_instrument_gate` ranks A.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtest_scripts/test_validate_component_instrument.py tests/backtesting/instrument/test_date_literal_guard.py
git commit -m "feat(funnel): v190 V190-11 -- validate_component --instrument; v3 refused until a methodology spec maps Stage 2/3 to five folds"
```
