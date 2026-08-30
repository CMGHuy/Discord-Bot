# v67 — Part 6: Cleanup and close-out (tasks P6-07…P6-12)

> Continuation of `2026-08-29-v67-json-to-postgres_6a-cutover.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_6a` file before starting any task here** — the
> Parallelisation note, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P6-07: Flip production to db, one group at a time — TOUCHES PRODUCTION

The import has run and `parity_report --all` is clean. Now `DB_STORES` moves,
in groups, with a soak between them. **Nothing in this task is committed to the
repo** except the record of what was done — `DB_STORES` is a production `.env`
value.

**Files:**
- Modify: `docs/deploy/DB_CUTOVER.md` (append the flip sequence and the log)
- Test: `tests/db/test_stage_rollback.py`

**Interfaces:**
- Consumes: `stages` (P1-10), the parity report (P2-06).
- Produces: nothing in code. The deliverable is a production state plus its
  written record.

**Why groups and not all at once.** Every store's `db` stage was tested
individually, and the risk left is interaction — two stores whose combined
behaviour differs from either alone. Groups of related stores bound how much has
to be reasoned about when something looks wrong, and a rollback is one `.env`
edit either way.

- [ ] **Step 1: Write the rollback test**

Rolling back is the property that makes this safe, so it gets a test rather than
a promise. Create `tests/db/test_stage_rollback.py`:

```python
"""A stage rolls back by editing DB_STORES and reloading. No redeploy."""
import os

import pytest

from swingbot import config
from swingbot.core.db import stages


@pytest.fixture
def isolated(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_a_stage_change_takes_effect_without_a_restart(isolated, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert stages.reads_db("trades") is True
    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    assert stages.reads_db("trades") is False
    assert stages.writes_db("trades") is True
    monkeypatch.setattr(config, "DB_STORES", "")
    assert stages.writes_db("trades") is False


def test_rolling_back_from_db_to_dual_restores_file_reads(isolated, monkeypatch):
    from swingbot.core.infra.jsonio import atomic_write_json
    from swingbot.core.tracking.performance import TradeLog

    row = dict(trade_id="ROLLBACK-1", ticker="AAPL", strategy="RSI",
               horizon="2w", direction="bullish", status="open",
               opened_at="2026-01-02T15:00:00+00:00")
    atomic_write_json(os.path.join(isolated, "trades.json"), [row])

    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert TradeLog().get_trades(status="open", limit=None) == []

    monkeypatch.setattr(config, "DB_STORES", "trades:dual")
    assert [t["trade_id"] for t in
            TradeLog().get_trades(status="open", limit=None)] == ["ROLLBACK-1"]


def test_one_store_rolling_back_does_not_move_another(isolated, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:dual,plans:db")
    assert stages.reads_db("trades") is False
    assert stages.reads_db("plans") is True


def test_an_unknown_store_in_the_string_is_ignored_not_fatal(isolated,
                                                              monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "trades:db,typo_store:db")
    assert stages.reads_db("trades") is True
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/db/test_stage_rollback.py
```

Expected: `0 failed`.

- [ ] **Step 3: Flip, group by group**

On the VM, for each group: edit `.env`, `docker compose restart bot admin`,
then watch. **Soak each group through at least one full trading session before
the next**, because the failure this is looking for is behavioural, not
immediate.

| Order | `DB_STORES` addition | Watch for |
|---|---|---|
| 1 | `flags:db,heartbeat:db,scheduled_jobs:db` | the admin dashboard dot, the pause toggle, a manual `!check` |
| 2 | `jobs:db,preferences:db,settings_audit:db,tuning:db` | starting a tune job, its progress ticking, its result rendering |
| 3 | `telemetry:db,shadow:db,retrospective:db,scan_snapshots:db,analytics:db` | the risk page sparkline, a retrospective posting |
| 4 | `ticker_directory:db,meta_cache:db,rs_cache:db,fold_trades:db` | watchlist search, company names in alerts |
| 5 | `state:db,watchlist:db,journal:db,account:db,killswitch:db` | a scan producing the same alerts it did yesterday |
| 6 | `trades:db,plans:db,starred_plans:db` | **the whole system.** Alerts, fills, closes, `!performance` |
| 7 | `settings:db` | change a setting in the admin UI, confirm the bot logs the reload |
| 8 | `events:db` | the SPA updating live with no refresh |

Group 6 is last among the data stores and group 8 last overall, deliberately:
trades and plans are the records every number is derived from, and the event
listener is the only change a user sees directly.

**Between every group**, run `python scripts/db/parity_report.py --all` while
the previous groups are at `db` and the rest are at `json`. A store at `db` will
report `MISSING` for anything written since it stopped writing files — that is
expected and is not a failure; what matters is that no store still at `dual`
reports a `MISMATCH`.

- [ ] **Step 4: Record it**

Append to `docs/deploy/DB_CUTOVER.md`: the date and time of each group's flip,
the `DB_STORES` value after each, anything that looked wrong and what was done,
and the final value. Per `CLAUDE.md`, **a live change is not done until it is
mirrored back into this repo and committed** — for this task the mirrored
artefact is the record, since `DB_STORES` itself is a `.env` value that is
never committed.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy/DB_CUTOVER.md tests/db/test_stage_rollback.py
git commit -m "docs(v67): record the production stage flip"
```

---

### Task P6-08: Delete the JSON store paths

Every store has run at `db` in production. The `json` and `dual` branches are
now unreachable code that a reader still has to understand.

**Files:**
- Modify: every store module Parts 2, 3 and 5 branched
- Modify: `swingbot/core/db/stages.py`
- Test: `tests/db/test_no_json_paths.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `stages.py` keeps `stage_for` and the three predicates, but `JSON`
  and `DUAL` are removed from `STAGES` — see below.

**What is deleted and what is not.** The file-reading and file-writing branches
go. `swingbot/core/infra/jsonio.py` **stays** — the files that remain (`.env`,
`validation_registry.json`, `sp500.json`, `etfs.json`, `VERSION.json`) still
need atomic writes, and the spec says so explicitly.

**`DB_STORES` keeps working, and this is the one judgement call in this task.**
Deleting the stage machinery entirely would be tidier and would remove the
rollback that made every step of this plan reversible — including the rollback
someone needs three months from now when a bug is traced to this migration. The
resolution: keep `stage_for`, delete `json` and `dual` as *valid* stages, and
make a `.env` still naming one fail loudly at startup rather than silently
reading a file that no longer exists.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_no_json_paths.py`:

```python
"""No code path reads a migrated JSON file."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "swingbot"

# Files that STAY. jsonio.py survives the migration for exactly these.
KEEPS = {"validation_registry.json", "sp500.json", "etfs.json",
         "VERSION.json", "version_history.json", ".env", ".env.bak"}

MIGRATED = {
    "trades.json", "plans.json", "starred_plans.json", "account.json",
    "journal.json", "state.json", "watchlist.json", "admin_jobs.json",
    "scheduled_jobs.json", "ui_preferences.json", "killswitch.json",
    "bot_heartbeat.json", "manual_close_notify.json", "settings_audit.jsonl",
    "ticker_directory.json", "analytics_snapshot.json", "scan_snapshots.json",
    "scan_telemetry.jsonl", "shadow_plans.jsonl", "retrospective_history.json",
    "ticker_meta_cache.json", "rs_cache.json",
    "scan_running.flag", "scan_paused.flag", "trigger_check.flag",
    "stop_scan.flag",
}


def _sources():
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("filename", sorted(MIGRATED))
def test_no_module_names_a_migrated_file(filename):
    hits = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if filename in line and not line.lstrip().startswith("#"):
                hits.append(f"{path.relative_to(REPO).as_posix()}:{i}")
    assert not hits, f"{filename} is still referenced: {hits}"


def test_jsonio_survives():
    """It is not dead code -- .env, the git-committed evidence files and
    VERSION.json still need atomic writes."""
    assert (SRC / "core" / "infra" / "jsonio.py").exists()


def test_something_still_uses_jsonio():
    users = [p.relative_to(REPO).as_posix() for p in _sources()
             if "jsonio" in p.read_text(encoding="utf-8", errors="ignore")
             and p.name != "jsonio.py"]
    assert users, "jsonio has no callers left; re-check the KEEPS list"


def test_json_and_dual_are_no_longer_valid_stages():
    from swingbot.core.db import stages
    assert stages.STAGES == ("db",)


def test_a_stale_db_stores_value_fails_loudly(monkeypatch, caplog):
    """A .env still saying trades:json must not silently read a file that no
    longer exists."""
    from swingbot import config
    from swingbot.core.db import stages
    monkeypatch.setattr(config, "DB_STORES", "trades:json")
    with pytest.raises(ValueError, match="no longer supported"):
        stages.validate_db_stores()


def test_stage_for_still_answers_db_for_everything(monkeypatch):
    from swingbot import config
    from swingbot.core.db import stages
    monkeypatch.setattr(config, "DB_STORES", "")
    assert stages.stage_for("trades") == stages.DB
    assert stages.reads_db("anything") is True
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_no_json_paths.py -q
```

Expected: most `test_no_module_names_a_migrated_file` parametrisations fail,
listing exactly what to delete. **That list is this task's work plan** — work
through it rather than grepping independently.

- [ ] **Step 3: Delete the branches**

For each store module, remove the `stages.writes_json(...)` / `not
stages.reads_db(...)` branch and its body, leaving the database path
unconditional. The path constants those branches used (`_STOP_FILE`,
`_PAUSE_FILE`, `_HEARTBEAT_FILE`, `TELEMETRY_PATH`, `RS_CACHE_PATH`,
`DEFAULT_PATH`, `_STARRED_PATH`, `_SNAPSHOT_PATH`, `KILLSWITCH_PATH`,
`_HISTORY_PATH`, `_TICKER_META_CACHE_PATH`, `_default_config_path`,
`_jobs_path`, `_scheduled_jobs_path`, `_preferences_path`, `_audit_log_path`)
go with them.

**The `path=` parameters those functions take are a separate decision.** Several
exist so tests can isolate themselves from the real `data/` — and with no file
backend there is nothing left for them to point at. Remove the parameter where
its only remaining caller is a test, and update those tests to use `db_conn`.
Keep it where a *script* passes an explicit path for a real reason
(`shadow_parity_report.py` reading an archived file, for one).

- [ ] **Step 4: Narrow the stage machinery**

In `swingbot/core/db/stages.py`:

```python
DB = "db"
STAGES = (DB,)

#: Stages that existed during the v67 migration and no longer do. Named rather
#: than forgotten so a .env still carrying one fails with a sentence instead of
#: a KeyError.
RETIRED_STAGES = ("json", "dual")


def validate_db_stores() -> None:
    """Raise if DB_STORES names a retired stage. Called at startup.

    This is the one place the plan chooses a loud failure over a safe default.
    Everywhere else a bad DB_STORES entry falls back to json, because json was
    today's behaviour and could not be wrong. There is no json any more: a
    value saying trades:json describes a backend that does not exist, and
    silently treating it as db would hide a stale deployment config.
    """
    for chunk in (config.DB_STORES or "").split(","):
        entry = chunk.strip()
        if not entry or ":" not in entry:
            continue
        _name, stage = (p.strip().lower() for p in entry.split(":", 1))
        if stage in RETIRED_STAGES:
            raise ValueError(
                f"DB_STORES contains {entry!r}, but the {stage!r} stage was "
                f"removed in v67 -- every store is Postgres-backed. Remove "
                f"this entry from .env."
            )
```

`stage_for` returns `DB` unconditionally; `writes_json` is deleted; `writes_db`
and `reads_db` return `True`. Keep them: dozens of call sites read better as
`if reads_db("trades")` than as nothing, and P6-08's successor plan (SQL
pushdown) will want the seam.

Call `validate_db_stores()` from `config.log_startup_config()`.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_no_json_paths.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. Expect a substantial number of existing tests to need
updating — they were written against the file backend and passed an explicit
`path=`. That is the work, not a surprise.

- [ ] **Step 6: Commit**

```bash
git add swingbot scripts tests
git commit -m "refactor(v67): delete the JSON store paths"
```

---

### Task P6-09: Delete the file watcher

`FileWatcher` has been the fallback since P3-23 and is now unreachable.

**Files:**
- Delete: `swingbot/admin/events/watcher.py`
- Delete: `tests/admin/test_events_watcher.py`
- Modify: `swingbot/admin/events/broker.py`
- Modify: `swingbot/admin/events/db_listener.py` (adopt `WATCHED_EVENTS`)
- Test: `tests/admin/test_sse_contract.py` (re-point its import)

**Interfaces:**
- Consumes: `DbEventListener` (P3-19).
- Produces: `WATCHED_EVENTS` moves from `watcher.py` to
  `swingbot/core/db/events.py`, since that is now the only place the taxonomy
  lives.

**Moving `WATCHED_EVENTS` rather than deleting it.** It is the SPA's contract
and `stream.py` imports it. Deleting the module it lives in without rehoming it
would break the stream; leaving it in a file that otherwise no longer exists is
not an option either.

- [ ] **Step 1: Rehome the constant**

In `swingbot/core/db/events.py`, add below `TABLE_CHANNELS`:

```python
#: Every event type the stream can raise from storage. `resync` and `ping` are
#: added by stream.py and have no table behind them.
#:
#: Moved here from admin/events/watcher.py when that module was deleted in v67:
#: it is the SPA's contract, and this is now the only place the table-to-concern
#: taxonomy lives.
WATCHED_EVENTS = frozenset(TABLE_CHANNELS.values())
```

- [ ] **Step 2: Update the importers of it**

```bash
git grep -n "WATCHED_EVENTS\|events.watcher\|from .watcher\|FileWatcher" -- swingbot tests
```

Every hit moves to `from swingbot.core.db.events import WATCHED_EVENTS` or is
deleted. In `broker.py`, `_default_watcher` collapses to
`return DbEventListener(emit)` and the `FileWatcher` import goes; its
`_release` docstring loses the "a FileWatcher primes itself" clause, keeping the
"avoids racing a thread winding down from stop()" reason, which still holds.

- [ ] **Step 3: Write the failing test**

Add to `tests/admin/test_sse_contract.py`:

```python
def test_the_file_watcher_is_gone():
    import pathlib
    repo = pathlib.Path(__file__).resolve().parents[2]
    assert not (repo / "swingbot" / "admin" / "events" / "watcher.py").exists()


def test_nothing_imports_the_watcher():
    import pathlib
    repo = pathlib.Path(__file__).resolve().parents[2]
    hits = [p.relative_to(repo).as_posix()
            for p in (repo / "swingbot").rglob("*.py")
            if "events.watcher" in p.read_text(encoding="utf-8", errors="ignore")
            or "FileWatcher" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, hits


def test_watched_events_is_unchanged_after_the_move():
    from swingbot.core.db.events import WATCHED_EVENTS
    assert set(WATCHED_EVENTS) == EXPECTED_EVENTS
```

and re-point that file's own `from swingbot.admin.events.watcher import
WATCHED_EVENTS` to the new home.

- [ ] **Step 4: Delete**

```bash
git rm swingbot/admin/events/watcher.py tests/admin/test_events_watcher.py
```

`tests/admin/test_no_double_watcher.py`'s `test_no_stat_calls_on_data_at_the_db_stage`
stays — it is now a stronger claim than when it was written, because there is no
watcher left that could stat anything.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_sse_contract.py
python scripts/dev/testrun.py file tests/admin/test_events_broker.py
python scripts/dev/testrun.py file tests/admin/test_no_double_watcher.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot tests
git commit -m "refactor(v67): delete the file watcher, rehome WATCHED_EVENTS"
```

---

### Task P6-10: Delete reload(), refresh() and the stale-snapshot machinery

`TradeLog.reload()`, `TradeLog.refresh()` and `PlanStore.reload()` existed
solely to narrow the whole-file clobber window. Parts 2 neutralised them; this
deletes them and their callers.

**Files:**
- Modify: `swingbot/core/tracking/performance.py`, `swingbot/core/planning/plan_store.py`
- Modify: every caller (`git grep -n "\.reload()\|\.refresh()" -- swingbot`)
- Modify: `swingbot/core/marketdata/watchlist.py` (delete `DEFAULT_PATH`)
- Test: `tests/db/test_no_stale_snapshot_machinery.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing. This task only removes.

**Do not delete `config.reload()` or `config.auto_reload_if_changed()`.** They
are a different thing that shares a name: they re-read `.env` for secrets, which
P4-09 established as a path that stays.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_no_stale_snapshot_machinery.py`:

```python
"""The methods that existed to narrow a race that no longer exists."""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_tradelog_has_no_reload_or_refresh():
    from swingbot.core.tracking.performance import TradeLog
    assert not hasattr(TradeLog, "reload")
    assert not hasattr(TradeLog, "refresh")


def test_planstore_has_no_reload():
    from swingbot.core.planning.plan_store import PlanStore
    assert not hasattr(PlanStore, "reload")


def test_nothing_calls_them():
    hits = []
    for path in (REPO / "swingbot").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if ("_log.reload()" in line or "store.reload()" in line
                    or ".refresh()" in line):
                hits.append(f"{path.relative_to(REPO).as_posix()}:{i}")
    assert not hits, hits


def test_config_reload_survives():
    """A different thing that shares a name: .env secrets still reload."""
    from swingbot import config
    assert callable(config.reload)
    assert callable(config.reload_settings)


def test_the_watchlist_default_path_constant_is_gone():
    from swingbot.core.marketdata import watchlist
    assert not hasattr(watchlist, "DEFAULT_PATH")


def test_a_long_lived_store_sees_another_processes_write(db_committed,
                                                          monkeypatch):
    """The property that made reload() unnecessary, asserted once more at the
    point the method is removed."""
    from swingbot import config
    from swingbot.core.db.repositories.trades import TradeRepository
    from swingbot.core.tracking.performance import TradeLog

    monkeypatch.setattr(config, "DB_STORES", "")
    long_lived = TradeLog()
    assert long_lived.get_trades(status="open", limit=None) == []
    TradeRepository().upsert(dict(
        trade_id="AFTER", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="open",
        opened_at="2026-01-02T15:00:00+00:00"))
    assert [t["trade_id"] for t in
            long_lived.get_trades(status="open", limit=None)] == ["AFTER"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_no_stale_snapshot_machinery.py -q
```

Expected: the first three fail.

- [ ] **Step 3: Delete them and their callers**

```bash
git grep -n "\.reload()\|\.refresh()" -- swingbot
```

Filter out `config.reload()`. The remaining hits are in `plan_manager.py`
(`run_manager_tick`) and the scan engine; delete the call lines. Where a call
was the only statement in a `with _LOCK:` block, remove the block too.

`self._trades` and `self._plans` become unused once the stores read through
`_all()` — delete the attributes, their `_load()` calls in `__init__`, and
`_load`/`_save` themselves. `PlanStore.__init__` reduces to storing nothing at
all, which is correct: a repository-backed store has no state to hold.

`_LOCK` in both modules protected the in-memory list against threads in one
process. With no in-memory list there is nothing for it to protect —
`UPDATE ... WHERE` is atomic on the server. Delete both, and say so in the
commit rather than leaving a lock nobody can explain.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_no_stale_snapshot_machinery.py
python scripts/dev/testrun.py file tests/tracking/test_performance.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot tests
git commit -m "refactor(v67): delete reload/refresh and the in-memory snapshots

The module-level threading.Locks go with them: they protected an in-memory list
that no longer exists, and row-level UPDATE ... WHERE is atomic server-side."
```

---

### Task P6-11: The documentation sweep

Nine documents describe a system that no longer exists in the way they describe
it. This is one task rather than nine because they must agree with each other,
and a reader who finds two of them disagreeing trusts neither.

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `.codex/AGENTS.md`
- Modify: `docs/claude/architecture.md`, `docs/claude/known-traps.md`,
  `docs/claude/testing-cost.md`, `docs/claude/working-conventions.md`
- Modify: `docs/deploy/DOCKER.md`, `docs/deploy/DEPLOY_HETZNER.md`
- Modify: `docs/setup.md`
- Test: `tests/test_docs_consistency.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing in code.

**`CLAUDE.md` is at its 200-line budget.** Anything added there displaces
something — move the displaced content into the matching `docs/claude/*.md`,
per that file's own rule. The Postgres facts that must fire unprompted are two:
the database is part of the stack, and the test tier needs it running.

- [ ] **Step 1: Write the consistency test**

Create `tests/test_docs_consistency.py`:

```python
"""The docs must not describe a JSON persistence layer."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

DOCS = [
    "README.md", "CLAUDE.md", ".codex/AGENTS.md",
    "docs/claude/architecture.md", "docs/claude/known-traps.md",
    "docs/claude/testing-cost.md", "docs/deploy/DOCKER.md",
    "docs/deploy/DEPLOY_HETZNER.md", "docs/setup.md",
]

STALE = [
    r"JSON persistence under `?data/`?",
    r"no database",
    r"trades\.json",
    r"plans\.json",
]


@pytest.mark.parametrize("doc", DOCS)
def test_the_doc_exists(doc):
    assert (REPO / doc).exists(), doc


@pytest.mark.parametrize("doc", DOCS)
def test_no_doc_claims_json_persistence(doc):
    text = (REPO / doc).read_text(encoding="utf-8")
    for pattern in STALE:
        for match in re.finditer(pattern, text, re.I):
            line = text[:match.start()].count("\n") + 1
            # A historical reference is fine if it says so.
            context = text.splitlines()[line - 1]
            if re.search(r"\b(was|were|used to|before v67|until v67|"
                         r"historical|v67 replaced)\b", context, re.I):
                continue
            pytest.fail(f"{doc}:{line} still describes JSON persistence: "
                        f"{context.strip()}")


def test_claude_md_is_within_its_budget():
    lines = (REPO / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, f"CLAUDE.md is {len(lines)} lines (budget 200)"


def test_claude_md_mentions_the_database_and_the_test_requirement():
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8").lower()
    assert "postgres" in text
    assert "db-test" in text or "test database" in text


def test_the_architecture_doc_documents_core_db():
    text = (REPO / "docs/claude/architecture.md").read_text(encoding="utf-8")
    for needle in ("core/db", "codec", "DB_STORES", "alembic"):
        assert needle.lower() in text.lower(), needle


def test_testing_cost_has_been_rebaselined():
    text = (REPO / "docs/claude/testing-cost.md").read_text(encoding="utf-8")
    assert "v67" in text, "the suite got slower and the baseline was not updated"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_docs_consistency.py -q
```

Expected: a list of every stale claim. **That list is the work plan.**

- [ ] **Step 3: Update each document**

- **`README.md`** — "JSON persistence under `data/`; no database" becomes
  PostgreSQL 18 with the `data/` files that remain named explicitly. Add
  `docs/deploy/DB_LOCAL_DEV.md` and `docs/claude/schema-evolution.md` to the
  documentation index.
- **`CLAUDE.md`** — the "What this is" paragraph gains Postgres; add one line
  under Commands for `docker compose --profile test up -d db-test`. Move
  whatever this displaces into `docs/claude/architecture.md`.
- **`docs/claude/architecture.md`** — the `core/db/` section P1-14 added,
  expanded now that every part has landed: the eleven-package map gains a
  twelfth, and the module table gains `codec`, `engine`, `schema`,
  `repositories/`, `notify`, `stages`, `migrations/`.
- **`docs/claude/known-traps.md`** — the two OHLCV caches entry is unaffected.
  Add: `merge_doc` omits a NULL promoted column (so a promoted field's absence
  and `None` are the same thing); a `NOTIFY` fires only on commit, so a test
  using `db_conn` never sees one; `db_engine` and `db_engine_empty` both reset
  the schema and cannot be used in the same session.
- **`docs/claude/testing-cost.md`** — **re-measure and re-baseline.** The spec
  says the fast tier gets slower and that hiding it is not an option. Run
  `python scripts/dev/testrun.py fast` and `... full` three times each, record
  the numbers, and note that the database tier is the difference.
- **`docs/claude/working-conventions.md`** — a production change now includes
  `DB_STORES` and any hand-run migration; both are mirrored back.
- **`docs/deploy/DOCKER.md`** / **`DEPLOY_HETZNER.md`** — the `db` service, the
  `pgdata` volume, `down -v` destroying it, backups, restore, and the cutover
  runbook pointer.
- **`docs/setup.md`** — a first-time setup now starts Postgres and runs
  `alembic upgrade head`.
- **`.codex/AGENTS.md`** — condensed to match, per `CLAUDE.md`'s one-way sync
  rule. Never the reverse.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_docs_consistency.py
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
```

Expected: `0 failed`. The second is there because `.claude/hooks/guardrails.py`
denies patterns `CLAUDE.md` forbids in prose — if the edits changed one of those
sentences, that test says so.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md .codex/AGENTS.md docs tests/test_docs_consistency.py
git commit -m "docs(v67): describe the PostgreSQL persistence layer"
```

---

### Task P6-12: Full-suite verification and close-out

The plan verifies itself **once**, here. A red result is the start of the work,
not a reason to re-litigate earlier tasks.

**Run this last, after Parts 7 and 8.** Numbering is not execution order: this
is the plan's single full-suite gate and its release commit, so it has to cover
every part's code. Confirm both have landed before starting:

```bash
git fetch
grep -rn "^### Task P[78]-" docs/superpowers/plans/ | wc -l   # expect 18
python -c "from swingbot.core.db import profiles, datasets; print('part 7 ok')"
python -c "from swingbot.core.db.schema import promoted_for; \
           assert 'r_multiple' in promoted_for('trades'); print('part 8 ok')"
```

**Files:**
- Modify: `VERSION.json`
- Modify: `frontend/src/assets/version_history.json` (regenerated)
- Move: every `2026-08-29-v67-*` file into `implemented/`

**Interfaces:**
- Consumes: everything.
- Produces: the release.

- [ ] **Step 1: Run the full suite**

```bash
docker compose --profile test up -d db-test
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. Dispatch the `test-runner` subagent if the
output should stay out of this session's context.

**If it is red, fix forward from the failures the run names.** Do not re-run
earlier tasks' narrow tests hoping the failure goes away.

- [ ] **Step 2: Run the frontend suite**

This plan touched `frontend/` only via `version_history.json`, which is
generated. Run it anyway, once — the rule is "every suite the plan's own files
touch":

```bash
cd frontend && npm test && cd ..
```

Expected: green.

- [ ] **Step 3: Run the slow tier explicitly**

`testrun.py full` includes it, but the notification and end-to-end tests are the
ones most likely to be flaky under load and most important in this plan. Confirm
them on their own:

```bash
python -m pytest -m slow tests/db/ tests/admin/ tests/infra/ -q
```

Expected: `0 failed`.

- [ ] **Step 4: Bump the version**

Per the spec's header: `bot minor (1.5.0 → 1.6.0)`, `ui patch (1.9.2 → 1.9.3)`.

The `ui` bump is a patch and not a minor even though the admin gained a
per-record export and lost the Docker socket: the export is an inspection tool
replacing `cat`, not a new capability a user asked for. Two independent
`VERSION.json` lines, per `docs/claude/working-conventions.md`.

```bash
python - <<'PY'
import json, datetime as dt
p = "VERSION.json"
v = json.load(open(p, encoding="utf-8"))
now = dt.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
v["bot"], v["bot_updated"] = "1.6.0", now
v["ui"], v["ui_updated"] = "1.9.3", now
open(p, "w", encoding="utf-8").write(json.dumps(v, indent=2) + "\n")
print(v)
PY
```

- [ ] **Step 5: Regenerate the version history**

**This step is not optional and is easy to miss.** The pre-commit gate runs
*before* the bump, so it structurally cannot catch a stale
`version_history.json`:

```bash
python scripts/dev/build_version_matrix.py
git diff --stat frontend/src/assets/version_history.json
```

Expected: a non-empty diff carrying `1.6.0` and `1.9.3`. An empty diff means the
script did not pick up the bump — investigate before committing.

- [ ] **Step 6: Close the documents out**

Per `docs/claude/document-lifecycle.md`:

```bash
git mv docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md \
       docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-29-v67-json-to-postgres_*.md \
       docs/superpowers/plans/implemented/
```

Then amend the spec's header if either prediction came out wrong. Both are worth
checking honestly:

- **`Bump:`** — did the `ui` half land as a patch? If the export endpoint or the
  settings page turned out to change what a user sees, say so in one clause.
- **`Edge: none (integrity)`** — this one should hold. If any part of the work
  measurably changed expectancy, that is a finding worth a sentence, and it
  almost certainly means something else changed too.

Add a short "What actually happened" section to the spec: the measured suite
timings from P6-11, anything the production import surfaced, and any store whose
promotion criteria turned out wrong.

- [ ] **Step 7: Verify the tree is clean and the branch is current**

```bash
git fetch
git status --short
git log --oneline origin/main..HEAD | head -40
git rev-list --count origin/main..HEAD
```

Confirm nothing untracked belongs in the commit and that `main` has not moved
underneath this work. If it has, rebase before merging — never force-push over
it.

- [ ] **Step 8: Commit**

```bash
git add VERSION.json frontend/src/assets/version_history.json \
        docs/superpowers/specs docs/superpowers/plans
git commit -m "release(v67): bot 1.6.0, ui 1.9.3 -- PostgreSQL persistence

Replaces the data/*.json persistence layer with PostgreSQL 18. A hybrid schema
(promoted typed columns plus a doc JSONB column, joined by a codec) keeps
schema change as cheap as editing a Python dict, and call sites keep the flat
dict contract they had.

Closes the lost-update bug: TradeLog._save() and PlanStore._save() serialised
an entire in-memory list over the whole file on every write, guarded only by a
module-level threading.Lock that protected nothing across the bot and admin
containers. Row-level UPDATE ... WHERE has no such window.

LISTEN/NOTIFY replaces the admin's stat()-based file watcher; the SSE contract
is unchanged. Non-sensitive settings move to a settings table resolved
DB -> .env -> default; secrets stay in .env and never reach the database.

Suite timings re-baselined in docs/claude/testing-cost.md -- the database tier
is not free and the numbers say so."
```

---

## After the merge

**Do not run either suite again.** The branch was green when the merge started
and a conflict-free merge does not produce code nobody ran
(`docs/claude/document-conventions.md`). The one exception is a merge that
actually resolved conflicts — that resolution is new, unrun code, and it gets
the one run.

Once merged, three things remain outside this plan and are named here so they
are not mistaken for oversights:

1. **SQL pushdown.** Excluded deliberately: changing the storage and the
   aggregation together would leave a shifted number with two possible causes.
   `TradeLog._all()` is its seam.
2. **The `analytics` snapshot's rebuild trigger.** Still time-based
   (`max_age_seconds`), not event-driven. A `NOTIFY` on `trades` could drive it;
   that is a change with its own risk and belongs to its own plan.
3. **E39's fold-trade producer.** The table exists and is empty. That is a
   measured answer, not a stub — see `docs/claude/known-traps.md`.
