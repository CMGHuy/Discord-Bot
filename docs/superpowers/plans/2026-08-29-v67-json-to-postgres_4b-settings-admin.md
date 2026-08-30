# v67 — Part 4: Settings (tasks P4-08…P4-14)

> Continuation of `2026-08-29-v67-json-to-postgres_4a-settings-resolution.md`.
> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints and the `_4a` file before starting any task here** — the
> Parallelisation map, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P4-08: The bot reloads on NOTIFY

A settings row changes, the trigger fires, the bot's listener calls
`config.reload_settings()`. No SIGHUP, no Docker socket, no polling.

**Files:**
- Create: `swingbot/core/infra/settings_listener.py`
- Modify: `bot.py` (start it alongside the other background tasks)
- Test: `tests/infra/test_settings_listener.py`

**Interfaces:**
- Consumes: `notify.listen` (P1-13), `config.reload_settings` (P4-03),
  `stages`.
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

log = logging.getLogger("swing-bot.settings")

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

In `bot.py`, beside the other background startup (find the `on_ready` /
`setup_hook` block with `grep -n "async def on_ready\|setup_hook" bot.py`):

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
python scripts/dev/testrun.py file tests/test_bot_startup.py
```

Expected: `0 failed`. The listener tests are `slow` (they commit), so the fast
tier skips them and raw pytest is the right call here.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/infra/settings_listener.py bot.py \
        tests/infra/test_settings_listener.py
git commit -m "feat(v67): reload config when a settings row changes"
```

---

### Task P4-09: SIGHUP still works, for secrets

SIGHUP is retained for `.env` secret changes. This task is the test that says
so, plus the one-line change that makes the handler call the right function.

**Files:**
- Modify: `bot.py` (the SIGHUP handler — `grep -n "SIGHUP" bot.py`)
- Test: `tests/test_sighup_reload.py`

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
    import bot
    source = inspect.getsource(bot)
    handler = source[source.index("SIGHUP"):]
    assert "config.reload()" in handler[:2000]
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
grep -n "SIGHUP" -A 8 bot.py
```

It must call `config.reload()`. If it does, this task changes no production
code — say so in the commit message rather than inventing an edit.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_sighup_reload.py
python scripts/dev/testrun.py file tests/test_config.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_sighup_reload.py
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
it. `account.py:72`'s `_default_config_path()` is the worked example already in
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
- Modify: `docker-compose.yml` (the admin service's socket mount)
- Modify: `docs/deploy/DOCKER.md`, `docs/deploy/DEPLOY_HETZNER.md`
- Test: `tests/admin/test_settings_needs_no_restart.py`

**Interfaces:**
- Consumes: `SettingsListener` (P4-08).
- Produces: no new symbols.

**What is NOT removed.** The "Restart bot container" button, and the `docker`
dependency behind it, stay — they are a deliberate operator action, not part of
the settings path. What changes is that saving a setting stops *needing* them.
Removing the button would be a scope expansion this plan did not ask for.

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
git add docker-compose.yml docs/deploy/DOCKER.md docs/deploy/DEPLOY_HETZNER.md \
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
python scripts/dev/testrun.py file tests/admin/test_helpers.py
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

- [ ] **Step 1: Write the test**

Create `tests/admin/test_settings_api_parity.py`:

```python
"""Same requests, same responses, either storage backend.

The endpoint contract is what the SPA is written against; the storage swap is
supposed to be invisible to it. Every assertion here compares the two stages
against each other rather than against a hardcoded shape, so it keeps meaning
something when the settings page grows a field.
"""
import pytest

from swingbot import config


def _client(monkeypatch, tmp_path, stage):
    env = tmp_path / ".env"
    if not env.exists():
        env.write_text("DISCORD_TOKEN=secret\n"
                       "MIN_ALERT_CONFIDENCE_LEVEL=3\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", stage)
    from tests.admin.conftest import authed_client      # existing helper
    return authed_client()


@pytest.fixture
def both(monkeypatch, tmp_path, db_committed):
    def _make(stage):
        return _client(monkeypatch, tmp_path / stage.replace(":", "_"), stage)
    return _make


def test_get_settings_returns_the_same_field_set(both):
    a = both("").get("/api/v1/system/settings").get_json()
    b = both("settings:db").get("/api/v1/system/settings").get_json()
    assert set(_keys(a)) == set(_keys(b))


def _keys(payload):
    """Field keys out of whatever shape the endpoint returns."""
    if isinstance(payload, dict) and "fields" in payload:
        return [f["key"] for f in payload["fields"]]
    if isinstance(payload, dict):
        return list(payload)
    return [f["key"] for f in payload]


def test_get_settings_masks_secrets_at_both_stages(both):
    for stage in ("", "settings:db"):
        body = both(stage).get("/api/v1/system/settings").get_data(as_text=True)
        assert "secret" not in body


def test_post_settings_returns_the_same_status(both):
    payload = {"MIN_ALERT_CONFIDENCE_LEVEL": "5"}
    a = both("").post("/api/v1/system/settings", json=payload)
    b = both("settings:db").post("/api/v1/system/settings", json=payload)
    assert a.status_code == b.status_code


def test_a_saved_value_reads_back_at_both_stages(both):
    for stage in ("", "settings:db"):
        c = both(stage)
        c.post("/api/v1/system/settings",
               json={"MIN_ALERT_CONFIDENCE_LEVEL": "5"})
        body = c.get("/api/v1/system/settings").get_data(as_text=True)
        assert "5" in body


def test_the_export_endpoint_returns_the_same_keys(both):
    a = both("").get("/api/v1/system/settings/export").get_data(as_text=True)
    b = both("settings:db").get(
        "/api/v1/system/settings/export").get_data(as_text=True)
    assert sorted(l.split("=")[0] for l in a.splitlines() if l) == \
           sorted(l.split("=")[0] for l in b.splitlines() if l)


def test_an_invalid_value_is_refused_the_same_way(both):
    payload = {"MIN_ALERT_CONFIDENCE_LEVEL": "not-a-number"}
    a = both("").post("/api/v1/system/settings", json=payload)
    b = both("settings:db").post("/api/v1/system/settings", json=payload)
    assert a.status_code == b.status_code
```

The endpoint paths and payload shape above are the plausible ones — **read
`swingbot/admin/api_v1/system.py` and match the real routes and bodies before
running this.** A parity test written against endpoints that do not exist tests
nothing and passes for the wrong reason.

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
python -m pytest tests/db/ tests/admin/ tests/infra/ tests/test_config*.py -q
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
