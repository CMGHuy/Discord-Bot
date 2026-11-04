---
name: replicate-prod-db
description: "Use before a task's first test run that reaches the local Postgres (the storage suite, tests/db/, any test on a store's read/write path or an Alembic migration), or when asked to refresh, replicate or copy production data locally (/replicate-prod-db). Not for frontend-only or pure-unit runs, not for writing to production, and not when a sibling task in this session already synced the replica."
---
<!-- GENERATED from .claude/skills/replicate-prod-db/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Replicate prod DB

## Step 1 — Read the authority

`docs/deploy/DB_RESTORE.md` and `docs/deploy/DEPLOY_HETZNER.md` "PostgreSQL (the only store)".

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
starts the bot, admin and tunnel). It also serves the test suite on
`127.0.0.1:56789` (git-ignored `docker-compose.override.yml`, service `db`;
55432 is a Windows reserved port). Credentials are `.env`'s `DATABASE_URL` via
`scripts/dev/swing_db.py` (any worktree or agent may use it, nobody prints it);
recreate with `docker compose up -d db` from the main checkout. `swing-db-test`
is CI only. Any other `swing-*` Postgres container is a stray: report it, never
point a plan at it or delete it without asking.

## Step 3 — Replicate

```bash
bash scripts/ops/replicate_prod_db.sh                      # top up swingbot_prod_replica (rebuild if absent / other revision)
bash scripts/ops/replicate_prod_db.sh --full               # drop and rebuild it
bash scripts/ops/replicate_prod_db.sh <name>               # -> another replica name
bash scripts/ops/replicate_prod_db.sh --dry-run            # show source/target/dump, touch nothing
```

Default is **incremental**: on the same alembic revision only the rows the
replica lacks are inserted (`ON CONFLICT DO NOTHING`, one transaction, nothing
dropped). Rows production deleted or changed are not touched; use `--full` then.
Production is only read (one `pg_dump`, one count query), only through
`scripts/ops/ssh-hetzner.sh`, never raw `ssh`/`scp`. The dump stays in
`backups/prod-replica/` (gitignored, newest 3 kept) and never leaves this machine.

## Step 4 — Report

Read the final `replicate_prod_db: <VERDICT> target=… tables=… alembic=…` line
and report the verdict, target, table count and `alembic` revision:

- `mode=incremental added=N` — N rows were new; `mode=full` rebuilt it.
- **MATCH** — every table's replica count equals production's.
- **DRIFT** — production gained rows between dump and count. Expected on a
  busy table; name the tables printed under the line.
- **MISMATCH** (exit 1) — the replica has more rows than production or lacks a
  table. Show the printed lines in full and stop; do not trust the copy.

A `FAIL …; local db untouched` line: dump empty or invalid, nothing local
changed. Report it as printed. Then compare `alembic=` with this checkout's head (`python -m alembic heads`). If
the replica is behind, migrate **the replica only** (`DATABASE_URL` at
`swingbot_prod_replica`); never `upgrade head` against `swingbot` from here.

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
