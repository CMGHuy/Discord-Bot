---
name: mirror-prod
description: Use when about to change anything on the Hetzner production VM (167.233.26.185, scripts/ops/ssh-hetzner.sh, docker compose restart, editing .env, a hotfix applied live). Production changes must be mirrored back into this repo and committed before the task counts as done. Not for read-only production commands -- logs, docker ps, status checks.
---

# Mirror prod

## Step 1 — Read the authority

`docs/claude/working-conventions.md` for what "mirrored" means and why;
`docs/deploy/DEPLOY_HETZNER.md` for the VM itself. This skill does not
restate either.

## Step 2 — Production is never this machine

Confirm you are targeting the VM deliberately, not by habit. "Production"
means the Hetzner box, never the dev machine this session is running on —
say which one a command is about to touch before you run it.

## Step 3 — Write down the change before making it

The exact file, the exact edit. A live fix you cannot describe is a live fix
you cannot mirror — if you can't name the file and the diff in one sentence,
you don't yet know what you're about to do to the box.

## Step 4 — Mirror it back, same session

Apply the identical change to the repo, run the narrow test for the file you
touched, and commit. A `.env` change mirrors into the schema in
`swingbot/config.py` and the deploy doc, not just the VM — a value changed
only on the box is invisible here and reverts on the next manual edit.

## The gate

`git log` shows the mirroring commit. Until it does, the task is open,
regardless of production being healthy.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "it is a one-line config tweak" | Those are exactly the ones that vanish — nothing this small survives being remembered instead of committed. |
| "I will mirror it after the next deploy" | The next deploy overwrites it; the deploy pulls the image and the compose file from the repo, not the other way round. |
| "production is fine now" | Production being fine is not the deliverable — the repo matching what's running on the box is. |
| "I already told the human partner what I changed" | Telling is not mirroring; the gate is a commit in `git log`, not a message in the transcript. |

## Trigger table

Should fire: about to SSH into the VM and edit a file by hand.
Should fire: restarting a container on the VM after changing something on it.
Should fire: hand-patching a file on the VM to stop a live incident.
Should fire: editing `.env` directly on the server through the admin UI or a shell.
Should not fire: tailing `docker compose logs` to read what happened.
Should not fire: running `docker ps` or `docker compose ps` to check container status.
Should not fire: reading a container's env or config on the VM to answer a question, with no edit made.
