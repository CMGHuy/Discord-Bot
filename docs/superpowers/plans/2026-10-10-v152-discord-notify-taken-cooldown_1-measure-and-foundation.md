# v152 Discord notify, Following, per-symbol cooldown: Part 1, measurement and foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V152-3:" -A 400 docs/superpowers/plans/2026-10-10-v152-discord-notify-taken-cooldown_1-measure-and-foundation.md`.

**Bump:** bot minor · ui patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md)

Global constraints, the decisions this part relies on (1–4), the task ledger and the full `## Parallelisation` live in the index: [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md). Every task below implicitly includes those constraints (never `cd`; stage by name; no `VERSION.json` bump; complexity < 15; every new DB call from Discord code goes through `asyncio.to_thread` — the repositories here are plain sync code, the callers in later parts wrap them).

## Parallelisation

V152-1 touches no code (results note only). V152-2 first among the code tasks: V152-3 and V152-4 import its tables and run in parallel with each other (disjoint files). V152-5 (`config.py`, `.env.example`, its own test) is parallel with V152-2..V152-4. Full edge list: the index.

# Phase M0 — production measurement

### Task V152-1: M0: production volume measurement (read-only)

**Model:** sonnet — a read-only production query and a short results note; judgement only in stating the caveats.

**Files:**
- Create: `docs/superpowers/results/<run-date>-v152-notify-cooldown-volume.md` (`<run-date>` = the date the query runs, `YYYY-MM-DD`)

**Interfaces:**
- Consumes: production `plans` through `PlanStore().all()` inside the bot container (`swingbot/core/planning/plan_store.py`), the `status_history` entries written by `record_transition` (`plan_types.py:200-207`: `{"status", "reason", "at"}`), `plan.origin` (v144; `None` = the regular lane).
- Produces: no code. Two figures in the results note, which V152-17 must not merge without: **D1** messages/week per notify event (`near_stop` upper bound, `tp1`, `tp2`, `stopped`, `expired`, `closed_other`), **D3** scheduled alert posts/week before vs after a 24 h `(ticker, direction, horizon_key)` cooldown.

**Read-only.** This task changes nothing on production: no `.env` edit, no restart, no write. It does not need `mirror-prod`. The controller may route it to the `prod-inspector` agent with the script below verbatim. Always connect with `scripts/ops/ssh-hetzner.sh` (never raw `ssh`).

- [ ] **Step 1: Confirm the bot container is up**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps bot"
```

Expected: one `bot` row with `Up` in its status. If it is not up, stop and report — do not start it.

- [ ] **Step 2: Run the measurement script (stdin, no file on the VM)**

The mapping mirrors the spec's D1 event table (index decision 9 and spec § D1 "Events"): `PARTIAL` → `tp1`; `CLOSED` reason `win` → `tp1`, `tp1_runner_tp2` → `tp2`, a `_STOPPED_REASONS` member (`loss`, `scratch`, `tp1_runner_be`, `tp1_runner_trail`) → `stopped`, any other `CLOSED` reason → `closed_other`; `CANCELLED` reason `invalidated` / `risk_cap` → `closed_other`, any other `CANCELLED` reason (`expired`, the v144 session-window reasons) → `expired`. Dedupe is per `(plan_id, notify event)`, as the `plan_notifications` claim does. `near_stop` cannot be measured from `plans` (no price path is stored), so the script reports its structural upper bound: plans that reached `ACTIVE`, at most one `near_stop` each. `closed_other` is reported unconditionally; after launch it posts only for plans with a Following follower, so the live figure will be lower.

The D3 estimate takes regular-lane plans (`origin is None`) in creation order and holds a plan when a plan with the same `(ticker, direction, horizon_key)` was *posted* (not itself held) less than 24 h before it, which is the rule `cooldown.suppressed` applies (index decision 4).

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" <<'PY'
"""v152 M0 -- read-only: D1 notify volume, D3 cooldown estimate, last 4 weeks."""
import collections
import datetime as dt

from swingbot.core.planning.plan_store import PlanStore

WEEKS = 4
NOW = dt.datetime.now(dt.timezone.utc)
SINCE = NOW - dt.timedelta(weeks=WEEKS)
WINDOW = dt.timedelta(hours=24)
STOPPED = {"loss", "scratch", "tp1_runner_be", "tp1_runner_trail"}
CANCEL_OTHER = {"invalidated", "risk_cap"}
CLOSED_BY_REASON = {"win": "tp1", "tp1_runner_tp2": "tp2"}


def ts(raw):
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def closed_event(reason):
    if reason in STOPPED:
        return "stopped"
    return CLOSED_BY_REASON.get(reason, "closed_other")


def notify_event(entry):
    status, reason = entry.get("status"), entry.get("reason")
    if status == "PARTIAL":
        return "tp1"
    if status == "CLOSED":
        return closed_event(reason)
    if status == "CANCELLED":
        return "closed_other" if reason in CANCEL_OTHER else "expired"
    return None


plans = PlanStore().all()
created = [ts(p.created_at) for p in plans if ts(p.created_at)]
print(f"plans in store: {len(plans)}; oldest created_at: {min(created) if created else None}")
print(f"window: {SINCE.isoformat()} .. {NOW.isoformat()} ({WEEKS} weeks)")

claims, fills, missing_at = set(), set(), 0
for plan in plans:
    for entry in plan.status_history or []:
        at = ts(entry.get("at"))
        if at is None:
            missing_at += 1
            continue
        if at < SINCE:
            continue
        if entry.get("status") == "ACTIVE":
            fills.add(plan.plan_id)
        event = notify_event(entry)
        if event is not None:
            claims.add((plan.plan_id, event))

per_event = collections.Counter(event for _, event in claims)
print(f"status_history entries without a usable 'at': {missing_at}")
print("D1 messages/week per notify event:")
print(f"  near_stop  <= {len(fills) / WEEKS:.1f}  (upper bound: plans filled)")
for event in ("tp1", "tp2", "stopped", "expired", "closed_other"):
    print(f"  {event:<12} {per_event[event] / WEEKS:.1f}  (n={per_event[event]})")
total = len(fills) + sum(per_event.values())
print(f"  all events <= {total / WEEKS:.1f}/week")

regular = sorted((p for p in plans if getattr(p, "origin", None) is None
                  and ts(p.created_at) and ts(p.created_at) >= SINCE),
                 key=lambda p: ts(p.created_at))
date_only = sum(1 for p in regular if len(str(p.created_at)) <= 10)
last_posted, held = {}, []
for plan in regular:
    key = (plan.ticker, plan.direction, plan.horizon_key)
    at = ts(plan.created_at)
    previous = last_posted.get(key)
    if previous is not None and at - previous < WINDOW:
        held.append(key)
        continue
    last_posted[key] = at
posted = len(regular) - len(held)
print("D3 scheduled alert posts/week (regular-lane plans):")
print(f"  before: {len(regular) / WEEKS:.1f}/week (n={len(regular)})")
print(f"  after a 24 h cooldown: {posted / WEEKS:.1f}/week (held n={len(held)})")
print(f"  regular plans with a date-only created_at: {date_only}")
print(f"  most-held keys: {collections.Counter(held).most_common(5)}")
PY
```

Expected: the printed block, no traceback. If `PlanStore` raises, report the traceback and stop — never retry with a write.

- [ ] **Step 3: Write the results note**

Create `docs/superpowers/results/<run-date>-v152-notify-cooldown-volume.md` with the figures from Step 2 copied verbatim (no rounding beyond the script's one decimal). Structure:

```markdown
# v152 M0 — notify volume and cooldown estimate (production, read-only)

**Run:** <run-date>, `PlanStore().all()` on the Hetzner bot container, window <SINCE> .. <NOW> (4 weeks).
**Plan:** [v152 index](../plans/2026-10-10-v152-discord-notify-taken-cooldown_0-index.md), task V152-1.

## D1 — notify channel, messages/week per event

| Event | Messages/week | n (4 weeks) | Note |
|---|---|---|---|
| near_stop | ≤ x.x | | upper bound: plans filled; fires only in the regular session, once per plan |
| tp1 | | | PARTIAL, or CLOSED `win` (no-TP2 plan) |
| tp2 | | | CLOSED `tp1_runner_tp2` |
| stopped | | | CLOSED in `_STOPPED_REASONS` |
| expired | | | CANCELLED other than invalidated / risk_cap |
| closed_other | | | measured unconditionally; live posts only with a Following follower |
| **all** | ≤ | | structural bound: ≤ 3 per filled plan + 1 per expired plan |

## D3 — scheduled alert posts/week, 24 h `(ticker, direction, horizon_key)` cooldown

| | Posts/week | n (4 weeks) |
|---|---|---|
| before (regular-lane plans) | | |
| after the cooldown | | |
| held | | |

Most-held keys: (from the script).

## Caveats

- Plans pruned before the window start are not counted (oldest `created_at` in store: …).
- `origin is None` is the regular lane; it includes plans created by the admin-UI-triggered scan and `!check` if those persist plans, which the live rule never suppresses — the "after" figure is a lower bound on posts.
- `created_at` date-only rows (count from the script) make the 24 h window coarse for those plans.
- After launch `alert_posts` measures D3 directly (`outcome = 'suppressed'`).
```

Fill every cell from the Step 2 output; write each caveat with its printed count. No cell stays empty: a figure the script did not print is written as "not measured" with the reason.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<run-date>-v152-notify-cooldown-volume.md
git commit -m "docs(v152): M0 notify volume and cooldown estimate from production (read-only)"
```

# Phase F — foundation

### Task V152-2: Four tables + revision `v152_001`

**Model:** opus — a DDL revision that must equal `schema.py` exactly, with a downgrade, cascades and a schema-contract surface several tests pin.

**Files:**
- Modify: `swingbot/core/db/schema.py` (four tables after `dropped_doc_fields` at :202-209; four `PROMOTION_REASONS` entries and the `plans.plan_id` reason at :217-291)
- Create: `swingbot/core/db/migrations/versions/v152_001_follow_notify_cooldown.py`
- Create: `tests/db/test_v152_tables.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (four `CASES` entries; the FK seeding generalised)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `METADATA`, the `plans.plan_id` unique column (FK target, as `starred_plans` uses it at :113-117); Alembic head HEAD = the single id `python -m alembic heads` prints at implementation time (`v144_001` on 2026-10-10; `v146_001`/`v147_001` if those merged first; index decision 1).
- Produces (V152-3 and V152-4 consume):
  - `schema.plan_followers`: `id` BIGINT PK, `plan_id` TEXT NOT NULL FK `plans.plan_id` ON DELETE CASCADE, `user_id` BIGINT NOT NULL, `kind` TEXT NOT NULL, `doc`, `updated_at`; `UniqueConstraint("plan_id", "user_id", "kind", name="plan_followers_row_uq")`; `Index("plan_followers_plan_idx", "plan_id")`. Promoted `("plan_id", "user_id", "kind")`.
  - `schema.plan_notifications`: `id`, `plan_id` TEXT NOT NULL FK cascade, `event` TEXT NOT NULL, `state` TEXT NOT NULL, `doc`, `updated_at`; `UniqueConstraint("plan_id", "event", name="plan_notifications_claim_uq")`; `Index("plan_notifications_state_idx", "state")`. Promoted `("plan_id", "event", "state")`.
  - `schema.notify_prefs`: `id`, `user_id` BIGINT NOT NULL UNIQUE, `doc`, `updated_at`. Promoted `("user_id",)`.
  - `schema.alert_posts`: `id`, `ticker` TEXT NOT NULL, `at` TIMESTAMPTZ NOT NULL, `outcome` TEXT NOT NULL, `doc`, `updated_at`; `Index("alert_posts_ticker_at_idx", "ticker", "at")` only (spec § Schema "Index choice"). Promoted `("ticker", "at", "outcome")`.
  - Alembic revision `v152_001`, `down_revision` = HEAD (Step 1); `downgrade()` drops the four tables.
- **Insertion points (audit 2026-10-10, order-independent):** if another plan's table already follows `dropped_doc_fields` in `schema.py`, insert the four tables after that table instead; if another plan's `PROMOTION_REASONS` entry already ends the dict (after `dropped_doc_fields`), add the four entries after it; if another plan's `CASES` entry already follows `market_data_state` in `tests/db/test_unknown_field_round_trip.py`, add the four entries after it. Keep every entry other plans added.
- None of the four tables gets a NOTIFY trigger or a `events.TABLE_CHANNELS` entry: nothing in the SPA streams them (`dropped_doc_fields` is the precedent for a trigger-less table; `tests/db/test_trigger_coverage.py` checks only mapped tables).

- [ ] **Step 1: Write the failing tests**

First run `python -m alembic heads` and call the single id it prints HEAD (`v144_001` on 2026-10-10; `v146_001` or `v147_001` if those plans merged first). Two heads printed → stop and ask the partner; never pick one.

Create `tests/db/test_v152_tables.py`:

```python
"""v152: plan_followers, plan_notifications, notify_prefs, alert_posts, revision v152_001.

Followers and notification claims cascade with their plan (spec § Schema); the
user ids are Discord snowflakes, which overflow a 32-bit integer."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import schema
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.plans import PlanRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
TS = "2026-10-10T14:00:00+00:00"
SNOWFLAKE = 123456789012345678
V152_TABLES = ("plan_followers", "plan_notifications", "notify_prefs", "alert_posts")
EXPECTED_PROMOTED = {
    "plan_followers": ("plan_id", "user_id", "kind"),
    "plan_notifications": ("plan_id", "event", "state"),
    "notify_prefs": ("user_id",),
    "alert_posts": ("ticker", "at", "outcome"),
}


def _plan(plan_id="P1"):
    return {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "status": "PENDING", "created_at": TS}


def _generic(name):
    return Repository(schema.METADATA.tables[name], key="id")


def _index_columns(name):
    return {index.name: [column.name for column in index.columns]
            for index in schema.METADATA.tables[name].indexes}


def _unique_constraints(name):
    return {constraint.name: [column.name for column in constraint.columns]
            for constraint in schema.METADATA.tables[name].constraints
            if isinstance(constraint, sa.UniqueConstraint)}


@pytest.mark.parametrize("name", V152_TABLES)
def test_each_table_is_registered_with_its_promoted_columns_and_reasons(name):
    table = schema.METADATA.tables[name]
    assert schema.promoted_for(name) == EXPECTED_PROMOTED[name]
    assert set(schema.PROMOTION_REASONS[name]) == set(EXPECTED_PROMOTED[name])
    assert schema.contract_violations(table) == []
    for column in EXPECTED_PROMOTED[name]:
        assert table.c[column].nullable is False, (name, column)


def test_the_natural_keys_and_indexes_are_declared():
    assert _unique_constraints("plan_followers")["plan_followers_row_uq"] == [
        "plan_id", "user_id", "kind"]
    assert _index_columns("plan_followers")["plan_followers_plan_idx"] == ["plan_id"]
    assert _unique_constraints("plan_notifications")["plan_notifications_claim_uq"] == [
        "plan_id", "event"]
    assert _index_columns("plan_notifications")["plan_notifications_state_idx"] == ["state"]
    assert schema.notify_prefs.c.user_id.unique is True
    assert _index_columns("alert_posts") == {"alert_posts_ticker_at_idx": ["ticker", "at"]}
    assert schema.alert_posts.c.at.type.timezone is True


def test_discord_user_ids_are_bigint():
    assert isinstance(schema.plan_followers.c.user_id.type, sa.BigInteger)
    assert isinstance(schema.notify_prefs.c.user_id.type, sa.BigInteger)


@pytest.mark.parametrize("name", ["plan_followers", "plan_notifications"])
def test_the_plan_id_foreign_key_cascades(name):
    (fk,) = schema.METADATA.tables[name].c.plan_id.foreign_keys
    assert fk.target_fullname == "plans.plan_id"
    assert fk.ondelete == "CASCADE"


def test_followers_and_claims_go_with_their_plan(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    _generic("plan_followers").insert(
        {"plan_id": "P1", "user_id": SNOWFLAKE, "kind": "taken"}, conn=db_conn)
    _generic("plan_notifications").insert(
        {"plan_id": "P1", "event": "tp1", "state": "pending"}, conn=db_conn)
    PlanRepository().delete("P1", conn=db_conn)
    assert _generic("plan_followers").count(conn=db_conn) == 0
    assert _generic("plan_notifications").count(conn=db_conn) == 0


def test_a_follower_of_a_missing_plan_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        _generic("plan_followers").insert(
            {"plan_id": "GHOST", "user_id": SNOWFLAKE, "kind": "watch"}, conn=db_conn)


def test_one_claim_per_plan_and_event(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    claims = _generic("plan_notifications")
    claims.insert({"plan_id": "P1", "event": "tp1", "state": "pending"}, conn=db_conn)
    with pytest.raises(sa.exc.IntegrityError):
        claims.insert({"plan_id": "P1", "event": "tp1", "state": "sent"}, conn=db_conn)


def test_an_alert_post_row_round_trips_its_doc(db_conn):
    posts = _generic("alert_posts")
    posts.insert({"ticker": "AAPL", "at": TS, "outcome": "posted", "direction": "bullish",
                  "horizon_key": "2w", "plan_id": "P1"}, conn=db_conn)
    (row,) = posts.list_all(conn=db_conn)
    assert (row["ticker"], row["outcome"], row["direction"], row["horizon_key"]) == (
        "AAPL", "posted", "bullish", "2w")


def test_v152_001_sits_on_the_single_prior_head():
    s = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    rev = s.get_revision("v152_001")
    assert s.get_revision(rev.down_revision) is not None and s.get_heads() == ["v152_001"]


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v152_001_downgrade_drops_the_four_tables_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert set(V152_TABLES) <= _tables(connection)
        downgrade(cfg, "-1")
        remaining = _tables(connection)
        assert not set(V152_TABLES) & remaining
        assert "plans" in remaining and "starred_plans" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert set(V152_TABLES) <= _tables(connection)
```

The downgrade test lives here rather than in `tests/db/test_migrations.py` (the spec's wording): that file pins graph-wide invariants, and this revision's round trip is v152's own. `test_migrations_produce_exactly_the_declared_schema` in that file still checks the upgrade against `schema.py` unchanged.

Modify `tests/db/test_unknown_field_round_trip.py`. Add the import beside the other repository imports:

```python
from swingbot.core.db.repositories.base import Repository
```

Add these four entries at the end of `CASES` (after `"market_data_state"`, or after another plan's entry that already follows it):

```python
    # v152: the base surrogate-keyed Repository over each new table. The
    # V152-3/V152-4 classes subclass it; the property under test is the base
    # insert/list path every one of them reads back through.
    "plan_followers": (lambda: Repository(schema.plan_followers, key="id"),
                       {"plan_id": "P-probe", "user_id": 123456789012345678, "kind": "watch"}),
    "plan_notifications": (lambda: Repository(schema.plan_notifications, key="id"),
                           {"plan_id": "P-probe", "event": "tp1", "state": "pending"}),
    "notify_prefs": (lambda: Repository(schema.notify_prefs, key="id"),
                     {"user_id": 123456789012345678}),
    "alert_posts": (lambda: Repository(schema.alert_posts, key="id"),
                    {"ticker": "AAPL", "at": TS, "outcome": "posted"}),
```

Below `NOT_REPOSITORY_BACKED`, add:

```python
#: Tables whose rows need the probe plan first (a foreign key into plans).
NEEDS_PLAN = {"starred_plans", "plan_followers", "plan_notifications"}
```

and in `test_an_unseen_field_round_trips_unchanged` replace

```python
    if table == "starred_plans":
        PlanRepository().upsert(dict(PLAN), conn=db_conn)   # its foreign key
```

with

```python
    if table in NEEDS_PLAN:
        PlanRepository().upsert(dict(PLAN), conn=db_conn)   # its foreign key
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v152_tables.py`
Expected: FAIL — `KeyError: 'plan_followers'` (the tables do not exist in `schema.METADATA` yet).

- [ ] **Step 3: Declare the four tables in `schema.py`**

In `swingbot/core/db/schema.py`, insert after the `dropped_doc_fields = register(...)` block (ends at :209) — or after another plan's table that already follows it — and before the `#: Why each promoted column ...` comment:

```python
# v152 D1-D3: who follows a plan (Watch / Following), the notify channel's
# one-message-per-(plan, event) claim with its retry state, each Discord
# user's /notify settings, and the scheduled scan's alert-post record the
# per-symbol cooldown reads. Followers and claims cascade with their plan;
# the trade keeps its own denormalised taken_by copy (a doc field).
plan_followers = register(sa.Table(
    "plan_followers", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
              nullable=False),
    sa.Column("user_id", sa.BigInteger, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("plan_id", "user_id", "kind", name="plan_followers_row_uq"),
    sa.Index("plan_followers_plan_idx", "plan_id"),
), ("plan_id", "user_id", "kind"))

plan_notifications = register(sa.Table(
    "plan_notifications", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, sa.ForeignKey("plans.plan_id", ondelete="CASCADE"),
              nullable=False),
    sa.Column("event", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    *standard_columns(),
    sa.UniqueConstraint("plan_id", "event", name="plan_notifications_claim_uq"),
    sa.Index("plan_notifications_state_idx", "state"),
), ("plan_id", "event", "state"))

notify_prefs = register(sa.Table(
    "notify_prefs", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("user_id", sa.BigInteger, nullable=False, unique=True),
    *standard_columns(),
), ("user_id",))

alert_posts = register(sa.Table(
    "alert_posts", METADATA, sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("ticker", sa.Text, nullable=False),
    sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("outcome", sa.Text, nullable=False),
    *standard_columns(),
    sa.Index("alert_posts_ticker_at_idx", "ticker", "at"),
), ("ticker", "at", "outcome"))
```

In `PROMOTION_REASONS`, change the `plans` → `plan_id` line to:

```python
        "plan_id": "natural key; foreign-key target of starred_plans, plan_followers, plan_notifications",
```

and add after the `"dropped_doc_fields": {...},` entry — or after another plan's entry that already follows it — (before the closing `}` at :291):

```python
    "plan_followers": {
        "plan_id": "cascading foreign key into plans; plan_followers_plan_idx lookup by plan",
        "user_id": "part of the plan_followers_row_uq natural key; the Discord user",
        "kind": "part of the natural key; watch vs taken filter",
    },
    "plan_notifications": {
        "plan_id": "cascading foreign key into plans; half of the claim key",
        "event": "other half of plan_notifications_claim_uq, the idempotency claim",
        "state": "plan_notifications_state_idx; the retry sweep's state='pending' filter",
    },
    "notify_prefs": {"user_id": "natural key; one row per Discord user"},
    "alert_posts": {
        "ticker": "alert_posts_ticker_at_idx; the per-ticker cooldown window lookup",
        "at": "alert_posts_ticker_at_idx; window, digest count and prune by time; NOT NULL",
        "outcome": "posted vs suppressed; only posted rows open a cooldown window",
    },
```

(Every reason is one line, ≤ 100 characters — `test_every_promoted_column_has_exactly_one_one_line_reason` enforces it.)

- [ ] **Step 4: Run the declaration tests**

Run: `python scripts/dev/testrun.py file tests/db/test_v152_tables.py`
Expected: the metadata tests and the `db_conn` tests PASS (the session `db_engine` builds from `METADATA.create_all`); `test_v152_001_sits_on_the_single_prior_head` and the downgrade test FAIL (`v152_001` does not exist). If Postgres is unreachable every DB test is skipped with "Start it with: docker compose --profile test up -d db-test" — start it and re-run; a skip is not a pass.

- [ ] **Step 5: Write the revision**

Create `swingbot/core/db/migrations/versions/v152_001_follow_notify_cooldown.py`:

```python
"""plan_followers, plan_notifications, notify_prefs, alert_posts (v152 D1-D3)

Four new hybrid tables, no change to an existing one. No NOTIFY trigger: the
SPA streams none of them. The downgrade drops all four; the followers record
and the notification claims go with them (trade taken_by stays in trades.doc).

Revision ID: v152_001
Revises: <HEAD>
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v152_001"
down_revision = "<HEAD>"  # replace with the id Step 1 printed, e.g. "v144_001"
branch_labels = None
depends_on = None

_TABLES = ("plan_followers", "plan_notifications", "notify_prefs", "alert_posts")


def _std():
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def _plan_fk():
    return sa.ForeignKeyConstraint(["plan_id"], ["plans.plan_id"], ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "plan_followers",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        *_std(),
        _plan_fk(),
        sa.UniqueConstraint("plan_id", "user_id", "kind", name="plan_followers_row_uq"),
    )
    op.create_index("plan_followers_plan_idx", "plan_followers", ["plan_id"])
    op.create_table(
        "plan_notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        *_std(),
        _plan_fk(),
        sa.UniqueConstraint("plan_id", "event", name="plan_notifications_claim_uq"),
    )
    op.create_index("plan_notifications_state_idx", "plan_notifications", ["state"])
    op.create_table(
        "notify_prefs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False, unique=True),
        *_std(),
    )
    op.create_table(
        "alert_posts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        *_std(),
    )
    op.create_index("alert_posts_ticker_at_idx", "alert_posts", ["ticker", "at"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)    # drops its indexes and constraints with it
```

- [ ] **Step 6: Run the new tests and the schema/migration guards**

Run: `python scripts/dev/testrun.py file tests/db/test_v152_tables.py`
Expected: PASS (all tests).

Run: `python scripts/dev/testrun.py file tests/db/test_migrations.py`
Expected: PASS — in particular `test_exactly_one_head` (head is now `v152_001`) and `test_migrations_produce_exactly_the_declared_schema` (an empty diff; a reported `add_fk`/`remove_fk` or index item means the revision and `schema.py` disagree — fix the revision, not the test).

Run: `python scripts/dev/testrun.py file tests/db/test_schema_contract.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: PASS, including the four new parametrised cases and `test_every_table_is_covered_or_excused`.

Run: `python scripts/dev/testrun.py file tests/db/test_schema.py`
Expected: PASS (`METADATA.tables == PROMOTED`).

Run: `python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py`
Expected: PASS (no new mapped table, so no new trigger is expected).

- [ ] **Step 7: Confirm the head and complexity**

Run: `python -m alembic heads`
Expected: `v152_001 (head)`.

Run: `pip install radon >/dev/null 2>&1; python -m radon cc -s -n C swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v152_001_follow_notify_cooldown.py`
Expected: no output (nothing at C or worse).

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v152_001_follow_notify_cooldown.py tests/db/test_v152_tables.py tests/db/test_unknown_field_round_trip.py
git commit -m "feat(v152): plan_followers, plan_notifications, notify_prefs, alert_posts + v152_001"
```

### Task V152-3: Repositories: followers + notify prefs

**Model:** sonnet — two small repositories with composite-key SQL on the base class; the contract is fixed by the ledger.

**Files:**
- Create: `swingbot/core/db/repositories/followers.py`
- Create: `swingbot/core/db/repositories/notify_prefs.py`
- Create: `tests/db/test_followers_prefs_repos.py`

**Interfaces:**
- Consumes: `schema.plan_followers`, `schema.notify_prefs` (V152-2); `Repository` (`base.py`: `_tx`, `_values`, `list_all`); `codec.RESERVED_KEYS`.
- Produces (V152-8, V152-17, V152-19 consume; index decisions 2, 3, 9):
  - `followers.FOLLOW_KINDS = ("watch", "taken")`
  - `followers_repo() -> FollowersRepository` (module singleton, as `starred_repo()`), with
    - `add(plan_id: str, user_id: int, kind: str, *, status_at_press: str, conn=None) -> bool` — True when a row was inserted, False when it already existed (`ON CONFLICT DO NOTHING` on `plan_followers_row_uq`); doc `{"at": <UTC ISO>, "status_at_press": status_at_press}`.
    - `remove(plan_id: str, user_id: int, kind: str, *, conn=None) -> bool` — True when a row was deleted.
    - `has(plan_id: str, user_id: int, kind: str, *, conn=None) -> bool`
    - `user_ids(plan_id: str, kinds: Iterable[str], *, conn=None) -> list[int]` — sorted, unique.
    - `followers(plan_id: str, *, conn=None) -> dict[int, frozenset[str]]` — user id → the kinds that user holds on the plan.
    - A `kind` outside `FOLLOW_KINDS` raises `ValueError` before any SQL.
  - `notify_prefs_repo() -> NotifyPrefsRepository`, with
    - `prefs(user_id: int, *, conn=None) -> dict` — the flat doc, `{}` when the user never set anything.
    - `prefs_many(user_ids: Iterable[int], *, conn=None) -> dict[int, dict]` — one entry per requested id, `{}` for a user with no row.
    - `set_pref(user_id: int, key: str, value: bool | str, *, conn=None) -> None` — upsert that merges `{key: value}` into the doc with JSONB `||` (no read-modify-write). A reserved/empty key raises `ValueError`; a value that is not `bool`/`str` raises `TypeError`. The repository does not know the event names: `/notify` (V152-19) validates `key` against `follow_notify.NOTIFY_EVENTS` + `"watch_mode"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_followers_prefs_repos.py`:

```python
"""v152: plan_followers and notify_prefs repositories (real Postgres, rolled back)."""
import pytest

from swingbot.core.db.repositories.followers import (
    FOLLOW_KINDS, FollowersRepository, followers_repo)
from swingbot.core.db.repositories.notify_prefs import NotifyPrefsRepository, notify_prefs_repo
from swingbot.core.db.repositories.plans import PlanRepository

ALICE, BOB = 111111111111111111, 222222222222222222


def _plan(db_conn, plan_id="P1"):
    PlanRepository().insert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "PENDING",
                             "created_at": "2026-10-10T14:00:00+00:00"}, conn=db_conn)


def test_the_two_kinds_are_watch_and_taken():
    assert FOLLOW_KINDS == ("watch", "taken")


def test_singletons_are_stable():
    assert followers_repo() is followers_repo()
    assert notify_prefs_repo() is notify_prefs_repo()


def test_add_is_idempotent_and_reports_whether_it_inserted(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    assert repo.add("P1", ALICE, "taken", status_at_press="PENDING", conn=db_conn) is True
    assert repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn) is False
    (row,) = repo.list_all(conn=db_conn)
    assert row["status_at_press"] == "PENDING"      # the first press is kept
    assert row["at"].endswith("+00:00")


def test_has_and_remove_are_per_user_and_per_kind(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    repo.add("P1", ALICE, "watch", status_at_press="PENDING", conn=db_conn)
    assert repo.has("P1", ALICE, "watch", conn=db_conn) is True
    assert repo.has("P1", ALICE, "taken", conn=db_conn) is False
    assert repo.has("P1", BOB, "watch", conn=db_conn) is False
    assert repo.remove("P1", BOB, "watch", conn=db_conn) is False
    assert repo.remove("P1", ALICE, "watch", conn=db_conn) is True
    assert repo.has("P1", ALICE, "watch", conn=db_conn) is False


def test_user_ids_filters_by_kind_sorted_and_unique(db_conn):
    _plan(db_conn)
    _plan(db_conn, "P2")
    repo = FollowersRepository()
    repo.add("P1", BOB, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "watch", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P2", BOB, "watch", status_at_press="ACTIVE", conn=db_conn)
    assert repo.user_ids("P1", ("taken",), conn=db_conn) == [ALICE, BOB]
    assert repo.user_ids("P1", ("watch",), conn=db_conn) == [ALICE]
    assert repo.user_ids("P1", FOLLOW_KINDS, conn=db_conn) == [ALICE, BOB]
    assert repo.user_ids("P1", (), conn=db_conn) == []
    assert repo.user_ids("P3", FOLLOW_KINDS, conn=db_conn) == []


def test_followers_maps_each_user_to_their_kinds(db_conn):
    _plan(db_conn)
    repo = FollowersRepository()
    repo.add("P1", ALICE, "taken", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", ALICE, "watch", status_at_press="ACTIVE", conn=db_conn)
    repo.add("P1", BOB, "watch", status_at_press="ACTIVE", conn=db_conn)
    assert repo.followers("P1", conn=db_conn) == {
        ALICE: frozenset({"taken", "watch"}), BOB: frozenset({"watch"})}
    assert repo.followers("NONE", conn=db_conn) == {}


@pytest.mark.parametrize("call", [
    lambda r: r.add("P1", ALICE, "fill", status_at_press="ACTIVE"),
    lambda r: r.remove("P1", ALICE, "fill"),
    lambda r: r.has("P1", ALICE, "fill"),
    lambda r: r.user_ids("P1", ("watch", "fill")),
])
def test_an_unknown_kind_is_rejected_before_any_sql(call):
    with pytest.raises(ValueError, match="fill"):
        call(FollowersRepository())


def test_prefs_are_empty_until_set(db_conn):
    assert NotifyPrefsRepository().prefs(ALICE, conn=db_conn) == {}


def test_set_pref_merges_keys_and_overwrites_one(db_conn):
    repo = NotifyPrefsRepository()
    repo.set_pref(ALICE, "near_stop", True, conn=db_conn)
    repo.set_pref(ALICE, "watch_mode", "silent", conn=db_conn)
    repo.set_pref(ALICE, "near_stop", False, conn=db_conn)
    assert repo.prefs(ALICE, conn=db_conn) == {"near_stop": False, "watch_mode": "silent"}
    assert repo.count(conn=db_conn) == 1


def test_prefs_many_answers_every_requested_user(db_conn):
    repo = NotifyPrefsRepository()
    repo.set_pref(BOB, "tp1", False, conn=db_conn)
    assert repo.prefs_many([ALICE, BOB, BOB], conn=db_conn) == {ALICE: {}, BOB: {"tp1": False}}
    assert repo.prefs_many([], conn=db_conn) == {}


@pytest.mark.parametrize("key", ["", "id", "doc", "updated_at", "user_id"])
def test_a_reserved_or_empty_key_is_rejected(key):
    with pytest.raises(ValueError):
        NotifyPrefsRepository().set_pref(ALICE, key, True)


@pytest.mark.parametrize("value", [1, None, 0.5, ["x"]])
def test_a_value_must_be_bool_or_str(value):
    with pytest.raises(TypeError):
        NotifyPrefsRepository().set_pref(ALICE, "tp1", value)
```

(`1` is rejected even though `bool` subclasses `int`: the check is `isinstance(value, (bool, str))`, and `1` is not a `bool`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_followers_prefs_repos.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.followers'`.

- [ ] **Step 3: Write `followers.py`**

Create `swingbot/core/db/repositories/followers.py`:

```python
"""v152 D2: who follows a plan -- one row per (plan_id, user_id, kind).

`watch` is the per-user Watch button; `taken` is the Following button, which
records intent to follow the plan, never a fill. The natural key is composite,
so the writes are their own SQL rather than the single-key Repository.upsert.
Callers on the Discord event loop wrap every method in asyncio.to_thread."""
from __future__ import annotations

import datetime as dt
from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plan_followers

FOLLOW_KINDS = ("watch", "taken")


def _check_kind(kind: str) -> str:
    if kind not in FOLLOW_KINDS:
        raise ValueError(f"unknown follower kind {kind!r}; expected one of {FOLLOW_KINDS}")
    return kind


class FollowersRepository(Repository):
    def __init__(self):
        super().__init__(plan_followers, key="id")

    def _row(self, plan_id: str, user_id: int, kind: str):
        c = self.table.c
        return sa.and_(c.plan_id == plan_id, c.user_id == int(user_id),
                       c.kind == _check_kind(kind))

    def add(self, plan_id: str, user_id: int, kind: str, *, status_at_press: str,
            conn=None) -> bool:
        record = {"plan_id": plan_id, "user_id": int(user_id), "kind": _check_kind(kind),
                  "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "status_at_press": status_at_press}
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint="plan_followers_row_uq"))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def remove(self, plan_id: str, user_id: int, kind: str, *, conn=None) -> bool:
        statement = sa.delete(self.table).where(self._row(plan_id, user_id, kind))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def has(self, plan_id: str, user_id: int, kind: str, *, conn=None) -> bool:
        statement = (sa.select(self.table.c.id)
                     .where(self._row(plan_id, user_id, kind)).limit(1))
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def user_ids(self, plan_id: str, kinds: Iterable[str], *, conn=None) -> list[int]:
        wanted = tuple(_check_kind(kind) for kind in kinds)
        if not wanted:
            return []
        c = self.table.c
        statement = (sa.select(c.user_id).where(c.plan_id == plan_id, c.kind.in_(wanted))
                     .distinct().order_by(c.user_id))
        with self._tx(conn) as connection:
            return [int(user_id) for user_id in connection.execute(statement).scalars()]

    def followers(self, plan_id: str, *, conn=None) -> dict[int, frozenset[str]]:
        c = self.table.c
        statement = sa.select(c.user_id, c.kind).where(c.plan_id == plan_id)
        kinds: dict[int, set[str]] = {}
        with self._tx(conn) as connection:
            for user_id, kind in connection.execute(statement).all():
                kinds.setdefault(int(user_id), set()).add(kind)
        return {user_id: frozenset(held) for user_id, held in sorted(kinds.items())}


_repo: FollowersRepository | None = None


def followers_repo() -> FollowersRepository:
    global _repo
    if _repo is None:
        _repo = FollowersRepository()
    return _repo
```

- [ ] **Step 4: Write `notify_prefs.py`**

Create `swingbot/core/db/repositories/notify_prefs.py`:

```python
"""v152 D1: each Discord user's /notify settings -- one flat doc per user.

The doc holds one boolean per notify event the user toggled, plus
`watch_mode` ("mention" | "silent"); a missing key means "use the default"
(follow_notify owns the defaults and the valid names). Writes merge with
JSONB `||` inside one upsert, so two toggles never race a read-modify-write."""
from __future__ import annotations

from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import RESERVED_KEYS
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import notify_prefs

_FORBIDDEN_KEYS = RESERVED_KEYS | {"user_id"}


class NotifyPrefsRepository(Repository):
    def __init__(self):
        super().__init__(notify_prefs, key="id")

    def prefs(self, user_id: int, *, conn=None) -> dict:
        return self.prefs_many([user_id], conn=conn)[int(user_id)]

    def prefs_many(self, user_ids: Iterable[int], *, conn=None) -> dict[int, dict]:
        ids = sorted({int(user_id) for user_id in user_ids})
        found: dict[int, dict] = {user_id: {} for user_id in ids}
        if not ids:
            return found
        c = self.table.c
        statement = sa.select(c.user_id, c.doc).where(c.user_id.in_(ids))
        with self._tx(conn) as connection:
            for user_id, doc in connection.execute(statement).all():
                found[int(user_id)] = dict(doc or {})
        return found

    def set_pref(self, user_id: int, key: str, value: bool | str, *, conn=None) -> None:
        if not key or key in _FORBIDDEN_KEYS:
            raise ValueError(f"not a preference key: {key!r}")
        if not isinstance(value, (bool, str)):
            raise TypeError(f"preference {key!r} must be bool or str, got {type(value).__name__}")
        statement = pg_insert(self.table).values(user_id=int(user_id), doc={key: value})
        statement = statement.on_conflict_do_update(
            index_elements=[self.table.c.user_id],
            set_={"doc": self.table.c.doc.op("||")(statement.excluded.doc),
                  "updated_at": sa.func.clock_timestamp()},
        )
        with self._tx(conn) as connection:
            connection.execute(statement)


_repo: NotifyPrefsRepository | None = None


def notify_prefs_repo() -> NotifyPrefsRepository:
    global _repo
    if _repo is None:
        _repo = NotifyPrefsRepository()
    return _repo
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_followers_prefs_repos.py`
Expected: PASS. A skip of the `db_conn` tests means Postgres is down (`docker compose --profile test up -d db-test`) — not a pass.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/db/repositories/followers.py swingbot/core/db/repositories/notify_prefs.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/repositories/followers.py swingbot/core/db/repositories/notify_prefs.py tests/db/test_followers_prefs_repos.py
git commit -m "feat(v152): followers and notify-prefs repositories"
```

### Task V152-4: Repositories: notification claims + alert posts

**Model:** sonnet — two repositories with conflict-free claim SQL and a database-side attempts counter; contract fixed by the ledger.

**Files:**
- Create: `swingbot/core/db/repositories/notifications.py`
- Create: `swingbot/core/db/repositories/alert_posts.py`
- Create: `tests/db/test_notifications_alert_posts_repos.py`

**Interfaces:**
- Consumes: `schema.plan_notifications`, `schema.alert_posts` (V152-2); `Repository` (`_tx`, `_values`, `list_all`, `count`, `insert`).
- Produces (V152-11 and V152-17 consume; index decisions 2, 4, 11, 12):
  - `notifications.MAX_ATTEMPTS = 5`; `notifications.STATES = ("pending", "sent", "failed")`
  - `notifications_repo() -> NotificationsRepository`, with
    - `claim(plan_id: str, event: str, doc: dict, *, conn=None) -> bool` — inserts `state='pending'` with `doc` plus `attempts: 0`; `ON CONFLICT DO NOTHING` on `plan_notifications_claim_uq`; True = this caller owns the claim. The notifier stores `{"transition": ..., "detail": {...}}` as `doc`. A plan id not in `plans` raises `IntegrityError` (FK) — the notifier claims only for plans it read from the store.
    - `mark_sent(plan_id: str, event: str, *, conn=None) -> None` — `state='sent'`, `updated_at = clock_timestamp()`.
    - `record_failure(plan_id: str, event: str, *, max_attempts: int = MAX_ATTEMPTS, conn=None) -> str` — one SQL `UPDATE ... RETURNING state` on the **pending** row: `attempts += 1` in `doc`, `state` becomes `'failed'` once `attempts >= max_attempts`, else stays `'pending'`; `updated_at` refreshed (so the 60 s retry age restarts). Returns the new state; returns `"failed"` when no pending row exists (already sent, failed, or cascaded away with its plan) — nothing is left to retry.
    - `pending_older_than(cutoff: dt.datetime, *, conn=None) -> list[dict]` — flat records (`plan_id`, `event`, `state`, plus the doc keys `transition`, `detail`, `attempts`) with `state='pending'` and `updated_at < cutoff`, oldest first.
    - `claimed_keys(*, conn=None) -> set[tuple[str, str]]` — every `(plan_id, event)`, any state (seeds the notifier's `_CLAIMED` cache).
  - `alert_posts.ALERT_OUTCOMES = ("posted", "suppressed")`
  - `alert_posts_repo() -> AlertPostsRepository`, with
    - `add(ticker: str, at: dt.datetime, outcome: str, *, direction: str, horizon_key: str, plan_id: str | None, conn=None) -> None` — append-only insert; `direction`, `horizon_key`, `plan_id` go to `doc`. `outcome` outside `ALERT_OUTCOMES` → `ValueError`; a naive `at` → `ValueError`.
    - `posted_since(ticker: str, direction: str, horizon_key: str, since: dt.datetime, *, conn=None) -> bool` — a `posted` row for the same three-part key with `at >= since` exists.
    - `count_since(outcome: str, since: dt.datetime, *, conn=None) -> int`
    - `prune_before(cutoff: dt.datetime, *, conn=None) -> int` — deletes rows with `at < cutoff`, returns how many.
  - No foreign key from `alert_posts.doc.plan_id`: posts outlive plan pruning (spec § D3 "Record").

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_notifications_alert_posts_repos.py`:

```python
"""v152: plan_notifications claims/retry state and alert_posts (real Postgres, rolled back)."""
import datetime as dt

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories.alert_posts import (
    ALERT_OUTCOMES, AlertPostsRepository, alert_posts_repo)
from swingbot.core.db.repositories.notifications import (
    MAX_ATTEMPTS, NotificationsRepository, notifications_repo)
from swingbot.core.db.repositories.plans import PlanRepository

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 2, 14, 0, tzinfo=UTC)   # well before any clock_timestamp() a run sees
DOC = {"transition": "tp1_partial", "detail": {"exit_price": 190.0, "r": 1.0}}


def _plan(db_conn, plan_id="P1"):
    PlanRepository().insert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "ACTIVE",
                             "created_at": "2026-10-10T13:00:00+00:00"}, conn=db_conn)


def _age_all_claims(db_conn, at: dt.datetime) -> None:
    db_conn.execute(sa.update(schema.plan_notifications).values(updated_at=at))


def test_constants_and_singletons():
    assert MAX_ATTEMPTS == 5
    assert ALERT_OUTCOMES == ("posted", "suppressed")
    assert notifications_repo() is notifications_repo()
    assert alert_posts_repo() is alert_posts_repo()


def test_the_first_claim_wins_and_a_second_is_refused(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    assert repo.claim("P1", "tp1", DOC, conn=db_conn) is True
    assert repo.claim("P1", "tp1", {"transition": "closed", "detail": {}}, conn=db_conn) is False
    assert repo.claim("P1", "stopped", DOC, conn=db_conn) is True
    rows = {row["event"]: row for row in repo.list_all(conn=db_conn)}
    assert rows["tp1"]["state"] == "pending"
    assert rows["tp1"]["attempts"] == 0
    assert rows["tp1"]["transition"] == "tp1_partial"      # the first claim's doc is kept
    assert rows["tp1"]["detail"] == {"exit_price": 190.0, "r": 1.0}


def test_a_claim_for_a_missing_plan_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        NotificationsRepository().claim("GHOST", "tp1", DOC, conn=db_conn)


def test_claimed_keys_cover_every_state(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.claim("P1", "near_stop", DOC, conn=db_conn)
    repo.mark_sent("P1", "tp1", conn=db_conn)
    assert repo.claimed_keys(conn=db_conn) == {("P1", "tp1"), ("P1", "near_stop")}


def test_pending_older_than_returns_old_pending_rows_only(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.claim("P1", "near_stop", DOC, conn=db_conn)
    _age_all_claims(db_conn, T0)
    repo.mark_sent("P1", "near_stop", conn=db_conn)
    assert repo.pending_older_than(T0 - dt.timedelta(seconds=1), conn=db_conn) == []
    (row,) = repo.pending_older_than(T0 + dt.timedelta(seconds=60), conn=db_conn)
    assert (row["plan_id"], row["event"], row["state"]) == ("P1", "tp1", "pending")
    assert row["transition"] == "tp1_partial" and row["attempts"] == 0


def test_record_failure_counts_attempts_and_fails_at_the_limit(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    states = [repo.record_failure("P1", "tp1", conn=db_conn) for _ in range(MAX_ATTEMPTS)]
    assert states == ["pending"] * (MAX_ATTEMPTS - 1) + ["failed"]
    (row,) = repo.list_all(conn=db_conn)
    assert (row["state"], row["attempts"]) == ("failed", MAX_ATTEMPTS)
    assert row["transition"] == "tp1_partial"                # the doc merge keeps the detail
    assert repo.record_failure("P1", "tp1", conn=db_conn) == "failed"
    (row,) = repo.list_all(conn=db_conn)
    assert row["attempts"] == MAX_ATTEMPTS                   # a failed row is never bumped


def test_record_failure_refreshes_the_retry_age(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    _age_all_claims(db_conn, T0)
    repo.record_failure("P1", "tp1", conn=db_conn)
    assert repo.pending_older_than(T0 + dt.timedelta(seconds=60), conn=db_conn) == []


def test_record_failure_on_a_sent_or_missing_row_reports_failed(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.mark_sent("P1", "tp1", conn=db_conn)
    assert repo.record_failure("P1", "tp1", conn=db_conn) == "failed"
    assert repo.record_failure("P1", "tp2", conn=db_conn) == "failed"
    (row,) = repo.list_all(conn=db_conn)
    assert row["state"] == "sent"


def test_record_failure_honours_a_custom_limit(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    assert repo.record_failure("P1", "tp1", max_attempts=1, conn=db_conn) == "failed"


def _post(repo, db_conn, at, *, ticker="AAPL", direction="bullish", horizon="2w",
          outcome="posted"):
    repo.add(ticker, at, outcome, direction=direction, horizon_key=horizon,
             plan_id=f"{ticker}-{at:%H%M}", conn=db_conn)


def test_posted_since_matches_the_full_key_inside_the_window(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0)
    since = T0 - dt.timedelta(hours=24)
    assert repo.posted_since("AAPL", "bullish", "2w", since, conn=db_conn) is True
    assert repo.posted_since("AAPL", "bearish", "2w", since, conn=db_conn) is False
    assert repo.posted_since("AAPL", "bullish", "4w", since, conn=db_conn) is False
    assert repo.posted_since("MSFT", "bullish", "2w", since, conn=db_conn) is False
    assert repo.posted_since("AAPL", "bullish", "2w", T0 + dt.timedelta(seconds=1),
                             conn=db_conn) is False


def test_a_suppressed_row_never_opens_a_window(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0, outcome="suppressed")
    assert repo.posted_since("AAPL", "bullish", "2w", T0 - dt.timedelta(hours=1),
                             conn=db_conn) is False


def test_count_since_counts_one_outcome(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0 - dt.timedelta(days=2), outcome="suppressed")
    _post(repo, db_conn, T0, outcome="suppressed")
    _post(repo, db_conn, T0, ticker="MSFT", outcome="suppressed")
    _post(repo, db_conn, T0)
    since = T0 - dt.timedelta(hours=1)
    assert repo.count_since("suppressed", since, conn=db_conn) == 2
    assert repo.count_since("posted", since, conn=db_conn) == 1


def test_prune_before_deletes_only_older_rows(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0 - dt.timedelta(days=8))
    _post(repo, db_conn, T0 - dt.timedelta(days=6), ticker="MSFT")
    assert repo.prune_before(T0 - dt.timedelta(days=7), conn=db_conn) == 1
    assert [row["ticker"] for row in repo.list_all(conn=db_conn)] == ["MSFT"]


def test_add_rejects_an_unknown_outcome_and_a_naive_time():
    repo = AlertPostsRepository()
    with pytest.raises(ValueError, match="held"):
        repo.add("AAPL", T0, "held", direction="bullish", horizon_key="2w", plan_id=None)
    with pytest.raises(ValueError, match="timezone"):
        repo.add("AAPL", T0.replace(tzinfo=None), "posted", direction="bullish",
                 horizon_key="2w", plan_id=None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_notifications_alert_posts_repos.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.alert_posts'`.

- [ ] **Step 3: Write `notifications.py`**

Create `swingbot/core/db/repositories/notifications.py`:

```python
"""v152 D1: the notify channel's one-message-per-(plan, event) claim.

A claim is inserted `pending` before the send (ON CONFLICT DO NOTHING: zero
rows = someone already claimed it), set `sent` only after Discord accepted
the message, and counted up by `record_failure` until MAX_ATTEMPTS makes it
`failed`. The attempts counter lives in `doc` and is bumped in SQL, so a
retry never reads-modifies-writes. Retries depend on this table alone."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plan_notifications

MAX_ATTEMPTS = 5
STATES = ("pending", "sent", "failed")


class NotificationsRepository(Repository):
    def __init__(self):
        super().__init__(plan_notifications, key="id")

    def _key(self, plan_id: str, event: str):
        c = self.table.c
        return sa.and_(c.plan_id == plan_id, c.event == event)

    def claim(self, plan_id: str, event: str, doc: dict, *, conn=None) -> bool:
        record = {**doc, "plan_id": plan_id, "event": event, "state": "pending",
                  "attempts": 0}
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint="plan_notifications_claim_uq"))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def mark_sent(self, plan_id: str, event: str, *, conn=None) -> None:
        statement = (sa.update(self.table).where(self._key(plan_id, event))
                     .values(state="sent", updated_at=sa.func.clock_timestamp()))
        with self._tx(conn) as connection:
            connection.execute(statement)

    def record_failure(self, plan_id: str, event: str, *, max_attempts: int = MAX_ATTEMPTS,
                       conn=None) -> str:
        c = self.table.c
        attempts = sa.func.coalesce(c.doc["attempts"].astext.cast(sa.Integer), 0) + 1
        bumped = sa.func.jsonb_build_object(sa.cast(sa.literal("attempts"), sa.Text), attempts)
        statement = (
            sa.update(self.table)
            .where(self._key(plan_id, event), c.state == "pending")
            .values(doc=c.doc.op("||")(bumped),
                    state=sa.case((attempts >= max_attempts, "failed"), else_="pending"),
                    updated_at=sa.func.clock_timestamp())
            .returning(c.state)
        )
        with self._tx(conn) as connection:
            state = connection.execute(statement).scalar_one_or_none()
        return "failed" if state is None else state

    def pending_older_than(self, cutoff: dt.datetime, *, conn=None) -> list[dict]:
        c = self.table.c
        return self.list_all(conn=conn, where=sa.and_(c.state == "pending", c.updated_at < cutoff),
                             order_by=c.updated_at)

    def claimed_keys(self, *, conn=None) -> set[tuple[str, str]]:
        c = self.table.c
        with self._tx(conn) as connection:
            return {(plan_id, event) for plan_id, event
                    in connection.execute(sa.select(c.plan_id, c.event)).all()}


_repo: NotificationsRepository | None = None


def notifications_repo() -> NotificationsRepository:
    global _repo
    if _repo is None:
        _repo = NotificationsRepository()
    return _repo
```

Both `SET` expressions read the row's *old* `doc`, so `attempts` and the `CASE` agree within the one statement. The `'attempts'` key is cast to `TEXT` because `jsonb_build_object` is variadic `"any"` and an untyped bind parameter there fails with "could not determine data type of parameter".

- [ ] **Step 4: Write `alert_posts.py`**

Create `swingbot/core/db/repositories/alert_posts.py`:

```python
"""v152 D3: the scheduled scan's alert-post record, append-only.

One row per alert the scheduled session scan posted or held: promoted
ticker/at/outcome (alert_posts_ticker_at_idx serves the per-ticker window),
doc {direction, horizon_key, plan_id}. No foreign key to plans: the record
outlives plan pruning. Tens of rows a day; cooldown.prune trims it nightly."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import alert_posts

ALERT_OUTCOMES = ("posted", "suppressed")


class AlertPostsRepository(Repository):
    def __init__(self):
        super().__init__(alert_posts, key="id")

    def add(self, ticker: str, at: dt.datetime, outcome: str, *, direction: str,
            horizon_key: str, plan_id: str | None, conn=None) -> None:
        if outcome not in ALERT_OUTCOMES:
            raise ValueError(f"unknown alert outcome {outcome!r}; expected one of {ALERT_OUTCOMES}")
        if at.tzinfo is None:
            raise ValueError("alert_posts.at needs a timezone-aware datetime")
        self.insert({"ticker": ticker, "at": at, "outcome": outcome, "direction": direction,
                     "horizon_key": horizon_key, "plan_id": plan_id}, conn=conn)

    def posted_since(self, ticker: str, direction: str, horizon_key: str,
                     since: dt.datetime, *, conn=None) -> bool:
        c = self.table.c
        statement = sa.select(c.id).where(
            c.outcome == "posted", c.ticker == ticker, c.at >= since,
            c.doc["direction"].astext == direction,
            c.doc["horizon_key"].astext == horizon_key,
        ).limit(1)
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def count_since(self, outcome: str, since: dt.datetime, *, conn=None) -> int:
        c = self.table.c
        return self.count(conn=conn, where=sa.and_(c.outcome == outcome, c.at >= since))

    def prune_before(self, cutoff: dt.datetime, *, conn=None) -> int:
        statement = sa.delete(self.table).where(self.table.c.at < cutoff)
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount


_repo: AlertPostsRepository | None = None


def alert_posts_repo() -> AlertPostsRepository:
    global _repo
    if _repo is None:
        _repo = AlertPostsRepository()
    return _repo
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_notifications_alert_posts_repos.py`
Expected: PASS. A skip of the `db_conn` tests means Postgres is down — start it, re-run.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/db/repositories/notifications.py swingbot/core/db/repositories/alert_posts.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/repositories/notifications.py swingbot/core/db/repositories/alert_posts.py tests/db/test_notifications_alert_posts_repos.py
git commit -m "feat(v152): notification-claim and alert-post repositories"
```

### Task V152-5: Config: `DISCORD_CHANNEL_NOTIFY_ID`, `ALERT_SYMBOL_COOLDOWN_HOURS`

**Model:** haiku — two `Field` entries, one search-class line, two `.env.example` blocks, tests given verbatim.

**Files:**
- Modify: `swingbot/config.py` (`FIELDS`: after `DISCORD_CHANNEL_OPS_ID` at :121-125 and after `DIGEST_MAX_PLANS` at ~:782; `_SEARCH_CLASSES["live_only"]` at :1264)
- Modify: `.env.example` (after `DISCORD_CHANNEL_OPS_ID=` at :44; after `DIGEST_MAX_PLANS=3` at ~:476)
- Create: `tests/test_config_v152_keys.py`

**Interfaces:**
- Produces (V152-11, V152-17 consume): `config.DISCORD_CHANNEL_NOTIFY_ID: str` (section "Discord Connection", default `""` = D1 off, hot-reloadable, search class `excluded`); `config.ALERT_SYMBOL_COOLDOWN_HOURS: float` (section "Discord Alerts", `type="float"`, default `"24"`, `min=0`, `0` = off, hot-reloadable, search class `live_only` — it is not a `ScanParams` knob, so `tests/infra/test_scan_params_coverage.py` stays green).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_v152_keys.py`:

```python
"""v152: DISCORD_CHANNEL_NOTIFY_ID (D1 notify channel) and ALERT_SYMBOL_COOLDOWN_HOURS (D3)."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_notify_channel_is_an_empty_hot_reloadable_connection_key():
    field = _field("DISCORD_CHANNEL_NOTIFY_ID")
    assert (field.key, field.section, field.type, field.default) == (
        "DISCORD_CHANNEL_NOTIFY_ID", "Discord Connection", "text", "")
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "not silent" in field.help.lower()


def test_notify_channel_sits_right_after_the_ops_channel():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("DISCORD_CHANNEL_NOTIFY_ID") == attrs.index("DISCORD_CHANNEL_OPS_ID") + 1


def test_cooldown_is_a_live_only_float_defaulting_to_24_hours():
    field = _field("ALERT_SYMBOL_COOLDOWN_HOURS")
    assert (field.section, field.type, field.default, field.min) == (
        "Discord Alerts", "float", "24", 0)
    assert field.hot_reloadable is True
    assert field.search_class == "live_only"
    assert config._cast(field, field.default) == 24.0
    assert config._cast(field, "0") == 0.0
    assert "ALERT_SYMBOL_COOLDOWN_HOURS" not in config.searchable_attrs()


def test_both_keys_are_module_attributes_of_the_right_type():
    assert isinstance(config.DISCORD_CHANNEL_NOTIFY_ID, str)
    assert isinstance(config.ALERT_SYMBOL_COOLDOWN_HOURS, float)


def test_env_example_lists_both_keys():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nDISCORD_CHANNEL_NOTIFY_ID=\n" in text
    assert "\nALERT_SYMBOL_COOLDOWN_HOURS=24\n" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_v152_keys.py`
Expected: FAIL — `StopIteration` from `_field("DISCORD_CHANNEL_NOTIFY_ID")`.

- [ ] **Step 3: Add the two Fields**

In `swingbot/config.py`, directly after the `Field("DISCORD_CHANNEL_OPS_ID", ...)` entry (its `help=` ends "...health notices are NOT silent."),`) and before the `# --- eToro paper trading` comment, insert:

```python
    Field("DISCORD_CHANNEL_NOTIFY_ID", "DISCORD_CHANNEL_NOTIFY_ID", "Discord Connection", "Plan-updates channel ID",
          help="Channel for factual paper-plan updates on plans people follow: near stop, TP1, TP2, "
               "stopped, expired, and closed/cancelled for Following followers only. Each message "
               "mentions the users who follow the plan (Watch or Following), so this channel is NOT "
               "silent; /notify sets each user's mentions. Empty = off: nothing is posted or recorded."),
```

Directly after the `Field("DIGEST_MAX_PLANS", ...)` entry (end of the "Discord Alerts" block, before `# --- Execution Realism`), insert:

```python
    Field("ALERT_SYMBOL_COOLDOWN_HOURS", "ALERT_SYMBOL_COOLDOWN_HOURS", "Discord Alerts",
          "Per-symbol alert cooldown (hours)",
          type="float", default="24", min=0, step=1,
          help="On the scheduled session scan only, an alert for the same ticker, direction and "
               "horizon is not posted when one was posted within this many hours. The plan is still "
               "built, managed and in the book -- only the Discord post is held, and the ops channel "
               "says how many. !check and the admin-UI scan are never held. 0 = off."),
```

In `_SEARCH_CLASSES["live_only"]`, add `"ALERT_SYMBOL_COOLDOWN_HOURS",` on the last line of the set, so it reads:

```python
        "SHORT_UNIVERSE_MAX_SYMBOLS", "SHORT_UNIVERSE_FETCH_BUDGET_SECONDS",
        "ALERT_SYMBOL_COOLDOWN_HOURS",
    },
```

`DISCORD_CHANNEL_NOTIFY_ID` stays `excluded` (the default), as every other channel id.

- [ ] **Step 4: Add the `.env.example` blocks**

In `.env.example`, after the `DISCORD_CHANNEL_OPS_ID=` line, insert:

```
# Channel for factual paper-plan updates on plans people follow (near stop,
# TP1, TP2, stopped, expired; closed/cancelled for Following only). Messages
# mention the followers, so this channel is NOT silent. Empty = off.
DISCORD_CHANNEL_NOTIFY_ID=
```

After the `DIGEST_MAX_PLANS=3` line, insert:

```
# Scheduled scan only: an alert for the same ticker, direction and horizon is
# not posted again within this many hours (the plan is still built and in the
# book). !check and the admin-UI scan are never held. 0 = off.
ALERT_SYMBOL_COOLDOWN_HOURS=24
```

Keep one blank line before each comment block, matching the surrounding entries.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_config_v152_keys.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS (both keys in the schema and in `.env.example`).

Run: `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`
Expected: PASS (`live_only` and `excluded` keys are not `ScanParams` fields).

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_v152_keys.py
git commit -m "feat(v152): DISCORD_CHANNEL_NOTIFY_ID and ALERT_SYMBOL_COOLDOWN_HOURS config keys"
```
