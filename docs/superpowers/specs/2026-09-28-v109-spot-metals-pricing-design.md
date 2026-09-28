# v109 — Spot gold/silver (XAUUSD/XAGUSD) as spot-priced instruments

**Version:** ui 1.21.0 · bot 1.10.4
**Bump:** bot patch
**Edge:** volume
**Plan:** `docs/superpowers/plans/2026-09-28-v109-spot-metals-pricing.md`

## Why

The partner trades **spot** gold and silver (XAUUSD / XAGUSD at a broker) and
places resting orders at alert time. The bot prices metals off Yahoo COMEX
futures — production's watchlist holds `GC=F` and `SI=F` literally — so every
metals alert's trigger, stop and targets sit on the futures curve, not the spot
price the order is placed against. Measured 2026-09-28 ~09:45 UTC: spot gold
**4151.70** (gold-api.com) vs `GC=F` **4175.30** — a **0.57 %** basis. On a
2 %-risk plan that is over a quarter of the stop distance: a spot order placed at
the futures trigger fills early or never, and its stop is not where the plan
says.

Yahoo has no spot metals series (`XAUUSD=X` / `XAGUSD=X` return
"possibly delisted"), and stooq sits behind a JS challenge. A keyless live
spot quote does exist: `https://api.gold-api.com/price/XAU` and `/XAG`
(JSON `{"price": ..., "updatedAt": "<ISO UTC>"}`), verified live the same day.

`Edge: volume` — metals alerts the partner can actually place. Silver only began
scanning in bot 1.10.4 (futures exempted from the dollar-volume floor); without
this spec those alerts are mispriced for a spot account. No ExpR claim: signal
detection is unchanged by construction (see "Scaling").

## Decisions (from the brainstorm)

| Decision | Choice |
|---|---|
| Depth | **Spot-native instrument.** `XAUUSD` / `XAGUSD` are their own symbols end to end: bars, live quote, alerts, charts, plan fills, paper book — all spot. |
| History | Yahoo futures bars (`GC=F` / `SI=F`) **rescaled** by the live spot/futures ratio. No paid source. |
| Live quote | gold-api.com spot quote directly. |
| Watchlist | Production **replaces** `GC=F → XAUUSD`, `SI=F → XAGUSD`. Open futures plans run out in futures. |
| Backtests | Out of scope — stay on `GC=F` / `SI=F` CSVs (results would be identical; see "Scaling"). |

## Design

### 1. `swingbot/core/marketdata/spot_metals.py` (new)

- `SPOT_PAIRS = {"XAUUSD": ("XAU", "GC=F"), "XAGUSD": ("XAG", "SI=F")}` — the
  single source of truth; `is_spot_metal(sym)` reads it.
- `spot_quote(sym) -> SpotQuote(price, updated_at) | None` — urllib GET, 10 s
  timeout, 15 s in-process cache (the same TTL as `data.py`'s `_price_cache`),
  `_raw_get` split out so tests never touch the network (the
  `marketdata/fmp_client.py` pattern). Any HTTP/JSON error or non-positive
  price → `None`, logged once per failure streak, never raised.
- A quote is **stale** when `updated_at` is older than
  `SPOT_QUOTE_MAX_AGE_SECONDS` (new config field, default 900). Stale is
  treated exactly like missing on every path below.
- `spot_ratio(sym) -> float | None` — `spot_quote / live futures price`, the
  futures price taken from the existing `get_current_price_batch` path with
  `allow_stale=False`. `None` if either side is missing/stale. Sanity band:
  a ratio outside `[0.95, 1.05]` is rejected as `None` and logged (a bad quote
  or a contract-roll glitch must not rescale a whole history).

### 2. Scaling (daily and intraday bars)

`XAUUSD` bars = `GC=F` bars with `Open/High/Low/Close × spot_ratio("XAUUSD")`;
`Volume` unchanged; `df.attrs["source"] = "spot-scaled:GC=F"`.

One constant multiplier across the whole frame preserves every percentage
distance, every indicator crossing, every level ordering and every
risk/reward ratio, so a setup is detected on `XAUUSD` **iff** it is detected
on `GC=F` over the same bars — only the price scale differs. Nothing reads a
future bar; the ratio is a present-time reading applied to the presentation
of past bars, the same way a currency conversion would be. (The price-floor
gate `UNIVERSE_MIN_PRICE` is the only absolute-price check on this path, and
metals clear it by three orders of magnitude.)

Hook points — every one must go through the spot branch **before** any
alias/candidate fallback, because today `get_daily_data("XAUUSD")` silently
falls back to *unscaled* `GC=F` via `ticker_utils.ALIASES`:

- `data.get_daily_data` and `data.get_daily_data_batch` (the scan crawl uses
  the batch path, which does no aliasing at all today).
- `get_intraday` (the 5m / 1h horizons — the 2026-09-28 gold plans were 5m).
- `providers/router.py`: spot symbols are split off before `_split`, tagged
  with a new `SOURCE_SPOT_SCALED`, and never sent to Alpaca or to yfinance
  under their own name.

**Cache rule (see `known-traps.md`, two OHLCV caches):** only the raw
futures frame is ever cached, under `GC_F`. Scaled frames are computed on
read and **never** written to either cache under `XAUUSD` — a cached scaled
frame would freeze yesterday's ratio into today's levels.

### 3. Live price

`get_current_price`, `get_current_price_detail` and `get_current_price_batch`
return `spot_quote(sym).price` for spot symbols (source tag
`SOURCE_SPOT`). Stale/missing → the same "no price" result the existing code
already produces for a failed quote: the plan manager (`allow_stale=False`)
skips stepping that plan for the tick; display paths with `allow_stale=True`
may use the existing 15-min last-good fallback.

### 4. Failure handling

- Scan: if `spot_ratio` is `None`, the spot symbol is skipped for new
  signals with one `log.info("%s: skipping new-signal scan -- spot quote
  unavailable (%s)", ...)`. It **never** falls back to unscaled futures
  prices — a plausible-looking alert 0.6 % off is worse than no alert.
- Open spot plans: no price → not stepped (existing behaviour); resumes on
  the next fresh quote.
- The ratio used for a scan is logged once per symbol per scan
  (`XAUUSD: spot ratio 0.99435 (spot 4151.70 / GC=F 4175.30)`) so an alert
  can always be reconciled with the futures chart.

### 5. Classification and gates

- `asset_class.classify("XAUUSD")` → new class `"spot_metal"` (checked before
  the alias walk, so it no longer reads as `"future"`).
- `"spot_metal"` is RS-exempt (not in `_RS_ELIGIBLE`, same as futures) and
  joins `universe._VOLUME_NOT_SHARES` (dollar-volume floor exempt — the
  volume column is still futures contracts).
- Earnings lookups: spot symbols return "no earnings" without a network call.
- `commands/watchlist.py` help text and `data.py`'s not-found hint:
  "gold = `XAUUSD`, silver = `XAGUSD`" (futures `GC=F` / `SI=F` still work
  and stay futures-priced).

### 6. Rollout

1. Deploy with the watchlist unchanged (the new code is inert until a spot
   symbol is on the watchlist).
2. On production, via `!watchlist remove GC=F` / `add XAUUSD` and the same
   for silver (data change, not config — nothing to mirror into the repo).
3. Open `GC=F` / `SI=F` plans are left alone and close out in futures.
4. Verify on the first scan: the ratio log line, a non-skipped `XAUUSD`
   crawl, and — once one fires — an alert whose prices sit within the
   quote's spread of gold-api's spot.

## Testing

- `spot_metals`: quote parsing, staleness, cache TTL, error → `None`, ratio
  sanity band — all against a stubbed `_raw_get`.
- Scaling invariance: for a fixture `GC=F` frame, `build_scenarios` /
  entry-signal output on the scaled frame equals the unscaled output with
  every price × ratio (the no-lookahead / detection-parity guarantee, as a
  test).
- Every hook point (daily, batch, intraday, live, batch live) returns scaled
  / spot values for `XAUUSD` and never the unscaled alias fallback; a stubbed
  quote outage yields a skip, not futures prices.
- Cache: after a scaled read, no `XAUUSD` file exists in either OHLCV cache.
- `classify`, liquidity and RS exemptions for `"spot_metal"`.
- Full suite once, as the plan's final task.

## Out of scope

- Backtesting on spot (identical by the scaling argument).
- Any paid or keyed spot-history provider.
- Other spot metals (platinum/palladium) — `SPOT_PAIRS` makes them a one-line
  addition later if wanted.
- Contract-size-aware position sizing — sizing stays nominal units, as today.
