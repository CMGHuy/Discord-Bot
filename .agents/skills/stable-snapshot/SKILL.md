---
name: stable-snapshot
description: Pin a known-good point -- VM snapshot folder, annotated stable-* git tag, and an off-VM copy -- and print the restore command. Invoked explicitly as /stable-snapshot, never model-triggered.
---
<!-- GENERATED from .claude/skills/stable-snapshot/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Stable snapshot

## Step 1 — Read the authority

Spec sections 1, 2 and 4 of
`docs/superpowers/specs/2026-10-01-v120-stable-snapshots-offsite-pull-design.md`,
then `docs/deploy/DB_RESTORE.md`. This skill is the checklist; the reasoning
lives there. Ask the partner for a one-line note for the tag.

## Step 2 — Preconditions (create nothing until all hold)

All VM access goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`, never a
raw `ssh`.

- Local: branch is `main`, `git status --porcelain` prints nothing, and after
  `git fetch` `git rev-parse HEAD` equals `git rev-parse origin/main`.
- VM: `git -C /opt/swing-bot rev-parse HEAD` and the `git_sha` of the last line
  of `backups/deploys.jsonl` both equal local HEAD.
- VM: `cd /opt/swing-bot && docker compose ps` shows `bot` and `admin` running.

Any miss: stop and tell the partner which one.

## Step 3 — Name

Write `git tag -l 'stable-*'` plus `git ls-remote --tags origin 'stable-*'`
(strip the `refs/tags/` prefix and the `^{}` suffix) to a scratch file, then:

```bash
python scripts/ops/backup_manifest.py next-name <UTC date> --existing <that file>
```

## Step 4 — Snapshot on the VM, first

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash scripts/ops/stable_snapshot.sh <name>"
```

The manifest JSON is its last output; keep it for Steps 5 and 7.

## Step 5 — Tag, then push

`git tag -a <name>` with a message of: the partner's note, `ui` and `bot` from
`VERSION.json`, and both image digests from the manifest. Then
`git push origin <name>`. If the push fails, retry only the push; the VM folder
stays. Never `git branch` for a stable point, and never touch the three
existing `stable-*` branches.

## Step 6 — Pull it off the VM

`bash scripts/ops/pull_backups.sh --stable <name>`. A failure here leaves a
`.partial` folder: report it, do not delete it.

## Step 7 — Report

Name, manifest summary (git SHA, both images, restic id, table count, bytes),
and the restore command `scripts/ops/restore_stable.sh <name> --dry-run`. Say
a real restore needs `--i-mean-it`; this skill never runs one.

## The gate

The VM folder, the pushed tag and the local `backups/stable/<name>/` all exist.
