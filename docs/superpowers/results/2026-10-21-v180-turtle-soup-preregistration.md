# v180 pre-registration — Turtle Soup entry, structural arm (bullish, `2w`)

Spec: `docs/superpowers/specs/2026-10-21-v180-turtle-soup-entry-design.md`.
Plan: `2026-10-21-v180-turtle-soup-entry` (index `docs/superpowers/plans/2026-10-21-v180-turtle-soup-entry_0-index.md`, tasks V180-10..V180-14).
Edge: expectancy. Screen: `screen-turtle_soup` SCREEN-PASS (ledger).

**Written before any v180 outcome existed.** When this file is committed, no v180 arm JSON, pilot, MDE, fold or VALIDATION run exists, and it contains no performance figure of the structural arm. The only figures quoted are the screen's, from its own ledger row. Nothing above `## Readings` changes after this commit; each stage appends one reading below it.

## Hypothesis (frozen by the spec, one cell, no grid)

A completed daily bar `t` that trades under the lowest low of bars `t-20 .. t-1` (`L`), where the latest bar holding `L` is at least 4 bars before `t`, and that closes back above `L`, predicts a rebound. The arm buys it at the next session's open, with the stop under the sweep bar's own low and the target at the nearest level-map level inside the 1.5–2.5 R:R band. Adding these trades to the book raises its decided win rate (A1) and does not lower its ExpR beyond the clause-2 margin.

The screen evidence covers the trigger only (paired ΔExpR +0.316R [+0.254, +0.381], N = 10,438, PIT S&P 500 2011–2019, yfinance, fixed 1.5/3 ATR race). This structural shape was never screened. The spec's prediction: a positive but small ExpR on the added rows and a win rate below the book's. The base case is a fail on the win-rate clause.

## Instrument

- Code: `main` at `107140ab` (on top of the `merge(v180)` commit).
- Producer: `scripts/backtest/measure_arms.py` (standard v100 producer), engine `strategy` (`arms/strategy_engine.py`), instrument v1. No bespoke instrument.
- Baseline arm: the knob at its default `off` (every existing strategy, no Turtle Soup). Component arm: `--knob TURTLE_SOUP_RESEARCH_MODE=structural` (the same rows plus Turtle Soup inside the scoped `("bullish", "2w")` research cell, `turtle_soup_research.RESEARCH_CELL`). The live `STRATEGY_GATES["Turtle Soup"]` stays `{"directions": ()}`.
- Subset proof: `tests/backtesting/test_turtle_soup_engine.py` shows on a fixture that every baseline row appears unchanged in the component (`population_split` gives `removed == []`, `changed == []`). Each stage re-checks it: `validate_component.py --stage reachability` prints the split, and the permutation harness refuses a non-additive pair.
- Plan constructor: the live `build_strategy_plan` on bars `<= t`; exit `simulate_exit(..., scale_out=True)`, which for this strategy takes `next_open_entry.next_open_exit`.
- Data source: **`--data-source alpaca`** on every producer and replay command (v162 rule). Alpaca history store manifest `9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60`, feed `sip`, adjustment `all`. The screen ran on yfinance bars. The change is disclosed and decides nothing.
- Membership: `data/universe/sp500_membership.csv`, sha256 `183a57080d1414bdfa45a5a15b58aed41f86bf19cb4b9ae4788d24fc38f6dc32`, read only for the descriptive universe share.

## Frozen values

| Item | Frozen value | Source |
|---|---|---|
| Strategy / horizon | `Turtle Soup`, bullish only, `2w` only | spec § 1–2; `RESEARCH_CELL` |
| Trigger | `channel = 20`, `min_age = 4`, close-confirmed reclaim; parity with `screen/ideas/turtle_soup.events` bar for bar | spec § 1; `turtle_soup.CHANNEL`, `MIN_AGE` |
| Entry | market-on-open at session `t+1` (`next_open_exit`); never the signal close | spec § 3 |
| Open at or below the stop | no trade, counted `cancelled_open_through_stop` | spec § 3 |
| Stop | `Low[t] − 0.25 × ATR14[t]` (`STRUCTURE_BUFFER_ATR`, Wilder ATR14 on bars `<= t`), routed through `_bounded_stop` | spec § 3 |
| Risk cap | drop, never squeeze: `2w` `max_risk_pct` 3.0%. Builder drop from the signal close (`risk_cap`); re-checked from the fill price (`cancelled_risk_cap_fill`). The stop is never moved | spec § 3; `STRUCTURAL_DROP_STRATEGIES` |
| Target | the nearest level-map resistance whose R:R from the signal close lies in `[MIN_RISK_REWARD_RATIO, MAX_RISK_REWARD_RATIO]` = `[1.5, 2.5]`; no level in the band = no plan (`no_level_in_band`); the synthetic `entry + 2.5R` fallback never fires | spec § 3 |
| Management | one whole-position leg: `tp1_fraction 1.0`, `breakeven_trigger_fraction 1.0`, no TP2, no runner | spec § 3; `PLAN_SHAPES` |
| Hold cap | 10 sessions, fill session = session 1; the 10th session closes at its close (`time_exit`, daily close proxy) | spec § 3; `SESSION_ONE_HOLD_CAP` |
| Gaps | an open beyond the stop fills at the open (`gap_stop`), an open beyond the target fills at the open (`gap_target`), the live `plan_manager.gap_stop_fill` / `gap_target_fill` convention; same-bar stop before target | spec § 3 |
| R | measured from the fill price to the stop | spec § 3 |
| Costs | Turtle Soup rows net of 5 bps a side (`apply_frictions`) plus `commission_r()` (0.02R at the default basis); baseline rows gross and byte-identical | spec § 3; `turtle_soup_research.net_r` |
| One trade at a time | per (ticker, strategy, horizon), as every `StrategyEngine` cell | `StrategyEngine.iter_trades` |
| Windows | Stage −1 pilot 2018-06-01..2020-12-31 (pilot ticker prefix); Stage 0 fold-train 2018-06-01..2022-12-31; Stage 2 walk-forward 2021 / 2022 / 2023; Stage 3 VALIDATION 2024-01-01..2025-12-31, **one shot** | `arms/windows.py` |
| Selection rule | none: one frozen cell, no grid | spec § The funnel |
| Bootstrap | ticker-cluster, 10,000 resamples, seed 42 | `acceptance.BOOTSTRAP_RESAMPLES` |

**Hold-cap parity (the spec's quant-engineer check).** The screen's `CAP = 10` exits at the close of bar `t+10`. This plan fills at the open of `t+1` (session 1) and closes the 10th session at the close of `t+10`. The two count the same bars, so the results doc has nothing to disclose beyond this line.

## Acceptance amendment (v119 A1–A4, adopted verbatim; it relaxes no threshold)

The standard `delta_standardised_win_rate` weights strata by the baseline's `(strategy, horizon)` mix and drops strata the baseline lacks. A new strategy's stratum is therefore weightless, and ΔWR is exactly 0 in every draw. Clause 5 and the Stage 0 MDE inherit that zero. Therefore:

- **A1 — clause 1 instrument.** Pooled (unstandardised) ΔWR over decided trades, `WR(component) − WR(baseline)` (`acceptance.delta_pooled_win_rate`, selected by `--wr-statistic pooled`), the same ticker-cluster bootstrap, 10,000 resamples, seed 42. Pass: point > 0 **and** one-sided p < 0.05.
- **A2 — clause 5 instrument.** `permutation_test.py --shift-replay`: the circular entry shift (`bt.ENTRY_SHIFT`, shifts drawn from `[20, 200)`), n = 200, seed 42, statistic = A1. Only the added strategy is replayed under each shift; the real baseline stays fixed. Pass: p < 0.05 at VALIDATION. A missing p is a FAIL.
- **A3 — Stage 0 MDE statistic.** `mde_paired` with the A1 statistic. The TRAIN effect compared against it is the A1 point estimate on the fold-train arms (`--train-effect-from-arms`).
- **A4 — no other change.** Thresholds, windows, the bootstrap, and clauses 2, 3, 4 and 6 are as written in `docs/claude/backtest-methodology.md` § Acceptance gate. Clause 3 (geometry) is applied, and a geometry failure is not waived because the plan shape differs. Clause 6 is `SKIPPED` (not a subset feature).

The instrument was committed and merged before this file (V180-2, V180-3, merged in V180-9).

## Gates (verbatim from the spec)

Every command runs from the repo root.

- **Stage −1 reachability.**
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/measure_arms.py --stage pilot --knob TURTLE_SOUP_RESEARCH_MODE=structural --preregistration docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md --out logs/v180/pilot.json --data-source alpaca`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/validate_component.py --data-source alpaca --stage reachability --arms logs/v180/pilot.json --title "v180 Turtle Soup structural -- stage -1 reachability" --window 2018-06-01..2020-12-31`
  - Gate: the knob is reachable, changed outcomes are nonzero and the split reads `removed=0 … changed=0`; else refused, budget intact.
- **Stage 0 MDE (A3).**
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/measure_arms.py --stage selection --knob TURTLE_SOUP_RESEARCH_MODE=structural --preregistration docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md --out logs/v180/selection.json --data-source alpaca`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/validate_component.py --data-source alpaca --stage mde --arms logs/v180/selection.json --wr-statistic pooled --train-effect-from-arms --mde-method paired --title "v180 Turtle Soup structural -- stage 0 MDE" --window 2018-06-01..2022-12-31`
  - Gate: the A1 TRAIN point below the paired MDE prints `REFUSED`; the shot is refused, budget intact.
- **Stage 1 selection.** No command. It **tests nothing**: one cell, no grid, and `plateau_report()` on a one-element grid always returns a plateau. It is stated, not counted as evidence.
- **Stage 2 walk-forward.**
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/measure_arms.py --stage walkforward --knob TURTLE_SOUP_RESEARCH_MODE=structural --preregistration docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md --out logs/v180/walkforward.json --data-source alpaca`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/validate_component.py --data-source alpaca --stage walkforward --arms logs/v180/walkforward.json --wr-statistic pooled --title "v180 Turtle Soup structural -- stage 2 walk-forward" --window 2021-01-01..2023-12-31 --out-json docs/superpowers/results/v180/walkforward.json`
  - Gate: `gate_win_rate` on the A1 fold rows: at least 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30 **decided added Turtle Soup trades**.
- **Stage 3 VALIDATION, one shot, only after the partner's explicit go.**
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/measure_arms.py --stage validation --knob TURTLE_SOUP_RESEARCH_MODE=structural --preregistration docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md --out logs/v180/validation.json --data-source alpaca`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/permutation_test.py --arms logs/v180/validation.json --shift-replay --wr-statistic pooled --n 200 --seed 42 --data-source alpaca --out-json docs/superpowers/results/v180/permutation.json`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/validate_component.py --data-source alpaca --stage validation --arms logs/v180/validation.json --wr-statistic pooled --permutation-p <p_value from permutation.json; the flag is omitted when p_value is null, which fails clause 5> --title "v180 Turtle Soup structural -- stage 3 VALIDATION" --window 2024-01-01..2025-12-31 --out-md docs/superpowers/results/v180/validation-gate.md --out-json docs/superpowers/results/v180/validation-gate.json`
  - `MEASURE_ARMS_UNIVERSE=cache python scripts/backtest/turtle_soup_report.py --arms logs/v180/validation.json --out-json docs/superpowers/results/v180/badge.json`
  - Gate: all six clauses with A1/A2 (clause 3 applied, clause 6 `SKIPPED`) **and** the badge check on the added rows: `win_rate >= 50` over win+loss, `expectancy_r > 0`, N ≥ 15, scratches + timeouts ≤ 50% of closed, time-cap exits counted as timeouts.

## Verdict mapping (ledger row `v180-turtle-soup-structural`)

| Funnel ended at | Ledger verdict |
|---|---|
| Stage −1 refused (unreachable, zero-diff) | `UNMEASURABLE` |
| Stage 0 `REFUSED` | `NO-LIFT` (VALIDATION not spent, budget intact) |
| Stage 2 `FAIL` | `NO-LIFT` (VALIDATION not spent) |
| Stage 3: gate `PASS` and badge `PASS` | `PASS` |
| Stage 3: anything else | `FAIL` |

A pass ships nothing. It licenses the follow-on change in the spec's "If the arm passes VALIDATION". A fail closes Turtle Soup under this shape. It never re-enters the funnel with a retuned `channel`, `min_age`, stop buffer, R:R band or hold cap, and arm A (the screened 1.5/3 ATR shape) is not revived.

## Disclosures fixed before any outcome

- **Costs on the added rows only.** Baseline rows stay gross (byte-identical); Turtle Soup rows are net. Clause 2 and the badge's `expectancy_r > 0` therefore compare a net cohort with a gross book. The bias runs against the arm. Clause 1 and the badge win rate are unaffected, because costs never flip a win or a loss.
- **Two risk-cap readings**, reported apart: `risk_cap` (builder, from the signal close) and `cancelled_risk_cap_fill` (from the fill).
- **"No level in the band" is read literally.** Candidates are pre-filtered to the band, so `select_structural_target`'s synthetic fallback never fires.
- **Per-fold N** counts decided added Turtle Soup trades, which is stricter than all added trades.
- **Universe.** The producer's cached universe is today's watchlist. PIT S&P 500 membership per signal date is reported as the added-row share outside the index. It is never used to exclude rows after the fact.

## Reported at every stage that runs (descriptive, never gating)

Read from the `<stage>.turtle_soup.json` sidecar (`arms/turtle_soup_report.measure`):

- drop and cancel shares of signals by reason (`risk_cap`, `no_level_in_band`, `plan_other`, `cancelled_open_through_stop`, `cancelled_risk_cap_fill`, `not_triggered`, `position_open`);
- each excluded population's screen-style outcome (the screen's own `race()`);
- sweep depth `(L − Low[t]) / ATR14[t]` for kept and dropped plans;
- the share of trades stopped within 2 sessions;
- the exit mix (target / stop / gap / time cap) with the decided win rate;
- ExpR and win rate with SPY above and below its 200-day SMA;
- maximum and p95 Turtle Soup signals per day;
- the added-row share outside the S&P 500.

## Readings

### Stage −1 — reachability (pilot 2018-06-01..2020-12-31), 2026-10-22

- Exit codes: producer 0, reachability 0.
- `knobs: {'TURTLE_SOUP_RESEARCH_MODE': 'structural'} baseline N=907 component N=919 changed outcomes: 12`
- `split removed=0 added=12 changed=0 is_subset=False` (additive: 12 added rows, baseline untouched)
- Verdict: `REACHABLE -- the component changes trades; Stage 0 may proceed.`, so continue to Stage 0.
- Descriptive (pilot, never gating), from `v180/pilot.turtle_soup.json`: signals 53; shares by status trade: 0.226, risk_cap: 0.472, no_level_in_band: 0.151, plan_other: 0.000, cancelled_open_through_stop: 0.038, cancelled_risk_cap_fill: 0.113, not_triggered: 0.000, position_open: 0.000; sweep depth median kept 0.225 / dropped 0.215 ATR; early-stop share 0.75; exit mix target 0.083, stop 0.667, gap 0.250, time cap 0.000 (decided win rate 8.3%, n=12); signals per day max 3, p95 1.0; added-row share outside the S&P 500 0.25.
