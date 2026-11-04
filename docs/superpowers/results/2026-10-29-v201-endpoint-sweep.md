# v201 endpoint sweep (V201-8)

**Purpose:** list every admin request-path reference to a market-data or FX
fetch and say whether, with the refresher on, a page load can still reach it.

- **Command:** `git -C <wt> grep -nE "page_quotes|get_quote_batch|get_current_price|prefetch_prices|get_daily_data_batch|quote_currency_code|fx_rate|refresh_snapshot|collect_portfolio_state|warm_quotes_background|warm_batch_price|page_daily|tape_cache\.|yf_safe|refresh_tape" -- swingbot/admin`
- **Date:** 2026-11-03
- **Worktree HEAD:** `2d2f5cd4` plus the V201-8 working tree (the sweep ran over
  the changes this task commits, so line numbers are those of the V201-8 commit).
- **Result:** 0 `UNCLASSIFIED`. `quote_currency_code` and `fx_rate` have no hit
  under `swingbot/admin` (V201-4 moved conversion into core with `fetch=not refresher_on()`).

| Hit (`file:line`) | Endpoint(s) reaching it | Verdict |
|---|---|---|
| `api_v1/analytics.py:38` | `/api/v1/analytics/*` (`_snapshot`) | v204 (snapshot pages) |
| `api_v1/analytics.py:41` | `/api/v1/analytics/*` (`_snapshot(fresh=True)`) | v204 (snapshot pages) |
| `api_v1/analytics.py:43` | `/api/v1/analytics/*` (`_snapshot`) | v204 (snapshot pages) |
| `api_v1/dashboard.py:24` | none (module docstring) | out of scope: comment, no call |
| `api_v1/dashboard.py:59` | `/api/v1/dashboard` (`_equity_snapshot`, after its `refresher_on()` return) | refresher-off fallback only |
| `api_v1/dashboard.py:60` | `/api/v1/dashboard` (`_equity_snapshot`, after its `refresher_on()` return) | refresher-off fallback only |
| `api_v1/dashboard.py:95` | none (docstring of `_risk_figures`) | out of scope: comment, no call |
| `api_v1/market.py:543` | none (docstring of `_tape_change_pct`) | out of scope: comment, no call |
| `api_v1/market.py:672` | `/api/v1/market/tape` (`_tape_quotes_direct`, reached only past the `refresher_on()` guard in `_tape_quotes`) | refresher-off fallback only |
| `api_v1/market.py:673` | `/api/v1/market/tape` (`_tape_quotes_direct`) | refresher-off fallback only |
| `api_v1/market.py:781` | `/api/v1/market/tape` (`_tape_self_fetch` from `_shared_tape_quotes`, off only) | refresher-off fallback only |
| `api_v1/risk.py:13` | none (module docstring) | out of scope: comment, no call |
| `api_v1/risk.py:201` | none (comment) | out of scope: comment, no call |
| `api_v1/risk.py:384` | `/api/v1/risk` (`_risk_bars`) | v204 (snapshot pages) |
| `api_v1/risk.py:385` | `/api/v1/risk` (`_risk_bars`) | v204 (snapshot pages) |
| `api_v1/risk.py:386` | `/api/v1/risk` (`_risk_bars`) | v204 (snapshot pages) |
| `api_v1/risk.py:499` | none (docstring) | out of scope: comment, no call |
| `api_v1/risk.py:502` | `/api/v1/risk` (portfolio state) | v204 (snapshot pages) |
| `api_v1/risk.py:506` | `/api/v1/risk` (portfolio state) | v204 (snapshot pages) |
| `api_v1/trade_commands.py:103` | `POST /api/v1/trades/<id>/close` (`_build_override_stamp` → `_live_quote`) | out of scope: a user's close command, not a page load (index: cancels and commands) |
| `api_v1/trades.py:1334` | `/api/v1/trades`, `/api/v1/trades/<id>` (`_attach_current_prices`) | door (V201-9) |
| `api_v1/trades.py:1348` | none (docstring) | door (V201-9) |
| `api_v1/trades.py:1373` | `/api/v1/trades`, `/api/v1/trades/<id>` | door (V201-9) |
| `api_v1/trades.py:1374` | `/api/v1/trades`, `/api/v1/trades/<id>` | door (V201-9) |
| `api_v1/trades.py:1376` | `/api/v1/trades`, `/api/v1/trades/<id>` | door (V201-9) |
| `app.py:255` | chart endpoints (`_ohlcv_frame` → `_live_daily`) | out of scope: charts need bars, not quotes |
| `app.py:415` | none (`main()` sets the yfinance lock timeout at process start) | out of scope: process startup, not a request |
| `queries.py:35` | `/api/v1/analytics` registry (`_registry_rows`) | v204 (snapshot pages) |
| `queries.py:209` | `/api/v1/analytics` registry (`_registry_rows`) | v204 (snapshot pages) |
| `dashboard.py:33` | `/api/v1/dashboard` (import of the off-path fetchers) | refresher-off fallback only |
| `dashboard.py:355` | `/api/v1/dashboard` (`_open_trade_prices`, called only when `refresher_on()` is false) | refresher-off fallback only |
| `dashboard.py:357` | `/api/v1/dashboard` (`_open_trade_prices`) | refresher-off fallback only |
| `dashboard.py:358` | `/api/v1/dashboard` (`_open_trade_prices`) | refresher-off fallback only |
| `freshness.py:72` | definition of `page_quotes`; reached only through the callers above | out of scope: helper definition, classified at each caller |
| `freshness.py:76` | inside `page_quotes` | out of scope: helper definition, classified at each caller |
| `freshness.py:79` | inside `page_quotes` (log label) | out of scope: helper definition, classified at each caller |
| `freshness.py:97` | definition of `warm_quotes_background` | out of scope: helper definition, classified at each caller |
| `freshness.py:101` | inside `warm_quotes_background` | out of scope: helper definition, classified at each caller |
| `freshness.py:179` | definition of `page_daily` | out of scope: helper definition, classified at each caller |
| `freshness.py:184` | inside `page_daily` | out of scope: helper definition, classified at each caller |
| `tape_cache.py:108` | `tape_cache.prices`, reached only from `_tape_quotes_direct` | out of scope: helper definition, classified at each caller |
| `tape_cache.py:113` | `tape_cache.daily_frames`, reached only from `_tape_quotes_direct` | out of scope: helper definition, classified at each caller |
| `watchlist_rows.py:33` | `/api/v1/watchlist/tickers` (import of `get_daily_data_batch`) | refresher-off fallback only |
| `watchlist_rows.py:36` | `/api/v1/watchlist/tickers` (import of `warm_batch_price_cache_background`) | refresher-off fallback only |
| `watchlist_rows.py:137` | none (docstring of `_cached_daily`) | out of scope: comment, no call |
| `watchlist_rows.py:171` | `/api/v1/watchlist/tickers` (`_cold_frames`, after its `refresher_on()` return) | refresher-off fallback only |
| `watchlist_rows.py:172` | `/api/v1/watchlist/tickers` (`_cold_frames`) | refresher-off fallback only |
| `watchlist_rows.py:230` | `/api/v1/watchlist/tickers` (`_layer_overlay`, reached only past the `refresher_on()` guard in `_overlay`) | refresher-off fallback only |
| `watchlist_rows.py:284` | `/api/v1/watchlist/tickers` (`_live_overlay`, off only) | refresher-off fallback only |

The door paths themselves (`dashboard._open_trade_market`,
`api_v1/dashboard._open_meta`/`_equity_snapshot`, `api_v1/market._door_tape_quotes`,
`watchlist_rows._door_overlay`/`_cold_frames`) are pinned by
`tests/admin_market/test_page_loads_never_fetch.py`, which records every
forbidden fetcher a page load reaches with the refresher on and asserts none.
