# v227 — Voice notifications, Part 1: storage, repository and headline (V227-1..V227-3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post](../specs/2026-11-12-v227-voice-notifications-design.md) (§ 1 Recording a post, § 2 Serving it, § Testing backend)

Goal, architecture, **Global Constraints**, **Parallelisation** and the task
ledger live in the index:
[`2026-11-12-v227-voice-notifications_0-index.md`](2026-11-12-v227-voice-notifications_0-index.md).
Every task below implicitly carries those constraints. Work happens in the
worktree `.claude/worktrees/2026-11-12-v227-voice-notifications` (all paths
below are relative to it). Tests that reach Postgres need `/replicate-prod-db`
run once per session first (shared `swing-db`, port 56789).

V227-4..V227-6 (recorder, call sites, admin endpoints) continue in
[`2026-11-12-v227-voice-notifications_1b-recorder-admin.md`](2026-11-12-v227-voice-notifications_1b-recorder-admin.md)
(split for the 1500-line cap, never compressed).

Two test files join V227-1 beyond its ledger row, both touched by no other
task: `tests/db/test_unknown_field_round_trip.py` and
`tests/db/test_notify_ddl.py` (they enumerate tables and channels and fail
otherwise).

# Phase 1 — Storage and the `feed` channel

### Task V227-1: `feed_posts` table, revision and the `feed` channel in every registry

**Model:** opus — an Alembic revision with a NOTIFY trigger, a rollback-safety override and an SSE contract that spans Python and TypeScript (schema change + cross-stack contract).

**Files:**
- Create: `swingbot/core/db/migrations/versions/v227_001_feed_posts.py`
- Create: `tests/db/test_v227_feed_posts_schema.py`
- Modify: `swingbot/core/db/schema.py` (new table after `alert_posts`, ~line 265; `PROMOTION_REASONS` entry before its closing `}`, ~line 722)
- Modify: `swingbot/core/db/notify.py:15` (`CHANNELS`)
- Modify: `swingbot/core/db/events.py:9` (`TABLE_CHANNELS`)
- Modify: `tests/admin/test_sse_contract.py` (`EXPECTED_EVENTS`)
- Modify: `tests/db/test_notify_ddl.py` (`test_channels_match_the_existing_watcher_concerns`)
- Modify: `tests/db/test_unknown_field_round_trip.py` (`NOT_REPOSITORY_BACKED`)
- Modify: `frontend/src/app/api/event-stream.ts:9-27` (`EventName`, `EVENT_NAMES`)
- Modify: `frontend/src/app/api/event-stream.spec.ts:472-490` (the "last name" assertion)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns` (schema.py:20/29); `notify.trigger_ddl`, `notify.drop_trigger_ddl`, `notify.trigger_name` (notify.py); `scripts/ops/rollback_migrations.scan_upgrade(source, *, revision, path) -> Verdict` (`.safe`, `.override`, `.reasons`).
- Produces: `schema.feed_posts: sa.Table` with columns `id, posted_at, kind, ticker, headline, doc, updated_at` and index `feed_posts_posted_at_idx`; `notify.CHANNELS[-1] == "feed"`; `events.TABLE_CHANNELS["feed_posts"] == "feed"`; TS `EventName` includes `'feed'`, last in `EVENT_NAMES`; Alembic revision `v227_001`.

- [ ] **Step 0: Confirm the Alembic head**

Run: `python -m alembic heads`
Expected: `v209_001 (head)`. If anything else is the head, stop and report it to the controller: the revision's `down_revision` and this task's tests name `v209_001`.

- [ ] **Step 1: Write the failing schema/migration test**

Create `tests/db/test_v227_feed_posts_schema.py`:

```python
"""v227: revision v227_001 -- feed_posts, the simple-channel post log behind the
site's voice notifications, and its `feed` NOTIFY channel."""
import pathlib
import sys

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, notify, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION = REPO / "swingbot" / "core" / "db" / "migrations" / "versions" / "v227_001_feed_posts.py"
PROMOTED = ("posted_at", "kind", "ticker", "headline")

sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_migrations as rm  # noqa: E402


def test_registered_with_reasons_and_contract():
    table = schema.METADATA.tables["feed_posts"]
    assert schema.promoted_for("feed_posts") == PROMOTED
    assert set(schema.PROMOTION_REASONS["feed_posts"]) == set(PROMOTED)
    assert all(len(reason) <= 100 for reason in schema.PROMOTION_REASONS["feed_posts"].values())
    assert schema.contract_violations(table) == []


def test_columns_and_index():
    t = schema.feed_posts
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.BigInteger)
    assert t.c.posted_at.nullable is False and t.c.posted_at.type.timezone is True
    assert t.c.posted_at.server_default is not None
    assert t.c.kind.nullable is False and t.c.headline.nullable is False
    assert t.c.ticker.nullable is True
    assert [(i.name, [c.name for c in i.columns]) for i in t.indexes] == [
        ("feed_posts_posted_at_idx", ["posted_at"])]


def test_feed_is_the_last_channel_and_feed_posts_raises_it():
    assert notify.CHANNELS[-1] == "feed"
    assert events.TABLE_CHANNELS["feed_posts"] == "feed"
    assert "feed" in events.SSE_EVENTS


def test_v227_001_sits_on_v209_001_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v227_001").down_revision == "v209_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v227_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_the_revision_is_rollback_safe_by_its_stated_reason():
    verdict = rm.scan_upgrade(REVISION.read_text(encoding="utf-8"), revision="v227_001",
                              path=str(REVISION))
    assert verdict.safe is True
    assert verdict.override is not None and "feed_posts" in verdict.override


def test_the_revision_restates_its_channel_instead_of_importing_the_registry():
    source = REVISION.read_text(encoding="utf-8")
    assert "TABLE_CHANNELS" not in source
    assert '("feed_posts", "feed")' in source


def _trigger_names(connection) -> set[str]:
    return set(connection.execute(sa.text(
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())


def test_downgrade_drops_table_and_trigger_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "feed_posts" in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") in _trigger_names(connection)
        downgrade(cfg, "v209_001")
        assert "feed_posts" not in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") not in _trigger_names(connection)
        assert "market_shock_readings" in sa.inspect(connection).get_table_names()
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "feed_posts" in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") in _trigger_names(connection)
```

- [ ] **Step 2: Update the hard-coded registries in the existing tests**

`tests/admin/test_sse_contract.py`, replace `EXPECTED_EVENTS`:

```python
EXPECTED_EVENTS = {"trades", "account", "analytics", "scan", "journal",
                   "bot", "risk", "watchlist", "jobs", "settings", "market", "feed"}
```

`tests/db/test_notify_ddl.py`, replace the first test's tuple:

```python
def test_channels_match_the_existing_watcher_concerns():
    assert notify.CHANNELS == (
        "trades", "account", "analytics", "scan", "journal", "bot", "risk", "watchlist", "jobs", "settings",
        "market", "feed",
    )
```

`tests/db/test_unknown_field_round_trip.py`, add to `NOT_REPOSITORY_BACKED` (after the `admin_snapshots` entry):

```python
    "feed_posts": "append-only spoken-headline log written by FeedPostsRepository.insert with "
                  "doc {} and read as promoted columns; tests/db/test_feed_posts_repository.py",
```

`frontend/src/app/api/event-stream.spec.ts`, replace the whole `describe('market event (v201)', ...)` block (the file's last block) with:

```ts
describe('market event (v201)', () => {
  it('sits just before feed, the last name EVENT_NAMES subscribes to', () => {
    expect(EVENT_NAMES[EVENT_NAMES.length - 2]).toBe('market');
  });

  it('a market SSE message bumps changes(market)', () => {
    FakeEventSource.reset();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const stream = TestBed.inject(EventStream);
    stream.connect();
    const market = stream.changes('market');
    FakeEventSource.latest().emit('market');
    expect(market()).toBe(1);
    stream.disconnect();
    vi.unstubAllGlobals();
  });
});

describe('feed event (v227)', () => {
  it('is the last name EVENT_NAMES subscribes to', () => {
    expect(EVENT_NAMES[EVENT_NAMES.length - 1]).toBe('feed');
  });

  it('a feed SSE message bumps changes(feed) and nothing else', () => {
    FakeEventSource.reset();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const stream = TestBed.inject(EventStream);
    stream.connect();
    const feed = stream.changes('feed');
    const market = stream.changes('market');
    FakeEventSource.latest().emit('feed');
    expect(feed()).toBe(1);
    expect(market()).toBe(0);
    stream.disconnect();
    vi.unstubAllGlobals();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v227_feed_posts_schema.py`
Expected: FAIL — `KeyError: 'feed_posts'` / `AttributeError: module 'swingbot.core.db.schema' has no attribute 'feed_posts'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_sse_contract.py`
Expected: FAIL — `"feed"` missing from `SSE_EVENTS` and `CHANNELS`.

- [ ] **Step 4: Add the channel to the three registries**

`swingbot/core/db/notify.py`:

```python
CHANNELS: tuple[str, ...] = (
    "trades", "account", "analytics", "scan",
    "journal", "bot", "risk", "watchlist", "jobs", "settings",
    "market",
    # v227: feed_posts -- one row per accepted simple-channel post; the SPA
    # fetches the new rows and speaks their headlines.
    "feed",
)
```

`swingbot/core/db/events.py`, append inside `TABLE_CHANNELS` after `"market_data_state": "watchlist",`:

```python
    # v227: the simple-channel post log; raises its own concern so only the
    # voice notifier refetches, never a panel.
    "feed_posts": "feed",
```

`swingbot/core/db/schema.py`, after the `alert_posts = register(...)` block:

```python
# v227: one row per simple-channel post Discord accepted, written synchronously by
# the bot process only (id order = commit order, which makes ?after=<id> paging
# gap-free). Pruned after 7 days by the recorder itself. SSE `feed`.
feed_posts = register(sa.Table(
    "feed_posts", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("ticker", sa.Text, nullable=True),
    sa.Column("headline", sa.Text, nullable=False),
    *standard_columns(),
    sa.Index("feed_posts_posted_at_idx", "posted_at"),
), ("posted_at", "kind", "ticker", "headline"))
```

And in `PROMOTION_REASONS`, after the `"market_shock_state": {...},` entry:

```python
    "feed_posts": {
        "posted_at": "feed_posts_posted_at_idx: the 7-day prune's WHERE and its existence check",
        "kind": "NOT NULL Kind member name; the SPA's per-kind voice filter",
        "ticker": "ticker spoken in the headline; NULL for a post without one",
        "headline": "NOT NULL spoken text, served as is by GET /feed-posts",
    },
```

- [ ] **Step 5: Write the revision**

Create `swingbot/core/db/migrations/versions/v227_001_feed_posts.py`:

```python
"""v227: feed_posts -- one row per accepted simple-channel post, spoken by the site.

Additive: rollback is this revision's downgrade (drop the trigger, then the
table). Leaving it after a code-only rollback is also safe: older code never
reads feed_posts, and an older admin ignores the unknown `feed` channel
(swingbot/admin/events/db_listener.py logs it at debug and moves on).

Revision ID: v227_001
Revises: v209_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from swingbot.core.db.notify import drop_trigger_ddl, trigger_ddl

revision = "v227_001"
down_revision = "v209_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

# op.execute(trigger_ddl(...)) is non-literal SQL, which scripts/ops/rollback_migrations.py
# cannot read; this states why running older code on this schema is still safe.
ROLLBACK_SAFE = "older code never reads feed_posts; an older admin ignores the unknown feed channel"

_TS = sa.TIMESTAMP(timezone=True)
# Restated rather than read from events.TABLE_CHANNELS: a revision is frozen.
_TABLE = ("feed_posts", "feed")


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    table, channel = _TABLE
    op.create_table(table,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("posted_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("ticker", sa.Text, nullable=True),
        sa.Column("headline", sa.Text, nullable=False),
        *_standard())
    op.create_index("feed_posts_posted_at_idx", table, ["posted_at"])
    op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    table, _channel = _TABLE
    op.execute(drop_trigger_ddl(table))
    op.drop_index("feed_posts_posted_at_idx", table_name=table)
    op.drop_table(table)
```

Keep `ROLLBACK_SAFE` a single plain string literal on one top-level assignment (the scanner reads it with `ast.literal_eval`), and `_TABLE` written exactly `("feed_posts", "feed")` (a test looks for that literal).

- [ ] **Step 6: Add `feed` to the SPA's event names**

`frontend/src/app/api/event-stream.ts`, update the doc comment and both lists:

```ts
/** The event types the server can raise, plus the two it synthesises.
 *  Mirrors spec v12's taxonomy table -- one type per *concern*, so several
 *  files raise the same event and the client never learns the storage
 *  layout. `feed` (v227) is the simple-channel post log the voice notifier
 *  reads. */
export type EventName =
  | 'trades'
  | 'account'
  | 'analytics'
  | 'journal'
  | 'scan'
  | 'bot'
  | 'risk'
  | 'watchlist'
  | 'jobs'
  | 'settings'
  | 'market'
  | 'feed';

export const EVENT_NAMES: readonly EventName[] = [
  'trades', 'account', 'analytics', 'journal', 'scan',
  'bot', 'risk', 'watchlist', 'jobs', 'settings', 'market', 'feed',
] as const;
```

- [ ] **Step 7: Run the tests to verify they pass**

Run each (all must be green):

```bash
python scripts/dev/testrun.py file tests/db/test_v227_feed_posts_schema.py
python scripts/dev/testrun.py file tests/admin/test_sse_contract.py
python scripts/dev/testrun.py file tests/db/test_notify_ddl.py
python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
python scripts/dev/testrun.py file tests/db/test_file_publishers.py
python scripts/dev/testrun.py file tests/db/test_schema_contract.py
python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py
node frontend/scripts/ng-test.mjs frontend --include src/app/api/event-stream.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 8: Commit (two scoped commits), then the committed-tree rollback check**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/notify.py swingbot/core/db/events.py \
        swingbot/core/db/migrations/versions/v227_001_feed_posts.py \
        tests/db/test_v227_feed_posts_schema.py tests/db/test_notify_ddl.py \
        tests/db/test_unknown_field_round_trip.py tests/admin/test_sse_contract.py
git commit -m "feat(db): v227 feed_posts table, rollback-safe revision v227_001 and the feed NOTIFY channel (V227-1)"
git add frontend/src/app/api/event-stream.ts frontend/src/app/api/event-stream.spec.ts
git commit -m "feat(ui): feed joins the SPA's SSE event names (V227-1)"
python scripts/dev/testrun.py file tests/scripts/test_rollback_migrations.py
```

Expected: PASS. `test_every_revision_newer_than_the_floor_is_rollback_safe` scans the committed `HEAD`, so it sees `v227_001` only after the commit.

### Task V227-2: `FeedPostsRepository`: insert, page after an id, latest id, guarded prune

**Model:** sonnet — a small append-only repository over an existing table, following `alert_posts.py`, with one non-obvious guard (no empty `DELETE`) spelled out below.

**Files:**
- Create: `swingbot/core/db/repositories/feed_posts.py`
- Create: `tests/db/test_feed_posts_repository.py`

**Interfaces:**
- Consumes: `schema.feed_posts` (V227-1); `swingbot.core.db.engine.get_engine` (read through the module attribute so the test conftest's patch applies).
- Produces (final names, consumed by V227-4 and V227-6):
  - `class FeedPostsRepository`
  - `insert(kind: str, ticker: str | None, headline: str, *, conn: sa.Connection) -> int` — the new id
  - `after(after_id: int, limit: int, *, conn: sa.Connection | None = None) -> list[dict]` — keys `id, posted_at, kind, ticker, headline`; `posted_at` a tz-aware `datetime`; ascending id; `limit` used as given
  - `latest_id(*, conn: sa.Connection | None = None) -> int` — `0` on an empty table
  - `prune(days: int, *, conn: sa.Connection) -> int` — rows deleted; `0` and **no `DELETE` statement** when nothing is older
  - `feed_posts_repo() -> FeedPostsRepository` — module singleton

Why a plain class, not `Repository`: the base class is key-shaped and its `insert(record)` takes a flat dict; this table is written with three fixed fields and read as promoted columns only. Why the existence check in `prune`: the `feed_posts` NOTIFY trigger is statement-level, so even a zero-row `DELETE` raises a `feed` event to every open admin tab (spec § 1 Retention).

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_feed_posts_repository.py`:

```python
"""v227: FeedPostsRepository -- the simple-channel post log the site speaks from."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories import feed_posts as fp


@pytest.fixture
def repo():
    return fp.FeedPostsRepository()


def _age(conn, row_id: int, days: float) -> None:
    conn.execute(sa.update(schema.feed_posts).where(schema.feed_posts.c.id == row_id)
                 .values(posted_at=sa.func.now() - timedelta(days=days)))


def test_insert_returns_the_new_id_and_stores_the_promoted_fields(repo, db_conn):
    first = repo.insert("FILLED", "MSFT", "Order filled, MSFT", conn=db_conn)
    second = repo.insert("CANCEL", None, "Order cancelled", conn=db_conn)
    assert second > first
    row = db_conn.execute(sa.select(schema.feed_posts).where(
        schema.feed_posts.c.id == first)).one()._mapping
    assert (row["kind"], row["ticker"], row["headline"]) == ("FILLED", "MSFT", "Order filled, MSFT")
    assert row["doc"] == {}
    assert row["posted_at"].tzinfo is not None


def test_after_pages_oldest_first_and_honours_the_limit(repo, db_conn):
    ids = [repo.insert("FILLED", t, f"Order filled, {t}", conn=db_conn) for t in ("A", "B", "C")]
    page = repo.after(ids[0], 10, conn=db_conn)
    assert [r["id"] for r in page] == ids[1:]
    assert set(page[0]) == {"id", "posted_at", "kind", "ticker", "headline"}
    assert isinstance(page[0]["posted_at"], datetime) and page[0]["posted_at"].tzinfo is not None
    assert [r["ticker"] for r in repo.after(0, 2, conn=db_conn)] == ["A", "B"]


def test_after_the_newest_id_is_empty(repo, db_conn):
    newest = repo.insert("FILLED", "A", "Order filled, A", conn=db_conn)
    assert repo.after(newest, 20, conn=db_conn) == []


def test_latest_id_is_zero_on_an_empty_table_then_the_newest_id(repo, db_conn):
    assert repo.latest_id(conn=db_conn) == 0
    repo.insert("FILLED", "A", "Order filled, A", conn=db_conn)
    newest = repo.insert("WIN", "B", "Winner, B", conn=db_conn)
    assert repo.latest_id(conn=db_conn) == newest


def test_prune_removes_only_rows_older_than_the_window(repo, db_conn):
    old = repo.insert("FILLED", "OLD", "Order filled, OLD", conn=db_conn)
    edge = repo.insert("FILLED", "EDGE", "Order filled, EDGE", conn=db_conn)
    fresh = repo.insert("FILLED", "NEW", "Order filled, NEW", conn=db_conn)
    _age(db_conn, old, 8)
    _age(db_conn, edge, 6.9)
    assert repo.prune(7, conn=db_conn) == 1
    assert [r["id"] for r in repo.after(0, 50, conn=db_conn)] == [edge, fresh]


class _Statements:
    """Every SQL statement the connection's engine runs while installed."""

    def __init__(self, conn):
        self.engine, self.seen = conn.engine, []

    def __enter__(self):
        sa.event.listen(self.engine, "before_cursor_execute", self._record)
        return self.seen

    def __exit__(self, *exc):
        sa.event.remove(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.seen.append(statement.strip().upper())


def test_prune_with_nothing_old_issues_no_delete(repo, db_conn):
    repo.insert("FILLED", "NEW", "Order filled, NEW", conn=db_conn)
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 0
    assert seen and not any(s.startswith("DELETE") for s in seen)


def test_prune_on_an_empty_table_issues_no_delete(repo, db_conn):
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 0
    assert not any(s.startswith("DELETE") for s in seen)


def test_prune_with_an_old_row_issues_exactly_one_delete(repo, db_conn):
    _age(db_conn, repo.insert("FILLED", "OLD", "Order filled, OLD", conn=db_conn), 30)
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 1
    assert sum(s.startswith("DELETE") for s in seen) == 1


def test_reads_without_a_connection_use_the_store_engine(repo, db_engine):
    # conn=None goes through swingbot.core.db.engine.get_engine, which the
    # autouse _store_database fixture points at this worker's test database.
    assert repo.latest_id() == 0
    assert repo.after(0, 5) == []


def test_the_module_singleton_is_one_instance():
    assert fp.feed_posts_repo() is fp.feed_posts_repo()
    assert isinstance(fp.feed_posts_repo(), fp.FeedPostsRepository)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_feed_posts_repository.py`
Expected: FAIL — `ImportError: cannot import name 'feed_posts' from 'swingbot.core.db.repositories'` (module missing).

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/feed_posts.py`:

```python
"""v227: the simple-channel post log the admin site speaks from, append-only.

One row per simple-channel post Discord accepted: promoted posted_at / kind /
ticker / headline, ``doc`` always ``{}``. Written synchronously by the bot
process only (swingbot.core.infra.feed_posts.record_feed_post), so id order is
commit order and ``after(id)`` paging never skips a row. Read by
``GET /api/v1/feed-posts``. Pruned after a week by the recorder.

The table's NOTIFY trigger is statement-level: every INSERT/UPDATE/DELETE,
even one touching zero rows, raises the ``feed`` SSE event. ``prune``
therefore looks for an old row first and only then deletes.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import sqlalchemy as sa

from swingbot.core.db import engine as db_engine
from swingbot.core.db.schema import feed_posts

_COLUMNS = ("id", "posted_at", "kind", "ticker", "headline")


class FeedPostsRepository:
    def __init__(self):
        self.table = feed_posts

    @contextmanager
    def _tx(self, conn: sa.Connection | None) -> Iterator[sa.Connection]:
        if conn is not None:
            yield conn
            return
        # Through the module attribute, never a name bound at import: the test
        # conftest swaps engine.get_engine for this worker's database.
        with db_engine.get_engine().begin() as owned:
            yield owned

    def insert(self, kind: str, ticker: str | None, headline: str, *,
               conn: sa.Connection) -> int:
        statement = (sa.insert(self.table)
                     .values(kind=kind, ticker=ticker, headline=headline, doc={})
                     .returning(self.table.c.id))
        return int(conn.execute(statement).scalar_one())

    def after(self, after_id: int, limit: int, *,
              conn: sa.Connection | None = None) -> list[dict]:
        c = self.table.c
        statement = (sa.select(*(c[name] for name in _COLUMNS))
                     .where(c.id > after_id).order_by(c.id).limit(limit))
        with self._tx(conn) as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]

    def latest_id(self, *, conn: sa.Connection | None = None) -> int:
        statement = sa.select(sa.func.coalesce(sa.func.max(self.table.c.id), 0))
        with self._tx(conn) as connection:
            return int(connection.execute(statement).scalar_one())

    def prune(self, days: int, *, conn: sa.Connection) -> int:
        cutoff = sa.func.now() - sa.literal_column(f"interval '{int(days)} days'")
        old = self.table.c.posted_at < cutoff
        found = conn.execute(sa.select(sa.literal(1)).where(old).limit(1)).first()
        if found is None:
            return 0    # no DELETE: the statement trigger would raise an empty `feed` event
        return conn.execute(sa.delete(self.table).where(old)).rowcount


_repo: FeedPostsRepository | None = None


def feed_posts_repo() -> FeedPostsRepository:
    global _repo
    if _repo is None:
        _repo = FeedPostsRepository()
    return _repo
```

`int(days)` is what keeps the interval literal safe to interpolate.

- [ ] **Step 4: Run it to verify it passes**

Run: `python scripts/dev/testrun.py file tests/db/test_feed_posts_repository.py`
Expected: PASS, `0 failed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new offender.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/feed_posts.py tests/db/test_feed_posts_repository.py
git commit -m "feat(db): v227 FeedPostsRepository -- insert, page after an id, latest id, prune without an empty DELETE (V227-2)"
```

# Phase 2 — The spoken headline

### Task V227-3: Spoken headline builder; push embeds carry side and entry price

**Model:** opus — touches the registry-driven embed class every Discord push goes through (`PushEmbed` slots must never reach the wire) and fixes the spoken wording the partner hears (presentation contract + alert surface).

**Files:**
- Create: `swingbot/core/presentation/feed_headline.py`
- Create: `tests/presentation/test_feed_headline.py`
- Modify: `swingbot/core/presentation/components.py` (`PushEmbed.__slots__`, `push_embed`, `status_embed`)
- Modify: `swingbot/core/scanning/alert_embeds.py` (`build_strategy_simple_embed`, `build_simple_alert`)
- Modify: `swingbot/core/scanning/execution_embeds.py` (`build_ticket_embed`)
- Modify: `tests/presentation/test_components.py` (push-embed slots)

**Interfaces:**
- Consumes: `kinds.Kind`, `kinds.Family`, `kinds.side_word(direction) -> "LONG" | "SHORT" | tokens.ABSENT` (kinds.py:186), `tokens.ABSENT == "—"`.
- Produces (final, consumed by V227-4 and V227-6):
  - `FEED_FAMILIES: tuple[Family, ...] = (Family.NEW_SETUP, Family.ENTRY, Family.MANAGE, Family.WATCH, Family.RESULT)`
  - `KIND_PHRASES: dict[Kind, str]` (may hold `{side}`)
  - `kind_phrase(kind: Kind, side: str | None = None) -> str`
  - `feed_headline(kind: Kind, embed, ticker: str | None) -> str`
  - `sample_headline(kind: Kind) -> str` — ticker `"AAPL"`, side long, price `187.50` where the kind speaks one
  - `PushEmbed.direction: str | None`, `PushEmbed.entry_price: float | None` — never sent to Discord; read with `getattr(embed, ..., None)` so any embed (plain `discord.Embed`, `SimpleNamespace`) is safe

Wording rules (spec § 1 Headline builder, index Global Constraints): phrase from `KIND_PHRASES`, else `kind.label.lower()`; `{side}` becomes `long`/`short`, and with no known side the placeholder and its trailing space vanish ("New alert"); ticker next; a price clause only for `SETUP_ALERT`, `SETUP_SIMPLE`, `STRATEGY_SIGNAL`, `TICKET_PLACE` with a finite positive entry price — "buy at 187.50" (long), "sell at 187.50" (short), "entry 187.50" (side unknown). Non-empty parts joined with ", ". Never `None`, `nan` or an empty clause.

- [ ] **Step 1: Write the failing test**

Create `tests/presentation/test_feed_headline.py`:

```python
"""v227: the short headline the admin site speaks for each simple-channel post."""
import dataclasses
import math
from types import SimpleNamespace

import discord
import pytest

from swingbot import config
from swingbot.core.presentation import components as c
from swingbot.core.presentation import feed_headline as fh
from swingbot.core.presentation import short_notice
from swingbot.core.presentation.kinds import Family, Kind
from swingbot.core.scanning import alert_embeds as ae
from swingbot.core.scanning import execution_embeds
from tests.presentation.test_market_on_open_alert import _market
from tests.scanning.test_embeds_v3 import (make_item, make_plan_v2,  # noqa: F401
                                           _isolated_scan_snapshots)

FIVE = (Family.NEW_SETUP, Family.ENTRY, Family.MANAGE, Family.WATCH, Family.RESULT)


def _embed(direction=None, entry_price=None):
    return SimpleNamespace(direction=direction, entry_price=entry_price)


def test_the_five_simple_channel_families_in_order():
    assert fh.FEED_FAMILIES == FIVE


def test_every_kind_of_the_five_families_has_a_phrase():
    missing = [k.name for k in Kind if k.family in FIVE and k not in fh.KIND_PHRASES]
    assert missing == []
    assert not [k.name for k in fh.KIND_PHRASES if k.family not in FIVE]


@pytest.mark.parametrize("kind,embed,ticker,expected", [
    (Kind.SETUP_SIMPLE, _embed("bullish", 187.5), "AAPL", "New long alert, AAPL, buy at 187.50"),
    (Kind.SETUP_ALERT, _embed("bearish", 42.0), "TSLA", "New short alert, TSLA, sell at 42.00"),
    (Kind.STRATEGY_SIGNAL, _embed(None, 10.0), "AMD", "New alert, AMD, entry 10.00"),
    (Kind.TICKET_PLACE, _embed("bullish", 99.991), "NVDA", "Place order, NVDA, buy at 99.99"),
    (Kind.TICKET_DO_NOT_PLACE, _embed("bullish", 99.0), "NVDA", "Do not place, NVDA"),
    (Kind.FILLED, _embed("bullish", 187.5), "MSFT", "Order filled, MSFT"),
    (Kind.CANCEL, _embed("bullish"), "MSFT", "Order cancelled, MSFT"),
    (Kind.MOVE_STOP, _embed(), "MSFT", "Move stop loss, MSFT"),
    (Kind.TP1_HIT, _embed(), "MSFT", "Take profit one, MSFT"),
    (Kind.STOPPED, _embed(), "MSFT", "Stopped out, MSFT"),
    (Kind.NEAR_STOP, _embed(), "MSFT", "Near stop, MSFT"),
    (Kind.RISK_CAP, _embed(), None, "Cancelled by risk cap"),
])
def test_headlines(kind, embed, ticker, expected):
    assert fh.feed_headline(kind, embed, ticker) == expected


@pytest.mark.parametrize("price", [None, 0, -5.0, math.nan, math.inf, "abc", "187.5x"])
def test_a_missing_or_bad_price_drops_the_clause(price):
    assert fh.feed_headline(Kind.SETUP_SIMPLE, _embed("bullish", price), "AAPL") == "New long alert, AAPL"


@pytest.mark.parametrize("ticker", [None, "", "   ", math.nan, 12])
def test_a_missing_or_odd_ticker_is_dropped(ticker):
    assert fh.feed_headline(Kind.FILLED, _embed(), ticker) == "Order filled"


def test_an_embed_without_the_attributes_is_fine():
    assert fh.feed_headline(Kind.SETUP_SIMPLE, discord.Embed(), "AAPL") == "New alert, AAPL"
    assert fh.feed_headline(Kind.SETUP_SIMPLE, object(), "AAPL") == "New alert, AAPL"


def test_a_kind_without_a_phrase_falls_back_to_its_label_lower_cased():
    assert fh.feed_headline(Kind.BOT_ONLINE, _embed(), None) == "online"
    assert fh.kind_phrase(Kind.HEALTH_ALERT) == "health alert"


def test_spoken_text_never_says_none_or_nan_for_any_kind():
    for kind in Kind:
        for embed in (_embed(), _embed("bullish", None), _embed("sideways", math.nan)):
            text = fh.feed_headline(kind, embed, None)
            assert text and "None" not in text and "nan" not in text.split(", ")
            assert ", ," not in text and not text.endswith(", ")


def test_kind_phrase_without_a_side_drops_the_placeholder():
    assert fh.kind_phrase(Kind.SETUP_SIMPLE) == "New alert"
    assert fh.kind_phrase(Kind.SETUP_SIMPLE, "long") == "New long alert"
    assert fh.kind_phrase(Kind.FILLED, "long") == "Order filled"


def test_sample_headlines():
    assert fh.sample_headline(Kind.SETUP_SIMPLE) == "New long alert, AAPL, buy at 187.50"
    assert fh.sample_headline(Kind.TICKET_PLACE) == "Place order, AAPL, buy at 187.50"
    assert fh.sample_headline(Kind.FILLED) == "Order filled, AAPL"
    assert fh.sample_headline(Kind.NEAR_TP) == "Near target, AAPL"


# --- the embeds carry what the headline reads ---------------------------------------

def test_push_embed_carries_direction_and_no_price():
    embed = c.push_embed(Kind.FILLED, "MSFT", "bearish")
    assert embed.direction == "bearish" and embed.entry_price is None


def test_status_embed_carries_neither():
    embed = c.status_embed("Title", "Body", 0x123456)
    assert embed.direction is None and embed.entry_price is None


def test_the_new_slots_never_reach_discord():
    embed = c.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv3")
    embed.entry_price = 187.5
    payload = embed.to_dict()
    assert "direction" not in payload and "entry_price" not in payload
    assert c.push_kwargs(embed) == {"embed": embed, "content": embed.push_text}


@pytest.fixture
def _alerts_env(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-01")
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {
        "shares": 20.0, "risk_amount": 100.0, "position_value": 2000.0, "mode": "risk_pct"})


def test_the_strategy_mirror_carries_its_trigger_price(_alerts_env):
    plan = _market(source="strategy", strategy="Fibonacci", trigger_price=101.25)
    embed = ae.build_strategy_simple_embed(plan)
    assert embed.direction == "bullish" and embed.entry_price == 101.25
    assert fh.feed_headline(embed.kind, embed, plan.ticker).endswith("buy at 101.25")


def test_the_simple_alert_carries_the_entry_it_prints(_alerts_env):
    item = make_item(plan_v2=make_plan_v2())
    embed = ae.build_simple_alert(item)
    assert embed.direction == item.result.trend
    assert isinstance(embed.entry_price, float) and embed.entry_price > 0
    assert f"Entry **{embed.entry_price:.2f}**" in embed.description


def test_the_ticket_carries_its_trigger_price(_alerts_env):
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(trigger_price=123.4), stop_loss=95.0))
    item.paper_logged = True
    embed = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert embed.kind in (Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE)
    assert embed.entry_price == 123.4 and embed.direction == "bullish"
```

Add to `tests/presentation/test_components.py`, after `test_push_kwargs_without_a_view_never_adds_the_view_key`:

```python
def test_push_embed_slots_carry_v227_spoken_fields():
    # v227: direction and entry_price ride on the embed for the spoken headline
    # (swingbot.core.presentation.feed_headline) and are never sent.
    assert c.PushEmbed.__slots__ == ("push_text", "kind", "direction", "entry_price")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/presentation/test_feed_headline.py`
Expected: FAIL — `ImportError: cannot import name 'feed_headline' from 'swingbot.core.presentation'`.

- [ ] **Step 3: Carry side and entry on the push embeds**

`swingbot/core/presentation/components.py`:

```python
class PushEmbed(discord.Embed):
    """A discord.Embed that also carries its push-preview line (v110 §4).

    A phone push shows a message's ``content``, never the embed title, so every
    pushed builder returns one of these and every sender passes
    ``push_kwargs(embed)`` to ``send()``. Carrying the line on the embed keeps
    the alert tuples' shape unchanged. ``kind`` is kept for v111's
    "alert posted" log line, ``direction`` and ``entry_price`` for v227's
    spoken headline (presentation.feed_headline); none of them is ever sent
    (``Embed.to_dict`` reads only ``Embed``'s own underscore slots)."""

    __slots__ = ("push_text", "kind", "direction", "entry_price")


def push_embed(kind: Kind, ticker: str = "", direction: str | None = None,
               detail: str = "", *, description: str | None = None,
               factual: bool = False) -> PushEmbed:
    """A PushEmbed whose title and push line both come from the registry."""
    embed = PushEmbed(title=kinds.title(kind, ticker, direction, detail, factual=factual), description=description)
    embed.push_text = kinds.content_line(kind, ticker, direction, detail, factual=factual)
    embed.kind = kind
    embed.direction = direction
    embed.entry_price = None    # set by the builders whose post speaks a price
    return embed


def status_embed(title: str, description: str, colour: int) -> PushEmbed:
    """A plain status PushEmbed (no registry kind) striped with ``colour`` (v210).

    Colour is set here, in the presentation package, so scanning code that
    posts a status notice never touches ``discord.Color`` itself."""
    embed = PushEmbed(title=title, description=description, colour=discord.Color(colour))
    embed.push_text = title
    embed.kind = None
    embed.direction = None
    embed.entry_price = None
    return embed
```

`swingbot/core/scanning/alert_embeds.py`, in `build_strategy_simple_embed`, between `ui.apply_chrome(...)` and `return embed`:

```python
    embed.entry_price = plan.trigger_price    # v227: spoken "buy at <entry>"
```

In `build_simple_alert`, between its `ui.apply_chrome(...)` and `return embed`:

```python
    embed.entry_price = nums["entry"]    # v227: the entry the plan line prints
```

`swingbot/core/scanning/execution_embeds.py`, replace the last line of `build_ticket_embed`:

```python
    embed = render(instruction, kind, block=plan_levels_block(plan, plan.trigger_price))
    embed.entry_price = plan.trigger_price    # v227: spoken "buy at <entry>"
    return embed
```

(`render` builds through `ui.push_embed`, so `direction` is already `instruction.direction`.)

- [ ] **Step 4: Write the headline builder**

Create `swingbot/core/presentation/feed_headline.py`:

```python
"""v227: the short headline the admin site speaks for a simple-channel post.

Table-driven: one phrase per Kind of the five families the simple channel
carries, then the ticker, then -- for new setups and tickets only -- the entry
price ("New long alert, AAPL, buy at 187.50"). A missing piece is dropped,
never spoken as "None". A Kind with no phrase speaks its registry label,
lower-cased. Reads ``direction`` and ``entry_price`` off the embed with
``getattr`` (presentation.components.PushEmbed carries both).
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from swingbot.core.presentation import kinds, tokens
from swingbot.core.presentation.kinds import Family, Kind

#: The families the simple channel posts; SYSTEM and BOOK never go there.
FEED_FAMILIES: tuple[Family, ...] = (Family.NEW_SETUP, Family.ENTRY, Family.MANAGE,
                                     Family.WATCH, Family.RESULT)

KIND_PHRASES: dict[Kind, str] = {
    Kind.SETUP_ALERT: "New {side} alert",
    Kind.SETUP_SIMPLE: "New {side} alert",
    Kind.STRATEGY_SIGNAL: "New {side} alert",
    Kind.TICKET_PLACE: "Place order",
    Kind.TICKET_DO_NOT_PLACE: "Do not place",
    Kind.DIGEST: "Setup digest",
    Kind.ENTRY_TRIGGERED: "Entry triggered",
    Kind.FILLED: "Order filled",
    Kind.RECLAIM_ORDER: "Reclaim order",
    Kind.BE_MOVED: "Stop moved to break even",
    Kind.TP1_HIT: "Take profit one",
    Kind.MOVE_STOP: "Move stop loss",
    Kind.CANCEL: "Order cancelled",
    Kind.RISK_CAP: "Cancelled by risk cap",
    Kind.PLAN_UPDATE: "Plan updated",
    Kind.NEAR_STOP: "Near stop",
    Kind.NEAR_TP: "Near target",
    Kind.CLOSED_TRADE: "Trade closed",
    Kind.STOPPED: "Stopped out",
    Kind.WIN: "Winner",
    Kind.SCRATCHED: "Scratched",
    Kind.EXITED: "Exited",
    Kind.CLOSE_AT_MARKET: "Close at market",
    Kind.EXPIRED: "Expired",
    Kind.INVALIDATED: "Invalidated",
}

#: Kinds whose headline speaks the entry price.
_PRICED = frozenset({Kind.SETUP_ALERT, Kind.SETUP_SIMPLE, Kind.STRATEGY_SIGNAL,
                     Kind.TICKET_PLACE})
_PRICE_VERB = {"bullish": "buy at", "bearish": "sell at"}
_SAMPLE = SimpleNamespace(direction="bullish", entry_price=187.50)


def _side(direction) -> str | None:
    word = kinds.side_word(direction if isinstance(direction, str) else None)
    return None if word == tokens.ABSENT else word.lower()


def kind_phrase(kind: Kind, side: str | None = None) -> str:
    """The phrase for ``kind``; ``{side}`` filled or dropped with its space."""
    template = KIND_PHRASES.get(kind)
    if template is None:
        return kind.label.lower()
    return template.replace("{side} ", f"{side} " if side else "")


def _ticker(ticker) -> str:
    return ticker.strip() if isinstance(ticker, str) else ""


def _price(embed) -> float | None:
    try:
        value = float(getattr(embed, "entry_price", None))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _price_clause(kind: Kind, direction, price: float | None) -> str:
    if kind not in _PRICED or price is None:
        return ""
    return f"{_PRICE_VERB.get(direction, 'entry')} {price:.2f}"


def feed_headline(kind: Kind, embed, ticker: str | None) -> str:
    """"New long alert, AAPL, buy at 187.50" / "Order filled, MSFT" / "Order cancelled"."""
    direction = getattr(embed, "direction", None)
    parts = (kind_phrase(kind, _side(direction)), _ticker(ticker),
             _price_clause(kind, direction, _price(embed)))
    return ", ".join(part for part in parts if part)


def sample_headline(kind: Kind) -> str:
    """What ``kind`` sounds like for a long AAPL plan entering at 187.50."""
    return feed_headline(kind, _SAMPLE, "AAPL")
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/presentation/test_feed_headline.py
python scripts/dev/testrun.py file tests/presentation/test_components.py
python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py
python scripts/dev/testrun.py file tests/presentation/test_market_on_open_alert.py
python scripts/dev/testrun.py file tests/presentation/test_kinds.py
python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; the gate reports no new offender. If `test_the_simple_alert_carries_the_entry_it_prints` fails on the description match, read `build_simple_alert`'s `plan_line` (alert_embeds.py ~line 437) and assert against the exact `Entry **<x>**` text it prints — `entry_price` must be the same `nums["entry"]`.

- [ ] **Step 6: Commit (two scoped commits)**

```bash
git add swingbot/core/presentation/components.py swingbot/core/scanning/alert_embeds.py \
        swingbot/core/scanning/execution_embeds.py tests/presentation/test_components.py
git commit -m "feat(presentation): push embeds carry direction and entry price for v227's spoken headline, never sent (V227-3)"
git add swingbot/core/presentation/feed_headline.py tests/presentation/test_feed_headline.py
git commit -m "feat(presentation): v227 feed_headline -- table-driven spoken headline per Kind (V227-3)"
```

