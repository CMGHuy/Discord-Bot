# v161 — Trade scout: generator roles that turn the live book into ranked hypotheses

**Version:** ui 1.23.1 · bot 2.5.0 (at writing)
**Bump:** none — repo tooling only (`.claude/` skills and agent, `scripts/`), no running bot or UI code changes.
**Edge:** none (integrity) — produces hypotheses, never a lift by itself. Every row it emits still has to earn a `SCREEN-PASS` or a pre-registration before any spec.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, veteran-trader, staff-engineer
**Status:** spec written 2026-10-15 from a brainstorm with the partner (approach "A and B": one orchestrator plus three generator roles); panel review applied (see the end). Sub-project 1 of 2; the live alert desk is sub-project 2, not specified here.

## Why

The pre-registration ledger (`docs/superpowers/results/preregistration-ledger.jsonl`)
holds 65 rows on 2026-10-14: 39 NO-LIFT, 7 FAIL, 6 UNMEASURABLE, 3 SCREEN-FAIL,
5 PASS, 1 SCREEN-PASS, 3 OPEN and 1 WITHDRAWN. The gate works. What limits the
bot issuing more and better plans is the **hit rate of the ideas fed into it**:
most hypotheses reach the ledger from whoever is in the session, not from the
evidence in the live book.

All nine expert role skills (`docs/claude/skills-tools.md` § Expert roles) are
reviewers. They reject defects; none proposes. The data a proposer needs already
exists: each closed trade's journal entry carries `mae_r`, `mfe_r` and exit
efficiency (`swingbot/core/analytics/journal.py:196`, `exit_quality.py`), and
`scripts/reports/runner_headroom.py` measures runner give-back. The v82 follow-on
left an open lead: `check_near_tp_timeout`
(`swingbot/core/tracking/performance.py:1499`) closes stalled trades early.

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
5. **Every autopsy-derived row is exploratory, and the holdout is protected.**
   The live book's window (printed in the autopsy header) overlaps the frozen
   holdout (`HOLDOUT_START = "2026-01-01"`, `scripts/backtest/measure_v104.py:37`).
   A row is chosen after looking at that window, so: its `/prereg` must freeze
   its thresholds and score them on TRAIN/VALIDATION windows that end before the
   autopsy window starts, and the pre-registration must record that the holdout
   is **contaminated for that idea** (it may not be spent as confirmation). A
   `/screen` route is unaffected (PIT S&P 500 2010-2019 does not overlap).

## Architecture

```
VM (read-only):  psql READ ONLY export  →  rows.csv     host grep of logs  →  rejections.csv
        │  (over scripts/ops/ssh-hetzner.sh; no Python in the bot container)
        ▼
local:  scripts/reports/book_autopsy.py  rows.csv rejections.csv
        │  docs/superpowers/results/<date>-book-autopsy.{json,md}
        ▼
/trade-scout [roles=exit-harvester,setup-scout,regime-desk] [autopsy=<path>]
        │  one `scout` agent dispatch per role, serially (Sonnet)
        ├── exit-harvester
        ├── setup-scout     (also reads references/playbook.md)
        └── regime-desk
        ▼
scripts/dev/scout_merge.py  →  drop closed / duplicate / unsupported rows, rank
        ▼
docs/superpowers/results/<date>-scout-slate.md   (committed on main)
        ▼
/panel quant-researcher <slate>  →  partner picks rows  →  /screen or /prereg
```

## Components

### 1. Export (VM) and `scripts/reports/book_autopsy.py` (local)

**Export — the whole production footprint is two read-only commands:**

- `scripts/ops/export_book_rows.sh` (committed; runs on the VM through
  `ssh-hetzner.sh`): one `psql` session opened with
  `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, then a single
  `\copy (SELECT <listed columns> FROM journal_entries JOIN ...) TO STDOUT CSV HEADER`.
  The column list is fixed in the script. No Python runs in the bot container, so
  no repository helper and no deployed-image version is involved, and the scan
  loop's CPU is untouched beyond one SELECT.
- Rejection counts: `grep -h "plan rejected (" /opt/swing-bot/logs/*.log*` on
  the **host** (the host path; the container sees `/app/logs`,
  `docker-compose.yml:141`), split current versus rotated per
  `production-log-investigation`, reduced to `date,reason,count` on the VM.
- Both are written to local files under the scratchpad, never committed (raw
  production rows). A test pins that the export script contains `READ ONLY` and
  no `INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE`.

**Columns exported** (the plan's brief resolves exact names against
`swingbot/core/db/schema.py`): trade id, ticker, sector, strategy, horizon,
direction, plan time, fill time and fill status (filled / expired unfilled /
never touched), planned entry, actual fill, open price on the fill day, stop,
targets, stop distance in ATR, exit time, exit reason (including the value
`check_near_tp_timeout` writes), realised R net of frictions, gross R,
`mae_r`, `mfe_r`, regime fields, earnings/OPEX/macro-event proximity where
stored, dollar volume and ATR% at signal, alert hour.

**`book_autopsy.py` — local, deterministic, no model, no network.**

- Reads the two CSVs; computes every cut locally (bootstraps never run on the VM).
- **Cuts:**
  - strategy × horizon; direction; ticker and sector concentration;
  - regime bucket; entry weekday and Friday/weekend hold; earnings, OPEX and
    macro-event (FOMC, CPI, NFP via `swingbot/core/market/events.py`) proximity;
  - **fill reality:** fill rate (filled / expired unfilled / never touched),
    open gap against planned entry, entries that gapped through the limit;
  - **liquidity and volatility:** dollar-volume and ATR% buckets;
  - **alert supply:** alerts per day, alert hour against the session, count
    actionable before the open; rejected-plan reasons;
  - **exits, full population:** exit reason; `check_near_tp_timeout` closes;
    give-back (`mfe_r - realised_r`) reported for **all** trades, not winners
    only; near-stop reversals reported beside the trades a wider stop would
    still have lost; **gap-through-stop** (realised R below −1 on stop exits,
    with the gap size); holding time against R per horizon.
- **Every cell** prints N, distinct weeks, win rate, net ExpR, gross ExpR, and
  `Δ = cell − complement` with a 95% interval from `week_cluster_bootstrap`
  (`swingbot/core/backtesting/instrument/stats.py:57`), paired by week (never
  cell against a pool that contains it), plus a Benjamini–Hochberg q-value across
  **every** cell tested (`bh_qvalues` in the same module). Stop-related cells
  also print stop distance in ATR and dollar loss at fixed 2% risk. A cell using
  bars prints bar-covered N beside total N.
- **`thin`:** N < 30 **or** fewer than 8 distinct weeks. Never ranked as evidence.
- **Header:** window (first and last exit date), total N, pooled net ExpR and
  win rate, net-of-frictions flag, total cells tested. Roles quote only these and
  per-cell figures.
- **Output:** JSON (read by the merge) plus a Markdown summary (≤ 150 lines, the
  only thing a role reads), committed under `docs/superpowers/results/`.
- Every function under complexity 15 (`docs/claude/code-complexity.md`).

### 2. Three generator role skills

Same file shape as the reviewer roles, except the first heading is
`## Generator lens` (see Codex mirror and docs) — then `## Checklist` (here:
where to look), `## Red flags` (here: what the role must not propose),
`## Out of scope`, `## Row format`, `## Trigger table`. A generator emits **at
most 5 rows**. Each row:

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: <autopsy cut + cell: N, weeks, Δ net ExpR [CI], q>  |  playbook: <entry id>
  exploratory: yes            # always yes for autopsy evidence (boundary 5)
  edge: expectancy | harvest | volume
  mechanism: <why a trader expects it to pay, one or two sentences>
  order_form: <how it becomes resting orders: stop-buy / limit / market-on-open, validity>
  manual_actions: none | <mid-trade action a non-watching trader must take>
  pairs_with: <for any tightening: where the volume or R comes back; else n/a>
  divergence: no | yes        # live diverges from the plan (unfilled, gap, silent change)
  route: /screen <idea>  |  /prereg  |  harvest-headroom <results path>
```

The skills share the reviewer roles' boundary sentences (never decide, never
lower a gate, `pooled-numbers`, `backtest-gate`) so the existing
`test_role_skills.py` boundary pattern applies.

**`exit-harvester`** — money earned and given back, or never taken.
- Look at: give-back across all trades (trail / scale-out headroom,
  cross-checked against `runner_headroom.py`); near-stop reversals beside the
  trades a wider stop would still lose; `check_near_tp_timeout` closes;
  holding time against R per horizon; gap-through-stop losses.
- Must not propose: v129 acceptance-failure exits (arm Z / arm B), v139
  structural stop or stop drop, `DATA_DRIVEN_STOPS_ENABLED`; any stop change —
  tighter **or wider** — without the dollar view at fixed 2% risk (R-unit
  inflation); a trail or breakeven move that needs `manual_actions` with no
  alert message to carry it.

**`setup-scout`** — entries the bot doesn't take, or takes badly.
- Look at: cells whose `Δ` interval excludes zero with q ≤ 0.10, not thin;
  fill-reality cells (entry order form and validity); liquidity buckets (is a
  high cell a few thin names?); rejected-plan reasons that block plans (a volume
  lever, measured in shadow, not assumed); setups in `references/playbook.md`
  absent from `strategy_types.py`; variants of the one `SCREEN-PASS`
  (`screen-uptrend_pullback`) that are a new mechanism, not a new threshold.
- Must not propose: any SCREEN-FAIL idea under a new name (`high52w`,
  `gap_volume`, `turn_of_month`); v122 volume dry-up, v127 structure-break
  armed entries, v128 FVG level modes, v131 Fibonacci limit, v135 headroom veto,
  v143 FVG-bullish features, v36 touch strength, v49 effective confluence,
  v68 dead-cat-bounce veto.

**`regime-desk`** — when to trade or stand aside.
- Look at: `Δ` by index trend, volatility and breadth bucket (`regime2.py`,
  `market_context.py`); weekday, Friday entries and weekend holds; OPEX week;
  macro-event proximity; sector clustering of same-day losers (`correlation.py`).
- Must not propose: the `REGIME_ALLOW` gate (v17 P2a: 0 of 44 cells),
  `EARNINGS_BLACKOUT_SESSIONS` (v82: near-earnings trades scored better), any
  regime variable not point-in-time, a stand-aside filter whose only effect is
  to cut N without naming where volume comes back
  (`feedback-yield-over-pure-integrity`).

### 3. `references/playbook.md` (under the `setup-scout` skill)

Curated trader setups. Each entry: id, textbook rule, horizon, **resting-order
form** (stop-buy or limit, validity), the failure mode a trader watches for, and
the closed or passed ledger rows it must not duplicate. Kept out of `SKILL.md`
so it loads only for `setup-scout`. Seed entries, chosen to avoid closed rows
and the one SCREEN-PASS (the partner may edit):

- gap-and-hold continuation: next-day stop-buy above the gap day's high;
- gap-fill reversal into a prior level: limit at the level, one-session validity;
- tight base breakout: stop-buy above the base on volume confirmation;
- relative-strength leader versus its index on an index pullback day;
- failed-breakdown reclaim of a prior low: stop-buy above the reclaim bar;
- ATR-based re-entry after a stop-out when the setup re-arms within N bars;
- three-bar reversal at a weekly level.

Post-earnings drift is left to a `fundamental-analyst`-reviewed idea (it needs
point-in-time estimates); 52-week-high and 20-EMA-pullback variants are left out
as too close to `screen-high52w` and `screen-uptrend_pullback`.

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
   is older than 7 days or absent, ask the partner before running the export on
   the VM (read-only, but a production command), preferably outside the US
   session and premarket.
2. Dispatch `scout` once per role, serially — never in parallel.
3. Write the role outputs to a scratch file and run
   `python scripts/dev/scout_merge.py <file> --autopsy <json>`.
4. Commit the autopsy and slate on `main`; run `/panel quant-researcher <slate>`
   and append its findings to the slate as `## Panel review`.
5. Present the top rows to the partner with `AskUserQuestion`, one question,
   recommended row first. The partner's pick goes to `/screen` or `/prereg`;
   the scout itself starts neither.

### 6. `scripts/dev/scout_merge.py`

Deterministic. Records every drop with its reason in the slate's `## Dropped`
section. **Drops** a row when:
- its `idea` matches a ledger `id` or hypothesis (case-insensitive, normalised
  kebab-case), or a name in the closed-pre-registrations table parsed from
  `backtest-methodology.md` § Closed pre-registrations — do not re-run these;
- its evidence cell is `thin`, or not present in the autopsy JSON (an invented
  figure), unless `route` is a playbook `/screen`;
- its evidence `Δ` lower bound is at or below zero (no evidence to rank).

**Pins** every `divergence: yes` row to the top (real-money divergence is
`Edge: harvest`, `docs/claude/edge-priorities.md`). **Ranks** the rest by `edge`
(expectancy, then harvest, then volume), then `Δ` lower bound, then N, and
ranks down a row with `manual_actions` other than `none`. Writes
`docs/superpowers/results/<date>-scout-slate.md` with the autopsy header
(window, N, cells tested) copied verbatim and a reminder of boundary 5.

The closed-table parse is pinned by a test that runs it against the **real**
`backtest-methodology.md` and asserts known names (v129, v135, `high52w`,
`REGIME_ALLOW`) come back, so a rewording of that section fails loudly instead
of silently disabling the drops.

## Retention and removal

- Raw export CSVs are scratch only, never committed.
- Committed artefacts per run: one `*-book-autopsy.{json,md}` and one
  `*-scout-slate.md`. Owner: the session that ran the scout. A slate is history
  once its rows are picked or rejected; no pruning beyond normal results-doc
  practice.
- **Removal condition:** if three consecutive slates produce no row that the
  partner sends to `/screen` or `/prereg`, the next session records that in the
  latest slate and asks the partner whether to retire the tooling.

## Token budget

Each role reads its skill (~3.5 KB) plus the autopsy Markdown (≤ 150 lines);
the playbook only for `setup-scout`. At most three Sonnet dispatches per run,
serial; only the merged slate reaches the controller. The export, autopsy and
merge are scripts — the model never crunches the book.

## Codex mirror and docs

- `python scripts/dev/sync_codex.py` for the three role skills, `trade-scout` and
  the `scout` agent; `tests/hooks/test_codex_mirror.py` must pass.
- `docs/claude/skills-tools.md`: a `## Generator roles (v161)` section beside
  Expert roles, and `scout` in § Which agent for what. `AGENTS.md` gets one line
  in its Skills section, staying under the 32 KiB cap.
- The generator roles are **not** registered in `test_role_skills.py`'s `ROLES`
  (that test pins *reviewer* roles via `## Lens`). They use `## Generator lens`
  instead, so `lens_skills()` does not pick them up, and get their own shape test.
- `scripts/dev/select_tests.py` `DATA_READERS`: add `tests/scout/` to the
  `preregistration-ledger.jsonl` row and add a row for
  `docs/claude/backtest-methodology.md` → the merge's closed-table test, so
  `testrun.py changed` selects them.

## Testing (free, local)

New directory `tests/scout/`, added to exactly one suite in `tests/suites.toml`
in the same commit (`docs/claude/testing-cost.md` § Test suites):

- export script: contains `READ ONLY`, no write keyword, fixed column list.
- autopsy, on fixture CSVs: N, weeks, WR, net and gross ExpR; `thin` by N and
  by weeks; `Δ = cell − complement` passed to `week_cluster_bootstrap` with week
  clusters; BH q-values over all cells; give-back over all trades; fill-rate
  and gap-through-stop cuts; bar-covered N; header fields.
- merge: a ledger id, a closed-table name and a renamed SCREEN-FAIL idea each
  dropped with a reason; thin, missing-cell and non-positive-bound drops;
  divergence pinning; manual-action rank-down; ranking order; the closed-table
  parse against the real doc.
- generator role shape: the sections plus Row format, boundary sentences, the
  "at most 5 rows" rule, `exploratory: yes`, and each role's red-flag list
  naming the closed rows above.
- skill and agent: `trade-scout` names serial dispatch and the merge script;
  `scout` lists only read-only tools.

## Out of scope

- Sub-project 2, the **live alert desk** (pre-open annotation of each day's
  alerts reusing the autopsy cuts), gets its own spec.
- Running any slate row through `/screen` or `/prereg`.
- Any change to `swingbot/` runtime code, thresholds or the admin UI.
- A scheduled export cron (can follow once the manual run has proven useful).

## Panel review

Run 2026-10-15 over 0eb1aea3 (quant-researcher on opus, veteran-trader on
sonnet, staff-engineer on opus).

- quant-researcher [BLOCKING]: live-book window overlaps the 2026 holdout; a `/prereg` row would pick its cell after reading data its holdout scores -- applied (boundary 5, `exploratory: yes`, slate reminder).
- quant-researcher: no multiple-comparison count -- applied (cells tested in header, BH q per cell).
- quant-researcher: Row format cannot mark a row exploratory -- applied (`exploratory:` field).
- quant-researcher: interval statistic unspecified; cell vs containing pool is not independent -- applied (`Δ = cell − complement`, paired by week).
- quant-researcher: `thin` ignores week clustering -- applied (fewer than 8 distinct weeks is thin).
- quant-researcher: give-back on winners only and reversal cut select on outcome; red flag guarded only tighter stops -- applied (full-population cuts, tighter or wider).
- quant-researcher: class-first ranking lets a non-positive-bound row outrank -- applied (drop bound ≤ 0 before ranking).
- quant-researcher: ledger tally summed to 61 of 65 -- applied (OPEN and WITHDRAWN listed).
- quant-researcher: bar-reading lookahead in the reversal cut belongs to quant-engineer -- applied (the plan dispatches quant-engineer review of the autopsy task; reversal reads only bars after the exit).
- veteran-trader: no fill-reality cuts -- applied.
- veteran-trader: gap-through-stop named for the role but missing as a cut -- applied.
- veteran-trader: net or gross unspecified -- applied (both printed, flag in header).
- veteran-trader: no order form or manual-action fields -- applied (`order_form`, `manual_actions`, rank-down).
- veteran-trader: no liquidity, volatility, ticker or sector cut -- applied.
- veteran-trader: no alert-volume or timing cut -- applied (alert supply cut).
- veteran-trader: no macro-event or weekend-hold cut -- applied.
- veteran-trader: playbook seeds near closed or passed ideas -- applied (seeds replaced, each with an order form).
- veteran-trader: stop cells need ATR distance and dollar loss at fixed risk -- applied.
- veteran-trader: bar-covered N not printed -- applied.
- veteran-trader: divergence rows get no priority -- applied (`divergence:` field, pinned).
- staff-engineer: log path is the host path inside the container -- applied (logs grepped on the host).
- staff-engineer: stdin run, two outputs and image version skew unspecified -- applied (VM runs only a psql export; all Python is local).
- staff-engineer: bootstraps inside the live container -- applied (computed locally; run outside the session).
- staff-engineer: read-only guarantee covered only the script, not helpers -- applied (`READ ONLY` session, no helpers).
- staff-engineer: closed-ideas parse is a hidden doc coupling -- applied (pinned by a test on the real doc and a `DATA_READERS` row).
- staff-engineer: `DATA_READERS` rows missing -- applied.
- staff-engineer: no owner, retention or removal condition -- applied (§ Retention and removal).
- staff-engineer: `check_near_tp_timeout` cited at a docstring -- applied (definition cited; exit-reason value resolved in the brief).
