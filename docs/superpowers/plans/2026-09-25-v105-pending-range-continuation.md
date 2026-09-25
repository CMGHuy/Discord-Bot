# v105 PENDING daily range continuation — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-09-25-v105-pending-range-continuation-design.md`
**Bump:** none until alert enablement; bot minor only if a direction ships
**Edge:** expectancy

**Progress:** Not started. No code, backtest or production work is implied by
the creation of this plan.

**Goal:** Produce a causally correct, measurable source of pre-break PENDING
range plans; test directional pressure against the unfiltered range source;
keep alerts shadow-only until the frozen evidence and execution-feed gates pass.

**Architecture:** A pure range candidate module owns the geometry and
directional-pressure fields. One builder turns a candidate into `TradePlanV2`.
The scan and replay call those same units. A source-specific identity prevents
repeated alerts from a moving rolling window. Measurement emits keyed,
provenance-stamped paired arms. Notifications reuse the plan manager's state
transitions and existing alert path. v104's stop/sizing model is read at
execution time and frozen identically across both measurement arms.

**Tech stack:** Python 3.11+, pandas/numpy, pytest, existing JSON PlanStore and
Discord presentation. No external TrendSpider integration is assumed.

## Global constraints

- Before implementing, read `docs/claude/architecture.md`, `known-traps.md`,
  `backtest-methodology.md`, `edge-priorities.md`, `code-complexity.md`, and the
  relevant `.claude/skills/no-lookahead`, `edge-module`, `alert-surface` and
  `backtest-gate` checklists. Reinspect the exact code after v104/v100 merges;
  this plan's paths are starting points, not authority over changed code.
- No production deployment, SSH or live configuration change is in scope.
  The source remains masked until Task 11's explicit evidence decision.
- The live universe is the current watchlist. Measurement uses the full
  available cached universe × all ten horizons. Report ticker and sector
  concentration; one sector cluster is not independent replication.
- The decision on session `t` reads completed daily bars only through `t-1`.
  The live quote can determine proximity/crossing, never range geometry.
  Every signal feature needs a full-series-versus-truncated-series test.
- Use a single `range_continuation` source ID. Do not change existing
  confluence or v104 B1/B2 entry logic. Do not reopen v69, v88 or v90.
- Start with the exact spec geometry, pressure predicate and TRAIN axes.
  Do not add a rescue filter or expand a grid after a failed gate.
- Keep pressure-off/on entry, stop, target and exits identical for any
  shared candidate. Use current structural target selection and current
  stop ceiling/sizing in both arms; no fabricated TP or silent risk-cap move.
- A PENDING paper event must never imply that the bot has placed or cancelled
  a real broker order. Explicitly surface fill, expiry, invalidation and
  risk-cap divergence to a user with an overnight order.
- Changed functions have cyclomatic complexity below 15; inspect with
  `python -m radon cc -s -n C <changed files>`. Iterate with one narrow test
  file per task. `0 failed` and `0 xfailed` is green. Run the full suite once
  as the final verification task, not after each task.
- Commit each finished implementation task separately. Stage explicit paths;
  check origin and shared-tree status before commits. Version bump is a
  separate final release commit only if alert behaviour actually ships.

## Acceptance and measurement contract

1. Stage −1 proves that candidate generation is reachable, live/replay plans
   are field-identical at the same as-of time, and filled counts make the
   predeclared effect detectable. Failure ends measurement with no holdout
   shot. The range source may remain shadow-only.
2. TRAIN chooses one `{N,d}` cell on a predeclared plateau, using paired
   pressure-off/on outcomes. The source's own baseline profitability and badge
   are reported separately from the pressure feature's incremental effect.
3. Stage 2 requires the repository's fold consistency rule. Stage 3 is one
   prospective, untouched holdout shot after sufficient follow-up. The
   already-used 2024–25 window and v104's 2026 holdout cannot be recycled as
   this feature's selection or validation window.
4. Score LONG and SHORT separately. For pressure as a feature, use all six
   applicable v72 acceptance clauses (the removed-population clause applies).
   `ExpR` ranks work; the feature gate's win-rate objective and expectancy
   non-inferiority constraint remain authoritative. A strategy source/badge
   must independently clear its own absolute gate before live enablement.
5. Daily OHLC reports the trigger-then-close-back-inside diagnostic. It does
   not count entry-day stops unless timestamped intraday events resolve order.
   Report lead time, late alerts, gaps, cancellations and delivery from the
   prospective shadow feed, with data-age stamps and missing-event counts.

## Review focus

- An order can fill at the broker overnight before the bot's next poll; a
  later paper `cancelled_risk_cap` must be sent as a divergence notice, not
  represented as proof the broker order was cancelled.
- `exit_sim.py` currently begins exit evaluation after the entry bar. A
  replay result must not describe this as an entry-day stop test.
- `build_confluence_plan` currently uses the scenario/current entry as its
  stop-entry trigger. The new range builder sets an independently frozen
  boundary trigger and leaves old plans byte-for-byte unaffected.
- The historical 1-minute/5-minute Yahoo windows are short. A long
  backtest cannot recover minute-level alert lead from daily candles.
- If v104 changes the stop ceiling or risk sizing before this plan runs,
  reproduce and freeze one baseline under the new model, rather than
  comparing numbers from different models.

## Parallelisation

Tasks 1–4 form a chain because the builder consumes the candidate and the
replay consumes both. Task 5 needs the source identity from Task 2. Tasks 6
and 7 can start after Tasks 4–5, because measurement and shadow telemetry
read the same candidate contract but write distinct files. Task 8 follows
Task 6; Task 9 follows Tasks 7–8; Task 10 follows the powered prospective
sample; Task 11 follows all evidence and release review; Task 12 is final.
No parallel subagent execution is required by this plan.

# Phase 1 — Candidate and PENDING lifecycle

### Task 1: Reconcile dependencies and freeze the as-of contract

- [ ] Inspect current v100/v104 landed code and active worktree state. Record
  source IDs, target selector, stop ceiling, sizing guard, scan insertion
  point, PlanStore identity fields, acceptance instrument and cache path in a
  brief result note under `docs/superpowers/results/`.
- [ ] In that note, freeze the exact TRAIN window, full cache manifest/hash,
  universe, ten horizons, spec constants, code commit, expected number of
  independent sector clusters and new holdout eligibility rule before any
  outcome run. If v100's producer is absent, name the bespoke instrument and
  prove it reaches the same live source.
- [ ] Check `git worktree list` and never edit another session's checkout.
  Confirm that the v104 baseline is fixed for both arms. Commit the note.

**Verification:** Review the note against spec §§ Boundary/Evidence and
`docs/claude/backtest-methodology.md`; no performance score is generated here.

### Task 2: Implement pure range candidate and causal pressure

- [ ] Add a small module under `swingbot/core/market/` for completed-bar
  range geometry, pre-range trend, confirmed pivot and pressure predicate.
  Return a typed immutable candidate with range start/end, boundary, ATR,
  trigger-side touch dates and as-of timestamp. Keep candidate creation
  separate from plan construction.
- [ ] Add `tests/market/test_pending_range_candidate.py`: LONG and SHORT
  mirror cases, missing warm-up, two separated touches, width edges, trend
  fixed before the range, current partial candle excluded, confirmed pivot,
  and full-versus-truncated equality at each sampled bar.
- [ ] Add a test where appending a dramatic future breakout leaves the
  earlier candidate and pressure value unchanged. Keep any v104 entry module
  untouched.

**Verification:** `python scripts/dev/testrun.py file tests/market/test_pending_range_candidate.py`
and radon on the changed source/test file.

### Task 3: Build one range plan with real target and risk guard

- [ ] Add a focused builder under `swingbot/core/planning/` accepting only
  the Task 2 candidate and already-known structural candidates. Set
  `entry_type=stop_entry`, frozen boundary `trigger_price`, structural stop,
  real TP1, five-session expiry, source ID and candidate identity. Round the
  trigger outward to the tradable tick.
- [ ] Apply the current v104 risk ceiling and fixed-dollar sizing guard
  where present. Return no plan on missing pivot/target, outside 1.5R–2.5R,
  nonfinite arithmetic or unsafe risk. The builder must not mutate the
  shared dataframe or an old confluence plan.
- [ ] Add `tests/planning/test_pending_range_builder.py` covering both
  directions, stop/target ordering, gap risk, target refusal and exact
  old-confluence behaviour as a regression.

**Verification:** `python scripts/dev/testrun.py file tests/planning/test_pending_range_builder.py`
and radon on changed functions.

### Task 4: Replay trigger, gap and expiry through the shared source

- [ ] Connect the Task 2/3 functions to a source-specific replay under
  `swingbot/core/backtesting/`. Evaluate five eligible sessions, worse-of
  trigger/open stop-market fills, invalidation, and one-plan-per-range
  identity. Keep the existing next-bar exit limitation explicit in output.
- [ ] Add `tests/backtesting/test_pending_range_replay.py` with intrabar
  trigger but close inside, gap through trigger, no fill, fifth-day fill,
  sixth-day refusal, and overlap suppression. Compare live-builder and
  replay-builder plan fields on the same truncated frame.
- [ ] Count trigger-then-close-back-inside separately from win/loss. If both
  stop and target are inside the entry bar, report unresolved ordering
  instead of guessing an outcome.

**Verification:** `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_replay.py`
and the no-lookahead truncation cases.

### Task 5: Wire a masked watchlist source and reliable PENDING notices

- [ ] Add the source to the current watchlist scan through a default-off
  mask/shadow mode. Use only a fresh quote for proximity. Insert after
  open-position monitoring and ticker data/liquidity screens, preserving
  scan-loop ordering. Deduplicate by candidate identity, ticker and source.
- [ ] Route PENDING creation, fill, expiry, invalidation and risk-cap
  divergence through the existing plan manager/alert channel; include
  trigger, stop, target, expiry session, timestamp and explicit broker-order
  action. Show one sector primary with alternatives only after calibrated
  ranking exists; otherwise use an unranked deterministic list.
- [ ] Add `tests/scanning/test_pending_range_alerts.py` for pre-break
  notice, already-crossed refusal, stale quote refusal, fifth-session
  expiry notice, new-range rearm only, same-sector grouping and failed send
  retry. Add a lifecycle regression test for a gap fill followed by paper
  risk-cap cancellation, marking broker status unknown.

**Verification:** `python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py`,
then focused existing `tests/scanning/test_execution_feed_routing.py`.

# Phase 2 — Measurement and forward evidence

### Task 6: Produce paired, stamped measurement arms

- [ ] Extend v100 `ArmEngine` if landed; otherwise add a bespoke source
  adapter under `swingbot/core/backtesting/` and record the explicit reason.
  Emit paired keys, source code hash, cache manifest, universe, horizons,
  window, exit model and pressure-off/on flag. Do not score a stale or
  unobservable arm.
- [ ] Add `tests/backtesting/test_pending_range_arms.py` proving pressure
  changes only candidate acceptance, not shared-trade plan arithmetic;
  separate LONG/SHORT; full-universe enumeration; and refusals for missing
  provenance or future-dated selection bars.
- [ ] Add a small `scripts/backtest/measure_pending_range.py` command with
  a bounded pilot and flushed per-unit progress. The pilot estimates
  reachability and MDE, but must not inspect the future holdout.

**Verification:** `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_arms.py`
and a help/dry-run smoke check of the measurement command.

### Task 7: Capture prospective alert lead and broker divergence

- [ ] Add append-only timestamped shadow events for candidate ready,
  PENDING notice attempted/delivered, trigger observed, gap/open, expiry,
  invalidation, and plan-state changes. Include market-data age and polling
  interval. Use the repository's atomic persistence conventions for any new
  JSON state; log append failures visibly.
- [ ] Add `tests/backtesting/test_pending_range_shadow.py` for clock order,
  duplicate suppression, missing/late notice, stale quote, and overnight
  trigger before the paper poll. A cancellation record never asserts broker
  cancellation without broker evidence.
- [ ] Add a read-only report of lead-time distribution, late-alert rate,
  fill gaps, same-day close-back rate, unresolved entry-day sequencing and
  delivery parity. Keep the report off the trade alert channel.

**Verification:** `python scripts/dev/testrun.py file tests/backtesting/test_pending_range_shadow.py`
and inspect one synthetic rendered report.

### Task 8: Run free TRAIN stages and record the finding

- [ ] Read `.claude/skills/backtest-gate/SKILL.md` immediately before
  running. First run the bounded pilot and Stage 0 MDE. Stop if reachability,
  sample width or effect size is inadequate; do not loosen geometry or widen
  the grid afterward. Log percent-complete for runs longer than 15 minutes.
- [ ] If eligible, run the frozen `{N,d}` TRAIN cells and plateau test, then
  fold consistency. Include both direction-specific results, sector-cluster
  counts, ΔExpR, ΔWR, planned RR, win R, accepted-alert change and removed
  population. Label same-day close-back as a diagnostic. No holdout call.
- [ ] Write `docs/superpowers/results/<date>-v105-train.md` with exact code
  hash, cache provenance, selected cell or no-eligible-cell, and whether the
  one-shot budget remains unused. Commit result and code separately as
  appropriate. Do not quote a stale pooled figure from another document.

**Verification:** Recompute reported aggregates from emitted keyed rows;
run the relevant `validate_component.py --stage mde|walkforward` gate and
inspect its complete verdict. This is a measurement task, not a test rerun.

### Task 9: Freeze the prospective holdout before it can be scored

- [ ] Only if Task 8 clears its free stages, write a pre-registration result
  recording the future holdout start/end, minimum effective sample/MDE,
  chosen `N,d`, direction-specific shot count, code/cache hashes and
  decision rule. The first eligible complete session is after this
  pre-registration's commit. Never use v104's sealed 2026 holdout as this shot.
- [ ] Prove the scorer refuses an unfinished/thin holdout and refuses a
  second shot after one is spent. Add narrow tests under
  `tests/backtesting/test_pending_range_arms.py`.
- [ ] Review Task 7's forward timestamps for lead-time data completeness.
  Missing execution evidence leaves alerts masked even if TRAIN looks good.

**Verification:** Narrow holdout-refusal tests; inspect the frozen
pre-registration diff before committing it. No validation outcomes are read.

### Task 10: Score one powered holdout shot and execution feed

- [ ] When the pre-registered future window ends and has sufficient power,
  run the one-shot holdout once. A thin sample records only the allowed
  sealed-thin status and waits for the predeclared maturity condition.
- [ ] Report all applicable six v72 clauses, direction-specific strategy
  badge gates, same-sector concentration, trigger-close-back diagnostic and
  prospective notice lead/cancellation parity. Do not tune a failed result.
- [ ] Commit the result under `docs/superpowers/results/`. A failure ends
  this implementation as no-lift or shadow-only; a pass makes Task 11
  eligible, not automatic.

**Verification:** Independently re-derive aggregates from the sealed rows
and inspect the acceptance script's complete verdict once.

# Phase 3 — Release and verification

### Task 11: Decide direction-specific alert enablement

- [ ] For each direction independently, require the frozen evidence gate,
  source badge, timely PENDING delivery and action-safe cancellation parity.
  If any fails, keep that direction masked; record the reason. If a
  direction passes, enable only that direction on the watchlist with the
  existing paper-plan path and clear human broker-order instructions.
- [ ] Check v104 B1/B2 overlap and sector grouping; no duplicated alert for
  the same range/ticker. Update user-facing strategy/alert documentation and
  `.env.example` if a default changes. Do not touch production.
- [ ] Add a narrow integration test of full scan → PENDING notice → fill or
  expiry → linked paper trade. Verify exact notification routing and no
  silent cancellation.

**Verification:** `python scripts/dev/testrun.py file tests/scanning/test_pending_range_alerts.py`
and focused plan-manager tests. If no direction passes, record no-lift and
skip the bot version bump.

### Task 12: Run the one final suite and close out

- [ ] Run `python scripts/dev/testrun.py full` once and read the one-line
  verdict; require `0 failed`, `0 xfailed`. Run `python -m radon cc -s -n C`
  on all changed functions and a compile check. Do not repeat a clean full
  suite after a clean merge.
- [ ] Follow `docs/claude/document-lifecycle.md` to move the spec/plan to
  `implemented/` only if complete, or `no-lift/` if the measured work cannot
  ship. Write the final evidence summary and actual limitations.
- [ ] If live alert behaviour shipped, make the bot version bump its own
  release commit, regenerate `swingbot/admin/version_history.json` in a
  second commit and run its narrow version-matrix test. If shadow-only,
  no release bump.

**Verification:** Preserve the exact final suite result, radon result,
release commits if any, and direction-specific gate decisions in close-out.
