# Database restore drill

**Rollback is `scripts/ops/rollback_to.sh "<UTC>"`** (point-in-time, last 30
days, see `DEPLOY_HETZNER.md` "Point-in-time rollback"). The `pg_dump` described
here (kept 90 days) is the second, day-level method for anything older.


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
(installed 2026-09-30). Dumps are pruned after 90 days.

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

### Drill 2026-10-01 (v116 V116-10)

`scripts/ops/pitr_drill.sh` restored `2026-10-01 13:51:42+00` into the `swingbot-drill` scratch
project (127.0.0.1:55433, volume `drill_pgdata`, `archive_mode=off`, repository mounted read-only)
from the full backup `20261001-124820F`.

| check | at target (production) | restored |
|---|---|---|
| mark written 2 s before | present | 1 |
| mark written 2 s after | present in production | 0 |
| first trade record md5 | 20adb1fc92347842f5211ae5eeabc09b | 20adb1fc92347842f5211ae5eeabc09b |
| signal_state md5 | 29a9aa7c3f80d2c4d2cc9b8464914d5a | 29a9aa7c3f80d2c4d2cc9b8464914d5a |

VERDICT: PASS. Scratch project and volume removed afterwards (0 containers, 0 volumes left).

An earlier attempt at 13:50 UTC FAILED before restoring anything: the scratch compose file requires
`DRILL_TARGET` whenever it is parsed, and the script set it only inline on one command, so the
`run`, `up` and `exec` calls aborted (`required variable DRILL_TARGET is missing a value`). It left
only its two mark rows in the `pitr_drill` schema in production, which is by design. The script now
exports `DRILL_TARGET` once the target second is known (commit `fix(v116): the PITR drill exports
DRILL_TARGET ...`); the passing run used that fixed copy, run from `/tmp` on the VM.

## Off-VM copy and stable snapshots (v120)

Live on 2026-10-02 (UTC), after the v120 scripts reached production through the normal deploy
(CI run for `122b7444`). Everything below ran against production through `scripts/ops/ssh-hetzner.sh`.
Two skills drive it from the dev machine: `/backup-pull` (`scripts/ops/pull_backups.sh`) and
`/stable-snapshot <note>` (`scripts/ops/stable_snapshot.sh` on the VM, then the tag and a local copy).
Local copies live in the main tree's gitignored `backups/` (`pulls/`, `market_data/`, `stable/`).

### Pulls

| pull | folder | bytes | files | time | verdict |
|---|---|---|---|---|---|
| first (full `market_data/`) | `pulls/2026-10-02T07-59Z` | 191,025,299 (dump 555,874; `market_data.tar` 190,443,520) | 520 | 28 s | PASS |
| second (incremental) | `pulls/2026-10-02T08-04Z` | 38,183,027 (`market_data.tar` 37,601,280) | 59 | 12 s | PASS |

Both folders pass `backup_manifest.py verify` (sha256 and size of every file, no unlisted file, full gzip read);
nothing was missing on the VM; the local mirror holds 520 files; `git status` stayed clean (`backups/` is ignored).

### Local restore drill

`db.sql.gz` of the first pull was restored into a throwaway `postgres:18` container (the manifest's
`pg_server_version` is `18.6`; the container reported `18.6 (Debian 18.6-1.pgdg13+2)`) in 4.7 s, then exact
`count(*)` per table was compared with the manifest's `row_counts` (keys are schema-qualified, counted from the
dump's COPY blocks):

| table | manifest | restored |
|---|---|---|
| `pitr_drill.marks` | 4 | 4 |
| `public.account` | 1 | 1 |
| `public.account_balance_history` | 872 | 872 |
| `public.admin_jobs` | 0 | 0 |
| `public.alembic_version` | 1 | 1 |
| `public.bot_heartbeat` | 1 | 1 |
| `public.dropped_doc_fields` | 0 | 0 |
| `public.journal_entries` | 666 | 666 |
| `public.killswitch` | 1 | 1 |
| `public.manual_close_notify` | 0 | 0 |
| `public.market_data_state` | 466 | 466 |
| `public.plans` | 516 | 516 |
| `public.runtime_flags` | 1 | 1 |
| `public.scan_progress` | 1 | 1 |
| `public.scheduled_jobs` | 3 | 3 |
| `public.settings_audit` | 1 | 1 |
| `public.signal_state` | 1637 | 1637 |
| `public.starred_plans` | 0 | 0 |
| `public.ticker_directory` | 0 | 0 |
| `public.trades` | 861 | 861 |
| `public.tuning_proposals` | 0 | 0 |
| `public.tuning_results` | 0 | 0 |
| `public.ui_preferences` | 1 | 1 |
| `public.watchlist` | 77 | 77 |

24 tables and 5,110 rows on both sides, 0 mismatches; `alembic_version` in the restored database is `v116_002`.
VERDICT: PASS. Container and anonymous volume removed (Docker volumes 47 before and after).

### First stable snapshot

- Tag `stable-2026-10-02` (annotated, pushed) on `122b7444`, which was at that moment `origin/main`, the VM checkout
  `HEAD` and the `git_sha` of the last `deploys.jsonl` line. Local `main` carried another session's unpushed commit,
  so the tag names the commit explicitly instead of `HEAD`.
- VM folder `backups/stable/stable-2026-10-02/` (mode 700; `db.sql.gz` and `env` mode 600): `db.sql.gz` 555,859 bytes,
  `env` 5,633, `deploy.json` 203, `manifest.json` 1,594. Manifest: git `122b7444afe8`, bot image
  `ghcr.io/cmghuy/discord-bot:sha-122b7444afe8`, db image `ghcr.io/cmghuy/discord-bot-db:pgcfg-aae12c7a4b74`,
  Postgres 18.6, 24 tables, 5,110 rows. The snapshot took 5 s and was started at 08:10 UTC, after the hourly restic
  job's `:07` lock window.
- restic snapshot `e8d77959` (181.232 MiB) tagged `market_data`, `stable`, `stable-2026-10-02`; `restic_hourly.sh`
  now forgets with `--keep-tag stable`, so it outlives the 30-day window.
- Local copy `backups/stable/stable-2026-10-02/` pulled and verified (PASS); `LAST_GOOD_PULL` untouched.

`restore_stable.sh stable-2026-10-02 --dry-run` on the VM:

```
PASS
Stable point stable-2026-10-02 resolves to:
  dump       backups/stable/stable-2026-10-02/db.sql.gz
  code       git 122b7444afe89fdff0a7d5338fcf61ca5c66e588
  bot image  ghcr.io/cmghuy/discord-bot:sha-122b7444afe8
  db image   ghcr.io/cmghuy/discord-bot-db:pgcfg-aae12c7a4b74
  market     restic e8d77959c5f06fb2e33ff5020d35d139a1a6764e0469b5a6ebd833c589491fa4
Dry run: nothing changed.
```

It changed nothing: container creation times, the `.env` mtime, the checkout `HEAD` and the `market_data` file
count (520) were identical before and after.

### What this does and does not cover

- The off-VM copy is as old as the last `/backup-pull`; the SessionStart `BACKUP` line warns from 8 days.
- It restores to the pull, not to a second: point-in-time history stays on the VM (pgBackRest, restic).
- A stable point's `market_data/` is pinned only on the VM (restic); off the VM it is the rolling mirror.
- Each pull's `env` is plaintext on the dev machine, like `.env`.
- A real `restore_stable.sh --i-mean-it` has not been run, only `--dry-run`.
