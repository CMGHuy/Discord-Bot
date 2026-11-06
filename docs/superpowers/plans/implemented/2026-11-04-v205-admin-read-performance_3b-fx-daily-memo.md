# Admin read performance, Layer 1 -- Part 3b: the `fx_daily_rates` memo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-a" (Read), "Error handling", "Testing".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

This part holds one task, V205-12b, split from V205-12 (part 3) for the 20 KB task cap; part 3 sits too close to its 1500-line cap to hold it. V205-12b runs directly after V205-12, which creates the module it extends. Nothing reads the memo until V205-15, so no output moves.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

# Phase 4 -- One FX rate per pair per day (L1-a): the table's reader, continued

### Task V205-12b: The version-keyed `fx_daily_rates` memo: `lookup`, `reset_memo`

**Model:** opus — a thread-shared process memo whose failure mode must degrade to `fx_missing` (never 1.0, never a 500), with a version check that must not turn a missing key into a query per amount.

**Files:**
- Modify: `swingbot/core/marketdata/fx_daily.py` (append the memo; two imports)
- Create: `tests/marketdata/test_fx_daily_lookup.py`

**Interfaces:**
- Consumes (V205-11): `fx_daily_rate_repo()` with `version() -> tuple[int, datetime | None]` and `all_rates() -> list[dict]` (`{base, account, day, rate, bar_date}`, ordered by `(base, account, day)`). (V205-12): `fx_daily.FALLBACK_DAYS`, `fx_daily._clock`, `fx_daily.log`. Existing: `swallowed(log, tag, exc, ..., level=...)`.
- Produces (ledger, index "fx_daily"): `VERSION_CHECK_S = 60`; `lookup(base: str, account: str, day: date) -> float | None` (majors in, no scale); `reset_memo() -> None`. V205-15 calls `lookup` from `fx.fx_rate`; V205-15's and V205-16's tests call `reset_memo`.
- The module still imports nothing from `fx`, `swingbot.admin` or `flask`: V205-12's import test keeps guarding it.

**The memo.** `lookup` reads the whole table once into `{(base, account): (days, entries)}`, sorted by day. It checks the table's version (`count(*), max(snapped_at)`) at most once per `VERSION_CHECK_S` and reloads the rows only when the version changed. So a missing key (before 08:00, refresher down, a pair with no frame) never reloads per request. An exact row wins. Otherwise the nearest earlier row answers if its `bar_date` is within `FALLBACK_DAYS` of D; else the answer is `None`. A read error answers `None` for that call (`marketdata.fx_daily.lookup`, which matches `^(scan|marketdata|earnings|runstate|ops)\.`). It keeps the memo and stamps the check time, so a missing table in the deploy window costs one failed query per 60 s, not one per amount. The memo is one immutable `_Memo` swapped in a single assignment, so 16 gunicorn threads never see a half-built index. Two threads reloading at once build equal objects, which is harmless.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_fx_daily_lookup.py`:

```python
"""v205 L1-a: fx_daily.lookup over the fx_daily_rates memo (version-keyed, 60 s check).

Every expected rate is a literal from the fake table, never a recomputation."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx_daily


class FakeRates:
    def __init__(self, rows):
        self.rows = list(rows)
        self.at = datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc)
        self.version_calls = 0
        self.load_calls = 0
        self.fail = False

    def version(self, *, conn=None):
        self.version_calls += 1
        if self.fail:
            raise RuntimeError('relation "fx_daily_rates" does not exist')
        return len(self.rows), self.at

    def all_rates(self, *, conn=None):
        self.load_calls += 1
        return sorted(self.rows, key=lambda r: (r["base"], r["account"], r["day"]))


def _rate(day, rate, bar, base="USD", account="EUR"):
    return {"base": base, "account": account, "day": day, "rate": rate, "bar_date": bar}


class Clock:
    def __init__(self):
        self.now = 5000.0

    def __call__(self):
        return self.now


@pytest.fixture
def table(monkeypatch):
    repo = FakeRates([
        _rate(date(2026, 11, 2), 0.86, date(2026, 10, 30)),     # Monday: Friday's close
        _rate(date(2026, 11, 3), 0.87, date(2026, 11, 2)),
        _rate(date(2026, 11, 3), 1.15, date(2026, 11, 2), base="GBP"),
    ])
    fx_daily.reset_memo()
    monkeypatch.setattr(fx_daily, "fx_daily_rate_repo", lambda: repo)
    yield repo
    fx_daily.reset_memo()


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(fx_daily, "_clock", c)
    return c


def test_an_exact_row_wins(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 2)) == 0.86
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87
    assert fx_daily.lookup("GBP", "EUR", date(2026, 11, 3)) == 1.15


def test_a_missing_day_falls_back_to_the_nearest_earlier_row_within_seven_days(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87      # bar 11-02, 2 days
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 9)) == 0.87      # bar 11-02, 7 days
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 10)) is None     # 8 days: fx_missing


def test_before_the_first_row_or_an_unknown_pair_is_none(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 1)) is None
    assert fx_daily.lookup("ZAR", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "GBP", date(2026, 11, 3)) is None


def test_an_empty_table_is_none_and_loads_once(table, clock):
    table.rows.clear()
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) is None
    assert (table.version_calls, table.load_calls) == (1, 1)


def test_the_version_is_checked_at_most_once_per_minute(table, clock):
    for _ in range(50):
        fx_daily.lookup("USD", "EUR", date(2026, 11, 5))                  # a missing key, every call
    assert (table.version_calls, table.load_calls) == (1, 1)
    clock.now += fx_daily.VERSION_CHECK_S - 1
    fx_daily.lookup("USD", "EUR", date(2026, 11, 5))
    assert (table.version_calls, table.load_calls) == (1, 1)
    clock.now += 2
    fx_daily.lookup("USD", "EUR", date(2026, 11, 5))
    assert (table.version_calls, table.load_calls) == (2, 1)              # same version: no reload


def test_a_new_row_shows_after_the_next_version_check(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87
    table.rows.append(_rate(date(2026, 11, 4), 0.88, date(2026, 11, 3)))
    table.at = datetime(2026, 11, 4, 7, 0, 5, tzinfo=timezone.utc)
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87      # inside the minute
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.88
    assert table.load_calls == 2


def test_an_unreadable_table_is_none_swallowed_and_checked_again_a_minute_later(table, clock):
    before = sw.snapshot().get("marketdata.fx_daily.lookup", {}).get("count", 0)
    table.fail = True
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert table.version_calls == 1                                       # not one query per amount
    assert sw.snapshot()["marketdata.fx_daily.lookup"]["count"] == before + 1
    table.fail = False
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87


def test_a_read_error_keeps_the_loaded_memo(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87
    table.fail = True
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None      # the failing call
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87      # the kept memo
    assert table.version_calls == 2


def test_reset_memo_forces_a_reload(table, clock):
    fx_daily.lookup("USD", "EUR", date(2026, 11, 3))
    fx_daily.reset_memo()
    fx_daily.lookup("USD", "EUR", date(2026, 11, 3))
    assert table.load_calls == 2


def test_the_answer_is_never_one_for_a_missing_rate(table, clock):
    answers = [fx_daily.lookup(base, "EUR", date(2026, 11, d))
               for base in ("USD", "GBP", "ZAR") for d in range(1, 15)]
    assert 1.0 not in answers and None in answers
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_daily_lookup.py`
Expected: FAIL; `fx_daily.reset_memo` raises `AttributeError: module 'swingbot.core.marketdata.fx_daily' has no attribute 'reset_memo'` in the `table` fixture.

- [ ] **Step 3: Append the memo to `fx_daily.py`**

In `<wt>/swingbot/core/marketdata/fx_daily.py`, extend the imports to:

```python
import bisect
import logging
import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
from swingbot.core.infra.swallowed import swallowed
```

After `FALLBACK_DAYS = 7` add:

```python
#: How often a process asks whether the table changed.
VERSION_CHECK_S = 60
```

At the end of the module append:

```python
@dataclass(frozen=True)
class _Memo:
    version: tuple | None
    checked_at: float
    pairs: dict = field(default_factory=dict)   # (base, account) -> ([day], [(day, rate, bar_date)])


_memo: _Memo | None = None


def reset_memo() -> None:
    """Forget the loaded table (tests; nothing in production calls it)."""
    global _memo
    _memo = None


def _index(rows: list[dict]) -> dict:
    """Rows ordered by (base, account, day) -> per pair, parallel sorted lists for bisect."""
    pairs: dict = {}
    for row in rows:
        days, entries = pairs.setdefault((row["base"], row["account"]), ([], []))
        days.append(row["day"])
        entries.append((row["day"], float(row["rate"]), row["bar_date"]))
    return pairs


def _current(now: float) -> _Memo:
    """The memo, its version re-checked once VERSION_CHECK_S has passed."""
    global _memo
    memo = _memo
    if memo is not None and now - memo.checked_at < VERSION_CHECK_S:
        return memo
    repo = fx_daily_rate_repo()
    version = tuple(repo.version())
    if memo is not None and memo.version == version:
        memo = _Memo(version, now, memo.pairs)
    else:
        memo = _Memo(version, now, _index(repo.all_rates()))
    _memo = memo
    return memo


def _pick(series, day: date) -> float | None:
    """The exact row's rate, else the nearest earlier row's if its bar is within FALLBACK_DAYS."""
    if not series:
        return None
    days, entries = series
    position = bisect.bisect_right(days, day)
    if position == 0:
        return None
    row_day, rate, bar_date = entries[position - 1]
    if row_day == day or (day - bar_date).days <= FALLBACK_DAYS:
        return rate
    return None


def lookup(base: str, account: str, day: date) -> float | None:
    """The stored rate for (major base, major account, Berlin day), or None.

    A read error is None for this call, keeps the memo, and waits
    VERSION_CHECK_S before asking again (the deploy window before
    `alembic upgrade head` creates the table)."""
    global _memo
    now = _clock()
    try:
        memo = _current(now)
    except Exception as exc:
        swallowed(log, "marketdata.fx_daily.lookup", exc, level=logging.DEBUG)
        kept = _memo
        _memo = _Memo(kept.version if kept else None, now, kept.pairs if kept else {})
        return None
    return _pick(memo.pairs.get((base, account)), day)
```

`_index` relies on `all_rates()` being ordered by `(base, account, day)` (V205-11 contract), so each pair's `days` list is sorted for `bisect`. Also change the module docstring's "`lookup` (V205-12b) serves" to "`lookup` serves"; the docstring is otherwise unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_daily_lookup.py`
Expected: `10 passed`, `0 failed`.

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_daily.py` -- expected `18 passed` (the import guard still holds with the two new imports).

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` -- expected `0 failed` (`marketdata.fx_daily.lookup` is new and unique).

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx_daily.py` -- every function `A` or `B` (under 10); `python <wt>/scripts/dev/complexity_gate.py` clean.

Run: `python <wt>/scripts/dev/testrun.py suite market-data` -- expected `0 failed`, `0 xfailed` (nothing calls `lookup` yet; this proves the new import of `market_refresh` has no side effect).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/fx_daily.py tests/marketdata/test_fx_daily_lookup.py
git -C <wt> commit -m "feat(marketdata): version-keyed fx_daily_rates memo, lookup degrades to a miss (v205 V205-12b)"
```
