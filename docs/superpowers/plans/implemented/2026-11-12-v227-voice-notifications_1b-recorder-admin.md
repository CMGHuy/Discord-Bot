# v227 — Voice notifications, Part 1b: recorder, call sites and admin endpoints (V227-4..V227-6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post](../specs/2026-11-12-v227-voice-notifications-design.md) (§ 1 Recording a post: kill switch, recorder, call sites, ordering, retention; § 2 Serving it; § Testing backend)

Part 1 of the index's Parts table, continued: V227-1..V227-3 are in
[`2026-11-12-v227-voice-notifications_1-backend.md`](2026-11-12-v227-voice-notifications_1-backend.md)
(split for the 1500-line cap, never compressed). Goal, architecture, **Global
Constraints**, **Parallelisation** and the task ledger live in the index:
[`2026-11-12-v227-voice-notifications_0-index.md`](2026-11-12-v227-voice-notifications_0-index.md).
Every task below implicitly carries those constraints. Work happens in the
worktree `.claude/worktrees/2026-11-12-v227-voice-notifications` (all paths
below are relative to it). Tests that reach Postgres need `/replicate-prod-db`
run once per session first (shared `swing-db`, port 56789).

Two files join V227-4 beyond its ledger row, both touched by no other task:
`tests/conftest.py` (pin the new kill switch off for every test so no test
writes into the `.env` database through the side engine) and `.env.example`
(must list every config key, `tests/infra/test_env_example_sync.py`).

# Phase 3 — Recording at send time

### Task V227-4: `record_feed_post` glue, `FEED_POSTS_ENABLED`, hourly prune

**Model:** opus — code that runs inside the bot's event loop on every simple-channel post: it must never raise, never stall past the side engine's timeout, keep the `core/infra` → `presentation` import seam lazy, and pin a kill switch off for the whole test suite (concurrency + import-cycle + test-isolation judgement).

**Files:**
- Create: `swingbot/core/infra/feed_posts.py`
- Create: `tests/infra/test_feed_posts_recorder.py`
- Create: `tests/test_config_v227_keys.py`
- Modify: `swingbot/config.py` (new `Field` right after `ALERT_SYMBOL_COOLDOWN_HOURS`, ~line 1101)
- Modify: `.env.example` (after `ALERT_SYMBOL_COOLDOWN_HOURS=24`, ~line 588)
- Modify: `tests/conftest.py` (`_pin_dotenv_settings`, ~line 131)

**Interfaces:**
- Consumes: `feed_posts_repo()`, `FeedPostsRepository.insert(kind, ticker, headline, *, conn) -> int`, `.prune(days, *, conn) -> int` (V227-2); `feed_headline(kind, embed, ticker) -> str` (V227-3); `swingbot.core.db.side_engine.side_connection()` (side_engine.py:147, autocommit, statement timeout `MARKETDATA_PG_TIMEOUT_MS`, raises `DatabaseUnavailable` while backing off); `swallowed(log, tag, exc, msg="", *args, level=..., exc_info=False)` (swallowed.py:62).
- Produces (final, consumed by V227-5): `record_feed_post(embed, ticker: str | None, kind=None) -> None`; `RETENTION_DAYS = 7`; `PRUNE_EVERY_S = 3600`; `reset_prune_clock() -> None`; `config.FEED_POSTS_ENABLED: bool`.

Order inside `record_feed_post` (index Global Constraints): kill switch first, before any work; resolve `kind = kind or getattr(embed, "kind", None)` exactly as `log_posted` does; no kind → nothing recorded; lazy imports; headline; one insert through `side_connection()`; then the prune check in its own `try` and its own connection. Every failure goes through `swallowed(..., level=logging.DEBUG)` with tag `"feed_posts.record"` or `"feed_posts.prune"`. Synchronous on purpose: a thread or task would break the single-writer ordering that makes `after=<id>` paging gap-free (spec § 1 Ordering invariant); the side engine's statement timeout bounds the stall.

Why `tests/conftest.py` changes: `side_connection()` reads `config.DATABASE_URL` from `.env`, which on a dev machine is the local replica. Without a pin, every existing test that drives `_mirror` or `_send_instruction` (e.g. `tests/infra/test_posted_log.py`) would write rows into that database once V227-5 lands. The pin follows the `MARKETDATA_LAYER="off"` precedent in the same function; tests that want recording set `FEED_POSTS_ENABLED` themselves.

- [ ] **Step 1: Write the failing config test**

Create `tests/test_config_v227_keys.py`:

```python
"""v227: FEED_POSTS_ENABLED -- the voice-notification recorder's kill switch."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_kill_switch_is_a_hot_reloadable_discord_alerts_checkbox_on_by_default():
    field = _field("FEED_POSTS_ENABLED")
    assert (field.key, field.section, field.type, field.default) == (
        "FEED_POSTS_ENABLED", "Discord Alerts", "checkbox", "true")
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v227" in field.help
    assert config._cast(field, "true") is True and config._cast(field, "false") is False


def test_it_sits_right_after_the_alert_cooldown():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs[attrs.index("ALERT_SYMBOL_COOLDOWN_HOURS") + 1] == "FEED_POSTS_ENABLED"


def test_env_example_lists_it_on():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nFEED_POSTS_ENABLED=true\n" in text


def test_the_test_suite_runs_with_recording_off():
    # tests/conftest.py pins it off so no test writes into the .env database
    # through the side engine; recorder tests switch it on themselves.
    assert config.FEED_POSTS_ENABLED is False
```

- [ ] **Step 2: Write the failing recorder test**

Create `tests/infra/test_feed_posts_recorder.py`:

```python
"""v227: record_feed_post -- one row per accepted simple-channel post, never raising,
only through the fail-fast side engine, pruned at most once an hour."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import schema, side_engine
from swingbot.core.db.engine import DatabaseUnavailable
from swingbot.core.db.repositories import feed_posts as repo_module
from swingbot.core.infra import feed_posts as recorder
from swingbot.core.presentation import components
from swingbot.core.presentation.kinds import Kind

CONN = object()


class _Repo:
    def __init__(self):
        self.inserts, self.prunes = [], []

    def insert(self, kind, ticker, headline, *, conn):
        self.inserts.append((kind, ticker, headline, conn))
        return len(self.inserts)

    def prune(self, days, *, conn):
        self.prunes.append((days, conn))
        return 0


@pytest.fixture
def env(monkeypatch):
    """Recording on, a fake side connection and a recording repository."""
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", True)
    state = SimpleNamespace(repo=_Repo(), connections=0, raise_on_connect=None, now=1000.0)

    @contextmanager
    def fake_side_connection():
        state.connections += 1
        if state.raise_on_connect is not None:
            raise state.raise_on_connect
        yield CONN

    monkeypatch.setattr(side_engine, "side_connection", fake_side_connection)
    monkeypatch.setattr(repo_module, "feed_posts_repo", lambda: state.repo)
    monkeypatch.setattr(recorder, "_clock", lambda: state.now)
    recorder.reset_prune_clock()
    yield state
    recorder.reset_prune_clock()


def test_an_accepted_post_inserts_one_row_through_the_side_connection(env):
    embed = components.push_embed(Kind.FILLED, "MSFT", "bullish")
    recorder.record_feed_post(embed, "MSFT")
    assert env.repo.inserts == [("FILLED", "MSFT", "Order filled, MSFT", CONN)]


def test_an_explicit_kind_wins_over_the_embeds(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "MSFT", kind=Kind.CANCEL)
    assert env.repo.inserts[0][:2] == ("CANCEL", "MSFT")


def test_an_embed_without_a_kind_records_nothing(env):
    recorder.record_feed_post(SimpleNamespace(), "MSFT")
    recorder.record_feed_post(components.status_embed("t", "d", 0), "MSFT")
    assert env.repo.inserts == [] and env.connections == 0


def test_a_blank_ticker_is_stored_as_null(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.RISK_CAP), "")
    assert env.repo.inserts == [("RISK_CAP", None, "Cancelled by risk cap", CONN)]


def test_switched_off_it_touches_no_connection_and_no_embed(env, monkeypatch):
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", False)

    class Exploding:
        @property
        def kind(self):
            raise AssertionError("read the embed with the switch off")

    recorder.record_feed_post(Exploding(), "MSFT")
    assert env.connections == 0 and env.repo.inserts == []


@pytest.mark.parametrize("exc", [DatabaseUnavailable("down"),
                                 sa.exc.OperationalError("SELECT 1", {}, Exception("timeout")),
                                 RuntimeError("boom")])
def test_a_failing_connection_is_swallowed(env, exc):
    env.raise_on_connect = exc
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "MSFT")   # must not raise
    assert env.repo.inserts == [] and env.repo.prunes == []


def test_a_broken_embed_is_swallowed(env):
    class Broken:
        @property
        def kind(self):
            raise RuntimeError("boom")

    recorder.record_feed_post(Broken(), "MSFT")
    assert env.repo.inserts == []


def test_the_first_post_prunes_then_not_again_within_the_hour(env):
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "A")
    env.now += recorder.PRUNE_EVERY_S - 1
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "B")
    assert env.repo.prunes == [(recorder.RETENTION_DAYS, CONN)]
    env.now += 1
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "C")
    assert len(env.repo.prunes) == 2


def test_a_failing_prune_is_swallowed_and_not_retried_every_post(env):
    def boom(days, *, conn):
        env.repo.prunes.append((days, conn))
        raise RuntimeError("prune failed")

    env.repo.prune = boom
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "A")
    recorder.record_feed_post(SimpleNamespace(kind=Kind.FILLED), "B")
    assert len(env.repo.inserts) == 2 and len(env.repo.prunes) == 1


def test_constants():
    assert (recorder.RETENTION_DAYS, recorder.PRUNE_EVERY_S) == (7, 3600)


def test_the_module_imports_no_presentation_or_repository_at_load():
    source = recorder.__file__
    text = open(source, encoding="utf-8").read()
    top = text.split("def record_feed_post", 1)[0]
    assert "swingbot.core.presentation" not in top
    assert "repositories.feed_posts" not in top


@pytest.fixture
def side_db(db_committed, db_engine, monkeypatch):
    """The real side engine pointed at this worker's test database (tests/db/test_side_engine.py)."""
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_PG_TIMEOUT_MS", 250)
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", True)
    side_engine.reset()
    recorder.reset_prune_clock()
    yield db_committed
    side_engine.reset()
    recorder.reset_prune_clock()


def test_a_real_row_lands_through_the_side_engine(side_db):
    embed = components.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv3")
    embed.entry_price = 187.5
    recorder.record_feed_post(embed, "AAPL")
    rows = side_db.execute(sa.select(schema.feed_posts.c.kind, schema.feed_posts.c.ticker,
                                     schema.feed_posts.c.headline)).all()
    assert [tuple(r) for r in rows] == [("SETUP_SIMPLE", "AAPL", "New long alert, AAPL, buy at 187.50")]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_v227_keys.py`
Expected: FAIL — `StopIteration` (no `FEED_POSTS_ENABLED` field).

Run: `python scripts/dev/testrun.py file tests/infra/test_feed_posts_recorder.py`
Expected: FAIL — `ImportError: cannot import name 'feed_posts' from 'swingbot.core.infra'`.

- [ ] **Step 4: Add the config key, its example line and the suite-wide pin**

`swingbot/config.py`, right after the `ALERT_SYMBOL_COOLDOWN_HOURS` `Field(...)`:

```python
    Field("FEED_POSTS_ENABLED", "FEED_POSTS_ENABLED", "Discord Alerts",
          "Record simple-channel posts for voice notifications (v227)",
          type="checkbox", default="true",
          help="v227. On (default): every post the simple trades channel accepts is also written "
               "to the feed_posts table, and an open bomeo-capital.com tab speaks its headline. "
               "Off: nothing is recorded and the site stays silent; Discord is unaffected."),
```

`.env.example`, after `ALERT_SYMBOL_COOLDOWN_HOURS=24` and its blank line, before `# --- Execution Realism ---`:

```
# v227: record each accepted simple-channel post so an open admin tab can
# speak its headline. false = the site stays silent; Discord is unaffected.
FEED_POSTS_ENABLED=true

```

`tests/conftest.py`, inside `_pin_dotenv_settings`, after `monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")`:

```python
    # v227: the feed-post recorder writes through the side engine, which reads
    # config.DATABASE_URL (the .env database), not the per-worker test engine.
    # Off for every test; recorder tests switch it on with their own database.
    monkeypatch.setattr(config, "FEED_POSTS_ENABLED", False)
```

- [ ] **Step 5: Write the recorder**

Create `swingbot/core/infra/feed_posts.py`:

```python
"""v227: record each accepted simple-channel post for the site's voice notifications.

Called by the two simple-channel senders right after ``log_posted``, inside the
send's ``try``, so a row exists only for a message Discord accepted
(swingbot/commands/scanning/alerts.py:_mirror and the feed branch of
swingbot/core/scanning/lifecycle_embeds.py:_send_instruction).

Never raises, and never holds the bot loop longer than the side engine's
statement timeout: the insert runs on swingbot.core.db.side_engine (autocommit,
fail-fast, its own tiny pool), never the main pool. It stays synchronous on
purpose -- the bot process is the only writer, so id order is commit order and
``GET /feed-posts?after=<id>`` never skips a row; a thread would break that.

``FEED_POSTS_ENABLED`` off returns before any work. The prune runs at most once
per ``PRUNE_EVERY_S`` per process (an in-process clock, not a scheduled job).

The presentation registry and the repository are imported inside the functions:
core/infra keeps no module-level import of presentation (the cycle
posted_log.py avoids).
"""
from __future__ import annotations

import logging
import time

from swingbot import config
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

RETENTION_DAYS = 7
PRUNE_EVERY_S = 3600

_clock = time.monotonic
_last_prune: float | None = None


def reset_prune_clock() -> None:
    """Forget the last prune (tests): the next recorded post prunes again."""
    global _last_prune
    _last_prune = None


def record_feed_post(embed, ticker: str | None, kind=None) -> None:
    """Record one accepted simple-channel post; never raises."""
    if not config.FEED_POSTS_ENABLED:
        return
    try:
        recorded = _insert(embed, ticker, kind)
    except Exception as exc:  # noqa: BLE001 -- a lost notification, never a lost send
        swallowed(log, "feed_posts.record", exc, level=logging.DEBUG)
        return
    if recorded:
        _maybe_prune()


def _insert(embed, ticker, kind) -> bool:
    kind = kind or getattr(embed, "kind", None)
    if kind is None:
        return False
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    from swingbot.core.presentation.feed_headline import feed_headline

    ticker = ticker.strip() if isinstance(ticker, str) and ticker.strip() else None
    headline = feed_headline(kind, embed, ticker)
    with side_engine.side_connection() as conn:
        feed_posts_repo().insert(kind.name, ticker, headline, conn=conn)
    return True


def _maybe_prune() -> None:
    global _last_prune
    now = _clock()
    if _last_prune is not None and now - _last_prune < PRUNE_EVERY_S:
        return
    _last_prune = now    # set before the attempt: a failing prune is not retried every post
    try:
        from swingbot.core.db import side_engine
        from swingbot.core.db.repositories.feed_posts import feed_posts_repo
        with side_engine.side_connection() as conn:
            feed_posts_repo().prune(RETENTION_DAYS, conn=conn)
    except Exception as exc:  # noqa: BLE001 -- retention is best effort
        swallowed(log, "feed_posts.prune", exc, level=logging.DEBUG)
```

`side_engine.side_connection` and `repositories.feed_posts.feed_posts_repo` are looked up as module attributes at call time, which is what the tests patch.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/test_config_v227_keys.py
python scripts/dev/testrun.py file tests/infra/test_feed_posts_recorder.py
python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py
python scripts/dev/testrun.py file tests/infra/test_posted_log.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; the gate reports no new offender. If a hygiene test counts bare/untagged `except Exception` handlers (known-traps, silent no-ops), both handlers here are tagged through `swallowed` and should pass; if one still flags them, read that test's rule and match it rather than adding a baseline entry.

- [ ] **Step 7: Commit (two scoped commits)**

```bash
git add swingbot/config.py .env.example tests/conftest.py tests/test_config_v227_keys.py
git commit -m "feat(config): v227 FEED_POSTS_ENABLED kill switch, pinned off for the test suite (V227-4)"
git add swingbot/core/infra/feed_posts.py tests/infra/test_feed_posts_recorder.py
git commit -m "feat(infra): v227 record_feed_post -- side-engine insert that never raises, hourly guarded prune (V227-4)"
```

### Task V227-5: Record at the two simple-channel senders

**Model:** sonnet — two one-line insertions at named lines plus call-site tests copied from an existing helper file; the placement rule (inside the `try`, after `log_posted`) is fully specified.

**Files:**
- Modify: `swingbot/commands/scanning/alerts.py` (import block ~line 12; `_mirror` ~line 217)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (import block ~line 14; `_send_instruction` ~line 547)
- Create: `tests/infra/test_feed_posts_call_sites.py`

**Interfaces:**
- Consumes: `record_feed_post(embed, ticker: str | None, kind=None) -> None` from `swingbot.core.infra.feed_posts` (V227-4).
- Produces: nothing new. Both senders call `record_feed_post` exactly once per simple-channel send that returned, and never for a failed send, the history copy, or a history-only status embed.

Placement (spec § 1 Call sites; index Review Focus 1): **inside the `try`, on the line right after `log_posted(...)`**, so a raising `send` skips it. `git grep -n TRADES_SIMPLE_ID swingbot` finds only these two senders; the history-channel fallback copy in `_send_instruction` and the history-only `status_embed` send in `notify_plan_events` are not simple-channel posts and stay unrecorded. The import is module-level in both files: `swingbot.core.infra.feed_posts` imports nothing from presentation at load (V227-4), so no cycle; tests patch the name in each consuming module.

- [ ] **Step 1: Write the failing test**

Create `tests/infra/test_feed_posts_call_sites.py`:

```python
"""v227: only an accepted simple-channel send records a feed post -- never a failed
send, the history copy, or a history-only status embed."""
import asyncio
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.core import presentation as ui
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import lifecycle_embeds as life


class _Chan:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.sent = name, fail, []

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord 500")
        self.sent.append(kwargs)
        return SimpleNamespace(id=len(self.sent))


def _bot(**channels):
    return SimpleNamespace(get_channel=lambda cid: channels.get(str(int(cid))))


@pytest.fixture
def calls(monkeypatch):
    """Every record_feed_post call either sender makes, as (embed, ticker)."""
    seen: list[tuple] = []

    def record(embed, ticker, kind=None):
        seen.append((embed, ticker))

    monkeypatch.setattr(alerts, "record_feed_post", record)
    monkeypatch.setattr(life, "record_feed_post", record)
    monkeypatch.setattr(ui, "push_kwargs", lambda embed, view=None: {"embed": embed})
    monkeypatch.setattr(alerts, "_ticket_view", lambda embed, plan: None)
    monkeypatch.setattr(life, "_feed_view", lambda plan_id: None)
    return seen


# --- alerts._mirror: new setups, tickets, strategy mirrors ----------------------------

def test_an_accepted_mirror_records_the_simple_embed_once(calls):
    embed = SimpleNamespace(kind=Kind.SETUP_SIMPLE)
    plan = SimpleNamespace(ticker="NVDA", plan_id="p1")
    assert asyncio.run(alerts._mirror(_Chan("simple"), embed, plan)) is True
    assert calls == [(embed, "NVDA")]


def test_a_mirror_without_a_plan_records_a_null_ticker(calls):
    embed = SimpleNamespace(kind=Kind.STRATEGY_SIGNAL)
    assert asyncio.run(alerts._mirror(_Chan("simple"), embed, None)) is True
    assert calls == [(embed, None)]


def test_a_failed_mirror_records_nothing(calls):
    ok = asyncio.run(alerts._mirror(_Chan("simple", fail=True), SimpleNamespace(kind=Kind.SETUP_SIMPLE),
                                    SimpleNamespace(ticker="NVDA", plan_id="p1")))
    assert ok is False and calls == []


def test_no_simple_channel_records_nothing(calls):
    assert asyncio.run(alerts._mirror(None, SimpleNamespace(kind=Kind.SETUP_SIMPLE), None)) is False
    assert calls == []


# --- lifecycle_embeds._send_instruction: fills, cancels, stops, TP1, results ----------

_PLAN = SimpleNamespace(plan_id="p1", ticker="AMD", direction="bullish")
_EVENT = SimpleNamespace(plan_id="p1", transition="be_moved", detail={})


def _instruction(feed, history):
    embed = SimpleNamespace(kind=Kind.BE_MOVED)
    pinged = asyncio.run(life._send_instruction(feed, history, embed, _PLAN, _EVENT))
    return embed, pinged


def test_an_accepted_feed_send_records_once_and_the_history_copy_never(calls):
    feed, history = _Chan("feed"), _Chan("history")
    embed, pinged = _instruction(feed, history)
    assert pinged is True and len(feed.sent) == 1 and len(history.sent) == 1
    assert calls == [(embed, "AMD")]


def test_a_failed_feed_send_records_nothing_even_when_history_takes_it(calls):
    history = _Chan("history")
    _embed, pinged = _instruction(_Chan("feed", fail=True), history)
    assert pinged is True and len(history.sent) == 1
    assert calls == []


def test_no_feed_channel_history_only_records_nothing(calls):
    _embed, pinged = _instruction(None, _Chan("history"))
    assert pinged is True and calls == []


def test_a_history_only_status_event_records_nothing(calls, monkeypatch):
    from swingbot.core.planning import plan_store
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(get=lambda pid: _PLAN))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2")
    monkeypatch.setattr(life, "build_plan_event_embed", lambda p, e: SimpleNamespace(kind=Kind.EXPIRED))
    history = _Chan("history")
    event = SimpleNamespace(plan_id="p1", transition="something_else", detail={})
    asyncio.run(life.notify_plan_events(_bot(**{"1": _Chan("feed"), "2": history}), [event]))
    assert len(history.sent) == 1 and calls == []


def test_a_feed_event_through_notify_plan_events_records_once(calls, monkeypatch):
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import execution_embeds
    embed = SimpleNamespace(kind=Kind.BE_MOVED)
    monkeypatch.setattr(plan_store, "PlanStore", lambda: SimpleNamespace(get=lambda pid: _PLAN))
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "1")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "2")
    monkeypatch.setattr(execution_embeds, "build_instruction_embed", lambda p, e: embed)
    monkeypatch.setattr(life, "_delivery", lambda p, e: None)
    asyncio.run(life.notify_plan_events(_bot(**{"1": _Chan("feed"), "2": _Chan("history")}), [_EVENT]))
    assert calls == [(embed, "AMD")]


def test_both_senders_call_the_recorder_right_after_log_posted():
    import inspect
    for fn, line in ((alerts._mirror, "log_posted(simple_embed"),
                     (life._send_instruction, "log_posted(embed, plan.ticker, feed)")):
        src = inspect.getsource(fn)
        after = src.split(line, 1)[1].splitlines()[1].strip()
        assert after.startswith("record_feed_post("), fn.__name__
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/infra/test_feed_posts_call_sites.py`
Expected: FAIL — `AttributeError: <module 'swingbot.commands.scanning.alerts'> has no attribute 'record_feed_post'` (monkeypatch's `raising=True`).

- [ ] **Step 3: Record in `_mirror`**

`swingbot/commands/scanning/alerts.py`, in the import block, after `from swingbot.core.infra.posted_log import log_posted`:

```python
from swingbot.core.infra.feed_posts import record_feed_post
```

and in `_mirror`:

```python
    try:
        await simple_channel.send(**ui.push_kwargs(simple_embed,
                                                   view=_ticket_view(simple_embed, plan)))
        log_posted(simple_embed, getattr(plan, "ticker", None), simple_channel)
        record_feed_post(simple_embed, getattr(plan, "ticker", None))   # v227: the site speaks it
    except Exception as exc:
```

(The rest of `_mirror` is unchanged.)

- [ ] **Step 4: Record in the feed branch of `_send_instruction`**

`swingbot/core/scanning/lifecycle_embeds.py`, in the import block, after `from swingbot.core.infra.posted_log import log_posted`:

```python
from swingbot.core.infra.feed_posts import record_feed_post
```

and in `_send_instruction`'s feed branch only:

```python
    if feed is not None:
        try:
            await feed.send(**ui.push_kwargs(embed, view=_feed_view(plan.plan_id)))
            log_posted(embed, plan.ticker, feed)
            record_feed_post(embed, plan.ticker)   # v227: the simple channel only, never history
            pinged = True
        except Exception as exc:
```

The history branch below it stays exactly as it is.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/infra/test_feed_posts_call_sites.py
python scripts/dev/testrun.py file tests/infra/test_posted_log.py
python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py
python scripts/dev/testrun.py file tests/commands/test_loops_follow_notify.py
python scripts/dev/testrun.py file tests/scanning/test_lifecycle_notifications.py
python scripts/dev/testrun.py file tests/scanning/test_feed_buttons_attach.py
python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; `_mirror` and `_send_instruction` stay well under 15 (no branch added). The existing files run with `FEED_POSTS_ENABLED` pinned off by `tests/conftest.py` (V227-4), so they write nothing.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/alerts.py swingbot/core/scanning/lifecycle_embeds.py \
        tests/infra/test_feed_posts_call_sites.py
git commit -m "feat(alerts): v227 the two simple-channel senders record each accepted post for the site's voice (V227-5)"
```

# Phase 4 — Serving it

### Task V227-6: Admin endpoints `/feed-posts` and `/feed-posts/kinds`

**Model:** sonnet — two read-only Flask routes following `market_updates.py`, with the response shapes fixed in the ledger and the access row decided (viewer).

**Files:**
- Create: `swingbot/admin/api_v1/feed_posts.py`
- Create: `tests/admin/test_api_v1_feed_posts.py`
- Modify: `swingbot/admin/api_v1/__init__.py` (the tuple import inside `register()`, ~line 34-36)
- Modify: `tests/admin/access_expectations.py` (`_VIEWER_GET`, ~line 30-42)

**Interfaces:**
- Consumes: `feed_posts_repo()`, `.after(after_id, limit, *, conn=None) -> list[dict]`, `.latest_id(*, conn=None) -> int` (V227-2); `FEED_FAMILIES`, `kind_phrase(kind, side=None)`, `sample_headline(kind)` (V227-3); `side_engine.side_connection()`; `ApiError(code, message, status)`, `api_v1`, `iso()` (api_v1/__init__.py); `require_auth` (api_v1/auth.py).
- Produces (final, consumed by V227-7 in Part 2):
  - `GET /api/v1/feed-posts?after=<id>&limit=<n>` → `{"items": [{"id": int, "posted_at": iso str, "kind": str, "family": str | null, "ticker": str | null, "headline": str}], "latest_id": int}` oldest first. `limit` default 20, above 50 clamps to 50, `< 1` → 400; non-integer `after`/`limit` → 400 `{"error": {"code": "invalid", ...}}`; no `after` → `"items": []`; `latest_id` 0 on an empty table. A database that cannot be reached → 503 `{"error": {"code": "unavailable", ...}}`.
  - `GET /api/v1/feed-posts/kinds` → `{"families": [{"family": "NEW_SETUP", "label": "New setup", "default_on": bool, "kinds": [{"kind": "FILLED", "label": str, "phrase": str, "sample": str}]}]}` in `FEED_FAMILIES` order, kinds in `Kind` declaration order; `default_on` false only for `WATCH`; SYSTEM and BOOK never listed.
  - Both readable by viewers (`_VIEWER_GET`).

`latest_id` is read **before** the page (index Global Constraints; the notifier sets its cursor to `latest_id` when a page comes back empty): read after, a row committed between the two reads would be skipped by that cursor and never spoken.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_api_v1_feed_posts.py`:

```python
"""v227: GET /api/v1/feed-posts (paging after an id) and /feed-posts/kinds."""
from datetime import datetime, timezone

import pytest

from swingbot.core.db.engine import DatabaseUnavailable
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape

URL = "/api/v1/feed-posts"
KINDS_URL = "/api/v1/feed-posts/kinds"
T0 = datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc)
_ITEM = {"id": int, "posted_at": str, "kind": str, "family": NULLABLE_STR,
         "ticker": NULLABLE_STR, "headline": str}


def _row(row_id, kind="FILLED", ticker="MSFT", headline="Order filled, MSFT"):
    return {"id": row_id, "posted_at": T0, "kind": kind, "ticker": ticker, "headline": headline}


@pytest.fixture
def feed(client, monkeypatch):
    # `client` first: it loads swingbot.admin.app, which registers the endpoints.
    from swingbot.admin.api_v1 import feed_posts as mod
    state = {"rows": [], "latest": 0, "pages": [], "order": []}

    def page(after, limit):
        state["pages"].append((after, limit))
        state["order"].append("page")
        return [r for r in state["rows"] if r["id"] > after][:limit]

    def latest():
        state["order"].append("latest")
        return state["latest"]

    monkeypatch.setattr(mod, "_page", page)
    monkeypatch.setattr(mod, "_latest", latest)
    return state


def test_unauthenticated_is_401(client, feed):
    assert_error(client.get(URL), "auth", 401)
    assert_error(client.get(KINDS_URL), "auth", 401)


def test_without_after_only_the_latest_id_comes_back(client, auth, feed):
    feed["rows"], feed["latest"] = [_row(1), _row(2)], 2
    body = client.get(URL, headers=auth).get_json()
    assert body == {"items": [], "latest_id": 2}
    assert feed["pages"] == []


def test_an_empty_table_is_latest_zero(client, auth, feed):
    assert client.get(URL, headers=auth).get_json() == {"items": [], "latest_id": 0}
    assert client.get(URL + "?after=0", headers=auth).get_json() == {"items": [], "latest_id": 0}


def test_after_pages_oldest_first_with_the_family(client, auth, feed):
    feed["rows"] = [_row(1), _row(2, "MOVE_STOP", "AMD", "Move stop loss, AMD"),
                    _row(3, "LEGACY_GONE", None, "gone")]
    feed["latest"] = 3
    body = client.get(URL + "?after=1", headers=auth).get_json()
    assert_shape(body, {"items": list, "latest_id": int})
    for item in body["items"]:
        assert_shape(item, _ITEM, where="item")
    assert [i["id"] for i in body["items"]] == [2, 3]
    assert body["items"][0] == {"id": 2, "posted_at": "2026-11-12T14:30:00+00:00",
                                "kind": "MOVE_STOP", "family": "MANAGE", "ticker": "AMD",
                                "headline": "Move stop loss, AMD"}
    assert body["items"][1]["family"] is None and body["items"][1]["ticker"] is None
    assert feed["pages"] == [(1, 20)]


def test_the_latest_id_is_read_before_the_page(client, auth, feed):
    client.get(URL + "?after=0", headers=auth)
    assert feed["order"] == ["latest", "page"]


@pytest.mark.parametrize("limit,passed", [("1", 1), ("50", 50), ("99", 50)])
def test_limit_is_used_up_to_fifty(client, auth, feed, limit, passed):
    client.get(f"{URL}?after=0&limit={limit}", headers=auth)
    assert feed["pages"] == [(0, passed)]


@pytest.mark.parametrize("query", ["?after=abc", "?after=1.5", "?after=0&limit=0",
                                   "?after=0&limit=-3", "?after=0&limit=ten"])
def test_bad_parameters_are_400(client, auth, feed, query):
    assert_error(client.get(URL + query, headers=auth), "invalid", 400)
    assert feed["pages"] == []


def test_an_unreachable_database_is_503(client, auth, monkeypatch, feed):
    from swingbot.admin.api_v1 import feed_posts as mod

    def down():
        raise DatabaseUnavailable("side engine backing off")

    monkeypatch.setattr(mod, "_latest", down)
    assert_error(client.get(URL + "?after=0", headers=auth), "unavailable", 503)


def test_a_viewer_may_read_both(viewer_client, feed):
    client, _row_ = viewer_client
    assert client.get(URL).status_code == 200
    assert client.get(KINDS_URL).status_code == 200


def test_kinds_lists_the_five_families_in_order_with_watch_off(client, auth, feed):
    body = client.get(KINDS_URL, headers=auth).get_json()
    families = body["families"]
    assert [f["family"] for f in families] == ["NEW_SETUP", "ENTRY", "MANAGE", "WATCH", "RESULT"]
    assert [f["label"] for f in families] == ["New setup", "Entry", "Manage", "Watch", "Result"]
    assert {f["family"]: f["default_on"] for f in families} == {
        "NEW_SETUP": True, "ENTRY": True, "MANAGE": True, "WATCH": False, "RESULT": True}
    for family in families:
        assert_shape(family, {"family": str, "label": str, "default_on": bool, "kinds": list})
        for kind in family["kinds"]:
            assert_shape(kind, {"kind": str, "label": str, "phrase": str, "sample": str})


def test_kinds_carry_label_phrase_and_sample_in_registry_order(client, auth, feed):
    from swingbot.core.presentation.kinds import Family, Kind
    families = client.get(KINDS_URL, headers=auth).get_json()["families"]
    entry = next(f for f in families if f["family"] == "ENTRY")
    assert [k["kind"] for k in entry["kinds"]] == [k.name for k in Kind if k.family is Family.ENTRY]
    filled = next(k for k in entry["kinds"] if k["kind"] == "FILLED")
    assert filled == {"kind": "FILLED", "label": "FILLED", "phrase": "Order filled",
                      "sample": "Order filled, AAPL"}
    setup = next(f for f in families if f["family"] == "NEW_SETUP")
    simple = next(k for k in setup["kinds"] if k["kind"] == "SETUP_SIMPLE")
    assert simple["phrase"] == "New alert"
    assert simple["sample"] == "New long alert, AAPL, buy at 187.50"


def test_kinds_never_lists_system_or_book(client, auth, feed):
    from swingbot.core.presentation.kinds import Family, Kind
    families = client.get(KINDS_URL, headers=auth).get_json()["families"]
    listed = {k["kind"] for f in families for k in f["kinds"]}
    assert not listed & {k.name for k in Kind if k.family in (Family.SYSTEM, Family.BOOK)}
```

`tests/admin/access_expectations.py`, in `_VIEWER_GET`, extend the line holding `"/events"`:

```python
    "/cancel-precision", "/dashboard", "/equity/candles", "/events", "/feed-posts",
    "/feed-posts/kinds", "/health", "/live",
```

(Replace the existing `"/cancel-precision", "/dashboard", "/equity/candles", "/events", "/health", "/live",` line with the two lines above; nothing else in the list moves.)

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_feed_posts.py`
Expected: FAIL — `ImportError: cannot import name 'feed_posts' from 'swingbot.admin.api_v1'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_access_contract.py`
Expected: FAIL — the two new `_VIEWER_GET` rows name rules the app does not serve yet.

- [ ] **Step 3: Write the routes**

Create `swingbot/admin/api_v1/feed_posts.py`:

```python
"""v227: ``GET /feed-posts`` and ``GET /feed-posts/kinds`` -- what the site speaks.

``/feed-posts`` pages the simple-channel post log (feed_posts) after an id,
oldest first; with no ``after`` it returns only ``latest_id``, which is how a
freshly opened tab starts without a backlog. ``/feed-posts/kinds`` lists the
toggleable kinds per family, with the spoken phrase and a sample, so the
Settings block never hard-codes the registry.

Imports of the repository, the side engine and the presentation registry live
inside the functions (the circular-import note in ``api_v1/__init__.py``).
"""
from __future__ import annotations

import sqlalchemy as sa
from flask import jsonify, request

from swingbot.core.db.engine import DatabaseUnavailable

from . import ApiError, api_v1, iso
from .auth import require_auth

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _int_arg(name: str, default: int | None) -> int | None:
    raw = request.args.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ApiError("invalid", f"{name} must be an integer", 400) from None


def _limit() -> int:
    limit = _int_arg("limit", DEFAULT_LIMIT)
    if limit < 1:
        raise ApiError("invalid", "limit must be at least 1", 400)
    return min(limit, MAX_LIMIT)


def _latest() -> int:
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    with side_engine.side_connection() as conn:
        return feed_posts_repo().latest_id(conn=conn)


def _page(after: int, limit: int) -> list[dict]:
    from swingbot.core.db import side_engine
    from swingbot.core.db.repositories.feed_posts import feed_posts_repo
    with side_engine.side_connection() as conn:
        return feed_posts_repo().after(after, limit, conn=conn)


def _family(kind_name: str) -> str | None:
    from swingbot.core.presentation.kinds import Kind
    member = Kind.__members__.get(kind_name)
    return member.family.name if member is not None else None


def _item(row: dict) -> dict:
    return {"id": row["id"], "posted_at": iso(row["posted_at"]), "kind": row["kind"],
            "family": _family(row["kind"]), "ticker": row["ticker"], "headline": row["headline"]}


@api_v1.route("/feed-posts", methods=["GET"])
@require_auth
def feed_posts_view():
    after = _int_arg("after", None)
    limit = _limit()
    try:
        latest = _latest()   # before the page: a row landing in between is never skipped
        rows = [] if after is None else _page(after, limit)
    except (DatabaseUnavailable, sa.exc.OperationalError, sa.exc.InterfaceError):
        raise ApiError("unavailable", "feed posts are unavailable right now", 503) from None
    return jsonify({"items": [_item(row) for row in rows], "latest_id": latest})


def _kinds_payload() -> list[dict]:
    from swingbot.core.presentation.feed_headline import FEED_FAMILIES, kind_phrase, sample_headline
    from swingbot.core.presentation.kinds import Family, Kind
    return [{"family": family.name, "label": family.label.capitalize(),
             "default_on": family is not Family.WATCH,
             "kinds": [{"kind": kind.name, "label": kind.label, "phrase": kind_phrase(kind),
                        "sample": sample_headline(kind)}
                       for kind in Kind if kind.family is family]}
            for family in FEED_FAMILIES]


@api_v1.route("/feed-posts/kinds", methods=["GET"])
@require_auth
def feed_post_kinds_view():
    return jsonify({"families": _kinds_payload()})
```

`swingbot/admin/api_v1/__init__.py`, inside `register()`, add `feed_posts` to the endpoint-module import (alphabetical after `equity`):

```python
    from . import (access_hook, analytics, calendar, cancel_precision, dashboard, equity,  # noqa: F401
                   feed_posts, jobs, live, market, market_updates, ops_health, reports, research,
                   risk, session, system, trade_commands, trades, users, versions,
                   watchlist)  # (routes + the v207 access hook)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_v1_feed_posts.py
python scripts/dev/testrun.py file tests/admin/test_access_contract.py
python scripts/dev/testrun.py file tests/admin/test_viewer_route_matrix.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_contract.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; no new complexity offender. If `test_viewer_route_matrix.py` needs a sample path or seed for the new rules, they take no converters, so none should be required.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/feed_posts.py swingbot/admin/api_v1/__init__.py \
        tests/admin/test_api_v1_feed_posts.py tests/admin/access_expectations.py
git commit -m "feat(admin): v227 GET /feed-posts paging and /feed-posts/kinds, viewer-readable (V227-6)"
```

