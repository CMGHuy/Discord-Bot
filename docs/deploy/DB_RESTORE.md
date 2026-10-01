# Database restore drill

An unexercised restore is a hope, not a backup. This is the record of the drill
(v67 P6-04), run against **production** on 2026-09-30.

## Commands

```bash
# on /opt/swing-bot (via scripts/ops/ssh-hetzner.sh)
./scripts/ops/backup_db.sh
# -> data/backups/db/swingbot_2026-09-30_09-02-23.sql.gz (519 KB)
./scripts/ops/restore_db.sh data/backups/db/swingbot_2026-09-30_09-02-23.sql.gz swingbot_restore_drill
docker compose exec -T db psql -U swingbot -d postgres -c 'DROP DATABASE swingbot_restore_drill;'
```

The target database is a required argument; restoring into `swingbot` needs
`--i-mean-it`.

## Result

Exact row counts, live `swingbot` vs restored `swingbot_restore_drill`:

| trades | plans | journal_entries | signal_state | watchlist | account_balance_history | alembic_version |
|---|---|---|---|---|---|---|
| 832 | 485 | 640 | 1512 | 77 | 846 | p6_001 |
| 832 | 485 | 640 | 1512 | 77 | 846 | p6_001 |

`pg_stat_user_tables` row counts for all 20 tables also matched the live
database (account 1, starred_plans 0, every other table 0 besides those above).
The restored database carries `alembic_version` at `p6_001 (head)`, so it can
be migrated forward.

## If they had not matched

Do not flip any store to `db`. Compare per table to find what the dump dropped,
check `pg_dump` stderr in `logs/backup.log`, fix the script, and repeat the
drill before trusting any backup.

## Scheduling

Cron on the VM: `0 3 * * *  cd /opt/swing-bot && ./scripts/ops/backup_db.sh >> logs/backup.log 2>&1`
(installed 2026-09-30). Dumps are pruned after 14 days.

## Point-in-time recovery (v116)

Set up on production on 2026-10-01 (UTC), by hand through `scripts/ops/ssh-hetzner.sh`:

- Database image `ghcr.io/cmghuy/discord-bot-db:pgcfg-aae12c7a4b74` (pgBackRest 2.58.0), pinned in
  the VM `.env` by `deploy.sh` together with the bot image; `backups/deploys.jsonl` has one line per deploy.
- `.env` keys set in place with `env_set.py`: `PG_ARCHIVE_MODE=on`, `RESTIC_PASSWORD` (value only on the VM).
  Archiving needs a database restart: `archive_mode=on`, `archive_command=pgbackrest --stanza=swingbot archive-push %p`.
- pgBackRest stanza `swingbot` created and checked; first full backup `20261001-124820F`
  (46.6 MB database, 7.4 MB in the repository, repository `backups/pitr/`, retention 30 days).
- restic repository `/opt/swing-bot/backups/restic` (market data), first snapshot `de4bdb0b` (171 MiB).
- Host packages: `restic`, `python3` (apt).
- Migrations applied by hand: `alembic upgrade head`, `p6_001 -> p3_007 -> v116_001 -> v116_002`.
- Crons, installed with `scripts/ops/install_pitr_crons.sh` (idempotent): pgBackRest nightly 02:30
  (full on Sundays, differential otherwise), restic hourly at :07, monthly verify on the 1st at 04:00,
  next to the existing `backup_db.sh` 03:00 line.
- Disk after setup: `/` 62% used (alarm threshold 80%).
- `.env` on the VM must be owned by the CI deploy user: `chown deploy:deploy /opt/swing-bot/.env`
  (it was `root:root`, so `deploy.sh`'s image-pin step failed with `PermissionError`).
