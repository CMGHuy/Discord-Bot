# v161 — Trade scout: generator roles that turn the live book into ranked hypotheses

**Version:** ui 1.23.1 · bot 2.5.0 (at writing)
**Bump:** none — repo tooling only (`.claude/` skills and agent, `scripts/`), no running bot or UI code changes.
**Edge:** none (integrity) — produces hypotheses, never a lift by itself. Every row it emits still has to earn a `SCREEN-PASS` or a pre-registration before any spec.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, veteran-trader, staff-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (approach "A and B": one orchestrator plus three generator roles). Sub-project 1 of 2; the live alert desk is sub-project 2, not specified here.

## Why

The pre-registration ledger (`docs/superpowers/results/preregistration-ledger.jsonl`)
holds 65 rows on 2026-10-14: 39 NO-LIFT, 7 FAIL, 6 UNMEASURABLE, 3 SCREEN-FAIL,
5 PASS and 1 SCREEN-PASS. The gate works. What limits the bot issuing more and
better plans is the **hit rate of the ideas fed into it**: most hypotheses reach
the ledger from whoever is in the session, not from the evidence in the live book.

All nine expert role skills (`docs/claude/skills-tools.md` § Expert roles) are
reviewers. They reject defects; none proposes. The data a proposer needs already
exists: each closed trade's journal entry carries `mae_r`, `mfe_r` and exit
efficiency (`swingbot/core/analytics/journal.py:196`, `exit_quality.py`), and
`scripts/reports/runner_headroom.py` measures runner give-back. The v82 follow-on
left an open lead: `check_near_tp_timeout` (`swingbot/commands/scanning/loops.py:597`)
closes stalled trades early.

This spec adds a generator side: trader-lens roles that read a deterministic
autopsy of the live book and propose ranked, deduplicated hypotheses for
`/screen` and `/prereg`. It changes no code path, threshold or alert.

## Hard boundaries

1. **No gate moves.** A slate row is a hypothesis. It never edits code, config,
   thresholds or live alerts, and never licenses a re-run of a closed
   pre-registration (`docs/claude/backtest-methodology.md` § Closed
   pre-registrations — do not re-run these).
2. **Every entry or filter idea still needs a `SCREEN-PASS`** row before its
   spec (root `CLAUDE.md` § Prioritise expectancy and win rate).
3. **No paid usage** (`docs/claude/working-conventions.md` § Paid usage): the
   autopsy is a plain script; the roles run as subagents on the subscription.
4. **Numbers come from one autopsy run.** A role quotes only figures printed in
   the autopsy report it was given, with that report's window and N
   (`pooled-numbers`). The production book is read read-only.

## Architecture

```
scripts/reports/book_autopsy.py        (deterministic, read-only, no model)
        │  docs/superpowers/results/<date>-book-autopsy.{json,md}
        ▼
/trade-scout [roles=exit-harvester,setup-scout,regime-desk] [autopsy=<path>]
        │  one `scout` agent dispatch per role, serially (Sonnet)
        ├── exit-harvester
        ├── setup-scout     (also reads references/playbook.md)
        └── regime-desk
        ▼
scripts/dev/scout_merge.py  →  drop closed / duplicate rows, rank
        ▼
docs/superpowers/results/<date>-scout-slate.md   (committed on main)
        ▼
/panel quant-researcher <slate>  →  partner picks rows  →  /screen or /prereg
```

## Components

### 1. `scripts/reports/book_autopsy.py`

- **Runs** inside the bot container on the VM:
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < scripts/reports/book_autopsy.py > <local json>`.
  Never against the local database (`local-journal` is fixture data).
- **Read-only:** `SELECT` statements only, through the existing repository read
  helpers where one exists. A test greps the module for
  `INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP` and fails on any hit.
- **Inputs:** closed `journal_entries` (outcome R, `mae_r`, `mfe_r`, exit
  reason, strategy, horizon, direction, regime fields, entry weekday, earnings
  and OPEX proximity where stored); counts of `plan rejected (` reasons from
  `/opt/swing-bot/logs/*.log*` (current and rotated, split as
  `production-log-investigation` describes).
- **Cuts** (each a table of cells): strategy × horizon; direction; regime
  bucket; entry weekday; earnings proximity; exit reason; give-back
  (`mfe_r - realised_r` on winners); near-stop reversals (losers whose MAE
  reached within 0.2R of the stop before the close, and trades that hit the stop
  and later traded beyond entry within the horizon, where bars are available);
  `check_near_tp_timeout` closes; rejected-plan reasons.
- **Every cell** carries N, win rate, ExpR and a week-cluster bootstrap 95%
  interval from `week_cluster_bootstrap`
  (`swingbot/core/backtesting/instrument/stats.py:57`). A cell with N < 30 is
  labelled `thin` and is never ranked as evidence.
- **Header** prints the window, total N and pooled ExpR and win rate once; roles
  quote only these.
- **Output:** JSON (machine-read by the merge) plus a compact Markdown summary
  (≤ 150 lines, the only thing a role reads), committed under
  `docs/superpowers/results/`.
- Every function under complexity 15 (`docs/claude/code-complexity.md`).

### 2. Three generator role skills

Same file shape as the reviewer roles, except the first heading is
`## Generator lens` (see Codex mirror and docs) — `## Checklist` (here: where
to look), `## Red flags` (here: what the role must not propose), `## Out of
scope`, `## Trigger table` — plus a `## Row format` section. A generator emits
**at most 5 rows**. Each row:

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: <autopsy cut + cell, N, ExpR [CI]>  |  playbook: <entry id>
  edge: expectancy | harvest | volume
  mechanism: <why a trader expects it to pay, one or two sentences>
  pairs_with: <for any tightening: where the volume or R comes back; else n/a>
  route: /screen <idea>  |  /prereg  |  harvest-headroom <results path>
```

The skills share the reviewer roles' boundary sentences (never decide, never
lower a gate, `pooled-numbers`, `backtest-gate`) so the existing
`test_role_skills.py` boundary pattern applies.

**`exit-harvester`** — money earned and given back, or never taken.
- Look at: winners with MFE ≥ 2 × realised R (trail / scale-out headroom,
  cross-checked against `runner_headroom.py`); losers whose MAE sat near the
  stop and reversed beyond entry (stop placement or entry timing); stalls closed
  by `check_near_tp_timeout`; holding time against R per horizon; gap-through-stop
  losses beyond 1R.
- Must not propose: v129 acceptance-failure exits (arm Z / arm B), v139
  structural stop or stop drop, `DATA_DRIVEN_STOPS_ENABLED`, a tighter stop
  sold on ExpR without the dollar view at fixed risk (R-unit inflation).

**`setup-scout`** — entries the bot doesn't take, or takes badly.
- Look at: cells with ExpR above the pooled figure whose interval excludes it,
  at N ≥ 30; rejected-plan reasons that block plans (a volume lever, to be
  measured in shadow, not assumed); setups in `references/playbook.md` absent
  from `strategy_types.py`; variants of the one `SCREEN-PASS`
  (`screen-uptrend_pullback`) that are a new mechanism, not a new threshold.
- Must not propose: any SCREEN-FAIL idea under a new name (`high52w`,
  `gap_volume`, `turn_of_month`); v122 volume dry-up, v127 structure-break
  armed entries, v128 FVG level modes, v131 Fibonacci limit, v135 headroom veto,
  v143 FVG-bullish features, v36 touch strength, v49 effective confluence,
  v68 dead-cat-bounce veto; a cell picked after looking without saying it is
  exploratory.

**`regime-desk`** — when to trade or stand aside.
- Look at: ExpR by index trend, volatility and breadth bucket (`regime2.py`,
  `market_context.py`); weekday and Friday entries; OPEX week; sector clustering
  of same-day losers (`correlation.py`).
- Must not propose: the `REGIME_ALLOW` gate (v17 P2a: 0 of 44 cells),
  `EARNINGS_BLACKOUT_SESSIONS` (v82: near-earnings trades scored better), any
  regime variable not point-in-time, a stand-aside filter whose only effect is
  to cut N without naming where volume comes back
  (`feedback-yield-over-pure-integrity`).

### 3. `references/playbook.md` (under the `setup-scout` skill)

Curated trader setups, each with an id, the textbook rule, the horizon it fits
and the failure mode a trader watches for. Kept out of `SKILL.md` so the skill
stays small and the playbook loads only for `setup-scout`. Seed entries
(the partner may edit): pullback to a rising 20 EMA in a stage-2 uptrend;
failed-breakdown reclaim of a prior low; inside day after a trend leg;
narrow-range-7 contraction; post-earnings-announcement drift; first pullback
after a 52-week-high breakout with volume; three-bar reversal at a weekly level.
Every entry names the closed ledger rows it must not duplicate.

### 4. `scout` agent (`.claude/agents/scout.md`)

Read-only, `model: sonnet`, tools `Read, Grep, Glob, Skill`. Prompt names
`role=<generator>` and the autopsy Markdown path. It loads the role skill, reads
only the autopsy summary (and the playbook for `setup-scout`), and returns the
row list in the Row format, or `NO ROWS` with one line why. It never runs SQL,
a backtest or the test suite. An unknown role returns `UNKNOWN ROLE` naming the
three valid ones.

### 5. `trade-scout` skill (`.claude/skills/trade-scout/SKILL.md`)

User- and model-invocable (`/trade-scout`). Steps:
1. Use the newest `*-book-autopsy.md` under `docs/superpowers/results/`; if it
   is older than 7 days or absent, ask the partner before running the autopsy
   on the VM (it is read-only, but it is a production command).
2. Dispatch `scout` once per role, serially — never in parallel.
3. Write the role outputs to a scratch file and run
   `python scripts/dev/scout_merge.py <file>`.
4. Commit the slate on `main`; run `/panel quant-researcher <slate>` and append
   its findings to the slate as `## Panel review`.
5. Present the top rows to the partner with `AskUserQuestion`, one question,
   recommended row first. The partner's pick goes to `/screen` or `/prereg`;
   the scout itself starts neither.

### 6. `scripts/dev/scout_merge.py`

Deterministic. Parses rows; **drops** a row whose `idea` matches a ledger `id`
or hypothesis (case-insensitive, normalised kebab-case), or one listed in a
`closed_ideas` table the script parses from `backtest-methodology.md` § Closed
pre-registrations, and records every drop with its reason in the slate's
`## Dropped` section. Drops `thin` evidence rows unless `route` is a playbook
`/screen`. **Ranks** by `edge` (expectancy, then harvest, then volume), then the
evidence cell's interval lower bound, then N. Writes
`docs/superpowers/results/<date>-scout-slate.md` with the autopsy header
(window, N) copied verbatim.

## Token budget

Each role reads its skill (~3.5 KB) plus the autopsy Markdown (≤ 150 lines);
the playbook only for `setup-scout`. At most three Sonnet dispatches per run,
serial; only the merged slate reaches the controller. The autopsy and the merge
are scripts — the model never crunches the book.

## Codex mirror and docs

- `python scripts/dev/sync_codex.py` for the three role skills, `trade-scout` and
  the `scout` agent; `tests/hooks/test_codex_mirror.py` must pass.
- `docs/claude/skills-tools.md`: a `## Generator roles (v161)` section beside
  Expert roles, and `scout` in § Which agent for what. `AGENTS.md` gets one line
  in its Skills section, staying under the 32 KiB cap.
- The generator roles are **not** registered in `test_role_skills.py`'s `ROLES`
  (that test pins *reviewer* roles via `## Lens`). They use `## Generator lens`
  instead, so `lens_skills()` does not pick them up, and get their own shape test.

## Testing (free, local)

New directory `tests/scout/`, added to exactly one suite in `tests/suites.toml`
in the same commit (`docs/claude/testing-cost.md` § Test suites):

- autopsy: cell math on a fixture journal (N, WR, ExpR, `thin` below 30,
  bootstrap called with week clusters), give-back and near-stop-reversal cuts,
  header printing window and N, the read-only grep.
- merge: a ledger id, a closed-table name and a renamed SCREEN-FAIL idea are
  each dropped with a reason; ranking order; `thin` handling.
- generator role shape: the five sections plus Row format, boundary sentences,
  the "at most 5 rows" rule, and each role's red-flag list naming the closed
  rows above.
- skill and agent: `trade-scout` names serial dispatch and the merge script;
  `scout` lists only read-only tools.

## Out of scope

- Sub-project 2, the **live alert desk** (pre-open annotation of each day's
  alerts reusing the autopsy cuts), gets its own spec.
- Running any slate row through `/screen` or `/prereg`.
- Any change to `swingbot/` runtime code, thresholds or the admin UI.
- A scheduled autopsy cron (can follow once the manual run has proven useful).
