# v228 — Intraday MFE/MAE for the journal: Part 1 (core)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-3" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../specs/2026-11-14-v228-intraday-excursion-design.md)
**Index:** [2026-11-14-v228-intraday-excursion_0-index.md](2026-11-14-v228-intraday-excursion_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the Task ledger (the cross-task contract) live there; every task below implicitly includes the Global Constraints.

Tasks in this part: V228-1 (time-basis pin), V228-2 and V228-2b (`compute_excursion`, then the `compute_mfe_mae` wrapper), V228-3 (conditional patch), V228-4 (frames loader and journal). V228-5 (upgrade pass) lives in part 5 (`_5-upgrade.md`).

Shared notes for this part:

- Run tests with the narrow runner only: `python scripts/dev/testrun.py file <test file>`. No task here runs the full suite.
- V228-3, V228-4 and V228-5 reach the local Postgres: run `/replicate-prod-db` first (shared `swing-db` container, port 56789, `.env` credentials never printed). `tests/conftest.py:_store_database` *skips* DB tests when the database is down — a skip is not a pass; re-run after starting it.
- Iterate complexity with `python -m radon cc -s -n C <files>`; every changed function ends below 15.
- Do not commit on `main` from a plan session; the commit steps below are for the implementing worktree.

# Phase 1 — Excursion core

### Task V228-1: Pin the archive time basis on real Yahoo and Alpaca archive rows

**Model:** sonnet — fixture capture from the VM plus a pure pandas test; no design judgement, but the read-only production step must be exact.

**Files:**
- Create: `tests/fixtures/v228/archive/5min/AAPL.csv`, `tests/fixtures/v228/archive/5min/GC_F.csv`, `tests/fixtures/v228/archive/15min/AAPL.csv`, `tests/fixtures/v228/archive/15min/GC_F.csv`, `tests/fixtures/v228/archive/hourly/AAPL.csv`, `tests/fixtures/v228/archive/hourly/GC_F.csv` (rows copied read-only from the VM, sessions 2026-10-30 and 2026-11-03)
- Create: `tests/marketdata/test_archive_time_basis.py` (suite `market-data`, which already covers `tests/marketdata/`)

**Interfaces:**
- Consumes: `swingbot.core.marketdata.data_store.load_normalized(ticker, interval, base_dir=DATA_DIR) -> pd.DataFrame | None` (exists, `data_store.py:310`); `safe_symbol("GC=F") == "GC_F"` (`data_store.py:112`).
- Produces: the verdict `ARCHIVE_TIME_BASIS_OK` in this task's commit message. It tells V228-2 that `load_normalized` returns **naive-UTC bar starts** for both providers (AAPL is Alpaca-eligible, `GC=F` is Yahoo-only), so `compute_excursion` only has to convert the *trade's* aware times to naive UTC (and, defensively, an aware frame index to naive UTC). If a test in Step 3 fails for a provider, do **not** loosen it: follow Step 4 — V228-2's contract is the same either way.

**Why these rows:** sessions 2026-10-30 (US daylight time, regular session 13:30–20:00 UTC) and 2026-11-03 (standard time, 14:30–21:00 UTC) straddle the 2026-11-01 DST change. If the archive were stamped in New York wall-clock or with bar *ends*, the first AAPL bar would not sit at 13:30 and then 14:30 UTC. Checked on production 2026-11-14 (read-only, plan writer): every file's header is `Datetime,Close,High,Low,Open,Volume` (hourly AAPL has an empty first header cell, which `index_col=0` reads the same), every row carries `+00:00`, and the two sessions hold 156 / 52 / 14 AAPL rows and 528 / 176 / 44 GC_F rows in 5min / 15min / hourly.

- [ ] **Step 1: Copy the fixture rows from the VM (read-only)**

The `ssh-hetzner.sh` wrapper expands `$` on this machine, so each remote script is built locally (the loop variables expand here, which is what we want) and piped on stdin. Run from the repo root in Git Bash:

```bash
mkdir -p tests/fixtures/v228/archive/5min tests/fixtures/v228/archive/15min tests/fixtures/v228/archive/hourly
for tf in 5min 15min hourly; do
  for t in AAPL GC_F; do
    printf '%s\n' "cd /opt/swing-bot/market_data" \
      "head -1 $tf/$t.csv" \
      "grep -e '^2026-10-30' -e '^2026-11-03' $tf/$t.csv" \
      | bash scripts/ops/ssh-hetzner.sh "bash -s" 2>/dev/null \
      > "tests/fixtures/v228/archive/$tf/$t.csv"
  done
done
wc -l tests/fixtures/v228/archive/*/*.csv
```

Expected `wc -l` (header + rows): 5min AAPL 157, GC_F 529; 15min AAPL 53, GC_F 177; hourly AAPL 15, GC_F 45. A file of 0 or 1 lines means the SSH call failed — re-run that pair, never hand-edit rows. Check one file: line 1 is the header, line 2 starts `2026-10-30 ` and is a whole row.

- [ ] **Step 2: Write the test**

Create `tests/marketdata/test_archive_time_basis.py`:

```python
"""v228 V228-1: pin the archive time basis on real production rows.

compute_excursion (V228-2) compares journal times (aware UTC ISO strings)
with archive bar indexes. These tests prove what load_normalized hands it:
a naive index in UTC, each bar stamped with its START, for an
Alpaca-eligible ticker (AAPL) and a Yahoo-only one (GC=F), across the
2026-11-01 DST change. They also pin the two traps in
data_store._normalize_cached: mixed offsets -> None, and a single non-UTC
offset -> local wall-clock (which is why every archive must stay +00:00)."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.marketdata.data_store import load_normalized

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "v228" / "archive"
FRAMES = ("5min", "15min", "hourly")
TICKERS = ("AAPL", "GC=F")
STEM = {"AAPL": "AAPL", "GC=F": "GC_F"}


def _raw_stamps(frame: str, ticker: str) -> list[str]:
    path = FIXTURES / frame / f"{STEM[ticker]}.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) > 1, f"{path} holds no data rows -- re-run V228-1 Step 1"
    return [row[0] for row in rows[1:]]


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("ticker", TICKERS)
def test_every_archived_stamp_carries_a_utc_offset(frame, ticker):
    stamps = _raw_stamps(frame, ticker)
    offenders = [s for s in stamps if not s.endswith("+00:00")]
    assert offenders == []


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("ticker", TICKERS)
def test_load_normalized_returns_the_file_stamps_as_naive_utc(frame, ticker):
    df = load_normalized(ticker, frame, base_dir=str(FIXTURES))
    assert df is not None
    assert df.index.tz is None
    expected = pd.DatetimeIndex(pd.to_datetime(_raw_stamps(frame, ticker), utc=True)).tz_localize(None)
    expected = expected[~expected.duplicated(keep="last")].sort_values()
    assert list(df.index) == list(expected)
    assert df.index.is_monotonic_increasing


def _session(df: pd.DataFrame, day: str) -> pd.DatetimeIndex:
    return df.index[df.index.normalize() == pd.Timestamp(day)]


@pytest.mark.parametrize("frame,last_start", [
    ("5min", ("19:55", "20:55")),
    ("15min", ("19:45", "20:45")),
    ("hourly", ("19:30", "20:30")),
])
def test_aapl_bars_are_stamped_with_their_start_across_the_dst_change(frame, last_start):
    df = load_normalized("AAPL", frame, base_dir=str(FIXTURES))
    before, after = _session(df, "2026-10-30"), _session(df, "2026-11-03")
    # 09:30 New York is 13:30 UTC in daylight time and 14:30 UTC in standard time.
    assert before[0].strftime("%H:%M") == "13:30"
    assert after[0].strftime("%H:%M") == "14:30"
    # The last bar STARTS one bar before the 16:00 New York close.
    assert (before[-1].strftime("%H:%M"), after[-1].strftime("%H:%M")) == last_start


def test_aapl_session_row_counts_match_the_production_check():
    counts = {f: len(load_normalized("AAPL", f, base_dir=str(FIXTURES))) for f in FRAMES}
    assert counts == {"5min": 156, "15min": 52, "hourly": 14}


def _rewrite_offsets(tmp_path: Path, offset_for) -> Path:
    """Copy the AAPL 5min fixture with every stamp moved to a local offset."""
    src = FIXTURES / "5min" / "AAPL.csv"
    with src.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    out_rows = [rows[0]]
    for row in rows[1:]:
        ts = pd.Timestamp(row[0])
        local = ts.tz_convert(offset_for(ts))
        out_rows.append([local.isoformat(sep=" "), *row[1:]])
    target = tmp_path / "5min"
    target.mkdir(parents=True)
    with (target / "AAPL.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(out_rows)
    return tmp_path


def test_mixed_offsets_make_load_normalized_return_none(tmp_path):
    dst_end = pd.Timestamp("2026-11-01", tz="UTC")
    base = _rewrite_offsets(tmp_path, lambda ts: "-04:00" if ts < dst_end else "-05:00")
    assert load_normalized("AAPL", "5min", base_dir=str(base)) is None


def test_a_single_non_utc_offset_is_read_as_local_wall_clock(tmp_path):
    """The trap the +00:00 assertion guards: tz_localize(None) keeps the
    wall-clock, so a New York-offset file would read 09:30, not 14:30."""
    base = _rewrite_offsets(tmp_path, lambda ts: "-05:00")
    df = load_normalized("AAPL", "5min", base_dir=str(base))
    assert df is not None
    assert _session(df, "2026-11-03")[0].strftime("%H:%M") == "09:30"


def test_the_fixture_tree_is_not_written_by_the_loader():
    before = sorted(p.relative_to(FIXTURES) for p in FIXTURES.rglob("*"))
    for frame in FRAMES:
        load_normalized("AAPL", frame, base_dir=str(FIXTURES))
    assert sorted(p.relative_to(FIXTURES) for p in FIXTURES.rglob("*")) == before
```

- [ ] **Step 3: Run the test**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_archive_time_basis.py`
Expected: all pass. There is no production code in this task: the test *is* the deliverable and must pass against today's `data_store`. An empty fixture fails in `_raw_stamps` and names the file.

- [ ] **Step 4: Read the verdict**

- All green → verdict `ARCHIVE_TIME_BASIS_OK`.
- `test_every_archived_stamp_carries_a_utc_offset`, `test_load_normalized_returns_the_file_stamps_as_naive_utc` or the DST test fails for a ticker → verdict `ARCHIVE_TIME_BASIS_FAIL <ticker> <frame>`. Stop and tell the controller before committing (CLAUDE.md: green means 0 failed and 0 xfailed, so an `xfail` is the controller's call, never yours). V228-2 then converts that frame's index to naive-UTC bar starts.
- `test_mixed_offsets…` or `test_a_single_non_utc_offset…` fails → pandas changed behaviour; report it and do not edit `data_store.py` in this plan.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/v228/archive tests/marketdata/test_archive_time_basis.py
git commit -m "test(v228): pin the archive time basis on real AAPL/GC_F rows across the DST change

ARCHIVE_TIME_BASIS_OK: load_normalized returns naive-UTC bar starts for the
Alpaca (AAPL) and Yahoo (GC=F) 5min/15min/hourly archives; mixed offsets -> None.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V228-2: `compute_excursion` with coverage, density, slice and anchors; `compute_mfe_mae` as a wrapper

**Model:** opus — the no-lookahead surface of the plan (entry-bar exclusion, anchors, time basis) plus a behaviour-preserving split of a baseline function.

**Files:**
- Modify: `swingbot/core/analytics/mfe_mae.py` (everything above `def compute_mfe_mae` is replaced; `compute_mfe_mae` itself stays untouched until V228-2b)
- Modify: `tests/suites.toml` (new `[suites.excursion]` directly after `[suites.analytics]`, line 65–67)
- Create: `tests/excursion/__init__.py` (empty)
- Create: `tests/excursion/test_compute_excursion.py`
- Unchanged but must stay green: `tests/analytics/test_mfe_mae.py`

**Split:** this task passed 20 KB and is split, not compressed. V228-2 adds the new core beside the old function; V228-2b turns `compute_mfe_mae` into the wrapper, drops the baseline row and adds the parity and edge-case tests.

**Interfaces:**
- Consumes: `swingbot.core.analytics.metrics.r_multiple(trade) -> float | None` (exists, `metrics.py:259`); V228-1's verdict (`ARCHIVE_TIME_BASIS_OK`: archive indexes are naive-UTC bar starts). If V228-1 reported `ARCHIVE_TIME_BASIS_FAIL`, the controller tells you which frame to convert in `_naive_index`; the contract below does not change.
- Produces (final names, consumed by V228-4, V228-5 and V228-9):
  - `EXCURSION_SOURCES = ("5min", "15min", "hourly", "daily")`
  - `INTRADAY_SOURCES = ("5min", "15min", "hourly")`
  - `BAR_MINUTES = {"5min": 5, "15min": 15, "hourly": 60}`
  - `source_rank(source: str | None) -> int` — 5min 0, 15min 1, hourly 2, daily 3, `None`/unknown 4
  - `coarser_sources(source: str) -> tuple[str | None, ...]` — sources ranked coarser, then `None` (e.g. `"15min"` → `("hourly", "daily", None)`)
  - `frame_verdicts(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict[str, str]` — values `"ok"`, `"empty"`, `"coverage"`, `"density"`, `"unsupported"`; `{}` when the trade has no usable risk or dates
  - `compute_excursion(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict | None` — keys `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`
  - `compute_mfe_mae(trade, df) -> dict | None` — untouched here; becomes the wrapper in V228-2b

**Rules implemented (Global Constraints, restated so the implementer needs nothing else):** frames are tried finest first whatever the mapping order; an intraday frame covers when its first bar starts at or before `opened_at` and its last bar starts at or after `closed_at` minus one bar; density — inside the window from the bar holding the entry to `closed_at`, two consecutive bars on the same calendar date at most **four** bar lengths apart; slice — bar start `>= opened_at` and `<= closed_at` (so the bar containing the fill is dropped unless it starts exactly at the fill, and the bar containing the exit is kept); anchors (intraday only) — `mfe_r >= max(0, r at exit)`, `mae_r >= max(0, -r at exit)`, where `r at exit` is the signed move to `exit_price` over the risk; an empty intraday slice is answered from the anchors; `daily` keeps today's arithmetic byte for byte (no anchors, empty slice → not covered); efficiency `r_multiple / mfe_r` clamped to `[-5, 1]` when `mfe_r > 0`; 4 dp.

- [ ] **Step 1: Join the new test directory to a suite**

In `tests/suites.toml`, directly after the `[suites.analytics]` block (lines 65–67), add:

```toml
[suites.excursion]
description = "v228 intraday MFE/MAE: excursion core, frames loader, upgrade pass"
paths = ["tests/excursion/"]
```

Create the empty `tests/excursion/__init__.py`. `tests/analytics/` holds about 1,121 of its 1,200 tests, so the excursion tests live here; the limit is never raised.

- [ ] **Step 2: Write the failing tests**

Create `tests/excursion/test_compute_excursion.py` (V228-2b appends more tests to it):

```python
"""v228 V228-2: compute_excursion -- finest covering frame, entry bar out,
exit bar in, anchors, density, time basis, daily parity."""
from __future__ import annotations

import pandas as pd
import pytest

from swingbot.core.analytics.mfe_mae import (
    BAR_MINUTES, EXCURSION_SOURCES, INTRADAY_SOURCES, coarser_sources,
    compute_excursion, frame_verdicts, source_rank,
)
from tests.conftest import make_ohlcv

DAY = "2026-11-12"


def _flat(start, end, freq, high=100.5, low=99.5):
    idx = pd.date_range(start, end, freq=freq)
    mid = (high + low) / 2
    return pd.DataFrame({"Open": mid, "High": high, "Low": low, "Close": mid,
                         "Volume": 1000.0}, index=idx)


def _session(freq="5min", start=f"{DAY} 14:30", end=f"{DAY} 20:55"):
    return _flat(start, end, freq)


def _set(df, ts, high=None, low=None):
    if high is not None:
        df.loc[pd.Timestamp(ts), "High"] = high
    if low is not None:
        df.loc[pd.Timestamp(ts), "Low"] = low
    return df


def _trade(**kw):
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 98.0, "exit_price": 101.0,
         "status": "win", "opened_at": f"{DAY}T15:02:00+00:00",
         "closed_at": f"{DAY}T15:31:00+00:00"}
    t.update(kw)
    return t


def _spiky_5min():
    df = _session()
    _set(df, f"{DAY} 15:00", high=110.0, low=90.0)   # holds the fill: pre-fill prices
    _set(df, f"{DAY} 15:30", high=104.0)             # holds the exit: kept
    _set(df, f"{DAY} 15:35", high=120.0, low=80.0)   # after the exit: never read
    return df


def test_constants_and_ranks():
    assert EXCURSION_SOURCES == ("5min", "15min", "hourly", "daily")
    assert INTRADAY_SOURCES == ("5min", "15min", "hourly")
    assert BAR_MINUTES == {"5min": 5, "15min": 15, "hourly": 60}
    assert [source_rank(s) for s in (*EXCURSION_SOURCES, None, "1min")] == [0, 1, 2, 3, 4, 4]
    assert coarser_sources("5min") == ("15min", "hourly", "daily", None)
    assert coarser_sources("15min") == ("hourly", "daily", None)
    assert coarser_sources("daily") == (None,)


def test_entry_bar_is_dropped_and_exit_bar_is_kept():
    m = compute_excursion(_trade(), {"5min": _spiky_5min()})
    assert m == {"mfe_r": 2.0, "mae_r": 0.25, "exit_efficiency": 0.25, "excursion_source": "5min"}


@pytest.mark.parametrize("opened,mfe", [("15:00:00", 5.0), ("15:00:01", 2.0), ("15:01:00", 2.0)])
def test_a_bar_starting_exactly_at_the_fill_is_kept_an_earlier_one_dropped(opened, mfe):
    """The 15:00 bar holds the 110 spike: kept when the fill is at 15:00:00, dropped
    once the bar started before the fill (15:00:01, 15:01)."""
    m = compute_excursion(_trade(opened_at=f"{DAY}T{opened}+00:00"), {"5min": _spiky_5min()})
    assert m["mfe_r"] == mfe


def test_a_trade_inside_one_bar_is_answered_from_its_anchors():
    loss = _trade(opened_at=f"{DAY}T15:31:00+00:00", closed_at=f"{DAY}T15:33:00+00:00",
                  exit_price=99.0, status="loss")
    assert compute_excursion(loss, {"5min": _spiky_5min()}) == {
        "mfe_r": 0.0, "mae_r": 0.5, "exit_efficiency": None, "excursion_source": "5min"}
    win = dict(loss, exit_price=101.2, status="win")
    m = compute_excursion(win, {"5min": _spiky_5min()})
    assert (m["mfe_r"], m["mae_r"], m["exit_efficiency"]) == (0.6, 0.0, 1.0)


def test_anchors_lift_an_excursion_the_bars_understate():
    m = compute_excursion(_trade(exit_price=103.0), {"5min": _session()})
    assert m["mfe_r"] == 1.5 and m["mae_r"] == 0.25


def test_bearish_trades_mirror_every_rule():
    df = _session()
    _set(df, f"{DAY} 15:00", high=110.0, low=90.0)
    _set(df, f"{DAY} 15:30", low=96.0)
    t = _trade(direction="bearish", entry=100.0, stop_loss=102.0, exit_price=99.0)
    m = compute_excursion(t, {"5min": df})
    assert (m["mfe_r"], m["mae_r"], m["exit_efficiency"]) == (2.0, 0.25, 0.25)


def test_coverage_failure_falls_through_each_rung():
    late_5 = _flat(f"{DAY} 15:10", f"{DAY} 20:55", "5min")          # starts after the fill
    short_15 = _flat(f"{DAY} 14:30", f"{DAY} 15:00", "15min")       # ends before the exit
    hourly = _flat(f"{DAY} 14:30", f"{DAY} 20:30", "60min")
    daily = make_ohlcv([100.0], spread_pct=1.0, start=DAY)
    frames = {"5min": late_5, "15min": short_15, "hourly": hourly, "daily": daily}
    assert frame_verdicts(_trade(), frames) == {
        "5min": "coverage", "15min": "coverage", "hourly": "ok", "daily": "ok"}
    assert compute_excursion(_trade(), frames)["excursion_source"] == "hourly"
    frames["hourly"] = None
    assert compute_excursion(_trade(), frames)["excursion_source"] == "daily"



def test_a_hole_inside_the_hold_skips_the_frame():
    holed = _session().drop(pd.date_range(f"{DAY} 15:05", f"{DAY} 15:20", freq="5min"))
    frames = {"5min": holed, "15min": _session("15min", end=f"{DAY} 20:45")}
    assert frame_verdicts(_trade(), frames)["5min"] == "density"
    assert compute_excursion(_trade(), frames)["excursion_source"] == "15min"


def test_a_gap_of_exactly_four_bars_is_dense_enough():
    gap = _session().drop(pd.date_range(f"{DAY} 15:05", f"{DAY} 15:15", freq="5min"))  # 15:00 -> 15:20
    assert frame_verdicts(_trade(), {"5min": gap}) == {"5min": "ok"}



def test_time_basis_aware_index_and_offset_trade_times_match_naive_utc():
    naive = compute_excursion(_trade(), {"5min": _spiky_5min()})
    aware = _spiky_5min().tz_localize("UTC")
    assert compute_excursion(_trade(), {"5min": aware}) == naive
    new_york = _trade(opened_at=f"{DAY}T10:02:00-05:00", closed_at=f"{DAY}T10:31:00-05:00")
    assert compute_excursion(new_york, {"5min": _spiky_5min()}) == naive

```

- [ ] **Step 3: Run to see them fail**

Run: `python scripts/dev/testrun.py file tests/excursion/test_compute_excursion.py`
Expected: collection error, `ImportError: cannot import name 'BAR_MINUTES'`.

- [ ] **Step 4: Replace the top of `swingbot/core/analytics/mfe_mae.py`**

Replace the module docstring, the imports and `_parse_dt` (lines 1–24, everything above `def compute_mfe_mae`) with the block below. Leave `def compute_mfe_mae` and its body (lines 26–88) exactly as they are at the end of the module; it still uses `_parse_dt`, `dt` and `r_multiple`, which the block keeps.

```python
"""Maximum Favorable/Adverse Excursion and exit efficiency for one closed
trade -- the "how good was this exit, really" number the auto-journal
(journal.py) is built around.

v228: the excursion is measured on the finest archived bars that cover the
trade (5min, 15min, hourly, then daily), and the result names the frame used
(`excursion_source`). Since 2026-10-01 most LONG trades close the day they
open, and a daily bar's range includes price before the fill and after the
exit. Intraday rules: the bar holding the fill is dropped (pre-fill prices),
the bar holding the exit is kept (overstates by at most one bar), and the
entry and exit prices are always points on the path (anchors), so a trade
inside one bar still gets a bounded answer -- a lower bound, since the
source names the bars consulted, not the precision achieved. The daily frame
keeps the pre-v228 arithmetic exactly.

Time basis: archive indexes from data_store.load_normalized are naive UTC
bar starts (pinned by tests/marketdata/test_archive_time_basis.py); journal
times are aware UTC ISO strings, converted to naive UTC before comparing.

Pure functions, no I/O -- excursion_frames.load_frames loads the frames."""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from swingbot.core.analytics.metrics import r_multiple

EXCURSION_SOURCES = ("5min", "15min", "hourly", "daily")
INTRADAY_SOURCES = ("5min", "15min", "hourly")
BAR_MINUTES = {"5min": 5, "15min": 15, "hourly": 60}
#: Two bars on one date further apart than this many bar lengths are a hole:
#: the frame is skipped like an uncovered one, never used silently.
DENSITY_BAR_LENGTHS = 4


def source_rank(source: str | None) -> int:
    """5min 0 ... daily 3; None or anything unknown ranks coarsest (4)."""
    try:
        return EXCURSION_SOURCES.index(source)
    except ValueError:
        return len(EXCURSION_SOURCES)


def coarser_sources(source: str) -> tuple[str | None, ...]:
    """Every stored source a result from `source` may replace, then None."""
    rank = source_rank(source)
    return tuple(s for s in EXCURSION_SOURCES if source_rank(s) > rank) + (None,)


def _parse_dt(iso_str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _Inputs:
    entry: float
    risk: float
    start: dt.datetime
    end: dt.datetime
    is_bull: bool


def _inputs(trade: dict) -> _Inputs | None:
    entry, stop = trade.get("entry"), trade.get("stop_loss")
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    start = _parse_dt(trade.get("opened_at"))
    end = _parse_dt(trade.get("closed_at"))
    if start is None or end is None:
        return None
    return _Inputs(entry, risk, start, end, trade.get("direction") == "bullish")


def _naive_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)


def _naive_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx


def _daily_slice(df: pd.DataFrame, inputs: _Inputs) -> pd.DataFrame:
    """The pre-v228 date-level slice, unchanged."""
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        start = inputs.start if inputs.start.tzinfo else inputs.start.replace(tzinfo=dt.timezone.utc)
        end = inputs.end if inputs.end.tzinfo else inputs.end.replace(tzinfo=dt.timezone.utc)
    else:
        start, end = inputs.start.replace(tzinfo=None), inputs.end.replace(tzinfo=None)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return df.loc[(idx >= start) & (idx <= end)]


def _cover(idx: pd.DatetimeIndex, start: dt.datetime, end: dt.datetime, bar: dt.timedelta) -> bool:
    return idx[0] <= start and idx[-1] >= end - bar


def _dense(idx: pd.DatetimeIndex, start: dt.datetime, end: dt.datetime, bar: dt.timedelta) -> bool:
    window = idx[(idx > start - bar) & (idx <= end)]
    if len(window) < 2:
        return True
    gaps = window[1:] - window[:-1]
    same_date = window[1:].normalize() == window[:-1].normalize()
    return not bool(((gaps > bar * DENSITY_BAR_LENGTHS) & same_date).any())


def _intraday_verdict(name: str, df: pd.DataFrame, inputs: _Inputs):
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    bar = dt.timedelta(minutes=BAR_MINUTES[name])
    idx = _naive_index(df)
    start, end = _naive_utc(inputs.start), _naive_utc(inputs.end)
    if not _cover(idx, start, end, bar):
        return "coverage", None
    if not _dense(idx, start, end, bar):
        return "density", None
    return "ok", df.loc[(idx >= start) & (idx <= end)]


def _verdict(name: str, df: pd.DataFrame | None, inputs: _Inputs):
    if name not in EXCURSION_SOURCES:
        return "unsupported", None
    if df is None or df.empty:
        return "empty", None
    if name == "daily":
        sliced = _daily_slice(df, inputs)
        return ("coverage", None) if sliced.empty else ("ok", sliced)
    return _intraday_verdict(name, df, inputs)


def _ordered(frames: Mapping[str, pd.DataFrame | None]):
    return sorted(frames.items(), key=lambda item: source_rank(item[0]))


def _excursion_r(sliced: pd.DataFrame, inputs: _Inputs) -> tuple[float, float]:
    high, low = float(sliced["High"].max()), float(sliced["Low"].min())
    if inputs.is_bull:
        return (high - inputs.entry) / inputs.risk, max(0.0, (inputs.entry - low) / inputs.risk)
    return (inputs.entry - low) / inputs.risk, max(0.0, (high - inputs.entry) / inputs.risk)


def _exit_r(trade: dict, inputs: _Inputs) -> float:
    """Signed R of the exit price; 0.0 (the entry anchor) when unknown."""
    try:
        price = float(trade.get("exit_price"))
    except (TypeError, ValueError):
        return 0.0
    move = price - inputs.entry if inputs.is_bull else inputs.entry - price
    return move / inputs.risk


def _anchored_r(sliced: pd.DataFrame, inputs: _Inputs, trade: dict) -> tuple[float, float]:
    mfe, mae = _excursion_r(sliced, inputs) if not sliced.empty else (0.0, 0.0)
    exit_r = _exit_r(trade, inputs)
    return max(mfe, 0.0, exit_r), max(mae, 0.0, -exit_r)


def _result(mfe_r: float, mae_r: float, trade: dict, source: str) -> dict:
    r_real = r_multiple(trade)
    exit_efficiency = None
    if r_real is not None and mfe_r > 0:
        exit_efficiency = max(-5.0, min(1.0, r_real / mfe_r))
    return {"mfe_r": round(mfe_r, 4), "mae_r": round(mae_r, 4),
            "exit_efficiency": round(exit_efficiency, 4) if exit_efficiency is not None else None,
            "excursion_source": source}


def frame_verdicts(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict[str, str]:
    """Why each frame was used or skipped, finest first; {} for an unusable trade."""
    inputs = _inputs(trade)
    if inputs is None:
        return {}
    return {name: _verdict(name, df, inputs)[0] for name, df in _ordered(frames)}


def compute_excursion(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict | None:
    """MFE/MAE/exit efficiency from the finest frame that covers the trade."""
    inputs = _inputs(trade)
    if inputs is None or not frames:
        return None
    for name, df in _ordered(frames):
        verdict, sliced = _verdict(name, df, inputs)
        if verdict != "ok":
            continue
        if name == "daily":
            mfe_r, mae_r = _excursion_r(sliced, inputs)
        else:
            mfe_r, mae_r = _anchored_r(sliced, inputs, trade)
        return _result(mfe_r, mae_r, trade, name)
    return None
```

Notes for the implementer:
- `_Inputs.entry` keeps the trade's own number (not `float(...)`), so the daily path computes exactly what the old code did; V228-2b relies on that for byte-for-byte parity.
- `swingbot/core/analytics/__init__.py:23` re-exports `compute_mfe_mae` only; leave it.
- If V228-1 reported a provider failure, the conversion goes in `_naive_index` (the only place a frame index is read).

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/excursion/test_compute_excursion.py`
Expected: all pass.
Run: `python scripts/dev/testrun.py file tests/analytics/test_mfe_mae.py`
Expected: all pass (the old function is untouched).
Run: `python scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: pass (the new directory belongs to exactly one suite).
Run: `python -m radon cc -s -n C swingbot/core/analytics/mfe_mae.py`
Expected: only `compute_mfe_mae` (C, 16) is listed — V228-2b removes it.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/mfe_mae.py tests/suites.toml tests/excursion/__init__.py tests/excursion/test_compute_excursion.py
git commit -m "feat(v228): compute_excursion on the finest covering frame (coverage, density, entry bar out, anchors)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V228-2b: `compute_mfe_mae` becomes the daily wrapper; parity and edge-case tests; baseline row dropped

**Model:** opus — behaviour-preserving refactor of a baseline function whose numbers every journal reader inherits; parity must be exact.

**Files:**
- Modify: `swingbot/core/analytics/mfe_mae.py` (`compute_mfe_mae` body only)
- Modify: `scripts/dev/complexity_baseline.json` (delete the row `"swingbot.core.analytics.mfe_mae:compute_mfe_mae": 16,`, line 44)
- Modify: `tests/excursion/test_compute_excursion.py` (created by V228-2; import line plus appended tests)
- Unchanged but must stay green: `tests/analytics/test_mfe_mae.py` (the pre-v228 daily fixtures)

**Interfaces:**
- Consumes (from V228-2, same module): `compute_excursion`, `frame_verdicts`, the test helpers `_flat`, `_session`, `_set`, `_trade`, `_spiky_5min`, `DAY` and the `make_ohlcv` import already in the test file.
- Produces: `compute_mfe_mae(trade, df) -> dict | None` with its pre-v228 contract — keys `mfe_r`, `mae_r`, `exit_efficiency` only; `None` when `df is None`, the trade has no usable risk or dates, or the date-level slice is empty. Nothing else changes for V228-4/5.

These tests pin behaviour that V228-2's `compute_excursion` already has and that the old `compute_mfe_mae` already had; they pass before and after the refactor. They are the parity guard; the refactor's own gate is Step 5 (complexity).

- [ ] **Step 1: Extend the test file**

In `tests/excursion/test_compute_excursion.py`, change the import to:

```python
from swingbot.core.analytics.mfe_mae import (
    BAR_MINUTES, EXCURSION_SOURCES, INTRADAY_SOURCES, coarser_sources,
    compute_excursion, compute_mfe_mae, frame_verdicts, source_rank,
)
```

and append:

```python
def test_last_bar_tolerance_is_one_bar_length():
    df = _flat(f"{DAY} 14:30", f"{DAY} 15:25", "5min")  # last start 15:25 vs close 15:31
    assert frame_verdicts(_trade(), {"5min": df}) == {"5min": "coverage"}
    df = _flat(f"{DAY} 14:30", f"{DAY} 15:26", "1min").resample("5min").last()  # last start 15:25
    assert frame_verdicts(_trade(closed_at=f"{DAY}T15:30:00+00:00"), {"5min": df}) == {"5min": "ok"}


def test_the_overnight_gap_between_sessions_is_not_a_hole():
    two_days = pd.concat([_session(), _session(start="2026-11-13 14:30", end="2026-11-13 20:55")])
    t = _trade(closed_at="2026-11-13T15:31:00+00:00")
    assert frame_verdicts(t, {"5min": two_days}) == {"5min": "ok"}


def test_mapping_order_does_not_matter_and_unknown_frames_are_skipped():
    daily = make_ohlcv([100.0], spread_pct=1.0, start=DAY)
    frames = {"1min": _session("1min"), "daily": daily, "5min": _spiky_5min()}
    assert compute_excursion(_trade(), frames)["excursion_source"] == "5min"
    assert frame_verdicts(_trade(), frames) == {"5min": "ok", "daily": "ok", "1min": "unsupported"}


def test_daily_keeps_todays_arithmetic_without_anchors():
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    assert compute_excursion(t, {"daily": df}) == {
        "mfe_r": 2.0, "mae_r": 0.5, "exit_efficiency": 0.5, "excursion_source": "daily"}
    beyond = make_ohlcv([100, 101], spread_pct=0.0, start="2026-03-02")
    t2 = dict(t, closed_at="2026-03-03T15:00:00+00:00")
    assert compute_excursion(t2, {"daily": beyond})["mfe_r"] == 0.25   # exit 104 is NOT an anchor


def test_compute_mfe_mae_is_the_daily_wrapper():
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00"}
    assert compute_mfe_mae(t, df) == {"mfe_r": 2.0, "mae_r": 0.5, "exit_efficiency": 0.5}
    assert compute_mfe_mae(t, None) is None
    outside = dict(t, opened_at="2027-01-04T15:00:00+00:00", closed_at="2027-01-05T15:00:00+00:00")
    assert compute_mfe_mae(outside, df) is None


@pytest.mark.parametrize("frames", [{}, {"5min": None, "daily": None},
                                    {"5min": pd.DataFrame(), "daily": pd.DataFrame()}])
def test_no_bars_at_all_gives_no_answer(frames):
    assert compute_excursion(_trade(), frames) is None


def test_an_empty_finer_frame_falls_to_the_next():
    frames = {"5min": pd.DataFrame(), "15min": _session("15min", end=f"{DAY} 20:45")}
    assert frame_verdicts(_trade(), frames)["5min"] == "empty"
    assert compute_excursion(_trade(), frames)["excursion_source"] == "15min"


@pytest.mark.parametrize("bad", [{"stop_loss": 100.0}, {"stop_loss": None}, {"entry": None},
                                 {"opened_at": None}, {"closed_at": "not a date"}])
def test_unusable_trades_give_none_and_no_verdicts(bad):
    t = _trade(**bad)
    assert compute_excursion(t, {"5min": _session()}) is None
    assert frame_verdicts(t, {"5min": _session()}) == {}


def test_rounding_and_efficiency_clamp():
    df = _session()
    _set(df, f"{DAY} 15:10", high=101.0)
    m = compute_excursion(_trade(stop_loss=97.0, exit_price=100.0), {"5min": df})
    assert m["mfe_r"] == 0.3333 and m["mae_r"] == 0.1667 and m["exit_efficiency"] == 0.0
    clamp = compute_excursion(_trade(exit_price=96.0, status="loss"), {"5min": _session()})
    assert clamp["mfe_r"] == 0.25 and clamp["mae_r"] == 2.0 and clamp["exit_efficiency"] == -5.0
```

Check the clamp case by hand: bars 100.5/99.5, entry 100, risk 2, exit 96 → r = −2.0; mfe = max(0.25, 0, −2) = 0.25; mae = max(0.25, 2.0) = 2.0; efficiency −2 / 0.25 = −8 → −5.0. The rounding case: risk 3, high 101 → 1/3 → 0.3333; low 99.5 → 0.5/3 → 0.1667; exit 100 → r 0 → efficiency 0.0.

- [ ] **Step 2: Run them against the old function**

Run: `python scripts/dev/testrun.py file tests/excursion/test_compute_excursion.py`
Expected: all pass (parity guard in place before the refactor).

- [ ] **Step 3: Replace the body of `compute_mfe_mae`**

Replace the whole `def compute_mfe_mae` (docstring and body, lines 26–88 before V228-2; now at the end of the module) with:

```python
def compute_mfe_mae(trade: dict, df) -> dict | None:
    """The pre-v228 contract: daily bars only, three keys, None without bars."""
    if df is None:
        return None
    m = compute_excursion(trade, {"daily": df})
    if m is None:
        return None
    return {key: m[key] for key in ("mfe_r", "mae_r", "exit_efficiency")}
```

Update the module docstring's last paragraph only if it still mentions "cached daily bars" (V228-2 already rewrote it).

- [ ] **Step 4: Run every excursion test and the old fixtures**

Run: `python scripts/dev/testrun.py file tests/excursion/test_compute_excursion.py`
Expected: all pass.
Run: `python scripts/dev/testrun.py file tests/analytics/test_mfe_mae.py`
Expected: all 6 pass unchanged (byte-for-byte daily parity).

- [ ] **Step 5: Drop the baseline row and check complexity**

Delete the line `    "swingbot.core.analytics.mfe_mae:compute_mfe_mae": 16,` from `scripts/dev/complexity_baseline.json` (it is not the last entry, so no comma fix is needed).

Run: `python -m radon cc -s -n C swingbot/core/analytics/mfe_mae.py`
Expected: no output (every function under 11).
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/mfe_mae.py scripts/dev/complexity_baseline.json tests/excursion/test_compute_excursion.py
git commit -m "refactor(v228): compute_mfe_mae is compute_excursion's daily wrapper; baseline row removed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V228-3: Conditional `Repository.patch(where=)` and `JournalRepository.patch_if_coarser`

**Model:** sonnet — a small, well-precedented SQLAlchemy change; the one subtle point (the guard lives in the `UPDATE`) is spelled out and tested.

**Files:**
- Modify: `swingbot/core/db/repositories/base.py` (`Repository.patch`, lines 97–110)
- Modify: `swingbot/core/db/repositories/journal.py` (new method on `JournalRepository`)
- Modify: `tests/db/test_repository_base.py`
- Modify: `tests/db/test_journal_repository.py`

**Interfaces:**
- Consumes: nothing from other v228 tasks (this task runs in parallel with V228-1/V228-2, so its tests spell the source tuples out literally instead of importing `coarser_sources`).
- Produces (final, consumed by V228-5):
  - `Repository.patch(self, key_value, changes: dict, *, conn=None, where: sa.ColumnElement[bool] | None = None) -> dict | None` — `where` is ANDed into the `UPDATE ... WHERE key = :key`; returns `None` when no row matched (missing key **or** guard miss). Every existing caller passes no `where` and keeps today's behaviour.
  - `JournalRepository.patch_if_coarser(self, trade_id: str, changes: dict, *, coarser: tuple[str | None, ...], conn=None) -> dict | None` — matches only while `coalesce(doc->>'excursion_source', '')` is in `coarser`, with `None` mapped to `''` (so a missing field and an explicit JSON `null` both count as `None`). No read before the write.

**Why in the statement:** the bot's nightly pass (V228-6) and the operator backfill (V228-8) can reach the same entry at once. With the rank guard inside the `UPDATE`, whichever finer write lands first wins and a coarser one matches zero rows; a read-then-write check would let them downgrade each other. The patch composes JSONB with `||`, so fields it does not name — above all the partner's `note` — are never touched.

Run `/replicate-prod-db` before Step 2 (DB tests; shared `swing-db` container).

- [ ] **Step 1: Write the failing tests**

Append to `tests/db/test_repository_base.py` (the module already imports `pytest`, `Repository`, `trades`; add the `journal_entries` import at the top):

```python
from swingbot.core.db.schema import journal_entries


def _journal_row(**doc):
    return {"trade_id": "J1", "strategy": "RSI", "outcome": "loss",
            "closed_at": "2026-11-12T15:31:00+00:00",
            "created_at": "2026-11-12T15:32:00+00:00", **doc}


def test_patch_where_that_matches_composes_the_doc(db_conn):
    repo = Repository(journal_entries, "trade_id")
    repo.upsert(_journal_row(note="keep", mfe_r=1.0), conn=db_conn)
    out = repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn,
                     where=journal_entries.c.doc["note"].astext == "keep")
    assert out["mfe_r"] == 0.3 and out["note"] == "keep"


def test_patch_where_that_misses_returns_none_and_writes_nothing(db_conn):
    repo = Repository(journal_entries, "trade_id")
    repo.upsert(_journal_row(note="keep", mfe_r=1.0), conn=db_conn)
    assert repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn,
                      where=journal_entries.c.doc["note"].astext == "other") is None
    assert repo.get("J1", conn=db_conn)["mfe_r"] == 1.0


def test_patch_without_where_keeps_todays_behaviour(db_conn):
    repo = Repository(journal_entries, "trade_id")
    assert repo.patch("missing", {"mfe_r": 0.3}, conn=db_conn) is None
    repo.upsert(_journal_row(mfe_r=1.0), conn=db_conn)
    assert repo.patch("J1", {"mfe_r": 0.3}, conn=db_conn)["mfe_r"] == 0.3
```

Append to `tests/db/test_journal_repository.py` (uses its `repo` fixture and `_entry` helper):

```python
FINER_THAN_5MIN = ("15min", "hourly", "daily", None)   # coarser_sources("5min") in V228-2
FINER_THAN_HOURLY = ("daily", None)                     # coarser_sources("hourly")


def test_patch_if_coarser_upgrades_a_daily_row_and_keeps_the_note(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="daily", mfe_r=1.24, note="partner note"), conn=db_conn)
    out = repo.patch_if_coarser("T1", {"mfe_r": 0.31, "excursion_source": "5min"},
                                coarser=FINER_THAN_5MIN, conn=db_conn)
    assert (out["excursion_source"], out["mfe_r"], out["note"]) == ("5min", 0.31, "partner note")
    assert out["tags"] == ["clean-entry"] and out["lesson"] == "held to TP1"


def test_a_coarser_write_after_a_finer_one_is_a_no_op(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="daily", mfe_r=1.24), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"mfe_r": 0.31, "excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is not None
    assert repo.patch_if_coarser("T1", {"mfe_r": 0.5, "excursion_source": "hourly"},
                                 coarser=FINER_THAN_HOURLY, conn=db_conn) is None
    row = repo.get("T1", conn=db_conn)
    assert (row["excursion_source"], row["mfe_r"]) == ("5min", 0.31)


@pytest.mark.parametrize("stored", [{}, {"excursion_source": None}])
def test_a_missing_or_null_source_counts_as_none(repo, db_conn, stored):
    repo.upsert(_entry("T1", **stored), conn=db_conn)
    out = repo.patch_if_coarser("T1", {"excursion_source": "daily", "mfe_r": 1.0},
                                coarser=(None,), conn=db_conn)
    assert out["excursion_source"] == "daily"


def test_an_equal_source_is_not_rewritten(repo, db_conn):
    repo.upsert(_entry("T1", excursion_source="hourly", mfe_r=0.9), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"excursion_source": "hourly", "mfe_r": 0.1},
                                 coarser=FINER_THAN_HOURLY, conn=db_conn) is None
    assert repo.get("T1", conn=db_conn)["mfe_r"] == 0.9


def test_a_missing_row_and_an_empty_coarser_set_never_match(repo, db_conn):
    assert repo.patch_if_coarser("nope", {"excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is None
    repo.upsert(_entry("T1", excursion_source="daily"), conn=db_conn)
    assert repo.patch_if_coarser("T1", {"excursion_source": "5min"},
                                 coarser=(), conn=db_conn) is None


def test_patch_if_coarser_never_reads_before_writing(repo, db_conn, monkeypatch):
    repo.upsert(_entry("T1", excursion_source="daily"), conn=db_conn)

    def no_read(*args, **kwargs):
        raise AssertionError("patch_if_coarser must not read-then-write")

    monkeypatch.setattr(repo, "get", no_read)
    monkeypatch.setattr(repo, "get_for_update", no_read)
    assert repo.patch_if_coarser("T1", {"excursion_source": "5min"},
                                 coarser=FINER_THAN_5MIN, conn=db_conn) is not None
```

- [ ] **Step 2: Run to see them fail**

Run: `python scripts/dev/testrun.py file tests/db/test_repository_base.py`
Expected: the three new tests fail with `TypeError: Repository.patch() got an unexpected keyword argument 'where'` (the last one passes already).
Run: `python scripts/dev/testrun.py file tests/db/test_journal_repository.py`
Expected: new tests fail with `AttributeError: 'JournalRepository' object has no attribute 'patch_if_coarser'`.
If they *skip*, the database is down: start it (see `/replicate-prod-db`) and re-run — a skip is not a pass.

- [ ] **Step 3: Add `where=` to `Repository.patch`**

In `swingbot/core/db/repositories/base.py`, replace `patch` (lines 97–110) with:

```python
    def patch(self, key_value: Any, changes: dict, *,
              conn: sa.Connection | None = None,
              where: sa.ColumnElement[bool] | None = None) -> dict | None:
        """Patch named fields only, composing JSONB changes in the database.

        ``where`` (v228) is ANDed into the UPDATE itself, so a guard on the
        stored row ("only while its source is coarser") cannot race a
        concurrent writer the way a read-then-write check would. None is
        returned when no row matched: a missing key or a guard miss."""
        columns, document_patch = split_doc(changes, self.promoted)
        values: dict[str, Any] = {**columns, "updated_at": sa.func.clock_timestamp()}
        if document_patch:
            values["doc"] = self.table.c.doc.op("||")(
                sa.cast(sa.literal(document_patch, type_=sa.JSON), JSONB))
        statement = sa.update(self.table).where(self.key_col == key_value)
        if where is not None:
            statement = statement.where(where)
        statement = statement.values(**values).returning(self.table)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)
```

Keep the body of the existing method exactly where this block does not differ (read lines 97–110 first; only the signature, the docstring and the `where` lines are new).

- [ ] **Step 4: Add `JournalRepository.patch_if_coarser`**

In `swingbot/core/db/repositories/journal.py`, add this method after `entries` (before `version`):

```python
    def patch_if_coarser(self, trade_id: str, changes: dict, *,
                         coarser: tuple[str | None, ...], conn=None) -> dict | None:
        """v228: patch an entry only while its stored excursion_source is one
        of ``coarser`` (None = missing or JSON null). The rank guard is part of
        the UPDATE, so the bot's nightly pass and the backfill script cannot
        downgrade each other; fields not in ``changes`` (the note above all)
        are untouched. None when the row is missing or already as fine."""
        allowed = ["" if source is None else source for source in coarser]
        stored = sa.func.coalesce(journal_entries.c.doc["excursion_source"].astext, "")
        return self.patch(trade_id, changes, conn=conn, where=stored.in_(allowed))
```

`stored.in_([])` renders as an always-false expression in SQLAlchemy 2.x, which is what an empty `coarser` must mean.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/db/test_repository_base.py`
Expected: all pass.
Run: `python scripts/dev/testrun.py file tests/db/test_journal_repository.py`
Expected: all pass.
Run: `python scripts/dev/testrun.py file tests/db/test_lost_update.py`
Expected: all pass (existing `patch` callers unchanged).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/base.py swingbot/core/db/repositories/journal.py tests/db/test_repository_base.py tests/db/test_journal_repository.py
git commit -m "feat(v228): Repository.patch(where=) and JournalRepository.patch_if_coarser -- the rank guard lives in the UPDATE

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V228-4: Frames loader; `build_entry`/`journal_trade_close` take frames and record `excursion_source`; both re-journal scripts

**Model:** opus — changes the one builder every journal row goes through, its never-raise close hook and two operator scripts; the note-wipe and fallback paths must stay exact.

**Files:**
- Create: `swingbot/core/analytics/excursion_frames.py`
- Modify: `swingbot/core/analytics/journal.py` (import line 13, `build_entry` line 153, `journal_trade_close` line 190)
- Modify: `scripts/data/backfill_journal.py` (`_fetch_with_cache_fallback` line 24, `backfill` line 61)
- Modify: `scripts/ops/rejournal_fill_mismatch.py` (`EXIT_FIELDS` line 57, `main` lines 71–101)
- Create: `tests/excursion/test_excursion_frames.py`
- Modify: `tests/analytics/test_journal.py`, `tests/analytics/test_journal_risk_features.py`, `tests/tracking/test_origin.py`, `tests/scripts/test_rejournal_fill_mismatch.py`

**Interfaces:**
- Consumes: from V228-2 — `INTRADAY_SOURCES`, `compute_excursion(trade, frames) -> dict | None` (keys `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`); `data_store.load_normalized`, `safe_symbol`, `DATA_DIR` (exist).
- Produces (final, consumed by V228-5 and V228-8):
  - `@dataclass(frozen=True) class FrameSet: frames: dict[str, pd.DataFrame]; missing: tuple[str, ...]; unreadable: tuple[str, ...]`
  - `load_frames(ticker: str, *, daily: pd.DataFrame | None = None, daily_from_archive: bool = False, base_dir: str = DATA_DIR) -> FrameSet` — intraday names in `INTRADAY_SOURCES` order, then `daily`; a passed non-empty `daily` wins over the archive; `daily_from_archive` reads `market_data/daily/<SYMBOL>.csv` only when no `daily` is passed; a file that does not exist is `missing`, a file `load_normalized` cannot use is `unreadable`; never creates a folder.
  - `build_entry(trade: dict, frames: Mapping[str, pd.DataFrame | None] | None) -> dict` — adds `"excursion_source"` (right after `"exit_efficiency"`); a bare DataFrame raises `TypeError`.
  - `journal_trade_close(trade)` loads `load_frames(ticker, daily=get_daily_data(ticker))`; still never raises.

At close time the sub-hourly archives are up to a day stale, so most new entries are written `daily`; V228-5 upgrades them. Spot metals (`XAUUSD`, `XAGUSD`) have no archive under their own name, so they come out `missing` and fall to daily — never compare spot prices with future bars.

Run `/replicate-prod-db` before Step 3 (the journal tests write through `JournalStore`).

- [ ] **Step 1: Write the loader tests**

Create `tests/excursion/test_excursion_frames.py`:

```python
"""v228 V228-4: load_frames tells a missing archive from an unreadable one."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from swingbot.core.analytics.excursion_frames import FrameSet, load_frames
from tests.conftest import make_ohlcv


def _bars(freq: str, periods: int = 6, start: str = "2026-11-12 14:30") -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC", name="Datetime")
    return pd.DataFrame({"Close": 100.0, "High": 100.5, "Low": 99.5, "Open": 100.0,
                         "Volume": 1000.0}, index=idx)


def _write(base, folder: str, stem: str, df: pd.DataFrame | None = None, text: str | None = None):
    (base / folder).mkdir(parents=True, exist_ok=True)
    path = base / folder / f"{stem}.csv"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    else:
        df.to_csv(path)


def test_reads_every_intraday_archive_finest_first_as_naive_utc(tmp_path):
    for folder, freq in (("hourly", "60min"), ("5min", "5min"), ("15min", "15min")):
        _write(tmp_path, folder, "AAPL", _bars(freq))
    fs = load_frames("AAPL", base_dir=str(tmp_path))
    assert list(fs.frames) == ["5min", "15min", "hourly"]
    assert (fs.missing, fs.unreadable) == ((), ())
    assert fs.frames["5min"].index.tz is None
    assert fs.frames["5min"].index[0] == pd.Timestamp("2026-11-12 14:30")


def test_a_missing_file_and_an_unreadable_file_are_told_apart(tmp_path):
    _write(tmp_path, "5min", "AAPL", _bars("5min"))
    _write(tmp_path, "15min", "AAPL", text="Datetime,Close\nnot-a-date,1\n")
    fs = load_frames("AAPL", base_dir=str(tmp_path))
    assert list(fs.frames) == ["5min"]
    assert fs.missing == ("hourly",)
    assert fs.unreadable == ("15min",)


def test_a_passed_daily_frame_goes_last_and_wins_over_the_archive(tmp_path):
    daily = make_ohlcv([100.0, 101.0], start="2026-11-11")
    _write(tmp_path, "daily", "AAPL", _bars("1D", periods=2, start="2026-11-11"))
    fs = load_frames("AAPL", daily=daily, daily_from_archive=True, base_dir=str(tmp_path))
    assert list(fs.frames) == ["daily"]
    assert fs.frames["daily"] is daily
    assert fs.missing == ("5min", "15min", "hourly")


def test_an_empty_daily_frame_is_left_out_and_not_counted(tmp_path):
    fs = load_frames("AAPL", daily=pd.DataFrame(), base_dir=str(tmp_path))
    assert "daily" not in fs.frames and "daily" not in fs.missing


def test_daily_from_archive_reads_the_daily_folder_or_counts_it_missing(tmp_path):
    assert load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path)).missing == (
        "5min", "15min", "hourly", "daily")
    _write(tmp_path, "daily", "AAPL", _bars("1D", periods=2, start="2026-11-11"))
    fs = load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path))
    assert list(fs.frames) == ["daily"]


@pytest.mark.parametrize("ticker", ["XAUUSD", ""])
def test_spot_metals_and_blank_tickers_have_no_files(tmp_path, ticker):
    _write(tmp_path, "5min", "GC_F", _bars("5min"))
    fs = load_frames(ticker, base_dir=str(tmp_path))
    assert fs.frames == {} and fs.missing == ("5min", "15min", "hourly")


def test_a_future_symbol_maps_to_its_safe_file_name(tmp_path):
    _write(tmp_path, "5min", "GC_F", _bars("5min"))
    assert list(load_frames("GC=F", base_dir=str(tmp_path)).frames) == ["5min"]


def test_the_loader_creates_no_folders(tmp_path):
    load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_frameset_is_frozen():
    fs = FrameSet(frames={}, missing=(), unreadable=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        fs.missing = ("5min",)
```

- [ ] **Step 2: Write the journal and script tests**

In `tests/analytics/test_journal.py`:

1. Add imports at the top: `import pandas as pd`, `import pytest`, `from swingbot.core.analytics.excursion_frames import FrameSet` and `from swingbot.core.analytics.mfe_mae import INTRADAY_SOURCES`.
2. In `test_build_entry_rule1_loss_stopped_after_running`, `test_build_entry_rule2_win_clean_capture` and `test_build_entry_rule4_scratch_no_followthrough`, change `build_entry(t, df)` to `build_entry(t, {"daily": df})`; in rule 1 add `assert e["excursion_source"] == "daily"`.
3. In `test_build_entry_fallback_and_df_none_is_safe` add `assert e["excursion_source"] is None`.
4. In `test_journal_trade_close_adds_entry`, wrap the call in a second patch so the test never reads the checkout's `market_data/`:
   `with patch("swingbot.core.marketdata.data.get_daily_data", return_value=df), patch("swingbot.core.analytics.excursion_frames.load_frames", return_value=FrameSet({"daily": df}, INTRADAY_SOURCES, ())):` and add `assert store.get("t1")["excursion_source"] == "daily"`.
5. In `test_journal_trade_close_never_raises_on_fetch_failure`, add the same second patch with `return_value=FrameSet({}, INTRADAY_SOURCES, ())` and keep the `mfe_r is None` assertion; add `assert store.get("t1")["excursion_source"] is None`.
6. Append:

```python
def _five_minute_day(day="2026-03-02"):
    idx = pd.date_range(f"{day} 14:30", f"{day} 20:55", freq="5min")
    return pd.DataFrame({"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0,
                         "Volume": 1000.0}, index=idx)


def _same_day_loss():
    return _base_trade(status="loss", exit_price=96.0,
                       opened_at="2026-03-02T15:02:00+00:00", closed_at="2026-03-02T15:31:00+00:00")


def test_build_entry_records_the_finest_source_and_derives_the_lesson_from_it():
    daily = make_ohlcv([100, 104, 99], spread_pct=0.0, start="2026-03-02")
    e = build_entry(_same_day_loss(), {"daily": daily, "5min": _five_minute_day()})
    assert e["excursion_source"] == "5min"
    assert (e["mfe_r"], e["mae_r"]) == (0.125, 1.0)
    assert e["auto_lesson"] == "Entry was wrong from the first bar — review the trigger, not the exit."
    assert list(e).index("excursion_source") == list(e).index("exit_efficiency") + 1


def test_build_entry_with_an_empty_mapping_is_safe():
    e = build_entry(_same_day_loss(), {})
    assert e["mfe_r"] is None and e["excursion_source"] is None and e["note"] == ""


def test_build_entry_rejects_a_bare_dataframe():
    with pytest.raises(TypeError, match="frames mapping"):
        build_entry(_same_day_loss(), make_ohlcv([100, 101], start="2026-03-02"))


def test_journal_trade_close_records_the_archive_source():
    t = dict(_same_day_loss(), id="t5")
    fs = FrameSet({"5min": _five_minute_day(), "daily": make_ohlcv([100], start="2026-03-02")}, (), ())
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=None), \
            patch("swingbot.core.analytics.excursion_frames.load_frames", return_value=fs) as loader:
        journal_trade_close(t)
    assert loader.call_args.args == ("AAPL",) and "daily" in loader.call_args.kwargs
    assert JournalStore().get("t5")["excursion_source"] == "5min"


def test_journal_trade_close_falls_back_to_daily_when_the_archive_read_fails():
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    with patch("swingbot.core.marketdata.data.get_daily_data", return_value=df), \
            patch("swingbot.core.analytics.excursion_frames.load_frames", side_effect=OSError("disk")):
        journal_trade_close(_closed_trade())
    entry = JournalStore().get("t1")
    assert entry["excursion_source"] == "daily" and entry["mfe_r"] == 2.0


def test_backfill_hands_the_frames_mapping_to_build_entry():
    store = JournalStore()
    trade = {"id": "bf1", "ticker": "MSFT", "status": "loss", "direction": "bearish",
             "entry": 50.0, "stop_loss": 52.0, "exit_price": 52.0,
             "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-03T15:00:00+00:00"}
    daily = make_ohlcv([50.0, 51.0], spread_pct=1.0, start="2026-03-02")
    assert backfill([trade], store, lambda ticker: {"daily": daily}) == (1, 0)
    assert store.get("bf1")["excursion_source"] == "daily"
```

Check `_same_day_loss` by hand: entry 100, stop 96 (risk 4), bars 100.5/99.5, exit 96 → r −1.0; mfe = max(0.5/4, 0, −1) = 0.125; mae = max(0.125, 1.0) = 1.0 → lesson rule 3 (loss, mae ≥ 1.0, mfe < 0.2).

In `tests/analytics/test_journal_risk_features.py`, in the first test (`e = build_entry(_trade(), None)`, line 18) add `assert e["excursion_source"] is None`.

In `tests/tracking/test_origin.py`, after line 73 add `assert build_entry(trade, None)["excursion_source"] is None`.

In `tests/scripts/test_rejournal_fill_mismatch.py`, in `test_only_exit_derived_fields_are_replaced` add `"excursion_source": "5min"` to `rebuilt`, `"excursion_source": "daily"` to `old`, and assert `new["excursion_source"] == "5min"`; append:

```python
def test_excursion_source_is_an_exit_field():
    assert "excursion_source" in rj.EXIT_FIELDS
```

- [ ] **Step 3: Run to see them fail**

Run: `python scripts/dev/testrun.py file tests/excursion/test_excursion_frames.py`
Expected: `ModuleNotFoundError: No module named 'swingbot.core.analytics.excursion_frames'`.
Run: `python scripts/dev/testrun.py file tests/analytics/test_journal.py`
Expected: import error for `excursion_frames` (then, once it exists, `KeyError: 'excursion_source'`).

- [ ] **Step 4: Create `swingbot/core/analytics/excursion_frames.py`**

```python
"""v228: one ticker's archived bars for compute_excursion, finest first.

Reads market_data/{5min,15min,hourly}/<SYMBOL>.csv through
data_store.load_normalized (naive-UTC bar starts, pinned by
tests/marketdata/test_archive_time_basis.py) and tells a file that does not
exist (`missing`) from one that cannot be used (`unreadable`, e.g. mixed UTC
offsets), so the upgrade report never counts either as "no coverage".
Never creates a folder (data_store.cache_path would)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from swingbot.core.analytics.mfe_mae import INTRADAY_SOURCES
from swingbot.core.marketdata.data_store import DATA_DIR, load_normalized, safe_symbol


@dataclass(frozen=True)
class FrameSet:
    frames: dict[str, pd.DataFrame]
    missing: tuple[str, ...]
    unreadable: tuple[str, ...]


def _read(ticker: str, name: str, base_dir: str) -> tuple[str, pd.DataFrame | None]:
    if not ticker or not os.path.isfile(os.path.join(base_dir, name, f"{safe_symbol(ticker)}.csv")):
        return "missing", None
    df = load_normalized(ticker, name, base_dir=base_dir)
    return ("unreadable", None) if df is None else ("ok", df)


def load_frames(ticker: str, *, daily: pd.DataFrame | None = None,
                daily_from_archive: bool = False, base_dir: str = DATA_DIR) -> FrameSet:
    """Intraday archives in INTRADAY_SOURCES order, then the daily frame:
    the one passed in when it holds bars, else (daily_from_archive) the
    market_data/daily archive."""
    has_daily = daily is not None and not daily.empty
    names = INTRADAY_SOURCES + (("daily",) if daily_from_archive and not has_daily else ())
    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    unreadable: list[str] = []
    for name in names:
        state, df = _read(ticker, name, base_dir)
        if state == "ok":
            frames[name] = df
        else:
            (missing if state == "missing" else unreadable).append(name)
    if has_daily:
        frames["daily"] = daily
    return FrameSet(frames, tuple(missing), tuple(unreadable))
```

- [ ] **Step 5: Change `journal.py`**

Replace line 13 `from swingbot.core.analytics.mfe_mae import compute_mfe_mae` with:

```python
from collections.abc import Mapping

import pandas as pd

from swingbot.core.analytics.mfe_mae import compute_excursion
```

(put `from collections.abc import Mapping` with the stdlib imports above, `import pandas as pd` after them.) Replace the first lines of `build_entry` up to `exit_efficiency = ...`:

```python
def build_entry(trade: dict, frames: Mapping[str, pd.DataFrame | None] | None) -> dict:
    """One journal entry. `frames` is the {timeframe: bars} mapping from
    excursion_frames.load_frames (v228); the excursion comes from the finest
    frame that covers the trade and `excursion_source` names it."""
    if isinstance(frames, pd.DataFrame):
        raise TypeError("build_entry takes a frames mapping (v228); wrap a daily frame as {'daily': df}")
    m = compute_excursion(trade, frames) if frames else None
    mfe_r = m["mfe_r"] if m else None
    mae_r = m["mae_r"] if m else None
    exit_efficiency = m["exit_efficiency"] if m else None
```

and in the returned dict, directly after `"exit_efficiency": exit_efficiency,` add `"excursion_source": m["excursion_source"] if m else None,`. Nothing else in the dict changes (`"note": ""` stays: this builder is for new entries; V228-5 never calls it).

Replace `journal_trade_close`'s body with:

```python
    daily = None
    try:
        from swingbot.core.marketdata.data import get_daily_data
        daily = get_daily_data(trade["ticker"])
    except Exception:
        log.warning("journal_trade_close: bars fetch failed for %s -- journaling without MFE/MAE",
                    trade.get("ticker"), exc_info=True)

    try:
        from swingbot.core.analytics.excursion_frames import load_frames
        frames = load_frames(trade.get("ticker") or "", daily=daily).frames
    except Exception:
        log.warning("journal_trade_close: archive read failed for %s -- daily bars only",
                    trade.get("ticker"), exc_info=True)
        frames = {"daily": daily} if daily is not None else None

    try:
        entry = build_entry(trade, frames)
        JournalStore().add(entry)
    except Exception:
        log.warning("journal_trade_close: failed to journal trade %s", trade.get("id"), exc_info=True)
```

Keep its docstring; append one sentence: "v228: the excursion is measured on the finest archived frame that covers the trade; at close the sub-hourly archives are usually a day stale, so most entries start as `daily` and excursion_upgrade raises them later."

- [ ] **Step 6: Change both scripts**

`scripts/data/backfill_journal.py`: rename the existing `_fetch_with_cache_fallback` to `_daily_with_cache_fallback` (body unchanged) and add below it:

```python
def _fetch_with_cache_fallback(ticker: str) -> dict:
    """v228: every frame build_entry can use -- the 5min/15min/hourly
    archives under market_data/, then the daily bars (live fetch, else the
    backtest cache)."""
    from swingbot.core.analytics.excursion_frames import load_frames
    return load_frames(ticker, daily=_daily_with_cache_fallback(ticker)).frames
```

In `backfill`, replace `df = fetch_fn(t["ticker"])` / `entry = build_entry(t, df)` with `entry = build_entry(t, fetch_fn(t["ticker"]))`, and in its docstring say `fetch_fn(ticker)` returns a frames mapping (or None). `main` keeps passing `_fetch_with_cache_fallback`.

`scripts/ops/rejournal_fill_mismatch.py`: add `"excursion_source"` to `EXIT_FIELDS` (after `"exit_efficiency"`). In `main`, import `from swingbot.core.analytics.excursion_frames import load_frames` beside the other imports and replace `new = merge_entry(build_entry(t, df), old)` with:

```python
        frames = load_frames(t["ticker"], daily=df).frames
        new = merge_entry(build_entry(t, frames), old)
```

and add `"excursion_source"` to the tuple of keys the dry-run diff prints (`("r_realized", "outcome", "closed_at", "exit_efficiency")`).

- [ ] **Step 7: Run the tests**

Run each; expected all pass:
`python scripts/dev/testrun.py file tests/excursion/test_excursion_frames.py`
`python scripts/dev/testrun.py file tests/analytics/test_journal.py`
`python scripts/dev/testrun.py file tests/analytics/test_journal_risk_features.py`
`python scripts/dev/testrun.py file tests/tracking/test_origin.py`
`python scripts/dev/testrun.py file tests/scripts/test_rejournal_fill_mismatch.py`
`python scripts/dev/testrun.py file tests/excursion/test_compute_excursion.py`

Then `python -m radon cc -s -n C swingbot/core/analytics/excursion_frames.py swingbot/core/analytics/journal.py scripts/data/backfill_journal.py scripts/ops/rejournal_fill_mismatch.py` — only the baseline rows `journal:tags_for` and `journal:_auto_lesson` may appear, at their baseline values; `build_entry` stays under 11. `python scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/analytics/excursion_frames.py swingbot/core/analytics/journal.py scripts/data/backfill_journal.py scripts/ops/rejournal_fill_mismatch.py tests/excursion/test_excursion_frames.py tests/analytics/test_journal.py tests/analytics/test_journal_risk_features.py tests/tracking/test_origin.py tests/scripts/test_rejournal_fill_mismatch.py
git commit -m "feat(v228): load_frames and excursion_source in every new journal entry; re-journal scripts pass frames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

