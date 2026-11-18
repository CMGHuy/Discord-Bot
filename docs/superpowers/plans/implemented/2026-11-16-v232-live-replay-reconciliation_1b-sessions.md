# v232 — Live versus replay reconciliation: Part 1b, sessions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-5" -A 400 <this file>`).

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) — its `## Clarifications from the code brief` are binding.
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger (every cross-task name and signature) and `## Handoff` live there; every task below implicitly includes the Global Constraints.

Part 1 continued: V232-5 belongs to part 1 (ledger), but `_1-foundations.md` reached 1353 lines after V232-4b and a task is never split across files, so it sits here alone. It is parallel to V232-1..V232-4b (disjoint files); it and V232-4 both create `scripts/reports/reconcile/__init__.py` only if it is absent, with the identical content given below.

---

# Phase 1 — Foundations (continued)

### Task V232-5: Package, sessions and the ignore rule

**Model:** sonnet — small pure time helpers on the existing NYSE calendar with every boundary pinned by tests; one ignore line.

**Files:**
- Create: `scripts/reports/reconcile/__init__.py` **only if absent** (V232-4 creates the identical file)
- Create: `scripts/reports/reconcile/sessions.py`
- Create: `tests/scout/test_reconcile_sessions.py` (suite `scout`)
- Modify: `.gitignore` (append two lines at the end)
- Create: `tests/scout/test_reconcile_ignored.py` (suite `scout`)

**Interfaces:**
- Consumes: existing `swingbot/core/market/session.py`: `US_MARKET_TZ`, `RTH_OPEN`, `session_close(d)`, `nyse_calendar()` (`SessionCalendar.is_session`, `session_after(d, 0)` = the session on or before `d`, `position_on_or_before`). Nothing from other v232 tasks.
- Produces (ledger contract, consumed by V232-6 `records`, V232-8 `tags`, V232-9 `layer1_run`, V232-10 `layer2`):
  - package docstring `"""v232: live versus replay reconciliation (scripts/reports/live_replay_reconcile.py)."""` and `WORK_DIR = Path("data/v232")`; `.gitignore` line `data/v232/`.
  - `sessions.to_utc(value: str | dt.datetime) -> dt.datetime` — aware UTC. Accepts ISO with `Z`, `+00:00`, a bare `+00` (Postgres text) or a space separator; a naive value is read as UTC (the stores write UTC wall clock); a date-only string raises `ValueError`.
  - `ny_time(stamp) -> dt.datetime` — aware `America/New_York`.
  - `issue_session(stamp) -> dt.date` — the latest NYSE regular session whose 09:30 ET open is at or before the stamp (pre-open: the previous session; after the close: that day's; weekend or holiday: the last session before it).
  - `stamp_source(plan_doc: dict) -> tuple[dt.datetime, str]` — `(to_utc(issued_at), "issued_at")` when the doc has a non-empty `issued_at`, else `(the close of the created_at session, "created_at")`; neither: `ValueError`.
  - `ISSUE_BUCKETS = ("open_to_1030", "mid_day", "last_hour", "outside_session")`; `issue_bucket(stamp) -> str`.
  - `in_regular_session(stamp) -> bool` (holiday- and early-close-aware); `minutes_after_open(stamp) -> float | None` (None outside the regular session).
  - `sessions_apart(a: dt.date, b: dt.date) -> int` — signed session count from `a` to `b` (`b` later: positive).

**Rules this task freezes:**
- `open_to_1030` = `[09:30, 10:30)` ET; `last_hour` = `[close − 60 min, close)` with `close = session_close(d)` (13:00 on an early close, so its last hour is 12:00-13:00); `mid_day` = the rest of the regular session; `outside_session` = anything outside `[09:30, close)` or on a non-session day.
- A plan doc's `created_at` is the creating bar's **date** (`plan_types.py:123-124`: "created_at is a DATE"), with no time of day. `stamp_source` maps it to that session's close instant, so `issue_session` returns the bar's own session (the backtest's signal bar). Its `issue_bucket` is `outside_session` by construction; **consumers must split buckets by stamp source** (V232-10 counts `created_at`-sourced live-only plans apart, never as an outside-session issue). A full ISO `created_at` (should one exist) goes through `to_utc`.
- All zone work in Python `zoneinfo`; nothing reads `TZ` or the process clock.

**Traps:** brief T8 — the 2026-11-01 fall-back (EDT UTC-4 → EST UTC-5): the same UTC minute 13:31Z is 09:31 ET on Fri 2026-10-30 and 08:31 ET on Mon 2026-11-02. Thanksgiving Thu 2026-11-26 is a holiday; Fri 2026-11-27 closes at 13:00. `override_fidelity.assign_session` maps a pre-open time to the same day and is not reused (spec clarification 4).

- [ ] **Step 1: Write the failing tests**

Create `tests/scout/test_reconcile_sessions.py`:

```python
"""v232: UTC stamps to NYSE sessions, issue-time buckets, stamp sources."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
import reconcile  # noqa: E402
from reconcile import sessions  # noqa: E402

D = dt.date


def test_the_package_names_its_git_ignored_work_dir():
    assert reconcile.WORK_DIR == Path("data/v232")
    assert "live_replay_reconcile.py" in reconcile.__doc__


@pytest.mark.parametrize("text", ["2026-09-15T08:54:50Z", "2026-09-15T08:54:50+00:00",
                                  "2026-09-15 08:54:50+00", "2026-09-15T04:54:50-04:00",
                                  "2026-09-15T08:54:50"])
def test_to_utc_reads_every_stored_form(text):
    assert sessions.to_utc(text) == dt.datetime(2026, 9, 15, 8, 54, 50, tzinfo=dt.timezone.utc)


def test_to_utc_keeps_microseconds_and_converts_aware_datetimes():
    got = sessions.to_utc("2026-03-02T14:35:10.123456+00:00")
    assert got.microsecond == 123456
    et = dt.datetime(2026, 11, 2, 9, 31, tzinfo=sessions.session.US_MARKET_TZ)
    assert sessions.to_utc(et) == dt.datetime(2026, 11, 2, 14, 31, tzinfo=dt.timezone.utc)


def test_to_utc_refuses_a_bare_date():
    with pytest.raises(ValueError, match="date"):
        sessions.to_utc("2026-09-15")


def test_ny_time_follows_the_clock_change():
    assert sessions.ny_time("2026-10-30T13:31:00Z").strftime("%H:%M %Z") == "09:31 EDT"
    assert sessions.ny_time("2026-11-02T13:31:00Z").strftime("%H:%M %Z") == "08:31 EST"


@pytest.mark.parametrize("stamp, session_day", [
    ("2026-10-30T13:31:00Z", D(2026, 10, 30)),   # 09:31 EDT: after the open
    ("2026-11-02T13:31:00Z", D(2026, 10, 30)),   # 08:31 EST: pre-open -> previous session
    ("2026-11-02T14:29:59Z", D(2026, 10, 30)),   # 09:29:59 EST
    ("2026-11-02T14:30:00Z", D(2026, 11, 2)),    # 09:30 EST exactly: the open
    ("2026-10-31T15:00:00Z", D(2026, 10, 30)),   # Saturday
    ("2026-11-01T18:00:00Z", D(2026, 10, 30)),   # Sunday, the clock-change day
    ("2026-11-10T22:00:00Z", D(2026, 11, 10)),   # 17:00 EST: after the close
    ("2026-11-11T02:00:00Z", D(2026, 11, 10)),   # 21:00 EST the evening before, UTC next day
    ("2026-11-26T16:00:00Z", D(2026, 11, 25)),   # Thanksgiving
    ("2026-11-27T19:00:00Z", D(2026, 11, 27)),   # 14:00 EST, after the 13:00 early close
])
def test_issue_session(stamp, session_day):
    assert sessions.issue_session(stamp) == session_day


@pytest.mark.parametrize("stamp, inside", [
    ("2026-11-10T14:30:00Z", True), ("2026-11-10T20:59:59Z", True),
    ("2026-11-10T21:00:00Z", False), ("2026-11-10T14:29:00Z", False),
    ("2026-11-27T17:59:00Z", True), ("2026-11-27T18:00:00Z", False),
    ("2026-11-26T16:00:00Z", False), ("2026-10-31T15:00:00Z", False),
])
def test_in_regular_session(stamp, inside):
    assert sessions.in_regular_session(stamp) is inside


def test_minutes_after_open_on_both_sides_of_the_clock_change():
    assert sessions.minutes_after_open("2026-10-30T13:45:00Z") == 15.0   # 09:45 EDT
    assert sessions.minutes_after_open("2026-11-10T14:45:00Z") == 15.0   # 09:45 EST
    assert sessions.minutes_after_open("2026-11-10T14:29:00Z") is None
    assert sessions.minutes_after_open("2026-11-26T16:00:00Z") is None


@pytest.mark.parametrize("stamp, bucket", [
    ("2026-11-10T14:30:00Z", "open_to_1030"), ("2026-11-10T15:29:59Z", "open_to_1030"),
    ("2026-11-10T15:30:00Z", "mid_day"), ("2026-11-10T19:59:59Z", "mid_day"),
    ("2026-11-10T20:00:00Z", "last_hour"), ("2026-11-10T20:59:59Z", "last_hour"),
    ("2026-11-10T21:00:00Z", "outside_session"), ("2026-11-10T12:00:00Z", "outside_session"),
    ("2026-11-27T16:59:00Z", "mid_day"), ("2026-11-27T17:00:00Z", "last_hour"),
    ("2026-10-31T15:00:00Z", "outside_session"),
])
def test_issue_bucket(stamp, bucket):
    assert sessions.issue_bucket(stamp) == bucket
    assert bucket in sessions.ISSUE_BUCKETS


def test_issue_buckets_are_frozen():
    assert sessions.ISSUE_BUCKETS == ("open_to_1030", "mid_day", "last_hour", "outside_session")


def test_stamp_source_prefers_issued_at():
    doc = {"plan_id": "P1", "created_at": "2026-11-09",
           "issued_at": "2026-11-10T15:00:00.500000+00:00"}
    stamp, source = sessions.stamp_source(doc)
    assert source == "issued_at"
    assert stamp == dt.datetime(2026, 11, 10, 15, 0, 0, 500000, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("doc", [{"plan_id": "P1", "created_at": "2026-11-10"},
                                 {"plan_id": "P1", "created_at": "2026-11-10",
                                  "issued_at": None},
                                 {"plan_id": "P1", "created_at": "2026-11-10",
                                  "issued_at": ""}])
def test_stamp_source_falls_back_to_the_created_bar_close(doc):
    stamp, source = sessions.stamp_source(doc)
    assert source == "created_at"
    assert stamp == dt.datetime(2026, 11, 10, 21, 0, tzinfo=dt.timezone.utc)   # 16:00 EST
    assert sessions.issue_session(stamp) == D(2026, 11, 10)
    assert sessions.issue_bucket(stamp) == "outside_session"


def test_a_created_at_on_an_early_close_maps_to_13_00():
    stamp, _ = sessions.stamp_source({"plan_id": "P1", "created_at": "2026-11-27"})
    assert sessions.ny_time(stamp).strftime("%H:%M") == "13:00"
    assert sessions.issue_session(stamp) == D(2026, 11, 27)


def test_stamp_source_without_any_stamp_is_refused():
    with pytest.raises(ValueError, match="P9"):
        sessions.stamp_source({"plan_id": "P9"})


@pytest.mark.parametrize("a, b, apart", [
    (D(2026, 10, 30), D(2026, 11, 2), 1),      # over a weekend
    (D(2026, 11, 25), D(2026, 11, 27), 1),     # over Thanksgiving
    (D(2026, 11, 2), D(2026, 10, 30), -1),
    (D(2026, 11, 10), D(2026, 11, 10), 0),
    (D(2026, 11, 9), D(2026, 11, 13), 4),
])
def test_sessions_apart(a, b, apart):
    assert sessions.sessions_apart(a, b) == apart
```

Create `tests/scout/test_reconcile_ignored.py`:

```python
"""v232: per-trade rows carry strategy, horizon and ticker -- they never reach git."""
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _ignored(path: str) -> bool:
    done = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert done.returncode in (0, 1), done
    return done.returncode == 0


@pytest.mark.parametrize("path", [
    "data/v232/trade-rows.jsonl",
    "data/v232/layer2/lane-base.jsonl",
    "data/v232/bars/raw/daily/AAPL.csv",
    "data/v232/bars/split/daily/_manifest.json",
])
def test_git_ignores_the_work_dir(path):
    assert _ignored(path), f"{path} is not git-ignored"


@pytest.mark.parametrize("path", [
    "docs/superpowers/results/2026-11-20-v232-live-replay-reconciliation.md",
    "docs/superpowers/results/2026-11-20-v232-live-replay-reconciliation.json",
    "scripts/reports/reconcile/sessions.py",
])
def test_the_committed_outputs_are_not_ignored(path):
    assert not _ignored(path), f"{path} must stay committable"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_sessions.py`
Expected: collection error — `ModuleNotFoundError: No module named 'reconcile'` (or `cannot import name 'sessions'` when V232-4 created the package first).
Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_ignored.py`
Expected: `test_git_ignores_the_work_dir` FAILS for all four paths; the committed-outputs tests PASS.

- [ ] **Step 3: Implement**

If `scripts/reports/reconcile/__init__.py` does not exist yet, create it with exactly this content (V232-4 creates the same file):

```python
"""v232: live versus replay reconciliation (scripts/reports/live_replay_reconcile.py)."""
from pathlib import Path

#: Git-ignored work directory: per-trade rows, layer 2 checkpoints, raw bars.
WORK_DIR = Path("data/v232")
```

Append to the end of `.gitignore`:

```gitignore
# v232 live-replay reconciliation: per-trade rows (strategy/horizon/ticker), layer 2 checkpoints, raw bars
data/v232/
```

Create `scripts/reports/reconcile/sessions.py`:

```python
"""v232: one clock for the reconciliation -- UTC stamps to NYSE sessions.

All zone work is Python zoneinfo (session.US_MARKET_TZ); Git Bash has no zone
data and nothing here reads TZ or the process clock.

issue_session(stamp) is the latest regular session whose 09:30 ET open is at
or before the stamp: a pre-open stamp belongs to the previous session, an
after-close stamp to that day's, a weekend or holiday stamp to the last session
before it. override_fidelity.assign_session maps a pre-open time to the same
day and is deliberately not reused (spec clarification 4).

A plan doc's created_at is the creating bar's DATE (plan_types.py); without
issued_at the stamp is that session's close, so its issue bucket is
outside_session by construction and consumers split buckets by stamp source.
"""
from __future__ import annotations

import datetime as dt
import re

from swingbot.core.market import session

UTC = dt.timezone.utc
NY = session.US_MARKET_TZ
ISSUE_BUCKETS = ("open_to_1030", "mid_day", "last_hour", "outside_session")
_BARE_OFFSET = re.compile(r"([+-]\d{2})$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse(text: str) -> dt.datetime:
    text = text.strip().replace(" ", "T", 1)
    if _DATE_ONLY.match(text):
        raise ValueError(f"{text!r} is a date, not a time of day")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return dt.datetime.fromisoformat(_BARE_OFFSET.sub(r"\1:00", text))


def to_utc(value: str | dt.datetime) -> dt.datetime:
    """An aware UTC datetime; a naive value is read as UTC (stores write UTC)."""
    stamp = value if isinstance(value, dt.datetime) else _parse(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def ny_time(stamp) -> dt.datetime:
    return to_utc(stamp).astimezone(NY)


def issue_session(stamp) -> dt.date:
    """The latest NYSE regular session whose open is at or before the stamp."""
    et = ny_time(stamp)
    day = et.date() if et.time() >= session.RTH_OPEN else et.date() - dt.timedelta(days=1)
    found = session.nyse_calendar().session_after(day, 0)
    if found is None:
        raise ValueError(f"{stamp!r} lies outside the NYSE calendar")
    return found


def _close_at(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, session.session_close(day), tzinfo=NY)


def _open_at(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, session.RTH_OPEN, tzinfo=NY)


def in_regular_session(stamp) -> bool:
    et = ny_time(stamp)
    day = et.date()
    if not session.nyse_calendar().is_session(day):
        return False
    return _open_at(day) <= et < _close_at(day)


def minutes_after_open(stamp) -> float | None:
    """Minutes since that day's 09:30 ET open, inside the regular session only."""
    if not in_regular_session(stamp):
        return None
    et = ny_time(stamp)
    return (et - _open_at(et.date())).total_seconds() / 60.0


def issue_bucket(stamp) -> str:
    """open_to_1030 [09:30, 10:30), last_hour [close - 60 min, close), else mid_day;
    outside_session outside the regular session (early closes included)."""
    minutes = minutes_after_open(stamp)
    if minutes is None:
        return "outside_session"
    if minutes < 60:
        return "open_to_1030"
    et = ny_time(stamp)
    if (_close_at(et.date()) - et).total_seconds() <= 3600:
        return "last_hour"
    return "mid_day"


def stamp_source(plan_doc: dict) -> tuple[dt.datetime, str]:
    """(issue stamp, "issued_at" | "created_at") for one stored plan doc."""
    issued = plan_doc.get("issued_at")
    if issued:
        return to_utc(issued), "issued_at"
    created = str(plan_doc.get("created_at") or "").strip()
    if not created:
        raise ValueError(f"plan {plan_doc.get('plan_id')!r} has neither issued_at "
                         f"nor created_at")
    if _DATE_ONLY.match(created):
        day = dt.date.fromisoformat(created)
        return _close_at(day).astimezone(UTC), "created_at"
    return to_utc(created), "created_at"


def sessions_apart(a: dt.date, b: dt.date) -> int:
    """Signed NYSE session count from a to b (each read as its session on or before)."""
    cal = session.nyse_calendar()
    pa, pb = cal.position_on_or_before(a), cal.position_on_or_before(b)
    if pa is None or pb is None:
        raise ValueError(f"{a} or {b} lies before the NYSE calendar")
    return pb - pa
```

`_close_at(day) - et` subtracts two datetimes with the same `ZoneInfo`, which Python does on wall-clock values; inside one regular session (09:30-16:00) no clock change can fall, so the difference is exact.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_sessions.py`
Expected: all PASS.
Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_ignored.py`
Expected: all PASS.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/__init__.py scripts/reports/reconcile/sessions.py tests/scout/test_reconcile_sessions.py .gitignore tests/scout/test_reconcile_ignored.py
git commit -m "feat(v232): reconcile package, NYSE session clock and the data/v232 ignore rule"
```

(If V232-4 already committed `__init__.py`, it is unchanged and `git add` is a no-op for it.)
