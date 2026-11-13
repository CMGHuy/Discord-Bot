# v222 — Market-shock detector: index + VIX entry path — Part 1: Stage 1 daily screen

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, plan-time readings, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V222-1, V222-2, V222-3, V222-3b: the worktree, daily SPY and `^VIX` to
2026-11-04, the daily close and upper-bound series, fire days and episodes, the
16-cell grid with the budget, the edge-aware winner rule and the prior check,
and the descriptive arms. Nothing here reads a candidate Stage 2 day's intraday
data, and nothing here edits the detector.

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
D=$M/data/v222                                                                 # stage data (gitignored, main tree)
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths.

# Phase 1 — Stage 1 data and daily screen

### Task V222-1: Worktree; daily SPY + `^VIX` to 2026-11-04 via `fetch_backtest_data.py --shock-index`

**Model:** sonnet — a guarded extension of an existing fetch mode, with one network run.

> Split at plan time (task over 20 KB): V222-1 is the worktree and the fetch
> mode; **V222-1b** creates the screen module's readers, the `DATA_READERS` row,
> the window and the Results scaffold. Each has its own ledger row.

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py` (constants and `fetch_shock_index` after `vix_context_main`, l.~214-236; `_entry`, l.358-361; module docstring)
- Create: `tests/backtest_scripts/test_fetch_shock_index.py`
- Data (main tree, gitignored): `data/v222/SPY.csv`, `data/v222/^VIX.csv`, `data/v222/provenance.json`

**Interfaces:**
- Consumes: `fetch_backtest_data.fetch(ticker, start, end)`, `_clean_vix_frame(frame, end)`, `fetch_vix_context(cache_dir, *, start, end, fetcher)` (writes `<cache_dir>/^VIX.csv`, session-checked against `<cache_dir>/SPY.csv` from `screen_context.CONTEXT_START` = 2009-06-01 to `end`), `VIX_CONTEXT = "^VIX"`, `screen_context.ContextError`.
- Produces: `fetch_backtest_data.SHOCK_INDEX_END = "2026-11-04"`, `SHOCK_INDEX_SPY_START = "1993-01-01"`, `SHOCK_INDEX_VIX_START = "1990-01-01"`, `PINNED_CACHES = ("data/backtest_cache", "data/backtest_cache_ext")`, `SHOCK_INDEX_FILES = ("SPY.csv", "^VIX.csv", "provenance.json")`; `fetch_shock_index(cache_dir: Path, *, end: str = SHOCK_INDEX_END, fetcher=fetch) -> dict` returning `{source, fetched_at, end, spy_first, spy_rows, vix_first, vix_rows}` (raises `ContextError` on a pinned cache or an empty SPY fetch); `shock_index_main(argv) -> int` (CLI `--shock-index --cache-dir DIR [--end] [--force]`, exit 2 on existing files without `--force`, on a pinned dir, or on any `ContextError`); the worktree and branch `2026-11-09-v222-shock-index-vix-path`; the three data files.

**Why the fetch path looks like this.** The brief found that the spec's "`fetch_backtest_data.py` does not carry VIX today" is out of date: v211's `--vix-context` mode already fetches daily `^VIX` with a session check against SPY, but it is pinned to 2009..2019 for other screens and refuses to overwrite. `--shock-index` reuses `fetch_vix_context` into a *separate* directory (`data/v222/`), fetches its own SPY there first (the session check needs it), and refuses the two pinned caches outright, so no screen's pinned context file can ever be rewritten. `fetch()` returns `None` below 260 bars and uses `auto_adjust=True`; ATR-scaled moves are unaffected by the adjustment factor.

- [ ] **Step 1: Create the worktree off `main`**

```bash
M=E:/Documents/Private/Projects/Discord-Bot
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path
git -C "$M" fetch origin
git -C "$M" status --short --branch | head -3      # main must not be behind origin/main
git -C "$M" worktree add "$W" -b 2026-11-09-v222-shock-index-vix-path main
git -C "$W" log --oneline -1
```

Expected: the new worktree at `main`'s HEAD. If `git worktree list` already shows this path, reuse it and resume at its first uncommitted step.

- [ ] **Step 2: Write the failing fetch tests**

Create `tests/backtest_scripts/test_fetch_shock_index.py`:

```python
"""v222 V222-1: --shock-index fetches daily SPY and ^VIX to 2026-11-04 into
its own directory, never into a pinned cache, and writes a provenance file."""
import json
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

END = "2009-07-31"


def _ohlcv(index) -> pd.DataFrame:
    index = pd.DatetimeIndex(index, name="Date")
    close = np.linspace(20.0, 30.0, len(index))
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.zeros(len(index))}, index=index)


def _fetcher(calls, *, spy_index=None, vix_index=None):
    spy_index = pd.bdate_range("2009-05-01", "2009-08-14") if spy_index is None else spy_index
    vix_index = pd.bdate_range("2009-04-01", "2009-08-14") if vix_index is None else vix_index

    def fake(ticker, start, end):
        calls.append((ticker, start, end))
        index = spy_index if ticker == "SPY" else vix_index
        return None if not len(index) else _ohlcv(index)
    return fake


def test_constants_are_the_frozen_window():
    assert fbd.SHOCK_INDEX_END == "2026-11-04"
    assert fbd.SHOCK_INDEX_SPY_START == "1993-01-01"
    assert fbd.SHOCK_INDEX_VIX_START == "1990-01-01"
    assert fbd.PINNED_CACHES == ("data/backtest_cache", "data/backtest_cache_ext")
    assert fbd.SHOCK_INDEX_FILES == ("SPY.csv", "^VIX.csv", "provenance.json")


def test_fetch_writes_spy_vix_and_provenance_cut_at_end(tmp_path):
    calls = []
    out = tmp_path / "v222"
    prov = fbd.fetch_shock_index(out, end=END, fetcher=_fetcher(calls))
    assert calls == [("SPY", "1993-01-01", "2009-08-01"), ("^VIX", "1990-01-01", "2009-08-01")]
    spy = pd.read_csv(out / "SPY.csv", parse_dates=["Date"], index_col="Date")
    vix = pd.read_csv(out / "^VIX.csv", parse_dates=["Date"], index_col="Date")
    assert spy.index[-1] == pd.Timestamp(END) and vix.index[-1] == pd.Timestamp(END)
    assert list(spy.columns) == ["Open", "High", "Low", "Close", "Volume"]
    on_disk = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    assert on_disk == prov
    assert set(prov) == {"source", "fetched_at", "end", "spy_first", "spy_rows",
                         "vix_first", "vix_rows"}
    assert (prov["end"], prov["spy_first"], prov["vix_first"]) == (END, "2009-05-01", "2009-04-01")
    assert prov["spy_rows"] == len(spy) and prov["vix_rows"] == len(vix)
    assert "yfinance" in prov["source"]


@pytest.mark.parametrize("pinned", ["backtest_cache", "backtest_cache_ext"])
def test_a_pinned_cache_is_refused_before_any_fetch(tmp_path, pinned):
    calls = []
    target = tmp_path / "data" / pinned
    with pytest.raises(ContextError, match="pinned"):
        fbd.fetch_shock_index(target, end=END, fetcher=_fetcher(calls))
    assert calls == [] and not target.exists()


def test_an_empty_spy_fetch_refuses_and_writes_nothing(tmp_path):
    out = tmp_path / "v222"
    with pytest.raises(ContextError, match="SPY"):
        fbd.fetch_shock_index(out, end=END, fetcher=_fetcher([], spy_index=pd.DatetimeIndex([])))
    assert not (out / "SPY.csv").exists()


def test_a_vix_calendar_gap_after_the_context_start_refuses(tmp_path):
    vix = pd.bdate_range("2009-04-01", "2009-08-14").drop(pd.Timestamp("2009-06-15"))
    out = tmp_path / "v222"
    with pytest.raises(ContextError, match="missing"):
        fbd.fetch_shock_index(out, end=END, fetcher=_fetcher([], vix_index=vix))
    assert not (out / "^VIX.csv").exists() and not (out / "provenance.json").exists()


def test_cli_refuses_existing_files_without_force(tmp_path, monkeypatch, capsys):
    out = tmp_path / "v222"
    out.mkdir()
    (out / "SPY.csv").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(fbd, "fetch", _fetcher([]))
    assert fbd.shock_index_main(["--shock-index", "--cache-dir", str(out), "--end", END]) == 2
    assert "refusing" in capsys.readouterr().out
    assert fbd.shock_index_main(["--shock-index", "--cache-dir", str(out), "--end", END,
                                 "--force"]) == 0
    assert (out / "provenance.json").exists()


def test_cli_refuses_a_pinned_dir_even_with_force(tmp_path, monkeypatch):
    monkeypatch.setattr(fbd, "fetch", _fetcher([]))
    target = tmp_path / "data" / "backtest_cache_ext"
    assert fbd.shock_index_main(["--shock-index", "--cache-dir", str(target), "--force"]) == 2


def test_entry_dispatches_shock_index(monkeypatch):
    seen = []
    monkeypatch.setattr(fbd, "shock_index_main", lambda argv: seen.append(argv) or 0)
    assert fbd._entry(["--shock-index", "--cache-dir", "x"]) == 0
    assert seen == [["--shock-index", "--cache-dir", "x"]]
```

- [ ] **Step 3: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_fetch_shock_index.py`
Expected: FAIL — `AttributeError: module 'fetch_backtest_data' has no attribute 'SHOCK_INDEX_END'`.

- [ ] **Step 4: Implement `--shock-index` in `scripts/data/fetch_backtest_data.py`**

Add after `vix_context_main` (before `training_tickers`):

```python
# v222: daily SPY + ^VIX for the shock-index screen, in its own directory.
SHOCK_INDEX_END = "2026-11-04"          # the day before 2026-11-05 (spec § Frozen Window)
SHOCK_INDEX_SPY_START = "1993-01-01"    # before SPY's first bar; Yahoo returns from 1993-01-29
SHOCK_INDEX_VIX_START = "1990-01-01"
PINNED_CACHES = ("data/backtest_cache", "data/backtest_cache_ext")
SHOCK_INDEX_FILES = ("SPY.csv", f"{VIX_CONTEXT}.csv", "provenance.json")


def _is_pinned(cache_dir: Path) -> bool:
    """True for <any tree>/data/backtest_cache[_ext]: other screens read those."""
    return "/".join(Path(cache_dir).resolve().parts[-2:]) in PINNED_CACHES


def _yf_stop(end: str) -> str:
    return (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat()  # exclusive end


def fetch_shock_index(cache_dir: Path, *, end: str = SHOCK_INDEX_END, fetcher=fetch) -> dict:
    """Fetch daily SPY, then ^VIX through fetch_vix_context (session check vs
    that SPY file), into cache_dir; write and return provenance.json."""
    cache_dir = Path(cache_dir)
    if _is_pinned(cache_dir):
        raise screen_context.ContextError(
            f"{cache_dir}: a pinned cache is never written by --shock-index")
    raw = fetcher("SPY", SHOCK_INDEX_SPY_START, _yf_stop(end))
    if raw is None or raw.empty:
        raise screen_context.ContextError("SPY: the fetch returned no data")
    cache_dir.mkdir(parents=True, exist_ok=True)
    spy = _clean_vix_frame(raw, end)          # generic OHLCV clean: drop NaN rows, cut at end
    spy.to_csv(cache_dir / "SPY.csv")
    vix_path = fetch_vix_context(cache_dir, start=SHOCK_INDEX_VIX_START, end=end,
                                 fetcher=fetcher)
    vix = pd.read_csv(vix_path, parse_dates=["Date"], index_col="Date")
    prov = {
        "source": "yfinance daily (auto_adjust=True), fetch_backtest_data.py --shock-index",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "end": end,
        "spy_first": spy.index[0].date().isoformat(), "spy_rows": int(len(spy)),
        "vix_first": vix.index[0].date().isoformat(), "vix_rows": int(len(vix)),
    }
    (cache_dir / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n",
                                               encoding="utf-8")
    return prov


def shock_index_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="v222: daily SPY + ^VIX for the shock-index screen")
    ap.add_argument("--shock-index", action="store_true", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--end", default=SHOCK_INDEX_END)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    cache_dir = Path(args.cache_dir)
    existing = [name for name in SHOCK_INDEX_FILES if (cache_dir / name).exists()]
    if existing and not args.force:
        print(f"refusing: {', '.join(existing)} already in {cache_dir}; pass --force to refetch")
        return 2
    try:
        prov = fetch_shock_index(cache_dir, end=args.end, fetcher=fetch)
    except screen_context.ContextError as exc:
        print(f"error: {exc}")
        return 2
    print(f"+ SPY {prov['spy_rows']} bars from {prov['spy_first']}; ^VIX {prov['vix_rows']} "
          f"bars from {prov['vix_first']}; end {prov['end']} -> {cache_dir}")
    return 0
```

`fetcher=fetch` is looked up at call time inside `shock_index_main`, so the CLI tests' `monkeypatch.setattr(fbd, "fetch", ...)` takes effect. If the `^VIX` session check refuses after SPY was written, `SPY.csv` stays; a rerun needs `--force`. Extend `_entry`:

```python
def _entry(argv: list[str]) -> int | None:
    if "--shock-index" in argv:
        return shock_index_main(argv)
    if "--vix-context" in argv:
        return vix_context_main(argv)
    return main()
```

Add one paragraph to the module docstring after the `--vix-context` paragraph:

```text
--shock-index (v222) is its own mode: daily SPY from 1993 and, through the same
fetch_vix_context session check, daily ^VIX to 2026-11-04 into --cache-dir with a
provenance.json. It refuses data/backtest_cache and data/backtest_cache_ext.
    python scripts/data/fetch_backtest_data.py --shock-index --cache-dir data/v222
```

- [ ] **Step 5: Run the fetch tests, and the v211 neighbour, to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_fetch_shock_index.py`
Expected: 9 passed.
Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_fetch_vix_context.py`
Expected: all pass (unchanged behaviour).

- [ ] **Step 6: Commit the fetch mode**

```bash
git -C "$W" add scripts/data/fetch_backtest_data.py tests/backtest_scripts/test_fetch_shock_index.py
git -C "$W" commit -m "feat(v222): fetch_backtest_data --shock-index -- daily SPY + ^VIX to 2026-11-04, pinned caches refused"
```

- [ ] **Step 7: Fetch the real data (network) into the main tree's `data/v222/`**

```bash
python "$W/scripts/data/fetch_backtest_data.py" --shock-index --cache-dir "$D" > "$M/data/v222-fetch.log" 2>&1; echo "exit $?"; tail -2 "$M/data/v222-fetch.log"
```

Expected: `exit 0` and one `+ SPY ... ^VIX ...` line. Read nothing else from the files yet (the window is computed in V222-1b, before any cell). If the `^VIX` session check refuses (a missing or extra date after 2009-06-01), **stop and report `BLOCKED:` with the error line**; never loosen the check or patch the CSV.

### Task V222-1b: Screen module readers, `DATA_READERS` row, the window, Results scaffold

**Model:** sonnet — two small pure readers, one selector row and a doc edit.

**Files:**
- Create: `scripts/backtest/shock_index_screen.py`
- Create: `tests/backtest_scripts/test_shock_index_screen.py`
- Modify: `scripts/dev/select_tests.py` (one `DATA_READERS` row after the v209 A1 shock rows, l.~306-309)
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (**main tree**, append `## Results`; the controller commits it on `main`)

**Interfaces:**
- Consumes: `data/v222/{SPY.csv,^VIX.csv,provenance.json}` from V222-1 (main tree).
- Produces: `shock_index_screen.WINDOW_END = "2026-11-04"`, `OHLC = ["Open", "High", "Low", "Close"]`, `ROOT`; `read_daily(path: Path) -> pd.DataFrame` (Date index, `Open,High,Low,Close`, sorted); `common_window(spy, vix) -> dict` (`{"start": iso, "end": iso, "years": int, "sessions": int}`); the test file's `_frame(index, close=None)` helper and `sis` import, which V222-2..V222-4 reuse; `DATA_READERS` row `("data/v222/", ("tests/backtest_scripts/test_shock_index_screen.py",))`; the spec's `## Results` section with its window block and the pending headings later tasks fill.

- [ ] **Step 1: Write the failing reader tests**

Create `tests/backtest_scripts/test_shock_index_screen.py` (V222-2..V222-4 append to it):

```python
"""v222 Stage 1: the daily screen of the index + VIX shock path."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import shock_index_screen as sis  # noqa: E402


def _frame(index, close=None) -> pd.DataFrame:
    index = pd.DatetimeIndex(index, name="Date")
    close = np.linspace(100.0, 110.0, len(index)) if close is None else np.asarray(close, float)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.zeros(len(index))}, index=index)


def test_read_daily_keeps_ohlc_sorted(tmp_path):
    frame = _frame(pd.bdate_range("2020-01-01", periods=5))
    frame.iloc[::-1].to_csv(tmp_path / "SPY.csv")
    out = sis.read_daily(tmp_path / "SPY.csv")
    assert list(out.columns) == ["Open", "High", "Low", "Close"]
    assert out.index.is_monotonic_increasing and out.index.name == "Date"


def test_common_window_starts_at_the_first_shared_date_and_stops_at_11_04():
    spy = _frame(pd.bdate_range("1993-01-29", "2026-11-10"))
    vix = _frame(pd.bdate_range("1990-01-02", "2026-11-10"))
    window = sis.common_window(spy, vix)
    assert window["start"] == "1993-01-29" and window["end"] == "2026-11-04"
    assert window["years"] == 34
    assert window["sessions"] == len(pd.bdate_range("1993-01-29", "2026-11-04"))
    assert sis.WINDOW_END == "2026-11-04"


def test_common_window_refuses_disjoint_series():
    with pytest.raises(ValueError, match="share no session"):
        sis.common_window(_frame(pd.bdate_range("2020-01-01", periods=3)),
                          _frame(pd.bdate_range("2021-01-01", periods=3)))


def test_stage_data_routes_to_this_test():
    spec = importlib.util.spec_from_file_location("select_tests_v222",
                                                  ROOT / "scripts/dev/select_tests.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # @dataclass resolves annotations through sys.modules
    spec.loader.exec_module(mod)
    result = mod.select(["data/v222/SPY.csv"], ROOT)
    assert result.full is False
    assert "tests/backtest_scripts/test_shock_index_screen.py" in result.targets
```

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_index_screen'`.

- [ ] **Step 2: Create `scripts/backtest/shock_index_screen.py`**

```python
#!/usr/bin/env python3
"""v222 Stage 1: daily screen of the index + VIX shock path.

Pure functions over daily SPY and ^VIX bars (data/v222/, written by
`fetch_backtest_data.py --shock-index`): the window, the close and
upper-bound series, fire days and episodes, the 16-cell grid against the
6-episodes-per-year budget, the edge-aware winner rule, the prior check, the
descriptive arms and the Stage 2 day picker. Every frozen value is a module
constant copied from the spec's § Frozen section; none is ever re-chosen.

    python scripts/backtest/shock_index_screen.py --data-dir data/v222 \
        --out-json data/v222/stage1.json --out-md data/v222/stage1.md
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

WINDOW_END = "2026-11-04"
OHLC = ["Open", "High", "Low", "Close"]


def read_daily(path: Path) -> pd.DataFrame:
    """One daily CSV (Date,Open,High,Low,Close[,Volume]) as a sorted OHLC frame."""
    frame = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    return frame[OHLC].sort_index()


def common_window(spy: pd.DataFrame, vix: pd.DataFrame) -> dict:
    """First date both series exist to WINDOW_END; years counts calendar years."""
    common = spy.index.intersection(vix.index)
    common = common[common <= pd.Timestamp(WINDOW_END)]
    if not len(common):
        raise ValueError("SPY and ^VIX share no session up to " + WINDOW_END)
    start, end = common[0], common[-1]
    return {"start": start.date().isoformat(), "end": end.date().isoformat(),
            "years": int(end.year - start.year + 1), "sessions": int(len(common))}
```

- [ ] **Step 3: Add the `DATA_READERS` row**

Read `tests/dev/test_select_tests.py` around `test_shock_replay_fixtures_route_to_the_replay_test` (l.~724) and `test_no_path_a_test_reads_is_classified_inert` first; neither pins the row count. In `scripts/dev/select_tests.py`, directly after the `tests/fixtures/shock_replay_2026_11_05.json` row:

```python
    # v222: Stage 1 daily SPY / ^VIX and stage outputs (main tree, gitignored).
    ("data/v222/", ("tests/backtest_scripts/test_shock_index_screen.py",)),
```

No other row starts with `data/v2`, so first-match order is safe.

- [ ] **Step 4: Run the screen and selector tests**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 4 passed.
Run: `python "$W/scripts/dev/testrun.py" file tests/dev/test_select_tests.py`
Expected: all pass.

- [ ] **Step 5: Commit the reader and the row**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- daily readers and the common window"
git -C "$W" add scripts/dev/select_tests.py
git -C "$W" commit -m "chore(v222): DATA_READERS row for data/v222/"
```

- [ ] **Step 6: Compute the window (nothing else is read)**

```bash
python -c "import sys; sys.path.insert(0, r'$W/scripts/backtest'); import shock_index_screen as s; from pathlib import Path; d = Path(r'$D'); print(s.common_window(s.read_daily(d / 'SPY.csv'), s.read_daily(d / '^VIX.csv')))"
```

Expected: a dict like `{'start': '1993-01-29', 'end': '2026-11-04', 'years': 34, 'sessions': ...}`. If `end` is not `2026-11-04`, record the real end and flag it in the report; do not refetch with another `--end`.

- [ ] **Step 7: Append the Results scaffold to the spec (main tree)**

Append to `$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`, filling the angle-bracket values from `$D/provenance.json` and Step 6:

```markdown
## Results

### Stage 1 — window (written before any cell is read)

- Source: <provenance.source>, fetched <provenance.fetched_at> into the main
  tree's gitignored `data/v222/` by `fetch_backtest_data.py --shock-index`
  (v222 worktree commit <sha of V222-1 Step 6>).
- SPY daily: first bar <spy_first>, <spy_rows> rows. `^VIX` daily: first bar
  <vix_first>, <vix_rows> rows. Both end <end>.
- **Window: <start> to <end>, <years> calendar years, <sessions> common
  sessions.** A session is scored once 15 completed SPY bars precede it
  (ATR14, index § plan-time readings).

### Stage 1 — screen

Pending V222-5.

### Stage 2 day list

Pending V222-5.

### Stage 2

Pending V222-8.

### Production check

Pending V222-12.

### Stage 3

Pending V222-13.
```

Do not commit it: the controller commits Results on `main`. `git -C "$M" status --short` must show only the spec (beside any plan files the controller has open).

### Task V222-2: Daily series, fire days, episodes (no lookahead)

**Model:** opus — the no-lookahead arithmetic of the two series and the episode rule decide every Stage 1 verdict; an off-by-one here silently changes the winner.

**Files:**
- Modify: `scripts/backtest/shock_index_screen.py`
- Modify: `tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `read_daily`, `WINDOW_END`, `OHLC` (V222-1b); `swingbot.core.market.indicators.atr(df, period=14) -> pd.Series` (Wilder, `ewm(alpha=1/14, min_periods=14, adjust=False)` over true range; causal, so `atr(df).shift(1)` at row *i* equals `atr(df.iloc[:i]).iloc[-1]`).
- Produces: `GRID_K = (1.0, 1.25, 1.5, 2.0)`; `GRID_VIX = (10.0, 15.0, 20.0, 25.0)`; `EPISODE_GAP = 5`; `BUDGET_PER_YEAR = 6`; `EPS = 1e-9`; `ATR_PERIOD = 14`; `MIN_PRIOR_BARS = 15`; `SERIES = ("close", "upper", "spy_upper")`; `MOVE_COLUMNS`; `daily_moves(spy, vix) -> pd.DataFrame` (index = scored sessions; columns `spy_close_atr, spy_low_atr, spy_open_atr, vix_close_chg, vix_high_chg`); `fire_days(moves, k: float, v: float, series: str) -> list[pd.Timestamp]`; `episodes(fires, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]`; `episodes_per_year(eps, years: range) -> dict[int, int]`; `representative(ep, moves) -> pd.Timestamp`.

**The readings this task pins (index § plan-time readings, copied):** prior close = previous session's close; ATR14 from at least 15 completed bars dated before the session; close series SPY `(Close − prev)/ATR14`, VIX `(Close/prevClose − 1)·100`; upper bound SPY `(Low − prev)/ATR14`, VIX `(High/prevClose − 1)·100`; gap part `(Open − prev)/ATR14`; a bar is met with `1e-9` tolerance as `shock._meets` (`value + 1e-9 >= bar`). Fires separated by fewer than 5 sessions (session positions in the scored index) form one episode; an episode's year is its first fire's year; an episode's representative session has the most negative `spy_low_atr`, ties to the earlier session.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_screen.py`:

```python
from swingbot.core.market.indicators import atr  # noqa: E402


def test_frozen_constants_are_the_spec_values():
    assert sis.GRID_K == (1.0, 1.25, 1.5, 2.0)
    assert sis.GRID_VIX == (10.0, 15.0, 20.0, 25.0)
    assert (sis.EPISODE_GAP, sis.BUDGET_PER_YEAR, sis.EPS) == (5, 6, 1e-9)
    assert (sis.ATR_PERIOD, sis.MIN_PRIOR_BARS) == (14, 15)
    assert sis.SERIES == ("close", "upper", "spy_upper")


def _flat(n=20, start="2020-01-01"):
    """SPY with true range 2.0 every bar (ATR14 == 2.0) and VIX flat at 20."""
    idx = pd.bdate_range(start, periods=n, name="Date")
    spy = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0}, index=idx)
    vix = pd.DataFrame({"Open": 20.0, "High": 20.0, "Low": 20.0, "Close": 20.0}, index=idx)
    return spy, vix


def test_daily_moves_arithmetic_on_a_known_day():
    spy, vix = _flat()
    day = spy.index[17]
    spy.loc[day, ["Open", "High", "Low", "Close"]] = [99.0, 99.5, 95.0, 97.0]
    vix.loc[day, ["High", "Close"]] = [26.0, 24.0]
    row = sis.daily_moves(spy, vix).loc[day]
    assert row["spy_close_atr"] == pytest.approx(-1.5)      # (97 - 100) / 2
    assert row["spy_low_atr"] == pytest.approx(-2.5)        # (95 - 100) / 2
    assert row["spy_open_atr"] == pytest.approx(-0.5)       # (99 - 100) / 2
    assert row["vix_close_chg"] == pytest.approx(20.0)      # 24 / 20 - 1
    assert row["vix_high_chg"] == pytest.approx(30.0)       # 26 / 20 - 1
    assert list(sis.daily_moves(spy, vix).columns) == list(sis.MOVE_COLUMNS)


def test_a_session_needs_fifteen_prior_bars():
    spy, vix = _flat()
    moves = sis.daily_moves(spy, vix)
    assert moves.index[0] == spy.index[15]
    assert len(moves) == len(spy) - 15


def test_moves_stop_at_the_window_end():
    spy, vix = _flat(n=40, start="2026-10-01")
    assert sis.daily_moves(spy, vix).index[-1] == pd.Timestamp("2026-11-04")


def _walk(n=80, seed=7):
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    idx = pd.bdate_range("2019-01-01", periods=n, name="Date")
    spy = pd.DataFrame({"Open": close * (1 + rng.normal(0, 0.003, n)),
                        "High": close * 1.008, "Low": close * 0.99, "Close": close}, index=idx)
    vclose = 18.0 * np.exp(np.cumsum(rng.normal(0, 0.05, n)))
    vix = pd.DataFrame({"Open": vclose, "High": vclose * 1.06, "Low": vclose * 0.95,
                        "Close": vclose}, index=idx)
    return spy, vix


def test_atr_is_the_value_known_at_the_prior_close():
    spy, vix = _walk()
    moves = sis.daily_moves(spy, vix)
    for day in moves.index[::7]:
        before = spy[spy.index < day]
        expected = (spy.loc[day, "Close"] - before["Close"].iloc[-1]) / atr(before, 14).iloc[-1]
        assert moves.loc[day, "spy_close_atr"] == pytest.approx(expected)


def test_changing_a_later_bar_never_changes_an_earlier_reading():
    spy, vix = _walk()
    base = sis.daily_moves(spy, vix)
    cut = spy.index[50]
    spy2, vix2 = spy.copy(), vix.copy()
    spy2.loc[cut:, ["High", "Low", "Close", "Open"]] *= 0.7
    vix2.loc[cut:, ["High", "Close"]] *= 2.0
    changed = sis.daily_moves(spy2, vix2)
    pd.testing.assert_frame_equal(base[base.index < cut], changed[changed.index < cut])


def _moves(rows):
    idx = pd.bdate_range("2021-01-04", periods=len(rows), name="Date")
    return pd.DataFrame(rows, index=idx, columns=list(sis.MOVE_COLUMNS))


def test_fire_days_per_series_with_tolerance():
    moves = _moves([
        # spy_close, spy_low, spy_open, vix_close, vix_high
        (-1.0, -1.0, 0.0, 10.0, 10.0),                # exactly on both bars: fires
        (-1.0 + 5e-10, -1.0 + 5e-10, 0.0, 10.0 - 5e-10, 10.0),  # inside EPS: fires
        (-0.999, -2.0, 0.0, 5.0, 12.0),               # close misses SPY, upper fires
        (-3.0, -3.0, 0.0, 9.0, 9.0),                  # VIX half misses on both
        (0.5, -1.2, 0.0, -1.0, 0.0),                  # only the SPY-only upper fires
    ])
    d = list(moves.index)
    assert sis.fire_days(moves, 1.0, 10.0, "close") == [d[0], d[1]]
    assert sis.fire_days(moves, 1.0, 10.0, "upper") == [d[0], d[1], d[2]]
    assert sis.fire_days(moves, 1.0, 999.0, "spy_upper") == d    # v ignored
    with pytest.raises(ValueError, match="series"):
        sis.fire_days(moves, 1.0, 10.0, "low")


def test_episodes_join_fires_fewer_than_five_sessions_apart():
    sessions = pd.bdate_range("2021-01-04", periods=30, name="Date")
    fires = [sessions[p] for p in (20, 0, 4, 9, 10)]          # unsorted on purpose
    eps = sis.episodes(fires, sessions)
    assert eps == [[sessions[0], sessions[4]], [sessions[9], sessions[10]], [sessions[20]]]
    assert sis.episodes([], sessions) == []
    with pytest.raises(ValueError, match="session"):
        sis.episodes([pd.Timestamp("2021-01-09")], sessions)  # a Saturday


def test_episodes_per_year_counts_the_first_fire_year_and_zero_years():
    dec, jan = pd.Timestamp("2020-12-30"), pd.Timestamp("2021-01-04")
    eps = [[dec, jan], [pd.Timestamp("2022-03-01")]]
    assert sis.episodes_per_year(eps, range(2020, 2023)) == {2020: 1, 2021: 0, 2022: 1}


def test_representative_is_the_deepest_upper_bound_day_ties_earlier():
    moves = _moves([(0, -1.5, 0, 0, 0), (0, -2.5, 0, 0, 0), (0, -2.5, 0, 0, 0), (0, -0.5, 0, 0, 0)])
    d = list(moves.index)
    assert sis.representative(d, moves) == d[1]
    assert sis.representative([d[3]], moves) == d[3]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `AttributeError: module 'shock_index_screen' has no attribute 'GRID_K'`.

- [ ] **Step 3: Implement the series, fires and episodes**

Add to `scripts/backtest/shock_index_screen.py` (the indicator import goes with the other imports below `sys.path`):

```python
from swingbot.core.market.indicators import atr  # noqa: E402

# Frozen before any data is read (spec § Frozen; copied, never re-chosen).
GRID_K = (1.0, 1.25, 1.5, 2.0)            # index_atr_k: SPY down at least k ATR14
GRID_VIX = (10.0, 15.0, 20.0, 25.0)       # index_vix_chg: ^VIX up at least v percent
EPISODE_GAP = 5                           # fires fewer than 5 sessions apart = one episode
BUDGET_PER_YEAR = 6                       # at most 6 episodes in every calendar year (upper series)
EPS = 1e-9                                # shock._meets tolerance
ATR_PERIOD = 14
MIN_PRIOR_BARS = 15                       # completed SPY bars before a scored session
SERIES = ("close", "upper", "spy_upper")
MOVE_COLUMNS = ("spy_close_atr", "spy_low_atr", "spy_open_atr", "vix_close_chg", "vix_high_chg")


def daily_moves(spy: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """Per scored session: SPY close/low/open vs the prior close in ATR14 known
    at the prior close, and the ^VIX close/high change vs its prior close (%).

    Wilder's ATR is a causal ewm, so `atr(spy).shift(1)` on a session equals
    `atr(bars before the session).iloc[-1]`; nothing dated on or after the
    session enters its ATR or its prior close."""
    prev = spy["Close"].shift(1)
    atr_prev = atr(spy, ATR_PERIOD).shift(1)
    position = pd.Series(range(len(spy)), index=spy.index)
    keep = (position >= MIN_PRIOR_BARS) & (atr_prev > 0)
    spy_part = pd.DataFrame({
        "spy_close_atr": (spy["Close"] - prev) / atr_prev,
        "spy_low_atr": (spy["Low"] - prev) / atr_prev,
        "spy_open_atr": (spy["Open"] - prev) / atr_prev,
    }, index=spy.index)[keep]
    vix_prev = vix["Close"].shift(1)
    vix_part = pd.DataFrame({
        "vix_close_chg": (vix["Close"] / vix_prev - 1.0) * 100.0,
        "vix_high_chg": (vix["High"] / vix_prev - 1.0) * 100.0,
    }, index=vix.index)
    out = spy_part.join(vix_part, how="inner").dropna()
    out = out[out.index <= pd.Timestamp(WINDOW_END)]
    out.index.name = "Date"
    return out[list(MOVE_COLUMNS)]


def _meets(values: pd.Series, bar: float) -> pd.Series:
    return values + EPS >= bar


def fire_days(moves: pd.DataFrame, k: float, v: float, series: str) -> list[pd.Timestamp]:
    """Sessions where SPY is at least k ATR down and ^VIX at least v % up.
    'close' uses closes, 'upper' the SPY low and VIX high (the upper bound on
    the live rate), 'spy_upper' the SPY low alone (v ignored)."""
    if series not in SERIES:
        raise ValueError(f"series must be one of {SERIES}, got {series!r}")
    spy_col = "spy_close_atr" if series == "close" else "spy_low_atr"
    hit = _meets(-moves[spy_col], k)
    if series != "spy_upper":
        vix_col = "vix_close_chg" if series == "close" else "vix_high_chg"
        hit &= _meets(moves[vix_col], v)
    return list(moves.index[hit.to_numpy()])


def episodes(fires, sessions: pd.DatetimeIndex,
             gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]:
    """Group fire days whose session positions differ by fewer than `gap`."""
    if not len(fires):
        return []
    days = pd.DatetimeIndex(fires)
    pos = sessions.get_indexer(days)
    if (pos < 0).any():
        raise ValueError(f"fire day {days[pos < 0][0]:%Y-%m-%d} is not a scored session")
    out: list[list[pd.Timestamp]] = []
    last = None
    for p in sorted(pos):
        if last is None or p - last >= gap:
            out.append([])
        out[-1].append(sessions[p])
        last = p
    return out


def episodes_per_year(eps, years: range) -> dict[int, int]:
    counts = {year: 0 for year in years}
    for ep in eps:
        counts[ep[0].year] = counts.get(ep[0].year, 0) + 1
    return counts


def representative(ep, moves: pd.DataFrame) -> pd.Timestamp:
    """The episode session with the largest upper-bound SPY drop; ties earlier."""
    lows = moves.loc[list(ep), "spy_low_atr"]
    return lows.idxmin()
```

`idxmin` returns the first label of the minimum, and `ep` is in session order, so ties go to the earlier session.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 14 passed.

- [ ] **Step 5: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender (every function here is well under 15).

- [ ] **Step 6: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- daily close/upper series, fire days, episodes (no lookahead)"
```

### Task V222-3: Grid, budget, edge-aware winner rule, prior check, report CLI

**Model:** opus — the winner rule and its edge-cell reading are the pre-registered verdict; a wrong neighbour set or ordering picks a different cell or hides a NO-LIFT.

**Files:**
- Modify: `scripts/backtest/shock_index_screen.py`
- Modify: `tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `read_daily`, `common_window` (V222-1b); `GRID_K`, `GRID_VIX`, `BUDGET_PER_YEAR`, `EPISODE_GAP`, `daily_moves`, `fire_days`, `episodes`, `episodes_per_year` (V222-2); test helpers `_flat`, `_moves` (V222-2).
- Produces: `PRIOR = {"fail_k_max": 1.25, "fail_years_min": 2, "crisis_years": (2008, 2020), "winner_k_min": 1.5}`; `CellResult` (frozen dataclass: `k, v, close_fires, close_episodes, upper_fires, upper_episodes, upper_episode_sessions, per_year_close: dict[int, int], per_year_upper: dict[int, int], years_over_cap: tuple[int, ...], in_budget: bool`); `cell_key(k, v) -> str` (`f"{k:g},{v:g}"`, e.g. `"1.25,10"`; the key of `report["episodes"]`); `upper_episodes(moves, k, v) -> list[list[pd.Timestamp]]`; `screen_cell(moves, k, v, years) -> CellResult`; `screen_grid(moves, years: range) -> list[CellResult]` (k outer, v inner); `neighbours(k, v) -> list[tuple[float, float]]`; `qualifying(cells) -> list[tuple[float, float]]` (most sensitive first); `pick_winner(cells) -> tuple[float, float] | None`; `prior_report(cells, winner) -> dict`; `load(data_dir: Path) -> tuple[dict, pd.DataFrame]` (window, moves); `build_report(data_dir: Path) -> dict` with keys `window, scored_from, cells, qualifying, winner, prior, episodes` (`cells`: list of `cell_json` dicts; `winner`: `[k, v]` or `None`; `episodes`: `cell_key -> [[iso, ...], ...]`, upper series, every cell); `cell_json(c) -> dict`; `render_md(report: dict) -> str`; `main(argv=None) -> int` (CLI `--data-dir --out-json --out-md`). V222-3b and V222-4 extend `build_report`, `render_md` and `main`.

**Rules pinned here (spec § Frozen, copied):** a cell is in budget when its upper-bound series has at most 6 episodes in **every** calendar year of the window. Neighbours are the cells one grid step away on one axis, either direction (at most four); a cell qualifies only when it is in budget and **every neighbour that exists on the grid** is in budget; a missing beyond-edge neighbour counts neither for nor against. The winner is the most sensitive qualifying cell (lowest `index_atr_k`, then lowest `index_vix_chg`); none qualifies → **NO-LIFT**. The prior is reported per cell beside the failing-year count and never decides anything. Episode-session days = sessions from an episode's first to its last fire, inclusive, summed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_screen.py`:

```python
import json  # noqa: E402

ALL_CELLS = [(k, v) for k in sis.GRID_K for v in sis.GRID_VIX]


def test_prior_is_the_pre_registered_expectation():
    assert sis.PRIOR == {"fail_k_max": 1.25, "fail_years_min": 2,
                         "crisis_years": (2008, 2020), "winner_k_min": 1.5}
    assert sis.cell_key(1.25, 10.0) == "1.25,10" and sis.cell_key(2.0, 25.0) == "2,25"


def test_neighbours_are_one_step_on_one_axis_and_stop_at_the_edge():
    assert sis.neighbours(1.0, 10.0) == [(1.25, 10.0), (1.0, 15.0)]
    assert sis.neighbours(2.0, 25.0) == [(1.5, 25.0), (2.0, 20.0)]
    assert sorted(sis.neighbours(1.25, 15.0)) == [(1.0, 15.0), (1.25, 10.0),
                                                  (1.25, 20.0), (1.5, 15.0)]


def _cells(over=None):
    """16 synthetic cells; `over` maps (k, v) -> the years over the cap."""
    over = over or {}
    out = []
    for k, v in ALL_CELLS:
        years = tuple(over.get((k, v), ()))
        out.append(sis.CellResult(k, v, 0, 0, 0, 0, 0, {}, {}, years, not years))
    return out


def test_all_in_budget_picks_the_most_sensitive_corner():
    assert sis.pick_winner(_cells()) == (1.0, 10.0)
    assert len(sis.qualifying(_cells())) == 16


def test_an_out_of_budget_neighbour_disqualifies_and_order_is_k_then_v():
    cells = _cells({(1.0, 10.0): (2008,)})
    q = sis.qualifying(cells)
    assert (1.0, 15.0) not in q and (1.25, 10.0) not in q      # neighbour of the failing cell
    assert q[:2] == [(1.0, 20.0), (1.0, 25.0)]                  # edge cell: missing k=0.75 is ignored
    assert (1.25, 15.0) in q
    assert sis.pick_winner(cells) == (1.0, 20.0)


def test_low_k_failing_pushes_the_winner_to_the_high_edge():
    over = {(k, v): (2008, 2020) for k, v in ALL_CELLS if k <= 1.25}
    over[(1.5, 10.0)] = (2020,)
    assert sis.pick_winner(_cells(over)) == (2.0, 15.0)


def test_no_qualifying_cell_is_no_lift():
    assert sis.pick_winner(_cells({cell: (2020,) for cell in ALL_CELLS})) is None
    with pytest.raises(ValueError, match="16"):
        sis.qualifying(_cells()[:15])


def _screen_moves():
    """2019: one two-fire episode; 2020: seven one-day episodes (over the cap);
    2021: one day where only the (1.0, 10) upper-bound series fires."""
    idx = pd.bdate_range("2019-01-01", "2021-12-31", name="Date")
    moves = pd.DataFrame(0.0, index=idx, columns=list(sis.MOVE_COLUMNS))
    full = (-3.0, -3.0, 0.0, 30.0, 30.0)
    y2020 = [i for i, d in enumerate(idx) if d.year == 2020][:42:6]
    for pos in [10, 12, *y2020]:
        moves.iloc[pos] = full
    moves.iloc[[i for i, d in enumerate(idx) if d.year == 2021][100]] = (-0.5, -1.1, 0.0, 5.0, 12.0)
    return moves


def test_screen_grid_counts_both_series_per_year():
    cells = sis.screen_grid(_screen_moves(), range(2019, 2022))
    assert [(c.k, c.v) for c in cells] == ALL_CELLS
    low = cells[0]
    assert (low.close_fires, low.close_episodes) == (9, 8)
    assert (low.upper_fires, low.upper_episodes, low.upper_episode_sessions) == (10, 9, 11)
    assert low.per_year_upper == {2019: 1, 2020: 7, 2021: 1}
    assert low.per_year_close == {2019: 1, 2020: 7, 2021: 0}
    assert low.years_over_cap == (2020,) and low.in_budget is False
    high = cells[-1]
    assert (high.upper_fires, high.upper_episodes, high.upper_episode_sessions) == (9, 8, 10)


def test_prior_report_checks_low_k_cells_and_the_winner():
    over = {(1.0, 10.0): (2008, 2020), (1.25, 10.0): (2008,), (1.5, 10.0): (2001, 2008, 2020)}
    rep = sis.prior_report(_cells(over), (1.5, 15.0))
    rows = {(r["k"], r["v"]): r for r in rep["cells"]}
    assert rows[(1.0, 10.0)] == {"k": 1.0, "v": 10.0, "failing_years": 2, "expected_to_fail": True,
                                 "crisis_years_over": [2008, 2020], "as_expected": True}
    assert rows[(1.25, 10.0)]["as_expected"] is False
    assert rows[(1.0, 15.0)]["as_expected"] is False                # expected to fail, did not
    assert rows[(1.5, 10.0)]["expected_to_fail"] is False and rows[(1.5, 10.0)]["as_expected"] is None
    assert rep["winner_as_expected"] is True and rep["no_lift"] is False
    assert rep["low_k_as_expected"] == [1, 8]
    none = sis.prior_report(_cells(), None)
    assert none["no_lift"] is True and none["winner_as_expected"] is None


def _write(tmp_path, spy, vix):
    spy.to_csv(tmp_path / "SPY.csv")
    vix.to_csv(tmp_path / "^VIX.csv")
    return tmp_path


def test_build_report_and_cli_on_a_calm_tape(tmp_path):
    data = _write(tmp_path, *_flat(n=40))
    report = sis.build_report(data)
    assert set(report) >= {"window", "scored_from", "cells", "qualifying", "winner", "prior",
                           "episodes"}
    assert report["winner"] == [1.0, 10.0] and len(report["qualifying"]) == 16
    assert set(report["episodes"]) == {sis.cell_key(k, v) for k, v in ALL_CELLS}
    assert report["cells"][0]["per_year_upper"] == {"2020": 0}
    out_json, out_md = tmp_path / "s1.json", tmp_path / "s1.md"
    assert sis.main(["--data-dir", str(data), "--out-json", str(out_json),
                     "--out-md", str(out_md)]) == 0
    assert json.loads(out_json.read_text(encoding="utf-8"))["winner"] == [1.0, 10.0]
    md = out_md.read_text(encoding="utf-8")
    assert "| k | v (%) |" in md and "Winner: k = 1, v = 10" in md


def test_render_md_says_no_lift_without_a_winner(tmp_path):
    report = sis.build_report(_write(tmp_path, *_flat(n=40)))
    report.update(winner=None, qualifying=[])
    assert "**NO-LIFT**" in sis.render_md(report)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `AttributeError: module 'shock_index_screen' has no attribute 'PRIOR'`.

- [ ] **Step 3: Implement the grid, the winner rule and the prior**

Add `import argparse`, `import json` and `from dataclasses import asdict, dataclass` to the imports, then:

```python
# Pre-registered expectation (spec § Frozen Prior); reported, never deciding.
PRIOR = {"fail_k_max": 1.25, "fail_years_min": 2, "crisis_years": (2008, 2020),
         "winner_k_min": 1.5}


@dataclass(frozen=True)
class CellResult:
    k: float
    v: float
    close_fires: int
    close_episodes: int
    upper_fires: int
    upper_episodes: int
    upper_episode_sessions: int
    per_year_close: dict
    per_year_upper: dict
    years_over_cap: tuple
    in_budget: bool


def cell_key(k: float, v: float) -> str:
    return f"{k:g},{v:g}"


def upper_episodes(moves: pd.DataFrame, k: float, v: float) -> list[list[pd.Timestamp]]:
    return episodes(fire_days(moves, k, v, "upper"), moves.index)


def _episode_sessions(eps, sessions: pd.DatetimeIndex) -> int:
    return int(sum(sessions.get_loc(ep[-1]) - sessions.get_loc(ep[0]) + 1 for ep in eps))


def screen_cell(moves: pd.DataFrame, k: float, v: float, years: range) -> CellResult:
    close_fires = fire_days(moves, k, v, "close")
    close_eps = episodes(close_fires, moves.index)
    upper_fires = fire_days(moves, k, v, "upper")
    upper_eps = episodes(upper_fires, moves.index)
    per_upper = episodes_per_year(upper_eps, years)
    over = tuple(year for year, n in sorted(per_upper.items()) if n > BUDGET_PER_YEAR)
    return CellResult(k=k, v=v, close_fires=len(close_fires), close_episodes=len(close_eps),
                      upper_fires=len(upper_fires), upper_episodes=len(upper_eps),
                      upper_episode_sessions=_episode_sessions(upper_eps, moves.index),
                      per_year_close=episodes_per_year(close_eps, years),
                      per_year_upper=per_upper, years_over_cap=over, in_budget=not over)


def screen_grid(moves: pd.DataFrame, years: range) -> list[CellResult]:
    return [screen_cell(moves, k, v, years) for k in GRID_K for v in GRID_VIX]


def neighbours(k: float, v: float) -> list[tuple[float, float]]:
    """Cells one grid step away on one axis; beyond-edge cells do not exist."""
    i, j = GRID_K.index(k), GRID_VIX.index(v)
    out = []
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        a, b = i + di, j + dj
        if 0 <= a < len(GRID_K) and 0 <= b < len(GRID_VIX):
            out.append((GRID_K[a], GRID_VIX[b]))
    return out


def qualifying(cells) -> list[tuple[float, float]]:
    """In-budget cells whose every existing neighbour is in budget, most sensitive first."""
    budget = {(c.k, c.v): c.in_budget for c in cells}
    if len(budget) != len(GRID_K) * len(GRID_VIX):
        raise ValueError(f"the winner rule needs all 16 cells, got {len(budget)}")
    return [cell for cell in sorted(budget)
            if budget[cell] and all(budget[n] for n in neighbours(*cell))]


def pick_winner(cells) -> tuple[float, float] | None:
    q = qualifying(cells)
    return q[0] if q else None


def _prior_row(c: CellResult) -> dict:
    expected = c.k <= PRIOR["fail_k_max"]
    crisis = [y for y in PRIOR["crisis_years"] if y in c.years_over_cap]
    as_expected = None
    if expected:
        as_expected = (len(c.years_over_cap) >= PRIOR["fail_years_min"]
                       and len(crisis) == len(PRIOR["crisis_years"]))
    return {"k": c.k, "v": c.v, "failing_years": len(c.years_over_cap),
            "expected_to_fail": expected, "crisis_years_over": crisis,
            "as_expected": as_expected}


def prior_report(cells, winner) -> dict:
    rows = [_prior_row(c) for c in cells]
    low = [r for r in rows if r["expected_to_fail"]]
    return {"prior": dict(PRIOR, crisis_years=list(PRIOR["crisis_years"])), "cells": rows,
            "low_k_as_expected": [sum(1 for r in low if r["as_expected"]), len(low)],
            "no_lift": winner is None,
            "winner_as_expected": None if winner is None else winner[0] >= PRIOR["winner_k_min"]}
```

`sorted(budget)` sorts `(k, v)` tuples, which is exactly "lowest k, then lowest v".

- [ ] **Step 4: Implement the report, the markdown and the CLI**

```python
def cell_json(c: CellResult) -> dict:
    out = asdict(c)
    out["per_year_close"] = {str(y): n for y, n in c.per_year_close.items()}
    out["per_year_upper"] = {str(y): n for y, n in c.per_year_upper.items()}
    out["years_over_cap"] = list(c.years_over_cap)
    return out


def _isos(eps) -> list[list[str]]:
    return [[d.date().isoformat() for d in ep] for ep in eps]


def load(data_dir: Path) -> tuple[dict, pd.DataFrame]:
    spy, vix = read_daily(Path(data_dir) / "SPY.csv"), read_daily(Path(data_dir) / "^VIX.csv")
    return common_window(spy, vix), daily_moves(spy, vix)


def build_report(data_dir: Path) -> dict:
    window, moves = load(data_dir)
    years = range(int(window["start"][:4]), int(window["end"][:4]) + 1)
    cells = screen_grid(moves, years)
    winner = pick_winner(cells)
    return {"window": window, "scored_from": moves.index[0].date().isoformat(),
            "cells": [cell_json(c) for c in cells],
            "qualifying": [list(q) for q in qualifying(cells)],
            "winner": list(winner) if winner else None,
            "prior": prior_report(cells, winner),
            "episodes": {cell_key(c.k, c.v): _isos(upper_episodes(moves, c.k, c.v))
                         for c in cells}}


CELL_HEADER = ["| k | v (%) | close fires | close episodes | upper fires | upper episodes "
               "| upper episode-sessions | years over cap | in budget | prior |",
               "|---|---|---|---|---|---|---|---|---|---|"]


def _prior_text(row: dict) -> str:
    if row["as_expected"] is None:
        return "-"
    return "as expected" if row["as_expected"] else "not as expected"


def _cell_row(c: dict, prior_row: dict) -> str:
    over = ", ".join(str(y) for y in c["years_over_cap"]) or "none"
    return (f"| {c['k']:g} | {c['v']:g} | {c['close_fires']} | {c['close_episodes']} "
            f"| {c['upper_fires']} | {c['upper_episodes']} | {c['upper_episode_sessions']} "
            f"| {len(c['years_over_cap'])} ({over}) | {'yes' if c['in_budget'] else 'no'} "
            f"| {_prior_text(prior_row)} |")


def _year_table(cells: list[dict]) -> list[str]:
    keys = [cell_key(c["k"], c["v"]) for c in cells]
    lines = ["Upper-bound episodes per year (bold = over the cap):", "",
             "| year | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
    for year in cells[0]["per_year_upper"]:
        counts = [c["per_year_upper"][year] for c in cells]
        shown = [f"**{n}**" if n > BUDGET_PER_YEAR else str(n) for n in counts]
        lines.append(f"| {year} | " + " | ".join(shown) + " |")
    return lines


def _verdict(report: dict) -> list[str]:
    prior = report["prior"]
    q = ", ".join(cell_key(*cell) for cell in report["qualifying"]) or "none"
    if report["winner"]:
        k, v = report["winner"]
        head = f"Winner: k = {k:g}, v = {v:g}"
    else:
        head = "**NO-LIFT**: no in-budget cell has every existing neighbour in budget"
    return [f"Qualifying cells (most sensitive first): {q}.", "", head + ".", "",
            f"Prior: {prior['low_k_as_expected'][0]} of {prior['low_k_as_expected'][1]} cells "
            f"with k <= {PRIOR['fail_k_max']} broke the cap in >= {PRIOR['fail_years_min']} "
            f"years incl. 2008 and 2020; winner at k >= {PRIOR['winner_k_min']}: "
            f"{prior['winner_as_expected']}; NO-LIFT: {prior['no_lift']}."]


def render_md(report: dict) -> str:
    w = report["window"]
    prior = {(r["k"], r["v"]): r for r in report["prior"]["cells"]}
    lines = ["# v222 Stage 1 — daily screen", "",
             f"Window {w['start']} to {w['end']} ({w['years']} calendar years, "
             f"{w['sessions']} sessions); scored from {report['scored_from']}. Budget: at most "
             f"{BUDGET_PER_YEAR} upper-bound episodes in every calendar year; episode gap "
             f"{EPISODE_GAP} sessions.", "", *CELL_HEADER]
    lines += [_cell_row(c, prior[(c["k"], c["v"])]) for c in report["cells"]]
    lines += ["", *_year_table(report["cells"]), "", *_verdict(report)]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v222 Stage 1 daily screen")
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-md", required=True, type=Path)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(args.data_dir)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_md(report), encoding="utf-8")
    print("winner: " + (cell_key(*report["winner"]) if report["winner"] else "NO-LIFT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`_parser()` is split out so V222-3b and V222-4 add their flags there without growing `main`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 24 passed.

- [ ] **Step 6: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender.

- [ ] **Step 7: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- 16-cell grid, budget, edge-aware winner rule, prior, report CLI"
```

Do **not** run the CLI on `data/v222/` here: V222-5 runs Stage 1 once, after V222-3b and V222-4 have landed.

### Task V222-3b: Descriptive arms: SPY-only, gap/intraday split, macro days, VIX-high timing

**Model:** sonnet — descriptive tables over functions V222-2/V222-3 already pin; nothing here decides a cell or a gate.

**Files:**
- Modify: `scripts/backtest/shock_index_screen.py`
- Modify: `tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `GRID_K`, `fire_days`, `episodes`, `episodes_per_year`, `representative`, `BUDGET_PER_YEAR` (V222-2); `upper_episodes`, `load`, `screen_grid`, `pick_winner`, `build_report`, `render_md`, `_parser`, `main` (V222-3); test helpers `_flat`, `_moves`, `_screen_moves`, `_write`; `swingbot.core.market.market_events.FOMC_DECISION_DATES` (list of `dt.date`, today 2026-01-28..2027-12-08); `swingbot.core.market.session.RTH_OPEN`, `session.US_MARKET_TZ`.
- Produces: `SESSION_MINUTES = 390`; `spy_only_arm(moves, years: range) -> list[dict]` (per k: `{"k", "upper_fires", "upper_episodes", "years_over_cap": [int]}`); `macro_flag(d: date) -> str` (`"yes"`/`"no"`/`"unknown"`); `episode_splits(moves, eps) -> list[dict]` (`{"rep": iso, "total_atr", "gap_atr", "intraday_atr", "gap_share": float | None, "macro"}`); `session_open_utc(d: date) -> datetime`; `read_vix_1m(path: Path) -> pd.Series` (UTC bar start -> high, yfinance 3-header CSV); `vix_high_in_settle(vix_1m: pd.Series, open_utc: datetime, settle_min: int = 15) -> bool | None`; `descriptive_arms(moves, years, winner, vix_1m: dict[str, Path]) -> dict`; `build_report(data_dir: Path, vix_1m: dict[str, Path] | None = None) -> dict` adding keys `spy_only`, `splits` (winner cell's episodes, `[]` without a winner), `vix_high_timing` (`{iso: bool | None}`); CLI `--vix-1m DAY=PATH` (repeatable).

**Readings pinned here (index § plan-time readings, copied).** *Macro split:* `market_events.FOMC_DECISION_DATES` is the only calendar; inside its first..last span a representative session is `yes` if it is an FOMC decision date or a first Friday of the month (payrolls), else `no`; outside the span `unknown`. CPI is not used (the repo's CPI dates are approximations). With today's list (2026–2027) nearly every Stage 1 episode reads `unknown`; that is the honest answer, not a bug. *Gap/intraday split:* on the representative session, gap = `spy_open_atr`, intraday = `spy_low_atr − spy_open_atr`, gap share = gap / total (None when total is 0). *VIX-high timing:* the regular session is the 390 minutes from the open; `True` when the session's first maximum `High` bar starts before open + 15 min, `False` after, `None` with no bar in the session. Historical representative sessions have no one-minute `^VIX` and read `None` (unknown); a `--vix-1m DAY=PATH` day (2026-11-05, later shadow days) is measured. Everything here is descriptive and decides nothing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_screen.py`:

```python
from datetime import date, datetime, timezone  # noqa: E402


def test_spy_only_arm_drops_the_vix_half():
    arm = sis.spy_only_arm(_screen_moves(), range(2019, 2022))
    assert [row["k"] for row in arm] == list(sis.GRID_K)
    assert arm[0] == {"k": 1.0, "upper_fires": 10, "upper_episodes": 9, "years_over_cap": [2020]}
    assert (arm[1]["upper_fires"], arm[1]["upper_episodes"]) == (9, 8)   # -1.1 misses 1.25


@pytest.mark.parametrize("day, flag", [
    (date(2026, 3, 18), "yes"),      # FOMC decision date
    (date(2026, 3, 6), "yes"),       # first Friday (payrolls)
    (date(2026, 3, 13), "no"),       # a later Friday
    (date(2026, 3, 10), "no"),
    (date(2025, 4, 4), "unknown"),   # before the calendar span
    (date(2028, 1, 7), "unknown"),   # after it
])
def test_macro_flag_reads_only_inside_the_fomc_span(day, flag):
    assert sis.macro_flag(day) == flag


def test_episode_splits_use_the_representative_session():
    moves = _moves([(0, -1.5, -0.5, 0, 0), (0, -2.0, -1.5, 0, 0), (0, 0.0, 0.0, 0, 0)])
    d = list(moves.index)
    rows = sis.episode_splits(moves, [[d[0], d[1]], [d[2]]])
    assert rows[0] == {"rep": d[1].date().isoformat(), "total_atr": -2.0, "gap_atr": -1.5,
                       "intraday_atr": -0.5, "gap_share": 0.75, "macro": "unknown"}
    assert rows[1]["gap_share"] is None


def _vix_csv(path, stamps, highs):
    lines = ["Price,Adj Close,Close,High,Low,Open,Volume", "Ticker,^VIX,^VIX,^VIX,^VIX,^VIX,^VIX",
             "Datetime,,,,,,"]
    lines += [f"{s}+00:00,{h - 0.1},{h - 0.1},{h},{h - 0.2},{h - 0.1},0"
              for s, h in zip(stamps, highs)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_read_vix_1m_parses_the_three_header_csv(tmp_path):
    path = _vix_csv(tmp_path / "v.csv", ["2026-11-05 14:31:00", "2026-11-05 14:30:00"],
                    [21.0, 20.0])
    s = sis.read_vix_1m(path)
    assert str(s.index.tz) == "UTC" and s.index.is_monotonic_increasing
    assert s.iloc[0] == pytest.approx(20.0) and s.iloc[1] == pytest.approx(21.0)


def test_vix_high_in_settle_true_false_unknown():
    open_utc = datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc)
    idx = pd.date_range("2026-11-05 14:00", periods=400, freq="1min", tz="UTC")
    early = pd.Series(20.0, index=idx)
    early[pd.Timestamp("2026-11-05 14:44", tz="UTC")] = 30.0
    early[pd.Timestamp("2026-11-05 14:10", tz="UTC")] = 40.0     # pre-open: ignored
    assert sis.vix_high_in_settle(early, open_utc) is True
    late = pd.Series(20.0, index=idx)
    late[pd.Timestamp("2026-11-05 14:45", tz="UTC")] = 30.0       # first bar after settle
    assert sis.vix_high_in_settle(late, open_utc) is False
    assert sis.vix_high_in_settle(early, open_utc + pd.Timedelta(days=1)) is None


def test_session_open_utc_is_dst_aware():
    assert sis.session_open_utc(date(2026, 11, 5)) == datetime(2026, 11, 5, 14, 30, tzinfo=timezone.utc)
    assert sis.session_open_utc(date(2026, 7, 1)) == datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)


def test_build_report_carries_the_arms_and_the_cli_reads_vix_1m(tmp_path):
    data = _write(tmp_path, *_flat(n=40))
    stamps = [f"2026-11-05 14:{m:02d}:00" for m in range(30, 60)]
    vix = _vix_csv(tmp_path / "vix1m.csv", stamps, [20.0 + m for m in range(30)])
    report = sis.build_report(data, vix_1m={"2026-11-05": vix})
    assert len(report["spy_only"]) == 4 and report["splits"] == []
    assert report["vix_high_timing"] == {"2026-11-05": False}   # rising all session
    out_json, out_md = tmp_path / "s1.json", tmp_path / "s1.md"
    assert sis.main(["--data-dir", str(data), "--out-json", str(out_json), "--out-md", str(out_md),
                     "--vix-1m", f"2026-11-05={vix}"]) == 0
    md = out_md.read_text(encoding="utf-8")
    assert "SPY-only arm" in md and "VIX high in the open-settle window" in md
    with pytest.raises(SystemExit):
        sis.main(["--data-dir", str(data), "--out-json", str(out_json), "--out-md", str(out_md),
                  "--vix-1m", "no-equals-sign"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL — `AttributeError: module 'shock_index_screen' has no attribute 'spy_only_arm'`.

- [ ] **Step 3: Implement the arms**

Add `from datetime import date, datetime, timezone` to the imports and, below the `sys.path` block, `from swingbot.core.market import market_events, session  # noqa: E402`. Then add after `prior_report`:

```python
SESSION_MINUTES = 390          # regular session length from the open (descriptive window)


def spy_only_arm(moves: pd.DataFrame, years: range) -> list[dict]:
    """Per k, the upper-bound series with the VIX half dropped (descriptive)."""
    rows = []
    for k in GRID_K:
        fires = fire_days(moves, k, 0.0, "spy_upper")
        eps = episodes(fires, moves.index)
        per_year = episodes_per_year(eps, years)
        rows.append({"k": k, "upper_fires": len(fires), "upper_episodes": len(eps),
                     "years_over_cap": [y for y, n in sorted(per_year.items())
                                        if n > BUDGET_PER_YEAR]})
    return rows


def macro_flag(d: date) -> str:
    """FOMC decision date or first Friday inside the FOMC calendar's span."""
    span = market_events.FOMC_DECISION_DATES
    if not span or not (min(span) <= d <= max(span)):
        return "unknown"
    first_friday = d.weekday() == 4 and d.day <= 7
    return "yes" if d in set(span) or first_friday else "no"


def episode_splits(moves: pd.DataFrame, eps) -> list[dict]:
    rows = []
    for ep in eps:
        rep = representative(ep, moves)
        total = float(moves.loc[rep, "spy_low_atr"])
        gap = float(moves.loc[rep, "spy_open_atr"])
        rows.append({"rep": rep.date().isoformat(), "total_atr": total, "gap_atr": gap,
                     "intraday_atr": total - gap,
                     "gap_share": gap / total if total else None,
                     "macro": macro_flag(rep.date())})
    return rows


def session_open_utc(d: date) -> datetime:
    return datetime.combine(d, session.RTH_OPEN,
                            tzinfo=session.US_MARKET_TZ).astimezone(timezone.utc)


def read_vix_1m(path: Path) -> pd.Series:
    """yfinance one-minute CSV (rows Price/Ticker/Datetime, then bars) -> High by UTC bar start."""
    with open(path, encoding="utf-8") as fh:
        names = fh.readline().strip().split(",")
    names[0] = "Datetime"
    frame = pd.read_csv(path, skiprows=3, header=None, names=names)
    index = pd.DatetimeIndex(pd.to_datetime(frame["Datetime"], utc=True))
    return pd.Series(frame["High"].to_numpy(float), index=index, name="High").sort_index()


def vix_high_in_settle(vix_1m: pd.Series, open_utc: datetime,
                       settle_min: int = 15) -> bool | None:
    start = pd.Timestamp(open_utc)
    end = start + pd.Timedelta(minutes=SESSION_MINUTES)
    day = vix_1m[(vix_1m.index >= start) & (vix_1m.index < end)].dropna()
    if day.empty:
        return None
    return bool(day.idxmax() < start + pd.Timedelta(minutes=settle_min))


def vix_high_timing(win_eps, moves: pd.DataFrame, vix_1m: dict[str, Path]) -> dict:
    timing = {representative(ep, moves).date().isoformat(): None for ep in win_eps}
    for iso, path in sorted(vix_1m.items()):
        bars = read_vix_1m(Path(path))
        timing[iso] = vix_high_in_settle(bars, session_open_utc(date.fromisoformat(iso)))
    return timing


def descriptive_arms(moves: pd.DataFrame, years: range, winner,
                     vix_1m: dict[str, Path]) -> dict:
    win_eps = upper_episodes(moves, *winner) if winner else []
    return {"spy_only": spy_only_arm(moves, years),
            "splits": episode_splits(moves, win_eps),
            "vix_high_timing": vix_high_timing(win_eps, moves, vix_1m)}
```

- [ ] **Step 4: Wire the arms into the report, the markdown and the CLI**

Replace `build_report` with (the first seven lines are unchanged):

```python
def build_report(data_dir: Path, vix_1m: dict[str, Path] | None = None) -> dict:
    window, moves = load(data_dir)
    years = range(int(window["start"][:4]), int(window["end"][:4]) + 1)
    cells = screen_grid(moves, years)
    winner = pick_winner(cells)
    report = {"window": window, "scored_from": moves.index[0].date().isoformat(),
              "cells": [cell_json(c) for c in cells],
              "qualifying": [list(q) for q in qualifying(cells)],
              "winner": list(winner) if winner else None,
              "prior": prior_report(cells, winner),
              "episodes": {cell_key(c.k, c.v): _isos(upper_episodes(moves, c.k, c.v))
                           for c in cells}}
    report.update(descriptive_arms(moves, years, winner, vix_1m or {}))
    return report
```

Add the markdown sections and call them from `render_md`, whose last two lines become:

```python
    lines += ["", *_year_table(report["cells"]), "", *_verdict(report)]
    lines += ["", *_arms_md(report)]
    return "\n".join(lines) + "\n"
```

```python
def _fmt(x) -> str:
    return "-" if x is None else f"{x:.2f}"


def _spy_only_md(rows: list[dict]) -> list[str]:
    lines = ["## SPY-only arm (descriptive: upper-bound series, VIX half dropped)", "",
             "| k | upper fires | upper episodes | years over cap |", "|---|---|---|---|"]
    for r in rows:
        over = ", ".join(str(y) for y in r["years_over_cap"]) or "none"
        lines.append(f"| {r['k']:g} | {r['upper_fires']} | {r['upper_episodes']} | {over} |")
    return lines


def _splits_md(rows: list[dict]) -> list[str]:
    if not rows:
        return ["## Winner episodes: gap vs intraday, macro days", "", "No winner: no splits."]
    macro = {flag: sum(1 for r in rows if r["macro"] == flag) for flag in ("yes", "no", "unknown")}
    lines = ["## Winner episodes: gap vs intraday, macro days (descriptive)", "",
             f"Macro (FOMC or first Friday, inside the FOMC calendar only): yes {macro['yes']}, "
             f"no {macro['no']}, unknown {macro['unknown']}.", "",
             "| representative | total ATR | gap ATR | intraday ATR | gap share | macro |",
             "|---|---|---|---|---|---|"]
    lines += [f"| {r['rep']} | {_fmt(r['total_atr'])} | {_fmt(r['gap_atr'])} "
              f"| {_fmt(r['intraday_atr'])} | {_fmt(r['gap_share'])} | {r['macro']} |"
              for r in rows]
    return lines


def _timing_md(timing: dict) -> list[str]:
    shown = {True: "yes", False: "no", None: "unknown"}
    lines = ["## VIX high in the open-settle window (descriptive)", "",
             "| session | VIX high inside open + 15 min |", "|---|---|"]
    lines += [f"| {iso} | {shown[value]} |" for iso, value in sorted(timing.items())]
    return lines


def _arms_md(report: dict) -> list[str]:
    return [*_spy_only_md(report["spy_only"]), "", *_splits_md(report["splits"]), "",
            *_timing_md(report["vix_high_timing"])]
```

Extend `_parser` and `main`:

```python
def _day_path(text: str) -> tuple[str, Path]:
    iso, sep, path = text.partition("=")
    if not sep or not path:
        raise argparse.ArgumentTypeError(f"expected DAY=PATH, got {text!r}")
    date.fromisoformat(iso)                       # raises ValueError on a bad day
    return iso, Path(path)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="v222 Stage 1 daily screen")
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-md", required=True, type=Path)
    ap.add_argument("--vix-1m", action="append", default=[], type=_day_path,
                    metavar="DAY=PATH", help="one-minute ^VIX CSV for a session (repeatable)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(args.data_dir, vix_1m=dict(args.vix_1m))
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_md(report), encoding="utf-8")
    print("winner: " + (cell_key(*report["winner"]) if report["winner"] else "NO-LIFT"))
    return 0
```

argparse turns the `ArgumentTypeError` (and the `ValueError` of a bad ISO day) into exit 2 via `SystemExit`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_screen.py`
Expected: 36 passed (24 earlier + 12 new, the macro case counting 6).

- [ ] **Step 6: Complexity check**

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new offender.

- [ ] **Step 7: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C "$W" commit -m "feat(v222): shock_index_screen -- descriptive arms (SPY-only, gap/intraday, macro, VIX-high timing)"
```

