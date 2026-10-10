# v156 — Review ritual skills: one trade, one market day, live-versus-replay drift and the quarterly revalidation

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling only; no shipped code)
**Edge:** none (integrity) — descriptive review only. Nothing here selects a parameter, moves a badge or registers a hypothesis; a pattern it surfaces becomes a separate pre-registration or nothing.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, veteran-trader
**Status:** spec written 2026-10-10; panel review pending; no plan yet.
**Depends on:** v154 (frontmatter helper, `doc_section.py`). Reads modules that already exist; builds none.

## Why

The analytics exist — `swingbot/core/analytics/` has `mfe_mae.py`,
`exit_quality.py`, `calibration.py`, `market_day.py`, `cohort.py` and
`journal.py`, and `scripts/reports/` has the parity and market-day reports —
but each review is assembled by hand in the main context, with raw output
landing there. Four reviews recur:

1. **Why did this one trade lose?** Answered today by reading the journal row,
   the chart and the bars separately.
2. **What did today's market do to the book?** `market_day_report.py` (v141)
   answers it and is explicit that it is descriptive only.
3. **Is live drifting from replay?** `parity_exits.py`, `parity_sizing.py` and
   `shadow_parity_report.py` each answer a part.
4. **Has an adopted component decayed?** `quarterly_revalidation.py` is a
   deliberately human-run ritual for the first weekend of each quarter;
   `swingbot/core/edge/strategy_soak.py` holds the pre-registered v93 trust rule.

The first brainstorm listed twelve skills here. Dropped after reading the
code: expectancy attribution and gate ablation (v146 and v147 already spec
them), regime split and correlation clusters (covered by `risk-manager` and
existing reports), a catalyst calendar (the `fundamental-analyst` role plus
`measure_earnings_blackout.py`), options context (`record_option_snapshots.py`
is still accumulating an archive that cannot yet be backtested), and event
studies, seasonality and breadth (each is a new hypothesis, so it starts at
Stage −2, not at a skill).

## Decisions taken in the brainstorm

- **All four are slash-only and forked** (`context: fork`), so their raw
  output never reaches the main context and they add nothing to the listing.
- **Descriptive, never selecting.** Every skill ends with the same fixed line:
  "Descriptive only. A pattern seen here is a hypothesis for `/screen` or
  `/prereg` (v155), not a result." A single trade, a single day and a 4 × 3 × 2
  grid of buckets are each too small or too many to conclude from.
- **Production reads go through the existing read-only pattern**
  (`scripts/ops/ssh-hetzner.sh` piping a stdlib script, as
  `market_day_live_dump.py` does). No skill writes to production, so
  `mirror-prod` does not apply.
- **Figures follow `pooled-numbers`.** A skill prints what a script computed,
  names the script and the window, and never restates a pooled figure from a
  document.

## Design

### 1. `/trade-autopsy <journal id | SYMBOL YYYY-MM-DD>` (fork, sonnet)

Reads one closed trade's journal row and its bars, and reports in a fixed
shape of at most fifteen lines:

- the plan as alerted (entry, stop, targets, horizon, strategy, confidence);
- what the entry bar knew — the inputs available at that bar only, per
  `architecture.md` § NO-LOOKAHEAD — and nothing later;
- MFE and MAE in R from `analytics/mfe_mae.py`, and the bar on which each
  occurred;
- how it exited, and how far price travelled past the stop afterwards;
- whether an earnings date fell inside the holding window.

It does not say the stop was "too tight" or the setup "bad". Judging that
from one trade is the error the skill exists to prevent; it reports the
measurements and the fixed closing line.

How the journal row is fetched (local Postgres copy or a production read) is
settled by the plan's brief from `analytics/journal.py`; if only production
holds it, the read is dispatched through `prod-inspector`.

### 2. `/market-day-review [YYYY-MM-DD]` (fork, sonnet)

Runs `market_day_live_dump.py` over the ssh wrapper, feeds
`market_day_report.py`, and returns the report's own table plus two lines:
alerts raised, and positions opened and closed that day. The report's
"descriptive only" header is kept verbatim at the top.

### 3. `/live-drift` (fork, sonnet)

Runs `shadow_parity_report.py`, `parity_exits.py` and `parity_sizing.py` and
returns one line per report: clean, or the count and the first three
mismatches. `invariant_violations` from the shadow report is printed as a
number, because a non-zero value is the one figure here that an existing gate
reads. Each of the two parity scripts is a long TRAIN-window run, so the skill
dispatches them through `backtest-runner` rather than running them inline.

### 4. `/revalidate` (slash-only, main context for the judgement, runs dispatched)

The quarterly ritual around `quarterly_revalidation.py`:

1. Read the methodology's acceptance-gate section and the v93 trust rule's
   docstring in `strategy_soak.py`.
2. `/data-check` (v155) first; stop on a dirty cache.
3. Dispatch `backtest-runner` for the script; relay verdict lines only.
4. List each component that degraded against its recorded baseline, with the
   results doc that holds that baseline.
5. Pruning is the partner's decision: ask through `AskUserQuestion`, one
   component per question. The skill disables nothing itself.

### Codex mirror

`sync_codex.py` mirrors the four; `AGENTS.md` gains their names in the same
commits. Codex runs them unforked (`sync_codex.py` drops `context`/`model`),
as stated in v154.

## Edge cases

- An open trade passed to `/trade-autopsy`: refused — MFE/MAE are not final.
- A day with no alerts: `/market-day-review` says so in one line.
- `data/shadow_plans.jsonl` absent: `/live-drift` reports that report as
  unavailable and still runs the other two.
- Production unreachable: the skill reports the wrapper's error and stops; it
  never falls back to a stale local copy without saying so.

## Testing

- `tests/hooks/test_skill_shape.py`: the four names join `TIER_2` and the
  slash-only set; a new assertion pins the fixed closing line in the three
  descriptive skills.
- `tests/hooks/test_codex_mirror.py` green after `sync_codex.py`.
- Manual, recorded in the plan's results: each skill run once against real
  data, output pasted into the results doc.
- No eval suites: slash-only skills have no trigger to prove.

## Parallelisation

- The four skills are independent in content. They share `TIER_2` in
  `test_skill_shape.py` and `sync_codex.py` output, so they commit one at a
  time; there is no other ordering between them.
- `/revalidate` names `/data-check`, so v155 lands first.

## Out of scope

- Any new analytics module, report or chart; any change to an existing one.
- Any automatic action on a finding: disabling a strategy, moving a badge,
  changing a stop.
- Scheduling these as crons or routines.
