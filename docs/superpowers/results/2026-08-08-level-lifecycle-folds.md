# Edge Engine v4 — Task E33: Phase-E2 component fold decisions

Generated 2026-08-08T20:47:54+00:00 in 11.5 min.

## Pre-registered selection rule (quoted verbatim, fixed before data contact)

> anchored expanding folds — train 2018→fold-start, test years 2021 / 2022 / 2023. A component passes if pooled test `expectancy_r` improves vs baseline in **≥ 2 of 3 folds**, no fold degrades baseline expectancy by more than 0.05R, and N ≥ 30 per fold. Components that fail are documented and dropped — no second grid on the same hypothesis.

Constants as run: improving folds ≥ 2, max degradation 0.05R, min N 30.

## Setup

- Universe: `sp500` — 503 symbols, 11 strategies × 10 horizons
- Exit model: v2 + scale-out, `tp2_mode=levels`, frictions ON (matches the E22 friction-adjusted baseline tooling's own defaults)
- OHLCV: `data/backtest_cache/` (same cache the E22 baseline was measured on)
- Each (symbol, strategy, horizon) backtested once per leg; folds sliced by entry_date

## Results

### LEVEL_LIFECYCLE_STOPS_ENABLED — **PASS**

| fold | N | baseline expR | component expR | delta |
|---|---:|---:|---:|---:|
| 2021 | 2030 |   0.1376 |   0.1327 |  -0.0049 |
| 2022 | 1163 |  -0.1065 |  -0.0855 |  +0.0209 |
| 2023 | 1541 |   0.0929 |   0.0937 |  +0.0007 |

Pooled delta expectancy_r: +0.0056

## Not run — the harness cannot observe these

Registering these would score a meaningless 0.0000 delta and burn their one-shot pre-registration, so they are deliberately NOT run.

- **DATA_DRIVEN_STOPS_ENABLED** — E31/E32 reach plan_engine.build_strategy_plan only; the backtest sizes through backtest._trade_plan_at, which takes no stop_mult/tp2_r. Needs those threaded through run_backtest first.
- **REGIME_GATES_ENABLED** — The wiring objection is FIXED (P0: market_context.attach/get now supplies entries_for with a ctx_regime series in both the backtest and the live scan), but the gate is still inert for a second, stronger reason: its pre-registered TRAIN shot ran on 2026-08-08 and denied ZERO of 44 (strategy, regime) cells, so REGIME_ALLOW is empty by evidence rather than by omission. Re-running this without new bear-regime data would only re-measure a table that is empty on purpose -- see design doc section 5.5.
- **LEVEL_LIFECYCLE_TARGETS_ENABLED** — Structurally cannot fire, measured 2026-08-08 over 12 symbols x 11 strategies x 10 horizons: of 428 entry bars, 248 had a gatekeeper in the path and 180 had none -- and the pull-in was rejected by RR_FLOOR in 248 of 248. Pulling TP1 just inside a blocker yields median 0.063 R:R against the frozen 0.30 floor, a 5x gap that no choice of blocker closes (farthest clears in 0.4% of bars, king in 0%). Blockers sit adjacent to entry, so the 'realistic' target is too close to be a trade. Registering it would score exactly 0.0000 -- which is what a slice run did score. Fix the concept or drop it; do NOT lower RR_FLOOR to make it fire.
- **PYRAMIDING_ENABLED** — E38 lives in the live plan manager; plan_engine.simulate_exit has no pyramiding concept, so the backtest cannot observe it.
- **EARNINGS_BLACKOUT_DAYS** — E18's gate was never wired into the scan or backtest path.

## Observations

_Written after reading the numbers above; failures are recorded, not fixed._

**Effective universe: 78 symbols, not 503.** `--universe sp500` enumerates 503
names but only those present in `data/backtest_cache/` produce a frame; the
other 425 are skipped instantly. 78 is the same effective set the P2a regime
evidence ran on, so the two P-components of this branch are measured on
identical data. 10,835 baseline trades / 10,773 component trades.

**Verdict: PASS, but read the margin honestly.** The rule is satisfied — 2 of 3
folds improve, the one degrading fold (2021, −0.0049R) is an order of magnitude
inside the 0.05R tolerance, and every fold has N in the thousands. It is a real
pass on a rule fixed before the run, and it is not going to be re-read as a
failure after the fact.

But the pooled effect is **+0.0056R**, and it is not evenly earned:

- **2022 (+0.0209R) does all the work.** That is the bear year, and it is the
  intuitive place for this component to help: anchoring a stop behind a level
  price has actually *tested and held* matters most when price is repeatedly
  probing support. The mechanism and the fold that moved agree, which is worth
  more than the pooled number.
- **2023 (+0.0007R) is a rounding error.** It counts as an "improving fold"
  under the rule, so the 2-of-3 clause is carried by a delta indistinguishable
  from noise. Anyone treating this as two independent confirmations is
  over-reading it; the honest description is *one fold moved, one was flat, one
  was slightly negative*.

**Trade count barely changed** (10,835 → 10,773, −0.6%), which is the expected
signature: the component only ever *widens* a stop, capped by `max_risk_pct`,
and re-derives the target to preserve the frozen R:R. It is not buying
expectancy by cutting trades.

**Recommendation:** the flag has earned its pass and can be considered for
default-on, but on the strength of one fold. The natural confirmation is the
VALIDATION window (2024–2025), which this harness's anchored folds do not
touch — that shot is unspent.

**Its sibling was not run.** `LEVEL_LIFECYCLE_TARGETS_ENABLED` failed the
pre-registration observability check and is listed above under "Not run"; see
design doc §7.6 for the measurement.

**Process note, recorded against re-interpretation.** A first execution of this
component on 2026-08-08 accidentally ran on a 3-symbol universe — this
worktree's `data/watchlist.json` is gitignored and had been auto-seeded to the
default `["AAPL","MSFT","SPY"]`, so `--universe watchlist` silently measured
three tickers and reported FAIL (N=16 in the 2022 fold, below the N≥30 clause).
That run was mis-scoped, not a result: it is discarded on the universe defect,
which is visible in its own setup line, **not** because of the verdict it
produced. The pre-registered rule was not touched between the two runs.

