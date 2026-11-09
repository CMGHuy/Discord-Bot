# v222 — Market-shock detector: index + VIX entry path — Part 1: Stage 1 daily screen (V222-1..V222-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Architecture, **Global Constraints** (frozen grid, episode, budget, winner rule and the plan-time operational readings) and the task ledger live there; every task below implicitly includes them.

## Parallelisation

See the index. Inside this part: V222-1 → V222-2 → V222-3 → V222-5 is sequential
(V222-2/3 share one module; V222-5 runs everything). V222-4 touches disjoint files and
may run beside V222-2/V222-3.

Conventions for every task in this part:

- `W` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector`
  (code, tests, commits on branch `2026-11-05-v209-market-shock-detector`).
- `M` = `E:/Documents/Private/Projects/Discord-Bot` (main tree: the spec's `## Results`,
  and the gitignored stage data in `M/data/v222/`).
- Never `cd`; run tests by the absolute path of `W`'s runner,
  e.g.
  `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_fetch_shock_index_daily.py`
  (the runner resolves the repo from its own location).
- Scripts read from / write to `M/data/v222/` through an **absolute** `--data-dir`.

# Phase 1 — Stage 1 data, screen and forward long-book

### Task V222-1: Daily SPY + ^VIX to 2026-11-04, provenance, Results scaffold and frozen window

**Model:** sonnet — one standalone fetch script with a stubbed network seam; no `swingbot/core` change.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/fetch_shock_index_daily.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_fetch_shock_index_daily.py`
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (main tree: new `## Results` section, Stage 1 data/window table only)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (for V222-3, V222-4, V222-5):
  - `fetch_shock_index_daily.WINDOW_END = date(2026, 11, 4)`
  - `fetch_daily(symbol: str, end: date, *, download=None) -> pd.DataFrame` — `Date` index (tz-naive, normalised), columns `Open, High, Low, Close` (float), rows `<= end`.
  - `read_daily(path: Path) -> pd.DataFrame` — same shape, from a CSV this script wrote.
  - `common_window(spy, vix) -> dict` — keys `start`, `end` (ISO strings), `years` (int, calendar years touched), `sessions` (int, common sessions).
  - Files in `M/data/v222/`: `SPY.csv`, `VIX.csv`, `provenance.json`.

Why a dedicated directory: extending `data/backtest_cache_ext/^VIX.csv` would change a file the v211 plan reads, and `backtest_cache.cache_path` writes `_VIX.csv` for `^VIX` (naming trap). `data/v222/` is gitignored with the rest of `data/`.

- [ ] **Step 1: Write the failing tests**

`W/tests/scripts/test_fetch_shock_index_daily.py`:

```python
"""v222 V222-1: daily SPY + ^VIX fetch for the Stage 1 screen (network stubbed)."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import fetch_shock_index_daily as fsd  # noqa: E402


def _raw(symbol, days, *, multi=True, tz=None, close=100.0):
    idx = pd.DatetimeIndex(pd.to_datetime(days))
    if tz:
        idx = idx.tz_localize(tz)
    n = len(days)
    df = pd.DataFrame({"Open": [close] * n, "High": [close + 1] * n,
                       "Low": [close - 1] * n, "Close": [close] * n,
                       "Volume": [0] * n}, index=idx)
    if multi:
        df.columns = pd.MultiIndex.from_product([df.columns, [symbol]],
                                                names=["Price", "Ticker"])
    return df


def _download(frames):
    calls = []

    def fake(symbol, start, end):
        calls.append((symbol, start, end))
        return frames[symbol]
    fake.calls = calls
    return fake


def test_window_end_is_the_day_before_the_replay():
    assert fsd.WINDOW_END == date(2026, 11, 4)


def test_fetch_daily_flattens_trims_and_normalises():
    raw = _raw("SPY", ["2026-11-03", "2026-11-04", "2026-11-05"], tz="America/New_York")
    dl = _download({"SPY": raw})
    df = fsd.fetch_daily("SPY", date(2026, 11, 4), download=dl)
    assert list(df.columns) == ["Open", "High", "Low", "Close"]
    assert df.index.name == "Date" and df.index.tz is None
    assert [d.date().isoformat() for d in df.index] == ["2026-11-03", "2026-11-04"]
    assert dl.calls == [("SPY", "1990-01-01", "2026-11-05")]   # yfinance end is exclusive


def test_fetch_daily_drops_rows_without_a_close_and_duplicate_dates():
    raw = _raw("^VIX", ["2026-11-02", "2026-11-03", "2026-11-03"], multi=False)
    raw.iloc[0, raw.columns.get_loc("Close")] = float("nan")
    df = fsd.fetch_daily("^VIX", date(2026, 11, 4), download=_download({"^VIX": raw}))
    assert [d.date().isoformat() for d in df.index] == ["2026-11-03"]


@pytest.mark.parametrize("raw", [pd.DataFrame(), None])
def test_fetch_daily_refuses_an_empty_download(raw):
    with pytest.raises(ValueError):
        fsd.fetch_daily("SPY", date(2026, 11, 4), download=lambda *a: raw)


def test_fetch_daily_refuses_missing_columns():
    raw = _raw("SPY", ["2026-11-03"], multi=False).drop(columns=["Low"])
    with pytest.raises(ValueError, match="Low"):
        fsd.fetch_daily("SPY", date(2026, 11, 4), download=lambda *a: raw)


def test_read_daily_round_trips_what_main_writes(tmp_path):
    df = fsd.fetch_daily("SPY", date(2026, 11, 4),
                         download=lambda *a: _raw("SPY", ["2026-11-03", "2026-11-04"]))
    path = tmp_path / "SPY.csv"
    df.to_csv(path)
    back = fsd.read_daily(path)
    pd.testing.assert_frame_equal(back, df, check_freq=False)


def test_common_window_is_the_intersection_up_to_the_window_end():
    spy = fsd.fetch_daily("SPY", date(2027, 1, 1), download=lambda *a: _raw(
        "SPY", ["2024-12-30", "2024-12-31", "2025-01-02", "2026-11-04", "2026-11-05"]))
    vix = fsd.fetch_daily("^VIX", date(2027, 1, 1), download=lambda *a: _raw(
        "^VIX", ["2024-12-31", "2025-01-02", "2026-11-04", "2026-11-05"]))
    assert fsd.common_window(spy, vix) == {"start": "2024-12-31", "end": "2026-11-04",
                                           "years": 3, "sessions": 3}


def test_common_window_refuses_disjoint_series():
    spy = fsd.fetch_daily("SPY", date(2026, 11, 4),
                          download=lambda *a: _raw("SPY", ["2026-11-03"]))
    vix = fsd.fetch_daily("^VIX", date(2026, 11, 4),
                          download=lambda *a: _raw("^VIX", ["2026-11-04"]))
    with pytest.raises(ValueError):
        fsd.common_window(spy, vix)


def test_main_writes_both_csvs_and_provenance_then_refuses_to_overwrite(tmp_path, capsys):
    days = ["2026-11-02", "2026-11-03", "2026-11-04"]
    dl = _download({"SPY": _raw("SPY", days), "^VIX": _raw("^VIX", days, close=20.0)})
    assert fsd.main(["--data-dir", str(tmp_path)], download=dl) == 0
    assert {p.name for p in tmp_path.iterdir()} == {"SPY.csv", "VIX.csv", "provenance.json"}
    prov = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    assert prov["source"] == "yahoo" and prov["auto_adjust"] is True
    assert prov["window_end"] == "2026-11-04"
    assert prov["window"] == {"start": "2026-11-02", "end": "2026-11-04",
                              "years": 1, "sessions": 3}
    assert prov["files"]["VIX.csv"]["symbol"] == "^VIX"
    assert prov["files"]["SPY.csv"]["rows"] == 3
    assert len(prov["files"]["SPY.csv"]["sha256"]) == 64
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["sessions"] == 3
    before = (tmp_path / "SPY.csv").read_bytes()
    assert fsd.main(["--data-dir", str(tmp_path)], download=dl) == 2   # frozen once fetched
    assert (tmp_path / "SPY.csv").read_bytes() == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_fetch_shock_index_daily.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'fetch_shock_index_daily'`).

- [ ] **Step 3: Write the implementation**

`W/scripts/data/fetch_shock_index_daily.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 1: daily SPY and ^VIX from Yahoo up to the frozen window end.

Yahoo through yfinance (``auto_adjust=True``) is the live tape's source. The
files go to a dedicated directory (``--data-dir``, normally the main tree's
gitignored ``data/v222/``), never ``data/backtest_cache_ext/``: extending the
cached ``^VIX.csv`` there would change a file the v211 plan reads.

Once ``provenance.json`` exists the data is frozen: a second run refuses
(exit 2) unless ``--force``, so a cell can never be read on re-fetched data.

    python scripts/data/fetch_shock_index_daily.py --data-dir <abs>/data/v222
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

WINDOW_END = date(2026, 11, 4)          # spec § Frozen: the day before the replay
EARLIEST = "1990-01-01"                 # before either series begins
COLUMNS = ["Open", "High", "Low", "Close"]
FILES = {"SPY": "SPY.csv", "^VIX": "VIX.csv"}


def _yf_download(symbol: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.download(symbol, start=start, end=end, auto_adjust=True,
                       progress=False, actions=False)


def _normalise(raw: pd.DataFrame | None, end: date) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError("the download returned no rows")
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"the download lacks columns {missing}")
    df = df[COLUMNS].astype(float).dropna(subset=["Close"])
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    df.index.name = "Date"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[df.index <= pd.Timestamp(end)]


def fetch_daily(symbol: str, end: date, *, download=None) -> pd.DataFrame:
    """Every daily bar of ``symbol`` up to and including ``end``."""
    dl = download or _yf_download
    df = _normalise(dl(symbol, EARLIEST, (end + timedelta(days=1)).isoformat()), end)
    if df.empty:
        raise ValueError(f"{symbol}: no rows on or before {end}")
    return df


def read_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    return df[COLUMNS].astype(float)


def common_window(spy: pd.DataFrame, vix: pd.DataFrame) -> dict:
    """First to last session both series carry, capped at WINDOW_END."""
    common = spy.index.intersection(vix.index)
    common = common[common <= pd.Timestamp(WINDOW_END)]
    if common.empty:
        raise ValueError("SPY and ^VIX share no session")
    start, end = common[0], common[-1]
    return {"start": start.date().isoformat(), "end": end.date().isoformat(),
            "years": end.year - start.year + 1, "sessions": len(common)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yf_version() -> str:
    try:
        from importlib.metadata import version
        return version("yfinance")
    except Exception:  # noqa: BLE001 -- provenance only
        return "unknown"


def _file_record(symbol: str, df: pd.DataFrame, path: Path) -> dict:
    return {"symbol": symbol, "first": df.index[0].date().isoformat(),
            "last": df.index[-1].date().isoformat(), "rows": len(df),
            "sha256": _sha256(path)}


def _parse(argv):
    p = argparse.ArgumentParser(description="v222 Stage 1 daily SPY/^VIX fetch")
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--force", action="store_true",
                   help="re-fetch over frozen files (never after a cell is read)")
    return p.parse_args(argv)


def main(argv=None, *, download=None) -> int:
    args = _parse(argv)
    out = args.data_dir
    if (out / "provenance.json").exists() and not args.force:
        print(f"{out / 'provenance.json'} exists: the data is frozen", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    frames, files = {}, {}
    for symbol, name in FILES.items():
        frames[symbol] = fetch_daily(symbol, WINDOW_END, download=download)
        frames[symbol].to_csv(out / name)
        files[name] = _file_record(symbol, frames[symbol], out / name)
    window = common_window(frames["SPY"], frames["^VIX"])
    prov = {"source": "yahoo", "library": f"yfinance {_yf_version()}",
            "auto_adjust": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window_end": WINDOW_END.isoformat(), "window": window, "files": files}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    print(json.dumps(window))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_fetch_shock_index_daily.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit the script (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/data/fetch_shock_index_daily.py tests/scripts/test_fetch_shock_index_daily.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): daily SPY and ^VIX fetch for the Stage 1 screen" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Fetch once (network) into the main tree's `data/v222/`**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/data/fetch_shock_index_daily.py --data-dir E:/Documents/Private/Projects/Discord-Bot/data/v222
```

Expected: exit 0; the last stdout line is `{"start": ..., "end": "2026-11-04", "years": ..., "sessions": ...}`.
If `end` is not `2026-11-04` (Yahoo lacks a bar), stop and report: the frozen window end never moves.
`git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows nothing new (`data/` is gitignored).
**Read no per-cell number in this task** — only the window line and `provenance.json`.

- [ ] **Step 7: Add the `## Results` scaffold with the frozen window to the spec (main tree)**

Append at the end of `M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`
(after `## Panel review`), filling every `<...>` from `provenance.json` (exact values, no rounding):

```markdown
## Results

Filled by plan v222 as each stage closes. A subsection is never edited after
the stage that wrote it; a later stage adds its own.

### Stage 1 — data and window (frozen before any cell was read)

| Item | Value |
|---|---|
| Source | Yahoo via `<library>` (`auto_adjust=True`), the live tape's source |
| Fetched (UTC) | `<fetched_at>` |
| SPY daily | `<files["SPY.csv"].first>` to `<.last>`, `<.rows>` rows, sha256 `<.sha256>` |
| ^VIX daily | `<files["VIX.csv"].first>` to `<.last>`, `<.rows>` rows, sha256 `<.sha256>` |
| Window | `<window.start>` to `<window.end>` |
| Calendar years | `<window.years>` (first and last may be partial) |
| Common sessions | `<window.sessions>` |
| Files | main tree `data/v222/` (gitignored): `SPY.csv`, `VIX.csv`, `provenance.json` |
```

- [ ] **Step 8: Commit the scaffold on `main` (controller)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v222): Results scaffold -- Stage 1 window frozen before any cell is read" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V222-2: Daily series, fire days and episodes (no lookahead)

**Model:** opus — no-lookahead daily series that feed a gate (statistical code feeding gate 1).

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_screen.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: `swingbot.core.market.indicators.atr(df, period=14) -> pd.Series` (exists, Wilder EWM, `adjust=False`, so causal); frames shaped like `fetch_shock_index_daily.read_daily` (V222-1): `Date` index, `Open, High, Low, Close`.
- Produces (for V222-3, V222-4 via JSON, V222-5):
  - constants `GRID_K = (1.0, 1.25, 1.5, 2.0)`, `GRID_VIX = (10.0, 15.0, 20.0, 25.0)`, `EPISODE_GAP = 5`, `BUDGET_PER_YEAR = 6`, `EPS = 1e-9`, `MIN_COMPLETED_BARS = 15`, `SERIES = {"close": ("spy_close_atr", "vix_close_chg"), "upper": ("spy_low_atr", "vix_high_chg")}`
  - `daily_moves(spy, vix) -> pd.DataFrame` — index = sessions both series carry; columns `spy_close_atr, spy_low_atr, vix_close_chg, vix_high_chg` (NaN where undefined).
  - `fire_days(moves, k: float, v: float, series: str) -> list[pd.Timestamp]`
  - `episodes(fires, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]`
  - `episodes_per_year(eps, years: range) -> dict[int, int]`

The frozen definitions (index § Global Constraints, plan-time readings), implemented exactly:

- Prior close = the previous session's close **of the same series** (SPY from SPY, VIX from VIX).
- ATR14 for session *i* = `indicators.atr(spy.iloc[:i], 14).iloc[-1]`, i.e. on completed bars dated before the session, and only when at least 15 such bars exist (as `shock_scan._name_row` does live with `MIN_COMPLETED_BARS = 15`). Because `atr` is a causal EWM, `atr(spy).shift(1)` gives the same value in one pass; a test pins that equality against the per-day call.
- Close series: SPY `(Close − prev)/ATR14`, VIX `(Close/prevClose − 1)·100`. Upper bound: SPY `(Low − prev)/ATR14`, VIX `(High/prevClose − 1)·100`.
- The daily rule on one session: `-spy + EPS >= k` and `vix + EPS >= v` (as `shock._meets`); NaN never meets.
- Episode: fires whose session positions differ by fewer than `EPISODE_GAP` from the previous fire chain into one episode. An episode counts in the calendar year of its **first** fire.

- [ ] **Step 1: Write the failing tests**

`W/tests/backtest_scripts/test_shock_index_screen.py`:

```python
"""v222 V222-2: Stage 1 daily series, fire days and episodes."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import shock_index_screen as sis  # noqa: E402

from swingbot.core.market import indicators  # noqa: E402


def _bars(closes, *, highs=None, lows=None, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(closes), name="Date")
    closes = np.asarray(closes, dtype=float)
    highs = closes + 1 if highs is None else np.asarray(highs, dtype=float)
    lows = closes - 1 if lows is None else np.asarray(lows, dtype=float)
    return pd.DataFrame({"Open": closes, "High": highs, "Low": lows, "Close": closes},
                        index=idx)


def _walk(n=60, seed=7, base=100.0):
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 1.0, n))
    spread = rng.uniform(0.5, 2.0, n)
    return _bars(closes, highs=closes + spread, lows=closes - spread)


def test_frozen_constants_are_the_spec_values():
    assert sis.GRID_K == (1.0, 1.25, 1.5, 2.0)
    assert sis.GRID_VIX == (10.0, 15.0, 20.0, 25.0)
    assert (sis.EPISODE_GAP, sis.BUDGET_PER_YEAR, sis.EPS) == (5, 6, 1e-9)
    assert sis.MIN_COMPLETED_BARS == 15


def test_daily_moves_on_a_hand_built_shock_day():
    closes = [100.0] * 20 + [97.0]
    lows = [99.0] * 20 + [96.0]
    spy = _bars(closes, highs=[101.0] * 21, lows=lows)          # true range 2 -> ATR14 == 2
    vix = _bars([20.0] * 20 + [24.0], highs=[20.0] * 20 + [26.0])
    row = sis.daily_moves(spy, vix).iloc[-1]
    assert row["spy_close_atr"] == pytest.approx(-1.5)
    assert row["spy_low_atr"] == pytest.approx(-2.0)
    assert row["vix_close_chg"] == pytest.approx(20.0)
    assert row["vix_high_chg"] == pytest.approx(30.0)


def test_spy_moves_need_fifteen_completed_bars():
    moves = sis.daily_moves(_walk(30), _walk(30, seed=9, base=50.0))
    assert moves["spy_close_atr"].iloc[:15].isna().all()
    assert moves["spy_close_atr"].iloc[15:].notna().all()
    assert moves["vix_close_chg"].iloc[0] != moves["vix_close_chg"].iloc[0]   # NaN: no prior
    assert moves["vix_close_chg"].iloc[1:].notna().all()


@pytest.mark.parametrize("i", [15, 31, 59])
def test_atr_is_the_live_per_day_call_on_bars_before_the_session(i):
    spy = _walk(60)
    moves = sis.daily_moves(spy, _walk(60, seed=3, base=50.0))
    atr_live = indicators.atr(spy.iloc[:i], 14).iloc[-1]
    expected = (spy["Close"].iloc[i] - spy["Close"].iloc[i - 1]) / atr_live
    assert moves["spy_close_atr"].iloc[i] == pytest.approx(expected, rel=1e-12)
    expected_low = (spy["Low"].iloc[i] - spy["Close"].iloc[i - 1]) / atr_live
    assert moves["spy_low_atr"].iloc[i] == pytest.approx(expected_low, rel=1e-12)


def test_no_lookahead_future_bars_and_the_same_day_high_change_nothing():
    spy, vix = _walk(60), _walk(60, seed=5, base=50.0)
    base = sis.daily_moves(spy, vix)
    later = spy.copy()
    later.iloc[40:, :] = later.iloc[40:, :] * 3.0         # rewrite the future
    later.iloc[39, later.columns.get_loc("High")] += 50.0  # and day 39's own high
    moved = sis.daily_moves(later, vix)
    pd.testing.assert_frame_equal(moved.iloc[:40], base.iloc[:40])


def test_daily_moves_keeps_only_sessions_both_series_carry():
    spy = _bars([100.0] * 20)
    vix = _bars([20.0] * 20).drop(index=pd.bdate_range("2020-01-01", periods=20)[[3, 7]])
    moves = sis.daily_moves(spy, vix)
    assert len(moves) == 18
    assert list(moves.columns) == ["spy_close_atr", "spy_low_atr",
                                   "vix_close_chg", "vix_high_chg"]


def _moves(rows):
    idx = pd.bdate_range("2021-01-04", periods=len(rows), name="Date")
    return pd.DataFrame(rows, index=idx,
                        columns=["spy_close_atr", "spy_low_atr", "vix_close_chg", "vix_high_chg"])


def test_fire_days_meet_the_bar_with_the_shock_tolerance():
    moves = _moves([
        [-1.0 + 5e-10, -1.0, 10.0 - 5e-10, 10.0],   # inside EPS on both halves: fires
        [-0.99, -3.0, 50.0, 50.0],                   # close SPY half short: no close fire
        [-2.0, -2.0, 9.9, 30.0],                     # close VIX half short
        [np.nan, -2.0, 20.0, np.nan],                # NaN never meets
        [-1.5, -1.5, 12.0, 12.0],
    ])
    days = list(moves.index)
    assert sis.fire_days(moves, 1.0, 10.0, "close") == [days[0], days[4]]
    assert sis.fire_days(moves, 1.0, 10.0, "upper") == [days[0], days[1], days[2], days[4]]
    assert sis.fire_days(moves, 1.25, 15.0, "upper") == [days[1], days[2]]


def test_fire_days_refuses_an_unknown_series():
    with pytest.raises(ValueError):
        sis.fire_days(_moves([[0.0, 0.0, 0.0, 0.0]]), 1.0, 10.0, "intraday")


def test_episodes_chain_fires_fewer_than_five_sessions_apart():
    sessions = pd.bdate_range("2021-01-04", periods=25)
    s = list(sessions)
    fires = [s[9], s[0], s[1], s[4], s[14], s[20]]          # unsorted on purpose
    assert sis.episodes(fires, sessions) == [[s[0], s[1], s[4]], [s[9]], [s[14]], [s[20]]]
    assert sis.episodes([s[0], s[4], s[8], s[12]], sessions) == [[s[0], s[4], s[8], s[12]]]
    assert sis.episodes([], sessions) == []


def test_episodes_refuses_a_fire_outside_the_sessions():
    sessions = pd.bdate_range("2021-01-04", periods=5)
    with pytest.raises(ValueError):
        sis.episodes([pd.Timestamp("2022-01-03")], sessions)


def test_episodes_per_year_counts_each_year_by_first_fire_with_zeros():
    eps = [[pd.Timestamp("2020-12-30"), pd.Timestamp("2021-01-04")],
           [pd.Timestamp("2021-03-01")], [pd.Timestamp("2021-06-01")]]
    assert sis.episodes_per_year(eps, range(2019, 2023)) == {2019: 0, 2020: 1, 2021: 2, 2022: 0}
    with pytest.raises(ValueError):
        sis.episodes_per_year(eps, range(2021, 2023))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_screen.py`
Expected: FAIL (`ModuleNotFoundError: No module named 'shock_index_screen'`).

- [ ] **Step 3: Write the implementation**

`W/scripts/backtest/shock_index_screen.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 1: daily screen for the index + VIX shock entry path.

Pure daily series, fire days and episodes (this task); the grid, budget,
winner rule, Stage 2 day picker and CLI follow in V222-3. Every frozen value
is copied verbatim from the spec's "Frozen before any data is read" section.

No lookahead: a session's prior close is the previous session's close and its
ATR14 comes from completed bars dated before the session (at least 15), as
``shock_scan._name_row`` computes it live. The upper-bound series uses the
same day's SPY low and VIX high; it is a bound on the live rule, not a
tradeable signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market import indicators  # noqa: E402

GRID_K = (1.0, 1.25, 1.5, 2.0)            # index_atr_k, ATR14 below prior close
GRID_VIX = (10.0, 15.0, 20.0, 25.0)       # index_vix_chg, percent
EPISODE_GAP = 5                           # fires < 5 sessions apart = one episode
BUDGET_PER_YEAR = 6                       # max episodes in every calendar year (upper)
EPS = 1e-9                                # shock._meets tolerance
MIN_COMPLETED_BARS = 15                   # shock_scan.MIN_COMPLETED_BARS
ATR_PERIOD = 14
SERIES = {"close": ("spy_close_atr", "vix_close_chg"),
          "upper": ("spy_low_atr", "vix_high_chg")}


def _spy_moves(spy: pd.DataFrame) -> pd.DataFrame:
    prev = spy["Close"].shift(1)
    # atr(...) is a causal EWM: its value at i-1 equals atr(spy.iloc[:i]).iloc[-1].
    atr_prior = indicators.atr(spy, ATR_PERIOD).shift(1)
    enough = pd.Series(np.arange(len(spy)) >= MIN_COMPLETED_BARS, index=spy.index)
    atr_prior = atr_prior.where(enough & (atr_prior > 0))
    return pd.DataFrame({"spy_close_atr": (spy["Close"] - prev) / atr_prior,
                         "spy_low_atr": (spy["Low"] - prev) / atr_prior})


def _vix_moves(vix: pd.DataFrame) -> pd.DataFrame:
    prev = vix["Close"].shift(1)
    prev = prev.where(prev > 0)
    return pd.DataFrame({"vix_close_chg": (vix["Close"] / prev - 1.0) * 100.0,
                         "vix_high_chg": (vix["High"] / prev - 1.0) * 100.0})


def daily_moves(spy: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    """Both series' daily moves on the sessions SPY and ^VIX share."""
    moves = _spy_moves(spy).join(_vix_moves(vix), how="inner")
    moves.index.name = "Date"
    return moves


def fire_days(moves: pd.DataFrame, k: float, v: float, series: str) -> list[pd.Timestamp]:
    """Sessions on which SPY is down >= k ATR and VIX up >= v percent."""
    if series not in SERIES:
        raise ValueError(f"unknown series {series!r}; expected one of {sorted(SERIES)}")
    spy_col, vix_col = SERIES[series]
    hit = (-moves[spy_col] + EPS >= k) & (moves[vix_col] + EPS >= v)
    return list(moves.index[hit.fillna(False).to_numpy(dtype=bool)])


def episodes(fires, sessions: pd.DatetimeIndex,
             gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]:
    """Group fires whose session positions are fewer than ``gap`` apart."""
    if not len(fires):
        return []
    positions = sessions.get_indexer(pd.DatetimeIndex(fires))
    if (positions < 0).any():
        raise ValueError("a fire day is not one of the sessions")
    out: list[list[pd.Timestamp]] = []
    last = None
    for pos in sorted(positions):
        if last is not None and pos - last < gap:
            out[-1].append(sessions[pos])
        else:
            out.append([sessions[pos]])
        last = pos
    return out


def episodes_per_year(eps, years: range) -> dict[int, int]:
    """Episodes per calendar year (by first fire), every year present."""
    counts = {year: 0 for year in years}
    for episode in eps:
        year = episode[0].year
        if year not in counts:
            raise ValueError(f"episode in {year} is outside {years}")
        counts[year] += 1
    return counts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_screen.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): Stage 1 daily series, fire days and episodes without lookahead" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V222-3: Grid, budget, winner rule, Stage 2 day picker, report CLI

**Model:** opus — the winner rule and day picker decide gate 1 and the frozen Stage 2 list (statistical code feeding a gate).

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_screen.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_screen.py`

**Interfaces:**
- Consumes: from V222-2 (same module) `GRID_K`, `GRID_VIX`, `EPISODE_GAP`, `BUDGET_PER_YEAR`, `SERIES`, `daily_moves`, `fire_days`, `episodes`, `episodes_per_year`; from V222-1 `fetch_shock_index_daily.read_daily`, `common_window` (imported through `scripts/data` on `sys.path`); test helpers `_bars`, `_walk`, `_moves` already in the test module (V222-2).
- Produces (for V222-4, V222-5):
  - `CellResult` frozen dataclass: `k, v, close_fires, close_episodes, upper_fires, upper_episodes, per_year_close, per_year_upper, in_budget`
  - `screen_grid(moves) -> list[CellResult]` (16 cells, `GRID_K`-major order)
  - `neighbours(k, v) -> list[tuple[float, float]]`; `qualifying(cells) -> list[tuple[float, float]]` (most sensitive first); `pick_winner(cells) -> tuple[float, float] | None`
  - `stage2_days(moves, winner, *, alpaca_from=date(2016, 1, 4), n_shock=5, exclude=(date(2026, 11, 5),)) -> dict` (`{"shock": [iso...], "quiet": [iso...]}`)
  - `cell_key(k, v) -> str` (`"1.0,10.0"`); `build_report(moves, window) -> dict`; `render_md(report) -> str`
  - CLI `--data-dir --out-json --out-md`; JSON keys `window, cells, qualifying, winner, episodes, stage2_days` (`episodes`: `cell_key -> [[iso...]...]`, upper series; `stage2_days` is `null` on NO-LIFT).

Frozen rules implemented here (index § Global Constraints, verbatim meaning):

- **Budget:** a cell is in budget when its **upper-bound** episodes are `<= BUDGET_PER_YEAR` in **every** calendar year of the window.
- **Neighbour:** a grid cell one step away on one axis; edge cells have only the neighbours that exist.
- **Qualifying / winner:** in budget **and** every neighbour in budget; the winner is the most sensitive qualifying cell (lowest `k`, then lowest `v`); none → NO-LIFT.
- **Stage 2 shock days:** the winner's upper-bound episodes, restricted to sessions on or after `alpaca_from` (Alpaca 15-minute bars) and never in `exclude`; each episode is represented by its session with the most negative `spy_low_atr`; episodes ranked by that value, most negative first; the top `n_shock`.
- **Stage 2 quiet day per shock day (in rank order):** among eligible sessions of the previous calendar month that are not already chosen and on which no upper-bound fire of the most sensitive cell `(GRID_K[0], GRID_VIX[0])` lies within `EPISODE_GAP` sessions (`|position difference| <= 5`, the day itself included), the one nearest the shock day's day of month (ties: the earlier date). Previous month outside the eligible window **or with no such session** → the next month; neither → no quiet partner for that day (V222-5 reports it).

- [ ] **Step 1: Write the failing tests** — append to `W/tests/backtest_scripts/test_shock_index_screen.py`
  (add `import json` and `from datetime import date` to its import block):

```python
def _cells(out_of_budget=()):
    return [sis.CellResult(k, v, 0, 0, 0, 0, {}, {}, (k, v) not in out_of_budget)
            for k in sis.GRID_K for v in sis.GRID_VIX]


def test_neighbours_on_corner_edge_and_middle():
    assert sis.neighbours(1.0, 10.0) == [(1.25, 10.0), (1.0, 15.0)]
    assert sis.neighbours(2.0, 15.0) == [(1.5, 15.0), (2.0, 10.0), (2.0, 20.0)]
    assert sis.neighbours(1.25, 20.0) == [(1.0, 20.0), (1.5, 20.0), (1.25, 15.0), (1.25, 25.0)]
    with pytest.raises(ValueError):
        sis.neighbours(1.1, 10.0)


def test_winner_is_the_most_sensitive_cell_whose_neighbours_are_in_budget():
    cells = _cells(out_of_budget={(1.0, 10.0), (1.25, 10.0)})
    q = sis.qualifying(cells)
    assert q[0] == (1.0, 20.0)                     # (1.0, 15.0) has (1.0, 10.0) as a neighbour
    assert (1.0, 15.0) not in q and (1.25, 15.0) not in q and (1.5, 10.0) not in q
    assert q == sorted(q)
    assert sis.pick_winner(cells) == (1.0, 20.0)


def test_no_qualifying_cell_is_no_lift():
    everything = {(k, v) for k in sis.GRID_K for v in sis.GRID_VIX}
    assert sis.pick_winner(_cells(out_of_budget=everything)) is None
    assert sis.qualifying(_cells(out_of_budget=everything)) == []


def test_qualifying_refuses_an_incomplete_grid():
    with pytest.raises(ValueError):
        sis.qualifying(_cells()[:-1])


def _upper(start, end, fires):
    """Moves frame of calm sessions with upper-bound fires {iso: (spy_low_atr, vix_high_chg)}."""
    idx = pd.bdate_range(start, end, name="Date")
    moves = pd.DataFrame(0.0, index=idx,
                         columns=["spy_close_atr", "spy_low_atr", "vix_close_chg", "vix_high_chg"])
    for day, (spy, vix) in fires.items():
        moves.loc[pd.Timestamp(day), ["spy_low_atr", "vix_high_chg"]] = [spy, vix]
    return moves


def test_screen_grid_counts_both_series_and_judges_the_budget_on_upper():
    days = pd.bdate_range("2021-01-04", periods=70)
    moves = _upper("2021-01-04", "2022-03-31",
                   {d.isoformat(): (-1.1, 12.0) for d in days[::10]})   # 7 episodes in 2021
    cells = sis.screen_grid(moves)
    assert [(c.k, c.v) for c in cells] == [(k, v) for k in sis.GRID_K for v in sis.GRID_VIX]
    first = cells[0]
    assert (first.upper_fires, first.upper_episodes, first.close_fires) == (7, 7, 0)
    assert first.per_year_upper == {2021: 7, 2022: 0}
    assert first.per_year_close == {2021: 0, 2022: 0}
    assert first.in_budget is False
    assert all(c.in_budget and c.upper_fires == 0 for c in cells[1:])
    assert sis.pick_winner(cells) == (1.0, 20.0)


def test_six_episodes_in_a_year_is_still_inside_the_budget():
    days = pd.bdate_range("2021-01-04", periods=60)
    moves = _upper("2021-01-04", "2021-12-31",
                   {d.isoformat(): (-1.1, 12.0) for d in days[::10]})   # exactly 6
    assert sis.screen_grid(moves)[0].in_budget is True


STAGE2_FIRES = {
    "2015-12-15": (-5.0, 30.0),    # before Alpaca bars: never a Stage 2 day
    "2016-03-15": (-1.5, 20.0), "2016-03-16": (-3.0, 25.0),   # one episode, worst 03-16
    "2016-06-15": (-2.0, 20.0),
    "2016-08-15": (-1.05, 11.0),   # fires only the most sensitive cell (1.0, 10)
    "2016-09-15": (-4.0, 30.0),
    "2016-11-07": (-6.0, 40.0),    # excluded day
    "2017-02-15": (-1.3, 16.0),
}


def test_stage2_days_rank_episodes_and_match_calm_quiet_days():
    moves = _upper("2015-12-01", "2017-12-29", STAGE2_FIRES)
    days = sis.stage2_days(moves, (1.25, 15.0), n_shock=3, exclude=(date(2016, 11, 7),))
    assert days["shock"] == ["2016-09-15", "2016-03-16", "2016-06-15"]
    # Aug 8..22 sit within 5 sessions of the (1.0, 10) fire on 08-15; Aug 23 is nearest after.
    assert days["quiet"] == ["2016-08-23", "2016-02-16", "2016-05-16"]


def test_stage2_quiet_day_falls_to_the_next_month_before_the_alpaca_window():
    moves = _upper("2015-11-02", "2016-06-30", {"2016-01-20": (-2.5, 20.0)})
    assert sis.stage2_days(moves, (1.0, 10.0)) == {"shock": ["2016-01-20"],
                                                    "quiet": ["2016-02-19"]}


def test_stage2_days_default_excludes_the_replay_day():
    moves = _upper("2026-09-01", "2026-11-05", {"2026-11-05": (-3.0, 25.0)})
    assert sis.stage2_days(moves, (1.0, 10.0)) == {"shock": [], "quiet": []}


def test_render_md_says_no_lift_without_a_winner():
    cells = [dataclasses.asdict(c) for c in _cells()]
    for c in cells:
        c["per_year_upper"] = c["per_year_close"] = {2021: 0}
    report = {"window": {"start": "2021-01-04", "end": "2021-12-31", "years": 1,
                         "sessions": 252},
              "cells": cells, "qualifying": [], "winner": None, "episodes": {},
              "stage2_days": None}
    md = sis.render_md(report)
    assert "NO-LIFT" in md and md.count("| 2021 |") == 2


def test_cli_writes_the_report_json_and_markdown(tmp_path):
    _walk(300, base=300.0).to_csv(tmp_path / "SPY.csv")
    _walk(300, seed=11, base=50.0).to_csv(tmp_path / "VIX.csv")
    out_json, out_md = tmp_path / "stage1.json", tmp_path / "stage1.md"
    assert sis.main(["--data-dir", str(tmp_path), "--out-json", str(out_json),
                     "--out-md", str(out_md)]) == 0
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert set(report) == {"window", "cells", "qualifying", "winner", "episodes",
                           "stage2_days"}
    assert report["window"]["sessions"] == 300
    assert len(report["cells"]) == 16 and len(report["episodes"]) == 16
    assert sis.cell_key(1.0, 10.0) == "1.0,10.0" and "1.0,10.0" in report["episodes"]
    md = out_md.read_text(encoding="utf-8")
    assert "## Cells" in md and md.count("| 2020 |") == 2
```

Also add `import dataclasses` to the test module's import block.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_screen.py`
Expected: the V222-2 tests pass; the new ones FAIL (`AttributeError: module 'shock_index_screen' has no attribute 'CellResult'`).

- [ ] **Step 3: Write the implementation**

In `W/scripts/backtest/shock_index_screen.py`, replace the import block (from `import sys` to the `indicators` import) with:

```python
import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "scripts" / "data"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fetch_shock_index_daily import common_window, read_daily  # noqa: E402
from swingbot.core.market import indicators  # noqa: E402
```

Add below the constants:

```python
ALPACA_FROM = date(2016, 1, 4)            # first Alpaca 15-minute bars
N_SHOCK = 5
EXCLUDE = (date(2026, 11, 5),)            # the replay day is never a Stage 2 day
```

Append at the end of the module:

```python
@dataclass(frozen=True)
class CellResult:
    k: float
    v: float
    close_fires: int
    close_episodes: int
    upper_fires: int
    upper_episodes: int
    per_year_close: dict
    per_year_upper: dict
    in_budget: bool


def _years(moves: pd.DataFrame) -> range:
    return range(moves.index[0].year, moves.index[-1].year + 1)


def _iso(day: pd.Timestamp) -> str:
    return day.date().isoformat()


def cell_key(k: float, v: float) -> str:
    return f"{k},{v}"


def cell_episodes(moves: pd.DataFrame, k: float, v: float, series: str):
    return episodes(fire_days(moves, k, v, series), moves.index)


def screen_cell(moves: pd.DataFrame, k: float, v: float) -> CellResult:
    years = _years(moves)
    fires = {s: fire_days(moves, k, v, s) for s in SERIES}
    eps = {s: episodes(fires[s], moves.index) for s in SERIES}
    per_upper = episodes_per_year(eps["upper"], years)
    return CellResult(k, v, len(fires["close"]), len(eps["close"]),
                      len(fires["upper"]), len(eps["upper"]),
                      episodes_per_year(eps["close"], years), per_upper,
                      max(per_upper.values()) <= BUDGET_PER_YEAR)


def screen_grid(moves: pd.DataFrame) -> list[CellResult]:
    return [screen_cell(moves, k, v) for k in GRID_K for v in GRID_VIX]


def neighbours(k: float, v: float) -> list[tuple[float, float]]:
    """Cells one grid step away on one axis (edge cells have fewer)."""
    if k not in GRID_K or v not in GRID_VIX:
        raise ValueError(f"({k}, {v}) is not a grid cell")
    i, j = GRID_K.index(k), GRID_VIX.index(v)
    out = [(GRID_K[i + d], v) for d in (-1, 1) if 0 <= i + d < len(GRID_K)]
    out += [(k, GRID_VIX[j + d]) for d in (-1, 1) if 0 <= j + d < len(GRID_VIX)]
    return out


def qualifying(cells: list[CellResult]) -> list[tuple[float, float]]:
    """In budget with every neighbour in budget; most sensitive first."""
    by_key = {(c.k, c.v): c for c in cells}
    if set(by_key) != {(k, v) for k in GRID_K for v in GRID_VIX}:
        raise ValueError("the winner rule needs all 16 grid cells")
    return sorted(key for key, cell in by_key.items()
                  if cell.in_budget and all(by_key[n].in_budget for n in neighbours(*key)))


def pick_winner(cells: list[CellResult]) -> tuple[float, float] | None:
    q = qualifying(cells)
    return q[0] if q else None


def _eligible(sessions: pd.DatetimeIndex, alpaca_from: date, exclude) -> pd.DatetimeIndex:
    skip = pd.DatetimeIndex([pd.Timestamp(d) for d in exclude])
    return sessions[(sessions >= pd.Timestamp(alpaca_from)) & ~sessions.isin(skip)]


def _shock_days(moves, winner, eligible, n_shock) -> list[pd.Timestamp]:
    ranked = []
    for episode in cell_episodes(moves, *winner, "upper"):
        days = [d for d in episode if d in eligible]
        if days:
            worst = min(days, key=lambda d: (moves.at[d, "spy_low_atr"], d))
            ranked.append((moves.at[worst, "spy_low_atr"], worst))
    return [day for _, day in sorted(ranked)[:n_shock]]


def _calm_check(moves: pd.DataFrame):
    fires = moves.index.get_indexer(
        pd.DatetimeIndex(fire_days(moves, GRID_K[0], GRID_VIX[0], "upper")))

    def calm(day: pd.Timestamp) -> bool:
        pos = moves.index.get_loc(day)
        return all(abs(pos - f) > EPISODE_GAP for f in fires)
    return calm


def _shift_month(day: pd.Timestamp, offset: int) -> tuple[int, int]:
    month = day.year * 12 + (day.month - 1) + offset
    return month // 12, month % 12 + 1


def _quiet_day(day, eligible, calm, taken) -> pd.Timestamp | None:
    for offset in (-1, 1):
        year, month = _shift_month(day, offset)
        pool = [s for s in eligible if s.year == year and s.month == month
                and s not in taken and calm(s)]
        if pool:
            return min(pool, key=lambda s: (abs(s.day - day.day), s))
    return None


def stage2_days(moves: pd.DataFrame, winner: tuple[float, float], *,
                alpaca_from: date = ALPACA_FROM, n_shock: int = N_SHOCK,
                exclude=EXCLUDE) -> dict:
    """The frozen Stage 2 list: shock days from the winner, matched quiet days."""
    eligible = _eligible(moves.index, alpaca_from, exclude)
    shock = _shock_days(moves, winner, eligible, n_shock)
    calm, taken, quiet = _calm_check(moves), set(shock), []
    for day in shock:
        partner = _quiet_day(day, eligible, calm, taken)
        if partner is not None:
            quiet.append(partner)
            taken.add(partner)
    return {"shock": [_iso(d) for d in shock], "quiet": [_iso(d) for d in quiet]}


def build_report(moves: pd.DataFrame, window: dict) -> dict:
    cells = screen_grid(moves)
    winner = pick_winner(cells)
    return {
        "window": window,
        "cells": [asdict(c) for c in cells],
        "qualifying": [list(key) for key in qualifying(cells)],
        "winner": list(winner) if winner else None,
        "episodes": {cell_key(c.k, c.v): [[_iso(d) for d in ep]
                                          for ep in cell_episodes(moves, c.k, c.v, "upper")]
                     for c in cells},
        "stage2_days": stage2_days(moves, winner) if winner else None,
    }


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _cell_rows(report: dict) -> list[str]:
    q = {tuple(key) for key in report["qualifying"]}
    rows = ["| k (ATR) | VIX % | close fires | close episodes | upper fires | upper episodes "
            "| max upper episodes/yr | in budget | qualifies |",
            "|---|---|---|---|---|---|---|---|---|"]
    for c in report["cells"]:
        rows.append(f"| {c['k']} | {c['v']} | {c['close_fires']} | {c['close_episodes']} "
                    f"| {c['upper_fires']} | {c['upper_episodes']} "
                    f"| {max(c['per_year_upper'].values())} | {_yes(c['in_budget'])} "
                    f"| {_yes((c['k'], c['v']) in q)} |")
    return rows


def _year_rows(report: dict, key: str) -> list[str]:
    cells = report["cells"]
    rows = ["| year | " + " | ".join(f"{c['k']}/{c['v']}" for c in cells) + " |",
            "|---|" + "---|" * len(cells)]
    for year in cells[0][key]:
        rows.append(f"| {year} | " + " | ".join(str(c[key][year]) for c in cells) + " |")
    return rows


def _winner_lines(report: dict) -> list[str]:
    if not report["winner"]:
        return ["NO-LIFT: no cell is inside the budget with every neighbour inside it."]
    k, v = report["winner"]
    days = report["stage2_days"]
    return [f"Winner: index_atr_k = {k}, index_vix_chg = {v}.",
            f"Stage 2 shock days: {', '.join(days['shock']) or 'none'}.",
            f"Stage 2 quiet days: {', '.join(days['quiet']) or 'none'}."]


def render_md(report: dict) -> str:
    w = report["window"]
    lines = ["# v222 Stage 1 daily screen", "",
             f"Window {w['start']} to {w['end']}: {w['years']} calendar years, "
             f"{w['sessions']} sessions.", "", "## Cells", "", *_cell_rows(report), "",
             "## Episodes per year, upper-bound series (the budget)", "",
             *_year_rows(report, "per_year_upper"), "",
             "## Episodes per year, close series (a lower bound)", "",
             *_year_rows(report, "per_year_close"), "", "## Winner", "",
             *_winner_lines(report)]
    return "\n".join(lines) + "\n"


def _parse(argv):
    p = argparse.ArgumentParser(description="v222 Stage 1 daily screen")
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--out-json", type=Path, required=True)
    p.add_argument("--out-md", type=Path, required=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    spy = read_daily(args.data_dir / "SPY.csv")
    vix = read_daily(args.data_dir / "VIX.csv")
    window = common_window(spy, vix)
    moves = daily_moves(spy, vix).loc[:window["end"]]
    report = build_report(moves, window)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.out_md.write_text(render_md(report), encoding="utf-8")
    print("winner:", report["winner"] or "NO-LIFT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`json.dumps` turns the `per_year_*` int keys into strings; `render_md` runs on the in-memory report, so its keys stay ints there.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_screen.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_screen.py tests/backtest_scripts/test_shock_index_screen.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): Stage 1 grid, budget, winner rule and frozen Stage 2 day picker" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V222-4: Forward long-book: prod dump and descriptive forward table

**Model:** sonnet — two small scripts with stubbed inputs; descriptive output that decides no gate.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/reports/shock_longbook_dump.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_forward.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_shock_longbook_dump.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_forward.py`

**Interfaces:**
- Consumes: `swingbot.core.analytics.metrics.r_multiple(trade) -> float | None`, `swingbot.core.analytics.scope.CLOSED_STATUSES`, `swingbot.core.tracking.origin.is_regular(record)`, `TradeLog().get_trades(status=None, limit=None, ledger="main")` (all exist on main and production); `swingbot.core.backtesting.instrument.stats.week_cluster_bootstrap(baseline, component, statistic)` (items need `.entry_date`); from V222-3 `shock_index_screen.cell_key` and `read_daily` (re-exported there), and the screen JSON keys `window`, `winner`, `episodes`.
- Produces (for V222-5): `shock_longbook_dump.longbook_record(trade: dict) -> dict | None` (`{opened_at, r}`), `build_dump(trades) -> dict` (`{"trades": [...]}`); `shock_index_forward.HORIZONS = (1, 3, 5)`, `forward_longbook(episodes: list[list[str]], trades: list[dict], sessions: list[str], horizons=HORIZONS) -> list[dict]` (per horizon: `horizon, n_trades, n_episodes, exp_r, total_r, ci_low, ci_high`); CLI `--screen-json --longbook --data-dir --out-md [--cell K,V]`.

Population (index plan-time reading): closed `bullish` main-ledger **regular** trades whose open session (the America/New_York date of `opened_at`) falls within the first 1, 3, 5 sessions of an episode, session 1 being the episode's first fire day. Episodes are at least 5 sessions apart, so a trade lands in at most one window. **Descriptive only:** the table decides no cell and no gate; N per episode is reported beside N per trade, Total R beside ExpR, and a 95 % `week_cluster_bootstrap` interval of ExpR. Local `data/journal.json` is fixture data: the real book comes from production, read-only.

- [ ] **Step 1: Write the failing tests**

`W/tests/scripts/test_shock_longbook_dump.py`:

```python
"""v222 V222-4: the read-only production long-book dump."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import shock_longbook_dump as dump  # noqa: E402

from swingbot.core.analytics import metrics  # noqa: E402


@pytest.fixture(autouse=True)
def _r(monkeypatch):
    monkeypatch.setattr(metrics, "r_multiple", lambda t: t.get("_r"))


def _trade(**over):
    base = {"direction": "bullish", "status": "win", "ledger": "main", "origin": None,
            "opened_at": "2026-03-10T14:45:00+00:00", "_r": 1.5}
    return {**base, **over}


def test_a_closed_regular_main_long_is_recorded():
    assert dump.longbook_record(_trade()) == {"opened_at": "2026-03-10T14:45:00+00:00",
                                              "r": 1.5}
    assert dump.longbook_record(_trade(ledger=None, status="loss", _r=-1)) == {
        "opened_at": "2026-03-10T14:45:00+00:00", "r": -1.0}


@pytest.mark.parametrize("over", [
    {"direction": "bearish"}, {"status": "open"}, {"status": "pending"},
    {"ledger": "weak"}, {"origin": "replay"}, {"_r": None}, {"opened_at": None},
])
def test_everything_else_is_left_out(over):
    assert dump.longbook_record(_trade(**over)) is None


def test_build_dump_keeps_only_records():
    out = dump.build_dump([_trade(), _trade(direction="bearish"), _trade(_r=-0.5)])
    assert [t["r"] for t in out["trades"]] == [1.5, -0.5]
```

`W/tests/backtest_scripts/test_shock_index_forward.py`:

```python
"""v222 V222-4: descriptive forward long-book after Stage 1 episodes."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import shock_index_forward as fwd  # noqa: E402

S = [d.date().isoformat() for d in pd.bdate_range("2021-01-04", periods=10)]
EPISODES = [[S[0], S[1]], [S[6]]]
TRADES = [{"opened_at": f"{S[0]}T14:45:00+00:00", "r": 1.0},
          {"opened_at": f"{S[2]}T15:00:00+00:00", "r": -1.0},
          {"opened_at": f"{S[4]}T15:00:00+00:00", "r": 2.0},
          {"opened_at": f"{S[6]}T15:00:00+00:00", "r": 0.5},
          {"opened_at": f"{S[9]}T15:00:00+00:00", "r": 3.0},
          {"opened_at": f"{S[5]}T15:00:00+00:00", "r": -9.0}]   # outside every window


def test_horizons_are_one_three_five_sessions():
    assert fwd.HORIZONS == (1, 3, 5)


def test_forward_longbook_counts_trades_and_episodes_per_horizon():
    rows = {r["horizon"]: r for r in fwd.forward_longbook(EPISODES, TRADES, S)}
    assert (rows[1]["n_trades"], rows[1]["n_episodes"]) == (2, 2)
    assert rows[1]["total_r"] == pytest.approx(1.5) and rows[1]["exp_r"] == pytest.approx(0.75)
    assert (rows[3]["n_trades"], rows[3]["total_r"]) == (3, pytest.approx(0.5))
    assert (rows[5]["n_trades"], rows[5]["total_r"]) == (5, pytest.approx(5.5))
    assert rows[5]["exp_r"] == pytest.approx(1.1)
    for row in rows.values():
        assert row["ci_low"] <= row["exp_r"] <= row["ci_high"]


def test_the_open_session_is_the_new_york_date():
    late = [{"opened_at": f"{S[1]}T02:00:00+00:00", "r": 1.0}]   # 21:00 ET on S[0]
    row = fwd.forward_longbook([[S[0]]], late, S, horizons=(1,))[0]
    assert row["n_trades"] == 1


def test_no_trades_gives_an_empty_row():
    row = fwd.forward_longbook(EPISODES, [], S, horizons=(3,))[0]
    assert row == {"horizon": 3, "n_trades": 0, "n_episodes": 0, "exp_r": None,
                   "total_r": 0.0, "ci_low": None, "ci_high": None}


def test_an_episode_off_the_sessions_is_refused():
    with pytest.raises(ValueError):
        fwd.forward_longbook([["2030-01-02"]], TRADES, S)


def _write_inputs(tmp_path, winner):
    idx = pd.DatetimeIndex(pd.to_datetime(S), name="Date")
    pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0},
                 index=idx).to_csv(tmp_path / "SPY.csv")
    screen = {"window": {"start": S[0], "end": S[-1], "years": 1, "sessions": 10},
              "winner": winner, "episodes": {"1.0,10.0": EPISODES}}
    (tmp_path / "stage1.json").write_text(json.dumps(screen), encoding="utf-8")
    (tmp_path / "longbook.json").write_text(json.dumps({"trades": TRADES}), encoding="utf-8")


def _run(tmp_path, *extra):
    out = tmp_path / "forward.md"
    assert fwd.main(["--screen-json", str(tmp_path / "stage1.json"),
                     "--longbook", str(tmp_path / "longbook.json"),
                     "--data-dir", str(tmp_path), "--out-md", str(out), *extra]) == 0
    return out.read_text(encoding="utf-8")


def test_cli_writes_the_table_for_the_winner(tmp_path):
    _write_inputs(tmp_path, [1.0, 10.0])
    md = _run(tmp_path)
    assert "Descriptive only" in md and "| 5 | 5 | 2 |" in md


def test_cli_without_a_winner_says_no_lift_unless_a_cell_is_named(tmp_path):
    _write_inputs(tmp_path, None)
    assert "NO-LIFT" in _run(tmp_path)
    assert "| 1 | 2 | 2 |" in _run(tmp_path, "--cell", "1.0,10.0")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_shock_longbook_dump.py`
then `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_forward.py`
Expected: both FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

`W/scripts/reports/shock_longbook_dump.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 1: the closed regular long main-ledger trades as ONE JSON line. Read-only.

Standalone on purpose (production does not carry the v209 branch): it imports
only modules production already runs and is piped over ssh::

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/shock_longbook_dump.py > data/v222/longbook.json

It writes nothing on the box and leaves tickers out (the table needs none).
"""
from __future__ import annotations

import json


def longbook_record(trade: dict) -> dict | None:
    """``{opened_at, r}`` for a closed bullish regular main-ledger trade, else None."""
    from swingbot.core.analytics import metrics
    from swingbot.core.analytics.scope import CLOSED_STATUSES
    from swingbot.core.tracking.origin import is_regular
    if trade.get("direction") != "bullish" or trade.get("status") not in CLOSED_STATUSES:
        return None
    if (trade.get("ledger") or "main") != "main" or not is_regular(trade):
        return None
    r = metrics.r_multiple(trade)
    if r is None or not trade.get("opened_at"):
        return None
    return {"opened_at": str(trade["opened_at"]), "r": float(r)}


def build_dump(trades: list[dict]) -> dict:
    return {"trades": [rec for t in trades if (rec := longbook_record(t)) is not None]}


def main() -> None:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status=None, limit=None, ledger="main")
    print(json.dumps(build_dump(trades)))


if __name__ == "__main__":
    main()
```

`W/scripts/backtest/shock_index_forward.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 1: descriptive forward long-book after the screen's episodes.

Descriptive only -- decides no cell and no gate. Trades inside one episode are
not independent, so N per episode sits beside N per trade, Total R beside
ExpR, and the interval is a week-cluster bootstrap of ExpR.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shock_index_screen import cell_key, read_daily  # noqa: E402  (also puts ROOT on sys.path)
from swingbot.core.backtesting.instrument.stats import week_cluster_bootstrap  # noqa: E402

HORIZONS = (1, 3, 5)
NY = "America/New_York"


class _Row(NamedTuple):
    entry_date: str
    r: float


def _session_date(opened_at) -> str:
    ts = pd.Timestamp(opened_at)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(NY)
    return ts.date().isoformat()


def _windows(episodes, sessions: list[str], horizon: int) -> list[set[str]]:
    position = {day: i for i, day in enumerate(sessions)}
    out = []
    for episode in episodes:
        if episode[0] not in position:
            raise ValueError(f"episode start {episode[0]} is not a session")
        start = position[episode[0]]
        out.append(set(sessions[start:start + horizon]))
    return out


def _rows_in(trades, windows) -> tuple[list[_Row], set[int]]:
    rows, hit = [], set()
    for trade in trades:
        day = _session_date(trade["opened_at"])
        for n, window in enumerate(windows):
            if day in window:
                rows.append(_Row(day, float(trade["r"])))
                hit.add(n)
                break
    return rows, hit


def _mean_r(draw, _component):
    return float(np.mean([row.r for row in draw])) if draw else None


def _summary(horizon: int, rows: list[_Row], n_episodes: int) -> dict:
    if not rows:
        return {"horizon": horizon, "n_trades": 0, "n_episodes": 0, "exp_r": None,
                "total_r": 0.0, "ci_low": None, "ci_high": None}
    rs = [row.r for row in rows]
    draws = week_cluster_bootstrap(rows, (), _mean_r)
    low, high = ((float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
                 if len(draws) else (None, None))
    return {"horizon": horizon, "n_trades": len(rows), "n_episodes": n_episodes,
            "exp_r": float(np.mean(rs)), "total_r": float(sum(rs)),
            "ci_low": low, "ci_high": high}


def forward_longbook(episodes, trades, sessions, horizons=HORIZONS) -> list[dict]:
    out = []
    for horizon in horizons:
        rows, hit = _rows_in(trades, _windows(episodes, sessions, horizon))
        out.append(_summary(horizon, rows, len(hit)))
    return out


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def render_md(cell, rows: list[dict]) -> str:
    lines = ["# v222 Stage 1 forward long-book (descriptive)", "",
             "Descriptive only: decides no cell and no gate. A shock can be followed "
             "by a bounce; no direction is claimed.", ""]
    if cell is None:
        return "\n".join(lines + ["NO-LIFT: no winner, forward table not computed."]) + "\n"
    lines += [f"Cell: index_atr_k = {cell[0]}, index_vix_chg = {cell[1]} (upper-bound episodes).",
              "", "| sessions | trades | episodes with a trade | ExpR | Total R "
              "| 95% week-cluster CI |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['horizon']} | {r['n_trades']} | {r['n_episodes']} "
                     f"| {_fmt(r['exp_r'])} | {r['total_r']:+.3f} "
                     f"| {_fmt(r['ci_low'])} .. {_fmt(r['ci_high'])} |")
    return "\n".join(lines) + "\n"


def _parse(argv):
    p = argparse.ArgumentParser(description="v222 Stage 1 forward long-book")
    p.add_argument("--screen-json", type=Path, required=True)
    p.add_argument("--longbook", type=Path, required=True)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--out-md", type=Path, required=True)
    p.add_argument("--cell", help="K,V instead of the winner")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse(argv)
    screen = json.loads(args.screen_json.read_text(encoding="utf-8"))
    cell = ([float(x) for x in args.cell.split(",")] if args.cell else screen["winner"])
    if cell is None:
        args.out_md.write_text(render_md(None, []), encoding="utf-8")
        return 0
    window = screen["window"]
    sessions = [d.date().isoformat() for d in read_daily(args.data_dir / "SPY.csv").index]
    sessions = [d for d in sessions if window["start"] <= d <= window["end"]]
    trades = json.loads(args.longbook.read_text(encoding="utf-8"))["trades"]
    rows = forward_longbook(screen["episodes"][cell_key(*cell)], trades, sessions)
    args.out_md.write_text(render_md(cell, rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run the two commands of Step 2 again. Expected: PASS, 0 failed each.

- [ ] **Step 5: Commit (v209 branch), one commit per script**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/reports/shock_longbook_dump.py tests/scripts/test_shock_longbook_dump.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): read-only production long-book dump for the forward table" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_forward.py tests/backtest_scripts/test_shock_index_forward.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): descriptive forward long-book after Stage 1 episodes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V222-5: Run Stage 1, write Results, freeze the Stage 2 day list, gate 1

**Model:** sonnet — runs finished scripts and transcribes their output; no new code.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (main tree, `## Results`: new `### Stage 1 — screen` and `### Stage 2 — frozen day list`)

**Interfaces:**
- Consumes: V222-1 data in `M/data/v222/`; V222-3 CLI and JSON keys; V222-4 dump and forward CLI.
- Produces (for V222-6..V222-8): `M/data/v222/stage1.json`, `stage1.md`, `longbook.json`, `forward.md`, and `M/data/v222/stage2_days.json` = `{"shock": [iso...], "quiet": [iso...], "cells": [[k, v]...]}` (`cells` = the qualifying cells, most sensitive first; Stage 2 judges each).

No test code: every script was tested in V222-1..V222-4. Run from any directory; all paths absolute.

- [ ] **Step 1: Run the screen**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_screen.py --data-dir E:/Documents/Private/Projects/Discord-Bot/data/v222 --out-json E:/Documents/Private/Projects/Discord-Bot/data/v222/stage1.json --out-md E:/Documents/Private/Projects/Discord-Bot/data/v222/stage1.md
```

Expected: exit 0, prints `winner: [k, v]` or `winner: NO-LIFT`. Check the `window` in `stage1.json` equals the Results window table from V222-1 (else stop: the data moved).

- [ ] **Step 2: Production long-book dump (read-only, standing permission) and the forward table**

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/reports/shock_longbook_dump.py > E:/Documents/Private/Projects/Discord-Bot/data/v222/longbook.json
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_forward.py --screen-json E:/Documents/Private/Projects/Discord-Bot/data/v222/stage1.json --longbook E:/Documents/Private/Projects/Discord-Bot/data/v222/longbook.json --data-dir E:/Documents/Private/Projects/Discord-Bot/data/v222 --out-md E:/Documents/Private/Projects/Discord-Bot/data/v222/forward.md
```

Expected: `longbook.json` is one JSON line `{"trades": [...]}`; `forward.md` holds the 1/3/5-session table (or the NO-LIFT line).

- [ ] **Step 3: Freeze the Stage 2 day list (before any replay is built)**

```bash
python -c "import json,pathlib; d=pathlib.Path('E:/Documents/Private/Projects/Discord-Bot/data/v222'); s=json.loads((d/'stage1.json').read_text()); days=s['stage2_days'] or {'shock': [], 'quiet': []}; (d/'stage2_days.json').write_text(json.dumps({**days, 'cells': s['qualifying']}, indent=2)); print(len(days['shock']), len(days['quiet']))"
```

- [ ] **Step 4: Write the Results (main tree spec), under the V222-1 window table**

Add `### Stage 1 — screen` with: the cell table and both per-year tables copied from `stage1.md` unchanged; the qualifying cells; the winner, or **NO-LIFT** with the reason; the forward table from `forward.md` with its "descriptive only" line; one line naming the population (closed bullish regular main-ledger trades, production, dump date). Add `### Stage 2 — frozen day list` with the shock and quiet days from `stage2_days.json`, each shock day's upper-bound `spy_low_atr` and `vix_high_chg` (from `stage1.json` episodes plus `daily_moves`), a line for every shock day without a quiet partner, the cells Stage 2 judges, and: "Frozen before any replay is built; 2026-11-05 excluded."

- [ ] **Step 5: Commit on `main` (controller)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v222): Stage 1 results and the frozen Stage 2 day list" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Gate 1 (partner, `AskUserQuestion`, recommended option first)**

- Winner and at least 3 shock days: ask "Stage 1 results are in the spec; proceed to Stage 2 with this day list?" (recommended: proceed).
- NO-LIFT: report it; recommended option "close v222 as NO-LIFT (plan to `no-lift/`, nothing ships; v209's release is decided separately)".
- Winner but fewer than 3 shock days: stop and ask; never widen the window, the grid or `alpaca_from`.

