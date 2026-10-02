# v121 — Causal structure and volume-in-context features in the entry snapshot

**Version:** ui 1.21.0 · bot 2.0.0 (at writing)
**Bump:** bot patch (new fields on stored trade records; no alert, gate or exit changes)
**Edge:** none (integrity) — measurement only; it is the shared instrument v122 (expectancy) and v123 (harvest) are built on

## Why

The partner's volume handbook (`docs/strategy/volume-in-context.md`) argues
volume is meaningful only beside structure (HH/HL), candle range, price
progress and key levels. The bot records none of those at entry: the v93
entry-context snapshot (`swingbot/core/edge/context.py`) holds
`vol_ratio_20` but no structure, and its `swing_high_atr`/`swing_low_atr`
keys are declared in `FEATURE_KEYS` yet never filled (always `None`).

This spec adds one pure, causal module that computes those concepts, stamps
them onto every entry snapshot (live and replay), and ships a descriptive
report. It gates nothing, scores nothing and changes no plan.

## Scope

In: a new `swingbot/core/market/structure.py`; new snapshot keys in
`edge/context.py`; filling the two dead keys; a descriptive report script.
Out: any gate, score weight, exit rule, alert text or chart change. Those are
v122/v123 or later work, each with its own pre-registration.

## The causal pivot contract (load-bearing)

All structure features rest on **confirmed fractal pivots**: bar `i` is a
swing high when `High[i]` is strictly greater than the `k` highs before it and
greater than or equal to the `k` highs after it (mirror for swing lows),
`k = 3`. A pivot at `i` is **knowable only from bar `i + k` onward**. At
decision bar `t`, only pivots with `i <= t - k` exist. This is the single
place the confirmation lag lives; every consumer (v121 snapshot, v122 gate,
v123 exit) calls the same function, so no caller can reintroduce lookahead.

`confirmed_pivots(df, k=3) -> DataFrame` returns, per bar `t`, the index and
price of the last two confirmed swing highs and last two confirmed swing lows
known at `t` (NaN where fewer exist). It is vectorised and truncation-stable:
row `t` computed on `df` equals the last row computed on `df.iloc[:t+1]`.
Existing helpers (`indicators.zigzag_pivots`, `signals._swing_highs`) are not
reused: zigzag's threshold makes confirmation timing data-dependent, and the
nested `signals` helpers are private to divergence detection. `k` is frozen
at 3, not a search knob.

## Features (all computed at the entry bar `t`, from `df.iloc[:t+1]`)

Direction-aware features are expressed **for the trade's direction** (mirror
for bearish) so analysis never has to branch.

| Key | Definition | Lesson |
|---|---|---|
| `structure_state` | `"up"` if last confirmed SH > prior SH **and** last SL > prior SL; `"down"` if both lower; `"mixed"` otherwise; `None` with < 2 of either | 3 |
| `structure_aligned` | `structure_state` is `"up"` (bullish) / `"down"` (bearish); `None` if state is `None` | 3 |
| `last_pivot_held` | bullish: `Close[t] > last confirmed SL`; bearish: `Close[t] < last confirmed SH` | 3 |
| `hh_failed` | bullish: last confirmed SH ≤ prior SH; bearish: last confirmed SL ≥ prior SL | 4 |
| `swing_high_atr` | `(last confirmed SH − Close[t]) / ATR14[t]` (existing dead key, now filled) | 3 |
| `swing_low_atr` | `(Close[t] − last confirmed SL) / ATR14[t]` (existing dead key, now filled) | 3 |
| `vol_trend_10_50` | mean Volume over bars `t-9..t` ÷ mean over `t-49..t` | 1, 2 |
| `range_trend_10_50` | mean True Range over `t-9..t` ÷ mean over `t-49..t` | 4 |
| `progress_atr_10` | direction-signed `(Close[t] − Close[t-10]) / ATR14[t]` | 4 |
| `absorption_bar` | entry bar `Volume / mean20(prior) ≥ 1.5` **and** `(High−Low) / ATR14 ≤ 0.6` | 5 |
| `absorption_count_10` | number of absorption bars in `t-9..t` | 5 |
| `pullback_vol_ratio` | mean Volume of the **pullback leg** ÷ mean Volume of the **impulse leg** (below) | 2, 5 |

**Pullback / impulse legs** (bullish; mirror for bearish). Let `SH` be the
last confirmed swing high at `t` and `SL0` the last confirmed swing low before
`SH`'s index. Impulse leg = bars `SL0 .. SH`. Pullback leg = bars
`SH+1 .. t`. `None` if either leg has fewer than 2 bars, either mean volume is
zero/NaN, or `Close[t] > High[SH]` (price already past the high: not a
pullback). The pivot at `SH` is confirmed (≤ `t-3`), so bars `SH+1..t`
contain at least 3 bars whenever it is defined; bars between `SH` and
`SH+3` are read as ordinary volume, which is knowable — only the *pivot
label* is lagged.

The 1.5 and 0.6 absorption constants and the 10/50 windows are frozen
descriptive definitions, not search knobs; changing one is a new spec.

## Placement and data flow

`market/structure.py` holds the pure series functions (pivots, legs, the
feature frame). `edge/context.py:entry_context` calls one function,
`structure_features(df, direction) -> dict`, and merges its keys; the new
keys are appended to `FEATURE_KEYS` so the existing `{key: None}` default
covers short frames and old records. Because `entry_context` is already
called from both the live stamp (`planning/params.py:stamp_entry_context`)
and replay (`backtesting/backtest.py`, `backtest_scenarios.py`), both paths
gain the features with no new wiring. Short frames (< 60 bars) return all
`None`, never raise.

**Storage.** The snapshot travels as `entry_context` on the trade record
(`tracking/performance.py`). The plan must confirm with the `schema-change`
skill whether that is a JSON/JSONB payload (no Alembic revision; a missing
key on an old record reads as `None`, which is exactly the existing default,
not read-time upcasting) or a typed column set (then an additive revision per
`schema-evolution.md`). No backfill of historical records: a feature computed
today for a past entry would be computed on bars the original snapshot did
not have stamped, and the report already gets historical coverage from
replay.

## Report

`scripts/reports/volume_context_report.py` buckets **closed** trades by each
new feature (categorical as-is; continuous by fixed quintiles of the TRAIN
population) and prints N, win rate, ExpR per bucket, separately for
confluence-sourced and strategy-sourced trades and per direction. Inputs:

- `--source replay` — the confluence/strategy arm engines over **TRAIN
  2020-01-01..2023-12-31 only**. The script refuses any window touching
  2024-01-01 or later.
- `--source live` — the production trade book, monitoring only.

The report is descriptive. **It must not be used to choose v122's or v123's
grid values** — both grids are frozen in their own specs, written before this
report exists, precisely so no bucket table can leak into selection. The
live book overlaps the 2026 holdout that other pre-registrations (v104) are
waiting on; the report's header says so and prints no inferential statistic.

## Testing

- Pivot truncation: for every cut `t`, `confirmed_pivots(df.iloc[:t+1])`'s
  last row equals `confirmed_pivots(df).iloc[t]`; a pivot never appears
  before `i + k`.
- Each feature: hand-built frames with known answers (clean HH/HL uptrend →
  `"up"`, aligned, held; lower high → `hh_failed`; a 2-bar pullback on half
  the impulse volume → `pullback_vol_ratio == 0.5`; a high-volume inside bar →
  `absorption_bar`); bearish mirrors of each.
- `entry_context` keeps every pre-existing key's value byte-identical on a
  fixture (witness test captured before the change), and `entry_context` on
  < 60 bars returns `None` for every new key.
- Report: refuses a window ending after 2023-12-31 for `--source replay`.
- `no-lookahead` skill review on `structure.py` and `context.py`.

## Parallelisation

`market/structure.py` (pivots first, then legs and features) is a chain:
each function consumes the previous one. The `context.py` integration
consumes `structure_features`. The report consumes the stored keys. The
storage confirmation (schema-change skill) is independent of the feature
code and can run beside the pivot work. Full suite once at the end.
v122 and v123 both depend on this spec's `structure.py` contract and must
not start implementation until it is merged.
