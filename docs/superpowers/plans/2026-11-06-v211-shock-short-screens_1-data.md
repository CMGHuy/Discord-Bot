# v211 — Shock-conditioned short screens, Part 1: data (V211-1..V211-3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md), § Track 2 → "The shared daily inputs".
**Index:** [`2026-11-06-v211-shock-short-screens_0-index.md`](2026-11-06-v211-shock-short-screens_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.

This part builds the two context files the ideas read and keeps them out of
every ticker listing: `CONTEXT_ONLY_STEMS` (V211-1), the `^VIX.csv` fetch
aligned to SPY sessions (V211-2), and the point-in-time `BREADTH_ATR1.csv`
builder (V211-3). The three tasks touch disjoint files and may run in
parallel; all three run in the worktree
`.claude/worktrees/2026-11-06-v211-shock-short-screens` (created by
whichever of them starts first, see V211-1 Step 0). No task here reaches
the network (fetchers are injected) or Postgres, and none runs the full
suite.

# Phase A — data

### Task V211-1: Context-only stems never listed as tickers

**Model:** sonnet — a constant, a filter in three readers and one helper, all pinned by the given tests; no judgment calls.

**Files:**
- Modify: `swingbot/core/backtesting/screen/context.py` (one constant + one helper, after `MIN_Z_COVERAGE`, line 31)
- Modify: `scripts/backtest/cache_dir_source.py:66-87` (`listing`, `load_all`, `cache_files`)
- Modify: `scripts/data/fetch_earnings_dates.py:46` (`cached_symbols`)
- Modify: `swingbot/core/marketdata/training_data.py:272-278` (`available_tickers`, yfinance branch) + a private `_CONTEXT_ONLY_STEMS` constant
- Create: `tests/backtest_scripts/test_context_stems_never_listed.py` (suite `backtest-scripts`)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `swingbot.core.backtesting.screen.context.CONTEXT_ONLY_STEMS: frozenset[str] = frozenset({"BREADTH_ATR1", "^VIX"})`; `swingbot.core.backtesting.screen.context.is_context_only(stem: str) -> bool`. V211-2 writes `^VIX.csv` and V211-3 writes `BREADTH_ATR1.csv` into the same cache dir the ticker readers glob; this task keeps them out. `swingbot.core.marketdata.training_data._CONTEXT_ONLY_STEMS` — the same set, private, pinned equal to the screen's by a test.

**Why:** spec § Track 2 "Where the two files live": `cache_dir_source.listing()` treats every `*.csv` in the cache dir as a ticker, and the context loader reads `<cache_dir>/<stem>.csv` literally (brief D7), so both files must sit in the cache dir and every ticker listing must skip them. `SPY`, `TLT` and `UUP` stay listed: SPY is a ticker for the measure scripts and `tests/history_store/test_cache_dir_scripts.py:117` pins `["AAA", "CCC", "SPY"]` unchanged (brief T9). `scripts/data/snapshot_backtest_cache.py` deliberately keeps copying every file (a snapshot is a byte copy of the dir, context included). `training_data.available_tickers()` globs the same files when the yfinance switch points at the ext dir (`BACKTEST_CACHE_DIR=data/backtest_cache_ext`), for about ten measure/tune scripts; it has no caller under `swingbot/`, `bot.py` or `admin_ui.py`, so filtering it is off the live path (index Global Constraints). It cannot import `is_context_only`: `tests/backtesting/screen/test_import_guard.py` forbids any `swingbot/` module outside `backtesting/` importing the screen, so it carries a private mirror of the set.

- [ ] **Step 0: Create the worktree (only the first task of the plan to start)**

If `git worktree list` does not show `.claude/worktrees/2026-11-06-v211-shock-short-screens`, create it from `main`:

```bash
git worktree add .claude/worktrees/2026-11-06-v211-shock-short-screens -b 2026-11-06-v211-shock-short-screens main
```

Every path below is relative to that worktree. V211-2 and V211-3, run in parallel, reuse it.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_context_stems_never_listed.py`:

```python
"""v211 V211-1: BREADTH_ATR1.csv and ^VIX.csv sit in the cache dir beside the
ticker CSVs (the context loader reads <cache_dir>/<stem>.csv literally), so
every ticker listing must skip them. SPY/TLT/UUP stay tickers."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("backtest", "data"):
    if str(ROOT / "scripts" / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts" / _sub))

import cache_dir_source as cds  # noqa: E402
import fetch_earnings_dates as fed  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.marketdata import backtest_cache, training_data  # noqa: E402

STEMS = ("AAA", "BREADTH_ATR1", "SPY", "TLT", "UUP", "^VIX")


def _cache_dir(tmp_path: Path) -> Path:
    frame = pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
                          "Volume": [0.0]}, index=pd.DatetimeIndex(["2010-01-04"], name="Date"))
    for stem in STEMS:
        frame.to_csv(tmp_path / f"{stem}.csv")
    return tmp_path


def test_the_context_only_set_is_exactly_the_two_new_files():
    assert screen_context.CONTEXT_ONLY_STEMS == frozenset({"BREADTH_ATR1", "^VIX"})
    assert screen_context.is_context_only("BREADTH_ATR1")
    assert screen_context.is_context_only("^VIX")
    for ticker in ("SPY", "TLT", "UUP", "_VIX", "VIX", "AAA"):
        assert not screen_context.is_context_only(ticker), ticker


def test_directory_readers_skip_context_stems_and_keep_spy(tmp_path):
    cache_dir = _cache_dir(tmp_path)
    assert cds.listing(cache_dir) == ["AAA", "SPY", "TLT", "UUP"]
    assert cds.cache_files(cache_dir) == ["AAA.csv", "SPY.csv", "TLT.csv", "UUP.csv"]
    assert sorted(cds.load_all(cache_dir)) == ["AAA", "SPY", "TLT", "UUP"]


def test_load_all_filters_before_the_limit(tmp_path):
    # Unfiltered, the sorted paths start AAA.csv, BREADTH_ATR1.csv: the
    # limit must count tickers, never a context file.
    assert sorted(cds.load_all(_cache_dir(tmp_path), limit=2)) == ["AAA", "SPY"]


def test_switch_readers_drop_context_stems_too(monkeypatch):
    # The yfinance source with BACKTEST_CACHE_DIR at the ext dir globs the same files.
    monkeypatch.setattr(cds.training_data, "available_tickers",
                        lambda: ["AAA", "BREADTH_ATR1", "SPY", "^VIX"])
    monkeypatch.setattr(cds.training_data, "load_daily",
                        lambda t: pd.DataFrame({"Close": [1.0]}))
    assert cds.listing(None) == ["AAA", "SPY"]
    assert cds.cache_files(None) == ["AAA.csv", "SPY.csv"]
    assert sorted(cds.load_all(None)) == ["AAA", "SPY"]
    assert sorted(cds.load_all(None, limit=1)) == ["AAA"]


def test_earnings_fetch_never_asks_for_a_context_stem(tmp_path):
    assert fed.cached_symbols(_cache_dir(tmp_path)) == ["AAA", "SPY", "TLT", "UUP"]


@pytest.fixture
def yfinance_dir(tmp_path, monkeypatch):
    """The yfinance switch reading tmp_path as backtest_cache.CACHE_DIR."""
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    training_data.reset()
    training_data.select("yfinance")
    yield tmp_path
    training_data.reset()


def test_yfinance_switch_on_an_ext_dir_never_lists_context_stems(yfinance_dir):
    _cache_dir(yfinance_dir)
    assert training_data.available_tickers() == ["AAA", "SPY", "TLT", "UUP"]


def test_yfinance_switch_on_a_normal_dir_lists_as_before(yfinance_dir):
    for stem in ("AAA", "SPY", "ZZZ", "_VIX"):      # _VIX is cache_path's spelling, a ticker file
        (yfinance_dir / f"{stem}.csv").write_text("Date,Close
", encoding="utf-8")
    assert training_data.available_tickers() == sorted(p.stem for p in yfinance_dir.glob("*.csv"))
    assert training_data.available_tickers() == ["AAA", "SPY", "ZZZ", "_VIX"]


def test_training_data_mirrors_the_screen_set():
    # marketdata may not import the screen (test_import_guard.py), so it keeps a copy.
    assert training_data._CONTEXT_ONLY_STEMS == screen_context.CONTEXT_ONLY_STEMS


#: Every script that globs *.csv, and why it is safe. A new glob over a cache
#: dir fails here until it filters with is_context_only or is listed with a reason.
KNOWN_CSV_GLOBS = {
    "scripts/backtest/cache_dir_source.py": "filters is_context_only (V211-1)",
    "scripts/data/fetch_earnings_dates.py": "filters is_context_only (V211-1)",
    "scripts/data/snapshot_backtest_cache.py": "byte copy of the whole dir, context included",
    "scripts/backtest/measure_fvg_bullish_diagnostic.py": "globs the earnings dir, not a cache dir",
    "scripts/backtest/measure_giveback_levels.py": "globs the earnings dir, not a cache dir",
    "scripts/data/fetch_intraday_cache.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/audit_quality_score.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/parity_sizing.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
    "scripts/reports/runner_headroom.py": "reads backtest_cache.CACHE_DIR (data/backtest_cache by default)",
}
_GLOB = re.compile(r"""r?glob\(\s*["']\*\.csv["']\s*\)""")


def test_every_csv_glob_in_scripts_is_known():
    found = {path.relative_to(ROOT).as_posix()
             for path in sorted((ROOT / "scripts").rglob("*.py"))
             if _GLOB.search(path.read_text(encoding="utf-8"))}
    assert found == set(KNOWN_CSV_GLOBS)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_context_stems_never_listed.py`
Expected: FAIL. `test_the_context_only_set_is_exactly_the_two_new_files` raises `AttributeError: ... has no attribute 'CONTEXT_ONLY_STEMS'`, and the reader tests see `BREADTH_ATR1` and `^VIX`. `test_every_csv_glob_in_scripts_is_known` already passes (it pins today's set).

- [ ] **Step 3: Add the constant and helper to `screen/context.py`**

Below `MIN_Z_COVERAGE = 0.95` (line 31):

```python
#: v211: context series stored in a cache dir beside the ticker CSVs (the
#: runner reads <cache_dir>/<stem>.csv literally) that are never tickers.
#: SPY/TLT/UUP are context *and* tickers, so they are not in this set.
CONTEXT_ONLY_STEMS = frozenset({"BREADTH_ATR1", "^VIX"})


def is_context_only(stem: str) -> bool:
    """True for a cache-dir file stem that no ticker listing may return."""
    return stem in CONTEXT_ONLY_STEMS
```

- [ ] **Step 4: Filter the three readers in `cache_dir_source.py`**

Add `from swingbot.core.backtesting.screen.context import is_context_only  # noqa: E402` beside the other `swingbot` imports (the screen's import guard covers `swingbot/` only; scripts may import the screen). Then:

- `listing(cache_dir)`: both branches return only stems where `not is_context_only(stem)`.
- `load_all(cache_dir, limit)`: filter **before** `[:limit]` on both branches (directory: drop paths whose `p.stem` is context-only; switch: drop such tickers).
- `cache_files(cache_dir)`: both branches drop context-only entries (directory: by `p.stem`; switch: by ticker).

Add one sentence to the module docstring: `v211: BREADTH_ATR1 and ^VIX (screen.context.CONTEXT_ONLY_STEMS) live in the same directory for the screen's context loader and are never returned as tickers.` Keep each function under CC 15; a shared private filter helper is the obvious shape.

- [ ] **Step 5: Filter `fetch_earnings_dates.cached_symbols`**

Import `from swingbot.core.backtesting.screen.context import is_context_only` beside its other `swingbot` imports (ROOT is already on `sys.path` there), and make `cached_symbols(cache_dir)` return `sorted(path.stem for path in Path(cache_dir).glob("*.csv") if not is_context_only(path.stem))`.

- [ ] **Step 5b: Filter `training_data.available_tickers()` (yfinance branch only)**

In `swingbot/core/marketdata/training_data.py`, above `available_tickers` (line 272):

```python
#: v211: context-only files the idea screen keeps beside the ticker CSVs of a
#: yfinance cache dir. Mirrors screen.context.CONTEXT_ONLY_STEMS (a test pins
#: them equal); marketdata may not import the screen (test_import_guard.py).
_CONTEXT_ONLY_STEMS = frozenset({"BREADTH_ATR1", "^VIX"})
```

and in the yfinance branch add the one filter: `sorted(p.stem for p in folder.glob("*.csv") if p.stem not in _CONTEXT_ONLY_STEMS)`. The alpaca branch is untouched (its manifest never holds these stems). A directory without the two files lists byte-identically to before.

- [ ] **Step 6: Run the new tests and the existing reader pins**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_context_stems_never_listed.py`
Expected: PASS (9 tests).

Run: `python scripts/dev/testrun.py file tests/history_store/test_cache_dir_scripts.py`
Expected: PASS, unchanged (`listing(csv_dir) == ["AAA", "CCC", "SPY"]` still holds).

Run: `python scripts/dev/testrun.py file tests/history_store/test_training_data.py`
Expected: PASS, unchanged (`available_tickers() == ["AAPL", "EMPTY"]` still holds).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (`training_data.py` imports nothing from the screen).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/screen/context.py swingbot/core/marketdata/training_data.py scripts/backtest/cache_dir_source.py scripts/data/fetch_earnings_dates.py tests/backtest_scripts/test_context_stems_never_listed.py
git commit -m "feat(v211): context-only stems BREADTH_ATR1 and ^VIX never listed as tickers"
```

### Task V211-2: `^VIX` daily context fetch, stored as `^VIX.csv`, aligned to SPY sessions

**Model:** sonnet — one fetch helper, one session check that reuses `screen.context.check_contiguous`, and a CLI mode; behaviour fully pinned by the tests below.

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py` (new constants and three functions after `fetch` at line 149; a `vix_context_main` CLI and an `_entry` dispatcher at the bottom; one docstring paragraph)
- Create: `tests/backtest_scripts/test_fetch_vix_context.py` (suite `backtest-scripts`)

**Interfaces:**
- Consumes: `swingbot.core.backtesting.screen.context` (`CONTEXT_START = "2009-06-01"`, `check_raw_index(index, name)`, `check_contiguous(index, sessions, name)`, `ContextError`) — all exist today. `fetch(ticker, start, end) -> pd.DataFrame | None` (line 149, yfinance, end exclusive, `None` under 260 bars).
- Produces (V211-13 runs the CLI on the real cache):
  - `VIX_CONTEXT = "^VIX"`; `VIX_START, VIX_END = "2009-01-01", "2019-12-31"`
  - `vix_context_path(cache_dir: Path) -> Path` → `<cache_dir>/^VIX.csv`
  - `check_vix_sessions(vix_index: pd.DatetimeIndex, spy_index: pd.DatetimeIndex, *, start: str = CONTEXT_START, end: str = VIX_END) -> None` — raises `ContextError` on a non-unique or non-midnight index, or on any SPY session in `[start, end]` that `^VIX` lacks, or any `^VIX` bar in `[start, end]` that is not a SPY session
  - `fetch_vix_context(cache_dir: Path, *, start: str = VIX_START, end: str = VIX_END, fetcher=fetch) -> Path` — fetches, drops rows with a NaN in `Open/High/Low/Close` (the runner's `load_frame` drops them too, so the check sees what the runner will), checks, and **only then** writes `^VIX.csv`; a failed check leaves any existing file untouched
  - `vix_context_main(argv: list[str] | None = None) -> int`: `--vix-context --cache-dir PATH [--start] [--end] [--force]`; exit 2 on an existing file without `--force` or on a `ContextError`, 0 after writing
  - `_entry(argv: list[str]) -> int | None`: `--vix-context` in argv → `vix_context_main(argv)`, else `main()`; `if __name__ == "__main__": sys.exit(_entry(sys.argv[1:]))`

**Why:** spec § Track 2 "The shared daily inputs" → `^VIX`: fetch 2009–2019 daily `^VIX` from Yahoo; store it as `^VIX.csv` because the loader reads `<ticker>.csv` literally while `backtest_cache.cache_path("^VIX")` writes `_VIX.csv` (brief D7, T9); its dates must equal the SPY session index exactly, checked here and failing loudly (brief T11: `check_contiguous` refuses both missing and extra dates). yfinance's `end` is exclusive, so the fetch asks for `end + 1 day` to include 2019-12-31. `main()` is left byte-identical: the new mode is reached through `_entry`, so no existing function's complexity rises.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_fetch_vix_context.py`:

```python
"""v211 V211-2: ^VIX context is fetched once, stored as ^VIX.csv (never
_VIX.csv), and refused unless its dates equal SPY's sessions exactly."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_backtest_data as fbd  # noqa: E402
from swingbot.core.backtesting.screen.context import ContextError  # noqa: E402

START, END = "2009-05-01", "2009-07-31"
HEADER = "Date,Open,High,Low,Close,Volume"


def _ohlcv(index) -> pd.DataFrame:
    index = pd.DatetimeIndex(index, name="Date")
    close = np.linspace(20.0, 30.0, len(index))
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.zeros(len(index))}, index=index)


def _sessions() -> pd.DatetimeIndex:
    return pd.bdate_range(START, END)


def _with_spy(tmp_path: Path) -> Path:
    _ohlcv(_sessions()).to_csv(tmp_path / "SPY.csv")
    return tmp_path


def _fetcher(index, calls=None):
    def fake(ticker, start, end):
        if calls is not None:
            calls.append((ticker, start, end))
        return _ohlcv(index)
    return fake


def test_the_path_keeps_the_caret(tmp_path):
    assert fbd.VIX_CONTEXT == "^VIX"
    assert fbd.vix_context_path(tmp_path) == tmp_path / "^VIX.csv"


def test_fetch_writes_caret_vix_aligned_to_spy(tmp_path):
    calls = []
    path = fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END,
                                 fetcher=_fetcher(_sessions(), calls))
    assert path == tmp_path / "^VIX.csv"
    assert not (tmp_path / "_VIX.csv").exists()
    assert calls == [("^VIX", START, "2009-08-01")]        # yfinance end is exclusive
    assert path.read_text(encoding="utf-8").splitlines()[0] == HEADER
    written = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    assert written.index.equals(_sessions())


def test_a_missing_session_refuses_and_writes_nothing(tmp_path):
    index = _sessions().drop(pd.Timestamp("2009-06-15"))
    with pytest.raises(ContextError, match="missing"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))
    assert not (tmp_path / "^VIX.csv").exists()


def test_an_extra_bar_refuses(tmp_path):
    index = _sessions().append(pd.DatetimeIndex(["2009-06-13"])).sort_values()  # a Saturday
    with pytest.raises(ContextError, match="extra"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))


def test_dates_before_the_context_start_are_not_checked(tmp_path):
    index = _sessions().drop(pd.Timestamp("2009-05-04"))   # before CONTEXT_START 2009-06-01
    path = fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))
    assert path.exists()


def test_a_nan_row_counts_as_missing(tmp_path):
    def fake(ticker, start, end):
        frame = _ohlcv(_sessions())
        frame.loc[pd.Timestamp("2009-06-15"), "Close"] = np.nan
        return frame
    with pytest.raises(ContextError, match="missing"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=fake)


def test_no_spy_file_refuses(tmp_path):
    with pytest.raises(ContextError, match="SPY"):
        fbd.fetch_vix_context(tmp_path, start=START, end=END, fetcher=_fetcher(_sessions()))


def test_an_empty_fetch_refuses(tmp_path):
    with pytest.raises(ContextError, match="no data"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END,
                              fetcher=lambda ticker, start, end: None)


def test_check_rejects_a_repeated_date():
    index = _sessions().append(pd.DatetimeIndex(["2009-06-15"])).sort_values()
    with pytest.raises(ContextError, match="not unique"):
        fbd.check_vix_sessions(index, _sessions(), end=END)


def _argv(tmp_path, *extra):
    return ["--vix-context", "--cache-dir", str(tmp_path), "--start", START, "--end", END, *extra]


def test_cli_refuses_an_existing_file_without_force(tmp_path, monkeypatch, capsys):
    _with_spy(tmp_path)
    (tmp_path / "^VIX.csv").write_text("old", encoding="utf-8")
    calls = []
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions(), calls))
    assert fbd.vix_context_main(_argv(tmp_path)) == 2
    assert (tmp_path / "^VIX.csv").read_text(encoding="utf-8") == "old"
    assert calls == []
    assert "--force" in capsys.readouterr().out


def test_cli_force_overwrites_and_a_failed_check_keeps_the_file(tmp_path, monkeypatch):
    _with_spy(tmp_path)
    (tmp_path / "^VIX.csv").write_text("old", encoding="utf-8")
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions()))
    assert fbd.vix_context_main(_argv(tmp_path, "--force")) == 0
    good = (tmp_path / "^VIX.csv").read_text(encoding="utf-8")
    assert good.splitlines()[0] == HEADER
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions().drop(pd.Timestamp("2009-06-15"))))
    assert fbd.vix_context_main(_argv(tmp_path, "--force")) == 2
    assert (tmp_path / "^VIX.csv").read_text(encoding="utf-8") == good


def test_entry_dispatches_the_vix_mode_and_leaves_main_alone(monkeypatch):
    seen = []
    monkeypatch.setattr(fbd, "vix_context_main", lambda argv: seen.append(("vix", argv)) or 0)
    monkeypatch.setattr(fbd, "main", lambda: seen.append(("main", None)))
    assert fbd._entry(["--vix-context", "--cache-dir", "x"]) == 0
    fbd._entry(["--tickers", "SPY"])
    assert seen == [("vix", ["--vix-context", "--cache-dir", "x"]), ("main", None)]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_fetch_vix_context.py`
Expected: FAIL — `AttributeError: module 'fetch_backtest_data' has no attribute 'VIX_CONTEXT'` (and the same for the other new names).

- [ ] **Step 3: Implement the fetch, the check and the CLI in `scripts/data/fetch_backtest_data.py`**

Imports: add `from swingbot.core.backtesting.screen import context as screen_context` beside the other `swingbot` imports (light: numpy/pandas only).

Constants and functions, placed after `fetch` (line 149), with the signatures in Interfaces:

- `check_vix_sessions`: `screen_context.check_raw_index(vix_index, VIX_CONTEXT)`; slice both indexes to `[pd.Timestamp(start), pd.Timestamp(end)]` inclusive; raise `ContextError("^VIX: no SPY session between <start> and <end>")` when the SPY slice is empty; then `screen_context.check_contiguous(vix_slice, spy_slice, VIX_CONTEXT)` (it raises with "missing" / "extra" in the message).
- `fetch_vix_context`:
  1. `spy_path = Path(cache_dir) / "SPY.csv"`; missing → `ContextError(f"^VIX: {spy_path} is missing; the session check needs SPY")`. Read it with `pd.read_csv(spy_path, parse_dates=["Date"], index_col="Date")`.
  2. `frame = fetcher(VIX_CONTEXT, start, <end + 1 day, ISO>)` (yfinance `end` is exclusive); `None` or empty → `ContextError("^VIX: the fetch returned no data")`.
  3. Keep the columns `Open, High, Low, Close, Volume`; drop rows with a NaN in `Open/High/Low/Close`; `Volume` NaN → `0.0`; drop rows dated after `end`; `index.name = "Date"`.
  4. `check_vix_sessions(frame.index, spy.index, end=end)`.
  5. Write `frame.to_csv(vix_context_path(cache_dir))` and return that path. Nothing is written when 2–4 raise.
- `vix_context_main(argv=None) -> int`: its own `argparse.ArgumentParser` with `--vix-context` (`store_true`, `required=True`), `--cache-dir` (required), `--start` (default `VIX_START`), `--end` (default `VIX_END`), `--force`. If `vix_context_path(cache_dir)` exists and not `--force`: print `refusing: <path> exists; pass --force to refetch (a pinned context file is never refetched)` and return 2. Call `fetch_vix_context(cache_dir, start=..., end=..., fetcher=fetch)` — `fetch` is looked up at call time so tests can monkeypatch it. On `ContextError` print `error: <message>` and return 2. Otherwise print `+ ^VIX: <n> bars (<first> -> <last>) -> <path>` and return 0.
- `_entry(argv)` and the `__main__` block as in Interfaces. `main()` itself is not edited.

Add to the module docstring, after the `--training-universe` paragraph:

```
--vix-context (v211) is its own mode: it fetches daily ^VIX 2009-01-01 ->
2019-12-31 into <cache-dir>/^VIX.csv (the screen's context loader reads
<stem>.csv literally, so not cache_path's _VIX.csv) and refuses a calendar
that differs from <cache-dir>/SPY.csv's sessions from 2009-06-01.
    python scripts/data/fetch_backtest_data.py --vix-context --cache-dir data/backtest_cache_ext
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_fetch_vix_context.py`
Expected: PASS (12 tests).

Run: `python scripts/dev/testrun.py file tests/scripts/test_fetch_backtest_tickers.py`
Expected: PASS, unchanged (`main()` untouched).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/fetch_backtest_data.py tests/backtest_scripts/test_fetch_vix_context.py
git commit -m "feat(v211): --vix-context fetch writes ^VIX.csv aligned to SPY sessions"
```

### Task V211-3: `BREADTH_ATR1` builder (point-in-time, ATR dated `t−1`)

**Model:** opus — a cross-sectional, point-in-time series that a one-shot screen will read: membership spans, data holes and the ATR date offset each decide the frozen definition, and a slip is invisible after the pin.

**Files:**
- Create: `swingbot/core/backtesting/screen/breadth.py` (pure; no CAP/events, so never an idea)
- Create: `scripts/data/build_breadth_context.py`
- Create: `tests/backtesting/screen/test_breadth.py` (suite `backtesting-arms`)
- Create: `tests/backtest_scripts/test_build_breadth_context.py` (suite `backtest-scripts`)

**Interfaces:**
- Consumes: `swingbot.core.backtesting.screen.indicators.atr(df, n=14) -> pd.Series` (Wilder, causal); `swingbot.core.backtesting.screen.context` (`CONTEXT_START = "2009-06-01"`, `check_raw_index`, `ContextError`); `swingbot.core.marketdata.pit_membership` (`load_intervals(path) -> dict[str, list[tuple[str, str]]]` with half-open `[start, end)` ISO spans and `OPEN_END = "9999-12-31"`, `members_between(intervals, start, end) -> list[str]`); `swingbot.core.marketdata.backtest_cache.cache_path(ticker).name` (the cache spelling of a symbol). All exist today.
- Produces (V211-7 reads the file through the runner; V211-13 runs the script on the real cache):
  - `breadth.NAME = "BREADTH_ATR1"`, `breadth.ATR_MOVE = -1.0`
  - `breadth.member_atr_moves(df: pd.DataFrame) -> pd.Series` = `(Close − Close.shift(1)) / indicators.atr(df).shift(1)` on `df`'s own rows
  - `breadth.member_mask(spans: Sequence[tuple[str, str]], sessions: pd.DatetimeIndex) -> np.ndarray` — bool, `start <= ISO date < end` for any span (ISO string compare, so `OPEN_END` never overflows a `Timestamp`)
  - `breadth.breadth_atr1(frames: Mapping[str, pd.DataFrame], intervals: Mapping[str, list], sessions: pd.DatetimeIndex) -> pd.DataFrame` — index `sessions` named `Date`, columns `Open, High, Low, Close, Volume`; `Open = High = Low = Close` = the fraction in `[0, 1]`; `Volume` = members with a finite move (int); `0.0` / `0` on a session with none, never NaN
  - script `scripts/data/build_breadth_context.py`: `main(argv: list[str] | None = None) -> int` with `--cache-dir` (required), `--membership` (default `<repo>/data/universe/sp500_membership.csv`), `--end` (default `"2019-12-31"`), `--out` (default `<cache-dir>/BREADTH_ATR1.csv`); exit 2 on an existing output, a missing `SPY.csv` or an empty membership file; prints per-year coverage

**Definition (spec § Track 2 "The shared daily inputs", index Global Constraints and OPEN):** `d_breadth[t]` = (members on `t` with a finite move and move `≤ −1.0`) / (members on `t` with a finite move), move = `(Close[t] − Close[t−1]) / ATR14[t−1]`. A member's move on `t` counts only when its previous bar is SPY's previous session: a missing bar leaves the denominator on that session **and** on the next one (no move across a hole). Sessions are SPY's dates from `CONTEXT_START` to `--end`, so the output passes the runner's `check_contiguous` by construction (Review Focus 2). The ATR is computed on the member's whole file, so 2009 bars before `CONTEXT_START` warm it up.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/backtesting/screen/test_breadth.py`:

```python
"""v211 V211-3: BREADTH_ATR1[t] = share of PIT members with a finite move
(Close[t] - Close[t-1]) / ATR14[t-1] at or below -1.0; reads bars <= t only."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import breadth
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk

ALWAYS = [("2000-01-01", "9999-12-31")]
SESSIONS = pd.bdate_range("2010-01-04", periods=5)


def _fixed_moves(monkeypatch, moves: dict):
    """member_atr_moves returns the given per-session values for each frame."""
    by_id = {id(frame): pd.Series(values, index=frame.index, dtype=float)
             for frame, values in moves.values()}
    monkeypatch.setattr(breadth, "member_atr_moves", lambda df: by_id[id(df)])
    return {name: frame for name, (frame, _) in moves.items()}


def _flat(index=SESSIONS) -> pd.DataFrame:
    return pd.DataFrame({c: 1.0 for c in ("Open", "High", "Low", "Close", "Volume")}, index=index)


def test_constants():
    assert breadth.NAME == "BREADTH_ATR1"
    assert breadth.ATR_MOVE == -1.0


def test_share_counts_moves_at_or_below_minus_one_atr(monkeypatch):
    nan = np.nan
    frames = _fixed_moves(monkeypatch, {
        "A": (_flat(), [nan, 0.0, -1.0, 0.5, 0.0]),       # exactly -1.0 counts
        "B": (_flat(), [nan, 0.0, -0.999, 0.5, 0.0]),
        "C": (_flat(), [nan, 0.0, -2.5, 0.5, 0.0]),
        "D": (_flat(), [nan, 0.0, nan, 0.5, 0.0]),        # no finite move: out of the denominator
    })
    table = breadth.breadth_atr1(frames, {k: ALWAYS for k in frames}, SESSIONS)
    assert table["Close"].iloc[2] == pytest.approx(2 / 3)
    assert table["Volume"].iloc[2] == 3
    assert table["Close"].iloc[3] == 0.0 and table["Volume"].iloc[3] == 4


def test_a_session_without_any_finite_move_is_zero_not_nan(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [np.nan] * 5)})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS}, SESSIONS)
    assert table["Close"].tolist() == [0.0] * 5
    assert table["Volume"].tolist() == [0] * 5
    assert np.isfinite(table.to_numpy(dtype=float)).all()


def test_shape_is_a_contiguous_ohlcv_frame(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [np.nan, -3.0, 0.0, 0.0, 0.0])})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS}, SESSIONS)
    assert list(table.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert table.index.name == "Date" and table.index.equals(SESSIONS)
    for column in ("Open", "High", "Low"):
        assert table[column].equals(table["Close"])
    assert table["Close"].iloc[1] == 1.0


def test_membership_is_point_in_time_and_half_open(monkeypatch):
    frames = _fixed_moves(monkeypatch, {
        "A": (_flat(), [-2.0] * 5),
        "B": (_flat(), [0.0] * 5),
    })
    # Session 0 has no previous session, so nobody counts there. B joins on
    # session 1 and leaves before session 3 (end is exclusive).
    spans = {"A": ALWAYS, "B": [("2010-01-05", "2010-01-07")]}
    table = breadth.breadth_atr1(frames, spans, SESSIONS)
    assert table["Volume"].tolist() == [0, 2, 2, 1, 1]
    assert table["Close"].tolist() == [0.0, 0.5, 0.5, 1.0, 1.0]


def test_member_mask_reads_the_open_end_without_overflow():
    mask = breadth.member_mask([("2010-01-06", "9999-12-31")], SESSIONS)
    assert mask.tolist() == [False, False, True, True, True]


def test_symbols_missing_a_frame_or_spans_are_ignored(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [-2.0] * 5), "Z": (_flat(), [-2.0] * 5)})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS, "Y": ALWAYS}, SESSIONS)
    assert table["Volume"].tolist() == [0, 1, 1, 1, 1]


def test_a_missing_bar_leaves_the_denominator_that_day_and_the_next():
    sessions = pd.bdate_range("2010-01-04", periods=60)
    full = random_walk(60, seed=3)
    holed = random_walk(60, seed=5).drop(sessions[40])
    table = breadth.breadth_atr1({"A": holed, "B": full}, {"A": ALWAYS, "B": ALWAYS}, sessions)
    assert table["Volume"].iloc[38:43].tolist() == [2, 2, 1, 1, 2]


def test_member_moves_read_the_atr_dated_t_minus_1():
    df = random_walk(80, seed=11)
    before = breadth.member_atr_moves(df)
    wider = df.copy()
    wider.iloc[50, wider.columns.get_loc("High")] += 50.0      # widens TR (and ATR) at bar 50 only
    after = breadth.member_atr_moves(wider)
    assert after.iloc[50] == before.iloc[50]                   # ATR[49] divides bar 50
    assert after.iloc[51] != before.iloc[51]


def test_member_moves_are_prefix_stable():
    assert_prefix_stable(breadth.member_atr_moves, random_walk(120, seed=2), [20, 60, 119])


def test_breadth_at_t_ignores_every_later_bar():
    sessions = pd.bdate_range("2010-01-04", periods=120)
    frames = {name: random_walk(120, seed=seed) for name, seed in (("A", 1), ("B", 2), ("C", 4))}
    spans = {name: ALWAYS for name in frames}
    full = breadth.breadth_atr1(frames, spans, sessions)
    for t in (20, 75, 119):
        cut = {name: df.iloc[: t + 1] for name, df in frames.items()}
        part = breadth.breadth_atr1(cut, spans, sessions[: t + 1])
        pd.testing.assert_frame_equal(part, full.iloc[: t + 1], check_exact=False, rtol=1e-12)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_breadth.py`
Expected: FAIL — `ImportError: cannot import name 'breadth' from 'swingbot.core.backtesting.screen'`.

- [ ] **Step 3: Implement `swingbot/core/backtesting/screen/breadth.py`**

Module docstring: what `BREADTH_ATR1` is (the definition above), that it is precomputed into a context file because the idea interface has no cross-sectional input (spec § Track 2), that every value at `t` reads bars dated `≤ t` and the ATR `≤ t−1`, and that a missing member bar leaves the denominator on that session and the next. Imports: `numpy`, `pandas`, `typing.Mapping, Sequence`, `from swingbot.core.backtesting.screen import indicators`.

Functions, signatures as in Interfaces:
- `member_atr_moves(df)`: the one-line formula; returns a float Series on `df.index`.
- `member_mask(spans, sessions)`: `iso = sessions.strftime("%Y-%m-%d").to_numpy(dtype=str)`; OR over spans of `(iso >= start) & (iso < end)`; all-False when `spans` is empty.
- a private `_session_moves(df, sessions) -> np.ndarray`: call `member_atr_moves(df)` **through the module global** (the tests monkeypatch it), reindex onto `sessions`, and set NaN wherever the member's previous own bar date (`pd.Series(df.index, index=df.index).shift(1)` reindexed onto `sessions`) differs from SPY's previous session (`sessions` shifted by one; NaT on the first session compares unequal, so session 0 never counts).
- `breadth_atr1(frames, intervals, sessions)`: for each symbol present in **both** mappings with non-empty spans, `ok = member_mask(...) & np.isfinite(moves)`; accumulate `counted += ok` and `hits += ok & (moves <= ATR_MOVE)`; `share = np.divide(hits, counted, out=np.zeros(len(sessions)), where=counted > 0)`; return the frame with `index=pd.DatetimeIndex(sessions, name="Date")`, the four price columns equal to `share`, `Volume = counted.astype(int)`.

Each function stays well under CC 15.

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_breadth.py`
Expected: PASS (11 tests).

- [ ] **Step 5: Write the failing script tests**

Create `tests/backtest_scripts/test_build_breadth_context.py`:

```python
"""v211 V211-3: build_breadth_context.py writes <cache-dir>/BREADTH_ATR1.csv on
SPY's sessions from CONTEXT_START, point in time, and never overwrites it."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import build_breadth_context as bbc  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

HEADER = "Date,Open,High,Low,Close,Volume"
END = "2009-12-31"


def _cache(tmp_path: Path) -> tuple[Path, Path]:
    cache = tmp_path / "cache"
    cache.mkdir()
    random_walk(300, seed=1, start="2009-01-02").to_csv(cache / "SPY.csv", index_label="Date")
    random_walk(300, seed=2, start="2009-01-02").to_csv(cache / "AAA.csv", index_label="Date")
    random_walk(300, seed=3, start="2009-01-02").to_csv(cache / "BRK-B.csv", index_label="Date")
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n"
                          "AAA,2000-01-03,\n"
                          "BRK.B,2000-01-03,2009-09-01\n"          # normalised to BRK-B, leaves 09-01
                          "CCC,2000-01-03,\n", encoding="utf-8")   # a PIT member without a cache file
    return cache, membership


def _spy_sessions(cache: Path) -> pd.DatetimeIndex:
    spy = pd.read_csv(cache / "SPY.csv", parse_dates=["Date"], index_col="Date").index
    return spy[(spy >= pd.Timestamp(screen_context.CONTEXT_START)) & (spy <= pd.Timestamp(END))]


def test_builds_breadth_on_spy_sessions(tmp_path, capsys):
    cache, membership = _cache(tmp_path)
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 0
    out = cache / "BREADTH_ATR1.csv"
    assert out.read_text(encoding="utf-8").splitlines()[0] == HEADER
    raw = pd.read_csv(out, parse_dates=["Date"], index_col="Date")
    screen_context.check_raw_index(raw.index, "BREADTH_ATR1")
    sessions = _spy_sessions(cache)
    screen_context.check_contiguous(raw.index, sessions, "BREADTH_ATR1")
    assert raw["Close"].between(0.0, 1.0).all()
    assert raw.loc[: "2009-08-31", "Volume"].max() == 2
    assert raw.loc["2009-09-01":, "Volume"].max() == 1         # BRK-B left the index
    printed = capsys.readouterr().out
    assert "2009:" in printed
    assert "1 PIT member(s) without a cache file" in printed


def test_refuses_an_existing_output(tmp_path, capsys):
    cache, membership = _cache(tmp_path)
    (cache / "BREADTH_ATR1.csv").write_text("old", encoding="utf-8")
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 2
    assert (cache / "BREADTH_ATR1.csv").read_text(encoding="utf-8") == "old"
    assert "exists" in capsys.readouterr().out


def test_out_path_is_honoured(tmp_path):
    cache, membership = _cache(tmp_path)
    target = tmp_path / "elsewhere.csv"
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership),
                     "--end", END, "--out", str(target)]) == 0
    assert target.exists() and not (cache / "BREADTH_ATR1.csv").exists()


def test_refuses_without_spy_or_membership(tmp_path):
    cache, membership = _cache(tmp_path)
    empty = tmp_path / "empty.csv"
    empty.write_text("ticker,start_date,end_date\n", encoding="utf-8")
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(empty), "--end", END]) == 2
    (cache / "SPY.csv").unlink()
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 2
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_build_breadth_context.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_breadth_context'`.

- [ ] **Step 7: Implement `scripts/data/build_breadth_context.py`**

Module docstring: what it builds, the run command (`python scripts/data/build_breadth_context.py --cache-dir data/backtest_cache_ext`), that the output is built once and pinned (V211-13) and never rebuilt over an existing file, and that `--membership` defaults to the tracked `data/universe/sp500_membership.csv`. Put `ROOT = Path(__file__).resolve().parents[2]` on `sys.path` as `fetch_earnings_dates.py` does, then import `breadth`, `screen.context as screen_context`, `pit_membership`, `backtest_cache.cache_path`.

Helpers (each CC < 15), then `main`:
- `build_parser() -> argparse.ArgumentParser` with the four options in Interfaces.
- `spy_sessions(cache_dir: Path, end: str) -> pd.DatetimeIndex`: read `<cache_dir>/SPY.csv`; missing → `screen_context.ContextError`; keep dates in `[CONTEXT_START, end]`.
- `load_member(path: Path) -> pd.DataFrame | None`: `None` when the file is missing; else read with `parse_dates=["Date"], index_col="Date"`, drop rows with a NaN in `Open/High/Low/Close`, drop duplicated dates (keep first), sort.
- `load_members(cache_dir, symbols) -> tuple[dict[str, pd.DataFrame], list[str]]`: `cache_dir / cache_path(symbol).name` per symbol (`BRK-B` → `BRK-B.csv`); returns the frames and the sorted symbols without a file.
- `coverage_lines(table: pd.DataFrame, intervals, sessions) -> list[str]`: per calendar year, `f"{year}: {with_data:.1f} of {members:.1f} PIT members with a finite move per session ({share:.1%})"`, where `with_data` is the mean `Volume` and `members` the mean count of `breadth.member_mask` hits across all intervals that year (`share` 0.0 when `members` is 0).
- `main(argv=None) -> int`: parse; `out = args.out or cache_dir / f"{breadth.NAME}.csv"`; exists → print `refusing: <out> exists; BREADTH_ATR1 is built once and pinned` and return 2; `intervals = pit_membership.load_intervals(args.membership)`, empty → print `error: no membership rows in <path>` and return 2; `spy_sessions` raising `ContextError` → print `error: <message>` and return 2; `symbols = pit_membership.members_between(intervals, CONTEXT_START, end)`; load; `table = breadth.breadth_atr1(frames, intervals, sessions)`; `table.to_csv(out)`; print `f"{len(missing)} PIT member(s) without a cache file"` (plus the first ten names), the coverage lines, and `+ BREADTH_ATR1: <n> sessions (<first> -> <last>) -> <out>`; return 0.
- `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 8: Run both test files and the gates**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_build_breadth_context.py`
Expected: PASS (4 tests).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_breadth.py`
Expected: PASS (11 tests).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (`breadth.py` sits inside `swingbot/core/backtesting/`; nothing outside imports it).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/backtesting/screen/breadth.py scripts/data/build_breadth_context.py tests/backtesting/screen/test_breadth.py tests/backtest_scripts/test_build_breadth_context.py
git commit -m "feat(v211): BREADTH_ATR1 point-in-time breadth context builder"
```

