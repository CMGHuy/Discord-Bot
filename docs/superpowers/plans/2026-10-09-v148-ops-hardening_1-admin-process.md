# v148 Ops hardening. Implementation Plan, part 1 (admin process: single worker, gunicorn, login hardening, config keys)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief OH3` or `grep -n "^### Task OH3:" -A 400 docs/superpowers/plans/2026-10-09-v148-ops-hardening_1-admin-process.md`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md`](../specs/2026-10-09-v148-ops-hardening-design.md) (sections "O1 — Production WSGI server", "O2 — Constant-time checks and a login limiter", the O4 "Config" table, "Testing")
**Index:** [`2026-10-09-v148-ops-hardening_0-index.md`](2026-10-09-v148-ops-hardening_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 2–5.

**Tasks in this part:** OH1, OH2, OH3, OH4, OH5. OH1 lands first (read-only gate; a blocker stops the plan). Then OH2, OH3 and OH5 are disjoint and may run in parallel (at most 2 implementers at once, together with part 2's OH6). OH4 waits for OH3 (it consumes the `rate_limited` code and body shape).

Conventions used in every task (from the index's `## Where to work`):

- `$R` = `/home/user/Discord-Bot` (main tree, never edited by an implementation task). `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening` (branch `2026-10-09-v148-ops-hardening`).
- Never `cd`. Use `git -C $WT ...`, `python $WT/scripts/dev/testrun.py file tests/...` (test paths resolve against `$WT`) and `npm --prefix $WT/frontend ...`.
- After every commit: `git -C $R status --short` prints nothing new (the main tree is unchanged). OH1 is the one exception: its finding is written to the index on `$R` and committed by the controller.
- Every new or changed function stays < complexity 15: `python -m radon cc -s -n C <files>` prints nothing (`python -m pip install radon` first if `python -m radon` fails; no `requirements.txt` change).

# Phase A — Admin process

### Task OH1: Single-worker verification (read-only)

**Model:** sonnet — read-only review across five admin modules with a written verdict; judgement, no code.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` (the `## Progress` block only, on `$R`)

**Why:** spec O1, last bullet: before any gunicorn work, confirm that nothing in the admin process depends on more than one worker and nothing breaks with exactly one worker, under `gunicorn -w 1 -k gthread --threads 16` with `preload_app = False` (the app module is imported in the worker, after the master has started, and never in the master). The spec's binding reasons for one worker are the in-memory login limiter (OH3), the in-memory admin-side swallowed counter (OH6) and the single SSE `id:` sequence (`broker.py`). This task checks the converse: that one worker, 16 threads, with the app imported in a worker rather than by `python admin_ui.py`, breaks nothing. If it finds a blocker, the plan stops.

No code changes and no tests. Nothing is committed on the branch.

- [ ] **Step 0: Create the worktree (first task of the plan only)**

Invoke the `worktree-lifecycle` skill, then:

```bash
git -C /home/user/Discord-Bot worktree list
git -C /home/user/Discord-Bot worktree add -b 2026-10-09-v148-ops-hardening /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening main
```

If `git worktree list` already shows the worktree, reuse it and resume at the first uncommitted task (`git -C $WT log --oneline main..HEAD`).

- [ ] **Step 1: Read the five places the spec names, plus the two background threads**

Read each of these, in `$WT` (all short reads; never read a plan file whole):

```bash
sed -n 1,120p  $WT/swingbot/admin/events/broker.py
sed -n 280,300p $WT/swingbot/admin/events/broker.py
sed -n 1,140p  $WT/swingbot/admin/events/db_listener.py
sed -n 1,140p  $WT/swingbot/admin/events/stream.py
sed -n 60,90p  $WT/swingbot/admin/app.py
sed -n 265,300p $WT/swingbot/admin/helpers.py
sed -n 200,275p $WT/swingbot/admin/jobs.py
git -C $WT grep -n "threading.Thread\|Thread(\|lru_cache\|^_[A-Z_]* = \|global " -- swingbot/admin
```

- [ ] **Step 2: Answer each question in writing (scratch notes, not a file in the repo)**

For every item, record yes/no and the `path:line` evidence:

1. **Secret key** (`app.py:76` → `helpers._load_or_create_secret_key`, `helpers.py:270`): with one worker the file is created at most once per boot, by the one process that imports the app. Confirm nothing else (the master) imports `swingbot.admin.app` under `preload_app = False`, so there is no create-create race. With 16 threads, confirm creation happens at import time (before any request thread exists), not lazily per request.
2. **SSE broker** (`broker.py:285-295` `get_broker`, `MAX_CONNECTIONS = 8` at `broker.py:58`): the singleton is created under `_BROKER_LOCK`, so 16 request threads share one broker and one `id:` sequence. Confirm `MAX_CONNECTIONS` (8) is below the thread count (16), so 8 open streams leave 8 threads for ordinary requests.
3. **DB listener thread** (`db_listener.py:98-102` `start`): find where `start()` is called (`git -C $WT grep -n "\.start()" -- swingbot/admin`). It must start in the process that serves requests. With `preload_app = False` that is the worker. Confirm it is not started at import time of a module the gunicorn *master* imports. The master imports only `deploy/gunicorn.conf.py` and gunicorn itself, so a thread started at app import time is in the worker, which is correct.
4. **Job watcher threads** (`jobs.py:270`, `threading.Thread(target=_watch, daemon=True)`): daemon threads spawned per job inside the worker. Confirm the job state they write is on disk or in the DB (`_write_jobs`), not only in memory that a second worker would miss. With one worker this is moot, but note it.
5. **Module-level caches** (`api_v1/versions.py:42,61` `lru_cache(maxsize=1)`, plus any `_[A-Z_]* =` globals the grep finds): confirm each is thread-safe for reads under 16 threads, or is guarded by a lock. `lru_cache` is thread-safe; a plain dict mutated from request threads without a lock is a finding.
6. **`gthread` timeouts:** confirm a long-lived SSE response (`stream.py`, `PING_INTERVAL = 20.0`) does not block the worker heartbeat. Under `gthread` the heartbeat runs in the main worker thread, independent of request threads. A ping every 20 s is well under `timeout = 60`.
7. **Before-request hook** `_reload_env_if_changed` (`app.py`, after `require_auth`): it calls `config.auto_reload_if_changed()` from request threads. Confirm it is safe with 16 concurrent threads, as it already is under `app.run(threaded=True)`, which is Flask's default and also threaded. A difference from `app.run` here is a finding.
8. **`app.main()` side effects** that gunicorn skips: `yf_safe.set_default_lock_timeout(...)` (`app.py`, `main()`). This is already handled by index Global Constraint 5 (`admin_wsgi.py` replicates it). Confirm `main()` does nothing else besides `app.run`.

- [ ] **Step 3: Record the finding in the index on `$R`**

If every answer is safe, replace the `## Progress` body line `Not started. OH1 records its single-worker finding here before OH2 starts.` in `$R/docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` with one line of this shape (fill in the evidence; keep it to one line):

```markdown
- OH1 (2026-10-DD): one worker safe — secret key created at app import in the worker only (helpers.py:270, preload_app False); broker singleton under _BROKER_LOCK, 8-stream cap < 16 threads (broker.py:58,289); DB listener started in the worker (<path:line>); job watchers persist via _write_jobs (jobs.py:<n>); caches thread-safe (<list>); app.main() extra = yf lock timeout only (covered by admin_wsgi).
```

Use `Edit` on that one line, not `sed -i`. Do not touch any other section of the index.

If any answer is **not** safe, do not edit the index beyond writing `- OH1 (2026-10-DD): BLOCKED — <one sentence, path:line>` and stop. Report `BLOCKED: <the finding>` to the controller. The partner decides; OH2 must not start.

- [ ] **Step 4: Hand the index change to the controller**

```bash
git -C /home/user/Discord-Bot diff --stat -- docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md
```

The diff shows exactly one changed line in `## Progress`. The controller commits it on `main` with message `docs(plans): v148 OH1 single-worker finding`. The implementer does not commit, and nothing is committed on the branch for OH1.

### Task OH2: gunicorn launch inside the image

**Model:** sonnet — new launcher and conf modules plus logging wiring, each with behaviour tests; touches process start-up, so not haiku.

**Files:**
- Create: `admin_wsgi.py`
- Create: `deploy/gunicorn.conf.py`
- Modify: `admin_ui.py`
- Modify: `requirements.txt`
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (§ Rolling back and § Point-in-time rollback notes only; OH19 adds the cron row later)
- Create: `tests/admin/test_gunicorn_conf.py`
- Modify: `tests/admin/test_admin_logging.py`

**Why:** spec O1. `python admin_ui.py` stays the only command compose (`docker-compose.yml:191`) and CI (`.github/workflows/deploy.yml:605`) ever run. Inside the image, the first thing `__main__` does is `_maybe_exec_gunicorn()`: off Windows, when `find_spec("gunicorn")` finds it, the process `os.execv`s `sys.executable -m gunicorn -c <root>/deploy/gunicorn.conf.py admin_wsgi:app`. This happens before `setup_logging()` and `record_boot("admin")`, so neither runs twice: `admin_wsgi` does both in the worker. Everywhere else (Windows dev, a pre-v148 image without gunicorn) it falls through to `app.run`, unchanged. A rollback image under today's compose file therefore still boots.

Contracts other tasks rely on (ledger): `admin_ui._gunicorn_argv(root: Path) -> list[str]`, `admin_ui._maybe_exec_gunicorn() -> None`, `admin_wsgi.app`, and the conf globals `bind, workers=1, worker_class="gthread", threads=16, timeout=60, graceful_timeout=5, keepalive=5, accesslog="-", preload_app=False`. OH15's ratchet scans `admin_wsgi.py` (repo-root `*.py`). It contains no `except Exception`, so it adds nothing to the baseline.

Logging under gunicorn: gunicorn's `glogging.Logger` sets `propagate = False` on `gunicorn.access` and `gunicorn.error` and writes both to stdout/stderr through its own handlers (`accesslog = "-"`). The admin's request lines therefore reach `logs/admin.log` only through a handler attached to those loggers. `setup_logging` attaches the root's logsetup-owned **file** handler and nothing else. Attaching the console handler too would print every request twice in `docker logs`. Because `configure_logging` closes and replaces its owned handlers on every call, `setup_logging` first removes the handlers it attached on a previous call.

`admin_wsgi.py` must also call `yf_safe.set_default_lock_timeout(float(config.ADMIN_YF_LOCK_TIMEOUT_SECONDS))` (index Global Constraint 5): gunicorn never runs `app.main()`, and without this call the v132 lock-wait safeguard is lost.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/admin/test_gunicorn_conf.py`:

```python
"""v148 O1: the admin's production server is chosen inside the image.

gunicorn itself is never imported here. It needs fcntl, which Windows lacks,
so the conf is loaded with runpy as the plain Python it is, and
`_maybe_exec_gunicorn` is driven with `find_spec`, `sys.platform` and
`os.execv` patched.
"""
import ast
import importlib
import importlib.util
import logging
import runpy
import sys
from pathlib import Path

import pytest

import admin_ui
from swingbot.admin.events import broker

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "deploy" / "gunicorn.conf.py"


@pytest.fixture
def restore_gunicorn_loggers():
    """setup_logging attaches handlers to gunicorn's loggers; put them back."""
    saved = {}
    for name in admin_ui.GUNICORN_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (logger.handlers[:], logger.level, logger.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def _conf(monkeypatch, **env) -> dict:
    for key in ("ADMIN_HOST", "ADMIN_PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(str(CONF))


# --- deploy/gunicorn.conf.py ----------------------------------------------

def test_conf_runs_one_gthread_worker_with_room_for_every_sse_stream(monkeypatch):
    conf = _conf(monkeypatch)
    assert conf["workers"] == 1
    assert conf["worker_class"] == "gthread"
    # The 8-stream SSE cap plus as many threads again for ordinary requests.
    assert conf["threads"] >= 2 * broker.MAX_CONNECTIONS
    # The broker's listener thread must start in the worker, not the master.
    assert conf["preload_app"] is False
    assert (conf["timeout"], conf["graceful_timeout"], conf["keepalive"]) == (60, 5, 5)
    assert conf["accesslog"] == "-"


def test_conf_binds_where_app_run_did(monkeypatch):
    assert _conf(monkeypatch)["bind"] == "0.0.0.0:1234"
    assert _conf(monkeypatch, ADMIN_HOST="127.0.0.1", ADMIN_PORT="8080")["bind"] == "127.0.0.1:8080"
    # An empty value in .env means "unset", as os.getenv(...) or default does in app.main().
    assert _conf(monkeypatch, ADMIN_HOST="", ADMIN_PORT="")["bind"] == "0.0.0.0:1234"


def test_conf_imports_nothing_but_os():
    tree = ast.parse(CONF.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0]
                for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {(node.module or "").split(".")[0]
                 for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= {"os"}


# --- admin_ui launcher ------------------------------------------------------

def test_gunicorn_argv_names_the_conf_and_the_wsgi_module(tmp_path):
    assert admin_ui._gunicorn_argv(tmp_path) == [
        sys.executable, "-m", "gunicorn",
        "-c", str(tmp_path / "deploy" / "gunicorn.conf.py"),
        "admin_wsgi:app",
    ]


def test_the_files_the_argv_names_ship_in_the_repo():
    argv = admin_ui._gunicorn_argv(ROOT)
    assert Path(argv[4]).is_file()
    assert (ROOT / "admin_wsgi.py").is_file()


def _patch_exec(monkeypatch, *, platform: str, installed: bool) -> list:
    calls = []
    monkeypatch.setattr(admin_ui.sys, "platform", platform)
    monkeypatch.setattr(admin_ui, "find_spec",
                        lambda name: object() if installed and name == "gunicorn" else None)
    monkeypatch.setattr(admin_ui.os, "execv", lambda path, argv: calls.append((path, list(argv))))
    return calls


def test_execs_gunicorn_when_the_image_has_it(monkeypatch):
    calls = _patch_exec(monkeypatch, platform="linux", installed=True)
    admin_ui._maybe_exec_gunicorn()
    argv = admin_ui._gunicorn_argv(Path(admin_ui.__file__).resolve().parent)
    assert calls == [(argv[0], argv)]


def test_falls_through_when_gunicorn_is_absent(monkeypatch):
    """A pre-v148 image, or a dev machine without it: today's app.run path."""
    calls = _patch_exec(monkeypatch, platform="linux", installed=False)
    admin_ui._maybe_exec_gunicorn()
    assert calls == []


def test_falls_through_on_windows_even_when_installed(monkeypatch):
    calls = _patch_exec(monkeypatch, platform="win32", installed=True)
    admin_ui._maybe_exec_gunicorn()
    assert calls == []


def test_main_block_without_gunicorn_boots_app_run_once(admin_app, tmp_path, monkeypatch,
                                                        restore_root_logging,
                                                        restore_gunicorn_loggers):
    from swingbot import config
    from swingbot.admin import app as app_mod
    from swingbot.core.infra import deploy_marker

    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(tmp_path / "admin.log"))
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a: None if name == "gunicorn" else real_find_spec(name, *a))
    events = []
    monkeypatch.setattr(admin_ui.os, "execv", lambda *a: events.append("execv"))
    monkeypatch.setattr(deploy_marker, "record_boot", lambda component: events.append(f"boot:{component}"))
    monkeypatch.setattr(app_mod, "main", lambda: events.append("main"))

    runpy.run_path(str(ROOT / "admin_ui.py"), run_name="__main__")

    assert events == ["boot:admin", "main"]


# --- admin_wsgi -------------------------------------------------------------

def test_admin_wsgi_logs_boots_and_bounds_the_yf_lock_before_exposing_the_app(admin_app, monkeypatch):
    from swingbot import config
    from swingbot.core.infra import deploy_marker
    from swingbot.core.marketdata import yf_safe

    events = []
    monkeypatch.setattr(admin_ui, "setup_logging", lambda: events.append("logging"))
    monkeypatch.setattr(deploy_marker, "record_boot", lambda component: events.append(f"boot:{component}"))
    monkeypatch.setattr(yf_safe, "set_default_lock_timeout", lambda s: events.append(f"lock:{s}"))
    monkeypatch.setattr(config, "ADMIN_YF_LOCK_TIMEOUT_SECONDS", 7)
    sys.modules.pop("admin_wsgi", None)
    try:
        wsgi = importlib.import_module("admin_wsgi")
        assert wsgi.app is sys.modules["swingbot.admin.app"].app
        assert events == ["logging", "boot:admin", "lock:7.0"]
    finally:
        sys.modules.pop("admin_wsgi", None)
```

Append to `$WT/tests/admin/test_admin_logging.py`. Add `import pytest` to the import block (it currently imports `logging`, `re`, `RotatingFileHandler`, `admin_ui`, `config`), then append at the end of the file:

```python
@pytest.fixture
def restore_gunicorn_loggers():
    """setup_logging attaches handlers to gunicorn's loggers; put them back."""
    saved = {}
    for name in admin_ui.GUNICORN_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (logger.handlers[:], logger.level, logger.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def test_gunicorn_request_lines_reach_admin_log_under_a_warning_level(
        tmp_path, monkeypatch, restore_root_logging, restore_gunicorn_loggers):
    """v148 O1: under gunicorn the Logs page keeps showing admin requests."""
    path = tmp_path / "admin.log"
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(path))
    monkeypatch.setattr(config, "LOG_LEVEL", "WARNING")
    access = logging.getLogger("gunicorn.access")
    access.propagate = False   # what gunicorn's glogging.Logger sets on both loggers

    admin_ui.setup_logging()

    for name in admin_ui.GUNICORN_LOGGERS:
        assert logging.getLogger(name).getEffectiveLevel() == logging.INFO
    access.info('10.0.0.1 - - "GET /api/v1/health HTTP/1.1" 200 51')
    _owned_file_handler(restore_root_logging).flush()
    assert re.search(r"\[INFO\] \[-\] gunicorn\.access: .*GET /api/v1/health", path.read_text())


def test_setting_up_twice_leaves_one_live_file_handler_on_each_gunicorn_logger(
        tmp_path, monkeypatch, restore_root_logging, restore_gunicorn_loggers):
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(tmp_path / "admin.log"))

    admin_ui.setup_logging()
    admin_ui.setup_logging()

    live = _owned_file_handler(restore_root_logging)
    for name in admin_ui.GUNICORN_LOGGERS:
        owned = [h for h in logging.getLogger(name).handlers
                 if getattr(h, "_swingbot_logsetup", False)]
        # Only the file handler: gunicorn already writes these to stdout itself,
        # and the console handler would print every request twice.
        assert owned == [live]
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/admin/test_gunicorn_conf.py
python $WT/scripts/dev/testrun.py file tests/admin/test_admin_logging.py
```

Expected: `test_gunicorn_conf.py` fails at collection or per test (`deploy/gunicorn.conf.py` missing, `admin_ui` has no `GUNICORN_LOGGERS` / `_gunicorn_argv` / `find_spec`). In `test_admin_logging.py`, the fixture errors with `AttributeError: module 'admin_ui' has no attribute 'GUNICORN_LOGGERS'`, while the four existing tests still pass.

- [ ] **Step 3: Create `deploy/gunicorn.conf.py`**

Create `$WT/deploy/gunicorn.conf.py`:

```python
"""gunicorn settings for the admin container (v148, spec O1).

Loaded by `admin_ui._maybe_exec_gunicorn` (`gunicorn -c deploy/gunicorn.conf.py
admin_wsgi:app`). Plain Python on purpose: it never imports gunicorn, so
tests/admin/test_gunicorn_conf.py can load it with runpy on any OS.

ONE worker is a requirement, not a tuning choice: the login limiter
(swingbot/admin/login_limiter.py), the admin-side swallowed-error counter and
the SSE broker's event sequence all live in this process's memory. Two
workers would split each of them in two (OH1's finding is in the plan's
Progress block).

ADMIN_HOST / ADMIN_PORT come from the container environment (compose's
env_file), exactly as app.main() reads them. They are read once at launch,
so a bind change needs a container restart, not a SIGHUP (as with app.run).
"""
import os

bind = f"{os.environ.get('ADMIN_HOST') or '0.0.0.0'}:{os.environ.get('ADMIN_PORT') or 1234}"
workers = 1
worker_class = "gthread"
# The broker's 8-stream SSE cap (broker.MAX_CONNECTIONS) plus 8 threads for
# ordinary requests. The cap stays at 8.
threads = 16
timeout = 60
# Open SSE streams would otherwise hold every restart for the 30 s default;
# the SPA's EventSource reconnects on its own.
graceful_timeout = 5
keepalive = 5
# Request lines to stdout (docker logs); admin_ui.setup_logging also routes
# the gunicorn.access logger into logs/admin.log for the Logs page.
accesslog = "-"
# The app module (and the DB LISTEN thread it starts) must load in the
# worker, never in the master.
preload_app = False
```

- [ ] **Step 4: Rewrite `admin_ui.py`**

Replace the whole of `$WT/admin_ui.py` with:

```python
"""
Admin web UI -- entry point. The actual implementation lives at
swingbot/admin/app.py; this file configures logging and launches it.

Run with: python admin_ui.py
Listens on ADMIN_HOST:ADMIN_PORT (default 0.0.0.0:1234).

v148 (spec O1): the server is chosen INSIDE the image, never in
docker-compose.yml. Off Windows, with gunicorn importable (the production
image), this process replaces itself with gunicorn (deploy/gunicorn.conf.py,
admin_wsgi:app) before doing anything else, and admin_wsgi.py then does the
logging and boot record in the worker. Anywhere else (Windows dev, a
pre-v148 image without gunicorn) it falls through to Flask's app.run as
before. A rollback to an older image under today's compose file still boots.
"""
import logging
import os
import sys
from importlib.util import find_spec
from logging.handlers import RotatingFileHandler
from pathlib import Path

from swingbot import config
from swingbot.core.infra.logsetup import _OWNED, configure_logging

ADMIN_LOG_MAX_BYTES = 5 * 1024 * 1024
ADMIN_LOG_BACKUPS = 2
# gunicorn sets propagate=False on both and writes them to stdout/stderr with
# its own handlers, so logs/admin.log only sees them through a handler
# attached here.
GUNICORN_LOGGERS = ("gunicorn.access", "gunicorn.error")


def _pin_gunicorn_loggers() -> None:
    """Route gunicorn's request and error lines into logs/admin.log at INFO.

    Only the logsetup-owned FILE handler is attached: gunicorn already prints
    both loggers to the console. The handler an earlier call attached is
    removed first, because configure_logging closes and replaces it."""
    root = logging.getLogger()
    files = [h for h in root.handlers
             if isinstance(h, RotatingFileHandler) and getattr(h, _OWNED, False)]
    for name in GUNICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        for stale in [h for h in logger.handlers if getattr(h, _OWNED, False)]:
            logger.removeHandler(stale)
        for handler in files:
            logger.addHandler(handler)


def setup_logging() -> None:
    """Root logging for the admin process: console plus logs/admin.log (5MB x 2).

    Werkzeug request lines stay pinned at INFO whatever LOG_LEVEL says, as
    they were before v111, so the Logs page still shows admin activity; under
    gunicorn (v148) its access and error loggers get the same treatment."""
    configure_logging(config.ADMIN_LOG_FILE, config.LOG_LEVEL,
                      max_bytes=ADMIN_LOG_MAX_BYTES, backups=ADMIN_LOG_BACKUPS)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    _pin_gunicorn_loggers()


def _gunicorn_argv(root: Path) -> list[str]:
    """The command that replaces this process when the image ships gunicorn."""
    return [sys.executable, "-m", "gunicorn",
            "-c", str(root / "deploy" / "gunicorn.conf.py"),
            "admin_wsgi:app"]


def _maybe_exec_gunicorn() -> None:
    """Become gunicorn when it is importable off Windows; otherwise return.

    `find_spec` locates the package without importing it (gunicorn needs
    fcntl). On success `os.execv` never returns."""
    if sys.platform == "win32" or find_spec("gunicorn") is None:
        return
    argv = _gunicorn_argv(Path(__file__).resolve().parent)
    os.execv(argv[0], argv)


if __name__ == "__main__":
    # v148: before logging and record_boot, so neither runs twice -- under
    # gunicorn, admin_wsgi.py does both in the worker.
    _maybe_exec_gunicorn()
    # Logging first, so anything logged while importing the app lands in admin.log.
    setup_logging()
    from swingbot.admin.app import main
    from swingbot.core.infra.deploy_marker import record_boot
    record_boot("admin")
    main()
```

- [ ] **Step 5: Create `admin_wsgi.py`**

Create `$WT/admin_wsgi.py`:

```python
"""WSGI entry for gunicorn (v148, spec O1): `gunicorn ... admin_wsgi:app`.

Imported once, in the single gunicorn worker (preload_app = False), never by
`python admin_ui.py`'s own app.run path. It does what admin_ui.py's
__main__ block and app.main() do before serving, in the same order:

1. root logging (so anything logged while importing the app lands in
   logs/admin.log),
2. the boot record for the deploy telemetry,
3. the app itself,
4. the v132 bound on the admin's wait for the yfinance download lock --
   app.main() sets it, and gunicorn never runs app.main().
"""
import admin_ui
from swingbot import config
from swingbot.core.infra import deploy_marker

admin_ui.setup_logging()
deploy_marker.record_boot("admin")

from swingbot.admin.app import app  # noqa: E402  -- after logging, as in admin_ui.py
from swingbot.core.marketdata import yf_safe  # noqa: E402

yf_safe.set_default_lock_timeout(float(config.ADMIN_YF_LOCK_TIMEOUT_SECONDS))

__all__ = ["app"]
```

- [ ] **Step 6: Pin gunicorn in `requirements.txt`**

Check the newest 23.x release (the spec pins the newest 23.x, exactly):

```bash
python -m pip index versions gunicorn
```

As of 2026-10-10 the only 23.x release is `23.0.0`. If a newer `23.x.y` is listed, pin that instead. In `$WT/requirements.txt`, directly after the `flask==3.1.3` line, insert:

```
# v148: production WSGI server for the admin container. Used on Linux only:
# admin_ui.py execs it when importable off Windows and falls back to
# app.run otherwise. No test imports it (it needs fcntl).
gunicorn==23.0.0
```

Do not install it into the dev environment. The tests never need it, and the falls-through tests patch `find_spec` regardless.

- [ ] **Step 7: Rollback notes in `docs/deploy/DEPLOY_HETZNER.md`**

Use `Edit` (not `sed -i`). In `$WT/docs/deploy/DEPLOY_HETZNER.md`, under `## Rolling back`, after the paragraph that ends `the "Publishing as …" line of the run that shipped it.`, insert this blank-line-separated paragraph:

```markdown
**The admin's server is chosen inside the image (v148).** Compose runs the
admin as `python admin_ui.py`, and it must keep doing so. A v148+ image execs
gunicorn from there (`deploy/gunicorn.conf.py`, one gthread worker); an older
image runs Flask's `app.run`. Rolling back to a pre-v148 tag therefore needs no
compose edit. Never point the admin's compose `command:` at gunicorn: a
pre-v148 image has neither gunicorn nor `admin_wsgi.py`, and the admin would
crash-loop. Which one is running: `docker compose exec admin ps -o pid,args`.
```

Under `### Point-in-time rollback`, after the paragraph that ends with the words "Run it again without `--dry-run` to roll back." (it follows the fenced `--dry-run` rehearsal block) and before `**Backups.**`, insert:

```markdown
A point-in-time rollback restores the images of that moment under the compose
file already on the VM. Before v148 the admin image runs `app.run`, from v148
on it runs gunicorn; both start from compose's `python admin_ui.py`, so no
compose edit is needed either way (see "Rolling back").
```

- [ ] **Step 8: Run the tests and watch them pass**

```bash
python $WT/scripts/dev/testrun.py file tests/admin/test_gunicorn_conf.py
python $WT/scripts/dev/testrun.py file tests/admin/test_admin_logging.py
python $WT/scripts/dev/testrun.py file tests/infra/test_logsetup.py
python -m py_compile $WT/admin_ui.py $WT/admin_wsgi.py $WT/deploy/gunicorn.conf.py
```

Expected: all green (`0 failed`, `0 xfailed`). `test_logsetup.py` guards the `_OWNED` import. If one of `test_admin_logging.py`'s existing tests now fails because the root logger carries extra handlers, the cause is a missing `restore_gunicorn_loggers` on the new tests, not the production code.

- [ ] **Step 9: Complexity and the no-gunicorn-import guard**

```bash
python -m radon cc -s -n C $WT/admin_ui.py $WT/admin_wsgi.py $WT/deploy/gunicorn.conf.py
git -C $WT grep -n "import gunicorn\|from gunicorn" -- '*.py'
```

Expected: radon prints nothing, and the grep prints nothing (no file imports gunicorn). If radon is missing, run `python -m pip install radon` first.

- [ ] **Step 10: Commit**

```bash
git -C $WT add admin_ui.py admin_wsgi.py deploy/gunicorn.conf.py requirements.txt docs/deploy/DEPLOY_HETZNER.md tests/admin/test_gunicorn_conf.py tests/admin/test_admin_logging.py
git -C $WT commit -m "feat(admin): v148 OH2 run the admin under gunicorn when the image has it, app.run otherwise"
git -C /home/user/Discord-Bot status --short
```

The last command prints nothing new.

### Task OH3: Constant-time credentials and the login limiter

**Model:** sonnet — a security fix that touches three auth sites and adds a thread-safe module with a reload-sensitive test fixture; contained, but must be exact.

**Files:**
- Create: `swingbot/admin/login_limiter.py`
- Modify: `swingbot/admin/app.py`
- Modify: `swingbot/admin/api_v1/auth.py`
- Modify: `swingbot/admin/api_v1/session.py`
- Modify: `tests/admin/conftest.py`
- Create: `tests/admin/test_login_limiter.py`

**Why:** spec O2. Three plain comparisons (`app.py:159`, `api_v1/auth.py:38-39`, `api_v1/session.py:56`) become one constant-time helper, `app.credentials_match`. All three paths share a sliding-window limiter of 5 failures per 15 minutes, keyed on `CF-Connecting-IP` (behind the tunnel `request.remote_addr` is the `cloudflared` container for everyone). A locked key gets **429** with `Retry-After`. The v1 paths use the existing error body with code `rate_limited`, and the `app.require_auth` Basic path answers plain text. A wrong credential counts as a failure and a right one clears the key. A request with no credentials is not an attempt.

Contracts other tasks rely on (ledger): `app.credentials_match(username: str, password: str) -> bool`; `LoginLimiter(max_failures=5, window_s=900, clock=time.monotonic)` with `check(key) -> int | None`, `fail(key)`, `succeed(key)`, `reset()`; `login_limiter.LIMITER`; `login_limiter.client_key() -> str`; `login_limiter.rate_limited_message(seconds) -> str`; the v1 429 body `{"error": {"code": "rate_limited", "message": ...}}` with a `Retry-After` header. OH4 consumes the code and the body shape.

Two implementation choices that stay inside the ledger:
- `rate_limited_message` says `1 minute` (singular) when N is 1 and `N minutes` otherwise. The ledger's template is `"Too many failed sign-ins. Try again in N minutes."`. Nothing outside this task matches the string; OH4's spec uses its own fixture text.
- The gate shared by the three sites is one function, `login_limiter.attempt(username, password, match) -> Attempt`. `match` is passed in (`app.credentials_match`), so `login_limiter` imports nothing from `swingbot.admin` and adds no import cycle. `attempt` reads the module-level `LIMITER` at call time, so a test can swap in a fake-clock instance with `monkeypatch.setattr(login_limiter, "LIMITER", ...)`.

Reload trap (index Global Constraints, "Admin tests"): `tests/admin/conftest.py` reloads `swingbot.admin.app` per test but not `api_v1.*` and not `login_limiter`. The api_v1 modules therefore call `_app.credentials_match` through the module attribute, and an autouse fixture clears `login_limiter.LIMITER` before and after every admin test. Without that fixture the failures from one test would lock out the next.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/admin/test_login_limiter.py`:

```python
"""v148 O2: constant-time credential checks and one login limiter shared by
the SPA login, v1 Basic auth and app.require_auth's Basic path."""
import base64
import re
import threading
from pathlib import Path

import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import login_limiter
from swingbot.admin.login_limiter import LoginLimiter

_WRONG = {"username": "admin", "password": "wrong"}
_RIGHT = {"username": "admin", "password": "admin"}
_FIFTEEN = "Too many failed sign-ins. Try again in 15 minutes."


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _fail_login(client, n: int, **kwargs) -> None:
    for _ in range(n):
        assert client.post("/api/v1/session", json=_WRONG, **kwargs).status_code == 401


# --- LoginLimiter -------------------------------------------------------------

def test_five_failures_lock_the_key_for_the_window():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(4):
        limiter.fail("203.0.113.7")
    assert limiter.check("203.0.113.7") is None
    limiter.fail("203.0.113.7")
    assert limiter.check("203.0.113.7") == 900
    assert limiter.check("198.51.100.9") is None


def test_the_window_slides_off_the_oldest_failure():
    clock = _Clock()
    limiter = LoginLimiter(clock=clock)
    limiter.fail("k")                      # t = 1000
    clock.now = 1100.0
    for _ in range(4):
        limiter.fail("k")                  # t = 1100
    assert limiter.check("k") == 800       # until the t=1000 failure ages out
    clock.now = 1900.0
    assert limiter.check("k") is None      # four left inside the window
    limiter.fail("k")                      # a fifth inside the window again
    assert limiter.check("k") == 100       # 1100 + 900 - 1900


def test_success_clears_the_key():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(4):
        limiter.fail("k")
    limiter.succeed("k")
    for _ in range(4):
        limiter.fail("k")
    assert limiter.check("k") is None


def test_memory_is_bounded_by_the_keys_seen_inside_the_window():
    clock = _Clock()
    limiter = LoginLimiter(clock=clock)
    for i in range(100):
        limiter.fail(f"10.0.0.{i}")
    assert len(limiter) == 100
    clock.now += 901
    limiter.check("anyone")
    assert len(limiter) == 0


def test_concurrent_failures_are_all_counted():
    limiter = LoginLimiter(max_failures=4000, clock=_Clock())

    def hammer():
        for _ in range(500):
            limiter.fail("k")

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert limiter.check("k") is not None   # 8 x 500 = exactly the 4000 that lock


def test_reset_forgets_everything():
    limiter = LoginLimiter(clock=_Clock())
    for _ in range(5):
        limiter.fail("k")
    limiter.reset()
    assert limiter.check("k") is None and len(limiter) == 0


@pytest.mark.parametrize("seconds, text", [
    (1, "1 minute"), (60, "1 minute"), (61, "2 minutes"), (900, "15 minutes"),
])
def test_message_rounds_up_to_whole_minutes(seconds, text):
    assert login_limiter.rate_limited_message(seconds) == (
        f"Too many failed sign-ins. Try again in {text}.")


# --- credentials_match ----------------------------------------------------------

def test_credentials_match_always_compares_both_fields(admin_app, monkeypatch):
    from swingbot.admin import app as app_mod

    calls = []
    real = app_mod.hmac.compare_digest
    monkeypatch.setattr(app_mod.hmac, "compare_digest",
                        lambda a, b: calls.append((a, b)) or real(a, b))

    assert app_mod.credentials_match("nobody", "admin") is False
    # No short-circuit on the wrong username: the password is compared too.
    assert calls == [(b"nobody", b"admin"), (b"admin", b"admin")]
    calls.clear()
    assert app_mod.credentials_match("admin", "admin") is True
    assert len(calls) == 2
    assert app_mod.credentials_match("admin", "wrong") is False


def test_no_plain_comparison_against_the_admin_credentials_is_left():
    admin = Path(__file__).resolve().parents[2] / "swingbot" / "admin"
    plain = re.compile(r"[=!]=\s*(_app\.)?ADMIN_(USERNAME|PASSWORD)\b"
                       r"|ADMIN_(USERNAME|PASSWORD)\s*[=!]=")
    offenders = [str(p) for p in admin.rglob("*.py") if plain.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


# --- the three paths --------------------------------------------------------------

def test_spa_login_locks_after_five_failures_even_for_the_right_password(client):
    _fail_login(client, 5)
    r = client.post("/api/v1/session", json=_RIGHT)
    assert_error(r, "rate_limited", 429)
    assert r.get_json()["error"]["message"] == _FIFTEEN
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_v1_basic_auth_locks_after_five_failures(client):
    for _ in range(5):
        assert_error(client.get("/api/v1/health", headers=_basic("admin", "wrong")), "auth", 401)
    r = client.get("/api/v1/health", headers=_basic("admin", "admin"))
    assert_error(r, "rate_limited", 429)
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_app_require_auth_basic_path_answers_a_plain_text_429(admin_app):
    from swingbot.admin import app as app_mod

    view = app_mod.require_auth(lambda: "ok")

    def call(user, password):
        with admin_app.test_request_context("/", headers=_basic(user, password)):
            return admin_app.make_response(view())

    assert call("admin", "admin").get_data(as_text=True) == "ok"
    for _ in range(5):
        assert call("admin", "wrong").status_code == 401
    r = call("admin", "admin")
    assert r.status_code == 429
    assert r.mimetype == "text/plain"
    assert r.get_data(as_text=True) == _FIFTEEN
    assert 899 <= int(r.headers["Retry-After"]) <= 900


def test_the_three_paths_share_one_count(client):
    _fail_login(client, 3)
    for _ in range(2):
        assert client.get("/api/v1/health", headers=_basic("admin", "wrong")).status_code == 401
    assert_error(client.post("/api/v1/session", json=_RIGHT), "rate_limited", 429)
    assert_error(client.get("/api/v1/health", headers=_basic("admin", "admin")), "rate_limited", 429)


def test_a_right_password_clears_the_count(client):
    _fail_login(client, 4)
    assert client.post("/api/v1/session", json=_RIGHT).status_code == 200
    _fail_login(client, 5)   # the fifth is still a plain 401: the count restarted


def test_the_key_is_cf_connecting_ip(client):
    a = {"CF-Connecting-IP": "203.0.113.7"}
    b = {"CF-Connecting-IP": "198.51.100.9"}
    _fail_login(client, 5, headers=a)
    assert_error(client.post("/api/v1/session", json=_RIGHT, headers=a), "rate_limited", 429)
    # Same socket peer (the test client, as cloudflared is in production),
    # different client address: not locked.
    assert client.post("/api/v1/session", json=_RIGHT, headers=b).status_code == 200


def test_requests_without_credentials_never_count(client):
    for _ in range(10):
        assert_error(client.get("/api/v1/health"), "auth", 401)
        assert_error(client.post("/api/v1/session", json={}), "auth", 401)
    assert client.get("/api/v1/health", headers=_basic("admin", "admin")).status_code == 200


def test_the_lock_lifts_once_the_window_has_passed(client, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(login_limiter, "LIMITER", LoginLimiter(clock=clock))
    _fail_login(client, 5)
    assert_error(client.post("/api/v1/session", json=_RIGHT), "rate_limited", 429)
    clock.now += 901
    assert client.post("/api/v1/session", json=_RIGHT).status_code == 200
```

In `$WT/tests/admin/conftest.py`, append after the `auth` fixture (end of file):

```python


@pytest.fixture(autouse=True)
def _clear_login_limiter():
    """v148: login_limiter is NOT in _RELOAD_MODULES (nothing in it bakes a
    path), so its module-level LIMITER would carry one test's failed sign-ins
    into the next and lock it out. Cleared before and after every admin test."""
    from swingbot.admin import login_limiter

    login_limiter.LIMITER.reset()
    yield
    login_limiter.LIMITER.reset()
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/admin/test_login_limiter.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.admin.login_limiter'`.

- [ ] **Step 3: Create `swingbot/admin/login_limiter.py`**

```python
"""Login limiter (v148, spec O2).

Five failed sign-ins from one client address inside a sliding 15-minute window
lock that address out of all three credential checks: the SPA login form
(POST /api/v1/session), Basic auth on /api/v1/*, and Basic auth on
app.require_auth. The lock lifts when the oldest of those failures ages out.

One module-level instance, LIMITER, is valid because the admin runs ONE
worker (deploy/gunicorn.conf.py). Two workers would each keep their own count
and double the allowance.

The key is the CF-Connecting-IP header when present. Behind the Cloudflare
tunnel every request arrives from the cloudflared container, so
request.remote_addr is the same for everyone. The header is spoofable only by
someone who can reach port 1234 directly, which the VM firewall forbids
(docs/deploy/DEPLOY_HETZNER.md, "Accessing the admin UI").

Only attempts count: a request carrying no credentials is never a failure.
This module imports nothing from swingbot.admin. The credential check is
passed in, so app.py and the api_v1 modules can both import it without a cycle.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from flask import request

MAX_FAILURES = 5
WINDOW_S = 900.0


class LoginLimiter:
    """Failure timestamps per key over a sliding window, behind one lock.

    Every call prunes timestamps older than the window and drops keys left
    empty, so memory is bounded by the addresses that failed recently."""

    def __init__(self, max_failures: int = MAX_FAILURES, window_s: float = WINDOW_S,
                 clock: Callable[[], float] = time.monotonic):
        self._max = max_failures
        self._window = window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    def __len__(self) -> int:
        """Keys currently tracked (for the memory-bound test)."""
        with self._lock:
            return len(self._failures)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._failures):
            stamps = self._failures[key]
            while stamps and stamps[0] <= cutoff:
                stamps.popleft()
            if not stamps:
                del self._failures[key]

    def check(self, key: str) -> int | None:
        """Whole seconds until `key` may try again, or None when not locked."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            stamps = self._failures.get(key)
            if stamps is None or len(stamps) < self._max:
                return None
            # The lock lifts when the max-th most recent failure leaves the window.
            return max(1, math.ceil(stamps[-self._max] + self._window - now))

    def fail(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failures.setdefault(key, deque()).append(now)

    def succeed(self, key: str) -> None:
        with self._lock:
            self._prune(self._clock())
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


LIMITER = LoginLimiter()


def client_key() -> str:
    """CF-Connecting-IP when present, else the socket peer, else "unknown"."""
    forwarded = (request.headers.get("CF-Connecting-IP") or "").strip()
    return forwarded or request.remote_addr or "unknown"


def rate_limited_message(seconds: int) -> str:
    """The 429 text all three paths send, in whole minutes rounded up (min 1)."""
    minutes = max(1, math.ceil(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Too many failed sign-ins. Try again in {minutes} {unit}."


@dataclass(frozen=True)
class Attempt:
    """One gated credential check. `retry_after` is set only when locked."""
    ok: bool
    retry_after: int | None = None


def attempt(username: str, password: str, match: Callable[[str, str], bool]) -> Attempt:
    """Gate one credential check through LIMITER (read at call time).

    A locked key is refused before the credentials are compared. Empty
    username AND password is not an attempt and is never counted."""
    key = client_key()
    wait = LIMITER.check(key)
    if wait is not None:
        return Attempt(False, wait)
    if not username and not password:
        return Attempt(False)
    if match(username, password):
        LIMITER.succeed(key)
        return Attempt(True)
    LIMITER.fail(key)
    return Attempt(False)
```

- [ ] **Step 4: `app.py`: add `credentials_match` and gate the Basic path**

In `$WT/swingbot/admin/app.py`:

1. After the line `from .helpers import docker_sdk, _load_or_create_secret_key  # noqa: F401`, add:

```python
from . import login_limiter
```

(`login_limiter` imports only Flask, so importing it at the top does not hit the circular-import problem the blueprints at the bottom of this file avoid.)

2. Directly after `_session_authenticated()` and before `def require_auth(view):`, add:

```python
def credentials_match(username: str, password: str) -> bool:
    """Constant-time check of a username/password pair (v148, spec O2).

    Both fields are always compared, with no short-circuit on a wrong
    username, so the response time does not say which one was wrong. Read
    ADMIN_USERNAME/ADMIN_PASSWORD at call time: the conftest reloads this
    module per test, and api_v1 reaches this function as
    `_app.credentials_match`."""
    user_ok = hmac.compare_digest(username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8"))
    pass_ok = hmac.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))
    return user_ok and pass_ok
```

3. In `require_auth`'s `wrapped`, replace this block:

```python
        if auth:
            # Client explicitly attempted Basic Auth (e.g. a script, or this
            # suite's `auth` fixture) -- keep the original challenge behavior
            # for that path rather than redirecting it to an HTML login page.
            if auth.username == ADMIN_USERNAME and auth.password == ADMIN_PASSWORD:
                return view(*args, **kwargs)
            return Response(
                "Authentication required.", 401,
                {"WWW-Authenticate": 'Basic realm="Swing Bot Admin"'},
            )
```

with:

```python
        if auth:
            # Client explicitly attempted Basic Auth (e.g. a script, or this
            # suite's `auth` fixture) -- keep the original challenge behavior
            # for that path rather than redirecting it to an HTML login page.
            # v148: constant-time, and gated by the shared login limiter.
            outcome = login_limiter.attempt(auth.username or "", auth.password or "",
                                            credentials_match)
            if outcome.ok:
                return view(*args, **kwargs)
            if outcome.retry_after is not None:
                return Response(
                    login_limiter.rate_limited_message(outcome.retry_after), 429,
                    {"Retry-After": str(outcome.retry_after)}, mimetype="text/plain",
                )
            return Response(
                "Authentication required.", 401,
                {"WWW-Authenticate": 'Basic realm="Swing Bot Admin"'},
            )
```

(`auth.username` is `None` for a non-Basic `Authorization` scheme such as Bearer. The `or ""` keeps `.encode` safe, and such a request still ends in the 401 it gets today.)

- [ ] **Step 5: `api_v1/auth.py`: the v1 429 helper and the gated Basic path**

In `$WT/swingbot/admin/api_v1/auth.py`:

1. Replace the import line `from . import error` with:

```python
from swingbot.admin import login_limiter

from . import error
```

2. Before `def require_auth(view):`, add:

```python
def rate_limited(retry_after: int):
    """The v1 429 (v148): the one error body, plus a Retry-After header."""
    body, status = error("rate_limited", login_limiter.rate_limited_message(retry_after), 429)
    body.headers["Retry-After"] = str(retry_after)
    return body, status
```

3. In `wrapped`, replace:

```python
        auth = request.authorization
        if (auth and auth.username == _app.ADMIN_USERNAME
                and auth.password == _app.ADMIN_PASSWORD):
            return view(*args, **kwargs)
```

with:

```python
        auth = request.authorization
        if auth:
            # v148: constant-time, gated by the limiter app.require_auth and
            # POST /session share. A request with no credentials never counts.
            outcome = login_limiter.attempt(auth.username or "", auth.password or "",
                                            _app.credentials_match)
            if outcome.ok:
                return view(*args, **kwargs)
            if outcome.retry_after is not None:
                return rate_limited(outcome.retry_after)
```

The following lines (the no-`WWW-Authenticate` comment and `return error("auth", "Authentication required.", 401)`) stay as they are.

4. In the module docstring, after the paragraph ending `which the contract assertions caught immediately.`, add:

```
v148: the Basic comparison is `_app.credentials_match` (constant time), and
every attempt goes through `login_limiter.attempt`, shared with
`app.require_auth` and POST /api/v1/session. A locked client gets
`rate_limited` (429) with a Retry-After header.
```

- [ ] **Step 6: `api_v1/session.py`: the gated SPA login**

In `$WT/swingbot/admin/api_v1/session.py`:

1. Replace `from .auth import require_auth` with:

```python
from swingbot.admin import login_limiter

from .auth import rate_limited, require_auth
```

Keep the existing `from swingbot.admin import app as _app` and `from swingbot.admin import helpers as _helpers` lines, and put the new `login_limiter` import beside them (one `from swingbot.admin import ...` block), above `from . import api_v1, error`.

2. In `session_create`, replace:

```python
    username = payload.get("username", "")
    password = payload.get("password", "")
    if username != _app.ADMIN_USERNAME or password != _app.ADMIN_PASSWORD:
        return error("auth", "Invalid username or password.", 401)
```

with:

```python
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    # v148: constant-time, and gated by the login limiter all three
    # credential checks share. A locked client is refused before comparing.
    outcome = login_limiter.attempt(username, password, _app.credentials_match)
    if outcome.retry_after is not None:
        return rate_limited(outcome.retry_after)
    if not outcome.ok:
        return error("auth", "Invalid username or password.", 401)
```

- [ ] **Step 7: Run the tests and watch them pass**

```bash
python $WT/scripts/dev/testrun.py file tests/admin/test_login_limiter.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_session.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_skeleton.py
```

Expected: all green. `test_api_v1_session.py` pins the existing 401 bodies and the login/logout round trip. `test_api_v1_skeleton.py` covers the error handlers registered at reload. If an unrelated admin test now fails with a 429, a test there sends five or more wrong credentials. Show the controller the test name before changing anything: the autouse reset already isolates tests from each other, so the only remaining cause is five failures inside one test.

Then the admin tests that use Basic auth heavily:

```bash
python $WT/scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed` (it selects the admin tests reaching `app.py` and `api_v1/*`).

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/admin/login_limiter.py $WT/swingbot/admin/app.py $WT/swingbot/admin/api_v1/auth.py $WT/swingbot/admin/api_v1/session.py
```

Expected: no function listed. If a pre-existing function in `app.py` is listed, confirm its score did not rise: `git -C $WT show HEAD:swingbot/admin/app.py | python -m radon cc -s -n C -` must print the same score. `require_auth.wrapped` gains two branches and stays well under 15.

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/admin/login_limiter.py swingbot/admin/app.py swingbot/admin/api_v1/auth.py swingbot/admin/api_v1/session.py tests/admin/conftest.py tests/admin/test_login_limiter.py
git -C $WT commit -m "feat(admin): v148 OH3 constant-time credential checks and a shared 5-per-15-minute login limiter"
git -C /home/user/Discord-Bot status --short
```

The last command prints nothing new.

### Task OH4: SPA shows the 429 message

**Model:** haiku — one union member, one pure message function and one spec case, all fully specified below.

**Files:**
- Modify: `frontend/src/app/api/api-error.ts`
- Modify: `frontend/src/app/stores/session.store.ts`
- Modify: `frontend/src/app/stores/session.store.spec.ts`

**Why:** spec O2, last bullet. `session.store.ts`'s `login()` maps every error that is not `ApiError.isAuth` to "Could not reach the admin. Is it running?". A locked-out partner would therefore be told the admin is down. OH3's 429 arrives through `errorInterceptor` → `toApiError` as `new ApiError('rate_limited', 429, '<server message>')`, because the body declares a code. The store shows that message as-is: it already says when to retry. Depends on OH3 (the code and the body shape).

- [ ] **Step 1: Make sure the worktree has the frontend dependencies**

```bash
test -d /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend/node_modules || npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend ci
```

- [ ] **Step 2: Write the failing spec case**

In `$WT/frontend/src/app/stores/session.store.spec.ts`, insert this case directly after the `it('distinguishes a dead admin from a wrong password', ...)` case (inside the same `describe`):

```ts
  it('shows the server message when sign-ins are rate limited', async () => {
    await boot(false, null);

    const done = store.login('admin', 'admin');
    backend.expectOne('/api/v1/session').flush(
      {
        error: {
          code: 'rate_limited',
          message: 'Too many failed sign-ins. Try again in 15 minutes.',
        },
      },
      { status: 429, statusText: 'Too Many Requests', headers: { 'Retry-After': '900' } },
    );
    await done;

    // Not "Could not reach the admin": the admin answered, and said when to retry.
    expect(store.isAuthenticated()).toBe(false);
    expect(store.error()).toBe('Too many failed sign-ins. Try again in 15 minutes.');
    expect(store.submitting()).toBe(false);
  });
```

- [ ] **Step 3: Run it and watch it fail**

```bash
npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend test -- --include src/app/stores/session.store.spec.ts
```

Expected: the new case fails, with `expected 'Could not reach the admin. Is it running?' to be 'Too many failed sign-ins. Try again in 15 minutes.'`.

- [ ] **Step 4: Add the code and use the message**

In `$WT/frontend/src/app/api/api-error.ts`, replace the `ApiErrorCode` union with:

```ts
export type ApiErrorCode =
  | 'auth'
  | 'not_found'
  | 'invalid'
  | 'conflict'
  | 'unavailable'
  /** v148: too many failed sign-ins from this address; the message says when to retry. */
  | 'rate_limited';
```

In `$WT/frontend/src/app/stores/session.store.ts`, add this function directly after the `SessionState` interface (module level, before `export const SessionStore`):

```ts
/** The login form's message for a rejected attempt.
 *
 *  A 429 (v148) carries the server's own text, which says when to retry.
 *  It must not fall through to "Could not reach the admin": the admin answered. */
function loginError(error: unknown): string {
  if (error instanceof ApiError && error.code === 'rate_limited') {
    return error.message;
  }
  if (error instanceof ApiError && error.isAuth) {
    return 'Invalid username or password.';
  }
  return 'Could not reach the admin. Is it running?';
}
```

Then, in `login()`'s `catch (error)`, replace:

```ts
          error:
            error instanceof ApiError && error.isAuth
              ? 'Invalid username or password.'
              : 'Could not reach the admin. Is it running?',
```

with:

```ts
          error: loginError(error),
```

- [ ] **Step 5: Run the spec and the interceptor spec and watch them pass**

```bash
npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend test -- --include src/app/stores/session.store.spec.ts
npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend test -- --include src/app/api/interceptors.spec.ts
```

Expected: both green, including the existing "reports a rejected password" and "distinguishes a dead admin" cases.

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/api/api-error.ts frontend/src/app/stores/session.store.ts frontend/src/app/stores/session.store.spec.ts
git -C $WT commit -m "feat(ui): v148 OH4 show the server's rate-limit message on a 429 login"
git -C /home/user/Discord-Bot status --short
```

The last command prints nothing new.

### Task OH5: Ops alert config keys

**Model:** haiku — three declarative `Field` entries, three `.env.example` lines and a pinning test, all given verbatim.

**Files:**
- Modify: `swingbot/config.py`
- Modify: `.env.example`
- Create: `tests/infra/test_config_ops_alerts.py`

**Why:** spec O4 "Config" table. OH17/OH18 (provider verdict) read `config.PROVIDER_FALLBACK_ALERT_PCT` and `config.EMPTY_SYMBOLS_ALERT_PCT`, and OH20 echoes both as `thresholds`. OH19's cron reads `OPS_ALERT_WEBHOOK_URL` from `.env` with `grep`. All three live in section "Data Sources" after `SPOT_QUOTE_MAX_AGE_SECONDS`. `type="number"` casts with `int(...)` (`config._CASTERS`), so the module attributes are ints. `OPS_ALERT_WEBHOOK_URL` is `hot_reloadable=False` because no process reloads it: only the cron reads it. `tests/infra/test_env_example_sync.py` fails until all three keys are in `.env.example`.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/infra/test_config_ops_alerts.py`:

```python
"""v148: the ops-alert settings (spec O4 "Config")."""
import re
from pathlib import Path

from swingbot import config

_KEYS = ("PROVIDER_FALLBACK_ALERT_PCT", "EMPTY_SYMBOLS_ALERT_PCT", "OPS_ALERT_WEBHOOK_URL")


def _fields() -> dict:
    return {f.key: f for f in config.FIELDS}


def test_declared_in_data_sources_under_their_own_names():
    fields = _fields()
    for key in _KEYS:
        assert fields[key].section == "Data Sources", key
        assert fields[key].attr == key


def test_thresholds_are_hot_whole_percentages():
    fields = _fields()
    for key, default in (("PROVIDER_FALLBACK_ALERT_PCT", "20"), ("EMPTY_SYMBOLS_ALERT_PCT", "5")):
        f = fields[key]
        assert (f.type, f.default, f.min, f.max) == ("number", default, 1, 100), key
        assert f.hot_reloadable is True and f.sensitive is False
        assert config._cast(f, "35") == 35


def test_threshold_defaults_are_live_ints():
    assert config.PROVIDER_FALLBACK_ALERT_PCT == 20
    assert config.EMPTY_SYMBOLS_ALERT_PCT == 5


def test_webhook_is_a_secret_that_only_the_cron_reads():
    f = _fields()["OPS_ALERT_WEBHOOK_URL"]
    assert (f.type, f.default, f.sensitive, f.hot_reloadable) == ("password", "", True, False)
    assert "scripts/ops/heartbeat_watch.sh" in f.help
    assert "not by the bot or the admin" in f.help


def test_listed_in_env_example():
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    for key in _KEYS:
        assert re.search(rf"^{key}=", text, re.MULTILINE), key
```

- [ ] **Step 2: Run it and watch it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/infra/test_config_ops_alerts.py
```

Expected: every test fails with `KeyError: 'PROVIDER_FALLBACK_ALERT_PCT'` or `AttributeError`.

- [ ] **Step 3: Declare the fields**

In `$WT/swingbot/config.py`, directly after the `SPOT_QUOTE_MAX_AGE_SECONDS` `Field(...)` entry (the last "Data Sources" field, which ends `... until a fresh "\n "quote arrives. Never falls back to unscaled futures prices."),`) and before the `# --- Admin UI ...` comment, insert:

```python
    # v148: ops alerts (spec O3/O4).
    Field("PROVIDER_FALLBACK_ALERT_PCT", "PROVIDER_FALLBACK_ALERT_PCT", "Data Sources",
          "Ops alert: provider fallback above (%)", type="number", default="20",
          min=1, max=100, step=1,
          help="v148. A scheduled scan whose Alpaca-to-yfinance fallback rate "
               "(yfinance-fallback / (alpaca + yfinance-fallback)) exceeds this posts a "
               "provider-degraded notice to the ops channel, once per incident, and a "
               "recovery notice when a later scan is back under both thresholds."),
    Field("EMPTY_SYMBOLS_ALERT_PCT", "EMPTY_SYMBOLS_ALERT_PCT", "Data Sources",
          "Ops alert: empty symbols above (%)", type="number", default="5",
          min=1, max=100, step=1,
          help="v148. A scheduled scan in which more than this share of tickers came back "
               "with no price frame, or an empty one, posts the same provider-degraded notice."),
    Field("OPS_ALERT_WEBHOOK_URL", "OPS_ALERT_WEBHOOK_URL", "Data Sources",
          "Ops alert webhook URL (heartbeat cron)", type="password", default="",
          sensitive=True, hot_reloadable=False,
          help="Read from .env by the heartbeat_watch cron on the VM "
               "(scripts/ops/heartbeat_watch.sh), not by the bot or the admin; the cron "
               "picks a change up on its next run."),
```

- [ ] **Step 4: Add the keys to `.env.example`**

In `$WT/.env.example`, directly after the line `SPOT_QUOTE_MAX_AGE_SECONDS=900` and before the blank line that precedes `# --- Admin UI ---`, insert (use `Edit`, not `sed -i`):

```
# v148: ops alerts. A scheduled scan above either share posts a provider-degraded
# notice to the ops channel (once per incident, plus a recovery notice).
PROVIDER_FALLBACK_ALERT_PCT=20
EMPTY_SYMBOLS_ALERT_PCT=5
# v148: Discord webhook the VM's heartbeat_watch cron posts to when the bot's
# heartbeat goes stale. Read by that cron only; empty = log the verdict, never post.
OPS_ALERT_WEBHOOK_URL=
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
python $WT/scripts/dev/testrun.py file tests/infra/test_config_ops_alerts.py
python $WT/scripts/dev/testrun.py file tests/infra/test_env_example_sync.py
python $WT/scripts/dev/testrun.py file tests/infra/test_config_reload.py
```

Expected: all green. `test_env_example_sync.py` checks both directions of the key set, and `test_config_reload.py` covers the hot-reload table.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/config.py .env.example tests/infra/test_config_ops_alerts.py
git -C $WT commit -m "feat(config): v148 OH5 provider/empty-symbol alert thresholds and the ops webhook key"
git -C /home/user/Discord-Bot status --short
```

The last command prints nothing new.
