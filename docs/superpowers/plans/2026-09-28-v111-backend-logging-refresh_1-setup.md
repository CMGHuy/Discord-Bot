# v111 — Backend logging refresh, Part 1: one setup and the scan id

**Index, global constraints, resolved ambiguities and parallelisation:** [`2026-09-28-v111-backend-logging-refresh_0-index.md`](2026-09-28-v111-backend-logging-refresh_0-index.md). Every task below includes that file's Global Constraints.

# Phase 1 — One setup and the scan id

### Task V111-1: `logsetup.py`, the one logging setup and the scan-id context

**Files:**
- Create: `swingbot/core/infra/logsetup.py`
- Create: `tests/infra/test_logsetup.py`
- Modify: `tests/conftest.py` (add the `restore_root_logging` fixture)

**Interfaces:**
- Consumes: nothing.
- Produces (every later task relies on these exact names):
  - `LOG_FORMAT: str`, `NO_SCAN = "-"`
  - `scan_id_var: contextvars.ContextVar[str]` (default `"-"`)
  - `class ScanIdFilter(logging.Filter)`
  - `apply_log_level(level: int | str) -> int`
  - `configure_logging(log_file: str, level, *, max_bytes: int, backups: int) -> None`
  - `new_scan_id(now: float | None = None) -> str`
  - `scan_context(scan_id: str)`, a context manager yielding the id
  - `with_current_context(fn) -> callable`, which runs `fn` in a fresh copy of the caller's context on every call
  - handlers installed by `configure_logging` carry the attribute `_swingbot_logsetup = True`
  - pytest fixture `restore_root_logging` (in `tests/conftest.py`), which yields the root logger and restores its handlers and level afterwards

- [ ] **Step 1: Add the fixture to `tests/conftest.py`**

`tests/conftest.py` already imports `logging` and `pytest`. Append:

```python
@pytest.fixture
def restore_root_logging():
    """Snapshot the root logger's handlers and level; restore both afterwards.

    configure_logging() (swingbot/core/infra/logsetup.py) replaces the root
    handlers it owns. A test calling it without this fixture would leave its
    tmp-file handler on the process root for every later test in the worker.
    """
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield root
    for handler in root.handlers[:]:
        if handler not in saved_handlers:
            root.removeHandler(handler)
            handler.close()
    for handler in saved_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(saved_level)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/infra/test_logsetup.py`:

```python
"""v111 §1-§2: one root logging setup and the scan-id context."""
import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

from swingbot.core.infra.logsetup import (
    LOG_FORMAT, apply_log_level, configure_logging, new_scan_id, scan_context,
    scan_id_var, with_current_context)


def _owned(root):
    return [h for h in root.handlers if getattr(h, "_swingbot_logsetup", False)]


def _lines(root, path, marker):
    for handler in _owned(root):
        handler.flush()
    return [line for line in path.read_text().splitlines() if marker in line]


def test_format_carries_level_scan_id_and_logger_name():
    assert "[%(levelname)s]" in LOG_FORMAT
    assert "[%(scan_id)s]" in LOG_FORMAT
    assert "%(name)s:" in LOG_FORMAT
    # The admin Logs page finds the level as the FIRST [WORD] on a line
    # (frontend system.store.ts LEVEL_PATTERN); the level must stay first.
    assert LOG_FORMAT.index("%(levelname)s") < LOG_FORMAT.index("%(scan_id)s")


def test_configure_logging_is_idempotent(tmp_path, restore_root_logging):
    for _ in range(2):
        configure_logging(str(tmp_path / "bot.log"), "INFO", max_bytes=1024, backups=1)
    owned = _owned(restore_root_logging)
    assert len(owned) == 2
    assert sum(isinstance(h, RotatingFileHandler) for h in owned) == 1


def test_a_line_shows_level_scan_id_and_logger_name(tmp_path, restore_root_logging):
    path = tmp_path / "bot.log"
    configure_logging(str(path), "INFO", max_bytes=1 << 20, backups=1)
    logger = logging.getLogger("swingbot.test_logsetup")
    logger.info("outside")
    with scan_context("s-1405ab"):
        logger.info("inside")
    outside, inside = _lines(restore_root_logging, path, "swingbot.test_logsetup")
    assert re.search(r"\[INFO\] \[-\] swingbot\.test_logsetup: outside$", outside)
    assert re.search(r"\[INFO\] \[s-1405ab\] swingbot\.test_logsetup: inside$", inside)


def test_scan_id_is_dash_outside_and_the_id_inside():
    assert scan_id_var.get() == "-"
    with scan_context("s-0000aa") as sid:
        assert sid == "s-0000aa"
        assert scan_id_var.get() == "s-0000aa"
    assert scan_id_var.get() == "-"


def test_to_thread_work_inside_a_scan_carries_the_id():
    async def scan():
        with scan_context("s-0900zz"):
            return await asyncio.to_thread(scan_id_var.get)

    assert asyncio.run(scan()) == "s-0900zz"


def test_pool_work_wrapped_with_the_current_context_carries_the_id():
    with scan_context("s-0901q7"):
        task = with_current_context(scan_id_var.get)
        with ThreadPoolExecutor(max_workers=3) as pool:
            got = list(pool.map(lambda _: task(), range(6)))
    assert got == ["s-0901q7"] * 6


def test_a_bare_pool_does_not_carry_the_id():
    # Pins why with_current_context exists: ThreadPoolExecutor threads start
    # in an empty context, so unwrapped pool work logs as "-".
    with scan_context("s-0902aa"):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(scan_id_var.get).result() == "-"


def test_apply_log_level_changes_the_effective_level(restore_root_logging):
    apply_log_level("DEBUG")
    assert logging.getLogger("swingbot.anything").getEffectiveLevel() == logging.DEBUG
    apply_log_level("warning")
    assert logging.getLogger().level == logging.WARNING
    assert apply_log_level(logging.ERROR) == logging.ERROR
    assert apply_log_level("NOT-A-LEVEL") == logging.INFO   # bot_core's old fallback


def test_new_scan_id_is_s_hhmm_plus_two_characters():
    at_1405 = time.mktime((2026, 9, 28, 14, 5, 0, 0, 0, -1))
    assert re.fullmatch(r"s-1405[a-z0-9]{2}", new_scan_id(at_1405))
    assert re.fullmatch(r"s-\d{4}[a-z0-9]{2}", new_scan_id())
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_logsetup.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.infra.logsetup'`.

- [ ] **Step 4: Write the module**

Create `swingbot/core/infra/logsetup.py`:

```python
"""One logging setup for both processes (bot and admin), plus the scan id.

configure_logging() owns the ROOT logger's two handlers, console and a
rotating file, so every module logger (logging.getLogger(__name__)) reaches
both without wiring of its own. Before v111 the admin process attached
admin.log to app.logger and werkzeug only, and every other module's INFO in
that process was dropped.

The scan id is a ContextVar. scan_context() sets it around one scan, and
ScanIdFilter copies it onto every record the two handlers see, so a line
logged anywhere inside a scan carries the id without knowing about it.
asyncio tasks and asyncio.to_thread() copy the context. A ThreadPoolExecutor
does NOT, so pool work inside a scan goes through with_current_context().
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
import secrets
import string
import time
from logging.handlers import RotatingFileHandler

# The level stays the FIRST bracketed word: the admin Logs page filters on it.
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(scan_id)s] %(name)s: %(message)s"
NO_SCAN = "-"
_OWNED = "_swingbot_logsetup"
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits

scan_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("scan_id", default=NO_SCAN)


class ScanIdFilter(logging.Filter):
    """Stamp record.scan_id from the emitting thread's context. Never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.scan_id = scan_id_var.get()
        return True


def _level_value(level) -> int:
    if isinstance(level, int):
        return level
    return logging.getLevelNamesMapping().get(str(level).upper(), logging.INFO)


def apply_log_level(level) -> int:
    """Set the root logger's level. The only level setter after startup.

    An unknown name falls back to INFO, as bot_core always did."""
    value = _level_value(level)
    logging.getLogger().setLevel(value)
    return value


def _remove_owned_handlers(root: logging.Logger) -> None:
    for handler in [h for h in root.handlers if getattr(h, _OWNED, False)]:
        root.removeHandler(handler)
        handler.close()


def configure_logging(log_file: str, level, *, max_bytes: int, backups: int) -> None:
    """Install the console and rotating-file handlers on the root logger.

    Idempotent: handlers an earlier call installed are removed and closed
    first, so calling it twice never duplicates output."""
    root = logging.getLogger()
    _remove_owned_handlers(root)
    formatter = logging.Formatter(LOG_FORMAT, defaults={"scan_id": NO_SCAN})
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backups)
    for handler in (logging.StreamHandler(), file_handler):
        handler.setFormatter(formatter)
        handler.addFilter(ScanIdFilter())
        setattr(handler, _OWNED, True)
        root.addHandler(handler)
    apply_log_level(level)


def new_scan_id(now: float | None = None) -> str:
    """'s-' + local HHMM (the clock %(asctime)s prints) + two chars of [a-z0-9]."""
    stamp = time.strftime("%H%M", time.localtime(now))
    return "s-" + stamp + "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(2))


@contextlib.contextmanager
def scan_context(scan_id: str):
    """Set the scan id for everything logged inside the block."""
    token = scan_id_var.set(scan_id)
    try:
        yield scan_id
    finally:
        scan_id_var.reset(token)


def with_current_context(fn):
    """Wrap fn so each call runs in a fresh copy of the CALLER's context.

    For ThreadPoolExecutor work inside a scan. One Context object cannot be
    entered by two threads at once, so every call gets its own copy."""
    parent = contextvars.copy_context()

    @functools.wraps(fn)
    def run(*args, **kwargs):
        return parent.copy().run(fn, *args, **kwargs)

    return run
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/infra/test_logsetup.py`
Expected: PASS (9 tests).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/infra/logsetup.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/infra/logsetup.py tests/infra/test_logsetup.py tests/conftest.py
git commit -m "feat(v111): logsetup -- one root logging setup, scan-id ContextVar and filter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/infra/logsetup.py tests/infra/test_logsetup.py tests/conftest.py
```

---

### Task V111-2: The bot process logs through `configure_logging`, and SIGHUP uses `apply_log_level`

**Files:**
- Modify: `swingbot/bot_core.py` (module-level handler block, currently lines 20-38; `_handle_reload_signal`'s `LOG_LEVEL` branch, currently ~line 295)
- Create: `tests/test_bot_core_logging.py`

**Interfaces:**
- Consumes: V111-1 `configure_logging`, `apply_log_level`, fixture `restore_root_logging`.
- Produces: `bot_core.configure_bot_logging() -> None`, called once at import. `bot_core.apply_log_level` exists as a module attribute (imported name), so tests can patch it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_core_logging.py`:

```python
"""v111 §1: the bot process logs through the shared root setup."""
import logging
import re
from logging.handlers import RotatingFileHandler

from swingbot import bot_core, config


def _owned_file_handler(root):
    [handler] = [h for h in root.handlers
                 if isinstance(h, RotatingFileHandler) and getattr(h, "_swingbot_logsetup", False)]
    return handler


def test_bot_logging_writes_the_shared_format_to_log_file(tmp_path, monkeypatch, restore_root_logging):
    path = tmp_path / "bot.log"
    monkeypatch.setattr(config, "LOG_FILE", str(path))
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")

    bot_core.configure_bot_logging()

    handler = _owned_file_handler(restore_root_logging)
    assert (handler.maxBytes, handler.backupCount) == (5 * 1024 * 1024, 3)
    logging.getLogger("swingbot.core.scanning.scan_run").info("hello")
    handler.flush()
    assert re.search(r"\[INFO\] \[-\] swingbot\.core\.scanning\.scan_run: hello", path.read_text())


def test_sighup_reapplies_log_level_through_the_one_setter(monkeypatch):
    applied = []
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(bot_core.config, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(bot_core, "apply_log_level", applied.append)
    monkeypatch.setattr(bot_core, "_reload_callbacks", [])

    bot_core._handle_reload_signal()

    assert applied == ["DEBUG"]


def test_sighup_without_a_level_change_leaves_the_level_alone(monkeypatch):
    applied = []
    monkeypatch.setattr(bot_core.config, "reload", lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    monkeypatch.setattr(bot_core, "apply_log_level", applied.append)
    monkeypatch.setattr(bot_core, "_reload_callbacks", [])

    bot_core._handle_reload_signal()

    assert applied == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_bot_core_logging.py`
Expected: FAIL. `bot_core` has no attribute `configure_bot_logging`, and `monkeypatch.setattr(bot_core, "apply_log_level", …)` raises `AttributeError`.

- [ ] **Step 3: Replace the handler block**

In `swingbot/bot_core.py`, delete the import `from logging.handlers import RotatingFileHandler`. Replace the whole block from the comment `# Two handlers on the root logger: console (same as before -- …` through `_root_logger.addHandler(_file_handler)` with:

```python
from swingbot.core.infra.logsetup import apply_log_level, configure_logging


def configure_bot_logging() -> None:
    """Console (`docker compose logs -f bot`) plus logs/bot.log, which the
    admin container's Logs page reads off the shared bind mount. 5MB x 3
    backups; older history rolls off. Format and handlers are shared with
    the admin process (swingbot/core/infra/logsetup.py)."""
    configure_logging(config.LOG_FILE, config.LOG_LEVEL,
                      max_bytes=5 * 1024 * 1024, backups=3)


configure_bot_logging()
```

Place the `from swingbot.core.infra.logsetup import …` line with the other `from swingbot…` imports at the top of the file, not mid-module. Leave `log = logging.getLogger("swing-bot")` untouched; V111-6 renames it.

- [ ] **Step 4: Use the one setter on SIGHUP**

In `_handle_reload_signal`, replace:

```python
    if "LOG_LEVEL" in changed:
        new_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
        logging.getLogger().setLevel(new_level)
```

with:

```python
    if "LOG_LEVEL" in changed:
        apply_log_level(config.LOG_LEVEL)
```

- [ ] **Step 5: Confirm nothing else referenced the removed names**

Run: `git grep -n "_file_handler\|_console_handler\|_root_logger\|_log_formatter" -- swingbot tests scripts bot.py`
Expected: no output.

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/test_bot_core_logging.py`
Expected: PASS (3 tests).
Run: `python scripts/dev/testrun.py file tests/test_bot_core.py`
Expected: PASS (unchanged).

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/bot_core.py`
Expected: no function this task changed appears at 15 or above. `_handle_reload_signal` is below C.

- [ ] **Step 8: Commit**

```bash
git add swingbot/bot_core.py tests/test_bot_core_logging.py
git commit -m "refactor(v111): bot process logs through configure_logging; SIGHUP uses apply_log_level

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/bot_core.py tests/test_bot_core_logging.py
```

---

### Task V111-3: The admin process configures the root logger

**Files:**
- Modify: `admin_ui.py`
- Modify: `swingbot/admin/app.py` (delete the handler block, currently lines 89-97, and the now-unused `logging` / `RotatingFileHandler` imports)
- Create: `tests/admin/test_admin_logging.py`

**Interfaces:**
- Consumes: V111-1 `configure_logging`, fixture `restore_root_logging`.
- Produces: `admin_ui.setup_logging() -> None`, `admin_ui.ADMIN_LOG_MAX_BYTES = 5 * 1024 * 1024`, `admin_ui.ADMIN_LOG_BACKUPS = 2`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_admin_logging.py`:

```python
"""v111 §1: the admin process configures the ROOT logger, so INFO from any
swingbot.admin.* module reaches admin.log (before v111 only app.logger and
werkzeug had a handler, and every other module's INFO was dropped)."""
import logging
import re
from logging.handlers import RotatingFileHandler

import admin_ui
from swingbot import config


def _owned_file_handler(root):
    [handler] = [h for h in root.handlers
                 if isinstance(h, RotatingFileHandler) and getattr(h, "_swingbot_logsetup", False)]
    return handler


def test_admin_module_info_reaches_admin_log(tmp_path, monkeypatch, restore_root_logging):
    path = tmp_path / "admin.log"
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(path))
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")

    admin_ui.setup_logging()

    handler = _owned_file_handler(restore_root_logging)
    assert (handler.maxBytes, handler.backupCount) == (5 * 1024 * 1024, 2)
    logging.getLogger("swingbot.admin.events.stream").info("client connected")
    handler.flush()
    assert re.search(r"\[INFO\] \[-\] swingbot\.admin\.events\.stream: client connected",
                     path.read_text())


def test_werkzeug_request_lines_stay_at_info_under_a_warning_level(tmp_path, monkeypatch,
                                                                    restore_root_logging):
    monkeypatch.setattr(config, "ADMIN_LOG_FILE", str(tmp_path / "admin.log"))
    monkeypatch.setattr(config, "LOG_LEVEL", "WARNING")

    admin_ui.setup_logging()

    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger("werkzeug").getEffectiveLevel() == logging.INFO


def test_importing_the_app_attaches_no_handlers_of_its_own():
    import swingbot.admin.app as app_mod

    assert not hasattr(app_mod, "_admin_file_handler")
    assert not any(isinstance(h, RotatingFileHandler)
                   for h in logging.getLogger("werkzeug").handlers)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_admin_logging.py`
Expected: FAIL. `admin_ui` has no attribute `setup_logging`, and `app_mod._admin_file_handler` exists.

- [ ] **Step 3: Remove the ad-hoc wiring from `swingbot/admin/app.py`**

Delete this block:

```python
# Wire Flask + Werkzeug request logs to admin.log so the Logs page can show
# admin UI activity separately from the bot's own log stream.
_admin_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_admin_file_handler = RotatingFileHandler(config.ADMIN_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2)
_admin_file_handler.setFormatter(_admin_log_fmt)
app.logger.addHandler(_admin_file_handler)
app.logger.setLevel(logging.INFO)
logging.getLogger("werkzeug").addHandler(_admin_file_handler)
logging.getLogger("werkzeug").setLevel(logging.INFO)
```

Then run `git grep -n "logging\|RotatingFileHandler" -- swingbot/admin/app.py`. Delete `import logging` and `from logging.handlers import RotatingFileHandler` if nothing else in the file uses them. At plan time nothing did.

- [ ] **Step 4: Rewrite `admin_ui.py`**

Replace the whole file with:

```python
"""
Admin web UI -- entry point. The actual implementation lives at
swingbot/admin/app.py; this file configures logging and launches it.

Run with: python admin_ui.py
Listens on ADMIN_HOST:ADMIN_PORT (default 0.0.0.0:1234).
"""
import logging

from swingbot import config
from swingbot.core.infra.logsetup import configure_logging

ADMIN_LOG_MAX_BYTES = 5 * 1024 * 1024
ADMIN_LOG_BACKUPS = 2


def setup_logging() -> None:
    """Root logging for the admin process: console plus logs/admin.log (5MB x 2).

    Werkzeug request lines stay pinned at INFO whatever LOG_LEVEL says, as
    they were before v111, so the Logs page still shows admin activity."""
    configure_logging(config.ADMIN_LOG_FILE, config.LOG_LEVEL,
                      max_bytes=ADMIN_LOG_MAX_BYTES, backups=ADMIN_LOG_BACKUPS)
    logging.getLogger("werkzeug").setLevel(logging.INFO)


if __name__ == "__main__":
    # Logging first, so anything logged while importing the app lands in admin.log.
    setup_logging()
    from swingbot.admin.app import main
    from swingbot.core.infra.deploy_marker import record_boot
    record_boot("admin")
    main()
```

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_admin_logging.py`
Expected: PASS (3 tests).
Run: `python scripts/dev/testrun.py file tests/admin/test_admin_app_isolation.py`
Expected: PASS (unchanged).

- [ ] **Step 6: Syntax and complexity**

Run: `python -m py_compile admin_ui.py swingbot/admin/app.py`
Expected: no output.
Run: `python -m radon cc -s -n C admin_ui.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add admin_ui.py swingbot/admin/app.py tests/admin/test_admin_logging.py
git commit -m "fix(v111): admin process configures the root logger -- admin-module INFO reaches admin.log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- admin_ui.py swingbot/admin/app.py tests/admin/test_admin_logging.py
```

---

### Task V111-4: Every scan runs inside a scan id, and the scan's thread pools carry it

Load the `alert-surface` skill first (this edits `scan_run.py`).

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (`run_scan` only)
- Modify: `swingbot/core/scanning/fetch.py` (`map_tickers`)
- Modify: `swingbot/core/marketdata/providers/router.py` (`_attempt`)
- Create: `tests/scanning/test_run_scan_scan_id.py`
- Create: `tests/scanning/test_map_tickers_context.py`
- Create: `tests/marketdata/test_router_scan_context.py`

**Interfaces:**
- Consumes: V111-1 `scan_context`, `new_scan_id`, `scan_id_var`, `with_current_context`.
- Produces: `scan_run._run_scan_in_context(horizon_filter, require_confirmation, bot, progress, min_confluence) -> list`. It is the old `run_scan` body moved verbatim, and `run_scan` keeps its exact signature and return.

**Audit result (spec §2), recorded here and in `map_tickers`'s comment:**

| Site | Reached from a scan? | Context today | Action |
|---|---|---|---|
| `scan_run.run_scan` → `asyncio.to_thread(_sync_run_scan, …)` | yes | copied by `to_thread` | none |
| `fetch.map_tickers` → `ThreadPoolExecutor.map` | yes (`_scan_one` workers) | **lost** | wrap with `with_current_context` |
| `providers/router._attempt` → `_pool.submit` | yes (daily bars and live prices during a scan) | **lost** | wrap with `with_current_context` |
| `fetch._run_bounded` and the cold fetch (`ProcessPoolExecutor`, spawn) | yes | a separate process, so no ContextVar and no log handlers | none. The parent logs the outcome inside the scan context. |
| `market/events.warm_earnings_cache_background` | no (admin watchlist API) | n/a | none |
| `market/earnings_history.refresh_watchlist_earnings` | no (weekly loop) | n/a | none |
| `run_in_executor` | no call sites exist in `swingbot/` | n/a | none |

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_run_scan_scan_id.py`:

```python
"""v111 §2: every scan runs inside one scan id; outside a scan the id is '-'."""
import asyncio
import re

import pytest

from swingbot import config
from swingbot.core.infra.logsetup import scan_id_var
from swingbot.core.scanning import runstate, scan_run


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    # Same isolation as tests/scanning/test_run_scan_publishes_progress.py.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_mark_running", lambda running: None)
    monkeypatch.setattr(runstate, "_clear_stop", lambda: None)
    return tmp_path


def _record_ids(monkeypatch):
    seen = []

    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence):
        seen.append(scan_id_var.get())
        return [], [], []

    monkeypatch.setattr(scan_run, "_sync_run_scan", fake_sync_run)
    return seen


def test_the_scan_worker_thread_sees_the_scan_id(data_dir, monkeypatch):
    seen = _record_ids(monkeypatch)
    asyncio.run(scan_run.run_scan())
    assert len(seen) == 1 and re.fullmatch(r"s-\d{4}[a-z0-9]{2}", seen[0])
    assert scan_id_var.get() == "-"


def test_two_scans_get_their_own_ids(data_dir, monkeypatch):
    seen = _record_ids(monkeypatch)

    async def two_scans():
        await scan_run.run_scan()
        await scan_run.run_scan()

    asyncio.run(two_scans())
    assert len(seen) == 2 and all(sid.startswith("s-") for sid in seen)


def test_a_scan_that_raises_still_resets_the_id(data_dir, monkeypatch):
    def boom(*args):
        raise RuntimeError("fetch died")

    monkeypatch.setattr(scan_run, "_sync_run_scan", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(scan_run.run_scan())
    assert scan_id_var.get() == "-"
```

Create `tests/scanning/test_map_tickers_context.py`:

```python
"""v111 §2: map_tickers' pool workers log with the caller's scan id."""
from swingbot.core.infra.logsetup import scan_context, scan_id_var
from swingbot.core.scanning import fetch


def test_pool_workers_inherit_the_scan_id():
    with scan_context("s-1111ab"):
        got = fetch.map_tickers(lambda t: scan_id_var.get(), ["A", "B", "C", "D"], workers=3)
    assert got == ["s-1111ab"] * 4


def test_serial_path_is_unchanged():
    with scan_context("s-1112ab"):
        got = fetch.map_tickers(lambda t: (t, scan_id_var.get()), ["A"], workers=1)
    assert got == [("A", "s-1112ab")]
```

Create `tests/marketdata/test_router_scan_context.py`:

```python
"""v111 §2: the Alpaca call runs on the router's pool in the caller's scan context."""
from swingbot.core.infra.logsetup import scan_context, scan_id_var
from swingbot.core.marketdata.providers import router
from tests.marketdata.test_provider_router import FakeProvider, _use, enabled  # noqa: F401


class _ContextProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.seen = []

    def daily_bars(self, tickers, period):
        self.seen.append(scan_id_var.get())
        return {}


def test_alpaca_call_runs_in_the_callers_scan_context(enabled, monkeypatch):
    prov = _ContextProvider()
    _use(monkeypatch, prov)
    with scan_context("s-1200ab"):
        router.daily_bars(["AAPL"], "2y", lambda tickers, period: {})
    assert prov.seen == ["s-1200ab"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_run_scan_scan_id.py`
Expected: FAIL. The worker sees `"-"`, which does not match `s-\d{4}…`.
Run: `python scripts/dev/testrun.py file tests/scanning/test_map_tickers_context.py`
Expected: FAIL. The pool path returns `["-", …]`; the serial test passes already.
Run: `python scripts/dev/testrun.py file tests/marketdata/test_router_scan_context.py`
Expected: FAIL with `["-"] != ["s-1200ab"]`.

- [ ] **Step 3: Wrap `run_scan`**

In `swingbot/core/scanning/scan_run.py`, add to the imports:

```python
from swingbot.core.infra.logsetup import new_scan_id, scan_context
```

Split `run_scan` in two. Keep `run_scan`'s signature and its whole docstring. Append this paragraph to the docstring:

```
    v111: every line this scan logs -- here, in the _sync_run_scan worker
    thread (asyncio.to_thread copies the context) and in map_tickers' pool
    (which submits through with_current_context) -- carries one scan id, so
    `grep s-1405k3 logs/bot.log` shows the scan end to end.
```

The body of `run_scan` becomes:

```python
    with scan_context(new_scan_id()):
        return await _run_scan_in_context(horizon_filter, require_confirmation, bot,
                                          progress, min_confluence)
```

Directly below it, add the moved body. Everything from `started = time.monotonic()` through `return alerts` moves verbatim:

```python
async def _run_scan_in_context(horizon_filter, require_confirmation, bot, progress,
                               min_confluence) -> list:
    """run_scan's body, run inside the scan id set by run_scan."""
    started = time.monotonic()
    async with _scan_lock:
        # ... the existing body, unchanged, down to and including `return alerts`
```

- [ ] **Step 4: Carry the context into `map_tickers`' pool**

In `swingbot/core/scanning/fetch.py`, add `from swingbot.core.infra.logsetup import with_current_context` to the imports. In `map_tickers`, replace:

```python
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(safe, tickers))
```

with:

```python
    # v111 audit: ThreadPoolExecutor threads start in an empty context, so
    # without the wrap every worker line would log scan id "-". Spawned
    # ProcessPoolExecutor children (_run_bounded, the cold fetch) cannot
    # inherit a ContextVar at all; their outcome is logged by this process.
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(with_current_context(safe), tickers))
```

- [ ] **Step 5: Carry the context into the router's pool**

In `swingbot/core/marketdata/providers/router.py`, add `from swingbot.core.infra.logsetup import with_current_context` to the imports. In `_attempt`, replace:

```python
        result = _pool.submit(getattr(prov, method), *args).result(
            timeout=float(config.ALPACA_TIMEOUT_SECONDS))
```

with:

```python
        result = _pool.submit(with_current_context(getattr(prov, method)), *args).result(
            timeout=float(config.ALPACA_TIMEOUT_SECONDS))
```

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_run_scan_scan_id.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_map_tickers_context.py`
Run: `python scripts/dev/testrun.py file tests/marketdata/test_router_scan_context.py`
Expected: all PASS.
Run: `python scripts/dev/testrun.py file tests/scanning/test_run_scan_publishes_progress.py`
Run: `python scripts/dev/testrun.py file tests/marketdata/test_provider_router.py`
Expected: PASS (unchanged).

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/scan_run.py swingbot/core/scanning/fetch.py swingbot/core/marketdata/providers/router.py`
Expected: `run_scan` and `_run_scan_in_context` below C. `_sync_run_scan` still 108. `_fetch_cold_frames` still 13.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/core/scanning/fetch.py swingbot/core/marketdata/providers/router.py tests/scanning/test_run_scan_scan_id.py tests/scanning/test_map_tickers_context.py tests/marketdata/test_router_scan_context.py
git commit -m "feat(v111): every scan runs inside a scan id; scan thread pools carry it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/scan_run.py swingbot/core/scanning/fetch.py swingbot/core/marketdata/providers/router.py tests/scanning/test_run_scan_scan_id.py tests/scanning/test_map_tickers_context.py tests/marketdata/test_router_scan_context.py
```

---

### Task V111-5: Scan-time reload reapplies `LOG_LEVEL`; reload lines logged once

Load the `alert-surface` skill first (this edits `scan_run.py`).

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (the auto-reload block at the top of `_sync_run_scan`)
- Modify: `swingbot/commands/scanning/loops.py` (`config_watcher`'s reload block)
- Create: `tests/scanning/test_scan_reload_log_level.py`
- Create: `tests/commands/test_config_watcher_reload.py`

**Interfaces:**
- Consumes: V111-1 `apply_log_level`, fixture `restore_root_logging`. `loops._apply_scan_interval_change(changed: dict)` already exists (decorated `@on_config_reload`, which returns the function unchanged).
- Produces: `scan_run._reload_config_before_scan() -> dict`, which returns the `changed` dict from `auto_reload_if_changed()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_scan_reload_log_level.py`:

```python
"""v111 §1/§4: the scan-time config auto-reload reapplies LOG_LEVEL (it used
to miss it) and does not repeat config.reload()'s own change log."""
import logging

from swingbot import config
from swingbot.core.scanning import scan_run


def test_scan_time_auto_reload_reapplies_log_level(monkeypatch, restore_root_logging):
    monkeypatch.setattr(scan_run, "auto_reload_if_changed", lambda: {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")

    changed = scan_run._reload_config_before_scan()

    assert changed == {"LOG_LEVEL": ("INFO", "DEBUG")}
    assert logging.getLogger().level == logging.DEBUG


def test_other_changes_leave_the_level_alone(monkeypatch, restore_root_logging):
    logging.getLogger().setLevel(logging.WARNING)
    monkeypatch.setattr(scan_run, "auto_reload_if_changed",
                        lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")

    scan_run._reload_config_before_scan()

    assert logging.getLogger().level == logging.WARNING


def test_the_reload_is_not_logged_a_second_time(monkeypatch, caplog):
    monkeypatch.setattr(scan_run, "auto_reload_if_changed",
                        lambda: {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._reload_config_before_scan()
    assert not any("auto-reloaded" in r.getMessage() for r in caplog.records)
```

Create `tests/commands/test_config_watcher_reload.py`:

```python
"""v111 §1/§4: config_watcher uses apply_log_level, hands interval changes
to the one shared callback, and does not repeat config.reload()'s log."""
import asyncio
import logging

from swingbot import config
from swingbot.commands.scanning import loops


def _quiet_watcher(monkeypatch, tmp_path, changed):
    monkeypatch.setattr(loops, "auto_reload_if_changed", lambda: changed, raising=False)
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE", str(tmp_path / "manual_close_notify.json"))
    monkeypatch.setattr(loops.runstate, "_TRIGGER_FILE", str(tmp_path / "trigger_check.flag"))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "")


def test_watcher_reapplies_log_level_through_the_one_setter(monkeypatch, tmp_path):
    applied = []
    _quiet_watcher(monkeypatch, tmp_path, {"LOG_LEVEL": ("INFO", "DEBUG")})
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(loops, "apply_log_level", applied.append)

    asyncio.run(loops.config_watcher.coro())

    assert applied == ["DEBUG"]


def test_watcher_hands_interval_changes_to_the_shared_callback(monkeypatch, tmp_path):
    calls = []
    changed = {"SCAN_INTERVAL_MINUTES": (5, 10)}
    _quiet_watcher(monkeypatch, tmp_path, changed)
    monkeypatch.setattr(loops, "_apply_scan_interval_change", calls.append)

    asyncio.run(loops.config_watcher.coro())

    assert calls == [changed]


def test_watcher_does_not_repeat_the_reload_log(monkeypatch, tmp_path, caplog):
    _quiet_watcher(monkeypatch, tmp_path, {"MIN_RISK_REWARD_RATIO": (1.5, 2.0)})
    with caplog.at_level(logging.INFO):
        asyncio.run(loops.config_watcher.coro())
    assert not any("auto-reloaded" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_scan_reload_log_level.py`
Expected: FAIL with `AttributeError: … has no attribute '_reload_config_before_scan'`.
Run: `python scripts/dev/testrun.py file tests/commands/test_config_watcher_reload.py`
Expected: FAIL. `monkeypatch.setattr(loops, "apply_log_level", …)` raises `AttributeError`, the interval test records `[]`, and the log test finds "Config auto-reloaded from .env".

- [ ] **Step 3: Extract the scan-time reload**

In `swingbot/core/scanning/scan_run.py`, add `apply_log_level` to the V111-4 import (`from swingbot.core.infra.logsetup import apply_log_level, new_scan_id, scan_context`). Add this function above `_sync_run_scan`:

```python
def _reload_config_before_scan() -> dict:
    """Pick up .env edits saved since the last scan (e.g. via the admin UI).
    This works even without Docker socket / SIGHUP -- settings saved in the
    UI take effect on the next scan.

    config.reload() already logs every changed value (masked for secrets),
    so nothing is logged here; this only applies what a reload alone cannot."""
    changed = auto_reload_if_changed()
    if "LOG_LEVEL" in changed:
        apply_log_level(config.LOG_LEVEL)
    return changed
```

In `_sync_run_scan`, replace:

```python
    # Auto-reload config if .env was changed on disk since last load
    # (e.g. via the admin UI). This works even without Docker socket /
    # SIGHUP -- settings saved in the UI take effect on the next scan.
    changed = auto_reload_if_changed()
    if changed:
        log.info("Config auto-reloaded: %s", ", ".join(
            f"{k}={v[1]!r}" for k, v in changed.items()
        ))
```

with:

```python
    _reload_config_before_scan()
```

(`changed` is not read anywhere else in `_sync_run_scan`. Confirm with `awk 'NR>=170 && NR<=1000 && /changed/' swingbot/core/scanning/scan_run.py`, which should show only comment lines.)

- [ ] **Step 4: One level setter and one interval path in `config_watcher`**

In `swingbot/commands/scanning/loops.py`, add `from swingbot.core.infra.logsetup import apply_log_level` to the imports. In `config_watcher`, replace:

```python
    changed = await asyncio.to_thread(auto_reload_if_changed)
    if changed:
        # LOG_LEVEL change needs the Python logging level updated too
        if "LOG_LEVEL" in changed:
            import logging
            logging.getLogger().setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
        if "SCAN_INTERVAL_MINUTES" in changed and session_scan.is_running():
            session_scan.change_interval(minutes=config.SCAN_INTERVAL_MINUTES)
            log.info("Scan interval hot-reloaded to every %d min (takes effect next tick).",
                     config.SCAN_INTERVAL_MINUTES)
        _apply_market_data_refresh_config(changed)

        log.info("Config auto-reloaded from .env -- %d setting(s) changed: %s",
                 len(changed), ", ".join(f"{k}={v[1]!r}" for k, v in changed.items()))
```

with:

```python
    changed = await asyncio.to_thread(auto_reload_if_changed)
    if changed:
        # config.reload() already logged what changed (masked); SIGHUP and
        # this watcher share the one interval/market-data path below.
        if "LOG_LEVEL" in changed:
            apply_log_level(config.LOG_LEVEL)
        _apply_scan_interval_change(changed)
```

Leave the `_notify_keys` Discord-notice code that follows unchanged. `_apply_scan_interval_change` does exactly what the removed inline block did (same condition, same `change_interval`, then `_apply_market_data_refresh_config(changed)`), and its log line is now the only "Scan interval hot-reloaded" line.

- [ ] **Step 5: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_scan_reload_log_level.py`
Run: `python scripts/dev/testrun.py file tests/commands/test_config_watcher_reload.py`
Expected: PASS.
Run: `python scripts/dev/testrun.py file tests/commands/test_config_watcher_task.py`
Run: `python scripts/dev/testrun.py file tests/test_config_reload.py`
Expected: PASS (unchanged).

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py`
Expected: `_sync_run_scan` ≤ 108 (it loses a branch), `config_watcher` < 27, `_reload_config_before_scan` below C.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py tests/scanning/test_scan_reload_log_level.py tests/commands/test_config_watcher_reload.py
git commit -m "fix(v111): scan-time auto-reload reapplies LOG_LEVEL; reload and interval lines logged once

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py tests/scanning/test_scan_reload_log_level.py tests/commands/test_config_watcher_reload.py
```
