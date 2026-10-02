# Support/Resistance breakout

`ENTRY_FUNCS["Support/Resistance"]` = `support_resistance_entries` · signal
`support_resistance_signal` · sizing **structural** (`_sr_plan`) · gate
**bullish, horizons 2m / 3m**. Shared rules:
[shared-mechanics.md](shared-mechanics.md).

## Idea

The classic breakout from a base. Price consolidates in a tight range under a
ceiling, then closes through that ceiling on heavy volume with a strong bar.

## Entry rule (bullish; bearish mirrors)

`resistance = max(High over sr_lookback bars)`, shifted 1, so today's bar is
excluded. The lookback runs from 10 bars (2w) to 270 (9m); it is 60 on 2m and
90 on 3m.

1. **Breakout:** `close[t−1] ≤ resistance[t−1]` and `close[t] > resistance[t]`.
2. **Volume:** `Volume ≥ 1.5 × mean20(Volume)` (`SR_VOLUME_MULTIPLE`).
3. **Tight base:** the 10 bars before today span `≤ 4 × ATR14` (`base_atr`).
4. **Strong close:** `close ≥ High − 0.4 × (High − Low)` (`close_frac`).
5. **No exhaustion gap:** `Open ≤ resistance × 1.03` (`gap_pct` 3%).
6. Shared: `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm`. There is
   no `vol_ok`, because rule 2 replaces it.

Bearish: a breakdown through `support = min(Low)`, a close near the low, an
open ≥ support × 0.97, and the bear gates.

Optional `SR_MIN_LEVEL_TOUCHES` (default 0, off) requires the level to have
rejected price N times first. It is closed (v84).

## Plan

- **Stop:** `entry × (1 − min(sr_stop_pct, 2)%)`. Every `sr_stop_pct` is ≥ 3,
  so the stop is **always exactly 2%** below entry, before the level-lifecycle
  step.
- **TP1 candidates** (`sr_target_candidates`):
  - the rolling high/low over `sr_lookback`, shifted 1;
  - a percent band `entry × (1 ± pct)`, where `pct` is interpolated between
    `sr_target_min_pct` and `sr_target_max_pct` by breakout volume strength
    `clamp((volratio − 1.5) / (3.0 − 1.5), 0, 1)`;
  - both ends of that band.
- **In practice:** on a bullish breakout the rolling high is the level just
  broken, so it sits *below* entry. The band on 2m/3m starts at +16–18%,
  far past the 2.5R cap (+5% at a 2% stop). **So TP1 is almost always the
  synthetic 2.5R price, entry + 5%.**

Exits use the defaults: trail 2.5 × ATR, TP2 on.

## Measured

| Source | Window | N | WR | ExpR | Note |
|---|---|---|---|---|---|
| Registry (run 2026-09-10) | TRAIN 2020–23 | 247 | 45.7% | +0.316 | **WEAK** (legacy badge refresh, pre-2% cap) |
| v84 `min_level_touches` K=1..3 | TRAIN | ≈ same | 44.9 / 44.3 / 44.2% | — | stable plateau but toothless, so **closed** |
| v104 structural stop, out-of-scope arm | TRAIN 2010-2025, universe 74 | 1399 | 33.6% | +0.250 | `results/2026-09-28-v104-partA.md` |
| v104 structural stop, in-scope arm | same | 907 | 43.9% | +0.357 | Tier 2 (lower bound +0.281), beats baseline, clears the fold check (12/12) — **PROCEEDED to the 2026 holdout** |
| v104 structural stop, in-scope arm | HOLDOUT 2026-01-01..2026-09-25 | 45 | 40.0% | +0.139 | bootstrap lower bound **−0.143 → FAIL** (Tier 2's deciding clause); shot spent, final. `results/2026-09-28-v104-holdout.md` |

**v113 1w cells (Part B, TRAIN 2010-01-01..2025-12-31, universe 74, horizon 1w masked):** bullish N=921, WR 30.8%, ExpR +0.170, lower bound +0.087, cleared Tier 2 at Stage 1; Part B bar failing clauses: wr; folds 12 qualifying / 11 positive. bearish N=148, WR 32.4%, ExpR +0.132, lower bound -0.079, no tier; Part B bar failing clauses: wr, lower_bound; folds 4 qualifying / 2 positive. Neither cell proceeds to the holdout (Part B's bar is Tier 1 plus a bootstrap lower bound > 0; every 1w cell fails Tier 1 on WR); no `cells` admission, no registry row. Source: `results/2026-09-30-v113-partB.md`.

## Pseudocode

```python
R = rolling_max(High, L).shift(1)
fire if Close[t-1] <= R[t-1] and Close > R and Vol >= 1.5*mean20(Vol)
        and range(High,Low over t-10..t-1) <= 4*ATR and Close >= High - 0.4*(High-Low)
        and Open <= 1.03*R and bull_regime and Close > MA50 and atr_ok
stop = entry*0.98; tp1 = nearest candidate in [1.5R, 2.5R] else entry + 2.5R
```
