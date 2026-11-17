# v228 — Intraday MFE/MAE for the journal: Part 2, wiring (V228-6 .. V228-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-7" -A 400 <this file>`); never read the part whole.

**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../specs/2026-11-14-v228-intraday-excursion-design.md)
**Index:** [2026-11-14-v228-intraday-excursion_0-index.md](2026-11-14-v228-intraday-excursion_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the Task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the refresh-loop hook (V228-6), the data revision (V228-7), the operator backfill script (V228-8), the exit-quality trust rule and endpoint block (V228-9) and the calendar row key (V228-10).

Cross-part contracts consumed here (from the ledger, created in part 1): `swingbot.core.analytics.excursion_upgrade` (`UpgradeReport`, `pending_by_ticker`, `upgrade_ticker`, `upgrade_excursions`) from V228-5; `swingbot.core.analytics.mfe_mae.INTRADAY_SOURCES` from V228-2. `UpgradeReport.line()` returns one line starting `excursion upgrade:`; `UpgradeReport.as_dict()` returns `{"read": int, "upgraded": {source: int}, "no_trade": int, "no_file": int, "unreadable": int, "no_coverage": int, "density": int, "no_inputs": int, "lost_race": int, "budget_hit": bool}` and `absorb(counts)` adds such a dict into the report (ints summed, `upgraded` merged per source, `budget_hit` OR-ed). If V228-5 landed a different `as_dict()` shape, stop and report it rather than adapting silently.

Branch rule for every task: implement in the plan's worktree, never on `main`; each task ends with its own scoped commit there. Per-task verification is the narrow run named in each task; no task runs the full suite (CI does).

# Phase 4 — Running the upgrade

### Task V228-6: Run the pass from `market_data_refresh`: once per UTC date, worker thread, 60 s budget

**Model:** sonnet — one async helper and a call in an existing loop, with a starvation incident to respect and module state to reset in tests.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (module constants and `_run_excursion_pass` just above `market_data_refresh`, around l.1209; one call at the very end of `market_data_refresh`, after the `gaps` block, around l.1290)
- Modify: `tests/commands/test_market_data_refresh_task.py` (autouse stub + reset fixture; new tests)

**Interfaces:**
- Consumes (V228-5): `swingbot.core.analytics.excursion_upgrade.upgrade_excursions(since: str | None, until: str | None = None, *, budget_seconds: float | None = None, base_dir: str = DATA_DIR) -> UpgradeReport`; `UpgradeReport.line() -> str` (one line starting `excursion upgrade:`).
- Produces: `loops.EXCURSION_PASS_DAYS = 7`; `loops.EXCURSION_PASS_BUDGET_S = 60.0`; `loops._EXCURSION_PASS_DATE: dt.date | None`; `async def loops._run_excursion_pass(today: dt.date | None = None) -> None`.

**Design (spec § 3; Global Constraints "Refresh-loop pass"):**
- The pass runs **after** the refresh, at the end of the loop body, so the archives `refresh_all` just wrote are on disk. When the refresh itself raised, the loop already `return`s (l.1262) and the pass waits for the next tick; it has not stamped the date, so it still runs that day.
- **Once per UTC date:** the date is stamped *before* the work starts, so a pass that raises or hits its budget does not retry on every wake (the 2026-08-24 gateway-starvation incident is why). A restart clears the stamp and may run it again the same day; that is harmless because each upgrade is conditional and idempotent.
- **Worker thread:** `asyncio.to_thread(upgrade_excursions, ...)`; the event loop is never blocked.
- **Budget:** `budget_seconds=EXCURSION_PASS_BUDGET_S` is enforced inside `upgrade_excursions` (V228-5); `budget_hit` shows in the report line.
- **Window:** `since` = UTC midnight of `today` minus `EXCURSION_PASS_DAYS` days, as an aware ISO string (the same shape as journal `closed_at`); `until=None`.
- **Never fails the refresh:** its own `try/except Exception` → `log.exception`; a success logs exactly one `log.info` line, `market_data_refresh: <report.line()>`.
- `market_data_refresh` gains one `await` statement and no branch; its complexity does not move.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/commands/test_market_data_refresh_task.py`:

```python
import datetime as dt

import pytest

from swingbot.commands.scanning import loops
```

Add this fixture and these helpers below `_run`. The autouse fixture keeps the five existing loop tests away from the real journal and resets the module-level date stamp, which otherwise leaks between tests in one xdist worker:

```python
class _FakeReport:
    def __init__(self, text="excursion upgrade: read 3, upgraded 5min 2"):
        self.text = text

    def line(self):
        return self.text


@pytest.fixture(autouse=True)
def _stub_excursion_pass(monkeypatch):
    """Every test here starts with no pass run today and a fake pass."""
    calls = []

    def fake_upgrade(since, until=None, **kwargs):
        calls.append({"since": since, "until": until, **kwargs})
        return _FakeReport()

    monkeypatch.setattr(loops, "_EXCURSION_PASS_DATE", None)
    monkeypatch.setattr(
        "swingbot.core.analytics.excursion_upgrade.upgrade_excursions", fake_upgrade)
    return calls


def _fresh_refresh(symbols, timeframes, **_kwargs):
    return {"summary": {tf: {"full": 0, "incremental": 0, "fresh": 1,
                             "failed": 0, "added": 0} for tf in timeframes},
            "failures": [], "state": {}, "deadline_hit": False}


def _enable_refresh(monkeypatch, refresh=_fresh_refresh):
    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", True, raising=False)
    monkeypatch.setattr(config, "MARKET_DATA_TIMEFRAMES", "daily,5min", raising=False)
    monkeypatch.setattr(loops, "load_watchlist", lambda: ["AAPL"], raising=False)
    monkeypatch.setattr(loops, "_refresh_priority_tickers", lambda: [])
    monkeypatch.setattr("swingbot.core.marketdata.data_refresh.refresh_all", refresh)
```

Append these tests at the end of the file:

```python

def test_the_pass_constants_match_the_spec():
    assert loops.EXCURSION_PASS_DAYS == 7
    assert loops.EXCURSION_PASS_BUDGET_S == 60.0


def test_the_pass_runs_after_the_refresh_with_its_window_and_budget(
        monkeypatch, _stub_excursion_pass):
    order = []

    def refresh(symbols, timeframes, **kwargs):
        order.append("refresh")
        return _fresh_refresh(symbols, timeframes, **kwargs)

    def fake_upgrade(since, until=None, **kwargs):
        order.append("pass")
        _stub_excursion_pass.append({"since": since, "until": until, **kwargs})
        return _FakeReport()

    monkeypatch.setattr(
        "swingbot.core.analytics.excursion_upgrade.upgrade_excursions", fake_upgrade)
    _enable_refresh(monkeypatch, refresh)

    _run(scanning_mod.market_data_refresh.coro())

    assert order == ["refresh", "pass"]
    call = _stub_excursion_pass[0]
    today = dt.datetime.now(dt.timezone.utc).date()
    expected = dt.datetime.combine(today - dt.timedelta(days=7), dt.time(),
                                   tzinfo=dt.timezone.utc).isoformat()
    assert call["since"] == expected
    assert call["until"] is None
    assert call["budget_seconds"] == 60.0


def test_the_pass_runs_at_most_once_per_utc_date(_stub_excursion_pass):
    day = dt.date(2026, 11, 14)
    _run(loops._run_excursion_pass(day))
    _run(loops._run_excursion_pass(day))
    assert len(_stub_excursion_pass) == 1
    assert loops._EXCURSION_PASS_DATE == day


def test_a_new_utc_date_runs_the_pass_again(_stub_excursion_pass):
    _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    _run(loops._run_excursion_pass(dt.date(2026, 11, 15)))
    assert [c["since"] for c in _stub_excursion_pass] == [
        "2026-11-07T00:00:00+00:00", "2026-11-08T00:00:00+00:00"]


def test_the_pass_runs_in_a_worker_thread(monkeypatch):
    seen = []
    real = asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        seen.append(getattr(fn, "__name__", repr(fn)))
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(loops.asyncio, "to_thread", spy)
    _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    assert seen == ["fake_upgrade"]


def test_the_pass_logs_one_info_line_with_the_report():
    with patch.object(loops.log, "info") as info:
        _run(loops._run_excursion_pass(dt.date(2026, 11, 14)))
    assert info.call_count == 1
    assert info.call_args.args[0] == "market_data_refresh: %s"
    assert info.call_args.args[1].startswith("excursion upgrade:")


def test_a_failing_pass_is_logged_never_raised_and_not_retried_that_day(monkeypatch):
    calls = []

    def boom(since, until=None, **kwargs):
        calls.append(since)
        raise RuntimeError("journal unreachable")

    monkeypatch.setattr("swingbot.core.analytics.excursion_upgrade.upgrade_excursions", boom)
    day = dt.date(2026, 11, 14)
    with patch.object(loops.log, "exception") as exception:
        _run(loops._run_excursion_pass(day))
        _run(loops._run_excursion_pass(day))
    assert len(calls) == 1
    assert "excursion upgrade failed" in str(exception.call_args)


def test_a_failing_pass_never_fails_the_refresh(monkeypatch, caplog):
    def boom(since, until=None, **kwargs):
        raise RuntimeError("journal unreachable")

    monkeypatch.setattr("swingbot.core.analytics.excursion_upgrade.upgrade_excursions", boom)
    _enable_refresh(monkeypatch)
    with caplog.at_level("INFO"):
        _run(scanning_mod.market_data_refresh.coro())   # must not raise
    assert any("excursion upgrade failed" in r.message for r in caplog.records)


def test_a_failed_refresh_skips_the_pass_and_leaves_the_date_unstamped(
        monkeypatch, _stub_excursion_pass):
    def refresh(symbols, timeframes, **kwargs):
        raise RuntimeError("provider down")

    _enable_refresh(monkeypatch, refresh)
    _run(scanning_mod.market_data_refresh.coro())
    assert _stub_excursion_pass == []
    assert loops._EXCURSION_PASS_DATE is None


def test_auto_refresh_off_runs_no_pass(monkeypatch, _stub_excursion_pass):
    monkeypatch.setattr(config, "MARKET_DATA_AUTO_REFRESH", False, raising=False)
    _run(scanning_mod.market_data_refresh.coro())
    assert _stub_excursion_pass == []


def test_a_budget_hit_refresh_still_runs_the_pass(monkeypatch, _stub_excursion_pass):
    def refresh(symbols, timeframes, **kwargs):
        result = _fresh_refresh(symbols, timeframes)
        result["deadline_hit"] = True
        return result

    _enable_refresh(monkeypatch, refresh)
    _run(scanning_mod.market_data_refresh.coro())
    assert len(_stub_excursion_pass) == 1
```

`loops.log` is the module logger, and `log.exception` logs at ERROR, which `caplog.at_level("INFO")` captures. If the logger does not propagate to the root (check `logging.getLogger("swingbot.commands.scanning.loops").propagate`), swap the `caplog` assertion for `patch.object(loops.log, "exception")` as in the test above it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_market_data_refresh_task.py`
Expected: FAIL — `AttributeError: <module 'swingbot.commands.scanning.loops'> has no attribute '_EXCURSION_PASS_DATE'`, raised by the autouse fixture, so every test in the file errors at setup until Step 3.

- [ ] **Step 3: Implement**

In `swingbot/commands/scanning/loops.py`, directly above `@tasks.loop(minutes=config.MARKET_DATA_REFRESH_MINUTES)` (l.1210), add:

```python
#: v228: how far back the excursion upgrade pass looks, and how long it may run.
#: An entry that cannot reach a finer source is re-read once a day for this many
#: days, then left to the operator backfill (scripts/ops/backfill_excursions.py).
EXCURSION_PASS_DAYS = 7
EXCURSION_PASS_BUDGET_S = 60.0
#: UTC date the pass last started on; a restart clears it (harmless: every
#: upgrade is a conditional, idempotent patch).
_EXCURSION_PASS_DATE: dt.date | None = None


async def _run_excursion_pass(today: dt.date | None = None) -> None:
    """Upgrade recent journal excursions to the finest archived bars.

    Fenced three ways (spec v228 § 3): at most once per UTC date (stamped
    before the work, so a failure or a budget hit is not retried every
    wake), off the event loop through ``asyncio.to_thread``, and inside an
    ``EXCURSION_PASS_BUDGET_S`` budget enforced by ``upgrade_excursions``.
    Any exception is logged and swallowed: the pass never fails the refresh.
    """
    global _EXCURSION_PASS_DATE
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if _EXCURSION_PASS_DATE == today:
        return
    _EXCURSION_PASS_DATE = today
    since = dt.datetime.combine(today - dt.timedelta(days=EXCURSION_PASS_DAYS),
                                dt.time(), tzinfo=dt.timezone.utc).isoformat()
    try:
        from swingbot.core.analytics.excursion_upgrade import upgrade_excursions
        report = await asyncio.to_thread(upgrade_excursions, since,
                                         budget_seconds=EXCURSION_PASS_BUDGET_S)
    except Exception:
        log.exception("market_data_refresh: excursion upgrade failed")
        return
    log.info("market_data_refresh: %s", report.line())
```

At the very end of `market_data_refresh` (after the `if gaps:` block, still inside the function), add:

```python

    # v228: the archives this tick refreshed are on disk now; upgrade the
    # last week's journal excursions from them (once per UTC date).
    await _run_excursion_pass()
```

Append to the `market_data_refresh` docstring, as a new final paragraph:

```
    After the sweep, once per UTC date, the v228 excursion upgrade pass
    re-measures the last week's journal MFE/MAE on the finest archived bars
    (``_run_excursion_pass``); it has its own budget and never fails the loop.
```

Notes for the implementer:
- `asyncio`, `dt` and `log` already exist at module level in `loops.py` (l.1-2 imports; `log` is the module logger). Add no imports.
- The test fakes replace `upgrade_excursions` on `swingbot.core.analytics.excursion_upgrade`, which works because `_run_excursion_pass` imports the name inside the function at call time. Keep that import local: `loops` import time stays unchanged and the bot still starts if the analytics module fails to import.
- `upgrade_excursions` is called with `since` positional and `budget_seconds` keyword only; `until` stays at its default `None`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_market_data_refresh_task.py`
Expected: PASS (5 existing + 11 new tests).

Complexity check: `python -m radon cc -s -n C swingbot/commands/scanning/loops.py` — `_run_excursion_pass` is not listed (cc < 15) and `market_data_refresh` gains no row.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_market_data_refresh_task.py
git commit -m "feat(v228): run the excursion upgrade pass once per UTC date after the market-data refresh"
```

# Phase 5 — Existing rows

### Task V228-7: Data revision `v228_001`: stamp `daily` on rows with `mfe_r` and no source

**Model:** opus — a production data revision with a deliberate no-op downgrade and a rollback-safety declaration; the WHERE clause decides which rows a later upgrade can still reach.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v228_001_excursion_source.py`
- Create: `tests/db/test_v228_excursion_source_migration.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (disjoint; may run in parallel with anything). The field name `excursion_source` and the value `"daily"` are the ledger's (`mfe_mae.EXCURSION_SOURCES`, V228-2), written here as literals because a revision never imports live code that may change later.
- Produces: revision `v228_001`, the single Alembic head after this task; module-level `ROLLBACK_SAFE` string containing `excursion_source`; module function `stamp(conn) -> int` (rows stamped), used by the test.

**Rules this task follows (`docs/claude/schema-evolution.md`):**
- `excursion_source` is an **add** (a new doc field; no DDL). This revision is not the field's migration: it is a one-off data revision so that after it no reader has to treat a missing source as anything (spec § 4).
- Revision id `v<plan>_NNN` → `v228_001`; `down_revision` is the current head. On 2026-11-14 that is `v208_001` (the chain is `v204_001 → v209_001 → v227_001 → v208_001`; the newest *filename* `v227_001_feed_posts.py` is **not** the head). Step 0 re-reads it.
- `tests/db/test_migrations.py` enforces the id shape and exactly one head; it must stay green.
- Rollback safety (v220): `upgrade()` calls `op.get_bind()` and executes an `UPDATE`, which `scripts/ops/rollback_migrations.py` classifies unsafe, so the module declares `ROLLBACK_SAFE = "<what older code does with the new shape>"`, never "reviewed".
- **Which rows (Review Focus):** `WHERE doc->>'mfe_r' IS NOT NULL AND doc->'excursion_source' IS NULL`. A row whose `mfe_r` is an explicit JSON `null` (`build_entry` writes that when no bars covered the trade at close) has `doc->>'mfe_r'` SQL `NULL`, so it stays **unlabelled** and a later upgrade can still give it an intraday source. A row that already carries any source (`5min`, `hourly`, `daily`, written by V228-4 code that deployed before the revision ran) is left alone.
- **Downgrade is a no-op** (spec § 4): stripping the field would also strip `5min`/`hourly` sources written after the upgrade, and a re-upgrade would then label intraday numbers `daily`. Older code keeps unknown doc fields (`tests/db/test_unknown_field_round_trip.py`), so leaving the field is safe. The one loss, named in `ROLLBACK_SAFE`: older code re-journaling a trade upserts the entry without the field. The index's OPEN item records that the spec's Testing line once said "downgrade restores"; the plan follows the body (no-op), and this task tests exactly that.
- `drop_doc_field` / `restore_doc_field` are **not** used.
- Before the revision runs on production, V228-17 checks the last PITR drill passed (`schema-evolution.md` § Before running a data revision on production). Nothing in this task touches production.

- [ ] **Step 0: Confirm the head and sync the replica**

Run: `python -m alembic heads`
Expected: `v208_001 (head)`. If it prints another id, use that id for `down_revision` in Step 3 and for `PREVIOUS_HEAD` in Step 1, and say so in the commit message.

Run `/replicate-prod-db` (the shared `swing-db` container on port 56789, credentials from `.env`, never printed) before the first DB test run, unless a sibling task in this session already synced it.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_v228_excursion_source_migration.py`:

```python
"""v228_001: stamp excursion_source = "daily" on every journal entry that has
an mfe_r and no source, once. The downgrade is a deliberate no-op: stripping
the field would also strip intraday sources written after the upgrade."""
from __future__ import annotations

import importlib.util
import logging
import pathlib
import sys

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from swingbot.core.db.repositories.journal import JournalRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v228_001_excursion_source.py")
PREVIOUS_HEAD = "v208_001"   # `python -m alembic heads` when V228-7 ran

sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_migrations as rm  # noqa: E402


def _load_revision():
    spec = importlib.util.spec_from_file_location("v228_001_excursion_source", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()


@pytest.fixture
def journal_conn(db_conn):
    db_conn.execute(sa.text("DELETE FROM journal_entries"))   # rolled back with the fixture
    return db_conn


def _entry(conn, trade_id, **doc):
    record = {"trade_id": trade_id, "strategy": "S/R Confluence", "outcome": "loss",
              "closed_at": "2026-10-14T15:00:00+00:00",
              "created_at": "2026-10-14T15:00:01+00:00",
              "mfe_r": 1.24, "mae_r": 1.0, "exit_efficiency": -0.8065,
              "tags": ["near-miss-tp"], "note": "", "holding_days": 0.2}
    record.update(doc)
    JournalRepository().upsert(record, conn=conn)


def _drop_key(conn, trade_id, key):
    conn.execute(sa.text("UPDATE journal_entries SET doc = doc - :key WHERE trade_id = :tid"),
                 {"key": key, "tid": trade_id})


def _row(conn, trade_id):
    return JournalRepository().get(trade_id, conn=conn)



def test_a_row_with_mfe_and_no_source_is_stamped_daily(journal_conn):
    _entry(journal_conn, "T1")
    assert MIG.stamp(journal_conn) == 1
    assert _row(journal_conn, "T1")["excursion_source"] == "daily"


def test_an_explicit_null_mfe_stays_unlabelled(journal_conn):
    """No bars at close: build_entry wrote mfe_r = null. A later upgrade can
    still give it an intraday source, so the revision must not call it daily."""
    _entry(journal_conn, "T-null", mfe_r=None, mae_r=None, exit_efficiency=None)
    assert MIG.stamp(journal_conn) == 0
    assert "excursion_source" not in _row(journal_conn, "T-null")


def test_a_row_without_an_mfe_key_stays_unlabelled(journal_conn):
    _entry(journal_conn, "T-nokey")
    _drop_key(journal_conn, "T-nokey", "mfe_r")
    assert MIG.stamp(journal_conn) == 0
    assert "excursion_source" not in _row(journal_conn, "T-nokey")


@pytest.mark.parametrize("source", ["5min", "15min", "hourly", "daily"])
def test_a_row_that_already_names_its_source_is_left_alone(journal_conn, source):
    _entry(journal_conn, "T-src", excursion_source=source)
    assert MIG.stamp(journal_conn) == 0
    assert _row(journal_conn, "T-src")["excursion_source"] == source


def test_the_stamp_touches_no_other_field(journal_conn):
    _entry(journal_conn, "T1", note="Should have trailed further.")
    before = _row(journal_conn, "T1")
    MIG.stamp(journal_conn)
    after = _row(journal_conn, "T1")
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    assert changed <= {"excursion_source", "updated_at"}
    assert after["note"] == "Should have trailed further."
    assert after["mfe_r"] == 1.24 and after["tags"] == ["near-miss-tp"]


def test_the_stamp_is_idempotent(journal_conn):
    _entry(journal_conn, "T1")
    _entry(journal_conn, "T2")
    assert MIG.stamp(journal_conn) == 2
    assert MIG.stamp(journal_conn) == 0


def test_an_empty_journal_stamps_nothing(journal_conn):
    assert MIG.stamp(journal_conn) == 0



def test_upgrade_logs_the_count_and_downgrade_leaves_stamped_rows(journal_conn, caplog):
    _entry(journal_conn, "T1")
    _entry(journal_conn, "T2", mfe_r=None)
    with Operations.context(MigrationContext.configure(journal_conn)):
        with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
            MIG.upgrade()
        assert _row(journal_conn, "T1")["excursion_source"] == "daily"
        MIG.downgrade()
    assert _row(journal_conn, "T1")["excursion_source"] == "daily"
    assert "excursion_source" not in _row(journal_conn, "T2")
    assert "v228_001: stamped 1 journal entry row(s) excursion_source=daily" in caplog.text


def test_downgrade_keeps_an_intraday_source_written_after_the_upgrade(journal_conn):
    """The reason the downgrade is a no-op: a later pass wrote 5min."""
    _entry(journal_conn, "T1")
    with Operations.context(MigrationContext.configure(journal_conn)):
        MIG.upgrade()
        JournalRepository().patch("T1", {"excursion_source": "5min", "mfe_r": 0.31},
                                  conn=journal_conn)
        MIG.downgrade()
    row = _row(journal_conn, "T1")
    assert row["excursion_source"] == "5min" and row["mfe_r"] == 0.31



def test_the_revision_is_rollback_safe_by_its_stated_reason():
    verdict = rm.scan_upgrade(REVISION_FILE.read_text(encoding="utf-8"),
                              revision="v228_001", path=str(REVISION_FILE))
    assert verdict.safe is True
    assert verdict.override is not None and "excursion_source" in verdict.override
    assert "reviewed" not in verdict.override.lower()


def test_v228_001_sits_on_the_previous_head_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert MIG.revision == "v228_001"
    assert scripts.get_revision("v228_001").down_revision == PREVIOUS_HEAD
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v228_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_the_revision_runs_up_down_and_up_again(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, MIG.down_revision)
        upgrade(cfg, "head")
```

Notes:
- `JournalRepository().upsert` writes non-promoted keys into `doc`; a `None` value lands as JSON `null` (that is the "explicit null" case). If the repository turns out to drop `None` keys, seed `T-null` with `_entry(...)` then `UPDATE journal_entries SET doc = jsonb_set(doc, '{mfe_r}', 'null') WHERE trade_id = 'T-null'` instead, and keep the assertion.
- `_row` returns the merged record (`doc` plus promoted columns), so `"excursion_source" not in row` means the doc key is absent.
- `test_the_stamp_touches_no_other_field` allows `updated_at` only in case the repository's record exposes it; the revision itself does not set `updated_at`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v228_excursion_source_migration.py`
Expected: FAIL at collection — `FileNotFoundError` for `v228_001_excursion_source.py` in `_load_revision`.

- [ ] **Step 3: Write the revision**

Create `swingbot/core/db/migrations/versions/v228_001_excursion_source.py`:

```python
"""journal_entries.doc.excursion_source: label every measured entry "daily"

v228 V228-7. Before v228 every journal MFE/MAE/exit-efficiency figure was
measured on daily bars; from v228 each entry records which bars measured it
in the doc field `excursion_source` ("5min", "15min", "hourly" or "daily").
This revision stamps "daily" on every existing entry that has an `mfe_r` and
no source, so no reader ever has to treat a missing source as anything
(docs/claude/schema-evolution.md: no read-time upcasting).

Rows left unlabelled on purpose:
- `mfe_r` is an explicit JSON null (no bars covered the trade at close):
  there is no daily figure to label, and the v228 upgrade pass may still
  measure it on intraday bars later.
- the entry already names a source (written by v228 code before this ran).

The downgrade is a no-op: stripping the field would also strip the intraday
sources the upgrade pass writes after this revision, and a re-upgrade would
then label those intraday numbers "daily". Older code keeps unknown doc
fields, so leaving the field in place is safe (ROLLBACK_SAFE below).

Revision ID: v228_001
Revises: v208_001
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "v228_001"
down_revision = "v208_001"
branch_labels = None
depends_on = None

ROLLBACK_SAFE = (
    "older code never reads the journal doc field excursion_source and keeps "
    "unknown doc fields on read and patch (v116 unknown-field round-trip); the "
    "one loss is that older code re-journaling a trade upserts the entry "
    "without excursion_source, which the v228 upgrade pass re-derives"
)

log = logging.getLogger("alembic.runtime.migration")

_STAMP = sa.text(
    "UPDATE journal_entries "
    "SET doc = doc || jsonb_build_object('excursion_source', 'daily') "
    "WHERE doc->>'mfe_r' IS NOT NULL AND doc->'excursion_source' IS NULL")


def stamp(conn) -> int:
    """Label every measured, unlabelled journal entry "daily"; rows stamped."""
    return conn.execute(_STAMP).rowcount


def upgrade() -> None:
    stamped = stamp(op.get_bind())
    log.info("v228_001: stamped %d journal entry row(s) excursion_source=daily", stamped)


def downgrade() -> None:
    """No-op by design: see the module docstring and ROLLBACK_SAFE."""
```

If Step 0 printed a head other than `v208_001`, change `down_revision` and the docstring's `Revises:` line to it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_v228_excursion_source_migration.py`
Expected: PASS (14 collected tests: 11 functions, one parametrized over 4 sources).

Then the two guards on the revision graph and rollback scanning:

Run: `python scripts/dev/testrun.py file tests/db/test_migrations.py`
Expected: PASS (one head, id shape accepted).

The rollback classification is covered by `test_the_revision_is_rollback_safe_by_its_stated_reason` (it calls the same `rm.scan_upgrade` that `/rollback` uses); `rollback_migrations.py`'s CLI needs a target sha and is not run here.

If the DB tests report **skipped** instead of passed, the `swing-db` container is not reachable on port 56789: start it (`skills-tools.md`), re-run, and never count a skip as green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/migrations/versions/v228_001_excursion_source.py tests/db/test_v228_excursion_source_migration.py
git commit -m "feat(v228): data revision v228_001 stamps excursion_source=daily on measured journal entries (no-op downgrade, ROLLBACK_SAFE)"
```

### Task V228-8: Operator script `backfill_excursions.py` with per-ticker checkpoints

**Model:** sonnet — an ops script on an established checkpoint pattern, calling V228-5's functions; restart safety is the part to get right.

**Files:**
- Create: `scripts/ops/backfill_excursions.py`
- Create: `tests/scripts/test_backfill_excursions.py` (suite `tooling`, which owns `tests/scripts/`)

**Interfaces:**
- Consumes (V228-5, `swingbot.core.analytics.excursion_upgrade`):
  - `pending_by_ticker(since: str | None, until: str | None = None) -> dict[str, list[tuple[dict, dict | None]]]` — only entries whose stored source is coarser than `5min` or absent.
  - `upgrade_ticker(ticker: str, pairs: list[tuple[dict, dict | None]], report: UpgradeReport, *, base_dir: str = DATA_DIR, deadline: float | None = None) -> bool`.
  - `UpgradeReport()` (all counts zero, `upgraded == {}`, `budget_hit False`), `.line() -> str` (starts `excursion upgrade:`), `.as_dict() -> dict`, `.absorb(counts: dict) -> None` (adds an `as_dict()`-shaped dict into the report).
  - `swingbot.core.marketdata.data_store.DATA_DIR`.
- Produces: `FINGERPRINT = "v228-excursion-backfill-1"`; `run(checkpoint_dir: Path, *, since: str | None = None, base_dir: str = DATA_DIR) -> UpgradeReport`; `main(argv: list[str] | None = None) -> int`; CLI `--checkpoint-dir` (default `logs/backfill_excursions.ckpt`), `--report-file` (default `logs/backfill_excursions.report.txt`), `--since`; prints `resuming: n/N tickers restored` first, then one final `excursion upgrade: …` line. V228-17 runs it on the VM.

**Design (spec § 4; CLAUDE.md "Long runs must checkpoint"; reference `build()` in `scripts/backtest/measure_atr_band_stop.py:161-193`):**
- **Unit = ticker.** After each ticker finishes, its per-ticker counts (`UpgradeReport.as_dict()` of a fresh report used for that ticker only) are written to `<checkpoint_dir>/<safe name>.json` through a `.tmp` file and `replace`, as `{"fingerprint": FINGERPRINT, "ticker": <ticker>, "counts": {...}}`.
- **Restart skips finished tickers.** Every `*.json` in the directory whose `fingerprint` matches is restored (its `counts` absorbed into the total, its `ticker` skipped) — including tickers that no longer appear in `pending_by_ticker` because the first run already upgraded all their entries to `5min`. A blob with another fingerprint, unparsable JSON, or a missing `ticker`/`counts` is ignored, so that ticker is redone.
- **A ticker interrupted halfway is simply redone.** That is safe because each entry's upgrade is a conditional patch (`patch_if_coarser`, V228-3) that never downgrades and writes nothing when unchanged; entries the first attempt already upgraded to `5min` are no longer returned by `pending_by_ticker`.
- `N` in `resuming: n/N` = restored tickers plus pending tickers not restored. `resuming: 0/N tickers restored` is printed on a fresh run too, so the operator log always shows it.
- **On completion** the checkpoint directory is removed and the final line is printed and written to `--report-file` (parent directories created). On the VM both default paths sit under `logs/`, a host mount (`docker-compose.yml`), so the checkpoint survives a container restart.
- No budget: `upgrade_ticker(..., deadline=None)`. The script is the whole-book run; the 60-second budget belongs to the bot's daily pass (V228-6).
- **Runs from a file or from stdin.** `ROOT` falls back to the working directory when `__file__` is undefined (`docker compose exec -T bot python - < script.py`), so the `sys.path` insert never raises.
- Ticker names may carry `=`, `^` or `/` (`GC=F`, `^VIX`): the checkpoint filename replaces every character outside `[A-Za-z0-9._-]` with `_`; the real ticker lives inside the blob, so two names that sanitise alike never collide on restore (the second would overwrite the first's file only if both are pending, and then it is redone — still idempotent).

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_backfill_excursions.py`:

```python
"""v228 operator backfill: per-ticker checkpoints, restart skips finished
tickers, a half-done ticker is redone, the report line is printed and saved."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from swingbot.core.analytics.excursion_upgrade import UpgradeReport

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backfill_excursions.py"

_spec = importlib.util.spec_from_file_location("backfill_excursions", SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


def _pairs(n):
    return [({"trade_id": f"t{i}", "excursion_source": "daily"}, {"id": f"t{i}"})
            for i in range(n)]


@pytest.fixture
def fake_pass(monkeypatch):
    """pending_by_ticker returns three tickers; upgrade_ticker upgrades every
    pair to 5min and records the order it was called in."""
    state = {"pending": {"AAPL": _pairs(2), "GC=F": _pairs(1), "MSFT": _pairs(3)},
             "calls": [], "fail_on": None, "since": []}

    def pending(since, until=None):
        state["since"].append(since)
        return {t: list(p) for t, p in state["pending"].items()}

    def upgrade(ticker, pairs, report, *, base_dir=None, deadline=None):
        if ticker == state["fail_on"]:
            raise KeyboardInterrupt("operator stopped the run")
        state["calls"].append((ticker, base_dir, deadline))
        report.read += len(pairs)
        report.upgraded["5min"] = report.upgraded.get("5min", 0) + len(pairs)
        return True

    monkeypatch.setattr(bf, "pending_by_ticker", pending)
    monkeypatch.setattr(bf, "upgrade_ticker", upgrade)
    return state


def test_a_fresh_run_upgrades_every_ticker_and_removes_its_checkpoints(
        fake_pass, tmp_path, capsys):
    ckpt = tmp_path / "ckpt"
    report = bf.run(ckpt, base_dir="md")
    assert [c[0] for c in fake_pass["calls"]] == ["AAPL", "GC=F", "MSFT"]
    assert all(c[1] == "md" and c[2] is None for c in fake_pass["calls"])
    assert report.read == 6 and report.upgraded == {"5min": 6}
    assert not ckpt.exists()
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "resuming: 0/3 tickers restored"


def test_each_finished_ticker_writes_a_checkpoint(fake_pass, tmp_path):
    ckpt = tmp_path / "ckpt"
    fake_pass["fail_on"] = "MSFT"
    with pytest.raises(KeyboardInterrupt):
        bf.run(ckpt)
    files = sorted(p.name for p in ckpt.glob("*.json"))
    assert files == ["AAPL.json", "GC_F.json"]
    blob = json.loads((ckpt / "GC_F.json").read_text(encoding="utf-8"))
    assert blob["fingerprint"] == bf.FINGERPRINT
    assert blob["ticker"] == "GC=F"
    assert blob["counts"]["read"] == 1 and blob["counts"]["upgraded"] == {"5min": 1}
    assert not list(ckpt.glob("*.tmp"))


def test_a_restart_skips_finished_tickers_and_redoes_the_interrupted_one(
        fake_pass, tmp_path, capsys):
    ckpt = tmp_path / "ckpt"
    fake_pass["fail_on"] = "MSFT"
    with pytest.raises(KeyboardInterrupt):
        bf.run(ckpt)
    capsys.readouterr()
    fake_pass["fail_on"] = None
    fake_pass["calls"].clear()

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["MSFT"]
    assert report.read == 6 and report.upgraded == {"5min": 6}   # restored + redone
    assert capsys.readouterr().out.splitlines()[0] == "resuming: 2/3 tickers restored"
    assert not ckpt.exists()


def test_a_restored_ticker_no_longer_pending_still_counts(fake_pass, tmp_path, capsys):
    """After a first run upgraded all of AAPL to 5min, pending_by_ticker no
    longer returns AAPL; its checkpoint must still be restored and counted."""
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    done = UpgradeReport()
    done.read, done.upgraded = 2, {"5min": 2}
    (ckpt / "AAPL.json").write_text(json.dumps(
        {"fingerprint": bf.FINGERPRINT, "ticker": "AAPL", "counts": done.as_dict()}),
        encoding="utf-8")
    del fake_pass["pending"]["AAPL"]

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["GC=F", "MSFT"]
    assert report.read == 6
    assert capsys.readouterr().out.splitlines()[0] == "resuming: 1/3 tickers restored"


def test_checkpoints_from_other_code_or_corrupt_files_are_redone(fake_pass, tmp_path):
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "AAPL.json").write_text(json.dumps(
        {"fingerprint": "older-code", "ticker": "AAPL", "counts": {"read": 99}}),
        encoding="utf-8")
    (ckpt / "MSFT.json").write_text("{not json", encoding="utf-8")
    (ckpt / "GC_F.json").write_text(json.dumps({"fingerprint": bf.FINGERPRINT}),
                                    encoding="utf-8")   # no ticker / counts

    report = bf.run(ckpt)

    assert [c[0] for c in fake_pass["calls"]] == ["AAPL", "GC=F", "MSFT"]
    assert report.read == 6


def test_an_empty_book_prints_zero_and_a_report_line(fake_pass, tmp_path, capsys):
    fake_pass["pending"] = {}
    report = bf.run(tmp_path / "ckpt")
    assert report.read == 0 and fake_pass["calls"] == []
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "resuming: 0/0 tickers restored"
    assert out[-1].startswith("excursion upgrade:")


def test_since_is_passed_through(fake_pass, tmp_path):
    bf.run(tmp_path / "ckpt", since="2026-10-01T00:00:00+00:00")
    assert fake_pass["since"] == ["2026-10-01T00:00:00+00:00"]


def test_main_writes_the_report_file_and_prints_the_line_last(fake_pass, tmp_path, capsys):
    ckpt, report_file = tmp_path / "ckpt", tmp_path / "out" / "report.txt"
    code = bf.main(["--checkpoint-dir", str(ckpt), "--report-file", str(report_file),
                    "--since", "2026-06-23"])
    assert code == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1].startswith("excursion upgrade:")
    assert report_file.read_text(encoding="utf-8").strip() == out[-1]
    assert fake_pass["since"] == ["2026-06-23"]


def test_cli_defaults_sit_under_logs():
    args = bf.parse_args([])
    assert args.checkpoint_dir == pathlib.Path("logs/backfill_excursions.ckpt")
    assert args.report_file == pathlib.Path("logs/backfill_excursions.report.txt")
    assert args.since is None


@pytest.mark.parametrize("ticker,name", [
    ("AAPL", "AAPL.json"), ("GC=F", "GC_F.json"), ("^VIX", "_VIX.json"),
    ("BRK-B", "BRK-B.json"), ("BTC/USD", "BTC_USD.json"),
])
def test_checkpoint_filenames_are_safe(ticker, name):
    assert bf.checkpoint_name(ticker) == name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backfill_excursions.py`
Expected: FAIL at collection — `FileNotFoundError` for `scripts/ops/backfill_excursions.py`.

- [ ] **Step 3: Write the script**

Create `scripts/ops/backfill_excursions.py`:

```python
#!/usr/bin/env python3
"""v228: upgrade every journal entry's MFE/MAE to the finest archived bars.

Calls the same per-ticker upgrade the bot's daily pass uses
(swingbot.core.analytics.excursion_upgrade) over the whole book, with no time
budget. Each entry's write is a conditional JSONB patch that only moves
`excursion_source` finer, never touches the partner's note, and writes nothing
when the figures are unchanged -- so the bot's pass and this script can meet
on the same entry safely.

Checkpointed per ticker under --checkpoint-dir (git-ignored logs/, a host
mount on the VM): a restart skips finished tickers and redoes an interrupted
one, which is safe because every upgrade is idempotent. The final report line
is printed last and saved to --report-file.

    python scripts/ops/backfill_excursions.py
    python scripts/ops/backfill_excursions.py --since 2026-10-01
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

#: Piped through stdin (`docker compose exec -T bot python - < script.py`)
#: there is no __file__; the container's working directory is the repo root.
ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path.cwd()
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.excursion_upgrade import (  # noqa: E402
    UpgradeReport, pending_by_ticker, upgrade_ticker,
)
from swingbot.core.marketdata.data_store import DATA_DIR  # noqa: E402

#: Change it whenever what a finished ticker means changes; old checkpoints
#: are then ignored and their tickers redone.
FINGERPRINT = "v228-excursion-backfill-1"
DEFAULT_CHECKPOINT_DIR = Path("logs/backfill_excursions.ckpt")
DEFAULT_REPORT_FILE = Path("logs/backfill_excursions.report.txt")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def checkpoint_name(ticker: str) -> str:
    """A filesystem-safe checkpoint filename; the real ticker lives inside."""
    return _UNSAFE.sub("_", ticker) + ".json"


def _restore(directory: Path) -> dict[str, dict]:
    """ticker -> counts for every checkpoint written by this code."""
    done: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(blob, dict) or blob.get("fingerprint") != FINGERPRINT:
            continue
        ticker, counts = blob.get("ticker"), blob.get("counts")
        if isinstance(ticker, str) and isinstance(counts, dict):
            done[ticker] = counts
    return done


def _save(directory: Path, ticker: str, counts: dict) -> None:
    target = directory / checkpoint_name(ticker)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"fingerprint": FINGERPRINT, "ticker": ticker,
                               "counts": counts}), encoding="utf-8")
    tmp.replace(target)


def run(checkpoint_dir: Path, *, since: str | None = None,
        base_dir: str = DATA_DIR) -> UpgradeReport:
    """Upgrade the whole book (or entries closed since `since`), ticker by
    ticker, checkpointing each; returns the combined report."""
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    pending = pending_by_ticker(since)
    restored = _restore(checkpoint_dir)
    todo = [ticker for ticker in sorted(pending) if ticker not in restored]
    print(f"resuming: {len(restored)}/{len(restored) + len(todo)} tickers restored",
          flush=True)
    report = UpgradeReport()
    for counts in restored.values():
        report.absorb(counts)
    for ticker in todo:
        per_ticker = UpgradeReport()
        upgrade_ticker(ticker, pending[ticker], per_ticker, base_dir=base_dir, deadline=None)
        counts = per_ticker.as_dict()
        _save(checkpoint_dir, ticker, counts)
        report.absorb(counts)
    shutil.rmtree(checkpoint_dir, ignore_errors=True)
    print(report.line(), flush=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    parser.add_argument("--since", default=None,
                        help="only entries closed at or after this ISO date (default: whole book)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args.checkpoint_dir, since=args.since)
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(report.line() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Notes for the implementer:
- `pending_by_ticker` and `upgrade_ticker` are imported by name so the test can monkeypatch them on the script module (`bf.pending_by_ticker`); keep the `from ... import` form.
- The script reads and writes only through `excursion_upgrade` — no `JournalStore.add`, no `build_entry`, no direct SQL.
- `logs/` is already git-ignored (`.gitignore` l.113), so local test runs leave nothing to commit.
- Every function stays well under cc 15 (`run` is the largest, ~4).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_backfill_excursions.py`
Expected: PASS (14 tests, counting the 5 parametrized filename cases).

Then check the stdin path parses (no DB access; `--help` exits before any work):

Run: `python - --help < scripts/ops/backfill_excursions.py`
Expected: the argparse usage text, exit 0, no `NameError` for `__file__`.

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/backfill_excursions.py tests/scripts/test_backfill_excursions.py
git commit -m "feat(v228): backfill_excursions.py upgrades the whole journal with per-ticker checkpoints"
```

# Phase 6 — Backend readers

### Task V228-9: Exit-quality trust rule, per-source counts, endpoint `excursion` block

**Model:** sonnet — pure aggregate helpers and a filter in one endpoint, against an exact rule the index fixes.

**Files:**
- Modify: `swingbot/core/analytics/exit_quality.py`
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_exit_quality`, l.485-523)
- Modify: `tests/analytics/test_exit_quality.py`
- Modify: `tests/admin/test_api_v1_analytics.py`

**Interfaces:**
- Consumes (V228-2): `swingbot.core.analytics.mfe_mae.INTRADAY_SOURCES = ("5min", "15min", "hourly")`.
- Produces (V228-14 imports `is_daily_estimate`; V228-11/13 read the JSON):
  - `exit_quality.TRUSTED_MIN_HOLD_DAYS = 2.0`
  - `is_trusted(entry: dict) -> bool` — `excursion_source` in `INTRADAY_SOURCES`, **or** `holding_days >= 2`.
  - `is_daily_estimate(entry: dict) -> bool` — `excursion_source == "daily"` and `holding_days < 2`; a `daily` entry with no usable `holding_days` (missing, `None`, non-numeric, NaN) counts as a short hold, so every `daily` entry is exactly one of trusted or estimate.
  - `excursion_summary(entries: list[dict]) -> dict` = `{"sources": {name or "none": int}, "included": int, "excluded": int, "total": int}` — `included` = entries `is_trusted`, `excluded` = entries `is_daily_estimate`, `total` = all entries. `total - included - excluded` are entries with no source and a short or unknown hold (no figures were recorded for them; they never feed an aggregate either way).
  - `mfe_mae_points` points gain `"excursion_source": str | None`.
  - `GET /api/v1/analytics/exit-quality` gains `"excursion": excursion_summary(entries)`; `efficiency`, `mae` and `scatter` are built from trusted entries only; `coverage` keeps describing every scoped entry.

**Rule (Global Constraints "Trust rule everywhere"):** a figure is an estimate when `excursion_source == "daily"` and the hold is under two days. Aggregates (median efficiency, the MAE histogram, the MFE/MAE scatter) use only entries whose source is intraday or whose `holding_days >= 2`; the excluded count is returned so the UI can say so (V228-13 renders "n of N trades; M short holds on daily bars excluded" from `included`/`total`/`excluded`).

**Suite budget:** `tests/analytics/` holds about 1,121 tests against `max_tests = 1200` before v228; part 1 adds a few to `test_journal.py`. This task adds 7 test functions there (14 collected tests with parametrisation). Step 4 runs `tests/dev/test_suites.py`; if it reports the suite over its limit, stop and report it (the limit is never raised; the controller decides where the overflow moves).

- [ ] **Step 1: Write the failing tests**

Add `import pytest` at the top of `tests/analytics/test_exit_quality.py` (above the existing `from swingbot.core.analytics import exit_quality as eq`), then append:

```python
def _sourced(source, hold, outcome="win", **overrides):
    return _entry(outcome, excursion_source=source, holding_days=hold, **overrides)


@pytest.mark.parametrize("source,hold,trusted,estimate", [
    ("5min", 0.1, True, False),
    ("15min", 0.5, True, False),
    ("hourly", 1.9, True, False),
    ("daily", 1.99, False, True),
    ("daily", 2.0, True, False),     # boundary: two days is trusted
    ("daily", None, False, True),    # unknown hold on daily bars: an estimate
    (None, 3.0, True, False),        # no source, long hold
    (None, 0.5, False, False),       # no source, short hold: no figures at all
])
def test_trust_and_estimate_rules(source, hold, trusted, estimate):
    entry = _sourced(source, hold)
    assert eq.is_trusted(entry) is trusted
    assert eq.is_daily_estimate(entry) is estimate


def test_a_non_numeric_or_nan_hold_on_daily_bars_is_an_estimate():
    assert eq.is_daily_estimate(_sourced("daily", "n/a")) is True
    assert eq.is_daily_estimate(_sourced("daily", float("nan"))) is True
    assert eq.is_trusted(_sourced("daily", float("nan"))) is False


def test_the_threshold_constant_is_two_days():
    assert eq.TRUSTED_MIN_HOLD_DAYS == 2.0


def test_excursion_summary_counts_sources_included_and_excluded():
    entries = [_sourced("5min", 0.2), _sourced("5min", 0.3), _sourced("daily", 0.4),
               _sourced("daily", 4.0), _sourced(None, 0.5), _entry()]
    summary = eq.excursion_summary(entries)
    assert summary == {"sources": {"5min": 2, "daily": 2, "none": 2},
                       "included": 3, "excluded": 1, "total": 6}


def test_excursion_summary_of_an_empty_book():
    assert eq.excursion_summary([]) == {"sources": {}, "included": 0,
                                        "excluded": 0, "total": 0}


def test_scatter_points_carry_the_source():
    points = eq.mfe_mae_points([_sourced("5min", 0.2), _entry()])
    assert [p["excursion_source"] for p in points] == ["5min", None]


def test_aggregates_over_trusted_entries_drop_short_daily_holds():
    entries = [_sourced("5min", 0.2, exit_efficiency=0.9),
               _sourced("daily", 0.3, exit_efficiency=0.1),
               _sourced("daily", 2.5, exit_efficiency=0.5)]
    trusted = [e for e in entries if eq.is_trusted(e)]
    result = eq.efficiency_histogram(trusted, bins=2)
    assert result["n"] == 2 and result["median"] == pytest.approx(0.7)
```

The existing `_entry` helper (no `excursion_source`, no `holding_days`) stays as it is; its three tests keep passing because the existing functions keep their contracts.

Append to `tests/admin/test_api_v1_analytics.py`, below `test_exit_quality_rejects_non_scope_parameters`:

```python
def _journal_entry(trade_id, *, source, hold, efficiency, mfe=2.0, mae=0.4):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI Divergence",
            "horizon_key": "1m", "direction": "bullish", "outcome": "win",
            "r_realized": 1.0, "mfe_r": mfe, "mae_r": mae,
            "exit_efficiency": efficiency, "holding_days": hold,
            "excursion_source": source, "tags": [], "auto_lesson": None, "note": "",
            "opened_at": "2026-08-01T14:00:00+00:00",
            "closed_at": "2026-08-04T15:00:00+00:00",
            "created_at": "2026-08-04T15:00:01+00:00"}


def test_exit_quality_aggregates_trusted_entries_and_reports_the_exclusion(seed, logged_in):
    seed(trades=[_closed("a" * 16), _closed("b" * 16), _closed("c" * 16)])
    seed_store("journal", [
        _journal_entry("a" * 16, source="5min", hold=0.2, efficiency=0.9),
        _journal_entry("b" * 16, source="daily", hold=0.3, efficiency=0.1),   # excluded
        _journal_entry("c" * 16, source="daily", hold=3.0, efficiency=0.5),
    ])
    body = logged_in.get("/api/v1/analytics/exit-quality").get_json()

    assert body["excursion"] == {"sources": {"5min": 1, "daily": 2},
                                 "included": 2, "excluded": 1, "total": 3}
    assert body["efficiency"]["n"] == 2
    assert body["efficiency"]["median"] == pytest.approx(0.7)
    assert body["mae"]["n"] == 2
    assert sorted(p["excursion_source"] for p in body["scatter"]) == ["5min", "daily"]
    # Coverage still describes every scoped entry, excluded ones included.
    assert body["coverage"]["mfe_r"]["total"] == 3


def test_exit_quality_on_an_empty_book_reports_an_empty_excursion_block(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/analytics/exit-quality").get_json()
    assert body["excursion"] == {"sources": {}, "included": 0, "excluded": 0, "total": 0}
    assert body["efficiency"] == {"bins": [], "n": 0, "median": None}
    assert body["scatter"] == []
```

`seed_store` is already imported at the top of `test_api_v1_analytics.py` (`from tests.store_seed import seed_store`); the `seed` fixture seeds trades only, so the journal is seeded directly. The trades and entries are joined by `trade_id`, which `_closed` puts in `"id"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.analytics.exit_quality' has no attribute 'is_trusted'` (and `TRUSTED_MIN_HOLD_DAYS`, `excursion_summary`), plus `KeyError: 'excursion_source'` in the scatter test.

Run `/replicate-prod-db` first if no sibling task in this session synced the replica (the admin tests go through the Postgres stores), then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: FAIL — `KeyError: 'excursion'` in both new tests.

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/exit_quality.py`, replace the module docstring and imports with:

```python
"""Pure aggregates for journalled exit-quality data.

The histograms are winners-only: a losing trade's MAE includes the stop it
hit, so it must not inform the distribution used to tune trade management.
The scatter deliberately includes every outcome because that separation is its
diagnostic value.  Callers supply entries; this module never loads a journal.

v228: an entry's excursion is only trusted when it was measured on intraday
bars or the trade was held two days or more. A short hold measured on daily
bars takes the whole day's range, price before the fill and after the exit
included, so it overstates MFE and MAE; callers filter aggregates through
``is_trusted`` and report ``excursion_summary`` so the exclusion is visible.
``is_daily_estimate`` is the same rule from the other side, for markers.
"""
from __future__ import annotations

from swingbot.core.analytics import metrics
from swingbot.core.analytics.mfe_mae import INTRADAY_SOURCES

_FIELDS = ("mfe_r", "mae_r", "exit_efficiency")
#: Holds this long or longer are trusted even on daily bars.
TRUSTED_MIN_HOLD_DAYS = 2.0
```

Add below `_median` (before `_distribution`):

```python
def _hold_days(entry: dict) -> float | None:
    """The entry's holding_days as a float, or None when missing or unusable."""
    try:
        days = float(entry.get("holding_days"))
    except (TypeError, ValueError):
        return None
    return days if days == days else None


def is_trusted(entry: dict) -> bool:
    """True when the entry's MFE/MAE may feed an aggregate: measured on
    intraday bars, or held at least TRUSTED_MIN_HOLD_DAYS."""
    if entry.get("excursion_source") in INTRADAY_SOURCES:
        return True
    days = _hold_days(entry)
    return days is not None and days >= TRUSTED_MIN_HOLD_DAYS


def is_daily_estimate(entry: dict) -> bool:
    """True when the figures came from daily bars on a hold under two days
    (or of unknown length): the range may be overstated."""
    if entry.get("excursion_source") != "daily":
        return False
    days = _hold_days(entry)
    return days is None or days < TRUSTED_MIN_HOLD_DAYS


def excursion_summary(entries: list[dict]) -> dict:
    """Per-source counts and how many entries the trust rule kept and dropped."""
    sources: dict[str, int] = {}
    for entry in entries:
        name = entry.get("excursion_source") or "none"
        sources[name] = sources.get(name, 0) + 1
    return {"sources": sources,
            "included": sum(1 for entry in entries if is_trusted(entry)),
            "excluded": sum(1 for entry in entries if is_daily_estimate(entry)),
            "total": len(entries)}
```

In `mfe_mae_points`, add the source to the appended point (the rest of the function is unchanged):

```python
        points.append({"mae_r": round(mae, 4), "mfe_r": round(mfe, 4),
                       "r_realized": realized,
                       "outcome": str(entry.get("outcome") or "unknown").lower(),
                       "ticker": entry.get("ticker") or "",
                       "strategy": entry.get("strategy") or "",
                       "excursion_source": entry.get("excursion_source")})
```

In `swingbot/admin/api_v1/analytics.py`, `analytics_exit_quality`, replace the `return jsonify(...)` block (keep everything above it) with:

```python
    # v228: short holds measured on daily bars overstate MFE/MAE; the
    # aggregates use trusted entries only and the excursion block says how
    # many were left out. Coverage keeps describing every scoped entry.
    trusted = [entry for entry in entries if eq.is_trusted(entry)]
    return jsonify({"exit_reasons": m.exit_reason_split(scoped),
                    "unmapped_reasons": m.unmapped_exit_reasons(scoped),
                    "hold_by_outcome": m.hold_by_outcome(scoped),
                    "hold_points": hold_points,
                    "efficiency": eq.efficiency_histogram(trusted),
                    "mae": eq.mae_histogram(trusted),
                    "scatter": eq.mfe_mae_points(trusted),
                    "coverage": eq.coverage(entries),
                    "excursion": eq.excursion_summary(entries),
                    "min_cell_n": MIN_CELL_N,
                    **echo(scope, len(scoped))})
```

Also append one line to the endpoint docstring: `v228: efficiency, mae and scatter use trusted entries only (exit_quality.is_trusted); "excursion" carries the per-source and exclusion counts.`

Notes:
- `mfe_mae` does not import `exit_quality`, so the new import creates no cycle; `exit_quality` already imports `metrics`, which `mfe_mae` also imports.
- `is_trusted` and `is_daily_estimate` take the journal-entry shape (`excursion_source`, `holding_days`). V228-14 calls `is_daily_estimate` from the Discord chart path with that same shape.
- `analytics_exit_quality` gains one comprehension; check it with `python -m radon cc -s swingbot/admin/api_v1/analytics.py | grep analytics_exit_quality` (must stay < 15).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_exit_quality.py`
Expected: PASS (3 existing + 14 new collected tests).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS (existing + 2 new). A **skipped** DB test is not green: start `swing-db` and re-run.

Run: `python scripts/dev/testrun.py file tests/admin/test_v144_pooled_readers.py`
Expected: PASS (the exit-quality journal read still spans every lane).

Run: `python scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: PASS (the `analytics` suite is still under `max_tests`; if not, stop and report, do not raise the limit).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/exit_quality.py swingbot/admin/api_v1/analytics.py tests/analytics/test_exit_quality.py tests/admin/test_api_v1_analytics.py
git commit -m "feat(v228): exit-quality aggregates use trusted excursions only and report the exclusion"
```

### Task V228-10: `excursion_source` in `pnl_calendar.ROW_KEYS` and the three contract tests

**Model:** haiku — one key added to a declared tuple and a row dict, plus the three exact-shape tests that pin it; no logic.

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (`ROW_KEYS` l.35-42; the row dict around l.227-229)
- Modify: `tests/analytics/test_pnl_calendar.py`
- Modify: `tests/admin/test_api_v1_calendar.py` (`assert_shape(body["trades"][0], {...})` in `test_day_trade_shape_carries_the_journal_join`, around l.212-229)
- Modify: `tests/admin/test_api_journal.py` (`_entry` helper l.23-35 and `_ENTRY_SHAPE` l.71-84)

**Interfaces:**
- Consumes: the journal doc field `excursion_source` that V228-4 writes (`"5min"`, `"15min"`, `"hourly"`, `"daily"` or `None`). This task does not import anything from part 1; it reads the field from the joined journal entry and so may run in parallel with groups A–C.
- Produces: every calendar row (`joined_rows`, so `/api/v1/calendar/pnl/day` `trades[]`) carries `"excursion_source": str | None` — the joined entry's value, `None` for an unjournaled trade or an entry without the field. V228-11 adds `CalendarTrade.excursion_source?` in `models.ts`; V228-12 marks the day card from it plus the row's existing `held_hours` (`held_hours < 48` is the two-day rule).

**Why the tests change:** `ROW_KEYS` is declared because `tests/admin/test_api_v1_calendar.py` pins the route's exact key set, and `assert_shape` (`tests/admin/api_v1_contract.py`) fails on an undeclared key as loudly as on a missing one. `GET /trades/<id>/journal` returns the stored entry unfiltered (`swingbot/admin/api_v1/trade_commands.py:358`), so once V228-4 writes the field it reaches `_ENTRY_SHAPE` too; that shape must declare it.

- [ ] **Step 1: Write the failing tests**

In `tests/analytics/test_pnl_calendar.py`, append below `test_a_trade_with_no_journal_entry_still_joins`:

```python
def test_a_row_carries_the_journal_excursion_source():
    entry = _entry("a" * 16)
    entry["excursion_source"] = "5min"
    rows = joined_rows([_trade("a" * 16)], [entry])
    assert rows[0]["excursion_source"] == "5min"


def test_an_unjournaled_or_unlabelled_row_has_no_excursion_source():
    """No entry, or an entry written before v228 labelled it: None, never ''."""
    assert joined_rows([_trade("b" * 16)], [])[0]["excursion_source"] is None
    assert joined_rows([_trade("a" * 16)], [_entry("a" * 16)])[0]["excursion_source"] is None


def test_every_leg_of_a_scaled_out_trade_carries_the_source():
    entry = _entry("a" * 16)
    entry["excursion_source"] = "daily"
    rows = joined_rows([_scaled_trade("a" * 16)], [entry])
    assert [r["excursion_source"] for r in rows] == ["daily", "daily"]
```

`_scaled_trade` is defined further down the file (l.~321); module-level helpers resolve at call time, so the order is fine. The existing `test_a_row_carries_exactly_the_declared_keys` needs no edit: it compares a row against `set(ROW_KEYS)` and passes once both carry the key.

In `tests/admin/test_api_v1_calendar.py`, `test_day_trade_shape_carries_the_journal_join`, add the key to the `assert_shape(body["trades"][0], {...})` dict, after `"return_pct": NULLABLE_NUMBER, "exit_reason": str,`:

```python
        # v228 -- which bars measured the joined entry's MFE/MAE.
        "excursion_source": NULLABLE_STR,
```

and after the existing `assert body["trades"][0]["auto_lesson"] == "Held to target."` add:

```python
    assert body["trades"][0]["excursion_source"] is None   # _entry carries no source
```

Then add a test below it:

```python
def test_day_trade_carries_the_entry_excursion_source(seed, logged_in):
    entry = _entry("a" * 16)
    entry["excursion_source"] = "daily"
    seed(trades=[_trade("a" * 16)], entries=[entry])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    assert body["trades"][0]["excursion_source"] == "daily"
```

In `tests/admin/test_api_journal.py`:

1. Give `_entry` an `excursion_source` keyword (default `"daily"`, the value every pre-v228 entry carries after V228-7's revision) and write it into the record:

```python
def _entry(trade_id, *, outcome="loss", tags=(), note="", lesson=None,
           mfe_r=1.4, mae_r=0.2, exit_efficiency=0.31, closed_at="2026-08-12T15:00:00+00:00",
           excursion_source="daily"):
    """One journal.json record, as `build_entry` writes it."""
    return {
        "trade_id": trade_id, "ticker": "AAPL", "strategy": "RSI Divergence",
        "horizon_key": "1m", "direction": "bullish", "tier": "A",
        "badge": "VALIDATED", "quality_score": 72, "outcome": outcome,
        "r_realized": -1.0, "mfe_r": mfe_r, "mae_r": mae_r,
        "exit_efficiency": exit_efficiency, "holding_days": 3.2,
        "excursion_source": excursion_source,
        "tags": list(tags), "auto_lesson": lesson, "note": note,
        "opened_at": "2026-08-09T10:00:00+00:00", "closed_at": closed_at,
        "created_at": "2026-08-12T15:00:01+00:00",
    }
```

2. Declare it in `_ENTRY_SHAPE`, after `"holding_days": NULLABLE_NUMBER, "tags": list,`:

```python
    # v228 -- "5min", "15min", "hourly" or "daily"; null when no bars covered it.
    "excursion_source": (str, type(None)),
```

3. Append a test below `test_journal_entry_carries_the_excursion_figures`:

```python
def test_journal_entry_carries_its_excursion_source(seed, logged_in):
    """The SPA marks a short hold measured on daily bars; it needs the source."""
    seed(trades=[_trade("c" * 16)], entries=[_entry("c" * 16, excursion_source="5min")])
    entry = logged_in.get("/api/v1/trades/" + "c" * 16 + "/journal").get_json()["entry"]
    assert entry["excursion_source"] == "5min"


def test_journal_entry_with_no_bars_has_a_null_source(seed, logged_in):
    seed(trades=[_trade("d" * 16)],
         entries=[_entry("d" * 16, mfe_r=None, mae_r=None, exit_efficiency=None,
                         excursion_source=None)])
    entry = logged_in.get("/api/v1/trades/" + "d" * 16 + "/journal").get_json()["entry"]
    assert_shape(entry, _ENTRY_SHAPE, where="entry")
    assert entry["excursion_source"] is None
```

Before writing these two, check the ids `"c" * 16` and `"d" * 16` are not already seeded by another test in the same file in a way that collides (each test seeds its own store, so reuse across tests is fine; only a duplicate test *name* would clash).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL — `KeyError: 'excursion_source'` in the three new tests.

Run `/replicate-prod-db` first if no sibling task in this session synced the replica, then:

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: FAIL — `trades[0]: missing key(s) ['excursion_source']` and `KeyError` in the new test.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_journal.py`
Expected: PASS already for the shape tests (the route returns the stored entry as seeded, so the new key is present once `_entry` writes it) — this file pins the contract rather than driving new code; its new tests pass as soon as the helper and shape are edited.

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/pnl_calendar.py`, extend `ROW_KEYS`:

```python
ROW_KEYS = (
    "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction", "day",
    "opened_at", "closed_at", "outcome", "pnl_amount", "fx_missing", "r_multiple", "mfe_r", "mae_r",
    "exit_efficiency", "tags", "auto_lesson", "leg_index", "leg_total",
    # v165 D1 -- read from the part, never re-derived (see `_detail_fields`).
    "entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares",
    "held_hours", "return_pct", "exit_reason",
    # v228 -- which bars measured the journal entry's MFE/MAE (None: unjournaled
    # or no bars). The day card marks a daily-bar figure on a hold under 48h.
    "excursion_source",
)
```

In the row dict (around l.227-229), directly after `"exit_efficiency": _float_or_none(entry.get("exit_efficiency")),` add:

```python
        "excursion_source": entry.get("excursion_source") or None,
```

(`entry` is the joined journal entry, `{}` for an unjournaled trade, so `.get` returns `None` there; `or None` turns a stray empty string into `None`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: PASS (existing + 3 new).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: PASS (existing + 1 new).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_journal.py`
Expected: PASS (existing + 2 new). A **skipped** DB test is not green: start `swing-db` and re-run.

Complexity: the row builder gains one dict entry and no branch; `python -m radon cc -s -n C swingbot/core/analytics/pnl_calendar.py` lists nothing new.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py tests/admin/test_api_v1_calendar.py tests/admin/test_api_journal.py
git commit -m "feat(v228): calendar rows and the journal contract carry excursion_source"
```
