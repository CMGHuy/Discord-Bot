# v181 — Dashboard range chart: Part 2a — range API and the scope model (V181-10..V181-12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V181-12:" -A 400 <this file>`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Index:** [2026-10-21-v181-dashboard-range-chart_0-index.md](2026-10-21-v181-dashboard-range-chart_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there and bind every task below.

Tasks V181-10..V181-12 (V181-13, `DashboardStore`'s scope, moved to part 2c for the 1500-line limit): `GET /dashboard?mode=range` with one `ClosedWindow` threaded through every consumer of `mode` (and `dashboard()` pulled below its complexity baseline), `GET /trades?closed_from=&closed_to=` for the Closed tab, the pure preset model with its preference key and client parameters, and `DashboardStore`'s scope selection with the debounced range refetch and the `stale` flag. Spec sections covered: § 1 (presets, persistence, the ad-hoc Range never persisted), § 6 (`mode=range`, the Closed tab, the request mapping, the one-clock rule), § 7 (`DashboardStore` ownership), § 8 (data flow), § 9 (range refetch failure).

Work in the worktree `.claude/worktrees/2026-10-21-v181-dashboard-range-chart` (created in V181-1); every path below is relative to its root.

**Contracts consumed from part 1a** (ledger rows V181-2..V181-4; this part relies on exactly these):

- `equity-range.model.ts` exports `TimeWindow { from: string; to: string }` (ISO UTC, `Date.toISOString()` form, half-open), `nyMidnight(isoDate: string): Date`, and has the module-private helpers `NY_PARTS` (an `Intl.DateTimeFormat` for `America/New_York` with 2-digit month/day, `hourCycle: 'h23'`) and `addDays(isoDate: string, days: number): string`. V181-12 appends to the same file and reuses the two private helpers in place — it does not redefine them.
- `equity-range.model.ts` already imports `EQUITY_TIMEFRAMES` from `../../../ui/equity-chart-prefs`, so the preference module must never import a value back from the model (that would be a cycle). V181-12 therefore defines `ScopePreset` and `SCOPE_PRESETS` in `equity-chart-prefs.ts` beside `EQUITY_TIMEFRAMES` and **re-exports both from `equity-range.model.ts`**, which is where the ledger names them; consumers import them from the model.

**Frontend runner:** `cd frontend && npx ng test --include <spec> --watch=false` — never bare `npx vitest run`. A run that dies after exactly 60 s with `Timeout waiting for worker to respond` ran nothing: re-run it (`docs/claude/testing-cost.md` § Frontend).

**Backend runner:** `python scripts/dev/testrun.py file <test file>` (`admin` suite). `/replicate-prod-db` already ran in V181-1.

---

# Phase 3 — Range scope: API

### Task V181-10: `/dashboard?mode=range`: one window through every consumer

**Model:** opus — threads one window through five `mode` consumers of a legacy complexity-21 handler whose `_lifecycle_counts` swallows exceptions, so a fall-through to "today" fails silently; the extraction must lower the score without changing any other mode.

**Files:**
- Create: `swingbot/admin/api_v1/closed_window.py`
- Modify: `swingbot/admin/api_v1/dashboard.py` (imports at lines 32-41; `_lifecycle_counts` lines 99-139; `_SCOPES`/`_scope` lines 142-155; `_realized_parts` lines 157-171; `dashboard()` lines 224-306)
- Create: `tests/admin/test_closed_window.py` (the `admin` suite owns `tests/admin/`; no `suites.toml` change)
- Modify: `tests/admin/test_api_v1_dashboard.py` (top imports; `test_scope_defaults_to_active_and_is_echoed_back` ~line 450; a new section appended at the end)
- Modify: `scripts/dev/complexity_baseline.json` (only through `--update`)

**Interfaces:**
- Consumes: `ApiError(code, message, status)` and `iso(value: datetime | None) -> str | None` from `swingbot/admin/api_v1/__init__.py`; `dash.is_today_berlin(iso_ts)` (`swingbot/admin/dashboard.py:94`); `trades.build_rows(all_trades)` rows carrying `status`, `closed_at` (the terminal time: the trade's close, or the cancel transition for an unfilled plan, `trades.py:236-238`) and `today`.
- Produces (V181-11 imports the first three; V181-12's client sends the query):
  - `closed_window.ClosedWindow(NamedTuple)`: `start: datetime`, `end: datetime` (both aware).
  - `closed_window.parse_closed_window(from_raw: str | None, to_raw: str | None, *, names: tuple[str, str] = ("from", "to")) -> ClosedWindow` — `ApiError("invalid", …, 400)` on a missing bound, an unreadable or naive timestamp, or `from > to`; the message names the offending parameter from `names`.
  - `closed_window.closed_in_window(iso_ts: str | None, window: ClosedWindow) -> bool` — `start <= ts < end` on aware instants, a naive stored value read as UTC, a missing/unreadable one outside.
  - `dashboard.py`: `_SCOPES = ("active", "today", "all", "range")`; `_parse_range_window(mode: str) -> ClosedWindow | None`; `_scope_trades(all_raw: list[dict], mode: str, window: ClosedWindow | None) -> list[dict]`; `_realized_parts(trades, mode, window=None)`; `_lifecycle_counts(mode, all_trades, window=None)`; private `_closed_row_in_scope(row, mode, window) -> bool` and `_scope_echo(mode, window) -> dict`.
  - Response `scope: {"mode": str, "from": str | None, "to": str | None}` — the bounds as `iso()` UTC strings for `range`, `null` for every other mode.

**Rules (spec § 6):** `mode=range` needs both `from` and `to`, timezone-aware, `from <= to` (an empty window is allowed); closes count when `from <= closed_at < to`. Open trades stay in `scoped_raw` exactly as in `mode=today`. Every helper decides on `window is not None` **first**, so `range` can never reach the Berlin-day branch. Point-in-time figures (balance, open P&L, open trades, risk used) never read the window. `test_dashboard_reads_the_trade_log_once` stays green: no second `TradeLog` read.

- [ ] **Step 1: Record the complexity before**

Run: `python -m radon cc -s swingbot/admin/api_v1/dashboard.py | cat`
Expected: `F 226:0 dashboard - D (21)` (and `_lifecycle_counts - B (8)`, `_realized_parts - B (6)`). Note the 21 for the commit message. (`| cat` — radon crashes with a colorama `OSError` on this Windows shell without it.)

- [ ] **Step 2: Write the failing unit tests for the window**

Create `tests/admin/test_closed_window.py`:

```python
"""v181 -- the `[from, to)` closed-trade window.

One definition, shared by `GET /dashboard?mode=range` and the Closed tab's
`GET /trades?closed_from=&closed_to=`, so the KPIs and the table under them
cannot disagree about which closes a window holds (spec v181 § 6).
"""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin.api_v1 import ApiError
from swingbot.admin.api_v1.closed_window import (
    ClosedWindow,
    closed_in_window,
    parse_closed_window,
)

UTC = timezone.utc
START = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)   # 00:00 New York, 1 Oct
END = datetime(2026, 10, 2, 4, 0, tzinfo=UTC)
WINDOW = ClosedWindow(START, END)


def test_parses_two_aware_bounds_in_any_offset():
    window = parse_closed_window("2026-10-01T04:00:00+00:00", "2026-10-02T00:00:00-04:00")
    assert window == WINDOW


def test_accepts_the_form_the_spa_sends():
    # Date.toISOString() -> milliseconds and a Z suffix.
    assert parse_closed_window("2026-10-01T04:00:00.000Z", "2026-10-02T04:00:00.000Z") == WINDOW


def test_an_empty_window_is_allowed():
    assert parse_closed_window(START.isoformat(), START.isoformat()) == ClosedWindow(START, START)


@pytest.mark.parametrize("from_raw, to_raw, names_in_message", [
    (None, "2026-10-02T04:00:00+00:00", "from"),
    ("2026-10-01T04:00:00+00:00", "", "to"),
    ("2026-10-01T04:00:00", "2026-10-02T04:00:00+00:00", "timezone"),
    ("2026-10-01", "2026-10-02T04:00:00+00:00", "timezone"),
    ("yesterday", "2026-10-02T04:00:00+00:00", "from"),
    ("2026-10-02T04:00:00+00:00", "2026-10-01T04:00:00+00:00", "after"),
])
def test_rejects_a_bad_window_with_a_400(from_raw, to_raw, names_in_message):
    with pytest.raises(ApiError) as caught:
        parse_closed_window(from_raw, to_raw)
    assert (caught.value.code, caught.value.status) == ("invalid", 400)
    assert names_in_message in caught.value.message


def test_names_the_parameters_it_was_given():
    with pytest.raises(ApiError) as caught:
        parse_closed_window(None, END.isoformat(), names=("closed_from", "closed_to"))
    assert "closed_from" in caught.value.message


def test_a_close_at_from_counts_and_one_at_to_does_not():
    assert closed_in_window(START.isoformat(), WINDOW)
    assert closed_in_window((END - timedelta(microseconds=1)).isoformat(), WINDOW)
    assert not closed_in_window(END.isoformat(), WINDOW)
    assert not closed_in_window((START - timedelta(seconds=1)).isoformat(), WINDOW)


def test_compares_instants_not_wall_clocks():
    # 00:30 in New York on 1 Oct is 04:30Z: inside, whatever the offset says.
    assert closed_in_window("2026-10-01T00:30:00-04:00", WINDOW)
    assert not closed_in_window("2026-10-01T23:59:00-05:00", WINDOW)


def test_reads_a_naive_stored_close_as_utc():
    # Older records carry naive timestamps; `is_today_berlin` reads them as UTC too.
    assert closed_in_window("2026-10-01T04:00:00", WINDOW)
    assert not closed_in_window("2026-10-01T03:59:59", WINDOW)


@pytest.mark.parametrize("raw", [None, "", "not-a-date"])
def test_a_missing_or_unreadable_close_is_outside(raw):
    assert not closed_in_window(raw, WINDOW)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_closed_window.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.admin.api_v1.closed_window'`.

- [ ] **Step 4: Implement the window module**

Create `swingbot/admin/api_v1/closed_window.py`:

```python
"""v181 -- the `[from, to)` window a closed trade is counted in.

Shared by `GET /dashboard?mode=range` (`dashboard.py`) and the Closed tab's
`GET /trades?closed_from=&closed_to=` (`trades.py`). One parser and one
in-window test, so the KPI cards and the table under them are structurally
unable to disagree about which closes a window holds.

The SPA builds every window from whole New York buckets (spec v181 § 6), but
nothing here knows about New York: a window is two aware instants, and a close
is compared as an instant. A naive stored `closed_at` is read as UTC, exactly
as `dashboard.is_today_berlin` reads it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from . import ApiError


class ClosedWindow(NamedTuple):
    """Half-open `[start, end)`; both bounds timezone-aware."""

    start: datetime
    end: datetime


def _aware(raw: str | None, name: str) -> datetime:
    """One bound, or a 400 naming the parameter.

    A naive bound is rejected rather than read as UTC: the caller is the SPA,
    which always sends an offset, so a naive value is a malformed request --
    unlike a stored `closed_at`, which is old data and gets the UTC reading.
    """
    text = (raw or "").strip()
    if not text:
        raise ApiError("invalid", f"{name} is required: a window needs both bounds", 400)
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError("invalid", f"{name} is not an ISO timestamp: {raw!r}", 400)
    if value.tzinfo is None:
        raise ApiError("invalid", f"{name} must carry a timezone offset", 400)
    return value


def parse_closed_window(
    from_raw: str | None,
    to_raw: str | None,
    *,
    names: tuple[str, str] = ("from", "to"),
) -> ClosedWindow:
    """Both bounds, aware, in order -- or `ApiError("invalid", ..., 400)`.

    `names` are the query-parameter names the caller read, so the error
    message says `closed_from` on `/trades` and `from` on `/dashboard`.
    An empty window (`from == to`) is valid and simply holds nothing.
    """
    start = _aware(from_raw, names[0])
    end = _aware(to_raw, names[1])
    if start > end:
        raise ApiError("invalid", f"{names[0]} must not be after {names[1]}", 400)
    return ClosedWindow(start, end)


def closed_in_window(iso_ts: str | None, window: ClosedWindow) -> bool:
    """Whether a close at `iso_ts` falls in `[start, end)`.

    Missing or unreadable means outside: it cannot be shown to satisfy the
    window, and keeping it would make a count disagree with its rows.
    """
    if not iso_ts:
        return False
    try:
        value = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return window.start <= value < window.end
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_closed_window.py`
Expected: PASS (16 tests).

- [ ] **Step 6: Write the failing endpoint tests**

In `tests/admin/test_api_v1_dashboard.py`, extend the top imports (after `import json`):

```python
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
```

Change the shape in `test_scope_defaults_to_active_and_is_echoed_back` (~line 450) to the new echo:

```python
def test_scope_defaults_to_active_and_is_echoed_back(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert_shape(body["scope"], {"mode": str, "from": (str, type(None)),
                                 "to": (str, type(None))}, where="scope")
    assert body["scope"] == {"mode": "active", "from": None, "to": None}
```

Append at the end of the file:

```python
# --------------------------------------------------------------- v181 mode=range
#
# One window threads through every consumer of `mode`: the scoped_raw
# selection (`_scope_trades`), both `_realized_parts` calls (main and weak
# ledger) and `_lifecycle_counts`. One test per consumer, so none of them can
# fall through to the Berlin-day branch unnoticed -- `_lifecycle_counts`
# swallows exceptions and would blank the strip rather than fail.

RANGE_FROM = "2026-01-05T05:00:00+00:00"   # 00:00 New York, Mon 5 Jan
RANGE_TO = "2026-01-06T05:00:00+00:00"     # 00:00 New York, Tue 6 Jan
INSIDE = "2026-01-05T15:00:00+00:00"
BEFORE = "2026-01-04T15:00:00+00:00"
AFTER = "2026-01-07T15:00:00+00:00"

# The scope-dependent figures, plus the point-in-time ones that must never
# read the window (open P&L is left out: it prices open trades live).
_PARITY_KEYS = ("win_rate", "win_rate_n", "expectancy_r", "expectancy_n",
                "payoff_ratio", "realized", "realized_weak", "lifecycle",
                "open_trades", "risk_used_pct", "account_balance")


def _range(client, start=RANGE_FROM, end=RANGE_TO):
    # query_string, not an f-string URL: a literal "+00:00" in a URL decodes
    # to a space and the bound turns naive.
    return client.get("/api/v1/dashboard",
                      query_string={"mode": "range", "from": start, "to": end})


def _berlin_today_window() -> tuple[str, str]:
    """Berlin local midnight to the NEXT local midnight -- built from the two
    midnights, never `+24h`, so the 23 h and 25 h DST days hold."""
    berlin = ZoneInfo("Europe/Berlin")
    today = datetime.now(berlin).date()
    start = datetime.combine(today, time(0), tzinfo=berlin)
    end = datetime.combine(today + timedelta(days=1), time(0), tzinfo=berlin)
    return start.isoformat(), end.isoformat()


def _weak(trade: dict) -> dict:
    return {**trade, "ledger": "weak"}


def test_range_scope_echoes_its_bounds(seed, logged_in):
    seed()
    body = _range(logged_in).get_json()
    assert body["scope"] == {"mode": "range", "from": RANGE_FROM, "to": RANGE_TO}


def test_other_modes_echo_null_bounds(seed, logged_in):
    seed()
    for mode in ("today", "all"):
        scope = logged_in.get(f"/api/v1/dashboard?mode={mode}").get_json()["scope"]
        assert scope == {"mode": mode, "from": None, "to": None}


@pytest.mark.parametrize("query", [
    {"mode": "range"},
    {"mode": "range", "from": RANGE_FROM},
    {"mode": "range", "to": RANGE_TO},
    {"mode": "range", "from": "2026-01-05T05:00:00", "to": RANGE_TO},
    {"mode": "range", "from": RANGE_TO, "to": RANGE_FROM},
])
def test_a_bad_range_is_a_400(seed, logged_in, query):
    seed()
    assert_error(logged_in.get("/api/v1/dashboard", query_string=query), "invalid", 400)


def test_a_close_at_from_counts_and_one_at_to_does_not(seed, logged_in):
    seed(trades=[
        _closed("a" * 16, closed_at=RANGE_FROM, amount=10.0),
        _closed("b" * 16, closed_at=INSIDE, amount=5.0),
        _closed("c" * 16, closed_at=RANGE_TO, amount=999.0),
    ])
    realized = _range(logged_in).get_json()["realized"]
    assert (realized["n"], realized["amount"]) == (2, 15.0)


def test_range_scopes_the_main_ledger_realised_parts(seed, logged_in):
    """Main `_realized_parts`: realised, win rate, expectancy and payoff."""
    seed(trades=[
        _closed("d" * 16, closed_at=INSIDE, amount=50.0, status="win"),
        _closed("e" * 16, closed_at=BEFORE, amount=-20.0, status="loss", pct_exit=90.0),
        _closed("f" * 16, closed_at=AFTER, amount=-30.0, status="loss", pct_exit=90.0),
    ])
    body = _range(logged_in).get_json()
    assert body["realized"]["n"] == 1
    assert body["realized"]["amount"] == 50.0
    assert body["win_rate"] == 100.0
    assert body["expectancy_n"] == 1


def test_range_scopes_the_weak_ledger_realised_parts(seed, logged_in):
    """Weak `_realized_parts`: the second consumer, kept apart from main."""
    seed(trades=[
        _weak(_closed("g" * 16, closed_at=INSIDE, amount=40.0)),
        _weak(_closed("h" * 16, closed_at=BEFORE, amount=70.0)),
    ])
    body = _range(logged_in).get_json()
    assert (body["realized_weak"]["n"], body["realized_weak"]["amount"]) == (1, 40.0)
    assert body["realized"]["n"] == 0


def test_range_scopes_the_lifecycle_closed_and_cancelled_counts(seed, logged_in):
    from tests.admin.test_api_v1_trades import _plan, _trade

    inside = _trade("aaaaaaaaaaaaaaaa", status="win")
    inside["closed_at"] = INSIDE
    outside = _trade("bbbbbbbbbbbbbbbb", status="loss")
    outside["closed_at"] = AFTER
    cancelled_in = _plan("11111111-1111-4111-8111-111111111111", status="CANCELLED")
    cancelled_in["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": INSIDE}]
    cancelled_out = _plan("22222222-2222-4222-8222-222222222222", status="CANCELLED")
    cancelled_out["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": BEFORE}]
    seed(plans=[cancelled_in, cancelled_out], trades=[inside, outside])

    lifecycle = _range(logged_in).get_json()["lifecycle"]
    assert (lifecycle["CLOSED"], lifecycle["CANCELLED"]) == (1, 1)


def test_range_scopes_the_trades_get_stats_reads(seed, logged_in, monkeypatch):
    """`scoped_raw` (`_scope_trades`): every open trade, however old, plus the
    closes in the window -- the same rule `mode=today` applies to its day."""
    from swingbot.core.tracking.performance import TradeLog
    from tests.admin.test_api_v1_trades import _trade

    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", status="open"),
        _closed("b" * 16, closed_at=INSIDE, amount=5.0),
        _closed("c" * 16, closed_at=AFTER, amount=5.0),
    ])
    seen = []
    original = TradeLog.get_stats

    def spy(self, *args, **kwargs):
        seen.append(sorted(t["id"] for t in kwargs.get("trades") or []))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_stats", spy)
    assert _range(logged_in).status_code == 200
    # `in`, not `==`: another collector may call get_stats without `trades`.
    assert ["aaaaaaaaaaaaaaaa", "b" * 16] in seen
    assert not any("c" * 16 in ids for ids in seen)


def test_scope_trades_never_falls_through_to_today():
    """Unit check on the helper itself: with a window, a close today but
    outside the window is out, whatever `mode` says."""
    from datetime import timezone as tz

    from swingbot.admin.api_v1.closed_window import ClosedWindow
    from swingbot.admin.api_v1.dashboard import _scope_trades

    window = ClosedWindow(datetime(2026, 1, 5, 5, tzinfo=tz.utc),
                          datetime(2026, 1, 6, 5, tzinfo=tz.utc))
    trades = [
        {"id": "open", "status": "open", "closed_at": None},
        {"id": "in", "status": "win", "closed_at": INSIDE},
        {"id": "today", "status": "win", "closed_at": _today_iso()},
    ]
    assert [t["id"] for t in _scope_trades(trades, "range", window)] == ["open", "in"]
    assert [t["id"] for t in _scope_trades(trades, "all", None)] == ["open", "in", "today"]
    assert [t["id"] for t in _scope_trades(trades, "today", None)] == ["open", "today"]


def _parity_book():
    """A today win and loss, an old loss, an open trade, a weak close today
    and a plan cancelled today -- every consumer has something to count."""
    from tests.admin.test_api_v1_trades import _plan, _trade

    today = _today_iso()
    cancelled = _plan("11111111-1111-4111-8111-111111111111", status="CANCELLED")
    cancelled["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": today}]
    return {
        "plans": [cancelled],
        "trades": [
            _closed("a" * 16, closed_at=today, amount=50.0, status="win"),
            _closed("b" * 16, closed_at=today, amount=-20.0, status="loss", pct_exit=90.0),
            _closed("c" * 16, closed_at="2026-01-05T15:00:00+00:00", amount=-30.0,
                    status="loss", pct_exit=90.0),
            _trade("dddddddddddddddd", status="open"),
            _weak(_closed("e" * 16, closed_at=today, amount=15.0)),
        ],
    }


def test_a_berlin_day_window_equals_mode_today(seed, logged_in):
    seed(**_parity_book())
    start, end = _berlin_today_window()
    ranged = _range(logged_in, start, end).get_json()
    today = logged_in.get("/api/v1/dashboard?mode=today").get_json()
    assert {k: ranged[k] for k in _PARITY_KEYS} == {k: today[k] for k in _PARITY_KEYS}
    assert ranged["realized"]["n"] == 2


def test_a_window_over_all_history_equals_mode_all(seed, logged_in):
    seed(**_parity_book())
    ranged = _range(logged_in, "2000-01-01T00:00:00+00:00", "2100-01-01T00:00:00+00:00").get_json()
    all_days = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert {k: ranged[k] for k in _PARITY_KEYS} == {k: all_days[k] for k in _PARITY_KEYS}
    assert ranged["realized"]["n"] == 3


def test_range_mode_reads_the_trade_log_once(seed, logged_in, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog

    seed()
    calls = []
    original = TradeLog.get_trades

    def counting(self, *args, **kwargs):
        calls.append(kwargs.get("status"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TradeLog, "get_trades", counting)
    assert _range(logged_in).status_code == 200
    assert len(calls) == 1, f"get_trades called {len(calls)} times: {calls}"
```

- [ ] **Step 7: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: FAIL — the range tests get `400 mode must be one of active, today, all`, the echo tests see `{"mode": ...}` without `from`/`to`, and `_scope_trades` cannot be imported. Every pre-existing test still passes except `test_scope_defaults_to_active_and_is_echoed_back` (new shape).

- [ ] **Step 8: Thread the window through `dashboard.py`**

Imports (replace lines 39-41):

```python
from . import ApiError, api_v1, iso
from .auth import require_auth
from .closed_window import ClosedWindow, closed_in_window, parse_closed_window
```

In `_lifecycle_counts`, change the signature and the CLOSED/CANCELLED loop, and append one sentence to the docstring's `mode` paragraph:

```python
def _lifecycle_counts(mode: str, all_trades: list[dict],
                      window: ClosedWindow | None = None) -> dict:
```

docstring, after "...anything else counts only today's.":

```
    v181: with a `window` (`mode=range`) a CLOSED/CANCELLED row counts when
    its terminal time is in the window -- the rule `/trades?closed_from=`
    applies to the same rows, so the strip and the Closed tab still agree.
```

body:

```python
        counts = dict(_plan_rows()["counts"])
        rows = build_rows(all_trades)
        for status in ("CLOSED", "CANCELLED"):
            counts[status] = sum(
                1 for r in rows
                if r["status"] == status and _closed_row_in_scope(r, mode, window))
        return counts
```

Add this helper directly above `_lifecycle_counts`:

```python
def _closed_row_in_scope(row: dict, mode: str, window: ClosedWindow | None) -> bool:
    """Whether a CLOSED/CANCELLED `build_rows` row belongs to the scope.

    The window is checked first, so `range` can never reach the Berlin-day
    `today` flag. `closed_at` on a row is already its terminal time (the
    trade's close, or the cancel transition of an unfilled plan).
    """
    if window is not None:
        return closed_in_window(row.get("closed_at"), window)
    return mode == "all" or bool(row["today"])
```

Replace `_SCOPES` and `_scope()` (lines 142-155) with:

```python
_SCOPES = ("active", "today", "all", "range")


def _scope() -> str:
    """SR58 -- the dashboard's date scope, from `?mode=`.

    The Jinja dashboard's three modes: `active` (today plus anything still
    open, the default), `today`, and `all` -- plus v181's `range`, whose
    window `_parse_range_window` reads. An unknown value is a 400 rather
    than a silent fall back to the default -- a scope that quietly ignores
    what was asked for makes all-time numbers read as today's, which is the
    same class of bug SR52 fixed on the Trades list.
    """
    raw = (request.args.get("mode") or "").strip() or "active"
    if raw not in _SCOPES:
        raise ApiError("invalid", f"mode must be one of {', '.join(_SCOPES)}", 400)
    return raw


def _parse_range_window(mode: str) -> ClosedWindow | None:
    """v181 -- `?from=&to=` for `mode=range`, `None` for every other mode.

    Both bounds required, aware, `from <= to`, else a 400 (`closed_window`).
    The SPA sends whole New York buckets; this side only sees two instants.
    """
    if mode != "range":
        return None
    return parse_closed_window(request.args.get("from"), request.args.get("to"))


def _scope_trades(all_raw: list[dict], mode: str,
                  window: ClosedWindow | None) -> list[dict]:
    """The trades the win-rate/expectancy stats read (`scoped_raw`).

    Every still-open trade (it has no outcome yet to exclude) plus only the
    closes in scope: the window's for `range`, today's (Berlin) for
    `active`/`today`, all of them for `all`. The window is checked first so
    `range` can never fall through to the Berlin day.
    """
    if window is not None:
        return [t for t in all_raw
                if t.get("status") == "open" or closed_in_window(t.get("closed_at"), window)]
    if mode == "all":
        return all_raw
    return [t for t in all_raw
            if t.get("status") == "open" or dash.is_today_berlin(t.get("closed_at"))]
```

Replace `_realized_parts` (lines 157-171) with:

```python
def _realized_parts(trades: list[dict], mode: str,
                    window: ClosedWindow | None = None) -> list[dict]:
    """Every realized part of `trades` -- whole trades and individual legs --
    scoped by the part's OWN close.

    A partial is an individual trade (`expand_realized_legs`): the TP1 leg
    of a runner that is still open counts on the day it banked, and the two
    legs of a position that scaled out today count as two. That is the
    population the Trades table shows as CLOSED rows under it, and the one
    `get_stats` has counted since v79; scoping whole trades by the trade's
    close left this card and its chips a different book from that table.

    v181: a `window` (`mode=range`) wins over `mode`, so `range` never
    reaches the Berlin-day branch.
    """
    parts = [part for t in trades for part in expand_realized_legs(t)]
    if window is not None:
        return [part for part in parts if closed_in_window(part.get("closed_at"), window)]
    if mode == "all":
        return parts
    return [part for part in parts if dash.is_today_berlin(part.get("closed_at"))]
```

Add after `_total_or_none`:

```python
def _scope_echo(mode: str, window: ClosedWindow | None) -> dict:
    """SR58's echo of the applied scope, plus the bounds a `range` was read
    with (UTC ISO) -- null for every other mode."""
    if window is None:
        return {"mode": mode, "from": None, "to": None}
    return {"mode": mode, "from": iso(window.start), "to": iso(window.end)}
```

In `dashboard()`: read the window right after the mode, replace the inline `scoped_raw` block (the comment above it stays, reworded to name `_scope_trades`), and pass `window` to the four consumers and the echo. The changed lines, in order:

```python
    mode = _scope()
    window = _parse_range_window(mode)
    tl = TradeLog()
```

```python
    # win_rate/expectancy_r/payoff_ratio must scope with `mode` the same way
    # `_realized`/`_lifecycle_counts` already do -- see `_scope_trades` for
    # which trades each mode (and v181's range window) keeps.
    scoped_main = [trade for trade in _scope_trades(all_raw, mode, window) if is_main(trade)]
    stats = tl.get_stats(trades=scoped_main)
    stats.update(tl.get_extended_stats(trades=scoped_main))
    from swingbot.core.analytics import metrics as m
    # Each realized leg is its own trade here -- see `_realized_parts`.
    closed_scoped = _realized_parts([t for t in all_raw if is_main(t)], mode, window)
```

```python
        "lifecycle": _lifecycle_counts(mode, all_raw, window),
```

```python
        # SR58 -- the date scope, echoed back so the workspace can label the
        # figures it is showing rather than assume the request applied.
        "scope": _scope_echo(mode, window),
        "realized": _realized(closed_scoped),
        "realized_weak": _realized(
            _realized_parts([t for t in all_raw if is_weak(t)], mode, window)),
```

Nothing else in `dashboard()` changes: `open_trades`, `_risk_used`, `build_open_trade_views` and the balance never read `mode` or `window`.

- [ ] **Step 9: Run both test files to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: PASS, including `test_dashboard_reads_the_trade_log_once` and every pre-existing `mode` test.

Run: `python scripts/dev/testrun.py file tests/admin/test_closed_window.py`
Expected: PASS.

- [ ] **Step 10: Record the complexity after and shrink the baseline**

Run: `python -m radon cc -s swingbot/admin/api_v1/dashboard.py | cat`
Expected: `dashboard - C (17)` (measured on a draft of this exact body while writing the plan); every other function in the file below 15 (`_lifecycle_counts`, `_realized_parts`, `_scope_trades`, `_closed_row_in_scope` each A or B). If `dashboard` reads above 17, a consumer was inlined instead of called — fix the code, never the expectation; it must in any case be below 21.

Run: `python scripts/dev/complexity_gate.py --update`
Then: `git diff scripts/dev/complexity_baseline.json`
Expected: `"swingbot.admin.api_v1.dashboard:dashboard": 21` → `17`. `--update` only lowers scores; any other line it lowers is a real improvement elsewhere and stays.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 11: Commit**

```bash
git add swingbot/admin/api_v1/closed_window.py swingbot/admin/api_v1/dashboard.py tests/admin/test_closed_window.py tests/admin/test_api_v1_dashboard.py scripts/dev/complexity_baseline.json
git commit -m "feat(v181): /dashboard?mode=range -- one closed window through every mode consumer" -m "_scope_trades and _parse_range_window extracted; dashboard() complexity 21 -> 17, baseline shrunk." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V181-11: `/trades?closed_from=&closed_to=` for the Closed tab

**Model:** sonnet — one filter on a legacy complexity-34 handler, applied through a helper so the handler's score does not move; the window rule itself is V181-10's, imported unchanged.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (imports lines 47-48; `FILTERS` lines 63-78; a new constant after `_RANGE_FILTERS` line 112; a new helper after `_in_today_scope` lines 189-205; `list_trades()` the `for key, value in params.filters.items():` line ~870)
- Modify: `tests/admin/test_api_v1_trades.py` (a new section appended at the end; the `admin` suite owns it)

**Interfaces:**
- Consumes (V181-10, `swingbot/admin/api_v1/closed_window.py`): `ClosedWindow`, `parse_closed_window(from_raw, to_raw, *, names=("from", "to")) -> ClosedWindow` (`ApiError("invalid", …, 400)` naming the parameter), `closed_in_window(iso_ts, window) -> bool`. Rows from `build_rows()` carry `status` (plan vocabulary) and `closed_at` (a plan row's terminal time, a leg row's own close, a legacy row's close) — the same fields V181-10's `_closed_row_in_scope` reads for the lifecycle strip.
- Produces (V181-12's `ApiClient.trades()` sends them; V181-14's Closed tab sets them):
  - Query parameters `closed_from` / `closed_to` on `GET /api/v1/trades` — aware ISO timestamps, both or neither (an empty value counts as absent, the collection convention), `[from, to)`; a missing partner, a naive or unreadable bound, or `closed_from > closed_to` is a 400 `invalid` naming the parameter.
  - `trades._in_closed_scope(status: str, closed_at: str | None, window: ClosedWindow) -> bool` — a row not yet CLOSED/CANCELLED stays in, however old (the `_in_today_scope` rule); a terminal row only when its `closed_at` is in the window.
  - `trades._apply_closed_window(rows: list[dict], filters: dict) -> tuple[list[dict], dict]` — the window-filtered rows plus the remaining filters for the generic loop.

**Rules (spec § 6):** the Closed tab must agree with the KPIs over one window, so the rule is V181-10's `closed_in_window`, never a second comparison. `list_trades()` is legacy at complexity **34** (`scripts/dev/complexity_baseline.json`, `swingbot.admin.api_v1.trades:list_trades`); it must not rise, so the window is applied by one helper call before the filter loop rather than by a new `elif` arm.

- [ ] **Step 1: Record the complexity before**

Run: `python -m radon cc -s swingbot/admin/api_v1/trades.py | cat`
Expected: `F 861:0 list_trades - E (34)` and `F 189:0 _in_today_scope - A (2)`. Note the 34.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_api_v1_trades.py`:

```python
# --- v181: closed_from / closed_to (the Closed tab under a range scope) -----
# The Dashboard's range presets and its hand-dragged Range send a `[from, to)`
# window instead of `today`. The rule is `today`'s with the window in place of
# the Berlin day: a row that has not closed yet stays in however old it is,
# and a CLOSED/CANCELLED row counts only when its terminal time is in the
# window -- the same `closed_in_window` `/dashboard?mode=range` counts with,
# so the KPI cards and the table under them cannot disagree.

CLOSED_FROM = "2026-01-05T05:00:00+00:00"   # 00:00 New York, Mon 5 Jan
CLOSED_TO = "2026-01-06T05:00:00+00:00"     # 00:00 New York, Tue 6 Jan
_INSIDE = "2026-01-05T15:00:00+00:00"
_AFTER = "2026-01-07T15:00:00+00:00"


def _windowed(client, *, start=CLOSED_FROM, end=CLOSED_TO, **extra):
    # query_string, never an f-string URL: "+00:00" in a URL decodes to a
    # space and the bound turns naive (a 400).
    return client.get("/api/v1/trades",
                      query_string={"closed_from": start, "closed_to": end, **extra})


def _closed_plan(plan_id, trade_id, closed_at, *, status="win"):
    plan = _plan(plan_id, status="CLOSED")
    trade = _trade(trade_id, plan_id=plan_id, status=status)
    trade["closed_at"] = closed_at
    return plan, trade


def test_closed_window_counts_a_close_at_from_and_drops_one_at_to(seed, logged_in):
    at_from = _closed_plan("11111111-1111-4111-8111-111111111111", "a" * 16, CLOSED_FROM)
    inside = _closed_plan("22222222-2222-4222-8222-222222222222", "b" * 16, _INSIDE)
    at_to = _closed_plan("33333333-3333-4333-8333-333333333333", "c" * 16, CLOSED_TO)
    seed(plans=[at_from[0], inside[0], at_to[0]], trades=[at_from[1], inside[1], at_to[1]])

    items = _windowed(logged_in, status="CLOSED").get_json()["items"]
    assert sorted(r["id"] for r in items) == [at_from[0]["plan_id"], inside[0]["plan_id"]]


@pytest.mark.parametrize("status", ["PENDING", "ACTIVE", "PARTIAL"])
def test_closed_window_keeps_a_still_open_plan_no_matter_how_old(seed, logged_in, status):
    plan = _plan("11111111-1111-4111-8111-111111111111", status=status)
    plan["created_at"] = _OLD_ISO
    seed(plans=[plan])

    items = _windowed(logged_in, status=status).get_json()["items"]
    assert [r["id"] for r in items] == [plan["plan_id"]]


def test_closed_window_scopes_a_cancelled_plan_by_its_status_history(seed, logged_in):
    inside = _plan("11111111-1111-4111-8111-111111111111", status="CANCELLED")
    inside["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": _INSIDE}]
    after = _plan("22222222-2222-4222-8222-222222222222", status="CANCELLED")
    after["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": _AFTER}]
    seed(plans=[inside, after])

    items = _windowed(logged_in, status="CANCELLED").get_json()["items"]
    assert [r["id"] for r in items] == [inside["plan_id"]]


def test_closed_window_scopes_a_legacy_trade_by_when_it_closed(seed, logged_in):
    inside = _trade("aaaaaaaaaaaaaaaa", status="win")
    inside["opened_at"] = _OLD_ISO
    inside["closed_at"] = _INSIDE
    after = _trade("bbbbbbbbbbbbbbbb", status="loss")
    after["closed_at"] = _AFTER
    seed(trades=[inside, after])

    items = _windowed(logged_in, status="CLOSED").get_json()["items"]
    assert [r["id"] for r in items] == ["aaaaaaaaaaaaaaaa"]


def test_closed_window_compares_instants_not_wall_clocks(seed, logged_in):
    """00:30 New York on 5 Jan is 05:30Z -- inside, whatever offset it is written in."""
    plan, trade = _closed_plan("11111111-1111-4111-8111-111111111111", "a" * 16,
                               "2026-01-05T00:30:00-05:00")
    seed(plans=[plan], trades=[trade])
    assert _windowed(logged_in, status="CLOSED").get_json()["total"] == 1


@pytest.mark.parametrize("query, named", [
    ({"closed_from": CLOSED_FROM}, "closed_to"),
    ({"closed_to": CLOSED_TO}, "closed_from"),
    ({"closed_from": "2026-01-05T05:00:00", "closed_to": CLOSED_TO}, "closed_from"),
    ({"closed_from": "last-tuesday", "closed_to": CLOSED_TO}, "closed_from"),
    ({"closed_from": CLOSED_TO, "closed_to": CLOSED_FROM}, "closed_from"),
])
def test_a_bad_closed_window_is_a_400_naming_the_parameter(seed, logged_in, query, named):
    seed()
    resp = logged_in.get("/api/v1/trades", query_string=query)
    assert_error(resp, "invalid", 400)
    assert named in resp.get_json()["error"]["message"]


def test_no_closed_window_leaves_the_list_unfiltered(seed, logged_in):
    old = _closed_plan("11111111-1111-4111-8111-111111111111", "a" * 16, _OLD_ISO)
    seed(plans=[old[0]], trades=[old[1]])
    assert logged_in.get("/api/v1/trades?status=CLOSED").get_json()["total"] == 1


def test_the_closed_tab_agrees_with_the_dashboard_over_one_window(seed, logged_in):
    """Spec § 6 / Testing: the Closed tab filter agrees with the KPIs. The
    dashboard's lifecycle strip and realised count, and this endpoint's
    CLOSED/CANCELLED totals, all over the same `[from, to)` window."""
    closes = [
        _closed_plan("11111111-1111-4111-8111-111111111111", "a" * 16, CLOSED_FROM),
        _closed_plan("22222222-2222-4222-8222-222222222222", "b" * 16, _INSIDE, status="loss"),
        _closed_plan("33333333-3333-4333-8333-333333333333", "c" * 16, CLOSED_TO),
        _closed_plan("44444444-4444-4444-8444-444444444444", "d" * 16, _OLD_ISO),
    ]
    cancelled = _plan("55555555-5555-4555-8555-555555555555", status="CANCELLED")
    cancelled["status_history"] = [{"status": "CANCELLED", "reason": "expired", "at": _INSIDE}]
    still_open = _plan("66666666-6666-4666-8666-666666666666", status="PENDING")
    seed(plans=[p for p, _ in closes] + [cancelled, still_open],
         trades=[t for _, t in closes])

    dashboard = logged_in.get("/api/v1/dashboard", query_string={
        "mode": "range", "from": CLOSED_FROM, "to": CLOSED_TO}).get_json()
    closed_total = _windowed(logged_in, status="CLOSED").get_json()["total"]
    cancelled_total = _windowed(logged_in, status="CANCELLED").get_json()["total"]

    assert closed_total == 2
    assert dashboard["lifecycle"]["CLOSED"] == closed_total
    assert dashboard["lifecycle"]["CANCELLED"] == cancelled_total == 1
    assert dashboard["realized"]["n"] == closed_total


def test_in_closed_scope_keeps_open_rows_and_windows_terminal_ones():
    from datetime import datetime, timezone

    from swingbot.admin.api_v1.closed_window import ClosedWindow
    from swingbot.admin.api_v1.trades import _in_closed_scope

    window = ClosedWindow(datetime(2026, 1, 5, 5, tzinfo=timezone.utc),
                          datetime(2026, 1, 6, 5, tzinfo=timezone.utc))
    assert _in_closed_scope("ACTIVE", None, window)
    assert _in_closed_scope("PENDING", _OLD_ISO, window)
    assert _in_closed_scope("CLOSED", _INSIDE, window)
    assert not _in_closed_scope("CLOSED", _AFTER, window)
    assert not _in_closed_scope("CANCELLED", None, window)
```

If `dashboard["realized"]["n"]` reads 0 in the agreement test, the seeded `_trade` rows are missing a field `expand_realized_legs` needs: compare with `_closed()` in `tests/admin/test_api_v1_dashboard.py` (~line 419) and add that field to `_closed_plan`'s trade — never drop the assertion.

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — every windowed request gets `400 unknown parameter 'closed_from'`, so the 200-path tests fail and the 400-naming tests fail on the message (it names an unknown parameter, not a missing bound); `_in_closed_scope` cannot be imported. Every pre-existing test still passes.

- [ ] **Step 4: Implement the filter**

Imports (replace lines 47-48):

```python
from . import api_v1, collection, error, parse_collection_params, ApiError
from .auth import require_auth
from .closed_window import ClosedWindow, closed_in_window, parse_closed_window
```

In `FILTERS`, extend the last entry (keep its comment) so the set ends:

```python
                     # v85 R6-01: date range filters on opened_at
                     "opened_from", "opened_to",
                     # v181: the Dashboard's range scope on the Closed tab --
                     # see `_apply_closed_window`.
                     "closed_from", "closed_to"})
```

After `_RANGE_FILTERS = {"opened_from", "opened_to"}`:

```python
# v181. The `[from, to)` closed window, as a pair. Applied by
# `_apply_closed_window` before the per-key loop in `list_trades`, never by
# that loop: each bound alone is meaningless, and `list_trades` is legacy at
# complexity 34 -- a new arm there would raise it.
_CLOSED_WINDOW_FILTERS = ("closed_from", "closed_to")
```

After `_in_today_scope`:

```python
def _in_closed_scope(status: str, closed_at: str | None, window: ClosedWindow) -> bool:
    """`_in_today_scope` with a `[from, to)` window in place of the Berlin day.

    A row that has not closed yet stays in however old it is; a CLOSED or
    CANCELLED row counts when its terminal time is in the window. The test is
    `closed_in_window`, the one `/dashboard?mode=range` counts with (v181), so
    the Closed tab and the KPI cards above it cannot disagree.
    """
    return status not in _TERMINAL or closed_in_window(closed_at, window)


def _apply_closed_window(rows: list[dict], filters: dict) -> tuple[list[dict], dict]:
    """Apply `closed_from`/`closed_to` and hand back the other filters.

    Neither present: rows and filters unchanged. One present (an empty value
    is already absent, the collection convention): `parse_closed_window`
    400s naming the missing one -- as it does for a naive, unreadable or
    reversed bound.
    """
    rest = {k: v for k, v in filters.items() if k not in _CLOSED_WINDOW_FILTERS}
    if len(rest) == len(filters):
        return rows, filters
    window = parse_closed_window(filters.get("closed_from"), filters.get("closed_to"),
                                 names=_CLOSED_WINDOW_FILTERS)
    kept = [r for r in rows if _in_closed_scope(r.get("status"), r.get("closed_at"), window)]
    return kept, rest
```

In `list_trades()`, replace the loop header

```python
    for key, value in params.filters.items():
```

with

```python
    rows, filters = _apply_closed_window(rows, params.filters)
    for key, value in filters.items():
```

Nothing else in `list_trades()` changes.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: PASS, including every pre-existing `today` and `opened_from` test.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py`
Expected: PASS (untouched by this task; it is the other half of the agreement).

- [ ] **Step 6: Record the complexity after**

Run: `python -m radon cc -s swingbot/admin/api_v1/trades.py | cat`
Expected: `list_trades - E (34)` (unchanged: a call replaced an expression, no branch added); `_in_closed_scope - A (2)`, `_apply_closed_window - A (2)`.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0. No `--update`: nothing in `trades.py` went down.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trades.py
git commit -m "feat(v181): /trades closed_from/closed_to -- the Closed tab follows a range scope" -m "Same [from, to) rule as /dashboard?mode=range (closed_window); list_trades complexity unchanged at 34." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — Range scope: client model and store

### Task V181-12: Presets, scope request mapping, the preset preference, client params

**Model:** sonnet — pure date arithmetic on the New York clock with DST and month-end edges, plus additive client types; every rule is a unit test.

**Files:**
- Modify: `frontend/src/app/ui/equity-chart-prefs.ts` + `equity-chart-prefs.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts` + `equity-range.model.spec.ts` (append; imports extended)
- Modify: `frontend/src/app/api/models.ts` (`Dashboard.scope` ~line 392, `DashboardScope` ~line 411, `TradeQuery` lines 320-353)
- Modify: `frontend/src/app/api/api-client.ts` (`dashboard()` lines 129-136, `trades()` lines 140-153) + `api-client.spec.ts` (a new `describe` appended)

**Interfaces:**
- Consumes (V181-2, same file): `TimeWindow`, `nyMidnight(isoDate)`, and the module-private `NY_PARTS` and `addDays(isoDate, days)` — reused in place, not redefined. V181-10/V181-11's wire contract: `/dashboard?mode=range&from=&to=`, `/trades?closed_from=&closed_to=`.
- Produces (V181-13's store, V181-14's controls and V181-15's link consume these):
  - `equity-chart-prefs.ts`: `type ScopePreset = '1D' | '5D' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | 'All'`; `SCOPE_PRESETS: readonly ScopePreset[]` (control order); `SCOPE_PRESET_KEY = 'dashboard.scope.preset'`; `DEFAULT_SCOPE_PRESET: ScopePreset = '1D'`; `readScopePreset(prefs: Preferences): ScopePreset` (tolerant, default `'1D'`); `writeScopePreset(prefs: Preferences, preset: ScopePreset): Preferences` (pure, like `writeEquityChartPrefs`; the store calls it through `PreferencesStore.update`).
  - `equity-range.model.ts`: re-exports `ScopePreset` and `SCOPE_PRESETS`; `type ScopeSelection = { kind: 'preset'; preset: ScopePreset } | { kind: 'range'; window: TimeWindow }`; `interface ChartTarget { window: TimeWindow | null; seq: number }` (null window = all history); `type RollingPreset = Exclude<ScopePreset, '1D' | 'All'>`; `presetBounds(preset: RollingPreset, now: Date): TimeWindow`; `chartWindowFor(preset: ScopePreset, now: Date): TimeWindow | null`; `scopeToRequest(scope: ScopeSelection, now: Date): { mode: DashboardScope; window: TimeWindow | null }`; `rangeChipLabel(window: TimeWindow): string`; `showsNowLabel(scope: ScopeSelection): boolean`.
  - `models.ts`: `DashboardScope` gains `'range'`; `Dashboard.scope` is `{ mode: DashboardScope; from?: string | null; to?: string | null }`; `TradeQuery` gains `closedFrom?: string | null; closedTo?: string | null`.
  - `ApiClient.dashboard(mode?: DashboardScope, window?: TimeWindow | null)` sends `from`/`to` only with a window; `ApiClient.trades()` maps `closedFrom`/`closedTo` to `closed_from`/`closed_to`, dropping a null or empty bound.

**Rules (spec § 6):** preset `from` = 00:00 New York on the day the preset reaches back to; `to` = the next New York midnight after `now` (the end of the current 1D bucket), so the window moves only when a New York day opens. Reach-back per preset: **5D** the fifth weekday counting today when today is one (weekends skipped; holidays are not known on this side and simply hold no candle); **1M / 3M / 6M / 1Y** the same calendar day 1 / 3 / 6 / 12 months back, clamped to that month's last day; **YTD** 1 Jan of the New York year. 1D → `mode=today` (the Berlin day, unchanged), All → `mode=all`; the chart's 1D window is the New York day. A Range chip reads `3 Sep – 18 Oct` (New York dates, `to` exclusive; years shown only when the two differ).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/ui/equity-chart-prefs.spec.ts`, adding `SCOPE_PRESETS, SCOPE_PRESET_KEY, readScopePreset, writeScopePreset` to its import list:

```ts
describe('scope preset preference (v181)', () => {
  it('lists the presets in control order', () => {
    expect(SCOPE_PRESETS).toEqual(['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', 'All']);
    expect(SCOPE_PRESET_KEY).toBe('dashboard.scope.preset');
  });

  it('defaults to 1D, reads a stored preset, and falls back on anything else', () => {
    expect(readScopePreset({})).toBe('1D');
    expect(readScopePreset(undefined as never)).toBe('1D');
    expect(readScopePreset({ 'dashboard.scope.preset': '3M' })).toBe('3M');
    expect(readScopePreset({ 'dashboard.scope.preset': '2W' })).toBe('1D');
    expect(readScopePreset({ 'dashboard.scope.preset': 7 })).toBe('1D');
    // Range is never a stored value (spec § 1): it reads as the default.
    expect(readScopePreset({ 'dashboard.scope.preset': 'Range' })).toBe('1D');
  });

  it('writes the key, leaves every other key alone, and never writes a bad value', () => {
    const next = writeScopePreset({ 'dashboard.equity.tf': '4H' }, 'YTD');
    expect(next).toEqual({ 'dashboard.equity.tf': '4H', 'dashboard.scope.preset': 'YTD' });
    expect(writeScopePreset({}, 'bogus' as never)[SCOPE_PRESET_KEY]).toBe('1D');
  });
});
```

Append to `equity-range.model.spec.ts`, adding `SCOPE_PRESETS, ScopeSelection, chartWindowFor, presetBounds, rangeChipLabel, scopeToRequest, showsNowLabel` to its import list from `./equity-range.model`:

```ts
describe('scope presets (§ 1, § 6)', () => {
  const at = (s: string) => new Date(s);
  /** New York wall clock of an ISO instant, `YYYY-MM-DD HH:mm`. */
  const nyWall = (s: string) => new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(s)).replace(',', '');

  // Wed 21 Oct 2026, 10:00 in New York.
  const NOW = at('2026-10-21T14:00:00Z');

  it('re-exports the presets from the prefs module', () => {
    expect(SCOPE_PRESETS).toHaveLength(8);
  });

  it('reaches back per preset, to 00:00 New York, and ends at the next New York midnight', () => {
    const to = '2026-10-22T04:00:00.000Z';
    expect(presetBounds('5D', NOW)).toEqual({ from: '2026-10-15T04:00:00.000Z', to });
    expect(presetBounds('1M', NOW)).toEqual({ from: '2026-09-21T04:00:00.000Z', to });
    expect(presetBounds('3M', NOW)).toEqual({ from: '2026-07-21T04:00:00.000Z', to });
    expect(presetBounds('6M', NOW)).toEqual({ from: '2026-04-21T04:00:00.000Z', to });
    expect(presetBounds('YTD', NOW)).toEqual({ from: '2026-01-01T05:00:00.000Z', to });
    expect(presetBounds('1Y', NOW)).toEqual({ from: '2025-10-21T04:00:00.000Z', to });
  });

  it('puts every bound on a New York midnight, across both DST changeovers', () => {
    const nows = ['2026-03-09T15:00:00Z', '2026-11-02T15:00:00Z', '2026-01-01T12:00:00Z', NOW.toISOString()];
    for (const now of nows) {
      for (const preset of ['5D', '1M', '3M', '6M', 'YTD', '1Y'] as const) {
        const { from, to } = presetBounds(preset, at(now));
        expect(nyWall(from).endsWith('00:00')).toBe(true);
        expect(nyWall(to).endsWith('00:00')).toBe(true);
      }
    }
    // Monday after the November fall-back: from is EDT, to is EST.
    expect(presetBounds('5D', at('2026-11-02T15:00:00Z')))
      .toEqual({ from: '2026-10-27T04:00:00.000Z', to: '2026-11-03T05:00:00.000Z' });
    // Monday after the March spring-forward: from is EST, to is EDT.
    expect(presetBounds('1M', at('2026-03-09T15:00:00Z')))
      .toEqual({ from: '2026-02-09T05:00:00.000Z', to: '2026-03-10T04:00:00.000Z' });
  });

  it('skips the weekend for 5D', () => {
    // Sun 25 Oct: the five weekdays are Fri 23 back to Mon 19.
    expect(presetBounds('5D', at('2026-10-25T15:00:00Z')).from).toBe('2026-10-19T04:00:00.000Z');
  });

  it('clamps a month back to the shorter month', () => {
    expect(presetBounds('1M', at('2026-03-31T15:00:00Z')).from).toBe('2026-02-28T05:00:00.000Z');
  });

  it('reads YTD on the New York calendar, 1 Jan included', () => {
    // 07:00 New York on 1 Jan: the year just began.
    expect(presetBounds('YTD', at('2026-01-01T12:00:00Z')))
      .toEqual({ from: '2026-01-01T05:00:00.000Z', to: '2026-01-02T05:00:00.000Z' });
    // 22:00 New York on 31 Dec (already 1 Jan in Berlin): still last year.
    expect(presetBounds('YTD', at('2026-01-01T03:00:00Z')))
      .toEqual({ from: '2025-01-01T05:00:00.000Z', to: '2026-01-01T05:00:00.000Z' });
  });

  it('keeps `to` stable within a New York day and moves it when the next one opens', () => {
    const to = (s: string) => presetBounds('3M', at(s)).to;
    expect(to('2026-10-21T04:00:00Z')).toBe('2026-10-22T04:00:00.000Z');
    expect(to('2026-10-22T03:59:59Z')).toBe('2026-10-22T04:00:00.000Z');
    expect(to('2026-10-22T04:00:00Z')).toBe('2026-10-23T04:00:00.000Z');
  });

  it('gives the chart today’s New York day for 1D, all history for All, the bounds otherwise', () => {
    expect(chartWindowFor('1D', NOW))
      .toEqual({ from: '2026-10-21T04:00:00.000Z', to: '2026-10-22T04:00:00.000Z' });
    expect(chartWindowFor('All', NOW)).toBeNull();
    expect(chartWindowFor('6M', NOW)).toEqual(presetBounds('6M', NOW));
  });

  it('maps a scope to its request: 1D stays the Berlin today, All is all, the rest are ranges', () => {
    const preset = (p: '1D' | 'All' | '3M'): ScopeSelection => ({ kind: 'preset', preset: p });
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    expect(scopeToRequest(preset('1D'), NOW)).toEqual({ mode: 'today', window: null });
    expect(scopeToRequest(preset('All'), NOW)).toEqual({ mode: 'all', window: null });
    expect(scopeToRequest(preset('3M'), NOW)).toEqual({ mode: 'range', window: presetBounds('3M', NOW) });
    expect(scopeToRequest({ kind: 'range', window }, NOW)).toEqual({ mode: 'range', window });
  });

  it('labels a Range chip with its New York dates, `to` exclusive', () => {
    expect(rangeChipLabel({ from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' }))
      .toBe('3 Sep – 18 Oct');
    expect(rangeChipLabel({ from: '2025-12-29T05:00:00.000Z', to: '2026-01-03T05:00:00.000Z' }))
      .toBe('29 Dec 2025 – 2 Jan 2026');
    expect(rangeChipLabel({ from: '2026-10-16T04:00:00.000Z', to: '2026-10-17T04:00:00.000Z' }))
      .toBe('16 Oct');
    // Four 1H candles inside one day, and an empty window.
    expect(rangeChipLabel({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T18:00:00.000Z' }))
      .toBe('16 Oct');
    expect(rangeChipLabel({ from: '2026-10-16T14:00:00.000Z', to: '2026-10-16T14:00:00.000Z' }))
      .toBe('16 Oct');
  });

  it('shows the "now" sub-label everywhere but 1D', () => {
    expect(showsNowLabel({ kind: 'preset', preset: '1D' })).toBe(false);
    expect(showsNowLabel({ kind: 'preset', preset: '5D' })).toBe(true);
    expect(showsNowLabel({ kind: 'preset', preset: 'All' })).toBe(true);
    expect(showsNowLabel({ kind: 'range', window: { from: 'a', to: 'b' } })).toBe(true);
  });
});
```

Append to `frontend/src/app/api/api-client.spec.ts` (a third `describe`, same `beforeEach` as the two above it):

```ts
describe('ApiClient — dashboard range scope (v181)', () => {
  let api: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    api = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  const WINDOW = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };

  it('sends from/to on the dashboard only with a window', () => {
    api.dashboard('today').subscribe();
    const plain = http.expectOne((r) => r.url.endsWith('/api/v1/dashboard'));
    expect(plain.request.params.get('mode')).toBe('today');
    expect(plain.request.params.has('from')).toBe(false);
    expect(plain.request.params.has('to')).toBe(false);
    plain.flush({});

    api.dashboard('range', WINDOW).subscribe();
    const ranged = http.expectOne((r) => r.url.endsWith('/api/v1/dashboard'));
    expect(ranged.request.params.get('mode')).toBe('range');
    expect(ranged.request.params.get('from')).toBe(WINDOW.from);
    expect(ranged.request.params.get('to')).toBe(WINDOW.to);
    ranged.flush({});
  });

  it('maps closedFrom/closedTo to closed_from/closed_to, and drops a null bound', () => {
    api.trades({ status: 'CLOSED', closedFrom: WINDOW.from, closedTo: WINDOW.to }).subscribe();
    const windowed = http.expectOne((r) => r.url.endsWith('/api/v1/trades'));
    expect(windowed.request.params.get('closed_from')).toBe(WINDOW.from);
    expect(windowed.request.params.get('closed_to')).toBe(WINDOW.to);
    expect(windowed.request.params.has('closedFrom')).toBe(false);
    windowed.flush({ items: [], total: 0, page: 1, per_page: 25 });

    api.trades({ status: 'CLOSED', closedFrom: null, closedTo: null }).subscribe();
    const plain = http.expectOne((r) => r.url.endsWith('/api/v1/trades'));
    expect(plain.request.params.has('closed_from')).toBe(false);
    expect(plain.request.params.has('closed_to')).toBe(false);
    plain.flush({ items: [], total: 0, page: 1, per_page: 25 });
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx ng test --include src/app/ui/equity-chart-prefs.spec.ts --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --include src/app/api/api-client.spec.ts --watch=false`
Expected: FAIL — `readScopePreset`, `presetBounds` and the rest are not exported; the dashboard request carries no `from`; `trades()` sends `closedFrom` as-is.

- [ ] **Step 3: Add the preference**

Append to `frontend/src/app/ui/equity-chart-prefs.ts`:

```ts
/* -- v181: the Dashboard's scope preset ----------------------------------- */

/** The scope control's presets, in control order (spec v181 § 1). Defined
 *  here, beside the timeframes, because `equity-range.model.ts` imports from
 *  this module -- the model re-exports both, and consumers import them from
 *  there. An ad-hoc Range is not a preset and is never stored. */
export type ScopePreset = '1D' | '5D' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | 'All';
export const SCOPE_PRESETS: readonly ScopePreset[] = ['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', 'All'];

export const SCOPE_PRESET_KEY = 'dashboard.scope.preset';

/** 1D: what the Today toggle showed before v181. */
export const DEFAULT_SCOPE_PRESET: ScopePreset = '1D';

export function readScopePreset(prefs: Preferences): ScopePreset {
  return pick(prefs?.[SCOPE_PRESET_KEY], SCOPE_PRESETS, DEFAULT_SCOPE_PRESET);
}

export function writeScopePreset(prefs: Preferences, preset: ScopePreset): Preferences {
  // Normalised through the reader, so a bad value is never persisted.
  return { ...prefs, [SCOPE_PRESET_KEY]: readScopePreset({ [SCOPE_PRESET_KEY]: preset }) };
}
```

- [ ] **Step 4: Add the presets to the model**

In `equity-range.model.ts`, change the first two imports to:

```ts
import { DashboardScope, EquityCandle, EquityTimeframe } from '../../../api/models';
import { EQUITY_TIMEFRAMES, type ScopePreset } from '../../../ui/equity-chart-prefs';
```

and add directly below the imports:

```ts
export { SCOPE_PRESETS, type ScopePreset } from '../../../ui/equity-chart-prefs';
```

Append:

```ts
/* -- scope presets (§ 1, § 6) --------------------------------------------- */

/** What the panel is scoped to: a preset, or the window the partner dragged
 *  or zoomed to by hand. Only a preset is ever persisted. */
export type ScopeSelection =
  | { kind: 'preset'; preset: ScopePreset }
  | { kind: 'range'; window: TimeWindow };

/** A programmatic chart move. `window` null = all history; `seq` changes on
 *  every request, so asking for the same window twice still moves. */
export interface ChartTarget {
  window: TimeWindow | null;
  seq: number;
}

/** The presets that become a `mode=range` window. */
export type RollingPreset = Exclude<ScopePreset, '1D' | 'All'>;

/** `instant`'s New York calendar date, `YYYY-MM-DD`. */
function nyDate(instant: Date): string {
  const parts: Record<string, string> = {};
  for (const p of NY_PARTS.formatToParts(instant)) parts[p.type] = p.value;
  return `${parts['year']}-${parts['month']}-${parts['day']}`;
}

/** The same calendar day `months` away, clamped to that month's last day. */
function addMonths(isoDate: string, months: number): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  const lastDay = new Date(Date.UTC(y, m + months, 0)).getUTCDate();
  return new Date(Date.UTC(y, m - 1 + months, Math.min(d, lastDay))).toISOString().slice(0, 10);
}

/** The fifth weekday counting `today` when it is one. Holidays are not known
 *  here; one simply holds no candle. */
function fiveWeekdaysBack(today: string): string {
  let day = today;
  let seen = 0;
  for (;;) {
    const weekday = new Date(`${day}T12:00:00Z`).getUTCDay();
    if (weekday !== 0 && weekday !== 6) seen += 1;
    if (seen === 5) return day;
    day = addDays(day, -1);
  }
}

const PRESET_START: Record<RollingPreset, (today: string) => string> = {
  '5D': fiveWeekdaysBack,
  '1M': (today) => addMonths(today, -1),
  '3M': (today) => addMonths(today, -3),
  '6M': (today) => addMonths(today, -6),
  'YTD': (today) => `${today.slice(0, 4)}-01-01`,
  '1Y': (today) => addMonths(today, -12),
};

/** 00:00 New York of today and of tomorrow: the current 1D bucket. */
function nyDayWindow(now: Date): TimeWindow {
  const today = nyDate(now);
  return {
    from: nyMidnight(today).toISOString(),
    to: nyMidnight(addDays(today, 1)).toISOString(),
  };
}

/** A rolling preset's `[from, to)`: from 00:00 New York on the day it
 *  reaches back to, to the next New York midnight -- the end of the current
 *  1D bucket, also a 1H/4H edge -- so the KPIs move only when a day opens. */
export function presetBounds(preset: RollingPreset, now: Date): TimeWindow {
  return {
    from: nyMidnight(PRESET_START[preset](nyDate(now))).toISOString(),
    to: nyDayWindow(now).to,
  };
}

/** Where a preset moves the chart. 1D is the New York day (its KPIs stay the
 *  Berlin day, spec § 6); All is all history (null). */
export function chartWindowFor(preset: ScopePreset, now: Date): TimeWindow | null {
  if (preset === 'All') return null;
  return preset === '1D' ? nyDayWindow(now) : presetBounds(preset, now);
}

/** The `/dashboard` request for a scope: 1D -> `today`, All -> `all`, every
 *  other preset and a Range -> `range` with its window. */
export function scopeToRequest(
  scope: ScopeSelection,
  now: Date,
): { mode: DashboardScope; window: TimeWindow | null } {
  if (scope.kind === 'range') return { mode: 'range', window: scope.window };
  if (scope.preset === '1D') return { mode: 'today', window: null };
  if (scope.preset === 'All') return { mode: 'all', window: null };
  return { mode: 'range', window: presetBounds(scope.preset, now) };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function dayLabel(isoDate: string, withYear: boolean): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return withYear ? `${d} ${MONTHS[m - 1]} ${y}` : `${d} ${MONTHS[m - 1]}`;
}

/** The Range chip: first and last New York day of the window (`to` is
 *  exclusive), `3 Sep – 18 Oct`; the year only when the two differ. */
export function rangeChipLabel(window: TimeWindow): string {
  const first = nyDate(new Date(window.from));
  const last = nyDate(new Date(Math.max(Date.parse(window.from), Date.parse(window.to) - 1)));
  if (last === first) return dayLabel(first, false);
  const withYear = first.slice(0, 4) !== last.slice(0, 4);
  return `${dayLabel(first, withYear)} – ${dayLabel(last, withYear)}`;
}

/** Point-in-time cards (Open P&L, Open trades, Risk used) say "now" under
 *  every scope but 1D, where "today" and "now" coincide. */
export function showsNowLabel(scope: ScopeSelection): boolean {
  return !(scope.kind === 'preset' && scope.preset === '1D');
}
```

- [ ] **Step 5: Widen the client types and send the parameters**

In `frontend/src/app/api/models.ts`, replace the `DashboardScope` type and its comment:

```ts
/** The Jinja dashboard's three date scopes -- `active` (today plus anything
 *  still open), `today`, `all` -- plus v181's `range`, which carries a
 *  `[from, to)` window of aware ISO instants. */
export type DashboardScope = 'active' | 'today' | 'all' | 'range';
```

and the `scope` field of `Dashboard`:

```ts
  /** SR58 — the date scope the server actually applied, echoed back. v181:
   *  `from`/`to` are the window a `range` was read with (UTC ISO), null for
   *  every other mode. */
  scope: { mode: DashboardScope; from?: string | null; to?: string | null };
```

In `TradeQuery`, after `openedTo?: string | null;`:

```ts
  /** v181. The Closed tab's `[from, to)` window under a range scope -- aware
   *  ISO instants, both or neither, sent in place of `today`. Mapped to
   *  `closed_from`/`closed_to` by `ApiClient`; a null bound is left off. */
  closedFrom?: string | null;
  closedTo?: string | null;
```

In `frontend/src/app/api/api-client.ts`, add `TimeWindow` to the imports:

```ts
import type { TimeWindow } from '../workspaces/dashboard/panels/equity-range.model';
```

and replace `dashboard()` and `trades()`:

```ts
  /** SR58 — the scope is a query parameter, so the server does the date
   *  filtering. A client-side scope over an all-time payload could not
   *  narrow the realised figures at all. v181: a `range` sends its window. */
  dashboard(mode?: DashboardScope, window?: TimeWindow | null): Observable<Dashboard> {
    let params = new HttpParams();
    if (mode) params = params.set('mode', mode);
    if (window) params = params.set('from', window.from).set('to', window.to);
    return this.http.get<Dashboard>(`${this.base}/dashboard`, { params });
  }
```

```ts
  trades(query: TradeQuery = {}): Observable<TradeCollection> {
    const { openedFrom, openedTo, closedFrom, closedTo, ...rest } = query;
    let params = toParams(rest);
    if (openedFrom) params = params.set('opened_from', openedFrom);
    if (openedTo) params = params.set('opened_to', openedTo);
    if (closedFrom) params = params.set('closed_from', closedFrom);
    if (closedTo) params = params.set('closed_to', closedTo);
    return this.http.get<TradeCollection>(`${this.base}/trades`, {
      params,
    });
  }
```

and extend `trades()`'s doc comment's first line to name the new pair: `` `openedFrom`/`openedTo` (and v181's `closedFrom`/`closedTo`) are handled here ``.

`import type` keeps the API layer free of a runtime import from a panel; if the lint config forbids `api/` importing from `workspaces/`, declare `TimeWindow` in `models.ts` instead and have `equity-range.model.ts` re-export it — the shape is identical and every consumer keeps importing it from the model.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx ng test --include src/app/ui/equity-chart-prefs.spec.ts --include src/app/workspaces/dashboard/panels/equity-range.model.spec.ts --include src/app/api/api-client.spec.ts --watch=false`
Expected: PASS, every earlier `describe` in the three files still green.

Run: `cd frontend && npx ng test --include src/app/stores/dashboard.store.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --watch=false`
Expected: PASS (the widened types change nothing they read).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/equity-chart-prefs.ts frontend/src/app/ui/equity-chart-prefs.spec.ts frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts frontend/src/app/workspaces/dashboard/panels/equity-range.model.spec.ts frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts
git commit -m "feat(v181): scope presets on the New York clock, the preset preference, range client params" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

