# v120 — Stable snapshots and an off-VM backup pull

**Version:** ui 1.21.0 · bot 1.12.1 (at writing)
**Bump:** none (ops scripts, skills and docs; no bot or UI runtime code changes)
**Edge:** none (integrity)
**Status:** implemented and live on 2026-10-02; this text was amended that day to match the code as built (rulings and review history are in the plan's "Status as built"). The drills passed: `DB_RESTORE.md` § "Off-VM copy and stable snapshots (v120)".

## Intent

The partner wants two things:

1. **A repeatable way to mark a stable version** — a *full known-good point*:
   the code, the images that were running, the `.env`, and the data at that
   moment — restorable long after the 30-day point-in-time window has passed.
2. **Periodic backups that survive losing the VM.** Production already backs
   itself up (below), but every copy sits on the VM's own disk; the v116 spec's
   Honest limits say so: *"Losing the VM loses the history."*

Partner decisions (brainstorm 2026-10-01): full known-good point; off-VM copies
are **pulled to this dev machine**; the pull is **manual** (`/backup-pull`),
with a SessionStart warning when overdue; each pull brings the
**rebuild-from-zero set**; local copies live in a **gitignored `backups/` in
the repo**; approach A (two explicit-only skills over ops scripts).

## What already exists (not rebuilt)

| Mechanism | Where | Retention |
|---|---|---|
| Nightly `pg_dump` 03:00 | `scripts/ops/backup_db.sh` → `data/backups/db/` | 90 days (the script; `DEPLOY_HETZNER.md` said 14 until v116's close-out corrected it) |
| pgBackRest PITR, WAL + nightly full/diff | `pitr_backup.sh` → `backups/pitr/` | 30 days |
| restic hourly of `market_data/` | `restic_hourly.sh` → `backups/restic` | 30 days (`forget --keep-within 30d`) |
| `.env` versions, deploy image pins | `backups/env/`, `backups/deploys.jsonl` (`git_sha`, `bot_image`, `db_image`) | env 30 days |
| Whole-bot rollback to a second | `rollback_to.sh` | inside the 30-day window |

Three hand-made stable points exist: `stable-2026-08-07`, `-08-17`, `-09-17`,
each as **both a tag and a same-name branch** — `git` now warns
`refname 'stable-2026-09-17' is ambiguous`. They pin code only.

## Design

### 1. A stable snapshot

Name: `stable-YYYY-MM-DD` (UTC date); a second one the same day takes `-2`,
then `-3`. The name is computed against local **and** origin tags.

A snapshot is four things, created in this order so a failure leaves no tag
pointing at an incomplete point:

1. **Pinned folder on the VM**, `backups/stable/<name>/`, written by
   `scripts/ops/stable_snapshot.sh <name>` (runs on the VM as root; refuses if
   the folder exists). It is built as `<name>.partial` and renamed last, so a half
   snapshot never carries the final name; a failed run also forgets its restic
   snapshot. Git on the VM runs as `deploy` (`runuser -u deploy -- git`), and an
   empty git sha aborts before anything is written:
   - `db.sql.gz` — a fresh dump: it runs `backup_db.sh`, then copies the dump
     it just wrote. `backup_db.sh` is unchanged; its pruning only touches
     `data/backups/db/`, so the pinned copy is never pruned.
   - `env` — copy of `/opt/swing-bot/.env`, mode 600.
   - `deploy.json` — the last `backups/deploys.jsonl` line.
   - `manifest.json` — see §3.
2. **restic snapshot** of `market_data/` tagged `market_data`, `stable` and
   `<name>`, taken under `flock logs/restic.lock` BEFORE the manifest is built
   (the manifest carries its id; restic exit 3, a file vanished mid-read, is a
   warning). `restic_hourly.sh`'s `forget` gains
   `--keep-tag stable` (restic keeps a snapshot if *any* policy matches), so it
   outlives the 30-day window.
3. **Annotated git tag** `<name>` on the commit production runs, pushed to origin — **never a
   branch**. Message: the partner's note, `ui`/`bot` from `VERSION.json`, and
   the bot/db image *references* from the manifest (`bot_image`, `db_image`: the
   immutable `sha-` tags from `deploys.jsonl`, not digests). If the push fails, the skill
   retries only this step; the VM folder stays.
4. **Immediate local copy**: `pull_backups.sh --stable <name>` brings the
   pinned folder (not the market_data snapshot) to `backups/stable/<name>/`
   and verifies it against its manifest.

**Preconditions** (the skill refuses otherwise): on `main`, clean, HEAD equals
`origin/main`; the VM checkout's HEAD **and** the last `deploys.jsonl`
`git_sha` both equal local HEAD — production must actually be running what is
being tagged; `docker compose ps` shows `bot` and `admin` running.

**Restore**: within 30 days `rollback_to.sh` still applies. For an older
stable point, `scripts/ops/restore_stable.sh <name> [--dry-run]` (VM, root),
shaped like `rollback_to.sh`: it restores `db.sql.gz` into `swingbot` through
`restore_db.sh --i-mean-it`, restores `market_data/` from the snapshot's
restic id, puts `env` back as `.env` (owner `deploy:deploy`), and pins the two
images from `deploy.json`. It checks out the tag's SHA detached; the next
`deploy.sh` resets to `origin/main`. It refuses a checkout with modified tracked files and an
empty git sha (also under `--dry-run`), takes a checkpoint of now (pgBackRest differential
backup, restic, a `.env` version) before stopping anything, recreates the db container on
the pinned image before `restore_db.sh`, logs to `logs/rollback.log`, runs from `main()` so
the checkout cannot rewrite the script mid-run, and starts with scanning **paused**. No flag
prints the plan and exits 2; `--dry-run` prints it and changes nothing; a real run needs
`--i-mean-it`.

**Existing `stable-*` branches stay.** `git-safety.md` puts them off limits to
any destructive command without the partner; this spec only stops creating
new ones.

### 2. The pull: `/backup-pull`

`scripts/ops/pull_backups.sh` runs on this machine and talks to the VM only
through `scripts/ops/ssh-hetzner.sh`, streaming base64 tar exactly as
`pull_prod_snapshot.sh` does. One remote script piped over `bash -s` has the modes
`stage`, `stream`, `clean` and, for `--stable`, `stream-stable`; VM git runs as `deploy`:

1. **Stage** — on the VM, under `backups/outbox/<stamp>/`: run `backup_db.sh`
   and copy the fresh dump as `db.sql.gz`; copy `.env` as `env`;
   copy `backups/deploys.jsonl`; tar the `market_data/` files modified since
   the `since` epoch the client passes, selected by ctime so files restored with old
   mtimes are caught (none on the first pull → everything; tar exit 1, "file changed as
   we read it", is tolerated and verify still guards the result) into `market_data.tar`;
   write `manifest.json` (row counts come from the dump, see §3). Outbox folders older
   than two hours are swept first.
2. **Stream** the outbox folder to the client.
3. **Clean** — delete the outbox folder. A client-side EXIT trap does it on failure too;
   if the connection is dead, the outbox (with `env`, mode 600) stays on the VM until the
   next stage sweeps it.

The fresh dump lands in `data/backups/db/` and ages out with the nightlies.

**Local layout** (the MAIN tree's `backups/`, resolved with `git rev-parse
--git-common-dir` so a worktree session never writes into a worktree that close-out
deletes; `SWINGBOT_BACKUPS_DIR` overrides it; already in `.gitignore` as `/backups/`;
this spec adds it to `.ignore`):

```
backups/
  pulls/<YYYY-MM-DDTHH-MMZ>/   db.sql.gz  env  deploys.jsonl  market_data.tar  manifest.json
  market_data/                 incremental mirror of the VM's market_data/
  stable/<name>/               pinned snapshots — never pruned
  LAST_PULL                    "<iso UTC> PASS|FAIL <pull dir>"
  LAST_GOOD_PULL               "<iso UTC> <pull dir> <vm_epoch>"
```

**Incremental market_data.** `since` = the previous good pull's `vm_epoch`
(the VM's own clock at stage time) minus 3600 s of overlap, so clock skew and
in-flight writes cannot drop a file. After `market_data.tar` verifies, it is
extracted over `backups/market_data/`. Files listed on the VM side are
compared with the local mirror: **files missing on the VM are reported, never
deleted locally**, so a bad refresh on the VM cannot wipe the off-VM copy. Files absent
locally or of a different size are reported too (`report-market`), never fetched or
deleted. `market_data.tar` stays in the pull folder so a retained pull can still be
re-verified; it goes with the folder on prune.

**Pass / fail.** A pull counts only if `backup_manifest.py verify` passes
(§3). On failure the folder is renamed `<stamp>.FAILED`, `market_data.tar` is
**not** extracted, `LAST_PULL` records FAIL, `LAST_GOOD_PULL` is untouched,
and the script exits non-zero. Any abort after the pull folder exists (stream,
extract, verify) is recorded the same way by the EXIT trap, which also prints
`pull_backups: FAIL ...`; an abort before a folder exists writes `LAST_PULL ... FAIL
nothing-pulled`; a same-minute stamp collision is refused. Local `tar` calls that name an
archive use `--force-local` (a drive-letter path is otherwise read as `host:file`).
After a pass, `prune` (`--keep` below 1 is rejected) keeps the newest 10 good
pull folders and removes `.FAILED` folders older than the newest good one;
it never touches `stable/` or `market_data/`.

**Overdue warning.** `.claude/hooks/session-cursor.ps1` emits one line:
`BACKUP   : last good pull 4d ago | newest stable stable-2026-10-01`, and
`BACKUP   : WARNING no good pull for 9d -- run /backup-pull` from 8 whole days (and
`WARNING no good pull yet` when none exists, or a warning when the folder named in
`LAST_GOOD_PULL` is missing). The separator is ASCII because this console prints a
middle dot as a CP437 byte. The hook reads the main tree's `backups/`. Codex runs the same script (`.codex/hooks.json`), so the
mirror is automatic. The hook stays wrapped: it can never fail a session start.

**Secrets.** Every `env` file holds live tokens. A test asserts
`git check-ignore` covers sample paths under `backups/`, so `git add -A`
cannot stage them.

### 3. The manifest helper

`scripts/ops/backup_manifest.py`, standard library only (it runs on the VM's
`python3` and on Windows):

- `build <dir> [--git-sha S] [--deploy-json F] [--restic-id ID] [--row-counts F] [--pg-version V] [--vm-epoch N] [--market-files F]`
  → `<dir>/manifest.json`: `schema: 1`, `created_utc`, `vm_epoch`, `git_sha`,
  `bot_image`, `db_image`, `restic_id`, `row_counts` (schema-qualified table → rows for
  every table the dump contains, counted from the dump's COPY blocks by `count-dump`, so
  they equal what a restore produces even while the bot writes; keys look like
  `public.trades`, quotes stripped),
  `pg_server_version`, `files` (name → sha256, bytes) for every file in the
  folder except the manifest, and `market_files` (path → bytes) when given.
- `verify <dir>` → exit 0 when every listed file exists with the listed sha256
  and size, no unlisted file is present, and every `*.gz` passes a full gzip
  read; else exit 1 with one line per problem.
- `prune <backups dir> --keep N` (N is at least 1; default 10) → as §2.
- `count-dump <dump.sql.gz>` → one JSON object, schema-qualified table → rows, from a
  plain `pg_dump -Fp` (the COPY blocks).
- `report-market <manifest> <root>` → report only: VM market files absent under `<root>`
  or of a different size.
- `next-name <YYYY-MM-DD> --existing <file of tag names>` → the next free
  `stable-…` name.

Every function stays under cyclomatic complexity 15.

### 4. Skills

Two Tier 2 skills (`disable-model-invocation: true`, no Trigger table, under
the 80-line budget, no bare thresholds), mirrored with
`python scripts/dev/sync_codex.py`, added to `TIER_2` in
`tests/hooks/test_skill_shape.py`, to the table in `skills-tools.md`, and to
the explicit-only list in `AGENTS.md`:

- **`stable-snapshot`** — `/stable-snapshot <note>`: read this spec's §1 and
  `DB_RESTORE.md`; check the preconditions; compute the name; run
  `stable_snapshot.sh` on the VM; tag and push; pull and verify; report the
  name, manifest summary and the `restore_stable.sh` command.
- **`backup-pull`** — `/backup-pull`: run `pull_backups.sh`; report PASS/FAIL,
  pull age, bytes added, and any files missing on the VM.

## Testing

Under `tests/scripts/`, beside `test_pitr_*` and `test_backup_db.py`:

- `test_backup_manifest.py` — build/verify round trip; verify fails on a
  flipped byte, a missing file, an unlisted file, a truncated gzip; prune keeps
  newest 10 good, drops older `.FAILED`, never touches `stable/`; `next-name`
  for none / same-day / `-2` taken.
- `test_pitr_crons.py` — `restic_hourly.sh`'s forget carries `--keep-tag stable`.
- `test_stable_snapshot_shape.py`, `test_restore_stable_shape.py`,
  `test_pull_backups_shape.py` — strict mode, LF endings, the refusal and
  `--dry-run`/`--i-mean-it` guards, outbox cleanup trap, never-delete-locally,
  in the style of `test_rollback_to_shape.py`.
- `test_backups_ignored.py` — `git check-ignore` covers `backups/pulls/x/env`,
  `backups/stable/x/env`, `backups/market_data/x.csv`; `.ignore` lists `backups/`.

## Drill — the off-VM copy counts only after this passes

Recorded in `DB_RESTORE.md` under a new "Off-VM copy" section:

1. First real `/backup-pull` → PASS.
2. Restore its `db.sql.gz` into a throwaway local Postgres container of the
   manifest's `pg_server_version` major (Docker is on this machine; `18.6` →
   `postgres:18`); exact row counts per table equal the manifest's `row_counts` (split the
   schema-qualified key at the first dot and quote both parts; never `n_live_tup`).
   Remove the container and volume.
3. First real `/stable-snapshot`; `restore_stable.sh <name> --dry-run` on the
   VM prints a plan naming the pinned dump, restic id and both images.

## Production changes

`restic_hourly.sh` and the three new VM scripts reach the VM through the
normal deploy (`deploy.sh` resets the checkout to `origin/main`); no cron
changes. Any hand step on the VM is mirrored per `mirror-prod`.

## Docs

- `DEPLOY_HETZNER.md`: the dump retention line (already corrected by v116's close-out), a short
  "Off-VM copy and stable snapshots" paragraph pointing at `DB_RESTORE.md`.
- v116 spec Honest limits: losing the VM now loses only what changed since
  the last good pull, plus point-in-time history.

## Honest limits

- **The pull is manual.** The off-VM copy is as old as the last `/backup-pull`;
  the SessionStart line is the only reminder.
- **The off-VM copy has no point-in-time history.** It restores to the pull,
  not to a second.
- **A stable point's market_data is pinned only on the VM** (restic). Off the
  VM, market_data is the rolling mirror, not the stable moment.
- **The laptop is now a secrets store.** Each pull's `env` is plaintext on
  this disk, as `.env` already is.
- **Posted Discord messages are never restored**, as with `rollback_to.sh`.
- **A real `restore_stable.sh --i-mean-it` has never been run**; only `--dry-run` was
  exercised. Open questions: a rotated DB password inside a pinned `env`, and `DROP DATABASE`
  blocked by a cron connection.
