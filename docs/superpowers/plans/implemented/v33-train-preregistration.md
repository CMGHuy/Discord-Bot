# v33 TRAIN measurement and VALIDATION pre-registration

Task 7 of `docs/superpowers/plans/implemented/2026-08-16-v33-mtf-trend-alignment.md`.
Written before Task 8's VALIDATION run and **not to be revised after seeing
its result** — the same discipline
`docs/superpowers/plans/implemented/v32-train-preregistration.md` was held to.

---

## How the measurement was taken, and why not with the brief's command

Task 7's brief says to run
`scripts/backtest/run_backtest_range.py --train --json data/v33_train.json`.
**That command cannot measure this plan's work**, and was deliberately not
used:

- `run_backtest_range.py` simulates trades through
  `swingbot.core.backtesting.backtest` / `backtest_scenarios`, a replay
  harness.
- The thing v33 built — `MTF_ADJACENT_GATE` — lives in
  `swingbot/core/scanning/engine.py` (`_scan_one`'s per-scenario loop), and
  `factor_macro_alignment` lives in `swingbot/core/scanning/factors.py`.
  The replay harness never calls `scanning.engine` and never calls
  `run_factors`, so **neither the gate nor the factor can influence its
  output by any code path**. It would have produced a baseline unrelated to
  the gate, and a PASS/FAIL read off it would have been meaningless.

**What was run instead.** v33 Task 1 committed an instrument that records,
per TRAIN trade entry bar, exactly the verdicts the gate keys on
(`scripts/backtest/measure_trend_signal_overlap.py`). Task 7 added the
companion `scripts/backtest/measure_adjacent_gate_effect.py`, which imports
that instrument's `collect()` and **simulates the gate's real decision rule
on the recorded verdicts**: "gate on" is the same population minus every
scenario whose adjacent-horizon verdict is `opposed`. `exempt` and `aligned`
are both kept, per the plan's Global Constraints, which forbid conflating
exempt with opposed.

```
python scripts/backtest/measure_adjacent_gate_effect.py --train \
    --cache-dir <main checkout>/data/backtest_cache --json data/v33_train.json
```

`data/v33_train.json`: **4337 TRAIN scenarios**, 2020-01-01..2023-12-31, 75
tickers x 10 horizons x 11 strategies — the same population size v32's own
TRAIN measurement used, and the same one Task 1 reported against.

**Reproducibility, checked rather than assumed.** The sweep was run twice,
independently, and the two JSON dumps compare **byte-for-byte identical**
(4337 scenarios, 75 tickers, exit 0 both times). The instrument's own
NO-LOOKAHEAD guard — asserting the full-series EMA precompute reproduces
`get_htf_bias` bar for bar — passed on 1230 sampled (horizon, bar) pairs with
0 mismatches, so no number below is lookahead-contaminated.

**The simulated gate is the real gate.** `engine.py`'s `_scan_one` drops a
scenario iff `adjacent_aligned(...)["status"] == "opposed"`; the instrument
drops iff the recorded verdict is `False`, keeping exempt and aligned. Same
rule, verified against the source rather than assumed.

The JSON dumps are **gitignored on purpose** (`.gitignore`, same reasoning as
commit `912e004`): `data/` is bind-mounted into the running containers on the
deploy host, so a committed measurement dump under it breaks CI's `git
reset`. Every number below is therefore recorded *here*, and re-derivable by
re-running the two scripts named above. This overrides the brief's Step 6
`git add data/v33_train.json`.

Win rate is **wins / (wins + losses)** throughout — `backtest.py`'s own
convention, scratch and timeout excluded. "Scenarios" counts every row
*including* scratch/timeout, because the gate drops a scenario before its
outcome is known: that count, not the evaluated one, is the alert-volume
cost.

Every table below prints **scenarios, evaluated and wins**, so each stated
win rate and Wilson interval can be recomputed from this document alone
without the gitignored dump.

**"Alert volume" here means backtest trade *entry* volume — a proxy for
production alert volume, not equal to it.** See "What this Primary drops from
the plan's wording" before the VALIDATION section for the full statement and
for the `MIN_ALERT_CONFIDENCE_LEVEL` condition this measurement cannot apply.

---

## Step 1 — Per-horizon volume and win rate, gate off vs. gate on

**Reading the counts.** Each cell is `scenarios / evaluated / wins`, and the
three are different populations on purpose:

- **scenarios** — every row, scratch and timeout included. This is the
  alert-volume number, because the gate drops a scenario *before* its outcome
  is known. The `volume cut` column is computed from it.
- **evaluated** — scenarios that resolved to a win or a loss (scratch and
  timeout excluded), i.e. `backtest.py`'s own win-rate denominator.
- **wins** — wins among the evaluated.

**Every win rate and Wilson interval in this document is computed on
`wins / evaluated`, never on `scenarios`.** All three counts are printed in
every table below, so each stated interval can be recomputed from this
document alone, without the (gitignored) raw dump.

| Horizon | before: scen / eval / wins | WR before (Wilson 95%) | after: scen / eval / wins | WR after (Wilson 95%) | volume cut | ΔWR | separated? |
|---|---|---|---|---|---|---|---|
| `2w` | 470 / 337 / 144 | 42.73% [37.6, 48.1] | 345 / 247 / 106 | 42.91% [36.9, 49.1] | **26.60%** | +0.19pp | no |
| `4w` | 827 / 571 / 243 | 42.56% [38.6, 46.6] | 780 / 536 / 235 | 43.84% [39.7, 48.1] | 5.68% | +1.29pp | no |
| `2m` | 543 / 391 / 179 | 45.78% [40.9, 50.7] | 522 / 376 / 173 | 46.01% [41.0, 51.1] | 3.87% | +0.23pp | no |
| `3m` | 528 / 397 / 187 | 47.10% [42.2, 52.0] | 511 / 385 / 183 | 47.53% [42.6, 52.5] | 3.22% | +0.43pp | no |
| `4m` | 373 / 276 / 129 | 46.74% [40.9, 52.6] | 363 / 271 / 128 | 47.23% [41.4, 53.2] | 2.68% | +0.49pp | no |
| `5m` | 306 / 234 / 109 | 46.58% [40.3, 53.0] | 295 / 226 / 105 | 46.46% [40.1, 53.0] | 3.59% | −0.12pp | no |
| `6m` | 300 / 220 / 100 | 45.45% [39.0, 52.1] | 289 / 213 / 97 | 45.54% [39.0, 52.2] | 3.67% | +0.09pp | no |
| `7m` | 404 / 293 / 138 | 47.10% [41.5, 52.8] | 380 / 277 / 133 | 48.01% [42.2, 53.9] | 5.94% | +0.92pp | no |
| `8m` | 298 / 214 / 101 | 47.20% [40.6, 53.9] | 281 / 202 / 96 | 47.52% [40.7, 54.4] | 5.70% | +0.33pp | no |
| `9m` | 288 / 217 / 99 | 45.62% [39.1, 52.3] | 288 / 217 / 99 | 45.62% [39.1, 52.3] | 0.00% | +0.00pp | no |
| **ALL** | **4337 / 3150 / 1429** | **45.37% [43.6, 47.1]** | **4054 / 2950 / 1355** | **45.93% [44.1, 47.7]** | **6.53%** | **+0.57pp** | **no** |

`9m`'s 0.00% cut is the correct sanity signature: `9m` has no horizon above
it, so it is *exempt*, never gated.

**Comparator arm** (Task 1 asked for it — the horizon's *own* trend rather
than the adjacent one): 4337 / 3150 / 1429 → 3741 / 2731 / 1269, i.e. 45.37%
[43.6, 47.1] → 46.47% [44.6, 48.3]; cut 13.74%, ΔWR +1.10pp, also not
separated (the intervals overlap). The own
horizon is still the better-powered signal, and v33 gates on the adjacent one
anyway because that is what the spec built; this is recorded so a future spec
can revisit it with evidence rather than rediscover it.

**The honest headline: the gate's TRAIN effect is a small positive that is
not statistically demonstrated.** Every horizon's before/after Wilson
intervals overlap, and so does the aggregate's. +0.57pp on 4337 scenarios is
a point estimate, not a proven edge. This is stated here, before VALIDATION,
so that a PASS on Task 8 cannot later be sold as more than it is.

## Step 2 — Per-horizon volume loss against the ≤~30% budget

**Aggregate cut is 6.53%, far inside the plan's ≤~30% budget.** The cut is
very unevenly distributed: `2w` alone accounts for 125 of the 283 dropped
scenarios.

`2w`'s 26.60% is confirmed against Task 1's independent measurement to the
decimal, as is the 2.68–5.94% range across every other horizon.

**Decision: no horizon-scoped exemption. The gate applies to all 10
horizons.** Reasoning:

1. `2w`'s 26.60% is **inside** the ≤~30% budget the plan set. The
   pre-stated rule is a budget, and `2w` passes it. It is close to the
   ceiling, which is why the plan insisted on measuring per horizon — but
   close-and-inside is inside.
2. Scoping `2w` out would have to be justified by its poor cost/benefit
   (26.60% of its volume for +0.19pp). That ΔWR is **not Wilson-separated**,
   and neither is any other horizon's. Choosing the gate's scope by ranking
   ten non-separated point estimates is fitting to noise — precisely the
   data-dredging that v32's discipline (and this plan's own
   TRAIN-derived-weights rule) exists to prevent. A scope picked that way
   would look good on TRAIN by construction and carry nothing into
   VALIDATION.
3. The aggregate budget is not under pressure (6.53% vs. 30%), so there is
   no volume problem that an exemption is needed to solve.

**Recorded as a pre-registered watch item, not a live gate:** if VALIDATION
reproduces `2w` paying a >25% cut for a sub-1pp gain, a `2w` exemption is
the *first* thing a follow-up spec should measure. It must be measured
there, not assumed here.

## Step 3 — Neutral-band test

Brief's test: for scenarios where `|ema_fast − ema_slow| / close < 0.5%` on
the **adjacent** horizon's EMAs, is the win rate indistinguishable from a
coin flip (Wilson interval spanning 50%)?

`0.5%` was the pre-committed threshold; `0.25%` and `1.0%` are reported as
sensitivity only. A band chosen by scanning thresholds for the one that helps
would be exactly the dredging this document refuses elsewhere.

Same count convention as Step 1: `scenarios` is the volume number,
`evaluated`/`wins` are what the win rate and its Wilson interval are computed
on.

| Band | scen inside | share | eval | wins | WR inside (Wilson 95%) | spans 50%? | opposed inside / total |
|---|---|---|---|---|---|---|---|
| <0.25% | 259 | 6.4% | 188 | 83 | 44.15% [37.2, 51.3] | yes | 63 / 283 |
| **<0.50%** | **473** | **11.7%** | **340** | **142** | **41.76% [36.6, 47.1]** | **no** | **110 / 283** |
| <1.00% | 839 | 20.7% | 598 | 246 | 41.14% [37.3, 45.1] | no | 175 / 283 |

(`share` is of the 4048 scenarios that carry an adjacent-horizon margin at
all — the remainder are `9m`, which has no adjacent horizon, plus rows with
too little history.)

**Decision: NO neutral band. `mtf.py` is unchanged.** Three independent
reasons, any one of which is sufficient:

1. **The pre-committed test fails outright.** At the 0.5% band the Wilson
   interval is [36.6%, 47.1%] — its upper bound is below 50%, so the band is
   *not* indistinguishable from a coin flip. (It is also not distinguishable
   from the population's own 45.4% base rate, which is the fairer null; by
   that reading the band is simply an ordinary slice, not a noise pocket.)
2. **An opposed verdict inside the band still discriminates.** Inside the
   0.5% band, agree scores 42.86% (n=259) against oppose's 38.27% (n=81) —
   a **+4.59pp lift with the same sign as outside the band** (+10.15pp).
   Near-flat EMAs make the verdict weaker, not meaningless. Exempting them
   would hand back signal, not noise.
3. **A neutral band is a volume-relief mechanism, and there is no volume
   problem.** The gate costs 6.53% against a 30% budget. Applying the band
   anyway makes the gate strictly worse on the axis it exists for: the
   aggregate ΔWR falls from **+0.57pp to +0.36pp** while the cut falls
   6.53% → 3.99%. Paying win rate to buy back volume nobody needed is a bad
   trade.

The `<1.00%` row is worth recording because it points the same way even
harder: outside a 1% band the verdict's lift is +16.48pp and **non-overlapping**
(the only separated result anywhere in this measurement), while inside it the
lift collapses to +0.87pp. That is a real gradient — margin size does track
verdict quality — but it argues for *weighting* the verdict by margin in some
future spec, not for the binary exemption v33 asked about, and it is not what
this plan pre-registered. Left as evidence for a future spec.

## Step 4 — `_MACRO_ALIGNMENT_POINTS` re-derived

**Note the different `n` from Steps 1 and 3:** this step compares two arms of
the *same* population rather than measuring a volume cut, so there is no
scenario count to report — every `n` below is already the **evaluated**
count (wins + losses), which is what its Wilson interval is computed on.

| Arm | evaluated | wins | WR | Wilson 95% |
|---|---|---|---|---|
| 6m anchor agrees | 2150 | 967 | 44.98% | [42.9, 47.1] |
| 6m anchor opposes | 56 | 24 | 42.86% | [30.8, 55.9] |

Lift **+2.12pp, Wilson intervals overlapping almost entirely.**

The fuller sweep did **not** sharpen Task 1's finding: `n_oppose` is 56 in
both, because a 6m trend simply rarely opposes a shorter-horizon entry. There
is no bigger n to be had from this window.

Per horizon it is worse than merely weak — every measurable horizon overlaps,
**and the sign flips**:

| Horizon | agree n / WR | oppose n / WR | lift |
|---|---|---|---|
| `2w` | 327 / 42.51% | 10 / 50.00% | −7.49pp |
| `4w` | 562 / 42.53% | 9 / 44.44% | −1.92pp |
| `2m` | 382 / 46.34% | 9 / 22.22% | +24.11pp |
| `3m` | 387 / 47.29% | 10 / 40.00% | +7.29pp |
| `4m` | 266 / 46.62% | 10 / 50.00% | −3.38pp |
| `5m` | 226 / 46.46% | 8 / 50.00% | −3.54pp |

Four of six point the wrong way, on 8–10 opposed scenarios each. That is the
signature of noise, not of a weak-but-real effect.

**Decision: `_MACRO_ALIGNMENT_POINTS = 0`, measured (no longer provisional).**

v32 Task 9's rule — *assign points from measured lift* — is the same rule that
excluded 13 factors from `FACTORS` on exactly these grounds
(`factors.py`'s comment above `FACTORS`). Awarding this factor points anyway
would make it the single exception to the discipline the rest of that file
was built on. `factor_macro_alignment` **stays registered** in `FACTORS`,
in exactly `factor_gap`'s position: correct, tested, contributing nothing to
the score, and still carrying the 6m reading and its counter-trend warning
into the breakdown as information.

---

## VALIDATION pre-registration

**Task 8 must run this, not `run_backtest_range.py`** — see the first section
for why that script cannot see the gate. The plan's Task 8 Step 2 names it;
that instruction is superseded by this pre-registration:

```
python scripts/backtest/measure_adjacent_gate_effect.py --validation \
    --cache-dir <main checkout>/data/backtest_cache --json data/v33_validation.json
```

### What this Primary drops from the plan's wording, and why

The plan's Task 7 Step 5 template says: *"Primary: win rate at
MIN_ALERT_CONFIDENCE_LEVEL=4 with MTF_ADJACENT_GATE=on."* The Primary below
**deliberately drops the `MIN_ALERT_CONFIDENCE_LEVEL=4` condition**, and that
substitution is recorded here rather than made silently:

- The instrument measures **raw backtest trade entries**, which carry no
  confidence score at all. A confidence level is produced by
  `scanning.engine` + `run_factors` on live scan scenarios, and the replay
  harness this population comes from never calls either (the same reason
  `run_backtest_range.py` cannot see the gate — first section). There is no
  path by which a `MIN_ALERT_CONFIDENCE_LEVEL` filter could be applied to
  these rows, so the condition could not be honoured, only pretended to.
- The condition is also **orthogonal to what is being tested**. The gate is a
  filter that runs *before* scoring (`engine.py:925`, ahead of the confluence
  and confidence work); a confidence-level threshold filters *after*. Testing
  the gate on the unscored population measures the gate's own effect rather
  than the interaction of two filters.

**Consequently, "alert volume" throughout this document means backtest trade
_entry_ volume — a proxy for production alert volume, not equal to it.** In
production an entry must additionally clear the confidence-level threshold
and the min-strategies-confirmed requirement before it becomes an alert, so
the real alert count is strictly smaller than these scenario counts. The
≤30% and ≤50% budgets below are therefore stated and judged against
entry volume. This is the honest reading; a claim about production alert
counts would need a live scan comparison, which no offline harness in this
repo can produce.

- **Primary:** win rate (wins / (wins + losses)) over the VALIDATION window
  2024-01-01..2025-12-31, **gate on vs. gate off on the same population** —
  i.e. `adjacent_gate.ALL.after.wr` vs `adjacent_gate.ALL.before.wr` in the
  emitted JSON. The comparator is the ungated same-window population, not
  v32's number: the gate is a filter over a population, so the only
  like-for-like baseline is that population unfiltered.

- **PASS** requires **all three**:
  1. `adjacent_gate.ALL.after.wr` **>** `adjacent_gate.ALL.before.wr`
     (strictly; equal is a FAIL), **and**
  2. `adjacent_gate.ALL.volume_loss_pct` **≤ 30.0**, **and**
  3. `max(adjacent_gate[h].volume_loss_pct for h in the 10 horizons)`
     **≤ 50.0**.

- **FAIL:** any of the three unmet. Explicitly: a win rate that is equal or
  lower, an aggregate cut above 30%, or any single horizon cut above 50%.

- **Gate scope:** **all 10 horizons** (`2w`…`9m`), per Step 2. `9m` is
  *exempt* by construction (no horizon above it) — that exemption is not a
  pass and is not a scope exclusion.

- **Neutral band:** **excluded**, per Step 3. `mtf.py`'s
  `horizon_trend`/`adjacent_aligned` ship with no band.

- **`_MACRO_ALIGNMENT_POINTS = 0`** is already committed and is *not* under
  test here. It is a scoring weight; the gate is a filter. VALIDATION tests
  the gate.

- **Mandatory reporting condition (does not change the PASS bar).** TRAIN's
  aggregate effect was +0.57pp with fully overlapping Wilson intervals. Task 8
  must therefore report whether the VALIDATION before/after intervals are
  separated, and if they are not, `docs/strategy.md` must describe the gate as
  a **small, not statistically demonstrated** improvement. A PASS on point
  estimate alone may flip the flag on; it may not be written up as a proven
  edge.

- **One shot.** Task 8 runs it once and records the result verbatim, PASS or
  FAIL. **No re-runs on FAIL**, no threshold tuning, no scope adjustment
  after seeing the number. A FAIL means `MTF_ADJACENT_GATE` stays
  `default="false"` and no `VERSION.json` bump is earned.

---

# VALIDATION result — **FAIL** (appended after the run)

**Everything above this line is the pre-registration and is unchanged** — it
was committed at `0dc75ee`, `git diff` against that commit was empty
immediately before the run, and nothing above was edited after seeing the
number. This section only records what came back.

Run once, 2026-08-18, exit 0:

```
python scripts/backtest/measure_adjacent_gate_effect.py --validation \
    --cache-dir <main checkout>/data/backtest_cache --json data/v33_validation.json
```

`2804 VALIDATION scenarios`, 2024-01-01..2025-12-31, 75 tickers x 10 horizons
x 11 strategies. The instrument's NO-LOOKAHEAD guard passed first: 1230
sampled (horizon, bar) pairs, 0 mismatches. The dump is gitignored for the
same deploy reason as TRAIN's, so every number is recorded here.

## The three pre-registered conditions, scored

| # | Condition | Measured | Verdict |
|---|---|---|---|
| 1 | `ALL.after.wr` **>** `ALL.before.wr` (strict) | 47.981% vs **48.495%** — the gate **lowered** win rate by **0.515pp** | **FAIL** |
| 2 | `ALL.volume_loss_pct` ≤ 30.0 | **6.63%** | pass |
| 3 | `max` per-horizon `volume_loss_pct` ≤ 50.0 | **32.06%** (`2w`; next highest 7.66%) | pass |

**Verdict: FAIL.** Condition 1 is unmet, and the rule is "any of the three
unmet". Conditions 2 and 3 pass comfortably; they do not offset condition 1.

**Mandatory reporting condition:** the before/after Wilson intervals **overlap**
(`separated: false`) — before 48.50% [46.31, 50.69], after 47.98% [45.71,
50.25]. As on TRAIN, the effect is not statistically demonstrated. The
direction of the point estimate simply reversed: TRAIN +0.57pp, VALIDATION
−0.51pp, both inside the noise. That is the textbook signature of a signal
with no measurable edge, which is exactly what the pre-registration warned
TRAIN's overlapping intervals might mean.

## Step 1 table — VALIDATION, gate off vs. gate on

Same format as TRAIN's table above: `scenarios / evaluated / wins`, win rate
is `wins / evaluated`.

| Horizon | before: scen / eval / wins | WR before (Wilson 95%) | after: scen / eval / wins | WR after (Wilson 95%) | volume cut | ΔWR | separated? |
|---|---|---|---|---|---|---|---|
| `2w` | 315 / 235 / 104 | 44.26% [38.0, 50.6] | 214 / 158 / 67 | 42.41% [35.0, 50.2] | **32.06%** | −1.85pp | no |
| `4w` | 521 / 346 / 160 | 46.24% [41.1, 51.5] | 496 / 328 / 151 | 46.04% [40.7, 51.4] | 4.80% | −0.21pp | no |
| `2m` | 347 / 245 / 117 | 47.76% [41.6, 54.0] | 337 / 239 / 113 | 47.28% [41.0, 53.6] | 2.88% | −0.47pp | no |
| `3m` | 344 / 240 / 114 | 47.50% [41.3, 53.8] | 335 / 234 / 110 | 47.01% [40.7, 53.4] | 2.62% | −0.49pp | no |
| `4m` | 238 / 171 / 84 | 49.12% [41.7, 56.6] | 235 / 170 / 84 | 49.41% [42.0, 56.9] | 1.26% | +0.29pp | no |
| `5m` | 188 / 132 / 66 | 50.00% [41.6, 58.4] | 185 / 130 / 64 | 49.23% [40.8, 57.7] | 1.60% | −0.77pp | no |
| `6m` | 190 / 134 / 65 | 48.51% [40.2, 56.9] | 185 / 130 / 61 | 46.92% [38.6, 55.5] | 2.63% | −1.58pp | no |
| `7m` | 251 / 182 / 95 | 52.20% [45.0, 59.3] | 237 / 171 / 87 | 50.88% [43.4, 58.3] | 5.58% | −1.32pp | no |
| `8m` | 209 / 155 / 81 | 52.26% [44.4, 60.0] | 193 / 143 / 73 | 51.05% [42.9, 59.1] | 7.66% | −1.21pp | no |
| `9m` | 201 / 154 / 81 | 52.60% [44.7, 60.3] | 201 / 154 / 81 | 52.60% [44.7, 60.3] | 0.00% | +0.00pp | no |
| **ALL** | **2804 / 1994 / 967** | **48.50% [46.3, 50.7]** | **2618 / 1857 / 891** | **47.98% [45.7, 50.3]** | **6.63%** | **−0.51pp** | **no** |

`9m`'s 0.00% cut is the same correct sanity signature as on TRAIN: no horizon
above it, so it is *exempt*, never gated. **Eight of the ten horizons moved
negative**, including every horizon from `2m` up except `4m`. On TRAIN, nine
of ten were positive. Nothing about the sign pattern survived the window
change.

**The `2w` watch item fired, and then some.** The pre-registration recorded
(Step 2) that "if VALIDATION reproduces `2w` paying a >25% cut for a sub-1pp
gain, a `2w` exemption is the *first* thing a follow-up spec should measure."
VALIDATION paid **32.06%** of `2w`'s volume — above the 30% aggregate budget
figure, though the pre-registered per-horizon condition was the looser ≤50%,
which it still meets — for **−1.85pp**. Worse than the watch item's wording
anticipated, and in the other direction. That remains a follow-up spec's
question; it is not re-scoped here.

**Comparator arm** (the horizon's *own* trend rather than the adjacent one):
2804 / 1994 / 967 → 2386 / 1694 / 811, i.e. 48.50% [46.3, 50.7] → 47.87%
[45.5, 50.3]; cut 14.91%, ΔWR **−0.62pp**, also overlapping. TRAIN's
better-powered alternative did not survive either, so the FAIL is not "we
gated on the wrong one of the two signals".

**Neutral band, for the record only** (it was pre-registered as *excluded*,
and stays excluded — this is not a re-scoping): with the 0.50% band the
aggregate is 2695 / 1917 / 924 = 48.20% [46.0, 50.4], cut 3.89%, ΔWR
−0.30pp, still overlapping and still negative. A band would not have rescued
the gate.

**6m macro anchor on VALIDATION**, also for the record: agree n=1346
WR=46.7%, oppose n=23 WR=73.9% — i.e. the *counter*-macro arm won more often,
on 23 evaluated scenarios. `_MACRO_ALIGNMENT_POINTS = 0` (committed in Task 7
from TRAIN) was not under test and is unchanged; VALIDATION gives no reason
to award it points, and the inverted sign on n=23 is not evidence of anything
either.

## What this means, and what was and was not done

Per the pre-registration's own FAIL clause, and Task 8's brief:

- `MTF_ADJACENT_GATE` **stays `default="false"`** in `swingbot/config.py`. The
  gate ships as a measured, tested, off-by-default option, not as behaviour.
- **No `VERSION.json` bump** — nothing a running container does changed. The
  plan's `Bump: bot minor` header was a prediction conditional on a PASS.
- `docs/strategy.md` gets a short note that the gate was measured and did not
  clear VALIDATION, pointing here, so the next reader does not rediscover
  this from scratch. It is **not** written up as a shipping feature.
- **The command was run exactly once.** No re-run, no threshold change, no
  window or cache-path change, no "double check". The FAIL is recorded as it
  came back.

**What a future spec may legitimately ask** (none of it licensed by this
document, all of it needing its own pre-registration): whether a `2w`
exemption changes the picture; whether the gate helps inside a narrower
population (e.g. only scenarios that would clear `MIN_ALERT_CONFIDENCE_LEVEL`,
which this offline harness structurally cannot filter on — see "What this
Primary drops from the plan's wording"); or whether horizon-to-horizon trend
belongs in scoring rather than as a hard filter. What it may **not** do is
re-run this same measurement and read a different verdict off it.
