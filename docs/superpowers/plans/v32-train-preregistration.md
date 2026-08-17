# v32 TRAIN measurement and VALIDATION pre-registration

Task 9 of `docs/superpowers/plans/2026-08-16-v32-unified-confidence-score.md`.
Written before Task 10's VALIDATION run and not revised after seeing its
result.

## TRAIN measurement (Task 8)

`data/v32_train_lift.json`, 4337 TRAIN trades (2020-01-01..2023-12-31, 75
tickers x 10 horizons x 11 strategies), via
`scripts/backtest/measure_factor_lift.py --train`.

**Result: no factor kept a real, positively-signed weight.**

| Factor | Disposition |
|---|---|
| Target distance quality, Stop level confluence, Target confluence quality, HTF bias, ADX, MACD, Squeeze, Candlestick, MTF alignment, Volume ratio, ATR percentile, Trigger distance, Badge status, Tight-stop penalty | Measured, Wilson-overlapping (indistinguishable from zero lift) -- **dropped** |
| RSI trend alignment | Measured, real non-overlapping lift, but **negative** (-0.056): higher "RSI confirms direction" points correlate with a LOWER win rate -- the opposite of its designed premise -- **dropped** |
| Market regime alignment | Never measured (this harness runs offline, no historical SPY regime feed reconstructed -- same limitation as `scripts/reports/audit_quality_score.py`) -- **dropped**, no evidence either way |
| Relative strength, Market breadth | Never measured (need a historical per-date cross-sectional universe reconstruction this repo's cache doesn't retain) -- **dropped**, no evidence either way, real candidates for a future spec once measurable |
| Gap penalty | Never fires in this harness or in live production (`gap_fragile` is never wired by any caller) -- **kept**, inert either way, per Task 4's explicit instruction to port it pending future wiring |

`swingbot.core.scanning.factors.FACTORS` now contains exactly `[factor_gap]`.
Every other ported factor function stays defined and tested -- correct,
validated implementations that didn't earn inclusion on this evidence, not
broken code.

This is a genuinely significant, three-times-confirmed result (flagged to
the user across three separate decision points given how much it changes):
the quality-points pool ships effectively empty. `UNIFIED_CONFIDENCE`'s
level is now driven almost entirely by method count (via `honesty_cap`),
functionally close to what the pre-v32 legacy system's Step 1 already was.

## A structural fix this measurement forced (Task 9, beyond re-weighting)

`level_for_score()` (Task 5) originally derived level PURELY from the 0-100
score via a `LEVELS` band lookup, using `honesty_cap(target_count)` only as
an upper ceiling on that result. With the quality-points pool empty, every
score is pinned at 0, which would have made `level_for_score` return Level 1
for every scenario regardless of method count -- silently gating every
`UNIFIED_CONFIDENCE` alert below any sane `MIN_ALERT_CONFIDENCE_LEVEL`, and
making Task 10's VALIDATION run fail by construction (100% alert-volume
loss) rather than test anything real.

Fixed (confirmed with the user before implementing): `level_for_score` now
sets `target_count`'s `honesty_cap` as the BASE level, with the 0-100
quality score only able to nudge it -1 (weak quality, score<=30) or +1
(strong quality, score>=70 -- a structural no-op today, since base already
equals the cap and the upper clamp absorbs it). This matches the Global
Constraints' stated intent ("base level from method count... remains the
base, and the honesty cap remains on top of it") more faithfully than the
literal Task 5 code did. Full reasoning in `confidence.py`'s
`level_for_score` docstring and the Task 9 commit.

**Consequence for Task 9 Step 3 ("recalibrate the level bands so
MIN_ALERT_CONFIDENCE_LEVEL=4 admits ~today's population"):** this
instruction is now moot as literally written -- `LEVELS`' band edges no
longer drive level determination at all under the fixed mechanic (only
`_LEVEL_LABELS` still reads them). The only real lever left is
`_HONESTY_CAP`'s target_count-to-level mapping, and there is no TRAIN
evidence to justify changing it: `factor_target_confluence_quality` (built
directly from `target_count`) itself showed only 0.026 lift, statistically
insignificant. `_HONESTY_CAP` stays exactly as Task 5 set it
(`{0:1, 1:3, 2:4, 3:5}`, fallback 6) -- an unjustified recalibration would
be the same kind of ungrounded token-points move this whole measurement
exists to prevent. Recorded here as a genuine "doesn't apply as written"
finding rather than silently skipped.

## Level 6 decision (Task 9, Step 4)

Re-measured with the corrected `level_for_score` and the trimmed `FACTORS`
(both change which level every trade lands in vs. the first TRAIN run) --
same 4337 TRAIN trades, `data/v32_train_lift.json`:

| Level | n | Win rate | Wilson interval |
|---|---|---|---|
| 1 | 521 | 38.4% | [34.3%, 42.6%] |
| 2 | 166 | 30.1% | [23.7%, 37.5%] |
| 3 | 116 | 45.7% | [36.9%, 54.7%] |
| 4 | 144 | 42.4% | [34.6%, 50.5%] |
| 5 | 2211 | 49.4% | [47.4%, 51.5%] |
| 6 | **0** | -- | -- |

**Level 6 does not clear the bar -- decisively, not marginally.** n=0: with
the quality-points pool empty, the +1 nudge that could reach
`honesty_cap(4+)=6` never fires (score is always 0, never >=70), so Level 6
became structurally unreachable the moment Task 9's factor-dropping
decision landed. **Removed** per the plan's own instruction: `LEVELS`
restored to its exact pre-v32 5-band edges, `_HONESTY_CAP`'s fallback set
to 5, config `options` already `["1".."5"]` (Task 6 never added "6" --
that was reserved for Task 10 on a PASS, so there is nothing to revert
there).

## VALIDATION pre-registration

- **Primary:** win rate (TP1 before stop) at `MIN_ALERT_CONFIDENCE_LEVEL=4`.
- **PASS:** win rate improves vs. the legacy scorer on the same VALIDATION
  window, AND alert volume falls by no more than 30%.
- **FAIL:** any regression in win rate, or volume loss > 30%.
- **Level 6** ships only if TRAIN showed n>=100, point estimate >=90%,
  Wilson lower bound >=80% and above Level 5's own point estimate. Already
  decided by the TRAIN result above (n=0) -- Level 6 does not exist to ship
  regardless of Task 10's outcome; this line stays as the rule that was
  applied, not a live gate Task 10 still needs to check.
- **One shot.** A FAIL means `UNIFIED_CONFIDENCE` stays default-off.

Given the near-empty factor pool, a reasonable expectation going in: the
unified score is now close to a relabeling of method-count-driven gating,
so VALIDATION is largely a test of whether `honesty_cap`'s specific
target_count-to-level mapping (unchanged from Task 5/pre-v32 in spirit,
just applied more directly) performs comparably to the legacy scorer's
base-level-plus-nudges formula on real, unseen data -- not a test of
RS/MTF/breadth's promised gating influence, since none of the three
survived TRAIN with assignable weight.

## VALIDATION result (Task 10)

**A plan gap found before running:** the plan's literal Step 2 command
(`scripts/backtest/run_backtest_range.py --validation`) measures raw
per-(strategy,horizon) win rates via `run_backtest()`, entirely independent
of `score_confidence()`/`MIN_ALERT_CONFIDENCE_LEVEL` gating -- it cannot
test what this pre-registration's gate actually describes (a comparison of
two GATED alert populations). Built the real comparison instead:
`scripts/backtest/v32_validation.py` scores every VALIDATION-window
(2024-01-01..2025-12-31) trade with BOTH the legacy and the unified
`score_confidence()` path (toggling `config.UNIFIED_CONFIDENCE` around each
call, same scenario/context both times), gates each at
`MIN_ALERT_CONFIDENCE_LEVEL`, and compares the two gated populations'
win rate and volume. Smoke-tested on 2 tickers before the full run; the
user explicitly confirmed running the one-shot VALIDATION now, given TRAIN's
findings, before this was dispatched.

**Run once, 2806 VALIDATION trades, `data/v32_validation.json`:**

| | Legacy | Unified |
|---|---|---|
| Alerts (>= Level 4) | 2077 | 2172 |
| Evaluated (win/loss) | 1487 | 1562 |
| Win rate | 50.50% | 49.68% |

- Volume delta: **+4.6%** (well inside the +/-30% budget -- volume actually
  rose slightly, not fell).
- Win-rate delta: **-0.82 percentage points** (a regression).

**VERDICT: FAIL.** Per the pre-registered gate, "any regression in win
rate" fails regardless of volume. Small in magnitude, but a regression is a
regression -- not re-run, per the plan's own rule.

**`UNIFIED_CONFIDENCE` stays default-off.** No config change. This is a
measured, complete negative result for the spec's central hypothesis: after
TRAIN emptied the quality-points pool (no factor -- including RS, MTF,
market breadth, the three factors this spec exists to gate on -- kept
assignable positive weight) and Task 9's `level_for_score` fix restored
method-count as the level's driver, VALIDATION shows that restructured
method-count-only gating performs slightly WORSE than the legacy scorer's
existing base-level-plus-nudges formula, not better. The spec's premise
("RS, MTF and breadth become able to change an alert's fate for the first
time") does not ship in this version. Task 11 onward (tier retirement,
documentation) proceeds regardless, per the plan's own framing -- those are
independent cleanups, not conditioned on this VALIDATION passing.

## Task 12: decile audit / E43 ablation harness -- no re-pointing needed

Task 12 assumed both `scripts/reports/audit_quality_score.py` (the decile
audit) and `scripts/backtest/ablation.py` (the E43 harness) measure against
the A/B/C tier structure Task 11 removed, and need re-pointing at confidence
levels / `FACTORS`. **Neither premise holds, verified by reading both
scripts in full and running them:**

- **The decile audit never bucketed by tier.** It buckets TRAIN trades by
  `quality.score_plan()`'s raw 0-100 SCORE into deciles, plus a separate
  per-component logistic-regression significance test over `quality.py`'s
  seven base components (regime/htf/confluence/volume/atr_percentile/
  trigger_distance/badge) -- an entirely different axis from the A/B/C label
  `_tier(score)` derived from that same score. Task 11 deleted `_tier()` and
  the `tier` field; it did not touch `score_plan()`'s components or scoring
  at all, since those never depended on the label. Ran it unchanged: exit 0,
  produces both tables (a real, pre-existing, non-v32 finding surfaced along
  the way -- `badge` shows as a significant NEGATIVE coefficient, z=-2.51;
  not investigated further here, out of this task's scope).
- **The E43 ablation harness measures something structurally unrelated.**
  `ablation.py` does leave-one-out ablation over `adopted_components.json`
  -- backtest ACCEPTANCE-GATE config flags (`REGIME_GATES_ENABLED`,
  `AVWAP_LEVELS_ENABLED`, etc., per `docs/superpowers/plans/implemented/
  2026-07-11-v4-edge-engine.md`'s own Task E43 record) -- never `quality.py`
  or `confidence.py`'s scoring components. The design spec's claim ("the
  E43 ablation harness judges them individually") conflates this script
  with the decile audit's logistic-regression half, which is the one that
  actually judges components individually. `adopted_components.json` is
  still `{}` (empty; E33's fold sweep adopted nothing, unrelated to v32),
  so ablation over it is inherently a no-op -- matching this harness's own
  original E43 implementation note ("Not invoked against a live fold sweep
  -- with the adopted set empty, `run_folds({})` would cost ~76 min of real
  compute to confirm a mathematically guaranteed +0.0000R with zero
  ablation rows; documented rather than burned"). Ran it anyway to confirm:
  it crashes on a pre-existing, unrelated Windows-console Unicode bug (the
  "Δ" character in its print statement isn't encodable under cp1252) before
  reaching any ablation logic -- present regardless of any v32 change, not
  introduced by this plan, and out of scope to fix here.

**Task 9's `measure_factor_lift.py` (Task 8) already provides the TRAIN-based
evidence for the v32 merged score** that the design spec imagined this task's
"re-pointed ablation harness" would produce -- a purpose-built script, not a
repurposing of a harness built for a different axis. No code changes made to
either script; this reconciliation is Task 12's deliverable.
