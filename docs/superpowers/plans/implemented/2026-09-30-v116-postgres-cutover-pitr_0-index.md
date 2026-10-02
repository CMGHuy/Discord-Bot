# v116 — Postgres cutover with whole-bot point-in-time rollback Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole.** Pull one task: `grep -n "^### Task V116-12" -A 200 docs/superpowers/plans/2026-09-30-v116-postgres-cutover-pitr_*.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md`](../../specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md) (partner-approved 2026-09-30, committed at `b742c062`)
**Bump:** bot major · ui none
**Edge:** none (integrity)

**Goal:** Every trading and operational store reads and writes Postgres only, the JSON persistence paths are deleted, and the whole bot (data, code image, `.env`, `market_data/`) can be rolled back to any second in the last 30 days.

**Architecture:** Phase 0 builds point-in-time recovery first: a `Dockerfile.db` image with pgBackRest archives WAL into `/opt/swing-bot/backups/pitr`, `deploy.sh` records every deploy in `backups/deploys.jsonl`, every `.env` change path snapshots `.env`, restic snapshots `market_data/` hourly, and `scripts/ops/rollback_to.sh` puts all four back. Phase 1 merges the unmerged v67 LISTEN/NOTIFY branch and adds the last two live-update tables. Phase 2 pins the hybrid `doc JSONB` contract with tests and ships rename/drop helpers. Phase 3 flips three store groups `json → dual → db` on production behind a nightly VM soak check. Phase 4 deletes `stages`, `DB_STORES`, the dual guard, the file watcher and every JSON read/write path.

**Tech Stack:** Python 3.11, SQLAlchemy Core 2 + psycopg 3, Alembic, PostgreSQL 18 (`postgres:18-alpine` + pgBackRest), restic, Flask SSE, discord.py, pytest (+ `db-test` compose profile), GitHub Actions + GHCR, Docker Compose on the Hetzner VM.

## Progress

> Closed 2026-10-01. The plan's goal is met: every store reads and writes Postgres only (`bot 2.0.0`, `a0da07a7`), the JSON persistence paths, `stages`, `dual`, `DB_STORES` and the file watcher are deleted, and the whole bot can be rolled back to a past second (`scripts/ops/rollback_to.sh`, drill PASS 2026-10-01).
>
> - **Phases 0-3 shipped 2026-10-01** (merge `14551c3c`, then fixes through `275f6bb0`); **Phase 4 shipped the same day** (merge `a0da07a7`). The staged flips ran on production in one sitting, with every group's five-trading-day soak **overridden at the partner's request** (rows in the spec's Status section). The nightly soak cron (`install_v116_soak_cron.sh`) was never installed and V116-33's gate was not formally passed; Phase 4 was deployed with 0 database error lines and a green CI instead.
> - **Cut or changed on the way:** `scripts/ops/v116_soak.py`, `v116_parity_check.sh`, `install_v116_soak_cron.sh`, `pull_prod_snapshot.sh`, `reimport_production.sh` and `v116_flip_stage.sh` were deleted in Phase 4 (they existed to compare JSON with Postgres). `V116-26`'s soak cron step was skipped. `.env` on the VM still carries an ignored `DB_STORES=` line (remove it through the admin Settings page; never `sed -i`).
> - **Found and fixed on the way** (each test-first): balance-history rows at `db` (kill-switch drawdown crash), the empty daily summary, the legacy-trade close notice (`id` is a reserved column; the bot-side embed also read `id`), job state losing to the stored status, a store-write halt dropping already-logged trades' alerts, the PITR drill's `DRILL_TARGET`, `.env` ownership for CI's pin step, and the wrapper's `$(...)` expansion.
> - **Not part of the plan but found by it** (production data, fixed 2026-10-01): the `market_data/` cache held a different instrument's older history for 16 daily and 5 hourly files; the repair is recorded in the spec's Status section and the old files sit in `market_data/_quarantine/20261001-203019/`.
> - **Known local flake:** the full suite on a Windows checkout under `-n 4` fails different admin tests each run (missing tables, `can't start new thread`); every failing test passes alone and CI is green. `be3ec50f` fixed one real cause (the schema-free fixture dropping the shared database's tables).

## Parts

| File | Phase | Tasks | Group |
|---|---|---|---|
| `_0-index.md` (this file) | header, constraints, parallelisation, revision ids, spec points | — | — |
| `_1a-pitr.md` | Phase 0 — Point-in-time rollback | V116-01 … V116-05 | A |
| `_1b-pitr.md` | Phase 0 (continued) | V116-06 … V116-10 | A |
| `_2-events.md` | Phase 1 — Live events | V116-11 … V116-15 | B |
| `_3-schema.md` | Phase 2 — Schema-change guarantees | V116-16 … V116-19 | C |
| `_4a-readiness.md` | Phase 3 — readiness | V116-20 … V116-22 | D |
| `_4b-readiness.md` | Phase 3 — readiness (continued), ship | V116-23 … V116-26 | D |
| `_4c-flips.md` | Phase 3 — the three group flips and the Phase 4 gate | V116-27 … V116-33 | E |
| `_5-delete.md` | Phase 4 — Delete; full suite; release | V116-34 … V116-42 | F |

Check that no task was dropped across the parts:

```bash
for f in docs/superpowers/plans/2026-09-30-v116-postgres-cutover-pitr_*.md; do
  echo "$(basename $f): $(grep -o '^### Task V116-[0-9]*' $f | tr '\n' ' ')"
done
```

## Global Constraints

- **Worktree and branch:** `.claude/worktrees/2026-09-30-v116-postgres-cutover-pitr/`, branch `2026-09-30-v116-postgres-cutover-pitr`, cut from `main` in V116-01 (Phase 0) or V116-11 (Phase 1), whichever runs first. Do not touch any other worktree. Stage files by name. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Never delete** branch `2026-09-30-v67-p3-18-notify-events` or its worktree, even after it is merged (V116-11). That decision is the partner's (`docs/claude/git-safety.md`).
- **Production** is the Hetzner VM `/opt/swing-bot`. Every production command goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`, and a script is piped on stdin. `ssh-hetzner.sh` is **uncommitted**: it exists only in the main tree at `E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh`, not in the worktree. Never raw `ssh`/`scp`.
- **Production `.env` is edited in place** with `python3 scripts/ops/env_set.py KEY VALUE` (created in V116-03), which rewrites the same inode and then snapshots `.env`. **Never `sed -i`.** After any `.env` edit: `docker compose restart bot admin`, then verify inside **both** containers (`docker compose exec -T bot python -c "from swingbot import config; print(config.DB_STORES)"`, same for `admin`). Never trust the host file alone.
- **Production edits happen outside the session window** (`SESSION_START_HOUR`–`SESSION_END_HOUR` Europe/Berlin, Mon–Fri) so a restart never lands mid-scan.
- **Every production change is mirrored into the repo in the same task** (a cron under `scripts/ops/`, a live `DB_STORES` value in the `.env.example` comment, a drill result in `docs/deploy/DB_RESTORE.md`). The task is not done until that commit exists on `main`.
- **VM host scripts are stdlib-only Python 3** (`scripts/ops/env_set.py`, `scripts/ops/pitr_resolve.py`, `swingbot/core/infra/env_snapshot.py`). They run as `python3 …` on the host, not in a container, because the containers are stopped during a rollback.
- **Retention (spec § Phase 0):** pgBackRest `repo1-retention-full-type=time`, `repo1-retention-full=30`; `archive_timeout=300`; compression on (`compress-type=gz`); restic `forget --keep-within 30d --prune` hourly; `.env` snapshots 30 days (the newest snapshot older than 30 days is always kept, so the version live at the window's start survives); `backup_db.sh` 90 days (was 14); GHCR `cut-off: 45d` (was 14d — 30 days of rollback plus the age of the image live at the start of the window).
- **Alarms (spec § Proof):** `pg_stat_archiver.failed_count` growth, or `last_failed_time` newer than `last_archived_time`; disk usage above **80%** on the filesystem holding `data/` and `backups/` (one VM disk). Both post `Kind.HEALTH_ALERT` / `Kind.HEALTH_RECOVERED` (`swingbot/core/presentation/kinds.py`) to the ops channel via `loops._ops_channel()`.
- **Revision ids:** existing `p[1-6]_\d{3}`; the merged branch adds `p3_007`; this plan adds `v116_001` and `v116_002`. `tests/db/test_migrations.py::ID_RE` becomes `^(p[1-6]|v\d+)_\d{3}$` (V116-12). Exactly one Alembic head at all times.
- **Stage names** (the keys `stages.stage_for()` reads) and their groups, fixed for Phase 3:

  | Group | Stage names | Parity-report stores behind them |
  |---|---|---|
  | ops | `flags`, `heartbeat`, `jobs`, `scheduled_jobs`, `killswitch`, `notify_queue`, `scan_progress`, `market_data_state` | `jobs`, `scheduled_jobs`, `killswitch` (the other five are ephemeral and have no parity spec) |
  | reference | `watchlist`, `state`, `ticker_directory`, `preferences`, `settings_audit`, `tuning` | `watchlist`, `state`, `ticker_directory`, `preferences`, `settings_audit`, `tuning`, `tuning_proposals` |
  | trading | `plans`, `starred_plans`, `trades`, `account`, `journal` | the same five |

  The spec's "tuning_proposals" is not a stage name: the `tuning` stage governs both tuning tables. `events` is a sixth stage (the admin's LISTEN/NOTIFY switch, from the merged branch); it goes to `db` in the same `.env` edit that takes the trading group to `db` (V116-32).
- **Complexity:** every function written or changed ends at radon cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>` prints nothing new). Legacy functions already at or above 15 never get worse: `loops.on_ready` (15), `loops._session_scan_tick` (15), `loops.config_watcher` (19), `scan_run._sync_run_scan` (103). Tasks that touch them extract helpers first.
- **Tests:** anything needing Postgres needs `docker compose --profile test up -d db-test` first; without it those tests skip. Per-task verification is narrow: `python scripts/dev/testrun.py file <test path>` (one or more files). `python scripts/dev/testrun.py fast` only in the ship tasks. **The full suite runs once, in V116-41.** Green means `0 failed` and `0 xfailed`.
- **Shipping mid-plan:** V116-09, V116-26 and V116-42 merge the branch to `main` and let CI deploy. CI's backend test shards gate the deploy job, so no local full run is scheduled for them; each runs `testrun.py fast` first. Never ship a half-done task: every started task on the branch must be complete and committed.

## Parallelisation

The spec's group table, restated with every sequential edge and its reason:

| Group | Tasks | Depends on | Why |
|---|---|---|---|
| A | V116-01 … V116-10 (Phase 0) | — | |
| B | V116-11 … V116-15 (Phase 1) | — | |
| C | V116-16 … V116-19 (Phase 2) | B | the schema contract test must see the two new tables (V116-12) |
| D | V116-20 … V116-26 (Phase 3 readiness) | B, and A for three tasks | the export shapers cover the new tables (V116-12); V116-22/V116-23 edit `loops.py` after V116-07 does; V116-24 consumes `parity_report.STAGE_STORES` from V116-06 |
| E | V116-27 … V116-33 (Phase 3 flips) | A, D | no store reaches `db` before the rollback is drilled (V116-10); a group flips only once it can be rolled back to JSON (V116-20, V116-21, V116-25) and once readiness is deployed (V116-26) |
| F | V116-34 … V116-42 (Phase 4) | E | nothing is deleted until every group has soaked at `db` (V116-33) |

**A and B run in parallel.** They share no file: A touches `Dockerfile.db`, `deploy/`, `docker-compose.yml`, `.github/workflows/`, `scripts/ops/`, `scripts/db/parity_report.py`, `swingbot/core/infra/`, `swingbot/admin/helpers.py`, `swingbot/commands/scanning/{loops,notices}.py`; B touches `swingbot/core/db/`, `swingbot/admin/events/`, `swingbot/core/scanning/progress_store.py`, `swingbot/core/marketdata/data_refresh.py`, `tests/db/`. **C and D run in parallel after B**, except that V116-16/V116-18 (`schema.py`) and V116-20/V116-21 (`export_json.py`) are each internally sequential.

Within each phase (details repeated at the top of each part):

- **Phase 0:** Wave 1 = V116-01, V116-07 (parallel: disjoint files). Wave 2 = V116-02, V116-03, V116-08 (parallel after V116-01: V116-02 names `Dockerfile.db`/`deploy/db/pgbackrest.conf` which V116-01 creates; V116-03 edits `docker-compose.yml` after V116-01 does; V116-08 runs the V116-01 image). Wave 3 = V116-04, V116-05 (parallel after V116-03: both call `env_set.py` and `env_snapshot`, which V116-03 creates; disjoint files). V116-06 after V116-05 (calls `restic_hourly.sh`). V116-09 after all of Phase 0 (ships it). V116-10 after V116-09 (runs on the deployed image).
- **Phase 1:** V116-11 first (the merge everything else builds on). V116-12 next (creates the tables, repositories and `store_db` fixture). V116-13, V116-14, V116-15 in parallel after V116-12 (disjoint files; V116-15 needs only V116-11).
- **Phase 2:** V116-16 and V116-17 in parallel (V116-17 only adds a test file). V116-18 after V116-16 (both edit `schema.py`, and V116-18 adds a `PROMOTION_REASONS` entry V116-16 introduces). V116-19 after V116-18 (documents the helper names V116-18 creates).
- **Phase 3 readiness:** V116-20 → V116-21 (same file). V116-22 → V116-23 (both edit `loops.py`, `commands/scanning/runstate.py`, `admin/app.py`). V116-24 parallel with both chains. V116-25 after V116-21 (tests the ops-store exports). V116-26 after all of them (ships them).
- **Phase 3 flips:** sequential throughout — a chain of calendar soaks: V116-27 → V116-28 → V116-29 → V116-30 → V116-31 → V116-32 → V116-33. The spec orders the groups ops, reference, trading, and each group's `dual → db` gate needs five trading days of the previous state.
- **Phase 4:** sequential throughout. V116-34 builds the harness and the guard test everything after it turns green. V116-35/36/37 share `swingbot/admin/jobs.py`, `swingbot/commands/scanning/loops.py` and the test harness, and each shrinks the guard test's expected-failure set. V116-38 needs every table-backed store gone (V116-37). V116-39 deletes `stages.py`, which nothing may import by then. V116-40 documents the result. V116-41 is the one full-suite run. V116-42 releases.

## Alembic revisions

| Revision | Down | Task | Creates |
|---|---|---|---|
| `p3_007` | `p6_001` | V116-11 (merged from the v67 branch) | NOTIFY triggers for every `events.TABLE_CHANNELS` table |
| `v116_001` | `p3_007` | V116-12 | `scan_progress`, `market_data_state` + their NOTIFY triggers |
| `v116_002` | `v116_001` | V116-18 | `dropped_doc_fields` (the drop helper's side table) |

## Spec points resolved against the code while planning

These are recorded so a reviewer can check them; none adds scope beyond what the code forces.

1. **`PROMOTED` lives in `swingbot/core/db/schema.py`, not in each repository.** The "one-line reason" becomes a `PROMOTION_REASONS` dict beside it (V116-16).
2. **`market_data_state.json` drives no SSE event today** (it is not in `watcher._DATA_PATHS`). Its trigger raises `watchlist`, the concern whose rows show data freshness (V116-12).
3. **The listener on the branch does not reconnect** (`DbEventListener._run` logs "event listener stopped" and exits). V116-15 builds reconnect-with-backoff and the `resync`, not only the test.
4. **`compare_and_log` is never called by any store**, so no "dual divergence" line is ever logged. The soak check counts `dual[` lines plus database exceptions (`sqlalchemy.exc.`, `psycopg`, `DatabaseUnavailable`, `StoreWriteHalt`) in the last 24 h of `bot`/`admin` logs (V116-24).
5. **Five ops stores have no parity spec** (`flags`, `heartbeat`, `notify_queue`, `scan_progress`, `market_data_state`); they are ephemeral. Their soak verdict is the error-line count; their rollback readiness is the new export writers (V116-21) and the snapshot round trip (V116-25).
6. **Two stage bugs block the ops flip** and are fixed in V116-22: at `heartbeat:db` the bot's `_read_heartbeat()` and the admin's `scan_status_payload()` still read `bot_heartbeat.json` (the failure counter resets to 1 every tick, and the admin shows the bot offline); at `notify_queue:dual` the bot drains only the file, so the table accumulates every queued close and replays them all at the `db` flip.
7. **GHCR keeps `sha-*` tags 14 days** (`.github/workflows/registry-retention.yml`: `cut-off: 14d`, `keep-n-most-recent: 10`), short of the 30-day requirement. V116-02 raises it to 45 days and adds the db image.
8. **The db image is tagged by the content hash of its build inputs** (`pgcfg-<12>`), not by commit sha, and an existing tag is never re-pushed. A per-commit tag would recreate the Postgres container on every push to `main`. `deploys.jsonl` still records the exact db image per deploy.
9. **`archive_mode` defaults to `off` in `docker-compose.yml`** (`PG_ARCHIVE_MODE` interpolation), and production sets it `on`. With it on, a dev machine or CI with no pgBackRest stanza would pile WAL up on its own disk.
10. **`tests/db/test_migrations.py::ID_RE` is widened in V116-12, not Phase 2,** because `v116_001` lands there and the existing test would fail on it.
11. **The watcher cannot simply be deleted.** `analytics_snapshot.json`, `scan_snapshots.json`, `scan_telemetry.jsonl` and `.env` stay files (spec § Out) and still raise `analytics`/`scan`/`settings`. V116-38 makes their writers `NOTIFY` so `watcher.py` can go without breaking the SSE contract.
12. **Only one of five CI backend shards runs Postgres**, and 94 test files seed JSON store files. V116-34 adds `db-test` to every shard and a `seed_store` helper before any deletion.
13. **The watchlist/state head start is moot for the gate:** the reference group flips `dual → db` together and needs five clean days for all six of its stages (V116-30 records the v91 days but does not count them for the others).
