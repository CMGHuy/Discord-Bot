# v172 Equity candlestick chart, part 1b: candle bucketing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V172-3:" -A 400 docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_1b-candles.md`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md) (its `## Corrections from the code brief` and the § 3 raw-bar decision win over earlier wording)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md) — **Global Constraints, Parallelisation, the task ledger and `$WT`/`$R` are defined there; every task below implicitly includes the Global Constraints.** Split from part 1 (`_1-core.md`, V172-1..V172-2) to keep each file under 1500 lines.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C $WT`.

# Phase 1 — Core (continued)

### Task V172-3: Candle bucketing, pure functions

**Model:** sonnet — pure functions in one module, behaviour fixed by the spec

**Files:**
- Create: `swingbot/core/tracking/equity_candles.py`
- Test: `tests/tracking/test_equity_candles.py` (suite `storage`)

**Interfaces:**
- Consumes: `CENT`, `RealizedLeg`, `to_decimal` from `swingbot/core/tracking/equity.py` (V172-1); `US_MARKET_TZ` (`swingbot/core/market/session.py:12`).
- Produces (ledger contract, consumed by V172-5):
  - `TIMEFRAMES = ("1H", "4H", "1D", "1W")`
  - `bucket_start(at: datetime, tf: str) -> datetime` — New York-aware bucket start; `ValueError` on an unknown `tf`
  - `bucket_label(start: datetime, tf: str) -> str` — ISO date for 1D/1W, ISO datetime with offset for 1H/4H
  - `mtm_candles(rows: list[dict], tf: str) -> list[dict]` — rows as `EquitySampleRepository.list_rows` returns them (`at` aware, `equity`, `skipped_n`, `source`, `kind`, `id`)
  - `realized_candles(legs: Sequence[RealizedLeg], start: Decimal, tf: str) -> list[dict]`
  - `add_change(candles: list[dict]) -> list[dict]` — candles in time order with `o/h/l/c` (Decimal or float); returns dicts with keys exactly `t, o, h, l, c, change, change_pct, samples, skipped, approx`, money floats rounded 2 dp
  - `limit` is not applied here: V172-5 slices `candles[-limit:]` after these functions, so the first returned candle keeps its true `change`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/tracking/test_equity_candles.py`:

```python
"""v172 § 4: equity candles from raw samples and realized legs.

New York wall clock throughout. 2026 DST: spring forward Sun 8 March (02:00
EST -> 03:00 EDT), fall back Sun 1 November (02:00 EDT -> 01:00 EST).
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from swingbot.core.tracking.equity import RealizedLeg
from swingbot.core.tracking.equity_candles import (
    TIMEFRAMES, add_change, bucket_label, bucket_start, mtm_candles, realized_candles)

UTC = timezone.utc


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def _label(at, tf):
    return bucket_label(bucket_start(at, tf), tf)


def _row(at, equity, *, kind="point", source="live", skipped=0, row_id=0):
    return {"id": row_id, "at": at, "equity": equity, "kind": kind, "source": source,
            "skipped_n": skipped}


def test_the_four_timeframes():
    assert TIMEFRAMES == ("1H", "4H", "1D", "1W")


def test_an_unknown_timeframe_is_refused():
    with pytest.raises(ValueError):
        bucket_start(_utc(2026, 10, 16, 14), "15m")


def test_the_day_turns_at_new_york_midnight_not_utc():
    assert _label(_utc(2026, 10, 17, 3, 59), "1D") == "2026-10-16"     # 23:59 New York
    assert _label(_utc(2026, 10, 17, 4, 1), "1D") == "2026-10-17"      # 00:01 New York


def test_hour_labels_carry_the_new_york_offset():
    assert _label(_utc(2026, 10, 16, 14, 35), "1H") == "2026-10-16T10:00:00-04:00"
    assert _label(_utc(2026, 10, 16, 14, 35), "4H") == "2026-10-16T08:00:00-04:00"


def test_the_week_starts_on_monday():
    assert _label(_utc(2026, 10, 18, 15), "1W") == "2026-10-12"        # Sunday
    assert _label(_utc(2026, 10, 19, 15), "1W") == "2026-10-19"        # Monday


def test_4h_bucket_is_three_real_hours_on_spring_forward_day():
    first = bucket_start(_utc(2026, 3, 8, 7, 30), "4H")                # 03:30 EDT
    assert first == bucket_start(_utc(2026, 3, 8, 5, 30), "4H")        # 00:30 EST, same bucket
    assert first.astimezone(UTC) == _utc(2026, 3, 8, 5)                # 00:00 EST
    second = bucket_start(_utc(2026, 3, 8, 8, 0), "4H")                # 04:00 EDT
    assert (second.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 3 * 3600   # same-zone subtraction is wall-clock


def test_4h_bucket_is_five_real_hours_on_fall_back_day():
    first = bucket_start(_utc(2026, 11, 1, 8, 30), "4H")               # 03:30 EST
    assert first.astimezone(UTC) == _utc(2026, 11, 1, 4)               # 00:00 EDT
    second = bucket_start(_utc(2026, 11, 1, 9, 0), "4H")               # 04:00 EST
    assert (second.astimezone(UTC) - first.astimezone(UTC)).total_seconds() == 5 * 3600   # same-zone subtraction is wall-clock


def test_the_repeated_hour_on_fall_back_day_is_two_1h_buckets():
    assert _label(_utc(2026, 11, 1, 5, 30), "1H") == "2026-11-01T01:00:00-04:00"
    assert _label(_utc(2026, 11, 1, 6, 30), "1H") == "2026-11-01T01:00:00-05:00"


# --- mark-to-market -----------------------------------------------------------

BACKFILL_DAY = [  # Thu 15 Oct: open 13:30Z, close 20:00Z
    _row(_utc(2026, 10, 15, 13, 30), 10000.0, source="backfill", row_id=1),
    _row(_utc(2026, 10, 15, 13, 30), 10300.0, kind="day_high", source="backfill", skipped=1, row_id=2),
    _row(_utc(2026, 10, 15, 13, 30), 9900.0, kind="day_low", source="backfill", row_id=3),
    _row(_utc(2026, 10, 15, 20, 0), 10100.0, source="backfill", row_id=4),
]
LIVE_DAY = [  # Fri 16 Oct
    _row(_utc(2026, 10, 16, 14, 0), 10150.0, row_id=5),
    _row(_utc(2026, 10, 16, 15, 0), 10250.0, row_id=6),
    _row(_utc(2026, 10, 16, 19, 55), 10200.0, row_id=7),
]
CANDLE_KEYS = ["t", "o", "h", "l", "c", "change", "change_pct", "samples", "skipped", "approx"]


def test_daily_mtm_reads_o_and_c_from_points_and_h_l_from_every_row():
    first, second = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1D")
    assert list(first) == CANDLE_KEYS
    assert first == {"t": "2026-10-15", "o": 10000.0, "h": 10300.0, "l": 9900.0, "c": 10100.0,
                     "change": 100.0, "change_pct": 1.0, "samples": 4, "skipped": 1, "approx": True}
    assert second == {"t": "2026-10-16", "o": 10150.0, "h": 10250.0, "l": 10150.0, "c": 10200.0,
                      "change": 100.0, "change_pct": 0.99, "samples": 3, "skipped": 0,
                      "approx": False}


def test_rows_arrive_in_any_order():
    assert mtm_candles(list(reversed(BACKFILL_DAY + LIVE_DAY)), "1D") == mtm_candles(
        BACKFILL_DAY + LIVE_DAY, "1D")


def test_empty_buckets_are_omitted():
    monday = [_row(_utc(2026, 10, 19, 14), 10300.0, row_id=8)]
    candles = mtm_candles(LIVE_DAY + monday, "1D")
    assert [c["t"] for c in candles] == ["2026-10-16", "2026-10-19"]
    assert candles[1]["change"] == 100.0                               # vs Friday's close


def test_intraday_mtm_never_reads_backfill_rows():
    candles = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1H")
    assert [c["t"] for c in candles] == ["2026-10-16T10:00:00-04:00", "2026-10-16T11:00:00-04:00",
                                         "2026-10-16T15:00:00-04:00"]
    assert not any(c["approx"] for c in candles)
    assert candles[0]["change"] == 0.0                                 # first: c - its own o


def test_the_week_aggregates_both_days():
    (week,) = mtm_candles(BACKFILL_DAY + LIVE_DAY, "1W")
    assert (week["t"], week["o"], week["h"], week["l"], week["c"]) == (
        "2026-10-12", 10000.0, 10300.0, 9900.0, 10200.0)
    assert (week["samples"], week["skipped"], week["approx"]) == (7, 1, True)


def test_no_rows_no_candles():
    assert mtm_candles([], "1D") == []


# --- change -------------------------------------------------------------------

def test_change_pct_is_null_when_the_base_is_zero():
    (candle,) = add_change([{"t": "2026-10-16", "o": 0, "h": 5, "l": 0, "c": 5,
                             "samples": 1, "skipped": 0, "approx": False}])
    assert (candle["change"], candle["change_pct"]) == (5.0, None)


def test_change_is_measured_from_the_previous_close():
    candles = add_change([
        {"t": "a", "o": 100, "h": 110, "l": 95, "c": 105, "samples": 1, "skipped": 0, "approx": False},
        {"t": "b", "o": 108, "h": 108, "l": 101.333, "c": 101.333, "samples": 1, "skipped": 0,
         "approx": False}])
    assert [(c["change"], c["change_pct"]) for c in candles] == [(5.0, 5.0), (-3.67, -3.49)]
    assert candles[1]["l"] == 101.33


# --- realized basis -----------------------------------------------------------

def _leg(at, amount):
    return RealizedLeg(at=at, amount=Decimal(str(amount)), trade_id="t")


def test_realized_steps_through_each_leg_of_the_day():
    legs = [_leg(_utc(2026, 10, 14, 15), 50.0),      # TP1
            _leg(_utc(2026, 10, 14, 19), -80.0),
            _leg(_utc(2026, 10, 14, 19, 30), 20.0),
            _leg(_utc(2026, 10, 16, 18), 100.0)]
    first, second = realized_candles(legs, Decimal("10000"), "1D")
    assert first == {"t": "2026-10-14", "o": 10000.0, "h": 10050.0, "l": 9970.0, "c": 9990.0,
                     "change": -10.0, "change_pct": -0.1, "samples": 3, "skipped": 0,
                     "approx": False}
    assert second == {"t": "2026-10-16", "o": 9990.0, "h": 10090.0, "l": 9990.0, "c": 10090.0,
                      "change": 100.0, "change_pct": 1.0, "samples": 1, "skipped": 0,
                      "approx": False}


def test_a_day_with_no_leg_has_no_realized_candle():
    assert realized_candles([], Decimal("10000"), "1D") == []
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/tracking/test_equity_candles.py
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.tracking.equity_candles'`.

- [ ] **Step 3: Write the module**

Create `$WT/swingbot/core/tracking/equity_candles.py`:

```python
"""v172 § 4: equity candles, built on request from raw samples or realized legs.

Pure functions, no I/O. Buckets follow the New York wall clock: 1H = clock
hours; 4H starts at 00/04/08/12/16/20 (3 or 5 real hours on DST days); 1D =
the New York calendar day; 1W starts Monday. A bucket with nothing in it
produces no candle.

- **mtm:** `o`/`c` = the earliest/latest `point` row's `equity`; `h`/`l`
  over every row (backfill `day_high`/`day_low` included); `skipped` = the
  max `skipped_n`; `approx` = any backfill row. 1H/4H read `live` rows only.
- **realized:** each leg is a step; `o` = the balance before the bucket's
  first leg, `h`/`l` across the steps (and `o`), `c` = after the last.
- `change` is against the previous candle's `c` (the first against its own
  `o`); `change_pct` is that over the base x 100, 2 dp, None on a 0 base.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.tracking.equity import CENT, RealizedLeg, to_decimal

TIMEFRAMES = ("1H", "4H", "1D", "1W")
_INTRADAY = ("1H", "4H")


def _floor_hour(local: datetime) -> datetime:
    # replace() keeps `fold`, so the repeated 01:00 on fall-back day stays two hours.
    return local.replace(minute=0, second=0, microsecond=0)


def _floor_4h(local: datetime) -> datetime:
    return local.replace(hour=local.hour - local.hour % 4, minute=0, second=0, microsecond=0,
                         fold=0)


def _floor_day(local: datetime) -> datetime:
    return local.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)


def _floor_week(local: datetime) -> datetime:
    monday = local.date() - timedelta(days=local.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=US_MARKET_TZ)


_FLOORS = {"1H": _floor_hour, "4H": _floor_4h, "1D": _floor_day, "1W": _floor_week}


def bucket_start(at: datetime, tf: str) -> datetime:
    """The New York-aware start of the `tf` bucket holding instant `at`."""
    floor = _FLOORS.get(tf)
    if floor is None:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    return floor(at.astimezone(US_MARKET_TZ))


def bucket_label(start: datetime, tf: str) -> str:
    """`t` of a candle: ISO date for 1D/1W, ISO datetime with offset for 1H/4H."""
    if tf in _INTRADAY:
        return start.isoformat(timespec="seconds")
    return start.date().isoformat()


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _pct(change: Decimal, base: Decimal) -> float | None:
    if base == 0:
        return None
    return float((change / base * 100).quantize(CENT, rounding=ROUND_HALF_UP))


def add_change(candles: list[dict]) -> list[dict]:
    """The final candle dicts, in order, with `change`/`change_pct` against
    the previous candle's close (the first against its own open)."""
    out, previous = [], None
    for candle in candles:
        o, h, l, c = (to_decimal(candle[key]) for key in ("o", "h", "l", "c"))
        base = o if previous is None else previous
        change = c - base
        out.append({"t": candle["t"], "o": _money(o), "h": _money(h), "l": _money(l),
                    "c": _money(c), "change": _money(change), "change_pct": _pct(change, base),
                    "samples": candle["samples"], "skipped": candle["skipped"],
                    "approx": candle["approx"]})
        previous = c
    return out


def _group(items: list, at_of, tf: str) -> dict[str, list]:
    """Items grouped by bucket label, buckets in time order (items sorted first)."""
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(bucket_label(bucket_start(at_of(item), tf), tf), []).append(item)
    return groups


def _mtm_candle(label: str, rows: list[dict]) -> dict | None:
    points = [row for row in rows if row["kind"] == "point"]
    if not points:
        return None
    values = [to_decimal(row["equity"]) for row in rows]
    return {"t": label, "o": to_decimal(points[0]["equity"]), "h": max(values), "l": min(values),
            "c": to_decimal(points[-1]["equity"]), "samples": len(rows),
            "skipped": max(int(row.get("skipped_n") or 0) for row in rows),
            "approx": any(row["source"] == "backfill" for row in rows)}


def mtm_candles(rows: list[dict], tf: str) -> list[dict]:
    """Mark-to-market candles from `equity_samples` rows."""
    if tf not in TIMEFRAMES:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    usable = [row for row in rows if tf not in _INTRADAY or row["source"] == "live"]
    usable.sort(key=lambda row: (row["at"], row.get("id") or 0))
    candles = (_mtm_candle(label, bucket) for label, bucket in
               _group(usable, lambda row: row["at"], tf).items())
    return add_change([candle for candle in candles if candle is not None])


def realized_candles(legs: Sequence[RealizedLeg], start: Decimal, tf: str) -> list[dict]:
    """Closed-trades-only candles: one step per realized leg."""
    if tf not in TIMEFRAMES:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    balance = to_decimal(start)
    candles = []
    for label, bucket in _group(sorted(legs, key=lambda leg: leg.at), lambda leg: leg.at, tf).items():
        opening, steps = balance, []
        for leg in bucket:
            balance += leg.amount
            steps.append(balance)
        candles.append({"t": label, "o": opening, "h": max([opening, *steps]),
                        "l": min([opening, *steps]), "c": steps[-1], "samples": len(steps),
                        "skipped": 0, "approx": False})
    return add_change(candles)
```

- [ ] **Step 4: Run the tests to see them pass**

```bash
python $WT/scripts/dev/testrun.py file tests/tracking/test_equity_candles.py
python -m radon cc -s -n C $WT/swingbot/core/tracking/equity_candles.py
```

Expected: every test passes; radon prints nothing. If a DST test fails, print `bucket_start(...)` and its `.utcoffset()` for the failing instant before changing code: `_floor_4h` and `_floor_day` must reset `fold` to 0 and `_floor_hour` must keep it.

- [ ] **Step 5: Commit on the branch**

```bash
git -C $WT add swingbot/core/tracking/equity_candles.py tests/tracking/test_equity_candles.py
git -C $WT commit -m "feat(tracking): equity candle bucketing on the New York clock, mtm and realized bases (v172)"
git -C $R status --short
```

End the commit message with the attribution line from the session's system reminder. Expected: one commit on the branch; `$R`'s status shows no change from this task.
