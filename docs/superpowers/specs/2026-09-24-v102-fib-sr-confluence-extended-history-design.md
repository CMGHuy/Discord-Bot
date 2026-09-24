# v102 — Fibonacci × Rolling S/R confluence, on history extended to 2010

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** none for this spec; bot minor if a direction passes VALIDATION and the flag ships
**Edge:** expectancy

## Why this, and the honest prior

v101 closed no-lift (`results/2026-09-24-v101-fib-diagnostic.md`). Under
current arithmetic (post-`a3a903d6` 2% stop cap), Fibonacci on TRAIN
2020-01-01..2023-12-31 is bullish N=288 WR 28.8% ExpR +0.039 and bearish
N=94 WR 25.5% ExpR −0.091. It fails the `win_rate >= 50` badge clause on
**win rate, not sample size**: at N=288 the 95% interval on WR is about
±5pp, so more data alone narrows the estimate around 29% and cannot reach 50%.

A longer history does help one kind of mechanism: **a filter that cuts N
hard**. This spec tests one such filter, confluence with the one level family
that is nearly independent of Fibonacci, and gives it the room in N it needs
by extending history back to 2010.

**Prior:** the filter must roughly double the win rate. Filters in this repo
have typically moved WR by a few points. The design is built to reach "no"
cheaply and early (Stage 0 below).

**Priority note (recorded, overridden by the partner):** two open findings
from v101 rank higher by `edge-priorities.md`. Every registry badge predates
the 2% cap, including the two VALIDATED rows, MACD and Volume Profile. And
`apply_level_lifecycle` can widen live market-entry plans past the 2% planned
loss. The partner chose to continue Fibonacci first; both findings stay open.

## What is closed and must not be re-run

- v101 mechanisms #1 structural-stop filter, #2 deeper-ratio stop, #4 reclaim
  entry; v31 horizon splits; v84 1.0 extension; the 2026-09-10 refresh; the
  v93 bearish arm without a mechanism.
- v17 `REGIME_ALLOW` (regime filters). v102 adds no regime condition.
- v49 `EFFECTIVE_CONFLUENCE_ENABLED` measured *confluence counting on the
  confluence path*. v102 is a *strategy-source entry filter* on one named
  independent family, a different component. v49's redundancy measurement is
  the reason for choosing Rolling S/R: it is the only near-independent family
  (off-diagonal redundancy 0.235, against Fibonacci/Zigzag 0.838).

## The mechanism

Config flag `FIB_SR_CONFLUENCE_ATR: float = 0.0` (0 = off, bit-identical to
today). When it is `> 0`, `fibonacci_entries`
(`swingbot/core/market/entry_filters.py`) keeps a bullish or bearish signal at
bar i only if:

```
min(|tested_level_i − rolling_support_i|, |tested_level_i − rolling_resistance_i|)
    <= FIB_SR_CONFLUENCE_ATR × ATR14_i
```

- `tested_level_i`: the ratio level in `DEFAULT_PARAMS["Fibonacci"]["ratios"]`
  nearest to `Close_i`, the same level `is_testing` already found. It is the
  retracement level, **never the swing extremes**: Rolling support over a
  shorter window often equals the Fibonacci swing low, so comparing against
  the extremes would be trivially true.
- `rolling_support_i` / `rolling_resistance_i`:
  `Low/High.rolling(h["sr_lookback"]).min/max().shift(1)`, exactly as
  `swingbot/core/market/levels.py:240-246` computes them. The `shift(1)`
  keeps it free of lookahead.
- `ATR14_i`: `compute_shared_gates`' ATR if it exposes one, otherwise
  `indicators.atr(df, 14)`. The plan pins which.

The filter lives in the entry function, which both the backtest and the live
scan call through `entries_for`, so parity holds by construction. It never
touches stops, targets or exits.

## Extended history

- **Separate cache.** `scripts/data/fetch_backtest_data.py` gains `--start`
  and `--cache-dir`. `swingbot/core/marketdata/backtest_cache.CACHE_DIR`
  becomes overridable through a `BACKTEST_CACHE_DIR` environment variable,
  read at import, with the default unchanged. The fetch covers the watchlist
  tickers plus the market-context benchmark, from 2010-01-01 to 2025-12-31,
  into `data/backtest_cache_ext/`. **The shared `data/backtest_cache/` is not
  touched.** Back-filling it would move indicator warm-up and silently shift
  the numbers behind every closed result.
- **All v102 runs read the extended cache**, including VALIDATION, so TRAIN
  and VALIDATION share one data source.
- **Survivorship bias, declared.** The universe is today's watchlist. Stocks
  that later failed or delisted are absent, and the bias grows with distance
  from today. The pre-registration states it. Results from 2010–2015 are read
  with that in mind.
- **Tickers without 2010 data** (later IPOs) contribute from their first
  bars. The universe filter (`liquidity_reason`, `data_quality_issues`) is
  applied as today.

## Windows and funnel (pre-registered before any scoring; one verdict per direction)

| Stage | Window | Rule |
|---|---|---|
| 0 count (free) | TRAIN_EXT 2010-01-01..2023-12-31 | Signals surviving at each grid tolerance, per direction and per fold year. If the loosest tolerance cannot reach decided N >= 30 in a direction, that direction closes no-lift here |
| 1 selection | TRAIN_EXT | Grid `FIB_SR_CONFLUENCE_ATR ∈ {0.25, 0.5, 0.75, 1.0}`. A cell passes on the badge clauses: WR >= 50, ExpR > 0, decided N >= 30, scratch+timeout share <= 50%. **Plateau:** the chosen cell's grid neighbours must also pass. Winner = highest ExpR among plateau-passing cells |
| 2 walk-forward | anchored annual folds, train from 2010-01-01, test years 2013..2023 (11 folds) | Of the folds with N >= 15, at least 2/3 have ExpR > 0; at least 3 folds must have N >= 15 |
| 3 VALIDATION | 2024-01-01..2025-12-31 | **One shot per direction, ever.** Badge clauses with N >= 15 |

The bullish run uses the live gate. The bearish run is unmasked through
`gate_override`, with v93's laggard rule applied, as in
`measure_bearish_arms.py`. Measurement reuses `measure_fib_diagnostic.py`'s
collection path where possible. Anything new gets the same
`_trade_plan_at`-reproduction check (0 stop mismatches).

## Wiring (only for directions that pass VALIDATION)

- Flip `FIB_SR_CONFLUENCE_ATR` to the chosen tolerance in `config.py` and
  `.env.example`.
- Rewrite `STRATEGY_GATES["Fibonacci"]` to list only the passing directions,
  with current figures in its comment.
- Re-emit the registry row(s) through `run_backtest_range.py --emit-registry`,
  never by hand. If both directions pass, the registry key first gains
  `direction`.
- Add the closed row to `docs/claude/backtest-methodology.md` whatever the
  outcome.

## Testing

- `fibonacci_entries` with the flag at 0 is bit-identical to today (a series
  equality test on a real cached ticker).
- A synthetic frame where the tested level sits within, and just outside,
  `tol × ATR` of the Rolling support: the signal is kept and dropped
  respectively, in both directions.
- No lookahead: poisoning bars after i does not change the filter at i.
- `BACKTEST_CACHE_DIR` unset gives the default path; set, it redirects
  `cache_path`.
- The full suite runs once, as the plan's final task.

## Non-goals

- No regime condition, no horizon mask, no stop, target or exit change.
- No change to the shared cache, the shared TRAIN/VALIDATION constants or
  `ANCHORED_FOLDS`. v102's windows are its own constants.
- No change to other strategies.

## Parallelisation

- **Sequential:** (cache override + flag, default 0) → extended fetch →
  Stage 0 count → pre-registration commit → Stages 1–3 → wiring. Stage 0
  needs the filter to count survivors, so the flag, still off by default,
  exists before any measurement. Each later stage reads the previous stage's
  output.
- **Group 1 (parallel):** the `BACKTEST_CACHE_DIR` override and the
  `FIB_SR_CONFLUENCE_ATR` flag with its entry-filter tests touch disjoint
  files, so both can be built before Stage 0.
