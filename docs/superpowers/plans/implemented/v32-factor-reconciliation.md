# v32 Task 1 — Factor reconciliation

Input to Task 2 onward: the authoritative kept-factor list for
`swingbot/core/scanning/factors.py`, and the evidence behind every drop.

## Step 1: both factor sets, extracted verbatim

**From `confidence.py` (current lines noted; plan's stated 275-436 drifted by
~7 lines but the factor list itself matches):**

| Factor | Points | Lines |
|---|---|---|
| Target distance quality | 0-20 | 276-281 |
| Stop level confluence | 0-15 | 283-287 |
| Market regime alignment | 0/7/15 | 289-298 |
| ADX trend strength | 0-15 | 300-322 |
| MACD momentum alignment | 0-15 | 324-355 |
| RSI trend alignment | 0-10 | 357-391 |
| TTM Squeeze + volume breakout | 0-10 | 393-418 (side effect: appends to `scenario.target_sources`) |
| Candlestick pattern | 0-10 bonus | 420-436 (side effect: appends to `scenario.target_sources`) |
| Tight-stop penalty | 0 to -15 | 445-453 |

**From `quality.py`:**

| Component | Points | Lines |
|---|---|---|
| `component_regime` | 0/8/15 | 19-22 |
| `component_htf` | 0/8/15 | 25-28 |
| `component_confluence` | 0-20 | 31-34 |
| `component_volume` | 0-10 | 37-46 |
| `component_atr_percentile` | 0-10 | 65-72 |
| `component_distance` (trigger) | 0-10 | 75-82 |
| `component_badge` | 0/20 | 85-86 |
| `rs_points` | 0-10 | 114-117 |
| `mtf_points` | 0/3/6/10 | 120-123 |
| `breadth_points` | 0-5 | 126-129 |
| `candle_points` | 0-5 | 132-135 |
| `gap_penalty` | 0/-10 | 138-139 |

`swingbot/config.py:174` confirmed as `MIN_ALERT_CONFIDENCE_LEVEL`
(`default="4", options=["1".."5"]`) — the Global Constraints' "default is 4,
not 3" correction is accurate against the live code. The design spec's own
"What this deliberately does NOT change" section contradicts this with
"`MIN_ALERT_CONFIDENCE_LEVEL`'s default stays 3" — a defect in the spec
itself (it repeats the exact wrong claim the spec opens by correcting).
Flagged here for Task 13's documentation pass; `4` is authoritative for all
of this plan's work.

## Step 2: correlation measurement

Full script: `scripts/backtest/v32_factor_correlation.py`. Rather than
reconstructing full production `Scenario` objects at 500+ historical bars
(expensive: needs per-bar strategy-confluence simulation) or historical
universe-wide RS/breadth snapshots (needs per-date cross-sectional data this
repo doesn't retain), the measurement is scoped to exactly the factors the
Required Decisions table below needs a measured verdict for — the five that
are computable from a single ticker's `df` window alone: ADX, MACD, RSI, HTF
bias, MTF alignment. The other four pairs are decided by the input-identity
argument in Step 3 without needing a correlation number (see below).

Sampled every TRAIN-window (2020-01-01..2023-12-31) trade entry bar produced
by the existing backtest engine, across all 75 cached tickers x 10 horizons x
11 strategies, using the SAME production functions confidence.py/quality.py
call today (`adx_trend_strength`, `macd_momentum_aligned`,
`rsi_trend_aligned`, `get_htf_bias`, `rs_factors.mtf_alignment`), each fed
`df.iloc[:i+1]` only (NO-LOOKAHEAD). Correlated each function's own graded
**strength rank** (strong=3/moderate=2/weak=1/none=0, or the 0-3 MTF count
as-is) rather than its eventual point value, since `factors.py` doesn't exist
yet at this point in the plan (Task 3 is what extracts the point arithmetic)
and Spearman only needs the monotonic ordering, not the final scale.

Dispatched via the `backtest-runner` subagent (~7 min wall-clock, kept out of
the main context). **4337 TRAIN entry-bar samples**, zero missing data on any
of the 5 columns. 3 of 75 tickers (ARM, GEV, NBIS) contributed zero samples —
too little pre-2024 history (recent listings); not an error.

**Spearman correlation matrix (ordinal strength ranks):**

```
        adx     macd    rsi     htf     mtf
adx    1.000  -0.196  -0.117   0.118  -0.103
macd  -0.196   1.000   0.462   0.069   0.301
rsi   -0.117   0.462   1.000   0.217   0.392
htf    0.118   0.069   0.217   1.000   0.175
mtf   -0.103   0.301   0.392   0.175   1.000
```

Raw output: `data/v32_factor_correlation.json` (not committed — regenerable,
same convention as `data/backtest_cache/`). Full per-ticker log:
`docs/superpowers/results/2026-08-17-v32-factor-correlation.log`.

**No pair exceeds the |ρ| > 0.7 collapse threshold.** The highest magnitude
is MACD/RSI at 0.462 — a real but modest positive relationship (both read
momentum, but from different signals: histogram trajectory vs. oscillator
level), well short of redundant.

## Step 3: decisions

| Pair | Measured evidence | Decision |
|---|---|---|
| `confidence.regime` vs `quality.component_regime` | Not correlation-measured — both are the identical `SPY-trend vs scenario.direction` comparison, differing only in the "unavailable" default (confidence: 7, quality: 8/`_NEUTRAL`). Structurally the same function twice. | **Keep confidence.py's** (`factor_regime`). Task 3 ports it; Task 4's port list omits `component_regime` entirely — the plan's own task split already encodes this decision. Drop `quality.component_regime`. |
| `confidence.candlestick` vs `quality.candle_points` | Not the same detector by correlation, but by construction: `candle_points` takes a `candle_quality` kwarg to `score_plan()` that **no live caller ever supplies** (`engine.py::_build_quality_inputs`'s own docstring: "candle_quality... deliberately left out, not fabricated: candle_quality needs a specific touch-bar+level the scan loop doesn't track per plan"). It is dead code in production today — always `None`, always omitted from `score_plan`'s breakdown. `confidence.candlestick` is live: it runs `detect_confirming_pattern(df, direction)` on every scored scenario. | **Keep confidence.py's** (`factor_candlestick`, preserving its `target_sources` side effect). Task 4's port list omits `candle_points` — confirms this was already decided. Drop `quality.candle_points`. |
| `confidence.distance` (target) vs `quality.component_distance` (trigger) | Different inputs by construction: `scenario.target_distance_pct` (how far the take-profit sits beyond the minimum required move) vs `trigger_distance_pct` (how far price sits from the scenario's own entry trigger). Not measured — the plan's own text already argues these can't be the same signal. | **Keep both**, renamed for disambiguation: `factor_target_distance` (confidence.py) and `factor_trigger_distance` (quality.py). |
| ADX vs MACD vs RSI | Measured: max pairwise \|ρ\| = 0.462 (MACD/RSI), both other pairs weaker, ADX actually *negatively* correlated with both (-0.196, -0.117). None clears 0.7. | **Keep all three as independent factors.** No composite. This is the plan's speculative "if pairwise ρ > 0.7, merge" branch resolving to *no merge* — a genuine measured result, not a default. |
| `quality.component_htf` vs `factors.mtf_alignment` | Measured: ρ = 0.175 — weak. They read genuinely different things: `component_htf` is a single higher-timeframe EMA bias (bullish/bearish/neutral), `mtf_alignment` counts how many of 3 higher timeframes agree (0-3). | **Keep both.** The plan's text suggested "keep at most one (v33 revisits)" as a default, but the measured correlation is the "written justification" the plan's own general rule (`Rule: any pair with |ρ| > 0.7 collapses... unless a written justification says why both earn their place`) asks for — 0.175 does not support treating them as redundant. Left for v33 (the MTF spec, per this plan's own "Downstream" section) to revisit with better MTF granularity if it wants to fold HTF in. |
| `confidence.stop_confluence` vs `quality.component_confluence` (target-side) | Different sides by construction (stop vs target), matching the plan's own instruction. Not measured. | **Keep both**: `factor_stop_confluence` (confidence.py) and `factor_target_confluence_quality` (quality.py, renamed for disambiguation against the honesty-cap's own target-count base level — see the finding below). |

### An additional finding beyond the plan's Required Decisions table

`quality.component_confluence` scores **0-20 quality points from the same
`target_count`** that also sets the honesty-cap **base level** (Global
Constraints: "Base level from method count... remains the base... Quality
points... from a single merged factor set" — deliberately two separate
pools). This means the number of confirming strategies influences the final
score **twice**: once by raising the base level (and honesty cap), once more
by adding up to 20 quality points on top. This is exactly the shape of
problem this whole reconciliation exists to catch, and it is real — but it
is not an oversight this task can silently fix, for two reasons: (1) the
plan's own Required Decisions table explicitly pairs `component_confluence`
with `stop_confluence` and says "keep both," and (2) the Global Constraints
section explicitly frames base-level and quality-points as intentionally
separate pools, which is the same design that already shipped in `quality.py`
pre-v32 (this is not new to the merge). The design spec's own merged-factor
candidate table, however, **omits `component_confluence` entirely** — a
spec/plan drift worth Task 13 correcting. Decision: **keep it**, per the
plan's explicit instruction, renamed `factor_target_confluence_quality` to
make the distinction from the base-level count visible in the breakdown
("N strategies -> base Level X" from the honesty-cap line, vs "target
confluence quality: N strategies -> +M pts" from this factor) rather than
silently double-labeled. Flagged, not resolved differently — matches this
repo's convention (v31's registry-granularity reconciliation) of documenting
a real judgment call rather than deciding it unilaterally against explicit
plan text.

`gap_penalty`/`factor_gap` is similarly **dead in production today**
(`gap_fragile` is never computed by `_build_quality_inputs`; `config.py`
confirms `edge.gates.in_earnings_blackout` is defined but never called).
Unlike `candle_points`, there is no live equivalent factor already covering
this signal, and Task 4 explicitly lists `factor_gap` as a symbol to port.
**Kept per the plan's explicit instruction** — it will always be absent from
a live breakdown (per the `FactorContext`/`run_factors` contract, an absent
input is correctly omitted, not scored 0) until a future task wires gap
detection into the scan loop. Documented here so nobody mistakes its silence
in a live breakdown for a bug.

## Step 4: final kept factor list (input to Task 2+)

| # | Factor name | Points | Source |
|---|---|---|---|
| 1 | Target distance quality | 0-20 | confidence.py |
| 2 | Stop level confluence | 0-15 | confidence.py |
| 3 | Market regime alignment | 0/7/15 | confidence.py |
| 4 | ADX trend strength | 0-15 | confidence.py |
| 5 | MACD momentum alignment | 0-15 | confidence.py |
| 6 | RSI trend alignment | 0-10 | confidence.py |
| 7 | TTM Squeeze + volume breakout | 0-10 | confidence.py (side effect: `target_sources`) |
| 8 | Candlestick pattern | 0-10 | confidence.py (side effect: `target_sources`) |
| 9 | Tight-stop penalty | 0 to -15 | confidence.py |
| 10 | Relative strength | 0-10 | quality.py (`rs_points`) — newly gating |
| 11 | MTF alignment | 0/3/6/10 | quality.py (`mtf_points`) — newly gating |
| 12 | Market breadth | 0-5 | quality.py (`breadth_points`) — newly gating |
| 13 | HTF bias | 0/8/15 | quality.py (`component_htf`) |
| 14 | Volume ratio | 0-10 | quality.py (`component_volume`) |
| 15 | ATR percentile | 0-10 | quality.py (`component_atr_percentile`) |
| 16 | Trigger distance | 0-10 | quality.py (`component_distance`, renamed) |
| 17 | Badge status | 0/20 | quality.py (`component_badge`) |
| 18 | Target confluence quality | 0-20 | quality.py (`component_confluence`, renamed) |
| 19 | Gap penalty | 0/-10 | quality.py (`gap_penalty`) — currently always-absent in production |

**Dropped:** `quality.component_regime` (duplicate of #3), `quality.candle_points`
(dead code, duplicate detector of #8).

Weights above are ported verbatim in Tasks 3-4 and are **not final** — Task 9
re-derives them from TRAIN factor-lift evidence. This document fixes only
*which* factors exist and *why*, per Task 1's scope.
