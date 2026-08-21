Version: ui 1.8.0 · bot 1.3.2
Bump: ui minor (1.8.0 → 1.9.0) — new workspace page. bot minor
(1.3.2 → 1.4.0, independent of [[opex-day-caution-design]]'s bump if that
ships separately) — new background data-collection job and new persisted
data file; no change to trading/alert behavior.

# Gamma flip level page

## Problem

The bot has no options-chain data of any kind (confirmed in
[[opex-day-caution-design]]'s survey: `strategy.py:6`,
`levels_lifecycle.py:9`). Traders using the bot's watchlist have no visibility
into dealer gamma positioning or the "gamma flip level" — the spot price at
which aggregate dealer gamma exposure crosses from positive (dealer hedging
dampens price moves) to negative (dealer hedging amplifies price moves,
higher realized-vol risk). This is a read-only market-context tool for the
trader's own judgment — it does not feed the bot's trading signals.

## Non-goals

- **Not a trading signal.** Gamma exposure (GEX) is not consumed by
  `entry_filters.py` or any scan-pipeline gate. It's informational, shown
  only in the admin UI. Wiring it into signal generation is a plausible
  future spec, not this one.
- **Not exact dealer positioning.** True dealer inventory isn't observable
  from public data, so the model rests on the standard published assumption:
  customers overwrite calls (leaving dealers **long gamma** against call open
  interest) and buy puts for protection (leaving dealers **short gamma**
  against put open interest). See §2 for the resulting sign convention. This
  is a documented estimate, not ground truth — the UI must say so.
- **No paid data provider.** yfinance option chains only, per the chosen
  approach — no SpotGamma/Tradytics/Unusual-Whales-style integration.
- **No live on-demand re-fetch from the UI.** The page reads the
  periodically-refreshed cache; a "Reload" button re-reads the cache file,
  it does not trigger a new options-chain pull (avoids uncontrolled fetch
  volume from UI clicks).

## Design

**Module placement corrected 2026-08-21 while writing plan v46.** This spec
put both new modules under `core/market/`. The repo's actual split is
`marketdata/` fetches and caches (`data_refresh.py`, `fmp_client.py`) while
`market/` analyses (`volatility.py`, `levels.py`), so the work lands as three
modules: `marketdata/options_chain.py` (fetch), `market/gamma_exposure.py`
(maths), `market/gamma_store.py` (snapshot assembly + persistence).

### 1. Fetch (`swingbot/core/marketdata/options_chain.py`, new)

For each of the 78 watchlist tickers: `yfinance.Ticker(sym).options` for the
expiration list, then `option_chain(date)` (calls + puts: strike,
`openInterest`, `impliedVolatility`) for the nearest `GEX_EXPIRATIONS_COUNT`
expirations (default 3 — near-dated OI dominates dealer gamma; further out
adds fetch cost for diminishing signal).

**Corrected 2026-08-21:** this spec named a `with_backoff` helper at
`data_refresh.py:143`. The real helper is `_with_retry` (`data_refresh.py:141`),
and **the job deliberately does not use it.** Retrying inside a 78-ticker
sweep multiplies the worst case by the attempt count *and* its backoff delays,
turning a throttled window into a sweep that overruns its own 45-minute
cadence. A failed ticker is instead recorded as `fetch_failed` and picked up
by the next cycle, which is soon enough for a figure that moves with open
interest. What *is* reused is the per-symbol isolation invariant
`data_refresh.py:14` states — "a rate-limited window must not kill the loop".

**Load management**: ~78 tickers × 2-3 expirations × 2 calls (calls+puts)
≈ 150-230 requests per refresh cycle. Fetches are staggered with a small
per-ticker sleep (reusing the `sleep_seconds` pattern from
`refresh_ohlcv`, `data_refresh.py:254`) rather than bursting all 78 at once.
This is materially more yfinance load than anything the bot currently does
and should be watched after ship (rate-limit/backoff log volume) —
called out explicitly since it's a new category of load, not a tuning
afterthought.

### 2. Gamma exposure math (`swingbot/core/market/gamma_exposure.py`, new)

Per contract: Black-Scholes gamma(S, K, T, σ, r) × `openInterest` × 100
(contract multiplier) × S². Documented inline as a **modeled estimate**, not
measured dealer inventory.

**Sign convention — corrected 2026-08-21 while writing plan v46.** This spec
originally said net GEX = (put side) − (call side). That is backwards, and
the error is not cosmetic: it inverts the flip level, so a page built on it
would tell the reader that hedging dampens moves exactly when it amplifies
them. The standard published convention is:

```
net_gex = Σ(call gamma × OI) − Σ(put gamma × OI)
```

because customers are net *sellers* of calls (covered-call overwriting), so
dealers are **long gamma against call open interest**; and customers are net
*buyers* of puts (protection), so dealers are **short gamma against put open
interest**. Positive net GEX therefore means dealer hedging leans against
price moves and dampens realised volatility.

**Gamma flip level**: build the net-GEX profile across a range of
hypothetical spot prices (re-price gamma at each candidate price, holding
OI/IV fixed), then find the zero-crossing via linear interpolation between
the two adjacent evaluated prices where cumulative GEX changes sign.

**Sparse-data handling**: a ticker with fewer than 5 usable strikes across
both sides is reported as `insufficient_data` rather than given a fabricated
number, per the scoping decision to prefer an honest gap over a
low-confidence guess.

**Measured 2026-08-21, and load-bearing:** yfinance returns
`impliedVolatility == 0.00001` as a *sentinel* for "no vol available", not as
a real 0.001% vol. On SPY's own front expiration — the most liquid options
market there is — **173 of 253 call strikes carried it**, leaving 80 usable.
Taken literally, that sentinel produces an astronomically large fictional
gamma that dominates the whole sum, so filtering `IV <= 0.01` is what makes
the number mean anything, not a defensive nicety.

**Also measured: `T = 0` is a live division-by-zero.** Black-Scholes gamma
divides by `sigma * sqrt(T)`, and the front expiration *on* an expiry day has
`T = 0` — exactly the situation this feature most cares about. `T` is floored
at one hour rather than skipped, so same-day gamma stays finite (and
genuinely very large, which is real rather than an artefact).

**Output** per successfully-computed ticker: `{ symbol, spot, flip_level,
net_gex_notional, distance_pct, expirations_used, as_of }`, written to
`data/gamma_exposure.json` (JSON persistence, matching every other
data file in this repo — no database).

### 3. Refresh job

A new function in the `data_refresh.py` style, run on a
`GEX_REFRESH_MINUTES` cadence (config, default in the 30–60 min range) from
the bot process (`bot.py`) — matching the existing division of labor where
the bot does data collection and the admin process only reads
already-computed state (`swingbot/admin/api_v1/risk.py`'s stated
"nothing is computed here" philosophy applies equally here). Writes the
full `data/gamma_exposure.json` atomically (write-temp-then-rename, matching
this repo's existing JSON-persistence convention) so the admin API never
reads a partially-written file.

### 4. Admin API (`swingbot/admin/api_v1/gamma.py`, new)

`GET /api/v1/gamma` → reads `data/gamma_exposure.json`, returns the
ticker list + `as_of` timestamp. No computation in the request path.
Registered in `api_v1/__init__.py:register()` alongside the other endpoint
modules (~line 181). Handles the pre-first-refresh case (file doesn't exist
yet) by returning an empty list + `as_of: null` rather than a 500.
Uses `require_auth` from `auth.py`, matching every other `api_v1` endpoint.

### 5. Admin UI page

- `swingbot/admin/spa.py`: add `"gamma"` to the `WORKSPACES` tuple
  (~line 47) so a direct browser refresh on that path serves `index.html`
  instead of 404ing.
- `frontend/src/app/workspaces/gamma/gamma.ts` (+ template): new lazy
  `loadComponent` route in `app.routes.ts`, guarded by `authGuard`
  (matching every existing workspace route), nav entry added to `shell.ts`.
  API access via the existing `api-client.ts`, new response type added to
  `models.ts`.
- **Content**: one row per successfully-computed ticker — spot, flip level,
  net GEX notional, distance-to-flip %, as-of timestamp — sorted by
  `|distance_pct|` ascending by default (tickers closest to their flip level
  are the most actionable, surfaced first). Tickers with insufficient data
  listed separately with the "insufficient options data" note. A regime
  label per row: spot above flip = "positive gamma" (dealer hedging
  dampens moves), spot below flip = "negative gamma" (dealer hedging
  amplifies moves) — genuinely useful context independent of the exact
  numeric flip level. "Reload" button re-reads the cached JSON (does not
  trigger a new fetch, per the non-goal above) — labeled accordingly so it
  doesn't imply a live re-fetch.

### 6. Error handling

- Fetch failures for an individual ticker (rate limit, network error, empty
  chain) are caught per-ticker — one bad ticker doesn't abort the refresh
  cycle for the other 77 — following the existing `data_refresh.py`
  per-symbol isolation pattern (`data_refresh.py:14`'s stated invariant: "a
  rate-limited window must not kill the loop").
  A failed ticker is omitted from that cycle's output (not held over from a
  stale cycle — stale-but-labeled-fresh data is worse than an honest gap).
- Sparse/unusable chain data → "insufficient options data", never a
  fabricated number (per the earlier scoping decision).
- Admin API pre-first-refresh / missing file → empty response, not a 500.

## Testing

- `gamma_exposure.py`: unit tests against a **hand-constructed synthetic
  option chain** (a handful of strikes with known OI/IV) where the
  zero-crossing is computable by hand — verifies the BS-gamma math and
  interpolation with no network dependency.
- `options_chain.py`: integration-style test using a **recorded/fixture
  yfinance response** (no live network calls) covering the fetch → parse
  pipeline; confirm existing test conventions for mocking yfinance in this
  repo before writing (check `tests/` for the pattern already used by
  OHLCV-fetch tests) rather than inventing a new mocking approach.
- Sparse-data path: explicit test that <5 OI-bearing strikes or missing IV
  produces the skip/insufficient-data path, not a computed number.
- Refresh job: per-ticker failure isolation — one ticker raising doesn't
  abort the cycle; output omits only the failed ticker.
- Admin API: `GET /api/v1/gamma` returns correct shape from a fixture file,
  and the empty/no-data-yet case returns `200` with an empty list rather
  than `500`.
- Frontend: component renders the sparse/empty state and the
  positive/negative-gamma regime labeling correctly (component-level test,
  matching existing Angular workspace test conventions).
- Run via `python scripts/dev/testrun.py file <new test files>` while
  iterating; full suite via the `test-runner` subagent before commit.

## Parallelisation

Two independent halves after the shared fetch/math foundation lands:

1. **Sequential first**: `options_chain.py` → `gamma_exposure.py` (math
   depends on fetched data shape) → refresh job wiring in `bot.py`.
2. **Then parallel**: admin API (`gamma.py` + `api_v1/__init__.py`
   registration + `spa.py` WORKSPACES entry) and the Angular page
   (`workspaces/gamma/`, `app.routes.ts`, `shell.ts`, `models.ts`,
   `api-client.ts`) touch disjoint file sets (Python admin vs. TypeScript
   frontend) and share no contract beyond the already-fixed JSON shape from
   step 1 — safe to build concurrently in separate sessions once that shape
   is settled, since this working tree is shared and neither side edits a
   file the other touches.
