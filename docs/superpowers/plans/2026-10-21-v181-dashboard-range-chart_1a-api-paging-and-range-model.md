# v181 — Dashboard range chart: Part 1a — API paging and the range model

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V181-3:" -A 400 <this file>`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Tasks V181-1..V181-4: `before` / `has_more` on `/equity/candles`, the pure range model (`equity-range.model.ts`), history paging in `EquityCandlesStore`, and the profit/loss tone helpers. Spec sections covered: § 2 (older history on pan), § 3 (the `nextTimeframe` rule and its invariant), § 4 (in-window candles and range stats), § 5 (the colour rules as pure functions), § 6 (`GET /equity/candles`), § 7 (where the logic lives).

**Frontend narrow run.** The index's Global Constraints name `npx vitest run <spec>`; this repo's runner is the Angular unit-test builder (`frontend/vitest.config.ts` is only its `runnerConfig`), so the narrow run used below is `cd frontend && npx ng test --include <spec> --watch=false`. A "Timeout waiting for worker to respond" after 60 s is load, not a failure: re-run (the config header explains).

# Phase 1 — Backend cursor and the pure model

### Task V181-1: `/equity/candles` `before` cursor and `has_more`

**Model:** sonnet — two-file backend change with a DST-sensitive inverse parser and paging tests; contained, but the aware-instant comparison needs care.

**Files:**
- Modify: `swingbot/core/tracking/equity_candles.py` (imports at the top; new `parse_bucket_label` after `bucket_label`, currently lines 59-63)
- Modify: `swingbot/admin/api_v1/equity.py` (module docstring; new `_before` / `_page` after `_limit`; `equity_candles_view`, lines 66-81)
- Test: `tests/tracking/test_equity_candles.py`
- Test: `tests/admin/test_api_v1_equity.py`

**Interfaces:**
- Consumes: `bucket_start(at, tf)`, `bucket_label(start, tf)`, `TIMEFRAMES`, `_INTRADAY`, `_FLOORS` (all in `equity_candles.py`); `US_MARKET_TZ = ZoneInfo("America/New_York")` (`swingbot/core/market/session.py:12`); `ApiError`, `_INTRADAY`, `_limit()` in `equity.py`.
- Produces:
  - `equity_candles.parse_bucket_label(label: str, tf: str) -> datetime` — the aware New York bucket start a candle's `t` names; `ValueError` for an unknown `tf` or any shape `bucket_label` would not emit for that `tf`.
  - `equity.py` `_before(tf: str) -> datetime | None` — `None` when the query has no `before`; `ApiError("invalid", "before must be …", 400)` on a bad shape.
  - `equity.py` `_page(candles: list[dict], tf: str, before: datetime | None, limit: int) -> tuple[list[dict], bool]` — the slice and `has_more`.
  - Response key `has_more: bool`; query `?before=<t>` (exclusive). Consumed by V181-3 (`ApiClient.equityCandles(…, before)`, `EquityCandlesResponse.has_more`).

- [ ] **Step 1: Create the worktree and sync the database**

```bash
cd /e/Documents/Private/Projects/Discord-Bot
git worktree add -b 2026-10-21-v181-dashboard-range-chart .claude/worktrees/2026-10-21-v181-dashboard-range-chart main
cd .claude/worktrees/2026-10-21-v181-dashboard-range-chart
```

Then run `/replicate-prod-db` (CLAUDE.md: a task that runs tests against the database syncs the local replica first). Every later path in this plan is relative to the worktree root.

- [ ] **Step 2: Write the failing unit tests for `parse_bucket_label`**

In `tests/tracking/test_equity_candles.py`, extend the import block:

```python
from swingbot.core.tracking.equity_candles import (
    TIMEFRAMES, add_change, bucket_label, bucket_start, mtm_candles, parse_bucket_label,
    realized_candles)
```

and append after `test_the_repeated_hour_on_fall_back_day_is_two_1h_buckets`:

```python
# --- parse_bucket_label (v181: the /equity/candles paging cursor) -------------

ROUND_TRIP_INSTANTS = [
    _utc(2026, 10, 16, 14, 35),            # ordinary EDT session hour
    _utc(2026, 3, 8, 6, 30),               # 01:30 EST, the hour before spring forward
    _utc(2026, 3, 8, 7, 30),               # 03:30 EDT, the hour after the skipped one
    _utc(2026, 11, 1, 5, 30),              # 01:30 EDT, first pass of the repeated hour
    _utc(2026, 11, 1, 6, 30),              # 01:30 EST, second pass of the repeated hour
    _utc(2027, 1, 1, 4, 59),               # 23:59 New York on 31 Dec
]


@pytest.mark.parametrize("tf", TIMEFRAMES)
@pytest.mark.parametrize("at", ROUND_TRIP_INSTANTS)
def test_a_bucket_label_parses_back_to_its_bucket_start(at, tf):
    start = bucket_start(at, tf)
    label = bucket_label(start, tf)
    parsed = parse_bucket_label(label, tf)
    assert parsed.tzinfo is not None
    assert parsed.timestamp() == start.timestamp()     # instants, so `fold` counts
    assert bucket_label(parsed, tf) == label


def test_the_two_repeated_fall_back_hours_parse_to_different_instants():
    first = parse_bucket_label("2026-11-01T01:00:00-04:00", "1H")
    second = parse_bucket_label("2026-11-01T01:00:00-05:00", "1H")
    assert second.timestamp() - first.timestamp() == 3600


def test_a_daily_label_is_the_new_york_midnight_instant():
    parsed = parse_bucket_label("2026-10-16", "1D")
    assert parsed.astimezone(UTC) == _utc(2026, 10, 16, 4)   # 00:00 EDT


@pytest.mark.parametrize("label, tf", [
    ("2026-10-16", "1H"),                          # a date where a datetime is emitted
    ("2026-10-16T10:00:00-04:00", "1D"),           # a datetime where a date is emitted
    ("2026-10-16T10:00:00", "1H"),                 # naive
    ("2026-10-16T10:00:00Z", "4H"),                # Z is not the emitted offset form
    ("2026-10-16T10:00-04:00", "1H"),              # no seconds
    ("20261016", "1D"),                            # compact date
    ("2026-13-01", "1W"),                          # not a date
    ("", "1D"),
    ("abc", "1H"),
])
def test_any_other_label_shape_is_refused(label, tf):
    with pytest.raises(ValueError):
        parse_bucket_label(label, tf)


def test_parse_refuses_an_unknown_timeframe():
    with pytest.raises(ValueError):
        parse_bucket_label("2026-10-16", "15m")
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_equity_candles.py`
Expected: collection error — `ImportError: cannot import name 'parse_bucket_label'`.

- [ ] **Step 4: Implement `parse_bucket_label`**

In `swingbot/core/tracking/equity_candles.py`, change the imports:

```python
import re
from datetime import date, datetime, timedelta
```

and add directly after `bucket_label`:

```python
_DATE_LABEL = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME_LABEL = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")


def parse_bucket_label(label: str, tf: str) -> datetime:
    """The inverse of `bucket_label` (v181 § 6): the aware New York bucket
    start a candle's `t` names. Accepts exactly the shape `bucket_label`
    emits for `tf` -- an ISO date for 1D/1W, read as that New York day's
    midnight; an ISO datetime with offset for 1H/4H, whose offset keeps the
    two fall-back 01:00 hours apart. Anything else is a ValueError."""
    if tf not in _FLOORS:
        raise ValueError(f"tf {tf!r} is not one of {TIMEFRAMES}")
    if tf in _INTRADAY:
        if not _TIME_LABEL.fullmatch(label):
            raise ValueError(f"{label!r} is not a {tf} candle time")
        return datetime.fromisoformat(label).astimezone(US_MARKET_TZ)
    if not _DATE_LABEL.fullmatch(label):
        raise ValueError(f"{label!r} is not a {tf} candle date")
    day = date.fromisoformat(label)
    return datetime(day.year, day.month, day.day, tzinfo=US_MARKET_TZ)
```

`astimezone(US_MARKET_TZ)` from a fixed offset sets `fold` correctly, which is why `bucket_label(parsed, tf)` reproduces the `-05:00` form of the second fall-back hour. `date.fromisoformat` raises `ValueError` on `2026-13-01`, so an impossible date is refused too.

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_equity_candles.py`
Expected: all pass, `0 failed`.

- [ ] **Step 6: Write the failing endpoint tests**

In `tests/admin/test_api_v1_equity.py`, add `"has_more": bool` to the `BODY` contract:

```python
BODY = {"tf": str, "basis": str, "currency_symbol": str, "candles": list, "has_more": bool,
        "recording_since": NULLABLE_STR, "as_of": str}
```

Add two helpers after `_closed`:

```python
def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _page_all(client, **query):
    """Every candle, fetched one page of one candle at a time through the
    `before` cursor, oldest first."""
    candles, before = [], None
    while True:
        params = {**query, "limit": 1, **({"before": before} if before else {})}
        body = client.get(URL, query_string=params).get_json()
        candles = body["candles"] + candles
        if not body["has_more"]:
            return candles
        before = body["candles"][0]["t"]
```

Append the tests at the end of the file:

```python
# --- v181: the `before` cursor and `has_more` ------------------------------------

def test_has_more_is_false_when_every_candle_fits(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL).get_json()
    assert (len(body["candles"]), body["has_more"]) == (2, False)


def test_has_more_is_true_when_the_limit_cut_older_candles(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?limit=1").get_json()
    assert ([c["t"] for c in body["candles"]], body["has_more"]) == (["2026-10-15"], True)


def test_before_is_exclusive_of_the_cursor_bucket(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-15").get_json()
    assert [c["t"] for c in body["candles"]] == ["2026-10-13", "2026-10-14"]
    assert body["has_more"] is False


def test_before_with_a_limit_keeps_the_newest_older_candles(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-15&limit=1").get_json()
    assert ([c["t"] for c in body["candles"]], body["has_more"]) == (["2026-10-14"], True)


def test_a_page_keeps_the_change_measured_on_the_full_series(logged_in, account):
    _backfilled_tuesday()
    _two_live_days()
    (only,) = logged_in.get(URL + "?before=2026-10-15&limit=1").get_json()["candles"]
    full_middle = logged_in.get(URL).get_json()["candles"][1]
    assert only == full_middle                     # change vs Tuesday's close, not its own open


def test_before_the_oldest_candle_is_an_empty_page(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-10-14").get_json()
    assert (body["candles"], body["has_more"]) == ([], False)


def test_before_past_the_newest_candle_returns_the_latest(logged_in, account):
    _two_live_days()
    body = logged_in.get(URL + "?before=2026-12-01").get_json()
    assert [c["t"] for c in body["candles"]] == ["2026-10-14", "2026-10-15"]


@pytest.mark.parametrize("tf", ["1H", "4H", "1D", "1W"])
def test_the_cursor_round_trips_for_every_timeframe(logged_in, account, tf):
    _two_live_days()
    full = logged_in.get(URL, query_string={"tf": tf}).get_json()["candles"]
    assert full                                              # the fixture yields candles on every tf
    assert _page_all(logged_in, tf=tf) == full


def test_paging_works_on_the_realized_basis_and_carries_the_prior_close(logged_in, account):
    seed_store("trades", [_closed("t1", 50.0, "2026-10-13T15:00:00+00:00"),
                          _closed("t2", -20.0, "2026-10-14T15:00:00+00:00"),
                          _closed("t3", 30.0, "2026-10-15T15:00:00+00:00")])
    newest = logged_in.get(URL + "?basis=realized&limit=1").get_json()
    assert newest["has_more"] is True
    (latest,) = newest["candles"]
    older = logged_in.get(URL, query_string={"basis": "realized", "limit": 1,
                                             "before": latest["t"]}).get_json()
    (previous,) = older["candles"]
    assert (previous["t"], latest["t"]) == ("2026-10-14", "2026-10-15")
    assert latest["o"] == previous["c"]                      # the first o is the true prior balance
    assert _page_all(logged_in, basis="realized") == logged_in.get(
        URL + "?basis=realized").get_json()["candles"]


def _fall_back_night():
    """Sun 1 Nov 2026: 00:30 EDT, 01:30 EDT, 01:30 EST (repeated hour), 02:30 EST."""
    EquitySampleRepository().upsert_many([
        _row(_utc(2026, 11, 1, 4, 30), 10000), _row(_utc(2026, 11, 1, 5, 30), 10010),
        _row(_utc(2026, 11, 1, 6, 30), 10020), _row(_utc(2026, 11, 1, 7, 30), 10030),
    ])


def _spring_forward_night():
    """Sun 8 Mar 2026: 00:30 EST, 01:30 EST, 03:30 EDT (02:00-03:00 skipped), 04:30 EDT."""
    EquitySampleRepository().upsert_many([
        _row(_utc(2026, 3, 8, 5, 30), 10000), _row(_utc(2026, 3, 8, 6, 30), 10010),
        _row(_utc(2026, 3, 8, 7, 30), 10020), _row(_utc(2026, 3, 8, 8, 30), 10030),
    ])


@pytest.mark.parametrize("night", [_fall_back_night, _spring_forward_night])
@pytest.mark.parametrize("tf", ["1H", "4H"])
def test_paging_across_a_dst_change_loses_and_duplicates_no_candle(logged_in, account, night, tf):
    night()
    full = logged_in.get(URL, query_string={"tf": tf}).get_json()["candles"]
    paged = _page_all(logged_in, tf=tf)
    assert paged == full
    assert len({c["t"] for c in paged}) == len(paged)


def test_the_fall_back_night_has_two_distinct_01_00_candles(logged_in, account):
    _fall_back_night()
    times = [c["t"] for c in logged_in.get(URL + "?tf=1H").get_json()["candles"]]
    assert "2026-11-01T01:00:00-04:00" in times
    assert "2026-11-01T01:00:00-05:00" in times


@pytest.mark.parametrize("query", [
    {"tf": "1D", "before": "2026-10-15T00:00:00-04:00"},   # datetime on a date timeframe
    {"tf": "1W", "before": "2026-10-12T00:00:00-04:00"},
    {"tf": "1H", "before": "2026-10-15"},                  # date on an intraday timeframe
    {"tf": "4H", "before": "2026-10-15"},
    {"tf": "1H", "before": "2026-10-15T10:00:00"},         # naive
    {"tf": "1D", "before": "abc"},
    {"tf": "1D", "before": ""},
])
def test_any_other_before_shape_is_a_400(logged_in, account, query):
    response = logged_in.get(URL, query_string=query)
    assert_error(response, "invalid", 400)
    assert response.get_json()["error"]["message"].startswith("before must be")
```

The `_backfilled_tuesday` + `_two_live_days` fixture gives three daily candles (13, 14, 15 Oct), so the change test proves a page's `change` is still measured against the true previous close.

- [ ] **Step 7: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_equity.py`
Expected: FAIL — `has_more` missing from the body (`assert_shape`), `before` ignored (the exclusivity tests return every day), the 400 tests get 200.

- [ ] **Step 8: Implement `_before`, `_page` and the response key**

In `swingbot/admin/api_v1/equity.py`, append one paragraph to the module docstring (after the "no ISO code exists in config" paragraph):

```text
v181 § 6: `before=<t>` pages older history. It accepts exactly the `t` the
endpoint emits for that `tf` (`equity_candles.parse_bucket_label`) and keeps
candles whose bucket starts strictly before it, compared as instants. The
full series is built and `change`d first, then filtered and sliced, so a
page's `o`/`change` are the full-history values; `has_more` says whether
the slice cut older candles. Paging at the database is out of scope.
```

Add after `_limit`:

```python
def _before(tf: str) -> datetime | None:
    raw = request.args.get("before")
    if raw is None:
        return None
    try:
        return equity_candles.parse_bucket_label(raw, tf)
    except ValueError:
        form = "an ISO datetime with offset" if tf in _INTRADAY else "an ISO date"
        raise ApiError("invalid", f"before must be {form}, the t of a {tf} candle",
                       400) from None


def _page(candles: list[dict], tf: str, before: datetime | None,
          limit: int) -> tuple[list[dict], bool]:
    """The newest `limit` candles older than `before` (all when None), and
    whether older ones remain. Instants, not wall clock: same-zone aware
    datetimes ignore `fold`, which would merge the two fall-back hours."""
    if before is not None:
        cutoff = before.timestamp()
        candles = [c for c in candles
                   if equity_candles.parse_bucket_label(c["t"], tf).timestamp() < cutoff]
    return candles[-limit:], len(candles) > limit
```

Replace `equity_candles_view`:

```python
@api_v1.route("/equity/candles", methods=["GET"])
@require_auth
def equity_candles_view():
    tf = _choice("tf", equity_candles.TIMEFRAMES, "1D")
    basis = _choice("basis", BASES, "mtm")
    limit = _limit()
    before = _before(tf)
    candles = _mtm(tf) if basis == "mtm" else _realized(tf)
    page, has_more = _page(candles, tf, before, limit)
    return jsonify({
        "tf": tf,
        "basis": basis,
        "currency_symbol": config.CURRENCY_SYMBOL,
        "candles": page,
        "has_more": has_more,
        "recording_since": iso(equity_samples_repo().earliest_at("live")),
        "as_of": iso(datetime.now(timezone.utc)),
    })
```

`_before` runs before the series is built, so a bad cursor costs no database read.

- [ ] **Step 9: Run both test files to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_equity.py`
Expected: all pass, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/tracking/test_equity_candles.py`
Expected: all pass, `0 failed`.

- [ ] **Step 10: Check complexity**

Run: `python -m radon cc -s swingbot/admin/api_v1/equity.py swingbot/core/tracking/equity_candles.py | cat`
Expected: `parse_bucket_label`, `_before`, `_page` and `equity_candles_view` all rank A; nothing at or above 15.

- [ ] **Step 11: Commit (two scoped commits)**

```bash
git add swingbot/core/tracking/equity_candles.py tests/tracking/test_equity_candles.py
git commit -m "feat(v181): parse_bucket_label, the inverse of bucket_label for the paging cursor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add swingbot/admin/api_v1/equity.py tests/admin/test_api_v1_equity.py
git commit -m "feat(v181): /equity/candles pages older history with before= and reports has_more" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-2: Pure range model: in-window candles, bounds, stats, next timeframe

**Model:** sonnet — new pure module with DST-aware New York time arithmetic and exhaustive unit tests; no wiring, but the bucket-edge maths must be exact.

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts`

**Interfaces:**
- Consumes: `EquityCandle`, `EquityTimeframe` (`frontend/src/app/api/models.ts`); `isIntraday(tf)` (`equity-candles.model.ts`); `EQUITY_TIMEFRAMES = ['1H', '4H', '1D', '1W']` (`frontend/src/app/ui/equity-chart-prefs.ts:17`, ordered finest to coarsest).
- Produces (all exported from `equity-range.model.ts`; V181-3, V181-4 and V181-12 append to this same file):
  - `interface LogicalWindow { from: number; to: number }` — a lightweight-charts logical range (bar `i` is centred on `i`).
  - `interface TimeWindow { from: string; to: string }` — ISO UTC instants (`Date.toISOString()` form), half-open `[from, to)`.
  - `interface RangeStats { change: number; changePct: number | null; high: number; low: number; maxDrawdownPct: number | null }` — **`maxDrawdownPct` is a non-negative magnitude** (3.2 means a 3.2 % fall from the running peak); the readout (V181-7) prints it with a minus sign.
  - `inWindowCandles(range: LogicalWindow | null, candles: readonly EquityCandle[]): EquityCandle[]` — `[]` for a null range.
  - `nyMidnight(isoDate: string): Date`
  - `bucketStartInstant(t: string, tf: EquityTimeframe): Date`
  - `bucketEndInstant(t: string, tf: EquityTimeframe): Date` — the next bucket's start on the New York wall clock.
  - `windowBounds(candles: readonly EquityCandle[], tf: EquityTimeframe): TimeWindow | null`
  - `rangeStats(candles: readonly EquityCandle[]): RangeStats | null`
  - `TF_STEP_UP_BARS = 250`, `TF_STEP_DOWN_BARS = 15`, `TF_RATIO: Record<EquityTimeframe, number>` (`{ '1H': 1, '4H': 4, '1D': 6, '1W': 7 }` — how many buckets of the next finer timeframe one bucket holds at most).
  - `nextTimeframe(barCount: number, tf: EquityTimeframe, atHistoryEdge: boolean): EquityTimeframe`

**Design notes (spec § 3, § 4, § 6):**
- A candle `i` occupies logical `[i − 0.5, i + 0.5]`. It is in-window when that span overlaps the visible range, so a partly visible edge candle counts whole. The first index is `floor(from + 0.5)`, the last is `ceil(to − 0.5)`, both clamped to the loaded candles.
- New York wall time becomes an instant in two passes (offset at a first guess, then at the candidate); midnight and the 4H edges are never skipped or repeated hours. 1H buckets are one real hour each, including the two fall-back 01:00 hours, so a 1H end is `start + 1 h`. 4H/1D/1W ends are wall-clock edges, so the 4H bucket is 3 or 5 real hours on DST days, exactly as `equity_candles.py` buckets it.
- `nextTimeframe` never steps down at the history edge or with 0 bars in view; keeping the centre time across a step is the component's job (V181-8), not this function's.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import {
  TF_RATIO,
  TF_STEP_DOWN_BARS,
  TF_STEP_UP_BARS,
  bucketEndInstant,
  bucketStartInstant,
  inWindowCandles,
  nextTimeframe,
  nyMidnight,
  rangeStats,
  windowBounds,
} from './equity-range.model';

function candle(overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
           change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false, ...overrides };
}

/** Ten daily candles, 1 to 10 Oct 2026, so index i has t 2026-10-(i+1). */
const TEN = Array.from({ length: 10 }, (_, i) =>
  candle({ t: `2026-10-${String(i + 1).padStart(2, '0')}` }));

const iso = (d: Date): string => d.toISOString();

describe('inWindowCandles', () => {
  it('counts a partly visible edge candle whole', () => {
    expect(inWindowCandles({ from: 2.3, to: 5.4 }, TEN).map((c) => c.t))
      .toEqual(['2026-10-03', '2026-10-04', '2026-10-05', '2026-10-06']);
  });

  it('leaves out a candle whose span ends before the range starts', () => {
    expect(inWindowCandles({ from: 2.6, to: 5.6 }, TEN).map((c) => c.t))
      .toEqual(['2026-10-04', '2026-10-05', '2026-10-06', '2026-10-07']);
  });

  it('clamps a range that runs past either end to the loaded candles', () => {
    expect(inWindowCandles({ from: -3, to: 20 }, TEN)).toHaveLength(10);
  });

  it('is empty for a null range, a range past the data, or no candles', () => {
    expect(inWindowCandles(null, TEN)).toEqual([]);
    expect(inWindowCandles({ from: 12, to: 15 }, TEN)).toEqual([]);
    expect(inWindowCandles({ from: 0, to: 5 }, [])).toEqual([]);
  });
});

describe('nyMidnight', () => {
  it('is 04:00Z in summer and 05:00Z in winter', () => {
    expect(iso(nyMidnight('2026-10-16'))).toBe('2026-10-16T04:00:00.000Z');
    expect(iso(nyMidnight('2026-01-01'))).toBe('2026-01-01T05:00:00.000Z');
  });

  it('reads the offset of the night itself on both changeover days', () => {
    expect(iso(nyMidnight('2026-03-08'))).toBe('2026-03-08T05:00:00.000Z');   // still EST
    expect(iso(nyMidnight('2026-03-09'))).toBe('2026-03-09T04:00:00.000Z');   // now EDT
    expect(iso(nyMidnight('2026-11-01'))).toBe('2026-11-01T04:00:00.000Z');   // still EDT
    expect(iso(nyMidnight('2026-11-02'))).toBe('2026-11-02T05:00:00.000Z');   // now EST
  });
});

describe('bucket instants', () => {
  it('reads an intraday start from its offset and a daily start as New York midnight', () => {
    expect(iso(bucketStartInstant('2026-10-16T08:00:00-04:00', '4H'))).toBe('2026-10-16T12:00:00.000Z');
    expect(iso(bucketStartInstant('2026-10-16', '1D'))).toBe('2026-10-16T04:00:00.000Z');
  });

  it('ends a 1H bucket one real hour later, the repeated fall-back hour included', () => {
    expect(iso(bucketEndInstant('2026-11-01T01:00:00-04:00', '1H'))).toBe('2026-11-01T06:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01T01:00:00-05:00', '1H'))).toBe('2026-11-01T07:00:00.000Z');
    expect(iso(bucketEndInstant('2026-03-08T01:00:00-05:00', '1H'))).toBe('2026-03-08T07:00:00.000Z');
  });

  it('ends a 4H bucket on the wall clock: 3 real hours at spring forward, 5 at fall back', () => {
    expect(iso(bucketEndInstant('2026-03-08T00:00:00-05:00', '4H'))).toBe('2026-03-08T08:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01T00:00:00-04:00', '4H'))).toBe('2026-11-01T09:00:00.000Z');
  });

  it('ends the 20:00 4H bucket at the next New York midnight', () => {
    expect(iso(bucketEndInstant('2026-10-16T20:00:00-04:00', '4H'))).toBe('2026-10-17T04:00:00.000Z');
  });

  it('ends a day at the next New York midnight and a week seven days on', () => {
    expect(iso(bucketEndInstant('2026-10-16', '1D'))).toBe('2026-10-17T04:00:00.000Z');
    expect(iso(bucketEndInstant('2026-10-31', '1D'))).toBe('2026-11-01T04:00:00.000Z');
    expect(iso(bucketEndInstant('2026-11-01', '1D'))).toBe('2026-11-02T05:00:00.000Z');
    expect(iso(bucketEndInstant('2026-10-26', '1W'))).toBe('2026-11-02T05:00:00.000Z');
    expect(iso(bucketEndInstant('2026-12-28', '1W'))).toBe('2027-01-04T05:00:00.000Z');
  });
});

describe('windowBounds', () => {
  it('runs from the first bucket start to the last bucket end', () => {
    const days = [candle({ t: '2026-10-14' }), candle({ t: '2026-10-15' })];
    expect(windowBounds(days, '1D'))
      .toEqual({ from: '2026-10-14T04:00:00.000Z', to: '2026-10-16T04:00:00.000Z' });
  });

  it('sits on bucket edges for intraday candles', () => {
    const hours = [candle({ t: '2026-10-16T10:00:00-04:00' }), candle({ t: '2026-10-16T15:00:00-04:00' })];
    expect(windowBounds(hours, '1H'))
      .toEqual({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T20:00:00.000Z' });
  });

  it('agrees with inWindowCandles: a partly visible edge candle widens the bounds by its whole bucket', () => {
    const visible = inWindowCandles({ from: 2.3, to: 5.4 }, TEN);
    expect(windowBounds(visible, '1D'))
      .toEqual({ from: '2026-10-03T04:00:00.000Z', to: '2026-10-07T04:00:00.000Z' });
  });

  it('is null with no candles', () => {
    expect(windowBounds([], '1D')).toBeNull();
  });
});

describe('rangeStats', () => {
  const window = [
    candle({ t: '2026-10-14', o: 100, h: 110, l: 95, c: 105 }),
    candle({ t: '2026-10-15', o: 105, h: 108, l: 90, c: 92 }),
    candle({ t: '2026-10-16', o: 92, h: 120, l: 91, c: 118 }),
  ];

  it('measures the change from the first open to the last close', () => {
    const stats = rangeStats(window)!;
    expect(stats.change).toBeCloseTo(18, 9);
    expect(stats.changePct).toBeCloseTo(18, 9);
  });

  it('takes high and low from every in-window candle', () => {
    const stats = rangeStats(window)!;
    expect([stats.high, stats.low]).toEqual([120, 90]);
  });

  it('measures drawdown on closes against the running peak, as a positive magnitude', () => {
    expect(rangeStats(window)!.maxDrawdownPct).toBeCloseTo((13 / 105) * 100, 9);
  });

  it('ignores an intra-candle low: drawdown is within range on closes only', () => {
    const one = [candle({ o: 100, h: 101, l: 50, c: 100 })];
    expect(rangeStats(one)!.maxDrawdownPct).toBe(0);
    expect(rangeStats(one)!.low).toBe(50);
  });

  it('gives a flat window zero change and zero drawdown', () => {
    const flat = [candle({ o: 100, h: 100, l: 100, c: 100 }), candle({ o: 100, h: 100, l: 100, c: 100 })];
    expect(rangeStats(flat)).toEqual({ change: 0, changePct: 0, high: 100, low: 100, maxDrawdownPct: 0 });
  });

  it('gives a null drawdown when the running peak is not above zero', () => {
    const underwater = [candle({ o: -10, h: -2, l: -12, c: -5 }), candle({ o: -5, h: -1, l: -6, c: -3 })];
    expect(rangeStats(underwater)!.maxDrawdownPct).toBeNull();
  });

  it('gives a null change % on a zero opening equity', () => {
    expect(rangeStats([candle({ o: 0, h: 5, l: 0, c: 5 })])!.changePct).toBeNull();
  });

  it('is null with no candles', () => {
    expect(rangeStats([])).toBeNull();
  });
});

describe('nextTimeframe', () => {
  const pairs: [EquityTimeframe, EquityTimeframe][] = EQUITY_TIMEFRAMES.slice(0, -1)
    .map((finer, i) => [finer, EQUITY_TIMEFRAMES[i + 1]]);

  it('keeps 250 / ratio above 15 for every adjacent pair, so a step never bounces', () => {
    for (const [finer, coarser] of pairs) {
      const ratio = TF_RATIO[coarser];
      expect(TF_STEP_UP_BARS / ratio).toBeGreaterThan(TF_STEP_DOWN_BARS);
      // a step up at 251 bars lands near 251 / ratio bars and stays there
      expect(nextTimeframe(Math.floor((TF_STEP_UP_BARS + 1) / ratio), coarser, false)).toBe(coarser);
      // a step down at 14 bars lands near 14 x ratio bars and stays there
      expect(nextTimeframe((TF_STEP_DOWN_BARS - 1) * ratio, finer, false)).toBe(finer);
    }
  });

  it('steps up one timeframe above 250 bars and holds at 250', () => {
    expect(nextTimeframe(251, '1H', false)).toBe('4H');
    expect(nextTimeframe(251, '4H', false)).toBe('1D');
    expect(nextTimeframe(251, '1D', false)).toBe('1W');
    expect(nextTimeframe(250, '1H', false)).toBe('1H');
  });

  it('steps down one timeframe below 15 bars and holds at 15', () => {
    expect(nextTimeframe(14, '1W', false)).toBe('1D');
    expect(nextTimeframe(14, '1D', false)).toBe('4H');
    expect(nextTimeframe(14, '4H', false)).toBe('1H');
    expect(nextTimeframe(15, '1D', false)).toBe('1D');
  });

  it('stays put at the ends of the timeframe ladder', () => {
    expect(nextTimeframe(400, '1W', false)).toBe('1W');
    expect(nextTimeframe(3, '1H', false)).toBe('1H');
  });

  it('never steps down at the edge of history or with no bars in view', () => {
    expect(nextTimeframe(5, '1D', true)).toBe('1D');
    expect(nextTimeframe(0, '1D', false)).toBe('1D');
  });

  it('still steps up at the edge of history', () => {
    expect(nextTimeframe(300, '1H', true)).toBe('4H');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --watch=false`
Expected: FAIL — `Failed to resolve import "./equity-range.model"`.

- [ ] **Step 3: Implement the model**

Create `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts`:

```ts
import { EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import { isIntraday } from './equity-candles.model';

/**
 * Pure helpers for the range-aware equity chart — spec v181 § 7. The chart
 * component, `EquityCandlesStore` and `DashboardStore` only wire chart events
 * and responses to these, so every rule is testable without a canvas.
 *
 * **One clock.** Equity candles are bucketed on the New York wall clock
 * (`swingbot/core/tracking/equity_candles.py`), so every time window here is
 * a run of whole New York buckets.
 */

/** A lightweight-charts logical range: bar `i` is centred on `i`. */
export interface LogicalWindow {
  from: number;
  to: number;
}

/** ISO UTC instants (`Date.toISOString()`), half-open `[from, to)`. */
export interface TimeWindow {
  from: string;
  to: string;
}

/** The no-hover readout of the visible range (§ 4). `maxDrawdownPct` is a
 *  non-negative magnitude: 3.2 means closes fell 3.2 % below their running
 *  peak; null when that peak is not above zero. */
export interface RangeStats {
  change: number;
  changePct: number | null;
  high: number;
  low: number;
  maxDrawdownPct: number | null;
}

/* -- in-window candles ---------------------------------------------------- */

/** Every candle whose bucket overlaps the visible logical range. Candle `i`
 *  spans `[i - 0.5, i + 0.5]`, so a partly visible edge candle counts whole;
 *  the readout, the baseline and the KPI window all use these same buckets. */
export function inWindowCandles(
  range: LogicalWindow | null,
  candles: readonly EquityCandle[],
): EquityCandle[] {
  if (range === null || candles.length === 0) return [];
  const first = Math.max(0, Math.floor(range.from + 0.5));
  const last = Math.min(candles.length - 1, Math.ceil(range.to - 0.5));
  return first > last ? [] : candles.slice(first, last + 1);
}

/* -- New York bucket edges ----------------------------------------------- */

const HOUR_MS = 3_600_000;
const NY_PARTS = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', hourCycle: 'h23',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
});

/** New York's offset from UTC at `instantMs`, in ms (-4 h in summer). */
function nyOffsetMs(instantMs: number): number {
  const parts: Record<string, number> = {};
  for (const p of NY_PARTS.formatToParts(new Date(instantMs))) parts[p.type] = Number(p.value);
  const wallAsUtc = Date.UTC(parts['year'], parts['month'] - 1, parts['day'],
                             parts['hour'], parts['minute'], parts['second']);
  return wallAsUtc - Math.floor(instantMs / 1000) * 1000;
}

/** The instant of New York wall time `isoDate` `hour`:00 (`hour` may be 24).
 *  Two passes: the offset at a first guess, then at the candidate itself.
 *  Only called for 00/04/08/12/16/20, which are never skipped or repeated. */
function nyWallInstant(isoDate: string, hour: number): Date {
  const [y, m, d] = isoDate.split('-').map(Number);
  const wall = Date.UTC(y, m - 1, d, hour);
  const guess = wall - nyOffsetMs(wall + 5 * HOUR_MS);
  return new Date(wall - nyOffsetMs(guess));
}

function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** 00:00 New York on `isoDate` (`YYYY-MM-DD`), as an instant. */
export function nyMidnight(isoDate: string): Date {
  return nyWallInstant(isoDate, 0);
}

/** The instant a candle's bucket starts: its offset-carrying `t` for 1H/4H,
 *  New York midnight of its date for 1D/1W. */
export function bucketStartInstant(t: string, tf: EquityTimeframe): Date {
  return isIntraday(tf) ? new Date(Date.parse(t)) : nyMidnight(t.slice(0, 10));
}

const BUCKET_END: Record<EquityTimeframe, (t: string) => Date> = {
  // One real hour: the two fall-back 01:00 hours are two buckets.
  '1H': (t) => new Date(Date.parse(t) + HOUR_MS),
  // Wall clock: 3 real hours at spring forward, 5 at fall back.
  '4H': (t) => nyWallInstant(t.slice(0, 10), Number(t.slice(11, 13)) + 4),
  '1D': (t) => nyMidnight(addDays(t.slice(0, 10), 1)),
  '1W': (t) => nyMidnight(addDays(t.slice(0, 10), 7)),
};

/** The instant a candle's bucket ends: the next bucket's start. */
export function bucketEndInstant(t: string, tf: EquityTimeframe): Date {
  return BUCKET_END[tf](t);
}

/** `[first bucket start, last bucket end)` of in-order candles; null when
 *  there are none. */
export function windowBounds(
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
): TimeWindow | null {
  if (candles.length === 0) return null;
  return {
    from: bucketStartInstant(candles[0].t, tf).toISOString(),
    to: bucketEndInstant(candles[candles.length - 1].t, tf).toISOString(),
  };
}

/* -- range stats ---------------------------------------------------------- */

/** Peak-to-trough of closes as % of the running peak; null once the running
 *  peak is not above zero (a percentage of it would be meaningless). */
function maxDrawdownPct(candles: readonly EquityCandle[]): number | null {
  let peak = Number.NEGATIVE_INFINITY;
  let worst = 0;
  for (const { c } of candles) {
    peak = Math.max(peak, c);
    if (peak <= 0) return null;
    worst = Math.max(worst, ((peak - c) / peak) * 100);
  }
  return worst;
}

/** Equity change (first `o` to last `c`), high, low and max drawdown over
 *  the in-window candles; null when there are none. */
export function rangeStats(candles: readonly EquityCandle[]): RangeStats | null {
  if (candles.length === 0) return null;
  const first = candles[0];
  const change = candles[candles.length - 1].c - first.o;
  return {
    change,
    changePct: first.o === 0 ? null : (change / first.o) * 100,
    high: candles.reduce((max, c) => Math.max(max, c.h), Number.NEGATIVE_INFINITY),
    low: candles.reduce((min, c) => Math.min(min, c.l), Number.POSITIVE_INFINITY),
    maxDrawdownPct: maxDrawdownPct(candles),
  };
}

/* -- auto timeframe ------------------------------------------------------- */

export const TF_STEP_UP_BARS = 250;
export const TF_STEP_DOWN_BARS = 15;

/** How many buckets of the next finer timeframe one bucket holds at most:
 *  a 4H bucket holds 4 hours, a day 6 4H buckets, a week 7 sampled days.
 *  `TF_STEP_UP_BARS / ratio > TF_STEP_DOWN_BARS` for every adjacent pair is
 *  what stops a step from bouncing straight back (§ 3). */
export const TF_RATIO: Record<EquityTimeframe, number> = { '1H': 1, '4H': 4, '1D': 6, '1W': 7 };

/** The timeframe to show for `barCount` visible candles: one step coarser
 *  above 250, one finer below 15, else unchanged. Never steps down at the
 *  edge of history (`atHistoryEdge`, decided by the chart) or with no bars
 *  in view. */
export function nextTimeframe(
  barCount: number,
  tf: EquityTimeframe,
  atHistoryEdge: boolean,
): EquityTimeframe {
  const index = EQUITY_TIMEFRAMES.indexOf(tf);
  if (barCount > TF_STEP_UP_BARS) {
    return EQUITY_TIMEFRAMES[Math.min(index + 1, EQUITY_TIMEFRAMES.length - 1)];
  }
  if (barCount > 0 && barCount < TF_STEP_DOWN_BARS && !atHistoryEdge) {
    return EQUITY_TIMEFRAMES[Math.max(index - 1, 0)];
  }
  return tf;
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --watch=false`
Expected: PASS, every `describe` green. The DST cases depend on the ICU time-zone data Node ships (full ICU is the default since Node 13). If `nyMidnight('2026-03-08')` comes back at 04:00Z, the runtime has no zone data. That is an environment problem, not a model bug: check `node -p "Intl.DateTimeFormat('en-US',{timeZone:'America/New_York'}).format(0)"`.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc -p tsconfig.app.json --noEmit`
Expected: no errors (`noImplicitReturns` and `strict` are on; `BUCKET_END` is a total `Record`, so no switch fall-through).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts
git commit -m "feat(v181): equity-range model -- in-window candles, New York bucket bounds, range stats, auto timeframe rule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-3: History paging: client `before`, page merge, store pages

**Model:** sonnet — store state machine with in-flight, superseded and merge cases across five files; the paging rules are pure and pinned by tests.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`EquityCandlesResponse`, ~line 2164)
- Modify: `frontend/src/app/api/api-client.ts` (`equityCandles`, ~line 554)
- Modify: `frontend/src/app/api/api-client.spec.ts` (the `equityCandles` test, ~line 153)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts` (append)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts` (append)
- Modify: `frontend/src/app/stores/equity-candles.store.ts`
- Modify: `frontend/src/app/stores/equity-candles.store.spec.ts`
- Modify: `frontend/src/app/testing/equity-candles-store.stub.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (one field on the `CANDLES` literal, ~line 34)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` (one field in `response()`, ~line 19)
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts` (one field on the `CANDLES` literal, ~line 14)

The last three are type-only fixes: `has_more` becomes a required field of `EquityCandlesResponse`, so every typed literal of it gains `has_more: false`. Nothing else in those specs changes.

**Interfaces:**
- Consumes: V181-1's `has_more` response key and `?before=<t>`; V181-2's `LogicalWindow` (`equity-range.model.ts`).
- Produces:
  - `EquityCandlesResponse.has_more: boolean`
  - `ApiClient.equityCandles(tf: EquityTimeframe, basis: EquityBasis, limit?: number, before?: string): Observable<EquityCandlesResponse>`
  - model: `HISTORY_PAGE_LIMIT = 200`, `PAGE_TRIGGER_CANDLES = 20`, `prependPage(loaded: readonly EquityCandle[], page: readonly EquityCandle[]): EquityCandle[]`, `mergeLatest(loaded: readonly EquityCandle[], latest: readonly EquityCandle[]): EquityCandle[]`, `shouldLoadOlder(range: LogicalWindow | null, hasMore: boolean, busy: boolean): boolean`
  - `EquityCandlesStore` state `hasMore: boolean`, `pageLoading: boolean`, `pageError: boolean`, `atLiveEdge: boolean` (initially `false`, `false`, `false`, `true`); methods `loadOlder(): void`, `setAtLiveEdge(atEdge: boolean): void`. V181-7 calls `loadOlder()` when `shouldLoadOlder(visible, store.hasMore(), store.pageLoading())` is true, shows the retry note on `pageError()`, and drives `setAtLiveEdge`.
  - `equityCandlesStoreStub()` gains the same six members; `calls.loadOlder: number`, `calls.atLiveEdge: boolean[]`.

**Rules (spec § 2, § 9):**
- `loadOlder()` asks for `limit=200` before the oldest loaded candle's `t`, sent back unchanged. It is a no-op while a page is in flight, when the last answer said `has_more: false`, or with nothing loaded. `pageError` is cleared at the start of each attempt, so the next pan retries.
- A scan refresh fetches the newest 120 again. `mergeLatest` keeps the older pages and replaces everything from the refresh's first candle on, so the growing last candle updates and nothing paged in is lost. A page answering after a view change is dropped (`view` counter); a view change resets the four paging fields. `hasMore` then keeps the value the oldest page set. If the refresh's first candle is not among the loaded ones (the loaded set is shorter, or a gap opened), the refresh replaces everything and its own `has_more` applies.

- [ ] **Step 1: Write the failing model and client tests**

Append to `equity-range.model.spec.ts`, and add `HISTORY_PAGE_LIMIT, PAGE_TRIGGER_CANDLES, mergeLatest, prependPage, shouldLoadOlder` to its import list:

```ts
describe('history paging', () => {
  const day = (t: string, c = 100): EquityCandle => candle({ t, c });

  it('pages 200 candles and triggers within 20 candles of the oldest', () => {
    expect([HISTORY_PAGE_LIMIT, PAGE_TRIGGER_CANDLES]).toEqual([200, 20]);
    expect(shouldLoadOlder({ from: 19.5, to: 80 }, true, false)).toBe(true);
    expect(shouldLoadOlder({ from: 20, to: 80 }, true, false)).toBe(false);
  });

  it('never triggers without more history, while busy, or before the chart reports a range', () => {
    expect(shouldLoadOlder({ from: 2, to: 80 }, false, false)).toBe(false);
    expect(shouldLoadOlder({ from: 2, to: 80 }, true, true)).toBe(false);
    expect(shouldLoadOlder(null, true, false)).toBe(false);
  });

  it('prepends an older page and drops any candle already loaded', () => {
    const loaded = [day('2026-10-15'), day('2026-10-16')];
    const page = [day('2026-10-13'), day('2026-10-14'), day('2026-10-15', 999)];
    expect(prependPage(loaded, page).map((c) => [c.t, c.c])).toEqual([
      ['2026-10-13', 100], ['2026-10-14', 100], ['2026-10-15', 100], ['2026-10-16', 100]]);
  });

  it('keeps the two fall-back 01:00 hours apart: their t differs by offset', () => {
    const loaded = [day('2026-11-01T01:00:00-05:00')];
    const page = [day('2026-11-01T01:00:00-04:00')];
    expect(prependPage(loaded, page)).toHaveLength(2);
  });

  it('merges a refresh over the paged history, replacing from its first candle on', () => {
    const loaded = [day('2026-10-13'), day('2026-10-14'), day('2026-10-15'), day('2026-10-16', 1)];
    const latest = [day('2026-10-15'), day('2026-10-16', 2), day('2026-10-17')];
    expect(mergeLatest(loaded, latest).map((c) => [c.t, c.c])).toEqual([
      ['2026-10-13', 100], ['2026-10-14', 100], ['2026-10-15', 100],
      ['2026-10-16', 2], ['2026-10-17', 100]]);
  });

  it('takes the refresh whole when its first candle is not loaded', () => {
    const latest = [day('2026-10-20'), day('2026-10-21')];
    expect(mergeLatest([day('2026-10-13')], latest)).toEqual(latest);
    expect(mergeLatest([], latest)).toEqual(latest);
    expect(mergeLatest([day('2026-10-13')], [])).toEqual([]);
  });
});
```

In `frontend/src/app/api/api-client.spec.ts`, append inside the `equityCandles` test (after `second.flush(...)`):

```ts
    api.equityCandles('1H', 'mtm', 200, '2026-11-01T01:00:00-05:00').subscribe();
    const third = http.expectOne((r) => r.url.endsWith('/api/v1/equity/candles'));
    expect(third.request.params.get('limit')).toBe('200');
    expect(third.request.params.get('before')).toBe('2026-11-01T01:00:00-05:00');
    third.flush({ tf: '1H', basis: 'mtm', has_more: false, ...empty });
```

and in the same test assert the first request carries no cursor, right after `expect(first.request.params.has('limit')).toBe(false);`:

```ts
    expect(first.request.params.has('before')).toBe(false);
```

- [ ] **Step 2: Write the failing store tests**

In `frontend/src/app/stores/equity-candles.store.spec.ts`, give `response()` a `hasMore` argument and the new field:

```ts
function response(tf: EquityTimeframe = '1D', basis: EquityBasis = 'mtm',
                  candles: EquityCandle[] = [CANDLE], hasMore = false): EquityCandlesResponse {
  return { tf, basis, currency_symbol: '€', candles, has_more: hasMore, recording_since: null,
           as_of: '2026-10-17T14:00:00+00:00' };
}

const OLDER: EquityCandle = { ...CANDLE, t: '2026-10-15', c: 10120.5 };

/** The newest page says there is more; a `before` request answers `older`. */
function pagingApi(older: () => Observable<EquityCandlesResponse> = () =>
    of(response('1D', 'mtm', [OLDER], false))) {
  return {
    equityCandles: vi.fn().mockImplementation(
      (tf: EquityTimeframe, basis: EquityBasis, _limit?: number, before?: string) =>
        before ? older() : of(response(tf, basis, [CANDLE], true))),
  };
}
```

Add `Observable` to the `rxjs` import. Append inside `describe('EquityCandlesStore', …)`:

```ts
  it('starts with has_more from the first answer and the live edge in view', () => {
    const { store } = setup({}, pagingApi());
    expect(store.hasMore()).toBe(true);
    expect([store.pageLoading(), store.pageError(), store.atLiveEdge()]).toEqual([false, false, true]);
  });

  it('pages 200 candles before the oldest one and prepends them', () => {
    const { api, store } = setup({}, pagingApi());
    store.loadOlder();
    expect(api.equityCandles).toHaveBeenLastCalledWith('1D', 'mtm', 200, '2026-10-16');
    expect(store.data()?.candles).toEqual([OLDER, CANDLE]);
    expect(store.hasMore()).toBe(false);
    expect(store.pageLoading()).toBe(false);
  });

  it('does not page once the server said there is no more', () => {
    const { api, store } = setup();                       // okApi answers has_more: false
    store.loadOlder();
    expect(api.equityCandles).toHaveBeenCalledTimes(1);
  });

  it('keeps one page in flight at a time', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store } = setup({}, pendingApi(pending));
    pending[0].next(response('1D', 'mtm', [CANDLE], true));
    store.loadOlder();
    store.loadOlder();
    expect(pending).toHaveLength(2);
    expect(store.pageLoading()).toBe(true);
  });

  it('drops a page that answers after the timeframe changed', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store, tick } = setup({}, pendingApi(pending));
    pending[0].next(response('1D', 'mtm', [CANDLE], true));
    store.loadOlder();
    store.setTimeframe('1H');
    tick();
    const hour = { ...CANDLE, t: '2026-10-16T10:00:00-04:00' };
    pending[2].next(response('1H', 'mtm', [hour], false));
    pending[1].next(response('1D', 'mtm', [OLDER], false));
    expect(store.data()?.candles).toEqual([hour]);
    expect(store.pageLoading()).toBe(false);
  });

  it('keeps the candles on a failed page, flags it, and clears the flag on retry', () => {
    let fail = true;
    const { store } = setup({}, pagingApi(() =>
      fail ? throwError(() => new Error('boom')) : of(response('1D', 'mtm', [OLDER], false))));
    store.loadOlder();
    expect(store.data()?.candles).toEqual([CANDLE]);
    expect([store.pageError(), store.pageLoading(), store.hasMore()]).toEqual([true, false, true]);
    fail = false;
    store.loadOlder();
    expect(store.pageError()).toBe(false);
    expect(store.data()?.candles).toEqual([OLDER, CANDLE]);
  });

  it('keeps paged history through a scan refresh and updates the newest candle', () => {
    const api = pagingApi();
    const { store, scan, tick } = setup({}, api);
    store.loadOlder();
    const grown = { ...CANDLE, c: 10300 };
    api.equityCandles.mockImplementation(() => of(response('1D', 'mtm', [grown], true)));
    scan.update((n) => n + 1);
    tick();
    expect(store.data()?.candles).toEqual([OLDER, grown]);
    expect(store.hasMore()).toBe(false);                  // still the oldest page's answer
  });

  it('records the live-edge flag and resets it on a timeframe change', () => {
    const { store, tick } = setup();
    store.setAtLiveEdge(false);
    expect(store.atLiveEdge()).toBe(false);
    store.setTimeframe('1H');
    tick();
    expect(store.atLiveEdge()).toBe(true);
  });
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd frontend && npx ng test --include src/app/stores/equity-candles.store.spec.ts --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --include src/app/api/api-client.spec.ts --watch=false`
Expected: FAIL — `HISTORY_PAGE_LIMIT` / `prependPage` not exported, `store.loadOlder is not a function`, `before` param missing.

- [ ] **Step 4: Add the response field and the client cursor**

In `frontend/src/app/api/models.ts`, add `has_more: boolean;` to `EquityCandlesResponse` after `candles: EquityCandle[];`, and append to its doc comment (after "carried for API consumers."): `` `has_more` (v181) is true when older candles exist beyond this page; page them with `before`. ``

In `frontend/src/app/api/api-client.ts`, replace `equityCandles`:

```ts
  /** Equity candles for the Dashboard chart (v172). `limit` is left to the
   *  server's default (120) unless given. `before` (v181) pages older
   *  history: an oldest candle's `t`, sent back unchanged. */
  equityCandles(
    tf: EquityTimeframe,
    basis: EquityBasis,
    limit?: number,
    before?: string,
  ): Observable<EquityCandlesResponse> {
    let params = new HttpParams().set('tf', tf).set('basis', basis);
    if (limit !== undefined) params = params.set('limit', String(limit));
    if (before !== undefined) params = params.set('before', before);
    return this.http.get<EquityCandlesResponse>(`${this.base}/equity/candles`, { params });
  }
```

Add `has_more: false,` to the three typed literals:
- `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `const CANDLES: EquityCandlesResponse = { tf: '1D', basis: 'mtm', currency_symbol: '€', has_more: false, recording_since: …`
- `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts`, the same edit on its `CANDLES`.
- `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`, in `response()`: `return { tf: '1D', basis: 'mtm', currency_symbol: '€', candles, has_more: false, recording_since: …`

- [ ] **Step 5: Add the paging rules to the model**

Append to `equity-range.model.ts`:

```ts
/* -- history paging (§ 2) ------------------------------------------------- */

/** Candles asked for per older page. */
export const HISTORY_PAGE_LIMIT = 200;
/** Page once the view's left edge is within this many candles of the oldest. */
export const PAGE_TRIGGER_CANDLES = 20;

/** True when the view nears the oldest loaded candle (logical index 0), the
 *  last answer said older history exists, and no page is in flight. */
export function shouldLoadOlder(
  range: LogicalWindow | null,
  hasMore: boolean,
  busy: boolean,
): boolean {
  return range !== null && hasMore && !busy && range.from < PAGE_TRIGGER_CANDLES;
}

/** An older page in front of the loaded candles. A candle already loaded is
 *  not repeated; `t` is unique per bucket (the fall-back hours differ by
 *  offset), so it is the key. */
export function prependPage(
  loaded: readonly EquityCandle[],
  page: readonly EquityCandle[],
): EquityCandle[] {
  const known = new Set(loaded.map((c) => c.t));
  return [...page.filter((c) => !known.has(c.t)), ...loaded];
}

/** A refresh of the newest candles over paged history: loaded candles before
 *  the refresh's first one stay, everything from it on is replaced (the last
 *  candle grows between scans). When that first candle is not loaded, the
 *  refresh replaces everything, so no gap is ever bridged silently. */
export function mergeLatest(
  loaded: readonly EquityCandle[],
  latest: readonly EquityCandle[],
): EquityCandle[] {
  if (latest.length === 0) return [];
  const at = loaded.findIndex((c) => c.t === latest[0].t);
  return at < 0 ? [...latest] : [...loaded.slice(0, at), ...latest];
}
```

- [ ] **Step 6: Page in the store**

In `frontend/src/app/stores/equity-candles.store.ts`, extend the imports:

```ts
import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../api/models';
import {
  HISTORY_PAGE_LIMIT,
  mergeLatest,
  prependPage,
} from '../workspaces/dashboard/panels/equity-range.model';
```

Replace the slice and add the initial state:

```ts
interface EquityCandlesSlice {
  data: EquityCandlesResponse | null;
  loading: boolean;
  error: string | null;
  /** v181: the last answer that set the oldest candle said more exist. */
  hasMore: boolean;
  /** v181: an older page is in flight. */
  pageLoading: boolean;
  /** v181: the last older page failed; the chart shows a retry note. */
  pageError: boolean;
  /** v181: the chart shows the newest candle (drives "↦ Latest"). */
  atLiveEdge: boolean;
}

const INITIAL: EquityCandlesSlice = {
  data: null, loading: false, error: null,
  hasMore: false, pageLoading: false, pageError: false, atLiveEdge: true,
};

/** What a timeframe or basis change resets: the old view's paging state. */
const FRESH_VIEW = { hasMore: false, pageLoading: false, pageError: false, atLiveEdge: true };
```

Add this paragraph to the end of the store's doc comment:

```ts
 *
 * **Pages (v181 § 2).** `loadOlder()` prepends `HISTORY_PAGE_LIMIT` older
 * candles; a scan refresh merges the newest candles over them
 * (`mergeLatest`), so paged history survives the scan cadence. A page that
 * answers after a view change is dropped by the `view` counter. A failed
 * page keeps every candle and sets `pageError`; the next call retries.
```

Replace `withState(...)` with `withState<EquityCandlesSlice>(INITIAL),` and replace the whole `withMethods(...)` block:

```ts
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    // Bumped on every view change; a page answering for an older view is dropped.
    let view = 0;

    // untracked throughout: load() runs inside the onInit effect, and a
    // tracked read of `data`/`hasMore` would make every response re-trigger it.
    const applyLatest = (response: EquityCandlesResponse): void => {
      const shown = untracked(() => store.data());
      const sameView = shown !== null && shown.tf === response.tf && shown.basis === response.basis;
      const candles = sameView ? mergeLatest(shown.candles, response.candles) : response.candles;
      const keptOlder = candles.length > response.candles.length;
      patchState(store, {
        data: { ...response, candles },
        hasMore: keptOlder ? untracked(() => store.hasMore()) : response.has_more === true,
        loading: false,
        error: null,
      });
    };

    const load = (): void => {
      const tf = store.tf();
      const basis = store.basis();
      const previous = untracked(() => store.data());
      const sameView = previous !== null && previous.tf === tf && previous.basis === basis;
      const request = ++latestRequest;
      if (!sameView) view += 1;
      patchState(store, {
        loading: true, error: null, data: sameView ? previous : null,
        ...(sameView ? {} : FRESH_VIEW),
      });
      api.equityCandles(tf, basis).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.candles)) {
            patchState(store, { loading: false });
            return;
          }
          applyLatest(response);
        },
        error: () => {
          if (request !== latestRequest) return;
          // untracked for the same reason: a synchronous error (a test's
          // throwError) lands inside the effect's run.
          const shown = untracked(() => store.data());
          patchState(store, { loading: false, error: shown ? null : EQUITY_CANDLES_ERROR });
        },
      });
    };

    const loadOlder = (): void => {
      const shown = untracked(() => store.data());
      const busy = untracked(() => store.pageLoading());
      const more = untracked(() => store.hasMore());
      if (!shown || shown.candles.length === 0 || busy || !more) return;
      const pageView = view;
      patchState(store, { pageLoading: true, pageError: false });
      api.equityCandles(shown.tf, shown.basis, HISTORY_PAGE_LIMIT, shown.candles[0].t).subscribe({
        next: (page) => {
          if (pageView !== view) return;
          const current = untracked(() => store.data());
          if (!current || !page || !Array.isArray(page.candles)) {
            patchState(store, { pageLoading: false });
            return;
          }
          patchState(store, {
            data: { ...current, candles: prependPage(current.candles, page.candles) },
            hasMore: page.has_more === true,
            pageLoading: false,
          });
        },
        error: () => {
          if (pageView !== view) return;
          patchState(store, { pageLoading: false, pageError: true });
        },
      });
    };

    // Does not call `load()`: the write changes `tf()`/`basis()`, and the
    // tracked onInit effect refetches once as a result.
    const write = (value: EquityChartPrefs): void =>
      prefs.update((current) => writeEquityChartPrefs(current, value));

    return {
      load,
      loadOlder,
      setTimeframe(tf: EquityTimeframe): void {
        write({ tf, basis: store.basis() });
      },
      setBasis(basis: EquityBasis): void {
        write({ tf: store.tf(), basis });
      },
      setAtLiveEdge(atEdge: boolean): void {
        patchState(store, { atLiveEdge: atEdge });
      },
    };
  }),
```

`load()` still calls `api.equityCandles(tf, basis)` with two arguments, so the existing `toHaveBeenCalledWith('1D', 'mtm')` assertions hold.

- [ ] **Step 7: Extend the component stub**

In `frontend/src/app/testing/equity-candles-store.stub.ts`, inside `equityCandlesStoreStub`, replace the `calls` line and add the `atLiveEdge` signal beside `tf`/`basis`:

```ts
  const atLiveEdge = signal(true);
  const calls = { load: 0, loadOlder: 0, tf: [] as EquityTimeframe[], basis: [] as EquityBasis[],
                  atLiveEdge: [] as boolean[] };
```

In the returned object, add after `error: signal<string | null>(null),`:

```ts
    hasMore: signal(data?.has_more ?? false),
    pageLoading: signal(false),
    pageError: signal(false),
    atLiveEdge: atLiveEdge.asReadonly(),
```

and after the `load` method, plus at the end after `setBasis`:

```ts
    loadOlder: (): void => {
      calls.loadOlder += 1;
    },
```

```ts
    setAtLiveEdge: (value: boolean): void => {
      calls.atLiveEdge.push(value);
      atLiveEdge.set(value);
    },
```

Update its doc comment's first line to `A stand-in for \`EquityCandlesStore\` in component specs (v172, paging members v181): …`. `hasMore`, `pageLoading` and `pageError` are writable signals so a component spec can `.set()` them.

- [ ] **Step 8: Run the three specs to verify they pass**

Run: `cd frontend && npx ng test --include src/app/stores/equity-candles.store.spec.ts --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --include src/app/api/api-client.spec.ts --watch=false`
Expected: PASS, the existing store tests included.

- [ ] **Step 9: Run the specs whose literals changed, and type-check**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts --watch=false`
Expected: PASS (nothing in them reads the new members yet).

Run: `cd frontend && npx tsc -p tsconfig.spec.json --noEmit`
Expected: no errors. In particular, no `Property 'has_more' is missing` anywhere.

- [ ] **Step 10: Commit (two scoped commits)**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
git commit -m "feat(v181): equity candles client sends a before cursor; response carries has_more" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git add frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts frontend/src/app/stores/equity-candles.store.ts frontend/src/app/stores/equity-candles.store.spec.ts frontend/src/app/testing/equity-candles-store.stub.ts
git commit -m "feat(v181): EquityCandlesStore pages older history and keeps it through scan refreshes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-4: Profit/loss tone helpers

**Model:** haiku — four small pure functions with their thresholds given exactly; no wiring.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts` (append)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks besides the file itself (V181-2/V181-3 created and extended it).
- Produces (consumed by V181-7's readout parts and V181-9's cards; the API sends no colour, spec § 5; the rules themselves are the docstrings in Step 3):
  - `type PnlTone = 'pos' | 'neg' | 'warn' | 'neutral'` — maps to `--pos` / `--neg` / `--warn` / `--text-secondary`; a null figure is always `neutral`, so an em dash is never coloured.
  - `BREAKEVEN_BAND_PP = 0.5`, `MIN_CLOSES_FOR_TONE = 5`, `RISK_WARN_FRACTION = 0.75`
  - `signTone(value: number | null)`, `drawdownTone(pct: number | null)` (`neg` for any non-zero value, either sign), `breakevenPairTone(winRatePct: number | null, payoff: number | null, closes: number | null)` (win rate in percent, e.g. 49.1; one tone for both the win-rate and the payoff card), `riskTone(usedPct: number | null, capPct: number | null)` — all return `PnlTone`.

- [ ] **Step 1: Write the failing tests**

Append to `equity-range.model.spec.ts`, adding `BREAKEVEN_BAND_PP, MIN_CLOSES_FOR_TONE, RISK_WARN_FRACTION, breakevenPairTone, drawdownTone, riskTone, signTone` to its import list:

```ts
describe('profit/loss tones', () => {
  it('colours by sign, and never a zero or a missing figure', () => {
    expect([signTone(12.5), signTone(-0.01), signTone(0), signTone(null)])
      .toEqual(['pos', 'neg', 'neutral', 'neutral']);
  });

  it('colours any non-zero drawdown as a loss', () => {
    expect([drawdownTone(3.2), drawdownTone(-3.2), drawdownTone(0), drawdownTone(null)])
      .toEqual(['neg', 'neg', 'neutral', 'neutral']);
  });

  it('judges win rate against the breakeven its payoff implies, with a 0.5 pp band', () => {
    expect(BREAKEVEN_BAND_PP).toBe(0.5);
    // payoff 1 -> breakeven 50 %
    expect([50.6, 50.4, 49.6, 49.4].map((wr) => breakevenPairTone(wr, 1, 20)))
      .toEqual(['pos', 'neutral', 'neutral', 'neg']);
  });

  it('reads a low payoff on a high win rate as profitable: the pair, not each alone', () => {
    // payoff 0.8 -> breakeven 55.6 %; 65 % clears it
    expect(breakevenPairTone(65, 0.8, 30)).toBe('pos');
    // payoff 2.34 -> breakeven 29.9 %; 49.1 % clears it
    expect(breakevenPairTone(49.1, 2.34, 30)).toBe('pos');
    // payoff 0.5 -> breakeven 66.7 %; 60 % misses it
    expect(breakevenPairTone(60, 0.5, 30)).toBe('neg');
  });

  it('stays neutral with a missing figure, a payoff of zero or less, or fewer than 5 closes', () => {
    expect(MIN_CLOSES_FOR_TONE).toBe(5);
    expect([breakevenPairTone(null, 1.2, 20), breakevenPairTone(60, null, 20),
            breakevenPairTone(60, 1.2, null)]).toEqual(['neutral', 'neutral', 'neutral']);
    expect([breakevenPairTone(60, 0, 20), breakevenPairTone(60, -1, 20)])
      .toEqual(['neutral', 'neutral']);
    expect([breakevenPairTone(90, 3, 4), breakevenPairTone(90, 3, 5)]).toEqual(['neutral', 'pos']);
  });

  it('warns on risk from 75 % of the cap and flags it at or over the cap', () => {
    expect(RISK_WARN_FRACTION).toBe(0.75);
    expect([riskTone(0, 6), riskTone(4.4, 6), riskTone(4.5, 6), riskTone(5.9, 6)])
      .toEqual(['neutral', 'neutral', 'warn', 'warn']);
    expect([riskTone(6, 6), riskTone(7.2, 6)]).toEqual(['neg', 'neg']);
  });

  it('leaves risk neutral without a figure or a cap', () => {
    expect([riskTone(null, 6), riskTone(3, null), riskTone(3, 0)])
      .toEqual(['neutral', 'neutral', 'neutral']);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --watch=false`
Expected: FAIL — `signTone` (and the rest) not exported.

- [ ] **Step 3: Implement the helpers**

Append to `equity-range.model.ts`:

```ts
/* -- profit/loss tone (§ 5) ----------------------------------------------- */

/** `pos` = good for the account (`--pos`), `neg` = bad (`--neg`), `warn` =
 *  risk near its cap (`--warn`), `neutral` = no judgement or no data
 *  (`--text-secondary`). A null figure is always neutral, so an em dash is
 *  never coloured. The rules live only here; the API sends no colour. */
export type PnlTone = 'pos' | 'neg' | 'warn' | 'neutral';

/** Half-width of the neutral band around the breakeven win rate, in pp. */
export const BREAKEVEN_BAND_PP = 0.5;
/** Fewer closes than this and a win-rate/payoff colour would be noise. */
export const MIN_CLOSES_FOR_TONE = 5;
/** Risk used from this share of the cap reads as a warning. */
export const RISK_WARN_FRACTION = 0.75;

export function signTone(value: number | null): PnlTone {
  if (value === null || value === 0) return 'neutral';
  return value > 0 ? 'pos' : 'neg';
}

/** Any non-zero drawdown is bad; its sign convention does not matter. */
export function drawdownTone(pct: number | null): PnlTone {
  return pct === null || pct === 0 ? 'neutral' : 'neg';
}

/** Win rate and payoff judged as a pair: the book breaks even at a win rate
 *  of `100 / (1 + payoff)` %, so a 0.8 payoff on a 65 % win rate is green.
 *  Breakeven ignores costs; the panel caption says the figures are pre-cost. */
export function breakevenPairTone(
  winRatePct: number | null,
  payoff: number | null,
  closes: number | null,
): PnlTone {
  if (winRatePct === null || payoff === null || closes === null) return 'neutral';
  if (payoff <= 0 || closes < MIN_CLOSES_FOR_TONE) return 'neutral';
  const breakeven = 100 / (1 + payoff);
  if (winRatePct > breakeven + BREAKEVEN_BAND_PP) return 'pos';
  if (winRatePct < breakeven - BREAKEVEN_BAND_PP) return 'neg';
  return 'neutral';
}

/** Open risk against its cap: plain below 75 %, warning up to the cap, bad
 *  at or over it. */
export function riskTone(usedPct: number | null, capPct: number | null): PnlTone {
  if (usedPct === null || capPct === null || capPct <= 0) return 'neutral';
  if (usedPct >= capPct) return 'neg';
  return usedPct >= capPct * RISK_WARN_FRACTION ? 'warn' : 'neutral';
}
```

- [ ] **Step 4: Run them to verify they pass**

Run: `cd frontend && npx ng test --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --watch=false`
Expected: PASS, every earlier `describe` in the file still green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts
git commit -m "feat(v181): profit/loss tone helpers -- sign, drawdown, breakeven pair, risk against cap" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
