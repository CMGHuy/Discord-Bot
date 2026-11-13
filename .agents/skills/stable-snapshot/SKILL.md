---
name: stable-snapshot
description: "Pin a known-good point -- VM snapshot folder, annotated stable-* git tag, and an off-VM copy -- and print the restore command. Invoked explicitly as /stable-snapshot, never model-triggered."
---
<!-- GENERATED from .claude/skills/stable-snapshot/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Stable snapshot

## Step 1 — Read the authority
Spec sections 1, 2 and 4 of
`docs/superpowers/specs/implemented/2026-10-01-v120-stable-snapshots-offsite-pull-design.md`,
then `docs/deploy/DB_RESTORE.md`. Rollback fields and image pinning (v221): Section 2
of `docs/superpowers/specs/2026-11-08-v220-code-only-rollback-design.md`. Ask the
partner for a one-line tag note.

## Step 2 — Preconditions (create nothing until all hold)
All VM access goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`, never a raw `ssh`.

- Local: branch is `main`, `git status --porcelain` prints nothing, and after
  `git fetch` `git rev-parse HEAD` equals `git rev-parse origin/main`.
- VM: `runuser -u deploy -- git -C /opt/swing-bot rev-parse HEAD` (git always
  runs as `deploy`, the checkout's owner; as root it refuses) and the
  `git_sha` of the last line of `backups/deploys.jsonl` both equal local HEAD.
- VM: `cd /opt/swing-bot && docker compose ps` shows `bot` and `admin` running.
- VM: no deploy hold, `test ! -e /opt/swing-bot/backups/deploy_hold.json`. While
  `/rollback` holds deploys the VM runs a rollback target, not `main`: release
  first (`/rollback --release`).

Any miss: stop and tell the partner which one.
## Step 3 — Name
Write `git tag -l 'stable-*'` plus `git ls-remote --tags origin 'stable-*'`
(strip the `refs/tags/` prefix and the `^{}` suffix) to a scratch file, then
`python scripts/ops/backup_manifest.py next-name <UTC date> --existing <that file>`.

## Step 4 — Snapshot on the VM, first
Run `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/stable_snapshot.sh <name>"`.
The manifest JSON is its last output; keep it for Steps 4b, 5 and 7. If the ssh
snapshot fails, stop -- do NOT tag, and report the failure.

## Step 4b — Pin both images
The VM's GHCR login is read only: a workflow tags both manifest images `<name>`
(registry pruning skips `stable-*` tags).
```bash
gh workflow run pin-stable-image.yml -f name=<name> -f bot_image=<bot_image> -f db_image=<db_image>
gh run list --workflow pin-stable-image.yml -L 5 --json databaseId,displayTitle --jq '.[] | select(.displayTitle=="pin <name>") | .databaseId'
gh run watch <id> --exit-status
```
`<bot_image>`, `<db_image>`: the manifest's `bot_image` and `db_image`. Empty
list: wait, list again. Failed run: `gh run rerun <id>` once; failing again:
stop, do NOT tag, report `gh run view <id> --log-failed`. The VM folder stays.

## Step 5 — Tag, then push
`git tag -a <name>` with a message of: the partner's note, `ui` and `bot` from
`VERSION.json`, and the manifest's `bot_image` and `db_image` (image references:
the immutable `sha-` tags from `deploys.jsonl`). Then `git push origin <name>`;
on failure retry only the push. Never `git branch` for a stable point, and never
touch the three existing `stable-*` branches.

## Step 6 — Pull it off the VM
`bash scripts/ops/pull_backups.sh --stable <name>`. It lands in the main
tree's `backups/stable/`. A failure leaves a `backups/stable/<name>.partial`
folder: report it, do not delete it. Recovery: the partner inspects it,
deletes the .partial by hand, then re-runs Step 6 only (VM folder and tag stay).

## Step 7 — Report
Name, manifest summary (git SHA, both images, restic id, table count, bytes),
and the rollback fields: `alembic_head`, `bot_version` / `ui_version`,
`config_keys_sha256` (first 12 chars), `features` (one line per entry,
`<plan or -> <sha 8> <subject>`). Then:
- the floor verdict from `python scripts/ops/rollback_plan.py floor <git_sha>`
  (`above floor`, or each `below floor:` line: a code-only rollback would be refused);
- the code-only rollback `/rollback stable-<name>` (keeps every trade);
- the whole-bot restore `scripts/ops/restore_stable.sh <name> --dry-run`; a
  real restore needs `--i-mean-it`. This skill never runs one, nor a rollback.

## The gate
The VM folder, both `<name>` image tags, the pushed git tag and the main tree's `backups/stable/<name>/` all exist.
