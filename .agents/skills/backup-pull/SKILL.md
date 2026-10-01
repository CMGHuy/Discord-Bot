---
name: backup-pull
description: Pull a verified rebuild-from-zero backup set off the Hetzner VM into local backups/ and report the result. Invoked explicitly as /backup-pull, never model-triggered.
---
<!-- GENERATED from .claude/skills/backup-pull/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Backup pull

## Step 1 — Read the authority

Spec section 2 of
`docs/superpowers/specs/2026-10-01-v120-stable-snapshots-offsite-pull-design.md`.
This skill is the checklist; the reasoning lives there.

## Step 2 — Pull

```bash
bash scripts/ops/pull_backups.sh
```

It reaches the VM only through `scripts/ops/ssh-hetzner.sh`; never run a raw
`ssh` or `scp` instead. The copy lands in the main tree's `backups/`, even when
this session runs in a worktree.

## Step 3 — Report

Read the final `pull_backups: PASS` or `pull_backups: FAIL <reason>
pulls/<stamp>.FAILED` line (every abort path prints one) and report: PASS or
FAIL, the pull folder, bytes, files added, and any `missing on VM:`,
`absent locally:` or `size differs:` lines (report only: the pull never
deletes or re-fetches those; `backups/market_data/` is never pruned).

On FAIL, show the verifier's problem lines and stop. A refusal (exit 2, the
folder for this minute already exists) changed nothing: wait a minute and
rerun. Never delete a `.FAILED` folder by hand; the partner decides.

## The gate

A PASS line with the pull folder named, or a FAIL shown in full.
