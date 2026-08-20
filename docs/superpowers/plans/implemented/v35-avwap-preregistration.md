# v35 VALIDATION pre-registration — `AVWAP_LEVELS_ENABLED`

**Written:** 2026-08-20, **before** any win-rate number for either arm existed.
**Component:** `AVWAP_LEVELS_ENABLED` (anchored-VWAP levels as a 12th
price-producing strategy family in `levels.collect_candidate_levels`).
**Plan:** `docs/superpowers/plans/implemented/2026-08-16-v35-anchored-vwap.md`, Task 4.

---

## 1. The precondition the flag's help text names — it already ran, and it FAILED

The flag's help text says AVWAP "ships off until the E33 walk-forward folds and
the E40 shadow forward-gate have actually judged it". That is **stale, not
pending**. E33 judged it on 2026-07-26 and the verdict was FAIL.

Commit `c322e70`, record `docs/superpowers/results/2026-07-26-edge-folds.md`:

| fold | N | baseline expR | component expR | delta |
|---|---:|---:|---:|---:|
| 2021 | 1617 | 0.2125 | 0.2124 | -0.0001 |
| 2022 | 838 | 0.0346 | 0.0345 | -0.0001 |
| 2023 | 1076 | 0.1893 | 0.1893 | -0.0001 |

Pooled delta expectancy_r **-0.0001**, improving **0 of 3** folds against a gate
requiring >= 2. That doc's own words: "Both tested components fail decisively,
not marginally... these aren't components that almost passed." AVWAP was
dropped, `adopted_components.json` was written `{}`, and the default stayed off.

E40 exists as a mechanism (`7f3071b`,
`scripts/reports/shadow_component_report.py`) but never produced an AVWAP
verdict.

## 2. Why this is a new shot and not a re-read of a closed table

`docs/claude/backtest-methodology.md`: "A negative result closes a component; it
does not re-open it... Reopening one needs a **new** pre-registered hypothesis
and its own shot, never a re-read of the old table."

**The component materially changed between E33 and now.** E30's close-out note
flagged the exact weakness that plausibly produced E33's -0.0001R:

> "all 5 anchors land within ~30 bars of each other (`pivots_lo[-2:]`/
> `pivots_hi[-2:]` are by construction the most recent), so their 5
> today-values sit within ~1.2% and land in one `_cluster_levels` bucket"

At E33, the "12th family" was five near-identical numbers inside a single
cluster — one level wearing five hats. **v35 Task 2 added 52-week extreme
anchors** (`factors.avwap_anchors` now returns `52w high` / `52w low` from a
252-bar window alongside the 120-bar pivots and the volume spike). Those are the
first genuinely distant anchors the family has ever had. v35 Task 3 additionally
folded every per-anchor label back to one `AVWAP` family in both
`confidence._resolve_confluence` and `levels.strategy_family`.

**New hypothesis:** *with distant (52-week) anchors, anchored VWAP contributes a
level family that improves or at worst does not degrade out-of-sample win rate,
without inflating the confluence count.*

This is the second and final shot this component gets. A FAIL here should be
read together with E33's FAIL as closing `AVWAP_LEVELS_ENABLED` permanently.

## 3. Instrument, and its known blind spot — read this before trusting §5

**Command (both arms, identical except the flag):**

```bash
AVWAP_LEVELS_ENABLED=false python scripts/backtest/run_backtest_range.py \
    --validation --json data/v35_validation_off.json
AVWAP_LEVELS_ENABLED=true  python scripts/backtest/run_backtest_range.py \
    --validation --json data/v35_validation.json
python scripts/backtest/compare_backtest_json.py data/v35_validation_off.json data/v35_validation.json
```

**Verified before running, not assumed.** The v34 plan discovered mid-task that
its specified backtest command structurally could not see the feature under
test. That check was run here first, by source trace and by an instrumented
tracer:

- This command takes the **named-strategy** branch at `--exit-model v1`
  (the default), and `run_backtest_range.py:326` forces `tp2_mode="none"`
  whenever `exit_model != "v2"`, so `backtest.py:293`'s `build_level_map` call
  is **not reached**.
- `_trade_plan_at`'s `fib_/sr_/atr_/elliott_target_candidates` build each
  strategy's own candidates and never call `collect_candidate_levels`.
- The surviving channel is `apply_level_lifecycle` → `_lifecycle_levels` →
  `build_level_map` → `collect_candidate_levels`, live because
  `LEVEL_LIFECYCLE_STOPS_ENABLED` defaults **true**. AVWAP candidates therefore
  reach `classify_levels`/`preferred_stop_anchor` and can move the **stop**;
  TP1 moves only indirectly, when a widened stop forces
  `select_structural_target` to re-pick.
- Tracer on AAPL/MSFT/NVDA x {4w, 3m} x 11 strategies, with this command's exact
  kwargs: `collect_candidate_levels` called 122x in both arms; **780 AVWAP
  candidates produced with the flag on, 0 with it off**; 6 of 122 trades (4.9%)
  differ, 4 (3.3%) have a different TP1, and one outcome flipped.

**So the instrument is not blind — but it is narrow, and this is its blind
spot:** `count_confirming_strategies` is called **0 times** on this path (it is
reached only from `backtest_scenarios.replay_scenarios:103`, i.e. `--scenarios`
mode). Therefore this command **cannot** measure the brief's originally-stated
primary, "win rate at `MIN_ALERT_CONFIDENCE_LEVEL=4`", nor alert volume — there
is no confidence scoring and there are no alerts on this path.

**Consequence for this pre-registration:** the primary below is stated as the
metric the instrument actually evaluates, and the confluence guard is measured
with a separate purpose-built instrument (§4, clause B). Nothing here is
pre-registered that cannot be read off a real output. Committing a criterion the
harness cannot evaluate is how a shot gets burned for nothing (see
`DATA_DRIVEN_STOPS_ENABLED`, which "scored 0.0000 and burned its shot").

## 4. The reading rule — fixed before the numbers

**Primary metric.** Pooled win rate over the window,
`sum(wins) / sum(n_eval)` across all 11 strategies from the `--json` output
(`n_eval` is already win+loss only, matching this repo's "win_rate over win+loss
only" convention). Computed by `scripts/backtest/compare_backtest_json.py`. Two arms, AVWAP off
(baseline) and on (component), same window, same command.

**PASS requires ALL THREE clauses.**

- **A — win rate, non-inferiority.** `wr_on >= wr_off - 0.50pp`.

  The brief's phrase was "no win-rate regression", which is ambiguous, so it is
  resolved here explicitly. A strict `wr_on >= wr_off` on a point estimate is a
  coin flip on noise at any realistic N. A 0.50pp margin is materially smaller
  than one standard error at the N this window produces (at N ~ 1000 and
  p ~ 0.5, SE ~ 1.6pp), so it admits "statistically indistinguishable" without
  admitting "worse". **Fixed before any win-rate number for either arm was
  read.**

  **Caveat on that SE figure, added at §5.4 review:** the ~1.6pp SE is the
  *independent*-binomial figure (two unrelated samples of size ~1000 each). The
  two arms here are not independent -- same tickers, same window, same
  strategies, differing only in whether AVWAP candidates enter the level map --
  and §3's own harness verification found only ~4.9% of trades differ between
  them at all. The standard error of a *paired* difference that close to
  identical is well under the independent-binomial 1.6pp, so citing 1.6pp
  understates how tight the comparison actually is. That makes the 0.50pp
  margin **more permissive relative to what was really run** than the
  independent-binomial framing implies, not the conservative, comfortably-wide
  margin the SE comparison was meant to suggest. The margin is kept as
  pre-registered (changing it post hoc would be exactly the dredging this
  document exists to prevent); the point is that its statistical justification
  was looser than stated, not that the number itself needs revision.

- **B — confluence guard.** Mean confluence-count delta **< +0.500 methods per
  target**, measured on the **TRAIN** window by `scripts/backtest/measure_avwap_confluence.py`,
  fixed-target arm (level map held still, so the delta is purely the
  family-addition effect).

  This threshold is taken **verbatim from the brief** and was deliberately
  **not** adjusted after a 2-ticker preview came in at +0.4970 — i.e. flush
  against the line. Moving it would be precisely the dredging this document
  exists to prevent. It is a mechanism question, not an out-of-sample one, so
  TRAIN is the correct window for it.

- **C — volume sanity.** `|delta closed trades| <= 10%`. This spec adds no gate,
  so trade count should be roughly flat; a larger swing means the level map moved
  more than intended and must be investigated before shipping.

**TRAIN precondition — the VALIDATION shot is only spent if TRAIN clears.**
`docs/claude/backtest-methodology.md`: "a config that fails train never gets a
validation shot." Clauses A and B are therefore evaluated on TRAIN **first**. If
either fails on TRAIN, the VALIDATION run is **not executed**, and the recorded
outcome is **FAIL (on TRAIN)** — a complete result, not an unfinished task.

**Reporting rule, not a PASS clause.** Wilson 95% intervals for both arms are
reported. Overlap does **not** fail the run, but a PASS with overlapping
intervals must be recorded as "on by default, but not a demonstrated edge" —
the same formulation used for `LEVEL_LIFECYCLE_STOPS_ENABLED` (see
`docs/superpowers/results/2026-08-08-level-lifecycle-stops-validation.md`).

**One shot.** FAIL means `AVWAP_LEVELS_ENABLED` stays default-off, and **that is
a completed result, not a failure to retry.** Combined with E33, a second FAIL
closes this component; re-opening it again would need a genuinely new mechanism,
not a re-run.

## 5. Results

*(Filled in after the runs. TRAIN first; VALIDATION only if TRAIN clears.)*

### 5.1 TRAIN — confluence distribution (clause B)

Instrument: `scripts/backtest/measure_avwap_confluence.py`, TRAIN window, 78 watchlist tickers x
5 horizons (`4w, 2m, 3m, 4m, 6m`), every 20th bar, tolerance 5.0% (the value
`replay_scenarios` uses). **17,053 bars sampled, 264,595 targets evaluated.**

**Fixed-target arm (level map held still) — the guard test:**

| | mean confluence |
|---|---:|
| AVWAP OFF | 4.4889 |
| AVWAP ON | 4.9743 |
| **delta** | **+0.4854** |

**Clause B PASSES: +0.4854 < +0.500.** Headroom is only 0.0146 — about 3% of the
threshold. This is a pass, not a comfortable one.

**The anti-inflation guard holds, verified on real data rather than on unit-test
labels:**

- count-delta histogram: `{0: 136152, 1: 128443}` — **not a single target moved
  by more than +1.**
- all 128,443 of the +1 deltas carry an added-family set of exactly
  `('AVWAP',)`; no other added-family set occurs at all.
- **0 leaks**: no `delta > 1`, and no unfolded `Anchored VWAP (...)` label ever
  reached the family set as its own family.

So Task 3's family folding is genuinely working in production conditions, not
merely in `test_avwap_per_anchor_labels_fold_to_one_family`'s two synthetic
`strategy_family()` assertions.

**Honest observation, and the reason clause B is nearly breached.** The +0.4854
is not inflation — it is that **AVWAP lands within 5% of 48.5% of all candidate
targets** (128,443 / 264,595). It is correctly counted once, but it confirms
almost half of everything, which makes it a weak discriminator: a "confirming
family" that agrees with one target in two carries little information about
which target is better. The 52-week anchors that justified this re-shot are
part of why — they are far from price, so they sit near a great many levels.
This is a signal-quality caveat, not a guard failure, and it is recorded here
rather than resolved.

**Moving-map arm (level map rebuilt with the flag on) — TP/level drift:**

- 264,595 level prices compared: **75.65% unchanged, 24.35% moved.**
- drift among the moved: mean 0.4028%, median 0.2925%, p90 0.9316%, max 2.6479%.
- clustered levels in the map: 264,595 OFF -> 271,547 ON (**+2.63%**).

The map does move, but modestly and without adding a flood of new levels.

### 5.2 TRAIN — win rate (clause A precondition)

Instrument: the §3 command with `--train`. 78 tickers (2 excluded illiquid, 5
excluded bad data), 10 horizons, 11 strategies, 2020-01-01..2023-12-31.

| | wins | n_eval | closed | win% | Wilson 95% | expR |
|---|---:|---:|---:|---:|---|---:|
| OFF | 1384 | 3019 | 4169 | 45.84 | [44.07, 47.62] | +0.1492 |
| ON | 1383 | 3018 | 4170 | 45.83 | [44.05, 47.61] | +0.1487 |

- **win-rate delta -0.018 pp** -> clause A passes on TRAIN (margin 0.50pp).
- expectancy delta **-0.00046 R**.
- closed-trade delta **+1 (+0.02%)** -> clause C passes on TRAIN.
- Wilson intervals overlap almost entirely.

Per strategy, 6 of 11 are bit-identical. Movers: MACD +0.86pp, MA Ribbon
+0.22pp, Break & Retest -0.20pp, RSI Divergence -0.07pp, VWAP -0.49pp. Nothing
approaches significance at these N.

**Observation:** the -0.00046R expectancy delta is strikingly consistent with
E33's -0.0001R. On this instrument AVWAP is still an essentially inert
component — which is what §3's narrow-instrument analysis predicted, since only
~4.9% of trades are perturbed and only through the level-lifecycle stop channel.

**TRAIN precondition CLEARS** (A, B and C all pass on TRAIN). The VALIDATION
shot is therefore spent.

### 5.3 VALIDATION — one shot

Run once on 2026-08-20, both arms, the §3 command with `--validation`. Window
2024-01-01..2025-12-31. **Recorded verbatim; not re-run, not retuned.**

| | wins | n_eval | closed | win% | Wilson 95% | expR |
|---|---:|---:|---:|---:|---|---:|
| OFF | 875 | 1793 | 2553 | 48.80 | [46.49, 51.11] | +0.1898 |
| ON | 873 | 1792 | 2552 | 48.72 | [46.41, 51.03] | +0.1894 |

- **win-rate delta -0.084 pp**
- expectancy delta **-0.00037 R**
- closed-trade delta **-1 (-0.04%)**
- **Wilson intervals overlap** (heavily — the two are nearly coincident)

Per strategy: 5 of 11 are win-rate-identical (4 fully bit-identical --
Fibonacci, Support/Resistance, RSI, Elliott Wave -- plus MACD, whose win rate
and trade counts match but whose expectancy_r/max_dd_pct differ). Movers:
Volume Profile +3.52pp (N=33 -> 31), MA Ribbon +0.36pp, RSI Divergence
-0.16pp, Break & Retest -0.46pp, VWAP -0.68pp, EMA Crossover -2.00pp (N=25 ->
26). Every one of these is far inside sampling noise at its N. (RSI shows 100.00% in both arms on N=22 — a
pre-existing artefact of the baseline system, identical in both arms and
unrelated to AVWAP.)

### 5.4 Verdict — **PASS**

Scored against the §4 reading rule exactly as pre-registered:

| clause | rule | measured | result |
|---|---|---|---|
| **A** win rate | `wr_on >= wr_off - 0.50pp` | 48.72 >= 48.30 (delta -0.084pp) | **PASS** |
| **B** confluence guard | mean delta `< +0.500` on TRAIN | +0.4854 | **PASS** |
| **C** volume sanity | `\|delta closed\| <= 10%` | -0.04% | **PASS** |

**All three clauses pass. VALIDATION: PASS.**

**Consequence, per §4:** `AVWAP_LEVELS_ENABLED` default flips to `true`.

**Stated plainly, because this is the one sentence a future reader must not
miss: under a strict/literal reading of the brief's own PASS text ("no
win-rate regression versus AVWAP off"), this run is a FAIL.** The point
estimate did regress: 48.72% (on) < 48.80% (off). It is the pre-registered
0.50pp non-inferiority margin in clause A -- not the raw point estimate --
that turns this into a PASS. Clauses B and C would have passed under any
reasonable reading of the brief; clause A is the one place the pre-registered
rule, rather than the naive reading, decides the verdict.

**Mandatory caveat, per §4's reporting rule:** the Wilson intervals overlap
almost entirely, so this is recorded as **"on by default, but not a demonstrated
edge"** — the same formulation used for `LEVEL_LIFECYCLE_STOPS_ENABLED`
(default-on since 2026-08-08 on a PASS that "cleared every clause of its one
VALIDATION shot, but ... below the strength threshold fixed in advance, i.e.
NO MEASURABLE out-of-sample effect. It is on because it degrades nothing ...
NOT because an edge was measured" — see
`docs/superpowers/results/2026-08-08-level-lifecycle-stops-validation.md` and
that flag's help text in `swingbot/config.py`). What was measured is
that anchored VWAP **does not degrade** the system, not that it improves it. The
win-rate delta (-0.084pp), the expectancy delta (-0.00037R) and the trade-count
delta (-1 trade) are all indistinguishable from zero. This is a
*non-inferiority* pass, which is exactly what clause A was written to test.

**Three honest observations that belong with this verdict:**

1. **This is the same "inert" reading E33 got, scored against a different
   rule.** E33's gate demanded *improvement* (>= 2 of 3 folds better) and AVWAP's
   -0.0001R failed it. This shot's clause A demanded *non-degradation* and
   AVWAP's -0.00037R passes it. Both measurements agree on the underlying fact —
   AVWAP moves almost nothing on this harness. The verdict differs because the
   question does. That is legitimate (the two gates encode different decisions:
   "is this an edge worth adopting?" vs "is this safe to turn on?") but it should
   not be mistaken for E33 having been overturned by new evidence.

2. **The instrument is narrow** (§3). It sees AVWAP only through the
   level-lifecycle stop channel and never calls `count_confirming_strategies`, so
   the confluence/confidence mechanism this plan is really about is measured only
   by the separate TRAIN probe in §5.1, never end-to-end against realised P&L. A
   `--scenarios`-mode measurement would close that gap and has not been run.

3. **Clause B passed with ~3% headroom, and the reason is a signal-quality
   concern in its own right:** AVWAP confirms 48.5% of all candidate targets
   (§5.1). It is counted once and the guard is airtight, but a family that agrees
   with one target in two is a weak discriminator, and it now feeds the
   confluence count that `MIN_CONFLUENCE` and the confidence score are built on.

**Budget status: spent.** This component has now had two pre-registered shots
(E33 2026-07-26, FAIL; this one 2026-08-20, PASS on a non-inferiority rule).
Re-opening it again requires a genuinely new mechanism, not another re-run.
