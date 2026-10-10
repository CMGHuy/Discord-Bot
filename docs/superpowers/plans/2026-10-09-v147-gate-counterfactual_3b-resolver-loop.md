# v147 Gate counterfactual: Part 3b, the nightly resolver loop (V147-12)

> Part of the v147 plan, split from Part 3 to stay under the 1500-line cap. Header, Global Constraints, deviations, parallelisation and the task ledger are in [`_0-index`](2026-10-09-v147-gate-counterfactual_0-index.md). **Never read this file whole**: `/task-brief V147-12` or `grep -n "^### Task V147-12:" -A 300 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_3b-resolver-loop.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md) § Live side / Nightly resolver (the loop shape, off the event loop, once per weekday after the close).

All commands run inside the plan's worktree `.claude/worktrees/2026-10-09-v147-gate-counterfactual` (created by V147-1). Paths below are relative to it. V147-12 needs V147-11 (`gate_resolver.resolve_due`, Part 3).

---

### Task V147-12: Nightly resolver loop

**Model:** sonnet — a scheduled loop copied from `weekly_earnings_refresh`/`daily_recap` with a fixed slot, fire-once marker and `asyncio.to_thread`; the resolver logic itself is V147-11's.

**Cross-plan (audit 2026-10-10):**
- **`_always_on_loops()` (v148 adds `ops_watch`).** Insert `gate_counterfactual_resolve` into the `_always_on_loops()` tuple as it stands, before `pitr_watch_loop`, keeping every entry already there (v148 adds `ops_watch` after it). Never replace the tuple from this plan's literal.
- **Swallowed-error ratchet (owner v148; full rule in the v148 index).** If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged), the loop's handler is `except Exception as exc:` with first statement `swallowed(log, "ops.gate_counterfactual_resolve", exc, level=logging.DEBUG)` (import from `swingbot.core.infra.swallowed`), keeping the `log.exception(...)` line after it; Step 4 also runs `python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py` (PASS; never raise `BASELINE`).

**Files:**
- Modify: `swingbot/commands/scanning/loops.py`
- Create: `tests/commands/test_gate_resolver_loop.py`

**Interfaces (ledger):** `gate_counterfactual_resolve` (`@tasks.loop(minutes=1)`), firing once per weekday (Berlin Mon–Fri) at the first poll at or after `SESSION_END_HOUR:45` Berlin, guarded by the module flag `_gate_resolve_fired_date` plus the persisted `_scheduled_job_already_fired` / `_mark_scheduled_job_fired('gate_counterfactual_resolve', today)` marker, calling `await asyncio.to_thread(gate_resolver.resolve_due, session_date(now))`; listed in `_always_on_loops()` right after `weekly_earnings_refresh`.

Consumes: `gate_resolver.resolve_due(today: str, ...) -> dict[str, int]` (V147-11). Verified at HEAD in `swingbot/commands/scanning/loops.py`: `SESSION_TZ` (Europe/Berlin, imported from `swingbot.bot_core`), `_scheduled_job_already_fired` / `_mark_scheduled_job_fired` (`:644/649`), the `daily_recap` slot shape (`SESSION_END_HOUR` + minute grace, `:654-690`), `weekly_earnings_refresh` (`:831`, `asyncio.to_thread` + `log.exception`), `_always_on_loops()` (`:966`). `session.session_date(now) -> str` (ET date, `swingbot/core/market/session.py:110`).

Why `:45`: `daily_recap` takes `:15`; `:45` leaves the recap and the session's last scan their slot, and `resolve_due` reads bars only up to the last session strictly before `today` anyway, so the exact minute never changes a result. The resolver is imported lazily inside the loop (like `refresh_watchlist_earnings`), so `loops.py` keeps no import-time dependency on `swingbot.core.backtesting`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_gate_resolver_loop.py`:

```python
"""v147 V147-12: the nightly gate-counterfactual resolver loop."""
import asyncio
import datetime as dt
import logging
import threading

import pytest

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.backtesting import gate_resolver
from swingbot.core.db.repositories.scheduled import scheduled_repo

JOB = "gate_counterfactual_resolve"
MONDAY = dt.date(2026, 10, 12)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_resolve(today, **kwargs):
        seen.append((today, threading.current_thread() is threading.main_thread()))
        return {"filled": 1}

    monkeypatch.setattr(gate_resolver, "resolve_due", fake_resolve)
    monkeypatch.setattr(config, "SESSION_END_HOUR", 22)
    monkeypatch.setattr(loops_mod, "_gate_resolve_fired_date", None)
    return seen


def _tick(monkeypatch, now: dt.datetime, *, restart: bool = False) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    if restart:
        monkeypatch.setattr(loops_mod, "_gate_resolve_fired_date", None)
    asyncio.run(loops_mod.gate_counterfactual_resolve.coro())


def test_fires_once_at_the_slot_off_the_event_loop(monkeypatch, calls):
    _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 44))
    _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 45))
    _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 46))
    assert calls == [("2026-10-12", False)]           # the ET session date, on a worker thread
    assert scheduled_repo().fired_on(JOB) == MONDAY.isoformat()


def test_a_restart_on_the_same_day_does_not_fire_again(monkeypatch, calls):
    _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 45))
    _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 50), restart=True)
    assert len(calls) == 1


@pytest.mark.parametrize("day", [10, 11])           # Saturday, Sunday
def test_never_fires_on_a_weekend(monkeypatch, calls, day):
    _tick(monkeypatch, dt.datetime(2026, 10, day, 22, 45))
    assert calls == []


def test_a_failing_resolver_is_logged_never_raised(monkeypatch, calls, caplog):
    def boom(today, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(gate_resolver, "resolve_due", boom)
    with caplog.at_level(logging.ERROR, logger=loops_mod.log.name):
        _tick(monkeypatch, dt.datetime(2026, 10, 12, 22, 45))
    assert any("gate_counterfactual_resolve" in r.getMessage() for r in caplog.records)


def test_the_loop_starts_with_the_bot():
    assert loops_mod.gate_counterfactual_resolve in loops_mod._always_on_loops()
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_gate_resolver_loop.py`
Expected: FAIL, `AttributeError: ... has no attribute '_gate_resolve_fired_date'` / `'gate_counterfactual_resolve'`.

- [ ] **Step 3: Add the loop to `swingbot/commands/scanning/loops.py`**

Next to the other fired-date flags (directly under `_earnings_refresh_fired_date: dt.date | None = None`), add:

```python
_gate_resolve_fired_date: dt.date | None = None
```

Directly after the whole `weekly_earnings_refresh` function (before `@tasks.loop(minutes=config.MARKET_DATA_REFRESH_MINUTES)`), add:

```python


@tasks.loop(minutes=1)
async def gate_counterfactual_resolve():
    """v147: resolve expired `gate_rejections` rows once per weekday at SESSION_END_HOUR:45 Berlin.

    Off the event loop (`asyncio.to_thread`) under gate_resolver's per-night batch
    cap; reads the live market_data cache only. The persisted scheduler marker
    makes a restart inside the slot safe."""
    global _gate_resolve_fired_date
    now = dt.datetime.now(SESSION_TZ)
    if now.weekday() > 4 or now.hour != config.SESSION_END_HOUR or now.minute < 45:
        return
    today = now.date()
    if _gate_resolve_fired_date == today or _scheduled_job_already_fired('gate_counterfactual_resolve', today):
        return
    _gate_resolve_fired_date = today
    _mark_scheduled_job_fired('gate_counterfactual_resolve', today)
    try:
        from swingbot.core.backtesting import gate_resolver
        from swingbot.core.market.session import session_date
        counts = await asyncio.to_thread(gate_resolver.resolve_due, session_date(now))
        log.info("gate_counterfactual_resolve: %s", counts or "nothing due")
    except Exception:
        log.exception("gate_counterfactual_resolve: resolver failed")
```

In `_always_on_loops()`, insert `gate_counterfactual_resolve` into the return tuple directly before `pitr_watch_loop`, keeping every entry already there (another plan, e.g. v148's `ops_watch`, may have added entries). With today's tuple the result reads:

```python
    return (session_scan, heartbeat, config_watcher, trade_monitor, daily_recap,
            weekend_deep_scan_task, weekly_earnings_refresh, gate_counterfactual_resolve,
            pitr_watch_loop, next_session_scan, next_session_wrapup)
```

Leave `swingbot/commands/scanning/__init__.py` unchanged: its facade re-exports only some loops (`pitr_watch_loop`, `next_session_scan`, `next_session_wrapup` are not there either), and the tests import the loop from `loops`.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_gate_resolver_loop.py`
Expected: PASS, `6 passed`, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
Run: `python scripts/dev/testrun.py file tests/commands/test_outlook_loops.py`
Run: `python scripts/dev/testrun.py file tests/commands/test_pitr_watch_loop.py`
Expected: each `0 failed` (they pin `_always_on_loops()` membership and the shared scheduler marker).

- [ ] **Step 5: Complexity and syntax**

Run: `python -m radon cc -s swingbot/commands/scanning/loops.py | grep -E "gate_counterfactual_resolve|_always_on_loops"`
Expected: `gate_counterfactual_resolve` A or B (well under 15), `_always_on_loops` A.

Run: `python -m py_compile swingbot/commands/scanning/loops.py`
Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_gate_resolver_loop.py
git commit -m "feat(v147): nightly gate-counterfactual resolver loop (V147-12)"
```

