# v223 — Provider alert counts only real Alpaca failures

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch (the provider alert stops firing on intended fallbacks; new telemetry field), ui patch (Provider health panel shows the old-print rate; watchlist badge tooltip)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Why

Since 2026-11-09 the ops channel gets "market-data provider degraded" every
weekday around 09:00 and 21:00 UTC. Alpaca has not degraded: in the ten days
up to 2026-11-10 the logs show zero Alpaca 429s and one real batch timeout
(2026-11-05 15:05).

Commit `2e6df134` ("an old IEX print is a miss whenever the US tape is live")
went live with the 2026-11-09 ~14:25-14:53 UTC restarts. It changed
`AlpacaProvider._fresh_price` from `_in_regular_session` to
`session.is_tape_open` (Mon-Fri 04:00-20:00 ET). Before and after regular
hours, IEX trades rarely, so most symbols' last print is older than
`ALPACA_MAX_TRADE_AGE_SECONDS` (300). They become misses and are re-asked from
yfinance on purpose; that is what `2e6df134` was for. But the router tags
every miss `yfinance-fallback`, and `telemetry.fallback_rate` treats every
`yfinance-fallback` as an Alpaca failure. The alert
(`ops_watch.provider_verdict`, threshold `PROVIDER_FALLBACK_ALERT_PCT=20`)
therefore fires on the intended behaviour.

Production telemetry (`/opt/swing-bot/data/scan_telemetry.jsonl`, all times UTC):

| Breach row (scan end) | ET | `provider_fallback_rate` | What was happening |
|---|---|---|---|
| 2026-11-09 14:31 | 09:31 | 0.929 | live prices fetched at ~14:27 (09:27 ET), still pre-market, minutes after the deploy |
| 2026-11-09 21:10-22:03 | 16:10-17:03 | 0.89-0.98 (14 scans) | after-hours |
| 2026-11-10 09:04, 09:09 | 04:04, 04:09 | 1.0 | pre-market begins |

Before the deploy, the rate stayed at 0.00-0.07 on every day. That includes
the market opens of 2026-11-02 to 11-06 and the 2026-11-09 pre-market scans
from 09:00 to 14:25 UTC (rate 0.0). In the breach windows, `empty_rate` never
exceeded 5%, because yfinance answered every re-ask.

## Vocabulary

This area already has three meanings of "stale" (staff-engineer finding 4):

- `stale_symbols`: daily bars older than the previous session.
- `data.py:_split_fresh_prices`'s `served_stale`: a cached price served
  because the live fetch failed.
- `2e6df134`'s old trade.

So this spec never says "stale" for the new concept. The new concept is an
**old print**: Alpaca's snapshot has a positive last trade that is older than
`ALPACA_MAX_TRADE_AGE_SECONDS`, taken while the tape is open **outside the
regular session**. The new tag is `yfinance-old-print`, and the new field is
`old_print_rate`.

## What changes

1. **Classification: an old print exists only outside the regular session.**
   `AlpacaProvider` gets one classifier, `_price_verdict(snap, now, max_age_s)
   -> (price | None, old_print: bool)`. `_fresh_price` and `_detail` both use
   it, so the classification comes from the trade's own branches and never
   from the shape of the returned detail (quant-engineer finding 1). It
   returns `old_print=True` only when all four of these hold:
   - the trade price is positive;
   - `session.is_tape_open(now)`;
   - **not** `session.is_nyse_regular_session(now)` (holiday- and early-close
     aware);
   - the trade's age is more than `max_age_s`.

   Everything else that yields no price is a **miss**: no snapshot, no trade, a
   non-positive price, a failed call, and **an old trade during the regular
   session**. A frozen IEX feed in regular hours therefore still counts as an
   Alpaca failure and still alerts, exactly as before `2e6df134`
   (quant-engineer finding 4). The pre-market and after-hours re-ask is what
   becomes an old print. Overnight and on weekends, an old trade remains a hit
   (unchanged).
2. **Contract: a pure return value, no side channel** (staff-engineer finding
   1). Two new provider methods return the reason alongside the result, from
   the same single `get_stock_snapshot` call:
   - `latest_price_answers(tickers, max_age_s) -> (dict[str, float], frozenset[str])`
   - `latest_quote_answers(tickers, max_age_s) -> (dict[str, QuoteDetail], frozenset[str])`

   The second element is the set of tickers answered with an old print. The
   existing `latest_prices` and `latest_quotes` keep their exact return shape
   as thin wrappers returning element 0. Their direct callers
   (`scripts/ops/data_sources_check.py:137`,
   `scripts/reports/provider_parity_report.py:103`) are unchanged. Nothing is
   stored on the provider object, which is shared across `_quote_pool` threads,
   the scan, admin refresh and requote.
3. **Router.** `latest_prices` and `latest_quotes` call the `*_answers` method
   when the active provider has it (`getattr`). Otherwise, or when the call
   fails (`_attempt` → None), the old-print set is empty, so every missing
   symbol is a miss tagged `yfinance-fallback`. This is the defined fallback
   (quant-engineer finding 6): it can only over-report failures, never hide
   one. Old-print symbols are re-asked from yfinance exactly like misses and
   tagged `SOURCE_OLD_PRINT = "yfinance-old-print"` (`providers/base.py`, next
   to `SOURCE_FALLBACK`). `_last_source`, `_stats` (new key `old_print`) and
   the debug fallback log line keep the two apart. `latest_quotes` keeps the
   Alpaca bid/ask on an old-print detail, as it does today for misses.
4. **One list of live-price tags** (staff-engineer finding 5).
   `providers/base.py` exports `PRICE_SOURCES = (SOURCE_ALPACA, SOURCE_YF,
   SOURCE_FALLBACK, SOURCE_OLD_PRINT)`. `fetch._PRICE_SOURCE_KEYS` becomes
   `PRICE_SOURCES + ("none",)`, so a new tag can no longer fall silently into
   `"none"`. `scan_run._SOURCE_BUCKETS` (daily frames) is built from the same
   constants without `SOURCE_OLD_PRINT`, because the daily path (`_merge`,
   `daily_delta`) has no freshness rule and never emits it. A test pins that.
5. **`telemetry.fallback_rate` keeps its formula**,
   `yfinance-fallback / (alpaca + yfinance-fallback)` pooled over
   `data_sources` and `price_sources`. Old prints are in neither the numerator
   nor the denominator: an old print is neither a hit nor a failure. With old
   prints out of the `yfinance-fallback` bucket, the rate and the alert measure
   Alpaca failures only.
6. **New telemetry field `old_print_rate`**, added by
   `telemetry.provider_health`. It is computed over `price_sources` **only**,
   because daily frames can never be old prints:
   `yfinance-old-print / (alpaca + yfinance-fallback + yfinance-old-print)`,
   or None when that sum is 0. It is labelled "of live-price asks" wherever it
   is shown, so nobody tries to reconcile it with `provider_fallback_rate`'s
   wider pool (quant-engineer finding 3). It is for display only. **No alert,
   no threshold** (partner decision, 2026-11-10). With item 1, the gap that
   would leave is closed: a regular-hours freeze still alerts as a miss.
7. **A ticker that is an old print and that yfinance also fails for** is not
   in the returned prices, so `fetch._price_batch_with_sources` records it as
   `"none"` (`fetch.py:84`, `_record_price_sources`). Real misses are already
   treated this way. It shows in `empty_rate`, whose 5% alert covers it, and
   not in `old_print_rate`. This is intended and pinned by a test
   (quant-engineer finding 2).
8. **Pooled Risk/Providers rate** (staff-engineer finding 3).
   `admin/api_v1/risk.py` pools `price_sources` through the same
   `telemetry.fallback_rate`, so its meaning changes in the same way. For one
   window length after the deploy, it mixes pre-v223 rows (old prints counted
   as fallback) with post-v223 rows (excluded). This shows as a falling rate
   and is expected. The docstrings that state the formula (`risk.py:52-56`,
   `frontend/src/app/api/models.ts:1573` and `:1837`) gain one clause saying
   old prints are excluded from v223 on.
9. **Display.**
   - `admin/api_v1/ops_health.py` `_PROVIDER_KEYS` adds `old_print_rate`.
   - The Angular Provider health panel (`provider-health-panel.ts`, model in
     `api/models.ts`) is a table with one row per scan. It gains one
     **column**, "Old prints", with a header tooltip "Old IEX prints re-asked
     from yfinance, share of live-price asks", showing "—" for None. On
     `ProviderHealthRow` the field is **optional**
     (`old_print_rate?: number | null`), so existing typed fixtures
     (`provider-health-panel.spec.ts`, `system.store.spec.ts`,
     `providers-tab.spec.ts`) still compile. The column follows the table's
     existing responsive rules at phone, tablet and desktop widths.
   - `provider_degraded_embed` and `provider_recovered_embed` add one line,
     `• Old IEX prints: <rate> of live-price asks`, next to the existing
     `Stale symbols` line, which keeps its meaning.
10. **Watchlist badge** (staff-engineer finding 2).
    `swingbot/admin/watchlist_rows.py:306` passes `router.last_source` through
    as the row's `price_source`. The TS union at `models.ts:1440` adds
    `'yfinance-old-print'`. `watchlist.ts:469` shows the same "fallback" badge
    for both tags, so pre-market and after-hours rows keep the badge they show
    today. `yfinance-fallback` keeps the existing `WATCHLIST_FALLBACK_HINT`
    (`watchlist.ts:179`, pinned verbatim by `watchlist.spec.ts`).
    `yfinance-old-print` gets a new `WATCHLIST_OLD_PRINT_HINT`: "Alpaca's last
    IEX trade is older than 5 minutes outside regular hours, so this price
    comes from yfinance's extended-hours data."

## What does not change

- Which price the scan, requote and plan entry use. They key off the price
  and the fresh/stale marks, not the source string (quant-engineer finding 5,
  verified).
- Regular-session behaviour, in classification and in alerting.
- The daily-bars fallback (`daily_delta`, `_merge`): untouched.
- The breaker, budgets and timeouts.
- Old telemetry rows. There is no backfill: rows from before the deploy lack
  `old_print_rate` and show "—", and their `provider_fallback_rate` stays as
  recorded (`schema-evolution.md`: no read-time upcasting).
  `scripts/ops/v106_soak_check.py:61-63` reads `price_sources` with its
  original meaning. It is a closed historical soak check and is left alone.

## Rollback

There's no schema change; the telemetry row is JSONL with one added field. A
code rollback (`scripts/ops/rollback_to.sh`, `docs/deploy/DEPLOY_HETZNER.md`)
restores the old tagging at once. Rows written by v223 keep their
`yfinance-old-print` counts, which older code ignores in `fallback_rate`. Those
rows read low after a rollback, which is cosmetic (staff-engineer finding 6).

## Tests

- `tests/marketdata/test_alpaca_provider.py`, `_price_verdict` with an
  injected `now` (quant-engineer finding 7):

  | Time (ET) | Trade | Expected |
  |---|---|---|
  | 03:59 | old | hit |
  | 04:00 | old | old print |
  | 09:29 | old | old print |
  | 09:30 | old | miss |
  | 15:59 | old | miss |
  | 16:00 | old | old print |
  | 19:59 | old | old print |
  | 20:00 | old | hit |
  | 13:30 on an early-close day | old | old print |
  | full-day holiday | old | hit |
  | any | fresh | hit |

  Separately: no snapshot, `trade is None` with a two-sided quote, and a zero
  price with a quote are misses. An old print with no two-sided quote is still
  classified as an old print by `latest_quote_answers`. The `latest_prices` and
  `latest_quotes` wrappers return exactly element 0.
- Router: old prints are tagged `yfinance-old-print` and misses
  `yfinance-fallback`, for both entry points. A failed snapshot call, and a
  provider without `*_answers`, both make every wanted symbol
  `yfinance-fallback`. `_stats["old_print"]` counts.
- `fetch`: `_PRICE_SOURCE_KEYS` equals `PRICE_SOURCES + ("none",)`.
  `yfinance-old-print` gets its own bucket. An old print that yfinance also
  fails for lands in `"none"`.
- `scan_run._count_sources`: the daily buckets never include
  `yfinance-old-print`.
- `telemetry.provider_health` with **non-empty** `data_sources`
  (`{alpaca: 85, cache: 2}`) and `price_sources` `{alpaca: 7,
  yfinance-old-print: 80, yfinance-fallback: 0}`:
  - `provider_fallback_rate == 0.0`;
  - `old_print_rate == 80/87`;
  - all-zero counts give both None.
- `ops_watch.provider_verdict`: that row does not alert. A row with real
  `yfinance-fallback` above 20% still alerts (regression).
- `risk.py`'s pooled rate excludes old prints.
- Embeds: the degraded and recovered texts carry the old-print line, with
  "—" for None.
- Frontend:
  - `provider-health-panel.spec.ts`: the new row with a value and with None.
  - `system.store.spec.ts`: the field is carried through.
  - `watchlist.spec.ts`: both tags show the badge, each with its own tooltip.

## Acceptance

Checked read-only on production on the first weekday after deploy:

- No "market-data provider degraded" post between 09:00 and 14:30 UTC or
  between 21:00 and 22:00 UTC.
- Those telemetry rows show `provider_fallback_rate` near 0 and
  `old_print_rate` high.
- Regular-hours rows show `old_print_rate` 0.

## What follows

v224 (to be brainstormed): the stale-scan watchdog alerts on the first session
tick. The scan's analysis phase roughly doubled since 2026-11-03: the median
tick went from 182 s to 314 s, with the bot container at 100% CPU,
`SCAN_WORKERS=1` and a 5-min interval. On top of that, the session's first tick
refetches anchors (crawl ~153 s against ~45 s). Profile it before designing.

## Panel review

- staff-engineer: provider→router contract unspecified; a side channel would
  race `_quote_pool` threads -- applied (item 2: pure `*_answers` return value,
  wrappers keep old shape)
- staff-engineer: watchlist badge consumer `watchlist_rows.py:306` / TS union
  missed -- applied (item 10)
- staff-engineer: Risk/Providers pooled rate changes meaning, transition
  window mixes -- applied (item 8)
- staff-engineer: four "stale" concepts in one area -- applied (Vocabulary;
  renamed to old print / `yfinance-old-print` / `old_print_rate`)
- staff-engineer: `_SOURCE_BUCKETS` second hand-kept tag list -- applied
  (item 4: one constant in `providers/base.py`, daily path pinned)
- staff-engineer: no rollback note; `v106_soak_check.py` reads old meaning --
  applied (Rollback; What does not change)
- quant-engineer: stale/miss classification read from detail shape is wrong
  for `latest_quotes` -- applied (item 1: one `_price_verdict` classifier)
- quant-engineer: old print that yfinance also fails for lands in `"none"`
  -- applied (item 7, stated and tested)
- quant-engineer: two rates on different pools -- applied (item 6: price-only
  pool, labelled "of live-price asks", test with non-empty `data_sources`)
- quant-engineer: a frozen regular-hours IEX feed would become an
  unalerted old print -- applied (item 1: old print only outside the regular
  session; keeps the partner's no-alert decision)
- quant-engineer: verified no downstream price path keys off the tag --
  applied (What does not change)
- quant-engineer: error-path fallback undefined and untested -- applied
  (item 3, router tests)
- quant-engineer: session-boundary and early-close cases untested -- applied
  (Tests table)
