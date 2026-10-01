# v116 — Part 5: Phase 4, delete; full suite; release (V116-34 … V116-42)

Header, global constraints and revision ids: `_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 4.

**Start only after V116-33 recorded PASS**, and within seven days of its drill.

**Parallelisation (Phase 4, group F):** sequential throughout.
- V116-34 first: every later task leans on its harness (the lazy test-database fixture, `seed_store`, `db-test` in every CI shard) and its guard test.
- V116-35 → V116-36 → V116-37: they share `swingbot/admin/jobs.py`, `swingbot/commands/scanning/loops.py`, `tests/db/test_json_paths_removed.py` and `tests/store_seed.py`, and each adds its group's rows to the guard test.
- V116-38 after V116-37: the file watcher can go only once no table-backed store is written as a file.
- V116-39 after V116-38: it deletes `stages.py`, which nothing may still import.
- V116-40 documents the result; V116-41 is the plan's one full-suite run; V116-42 releases.

Every command runs from the worktree root (re-sync it first: `git merge origin/main`). `docker compose --profile test up -d db-test` for the whole phase: after it, every store test needs Postgres.

## The deletion rules (V116-35 … V116-37 apply them to their files)

The `db` branch of every fork is the code that has been running in production since V116-28/30/32. Keep it, drop the rest. Four shapes cover every call site (`git grep -n "stages\." -- swingbot`):

1. **Write fork** — `if stages.writes_json(X): <json write>` then `if stages.writes_db(X): <db write>` → keep `<db write>`, unindented, with its lazy repository import.
2. **Read fork** — `if stages.reads_db(X): return <db read>` then `return <json read>` (or an `if not stages.reads_db(X): return <json>` guard) → `return <db read>`.
3. **No-op guard** — `if stages.reads_db(X): return` at the top of a method that exists only for JSON (`reload`, `refresh`, `_drop_local`, `_persist` of a whole list) → delete the method and every call to it.
4. **File escape hatch** — a `path=`/`trades_path=` parameter that "always selects the file backend" → delete the parameter; callers that passed it were tests or maintenance scripts and move to `seed_store` / the repository.

Then delete what became unreferenced: path constants (`_PAUSE_FILE`, `STATE_FILE`, `KILLSWITCH_PATH`, …), `_load`/`_save`, `read_json`/`atomic_write_json` imports. Check each with `git grep -n "<name>"` before deleting; a hit outside the file is a caller to migrate, not a reason to keep it.

Worked example 1 (read fork + write fork, `swingbot/commands/scanning/runstate.py`):

```python
def is_scan_paused() -> bool:
    """Whether the automatic background scan loop is paused (admin toggle or
    !pause). Manual scans are not affected."""
    from swingbot.core.db.repositories.flags import flags_repo
    return flags_repo().is_set("scan_paused")


def set_scan_paused(paused: bool) -> None:
    from swingbot.core.db.repositories.flags import flags_repo
    repo = flags_repo()
    repo.set("scan_paused") if paused else repo.clear("scan_paused")
    if not paused:
        # Unpausing is the partner's acknowledgement of a store-write halt.
        _update_heartbeat({"store_write_failure": None})
```

Worked example 2 (escape hatch + write fork, `swingbot/core/planning/account.py`):

```python
def save_account_config(config: dict) -> None:
    from swingbot.core.db.repositories.account import account_repo
    account_repo().save(config)
```

with `path` removed from every caller (`git grep -n "save_account_config(\|load_account_config(" -- swingbot scripts tests`).

**Tests follow the same rule.** A test that seeds `tmp_path/"<store>.json"` seeds with `seed_store("<store>", payload)` instead (same payload literal). A test parametrised over `""`/`"X:dual"`/`"X:db"` keeps only the `db` case. A test that asserts a JSON file was written is deleted — that behaviour no longer exists — and the commit message lists every deleted test by node id.

---

# Phase 4 — Delete

### Task V116-34: A test database for every test, `seed_store`, and `db-test` in every CI shard

**Files:**
- Modify: `tests/conftest.py` (autouse `_store_database`)
- Create: `tests/store_seed.py`
- Modify: `tests/db/test_prod_snapshot_round_trip.py` (import `IMPORTS` from `tests/store_seed.py`)
- Modify: `.github/workflows/deploy.yml` (`services: db-test` on `backend-test-charts`, `-pipeline`, `-admin`, `-misc`)
- Modify: `tests/dev/test_ci_db_image.py` (one test)
- Create: `tests/test_store_harness.py`

**Interfaces:**
- Consumes: `db_engine`, `METADATA`, the importers (V116-25's table).
- Produces: `tests.store_seed.IMPORTS` (moved from V116-25), `seed_store(name: str, payload) -> None` (`payload` in the store's on-disk JSON shape; for `tuning`/`tuning_proposals` a `{filename: content}` dict; for `settings_audit` a list of entries), autouse fixture `_store_database` (any test that reaches `get_engine()` gets the per-worker test database, lazily; tables are truncated after only those tests; a test that needs it with `db-test` down is skipped with the start command).

- [ ] **Step 1: Write the failing tests**

`tests/test_store_harness.py`:

```python
"""Phase 4 harness: every store is Postgres, so every test reaches the test
database through the app's own engine, and seeds stores through importers."""
from swingbot.core.db.engine import get_engine
from swingbot.core.db.repositories.trades import TradeRepository
from tests.store_seed import seed_store

TRADE = {"id": "T1", "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
         "direction": "bullish", "status": "open", "opened_at": "2026-10-01T10:00:00+00:00",
         "entry": 100.0, "stop_loss": 98.0}


def test_the_app_engine_is_the_test_database_without_asking():
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("select current_database()").scalar().startswith("swingbot_test")


def test_seed_store_writes_through_the_real_importer():
    seed_store("trades", [TRADE])
    assert TradeRepository().get("T1")["ticker"] == "AAPL"


def test_the_previous_test_left_nothing_behind():
    assert TradeRepository().count() == 0


def test_get_engine_is_the_lazy_test_fixture():
    from swingbot.core.db import engine
    assert engine.get_engine.__name__ == "lazy"
```

Add to `tests/dev/test_ci_db_image.py`:

```python
def test_every_backend_shard_runs_the_test_database():
    jobs = _load("deploy.yml")["jobs"]
    shards = [name for name in jobs if name.startswith("backend-test-")]
    assert len(shards) == 5
    for name in shards:
        assert jobs[name]["services"]["db-test"]["image"] == "postgres:18-alpine", name
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_store_harness.py tests/dev/test_ci_db_image.py`
Expected: FAIL — `ModuleNotFoundError: tests.store_seed`; four shards lack `services`.

- [ ] **Step 3: `tests/store_seed.py`**

Move the `IMPORTS` dict and its imports from `tests/db/test_prod_snapshot_round_trip.py` into this module verbatim, then add:

```python
"""Seed stores through their real importers (v116 Phase 4).

Every store lives in Postgres, so a test that used to write data/<store>.json
calls seed_store("<store>", <the same payload>) instead. The payload keeps the
on-disk JSON shape; the importer does the translation the production import
did, so a fixture cannot drift from what the bot reads."""
import json
import os
import tempfile

from scripts.db.parity_report import STORES
from swingbot.core.db.repositories.account import AccountRepository

# IMPORTS = { ... moved here from tests/db/test_prod_snapshot_round_trip.py ... }


def _write_source(directory: str, name: str, payload) -> str:
    path = os.path.join(directory, STORES[name].filename)
    if name in ("tuning", "tuning_proposals"):
        os.makedirs(path)
        for filename, content in payload.items():
            with open(os.path.join(path, filename), "w", encoding="utf-8") as handle:
                json.dump(content, handle)
    elif name == "settings_audit":
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(json.dumps(entry) + "\n" for entry in payload)
    else:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    return path


def seed_store(name: str, payload) -> None:
    if name == "account":
        AccountRepository().save(payload)
        return
    load, factory, write_one, prepare = IMPORTS[name]
    repo = factory()
    if prepare is not None:
        prepare(repo)
    with tempfile.TemporaryDirectory() as directory:
        for record in load(_write_source(directory, name, payload)):
            write_one(repo, record)
```

In `tests/db/test_prod_snapshot_round_trip.py`, replace the moved block with `from tests.store_seed import IMPORTS`.

- [ ] **Step 4: The lazy test database** — append to `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _store_database(request, monkeypatch):
    """v116 Phase 4: every store is Postgres. A test that reaches get_engine()
    gets this worker's test database -- lazily, so a test that never touches
    a store opens nothing -- and the tables it touched are truncated after it.
    With db-test down, such a test skips with the start command."""
    import sqlalchemy as sa

    from swingbot.core.db import engine as engine_module
    from swingbot.core.db.repositories import base as base_module
    from swingbot.core.db.schema import METADATA
    used = {}

    def lazy():
        if "engine" not in used:
            used["engine"] = request.getfixturevalue("db_engine")
        return used["engine"]

    monkeypatch.setattr(engine_module, "get_engine", lazy)
    monkeypatch.setattr(base_module, "get_engine", lazy)
    yield
    if used:
        names = ", ".join(table.name for table in METADATA.sorted_tables)
        with used["engine"].begin() as conn:
            conn.execute(sa.text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
```

Run `git grep -n "import get_engine\|get_engine," -- swingbot scripts` and patch every other module that binds the name at import the same way (`scripts/db/import_settings_audit.py` binds it; `swingbot/core/db/migrations/env.py` does not need it — Alembic tests pass their own connection). `store_db` keeps working: it points `DATABASE_URL` at the same database.

- [ ] **Step 5: `db-test` in every backend shard**

In `.github/workflows/deploy.yml`, copy the `services:` block of `backend-test-backtest-edge` (from `services:` to `--health-interval … --health-retries 10`) verbatim under `runs-on: ubuntu-latest` of `backend-test-charts`, `backend-test-pipeline`, `backend-test-admin` and `backend-test-misc`, each with the comment `# v116 Phase 4: every store is Postgres; store tests need the database in every shard.`

- [ ] **Step 6: Run the harness tests and a broad sample**

Run: `python scripts/dev/testrun.py file tests/test_store_harness.py tests/dev/test_ci_db_image.py tests/db`
Expected: PASS. Then `python scripts/dev/testrun.py fast` — `0 failed` (nothing is deleted yet; the fixture only changes where an engine points).

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/store_seed.py tests/db/test_prod_snapshot_round_trip.py tests/test_store_harness.py .github/workflows/deploy.yml tests/dev/test_ci_db_image.py
git commit -m "test(v116): Postgres for every test that touches a store; seed_store; db-test in every shard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-35: Delete the ops group's JSON paths

**Files:**
- Create: `tests/db/test_json_paths_removed.py`
- Modify: `swingbot/commands/scanning/runstate.py` (flags, heartbeat, manual-close queue path), `swingbot/core/scanning/runstate.py` (flags), `swingbot/commands/scanning/loops.py` (`_scheduled_job_already_fired`, `_mark_scheduled_job_fired`, `_scheduled_jobs_path`, `_take_manual_close_queue`, `_read_queue_file`), `swingbot/admin/api_v1/trade_commands.py` (`_queue_notify`, `_queue_path`, `_QUEUE_LOCK`), `swingbot/core/edge/throttle.py` (`kill_state`, `set_kill`, `KILLSWITCH_PATH`), `swingbot/admin/jobs.py` and `swingbot/admin/api_v1/jobs.py` (the `jobs` forks only), `swingbot/core/scanning/progress_store.py`, `swingbot/core/marketdata/data_refresh.py` (`load_state`, `save_state`, `STATE_FILE`), `swingbot/admin/app.py` (`_heartbeat_snapshot`)
- Modify/delete: the tests that seed or assert those files (found in Step 3)

**Interfaces:**
- Consumes: V116-34's harness; the deletion rules above.
- Produces: the ops stores are Postgres-only. `tests/db/test_json_paths_removed.py::FORBIDDEN` (a list of `(path, regex, why)`), which V116-36/37/39 extend.

- [ ] **Step 1: Write the guard test**

```python
"""No migrated store keeps a JSON read or write path (v116 Phase 4).
Each Phase 4 task adds its group's rows; V116-39 adds the global ones."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

#: (file, pattern that must not appear, why)
FORBIDDEN = [
    # ops group (V116-35)
    ("swingbot/commands/scanning/runstate.py", r"stages\.|\.flag\"|_HEARTBEAT_FILE|_MANUAL_CLOSE_QUEUE", "flags, heartbeat, notify_queue are tables"),
    ("swingbot/core/scanning/runstate.py", r"stages\.|\.flag\"", "flags are a table"),
    ("swingbot/commands/scanning/loops.py", r"stages\.\w+\(\"(scheduled_jobs|notify_queue)\"\)|scheduled_jobs\.json|_MANUAL_CLOSE_QUEUE", "scheduled_jobs, notify_queue are tables"),
    ("swingbot/admin/api_v1/trade_commands.py", r"stages\.|manual_close_notify\.json", "notify_queue is a table"),
    ("swingbot/core/edge/throttle.py", r"stages\.|KILLSWITCH_PATH|killswitch\.json", "killswitch is a table"),
    ("swingbot/admin/jobs.py", r"stages\.\w+\(\"jobs\"\)|admin_jobs\.json", "jobs is a table"),
    ("swingbot/admin/api_v1/jobs.py", r"stages\.\w+\(\"jobs\"\)", "jobs is a table"),
    ("swingbot/core/scanning/progress_store.py", r"stages\.|scan_progress\.json", "scan_progress is a table"),
    ("swingbot/core/marketdata/data_refresh.py", r"stages\.|market_data_state\.json|STATE_FILE", "market_data_state is a table"),
    ("swingbot/admin/app.py", r"stages\.\w+\(\"heartbeat\"\)|bot_heartbeat\.json", "heartbeat is a table"),
]


@pytest.mark.parametrize("path,pattern,why", FORBIDDEN, ids=[f"{p}:{w}" for p, _r, w in FORBIDDEN])
def test_no_json_path_remains(path, pattern, why):
    text = (REPO / path).read_text(encoding="utf-8")
    hits = [f"{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
            if re.search(pattern, line)]
    assert not hits, f"{path} still has a JSON path ({why}):\n" + "\n".join(hits)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_json_paths_removed.py` — 10 failures, each listing its lines.

- [ ] **Step 3: Apply the deletion rules to the ten files**, one at a time, re-running the guard test after each. Before each file: `git grep -n "<constant or function you are about to delete>" -- swingbot scripts tests` to find callers. Specifics:
  - `commands/scanning/runstate.py`: `_read_heartbeat` returns `heartbeat_repo().last() or {}` inside its `try`; `_update_heartbeat` keeps its `db` half; `_flag_set_at(name)` loses its `path` argument and the mtime branch; delete `_TRIGGER_FILE`, `_PAUSE_FILE`, `_HEARTBEAT_FILE`, `_MANUAL_CLOSE_QUEUE` and the `json`/`os` imports if unused. `request_trigger(payload=None)`: the payload was the flag file's body; the row stores only `set_at`, so the parameter goes and its admin caller (`api_v1/system.py`) stops passing it.
  - `loops.py`: `_take_manual_close_queue()` becomes `return notify_queue_repo().drain()` (with the import); delete `_read_queue_file` and `_scheduled_jobs_path`.
  - `admin/app.py`: `_heartbeat_snapshot()` becomes the former `db` branch only.
  - `throttle.py`: `kill_state()` returns `killswitch_repo().state()`; `set_kill` keeps only its repository branch.
  - `progress_store.py`: keep `_write_row`, `_read_row` and the repository `clear`; delete `FILENAME`, `path()`, `_write_file`, `_read_file`. `read()` returns `_read_row()`.
  - `data_refresh.py`: `load_state()` keeps its `try: … load()` block; `save_state()` keeps its `db` write inside the `try`.

- [ ] **Step 4: Migrate the ops tests**

```bash
git grep -ln "scan_paused.flag\|trigger_check.flag\|stop_scan.flag\|scan_running.flag\|bot_heartbeat.json\|_HEARTBEAT_FILE\|_PAUSE_FILE\|_TRIGGER_FILE\|_MANUAL_CLOSE_QUEUE\|manual_close_notify.json\|scheduled_jobs.json\|killswitch.json\|KILLSWITCH_PATH\|admin_jobs.json\|scan_progress.json\|market_data_state.json\|STATE_FILE\|flags:\|heartbeat:\|notify_queue:\|scheduled_jobs:\|killswitch:\|jobs:\|scan_progress:\|market_data_state:" -- tests
```

Apply the test rule to every file listed. `tests/admin/conftest.py`'s `runstate._TRIGGER_FILE`/`_PAUSE_FILE` patches go (the flags are rows now, truncated per test).

- [ ] **Step 5: Run**

Run: `python scripts/dev/testrun.py file tests/db/test_json_paths_removed.py` — PASS. Then `python scripts/dev/testrun.py fast` — `0 failed`.

- [ ] **Step 6: Complexity and commit**

`python -m radon cc -s -n C <the ten files>` — nothing at C except `loops.config_watcher`, `loops._session_scan_tick`, `loops.on_ready`, each at or below the value the index lists.

```bash
git add -A swingbot tests
git status --short   # only the files named above and the migrated/deleted tests
git commit -m "refactor(v116)!: ops stores are Postgres-only -- delete their JSON paths

Deleted tests (behaviour removed): <node ids>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-36: Delete the reference group's JSON paths

**Files:**
- Modify: `tests/db/test_json_paths_removed.py` (reference rows)
- Modify: `swingbot/core/marketdata/watchlist.py`, `swingbot/core/marketdata/ticker_directory.py`, `swingbot/core/infra/state.py`, `swingbot/admin/helpers.py` (`append_settings_audit`, `read_settings_audit`, `_audit_log_path`), `swingbot/admin/api_v1/system.py` (preferences), `swingbot/admin/jobs.py`, `swingbot/admin/api_v1/jobs.py`, `swingbot/admin/queries.py` (the `tuning` forks, `TUNING_PROPOSALS_DIR_NAME`)
- Modify/delete: the tests that seed or assert those files

**Interfaces:**
- Consumes: V116-35's guard test and harness.
- Produces: the reference stores are Postgres-only.

- [ ] **Step 1: Add the reference rows to `FORBIDDEN`**

```python
    # reference group (V116-36)
    ("swingbot/core/marketdata/watchlist.py", r"stages\.|watchlist\.json", "watchlist is a table"),
    ("swingbot/core/marketdata/ticker_directory.py", r"stages\.|ticker_directory\.json", "ticker_directory is a table"),
    ("swingbot/core/infra/state.py", r"stages\.|state\.json|_save\(", "signal_state is a table"),
    ("swingbot/admin/helpers.py", r"stages\.|settings_audit\.jsonl", "settings_audit is a table"),
    ("swingbot/admin/api_v1/system.py", r"stages\.|ui_preferences\.json", "preferences is a table"),
    ("swingbot/admin/jobs.py", r"stages\.|tuning_results", "tuning is a table"),
    ("swingbot/admin/api_v1/jobs.py", r"stages\.|tuning_results", "tuning is a table"),
    ("swingbot/admin/queries.py", r"stages\.|TUNING_PROPOSALS_DIR_NAME", "tuning_proposals is a table"),
```

Run the guard test — the eight new rows fail.

- [ ] **Step 2: Apply the deletion rules** to the eight files, one at a time, re-running the guard after each. `StateStore` keeps its lock and debounce contract (`tests/infra/test_state_db.py` pins it) with the repository as its only backend; `load_watchlist(path=None)`'s escape hatch goes (rule 4); `ticker_directory`'s in-memory cache keyed on file `fetched_at` keys on `ticker_directory_repo().loaded_at()` only.

- [ ] **Step 3: Migrate the reference tests** — `git grep -ln "watchlist.json\|ticker_directory.json\|state.json\|settings_audit.jsonl\|ui_preferences.json\|tuning_results\|tuning_proposals\|watchlist:\|state:\|ticker_directory:\|preferences:\|settings_audit:\|tuning:" -- tests` and apply the test rule (`seed_store("watchlist", [...])`, `seed_store("tuning", {"J1.json": {...}})`, …). `tests/test_watchlist_default_path_staging.py` tests only the escape hatch: delete it and list it.

- [ ] **Step 4: Run** — guard test PASS; `python scripts/dev/testrun.py fast` — `0 failed`.

- [ ] **Step 5: Complexity and commit** — `python -m radon cc -s -n C <the eight files>` nothing new.

```bash
git add -A swingbot tests
git commit -m "refactor(v116)!: reference stores are Postgres-only -- delete their JSON paths

Deleted tests (behaviour removed): <node ids>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-37: Delete the trading group's JSON paths and the reload/refresh machinery

**Files:**
- Modify: `tests/db/test_json_paths_removed.py` (trading rows)
- Modify: `swingbot/core/tracking/performance.py` (`TradeLog`: `path`, `_trades`, `_load`, `reload`, `_save`, `_persist`'s list branch, `_reads_db`, `_drop_local`, `_persist_changed`'s JSON branch, `_all`'s JSON branch, `refresh` and its eleven calls), `swingbot/core/planning/plan_store.py` (`PlanStore`: `path`, `_plans`, `_load`, `reload`, `_save`, `_all`'s JSON branch), `swingbot/core/planning/plan_manager.py` (`store.reload()`/`trade_log.reload()` calls at lines 267, 352–354, 382, 955; the two stage checks at 526–527), `swingbot/core/planning/account.py` (`_default_config_path`, `_read_trades_file`, the `path`/`trades_path` escape hatches, the forks at 92/123/208/210), `swingbot/core/analytics/journal.py`, `swingbot/commands/views.py` (starred), `swingbot/admin/watchlist_rows.py` (plans), `swingbot/core/scanning/engine.py` (the module `trade_log` singleton comment)
- Modify/delete: the tests that seed or assert those files

**Interfaces:**
- Consumes: V116-36's state of the guard test and harness.
- Produces: `TradeLog()` and `PlanStore()` take no arguments and hold no snapshot; every read goes to the repository. The spec's "reload()/refresh()/stale-snapshot machinery" is gone.

- [ ] **Step 1: Add the trading rows to `FORBIDDEN`**

```python
    # trading group (V116-37)
    ("swingbot/core/tracking/performance.py", r"stages\.|trades\.json|def reload|def refresh|\.refresh\(\)|self\._trades\b", "trades is a table; no snapshot to refresh"),
    ("swingbot/core/planning/plan_store.py", r"stages\.|plans\.json|def reload|self\._plans\b", "plans is a table; no snapshot to reload"),
    ("swingbot/core/planning/plan_manager.py", r"stages\.|\.reload\(\)", "no snapshot to reload"),
    ("swingbot/core/planning/account.py", r"stages\.|account\.json|trades\.json|_read_trades_file", "account and trades are tables"),
    ("swingbot/core/analytics/journal.py", r"stages\.|journal\.json", "journal is a table"),
    ("swingbot/commands/views.py", r"stages\.|starred_plans\.json", "starred_plans is a table"),
    ("swingbot/admin/watchlist_rows.py", r"stages\.", "plans is a table"),
```

Run the guard — seven new failures.

- [ ] **Step 2: Apply the deletion rules**, in this order (each depends on the one before being green): `performance.py`, `plan_store.py`, `plan_manager.py`, `account.py`, `journal.py`, `views.py`, `watchlist_rows.py`. In `TradeLog`, `_all()` becomes `return [_json_record(row) for row in trades_repo().list_all()]`, `_persist(trade)` becomes `self._db_upsert(trade, conn=conn)` for a single trade, and a bulk mutation persists through `_persist_changed`'s per-trade upserts. Every `self.refresh()` call (lines 1065, 1104, 1144, 1225, 1245, 1264, 1316, 1344, 1530, 1636 when planned — re-find them with `git grep -n "self.refresh()" swingbot/core/tracking/performance.py`) is deleted, not replaced. `PlanStore._all()` keeps its `created_at` isoformat conversion.

- [ ] **Step 3: Migrate the trading tests** — `git grep -ln "trades.json\|plans.json\|account.json\|journal.json\|starred_plans.json\|TradeLog(\S\|PlanStore(\S\|trades_path=\|\.reload()\|\.refresh()\|plans:\|trades:\|account:\|journal:\|starred_plans:" -- tests` (about 90 files when planned) and apply the test rule. `tests/admin/conftest.py::admin_app` stops writing `trades.json`/`account.json`/`plans.json` and calls `seed_store("account", {…same dict…})`. `tests/tracking/test_tradelog_reload_retired.py` and `tests/planning/test_plan_store_dual.py` test removed behaviour: delete and list them. Work directory by directory (`tests/tracking`, `tests/planning`, `tests/analytics`, `tests/admin`, `tests/commands`, `tests/scanning`, the rest), running `python scripts/dev/testrun.py file tests/<dir>` after each.

- [ ] **Step 4: Run** — guard test PASS; `python scripts/dev/testrun.py fast` — `0 failed`.

- [ ] **Step 5: Complexity and commit** — `python -m radon cc -s -n C <the files>`: nothing new; `scan_run._sync_run_scan` untouched.

```bash
git add -A swingbot tests
git commit -m "refactor(v116)!: trading stores are Postgres-only; delete reload/refresh and the in-memory snapshots

Deleted tests (behaviour removed): <node ids>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-38: Writers of the remaining files NOTIFY; delete the file watcher

**Files:**
- Modify: `swingbot/core/db/notify.py` (new `publish`)
- Modify: `swingbot/core/db/events.py` (new `SSE_EVENTS`, `FILE_PUBLISHERS`)
- Modify: `swingbot/core/analytics/snapshots.py` (`save_snapshot`), `swingbot/core/scanning/snapshots.py` (`_save_scan_snapshots`), `swingbot/core/scanning/telemetry.py` (`log_scan_telemetry`), `swingbot/admin/helpers.py` (`_write_env_text`), `scripts/ops/env_set.py` (`main`)
- Modify: `swingbot/admin/events/broker.py` (`_default_watcher` → `DbEventListener(emit)`; delete `_CompositeWatcher`, `_stop_all`, the `FileWatcher`/`residual_paths` import)
- Delete: `swingbot/admin/events/watcher.py`
- Modify: `tests/db/test_trigger_coverage.py`, `tests/db/test_part3_exit.py`, `tests/admin/test_no_double_watcher.py` (rewritten), every test importing `watcher` (Step 5)
- Create: `tests/db/test_file_publishers.py`
- Modify: `tests/db/test_json_paths_removed.py` (one row)

**Interfaces:**
- Consumes: `notify.emit`, `notify.CHANNELS`; the broker from V116-11/15.
- Produces: `notify.publish(channel: str) -> None` (one NOTIFY outside any store write; never raises). `events.SSE_EVENTS = frozenset(notify.CHANNELS)` replaces `watcher.WATCHED_EVENTS`. `events.FILE_PUBLISHERS: dict[str, str]` documents the four file-backed sources and their channel. The SSE contract is unchanged: the same ten names, `resync` from the stream and the listener.

Why this is not a plain deletion (`_0-index.md` § Spec points, 11): `analytics_snapshot.json`, `scan_snapshots.json`, `scan_telemetry.jsonl` and `.env` stay files (spec § Out) and still raise `analytics`/`scan`/`settings`. With the watcher gone, their writers raise the event themselves.

- [ ] **Step 1: Write the failing tests** — `tests/db/test_file_publishers.py`:

```python
"""The four sources that stay files raise their SSE concern themselves (v116)."""
import json
import threading

from swingbot.core.db import events, notify


def _capture(db_engine, channel, action):
    got, stop = [], threading.Event()

    def on_listening():
        action()

    def on_event(name):
        if name == channel:
            got.append(name)
            stop.set()

    timer = threading.Timer(3.0, stop.set)
    timer.start()
    notify.listen((channel,), on_event, stop, poll=0.05,
                  dsn=db_engine.url.render_as_string(hide_password=False),
                  on_listening=on_listening)
    timer.cancel()
    return got


def test_publish_raises_a_notify(db_engine):
    assert _capture(db_engine, "analytics", lambda: notify.publish("analytics")) == ["analytics"]


def test_publish_never_raises_without_a_database(monkeypatch):
    from swingbot.core.db import engine
    monkeypatch.setattr(engine, "get_engine", lambda: (_ for _ in ()).throw(OSError("down")))
    notify.publish("scan")


def test_the_analytics_snapshot_writer_publishes(db_engine, tmp_path):
    from swingbot.core.analytics.snapshots import save_snapshot
    got = _capture(db_engine, "analytics",
                   lambda: save_snapshot({"x": 1}, str(tmp_path / "snap.json")))
    assert got == ["analytics"]


def test_the_telemetry_writer_publishes(db_engine, tmp_path):
    from swingbot.core.scanning.telemetry import log_scan_telemetry
    got = _capture(db_engine, "scan",
                   lambda: log_scan_telemetry({"duration_s": 1.0}, str(tmp_path / "t.jsonl")))
    assert got == ["scan"]


def test_every_sse_event_has_a_table_or_a_file_publisher():
    raised = set(events.TABLE_CHANNELS.values()) | set(events.FILE_PUBLISHERS.values())
    assert raised == set(events.SSE_EVENTS)
```

Add to `FORBIDDEN`:

```python
    ("swingbot/admin/events/broker.py", r"FileWatcher|residual_paths|_CompositeWatcher|stages\.", "the admin listens to Postgres only"),
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_file_publishers.py tests/db/test_json_paths_removed.py` — `AttributeError: publish`, the broker row fails.

- [ ] **Step 3: `notify.publish` and the two maps**

`swingbot/core/db/notify.py`, after `emit`:

```python
def publish(channel: str) -> None:
    """One NOTIFY outside any store write, for a concern whose source stays a
    file (events.FILE_PUBLISHERS). Never raises: a missed refresh costs one
    stale screen until the next event, a raised one would fail the write."""
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a known channel")
    try:
        from swingbot.core.db.engine import get_engine
        with get_engine().begin() as conn:
            emit(conn, channel)
    except Exception:  # noqa: BLE001
        log.debug("could not publish %s", channel, exc_info=True)
```

`swingbot/core/db/events.py`, at the end (and delete the "`analytics` and Part 5's tables are added by that part" comment):

```python
from swingbot.core.db.notify import CHANNELS

#: The SPA's event contract: every name the stream can send besides `resync`
#: and `ping`. Formerly admin/events/watcher.py's WATCHED_EVENTS.
SSE_EVENTS = frozenset(CHANNELS)

#: Sources that stay files (spec § Out) and raise their concern themselves
#: through notify.publish -- the watcher that stat()ed them is gone (v116).
FILE_PUBLISHERS: dict[str, str] = {
    "data/analytics_snapshot.json (analytics.snapshots.save_snapshot)": "analytics",
    "data/scan_snapshots.json (scanning.snapshots._save_scan_snapshots)": "scan",
    "data/scan_telemetry.jsonl (scanning.telemetry.log_scan_telemetry)": "scan",
    ".env (admin.helpers._write_env_text, scripts/ops/env_set.py)": "settings",
}
```

- [ ] **Step 4: The writers publish**

- `analytics/snapshots.py::save_snapshot`: after `atomic_write_json(...)`, `notify.publish("analytics")` (import `from swingbot.core.db import notify` inside the function).
- `scanning/snapshots.py::_save_scan_snapshots`: after the `json.dump` block inside the `try`, `notify.publish("scan")`.
- `scanning/telemetry.py::log_scan_telemetry`: after the `with open(...)` block, `notify.publish("scan")`.
- `admin/helpers.py::_write_env_text`: after the second `snapshot_quietly`, `notify.publish("settings")`.
- `scripts/ops/env_set.py::main`: after the second snapshot, a best-effort NOTIFY through the db container (the host has no psql):

```python
    import subprocess
    subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "swingbot",
                    "-d", "swingbot", "-c", "NOTIFY settings"],
                   cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, check=False)
```

Add to `tests/scripts/test_env_set.py`: a test that monkeypatches `subprocess.run` to record its argv and asserts `NOTIFY settings` was sent once after a set, and never for `--get`.

- [ ] **Step 5: The broker listens to Postgres only; delete the watcher**

In `broker.py`: `_default_watcher(emit)` becomes `return DbEventListener(emit)` with a docstring "One listener per process: LISTEN/NOTIFY for every concern (v116)"; delete `_CompositeWatcher`, `_stop_all` and `from .watcher import FileWatcher, residual_paths`; the module docstring's "watcher (NG20)" wording becomes "listener". `git rm swingbot/admin/events/watcher.py`. Then `git grep -ln "events.watcher\|events import watcher\|WATCHED_EVENTS\|FileWatcher\|residual_paths\|_TABLE_BACKED" -- swingbot tests` and:
  - `tests/db/test_trigger_coverage.py::test_every_watched_event_has_at_least_one_table` → covered by `test_every_sse_event_has_a_table_or_a_file_publisher`; delete it.
  - `tests/db/test_part3_exit.py`: `test_the_four_flag_files_have_exactly_one_owner_module` → delete (no flag files remain; the guard test covers it); `test_every_channel_has_at_least_one_table_or_a_stated_reason` → delete (superseded); the `.env.example` test waits for V116-39.
  - `tests/admin/test_no_double_watcher.py` → rewrite as one test: a subscribed broker's `_watcher` is a `DbEventListener`, and a second subscription reuses it.
  - FileWatcher's own test files → `git rm`, listed in the commit.

- [ ] **Step 6: Run** — `python scripts/dev/testrun.py file tests/db/test_file_publishers.py tests/db/test_json_paths_removed.py tests/admin/test_no_double_watcher.py tests/admin/test_sse_contract.py tests/admin/test_live_updates_e2e.py tests/admin/test_broker_db_listener.py tests/scripts/test_env_set.py` — PASS; then `python scripts/dev/testrun.py fast` — `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add -A swingbot tests scripts/ops/env_set.py
git commit -m "refactor(v116)!: file-backed sources NOTIFY themselves; delete the file watcher

Deleted tests: <node ids>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-39: Delete `stages`, `DB_STORES` and the dual guard

**Files:**
- Delete: `swingbot/core/db/stages.py`, `swingbot/core/db/dual.py`, `tests/db/test_stages.py`, `tests/db/test_dual.py`, `scripts/ops/v116_soak.py`, `scripts/ops/v116_parity_check.sh`, `scripts/ops/install_v116_soak_cron.sh`, `tests/scripts/test_v116_soak.py`, `scripts/ops/v91_dual_check.sh`, `scripts/ops/install_v91_dual_check_cron.sh`
- Modify: `swingbot/core/db/codec.py` (receives `normalise`), every importer of `swingbot.core.db.dual` (`scripts/db/export_json.py`, `scripts/db/parity_report.py`, `swingbot/core/analytics/journal.py`, `swingbot/core/planning/account.py`, `swingbot/core/tracking/performance.py`)
- Modify: `swingbot/config.py` (delete the `DB_STORES` `Field`), `.env.example` (delete the `DB_STORES` comment block and line)
- Modify: `swingbot/core/db/write_failure.py` (`halts_issuance` no longer consults stages)
- Modify: `scripts/db/parity_report.py` (delete `STAGE_STORES`, `dual_stores`, `--dual`), `scripts/ops/rollback_to.sh` (step 9 and the DB_STORES dry-run lines), `tests/scripts/test_rollback_to_shape.py`, `tests/scripts/test_parity_dual.py` (delete)
- Modify: `scripts/db/export_json.py` (`RESTART_WARNING` → none needed; the module docstring)
- Modify: `tests/db/test_part3_exit.py` (the `.env.example` test), `tests/db/test_json_paths_removed.py` (global rows)

**Interfaces:**
- Consumes: V116-35 … V116-38 (nothing reads a stage any more except the modules deleted here).
- Produces: `codec.normalise(value)`; `write_failure.halts_issuance(exc) == is_store_write_failure(exc)`. Rollback now means Phase 0 only (spec § Phase 4).

- [ ] **Step 1: Add the global rows to the guard**

```python
    # global (V116-39)
    ("swingbot/core/db/codec.py", r"from swingbot\.core\.db import stages", "no stages module"),
    ("swingbot/config.py", r"\"DB_STORES\"", "no per-store stages"),
    (".env.example", r"^DB_STORES=", "no per-store stages"),
    ("scripts/ops/rollback_to.sh", r"parity_report|DB_STORES", "rollback is PITR only"),
    ("swingbot/core/db/write_failure.py", r"stages", "every trading store is at db"),
]


def test_no_module_imports_stages_or_dual():
    hits = []
    for path in list((REPO / "swingbot").rglob("*.py")) + list((REPO / "scripts").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"core\.db import stages|core\.db\.stages|core\.db\.dual|core\.db import dual", text):
            hits.append(path.relative_to(REPO).as_posix())
    assert hits == [], hits
    assert not (REPO / "swingbot/core/db/stages.py").exists()
    assert not (REPO / "swingbot/core/db/dual.py").exists()
```

(the `]` closes `FORBIDDEN`). Run it — failures listed.

- [ ] **Step 2: Move `normalise`** — cut `normalise` from `dual.py` into `codec.py` (with `import datetime as dt` and `from decimal import Decimal`); change every `from swingbot.core.db.dual import normalise` to `from swingbot.core.db.codec import normalise`; add three cases to `tests/db/test_codec.py` (`Decimal("1.5")` → `1.5`; a tz-aware `datetime` → its `isoformat()`; a nested dict/list of both → the same structure normalised); `git rm swingbot/core/db/dual.py tests/db/test_dual.py`.

- [ ] **Step 3: Delete `stages`, `DB_STORES` and what only served them** — `git rm swingbot/core/db/stages.py tests/db/test_stages.py`; delete the `DB_STORES` `Field` from `swingbot/config.py` and its block from `.env.example`; `write_failure.py`: delete `TRADING_STORES` and `trading_store_at_db`, `halts_issuance` returns `is_store_write_failure(exc)` (its docstring: "every trading store is at db"); update `tests/commands/test_store_write_halt.py::test_only_a_trading_store_at_db_halts` to `test_any_database_write_failure_halts`; `parity_report.py`: delete `STAGE_STORES`, `dual_stores`, `_selected`'s `--dual` branch and the flag; `git rm tests/scripts/test_parity_dual.py`; `git rm` the soak and v91 scripts and `tests/scripts/test_v116_soak.py`; `tests/db/test_part3_exit.py::test_the_committed_env_example_promotes_no_store` → delete.

- [ ] **Step 4: `rollback_to.sh` step 9 is PITR only** — delete the two `echo "--- parity …"`/`parity_report.py --dual` lines and the "Stores whose JSON file stays …" `echo`/`grep` pair, and the header sentence about json/dual stores. In `tests/scripts/test_rollback_to_shape.py`, drop `"parity_report.py --dual"` from `markers`.

- [ ] **Step 5: Run** — `python scripts/dev/testrun.py file tests/db/test_json_paths_removed.py tests/db/test_codec.py tests/commands/test_store_write_halt.py tests/scripts/test_rollback_to_shape.py tests/test_env_example_sync.py tests/db/test_part3_exit.py` — PASS; `python scripts/dev/testrun.py fast` — `0 failed`; `git grep -n "DB_STORES\|stages\.\|core\.db\.dual" -- swingbot scripts tests .env.example` — only historical comments, each reworded to past tense or removed.

- [ ] **Step 6: Commit**

```bash
git add -A swingbot scripts tests .env.example
git commit -m "refactor(v116)!: delete stages, DB_STORES and the dual guard -- Postgres is the only store

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-40: Docs sweep, the `schema-change` skill, and the Codex mirror

**Files:**
- Modify: `docs/claude/architecture.md`, `docs/claude/known-traps.md`, `docs/deploy/DEPLOY_HETZNER.md`, `docs/deploy/DB_RESTORE.md`, `.claude/skills/schema-change/SKILL.md`, `AGENTS.md`, and the generated `.agents/skills/schema-change/SKILL.md` (via `python scripts/dev/sync_codex.py`)

**Interfaces:**
- Consumes: the finished code (V116-34 … V116-39) and `docs/claude/schema-evolution.md` (V116-19).
- Produces: documentation that says "every trading and operational store is Postgres-only; rollback is `scripts/ops/rollback_to.sh`".

- [ ] **Step 1: Find every stale statement**

```bash
git grep -n -i "DB_STORES\|stage\b\|stages\|dual\b\|strangler\|partially complete\|json-only\|FileWatcher\|file watcher\|trades\.json\|plans\.json\|reload()\|refresh()" -- docs/claude docs/deploy .claude/skills AGENTS.md CLAUDE.md
```

- [ ] **Step 2: Rewrite each hit**
  - `architecture.md`: the `core/db` map gains `doc_fields.py`, `write_failure.py`, `events.py`, loses `stages.py`/`dual.py`; the persistence paragraph says every store in `schema.PROMOTED` is Postgres-only and live updates are LISTEN/NOTIFY plus `notify.publish` for the four file sources.
  - `known-traps.md`: drop traps that only existed for JSON stores (stale in-memory snapshots, the flag-file name mismatch); keep and reword the `.env` bind-mount trap to point at `scripts/ops/env_set.py`; add "a DB write failure at issuance pauses scanning (`StoreWriteHalt`); unpause from the admin UI after fixing the database".
  - `DEPLOY_HETZNER.md` § PostgreSQL: remove "(v67 migration, in progress)", the Stages bullet and "Rolling a store back from `db` to JSON"; add a "Point-in-time rollback" subsection: `scripts/ops/rollback_to.sh "<UTC>" --dry-run`, then without `--dry-run`; the backup crons; `backups/` layout; the drill.
  - `DB_RESTORE.md`: a top paragraph saying `rollback_to.sh` is the rollback and `pg_dump` (90 days) is the second, day-level method.
  - `.claude/skills/schema-change/SKILL.md`: the description's "the JSON-to-Postgres strangler is per-store and partially complete, so some stores are migrated and some are not" → "every store is Postgres-only; a shape change is an Alembic revision following docs/claude/schema-evolution.md"; Step 1 becomes "Read `docs/claude/schema-evolution.md` and pick the operation (add/rename/drop/promote)"; Step 3's `parity_report` becomes the three contract tests; the gate becomes "the contract tests green, the revision's downgrade run once against the test database, and a PITR drill within 7 days before running a drop/rename on production"; the trigger table keeps its rows.
  - `AGENTS.md`: mirror the skill and doc changes (condensed).

- [ ] **Step 3: Regenerate and check the mirror**

Run: `python scripts/dev/sync_codex.py` then `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py tests/hooks/test_skill_shape.py` — PASS. The skill's description changed, so also run its eval suite (v96 skills layer: the eval checks the skill still fires) with the command documented in `docs/claude/skills-tools.md`; the worktree refuses commands containing "eval", so run it from the main tree after merging, or record it as V116-42 Step 2.

- [ ] **Step 4: Commit (Claude docs and Codex mirror together)**

```bash
git add docs/claude docs/deploy .claude/skills/schema-change .agents/skills/schema-change AGENTS.md
git commit -m "docs(v116): Postgres-only stores and point-in-time rollback; schema-change skill; Codex mirror

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-41: Full-suite verification

**Files:** none unless a failure is fixed forward.

- [ ] **Step 1: The one full run of the plan**

`docker compose --profile test up -d db-test`, then run `python scripts/dev/testrun.py full` (or dispatch the `test-runner` subagent) once, over everything this plan implemented. Expect `0 failed`, `0 xfailed`, and no skip whose reason is "test database unreachable". The plan did not touch `frontend/`, so no `npm test`.

- [ ] **Step 2: If it is not green, fix forward** from the failures it names — they are this plan's regressions. Each fix is its own commit; re-run only the failing files (`testrun.py file …`), then `testrun.py full` once more at the end. The task is done when a full run is green.

- [ ] **Step 3: Complexity over the whole diff**

`git diff --name-only origin/main...HEAD -- '*.py' | xargs python -m radon cc -s -n C` — nothing except the four legacy functions listed in the index, none above its listed value.

---

### Task V116-42: Release (bot major), ship, VM clean-up, close-out — TOUCHES PRODUCTION

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`
- Move: the spec and the six plan parts to `implemented/` (`document-lifecycle.md`)

**Interfaces:**
- Consumes: V116-41 green.
- Produces: `bot` major release; production running Postgres-only code; the soak and v91 crons removed; the plan closed.

- [ ] **Step 1: Bump, then regenerate, as two commits** (`working-conventions.md` § How)

Read `VERSION.json` now (never a number from this plan or the spec). Increment `bot`'s **major** part (`X.Y.Z` → `X+1.0.0`), leave `ui` and `ui_updated` alone, set `bot_updated` to now in `YYYY-MM-DD HH-MM-SS` UTC.

```bash
git add VERSION.json
git commit -m "release(bot): <X+1>.0.0 -- stores are Postgres-only; whole-bot point-in-time rollback

Major: the bot no longer starts from data/*.json; an install that has not
imported into Postgres breaks, and DB_STORES is removed from .env.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <X+1>.0.0 -- stores are Postgres-only; whole-bot point-in-time rollback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Merge and ship** — as V116-09 Step 2 (message `merge(v116): Phase 4 -- delete the JSON persistence paths`). If the merge resolved conflicts, run `testrun.py full` once on `main` first (`document-conventions.md`: a conflict resolution is new code). Run the `schema-change` skill eval from the main tree if V116-40 deferred it.

- [ ] **Step 3: Production after the deploy**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current && docker compose ps && docker compose logs --since 10m bot admin | grep -cE 'sqlalchemy\.exc\.|psycopg\.|DatabaseUnavailable|StoreWriteHalt'"
bash scripts/ops/ssh-hetzner.sh "crontab -l | grep -vE 'v116_parity_check|v116 soak|v91_dual_check|v91 dual' | crontab - && crontab -l"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -n '^DB_STORES=' .env"
```

Expected: `v116_002 (head)`, all services healthy, `0` error lines; the crontab keeps the PITR and `backup_db.sh` lines only. `DB_STORES` in the VM `.env` is now ignored; remove the line through the admin Settings page (it rewrites the file and snapshots it) or leave it and note it — never `sed -i`. Check the admin Dashboard, Trades, Plans and live updates, and that a new alert's trade appears in Postgres (`docker compose exec -T db psql -U swingbot -d swingbot -tAc "select max(opened_at) from trades"`).

- [ ] **Step 4: Close out** — use the `close-out` skill (`document-lifecycle.md`): move `docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md` and the six `docs/superpowers/plans/2026-09-30-v116-postgres-cutover-pitr_*.md` parts to their `implemented/` directories, fix links, commit `docs(v116): close out -- implemented`, push. Do not delete the v116 or v67 branches or worktrees; report them to the partner for a decision.
