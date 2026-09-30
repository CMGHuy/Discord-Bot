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
