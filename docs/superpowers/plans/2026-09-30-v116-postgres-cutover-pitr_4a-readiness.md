# v116 — Part 4a: Phase 3 readiness (V116-20 … V116-22)

Header, global constraints, revision ids and the full parallelisation map: `_0-index.md`. Spec: `docs/superpowers/specs/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 3. V116-23 … V116-26 are `_4b-readiness.md`; the flips are `_4c-flips.md`.

**Parallelisation (Phase 3 readiness, group D — after Phase 1):**
- **Chain 1:** V116-20 → V116-21. Same file (`scripts/db/export_json.py`); V116-21 extends the writer table V116-20 introduces.
- **Chain 2:** V116-22 → V116-23. Both edit `swingbot/commands/scanning/loops.py`, `swingbot/commands/scanning/runstate.py` and `swingbot/admin/app.py`. Chain 2 also waits for V116-07 (Phase 0), which edits `loops.py` first.
- **V116-24** runs in parallel with both chains (its own new files), after V116-06 (it imports `parity_report.STAGE_STORES`).
- **V116-25** after V116-21 (it round-trips the ops-store exports V116-21 adds).
- **V116-26** after every other task here, and after Phase 0 has shipped (V116-09): it ships this group and installs the soak cron.
- Group D shares no file with group C (Phase 2), so the two run in parallel.

Every command runs from the worktree root; Postgres tests need `docker compose --profile test up -d db-test`.

---

# Phase 3 — Staged production flip (readiness)

### Task V116-20: `export_json` shapers for every Part 3 store

**Files:**
- Modify: `scripts/db/export_json.py`
- Create: `tests/db/test_export_json_part3.py`

**Interfaces:**
- Consumes: `parity_report.STORES` and its `from_repo_shape` functions, `part3_sources` loaders (main); `store_db` (V116-12).
- Produces: `export_json.KINDS: dict[str, str]` (`"file"` default, `"jsonl"`, `"dir"`), `WRITERS: dict[str, Callable[[str, Any], None]]`, `BUILDERS` (`account`, `ticker_directory`), shapers for `jobs`, `scheduled_jobs`, `preferences`, `settings_audit`, `killswitch`, `tuning`, `tuning_proposals`. `run_export(names, out_dir, *, dry_run, force)` now covers every `parity_report.STORES` name. V116-21 extends `WRITERS` and the name list; V116-25 and every Phase 3 rollback-to-dual use `run_export`.

- [ ] **Step 1: Write the failing test** — `tests/db/test_export_json_part3.py`:

```python
"""export_json writes every Part 3 store back in its on-disk shape (v116).

The check is that the file export_json writes is read back by parity's own
loader (the one the importers and the running bot's JSON path agree with) as
exactly the rows the table holds: DB -> JSON is the inverse of JSON -> DB."""
import json
import os

import pytest

from scripts.db import export_json
from scripts.db.parity_report import STORES, parity
from swingbot.core.db.repositories.jobs import jobs_repo
from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.db.repositories.preferences import preferences_repo
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.db.repositories.settings_audit import settings_audit_repo
from swingbot.core.db.repositories.ticker_directory import ticker_directory_repo
from swingbot.core.db.repositories.tuning import proposals_repo, tuning_repo

TS = "2026-10-01T10:00:00+00:00"
PART3 = ["jobs", "scheduled_jobs", "preferences", "settings_audit", "killswitch",
         "ticker_directory", "tuning", "tuning_proposals"]


@pytest.fixture
def seeded(store_db):
    jobs_repo().put({"id": "J1", "kind": "tune", "state": "done", "started_at": TS,
                     "finished_at": TS, "progress": {"pct": 100}})
    scheduled_repo().mark("daily_recap", "2026-10-01")
    preferences_repo().save({"columns": {"trades": ["ticker", "r"]}})
    settings_audit_repo().append([{"key": "A", "old": "1", "new": "2"}], ts=TS)
    settings_audit_repo().append([{"key": "B", "old": "x", "new": "y"}], ts=TS)
    killswitch_repo().engage("drawdown")
    ticker_directory_repo().replace([{"symbol": "AAPL", "name": "Apple"},
                                     {"symbol": "MSFT", "name": "Microsoft"}])
    tuning_repo().save_result("J1", {"best": {"x": 1}})
    proposals_repo().save("2026-10-01_rsi.json", {"params": {"a": 1}}, created_at=TS)
    return store_db


@pytest.mark.parametrize("name", PART3)
def test_the_export_reads_back_through_parity_as_the_table(name, seeded, tmp_path):
    results = export_json.run_export([name], str(tmp_path), dry_run=False, force=False)
    assert results[0].status == "written"
    report = parity(name, source_path=str(tmp_path / STORES[name].filename))
    assert report.ok, report.render()


def test_on_disk_shapes_match_what_the_bot_reads(seeded, tmp_path):
    export_json.run_export(["all"], str(tmp_path), dry_run=False, force=False)
    assert isinstance(json.loads((tmp_path / "admin_jobs.json").read_text()), dict)
    assert json.loads((tmp_path / "scheduled_jobs.json").read_text()) == {"daily_recap": "2026-10-01"}
    lines = (tmp_path / "settings_audit.jsonl").read_text().splitlines()
    assert [json.loads(line)["changes"][0]["key"] for line in lines] == ["A", "B"]
    assert json.loads((tmp_path / "killswitch.json").read_text())["on"] is True
    directory = json.loads((tmp_path / "ticker_directory.json").read_text())
    assert [row["symbol"] for row in directory["rows"]] == ["AAPL", "MSFT"]
    assert directory["fetched_at"] > 0
    assert sorted(os.listdir(tmp_path / "tuning_results")) == ["J1.json"]
    assert sorted(os.listdir(tmp_path / "tuning_proposals")) == ["2026-10-01_rsi.json"]


def test_a_directory_export_removes_a_result_the_table_no_longer_has(seeded, tmp_path):
    stale = tmp_path / "tuning_results"
    stale.mkdir()
    export_json.run_export(["tuning"], str(tmp_path), dry_run=False, force=True)
    (stale / "GONE.json").write_text("{}")
    export_json.run_export(["tuning"], str(tmp_path), dry_run=False, force=True)
    assert sorted(os.listdir(stale)) == ["J1.json"]


def test_a_differing_jsonl_is_refused_without_force(seeded, tmp_path):
    (tmp_path / "settings_audit.jsonl").write_text('{"ts": "x", "changes": []}\n')
    result = export_json.run_export(["settings_audit"], str(tmp_path), dry_run=False, force=False)[0]
    assert result.status == "refused"
    assert (tmp_path / "settings_audit.exported.jsonl").exists()


def test_every_parity_store_is_exportable():
    assert set(STORES) <= set(export_json.exportable_names())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_export_json_part3.py`
Expected: FAIL — `SystemExit: export_json: no JSON shaper for store(s): jobs` and `AttributeError: exportable_names`.

- [ ] **Step 3: Shapers, builder and writers** — in `scripts/db/export_json.py`, add `import json` to the imports, then after `_shape_starred`:

```python
def _without(row: dict, *keys: str) -> dict:
    return {key: value for key, value in row.items() if key not in keys}


def _shape_jobs(rows: list[dict]) -> Any:
    return {row["id"]: row for row in _sorted_by(rows, "started_at", "id")}


def _shape_scheduled(rows: list[dict]) -> Any:
    return {row["job"]: row["fired_on"] for row in _sorted_by(rows, "job")}


def _shape_preferences(rows: list[dict]) -> Any:
    owned = [row for row in rows if row.get("owner") == "admin"]
    return _without(owned[0], "owner") if owned else {}


def _shape_audit(rows: list[dict]) -> Any:
    return [{"ts": row["ts"], "changes": row.get("changes") or []}
            for row in sorted(rows, key=lambda row: row["seq"])]


def _shape_killswitch(rows: list[dict]) -> Any:
    return _without(rows[0], "key") if rows else {}


def _shape_tuning(rows: list[dict]) -> Any:
    return {f"{row['job_id']}.json": _without(row, "job_id", "created_at")
            for row in _sorted_by(rows, "job_id")}


def _shape_proposals(rows: list[dict]) -> Any:
    return {row["filename"]: _without(row, "filename") for row in _sorted_by(rows, "filename")}


def _build_ticker_directory() -> Any:
    from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
    repo = TickerDirectoryRepository()
    return {"fetched_at": repo.loaded_at(), "rows": _sorted_by(_rows("ticker_directory"), "symbol")}
```

Replace the `SHAPERS` dict, `build_payload`, `_record_count`, `_sidecar`, `_decide`, `export_one` and `run_export` with:

```python
SHAPERS: dict[str, Callable[[list[dict]], Any]] = {
    "trades": _shape_trades, "plans": _shape_plans, "journal": _shape_journal,
    "state": _shape_state, "watchlist": _shape_watchlist,
    "starred_plans": _shape_starred,
    # v116: Part 3.
    "jobs": _shape_jobs, "scheduled_jobs": _shape_scheduled,
    "preferences": _shape_preferences, "settings_audit": _shape_audit,
    "killswitch": _shape_killswitch, "tuning": _shape_tuning,
    "tuning_proposals": _shape_proposals,
}

#: Stores whose document is not a function of their rows alone.
BUILDERS: dict[str, Callable[[], Any]] = {
    "account": _build_account, "ticker_directory": _build_ticker_directory,
}

#: How a store lands on disk; absent means one JSON document ("file").
KINDS: dict[str, str] = {"settings_audit": "jsonl", "tuning": "dir", "tuning_proposals": "dir"}


def _kind(name: str) -> str:
    return KINDS.get(name, "file")


def _write_jsonl(path: str, payload: list) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        for entry in payload:
            handle.write(json.dumps(entry) + "\n")
    os.replace(tmp, path)


def _write_dir(path: str, payload: dict) -> None:
    """The table is the truth: a file it no longer has is removed."""
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        if name.endswith(".json") and name not in payload:
            os.remove(os.path.join(path, name))
    for name, content in payload.items():
        atomic_write_json(os.path.join(path, name), content)


WRITERS: dict[str, Callable[[str, Any], None]] = {
    "file": atomic_write_json, "jsonl": _write_jsonl, "dir": _write_dir,
}


def _read_jsonl(path: str) -> list | None:
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _read_dir(path: str) -> dict:
    return {name: read_json(os.path.join(path, name), None)
            for name in sorted(os.listdir(path)) if name.endswith(".json")}


_READERS = {"file": lambda path: read_json(path, None), "jsonl": _read_jsonl, "dir": _read_dir}


def build_payload(name: str) -> Any:
    """Return the JSON-ready document for one store, in on-disk shape."""
    if name in BUILDERS:
        return normalise(BUILDERS[name]())
    return normalise(SHAPERS[name](_rows(name)))


def _record_count(name: str, payload: Any) -> int:
    if name == "account":
        return len(payload.get("balance_history", [])) + (1 if payload else 0)
    if name == "ticker_directory":
        return len(payload.get("rows", []))
    return len(payload)


def _sidecar(path: str, kind: str) -> str:
    if kind == "dir":
        return f"{path}.exported"
    stem, ext = os.path.splitext(path)
    return f"{stem}.exported{ext}"


def _decide(path: str, kind: str, checksum: str, force: bool) -> tuple[str, str]:
    """Return (status, target_path) for a write to ``path``."""
    if not os.path.exists(path):
        return "written", path
    if record_checksum({"v": _READERS[kind](path)}) == checksum:
        return "unchanged", path
    return ("written", path) if force else ("refused", _sidecar(path, kind))


def export_one(name: str, out_dir: str, *, dry_run: bool, force: bool) -> ExportResult:
    payload = build_payload(name)
    checksum = record_checksum({"v": payload})
    kind = _kind(name)
    path = os.path.join(out_dir, STORES[name].filename)
    status, target = _decide(path, kind, checksum, force)
    if dry_run:
        status = "dry-run"
    elif status != "unchanged":
        WRITERS[kind](target, payload)
    return ExportResult(name, _record_count(name, payload), checksum, target, status)


def exportable_names() -> list[str]:
    return sorted(name for name in STORES if name in BUILDERS or name in SHAPERS)


def run_export(names: list[str], out_dir: str, *, dry_run: bool, force: bool) -> list[ExportResult]:
    exportable = exportable_names()
    selected = exportable if "all" in names else names
    unshaped = [name for name in selected if name not in exportable]
    if unshaped:
        raise SystemExit(f"export_json: no JSON shaper for store(s): {', '.join(unshaped)}")
    os.makedirs(out_dir, exist_ok=True)
    return [export_one(name, out_dir, dry_run=dry_run, force=force) for name in selected]
```

Update the module docstring's restart warning list to "every store singleton" and leave `RESTART_WARNING` as is.

- [ ] **Step 4: Run the new and existing export tests**

Run: `python scripts/dev/testrun.py file tests/db/test_export_json_part3.py tests/db/test_export_json_roundtrip.py tests/scripts/test_export_json.py`
Expected: PASS.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C scripts/db/export_json.py` — no output.

```bash
git add scripts/db/export_json.py tests/db/test_export_json_part3.py
git commit -m "feat(v116): export_json writes every Part 3 store back in its on-disk shape

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-21: `export_json` for the ephemeral ops stores

**Files:**
- Modify: `scripts/db/export_json.py` (`EXTRA` specs, flag/optional writers, `export_one` dispatch, CLI choices)
- Create: `tests/db/test_export_json_ops.py`

**Interfaces:**
- Consumes: `FLAGS`/`flags_repo`, `heartbeat_repo`, `NotifyQueueRepository`, `scan_progress_repo`, `market_data_state_repo` (main + V116-12); `WRITERS`, `run_export`, `exportable_names` (V116-20).
- Produces: `export_json.EXTRA: dict[str, ExtraSpec]` for stage names `flags`, `heartbeat`, `notify_queue`, `scan_progress`, `market_data_state`; `ExtraSpec(filename, build, kind)`. They have no parity spec, so an export always writes (no refuse/sidecar): at `db` the file is stale by definition. `notify_queue` export does **not** drain the table. `exportable_names()` includes them.

- [ ] **Step 1: Write the failing test** — `tests/db/test_export_json_ops.py`:

```python
"""export_json for the five ephemeral ops stores (v116). Proven by reading
each exported file back through the store's own JSON-stage reader."""
import json

from swingbot import config
from scripts.db import export_json
from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories.flags import flags_repo
from swingbot.core.db.repositories.heartbeat import heartbeat_repo
from swingbot.core.db.repositories.market_data_state import market_data_state_repo
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.scan_progress import scan_progress_repo
from swingbot.core.marketdata import data_refresh
from swingbot.core.scanning import progress_store

STATE = {"AAPL|daily": {"last_status": "failed", "fail_count": 1, "last_error": "x"}}
PROGRESS = {"at": "2026-10-01T10:00:00+00:00", "pct": 50, "stage": "analyzing"}


def _seed():
    flags_repo().set("scan_paused")
    heartbeat_repo().beat({"session_active": True, "consecutive_failures": 2})
    queue = NotifyQueueRepository()
    queue.enqueue({"trade_id": "T1"})
    queue.enqueue({"trade_id": "T2"})
    scan_progress_repo().publish(PROGRESS)
    market_data_state_repo().save(STATE)


def test_every_ops_store_exports_and_reads_back_at_the_json_stage(store_db, tmp_path, monkeypatch):
    _seed()
    (tmp_path / "trigger_check.flag").write_text("stale")
    names = ["flags", "heartbeat", "notify_queue", "scan_progress", "market_data_state"]
    results = export_json.run_export(names, str(tmp_path), dry_run=False, force=False)
    assert {r.name: r.status for r in results} == {name: "written" for name in names}

    monkeypatch.setattr(config, "DB_STORES", "")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_PAUSE_FILE", str(tmp_path / "scan_paused.flag"))
    monkeypatch.setattr(runstate, "_TRIGGER_FILE", str(tmp_path / "trigger_check.flag"))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(data_refresh, "STATE_FILE", str(tmp_path / "market_data_state.json"))
    assert runstate.is_scan_paused() is True
    assert runstate.is_trigger_requested() is False        # the stale flag was removed
    assert runstate._read_heartbeat()["consecutive_failures"] == 2
    queued = json.loads((tmp_path / "manual_close_notify.json").read_text())
    assert [r["trade_id"] for r in queued] == ["T1", "T2"]
    assert all("queued_at" not in r for r in queued)
    assert progress_store.read() == PROGRESS
    assert data_refresh.load_state() == STATE


def test_exporting_the_queue_does_not_drain_it(store_db, tmp_path):
    _seed()
    export_json.run_export(["notify_queue"], str(tmp_path), dry_run=False, force=False)
    assert NotifyQueueRepository().pending() == 2


def test_no_scan_in_progress_removes_the_progress_file(store_db, tmp_path):
    (tmp_path / "scan_progress.json").write_text(json.dumps(PROGRESS))
    export_json.run_export(["scan_progress"], str(tmp_path), dry_run=False, force=False)
    assert not (tmp_path / "scan_progress.json").exists()


def test_the_ops_stores_are_exportable_names():
    assert {"flags", "heartbeat", "notify_queue", "scan_progress",
            "market_data_state"} <= set(export_json.exportable_names())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_export_json_ops.py`
Expected: FAIL — `SystemExit: export_json: no JSON shaper for store(s): flags, …`.

- [ ] **Step 3: Add the extra specs and writers** — in `scripts/db/export_json.py`, after `WRITERS`:

```python
@dataclass(frozen=True)
class ExtraSpec:
    """An ephemeral ops store: no parity spec, and at `db` its file is stale
    by definition, so an export always writes it."""
    filename: str
    build: Callable[[], Any]
    kind: str              # "file" | "flags" | "optional"


def _build_flags() -> dict:
    from swingbot.core.db.repositories.flags import FLAGS, flags_repo
    repo = flags_repo()
    return {name: normalise(repo.set_at(name)) for name in FLAGS if repo.is_set(name)}


def _build_heartbeat() -> dict:
    from swingbot.core.db.repositories.heartbeat import heartbeat_repo
    return normalise(heartbeat_repo().last() or {})


def _build_notify_queue() -> list:
    from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
    rows = sorted(NotifyQueueRepository().list_all(), key=lambda row: str(row.get("queued_at")))
    return [normalise(_without(row, "queued_at")) for row in rows]


def _build_scan_progress() -> dict | None:
    from swingbot.core.db.repositories.scan_progress import scan_progress_repo
    record = scan_progress_repo().read()
    return None if record is None else normalise(record)


def _build_market_data_state() -> dict:
    from swingbot.core.db.repositories.market_data_state import market_data_state_repo
    return normalise(market_data_state_repo().load())


def _write_flags(out_dir: str, payload: dict) -> None:
    from swingbot.core.db.repositories.flags import FLAGS
    for name in FLAGS:
        path = os.path.join(out_dir, f"{name}.flag")
        if name in payload:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(payload[name]))
        elif os.path.exists(path):
            os.remove(path)


def _write_optional(path: str, payload: Any) -> None:
    if payload is None:
        if os.path.exists(path):
            os.remove(path)
        return
    atomic_write_json(path, payload)


EXTRA: dict[str, ExtraSpec] = {
    "flags": ExtraSpec("", _build_flags, "flags"),
    "heartbeat": ExtraSpec("bot_heartbeat.json", _build_heartbeat, "file"),
    "notify_queue": ExtraSpec("manual_close_notify.json", _build_notify_queue, "file"),
    "scan_progress": ExtraSpec("scan_progress.json", _build_scan_progress, "optional"),
    "market_data_state": ExtraSpec("market_data_state.json", _build_market_data_state, "file"),
}


def _export_extra(name: str, out_dir: str, *, dry_run: bool) -> ExportResult:
    spec = EXTRA[name]
    payload = spec.build()
    checksum = record_checksum({"v": payload})
    target = out_dir if spec.kind == "flags" else os.path.join(out_dir, spec.filename)
    count = 0 if payload is None else len(payload)
    if dry_run:
        return ExportResult(name, count, checksum, target, "dry-run")
    if spec.kind == "flags":
        _write_flags(out_dir, payload)
    elif spec.kind == "optional":
        _write_optional(target, payload)
    else:
        atomic_write_json(target, payload)
    return ExportResult(name, count, checksum, target, "written")
```

At the top of `export_one` add the dispatch, and extend `exportable_names` and the CLI:

```python
def export_one(name: str, out_dir: str, *, dry_run: bool, force: bool) -> ExportResult:
    if name in EXTRA:
        return _export_extra(name, out_dir, dry_run=dry_run)
    payload = build_payload(name)
    # ... rest unchanged from V116-20
```

```python
def exportable_names() -> list[str]:
    shaped = [name for name in STORES if name in BUILDERS or name in SHAPERS]
    return sorted(shaped + list(EXTRA))
```

In `main`: `choices=sorted(STORES) + ["all"]` → `choices=exportable_names() + ["all"]`.

- [ ] **Step 4: Run all export tests**

Run: `python scripts/dev/testrun.py file tests/db/test_export_json_ops.py tests/db/test_export_json_part3.py tests/db/test_export_json_roundtrip.py tests/scripts/test_export_json.py`
Expected: PASS.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C scripts/db/export_json.py` — no output.

```bash
git add scripts/db/export_json.py tests/db/test_export_json_ops.py
git commit -m "feat(v116): export_json covers flags, heartbeat, notify queue, scan progress, market-data state

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-22: Two stage bugs that block the ops flip — heartbeat reads, notify-queue drain

**Files:**
- Modify: `swingbot/commands/scanning/runstate.py` (`_read_heartbeat`)
- Modify: `swingbot/admin/app.py` (`scan_status_payload`'s heartbeat block → `_heartbeat_snapshot`, `_heartbeat_status`, `_parse_iso`)
- Modify: `swingbot/commands/scanning/loops.py` (`config_watcher`'s queue block → `_read_queue_file`, `_take_manual_close_queue`, `_post_manual_close_queue`)
- Create: `tests/commands/test_heartbeat_stage_reads.py`, `tests/commands/test_manual_close_queue_dual.py`

**Interfaces:**
- Consumes: `heartbeat_repo`, `notify_queue_repo`, `store_db`; V116-07's `loops.py`; the merged branch's `app.py`.
- Produces: at `heartbeat:db` the bot's failure counter and alert flag, and the admin's `bot_alive`/`bot_healthy`/`bot_consecutive_failures`, come from the `bot_heartbeat` row (at `json`/`dual`: the file, unchanged). At `notify_queue:dual` the bot drains the table's shadow copy every time it drains the file, so the `db` flip replays nothing. `app._heartbeat_status(hb, seen, threshold) -> dict` is what V116-23 extends.

Both bugs were found while planning (`_0-index.md` § Spec points, 6): `_read_heartbeat()` is file-only, so at `heartbeat:db` `record_tick_failure()` returns 1 forever and the v71 escalation never fires; `scan_status_payload()` reads `bot_heartbeat.json` directly, so the admin shows the bot offline; and `config_watcher` at `dual` drains only the file, so the table keeps every queued close and posts them all again at the flip.

- [ ] **Step 1: Write the failing tests**

`tests/commands/test_heartbeat_stage_reads.py`:

```python
"""At heartbeat:db the counter, the alert flag and the admin read the row (v116)."""
import pytest

from swingbot import config
from swingbot.commands.scanning import runstate


@pytest.fixture
def at_db(tmp_path, store_db, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(config, "DB_STORES", "heartbeat:db")
    return tmp_path


def test_the_failure_counter_counts_at_the_db_stage(at_db):
    assert runstate.record_tick_failure() == 1
    assert runstate.record_tick_failure() == 2
    runstate.set_alert_active(True)
    assert runstate.get_alert_active() is True
    assert runstate.record_tick_success() is True
    assert runstate._read_heartbeat()["consecutive_failures"] == 0
    assert not (at_db / "bot_heartbeat.json").exists()


def test_the_admin_reads_the_row_at_the_db_stage(at_db):
    from swingbot.admin import app as admin_app
    runstate._write_heartbeat()
    runstate.record_tick_failure()
    payload = admin_app.scan_status_payload()
    assert payload["bot_alive"] is True
    assert payload["bot_consecutive_failures"] == 1
    assert payload["bot_last_seen"] is not None


def test_the_json_stage_still_reads_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate.record_tick_failure()
    assert runstate.record_tick_failure() == 2
    assert (tmp_path / "bot_heartbeat.json").exists()
```

`tests/commands/test_manual_close_queue_dual.py`:

```python
"""notify_queue at dual: the file is the truth and the table its shadow, so
both are drained together and the db flip replays nothing (v116)."""
import asyncio
import json

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository

RECORD = {"trade_id": "T1", "ticker": "AAPL"}


@pytest.fixture
def posted(tmp_path, store_db, monkeypatch):
    sent = []

    async def fake_notify(_bot, records):
        sent.extend(records)

    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_closed_trades", fake_notify)
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE",
                        str(tmp_path / "manual_close_notify.json"))
    return sent


def _queue_both(tmp_path):
    (tmp_path / "manual_close_notify.json").write_text(json.dumps([RECORD]))
    NotifyQueueRepository().enqueue(dict(RECORD))


def test_dual_posts_the_file_once_and_drains_the_shadow(tmp_path, posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:dual")
    _queue_both(tmp_path)
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]
    assert NotifyQueueRepository().pending() == 0
    assert not (tmp_path / "manual_close_notify.json").exists()


def test_flipping_to_db_after_a_dual_soak_replays_nothing(tmp_path, posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:dual")
    _queue_both(tmp_path)
    asyncio.run(loops._post_manual_close_queue())
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:db")
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]


def test_the_db_stage_drains_the_table(posted, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "notify_queue:db")
    NotifyQueueRepository().enqueue(dict(RECORD))
    asyncio.run(loops._post_manual_close_queue())
    assert posted == [RECORD]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_heartbeat_stage_reads.py tests/commands/test_manual_close_queue_dual.py`
Expected: FAIL — `assert 1 == 2` on the counter; `AttributeError: … _post_manual_close_queue`.

- [ ] **Step 3: `runstate._read_heartbeat` honours the stage**

```python
def _read_heartbeat() -> dict:
    """Current heartbeat state, or {} when absent or unreadable.

    Absent is "unknown", never "failing" -- an upgraded admin container reads
    state written by a bot that has not restarted yet. At heartbeat:db the
    row is the only copy (v116: this read was file-only, which reset the
    failure counter every tick at db).
    """
    from swingbot.core.db import stages
    if stages.reads_db("heartbeat"):
        try:
            from swingbot.core.db.repositories.heartbeat import heartbeat_repo
            return heartbeat_repo().last() or {}
        except Exception:
            return {}
    try:
        with open(_HEARTBEAT_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
```

- [ ] **Step 4: The admin reads the heartbeat of the current stage** — in `swingbot/admin/app.py`, add above `scan_status_payload`:

```python
def _parse_iso(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _heartbeat_snapshot() -> tuple[dict, datetime | None]:
    """(heartbeat fields, when last seen) from the current stage's store.
    json/dual: the file and its mtime, exactly as before. db: the row and
    its `timestamp` field (v116)."""
    from swingbot.core.db import stages
    if stages.reads_db("heartbeat"):
        from swingbot.commands.scanning import runstate
        fields = runstate._read_heartbeat()
        return fields, _parse_iso(fields.get("timestamp"))
    path = os.path.join(config.DATA_DIR, "bot_heartbeat.json")
    try:
        seen = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        return {}, None
    try:
        with open(path) as handle:
            fields = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}, seen
    return (fields if isinstance(fields, dict) else {}), seen


def _heartbeat_status(hb: dict, seen: datetime | None, threshold: float) -> dict:
    now = datetime.now(timezone.utc)
    last_success = hb.get("last_success")
    success_at = _parse_iso(last_success)
    return {
        "bot_alive": seen is not None and (now - seen).total_seconds() < threshold,
        "bot_last_seen": seen.isoformat() if seen else None,
        "bot_session_active": hb.get("session_active"),
        "bot_scan_paused": hb.get("scan_paused"),
        "bot_healthy": None if success_at is None else (now - success_at).total_seconds() < threshold,
        "bot_last_success": last_success,
        "bot_consecutive_failures": int(hb.get("consecutive_failures") or 0),
    }
```

In `scan_status_payload`, delete everything from the comment `# Bot liveness: the heartbeat file is written…` through the heartbeat `try/except` block, and build the return value as:

```python
    # Bot liveness: written on every session_scan tick (every
    # SCAN_INTERVAL_MINUTES). Older than 2x that interval means the bot
    # process is likely hung or offline.
    threshold = config.SCAN_INTERVAL_MINUTES * 60 * 2
    hb, seen = _heartbeat_snapshot()
    return {
        "pending": pending, "triggered_at": mtime, "paused": paused, "paused_at": paused_at,
        "running": running,
        # None whenever no scan is publishing, which the SPA must render as
        # "no bar" rather than as 0% -- see progress_store.
        "progress": progress_store.read(),
        **_heartbeat_status(hb, seen, threshold),
    }
```

- [ ] **Step 5: The queue drain becomes a helper, and drains the shadow at dual** — in `swingbot/commands/scanning/loops.py`, add before `config_watcher`:

```python
def _read_queue_file() -> list:
    if not os.path.exists(runstate._MANUAL_CLOSE_QUEUE):
        return []
    try:
        with open(runstate._MANUAL_CLOSE_QUEUE, "r") as handle:
            data = json.load(handle)
    except Exception as exc:
        log.warning("Could not read manual_close_notify queue: %s", exc, exc_info=True)
        return []
    return data if isinstance(data, list) else []


def _take_manual_close_queue() -> list:
    """Remove and return the queued manual-close records.

    At notify_queue:db the table is the queue. At dual the file is the truth
    and the table its shadow: both are drained together, or the table keeps
    every close queued during the soak and replays them all at the db flip
    (v116). At json only the file exists.
    """
    from swingbot.core.db import stages
    if stages.reads_db("notify_queue"):
        from swingbot.core.db.repositories.notify_queue import notify_queue_repo
        return notify_queue_repo().drain()
    queued = _read_queue_file()
    if stages.writes_db("notify_queue"):
        from swingbot.core.db.repositories.notify_queue import notify_queue_repo
        notify_queue_repo().drain()
    if queued:
        try:
            os.remove(runstate._MANUAL_CLOSE_QUEUE)
        except OSError:
            pass
    return queued


async def _post_manual_close_queue() -> None:
    queued = _take_manual_close_queue()
    if not queued:
        return
    from swingbot.core.scanning.embeds import notify_closed_trades
    try:
        await notify_closed_trades(bot, queued)
        log.info("Posted %d manually-closed trade notification(s) to Discord.", len(queued))
    except Exception as exc:
        log.warning("Failed to post manual-close notifications: %s", exc, exc_info=True)
```

In `config_watcher`, replace the whole `# --- Admin UI manual-close notification queue ---` block (from `from swingbot.core.db import stages` through the `except Exception as _ne:` handler) with:

```python
    # --- Admin UI manual-close notification queue ---
    await _post_manual_close_queue()
```

- [ ] **Step 6: Run the new and existing heartbeat, scan-status and config-watcher tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_heartbeat_stage_reads.py tests/commands/test_manual_close_queue_dual.py tests/scanning/test_heartbeat_outcome.py tests/commands/test_heartbeat_db.py tests/admin/test_api_v1_system_scan.py tests/admin/test_scan_flags_stage.py tests/commands/test_config_watcher_reload.py tests/commands/test_config_watcher_task.py tests/commands/test_manual_close_queue_db.py`
Expected: PASS.

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s swingbot/commands/scanning/loops.py swingbot/admin/app.py swingbot/commands/scanning/runstate.py | grep -E "config_watcher|scan_status_payload|_heartbeat|_take_manual|_read_heartbeat"` — `config_watcher` below its 19, every other listed function below 15.

```bash
git add swingbot/commands/scanning/runstate.py swingbot/admin/app.py swingbot/commands/scanning/loops.py tests/commands/test_heartbeat_stage_reads.py tests/commands/test_manual_close_queue_dual.py
git commit -m "fix(v116): heartbeat reads and the manual-close queue drain honour the stage

At heartbeat:db the failure counter reset every tick and the admin showed the
bot offline; at notify_queue:dual the table kept every queued close and would
have replayed them all at the db flip.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
