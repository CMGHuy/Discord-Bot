# v109 — Spot gold/silver (XAUUSD/XAGUSD) as spot-priced instruments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-09-28-v109-spot-metals-pricing-design.md`](../specs/2026-09-28-v109-spot-metals-pricing-design.md)
**Bump:** bot patch
**Edge:** volume

**Goal:** Make `XAUUSD` / `XAGUSD` spot-priced symbols end to end. Their bars are the `GC=F` / `SI=F` bars times one live spot/futures ratio. Their live price is gold-api.com's keyless spot quote. None of these paths may ever fall back to unscaled futures prices.

**Architecture:** A new module `swingbot/core/marketdata/spot_metals.py` owns the pair table, the quote client (15 s cache, staleness gate), the ratio (sanity band) and the pure `scale_frame`. The provider router splits spot symbols off before its Alpaca/yfinance split. It fetches their underlying under its own name, scales it, and serves live prices from the spot quote. `data.py`'s single-symbol paths (`get_daily_data`, `get_current_price_detail`) branch to spot before the `candidate_symbols()` alias loop, which would otherwise hand back unscaled `GC=F`. Cache writers map a spot symbol to its underlying, and `save_to_disk` refuses a spot name. The scan crawl fetches spot symbols in their own bounded workers and logs, in the scan's own process, either the ratio or the skip.

**Tech Stack:** Python 3.11, stdlib `urllib`/`json`, pandas, pytest; existing `providers/router.py`, `data.py`, `data_store.py`, `data_refresh.py`, `backtest_cache.py`, `scanning/fetch.py`.

## Global Constraints

Copied from the spec. Every task's requirements include this section.

- `SPOT_PAIRS = {"XAUUSD": ("XAU", "GC=F"), "XAGUSD": ("XAG", "SI=F")}` is the single source of truth. `is_spot_metal(sym)` reads it.
- Quote endpoint: `https://api.gold-api.com/price/XAU` and `/XAG`, returning JSON `{"price": ..., "updatedAt": "<ISO UTC>"}`. Use a urllib GET with a **10 s** timeout and a **15 s** in-process cache. `_raw_get` is split out, so tests never touch the network.
- Any HTTP/JSON error or non-positive price → `None`, **logged once per failure streak, never raised**.
- A quote is **stale** when `updatedAt` is older than `SPOT_QUOTE_MAX_AGE_SECONDS` (new config field, default **900**). Stale is treated exactly like missing on every path.
- `spot_ratio = spot quote / live futures price`. The futures price comes from `get_current_price_batch(..., allow_stale=False)`. A ratio outside **`[0.95, 1.05]`** is rejected as `None` and logged.
- Scaling: `Open/High/Low/Close × ratio`, `Volume` unchanged, `df.attrs["source"] = "spot-scaled:GC=F"` (resp. `SI=F`).
- **Never fall back to unscaled futures prices** for a spot symbol, on any path. Every hook goes through the spot branch *before* any alias/candidate fallback.
- **Cache rule:** only the raw futures frame is ever cached, under `GC_F` / `SI_F`. A scaled frame is never written to either OHLCV cache (`market_data/`, `data/backtest_cache/`) under `XAUUSD` / `XAGUSD`.
- Live price source tag: `SOURCE_SPOT`. Scaled bars source tag: `SOURCE_SPOT_SCALED`.
- The scan logs the skip exactly as `log.info("%s: skipping new-signal scan -- spot quote unavailable (%s)", ...)`. The ratio log line has the shape `XAUUSD: spot ratio 0.99435 (spot 4151.70 / GC=F 4175.30)`, once per symbol per scan.
- `asset_class.classify("XAUUSD") == "spot_metal"`, checked before the alias walk. `"spot_metal"` is RS-exempt and sits in `universe._VOLUME_NOT_SHARES`.
- Earnings lookups return "no earnings" for spot symbols without a network call.
- Watchlist help text and `data.py`'s not-found hint say "gold = `XAUUSD`, silver = `XAGUSD`". `GC=F` / `SI=F` still work and stay futures-priced.
- Out of scope: backtesting on spot, paid/keyed providers, other metals, contract-size sizing, `export_data.py`'s CSV export, scan telemetry buckets (a spot live price counts as `"none"` in `price_sources` and a scaled frame as `"cache"` in `data_sources`; both are accepted as they are).
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`), and a legacy function already at 15 or more never gets worse. `_scan_one` (complexity 39) and `refresh_all` (17) gain **no** branches.
- NO-LOOKAHEAD: the ratio is a present-time reading applied to past bars. Detection parity is proved by a test (V109-2), never assumed.
- Never `cd` in Bash.

**Spec correction noted here (not a design change):** the spec's §2 says "the 5m / 1h horizons — the 2026-09-28 gold plans were 5m". In this repo `5m` is the **5-month** swing horizon (`strategy_types.HORIZONS`), not 5-minute bars. The only intraday consumer is `edge/factors.intraday_confirms` (1h, through `data_store.get_intraday`). The `get_intraday` hook stays in scope for that consumer, and the daily hooks cover every horizon.

## Parallelisation

- **Sequential:** V109-1 → V109-2. Both edit `swingbot/core/marketdata/spot_metals.py` and `tests/marketdata/test_spot_metals.py`, and V109-2 consumes V109-1's `quote_with_reason`.
- **Group 1 (parallel, after V109-2):** V109-3, V109-4, V109-6.
  - V109-3 touches `asset_class.py`, `universe.py`, `market/events.py` and their tests.
  - V109-4 touches `providers/router.py` and `tests/marketdata/test_provider_router_spot.py`.
  - V109-6 touches `data_store.py`, `data_refresh.py`, `backtest_cache.py`, `docs/claude/known-traps.md` and `tests/marketdata/test_spot_cache_rule.py`.
  - The files are disjoint. Each task consumes only V109-1/V109-2 symbols, and none consumes another's.
- **Group 2 (parallel, after V109-4):** V109-5 and V109-7.
  - V109-5 touches `data.py`, `ticker_utils.py`, `commands/watchlist.py` and `tests/marketdata/test_data_spot.py`.
  - V109-7 touches `scanning/fetch.py` and `tests/scanning/test_crawl_spot.py`.
  - Both consume V109-4's `router.spot_miss_reason` and router spot branches, which is the sequential edge to V109-4. Neither consumes the other.
  - V109-7 may also run beside V109-6 (disjoint files).
- **Sequential, from here on:** V109-8 (the one full-suite run) comes after every code task. V109-9 (merge + release) comes after V109-8. V109-10 (production rollout and close-out) comes after the deploy V109-9's push triggers.
- All parallel tasks share one worktree. Each stages only its own files and commits with an explicit pathspec. If a commit fails on `index.lock`, wait and retry. Never `git add -A`.

## Conventions for every task

- V109-1..V109-8 run in the worktree `.claude/worktrees/2026-09-28-v109-spot-metals-pricing` on branch `2026-09-28-v109-spot-metals-pricing`, created from `main` before V109-1 (`worktree-lifecycle` skill). V109-9 merges it. Run every command from the worktree root.
- Per-task check: `python scripts/dev/testrun.py file <the task's test file>`, never `full` (V109-8 is the one full run).
- Load the `no-lookahead` skill before V109-2 and V109-7, and `alert-surface` before V109-7 (scan pipeline).
- Complexity check per task: `python -m radon cc -s -n C <the task's modified .py files>`. Every function the task wrote or changed must be absent from its output (below C = < 11), or at C with a value < 15. `refresh_all` stays at 17.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Parts

| File | Tasks |
|---|---|
| `2026-09-28-v109-spot-metals-pricing_0-index.md` | header, goal, constraints, parallelisation, conventions (this file) |
| `2026-09-28-v109-spot-metals-pricing_1-spot-module.md` | Phase A (V109-1, V109-2), Phase B part 1 (V109-3, V109-4) |
| `2026-09-28-v109-spot-metals-pricing_2-wiring-release.md` | Phase B part 2 (V109-5, V109-6, V109-7), Phase C (V109-8, V109-9, V109-10) |

Pull one task with `grep -n "^### Task V109-4" -A 200 docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing_*.md` or `/task-brief V109-4`. Never read a part whole.
