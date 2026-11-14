---
name: prod-incident
description: "Use when the partner reports an issue, bug, error, outage or anything wrong on production -- the live Discord bot, bomeo-capital.com, the admin UI, the refresher, missing or odd alerts, a 504, a crash -- before investigating or fixing it. Not for a bug seen only on the dev machine or in tests, and not for a planned deploy (that is /deploy)."
---

# Prod incident

## Step 1 — Read the authority

`docs/deploy/DEPLOY_HETZNER.md` (§ "How it works, in short", § "Rolling back",
§ "PostgreSQL (the only store)", § "Troubleshooting") for the VM's shape;
`docs/claude/known-traps.md` before touching caches or `.env`. Then load
`superpowers:systematic-debugging` — no fix before a root cause.

## Step 2 — Pin down the report

What broke, on which surface (bot / admin / refresher / db / tunnel), since when.
Ask with `AskUserQuestion` only if the surface is ambiguous; otherwise start.

## Step 3 — Look, read-only (standing permission, no asking)

Every command goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"`, never a
raw `ssh`/`scp`; remote `$(...)`/`$VAR` expand locally, so pipe a script
on stdin. Hand log volume to the `prod-inspector` agent, one question
per dispatch, so raw logs stay out of this context.

- **Status:** `cd /opt/swing-bot && docker compose ps`, `df -h`, `uptime`.
- **Logs:** `/opt/swing-bot/logs/{bot,admin}.log[.N]`, not `docker logs`
  (a deploy empties it). Tally error classes; split **still firing in the
  current file** from **only in rotated files** (usually already fixed).
- **Data:** read-only `docker compose exec -T db psql -U swingbot -d swingbot`.
- **What is running:** the image tag pinned in the VM's `.env`; compare with
  `git log origin/main` to tell "not deployed yet" from "deployed and broken".
- **UI symptoms:** drive bomeo-capital.com with Playwright only, logged in with
  `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the script, never
  printed. Before any probe, check for orphaned probe/Chromium processes on
  this machine — they have overloaded prod before.

## Step 4 — Reproduce locally

`/replicate-prod-db`, then a failing test that shows the bug — no red test, no fix.

## Step 5 — Fix through the normal path

| Situation | Route |
|---|---|
| Code bug | Fix + test on a branch/worktree, merge, push; CI deploys. Watch the run to green (`working-conventions.md` § Pipeline watch). |
| Config value | `python3 scripts/ops/env_set.py KEY value` on the VM (never `sed -i`), then mirror into `swingbot/config.py`/docs. |
| Bleeding now, fix not ready | Roll back as the deploy doc's "Rolling back" section says (or `scripts/ops/rollback_to.sh '<UTC time>'` — a timestamp, not an image tag; `--dry-run` first); ask the partner first. |
| Hand edit on the VM | Only under the `mirror-prod` skill; mirrored commit before done. |

Every write to the VM — a restart included — needs the partner's go-ahead,
saves the evidence logs first, and goes through `mirror-prod`.

## Step 6 — Verify on production and report

After the deploy, re-run the Step 3 check that showed the bug and confirm it
is gone from the **current** log. Report: root cause, the fix commit, the
evidence it is live, and anything historical that was not this bug.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "`docker logs` shows no errors" | A deploy recreated the container; the history is in `/opt/swing-bot/logs/`. |
| "this error is all over the logs" | Check it fires in the current file, not only rotated ones. |
| "quick patch on the box, mirror later" | Next deploy erases it; `mirror-prod` gate applies. |
| "restart now, find the cause later" | A restart erases the evidence and hides the bug; ask first, save logs first. |
| "no alerts, so the bot is broken" | Quiet days are usually the 2% cap: grep `plan rejected (` before calling it a bug. |
| "the dev machine shows the same thing" | Production is only the Hetzner VM; the local journal is fixture data. |

## Trigger table

Should fire: "there's an issue on production, the bot stopped posting alerts".
Should fire: "bomeo-capital.com shows a 504 on the dashboard".
Should fire: "something's wrong in prod, the trades page is empty".
Should fire: "the live bot crashed overnight, can you fix it?".
Should not fire: a unit test fails locally after an edit.
Should not fire: "deploy main to Hetzner" with nothing reported broken.
Should not fire: "run a backtest of the RSI strategy".
