# v116 — Part 4b: Phase 3 readiness, continued (V116-23 … V116-26)

Continues `_4a-readiness.md`, which carries this group's parallelisation. Header, global constraints and revision ids: `_0-index.md`. The flips are `_4c-flips.md`.

---

# Phase 3 — Staged production flip (readiness, continued)

### Task V116-23: A store write failure at `db` halts issuance

**Files:**
- Create: `swingbot/core/db/write_failure.py`
- Modify: `swingbot/core/scanning/scan_run.py:215` (`_persist_plan_v2`)
- Modify: `swingbot/commands/scanning/loops.py` (`session_scan`'s except branch; new `_halt_on_store_failure`)
- Modify: `swingbot/commands/scanning/notices.py` (new `store_write_halt_embed`)
- Modify: `swingbot/commands/scanning/runstate.py` (new `record_store_write_failure`; `set_scan_paused(False)` clears it)
- Modify: `swingbot/admin/app.py` (`_heartbeat_status`: `bot_store_write_failure`, unhealthy while set)
- Create: `tests/commands/test_store_write_halt.py`

**Interfaces:**
- Consumes: `_heartbeat_status` (V116-22), `loops._ops_channel`, `notices.system_embed`, `runstate.set_scan_paused`, `engine.DatabaseUnavailable`.
- Produces: `write_failure.TRADING_STORES = ("plans", "trades", "account", "journal")`, `StoreWriteHalt(RuntimeError)`, `is_store_write_failure(exc) -> bool` (walks `__cause__`/`__context__`), `trading_store_at_db() -> bool`, `halts_issuance(exc) -> bool`. The v116 soak check (V116-24) greps for `StoreWriteHalt`. Phase 4 (V116-39) drops `trading_store_at_db` when stages go.

Spec § Phase 3: writes already raise; this makes the raise stop issuance rather than skip one record. The one place a store write is swallowed during issuance is `_persist_plan_v2` (it logs and continues, so the alert posts for a plan the book never stored). At a trading store's `db` stage it now raises `StoreWriteHalt`; `_sync_run_scan` propagates it, so `run_scan` never returns alerts and `_send_alerts` never runs for that scan. `session_scan` then pauses scheduled scanning, posts to ops immediately and marks the heartbeat. At `json`/`dual` nothing changes: a DB hiccup during a soak must not pause alerts while JSON is still the truth.

- [ ] **Step 1: Write the failing tests** — `tests/commands/test_store_write_halt.py`:

```python
"""A DB write failure at a trading store's db stage pauses alerting instead
of issuing a trade the book cannot record (v116 Phase 3)."""
import asyncio
import datetime as dt

import pytest
import sqlalchemy.exc as sa_exc

from swingbot import config
from swingbot.commands.scanning import loops, runstate
from swingbot.core.db import write_failure
from swingbot.core.scanning import scan_run


def _db_error():
    return sa_exc.OperationalError("INSERT INTO plans", {}, Exception("server closed"))


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append({"content": content, **kw})


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(runstate, "_PAUSE_FILE", str(tmp_path / "scan_paused.flag"))
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)
    return tmp_path


def test_a_wrapped_database_error_is_a_store_write_failure():
    try:
        try:
            raise _db_error()
        except sa_exc.OperationalError as inner:
            raise RuntimeError("persist failed") from inner
    except RuntimeError as outer:
        assert write_failure.is_store_write_failure(outer) is True
    assert write_failure.is_store_write_failure(ValueError("bad price")) is False


def test_only_a_trading_store_at_db_halts(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual,flags:db")
    assert write_failure.halts_issuance(_db_error()) is False
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    assert write_failure.halts_issuance(_db_error()) is True


def test_persist_plan_raises_at_db_and_still_swallows_at_json(monkeypatch):
    class Boom:
        def add(self, _plan):
            raise _db_error()

    class Plan:
        plan_id = "P1"

    monkeypatch.setattr(scan_run, "PlanStore", Boom)
    monkeypatch.setattr(config, "DB_STORES", "")
    scan_run._persist_plan_v2(Plan())                       # logged, swallowed
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    with pytest.raises(write_failure.StoreWriteHalt):
        scan_run._persist_plan_v2(Plan())


def test_the_scan_loop_pauses_posts_to_ops_and_marks_health(files, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)

    async def _halted():
        raise write_failure.StoreWriteHalt("plan P1 could not be stored") from _db_error()

    monkeypatch.setattr(loops, "_session_scan_tick", _halted)
    asyncio.run(loops.session_scan.coro())

    assert runstate.is_scan_paused() is True
    assert len(channel.sent) == 1                     # immediately, not after 3 ticks
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "alerting paused" in channel.sent[0]["embed"].title
    assert runstate._read_heartbeat()["store_write_failure"]["error"].startswith("StoreWriteHalt")


def test_unpausing_clears_the_health_mark(files, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("x"))
    runstate.set_scan_paused(False)
    assert runstate._read_heartbeat().get("store_write_failure") is None


def test_the_admin_reports_unhealthy_while_marked(files, monkeypatch):
    from swingbot.admin import app as admin_app
    monkeypatch.setattr(config, "DB_STORES", "")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    runstate._update_heartbeat({"timestamp": now, "last_success": now})
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("plan P1"))
    payload = admin_app.scan_status_payload()
    assert payload["bot_healthy"] is False
    assert payload["bot_store_write_failure"]["error"].startswith("StoreWriteHalt")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_store_write_halt.py`
Expected: FAIL — `ImportError: cannot import name 'write_failure'`.

- [ ] **Step 3: `swingbot/core/db/write_failure.py`**

```python
"""A database write failure at the db stage stops issuance (v116 Phase 3).

Writes already raise (the fail-fast rule). This decides which raises mean
"the book can no longer record what the scan is issuing", so the scan loop
pauses alerting instead of posting an alert whose trade or plan was never
stored. Only once a trading store is at `db`: before that the JSON file is
still the truth, and a database hiccup during a soak must not pause alerts.
"""
from __future__ import annotations

#: The stores an issued alert writes to.
TRADING_STORES = ("plans", "trades", "account", "journal")


class StoreWriteHalt(RuntimeError):
    """Raised in place of a swallowed store write during issuance."""


def is_store_write_failure(exc: BaseException | None) -> bool:
    import sqlalchemy.exc as sa_exc

    from swingbot.core.db.engine import DatabaseUnavailable
    kinds = (sa_exc.SQLAlchemyError, DatabaseUnavailable, StoreWriteHalt)
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, kinds):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def trading_store_at_db() -> bool:
    from swingbot.core.db import stages
    return any(stages.reads_db(store) for store in TRADING_STORES)


def halts_issuance(exc: BaseException) -> bool:
    return trading_store_at_db() and is_store_write_failure(exc)
```

- [ ] **Step 4: `_persist_plan_v2` raises at `db`** — in `swingbot/core/scanning/scan_run.py`, add `from swingbot.core.db import write_failure` beside the other imports and replace the function:

```python
def _persist_plan_v2(plan_v2) -> None:
    """Add the plan to PlanStore; log it as armed only once that succeeded.

    v116: at a trading store's db stage a failed write is not swallowed. The
    alert for this plan would otherwise post with no plan behind it, so the
    whole scan stops before anything is sent (session_scan then pauses).
    """
    try:
        PlanStore().add(plan_v2)
    except Exception as exc:
        if write_failure.halts_issuance(exc):
            raise write_failure.StoreWriteHalt(
                f"plan {plan_v2.plan_id} could not be stored") from exc
        log.warning("Failed to persist plan_v2 %s to PlanStore",
                    plan_v2.plan_id, exc_info=True)
        return
    log_plan_armed(plan_v2)
```

- [ ] **Step 5: The loop halts** — in `swingbot/commands/scanning/loops.py`, import `from swingbot.core.db import write_failure`; in `session_scan`'s `except Exception as exc:` branch, directly after `failures = runstate.record_tick_failure()`:

```python
        if write_failure.halts_issuance(exc):
            await _halt_on_store_failure(exc)
```

and add after `_post_health_recovered`:

```python
async def _halt_on_store_failure(exc: Exception) -> None:
    """v116: the book could not record what the scan was issuing. Pause the
    scheduled scan (the partner unpauses from the admin UI), tell ops now --
    not after HEALTH_ALERT_AFTER_FAILURES ticks -- and mark the heartbeat so
    the admin's health signal shows it."""
    try:
        runstate.set_scan_paused(True)
    except Exception:
        log.exception("store-write halt: could not set the pause flag; the database is "
                      "likely down, and every tick fails until it is back")
    runstate.record_store_write_failure(exc)
    channel = _ops_channel()
    if channel is not None:
        await notices.send_guarded(channel, notices.store_write_halt_embed(exc),
                                   what="store-write halt notice")
```

- [ ] **Step 6: The notice** — `swingbot/commands/scanning/notices.py`, after `pitr_notice_embed`:

```python
def store_write_halt_embed(exc: Exception):
    """v116: issuance stopped because the book could not store a record."""
    return system_embed(Kind.HEALTH_ALERT, "alerting paused: a record could not be stored", (
        f"• Error: `{type(exc).__name__}: {str(exc)[:400]}`\n"
        "• The scan stopped before posting, so no alert went out for a trade or plan "
        "the book did not record.\n"
        "Scheduled scanning is paused. Fix the database, then unpause from the admin UI."))
```

- [ ] **Step 7: The health mark** — `swingbot/commands/scanning/runstate.py`, after `last_success_iso`:

```python
def record_store_write_failure(exc: Exception) -> None:
    """v116: mark the heartbeat so the admin shows the halt until unpaused."""
    _update_heartbeat({"store_write_failure": {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
    }})
```

and at the end of `set_scan_paused`:

```python
    if not paused:
        # Unpausing is the partner's acknowledgement of a store-write halt.
        _update_heartbeat({"store_write_failure": None})
```

In `swingbot/admin/app.py`, `_heartbeat_status` becomes:

```python
def _heartbeat_status(hb: dict, seen: datetime | None, threshold: float) -> dict:
    now = datetime.now(timezone.utc)
    last_success = hb.get("last_success")
    success_at = _parse_iso(last_success)
    healthy = None if success_at is None else (now - success_at).total_seconds() < threshold
    halted = hb.get("store_write_failure")
    return {
        "bot_alive": seen is not None and (now - seen).total_seconds() < threshold,
        "bot_last_seen": seen.isoformat() if seen else None,
        "bot_session_active": hb.get("session_active"),
        "bot_scan_paused": hb.get("scan_paused"),
        # v116: a store-write halt is unhealthy until the partner unpauses.
        "bot_healthy": False if halted else healthy,
        "bot_last_success": last_success,
        "bot_consecutive_failures": int(hb.get("consecutive_failures") or 0),
        "bot_store_write_failure": halted,
    }
```

- [ ] **Step 8: Run the new and neighbouring tests**

Run: `python scripts/dev/testrun.py file tests/commands/test_store_write_halt.py tests/scanning/test_heartbeat_outcome.py tests/commands/test_heartbeat_stage_reads.py tests/admin/test_api_v1_system_scan.py tests/commands/test_system_notices.py tests/commands/test_scan_paused_db.py`
Expected: PASS.

- [ ] **Step 9: Complexity and commit**

Run: `python -m radon cc -s swingbot/commands/scanning/loops.py swingbot/core/scanning/scan_run.py swingbot/core/db/write_failure.py | grep -E "session_scan |_halt_on|_persist_plan_v2|is_store_write|halts_issuance"` — all A/B.

```bash
git add swingbot/core/db/write_failure.py swingbot/core/scanning/scan_run.py swingbot/commands/scanning/loops.py swingbot/commands/scanning/notices.py swingbot/commands/scanning/runstate.py swingbot/admin/app.py tests/commands/test_store_write_halt.py
git commit -m "feat(v116): a store write failure at db pauses alerting instead of issuing an unrecorded trade

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-24: Soak tooling — nightly check, its cron, and the gate that reads it

**Files:**
- Create: `scripts/ops/v116_soak.py`
- Create: `scripts/ops/v116_parity_check.sh`, `scripts/ops/install_v116_soak_cron.sh`
- Create: `tests/scripts/test_v116_soak.py`

**Interfaces:**
- Consumes: `parity_report.STAGE_STORES`, `parity_report.parity` (V116-06); `stages.parse`, `config.DB_STORES`; `swingbot.core.market.session.NYSE_HOLIDAYS`.
- Produces: `v116_soak.GROUPS` (`_0-index.md` table), `VERDICT_RE`, `group_stage(stage_by_store, group) -> str` (`json`/`dual`/`db`/`mixed`), `check_lines(day, trading_day, error_lines, stage_by_store, parity_ok) -> list[str]`, `gate(lines, group, stage, need=5) -> tuple[str, int]` (`PASS`/`WAIT`/`DIRTY`, streak). Log line format: `VERDICT day=YYYY-MM-DD trading_day=yes|no group=<g> stage=<s> result=CLEAN|DIRTY errors=<n>`. `/opt/swing-bot/logs/v116_parity.log`, cron `15 22 * * 1-5`. Every gate task in `_4c-flips.md` runs `gate`.

- [ ] **Step 1: Write the failing tests** — `tests/scripts/test_v116_soak.py`:

```python
"""The v116 soak: what the nightly check logs and how a gate reads it."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import v116_soak as soak  # noqa: E402
from scripts.db.parity_report import STAGE_STORES  # noqa: E402

DUAL_OPS = {name: "dual" for name in soak.GROUPS["ops"]}


def _line(day, result="CLEAN", stage="dual", trading="yes", group="ops"):
    return (f"VERDICT day={day} trading_day={trading} group={group} "
            f"stage={stage} result={result} errors=0")


def test_every_stage_name_is_in_exactly_one_group():
    names = [name for group in soak.GROUPS.values() for name in group]
    assert len(names) == len(set(names))
    assert set(STAGE_STORES) <= set(names)


def test_group_stage_reports_mixed_mid_flip():
    assert soak.group_stage(DUAL_OPS, "ops") == "dual"
    assert soak.group_stage({**DUAL_OPS, "flags": "db"}, "ops") == "mixed"
    assert soak.group_stage({}, "trading") == "json"


def test_check_is_clean_only_with_parity_clean_and_no_errors():
    clean = soak.check_lines("2026-10-05", True, 0, DUAL_OPS, lambda _n: True)
    assert clean[-1] == _line("2026-10-05")
    dirty = soak.check_lines("2026-10-05", True, 3, DUAL_OPS, lambda _n: True)
    assert dirty[-1].endswith("result=DIRTY errors=3")
    parity_bad = soak.check_lines("2026-10-05", True, 0, DUAL_OPS, lambda n: n != "jobs")
    assert "result=DIRTY" in parity_bad[-1]
    assert any("parity[jobs] DIRTY" in line for line in parity_bad)


def test_check_skips_groups_still_at_json():
    assert soak.check_lines("2026-10-05", True, 0, {}, lambda _n: True) == []


def test_five_consecutive_clean_trading_days_pass():
    days = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    assert soak.gate([_line(d) for d in days], "ops", "dual") == ("PASS", 5)


def test_four_days_wait():
    days = ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
    assert soak.gate([_line(d) for d in days], "ops", "dual") == ("WAIT", 4)


def test_a_dirty_day_fails_and_restarts_the_count():
    lines = [_line("2026-10-05"), _line("2026-10-06", "DIRTY")]
    assert soak.gate(lines, "ops", "dual") == ("DIRTY", 0)
    lines += [_line("2026-10-07"), _line("2026-10-08")]
    assert soak.gate(lines, "ops", "dual") == ("WAIT", 2)


def test_a_missing_weekday_breaks_the_streak_but_a_logged_holiday_does_not():
    gap = [_line("2026-10-05"), _line("2026-10-06"), _line("2026-10-08")]
    assert soak.gate(gap, "ops", "dual") == ("WAIT", 1)
    holiday = [_line("2026-10-05"), _line("2026-10-06"),
               _line("2026-10-07", trading="no"), _line("2026-10-08")]
    assert soak.gate(holiday, "ops", "dual") == ("WAIT", 3)


def test_days_at_another_stage_do_not_count():
    lines = [_line("2026-10-05", stage="db"), _line("2026-10-06")]
    assert soak.gate(lines, "ops", "dual") == ("WAIT", 1)


def test_the_cron_script_counts_database_errors_and_calls_check():
    text = (ROOT / "scripts" / "ops" / "v116_parity_check.sh").read_text(encoding="utf-8")
    assert "logs/v116_parity.log" in text
    assert "StoreWriteHalt" in text and "sqlalchemy" in text and "dual\\[" in text
    assert "v116_soak.py check --error-lines" in text
    assert b"\r" not in (ROOT / "scripts" / "ops" / "v116_parity_check.sh").read_bytes()
    installer = (ROOT / "scripts" / "ops" / "install_v116_soak_cron.sh").read_text(encoding="utf-8")
    assert "15 22 * * 1-5" in installer
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_v116_soak.py`
Expected: FAIL — `ModuleNotFoundError: v116_soak`.

- [ ] **Step 3: `scripts/ops/v116_soak.py`**

```python
#!/usr/bin/env python3
"""v116 Phase 3 soak: the nightly check, and the gate that reads its log.

    check  inside the bot container, from v116_parity_check.sh (cron, 22:15 UTC Mon-Fri):
           python scripts/ops/v116_soak.py check --error-lines N [--day YYYY-MM-DD]
    gate   on a copy of logs/v116_parity.log (stdlib only):
           python scripts/ops/v116_soak.py gate --log FILE --group ops --stage dual [--need 5]

A group's day is CLEAN when every store of it at `dual` with a parity spec
compares clean and no database error line was logged in the last 24 h.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

GROUPS: dict[str, tuple[str, ...]] = {
    "ops": ("flags", "heartbeat", "jobs", "scheduled_jobs", "killswitch",
            "notify_queue", "scan_progress", "market_data_state"),
    "reference": ("watchlist", "state", "ticker_directory", "preferences",
                  "settings_audit", "tuning"),
    "trading": ("plans", "starred_plans", "trades", "account", "journal"),
}
VERDICT_RE = re.compile(r"^VERDICT day=(?P<day>\S+) trading_day=(?P<trading>yes|no) "
                        r"group=(?P<group>\S+) stage=(?P<stage>\S+) result=(?P<result>CLEAN|DIRTY)")


def group_stage(stage_by_store: dict, group: str) -> str:
    found = {stage_by_store.get(store, "json") for store in GROUPS[group]}
    return found.pop() if len(found) == 1 else "mixed"


def _store_lines(group: str, stage_by_store: dict, parity_ok) -> tuple[list[str], bool]:
    from scripts.db.parity_report import STAGE_STORES
    lines, clean = [], True
    for store in GROUPS[group]:
        stage = stage_by_store.get(store, "json")
        names = STAGE_STORES.get(store, ())
        if stage != "dual" or not names:
            why = "no parity spec (ephemeral)" if not names else f"parity not applicable at {stage}"
            lines.append(f"  {store:<18} {stage:<5} n/a -- {why}")
            continue
        for name in names:
            ok = parity_ok(name)
            clean = clean and ok
            lines.append(f"  {store:<18} {stage:<5} parity[{name}] {'clean' if ok else 'DIRTY'}")
    return lines, clean


def check_lines(day: str, trading_day: bool, error_lines: int, stage_by_store: dict,
                parity_ok) -> list[str]:
    out = []
    for group in GROUPS:
        stage = group_stage(stage_by_store, group)
        if stage == "json":
            continue
        lines, clean = _store_lines(group, stage_by_store, parity_ok)
        result = "CLEAN" if clean and error_lines == 0 and stage != "mixed" else "DIRTY"
        out.extend([f"--- group {group} ({stage}) ---", *lines,
                    f"VERDICT day={day} trading_day={'yes' if trading_day else 'no'} "
                    f"group={group} stage={stage} result={result} errors={error_lines}"])
    return out


def _weekday_lines(lines: list[str], group: str) -> dict[str, re.Match]:
    by_day = {}
    for line in lines:
        match = VERDICT_RE.match(line.strip())
        if match and match["group"] == group:
            by_day[match["day"]] = match          # a re-run the same day wins
    return by_day


def gate(lines: list[str], group: str, stage: str, need: int = 5) -> tuple[str, int]:
    """PASS after `need` consecutive clean trading days at `stage`; DIRTY if
    the latest trading day was dirty; else WAIT. A weekday with no line at
    all (the cron did not run) breaks the streak; a logged holiday does not."""
    by_day = _weekday_lines(lines, group)
    if not by_day:
        return "WAIT", 0
    day = dt.date.fromisoformat(min(by_day))
    last = dt.date.fromisoformat(max(by_day))
    streak, latest = 0, None
    while day <= last:
        match = by_day.get(day.isoformat())
        if match is None and day.weekday() < 5:
            streak = 0
        elif match is not None and match["trading"] == "yes":
            ok = match["stage"] == stage and match["result"] == "CLEAN"
            streak, latest = (streak + 1 if ok else 0), ok
        day += dt.timedelta(days=1)
    if streak >= need:
        return "PASS", streak
    return ("DIRTY" if latest is False else "WAIT"), streak


def _is_trading_day(day: dt.date) -> bool:
    from swingbot.core.market.session import NYSE_HOLIDAYS
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS


def _parity_ok(name: str) -> bool:
    from scripts.db.parity_report import parity
    try:
        report = parity(name)
    except Exception as exc:  # noqa: BLE001 -- an erroring compare is not clean
        print(f"  parity[{name}] raised {type(exc).__name__}: {exc}")
        return False
    return report.ok


def _cmd_check(args) -> int:
    from swingbot import config
    from swingbot.core.db import stages
    day = dt.date.fromisoformat(args.day) if args.day else dt.datetime.now(dt.timezone.utc).date()
    print(f"DB_STORES={config.DB_STORES}")
    for line in check_lines(day.isoformat(), _is_trading_day(day), args.error_lines,
                            stages.parse(config.DB_STORES), _parity_ok):
        print(line)
    return 0


def _cmd_gate(args) -> int:
    with open(args.log, encoding="utf-8") as handle:
        verdict, streak = gate(handle.read().splitlines(), args.group, args.stage, args.need)
    print(f"GATE group={args.group} stage={args.stage} streak={streak} need={args.need} {verdict}")
    return {"PASS": 0, "WAIT": 3, "DIRTY": 1}[verdict]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--error-lines", type=int, required=True)
    check.add_argument("--day")
    gate_cmd = sub.add_parser("gate")
    gate_cmd.add_argument("--log", required=True)
    gate_cmd.add_argument("--group", required=True, choices=sorted(GROUPS))
    gate_cmd.add_argument("--stage", required=True, choices=("dual", "db"))
    gate_cmd.add_argument("--need", type=int, default=5)
    args = parser.parse_args(argv)
    return _cmd_check(args) if args.command == "check" else _cmd_gate(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: `scripts/ops/v116_parity_check.sh`**

```bash
#!/usr/bin/env bash
# Nightly v116 Phase 3 soak check, run BY CRON ON THE VM at 22:15 UTC Mon-Fri
# (after the US close). Counts database error lines in the last 24 h of the
# bot and admin logs, runs parity for every group not at json, and appends
# one block per run to logs/v116_parity.log. Read-only against the stores.
# The gate tasks read the log with `scripts/ops/v116_soak.py gate`.
set -uo pipefail
cd /opt/swing-bot || exit 1
LOG=/opt/swing-bot/logs/v116_parity.log
PATTERN='dual\[|sqlalchemy\.exc\.|psycopg\.|DatabaseUnavailable|StoreWriteHalt'

{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) v116 soak check ==="
  ERRORS=$(docker compose logs --since 24h bot admin </dev/null 2>&1 | grep -cE "$PATTERN")
  echo "--- database error lines, last 24h: ${ERRORS} (first 20) ---"
  docker compose logs --since 24h bot admin </dev/null 2>&1 | grep -E "$PATTERN" | head -20
  docker compose exec -T bot python scripts/ops/v116_soak.py check --error-lines "$ERRORS" </dev/null 2>&1
} >> "$LOG" 2>&1
```

- [ ] **Step 5: `scripts/ops/install_v116_soak_cron.sh`**

```bash
#!/usr/bin/env bash
# Installs (idempotently) the v116 soak cron on the Hetzner VM. Run ON the VM:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v116_soak_cron.sh
# Removed by V116-42 once Phase 4 ships.
set -euo pipefail
MARKER='# v116 soak check (installed by install_v116_soak_cron.sh)'
chmod +x /opt/swing-bot/scripts/ops/v116_parity_check.sh
{
  crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "v116_parity_check" || true
  echo "$MARKER"
  echo "15 22 * * 1-5 /opt/swing-bot/scripts/ops/v116_parity_check.sh"
} | crontab -
crontab -l
```

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_v116_soak.py` — PASS. `bash -n scripts/ops/v116_parity_check.sh && bash -n scripts/ops/install_v116_soak_cron.sh` — no output.

- [ ] **Step 7: Complexity and commit**

Run: `python -m radon cc -s -n C scripts/ops/v116_soak.py` — no output.

```bash
git add --chmod=+x scripts/ops/v116_soak.py scripts/ops/v116_parity_check.sh scripts/ops/install_v116_soak_cron.sh
git add tests/scripts/test_v116_soak.py
git commit -m "feat(v116): nightly soak check, its VM cron, and the five-trading-day gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-25: Round-trip every store against a pulled production snapshot

**Files:**
- Create: `scripts/ops/pull_prod_snapshot.sh`
- Modify: `.gitignore` (`data/v116_snapshot/`)
- Create: `tests/db/test_prod_snapshot_round_trip.py`

**Interfaces:**
- Consumes: the importers `scripts/db/import_*.py` (`load_source`, `write_one`, `prepare`), `parity_report.parity`/`STORES`, `export_json.run_export` + `EXTRA` (V116-20/21), `store_db`.
- Produces: the committed round-trip tests the `schema-change` skill's gate asks for, run against real production data. They skip (with the pull command in the reason) when no snapshot is present, so CI stays green. V116-26 runs them on a fresh snapshot and records the result.

- [ ] **Step 1: `scripts/ops/pull_prod_snapshot.sh`** (runs on the dev machine, Git Bash):

```bash
#!/usr/bin/env bash
# Pull a read-only copy of production's store files into data/v116_snapshot/
# for tests/db/test_prod_snapshot_round_trip.py (v116 Phase 3). Gitignored;
# never commit it. Read-only on the VM: it only tars and streams.
#   bash scripts/ops/pull_prod_snapshot.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"
OUT=data/v116_snapshot
FILES="trades.json plans.json starred_plans.json account.json state.json journal.json \
watchlist.json admin_jobs.json scheduled_jobs.json ui_preferences.json settings_audit.jsonl \
killswitch.json ticker_directory.json tuning_results tuning_proposals scan_paused.flag \
trigger_check.flag scan_running.flag stop_scan.flag bot_heartbeat.json manual_close_notify.json \
market_data_state.json scan_progress.json"

rm -rf "$OUT.tmp"
mkdir -p "$OUT.tmp"
bash "$SSH_HETZNER" "cd /opt/swing-bot/data && tar czf - \$(ls -d $FILES 2>/dev/null) | base64 -w0" \
  | base64 -d | tar xzf - -C "$OUT.tmp"
rm -rf "$OUT"
mv "$OUT.tmp" "$OUT"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/PULLED_AT"
ls -la "$OUT"
```

Append to `.gitignore` (Data directories block): `data/v116_snapshot/`.

- [ ] **Step 2: Write the test** — `tests/db/test_prod_snapshot_round_trip.py`:

```python
"""Rollback readiness on the real book (v116 Phase 3; the schema-change
skill's gate). Each production file is written through its importer, read
back through its repository and compared by parity; then exported and
compared again -- so db -> json is proven on production data, not a fixture.

Skips without a snapshot (bash scripts/ops/pull_prod_snapshot.sh) or db-test."""
import json
import os
import pathlib

import pytest

from scripts.db import export_json
from scripts.db import (import_jobs, import_journal, import_killswitch, import_plans,
                        import_preferences, import_scheduled, import_settings_audit,
                        import_starred, import_state, import_ticker_directory, import_trades,
                        import_tuning, import_watchlist)
from scripts.db.parity_report import STORES, parity
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.flags import FLAGS, flags_repo
from swingbot.core.db.repositories.heartbeat import heartbeat_repo
from swingbot.core.db.repositories.market_data_state import market_data_state_repo
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.scan_progress import scan_progress_repo
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = pathlib.Path(os.getenv("V116_SNAPSHOT_DIR", REPO / "data" / "v116_snapshot"))
pytestmark = pytest.mark.skipif(
    not (SNAPSHOT / "PULLED_AT").exists(),
    reason="no production snapshot; run: bash scripts/ops/pull_prod_snapshot.sh")

#: store -> (load_source(path) -> rows, repository factory, write_one, prepare or None).
#: plans before starred_plans (foreign key).
IMPORTS = {
    "watchlist": (import_watchlist.load_source, STORES["watchlist"].repo_factory, import_watchlist.write_one, None),
    "state": (import_state.load_source, STORES["state"].repo_factory, import_state.write_one, None),
    "plans": (import_plans.load_source, STORES["plans"].repo_factory, import_plans.write_one, None),
    "starred_plans": (import_starred.load_source, STORES["starred_plans"].repo_factory, import_starred.write_one, None),
    "trades": (import_trades.load_source, STORES["trades"].repo_factory, import_trades.write_one, None),
    "journal": (import_journal.load_source, STORES["journal"].repo_factory, import_journal.write_one, None),
    "jobs": (import_jobs.load_source, STORES["jobs"].repo_factory, import_jobs.write_one, None),
    "scheduled_jobs": (import_scheduled.load_source, STORES["scheduled_jobs"].repo_factory, import_scheduled.write_one, None),
    "preferences": (import_preferences.load_source, STORES["preferences"].repo_factory, import_preferences.write_one, None),
    "settings_audit": (import_settings_audit.load_source, SettingsAuditRepository, import_settings_audit.write_one, import_settings_audit.prepare),
    "killswitch": (import_killswitch.load_source, STORES["killswitch"].repo_factory, import_killswitch.write_one, None),
    "ticker_directory": (import_ticker_directory.load_source, STORES["ticker_directory"].repo_factory, import_ticker_directory.write_one, None),
    "tuning": (import_tuning.load_results, TuningRepository, import_tuning.write_one, None),
    "tuning_proposals": (import_tuning.load_proposals, ProposalRepository, import_tuning.write_one, None),
}


def _import(name: str, source: str) -> None:
    load, factory, write_one, prepare = IMPORTS[name]
    repo = factory()
    if prepare is not None:
        prepare(repo)
    for record in load(source):
        write_one(repo, record)


def test_every_parity_store_round_trips_production_data(store_db, tmp_path):
    failures, seen = {}, []
    account = SNAPSHOT / "account.json"
    if account.exists():
        AccountRepository().save(json.loads(account.read_text(encoding="utf-8")))
    for name in IMPORTS:
        source = SNAPSHOT / STORES[name].filename
        if not source.exists():
            continue
        seen.append(name)
        _import(name, str(source))
        imported = parity(name, source_path=str(source))
        if not imported.ok:
            failures[f"{name}: import"] = imported.render()
            continue
        export_json.run_export([name], str(tmp_path), dry_run=False, force=True)
        exported = parity(name, source_path=str(tmp_path / STORES[name].filename))
        if not exported.ok:
            failures[f"{name}: export"] = exported.render()
    assert seen, "the snapshot holds none of the store files"
    assert not failures, "\n".join(f"[{key}]\n{value}" for key, value in failures.items())


def _load(name):
    path = SNAPSHOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_the_ops_stores_round_trip_production_data(store_db, tmp_path):
    state = _load("market_data_state.json")
    if state is not None:
        market_data_state_repo().save(state)
    heartbeat = _load("bot_heartbeat.json")
    if heartbeat is not None:
        heartbeat_repo().beat(heartbeat)
    for record in _load("manual_close_notify.json") or []:
        NotifyQueueRepository().enqueue(record)
    progress = _load("scan_progress.json")
    if progress is not None:
        scan_progress_repo().publish(progress)
    raised = [name for name in FLAGS if (SNAPSHOT / f"{name}.flag").exists()]
    for name in raised:
        flags_repo().set(name)

    export_json.run_export(list(export_json.EXTRA), str(tmp_path), dry_run=False, force=True)

    if state is not None:
        assert _json(tmp_path / "market_data_state.json") == state
    if heartbeat is not None:
        exported = _json(tmp_path / "bot_heartbeat.json")
        assert {key: exported.get(key) for key in heartbeat} == heartbeat
    assert (_json(tmp_path / "manual_close_notify.json") or []) == (_load("manual_close_notify.json") or [])
    if progress is not None:
        assert _json(tmp_path / "scan_progress.json") == progress
    assert sorted(p.stem for p in tmp_path.glob("*.flag")) == sorted(raised)


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
```

- [ ] **Step 3: Run it without a snapshot (the CI shape)**

Run: `python scripts/dev/testrun.py file tests/db/test_prod_snapshot_round_trip.py`
Expected: 2 skipped, reason "no production snapshot".

- [ ] **Step 4: Run it against a real snapshot, locally**

```bash
bash scripts/ops/pull_prod_snapshot.sh
docker compose --profile test up -d db-test
python scripts/dev/testrun.py file tests/db/test_prod_snapshot_round_trip.py
```

Expected: 2 passed. A failure is a real finding (the rollback path would corrupt that store): fix the shaper, loader or repository in its own commit, re-pull, re-run. Never loosen a comparison to pass. Write the snapshot's `PULLED_AT`, the per-store row counts (`wc -l`/`jq length` on the files) and the result into this task's commit message.

- [ ] **Step 5: Commit**

```bash
git add --chmod=+x scripts/ops/pull_prod_snapshot.sh
git add .gitignore tests/db/test_prod_snapshot_round_trip.py
git commit -m "test(v116): round-trip every store against a pulled production snapshot

Snapshot pulled <PULLED_AT>: <store counts>. Result: <2 passed>.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-26: Ship Phase 1–3 readiness and install the soak cron — TOUCHES PRODUCTION

**Files:**
- Modify: `docs/deploy/DB_RESTORE.md` (`### Rollback readiness <date>` under the v116 section)

**Interfaces:**
- Consumes: every task in Phases 1 and 2 and V116-20 … V116-25; Phase 0 live (V116-09) and drilled (V116-10).
- Produces: production at Alembic head `v116_002` with NOTIFY triggers on every `TABLE_CHANNELS` table, readiness code deployed, `logs/v116_parity.log` receiving nightly blocks. `DB_STORES` is untouched (`watchlist:dual,state:dual`). The flips (`_4c-flips.md`) start from here.

Use the `mirror-prod` and `worktree-lifecycle` skills. Outside the session window.

- [ ] **Step 1: Gate the branch**

`python scripts/dev/testrun.py fast` — `0 failed`. `python -m alembic heads` — `v116_002 (head)`. `python -m radon cc -s -n C swingbot/core/db swingbot/admin/events swingbot/core/scanning/progress_store.py swingbot/core/marketdata/data_refresh.py scripts/db scripts/ops/*.py` — nothing new.

- [ ] **Step 2: Merge to `main` and let CI deploy** — same commands as V116-09 Step 2, message `merge(v116): Phases 1-2 and Phase 3 readiness`.

- [ ] **Step 3: Migrate and verify the triggers**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic upgrade head && docker compose exec -T bot alembic current"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -tAc \"select tgname from pg_trigger where not tgisinternal order by 1\""
```

Expected: `v116_002 (head)`; one `<table>_notify_trg` per `events.TABLE_CHANNELS` entry, including `scan_progress_notify_trg` and `market_data_state_notify_trg` (21 in total).

- [ ] **Step 4: Nothing changed for the running stores**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py --get DB_STORES && docker compose exec -T bot python scripts/db/parity_report.py --dual"
```

Expected: `watchlist:dual,state:dual`; both parity blocks `VERDICT: OK`.

- [ ] **Step 5: Install the soak cron and run it once by hand**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v116_soak_cron.sh
bash scripts/ops/ssh-hetzner.sh "/opt/swing-bot/scripts/ops/v116_parity_check.sh; tail -20 /opt/swing-bot/logs/v116_parity.log"
```

Expected: the crontab shows the v116 line; the log block lists `group reference (mixed)` with `result=DIRTY` (only watchlist/state are at dual — expected until V116-29) and database error lines `0`. Any non-zero error count is investigated before V116-27.

- [ ] **Step 6: Re-run the production round trip on a fresh snapshot**

`bash scripts/ops/pull_prod_snapshot.sh && python scripts/dev/testrun.py file tests/db/test_prod_snapshot_round_trip.py` — 2 passed.

- [ ] **Step 7: Record and commit on `main`**

Append to `docs/deploy/DB_RESTORE.md` under the v116 section: `### Rollback readiness <date>` with the head (`v116_002`), the trigger count, the soak cron line, the snapshot `PULLED_AT` and "round trip 2 passed". Commit (`docs(v116): record rollback readiness on production`) and push, then merge `origin/main` back into the worktree branch.
