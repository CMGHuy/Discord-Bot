---
name: replicate-prod-db
description: "Use before a task's first test run that reaches the local Postgres (the storage suite, tests/db/, any test on a store's read/write path or an Alembic migration), or when asked to refresh, replicate or copy production data locally. Run as /replicate-prod-db, or by Claude itself before such a test run. Not for frontend-only or pure-unit runs, not for writing to production, and not when a sibling task in this session already synced the replica."
---
<!-- GENERATED from .claude/skills/replicate-prod-db/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Replicate prod DB

## Step 1 — Read the authority

`docs/deploy/DB_RESTORE.md` and `docs/deploy/DEPLOY_HETZNER.md` "PostgreSQL (the only store)".

## Step 2 — Pick the target

Default is the separate local database `swingbot_prod_replica` in the local
`swing-db` container. Pick another name only if the partner gave one.
**Never** target `swingbot` (the working local database) unless the partner
asked for it by name: that drops and recreates it (`--i-mean-it` is required).

**Exactly one database container for this project, always** (`swing-db`).
A plan touching the database only refreshes it from production (Step 3): never
a new container, database, per-worktree copy, or port. Every plan and worktree
points `DATABASE_URL` at the one replica; skip a re-run a sibling just did.

List what exists: `docker ps -a --format '{{.Names}}' | grep swing`. If
`swing-db` is stopped, `docker start swing-db` (never `make up`: it also starts
the bot, admin and tunnel). It serves the tests on `127.0.0.1:56789`
(git-ignored `docker-compose.override.yml`, service `db`). Credentials are
`.env`'s `DATABASE_URL` via `scripts/dev/swing_db.py` (any worktree or agent may
use it, nobody prints it); recreate with `docker compose up -d db` from the main
checkout. `swing-db-test` is CI only; any other `swing-*` container is a stray: report it.

## Step 3 — Replicate

```bash
bash scripts/ops/replicate_prod_db.sh                      # top up swingbot_prod_replica (rebuild if absent / other revision)
bash scripts/ops/replicate_prod_db.sh --full               # drop and rebuild it
bash scripts/ops/replicate_prod_db.sh <name>               # -> another replica name
bash scripts/ops/replicate_prod_db.sh --dry-run            # show source/target/dump, touch nothing
```

Default is **incremental**: same alembic revision, only rows the replica lacks
are inserted (one transaction); rows production deleted or changed need `--full`.
Production is only read, only through `scripts/ops/ssh-hetzner.sh`, never raw
`ssh`/`scp`. The dump stays in gitignored `backups/prod-replica/`.

## Step 4 — Report

Read the final `replicate_prod_db: <VERDICT> target=… tables=… alembic=…` line
and report verdict, target, table count and `alembic` revision:

- `mode=incremental added=N` — N rows were new; `mode=full` rebuilt it.
- **MATCH** — every table's replica count equals production's.
- **DRIFT** — production gained rows between dump and count; name the tables.
- **MISMATCH** (exit 1) — replica has extra rows or lacks a table: show the
  lines in full, stop, do not trust the copy.

A `FAIL …; local db untouched` line: nothing changed; report it as printed. If
`alembic=` trails `python -m alembic heads`, migrate **the replica only**.

## The gate

A verdict line naming target and `alembic` revision, or a FAIL shown in full.
## Known wrong turns

| Tempting | Reality |
|---|---|
| "just restore into `swingbot`, it is the one the app reads" | It is dropped first. Replicate to the default name and point a session at it. |
| "run `pg_dump` against prod from my machine directly" | The port is unpublished and the key goes through `ssh-hetzner.sh`; the script does the whole path. |
| "DRIFT means it failed" | Production kept writing between dump and count. Only MISMATCH is a bad copy. |
| "commit the dump so others can reuse it" | It is the live trading history; `backups/` is ignored on purpose. |
| "the tests passed on yesterday's replica, skip the sync" | Partner rule (2026-10-18): the first DB test run of a task tops the replica up first. Only a sync earlier in this session counts. |

## Trigger table

Should fire: about to run `testrun.py suite storage` or a file under `tests/db/`.
Should fire: implementing a store's write path, then running its tests.
Should fire: "refresh my local database from production".
Should not fire: running `ng test` / a frontend unit test.
Should not fire: running a pure-unit test file under `tests/charts/`.
Should not fire: asking how many rows a production table has (`prod-inspector`).
