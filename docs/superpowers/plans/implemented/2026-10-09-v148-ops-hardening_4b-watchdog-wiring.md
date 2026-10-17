# v148 Ops hardening, part 4b: watchdog loop, provider check and loop wiring (OH18)

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH18:" -A 380 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O3 "In-bot watchdog", § O4)
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md`. Its Global Constraints, Parallelisation and task ledger are binding here and are not repeated. Part 4 (`_4-ratchet-metrics-watch.md`, OH15–OH17) was split here only to keep each file under 1500 lines.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`.

OH18 needs OH16 and OH17 (part 4). Its handlers call `swallowed()` with new unique tags (`ops.scan_watchdog`, `ops.provider_health`), so it does not move OH15's `BASELINE`.

# Phase D (continued) — watchdog and wiring

### Task OH18: Watchdog loop, provider check and loop wiring

**Model:** sonnet — the async glue around OH17's pure verdicts, following `pitr_watch_loop` and `_maybe_escalate_health`; the import-cycle rule is fixed by the index.

**Files:**
- Modify: `swingbot/commands/scanning/ops_watch.py` (imports; append a section)
- Modify: `swingbot/commands/scanning/loops.py` (`:22` import; `_session_scan_tick` after `_refresh_snapshot_safely()`; `_always_on_loops` `:966`)
- Modify: `tests/scanning/test_ops_watch.py` (append)
- Modify: `tests/infra/test_silent_alerts_channel.py` (one stub in `test_the_scan_tick_actually_delivers_a_built_alert`)

**Contract (ledger, final):** `ops_watch.scan_watchdog` (`tasks.loop(minutes=1)`), `async ops_watch.watchdog_tick(now: dt.datetime | None = None) -> str | None`, `async ops_watch.check_provider_health(row: dict | None = None) -> str | None`, `ops_watch._channel()`; `scan_watchdog` in `loops._always_on_loops()`. Tags `ops.scan_watchdog` and `ops.provider_health` (ERROR, `exc_info=True`). Both are new, and each sits in one handler.

Design points (spec § O3, § O4; index Global Constraints 7 and "`tasks.loop` bodies never raise"):
- `_channel()` does `from . import loops` **inside the function**. `loops` imports `ops_watch` at its top, and tests patch `loops._ops_channel`.
- `_post` mirrors `_maybe_escalate_health`. With no channel, nothing is posted. A failed send raises. In both cases the flag stays unset and the next tick retries. The flag is persisted only after a successful send, so a restart neither re-posts nor forgets.
- Each loop body is one `try`/`swallowed`. `_session_scan_tick` (complexity 15, legacy) gains one `await` and no branch. The jsonl is read whole, so the read goes through `asyncio.to_thread`.
- **`test_silent_alerts_channel.py`:** `test_the_scan_tick_actually_delivers_a_built_alert` drives the whole tick and asserts exactly one send to a fake that answers every channel id. Left unstubbed, the provider check would read the worktree's real `data/scan_telemetry.jsonl` and the heartbeat DB, and a breaching row there would add a send. So that test stubs the check.

- [ ] **Step 1: Write the failing tests**

Append to `$WT/tests/scanning/test_ops_watch.py` after two blank lines (the mid-file imports are deliberate, so OH17's block stays untouched):

```python
# --- OH18: the watchdog loop, the provider check and the wiring --------------------

import ast
import asyncio
import inspect
import json
import logging
from pathlib import Path

from swingbot import config
from swingbot.commands.scanning import loops, runstate
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.scanning import telemetry


class _FakeChannel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, content=None, **kw):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append({"content": content, **kw})


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


@pytest.fixture
def heartbeat(monkeypatch):
    """An in-memory heartbeat doc behind every runstate getter and setter."""
    doc = {}
    monkeypatch.setattr(runstate, "_read_heartbeat", lambda: dict(doc))
    monkeypatch.setattr(runstate, "_update_heartbeat", doc.update)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: False)
    monkeypatch.setattr(ops_watch, "in_session", lambda: True)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", NOW - dt.timedelta(hours=2))
    monkeypatch.setattr(config, "SCAN_INTERVAL_MINUTES", INTERVAL)
    monkeypatch.setattr(config, "PROVIDER_FALLBACK_ALERT_PCT", 20)
    monkeypatch.setattr(config, "EMPTY_SYMBOLS_ALERT_PCT", 5)
    return doc


@pytest.fixture
def channel(monkeypatch):
    chan = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: chan)
    return chan


def _tick(now=NOW):
    return asyncio.run(ops_watch.watchdog_tick(now))


def test_a_wedged_tick_alerts_once_then_recovers_once(heartbeat, channel):
    heartbeat["last_success"] = _ago(14)
    assert _tick() == "alert"
    assert _tick() is None
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "no completed scan tick for 14 min" in channel.sent[0]["embed"].title
    assert heartbeat["stale_alert_active"] is True

    heartbeat["last_success"] = _ago(1)
    assert _tick() == "recover"
    assert _tick() is None
    assert len(channel.sent) == 2
    assert "scan ticks completing again" in channel.sent[1]["embed"].title
    assert heartbeat["stale_alert_active"] is False


@pytest.mark.parametrize("open_flag", ["stale_alert_active", "alert_active"])
def test_an_open_alert_suppresses_a_new_stale_post(heartbeat, channel, open_flag):
    """A restart with its stale alert still open; a failure-streak alert open."""
    heartbeat.update({"last_success": _ago(30), open_flag: True})
    assert _tick() is None and channel.sent == []


def test_no_ops_channel_posts_nothing_and_leaves_the_flag_unset(heartbeat, monkeypatch):
    monkeypatch.setattr(loops, "_ops_channel", lambda: None)
    heartbeat["last_success"] = _ago(30)
    assert _tick() is None
    assert "stale_alert_active" not in heartbeat


def test_a_raising_heartbeat_read_leaves_the_loop_running(heartbeat, monkeypatch, caplog):
    def down():
        raise RuntimeError("db down")

    monkeypatch.setattr(runstate, "last_success_iso", down)
    with caplog.at_level(logging.ERROR, logger=ops_watch.log.name):
        assert asyncio.run(ops_watch.scan_watchdog.coro()) is None
    entry = swallowed_mod.snapshot()["ops.scan_watchdog"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: db down"
    assert "scan watchdog tick failed" in caplog.text


def test_a_failed_send_is_retried_on_the_next_tick(heartbeat, monkeypatch):
    real_now = dt.datetime.now(dt.timezone.utc)
    monkeypatch.setattr(ops_watch, "BOOTED_AT", real_now - dt.timedelta(hours=2))
    heartbeat["last_success"] = (real_now - dt.timedelta(minutes=30)).isoformat()
    monkeypatch.setattr(loops, "_ops_channel", lambda: _FakeChannel(fail=True))
    asyncio.run(ops_watch.scan_watchdog.coro())
    assert "stale_alert_active" not in heartbeat
    assert swallowed_mod.snapshot()["ops.scan_watchdog"]["count"] == 1

    good = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: good)
    asyncio.run(ops_watch.scan_watchdog.coro())
    assert len(good.sent) == 1 and heartbeat["stale_alert_active"] is True


def test_the_watchdog_runs_every_minute_with_the_other_loops():
    assert ops_watch.scan_watchdog in loops._always_on_loops()
    assert ops_watch.scan_watchdog.minutes == 1


def test_ops_watch_never_imports_loops_at_module_level():
    tree = ast.parse(Path(ops_watch.__file__).read_text(encoding="utf-8"))
    top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    names = [alias.name for node in top for alias in node.names]
    names += [node.module or "" for node in top if isinstance(node, ast.ImportFrom)]
    assert not [name for name in names if name.endswith("loops")]


def test_a_breaching_scan_alerts_once_then_recovers_once(heartbeat, channel):
    assert asyncio.run(ops_watch.check_provider_health(ROW_BAD)) == "alert"
    assert asyncio.run(ops_watch.check_provider_health(ROW_BAD)) is None
    assert "market-data provider degraded" in channel.sent[0]["embed"].title
    assert heartbeat["provider_alert_active"] is True

    assert asyncio.run(ops_watch.check_provider_health(ROW_OK)) == "recover"
    assert asyncio.run(ops_watch.check_provider_health(ROW_OK)) is None
    assert len(channel.sent) == 2
    assert heartbeat["provider_alert_active"] is False


def test_the_newest_scan_row_is_read_when_none_is_given(heartbeat, channel, tmp_path,
                                                        monkeypatch):
    path = tmp_path / "scan_telemetry.jsonl"
    rows = [ROW_OK, {"type": "deploy", "at": "2026-10-12T14:58:00+00:00"}, ROW_BAD]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(path))
    assert asyncio.run(ops_watch.check_provider_health()) == "alert"


def test_a_pre_v148_row_posts_nothing(heartbeat, channel):
    assert asyncio.run(ops_watch.check_provider_health(ROW_PRE_V148)) is None
    assert channel.sent == []


def test_a_failing_provider_check_never_raises(heartbeat, channel, monkeypatch):
    def broken(n=50, path=None):
        raise OSError("disk gone")

    monkeypatch.setattr(telemetry, "recent_scan_telemetry", broken)
    assert asyncio.run(ops_watch.check_provider_health()) is None
    assert swallowed_mod.snapshot()["ops.provider_health"]["count"] == 1


def test_the_scan_tick_checks_providers_after_the_scan():
    source = inspect.getsource(loops._session_scan_tick)
    check = source.index("await ops_watch.check_provider_health()")
    assert source.index("_refresh_snapshot_safely()") < check < source.index("f = progress.funnel")
```

Run `python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`. Expected: OH17's 38 pass, and the 13 new tests fail or error with `AttributeError: module 'swingbot.commands.scanning.ops_watch' has no attribute 'watchdog_tick'` (or `scan_watchdog`, `check_provider_health`).

- [ ] **Step 2: Extend `ops_watch.py`**

In `$WT/swingbot/commands/scanning/ops_watch.py`, replace the import block (`from __future__ import annotations` + `import datetime as dt`) with:

```python
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from discord.ext import tasks

from swingbot import config
from swingbot.bot_core import in_session
from swingbot.core import presentation as ui
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.scanning import telemetry

from . import notices, runstate

log = logging.getLogger(__name__)
```

Append at the end of the file:

```python
# --- v148 OH18: the sends, the watchdog loop and the provider check -----------

def _channel():
    """``loops._ops_channel()``, looked up at call time (``loops`` imports us)."""
    from . import loops
    return loops._ops_channel()


async def _post(embed) -> bool:
    """False when no ops channel is configured. A failed send raises, so the
    caller's flag stays unset and the next tick retries (as escalation does)."""
    channel = _channel()
    if channel is None:
        return False
    await channel.send(**ui.push_kwargs(embed))
    return True


def _stale_embed(verdict: str, now: dt.datetime, last_success: str):
    if verdict == "recover":
        return notices.stale_scan_recovered_embed(last_success)
    age_min = int((now - parse_moment(last_success)).total_seconds() // 60)
    return notices.stale_scan_embed(age_min, last_success)


async def watchdog_tick(now: dt.datetime | None = None) -> str | None:
    """One stale-scan decision; returns the verdict it posted, or None."""
    now = now or dt.datetime.now(dt.timezone.utc)
    last = runstate.last_success_iso()
    verdict = stale_scan_verdict(
        now, last, int(config.SCAN_INTERVAL_MINUTES), BOOTED_AT,
        in_session=in_session(), paused=runstate.is_scan_paused(),
        failure_alert_active=runstate.get_alert_active(),
        stale_alert_active=runstate.get_stale_alert_active())
    if verdict is None or not await _post(_stale_embed(verdict, now, last)):
        return None
    runstate.set_stale_alert_active(verdict == "alert")
    return verdict


@tasks.loop(minutes=1)
async def scan_watchdog():
    """v148 O3: the wedged tick the failure streak cannot see (a dead process
    is the VM cron's). Never raises: that would stop the loop for good."""
    try:
        await watchdog_tick()
    except Exception as exc:
        swallowed(log, "ops.scan_watchdog", exc, "scan watchdog tick failed",
                  level=logging.ERROR, exc_info=True)


async def _latest_scan_row() -> dict | None:
    rows = await asyncio.to_thread(telemetry.recent_scan_telemetry, 1)
    return rows[-1] if rows else None


async def _provider_check(row: dict | None) -> str | None:
    row = row if row is not None else await _latest_scan_row()
    fallback_pct = float(config.PROVIDER_FALLBACK_ALERT_PCT)
    empty_pct = float(config.EMPTY_SYMBOLS_ALERT_PCT)
    verdict = provider_verdict(row, fallback_pct=fallback_pct, empty_pct=empty_pct,
                               alert_active=runstate.get_provider_alert_active())
    if verdict is None:
        return None
    embed = (notices.provider_degraded_embed(row, fallback_pct, empty_pct)
             if verdict == "alert" else notices.provider_recovered_embed(row))
    if not await _post(embed):
        return None
    runstate.set_provider_alert_active(verdict == "alert")
    return verdict


async def check_provider_health(row: dict | None = None) -> str | None:
    """v148 O4: one notice per provider incident, one on recovery, from the
    newest scan row (or `row`). Never raises into the scan tick."""
    try:
        return await _provider_check(row)
    except Exception as exc:
        swallowed(log, "ops.provider_health", exc, "provider health check failed",
                  level=logging.ERROR, exc_info=True)
        return None
```

- [ ] **Step 3: Wire `loops.py`**

In `$WT/swingbot/commands/scanning/loops.py`:

1. `:22` (today `from . import notices, outlook, presence, recap, runstate`): add `ops_watch` to that alphabetical `from . import …` line, keeping every name other plans added (v152 adds `cooldown`). Today's line would become `from . import notices, ops_watch, outlook, presence, recap, runstate`.
2. In `_session_scan_tick`, directly after `_refresh_snapshot_safely()` and before `f = progress.funnel`, add at the same indent:

```python
    await ops_watch.check_provider_health()
```

3. In `_always_on_loops`, insert `ops_watch.scan_watchdog` directly after `pitr_watch_loop` in the returned tuple, keeping every entry already there (v147 adds its resolver loop before `pitr_watch_loop`; keep it). Do not rewrite the tuple from a literal. On today's tuple the result is:

```python
    return (session_scan, heartbeat, config_watcher, trade_monitor, daily_recap,
            weekend_deep_scan_task, weekly_earnings_refresh, pitr_watch_loop,
            ops_watch.scan_watchdog, next_session_scan, next_session_wrapup)
```

- [ ] **Step 4: Stub the check in the end-to-end tick test**

In `$WT/tests/infra/test_silent_alerts_channel.py`, add `from swingbot.commands.scanning import ops_watch` after `from swingbot.commands.scanning import presence` (`:28`). In `test_the_scan_tick_actually_delivers_a_built_alert`, directly after `monkeypatch.setattr(loops_mod, "_refresh_snapshot_safely", lambda: None, raising=False)`, add the line below. `_noop` is that test's existing `async def _noop(*args, **kwargs)`.

```python
    monkeypatch.setattr(ops_watch, "check_provider_health", _noop)   # v148: tested in test_ops_watch.py
```

- [ ] **Step 5: Run the tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_ops_watch.py
python $WT/scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py
python $WT/scripts/dev/testrun.py file tests/commands/test_pitr_watch_loop.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
python $WT/scripts/dev/testrun.py changed
```

Expected: `test_ops_watch.py` `51 passed`. Every run shows `0 failed`, `0 xfailed`. The ratchet passes with `BASELINE` unchanged (both new handlers are tagged, with new unique tags), and an import of `swingbot.commands.scanning` raises no circular-import error.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/commands/scanning/ops_watch.py
python -m radon cc -s $WT/swingbot/commands/scanning/loops.py | grep -E "_session_scan_tick|_always_on_loops"
```

Expected: no output from the first command, then `_session_scan_tick - C (15)` (unchanged: an `await` adds no branch) and `_always_on_loops - A (1)`.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/commands/scanning/ops_watch.py swingbot/commands/scanning/loops.py tests/scanning/test_ops_watch.py tests/infra/test_silent_alerts_channel.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH18: scan_watchdog loop and post-scan provider check, once per incident, wired into loops"
```
