# v67 — Part 4: Settings (tasks P4-07…P4-14)

> Continuation of `2026-08-29-v67-json-to-postgres_4a-settings-resolution.md`.
> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints and the `_4a` file before starting any task here** — the
> Parallelisation map, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

> **2026-09-30:** P4-07 moved here from `_4a` unchanged, so `_4a` stays under
> 1500 lines. It still runs after P4-06 (both edit `admin/helpers.py`) and
> before P4-08; the index's part table row should read P4-01…06 / P4-07…14.

### Task P4-07: Export and import still round-trip

`build_settings_export_text` (`helpers.py:205`) emits every non-sensitive field
so someone can export, edit and re-import. `import_env_text` (`:225`) applies a
pasted `.env`, sensitive keys included.

> **2026-09-30 re-examination:** both functions and their contracts match
> `main`; their only callers are `api_v1/system.py:export_settings` /
> `import_settings` (the Jinja `app.py` routes are gone). **Design fix to
> Step 3:** `import_env_text` does **not** write through `_build_env_text` — it
> has its own section/leftover line loop over `new_values`. Keep that loop and
> filter it by `f.sensitive or f.key in config._ENV_ONLY` at the db stage;
> do not swap in `_build_env_text(new_values, ...)` as the snippet shows,
> because `_build_env_text`'s checkbox branch reads the form convention
> (`form.get(key) == "on"`) and would write every pasted `true` checkbox as
> `false`. The export's `db` read should use `helpers.current_values()`
> (P4-05) rather than a second copy of the bool/None stringification. Tests:
> the fixture needs `monkeypatch.setenv("DB_STORES", "settings:db")`, and the
> regression suite is `tests/admin/test_api_v1_system_settings.py` (its
> export/import round-trip tests), not `tests/admin/test_helpers.py`. Both must keep working when the
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
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_settings.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because `helpers.py` is imported by most
of the admin surface (2026-09-30: the `app.py` export/import callers are gone;
the v1 API is the only caller).

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py tests/admin/test_settings_export_import_db.py
git commit -m "feat(v67): keep the settings export/import round trip intact"
```

---

### Task P4-08: The bot reloads on NOTIFY

A settings row changes, the trigger fires, the bot's listener calls
`config.reload_settings()`. No SIGHUP, no Docker socket, no polling.

**Files:**
- Create: `swingbot/core/infra/settings_listener.py`
- Modify: ~~`bot.py`~~ `swingbot/commands/scanning/loops.py` (`on_ready` `:849`,
  `config_watcher` `:283`) — 2026-09-30: `bot.py` has no startup hooks; the
  background tasks start in `loops.on_ready`
- Test: `tests/infra/test_settings_listener.py`

**Interfaces:**
- Consumes: `notify.listen` (P1-13), `config.reload_settings` (P4-03),
  `stages`.

> **2026-09-30 re-examination — blocked, and the reload must go through the
> bot's post-reload path.**
>
> - **Blocker:** `notify.listen()` (P1-13) does not exist on `main`
>   (`swingbot/core/db/notify.py` has only the DDL helpers and `emit`). Build
>   P1-13 first, to the signature in `_1c` (`listen(channels, on_event, stop,
>   *, poll=0.5, dsn=None)`). As specified there it raises on a dropped
>   connection, so `_run` below must loop with a capped backoff and re-LISTEN
>   rather than log once and let the thread die — otherwise one Postgres
>   restart silently ends hot-reload until the bot restarts. Add a test that
>   kills the listening backend (`pg_terminate_backend`) and asserts a later
>   write still reloads.
> - **Side effects:** a reload is not just `config.reload_settings()`. After
>   `.env` reloads, `config_watcher` applies `LOG_LEVEL`
>   (`apply_log_level`), `_apply_scan_interval_change(changed)` and v110's
>   `_post_config_notices(changed)`; SIGHUP runs `bot_core._reload_callbacks`.
>   Calling `reload_settings()` bare from a thread skips all three, so an
>   admin change to `SCAN_INTERVAL_MINUTES` or `LOG_LEVEL` would update the
>   global and do nothing. Those also need the event loop, not the listener
>   thread. Design: the listener thread only sets a `threading.Event`
>   (`settings_dirty`) — no config work on that thread. `config_watcher`
>   checks it every tick, clears it, runs `reload_settings` via
>   `asyncio.to_thread`, and feeds the result into the **same** post-reload
>   block it uses for `auto_reload_if_changed` (extract that block as
>   `_after_reload(changed)`). Latency becomes ≤30 s (the watcher's interval),
>   the same as `.env` today. If that is too slow, wake it with
>   `loop.call_soon_threadsafe` — ask the partner before adding that.
>   `SettingsListener(on_reload=...)` keeps its seam for tests; the default
>   `on_reload` sets the event.
> - **Logger:** `logging.getLogger(__name__)`, not `"swing-bot.settings"` —
>   `tests/infra/test_logger_names.py` (v111) fails on a `swing-bot` literal.
> - **Shared channel:** the `settings_audit` trigger also notifies on
>   `settings`, so expect ≥2 events per audited save; the dirty-flag design
>   collapses them for free.
> - `tests/test_bot_startup.py` does not exist; use
>   `tests/commands/test_config_watcher_task.py` and
>   `tests/commands/test_config_watcher_reload.py` as the regression check.
- Produces:
  - `SettingsListener(on_reload=config.reload_settings)` with `.start()`,
    `.stop()`
  - `start_settings_listener() -> SettingsListener | None` — returns `None` at
    the `json` stage, so `bot.py` has one call and no branch of its own

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_settings_listener.py`:

```python
"""A settings write in Postgres reaches the bot's config globals."""
import threading
import time

import pytest

from swingbot import config
from swingbot.core.infra.settings_listener import (
    SettingsListener,
    start_settings_listener,
)

pytestmark = pytest.mark.slow


@pytest.fixture
def db_stage(monkeypatch, db_engine, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    yield
    config._apply_env()


def test_the_json_stage_starts_no_listener(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    assert start_settings_listener() is None


def test_the_db_stage_starts_one(db_stage):
    listener = start_settings_listener()
    assert isinstance(listener, SettingsListener)
    listener.stop()


def test_a_settings_write_triggers_a_reload(db_stage, db_committed):
    from swingbot.core.db.repositories.settings import settings_repo
    reloads = []
    listener = SettingsListener(on_reload=lambda: reloads.append(1) or {})
    listener.start()
    try:
        time.sleep(0.5)                       # let LISTEN register
        with db_committed.begin():
            settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5,
                                updated_by="test", conn=db_committed)
        deadline = time.time() + 8
        while time.time() < deadline and not reloads:
            time.sleep(0.05)
        assert reloads, "no reload fired within 8s"
    finally:
        listener.stop()


def test_the_reloaded_value_reaches_config(db_stage, db_committed):
    from swingbot.core.db.repositories.settings import settings_repo
    listener = SettingsListener()
    listener.start()
    try:
        time.sleep(0.5)
        with db_committed.begin():
            settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5,
                                updated_by="test", conn=db_committed)
        deadline = time.time() + 8
        while time.time() < deadline and config.MIN_ALERT_CONFIDENCE_LEVEL != 5:
            time.sleep(0.05)
        assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5
    finally:
        listener.stop()


def test_a_raising_reload_does_not_kill_the_listener(db_stage, db_committed):
    """A bad value in the table must not take the listener thread down --
    the next good write has to be able to fix it."""
    from swingbot.core.db.repositories.settings import settings_repo
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("bad config")

    listener = SettingsListener(on_reload=boom)
    listener.start()
    try:
        time.sleep(0.5)
        for _ in range(2):
            with db_committed.begin():
                settings_repo().put("K", len(calls), updated_by="test",
                                    conn=db_committed)
            time.sleep(1.0)
        assert len(calls) >= 2, "the listener stopped after the first raise"
    finally:
        listener.stop()


def test_stop_joins_the_thread(db_stage):
    listener = SettingsListener()
    listener.start()
    listener.stop()
    assert not any(t.name == "settings-listener" and t.is_alive()
                   for t in threading.enumerate())
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/infra/test_settings_listener.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `swingbot/core/infra/settings_listener.py`:

```python
"""Wake the bot when a settings row changes.

This is what removes the Docker socket from the settings path: the admin no
longer has to restart the bot container for a configuration change to take
effect, because the bot hears about it.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from swingbot import config
from swingbot.core.db import notify

log = logging.getLogger(__name__)   # v111: never a "swing-bot" literal

CHANNEL = "settings"


class SettingsListener:
    """LISTEN on `settings`; call `on_reload` per notification."""

    def __init__(self, on_reload: Callable[[], dict] | None = None):
        self._on_reload = on_reload or config.reload_settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="settings-listener")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)

    def _run(self) -> None:
        try:
            notify.listen([CHANNEL], self._on_event, self._stop, poll=0.5)
        except Exception:
            log.exception("settings listener stopped")

    def _on_event(self, channel: str | None) -> None:
        if channel is None:      # a poll tick with nothing delivered
            return
        try:
            self._on_reload()
        except Exception:
            # Never let a bad stored value take the thread down -- the next
            # good write has to be able to fix it.
            log.exception("settings reload failed; keeping the previous config")


def start_settings_listener() -> SettingsListener | None:
    """Start one if this stage needs it, else None.

    Returning None rather than a no-op object keeps the stage decision here
    instead of in bot.py, which has no business knowing about DB_STORES.
    """
    from swingbot.core.db import stages
    if not stages.reads_db("settings"):
        return None
    listener = SettingsListener()
    listener.start()
    log.info("Listening for settings changes on the %r channel", CHANNEL)
    return listener
```

- [ ] **Step 4: Start it from the bot**

In ~~`bot.py`~~ `swingbot/commands/scanning/loops.py:on_ready` (2026-09-30:
beside `config_watcher.start()`; guard against a second start on reconnect,
since `on_ready` fires on every resume — mirror the `is_running()` guards
there), and wire the dirty flag into `config_watcher` per the callout above:

```python
    from swingbot.core.infra.settings_listener import start_settings_listener
    _settings_listener = start_settings_listener()
```

Keep the reference at module scope so the object is not garbage-collected while
its thread runs. The thread is a daemon, so no shutdown hook is required —
but if `bot.py` already has an explicit shutdown path, call `.stop()` there.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest tests/infra/test_settings_listener.py -q
python scripts/dev/testrun.py file tests/commands/test_config_watcher_task.py
python scripts/dev/testrun.py file tests/commands/test_config_watcher_reload.py
python scripts/dev/testrun.py file tests/infra/test_logger_names.py
```

Expected: `0 failed`. The listener tests are `slow` (they commit), so the fast
tier skips them and raw pytest is the right call here.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/infra/settings_listener.py \
        swingbot/commands/scanning/loops.py \
        tests/infra/test_settings_listener.py
git commit -m "feat(v67): reload config when a settings row changes"
```

---

### Task P4-09: SIGHUP still works, for secrets

SIGHUP is retained for `.env` secret changes. This task is the test that says
so, plus the one-line change that makes the handler call the right function.

**Files:**
- Modify: ~~`bot.py`~~ `swingbot/bot_core.py` (`_handle_reload_signal` `:265`,
  installed by `install_reload_signal_handler` `:298`) — 2026-09-30: the
  handler moved; `bot.py` contains no `SIGHUP`
- Test: `tests/test_sighup_reload.py`

> **2026-09-30 re-examination:** the handler already calls `config.reload()`
> (`bot_core.py:273`), then `apply_log_level` and `_reload_callbacks`; so this
> task is expected to change no production code. The source-text test must
> target `swingbot.bot_core._handle_reload_signal`, not `bot`. The DB-survives
> test needs `monkeypatch.setenv("DB_STORES", "settings:db")` too (P4-02
> callout) — and note the `.env` it writes lacks `DB_STORES`, so without the
> setenv `reload()` would flip the stage back to `json` mid-test.
> `config_watcher`'s 30 s `.env` mtime poll (`loops.py:283`) is a third path
> that also calls `reload()`; it stays, and needs no change here.

**Interfaces:**
- Consumes: `config.reload` (unchanged), `config.reload_settings` (P4-03).
- Produces: no new symbols.

**Why both paths stay.** SIGHUP re-reads `.env`, which is where secrets live and
where they will keep living. NOTIFY re-reads the settings table. Neither
subsumes the other, and collapsing them would mean either polling `.env` for
secret changes or putting secrets in the database — both of which this plan
rejected explicitly.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sighup_reload.py`:

```python
"""SIGHUP is the secrets path; NOTIFY is the settings path. Both stay."""
import pytest

from swingbot import config


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("DISCORD_TOKEN=first\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(path))
    yield path
    config._apply_env()


def test_reload_picks_up_a_changed_secret(env):
    config.reload()
    assert config.TOKEN == "first"
    env.write_text("DISCORD_TOKEN=second\n", encoding="utf-8")
    changed = config.reload()
    assert config.TOKEN == "second"
    assert "TOKEN" in changed


def test_reload_masks_the_secret_in_its_log(env, caplog):
    env.write_text("DISCORD_TOKEN=second\n", encoding="utf-8")
    with caplog.at_level("INFO"):
        config.reload()
    assert "second" not in caplog.text
    assert "***" in caplog.text


def test_a_db_settings_value_survives_a_sighup_reload(env, monkeypatch,
                                                      db_committed):
    """SIGHUP must not blow away a DB-resolved setting by re-reading .env."""
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    monkeypatch.setenv("DB_STORES", "settings:db")   # 2026-09-30, see callout
    from swingbot.core.db.repositories.settings import settings_repo
    settings_repo().put("MIN_ALERT_CONFIDENCE_LEVEL", 5, updated_by="test")
    env.write_text("DISCORD_TOKEN=second\nMIN_ALERT_CONFIDENCE_LEVEL=2\n",
                   encoding="utf-8")
    config.reload()
    assert config.TOKEN == "second"
    assert config.MIN_ALERT_CONFIDENCE_LEVEL == 5


def test_the_sighup_handler_calls_reload_not_reload_settings():
    """A handler wired to reload_settings would stop picking up secrets --
    the exact regression this test exists to catch."""
    import inspect
    from swingbot import bot_core          # 2026-09-30: handler lives here
    source = inspect.getsource(bot_core._handle_reload_signal)
    assert "config.reload()" in source
    assert "reload_settings" not in source
```

`test_the_sighup_handler_calls_reload_not_reload_settings` reads source text,
which is a blunt instrument — but the alternative is sending a real signal in a
test, and this catches the one substitution that would break the secrets path.

- [ ] **Step 2: Run to verify it passes or find the gap**

```bash
python -m pytest tests/test_sighup_reload.py -q
```

`test_a_db_settings_value_survives_a_sighup_reload` is the one that can fail —
it will pass only because P4-02 layered the DB *above* `os.getenv`. If it
fails, the layering is inverted; fix `_resolve`, not this test.

- [ ] **Step 3: Confirm the handler**

```bash
git grep -n "def _handle_reload_signal" -A 20 swingbot/bot_core.py
```

It must call `config.reload()`. If it does, this task changes no production
code — say so in the commit message rather than inventing an edit.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_sighup_reload.py
python scripts/dev/testrun.py file tests/test_config_reload.py
```

Expected: `0 failed`. (2026-09-30: `tests/test_config.py` does not exist.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_sighup_reload.py   # + swingbot/bot_core.py only if it changed
git commit -m "test(v67): pin SIGHUP as the secrets reload path"
```

---

### Task P4-10: Audit import-time config captures

The spec names this as a risk: any module that captured a `config.XXX` value at
import time holds a stale setting forever. `reload()`'s in-place mutation makes
this a **pre-existing** hazard; the DB-backed path widens the window, because a
value can now change without anyone touching a file.

**Files:**
- Create: `tests/test_no_import_time_config_capture.py`
- Modify: whatever the audit finds (expect a handful of module-level constants)

**Interfaces:**
- Consumes: `config.FIELDS`.
- Produces: `tests/test_no_import_time_config_capture.py` with an explicit
  allowlist of known, reviewed captures.

> **2026-09-30 re-examination:** the scanner below, run against `main` today,
> finds exactly one offender: `swingbot/core/scanning/regime.py:24` captures
> `config.MARKET_REGIME_TICKER`. The worked example is
> `swingbot/core/planning/account.py:67` `_default_config_path()` (not
> `account.py:72`). Everything else in the task holds; `FIELDS` has 148 entries
> today, so the parametrised `hasattr` test is 148 cases.

**This is an audit, not a rewrite.** The deliverable is the test plus fixes for
whatever it catches. If it catches nothing, the deliverable is the test — and
that is a real result, not a wasted task: it is the thing that fails when
someone adds a capture next year.

- [ ] **Step 1: Write the audit**

Create `tests/test_no_import_time_config_capture.py`:

```python
"""No module may capture a FIELDS-backed config value at import time.

config.reload() mutates module globals IN PLACE, which is what makes
`config.XXX` readers see new values without re-importing. A module that does
`FOO = config.FOO` at import time opts out of that: it holds whatever the value
was when it was first imported, forever. That was already true before v67;
DB-backed settings widen the window, because a value can now change without
anyone touching a file.
"""
import ast
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "swingbot"

FIELD_ATTRS = {f.attr for f in config.FIELDS}

# Reviewed and deliberate. Each entry needs a reason, because an allowlist
# without reasons becomes a place to hide the next real one.
ALLOWED = {
    # (module path relative to repo, attribute name): reason
    ("swingbot/config.py", "*"):
        "config.py IS the module these live in",
}


def _module_level_captures(path: pathlib.Path) -> list[tuple[int, str]]:
    """(lineno, attr) for every module-level `X = config.ATTR`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []
    found = []
    for node in tree.body:                      # module level only
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        # `config.FOO`, `app_config.FOO`, `_app_config.FOO`
        if (isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id.endswith("config")
                and value.attr in FIELD_ATTRS):
            found.append((node.lineno, value.attr))
    return found


def _sources():
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_captures_a_config_field_at_import_time():
    offenders = []
    for path in _sources():
        rel = path.relative_to(REPO).as_posix()
        if (rel, "*") in ALLOWED:
            continue
        for lineno, attr in _module_level_captures(path):
            if (rel, attr) in ALLOWED:
                continue
            offenders.append(f"{rel}:{lineno} captures config.{attr}")
    assert not offenders, (
        "import-time config captures found. Read the value inside the "
        "function instead -- config.reload() mutates globals in place and a "
        "captured copy never sees the change:\n  " + "\n  ".join(offenders))


def test_every_allowlist_entry_carries_a_reason():
    assert all(reason.strip() for reason in ALLOWED.values())


def test_every_allowlist_entry_still_points_at_a_real_file():
    for (rel, _attr) in ALLOWED:
        assert (REPO / rel).exists(), f"stale allowlist entry: {rel}"


@pytest.mark.parametrize("attr", sorted(FIELD_ATTRS))
def test_every_field_attr_exists_on_config(attr):
    """A FIELDS entry whose attr does not exist would make the scan above
    silently skip it."""
    assert hasattr(config, attr), attr
```

- [ ] **Step 2: Run it and read what it finds**

```bash
python -m pytest tests/test_no_import_time_config_capture.py -q
```

Expected: a list of offenders, or a clean pass. **Read the list before
changing anything** — some captures are of a `DATA_DIR`-derived path rather
than a `FIELDS` value, and those are a different (already documented) hazard
this test deliberately does not cover.

- [ ] **Step 3: Fix each offender**

The fix is always the same shape: move the read inside the function that uses
it. `swingbot/core/planning/account.py:67`'s `_default_config_path()` is the worked example already in
the codebase, and its docstring explains the failure mode in detail — point at
it in the commit rather than re-explaining.

Where a capture is genuinely correct (a value that must not change for the life
of the process, such as one feeding a `@dataclass` field default), add it to
`ALLOWED` **with its reason**, and say in the commit why a restart is the right
mechanism for that one.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_no_import_time_config_capture.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because any fix here changes a module's
import-time behaviour.

- [ ] **Step 5: Commit**

```bash
git add tests/test_no_import_time_config_capture.py swingbot
git commit -m "test(v67): forbid import-time capture of config fields"
```

---

### Task P4-11: Drop the Docker socket from the settings path

The side effect the spec calls out: pushing a settings change no longer needs
the Docker socket mounted into the admin container, because it no longer needs
a container restart.

**Files:**
- Modify: `docker-compose.yml` (the admin service's socket mount, `:188`)
- Modify: `swingbot/admin/api_v1/system.py` (`save_settings` hot-reload gate;
  `restart_available`) — 2026-09-30
- Modify: `docs/deploy/DOCKER.md` (`DEPLOY_HETZNER.md` has no socket text)
- Test: `tests/admin/test_settings_needs_no_restart.py`

**Interfaces:**
- Consumes: `SettingsListener` (P4-08).
- Produces: no new symbols.

**What is NOT removed.** The "Restart bot container" button, and the `docker`
dependency behind it, stay — they are a deliberate operator action, not part of
the settings path. What changes is that saving a setting stops *needing* them.
Removing the button would be a scope expansion this plan did not ask for.

> **2026-09-30 re-examination — the socket is still on the save path, and
> removing the mount has a user-visible cost.**
>
> - The committed `docker-compose.yml:188` **does** mount
>   `/var/run/docker.sock:ro` on `admin`. `docs/deploy/DOCKER.md:127,135,196`
>   describe it; `DEPLOY_HETZNER.md` does not mention it (no edit needed there).
>   Also stale once this lands: the `swingbot/admin/app.py:26` and
>   `swingbot/config.py:11-15` docstrings and `config_watcher`'s docstring
>   (`loops.py:284`).
> - The PUT route (`api_v1/system.py:save_settings`) calls
>   `_hot_reload_bot_container()` (a Docker `kill(signal="SIGHUP")`) on
>   **every** save. Removing the mount alone leaves every save returning
>   `hot_reload.ok == false` with "needs the Docker socket mount". Gate it:
>   when `stages.reads_db("settings")` and the diff has no sensitive /
>   `_ENV_ONLY` key, skip Docker and return
>   `{"ok": true, "message": "Saved; the bot applies it within 30 s."}` (or
>   whatever P4-08's latency is). A secret change still needs SIGHUP or the
>   30 s `.env` poll. The test below must drive the **route**
>   (`logged_in.put("/api/v1/system/settings", json={"settings": {...}})`),
>   not `helpers.save_settings`, which does not exist.
> - `restart_available` (`system.py:114`) is `docker_sdk is not None` — true
>   whenever the SDK is installed, socket or not — so without the mount the
>   SPA would still offer "Restart bot" (`frontend/src/app/stores/system.store.ts:361`)
>   and it would fail on click. The "degrades to disabled" claim in the compose
>   comment below is false until `restart_available` also checks the socket
>   (e.g. `os.path.exists("/var/run/docker.sock")`).
> - **Partner decision before Step 3:** unmounting takes the restart button
>   away on production. Ask (`AskUserQuestion`) whether to drop the mount now
>   or keep it and only take it off the settings path (the gate above). The
>   compose change reaches production on the next deploy — follow
>   `mirror-prod` if it is applied there by hand.

- [ ] **Step 1: Write the test**

Create `tests/admin/test_settings_needs_no_restart.py`:

```python
"""Saving a setting must not reach for Docker."""
import pytest

from swingbot import config
from swingbot.admin import helpers


@pytest.fixture
def db_stage(monkeypatch, db_committed, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_TOKEN=secret\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield
    config._apply_env()


def test_saving_a_setting_does_not_import_docker(db_stage, monkeypatch):
    import builtins
    real_import = builtins.__import__
    touched = []

    def spy(name, *a, **kw):
        if name == "docker" or name.startswith("docker."):
            touched.append(name)
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", spy)
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    assert touched == [], f"the settings path reached for docker: {touched}"


def test_the_restart_button_still_exists():
    """Not removed -- it is a deliberate operator action, not part of the
    settings path. This test is here so nobody deletes it as 'now unused'."""
    import swingbot.admin.api_v1.system as system
    source = __import__("inspect").getsource(system)
    assert "restart" in source.lower()


def test_the_admin_service_no_longer_mounts_the_docker_socket():
    import pathlib
    import pytest as _pytest
    yaml = _pytest.importorskip("yaml")
    compose = yaml.safe_load(
        (pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml")
        .read_text(encoding="utf-8"))
    mounts = compose["services"]["admin"].get("volumes") or []
    assert not any("docker.sock" in str(m) for m in mounts)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_settings_needs_no_restart.py -q
```

Expected: `test_the_admin_service_no_longer_mounts_the_docker_socket` fails if
the socket is mounted. Check first — it may already be absent from the committed
compose file and mounted only on the VM, in which case the fix is a production
change to mirror back, per `CLAUDE.md`.

- [ ] **Step 3: Remove the mount and document why**

In `docker-compose.yml`, remove the `/var/run/docker.sock` line from the
`admin` service's `volumes:` if present, leaving a comment in its place:

```yaml
      # The Docker socket is NOT mounted. It was here so a settings change
      # could restart the bot container to take effect; as of v67 a settings
      # change is a row write the bot hears about over LISTEN/NOTIFY, so
      # nothing in the settings path needs it. Mounting the host's Docker
      # socket into a web-facing container grants that container root on the
      # host, which is a large amount of blast radius for a convenience the
      # design no longer uses. The "Restart bot container" button degrades to
      # disabled without it, which is exactly the documented behaviour.
```

Update `docs/deploy/DOCKER.md` and `docs/deploy/DEPLOY_HETZNER.md` wherever they
tell an operator to mount it: say a settings change no longer requires it, and
that mounting it is now an opt-in for the restart button alone.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_settings_needs_no_restart.py
python scripts/dev/testrun.py file tests/db/test_compose.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml docs/deploy/DOCKER.md swingbot/admin/api_v1/system.py \
        tests/admin/test_settings_needs_no_restart.py
git commit -m "feat(v67): drop the docker socket from the settings path"
```

---

### Task P4-12: Every settings write is audited

Three write paths now reach the settings table — the admin page (P4-05),
`import_env_text` (P4-07) and the seed script (P4-04). Two of them audit today.
This task makes the audit a property of the write rather than of the caller.

**Files:**
- Modify: `swingbot/admin/helpers.py` (`import_env_text`)
- Test: `tests/admin/test_settings_audit_coverage.py`

**Interfaces:**
- Consumes: `append_settings_audit` (existing), `settings_repo` (P4-01).
- Produces: no new symbols.

> **2026-09-30 re-examination:**
>
> - **Depends on P3-12** (branch `2026-09-29-v67-p3-10-scheduled-jobs`,
>   `swingbot/core/db/repositories/settings_audit.py`:
>   `SettingsAuditRepository.append(changes, ts=None)`, `.recent(n)`,
>   `settings_audit_repo()`), which makes `helpers.append_settings_audit` /
>   `read_settings_audit` write/read by the `settings_audit` store's stage.
>   Merge it before this task: both touch the same `helpers.py` lines. Keep
>   calling the helpers, never the repository directly, so the stage switch
>   stays in one place. The fixture should set both stores
>   (`DB_STORES="settings:db,settings_audit:db"`, via `setenv` too) to prove the
>   audit also lands in Postgres; the `DATA_DIR` patch still covers the
>   `json`-stage JSONL.
> - **Masking already exists on the PUT path:** `settings_diff` masks sensitive
>   values as `•••` (`helpers.MASK` in `api_v1/system.py`), pinned by
>   `tests/admin/test_api_v1_system_settings.py::test_sensitive_values_are_masked_in_the_audit_log`.
>   So `test_a_secret_change_is_audited_without_its_value` is expected to pass,
>   and the import diff below must mask with `•••`, not `***` — two masks for
>   one meaning would split the UI. The simplest correct import diff is
>   `settings_diff(form, existing)` over an effective form built from the
>   applied keys, which gets the masking and "blank = no change" rule for free.
> - Restrict the diff to `FIELDS_BY_KEY` keys: `new_values` starts as
>   `dict(existing)` and includes custom variables. At the db stage the "old"
>   side must come from `helpers.current_values()` (P4-05).
> - `save_settings` is the `system.py` route (see P4-05); the tests drive it
>   through the client. `tests/admin/test_helpers.py` does not exist — run
>   `tests/admin/test_api_v1_system_settings.py` and, once merged,
>   `tests/admin/test_settings_audit_db.py` (P3-12).

**Why not audit inside the repository.** It would look tidier, and it is wrong:
the seed script writes several hundred rows in one go from a file that is
already the record of what they were, and an audit entry per row would bury the
one human change someone is looking for. The audit belongs to the *human*
actions, which is why it stays at the two call sites that have one.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_settings_audit_coverage.py`:

```python
"""Which settings writes are audited, and which deliberately are not."""
import pytest

from swingbot import config
from swingbot.admin import helpers


@pytest.fixture
def db_stage(monkeypatch, db_committed, tmp_path):
    env = tmp_path / ".env"
    env.write_text("DISCORD_TOKEN=secret\nMIN_ALERT_CONFIDENCE_LEVEL=3\n",
                   encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    yield
    config._apply_env()


def test_the_admin_page_write_is_audited(db_stage):
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    assert any(c["key"] == "MIN_ALERT_CONFIDENCE_LEVEL"
               for r in helpers.read_settings_audit() for c in r["changes"])


def test_a_bulk_import_is_audited_as_one_entry(db_stage):
    helpers.import_env_text("MIN_ALERT_CONFIDENCE_LEVEL=5\n"
                            "SESSION_START_HOUR=10\n")
    rows = helpers.read_settings_audit()
    assert len(rows) == 1
    assert {c["key"] for c in rows[0]["changes"]} == {
        "MIN_ALERT_CONFIDENCE_LEVEL", "SESSION_START_HOUR"}


def test_an_import_that_changes_nothing_is_not_audited(db_stage):
    helpers.import_env_text("MIN_ALERT_CONFIDENCE_LEVEL=3\n")
    assert helpers.read_settings_audit() == []


def test_the_audit_records_the_old_and_new_values(db_stage):
    helpers.save_settings({"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
    change = helpers.read_settings_audit()[0]["changes"][0]
    assert str(change["old"]) == "3"
    assert str(change["new"]) == "5"


def test_a_secret_change_is_audited_without_its_value(db_stage):
    helpers.save_settings({"DISCORD_TOKEN": "brand-new-secret"})
    text = str(helpers.read_settings_audit())
    assert "brand-new-secret" not in text, "a secret leaked into the audit log"


def test_the_seed_script_is_deliberately_not_audited(db_stage):
    """It writes what .env already recorded. An entry per row would bury the
    one human change someone is actually looking for."""
    from scripts.db.import_settings import main
    main([])
    assert helpers.read_settings_audit() == []
```

`test_a_secret_change_is_audited_without_its_value` may already pass or already
fail depending on what `append_settings_audit` records today. If it fails, that
is a **pre-existing secret leak into a log file** — fix it here and say so
plainly in the commit; do not treat it as introduced by this plan.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_settings_audit_coverage.py -q
```

Expected: `test_a_bulk_import_is_audited_as_one_entry` fails —
`import_env_text` does not audit.

- [ ] **Step 3: Audit the import**

In `import_env_text`, build the diff from the values it actually applied and
call the existing helper once:

```python
    # One audit entry for the whole paste, not one per key: a bulk import is a
    # single human action, and N entries would bury it.
    diff = [{"key": k, "old": existing.get(k, ""), "new": v}
            for k, v in new_values.items()
            if existing.get(k) != v]
    for entry in diff:
        f = FIELDS_BY_KEY.get(entry["key"])
        if f is not None and f.sensitive:
            entry["old"] = "***" if entry["old"] else ""
            entry["new"] = "***"
    append_settings_audit(diff)
```

Apply the same masking in `save_settings`'s diff if it is not already there.
`config.reload()` already masks sensitive values in its log; the audit file is
the other place a secret could land, and it is the one that persists.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_settings_audit_coverage.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_settings.py
python scripts/dev/testrun.py file tests/admin/test_settings_audit_db.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py tests/admin/test_settings_audit_coverage.py
git commit -m "feat(v67): audit bulk settings imports, mask secrets in the log"
```

---

### Task P4-13: The settings API behaves identically

The SPA's settings page talks to `/api/v1/system/settings*`. None of it may
change. This is the endpoint-level parity check, sitting above the unit tests
that verified each half.

**Files:**
- Test: `tests/admin/test_settings_api_parity.py`

**Interfaces:**
- Consumes: the existing v1 settings endpoints (`grep -n "system/settings"
  swingbot/admin/api_v1/system.py`).
- Produces: nothing.

> **2026-09-30 re-examination:** the SPA settings workspace is
> `frontend/src/app/workspaces/system/settings-tab.ts` (+ `settings-grouping.ts`,
> store `frontend/src/app/stores/system.store.ts`, models
> `frontend/src/app/api/models.ts:877-916`); it needs no change if this test
> passes. The original test body used POST and an unwrapped payload and an
> `authed_client` helper that never existed — it is rewritten below against
> the real contract.

- [ ] **Step 1: Write the test**

Create `tests/admin/test_settings_api_parity.py`:

```python
"""Same requests, same responses, either storage backend.

The endpoint contract is what the SPA is written against; the storage swap is
supposed to be invisible to it. Every assertion here compares the two stages
against each other rather than against a hardcoded shape, so it keeps meaning
something when the settings page grows a field.

2026-09-30: rewritten against the real routes -- GET/PUT
/api/v1/system/settings (PUT body {"settings": {...}}, a bad value is a 400),
GET .../export, and the `admin_app`/`client` fixtures in tests/admin/conftest.py
(there is no `authed_client` helper). DB_STORES is read live by `stages`, so one
client can be flipped between stages mid-test.
"""
import pytest

from swingbot import config

_LOGIN = {"username": "admin", "password": "admin"}
STAGES = ("", "settings:db")


@pytest.fixture(autouse=True)
def no_docker(monkeypatch):
    monkeypatch.setattr("swingbot.admin.helpers._hot_reload_bot_container",
                        lambda: (True, "reloaded"))


@pytest.fixture
def at(client, tmp_path, monkeypatch, db_committed):
    (tmp_path / ".env").write_text("DISCORD_TOKEN=secret\n"
                                   "MIN_ALERT_CONFIDENCE_LEVEL=3\n",
                                   encoding="utf-8")
    client.post("/api/v1/session", json=_LOGIN)

    def _stage(stage):
        monkeypatch.setattr(config, "DB_STORES", stage)
        monkeypatch.setenv("DB_STORES", stage)
        return client
    yield _stage
    config._apply_env()


def _keys(payload):
    return [f["key"] for s in payload["sections"] for f in s["fields"]]


def _value(payload, key):
    return next(f["value"] for s in payload["sections"] for f in s["fields"]
                if f["key"] == key)


def test_get_settings_returns_the_same_field_set(at):
    a = at("").get("/api/v1/system/settings").get_json()
    b = at("settings:db").get("/api/v1/system/settings").get_json()
    assert _keys(a) == _keys(b)


def test_get_settings_masks_secrets_at_both_stages(at):
    for stage in STAGES:
        body = at(stage).get("/api/v1/system/settings").get_data(as_text=True)
        assert "secret" not in body


def test_put_settings_returns_the_same_status_and_shape(at):
    payload = {"settings": {"MIN_ALERT_CONFIDENCE_LEVEL": "5"}}
    a = at("").put("/api/v1/system/settings", json=payload)
    b = at("settings:db").put("/api/v1/system/settings", json=payload)
    assert a.status_code == b.status_code == 200
    assert set(a.get_json()) == set(b.get_json())


def test_a_saved_value_reads_back_at_both_stages(at):
    for stage in STAGES:
        c = at(stage)
        c.put("/api/v1/system/settings",
              json={"settings": {"MIN_ALERT_CONFIDENCE_LEVEL": "5"}})
        body = c.get("/api/v1/system/settings").get_json()
        assert str(_value(body, "MIN_ALERT_CONFIDENCE_LEVEL")) == "5", stage


def test_the_export_endpoint_returns_the_same_keys(at):
    a = at("").get("/api/v1/system/settings/export").get_data(as_text=True)
    b = at("settings:db").get(
        "/api/v1/system/settings/export").get_data(as_text=True)
    assert sorted(l.split("=")[0] for l in a.splitlines() if l) == \
           sorted(l.split("=")[0] for l in b.splitlines() if l)


def test_an_invalid_value_is_refused_the_same_way(at):
    payload = {"settings": {"MIN_ALERT_CONFIDENCE_LEVEL": "not-a-number"}}
    a = at("").put("/api/v1/system/settings", json=payload)
    b = at("settings:db").put("/api/v1/system/settings", json=payload)
    assert a.status_code == b.status_code == 400
```

The endpoint paths and payload shape above are the plausible ones — **read
`swingbot/admin/api_v1/system.py` and match the real routes and bodies before
running this.** A parity test written against endpoints that do not exist tests
nothing and passes for the wrong reason. (2026-09-30: matched against `main` —
`get_settings` `:208`, `save_settings` `:231`, `export_settings`, and the
document shape `{"sections": [{"fields": [...]}], "audit",
"restart_available"}`. The `hot_reload` message legitimately differs between
stages after P4-11, which is why the PUT test compares keys, not bodies.)

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/admin/test_settings_api_parity.py
```

Expected: `0 failed`. A failure here is a real contract break — the SPA is not
supposed to notice this migration.

- [ ] **Step 3: Commit**

```bash
git add tests/admin/test_settings_api_parity.py
git commit -m "test(v67): pin settings API parity across storage backends"
```

---

### Task P4-14: Part 4 verification

**Files:**
- Create: `tests/db/test_part4_exit.py`

**Interfaces:**
- Consumes: everything in Part 4.
- Produces: nothing.

> **2026-09-30 re-examination:** the first test calls `helpers.save_settings`,
> which does not exist — drive the PUT route through the `admin_app`/`client`
> fixtures instead (see P4-13's `at` fixture), wrapping the body as
> `{"settings": {...}}` and sending only non-checkbox keys (the route's
> `_validate` rejects `"y"` for number/select fields with a 400, which would
> make the test pass vacuously — assert the PUT returns 200, using each field's
> `default` or a valid option). `leaked` must also exclude `_ENV_ONLY` keys
> (`DB_STORES`, P4-02). Every `monkeypatch.setattr(config, "DB_STORES", ...)`
> needs a matching `setenv`. Add `tests/infra/test_logger_names.py` and
> `tests/db/test_migrations.py` to Step 2's run (single head off `p6_001`).
> Per CLAUDE.md the full suite runs once per plan as its final task; this
> part's step stays `fast` plus the targeted slow files below.

- [ ] **Step 1: Write the exit test**

Create `tests/db/test_part4_exit.py`:

```python
"""Checks that only make sense once every Part 4 task has landed."""
import pytest

from swingbot import config


def test_no_sensitive_field_can_reach_the_settings_table(db_committed,
                                                          monkeypatch, tmp_path):
    """The single most important property in this part, asserted against every
    write path at once rather than one test per path."""
    from swingbot.admin import helpers
    from swingbot.core.db.repositories.settings import settings_repo
    from scripts.db.import_settings import main

    env = tmp_path / ".env"
    env.write_text("".join(f"{f.key}=x\n" for f in config.FIELDS),
                   encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "settings:db")

    sensitive = {f.key for f in config.FIELDS if f.sensitive}

    main([])                                              # seed script
    helpers.save_settings({f.key: "y" for f in config.FIELDS})   # admin page
    helpers.import_env_text("".join(f"{f.key}=z\n" for f in config.FIELDS))

    leaked = sensitive & set(settings_repo().all_settings())
    assert not leaked, f"secrets in the settings table: {sorted(leaked)}"
    config._apply_env()


def test_every_non_sensitive_field_is_resolvable_from_the_database(
        db_committed, monkeypatch):
    """A field the resolver cannot source from a row is a field the admin page
    can appear to save and the bot will never see."""
    monkeypatch.setattr(config, "DB_STORES", "settings:db")
    from swingbot.core.db.repositories.settings import settings_repo
    non_sensitive = [f for f in config.FIELDS if not f.sensitive]
    for f in non_sensitive:
        settings_repo().put(f.key, f.default or "1", updated_by="exit-test")
    db = config._db_settings()
    missing = [f.key for f in non_sensitive if f.key not in db]
    assert not missing, f"not resolvable from the database: {missing}"
    config._apply_env()


def test_reload_settings_exists_and_reload_still_reads_env():
    assert callable(config.reload_settings)
    assert callable(config.reload)


def test_db_stores_is_not_promoted_in_this_checkout():
    from swingbot.core.db import stages
    assert "settings" not in stages.parse(config.DB_STORES), (
        "DB_STORES promotes settings in this checkout; that is a local "
        "setting, not something to commit")
```

- [ ] **Step 2: Run everything Part 4 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part4_exit.py
python scripts/dev/testrun.py fast
python -m pytest tests/db/ tests/admin/ tests/infra/ tests/test_config*.py \
    tests/commands/test_config_watcher_*.py tests/test_sighup_reload.py -q
```

Expected: `0 failed`, `0 xfailed` on all three. The last covers the `slow`
listener tests the fast tier skips.

- [ ] **Step 3: Commit**

```bash
git add tests/db/test_part4_exit.py
git commit -m "test(v67): pin Part 4 exit criteria"
```

---

**Part 4 exit criteria are in
`2026-08-29-v67-json-to-postgres_4a-settings-resolution.md`.** Confirm all six
before treating this part as done.
