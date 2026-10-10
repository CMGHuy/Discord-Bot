# v148 Ops hardening, part 2: swallowed helper, spawn round-trip, heartbeat merge, first scan conversion

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH7:" -A 260 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O3 "Heartbeat writes become key-level merges", § O5)
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` — Global Constraints, Parallelisation and the task ledger are binding here and are not repeated.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`.

Shared rule for every conversion in this part (index § Global Constraints, "Behaviour-preserving conversion"): `swallowed()` calls the logger's own level method (`log.warning`, `log.error`, `log.debug`, …) with the site's message, args and `exc_info`, so a test that patches `log.warning` or reads `caplog` still sees the same call. Nothing else in a handler changes.

# Phase B — swallowed-error counting and heartbeat merge

### Task OH6: `swallowed` helper

**Model:** sonnet — a new leaf module with a lock and logging semantics, fully specified, no cross-package wiring.

**Files:**
- Create: `swingbot/core/infra/swallowed.py`
- Create: `tests/infra/test_swallowed.py`

**Contract (ledger, final):** `swallowed(log, tag, exc, msg="", *args, level=logging.WARNING, exc_info=False) -> None`; `snapshot() -> dict[str, dict]` (tag → `{"count", "first_at", "last_at", "last_error"}`); `merge(counts) -> None`; `reset() -> None`; `STARTED_AT: str`. The record carries `extra={"swallowed_tag": tag}`. The module imports nothing from `swingbot`.

Design points the code below encodes:
- The record is emitted through the logger's **own level method** (`log.warning` for `WARNING`, `log.error` for `ERROR`, …) found with `logging.getLevelName(level).lower()`. Existing tests patch those methods (`patch.object(fetch.log, "error")` in `tests/scanning/test_cold_fetch_pool.py:80,87`, `patch.object(analyze.log, "warning")` in `tests/scanning/test_engine_v2_plans.py:879`, `patch.object(refresh_mod.log, ...)` in `tests/marketdata/test_data_refresh.py`), and they must keep seeing the converted call. A non-standard level falls back to `functools.partial(log.log, level)`, which adds no Python frame, so `stacklevel=2` still points at the caller.
- `log.exception(m, *a)` is `log.error(m, *a, exc_info=True)`, so `level=logging.ERROR, exc_info=True` reproduces it exactly.
- `msg=""` (a site that logged nothing) logs `"swallowed %s: %s"` with the tag and `last_error`.
- The count is taken before the log call.

- [ ] **Step 0: Confirm the worktree and that the module is new**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening status --short --branch
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -n "swallowed" -- 'swingbot/*.py' | head
```

Expected: branch `2026-10-09-v148-ops-hardening`, a clean tree, and no `swallowed` hits in `swingbot/`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/infra/test_swallowed.py`:

```python
"""v148 O5: the swallowed-error counter -- per-tag counts, merge, thread
safety, and a log record identical to the one the handler emitted before."""
import ast
import datetime as dt
import logging
import pathlib
import threading
from unittest.mock import patch

import pytest

from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed

LOG = logging.getLogger("tests.infra.swallowed_site")
MODULE_PATH = pathlib.Path(swallowed_mod.__file__)


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


def _site(level=logging.WARNING, exc_info=False):
    """A converted handler, as production code writes it."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        swallowed(LOG, "test.site", exc, "fetch %s failed", "AAPL",
                  level=level, exc_info=exc_info)


def _records(caplog):
    return [r for r in caplog.records if r.name == LOG.name]


def test_counts_per_tag_with_first_and_last_seen():
    swallowed(LOG, "a.one", ValueError("x"))
    swallowed(LOG, "a.one", KeyError("y"))
    swallowed(LOG, "b.two", RuntimeError("z"))

    snap = swallowed_mod.snapshot()

    assert snap["a.one"]["count"] == 2
    assert snap["b.two"]["count"] == 1
    assert snap["a.one"]["last_error"] == "KeyError: 'y'"
    assert snap["a.one"]["first_at"] <= snap["a.one"]["last_at"]


def test_last_error_is_type_and_message_truncated_to_200():
    swallowed(LOG, "a.long", ValueError("v" * 500))

    last_error = swallowed_mod.snapshot()["a.long"]["last_error"]

    assert last_error.startswith("ValueError: vvv")
    assert len(last_error) == 200


def test_record_keeps_message_level_and_points_at_the_caller(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        _site()

    [record] = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "fetch AAPL failed"
    assert record.swallowed_tag == "test.site"
    assert record.funcName == "_site"
    assert record.exc_info is None


def test_error_with_exc_info_matches_log_exception(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        try:
            raise ValueError("boom")
        except ValueError:
            LOG.exception("fetch %s failed", "AAPL")
        _site(level=logging.ERROR, exc_info=True)

    before, after = _records(caplog)
    assert (before.levelno, before.getMessage()) == (after.levelno, after.getMessage())
    assert after.exc_info is not None and after.exc_info[0] is ValueError


def test_a_site_that_logged_nothing_logs_the_tag_at_its_level(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        swallowed(LOG, "a.quiet", ValueError("boom"), level=logging.DEBUG)

    [record] = _records(caplog)
    assert record.levelno == logging.DEBUG
    assert record.getMessage() == "swallowed a.quiet: ValueError: boom"


def test_a_patched_level_method_still_sees_the_call():
    with patch.object(LOG, "warning") as warning:
        _site()

    warning.assert_called_once()
    assert warning.call_args.args == ("fetch %s failed", "AAPL")
    assert warning.call_args.kwargs["extra"] == {"swallowed_tag": "test.site"}


def test_a_non_standard_level_goes_through_log_log(caplog):
    with caplog.at_level(1, logger=LOG.name):
        swallowed(LOG, "a.odd", ValueError("boom"), "odd %s", "level", level=25)

    [record] = _records(caplog)
    assert record.levelno == 25 and record.getMessage() == "odd level"


def test_merge_adds_counts_and_widens_the_span():
    swallowed_mod.merge({"a.one": {"count": 2, "first_at": "2026-10-01T00:00:00+00:00",
                                   "last_at": "2026-10-01T01:00:00+00:00",
                                   "last_error": "ValueError: old"}})
    swallowed_mod.merge({"a.one": {"count": 3, "first_at": "2026-10-01T02:00:00+00:00",
                                   "last_at": "2026-10-01T03:00:00+00:00",
                                   "last_error": "ValueError: new"}})

    entry = swallowed_mod.snapshot()["a.one"]

    assert entry == {"count": 5, "first_at": "2026-10-01T00:00:00+00:00",
                     "last_at": "2026-10-01T03:00:00+00:00", "last_error": "ValueError: new"}


def test_merge_of_an_older_entry_keeps_the_newer_last_error():
    swallowed(LOG, "a.one", ValueError("now"))
    swallowed_mod.merge({"a.one": {"count": 1, "first_at": "2000-01-01T00:00:00+00:00",
                                   "last_at": "2000-01-01T00:00:00+00:00",
                                   "last_error": "ValueError: ancient"}})

    entry = swallowed_mod.snapshot()["a.one"]

    assert entry["count"] == 2
    assert entry["first_at"] == "2000-01-01T00:00:00+00:00"
    assert entry["last_error"] == "ValueError: now"


def test_merge_of_nothing_changes_nothing():
    swallowed_mod.merge({})
    swallowed_mod.merge(None)
    assert swallowed_mod.snapshot() == {}


def test_snapshot_is_a_copy():
    swallowed(LOG, "a.one", ValueError("x"))
    snap = swallowed_mod.snapshot()
    snap["a.one"]["count"] = 99
    assert swallowed_mod.snapshot()["a.one"]["count"] == 1


def test_counting_is_thread_safe():
    def hammer():
        for _ in range(500):
            swallowed(LOG, "a.threads", ValueError("x"), level=logging.DEBUG)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert swallowed_mod.snapshot()["a.threads"]["count"] == 4000


def test_started_at_is_a_utc_iso_timestamp():
    parsed = dt.datetime.fromisoformat(swallowed_mod.STARTED_AT)
    assert parsed.utcoffset() == dt.timedelta(0)


def test_module_is_a_leaf():
    """Spawned fetch children and runstate import it; a swingbot import here
    could close a cycle."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names]
    imported += [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not [name for name in imported if name.startswith("swingbot")]
```

- [ ] **Step 2: Run them to watch them fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/infra/test_swallowed.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.infra.swallowed'`.

- [ ] **Step 3: Write the module**

Create `$WT/swingbot/core/infra/swallowed.py`:

```python
"""Count every swallowed exception per call-site tag (v148 O5).

A leaf module: it imports nothing from ``swingbot``, so any module -- a
spawned fetch child included -- can import it without closing a cycle.

``swallowed()`` replaces the body of an ``except Exception`` handler that does
not re-raise. It logs through the *caller's* logger, at the caller's level,
with the caller's message and ``exc_info`` -- so converting a site changes no
log line -- tags the record with ``extra={"swallowed_tag": tag}``, and counts
the tag. Counts live in this process only: ``fetch._counted_call`` carries a
spawned child's ``snapshot()`` back to the parent, which ``merge()``s it, and
the bot flushes its snapshot into the heartbeat row every tick
(``runstate._write_heartbeat``). Tags are ``<area>.<function>`` string
literals, unique per site (``tests/infra/test_swallowed_ratchet.py``).
"""
from __future__ import annotations

import datetime as dt
import functools
import logging
import threading

_LAST_ERROR_MAX = 200

#: Process boot (UTC ISO): the "since" of every count this process holds.
STARTED_AT: str = dt.datetime.now(dt.timezone.utc).isoformat()

_lock = threading.Lock()
_counts: dict[str, dict] = {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _describe(exc: BaseException) -> str:
    """``Type: message``, capped -- no traceback, no locals."""
    return f"{type(exc).__name__}: {exc}"[:_LAST_ERROR_MAX]


def _emitter(log: logging.Logger, level: int):
    """The logger's own level method (``log.warning`` for WARNING, ...), so a
    test that patches ``log.warning`` still sees a converted site's call.
    ``partial(log.log, level)`` for a non-standard level: a partial adds no
    Python frame, so ``stacklevel=2`` still names the caller."""
    method = getattr(log, logging.getLevelName(level).lower(), None)
    return method if method is not None else functools.partial(log.log, level)


def _count(tag: str, error: str) -> None:
    now = _now()
    with _lock:
        entry = _counts.get(tag)
        if entry is None:
            _counts[tag] = {"count": 1, "first_at": now, "last_at": now, "last_error": error}
            return
        entry["count"] += 1
        entry["last_at"] = now
        entry["last_error"] = error


def swallowed(log: logging.Logger, tag: str, exc: BaseException, msg: str = "", *args,
              level: int = logging.WARNING, exc_info: bool = False) -> None:
    """Count `tag` and log `msg % args` exactly as the handler did before.

    ``log.exception(m, *a)`` becomes ``level=logging.ERROR, exc_info=True``.
    With no `msg` (a handler that logged nothing) it logs the tag and error.
    """
    error = _describe(exc)
    _count(tag, error)
    if not msg:
        msg, args = "swallowed %s: %s", (tag, error)
    _emitter(log, level)(msg, *args, exc_info=exc_info,
                         extra={"swallowed_tag": tag}, stacklevel=2)


def snapshot() -> dict[str, dict]:
    """A deep-enough copy: tag -> {count, first_at, last_at, last_error}."""
    with _lock:
        return {tag: dict(entry) for tag, entry in _counts.items()}


def _merge_one(tag: str, other: dict) -> None:
    mine = _counts.get(tag)
    if mine is None:
        _counts[tag] = dict(other)
        return
    mine["count"] += int(other.get("count") or 0)
    mine["first_at"] = min(mine["first_at"], other.get("first_at") or mine["first_at"])
    if (other.get("last_at") or "") > mine["last_at"]:
        mine["last_at"] = other["last_at"]
        mine["last_error"] = other.get("last_error", mine["last_error"])


def merge(counts: dict[str, dict] | None) -> None:
    """Add another process's snapshot (a spawned child's delta) to ours.
    ISO-8601 UTC strings compare correctly as text."""
    if not counts:
        return
    with _lock:
        for tag, other in counts.items():
            _merge_one(tag, other)


def reset() -> None:
    """Tests only."""
    with _lock:
        _counts.clear()
```

- [ ] **Step 4: Run the tests**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/infra/test_swallowed.py
```

Expected: `14 passed`, `0 failed`.

- [ ] **Step 5: Complexity**

```bash
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/infra/swallowed.py
```

Expected: no output (every function below C, i.e. < 11).

- [ ] **Step 6: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/infra/swallowed.py tests/infra/test_swallowed.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH6: swallowed() helper -- per-tag counter, same log record as the handler"
```

### Task OH7: `_run_bounded` carries child counts back

**Model:** opus — process-boundary semantics (spawn pickling, parent-vs-child counting, success-only unwrap) where a mistake double-counts or changes every caller's return shape.

**Files:**
- Modify: `swingbot/core/scanning/fetch.py` (imports; new `_counted_call` above `_run_bounded`; `_run_bounded` body, today `:175-208`)
- Modify: `tests/infra/test_swallowed.py` (append, created by OH6)
- Create: `tests/infra/swallowed_probe.py`

**Contract (ledger, final):** `fetch._counted_call(fn, *args) -> tuple[Any, dict]`. `_run_bounded(fn, args, timeout_seconds, label)` keeps its signature and return shape: `fn`'s own result, or `None` on failure or timeout. Its two failure paths are counted under `scan.run_bounded`. Probe functions `count_then_return(x)` and `sleep_forever()` are module-level so spawn can pickle them.

Why it is shaped this way (spec § O5 "Child processes", index § Global Constraints "Spawn safety"):
- `_run_bounded` submits `_counted_call, fn, *args`. A spawned child starts with an empty counter, so `swallowed_mod.snapshot()` taken at the end of `_counted_call` is exactly that child's delta.
- In the parent process (`multiprocessing.parent_process() is None`), which is where every in-process fake pool in `tests/scanning/` runs `fn`, the counts have already landed in the parent's own counter. `_counted_call` then returns `{}`, so nothing is counted twice.
- The unwrap and `swallowed_mod.merge(counts)` run on the success path only. A raising or killed child returns no counts; its log lines remain. The parent-side `scan.run_bounded` call counts the failure itself.
- Every fake pool in the suite (`tests/scanning/conftest.py:_InlineProcessPool`, `test_cold_fetch_pool._FakePool` with `lambda fn, *a: _done_future(fn(*a))`, the `_InlinePool`s in `test_no_cross_ticker_mixing.py`, `test_cold_fetch_splice.py`, `test_crawl_spot.py` and `test_scan_telemetry_sources.py`) calls `fn(*args)`. That `fn` is now `_counted_call`, so the tuple comes back through them unchanged. The kill-path fakes never resolve their future, so nothing is unpacked there.
- The timeout is not an exception, so it passes a constructed `TimeoutError(label)` as `exc`. `tests/scanning/test_cold_fetch_pool.py:80,87` patch `fetch.log.error` and assert the label is in `error.call_args`. `swallowed` calls `log.error` (OH6 `_emitter`), so they stay green unchanged.
- This task converts only `_run_bounded`'s own handler. OH10 converts the rest of `fetch.py` and must leave `_run_bounded` alone.
- The tag `scan.run_bounded` is deliberately used twice inside `_run_bounded`: once in the handler, once on the timeout path, which is not in a handler (spec § O5). OH15's uniqueness assertion has to count tags per `except` handler.

- [ ] **Step 1: Write the probe module**

Create `$WT/tests/infra/swallowed_probe.py`:

```python
"""Module-level workers for tests/infra/test_swallowed.py's real-process
_run_bounded round trips. Spawn pickles a function by its module path, so
these cannot be lambdas or test-local closures."""
import logging
import time

from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)


def count_then_return(x):
    """Swallows twice under one tag, then returns x * 2."""
    for _ in range(2):
        try:
            raise ValueError("probe")
        except ValueError as exc:
            swallowed(log, "probe.count_then_return", exc, "probe %s", x,
                      level=logging.DEBUG)
    return x * 2


def sleep_forever():
    """Outlives any test budget, so _run_bounded's kill path runs."""
    time.sleep(3600)
```

- [ ] **Step 2: Append the failing tests**

Append to `$WT/tests/infra/test_swallowed.py`:

```python
# ---------------------------------------------------------------------------
# OH7: _run_bounded carries a spawned child's counts back to the parent
# ---------------------------------------------------------------------------

class _InlinePool:
    """In-process stand-in for ProcessPoolExecutor: runs the submitted
    callable here, like tests/scanning/conftest.py's _InlineProcessPool."""

    def __init__(self, max_workers=None, mp_context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        from concurrent.futures import Future
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _boom(_x):
    raise RuntimeError("child exploded")


def _probe():
    from tests.infra import swallowed_probe
    return swallowed_probe


def test_counted_call_in_the_parent_returns_no_counts():
    from swingbot.core.scanning import fetch

    assert fetch._counted_call(_probe().count_then_return, 21) == (42, {})
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


def test_counted_call_in_a_child_returns_its_snapshot(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch.multiprocessing, "parent_process", lambda: object())

    result, counts = fetch._counted_call(_probe().count_then_return, 21)

    assert result == 42
    assert counts["probe.count_then_return"]["count"] == 2


def test_inline_pool_keeps_the_return_shape_and_counts_once(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)

    assert fetch._run_bounded(_probe().count_then_return, (21,), 5, "probe") == 42
    assert fetch._run_bounded(dict, (), 5, "probe-dict") == {}
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


def test_a_raising_child_is_counted_under_run_bounded(monkeypatch, caplog):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)

    with caplog.at_level(logging.ERROR, logger=fetch.log.name):
        assert fetch._run_bounded(_boom, (1,), 5, "probe-fail") is None

    entry = swallowed_mod.snapshot()["scan.run_bounded"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: child exploded"
    [record] = [r for r in caplog.records if r.name == fetch.log.name]
    assert record.getMessage() == "probe-fail failed: child exploded"
    assert record.levelno == logging.ERROR and record.exc_info is not None


@pytest.mark.slow
def test_a_spawned_child_counts_travel_back():
    from swingbot.core.scanning import fetch

    out = fetch._run_bounded(_probe().count_then_return, (21,), 120, "probe-spawn")

    assert out == 42
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


@pytest.mark.slow
def test_a_timeout_is_counted_under_run_bounded(caplog):
    from swingbot.core.scanning import fetch

    with caplog.at_level(logging.ERROR, logger=fetch.log.name):
        assert fetch._run_bounded(_probe().sleep_forever, (), 0.5, "probe-stuck") is None

    entry = swallowed_mod.snapshot()["scan.run_bounded"]
    assert entry["count"] == 1 and entry["last_error"] == "TimeoutError: probe-stuck"
    assert any("probe-stuck did not finish within 0.5s" in r.getMessage()
               for r in caplog.records if r.name == fetch.log.name)
```

- [ ] **Step 3: Run them to watch them fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/infra/test_swallowed.py
```

Expected: the OH7 tests fail with `AttributeError: module 'swingbot.core.scanning.fetch' has no attribute '_counted_call'`, and `test_a_raising_child...` / `test_a_timeout...` fail with `KeyError: 'scan.run_bounded'`. OH6's 14 tests pass.

- [ ] **Step 4: Implement in `fetch.py`**

In `$WT/swingbot/core/scanning/fetch.py`, add the imports after `from swingbot.core.infra.logsetup import with_current_context` (line 14):

```python
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed
```

Add this function directly above `def _run_bounded(` (today line 148, after `_SPAWN_CTX = ...`):

```python
def _counted_call(fn, *args):
    """Run fn(*args) and return (result, the swallowed counts it produced).

    _run_bounded submits this in place of fn (v148 O5). A spawned child starts
    with an empty swallowed counter, so its snapshot() is exactly that child's
    delta, carried back with the result the way price_sources already is. Run
    in the parent process -- the in-process fake pools in tests/scanning/ --
    the counts already landed in the parent's own counter, so it returns {}
    rather than count them twice. Module-level so spawn can pickle it.
    """
    result = fn(*args)
    if multiprocessing.parent_process() is None:
        return result, {}
    return result, swallowed_mod.snapshot()
```

In `_run_bounded`, append this paragraph to the end of the docstring (before the closing `"""`):

```python
    v148 O5: fn runs inside _counted_call, which hands back (result, the
    child's swallowed counts). Those counts are merged here on success only:
    a raising or killed child loses its own counts (its log lines remain),
    and both failure paths below are counted under "scan.run_bounded" in
    this, the parent, process. The return shape is unchanged for every
    caller -- fn's own result, or None.
```

Then replace the body from `future = pool.submit(fn, *args)` down to and including the first `log.error(... "treating this as a failed fetch", label, timeout_seconds)` call with:

```python
        future = pool.submit(_counted_call, fn, *args)
        done, _ = _futures_wait([future], timeout=timeout_seconds)
        if future in done:
            try:
                result, counts = future.result()
            except Exception as exc:
                swallowed(log, "scan.run_bounded", exc, "%s failed: %s", label, exc,
                          level=logging.ERROR, exc_info=True)
                return None
            swallowed_mod.merge(counts)
            return result
        swallowed(log, "scan.run_bounded", TimeoutError(label),
                  "%s did not finish within %ss -- killing the worker process and "
                  "treating this as a failed fetch", label, timeout_seconds,
                  level=logging.ERROR)
```

Leave the kill loop, the long `wait=True` comment, `pool.shutdown(wait=True, cancel_futures=True)` and the final `return None` exactly as they are.

- [ ] **Step 5: Run the new tests and every `_run_bounded` caller's tests**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/infra/test_swallowed.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_scan_telemetry_sources.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_crawl_spot.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_cold_fetch_splice.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py
```

Expected: every run `0 failed`, `0 xfailed`; `test_swallowed.py` shows `20 passed`. `test_trade_monitor_task.py` and `test_scan_telemetry_sources.py::test_attrs_survive_spawn_round_trip` use real spawn children. They pass only if `_counted_call` pickles and the tuple is unwrapped before the caller sees it. If either returns `None`, read the `scan.run_bounded` ERROR line in the output for the child's traceback.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning/fetch.py
```

Expected: `_run_bounded` and `_counted_call` absent from the output (both < 11). If another `fetch.py` function is listed, it was listed before this task too, and it must not have grown. Compare against the committed copy without touching the tree: `git -C $WT show HEAD:swingbot/core/scanning/fetch.py > /tmp/fetch_before.py && python -m radon cc -s -n C /tmp/fetch_before.py`.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/scanning/fetch.py tests/infra/test_swallowed.py tests/infra/swallowed_probe.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH7: _run_bounded carries spawned children's swallowed counts back; failures count scan.run_bounded"
```

### Task OH8: Heartbeat key-level merge and runstate flags

**Model:** opus — it changes the write semantics of a row both processes share, from whole-doc read-modify-write to a SQL `doc || patch`; a mistake silently drops liveness keys in production.

**Files:**
- Modify: `swingbot/core/db/repositories/heartbeat.py` (add `merge` after `beat`)
- Modify: `swingbot/commands/scanning/runstate.py` (imports; `_read_heartbeat` `:6-13`; `_update_heartbeat` `:16-25`; `_write_heartbeat` `:28-45`; four new getters/setters after `set_alert_active` `:75-76`)
- Create: `tests/scanning/test_heartbeat_merge.py`

**Contract (ledger, final):** `HeartbeatRepository.merge(self, fields: dict, *, conn=None) -> None`. In `runstate`: `get_stale_alert_active() -> bool`, `set_stale_alert_active(active: bool) -> None`, `get_provider_alert_active() -> bool`, `set_provider_alert_active(active: bool) -> None`. The heartbeat doc gains the key `swallowed: {"since": swallowed_mod.STARTED_AT, "counts": swallowed_mod.snapshot()}`, written every tick by `_write_heartbeat`. Tags: `runstate.read_heartbeat` (DEBUG) and `runstate.update_heartbeat` (WARNING, `"heartbeat write failed"`). OH17, OH18 and OH20 consume these names.

Facts this rests on (brief § 0.3, § 6; index Global Constraints 4 and 6):
- `Repository.patch(key, changes)` (`swingbot/core/db/repositories/base.py:85-98`) splits `changes` into promoted columns (`ts`) and a doc patch. It applies the doc patch as `doc || :patch` in SQL and returns `None` when the row is absent, without raising. So `merge` patches first and falls back to `beat` (an upsert) only on `None`.
- `_update_heartbeat` stops reading the row first. Each writer touches only its own keys: the bot's `timestamp`/`session_active`/`scan_paused`/`swallowed` every tick, the alert flags, and the admin's unpause (`store_write_failure: None`). `record_tick_failure`'s read-then-increment stays as it is (spec § O3). That writer is bot-only, in one loop.
- `doc || {"store_write_failure": null}` stores JSON `null`, which `last()` reads back as `None`, the same as today.
- `runstate.py` has no `logging` import or `log` yet (Global Constraint 6). There are two `runstate` modules. This task edits `swingbot/commands/scanning/runstate.py` only. `swingbot/core/scanning/runstate.py` is a different module and is left alone.
- Every test that reaches the engine gets the worker's Postgres test database lazily through the autouse `_store_database` fixture (`tests/conftest.py:173`), as `tests/scanning/test_heartbeat_outcome.py` does. No explicit DB fixture is needed. The DB is down → those tests skip with the start command, as the rest of the store tests do.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scanning/test_heartbeat_merge.py`:

```python
"""v148 O3/O5: heartbeat writes are key-level merges (doc || patch), so the
bot and the admin never drop each other's keys, and a failed heartbeat
read or write is counted instead of vanishing."""
import logging

import pytest

from swingbot.commands.scanning import runstate
from swingbot.core.db.repositories import heartbeat as heartbeat_mod
from swingbot.core.db.repositories.heartbeat import KEY, HeartbeatRepository
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


class _Broken:
    """A heartbeat repository whose database is gone."""

    def merge(self, fields, *, conn=None):
        raise RuntimeError("db down")

    def last(self, *, conn=None):
        raise RuntimeError("db down")


def test_merge_creates_the_row_when_absent():
    HeartbeatRepository().merge({"a": 1})

    last = HeartbeatRepository().last()
    assert last["a"] == 1 and last["ts"]


def test_merge_touches_only_its_own_keys_and_bumps_ts():
    repo = HeartbeatRepository()
    repo.beat({"a": 1, "b": 2})
    first_ts = repo.last()["ts"]

    repo.merge({"b": 3})

    last = repo.last()
    assert (last["a"], last["b"]) == (1, 3)
    assert last["ts"] >= first_ts
    assert repo.count() == 1


def test_two_writers_with_disjoint_keys_both_survive():
    runstate.set_alert_active(True)                      # bot: tick outcome
    runstate._update_heartbeat({"store_write_failure": None})   # admin: unpause
    runstate._write_heartbeat()                          # bot: next tick's liveness

    state = runstate._read_heartbeat()
    assert state["alert_active"] is True
    assert "store_write_failure" in state and state["store_write_failure"] is None
    assert "timestamp" in state and "swallowed" in state


def test_update_does_not_read_the_row_first(monkeypatch):
    """A writer holding a stale whole-doc view used to write it back over
    the other process's keys. A write that reads nothing cannot."""
    runstate.set_alert_active(True)

    def no_reads(self, *, conn=None):
        raise AssertionError("_update_heartbeat must not read the row")

    monkeypatch.setattr(HeartbeatRepository, "last", no_reads)
    runstate._update_heartbeat({"scan_paused": True})

    row = HeartbeatRepository().get(KEY)
    assert row["alert_active"] is True and row["scan_paused"] is True
    assert "runstate.update_heartbeat" not in swallowed_mod.snapshot()


def test_a_failed_write_is_counted_and_logged_at_warning(monkeypatch, caplog):
    monkeypatch.setattr(heartbeat_mod, "heartbeat_repo", lambda: _Broken())

    with caplog.at_level(logging.DEBUG, logger=runstate.log.name):
        runstate._update_heartbeat({"timestamp": "2026-10-01T00:00:00+00:00"})

    entry = swallowed_mod.snapshot()["runstate.update_heartbeat"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: db down"
    [record] = [r for r in caplog.records if r.name == runstate.log.name]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "heartbeat write failed"


def test_a_failed_read_is_counted_and_reads_as_unknown(monkeypatch, caplog):
    monkeypatch.setattr(heartbeat_mod, "heartbeat_repo", lambda: _Broken())

    with caplog.at_level(logging.DEBUG, logger=runstate.log.name):
        assert runstate._read_heartbeat() == {}
        assert runstate.get_stale_alert_active() is False

    assert swallowed_mod.snapshot()["runstate.read_heartbeat"]["count"] == 2
    assert {r.levelno for r in caplog.records if r.name == runstate.log.name} == {logging.DEBUG}


def test_the_tick_heartbeat_carries_the_swallowed_counts():
    swallowed(logging.getLogger("tests.heartbeat_probe"), "probe.heartbeat",
              ValueError("v"), level=logging.DEBUG)

    runstate._write_heartbeat()

    flushed = runstate._read_heartbeat()["swallowed"]
    assert flushed["since"] == swallowed_mod.STARTED_AT
    assert flushed["counts"]["probe.heartbeat"]["count"] == 1
    assert flushed["counts"]["probe.heartbeat"]["last_error"] == "ValueError: v"


def test_stale_and_provider_alert_flags_round_trip():
    assert runstate.get_stale_alert_active() is False
    assert runstate.get_provider_alert_active() is False

    runstate.set_stale_alert_active(True)
    runstate.set_provider_alert_active(True)
    runstate.set_stale_alert_active(False)

    assert runstate.get_stale_alert_active() is False
    assert runstate.get_provider_alert_active() is True
    assert runstate.get_alert_active() is False
```

- [ ] **Step 2: Run them to watch them fail**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_heartbeat_merge.py
```

Expected: failures with `AttributeError: 'HeartbeatRepository' object has no attribute 'merge'`, `AttributeError: module ... runstate has no attribute 'log'` and `... 'get_stale_alert_active'`, and `KeyError: 'swallowed'`.

- [ ] **Step 3: Add `merge` to the repository**

In `$WT/swingbot/core/db/repositories/heartbeat.py`, add this method directly after `beat`:

```python
    def merge(self, fields: dict, *, conn=None) -> None:
        """Write only `fields` (and a fresh `ts`): `doc || fields` in SQL, so
        two writers with disjoint keys -- the bot's tick, the admin's unpause,
        the alert flags -- never drop each other's keys (v148 O3). `patch`
        returns None when the row does not exist yet; `beat` creates it."""
        stamped = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **fields}
        if self.patch(KEY, stamped, conn=conn) is None:
            self.beat(fields, conn=conn)
```

- [ ] **Step 4: Rewrite the runstate writers**

In `$WT/swingbot/commands/scanning/runstate.py`, replace the import block at the top (`import datetime as dt` … `from swingbot.bot_core import in_session`) with:

```python
import datetime as dt
import logging

from swingbot.bot_core import in_session
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)
```

Replace `_read_heartbeat` and `_update_heartbeat` (today `:6-25`) with:

```python
def _read_heartbeat() -> dict:
    """Current heartbeat state, or {} when absent or unreadable.

    Absent is "unknown", never "failing"."""
    try:
        from swingbot.core.db.repositories.heartbeat import heartbeat_repo
        return heartbeat_repo().last() or {}
    except Exception as exc:
        swallowed(log, "runstate.read_heartbeat", exc, level=logging.DEBUG)
        return {}


def _update_heartbeat(fields: dict) -> None:
    """Merge `fields` into the heartbeat row key by key (`doc || fields` in
    SQL, v148): no read first, so the bot and the admin never write a stale
    whole-doc view over each other's keys. A failed write is counted and
    logged, never raised -- the heartbeat must not take down a tick."""
    try:
        from swingbot.core.db.repositories.heartbeat import heartbeat_repo
        heartbeat_repo().merge(fields)
    except Exception as exc:
        swallowed(log, "runstate.update_heartbeat", exc, "heartbeat write failed")
```

In `_write_heartbeat`, replace the first docstring sentence `Stamps a small JSON file that the admin UI reads to show a blinking bot-liveness dot on the Dashboard.` with `Stamps the bot_heartbeat row that the admin UI reads to show a blinking bot-liveness dot on the Dashboard, and flushes this process's swallowed-error counts (v148 O5) for the System → Scan panel.` Leave the rest of the docstring as it is. Then replace its `_update_heartbeat({...})` call with:

```python
    _update_heartbeat({
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_active": in_session(),
        "scan_paused": is_scan_paused(),
        "swallowed": {"since": swallowed_mod.STARTED_AT,
                      "counts": swallowed_mod.snapshot()},
    })
```

Directly after `set_alert_active` (today `:75-76`), add:

```python
def get_stale_alert_active() -> bool:
    """v148 O3: a stale-scan alert is open (ops_watch.scan_watchdog). Kept in
    the heartbeat row so a restart neither re-posts nor forgets it."""
    return bool(_read_heartbeat().get("stale_alert_active"))


def set_stale_alert_active(active: bool) -> None:
    _update_heartbeat({"stale_alert_active": bool(active)})


def get_provider_alert_active() -> bool:
    """v148 O4: a provider-degradation alert is open (ops_watch.check_provider_health)."""
    return bool(_read_heartbeat().get("provider_alert_active"))


def set_provider_alert_active(active: bool) -> None:
    _update_heartbeat({"provider_alert_active": bool(active)})
```

- [ ] **Step 5: Run the new tests and every existing heartbeat test**

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_heartbeat_merge.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/commands/test_heartbeat_db.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_heartbeat_outcome.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/commands/test_store_write_halt.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/db/test_export_json_ops.py
```

Expected: `test_heartbeat_merge.py` `8 passed`; every run `0 failed`, `0 xfailed`. `test_heartbeat_db.py::test_a_database_failure_does_not_take_down_the_scan_loop` now logs one WARNING `heartbeat write failed` and still passes. If the admin scan test asserts the exact heartbeat doc shape, check the diff. It should show the new `swallowed` key only, and that key is additive (index § Global Constraints, Schema).

- [ ] **Step 6: Complexity**

```bash
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/commands/scanning/runstate.py /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/db/repositories/heartbeat.py
```

Expected: no output.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/db/repositories/heartbeat.py swingbot/commands/scanning/runstate.py tests/scanning/test_heartbeat_merge.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH8: heartbeat writes are key-level merges; stale/provider alert flags; swallowed counts flushed every tick"
```

### Task OH9: Scan conversion A (`scan_run` and five small files)

**Model:** sonnet — a mechanical one-for-one conversion of 21 handlers across six files, where each site's level, message and `exc_info` must be carried over exactly.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (14 handlers)
- Modify: `swingbot/core/scanning/strategy_pass.py` (3 handlers)
- Modify: `swingbot/core/scanning/plan_table.py` (1 handler; adds `import logging` and `log`)
- Modify: `swingbot/core/scanning/lane_overlap.py` (1 handler)
- Modify: `swingbot/core/scanning/outlook_context.py` (1 handler; adds `import logging` and `log`)
- Modify: `swingbot/core/scanning/scan_replay.py` (1 handler; adds `import logging` and `log`)

**Contract:** `scan.*` tags as listed in the table below. The tags are final, because OH15's ratchet asserts them unique repo-wide and OH20's panel shows them. No function signature, return value or fallback changes.

Rules for every site (index § Global Constraints, "Behaviour-preserving conversion"):
- The handler's single log call becomes one `swallowed(log, "<tag>", <exc>, <same message>, <same args>, level=..., exc_info=...)` call. Use the same `log` object, the same message string and args, and the same level and `exc_info`. Omit `level=` for WARNING, which is the default, and omit `exc_info=` when it was absent. Every other statement in the handler (`return`, `continue`, assignments) stays exactly where it is.
- `log.exception(m, *a)` becomes `level=logging.ERROR, exc_info=True`.
- A handler with no `as` gains `as exc`. A handler that already binds `as e` keeps `e`. Neither name is used after its handler anywhere in these functions (checked: the only other `exc` in `_sync_run_scan` is the handler-local one at `:877`).
- `scan_run._persist_plan_v2` (`:334`) contains a `raise` (`write_failure.StoreWriteHalt`). It is **not** converted.
- Imports: in each modified file, add `from swingbot.core.infra.swallowed import swallowed` to the `swingbot` import group. `scan_run.py`, `strategy_pass.py` and `lane_overlap.py` already have `import logging` and `log = logging.getLogger(__name__)`. The other three files gain both lines.

| File:line (today) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `scan_run.py:136` | `_compression_seen` | `scan.compression_seen` | WARNING / True |
| `scan_run.py:245` | `get_regime` | `scan.get_regime` | WARNING / True |
| `scan_run.py:311` | `_earnings_in_window` | `scan.earnings_in_window` | DEBUG / — |
| `scan_run.py:443` | `_sync_run_scan` | `scan.run_scan.rs_cache` | WARNING / True |
| `scan_run.py:468` | `_sync_run_scan` | `scan.run_scan.sector_etfs` | WARNING / True |
| `scan_run.py:493` | `_sync_run_scan` | `scan.run_scan.market_context` | ERROR / True (was `log.exception`) |
| `scan_run.py:508` | `_sync_run_scan` | `scan.run_scan.regime_series` | DEBUG / True |
| `scan_run.py:877` | `_sync_run_scan` | `scan.run_scan.chart_data` | WARNING / True |
| `scan_run.py:959` | `_sync_run_scan` | `scan.run_scan.trendline_fit` | WARNING / True |
| `scan_run.py:1042` | `_sync_run_scan` | `scan.run_scan.trade_chart` | WARNING / True |
| `scan_run.py:1088` | `_sync_run_scan` | `scan.run_scan.intraday` | DEBUG / — |
| `scan_run.py:1165` | `_sync_run_scan` | `scan.run_scan.telemetry` | ERROR / True (was `log.exception`) |
| `scan_run.py:1243` | `get_all_unrealized_pnl` | `scan.unrealized_pnl.batch` | WARNING / True |
| `scan_run.py:1253` | `get_all_unrealized_pnl` | `scan.unrealized_pnl.ticker` | WARNING / True |
| `strategy_pass.py:52` | `strategy_signals` | `scan.strategy_signals` | WARNING / True |
| `strategy_pass.py:281` | `_shadow_step` | `scan.shadow_step` | WARNING / True |
| `strategy_pass.py:315` | `run_strategy_pass` | `scan.run_strategy_pass` | WARNING / True |
| `plan_table.py:129` | `_sizing_snapshot` | `scan.sizing_snapshot` | DEBUG / — (logged nothing) |
| `lane_overlap.py:36` | `overlap_line` | `scan.overlap_line` | DEBUG / True |
| `outlook_context.py:55` | `regime_line` | `scan.regime_line` | DEBUG / — (logged nothing) |
| `scan_replay.py:171` | `_regimes` | `scan.scan_replay.regimes` | DEBUG / — (logged nothing) |

`scan.scan_replay.regimes` carries the module name because `outlook_run._regimes` (converted by OH11) has the same function name.

- [ ] **Step 1: Record the before-state**

The verification below is an AST count of untagged handlers in the six files, using the rule OH15's ratchet uses: a handler is untagged if it catches `Exception`, alone or in a tuple, its body calls no `swallowed`, and it contains no `raise`. Save it as a scratch script (it is not committed):

```bash
mkdir -p /tmp/claude-oh9 && cat > /tmp/claude-oh9/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _catches_exception(handler):
    node = handler.type
    names = node.elts if isinstance(node, ast.Tuple) else [node]
    return any(isinstance(n, ast.Name) and n.id == "Exception" for n in names)


def _calls_swallowed(handler):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
               for n in ast.walk(handler))


def _raises(handler):
    return any(isinstance(n, ast.Raise) for n in ast.walk(handler))


for name in sys.argv[1:]:
    tree = ast.parse(Path(name).read_text(encoding="utf-8"))
    lines = [h.lineno for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
             and h.type is not None and _catches_exception(h)
             and not _calls_swallowed(h) and not _raises(h)]
    print(f"{name}: {len(lines)} untagged {sorted(lines)}")
PY
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh9/untagged.py $S/scan_run.py $S/strategy_pass.py $S/plan_table.py $S/lane_overlap.py $S/outlook_context.py $S/scan_replay.py
```

Expected: `scan_run.py: 14 untagged`, `strategy_pass.py: 3`, and `1` each for the other four. That makes 21 handlers in total. If a count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `scan_run.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.notifier import notify_secondary` (`:22`). Then replace each handler body as follows (old → new). The surrounding code is unchanged.

`:136` (`_compression_seen`):
```python
    except Exception as exc:    # noqa: BLE001 -- a damaged audit log must never stop a scan or its Discord alerts
        swallowed(log, "scan.compression_seen", exc,
                  "compression shadow log unreadable -- dedup disabled this scan", exc_info=True)
        return set()
```

`:245` (`get_regime`):
```python
    except Exception as e:
        swallowed(log, "scan.get_regime", e, "Could not fetch market regime: %s", e, exc_info=True)
        return None
```

`:311` (`_earnings_in_window`):
```python
    except Exception as e:
        swallowed(log, "scan.earnings_in_window", e, "Earnings check failed for %s: %s", ticker, e,
                  level=logging.DEBUG)
        return None
```

`:443`:
```python
    except Exception as e:
        swallowed(log, "scan.run_scan.rs_cache", e,
                  "Could not compute relative-strength cache: %s", e, exc_info=True)
        spy_df = None
        rs_cache = None
```

`:468`:
```python
    except Exception as e:
        swallowed(log, "scan.run_scan.sector_etfs", e,
                  "Could not fetch sector ETFs for relative-strength: %s", e, exc_info=True)
        sector_of_ticker = {}
        etf_symbol_of_sector = {}
        sector_etf_frames = {}
```

`:493`:
```python
            except Exception as exc:
                swallowed(log, "scan.run_scan.market_context", exc,
                          "market_context.attach failed for %s", _t,
                          level=logging.ERROR, exc_info=True)
```

`:508`:
```python
        except Exception as exc:
            swallowed(log, "scan.run_scan.regime_series", exc, "regime_series computation failed",
                      level=logging.DEBUG, exc_info=True)
```

`:877`:
```python
            except Exception as exc:
                swallowed(log, "scan.run_scan.chart_data", exc,
                          "Could not fetch chart data for %s; posting without chart: %s",
                          result.ticker, exc, exc_info=True)
```

`:959`:
```python
                except Exception as exc:
                    swallowed(log, "scan.run_scan.trendline_fit", exc,
                              "Trendline fit failed for %s (%s) -- trade stores no fit",
                              result.ticker, result.horizon_key, exc_info=True)
```

`:1042`:
```python
        except Exception as e:
            swallowed(log, "scan.run_scan.trade_chart", e,
                      "Could not generate trade chart for %s: %s", result.ticker, e, exc_info=True)
            chart_path, chart_filename = None, None
```

`:1088`:
```python
        except Exception as e:
            swallowed(log, "scan.run_scan.intraday", e,
                      "Intraday confirmation unavailable for %s: %s", result.ticker, e,
                      level=logging.DEBUG)
            item.intraday = None
```

`:1165`:
```python
    except Exception as exc:
        swallowed(log, "scan.run_scan.telemetry", exc,
                  "Scan health telemetry failed -- not blocking the scan result",
                  level=logging.ERROR, exc_info=True)
```

`:1243`:
```python
    except Exception as exc:
        swallowed(log, "scan.unrealized_pnl.batch", exc,
                  "get_all_unrealized_pnl: batch price fetch failed: %s", exc, exc_info=True)
        price_cache = {}
```

`:1253`:
```python
            except Exception as exc:
                swallowed(log, "scan.unrealized_pnl.ticker", exc,
                          "get_all_unrealized_pnl: could not fetch price for %s: %s", ticker, exc,
                          exc_info=True)
                price_cache[ticker] = None
```

- [ ] **Step 3: Convert `strategy_pass.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.edge.gates import PULLBACK_VOLUME_REASON, pullback_dryup_blocks` (`:16`).

`:52` (`strategy_signals`). The old handler did `import logging` and called `logging.getLogger(__name__)`, which is the same logger object as the module-level `log` (`:20`). **Do not reference `logging` anywhere in this handler.** The function has another local `import logging` on the no-SPY branch (`:44`), which makes `logging` a local name throughout the function body. Reading `logging.WARNING` here would raise `UnboundLocalError` whenever that branch did not run. WARNING is the default level, so no `level=` is needed:

```python
        except Exception as exc:
            swallowed(log, "scan.strategy_signals", exc,
                      "strategy pass: %s/%s raised -- skipped", strategy, horizon_key, exc_info=True)
            continue
```

`:281` (`_shadow_step`):
```python
    except Exception as exc:
        swallowed(log, "scan.shadow_step", exc,
                  "compression shadow: %s/%s failed -- continuing", ticker, horizon, exc_info=True)
        return
```

`:315` (`run_strategy_pass`):
```python
        except Exception as exc:
            swallowed(log, "scan.run_strategy_pass", exc,
                      "strategy pass: %s failed -- continuing", ticker, exc_info=True)
```

- [ ] **Step 4: Convert the four small files**

`plan_table.py`: make the import block (`:7-12`) start with `import logging`, then a blank line, then the existing `from swingbot ...` lines plus `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.backtesting.registry import Badge, decay_for`. Add `log = logging.getLogger(__name__)` on its own line after the block, followed by two blank lines. Then convert `_sizing_snapshot` (`:127-130`):

```python
    try:
        return account.compute_position_size(entry, plan.stop_loss)
    except Exception as exc:
        swallowed(log, "scan.sizing_snapshot", exc, level=logging.DEBUG)
        return None
```

`lane_overlap.py`: add `from swingbot.core.infra.swallowed import swallowed` before `from swingbot.core.tracking.origin import NEXT_SESSION, origin_of` (`:12`), then convert `overlap_line` (`:34-38`):

```python
    try:
        others = _other_lane_trades(ticker, viewer_origin)
    except Exception as exc:
        swallowed(log, "scan.overlap_line", exc, "overlap line unavailable for %s", ticker,
                  level=logging.DEBUG, exc_info=True)
        return None
```

`outlook_context.py`: the import block becomes:

```python
from __future__ import annotations

import logging

import pandas as pd

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.scanning.regime import get_market_regime

log = logging.getLogger(__name__)
```

and `regime_line`'s handler (`:55-56`) becomes:

```python
    except Exception as exc:
        swallowed(log, "scan.regime_line", exc, level=logging.DEBUG)
        return None                       # too little history for the 200EMA regime
```

`scan_replay.py`: add `import logging` directly after `import datetime as dt` (`:36`), add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.state import StateStore` (`:46`), and add `log = logging.getLogger(__name__)` after `from .short_reference import etf_for_sector` (`:53`), separated by one blank line, before `LANE_BASE = "base"`. Then `_regimes` (`:168-172`):

```python
def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception as exc:
        swallowed(log, "scan.scan_replay.regimes", exc, level=logging.DEBUG)
        return None
```

- [ ] **Step 5: Verify nothing is left untagged and the tags are unique**

```bash
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh9/untagged.py $S/scan_run.py $S/strategy_pass.py $S/plan_table.py $S/lane_overlap.py $S/outlook_context.py $S/scan_replay.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -ohE 'swallowed\(log, "[a-z_.]+"' -- swingbot | sort | uniq -d
```

Expected: `0 untagged []` for every file. The `uniq -d` line prints nothing, or only `swallowed(log, "scan.run_bounded"` if OH7 has landed. That tag is deliberately shared by `_run_bounded`'s handler and its timeout path (OH7).

Then prove a converted site still behaves and now counts. Two sites are checked: a DEBUG one that logged a message, and one that logged nothing:

```bash
cd /tmp && python - <<'PY'
import logging, sys
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import plan_table, scan_run

def boom(*a, **k):
    raise RuntimeError("yahoo")

scan_run.earnings_within_window = boom
assert scan_run._earnings_in_window("AAPL", 20) is None
plan_table.account.compute_position_size = boom
assert plan_table._sizing_snapshot(100.0, type("P", (), {"stop_loss": 95.0})()) is None
snap = sw.snapshot()
assert snap["scan.earnings_in_window"]["count"] == 1, snap
assert snap["scan.sizing_snapshot"]["last_error"] == "RuntimeError: yahoo", snap
print("OK", sorted(snap))
PY
```

Expected: `OK ['scan.earnings_in_window', 'scan.sizing_snapshot']`. The script runs from `/tmp` with only the worktree on `sys.path`, so it imports the worktree copy. It patches module attributes in a throwaway process.

- [ ] **Step 6: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_lane_overlap.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_outlook_embeds.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_strategy_pass_signals.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_strategy_pass_emit.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_measure_short_universe.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. `test_log_levels_v111.py::test_an_earnings_lookup_error_is_none_at_debug` pins `_earnings_in_window`'s single DEBUG record. It must still pass unchanged, and that proves the level was carried over. `changed` widens to every test reaching `scan_run.py`. If it escalates to the full suite, let it run: that is the selector's call, not a re-run.

- [ ] **Step 7: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/core/scanning/scan_run.py $WT/swingbot/core/scanning/strategy_pass.py $WT/swingbot/core/scanning/plan_table.py $WT/swingbot/core/scanning/lane_overlap.py $WT/swingbot/core/scanning/outlook_context.py $WT/swingbot/core/scanning/scan_replay.py > /tmp/claude-oh9/cc_after.txt
for f in scan_run strategy_pass plan_table lane_overlap outlook_context scan_replay; do git -C $WT show HEAD:swingbot/core/scanning/$f.py > /tmp/claude-oh9/$f.py; done
python -m radon cc -s -n C /tmp/claude-oh9/scan_run.py /tmp/claude-oh9/strategy_pass.py /tmp/claude-oh9/plan_table.py /tmp/claude-oh9/lane_overlap.py /tmp/claude-oh9/outlook_context.py /tmp/claude-oh9/scan_replay.py > /tmp/claude-oh9/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh9/cc_before.txt) <(norm /tmp/claude-oh9/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`. A conversion swaps one call for another and adds no branch, so every function's grade and score is identical. `_sync_run_scan` is a legacy function well above 15. It is listed in both files, with the same score.

- [ ] **Step 8: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/scanning/scan_run.py swingbot/core/scanning/strategy_pass.py swingbot/core/scanning/plan_table.py swingbot/core/scanning/lane_overlap.py swingbot/core/scanning/outlook_context.py swingbot/core/scanning/scan_replay.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH9: count swallowed errors in scan_run, strategy_pass and four small scan modules"
```

