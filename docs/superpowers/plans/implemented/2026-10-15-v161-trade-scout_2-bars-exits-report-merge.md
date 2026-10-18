# v161 Trade scout, part 2: bar cuts, exit and supply cuts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task TS6" -A 300 docs/superpowers/plans/implemented/2026-10-15-v161-trade-scout_2-bars-exits-report-merge.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-15-v161-trade-scout-design.md`](../../specs/implemented/2026-10-15-v161-trade-scout-design.md) (§ 1 cuts, statistics and output; § 6 merge drops; Data availability; Panel review)
**Bump:** none
**Edge:** none (integrity)
**Index:** [`2026-10-15-v161-trade-scout_0-index.md`](2026-10-15-v161-trade-scout_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts (Export columns, cell id, cut names, Autopsy JSON, Row format) and the task ledger. Every task below implicitly includes them. Ledger part 2 outgrew the 1500-line cap: TS5 and TS6 are here, TS7 and TS8 are in [`2026-10-15-v161-trade-scout_2b-report-merge-parse.md`](2026-10-15-v161-trade-scout_2b-report-merge-parse.md).

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths.
- The autopsy package `scripts/reports/autopsy/` imports its siblings **relatively** (`from .cells import Tally`), so it loads both as `autopsy.<module>` (tests and `book_autopsy.py` put `scripts/reports` on `sys.path`) and under any other root. Tests import it as:
  ```python
  ROOT = Path(__file__).resolve().parents[2]
  sys.path.insert(0, str(ROOT / "scripts" / "reports"))
  from autopsy import cells, rows  # noqa: E402
  ```
  If TS2 (part 1) chose a different import root, follow TS2's form in the test headers; the module code is unaffected.
- Tests build `BookRow`s through a local helper that defaults every field from `dataclasses.fields(BookRow)`, so they do not depend on the field order TS2 chose:
  ```python
  def _row(**kw):
      base = {f.name: None for f in fields(rows.BookRow) if f.name != "bars"}
      base.update(row_kind="trade", close_reason="", direction="bullish")
      base.update(kw)
      return rows.BookRow(**base)
  ```
- `BookRow.close_reason` is the lowercased-or-not text TS2 produced from `last_leg_reason` (preferred when present) over `close_reason`, as `metrics.close_reason_text` does; this part lowercases it again before matching.
- Bootstrap tests pass `n_resamples=200`.

# Phase B (continued): bar cuts, exit and supply cuts

### Task TS5: Bar-reading cuts: fill reality, gaps, liquidity, reversals

**Model:** opus — reads bars around each trade's dates, so it is no-lookahead territory (`model-routing.md`: no-lookahead → opus)

**Files:**
- Create: `scripts/reports/autopsy/bars.py`
- Test: `tests/scout/test_autopsy_bars.py`

**Interfaces:**
- Consumes (TS2, `autopsy/rows.py`): `BookRow` fields `row_kind, ticker, direction, plan_date, plan_status, plan_status_reason, entry_type, expiry_bars, valid_session, planned_entry, entry_date, entry, stop, take_profit, exit_date, close_reason, outcome, gross_r, stop_width_atr, bars`. (TS3, `autopsy/cells.py`): `Tally(id, cut, value, count, extra)`.
- Produces (ledger TS5): `SPLIT_GUARD = 0.25`; `REVERSAL_BARS = 10`; `WIDER_STOP_ATR = 0.5`; `FILL_STATUS_ORDER`; `load_bars(bars_dir: Path | None, ticker: str) -> pd.DataFrame | None`; `enrich_with_bars(rows: list[BookRow], bars_dir: Path | None) -> int` (fills `row.bars` with keys `covered, fill_day_open, open_gap_pct, gapped_through, dollar_volume, fill_status, reversal, wider_stop_lost`; returns the bar-covered count of **closed trades**); `bar_cuts()` → `(("open_gap_bucket", f), ("gapped_through_entry", f), ("dollar_volume_bucket", f), ("near_stop_reversal", f))`; `fill_tallies(rows) -> list[Tally]` (one per `FILL_STATUS_ORDER` entry, id `fill_status=<status>`, `extra = {"bar_covered": int, "of_plans": int}`). TS7 consumes all of these.

**Rules this task freezes (spec Data availability; index Global Constraints "Bars" and "No lookahead"):**
- Bars come only from `bars_dir`, file `<ticker with = ^ / → _>.csv`, columns `Date,Open,High,Low,Close,Volume`. No network, never `data/backtest_cache/` implicitly.
- **Anchor bar** = the last bar on or before `plan_date`; a row without a plan day anchors on the last bar strictly before its fill day. **Covered** = the file exists, an anchor exists, and `|anchor close − reference| / reference ≤ SPLIT_GUARD`, reference = `planned_entry`, else `entry`.
- **Dollar volume** = mean of `Close × Volume` over the 20 bars ending at the anchor; fewer than 20 bars → `None`.
- **Open gap** (filled trades only) = `(fill-day open − planned_entry) / planned_entry × 100`, signed so positive is adverse to the trade (bearish rows multiply by −1). **Gapped through**: `stop_entry` → gap > 0 (filled at a worse open), `limit` → gap < 0 (filled at a better open), `market` → `None`.
- **Fill status:** a `trade` row → `filled`; plan rows: `PENDING` → `open`; `ACTIVE`/`PARTIAL`/`CLOSED` → `filled`; `CANCELLED` + reason `risk_cap` / `invalidated` → that reason; `CANCELLED` + `expired` → `expired_unfilled` when a bar of the validity window reached the entry (live diverged from the plan), `never_touched` when none did, `unknown` without bar coverage or a complete window. The validity window is the `valid_session` bar alone when set (v144), else the `expiry_bars` bars strictly after the plan day.
- **Near-stop reversal** (stop exits only): over the `REVERSAL_BARS` bars **strictly after the exit day**, walk bar by bar: the stop widened by `WIDER_STOP_ATR × ATR` (ATR = `|entry − stop| / stop_width_atr`) is checked first on each bar; hit → `wider_stop_lost`; else a take-profit hit → `reversed_to_target`; neither in the window → `no_resolution`; fewer than `REVERSAL_BARS` bars after the exit → `None`. A stop exit is close reason `loss`/`stop`, or `auto (price monitor)` with outcome `loss`; `exits.is_stop_exit` (TS6) uses the same rule and TS7 pins that they agree.

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_autopsy_bars.py`:

```python
"""v161 TS5: bar-reading cuts -- coverage, split guard, gaps, liquidity, fill reality, reversals.

Bars are fixture CSVs in tmp_path. The rules under test are frozen in the plan
(TS5 "Rules this task freezes"); the reversal tests pin that only bars strictly
after the exit day are read."""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import bars, rows  # noqa: E402

DAYS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-02-02", periods=45)]


def _row(**kw):
    base = {f.name: None for f in fields(rows.BookRow) if f.name != "bars"}
    base.update(row_kind="trade", close_reason="", direction="bullish")
    base.update(kw)
    return rows.BookRow(**base)


def _trade(**kw):
    base = dict(ticker="AAA", plan_date=DAYS[24], entry_date=DAYS[25], planned_entry=100.0,
                entry=100.0, stop=98.0, take_profit=104.0, stop_width_atr=1.0,
                entry_type="stop_entry", gross_r=1.0, outcome="win", close_reason="tp1",
                exit_date=DAYS[28])
    base.update(kw)
    return _row(**base)


def _plan(**kw):
    base = dict(row_kind="plan", ticker="AAA", plan_date=DAYS[24], planned_entry=100.0,
                entry_type="stop_entry", expiry_bars=2, plan_status="CANCELLED",
                plan_status_reason="expired")
    base.update(kw)
    return _row(**base)


def _series(close=99.0, volume=1_000_000):
    """One bar per DAYS entry: Open = Close = close, High/Low half a point away."""
    return [[day, close, close + 0.5, close - 0.5, close, volume] for day in DAYS]


def _write(tmp_path, ticker, series):
    out = tmp_path / "bars"
    out.mkdir(exist_ok=True)
    lines = ["Date,Open,High,Low,Close,Volume"]
    lines += [",".join(str(v) for v in bar) for bar in series]
    (out / f"{ticker}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _cut(name, row):
    return dict(bars.bar_cuts())[name](row)


def test_bar_cuts_are_the_four_ledger_names_in_order():
    assert [name for name, _ in bars.bar_cuts()] == [
        "open_gap_bucket", "gapped_through_entry", "dollar_volume_bucket", "near_stop_reversal"]


def test_load_bars_uses_the_cache_file_name_and_returns_none_without_a_file(tmp_path):
    d = _write(tmp_path, "BRK_B", _series())
    _write(tmp_path, "_GSPC", _series())
    assert list(bars.load_bars(d, "BRK/B")["day"])[:2] == DAYS[:2]
    assert bars.load_bars(d, "^GSPC") is not None
    assert bars.load_bars(d, "ZZZ") is None
    assert bars.load_bars(None, "BRK/B") is None


@pytest.mark.parametrize("close, covered", [(110.0, True), (140.0, False)])
def test_the_split_guard_uncovers_rows_whose_plan_day_close_is_off_scale(tmp_path, close, covered):
    series = _series()
    series[24][4] = close
    row = _trade()
    assert bars.enrich_with_bars([row], _write(tmp_path, "AAA", series)) == int(covered)
    assert row.bars["covered"] is covered


def test_no_bars_dir_leaves_every_row_uncovered():
    row = _trade()
    assert bars.enrich_with_bars([row], None) == 0
    assert row.bars["covered"] is False
    assert row.bars["fill_status"] == "filled"
    assert all(_cut(name, row) is None for name, _ in bars.bar_cuts())


def test_the_covered_count_is_closed_trades_only(tmp_path):
    d = _write(tmp_path, "AAA", _series())
    assert bars.enrich_with_bars([_trade(), _plan(), _trade(gross_r=None)], d) == 1


def test_dollar_volume_is_the_20_bar_mean_ending_at_the_plan_day(tmp_path):
    series = _series(close=10.0)
    series[25][5] = 10 ** 9   # the fill day, after the plan day: must not count
    series[4][5] = 10 ** 9    # 21st bar back: outside the window
    row = _trade(planned_entry=10.0, entry=10.0, stop=9.8, take_profit=10.4)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["dollar_volume"] == pytest.approx(1e7)
    assert _cut("dollar_volume_bucket", row) == "lt_20m"


def test_dollar_volume_needs_twenty_bars(tmp_path):
    row = _trade(plan_date=DAYS[10], entry_date=DAYS[11])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["covered"] is True
    assert row.bars["dollar_volume"] is None
    assert _cut("dollar_volume_bucket", row) is None


@pytest.mark.parametrize("value, label", [(1e7, "lt_20m"), (3e7, "20m_50m"), (1e8, "50m_200m"),
                                          (5e8, "ge_200m")])
def test_dollar_volume_buckets(value, label):
    row = _row()
    row.bars = {"covered": True, "dollar_volume": value}
    assert _cut("dollar_volume_bucket", row) == label


def test_a_bullish_stop_entry_that_opens_above_its_trigger_gapped_through(tmp_path):
    series = _series()
    series[25][1], series[25][2] = 101.5, 102.0
    row = _trade()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_day_open"] == 101.5
    assert row.bars["open_gap_pct"] == pytest.approx(1.5)
    assert row.bars["gapped_through"] is True
    assert _cut("open_gap_bucket", row) == "adverse_large"
    assert _cut("gapped_through_entry", row) == "gapped"


def test_a_bearish_limit_that_opens_beyond_its_limit_filled_better(tmp_path):
    series = _series()
    series[25][1] = 101.0
    row = _trade(direction="bearish", entry_type="limit", stop=102.0, take_profit=96.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["open_gap_pct"] == pytest.approx(-1.0)
    assert row.bars["gapped_through"] is True
    assert _cut("open_gap_bucket", row) == "favourable"


def test_a_market_entry_has_a_gap_but_no_gapped_through_flag(tmp_path):
    row = _trade(entry_type="market", planned_entry=99.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["open_gap_pct"] == pytest.approx(0.0)
    assert _cut("open_gap_bucket", row) == "flat"
    assert row.bars["gapped_through"] is None
    assert _cut("gapped_through_entry", row) is None


@pytest.mark.parametrize("touch_index, expected", [(26, "expired_unfilled"), (27, "never_touched"),
                                                   (None, "never_touched")])
def test_an_expired_plan_is_split_by_whether_its_window_reached_the_trigger(
        tmp_path, touch_index, expected):
    series = _series()   # High 99.5, below the 100 trigger
    if touch_index is not None:
        series[touch_index][2] = 100.2   # window = DAYS[25], DAYS[26] (expiry_bars 2)
    row = _plan()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == expected


@pytest.mark.parametrize("touch_index, expected", [(27, "expired_unfilled"), (26, "never_touched")])
def test_a_valid_session_plan_only_reads_its_named_session(tmp_path, touch_index, expected):
    series = _series()
    series[touch_index][2] = 100.2
    row = _plan(valid_session=DAYS[27])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == expected


def test_a_bearish_limit_plan_is_touched_by_a_high_at_its_limit(tmp_path):
    series = _series()
    series[25][2] = 100.0
    row = _plan(direction="bearish", entry_type="limit")
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert row.bars["fill_status"] == "expired_unfilled"


def test_an_expired_plan_whose_window_runs_past_the_bars_is_unknown(tmp_path):
    row = _plan(plan_date=DAYS[43])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["fill_status"] == "unknown"


@pytest.mark.parametrize("status, reason, expected", [
    ("PENDING", None, "open"), ("ACTIVE", "stop_entry_fill", "filled"),
    ("PARTIAL", "tp1", "filled"), ("CANCELLED", "risk_cap", "risk_cap"),
    ("CANCELLED", "invalidated", "invalidated"), ("CANCELLED", "expired", "unknown"),
    ("CANCELLED", "something_else", "unknown")])
def test_plan_status_maps_to_a_fill_status_without_bars(status, reason, expected):
    row = _plan(plan_status=status, plan_status_reason=reason)
    bars.enrich_with_bars([row], None)
    assert row.bars["fill_status"] == expected


def _stopped(**kw):
    base = dict(close_reason="loss", outcome="loss", gross_r=-1.0)
    base.update(kw)
    return _trade(**base)


def test_a_stop_out_that_later_reaches_the_target_reversed(tmp_path):
    series = _series()
    series[31][2] = 104.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert (row.bars["reversal"], row.bars["wider_stop_lost"]) == (True, False)
    assert _cut("near_stop_reversal", row) == "reversed_to_target"


def test_a_wider_stop_hit_before_the_target_still_lost(tmp_path):
    series = _series()
    series[30][3] = 96.5    # wider stop = 98 - 0.5 x ATR 2 = 97
    series[31][2] = 104.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "wider_stop_lost"


def test_a_bar_hitting_both_counts_the_wider_stop_first(tmp_path):
    series = _series()
    series[30][2], series[30][3] = 104.5, 96.5
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "wider_stop_lost"


def test_the_exit_day_bar_is_never_read(tmp_path):
    series = _series()
    series[28][2] = 110.0   # the exit day itself: reading it would be lookahead into the stop bar
    row = _stopped()
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert _cut("near_stop_reversal", row) == "no_resolution"


def test_fewer_than_reversal_bars_after_the_exit_is_unknown(tmp_path):
    row = _stopped(exit_date=DAYS[40])
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", _series()))
    assert row.bars["reversal"] is None
    assert _cut("near_stop_reversal", row) is None


@pytest.mark.parametrize("reason, outcome, stopped", [
    ("loss", "loss", True), ("stop", "loss", True), ("auto (price monitor)", "loss", True),
    ("auto (price monitor)", "win", False), ("tp1_runner_tp2", "win", False),
    ("auto (near-TP stall)", "win", False)])
def test_only_stop_exits_get_a_reversal_reading(tmp_path, reason, outcome, stopped):
    series = _series()
    series[31][2] = 104.5
    row = _trade(close_reason=reason, outcome=outcome, gross_r=-1.0 if stopped else 1.0)
    bars.enrich_with_bars([row], _write(tmp_path, "AAA", series))
    assert (_cut("near_stop_reversal", row) is not None) is stopped


def test_fill_tallies_list_every_status_in_order_with_bar_covered_counts():
    filled, never, plain = _trade(), _plan(), _plan()
    filled.bars = {"fill_status": "filled", "covered": True}
    never.bars = {"fill_status": "never_touched", "covered": True}
    tallies = bars.fill_tallies([filled, never, plain])   # `plain` was never enriched
    assert [t.id for t in tallies] == [f"fill_status={s}" for s in bars.FILL_STATUS_ORDER]
    by = {t.value: t for t in tallies}
    assert by["filled"].count == 1 and by["never_touched"].count == 1
    assert by["unknown"].count == 1 and by["unknown"].extra == {"bar_covered": 0, "of_plans": 3}
    assert by["risk_cap"].count == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_autopsy_bars.py`
Expected: FAIL at collection with `ImportError: cannot import name 'bars' from 'autopsy'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/autopsy/bars.py`:

```python
"""v161 TS5: autopsy cuts that read daily bars -- fill reality, open gaps,
liquidity and near-stop reversals.

Bars come only from ``bars_dir`` (files named like
``backtest_cache.cache_path``: ``<TICKER with = ^ / -> _>.csv``, columns
``Date,Open,High,Low,Close,Volume``); this module does no network I/O. A row
is bar-covered when its file exists, it has an anchor bar and the anchor close
lies within SPLIT_GUARD of the planned entry: the cache is split- and
dividend-adjusted, so a row past the guard would compare prices on two scales.

No lookahead: dollar volume ends at the plan day; the fill-day open is known
at the fill; the reversal walk reads only bars strictly after the exit day."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path

import pandas as pd

from .cells import Tally

SPLIT_GUARD = 0.25            # fraction: anchor close vs planned entry
REVERSAL_BARS = 10            # bars after the exit day the reversal walk reads
WIDER_STOP_ATR = 0.5          # how much wider the counterfactual stop is, in ATR
DOLLAR_VOLUME_BARS = 20
GAP_FLAT_PCT = 0.25           # |open gap| at or under this is "flat"
GAP_LARGE_PCT = 1.0           # an adverse gap above this is "adverse_large"
DOLLAR_VOLUME_EDGES = ((20e6, "lt_20m"), (50e6, "20m_50m"), (200e6, "50m_200m"))
DOLLAR_VOLUME_TOP = "ge_200m"
FILLED_PLAN_STATUSES = frozenset({"ACTIVE", "PARTIAL", "CLOSED"})
FILL_STATUS_ORDER = ("filled", "expired_unfilled", "never_touched", "risk_cap",
                     "invalidated", "open", "unknown")
STOP_REASONS = frozenset({"loss", "stop"})
_CANCEL_REASONS = {"risk_cap": "risk_cap", "invalidated": "invalidated"}
# (entry_type, direction sign) -> (bar column, True when the price must reach at-or-above)
_TOUCH = {("stop_entry", 1): ("High", True), ("stop_entry", -1): ("Low", False),
          ("limit", 1): ("Low", False), ("limit", -1): ("High", True)}
_EMPTY = {"covered": False, "fill_day_open": None, "open_gap_pct": None,
          "gapped_through": None, "dollar_volume": None, "fill_status": "unknown",
          "reversal": None, "wider_stop_lost": None}


def _cache_name(ticker: str) -> str:
    """``backtest_cache.cache_path``'s file stem (not imported: its CACHE_DIR is not ours)."""
    return ticker.replace("=", "_").replace("^", "_").replace("/", "_")


def load_bars(bars_dir: Path | None, ticker: str) -> pd.DataFrame | None:
    """The ticker's daily bars sorted by day, with an ISO ``day`` column; None when absent."""
    if bars_dir is None or not ticker:
        return None
    path = Path(bars_dir) / f"{_cache_name(ticker)}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty or "Date" not in df.columns:
        return None
    df["day"] = df["Date"].astype(str).str[:10]
    return df.sort_values("day").reset_index(drop=True)


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def _sign(row) -> int:
    return 1 if row.direction == "bullish" else -1


def _is_closed_trade(row) -> bool:
    return row.row_kind == "trade" and row.gross_r is not None


def _index_of(days: list[str], day: str | None) -> int | None:
    if day is None:
        return None
    i = bisect_left(days, day)
    return i if i < len(days) and days[i] == day else None


def _anchor_index(days: list[str], row) -> int | None:
    """The plan-day bar; a row without a plan day anchors on the last bar before its fill."""
    if row.plan_date:
        i = bisect_right(days, _day(row.plan_date)) - 1
    elif row.entry_date:
        i = bisect_left(days, _day(row.entry_date)) - 1
    else:
        return None
    return i if i >= 0 else None


def _within_guard(df: pd.DataFrame, index: int, row) -> bool:
    ref = row.planned_entry if row.planned_entry is not None else row.entry
    if ref is None or ref <= 0:
        return False
    return abs(float(df["Close"].iloc[index]) - ref) / ref <= SPLIT_GUARD


def _dollar_volume(df: pd.DataFrame, index: int) -> float | None:
    if index + 1 < DOLLAR_VOLUME_BARS:
        return None
    window = df.iloc[index + 1 - DOLLAR_VOLUME_BARS: index + 1]
    return float((window["Close"] * window["Volume"]).mean())


def _gap(row, open_: float) -> tuple[float | None, bool | None]:
    """Open gap in percent, positive = adverse to the trade, and the gapped-through flag."""
    if row.planned_entry is None or row.planned_entry <= 0:
        return None, None
    pct = (open_ - row.planned_entry) / row.planned_entry * 100.0 * _sign(row)
    if row.entry_type == "stop_entry":
        return pct, pct > 0
    if row.entry_type == "limit":
        return pct, pct < 0
    return pct, None


def _fill_day_fields(df: pd.DataFrame, days: list[str], row) -> dict:
    if row.row_kind != "trade":
        return {}
    i = _index_of(days, _day(row.entry_date))
    if i is None:
        return {}
    open_ = float(df["Open"].iloc[i])
    pct, through = _gap(row, open_)
    return {"fill_day_open": open_, "open_gap_pct": pct, "gapped_through": through}


def _window(days: list[str], row) -> list[int]:
    """The plan's validity bars: its valid_session alone, else the expiry_bars bars after
    the plan day. Empty when the bars end before the window does."""
    if row.valid_session:
        i = _index_of(days, _day(row.valid_session))
        return [] if i is None else [i]
    if not row.plan_date:
        return []
    start = bisect_right(days, _day(row.plan_date))
    end = start + (row.expiry_bars or 1)
    return list(range(start, end)) if end <= len(days) else []


def _touched(df: pd.DataFrame, window: list[int], row) -> bool | None:
    if not window or row.planned_entry is None:
        return None
    if row.entry_type == "market":
        return True
    rule = _TOUCH.get((row.entry_type, _sign(row)))
    if rule is None:
        return None
    column, at_or_above = rule
    prices = df[column].iloc[window]
    hits = prices >= row.planned_entry if at_or_above else prices <= row.planned_entry
    return bool(hits.any())


def _plan_fill_status(row) -> str | None:
    """The status the plan record alone decides; None for an expired plan (bars decide)."""
    status = (row.plan_status or "").upper()
    if status == "PENDING":
        return "open"
    if status in FILLED_PLAN_STATUSES:
        return "filled"
    if status != "CANCELLED":
        return "unknown"
    reason = (row.plan_status_reason or "").lower()
    return None if reason == "expired" else _CANCEL_REASONS.get(reason, "unknown")


def _fill_status(row, df: pd.DataFrame | None, days: list[str], covered: bool) -> str:
    if row.row_kind == "trade":
        return "filled"
    decided = _plan_fill_status(row)
    if decided is not None:
        return decided
    touched = _touched(df, _window(days, row), row) if covered else None
    if touched is None:
        return "unknown"
    return "expired_unfilled" if touched else "never_touched"


def _stopped_out(row) -> bool:
    """A stop exit -- the same rule as ``exits.is_stop_exit`` (TS7 pins that they agree):
    the v2 leg reason ``loss`` (bucket ``stop``), or a legacy price-monitor close that lost."""
    reason = (row.close_reason or "").lower()
    if reason in STOP_REASONS:
        return True
    return reason.startswith("auto (price monitor)") and row.outcome == "loss"


def _wider_stop(row) -> float | None:
    if None in (row.entry, row.stop, row.take_profit) or not row.stop_width_atr:
        return None
    atr = abs(row.entry - row.stop) / row.stop_width_atr
    return row.stop - _sign(row) * WIDER_STOP_ATR * atr


def _walk_after(after: pd.DataFrame, row, wider: float) -> tuple[bool, bool]:
    """(reversed_to_target, wider_stop_lost): the wider stop is checked first on each bar."""
    bull = _sign(row) == 1
    for high, low in zip(after["High"], after["Low"]):
        if (low <= wider) if bull else (high >= wider):
            return False, True
        if (high >= row.take_profit) if bull else (low <= row.take_profit):
            return True, False
    return False, False


def _reversal(df: pd.DataFrame, days: list[str], row) -> tuple[bool | None, bool | None]:
    if not _is_closed_trade(row) or not _stopped_out(row) or not row.exit_date:
        return None, None
    wider = _wider_stop(row)
    if wider is None:
        return None, None
    start = bisect_right(days, _day(row.exit_date))   # strictly after the exit day
    after = df.iloc[start:start + REVERSAL_BARS]
    if len(after) < REVERSAL_BARS:
        return None, None
    return _walk_after(after, row, wider)


def _row_bars(row, df: pd.DataFrame | None) -> dict:
    out = dict(_EMPTY)
    days = df["day"].tolist() if df is not None else []
    anchor = _anchor_index(days, row) if days else None
    out["covered"] = anchor is not None and _within_guard(df, anchor, row)
    out["fill_status"] = _fill_status(row, df, days, out["covered"])
    if not out["covered"]:
        return out
    out["dollar_volume"] = _dollar_volume(df, anchor)
    out.update(_fill_day_fields(df, days, row))
    out["reversal"], out["wider_stop_lost"] = _reversal(df, days, row)
    return out


def enrich_with_bars(rows: list, bars_dir: Path | None) -> int:
    """Fill every row's ``bars`` dict; return how many closed trades are bar-covered."""
    cache: dict[str, pd.DataFrame | None] = {}
    covered = 0
    for row in rows:
        if row.ticker not in cache:
            cache[row.ticker] = load_bars(bars_dir, row.ticker)
        row.bars = _row_bars(row, cache[row.ticker])
        covered += int(row.bars["covered"] and _is_closed_trade(row))
    return covered


def _open_gap_bucket(row) -> str | None:
    pct = row.bars.get("open_gap_pct")
    if pct is None:
        return None
    if pct < -GAP_FLAT_PCT:
        return "favourable"
    if pct <= GAP_FLAT_PCT:
        return "flat"
    return "adverse_small" if pct <= GAP_LARGE_PCT else "adverse_large"


def _gapped_through_entry(row) -> str | None:
    flag = row.bars.get("gapped_through")
    if flag is None:
        return None
    return "gapped" if flag else "not_gapped"


def _dollar_volume_bucket(row) -> str | None:
    value = row.bars.get("dollar_volume")
    if value is None:
        return None
    for edge, label in DOLLAR_VOLUME_EDGES:
        if value < edge:
            return label
    return DOLLAR_VOLUME_TOP


def _near_stop_reversal(row) -> str | None:
    reversal = row.bars.get("reversal")
    if reversal is None:
        return None
    if reversal:
        return "reversed_to_target"
    return "wider_stop_lost" if row.bars.get("wider_stop_lost") else "no_resolution"


def bar_cuts() -> tuple:
    """The four bar cuts, in ledger order: (name, key) pairs for ``cells.cut_cells``."""
    return (("open_gap_bucket", _open_gap_bucket),
            ("gapped_through_entry", _gapped_through_entry),
            ("dollar_volume_bucket", _dollar_volume_bucket),
            ("near_stop_reversal", _near_stop_reversal))


def fill_tallies(rows: list) -> list[Tally]:
    """Fill reality over every exported row (one row = one plan or one closed trade)."""
    counts: Counter = Counter()
    covered: Counter = Counter()
    for row in rows:
        status = row.bars.get("fill_status", "unknown")
        counts[status] += 1
        covered[status] += int(bool(row.bars.get("covered")))
    total = sum(counts.values())
    return [Tally(id=f"fill_status={s}", cut="fill_status", value=s, count=counts[s],
                  extra={"bar_covered": covered[s], "of_plans": total})
            for s in FILL_STATUS_ORDER]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_autopsy_bars.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity and lookahead self-check**

Run: `python -m radon cc -s -n C $WT/scripts/reports/autopsy/bars.py`
Expected: no output (`-n C` lists rank C and worse, complexity 11 and up; every function here stays at 10 or below).

Then load the `no-lookahead` skill and walk its checklist over `bars.py`. The three answers it must find: dollar volume ends at the anchor (the plan day, or the bar before the fill); the fill-day open is read only for a row that filled that day; `_reversal` slices from `bisect_right(days, exit_day)`, so the exit bar is never read (`test_the_exit_day_bar_is_never_read`).

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/reports/autopsy/bars.py tests/scout/test_autopsy_bars.py
git -C $WT commit -m "feat(v161): autopsy bar cuts -- fill reality, gaps, liquidity, near-stop reversals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short   # main tree unchanged
```

### Task TS6: Exit and alert-supply cuts, give-back, stop extras

**Model:** sonnet — plain bucketing and tallies inside one new module, behaviour fixed by the spec and the rules below

**Files:**
- Create: `scripts/reports/autopsy/exits.py`
- Test: `tests/scout/test_autopsy_exits.py`

**Interfaces:**
- Consumes (TS2): `BookRow` fields `row_kind, horizon, plan_date, plan_hour, close_reason, outcome, gross_r, net_r, mfe_r, holding_days, stop_width_atr`; `RejectionCount(date: str, reason: str, count: int)`. (TS3): `Tally(id, cut, value, count, extra)`. Existing: `swingbot/core/analytics/metrics.py:819 _exit_reason_bucket(trade: dict) -> str` (the live book's own exit-bucket rule, reused so the autopsy and `/stats` share one vocabulary: `tp1, runner_tp2, runner_trail, runner_be, stop, scratch, timeout, reversed, other`).
- Produces (ledger TS6): `exit_cuts()` → `(("exit_reason", f), ("near_tp_close", f), ("gap_through_stop", f), ("holding_bucket", f))`; `STOP_CUTS = frozenset({"exit_reason", "gap_through_stop", "near_stop_reversal"})`; `is_stop_exit(row) -> bool`; `stop_extra(members: list[BookRow], balance: float) -> dict` with keys `mean_stop_atr`, `dollar_loss_at_2pct`, `mean_overshoot_r` (the gap size the spec asks for beside gap-through-stop); `giveback_summary(trades: list[BookRow]) -> dict` (`n`, `mean`, `median`); `alert_supply_tallies(rows: list[BookRow], rejections: list[RejectionCount]) -> list[Tally]`. TS7 consumes all of these.

**Rules this task freezes:**
- **Exit reason** = `_exit_reason_bucket({"close_reason": row.close_reason})`, no `status` key, so the reason text decides (`auto (near-TP timeout)` lands in `timeout` through `resolve_outcome`'s substring test instead of being masked by the `win` status).
- **Near-TP close:** `auto (near-tp stall)` → `near_tp_stall`, `auto (near-tp timeout)` → `near_tp_timeout` (case-insensitive, spec Data availability), every other closed trade → `other_exit`.
- **Stop exit** (`is_stop_exit`): close reason `loss` or `stop`, or `auto (price monitor)` with outcome `loss`. Same rule as `bars._stopped_out` (TS5); TS7 pins that they agree.
- **Gap-through-stop** (stop exits only): `round(gross_r, 2) < −1.0` → `through_stop`, else `at_stop`. `mean_overshoot_r` = mean of `−1.0 − gross_r` over the cell's through-stop members.
- **Holding bucket** = `<horizon>|<le_2d | 3_5d | 6_10d | gt_10d>` from `holding_days`; `None` without a horizon or holding days.
- **Stop extras:** `mean_stop_atr` = mean `stop_width_atr`; `dollar_loss_at_2pct` = mean loss in net R over losing members × 2% × balance (the dollar view at fixed 2% risk); each `None` when it has no inputs.
- **Give-back** = `mfe_r − gross_r` over **every** trade with both (winners and losers, spec panel finding).
- **Alert supply** (every exported row with a `plan_date` is one issued plan): `alerts_per_day=<1 | 2_3 | 4_6 | 7_plus>` counts plan-days by how many plans they issued (`extra.plans` = plans on those days); `alert_hour_session=<premarket | regular | after_close | unknown>` from `plan_hour` (hour < 9 premarket, < 16 regular, else after_close; hour granularity, so 09:00–09:29 counts as regular); `actionable_before_open=<yes | no | unknown>`: yes = issued while the market was closed (premarket or after the close), no = issued during the regular session; `rejection_reason=<reason>` sums the rejections CSV per reason (`extra.days` = distinct dates), most frequent first. A `;` in a reason becomes `,` (cell ids never carry `;`).

- [ ] **Step 1: Write the failing test**

Create `tests/scout/test_autopsy_exits.py`:

```python
"""v161 TS6: exit cuts, give-back over all trades, stop extras and alert-supply tallies."""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import exits, rows  # noqa: E402


def _row(**kw):
    base = {f.name: None for f in fields(rows.BookRow) if f.name != "bars"}
    base.update(row_kind="trade", close_reason="", direction="bullish")
    base.update(kw)
    return rows.BookRow(**base)


def _cut(name, row):
    return dict(exits.exit_cuts())[name](row)


def test_exit_cuts_are_the_four_ledger_names_in_order():
    assert [name for name, _ in exits.exit_cuts()] == [
        "exit_reason", "near_tp_close", "gap_through_stop", "holding_bucket"]
    assert exits.STOP_CUTS == {"exit_reason", "gap_through_stop", "near_stop_reversal"}


@pytest.mark.parametrize("reason, bucket", [
    ("loss", "stop"), ("tp1", "tp1"), ("tp1_runner_tp2", "runner_tp2"), ("tp1_runner_be", "runner_be"),
    ("scratch", "scratch"), ("time_exit", "timeout"), ("auto (near-TP stall)", "timeout"),
    ("auto (near-TP timeout)", "timeout"), ("auto (price monitor)", "other")])
def test_exit_reason_uses_the_live_book_bucket_rule(reason, bucket):
    assert _cut("exit_reason", _row(close_reason=reason, outcome="win", gross_r=0.5)) == bucket


@pytest.mark.parametrize("reason, label", [
    ("auto (near-TP stall)", "near_tp_stall"), ("AUTO (NEAR-TP TIMEOUT)", "near_tp_timeout"),
    ("loss", "other_exit"), ("", "other_exit")])
def test_near_tp_closes_are_split_from_every_other_exit(reason, label):
    assert _cut("near_tp_close", _row(close_reason=reason, gross_r=0.4)) == label


@pytest.mark.parametrize("reason, outcome, stop", [
    ("loss", "loss", True), ("STOP", "loss", True), ("auto (price monitor)", "loss", True),
    ("auto (price monitor)", "win", False), ("tp1", "win", False), (None, "loss", False)])
def test_is_stop_exit(reason, outcome, stop):
    assert exits.is_stop_exit(_row(close_reason=reason, outcome=outcome)) is stop


@pytest.mark.parametrize("reason, gross, label", [
    ("loss", -1.4, "through_stop"), ("loss", -1.0, "at_stop"), ("loss", -1.004, "at_stop"),
    ("tp1", -1.4, None)])
def test_gap_through_stop_is_read_on_stop_exits_only(reason, gross, label):
    row = _row(close_reason=reason, outcome="loss" if reason == "loss" else "win", gross_r=gross)
    assert _cut("gap_through_stop", row) == label


@pytest.mark.parametrize("days, label", [(1.0, "2w|le_2d"), (4.0, "2w|3_5d"), (10.0, "2w|6_10d"),
                                         (11.0, "2w|gt_10d")])
def test_holding_bucket_is_per_horizon(days, label):
    assert _cut("holding_bucket", _row(horizon="2w", holding_days=days, gross_r=0.1)) == label


def test_holding_bucket_needs_a_horizon_and_holding_days():
    assert _cut("holding_bucket", _row(horizon=None, holding_days=3.0)) is None
    assert _cut("holding_bucket", _row(horizon="2w", holding_days=None)) is None


def test_stop_extra_reports_atr_width_dollar_loss_at_fixed_risk_and_overshoot():
    members = [
        _row(stop_width_atr=1.0, net_r=-1.0, gross_r=-1.0, close_reason="loss", outcome="loss"),
        _row(stop_width_atr=2.0, net_r=-1.5, gross_r=-1.5, close_reason="loss", outcome="loss"),
        _row(stop_width_atr=None, net_r=0.5, gross_r=0.6, close_reason="tp1", outcome="win"),
    ]
    extra = exits.stop_extra(members, balance=10_000.0)
    assert extra["mean_stop_atr"] == pytest.approx(1.5)
    assert extra["dollar_loss_at_2pct"] == pytest.approx(250.0)   # 1.25 R x 2% x 10 000
    assert extra["mean_overshoot_r"] == pytest.approx(0.5)


def test_stop_extra_without_inputs_is_none_not_zero():
    assert exits.stop_extra([_row(net_r=0.4, gross_r=0.5)], balance=10_000.0) == {
        "mean_stop_atr": None, "dollar_loss_at_2pct": None, "mean_overshoot_r": None}


def test_giveback_covers_losers_as_well_as_winners():
    trades = [_row(mfe_r=2.0, gross_r=1.0), _row(mfe_r=1.5, gross_r=-1.0),
              _row(mfe_r=None, gross_r=0.3)]
    assert exits.giveback_summary(trades) == {"n": 2, "mean": 1.75, "median": 1.75}
    assert exits.giveback_summary([]) == {"n": 0, "mean": None, "median": None}


def _plans():
    out = [_row(row_kind="plan", plan_date="2026-03-02", plan_hour=7)]
    out += [_row(row_kind="plan", plan_date="2026-03-03", plan_hour=h) for h in (12, 17, None)]
    out += [_row(row_kind="trade", plan_date="2026-03-04 14:00:00", plan_hour=8) for _ in range(8)]
    out.append(_row(row_kind="trade", plan_date=None, plan_hour=None))   # a trade with no plan
    return out


def test_alert_supply_tallies_count_days_sessions_and_rejections():
    rejections = [rows.RejectionCount(date="2026-03-02", reason="risk_cap", count=4),
                  rows.RejectionCount(date="2026-03-03", reason="risk_cap", count=1),
                  rows.RejectionCount(date="2026-03-03", reason="a;b", count=2)]
    tallies = exits.alert_supply_tallies(_plans(), rejections)
    by = {t.id: t for t in tallies}
    assert [t.id for t in tallies][:4] == [
        "alerts_per_day=1", "alerts_per_day=2_3", "alerts_per_day=4_6", "alerts_per_day=7_plus"]
    assert (by["alerts_per_day=1"].count, by["alerts_per_day=1"].extra) == (1, {"plans": 1})
    assert (by["alerts_per_day=2_3"].count, by["alerts_per_day=2_3"].extra) == (1, {"plans": 3})
    assert (by["alerts_per_day=7_plus"].count, by["alerts_per_day=7_plus"].extra) == (1, {"plans": 8})
    assert by["alerts_per_day=4_6"].count == 0
    assert by["alert_hour_session=premarket"].count == 9
    assert by["alert_hour_session=regular"].count == 1
    assert by["alert_hour_session=after_close"].count == 1
    assert by["alert_hour_session=unknown"].count == 1
    assert (by["actionable_before_open=yes"].count, by["actionable_before_open=no"].count,
            by["actionable_before_open=unknown"].count) == (10, 1, 1)
    assert [t.id for t in tallies if t.cut == "rejection_reason"] == [
        "rejection_reason=risk_cap", "rejection_reason=a,b"]
    assert by["rejection_reason=risk_cap"].count == 5
    assert by["rejection_reason=risk_cap"].extra == {"days": 2}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py`
Expected: FAIL at collection with `ImportError: cannot import name 'exits' from 'autopsy'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/reports/autopsy/exits.py`:

```python
"""v161 TS6: autopsy exit cuts, give-back over every trade, stop-cell extras and
the alert-supply tallies (alerts per day, alert hour against the session,
issued-before-the-open, rejected-plan reasons).

The exit bucket is the live book's own rule (``metrics._exit_reason_bucket``),
so the autopsy and ``/stats`` speak one vocabulary."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from swingbot.core.analytics.metrics import _exit_reason_bucket

from .cells import Tally

STOP_CUTS = frozenset({"exit_reason", "gap_through_stop", "near_stop_reversal"})
STOP_REASONS = frozenset({"loss", "stop"})
RISK_FRACTION = 0.02          # the fixed 2% dollar risk the dollar view is priced at
GAP_THROUGH_R = -1.0          # a stop exit below this (rounded to 0.01 R) gapped through
HOLDING_EDGES = ((2, "le_2d"), (5, "3_5d"), (10, "6_10d"))
HOLDING_TOP = "gt_10d"
ALERTS_PER_DAY_EDGES = ((1, "1"), (3, "2_3"), (6, "4_6"))
ALERTS_PER_DAY_TOP = "7_plus"
REGULAR_OPEN_HOUR = 9         # hour granularity: 09:00-09:29 counts as regular
REGULAR_CLOSE_HOUR = 16
SESSIONS = ("premarket", "regular", "after_close", "unknown")
_NEAR_TP = {"auto (near-tp stall)": "near_tp_stall", "auto (near-tp timeout)": "near_tp_timeout"}


def _reason(row) -> str:
    return (row.close_reason or "").strip().lower()


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def is_stop_exit(row) -> bool:
    """A stop exit: the v2 leg reason ``loss`` (bucket ``stop``), or a legacy
    price-monitor close that lost. Same rule as ``bars._stopped_out``."""
    reason = _reason(row)
    if reason in STOP_REASONS:
        return True
    return reason.startswith("auto (price monitor)") and row.outcome == "loss"


def _exit_reason(row) -> str | None:
    return _exit_reason_bucket({"close_reason": row.close_reason or ""})


def _near_tp_close(row) -> str | None:
    return _NEAR_TP.get(_reason(row), "other_exit")


def _gap_through_stop(row) -> str | None:
    if row.gross_r is None or not is_stop_exit(row):
        return None
    return "through_stop" if round(row.gross_r, 2) < GAP_THROUGH_R else "at_stop"


def _holding_bucket(row) -> str | None:
    if row.holding_days is None or not row.horizon:
        return None
    for edge, label in HOLDING_EDGES:
        if row.holding_days <= edge:
            return f"{row.horizon}|{label}"
    return f"{row.horizon}|{HOLDING_TOP}"


def exit_cuts() -> tuple:
    """The four exit cuts, in ledger order: (name, key) pairs for ``cells.cut_cells``."""
    return (("exit_reason", _exit_reason), ("near_tp_close", _near_tp_close),
            ("gap_through_stop", _gap_through_stop), ("holding_bucket", _holding_bucket))


def _overshoots(members: list) -> list[float]:
    return [GAP_THROUGH_R - r.gross_r for r in members
            if _gap_through_stop(r) == "through_stop"]


def stop_extra(members: list, balance: float) -> dict:
    """Stop distance in ATR, mean dollar loss at fixed 2% risk, and the gap past -1 R."""
    widths = [r.stop_width_atr for r in members if r.stop_width_atr is not None]
    losses = [r.net_r for r in members if r.net_r is not None and r.net_r < 0]
    loss = _mean(losses)
    return {"mean_stop_atr": _mean(widths),
            "dollar_loss_at_2pct": None if loss is None else round(-loss * RISK_FRACTION * balance, 2),
            "mean_overshoot_r": _mean(_overshoots(members))}


def giveback_summary(trades: list) -> dict:
    """``mfe_r - gross_r`` over every trade that has both -- losers included."""
    values = [r.mfe_r - r.gross_r for r in trades if r.mfe_r is not None and r.gross_r is not None]
    if not values:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(values), "mean": _mean(values),
            "median": round(statistics.median(values), 4)}


def _per_day_label(n: int) -> str:
    for edge, label in ALERTS_PER_DAY_EDGES:
        if n <= edge:
            return label
    return ALERTS_PER_DAY_TOP


def _alerts_per_day(issued: list) -> list[Tally]:
    per_day = Counter(str(r.plan_date)[:10] for r in issued)
    days: Counter = Counter()
    plans: Counter = Counter()
    for n in per_day.values():
        label = _per_day_label(n)
        days[label] += 1
        plans[label] += n
    labels = [label for _, label in ALERTS_PER_DAY_EDGES] + [ALERTS_PER_DAY_TOP]
    return [Tally(id=f"alerts_per_day={lab}", cut="alerts_per_day", value=lab,
                  count=days[lab], extra={"plans": plans[lab]}) for lab in labels]


def _session_of(hour: int | None) -> str:
    if hour is None:
        return "unknown"
    if hour < REGULAR_OPEN_HOUR:
        return "premarket"
    return "regular" if hour < REGULAR_CLOSE_HOUR else "after_close"


def _hour_tallies(issued: list) -> list[Tally]:
    sessions = Counter(_session_of(r.plan_hour) for r in issued)
    out = [Tally(id=f"alert_hour_session={s}", cut="alert_hour_session", value=s,
                 count=sessions[s]) for s in SESSIONS]
    before = {"yes": sessions["premarket"] + sessions["after_close"],
              "no": sessions["regular"], "unknown": sessions["unknown"]}
    out += [Tally(id=f"actionable_before_open={k}", cut="actionable_before_open", value=k,
                  count=v) for k, v in before.items()]
    return out


def _rejection_tallies(rejections: list) -> list[Tally]:
    counts: Counter = Counter()
    days: defaultdict = defaultdict(set)
    for rej in rejections:
        reason = rej.reason.replace(";", ",")
        counts[reason] += rej.count
        days[reason].add(rej.date)
    ordered = sorted(counts, key=lambda r: (-counts[r], r))
    return [Tally(id=f"rejection_reason={r}", cut="rejection_reason", value=r,
                  count=counts[r], extra={"days": len(days[r])}) for r in ordered]


def alert_supply_tallies(rows: list, rejections: list) -> list[Tally]:
    """Alerts per day, alert hour against the session, issued-before-the-open, rejections."""
    issued = [r for r in rows if r.plan_date]
    return _alerts_per_day(issued) + _hour_tallies(issued) + _rejection_tallies(rejections)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/reports/autopsy/exits.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/reports/autopsy/exits.py tests/scout/test_autopsy_exits.py
git -C $WT commit -m "feat(v161): autopsy exit and alert-supply cuts, give-back over all trades

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short   # main tree unchanged
```

