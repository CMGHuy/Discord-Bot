# v60 — Session-habit guardrails

Version: ui 1.8.4 · bot 1.4.3
Bump: none
Edge: none (integrity)

## What this is

A `PreToolUse` hook that enforces, at the moment of the mistake, the token
rules `CLAUDE.md` already states in prose. Nothing here ships in the bot or
the admin — it is repo tooling only, which is why `Bump:` is `none`.

The `Edge:` line is `none (integrity)` and honest about it: this buys no
discriminator and harvests no R. It buys session budget, which is the
constraint that decides how much edge work fits in a day.

## Why prose rules are not enough

`CLAUDE.md` already says: scope `Glob` by hand, never read a plan file whole,
never `grep -r` from the repo root, never edit under `.claude/worktrees/`,
go through `scripts/dev/testrun.py`. Those rules are correct and they are
loaded into every session.

They still get broken, because they are recall-dependent and the moments they
apply are exactly the moments attention is elsewhere — mid-debug, mid-plan,
reaching for a file. A rule that fires only when remembered is a rule with a
silent failure mode.

The costs are measured, not hypothetical, and are already documented in the
repo:

| Pattern | Cost | Where documented |
|---|---|---|
| `Glob("**/*.py")` | 500 matches for 232 real files; ~70% worktree copies | `.ignore` header, verified 2026-07-26 |
| `Read` on `implemented/2026-07-11-v3-cockpit.md` | 648 KB ≈ 170K tokens, one call | `CLAUDE.md`, `document-conventions.md` |
| `grep -r` from repo root | walks ~2,600 files / 160 MB, times out at 20s, returns nothing | `.ignore` header |
| bare `python -m pytest` | ~1150 progress lines into context | `CLAUDE.md`, `testing-cost.md` |
| `Edit` under `.claude/worktrees/` | edits the wrong branch — a correctness bug, not a token one | `CLAUDE.md` |

## Design

One PowerShell script, `.claude/hooks/guardrails.ps1`, registered as a
`PreToolUse` hook in `.claude/settings.json`. That file today carries only
`SessionStart` and `Stop` hooks; this adds a third block and changes nothing
existing.

PowerShell to match the three hooks already in `.claude/hooks/`
(`session-cursor.ps1`, `notify.ps1`, `usage-watch.ps1`) and the `pwsh
-NoProfile -File` invocation they all use. No new runtime dependency.

The hook reads the tool call on stdin as JSON, matches it against the rules
below, and exits without output when nothing matches — the overwhelmingly
common case, and it must stay cheap enough to be invisible.

### Two tiers

**Deny** is reserved for patterns that are *always* wrong in this repo, where
a correct alternative always exists. The hook returns a permission decision of
`deny` with a reason. That reason is fed back into the session, so the
correction happens in the same turn rather than as a lost call.

**Warn** is for patterns that are usually wrong but legitimately needed
sometimes. The hook emits the nudge and allows the call.

### Rules

| Tier | Tool | Trigger | Message names |
|---|---|---|---|
| deny | `Glob` | `pattern` starts with `**/` | `Glob("swingbot/**/*.py")` — scope it |
| deny | `Bash` | `grep -r` / `rg` whose path is the repo root or `.` | the `Grep` tool, or `git grep` |
| deny | `Read` | path under `docs/superpowers/plans/implemented/` and file > 100 KB | `/task-brief <id>`, or `grep -n "^### Task <id>" -A 120 <plan>` |
| deny | `Edit`/`Write` | path contains `.claude/worktrees/` | edit from that worktree's own session |
| warn | `Bash` | `python -m pytest` with no file/node argument | `python scripts/dev/testrun.py fast`, or the `test-runner` subagent |
| warn | `Read`/`Bash` | `cat`/`Read` on `README.md`, `.superpowers/sdd/progress.md`, or any `.md` > 50 KB | the specific topic doc; `tail` for `progress.md` |

Each message states the alternative. A refusal that only refuses trains
nothing and costs a turn.

### What is deliberately not guarded

- **`Grep` with no `path`.** Legitimate and common; `.ignore` already makes it
  cheap. Guarding it would fire constantly for no gain.
- **Reading live plans at the top level of `plans/`.** They are within budget
  by convention (largest live one is 51 KB). Only `implemented/` holds the
  landmines.
- **Subagent count.** `CLAUDE.md` caps concurrent subagents at one, but a
  `PreToolUse` hook sees a single call and cannot count what is already in
  flight. Enforcing this needs session state the hook does not have; it stays
  a prose rule.
- **Anything advisory about *what* to read.** The hook guards mechanical
  patterns with unambiguous alternatives. Judgement stays with the operator.

## Failure modes

The hook sits in front of every tool call, so its own failure budget is
tight.

- **Hook crashes or times out.** Must fail open — a broken guardrail must
  never block work. Wrap the body so any unexpected error exits 0 silently.
  A 5-second timeout in the settings block, well above the expected cost.
- **A deny fires on legitimate work.** The escape hatch is explicit and
  documented in the message: for `Glob`, pass a scoped pattern; for a
  deliberate full-suite run, `scripts/dev/testrun.py full`; for genuinely
  needing a whole implemented plan, `git show` it or read it from the Bash
  side. No rule denies something with no route around it.
- **Stdin JSON shape changes.** Parse defensively; on any field being absent,
  allow.

## Verification

The hook is not covered by `pytest` — it is harness config, outside the
Python package. It is verified by direct exercise, one case per rule:

1. Feed each rule's trigger to the script as JSON on stdin, assert `deny` or
   `warn` as specified and that the message names the alternative.
2. Feed a benign call of each guarded tool, assert exit 0 with no output.
3. Feed malformed JSON and a missing-field payload, assert exit 0 (fail open).
4. In a live session: one denied `Glob("**/*.py")`, one allowed
   `Glob("swingbot/**/*.py")`.

A tiny fixture-driven harness under `scripts/dev/` runs 1–3 without a live
session so the rules stay checkable after later edits.

## Out of scope

Changes to `CLAUDE.md`'s prose. The rules already live there; this spec makes
them fire. If a hook rule and `CLAUDE.md` ever disagree, `CLAUDE.md` wins and
the hook is the thing that gets fixed.
