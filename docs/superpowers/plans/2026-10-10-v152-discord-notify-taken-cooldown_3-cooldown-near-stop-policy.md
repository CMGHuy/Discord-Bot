# v152 part 3: per-symbol cooldown, near-stop event, notify policy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V152-12:" -A 400 docs/superpowers/plans/2026-10-10-v152-discord-notify-taken-cooldown_3-cooldown-near-stop-policy.md`.

**Bump:** bot minor · ui patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § D3, § D1 (near-stop detection, event mapping, `/notify` defaults)
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, Decisions fixed by this index (4, 9, 10, 13, 14 bind this part), the task ledger and the full `## Parallelisation` live there and bind every task below.

Tasks V152-11 .. V152-13 here; V152-14 and V152-15 continue in [`_3b-policy-and-loops`](2026-10-10-v152-discord-notify-taken-cooldown_3b-policy-and-loops.md) (same part, split only to stay under 1500 lines). None is v151-gated. Part 1 creates what this part consumes: `alert_posts_repo()` with `add` / `posted_since` / `count_since` / `prune_before` (V152-4, `swingbot/core/db/repositories/alert_posts.py`) and `config.ALERT_SYMBOL_COOLDOWN_HOURS` (V152-5). Every test that touches the database gets the worker's test database and has its tables truncated afterwards (`tests/conftest.py::_store_database`, autouse), so the cooldown tests below run against the real repository.

Test plan ids are 36-char dashed uuids, like part 2's: the persistent `custom_id` template (V152-6) rejects short ids.

## Parallelisation

- **V152-11** (`cooldown.py` + its test) needs V152-4 and V152-5 only; parallel with every part-2 task, V152-13 and V152-14.
- **V152-12 after V152-11** (calls `cooldown.suppressed` / `record` / `held_today`). Files: `alerts.py`, its new test, and the `_record_order` fake in `tests/scanning/test_short_lane_scan.py` (no other task touches either).
- **V152-13** (`plan_manager.py`, `lifecycle_embeds.py`) and **V152-14** (`follow_notify.py`, pure) are parallel with each other and with V152-11/V152-12: disjoint files, no shared symbol.
- **V152-15** (in `_3b`) after V152-12 and V152-11. Part 4's V152-18 edits `loops.py` after it.

# Phase 4: Per-symbol alert cooldown

### Task V152-11: `cooldown.py`: window, record, note, prune

**Model:** sonnet — a small new module over an existing repository; the judgement is in the fail-open contract and the Berlin day boundary, both pinned by tests below.

**Files:**
- Create: `swingbot/commands/scanning/cooldown.py`
- Create: `tests/commands/test_cooldown.py`

**Consumes:** `alert_posts_repo()` (V152-4): `add(ticker, at, outcome, *, direction, horizon_key, plan_id)`, `posted_since(ticker, direction, horizon_key, since) -> bool`, `count_since(outcome, since) -> int`, `prune_before(cutoff) -> int`; `config.ALERT_SYMBOL_COOLDOWN_HOURS: float` (V152-5); `swingbot.core.market.session.BERLIN_TZ`, `now_berlin` (exist, `session.py:16`, `:39`).
**Produces (ledger):** `suppressed(plan, now=None) -> bool` (fail-open `False`); `record(plan, outcome: str, now=None) -> None` (fail-open); `held_note(held: list) -> str | None` (pure; `None` when empty); `held_today(now=None) -> int` (Berlin session date; `0` on error); `prune(now=None) -> int` (cutoff `max(hours, 168)` h; raises — the `daily_recap` caller in V152-15 logs).

**Design.**
- The key is `(plan.ticker, plan.direction, plan.horizon_key)` (spec § D3 Rule). Only `posted` rows open a window (V152-4's `posted_since` filters `outcome = 'posted'`), so a held alert never extends its own window.
- `ALERT_SYMBOL_COOLDOWN_HOURS <= 0` turns the **check** off (`suppressed` is `False` without a DB read). `record` still writes: the spec writes a row "after Discord accepts a post, or when a post is suppressed", unconditionally, and the record is how D3 is measured after launch (spec § D3 Expected volume). Only the scheduled path calls `record` at all (index decision 4).
- Fail open: `suppressed`, `record` and `held_today` catch every exception, log one WARNING with the traceback, and return `False` / `None` / `0`. Both callers in V152-12 run them through `asyncio.to_thread`.
- `held_today` counts `suppressed` rows since 00:00 Europe/Berlin of `now`'s Berlin date (index decision 14), not UTC midnight.
- `prune` deletes rows older than `max(ALERT_SYMBOL_COOLDOWN_HOURS, 168)` hours: the window is never cut short and a week of history is kept for the digest and M0-style reads (spec § D3 Record: "older than `max(ALERT_SYMBOL_COOLDOWN_HOURS, 7 days)`").
- `held_note` wording is the spec's: `Cooldown held 2 alert(s) this scan: AAPL long 4w, MSFT short 2w (posted within 24h).` `bullish`/`bearish` read `long`/`short`; the hours print with `:g` (24.0 → `24`, 12.5 → `12.5`).

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_cooldown.py`:

```python
"""v152 D3: the per-symbol alert cooldown module.

Real alert_posts table (tests/conftest.py gives each test the worker's test
database and truncates it afterwards). The module must fail open: a fault in
the window read or the record write posts the alert and logs one WARNING.
"""
import datetime as dt
import logging
import types

import pytest

from swingbot import config
from swingbot.commands.scanning import cooldown
from swingbot.core.db.repositories.alert_posts import alert_posts_repo
from swingbot.core.market.session import BERLIN_TZ

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


def _plan(ticker="AAPL", direction="bullish", horizon_key="4w",
          plan_id="3b2f0c1e-8a4d-4f7e-9c61-2d5e8f9a1b07"):
    return types.SimpleNamespace(plan_id=plan_id, ticker=ticker, direction=direction,
                                 horizon_key=horizon_key)


@pytest.fixture(autouse=True)
def _hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 24.0, raising=False)


class _Broken:
    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise RuntimeError("database is having a day")
        return _raise


def _warnings(caplog):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and r.name == cooldown.log.name]


def test_same_key_posted_inside_the_window_is_suppressed():
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(_plan(), now=T0) is True


@pytest.mark.parametrize("other", [
    _plan(direction="bearish"),          # flipped direction posts
    _plan(horizon_key="2w"),             # another horizon posts
    _plan(ticker="MSFT"),                # another ticker posts
])
def test_a_different_key_is_never_suppressed(other):
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(other, now=T0) is False


def test_a_post_outside_the_window_does_not_suppress():
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=25))
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_a_held_alert_does_not_open_or_extend_a_window():
    cooldown.record(_plan(), "suppressed", now=T0 - dt.timedelta(hours=1))
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_zero_hours_turns_the_check_off_without_a_read(monkeypatch):
    cooldown.record(_plan(), "posted", now=T0 - dt.timedelta(hours=1))
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 0.0, raising=False)
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    assert cooldown.suppressed(_plan(), now=T0) is False


def test_record_writes_the_doc_keys_the_window_reads():
    cooldown.record(_plan(), "posted", now=T0)
    rows = alert_posts_repo().list_all()
    assert len(rows) == 1
    row = rows[0]
    assert (row["ticker"], row["outcome"]) == ("AAPL", "posted")
    assert (row["direction"], row["horizon_key"], row["plan_id"]) == (
        "bullish", "4w", "3b2f0c1e-8a4d-4f7e-9c61-2d5e8f9a1b07")


def test_a_failing_read_posts_anyway_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.suppressed(_plan(), now=T0) is False
    assert len(_warnings(caplog)) == 1
    assert _warnings(caplog)[0].exc_info is not None


def test_a_bad_hours_value_fails_open(monkeypatch, caplog):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", "soon", raising=False)
    with caplog.at_level(logging.WARNING):
        assert cooldown.suppressed(_plan(), now=T0) is False
    assert len(_warnings(caplog)) == 1


def test_a_failing_write_never_raises_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.record(_plan(), "posted", now=T0) is None
    assert len(_warnings(caplog)) == 1


def test_held_note_is_none_without_held_alerts():
    assert cooldown.held_note([]) is None


def test_held_note_names_each_held_alert_and_the_window():
    held = [_plan(), _plan(ticker="MSFT", direction="bearish", horizon_key="2w")]
    assert cooldown.held_note(held) == (
        "Cooldown held 2 alert(s) this scan: AAPL long 4w, MSFT short 2w "
        "(posted within 24h).")


def test_held_note_prints_fractional_hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 12.5, raising=False)
    assert cooldown.held_note([_plan()]).endswith("(posted within 12.5h).")


def test_held_today_counts_from_berlin_midnight_not_utc():
    now = dt.datetime(2026, 10, 12, 0, 30, tzinfo=BERLIN_TZ)        # 22:30 UTC on the 11th
    cooldown.record(_plan(), "suppressed",
                    now=dt.datetime(2026, 10, 11, 23, 0, tzinfo=BERLIN_TZ))   # yesterday in Berlin
    cooldown.record(_plan(ticker="MSFT"), "suppressed",
                    now=dt.datetime(2026, 10, 12, 0, 10, tzinfo=BERLIN_TZ))   # today in Berlin
    cooldown.record(_plan(ticker="NVDA"), "posted",
                    now=dt.datetime(2026, 10, 12, 0, 15, tzinfo=BERLIN_TZ))   # posted, not held
    assert cooldown.held_today(now=now) == 1


def test_held_today_is_zero_on_error(monkeypatch, caplog):
    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: _Broken())
    with caplog.at_level(logging.WARNING):
        assert cooldown.held_today(now=T0) == 0
    assert len(_warnings(caplog)) == 1


def test_prune_keeps_a_week_when_the_window_is_shorter():
    for hours in (200, 100, 1):
        cooldown.record(_plan(ticker=f"T{hours}"), "posted", now=T0 - dt.timedelta(hours=hours))
    assert cooldown.prune(now=T0) == 1
    assert sorted(r["ticker"] for r in alert_posts_repo().list_all()) == ["T1", "T100"]


def test_prune_never_cuts_into_a_window_longer_than_a_week(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 200.0, raising=False)
    for hours in (201, 199):
        cooldown.record(_plan(ticker=f"T{hours}"), "posted", now=T0 - dt.timedelta(hours=hours))
    assert cooldown.prune(now=T0) == 1
    assert [r["ticker"] for r in alert_posts_repo().list_all()] == ["T199"]
    assert cooldown.suppressed(_plan(ticker="T199"), now=T0) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_cooldown.py`
Expected: FAIL — `ImportError: cannot import name 'cooldown' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Write `cooldown.py`**

Create `swingbot/commands/scanning/cooldown.py`:

```python
"""v152 D3: the per-symbol alert cooldown, owner of the alert_posts record.

On the scheduled session scan only (alerts._send_alerts(apply_cooldown=True)),
an alert for (ticker, direction, horizon_key) is not posted when one with the
same key was POSTED within ALERT_SYMBOL_COOLDOWN_HOURS. Only the Discord post
is held: the plan and its placeholder trade were persisted by scan_run before
any of this runs, so the book is unchanged.

Fails open: any error reading the window or writing the record posts the
alert and logs one WARNING -- a cooldown fault never costs an alert and never
raises into the scan. The callers run these through asyncio.to_thread.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot import config
from swingbot.core.db.repositories.alert_posts import alert_posts_repo
from swingbot.core.market.session import BERLIN_TZ, now_berlin

log = logging.getLogger(__name__)

PRUNE_FLOOR_HOURS = 168.0          # keep at least a week of alert_posts
_DIRECTION_WORDS = {"bullish": "long", "bearish": "short"}


def _now(now: dt.datetime | None) -> dt.datetime:
    return now if now is not None else dt.datetime.now(dt.timezone.utc)


def _hours() -> float:
    return float(config.ALERT_SYMBOL_COOLDOWN_HOURS or 0)


def suppressed(plan, now: dt.datetime | None = None) -> bool:
    """True when an alert with this plan's key was posted inside the window."""
    try:
        hours = _hours()
        if hours <= 0:
            return False
        since = _now(now) - dt.timedelta(hours=hours)
        return alert_posts_repo().posted_since(plan.ticker, plan.direction,
                                               plan.horizon_key, since)
    except Exception:
        log.warning("cooldown: window read failed for %s -- posting the alert anyway.",
                    getattr(plan, "ticker", "?"), exc_info=True)
        return False


def record(plan, outcome: str, now: dt.datetime | None = None) -> None:
    """Append one alert_posts row ('posted' after Discord accepted it, or
    'suppressed'). Never raises."""
    try:
        alert_posts_repo().add(plan.ticker, _now(now), outcome,
                               direction=plan.direction, horizon_key=plan.horizon_key,
                               plan_id=getattr(plan, "plan_id", None))
    except Exception:
        log.warning("cooldown: could not record the %s alert for %s.",
                    outcome, getattr(plan, "ticker", "?"), exc_info=True)


def _held_label(plan) -> str:
    direction = _DIRECTION_WORDS.get(plan.direction, plan.direction)
    return f"{plan.ticker} {direction} {plan.horizon_key}"


def held_note(held: list) -> str | None:
    """The one-line ops note for a scan that held alerts; None when it held none."""
    if not held:
        return None
    names = ", ".join(_held_label(plan) for plan in held)
    return (f"Cooldown held {len(held)} alert(s) this scan: {names} "
            f"(posted within {_hours():g}h).")


def held_today(now: dt.datetime | None = None) -> int:
    """Alerts held since 00:00 Europe/Berlin of today's Berlin date; 0 on error."""
    try:
        day = now_berlin(now).date()
        since = dt.datetime.combine(day, dt.time.min, tzinfo=BERLIN_TZ)
        return alert_posts_repo().count_since("suppressed", since)
    except Exception:
        log.warning("cooldown: could not count today's held alerts.", exc_info=True)
        return 0


def prune(now: dt.datetime | None = None) -> int:
    """Delete alert_posts rows older than max(window, one week). Raises: the
    nightly caller (loops.daily_recap) logs a failure."""
    keep = max(_hours(), PRUNE_FLOOR_HOURS)
    return alert_posts_repo().prune_before(_now(now) - dt.timedelta(hours=keep))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_cooldown.py`
Expected: PASS. A skip of every test means the test Postgres is down — start it and re-run; a skip is not a pass.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/cooldown.py`
Expected: no output (every function below C). If radon is missing: `pip install radon` first.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/cooldown.py tests/commands/test_cooldown.py
git commit -m "feat(v152): per-symbol alert cooldown module (fail-open window, record, note, prune)"
```

### Task V152-12: `_send_alerts(apply_cooldown=)` + digest held line

**Model:** sonnet — threads one keyword through three existing async functions and adds a digest suffix; the contract (filter before the cap, record after a successful send, return held plans) is fixed by the index.

**Files:**
- Modify: `swingbot/commands/scanning/alerts.py` (`_post_daily_digest` :53-85, `_post_alert` :205-217, `_send_alerts` :220-288, `post_short_universe` :291-305, `send_then_short` :308-313)
- Modify: `tests/scanning/test_short_lane_scan.py` (the `_record_order` fake at :253-266 only)
- Create: `tests/commands/test_send_alerts_cooldown.py`

**Consumes:** `cooldown.suppressed`, `cooldown.record`, `cooldown.held_today` (V152-11).
**Produces (ledger):** `_send_alerts(destination, alerts, route_by_confidence: bool = False, *, apply_cooldown: bool = False) -> list` (the held plans; `[]` when `apply_cooldown` is false); `_hold_by_cooldown(alerts: list) -> tuple[list, list]` (async; kept alerts, held plans); `post_short_universe(..., apply_cooldown: bool = False, held: list | None = None) -> list` (still returns the short alerts; extends `held`); `send_then_short(..., apply_cooldown: bool = False) -> list` (base + short held plans).

**Design.**
- `_hold_by_cooldown` runs **before** `_ordered_alerts` and the cap (spec § D3 Where: "Capped overflow ranks only what survives"), so a held alert sends neither the full alert nor its simple mirror and never appears in the `+N more` footer. A legacy alert (`alert[2] is None`) always passes, with no DB call. Each held plan is recorded `suppressed`.
- `posted` is recorded inside `_post_alert`, after `send_to.send(...)` returned, and only when `record_post=True` (= `apply_cooldown`): a failed send records nothing, and a `!check` / admin-UI / halt re-post never writes a row (index decision 4).
- Both cooldown calls go through `asyncio.to_thread`; both are fail-open (V152-11), so `_send_alerts` gains no `try`.
- `_send_alerts` gains exactly one branch (`if apply_cooldown:`): 9 → 10. `_post_alert` gains one (`if record_post and plan is not None:`).
- Existing callers ignore the new return value; none of them passes `apply_cooldown`. Only V152-15 passes `True`, from `_session_scan_tick` through `send_then_short`.
- Digest (index decision 14): `_post_daily_digest` appends ` · N alert(s) held by the symbol cooldown today` to its content line when `cooldown.held_today()` (via `to_thread`) is > 0 — on the header of the first embed and on the "no VALIDATED plans" line alike. `digest_payload` is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_send_alerts_cooldown.py`:

```python
"""v152 D3: _send_alerts(apply_cooldown=True) holds a repeat alert before the
cap, records posts only after Discord accepted them, and fails open; the
daily digest states how many alerts the cooldown held today."""
import asyncio
import logging
import types

import discord
import pytest

from swingbot import config
from swingbot.commands.scanning import alerts, cooldown
from swingbot.commands.scanning.alerts import _send_alerts, send_then_short
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

PIDS = {
    "AAPL": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a41",
    "MSFT": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a42",
    "NVDA": "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a43",
}


class Chan:
    def __init__(self, fail_on=()):
        self.sent, self.calls, self.fail_on = [], 0, set(fail_on)

    async def send(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=self.calls)


class FakeCooldown:
    def __init__(self, held_tickers=()):
        self.held_tickers = set(held_tickers)
        self.checked, self.recorded = [], []

    def suppressed(self, plan, now=None):
        self.checked.append(plan.ticker)
        return plan.ticker in self.held_tickers

    def record(self, plan, outcome, now=None):
        self.recorded.append((plan.ticker, outcome))


def _plan(ticker):
    return types.SimpleNamespace(plan_id=PIDS[ticker], ticker=ticker, direction="bullish",
                                 horizon_key="4w")


def _alert(ticker, plan=None):
    plan = plan if plan is not None else _plan(ticker)
    return (discord.Embed(title=ticker), None, plan, discord.Embed(title=f"{ticker}-simple"))


@pytest.fixture
def env(monkeypatch):
    from swingbot.commands import views
    from swingbot.core.analytics import rank

    class View:
        def __init__(self, plan_id, author_id=None):
            self.plan_id, self.message = plan_id, None

    simple = Chan()
    monkeypatch.setattr(views, "PlanActionView", View)
    monkeypatch.setattr(alerts, "rank_plans", lambda plans, today=None: list(plans))
    monkeypatch.setattr(rank, "follow_score", lambda plan: 50.0)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "999", raising=False)
    monkeypatch.setattr(alerts, "bot", types.SimpleNamespace(get_channel=lambda _id: simple),
                        raising=False)
    return simple


@pytest.fixture
def fake_cd(monkeypatch):
    def install(held_tickers=()):
        fake = FakeCooldown(held_tickers)
        monkeypatch.setattr(cooldown, "suppressed", fake.suppressed)
        monkeypatch.setattr(cooldown, "record", fake.record)
        return fake
    return install


def _titles(chan):
    return [s["embed"].title for s in chan.sent]


def test_the_default_path_never_reads_or_writes_the_cooldown(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    held = asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT")]))
    assert held == []
    assert _titles(main) == ["AAPL", "MSFT"]
    assert fake.checked == [] and fake.recorded == []


def test_a_held_alert_posts_neither_the_alert_nor_its_mirror(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    aapl = _plan("AAPL")
    held = asyncio.run(_send_alerts(main, [_alert("AAPL", aapl), _alert("MSFT")],
                                    apply_cooldown=True))
    assert held == [aapl]
    assert _titles(main) == ["MSFT"]
    assert _titles(env) == ["MSFT-simple"]
    assert fake.recorded == [("AAPL", "suppressed"), ("MSFT", "posted")]


def test_the_cap_ranks_only_what_survives(env, fake_cd, monkeypatch):
    fake_cd({"AAPL"})
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 1, raising=False)
    main = Chan()
    asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT"), _alert("NVDA")],
                             apply_cooldown=True))
    assert _titles(main) == ["MSFT"]
    assert main.sent[0]["embed"].footer.text == "+1 more: NVDA (50)"


def test_a_legacy_alert_passes_without_a_check(env, fake_cd):
    fake = fake_cd({"AAPL"})
    main = Chan()
    held = asyncio.run(_send_alerts(main, [("E-legacy", None, None)], apply_cooldown=True))
    assert held == [] and fake.checked == [] and fake.recorded == []
    assert [s["embed"] for s in main.sent] == ["E-legacy"]


def test_a_failed_send_records_no_post(env, fake_cd):
    fake = fake_cd()
    main = Chan(fail_on={1})
    asyncio.run(_send_alerts(main, [_alert("MSFT"), _alert("NVDA")], apply_cooldown=True))
    assert _titles(main) == ["NVDA"]
    assert fake.recorded == [("NVDA", "posted")]


def test_a_broken_cooldown_store_still_posts_every_alert(env, monkeypatch, caplog):
    class Broken:
        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise RuntimeError("database is having a day")
            return _raise

    monkeypatch.setattr(cooldown, "alert_posts_repo", lambda: Broken())
    main = Chan()
    with caplog.at_level(logging.WARNING):
        held = asyncio.run(_send_alerts(main, [_alert("AAPL"), _alert("MSFT")],
                                        apply_cooldown=True))
    assert held == []
    assert _titles(main) == ["AAPL", "MSFT"]
    assert any("posting the alert anyway" in r.getMessage() for r in caplog.records)


def test_a_held_alert_writes_neither_its_plan_nor_its_trade(env, fake_cd, monkeypatch):
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.performance import TradeLog
    from tests.planning.test_plan_engine_model import _plan as stored_plan

    plan = stored_plan(plan_id=PIDS["AAPL"])
    PlanStore().add(plan)

    def _no_write(*args, **kwargs):
        raise AssertionError("the cooldown must not write the book")

    monkeypatch.setattr(PlanStore, "update", _no_write)
    monkeypatch.setattr(TradeLog, "_db_upsert", staticmethod(_no_write))
    fake_cd({"AAPL"})
    held = asyncio.run(_send_alerts(Chan(), [_alert("AAPL", plan)], apply_cooldown=True))
    assert held == [plan]
    assert PlanStore().get(PIDS["AAPL"]).status == "PENDING"


def _short_lane(monkeypatch, held_by_batch):
    calls = []

    async def fake_send(dest, batch, route_by_confidence=False, *, apply_cooldown=False):
        calls.append((list(batch), apply_cooldown))
        return list(held_by_batch.get(batch[0], []))

    async def fake_short(**kw):
        return ["SHORT"]

    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_BROAD_ENABLED", True)
    monkeypatch.setattr(alerts, "_send_alerts", fake_send)
    monkeypatch.setattr(alerts.scan_engine, "run_short_universe_scan", fake_short)
    return calls


def test_send_then_short_forwards_the_flag_and_returns_every_held_plan(monkeypatch):
    calls = _short_lane(monkeypatch, {"BASE": ["held-base"], "SHORT": ["held-short"]})
    held = asyncio.run(send_then_short("chan", ["BASE"], apply_cooldown=True))
    assert held == ["held-base", "held-short"]
    assert calls == [(["BASE"], True), (["SHORT"], True)]


def test_send_then_short_defaults_to_no_cooldown(monkeypatch):
    calls = _short_lane(monkeypatch, {})
    assert asyncio.run(send_then_short("chan", ["BASE"])) == []
    assert calls == [(["BASE"], False), (["SHORT"], False)]


@pytest.fixture
def digest_env(monkeypatch):
    from swingbot.commands import stats, views
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import embeds

    class View:
        def __init__(self, plan_id, author_id=None):
            self.message = None

    monkeypatch.setattr(plan_store, "PlanStore", lambda: types.SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(stats, "_fake_item_from_plan", lambda plan: plan)
    monkeypatch.setattr(embeds, "build_embed",
                        lambda item, *a, **k: discord.Embed(title=item.plan_id))
    monkeypatch.setattr(views, "PlanActionView", View)


HELD_LINE = " · 2 alert(s) held by the symbol cooldown today"


def test_the_digest_header_states_todays_held_count(digest_env, monkeypatch):
    plans = [types.SimpleNamespace(plan_id=PIDS["AAPL"], ticker="AAPL")]
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: plans)
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 2)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent[0]["content"] == kinds.content_line(
        Kind.DIGEST, "", detail="1 VALIDATED plan(s), ranked by follow score") + HELD_LINE


def test_the_empty_digest_states_todays_held_count(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 2)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [{"content": kinds.content_line(
        Kind.DIGEST, "", detail="no VALIDATED plans qualified today") + HELD_LINE}]


def test_no_held_alerts_leave_the_digest_line_unchanged(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    monkeypatch.setattr(cooldown, "held_today", lambda now=None: 0)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [{"content": kinds.content_line(
        Kind.DIGEST, "", detail="no VALIDATED plans qualified today")}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_cooldown.py`
Expected: FAIL — `TypeError: _send_alerts() got an unexpected keyword argument 'apply_cooldown'` (and the digest tests on the missing suffix).

- [ ] **Step 3: Import the cooldown module and `asyncio` in `alerts.py`**

At the top of `swingbot/commands/scanning/alerts.py`, change the import block head from

```python
import logging
import os

import discord
```

to

```python
import asyncio
import logging
import os

import discord
```

and directly after `from swingbot.core.market.session import market_today` add

```python
from . import cooldown
```

(`cooldown.py` imports only `config`, the `alert_posts` repository and `session` — no cycle with this package.)

- [ ] **Step 4: Add the digest held line**

In `_post_daily_digest`, replace

```python
    plans = PlanStore().all()
    top = digest_payload(plans, market_today(), config.DIGEST_MAX_PLANS)
    if not top:
        await channel.send(content=kinds.content_line(
            Kind.DIGEST, "", detail="no VALIDATED plans qualified today"))
        return

    # v110 §4: one registry content line for the whole batch, on its first
    # embed -- it replaces the separate "📌 Top plans today" header message.
    header = kinds.content_line(
        Kind.DIGEST, "", detail=f"{len(top)} VALIDATED plan(s), ranked by follow score")
```

with

```python
    plans = PlanStore().all()
    top = digest_payload(plans, market_today(), config.DIGEST_MAX_PLANS)
    held_line = _held_line(await asyncio.to_thread(cooldown.held_today))
    if not top:
        await channel.send(content=kinds.content_line(
            Kind.DIGEST, "", detail="no VALIDATED plans qualified today") + held_line)
        return

    # v110 §4: one registry content line for the whole batch, on its first
    # embed -- it replaces the separate "📌 Top plans today" header message.
    header = kinds.content_line(
        Kind.DIGEST, "", detail=f"{len(top)} VALIDATED plan(s), ranked by follow score") + held_line
```

and add this helper directly above `async def _post_daily_digest`:

```python
def _held_line(held: int) -> str:
    """v152 D3: the digest's held-alert suffix; empty when nothing was held."""
    return f" · {held} alert(s) held by the symbol cooldown today" if held > 0 else ""
```

- [ ] **Step 5: Record a post after Discord accepted it**

Replace `_post_alert` with:

```python
async def _post_alert(send_to, embed, chart_path, plan, mirrored: bool, view_cls,
                      *, record_post: bool = False) -> None:
    """Send one full alert: content line, chart, plan buttons. silent=True
    only once the mirror landed (the alerts channel forces it regardless).
    record_post (v152 D3, scheduled path only): write the 'posted' cooldown
    row once Discord accepted the send -- a failed send records nothing."""
    view = view_cls(plan.plan_id, author_id=None) if plan is not None else None
    kwargs = {**ui.push_kwargs(embed), "silent": mirrored}
    if chart_path:
        kwargs["file"] = discord.File(chart_path, filename=os.path.basename(chart_path))
    if view is not None:
        kwargs["view"] = view
    msg = await send_to.send(**kwargs)
    log_posted(embed, getattr(plan, "ticker", None), send_to)
    if view is not None:
        view.message = msg
    if record_post and plan is not None:
        await asyncio.to_thread(cooldown.record, plan, "posted")
```

- [ ] **Step 6: Filter before the cap in `_send_alerts`**

Add directly above `async def _send_alerts`:

```python
async def _hold_by_cooldown(alerts: list) -> tuple[list, list]:
    """v152 D3: split a scheduled batch into (kept alerts, held plans).

    Runs before ranking and the cap, so a held alert sends neither its full
    alert nor its simple mirror and the overflow footer names only what
    survived. A legacy (plan-less) alert always passes. A held plan is
    recorded 'suppressed'. Both cooldown calls fail open and never raise."""
    kept, held = [], []
    for alert in alerts:
        plan = alert[2]
        if plan is not None and await asyncio.to_thread(cooldown.suppressed, plan):
            held.append(plan)
            await asyncio.to_thread(cooldown.record, plan, "suppressed")
            continue
        kept.append(alert)
    return kept, held
```

Change the signature line

```python
async def _send_alerts(destination, alerts, route_by_confidence: bool = False):
```

to

```python
async def _send_alerts(destination, alerts, route_by_confidence: bool = False, *,
                       apply_cooldown: bool = False) -> list:
```

and append this paragraph at the end of its docstring (before the closing `"""`):

```python
    `apply_cooldown` (v152 D3) is passed True by the scheduled session scan
    only: an alert whose (ticker, direction, horizon_key) was posted within
    ALERT_SYMBOL_COOLDOWN_HOURS is held -- before the cap -- and every post
    that lands is recorded. Returns the held plans ([] when the flag is off).
    The plan and its trade are already in the book; only the post is held.
```

Replace

```python
    ordered = _ordered_alerts(alerts)
```

with

```python
    held: list = []
    if apply_cooldown:
        alerts, held = await _hold_by_cooldown(alerts)
    ordered = _ordered_alerts(alerts)
```

replace

```python
            await _post_alert(send_to, embed, chart_path, plan, mirrored, PlanActionView)
```

with

```python
            await _post_alert(send_to, embed, chart_path, plan, mirrored, PlanActionView,
                              record_post=apply_cooldown)
```

and append, after the `for alert in to_send:` loop (dedented to the function body):

```python
    return held
```

- [ ] **Step 7: Thread the flag through the short lane**

Replace `post_short_universe` and `send_then_short` with:

```python
async def post_short_universe(destination, *, bot=None, require_confirmation: bool = True,
                              route_by_confidence: bool = False, apply_cooldown: bool = False,
                              held: list | None = None) -> list:
    """V118-4: the SHORT extra-universe pass and its alerts.

    Only ever called AFTER the base alerts were sent, so a cold extra fetch
    cannot hold back a ready watchlist alert. Off (default): returns [] with
    no fetch. A recap/display-only caller never calls this and stays base-only.
    v152 D3: `apply_cooldown` is forwarded to _send_alerts; the plans it held
    are appended to `held` when one is given. Returns the short alerts.
    """
    if not admitted_short_modes(config):
        return []
    short_alerts = await scan_engine.run_short_universe_scan(
        require_confirmation=require_confirmation, bot=bot,
        progress=scan_engine.ScanProgress())
    short_held = await _send_alerts(destination, short_alerts,
                                    route_by_confidence=route_by_confidence,
                                    apply_cooldown=apply_cooldown)
    if held is not None:
        held.extend(short_held)
    return short_alerts


async def send_then_short(destination, base_alerts, *, bot=None, require_confirmation: bool = True,
                          route_by_confidence: bool = False, apply_cooldown: bool = False) -> list:
    """Send the base alerts, THEN run the extra lane (the scheduled-path invariant).
    Returns every plan the v152 cooldown held across both ([] without it)."""
    held = list(await _send_alerts(destination, base_alerts,
                                   route_by_confidence=route_by_confidence,
                                   apply_cooldown=apply_cooldown))
    await post_short_universe(destination, bot=bot, require_confirmation=require_confirmation,
                              route_by_confidence=route_by_confidence,
                              apply_cooldown=apply_cooldown, held=held)
    return held
```

- [ ] **Step 8: Keep the short-lane ordering fake in step with the new contract**

`tests/scanning/test_short_lane_scan.py::_record_order` fakes `_send_alerts` without the new keyword and returns `None`, which `send_then_short` now forwards and extends. In that helper replace

```python
    async def fake_send(dest, alerts, route_by_confidence=False):
        events.append(("send", list(alerts)))
```

with

```python
    async def fake_send(dest, alerts, route_by_confidence=False, *, apply_cooldown=False):
        events.append(("send", list(alerts)))
        return []
```

Nothing else in that file changes; its assertions are about ordering only.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_cooldown.py`
Expected: PASS.

Run each of these (the existing `_send_alerts` / digest / short-lane / halt callers):
- `python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py`
- `python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`
- `python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py`
- `python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`
- `python scripts/dev/testrun.py file tests/commands/test_store_write_halt.py`
- `python scripts/dev/testrun.py file tests/commands/test_outlook_loops.py`

Expected: PASS each (the existing digest tests now also read `held_today()` from the empty test table and get 0, so their lines are unchanged).

- [ ] **Step 10: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/alerts.py`
Expected: no output (`_send_alerts` is 10, `_post_alert` 6, `_hold_by_cooldown` 4).

- [ ] **Step 11: Commit**

```bash
git add swingbot/commands/scanning/alerts.py tests/commands/test_send_alerts_cooldown.py tests/scanning/test_short_lane_scan.py
git commit -m "feat(v152): hold repeat alerts on the scheduled path before the cap; digest held line"
```

# Phase 5: Near-stop event and notify policy

### Task V152-13: Near-stop `PlanEvent` + `FOLLOW_ONLY_EVENTS`

**Model:** opus — adds an event to the live plan state machine's `poll` (legacy complexity 20, must gain no branch) and the price-vs-stop geometry for long, short, breakeven and runner stops; a wrong sign or a branch in `poll` is a live-book integrity bug.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (constants beside `STOP_EVENTS` :68-70; one statement at the end of `poll`'s per-plan loop :568; `_near_stop_event` method after `poll`)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`notify_plan_events` :456 import, :465 loop head)
- Create: `tests/planning/test_near_stop_event.py`

**Produces (ledger):** `FOLLOW_ONLY_EVENTS = frozenset({"near_stop"})`; `NEAR_STOP_R = 0.25`; `PlanManager._near_stop_event(self, plan, price: float | None, now) -> list[PlanEvent]` — 0 or 1 `PlanEvent(plan_id, "near_stop", {"stop": float, "price": float, "r_dist": float})`. V152-14 maps the transition, V152-16 renders `stop` and `r_dist`, V152-17 dedupes it.

**Design (spec § D1 Near-stop detection).**
- Fires when the plan is ACTIVE or PARTIAL, the regular session is open, the price is **not beyond** the resting stop (long: `price >= stop`; short: `price <= stop`), and `abs(price - resting_stop(plan)) <= NEAR_STOP_R * abs(entry_price - stop_loss)` — initial R, so a breakeven or trailing stop is measured in the plan's original risk. `r_dist` is that distance in initial R.
- The stop is `resting_stop(plan)` (:135), which already returns the runner floor for a PARTIAL plan without a working stop, so breakeven and trail moves are covered.
- `poll` gains exactly one statement after `_feed_bookkeeping`: `events.extend(self._near_stop_event(plan, price, now))`. `plan` there is the store copy `_step` mutated in place, so a plan the same tick closed is CLOSED and emits nothing (a gap beyond the stop fires `closed` only). The event is never passed to `log_plan_event`, `_on_event` or `_feed_bookkeeping`, and it writes nothing.
- The helper emits on **every** in-band tick; once-per-plan is the notifier's `plan_notifications` claim plus its `_CLAIMED` cache (index decision 11, V152-17).
- The session test is a module function `_arms_near_stop(now)` around `is_regular_session(now)` (spec: regular session only, pre- and after-hours never fire, even with `INTRADAY_RTH_ONLY=false`). It is a separate name so Step 5 can force it on and find tests whose exact event lists would now depend on the wall clock.
- `notify_plan_events` skips `FOLLOW_ONLY_EVENTS` at the top of its loop, before the store read: one membership test, 12 → 13 (index decision 10). Without it `near_stop` would fall into the history branch for unknown transitions (`lifecycle_embeds.py:470-475`).

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_near_stop_event.py`:

```python
"""v152 D1: the R-based near-stop PlanEvent.

ACTIVE/PARTIAL only, regular session only, never beyond the resting stop,
within 0.25 initial R of it. poll() gains one statement for it; the
execution feed (notify_plan_events) never posts it -- it is follow-only.
"""
import asyncio
import datetime as dt
import types

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import (FOLLOW_ONLY_EVENTS, NEAR_STOP_R, NOTICE_EVENTS,
                                                 STOP_EVENTS, PlanEvent, PlanManager, resting_stop)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.time_exit import TIME_EVENTS
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending

RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)      # Thursday, regular session
PRE = dt.datetime(2026, 8, 27, 8, 0, tzinfo=US_MARKET_TZ)       # pre-market (14:00 Berlin)
AFTER = dt.datetime(2026, 8, 27, 16, 30, tzinfo=US_MARKET_TZ)   # after-hours (22:30 Berlin)


@pytest.fixture(autouse=True)
def _pinned_flags(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "EXTENDED_HOURS_EXIT_CHECK", True)
    monkeypatch.setattr(config, "TRAIL_NOTIFY_MIN_R", 0.25)
    monkeypatch.setattr(config, "PYRAMIDING_ENABLED", False)


def _manager():
    return PlanManager(PlanStore(), lambda ticker: 0.0)


def _env(prices, plan=None):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore()
    store.add(plan if plan is not None else _active())
    return store, PlanManager(store, feed.get_price)


def _short():
    plan = _plan(entry_type="market", direction="bearish", trigger_price=100.0,
                 entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=None)
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return plan


def test_the_band_is_a_quarter_of_initial_risk():
    assert NEAR_STOP_R == 0.25


def test_an_active_long_within_the_band_emits_stop_price_and_r_distance():
    events = _manager()._near_stop_event(_active(), 96.0, RTH)
    assert len(events) == 1
    event = events[0]
    assert (event.plan_id, event.transition) == ("p1", "near_stop")
    assert event.detail == {"stop": 95.0, "price": 96.0, "r_dist": pytest.approx(0.2)}


@pytest.mark.parametrize("price, fires", [(96.25, True), (96.3, False), (95.0, True),
                                          (94.99, False)])
def test_the_band_edges_and_the_stop_itself(price, fires):
    assert bool(_manager()._near_stop_event(_active(), price, RTH)) is fires


def test_a_short_is_measured_above_its_stop():
    manager = _manager()
    [event] = manager._near_stop_event(_short(), 104.0, RTH)
    assert event.detail == {"stop": 105.0, "price": 104.0, "r_dist": pytest.approx(0.2)}
    assert manager._near_stop_event(_short(), 105.5, RTH) == []      # beyond the stop
    assert manager._near_stop_event(_short(), 103.0, RTH) == []      # 0.4R away


def test_a_breakeven_stop_is_measured_in_initial_r():
    plan = _active(working_stop=100.0)
    [event] = _manager()._near_stop_event(plan, 101.0, RTH)
    assert event.detail["stop"] == resting_stop(plan) == 100.0
    assert event.detail["r_dist"] == pytest.approx(0.2)


@pytest.mark.parametrize("working_stop", [None, 108.0])
def test_a_partial_runner_uses_its_resting_stop(working_stop):
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 tp2=None, working_stop=working_stop)
    stop = resting_stop(plan)
    [event] = _manager()._near_stop_event(plan, stop + 0.5, RTH)
    assert event.detail["stop"] == pytest.approx(stop)
    assert event.detail["r_dist"] == pytest.approx(0.1)


@pytest.mark.parametrize("plan", [
    _pending(),
    _plan(status="CLOSED", entry_price=100.0),
    _plan(status="CANCELLED"),
])
def test_only_active_and_partial_plans_can_be_near_their_stop(plan):
    assert _manager()._near_stop_event(plan, 95.5, RTH) == []


@pytest.mark.parametrize("now", [PRE, AFTER])
def test_extended_hours_never_arm_it(now):
    assert _manager()._near_stop_event(_active(), 96.0, now) == []


def test_extended_hours_stay_unarmed_without_the_rth_gate(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    assert _manager()._near_stop_event(_active(), 96.0, PRE) == []


@pytest.mark.parametrize("price", [None, 0.0])
def test_no_price_no_event(price):
    assert _manager()._near_stop_event(_active(), price, RTH) == []


def test_zero_initial_risk_never_divides():
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=100.0)
    assert _manager()._near_stop_event(plan, 100.0, RTH) == []


def test_poll_emits_it_on_every_in_band_tick_and_writes_nothing():
    store, manager = _env([96.0, 96.0])
    before = store.get("p1")
    assert [e.transition for e in manager.poll(now=RTH)] == ["near_stop"]
    assert [e.transition for e in manager.poll(now=RTH)] == ["near_stop"]   # the notifier dedupes
    after = store.get("p1")
    assert (after.status, after.working_stop, after.notified_stop) == (
        before.status, before.working_stop, before.notified_stop)


def test_a_gap_beyond_the_stop_fires_closed_only():
    _store, manager = _env([94.5])
    assert [e.transition for e in manager.poll(now=RTH)] == ["closed"]


def test_poll_in_pre_market_emits_nothing():
    _store, manager = _env([96.0])
    assert manager.poll(now=PRE) == []


def test_near_stop_is_follow_only():
    assert FOLLOW_ONLY_EVENTS == frozenset({"near_stop"})
    assert not FOLLOW_ONLY_EVENTS & (STOP_EVENTS | NOTICE_EVENTS | TIME_EVENTS)


def test_the_execution_feed_never_posts_a_near_stop(monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning.embeds import notify_plan_events

    sent, reads = [], []

    class Chan:
        async def send(self, **kwargs):
            sent.append(kwargs)

    class Store:
        def get(self, plan_id):
            reads.append(plan_id)
            return _active()

    monkeypatch.setattr(plan_store, "PlanStore", Store)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2", raising=False)
    bot = types.SimpleNamespace(get_channel=lambda _id: Chan())
    event = PlanEvent("p1", "near_stop", {"stop": 95.0, "price": 96.0, "r_dist": 0.2})
    assert asyncio.run(notify_plan_events(bot, [event])) == []
    assert sent == [] and reads == []


def test_the_session_gate_is_the_regular_session(monkeypatch):
    seen = []
    monkeypatch.setattr(plan_manager, "is_regular_session", lambda now=None: seen.append(now) or True)
    assert plan_manager._arms_near_stop(PRE) is True
    assert seen == [PRE]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py`
Expected: FAIL — `ImportError: cannot import name 'FOLLOW_ONLY_EVENTS' from 'swingbot.core.planning.plan_manager'`.

- [ ] **Step 3: Add the constants, the session gate and the helper**

In `swingbot/core/planning/plan_manager.py`, directly after the `NOTICE_EVENTS = frozenset({...})` statement (:69-70), insert:

```python
# v152 D1: events only the notify channel (commands/scanning/follow_notify.py)
# posts. The execution feed skips them (lifecycle_embeds.notify_plan_events).
FOLLOW_ONLY_EVENTS = frozenset({"near_stop"})
# near_stop arms within this many INITIAL R of the resting stop.
NEAR_STOP_R = 0.25
_NEAR_STOP_STATUSES = frozenset({PlanStatus.ACTIVE, PlanStatus.PARTIAL})
```

Directly after `def resting_stop(plan)` (:135-139), insert the two module helpers:

```python
def _arms_near_stop(now) -> bool:
    """v152 D1: near_stop arms in the regular NYSE session only -- a pre- or
    after-hours print never fires it, whatever INTRADAY_RTH_ONLY says."""
    return is_regular_session(now)


def _initial_risk(plan) -> float:
    """abs(entry - initial stop); 0.0 when the plan has no entry yet."""
    if plan.entry_price is None:
        return 0.0
    return abs(float(plan.entry_price) - float(plan.stop_loss))
```

In `class PlanManager`, directly after the end of `def poll` (its `return events`, :569) and before `def _warn_legacy_open_risk`, insert:

```python
    def _near_stop_event(self, plan: TradePlanV2, price, now) -> list[PlanEvent]:
        """v152 D1: one near_stop event when an ACTIVE/PARTIAL plan's price is
        within NEAR_STOP_R initial R of its resting stop, not beyond it, in
        the regular session; else []. Emits on every in-band tick -- the
        notifier's plan_notifications claim makes it once per plan. Pure: it
        reads the plan poll() just stepped and writes nothing."""
        if plan.status not in _NEAR_STOP_STATUSES or not price or not _arms_near_stop(now):
            return []
        risk = _initial_risk(plan)
        if risk <= 0:
            return []
        stop, price = float(resting_stop(plan)), float(price)
        beyond = price < stop if plan.direction == "bullish" else price > stop
        distance = abs(price - stop)
        if beyond or distance > NEAR_STOP_R * risk:
            return []
        return [PlanEvent(plan.plan_id, "near_stop",
                          {"stop": stop, "price": price, "r_dist": distance / risk})]
```

- [ ] **Step 4: Wire it into `poll` (one statement, no branch)**

At the end of `poll`'s `for plan in open_plans:` loop, replace

```python
            for event in new_events:
                log_plan_event(plan, event)
                self._on_event(plan, event)
            events.extend(self._feed_bookkeeping(plan, new_events, regular, now))
        return events
```

with

```python
            for event in new_events:
                log_plan_event(plan, event)
                self._on_event(plan, event)
            events.extend(self._feed_bookkeeping(plan, new_events, regular, now))
            events.extend(self._near_stop_event(plan, price, now))
        return events
```

- [ ] **Step 5: Skip it on the execution feed**

In `swingbot/core/scanning/lifecycle_embeds.py::notify_plan_events`, change the import

```python
    from swingbot.core.planning.plan_manager import NOTICE_EVENTS, STOP_EVENTS
```

to

```python
    from swingbot.core.planning.plan_manager import FOLLOW_ONLY_EVENTS, NOTICE_EVENTS, STOP_EVENTS
```

and replace the loop head

```python
    for event in events:
        try:
            plan = store.get(event.plan_id)
```

with

```python
    for event in events:
        if event.transition in FOLLOW_ONLY_EVENTS:
            continue    # v152: the notify channel's alone (commands/scanning/follow_notify.py)
        try:
            plan = store.get(event.plan_id)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py`
Expected: PASS.

- [ ] **Step 7: Find exact-event-list tests that now depend on the wall clock**

Many manager tests call `poll()` without `now`, so the session is the real clock. Run the planning and monitor tests with the gate forced open, so a test that would see `near_stop` only during US market hours fails now, not on some afternoon CI run:

```bash
python - <<'FORCE_RTH_EOF'
import sys

import pytest


class ForceNearStopArmed:
    def pytest_configure(self, config):
        from swingbot.core.planning import plan_manager
        plan_manager._arms_near_stop = lambda now: True


sys.exit(pytest.main(["tests/planning", "tests/commands/test_trade_monitor_task.py",
                      "tests/scanning/test_execution_feed_routing.py", "-q", "-p", "no:cacheprovider"],
                     plugins=[ForceNearStopArmed()]))
FORCE_RTH_EOF
```

Expected: `0 failed`. For each failure: it asserts an exact transition list at a price within 0.25R of the resting stop. If that test pins `now` inside the regular session, the new event is correct there — add `"near_stop"` to its expected list. If its `now` is unpinned, add `monkeypatch.setattr(plan_manager, "_arms_near_stop", lambda now: False)` with the comment `# pins the lifecycle; v152 near_stop is tested in test_near_stop_event.py`. Never change an assertion about any other transition. Stage every test file edited here by name in Step 9 and list them in the commit body.

Then: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py`, `python scripts/dev/testrun.py file tests/commands/test_trade_monitor_task.py` and `python scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py` — PASS each, without the plugin.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py swingbot/core/scanning/lifecycle_embeds.py`
Expected: `poll` still reported at **20** (unchanged — the added line is a call, not a branch), `_step_active` at 21 (not edited), `notify_plan_events` at 13; `_near_stop_event`, `_arms_near_stop` and `_initial_risk` absent (below C). Baseline for `poll`: `git show HEAD:swingbot/core/planning/plan_manager.py > "${TMPDIR:-/tmp}/pm_head.py"` then `python -m radon cc -s -n C "${TMPDIR:-/tmp}/pm_head.py"` must print the same figure for `poll`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/core/scanning/lifecycle_embeds.py tests/planning/test_near_stop_event.py
git commit -m "feat(v152): R-based near_stop PlanEvent, follow-only (execution feed skips it)"
```
