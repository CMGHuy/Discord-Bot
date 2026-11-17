# v233 — Direction models: a LONG meta-labeler, a SHORT meta-labeler and a budget allocator, in shadow

**Version:** ui 1.44.0 · bot 2.19.1
**Bump:** bot minor (every alert gains one labelled shadow-score line); ui minor (a new "Direction models" panel in the Research workspace and the same line on the plan page)
**Edge:** none (integrity). An instrument: a dataset, two per-direction models, an allocator and their shadow record. Nothing it builds skips, sizes or blocks a trade. Any lift is claimed later, by Spec 2's pre-registration.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, veteran-trader
**Status:** spec written 2026-11-17 from a brainstorm with the partner; every decision in `## Partner decisions` was made in chat the same day. Plans queue behind v230 and v232 (both mid-write) — see `## Constraints`.

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
2. **The hard regime switch is closed.** v17 `REGIME_ALLOW` (per strategy ×
   regime allow lists) is ledger row `v17-regime-allow`, verdict NO-LIFT,
   0 of 44 cells. A bull_volatile veto was examined again on 2026-11-12 and
   would not clear the screen. This spec never re-tests either; a single
   SPY label is too coarse to carry the decision on its own.
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
   challenger runs in shadow and must beat it out of sample.
7. **Split around the screen rule.** This spec is the instrument (`Edge:
   none`, `Screen: exempt`). Spec 2 pre-registers the frozen models as a
   filter; that pre-registration stands in for the idea screen, which tests
   single frozen conditions and cannot take a trained model.
8. **Shared mirrored core plus 2–4 extras per direction**, all frozen before
   the first fit.
9. **Soft tilt, 85/15 to 15/85.** The minority side never goes to zero; its
   EV bar rises as its share shrinks.
10. **Training rows: raw signals and as-issued plans, weighted** toward
    as-issued.
11. **Frozen, hashed model versions.** A quarterly challenger refit on the
    VM shadows the champion before any swap.
12. **Visibility in Spec 1:** the Research panel, plus a one-line score on
    every alert and plan page labelled "unvalidated".
13. **Approach A: three plans in order** (dataset → models → live surface).
    A direction with no out-of-sample lift never gets a scoring surface
    beyond an honest "no model".

## Goals

1. A lookahead-clean, checkpointed replay dataset with one row per LONG and
   SHORT candidate: as-of features, a weight, and the outcome under the
   live exit model net of costs.
2. Per direction: a walk-forward fitted P(win) head and a win/loss-size
   head, with per-fold out-of-sample results that say plainly whether the
   model's take subset beats the unfiltered book.
3. An allocator that turns market state and model votes into a daily
   LONG/SHORT budget split, with its own walk-forward result against a
   fixed 50/50 split.
4. Live shadow scoring of every issued alert and of every day's tilt,
   joined to outcomes, visible on bomeo-capital.com and on each alert.

## Non-goals

- Skipping, resizing or blocking any trade. That is Spec 2, per direction,
  after a pass.
- Any change to the strategies, plan builders, the 2% dollar-risk cap,
  heat accounting or exit model.
- Re-testing a hard regime switch, any closed pre-registration, or any
  per-strategy regime allow list (`v17-regime-allow` stays closed).
- Serving the gradient-boosted challenger. It cannot be stored as plain
  coefficients; promoting it would need its own spec.
- Mapping the funnel to instrument v3 (`V3_FUNNEL_REFUSAL` stays; see
  `## What follows`).
- Auto-refitting in production without a logged champion/challenger swap.

## Anti-goals (a failure even if everything "works")

- A feature, weight, threshold, fold scheme or hyperparameter grid chosen
  after reading a fold result. Every value below is frozen here.
- A walk-forward table quoted as a lift or a verdict. These are fold
  results on years that are in-sample for every strategy that exists today
  (v3 rule); they decide only whether Spec 2 is worth writing.
- The live book used to fit, tune or select anything.
- LONG rows, LONG scores or LONG alerts changing because SHORT work
  shipped, or the reverse.
- A scorer failure delaying or dropping an alert.

## Design

### Units

| Unit | Location | Job | Depends on |
|---|---|---|---|
| Feature builder | `swingbot/core/edge/direction_features.py` | `build(candidate, asof) -> dict[str, float \| None]`, mirrored; the one function replay and live both call | `entry_context`, `edge/regime2.py`, as-of context loaders |
| Dataset exporter | `swingbot/core/backtesting/direction_dataset.py` + `scripts/backtest/export_direction_dataset.py` | Replays the v3 window, writes one row per candidate, checkpointed | replay engine, feature builder |
| Walk-forward fitter | `swingbot/core/backtesting/direction_fit.py` + `scripts/backtest/fit_direction_models.py` | Fits both heads per direction and the allocator per fold; writes results and hashed model records | dataset, scikit-learn (training only) |
| Scorer | `swingbot/core/edge/direction_scorer.py` | Loads a model record by hash; `score(candidate)` and `tilt(day)`; numpy only | feature builder, model store |
| Surface | scan pipeline hook, `direction_shadow` store, alert line, Research panel | Logs, joins, renders | scorer |

Live code never imports training code. The scorer evaluates stored
coefficients with numpy; scikit-learn is a training-time dependency only.

### Part A — the dataset

**Window and instrument.** Instrument v3 (v190): the PIT S&P 500 on Alpaca
bars, warm-up from 2016-01-04, research 2017-01-01..2025-12-31, the 2026
holdout untouched (`asof` guard refuses any bar on or after 2026-01-01).
The window holds the 2018 Q4, 2020 and 2022 sell-offs, which the SHORT
model needs.

**Rows.** One row per candidate, two populations, both carried:

- `as_issued` — a plan the live pipeline would issue: through the existing
  plan builders, entry filters and the 2% dollar-risk cap, as the replay
  engine already applies them. Weight 3.
- `raw` — every strategy entry signal that did not become an as-issued
  plan (rejected by a builder, filter or the cap). Weight 1.

The weights are frozen. Every reported metric is computed on `as_issued`
rows only; `raw` rows exist only to give the fit more examples.

**Labels.** Both populations are labelled with the live exit model (TP1,
TP2, runner, stops) as the replay engine runs it, net of costs (instrument
v3 fills and costs):

- `win` — net R > 0.
- `r_net` — the net R outcome.

A `raw` row that the cap rejected is labelled as if it had been filled at
its plan's entry, so it is one outcome definition across both populations.

**Columns.** `row_id`, `ticker`, `strategy`, `horizon_key`, `direction`,
`signal_date`, `exit_date`, `population`, `weight`, every feature, `win`,
`r_net`, `fold_year` (the calendar year of `signal_date`).

**Checkpointing.** A finished ticker × year unit is written to
`data/direction_dataset/<run_id>/<ticker>_<year>.parquet` the moment it
completes; a restart skips existing units. The final dataset is their
concatenation, sorted by `row_id`, so a resumed run is byte-identical to an
uninterrupted one.

### Part A — the features

All features are computed on bars at or before the signal bar. Each is
**signed so that a higher value favours the row's direction** (for a SHORT
row, a trend feature is the negative of the LONG value on the same bar).

**Shared core (both directions):**

| Feature | Definition |
|---|---|
| `regime2_*` | one-hot of `regime2.regime_series(spy_df)` at the signal bar (price only, as v231 Part C) |
| `spy_trend` | SPY close / SMA200 − 1 |
| `spy_slope` | SMA50 20-bar % change |
| `breadth` | share of the as-of PIT universe closing above its own SMA50, from cached bars (replay has no stored breadth history, so this proxy is the one definition used in both replay and live) |
| `vix_level` | ^VIX close, z-scored over its trailing 252 closes |
| `vix_curve` | ^VIX / ^VIX3M close (the context the `vix_curve_calm` screen loads) |
| `rs_pctile` | the stock's relative-strength percentile (the `entry_context` key) |
| `sector_pctile` | the sector's percentile (the `entry_context` key) |
| `atr_pct` | ATR14 / close |
| `dist_ma50`, `dist_ma200` | close / SMA − 1 |
| `strategy_*`, `horizon_*` | one-hot |

The market features (`regime2_*`, `spy_trend`, `spy_slope`, `breadth`,
`vix_*`) are not sign-flipped; their weights differ per direction because
each direction has its own model.

**SHORT extras:** `dist_52w_high` (close / 252-bar high − 1), `gap_up_freq`
(share of the last 60 bars opening ≥ 2% above the prior close),
`squeeze_20` (largest 3-bar gain in the last 20 bars, in ATR units).

**LONG extras:** `pullback_depth` (drawdown from the 20-bar high, in ATR
units), `dist_52w_low` (close / 252-bar low − 1).

A feature whose input is missing is `None`; the fitter imputes the fold's
training median and adds a `<name>_missing` flag. The list is frozen; a
change is a new model version and a new spec.

### Part B — the walk-forward fitter

**Folds.** The v3 scheme unchanged: five purged anchored yearly folds, test
years 2021–2025, `MIN_TRAIN_YEARS = 4`. Training rows are those with
`signal_date` before the test year, minus any row whose `exit_date` falls
in or after the test year (purge), and minus the 270-day embargo v3
already applies at each fold edge.

**Heads, per direction, per fold:**

1. **P(win):** L2 logistic on all features, sample-weighted (3/1),
   class-balanced.
2. **Size:** two L2 linear regressions on the same features, one on
   winning rows' `r_net` (W) and one on losing rows' |`r_net`| (L), each
   clipped to its training rows' [5th, 95th] percentile at prediction.
3. **EV:** P·W − (1 − P)·L.

**Hyperparameters.** L2 strength C from the frozen grid
{0.01, 0.03, 0.1, 0.3, 1.0}, picked per head by 3-fold time-ordered inner
cross-validation on the fold's training rows (log-loss for P(win), mean
absolute error for size). Nothing else is tuned.

**Take rule (frozen).** A row is "taken" when EV > `EV_BUFFER = 0.05R`.

**Challenger.** A gradient-boosted classifier (scikit-learn
`HistGradientBoostingClassifier`, `max_depth=3`, `max_iter=200`,
`learning_rate=0.05`, monotone +1 on `rs_pctile`, `spy_trend` and
`breadth`) replaces the P(win) head only; the size heads are shared. It is
reported beside the logistic model and never served.

**Thin rule.** A direction with fewer than 300 `as_issued` training rows in
a fold is `thin` for that fold and gets no model there. A direction thin in
three or more of the five folds gets no model record at all, and every
surface says "no model (thin)" for it.

**Per fold, per direction, reported on `as_issued` test rows:**

- unfiltered: N, win rate, net ExpR, 95% bootstrap CI
- taken subset: the same four
- skipped subset: N, net ExpR
- P(win) calibration by decile (predicted vs observed)
- v231's `regime_table` for the taken and the unfiltered rows
- the challenger's taken subset beside the logistic model's

The results document is `docs/superpowers/results/<date>-v233-direction-models.md`
plus the raw rows as JSON. It carries the line "fold results on in-sample
years (v3 rule); not a lift and not a verdict".

**Model record.** For each direction, the fitter also fits on all
2017–2025 rows (the champion candidate) and stores one record per head:
`direction`, `version`, `features` (ordered), `coef`, `intercept`,
imputation medians, clip bounds, `C`, `dataset_run_id`, `fit_date`, and
`model_hash` = sha256 of the canonical JSON of all of the above.

### Part B — the allocator

**Market score m ∈ [−1, 1].** An L2 logistic on the market features only
(`regime2_*`, `spy_trend`, `spy_slope`, `breadth`, `vix_level`,
`vix_curve`), one row per trading day, target = 1 when the `as_issued` LONG
rows signalled in the next 20 trading days earned a higher mean `r_net`
than the SHORT rows (days where either side has no rows are dropped).
m = 2·p − 1. Fitted on the same folds, same C grid.

**Vote score v ∈ [−1, 1].** From the day's candidates: (LONG rows with EV
above the buffer − SHORT rows with EV above the buffer) / all candidate
rows that day, 0 when there are none.

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
net ExpR per unit of risk, max drawdown in R, and the days spent above 70%
on either side. A direction that has no model gets v = its count of 0 and
still receives its floor share.

### Part C — the live surface

**Shadow hook.** After the scan builds an alert and before it is sent, the
scorer runs on the alert's plan inside a try/except with a 200 ms budget.
The send never waits on, or fails because of, the scorer.

**Store `direction_shadow`** (Postgres, Alembic revision per
`schema-evolution.md`):

- per alert: `plan_id`, `direction`, `model_hash`s, the feature row (JSON),
  `p_win`, `avg_win`, `avg_loss`, `ev`, `would_take`, `ev_bar`, `status`
  (`ok` / `no_model` / `error`), `error_reason`, `scored_at`
- per day (`kind = 'tilt'`): `long_share`, `short_share`, `m`, `v`,
  allocator hash, the driver features

Outcomes are joined by `plan_id` from the existing trade records at read
time; nothing is copied.

**Store `direction_models`** (Postgres): one row per model record from
Part B, plus `role` (`champion` / `challenger` / `retired`) and
`promoted_at`. The scorer loads the champion per direction at startup and
on SIGHUP.

**Alert line** (Discord embed and plan page), one line:

`Direction model (unvalidated): EV +0.18R · P(win) 54% · would TAKE · tilt 70/30 LONG`

- `no_model`: `Direction model (unvalidated): no SHORT model yet (thin) · tilt 70/30 LONG`
- `error`: the line is omitted and the store row carries the reason
- `DIRECTION_MODEL_ANNOTATE` in `.env` (`swingbot/config.py`, default on,
  hot-reloaded): off removes the line everywhere. With it off, embeds and
  plan pages are byte-identical to today's.

**Research panel "Direction models"** (mobile, tablet and desktop together,
per `ui-design.md`):

1. Today's tilt: the LONG/SHORT share, m and v, the top drivers.
2. Live shadow book per direction: taken vs skipped (N, win rate, net
   ExpR, `thin` under N = 30), with the line "shadow only; nothing was
   skipped".
3. Calibration chart per direction: predicted P(win) decile vs observed.
4. Walk-forward fold tables per direction from the latest results document.
5. Model versions: champion and challenger per direction, hash, fit date.

One read-only endpoint serves the panel. Empty states say why ("no model
(thin)", "no shadow rows yet").

**Quarterly challenger.** A VM cron (`scripts/ops/`, per
`working-conventions.md` § Scheduling) re-exports the dataset through
the latest complete quarter of 2025 data and earlier (never 2026), refits,
and stores challengers. A challenger replaces its champion only when its
fold results beat the champion's on every one of: taken-subset net ExpR
summed over folds, the number of folds where the taken subset beats
unfiltered, and P(win) log-loss. The swap is one logged row change in
`direction_models`, and a swap never happens silently.

## Constraints

- **Order.** P1 (dataset) → P2 (fitter and allocator) → P3 (scorer and
  surface). P3 is written after P2's results: in full for a direction with
  a model, and as the "no model (thin)" surface only for a direction
  without one.
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
- **No lookahead.** Every feature passes the truncation test (`no-lookahead`
  skill).

## Testing

- Feature builder: truncating the frame at the signal bar leaves every
  feature identical; a SHORT row's signed stock features equal the negated
  LONG values on the same bar; missing inputs give `None`, never raise.
- Exporter: a killed and resumed run is byte-identical to a full run; a
  label matches a hand-computed exit-model trade; the holdout guard refuses
  a 2026 bar; purge and embargo boundary rows are excluded.
- Fitter: on synthetic rows with a planted feature, the take subset beats
  unfiltered; on pure noise the take-minus-unfiltered CI covers 0; fixed
  seed gives identical records and hashes.
- Thin rule: under 300 rows gives `thin` and no record; three thin folds
  give no model at all.
- Scorer: the numpy prediction matches scikit-learn `predict_proba` to
  1e-9; a missing or corrupt record gives `no_model` / `error`, never an
  exception into the scan; the 200 ms budget is enforced.
- Allocator: clamp at 15/85, the 0.10 step, the two-day side flip, the
  minority EV-bar ramp at 50%, 32.5% and 15%.
- Surface: an alert sends when the scorer raises; each of the three line
  states renders; toggle off gives byte-identical embeds and plan pages;
  panel empty and thin states render at the three widths; endpoint returns
  an empty payload cleanly on an empty store.
- Stores: Alembic up/down; the outcome join tolerates a plan with no trade.

## Plans

1. `v233-direction-models-dataset` — feature builder, exporter, checkpoints.
2. `v233-direction-models-fit` — fitter, allocator, results document,
   `direction_models` store.
3. `v233-direction-models-surface` — scorer, `direction_shadow`, alert
   line, toggle, panel, endpoint, quarterly cron. Written after plan 2's
   results.

## Claude's calls, for the partner to check

1. **Window is instrument v3, 2017–2025, not 2010–2025.** In the brainstorm
   I said 2010–2025. The repo's PIT store with the live exit model starts
   in 2016 (warm-up) / 2017 (research); the 2010–2019 data serves only the
   idea screen's fixed race. The v3 window still holds 2018 Q4, 2020 and
   2022.
2. **Every fold is in-sample for the strategies themselves** (v3 rule):
   the strategies were tuned on 2020–2023. The models are new, so their
   fold results are informative about the *filter*, but not clean
   out-of-sample evidence. Hence Spec 2 and the live shadow book.
3. **Breadth is a price-derived proxy** (share of the PIT universe above
   SMA50), because replay has no stored breadth history; live uses the same
   proxy rather than the stored `breadth` tiebreak.
4. **Frozen numbers chosen by Claude, not by data:** weights 3/1,
   `EV_BUFFER = 0.05R`, the 300-row thin floor, the 0.7/0.3 blend, 0.35
   tilt slope, 0.10 daily step, two-day flip, +0.25R minority bar, the C
   grid, the challenger's settings and the quarterly swap rule.
5. **The size heads are fitted separately on winners and losers.** A
   single signed regression would blur the two halves; two clipped
   regressions keep "why skipped" readable (low P, or small W, or large L).
6. **Bump: bot minor** because every alert visibly gains a line, even
   though no decision changes.

## What follows

1. **Spec 2 — the direction-model filter.** Pre-registers one frozen model
   hash per direction plus the allocator hash, one run under v231
   `--gate direction`; on a pass, the stage-3 gate (skip and resize) for
   that direction only. It needs v231 shipped and either a v3 funnel
   mapping (v230 "What follows" item 1) or the shot run on instrument v2.
2. **The annotate-to-gate review**: after a quarter of live shadow rows,
   compare taken vs skipped net ExpR per direction, descriptively.

## Parallelisation

- **Group 1 (one unit): plan 1.** The dataset is the input to everything.
- **Group 2 (one unit): plan 2.** Needs plan 1's rows; the allocator needs
  the per-direction models' EV for its vote score, so it fits after them
  in the same plan.
- **Group 3: plan 3.** Its content depends on plan 2's results (which
  directions have a model). Inside it, the stores and the scorer come
  first; the alert line and the panel can then run in parallel, since they
  share only the read-only store.
