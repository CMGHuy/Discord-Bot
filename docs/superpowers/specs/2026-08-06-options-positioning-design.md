# Options Positioning for swingbot — Design

**Date:** 2026-08-06
**Source of the idea:** `https://dsgex.ai/main` (DSGEX — "Options Order Flow & Dealer Gamma Positioning")
**Constraint:** free yfinance data only. No paid subscription, no paid dependency, no API key.

---

## 1. Problem

DSGEX is an SPX **short-dated dealer-positioning terminal**. Its edge decays
over hours to days: 0DTE gamma pins, intraday order flow, a dealer map stale
by the next session.

swingbot holds **2w–9m** swing positions on ~75 individual stocks and ETFs
(`swingbot/core/strategy_types.py:HORIZONS`). Dealer gamma at 0DTE has no
bearing on a three-month target.

A direct clone is therefore a category error. This design copies only the
subset of DSGEX that is (a) reproducible on free data and (b) still
meaningful over weeks-to-months, and states plainly what is neither.

## 2. What the free feed actually contains — verified 2026-08-06

`yf.Ticker("SPY").option_chain(exp)` returned 31 expiries, 96 calls / 102
puts on the front expiry, with columns:

```
contractSymbol, lastTradeDate, strike, lastPrice, bid, ask, change,
percentChange, volume, openInterest, impliedVolatility, inTheMoney,
contractSize, currency
```

Three facts govern this entire design:

1. **No greeks are supplied.** Gamma/delta/vanna/charm must be computed
   locally via Black-Scholes. scipy 1.17.1 and yfinance 0.2.66 are already
   installed — no new dependency.
2. **No historical chains exist.** yfinance serves only *today's* chain.
   Any history must be accrued by recording it ourselves from day one.
   This is why nothing here can ever be backtested.
3. **The data is dirty.** The same probe returned `impliedVolatility` of
   `0.000010` and `2.185551` on adjacent strikes of the most liquid ETF in
   existence, with `volume` NaN and `openInterest` 0. On a thin single name
   it is worse. Every aggregate must be computed only after a liquidity
   filter, or it produces confident nonsense.

## 3. Feature verdicts

DSGEX's navigation is `DASHBOARD / GREEKS / HEATMAP / OI CHANGE / VOLATILITY / COT / DIF / FLOW`.

| DSGEX feature | Free yfinance? | Verdict |
|---|---|---|
| **VOLATILITY** — IV level, rank, term structure | Yes | **COPY. Highest value.** Gives a market-implied expected move over the holding period. |
| **HEATMAP** — strike × expiry surface | Yes | **COPY.** Render with the existing matplotlib/mplfinance stack. |
| **OI CHANGE** — day-over-day OI delta | Only from our own snapshots | **COPY, forward-only.** History starts the day this ships. |
| **GREEKS** — Vanna / Charm / Gamma | Computable, not supplied | **BUILD, display only.** Most decay-sensitive metrics; never inform a swing decision. |
| **Dealer gamma / "full dealer map"** | Modelable only | **BUILD, advisory.** The sign convention is an assumption, not observed data (§7). |
| **DASHBOARD** — Market Context / Catalysts / Market Forces | Partial | **ADAPT.** swingbot already has a regime filter and an events feed. |
| **COT** | Not yfinance (free from CFTC, weekly, futures-only) | **CUT.** Off-thesis for single-name equity swings. |
| **DIF** — dark-pool index | **No** | **CUT. Impossible on free data.** |
| **FLOW** — options order flow / tape | **No** | **CUT. Impossible on free data.** yfinance gives an end-of-day `volume` column, not a tape. Aggregate volume must never be presented as "flow". |

## 4. Decisions

Settled with the user, 2026-08-06:

| # | Decision | Choice |
|---|---|---|
| D-1 | Purpose | All three: feed the existing engine, a dashboard to eyeball, and new options-driven alerts |
| D-2 | Universe | Full watchlist (~75 tickers) |
| D-3 | Validation | Wire in live — no backtest is possible |
| D-4 | Horizon | Keep only durable metrics; short-dated gamma is display-only |
| D-5 | Cold start | Ship day-1 metrics now; history-dependent metrics auto-enable later |
| D-6 | Thin chains | Silent skip — no options signal rather than a weak one |
| D-7 | Authority | **Additive only** — may add levels and raise score; may never veto a plan or shrink a target |
| D-8 | Alerts | Four types: OI-wall approach, IV-rank extreme, multi-day OI build, gamma-flip cross |
| D-9 | Alert volume | Strict per-type daily caps + per-ticker cooldowns; strongest reading per ticker per day |
| D-10 | Routing | Dedicated options channel, separate from trade plans |
| D-11 | Cadence | Once daily, after close, off the scan loop |
| D-12 | Build order | Everything at once |

**Consequence of D-7 worth stating explicitly:** implied expected move
becomes a *scoring and display* input, not a filter. It cannot reject a plan
whose target exceeds the implied move — it can only report that. The v8
reachability screen (V11) and target floor (V10) are left untouched.

## 5. Architecture

```
                    once daily, after close
                             │
                    ┌────────▼────────┐
                    │  chain.py       │  fetch ≤6 horizon-relevant expiries
                    │  + liquidity    │  per ticker (not all 31)
                    │    filter       │
                    └────────┬────────┘
                             │  clean chain, or None
                    ┌────────▼────────┐
                    │  snapshots.py   │  data/options/<TICKER>/YYYY-MM-DD.json.gz
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐
   │ greeks   │        │  vol.py   │        │ exposure  │
   │  .py     │        │ IV rank,  │        │  .py      │
   │ BS gamma │        │ exp. move │        │ GEX, flip,│
   └────┬─────┘        └─────┬─────┘        │ OI walls  │
        └────────────────────┼──────────────└─────┬─────┘
                             │                    │
        ┌────────────────────┼────────────────────┤
        │                    │                    │
  ┌─────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
  │levels_     │      │ quality.py  │      │  alerts.py  │
  │source.py   │      │  (additive  │      │  4 types,   │
  │(price,lbl) │      │   bonus)    │      │  capped     │
  └─────┬──────┘      └─────────────┘      └──────┬──────┘
        │                                         │
  live scan only                          options channel
```

**Module boundaries.** Each file has one job and is testable alone:
`chain.py` knows yfinance and nothing else; `greeks.py` is pure math with no
I/O; `exposure.py` and `vol.py` consume clean frames and return numbers or
`None`; `levels_source.py` is a thin adapter; `alerts.py` owns throttling.
Everything downstream of `snapshots.py` reads the store, never the network —
so every consumer is testable from fixtures.

## 6. The two integration seams

Both are **additive** (D-7).

**Levels.** `swingbot/core/levels.py:177 collect_candidate_levels()` already
returns `(price, source_label)` tuples from every method the bot knows, and
`:111 _cluster_levels()` merges them by proximity. An OI wall is simply one
more method: it arrives as `(strike, "Call OI Wall")`, clusters with a
nearby EMA or Fibonacci level, and raises confluence exactly as a real
method does. **This seam is why the plan is worth building at all.**

**Score.** A new additive component in `swingbot/core/quality.py`, alongside
the existing `component_regime()` / `component_badge()`, fed by IV rank and
the implied-move ratio. Bonus only — the component's floor is zero.

## 7. Risks and mitigations

| ID | Risk | Mitigation |
|---|---|---|
| **R1** | **Lookahead into backtests.** `build_level_map()` is reached from `backtest.py:274` and `backtest_scenarios.py:51`. Adding options inside `collect_candidate_levels()` injects *today's* chain into every historical bar, silently invalidating the entire v8 results corpus. | Options candidates arrive via a **keyword-only `extra_candidates` parameter passed only at the live-scan call site**. Backtest call sites do not pass it and cannot reach it. A dedicated guard test monkeypatches the options module to raise on any call, then runs a backtest. **A failure here is a stop-the-line event.** |
| **R2** | Garbage IV on illiquid strikes — observed live. | Liquidity filter before every aggregate; <8 surviving strikes → discard the expiry; no surviving expiry → return `None`, never a degraded number (D-6). |
| **R3** | yfinance rate limiting. The live box (`/opt/swing-bot`) shares an IP with the scan loop — a ban breaks *price* fetching, not just options. | ≤6 expiries per ticker; once daily after close, off the scan loop; on-disk cache; hard request cap; exponential backoff. |
| **R4** | The dealer sign convention (dealers long calls, short puts) is an assumption, not observed data. | Documented in code and in `docs/claude/known-traps.md`. Every user-facing GEX figure is labelled "modeled, not observed". Never gates anything. |
| **R5** | Unvalidated signal in production (D-3). | Additive-only authority means the worst case is noise, not lost trades. Plus armed rollback triggers per the V29 pattern. |
| **R6** | Alert flooding — 4 types × 75 tickers. | Per-type daily caps, per-ticker cooldowns, one strongest reading per ticker per day, dedicated channel (D-9, D-10). |
| **R7** | Snapshot store growth. | Retention set before the first write, default 400 days. `data/options/` git-ignored and covered by root `.ignore`. |

## 8. Error handling

The governing principle is inherited from the existing level engine: *any
single method failing is skipped rather than failing the whole ticker.*

- Network failure → serve the last good snapshot; if none, emit no signal.
- Empty or unparseable chain → `None`, logged at debug, ticker trades as today.
- Insufficient history for a metric → `None`, never a partial computation.
- A raise anywhere in the options package must never propagate into the scan
  loop. `levels_source.options_candidates()` returns `[]` on any failure.

## 9. Testing

- `greeks.py` — pinned against hand-computed textbook values to 6dp; put-call
  gamma parity; no NaN/inf at T=0 or IV=0.
- `chain.py` — a fixture containing the exact pathological rows observed on
  2026-08-06 (IV `0.000010`, IV `2.185551`, NaN volume, OI 0), asserting all
  are dropped.
- `exposure.py` / `vol.py` — synthetic chains with analytically known
  answers; `None` returned below every cold-start threshold.
- `levels_source.py` — an OI wall within cluster tolerance of an EMA level
  merges into one `Level` carrying both sources.
- **`test_options_no_lookahead.py`** — the R1 guard test.
- Full suite baseline: `1711 passed, 62 skipped, 0 failed` (2026-08-04). Green
  means zero failures. Run in chunks; do not add `-q`.

## 10. Explicitly out of scope

FLOW, DIF, COT, any paid data source, intraday chain refresh, options
trading of any kind (the bot remains equity paper trades only), any veto or
target-shrinking authority for options data, and any new swing horizon.
