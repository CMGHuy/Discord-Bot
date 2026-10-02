# v116 — Postgres cutover with whole-bot point-in-time rollback

**Version:** ui 1.21.0 · bot 1.11.1
**Bump:** bot major — after Phase 4 the bot no longer starts from `data/*.json`; an install that has not imported into Postgres breaks (`working-conventions.md` § Major). ui none — the SSE contract and every screen stay the same.
**Edge:** none (integrity)

Supersedes the unbuilt remainder of v67
(`plans/implemented/2026-08-29-v67-json-to-postgres_0-index.md`, closed
2026-09-30). v67's spec stays the reference for the hybrid-schema design this
spec builds on (`specs/implemented/2026-08-29-v67-json-to-postgres-design.md`).

> **Corrections found while planning (2026-09-30).** The plan follows these,
> not the text below. Full list: plan `_0-index` § Spec points.
> - `PROMOTED` lives in `schema.py`, so the promotion reasons go in a
>   `PROMOTION_REASONS` dict there.
> - The branch's listener does not reconnect, so V116-15 builds reconnect and
>   `resync`.
> - GHCR keeps tags for only 14 days; V116-02 raises that to 45.
> - Nothing logs "dual divergence" lines, so the soak check counts database
>   exception lines instead.
> - `market_data_state` raised no SSE event; it now raises `watchlist`.
> - Two bugs would have broken the ops flip, and V116-22 fixes both: at
>   `heartbeat:db` the heartbeat was still read from the file, and at
>   `notify_queue:dual` the table was never drained.
> - The watchlist/state dual history does not shorten the reference group's
>   gate, because the group flips as one.

## Why this

v67 built the foundation: `swingbot/core/db/` (codec, engine, Alembic,
`stages`, `notify`), 18 repositories, `scripts/db/parity_report.py`, and
dual/db branches in every trading and operational store. It stopped there.
Production still runs `DB_STORES=watchlist:dual,state:dual`, and every other
store is JSON-only. Its remaining ~70 tasks included settings-in-DB,
data-access tooling, a round-trip publish, and moving logs and caches. The
partner judged that too much for what is needed.

What is needed, with the partner's decisions (brainstorm, 2026-09-30):

1. **Finish the move.** Every trading and operational store reads and writes
   Postgres only, and the JSON persistence paths are deleted.
2. **Stay on Postgres + JSONB, not NoSQL.** The data model changes about once
   per plan (v39, v50, v52, v58 reshaped trades and plans). The hybrid `doc
   JSONB` column already absorbs that: adding a field needs no migration.
   Postgres adds what a document store would make harder: one transaction
   across trade, plan and account; SQL and pandas access; and LISTEN/NOTIFY
   for live updates.
3. **Keep structure change cheap, and prove it stays cheap.**
4. **Roll the whole bot back to any second in the last 30 days.** That covers
   data, including every issued trade, plan, journal entry and the account;
   the code that was running; `.env`; and `market_data/`.

## Scope

**In:**
- Phase 0: point-in-time rollback.
- Phase 1: live events, which is mostly built already, see below.
- Phase 2: schema-change guarantees.
- Phase 3: staged production flip.
- Phase 4: deletion.

**Out (these stay files or stay unbuilt):**
- settings in the DB; `.env` stays the single config source
- data-access and tunnel tooling
- local→prod publish
- `scan_telemetry.jsonl`, `shadow_plans.jsonl`, analytics snapshots, `rs_cache`, `ticker_meta_cache`, `earnings_history.json`
- `market_data/`, `data/backtest_cache/`, `exports/`, `validation_registry.json`, `sp500.json`, `etfs.json`, `VERSION.json`

## Already built — start from it, do not rebuild

Branch `2026-09-30-v67-p3-18-notify-events` (worktree of the same name, tip
`b31835b9`, unmerged, 10 commits) implements v67 P3-18…P3-24:
- `p3_007_notify_triggers` on every event-raising table
- `swingbot/admin/events/db_listener.py`, with the broker building it
- admin trigger/pause buttons routed through `runstate` (the flag-file gap)
- tests pinning the SSE contract, the end-to-end live path, "nothing polls a
  table-backed file at db", and the Part 3 exit criteria

`main` has moved since the branch was cut. Phase 1's first task is to review
the branch, rebase or merge it onto `main`, and bring the gate back to green.
It is not a rebuild.

# Phase 0 — Point-in-time rollback

**This phase lands and is drilled before any store flips to `db`.** A store at
`db` has no JSON copy left to fall back on, so the recovery path has to exist
first.

**Storage.** Everything lives on the VM disk under `/opt/swing-bot/backups/`.
This was the partner's choice, knowing the trade-off: it protects against a bad
deploy, bad data or a bad migration, **not against losing the VM**. Retention
is 30 days of point-in-time history. Measured 2026-09-30: `market_data/` is
173 MB in 499 files, `data/` is 89 MB, and the disk has 13 GB free.

## Postgres

- **Custom image.** `Dockerfile.db` builds `FROM postgres:18-alpine` and adds
  `pgbackrest`. CI builds and pushes it next to the bot image, because the
  server does not build (`DEPLOY_HETZNER.md`). The major version stays pinned.
- **WAL archiving.** `archive_mode=on`, and `archive_command` goes through
  pgBackRest into repo `/opt/swing-bot/backups/pitr`. That is a host bind
  mount, **outside** the database volume. Compression is on, which matters:
  every forced WAL switch archives a 16 MB segment, so an uncompressed archive
  would not fit.
- **Worst-case loss.** `archive_timeout=300`, so at most five minutes of data
  can be lost.
- **Backup schedule.** A full backup weekly and a differential nightly, with
  `repo1-retention-full` set so that 30 days of point-in-time history stay
  restorable.
- **Second, independent method.** `backup_db.sh` (`pg_dump`) stays, and its
  retention goes from 14 to 90 days. It gives day-level restores beyond the
  30-day window.

## Code

- CI already tags every image `sha-<12>` on GHCR.
- `deploy/deploy.sh` appends one JSON line to
  `backups/deploys.jsonl`: `{ts, git_sha, bot_image, db_image}`.
- A rollback pulls the recorded tag from GHCR. It does not depend on the server
  keeping the image locally, because CI's cleanup job prunes old images there.
- A task confirms that GHCR keeps `sha-*` tags for at least 30 days, and
  records the retention it found.

## Config

- **When a version is taken.** Both change paths snapshot `.env`: the admin
  settings save (`swingbot/admin/helpers.py`, which also sends the SIGHUP) and
  `deploy.sh`.
- **How it is copied.** The snapshot goes to `backups/env/<UTC ts>.env` when the
  content hash changed. It is taken with `cp`, never `sed -i`, because `.env` is
  bind-mounted (see the memory note on that trap).
- **Protection and retention.** The directory is `chmod 700`, because the files
  hold secrets. Retention is 30 days.

## market_data

- An hourly cron runs `restic backup market_data/` into a local repo at
  `backups/restic`.
- After it, `restic forget --keep-within 30d --prune` removes older snapshots.
- The restic password lives in the VM `.env` and is mirrored as a placeholder in
  `.env.example`.

## `scripts/ops/rollback_to.sh "<UTC timestamp>" [--dry-run]`

1. **Refuse** a target older than the oldest restorable point, or in the future.
2. **Take a checkpoint of now:** a differential backup, a restic snapshot and a
   `.env` copy. This makes the rollback itself undoable. PITR opens a new
   timeline, so a later restore can still target any time on the old one.
3. **Resolve the artifacts current at the target:** the last `deploys.jsonl`
   line ≤ target, the last `.env` version ≤ target, and the last restic
   snapshot ≤ target. Print them. `--dry-run` stops here.
4. **Stop the services:** `docker compose stop bot admin`.
5. **Restore market_data.** Use `restic restore`, and swap the directory in
   atomically.
6. **Restore config and code.** Put back the chosen `.env` version and pin
   `SWING_BOT_IMAGE` and the db image to the recorded tags.
7. **Restore Postgres to the second:** `pgbackrest restore --delta
   --type=time --target=<ts> --target-action=promote`.
8. **Pause scanning before the bot starts.** Set the pause flag in the restored
   database first. Otherwise the bot re-posts alerts for setups it had already
   alerted on after the target time. The partner unpauses from the admin UI.
9. **Start and verify.** Start the stack, run `parity_report` (no-op at `db`),
   the health check and an Alembic-head check. Then print what came back from
   which time.

**Not rolled back, by design:** Discord messages already posted; logs,
telemetry and caches. Those are append-only or regenerable.

## Proof

- **The drill.** A task restores to a chosen past second into a *scratch*
  compose project on the VM, on a different port and volume. It checks that a
  known trade or plan record carries exactly the value it had at that second,
  and records the drill in `docs/deploy/DB_RESTORE.md`.
- **The monthly cron.** It runs `pgbackrest verify` and `restic check`, and
  logs to `logs/pitr_verify.log`.
- **Alarms.** An alarm fires on `pg_stat_archiver.failed_count` growth and on
  backups-disk usage above 80%. Both go to the ops Discord channel through the
  existing notification registry. A failing `archive_command` piles WAL up on
  the database disk, so the archiver alarm is not optional.

# Phase 1 — Live events

1. **Merge the branch** above: review it, bring it onto `main`, and re-run its
   tests plus the fast tier.
2. **Two new tables for the last files that drive live updates.**
   - `scan_progress` (writer: `swingbot/core/scanning/progress_store.py`) and
     `market_data_state` (writer: `swingbot/core/marketdata/data_refresh.py`).
   - Shape: a key, `doc JSONB`, `updated_at`, and the same NOTIFY trigger as
     the other tables.
   - Both go through `stages` like every other store. They hold ephemeral
     state, so there is no import: at `db` they start empty.
3. **The listener reconnects** with backoff. On reconnect it emits one
   `resync` SSE event and the SPA refetches, so a notification missed while
   disconnected is never silently lost. If the branch already does this, the
   task only adds the test.
4. **The file watcher is deleted in Phase 4, not here.** Stores still at
   `json`/`dual` need it until they flip.

# Phase 2 — Schema-change guarantees

The partner's requirement is that data structure can keep changing quickly.
The codec (`split_doc`/`merge_doc`) already delivers that; this phase stops it
eroding.

**Schema contract test.** It reflects every table in `swingbot/core/db/schema.py`
and requires:
- `doc JSONB NOT NULL DEFAULT '{}'`
- `updated_at TIMESTAMPTZ`
- that each promoted column is listed in its repository's `PROMOTED` with a
  one-line reason

A new table without `doc` fails the test.

**Unknown-field round-trip.** For every repository, a record carrying a field
no code has ever seen is written through the repository and read back
unchanged. Nested structures and lists are included.

**Rename and drop helpers.**
- `rename_doc_field(table, old, new)` and `drop_doc_field(table, name)` go in a
  small module used inside Alembic data revisions.
- The rename's downgrade reverses it.
- The drop snapshots the dropped values into a side table first, so its
  downgrade restores them.
- Both are tested up and down against the test database.

**Recipe doc.** `docs/claude/schema-evolution.md` gets a table row in
`CLAUDE.md`. It covers four operations:
- **add:** just write the field
- **rename:** a data revision using the helper
- **drop:** a data revision using the helper
- **promote:** `ADD COLUMN`, a backfill, and a `PROMOTED` entry, with the doc
  copy kept

**No read-time upcasting.** A shape change is applied once, by a revision, so
there is only one code path per field.

**Revision ids.** Phase revisions use the `v116_NNN` prefix, and
`tests/db/test_migrations.py::ID_RE` is widened to accept `v\d+_\d{3}` as well
as the existing `p[1-6]_\d{3}`. There is still one head at all times.

# Phase 3 — Staged production flip

Every step below touches production and goes through `scripts/ops/ssh-hetzner.sh`.
Each `.env` edit is made in place and then verified, never with `sed -i`, and
is mirrored into the repo.

**Rollback readiness first.**
- `scripts/db/export_json.py` gains shapers for every Part 3 store and the two
  new tables. Today it has none for Part 3.
- A round-trip test per store runs against a pulled production snapshot, not a
  fixture: write the record, read it back through the repository, compare.
  These tests are committed. This is the `schema-change` skill's gate.

**Groups, in this order** (each group flips `json → dual`, soaks, then goes
`dual → db`):

| Group | Stores |
|---|---|
| ops | flags, heartbeat, jobs, scheduled_jobs, killswitch, notify_queue, scan_progress, market_data_state |
| reference | watchlist, state, ticker_directory, preferences, settings_audit, tuning, tuning_proposals |
| trading | plans, starred_plans, trades, account, journal |

**Gate `dual → db`.**
- **What must hold:** five consecutive trading days where the nightly
  `parity_report` is clean for every store in the group, and zero `dual`
  divergence log lines.
- **Who checks it:** a VM cron, `scripts/ops/v116_parity_check.sh`, mirrored in
  the repo, appends to `logs/v116_parity.log`, and the next Claude session reads
  that log.
- **Head start:** watchlist and state have been in dual since v91, so their
  existing days count once verified from the log.

**Gate to Phase 4.**
- Every group has been at `db` for five trading days.
- No rollback has been used since.
- A Phase 0 drill passed within the last seven days.

**A failed gate** puts the group back to `dual` with one `.env` edit. The
cause is written into this spec's status block before any retry.

**A DB write failure at `db`** pauses alerting instead of issuing a trade the
bot cannot record. The scan loop sets the pause flag, posts to the ops channel,
and surfaces it in the v71 health signal. Writes already raise (the fail-fast
rule); this step makes the raise stop issuance rather than skip one record.

# Phase 4 — Delete

Remove:
- every `writes_json`/`reads_db`/`writes_db` branch, and the JSON read and
  write code of every migrated store
- `swingbot/core/db/stages.py`, the `DB_STORES` field, and the `dual.py`
  comparison guard
- `swingbot/admin/events/watcher.py` (the file watcher) and the
  `reload()`/`refresh()`/stale-snapshot machinery

After this phase, rollback means Phase 0 (PITR plus the image tag), not a stage
flip.

`export_json.py` stays, as a one-way dump for inspection.

A docs sweep updates `architecture.md`, `known-traps.md`, `DEPLOY_HETZNER.md`,
`DB_RESTORE.md` and the `schema-change` skill, which currently says the
strangler is "partially complete". The Codex mirror ships in the same commit.

The plan ends with a single full-suite run, then the release.

## Testing

- **Where tests run.** Unit and integration tests use the existing Postgres
  test harness (`db-test` compose profile).
- **Contract tests (Phase 2):** the schema contract, the unknown-field
  round-trip, and the rename/drop helpers up and down.
- **Production-data tests (Phase 3):** round-trip tests per store against a
  production snapshot.
- **Rollback script.** `rollback_to.sh --dry-run` is tested locally against
  fixture `deploys.jsonl`, `.env` versions and restic listings. The real
  restore is proven only by the Phase 0 drill on the VM's scratch stack.
- **Test-run budget.** Per-task runs are narrow (`testrun.py file …`). The full
  suite runs once, as the plan's final task.

## Parallelisation

| Group | Contents | Depends on |
|---|---|---|
| A | Phase 0 (PITR, code, config, market_data, `rollback_to.sh`, drill) | — |
| B | Phase 1 (merge branch, two tables, resync) | — |
| C | Phase 2 (contract tests, helpers, recipe) | B, because the contract test must see the two new tables |
| D | Phase 3 readiness (export shapers, round-trip tests) | B, because the shapers cover the new tables |
| E | Phase 3 flips | A, because no `db` flip happens before the rollback is drilled; D, because a group flips only once it can be rolled back to JSON |
| F | Phase 4 | E, because nothing is deleted until every group has soaked at `db` |

A and B run in parallel. C and D run in parallel after B. E is a chain of
three flips with calendar soaks between them, so it cannot be compressed. F is
a group of one.

## Honest limits

- **Losing the VM loses the history.** Point-in-time history sits on the same
  disk as the database; the partner accepted this, and it can be moved off-box
  later without changing the design. *Since 2026-10-02 (v120): losing the VM loses only
  what changed since the last good `/backup-pull`, plus the point-in-time history; see
  `DB_RESTORE.md`.*
- **Posted Discord alerts cannot be recalled.** After a rollback the book
  matches the target second, but the channel still shows later messages.
- **The worst case loses five minutes.** It is bounded by `archive_timeout`.

## Status (Phase 3)

All times UTC, 2026-10-01. The partner asked for the whole cutover on one day, so **every five-trading-day
soak gate was skipped** (rows marked OVERRIDE); each group got a short soak instead and nothing else about
the plan's order changed: the PITR drill passed before any store left `json`, and the trading flip took a
backup checkpoint first. Phase 4 (V116-34 to V116-42) is implemented on branch `2026-10-01-v116-phase4`
but **not shipped**: the JSON paths and `DB_STORES` still exist on `main`, so rollback to JSON stays possible.

| Time | Group | Change | Evidence |
|---|---|---|---|
| 12:21 | all | Phase 0-3 merged to `main` (`14551c3c`) and deployed | CI green except the pin step: `.env` was `root:root`; fixed with `chown deploy:deploy`, deploy rerun green |
| 12:46-13:05 | PITR | archiving on, stanza `swingbot`, full backup `20261001-124820F`, restic repo + snapshot `de4bdb0b`, crons installed, `alembic upgrade head` to `v116_002` | `docs/deploy/DB_RESTORE.md` |
| 13:51 | PITR | drill | PASS (a 13:50 attempt failed on `DRILL_TARGET`, fixed) |
| 14:04 | ops | json -> dual | parity clean: jobs 0/0, killswitch 1/1, scheduled_jobs 3/3 (+ state 1616, watchlist 77) |
| 14:29 | ops | dual -> db | OVERRIDE (soak ~25 min, 4 scans, 0 database error lines) |
| 14:39 | reference | json -> dual | parity clean: preferences 1/1, settings_audit 1/1, ticker_directory 0/0, tuning 0/0, tuning_proposals 0/0 |
| ~14:50 | reference | dual -> db | OVERRIDE (soak ~10 min, 2 scans, 0 errors) |
| 15:21 | trading | json -> dual | checkpoint `15:21:27Z`; imported plans 513, starred_plans 0, trades 858, account 872 balance points, journal 666; parity clean |
| 16:23 | trading | dual -> db, `events:db` | OVERRIDE (soak ~60 min, 12 scans, 0 errors); checkpoint `16:23:23Z` |
| 16:56 | settings | `SCAN_CACHE_MAX_AGE_HOURS` 6 -> 13 | mitigation for a theory that did not hold (live Alpaca daily frames are 502 rows) |
| 17:15 | settings | `SCAN_CACHE_MAX_AGE_HOURS` back to 6; `MIN_STOP_DISTANCE_PCT` 2.0 -> 1.75 | partner decision; documented in `.env.example` (shipped default stays 2.0) |
| 18:23 | settings | `SCAN_WORKERS` 4 -> 1 in the admin earlier, then 4 (partner request), then back to 1 (measured: median scan 108 s at 4 workers vs 92 s at 1) | net unchanged: 1 is the schema default (v56) |
| 20:30 | market_data | cache repair: 16 daily + 5 hourly files replaced after quarantine | `scripts/ops/market_cache_repair.py`; old files in `market_data/_quarantine/20261001-203019/`; re-audit 160/160 OK |
| 21:32 | all | Phase 4 deployed (`a0da07a7`, `bot 2.0.0`) | CI green; 0 database error lines; new trades issued at `db` afterwards (860 trades / 515 plans) |

Live `DB_STORES` after 16:23: `plans, starred_plans, trades, account, journal, watchlist, state,
ticker_directory, preferences, settings_audit, tuning, flags, heartbeat, jobs, scheduled_jobs, killswitch,
notify_queue, scan_progress, market_data_state, events`, all at `db`.

What the day found (all fixed before or at the flip, each test-first):
- At `db`, `get_balance_history_points` raised on datetimes (kill-switch drawdown on every scan) and
  `get_daily_summary` read an always-empty history.
- At `db`, closing a legacy trade in the admin never queued its Discord notice (`id` is a reserved column),
  and the bot's embed code read `id`; job state lost to the stored status.
- A store-write halt could leave already-logged trades without alerts (`_persist_plan_v2` now runs first).
- The wrapper `scripts/ops/ssh-hetzner.sh` expands `$(...)` on the dev machine; pipe scripts over stdin.

Known limits after the day: the JSON files stopped being updated at each group's `db` stage (rollback is
PITR via `scripts/ops/rollback_to.sh` or `scripts/db/export_json.py`); the nightly soak cron
(`install_v116_soak_cron.sh`) was not installed because the gates were overridden.
