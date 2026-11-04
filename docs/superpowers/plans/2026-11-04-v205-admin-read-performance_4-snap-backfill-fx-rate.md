# Admin read performance, Layer 1 -- Part 4: the 08:00 snap, the backfill, `fx_rate` on the table

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-a" (Snap, Backfill, Read, Figures this moves), "Error handling", "Testing", "Rollout and rollback".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

This part holds V205-13 (the refresher writes the day's row from 08:00 Berlin), V205-14 (the one-off backfill of past days, its ops script and the deploy runbook step) and V205-15 (`fx.fx_rate` reads the table; the strictly-before rule replaces `_close_on_or_before`). V205-13 and V205-14 add rows nobody reads yet, so no output moves. V205-15 is the first task whose output moves on purpose: it updates `money_reference.EXPECTED_MONEY` by hand and never a golden.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

**Suite headroom (read before adding tests).** `market-data` (`tests/marketdata/`, `tests/market/`) counted 1146 of 1200 on 2026-11-04. V205-10, V205-12 and V205-12b add 36, this part adds 13 (V205-13: 9, V205-15: 4), so V205-16 starts with about 5 to spare. Do not add tests to `tests/marketdata/` beyond the ones written here; V205-14's tests live in `tests/scripts/` (suite `tooling`).

# Phase 5 -- One FX rate per pair per day (L1-a): writing the rows, then reading them

### Task V205-13: Snap at 08:00 Berlin: `fx_snap.snap`, refresher step

**Model:** opus — a clock gate across both DST switches, insert-if-absent semantics across cycles, and a refresher step that must never fail the cycle during the deploy window.

**Files:**
- Create: `swingbot/core/marketdata/fx_snap.py`, `tests/marketdata/test_fx_snap.py`, `tests/refresher/test_fx_snap_step.py`
- Modify: `swingbot/refresher/quotes.py` (import, `fx_snap_step`, docstring), `swingbot/refresher/loop.py` (`STEPS`, docstring)

**Interfaces:**
- Consumes (V205-11): `fx_daily_rate_repo()` with `days_present(base, account, *, conn=None) -> set[date]` and `insert_if_absent(rows, *, conn=None) -> int` (rows `{base, account, day, rate, bar_date, snapped_at, source}`; it refuses a non-positive rate or a source outside `snap`/`backfill`, and returns 0 for no rows); `quote_currency_repo().known_codes(*, conn=None) -> set[str]`. (V205-12): `fx_daily.rate_before(frame, day) -> tuple[float, date] | None`. Existing: `fx._major(code) -> (major, scale)`, `fx.account_currency_code()`, `fx._pair_frame(pair, *, refresh=True)`, `BERLIN_TZ` (`swingbot/core/market/session.py:16`), `loop.CycleContext.now` (aware UTC), `loop._run_steps(ctx)`, `swallowed(log, tag, exc, msg="", *args, level=...)`.
- Produces (ledger, index "fx_snap"): `fx_snap.SNAP_HOUR = 8`; `pairs_in_use() -> list[tuple[str, str]]`; `snap(now: datetime) -> int`; private helpers `_berlin(now) -> datetime`, `_pair_frame(base, account)` and `_row(base, account, day, found, *, now, source) -> dict`, which V205-14 reuses; `quotes.fx_snap_step(ctx) -> None`, appended to `loop.STEPS` after `quotes.fx_step`. Test doubles `FRAME`, `FakeDaily`, `FakeCodes` in `tests/marketdata/test_fx_snap.py`, which V205-14's tests import.

**What it does (spec L1-a, Snap).** On every refresher cycle, once the Berlin clock is at or past 08:00, every pair in use that has no row for the Berlin day D gets one: `fx_daily.rate_before(frame, D)`, from the pair file as it stands (`fx._pair_frame(..., refresh=False)`: no fetch, no third cache). "In use" is the major of every `known` code in the quote-currency store, minus the account's own major. A missing frame, or a bar more than 7 days old, writes no row. Insert-if-absent: the first value written is the day's value, and a second cycle the same day writes nothing. `now` is converted with `astimezone(BERLIN_TZ)`; a naive `now` is refused, never guessed.

**Failure in the deploy window.** `deploy.sh` runs `alembic upgrade head` after `up --wait`, so the refresher's first cycles can run before `fx_daily_rates` exists. `fx_snap_step` catches every exception and calls `swallowed(log, "ops.refresher.fx_snap", ...)`. The tag matches `^(scan|marketdata|earnings|runstate|ops)\.` and is new repo-wide. The step does **not** set `ctx.report.error`. That field feeds the heartbeat's `last_error`, which is the admin's "refresher is failing" signal, and a missed snap does not make quotes stale: the next cycle writes the same row.

- [ ] **Step 1: Write the failing snap tests**

Create `tests/marketdata/test_fx_snap.py`:

```python
"""v205 L1-a: the 08:00 Berlin snap, fx_snap.snap and fx_snap.pairs_in_use.

Fakes stand in for both repositories and the pair files. Every expected rate is
a literal read off the fixture frame by hand, never recomputed. FRAME, FakeDaily
and FakeCodes are imported by tests/refresher/test_fx_snap_step.py and
tests/scripts/test_backfill_fx_daily_rates.py (V205-14)."""
import ast
import pathlib
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.marketdata import fx, fx_snap

UTC = timezone.utc
FRAME = pd.DataFrame(
    {"Close": [0.9200, 0.8600, 0.8680, 0.8700, 0.8720]},
    index=pd.DatetimeIndex(["2026-03-27", "2026-10-23", "2026-11-02", "2026-11-03", "2026-11-04"]))


class FakeDaily:
    """fx_daily_rates with on-conflict-do-nothing semantics."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.inserts: list[list[dict]] = []

    def days_present(self, base, account, *, conn=None):
        return {day for (b, a, day) in self.rows if (b, a) == (base, account)}

    def insert_if_absent(self, rows, *, conn=None):
        rows = list(rows)
        self.inserts.append(rows)
        written = 0
        for row in rows:
            key = (row["base"], row["account"], row["day"])
            if key not in self.rows:
                self.rows[key] = dict(row)
                written += 1
        return written


class FakeCodes:
    def __init__(self, codes):
        self.codes = set(codes)

    def known_codes(self, *, conn=None):
        return set(self.codes)


@pytest.fixture
def world(monkeypatch):
    daily, codes = FakeDaily(), FakeCodes({"USD", "EUR"})
    frames, reads = {"USDEUR=X": FRAME}, []

    def pair_frame(pair, *, refresh=True):
        reads.append((pair, refresh))
        return frames.get(pair)
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: codes)
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", pair_frame)
    return SimpleNamespace(daily=daily, codes=codes, frames=frames, reads=reads)


def test_pairs_in_use_are_the_majors_of_known_codes_except_the_account(world, monkeypatch):
    world.codes.codes = {"USD", "GBp", "GBP", "ZAc", "EUR", "ILA"}
    assert fx_snap.pairs_in_use() == [("GBP", "EUR"), ("ILS", "EUR"), ("USD", "EUR"), ("ZAR", "EUR")]
    monkeypatch.setattr(fx, "account_currency_code", lambda: "GBP")
    world.codes.codes = {"GBp", "USD"}
    assert fx_snap.pairs_in_use() == [("USD", "GBP")]           # pence into pounds: no pair


def test_from_eight_berlin_the_day_gets_the_close_before_it(world):
    now = datetime(2026, 11, 4, 7, 0, tzinfo=UTC)                # 08:00 CET
    assert fx_snap.snap(now) == 1
    assert world.daily.rows == {("USD", "EUR", date(2026, 11, 4)): {
        "base": "USD", "account": "EUR", "day": date(2026, 11, 4), "rate": 0.8700,
        "bar_date": date(2026, 11, 3), "snapped_at": now, "source": "snap"}}
    assert world.reads == [("USDEUR=X", False)]                  # the file as it stands, no fetch


def test_two_cycles_on_one_berlin_day_write_once_and_keep_the_first_value(world):
    assert fx_snap.snap(datetime(2026, 11, 4, 7, 0, tzinfo=UTC)) == 1
    world.frames["USDEUR=X"] = FRAME.assign(Close=[0.9200, 0.8600, 0.8680, 0.9900, 0.8720])
    assert fx_snap.snap(datetime(2026, 11, 4, 15, 0, tzinfo=UTC)) == 0
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 4))]["rate"] == 0.8700
    assert len(world.reads) == 1                                 # a present day reads no frame


@pytest.mark.parametrize("day,gate_utc_hour,rate,bar", [
    (date(2026, 3, 29), 6, 0.9200, date(2026, 3, 27)),          # CEST from 01:00 UTC: 08:00 = 06:00 UTC
    (date(2026, 10, 25), 7, 0.8600, date(2026, 10, 23)),        # CET again from 01:00 UTC: 08:00 = 07:00 UTC
])
def test_the_gate_is_eight_berlin_on_both_dst_switch_days(world, day, gate_utc_hour, rate, bar):
    just_before = datetime(day.year, day.month, day.day, gate_utc_hour - 1, 59, tzinfo=UTC)
    at_gate = datetime(day.year, day.month, day.day, gate_utc_hour, 0, tzinfo=UTC)
    assert fx_snap.snap(just_before) == 0 and world.daily.rows == {}
    assert fx_snap.snap(at_gate) == 1
    stored = world.daily.rows[("USD", "EUR", day)]
    assert (stored["rate"], stored["bar_date"]) == (rate, bar)


def test_after_midnight_berlin_before_eight_nothing_is_written(world):
    assert fx_snap.snap(datetime(2026, 11, 4, 23, 30, tzinfo=UTC)) == 0     # 00:30 Berlin 11-05
    assert world.daily.rows == {} and world.reads == []


def test_no_frame_or_a_stale_bar_writes_no_row(world):
    world.codes.codes = {"USD", "GBP"}                           # no GBPEUR=X file
    assert fx_snap.snap(datetime(2026, 11, 4, 9, 0, tzinfo=UTC)) == 1
    assert set(world.daily.rows) == {("USD", "EUR", date(2026, 11, 4))}
    world.daily.rows.clear()
    assert fx_snap.snap(datetime(2026, 11, 12, 9, 0, tzinfo=UTC)) == 0     # bar 11-04 is 8 days old


def test_a_naive_now_is_refused(world):
    with pytest.raises(ValueError, match="aware"):
        fx_snap.snap(datetime(2026, 11, 4, 9, 0))


def test_the_module_imports_nothing_from_admin_or_flask():
    tree = ast.parse(pathlib.Path(fx_snap.__file__).read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(name.startswith(("swingbot.admin", "flask")) for name in names), names
```

Hand checks: 08:00 CET on 11-04 is 07:00 UTC, and the newest bar before 11-04 is 11-03 (0.8700). On 2026-03-29 Berlin is on CEST from 01:00 UTC, so 05:59 UTC is 07:59 local; the newest bar before 03-29 is 03-27 (0.9200, 2 days). On 2026-10-25 Berlin is back on CET from 01:00 UTC, so 06:59 UTC is 07:59 local; the newest bar is 10-23 (0.8600). For 11-12 the newest bar is 11-04, 8 days back, past `FALLBACK_DAYS`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_snap.py`
Expected: collection fails with `ImportError: cannot import name 'fx_snap' from 'swingbot.core.marketdata'`.

- [ ] **Step 3: Write `fx_snap.py`**

Create `<wt>/swingbot/core/marketdata/fx_snap.py`:

```python
"""v205 L1-a: write the day's FX rate from 08:00 Berlin (`snap`); V205-14 adds `backfill`.

The row for (base, account, Berlin day D) holds `fx_daily.rate_before(frame, D)`:
the last positive daily close dated strictly before D, read from the pair file
the refresher keeps up to date (`fx._pair_frame(..., refresh=False)`: the cache
file as it stands, never a fetch, so there is no third OHLCV cache). Rows are
written insert-if-absent and never updated, so the first value written is the
day's value. The rule reads only bars before D. A refresher that was down at
08:00, or a currency first seen later in the day, therefore writes the same
value on its next cycle.

"In use" is the major code of every `known` answer in the quote-currency store,
except the account's own major. Rows hold majors only; a minor unit's scale is
applied by the reader (`fx.fx_rate`), never stored.

Display only, like `fx`. Imports nothing from the admin or flask.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo, quote_currency_repo
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.marketdata import fx, fx_daily

log = logging.getLogger(__name__)

#: The Berlin hour from which the day's row is written.
SNAP_HOUR = 8


def pairs_in_use() -> list[tuple[str, str]]:
    """Sorted (base major, account major) for every known quote currency but the account's own."""
    account = fx._major(fx.account_currency_code())[0]
    bases = {fx._major(code)[0] for code in quote_currency_repo().known_codes() if code}
    return sorted((base, account) for base in bases if base != account)


def _berlin(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("fx_snap needs an aware datetime, got a naive one")
    return now.astimezone(BERLIN_TZ)


def _pair_frame(base: str, account: str):
    return fx._pair_frame(f"{base}{account}=X", refresh=False)


def _row(base: str, account: str, day: date, found: tuple[float, date], *,
         now: datetime, source: str) -> dict:
    rate, bar_date = found
    return {"base": base, "account": account, "day": day, "rate": rate,
            "bar_date": bar_date, "snapped_at": now, "source": source}


def snap(now: datetime) -> int:
    """Write the Berlin day's row for every pair in use that lacks one; rows written.

    Nothing before 08:00 Berlin. A pair with no frame, or whose newest bar
    before the day is more than FALLBACK_DAYS old, gets no row."""
    local = _berlin(now)
    if local.hour < SNAP_HOUR:
        return 0
    day = local.date()
    repo = fx_daily_rate_repo()
    rows = []
    for base, account in pairs_in_use():
        if day in repo.days_present(base, account):
            continue
        found = fx_daily.rate_before(_pair_frame(base, account), day)
        if found is not None:
            rows.append(_row(base, account, day, found, now=now, source="snap"))
    written = repo.insert_if_absent(rows)
    if written:
        log.info("fx snap %s: %d fx_daily_rates row(s)", day.isoformat(), written)
    return written
```

A cycle with every row present costs one `known_codes` query and one `days_present` query per pair; `insert_if_absent([])` issues no statement (V205-11).

- [ ] **Step 4: Run the snap tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_snap.py`
Expected: `9 passed`, `0 failed` (8 test functions, the DST one parametrised twice).

- [ ] **Step 5: Write the failing refresher-step tests**

Create `tests/refresher/test_fx_snap_step.py`:

```python
"""v205 L1-a: the refresher's FX snap step runs every cycle and never fails one."""
from datetime import date, datetime, timezone

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx, fx_snap
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet
from tests.marketdata.test_fx_snap import FRAME, FakeCodes, FakeDaily

UTC = timezone.utc


def _ctx(now):
    return loop.CycleContext(now, "closed", SymbolSet((), ()), [], [], False,
                             loop.CycleReport("closed", 1800.0))


def test_the_step_snaps_at_the_cycles_own_now(monkeypatch):
    seen = []
    monkeypatch.setattr(quotes.fx_snap, "snap", lambda now: seen.append(now) or 0)
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    quotes.fx_snap_step(ctx)
    assert seen == [ctx.now]


def test_a_failing_snap_is_swallowed_and_leaves_the_cycle_error_alone(monkeypatch):
    def missing_table(now):
        raise RuntimeError('relation "fx_daily_rates" does not exist')
    monkeypatch.setattr(quotes.fx_snap, "snap", missing_table)
    before = sw.snapshot().get("ops.refresher.fx_snap", {}).get("count", 0)
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    quotes.fx_snap_step(ctx)
    assert ctx.report.error is None
    assert sw.snapshot()["ops.refresher.fx_snap"]["count"] == before + 1


def test_the_snap_step_follows_the_fx_step():
    assert loop.STEPS.index(quotes.fx_snap_step) == loop.STEPS.index(quotes.fx_step) + 1


def test_the_snap_runs_even_when_the_fx_step_returns_early(monkeypatch):
    seen = []

    def no_codes(*args, **kwargs):
        raise AssertionError("fx_step resolved codes on an empty cycle")
    monkeypatch.setattr(quotes.fx, "refresh_quote_codes", no_codes)
    monkeypatch.setattr(quotes.fx_snap, "snap", lambda now: seen.append(now) or 0)
    monkeypatch.setattr(loop, "STEPS", [quotes.fx_step, quotes.fx_snap_step])
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    loop._run_steps(ctx)
    assert seen == [ctx.now] and ctx.report.error is None


def test_two_cycles_on_one_berlin_day_insert_the_row_once(monkeypatch):
    daily = FakeDaily()
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: FakeCodes({"USD"}))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", lambda pair, *, refresh=True: FRAME)
    quotes.fx_snap_step(_ctx(datetime(2026, 11, 4, 7, 5, tzinfo=UTC)))
    quotes.fx_snap_step(_ctx(datetime(2026, 11, 4, 7, 10, tzinfo=UTC)))
    assert [len(batch) for batch in daily.inserts] == [1, 0]
    assert daily.rows[("USD", "EUR", date(2026, 11, 4))]["snapped_at"] == datetime(
        2026, 11, 4, 7, 5, tzinfo=UTC)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/refresher/test_fx_snap_step.py`
Expected: FAIL; `AttributeError: module 'swingbot.refresher.quotes' has no attribute 'fx_snap'` (and `'fx_snap_step'`).

- [ ] **Step 7: Add the step**

In `<wt>/swingbot/refresher/quotes.py`, change the import line

```python
from swingbot.core.marketdata import data, fx
```

to

```python
from swingbot.core.marketdata import data, fx, fx_snap
```

and append after `fx_step`:

```python
def fx_snap_step(ctx: "CycleContext") -> None:
    """v205: from 08:00 Berlin, the day's fx_daily_rates rows (insert-if-absent).

    Runs every cycle, after `fx_step` and even when it returned early. A failure
    is swallowed and stays out of `report.error`, because a missed snap does not
    make quotes stale and the next cycle writes the same row. Before
    `alembic upgrade head` creates the table, each cycle logs one warning."""
    try:
        fx_snap.snap(ctx.now)
    except Exception as exc:  # noqa: BLE001 - a missed snap never fails the cycle
        swallowed(log, "ops.refresher.fx_snap", exc, "fx snap failed: %s", exc,
                  level=logging.WARNING)
```

Extend the module docstring's last paragraph to:

```text
``fx_step`` resolves quote-currency codes for every symbol it sees (and, on a
full cycle, every ticker ever traded) and refreshes the pair frames.
``fx_snap_step`` (v205) writes the day's FX rate rows from 08:00 Berlin.
```

The docstring and code must not contain `refresh_symbol`, `data_refresh`, `update_cache` or `set_default_lock_timeout`: `test_refresher_never_sets_the_admin_lock_timeout_or_writes_ohlcv` scans every refresher file for them.

In `<wt>/swingbot/refresher/loop.py`, change

```python
STEPS: list[Callable[[CycleContext], None]] = [quotes.quote_step, quotes.fx_step]
```

to

```python
STEPS: list[Callable[[CycleContext], None]] = [quotes.quote_step, quotes.fx_step,
                                               quotes.fx_snap_step]
```

and in the module docstring change "``STEPS`` starts with the quote and FX steps (``quotes``)" to "``STEPS`` starts with the quote and FX steps and the v205 FX snap (``quotes``)".

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/refresher/test_fx_snap_step.py`
Expected: `5 passed`, `0 failed`.

Run: `python <wt>/scripts/dev/testrun.py suite refresher` -- expected `0 failed`, `0 xfailed`. The `test_loop.py` and `test_quote_cycle.py` fixtures replace `loop.STEPS`, so the new step never runs there.

Run: `python <wt>/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` -- expected `0 failed` (`ops.refresher.fx_snap` is new and unique).

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx_snap.py <wt>/swingbot/refresher/quotes.py` -- every new function `A` or `B`; `python <wt>/scripts/dev/complexity_gate.py` clean.

- [ ] **Step 9: Commit (two scoped commits)**

```bash
git -C <wt> add swingbot/core/marketdata/fx_snap.py tests/marketdata/test_fx_snap.py
git -C <wt> commit -m "feat(marketdata): fx_snap.snap writes the day's FX rate from 08:00 Berlin (v205 V205-13)"
git -C <wt> add swingbot/refresher/quotes.py swingbot/refresher/loop.py tests/refresher/test_fx_snap_step.py
git -C <wt> commit -m "feat(refresher): FX snap step after fx_step, failures swallowed (v205 V205-13)"
```

### Task V205-14: Backfill: `fx_snap.backfill`, ops script, deploy runbook step

**Model:** sonnet — the same rule and helpers V205-13 built, applied over past days, plus an argparse script and a runbook section; the one non-obvious part (Postgres's bound-parameter cap) is spelled out below.

**Files:**
- Modify: `swingbot/core/marketdata/fx_snap.py` (append `INSERT_CHUNK`, `planned_rows`, `backfill` and two helpers; two names added to the `datetime` import; the freshness guard in `snap` plus `_last_weekday_before`), `tests/marketdata/test_fx_snap.py` (three freshness tests), `docs/deploy/DEPLOY_HETZNER.md` (a v205 subsection at the end of "The refresher service (v201)", before "## Accessing the admin UI")
- Create: `scripts/ops/backfill_fx_daily_rates.py`, `tests/scripts/test_backfill_fx_daily_rates.py`

**Interfaces:**
- Consumes (V205-13): `fx_snap.pairs_in_use()`, `_berlin(now)`, `_pair_frame(base, account)`, `_row(base, account, day, found, *, now, source)`, `snap(now)`; test doubles `FakeDaily`, `FakeCodes` from `tests/marketdata/test_fx_snap.py`. (V205-12): `fx_daily.rate_before(frame, day)` and its private `fx_daily._bar_dates(index) -> np.ndarray` (datetime64[D]; the same normalisation the rule uses, so the first day is computed the way the rule reads dates). (V205-11): `fx_daily_rate_repo()` `days_present`, `insert_if_absent`.
- Produces (ledger, index "fx_snap" backfill, "Backfill script"): `fx_snap.INSERT_CHUNK = 1000`; `planned_rows(*, start: date | None = None, end: date | None = None, now: datetime | None = None) -> list[dict]` (the rows a backfill would write; the dry run's source); `backfill(*, start=None, end=None, now=None) -> int`; `scripts/ops/backfill_fx_daily_rates.py:main(argv: list[str] | None = None) -> int`. V205-18 runs the script on production unchanged.

**The rule (spec L1-a, Backfill; index "fx_snap").** For each pair in use, every Berlin day from the day after the frame's first bar through `end` gets `rate_before(frame, day)` with `source="backfill"`, where `rate_before` gives a value. `end` defaults to the Berlin date of `now` (aware; default `datetime.now(timezone.utc)`). `start`, when given, moves the first day later, never earlier. Days already present are skipped and the insert is insert-if-absent, so a re-run writes 0 and a snapped row is never overwritten. It reads frames like the snap (`refresh=False`, no fetch). The rows are written in chunks of `INSERT_CHUNK`. A row binds 8 parameters, Postgres allows 65,535 per statement, and yfinance FX history reaches back to 2003 (about 8,400 days per pair), so one statement per pair would fail.

**Freshness guard (controller, 2026-11-04; amends V205-13's `snap`).** Insert-if-absent makes a stale snap permanent, so `snap` writes a pair's row only when the frame is current for D: its last bar date must be on or after `_last_weekday_before(D)` (the latest Mon–Fri date strictly before D; Monday D needs Friday's bar). A stale or missing frame writes **no** row that cycle and logs once per pair per day at INFO. A later cycle, after `fx_step` has refreshed the pair file, writes it. Until then, reads use the nearest earlier row within `FALLBACK_DAYS` (spec L1-a Read). This keeps `snap(D) == backfill(D)` true for the frame backfill would later see. Add `_last_weekday_before(day) -> date` as a private helper in `fx_snap.py`. Add tests to `tests/marketdata/test_fx_snap.py` (Step 1, failing first):
- a frame ending two weekdays before D writes nothing and returns 0;
- the same day, after the frame gains the D-1 bar, a second `snap` writes the row;
- Monday D with a frame ending on the Friday before writes the row.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_backfill_fx_daily_rates.py`:

```python
"""v205 L1-a: fx_snap.backfill, snap(D) == backfill(D), and the ops script.

Every expected rate is read off the fixture frame by hand, never recomputed."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.ops import backfill_fx_daily_rates as script
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.marketdata import fx, fx_snap
from tests.marketdata.test_fx_snap import FakeCodes, FakeDaily

UTC = timezone.utc
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)                  # 13:00 Berlin (CET)
WEEK = pd.DataFrame({"Close": [0.8650, 0.8640, 0.0, 0.8700]},   # Monday 11-02 closed at 0.0
                    index=pd.DatetimeIndex(["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]))
EXPECTED = {                                                     # day -> (rate, bar_date), by hand
    date(2026, 10, 30): (0.8650, date(2026, 10, 29)),
    date(2026, 10, 31): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 1): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 2): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 3): (0.8640, date(2026, 10, 30)),             # the 0.0 close is skipped
    date(2026, 11, 4): (0.8700, date(2026, 11, 3)),
}


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(daily=FakeDaily(), frames={"USDEUR=X": WEEK})
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: state.daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: FakeCodes({"USD", "EUR"}))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", lambda pair, *, refresh=True: state.frames.get(pair))
    return state


def _stored(daily):
    return {day: (row["rate"], row["bar_date"]) for (_, _, day), row in daily.rows.items()}


def test_backfill_fills_each_day_after_the_first_bar_through_berlin_today(world):
    assert fx_snap.backfill(now=NOW) == 6
    assert _stored(world.daily) == EXPECTED
    assert {(r["source"], r["snapped_at"]) for r in world.daily.rows.values()} == {("backfill", NOW)}


def test_a_gap_past_seven_days_leaves_those_days_without_a_row(world):
    world.frames["USDEUR=X"] = pd.DataFrame(
        {"Close": [0.90, 0.91]}, index=pd.DatetimeIndex(["2026-10-01", "2026-10-20"]))
    assert fx_snap.backfill(end=date(2026, 10, 21), now=NOW) == 8
    assert set(_stored(world.daily)) == {date(2026, 10, d) for d in range(2, 9)} | {date(2026, 10, 21)}


def test_start_and_end_bound_the_days(world):
    assert fx_snap.backfill(start=date(2026, 11, 2), end=date(2026, 11, 3), now=NOW) == 2
    assert set(_stored(world.daily)) == {date(2026, 11, 2), date(2026, 11, 3)}
    assert fx_snap.backfill(start=date(2026, 1, 1), end=date(2026, 10, 30), now=NOW) == 1   # never before bar 1 + 1


def test_a_rerun_writes_nothing_and_a_snapped_row_is_kept(world):
    snapped = {"base": "USD", "account": "EUR", "day": date(2026, 11, 4), "rate": 0.8711,
               "bar_date": date(2026, 11, 3), "snapped_at": NOW, "source": "snap"}
    world.daily.rows[("USD", "EUR", date(2026, 11, 4))] = dict(snapped)
    assert fx_snap.backfill(now=NOW) == 5
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 4))] == snapped
    assert fx_snap.backfill(now=NOW) == 0


def test_snap_equals_backfill_on_every_day(world):
    fx_snap.backfill(now=NOW)
    backfilled = _stored(world.daily)
    for day in sorted(EXPECTED):
        world.daily = FakeDaily()
        assert fx_snap.snap(datetime(day.year, day.month, day.day, 8, 0, tzinfo=BERLIN_TZ)) == 1
        assert _stored(world.daily) == {day: backfilled[day]}, day


def test_a_long_history_is_inserted_in_chunks(world):
    days = pd.date_range("2019-01-01", periods=2600, freq="D")
    world.frames["USDEUR=X"] = pd.DataFrame({"Close": [0.9] * len(days)}, index=days)
    end = date(2019, 1, 1) + timedelta(days=2500)
    assert fx_snap.backfill(end=end, now=NOW) == 2500
    assert [len(batch) for batch in world.daily.inserts] == [1000, 1000, 500]


def test_the_dry_run_prints_counts_and_writes_nothing(world, capsys):
    assert script.main(["--dry-run", "--end", "2026-11-04"]) == 0
    out = capsys.readouterr().out
    assert "USDEUR planned=6" in out and "planned=6 (dry run: nothing written)" in out
    assert world.daily.inserts == []


def test_the_script_writes_and_prints_the_count(world, capsys):
    assert script.main(["--end", "2026-11-04"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "written=6"
    assert script.main(["--end", "2026-11-04"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "written=0"


@pytest.mark.parametrize("argv", [["--start", "2026-11-04", "--end", "2026-11-01"], ["--end", "11/04/2026"]])
def test_bad_arguments_exit_two(world, argv):
    with pytest.raises(SystemExit) as raised:
        script.main(argv)
    assert raised.value.code == 2
```

Hand checks for the gap case: the bar of 10-01 serves 10-02 through 10-08 (7 days back at most), 10-09 to 10-20 have no bar within 7 days (the 10-20 bar is not before 10-20), and 10-21 takes 10-20's 0.91: 7 + 1 = 8 rows. For the bounded case, `start=2026-01-01` is earlier than the day after the first bar (10-30), so the range starts at 10-30 and `end=10-30` leaves exactly one day. The chunk case covers days 2019-01-02 through 2019-01-01 + 2500 days, which is 2,500 days, each with yesterday's bar.

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_backfill_fx_daily_rates.py`
Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.ops.backfill_fx_daily_rates'`.

- [ ] **Step 3: Append the backfill to `fx_snap.py`**

In `<wt>/swingbot/core/marketdata/fx_snap.py`, change `from datetime import date, datetime` to `from datetime import date, datetime, timedelta, timezone`. In the module docstring's first line change "`snap`); V205-14 adds `backfill`." to "`snap`) and fill past days (`backfill`, the v205 one-off)." At the end of the module append:

```python
#: Rows per INSERT. A row binds 8 parameters and Postgres allows 65,535 per
#: statement; one pair's history since 2003 is about 8,400 days.
INSERT_CHUNK = 1000


def _days(first: date, last: date):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _pair_rows(base: str, account: str, *, start: date | None, end: date,
               now: datetime, present: set[date]) -> list[dict]:
    """The backfill rows of one pair: each absent day after its first bar that the rule serves."""
    frame = _pair_frame(base, account)
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return []
    first = fx_daily._bar_dates(frame.index).min().astype(object) + timedelta(days=1)
    if start is not None and start > first:
        first = start
    rows = []
    for day in _days(first, end):
        found = None if day in present else fx_daily.rate_before(frame, day)
        if found is not None:
            rows.append(_row(base, account, day, found, now=now, source="backfill"))
    return rows


def planned_rows(*, start: date | None = None, end: date | None = None,
                 now: datetime | None = None) -> list[dict]:
    """Every row a backfill would write now (the dry run prints their counts)."""
    now = now or datetime.now(timezone.utc)
    last = end or _berlin(now).date()
    repo = fx_daily_rate_repo()
    rows: list[dict] = []
    for base, account in pairs_in_use():
        rows += _pair_rows(base, account, start=start, end=last, now=now,
                           present=repo.days_present(base, account))
    return rows


def backfill(*, start: date | None = None, end: date | None = None,
             now: datetime | None = None) -> int:
    """Fill every past Berlin day the frames allow (insert-if-absent; idempotent). Rows written."""
    rows = planned_rows(start=start, end=end, now=now)
    repo = fx_daily_rate_repo()
    written = sum(repo.insert_if_absent(rows[i:i + INSERT_CHUNK])
                  for i in range(0, len(rows), INSERT_CHUNK))
    log.info("fx backfill: %d of %d planned fx_daily_rates row(s) written", written, len(rows))
    return written
```

`_bar_dates(...).min().astype(object)` turns the `datetime64[D]` minimum into a `datetime.date`, as `rate_before` does with its own newest date. A day costs one vectorised `rate_before` call, so the production backfill (a few pairs, about 8,400 days each) runs in seconds to a minute; it is a one-off.

- [ ] **Step 4: Write the script**

Create `<wt>/scripts/ops/backfill_fx_daily_rates.py`:

```python
#!/usr/bin/env python3
"""v205: fill fx_daily_rates for every past Berlin day the FX pair files allow.

One-off and idempotent. The row for day D is the last positive daily close
dated strictly before D (bar at most 7 days old), the same rule the
refresher's 08:00 snap uses, so a backfilled day equals the day's snap. It
writes insert-if-absent, so a snapped row is never overwritten and a re-run
writes 0. It reads the pair files in market_data/daily/ as they stand and never
fetches. Nothing is printed but counts.

Run on production once, after `alembic upgrade head` created the table
(docs/deploy/DEPLOY_HETZNER.md, "v205: daily FX rates"):

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python scripts/ops/backfill_fx_daily_rates.py --dry-run"
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python scripts/ops/backfill_fx_daily_rates.py"

Exit codes: 0 done, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata import fx_snap  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat,
                    help="First Berlin day, YYYY-MM-DD. Default: the day after each pair's first bar.")
    ap.add_argument("--end", type=date.fromisoformat,
                    help="Last Berlin day, YYYY-MM-DD. Default: Berlin today.")
    ap.add_argument("--dry-run", action="store_true", help="Print the planned counts; write nothing.")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if args.start and args.end and args.start > args.end:
        ap.error("--start is after --end")
    if args.dry_run:
        rows = fx_snap.planned_rows(start=args.start, end=args.end)
        pairs = Counter(f"{row['base']}{row['account']}" for row in rows)
        for pair, count in sorted(pairs.items()):
            print(f"{pair} planned={count}")
        print(f"planned={len(rows)} (dry run: nothing written)")
        return 0
    print(f"written={fx_snap.backfill(start=args.start, end=args.end)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`argparse` exits with code 2 for both an unparseable date (`type=date.fromisoformat` raises `ValueError`) and `ap.error(...)`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/scripts/test_backfill_fx_daily_rates.py`
Expected: `10 passed`, `0 failed` (9 test functions, the bad-argument one parametrised twice).

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_snap.py` -- expected `9 passed` (V205-13's snap is unchanged).

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx_snap.py <wt>/scripts/ops/backfill_fx_daily_rates.py` -- every function `A` or `B`; `python <wt>/scripts/dev/complexity_gate.py` clean.

- [ ] **Step 6: Add the runbook step**

In `<wt>/docs/deploy/DEPLOY_HETZNER.md`, insert this subsection after the last bullet of "## The refresher service (v201)" (the `scripts/ops/rollback_to.sh` bullet) and before "## Accessing the admin UI":

```markdown
### v205: daily FX rates (`fx_daily_rates`)

The admin converts money at one FX rate per currency pair per Berlin day,
stored in `fx_daily_rates` (revision `v205_001`). The refresher writes the
day's row from 08:00 Berlin by itself. Past days are filled once, by a
backfill, after the deploy that brings the revision:

1. Deploy as usual. `deploy.sh` runs `alembic upgrade head` after
   `up --wait`; until it has, the admin shows converted amounts as
   `fx_missing` and the refresher logs `fx snap failed` once per cycle. Both
   recover by themselves.
2. Check the revision:
   `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"`
   prints `v205_001 (head)` or a later head.
3. Dry run:
   `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/backfill_fx_daily_rates.py --dry-run"`.
   It prints `<PAIR> planned=<n>` per pair and the total, and writes nothing.
4. Backfill: the same command without `--dry-run`. It prints `written=<n>`.
   A re-run is safe (insert-if-absent) and prints `written=0`.

Rollback: redeploy the previous image (§ Rolling back). The old code never
reads the table, so it can stay. To remove it, run
`docker compose exec -T bot alembic downgrade <the revision v205_001 revises>`
(`v200_001` when v205 was written).
```

No test reads this doc and no `.env` key is added, so nothing else needs a run.

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git -C <wt> add swingbot/core/marketdata/fx_snap.py scripts/ops/backfill_fx_daily_rates.py tests/scripts/test_backfill_fx_daily_rates.py
git -C <wt> commit -m "feat(ops): fx_daily_rates backfill, same rule as the 08:00 snap (v205 V205-14)"
git -C <wt> add docs/deploy/DEPLOY_HETZNER.md
git -C <wt> commit -m "docs(deploy): v205 migration and FX backfill step (v205 V205-14)"
```

### Task V205-15: `fx.fx_rate` reads the table; strictly-before rule replaces `_close_on_or_before`; FX tests updated

**Model:** opus — the first deliberate output change: the rate moves from "close on the day" to "close before the day", and every moved figure must be re-derived by hand while goldens stay frozen and budgets stay green.

**Files:**
- Modify: `swingbot/core/marketdata/fx.py` (import, `FALLBACK_DAYS`, `fx_rate`, new `_day_rate`, delete `_close_on_or_before`, module docstring), `tests/marketdata/test_fx.py`, `tests/marketdata/test_fx_persisted.py`, `tests/admin_perf/money_reference.py`, `tests/admin_perf/golden_book.py` (`FX_DAILY_ROWS`, `fx_daily_rows`, `seed_fx_daily`), `tests/admin_perf/conftest.py` (`golden_seed.set_fx` seeds the table; teardown resets the memo)

**Interfaces:**
- Consumes (V205-12): `fx_daily.FALLBACK_DAYS`, `fx_daily.rate_before(frame, day)`. (V205-12b): `fx_daily.lookup(base, account, day) -> float | None` (majors, no scale; a read error is `None`), `fx_daily.reset_memo()`. (V205-11): `schema.fx_daily_rates`, `fx_daily_rate_repo().insert_if_absent(rows, *, conn=None)`. (V205-10): the `fx._unknown_until` reset already in both `_isolated` fixtures. (V205-4/4b): `golden_seed.set_fx(scale)`, `golden_book.FX_CLOSES`, `ACCOUNT_CODE`, `FROZEN_NOW`, `money_reference` constants.
- Produces (ledger, index "fx_rate after V205-15"): `fx_rate(from_code, to_code, on, *, refresh=True)`, signature unchanged; `fx.FALLBACK_DAYS is fx_daily.FALLBACK_DAYS`; `fx._close_on_or_before` gone. Test helpers `FakeRates`, `stored(...)` in `tests/marketdata/test_fx.py`; `golden_book.FX_DAILY_ROWS`, `fx_daily_rows(scale)`, `seed_fx_daily(scale)`. V205-16 builds on this `fx_rate` and edits `money_reference.py` again.

**The read (spec L1-a Read; index "fx_rate after V205-15").** Majors and scale are computed as today, and equal majors return the scale with no lookup. Otherwise the answer is `fx_daily.lookup(src, dst, day)`. On a miss with `refresh=True` (the refresher is off, the kill-switch path) it falls back to `fx_daily.rate_before(_pair_frame(pair, refresh=True), day)`, the same rule over the frame, and writes nothing. On a miss with `refresh=False` it is `None` (`fx_missing`): the request reads the table only, never a file. The result is multiplied by the scale. The day key is still `fx_convert._day` (the UTC date) until V205-16.

**What moves, by hand.** Each converted amount now uses the row for its day, the last positive close **before** that day. From `golden_book.FX_CLOSES`:

| Day D | Rate before (close on or before D) | Rate after (row for D) |
|---|---|---|
| 10-27 | 0.8620 | 0.8600 (bar 10-26) |
| 10-28 | 0.8620 (the 0.0 close skipped) | 0.8620 (bar 10-27) |
| 10-29 | 0.8650 | 0.8620 (bar 10-27; 10-28 is 0.0) |
| 10-30 | 0.8640 | 0.8650 (bar 10-29) |
| 10-31, 11-01 | 0.8640 | 0.8640 (bar 10-30) |
| 11-02 | 0.8680 | 0.8640 (bar 10-30, Friday) |
| 11-03 | 0.8700 | 0.8680 (bar 11-02) |
| 11-04 | 0.8720 | 0.8700 (bar 11-03) |

- [ ] **Step 1: Update `tests/marketdata/test_fx.py` (failing first)**

Change the imports to `from datetime import date, datetime` (unchanged) and `from swingbot.core.marketdata import fx, fx_daily`. Replace the `_isolated` fixture (keep V205-10's `_unknown_until` line) with:

```python
class FakeRates:
    """fx_daily_rates as fx_daily.lookup reads it. No insert method: a write would raise."""

    def __init__(self):
        self.rows: list[dict] = []

    def version(self, *, conn=None):
        return len(self.rows), None

    def all_rates(self, *, conn=None):
        return sorted(self.rows, key=lambda r: (r["base"], r["account"], r["day"]))


def stored(base, account, day, rate, bar_date):
    return {"base": base, "account": account, "day": day, "rate": rate, "bar_date": bar_date}


@pytest.fixture
def table(monkeypatch):
    """An empty fx_daily_rates; a test adds rows before its first fx_rate call."""
    rates = FakeRates()
    monkeypatch.setattr(fx_daily, "fx_daily_rate_repo", lambda: rates)
    fx_daily.reset_memo()
    yield rates
    fx_daily.reset_memo()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, table):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})
    monkeypatch.setattr(fx, "_unknown_until", {})
```

Change these existing tests to the strictly-before rule (each body shown whole):

```python
def test_converts_at_the_last_close_before_the_day(cache):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92, "2026-10-21": 0.93})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.91)
    assert refreshed == [("USDEUR=X", "daily")]
```

(replaces `test_converts_at_the_exit_dates_close`).

In `test_an_unusable_close_is_none`, ask for `date(2026, 10, 21)` instead of `date(2026, 10, 20)`, so the unusable 10-20 close is the one the rule would pick.

```python
def test_minor_units_scale_to_their_major_currency(cache):
    frames, _ = cache
    frames["GBPEUR=X"] = _frame({"2026-10-19": 1.15})
    assert fx.fx_rate("GBp", "GBP", date(2026, 10, 20)) == pytest.approx(0.01)
    assert fx.fx_rate("GBp", "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)


def test_a_datetime_is_read_as_its_date(cache):
    frames, _ = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92})
    assert fx.fx_rate("USD", "EUR", datetime(2026, 10, 20, 21, 5)) == pytest.approx(0.91)
```

In `test_a_failed_refresh_still_reads_what_the_cache_has`, ask for `date(2026, 10, 21)` (the frame's 10-20 close, 0.92, is then the answer). In `test_a_pence_quoted_ticker_converts_at_one_hundredth_of_the_pound`, date the `GBPEUR=X` bar `"2026-10-19"`. `test_falls_back_to_the_last_prior_trading_days_close` (bar 10-16 for 10-18), `test_never_reaches_past_the_fallback_window` (bar 10-01 serves 10-08, not 10-09), `test_never_uses_a_later_close`, `test_a_missing_pair_is_none_never_one` and `test_a_loaded_pair_is_reused_within_the_ttl` keep their bodies: the new rule gives the same answers.

Append, after the `fx_rate` block:

```python
def test_a_stored_row_wins_and_reads_no_frame(cache, table):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91})
    table.rows.append(stored("USD", "EUR", date(2026, 10, 20), 0.95, date(2026, 10, 19)))
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.95)
    assert refreshed == []


def test_a_major_row_serves_a_minor_quote_with_its_scale(cache, table):
    _, refreshed = cache
    table.rows.append(stored("GBP", "EUR", date(2026, 10, 20), 1.15, date(2026, 10, 19)))
    assert fx.fx_rate("GBp", "EUR", date(2026, 10, 20)) == pytest.approx(0.0115)
    assert fx.fx_rate("GBp", "GBP", date(2026, 10, 20)) == pytest.approx(0.01)
    assert refreshed == []


def test_a_miss_falls_back_to_the_frame_by_the_same_rule_and_writes_nothing(cache, table):
    frames, refreshed = cache
    frames["USDEUR=X"] = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92})
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20)) == pytest.approx(0.91)
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 20), refresh=False) is None   # table only
    assert table.rows == [] and refreshed == [("USDEUR=X", "daily")]


def test_fallback_days_is_fx_dailys_and_the_old_scan_is_gone():
    assert fx.FALLBACK_DAYS is fx_daily.FALLBACK_DAYS
    assert not hasattr(fx, "_close_on_or_before")
```

- [ ] **Step 2: Update `tests/marketdata/test_fx_persisted.py`**

Add `from swingbot.core.marketdata import fx_daily` and `from tests.marketdata.test_fx import FakeRates, stored` to the imports. Add the same `table` fixture as in Step 1 (verbatim) above `_isolated`, and add `table` to `_isolated`'s parameters: `def _isolated(monkeypatch, table):`. Its body is unchanged.

Replace `test_rate_without_refresh_reads_the_disk_file_only` with:

```python
def test_rate_without_refresh_reads_the_table_only(no_network, table, monkeypatch):
    monkeypatch.setattr(fx.data_store, "load_normalized", _boom)        # never a file
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 28), refresh=False) is None
    table.rows.append(stored("USD", "EUR", date(2026, 10, 28), 0.9, date(2026, 10, 27)))
    fx_daily.reset_memo()
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 28), refresh=False) == pytest.approx(0.9)
```

In `test_convert_without_fetch_flags_unknown_never_zero` and `test_risk_weights_never_fetch_with_the_refresher_on`, add `table` to the parameters and make the first line of each body:

```python
    table.rows.append(stored("USD", "EUR", date(2026, 10, 28), 0.9, date(2026, 10, 27)))
```

Both run with `fetch=False`, so the rate now comes from the table; their assertions (9.0, weight 1.0) are unchanged.

- [ ] **Step 3: Run the two files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx.py`
Expected: FAIL. The strictly-before cases get today's on-the-day close (for example `0.92 != approx(0.91)`), `test_a_stored_row_wins_and_reads_no_frame` reads the frame, and `test_fallback_days_is_fx_dailys_and_the_old_scan_is_gone` finds `_close_on_or_before`.

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_persisted.py`
Expected: FAIL in `test_rate_without_refresh_reads_the_table_only` (`AssertionError: network call on a never-fetch path`).

- [ ] **Step 4: Rewire `fx_rate`**

In `<wt>/swingbot/core/marketdata/fx.py`:

Change `from swingbot.core.marketdata import data, data_refresh, data_store` to `from swingbot.core.marketdata import data, data_refresh, data_store, fx_daily`.

Replace the `FALLBACK_DAYS = 7` block (comment and value) with:

```python
#: How old the bar behind a rate may be (a week covers every market closure
#: without letting a stale rate stand in for a missing one). The same object as
#: fx_daily.FALLBACK_DAYS: one rule for the table, the snap and the fallback.
FALLBACK_DAYS = fx_daily.FALLBACK_DAYS
```

Replace `fx_rate` with:

```python
def fx_rate(from_code: str, to_code: str, on: date, *, refresh: bool = True) -> float | None:
    """The multiplier turning an amount in `from_code` into `to_code` on `on`.

    The scale alone for equal majors (GBp -> GBP is 0.01), with no lookup.
    Otherwise v205's day rate: the `fx_daily_rates` row for (FROM, TO, day),
    the last positive `{FROM}{TO}=X` close strictly before the day, times the
    minor-unit scale. On a missing row, `refresh=True` (the refresher is off)
    applies the same rule to the pair frame and writes nothing; `refresh=False`
    (the refresher is on) is None. Never 1.0 for a missing rate.
    """
    if not from_code or not to_code:
        return None
    src, src_scale = _major(from_code)
    dst, dst_scale = _major(to_code)
    scale = src_scale / dst_scale
    if src == dst:
        return scale
    day = on.date() if isinstance(on, datetime) else on
    rate = _day_rate(src, dst, day, refresh=refresh)
    return None if rate is None else rate * scale


def _day_rate(src: str, dst: str, day: date, *, refresh: bool) -> float | None:
    """The stored row's rate, else (refresh only) the same rule over the pair frame."""
    stored = fx_daily.lookup(src, dst, day)
    if stored is not None or not refresh:
        return stored
    found = fx_daily.rate_before(_pair_frame(f"{src}{dst}=X", refresh=True), day)
    return None if found is None else found[0]
```

Delete `_close_on_or_before` (the module's last function). `timedelta` stays imported (`refresh_quote_codes` uses it).

In the module docstring, after the paragraph ending "never serves an FX pair.", add:

```text
v205: a request reads one rate per pair per Berlin day from `fx_daily_rates`
(`fx_daily.lookup`): the last positive close dated strictly before the day,
written by the refresher's 08:00 snap (`fx_snap`) from these same files. With
the refresher off, a missing row is computed by the same rule from the frame.
```

`fx_daily` imports nothing from `fx`, so the new import makes no cycle; `test_the_module_imports_neither_fx_nor_admin_nor_flask` (V205-12) still guards it.

- [ ] **Step 5: Run the FX tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx.py`, then `... file tests/marketdata/test_fx_persisted.py`, `... file tests/marketdata/test_fx_quote_batch.py`, `... file tests/marketdata/test_fx_daily.py`, `... file tests/marketdata/test_fx_daily_lookup.py`
Expected: `0 failed` each; `test_fx.py` has 4 more tests than before this task.

- [ ] **Step 6: Seed the golden book's `fx_daily_rates`**

In `<wt>/tests/admin_perf/golden_book.py`, add `date` to the `datetime` import, and after `FX_CLOSES` add:

```python
#: fx_daily_rates rows for USD -> EUR, written by hand from FX_CLOSES (v205 V205-15):
#: Berlin day -> (rate, bar_date), the last positive close dated strictly before the day.
FX_DAILY_ROWS: dict[str, tuple[float, str]] = {
    "2026-10-27": (0.8600, "2026-10-26"),
    "2026-10-28": (0.8620, "2026-10-27"),
    "2026-10-29": (0.8620, "2026-10-27"),   # the 10-28 close is 0.0: skipped
    "2026-10-30": (0.8650, "2026-10-29"),
    "2026-10-31": (0.8640, "2026-10-30"),
    "2026-11-01": (0.8640, "2026-10-30"),
    "2026-11-02": (0.8640, "2026-10-30"),   # Monday: Friday's close
    "2026-11-03": (0.8680, "2026-11-02"),
    "2026-11-04": (0.8700, "2026-11-03"),   # FROZEN_NOW's Berlin day
}


def fx_daily_rows(scale: float = 1.0) -> list[dict]:
    return [{"base": "USD", "account": ACCOUNT_CODE, "day": date.fromisoformat(day),
             "rate": rate * scale, "bar_date": date.fromisoformat(bar),
             "snapped_at": FROZEN_NOW, "source": "backfill"}
            for day, (rate, bar) in FX_DAILY_ROWS.items()]


def seed_fx_daily(scale: float = 1.0) -> None:
    """Replace fx_daily_rates with FX_DAILY_ROWS x scale and load the process memo.

    Loading it here models production's steady state (one table read per minute,
    not per request), so V205-5's statement budgets stay as they are."""
    import sqlalchemy as sa

    from swingbot.core.db import engine, schema
    from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
    from swingbot.core.marketdata import fx_daily
    with engine.get_engine().begin() as conn:
        conn.execute(sa.delete(schema.fx_daily_rates))
        fx_daily_rate_repo().insert_if_absent(fx_daily_rows(scale), conn=conn)
    fx_daily.reset_memo()
    fx_daily.lookup("USD", ACCOUNT_CODE, FROZEN_NOW.date())
```

In `<wt>/tests/admin_perf/conftest.py`, in `golden_seed`, add `fx_daily` to `from swingbot.core.marketdata import data, data_refresh, data_store, fx`, call `gb.seed_fx_daily(scale)` in `set_fx` right after `monkeypatch.setattr(fx, "_frames", {})`, and add `fx_daily.reset_memo()` after the final `risk._invalidate_cache()` (teardown), so no later test sees the golden book's rates. The per-test truncation in `tests/conftest.py` empties the table itself (it truncates every `METADATA` table).

- [ ] **Step 7: Update `money_reference.py` by hand**

In `<wt>/tests/admin_perf/money_reference.py`, replace the docstring's rule sentence ("Today's rule ... (frozen: 2026-11-04).") with:

```text
V205-15's rule: the rate for day D is the fx_daily_rates row for D
(golden_book.FX_DAILY_ROWS: the last positive USDEUR=X close dated strictly
before D), D being the UTC date of the amount's stamp (fx_convert._day; V205-16
moves it to the Berlin date); an open position converts at the frozen
date.today() (2026-11-04).
```

Replace the constants with:

```python
T1_SAP_WIN = 120.00       # EUR quote: no conversion
T2_AAPL_WIN = 43.40       # 50.00 x 0.8680 (row 2026-11-03: close 2026-11-02; exit 2026-11-03 20:30 UTC)
T3_AAPL_LOSS = -25.92     # -30.00 x 0.8640 (row 2026-11-02: close 2026-10-30; exit 2026-11-02 23:30 UTC)
T4_LEG1 = 43.10           # 50.00 x 0.8620 (row 2026-10-29: close 2026-10-27, the 10-28 close is 0.0)
T4_LEG2 = 17.28           # 20.00 x 0.8640 (row 2026-11-02: close 2026-10-30)
T4_TOTAL = 60.38          # round(43.10 + 17.28, 2)
T5_OPEN_AAPL = 34.80      # 40.00 x 0.8700 (row 2026-11-04, the frozen date.today())
T6_OPEN_SAP = 60.00       # EUR quote: no conversion
DAY_2026_11_02 = -8.64    # T3 + T4 leg 2 = -25.92 + 17.28 (the Calendar buckets closed_at[:10])
DAY_2026_11_03 = 163.40   # T1 + T2 = 120.00 + 43.40
MONTH_2026_11 = 154.76    # -8.64 + 163.40
```

Any other `EXPECTED_MONEY` value V205-4b wrote as a **literal** (a risk heat weight, a notional) is re-derived the same way: take the rate its comment names, replace it with the "Rate after" column of the table above for the same day, recompute by hand, and rewrite the comment with the new arithmetic. A value written as an expression over the constants needs no edit. Never compute a value through `fx`, `fx_convert` or `fx_daily`.

- [ ] **Step 8: Run the goldens and budgets**

This hits the database: run `/replicate-prod-db` first if this worktree has not yet.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`
Expected: `0 failed`, `0 xfailed`. `test_endpoint_matches_its_frozen_golden[*]` passes **unchanged** (the money pointers are masked). `test_money_fields_match_the_hand_computed_reference[*]` passes with the new values. `test_money_pointers_are_exactly_the_fx_sensitive_fields[*]` passes, because `set_fx(2.0)` doubles the table rows too. A failing golden means the code is wrong: fix `fx.py`, never a golden. A failing money value means the hand arithmetic or the table seed is wrong.

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf` -- expected `0 failed` (the budgets in `test_budgets.py` unchanged).

Run: `python <wt>/scripts/dev/testrun.py suite market-data` -- expected `0 failed`, `0 xfailed`, and a count at or under 1200 (`python <wt>/scripts/dev/testrun.py file tests/dev/test_suites.py` -- expected `0 failed`).

Run: `python <wt>/scripts/dev/testrun.py file tests/admin/test_api_v1_money.py` and `... file tests/admin/test_risk_read_model.py` -- expected `0 failed` (both replace `fx.fx_rate` itself, so they never reach the table).

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx.py` -- `fx_rate` and `_day_rate` `A`/`B`; `python <wt>/scripts/dev/complexity_gate.py` clean.

- [ ] **Step 9: Commit (two scoped commits)**

```bash
git -C <wt> add swingbot/core/marketdata/fx.py tests/marketdata/test_fx.py tests/marketdata/test_fx_persisted.py
git -C <wt> commit -m "feat(marketdata): fx_rate reads the day's stored rate, strictly before the day (v205 V205-15)"
git -C <wt> add tests/admin_perf/golden_book.py tests/admin_perf/conftest.py tests/admin_perf/money_reference.py
git -C <wt> commit -m "test(admin): golden book seeds fx_daily_rates; money references re-derived by hand (v205 V205-15)"
```

