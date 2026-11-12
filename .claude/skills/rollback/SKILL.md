---
name: rollback
description: "Code-only rollback -- put the VM's checkout and bot image back to an earlier main commit while keeping every trade and data row, and hold deploys until /rollback --release. Invoked explicitly as /rollback [target] [--release], never model-triggered."
disable-model-invocation: true
---

# Rollback (code only, keeps every trade)

## Step 1 — Read the authority, pick the path

`docs/deploy/DB_RESTORE.md` and the header of `scripts/ops/rollback_code.sh`.
This skill is the checklist. It keeps every trade, plan, journal row and
balance point: Postgres contents, the db container, `.env` values and the
market data cache are never touched, and no schema migration runs. If the
partner wants the data back too, this is the wrong path: stop and name
`scripts/ops/restore_stable.sh` (a stable point) or `scripts/ops/rollback_to.sh`
(a point in time).

## Step 2 — Always run main's script

The VM checkout may be an older target that lacks the script, so every call
takes it from `origin/main` first. `RB <args>` below means:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && runuser -u deploy -- git fetch -q origin main && runuser -u deploy -- git show origin/main:scripts/ops/rollback_code.sh > backups/rollback_code.sh && bash backups/rollback_code.sh <args>"
```

Exit codes: 0 pass, 1 failed (previous code and image already restored),
2 refused (nothing changed), 3 no-op. Show the partner the output as printed.

## Step 3 — Resolve the target

- Argument given (stable point, sha, `vNNN`, `vNNN-before`, `vNNN-after`,
  `bot-A.B.C`, UTC date): `RB --resolve <target>`. A refusal lists
  candidates; offer them with `AskUserQuestion`.
- No argument: `RB --candidates`, then `AskUserQuestion` with the newest rows
  whose `above_floor` is true, each labelled with bot version and plan ids;
  "Other" accepts any form above.
- A stable point resolves through its manifest `git_sha` or its git tag, so
  points made before v221 work; nothing here needs newer manifest fields.

## Step 4 — Dry run

Ask the partner for a one-line reason (it goes into the hold), then
`RB <sha> <image> --dry-run --reason "<reason>"`.

- Exit 3: already running there; stop.
- Exit 2 naming "market-data writer differs": Ask with `AskUserQuestion` before adding `--allow-writer-drift`,
  recommending to stop: the refresher then stays stopped, the admin may
  still write the cache, and the cache never self-heals
  (`docs/claude/known-traps.md`). Only on a yes, re-run the dry run with it.
- Any other exit 2: show the refusals and stop. Never work around one.
- Exit 0: show the plan (from and to, refresher, migrations, warnings).

## Step 5 — Execute on the partner's word only

Ask with `AskUserQuestion` before `--i-mean-it`, quoting from/to sha and image.
On a yes: `RB <sha> <image> --i-mean-it --reason "<reason>"` with the dry run's
flags. It takes a pgBackRest diff backup, writes the hold, switches checkout
and image (no Alembic), smoke-checks for up to three minutes, and on failure
restores the previous code and image by itself (exit 1: report and stop).
`/rollback <other target>` while held replaces the hold (Steps 3 to 5).

## Release (`/rollback --release`)

`RB --release --dry-run`, show it, Ask with `AskUserQuestion` before `--i-mean-it`, then
`RB --release --i-mean-it`. It removes the hold, checks out main, runs
`deploy/deploy.sh` with main's image, appends a release line and prints the
window report (rows the old code re-saved, keys dropped): show it verbatim.
Exit 3 means there was no hold. A failed release leaves the hold removed;
relay `deploy/deploy.sh`'s own message.

## The gate

Rolled back: `python scripts/dev/hold_status.py --refresh` then `--line`
shows the hold and the VM's `docker compose ps` shows admin healthy.
Released: no `HOLD` line. Nothing changed on the VM is missing from
`git log` (`mirror-prod`).
