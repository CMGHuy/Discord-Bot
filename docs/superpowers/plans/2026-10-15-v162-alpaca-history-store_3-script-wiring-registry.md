# v162 Alpaca history store, part 3: script wiring, provenance sidecar, registry key

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH12:" -A 600 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_3-script-wiring-registry.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§3 training switch, § Research discipline, Amendments "Registry rows are keyed by source", "Provenance is a sidecar", "One loader seam", "Ledger field is optional", Acceptance 5)
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts and the task ledger. Every task below implicitly includes them. Ledger part 3 outgrew the 1500-line cap: AH11 and AH12 are here, AH13–AH15 are in [`2026-10-15-v162-alpaca-history-store_3b-cache-dir-ledger-badge.md`](2026-10-15-v162-alpaca-history-store_3b-cache-dir-ledger-badge.md).

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows the main tree unchanged.
- The switch is AH10's `swingbot/core/marketdata/training_data.py`. The names this part uses, exactly as AH10 defines them: `DATA_SOURCES`, `select(name=None) -> str` (a `None` name means `"yfinance"` when env `BACKTEST_CACHE_DIR` is set, else `config.TRAINING_DATA_SOURCE`; `"alpaca"` raises `history_store.MissingStoreError` when the `daily` manifest is absent), `active()`, `reset()`, `load_daily(ticker)`, `available_tickers()` (sorted), `excluded()`, `exclusion_lines()` (`"excluded <TICKER>: <reason>"`), `provenance()`, `provenance_path(out) -> Path` (`<out>.provenance.json`), `write_provenance(out) -> Path`; and in `scripts/data/fetch_backtest_data.py`: `load_cached(ticker)` (delegates to `load_daily`), `add_data_source_arg(ap)` (`--data-source {alpaca,yfinance}`, default `None`), `apply_data_source(args) -> str`.
- **Process pools.** `training_data`'s selection lives in the parent process. A pool worker started with `spawn` (Windows, where backtests run) re-imports the module and would select the config default instead of the run's `--data-source`. Every pool whose workers read bars therefore gets `initializer=training_data.select, initargs=(training_data.active(),)`. Pools that receive ready frames need nothing.
- Tests in `tests/history_store/` rely on AH2's `conftest.py` (`scripts/data` and `scripts/ops` on `sys.path`; fixture `store_root` creates `tmp_path/"market_data"`, points `HISTORY_STORE_DIR` at it and returns it). Every test file here builds its store by hand in the index's manifest shape, resets the switch around each test with `training_data.reset()`, deletes `BACKTEST_CACHE_DIR` and pins `config.TRAINING_DATA_SOURCE`, exactly like AH10's `_fresh_switch` fixture.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Complexity: `python -m radon cc -s -n C <files>` lists no new function, and every legacy function it lists keeps the score in the Global Constraints.

# Phase C (continued): every training reader goes through the switch

### Task AH11: `run_backtest_range`: `--data-source`, hard error, sidecar, registry `data_source` key

**Model:** opus — wires a new switch through the legacy F(65) `main` without raising its score, and the registry key change decides which rows a merge replaces (the Amendment that keeps the yfinance and Alpaca populations apart).

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py` (imports at :29; `_build_asof_map` :88-102; `run_scenario_mode` frame loop :271-282; `build_registry_records` :416-445; `merge_registry` :448-458; `main` argparse :461-507, `--from-json` branch :518-534, normal-mode frame load :556-559, `--json`/`--trades-jsonl`/`--emit-registry` writes :660-674)
- Test: `tests/history_store/test_rbr_data_source.py`

**Interfaces:**
- Consumes (AH10): `fetch_backtest_data.add_data_source_arg`, `apply_data_source`, `load_cached`; `training_data.exclusion_lines`, `write_provenance`, `provenance_path`, `select`, `reset`; `history_store.MissingStoreError` (AH2).
- Produces (binding for AH15, AH23, AH24):
  - `build_registry_records(summaries, *, source, window, run_date, horizon=None, pass_wr=80.0, min_n=15, data_source: str = "yfinance") -> list[dict]`: every record gains `"data_source": data_source`.
  - `registry_key(rec: dict) -> tuple` = `(rec["source"], rec["strategy"], rec.get("horizon"), rec.get("data_source") or "yfinance")`. A missing (or null) value means `yfinance`.
  - `merge_registry(path, new_records)` replaces only rows with the same `registry_key`. Rows it keeps are written back unchanged (an old row never gains a `data_source` field). The file stays sorted by `(source, strategy, str(horizon), data_source)`, which leaves today's yfinance-only file in its current order.
  - `_report_exclusions() -> None`: prints `training_data.exclusion_lines()`, one per line.
  - `_write_provenance(json_out: str | None) -> None`: no-op on `None`, else `training_data.write_provenance(json_out)` and prints the sidecar path.
  - `_replay_data_source(json_in: str) -> str`: the `data_source` of `training_data.provenance_path(json_in)`, or `"yfinance"` when there is no sidecar (every pre-v162 `--json` file).
  - `_resolve_data_source(args) -> str` (private helper, called once from `main`): `--from-json` returns `_replay_data_source` and reads no bars (a conflicting `--data-source` exits with an error). Every other mode calls `apply_data_source(args)`, turns `MissingStoreError` into `SystemExit("error: <message naming the path>")`, and with `--validation` prints `VALIDATION_SOURCE_NOTICE`.
  - `VALIDATION_SOURCE_NOTICE: str` (module constant).
  - `_context_symbols(symbols) -> list[str]`: the context-only symbols (the sector ETFs of `sector_map("etfs")`) that `training_data.available_tickers()` holds, in input order. `_build_asof_map` loads only those, so a sector ETF absent from the store is never asked for and never becomes a `not in store` entry in `training_data.excluded()` or the sidecar. The data has no gap here: yfinance's cache lacks them too, and the as-of context already treats a missing ETF frame as absent. `SPY` (the benchmark) is **not** filtered: a run without it has no market context, and its `not in store` line is a real signal.
- Behaviour: a TRAIN run with no flag reads `TRAINING_DATA_SOURCE` (default `alpaca`), errors with no store, and writes `<out>.provenance.json` next to the `--json` and `--trades-jsonl` outputs. The `--json` file itself keeps the flat `{strategy: stats}` shape that `--from-json` replays.

**Why the sidecar is also written for `--trades-jsonl`:** §5 (AH23/AH24) builds its report from `--trades-jsonl` outputs, and each leg's file must say which data made it.

**Guardrail note:** `.claude/hooks/guardrails.py` `_rule_closed_preregistration` denies any Bash command that names this script together with a closed knob name (the list includes the literal word for a passing registry status). The commands below never put both on one line. Edit the file with the Edit tool, not with a shell heredoc that quotes its code.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_rbr_data_source.py`:

```python
"""v162 AH11: run_backtest_range reads one training-data source, stops when the
store is absent, writes a provenance sidecar next to every result file, and
keys registry rows by data_source so yfinance and Alpaca rows sit side by side."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import training_data

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "rbr_v162", ROOT / "scripts" / "backtest" / "run_backtest_range.py")
rbr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rbr)


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = np.r_[close[0], close[:-1]]
    idx = pd.DatetimeIndex(pd.bdate_range("2018-01-02", periods=n), name="Date")
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) + 0.5,
                         "Low": np.minimum(open_, close) - 0.5, "Close": close,
                         "Volume": np.full(n, 2_000_000.0)}, index=idx)


def _write_store(root, frames, statuses=None):
    """Hand-built daily store in the index's manifest shape."""
    statuses = statuses or {}
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    tickers = {}
    for ticker, frame in frames.items():
        frame.to_csv(folder / f"{ticker}.csv", index_label="Date", date_format="%Y-%m-%d")
        tickers[ticker] = {"status": statuses.get(ticker, "ok"), "start": "2016-01-01",
                           "first": str(frame.index[0].date()), "last": str(frame.index[-1].date()),
                           "rows": len(frame), "sha256": "0" * 64,
                           "fetched_at": "2026-10-18T06:12:40Z",
                           "identity": {"status": "ok", "median_ratio": 1.0,
                                        "overlap": len(frame), "dropped_before": None}}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all",
         "updated_at": "2026-10-18T06:31:02Z", "hash": "f" * 64, "tickers": tickers}),
        encoding="utf-8")


def _row(source="strategy", strategy="RSI", horizon=None, **extra):
    row = {"source": source, "strategy": strategy, "horizon": horizon, "status": "WEAK",
           "n": 40, "win_rate": 55.0, "expectancy_r": 0.1, "window": "w", "run_date": "d"}
    row.update(extra)
    return row


# --- registry key ------------------------------------------------------------------

def test_registry_key_treats_a_missing_or_null_source_as_yfinance():
    assert rbr.registry_key(_row()) == ("strategy", "RSI", None, "yfinance")
    assert rbr.registry_key(_row(data_source=None))[3] == "yfinance"
    assert rbr.registry_key(_row(data_source="alpaca"))[3] == "alpaca"


def test_build_registry_records_stamps_the_data_source():
    summaries = [{"strategy": "RSI", "n": 100, "win_rate": 60.0, "expectancy_r": 0.2}]
    default = rbr.build_registry_records(summaries, source="strategy", window="w", run_date="d")
    alpaca = rbr.build_registry_records(summaries, source="strategy", window="w", run_date="d",
                                        data_source="alpaca")
    assert default[0]["data_source"] == "yfinance"
    assert alpaca[0]["data_source"] == "alpaca"


def test_merge_keeps_both_populations_and_never_rewrites_an_old_row(tmp_path):
    path = tmp_path / "reg.json"
    old = _row(window="old")
    path.write_text(json.dumps([old]), encoding="utf-8")
    merged = rbr.merge_registry(path, [_row(window="alpaca", data_source="alpaca")])
    assert [r["window"] for r in merged] == ["old", "alpaca"]
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk[0] == old and "data_source" not in on_disk[0]


def test_merge_replaces_only_the_same_source(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps([_row(window="old"), _row(window="a1", data_source="alpaca")]),
                    encoding="utf-8")
    merged = rbr.merge_registry(path, [_row(window="y2", data_source="yfinance")])
    assert sorted(r["window"] for r in merged) == ["a1", "y2"]


# --- provenance sidecar ------------------------------------------------------------

def test_replay_source_reads_the_sidecar_and_defaults_to_yfinance(tmp_path):
    out = tmp_path / "res.json"
    out.write_text("{}", encoding="utf-8")
    assert rbr._replay_data_source(str(out)) == "yfinance"
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    assert rbr._replay_data_source(str(out)) == "alpaca"


def test_write_provenance_is_a_noop_without_a_path_and_writes_the_sidecar(store_root, tmp_path):
    _write_store(store_root, {"AAA": _frame(30)})
    training_data.select("alpaca")
    rbr._write_provenance(None)
    assert not list(tmp_path.glob("*.provenance.json"))
    out = tmp_path / "res.json"
    rbr._write_provenance(str(out))
    side = json.loads(training_data.provenance_path(out).read_text(encoding="utf-8"))
    assert (side["data_source"], side["manifest_hash"]) == ("alpaca", "f" * 64)


def test_report_exclusions_prints_every_left_out_ticker(store_root, capsys):
    _write_store(store_root, {"AAA": _frame(30), "BBB": _frame(30)},
                 {"BBB": "flagged: price-mismatch"})
    training_data.select("alpaca")
    rbr._report_exclusions()
    assert "excluded BBB: flagged: price-mismatch" in capsys.readouterr().out


def test_sector_etfs_missing_from_the_store_are_never_loaded(store_root, monkeypatch):
    from swingbot.core.backtesting import asof_context
    from swingbot.core.marketdata import universe
    _write_store(store_root, {"SPY": _frame(30), "XLK": _frame(30), "AAA": _frame(30)})
    training_data.select("alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(rbr, "_SPY_CACHE", {})
    monkeypatch.setattr(universe, "sector_map",
                        lambda name: {"XLK": "Technology", "XLE": "Energy"} if name == "etfs" else {})
    seen = {}
    monkeypatch.setattr(asof_context, "build_asof",
                        lambda frames, spy, **kw: seen.update(kw["sector_etf_frames"]) or {})
    rbr._build_asof_map(["AAA"], {"AAA": _frame(30)}, None)
    assert sorted(seen) == ["XLK"]                       # XLE is not in the store: skipped
    assert training_data.excluded() == {}                # no context-only noise


# --- source resolution -------------------------------------------------------------

def _ns(**over):
    base = {"from_json": None, "data_source": "alpaca", "validation": False}
    base.update(over)
    return argparse.Namespace(**base)


def test_alpaca_without_a_store_stops_naming_the_manifest(store_root):
    with pytest.raises(SystemExit) as exc:
        rbr._resolve_data_source(_ns())
    assert str(exc.value).startswith("error: ") and "_manifest.json" in str(exc.value)


def test_validation_prints_the_budget_notice(store_root, capsys):
    _write_store(store_root, {"AAA": _frame(30)})
    assert rbr._resolve_data_source(_ns(validation=True)) == "alpaca"
    assert rbr.VALIDATION_SOURCE_NOTICE in capsys.readouterr().out


def test_from_json_replays_the_sidecar_and_reads_no_store(tmp_path):
    out = tmp_path / "res.json"
    out.write_text("{}", encoding="utf-8")
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    assert rbr._resolve_data_source(_ns(from_json=str(out), data_source=None)) == "alpaca"
    with pytest.raises(SystemExit, match="cannot relabel"):
        rbr._resolve_data_source(_ns(from_json=str(out), data_source="yfinance"))


# --- main ----------------------------------------------------------------------------

def test_main_without_a_store_errors_before_any_backtest(store_root, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["rbr", "--train", "--data-source", "alpaca"])
    monkeypatch.setattr(rbr, "run_backtest", lambda *a, **k: pytest.fail("ran a backtest"))
    with pytest.raises(SystemExit) as exc:
        rbr.main()
    assert "_manifest.json" in str(exc.value)


def test_from_json_main_emits_rows_stamped_with_the_replayed_source(tmp_path, monkeypatch):
    out = tmp_path / "res.json"
    out.write_text(json.dumps({"RSI": {"n_eval": 40, "win_rate": 55.0, "expectancy_r": 0.2}}),
                   encoding="utf-8")
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    reg = tmp_path / "reg.json"
    monkeypatch.setattr(sys, "argv", ["rbr", "--train", "--from-json", str(out),
                                      "--emit-registry", str(reg), "--run-date", "2026-10-15"])
    rbr.main()
    rows = json.loads(reg.read_text(encoding="utf-8"))
    assert [(r["strategy"], r["data_source"]) for r in rows] == [("RSI", "alpaca")]


def test_train_run_writes_sidecars_naming_source_and_exclusions(store_root, tmp_path,
                                                                monkeypatch, capsys):
    _write_store(store_root, {"AAA": _frame(), "BBB": _frame(seed=8)},
                 {"BBB": "flagged: price-mismatch"})
    monkeypatch.chdir(tmp_path)                      # backtest_range_summary.txt lands here
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA", "BBB"])
    out, trades = tmp_path / "res.json", tmp_path / "trades.jsonl"
    monkeypatch.setattr(sys, "argv", ["rbr", "--from", "2019-01-01", "--to", "2020-03-31",
                                      "--strategy", "RSI", "--context", "off",
                                      "--data-source", "alpaca", "--json", str(out),
                                      "--trades-jsonl", str(trades)])
    rbr.main()
    assert set(json.loads(out.read_text(encoding="utf-8"))) == {"RSI"}   # flat shape kept
    for path in (out, trades):
        side = json.loads(training_data.provenance_path(path).read_text(encoding="utf-8"))
        assert side["data_source"] == "alpaca"
        assert side["excluded"]["BBB"] == "flagged: price-mismatch"
    assert "excluded BBB: flagged: price-mismatch" in capsys.readouterr().out
```

The synthetic frames start in 2018 and the window is 2019-01-01..2020-03-31. RSI may or may not trade on them; the test checks only the source, the exclusions and the file shapes, never a trade count. `SPY` is not in the store, so `_market_frame` prints its existing "no market context" warning and `SPY` may also appear in `excluded` as `not in store`; the assertions therefore look up `BBB` only.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_rbr_data_source.py`
Expected: FAIL with `AttributeError: module 'rbr_v162' has no attribute 'registry_key'` (and the other new names).

- [ ] **Step 3: Imports and the notice**

In `$WT/scripts/backtest/run_backtest_range.py`, replace the line

```python
from fetch_backtest_data import load_cached, load_watchlist
```

with

```python
from fetch_backtest_data import add_data_source_arg, apply_data_source, load_cached, load_watchlist
```

and add, after the line `from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason`:

```python
from swingbot.core.marketdata import training_data
from swingbot.core.marketdata.history_store import MissingStoreError
```

Below `_SPY_CACHE: dict = {}` add:

```python
#: Printed on every --validation run (spec § Research discipline): the switch
#: never buys a component a second VALIDATION shot.
VALIDATION_SOURCE_NOTICE = (
    "NOTE: a new data source resets no VALIDATION budget. A component whose "
    "validation shot was spent on yfinance has spent it, and every closed "
    "pre-registration stays closed (backtest-methodology.md).")
```

- [ ] **Step 4: Source, exclusion and sidecar helpers**

Add these functions directly above `def build_registry_records(` (after `registry_refusal`):

```python
def _replay_data_source(json_in: str) -> str:
    """The source a previous --json output was measured on: its sidecar's
    data_source, or yfinance for a file written before v162 (no sidecar)."""
    sidecar = training_data.provenance_path(json_in)
    if not sidecar.exists():
        return "yfinance"
    return json.loads(sidecar.read_text(encoding="utf-8")).get("data_source") or "yfinance"


def _resolve_data_source(args) -> str:
    """The run's one training-data source (spec §3), chosen before any bar is
    read. --from-json replays what its sidecar recorded and reads no bars; every
    other mode selects --data-source (else TRAINING_DATA_SOURCE) and stops with
    an error naming the missing path when the Alpaca store is absent."""
    if args.from_json:
        replayed = _replay_data_source(args.from_json)
        if args.data_source not in (None, replayed):
            raise SystemExit(f"error: {args.from_json} was measured on {replayed}; "
                             f"--data-source {args.data_source} cannot relabel it")
        return replayed
    try:
        source = apply_data_source(args)
    except MissingStoreError as exc:
        raise SystemExit(f"error: {exc}") from exc
    if args.validation:
        print(VALIDATION_SOURCE_NOTICE, flush=True)
    return source


def _report_exclusions() -> None:
    """Every ticker the training data left out, with its reason (spec §3)."""
    for line in training_data.exclusion_lines():
        print(line, flush=True)


def _write_provenance(json_out: str | None) -> None:
    """<out>.provenance.json next to a result file; the result shape is unchanged."""
    if not json_out:
        return
    path = training_data.write_provenance(json_out)
    print(f"Wrote provenance to {path}", flush=True)
```

- [ ] **Step 5: Registry rows carry and key on `data_source`**

In `build_registry_records`, add the keyword `data_source="yfinance"` after `min_n=15` in the signature, append this sentence to its docstring: "`data_source` (v162) names the bars the summaries were measured on.", and in the `recs.append({...})` literal change the last line

```python
                     "window": window, "run_date": run_date})
```

to

```python
                     "window": window, "run_date": run_date,
                     "data_source": data_source})
```

(The `candidate` dict handed to `registry_refusal` stays as it is.)

Replace `merge_registry` with these two functions:

```python
def registry_key(rec: dict) -> tuple:
    """(source, strategy, horizon, data_source); a row with no data_source was
    measured before v162 and means yfinance (schema-evolution: an added field,
    old rows never rewritten)."""
    return (rec["source"], rec["strategy"], rec.get("horizon"),
            rec.get("data_source") or "yfinance")


def merge_registry(path, new_records):
    """Merge records into the registry JSON, replacing same-key entries only.

    The key includes data_source, so an Alpaca row sits beside the yfinance
    row of the same (source, strategy, horizon) instead of overwriting it."""
    path = Path(path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    new_keys = {registry_key(r) for r in new_records}
    kept = [r for r in existing if registry_key(r) not in new_keys]
    merged = sorted(kept + new_records,
                    key=lambda r: (r["source"], r["strategy"], str(r.get("horizon")),
                                   registry_key(r)[3]))
    path.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    return merged
```

`run_confluence_validation.py`, `measure_fib_confluence.py` and `measure_v113.py` import these names. They get the `yfinance` default, which is right for them (AH12 pins the first to yfinance, and the ext-cache scripts run with `BACKTEST_CACHE_DIR` set).

- [ ] **Step 6: Wire `main` and `run_scenario_mode`: one added line per call, no new branch in either**

In `main`, after the `--from-json` `add_argument(...)` call (the last one before `args = ap.parse_args()`), add:

```python
    add_data_source_arg(ap)
```

After the two lines

```python
    if args.emit_registry and not args.run_date:
        ap.error("--emit-registry requires --run-date")
```

add:

```python
    data_source = _resolve_data_source(args)
```

It goes before the window checks on purpose: a missing store errors before `_check_record_blocked`, the watchlist query or any frame load.

In the `--from-json` branch, and again in the `if args.emit_registry:` block at the end of `main`, change

```python
            run_date=args.run_date, min_n=min_n, pass_wr=args.pass_wr))
```

to

```python
            run_date=args.run_date, min_n=min_n, pass_wr=args.pass_wr,
            data_source=data_source))
```

(match the indentation of each call site: the `--from-json` one is inside the `if args.from_json:` block, the other inside `if args.emit_registry:`).

In normal mode, after

```python
    frames = {ticker: frame for ticker, frame in frames.items() if frame is not None}
```

add:

```python
    _report_exclusions()
```

Directly above the final `if args.emit_registry:` block (after the `if args.trades_jsonl:` block), add:

```python
    _write_provenance(args.json_out)
    _write_provenance(args.trades_jsonl)
```

In `_build_asof_map`, replace

```python
    etf_frames = {etf: frame for etf in sector_of_etf
                  if (frame := load_cached(etf)) is not None}
```

with

```python
    etf_frames = {etf: frame for etf in _context_symbols(sector_of_etf)
                  if (frame := load_cached(etf)) is not None}
```

and add above `_build_asof_map`:

```python
def _context_symbols(symbols) -> list:
    """Context-only symbols (sector ETFs) the selected training data holds.
    One absent from the store is skipped rather than loaded: loading it would
    record a 'not in store' exclusion for a ticker the run never trades
    (yfinance's cache lacks them too), burying the real exclusions in the
    provenance sidecar. Under yfinance the list is the cache's own files, so
    nothing changes there."""
    available = set(training_data.available_tickers())
    return [symbol for symbol in symbols if symbol in available]
```

`measure_alert_density.py`, `measure_fib_confluence.py` and `measure_bearish_arms.py` build their as-of context through this same `_build_asof_map`, so they get the filter too.

In `run_scenario_mode`, directly above the `print(f"loaded {len(frames)}/{len(tickers)} cached tickers "` line, add:

```python
    _report_exclusions()
```

and directly after the `stats = _scenario_stats(...)` call (the closing `record_blocked=record_blocked)` line), add:

```python
    _write_provenance(trades_jsonl)
```

The `_SPY_CACHE` benchmark and `_build_asof_map`'s sector ETFs load through `load_cached` too. Under `alpaca` they come from the store or not at all: a benchmark missing from the store prints the existing "no market context" warning and shows in the exclusion lines as `not in store`. Sector ETFs the store lacks are skipped by `_context_symbols` and recorded nowhere. No per-ticker fallback to yfinance is added, because a run never mixes sources.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_rbr_data_source.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_emit_registry.py`
Expected: PASS, 0 failed. Rows built without a `data_source` key count as yfinance and still replace each other.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/backtest/run_backtest_range.py`
Expected: only the legacy entries `main` F (65), `run_scenario_mode` C (19) and `pool` C (15), each with its score unchanged. No new function is listed.

- [ ] **Step 9: Commit**

```bash
git -C $WT add scripts/backtest/run_backtest_range.py tests/history_store/test_rbr_data_source.py
git -C $WT commit -m "feat(v162): backtest range runner -- --data-source, hard error without the store, provenance sidecar, registry rows keyed by data_source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

### Task AH12: `tune_strategy` and the `load_cached`/glob scripts

**Model:** sonnet — twelve mechanical rewires that follow one pattern (flag, select, list from the switch, pool initializer, sidecar), each pinned by a test; the one judgement call (pinning the VALIDATION-only confluence replay to yfinance) is made below.

**Files:**
- Modify: `scripts/backtest/tune_strategy.py` (imports :24; `main` :113-180)
- Modify: `scripts/backtest/run_confluence_validation.py` (`main` :151-245)
- Modify: `scripts/reports/parity_exits.py` (imports :27-40; `main` :70)
- Modify: `scripts/backtest/measure_arms.py` (`UNIVERSE_*` comment :31-37; `cache_listing` :41-44; `cached_universe` :47-55; `_run_arm_all` :101-118; `population_symbols` :127-139; `main` :231-262)
- Modify: `scripts/backtest/measure_alert_density.py` (`load_frames` :345-360; `main` :514-631)
- Modify: `scripts/backtest/measure_acceptance_exits.py` (`cache_universe` :88-94; `build_rows` :97-122; `main` :211-230)
- Modify: `scripts/backtest/measure_factor_lift.py` (`CACHE_DIR` :33; frame load :153-154; `__main__` block :221-256)
- Modify: `scripts/backtest/measure_fvg_bullish_diagnostic.py` (`_worker` :133-145; `run_replay` pool :176-178; `load_or_replay` :225-236; `main` :249-257)
- Modify: `scripts/backtest/quarterly_revalidation.py` (`data_quality_sweep` :67-86)
- Modify: `scripts/backtest/tune_confluence_gates.py` (`CACHE_DIR` :35; `main` :74-79)
- Modify: `scripts/backtest/tune_exit_v2.py` (`CACHE_DIR` :21; `main` :51-61)
- Modify: `scripts/data/fill_regime_allow.py` (imports :54; `main` :209-251)
- Test: `tests/history_store/test_script_data_source.py`

**Interfaces:**
- Consumes (AH10): `fetch_backtest_data.add_data_source_arg`, `apply_data_source`, `load_cached`; `training_data.select`, `active`, `reset`, `load_daily`, `available_tickers`, `exclusion_lines`, `provenance`, `provenance_path`, `write_provenance`; `history_store.MissingStoreError` (AH2).
- Produces (binding for AH16): the `tune_strategy.py --json` payload gains `"data_source": str` and `"provenance": dict` (`training_data.provenance()`), and the file gets a `<out>.provenance.json` sidecar. Payload shape otherwise unchanged (`strategy`, `gate`, `grid`, `best`).
- Produces (private, this task only): `tune_strategy._select_source(args) -> str`; `run_confluence_validation._pin_yfinance() -> None`; `measure_arms._available() -> set[str]` and `_in_training_data(symbol: str, available: set[str]) -> bool`; `measure_factor_lift._training_frames() -> dict` and `main(argv=None) -> int`; `measure_fvg_bullish_diagnostic._session_calendar()`; `tune_confluence_gates._sampled_frames() -> tuple[dict, int]`; `tune_exit_v2._frames() -> dict`. Every `main` touched here takes `argv=None` and passes it to `parse_args`.

**The rules this task applies:**
- Every script below accepts `--data-source {alpaca,yfinance}` and calls `apply_data_source(args)` directly after `parse_args`, before any refusal check, watchlist query or frame load. With no store, `alpaca` fails there and names the missing manifest.
- Ticker lists that came from globbing `data/backtest_cache/*.csv` come from `training_data.available_tickers()`. Under `yfinance` that is the same glob (stems of `backtest_cache.CACHE_DIR`), so a yfinance run lists exactly what it listed before.
- Pools whose workers read bars get `initializer=training_data.select, initargs=(training_data.active(),)` (part header, "Process pools"). Pools that receive frames (`measure_alert_density`, `tune_confluence_gates`, `run_confluence_validation`) need none.
- Every JSON a script writes gets `training_data.write_provenance(<path>)` beside it.
- **Two documented exceptions:**
  - `run_confluence_validation.py` replays only the VALIDATION window, whose shot is spent, and resumes from yfinance chunk files. A new source buys no second run (spec § Research discipline), and Alpaca bars must never mix into those chunks, so the script is **pinned to yfinance** and gets no `--data-source` flag.
  - `quarterly_revalidation.py` is an orchestrator. Its subprocesses (`wf_run.py`, `permutation_test.py`) read bars through `backtest_wf._frame_for` (AH13) at the config value, so its own data-quality sweep follows the config value too. It gets no flag; switching it is the `.env` line.
- **Not touched, by design:** `measure_bearish_arms.py`, `measure_fib_diagnostic.py`, `measure_confluence_stop.py`, `measure_fib_extension.py` and `measure_strategy_arm.py` read through `load_cached`, `measure_arms` or `backtest_wf._frame_for`, so they follow `TRAINING_DATA_SOURCE` (or yfinance when `BACKTEST_CACHE_DIR` is set) without a flag. `scripts/reports/audit_quality_score.py`, `parity_sizing.py`, `runner_headroom.py` and `swingbot/core/backtesting/arms/compression_research.py` audit the yfinance cache file by file and stay on it.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_script_data_source.py`:

```python
"""v162 AH12: tune_strategy and every load_cached/glob script read through the
training-data switch. They take --data-source, refuse to start without the
Alpaca store, list tickers from the selected source, hand pool workers the
selection, and stamp provenance on what they write."""
import concurrent.futures
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import backtest_cache, training_data
from swingbot.core.marketdata.history_store import MissingStoreError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))   # sibling imports (measure_arms, ...)


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tune = _load("scripts/backtest/tune_strategy.py", "tune_v162")
rcv = _load("scripts/backtest/run_confluence_validation.py", "rcv_v162")
parity = _load("scripts/reports/parity_exits.py", "parity_v162")
ma = _load("scripts/backtest/measure_arms.py", "ma_v162")
density = _load("scripts/backtest/measure_alert_density.py", "density_v162")
mae = _load("scripts/backtest/measure_acceptance_exits.py", "mae_v162")
lift = _load("scripts/backtest/measure_factor_lift.py", "lift_v162")
fvg = _load("scripts/backtest/measure_fvg_bullish_diagnostic.py", "fvg_v162")
quarterly = _load("scripts/backtest/quarterly_revalidation.py", "quarterly_v162")
gates = _load("scripts/backtest/tune_confluence_gates.py", "gates_v162")
exits = _load("scripts/backtest/tune_exit_v2.py", "exits_v162")
regime = _load("scripts/data/fill_regime_allow.py", "regime_v162")


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=40, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-02", periods=n), name="Date")
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close,
                         "Volume": np.full(n, 1_000_000.0)}, index=idx)


def _write_store(root, frames, statuses=None):
    statuses = statuses or {}
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    tickers = {}
    for ticker, frame in frames.items():
        frame.to_csv(folder / f"{ticker}.csv", index_label="Date", date_format="%Y-%m-%d")
        tickers[ticker] = {"status": statuses.get(ticker, "ok"), "start": "2016-01-01",
                           "first": str(frame.index[0].date()), "last": str(frame.index[-1].date()),
                           "rows": len(frame), "sha256": "0" * 64,
                           "fetched_at": "2026-10-18T06:12:40Z",
                           "identity": {"status": "ok", "median_ratio": 1.0,
                                        "overlap": len(frame), "dropped_before": None}}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all",
         "updated_at": "2026-10-18T06:31:02Z", "hash": "f" * 64, "tickers": tickers}),
        encoding="utf-8")


@pytest.fixture
def alpaca_store(store_root):
    _write_store(store_root, {"AAA": _frame(), "BBB": _frame(seed=8), "SPY": _frame(seed=9)},
                 {"BBB": "flagged: price-mismatch"})
    return store_root


@pytest.fixture
def yf_cache(tmp_path, monkeypatch):
    folder = tmp_path / "backtest_cache"
    folder.mkdir()
    for ticker, seed in (("AAA", 1), ("BBB", 2), ("SPY", 3)):
        _frame(seed=seed).to_csv(folder / f"{ticker}.csv", index_label="Date")
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", folder)
    return folder


# --- every wired script refuses to start without the store ----------------------------

def _first(values):
    return str(sorted(values)[0])


REFUSALS = [
    (tune, lambda: ["--strategy", "RSI"]),
    (parity, lambda: []),
    (ma, lambda: ["--knob", "x=1", "--stage", "pilot", "--out", "o.json"]),
    (density, lambda: ["--train"]),
    (mae, lambda: ["--arm", _first(mae.CELLS), "--stage", _first(mae._STAGES)]),
    (lift, lambda: ["--train"]),
    (fvg, lambda: []),
    (gates, lambda: []),
    (exits, lambda: []),
    (regime, lambda: []),
]


@pytest.mark.parametrize("module, argv", REFUSALS, ids=lambda v: getattr(v, "__name__", ""))
def test_alpaca_without_a_store_stops_before_any_work(module, argv, store_root):
    with pytest.raises((SystemExit, MissingStoreError)) as exc:
        module.main([*argv(), "--data-source", "alpaca"])
    assert "_manifest.json" in str(exc.value)


def test_tune_strategy_error_is_a_clean_exit_message(store_root):
    with pytest.raises(SystemExit) as exc:
        tune.main(["--strategy", "RSI", "--data-source", "alpaca"])
    assert str(exc.value).startswith("error: ")


# --- tune_strategy payload ------------------------------------------------------------

def test_tune_payload_and_sidecar_name_the_source(alpaca_store, tmp_path, monkeypatch):
    stats = {"n_eval": 31, "win_rate": 55.0, "expectancy_r": 0.1, "excluded_share": 0.1}
    monkeypatch.setattr(tune, "run_config", lambda *a, **k: dict(stats))
    monkeypatch.setattr(tune, "load_watchlist", lambda: ["AAA", "BBB"])
    out = tmp_path / "grid.json"
    tune.main(["--strategy", "RSI", "--grid", "rsi_dip=45", "--data-source", "alpaca",
               "--json", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["data_source"] == "alpaca"
    assert payload["provenance"]["excluded"]["BBB"] == "flagged: price-mismatch"
    assert set(payload) == {"strategy", "gate", "grid", "best", "data_source", "provenance"}
    side = json.loads(training_data.provenance_path(out).read_text(encoding="utf-8"))
    assert side["data_source"] == "alpaca"


# --- ticker listings come from the selected source -------------------------------------

def test_measure_arms_listing_follows_the_source(alpaca_store, yf_cache, monkeypatch):
    training_data.select("yfinance")
    assert ma.cache_listing() == ["AAA", "BBB", "SPY"]
    training_data.select("alpaca")
    assert ma.cache_listing() == ["AAA", "SPY"]                 # BBB is flagged
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    assert ma.cached_universe() == ["AAA", "SPY"]


def test_acceptance_exits_universe_follows_the_source(alpaca_store):
    training_data.select("alpaca")
    assert mae.cache_universe() == ["AAA", "SPY"]


def test_factor_lift_and_grid_frames_follow_the_source(alpaca_store, yf_cache):
    training_data.select("alpaca")
    assert sorted(lift._training_frames()) == ["AAA", "SPY"]
    assert sorted(exits._frames()) == ["AAA", "SPY"]
    training_data.select("yfinance")
    frames, total = gates._sampled_frames()
    assert (sorted(frames), total) == (["AAA"], 3)             # every 3rd of AAA, BBB, SPY


def test_quarterly_sweep_visits_only_trainable_tickers(alpaca_store, monkeypatch):
    from swingbot.core.marketdata import universe
    seen = []
    monkeypatch.setattr(universe, "data_quality_issues",
                        lambda df, ticker: seen.append(ticker) or (["gap"] if ticker == "AAA" else []))
    training_data.select("alpaca")
    assert quarterly.data_quality_sweep() == {"AAA": ["gap"]}
    assert seen == ["AAA", "SPY"]


def test_fvg_calendar_comes_from_the_training_spy(alpaca_store):
    training_data.select("alpaca")
    assert len(fvg._session_calendar()) == 40


# --- pool workers inherit the selection ----------------------------------------------

class _FakePool:
    seen: dict = {}

    def __init__(self, max_workers=None, initializer=None, initargs=()):
        _FakePool.seen = {"initializer": initializer, "initargs": initargs}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        future = concurrent.futures.Future()
        future.set_result(fn(*args))
        return future


def test_measure_arms_pool_gets_the_selection(yf_cache, monkeypatch):
    training_data.select("yfinance")
    monkeypatch.setattr(ma, "ProcessPoolExecutor", _FakePool)
    monkeypatch.setattr(ma, "_worker", lambda task: (task[0], []))
    ma._run_arm_all("x", ["AAA", "BBB"], [], [], None, {}, 2, None, [0], 2)
    assert _FakePool.seen == {"initializer": training_data.select, "initargs": ("yfinance",)}


def test_acceptance_exits_pool_gets_the_selection(yf_cache, tmp_path, monkeypatch):
    training_data.select("yfinance")
    monkeypatch.setattr(mae, "ProcessPoolExecutor", _FakePool)
    monkeypatch.setattr(mae, "_worker", lambda task: (task[1], []))
    monkeypatch.setattr(mae, "_resolve_replay_workers", lambda workers: 2)
    monkeypatch.setattr(mae, "LOG_DIR", tmp_path)
    mae.build_rows(_first(mae.CELLS), ("2020-01-01", "2023-12-31"), [], workers=2)
    assert _FakePool.seen == {"initializer": training_data.select, "initargs": ("yfinance",)}


# --- the VALIDATION-only replay is pinned to yfinance --------------------------------

def test_confluence_validation_is_pinned_to_yfinance(store_root, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["rcv"])
    monkeypatch.setattr(rcv, "load_watchlist", lambda: [])
    monkeypatch.setattr(rcv, "CHUNK_DIR", tmp_path / "chunks")
    monkeypatch.setattr(rcv, "RESULTS_PATH", tmp_path / "rcv.json")
    rcv.main()                                   # no store, config says alpaca: still runs
    assert training_data.active() == "yfinance"
    side = json.loads(training_data.provenance_path(tmp_path / "rcv.json").read_text(encoding="utf-8"))
    assert side["data_source"] == "yfinance"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_script_data_source.py`
Expected: FAIL (`main() takes 0 positional arguments`, missing `_training_frames`, `_sampled_frames`, `_frames`, `_session_calendar`, no initializer seen, `MissingStoreError` from the confluence replay).

- [ ] **Step 3: `tune_strategy.py`**

Replace

```python
from fetch_backtest_data import load_cached, load_watchlist
```

with

```python
from fetch_backtest_data import add_data_source_arg, apply_data_source, load_cached, load_watchlist
from swingbot.core.marketdata import training_data
from swingbot.core.marketdata.history_store import MissingStoreError
```

Add above `def main`:

```python
def _select_source(args) -> str:
    """Pick the training bars before any is read. A missing Alpaca store stops
    the grid with an error naming the path (spec §3), never a zero-ticker grid."""
    try:
        return apply_data_source(args)
    except MissingStoreError as exc:
        raise SystemExit(f"error: {exc}") from exc


def _report_exclusions() -> None:
    for line in training_data.exclusion_lines():
        print(line, flush=True)
```

In `main`: change `def main():` to `def main(argv=None):`. Directly before `args = ap.parse_args()` add `add_data_source_arg(ap)`, change that line to `args = ap.parse_args(argv)`, and directly after it add:

```python
    data_source = _select_source(args)
```

Replace

```python
    dfs = {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}
    print(f"{len(dfs)} tickers loaded from cache")
```

with

```python
    dfs = {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}
    print(f"{len(dfs)} tickers loaded from {data_source} training data")
    _report_exclusions()
```

In the `if args.json:` block, replace the payload literal and the write with:

```python
        payload = {
            "strategy": strategy,
            "gate": gate_report,
            "grid": [{"params": p, **s} for p, s in rows],
            "best": ({"params": best[0], **best[1]} if best else None),
            "data_source": data_source,
            "provenance": training_data.provenance(),
        }
        Path(args.json).write_text(json.dumps(payload, indent=2))
        training_data.write_provenance(args.json)
        print(f"Wrote results to {args.json}")
```

The admin Tuning job (`swingbot/admin/jobs.py`) runs this script with `--json`. AH16 passes `--data-source` and reads `data_source` back from this payload.

- [ ] **Step 4: `run_confluence_validation.py`: pinned to yfinance**

Add after the line `from run_backtest_range import build_registry_records, merge_registry`:

```python
from swingbot.core.marketdata import training_data
```

Add above `def main`:

```python
def _pin_yfinance() -> None:
    """This script replays only the VALIDATION window, whose shot is spent, and
    resumes from yfinance chunk files. A new data source buys no second run and
    must never mix into those chunks (spec § Research discipline), so the
    replay is pinned to yfinance and takes no --data-source flag."""
    training_data.select("yfinance")
    print("training data: yfinance (pinned: VALIDATION replay of a spent shot)", flush=True)
```

In `main`, directly before `CHUNK_DIR.mkdir(parents=True, exist_ok=True)` add `_pin_yfinance()`. After `out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")` add `training_data.write_provenance(out_path)`. The `--emit-registry` path is unchanged: `build_registry_records` stamps its default `yfinance`, which is what the committed results were measured on.

- [ ] **Step 5: `parity_exits.py`**

Add `import argparse` to the stdlib imports, and change `from fetch_backtest_data import load_cached, load_watchlist` to `from fetch_backtest_data import add_data_source_arg, apply_data_source, load_cached, load_watchlist`. Replace `def main():` and its first line with:

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description="simulate_exit vs the legacy exit loop, TRAIN window")
    add_data_source_arg(ap)
    apply_data_source(ap.parse_args(argv))
    tickers = sorted(load_watchlist())
```

- [ ] **Step 6: `measure_arms.py`**

Add `from swingbot.core.marketdata import training_data  # noqa: E402` after the `from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers` import. In the comment above `UNIVERSE_ENV`, replace `"cache" is every cached\n#: CSV in backtest_cache.CACHE_DIR` with `"cache" is every ticker\n#: the training data holds (v162: training_data.available_tickers())`. Replace `cache_listing` and `cached_universe` with:

```python
def cache_listing() -> list[str]:
    """Every ticker the selected training data holds, sorted (v162). Under
    yfinance that is the CSV stems of backtest_cache.CACHE_DIR, as before."""
    return training_data.available_tickers()


def _available() -> set[str]:
    return set(training_data.available_tickers())


def _in_training_data(symbol: str, available: set[str]) -> bool:
    """A ticker, or its yfinance file stem (=, ^ and / become _), is served."""
    from swingbot.core.marketdata.backtest_cache import cache_path
    return symbol in available or cache_path(symbol).stem in available


def cached_universe() -> list[str]:
    source = (os.environ.get(UNIVERSE_ENV) or "watchlist").strip().lower()
    if source not in UNIVERSE_SOURCES:
        raise ValueError(f"{UNIVERSE_ENV} must be one of {UNIVERSE_SOURCES}, got {source!r}")
    if source == "cache":
        return cache_listing()
    from run_backtest_range import _tickers_for_run
    available = _available()
    return sorted(ticker for ticker in _tickers_for_run(None) if _in_training_data(ticker, available))
```

In `population_symbols`, delete the line `from swingbot.core.marketdata.backtest_cache import cache_path` and replace its `return` with:

```python
    available = _available()
    return sorted(symbol for symbol in wanted if _in_training_data(symbol, available))
```

and change the docstring's "that have a cached frame" to "that the training data holds". In `_run_arm_all` replace

```python
        with ProcessPoolExecutor(max_workers=workers) as pool:
```

with

```python
        with ProcessPoolExecutor(max_workers=workers, initializer=training_data.select,
                                 initargs=(training_data.active(),)) as pool:
```

In `main`, directly before `args = parser.parse_args(argv)` add:

```python
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    add_data_source_arg(parser)
```

and directly after it add `apply_data_source(args)`. After `args.out.write_text(json.dumps(blob), encoding="utf-8")` add `training_data.write_provenance(args.out)`.

`validate_component.py` and `permutation_test.py` call `cached_universe()` and read frames through `load_frame`, so they see the same source. AH13 gives `validate_component.py` its own `--data-source`.

- [ ] **Step 7: `measure_alert_density.py`**

In `load_frames`, change the reason `"not in backtest cache"` to `"not in training data"`. In `main`, change `def main():` to `def main(argv=None):`. After the line `from swingbot.core.market.strategy_types import LEGACY_HORIZONS` inside `main`, add:

```python
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    from swingbot.core.marketdata import training_data
```

Directly before `args = ap.parse_args()` add `add_data_source_arg(ap)`, change it to `args = ap.parse_args(argv)`, and directly after it add `apply_data_source(args)`. Inside `if args.json_out:`, after `print(f"\nSaved {args.json_out}")`, add `training_data.write_provenance(args.json_out)`. The pool receives frames, so no initializer is needed.

- [ ] **Step 8: `measure_acceptance_exits.py`**

Add `from swingbot.core.marketdata import training_data  # noqa: E402` after the `_resolve_replay_workers` import. Replace `cache_universe` with:

```python
def cache_universe() -> list[str]:
    """Every ticker the selected training data holds. The pre-registered universe
    is 'every watchlist ticker with a cached frame'; the watchlist lives in
    Postgres (unreachable from a worktree) and the cache holds exactly those
    tickers, so the listing stands in for it (partner decision, 2026-10-08).
    v162: listed through training_data, the yfinance glob under yfinance."""
    return training_data.available_tickers()
```

In `build_rows` replace

```python
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
```

with

```python
        with ProcessPoolExecutor(max_workers=n_workers, initializer=training_data.select,
                                 initargs=(training_data.active(),)) as pool:
```

In `main`, directly before `args = parser.parse_args(argv)` add:

```python
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    add_data_source_arg(parser)
```

and directly after it add `apply_data_source(args)`.

- [ ] **Step 9: `measure_factor_lift.py`**

Replace the line `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))` with:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "data"))
```

Add after `from swingbot.core.scanning.regime import get_htf_bias`:

```python
from swingbot.core.marketdata import training_data
from fetch_backtest_data import add_data_source_arg, apply_data_source
```

Delete the line `CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backtest_cache"` and add in its place:

```python
def _training_frames() -> dict:
    """{ticker: daily frame} for every ticker the selected training data holds."""
    return {t: f for t in training_data.available_tickers()
            if (f := training_data.load_daily(t)) is not None}
```

In `collect_train_trades`, replace

```python
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
```

with `    frames = _training_frames()`. Replace the whole `if __name__ == "__main__":` block with a `main` function holding the same body, plus the switch:

```python
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--json", default=None)
    add_data_source_arg(ap)
    args = ap.parse_args(argv)
    apply_data_source(args)

    trades = collect_train_trades()
    print(f"\nTotal TRAIN trades: {len(trades)}", flush=True)

    lift = factor_lift_table(trades)
    print("\nFactor lift (median split, win rate above vs at-or-below):")
    for row in sorted(lift, key=lambda r: -abs(r["lift"])):
        flag = " (overlapping -- no real lift)" if row["overlapping"] else ""
        print(f"  {row['factor']:<30} n={row['n_above']+row['n_at_or_below']:>5} "
              f"lift={row['lift']:+.3f}{flag}")

    levels_table = level_table(trades)
    print("\nPer-level win rate:")
    for row in levels_table:
        print(f"  Level {row['level']}: n={row['n']:>5} "
              f"WR={row['win_rate']*100:5.1f}% "
              f"Wilson=[{row['wilson_lo']*100:5.1f}%, {row['wilson_hi']*100:5.1f}%]")

    if args.json:
        # Lean raw records (no per-trade `points` breakdown -- factor_lift
        # already summarizes it, and 4337 full breakdowns would bloat a
        # committed file) so a future re-weighting/re-leveling pass can
        # recompute factor_lift_table()/level_table() offline without
        # re-running the whole backtest again.
        raw_trades = [{"outcome": t["outcome"], "score": t["score"],
                      "level": t["level"], "target_count": t["target_count"]}
                     for t in trades]
        out = {"n_trades": len(trades), "factor_lift": lift,
              "level_table": levels_table, "trades": raw_trades}
        Path(args.json).write_text(json.dumps(out, indent=2, default=list))
        training_data.write_provenance(args.json)
        print(f"\nWrote {args.json}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

If `pd` is no longer used anywhere in the file after this change, keep the import anyway only if `git grep -n "pd\." $WT/scripts/backtest/measure_factor_lift.py` still prints a line; otherwise delete `import pandas as pd`.

- [ ] **Step 10: `measure_fvg_bullish_diagnostic.py`**

Add `from swingbot.core.marketdata import training_data  # noqa: E402` after the `from swingbot.scan_params import ScanParams` import. Add above `def _worker`:

```python
def _session_calendar():
    """The SPY trading calendar from the selected training data (v162). Under
    yfinance this reads the same SPY.csv measure_earnings_blackout.load_calendar did."""
    from swingbot.core.market.session import SessionCalendar
    spy = training_data.load_daily("SPY")
    if spy is None or spy.empty:
        raise SystemExit("SPY missing from the training data")
    return SessionCalendar.from_bar_index(spy.index)
```

In `_worker`, replace

```python
    from measure_earnings_blackout import load_calendar, reaction_positions
    from swingbot.core.marketdata import backtest_cache
```

with

```python
    from measure_earnings_blackout import reaction_positions
```

and `calendar = load_calendar(backtest_cache.CACHE_DIR)` with `calendar = _session_calendar()`. In `run_replay` replace

```python
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
```

with

```python
        with ProcessPoolExecutor(max_workers=n_workers, initializer=training_data.select,
                                 initargs=(training_data.active(),)) as pool:
```

In `load_or_replay`, after `target.write_text(json.dumps(blob), encoding="utf-8")` add `training_data.write_provenance(target)`. In `main`, directly before `args = parser.parse_args(argv)` add:

```python
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    add_data_source_arg(parser)
```

and directly after it add `apply_data_source(args)`.

- [ ] **Step 11: `quarterly_revalidation.py`**

Replace `data_quality_sweep` with:

```python
def data_quality_sweep() -> dict:
    """Data-quality issues per ticker of the training data. It follows
    TRAINING_DATA_SOURCE (v162) because the fold sweep and permutation test this
    script runs as subprocesses read bars at that value too; switching the
    quarterly run is the .env line, not a flag."""
    from swingbot.core.marketdata import training_data
    from swingbot.core.marketdata.universe import data_quality_issues

    print(f"\n[2/5] Data quality sweep over the {training_data.active()} training data...")
    issues = {}
    tickers = training_data.available_tickers()
    for ticker in tickers:
        df = training_data.load_daily(ticker)
        found = data_quality_issues(df, ticker) if df is not None else []
        if found:
            issues[ticker] = found
    if issues:
        print(f"  {len(issues)}/{len(tickers)} ticker(s) with data quality issues:")
        for ticker, found in issues.items():
            print(f"    {ticker}: {'; '.join(found)}")
    else:
        print(f"  clean -- {len(tickers)} ticker(s), no data quality issues found")
    return issues
```

`refresh_cache` (step 1 of the quarterly run) still refreshes `data/backtest_cache/`, which the live bot keeps using; it is unchanged.

- [ ] **Step 12: `tune_confluence_gates.py`**

Add `import argparse` to the imports, replace `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))` with

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "data"))
```

add after `from swingbot.core.planning.plan_engine import simulate_exit`:

```python
from swingbot.core.marketdata import training_data
from fetch_backtest_data import add_data_source_arg, apply_data_source
```

delete the `CACHE_DIR = ...` line, and add above `def main`:

```python
def _sampled_frames() -> tuple[dict, int]:
    """({ticker: frame} for every SAMPLE_EVERY-th training ticker, alphabetical,
    and the size of the full list)."""
    tickers = training_data.available_tickers()
    frames = {t: f for t in tickers[::SAMPLE_EVERY]
              if (f := training_data.load_daily(t)) is not None}
    return frames, len(tickers)
```

Replace the start of `main` up to and including the first `print`:

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description="confluence-gate grid over TRAIN")
    add_data_source_arg(ap)
    apply_data_source(ap.parse_args(argv))
    frames, total = _sampled_frames()
    print(f"tickers: {len(frames)} of {total} (every {SAMPLE_EVERY}th, "
          f"alphabetical) = {sorted(frames)}\ntrain: {TRAIN}  rule: {RULE}\n")
```

`pd` stays imported only if the file still uses it (`git grep -n "pd\." $WT/scripts/backtest/tune_confluence_gates.py`); otherwise delete `import pandas as pd`.

- [ ] **Step 13: `tune_exit_v2.py`**

Add `import argparse` to the imports, add `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "data"))` after the existing `sys.path.insert`, and add after `from swingbot.core.market.strategy_types import LEGACY_HORIZONS, STRATEGY_GATES`:

```python
from swingbot.core.marketdata import training_data
from fetch_backtest_data import add_data_source_arg, apply_data_source
```

Delete the `CACHE_DIR = ...` line and add above `def main`:

```python
def _frames() -> dict:
    """{ticker: daily frame} for every ticker the selected training data holds."""
    return {t: f for t in training_data.available_tickers()
            if (f := training_data.load_daily(t)) is not None}
```

Replace the start of `main` through the `strategies = ...` line with:

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description="v2 exit grid over TRAIN")
    ap.add_argument("strategies", nargs="*",
                    help="strategy names (default: all). Operational only: lets the grid "
                         "run in per-strategy chunks; the grid and selection rule are unchanged")
    add_data_source_arg(ap)
    args = ap.parse_args(argv)
    apply_data_source(args)
    # The grid explores trail/tp2 via the module defaults, so the adopted
    # Task 31 per-strategy overrides must not shadow the axes on a rerun.
    plan_engine.EXIT_V2_PARAMS.clear()
    frames = _frames()
    strategies = args.strategies or list(ALL_STRATEGIES)
```

(This keeps `python scripts/backtest/tune_exit_v2.py RSI MACD` working as before.) Drop `import pandas as pd` if nothing else in the file uses `pd.`.

- [ ] **Step 14: `fill_regime_allow.py`**

Change `from fetch_backtest_data import load_cached, load_watchlist` to `from fetch_backtest_data import add_data_source_arg, apply_data_source, load_cached, load_watchlist` and add `from swingbot.core.marketdata import training_data` after it. In `main`, directly before `args = p.parse_args(argv)` add `add_data_source_arg(p)`, and directly after it add `apply_data_source(args)`. Inside `if args.json:`, after the `args.json.write_text(...)` call, add `training_data.write_provenance(args.json)`.

- [ ] **Step 15: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_script_data_source.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: 0 failed. It selects the existing tests that reach these scripts (for example `tests/scripts/` tests of `measure_arms`, `measure_acceptance_exits` and `tune_strategy`). A test that globbed `data/backtest_cache` through `CACHE_DIR` and now fails should get its fixture moved to `backtest_cache.CACHE_DIR` plus `training_data.select("yfinance")`. Fix the test, never the rule.

- [ ] **Step 16: No direct cache read is left, and complexity holds**

Run: `git -C $WT grep -n "CACHE_DIR\|backtest_cache\"" -- scripts/backtest/tune_strategy.py scripts/backtest/measure_arms.py scripts/backtest/measure_acceptance_exits.py scripts/backtest/measure_factor_lift.py scripts/backtest/measure_fvg_bullish_diagnostic.py scripts/backtest/quarterly_revalidation.py scripts/backtest/tune_confluence_gates.py scripts/backtest/tune_exit_v2.py`
Expected: no output.

Run: `python -m radon cc -s -n C $WT/scripts/backtest/tune_strategy.py $WT/scripts/backtest/measure_arms.py $WT/scripts/backtest/measure_alert_density.py $WT/scripts/backtest/measure_acceptance_exits.py $WT/scripts/backtest/measure_factor_lift.py $WT/scripts/backtest/measure_fvg_bullish_diagnostic.py $WT/scripts/backtest/quarterly_revalidation.py $WT/scripts/backtest/tune_confluence_gates.py $WT/scripts/backtest/tune_exit_v2.py $WT/scripts/backtest/run_confluence_validation.py $WT/scripts/reports/parity_exits.py $WT/scripts/data/fill_regime_allow.py`
Expected: the legacy entries only, with unchanged scores (`tune_strategy.main` D (29), `run_config` C (17), plus whatever the same command printed at the task's base commit; run it once with `git -C $WT stash` before editing if in doubt). `measure_factor_lift.main` is new and must not be listed.

- [ ] **Step 17: Commit**

```bash
git -C $WT add scripts/backtest/tune_strategy.py scripts/backtest/run_confluence_validation.py scripts/reports/parity_exits.py scripts/backtest/measure_arms.py scripts/backtest/measure_alert_density.py scripts/backtest/measure_acceptance_exits.py scripts/backtest/measure_factor_lift.py scripts/backtest/measure_fvg_bullish_diagnostic.py scripts/backtest/quarterly_revalidation.py scripts/backtest/tune_confluence_gates.py scripts/backtest/tune_exit_v2.py scripts/data/fill_regime_allow.py tests/history_store/test_script_data_source.py
git -C $WT commit -m "feat(v162): grid and measure scripts read through the training-data switch -- --data-source, listings, pool initializers, provenance

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

