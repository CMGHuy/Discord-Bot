# v118 result — SHORT candidate universe: stopped at reachability (blocked, no measurement)

Plan: `docs/superpowers/plans/implemented/2026-10-01-v118-short-universe-swing.md`.
Pre-registration: `docs/superpowers/results/2026-10-01-v118-short-universe-preregistration.md`.
Edge: volume.

**Outcome: no evidence was produced and none is claimed.** The measured stages
(reachability -> MDE -> TRAIN plateau -> folds -> VALIDATION) were never run, so no
expectancy, win rate or N exists for this lane and no validation shot was spent.

## Why it stopped

Historical replay needs a point-in-time sector history for the S&P members
(`data/universe/sp500_sector_history.csv`); none exists. Without it every decision
date records `no_snapshot`, the extra lane adds no rows, and `measure_arms.py`
refuses with `refused:zero-diff`. Projecting today's `sp500.json` sectors backward
is forbidden by the spec. On 2026-10-02 the human partner chose to stop at
reachability rather than accept a biased proxy or buy a data source.

## What shipped (inert, default off)

- Candidate lane: PIT membership/sector snapshot (`universe.short_snapshot`), aligned
  completed-bar reference and broad/isolated weakness modes, bounded extra fetch
  after the base send, bearish-only scan, direction/source/mode funnel, existing-trade
  routing, and a borrow-check/decision-date notice in Discord, simple, email and push.
- Measurement instrument: pure `qualify_short_item`, `scan_replay`, population engine
  `short_universe`, research knob `SHORT_UNIVERSE_RESEARCH_MODE` classified
  `REACHABLE` on fixtures.
- Runtime guard: `admitted_short_modes(cfg)`; `SHORT_UNIVERSE_ENABLED`,
  `SHORT_UNIVERSE_BROAD_ENABLED` and `SHORT_UNIVERSE_ISOLATED_ENABLED` all default
  false, so no live SHORT alert can be emitted. No bot version bump (nothing
  observable shipped).

## To resume

1. Obtain a true point-in-time sector-history source and file (not today's sectors).
2. Resolve the seven UNFROZEN items in the pre-registration by committed amendment,
   plus the review-noted gaps: the replay omits the live reversal path and kill
   switch; at pilot the base is 10 tickers while the extra population is the whole
   cached universe; fee days are counted from the decision date, not the fill.
3. Run the measured stages serially, per `docs/claude/backtest-methodology.md`.

This is not a closed negative result: nothing was measured, so the
closed-pre-registration table gets no row.
