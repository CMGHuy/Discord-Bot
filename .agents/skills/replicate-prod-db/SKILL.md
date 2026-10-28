---
name: replicate-prod-db
description: "Copy the production Postgres data into a local database (read-only on the Hetzner VM) and verify row counts. Run as /replicate-prod-db, or by Claude itself before a task's first test run against the database (partner rule, 2026-10-18)."
---
<!-- GENERATED from .claude/skills/replicate-prod-db/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Replicate prod DB

## Step 1 — Read the authority

`docs/deploy/DB_RESTORE.md` (the dump/restore pair this reuses) and
`docs/deploy/DEPLOY_HETZNER.md` "PostgreSQL (the only store)". This skill is
the checklist; it does not restate them.

## Step 2 — Pick the target

Default is the separate local database `swingbot_prod_replica` in the local
`swing-db` container. Pick a different name only if the partner gave one.
**Never** target `swingbot` (the working local database) unless the partner
asked for it by name: that drops and recreates it, and the script requires
`--i-mean-it` to allow it.

**Exactly one database container for this project, always** (`swing-db`).
A plan that touches the database does one thing: refresh that container with
the latest production data (Step 3). It never creates a container, a second
database, a per-plan or per-worktree copy, or a new port. Every plan and
worktree shares the one replica by pointing `DATABASE_URL` at it. Because it is
shared, a re-run drops and recreates the replica: skip it when a sibling task
synced it recently and is still testing.

Before Step 3, list what exists: `docker ps -a --format '{{.Names}}' | grep swing`.
Start the existing `swing-db` with `docker start swing-db` (never `make up`: it
also starts the bot, admin and tunnel containers) if it is stopped; if it will not
start (a port the OS refuses), fix that one container, do not stand up another.
`swing-db` also serves the test suite: it is published on `127.0.0.1:55432` by
the git-ignored `docker-compose.override.yml` (`ports: 127.0.0.1:55432:5432` on
service `db`), its `swingbot` role password is the test default and
`swingbot_test` exists, so tests and replicas share the one server. Recreate
it with `docker compose up -d db` from the main checkout, never from a
worktree. `swing-db-test` (compose profile `test`, CI only) must not run
locally. Any other `swing-*` Postgres container is a stray:
report it to the partner, never point a plan at it, and never delete one without
asking.

## Step 3 — Replicate

```bash
bash scripts/ops/replicate_prod_db.sh                      # -> swingbot_prod_replica
bash scripts/ops/replicate_prod_db.sh <name>               # -> another replica name
bash scripts/ops/replicate_prod_db.sh --dry-run            # show source/target/dump, touch nothing
```

Production is only read (one `pg_dump`, one count query) and only through
`scripts/ops/ssh-hetzner.sh`; never run a raw `ssh`/`scp` instead. The local
`swing-db` container must be up (`make up`). The dump is kept in
`backups/prod-replica/` (gitignored, newest 3 kept): it holds the whole trading
history, so it never leaves this machine.

## Step 4 — Report

Read the final `replicate_prod_db: <VERDICT> target=… tables=… alembic=…` line
and report the verdict, target, table count and `alembic` revision:

- **MATCH** — every table's replica count equals production's.
- **DRIFT** — production gained rows after the snapshot (the dump is one
  moment, the count a few seconds later). Expected on a busy table; name the
  tables printed under the line.
- **MISMATCH** (exit 1) — the replica has more rows than production or lacks a
  table. Show the printed lines in full and stop; do not trust the copy.

A `FAIL …; local db untouched` line means the dump was empty or invalid before
the restore ran: nothing local changed. Report it as printed.

Then compare `alembic=` with this checkout's head (`python -m alembic heads`).
If the replica is behind, migrate **the replica only**, by pointing
`DATABASE_URL` at `swingbot_prod_replica`; never `upgrade head` against the
working `swingbot` database as a side effect of this skill.

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
