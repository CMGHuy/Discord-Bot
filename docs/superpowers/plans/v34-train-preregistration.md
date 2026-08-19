# v34 TRAIN measurement and VALIDATION pre-registration

Task 7 of `docs/superpowers/plans/2026-08-16-v34-relative-strength-gate.md`.
Written before Task 8's VALIDATION run and **not to be revised after seeing its
result** — the same discipline
`docs/superpowers/plans/implemented/v32-train-preregistration.md` and
`docs/superpowers/plans/implemented/v33-train-preregistration.md` were held to.

---

## How the measurement was taken, and why not with the brief's command

Task 7's brief (and the plan's Task 8 Step 2) name
`scripts/backtest/tune_strategy.py` / `run_backtest_range.py`. **Neither can
measure this plan's work**, and neither was used:

- Both simulate trades through `swingbot.core.backtesting.backtest`, a replay
  harness. `tune_strategy.py` grids a *strategy's* entry-filter parameters and
  has no notion of `RS_LEADER_PERCENTILE` / `RS_LAGGARD_PERCENTILE` at all.
- v34's gate lives in `swingbot/core/scanning/engine.py` (`_sync_run_scan`'s
  per-item merge loop, Task 6), and its input `rs_combined` is set by
  `_apply_sector_rs` in that same loop. The replay harness never calls
  `scanning.engine`, so **the gate cannot influence its output by any code
  path**. This is the same structural gap that made
  `DATA_DRIVEN_STOPS_ENABLED` unmeasurable and burned its shot
  (`docs/claude/backtest-methodology.md`, closed pre-registrations).

**What was run instead**, following v33 Task 7's precedent exactly: a
purpose-built instrument, `scripts/backtest/measure_rs_gate_effect.py`, which
records per TRAIN trade entry bar the RS readings the gate keys on and then
**simulates the gate's real decision rule** on them.

```
python scripts/backtest/measure_rs_gate_effect.py --train \
    --cache-dir <main checkout>/data/backtest_cache \
    --json data/v34_train.json --rows-out data/v34_train_rows.json
```

**The simulated gate is the real gate.** `engine.py` drops an item iff
`rs_verdict(...)["status"] == "block"`; `rs_verdict` (`edge/rs_gate.py`) exempts
RS-ineligible symbols (index / fx / future, `marketdata/asset_class.py`), then
keeps a bullish setup iff `rs >= RS_LEADER_PERCENTILE` and a bearish setup iff
`rs <= RS_LAGGARD_PERCENTILE`. The instrument's `keeps()` is that rule with the
strings removed. Exempt is kept and is **not** counted as a pass.

**The RS readings are the real readings, checked rather than assumed.** The
instrument builds the cross-sectional percentile as a vectorized rank panel
rather than calling `rs_percentile` 4337 times, so it carries a guard
(`--verify-rs`) that asserts the panel reproduces the real
`edge/factors.py::rs_percentile` bar for bar before any number is computed:
**204 sampled (symbol, bar) pairs, 0 mismatches**, on every run below. The run
aborts on any mismatch.

**NO-LOOKAHEAD:** every reading at entry bar `d` is `Close[d]/Close[d−W] − 1`
minus SPY's over the same `W` bars. Nothing after `d` is touched; nothing is
resampled or forward-filled.

**Data.** `data/backtest_cache/` had no `SPY.csv` and no sector ETFs, so RS was
not computable from it at all. `SPY` plus the 13 sector/thematic ETFs in
`data/universe/etfs.json` were fetched into it (2018-06-01..2025-12-30, 1906
bars each) before the run. Consequence worth recording: any script that globs
`*.csv` out of that cache now sees 89 files rather than 75, so this instrument
takes its scenario universe from `data/watchlist.json` instead — SPY and the
ETFs are *inputs*, not subjects.

**Which RS window.** The live path computes `rs_pctile` **once per ticker with
the flat `RS_WINDOW = 63`** (`engine.py:958`) for every horizon;
`HORIZONS[hk]["rs_window"]` (Task 3) currently has **zero consumers**. So the
shipped gate is a 63-day gate, and the 63-day arm is the primary measurement.
The per-horizon-window arm is reported as secondary evidence only.

**Population: 4337 TRAIN scenarios**, 2020-01-01..2023-12-31, 75 tickers × 10
horizons × 11 strategies, ungated **45.37% [43.6, 47.1]** (1429 / 3150).
That is **v33's published population and baseline to the decimal** — an
independent cross-check that this instrument measures the same thing v33's did,
using a separately written collector.

Win rate is **wins / (wins + losses)** throughout — `backtest.py`'s own
convention, scratch and timeout excluded. "Scenarios" counts every row
*including* scratch/timeout, because the gate drops a scenario before its
outcome is known: that count, not the evaluated one, is the alert-volume cost.
Every table prints scenarios / evaluated / wins so each win rate and Wilson
interval is recomputable from this document alone.

`E[R]` is mean `r_multiple` over **all** closed trades (the methodology's
`expectancy_r` gate), reported alongside win rate throughout.

**The dumps are gitignored on purpose** (`data/v34_*.json`, added to
`.gitignore` in this commit for the same reason as the v32 and v33 globs:
`data/` is bind-mounted into the running containers, so a committed dump under
it breaks CI's `git reset` on the deploy host). This **overrides the brief's
Step 6 `git add data/v34_train.json`**, exactly as v33's pre-registration
overrode its own.

**"Alert volume" means backtest trade _entry_ volume — a proxy for production
alert volume, not equal to it,** and the `MIN_ALERT_CONFIDENCE_LEVEL = 4`
condition in the brief's template is dropped for the same structural reason
v33 dropped it: these rows carry no confidence score, because a confidence
level is produced by `scanning.engine` + `run_factors` on live scan scenarios
and this population comes from the replay harness. The condition could not be
honoured, only pretended to. It is also orthogonal: the RS gate runs *before*
scoring (`attach_plan_v2` is called a few lines below it), so testing it on the
unscored population measures the gate rather than the interaction of two
filters.

---

## The selection rule, stated before the grid was read

Committed in the instrument's docstring before any cell was looked at:

1. **The two arms are independent by construction.** The bullish keep rule
   reads only `leader`; the bearish keep rule reads only `laggard`. The 25-cell
   grid is literally the outer product of two 5-cell sweeps, so each threshold
   is chosen from its own arm.
2. Within an arm: among thresholds inside the volume budget, take the largest
   ΔWR; ties to the lower volume loss.
3. **If an arm's best ΔWR ≤ 0, that arm gets no gate.** A one-sided gate is an
   allowed outcome, not a failure to finish.
4. Wilson separation is **reported, never used to select**.
5. **Sector RS is kept only if `rs_combined` beats ticker-only `rs_percentile`**
   at the chosen thresholds. Otherwise Task 5's wiring is reverted — shipping
   unused wiring is the pattern this spec family exists to stop.

### One disclosed conflict between two pre-registered rules

The instrument's docstring applied the ≤30% volume budget **per arm**; the
plan's own Global Constraints state it as an **aggregate** budget
("Alert-volume loss ≤ ~30%"). That is a transcription error in the instrument,
not a post-hoc change, and it is resolved here in favour of **the plan's
aggregate budget** — the earlier and more authoritative pre-registration.

Both readings are reported below and **both select a bearish-only gate**. They
differ only in the laggard value: the per-arm reading selects **40**, the
aggregate reading selects **25**. The aggregate reading is adopted, and it is
also the only one that satisfies the plan's standing directive to *"prefer a
TRAIN effect that is Wilson-separated before spending the VALIDATION shot"*.
A reader who prefers the stricter per-arm reading can score this document
against `laggard=40` from the tables below without re-running anything.

---

## Step 1 — the 5×5 threshold grid, on `rs_combined`, 63-day window

Whole population, both arms live. `cut` is against 4337 scenarios; ΔWR is
against the ungated 45.37%.

| L\G | 25 | 30 | 35 | 40 | 45 |
|---|---|---|---|---|---|
| **55** | 37.12% / +3.83pp | 35.39% / +2.34pp | 34.15% / +1.59pp | 32.93% / +0.97pp | **31.57% / +0.34pp** |
| **60** | 42.82% / +3.05pp | 41.09% / +1.45pp | 39.84% / +0.65pp | 38.62% / −0.01pp | 37.26% / −0.67pp |
| **65** | 49.90% / +3.99pp | 48.17% / +2.15pp | 46.92% / +1.23pp | 45.70% / +0.47pp | 44.34% / −0.29pp |
| **70** | 59.33% / +4.12pp | 57.60% / +1.93pp | 56.35% / +0.85pp | 55.13% / −0.04pp | 53.77% / −0.91pp |
| **75** | 66.91% / +2.46pp | 65.18% / −0.09pp | 63.94% / −1.32pp | 62.72% / −2.30pp | 61.36% / −3.26pp |

(each cell: aggregate volume cut / ΔWR. **No cell is Wilson-separated.**)

**The headline result of Step 1 is a negative one: a symmetric gate is not
shippable at any threshold in the pre-registered grid.** The cheapest cell in
the entire grid (55/45) cuts **31.57%** of alert volume, already past the
plan's ≤~30% budget, and buys +0.34pp. The best-ΔWR cell (70/25, +4.12pp) costs
**59.33%** of volume — twice the budget. There is no corner of this grid where
the symmetric gate is affordable.

That is not a near miss to be argued around. It is the answer to the question
the grid was run to ask.

## Step 2 — the two arms, reported separately

The arms behave nothing alike, so a single "the gate does X" statement would be
false in both directions.

### Bullish arm (n = 3675 scenarios, ungated 48.09% [46.2, 50.0], E[R] +0.271)

| leader | after: scen / eval / wins | WR after | arm cut | ΔWR | ΔE[R] | separated? |
|---|---|---|---|---|---|---|
| 55 | 2437 / 1811 / 889 | 49.09% [46.8, 51.4] | 33.69% | +1.00pp | +0.044 | no |
| 60 | 2190 / 1629 / 785 | 48.19% [45.8, 50.6] | 40.41% | +0.10pp | +0.035 | no |
| 65 | 1883 / 1403 / 691 | 49.25% [46.6, 51.9] | 48.76% | +1.16pp | +0.069 | no |
| 70 | 1474 / 1136 / 561 | 49.38% [46.5, 52.3] | 59.89% | +1.30pp | +0.080 | no |
| 75 | 1145 / 893 / 422 | 47.26% [44.0, 50.5] | 68.84% | −0.83pp | +0.035 | no |

**Scored the way it would actually ship** — bullish-only gate, whole
population, against the 45.37% baseline:

| leader | scen | aggregate cut | WR | ΔWR | separated? |
|---|---|---|---|---|---|
| 55 | 3099 | 28.55% | 45.21% [43.2, 47.2] | **−0.16pp** | no |
| 60 | 2852 | 34.24% | 44.20% [42.1, 46.3] | −1.16pp | no |
| 65 | 2545 | 41.32% | 44.51% [42.3, 46.7] | −0.86pp | no |
| 70 | 2136 | 50.75% | 43.84% [41.5, 46.2] | −1.53pp | no |
| 75 | 1807 | 58.34% | 41.57% [39.0, 44.1] | −3.80pp | no |

**A bullish-only gate is negative at every threshold in the grid.** The
within-arm gains are entirely an artefact of changing the bullish/bearish mix:
the bullish arm wins 48.09% and the bearish arm 32.09%, so *any* filter that
removes bullish scenarios drags the pooled win rate down. `leader = 55` is the
only threshold that even fits the aggregate budget (28.55%), and it costs
0.16pp of win rate for that 28.55%.

The bullish effect is also not robust to how RS is computed. On ticker-only
`rs_percentile` the same arm runs **−0.72 / −2.00 / −1.92 / −1.57pp** at
60/65/70/75, and on the per-horizon-window arm it is negative at **every**
threshold (−0.39 to −3.99pp). A signal that changes sign when you change the
lookback or drop the sector blend is not a signal.

**Decision: no bullish gate.**

### Bearish arm (n = 662 scenarios, ungated 32.09% [28.3, 36.2], E[R] −0.030)

| laggard | after: scen / eval / wins | WR after | arm cut | ΔWR | ΔE[R] | separated? |
|---|---|---|---|---|---|---|
| **25** | 290 / 234 / 117 | **50.00% [43.6, 56.4]** | 56.19% | **+17.91pp** | +0.461 | **YES** |
| 30 | 365 / 304 / 120 | 39.47% [34.1, 45.1] | 44.86% | +7.38pp | +0.205 | no |
| 35 | 419 / 342 / 122 | 35.67% [30.8, 40.9] | 36.71% | +3.58pp | +0.107 | no |
| 40 | 472 / 384 / 128 | 33.33% [28.8, 38.2] | 28.70% | +1.24pp | +0.042 | no |
| 45 | 531 / 425 / 133 | 31.29% [27.1, 35.9] | 19.79% | −0.80pp | −0.013 | no |

**Scored the way it would actually ship** — bearish-only gate, whole
population, against the 45.37% baseline:

| laggard | scen | aggregate cut | eval / wins | WR | ΔWR | separated? |
|---|---|---|---|---|---|---|
| **25** | 3965 | **8.58%** | 2848 / 1374 | **48.24% [46.4, 50.1]** | **+2.88pp** | no |
| 30 | 4040 | 6.85% | 2918 / 1377 | 47.19% [45.4, 49.0] | +1.82pp | no |
| 35 | 4094 | 5.60% | 2956 / 1379 | 46.65% [44.9, 48.5] | +1.29pp | no |
| 40 | 4147 | 4.38% | 2998 / 1385 | 46.20% [44.4, 48.0] | +0.83pp | no |
| 45 | 4206 | 3.02% | 3039 / 1390 | 45.74% [44.0, 47.5] | +0.37pp | no |

Three things about this arm, in order of how much weight they deserve:

1. **It is monotone.** −0.80 → +1.24 → +3.58 → +7.38 → +17.91pp as the
   threshold tightens, with no reversals, and E[R] tracks it (−0.013 → +0.461).
   A single lucky cell would not do that; a dose-response gradient is the
   signature of a real effect. The same gradient shows up on ticker-only RS
   (−1.20 / +0.74 / +1.76 / +4.38 / +6.52pp), i.e. it does not depend on the
   sector blend for its existence, only for its size.
2. **`laggard = 25` is the only Wilson-separated result anywhere in this
   measurement** — bearish 32.09% [28.3, 36.2] → 50.00% [43.6, 56.4], intervals
   disjoint. It also turns the arm's expectancy from negative to strongly
   positive (E[R] −0.030 → +0.431), which is the methodology's second
   acceptance gate.
3. **That separation does not survive dilution, and must not be oversold.**
   The gate only acts on 15.3% of scenarios, so on the *whole* population the
   same configuration is +2.88pp with **overlapping** intervals (45.37%
   [43.6, 47.1] → 48.24% [46.4, 50.1]). The honest statement is: *RS
   discriminates among bearish setups on TRAIN with a separated interval; the
   bot-level effect of acting on that is a +2.88pp point estimate that is not
   statistically demonstrated.* It is a better starting position than v33 took
   into VALIDATION (+0.57pp, overlapping, on a 6.53% cut) — but it is the same
   *kind* of position, and v33 FAILed.

**Decision: bearish-only gate at `laggard = 25`.** Under the per-arm budget
reading it would be `laggard = 40` (+0.83pp whole-population, not separated);
that alternative is recorded here and is the one number to re-read if the
aggregate-budget resolution above is judged wrong.

### Per-horizon cost and effect of the frozen configuration (`laggard = 25`)

The v33 lesson — an aggregate that hides one horizon paying most of the bill —
does not repeat here. Every horizon is inside the budget and every horizon
moves the same way.

| Horizon | before: scen / eval / wins | WR before | after: scen / eval / wins | WR after | cut | ΔWR |
|---|---|---|---|---|---|---|
| `2w` | 470 / 337 / 144 | 42.73% | 433 / 308 / 136 | 44.16% | 7.87% | +1.43pp |
| `4w` | 827 / 571 / 243 | 42.56% | 740 / 504 / 227 | 45.04% | 10.52% | +2.48pp |
| `2m` | 543 / 391 / 179 | 45.78% | 507 / 362 / 173 | 47.79% | 6.63% | +2.01pp |
| `3m` | 528 / 397 / 187 | 47.10% | 499 / 372 / 181 | 48.66% | 5.49% | +1.55pp |
| `4m` | 373 / 276 / 129 | 46.74% | 338 / 247 / 124 | 50.20% | 9.38% | +3.46pp |
| `5m` | 306 / 234 / 109 | 46.58% | 274 / 206 / 105 | 50.97% | 10.46% | +4.39pp |
| `6m` | 300 / 220 / 100 | 45.45% | 270 / 195 / 98 | 50.26% | 10.00% | +4.80pp |
| `7m` | 404 / 293 / 138 | 47.10% | 375 / 269 / 135 | 50.19% | 7.18% | +3.09pp |
| `8m` | 298 / 214 / 101 | 47.20% | 269 / 191 / 98 | 51.31% | 9.73% | +4.11pp |
| `9m` | 288 / 217 / 99 | 45.62% | 260 / 194 / 97 | 50.00% | 9.72% | +4.38pp |
| **ALL** | **4337 / 3150 / 1429** | **45.37%** | **3965 / 2848 / 1374** | **48.24%** | **8.58%** | **+2.88pp** |

All ten horizons positive, cuts between 5.49% and 10.52%, no horizon anywhere
near the budget. (The `before` column reproduces v33's per-horizon table
row-for-row, which is the cross-check that both instruments see one
population.)

### Robustness of the bearish finding — where it does and does not come from

Cut on the row cache (`data/v34_train_rows.json`), over the 652 **eligible**
bearish scenarios (10 of the 662 are RS-exempt and always kept):

**The verdict discriminates, it does not merely shrink the sample.** Kept
(RS ≤ 25) 52.0% [45.5, 58.4] on 225 evaluated, versus dropped (RS > 25)
**18.2% [14.3, 23.0]** on 302 evaluated. Those intervals are far apart. The
gate is not thinning a population at random; the scenarios it removes lose
four times out of five.

**By year** — not one regime:

| Year | bearish scen | WR off | kept | WR on | Δ |
|---|---|---|---|---|---|
| 2020 | 65 | 28.8% | 33.8% | 61.9% | +33.1pp |
| 2021 | 1 | — | — | — | (no bearish population) |
| 2022 | 450 | 34.9% | 40.7% | 52.9% | +18.1pp |
| 2023 | 136 | 25.7% | 54.4% | 43.8% | +18.0pp |

Three separate years, same sign, comparable magnitude. 2021 produced a single
bearish scenario in the whole 75-ticker universe, which is its own comment on
that year.

**By strategy — this is the finding's main weakness, and it is stated rather
than buried.** Only 4 of the 11 strategies generate bearish signals at all, and
**RSI Divergence alone is 473 of the 652 (72.5%)**:

| Strategy | scen | WR off | kept | WR on | Δ |
|---|---|---|---|---|---|
| RSI Divergence | 473 | 31.7% [27.3, 36.5] | 230 | **55.2% [48.0, 62.3]** | +23.5pp |
| Break & Retest | 77 | 27.1% | 18 | 44.4% | +17.3pp |
| Elliott Wave | 68 | 29.4% | 27 | 38.1% | +8.7pp |
| EMA Crossover | 34 | 65.4% | 5 | 20.0% | −45.4pp |

Three of four point the same way and the dominant one separates on its own
intervals; the one that points the other way has **5** kept scenarios, which is
noise. But the honest reading is that this measurement is substantially a
statement about **RSI Divergence shorts**, because that is what the bearish
population mostly is. A VALIDATION PASS would inherit that same caveat, and
Task 8 must repeat it rather than describe the gate as strategy-neutral.

**By ticker:** 32 distinct tickers carry the kept scenarios; the top three
(SHOP, ASTS, MRNA) account for 32.1%. Concentrated, but not a handful.

**Why the direction is the opposite of the brief's guess.** The brief
anticipated "if bearish shows no measurable RS effect, ship bullish-only". The
data says the reverse, and the mechanism is legible: TRAIN
(2020-01-01..2023-12-31) is a mostly-rising market in which short setups won
32% of the time overall. Requiring a short to be a genuine relative laggard
— not merely below the median — is the condition under which shorts stopped
being a losing proposition (50.00%, E[R] +0.431). Requiring a long to be a
relative leader in a market where most things went up filtered on a
characteristic almost everything shared, and paid a third of alert volume for
it.

## Step 3 — sector RS's marginal contribution

Same population, same thresholds, the only change being the value the gate
reads: `rs_combined` = `rs_score(ticker, sector)` = 0.7/0.3 (Task 5) versus the
bare `rs_percentile` (ticker only).

| Arm / threshold | with sector (`rs_combined`) | ticker only (`rs_percentile`) |
|---|---|---|
| bearish, laggard 25 | **+17.91pp, SEPARATED**, arm cut 56.19% | +6.52pp, not separated, arm cut 44.86% |
| bearish, laggard 30 | +7.38pp | +4.38pp |
| bearish, laggard 35 | +3.58pp | +1.76pp |
| bearish, laggard 40 | +1.24pp | +0.74pp |
| bearish, laggard 45 | −0.80pp | −1.20pp |
| bullish, leader 55 | +1.00pp | +0.05pp |
| bullish, leader 60 | +0.10pp | −0.72pp |
| bullish, leader 65 | +1.16pp | −2.00pp |
| bullish, leader 70 | +1.30pp | −1.92pp |
| bullish, leader 75 | −0.83pp | −1.57pp |

**Decision: sector RS is KEPT. Task 5's wiring is not reverted.**
`rs_combined` beats ticker-only RS at **every one of the ten thresholds**, on
both arms, and the gap is decisive exactly where the gate ships: at the frozen
`laggard = 25` the sector blend is the difference between a separated +17.91pp
and an unseparated +6.52pp. `_apply_sector_rs`, `_sector_etfs_for_tickers`,
`_fetch_frames`, `_etf_symbol_of_sector` and the `ScanItem.sector_rs_percentile`
/ `rs_combined` fields stay, and the gate keeps reading `item.rs_combined`.

This was a live revert branch, not a formality: the plan required the wiring to
be deleted if it could not show measurable value, and the measurement was set
up to be able to say so. It did not.

### Secondary, for a future spec only: the per-horizon RS window stays dormant

`HORIZONS[hk]["rs_window"]` (Task 3) has no live consumer. Measured as an arm
anyway, it is **worse** than the shipped flat 63-day window on the bullish side
at every threshold (−0.39 / −0.96 / −0.83 / −2.57 / −3.99pp vs the 63-day arm's
+1.00 / +0.10 / +1.16 / +1.30 / −0.83pp). **No case for wiring it in.** It
stays a defined-but-unused key, and Task 8's documentation should say that
plainly rather than leave a reader to assume it is live.

## Step 4 — does the TRAIN window span a leadership rotation?

**Yes, repeatedly — measured, not asserted.** An RS gate is procyclical: it is
most confident about a leader immediately before that leader stops leading, so
a window containing a single stable leadership regime would flatter it. The
instrument's `--rotations-only` mode reports, per calendar quarter, which
sector ETF leads on 63-day relative return:

| | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| **2020** | XLK | XLE | XLY | XLE |
| **2021** | XLE | XLK | XLF | XLK |
| **2022** | XLE | XLP | XLY | XLE |
| **2023** | XLK | XLK | XLE | XLK |

**13 leadership changes across 16 quarters, 5 distinct leaders (XLE, XLF, XLK,
XLP, XLY).** TRAIN 2020-01-01..2023-12-31 (`docs/claude/backtest-methodology.md`)
contains the COVID crash and the mega-cap-tech regime, the November-2020
rotation into value and cyclicals, 2022's complete energy-led inversion, and
2023's return to tech leadership. A gate measured on this window is measured
*across* regime changes, not inside one, so the procyclicality objection does
not apply to this measurement.

VALIDATION's rotation profile is deliberately **not** examined here — that
window stays untouched until Task 8's single shot.

---

## VALIDATION pre-registration

**Task 8 must run this, not `run_backtest_range.py`** — see the first section
for why that script cannot see the gate. The plan's Task 8 Step 2 instruction
is superseded by this pre-registration:

```
python scripts/backtest/measure_rs_gate_effect.py --validation \
    --cache-dir <main checkout>/data/backtest_cache --json data/v34_validation.json
```

**Frozen configuration under test** (already committed in `swingbot/config.py`
by this task):

- `RS_LEADER_PERCENTILE = 0` — **the bullish arm is not gated.**
  `rs_verdict`'s bullish branch keeps a setup iff `rs_value >= 0`, and a
  percentile is never negative, so `0` disables that arm without touching
  `rs_gate.py`'s logic. This is the Step 2 decision expressed in the one file
  Task 7 is allowed to change, rather than left as a note for someone to
  implement later.
- `RS_LAGGARD_PERCENTILE = 25`.
- `RS_GATE` stays `default="false"`. Only a PASS may flip it, and only in
  Task 8.
- Sector RS **included** (`rs_combined`), per Step 3.
- Window: the shipped flat `RS_WINDOW = 63`. The per-horizon key stays
  dormant and is not under test.
- Scope: **all 10 horizons**, bearish scenarios only. Non-equities stay
  exempt, and an exemption is not a pass.

- **Primary:** win rate (wins / (wins + losses)) over VALIDATION
  2024-01-01..2025-12-31, **gate on vs. gate off on the same population** —
  `combined_w63.bearish_only_whole_population["25"].after.wr` vs `.before.wr`
  in the emitted JSON. The comparator is the ungated same-window population,
  not v32's or v33's numbers: the gate is a filter over a population, so the
  only like-for-like baseline is that population unfiltered.

- **PASS** requires **both**:
  1. `after.wr` **>** `before.wr` (strictly; equal is a FAIL), **and**
  2. `volume_loss_pct` **≤ 30.0** on the whole population.

- **FAIL:** either unmet.

- **Mandatory reporting conditions** (they do not change the PASS bar):
  1. Report whether the whole-population before/after Wilson intervals are
     separated. On TRAIN they were **not** (+2.88pp, overlapping). If they are
     not separated on VALIDATION either, `docs/strategy.md` must describe the
     gate as a **small, not statistically demonstrated** improvement. A PASS on
     point estimate alone may flip the flag on; it may not be written up as a
     proven edge.
  2. Report the **bearish-arm** before/after separately, including whether its
     intervals separate. TRAIN's one separated result lives there (32.09% →
     50.00%), and whether that reproduces is the single most informative thing
     VALIDATION can say about this gate — but it is *reporting*, not a pass
     bar, because the bot-level question is the pooled one.
  3. Report `E[R]` before and after. TRAIN moved the bearish arm from −0.030 to
     +0.431 (whole population +0.225 → +0.283); a PASS on win rate with a
     *falling* expectancy must be said out loud.
  4. Report the **strategy composition of the VALIDATION bearish arm**. On
     TRAIN it was 72.5% RSI Divergence, so the result is largely a statement
     about one strategy. Task 8 must say so rather than write the gate up as
     strategy-neutral.

**Reproducibility, checked rather than assumed.** The TRAIN sweep was run
twice, independently, and both runs report the identical population (4337
scenarios, 3675 bullish / 662 bearish, 64 exempt, 0 synthetic-50, 523 without
a sector ETF) and identical tables. The RS-panel guard passed on both (204
sampled pairs, 0 mismatches). The second run additionally wrote
`data/v34_train_rows.json`, so the analysis above can be re-cut with
`--rows-in` in seconds without re-taking the measurement.

- **One shot.** Task 8 runs it once and records the result verbatim, PASS or
  FAIL. **No re-runs on FAIL**, no threshold change, no scope change, no
  "double check" after seeing the number. A FAIL means `RS_GATE` stays
  `default="false"` and no `VERSION.json` bump is earned.

### What this document already concedes, before the shot is spent

- **A symmetric gate is dead on TRAIN**, at every threshold in the
  pre-registered grid, on the plan's own volume budget. VALIDATION is not being
  asked about it.
- **A bullish gate is dead on TRAIN**, negative at every threshold when scored
  the way it would ship. VALIDATION is not being asked about it either.
- **The surviving hypothesis is narrow**: that requiring a bearish setup to sit
  in the bottom quartile of combined relative strength improves the bot's
  pooled win rate. TRAIN says +2.88pp for an 8.58% volume cut, with overlapping
  pooled intervals and a separated bearish-arm interval.
- **Two consecutive predecessors FAILed this exact shape of shot** (v32's
  merged score, v33's adjacent gate), both with favourable-looking TRAIN point
  estimates and overlapping intervals that reversed sign in VALIDATION. This
  gate goes in with a larger TRAIN point estimate, a cheaper volume cost, a
  monotone dose-response across five thresholds, and one separated interval —
  which is a better hand than either predecessor held, and still not a
  prediction of a PASS.
