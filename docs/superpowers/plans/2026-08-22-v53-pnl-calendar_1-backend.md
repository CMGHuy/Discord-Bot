**Part 1 of 3** — `2026-08-22-v53-pnl-calendar_0-index.md` carries the header
block, goal, Global Constraints and the parallelisation map. **Read the index's
Global Constraints before starting any task here.**

Part 2 (`_2-frontend`) consumes the JSON response shapes Tasks 4 and 5 finalize.

---

# Phase 1 — Core aggregation

### Task 1: The trade join and day bucketing

**Files:**
- Create: `swingbot/core/analytics/pnl_calendar.py`
- Test: `tests/analytics/test_pnl_calendar.py`

**Interfaces:**
- Consumes: `metrics.r_multiple` (`swingbot/core/analytics/metrics.py:96`),
  `primary_strategy_label`
  (`swingbot/core/tracking/performance.py:162`), `TradeLog`
  (`performance.py:217`, `__init__(self, path=None)`), `JournalStore`
  (`swingbot/core/analytics/journal.py:24`, `__init__(self, path=None)`).
- Produces: `CLOSED_STATUSES: frozenset[str]`;
  `day_of(closed_at: str | None) -> str | None`;
  `joined_rows(trades: list[dict], entries: list[dict]) -> list[dict]` where
  each row has exactly the 15 keys listed in Step 3;
  `filter_rows(rows, *, strategy=None, horizon=None) -> list[dict]`;
  `available_filters(rows) -> dict` → `{"strategies": [...], "horizons": [...]}`;
  `load_rows(*, trade_log=None, journal=None) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `tests/analytics/test_pnl_calendar.py`:

```python
"""Day-level P&L aggregation for the /calendar workspace (plan v53).

Every expected value below is hand-computed, per the house convention in
tests/analytics/test_metrics_derived.py -- never copied from a run.
"""
import pytest

from swingbot.core.analytics.pnl_calendar import (available_filters, day_of,
                                                  filter_rows, joined_rows)


def _trade(trade_id, *, closed_at="2026-08-03T20:00:00+00:00", status="win",
           entry=100.0, exit_price=110.0, stop=95.0, pnl=50.0,
           direction="bullish", horizon="4w", ticker="AAPL"):
    """One closed trades.json record. `strategy` is deliberately the literal
    every live confluence trade carries -- see Global Constraint 3."""
    return {
        "id": trade_id, "ticker": ticker, "strategy": "S/R Confluence",
        "horizon_key": horizon, "direction": direction, "status": status,
        "entry": entry, "stop_loss": stop, "exit_price": exit_price,
        "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": closed_at,
        "realized_pnl_amount": pnl, "shares": 10,
        "target_sources": [], "stop_sources": [],
    }


def _entry(trade_id, *, r=2.0, tags=("clean-exit",), lesson="Held to target."):
    """One journal.json record. Note the key is `trade_id`, while the trade
    side calls it `id` -- that asymmetry IS the join."""
    return {
        "trade_id": trade_id, "ticker": "AAPL", "outcome": "win",
        "r_realized": r, "mfe_r": 2.4, "mae_r": -0.3,
        "exit_efficiency": 83.0, "tags": list(tags), "auto_lesson": lesson,
        "note": "", "closed_at": "2026-08-03T20:00:00+00:00",
    }


def test_day_of_slices_the_utc_calendar_day():
    assert day_of("2026-08-03T20:00:00+00:00") == "2026-08-03"
    assert day_of("2026-08-03") == "2026-08-03"
    assert day_of(None) is None
    assert day_of("") is None


def test_join_merges_journal_fields_onto_the_trade():
    rows = joined_rows([_trade("a" * 16)], [_entry("a" * 16)])
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_id"] == "a" * 16
    assert row["day"] == "2026-08-03"
    assert row["pnl_amount"] == 50.0
    # The journal's own r_realized wins over a re-derivation.
    assert row["r_multiple"] == 2.0
    assert row["tags"] == ["clean-exit"]
    assert row["auto_lesson"] == "Held to target."
    assert row["mfe_r"] == 2.4


def test_a_trade_with_no_journal_entry_still_joins():
    """The dollar figure and the grid cell must survive an unjournaled
    trade -- only the lesson/tag fields go absent."""
    rows = joined_rows([_trade("b" * 16)], [])
    assert len(rows) == 1
    row = rows[0]
    assert row["pnl_amount"] == 50.0
    # r falls back to metrics.r_multiple: (110-100)/(100-95) = +2.0
    assert row["r_multiple"] == pytest.approx(2.0)
    assert row["tags"] == []
    assert row["auto_lesson"] is None
    assert row["mfe_r"] is None


def test_open_trades_and_trades_without_a_close_date_are_excluded():
    rows = joined_rows(
        [
            _trade("c" * 16, status="open", closed_at=None),
            _trade("d" * 16, status="win", closed_at=None),
            _trade("e" * 16, status="loss"),
        ],
        [],
    )
    assert [r["trade_id"] for r in rows] == ["e" * 16]


def test_strategy_label_comes_from_primary_strategy_label():
    """Never t["strategy"] -- Global Constraint 3. With no target_sources to
    rank, the label falls back to something, but it must not be the raw
    literal for a trade that HAS sources."""
    trade = _trade("f" * 16)
    trade["target_sources"] = ["EMA20"]
    rows = joined_rows([trade], [])
    assert rows[0]["strategy"] == "EMA20"


def test_filter_rows_narrows_by_strategy_and_horizon():
    a = _trade("a" * 16, horizon="4w"); a["target_sources"] = ["EMA20"]
    b = _trade("b" * 16, horizon="3m"); b["target_sources"] = ["VWAP"]
    rows = joined_rows([a, b], [])

    assert [r["trade_id"] for r in filter_rows(rows, strategy="EMA20")] == ["a" * 16]
    assert [r["trade_id"] for r in filter_rows(rows, horizon="3m")] == ["b" * 16]
    assert filter_rows(rows, strategy="EMA20", horizon="3m") == []
    assert len(filter_rows(rows)) == 2


def test_available_filters_lists_what_the_full_set_contains_sorted():
    a = _trade("a" * 16, horizon="3m"); a["target_sources"] = ["VWAP"]
    b = _trade("b" * 16, horizon="4w"); b["target_sources"] = ["EMA20"]
    options = available_filters(joined_rows([a, b], []))
    assert options == {"strategies": ["EMA20", "VWAP"], "horizons": ["3m", "4w"]}


def test_a_row_carries_exactly_the_declared_keys():
    """ROW_KEYS is what the route's contract test pins, and `assert_shape`
    fails on an undeclared key as loudly as on a missing one. Catching the
    drift here names the cause; catching it there only names a route."""
    from swingbot.core.analytics.pnl_calendar import ROW_KEYS

    rows = joined_rows([_trade("a" * 16)], [_entry("a" * 16)])
    assert set(rows[0]) == set(ROW_KEYS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL — `ModuleNotFoundError: No module named
'swingbot.core.analytics.pnl_calendar'`

- [ ] **Step 3: Write minimal implementation**

Create `swingbot/core/analytics/pnl_calendar.py`:

```python
"""Day-level P&L aggregation behind the /calendar admin workspace.

Spec: `docs/superpowers/specs/2026-08-22-v53-pnl-calendar-design.md`.

**Why this module exists next to `metrics.calendar_returns`.** That function
compounds *percentage* return per calendar MONTH. This one sums *dollars* and
*R* per calendar DAY, and joins the journal in so a day can be drilled into.
They are different granularities over different units and must not be folded
together -- `/analytics/performance` already ships the monthly `calendar`
key, and two functions quietly answering "the calendar figures" in different
units is how the two come to disagree on the same page.

**Pure, and deliberately so.** Every function below takes lists of dicts.
`load_rows()` is the single I/O boundary, and even it accepts injected
stores. Nothing here imports from `swingbot.admin` -- `closed_r()` lives
there and is off limits; `metrics.r_multiple` is the core-layer equivalent
and is the repo's one shared R computation.
"""
from __future__ import annotations

from swingbot.core.analytics import metrics
from swingbot.core.tracking.performance import primary_strategy_label

# The three statuses that mean "this position is over". Matches the filter
# `api_v1/analytics.py` applies before every historical figure it serves.
CLOSED_STATUSES = frozenset({"win", "loss", "closed"})

# The keys a joined row carries. Declared as a constant because the route's
# contract test asserts an exact key set, and a field added here without a
# matching contract update is exactly the undocumented change that test
# exists to catch.
ROW_KEYS = (
    "trade_id", "ticker", "strategy", "horizon", "direction", "day",
    "closed_at", "outcome", "pnl_amount", "r_multiple", "mfe_r", "mae_r",
    "exit_efficiency", "tags", "auto_lesson",
)


def day_of(closed_at: str | None) -> str | None:
    """The calendar day of an ISO close timestamp, as `YYYY-MM-DD`.

    A STRING SLICE, not a timezone conversion -- see the plan's Global
    Constraint 4. `closed_at` is always written as UTC ISO, and
    `metrics.calendar_returns` / `cumulative_pnl_by_strategy` already bucket
    by slicing. Converting to Europe/Berlin here would put a late close on a
    different day than the monthly figures rendered beside it.
    """
    if not closed_at:
        return None
    return closed_at[:10] or None


def _float_or_none(value) -> float | None:
    """`float(value)`, or None for anything non-numeric.

    A record written before a field existed carries None, and a hand-edited
    trades.json can carry a string. Neither should raise in an aggregation
    whose whole job is to survive the archive.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def joined_rows(trades: list[dict], entries: list[dict]) -> list[dict]:
    """One row per closed trade, with its journal entry merged in.

    The join key is asymmetric by construction: the trade side calls it
    `id`, the journal side `trade_id` (set from `trade.get("id")` at
    `journal.py:211`). A trade with no journal entry still produces a row --
    its dollar figure is what colours the grid cell, and dropping it would
    make the calendar disagree with the Dashboard's realized total.
    """
    by_trade_id = {
        e["trade_id"]: e for e in entries if e.get("trade_id")
    }

    rows: list[dict] = []
    for t in trades:
        if t.get("status") not in CLOSED_STATUSES:
            continue
        day = day_of(t.get("closed_at"))
        if day is None:
            continue

        entry = by_trade_id.get(t.get("id")) or {}
        # The journal's r_realized is authoritative when present: it was
        # computed by the same metrics.r_multiple at close time, and reusing
        # it avoids a second answer for one trade.
        r = _float_or_none(entry.get("r_realized"))
        if r is None:
            r = metrics.r_multiple(t)

        rows.append({
            "trade_id": t.get("id"),
            "ticker": t.get("ticker"),
            "strategy": primary_strategy_label(t),
            "horizon": t.get("horizon_key"),
            "direction": t.get("direction"),
            "day": day,
            "closed_at": t.get("closed_at"),
            "outcome": entry.get("outcome") or t.get("status"),
            "pnl_amount": _float_or_none(t.get("realized_pnl_amount")),
            "r_multiple": r,
            "mfe_r": _float_or_none(entry.get("mfe_r")),
            "mae_r": _float_or_none(entry.get("mae_r")),
            "exit_efficiency": _float_or_none(entry.get("exit_efficiency")),
            "tags": list(entry.get("tags") or []),
            "auto_lesson": entry.get("auto_lesson") or None,
        })
    return rows


def filter_rows(rows: list[dict], *, strategy: str | None = None,
                horizon: str | None = None) -> list[dict]:
    """AND-combined strategy/horizon narrowing. `None` means "do not apply"."""
    out = rows
    if strategy:
        out = [r for r in out if r["strategy"] == strategy]
    if horizon:
        out = [r for r in out if r["horizon"] == horizon]
    return out


def available_filters(rows: list[dict]) -> dict:
    """The filter vocabulary, derived from the UNFILTERED row set.

    Callers must pass every row, not the narrowed set -- a dropdown that
    shrinks to only the option already selected cannot be un-selected.
    """
    return {
        "strategies": sorted({r["strategy"] for r in rows if r["strategy"]}),
        "horizons": sorted({r["horizon"] for r in rows if r["horizon"]}),
    }


def load_rows(*, trade_log=None, journal=None) -> list[dict]:
    """The module's one I/O boundary: read both stores and join them.

    Stores are constructed here rather than at import time (Global
    Constraint 1) and are injectable so tests can point them at a tmp_path
    without monkeypatching `config.DATA_DIR`.
    """
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.tracking.performance import TradeLog

    tl = trade_log if trade_log is not None else TradeLog()
    js = journal if journal is not None else JournalStore()

    trades = tl.get_trades(status=None, limit=None) or []
    try:
        entries = js.entries()
    except Exception:
        # Same posture as `api_v1/analytics.py:198-204`: an unreadable
        # journal degrades to "no lessons" rather than failing a page whose
        # dollar figures came from trades.json and are fine.
        entries = []
    return joined_rows(trades, entries)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git commit -m "feat(v53): join closed trades with journal entries by day"
```

---

### Task 2: Day summaries and the month grid

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (append)
- Test: `tests/analytics/test_pnl_calendar.py` (append)

**Interfaces:**
- Consumes: `joined_rows`, `day_of` from Task 1.
- Produces: `bucket_by_day(rows) -> dict[str, list[dict]]`;
  `day_summary(day: str, rows: list[dict]) -> dict` with exactly the keys
  `date`, `net_pnl_amount`, `net_r`, `trade_count`, `win_rate`;
  `month_grid(rows, month: str) -> dict` with exactly `month`, `days`,
  `totals`.

- [ ] **Step 1: Write the failing test**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
from swingbot.core.analytics.pnl_calendar import (bucket_by_day, day_summary,
                                                  month_grid)


def _day_rows():
    """Three closes: two on 2026-08-03 (+50, -20), one on 2026-08-05 (+80).

    Hand-computed: 08-03 net +30.0 with 1 win of 2 -> 50.0% WR; 08-05 net
    +80.0, 100.0% WR. Month total +110.0 over 3 trades, 2 wins -> 66.67%.
    """
    return joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0,
                   status="win", exit_price=110.0),
            _trade("b" * 16, closed_at="2026-08-03T20:30:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=80.0,
                   status="win", exit_price=115.0),
        ],
        [],
    )


def test_bucket_by_day_groups_on_the_sliced_day():
    buckets = bucket_by_day(_day_rows())
    assert sorted(buckets) == ["2026-08-03", "2026-08-05"]
    assert len(buckets["2026-08-03"]) == 2


def test_day_summary_sums_dollars_and_r_and_computes_win_rate():
    buckets = bucket_by_day(_day_rows())
    summary = day_summary("2026-08-03", buckets["2026-08-03"])
    assert summary["date"] == "2026-08-03"
    assert summary["net_pnl_amount"] == pytest.approx(30.0)
    # r: (110-100)/5 = +2.0 and (96-100)/5 = -0.8  ->  +1.2
    assert summary["net_r"] == pytest.approx(1.2)
    assert summary["trade_count"] == 2
    assert summary["win_rate"] == pytest.approx(50.0)


def test_day_summary_returns_none_not_zero_when_nothing_is_computable():
    """Global Constraint 5. A day whose only trade has no dollar figure is
    not a flat $0 day."""
    trade = _trade("a" * 16, pnl=None, exit_price=None, status="closed")
    rows = joined_rows([trade], [])
    summary = day_summary("2026-08-03", rows)
    assert summary["net_pnl_amount"] is None
    assert summary["net_r"] is None
    # status "closed" is neither a win nor a loss, so there is no win rate.
    assert summary["win_rate"] is None
    assert summary["trade_count"] == 1


def test_month_grid_omits_days_with_no_closes():
    """Global Constraint 6 -- a day you did not trade is not a flat day."""
    grid = month_grid(_day_rows(), "2026-08")
    assert grid["month"] == "2026-08"
    assert [d["date"] for d in grid["days"]] == ["2026-08-03", "2026-08-05"]
    assert grid["totals"]["net_pnl_amount"] == pytest.approx(110.0)
    assert grid["totals"]["trade_count"] == 3
    assert grid["totals"]["win_rate"] == pytest.approx(66.67, abs=0.01)


def test_month_grid_scopes_to_the_requested_month_only():
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-07-31T20:00:00+00:00"),
            _trade("b" * 16, closed_at="2026-08-01T20:00:00+00:00"),
            _trade("c" * 16, closed_at="2026-09-01T20:00:00+00:00"),
        ],
        [],
    )
    assert [d["date"] for d in month_grid(rows, "2026-08")["days"]] == ["2026-08-01"]


def test_month_grid_on_a_month_with_no_trades_is_empty_not_an_error():
    grid = month_grid(_day_rows(), "2026-01")
    assert grid["days"] == []
    assert grid["totals"]["trade_count"] == 0
    assert grid["totals"]["net_pnl_amount"] is None
    assert grid["totals"]["win_rate"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL — `ImportError: cannot import name 'bucket_by_day'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/analytics/pnl_calendar.py`:

```python
def _sum_or_none(values: list[float | None]) -> float | None:
    """Sum the computable values, or None if none are.

    `sum([])` is `0`, which is exactly the conflation Global Constraint 5
    forbids -- a day with no computable dollar figure must not render as a
    flat $0 day.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present), 2)


def bucket_by_day(rows: list[dict]) -> dict[str, list[dict]]:
    """`{"YYYY-MM-DD": [row, ...]}`. Days with no rows simply have no key."""
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row["day"], []).append(row)
    return buckets


def day_summary(day: str, rows: list[dict]) -> dict:
    """One grid cell: net dollars, net R, count, win rate.

    `win_rate` delegates to `metrics.win_rate` rather than counting inline,
    so a "closed" exit with no win/loss verdict is excluded from both
    numerator and denominator here exactly as it is everywhere else.
    """
    return {
        "date": day,
        "net_pnl_amount": _sum_or_none([r["pnl_amount"] for r in rows]),
        "net_r": _sum_or_none([r["r_multiple"] for r in rows]),
        "trade_count": len(rows),
        "win_rate": metrics.win_rate(
            [{"status": r["outcome"]} for r in rows]
        ),
    }


def month_grid(rows: list[dict], month: str) -> dict:
    """Every day of `month` (`YYYY-MM`) that had a close, plus the totals.

    Days are ascending. The totals are computed over the month's rows as one
    pool rather than by averaging the per-day summaries -- a 1-trade day and
    a 9-trade day must not carry equal weight in the month's win rate.
    """
    scoped = [r for r in rows if r["day"][:7] == month]
    buckets = bucket_by_day(scoped)
    days = [day_summary(day, buckets[day]) for day in sorted(buckets)]
    totals = day_summary(month, scoped)
    # `date` on a month total would invite reading it as a day.
    totals.pop("date", None)
    return {"month": month, "days": days, "totals": totals}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: PASS — 14 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git commit -m "feat(v53): summarise P&L per day and per month"
```

---

### Task 3: Day-of-week breakdown, best/worst day, and the day streak

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (append)
- Test: `tests/analytics/test_pnl_calendar.py` (append)

**Interfaces:**
- Consumes: `bucket_by_day`, `day_summary` from Task 2.
- Produces: `WEEKDAYS: tuple[str, ...]`;
  `day_of_week_breakdown(rows) -> list[dict]` — always 5 entries with keys
  `weekday`, `avg_pnl_amount`, `avg_r`, `win_rate`, `trade_count`;
  `best_worst_days(rows) -> dict` → `{"best": dict | None, "worst": dict | None}`;
  `day_streak(rows) -> dict` → `{"direction": str | None, "days": int}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
from swingbot.core.analytics.pnl_calendar import (best_worst_days, day_streak,
                                                  day_of_week_breakdown)


def test_day_of_week_breakdown_always_returns_the_five_trading_days():
    """A weekend never has closes, so Sat/Sun are not modelled at all --
    but Mon-Fri appear even with no data, so the table does not reflow as
    a filter narrows."""
    rows = joined_rows([_trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00")], [])
    breakdown = day_of_week_breakdown(rows)
    assert [b["weekday"] for b in breakdown] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    # 2026-08-03 is a Monday.
    assert breakdown[0]["trade_count"] == 1
    assert breakdown[0]["avg_pnl_amount"] == pytest.approx(50.0)
    assert breakdown[1]["trade_count"] == 0
    assert breakdown[1]["avg_pnl_amount"] is None
    assert breakdown[1]["win_rate"] is None


def test_day_of_week_breakdown_averages_per_trade_not_per_day():
    """Two Monday closes of +50 and -20 average +15.0 per trade."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0),
            _trade("b" * 16, closed_at="2026-08-10T20:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
        ],
        [],
    )
    monday = day_of_week_breakdown(rows)[0]
    assert monday["trade_count"] == 2
    assert monday["avg_pnl_amount"] == pytest.approx(15.0)
    assert monday["win_rate"] == pytest.approx(50.0)


def test_best_and_worst_days_are_whole_days_not_single_trades():
    """08-03 nets +30 (two trades), 08-05 nets -90 (one). The worst DAY is
    08-05 even though 08-03 contains the single worst trade."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0),
            _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=-90.0,
                   status="loss", exit_price=91.0),
        ],
        [],
    )
    extremes = best_worst_days(rows)
    assert extremes["best"]["date"] == "2026-08-03"
    assert extremes["best"]["net_pnl_amount"] == pytest.approx(30.0)
    assert extremes["worst"]["date"] == "2026-08-05"
    assert extremes["worst"]["net_pnl_amount"] == pytest.approx(-90.0)


def test_best_worst_days_are_none_on_an_empty_set():
    assert best_worst_days([]) == {"best": None, "worst": None}


def test_day_streak_counts_consecutive_same_sign_days_backwards():
    """08-03 -40, 08-04 +10, 08-05 +30 -> a 2-day winning streak."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=-40.0,
                   status="loss", exit_price=96.0),
            _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=10.0),
            _trade("c" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=30.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "winning", "days": 2}


def test_day_streak_is_not_broken_by_a_gap_with_no_trades():
    """A weekend, a holiday, or a quiet Wednesday is an ABSENCE of evidence,
    not a losing day. Only days that actually had closes are counted."""
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=10.0),
            # 08-04 .. 08-13 have no closes at all.
            _trade("b" * 16, closed_at="2026-08-14T20:00:00+00:00", pnl=20.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "winning", "days": 2}


def test_day_streak_reports_flat_for_a_zero_day_and_stops_there():
    rows = joined_rows(
        [
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=10.0),
            _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=0.0,
                   status="closed", exit_price=100.0),
        ],
        [],
    )
    assert day_streak(rows) == {"direction": "flat", "days": 1}


def test_day_streak_on_an_empty_set():
    assert day_streak([]) == {"direction": None, "days": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL — `ImportError: cannot import name 'best_worst_days'`

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/core/analytics/pnl_calendar.py`:

First add `import datetime as _dt` to the module's **top import block**
(above `from swingbot.core.analytics import metrics`), not here — a mid-file
import after executable code is an E402 and reads as an afterthought. Then
append the rest:

```python
# Monday-first, and only the five days a US-market swing bot can close on.
# Saturday and Sunday are not modelled: a weekend cell is rendered inert by
# the frontend rather than reported as a zero here.
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def _avg_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 2)


def day_of_week_breakdown(rows: list[dict]) -> list[dict]:
    """Per-weekday averages across every row given, Mon..Fri.

    Averaged PER TRADE, not per day: "what does a Monday trade typically
    do" is the question, and averaging day-averages would let a Monday with
    one trade outweigh a Monday with eight.

    All five weekdays are always present, even at n=0, so the table keeps
    its shape as a strategy/horizon filter narrows the set.
    """
    by_weekday: dict[str, list[dict]] = {name: [] for name in WEEKDAYS}
    for row in rows:
        try:
            index = _dt.date.fromisoformat(row["day"]).weekday()
        except ValueError:
            continue
        if index < len(WEEKDAYS):     # 5 and 6 are Sat/Sun -- see WEEKDAYS.
            by_weekday[WEEKDAYS[index]].append(row)

    return [
        {
            "weekday": name,
            "avg_pnl_amount": _avg_or_none([r["pnl_amount"] for r in group]),
            "avg_r": _avg_or_none([r["r_multiple"] for r in group]),
            "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in group]),
            "trade_count": len(group),
        }
        for name, group in ((n, by_weekday[n]) for n in WEEKDAYS)
    ]


def best_worst_days(rows: list[dict]) -> dict:
    """The single best and worst DAY by net dollars, each a full summary.

    A day, not a trade: the worst day in the book is often several ordinary
    losses rather than one spectacular one, and that is the fact worth
    surfacing. Days with no computable dollar total are excluded from the
    ranking rather than sorted as zero.
    """
    buckets = bucket_by_day(rows)
    summaries = [day_summary(day, buckets[day]) for day in sorted(buckets)]
    ranked = [s for s in summaries if s["net_pnl_amount"] is not None]
    if not ranked:
        return {"best": None, "worst": None}
    return {
        "best": max(ranked, key=lambda s: s["net_pnl_amount"]),
        "worst": min(ranked, key=lambda s: s["net_pnl_amount"]),
    }


def day_streak(rows: list[dict]) -> dict:
    """The current run of same-signed days, counted back from the latest.

    Only days that actually had closes participate. A gap -- a weekend, a
    holiday, a quiet Wednesday -- is an absence of evidence and does NOT
    break the run; treating it as a break would cap almost every streak at
    five and make the figure meaningless.

    A zero-dollar day is its own `"flat"` direction rather than being folded
    into either side, and ends whatever run was building.
    """
    buckets = bucket_by_day(rows)
    summaries = [day_summary(day, buckets[day]) for day in sorted(buckets, reverse=True)]
    ranked = [s for s in summaries if s["net_pnl_amount"] is not None]
    if not ranked:
        return {"direction": None, "days": 0}

    def _sign(summary: dict) -> str:
        amount = summary["net_pnl_amount"]
        if amount > 0:
            return "winning"
        if amount < 0:
            return "losing"
        return "flat"

    direction = _sign(ranked[0])
    if direction == "flat":
        return {"direction": "flat", "days": 1}

    days = 0
    for summary in ranked:
        if _sign(summary) != direction:
            break
        days += 1
    return {"direction": direction, "days": days}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: PASS — 22 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git commit -m "feat(v53): add weekday breakdown, day extremes and day streak"
```

---

# Phase 2 — API routes

### Task 4: `GET /api/v1/calendar/pnl`

**Files:**
- Create: `swingbot/admin/api_v1/calendar.py`
- Modify: `swingbot/admin/api_v1/__init__.py:181-183` (the register tuple)
- Test: `tests/admin/test_api_v1_calendar.py`

**Interfaces:**
- Consumes: every function from Tasks 1–3; `api_v1`, `ApiError` from
  `swingbot/admin/api_v1/__init__.py`; `require_auth` from `.auth`.
- Produces: `GET /api/v1/calendar/pnl?month=&strategy=&horizon=` returning
  exactly the keys `month`, `days`, `totals`, `day_of_week`, `best_day`,
  `worst_day`, `streak`, `filters`. Also `_month_param()`, used by Task 5.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_api_v1_calendar.py`:

```python
"""v53 — /api/v1/calendar/pnl and /api/v1/calendar/pnl/day.

Data is seeded by WRITING trades.json and journal.json into the tmp_path
`admin_app` points config.DATA_DIR at, rather than by monkeypatching the
stores -- the same posture as tests/admin/test_api_v1_analytics.py. Note
`admin_app` seeds trades.json/account.json/plans.json but NOT journal.json;
JournalStore reads a missing file as [], so the unjournaled case is the
default here and has to be asserted deliberately.
"""
import json

import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR,
                                         assert_error, assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}


def _trade(trade_id, *, closed_at="2026-08-03T20:00:00+00:00", status="win",
           pnl=50.0, exit_price=110.0, horizon="4w", sources=("EMA20",)):
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL",
        "strategy": "S/R Confluence", "horizon_key": horizon,
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0,
        "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED",
        "quality_score": 72, "source": "confluence", "legs": [],
        "opened_at": "2026-08-01T14:00:00+00:00", "status": status,
        "closed_at": closed_at, "exit_price": exit_price,
        "realized_pnl_amount": pnl, "shares": 10, "position_value": 1000.0,
        "target_sources": list(sources), "stop_sources": [],
        "target2_sources": [], "confirmed_by": [], "explanation": None,
        "confidence_breakdown": None,
    }


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=(), entries=()):
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
        (tmp_path / "journal.json").write_text(json.dumps(list(entries)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert_error(client.get("/api/v1/calendar/pnl?month=2026-08"), "auth", 401)


def test_works_on_an_empty_store(seed, logged_in):
    """A fresh install has no trades and no journal. The page must render."""
    seed()
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert body["days"] == []
    assert body["totals"]["trade_count"] == 0
    assert body["filters"] == {"strategies": [], "horizons": []}
    assert body["best_day"] is None
    assert body["streak"] == {"direction": None, "days": 0}


def test_response_shape(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert_shape(body, {
        "month": str, "days": list, "totals": dict, "day_of_week": list,
        "best_day": (dict, type(None)), "worst_day": (dict, type(None)),
        "streak": dict, "filters": dict,
    })
    assert_shape(body["days"][0], {
        "date": str, "net_pnl_amount": NULLABLE_NUMBER,
        "net_r": NULLABLE_NUMBER, "trade_count": int,
        "win_rate": NULLABLE_NUMBER,
    }, where="days[0]")
    assert_shape(body["totals"], {
        "net_pnl_amount": NULLABLE_NUMBER, "net_r": NULLABLE_NUMBER,
        "trade_count": int, "win_rate": NULLABLE_NUMBER,
    }, where="totals")
    assert_shape(body["day_of_week"][0], {
        "weekday": str, "avg_pnl_amount": NULLABLE_NUMBER,
        "avg_r": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
        "trade_count": int,
    }, where="day_of_week[0]")
    assert_shape(body["streak"], {"direction": NULLABLE_STR, "days": int},
                 where="streak")
    assert_shape(body["filters"], {"strategies": list, "horizons": list},
                 where="filters")
    assert len(body["day_of_week"]) == 5


def test_scopes_to_the_requested_month(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, closed_at="2026-07-20T20:00:00+00:00"),
        _trade("b" * 16, closed_at="2026-08-03T20:00:00+00:00"),
    ])
    body = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert [d["date"] for d in body["days"]] == ["2026-08-03"]


def test_a_malformed_month_is_a_400_not_a_silent_whole_history(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl?month=August"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/calendar/pnl?month=2026-13"), "invalid", 400)


def test_month_defaults_to_the_current_month_when_omitted(seed, logged_in):
    import datetime as dt
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl").get_json()
    assert body["month"] == dt.date.today().strftime("%Y-%m")


def test_filters_narrow_the_grid_but_not_the_filter_vocabulary(seed, logged_in):
    """A dropdown that shrinks to only the selected option cannot be
    un-selected -- `filters` must stay the full vocabulary."""
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",), horizon="4w"),
        _trade("b" * 16, closed_at="2026-08-04T20:00:00+00:00",
               sources=("VWAP",), horizon="3m"),
    ])
    body = logged_in.get(
        "/api/v1/calendar/pnl?month=2026-08&strategy=EMA20"
    ).get_json()
    assert [d["date"] for d in body["days"]] == ["2026-08-03"]
    assert body["filters"]["strategies"] == ["EMA20", "VWAP"]
    assert body["filters"]["horizons"] == ["3m", "4w"]


def test_an_unknown_query_parameter_is_rejected(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/calendar/pnl?tickr=AAPL"), "invalid", 400)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: FAIL — every request 404s (`assert_error` reports `not_found`
instead of the expected code) because no `/calendar/pnl` rule is registered.

- [ ] **Step 3: Write minimal implementation**

Create `swingbot/admin/api_v1/calendar.py`:

```python
"""GET /api/v1/calendar/* — the day-level P&L calendar surface.

Spec: `docs/superpowers/specs/2026-08-22-v53-pnl-calendar-design.md`.

**"UI renders, analytics computes."** Every figure here is computed by
`swingbot.core.analytics.pnl_calendar`; these routes select, scope and
forward. That is the same rule `analytics.py` states, and the reason this
module holds no arithmetic.

`TradeLog` / `JournalStore` are constructed inside the view, never at import
time -- see `tests/admin/conftest.py:34-47`. An api_v1 module that binds a
`config.DATA_DIR` path at import would read the real project's `data/`
directory throughout the test suite.
"""
from __future__ import annotations

import datetime as dt

from flask import jsonify, request

from . import ApiError, api_v1
from .auth import require_auth

# `month` is handled separately from the filters: it scopes the grid rather
# than narrowing the population, and it has its own format.
_FILTERS = frozenset({"month", "strategy", "horizon", "date"})


def _reject_unknown_params() -> None:
    """A query parameter nobody declared is a 400, never an ignored filter.

    Same reasoning as `parse_collection_params`: a silently dropped filter
    is how a filter that has stopped working survives to production -- the
    caller sees results, just not the ones it asked for.
    """
    unknown = sorted(set(request.args) - _FILTERS)
    if unknown:
        raise ApiError(
            "invalid",
            f"unknown parameter {unknown[0]!r}; allowed: {sorted(_FILTERS)}",
            400,
        )


def _month_param() -> str:
    """The `?month=YYYY-MM` scope, defaulting to the current month.

    A malformed value is a 400 rather than a silent fallback to all-time --
    the same trap `_iso_day` in `analytics.py` guards, where accepting
    `?from=last-tuesday` would hand a user all-time numbers to read as this
    month's.
    """
    raw = (request.args.get("month") or "").strip()
    if not raw:
        return dt.date.today().strftime("%Y-%m")
    try:
        dt.datetime.strptime(raw, "%Y-%m")
    except ValueError:
        raise ApiError("invalid", "month must be a YYYY-MM value", 400)
    return raw


def _filter_args() -> tuple[str | None, str | None]:
    strategy = (request.args.get("strategy") or "").strip() or None
    horizon = (request.args.get("horizon") or "").strip() or None
    return strategy, horizon


@api_v1.route("/calendar/pnl", methods=["GET"])
@require_auth
def calendar_pnl():
    """One month's day grid, plus the full-history context beside it.

    **Two different scopes in one payload, deliberately.** `days` and
    `totals` are the requested month; `day_of_week`, `best_day`,
    `worst_day` and `streak` are ALL of history under the same
    strategy/horizon filter. A weekday pattern drawn from one month is 4-5
    observations per weekday and would be noise presented as a finding.
    """
    from swingbot.core.analytics import pnl_calendar as pc

    _reject_unknown_params()
    month = _month_param()
    strategy, horizon = _filter_args()

    everything = pc.load_rows()
    rows = pc.filter_rows(everything, strategy=strategy, horizon=horizon)
    grid = pc.month_grid(rows, month)
    extremes = pc.best_worst_days(rows)

    return jsonify({
        "month": grid["month"],
        "days": grid["days"],
        "totals": grid["totals"],
        "day_of_week": pc.day_of_week_breakdown(rows),
        "best_day": extremes["best"],
        "worst_day": extremes["worst"],
        "streak": pc.day_streak(rows),
        # Derived from the UNFILTERED set -- see `available_filters`.
        "filters": pc.available_filters(everything),
    })
```

Then add the module to the register tuple in
`swingbot/admin/api_v1/__init__.py:181-183`:

```python
    from . import (analytics, calendar, dashboard, jobs, market,  # noqa: F401
                   risk, session, system, trade_commands, trades,
                   versions, watchlist)  # (register routes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/calendar.py swingbot/admin/api_v1/__init__.py \
        tests/admin/test_api_v1_calendar.py
git commit -m "feat(v53): serve the month P&L grid from /api/v1/calendar/pnl"
```

---

### Task 5: `GET /api/v1/calendar/pnl/day`

**Files:**
- Modify: `swingbot/admin/api_v1/calendar.py` (append)
- Test: `tests/admin/test_api_v1_calendar.py` (append)

**Interfaces:**
- Consumes: `_reject_unknown_params`, `_filter_args` from Task 4;
  `pc.load_rows`, `pc.filter_rows` from Task 1.
- Produces: `GET /api/v1/calendar/pnl/day?date=&strategy=&horizon=`
  returning exactly `{date, trades}`, where each trade carries exactly
  `pnl_calendar.ROW_KEYS`.

- [ ] **Step 1: Write the failing test**

Append to `tests/admin/test_api_v1_calendar.py`:

```python
def _entry(trade_id, *, r=2.0, tags=("clean-exit",)):
    return {
        "trade_id": trade_id, "ticker": "AAPL", "strategy": "S/R Confluence",
        "horizon_key": "4w", "direction": "bullish", "outcome": "win",
        "r_realized": r, "mfe_r": 2.4, "mae_r": -0.3,
        "exit_efficiency": 83.0, "holding_days": 2, "tags": list(tags),
        "auto_lesson": "Held to target.", "note": "",
        "opened_at": "2026-08-01T14:00:00+00:00",
        "closed_at": "2026-08-03T20:00:00+00:00",
    }


def test_day_requires_auth(client):
    assert_error(client.get("/api/v1/calendar/pnl/day?date=2026-08-03"),
                 "auth", 401)


def test_day_lists_every_trade_closed_that_day(seed, logged_in):
    seed(
        trades=[
            _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00"),
            _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
                   status="loss", exit_price=96.0),
            _trade("c" * 16, closed_at="2026-08-04T20:00:00+00:00"),
        ],
        entries=[_entry("a" * 16)],
    )
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert body["date"] == "2026-08-03"
    assert {t["trade_id"] for t in body["trades"]} == {"a" * 16, "b" * 16}


def test_day_trade_shape_carries_the_journal_join(seed, logged_in):
    seed(trades=[_trade("a" * 16)], entries=[_entry("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert_shape(body, {"date": str, "trades": list})
    assert_shape(body["trades"][0], {
        "trade_id": str, "ticker": str, "strategy": str,
        "horizon": NULLABLE_STR, "direction": NULLABLE_STR, "day": str,
        "closed_at": NULLABLE_STR, "outcome": NULLABLE_STR,
        "pnl_amount": NULLABLE_NUMBER, "r_multiple": NULLABLE_NUMBER,
        "mfe_r": NULLABLE_NUMBER, "mae_r": NULLABLE_NUMBER,
        "exit_efficiency": NULLABLE_NUMBER, "tags": list,
        "auto_lesson": NULLABLE_STR,
    }, where="trades[0]")
    assert body["trades"][0]["tags"] == ["clean-exit"]
    assert body["trades"][0]["auto_lesson"] == "Held to target."


def test_day_survives_a_trade_with_no_journal_entry(seed, logged_in):
    """journal.json is not seeded by admin_app, so this is the common case
    on a fresh install -- the dollar figure must still arrive."""
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    trade = body["trades"][0]
    assert trade["pnl_amount"] == 50.0
    assert trade["tags"] == []
    assert trade["auto_lesson"] is None


def test_day_respects_the_strategy_filter(seed, logged_in):
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", sources=("VWAP",)),
    ])
    body = logged_in.get(
        "/api/v1/calendar/pnl/day?date=2026-08-03&strategy=VWAP"
    ).get_json()
    assert [t["trade_id"] for t in body["trades"]] == ["b" * 16]


def test_a_day_with_no_closes_is_404_not_an_empty_200(seed, logged_in):
    """Every date the grid returns has >=1 trade, so this is only reachable
    from a stale link -- and "the day you asked for is not in the book" is a
    different answer from "that day was flat"."""
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-09"),
                 "not_found", 404)


def test_a_missing_or_malformed_date_is_a_400(seed, logged_in):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get("/api/v1/calendar/pnl/day"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08"),
                 "invalid", 400)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: FAIL — the new tests 404 with code `not_found` where they expect
`auth` / `invalid` / a body, since `/calendar/pnl/day` has no rule.

- [ ] **Step 3: Write minimal implementation**

Append to `swingbot/admin/api_v1/calendar.py`:

```python
def _date_param() -> str:
    """The required `?date=YYYY-MM-DD`. Absent or malformed is a 400."""
    raw = (request.args.get("date") or "").strip()
    if not raw:
        raise ApiError("invalid", "date is required (YYYY-MM-DD)", 400)
    try:
        dt.datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ApiError("invalid", "date must be a YYYY-MM-DD value", 400)
    return raw


@api_v1.route("/calendar/pnl/day", methods=["GET"])
@require_auth
def calendar_pnl_day():
    """Every trade closed on one day — the grid's drill-down drawer.

    404 rather than an empty 200 when the day holds nothing: every date the
    grid emits has at least one close (days with none are omitted), so an
    empty result means the client asked for a day that is not in the book,
    which is a different answer from "that day was flat".

    Ordered by close time so the drawer reads as the day happened.
    """
    from swingbot.core.analytics import pnl_calendar as pc

    _reject_unknown_params()
    date = _date_param()
    strategy, horizon = _filter_args()

    rows = pc.filter_rows(pc.load_rows(), strategy=strategy, horizon=horizon)
    day_rows = sorted(
        (r for r in rows if r["day"] == date),
        key=lambda r: r["closed_at"] or "",
    )
    if not day_rows:
        raise ApiError("not_found", f"no closed trades on {date}", 404)

    return jsonify({"date": date, "trades": day_rows})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/calendar.py tests/admin/test_api_v1_calendar.py
git commit -m "feat(v53): serve one day's closed trades for the calendar drawer"
```

---
