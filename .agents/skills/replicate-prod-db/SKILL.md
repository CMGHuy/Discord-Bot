---
name: replicate-prod-db
description: "Copy the production Postgres data into a local database (read-only on the Hetzner VM) and verify row counts. Run as /replicate-prod-db, or by Claude itself before a task's first test run against the database (partner rule, 2026-10-18)."
---
<!-- GENERATED from .claude/skills/replicate-prod-db/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Replicate prod DB

## Step 1 — Read the authority

`docs/deploy/DB_RESTORE.md` (the dump/restore pair this reuses) and
`docs/deploy/DEPLOY_HETZNER.md` "PostgreSQL (the only store)"; not restated here.

## Step 2 — Pick the target

Default is the separate local database `swingbot_prod_replica` in the local
`swing-db` container. Pick a different name only if the partner gave one.
**Never** target `swingbot` (the working local database) unless the partner
asked for it by name: that drops and recreates it, and the script requires
`--i-mean-it` to allow it.

**Exactly one database container for this project, always** (`swing-db`).
A plan that touches the database only refreshes it from production (Step 3):
never a new container, database, per-plan or per-worktree copy, or port. Every
plan and worktree points `DATABASE_URL` at the one replica. A re-run drops and
recreates it: skip it when a sibling task synced it recently and still tests.

List what exists first: `docker ps -a --format '{{.Names}}' | grep swing`.
If `swing-db` is stopped, `docker start swing-db` (never `make up`: it also
starts the bot, admin and tunnel); if it will not start, fix that one container.
It also serves the test suite on `127.0.0.1:55432` (git-ignored
`docker-compose.override.yml`, service `db`; `swingbot` role on the test default
password, `swingbot_test` exists). Recreate it with `docker compose up -d db`
from the main checkout, never a worktree. `swing-db-test` (profile `test`) is CI
only and must not run locally. Any other `swing-*` Postgres container is a
stray: report it, never point a plan at it, never delete one without asking.

## Step 3 — Replicate

```bash
bash scripts/ops/replicate_prod_db.sh                      # -> swingbot_prod_replica
bash scripts/ops/replicate_prod_db.sh <name>               # -> another replica name
bash scripts/ops/replicate_prod_db.sh --dry-run            # show source/target/dump, touch nothing
```

Production is only read (one `pg_dump`, one count query), only through
`scripts/ops/ssh-hetzner.sh`, never a raw `ssh`/`scp`. `swing-db` must be up
(Step 2). The dump stays in `backups/prod-replica/` (gitignored, newest 3 kept):
it is the whole trading history and never leaves this machine.

## Step 4 — Report

Read the final `replicate_prod_db: <VERDICT> target=… tables=… alembic=…` line
and report the verdict, target, table count and `alembic` revision:

- **MATCH** — every table's replica count equals production's.
- **DRIFT** — production gained rows between dump and count. Expected on a
  busy table; name the tables printed under the line.
- **MISMATCH** (exit 1) — the replica has more rows than production or lacks a
  table. Show the printed lines in full and stop; do not trust the copy.

A `FAIL …; local db untouched` line means the dump was empty or invalid before
the restore: nothing local changed. Report it as printed.

Then compare `alembic=` with this checkout's head (`python -m alembic heads`). If
the replica is behind, migrate **the replica only** (`DATABASE_URL` at
`swingbot_prod_replica`); never `upgrade head` against `swingbot` from here.

## The gate

A verdict line with the target and `alembic` revision named, or a FAIL shown
in full.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "just restore into `swingbot`, it is the one the app reads" | It is dropped first. Replicate to the default name and point a session at it. |
| "run `pg_dump` against prod from my machine directly" | The port is unpublished and the key goes through `ssh-hetzner.sh`; the script does the whole path. |
| "DRIFT means it failed" | Production kept writing between dump and count. Only MISMATCH is a bad copy. |
| "commit the dump so others can reuse it" | It is the live trading history; `backups/` is ignored on purpose. |
