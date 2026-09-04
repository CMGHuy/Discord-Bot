# v71 — Silent-failure hardening: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-04-v71-silent-failure-hardening-design.md`
**Version:** ui 1.11.0 · bot 1.6.0
**Bump:** ui patch (1.11.0 → 1.11.1) · bot patch (1.6.0 → 1.6.1)
**Edge:** none (integrity)

**Goal:** Make the end-of-session retrospective post reliably again, stop one bad
value from destroying a whole report, and make the dashboard tell the truth when
the bot is alive but failing.

**Architecture:** Four independent changes. Guard nullable metrics at the format
site rather than coercing them at the source; wrap each retrospective part in a
context manager so a failing part costs one section; extend the heartbeat file
with tick *outcome* (not just liveness) and escalate a sustained outage to
Discord; add a pyflakes undefined-name gate to the pre-commit runner.

**Tech Stack:** Python 3.11, pytest, discord.py, Flask (admin API), Angular
signals + `signalStore` (frontend), pyflakes.

## Global Constraints

- **`metrics.win_rate()` returns `None`, never `0.0`, when there are no win/loss
  trades.** Never coerce it. `metrics.py:211` — *"'no data yet' and '0% win
  rate' must never look the same on a UI."* Fix every site at the point of
  formatting.
- **`n > 0` never implies `win_rate is not None`.** `n` counts all trades at a
  level; `win_rate` counts only `status in ("win", "loss")`.
- **The health indicator introduces no green and no red.** `connection-status.ts`
  (NG52 colour review): *"Greyscale and amber, never green or red: connection
  state is not money."* Two severities of the same caution are both
  `var(--warn)`, told apart by their **label**.
- **Heartbeat readers must tolerate missing fields.** An upgraded admin
  container reads files written by a not-yet-restarted bot. Absent
  `last_success` means "unknown, not yet failing" — never "failing".
- **Per-task verification is the narrow run:** `python scripts/dev/testrun.py
  file tests/<the one file this task touched>.py` (~7s). Never `full`
  per task — the full suite runs once, in Task H15.
- **`bot.get_channel(int(<id>))`** is how a channel is resolved in this
  codebase. The alerts channel is additionally wrapped in `silence()`; ops
  escalation is **not** silenced — it must notify.
- Commit after every task. Do not bump `VERSION.json` in any task — the release
  bump is a separate deliberate commit after this plan lands.

## Parts

A task's id never changes when a file splits: `grep -rn "^### Task H8"
docs/superpowers/plans/` finds it without knowing which part it landed in.

| Part | Phases | Tasks | What it does |
|---|---|---|---|
| `_1-crash-and-isolation` | A, B | H1–H4 | Guard the three nullable-metric format sites; isolate each retrospective section |
| `_2-health-signal` | C | H5–H12 | Heartbeat tick outcome, Discord escalation, admin payload, frontend indicator, v67 routing |
| `_3-gate-and-verification` | D, E | H13–H15 | Import `ScanProgress`; gate undefined names; the single full-suite run |

## Parallelisation

Across parts, the order is **_1 → _2 → _3**, but only the last edge is a hard
dependency: `_3`'s gate (H14) must run against the finished tree, and it stays
red until H13 lands.

`_1` and `_2` touch disjoint files and may be worked concurrently:

- `_1` edits `retrospective.py`, `insights.py`, `analyze.py`.
- `_2` edits `runstate.py`, `loops.py`, `config.py`, `admin/app.py`, `frontend/`.

Per-phase groupings are stated in each part. The one cross-part caution:
**`_2`'s H12 edits a v67 plan file**, so do not run it concurrently with a
session working v67 itself.

## Exit criteria

- The end-of-session retrospective posts on a day whose only closed trades are
  manual closes, rendering `n/a` rather than raising.
- A raise inside one retrospective part costs that part only, and the report
  says so.
- `bot_healthy` distinguishes "process looping" from "ticks completing", the
  shell shows `bot failing`, and a sustained outage posts exactly one Discord
  alert plus one recovery notice.
- `python scripts/dev/testrun.py full` fails on any undefined name, and is
  green on this tree.
- H15's full Python and frontend runs are both green.
