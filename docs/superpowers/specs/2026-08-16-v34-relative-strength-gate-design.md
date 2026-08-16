# v34 — Relative strength gate

Version: ui 1.7.0 · bot 1.1.4
Bump: bot minor (1.3.x → 1.4.0) — RS stops being advisory and starts removing
alerts. `ui` none.

## The problem, stated once

Relative strength is **already built and already running**. `edge/factors.py`
provides `relative_return()`, `rs_percentile()`, `refresh_rs_cache()` and
`load_rs_cache()`; the cache is refreshed every scan
(`scanning/engine.py:1101`) and real per-item percentiles reach quality scoring
(`engine.py:1251`).

It has never stopped an alert. `rs_points()` contributes to a
`quality_score` that, per `commands/scanning.py:1163`, is "purely
informational/ranking".

Two further functions exist with **zero callers anywhere in the codebase**:

- `sector_rs_percentile(sector, sector_etf_dfs, spy_df, ...)`
- `rs_score(ticker_pctile, sector_pctile)`

Sector-relative strength is written and dormant. `marketdata/universe.py`
already provides `sector_map(name)`, so the mapping it needs exists too.

## Goal

Promote RS from an advisory score component to a **symmetric hard gate**, scale
its lookback per horizon, exempt non-equities, and activate the dormant
sector-RS path.

## Design

### Symmetric gate

- **Bullish** scenarios require RS **≥** the leader threshold.
- **Bearish** scenarios require RS **≤** the laggard threshold.

Shorting a market leader is exactly as bad as buying a laggard, so the gate cuts
both ways. Thresholds are symmetric around the median unless TRAIN says
otherwise.

### Per-horizon lookback

RS lookback scales with the horizon, as every other setting in `HORIZONS`
already does: a `2w` setup reads RS over roughly a month, a `9m` setup over
roughly six to twelve. A laggard-over-six-months is close to irrelevant to a
two-week swing.

Lookbacks are added as a new key in each `HORIZONS` entry, keeping the
established pattern of one settings dict per horizon rather than a parallel
table.

### Non-equity exemption

The watchlist holds FX, commodities and indices (`XAUUSD`→`GC=F`, `EURUSD=X`,
`^GSPC`). RS-vs-SPY is not meaningful for those, so they are **exempt** — they
pass the gate and score neutral, and the exemption is logged distinctly from a
pass.

Classification uses the resolved Yahoo symbol shape (`=X` FX, `=F` futures,
`^` index) plus a small static override table for cases the suffix heuristic
gets wrong. `universe.is_etf()` already exists and is reused rather than
reimplemented.

### Activating sector RS

`sector_rs_percentile()` and `rs_score()` are wired for the first time, using
`universe.sector_map()`. `rs_score(ticker_pctile, sector_pctile)` becomes the
gate's input rather than the bare ticker percentile — a stock that is strong
only because its whole sector is strong is a weaker signal than one leading a
flat sector.

Sector ETF frames must be fetched for the sectors present in the watchlist.
This is the **one place this spec adds data fetching**, and it is bounded: a
handful of sector ETFs per scan, cached alongside the existing RS cache. If a
sector's ETF frame is unavailable, that ticker falls back to ticker-only RS
rather than being blocked.

### Config

- `RS_GATE` — checkbox, **default off**; flipped on only by a VALIDATION pass.
- `RS_LEADER_PERCENTILE` / `RS_LAGGARD_PERCENTILE` — numeric, defaults set by
  the TRAIN sweep.

## Validation

New pre-registration. Acceptance: win-rate improvement with alert volume down no
more than **~30%**.

The TRAIN sweep must report, separately: gate effect on bullish vs bearish
scenarios (the symmetric assumption is a hypothesis, not a given), and the
marginal contribution of sector RS over ticker-only RS — if sector RS adds
nothing measurable, it stays dormant and this spec records that as a result
rather than shipping unused wiring.

## What this deliberately does NOT change

- **The RS computation itself.** `relative_return`/`rs_percentile` are
  untouched; this spec changes what their output is *allowed to do*.
- **The benchmark stays SPY.** Per-asset-class benchmarks (DXY for FX, a
  commodity index) are explicitly out of scope.
- **Non-equities are never blocked by this gate.**

## Risks

- **Momentum gates fail in sharp reversals.** An RS gate is procyclical: it is
  most confident right before a leadership rotation. Mitigation: the TRAIN
  window must span at least one regime change, and the pre-registration says so.
- **Sector mapping drift.** `sector_map` is static; a reclassified ticker
  silently gets the wrong benchmark. Mitigation: fall back to ticker-only RS on
  an unknown sector, and log it.
- **Shipping dormant wiring.** If sector RS does not earn its place in TRAIN,
  activating it anyway would repeat the exact pattern this spec exists to fix.

## Parallelisation

- **Group A (parallel):** non-equity classification (`ticker_utils` /
  `universe.py`) and per-horizon lookback keys (`strategy_types.py`) — disjoint
  files, neither consumes the other.
- **Sequential after Group A:** the gate itself (`scanning/engine.py`), which
  consumes both.
- **Sequential:** sector-ETF fetching + cache before `rs_score` wiring (the
  latter consumes the former's frames).
- **Sequential at the end:** TRAIN sweep → VALIDATION → docs and embed
  surfacing.

## Depends on

**v32 must land first** — RS's scoring contribution lives in the merged score,
and the gate's threshold calibration is measured against v32's level bands.
