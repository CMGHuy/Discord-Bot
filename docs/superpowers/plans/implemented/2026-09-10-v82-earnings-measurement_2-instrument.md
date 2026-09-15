# v82 — Earnings Blackout Measurement, Part 2: Instrument

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Index, Global Constraints and Parallelisation: `2026-09-10-v82-earnings-measurement_0-index.md`.

**Bump:** ui patch
**Edge:** expectancy

## Parallelisation (this part)

- **Group 1 (parallel, after M2):** M4, M5 (and Part 1's M3) — disjoint files.
- **Sequential:** M6 after M4 (imports `earnings_blackout`). M7 after M3–M6.

---

### Task M4: Measurement arithmetic

**Files:**
- Create: `swingbot/core/backtesting/earnings_blackout.py`
- Test: `tests/backtesting/test_earnings_blackout.py` (new)

**Interfaces:**
- Consumes: `acceptance.ArmTrade`, `win_rate`, `expectancy_r`, `delta_standardised_win_rate`, `delta_expectancy_r`, `NON_INFERIORITY_R` (−0.01), `VOLUME_MAX_CUT_PCT` (25.0); `backtest_wf.plateau_report(param_name, grid, expectancies, adopted_value) -> dict`; M2's `is_exposed`, `next_reaction_distance`.
- Produces:
  - constants `PARAM_NAME`, `GRID`, `COVERAGE_FLOOR_PCT`, `RUN1_WINDOW`, `SELECTION_WINDOW`, `SELECTION_OBSERVED_DAYS` (945), `MDE_TARGET_DAYS` (730), `FOLD_TEST_YEARS`, `VALIDATION_WINDOW`, `PERMUTATION_N`, `PERMUTATION_SEED`, `PERMUTATION_SHIFT_RANGE`; verdicts `SELECTED`, `NO_ELIGIBLE_K`, `SPIKE`, `INSUFFICIENT_COVERAGE`
  - `ExposureRow(trade: ArmTrade, population: str, is_etf: bool, covered: bool, signal_pos: int, distance: int | None)` with `.to_dict()` / `ExposureRow.from_dict(d)`
  - `in_window(rows, window) -> list`, `in_year(rows, year) -> list`, `coverage_pct(rows) -> float | None`
  - `split(rows, k) -> (baseline, component, removed)` — lists of `ArmTrade`
  - `arms_blob(rows, k) -> dict` (`{"baseline": [...], "component": [...]}`), `folds_blob(rows, k) -> dict` (`{"folds": [{"test_year", "baseline", "component"}, ...]}`)
  - `Candidate` (fields below), `score_candidate(rows, k) -> Candidate`
  - `Selection(candidates, selected_k, plateau, verdict)`, `select_k(rows, grid=GRID) -> Selection`
  - `permutation_test(rows, k, reactions_by_ticker: dict[str, list[int]], n_sessions: int, *, n=PERMUTATION_N, seed=PERMUTATION_SEED) -> dict` with keys `real_delta_win_rate_pp`, `p_value`, `n`, `n_valid`, `seed`, `shift_range`

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_earnings_blackout.py`:

```python
"""v82 M4: the pre-registered arithmetic of the earnings-blackout measurement."""
from __future__ import annotations

import dataclasses
import json

from swingbot.core.backtesting import earnings_blackout as eb
from swingbot.core.backtesting.acceptance import ArmTrade


def _rows(*groups, year="2019"):
    """groups: (count, outcome, distance). One ticker, one stratum, distinct
    entry dates; a row is covered iff it has a distance."""
    out, n = [], 0
    for count, outcome, distance in groups:
        for _ in range(count):
            r = 1.5 if outcome == "win" else -1.0
            date = f"{year}-{1 + n // 28:02d}-{1 + n % 28:02d}"
            trade = ArmTrade("AAA", "S", "4w", date, outcome, r, 2.0)
            out.append(eb.ExposureRow(trade, "strategy", False, distance is not None, 1000 + n, distance))
            n += 1
    return out


def test_pre_registered_constants():
    assert eb.GRID == (1, 2, 3, 5)
    assert eb.COVERAGE_FLOOR_PCT == 90.0
    assert eb.SELECTION_WINDOW == ("2018-06-01", "2020-12-31")
    assert eb.SELECTION_OBSERVED_DAYS == 945 and eb.MDE_TARGET_DAYS == 730
    assert eb.FOLD_TEST_YEARS == ("2021", "2022", "2023")
    assert eb.VALIDATION_WINDOW == ("2024-01-01", "2025-12-31")
    assert (eb.PERMUTATION_N, eb.PERMUTATION_SEED, eb.PERMUTATION_SHIFT_RANGE) == (200, 42, (20, 200))


def test_split_removes_only_rows_exposed_at_k():
    rows = _rows((1, "win", None), (1, "win", 0), (1, "loss", 1), (1, "loss", 2), (1, "win", 6))
    baseline, component, removed = eb.split(rows, 2)
    assert (len(baseline), len(component), len(removed)) == (5, 3, 2)
    assert {t.outcome for t in removed} == {"loss"}


def test_coverage_ignores_etf_rows():
    stock = _rows((3, "win", 1), (1, "win", None))
    etf = [dataclasses.replace(stock[0], is_etf=True, covered=False)]
    assert eb.coverage_pct(stock + etf) == 75.0
    assert eb.coverage_pct(etf) is None


def test_windows_and_years():
    rows = _rows((2, "win", None), year="2021") + _rows((1, "win", None), year="2024")
    assert len(eb.in_year(rows, "2021")) == 2
    assert len(eb.in_window(rows, eb.VALIDATION_WINDOW)) == 1


def test_candidate_is_eligible_when_exposed_rows_are_losers():
    c = eb.score_candidate(_rows((10, "win", None), (6, "loss", None), (4, "loss", 1)), 1)
    assert c.eligible, c.reasons
    assert c.removed_n == 4 and c.volume_cut_pct == 20.0
    assert c.delta_win_rate_pp > 0 and c.delta_expectancy_r > 0


def test_candidate_rejected_when_removed_rows_win():
    c = eb.score_candidate(_rows((6, "win", None), (10, "loss", None), (4, "win", 1)), 1)
    assert not c.eligible
    assert any(reason.startswith("mechanism") for reason in c.reasons)


def test_candidate_rejected_past_the_volume_ceiling():
    c = eb.score_candidate(_rows((10, "win", None), (4, "loss", None), (6, "loss", 1)), 1)
    assert any(reason.startswith("volume") for reason in c.reasons)


def test_candidate_that_removes_nothing_is_ineligible():
    assert not eb.score_candidate(_rows((5, "win", None), (5, "loss", None)), 3).eligible


def test_select_prefers_the_smaller_k_on_a_tie():
    sel = eb.select_k(_rows((10, "win", None), (6, "loss", None), (4, "loss", 1)))
    assert sel.verdict == eb.SELECTED and sel.selected_k == 1
    assert sel.plateau["is_plateau"]


def test_select_reports_no_eligible_k():
    sel = eb.select_k(_rows((6, "win", None), (10, "loss", None), (4, "win", 1)))
    assert sel.verdict == eb.NO_ELIGIBLE_K and sel.selected_k is None and sel.plateau is None


def test_select_refuses_a_spike():
    # K=2 removes 10 losers (eligible); K=1 removes nothing, so its expectancy
    # sits 0.17R away from K=2's -> not a plateau.
    sel = eb.select_k(_rows((40, "win", None), (30, "loss", None), (10, "loss", 2), (10, "win", 3)))
    assert sel.verdict == eb.SPIKE and sel.selected_k is None
    assert sel.plateau["adopted"] == 2 and not sel.plateau["is_plateau"]


def test_folds_blob_shape_loads_as_arm_trades():
    rows = []
    for year in eb.FOLD_TEST_YEARS:
        rows += _rows((3, "win", None), (1, "loss", 1), year=year)
    blob = eb.folds_blob(rows, 1)
    assert [f["test_year"] for f in blob["folds"]] == ["2021", "2022", "2023"]
    first = blob["folds"][0]
    assert len(first["baseline"]) == 4 and len(first["component"]) == 3
    ArmTrade(**first["baseline"][0])


def test_arms_blob_shape():
    blob = eb.arms_blob(_rows((3, "win", None), (1, "loss", 1)), 1)
    assert set(blob) == {"baseline", "component"}
    assert len(blob["baseline"]) == 4 and len(blob["component"]) == 3


def test_exposure_row_round_trips_through_json():
    row = _rows((1, "loss", 2))[0]
    assert eb.ExposureRow.from_dict(json.loads(json.dumps(row.to_dict()))) == row


def test_permutation_with_nothing_covered_returns_p_of_one():
    rows = [dataclasses.replace(r, covered=False)
            for r in _rows((10, "win", None), (6, "loss", None), (4, "loss", 1))]
    out = eb.permutation_test(rows, 1, {"AAA": [1001]}, n_sessions=5000, n=20)
    assert out["p_value"] == 1.0 and out["n_valid"] == 20 and out["n"] == 20


def test_permutation_is_deterministic():
    rows = _rows((10, "win", None), (6, "loss", None), (4, "loss", 1))
    reactions = {"AAA": sorted(r.signal_pos + r.distance for r in rows if r.distance is not None)}
    a = eb.permutation_test(rows, 1, reactions, n_sessions=5000, n=30)
    b = eb.permutation_test(rows, 1, reactions, n_sessions=5000, n=30)
    assert a == b
    assert 0.0 <= a["p_value"] <= 1.0 and a["seed"] == eb.PERMUTATION_SEED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_earnings_blackout.py`
Expected: FAIL — `ImportError: cannot import name 'earnings_blackout'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/backtesting/earnings_blackout.py`:

```python
"""Spec v82 Phase B -- the earnings-blackout measurement's arithmetic.

Pure functions over an EXPOSURE TABLE: one row per replayed trade, carrying
the trade (an ArmTrade) and how many sessions its signal bar sat before the
ticker's next earnings reaction. Every K arm, the Stage 1 selection rule, the
fold split and the calendar-shift permutation are arithmetic over that one
table, so every arm scores the identical population (v68's one-pass argument).

PRE-REGISTERED by docs/superpowers/specs/2026-09-10-v82-earnings-awareness-design.md
(B2-B5 and "Planning findings (Plan B)"). Changing a constant here is a new
pre-registration, not a tuning step.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, replace

import numpy as np

from swingbot.core.backtesting.acceptance import (
    NON_INFERIORITY_R, VOLUME_MAX_CUT_PCT, ArmTrade, delta_expectancy_r,
    delta_standardised_win_rate, expectancy_r, win_rate,
)
from swingbot.core.backtesting.backtest_wf import plateau_report
from swingbot.core.market.earnings_calendar import is_exposed, next_reaction_distance

PARAM_NAME = "EARNINGS_BLACKOUT_SESSIONS"
GRID = (1, 2, 3, 5)
COVERAGE_FLOOR_PCT = 90.0
RUN1_WINDOW = ("2018-06-01", "2023-12-31")
SELECTION_WINDOW = ("2018-06-01", "2020-12-31")
SELECTION_OBSERVED_DAYS = (dt.date.fromisoformat(SELECTION_WINDOW[1])
                           - dt.date.fromisoformat(SELECTION_WINDOW[0])).days + 1
MDE_TARGET_DAYS = 730
FOLD_TEST_YEARS = ("2021", "2022", "2023")
VALIDATION_WINDOW = ("2024-01-01", "2025-12-31")
PERMUTATION_N = 200
PERMUTATION_SEED = 42
PERMUTATION_SHIFT_RANGE = (20, 200)

SELECTED = "SELECTED"
NO_ELIGIBLE_K = "NO_ELIGIBLE_K"
SPIKE = "SPIKE"
INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


@dataclass(frozen=True)
class ExposureRow:
    trade: ArmTrade
    population: str          # "confluence" | "strategy"
    is_etf: bool
    covered: bool            # stock row inside its ticker's known report span
    signal_pos: int          # the signal bar's position in the session calendar
    distance: int | None     # sessions to the next reaction; None = not measurable

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExposureRow":
        return cls(trade=ArmTrade(**d["trade"]), population=d["population"],
                   is_etf=d["is_etf"], covered=d["covered"],
                   signal_pos=d["signal_pos"], distance=d["distance"])


def in_window(rows, window) -> list:
    lo, hi = window
    return [r for r in rows if lo <= r.trade.entry_date <= hi]


def in_year(rows, year: str) -> list:
    return [r for r in rows if r.trade.entry_date.startswith(year)]


def coverage_pct(rows) -> float | None:
    """Share of STOCK rows inside a known report span. ETF rows never count."""
    stock = [r for r in rows if not r.is_etf]
    if not stock:
        return None
    return 100.0 * sum(1 for r in stock if r.covered) / len(stock)


def split(rows, k: int) -> tuple[list, list, list]:
    """(baseline, component, removed) at K. The component is the baseline
    minus rows exposed at K (B2); nothing else differs."""
    baseline, component, removed = [], [], []
    for r in rows:
        baseline.append(r.trade)
        (removed if is_exposed(r.distance, k) else component).append(r.trade)
    return baseline, component, removed


def arms_blob(rows, k: int) -> dict:
    baseline, component, _ = split(rows, k)
    return {"baseline": [asdict(t) for t in baseline],
            "component": [asdict(t) for t in component]}


def folds_blob(rows, k: int) -> dict:
    return {"folds": [dict(test_year=year, **arms_blob(in_year(rows, year), k))
                      for year in FOLD_TEST_YEARS]}


@dataclass(frozen=True)
class Candidate:
    k: int
    removed_n: int
    removed_win_rate: float | None
    retained_win_rate: float | None
    removed_expectancy_r: float | None
    volume_cut_pct: float
    delta_win_rate_pp: float | None
    delta_expectancy_r: float | None
    eligible: bool
    reasons: tuple[str, ...]


def score_candidate(rows, k: int) -> Candidate:
    """Stage 1 eligibility (spec v82 B4): removed WR < retained WR and removed
    ExpR <= 0 (clause 6's mechanism), cut <= VOLUME_MAX_CUT_PCT (clause 4),
    dExpR >= NON_INFERIORITY_R (clause 2's margin)."""
    baseline, component, removed = split(rows, k)
    removed_wr, retained_wr = win_rate(removed), win_rate(component)
    removed_expr = expectancy_r(removed)
    cut = 100.0 * len(removed) / len(baseline) if baseline else 100.0
    dwr = delta_standardised_win_rate(baseline, component)
    dexpr = delta_expectancy_r(baseline, component)
    reasons = []
    if removed_wr is None or retained_wr is None or removed_wr >= retained_wr:
        reasons.append("mechanism: removed win rate is not below retained")
    if removed_expr is None or removed_expr > 0:
        reasons.append("mechanism: removed expectancy is above 0")
    if cut > VOLUME_MAX_CUT_PCT:
        reasons.append(f"volume: cut {cut:.2f}% > {VOLUME_MAX_CUT_PCT}%")
    if dexpr is None or dexpr < NON_INFERIORITY_R:
        reasons.append(f"profit: dExpR below {NON_INFERIORITY_R}R")
    if dwr is None:
        reasons.append("win rate: no decided trades to compare")
    return Candidate(k=k, removed_n=len(removed), removed_win_rate=removed_wr,
                     retained_win_rate=retained_wr, removed_expectancy_r=removed_expr,
                     volume_cut_pct=cut, delta_win_rate_pp=dwr, delta_expectancy_r=dexpr,
                     eligible=not reasons, reasons=tuple(reasons))


@dataclass(frozen=True)
class Selection:
    candidates: tuple[Candidate, ...]
    selected_k: int | None
    plateau: dict | None
    verdict: str


def select_k(rows, grid=GRID) -> Selection:
    """Greatest mix-standardised dWR among eligible K, ties to the smaller K,
    and the pick must sit on a plateau of component expectancy."""
    candidates = tuple(score_candidate(rows, k) for k in grid)
    eligible = [c for c in candidates if c.eligible]
    if not eligible:
        return Selection(candidates, None, None, NO_ELIGIBLE_K)
    best = max(eligible, key=lambda c: (c.delta_win_rate_pp, -c.k))
    expectancies = []
    for k in grid:
        e = expectancy_r(split(rows, k)[1])
        expectancies.append(float("nan") if e is None else e)
    plateau = plateau_report(PARAM_NAME, list(grid), expectancies, best.k)
    if not plateau["is_plateau"]:
        return Selection(candidates, None, plateau, SPIKE)
    return Selection(candidates, best.k, plateau, SELECTED)


def permutation_test(rows, k: int, reactions_by_ticker: dict, n_sessions: int, *,
                     n: int = PERMUTATION_N, seed: int = PERMUTATION_SEED) -> dict:
    """Stage 3's null (spec v82 B4): each permutation draws one shift
    s ~ U[20, 200) sessions, moves every ticker's reaction positions by s
    (mod n_sessions), recomputes covered rows' distances, and re-scores dWR.
    p = share of permuted dWR >= the real dWR."""
    baseline, component, _ = split(rows, k)
    real = delta_standardised_win_rate(baseline, component)
    shifts = np.random.default_rng(seed).integers(*PERMUTATION_SHIFT_RANGE, size=n)
    permuted = []
    for shift in shifts:
        moved_reactions = {t: sorted((p + int(shift)) % n_sessions for p in positions)
                           for t, positions in reactions_by_ticker.items()}
        moved = [replace(r, distance=next_reaction_distance(
                     r.signal_pos, moved_reactions.get(r.trade.ticker, [])))
                 if r.covered else r
                 for r in rows]
        b, c, _ = split(moved, k)
        permuted.append(delta_standardised_win_rate(b, c))
    valid = [p for p in permuted if p is not None]
    p_value = None if real is None or not valid else float(np.mean([p >= real for p in valid]))
    return {"real_delta_win_rate_pp": real, "p_value": p_value, "n": int(n),
            "n_valid": len(valid), "seed": seed, "shift_range": list(PERMUTATION_SHIFT_RANGE)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_earnings_blackout.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/earnings_blackout.py tests/backtesting/test_earnings_blackout.py
git commit -m "feat(v82): pre-registered earnings-blackout arithmetic -- arms, selection, folds, permutation"
```

---

### Task M5: Earnings-date fetch script

**Files:**
- Create: `scripts/data/fetch_earnings_dates.py`
- Test: `tests/scripts/test_fetch_earnings_dates.py` (new)

**Interfaces:**
- Consumes (M2): `CSV_FIELDS`, `EARNINGS_CSV_DIR`, `report_from_timestamp`, `CsvSource`; (M1) `session.US_MARKET_TZ`.
- Produces: `rows_from_frame(frame) -> list[dict]`, `write_csv(path, rows)`, `fetch_frame(symbol, limit)`, `cached_symbols(cache_dir) -> list[str]`, `main(argv=None) -> int` (0 = every stock ticker written or skipped, 1 = at least one had no data).

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_fetch_earnings_dates.py`:

```python
"""v82 M5: Yahoo earnings dates -> market_data/earnings/<SYM>.csv.

Import style follows tests/scripts/test_alert_density.py: scripts/ is not a
package, so the module under test is imported off sys.path."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_earnings_dates as fed  # noqa: E402
from swingbot.core.market.earnings_calendar import CsvSource, Report  # noqa: E402

ET = ZoneInfo("America/New_York")


def _frame(*stamps):
    return pd.DataFrame({"EPS Estimate": [1.0] * len(stamps)},
                        index=pd.DatetimeIndex(stamps, name="Earnings Date"))


def test_rows_from_frame_sorts_dedups_and_classifies():
    frame = _frame(pd.Timestamp("2026-10-29 16:00", tz=ET),
                   pd.Timestamp("2026-07-30 06:00", tz=ET),
                   pd.Timestamp("2026-07-30 07:00", tz=ET))
    rows = fed.rows_from_frame(frame)
    assert [(r["report_date"], r["timing"]) for r in rows] == [
        ("2026-07-30", "before_open"), ("2026-10-29", "after_close")]
    assert rows[1]["report_ts_et"].startswith("2026-10-29T16:00:00")


def test_rows_from_frame_reads_naive_stamps_as_eastern():
    rows = fed.rows_from_frame(_frame(pd.Timestamp("2026-10-29 16:00")))
    assert rows == [{"report_date": "2026-10-29", "timing": "after_close",
                     "report_ts_et": "2026-10-29T16:00:00-04:00"}]


def test_written_csv_round_trips_through_csv_source(tmp_path):
    fed.write_csv(tmp_path / "NVDA.csv", fed.rows_from_frame(_frame(pd.Timestamp("2026-10-29 16:00", tz=ET))))
    assert CsvSource(tmp_path).reports("NVDA") == [Report(dt.date(2026, 10, 29), "after_close")]


def test_main_skips_etfs_and_existing_files_and_flags_missing_data(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    for sym in ("SPY", "AAA", "BBB", "CCC"):
        (cache / f"{sym}.csv").write_text("Date,Close\n2026-01-02,1\n", encoding="utf-8")
    out = tmp_path / "earnings"
    out.mkdir()
    (out / "BBB.csv").write_text("report_date,timing,report_ts_et\n", encoding="utf-8")
    monkeypatch.setattr("swingbot.core.marketdata.universe.is_etf", lambda s: s == "SPY")
    fetched = []

    def fake_fetch(symbol, limit):
        fetched.append(symbol)
        return _frame(pd.Timestamp("2026-10-29 16:00", tz=ET)) if symbol == "AAA" else None

    monkeypatch.setattr(fed, "fetch_frame", fake_fetch)
    code = fed.main(["--cache-dir", str(cache), "--out-dir", str(out)])
    assert code == 1                      # CCC had no data
    assert fetched == ["AAA", "CCC"]      # SPY is an ETF, BBB already exists
    assert (out / "AAA.csv").exists() and not (out / "CCC.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fetch_earnings_dates.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_earnings_dates'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/data/fetch_earnings_dates.py`:

```python
#!/usr/bin/env python3
"""Spec v82 B3: cache Yahoo's historical earnings dates as
market_data/earnings/<SYM>.csv.

One CSV per non-ETF ticker in data/backtest_cache/, in the format frozen by
spec v82 and read by swingbot.core.market.earnings_calendar.CsvSource:
report_date,timing,report_ts_et. Same source as the live bot (Yahoo), so the
measured rule is the rule that runs. Network; about 2s per ticker. Prints one
flushed line per ticker and a summary.

Run:
  python scripts/data/fetch_earnings_dates.py
  python scripts/data/fetch_earnings_dates.py --tickers AAPL,NVDA --force
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.market.earnings_calendar import (  # noqa: E402
    CSV_FIELDS, EARNINGS_CSV_DIR, UNCONFIRMED, report_from_timestamp,
)
from swingbot.core.market.session import US_MARKET_TZ  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
#: About 15 years of quarterly reports -- 2018-06 needs ~33.
DEFAULT_LIMIT = 60


def rows_from_frame(frame) -> list[dict]:
    """One row per report DATE, ascending. A naive stamp is read as ET; two
    stamps on one date keep the later one read."""
    by_date = {}
    for ts in frame.index:
        stamp = pd.Timestamp(ts)
        stamp = stamp.tz_localize(US_MARKET_TZ) if stamp.tzinfo is None else stamp.tz_convert(US_MARKET_TZ)
        report = report_from_timestamp(stamp.to_pydatetime())
        by_date[report.date] = {"report_date": report.date.isoformat(),
                                "timing": report.timing,
                                "report_ts_et": stamp.isoformat()}
    return [by_date[d] for d in sorted(by_date)]


def write_csv(path: Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def fetch_frame(symbol: str, limit: int):
    import yfinance as yf
    from swingbot.core.marketdata.ticker_utils import candidate_symbols
    for candidate in candidate_symbols(symbol):
        try:
            frame = yf.Ticker(candidate).get_earnings_dates(limit=limit)
        except Exception as exc:
            print(f"    {candidate}: fetch failed: {exc}", flush=True)
            continue
        if frame is not None and not frame.empty:
            return frame
    return None


def cached_symbols(cache_dir: Path) -> list[str]:
    return sorted(p.stem for p in Path(cache_dir).glob("*.csv"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", default=None, help="comma-separated; default: every cached ticker")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--out-dir", default=str(EARNINGS_CSV_DIR))
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--force", action="store_true", help="re-fetch tickers that already have a CSV")
    args = ap.parse_args(argv)

    from swingbot.core.marketdata.universe import is_etf

    symbols = args.tickers.split(",") if args.tickers else cached_symbols(Path(args.cache_dir))
    written = skipped = etfs = missing = 0
    for n, sym in enumerate(symbols, 1):
        prefix = f"[{n}/{len(symbols)}] {sym}"
        if is_etf(sym):
            etfs += 1
            print(f"{prefix}: ETF, no earnings", flush=True)
            continue
        out = Path(args.out_dir) / f"{sym.upper()}.csv"
        if out.exists() and not args.force:
            skipped += 1
            print(f"{prefix}: exists, skipped", flush=True)
            continue
        frame = fetch_frame(sym, args.limit)
        rows = rows_from_frame(frame) if frame is not None else []
        if not rows:
            missing += 1
            print(f"{prefix}: NO DATA", flush=True)
            continue
        write_csv(out, rows)
        written += 1
        unconfirmed = sum(1 for r in rows if r["timing"] == UNCONFIRMED)
        print(f"{prefix}: {len(rows)} reports {rows[0]['report_date']}..{rows[-1]['report_date']}"
              f" (unconfirmed {unconfirmed})", flush=True)
    print(f"\nwritten {written} | skipped {skipped} | ETF {etfs} | no data {missing}", flush=True)
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fetch_earnings_dates.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/fetch_earnings_dates.py tests/scripts/test_fetch_earnings_dates.py
git commit -m "feat(v82): fetch Yahoo historical earnings dates into the frozen CSV format"
```

---

### Task M6: The instrument script

**Files:**
- Create: `scripts/backtest/measure_earnings_blackout.py`
- Modify: `.gitignore` (append `data/v82/`)
- Test: `tests/scripts/test_measure_earnings_blackout.py` (new)

**Interfaces:**
- Consumes: M4's module (`eb.*`); M2's `CsvSource`, `EARNINGS_CSV_DIR`, `UNCONFIRMED`, `next_reaction_distance`, `reaction_session`; M1's `SessionCalendar`; `acceptance.arm_trade_from_plan`, `arm_trade_from_backtest`, `delta_standardised_win_rate`; `backtest_scenarios.replay_scenarios(ticker, df, horizon_key)`; `plan_engine.simulate_exit(df, i, plan, scale_out=True)` → `.outcome`, `.r_total`; `backtest.run_backtest(...)` → `.trades` (`BacktestTrade.entry_date` is the signal bar); `backtest.ALL_STRATEGIES`; `strategy_types.HORIZONS`; `universe.is_etf`.
- Produces: CLI `replay | coverage | select | arms | permute`; module functions `load_frame`, `load_calendar`, `calendar_meta`, `reaction_positions(ticker, source, calendar) -> list[int]`, `exposure_row(trade, population, signal_date, *, is_etf, positions, calendar) -> ExposureRow`, `ticker_rows(...) -> list[ExposureRow]`, `_worker(task) -> (ticker, list[dict])`, `write_shard`, `read_rows(run_dir) -> list[ExposureRow]`, `main(argv=None) -> int`. Exit codes: 0 ok · 1 negative verdict · 2 coverage below floor · 3 VALIDATION locked · 4 calendar changed.
- On disk: `data/v82/<run>/<TICKER>.jsonl` (one `ExposureRow.to_dict()` per line), `data/v82/<run>/calendar.json` (`{"first", "last", "sessions"}`), `data/v82/<run>/progress.txt` while running.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_measure_earnings_blackout.py`:

```python
"""v82 M6: the earnings-blackout instrument -- exposure rows, shards, locks,
and arms that validate_component.py can load.

Import style follows tests/scripts/test_alert_density.py."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import measure_earnings_blackout as meb  # noqa: E402
import validate_component  # noqa: E402
from swingbot.core.backtesting import earnings_blackout as eb  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.market.earnings_calendar import CsvSource  # noqa: E402
from swingbot.core.market.session import SessionCalendar  # noqa: E402

D = dt.date.fromisoformat


def _calendar(start="2019-01-01", end="2023-12-31"):
    return SessionCalendar(ts.date() for ts in pd.bdate_range(start, end))


def _csv(directory: Path, ticker: str, reports):
    body = "".join(f"{d},{t},{d}T16:00:00-04:00\n" for d, t in reports)
    (directory / f"{ticker}.csv").write_text("report_date,timing,report_ts_et\n" + body, encoding="utf-8")


def _cache(tmp_path, *symbols):
    cache = tmp_path / "cache"
    cache.mkdir()
    frame = "Date,Open,High,Low,Close,Volume\n2019-01-02,1,1,1,1,1\n2019-01-03,1,1,1,1,1\n"
    for sym in symbols:
        (cache / f"{sym}.csv").write_text(frame, encoding="utf-8")
    return cache


def test_reaction_positions_are_sorted_unique_sessions(tmp_path):
    cal = _calendar()
    _csv(tmp_path, "AAA", [("2019-05-02", "after_close"), ("2019-02-01", "before_open")])
    positions = meb.reaction_positions("AAA", CsvSource(tmp_path), cal)
    sessions = cal.sessions(cal.first, cal.last)
    assert [sessions[p] for p in positions] == [D("2019-02-01"), D("2019-05-03")]


def test_exposure_row_coverage_and_distance():
    cal = _calendar()
    positions = [cal.position_on_or_after(D("2019-02-01")), cal.position_on_or_after(D("2019-05-03"))]
    trade = ArmTrade("AAA", "S", "4w", "2019-04-30", "win", 1.5, 2.0)
    row = meb.exposure_row(trade, "strategy", "2019-04-30", is_etf=False, positions=positions, calendar=cal)
    assert row.covered and row.distance == 3          # Tue 30 Apr -> Fri 3 May
    early = dataclasses.replace(trade, entry_date="2019-01-15")
    before = meb.exposure_row(early, "strategy", "2019-01-15", is_etf=False, positions=positions, calendar=cal)
    assert not before.covered and before.distance is None
    etf = meb.exposure_row(trade, "strategy", "2019-04-30", is_etf=True, positions=positions, calendar=cal)
    assert not etf.covered and etf.distance is None


def test_ticker_rows_relabels_confluence_and_respects_the_window(monkeypatch):
    cal = _calendar()
    idx = pd.bdate_range("2019-01-01", "2019-12-31")
    df = pd.DataFrame({"Close": 1.0}, index=idx)
    plan = SimpleNamespace(ticker="AAA", strategy="MACD", horizon_key="4w", entry_price=10.0,
                           trigger_price=10.0, stop_loss=9.0, tp1=12.0)
    inside = idx.get_loc(pd.Timestamp("2019-06-03"))
    outside = idx.get_loc(pd.Timestamp("2019-01-02"))
    monkeypatch.setattr("swingbot.core.backtesting.backtest_scenarios.replay_scenarios",
                        lambda ticker, frame, hk: [(outside, plan), (inside, plan)])
    monkeypatch.setattr("swingbot.core.planning.plan_engine.simulate_exit",
                        lambda frame, i, p, scale_out: SimpleNamespace(outcome="win", r_total=1.5))
    trade = SimpleNamespace(entry_date="2019-06-04", outcome="loss", r_multiple=-1.0,
                            entry=10.0, stop_loss=9.0, take_profit=12.0)
    monkeypatch.setattr("swingbot.core.backtesting.backtest.run_backtest",
                        lambda *a, **k: SimpleNamespace(trades=[trade]))
    rows = meb.ticker_rows("AAA", df, ("2019-03-01", "2019-12-31"), ["4w"], ["MACD"],
                           is_etf=False, positions=[], calendar=cal)
    assert [r.population for r in rows] == ["confluence", "strategy"]
    assert rows[0].trade.strategy == "confluence:MACD" and rows[1].trade.strategy == "MACD"
    assert rows[0].trade.key != rows[1].trade.key


def test_replay_writes_shards_resumes_and_deletes_progress(tmp_path, monkeypatch):
    cache = _cache(tmp_path, "SPY", "AAA")
    calls = []

    def fake_worker(task):
        calls.append(task[0])
        row = eb.ExposureRow(ArmTrade(task[0], "S", "4w", "2019-01-02", "win", 1.5, 2.0),
                             "strategy", task[-1], False, 0, None)
        return task[0], [row.to_dict()]

    monkeypatch.setattr(meb, "_worker", fake_worker)
    monkeypatch.setattr("swingbot.core.marketdata.universe.is_etf", lambda s: s == "SPY")
    argv = ["replay", "--run", "run1", "--cache-dir", str(cache), "--csv-dir", str(tmp_path),
            "--out-root", str(tmp_path / "v82"), "--workers", "1"]
    assert meb.main(argv) == 0
    run_dir = tmp_path / "v82" / "run1"
    assert sorted(p.name for p in run_dir.glob("*.jsonl")) == ["AAA.jsonl", "SPY.jsonl"]
    assert not (run_dir / "progress.txt").exists()
    assert json.loads((run_dir / "calendar.json").read_text()) == {
        "first": "2019-01-02", "last": "2019-01-03", "sessions": 2}
    assert len(meb.read_rows(run_dir)) == 2
    calls.clear()
    assert meb.main(argv) == 0 and calls == []


def test_run2_refuses_without_a_passing_stage2_doc(tmp_path):
    cache = _cache(tmp_path, "SPY")
    base = ["replay", "--run", "run2", "--cache-dir", str(cache), "--csv-dir", str(tmp_path),
            "--out-root", str(tmp_path / "v82"), "--workers", "1"]
    assert meb.main(base) == 3
    doc = tmp_path / "stage2.md"
    doc.write_text("**Overall: FAIL**\n", encoding="utf-8")
    assert meb.main(base + ["--stage2-doc", str(doc)]) == 3
    assert not (tmp_path / "v82" / "run2").exists()


def test_walkforward_arms_load_through_validate_component(tmp_path):
    run_dir = tmp_path / "v82" / "run1"
    run_dir.mkdir(parents=True)
    rows = []
    for year in eb.FOLD_TEST_YEARS:
        for n, (outcome, distance) in enumerate([("win", None), ("win", 5), ("loss", 1)]):
            trade = ArmTrade("AAA", "S", "4w", f"{year}-03-0{n + 1}", outcome,
                             1.5 if outcome == "win" else -1.0, 2.0)
            rows.append(eb.ExposureRow(trade, "strategy", False, True, n, distance))
    meb.write_shard(run_dir / "AAA.jsonl", [r.to_dict() for r in rows])
    out = tmp_path / "wf.json"
    assert meb.main(["arms", "--stage", "walkforward", "--k", "1",
                     "--out-root", str(tmp_path / "v82"), "--out", str(out)]) == 0
    folds = validate_component.load_folds(out)
    assert [f["test_year"] for f in folds] == ["2021", "2022", "2023"]
    assert all(len(f["baseline"]) == 3 and len(f["component"]) == 2 for f in folds)


def test_arms_refuse_below_the_coverage_floor(tmp_path):
    run_dir = tmp_path / "v82" / "run1"
    run_dir.mkdir(parents=True)
    trade = ArmTrade("AAA", "S", "4w", "2019-03-01", "win", 1.5, 2.0)
    meb.write_shard(run_dir / "AAA.jsonl", [eb.ExposureRow(trade, "strategy", False, False, 0, None).to_dict()])
    assert meb.main(["arms", "--stage", "mde", "--k", "1", "--out-root", str(tmp_path / "v82"),
                     "--out", str(tmp_path / "mde.json")]) == 2
    assert not (tmp_path / "mde.json").exists()


def test_permute_refuses_a_changed_calendar(tmp_path):
    cache = _cache(tmp_path, "SPY")
    run_dir = tmp_path / "v82" / "run2"
    run_dir.mkdir(parents=True)
    (run_dir / "calendar.json").write_text(
        json.dumps({"first": "2018-06-01", "last": "2025-12-30", "sessions": 1904}), encoding="utf-8")
    assert meb.main(["permute", "--k", "1", "--cache-dir", str(cache), "--csv-dir", str(tmp_path),
                     "--out-root", str(tmp_path / "v82"), "--out-json", str(tmp_path / "p.json")]) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_earnings_blackout.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'measure_earnings_blackout'`.

- [ ] **Step 3: Write the implementation**

Append to `.gitignore`:

```
# v82 earnings-blackout exposure tables (large, regenerable)
data/v82/
```

Create `scripts/backtest/measure_earnings_blackout.py`:

```python
#!/usr/bin/env python3
"""Spec v82 B3: the earnings-blackout instrument.

Subcommands:
  replay    Build the exposure table for one run window: one JSONL shard per
            ticker under data/v82/<run>/ (resumable -- an existing shard is
            skipped). Confluence replay + per-strategy backtests, all horizons.
  coverage  Coverage and unconfirmed-report counts for a window.
  select    Stage 1 on SELECTION_WINDOW (run1 rows only).
  arms      Arms JSON for validate_component.py: --stage mde|walkforward|validation.
  permute   Stage 3's calendar-shift permutation p (run2 rows only).

PRE-REGISTERED: spec v82 B2-B5 + "Planning findings (Plan B)". run2 replays the
VALIDATION window and refuses to start without --stage2-doc pointing at a
Stage 2 results doc that reads **Overall: PASS**.

Progress: one flushed line per ticker, plus data/v82/<run>/progress.txt
("37/89 tickers (42%)"), deleted when the replay ends.

Exit codes: 0 ok, 1 negative verdict, 2 coverage below floor,
3 VALIDATION locked, 4 calendar changed since the shards were built.

Run:
  python scripts/backtest/measure_earnings_blackout.py replay --run run1
  python scripts/backtest/measure_earnings_blackout.py coverage --run run1 --window 2018-06-01..2023-12-31
  python scripts/backtest/measure_earnings_blackout.py select --out-md <doc> --out-json <json>
  python scripts/backtest/measure_earnings_blackout.py arms --stage mde --k 2 --out data/v82/arms_mde.json
  python scripts/backtest/measure_earnings_blackout.py replay --run run2 --stage2-doc <doc>
  python scripts/backtest/measure_earnings_blackout.py permute --k 2 --out-json <json>
"""
import argparse
import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.backtesting import earnings_blackout as eb  # noqa: E402
from swingbot.core.backtesting.acceptance import (  # noqa: E402
    arm_trade_from_backtest, arm_trade_from_plan, delta_standardised_win_rate,
)
from swingbot.core.market.earnings_calendar import (  # noqa: E402
    EARNINGS_CSV_DIR, UNCONFIRMED, CsvSource, next_reaction_distance, reaction_session,
)
from swingbot.core.market.session import SessionCalendar  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_ROOT = ROOT / "data" / "v82"
RUNS = {"run1": eb.RUN1_WINDOW, "run2": eb.VALIDATION_WINDOW}
CALENDAR_SYMBOL = "SPY"
STAGE2_PASS_MARKER = "**Overall: PASS**"

LIMITATIONS = (
    "- Report dates are Yahoo's historical calendar. Companies announce them weeks ahead, "
    "but a late reschedule makes a date mild lookahead.\n"
    "- The universe is today's data/backtest_cache tickers (survivorship).\n"
    "- The confluence leg exits through simulate_exit (no frictions); the strategy leg through "
    "run_backtest(frictions=True). Win rate is mix-standardised within (strategy, horizon) strata, "
    "and confluence strata are labelled `confluence:<strategy>`, so the legs never pool in one stratum.\n"
    "- Coverage is measured over stock trade rows; ETF and uncovered rows are never exposed and "
    "stay in both arms.\n"
)


def load_frame(cache_dir: Path, symbol: str):
    path = Path(cache_dir) / f"{symbol}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, index_col="Date", parse_dates=True)


def load_calendar(cache_dir: Path) -> SessionCalendar:
    df = load_frame(cache_dir, CALENDAR_SYMBOL)
    if df is None or df.empty:
        raise SystemExit(f"{CALENDAR_SYMBOL}.csv missing from {cache_dir} -- it is the instrument's calendar")
    return SessionCalendar.from_bar_index(df.index)


def calendar_meta(calendar: SessionCalendar) -> dict:
    return {"first": calendar.first.isoformat(), "last": calendar.last.isoformat(),
            "sessions": len(calendar)}


def _calendar_matches(run_dir: Path, calendar: SessionCalendar) -> bool:
    path = run_dir / "calendar.json"
    return path.exists() and json.loads(path.read_text(encoding="utf-8")) == calendar_meta(calendar)


def reaction_positions(ticker: str, source, calendar: SessionCalendar) -> list[int]:
    out = set()
    for report in source.reports(ticker):
        session = reaction_session(report, calendar)
        pos = None if session is None else calendar.position_on_or_after(session)
        if pos is not None:
            out.add(pos)
    return sorted(out)


def exposure_row(trade, population: str, signal_date: str, *, is_etf: bool,
                 positions: list[int], calendar: SessionCalendar) -> eb.ExposureRow:
    pos = calendar.position_on_or_before(date.fromisoformat(signal_date))
    covered = (not is_etf and bool(positions) and pos is not None
               and positions[0] <= pos <= positions[-1])
    distance = next_reaction_distance(pos, positions) if covered else None
    return eb.ExposureRow(trade=trade, population=population, is_etf=is_etf, covered=covered,
                          signal_pos=-1 if pos is None else pos, distance=distance)


def ticker_rows(ticker: str, df, window, horizons, strategies, *, is_etf: bool,
                positions: list[int], calendar: SessionCalendar) -> list[eb.ExposureRow]:
    from swingbot.core.backtesting.backtest import run_backtest
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit

    lo, hi = window
    rows = []
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk):
            signal_date = str(df.index[i].date())
            if not lo <= signal_date <= hi:
                continue
            result = simulate_exit(df, i, plan, scale_out=True)
            trade = arm_trade_from_plan(plan, entry_date=signal_date, outcome=result.outcome,
                                        r_multiple=result.r_total)
            trade = dataclasses.replace(trade, strategy=f"confluence:{trade.strategy}")
            rows.append(exposure_row(trade, "confluence", signal_date, is_etf=is_etf,
                                     positions=positions, calendar=calendar))
    for strategy in strategies:
        for hk in horizons:
            summary = run_backtest(ticker, df, strategy, hk, exit_model="v2", scale_out=True,
                                   tp2_mode="levels", frictions=True)
            for t in summary.trades:
                if not lo <= t.entry_date <= hi:
                    continue
                trade = arm_trade_from_backtest(t, ticker=ticker, strategy=strategy, horizon_key=hk)
                rows.append(exposure_row(trade, "strategy", t.entry_date, is_etf=is_etf,
                                         positions=positions, calendar=calendar))
    return rows


def _worker(task) -> tuple:
    """One ticker, every horizon and strategy -- the process-pool entry point,
    so it is module-level and takes one picklable tuple."""
    ticker, cache_dir, csv_dir, window, horizons, strategies, is_etf = task
    calendar = load_calendar(Path(cache_dir))
    df = load_frame(Path(cache_dir), ticker)
    if df is None or df.empty:
        return ticker, []
    positions = [] if is_etf else reaction_positions(ticker, CsvSource(csv_dir), calendar)
    rows = ticker_rows(ticker, df, window, horizons, strategies, is_etf=is_etf,
                       positions=positions, calendar=calendar)
    return ticker, [r.to_dict() for r in rows]


def write_shard(path: Path, dict_rows: list[dict]) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in dict_rows:
            fh.write(json.dumps(row) + "\n")
    tmp.replace(path)


def read_rows(run_dir: Path) -> list[eb.ExposureRow]:
    rows = []
    for shard in sorted(Path(run_dir).glob("*.jsonl")):
        with open(shard, encoding="utf-8") as fh:
            rows.extend(eb.ExposureRow.from_dict(json.loads(line)) for line in fh if line.strip())
    return rows


def _write_progress(path: Path, done: int, total: int) -> None:
    pct = 100 * done // total if total else 100
    path.write_text(f"{done}/{total} tickers ({pct}%)\n", encoding="utf-8")


def _write(path, text: str) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _drain(results, run_dir: Path, progress: Path, done: int, total: int) -> None:
    for ticker, dict_rows in results:
        write_shard(run_dir / f"{ticker}.jsonl", dict_rows)
        done += 1
        print(f"[{done}/{total}] {ticker}: {len(dict_rows)} rows", flush=True)
        _write_progress(progress, done, total)


def cmd_replay(args) -> int:
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    from swingbot.core.marketdata.universe import is_etf

    if args.run == "run2":
        doc = Path(args.stage2_doc) if args.stage2_doc else None
        if doc is None or not doc.exists() or STAGE2_PASS_MARKER not in doc.read_text(encoding="utf-8"):
            print("REFUSED -- run2 replays the VALIDATION window. Pass --stage2-doc with the committed "
                  f"Stage 2 results doc reading {STAGE2_PASS_MARKER}.", file=sys.stderr)
            return 3
    window = RUNS[args.run]
    cache_dir = Path(args.cache_dir)
    calendar = load_calendar(cache_dir)
    run_dir = Path(args.out_root) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "calendar.json").exists() and not _calendar_matches(run_dir, calendar):
        print(f"REFUSED -- {cache_dir / 'SPY.csv'} differs from the calendar these shards were built on.",
              file=sys.stderr)
        return 4
    _write(run_dir / "calendar.json", json.dumps(calendar_meta(calendar)))

    symbols = args.tickers.split(",") if args.tickers else sorted(p.stem for p in cache_dir.glob("*.csv"))
    horizons = args.horizons.split(",") if args.horizons else list(HORIZONS)
    strategies = args.strategies.split("|") if args.strategies else list(ALL_STRATEGIES)
    todo = [s for s in symbols if not (run_dir / f"{s}.jsonl").exists()]
    done, total = len(symbols) - len(todo), len(symbols)
    print(f"{args.run} {window[0]}..{window[1]} | {total} tickers ({done} already sharded) | "
          f"{len(horizons)} horizons | {len(strategies)} strategies", flush=True)
    tasks = [(s, str(cache_dir), str(args.csv_dir), window, horizons, strategies, is_etf(s)) for s in todo]
    progress = run_dir / "progress.txt"
    try:
        _write_progress(progress, done, total)
        if args.workers == 1:
            _drain(map(_worker, tasks), run_dir, progress, done, total)
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                _drain(pool.map(_worker, tasks), run_dir, progress, done, total)
    finally:
        progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows in {run_dir}", flush=True)
    return 0


def cmd_coverage(args) -> int:
    lo, hi = args.window.split("..")
    rows = eb.in_window(read_rows(Path(args.out_root) / args.run), (lo, hi))
    source = CsvSource(args.csv_dir)
    tickers = sorted({r.trade.ticker for r in rows if not r.is_etf})
    unconfirmed = sum(1 for t in tickers for rep in source.reports(t)
                      if rep.timing == UNCONFIRMED and lo <= rep.date.isoformat() <= hi)
    missing = [t for t in tickers if not source.has_data(t)]
    coverage = eb.coverage_pct(rows)
    print(f"window {lo}..{hi}: rows {len(rows)} | stock rows {sum(1 for r in rows if not r.is_etf)} "
          f"| ETF rows {sum(1 for r in rows if r.is_etf)}")
    for population in ("confluence", "strategy"):
        print(f"  {population}: {sum(1 for r in rows if r.population == population)} rows")
    print(f"coverage: {'n/a' if coverage is None else f'{coverage:.2f}%'} (floor {eb.COVERAGE_FLOOR_PCT}%)")
    print(f"unconfirmed reports in window: {unconfirmed} | stock tickers without a CSV: {missing or 'none'}")
    return 0 if coverage is not None and coverage >= eb.COVERAGE_FLOOR_PCT else 2


def _fmt(value, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def render_selection_md(selection, rows, coverage: float) -> str:
    lines = [
        "# v82 earnings blackout — Stage 1 selection", "",
        f"Window: {eb.SELECTION_WINDOW[0]}..{eb.SELECTION_WINDOW[1]} (the earliest fold's train window)",
        f"Rows: {len(rows)} | coverage {coverage:.2f}% (floor {eb.COVERAGE_FLOOR_PCT}%)", "",
        "Rule (pre-registered, spec v82 B4): K is eligible iff removed WR < retained WR and removed "
        f"ExpR <= 0, volume cut <= {eb.VOLUME_MAX_CUT_PCT}%, and dExpR >= {eb.NON_INFERIORITY_R}R. "
        "The greatest mix-standardised dWR wins, ties go to the smaller K, and the pick must pass "
        "plateau_report.", "",
        "| K | removed N | removed WR | retained WR | removed ExpR | cut % | dWR (pp) | dExpR | eligible | reasons |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in selection.candidates:
        lines.append(
            f"| {c.k} | {c.removed_n} | {_fmt(c.removed_win_rate, '.2f')} | "
            f"{_fmt(c.retained_win_rate, '.2f')} | {_fmt(c.removed_expectancy_r, '+.4f')} | "
            f"{c.volume_cut_pct:.2f} | {_fmt(c.delta_win_rate_pp, '+.3f')} | "
            f"{_fmt(c.delta_expectancy_r, '+.4f')} | {'yes' if c.eligible else 'no'} | "
            f"{'; '.join(c.reasons) or '—'} |")
    if selection.plateau:
        p = selection.plateau
        lines += ["", f"Plateau: adopted K={p['adopted']}, neighbours {p['neighbors']}, "
                      f"is_plateau={p['is_plateau']}"]
    verdict = f"**Verdict: {selection.verdict}**"
    if selection.selected_k is not None:
        verdict += f" — K = {selection.selected_k}"
    lines += ["", verdict, "", "## Limitations", "", LIMITATIONS]
    return "\n".join(lines) + "\n"


def cmd_select(args) -> int:
    rows = eb.in_window(read_rows(Path(args.out_root) / "run1"), eb.SELECTION_WINDOW)
    coverage = eb.coverage_pct(rows)
    if coverage is None or coverage < eb.COVERAGE_FLOOR_PCT:
        shown = "n/a" if coverage is None else f"{coverage:.2f}%"
        md = (f"# v82 earnings blackout — Stage 1 selection\n\n**Verdict: {eb.INSUFFICIENT_COVERAGE}** "
              f"— coverage {shown} < {eb.COVERAGE_FLOOR_PCT}%. The budget is intact; this is no verdict "
              f"on the hypothesis.\n\n## Limitations\n\n{LIMITATIONS}")
        _write(args.out_md, md)
        print(md)
        return 2
    selection = eb.select_k(rows)
    md = render_selection_md(selection, rows, coverage)
    _write(args.out_md, md)
    _write(args.out_json, json.dumps({
        "verdict": selection.verdict, "selected_k": selection.selected_k, "coverage_pct": coverage,
        "plateau": selection.plateau,
        "candidates": [dataclasses.asdict(c) for c in selection.candidates]}, indent=1))
    print(md)
    return 0 if selection.verdict == eb.SELECTED else 1


def _covered_enough(rows, label: str) -> bool:
    coverage = eb.coverage_pct(rows)
    ok = coverage is not None and coverage >= eb.COVERAGE_FLOOR_PCT
    shown = "n/a" if coverage is None else f"{coverage:.2f}%"
    print(f"{label}: {len(rows)} rows, coverage {shown}"
          + ("" if ok else f" -- BELOW the {eb.COVERAGE_FLOOR_PCT}% floor"), flush=True)
    return ok


def cmd_arms(args) -> int:
    out_root = Path(args.out_root)
    meta = {"stage": args.stage, "k": args.k}
    if args.stage == "mde":
        rows = eb.in_window(read_rows(out_root / "run1"), eb.SELECTION_WINDOW)
        if not _covered_enough(rows, "selection window"):
            return 2
        baseline, component, _ = eb.split(rows, args.k)
        effect = delta_standardised_win_rate(baseline, component)
        blob = eb.arms_blob(rows, args.k)
        meta.update(window=list(eb.SELECTION_WINDOW), train_effect_pp=effect,
                    observed_days=eb.SELECTION_OBSERVED_DAYS, target_days=eb.MDE_TARGET_DAYS)
        print(f"--train-effect-pp {effect} --observed-days {eb.SELECTION_OBSERVED_DAYS} "
              f"--target-days {eb.MDE_TARGET_DAYS}", flush=True)
    elif args.stage == "walkforward":
        rows = read_rows(out_root / "run1")
        checks = [_covered_enough(eb.in_year(rows, year), f"fold-test {year}") for year in eb.FOLD_TEST_YEARS]
        if not all(checks):
            return 2
        blob = eb.folds_blob(rows, args.k)
        meta.update(test_years=list(eb.FOLD_TEST_YEARS))
    else:
        rows = eb.in_window(read_rows(out_root / "run2"), eb.VALIDATION_WINDOW)
        if not _covered_enough(rows, "validation window"):
            return 2
        blob = eb.arms_blob(rows, args.k)
        meta.update(window=list(eb.VALIDATION_WINDOW))
    blob["meta"] = meta
    _write(args.out, json.dumps(blob))
    print(f"wrote {args.out}", flush=True)
    return 0


def cmd_permute(args) -> int:
    calendar = load_calendar(Path(args.cache_dir))
    run_dir = Path(args.out_root) / "run2"
    if not _calendar_matches(run_dir, calendar):
        print("REFUSED -- the calendar differs from the one run2's shards were built on "
              "(or run2 has not run).", file=sys.stderr)
        return 4
    rows = eb.in_window(read_rows(run_dir), eb.VALIDATION_WINDOW)
    source = CsvSource(args.csv_dir)
    reactions = {t: reaction_positions(t, source, calendar)
                 for t in sorted({r.trade.ticker for r in rows if r.covered})}
    result = eb.permutation_test(rows, args.k, reactions, len(calendar))
    result["k"] = args.k
    text = json.dumps(result, indent=1)
    print(text, flush=True)
    _write(args.out_json, text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
        p.add_argument("--csv-dir", default=str(EARNINGS_CSV_DIR))
        p.add_argument("--out-root", default=str(OUT_ROOT))

    p = sub.add_parser("replay")
    common(p)
    p.add_argument("--run", choices=sorted(RUNS), required=True)
    p.add_argument("--tickers", default=None, help="comma-separated (smoke runs only)")
    p.add_argument("--horizons", default=None, help="comma-separated (smoke runs only)")
    p.add_argument("--strategies", default=None, help="'|'-separated (smoke runs only)")
    p.add_argument("--workers", type=int, default=None, help="process count; 1 = serial")
    p.add_argument("--stage2-doc", default=None, help="required for run2")

    p = sub.add_parser("coverage")
    common(p)
    p.add_argument("--run", choices=sorted(RUNS), required=True)
    p.add_argument("--window", required=True, help="YYYY-MM-DD..YYYY-MM-DD")

    p = sub.add_parser("select")
    common(p)
    p.add_argument("--out-md", default=None)
    p.add_argument("--out-json", default=None)

    p = sub.add_parser("arms")
    common(p)
    p.add_argument("--stage", choices=("mde", "walkforward", "validation"), required=True)
    p.add_argument("--k", type=int, choices=eb.GRID, required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("permute")
    common(p)
    p.add_argument("--k", type=int, choices=eb.GRID, required=True)
    p.add_argument("--out-json", default=None)

    args = ap.parse_args(argv)
    commands = {"replay": cmd_replay, "coverage": cmd_coverage, "select": cmd_select,
                "arms": cmd_arms, "permute": cmd_permute}
    return commands[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_earnings_blackout.py`
Expected: PASS.

- [ ] **Step 5: Smoke the real replay path on one ticker (only where a cache exists)**

If `data/backtest_cache/SPY.csv` is reachable, run with the main checkout's cache (a worktree has none):

```bash
python scripts/backtest/measure_earnings_blackout.py replay --run run1 --tickers AAPL --horizons 4w --strategies "MACD" --workers 1 --cache-dir <main checkout>/data/backtest_cache --csv-dir <scratchpad>/earnings --out-root <scratchpad>/v82-smoke
```

Expected: a `[1/1] AAPL: N rows` line with N > 0 and `complete: N rows`. Coverage is irrelevant here (no CSVs yet). Delete `<scratchpad>/v82-smoke` afterwards. If the cache is not reachable, record "smoke deferred to M8" in the task report.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_earnings_blackout.py tests/scripts/test_measure_earnings_blackout.py .gitignore
git commit -m "feat(v82): earnings-blackout instrument -- replay shards, coverage, select, arms, permute"
```

---

### Task M7: Full suite, merge, release

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json` (generated)
- Modify: `docs/superpowers/plans/2026-09-10-v82-earnings-measurement_0-index.md` (Progress block)

**Interfaces:**
- Consumes: M1–M6 on the branch.
- Produces: M1–M6 merged to `main`; a `ui` patch release. **This is the plan's one full-suite run** — M8–M14 change no code and must not re-run it.

- [ ] **Step 1: Syntax pass**

Run: `python -m py_compile swingbot/core/market/session.py swingbot/core/market/earnings_calendar.py swingbot/core/market/events.py swingbot/core/edge/gates.py swingbot/core/backtesting/earnings_blackout.py swingbot/config.py swingbot/scan_params.py scripts/data/fetch_earnings_dates.py scripts/backtest/measure_earnings_blackout.py scripts/backtest/wf_components.py`
Expected: no output.

- [ ] **Step 2: Full suite (dispatch `test-runner`)**

Dispatch the `test-runner` subagent to run `python scripts/dev/testrun.py full` in the worktree and return only the verdict line.
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). Any failure: stop, fix under `superpowers:systematic-debugging`, re-run only the failing file, then this step once more.

- [ ] **Step 3: Merge to `main`**

From the main checkout:

```bash
git fetch
git rev-list --left-right --count origin/main...main
```

Expected `0	0` (if `main` is behind, stop and tell the human partner — `stale-checkout` hazard). Then:

```bash
git merge --no-ff 2026-09-10-v82-earnings-measurement -m "merge(v82): earnings calendar and blackout measurement instrument"
```

- [ ] **Step 4: Run the cache-backed calendar test on `main`**

Run: `python scripts/dev/testrun.py file tests/market/test_session_calendar.py`
Expected: PASS with `test_table_matches_the_cached_spy_bar_index` **passed, not skipped** (the main checkout has `data/backtest_cache/SPY.csv`). If it is skipped, run `python scripts/data/fetch_backtest_data.py` first. If it fails, apply M1 Step 4's rule.

- [ ] **Step 5: Release `ui` patch**

Read `VERSION.json`. Increment `ui`'s patch component only; set `ui_updated` to the current UTC time as `YYYY-MM-DD HH-MM-SS`. Commit:

```bash
git add VERSION.json
git commit -m "release(ui): <new ui version> -- earnings blackout setting counts trading sessions"
```

Then regenerate and commit the matrix (order matters — `docs/claude/working-conventions.md` "How"):

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(ui): <new ui version> -- earnings blackout setting counts trading sessions"
```

Expected: the matrix test PASSES.

- [ ] **Step 6: Update Progress and commit**

Tick M1–M7 in the index's Progress block, then:

```bash
git add docs/superpowers/plans/2026-09-10-v82-earnings-measurement_0-index.md
git commit -m "docs(v82): measurement plan M1-M7 complete"
```

Do not push unless the human partner asks. Leave the worktree and branch in place; M14 removes the worktree.
