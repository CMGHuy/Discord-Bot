# v143 — FVG (bullish) badge diagnostic

**Version:** ui 1.21.1 · bot 2.2.2 (at writing)
**Bump:** none (a read-only measurement script and one results document; no live path changes)
**Edge:** none (integrity) — measurement only; it is the admission test for a possible later `expectancy` spec on FVG (bullish) plans
**Screen:** exempt (integrity)
**Status:** spec written 2026-10-09; amended the same day before any run (eight features, replay quality score); plan written.

## Why

The partner asked whether "FVG (bullish)" can earn a `VALIDATED` badge. On
production it is the second-largest primary strategy (71 plans, 58 closed
trades, 61.0% win rate, about +0.20R, 2026-07-24..2026-10-09) and every one
of those plans is stamped `WEAK`.

TRAIN says the live sample is noise. A full replay of the baseline confluence
book on TRAIN 2020-01-01..2023-12-31, current engine, 75 cached tickers, all
ten horizons (run 2026-10-09; it reproduced
`results/v129/2026-10-03-v129-armZ-train-rows.json` to the trade):

| Population | N | Win rate | ExpR | Median planned RR | Break-even WR |
|---|---|---|---|---|---|
| All confluence plans | 8,089 | 35.6% | +0.069R | 2.50 | 28.6% |
| FVG (bullish) primary | 1,278 | 29.9% | −0.100R | 2.37 | 29.7% |
| Best primary, Fib 38.2% | 220 | 45.0% | +0.355R | 2.41 | 29.4% |

The badge floor is `win_rate >= 50`, `expectancy_r > 0`, `N >= 30` on TRAIN
(`backtest-methodology.md`). Three facts frame what can be done about it:

1. **No confluence primary reaches 50% on TRAIN.** At a median planned RR
   near 2.4 the book lives in the 30s and 40s by construction.
2. **FVG (bullish) sits on its own break-even curve** (29.9% against 29.7%).
   Pulling targets nearer slides it along that curve: about 50% at RR 1.0
   with expectancy near zero before costs, which still fails the badge. A
   badge needs real discrimination; geometry only decides where that edge
   shows up as win rate.
3. **The label names the target, not the entry.** `primary_strategy_for`
   (`swingbot/core/planning/builders.py`) returns the highest-priority
   confirming method behind the plan's *target*, falling back to the stop's
   methods, and `"FVG"` is first in `chart_style.METHOD_PRIORITY`. So an
   "FVG (bullish)" plan is, most often, a trade aimed at a bullish gap, in
   either direction (484 bullish plans, 794 bearish on TRAIN).

This spec measures, on TRAIN only, whether anything knowable at the signal
bar separates the FVG (bullish) plans that work from the ones that do not,
at the live geometry and at two nearer first targets. It gates nothing and
changes nothing live.

## What was already seen (disclosed before the rule is fixed)

The session that wrote this spec looked at these splits of the 1,278 trades.
They are therefore **reported only** below, never candidates:

- plan direction: bullish 29.7% / −0.049R (N=484), bearish 30.1% / −0.131R (N=794)
- year: 2020 −0.107R, 2021 −0.119R, 2022 −0.244R, 2023 +0.147R
- horizon: best `8m` +0.015R (34.3%), worst `2w` −0.275R (25.6%)
- planned-RR bucket: no bucket above break-even by more than 0.7pp
- `gap_through` (known only after the trade): 226 trades gapped through the
  stop for −1R each; the other 1,052 ran 37.6% / +0.093R

The last line is the reason stop distance and earnings proximity are on the
candidate list. Nothing else on that list has been looked at.

## Scope

In: one read-only script `scripts/backtest/measure_fvg_bullish_diagnostic.py`;
its unit tests; one results document; one closed-table row.

Out: any change to `fvg.py`, `levels.py`, `builders.py`, plans, alerts,
charts, the registry, or any config default. The 2024–2025 VALIDATION window
is never read. No registry row is written or edited by hand.

## Population

Every plan `replay_scenarios` emits on TRAIN 2020-01-01..2023-12-31 (signal
date), every cached ticker in `data/backtest_cache`, all ten
`LEGACY_HORIZONS`, whose `plan.strategy == "FVG (bullish)"` and whose exit
simulation triggers (the same population rule as v129 arm Z's baseline:
`simulate_exit(df, i, plan, scale_out=True)`, untriggered plans dropped).
Expected N = 1,278; the script prints it and stops with a non-zero exit when
it differs by more than 2%, because that means the engine moved.

## What is recorded per trade

Everything is computed on `window = df.iloc[:i + 1]`, `i` the signal bar.

- **The gap.** The unfilled bullish gap from
  `fvg.find_fair_value_gaps_detailed(window)` that made FVG a confirming
  source: the one whose `mid` is nearest the scenario's own target
  (`scenario.take_profit`, the level the scan clustered on, captured at plan
  build) and within the live confluence tolerance of it
  (`confluence_deviation_pct`, the tolerance `count_confirming_strategies`
  uses); if none, the same test against the scenario's stop. `fvg_role` is
  `target`, `stop`, or `unidentified`. Unidentified trades stay in the
  population totals, are excluded from gap-geometry features, and their
  count is printed. *Corrected before any run, 2026-10-09:* the first draft
  matched within 0.25 × ATR14 of `plan.tp1`, which is re-selected
  structurally and can sit far from the clustered level; a two-ticker smoke
  run left 6 of 20 trades unidentified. The correction was made on feature
  data only, with no outcome joined.
- **Outcomes at three geometries.** `live`: the plan as built. `g125` and
  `g100`: a copy with `tp1` moved to `entry ± g × |entry − stop_loss|` for
  `g` = 1.25 and 1.00, stop and every other field unchanged, through the
  same `simulate_exit`. A copy whose `tp2` would no longer lie beyond the
  moved `tp1` keeps its `tp2` (it always lies beyond: `tp1` only moves in).
  Win = TP1 touched; win rate over win + loss; expectancy over all closed
  trades — the badge definitions.

## Candidate features

Eight features, one split each, the favourable side named here. Medians are
taken over the identified population from the feature alone, before any
outcome is joined.

| # | Feature | Favourable side |
|---|---|---|
| 1 | Gap age: `i − gap.bar_index`, bars | ≤ 20 |
| 2 | Gap height: `(top − bottom) / ATR14[i]` | ≥ 0.5 |
| 3 | Displacement: `fvg.is_displacement_gap(..., 1.5)` — v128's definition, body ≥ 1.5 × ATR14 and a close in the gap-side third of the range | true |
| 4 | Stop distance: `abs(entry − stop_loss) / ATR14[i]` | ≥ 1.0 |
| 5 | Replay quality: `quality.score_plan` on the inputs below | ≥ population median |
| 6 | Trend-aligned: `close > SMA200` for a bullish plan, `close < SMA200` for a bearish one | aligned |
| 7 | Volatility: `ATR14[i] / close[i]` | ≤ population median |
| 8 | Earnings distance: sessions to the next earnings reaction (`earnings_calendar.next_reaction_distance`) | > 5 |

A feature that cannot be computed for a trade (short history, no earnings
record, no identified gap) puts that trade in neither side; the count is
printed per feature. A feature whose computable share is under 80% of the
population is reported as **not tested**: it cannot be a candidate, and it
is not closed by this diagnostic either.

**Replay quality (feature 5).** `replay_scenarios` builds plans without
`quality_inputs`, so `plan.quality_score` is 0 on every replayed plan. The
diagnostic scores each plan itself with the live scorer, from the inputs
that are causal on the ticker's own window: higher-timeframe bias, volume
ratio, ATR percentile, trigger distance and confluence count, built the way
`scanning.analyze._build_quality_inputs` builds them. Market regime,
relative-strength percentile and breadth need the whole market at that date
and are passed as `None` (the scorer's neutral defaults). The results
document calls this a replay quality score and says it is not the live one.
`replay_scenarios` itself is not changed.

**Dropped before the run: share of gap filled.** The live gap finder drops a
gap as soon as any later bar overlaps it, so every plan in this population
sits on an untouched gap and the share is 0 by construction. It is recorded
as not testable on this population (partner decision, 2026-10-09). Whether
partially filled gaps should make plans at all is a different mechanism and
would need its own spec.

**Two of these revisit closed rows, and that is the partner's call, made
here in the open.** Feature 3 reuses v128's displacement definition; v128
tested it as a level-map filter over all confluence plans and was refused at
Stage 0. Here it is a plan-level split on one primary's population. Feature
8 reuses v82's exposure definition; v82 found no eligible K as a blackout on
the whole book. Neither closed row is re-run, and this diagnostic cannot
reopen either one.

## The rule

A (feature, geometry) pair is a **candidate** only when its favourable side
has all of:

1. N ≥ 150 closed trades;
2. win rate ≥ 50% and expectancy > 0 (the badge floor) at that geometry;
3. expectancy at least +0.10R above the unfavourable side at the same geometry;
4. expectancy > 0 in at least 3 of the 4 calendar years 2020–2023.

No feature is combined with another. No threshold is moved. Eight features at
three geometries is 24 looks; at a 5% false-positive rate one or two chance
hits are expected, and the results document says so above its table.

## Reported, never gating

One N / win rate / ExpR row per value of `fvg_role`, plan direction, horizon
and year at each geometry; the whole-population row at each geometry; and the exit mix. These are
context for whoever writes the next spec.

## What follows a result

- **One or more candidates.** Each has earned a spec, nothing more. That
  spec is `Edge: expectancy`, adds a filter, and therefore needs its own
  `Screen:` pass (Stage −2) before the funnel and its one VALIDATION shot.
  If the candidate needs `g125` or `g100`, the spec also has to argue a
  per-primary target rule against v31's structural target selection.
- **No candidate.** Closed. FVG (bullish) stays `WEAK`; no filter on this
  feature list is proposed again under another name. The separate question —
  skipping plans whose primary is FVG (bullish) to lift the rest of the book
  — is untouched by this result and stays open.

Either way the closed-table row in `backtest-methodology.md` records the
verdict, and `v143` joins `EXEMPT` in
`tests/backtesting/test_preregistration_ledger_file.py` as a read-only
diagnostic that spends no budget (the v124 precedent).

## Testing

Unit tests, on synthetic frames, for: each feature's value at a known bar;
that truncating the frame after the signal bar changes no feature (no
lookahead); the gap-matching tolerance and the `unidentified` path; that the
`g125`/`g100` copies leave the original plan untouched; and the candidate
rule on hand-built tables, one failing each clause. Trade rows are saved to `logs/v143-fvg-bullish-rows.json` (gitignored) so a
rendering fault never costs a second replay. The replay itself runs
once, through `backtest-runner`, with a flushed per-ticker progress line and
a percent file deleted on completion (about 70 minutes at 6 workers).

## Parallelisation

One chain, honestly: features and geometry copies (script + tests) → the one
replay → results document and closed-table row. The replay needs the script
finished; the document needs the replay's output.
