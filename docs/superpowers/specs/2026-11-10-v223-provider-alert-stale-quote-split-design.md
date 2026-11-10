# v223 — Provider alert counts only real Alpaca failures

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch (the provider alert stops firing on intended fallbacks; new telemetry field), ui patch (Provider health panel shows the stale-quote rate)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Why

Since 2026-11-09 the ops channel gets "market-data provider degraded" every
weekday around 09:00 and 21:00 UTC. Alpaca has not degraded: in the ten days
up to 2026-11-10 the logs show zero Alpaca 429s and one real batch timeout
(2026-11-05 15:05).

Commit `2e6df134` ("an old IEX print is a miss whenever the US tape is live",
deployed with the 2026-11-09 ~14:25-14:53 UTC restarts) changed
`AlpacaProvider._fresh_price` from `_in_regular_session` to
`session.is_tape_open` (Mon-Fri 04:00-20:00 ET). Before and after regular hours,
IEX trades rarely, so most symbols' last print is older than
`ALPACA_MAX_TRADE_AGE_SECONDS` (300). They become misses and are re-asked from
yfinance on purpose, which is what `2e6df134` was for. But the router tags every
miss `yfinance-fallback`, and `telemetry.fallback_rate` treats every
`yfinance-fallback` as an Alpaca failure. The alert (`ops_watch.provider_verdict`,
threshold `PROVIDER_FALLBACK_ALERT_PCT=20`) therefore fires on the intended
behaviour.

Production telemetry (`/opt/swing-bot/data/scan_telemetry.jsonl`, all times UTC):

| Breach row | ET | `provider_fallback_rate` | What was happening |
|---|---|---|---|
| 2026-11-09 14:31 | 09:31 | 0.929 | market open; most last prints still from pre-market |
| 2026-11-09 21:10-22:03 | 16:10-17:03 | 0.89-0.98 (14 scans) | after-hours |
| 2026-11-10 09:04, 09:09 | 04:04, 04:09 | 1.0 | pre-market begins |

Before the deploy the rate stayed at 0.00-0.07 on every day, including the
2026-11-09 pre-market scans (09:00-14:25 UTC, rate 0.0). In those same windows
`empty_rate` never exceeded 5%: yfinance answered every re-ask.

## What changes

1. **The provider tells the router why it returned no price for a symbol.**
   The snapshot can answer with a positive trade whose timestamp is too old
   while the tape is live (a *stale print*), or not answer usefully at all
   (no snapshot for the symbol, no trade, a non-positive price, or the call
   failed or timed out: a *miss*). Only the first one counts as stale. This
   reuses the same `get_stock_snapshot` call, with no extra Alpaca request.
   `latest_prices` and `latest_quotes` both carry this. A `latest_quotes`
   detail with `price is None` but a bid/ask is already a stale print.
2. **The router tags stale prints with a new source,
   `SOURCE_STALE = "yfinance-stale"`** (`providers/base.py`, next to
   `SOURCE_FALLBACK`). They are re-asked from yfinance exactly as today; only
   the tag changes. Real misses keep `yfinance-fallback`. `router.last_source`,
   `_stats` (new key `stale`) and the debug fallback log line say which is which.
3. **`fetch._PRICE_SOURCE_KEYS` gains `"yfinance-stale"`**, so the scan's
   `price_sources` counts (already persisted in every telemetry row through
   `fetch.fetch_stats()`) keep it in its own bucket. Today an unknown key would
   fall into `"none"`.
4. **`telemetry.fallback_rate` is unchanged in formula.** It still counts
   `yfinance-fallback / (alpaca + yfinance-fallback)`. Because stale prints
   leave that bucket, the rate and the alert now measure Alpaca failures only.
   Stale prints are excluded from both the numerator and the denominator: a
   stale answer is neither a hit nor a failure.
5. **New telemetry field `stale_quote_rate`**, added by
   `telemetry.provider_health`:
   `yfinance-stale / (alpaca + yfinance-fallback + yfinance-stale)` over the
   scan's `price_sources`, or None when Alpaca was asked for nothing. It is for
   display only. **No alert, no threshold** (partner decision, 2026-11-10): the
   old-quote fallback is intended, and the existing `EMPTY_SYMBOLS_ALERT_PCT`
   alert still catches yfinance failing too.
6. **Display.** `admin/api_v1/ops_health.py` `_PROVIDER_KEYS` adds
   `stale_quote_rate`. The Angular Provider health panel
   (`frontend/src/app/workspaces/system/provider-health-panel.ts`, model in
   `api/models.ts`) shows it as one more row, "Stale IEX prints (re-asked from
   yfinance)", with a "—" for None. It follows the panel's existing layout on
   phone, tablet and desktop. The Discord `provider_degraded_embed` and
   `provider_recovered_embed` add one line, `• Stale IEX prints: <rate>`, so the
   alert text explains itself.

## What does not change

- Which price the scan uses: stale prints are still replaced by yfinance's
  extended-hours price, as `2e6df134` intended.
- Regular-session behaviour: an IEX print older than 300 s at 11:00 ET was a
  miss before `2e6df134` and is still re-asked. It is now tagged
  `yfinance-stale`, not `yfinance-fallback`. Before `2e6df134` a stale
  regular-hours print could already raise the rate, but the 0.00-0.07 history
  shows this is rare for the 87-ticker watchlist.
- The daily-bars fallback (`daily_delta`, `_merge`): untouched. It has no
  freshness rule.
- The breaker, budgets and timeouts.
- Old telemetry rows: no backfill. Rows from before this change lack
  `stale_quote_rate` and show "—". Their `provider_fallback_rate` stays as
  recorded (`schema-evolution.md`: no read-time upcasting).

## Error handling

A provider that cannot tell why (an older provider object, or an exception
inside the classification) falls back to today's behaviour: every missing
symbol is a miss, tagged `yfinance-fallback`. This can only over-report
failures, never hide one. `provider_health` stays inside its existing
`_provider_health_fields` guard.

## Tests

- `tests/marketdata/test_alpaca_provider.py`: a positive trade older than 300 s
  at 04:30 ET, 09:31 ET and 16:30 ET is reported stale. A missing snapshot, a
  `None` trade and a zero price are misses. Overnight (02:00 ET) and on a
  weekend, the old print is a hit (unchanged).
- Router tests: stale symbols are tagged `yfinance-stale` and misses
  `yfinance-fallback`, for both `latest_prices` and `latest_quotes`. A failed
  snapshot call makes every wanted symbol a miss. `_stats["stale"]` counts.
- `fetch._record_price_sources`: `yfinance-stale` gets its own bucket, not
  `"none"`.
- `telemetry.provider_health`: a row with 80 `yfinance-stale`, 7 `alpaca` and
  0 `yfinance-fallback` gives `provider_fallback_rate == 0.0` and
  `stale_quote_rate ≈ 0.92`. An all-zero count gives both None.
- `ops_watch.provider_verdict` on that row: no alert. A row with real
  `yfinance-fallback` above 20% still alerts (regression).
- Embeds: the degraded and recovered texts carry the stale line, with "—" for
  None.
- Frontend: `provider-health-panel.spec.ts` renders the new row with a value
  and with None. `system.store.spec.ts` carries the field through.

## Acceptance

After deploy, on the first weekday:

- No "market-data provider degraded" post between 09:00 and 14:30 UTC or
  between 21:00 and 22:00 UTC.
- Those telemetry rows show `provider_fallback_rate` near 0 and
  `stale_quote_rate` high.

This is checked read-only on production. `stale_quote_rate` above 0 during
pre-market proves the new path ran.

## What follows

v224 (to be brainstormed): the stale-scan watchdog alerts on the first session
tick. The cause is that the scan's analysis phase roughly doubled since
2026-11-03 (median tick 182 s to 314 s, bot container at 100% CPU,
`SCAN_WORKERS=1`, 5-min interval), plus the session's first tick refetching
anchors (crawl ~153 s against ~45 s). Profile it before designing.
