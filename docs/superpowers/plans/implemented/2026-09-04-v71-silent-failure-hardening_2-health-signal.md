# v71 — Silent-failure hardening, part 2: an honest health signal

> **Part of a split plan.** The header block, Global Constraints and the
> cross-part map live in `2026-09-04-v71-silent-failure-hardening_0-index.md`.
> Read that first — this file carries only its phases.

# Phase C — An honest health signal

## Parallelisation

- **Sequential:** H5 (heartbeat state) before everything else in the phase —
  H6, H8, H9 and H11 all consume the fields it introduces. H7 (config) before
  H8 (escalation reads both new config fields).
- **Group 1 (parallel, after H5 and H7):** H8 (`loops.py` escalation) and H9
  (`admin/app.py` payload) — different files, no shared symbol.
- **Group 2 (parallel, after H9):** H10 (frontend store) then H11 (component) —
  **not** parallel with each other: H11 consumes the store field H10 adds.
- H12 (v67 update) is documentation-only and may run any time after H5.

### Task H5: Record tick outcome in the heartbeat

**Files:**
- Modify: `swingbot/commands/scanning/runstate.py:18-35`
- Test: `tests/scanning/test_heartbeat_outcome.py` (create)

**Interfaces:**
- Produces:
  - `runstate.record_tick_success() -> bool` — stamps `last_success`, zeroes
    `consecutive_failures`, clears `alert_active`; returns `True` **iff an
    alert was active**, i.e. this tick is a recovery.
  - `runstate.record_tick_failure() -> int` — increments and returns
    `consecutive_failures`.
  - `runstate.get_alert_active() -> bool`
  - `runstate.set_alert_active(active: bool) -> None`
  - `runstate.last_success_iso() -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_heartbeat_outcome.py`:

```python
import json

from swingbot.commands.scanning import runstate


def _use_tmp_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "bot_heartbeat.json"
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(path))
    monkeypatch.setattr(runstate.config, "DATA_DIR", str(tmp_path))
    return path


def test_failure_increments_and_success_resets(tmp_path, monkeypatch):
    path = _use_tmp_heartbeat(tmp_path, monkeypatch)

    assert runstate.record_tick_failure() == 1
    assert runstate.record_tick_failure() == 2
    assert runstate.last_success_iso() is None

    recovered = runstate.record_tick_success()

    state = json.loads(path.read_text())
    assert state["consecutive_failures"] == 0
    assert state["last_success"]
    assert recovered is False           # no alert was active, so not a recovery


def test_success_after_an_alert_reports_recovery(tmp_path, monkeypatch):
    _use_tmp_heartbeat(tmp_path, monkeypatch)

    runstate.record_tick_failure()
    runstate.set_alert_active(True)
    assert runstate.get_alert_active() is True

    assert runstate.record_tick_success() is True
    assert runstate.get_alert_active() is False


def test_liveness_write_preserves_outcome_fields(tmp_path, monkeypatch):
    """_write_heartbeat() runs at the top of every tick and must not wipe
    the outcome fields written at the end of the previous one."""
    path = _use_tmp_heartbeat(tmp_path, monkeypatch)

    runstate.record_tick_failure()
    runstate.record_tick_failure()
    runstate._write_heartbeat()

    state = json.loads(path.read_text())
    assert state["consecutive_failures"] == 2
    assert "timestamp" in state


def test_missing_file_reads_as_unknown(tmp_path, monkeypatch):
    _use_tmp_heartbeat(tmp_path, monkeypatch)
    assert runstate.last_success_iso() is None
    assert runstate.get_alert_active() is False
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/scanning/test_heartbeat_outcome.py -v`
Expected: **FAIL** — `AttributeError: module ... has no attribute
'record_tick_failure'`.

- [ ] **Step 3: Implement read-modify-write heartbeat state**

In `swingbot/commands/scanning/runstate.py`, replace `_write_heartbeat` (18-35)
with:

```python
def _read_heartbeat() -> dict:
    """Current heartbeat state, or {} when absent or unreadable.

    Absent is "unknown", never "failing" -- an upgraded admin container reads
    files written by a bot that has not restarted yet.
    """
    try:
        with open(_HEARTBEAT_FILE) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _update_heartbeat(fields: dict) -> None:
    """Merge `fields` into the heartbeat file, preserving everything else."""
    state = _read_heartbeat()
    state.update(fields)
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(_HEARTBEAT_FILE, "w") as fh:
            json.dump(state, fh)
    except Exception:
        pass


def _write_heartbeat() -> None:
    """
    Stamps a small JSON file that the admin UI reads to show a blinking
    bot-liveness dot on the Dashboard. Written on every session_scan tick
    (including off-hours / paused ticks) so the dot goes dark only when the
    bot process itself stops responding, not just because it's outside the
    trading session window.

    This is LIVENESS ONLY, and it is written before the tick does any work --
    so on its own it cannot distinguish "working" from "crashing every tick",
    which is exactly how a five-day alert blackout went unnoticed. Tick
    OUTCOME is record_tick_success() / record_tick_failure() below.
    """
    _update_heartbeat({
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_active": in_session(),
        "scan_paused": is_scan_paused(),
    })


def record_tick_success() -> bool:
    """Mark the tick as completed. Returns True iff this clears an active
    alert -- i.e. the caller should post a recovery notice."""
    was_alerting = bool(_read_heartbeat().get("alert_active"))
    _update_heartbeat({
        "last_success": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consecutive_failures": 0,
        "alert_active": False,
    })
    return was_alerting


def record_tick_failure() -> int:
    """Mark the tick as failed. Returns the new consecutive-failure count.

    Persisted rather than held in memory so a crash-looping container that
    restarts does not reset its own outage counter.
    """
    failures = int(_read_heartbeat().get("consecutive_failures") or 0) + 1
    _update_heartbeat({"consecutive_failures": failures})
    return failures


def get_alert_active() -> bool:
    return bool(_read_heartbeat().get("alert_active"))


def set_alert_active(active: bool) -> None:
    _update_heartbeat({"alert_active": bool(active)})


def last_success_iso() -> str | None:
    return _read_heartbeat().get("last_success")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_heartbeat_outcome.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning/runstate.py tests/scanning/test_heartbeat_outcome.py
git commit -m "feat(v71): record tick outcome in the heartbeat, not just liveness"
```

### Task H6: Wire tick outcome into the scan loop

**Files:**
- Modify: `swingbot/commands/scanning/loops.py:36-41`
- Test: `tests/scanning/test_heartbeat_outcome.py`

**Interfaces:**
- Consumes: `runstate.record_tick_success()`, `runstate.record_tick_failure()`
  from H5.
- Produces: nothing new yet — H8 adds the escalation calls into the same block.

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_heartbeat_outcome.py`:

`tasks.Loop.coro` is the undecorated coroutine function, so calling it runs one
tick's body without the scheduler — the same approach the existing tick
regression test in `tests/infra/test_silent_alerts_channel.py` uses.

```python
import asyncio


def test_tick_that_raises_is_recorded_as_failure(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert runstate.last_success_iso() is None
    assert runstate._read_heartbeat()["consecutive_failures"] == 1


def test_tick_that_returns_is_recorded_as_success(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)

    async def _ok():
        return None

    monkeypatch.setattr(loops, "_session_scan_tick", _ok)
    asyncio.run(loops.session_scan.coro())

    assert runstate.last_success_iso() is not None
    assert runstate._read_heartbeat()["consecutive_failures"] == 0
```

An early-returning tick (paused / off-session / no channel) exercises the same
`_ok` path: those are successful ticks — the tick did its job — which is why
success is recorded here, in the caller, rather than at the bottom of
`_session_scan_tick` where the early returns would skip it.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/scanning/test_heartbeat_outcome.py -k "recorded_as" -v`
Expected: **FAIL** — `KeyError: 'consecutive_failures'` / `last_success_iso()`
returning `None` on the success path, because nothing records outcome yet.

- [ ] **Step 3: Record outcome around the tick**

In `swingbot/commands/scanning/loops.py`, replace the body at 36-41:

```python
    try:
        await _session_scan_tick()
    except Exception:
        log.exception("session_scan tick failed -- will retry on the next scheduled tick "
                       "(every %d min) instead of stopping the loop entirely", config.SCAN_INTERVAL_MINUTES)
        runstate.record_tick_failure()
    else:
        runstate.record_tick_success()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_heartbeat_outcome.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/scanning/test_heartbeat_outcome.py
git commit -m "feat(v71): record scan-tick success and failure around the tick"
```

### Task H7: Add the two health config fields

**Files:**
- Modify: `swingbot/config.py` (after the `DISCORD_CHANNEL_FIREHOSE_ID` field, ~line 115)
- Test: `tests/test_config_flags.py` (exists — append, do not create a new file)

**Interfaces:**
- Produces: `config.DISCORD_CHANNEL_OPS_ID` (str, may be empty),
  `config.HEALTH_ALERT_AFTER_FAILURES` (int, default 3).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config_flags.py`:

```python
def test_health_config_fields_exist_with_documented_defaults():
    from swingbot import config

    assert config.HEALTH_ALERT_AFTER_FAILURES == 3
    assert hasattr(config, "DISCORD_CHANNEL_OPS_ID")

    # FIELDS (config.py:95) is the single source of truth for every
    # .env-driven setting; a field missing from it is invisible to the
    # admin UI and to SIGHUP hot-reload.
    keys = {f.key for f in config.FIELDS}
    assert "DISCORD_CHANNEL_OPS_ID" in keys
    assert "HEALTH_ALERT_AFTER_FAILURES" in keys
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/test_config_flags.py::test_health_config_fields_exist_with_documented_defaults -v`
Expected: **FAIL** — `AttributeError: module 'swingbot.config' has no attribute
'HEALTH_ALERT_AFTER_FAILURES'`.

- [ ] **Step 3: Add the fields**

After the `DISCORD_CHANNEL_FIREHOSE_ID` field in `swingbot/config.py`:

```python
    Field("DISCORD_CHANNEL_OPS_ID", "DISCORD_CHANNEL_OPS_ID", "Discord Connection", "Ops/health channel ID",
          help="Where bot-health alerts are posted when the scan tick keeps failing. "
               "Empty = falls back to the alerts channel, so the safety net is armed "
               "without any configuration. Set this to keep health notices out of the "
               "alert stream. Unlike the alerts channel, health notices are NOT silent."),
```

And beside the other `Scanning & Session` numeric fields:

```python
    Field("HEALTH_ALERT_AFTER_FAILURES", "HEALTH_ALERT_AFTER_FAILURES", "Scanning & Session",
          "Health alert after N failed ticks",
          type="number", default="3", min=1, max=100, step=1,
          help="Consecutive failed scan ticks before a health alert is posted to Discord. "
               "At the default 5-minute interval, 3 is about 15 minutes. One alert per "
               "outage, plus one when it recovers."),
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python scripts/dev/testrun.py file tests/test_config_flags.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py tests/test_config_flags.py
git commit -m "feat(v71): add ops channel and health-alert threshold config"
```

### Task H8: Escalate a sustained outage to Discord

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (the `session_scan` block from H6)
- Test: `tests/scanning/test_heartbeat_outcome.py`

**Interfaces:**
- Consumes: `runstate.record_tick_failure()`, `runstate.get_alert_active()`,
  `runstate.set_alert_active()`, `runstate.last_success_iso()` (H5);
  `config.HEALTH_ALERT_AFTER_FAILURES`, `config.DISCORD_CHANNEL_OPS_ID` (H7).
- Produces: `loops._ops_channel()`, `loops._maybe_escalate_health(failures, exc)`,
  `loops._post_health_recovered()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_heartbeat_outcome.py`:

```python
class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append(content)


def test_escalates_once_at_the_threshold_then_stays_quiet(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)

    for _ in range(5):
        asyncio.run(loops.session_scan.coro())

    assert len(channel.sent) == 1, "one alert per outage, not one per tick"
    assert "3" in channel.sent[0]
    assert "RuntimeError" in channel.sent[0]


def test_recovery_posts_exactly_one_notice(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 2)

    async def _boom():
        raise RuntimeError("tick exploded")

    async def _ok():
        return None

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())
    asyncio.run(loops.session_scan.coro())
    assert len(channel.sent) == 1

    monkeypatch.setattr(loops, "_session_scan_tick", _ok)
    asyncio.run(loops.session_scan.coro())
    asyncio.run(loops.session_scan.coro())

    assert len(channel.sent) == 2
    assert "recover" in channel.sent[1].lower()


def test_below_threshold_posts_nothing(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert channel.sent == []
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/scanning/test_heartbeat_outcome.py -k "escalat or recovery or threshold" -v`
Expected: **FAIL** — `AttributeError: module ... has no attribute '_ops_channel'`.

- [ ] **Step 3: Implement the escalation helpers**

In `swingbot/commands/scanning/loops.py`, add above `session_scan`:

```python
def _ops_channel():
    """Where health notices go. Falls back to the alerts channel when no
    dedicated ops channel is configured -- a safety net that needs
    configuring before it works is one that will not be armed when it
    matters. Deliberately NOT wrapped in silence(): this must notify."""
    chan_id = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID
    if not chan_id:
        return None
    return bot.get_channel(int(chan_id))


async def _maybe_escalate_health(failures: int, exc: Exception) -> None:
    """One alert per outage, once the failure streak crosses the threshold."""
    if failures < int(config.HEALTH_ALERT_AFTER_FAILURES):
        return
    if runstate.get_alert_active():
        return
    channel = _ops_channel()
    if channel is None:
        return
    last = runstate.last_success_iso() or "never"
    await channel.send(
        f"🚨 **Bot health alert** — the scan tick has failed {failures} time(s) in a row.\n"
        f"• Last successful tick: {last}\n"
        f"• Latest error: `{type(exc).__name__}: {exc}`\n"
        f"No alerts are being produced until this clears."
    )
    runstate.set_alert_active(True)


async def _post_health_recovered() -> None:
    channel = _ops_channel()
    if channel is None:
        return
    await channel.send("✅ **Bot health recovered** — the scan tick completed successfully again.")
```

- [ ] **Step 4: Call them from the tick block**

Replace the `session_scan` body from H6 with:

```python
    try:
        await _session_scan_tick()
    except Exception as exc:
        log.exception("session_scan tick failed -- will retry on the next scheduled tick "
                       "(every %d min) instead of stopping the loop entirely", config.SCAN_INTERVAL_MINUTES)
        failures = runstate.record_tick_failure()
        try:
            await _maybe_escalate_health(failures, exc)
        except Exception:
            log.exception("session_scan: health escalation itself failed")
    else:
        if runstate.record_tick_success():
            try:
                await _post_health_recovered()
            except Exception:
                log.exception("session_scan: health recovery notice failed")
```

The escalation is itself wrapped: a Discord outage must never turn a recorded
tick failure into an unrecorded one.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_heartbeat_outcome.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/scanning/test_heartbeat_outcome.py
git commit -m "feat(v71): escalate a sustained tick-failure streak to Discord"
```

### Task H9: Expose tick health on the admin API

**Files:**
- Modify: `swingbot/admin/app.py:312-370` (`scan_status_payload()`)
- Test: `tests/admin/test_api_v1_system_scan.py`

**Interfaces:**
- Produces three new keys on `scan_status_payload()`'s dict: `bot_healthy`
  (`bool | None`), `bot_last_success` (`str | None`),
  `bot_consecutive_failures` (`int`).

- [ ] **Step 1: Write the failing test**

Append to `tests/admin/test_api_v1_system_scan.py`, following that file's
existing fixture style for pointing `config.DATA_DIR` at `tmp_path`:

```python
import json
import os
from datetime import datetime, timedelta, timezone


def _write_heartbeat_file(tmp_path, **fields):
    path = os.path.join(str(tmp_path), "bot_heartbeat.json")
    with open(path, "w") as fh:
        json.dump(fields, fh)
    return path


def test_recent_success_is_healthy(tmp_path, monkeypatch):
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat(),
                          last_success=now.isoformat(), consecutive_failures=0)

    payload = admin_app.scan_status_payload()

    assert payload["bot_alive"] is True
    assert payload["bot_healthy"] is True
    assert payload["bot_consecutive_failures"] == 0


def test_fresh_heartbeat_with_stale_success_is_alive_but_unhealthy(tmp_path, monkeypatch):
    """The exact blackout shape: the process is looping and stamping
    liveness, but no tick has completed for hours."""
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat(),
                          last_success=(now - timedelta(hours=6)).isoformat(),
                          consecutive_failures=72)

    payload = admin_app.scan_status_payload()

    assert payload["bot_alive"] is True
    assert payload["bot_healthy"] is False
    assert payload["bot_consecutive_failures"] == 72


def test_never_reported_success_is_unknown_not_failing(tmp_path, monkeypatch):
    """A bot that has not restarted since the upgrade has no last_success.
    That is unknown, and must not render as failing."""
    from swingbot.admin import app as admin_app

    monkeypatch.setattr(admin_app.config, "DATA_DIR", str(tmp_path))
    now = datetime.now(timezone.utc)
    _write_heartbeat_file(tmp_path, timestamp=now.isoformat())

    payload = admin_app.scan_status_payload()

    assert payload["bot_healthy"] is None
    assert payload["bot_last_success"] is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest tests/admin/test_api_v1_system_scan.py -k "healthy or unknown" -v`
Expected: **FAIL** — `KeyError: 'bot_healthy'`.

- [ ] **Step 3: Derive health in the payload**

In `swingbot/admin/app.py`, inside the existing
`if os.path.exists(heartbeat_file):` block, after `bot_scan_paused` is read, add:

```python
                bot_last_success = hb.get("last_success")
                bot_consecutive_failures = int(hb.get("consecutive_failures") or 0)
                if bot_last_success:
                    try:
                        success_age = (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(bot_last_success)
                        ).total_seconds()
                        bot_healthy = success_age < threshold
                    except ValueError:
                        bot_healthy = None
```

Initialise the three alongside the existing defaults above the block:

```python
    bot_healthy = None
    bot_last_success = None
    bot_consecutive_failures = 0
```

`bot_healthy` stays `None` when no `last_success` has ever been written —
unknown, not failing. Reuse the existing `threshold`
(`SCAN_INTERVAL_MINUTES * 60 * 2`) so liveness and health share one definition
of "too long ago".

Add them to the returned dict:

```python
        "bot_healthy": bot_healthy,
        "bot_last_success": bot_last_success,
        "bot_consecutive_failures": bot_consecutive_failures,
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/app.py tests/admin/test_api_v1_system_scan.py
git commit -m "feat(v71): report tick health, not just liveness, from the admin API"
```

### Task H10: Carry bot health through the connection store

**Files:**
- Modify: `frontend/src/app/api/models.ts:707-712`,
  `frontend/src/app/stores/connection.store.ts`
- Test: `frontend/src/app/stores/connection.store.spec.ts`

**Interfaces:**
- Consumes: `ScanStatus.bot_healthy` from H9.
- Produces: `ConnectionStore.botHealthy` — `boolean | null`.

- [ ] **Step 1: Write the failing test**

Append inside the existing `describe('ConnectionStore', ...)` block in
`frontend/src/app/stores/connection.store.spec.ts`. The suite is **vitest**
with `HttpTestingController`; `tick()`, `HEALTH` and `SCAN` are already defined
in that file (`SCAN` at ~line 71, the `respond()` helper at ~line 105). These
tests flush their own scan payload rather than using `respond()`, because they
need a different `bot_healthy` per case:

```ts
it('carries bot_healthy through from scan status', () => {
  tick();
  backend.expectOne('/api/v1/health').flush(HEALTH);
  backend
    .expectOne('/api/v1/system/scan')
    .flush({ ...SCAN, bot_alive: true, bot_healthy: false });

  expect(store.botAlive()).toBe(true);
  expect(store.botHealthy()).toBe(false);
});

it('leaves bot health null when the bot has never completed a tick', () => {
  tick();
  backend.expectOne('/api/v1/health').flush(HEALTH);
  backend
    .expectOne('/api/v1/system/scan')
    .flush({ ...SCAN, bot_alive: true, bot_healthy: null });

  expect(store.botHealthy()).toBeNull();
});
```

Also add the three new keys to the shared `SCAN` const so it stays a faithful
sample of the real payload:

```ts
  bot_alive: true,
  bot_last_seen: '2026-08-14T09:00:00Z',
  bot_healthy: true,
  bot_last_success: '2026-08-14T09:00:00Z',
  bot_consecutive_failures: 0,
```

- [ ] **Step 2: Run the spec and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/stores/connection.store.spec.ts`
Expected: **FAIL** — `store.botHealthy is not a function`.

- [ ] **Step 3: Add the field to the model**

In `frontend/src/app/api/models.ts`, extend the `ScanStatus` interface:

```ts
  bot_alive: boolean;
  bot_last_seen: string | null;
  /** Null when the bot has never completed a tick -- unknown, not failing. */
  bot_healthy: boolean | null;
  bot_last_success: string | null;
  bot_consecutive_failures: number;
```

- [ ] **Step 4: Carry it through the store**

In `frontend/src/app/stores/connection.store.ts`, add to
`ConnectionStateSlice`:

```ts
  /** Null when the bot has never completed a tick -- distinct from false. */
  botHealthy: boolean | null;
```

Add `botHealthy: null` to the `withState` initial value, and to the
`api.scanStatus()` subscription's `patchState`:

```ts
          patchState(store, {
            botAlive: scan.bot_alive,
            botHealthy: scan.bot_healthy,
            botLastSeen: scan.bot_last_seen,
            unreachable: false,
          }),
```

- [ ] **Step 5: Run the spec and confirm it passes**

Run: `cd frontend && npm test -- --include src/app/stores/connection.store.spec.ts`
Expected: **PASS**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/connection.store.ts frontend/src/app/stores/connection.store.spec.ts
git commit -m "feat(v71): carry bot tick health through the connection store"
```

### Task H11: Show "bot failing" in the shell indicator

**Files:**
- Modify: `frontend/src/app/shell/connection-status.ts`,
  `frontend/src/app/shell/shell.html:141-145`
- Test: `frontend/src/app/shell/connection-status.spec.ts` (create — the
  component has no spec today; follow `profile-menu.spec.ts` for the pattern)

**Interfaces:**
- Consumes: `ConnectionStore.botHealthy` from H10.
- Produces: `ConnectionStatus.botHealthy` input.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/shell/connection-status.spec.ts`:

The app is zoneless, and the suite runner is vitest — match
`connection.store.spec.ts`'s imports rather than the Angular defaults:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConnectionStatus } from './connection-status';

describe('ConnectionStatus', () => {
  let fixture: ComponentFixture<ConnectionStatus>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ConnectionStatus],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(ConnectionStatus);
    fixture.componentRef.setInput('state', 'live');
  });

  const render = (botAlive: boolean | null, botHealthy: boolean | null) => {
    fixture.componentRef.setInput('botAlive', botAlive);
    fixture.componentRef.setInput('botHealthy', botHealthy);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  };

  it('says the bot is failing when it is alive but not healthy', () => {
    const el = render(true, false);
    expect(el.textContent).toContain('bot failing');
    expect(el.textContent).not.toContain('bot offline');
  });

  it('still says offline when the bot is not alive, and not both', () => {
    const el = render(false, false);
    expect(el.textContent).toContain('bot offline');
    expect(el.textContent).not.toContain('bot failing');
  });

  it('says nothing about the bot while health is unknown', () => {
    const el = render(true, null);
    expect(el.textContent).not.toContain('bot failing');
    expect(el.textContent).not.toContain('bot offline');
  });

  it('styles a failing bot with the same amber class as an offline one', () => {
    // NG52 colour review: health chrome is greyscale and amber only, and two
    // severities of one caution are told apart by their label, not a new
    // colour. Asserting the shared `.bot` class is what pins that down -- a
    // future green/red variant would have to drop it and fail here.
    const failing = render(true, false).querySelector('.bot-failing');
    expect(failing).toBeTruthy();
    expect(failing!.classList.contains('bot')).toBe(true);
  });
});
```

- [ ] **Step 2: Run the spec and confirm it fails**

Run: `cd frontend && npm test -- --include src/app/shell/connection-status.spec.ts`
Expected: **FAIL** — no `botHealthy` input exists, so `setInput` throws.

- [ ] **Step 3: Add the input and the label**

In `frontend/src/app/shell/connection-status.ts`, add beside `botAlive`:

```ts
  /** Null until the bot has ever completed a tick -- distinct from "failing".
   *  True/false only once the admin has a last_success to compare against. */
  readonly botHealthy = input<boolean | null>(null);
```

Extend the template's bot block. `bot offline` wins when both apply — a bot
that is gone is not merely failing:

```html
      @if (botAlive() === false) {
        <span class="bot">bot offline</span>
      } @else if (botHealthy() === false) {
        <span class="bot bot-failing">bot failing</span>
      }
```

No new style rule is needed: `.bot { color: var(--warn); }` already applies, and
that is deliberate. Both states are the same amber caution, told apart by the
label — the rule this component already documents for `.dot.degraded` versus
`.dot.dead`. Do **not** add a green or red variant.

- [ ] **Step 4: Wire it in the shell**

In `frontend/src/app/shell/shell.html`:

```html
      <sb-connection-status
        [state]="connection.state()"
        [botAlive]="connection.botAlive()"
        [botHealthy]="connection.botHealthy()"
        [marketActive]="connection.marketActive()"
      />
```

- [ ] **Step 5: Run the specs and confirm they pass**

Run: `cd frontend && npm test -- --include src/app/shell/connection-status.spec.ts`
Then: `cd frontend && npm test -- --include src/app/shell/shell.spec.ts`
Expected: **PASS** for both.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/shell/connection-status.ts frontend/src/app/shell/connection-status.spec.ts frontend/src/app/shell/shell.html
git commit -m "feat(v71): distinguish a failing bot from an offline one in the shell"
```

### Task H12: Route the new heartbeat fields into v67

Documentation only — no runtime code. Required by the standing rule that a
parallel plan changing `data/` JSON updates v67 before it closes.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_3a-operational-flags.md`

- [ ] **Step 1: Read the two table definitions**

Run: `grep -n "bot_heartbeat\|runtime_flags" docs/superpowers/plans/2026-08-29-v67-json-to-postgres_3a-operational-flags.md`

Confirm `bot_heartbeat` is the `(key, ts)` table at ~line 176 and that
`runtime_flags` shares revision `p3_001`.

- [ ] **Step 2: Add the migration note**

Add to that part's migration task for `bot_heartbeat`, verbatim:

```markdown
**v71 addition.** `data/bot_heartbeat.json` gained three fields recording tick
*outcome* (see `docs/superpowers/specs/2026-09-04-v71-silent-failure-hardening-design.md`).
They do not all belong in `bot_heartbeat`, whose shape is `(key, ts)`:

| JSON field | Destination | Why |
|---|---|---|
| `last_success` | `bot_heartbeat` row, `key='last_success'` | It is a timestamp; the table is already keyed for exactly this |
| `consecutive_failures` | `runtime_flags` | An integer, not a timestamp |
| `alert_active` | `runtime_flags` | A boolean, not a timestamp |

Both tables are in this part under revision `p3_001`, so this needs **no new
Alembic revision and no schema widening**.

Pre-existing gap, not introduced by v71: this table also does not carry the
`session_active` / `scan_paused` booleans today's JSON has. Decide where those
land while doing this migration.
```

- [ ] **Step 3: Verify the part still fits its budget**

Run: `wc -l docs/superpowers/plans/2026-08-29-v67-json-to-postgres_3a-operational-flags.md`
Expected: under 1500. If it now exceeds, split per `document-conventions.md`
(letter suffix, never compress) — do not shorten the note.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-08-29-v67-json-to-postgres_3a-operational-flags.md
git commit -m "docs(v67): route v71's heartbeat outcome fields into part 3a"
```
