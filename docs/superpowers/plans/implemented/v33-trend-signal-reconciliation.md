# v33 trend-signal reconciliation — TRAIN evidence and four decisions

Task 1 of `docs/superpowers/plans/2026-08-16-v33-mtf-trend-alignment.md`.
Written from a TRAIN-only measurement; **no VALIDATION data was read**, and
nothing here consumes v33's one-shot validation budget.

Tasks 4, 5 and 6 implement the decisions in the ["The four
decisions"](#the-four-decisions) section. Task 6 in particular is a direct
transcription of it — read that section, not the plan's original guesses at
what this task would find.

---

## Methodology

**Population.** Every backtest trade whose entry bar falls inside TRAIN
(`2020-01-01..2023-12-31`), over the 75-ticker CSV cache
(`data/backtest_cache/`, `scripts/data/fetch_backtest_data.py`) × 10
horizons × 11 strategies, `exit_model="v2"`, `scale_out=True` — the same
harness shape and the same population as v32 Task 8
(`scripts/backtest/measure_factor_lift.py`).

**Sample size: 4337 scenarios** — the plan asked for ≥500. The **entry set**
is identical in size to v32's `data/v32_train_lift.json` (also 4337), as
expected from the same window, cache and strategy/horizon grid.

**The outcome resolution is not identical, and this is only an entry-count
match — not a full reproduction of v32's run.**

| | win | loss | scratch | timeout | evaluated | WR |
|---|---|---|---|---|---|---|
| v32 `v32_train_lift.json` | 1457 | 1701 | 983 | 196 | 3158 | 46.14% |
| this measurement | 1429 | 1721 | 1000 | 187 | 3150 | 45.36% |

About 30 trades (≈0.9% of evaluated) resolve differently, moving the pooled
win rate 0.78pp. What was checked, and ruled out:

- **Not the data.** The CSV cache is unchanged since 2026-08-07, well before
  either run.
- **Not the harness.** Both call
  `run_backtest(ticker, df, strategy, hk, exit_model="v2", scale_out=True)`
  identically.
- **Not the exit arithmetic.** Diffing `swingbot/` between v32's
  measurement commit (`59c150e`) and this branch's HEAD shows the only
  changes on the backtest path are the A/B/C-tier removal (`backtest.py`,
  `plan_engine.py`) and a config *help-string* edit — no change to entry,
  target, stop or exit computation. v31's structural-target work was
  already merged before `59c150e`, so it is not the cause either.
- **Not run-to-run noise.** `run_backtest` is deterministic here: three
  independent runs on this branch produced 1429/1721/1000/187 every time.

The residual explanation is environment/config state at the time of v32's
run (`.env` is the single config source and differs per worktree; several
`config` values feed scenario construction). Pinning it exactly would mean
reconstructing v32's environment, which is that plan's territory, not this
task's.

**What this does and does not affect.** Nothing here is a cross-run
comparison — every number in this document is computed within this single
self-consistent dataset, so the pairwise V values, the lifts and the
per-horizon table are internally valid regardless. But the tightest result
in the document, `adj_agree`'s 0.22pp Wilson gap, sits well inside a
0.78pp shift in the base win rate. **Treat `adj_agree`'s separation as
fragile to environment state, not as a settled fact** — one more reason
Task 7's sweep, not this table, is the real test of the adjacent gate.

| | |
|---|---|
| Scenarios | 4337 |
| Outcomes | 1429 win, 1721 loss, 1000 scratch, 187 timeout |
| Evaluated (win+loss) | 3150 |
| Scratch+timeout share | 27.4% of closed trades (under the 50% methodology cap) |
| Direction | 3675 bullish, 662 bearish |

**Win rate** is `wins / (wins + losses)`, scratches and timeouts excluded —
`backtest.py`'s own convention. **Wilson 95% intervals** come from
`scripts/backtest/measure_factor_lift.py::wilson_interval`, reused verbatim.
Two groups are called *separated* only when their Wilson intervals do not
overlap; an overlapping pair is reported as no measured lift, not as a small
one.

**Cramér's V** is `sqrt(chi2 / (n * min(r-1, c-1)))` on the contingency table
of each pair, computed only over rows where **both** signals are non-`None`
(an unmapped or exempt reading is missing data, not a third category). No
bias correction — the plan's `> 0.7` rule is stated against plain V.

**NO-LOOKAHEAD.** Every reading uses `df.iloc[:i+1]` for the entry bar `i`.
`mtf_alignment` is called per window (its weekly resample's last bar is a
partial week ending at `i`, so it is not precomputable). The EMAs behind
`get_htf_bias`, the adjacent check and the macro anchor *are* precomputed
over the full series, which is exact rather than approximate: pandas
`ewm(span=N, adjust=False)` is strictly recursive, so `ema(full).iloc[i]` is
bit-identical to `ema(full.iloc[:i+1]).iloc[-1]`. This was verified against
the real `get_htf_bias` on 123 sampled (horizon, bar) pairs — **0
mismatches** — before the full run.

**Signals recorded.** The plan's four, plus two comparators that turned out
to matter:

| Key | Signal | Definition |
|---|---|---|
| `mtf_alignment` | S1, existing | `edge/factors.py::mtf_alignment(window, direction)`, 0–3, weekly resample |
| `htf_agree` | S2, existing | `scanning/regime.py::get_htf_bias(window, hk)["bias"] == direction` |
| `penalty_fired` | S3, existing | `HTF_COUNTER_TREND_PENALTY` would apply: `htf` present and its bias opposes |
| `adj_agree` | S4, **proposed** (plan Tasks 2–4) | next horizon's own `HORIZONS` pair: `"bullish" if ema_fast > ema_slow else "bearish"`, compared to direction. `9m` has no next horizon → exempt |
| `own_agree` | comparator | same formula on **this** horizon's own EMA pair |
| `macro_agree` | comparator, **proposed** (plan Task 5) | the `6m` anchor's own pair (50 vs 200 EMA). `6m`–`9m` exempt per the plan's own constraint |

`adj_agree` and `macro_agree` do not exist yet (Task 2 will encapsulate them
as `horizon_trend`/`adjacent_horizon` in `swingbot/core/market/mtf.py`), so
they were computed inline from `HORIZONS` using exactly the formula Task 2
specifies.

**Known limitation — the population is entries, not market states.** Every
row is a bar on which some strategy actually fired, not a uniformly sampled
trading day. Those entries cluster heavily in uptrends: 3675 of 4337 are
bullish, and `get_htf_bias` opposes on only 2.9% of them. That is *not*
because the 50/200-day EMA is rarely bearish — sampled over all AAPL bars
from index 400 on, the 50-EMA bias is bearish 527 of 1506 days (35%). It is
because signal generation and higher-timeframe trend are correlated
upstream of this measurement. The practical consequence is that
`get_htf_bias`'s and `macro_agree`'s opposed cells are small (n=67 and n=56
evaluated), which is precisely why their intervals overlap; their lift is
**unmeasured on this population**, not measured and found to be zero. Both
decisions below are written to respect that distinction.

**Reproducibility.** The measurement was run twice, in two separate
processes from two scripts (the second adding `macro_agree`). Every shared
number — n, all ten shared V values, all five shared lift rows, the
per-horizon coverage table — came out identical.

---

## Result 1 — pairwise Cramér's V

Sorted by V. The plan's collapse threshold is 0.7.

| Pair | V | n | Verdict |
|---|---|---|---|
| `htf_agree` × `penalty_fired` | **1.0000** | 4337 | **COLLAPSE** — perfect, and by construction |
| `adj_agree` × `own_agree` | 0.5677 | 4048 | keep both |
| `mtf_alignment` × `htf_agree` | 0.3752 | 4337 | keep both |
| `mtf_alignment` × `penalty_fired` | 0.3752 | 4337 | keep both |
| `htf_agree` × `adj_agree` | 0.3348 | 4048 | keep both |
| `penalty_fired` × `adj_agree` | 0.3348 | 4048 | keep both |
| `htf_agree` × `macro_agree` | 0.2930 | 3047 | keep both |
| `penalty_fired` × `macro_agree` | 0.2930 | 3047 | keep both |
| `htf_agree` × `own_agree` | 0.2604 | 4337 | keep both |
| `penalty_fired` × `own_agree` | 0.2604 | 4337 | keep both |
| `adj_agree` × `macro_agree` | 0.2110 | 3047 | keep both |
| `mtf_alignment` × `adj_agree` | 0.1163 | 4048 | keep both |
| `mtf_alignment` × `own_agree` | 0.0977 | 4337 | keep both |
| `own_agree` × `macro_agree` | 0.0660 | 3047 | keep both |
| `mtf_alignment` × `macro_agree` | 0.0317 | 3047 | keep both |

**Exactly one pair of fifteen exceeds 0.7, and it reaches 1.0.** The plan's
suspicion that the four signals are largely the same measurement is *not*
what TRAIN shows: every cross-family pair sits between 0.03 and 0.57. The
redundancy is real but it is entirely inside one pair, and that pair is an
identity rather than a correlation (see Decision 2).

Supporting contingency tables:

```
htf_agree x penalty_fired : {False|True: 127, True|False: 4210}
htf_agree x adj_agree     : {False|False: 67, False|True: 53, True|False: 216, True|True: 3712}
mtf_alignment x adj_agree : {0|False: 20, 0|True: 65,  1|False: 72,  1|True: 664,
                             2|False: 135, 2|True: 1895, 3|False: 56, 3|True: 1141}
adj_agree x own_agree     : {False|False: 245, False|True: 38, True|False: 331, True|True: 3434}
htf_agree x macro_agree   : {False|False: 28, False|True: 68, True|False: 55, True|True: 2896}
macro_agree x adj_agree   : {False|False: 34, False|True: 49, True|False: 197, True|True: 2767}
```

`get_htf_bias` and the adjacent check disagree on **269 of 4048** scenarios
where both are available (6.6%) — small, but not nil, and enough to explain
V = 0.335.

---

## Result 2 — per-signal win-rate lift

| Signal (agree vs oppose) | n agree | WR agree | Wilson | n oppose | WR oppose | Wilson | Lift | Separated? |
|---|---|---|---|---|---|---|---|---|
| **`adj_agree`** — adjacent horizon | 2733 | 46.0% | [44.1, 47.8] | 200 | 37.0% | [30.6, 43.9] | **+9.0pp** | **yes** |
| `own_agree` — own horizon | 2731 | 46.5% | [44.6, 48.3] | 419 | 38.2% | [33.7, 42.9] | +8.3pp | yes |
| `htf_agree` — `get_htf_bias` | 3083 | 45.6% | [43.9, 47.4] | 67 | 32.8% | [22.8, 44.7] | +12.8pp | **no — overlap** |
| `penalty_fired` (inverted) | 3083 | 45.6% | [43.9, 47.4] | 67 | 32.8% | [22.8, 44.7] | +12.8pp | **no — overlap** |
| `macro_agree` — 6m anchor | 2150 | 45.0% | [42.9, 47.1] | 56 | 42.9% | [30.8, 55.9] | +2.1pp | **no — overlap** |
| **`mtf_alignment`** (≥2 vs ≤1) | 2492 | 43.7% | [41.8, 45.7] | 658 | 51.7% | [47.9, 55.5] | **−8.0pp** | **yes — wrong-signed** |

Two things to read carefully here.

**`adj_agree` is the only signal in the table with a real, positively-signed
lift** — and its separation is razor-thin: the agree interval's floor is
44.10% against the oppose interval's ceiling of 43.88%, a gap of 0.22pp. It
clears the bar, but it clears it by a hair, on `n_oppose = 200`. Task 7's
sweep should be read as the real test of the adjacent gate, not as a
formality confirming this.

**`mtf_alignment` is separated in the wrong direction.** Scenarios where the
weekly frame *disagrees* with the trade won **more** often. Its per-value
table is non-monotonic:

| `mtf` | n (evaluated) | Win rate | Wilson 95% |
|---|---|---|---|
| 0 | 58 | 34.5% | [23.6, 47.3] |
| 1 | 600 | **53.3%** | [49.3, 57.3] |
| 2 | 1587 | 42.5% | [40.1, 44.9] |
| 3 | 905 | 45.9% | [42.6, 49.1] |

The live scoring map is `mtf_points = {0: 0, 1: 3, 2: 6, 3: 10}`
(`planning/quality.py`, mirrored by `scanning/factors.py::factor_mtf`) —
monotone increasing. It awards its **fewest** non-zero points to the bucket
with the **best** measured win rate (`mtf=1`, 53.3%, n=600) and its most to
buckets measuring 42–46%. The mapping's designed premise is contradicted.

### Corroboration from v32

`docs/superpowers/plans/implemented/v32-train-preregistration.md` measured
the same 4337 trades with a different (rank-median) split and reached
compatible conclusions independently: **"HTF bias"** and **"MTF alignment"**
were both listed as *"Measured, Wilson-overlapping (indistinguishable from
zero lift) — dropped"*. Neither survived into `FACTORS`, which today holds
only the inert `factor_gap`.

So this is not a first, contestable reading of two signals. It is a second
measurement, with a different split, agreeing with the first — and the
coarser threshold split used here is *harsher* on `mtf_alignment` than v32's
was, turning "no measured lift" into "measured lift, wrong sign".

Repo precedent for a real-but-wrong-signed factor is established and is
**drop, not invert**: v32 dropped `RSI trend alignment` (−0.056,
non-overlapping) rather than flipping it. Inverting a sign discovered on
TRAIN is a new hypothesis and would need its own pre-registration and its
own VALIDATION shot.

---

## Two of the plan's premises that TRAIN contradicts

Both need correcting before Tasks 4–6 act on them.

### Premise A — "half the horizons have no higher-timeframe signal at all today". **False.**

The plan (line 70) and this task's brief both state that `_HTF_EMA_PERIOD`
maps only `2w`,`4w`,`2m`,`3m`,`6m`, leaving `4m`,`5m`,`7m`,`8m`,`9m`
returning `None`. **Commit `512200e` (2026-07-07) already extended it to all
ten horizons**, five weeks before the plan was written:

```python
# swingbot/core/scanning/regime.py:38
_HTF_EMA_PERIOD = {
    "2w": 50, "4w": 50, "2m": 50,
    "3m": 200, "4m": 200, "5m": 200, "6m": 200, "7m": 200, "8m": 200, "9m": 200,
}
```

Measured, not inferred: **`htf_none = 0` of 4337**, and 0 in every one of the
ten per-horizon buckets, including the five the plan calls uncovered.

| Horizon | n | `htf` = None | `adj` = None |
|---|---|---|---|
| 2w | 470 | 0 | 0 |
| 4w | 827 | 0 | 0 |
| 2m | 543 | 0 | 0 |
| 3m | 528 | 0 | 0 |
| **4m** | 373 | **0** | 0 |
| **5m** | 306 | **0** | 0 |
| 6m | 300 | 0 | 0 |
| **7m** | 404 | **0** | 0 |
| **8m** | 298 | **0** | 1 |
| **9m** | 288 | **0** | 288 |

What *is* stale is the **docstring** at `regime.py:53`, which still says
"3m / 6m horizons → 200-day EMA". The plan's line 70 inherited its claim
from that docstring rather than from the dict beneath it.

The only genuine coverage hole in the whole set is the adjacent check's own:
`9m` has no horizon above it, so all 288 of its scenarios are exempt. The
plan already declares that an exemption rather than a pass, which is
correct.

### Premise B — "two of the four are the same signal counted twice, via the `htf` quality component and the penalty". **True, but not where the plan says.**

`UNIFIED_CONFIDENCE` is default-**off**, so `score_confidence()` dispatches
to `_score_confidence_legacy()`, which never reads `htf_bias` at all. In the
live path today the two readings land in **two different scores**:

- `quality.score_plan` → `component_htf` → **15 points** aligned / 0 opposed,
  inside the 0–100 plan-quality score rendered in the embed breakdown.
- `score_confidence` → **−15 raw points** via `HTF_COUNTER_TREND_PENALTY`
  (`engine.py:999`), enough to drop a level and thus fall below
  `MIN_ALERT_CONFIDENCE_LEVEL`.

**`factor_htf` is not the second half — it is inert.** It is defined in
`scanning/factors.py` but never registered: `factors.py:396-398` reads
`FACTORS[:] = [factor_gap,]`, v32's own outcome. So `factor_htf` contributes
**zero regardless of whether `UNIFIED_CONFIDENCE` is on or off**, and
switching that flag on would not create a +15/−15 collision inside one
score. It would take a future re-weighting spec re-registering `factor_htf`
for that to become possible.

The plan's framing — "one signal is worth 15 raw points *plus* a factor
score" — is therefore right about the *count* and wrong about the *place*.
The real, live double-count is `component_htf`'s 15 points in the
plan-quality score plus the penalty's −15 on the confidence score: two
scores, one boolean, paid for twice. That is what Decision 2 rests on, and
it holds at today's flag settings without depending on `UNIFIED_CONFIDENCE`
at all.

---

## The four decisions

### Decision 1 — `get_htf_bias` **survives**, with one consumer instead of two.

*The question: does it survive at all, given the adjacent check covers the
same idea with per-horizon EMAs and no unmapped-horizon hole?*

The question's two grounds for retiring it both fail on measurement:

- **It is not redundant with the adjacent check.** Cramér's V = **0.3348**
  (n=4048), less than half the 0.7 collapse threshold. They disagree on 269
  of 4048 scenarios. The collapse rule does not reach this pair.
- **The unmapped-horizon hole does not exist.** `htf_none = 0` of 4337
  (Premise A). Deleting `get_htf_bias` to close a hole would be deleting it
  to close a hole that was closed in July.

But its win-rate lift is **not measurable on this population**: +12.8pp with
Wilson intervals that overlap ([43.9, 47.4] vs [22.8, 44.7]), on
`n_oppose = 67` evaluated trades — an absence of evidence, not evidence of
absence.
It opposes on 127 of 4337 scenarios (2.9%), which is too rare a firing to
move win rate or alert volume in either direction. v32 measured the same
signal on the same population and dropped it for the same reason.

**So: keep the function, its `htf` quality component and its embed label —
and delete its second, punitive consumer.** The signal is cheap (one EMA off
already-fetched daily bars), genuinely independent of the new adjacent check,
covers all ten horizons including the `9m` the adjacent check cannot reach,
and a counter-trend *warning* is honest information for a human reader. What
it has not earned is the right to be paid for **twice** — once as a
component and again as a suppressor. Decision 2 removes the second copy.

To be unambiguous for Task 6: `component_htf` (`quality.py:25`) **stays at its
current 15 points** in the plan-quality score, and `factor_htf`
(`factors.py:284`) **stays defined and unregistered** — it is already inert,
because `FACTORS[:] = [factor_gap,]`, so it scores 0 today whatever
`UNIFIED_CONFIDENCE` is set to. This document re-weights neither and
registers neither. Their lift is unmeasured on this population rather than
measured-and-zero, and re-weighting the merged factor set on TRAIN is
explicitly a future spec's job per v32's close-out, not a side effect of this
reconciliation.

`_HTF_EMA_PERIOD` needs **no change**. Task 6 Step 3's conditional ("if it
was kept, extend `_HTF_EMA_PERIOD` to cover all ten horizons") is already
satisfied in code; only the stale docstring at `regime.py:53` needs fixing.

### Decision 2 — `HTF_COUNTER_TREND_PENALTY` is double-counting. **Retire the penalty.**

*The question: if `get_htf_bias` survives, is the penalty double-counting
it?*

**Yes, at Cramér's V = 1.0000 on n = 4337** — the only pair of fifteen above
the 0.7 threshold, and the plan's rule mandates a collapse.

This is not a strong correlation that might weaken out of sample. It is an
identity. `penalty_fired` is *defined* at `engine.py:995` as
`htf_result is not None and htf_result["bias"] != scenario.direction`,
i.e. exactly `not htf_agree`. The instrumentation confirms it holds with no
exceptions: **`penalty_fired != (not htf_agree)` in 0 of 4337 rows.** The
contingency table has only two non-empty cells
(`{False|True: 127, True|False: 4210}`). There is no configuration of market
data in which these two readings can differ.

Note that the collapse itself does not depend on sample size or on the
lift measurement at all: `V = 1.0` here is a restatement of the source code,
so no larger or differently-shaped population could weaken it. This decision
is safe from the "entries, not market states" limitation above.

**Which half goes: the penalty.** Of the two consumers of the boolean, the
penalty is the one that costs something — −15 raw points, explicitly
calibrated in `config.py` to "drop a borderline Level 3 signal to Level 2
(and thus below the default `MIN_ALERT_CONFIDENCE_LEVEL=3` gate)". It
suppresses alerts outright. The `htf` component and the embed warning only
inform.

Given that the lift evidence is *absent* rather than *negative* (n=67
opposed; see the limitation in Methodology), the tie-break is asymmetry of
harm: keeping an unproven **label** costs a line of embed text, whereas
keeping an unproven **suppressor** silently deletes alerts that no
measurement says deserve deleting. When the pair must collapse and the
evidence cannot say which half is right, drop the half that can do damage.

The `htf` label and its quality component keep the reading visible to a
human without letting it silently gate an alert.

### Decision 3 — `mtf_alignment` adds nothing. **Retire it as a scored input** — but not for the reason the plan expected.

*The question: does the weekly `mtf_alignment` add anything over the
adjacent check? If Cramér's V > 0.7, keep one.*

**The collapse rule does not apply — and that is not a reprieve.** Cramér's
V vs `adj_agree` is **0.1163** (n=4048), the third-lowest of all fifteen
pairs; vs `own_agree` it is 0.0977, vs `macro_agree` 0.0317. `mtf_alignment`
is close to statistically independent of every EMA-based trend signal here.
That is unsurprising — it reads a different frame (weekly resample) with a
different construction (EMA10 slope+position, swing-low/high sequence,
prior-week pivot) — and it means the two are not measuring the same thing.

But independence is not value. What `mtf_alignment` adds, measured, is
**negative**: a −8.0pp lift with **non-overlapping** Wilson intervals
([41.8, 45.7] agree vs [47.9, 55.5] oppose), on healthy sample sizes
(n=2492 / n=658), plus a non-monotonic per-value table whose best bucket
(`mtf=1`, 53.3%, n=600) is the one the live `{0:0, 1:3, 2:6, 3:10}` map
scores nearly lowest. v32 independently dropped it on the same trades.

So it is retired for failing on its own terms, not for duplicating the
adjacent check. **Drop, do not invert** — repo precedent (v32's `RSI trend
alignment`, −0.056 and non-overlapping, dropped rather than flipped) is that
a sign discovered on TRAIN is a new hypothesis owing its own
pre-registration, not a free win.

Task 6 Step 4 should check `tracking/retrospective.py` as it says; the live
callers are `scanning/engine.py:547` (quality inputs) and `:981`
(confidence inputs), plus `tests/edge/test_edge_factors.py`.

### Decision 4 — `4m`,`5m`,`7m`,`8m`,`9m` **already have** higher-timeframe coverage. No `_HTF_EMA_PERIOD` change; fix the docs.

*The question: extend `_HTF_EMA_PERIOD` to all ten horizons, or let the
adjacent check replace `get_htf_bias` entirely?*

**Neither. The question rests on a stale premise** (Premise A above).
`_HTF_EMA_PERIOD` has covered all ten horizons since commit `512200e`
(2026-07-07). Measured across 4337 TRAIN scenarios, `get_htf_bias` returned
`None` **zero** times — including 0 of 373 on `4m`, 0 of 306 on `5m`, 0 of
404 on `7m`, 0 of 298 on `8m` and 0 of 288 on `9m`, the five horizons the
plan describes as having "no higher-timeframe signal at all today".

Concretely:

1. **No code change to `_HTF_EMA_PERIOD`.** It is already correct.
2. **Fix the stale docstring** at `regime.py:53` ("3m / 6m horizons →
   200-day EMA") to say all of `3m`–`9m` use the 200-day EMA. This docstring
   is the origin of the plan's error and will re-seed it if left.
3. **Correct line 70 of the plan** in the same commit as Task 6, so the
   claim is not carried into Tasks 7–8.
4. **The one real coverage gap belongs to the new check, not the old one:**
   `9m` has no horizon above it, exempting all 288 of its scenarios from the
   adjacent gate. `get_htf_bias` is the signal that *does* cover `9m`, which
   is an additional argument for Decision 1 keeping it alive rather than
   letting the adjacent check "replace it entirely".

---

## Summary of what Task 6 must do

| Signal | Decision | Action |
|---|---|---|
| `get_htf_bias` (`regime.py:46`) | **Keep** | No change to the function or `_HTF_EMA_PERIOD`. Fix the docstring at `:53`. Keep `HTF_CONFLUENCE_ENABLED`. |
| `HTF_COUNTER_TREND_PENALTY` | **Retire** | Remove the `if` block at `engine.py:999-1010` **only**, plus the `Field` at `config.py:415` and the embed sentence at `embeds.py:623-624`. **Keep** the `htf_counter_trend` boolean at `engine.py:995-998` — `:1018` and `:1046` still read it, and Decision 1 keeps the embed warning it drives. |
| `component_htf` (`planning/quality.py:25`) | **Keep** | Unchanged at 15 points. This is the **live** surviving half of the Decision 2 collapse. |
| `factor_htf` (`scanning/factors.py:284`) | **Keep, and leave unregistered** | Already inert — `FACTORS[:] = [factor_gap,]` (`factors.py:396-398`). Do **not** add it to `FACTORS` as part of this work; it contributes 0 today and re-registering it is a future re-weighting spec's decision, not Task 6's. |
| `mtf_alignment` (`edge/factors.py:88`) | **Retire** | Remove it, `factor_mtf` (`scanning/factors.py:264`), `mtf_points` (`quality.py`), and the `mtf=` call sites at `engine.py:547` and `:981`. Check `tracking/retrospective.py` first. |
| adjacent check | **Build** (Tasks 2–4) | Only signal with real positive lift. |

Two consequences worth flagging before Task 6 runs:

- Removing the penalty block also removes v32 Task 6 Step 6's
  `_rebucket_after_htf_penalty` fix, which exists only to serve it. The plan
  already anticipates this at Task 6 Step 2. `_rebucket_after_htf_penalty`
  and `ConfidenceResult.breakdown["htf_counter_trend_penalty"]` should go
  with it; check `retrospective.py:58` and `:863`, which name
  `HTF_COUNTER_TREND_PENALTY` as a tunable knob.
- `htf_info` / the `📉 Counter-trend signal` embed section (`embeds.py:614-627`)
  stays as a *warning* — Decision 1 keeps the label. Its last sentence
  ("confidence was reduced by `{config.HTF_COUNTER_TREND_PENALTY}` points to
  reflect this", `embeds.py:623-624`) must go: it would otherwise reference a
  deleted config field, so leaving it in place breaks embed rendering
  outright rather than merely leaving a stale sentence.

---

## Findings that are not this task's decisions, but gate later tasks

**The 6m macro anchor (Task 5) has no TRAIN support.** Measured as a
comparator: **+2.1pp lift, Wilson-overlapping** ([42.9, 47.1] agree vs
[30.8, 55.9] oppose), on `n_oppose = 56`. Its Cramér's V against every other
signal is low (0.0317–0.2930), so it is independent — and, like
`get_htf_bias`, independent without being useful. Task 5 registers
`factor_macro_alignment` into `FACTORS` at a provisional 10 points; on this
evidence that point value should be treated as **0 pending Task 7**, not as
a default to be trimmed. Task 5's own text already says the value is
provisional until Task 7 re-derives it; this measurement says Task 7 will
have to justify any non-zero value from scratch.

**The horizon's *own* trend is a better-powered signal than the adjacent
one.** `own_agree` measures +8.3pp with `n_oppose = 419` versus
`adj_agree`'s +9.0pp with `n_oppose = 200`, and the two are only moderately
associated (V = 0.5677). Task 7's sweep should carry own-horizon alignment
as a comparator arm, so the plan can tell whether the adjacent horizon is
doing work the trade's own horizon was not already doing more reliably.

**The adjacent gate's volume cost is comfortable in aggregate and nearly
over budget on `2w`.** This is the most actionable number in the document
for Task 4, and it is exactly the reason the plan insists on measuring per
horizon rather than in aggregate.

Aggregate, `adj_agree` is `False` on 283 of 4337 scenarios — **6.5%**, far
inside the plan's ≤~30% budget. Per horizon, that 6.5% is not distributed
anything like evenly:

| Horizon | n | adjacent opposed | **% cut by the gate** | `htf` opposed | 6m macro opposed |
|---|---|---|---|---|---|
| **2w** | 470 | 125 | **26.60%** | 3.19% | 2.77% |
| 4w | 827 | 47 | 5.68% | 3.39% | 2.18% |
| 2m | 543 | 21 | 3.87% | 4.24% | 2.39% |
| 3m | 528 | 17 | 3.22% | 2.08% | 2.65% |
| 4m | 373 | 10 | 2.68% | 2.95% | 3.75% |
| 5m | 306 | 11 | 3.59% | 2.61% | 3.59% |
| 6m | 300 | 11 | 3.67% | 3.00% | exempt |
| 7m | 404 | 24 | 5.94% | 1.98% | exempt |
| 8m | 298 | 17 | 5.70% | 2.35% | exempt |
| 9m | 288 | exempt | — | 2.43% | exempt |

**`2w` alone absorbs 125 of the 283 rejections — 44% of the gate's entire
volume cost falls on one horizon**, at 26.6% of its own scenarios, against
2.7–5.9% everywhere else. That is inside the ≤~30% budget but with under
4pp of headroom, on TRAIN, before VALIDATION.

It is **not** explained by the size of the EMA step between neighbours, and
that hypothesis should not be carried forward: `3m → 4m` is the largest jump
in the whole ladder (slow leg 50 → 100, 2.00×) and `3m` loses only 3.22%,
while `2w → 4w` is a middling 13 → 21 (1.62×). The more likely driver is the
*absolute* length of the neighbour's slow EMA — `4w`'s 21-day leg changes
direction often enough for "opposed" to be a reachable state, whereas a
250–350-day leg is close to permanently bullish across a net-bull
2020–2023 TRAIN window, so the long horizons can barely register opposition
at all. That is a hypothesis this measurement did not test, and the
non-monotonic tail (7m 5.94%, 8m 5.70%, against 4m 2.68%) says it is not the
whole story either.

What is not a hypothesis is the number. Task 4 should expect `2w` to be where
the gate either earns its keep or fails, and Task 7 must report `2w`
separately rather than let it average into an aggregate that looks safe. If a
per-horizon exemption or softer treatment for `2w` turns out to be needed,
that is Task 4's decision on Task 7's evidence — this document does not
pre-empt it, only flags that the constraint is close to binding on exactly
one horizon.

---

## Reproducing this

The instrumentation is committed as
**`scripts/backtest/measure_trend_signal_overlap.py`**, following
`measure_factor_lift.py`'s conventions (TRAIN-only, `--json` dump, one
flushed progress line per ticker). Every number in this document comes from
one run of it:

```bash
python scripts/backtest/measure_trend_signal_overlap.py --train \
    --json data/v33_trend_overlap.json
```

Roughly 7 minutes over the 75-ticker cache. It emits, in order: the EMA
precompute check, the 15-pair Cramér's V table, the six lift rows, the
`mtf_alignment` per-value table, the per-horizon opposition table, the
S2/S3 identity check, and the `htf`-vs-`adj` disagreement count — i.e. every
table above.

Two things worth knowing before running it:

- **From a git worktree, pass `--cache-dir`.** `data/` is gitignored, so a
  worktree gets its own empty `data/backtest_cache/`; point the flag at the
  main checkout's cache. The script exits non-zero with that hint rather
  than reporting an empty result.
- **The EMA precompute is verified, not assumed.** The run aborts before
  collecting anything if the full-series precompute disagrees with the real
  `get_htf_bias` on any sampled bar, because a disagreement would mean every
  `htf`/adjacent/macro number is lookahead-contaminated. `--verify-ema` runs
  that check alone. Both the smoke run and the full run reported
  `1230 sampled (horizon, bar) pairs, 0 mismatches`.

Re-running it on this branch reproduces this document exactly — the
committed script was run over the full cache and matched all 15 V values,
all six lift rows, the `mtf` per-value table and the per-horizon table to
the last digit. Note the environment caveat under Methodology: the *entry
set* is stable, but outcome resolution has been observed to drift slightly
with config/`.env` state, so a materially different pooled win rate on a
re-run points at environment, not at this script.
