# v67 — JSON files to PostgreSQL

**Version:** ui 1.9.2 · bot 1.5.0
**Bump:** bot minor (1.5.0 → 1.6.0) · ui patch (1.9.2 → 1.9.3)
**Edge:** none (integrity)

Replace the `data/*.json` persistence layer with PostgreSQL, keeping the
schema as free to change as a Python dict is today.

## Why now

Two reasons, one of them a live bug.

**The bug.** `TradeLog._save()` (`swingbot/core/tracking/performance.py:360`)
and `PlanStore._save()` (`swingbot/core/planning/plan_store.py:59`) serialize
an entire in-memory list over the whole file on every write. Their only guard
is a module-level `threading.Lock`, which protects nothing across processes —
and the bot and admin run as **separate containers sharing a bind-mounted
`data/`** (`docker-compose.yml:63,120`). Both stores' own `reload()` docstrings
describe the consequence: a stale snapshot "serializes that stale list and
clobbers trades.json, erasing every trade logged elsewhere in the meantime."
`reload()` exists solely to narrow that window; it does not close it. Every
expectancy and win-rate number this repo reports is derived from the file that
race can silently truncate.

**The churn.** `v39` (runner floor), `v50` (closed-trade attribution), `v52`
(registry evidence integrity) and `v58` (partial-plan reframe) each reshaped
the trade or plan record. The data model changes roughly once per plan, so any
design requiring a migration per field change is the wrong design here.

This spec buys **no edge**. It does not improve expectancy, and under
`CLAUDE.md`'s priority rule it ranks below algorithm work. Its justification is
narrower and worth stating plainly: it protects the record that every edge
measurement reads from, and removes a class of silent data loss.

## Decisions taken

Settled during the brainstorm; recorded so the plan does not reopen them.

| Question | Decision |
|---|---|
| Engine | PostgreSQL 18 (`postgres:18-alpine`), one added container |
| Schema shape | Hybrid: promoted typed columns + `doc JSONB` |
| Access layer | SQLAlchemy Core + repositories returning plain dicts |
| Cutover | Store-by-store strangler, per-store flag |
| Config | Non-sensitive settings → DB; secrets stay in `.env` |
| Evidence files | `validation_registry.json`, `sp500.json`, `etfs.json` stay in git |
| Bulk market data | `market_data/`, `backtest_cache/*.csv`, `exports/` stay as files |
| DB unreachable | Fail fast; Docker `restart: unless-stopped` recovers |
| Live UI updates | `LISTEN/NOTIFY` replaces the mtime watcher |
| Backups | Nightly `pg_dump` to host + retention, plus a JSON export endpoint |
| Analytics | Behavior-preserving; SQL pushdown deferred to its own plan |
| Tests | Real Postgres, per-test transaction rollback |

### Why Postgres and not SQLite or Mongo

SQLite is the smaller answer and would work for this write volume, but it has
no `LISTEN/NOTIFY` (the SSE watcher would stay a polling loop), weaker JSON
indexing, and a less comfortable story for two containers writing the same
file over a bind mount — which is the exact failure being fixed. MongoDB is
the reflexive answer to "the schema changes constantly," but JSONB delivers
nearly the same freedom while keeping SQL, which this repo's analytics and
backtesting work lean on constantly. One extra container was accepted as the
cost; Postgres is what that budget buys the most with.

## 1. Schema strategy — the doc/column codec

This is the mechanism that delivers the flexibility requirement, and the one
piece of the design everything else depends on.

Each table has a set of **promoted** columns — the fields that are stable,
queried, sorted, or constrained — plus a `doc JSONB` column holding everything
else:

```sql
CREATE TABLE trades (
  id         BIGSERIAL PRIMARY KEY,
  trade_id   TEXT UNIQUE NOT NULL,
  ticker     TEXT NOT NULL,
  strategy   TEXT NOT NULL,
  horizon    TEXT NOT NULL,
  direction  TEXT NOT NULL,
  status     TEXT NOT NULL,
  opened_at  TIMESTAMPTZ NOT NULL,
  closed_at  TIMESTAMPTZ,
  entry      NUMERIC,
  stop_loss  NUMERIC,
  doc        JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX trades_ticker_opened_idx ON trades (ticker, opened_at DESC);
CREATE INDEX trades_doc_gin           ON trades USING GIN (doc);
```

`swingbot/core/db/codec.py` provides the two halves:

- `split_doc(record, promoted)` → `(columns: dict, doc: dict)`. Pops promoted
  keys into columns; everything else goes to `doc`.
- `merge_doc(row, promoted)` → one flat dict, promoted columns merged back over
  `doc`.

**The property that matters:** call sites always see a single flat dict, exactly
as they do today. Adding a field is `t["gamma_flip"] = x` — no migration, no
model change, no serializer change — and it is queryable immediately as
`doc->>'gamma_flip'`. Promoting a field later is `ADD COLUMN` + a backfill +
one name added to `PROMOTED`, and **no call site changes**, because they were
never reading columns directly.

Promotion criteria, so the choice is not made by taste: promote a field when it
is filtered/sorted on in a hot path, needs a `NOT NULL`/`CHECK` constraint, or
participates in a foreign key. Everything else stays in `doc` indefinitely.
Starting promoted sets are deliberately small — under-promoting costs a slow
query, over-promoting costs a migration, and only the first is cheap to fix.

## 2. Architecture

One new package, `swingbot/core/db/`:

| Module | Responsibility |
|---|---|
| `engine.py` | Engine + pool built from `DATABASE_URL`; fail-fast connection policy |
| `schema.py` | SQLAlchemy Core `Table` definitions and `PROMOTED` tuples |
| `codec.py` | `split_doc` / `merge_doc` |
| `notify.py` | `NOTIFY` emission helpers and the listener loop |
| `migrations/` | Alembic env + versions |
| `repositories/` | One module per aggregate, returning plain dicts |

Existing store classes keep their names and public methods. `TradeLog` still
exposes `log_trade()`, `close_plan_trade()`, `append_leg_by_plan()`; only their
bodies change from `_load`/`_save` to repository calls. `reload()` on both
`TradeLog` and `PlanStore` is **deleted, not ported** — it exists only to
mitigate whole-file clobbering, which row-level `UPDATE ... WHERE trade_id = ?`
makes impossible. The blast radius stays inside the store classes.

`swingbot/core/infra/jsonio.py` survives the migration: the files that stay
(secrets, git-committed evidence) still need atomic writes.

## 3. Inventory

**Moves to Postgres (~28 stores).**

| Group | Stores | Current owner |
|---|---|---|
| Live trading state | trades, plans, starred_plans, account, journal, state, watchlist | `tracking/performance.py`, `planning/plan_store.py`, `commands/views.py:28`, `planning/account.py:85`, `analytics/journal.py:26`, `infra/state.py:24`, `admin/api_v1/watchlist.py:38` |
| Operational state | admin_jobs, scheduled_jobs, ui_preferences, killswitch, bot_heartbeat, manual_close_notify, settings_audit, ticker_directory, tuning_results + proposals, the four `.flag` files | `admin/jobs.py:97`, `commands/scanning/loops.py:558`, `admin/api_v1/system.py:520`, `core/edge/throttle.py`, `commands/scanning/runstate.py:9-15`, `admin/helpers.py:181`, `core/marketdata/ticker_directory.py`, `admin/queries.py:271,294` |
| Append-only logs | scan_telemetry, shadow_plans, retrospective_history | `core/backtesting/shadow_log.py:16`, `core/tracking/retrospective.py:52` |
| Derived / cache | analytics_snapshot, scan_snapshots, ticker_meta_cache, rs_cache, fold_trades | `core/analytics/snapshots.py:20`, `core/scanning/snapshots.py`, `core/edge/factors.py:17`, `core/scanning/analyze.py:141` |

**Stays as files.** `market_data/` and `data/backtest_cache/*.csv` (large,
regenerable, read by pandas directly); `exports/` chart images;
`validation_registry.json` (`core/backtesting/registry.py:21` — its value *is*
its git-auditable provenance, which a DB row with no diff and no reviewer would
destroy); `sp500.json` / `etfs.json` (static reference data belonging with the
code); `.env` and `.env.bak`; `data/admin_session_secret` (bootstrap secret);
`VERSION.json`.

The four `.flag` files are cross-container IPC, not data — `scan_running`,
`scan_paused`, `trigger_check`, `stop_scan`. They become rows in a
`runtime_flags` table, with `NOTIFY` replacing mtime detection so the bot reacts
immediately rather than on its next poll.

## 4. Settings

`swingbot/config.py` already carries the split this needs. `FIELDS` is a
declarative registry (`config.py:95`) where each `Field` (`config.py:73`) has
`sensitive: bool` and `hot_reloadable: bool`, and `reload()` (`config.py:909`)
updates module globals **in place** — so `config.XXX` readers everywhere see new
values without re-importing.

The change is therefore confined to where `reload()` sources values:

- `sensitive=True` fields resolve from `.env` only, unchanged.
- Every other field resolves **DB → `.env` → `Field.default`**, from a
  `settings` table (`key`, `value JSONB`, `updated_at`, `updated_by`).
- The admin settings page writes rows instead of rewriting `.env` in place.
  `_build_env_text` / `_write_env_text` (`admin/helpers.py:66,106`) narrow to
  secrets only; `import_env_text` (`:232`) keeps working for bulk secret import.
- A `NOTIFY settings` wakes the bot's listener, which calls `reload()`. SIGHUP
  is retained for `.env` secret changes.

Side effect worth having: pushing a settings change no longer needs the Docker
socket mounted into the admin container.

## 5. Live updates

`swingbot/admin/events/watcher.py:61` stat()s 19 paths every 0.5s and emits one
event per *concern* (`trades`, `account`, `analytics`, `scan`, `journal`, `bot`,
`risk`, `watchlist`, `jobs`). Triggers on the migrated tables emit `NOTIFY` on
those same channel names, and the watcher becomes a listener.

**The SPA contract does not change** — same event names, same semantics. The
polling loop, `_signature`, `_UNREADABLE` and `default_paths()` are deleted.
Debounce (`DEBOUNCE = 0.25`) is retained: a scan tick still writes several
tables in a burst and the client should refetch once, when it settles.

## 6. Failure behavior

A write that cannot reach Postgres **raises**. The container dies and
`restart: unless-stopped` brings it back.

This deliberately reverses `jsonio.py`'s degrade-don't-crash policy, and the
reversal is the point: a corrupt JSON file was a local, recoverable condition
worth surviving, whereas an unreachable local database means something is
genuinely wrong, and a trading bot that keeps posting alerts while silently
recording none of them is worse than one that is visibly down. Reads of
regenerable caches (`rs_cache`, `ticker_meta_cache`) may still fall back to
recomputation; reads of trading state may not.

## 7. Testing

Session-scoped Postgres via a `test` profile in `docker-compose.yml`. Per-test
isolation by opening a transaction in a fixture and rolling it back — faster
than schema-per-test and sufficient for everything except notifications.

`NOTIFY` fires only on commit, so notification tests need a separate tier that
commits and truncates between tests. That tier is small and marked slow.

`scripts/dev/testrun.py` gains a preflight that checks the test database is
reachable and fails with an actionable message rather than ~1150 confusing
errors. The existing `config.DATA_DIR`-to-`tmp_path` isolation stays for the
stores that remain file-based.

**Cost, stated honestly:** the fast tier will get slower. Connection reuse and
rollback isolation keep it bounded, but a database in the loop is not free, and
`docs/claude/testing-cost.md` will need its baseline updated once measured.

## 8. Deployment and backup

A `db` service on `postgres:18-alpine` with a named volume (`pgdata`), a
`pg_isready` healthcheck, and `depends_on: {db: {condition: service_healthy}}`
on both bot and admin. `DATABASE_URL` and `POSTGRES_PASSWORD` join `.env` as
sensitive fields.

Backups: a nightly `pg_dump` writing timestamped dumps into
`./data/backups/db/` — beside the existing `data/backups/env/` — keeping **14
days**, which covers a bad change surviving a week unnoticed without unbounded
disk growth. Restore is documented and **exercised once during the plan**, on a
throwaway database, because an unexercised restore is a hope, not a backup.

The admin UI gains a per-record JSON export so single trades and plans stay
inspectable without `psql` — replacing what `cat data/trades.json` gave.

`docs/deploy/DOCKER.md` and `docs/deploy/DEPLOY_HETZNER.md` are updated in the
same plan. Per `CLAUDE.md`, anything done live on the VM during cutover is
mirrored back into the repo and committed before the plan closes.

## 9. Migration sequencing

One plan, six parts (`_0-index` plus `_1`…`_6`), following the v54/v61/v62
precedent. Roughly 145 tasks.

| Part | Content | ~Tasks |
|---|---|---|
| 1 | Foundation: `core/db/` package, codec, Alembic, engine, compose service, test harness | 25 |
| 2 | Live trading state: 7 stores, importers, strangler flags | 35 |
| 3 | Operational state, flags, jobs, LISTEN/NOTIFY watcher replacement | 30 |
| 4 | Settings to DB, config resolution, admin settings page | 20 |
| 5 | Append-only logs, derived/cache stores | 20 |
| 6 | Production cutover, backup/restore drill, dead-path deletion, docs | 15 |

Every store migrates through the same five steps: repository + tests →
importer → dual-write → flip reads → delete the JSON path.

Stage selection is per store, not a global on/off, so a store mid-migration
does not block the others. `DB_STORES` is a comma-separated `name:stage`
mapping with `json` as the default for any store not listed:

```
DB_STORES=trades:db,plans:dual,journal:json
```

Stages are `json` (files only, today's behavior), `dual` (write both, read
files), and `db` (DB only). A store rolls back one stage by editing this value
and reloading — no redeploy — which is what makes each step independently
reversible while the suite stays green throughout.

Production data import runs as a **verified dry run first** — row counts, and a
field-level checksum comparing every imported record against its JSON source —
before the real run. Local `data/` has no `trades.json` or `plans.json`; the
only real history lives on the VM, so this is a one-shot operation on
irreplaceable data.

## 10. Success criteria

1. Every store in the inventory reads and writes Postgres; no code path reads
   the migrated JSON files.
2. Imported production data matches its JSON source exactly — equal row counts
   and equal per-record checksums.
3. Analytics outputs are **numerically identical** before and after. This is the
   primary evidence the migration was faithful, and it is why SQL pushdown is
   excluded from this plan: changing the storage and the aggregation together
   would leave a shifted number with two possible causes.
4. `python scripts/dev/testrun.py full` is green — `0 failed`, `0 xfailed`.
5. The SSE stream delivers the same event names with no SPA change.
6. A restore from `pg_dump` into an empty database has been performed and
   verified once.
7. Two concurrent writers (bot + admin) cannot lose an update — covered by an
   explicit regression test that fails against the current file-based stores.

## 11. Risks and limitations

- **Suite runtime regression.** Real and unavoidable; magnitude unknown until
  measured. Re-baseline `testing-cost.md` rather than hiding it.
- **One-shot production import.** Mitigated by the dry run and checksums, but
  the underlying data is irreplaceable. Take a `data/` tarball before cutover.
- **Config becoming dynamic.** Any module that captured a `config.XXX` value at
  import time will hold a stale setting. `reload()`'s in-place mutation already
  makes this a pre-existing hazard; the DB-backed path widens the window. The
  plan greps for import-time captures of `FIELDS`-backed attributes.
- **Trigger maintenance.** Every new table needing live updates also needs its
  `NOTIFY` trigger. A test asserts every table in `WATCHED_EVENTS` has one.
- **No edge.** This plan competes with algorithm work for the same finite
  attention and buys zero expectancy. Accepted deliberately.

## Parallelisation

- **Sequential:** Part 1 before everything. It introduces `codec.py`,
  `schema.py` and the test harness that every later part consumes — a contract
  dependency, not merely an ordering preference.
- **Parts 2–5 (parallel across parts, sequential within).** Each part owns a
  disjoint set of store modules and its own Alembic revisions. Within a part,
  the five migration steps for one store are a strict chain — each consumes the
  previous step's schema or flag state.
- **Group 2a (parallel):** trades, plans, starred_plans — disjoint files
  (`tracking/performance.py`, `planning/plan_store.py`, `commands/views.py`).
- **Group 2b (parallel):** account, journal, state, watchlist — one module each.
- **Sequential inside Part 3:** the watcher rewrite lands *after* every
  operational store it listens to, since its test asserts against tables those
  tasks create.
- **Sequential:** Part 6 after all of 2–5. Cutover cannot precede the stores it
  cuts over, and the dead-path deletion needs every reader already migrated.
- **Alembic revision conflicts** are the one cross-part hazard: parallel parts
  autogenerating revisions concurrently produce multiple heads. Every revision
  is created with an explicit part-prefixed id (`alembic revision
  --rev-id p3_004`) rather than a random hash, so a collision is a visible name
  clash instead of a silent branch. Part 6 asserts `alembic heads` returns
  exactly one; a genuine branch is resolved with a merge revision, never by
  editing a `down_revision` that has already run anywhere.
