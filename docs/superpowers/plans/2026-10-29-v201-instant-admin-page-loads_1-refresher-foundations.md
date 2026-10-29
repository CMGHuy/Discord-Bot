# v201 Instant admin page loads, part 1: refresher foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Instant admin page loads](../specs/2026-10-29-v201-instant-admin-page-loads.md)
**Index:** [`_0-index.md`](2026-10-29-v201-instant-admin-page-loads_0-index.md): Goal, Global Constraints, Review Focus, Parallelisation and every cross-task contract (Config fields, Contract module, Tables, Repositories) live there and bind every task below.

Part scope: V201-1 … V201-5 (V201-6, the quote cycle, is in part 1b). The config/asker/session contract, the five tables, their repositories, persisted FX quote codes with never-fetch reads, the refresher process and its quote cycle. Nothing in this part changes what a page handler does; part 2 (V201-7+) switches the request path over.

`<wt>` is the implementation worktree's absolute path. Every DB-backed test needs the shared `swing-db` replica (`/replicate-prod-db`) before its first run.

# Phase 1: Contract

### Task V201-1: Config fields, `Asker.ADMIN_REFRESH`, session state, contract module, `refresher` suite

**Model:** opus — cross-cutting contract every later task imports; a wrong default or mapping silently changes freshness behaviour.

**Files:**
- Modify: `swingbot/config.py` (12 `Field`s directly after the `TAPE_PROXY_SYMBOLS` field, ~line 888; `_MODE_VALUES` ~line 1527)
- Modify: `.env.example` (12 keys directly after the `TAPE_PROXY_SYMBOLS=` line, ~line 501). Not in the ledger row, but `tests/infra/test_env_example_sync.py` fails without it.
- Modify: `swingbot/core/marketdata/shared/kinds.py` (`Asker`, `_PRIORITY`, `_QUOTE_ATTR`)
- Modify: `swingbot/core/market/session.py` (append after `is_nyse_regular_session`)
- Create: `swingbot/core/marketdata/shared/admin_refresh.py`
- Modify: `tests/suites.toml` (append `[suites.refresher]`)
- Create: `tests/refresher/__init__.py`, `tests/admin_market/__init__.py` (empty)
- Test: `tests/test_config_v201_keys.py`, `tests/refresher/test_admin_refresh_contract.py`, `tests/marketdata/test_shared_kinds.py`, `tests/marketdata/test_shared_budget.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: the index's "Config fields" and "Contract module" sections, exactly. `Asker.ADMIN_REFRESH = "admin_refresh"` (priority 5, quote window `ADMIN_REFRESH_REGULAR_S`). `session.SESSION_REGULAR = "regular"`, `SESSION_EXTENDED = "extended"`, `SESSION_CLOSED = "closed"`; `session.session_state(now: datetime | None = None) -> str`; `session.last_regular_close(now: datetime | None = None) -> datetime` (UTC-aware). Suite `refresher`.

- [ ] **Step 1: Write the failing config test** `tests/test_config_v201_keys.py`

```python
"""v201: the admin market refresher's flags and knobs (index "Config fields")."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default, min, max). Dict order is the FIELDS order.
V201_FIELDS = {
    "ADMIN_REFRESHER": ("select", "on", None, None),
    "ADMIN_REFRESH_REGULAR_S": ("number", "30", 10, 300),
    "ADMIN_REFRESH_EXTENDED_S": ("number", "300", 60, 3600),
    "ADMIN_REFRESH_CLOSED_S": ("number", "1800", 300, 7200),
    "ADMIN_REFRESH_SNAPSHOT_S": ("number", "300", 60, 3600),
    "ADMIN_REFRESH_YF_FALLBACK_CAP": ("number", "25", 0, 500),
    "ADMIN_REFRESH_MARK_TIMEOUT_S": ("number", "120", 30, 900),
    "ADMIN_REFRESH_FX_UNKNOWN_RETRY_S": ("number", "21600", 600, 604800),
    "ADMIN_STALE_PRICE_REGULAR_S": ("number", "120", 30, 1800),
    "ADMIN_STALE_PRICE_EXTENDED_S": ("number", "900", 60, 7200),
    "ADMIN_STALE_SNAPSHOT_REGULAR_S": ("number", "600", 60, 7200),
    "ADMIN_STALE_SNAPSHOT_EXTENDED_S": ("number", "1800", 300, 14400),
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_field_is_a_hot_reloadable_data_sources_knob(attr):
    field = _field(attr)
    kind, default, low, high = V201_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Data Sources", kind, default)
    assert (field.min, field.max) == (low, high)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v201" in field.help


def test_fields_sit_together_after_the_tape_proxies():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("TAPE_PROXY_SYMBOLS") + 1
    assert attrs[start:start + len(V201_FIELDS)] == list(V201_FIELDS)


def test_kill_switch_is_on_off_and_a_typo_falls_back_to_off():
    field = _field("ADMIN_REFRESHER")
    assert [value for value, _label in field.options] == ["on", "off"]
    assert config._MODE_VALUES["ADMIN_REFRESHER"] == ("on", "off")
    assert config._cast(field, "ON") == "on"
    assert config._cast(field, "maybe") == "off"


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    kind, default, _low, _high = V201_FIELDS[attr]
    expected = int(default) if kind == "number" else default
    assert config._cast(field, field.default) == expected


@pytest.mark.parametrize("attr", sorted(V201_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V201_FIELDS[attr][1]}\n" in text
```

(A select `Field` stores whatever `min`/`max` default to; check with `python -c "from swingbot import config; f=[x for x in config.FIELDS if x.attr=='MARKETDATA_LAYER'][0]; print(f.min, f.max)"` and make the `ADMIN_REFRESHER` tuple match what it prints.)

- [ ] **Step 2: Write the failing contract/session test** `tests/refresher/test_admin_refresh_contract.py`

```python
"""v201: the refresher contract module and the session-state clock."""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import session
from swingbot.core.marketdata.shared import admin_refresh as ar

UTC = timezone.utc


@pytest.mark.parametrize("now,state", [
    (datetime(2026, 10, 28, 14, 0, tzinfo=UTC), "regular"),     # Wed 10:00 ET
    (datetime(2026, 10, 28, 12, 0, tzinfo=UTC), "extended"),    # Wed 08:00 ET
    (datetime(2026, 10, 28, 21, 30, tzinfo=UTC), "extended"),   # Wed 17:30 ET
    (datetime(2026, 10, 29, 1, 0, tzinfo=UTC), "closed"),       # Wed 21:00 ET
    (datetime(2026, 10, 31, 15, 0, tzinfo=UTC), "closed"),      # Saturday
    (datetime(2026, 11, 26, 16, 0, tzinfo=UTC), "closed"),      # Thanksgiving
])
def test_session_state(now, state):
    assert session.session_state(now) == state


@pytest.mark.parametrize("now,close", [
    (datetime(2026, 10, 31, 16, 0, tzinfo=UTC), datetime(2026, 10, 30, 20, 0, tzinfo=UTC)),
    (datetime(2026, 10, 28, 19, 0, tzinfo=UTC), datetime(2026, 10, 27, 20, 0, tzinfo=UTC)),
    (datetime(2026, 10, 28, 21, 0, tzinfo=UTC), datetime(2026, 10, 28, 20, 0, tzinfo=UTC)),
    (datetime(2026, 11, 28, 15, 0, tzinfo=UTC), datetime(2026, 11, 27, 18, 0, tzinfo=UTC)),  # half day
])
def test_last_regular_close_is_utc_and_holiday_aware(now, close):
    got = session.last_regular_close(now)
    assert got == close and got.tzinfo is not None


@pytest.mark.parametrize("admin,layer,on", [
    ("on", "on", True), ("off", "on", False), ("on", "count", False), ("on", "off", False)])
def test_refresher_on_needs_both_flags(monkeypatch, admin, layer, on):
    monkeypatch.setattr(config, "ADMIN_REFRESHER", admin)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", layer)
    assert ar.refresher_on() is on


def test_cadence_and_staleness_read_config_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_REFRESH_REGULAR_S", 11)
    assert ar.cadence_s("regular") == 11.0
    assert ar.cadence_s("extended") == 300.0 and ar.cadence_s("closed") == 1800.0
    assert ar.stale_after_s("price", "regular") == 120.0
    assert ar.stale_after_s("price", "extended") == 900.0
    assert ar.stale_after_s("snapshot", "regular") == 600.0
    assert ar.stale_after_s("snapshot", "extended") == 1800.0
    assert ar.stale_after_s("price", "closed") is None
    with pytest.raises(ValueError):
        ar.cadence_s("lunch")


def test_heartbeat_stalled_after_three_cadences():
    now = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
    assert ar.heartbeat_stalled(None, 30.0, now) is True
    assert ar.heartbeat_stalled(now - timedelta(seconds=90), 30.0, now) is False
    assert ar.heartbeat_stalled(now - timedelta(seconds=91), 30.0, now) is True


def test_keys_priorities_and_snapshot_patterns():
    assert ar.quote_mark_key(" aapl ") == "quote:AAPL"
    assert ar.snapshot_mark_key("risk") == "snapshot:risk"
    assert (ar.PRIORITY_USER, ar.PRIORITY_FRESH_HINT, ar.PRIORITY_MISSING) == (0, 1, 2)
    assert (ar.QUEUE_KIND_QUOTE, ar.QUEUE_KIND_SNAPSHOT) == ("quote", "snapshot")
    assert (ar.HEARTBEAT_KEY, ar.QUEUE_RETENTION_S) == ("refresher", 3600)
    for key in ("risk", "analytics.snapshot", "analytics.performance:main",
                "analytics.equity_curve:weak", "calendar.pnl:2026-10"):
        assert ar.is_snapshot_key(key), key
    for key in ("riskx", "calendar.pnl", "analytics", "", None):
        assert not ar.is_snapshot_key(key), key
```

- [ ] **Step 3: Extend the kinds and budget tests**

In `tests/marketdata/test_shared_kinds.py`: change `test_priorities_put_money_first`'s list to `[1, 2, 3, 4, 5, 5, 5, 5]`; add `(Asker.ADMIN_REFRESH, "ADMIN_REFRESH_REGULAR_S")` to the `test_quote_window_reads_the_askers_knob_at_call_time` parametrize; append

```python
def test_refresher_asker_is_tier_5_and_never_turned_fresh():
    assert Asker.ADMIN_REFRESH.value == "admin_refresh" and Asker.ADMIN_REFRESH.priority == 5
    with fresh_request():
        assert resolve_asker(Asker.ADMIN_REFRESH) is Asker.ADMIN_REFRESH
```

In `tests/marketdata/test_shared_budget.py`: add `(Asker.ADMIN_REFRESH, 75.0)` to `test_take_passes_the_tier_reserve`'s parametrize; append (spec Non-goals, regression 2)

```python
def test_refresher_storm_leaves_budget_for_stop_monitor_and_scan(shared_db):
    taken = sum(budget.take(PROVIDER_ALPACA, Asker.ADMIN_REFRESH) for _ in range(100))
    assert taken <= 6                         # bucket 10, tier 5 keeps 5 (+1 refill slack)
    assert budget.take(PROVIDER_ALPACA, Asker.STOP_MONITOR) is True
    assert budget.take(PROVIDER_ALPACA, Asker.SCAN) is True
```

- [ ] **Step 4: Suite entry and package files**

Create empty `tests/refresher/__init__.py` and `tests/admin_market/__init__.py` (`testrun.py` refuses a path no suite owns). Append to `tests/suites.toml`:

```toml
[suites.refresher]
description = "v201 admin market refresher: contract, process, quote cycle, never-fetch request door"
paths = ["tests/refresher/", "tests/admin_market/"]
```

- [ ] **Step 5: Run the four test files to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/test_config_v201_keys.py`, then the same for `tests/refresher/test_admin_refresh_contract.py`, `tests/marketdata/test_shared_kinds.py`, `tests/marketdata/test_shared_budget.py`
Expected: FAIL (`StopIteration` for the fields, `ModuleNotFoundError: ...admin_refresh`, `AttributeError: ADMIN_REFRESH`).

- [ ] **Step 6: Implement the config fields**

After the `TAPE_PROXY_SYMBOLS` `Field(...)` in `swingbot/config.py`, add 12 `Field`s in `V201_FIELDS` order, all `"Data Sources"`, `key == attr`, each `help` starting `"v201. "`. Number fields: `type="number"`, `step=1`, except `step=60` for `ADMIN_REFRESH_FX_UNKNOWN_RETRY_S`; min/max per the table. The kill switch:

```python
    Field("ADMIN_REFRESHER", "ADMIN_REFRESHER", "Data Sources",
          "Admin market refresher", type="select", default="on", options=["on", "off"],
          help="v201. 'on' (with MARKETDATA_LAYER=on) = admin pages read prices, FX and heavy "
               "snapshots only from what the refresher service stored; no page load fetches. "
               "'off' = the pre-v201 request-time fetch paths, exactly."),
```

Labels for the rest, in order: "Refresher cadence: regular hours (s)", "Refresher cadence: pre/after hours (s)", "Refresher cadence: market closed (s)", "Refresher: heavy snapshot interval (s)", "Refresher: yfinance fallback cap per cycle", "Refresher: in-flight mark timeout (s)", "Refresher: retry an unknown quote currency after (s)", "Price stale after: regular hours (s)", "Price stale after: pre/after hours (s)", "Snapshot stale after: regular hours (s)", "Snapshot stale after: pre/after hours (s)". Add `"ADMIN_REFRESHER": ("on", "off"),` to `_MODE_VALUES` (no `_MODE_FALLBACK` entry: a typo lands on `"off"`, today's paths).

In `.env.example`, directly after `TAPE_PROXY_SYMBOLS=...`, add a `# v201: admin market refresher (compose service "refresher").` comment and the 12 `KEY=default` lines in the same order.

- [ ] **Step 7: Implement kinds and session**

`kinds.py`: append `ADMIN_REFRESH = "admin_refresh"` as the last `Asker` member; `_PRIORITY[Asker.ADMIN_REFRESH] = 5`; `_QUOTE_ATTR[Asker.ADMIN_REFRESH] = "ADMIN_REFRESH_REGULAR_S"`. `resolve_asker` is unchanged (it rewrites only `ADMIN_PAGE`/`ADMIN_DASHBOARD`).

`session.py`, after `is_nyse_regular_session`:

```python
SESSION_REGULAR = "regular"
SESSION_EXTENDED = "extended"
SESSION_CLOSED = "closed"


def session_state(now: dt.datetime | None = None) -> str:
    """v201: the refresher's clock. Regular = NYSE regular session (holiday and
    half-day aware); extended = the rest of the live tape; closed otherwise."""
    if is_nyse_regular_session(now):
        return SESSION_REGULAR
    if is_tape_open(now):
        return SESSION_EXTENDED
    return SESSION_CLOSED


def last_regular_close(now: dt.datetime | None = None) -> dt.datetime:
    """v201: the UTC instant the latest NYSE session closed at or before ``now``."""
    et = now_et(now)
    day = et.date()
    for _ in range(14):
        if day.weekday() < 5 and day not in NYSE_HOLIDAYS:
            close = dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)
            if close <= et:
                return close.astimezone(dt.timezone.utc)
        day -= dt.timedelta(days=1)
    raise ValueError(f"no NYSE session closed in the 14 days before {et.isoformat()}")
```

- [ ] **Step 8: Implement `swingbot/core/marketdata/shared/admin_refresh.py`**

Module docstring: the one contract the refresher, the request door and the SPA payloads share. Imports only `config`, `fnmatch.fnmatchcase`, `datetime`/`timezone` and `swingbot.core.market.session`. Constants exactly as the index's "Contract module". Body:

```python
_CADENCE_ATTR = {
    session.SESSION_REGULAR: "ADMIN_REFRESH_REGULAR_S",
    session.SESSION_EXTENDED: "ADMIN_REFRESH_EXTENDED_S",
    session.SESSION_CLOSED: "ADMIN_REFRESH_CLOSED_S",
}
_STALE_ATTR = {
    ("price", session.SESSION_REGULAR): "ADMIN_STALE_PRICE_REGULAR_S",
    ("price", session.SESSION_EXTENDED): "ADMIN_STALE_PRICE_EXTENDED_S",
    ("snapshot", session.SESSION_REGULAR): "ADMIN_STALE_SNAPSHOT_REGULAR_S",
    ("snapshot", session.SESSION_EXTENDED): "ADMIN_STALE_SNAPSHOT_EXTENDED_S",
}


def refresher_on() -> bool:
    return config.ADMIN_REFRESHER == "on" and config.MARKETDATA_LAYER == "on"


def cadence_s(state: str) -> float:
    attr = _CADENCE_ATTR.get(state)
    if attr is None:
        raise ValueError(f"unknown session state {state!r}")
    return float(getattr(config, attr))


def stale_after_s(kind: str, state: str) -> float | None:
    """Absolute threshold; None when closed (labelled closed, never stale)."""
    if state == session.SESSION_CLOSED:
        return None
    attr = _STALE_ATTR.get((kind, state))
    if attr is None:
        raise ValueError(f"unknown staleness kind/state {kind!r}/{state!r}")
    return float(getattr(config, attr))


def heartbeat_stalled(beat_at: datetime | None, cadence: float,
                      now: datetime | None = None) -> bool:
    if beat_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - beat_at).total_seconds() > 3 * float(cadence)


def quote_mark_key(symbol: str) -> str:
    return f"quote:{str(symbol).upper().strip()}"


def snapshot_mark_key(key: str) -> str:
    return f"snapshot:{key}"


def is_snapshot_key(key) -> bool:
    return isinstance(key, str) and any(fnmatchcase(key, p) for p in SNAPSHOT_KEY_PATTERNS)
```

- [ ] **Step 9: Run the changed files and the guards they touch**

Run: `python <wt>/scripts/dev/testrun.py file <f>` for each of `tests/test_config_v201_keys.py`, `tests/refresher/test_admin_refresh_contract.py`, `tests/marketdata/test_shared_kinds.py`, `tests/marketdata/test_shared_budget.py`, `tests/infra/test_env_example_sync.py`, `tests/dev/test_suites.py`, `tests/test_config_v171_keys.py`
Expected: all PASS (`0 failed`). Then `python <wt>/scripts/dev/complexity_gate.py`: clean.

- [ ] **Step 10: Commit**

```bash
git -C <wt> add swingbot/config.py .env.example swingbot/core/marketdata/shared/kinds.py swingbot/core/market/session.py swingbot/core/marketdata/shared/admin_refresh.py tests/suites.toml tests/refresher/__init__.py tests/admin_market/__init__.py tests/test_config_v201_keys.py tests/refresher/test_admin_refresh_contract.py tests/marketdata/test_shared_kinds.py tests/marketdata/test_shared_budget.py
git -C <wt> commit -m "feat(v201): refresher config, ADMIN_REFRESH asker, session state, contract module"
```

# Phase 2: Storage

### Task V201-2: Alembic revision `v201_001`: five tables + `market_cache` index

**Model:** opus — a schema migration on production Postgres; the declared schema and the revision must match exactly or `test_migrations.py` drifts.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v201_001_admin_refresher.py`
- Modify: `swingbot/core/db/schema.py` (five `register(...)` tables after `preregistration_verdicts` ~line 305; one `sa.Index` on `market_cache` ~line 309; five `PROMOTION_REASONS` entries ~line 488)
- Test: `tests/db/test_v201_tables.py`

**Interfaces:**
- Consumes: nothing.
- Produces: tables `admin_snapshots`, `quote_currencies`, `market_refresh_queue`, `market_refresh_marks`, `refresher_heartbeat` exactly as the index's "Tables", importable from `swingbot.core.db.schema` under those names; index `market_cache_kind_updated_idx (kind, updated_at)`. None in `events.TABLE_CHANNELS`.

- [ ] **Step 1: Write the failing test** `tests/db/test_v201_tables.py`

```python
"""v201: revision v201_001 -- the admin refresher's five stores and the
market_cache (kind, updated_at) index behind GET /market/updates."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
TABLES = {
    "admin_snapshots": ("key", "computed_at", "inputs", "stale_inputs"),
    "quote_currencies": ("symbol", "code", "outcome", "checked_at", "retry_after"),
    "market_refresh_queue": ("kind", "key", "priority", "requested_at", "taken_at"),
    "market_refresh_marks": ("key", "started_at", "expires_at", "error", "error_at"),
    "refresher_heartbeat": ("key", "beat_at", "cadence_s", "session", "cycle_ms", "last_error"),
}
NULLABLE = {"code", "retry_after", "taken_at", "error", "error_at", "cycle_ms", "last_error"}


@pytest.mark.parametrize("name", sorted(TABLES))
def test_registered_with_reasons_contract_and_no_sse(name):
    table = schema.METADATA.tables[name]
    assert schema.promoted_for(name) == TABLES[name]
    assert set(schema.PROMOTION_REASONS[name]) == set(TABLES[name])
    assert schema.contract_violations(table) == []
    for column in TABLES[name]:
        assert table.c[column].nullable is (column in NULLABLE), (name, column)
    assert name not in events.TABLE_CHANNELS


def _indexes(table):
    return {i.name: ([c.name for c in i.columns], i.unique) for i in table.indexes}


def test_indexes_and_the_pending_queue_uniqueness():
    assert _indexes(schema.admin_snapshots) == {"admin_snapshots_updated_idx": (["updated_at"], False)}
    assert _indexes(schema.market_refresh_marks) == {
        "market_refresh_marks_updated_idx": (["updated_at"], False)}
    queue = _indexes(schema.market_refresh_queue)
    assert queue["market_refresh_queue_pending_uq"] == (["kind", "key"], True)
    assert queue["market_refresh_queue_take_idx"] == (["taken_at", "priority", "requested_at"], False)
    pending = next(i for i in schema.market_refresh_queue.indexes
                   if i.name == "market_refresh_queue_pending_uq")
    assert "taken_at IS NULL" in str(pending.dialect_options["postgresql"]["where"])
    assert _indexes(schema.market_cache)["market_cache_kind_updated_idx"] == (
        ["kind", "updated_at"], False)


def test_column_types():
    assert isinstance(schema.market_refresh_queue.c.id.type, sa.BigInteger)
    assert isinstance(schema.market_refresh_queue.c.priority.type, sa.SmallInteger)
    assert isinstance(schema.refresher_heartbeat.c.cadence_s.type, sa.Float)
    assert isinstance(schema.admin_snapshots.c.stale_inputs.type, sa.Boolean)
    for table, col in (("admin_snapshots", "computed_at"), ("quote_currencies", "checked_at"),
                       ("market_refresh_marks", "expires_at"), ("refresher_heartbeat", "beat_at")):
        assert schema.METADATA.tables[table].c[col].type.timezone is True


def test_v201_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v201_001")
    assert scripts.get_revision(revision.down_revision) is not None
    assert scripts.get_heads() == ["v201_001"]


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_downgrade_drops_the_five_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert set(TABLES) <= _tables(connection)
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v201_001").down_revision)
        remaining = _tables(connection)
        assert not set(TABLES) & remaining
        assert "market_cache" in remaining
        idx = {i["name"] for i in sa.inspect(connection).get_indexes("market_cache")}
        assert "market_cache_kind_updated_idx" not in idx
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert set(TABLES) <= _tables(connection)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v201_tables.py`
Expected: FAIL with `KeyError: 'admin_snapshots'`.

- [ ] **Step 3: Declare the tables in `swingbot/core/db/schema.py`**

Add `sa.Index("market_cache_kind_updated_idx", "kind", "updated_at")` as the last argument of the `market_cache` `sa.Table(...)`. After `preregistration_verdicts`, under one comment block ("v201: the admin market refresher's stores. Written by the refresher process (swingbot/refresher), read by the admin request door. No SSE trigger: the refresher raises `market` itself, once per cycle."):

```python
admin_snapshots = register(sa.Table("admin_snapshots", METADATA,
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("inputs", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
    *standard_columns(),
    sa.Index("admin_snapshots_updated_idx", "updated_at")),
    ("key", "computed_at", "inputs", "stale_inputs"))

quote_currencies = register(sa.Table("quote_currencies", METADATA,
    sa.Column("symbol", sa.Text, primary_key=True),
    sa.Column("code", sa.Text),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column("retry_after", sa.TIMESTAMP(timezone=True)),
    *standard_columns()),
    ("symbol", "code", "outcome", "checked_at", "retry_after"))

market_refresh_queue = register(sa.Table("market_refresh_queue", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("priority", sa.SmallInteger, nullable=False),
    sa.Column("requested_at", sa.TIMESTAMP(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("taken_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.Index("market_refresh_queue_pending_uq", "kind", "key", unique=True,
             postgresql_where=sa.text("taken_at IS NULL")),
    sa.Index("market_refresh_queue_take_idx", "taken_at", "priority", "requested_at")),
    ("kind", "key", "priority", "requested_at", "taken_at"))
```

`market_refresh_marks` (key PK; `started_at`, `expires_at` NOT NULL TIMESTAMPTZ; `error` Text; `error_at` TIMESTAMPTZ; `market_refresh_marks_updated_idx (updated_at)`) and `refresher_heartbeat` (key PK; `beat_at` NOT NULL TIMESTAMPTZ; `cadence_s` `sa.Float(53)` NOT NULL; `session` Text NOT NULL; `cycle_ms` Integer; `last_error` Text) follow the same shape. `PROMOTION_REASONS` gets one entry per promoted column, each a reason in the existing style, e.g. `"computed_at": "NOT NULL; the snapshot's own clock the UI ages"`, `"retry_after": "the FX job's backoff WHERE for an unknown answer; NULL when known"`, `"taken_at": "pending-vs-taken split in the partial unique index and the take index"`, `"expires_at": "in-flight test (expires_at > now) in every active() read"`, `"beat_at": "stalled test (age > 3 x cadence) in /system/health and /market/updates"`.

- [ ] **Step 4: Write the revision** `swingbot/core/db/migrations/versions/v201_001_admin_refresher.py`

First find the head: `python -m alembic -c <wt>/alembic.ini heads` (expect `v173_002`; `v200_001` if v200 merged first). Use it as `down_revision`.

```python
"""v201: admin market refresher stores -- snapshots, quote currencies, refresh
queue, in-flight marks, heartbeat -- and market_cache (kind, updated_at).

Additive: rollback is this revision's downgrade; leaving the tables after a
code rollback is also safe (nothing else reads them).

Revision ID: v201_001
Revises: <head printed above>
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v201_001"
down_revision = "v173_002"   # replace with the head printed above
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("admin_snapshots",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("computed_at", _TS, nullable=False),
        sa.Column("inputs", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("stale_inputs", sa.Boolean, nullable=False, server_default=sa.false()),
        *_standard())
    op.create_index("admin_snapshots_updated_idx", "admin_snapshots", ["updated_at"])
    # quote_currencies, market_refresh_queue (+ both indexes; the unique one with
    # postgresql_where=sa.text("taken_at IS NULL")), market_refresh_marks (+ index),
    # refresher_heartbeat: column for column as schema.py.
    op.create_index("market_cache_kind_updated_idx", "market_cache", ["kind", "updated_at"])


def downgrade() -> None:
    op.drop_index("market_cache_kind_updated_idx", table_name="market_cache")
    for name in ("refresher_heartbeat", "market_refresh_marks", "market_refresh_queue",
                 "quote_currencies", "admin_snapshots"):
        op.drop_table(name)   # drops each table's own indexes with it
```

The four elided `create_table` calls are written out in full; the comment above only marks where.

- [ ] **Step 5: Run the new test and the schema guards**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v201_tables.py`, then `tests/db/test_migrations.py` (declared schema == migrated schema, one head), `tests/db/test_trigger_coverage.py`, `tests/db/test_schema_contract.py`, `tests/db/test_market_shared_repository.py`, `tests/db/test_v172_tables.py` (its `len(get_heads()) == 1` still holds)
Expected: all PASS. A `compare_metadata` diff in `test_migrations.py` names the column or index that differs between Step 3 and Step 4; fix the revision to match `schema.py`.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v201_001_admin_refresher.py tests/db/test_v201_tables.py
git -C <wt> commit -m "feat(v201): v201_001 -- admin refresher stores and market_cache (kind, updated_at) index"
```

### Task V201-3: Repositories for snapshots, quote currencies, queue, marks, heartbeat

**Model:** sonnet — five small repositories on a fixed schema; the two non-obvious statements (queue upsert, take) are given below.

**Files:**
- Create: `swingbot/core/db/repositories/market_refresh.py`
- Modify: `swingbot/core/db/repositories/market_shared.py` (`write_entries` stamps `updated_at` on insert too; new `changed_since`)
- Test: `tests/db/test_market_refresh_repos.py`, `tests/db/test_market_shared_repository.py`

**Interfaces:**
- Consumes: V201-2's tables from `swingbot.core.db.schema`.
- Produces: the index's "Repositories" section. Every method also takes a trailing keyword `conn: sa.Connection | None = None` (the `Repository._tx(conn)` pattern of `equity_samples.py`); `RefreshMarkRepository.changed_since` also takes `now=None`. Times are tz-aware UTC; symbols and keys are stored upper-cased where they are tickers (`quote_currencies.symbol`). `updated_at` is set to `clock_timestamp()` on every insert and update, so a cursor read from `clock_timestamp()` orders writes even inside one transaction. `MarketSharedRepository.changed_since(kind, since, *, conn) -> list[dict]` with keys `key, symbol, fetched_at, doc, updated_at`, `doc` the raw stored JSONB (`{"value": QuoteDetail.to_doc()}` for quotes), ordered by `updated_at`.

- [ ] **Step 1: Write the failing repository tests** `tests/db/test_market_refresh_repos.py`

```python
"""v201: the refresher's stores -- snapshots, quote currencies, queue, marks, heartbeat."""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from swingbot.core.db.repositories import market_refresh as mr

UTC = timezone.utc
T0 = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def test_snapshot_put_overwrites_and_changed_since_follows_updated_at(db_conn):
    repo = mr.AdminSnapshotRepository()
    repo.put("risk", {"heat": 1}, {"missing": {}}, computed_at=T0, stale_inputs=False, conn=db_conn)
    repo.put("risk", {"heat": 2}, {"missing": {"bars": ["X"]}},
             computed_at=T0 + timedelta(minutes=1), stale_inputs=True, conn=db_conn)
    got = repo.get("risk", conn=db_conn)
    assert got["doc"] == {"heat": 2} and got["inputs"] == {"missing": {"bars": ["X"]}}
    assert got["computed_at"] == T0 + timedelta(minutes=1) and got["stale_inputs"] is True
    assert repo.get("nope", conn=db_conn) is None
    assert set(repo.get_many(["risk", "nope"], conn=db_conn)) == {"risk"}
    assert repo.get_many([], conn=db_conn) == {}
    changed = repo.changed_since(got["updated_at"] - timedelta(microseconds=1), conn=db_conn)
    assert [(r["key"], r["stale_inputs"]) for r in changed] == [("risk", True)]
    assert repo.changed_since(got["updated_at"], conn=db_conn) == []


def test_quote_currency_due_honours_the_unknown_backoff(db_conn):
    repo = mr.QuoteCurrencyRepository()
    repo.put("aapl", "USD", "known", checked_at=T0, conn=db_conn)
    repo.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0 + timedelta(hours=6), conn=db_conn)
    assert repo.due(["AAPL", "ZZZ", "NEW"], T0 + timedelta(hours=1), conn=db_conn) == ["NEW"]
    assert repo.due(["AAPL", "zzz", "NEW"], T0 + timedelta(hours=6), conn=db_conn) == ["ZZZ", "NEW"]
    got = repo.get_many(["AAPL", "ZZZ", "NOPE"], conn=db_conn)
    assert got["AAPL"]["code"] == "USD" and got["AAPL"]["outcome"] == "known"
    assert got["ZZZ"]["code"] is None and got["ZZZ"]["retry_after"] == T0 + timedelta(hours=6)
    assert "NOPE" not in got


def test_enqueue_dedupes_pending_and_only_raises_urgency(db_conn):
    q = mr.RefreshQueueRepository()
    assert q.enqueue("quote", ["AAPL", "MSFT"], priority=2, conn=db_conn) == 2
    assert q.enqueue("quote", ["AAPL"], priority=2, conn=db_conn) == 0
    assert q.enqueue("quote", ["AAPL"], priority=0, conn=db_conn) == 0
    assert q.enqueue("quote", ["AAPL"], priority=1, conn=db_conn) == 0
    assert q.enqueue("snapshot", ["AAPL"], priority=2, conn=db_conn) == 1   # other kind
    taken = q.take(10, conn=db_conn)
    assert [(t["kind"], t["key"], t["priority"]) for t in taken] == [
        ("quote", "AAPL", 0), ("quote", "MSFT", 2), ("snapshot", "AAPL", 2)]
    assert q.take(10, conn=db_conn) == []
    assert q.enqueue("quote", ["AAPL"], priority=2, conn=db_conn) == 1      # taken row no longer blocks
    assert q.enqueue("quote", [], priority=2, conn=db_conn) == 0


def test_take_respects_the_limit_and_prune_drops_old_rows(db_conn):
    q = mr.RefreshQueueRepository()
    q.enqueue("quote", ["A", "B", "C"], priority=2, conn=db_conn)
    assert len(q.take(2, conn=db_conn)) == 2
    assert q.prune(EPOCH, conn=db_conn) == 0
    assert q.prune(datetime.now(UTC) + timedelta(seconds=5), conn=db_conn) == 3


def test_marks_expire_after_timeout(db_conn):
    m = mr.RefreshMarkRepository()
    m.mark(["quote:AAPL", "quote:MSFT"], timeout_s=120, now=T0, conn=db_conn)
    keys = ["quote:AAPL", "quote:MSFT", "quote:X"]
    assert m.active(keys, now=T0 + timedelta(seconds=119), conn=db_conn) == {"quote:AAPL", "quote:MSFT"}
    assert m.active(keys, now=T0 + timedelta(seconds=121), conn=db_conn) == set()


def test_clear_keeps_the_row_with_its_error_until_the_next_mark(db_conn):
    m = mr.RefreshMarkRepository()
    m.mark(["quote:AAPL"], timeout_s=120, now=T0, conn=db_conn)
    m.clear(["quote:AAPL"], error="no quote", now=T0 + timedelta(seconds=5), conn=db_conn)
    assert m.active(["quote:AAPL"], now=T0 + timedelta(seconds=6), conn=db_conn) == set()
    assert m.errors(["quote:AAPL", "quote:X"], conn=db_conn) == {"quote:AAPL": "no quote"}
    [row] = m.changed_since(EPOCH, now=T0 + timedelta(seconds=6), conn=db_conn)
    assert (row["key"], row["in_flight"], row["error"]) == ("quote:AAPL", False, "no quote")
    m.mark(["quote:AAPL"], timeout_s=120, now=T0 + timedelta(seconds=10), conn=db_conn)
    assert m.errors(["quote:AAPL"], conn=db_conn) == {}
    [row] = m.changed_since(EPOCH, now=T0 + timedelta(seconds=11), conn=db_conn)
    assert row["in_flight"] is True


def test_heartbeat_is_one_upserted_row(db_conn):
    h = mr.RefresherHeartbeatRepository()
    assert h.read(conn=db_conn) is None
    h.beat(cadence_s=30, session="regular", cycle_ms=850, last_error=None, now=T0, conn=db_conn)
    h.beat(cadence_s=300, session="extended", cycle_ms=None, last_error="boom",
           now=T0 + timedelta(seconds=30), conn=db_conn)
    assert h.read(conn=db_conn) == {"beat_at": T0 + timedelta(seconds=30), "cadence_s": 300.0,
                                    "session": "extended", "cycle_ms": None, "last_error": "boom"}
    assert db_conn.execute(sa.text("select count(*) from refresher_heartbeat")).scalar() == 1


def test_accessors_are_singletons():
    for accessor in (mr.admin_snapshot_repo, mr.quote_currency_repo, mr.refresh_queue_repo,
                     mr.refresh_mark_repo, mr.refresher_heartbeat_repo):
        assert accessor() is accessor()
```

Append to `tests/db/test_market_shared_repository.py`:

```python
def test_changed_since_returns_one_kinds_rows_after_the_cursor(repo, db_conn):
    cursor = db_conn.execute(sa.text("select clock_timestamp()")).scalar()
    repo.write_entries([_row(), {**_row("index:^GSPC:"), "kind": "index"}], conn=db_conn)
    got = repo.changed_since("quote", cursor, conn=db_conn)
    assert [(r["key"], r["symbol"]) for r in got] == [("quote:AAPL:", "AAPL")]
    assert got[0]["fetched_at"] == T0 and got[0]["doc"]["value"] == {"price": 1.5}
    assert repo.changed_since("quote", got[0]["updated_at"], conn=db_conn) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_market_refresh_repos.py` and `... file tests/db/test_market_shared_repository.py`
Expected: FAIL (`ModuleNotFoundError: ...market_refresh`; `AttributeError: ... changed_since`).

- [ ] **Step 3: Implement `swingbot/core/db/repositories/market_refresh.py`**

Module docstring: the five v201 stores, their one writer (the refresher; the queue's writer is the request door) and that none raises an SSE event. Five classes subclassing `Repository` (`super().__init__(<table>, key=<pk>)`), each method one statement inside `with self._tx(conn) as c:`, `_STAMP = sa.func.clock_timestamp()` for every `updated_at`. Readers return plain dicts built from row columns (not `_record`), so `doc` stays the payload. Accessors follow `equity_samples_repo()` (module `_repos: dict` or one global per class).

The two statements the tests do not determine:

```python
    def enqueue(self, kind: str, keys, *, priority: int, conn=None) -> int:
        """Rows inserted. A pending (kind, key) is kept; a lower priority number replaces its own."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return 0
        t = self.table
        ins = pg_insert(t).values([{"kind": kind, "key": k, "priority": int(priority),
                                    "updated_at": _STAMP} for k in keys])
        stmt = ins.on_conflict_do_update(
            index_elements=[t.c.kind, t.c.key], index_where=t.c.taken_at.is_(None),
            set_={"priority": sa.func.least(t.c.priority, ins.excluded.priority),
                  "updated_at": _STAMP},
        ).returning(sa.literal_column("(xmax = 0)").label("inserted"))
        with self._tx(conn) as c:
            return sum(1 for row in c.execute(stmt) if row.inserted)

    def take(self, limit: int, *, conn=None) -> list[dict]:
        t = self.table
        pick = (sa.select(t.c.id).where(t.c.taken_at.is_(None))
                .order_by(t.c.priority, t.c.requested_at).limit(int(limit))
                .with_for_update(skip_locked=True))
        stmt = (sa.update(t).where(t.c.id.in_(pick.scalar_subquery()))
                .values(taken_at=_STAMP, updated_at=_STAMP)
                .returning(t.c.kind, t.c.key, t.c.priority, t.c.requested_at, t.c.id))
        with self._tx(conn) as c:
            rows = sorted(c.execute(stmt), key=lambda r: (r.priority, r.requested_at, r.id))
        return [{"kind": r.kind, "key": r.key, "priority": int(r.priority)} for r in rows]
```

The rest, by the tests: `prune` deletes `requested_at < older_than` (taken or not) and returns `rowcount`. `mark` upserts each key with `started_at=now`, `expires_at=now+timeout_s`, `error=None`, `error_at=None`. `clear` updates the given keys to `expires_at=now`, `error=error`, `error_at=now if error else None` (a key with no row is inserted that way, so an error on a never-marked key is still visible). `active` = keys with `expires_at > now`. `errors` = `{key: error}` where `error IS NOT NULL`. Marks' `changed_since` returns `{key, in_flight: expires_at > now, error, updated_at}` with `updated_at > since`, ordered by `updated_at`. `AdminSnapshotRepository.put` upserts on `key` setting `doc`, `inputs`, `computed_at`, `stale_inputs`; its `changed_since` returns `key, computed_at, stale_inputs, updated_at`. `QuoteCurrencyRepository.put` upserts on `symbol.upper()`; `due` returns, in input order and upper-cased, symbols with no row or with `outcome = 'unknown' AND retry_after <= now`. `RefresherHeartbeatRepository` writes one row under `key = HEARTBEAT_KEY = "refresher"` (restated here so `core/db` imports nothing from `core/marketdata`; V201-5's test asserts it equals `admin_refresh.HEARTBEAT_KEY`).

- [ ] **Step 4: `market_shared.py`**

In `write_entries`, add `"updated_at": _now()` to each insert value (today an insert takes the column default `now()`, the transaction start, which would sort before a cursor read in the same transaction). Add:

```python
    def changed_since(self, kind: str, since: datetime, *, conn: sa.Connection) -> list[dict]:
        """Rows of ``kind`` written after ``since`` (index market_cache_kind_updated_idx)."""
        c = market_cache.c
        rows = conn.execute(
            sa.select(c.key, c.symbol, c.fetched_at, c.doc, c.updated_at)
            .where(c.kind == kind, c.updated_at > since, c.fetched_at.is_not(None))
            .order_by(c.updated_at)).all()
        return [dict(row._mapping) for row in rows]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_market_refresh_repos.py`, `... file tests/db/test_market_shared_repository.py`, `... file tests/marketdata/test_shared_layer.py`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/db/repositories/market_refresh.py swingbot/core/db/repositories/market_shared.py tests/db/test_market_refresh_repos.py tests/db/test_market_shared_repository.py
git -C <wt> commit -m "feat(v201): refresher repositories and market_cache changed_since"
```

### Task V201-4: FX: persisted quote-currency codes, never-fetch request reads, conversion moved to core

**Model:** opus — money conversion on every admin total; an "unknown" answer must never be summed as zero or re-fetched on a request.

**Files:**
- Modify: `swingbot/core/marketdata/fx.py`
- Create: `swingbot/core/marketdata/fx_convert.py` (the body of today's `money.py`, plus `fetch`)
- Modify: `swingbot/admin/api_v1/money.py` (thin wrapper), `swingbot/admin/api_v1/risk_read_model.py` (`_quote_rate`)
- Test: `tests/marketdata/test_fx_persisted.py`; `tests/marketdata/test_fx.py` only if a test there pins `_refreshed_frame`'s one-argument call

**Interfaces:**
- Consumes: `market_refresh.quote_currency_repo()` (V201-3: `get_many`, `put`, `due`); `config.ADMIN_REFRESH_FX_UNKNOWN_RETRY_S`, `Asker.ADMIN_REFRESH`, `admin_refresh.refresher_on()` (V201-1).
- Produces: `fx.quote_currency_code(ticker, *, fetch: bool = True) -> str | None`; `fx.fx_rate(from_code, to_code, on, *, refresh: bool = True) -> float | None`; `fx.refresh_quote_codes(symbols, *, now: datetime | None = None) -> dict[str, str | None]` (only the symbols it asked and got an answer for); `fx.refresh_pair_frames(codes: Iterable[str]) -> list[str]` (pairs whose frame loaded, sorted). `fx_convert.MONEY_FIELDS`, `fx_convert.to_account_currency(rows, *, account=None, fetch=True) -> list[dict]`, `fx_convert.convert_amount(amount, ticker, on, *, account=None, fetch=True) -> tuple[float | None, bool]`, `fx_convert.missing_count(rows) -> int`, and two seams `fx_convert.quote_code(ticker, *, fetch=True)`, `fx_convert.rate(from_code, to_code, on, *, fetch=True)`. `money.to_account_currency` / `convert_amount` keep today's signatures and pass `fetch=not admin_refresh.refresher_on()`.

- [ ] **Step 1: Write the failing test** `tests/marketdata/test_fx_persisted.py`

```python
"""v201: quote-currency codes persisted by the refresher; requests never fetch FX."""
import contextlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import fx, fx_convert
from swingbot.core.marketdata.shared.kinds import Asker

T0 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
FRAME = pd.DataFrame({"Close": [0.9]}, index=pd.to_datetime(["2026-10-27"]))


class FakeCodes:
    def __init__(self):
        self.rows = {}

    def get_many(self, symbols, *, conn=None):
        return {s: self.rows[s] for s in symbols if s in self.rows}

    def put(self, symbol, code, outcome, *, checked_at, retry_after=None, conn=None):
        self.rows[symbol] = {"symbol": symbol, "code": code, "outcome": outcome,
                             "checked_at": checked_at, "retry_after": retry_after}

    def due(self, symbols, now, *, conn=None):
        return [s for s in symbols if s not in self.rows or (
            self.rows[s]["outcome"] == "unknown" and self.rows[s]["retry_after"] <= now)]


def _boom(*_a, **_k):
    raise AssertionError("network call on a never-fetch path")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(fx, "_frames", {})
    monkeypatch.setattr(fx, "_quote_codes", {})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")


@pytest.fixture
def codes(monkeypatch):
    repo = FakeCodes()
    monkeypatch.setattr(fx, "quote_currency_repo", lambda: repo)
    return repo


@pytest.fixture
def provider(monkeypatch):
    calls = []
    answers = {"AAPL": ("USD", True), "ZZZ": (None, True), "DOWN": (None, False)}

    def fake(key):
        calls.append(key)
        if key == "BOOM":
            raise RuntimeError("provider down")
        return answers[key]
    monkeypatch.setattr(fx.data, "_provider_currency_code", fake)
    return calls


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(fx.data, "_provider_currency_code", _boom)
    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", _boom)
    monkeypatch.setattr(fx.data_store, "load_normalized", lambda pair, kind: FRAME)


def test_never_fetch_read_is_memo_then_store_then_none(codes, no_network):
    codes.put("AAPL", "USD", "known", checked_at=T0)
    codes.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0)
    assert fx.quote_currency_code("aapl", fetch=False) == "USD"
    assert fx.quote_currency_code("ZZZ", fetch=False) is None
    assert fx.quote_currency_code("NEW", fetch=False) is None
    codes.rows.clear()
    assert fx.quote_currency_code("AAPL", fetch=False) == "USD"      # memoised


def test_store_error_reads_as_none(monkeypatch, no_network):
    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(fx, "quote_currency_repo", down)
    assert fx.quote_currency_code("AAPL", fetch=False) is None


def test_refresh_persists_known_and_unknown_and_skips_unanswered(codes, provider):
    assert fx.refresh_quote_codes(["aapl", "ZZZ", "DOWN", "BOOM"], now=T0) == {"AAPL": "USD", "ZZZ": None}
    assert codes.rows["AAPL"]["outcome"] == "known"
    assert codes.rows["ZZZ"]["retry_after"] == T0 + timedelta(seconds=21600)
    assert "DOWN" not in codes.rows and "BOOM" not in codes.rows


def test_unknown_code_is_persisted_and_not_retried_before_backoff(codes, provider):
    fx.refresh_quote_codes(["ZZZ"], now=T0)
    fx.refresh_quote_codes(["ZZZ"], now=T0 + timedelta(hours=5))
    assert provider == ["ZZZ"]
    fx.refresh_quote_codes(["ZZZ"], now=T0 + timedelta(hours=6))
    assert provider == ["ZZZ", "ZZZ"]


def test_refresh_runs_at_the_refresher_tier(codes, provider, monkeypatch):
    scopes = []

    @contextlib.contextmanager
    def scope(asker):
        scopes.append(asker)
        yield
    monkeypatch.setattr(fx.router, "asker_scope", scope)
    fx.refresh_quote_codes(["AAPL"], now=T0)
    assert scopes == [Asker.ADMIN_REFRESH]


def test_rate_without_refresh_reads_the_disk_file_only(no_network):
    assert fx.fx_rate("USD", "EUR", date(2026, 10, 28), refresh=False) == pytest.approx(0.9)


def test_refresh_pair_frames_skips_the_account_currency(monkeypatch):
    refreshed = []
    monkeypatch.setattr(fx.data_refresh, "refresh_symbol", lambda pair, kind: refreshed.append(pair))
    monkeypatch.setattr(fx.data_store, "load_normalized",
                        lambda pair, kind: None if pair == "ILSEUR=X" else FRAME)
    assert fx.refresh_pair_frames(["USD", "EUR", "GBp", "USD", None, "ILA"]) == ["GBPEUR=X", "USDEUR=X"]
    assert refreshed == ["GBPEUR=X", "ILSEUR=X", "USDEUR=X"]


def _row(ticker, amount):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": "2026-10-28"}


def test_convert_without_fetch_flags_unknown_never_zero(codes, no_network):
    codes.put("AAPL", "USD", "known", checked_at=T0)
    rows = fx_convert.to_account_currency([_row("AAPL", 10.0), _row("NEW", 5.0)], fetch=False)
    assert (rows[0]["realized_pnl_amount"], rows[0]["fx_missing"]) == (9.0, False)
    assert (rows[1]["realized_pnl_amount"], rows[1]["fx_missing"]) == (None, True)
    assert fx_convert.missing_count(rows) == 1
    assert fx_convert.convert_amount(10.0, "AAPL", date(2026, 10, 28), fetch=False) == (9.0, False)


@pytest.mark.parametrize("admin,fetch", [("on", False), ("off", True)])
def test_money_wrapper_passes_fetch_from_the_kill_switch(monkeypatch, admin, fetch):
    from swingbot.admin.api_v1 import money
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ADMIN_REFRESHER", admin)
    seen = []
    monkeypatch.setattr(fx_convert, "to_account_currency",
                        lambda rows, *, account=None, fetch=True: seen.append(fetch) or rows)
    money.to_account_currency([])
    assert seen == [fetch]


def test_risk_weights_never_fetch_with_the_refresher_on(codes, no_network, monkeypatch):
    from swingbot.admin.api_v1 import risk_read_model
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    codes.put("AAPL", "USD", "known", checked_at=T0)
    trade = {"ticker": "AAPL", "direction": "bullish", "entry": 100.0, "shares": 2}
    weights, error = risk_read_model.signed_weights([trade], on=date(2026, 10, 28))
    assert error is None and weights == {"AAPL": pytest.approx(1.0)}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_persisted.py`
Expected: FAIL (`ModuleNotFoundError: ...fx_convert`).

- [ ] **Step 3: Implement the `fx.py` changes**

Import `quote_currency_repo` from `swingbot.core.db.repositories.market_refresh` at module level (the tests patch `fx.quote_currency_repo`), plus `timezone`. Keep `fetch=True` byte-for-byte today's path; it runs only with the refresher off.

```python
def quote_currency_code(ticker: str, *, fetch: bool = True) -> str | None:
    key = str(ticker or "").upper().strip()
    if not key:
        return None
    if key in _quote_codes:
        return _quote_codes[key]
    if not fetch:
        return _stored_code(key)
    # ... today's provider path, unchanged ...


def _stored_code(key: str) -> str | None:
    """v201: the refresher's persisted answer; never the network. Unknown/missing -> None."""
    try:
        row = quote_currency_repo().get_many([key]).get(key)
    except Exception as exc:
        swallowed(log, "marketdata.fx.stored_code", exc, level=logging.DEBUG)
        return None
    if not row or row.get("outcome") != "known" or not row.get("code"):
        return None
    _quote_codes[key] = str(row["code"])
    return _quote_codes[key]


def refresh_quote_codes(symbols, *, now: datetime | None = None) -> dict[str, str | None]:
    """v201 refresher FX job: ask the provider for every due symbol and persist the
    answer; an 'unknown' answer is stored with a retry_after backoff, an unanswered
    call (provider error) is not stored and is retried next cycle."""
    now = now or datetime.now(timezone.utc)
    repo = quote_currency_repo()
    keys = list(dict.fromkeys(str(s or "").upper().strip() for s in symbols if str(s or "").strip()))
    out: dict[str, str | None] = {}
    for key in repo.due(keys, now):
        code, answered = _ask_provider(key)
        if not answered:
            continue
        if code:
            repo.put(key, str(code), "known", checked_at=now)
            _quote_codes[key] = str(code)
        else:
            retry = now + timedelta(seconds=float(config.ADMIN_REFRESH_FX_UNKNOWN_RETRY_S))
            repo.put(key, None, "unknown", checked_at=now, retry_after=retry)
        out[key] = str(code) if code else None
    return out
```

`_ask_provider(key) -> tuple[str | None, bool]`: `data._provider_currency_code(key)` inside `router.asker_scope(Asker.ADMIN_REFRESH)`; any exception is `swallowed(..., level=logging.DEBUG)` and returns `(None, False)`.

`fx_rate(..., *, refresh=True)` passes `refresh` to `_pair_frame(pair, refresh=refresh)`. In `_pair_frame`, a miss loads `_refreshed_frame(pair)` when `refresh` else `_disk_frame(pair)` (`data_store.load_normalized(pair, "daily")`, an exception swallowed to `None`); both are memoised in `_frames` for `FRAME_TTL_S` as today. `_refreshed_frame(pair, asker: Asker = Asker.ADMIN_PAGE)` uses `router.asker_scope(kinds.resolve_asker(asker))`.

`refresh_pair_frames(codes)`: `account = _major(account_currency_code())[0]`; `pairs = sorted({f"{_major(c)[0]}{account}=X" for c in codes if c and _major(c)[0] != account})`; for each pair, `frame = _refreshed_frame(pair, asker=Asker.ADMIN_REFRESH)`, `_frames[pair] = (_clock(), frame)`; return the pairs whose frame is not `None`. This writes only the FX pair files `fx` already writes (Global Constraints).

- [ ] **Step 4: Create `swingbot/core/marketdata/fx_convert.py`; slim `money.py`; route `risk_read_model`**

Move `MONEY_FIELDS`, `_day`, `_Rates`, `_at`, `_priced_legs`, `_converted`, `to_account_currency`, `convert_amount`, `missing_count` from `money.py` into `fx_convert.py` unchanged, except: `_Rates(account, fetch)` stores `fetch` and calls the two seams below; `to_account_currency`/`convert_amount` take `fetch: bool = True` and pass it on; `_priced_legs` imports `expand_realized_legs` inside the function (no `core/tracking` import at module load). `fx` stays read at call time (`from swingbot.core.marketdata import fx`).

```python
def quote_code(ticker, *, fetch: bool = True) -> str | None:
    """fetch=True calls the one-argument form so seams pinned as `lambda ticker:` keep working."""
    return fx.quote_currency_code(ticker) if fetch else fx.quote_currency_code(ticker, fetch=False)


def rate(from_code: str, to_code: str, on, *, fetch: bool = True) -> float | None:
    return fx.fx_rate(from_code, to_code, on) if fetch else fx.fx_rate(from_code, to_code, on, refresh=False)
```

`money.py` keeps its docstring and becomes: `MONEY_FIELDS = fx_convert.MONEY_FIELDS`; `missing_count = fx_convert.missing_count`; `to_account_currency(rows, *, account=None)` and `convert_amount(amount, ticker, on, *, account=None)` call `fx_convert.<same>(..., fetch=not admin_refresh.refresher_on())`, reading `fx_convert.<name>` at call time (the wrapper test patches it). In `risk_read_model._quote_rate`, compute `fetch = not admin_refresh.refresher_on()` and replace the two `fx.` calls with `fx_convert.quote_code(ticker, fetch=fetch)` and `fx_convert.rate(quote, account, on, fetch=fetch)`; the `except`/`_WeightError` mapping stays.

- [ ] **Step 5: Run the new test and every existing FX/money consumer**

Run: `python <wt>/scripts/dev/testrun.py file tests/marketdata/test_fx_persisted.py`, then `tests/marketdata/test_fx.py`, `tests/admin/test_api_v1_money.py`, `tests/admin/test_risk_read_model.py`, `tests/admin/test_api_v1_risk.py`, `tests/admin/test_api_v1_dashboard.py`, `tests/analytics/test_pnl_calendar.py`
Expected: all PASS (the admin ones run with `MARKETDATA_LAYER` off, so `fetch=True`, today's path).

- [ ] **Step 6: Commit**

```bash
git -C <wt> add swingbot/core/marketdata/fx.py swingbot/core/marketdata/fx_convert.py swingbot/admin/api_v1/money.py swingbot/admin/api_v1/risk_read_model.py tests/marketdata/test_fx_persisted.py
git -C <wt> commit -m "feat(v201): persisted quote-currency codes, never-fetch FX reads, conversion in core"
```

# Phase 3: The refresher process

### Task V201-5: Refresher process: advisory lock, cadence loop, symbol set, heartbeat, queue prune, entry point

**Model:** opus — a new long-running production process; lock, cadence and failure handling decide whether a dead refresher can look like a quiet market.

**Files:**
- Create: `swingbot/refresher/__init__.py` (docstring only: the v201 process, `python -m swingbot.refresher`, never imported by bot or admin)
- Create: `swingbot/refresher/__main__.py`
- Create: `swingbot/refresher/lock.py`
- Create: `swingbot/refresher/symbols.py`
- Create: `swingbot/refresher/loop.py`
- Test: `tests/refresher/test_lock.py`, `tests/refresher/test_symbols.py`, `tests/refresher/test_loop.py`

**Interfaces:**
- Consumes: `admin_refresh.cadence_s`, `HEARTBEAT_KEY`, `QUEUE_KIND_QUOTE/SNAPSHOT`, `QUEUE_RETENTION_S`; `session.session_state` (V201-1); `refresh_queue_repo().take/prune`, `refresher_heartbeat_repo().beat`, `market_refresh.HEARTBEAT_KEY` (V201-3).
- Produces (ledger): `lock.ADVISORY_LOCK_KEY = 201001`; `lock.single_instance() -> ContextManager[bool]`. `symbols.SymbolSet(quotes: tuple[str, ...], index: tuple[str, ...])` (frozen); `symbols.symbol_set() -> SymbolSet`. `loop.CycleReport`, `loop.CycleContext` (fields exactly as the ledger; `CycleReport` fields after `cadence_s` default to `()`/`0`/`None`/`False`), `loop.STEPS: list[Callable[[CycleContext], None]]`, `loop.run_cycle(now=None) -> CycleReport`, `loop.run_forever(stop: threading.Event) -> None`, `__main__.main() -> int`. Also: `loop.LOCK_RETRY_S = 30.0`, `loop.QUEUE_POLL_S = 5.0`, `loop.QUEUE_TAKE_LIMIT = 500`, the seam `loop._wait(stop, seconds)`, and the rule **a cycle between full cadences carries `SymbolSet((), ())` and only the queued keys**, so a user's Refresh is served within `QUEUE_POLL_S` without refetching the whole set. **The process never exits on a database error**, missing tables included: `deploy/deploy.sh` runs `up --wait` before `alembic upgrade`, so the first cycles can meet a schema without the v201 tables. **Every inner tick (`QUEUE_POLL_S`) reloads a changed `.env` and re-reads the cadence**, so a flag or cadence change, or a queued Refresh while the market is closed, never waits out a 30-minute cadence. V201-6 appends its steps to `STEPS` and its NOTIFY to `run_cycle`'s tail.

- [ ] **Step 1: Write the failing tests**

`tests/refresher/test_lock.py`:

```python
"""v201: only one refresher fetches (Postgres session advisory lock)."""
from swingbot.refresher import lock


def test_second_holder_is_refused_until_the_first_releases():
    with lock.single_instance() as first:
        with lock.single_instance() as second:
            assert (first, second) == (True, False)
    with lock.single_instance() as again:
        assert again is True
    assert lock.ADVISORY_LOCK_KEY == 201001
```

`tests/refresher/test_symbols.py`:

```python
"""v201: the refresher's symbol set -- open trades, open plans, watchlist, tape."""
from swingbot.core.marketdata.shared import tape
from swingbot.refresher import symbols


def test_union_is_upper_cased_deduped_sorted_and_the_tape_is_separate(monkeypatch):
    monkeypatch.setattr(symbols, "_open_trade_tickers", lambda: ["aapl", " MSFT ", None])
    monkeypatch.setattr(symbols, "_open_plan_tickers", lambda: ["MSFT", "nvda", ""])
    monkeypatch.setattr(symbols, "_watchlist", lambda: ["AAPL", "XAUUSD", "^GSPC"])
    got = symbols.symbol_set()
    assert got.quotes == ("AAPL", "MSFT", "NVDA", "XAUUSD")
    assert got.index == tuple(tape.TAPE_FIXED)


def test_empty_book_still_refreshes_the_tape(monkeypatch):
    for name in ("_open_trade_tickers", "_open_plan_tickers", "_watchlist"):
        monkeypatch.setattr(symbols, name, lambda: [])
    assert symbols.symbol_set() == symbols.SymbolSet((), tuple(tape.TAPE_FIXED))
```

`tests/refresher/test_loop.py`:

```python
"""v201: one refresher cycle -- context, steps, heartbeat, prune -- and the lock loop."""
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot.core.db.repositories import market_refresh
from swingbot.core.marketdata.shared import admin_refresh
from swingbot.refresher import __main__ as entry
from swingbot.refresher import loop
from swingbot.refresher.symbols import SymbolSet

UTC = timezone.utc
REGULAR = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)


class FakeQueue:
    def __init__(self):
        self.rows, self.pruned = [], []

    def take(self, limit, *, conn=None):
        out, self.rows = self.rows[:limit], self.rows[limit:]
        return out

    def prune(self, older_than, *, conn=None):
        self.pruned.append(older_than)
        return 0


class FakeBeat:
    def __init__(self):
        self.beats = []

    def beat(self, **kw):
        self.beats.append(kw)


@pytest.fixture
def env(monkeypatch):
    queue, beat = FakeQueue(), FakeBeat()
    monkeypatch.setattr(loop, "refresh_queue_repo", lambda: queue)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", lambda: beat)
    monkeypatch.setattr(loop, "symbol_set", lambda: SymbolSet(("AAPL",), ("^GSPC",)))
    monkeypatch.setattr(loop, "_scan_running", lambda: False)
    monkeypatch.setattr(loop, "STEPS", [])
    monkeypatch.setattr(loop, "_last_full", None)
    return SimpleNamespace(queue=queue, beat=beat)


def test_cycle_builds_its_context_runs_steps_beats_and_prunes(env):
    env.queue.rows = [{"kind": "quote", "key": "NEW", "priority": 0},
                      {"kind": "snapshot", "key": "risk", "priority": 0}]
    seen = []
    loop.STEPS.append(seen.append)
    report = loop.run_cycle(REGULAR)
    [ctx] = seen
    assert (ctx.session, ctx.symbols.quotes, ctx.symbols.index) == ("regular", ("AAPL",), ("^GSPC",))
    assert (ctx.queued_quotes, ctx.queued_snapshots, ctx.scan_running) == (["NEW"], ["risk"], False)
    assert ctx.report is report and report.cadence_s == 30.0 and report.error is None
    [beat] = env.beat.beats
    assert (beat["session"], beat["cadence_s"], beat["last_error"]) == ("regular", 30.0, None)
    assert env.queue.pruned == [REGULAR - timedelta(seconds=3600)]


def test_a_failing_step_is_recorded_and_later_steps_still_run(env):
    ran = []

    def bad(ctx):
        raise RuntimeError("provider down")
    loop.STEPS.extend([bad, ran.append])
    report = loop.run_cycle(REGULAR)
    assert ran and report.error == "RuntimeError: provider down"
    assert env.beat.beats[-1]["last_error"] == "RuntimeError: provider down"


def test_between_full_cycles_only_the_queue_is_served(env):
    seen = []
    loop.STEPS.append(seen.append)
    for offset in (0, 5, 30):
        loop.run_cycle(REGULAR + timedelta(seconds=offset))
    assert [c.symbols for c in seen] == [
        SymbolSet(("AAPL",), ("^GSPC",)), SymbolSet((), ()), SymbolSet(("AAPL",), ("^GSPC",))]


def test_cadence_follows_the_session(env):
    assert loop.run_cycle(datetime(2026, 10, 31, 15, 0, tzinfo=UTC)).cadence_s == 1800.0
    assert loop.run_cycle(datetime(2026, 10, 28, 12, 0, tzinfo=UTC)).session == "extended"


def test_db_down_still_returns_a_report(env, monkeypatch):
    def down():
        raise RuntimeError("db down")
    monkeypatch.setattr(loop, "symbol_set", down)
    monkeypatch.setattr(loop, "refresher_heartbeat_repo", down)
    report = loop.run_cycle(REGULAR)
    assert report.error == "RuntimeError: db down" and report.session == "regular"


def test_missing_tables_never_end_the_cycle(env, monkeypatch):
    import sqlalchemy as sa

    def no_table(*_a, **_k):
        raise sa.exc.ProgrammingError("SELECT", {}, Exception('relation "market_refresh_queue" does not exist'))
    monkeypatch.setattr(env.queue, "take", no_table)
    monkeypatch.setattr(env.queue, "prune", no_table)
    report = loop.run_cycle(REGULAR)
    assert report.error.startswith("ProgrammingError") and env.beat.beats


def test_inner_tick_reloads_env_and_returns_when_the_queue_has_work(monkeypatch):
    import time
    reloads, ticks = [], []
    pending = iter([False, False, True])
    monkeypatch.setattr(loop, "_reload_if_env_changed", lambda: reloads.append(1))
    monkeypatch.setattr(loop, "_queue_pending", lambda: next(pending))
    monkeypatch.setattr(loop, "_wait", lambda stop, seconds: ticks.append(seconds))
    monkeypatch.setattr(loop.session, "session_state", lambda now=None: "closed")   # 1800 s cadence
    loop._sleep_until_due(threading.Event(), time.monotonic())
    assert ticks == [loop.QUEUE_POLL_S] * 3 and len(reloads) == 3


def test_second_instance_does_not_fetch(monkeypatch):
    cycles, waits = [], []

    @contextmanager
    def refused():
        yield False
    monkeypatch.setattr(loop.lock, "single_instance", refused)
    monkeypatch.setattr(loop, "run_cycle", lambda now=None: cycles.append(now))
    monkeypatch.setattr(loop, "_wait", lambda stop, seconds: (waits.append(seconds), stop.set()))
    loop.run_forever(threading.Event())
    assert cycles == [] and waits == [loop.LOCK_RETRY_S]


def test_heartbeat_key_matches_the_contract():
    assert market_refresh.HEARTBEAT_KEY == admin_refresh.HEARTBEAT_KEY == "refresher"


def test_main_runs_the_loop_with_a_stop_event(monkeypatch):
    got = []
    monkeypatch.setattr(entry.loop, "run_forever", got.append)
    assert entry.main() == 0 and isinstance(got[0], threading.Event)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/refresher/test_loop.py` (and `test_lock.py`, `test_symbols.py`)
Expected: FAIL (`ModuleNotFoundError: No module named 'swingbot.refresher'`).

- [ ] **Step 3: `lock.py` and `symbols.py`**

```python
"""v201: one refresher at a time. A session-level advisory lock held on one
dedicated connection for as long as the block runs; a second container during a
compose recreate gets False and fetches nothing."""
from contextlib import contextmanager
from typing import Iterator

import sqlalchemy as sa

from swingbot.core.db import engine

ADVISORY_LOCK_KEY = 201001


@contextmanager
def single_instance() -> Iterator[bool]:
    conn = engine.get_engine().connect()
    held = False
    try:
        held = bool(conn.execute(sa.text("SELECT pg_try_advisory_lock(:k)"),
                                 {"k": ADVISORY_LOCK_KEY}).scalar())
        conn.commit()
        yield held
    finally:
        if held:
            conn.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            conn.commit()
        conn.close()
```

`symbols.py`: the frozen `SymbolSet` dataclass; three private readers `_open_trade_tickers()` (`trades_repo().open_trades()` rows' `"ticker"`), `_open_plan_tickers()` (`plans_repo().open_plans()` dicts' `"ticker"`), `_watchlist()` (`watchlist.load_watchlist()`); `symbol_set()` upper-cases and strips every ticker, drops blanks and `tape.TAPE_FIXED` members, returns `SymbolSet(tuple(sorted(...)), tuple(tape.TAPE_FIXED))`.

- [ ] **Step 4: `loop.py`**

Module docstring: one cycle = context, `STEPS` in order (each failure recorded in `report.error`, never stopping the others), queue prune, heartbeat; nothing here ever raises out of `run_cycle`. Module-level imports of `refresh_queue_repo`, `refresher_heartbeat_repo`, `symbol_set`, `lock` (the tests patch them on `loop`). `_last_full: datetime | None = None`.

```python
def run_cycle(now: datetime | None = None) -> CycleReport:
    global _last_full
    now = now or datetime.now(timezone.utc)
    state = session.session_state(now)
    report = CycleReport(session=state, cadence_s=admin_refresh.cadence_s(state))
    started = time.monotonic()
    try:
        full = _last_full is None or (now - _last_full).total_seconds() >= report.cadence_s - 1.0
        ctx = _context(now, state, report, full=full)
        if full:
            _last_full = now
        _run_steps(ctx)
    except Exception as exc:  # noqa: BLE001 - a cycle never kills the process
        report.error = _describe(exc)
        swallowed(log, "refresher.cycle", exc, level=logging.WARNING)
    _guard("refresher.prune", lambda: refresh_queue_repo().prune(
        now - timedelta(seconds=admin_refresh.QUEUE_RETENTION_S)))
    _guard("refresher.heartbeat", lambda: refresher_heartbeat_repo().beat(
        cadence_s=report.cadence_s, session=state, last_error=report.error, now=now,
        cycle_ms=int((time.monotonic() - started) * 1000)))
    return report
```

`_describe(exc) -> str` is `f"{type(exc).__name__}: {exc}"`. `_guard(tag, fn)` calls `fn()` and `swallowed`s any exception. `_run_steps(ctx)` loops `list(STEPS)`, records the first failure's `_describe` in `ctx.report.error` (a later failure does not overwrite it) and continues. `_context` takes `refresh_queue_repo().take(QUEUE_TAKE_LIMIT)`, splits keys by `kind` into `queued_quotes` / `queued_snapshots`, uses `symbol_set()` when `full` else `SymbolSet((), ())`, and `_scan_running()` (`runstate.is_scan_running()` imported inside, any exception → `False`).

```python
def run_forever(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with lock.single_instance() as held:
                if not held:
                    log.info("another refresher holds lock %s; retrying", lock.ADVISORY_LOCK_KEY)
                    _wait(stop, LOCK_RETRY_S)
                    continue
                _serve(stop)
        except Exception as exc:  # noqa: BLE001 - DB down at start: back off, retry
            swallowed(log, "refresher.lock", exc, level=logging.WARNING)
            _wait(stop, LOCK_RETRY_S)
```

`_serve(stop)`: `while not stop.is_set(): started = time.monotonic(); run_cycle(); _sleep_until_due(stop, started)`. `_sleep_until_due(stop, started: float)` loops while `not stop.is_set()`: `_wait(stop, QUEUE_POLL_S)`, then `_reload_if_env_changed()`, then returns when `_queue_pending()` is true or `time.monotonic() - started >= admin_refresh.cadence_s(session.session_state())` (cadence re-read every tick, so a reloaded cadence or a session change takes effect at once). `_reload_if_env_changed()` calls `config.reload()` when `config._env_signature() != config._ENV_MTIME` (the signature `reload()` itself stores; no SIGHUP reaches this container from `scripts/ops/env_set.py`). `_queue_pending()` is one `SELECT EXISTS (... market_refresh_queue WHERE taken_at IS NULL)` on `engine.get_engine()`. Both swallow every exception (a missing table reads as `False`; a bad `.env` keeps the old values). `_wait(stop, seconds)` is `stop.wait(seconds)`.

- [ ] **Step 5: `__main__.py`**

```python
"""v201: `python -m swingbot.refresher` -- the refresher compose service's entry point."""
import logging
import signal
import threading

from swingbot import config
from swingbot.refresher import loop


def main() -> int:
    logging.basicConfig(level=getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, lambda *_: config.reload())
    loop.run_forever(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

(Use the same config-reload entry point the bot's SIGHUP handler calls; `git -C <wt> grep -n "SIGHUP" bot.py swingbot` names it. Never call `yf_safe.set_default_lock_timeout`.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python <wt>/scripts/dev/testrun.py file tests/refresher/test_lock.py`, `... file tests/refresher/test_symbols.py`, `... file tests/refresher/test_loop.py`; then `python <wt>/scripts/dev/complexity_gate.py`
Expected: all PASS; gate clean.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/refresher/__init__.py swingbot/refresher/__main__.py swingbot/refresher/lock.py swingbot/refresher/symbols.py swingbot/refresher/loop.py tests/refresher/test_lock.py tests/refresher/test_symbols.py tests/refresher/test_loop.py
git -C <wt> commit -m "feat(v201): refresher process -- advisory lock, cadence loop, symbol set, heartbeat"
```

