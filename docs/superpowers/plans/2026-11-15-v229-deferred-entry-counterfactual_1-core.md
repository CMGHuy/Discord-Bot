# v229 — Deferred-entry counterfactual: Part 1 — core (V229-1..V229-3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-3" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Index:** [2026-11-15-v229-deferred-entry-counterfactual_0-index.md](2026-11-15-v229-deferred-entry-counterfactual_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger, the shared PAIR shape and the `## Handoff` resolutions live there and bind every task below.

Scope of this part: the time basis (`bars.py`), the single-leg race on
5-minute bars (`simulate.py`), the three arms with frictions (`arms.py`), the
tradeability record and event flags (`tradeability.py`), and the export
reader, population funnel and pair assembly (`pairs.py`). Part 1 is split at
the 1500-line cap: V229-1..V229-3 are here, V229-4..V229-5 in
`2026-11-15-v229-deferred-entry-counterfactual_1b-assembly.md`. All modules live in
`scripts/reports/deferred_entry/`; all tests in `tests/scripts/` (suite
`tooling`). No database, no network: earnings lookups are injected in tests.

Common test import (every test file in this part): the package is imported as
`deferred_entry.<module>` after putting `scripts/reports` on `sys.path`,
exactly like `tests/scripts/test_giveback_live_counterfactual.py` does for
its script.

# Phase 1 — time basis and simulator

### Task V229-1: Package and time basis

**Model:** sonnet — new module with timezone and calendar logic, fully specified, one real-file capture.

**Files:**
- Create: `scripts/reports/deferred_entry/__init__.py`
- Create: `scripts/reports/deferred_entry/bars.py`
- Create: `tests/scripts/v229_fixtures.py`
- Create: `tests/scripts/test_deferred_entry_bars.py`
- Create: `tests/fixtures/v229/5min/AAPL.csv` (read-only copy of two VM archive sessions)
- Modify: `scripts/dev/select_tests.py` (two `DATA_READERS` rows, inserted directly above the `("data/market_data/", ...)` row near the end of the table)

**Interfaces:**
- Consumes: `swingbot.core.market.session` (`RTH_OPEN`, `is_early_close(d)`, `session_close(d) -> time`, `nyse_calendar()` with `is_session`, `session_after(d, n)`), `swingbot.core.marketdata.data_store.safe_symbol(ticker)`.
- Produces (fixed in the index ledger; later tasks rely on these exact names):
  - `bars.ET` (`ZoneInfo("America/New_York")`), `bars.DEFER_AT = dt.time(15, 30)`, `bars.BAR_MINUTES = 5`, `bars.COLUMNS = ("Open", "High", "Low", "Close", "Volume")`
  - `class ArchiveError(ValueError)`
  - `load_bars(bars_dir, ticker) -> pd.DataFrame | None` — float OHLCV, tz-aware UTC index of bar **starts**, sorted, de-duplicated, **regular NYSE session bars only** (09:30 <= ET time < that day's close); `None` when the file is missing; `ArchiveError` when unreadable, missing a column, or carrying a naive stamp.
  - `to_utc(text) -> pd.Timestamp` (UTC; `ValueError` on blank or unparseable)
  - `et_date(ts) -> dt.date`, `et_time(ts) -> dt.time`
  - `session_open(d) -> pd.Timestamp` (09:30 ET in UTC), `session_close_utc(d) -> pd.Timestamp` (that day's official close in UTC; 13:00 ET on a half day)
  - `deferral_start(d) -> pd.Timestamp | None` (15:30 ET in UTC; `None` on a half day or a non-session day)
  - `horizon_end(d, sessions=5) -> pd.Timestamp | None` (UTC close of `nyse_calendar().session_after(d, sessions)`; `None` past the calendar)
  - `archive_last_bar(bars_dir) -> str | None` (ISO UTC of the latest last-line stamp over `*.csv` in the directory)
  - Test helper `tests/scripts/v229_fixtures.py`: `et(text) -> pd.Timestamp` (ET wall clock `"YYYY-MM-DD HH:MM"` as a UTC stamp), `session_stamps(day) -> list[pd.Timestamp]`, `five_min(days, *, base=100.0, overrides=None) -> pd.DataFrame` (regular-session 5-minute bars for every NYSE session in `days`; `Open=Close=base`, `High=base+0.05`, `Low=base-0.05`, `Volume=1000`; `overrides` maps an ET `"YYYY-MM-DD HH:MM"` key to `(open, high, low, close)`), `write_bars(directory, ticker, frame) -> Path`.

**Why the archive is read here and not through `data_store`:** `load_normalized` drops the timezone and `cache_path` creates directories on a read path (Global Constraints). The archive stamps each bar with its **start** and carries an explicit UTC offset; the real-file test pins both on one EDT and one EST session. Pre- and post-market bars, if the archive holds any, are dropped by `load_bars`: every arm races the regular session only, and a bar at 09:30 ET is a session open (the simulator's gap rule relies on it).

- [ ] **Step 1: Capture the real archive slice (read-only production access)**

The archive exists only on the VM. Copy the header and the two sessions 2026-10-30 (EDT) and 2026-11-03 (EST) of `AAPL.csv`, never writing on the VM:

```bash
mkdir -p tests/fixtures/v229/5min
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && head -1 market_data/5min/AAPL.csv && grep -E '^2026-(10-30|11-03)' market_data/5min/AAPL.csv" > tests/fixtures/v229/5min/AAPL.csv
python -c "import pathlib; t = pathlib.Path('tests/fixtures/v229/5min/AAPL.csv').read_text().splitlines(); print(len(t), t[0]); print(t[1]); print(t[-1])"
```

Expected: about 157 lines (header plus 78 bars per session, more if the archive keeps extended hours); the first regular bar of 2026-10-30 is stamped `2026-10-30 13:30:00+00:00`. **If it is stamped `13:35:00+00:00` (bar end) or the stamps carry no offset, stop and report `BLOCKED: archive stamps are not bar-start UTC` — the spec's time basis would be wrong.**

- [ ] **Step 2: Write the fixture helper**

Create `tests/scripts/v229_fixtures.py`:

```python
"""v229: synthetic 5-minute archive frames, stamped like the VM archive --
bar START, tz-aware UTC, regular NYSE session only."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.marketdata.data_store import safe_symbol

PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


def et(text: str) -> pd.Timestamp:
    """An ET wall-clock 'YYYY-MM-DD HH:MM' as its UTC bar-start stamp."""
    return pd.Timestamp(text, tz=US_MARKET_TZ).tz_convert("UTC")


def _as_date(day) -> dt.date:
    return day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))


def session_stamps(day) -> list[pd.Timestamp]:
    """Every 5-minute bar start of one session, 09:30 ET to its close."""
    day = _as_date(day)
    start = pd.Timestamp(dt.datetime.combine(day, RTH_OPEN), tz=US_MARKET_TZ)
    end = pd.Timestamp(dt.datetime.combine(day, session_close(day)), tz=US_MARKET_TZ)
    return list(pd.date_range(start, end, freq="5min", inclusive="left").tz_convert("UTC"))


def five_min(days, *, base: float = 100.0, overrides: dict | None = None) -> pd.DataFrame:
    """Flat regular-session bars for every NYSE session in ``days``.

    ``overrides`` maps an ET 'YYYY-MM-DD HH:MM' bar start to
    (open, high, low, close); a key that is not a bar start is a KeyError."""
    cal = nyse_calendar()
    stamps = [ts for d in map(_as_date, days) if cal.is_session(d) for ts in session_stamps(d)]
    frame = pd.DataFrame(
        {"Open": base, "High": base + 0.05, "Low": base - 0.05, "Close": base, "Volume": 1000.0},
        index=pd.DatetimeIndex(stamps, name="Datetime"))
    for key, values in (overrides or {}).items():
        ts = et(key)
        if ts not in frame.index:
            raise KeyError(f"{key} ET is not a bar start in this frame")
        frame.loc[ts, PRICE_COLUMNS] = [float(v) for v in values]
    return frame


def write_bars(directory, ticker: str, frame: pd.DataFrame) -> Path:
    """Write ``frame`` as the archive would: <dir>/<SAFE>.csv, stamps with +00:00."""
    path = Path(directory) / f"{safe_symbol(ticker)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path)
    return path
```

- [ ] **Step 3: Write the failing tests**

Create `tests/scripts/test_deferred_entry_bars.py`:

```python
"""V229-1: the time basis -- archive parsing, 15:30 ET across DST, half days,
the five-session horizon and the archive's last bar."""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import bars  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min, write_bars  # noqa: E402

REAL_DIR = ROOT / "tests" / "fixtures" / "v229" / "5min"
UTC = "UTC"


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 10, 30), "2026-10-30 19:30"),  # EDT: UTC-4
    (dt.date(2026, 11, 2), "2026-11-02 20:30"),   # EST after the 2026-11-01 change
    (dt.date(2026, 3, 6), "2026-03-06 20:30"),    # EST before the 2026-03-08 change
    (dt.date(2026, 3, 9), "2026-03-09 19:30"),    # EDT after it
])
def test_deferral_start_moves_with_daylight_saving(day, expected):
    assert bars.deferral_start(day) == pd.Timestamp(expected, tz=UTC)


@pytest.mark.parametrize("day", [dt.date(2026, 11, 27),   # half day after Thanksgiving
                                 dt.date(2026, 11, 26),   # Thanksgiving
                                 dt.date(2026, 11, 7)])   # Saturday
def test_no_deferral_start_on_half_days_and_closed_days(day):
    assert bars.deferral_start(day) is None


def test_session_open_and_close_in_utc():
    assert bars.session_open(dt.date(2026, 11, 3)) == pd.Timestamp("2026-11-03 14:30", tz=UTC)
    assert bars.session_close_utc(dt.date(2026, 11, 3)) == pd.Timestamp("2026-11-03 21:00", tz=UTC)
    assert bars.session_close_utc(dt.date(2026, 11, 27)) == pd.Timestamp("2026-11-27 18:00", tz=UTC)


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 11, 3), "2026-11-10 21:00"),   # 4, 5, 6, 9, 10
    (dt.date(2026, 11, 23), "2026-12-01 21:00"),  # skips Thanksgiving, counts the half day
    (dt.date(2026, 11, 19), "2026-11-27 18:00"),  # the fifth session IS the half day
])
def test_horizon_end_is_the_close_of_the_fifth_session_after(day, expected):
    assert bars.horizon_end(day) == pd.Timestamp(expected, tz=UTC)


def test_horizon_end_past_the_calendar_is_none():
    assert bars.horizon_end(dt.date(2030, 12, 30)) is None


def test_to_utc_reads_the_export_text_and_refuses_blanks():
    assert bars.to_utc("2026-10-30 14:35:12.123+00") == pd.Timestamp("2026-10-30 14:35:12.123", tz=UTC)
    for bad in ("", "   ", None, "not a time"):
        with pytest.raises(ValueError):
            bars.to_utc(bad)


def test_et_date_and_time_convert_from_utc():
    ts = pd.Timestamp("2026-11-04 02:30", tz=UTC)  # 21:30 ET on the 3rd
    assert bars.et_date(ts) == dt.date(2026, 11, 3)
    assert bars.et_time(ts) == dt.time(21, 30)


def test_load_bars_round_trips_a_synthetic_archive(tmp_path):
    write_bars(tmp_path, "AAPL", five_min(["2026-11-03"]))
    out = bars.load_bars(tmp_path, "AAPL")
    assert list(out.columns) == list(bars.COLUMNS)
    assert str(out.index.tz) == UTC
    assert out.index[0] == et("2026-11-03 09:30") and out.index[-1] == et("2026-11-03 15:55")
    assert len(out) == 78


def test_load_bars_missing_file_is_none_and_safe_symbol_is_used(tmp_path):
    assert bars.load_bars(tmp_path, "MSFT") is None
    write_bars(tmp_path, "GC=F", five_min(["2026-11-03"]))
    assert (tmp_path / "GC_F.csv").is_file()
    assert bars.load_bars(tmp_path, "GC=F") is not None


def test_load_bars_drops_extended_hours_and_sorts(tmp_path):
    frame = five_min(["2026-11-03"])
    extra = frame.iloc[:1].copy()
    extra.index = pd.DatetimeIndex([et("2026-11-03 08:00")], name="Datetime")
    write_bars(tmp_path, "AAPL", pd.concat([frame.iloc[::-1], extra]))
    out = bars.load_bars(tmp_path, "AAPL")
    assert out.index.is_monotonic_increasing
    assert out.index[0] == et("2026-11-03 09:30") and len(out) == 78


def test_load_bars_refuses_naive_stamps_and_missing_columns(tmp_path):
    (tmp_path / "NAIVE.csv").write_text(
        "Datetime,Open,High,Low,Close,Volume\n2026-11-03 14:30:00,1,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(bars.ArchiveError, match="offset"):
        bars.load_bars(tmp_path, "NAIVE")
    (tmp_path / "COLS.csv").write_text(
        "Datetime,Open,High\n2026-11-03 14:30:00+00:00,1,1\n", encoding="utf-8")
    with pytest.raises(bars.ArchiveError, match="Low"):
        bars.load_bars(tmp_path, "COLS")


def test_real_archive_file_carries_utc_offsets_and_bar_start_stamps():
    raw = (REAL_DIR / "AAPL.csv").read_text(encoding="utf-8").splitlines()
    assert raw[1].split(",", 1)[0].endswith("+00:00")
    out = bars.load_bars(REAL_DIR, "AAPL")
    days = [bars.et_date(t) for t in out.index]
    first = {d: out.index[days.index(d)] for d in (dt.date(2026, 10, 30), dt.date(2026, 11, 3))}
    assert first[dt.date(2026, 10, 30)] == pd.Timestamp("2026-10-30 13:30", tz=UTC)  # EDT open
    assert first[dt.date(2026, 11, 3)] == pd.Timestamp("2026-11-03 14:30", tz=UTC)   # EST open
    assert bars.deferral_start(dt.date(2026, 11, 3)) in out.index


def test_archive_last_bar_is_the_latest_last_line(tmp_path):
    write_bars(tmp_path, "AAPL", five_min(["2026-11-03"]))
    write_bars(tmp_path, "MSFT", five_min(["2026-11-03", "2026-11-04"]))
    (tmp_path / "EMPTY.csv").write_text("Datetime,Open,High,Low,Close,Volume\n", encoding="utf-8")
    assert bars.archive_last_bar(tmp_path) == et("2026-11-04 15:55").isoformat()
    assert bars.archive_last_bar(tmp_path / "absent") is None
```

- [ ] **Step 4: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_bars.py`
Expected: collection error, `ModuleNotFoundError: No module named 'deferred_entry'`.

- [ ] **Step 5: Implement the package and `bars.py`**

Create `scripts/reports/deferred_entry/__init__.py`:

```python
"""v229 deferred-entry counterfactual: helpers behind
scripts/reports/deferred_entry_counterfactual.py (spec
docs/superpowers/specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)."""
```

Create `scripts/reports/deferred_entry/bars.py`:

```python
"""v229 time basis. The VM's 5-minute archive stamps each bar with its START
and an explicit UTC offset; the journal export writes UTC text. Both are read
here with UTC parsing -- never through data_store.load_normalized (drops the
zone) or cache_path (creates directories). 15:30 ET is derived per date
through zoneinfo, so it moves with daylight saving."""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market.session import (  # noqa: E402
    RTH_OPEN, is_early_close, nyse_calendar, session_close)
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFER_AT = dt.time(15, 30)
BAR_MINUTES = 5
COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_OFFSET = re.compile(r"(Z|[+-]\d{2}(:?\d{2})?)$")


class ArchiveError(ValueError):
    """An archive file exists but cannot be trusted as bar-start UTC bars."""


def to_utc(text) -> pd.Timestamp:
    """Parse a timestamp as UTC; ValueError on blank or unparseable text."""
    if text is None or not str(text).strip():
        raise ValueError("empty timestamp")
    ts = pd.to_datetime(str(text).strip(), utc=True)
    if pd.isna(ts):
        raise ValueError(f"unparseable timestamp {text!r}")
    return pd.Timestamp(ts)


def et_date(ts) -> dt.date:
    return pd.Timestamp(ts).tz_convert(ET).date()


def et_time(ts) -> dt.time:
    return pd.Timestamp(ts).tz_convert(ET).time()


def _utc_at(d: dt.date, wall: dt.time) -> pd.Timestamp:
    return pd.Timestamp(dt.datetime.combine(d, wall), tz=ET).tz_convert("UTC")


def session_open(d: dt.date) -> pd.Timestamp:
    return _utc_at(d, RTH_OPEN)


def session_close_utc(d: dt.date) -> pd.Timestamp:
    return _utc_at(d, session_close(d))


def deferral_start(d: dt.date) -> pd.Timestamp | None:
    """15:30 ET on ``d`` in UTC; None on a half day or a non-session day."""
    if not nyse_calendar().is_session(d) or is_early_close(d):
        return None
    return _utc_at(d, DEFER_AT)


def horizon_end(d: dt.date, sessions: int = 5) -> pd.Timestamp | None:
    """UTC close of the ``sessions``-th session after ``d``; None past the calendar."""
    last = nyse_calendar().session_after(d, sessions)
    return None if last is None else session_close_utc(last)


def _regular_mask(index: pd.DatetimeIndex) -> np.ndarray:
    local = index.tz_convert(ET)
    cal = nyse_calendar()
    closes = {d: session_close(d) for d in set(local.date) if cal.is_session(d)}
    return np.array([d in closes and RTH_OPEN <= t < closes[d]
                     for d, t in zip(local.date, local.time)], dtype=bool)


def _parse_index(raw: pd.Index, path: Path) -> pd.DatetimeIndex:
    text = raw.astype(str)
    naive = [s for s in text if not _OFFSET.search(s.strip())]
    if naive:
        raise ArchiveError(f"{path}: stamp without a UTC offset, e.g. {naive[0]!r}")
    try:
        return pd.DatetimeIndex(pd.to_datetime(text, utc=True), name="Datetime")
    except (ValueError, TypeError) as exc:
        raise ArchiveError(f"{path}: unparseable stamps ({exc})") from exc


def load_bars(bars_dir, ticker: str) -> pd.DataFrame | None:
    """Regular-session 5-minute bars of ``ticker``, UTC bar starts, sorted.
    None when the file is missing; ArchiveError when it cannot be trusted."""
    path = Path(bars_dir) / f"{safe_symbol(ticker)}.csv"
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0)
    except (OSError, ValueError) as exc:
        raise ArchiveError(f"{path}: unreadable ({exc})") from exc
    missing = [c for c in COLUMNS if c not in frame.columns]
    if missing:
        raise ArchiveError(f"{path}: missing columns {missing}")
    frame = frame[list(COLUMNS)].apply(pd.to_numeric, errors="coerce").astype(float)
    frame.index = _parse_index(frame.index, path)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame[_regular_mask(frame.index)]


def _last_stamp(path: Path) -> pd.Timestamp | None:
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 4096))
        lines = [ln for ln in fh.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return to_utc(lines[-1].split(",", 1)[0])
    except ValueError:
        return None


def archive_last_bar(bars_dir) -> str | None:
    """ISO UTC of the latest last bar over every archive file, or None."""
    root = Path(bars_dir)
    if not root.is_dir():
        return None
    stamps = [s for s in (_last_stamp(p) for p in sorted(root.glob("*.csv"))) if s is not None]
    return max(stamps).isoformat() if stamps else None
```

An empty file yields no lines and returns `None`; a header-only file fails `to_utc("Datetime")` and returns `None`.

- [ ] **Step 6: Add the `DATA_READERS` rows**

In `scripts/dev/select_tests.py`, insert directly above the `# The v162 Alpaca history store (data/market_data/, ...` comment (first match wins; no broader `data/` row exists, so placement only needs to stay inside the tuple and above that row):

```python
    # v229: the deferred-entry pair log (VM-side, appended by the weekly cron)
    # and the real 5-minute archive slice that pins the time basis.
    ("data/v229/", ("tests/scripts/test_deferred_entry_pairlog.py",
                    "tests/scripts/test_deferred_entry_counterfactual.py")),
    ("tests/fixtures/v229/", ("tests/scripts/test_deferred_entry_bars.py",)),
```

The two `data/v229/` targets are created by V229-6 and V229-10; until they exist the selector widens for that path (its documented behaviour for a missing target), which is safe.

- [ ] **Step 7: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_bars.py`
Expected: every test passes, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: `0 failed` (the new rows are well-formed and the fixture path is routed).

Run: `python scripts/dev/complexity_gate.py`
Expected: no new function at or above 15.

- [ ] **Step 8: Commit**

```bash
git add scripts/reports/deferred_entry/__init__.py scripts/reports/deferred_entry/bars.py tests/scripts/v229_fixtures.py tests/scripts/test_deferred_entry_bars.py tests/fixtures/v229/5min/AAPL.csv scripts/dev/select_tests.py
git commit -m "feat(v229): deferred-entry time basis -- archive reader, 15:30 ET, five-session horizon (V229-1)"
```

### Task V229-2: Single-leg race on 5-minute bars

**Model:** opus — the frozen race rule decides every arm's R; parity with the backtest walk and the gap rule must be exact.

**Files:**
- Create: `scripts/reports/deferred_entry/simulate.py`
- Create: `tests/scripts/test_deferred_entry_simulate.py`

**Interfaces:**
- Consumes: V229-1 `bars.et_time`, `tests/scripts/v229_fixtures.py` (`et`, `five_min`); `swingbot.core.backtesting.instrument.fills.gap_stop_fill(bar_open, level, direction)` (bullish `min(open, level)`, bearish `max(open, level)`); `swingbot.core.market.session.RTH_OPEN`; `swingbot.core.market.strategy_types.BREAKEVEN_TRIGGER_FRACTION` (0.5).
- Produces (index ledger):
  - `SIGN = {"bullish": 1, "bearish": -1}`, `OUTCOMES = ("win", "loss", "scratch", "timeout", "no_bars")`
  - `@dataclass(frozen=True) Race(outcome: str, exit_price: float | None, exit_ts: pd.Timestamp | None, gap_stop: bool, stop_moved: bool)`
  - `race(bars, *, direction, fill, stop, tp1, start, end, be_fraction=BREAKEVEN_TRIGGER_FRACTION) -> Race` — races the bars with `start <= index < end`; `direction` is `"bullish"`/`"bearish"` (anything else is a `ValueError`).
  - `gross_r(race, *, direction, fill, risk) -> float` — `sign * (exit_price - fill) / risk`; `0.0` when `exit_price` is None; `ValueError` when `risk <= 0`.

**The frozen rule (spec § Race rule; index Global Constraints "Race"):** mirror of `swingbot/core/planning/exit_sim.py:_single_leg_exit_walk` on 5-minute bars. Per bar, in this order: (1) the current stop (the original stop, or the fill once moved) is checked first — a hit fills at `gap_stop_fill(bar_open, stop, direction)`, outcome `scratch` if the stop had moved, else `loss`; (2) TP1 — a hit is `win` at exactly TP1 (no gap-target improvement, as the walk); (3) the breakeven trigger (`fill + sign * be_fraction * |tp1 - fill|`) — reaching it moves the stop to the fill for **later bars only**. With no exit before `end`, the outcome is `timeout` at the last raced bar's close. `gap_stop` is True only when the hit bar is a session open (ET 09:30; `load_bars` keeps regular-session bars only) and the fill is the open, beyond the stop (Handoff 5). A mid-session open beyond the stop still fills at the open, without the flag. The walk's v129 acceptance exit is not part of the frozen rule (inert in the walk when the plan has no acceptance level).

The bearish branch is table-driven through `SIGN` (adverse extreme = low for a long, high for a short), so one loop serves both directions and stays well under complexity 15.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_simulate.py`:

```python
"""V229-2: the single-leg race -- stop before target, breakeven protecting
later bars only, the five-session mark, gap fills, and parity with the
backtest's round-1 walk on a no-gap path."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import bars as tb  # noqa: E402
from deferred_entry import simulate as sim  # noqa: E402
from swingbot.core.planning.exit_sim import _single_leg_exit_walk  # noqa: E402
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

DAY = "2026-11-03"
LONG = dict(direction="bullish", fill=100.0, stop=98.0, tp1=104.0)  # trigger at 102
SHORT = dict(direction="bearish", fill=100.0, stop=102.0, tp1=96.0)
END = et("2026-11-03 16:00")


def _race(frame, start="2026-11-03 10:05", end=END, **levels):
    return sim.race(frame, start=et(start), end=end, **(levels or LONG))


def test_stop_is_checked_before_target_inside_one_bar():
    frame = five_min([DAY], overrides={f"{DAY} 10:30": (100.0, 104.5, 97.9, 100.0)})
    out = _race(frame)
    assert (out.outcome, out.exit_price, out.exit_ts) == ("loss", 98.0, et(f"{DAY} 10:30"))
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(-1.0)


def test_target_reached_is_a_win_at_tp1():
    frame = five_min([DAY], overrides={f"{DAY} 10:30": (101.0, 105.0, 100.9, 104.5)})
    out = _race(frame)
    assert (out.outcome, out.exit_price) == ("win", 104.0)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(2.0)


def test_breakeven_move_protects_later_bars_only():
    frame = five_min([DAY], overrides={
        f"{DAY} 10:30": (100.5, 102.3, 99.5, 102.0),   # reaches 102, dips below the fill
        f"{DAY} 10:35": (101.0, 101.2, 99.8, 100.0)})  # the moved stop is hit here
    out = _race(frame)
    assert out.outcome == "scratch" and out.stop_moved
    assert out.exit_ts == et(f"{DAY} 10:35") and out.exit_price == 100.0
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == 0.0


def test_timeout_marks_to_the_close_of_the_fifth_session_after_entry():
    days = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
            "2026-11-09", "2026-11-10", "2026-11-11"]
    frame = five_min(days, overrides={"2026-11-10 15:55": (100.0, 100.4, 99.9, 100.3),
                                      "2026-11-11 10:00": (99.0, 99.0, 90.0, 91.0)})
    out = _race(frame, end=tb.horizon_end(pd.Timestamp(DAY).date()))
    assert out.outcome == "timeout"
    assert out.exit_ts == et("2026-11-10 15:55") and out.exit_price == 100.3


def test_gap_through_the_stop_at_a_session_open_fills_at_the_open():
    frame = five_min([DAY, "2026-11-04"],
                     overrides={"2026-11-04 09:30": (97.0, 97.5, 96.5, 97.2)})
    out = _race(frame, end=et("2026-11-04 16:00"))
    assert (out.outcome, out.exit_price, out.gap_stop) == ("loss", 97.0, True)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(-1.5)


def test_a_mid_session_open_through_the_stop_fills_at_the_open_without_the_gap_flag():
    frame = five_min([DAY], overrides={f"{DAY} 11:00": (97.5, 97.8, 97.0, 97.6)})
    out = _race(frame)
    assert (out.outcome, out.exit_price, out.gap_stop) == ("loss", 97.5, False)


def test_bars_before_start_and_at_end_are_not_raced():
    frame = five_min([DAY], overrides={f"{DAY} 10:00": (99.0, 99.0, 97.0, 98.5),
                                       f"{DAY} 15:00": (99.0, 99.0, 97.0, 98.5)})
    out = _race(frame, start="2026-11-03 10:05", end=et(f"{DAY} 15:00"))
    assert out.outcome == "timeout" and out.exit_ts == et(f"{DAY} 14:55")


@pytest.mark.parametrize("bar, outcome, price, r", [
    ((100.0, 102.2, 99.9, 101.0), "loss", 102.0, -1.0),
    ((99.0, 99.1, 95.8, 96.0), "win", 96.0, 2.0),
])
def test_bearish_mirror(bar, outcome, price, r):
    frame = five_min([DAY], overrides={f"{DAY} 10:30": bar})
    out = _race(frame, **SHORT)
    assert (out.outcome, out.exit_price) == (outcome, price)
    assert sim.gross_r(out, direction="bearish", fill=100.0, risk=2.0) == pytest.approx(r)


def test_no_bars_in_the_window():
    out = _race(five_min([DAY]), start="2026-11-03 16:30", end=et("2026-11-03 17:00"))
    assert out == sim.Race("no_bars", None, None, False, False)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == 0.0
    assert sim.race(None, start=et(f"{DAY} 10:00"), end=END, **LONG).outcome == "no_bars"


def test_unknown_direction_and_zero_risk_are_refused():
    with pytest.raises(ValueError, match="direction"):
        _race(five_min([DAY]), direction="long", fill=100.0, stop=98.0, tp1=104.0)
    with pytest.raises(ValueError, match="risk"):
        sim.gross_r(sim.Race("loss", 98.0, None, False, False),
                    direction="bullish", fill=100.0, risk=0.0)


def _plan():
    return TradePlanV2(
        plan_id="p", ticker="XYZ", created_at=DAY, source="confluence",
        strategy="S/R Confluence", horizon_key="4w", direction="bullish", entry_type="stop_entry",
        trigger_price=100.0, entry_price=None, expiry_bars=5, stop_loss=98.0, tp1=104.0,
        tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, acceptance_level=None)


@pytest.mark.parametrize("overrides", [
    {f"{DAY} 10:30": (99.0, 99.2, 97.5, 98.0)},                                    # loss
    {f"{DAY} 10:30": (101.0, 104.2, 100.9, 104.0)},                                # win
    {f"{DAY} 10:30": (100.5, 102.3, 99.5, 102.0), f"{DAY} 10:35": (101.0, 101.2, 99.8, 100.0)},
    {},                                                                            # timeout
])
def test_parity_with_the_backtest_round_one_walk_on_a_no_gap_path(overrides):
    frame = five_min([DAY], overrides=overrides)
    k = list(frame.index).index(et(f"{DAY} 10:00"))
    walk = _single_leg_exit_walk(frame, k, 100.0, _plan(), len(frame))
    out = sim.race(frame, start=frame.index[k + 1], end=END, **LONG)
    assert out.outcome == walk.outcome
    assert out.exit_price == pytest.approx(walk.legs[0]["exit_price"])
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_simulate.py`
Expected: collection error, `ImportError: cannot import name 'simulate' from 'deferred_entry'`.

- [ ] **Step 3: Implement `simulate.py`**

Create `scripts/reports/deferred_entry/simulate.py`:

```python
"""v229 single-leg race on 5-minute bars (spec § Race rule, frozen).

The round-1 rule of swingbot/core/planning/exit_sim.py:_single_leg_exit_walk
(private, daily bars, a TradePlanV2), mirrored here on 5-minute bars: stop
before target within a bar; the stop moves to the fill once price reaches
be_fraction of the TP1 distance and protects LATER bars only; win at TP1,
loss at the stop, scratch at the moved stop; still open at `end` -> marked to
the last raced bar's close. Added on top of the walk: every stop hit fills
through gap_stop_fill, so a session-open gap through the stop fills at the
open. No runner, no TP2 -- the live scale-out is not reproduced."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingbot.core.backtesting.instrument.fills import gap_stop_fill
from swingbot.core.market.session import RTH_OPEN
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION

from .bars import et_time

SIGN = {"bullish": 1, "bearish": -1}
OUTCOMES = ("win", "loss", "scratch", "timeout", "no_bars")


@dataclass(frozen=True)
class Race:
    outcome: str
    exit_price: float | None
    exit_ts: pd.Timestamp | None
    gap_stop: bool
    stop_moved: bool


NO_BARS = Race("no_bars", None, None, False, False)


def _sign(direction: str) -> int:
    try:
        return SIGN[direction]
    except KeyError:
        raise ValueError(f"unknown direction {direction!r}; expected bullish or bearish") from None


def _window(bars, start, end) -> pd.DataFrame | None:
    if bars is None or bars.empty:
        return None
    window = bars[(bars.index >= start) & (bars.index < end)]
    return None if window.empty else window


def _stop_exit(ts, bar_open: float, level: float, direction: str, moved: bool) -> Race:
    price = float(gap_stop_fill(bar_open, level, direction))
    gapped = price != level and et_time(ts) == RTH_OPEN
    return Race("scratch" if moved else "loss", price, ts, gapped, moved)


def race(bars, *, direction: str, fill: float, stop: float, tp1: float, start, end,
         be_fraction: float = BREAKEVEN_TRIGGER_FRACTION) -> Race:
    """Race one plan over the bars with ``start <= index < end``."""
    sign = _sign(direction)
    window = _window(bars, start, end)
    if window is None:
        return NO_BARS
    trigger = fill + sign * be_fraction * abs(tp1 - fill)
    moved = False
    rows = zip(window.index, window["Open"], window["High"], window["Low"])
    for ts, bar_open, high, low in rows:
        adverse, favour = (low, high) if sign > 0 else (high, low)
        level = fill if moved else stop
        if sign * (adverse - level) <= 0:
            return _stop_exit(ts, float(bar_open), level, direction, moved)
        if sign * (favour - tp1) >= 0:
            return Race("win", float(tp1), ts, False, moved)
        if sign * (favour - trigger) >= 0:
            moved = True
    return Race("timeout", float(window["Close"].iloc[-1]), window.index[-1], False, moved)


def gross_r(result: Race, *, direction: str, fill: float, risk: float) -> float:
    """Frictionless R of a race: sign * (exit - fill) / risk; 0.0 with no exit."""
    if risk <= 0:
        raise ValueError(f"risk must be positive, got {risk}")
    if result.exit_price is None:
        return 0.0
    return _sign(direction) * (result.exit_price - fill) / risk
```

Note the relative import `from .bars import et_time`: the package is always imported as `deferred_entry` (the CLI's own directory, `scripts/reports`, is `sys.path[0]` when it runs; tests insert it). `bars.py` already put the repo root on `sys.path`, so the `swingbot` imports resolve on the VM's `docker compose exec -T bot python scripts/reports/...` run as well.

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_simulate.py`
Expected: every test passes, `0 failed`. If the parity test fails on the timeout row only, check `walk.legs[0]["exit_price"]` is the last bar's close (the walk marks to `close[end]` with `end = n - 1`); do not change the race rule to match a different reading.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new function at or above 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/deferred_entry/simulate.py tests/scripts/test_deferred_entry_simulate.py
git commit -m "feat(v229): single-leg race on 5-minute bars, walk parity and gap fills (V229-2)"
```

### Task V229-3: Arms C, A, B with frictions

**Model:** opus — the arm definitions, the strictly-before skip rule and the single frictions call carry the study's validity.

**Files:**
- Create: `scripts/reports/deferred_entry/arms.py`
- Create: `tests/scripts/test_deferred_entry_arms.py`

**Interfaces:**
- Consumes: V229-2 `simulate.SIGN`, `simulate.Race`, `simulate.race(...)`, `simulate.gross_r(...)`; V229-1 `bars.et_date`, `bars.deferral_start`, `bars.session_close_utc`, `bars.horizon_end`, fixtures `et`, `five_min`; `swingbot.core.backtesting.screen.sides.net_r(entry, price, risk, *, direction, days, slippage_bps=None, entry_bps=None, commission=None)` (direction `"long"`/`"short"`, returns a float for scalar inputs); `swingbot.core.edge.frictions.commission_r()`; `swingbot.config.SLIPPAGE_BPS`.
- Produces (index ledger):
  - `ARMS = ("C", "A", "B")`, `NET_DIRECTION = {"bullish": "long", "bearish": "short"}`, `DEFERRED_BPS_MULT = 2`
  - `class FrictionsError(RuntimeError)`; `assert_frictions() -> None` (raises when `config.SLIPPAGE_BPS <= 0` or `commission_r() <= 0`)
  - `shifted_levels(fill, *, entry, stop, tp1) -> tuple[float, float]` = `(fill - (entry - stop), fill + (tp1 - entry))` (both directions)
  - `held_touched(bars, *, direction, stop, start, deferral) -> bool` — any bar with `start <= index < deferral` traded at or beyond `stop` (long: `Low <= stop`; short: `High >= stop`)
  - `deferral_bar(bars, deferral, close) -> pd.Series | None` — first bar with `deferral <= index < close`; `.name` is its start
  - `@dataclass(frozen=True) ArmResult(arm, taken, fill, stop, tp1, outcome, r_net, r_gross, exit_ts: str | None, gap_stop: bool)` with `to_dict() -> dict` (the PAIR `arms` entries, keys in that order)
  - `price_arms(bars, *, direction, entry, stop, tp1, opened_at, deferral, close, end) -> dict[str, ArmResult]` — `deferral` is `bars.deferral_start(d)`, `close` is `bars.session_close_utc(d)`, `end` is `bars.horizon_end(d)`; `ValueError` on an unknown direction, zero risk or no deferral bar.

**Rules (spec § Three simulated arms, § Frictions; Handoff 1):**
- **C** fills at the trade's own `entry`, raced from `opened_at` (the first bar starting at or after it, so the entry bar is not raced).
- **A** fills at the deferral bar's **open** and races from that bar (inclusive: the fill is at its open, so its range comes after the fill). Stop and TP1 keep the plan's distances via `shifted_levels`.
- **B** is A, unless `held_touched(..., start=opened_at, deferral=<deferral bar start>)`: then `taken=False`, `outcome="skipped"`, `r_net = r_gross = 0.0`, levels `None`. The held check reads **only** bars strictly before the deferral bar — the no-lookahead test pins it by truncation.
- **Frictions** only here, once per arm: `net_r(fill, exit_price, risk, direction=NET_DIRECTION[d], days=..., entry_bps=...)`. C passes `entry_bps=None` (default slippage); A and B pass `DEFERRED_BPS_MULT * config.SLIPPAGE_BPS`. Longs pass `days=0` (never read). Shorts pass the **calendar** days between the ET fill date and the ET exit date, the unit the screen's own `_days` helper feeds `net_r` (Handoff 1 says "sessions held ... exactly as the screen applies it"; the screen counts calendar days, so calendar days it is — flagged to the controller). `assert_frictions()` runs first in `price_arms`, so zero frictions are refused before any arm is priced. `r_gross` (from `simulate.gross_r`) is recorded beside `r_net` and gates nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_arms.py`:

```python
"""V229-3: arms C, A, B -- distance-preserving levels, the strictly-before
skip rule, frictions through screen.sides.net_r, zero frictions refused."""
import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import arms  # noqa: E402
from deferred_entry import bars as tb  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen.sides import net_r  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

D = dt.date(2026, 11, 3)
DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
OPENED = "2026-11-03 10:02"


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _price(frame, direction="bullish", entry=100.0, stop=98.0, tp1=104.0):
    return arms.price_arms(
        frame, direction=direction, entry=entry, stop=stop, tp1=tp1,
        opened_at=et(OPENED), deferral=tb.deferral_start(D),
        close=tb.session_close_utc(D), end=tb.horizon_end(D))


def test_shifted_levels_keep_the_plan_distances_both_ways():
    assert arms.shifted_levels(101.0, entry=100.0, stop=98.0, tp1=104.0) == (99.0, 105.0)
    assert arms.shifted_levels(99.0, entry=100.0, stop=102.0, tp1=96.0) == (101.0, 95.0)


def test_arm_a_fills_at_the_1530_open_with_shifted_levels():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0)})
    out = _price(frame)
    assert set(out) == set(arms.ARMS)
    a = out["A"]
    assert (a.fill, a.stop, a.tp1, a.taken) == (101.0, 99.0, 105.0, True)
    assert out["C"].fill == 100.0 and out["C"].stop == 98.0


def test_every_arm_is_net_of_frictions_and_the_deferred_arms_pay_double_entry_slippage():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0)})
    out = _price(frame)
    c, a = out["C"], out["A"]
    assert c.outcome == a.outcome == "timeout"
    assert c.r_net == pytest.approx(net_r(100.0, 100.0, 2.0, direction="long", days=0))
    assert a.r_net == pytest.approx(net_r(101.0, 100.0, 2.0, direction="long", days=0, entry_bps=10.0))
    assert a.r_gross == pytest.approx(-0.5) and a.r_net < a.r_gross
    assert c.r_gross == 0.0 and c.r_net < 0.0


@pytest.mark.parametrize("field, value", [("SLIPPAGE_BPS", 0.0), ("COMMISSION_PER_TRADE", 0.0)])
def test_zero_frictions_are_refused(monkeypatch, field, value):
    monkeypatch.setattr(config, field, value, raising=False)
    with pytest.raises(arms.FrictionsError):
        _price(five_min(DAYS))


def test_arm_b_skips_when_the_stop_traded_before_1530():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 97.9, 98.5)})
    out = _price(frame)
    b = out["B"]
    assert (b.taken, b.outcome, b.r_net, b.r_gross, b.fill) == (False, "skipped", 0.0, 0.0, None)
    assert out["C"].outcome == "loss"


def test_arm_b_equals_arm_a_without_a_touch():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 98.05, 98.5)})
    out = _price(frame)
    assert out["B"].taken and out["B"] == dataclasses.replace(out["A"], arm="B")


def test_a_touch_inside_the_entry_bar_is_excluded_like_the_control():
    frame = five_min(DAYS, overrides={"2026-11-03 10:00": (100.0, 100.1, 97.5, 99.9)})
    out = _price(frame)
    assert out["B"].taken
    assert out["C"].outcome == "timeout"


def test_a_touch_in_the_1530_bar_does_not_skip_arm_b():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (100.0, 100.1, 97.0, 99.0)})
    out = _price(frame)
    assert out["B"].taken and out["B"].outcome == "loss"


@pytest.mark.parametrize("low", [97.9, 98.05])
def test_no_lookahead_removing_bars_from_1530_leaves_the_skip_decision_unchanged(low):
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, low, 98.5),
                                      "2026-11-04 10:00": (99.0, 99.0, 90.0, 95.0)})
    deferral = tb.deferral_start(D)
    kwargs = dict(direction="bullish", stop=98.0, start=et(OPENED), deferral=deferral)
    truncated = frame[frame.index < deferral]
    assert arms.held_touched(truncated, **kwargs) == arms.held_touched(frame, **kwargs)


def test_no_deferral_bar_is_refused():
    frame = five_min(DAYS)
    frame = frame[~((frame.index >= tb.deferral_start(D)) & (frame.index < tb.session_close_utc(D)))]
    assert arms.deferral_bar(frame, tb.deferral_start(D), tb.session_close_utc(D)) is None
    with pytest.raises(ValueError, match="deferral"):
        _price(frame)


def test_bearish_arms_mirror_and_pay_borrow_over_calendar_days():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (101.0, 102.1, 100.9, 101.5)})
    out = _price(frame, direction="bearish", entry=100.0, stop=102.0, tp1=96.0)
    assert out["C"].outcome == "loss" and not out["B"].taken
    a = out["A"]
    assert (a.stop, a.tp1) == (102.0, 96.0) and a.outcome == "timeout"
    held = (dt.date(2026, 11, 10) - D).days
    assert a.r_net == pytest.approx(
        net_r(100.0, 100.0, 2.0, direction="short", days=held, entry_bps=10.0))


def test_to_dict_carries_the_pair_keys_in_order():
    out = _price(five_min(DAYS))
    assert list(out["C"].to_dict()) == ["arm", "taken", "fill", "stop", "tp1", "outcome",
                                        "r_net", "r_gross", "exit_ts", "gap_stop"]
    assert out["C"].to_dict()["exit_ts"] == et("2026-11-10 15:55").isoformat()


def test_unknown_direction_and_zero_risk_are_refused():
    with pytest.raises(ValueError):
        _price(five_min(DAYS), direction="long")
    with pytest.raises(ValueError, match="risk"):
        _price(five_min(DAYS), stop=100.0)
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_arms.py`
Expected: collection error, `ImportError: cannot import name 'arms' from 'deferred_entry'`.

- [ ] **Step 3: Implement `arms.py`**

Create `scripts/reports/deferred_entry/arms.py`:

```python
"""v229 arms (spec § Three simulated arms, § Frictions).

C: the trade's own entry, raced from the first bar starting at or after
opened_at. A: the open of the first bar starting at or after 15:30 ET on the
entry date. B: as A, skipped (0R) when any bar starting at or after opened_at
and STRICTLY BEFORE the 15:30 bar traded at or beyond the plan's original
stop. A and B keep the plan's stop and TP1 distances. Every arm's R is net,
through screen.sides.net_r, called once per arm here and nowhere else; the
deferred arms pay twice the entry slippage (a market order in the last half
hour). Zero frictions are refused."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pandas as pd

from swingbot import config
from swingbot.core.backtesting.screen.sides import net_r
from swingbot.core.edge.frictions import commission_r

from .bars import et_date
from .simulate import SIGN, Race, gross_r, race

ARMS = ("C", "A", "B")
NET_DIRECTION = {"bullish": "long", "bearish": "short"}
DEFERRED_BPS_MULT = 2
SKIPPED = "skipped"


class FrictionsError(RuntimeError):
    """Frictions are zero: a lift measured without costs is refused."""


def assert_frictions() -> None:
    bps = float(getattr(config, "SLIPPAGE_BPS", 0.0) or 0.0)
    commission = commission_r()
    if bps <= 0 or commission <= 0:
        raise FrictionsError(f"zero frictions refused (SLIPPAGE_BPS={bps}, "
                             f"commission_r={commission})")


def shifted_levels(fill: float, *, entry: float, stop: float, tp1: float) -> tuple[float, float]:
    """The plan's stop and TP1 distances, carried to a new fill."""
    return fill - (entry - stop), fill + (tp1 - entry)


def held_touched(bars, *, direction: str, stop: float, start, deferral) -> bool:
    """Any bar with start <= index < deferral traded at or beyond ``stop``."""
    if bars is None or bars.empty:
        return False
    window = bars[(bars.index >= start) & (bars.index < deferral)]
    if window.empty:
        return False
    if SIGN[direction] > 0:
        return bool((window["Low"] <= stop).any())
    return bool((window["High"] >= stop).any())


def deferral_bar(bars, deferral, close) -> pd.Series | None:
    """The first bar with deferral <= index < close; ``.name`` is its start."""
    if bars is None or bars.empty or deferral is None:
        return None
    window = bars[(bars.index >= deferral) & (bars.index < close)]
    return None if window.empty else window.iloc[0]


@dataclass(frozen=True)
class ArmResult:
    arm: str
    taken: bool
    fill: float | None
    stop: float | None
    tp1: float | None
    outcome: str
    r_net: float
    r_gross: float
    exit_ts: str | None
    gap_stop: bool

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _calendar_days(direction: str, start_ts, result: Race) -> int:
    """Borrow days for a short, as the screen feeds net_r; a long never reads it."""
    if NET_DIRECTION[direction] == "long" or result.exit_ts is None:
        return 0
    return (et_date(result.exit_ts) - et_date(start_ts)).days


def _arm(name: str, result: Race, *, direction: str, fill: float, stop: float, tp1: float,
         risk: float, entry_bps, start_ts) -> ArmResult:
    r_net = 0.0
    if result.exit_price is not None:
        r_net = float(net_r(fill, result.exit_price, risk, direction=NET_DIRECTION[direction],
                            days=_calendar_days(direction, start_ts, result),
                            entry_bps=entry_bps))
    return ArmResult(
        arm=name, taken=True, fill=float(fill), stop=float(stop), tp1=float(tp1),
        outcome=result.outcome, r_net=r_net,
        r_gross=float(gross_r(result, direction=direction, fill=fill, risk=risk)),
        exit_ts=None if result.exit_ts is None else result.exit_ts.isoformat(),
        gap_stop=bool(result.gap_stop))


def _skipped() -> ArmResult:
    return ArmResult("B", False, None, None, None, SKIPPED, 0.0, 0.0, None, False)


def _checked(direction: str, entry: float, stop: float) -> float:
    if direction not in NET_DIRECTION:
        raise ValueError(f"unknown direction {direction!r}")
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        raise ValueError(f"zero risk: entry {entry} == stop {stop}")
    return risk


def price_arms(bars, *, direction: str, entry: float, stop: float, tp1: float,
               opened_at, deferral, close, end) -> dict[str, ArmResult]:
    """Arms C, A and B of one plan, each net of frictions."""
    assert_frictions()
    risk = _checked(direction, entry, stop)
    bar = deferral_bar(bars, deferral, close)
    if bar is None:
        raise ValueError("no deferral bar in [15:30 ET, close) on the entry date")
    fill = float(bar["Open"])
    a_stop, a_tp1 = shifted_levels(fill, entry=entry, stop=stop, tp1=tp1)
    control = race(bars, direction=direction, fill=entry, stop=stop, tp1=tp1,
                   start=opened_at, end=end)
    deferred = race(bars, direction=direction, fill=fill, stop=a_stop, tp1=a_tp1,
                    start=bar.name, end=end)
    late_bps = DEFERRED_BPS_MULT * float(config.SLIPPAGE_BPS)
    out = {
        "C": _arm("C", control, direction=direction, fill=entry, stop=stop, tp1=tp1,
                  risk=risk, entry_bps=None, start_ts=opened_at),
        "A": _arm("A", deferred, direction=direction, fill=fill, stop=a_stop, tp1=a_tp1,
                  risk=risk, entry_bps=late_bps, start_ts=bar.name),
    }
    touched = held_touched(bars, direction=direction, stop=stop, start=opened_at,
                           deferral=bar.name)
    out["B"] = _skipped() if touched else dataclasses.replace(out["A"], arm="B")
    return out
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_arms.py`
Expected: every test passes, `0 failed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new function at or above 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/deferred_entry/arms.py tests/scripts/test_deferred_entry_arms.py
git commit -m "feat(v229): arms C, A, B with distance-preserving levels and net frictions (V229-3)"
```

