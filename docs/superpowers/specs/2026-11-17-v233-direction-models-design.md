# v233 — Direction models: a LONG meta-labeler, a SHORT meta-labeler and a budget allocator, in shadow

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** bot minor (every alert gains one labelled shadow-score line); ui minor (a new "Direction models" panel in the Research workspace and the same line on the plan page)
**Edge:** none (integrity). An instrument: a dataset, two per-direction models, an allocator and their shadow record. Nothing it builds skips, sizes or blocks a trade. Any lift is claimed later, by Spec 2's pre-registration on the 2026 holdout.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-11-17 from a brainstorm with the partner; every decision in `## Partner decisions` was made in chat the same day. Panel review applied the same day (`## Panel review`). Plans queue behind v230 and v232 (both mid-write) — see `## Constraints`.

## Why

The partner asked how to train LONG and SHORT separately so the bot knows
which direction to issue and stops issuing longs into a bear market (and
shorts into a bull market).

Three facts shape the answer:

1. **There is no learned decision-maker today.** "Training" in this repo
   means per strategy × direction parameter grids and badge tiers
   (`strategy_types.py` admits each direction separately). Nothing reads
   the market context or the stock's context at alert time and decides
   whether this candidate, in this direction, is worth issuing.
2. **Neighbouring ideas are closed, and this spec re-tests none of them.**
   - v17 `REGIME_ALLOW` (per strategy × regime allow lists): ledger row
     `v17-regime-allow`, NO-LIFT, 0 of 44 cells. A bull_volatile veto was
     examined again on 2026-11-12 and would not clear the screen.
   - v146 "Confidence score as a ranker": NOT PREDICTIVE
     (`backtest-methodology.md` § Closed pre-registrations — do not re-run
     these).
   - v32/v33 blended confidence scores: both regressed.

   What differs here: the models are fitted per direction on outcomes (not
   hand-weighted points), are additive with no strategy × regime
   interaction terms (so no allow list is re-derived), and the allocator
   never takes a direction below a 15% floor. These priors still say a
   score built from context features has failed before; that is why this
   spec claims nothing and Spec 2 gets one shot on the holdout.
3. **Both directions lose in the live book** (v231 Finding 1, autopsy
   2026-11-16, exploratory because it overlaps the 2026 holdout): bullish
   N=747 net ExpR −0.067, bearish N=320 net ExpR −0.136. A perfect
   direction switch alone would only move risk between two losing books.
   The decision has to improve **which candidates are issued inside each
   direction** as well as **how the budget is split between directions**.

v231 (2026-11-16) builds the measuring side: per-direction book gates,
`PROVEN`/`UNPROVEN` status and a regime split that never gates. Its "What
follows" item 3 anticipates a regime-switch feature per direction. This spec
builds the decision side that v231 will measure.

## Partner decisions (2026-11-17)

1. **Layered.** An allocator splits the risk budget between LONG and SHORT
   each day; inside its share, a per-direction meta-labeler decides which
   candidates are worth issuing.
2. **Train on replay, walk-forward.** The live book is never trained on; it
   is the out-of-sample realism check.
3. **Two heads per direction.** P(win) and the average win and loss size,
   combined into EV = P·W − (1−P)·L. Win rate is a guardrail, not the
   objective.
4. **The allocator blends market state with model votes.** Top-down market
   features plus how many high-EV candidates each direction's model sees
   today, with hysteresis.
5. **Rollout: shadow, annotate, gate.** Gating is per direction, only after
   a pass under v231 `--gate direction`.
6. **L2-regularised logistic first.** A shallow monotone gradient-boosted
   comparator runs alongside and must beat it out of sample.
7. **Split around the screen rule.** This spec is the instrument (`Edge:
   none`, `Screen: exempt`). Spec 2 pre-registers the frozen models as a
   filter; that pre-registration stands in for the idea screen, which tests
   single frozen conditions and cannot take a trained model.
8. **Shared mirrored core plus 2–4 extras per direction**, all frozen before
   the first fit.
9. **Soft tilt, 85/15 to 15/85.** The minority side never goes to zero; its
   EV bar rises as its share shrinks.
10. **Training rows: as-issued plans and rejected plans, weighted** toward
    as-issued (narrowed by the panel to plans that exist; see Part A).
11. **Frozen, hashed model versions** with a champion/challenger mechanism
    (the scheduled refit is deferred by the panel; see Part C).
12. **Visibility in Spec 1:** the Research panel, plus a one-line score on
    every alert and plan page labelled "unvalidated".
13. **Approach A: three plans in order** (dataset → models → live surface).

## Goals

1. A lookahead-clean, checkpointed replay dataset with one row per LONG and
   SHORT plan: as-of features, a weight, and the outcome under the v3 fill
   and exit model net of every friction, borrow included.
2. Per direction: a walk-forward fitted P(win) head and a win/loss-size
   head, with per-fold results that say plainly how the model's take subset
   compares with the unfiltered book.
3. An allocator that turns market state and model votes into a daily
   LONG/SHORT budget split, with its own walk-forward result against a
   fixed 50/50 split and a per-episode view of the regime turns.
4. Live shadow scoring of every issued alert and of every day's tilt,
   joined to outcomes, visible on bomeo-capital.com and on each alert.
5. One frozen champion hash per direction, plus the allocator hash, ready
   for Spec 2 to pre-register on the 2026 holdout.

## Non-goals

- Skipping, resizing or blocking any trade. That is Spec 2, per direction,
  after a pass.
- Any change to the strategies, plan builders, the 2% dollar-risk cap,
  heat accounting, exit model or any order field (entry, stop, targets,
  expiry).
- Re-testing a hard regime switch, any closed pre-registration, or any
  per-strategy regime allow list.
- Serving the gradient-boosted comparator. It cannot be stored as plain
  coefficients; promoting it would need its own spec.
- Mapping the funnel to instrument v3 (`V3_FUNNEL_REFUSAL` stays).
- Short-interest, days-to-cover or hard-to-borrow features: the repo has
  no point-in-time source for them (`## Panel review`).
- A scheduled production refit (deferred; see Part C).

## Anti-goals (a failure even if everything "works")

- A feature, weight, threshold, fold scheme or hyperparameter grid chosen
  after reading a fold result. Every value below is frozen here.
- A walk-forward table quoted as a lift or a verdict, or used to decide
  which direction gets a surface. These are fold results on years that are
  in-sample for every strategy that exists today (v3 rule). The only
  mechanical decision taken from them is the thin rule.
- The live book or any 2026 bar used to fit, tune or select anything.
- LONG rows, LONG scores or LONG alert lines changing because SHORT work
  shipped, or the reverse.
- A scorer failure delaying or dropping an alert, or touching an order
  field.
- An alert line that reads as an instruction to skip, resize or move an
  order.

## Design

### Units

| Unit | Location | Job | Depends on |
|---|---|---|---|
| Market context | `swingbot/core/edge/direction_context.py` | One per-day frame (SPY, breadth, VIX, regime2) built once per scan or replay run, indexed by date, for both replay and live | the PIT store, the context loaders |
| Feature builder | `swingbot/core/edge/direction_features.py` | `build(candidate, stock_df, ctx_row, asof) -> dict[str, float \| None]`, mirrored; the one function replay and live both call | market context, as-of earnings snapshots |
| Dataset exporter | `swingbot/core/backtesting/direction_dataset.py` + `scripts/backtest/export_direction_dataset.py` | Replays the v3 window, writes one row per plan, checkpointed | v3 arm path, feature builder, `edge/frictions.py` |
| Walk-forward fitter | `swingbot/core/backtesting/direction_fit.py` + `scripts/backtest/fit_direction_models.py` | Fits both heads per direction and the allocator per fold; writes results and hashed model records | dataset, `instrument/folds.py`, `instrument/stats.py`, scikit-learn (training only) |
| Scorer | `swingbot/core/edge/direction_scorer.py` | Loads a model record by hash; `score(candidate)` and `tilt(day)`; numpy only | feature builder, model store |
| Surface | scan pipeline hook, `direction_shadow` store, alert line, Research panel | Logs, joins, renders | scorer |

Live code never imports training code. The scorer evaluates stored
coefficients with numpy; scikit-learn is a training-time dependency only.

### Part A — the dataset

**Window and instrument.** Instrument v3 (v190): the PIT S&P 500 on Alpaca
bars (`data/market_data_pit/`), warm-up from 2016-01-04, research
2017-01-01..2025-12-31, the 2026 holdout untouched (the exporter refuses any
bar on or after 2026-01-01). The window holds the 2018 Q4, 2020 and 2022
sell-offs, which the SHORT model needs. The run records its universe,
window, data-store snapshot (no refetch mid-run), library versions and
seed in a `manifest.json` beside the rows.

**Rows.** One row per **plan** the v3 arm path builds, in two populations:

- `as_issued` — a plan the live pipeline would issue: through the plan
  builders, entry filters and the 2% dollar-risk cap. Weight 3.
- `rejected` — a plan that was built (it has an entry, stop and targets)
  and then rejected by an entry filter or the 2% cap. Weight 1.

A signal that never became a plan has no stop or targets, so R is
undefined for it; it is **not** a row. Plan 1 builds the producer that
records rejected plans with their rejection reason (today `blocked_sink` in
`arms/strategy_engine.py` records compression decisions only and labels no
outcome). The weights are frozen. Every reported metric is computed on
`as_issued` rows only; `rejected` rows exist only to give the fit more
examples.

**Labels.** Both populations go through the same v3 fill model (a plan
whose entry is never reached is `no_fill` and is not a row in either
population) and the same exit simulation as the arm path runs it, including
the gap-through-stop fill (`planning/exit_sim.py`). Costs are
`edge/frictions.py` slippage and commission on every row, plus
`frictions.borrow_r(entry, risk, days)` on every SHORT row. The v3 arm path
does not apply borrow today; the exporter does, so SHORT outcomes are not
overstated.

- `win` — net R > 0.
- `r_net` — the net R outcome.

**Columns.** `row_id`, `ticker`, `strategy`, `horizon_key`, `direction`,
`signal_date`, `exit_date`, `population`, `rejection_reason`, `weight`,
every feature, `win`, `r_net`, `fold_year` (the calendar year of
`signal_date`).

**Checkpointing.** A finished ticker × year unit is written to
`data/direction_dataset/<run_id>/<ticker>_<year>.parquet` the moment it
completes; a restart skips existing units. Column order and dtypes are
fixed by one schema constant. The final dataset is their concatenation
sorted by `row_id`, and "a resumed run equals an uninterrupted one" is
checked by a canonical content hash (rows serialised in schema order), not
by file bytes, because Parquet metadata varies across writer versions.

### Part A — the features

All features read only bars at or before the signal bar. Context series
(SPY, ^VIX, ^VIX3M, breadth, regime2) are computed once over the full
history, then **indexed** at the stock bar's date, filling forward only
(the `asof_context.py` pattern). Stock features are **signed so that a
higher value favours the row's direction** (for a SHORT row, a trend
feature is the negative of the LONG value on the same bar). Every ratio
guards a zero or missing denominator and returns `None`; no NaN is ever
stored.

**Market context (both directions, not sign-flipped; each direction's own
model learns its own weights):**

| Feature | Definition |
|---|---|
| `regime2_*` | one-hot of `regime2.regime_series(spy_df)` (price only, as v231 Part C) |
| `spy_trend` | SPY close / SMA200 − 1 |
| `spy_slope` | SMA50 20-bar % change |
| `spy_ret_10` | SPY 10-bar return (fast; catches V-bottoms and bear rallies the SMA features miss for months) |
| `spy_off_low_20` | SPY close / 20-bar low − 1 (fast) |
| `breadth` | share of S&P 500 members as of that date closing above their own SMA50 (definition below) |
| `vix_level` | ^VIX close z-scored over the 252 closes ending at the bar |
| `vix_curve` | ^VIX / ^VIX3M close |
| `vix_curve_chg_5` | `vix_curve` 5-bar change (term-structure turn) |

**Breadth contract.** One function `breadth_series(frames, members_asof)`
in `direction_context.py`. Replay calls it with the PIT store frames and
the PIT membership the v3 instrument already uses. Live calls the **same
function on the same PIT store and membership source**, never on the
watchlist and never on `market_data/` (`known-traps.md` § the two OHLCV
caches). Plan 1's brief confirms the live process can read the PIT store
at scan time. If it cannot, `breadth` is **removed from the frozen list
before the first fit**, recorded in the plan; it is never computed two
different ways.

**Stock core (both directions, signed):**

| Feature | Definition |
|---|---|
| `rs_63` | stock 63-bar return − SPY 63-bar return |
| `sector_rs_63` | sector ETF 63-bar return − SPY 63-bar return, using the as-of sector assignment the arm path already uses |
| `atr_pct` | ATR14 / close |
| `dist_ma50`, `dist_ma200` | close / SMA − 1 |
| `days_to_earnings` | trading days to the next earnings date from the as-of earnings snapshot (`snapshot_of`, the arm path's source); capped at 60, `None` when unknown |
| `strategy_*`, `horizon_*` | one-hot |

`rs_63` and `sector_rs_63` replace the stored cross-sectional
`rs_pctile`/`sector_pctile`. Those depend on which population is ranked,
and replay (`asof_context.build_asof`) and live (`analyze.py:_rs_pctile`)
rank different sets. The time-series versions need no cross-section, so
live and replay compute them identically.

**SHORT extras:** `dist_52w_high` (close / 252-bar high − 1),
`gap_up_freq` (share of the last 60 bars opening ≥ 2% above the prior
close), `gap_vs_stop` (largest up-gap of the last 60 bars divided by this
plan's stop distance), `squeeze_20` (largest 3-bar gain in the last 20
bars, in ATR units).

**LONG extras:** `pullback_depth` (drawdown from the 20-bar high, in ATR
units), `dist_52w_low` (close / 252-bar low − 1).

**Preprocessing (stored in the model record).** A missing value is imputed
with the fold's training median and a `<name>_missing` flag is added; then
every numeric feature is standardised with the fold's training mean and
standard deviation (one-hot columns are not scaled). The list is frozen; a
change is a new model version and a new spec.

### Part B — the walk-forward fitter

**Folds.** The v3 scheme through `instrument/folds.py`, not a
reimplementation: five anchored yearly folds, test years 2021–2025,
`MIN_TRAIN_YEARS = 4`, split by `folds.split_fold(..., purge=True)` so a
training row whose `exit_date` reaches into the test year is purged. Under
anchored folds the embargo is a no-op (training always precedes the test);
the purge is the protection.

**Heads, per direction, per fold:**

1. **P(win):** L2 logistic on all features, sample-weighted (3/1), with no
   class balancing, so P stays calibrated to the base rate and EV is in
   true R units.
2. **Size:** two L2 linear regressions on the same features, one on
   winning rows' `r_net` (W) and one on losing rows' |`r_net`| (L), each
   clipped at prediction to its training rows' [5th, 95th] percentile.
3. **EV:** P·W − (1 − P)·L.

**Hyperparameters.** L2 strength C from the frozen grid
{0.01, 0.03, 0.1, 0.3, 1.0}, picked per head by 3-fold time-ordered inner
cross-validation on the fold's training rows, with the same `exit_date`
purge applied at every inner boundary (log-loss for P(win), mean absolute
error for size). Nothing else is tuned. Every random step is seeded
(`WEEK_BOOTSTRAP_SEED` for bootstraps, one recorded seed for fitting).

**Take rule (frozen).** A row is "taken" when EV > `EV_BUFFER = 0.05R`.

**Comparator.** A gradient-boosted classifier (scikit-learn
`HistGradientBoostingClassifier`, `max_depth=3`, `max_iter=200`,
`learning_rate=0.05`, `early_stopping=False`, `random_state` = the recorded
seed, monotone +1 on `rs_63`, `spy_trend` and `breadth`) replaces the
P(win) head only; the size heads are shared. It is reported beside the
logistic model and never served.

**Multiple comparisons.** Each run makes six model comparisons: two
directions × (logistic, comparator) plus the allocator against 50/50 and
the allocator per episode. The results document states this count. None of
these comparisons is a ledger row; Spec 2's single shot is, and it is read
with `ledger_qvalues` (`instrument/stats.py`).

**Thin rule (the only mechanical decision).** For a direction in a fold:

- fewer than 300 `as_issued` **training** rows: `thin`, no model fitted;
- fewer than 30 `as_issued` **test** rows, or fewer than 30 in its taken
  subset: the fold's results print `thin` instead of a figure.

A direction thin for training in three or more of the five folds gets no
model record at all, and every surface says "no model (thin)" for it.

**Per fold, per direction, reported on `as_issued` test rows:**

- unfiltered: N, win rate, net ExpR, total R, 95% CI
- taken subset: the same five
- skipped subset: N, net ExpR, total R
- P(win) calibration by decile (predicted vs observed)
- v231's `regime_table` for the taken and the unfiltered rows
- the comparator's taken subset beside the logistic model's

Every CI comes from `instrument/stats.week_cluster_bootstrap` (trades in
the same week are not independent).

The results document is `docs/superpowers/results/<date>-v233-direction-models.md`
plus the raw rows as JSON. It carries the line "fold results on in-sample
years (v3 rule); not a lift and not a verdict".

**Model record.** For each direction, the fitter also fits on all
2017–2025 rows (the champion candidate) and stores one record per head:
`direction`, `version`, `features` (ordered), `coef`, `intercept`,
imputation medians, scaler means and standard deviations, clip bounds,
`C`, `seed`, library versions, `dataset_run_id` and dataset content hash,
`fit_date`, and its fold results (the per-fold table above, produced by
the same code). `model_hash` = sha256 of the canonical JSON of all of the
above with every float rounded to 12 significant digits, so a
re-computation on another BLAS gives the same hash.

**Why fitting on all of 2017–2025 is safe.** The champion is fitted on
every research year, including v1 VALIDATION (2024–2025). That is
acceptable **only because no gating number is ever read on those years**.
Spec 2's verdict comes from the frozen champion scored on the 2026
holdout, as one shot charged to the holdout budget v2 and v3 share
(`backtest-methodology.md` § Windows). The fold tables here never gate.

### Part B — the allocator

**Market score m ∈ [−1, 1].** An L2 logistic on the market-context
features only, standardised as above, one row per trading day d. Target:
over the `as_issued` rows signalled in the 20 trading days after d, LONG
total net R per unit of risk minus SHORT total net R per unit of risk; the
target is 1 when that difference is positive. A day enters the fit only
when each side has at least 5 rows in its window; skipped days are counted
and reported per fold, so the share of days dropped while shorts are
sparse is visible. The target is relative: it says which side did better,
including "less negative" when both lose. That is what an allocator
decides; whether either side pays is v231's book gate. m = 2·p − 1.

The allocator fits on the same folds and C grid, and a day row is purged
from training when any row in its 20-day window has an `exit_date` in or
after the test year.

**Vote score v ∈ [−1, 1].** From the day's candidates: (LONG rows with EV
above the buffer − SHORT rows with EV above the buffer) / all candidate
rows that day, 0 when there are none. A direction without a model
contributes 0 to the count and still gets its floor share.

**Blend and mapping (frozen):**

- s = 0.7·m + 0.3·v
- target LONG share = clamp(0.5 + 0.35·s, 0.15, 0.85); SHORT share = 1 − LONG share
- hysteresis: the share moves at most 0.10 per trading day toward its
  target, and a change of which side holds more than half needs the target
  to sit on the new side for two consecutive days
- minority EV bar: for the side with share σ < 0.5, the take threshold is
  `EV_BUFFER + 0.25 · (0.5 − σ) / 0.35` R (0.05R at 50%, 0.30R at 15%)

**Allocator fold result.** On each test year, the `as_issued` book replayed
with each direction's risk scaled by its share versus a fixed 50/50 split:
total net R ÷ total risk committed, max drawdown in R, and the days spent
above 70% on either side.

**Episode view.** For three frozen windows, a daily series of LONG share
against SPY's forward 10-bar return: 2018-10-01..2019-01-31,
2020-02-15..2020-05-31, 2022-01-01..2022-12-31. This is the direct check
on "stops issuing longs into a bear market" and on how late it turns back
after a V-bottom. It is a picture, never a verdict.

### Part C — the live surface

**Per-scan context.** The market context frame (SPY, breadth, VIX,
regime2) is computed **once per scan** before any alert is scored, from
the same function replay uses. Scoring an alert is then a feature lookup
plus a dot product. The scorer runs after the plan is final and before the
send, inside a try/except. A synchronous call cannot be pre-empted, so
latency is enforced after the fact: elapsed time over 200 ms records
`status = error`, `error_reason = timeout` for that row. The send never
fails because of the scorer, and the scorer reads the plan and never
writes to it.

**Store `direction_shadow`** (Postgres, Alembic revision per
`schema-evolution.md`):

- per alert: `plan_id`, `direction`, `model_hash`s, the feature row (JSON,
  no NaN), `features_asof` (the bar date the features used), `p_win`,
  `avg_win`, `avg_loss`, `ev`, `above_bar`, `ev_bar`, `status` (`ok` /
  `no_model` / `error`), `error_reason`, `scored_at`
- per day (`kind = 'tilt'`): `tilt_date`, `long_share`, `short_share`, `m`,
  `v`, allocator hash, the driver features

Outcomes are joined by `plan_id` from the existing trade records at read
time; nothing is copied. A plan with no trade joins as open.

**Store `direction_models`** (Postgres): one row per model record from
Part B, plus `role` (`champion` / `challenger` / `retired`) and
`promoted_at`. The scorer loads the champion per direction at startup and
on SIGHUP.

**Champion and challenger.** "Challenger" means one thing: a later refit of
the same model through the same harness. The gradient-boosted model is the
"comparator", never a challenger. A challenger replaces its champion only
when its fold results beat the champion's stored fold results on all of:
taken-subset total net R summed over folds, the number of folds where the
taken subset beats unfiltered, and P(win) log-loss. The swap is one logged
row change. **Once Spec 2 pre-registers a direction's champion hash, that
direction's champion is frozen** until Spec 2's verdict is recorded.

**No scheduled refit in Spec 1.** The research window ends 2025-12-31 and
2026 is the holdout, so a quarterly re-export would add no data and could
only re-select on the same folds. A refit becomes possible when the
methodology moves the holdout boundary; the cron is written then (`## What
follows`).

**Alert line** (Discord embed and plan page), one line, information only:

`Model view (unvalidated, prior close 2026-11-16): EV +0.18R · P(win) 54% · above model bar · market tilt 70/30 LONG`

- It never says take, skip, size or move. "above model bar" / "below
  model bar" describes the score, not the order.
- `no_model`: `Model view (unvalidated): no SHORT model yet (thin) · market tilt 70/30 LONG`
- `error`: the line is omitted and the store row carries the reason.
- The date is `features_asof`; the tilt shown is that same day's tilt.
- `DIRECTION_MODEL_ANNOTATE` in `.env` (`swingbot/config.py`, default on,
  hot-reloaded): off removes the line everywhere. With it off, embeds and
  plan pages are byte-identical to today's. With it on or off, the plan
  record's order fields are byte-identical.

**Research panel "Direction models"** (mobile, tablet and desktop together,
per `ui-design.md`):

1. Today's tilt: the LONG/SHORT share, m and v, the top drivers.
2. Live shadow book per direction: above-bar vs below-bar (N, win rate, net
   ExpR, total R, `thin` under N = 30), with the line "shadow only; nothing
   was skipped".
3. Calibration chart per direction: predicted P(win) decile vs observed.
4. Walk-forward fold tables and the episode view from the latest results
   document.
5. Model versions: champion and challenger per direction, hash, fit date.

One read-only endpoint serves the panel. Empty states say why ("no model
(thin)", "no shadow rows yet").

## Constraints

- **Order.** P1 (dataset) → P2 (fitter and allocator) → P3 (scorer and
  surface). P3's scope follows the thin rule only: the full surface for a
  direction with a model record, the "no model (thin)" surface for one
  without. Fold results never decide P3's scope.
- **Queue.** The SessionStart hook holds two plans mid-write (v230, v232);
  they are resumed first. Spec 2 needs v231's direction gate, which waits
  on v230.
- **Dependencies.** scikit-learn joins the dev/training requirements only;
  the bot image and the scorer import numpy only.
- **Long runs.** The export and the fits run per ticker × year and per
  fold, persisting each finished unit; long runs go to `backtest-runner`
  and print a percent past 15 minutes.
- **Isolation.** A SHORT-only change never changes LONG rows, LONG scores
  or LONG alert lines, and vice versa; pinned by byte-identity tests.
- **Complexity.** Every function < 15 (`complexity_gate.py`).
- **No lookahead.** Every feature passes the truncation test, with the
  context frames truncated too (`no-lookahead` skill).

## Testing

- Feature builder: truncating the stock frame **and** the SPY, VIX and
  breadth context at the signal bar leaves every feature identical; a
  SHORT row's signed stock features equal the negated LONG values on the
  same bar; missing inputs and zero denominators give `None`, never raise,
  never NaN.
- Parity: `breadth_series`, `rs_63` and `sector_rs_63` give identical
  values through the replay entry and the live scan entry on the same
  frames and date.
- Exporter: a killed and resumed run has the same canonical content hash
  as a full run; a label matches a hand-computed v3 fill and exit trade; a
  SHORT label includes `borrow_r`; a gap-through-stop fixture fills at the
  open; the holdout guard refuses a 2026 bar; the producer records a
  cap-rejected plan with its reason; a signal with no plan yields no row.
- Folds: `split_fold` purges a training row whose exit crosses into the
  test year; the inner CV purges at each inner boundary; an allocator day
  row whose window crosses the test start is purged.
- Fitter: on synthetic rows with a planted feature, the take subset beats
  unfiltered; on pure noise the take-minus-unfiltered CI covers 0; a fixed
  seed gives identical records and hashes; rounding makes the hash stable
  under a 1e-14 coefficient perturbation.
- Thin rule: under 300 training rows gives `thin` and no model; under 30
  test or taken rows prints `thin`; three thin folds give no record.
- Scorer: the numpy prediction (impute → flag → scale → dot → sigmoid →
  clip) matches scikit-learn `predict_proba` to 1e-9; a missing or corrupt
  record gives `no_model` / `error`, never an exception into the scan; an
  elapsed time over 200 ms records `timeout`.
- Allocator: clamp at 15/85, the 0.10 step, the two-day side flip, the
  minority EV-bar ramp at 50%, 32.5% and 15%, and the 5-row day floor.
- Surface: an alert sends when the scorer raises; each line state renders
  with its date; the line contains none of "take", "skip", "size";
  toggle off gives byte-identical embeds and plan pages; toggle on or off
  leaves the plan record's entry, stop, targets and expiry byte-identical;
  panel empty and thin states render at the three widths; the endpoint
  returns an empty payload cleanly on an empty store.
- Stores: Alembic up/down; the outcome join tolerates a plan with no trade.

## Plans

1. `v233-direction-models-dataset`: market context, breadth contract,
   feature builder, rejected-plan producer, exporter, checkpoints.
2. `v233-direction-models-fit`: fitter, allocator, episode view, results
   document, `direction_models` store.
3. `v233-direction-models-surface`: scorer, per-scan context,
   `direction_shadow`, alert line, toggle, panel, endpoint. Written after
   plan 2, scoped by the thin rule.

## Claude's calls, for the partner to check

1. **Window is instrument v3, 2017–2025, not 2010–2025.** In the brainstorm
   I said 2010–2025. The repo's PIT store with the live fill and exit model
   starts in 2016 (warm-up) / 2017 (research); the 2010–2019 data serves
   only the idea screen's fixed race. The v3 window still holds 2018 Q4,
   2020 and 2022.
2. **Every fold is in-sample for the strategies themselves** (v3 rule).
   The fold tables inform Spec 2's design and never gate; Spec 2's verdict
   is one shot on the 2026 holdout, charged to the shared budget.
3. **"Rejected" rows are rejected plans only**, not every raw signal. A
   signal that never became a plan has no stop or targets, so its R is
   undefined. This narrows your decision 10 (panel finding).
4. **No scheduled refit yet** (narrows your decision 11). With 2026 sealed
   there is no new research data to refit on; the champion/challenger
   mechanism is built, the cron waits until the holdout boundary moves.
5. **Breadth is used only if live can compute it from the same PIT
   source**; otherwise it is dropped before the first fit.
6. **Relative strength is time-series** (`rs_63`), not the stored
   cross-sectional percentile, for replay/live parity.
7. **Frozen numbers chosen by Claude, not by data:** weights 3/1,
   `EV_BUFFER = 0.05R`, the 300/30 thin floors, the 5-row allocator day
   floor, the 0.7/0.3 blend, 0.35 tilt slope, 0.10 daily step, two-day
   flip, +0.25R minority bar, the C grid, the comparator's settings, the
   episode windows and the swap rule.
8. **The alert line says "above/below model bar", never "take/skip"**, and
   names the prior-close date its features used.
9. **Bump: bot minor** because every alert visibly gains a line, even
   though no decision changes.

## What follows

1. **Spec 2: the direction-model filter.** Pre-registers one frozen
   champion hash per direction plus the allocator hash; one shot on the
   2026 holdout under v231 `--gate direction`, charged to the shared
   holdout budget and read with `ledger_qvalues`; on a pass, the stage-3
   gate (skip and resize) for that direction only. It needs v231 shipped
   and either a v3 funnel mapping or the shot run on instrument v2.
2. **The annotate-to-gate review**: after a quarter of live shadow rows,
   compare above-bar vs below-bar net ExpR per direction, descriptively.
3. **The scheduled refit cron**, once the methodology moves the holdout
   boundary and new research years exist.

## Parallelisation

- **Group 1 (one unit): plan 1.** The dataset is the input to everything.
- **Group 2 (one unit): plan 2.** Needs plan 1's rows; the allocator needs
  the per-direction models' EV for its vote score, so it fits after them
  in the same plan.
- **Group 3: plan 3.** Its scope depends on plan 2's thin-rule outcome.
  Inside it, the stores, per-scan context and scorer come first; the alert
  line and the panel can then run in parallel, since they share only the
  read-only store.

## Panel review (2026-11-17)

quant-researcher (opus), quant-engineer (sonnet), veteran-trader (sonnet),
serially, on b77ca796. Five BLOCKING, the rest ADVISORY; duplicates merged.

**BLOCKING**

1. quant-researcher: the champion fitted on 2017–2025 (incl. v1 VALIDATION)
   would be scored on its own training years by Spec 2. -- applied: Spec 2's
   verdict is declared now as one shot on the 2026 holdout, shared budget
   (Part B "Why fitting on all of 2017–2025 is safe", What follows 1).
2. quant-engineer + veteran-trader: the breadth proxy names no membership
   source or cache; live (watchlist/`market_data/`) and replay (PIT store)
   would diverge. -- applied: one `breadth_series` on the PIT store and
   membership for both, a parity test, and dropped before the first fit if
   live cannot read the PIT store.
3. quant-engineer: `rs_pctile`/`sector_pctile` rank different populations in
   replay (`asof_context.build_asof`) and live (`analyze.py:_rs_pctile`). --
   applied: replaced by time-series `rs_63`/`sector_rs_63`, parity-tested.
4. quant-engineer + quant-researcher: no producer labels rejected signals,
   and builder-rejected signals have no stop or targets. -- applied:
   `rejected` = built plans rejected by a filter or the cap, through the
   same v3 fill model; signals with no plan are not rows; plan 1 builds the
   producer.
5. quant-engineer: the "270-day embargo" is a no-op under anchored folds
   (`instrument/folds.py`). -- applied: `folds.split_fold` with purge; the
   claim and its test removed.

**ADVISORY**

6. quant-researcher: class balancing miscalibrates P(win), so EV and the
   0.05R bar are off. -- applied: no class balancing.
7. quant-researcher: inner CV has no purge. -- applied.
8. quant-researcher + quant-engineer: allocator day rows leak test-year
   outcomes across the fold edge. -- applied: day-row purge.
9. quant-researcher: the allocator target has no N floor, drops days
   selectively, and "ExpR per unit of risk" is undefined. -- applied: total
   R per unit of risk, 5-row day floor, dropped days reported; the relative
   ("less negative") target kept and justified.
10. quant-researcher: thin floor counts training rows only; total R
    missing. -- applied: 30-row test/taken floor; total R everywhere.
11. quant-researcher: unnamed bootstrap. -- applied:
    `week_cluster_bootstrap`.
12. quant-researcher: "challenger" means two things; the champion has no
    fold results; a quarterly re-export adds no data; a swap could detach
    the live hash from Spec 2's. -- applied: GB renamed "comparator";
    champion carries fold results; cron deferred; champion frozen once
    pre-registered.
13. quant-researcher: "no OOS lift → no surface" makes fold tables decide.
    -- applied: P3 scope follows the thin rule only.
14. quant-researcher: uncited priors (v146 ranker, v32/v33) and uncounted
    comparisons. -- applied: Why item 2 and the multiple-comparisons line.
15. quant-researcher + veteran-trader: "EV · would TAKE" on real-money
    alerts invites acting on an unvalidated number. -- applied: "Model
    view", "above/below model bar", no take/skip/size wording (tested),
    prior-close date shown. financial-advisor was not on this panel; the
    partner chose the annotation explicitly (decision 12).
16. quant-engineer: context-frame lookahead and joins. -- applied: full
    series then indexed; truncation test covers context frames.
17. quant-engineer: Parquet byte-identity unstable; no manifest. --
    applied: canonical content hash, schema constant, run manifest.
18. quant-engineer: unseeded randomness; float hash unstable. -- applied:
    seeds, `early_stopping=False`, 12-significant-digit rounding, library
    versions in the record.
19. quant-engineer: 200 ms cannot be enforced by try/except; cold context
    loads. -- applied: per-scan context computed once; post-hoc `timeout`.
20. quant-engineer: scaler parameters absent; unscaled L2 ill-conditioned.
    -- applied: standardisation, parameters in the record, parity order
    pinned.
21. quant-engineer: division guards and NaN in JSON. -- applied.
22. veteran-trader: regime features lag turns (2020 V-bottom, 2022
    rallies). -- applied: `spy_ret_10`, `spy_off_low_20`,
    `vix_curve_chg_5`.
23. veteran-trader: hysteresis unchecked at turns. -- applied: the episode
    view over three frozen windows.
24. veteran-trader: short killers missing (borrow, earnings, gap size,
    short interest, HTB). -- applied: `borrow_r` on SHORT labels (the v3
    arm path omits it), `days_to_earnings` (both directions),
    `gap_vs_stop`, gap-through-stop named in labels. Short interest,
    days-to-cover and HTB rejected: no point-in-time source in the repo
    (Non-goals).
25. veteran-trader: frictions unnamed. -- applied: `edge/frictions.py`
    slippage, commission and borrow cited in Part A.
26. veteran-trader: order fields not pinned byte-identical. -- applied.
27. veteran-trader: say which day's tilt and features the line used. --
    applied: `features_asof`, `tilt_date`.
