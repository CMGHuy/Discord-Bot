# v218 — Admin snapshot, ETag/304 and Server-Timing — Part 1: the snapshot (V218-1..V218-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 3; L2 authority [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Layer 2 (L2-a..d).
**Index:** [`2026-11-06-v218-admin-snapshot-etag_0-index.md`](2026-11-06-v218-admin-snapshot-etag_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and the Handoff decisions. Every task below implicitly includes the index's Global Constraints.

**Worktree:** every task runs in `.claude/worktrees/2026-11-06-v218-admin-snapshot-etag` (branch of the same name). Paths below are relative to that worktree root.

**Scope of this part:** L2-a..d. `version()` twins and the recorded stamp gap (V218-1), the generation counters and the `ADMIN_STORE_SNAPSHOT` switch (V218-2), the always-on snapshot listener (V218-3), the snapshot itself (V218-4), the read-through from `read_memo` with the L2-c frozen double-run and midnight tests (V218-5), and the two existing `plans_repo().version()` callers keyed on the trades generation (V218-6). V218-5 and V218-6 live in [`_1b-read-through.md`](2026-11-06-v218-admin-snapshot-etag_1b-read-through.md): with them this file would pass 1500 lines.

**One addition beyond the ledger (additive, consumed only inside this part):** `store_snapshot.end_request() -> None`, created by V218-4 and called by V218-5 from `request_timing._teardown`. Without it the per-request version cache would outlive the request on a thread that keeps its context, and "outside a request it queries per call" (index, V218-4 note) would not hold. No other part depends on it.

# Phase 1 — versions, generations and the switch

### Task V218-1: Trades and journal `version()` twins; record the stamp gap for the existing callers

**Model:** sonnet — two small repository methods twinning an existing one, plus a two-connection DB test and a short Results note.

**Files:**
- Modify: `swingbot/core/db/repositories/trades.py` (new `TradeRepository.version`)
- Modify: `swingbot/core/db/repositories/journal.py` (new `JournalRepository.version`)
- Create: `tests/db/test_v218_store_versions.py`
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (append `### Plan 3 version() gap (V218-1)` at the end of the file, after `### Plan 2 after (committed probe)`)

**Interfaces:**
- Consumes: `PlanRepository.version(self, *, conn=None) -> tuple[int, str | None]` (`swingbot/core/db/repositories/plans.py:44`), the `tests/db/conftest.py` fixtures `db_engine`, `db_conn`, `db_committed`.
- Produces: `TradeRepository.version(self, *, conn=None) -> tuple[int, str | None]` and `JournalRepository.version(self, *, conn=None) -> tuple[int, str | None]`, both `(row count, max(updated_at).isoformat() or None)`. V218-4 reads all three per request; V218-8 hashes them into the ETag.

**Background.** `upsert()` and `patch()` stamp `updated_at` with `clock_timestamp()` (`repositories/base.py:89,101`), and `insert()` with the column default `now()` (transaction start, `schema.py:23-24`). Either way the stamp is taken *before* commit, so a transaction can commit after a concurrent one under an *older* stamp. `(count, max(updated_at))` then does not move although a row changed. The test below reproduces it. V218-6 closes it for the two existing callers by adding the NOTIFY-driven generation to their keys, and V218-4 never trusts versions alone (its token also carries the generations).

- [ ] **Step 0: Sync the local replica**

The test commits to Postgres. Run `/replicate-prod-db` once this session (shared `swing-db` container, port 56789, `.env` credentials never printed). Skip it if a sibling task in this session already ran it.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_v218_store_versions.py`:

```python
"""v218 V218-1: version() twins for trades and journal, and the stamp gap.

`(count, max(updated_at))` is a cheap change token, but the stamp is taken
before commit (`clock_timestamp()` in upsert/patch, `now()` in insert), so a
transaction that commits after a concurrent one can land under an older stamp
and leave the token unchanged. The gap tests below reproduce that on two real
connections; V218-6 adds the NOTIFY generation to the existing callers' keys."""
import time

import pytest

from swingbot.core.db.repositories.journal import JournalRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository


def _trade(trade_id, **overrides):
    trade = {"trade_id": trade_id, "ticker": "MSFT", "strategy": "swing", "horizon": "swing",
             "direction": "long", "status": "open", "opened_at": "2026-01-02T15:00:00+00:00"}
    trade.update(overrides)
    return trade


def _plan(plan_id, **overrides):
    plan = {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "status": "PENDING", "created_at": "2026-01-02T15:00:00+00:00",
            "entry": 100.0, "stop_loss": 95.0}
    plan.update(overrides)
    return plan


def _entry(trade_id, **overrides):
    entry = {"trade_id": trade_id, "strategy": "RSI", "outcome": "win",
             "closed_at": "2026-01-09T15:00:00+00:00", "created_at": "2026-01-09T16:00:00+00:00",
             "tags": [], "note": "", "lesson": ""}
    entry.update(overrides)
    return entry


@pytest.mark.parametrize("repo_cls, make", [(TradeRepository, _trade), (JournalRepository, _entry)])
def test_version_is_count_and_newest_stamp_and_moves_on_every_write(repo_cls, make, db_conn):
    repo = repo_cls()
    assert repo.version(conn=db_conn) == (0, None)
    repo.insert(make("A"), conn=db_conn)
    inserted = repo.version(conn=db_conn)
    assert inserted[0] == 1 and isinstance(inserted[1], str)
    repo.upsert(make("A", strategy="changed"), conn=db_conn)
    updated = repo.version(conn=db_conn)
    repo.delete("A", conn=db_conn)
    assert inserted != updated                          # clock_timestamp() moved inside one tx
    assert repo.version(conn=db_conn) == (0, None)


def test_version_shape_matches_the_plans_twin(db_conn):
    PlanRepository().insert(_plan("P1"), conn=db_conn)
    TradeRepository().insert(_trade("T1"), conn=db_conn)
    JournalRepository().insert(_entry("T1"), conn=db_conn)
    shapes = [type(part) for repo in (PlanRepository(), TradeRepository(), JournalRepository())
              for part in repo.version(conn=db_conn)]
    assert shapes == [int, str] * 3


def _version(engine, repo):
    with engine.begin() as connection:
        return repo.version(conn=connection)


def _gap(engine, repo, make, changed):
    """Commit X's change under an older stamp than Y's; return (after_y, after_x)."""
    with engine.begin() as connection:
        repo.insert(make("X"), conn=connection)
        repo.insert(make("Y"), conn=connection)
    slow = engine.connect()
    slow_tx = slow.begin()
    try:
        repo.upsert(make("X", **changed), conn=slow)     # stamped now, not yet committed
        time.sleep(0.01)
        with engine.begin() as fast:
            repo.upsert(make("Y", **changed), conn=fast)  # later stamp, commits first
        after_y = _version(engine, repo)
        slow_tx.commit()                                 # X commits under the OLDER stamp
    finally:
        slow.close()
    return after_y, _version(engine, repo)


def test_trades_version_misses_a_commit_stamped_before_a_concurrent_one(db_engine, db_committed):
    repo = TradeRepository()
    after_y, after_x = _gap(db_engine, repo, _trade, {"status": "win"})
    with db_engine.begin() as connection:
        assert repo.get("X", conn=connection)["status"] == "win"      # X really changed
    assert after_x == after_y                                         # ...and the token did not move


def test_plans_version_has_the_same_gap_the_existing_callers_rely_on(db_engine, db_committed):
    """cancel_precision._memo_key and watchlist_rows._plans_signature key on this."""
    repo = PlanRepository()
    after_y, after_x = _gap(db_engine, repo, _plan, {"status": "ACTIVE"})
    with db_engine.begin() as connection:
        assert repo.get("X", conn=connection)["status"] == "ACTIVE"
    assert after_x == after_y
```

`db_committed` is requested only for its teardown: it truncates every table after the test, because these tests commit.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v218_store_versions.py`
Expected: FAIL with `AttributeError: 'TradeRepository' object has no attribute 'version'` (and the same for `JournalRepository`). The plans gap test already passes, because it documents existing behaviour.

- [ ] **Step 3: Implement the twins**

In `swingbot/core/db/repositories/trades.py`, add after `clear()` inside `TradeRepository` (`sa` and `trades` are already imported):

```python
    def version(self, *, conn=None) -> tuple[int, str | None]:
        """(row count, newest updated_at) -- the twin of PlanRepository.version().

        Moves on any insert, update or delete, except that a write can commit
        under an older stamp than a concurrent one (V218-1): a cache keyed on
        it alone can miss that write, so v218 keys add the NOTIFY generation."""
        statement = sa.select(sa.func.count(), sa.func.max(trades.c.updated_at))
        with self._tx(conn) as connection:
            count, newest = connection.execute(statement).one()
        return int(count), None if newest is None else newest.isoformat()
```

In `swingbot/core/db/repositories/journal.py`, add after `entries()` inside `JournalRepository` (`sa` and `journal_entries` are already imported):

```python
    def version(self, *, conn=None) -> tuple[int, str | None]:
        """(row count, newest updated_at) over journal_entries -- the twin of
        PlanRepository.version(); same commit-order caveat (V218-1)."""
        statement = sa.select(sa.func.count(), sa.func.max(journal_entries.c.updated_at))
        with self._tx(conn) as connection:
            count, newest = connection.execute(statement).one()
        return int(count), None if newest is None else newest.isoformat()
```

- [ ] **Step 4: Run them to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_v218_store_versions.py`
Expected: PASS (5 tests). Then run `python scripts/dev/testrun.py file tests/db/test_plans_repository.py`, `... file tests/db/test_trades_repository.py` and `... file tests/db/test_journal_repository.py`. Expected: PASS, unchanged.

- [ ] **Step 5: Record the gap in the v206 spec**

Append to the end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`:

```markdown
### Plan 3 version() gap (V218-1)

`(count, max(updated_at))` is built from stamps written before commit:
`upsert()`/`patch()` use `clock_timestamp()` (`repositories/base.py:89,101`),
`insert()` uses the column default `now()` (transaction start). A transaction that
commits after a concurrent one can therefore land under an older stamp, and the
token does not move although a row changed.
`tests/db/test_v218_store_versions.py` reproduces it on two real connections for
`trades` (`TradeRepository.version()`, new in V218-1) and `plans`.

Existing callers of `plans_repo().version()`:

| Caller | Use | Verdict |
|---|---|---|
| `swingbot/admin/api_v1/cancel_precision.py:38-41` `_memo_key()` | memo key `(version, UTC hour)` of the cancel-precision payload | affected: an upsert committed under an older stamp leaves `(count, max)` unchanged, so the memo serves the old payload until the hour turns |
| `swingbot/admin/watchlist_rows.py:67-73` `_plans_signature()` | signature `("db", count, max)` of the watchlist plan projection | affected: same mechanism; stale until a later plan write moves the token |

Fix: V218-6 appends `store_generation.generation("trades")` to both keys. The
v218 snapshot listener bumps that generation on every `trades` NOTIFY, and the
`plans` and `starred_plans` triggers fire that channel too. The snapshot (V218-4)
and the ETag (V218-8) never trust versions alone either: their tokens carry the
generations too.
```

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/trades.py swingbot/core/db/repositories/journal.py tests/db/test_v218_store_versions.py
git commit -m "feat(db): trades and journal version() twins; test reproduces the commit-order stamp gap"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 3 version() gap recorded for the two existing callers"
```

### Task V218-2: Generation counters, settings generation on reload, `ADMIN_STORE_SNAPSHOT` switch

**Model:** sonnet — a leaf module of counters plus one config Field modelled on `ADMIN_REFRESHER`; no cross-package design.

**Files:**
- Create: `swingbot/core/infra/store_generation.py`
- Modify: `swingbot/config.py` (new Field after `ADMIN_SLOW_REQUEST_MS` at :1048; `_MODE_VALUES` :1651; `_MODE_FALLBACK` :1669; `reload()` :1828)
- Modify: `.env.example` (after `ADMIN_SLOW_REQUEST_MS=2000`, line 549)
- Create: `tests/admin_perf/test_store_generation.py`
- Create: `tests/test_config_v218_keys.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (final names, consumed by V218-3, V218-4, V218-6, V218-8):
  - `store_generation.CONCERNS = ("trades", "journal", "settings")`
  - `bump(concern: str) -> int` (new value; `KeyError` for an unknown concern)
  - `bump_all() -> None`
  - `generation(concern: str) -> int`
  - `token() -> tuple[int, int, int]` (in `CONCERNS` order)
  - `set_connected(flag: bool) -> None` (logs each transition once)
  - `connected() -> bool` (starts `False`)
  - `reset() -> None` (all counters 0, `connected` False; test seam)
  - `config.ADMIN_STORE_SNAPSHOT: str` in `{"on", "off"}`, default `"on"`; an invalid value falls back to `"on"`.

**Background.** The admin gets no SIGHUP. Its `@app.before_request _reload_env_if_changed` (`swingbot/admin/app.py:269`) calls `config.auto_reload_if_changed()` on every request, which calls `reload()` only when the `.env` mtime or size changed. The settings generation is therefore bumped inside `reload()` whenever `_apply_env()` reports a changed value (index Handoff 3). `store_generation` imports nothing from `swingbot` (a leaf, like `read_memo`), so `config` can import it lazily without a cycle.

`grep -n '"Admin UI"' tests frontend/src` finds only `tests/test_config_v205_keys.py`, which pins `ADMIN_SLOW_REQUEST_MS` right after `LOGS_REFRESH_SECONDS`. That test stays green because the new Field goes *after* `ADMIN_SLOW_REQUEST_MS`. No settings-page test counts fields per section.

- [ ] **Step 1: Write the failing generation tests**

Create `tests/admin_perf/test_store_generation.py`:

```python
"""v218 V218-2: process-wide change generations behind the admin snapshot (v205 L2-b)."""
import ast
import logging
import pathlib
import threading

import pytest

from swingbot.core.infra import store_generation as sg

SOURCE = pathlib.Path(sg.__file__)


@pytest.fixture(autouse=True)
def _clean():
    sg.reset()
    yield
    sg.reset()


def test_concerns_are_trades_journal_settings_and_start_at_zero():
    assert sg.CONCERNS == ("trades", "journal", "settings")
    assert sg.token() == (0, 0, 0)
    assert sg.connected() is False


def test_bump_moves_one_concern_and_returns_its_new_value():
    assert sg.bump("journal") == 1
    assert sg.bump("journal") == 2
    assert sg.generation("journal") == 2
    assert sg.token() == (0, 2, 0)


def test_an_unknown_concern_is_refused():
    with pytest.raises(KeyError):
        sg.bump("market")
    with pytest.raises(KeyError):
        sg.generation("market")


def test_bump_all_moves_every_concern():
    sg.bump("trades")
    sg.bump_all()
    assert sg.token() == (2, 1, 1)


def test_reset_zeroes_counters_and_clears_connected():
    sg.bump_all()
    sg.set_connected(True)
    sg.reset()
    assert sg.token() == (0, 0, 0) and sg.connected() is False


def test_set_connected_logs_each_transition_once(caplog):
    caplog.set_level(logging.INFO, logger=sg.log.name)
    sg.set_connected(True)
    sg.set_connected(True)
    sg.set_connected(False)
    sg.set_connected(False)
    lines = [r.getMessage() for r in caplog.records if r.name == sg.log.name]
    assert len(lines) == 2
    assert "connected" in lines[0] and "bypassed" in lines[1]


def test_concurrent_bumps_are_not_lost():
    def worker():
        for _ in range(500):
            sg.bump("trades")
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sg.generation("trades") == 4000


def test_the_module_is_a_leaf():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {name for name in imported if name.startswith(("swingbot", "flask"))}
```

- [ ] **Step 2: Write the failing config tests**

Create `tests/test_config_v218_keys.py`:

```python
"""v218 V218-2: the ADMIN_STORE_SNAPSHOT switch and the settings generation (index Handoff 3)."""
import pathlib

from swingbot import config
from swingbot.core.infra import store_generation

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "ADMIN_STORE_SNAPSHOT"


def _field():
    return next(f for f in config.FIELDS if f.attr == ATTR)


def test_is_a_hot_reloadable_admin_ui_on_off_select():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Admin UI", "select", "on")
    assert field.options == ["on", "off"]
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert field.help.startswith("v218. ")


def test_sits_right_after_the_slow_request_threshold():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("ADMIN_SLOW_REQUEST_MS") + 1


def test_default_is_on_and_off_is_accepted_in_any_case():
    assert config._cast(_field(), _field().default) == "on"
    assert config._cast(_field(), "OFF") == "off"
    assert config._cast(_field(), "on") == "on"


def test_an_invalid_value_falls_back_to_on():
    assert config._cast(_field(), "maybe") == "on"


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}=on\n" in text


def test_reload_bumps_the_settings_generation_only_when_a_value_changed(monkeypatch):
    store_generation.reset()
    monkeypatch.setattr(config, "_load_dotenv_file", lambda: (True, True))
    monkeypatch.setattr(config, "_ENV_MTIME", config._ENV_MTIME)    # restored after reload()
    monkeypatch.setattr(config, "_apply_env", lambda: {})
    config.reload()
    assert store_generation.generation("settings") == 0
    monkeypatch.setattr(config, "_apply_env", lambda: {"LOGS_REFRESH_SECONDS": (10, 11)})
    config.reload()
    assert store_generation.generation("settings") == 1
    store_generation.reset()


def test_an_unchanged_env_file_does_not_bump(monkeypatch):
    store_generation.reset()
    monkeypatch.setattr(config, "_ENV_MTIME", config._env_signature())
    monkeypatch.setattr(config, "reload", lambda: (_ for _ in ()).throw(AssertionError("no reload")))
    assert config.auto_reload_if_changed() == {}
    assert store_generation.generation("settings") == 0
```

- [ ] **Step 3: Run both to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_store_generation.py` and `python scripts/dev/testrun.py file tests/test_config_v218_keys.py`
Expected: FAIL. The first fails with `ImportError: cannot import name 'store_generation'`; the second fails at collection on the same import.

- [ ] **Step 4: Create the leaf module**

Create `swingbot/core/infra/store_generation.py`:

```python
"""Process-wide change generations for the admin's store snapshot (v218, v205 L2-b).

A leaf module: it imports nothing from ``swingbot`` (or flask), so ``config``
and core stores can import it without a cycle.

Three counters, one per concern whose change must invalidate the admin's
cross-request snapshot and its ETags:

* ``trades``   -- bumped by the snapshot listener on every ``trades`` NOTIFY
  (the trades, plans and starred_plans triggers fire that channel);
* ``journal``  -- bumped on every ``journal`` NOTIFY (journal_entries);
* ``settings`` -- bumped by ``config.reload()`` whenever a value changed.

``connected`` says whether the snapshot listener is LISTENing right now. While
it is False no NOTIFY can bump a counter, so the snapshot is bypassed
(``store_snapshot.enabled()``). It starts False: nothing is served from the
snapshot until the listener has connected once.

The admin runs one gunicorn worker with 16 threads; a lock guards the counters.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

CONCERNS: tuple[str, ...] = ("trades", "journal", "settings")

_lock = threading.Lock()
_counts: dict[str, int] = dict.fromkeys(CONCERNS, 0)
_connected = False


def bump(concern: str) -> int:
    """Advance one concern; return its new value. ``KeyError`` for an unknown concern."""
    with _lock:
        if concern not in _counts:
            _unknown(concern)
        _counts[concern] += 1
        return _counts[concern]


def _unknown(concern: str) -> int:
    raise KeyError(f"unknown store generation concern {concern!r}; expected one of {CONCERNS}")


def bump_all() -> None:
    """Advance every concern: after a (re)connect, missed NOTIFYs are unknowable."""
    with _lock:
        for concern in CONCERNS:
            _counts[concern] += 1


def generation(concern: str) -> int:
    with _lock:
        if concern not in _counts:
            _unknown(concern)
        return _counts[concern]


def token() -> tuple[int, int, int]:
    """Every generation, in ``CONCERNS`` order."""
    with _lock:
        return tuple(_counts[concern] for concern in CONCERNS)


def set_connected(flag: bool) -> None:
    """Record the listener's state; log only when it changes (no per-request noise)."""
    global _connected
    flag = bool(flag)
    with _lock:
        changed, _connected = _connected != flag, flag
    if not changed:
        return
    if flag:
        log.info("store snapshot listener connected; the admin snapshot may serve reads")
    else:
        log.warning("store snapshot listener disconnected; the admin snapshot is bypassed")


def connected() -> bool:
    return _connected


def reset() -> None:
    """Test seam: every counter back to 0, ``connected`` False."""
    global _connected
    with _lock:
        for concern in CONCERNS:
            _counts[concern] = 0
        _connected = False
```

- [ ] **Step 5: Add the Field, its mode values and the reload bump**

In `swingbot/config.py`, directly after the `ADMIN_SLOW_REQUEST_MS` Field (the entry ending `"on the next request, no restart."),` near :1048), add:

```python
    Field("ADMIN_STORE_SNAPSHOT", "ADMIN_STORE_SNAPSHOT", "Admin UI", "Admin store snapshot",
          type="select", default="on", options=["on", "off"],
          help="v218. 'on' = the admin keeps trades, plans and journal notes in memory between "
               "requests, invalidated by database notifications, and sends ETags on the closed "
               "Trades view. 'off' = every request reads the database, exactly as before v218. "
               "Read on every request: a saved .env applies on the next request, no restart."),
```

In `_MODE_VALUES` (:1651), add one line after `"ADMIN_REFRESHER": ("on", "off"),`:

```python
    "ADMIN_STORE_SNAPSHOT": ("on", "off"),
```

In `_MODE_FALLBACK` (:1669), add the key so a typo lands on the default rather than on `"off"`:

```python
_MODE_FALLBACK = {"CONFLUENCE_ATR_TARGET_MODE": "rechoose", "FVG_LEVELS_MODE": "all", "TRAINING_DATA_SOURCE": "alpaca",
                  "ADMIN_STORE_SNAPSHOT": "on"}
```

In `reload()` (:1828), bump the settings generation when something changed. The `changed = _apply_env()` line and the first line of its `if changed:` block become:

```python
    changed = _apply_env()
    if changed:
        # v218: the admin's snapshot and ETags key on this; the admin reloads by
        # .env mtime per request (admin/app.py), never by SIGHUP.
        from swingbot.core.infra import store_generation
        store_generation.bump("settings")
        log.info("Config reloaded from %s -- %d value(s) changed:", ENV_PATH, len(changed))
```

The rest of `reload()` stays as it is. Its complexity stays 9 (the bump adds no branch).

- [ ] **Step 6: Add the key to `.env.example`**

After the line `ADMIN_SLOW_REQUEST_MS=2000` (549), add:

```
# v218: 'off' turns off the admin's in-memory store snapshot and its ETags (rollback switch).
ADMIN_STORE_SNAPSHOT=on
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_store_generation.py`, `python scripts/dev/testrun.py file tests/test_config_v218_keys.py`, `python scripts/dev/testrun.py file tests/test_config_v205_keys.py` and `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS for all four.

Then run `python scripts/dev/complexity_gate.py`. Expected: no new violation.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/infra/store_generation.py tests/admin_perf/test_store_generation.py
git commit -m "feat(infra): process-wide store generations and the snapshot listener's connected flag"
git add swingbot/config.py .env.example tests/test_config_v218_keys.py
git commit -m "feat(config): ADMIN_STORE_SNAPSHOT switch; reload() bumps the settings generation"
```


# Phase 2 — the listener and the snapshot

### Task V218-3: Always-on snapshot listener, independent of the SSE broker

**Model:** sonnet — a subclass of an existing listener with three overridden hooks and a lazy singleton; the threading pattern is copied from the reconnect tests.

**Files:**
- Modify: `swingbot/admin/events/db_listener.py` (`__init__` :47-67, `_run` :112-124, `_on_listening` :126-136; new `connected` property and `_on_disconnected` hook)
- Create: `swingbot/admin/events/snapshot_listener.py`
- Modify: `swingbot/admin/app.py` (top imports :50-54; after `request_timing.install(app)` :293)
- Create: `tests/admin/test_snapshot_listener.py` (suite `admin-core`, glob `tests/admin/test_[b-z]*.py`)
- Modify: `tests/admin/test_no_double_watcher.py`

**Interfaces:**
- Consumes (V218-2): `store_generation.bump(concern)`, `bump_all()`, `set_connected(flag)`, `connected()`, `token()`, `reset()`; `config.ADMIN_STORE_SNAPSHOT`.
- Produces (final names; V218-4 reads `store_generation.connected()`, which this listener drives; V218-5 relies on the admin app calling `install`):
  - `DbEventListener.connected -> bool` (property; True between `_on_listening` and the next lost connection or `stop()`)
  - `DbEventListener._on_disconnected(self) -> None` (no-op hook, called each time a LISTEN connection is lost or the thread ends)
  - `snapshot_listener.SNAPSHOT_CHANNELS = ("trades", "journal")`
  - `class SnapshotListener(DbEventListener)`: `__init__(self, **kwargs)` forwards every `DbEventListener` keyword except `emit` and `channels`
  - `snapshot_listener.ensure_started(*, factory: Callable[[], SnapshotListener] | None = None) -> SnapshotListener | None`
  - `snapshot_listener.stop() -> None`
  - `snapshot_listener.install(app) -> None`

**Background.** `DbEventListener` runs only while an SSE tab is open: `EventBroker.subscribe()` starts it on the first subscriber and `_release()` stops it on the last (`swingbot/admin/events/broker.py:253-305`). The snapshot gets its own listener (index Handoff 1), on channels `trades` (the `trades`, `plans` and `starred_plans` triggers) and `journal` (`journal_entries`). `on_notification` fires once per NOTIFY *before* the debounce, so the generation bump goes there; the debounced `emit` is a no-op for this listener. A NOTIFY sent while the connection is down is lost, so a (re)connect bumps every generation, and a lost connection clears `connected` so `store_snapshot` (V218-4) bypasses the snapshot during the backoff wait. Gunicorn runs `preload_app = False` with one worker (`deploy/gunicorn.conf.py`), so the thread is started lazily from the first request, inside the worker. Tests never start it through `install`: the admin test app sets `TESTING=True` (`tests/admin/conftest.py:132`).

- [ ] **Step 1: Write the failing listener tests**

Create `tests/admin/test_snapshot_listener.py`:

```python
"""v218 V218-3: the snapshot's own LISTEN connection drives the store generations
(v205 L2-b; index Handoff 1). It runs whether or not an SSE tab is open."""
import threading

import pytest
from flask import Flask

from swingbot import config
from swingbot.admin.events import snapshot_listener as sl
from swingbot.admin.events.db_listener import DbEventListener
from swingbot.core.infra import store_generation as sg
from tests.admin.test_db_listener_reconnect import _scripted_listen, _wait_for


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _clean():
    sl.stop()
    sg.reset()
    yield
    sl.stop()
    sg.reset()


def test_the_base_listener_reports_connected_and_calls_the_disconnect_hook():
    downs = []

    class Recording(DbEventListener):
        def _on_disconnected(self):
            downs.append(self.connected)

    listen, calls = _scripted_listen(["drop", "ok"])
    listener = Recording(lambda _e: None, listen=listen, backoff=(0.01, 0.05))
    assert listener.connected is False
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "ok"] and listener.connected)
    listener.stop()
    assert listener.connected is False
    assert downs == [False, False]          # the drop, then stop(); each already marked down


def test_a_notification_bumps_its_generation_before_the_debounce():
    listener = sl.SnapshotListener(clock=FakeClock())
    listener.on_notification("trades")
    assert sg.token() == (1, 0, 0)          # no flush yet
    listener.on_notification("journal")
    listener.on_notification("journal")
    assert sg.token() == (1, 2, 0)


def test_a_channel_outside_the_snapshot_is_ignored():
    listener = sl.SnapshotListener(clock=FakeClock())
    listener.on_notification("account")
    listener.on_notification("settings")    # the settings concern moves only on config.reload()
    assert sg.token() == (0, 0, 0)


def test_the_debounced_emit_is_a_no_op():
    clock = FakeClock()
    listener = sl.SnapshotListener(clock=clock)
    listener.on_notification("trades")
    clock.now = 10.0
    assert listener.flush() == ["trades"]


def test_listens_on_trades_and_journal_only():
    assert sl.SNAPSHOT_CHANNELS == ("trades", "journal")
    assert sl.SnapshotListener()._channels == sl.SNAPSHOT_CHANNELS


def test_connect_bumps_everything_and_a_drop_bypasses_until_the_reconnect():
    listen, calls = _scripted_listen(["drop", "fail", "ok"])
    listener = sl.SnapshotListener(listen=listen, backoff=(0.01, 0.05))
    listener.start()
    assert _wait_for(lambda: calls == ["drop", "fail", "ok"] and sg.connected())
    assert sg.token() == (2, 2, 2)          # one bump_all per successful LISTEN
    listener.stop()
    assert sg.connected() is False


def test_ensure_started_is_one_singleton_until_stop():
    built = []

    def factory():
        listen, _calls = _scripted_listen([])
        built.append(sl.SnapshotListener(listen=listen, backoff=(0.01, 0.05)))
        return built[-1]

    first = sl.ensure_started(factory=factory)
    assert sl.ensure_started(factory=factory) is first
    assert built == [first]
    assert _wait_for(sg.connected)
    sl.stop()
    assert sg.connected() is False
    assert sl.ensure_started(factory=factory) is not first
    assert len(built) == 2


def test_concurrent_first_requests_start_one_listener():
    built = []
    gate = threading.Barrier(8)

    def factory():
        listen, _calls = _scripted_listen([])
        built.append(sl.SnapshotListener(listen=listen))
        return built[-1]

    def worker():
        gate.wait()
        sl.ensure_started(factory=factory)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(built) == 1


def test_a_failing_start_is_swallowed_and_retried_next_request():
    def factory():
        raise OSError("no database")

    assert sl.ensure_started(factory=factory) is None
    assert sl._listener is None


def _app(testing: bool) -> Flask:
    app = Flask(__name__)
    app.testing = testing
    app.add_url_rule("/x", "x", lambda: "ok")
    sl.install(app)
    return app


@pytest.mark.parametrize("testing, switch, expected", [
    (False, "on", 1), (True, "on", 0), (False, "off", 0)])
def test_install_starts_the_listener_on_a_real_request_only(monkeypatch, testing, switch, expected):
    started = []
    monkeypatch.setattr(sl, "ensure_started", lambda **_kw: started.append(1))
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", switch, raising=False)
    client = _app(testing).test_client()
    client.get("/x")
    assert len(started) == expected


def test_the_admin_app_installs_it(admin_app):
    assert sl._start_on_first_request in admin_app.before_request_funcs[None]
```

If `admin_app` (`tests/admin/conftest.py:62`) yields something other than the Flask app, read the app as `swingbot.admin.app.app` (attribute access after the fixture's reload, per that conftest's TRAP note) in the last test.

- [ ] **Step 2: Extend the one-watcher test**

In `tests/admin/test_no_double_watcher.py`, add two imports beside the existing ones:

```python
from swingbot.admin.events import snapshot_listener
from tests.admin.test_db_listener_reconnect import _scripted_listen
```

and append:

```python
def test_the_snapshot_listener_is_a_separate_singleton_the_broker_never_touches(
        monkeypatch, tmp_path, db_engine):
    """v218: the broker still owns exactly one watcher; the snapshot's listener is
    not it, and a broker subscribe/release neither starts nor stops it."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    listen, _calls = _scripted_listen([])
    snap = snapshot_listener.ensure_started(
        factory=lambda: snapshot_listener.SnapshotListener(listen=listen))
    try:
        broker = EventBroker()
        with broker.subscribe():
            assert broker._watcher is not snap
            assert not isinstance(broker._watcher, snapshot_listener.SnapshotListener)
        assert broker._watcher is None
        assert snapshot_listener.ensure_started() is snap
        assert snap._thread is not None
    finally:
        snapshot_listener.stop()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_snapshot_listener.py`
Expected: FAIL at collection with `ImportError: cannot import name 'snapshot_listener'`.

- [ ] **Step 4: Give `DbEventListener` a connected flag and a disconnect hook**

In `swingbot/admin/events/db_listener.py`, in `__init__` after `self._connected_before = False` (:62), add:

```python
        self._connected = False
```

Directly after `__init__`, add the property:

```python
    @property
    def connected(self) -> bool:
        """True while LISTEN is active: from ``_on_listening`` to the next lost
        connection or ``stop()``. Read by v218's snapshot listener."""
        return self._connected
```

Replace `_run` (:112-124) with:

```python
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen(self._channels, self._on_event, self._stop,
                             poll=self._debounce, dsn=self._dsn,
                             on_listening=self._on_listening)
                self._mark_down()
                return                      # stop() was called
            except Exception:
                self._mark_down()
                log.warning("event listener lost its database connection; "
                            "reconnecting in %.1fs", self._delay, exc_info=True)
            if self._stop.wait(self._delay):
                return
            self._delay = min(self._delay * 2, self._backoff[1])

    def _mark_down(self) -> None:
        self._connected = False
        try:
            self._on_disconnected()
        except Exception:
            log.exception("event listener disconnect hook failed")

    def _on_disconnected(self) -> None:
        """Hook: the LISTEN connection is gone (lost, never made, or stopped).
        A no-op here; v218's SnapshotListener bypasses the snapshot on it."""
```

In `_on_listening` (:126), add `self._connected = True` as its first line, before `self._delay = self._backoff[0]`. Nothing else in the class changes; the broker's listener behaves exactly as before.

- [ ] **Step 5: Create the snapshot listener**

Create `swingbot/admin/events/snapshot_listener.py`:

```python
"""The admin snapshot's own LISTEN connection (v218, v205 L2-b).

The SSE broker's DbEventListener runs only while a browser tab is subscribed
(broker.subscribe/_release), so it cannot vouch for a snapshot read by a cold
GET. This listener is a separate per-process singleton on channels ``trades``
(trades, plans, starred_plans triggers) and ``journal`` (journal_entries). It
emits nothing; each NOTIFY bumps that concern's generation in
``store_generation`` before the debounce. A (re)connect bumps every generation,
since NOTIFYs sent while the connection was down are gone, and a lost
connection clears ``store_generation.connected()`` so the snapshot is bypassed.

Started lazily on the admin's first non-testing request (gunicorn runs
``preload_app = False``, so the thread lives in the worker), never in tests
unless a test calls ``ensure_started`` with an injected ``listen=`` fake.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from flask import Flask, current_app

from swingbot import config
from swingbot.core.infra import store_generation
from swingbot.core.infra.swallowed import swallowed

from .db_listener import DbEventListener

log = logging.getLogger(__name__)

SNAPSHOT_CHANNELS: tuple[str, ...] = ("trades", "journal")

_lock = threading.Lock()
_listener: "SnapshotListener | None" = None


class SnapshotListener(DbEventListener):
    """Turn ``trades``/``journal`` NOTIFYs into store-generation bumps."""

    def __init__(self, **kwargs):
        super().__init__(lambda _name: None, channels=SNAPSHOT_CHANNELS, **kwargs)

    def on_notification(self, channel: str) -> None:
        super().on_notification(channel)
        if channel in SNAPSHOT_CHANNELS:
            store_generation.bump(channel)

    def _on_listening(self) -> None:
        super()._on_listening()
        store_generation.bump_all()          # before connected: no request sees the old token as valid
        store_generation.set_connected(True)

    def _on_disconnected(self) -> None:
        store_generation.set_connected(False)


def ensure_started(*, factory: Callable[[], SnapshotListener] | None = None) -> SnapshotListener | None:
    """The process's snapshot listener, built and started once; None if starting failed."""
    global _listener
    if _listener is not None:
        return _listener
    with _lock:
        if _listener is None:
            try:
                listener = (factory or SnapshotListener)()
                listener.start()
            except Exception as exc:
                swallowed(log, "ops.admin.snapshot_listener", exc)
                return None
            _listener = listener
        return _listener


def stop() -> None:
    """Stop and forget the singleton (tests, shutdown); the snapshot is bypassed after."""
    global _listener
    with _lock:
        listener, _listener = _listener, None
    if listener is not None:
        listener.stop()
    store_generation.set_connected(False)


def _start_on_first_request() -> None:
    if _listener is not None or current_app.testing:
        return
    if getattr(config, "ADMIN_STORE_SNAPSHOT", "on") == "off":
        return
    ensure_started()


def install(app: Flask) -> None:
    """Start the listener from ``app``'s first real request. Called once by app.py."""
    app.before_request(_start_on_first_request)
```

`swallowed`'s signature is `swallowed(log, tag, exc, msg="", *args, level=logging.WARNING, exc_info=False)` (`swingbot/core/infra/swallowed.py:62`); no test pins the set of tags.

- [ ] **Step 6: Install it in the admin app**

In `swingbot/admin/app.py`, add to the top imports after `from . import request_timing` (:54):

```python
from .events import snapshot_listener
```

`swingbot/admin/events/__init__.py` imports nothing and `db_listener` imports only `swingbot.core.db.notify`, so this adds no cycle. After `request_timing.install(app)` (:293), add:

```python
# v218: the admin snapshot's own LISTEN connection (trades, journal), started on
# the first non-testing request so its thread lives in the gunicorn worker.
snapshot_listener.install(app)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_snapshot_listener.py`, `python scripts/dev/testrun.py file tests/admin/test_db_listener.py`, `python scripts/dev/testrun.py file tests/admin/test_db_listener_reconnect.py` and `python scripts/dev/testrun.py file tests/admin/test_broker_db_listener.py`
Expected: PASS for all four.

`test_no_double_watcher.py` reaches Postgres: run `/replicate-prod-db` first if no sibling task this session did, then `python scripts/dev/testrun.py file tests/admin/test_no_double_watcher.py`. Expected: PASS (2 tests).

Then run `python scripts/dev/complexity_gate.py`. Expected: no new violation (`_run` stays under 5, `ensure_started` under 6).

- [ ] **Step 8: Commit**

```bash
git add swingbot/admin/events/db_listener.py swingbot/admin/events/snapshot_listener.py
git add tests/admin/test_snapshot_listener.py tests/admin/test_no_double_watcher.py
git commit -m "feat(admin): always-on snapshot listener bumps store generations on trades/journal NOTIFY"
git add swingbot/admin/app.py
git commit -m "feat(admin): start the snapshot listener on the first non-testing request"
```

### Task V218-4: Per-process raw-record snapshot with one rebuild under a lock

**Model:** opus — cross-request caching under 16 threads, where a wrong token order serves stale money; the validity rule must hold under concurrency.

**Files:**
- Create: `swingbot/core/infra/store_snapshot.py`
- Create: `tests/admin_perf/test_store_snapshot.py`

**Interfaces:**
- Consumes: `TradeRepository.version()`, `JournalRepository.version()` (V218-1), `PlanRepository.version()` (`swingbot/core/db/repositories/plans.py:44`), factories `plans_repo()`, `trades_repo()`, `journal_repo()` (`repositories/journal.py:46`); `store_generation.token()`, `connected()`, `reset()` (V218-2); `config.ADMIN_STORE_SNAPSHOT` (V218-2); `read_memo.TRADE_ROWS/TRADES/PLANS/NOTED_IDS`, `read_memo.active()`.
- Produces (final names; V218-5, V218-8 and V218-9 consume them):
  - `SNAPSHOT_KEYS: frozenset[str]` = `{read_memo.TRADE_ROWS, TRADES, PLANS, NOTED_IDS}`
  - `enabled() -> bool` (switch `on` and the listener connected)
  - `read(key: str, loader: Callable[[], T]) -> T` (the shared stored value; `read_memo` copies it for each caller)
  - `begin_request() -> None`, `end_request() -> None` (`end_request` is the part-header addition, called by V218-5 from `request_timing._teardown`)
  - `request_versions() -> tuple` (`(plans, trades, journal)` `version()` tuples, read once per request; per call outside a request)
  - `request_state() -> str` in `{"off", "miss", "hit"}`
  - `stored(key: str) -> object | None` (test seam, never loads)
  - `install() -> None` (= `read_memo.set_backing(read)`; `set_backing` is created by V218-5, which also tests `install`)
  - `reset() -> None` (test seam)

**Design.** The snapshot keeps the loaders' values, raw records only (index Global Constraints), per key, under one module lock. Its validity token is `(store_generation.token(), request_versions())`, so a NOTIFY (generation) or a committed change visible in `(count, max(updated_at))` (version) both invalidate it, and neither alone is trusted (V218-1's stamp gap). The token is read *before* the lock and before any load, so a stored value is always at least as fresh as the token it is filed under. A token unlike the stored one clears every key, and each key then reloads lazily under the lock, so concurrent readers wait for the one rebuild rather than each loading. A raising loader stores nothing and re-raises (as `read_memo._stored` does). A raising version query is swallowed (`ops.admin.snapshot`), and that request loads directly. `read` serves the snapshot only when all of these hold: the key is in `SNAPSHOT_KEYS`, `read_memo.active()`, `enabled()`, and the version query succeeded. Otherwise it returns `loader()` exactly as Layer 1 does.

`request_state()` (index planner note) reports, by precedence `off > miss > hit`: `off` when a read or version query was bypassed this request, or when nothing touched the snapshot at all (no read scope); `miss` when at least one key was rebuilt; `hit` otherwise, including a request (a V218-8 304) that only read the versions. Both per-request values sit in `ContextVar`s that `begin_request()` arms and `end_request()` disarms, because a gthread worker's thread keeps its context across requests.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin_perf/test_store_snapshot.py`:

```python
"""v218 V218-4: the admin's cross-request raw-record snapshot (v205 L2-a/L2-b)."""
import ast
import logging
import pathlib
import threading

import pytest

from swingbot import config
from swingbot.core.infra import read_memo, store_generation as sg, store_snapshot as ss

PLANS, TRADES = read_memo.PLANS, read_memo.TRADES


class Versions:
    """A fake ``_query_versions``: a mutable tuple and a call counter."""

    def __init__(self):
        self.value = ((2, "a"), (5, "b"), (1, "c"))
        self.calls = 0
        self.fail = False

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("database down")
        return self.value


@pytest.fixture
def versions(monkeypatch):
    fake = Versions()
    monkeypatch.setattr(ss, "_query_versions", fake)
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "on", raising=False)
    ss.reset()
    sg.reset()
    sg.set_connected(True)
    yield fake
    ss.end_request()
    ss.reset()
    sg.reset()


def _loader(calls, value):
    def load():
        calls.append(1)
        return value
    return load


def _request(key, loader):
    """One admin request: armed per-request state, one read scope, the state at the end."""
    ss.begin_request()
    try:
        with read_memo.scope():
            value = ss.read(key, loader)
        return value, ss.request_state()
    finally:
        ss.end_request()


def test_the_snapshot_keys_are_the_four_memo_keys():
    assert ss.SNAPSHOT_KEYS == frozenset({read_memo.TRADE_ROWS, TRADES, PLANS, read_memo.NOTED_IDS})


def test_a_second_request_is_a_hit_on_the_same_stored_value(versions):
    calls, value = [], {"p1": {"status": "ACTIVE"}}
    first, state1 = _request(PLANS, _loader(calls, value))
    second, state2 = _request(PLANS, _loader(calls, value))
    assert (state1, state2) == ("miss", "hit")
    assert calls == [1] and first is second is value
    assert ss.stored(PLANS) is value


@pytest.mark.parametrize("concern", sg.CONCERNS)
def test_any_generation_bump_clears_every_key(versions, concern):
    calls = []
    _request(PLANS, _loader(calls, {}))
    _request(TRADES, _loader(calls, []))
    sg.bump(concern)
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"
    assert ss.stored(TRADES) is None
    assert len(calls) == 3


def test_a_version_change_clears_the_snapshot_with_unchanged_generations(versions):
    calls = []
    _request(PLANS, _loader(calls, {}))
    versions.value = ((3, "a2"), (5, "b"), (1, "c"))
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"
    assert len(calls) == 2


def test_versions_are_read_once_per_request(versions):
    ss.begin_request()
    with read_memo.scope():
        for key in ss.SNAPSHOT_KEYS:
            ss.read(key, lambda: [])
    ss.end_request()
    assert versions.calls == 1
    _request(PLANS, lambda: {})
    assert versions.calls == 2


def test_outside_a_request_versions_are_read_per_call(versions):
    ss.request_versions()
    ss.request_versions()
    assert versions.calls == 2


@pytest.mark.parametrize("switch, connected", [("off", True), ("on", False)])
def test_switch_off_or_listener_down_loads_directly(versions, monkeypatch, switch, connected):
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", switch)
    sg.set_connected(connected)
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "off"
    _request(PLANS, _loader(calls, {}))
    assert len(calls) == 2 and ss.stored(PLANS) is None
    assert versions.calls == 0 and ss.enabled() is False


def test_outside_a_read_scope_or_for_another_key_it_is_the_loader(versions):
    calls = []
    ss.read(PLANS, _loader(calls, {}))                      # no read_memo.scope()
    with read_memo.scope():
        ss.read("watchlist", _loader(calls, []))
    assert len(calls) == 2 and ss.stored(PLANS) is None and versions.calls == 0


def test_a_failing_version_query_loads_directly_and_is_logged(versions, caplog):
    caplog.set_level(logging.WARNING)
    versions.fail = True
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "off"
    assert calls == [1] and ss.stored(PLANS) is None
    assert any("admin snapshot bypassed" in r.getMessage() for r in caplog.records)


def test_a_raising_loader_stores_nothing_and_re_raises(versions):
    def boom():
        raise RuntimeError("loader failed")

    with pytest.raises(RuntimeError, match="loader failed"):
        _request(PLANS, boom)
    assert ss.stored(PLANS) is None
    calls = []
    assert _request(PLANS, _loader(calls, {}))[1] == "miss"


def test_concurrent_readers_wait_for_one_rebuild(versions):
    started, release, calls, results = threading.Event(), threading.Event(), [], []
    value = {"p1": {}}

    def slow():
        calls.append(1)
        started.set()
        release.wait(2)
        return value

    def worker():
        with read_memo.scope():                             # each thread its own context
            results.append(ss.read(PLANS, slow))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    assert started.wait(2)
    release.set()
    for thread in threads:
        thread.join()
    assert calls == [1]
    assert len(results) == 6 and all(result is value for result in results)


def test_state_precedence_within_one_request(versions):
    _request(PLANS, lambda: {})                             # PLANS now stored
    ss.begin_request()
    with read_memo.scope():
        ss.read(PLANS, lambda: {})                          # hit
        ss.read(TRADES, lambda: [])                         # miss
    assert ss.request_state() == "miss"
    ss.end_request()


def test_a_request_that_reads_only_the_versions_is_a_hit(versions):
    ss.begin_request()
    ss.request_versions()                                   # what V218-8's 304 path does
    assert ss.request_state() == "hit"
    ss.end_request()


def test_a_request_that_touches_nothing_is_off(versions):
    ss.begin_request()
    assert ss.request_state() == "off"
    ss.end_request()


def test_end_request_drops_the_cached_versions(versions):
    ss.begin_request()
    ss.request_versions()
    ss.end_request()
    ss.request_versions()
    assert versions.calls == 2


def test_reset_drops_every_stored_value(versions):
    _request(PLANS, lambda: {"p": {}})
    ss.reset()
    assert ss.stored(PLANS) is None


def test_the_module_imports_no_flask_or_admin_code():
    tree = ast.parse(pathlib.Path(ss.__file__).read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {name for name in names if name.startswith(("flask", "swingbot.admin"))}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_store_snapshot.py`
Expected: FAIL at collection with `ImportError: cannot import name 'store_snapshot'`.

- [ ] **Step 3: Write the snapshot module**

Create `swingbot/core/infra/store_snapshot.py`:

```python
"""The admin's per-process raw-record snapshot (v218, v205 L2-a/L2-b).

``read_memo`` (L1-c) loads each store once per request. This module keeps the
same loaders' values *between* requests, for ``SNAPSHOT_KEYS`` only, and hands
``read_memo`` the stored value; ``read_memo`` still gives every caller shallow
copies. Raw records only: anything derived from the clock (days held, open
P&L, today) is computed per request by the callers, as before.

Validity: the token ``(store_generation.token(), request_versions())``. The
generations move on every ``trades``/``journal`` NOTIFY, on a listener
(re)connect and on a settings reload; the versions are the plans, trades and
journal ``(count, max(updated_at))``. Neither alone is trusted (V218-1: a
transaction can commit under an older stamp). The token is read before the
lock and before any load, so a value is never filed under a newer token than
the data it was loaded from.

Served only when the key is a snapshot key, a read scope is open, the switch
``ADMIN_STORE_SNAPSHOT`` is ``on``, the snapshot listener is connected and the
version query succeeded; otherwise ``read`` is ``loader()``, Layer 1 exactly.

Installed by the admin app only (``install()`` -> ``read_memo.set_backing``);
the bot and the refresher never import it. One gunicorn worker, 16 threads:
one lock, and one rebuild at a time.
"""
from __future__ import annotations

import contextvars
import logging
import threading
from typing import Callable, TypeVar

from swingbot import config
from swingbot.core.infra import read_memo, store_generation
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

T = TypeVar("T")

SNAPSHOT_KEYS: frozenset[str] = frozenset(
    {read_memo.TRADE_ROWS, read_memo.TRADES, read_memo.PLANS, read_memo.NOTED_IDS})

_TAG = "ops.admin.snapshot"
_OUTSIDE = object()                      # no request armed: versions are read per call
_RANK = {"hit": 0, "miss": 1, "off": 2}  # request_state precedence

_lock = threading.Lock()
_token: tuple | None = None
_values: dict[str, object] = {}

_VERSIONS: contextvars.ContextVar[object] = contextvars.ContextVar(
    "v218_snapshot_versions", default=_OUTSIDE)
_STATE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "v218_snapshot_state", default=None)


def enabled() -> bool:
    """The switch is on and the snapshot listener is LISTENing."""
    return getattr(config, "ADMIN_STORE_SNAPSHOT", "on") == "on" and store_generation.connected()


def _query_versions() -> tuple:
    from swingbot.core.db.repositories.journal import journal_repo
    from swingbot.core.db.repositories.plans import plans_repo
    from swingbot.core.db.repositories.trades import trades_repo
    return (plans_repo().version(), trades_repo().version(), journal_repo().version())


def _note(state: str) -> None:
    current = _STATE.get()
    if current is None or _RANK[state] > _RANK[current]:
        _STATE.set(state)


def begin_request() -> None:
    """Arm this request's version cache and state (request_timing._begin)."""
    _VERSIONS.set(None)
    _STATE.set(None)


def end_request() -> None:
    """Disarm them (request_timing._teardown): the thread outlives the request."""
    _VERSIONS.set(_OUTSIDE)
    _STATE.set(None)


def request_versions() -> tuple:
    """The plans, trades and journal versions: once per armed request, else per call."""
    cached = _VERSIONS.get()
    if cached is not None and cached is not _OUTSIDE:
        return cached
    try:
        versions = _query_versions()
    except Exception:
        _note("off")
        raise
    if cached is None:
        _VERSIONS.set(versions)
        _note("hit")
    return versions


def request_state() -> str:
    """off | miss | hit for the current request (Server-Timing ``snap;desc``)."""
    return _STATE.get() or "off"


def read(key: str, loader: Callable[[], T]) -> T:
    """The stored value for ``key`` when the snapshot can vouch for it, else ``loader()``."""
    if key not in SNAPSHOT_KEYS or not read_memo.active():
        return loader()
    if not enabled():
        _note("off")
        return loader()
    try:
        token = (store_generation.token(), request_versions())
    except Exception as exc:
        swallowed(log, _TAG, exc, "admin snapshot bypassed: version query failed")
        _note("off")
        return loader()
    return _read_valid(key, loader, token)


def _read_valid(key: str, loader: Callable[[], T], token: tuple) -> T:
    global _token
    with _lock:
        if _token != token:
            _values.clear()
            _token = token
        if key in _values:
            _note("hit")
            return _values[key]
        value = loader()                 # a raising loader stores nothing and re-raises
        _values[key] = value
        _note("miss")
        return value


def stored(key: str) -> object | None:
    """Test seam: the stored value for ``key``, or None (never loads)."""
    with _lock:
        return _values.get(key)


def install() -> None:
    """Make ``read_memo`` read through the snapshot. Called once by the admin app."""
    read_memo.set_backing(read)


def reset() -> None:
    """Test seam: drop every stored value and this context's request state."""
    global _token
    with _lock:
        _values.clear()
        _token = None
    end_request()
```

`read_memo` stays a leaf: this module imports `read_memo`, never the reverse. `read_memo.set_backing` does not exist until V218-5. `install()` is never called in this task, so the module imports cleanly.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_store_snapshot.py`
Expected: PASS.

Then run `python scripts/dev/complexity_gate.py`. Expected: no new violation (`read` is 5, `_read_valid` 3, `request_versions` 5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/infra/store_snapshot.py tests/admin_perf/test_store_snapshot.py
git commit -m "feat(infra): per-process raw-record store snapshot keyed on generations and versions"
```

