---
name: backup-pull
description: Pull a verified rebuild-from-zero backup set off the Hetzner VM into local backups/ and report the result. Invoked explicitly as /backup-pull, never model-triggered.
disable-model-invocation: true
---

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
`ssh` or `scp` instead.

## Step 3 — Report

Read the final `pull_backups: PASS` or `FAIL` line and report: PASS or FAIL,
the pull folder, bytes, files added, and any `missing on VM:` lines (say those
files were kept locally; the pull never deletes under `backups/market_data/`).

On FAIL, show the verifier's problem lines and stop. Never delete a `.FAILED`
folder by hand; the partner decides.

## The gate

A PASS line with the pull folder named, or a FAIL shown in full.
