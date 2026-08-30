# v67 — Part 4: Settings (tasks P4-01…P4-07)

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** Part 1 must be merged to
> `main` before this part begins. Tasks P4-08…P4-14 are in
> `2026-08-29-v67-json-to-postgres_4b-settings-admin.md`.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`
(section 4).

`swingbot/config.py` already carries the split this part needs. `FIELDS`
(`config.py:95`) is a declarative registry where each `Field` (`config.py:73`)
knows whether it is `sensitive` and whether it is `hot_reloadable`, and
`reload()` (`config.py:909`) updates module globals **in place** — so
`config.XXX` readers everywhere see new values without re-importing.

The change is therefore confined to **where `reload()` sources values**:

- `sensitive=True` fields resolve from `.env` only, unchanged.
- Every other field resolves **DB → `.env` → `Field.default`**.

Side effect worth having: pushing a settings change no longer needs the Docker
socket mounted into the admin container.

## Alembic revision ids

Part 4 owns `p4_*`, hanging off `p1_003` — **not** off Parts 2 or 3, which run
concurrently with this one. Two heads across parts is expected and Part 6's
merge revision resolves it.

| Revision | Content |
|---|---|
| `p4_001` | `settings` table + its NOTIFY trigger |

## Parallelisation

- **Sequential: P4-01 before everything** — it introduces the table and the
  repository every later task consumes.
- **Sequential: P4-02 before P4-03** (resolution before reload) **and P4-03
  before P4-05** (the admin page writes what `reload()` must then read).
- **Group 4a (parallel):** P4-06 and P4-07 — `_build_env_text`/`_write_env_text`
  and the export/import pair. Both live in `admin/helpers.py`, so they are
  **sequential with each other** despite being independent in subject. Named
  here so nobody re-derives it.
- **Sequential: the whole of `_4b` after `_4a`.** The listener, the SIGHUP
  path and the import-time-capture audit all assume DB resolution is live.

## Part 4 exit criteria

1. Every non-sensitive `FIELDS` entry resolves DB → `.env` → default.
2. No sensitive value is ever read from, or written to, the database.
3. The admin settings page writes rows; `.env` is rewritten only for secrets.
4. A settings change reaches the bot without SIGHUP and without the Docker
   socket.
5. `python scripts/dev/testrun.py fast` is green.
6. `DB_STORES` is empty in every committed file.

---

# Phase 4 — Settings

### Task P4-01: The settings table and repository

**Files:**
- Modify: `swingbot/core/db/schema.py`
- Modify: `swingbot/core/db/events.py` (map `settings` → the `settings` channel)
- Create: `swingbot/core/db/repositories/settings.py`
- Create: `swingbot/core/db/migrations/versions/p4_001_settings.py`
- Modify: `tests/db/conftest.py`
- Test: `tests/db/test_settings_repository.py`

**Interfaces:**
- Consumes: `register`, `standard_columns` (P1-04); `Repository` (P1-09);
  `trigger_ddl` (P1-12).
- Produces:
  - table `settings` — `key TEXT UNIQUE`, `value JSONB`, `updated_by TEXT`
  - `SettingsRepository` with `all_settings() -> dict[str, Any]`,
    `get_value(key)`, `put(key, value, updated_by)`, `put_many(mapping, updated_by)`,
    `remove(key)`; `settings_repo()`
  - `SENTINEL_MISSING` — the object `get_value` returns for an absent key, so
    a stored `None` is distinguishable from "not set"

**Why `value` is JSONB and not TEXT:** `Field.type` already spans `text`,
`number`, `float`, `checkbox` and `select`, and `_cast` turns a string into the
right Python type. Storing JSON means a stored `4` comes back as `4`, not
`"4"` — and `_cast` still runs on top, so a value hand-edited in `psql` as a
string is coerced exactly as an `.env` value would be.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_settings_repository.py`:

```python
"""Settings as rows. Typed values, not stringly-typed ones."""
import pytest

from swingbot.core.db.repositories.settings import (
    SENTINEL_MISSING,
    SettingsRepository,
)


@pytest.fixture
def repo():
    return SettingsRepository()


def test_an_empty_store_reads_as_an_empty_mapping(repo, db_conn):
    assert repo.all_settings(conn=db_conn) == {}


def test_put_then_get(repo, db_conn):
    repo.put("MIN_ALERT_CONFIDENCE_LEVEL", 4, updated_by="admin", conn=db_conn)
    assert repo.get_value("MIN_ALERT_CONFIDENCE_LEVEL", conn=db_conn) == 4


def test_types_survive_the_round_trip(repo, db_conn):
    repo.put("AN_INT", 4, updated_by="admin", conn=db_conn)
    repo.put("A_FLOAT", 1.5, updated_by="admin", conn=db_conn)
    repo.put("A_BOOL", True, updated_by="admin", conn=db_conn)
    repo.put("A_STR", "hello", updated_by="admin", conn=db_conn)
    got = repo.all_settings(conn=db_conn)
    assert got["AN_INT"] == 4 and isinstance(got["AN_INT"], int)
    assert got["A_FLOAT"] == 1.5
    assert got["A_BOOL"] is True
    assert got["A_STR"] == "hello"


def test_a_stored_none_is_distinguishable_from_absent(repo, db_conn):
    repo.put("EXPLICIT_NULL", None, updated_by="admin", conn=db_conn)
    assert repo.get_value("EXPLICIT_NULL", conn=db_conn) is None
    assert repo.get_value("NEVER_SET", conn=db_conn) is SENTINEL_MISSING


def test_put_twice_keeps_one_row(repo, db_conn):
    repo.put("K", 1, updated_by="admin", conn=db_conn)
    repo.put("K", 2, updated_by="admin", conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.get_value("K", conn=db_conn) == 2


def test_updated_by_is_recorded(repo, db_conn):
    repo.put("K", 1, updated_by="someone", conn=db_conn)
    row = repo.get("K", conn=db_conn)
    assert row["updated_by"] == "someone"


def test_put_many_is_one_write_per_key(repo, db_conn):
    repo.put_many({"A": 1, "B": 2}, updated_by="admin", conn=db_conn)
    assert repo.all_settings(conn=db_conn) == {"A": 1, "B": 2}


def test_remove_deletes_the_row(repo, db_conn):
    repo.put("K", 1, updated_by="admin", conn=db_conn)
    assert repo.remove("K", conn=db_conn) is True
    assert repo.get_value("K", conn=db_conn) is SENTINEL_MISSING


def test_removing_an_absent_key_reports_false(repo, db_conn):
    assert repo.remove("NOPE", conn=db_conn) is False


def test_the_settings_table_maps_to_the_settings_channel():
    from swingbot.core.db.events import TABLE_CHANNELS
    assert TABLE_CHANNELS["settings"] == "settings"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_settings_repository.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.settings'`.

- [ ] **Step 3: Declare the table**

Append to `swingbot/core/db/schema.py`:

```python
# Non-sensitive configuration. Sensitive fields never reach this table -- see
# the guard in config.py's DB resolution and the test that asserts it.
settings = register(
    sa.Table(
        "settings", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("key", sa.Text, nullable=False, unique=True),
        # JSONB rather than TEXT so a stored 4 comes back as 4. config._cast
        # still runs on top, so a value hand-edited in psql as a string is
        # coerced exactly as an .env value would be.
        sa.Column("value", JSONB),
        sa.Column("updated_by", sa.Text),
        *standard_columns(),
    ),
    ("key", "value", "updated_by"),
)
```

Add to `swingbot/core/db/events.py`'s `TABLE_CHANNELS`:

```python
    "settings": "settings",
```

- [ ] **Step 4: Write the repository**

Create `swingbot/core/db/repositories/settings.py`:

```python
"""Non-sensitive configuration, one row per key.

Sensitive fields stay in .env and never appear here. That is enforced at the
write path in config.py and in the admin save handler, and asserted by a test
in P4-02 -- not by anything this module does, because a repository that
silently dropped keys would be worse than one that stores what it is given.
"""
from __future__ import annotations

from typing import Any

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import settings


class _Missing:
    """Distinct from None, which is a legitimate stored value."""

    def __repr__(self) -> str:          # pragma: no cover -- debugging aid
        return "<missing>"

    def __bool__(self) -> bool:
        return False


SENTINEL_MISSING = _Missing()


class SettingsRepository(Repository):
    def __init__(self):
        super().__init__(settings, key="key")

    def all_settings(self, *, conn=None) -> dict[str, Any]:
        return {row["key"]: row.get("value") for row in self.list_all(conn=conn)}

    def get_value(self, key: str, *, conn=None) -> Any:
        row = self.get(key, conn=conn)
        if row is None:
            return SENTINEL_MISSING
        # `value` is a promoted column, so codec.merge_doc omits it when NULL.
        # An absent `value` on a present row therefore means a stored null.
        return row.get("value")

    def put(self, key: str, value: Any, *, updated_by: str, conn=None) -> dict:
        return self.upsert({"key": key, "value": value,
                            "updated_by": updated_by}, conn=conn)

    def put_many(self, mapping: dict[str, Any], *, updated_by: str,
                 conn=None) -> None:
        from swingbot.core.db.engine import transaction
        # One transaction: a settings save is atomic, so the bot's listener
        # never wakes on a half-applied change.
        with transaction(conn) as c:
            for key, value in mapping.items():
                self.put(key, value, updated_by=updated_by, conn=c)

    def remove(self, key: str, *, conn=None) -> bool:
        return self.delete(key, conn=conn)


_repo: SettingsRepository | None = None


def settings_repo() -> SettingsRepository:
    global _repo
    if _repo is None:
        _repo = SettingsRepository()
    return _repo
```

**Note the `get_value` subtlety the test pins:** `value` is promoted, and
`codec.merge_doc` omits a NULL promoted column. So a row storing `null` comes
back as a row with no `value` key, and `row.get("value")` returns `None` —
which is the correct answer. An absent *row* returns `SENTINEL_MISSING`. Those
are the two cases, and `.get()` on the row distinguishes them only because the
row's existence was already checked above.

- [ ] **Step 5: Write the migration and extend the harness**

Create `swingbot/core/db/migrations/versions/p4_001_settings.py` on `p2_001`'s
shape: `down_revision = "p1_003"`, an explicit `op.create_table`, and
`op.execute(trigger_ddl("settings", "settings"))`.

Add `("settings", "settings")` to the trigger loop in `tests/db/conftest.py`.

- [ ] **Step 6: Migrate and run**

```bash
alembic upgrade head
alembic downgrade p1_003 && alembic upgrade head
python scripts/dev/testrun.py file tests/db/test_settings_repository.py
python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
```

Expected: `0 failed`. `test_trigger_coverage.py` is Part 3's; if that part has
not landed, skip it.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/events.py \
        swingbot/core/db/repositories/settings.py \
        swingbot/core/db/migrations/versions/p4_001_settings.py \
        tests/db/conftest.py tests/db/test_settings_repository.py
git commit -m "feat(v67): add the settings table and repository"
```

---

### Task P4-02: DB → .env → default resolution

The one change that matters in this part. `_apply_env()` (`config.py:848`)
reads every `FIELDS` entry from `os.environ` and sets the module global. It
gains one source above that, for non-sensitive fields only.

**Files:**
- Modify: `swingbot/config.py` (`_apply_env` `:848`)
- Test: `tests/test_config_db_resolution.py`

**Interfaces:**
- Consumes: `settings_repo` (P4-01), `stages`.
- Produces on `swingbot.config`:
  - `_db_settings() -> dict[str, Any]` — the DB layer, `{}` when the stage is
    not `db`/`dual` or the database is unreachable
  - `_resolve(field: Field, db: dict) -> str` — the three-source lookup,
    returning a raw string for `_cast` exactly as `os.getenv` did

**The rule this task enforces, and the test that proves it:** a `sensitive`
field is resolved from `.env` only. Not "preferentially from .env" — the DB is
not consulted for it at all, and a row that somehow exists for a sensitive key
is ignored rather than used.

**Why `_db_settings()` degrades instead of raising.** This is the third
documented exception to the fail-fast rule, alongside the heartbeat and the
regenerable caches, and its reasoning is specific: `_apply_env()` runs at
**module import time** (`config.py:901`). A raise there makes `import swingbot.config`
fail, which makes every entry point fail, including the admin UI someone would
use to fix the connection string. Falling back to `.env` and the field defaults
leaves the bot running on its last-known-good configuration and logs loudly.
Trading state has no such circular dependency and is not exempt.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_db_resolution.py`:

```python
"""DB -> .env -> default, for non-sensitive fields only."""
import pytest

from swingbot import config


@pytest.fixture
def db_stage(monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield
    config._apply_env()          # restore module globals for the next test


def _field(key):
    return next(f for f in config.FIELDS if f.key == key)


def test_a_db_value_beats_the_env(db_stage, monkeypatch):
    from swingbot.core.db.repositories.settings import settings_repo
    monkeypatch.setenv("MIN_ALERT_CONFIDENCE_LEVEL", "2")
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    config._apply_env()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5


def test_the_env_is_used_when_the_db_has_no_row(db_stage, monkeypatch):
    monkeypatch.setenv("MIN_ALERT_CONFIDENCE_LEVEL", "2")
    config._apply_env()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 2


def test_the_field_default_is_used_when_neither_has_it(db_stage, monkeypatch):
    field = _field("MIN_ALERT_CONFIDENCE_LEVEL")
    monkeypatch.delenv("MIN_ALERT_CONFIDENCE_LEVEL", raising=False)
    config._apply_env()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == config._cast(field, field.default)


def test_a_sensitive_field_ignores_the_database(db_stage, monkeypatch):
    """Not 'prefers .env' -- the DB is not consulted for a secret at all."""
    from swingbot.core.db.repositories.settings import settings_repo
    monkeypatch.setenv("DISCORD_TOKEN", "from-env")
    settings_repo().put("DISCORD_TOKEN", "from-db", updated_by="test")
    config._apply_env()
    assert config.TOKEN == "from-env"


def test_no_sensitive_key_is_ever_written_by_the_resolver(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    config._apply_env()
    stored = set(settings_repo().all_settings())
    sensitive = {f.key for f in config.FIELDS if f.sensitive}
    assert not (stored & sensitive), "a secret reached the settings table"


def test_the_json_stage_never_touches_the_database(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    called = []
    monkeypatch.setattr(config, "_db_settings",
                        lambda: called.append(1) or {})
    config._apply_env()
    # _db_settings is still called; it must be the one that short-circuits.
    assert config._db_settings() == {}


def test_an_unreachable_database_falls_back_rather_than_raising(
        db_stage, monkeypatch, caplog):
    """_apply_env runs at import time. A raise here makes `import
    swingbot.config` fail, which breaks the admin UI someone would use to fix
    the connection string."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    monkeypatch.setenv("MIN_ALERT_CONFIDENCE_LEVEL", "3")
    with caplog.at_level("WARNING"):
        config._apply_env()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 3
    assert "settings" in caplog.text.lower()
    dbengine.reset_engine()


def test_a_malformed_db_value_falls_back_to_the_default(db_stage, monkeypatch):
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", "not-a-number",
                        updated_by="test")
    monkeypatch.delenv("MIN_ALERT_CONFIDENCE_LEVEL", raising=False)
    config._apply_env()
    field = _field("MIN_ALERT_CONFIDENCE_LEVEL")
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == config._cast(field, field.default)


def test_apply_env_still_reports_what_changed(db_stage, monkeypatch):
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    config._apply_env()
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 4, updated_by="test")
    changed = config._apply_env()
    assert changed["MIN_ALERT_CONFIDENCE_LEVEL"] == (5, 4)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_config_db_resolution.py -q
```

Expected: `test_a_db_value_beats_the_env` fails — the env value wins.

- [ ] **Step 3: Add the DB layer**

In `swingbot/config.py`, above `_apply_env`:

```python
def _db_settings() -> dict:
    """Non-sensitive settings from Postgres, or {} when unavailable.

    Degrades rather than raising, which is the THIRD documented exception to
    this plan's fail-fast rule (with the heartbeat and the regenerable caches).
    The reason is specific to this function: _apply_env() runs at module import
    time, so a raise here makes `import swingbot.config` fail -- and that
    breaks every entry point including the admin UI someone would use to fix
    the connection string. Falling back leaves the process on its last-known-
    good configuration and says so in the log. Trading state has no such
    circular dependency and gets no such exemption.
    """
    try:
        from swingbot.core.db import stages
        if not (stages.reads_db("settings") or stages.writes_db("settings")):
            return {}
        from swingbot.core.db.repositories.settings import settings_repo
        return settings_repo().all_settings()
    except Exception:
        log.warning("could not read settings from the database; falling back "
                    "to .env and field defaults", exc_info=True)
        return {}


def _resolve(f: "Field", db: dict) -> str:
    """The value for `f` as a raw string, ready for _cast.

    DB -> .env -> Field.default, except that a SENSITIVE field skips the DB
    entirely. Not "prefers .env": a secret is never read from the database,
    so a row that somehow exists for one is ignored rather than used.
    """
    if not f.sensitive and f.key in db:
        value = db[f.key]
        if isinstance(value, bool):
            # _cast's checkbox branch compares str(raw).lower() == "true".
            return "true" if value else "false"
        return "" if value is None else str(value)
    return os.getenv(f.key, f.default)
```

and in `_apply_env`, replace `raw = os.getenv(f.key, f.default)` with:

```python
    db = _db_settings()
    for f in FIELDS:
        raw = _resolve(f, db)
```

hoisting the `db = _db_settings()` call **above** the loop — one query per
`_apply_env()`, not one per field.

The existing malformed-value fallback below (`log.warning(... falling back to
default ...)`) now covers a malformed DB value too, unchanged. That is the
behaviour `test_a_malformed_db_value_falls_back_to_the_default` pins, and it is
why this task adds no new error handling inside the loop.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_config_db_resolution.py
python scripts/dev/testrun.py file tests/test_config.py
```

Expected: `0 failed` for both. The second is the regression check that the
`json` stage — every existing test's stage — resolves exactly as before.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py tests/test_config_db_resolution.py
git commit -m "feat(v67): resolve non-sensitive config DB -> .env -> default"
```

---

### Task P4-03: reload() picks up a database change

`reload()` (`config.py:909`) re-reads `.env` and calls `_apply_env()`. Since
P4-02 made `_apply_env` read the DB too, `reload()` already works — this task
adds the *entry point* the bot's listener will call, and the test that says
reloading needs no `.env` write.

**Files:**
- Modify: `swingbot/config.py` (`reload` `:909`, `auto_reload_if_changed` `:934`)
- Test: `tests/test_config_reload_db.py`

**Interfaces:**
- Consumes: `_db_settings` (P4-02).
- Produces on `swingbot.config`:
  - `reload_settings() -> dict` — re-applies without re-reading `.env` from
    disk, for a DB-originated change
  - `reload()` keeps its exact signature and behaviour

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_reload_db.py`:

```python
"""A settings change reaches config without anyone writing .env."""
import pytest

from swingbot import config


@pytest.fixture
def db_stage(monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield
    config._apply_env()


def test_reload_settings_picks_up_a_new_row(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    changed = config.reload_settings()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5
    assert "MIN_ALERT_CONFIDENCE_LEVEL" in changed


def test_reload_settings_returns_an_empty_dict_when_nothing_moved(db_stage):
    config.reload_settings()
    assert config.reload_settings() == {}


def test_reload_settings_does_not_stat_the_env_file(db_stage, monkeypatch):
    """The point of a separate entry point: a DB-originated change must not
    make a .env read part of the hot path."""
    import os
    calls = []
    real_stat = os.stat

    def spy(path, *a, **kw):
        if str(path) == str(config.ENV_PATH):
            calls.append(path)
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(os, "stat", spy)
    config.reload_settings()
    assert calls == []


def test_reload_still_rereads_env(db_stage, monkeypatch, tmp_path):
    """reload() is unchanged: it is what SIGHUP calls for a secret change."""
    env = tmp_path / ".env"
    env.write_text("MIN_ALERT_CONFIDENCE_LEVEL=2\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    config.reload()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 2


def test_a_db_value_still_wins_after_a_plain_reload(db_stage, monkeypatch,
                                                    tmp_path):
    from swingbot.core.db.repositories.settings import settings_repo
    env = tmp_path / ".env"
    env.write_text("MIN_ALERT_CONFIDENCE_LEVEL=2\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    config.reload()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5


def test_a_non_hot_reloadable_field_is_still_reported_but_not_promised(db_stage):
    """reload() has never made a non-hot-reloadable field take effect -- it
    updates the global and the caller is responsible for knowing a restart is
    needed. The DB path changes nothing about that."""
    non_hot = [f for f in config.FIELDS
               if not f.hot_reloadable and not f.sensitive]
    if not non_hot:
        pytest.skip("no non-sensitive, non-hot-reloadable field to test")
    field = non_hot[0]
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put(field.key, "changed-value", updated_by="test")
    changed = config.reload_settings()
    assert field.attr in changed
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_config_reload_db.py -q
```

Expected: `AttributeError: module 'swingbot.config' has no attribute 'reload_settings'`.

- [ ] **Step 3: Add the entry point**

In `swingbot/config.py`, beside `reload()`:

```python
def reload_settings() -> dict:
    """Re-apply configuration after a DATABASE change.

    Unlike reload(), this does NOT re-read .env from disk: a settings row
    moved, not a secret, and stat-ing plus re-parsing .env on every NOTIFY
    would put file I/O back into a path the migration exists to take it out of.
    SIGHUP still calls reload() for secret changes -- see P4-09.

    Returns {attr: (old, new)} for whatever actually changed, same as reload().
    """
    changed = _apply_env()
    if changed:
        log.info("Settings reloaded from the database -- %d value(s) changed:",
                 len(changed))
        for attr, (old, new) in changed.items():
            f = next((f for f in FIELDS if f.attr == attr), None)
            display_old = "***" if f and f.sensitive else old
            display_new = "***" if f and f.sensitive else new
            log.info("  %s: %r -> %r", attr, display_old, display_new)
    else:
        log.debug("Settings reloaded from the database -- no changes.")
    return changed
```

`reload()` is untouched. So is `auto_reload_if_changed()` — the `.env` mtime
check remains the right trigger for a `.env` change, and it now costs nothing
extra because DB changes arrive by NOTIFY rather than by polling.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_config_reload_db.py
python scripts/dev/testrun.py file tests/test_config.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py tests/test_config_reload_db.py
git commit -m "feat(v67): add config.reload_settings for DB-originated changes"
```

---

### Task P4-04: Seed the settings table from .env

The cutover import for this part: every non-sensitive field currently resolved
from `.env` becomes a row, so flipping the stage changes nothing about what the
bot reads.

**Files:**
- Create: `scripts/db/import_settings.py`
- Test: `tests/scripts/test_import_settings.py`

**Interfaces:**
- Consumes: `settings_repo` (P4-01), `config.FIELDS`, `dotenv_values`.
- Produces: `load_env_settings(env_path=None) -> dict[str, Any]` and a CLI with
  `--dry-run`.

**The property the import must have:** after it runs, `_apply_env()` must
produce **exactly the same module globals** as before. That is what the test
asserts, and it is a stronger check than comparing the rows to `.env` — it
compares the thing that actually matters.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_import_settings.py`:

```python
"""Seeding must not change a single resolved value."""
import pytest

from swingbot import config
from scripts.db.import_settings import load_env_settings, main


@pytest.fixture
def db_stage(monkeypatch, db_committed, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "MIN_ALERT_CONFIDENCE_LEVEL=4\n"
        "SESSION_START_HOUR=9\n"
        "DISCORD_TOKEN=super-secret\n",
        encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield env
    config._apply_env()


def test_no_sensitive_field_is_ever_loaded(db_stage):
    loaded = load_env_settings(str(db_stage))
    sensitive = {f.key for f in config.FIELDS if f.sensitive}
    assert not (set(loaded) & sensitive)


def test_only_known_fields_are_loaded(db_stage):
    db_stage.write_text(db_stage.read_text(encoding="utf-8")
                        + "SOMETHING_CUSTOM=x\n", encoding="utf-8")
    assert "SOMETHING_CUSTOM" not in load_env_settings(str(db_stage))


def test_values_are_loaded_with_their_field_type(db_stage):
    loaded = load_env_settings(str(db_stage))
    assert loaded["MIN_ALERT_CONFIDENCE_LEVEL"] == 4
    assert isinstance(loaded["MIN_ALERT_CONFIDENCE_LEVEL"], int)


def test_dry_run_writes_nothing(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    assert main(["--dry-run"]) == 0
    assert settings_repo().all_settings() == {}


def test_after_the_import_every_resolved_value_is_identical(db_stage):
    """The check that matters: the module globals, before and after."""
    config._apply_env()
    before = {f.attr: getattr(config, f.attr, None) for f in config.FIELDS}
    assert main([]) == 0
    config._apply_env()
    after = {f.attr: getattr(config, f.attr, None) for f in config.FIELDS}
    assert after == before


def test_re_running_the_import_is_idempotent(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    main([])
    first = settings_repo().all_settings()
    main([])
    assert settings_repo().all_settings() == first
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_import_settings.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.db.import_settings'`.

- [ ] **Step 3: Write it**

Create `scripts/db/import_settings.py`:

```python
#!/usr/bin/env python3
"""Seed the settings table from the current .env.

Non-sensitive fields only. After this runs, config._apply_env() must produce
byte-identical module globals -- the point of the seed is that flipping the
stage changes nothing about what the bot reads.

    python scripts/db/import_settings.py --dry-run
    python scripts/db/import_settings.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from dotenv import dotenv_values                              # noqa: E402

from swingbot import config                                   # noqa: E402
from swingbot.core.db.repositories.settings import settings_repo  # noqa: E402


def load_env_settings(env_path: str | None = None) -> dict:
    """Every non-sensitive FIELDS entry present in .env, cast to its type.

    Unknown keys are skipped: _build_env_text deliberately preserves
    hand-added custom variables at the bottom of .env, and those are not
    configuration this repo knows how to type or reload.
    """
    values = dotenv_values(env_path or config.ENV_PATH, encoding="utf-8")
    out = {}
    for f in config.FIELDS:
        if f.sensitive or f.key not in values:
            continue
        raw = values[f.key]
        if raw is None:
            continue
        try:
            out[f.key] = config._cast(f, raw)
        except (ValueError, TypeError):
            print(f"[settings] SKIP {f.key}: {raw!r} is not a valid {f.type}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env", help="path to .env (default: config.ENV_PATH)")
    args = ap.parse_args(argv)

    loaded = load_env_settings(args.env)
    print(f"[settings] {len(loaded)} non-sensitive field(s) in "
          f"{args.env or config.ENV_PATH}")
    if args.dry_run:
        for key in sorted(loaded):
            print(f"[settings]   would set {key}={loaded[key]!r}")
        print("[settings] DRY RUN -- nothing written")
        return 0

    settings_repo().put_many(loaded, updated_by="import_settings")
    stored = settings_repo().all_settings()
    missing = sorted(set(loaded) - set(stored))
    print(f"[settings] {len(stored)} row(s) written")
    if missing:
        print(f"[settings] MISSING after write: {missing}")
        return 1
    print("[settings] VERDICT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and a dry run**

```bash
python scripts/dev/testrun.py file tests/scripts/test_import_settings.py
python scripts/db/import_settings.py --dry-run
```

Expected: `0 failed`, and the dry run listing this checkout's non-sensitive
fields without writing.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/import_settings.py tests/scripts/test_import_settings.py
git commit -m "feat(v67): seed the settings table from .env"
```

---

### Task P4-05: The admin settings page writes rows

`save_settings` currently rebuilds the whole `.env` from the submitted form via
`_build_env_text` (`admin/helpers.py:66`) and rewrites it in place. At the db
stage it writes rows for the non-sensitive fields and touches `.env` only for
secrets.

**Files:**
- Modify: `swingbot/admin/helpers.py` (`save_settings` — find it with
  `grep -n "def save_settings" swingbot/admin/helpers.py`)
- Test: `tests/admin/test_save_settings_db.py`

**Interfaces:**
- Consumes: `settings_repo` (P4-01), `stages`, `append_settings_audit`
  (existing).
- Produces: `split_form_values(form) -> tuple[dict, dict]` — `(secrets,
  non_secrets)`, both keyed by `Field.key`, so the two destinations are decided
  in one place rather than at each write.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_save_settings_db.py`:

```python
"""Saving settings: rows for configuration, .env for secrets."""
import pytest

from swingbot import config
from swingbot.admin import helpers


@pytest.fixture
def db_stage(monkeypatch, db_committed, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_TOKEN=old-secret\n"
                   "MIN_ALERT_CONFIDENCE_LEVEL=3\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    return env


def test_split_puts_secrets_and_settings_in_separate_buckets():
    secrets, settings = helpers.split_form_values(
        {"DISCORD_TOKEN": "t", "MIN_ALERT_CONFIDENCE_LEVEL": "4"})
    assert set(secrets) == {"DISCORD_TOKEN"}
    assert set(settings) == {"MIN_ALERT_CONFIDENCE_LEVEL"}


def test_split_ignores_a_key_that_is_not_a_field():
    secrets, settings = helpers.split_form_values({"NOT_A_FIELD": "x"})
    assert secrets == {} and settings == {}


def test_a_non_secret_change_writes_a_row(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    assert settings_repo().get_value("MIN_ALERT_CONFIDENCE_LEVEL") == 5


def test_a_non_secret_change_does_not_rewrite_env(db_stage):
    before = db_stage.read_text(encoding="utf-8")
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    assert db_stage.read_text(encoding="utf-8") == before


def test_a_secret_change_still_rewrites_env(db_stage):
    helpers.save_settings({"DISCORD_TOKEN": "new-secret"})
    assert "new-secret" in db_stage.read_text(encoding="utf-8")


def test_no_secret_reaches_the_settings_table(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    helpers.save_settings({"DISCORD_TOKEN": "new-secret",
                           "MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    assert "DISCORD_TOKEN" not in settings_repo().all_settings()


def test_a_blank_secret_still_means_no_change(db_stage):
    """The existing rule: a blank sensitive field in the form is 'leave it
    alone', not 'wipe the credential'. It survives the migration."""
    helpers.save_settings({"DISCORD_TOKEN": ""})
    assert "old-secret" in db_stage.read_text(encoding="utf-8")


def test_the_change_is_audited(db_stage):
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    rows = helpers.read_settings_audit()
    assert any(c["key"] == "MIN_ALERT_CONFIDENCE_LEVEL"
               for r in rows for c in r["changes"])


def test_a_checkbox_round_trips_as_a_boolean(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    checkbox = next((f for f in config.FIELDS
                     if f.type == "checkbox" and not f.sensitive), None)
    if checkbox is None:
        pytest.skip("no non-sensitive checkbox field")
    helpers.save_settings({checkbox.key: "on"})
    assert settings_repo().get_value(checkbox.key) is True
```

`save_settings`'s real signature may differ from `save_settings(form)` — read
it before writing these tests and match it exactly, including whether it
returns a diff.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_save_settings_db.py -q
```

Expected: `AttributeError: module ... has no attribute 'split_form_values'`.

- [ ] **Step 3: Add the split and branch the save**

In `swingbot/admin/helpers.py`:

```python
def split_form_values(form) -> tuple[dict, dict]:
    """(secrets, non_secrets) from a submitted settings form.

    One place decides which destination a key has, so the save path, the audit
    entry and the export can never disagree about it. A key that is not a
    FIELDS entry belongs to neither bucket -- _build_env_text preserves those
    at the bottom of .env untouched, and that behaviour is unchanged.
    """
    secrets, non_secrets = {}, {}
    for key, value in form.items():
        f = FIELDS_BY_KEY.get(key)
        if f is None:
            continue
        (secrets if f.sensitive else non_secrets)[key] = value
    return secrets, non_secrets
```

and in `save_settings`, before the existing `_build_env_text` call:

```python
    from swingbot.core.db import stages
    secrets, non_secrets = split_form_values(form)

    if stages.writes_db("settings"):
        typed = {}
        for key, raw in non_secrets.items():
            f = FIELDS_BY_KEY[key]
            value = (form.get(key) == "on") if f.type == "checkbox" else raw
            try:
                typed[key] = config._cast(f, "true" if value is True
                                          else "false" if value is False
                                          else value)
            except (ValueError, TypeError):
                log.warning("settings save: %s=%r is not a valid %s; skipped",
                            key, raw, f.type)
        settings_repo().put_many(typed, updated_by="admin")

    # .env is rewritten only when a SECRET actually changed, or when the
    # settings stage still writes files. Pushing a settings change no longer
    # needs the Docker socket, because it no longer needs a container restart.
    if secrets or stages.writes_json("settings"):
        # ... existing _build_env_text / _write_env_text path ...
        pass
```

The audit entry is built from the same `diff` the function already computes —
do not compute a second one from the typed dict, or the two will disagree about
what a checkbox change looks like.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_save_settings_db.py
python scripts/dev/testrun.py file tests/admin/test_helpers.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system.py
```

Expected: `0 failed` for all three.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py tests/admin/test_save_settings_db.py
git commit -m "feat(v67): write settings rows from the admin page"
```

---

### Task P4-06: Narrow _build_env_text to secrets

`_build_env_text` (`helpers.py:66`) reconstructs the **whole** `.env` from the
form on every save — which is why toggling one column used to rewrite every
setting the bot has. At the db stage it emits only the sensitive fields, plus
the hand-added custom variables it has always preserved.

**Files:**
- Modify: `swingbot/admin/helpers.py` (`_build_env_text` `:66`)
- Test: `tests/admin/test_build_env_text_narrowed.py`

**Interfaces:**
- Consumes: `stages`, `split_form_values` (P4-05).
- Produces: `_build_env_text(form, existing, *, secrets_only: bool = False)` —
  one added keyword-only parameter, defaulting to today's behaviour.

**The default matters.** `secrets_only=False` keeps every existing caller and
every existing test working unchanged; only `save_settings` passes `True`, and
only at the db stage. A parameter that changed the default would make this a
behaviour change disguised as a refactor.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_build_env_text_narrowed.py`:

```python
"""_build_env_text, narrowed to secrets, without changing its default."""
import pytest

from swingbot import config
from swingbot.admin import helpers

FORM = {"DISCORD_TOKEN": "tok", "MIN_ALERT_CONFIDENCE_LEVEL": "4"}
EXISTING = {"DISCORD_TOKEN": "old", "MIN_ALERT_CONFIDENCE_LEVEL": "3",
            "SOMETHING_CUSTOM": "keep-me"}


def test_the_default_still_writes_every_field():
    text = helpers._build_env_text(FORM, EXISTING)
    assert "DISCORD_TOKEN=" in text
    assert "MIN_ALERT_CONFIDENCE_LEVEL=" in text


def test_secrets_only_omits_non_sensitive_fields():
    text = helpers._build_env_text(FORM, EXISTING, secrets_only=True)
    assert "DISCORD_TOKEN=tok" in text
    assert "MIN_ALERT_CONFIDENCE_LEVEL" not in text


def test_secrets_only_still_preserves_custom_variables():
    """The reason that block exists -- a hand-added variable must never be
    dropped just because the structured UI does not know about it -- is
    unaffected by which fields the UI manages."""
    text = helpers._build_env_text(FORM, EXISTING, secrets_only=True)
    assert "SOMETHING_CUSTOM=keep-me" in text


def test_secrets_only_still_treats_a_blank_as_no_change():
    text = helpers._build_env_text({"DISCORD_TOKEN": ""}, EXISTING,
                                   secrets_only=True)
    assert "DISCORD_TOKEN=old" in text


def test_every_sensitive_field_appears_in_the_secrets_only_output():
    text = helpers._build_env_text({}, EXISTING, secrets_only=True)
    for f in config.FIELDS:
        if f.sensitive:
            assert f"{f.key}=" in text, f.key


def test_the_output_is_still_parseable_as_dotenv():
    import io
    from dotenv import dotenv_values
    text = helpers._build_env_text(FORM, EXISTING, secrets_only=True)
    parsed = dotenv_values(stream=io.StringIO(text))
    assert parsed["DISCORD_TOKEN"] == "tok"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_build_env_text_narrowed.py -q
```

Expected: `TypeError: _build_env_text() got an unexpected keyword argument`.

- [ ] **Step 3: Add the parameter**

```python
def _build_env_text(form, existing: dict, *, secrets_only: bool = False) -> str:
    """
    Reconstructs the .env file: one section-commented block per FIELDS group
    with every known field's new value from the submitted form, followed by any
    keys that existed in the file but aren't covered by FIELDS -- so a
    manually-added custom variable is never silently dropped just because the
    structured UI doesn't know about it.

    `secrets_only=True` emits ONLY the sensitive fields (plus that same
    custom-variable block). That is what the db stage passes: non-sensitive
    configuration lives in the settings table there, and rewriting it into .env
    as well would give one value two homes that could disagree.

    The default is False so every existing caller and test is unaffected --
    a changed default here would be a behaviour change wearing a refactor's
    clothes.
    """
    known_keys = set(FIELDS_BY_KEY)
    lines = [
        "# Managed by the Swing Bot admin UI.",
        "# Structured fields below are grouped by section; anything else",
        "# found in the previous .env is preserved at the bottom untouched.",
        "",
    ]
    for section, fields in FIELDS_BY_SECTION:
        emitted = [f for f in fields if f.sensitive or not secrets_only]
        if not emitted:
            continue
        lines.append(f"# --- {section} ---")
        for f in emitted:
            # ... existing per-field body, unchanged ...
            pass
        lines.append("")
    # ... existing leftover block, unchanged ...
```

In `save_settings`'s `.env` branch (P4-05), pass
`secrets_only=stages.reads_db("settings")`.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_build_env_text_narrowed.py
python scripts/dev/testrun.py file tests/admin/test_helpers.py
python scripts/dev/testrun.py file tests/admin/test_save_settings_db.py
```

Expected: `0 failed` for all three.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py tests/admin/test_build_env_text_narrowed.py
git commit -m "feat(v67): narrow the .env rewrite to secrets at the db stage"
```

---

### Task P4-07: Export and import still round-trip

`build_settings_export_text` (`helpers.py:~225`) emits every non-sensitive field
so someone can export, edit and re-import. `import_env_text` (`:232`) applies a
pasted `.env`, sensitive keys included. Both must keep working when the
non-sensitive half lives in a table — and NG15's acceptance check is a round
trip, so this is where that check is re-established.

**Files:**
- Modify: `swingbot/admin/helpers.py` (`build_settings_export_text`,
  `import_env_text`)
- Test: `tests/admin/test_settings_export_import_db.py`

**Interfaces:**
- Consumes: `settings_repo` (P4-01), `stages`, `split_form_values` (P4-05).
- Produces: no new public symbols. Both functions keep their signatures and
  their return shapes (`import_env_text` still returns
  `(applied_count, unknown_keys)`).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_settings_export_import_db.py`:

```python
"""NG15's round trip: export, edit, import, and the bot reads the change."""
import io

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.admin import helpers


@pytest.fixture
def db_stage(monkeypatch, db_committed, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_TOKEN=secret\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield env
    config._apply_env()


def test_the_export_reads_current_values_from_the_database(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    text = helpers.build_settings_export_text()
    assert "MIN_ALERT_CONFIDENCE_LEVEL=5" in text


def test_the_export_still_omits_secrets(db_stage):
    text = helpers.build_settings_export_text()
    for f in config.FIELDS:
        if f.sensitive:
            assert f"{f.key}=" not in text, f.key


def test_an_imported_non_secret_lands_in_the_database(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    applied, unknown = helpers.import_env_text("MIN_ALERT_CONFIDENCE_LEVEL=5\n")
    assert applied == 1 and unknown == []
    assert settings_repo().get_value("MIN_ALERT_CONFIDENCE_LEVEL") == 5


def test_an_imported_secret_still_lands_in_env(db_stage):
    helpers.import_env_text("DISCORD_TOKEN=pasted-secret\n")
    assert "pasted-secret" in db_stage.read_text(encoding="utf-8")


def test_an_imported_secret_never_lands_in_the_database(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    helpers.import_env_text("DISCORD_TOKEN=pasted-secret\n")
    assert "DISCORD_TOKEN" not in settings_repo().all_settings()


def test_an_unknown_key_is_reported_not_applied(db_stage):
    applied, unknown = helpers.import_env_text("NOT_A_FIELD=x\n")
    assert applied == 0 and unknown == ["NOT_A_FIELD"]


def test_a_bad_numeric_is_skipped_rather_than_stored(db_stage):
    from swingbot.core.db.repositories.settings import settings_repo
    helpers.import_env_text("MIN_ALERT_CONFIDENCE_LEVEL=not-a-number\n")
    from swingbot.core.db.repositories.settings import SENTINEL_MISSING
    assert settings_repo().get_value("MIN_ALERT_CONFIDENCE_LEVEL") is SENTINEL_MISSING


def test_the_full_round_trip(db_stage):
    """Export, edit one value, re-import, and config resolves the new value."""
    text = helpers.build_settings_export_text()
    parsed = dotenv_values(stream=io.StringIO(text))
    assert "MIN_ALERT_CONFIDENCE_LEVEL" in parsed
    edited = text.replace(
        f"MIN_ALERT_CONFIDENCE_LEVEL={parsed['MIN_ALERT_CONFIDENCE_LEVEL']}",
        "MIN_ALERT_CONFIDENCE_LEVEL=5")
    helpers.import_env_text(edited)
    config.reload_settings()
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_settings_export_import_db.py -q
```

Expected: `test_the_export_reads_current_values_from_the_database` fails — the
export reads `_read_env_values()` only.

- [ ] **Step 3: Branch both**

`build_settings_export_text` resolves each field the same way `config` does,
rather than reading `.env` directly:

```python
def build_settings_export_text() -> str:
    """The exported .env body — one definition, two callers.

    Sensitive fields are OMITTED, not masked: a masked line would import as the
    literal mask and blank out a real secret, and an export is exactly the file
    someone re-imports.

    At the db stage the values come from the settings table layered over .env,
    because that is what the bot is actually running on -- an export that
    showed .env's stale copy would export a configuration nobody is using.
    """
    from swingbot.core.db import stages
    existing = _read_env_values()
    db = config._db_settings() if stages.reads_db("settings") else {}

    def _value(f):
        if f.key in db:
            v = db[f.key]
            if isinstance(v, bool):
                return "true" if v else "false"
            return "" if v is None else str(v)
        return existing.get(f.key, f.default)

    return "\n".join(f"{f.key}={_value(f)}"
                     for f in config.FIELDS if not f.sensitive) + "\n"
```

`import_env_text` routes each accepted key by sensitivity, reusing the existing
type-check loop and leaving its `(applied, unknown)` contract intact:

```python
    # ... existing parse + validation loop, unchanged, building new_values ...
    from swingbot.core.db import stages
    if stages.writes_db("settings"):
        typed = {}
        for key, raw in new_values.items():
            f = FIELDS_BY_KEY.get(key)
            if f is None or f.sensitive:
                continue
            try:
                typed[key] = config._cast(f, raw)
            except (ValueError, TypeError):
                continue          # already counted as skipped above
        settings_repo().put_many(typed, updated_by="import_env_text")
        new_values = {k: v for k, v in new_values.items()
                      if FIELDS_BY_KEY.get(k) and FIELDS_BY_KEY[k].sensitive}
    _write_env_text(_build_env_text(new_values, existing,
                                    secrets_only=stages.reads_db("settings")))
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_settings_export_import_db.py
python scripts/dev/testrun.py file tests/admin/test_helpers.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because export/import has callers in both
`app.py` and the v1 API.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py tests/admin/test_settings_export_import_db.py
git commit -m "feat(v67): keep the settings export/import round trip intact"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_4b-settings-admin.md`**
(P4-08…P4-14): the NOTIFY listener, SIGHUP, the import-time-capture audit, the
Docker-socket removal, and Part 4's verification.
