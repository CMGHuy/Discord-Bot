# v223 Provider alert counts only real Alpaca failures — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch, ui patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-10-v223-provider-alert-stale-quote-split-design.md](../specs/2026-11-10-v223-provider-alert-stale-quote-split-design.md)

## Goal

Since the `2e6df134` deploy on 2026-11-09 the ops channel has posted
"market-data provider degraded" every weekday around 09:00 and 21:00 UTC,
though Alpaca has not degraded. `2e6df134` made an old IEX print a miss
whenever the US tape is open, so pre-market and after-hours symbols are
re-asked from yfinance on purpose. The router tags every miss
`yfinance-fallback`, and `telemetry.fallback_rate` counts every
`yfinance-fallback` as an Alpaca failure. The alert therefore fires on the
behaviour that commit was written to produce. An alert that fires twice a day
for nothing trains the partner to ignore it, and then a real Alpaca outage
goes unnoticed.

Once this ships, the provider tells the router *why* a symbol has no price.
An **old print** is a positive trade older than `ALPACA_MAX_TRADE_AGE_SECONDS`,
taken while the tape is open but outside the NYSE regular session. It is
re-asked from yfinance exactly as before but tagged `yfinance-old-print`, not
`yfinance-fallback`. The fallback rate and the alert then measure only real
Alpaca failures. A frozen IEX feed during regular hours is still a miss, so it
still alerts, as it did before `2e6df134`. A new display-only
`old_print_rate` (share of live-price asks) shows on the System Provider
health panel and in the degraded/recovered embeds. The watchlist keeps its
"fallback" badge on both tags, with a separate tooltip for each.

How it works: `AlpacaProvider` gets one classifier, `_price_verdict`. Two new
methods, `latest_price_answers` and `latest_quote_answers`, return
`(result, frozenset of old-print tickers)` from the same single snapshot call,
with no state kept on the shared provider object. The existing
`latest_prices`/`latest_quotes` become thin wrappers with the same return
shape. The router uses the `*_answers` methods when the provider has them;
when it does not, or the call fails, the old-print set is empty and every
unpriced symbol is a miss, which can only over-report failures. The
live-price tags live in one constant, `providers/base.PRICE_SOURCES`, which
`fetch` and `scan_run` build their buckets from.

What it leaves alone: which price the scan, requote and plan entry use (they
never read the tag), regular-session classification, the daily-bars fallback
path, the breaker, budgets, timeouts, and every old telemetry row (no
backfill). Success is measured on production on the first weekday after
deploy: no degraded post in the 09:00-14:30 or 21:00-22:00 UTC windows, those
rows show `provider_fallback_rate` near 0 with `old_print_rate` high, and
regular-hours rows show `old_print_rate` 0.

## Architecture

- `swingbot/core/marketdata/providers/base.py` gains `SOURCE_OLD_PRINT` and
  `PRICE_SOURCES` (V223-1). `fetch._PRICE_SOURCE_KEYS` and
  `scan_run._SOURCE_BUCKETS` are derived from them.
- `alpaca_provider.py` classifies (V223-2). `router.py` dispatches and tags
  (V223-3). `router.py` is the only consumer of the `*_answers` contract.
- `telemetry.provider_health` adds `old_print_rate` (V223-4). The new bucket
  reaches it through `fetch.fetch_stats()["price_sources"]`, which
  `scan_run._sync_run_scan` already spreads into the row. `_sync_run_scan`
  (complexity 94, legacy) is **not touched**.
- Display: notices embeds (V223-4), `/api/v1/system/health` keys and the Risk
  docstring (V223-5), the Angular panel (V223-6), the watchlist badge (V223-7).

**Tech stack:** Python 3.11, pytest, alpaca-py; Angular (standalone, zoneless),
Vitest.

## Global Constraints

- Vocabulary: the new concept is an **old print**, never "stale". The tag is
  `yfinance-old-print` (`SOURCE_OLD_PRINT`), the field is `old_print_rate`, and
  the router stat key is `old_print`.
- Old print requires all four: trade price > 0; `session.is_tape_open(now)`;
  **not** `session.is_nyse_regular_session(now)`; trade age > `max_age_s`.
  An old trade in the regular session is a **miss**. An old trade overnight,
  at the weekend or on a full holiday is a **hit**.
- Contract: `latest_price_answers(tickers, max_age_s) -> (dict[str, float], frozenset[str])`,
  `latest_quote_answers(tickers, max_age_s) -> (dict[str, QuoteDetail], frozenset[str])`.
  No instance state on the provider. `latest_prices`/`latest_quotes` return exactly element 0.
- `telemetry.fallback_rate` formula is unchanged: `yfinance-fallback / (alpaca + yfinance-fallback)`.
- `old_print_rate = yfinance-old-print / (alpaca + yfinance-fallback + yfinance-old-print)`,
  over `price_sources` **only**, rounded to 4 places, None when the sum is 0 or
  `price_sources` is not a dict. Display only: **no alert, no threshold**.
- Label wherever it is shown: "of live-price asks".
- No backfill or read-time upcasting: a row without the field reads None and
  renders "—" (`schema-evolution.md`).
- `scripts/ops/v106_soak_check.py`, `scripts/ops/data_sources_check.py`,
  `scripts/reports/provider_parity_report.py`, `daily_delta.py` and
  `router._merge` are not modified.
- Every function written or changed stays at cyclomatic complexity < 15
  (`python scripts/dev/complexity_gate.py`).
- UI: the panel column and watchlist tooltip follow existing responsive rules
  and are checked at phone (390 px), tablet (768 px) and desktop (1280 px).
- Verification per task is the narrow run (`python scripts/dev/testrun.py file <test>`
  or `npm --prefix frontend test -- --include <spec>`). No task runs the full
  suite; CI does after the push.
- Implemented in a worktree (`.claude/worktrees/`, named per
  `document-lifecycle.md`). Every dispatch names that worktree.

## Parallelisation

| Task | Depends on | Reason |
|---|---|---|
| V223-1 | — | |
| V223-2 | — | disjoint file from V223-1, no contract dependency |
| V223-3 | V223-1, V223-2 | imports `SOURCE_OLD_PRINT` (V223-1); calls the `*_answers` contract (V223-2) |
| V223-4 | V223-1 | `telemetry` imports `SOURCE_OLD_PRINT` from base |
| V223-5 | — | only adds a key name and a docstring; its tests write raw rows |
| V223-6 | — | frontend only, disjoint files |
| V223-7 | V223-6 | the `price_source` union in `models.ts` (written in V223-6) must contain `'yfinance-old-print'` |
| V223-8 | all | release task: bumps, push and pipeline watch need every task merged |

Can run together: {V223-1, V223-2, V223-5, V223-6}. Then {V223-3, V223-4, V223-7}. Then V223-8.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V223-1 | One live-price tag list (base, fetch, scan_run) | 1 | opus | M `swingbot/core/marketdata/providers/base.py`, M `swingbot/core/scanning/fetch.py`, M `swingbot/core/scanning/scan_run.py`, M `tests/scanning/test_scan_telemetry_sources.py` | `base.SOURCE_OLD_PRINT = "yfinance-old-print"`; `base.PRICE_SOURCES: tuple[str, ...] = (SOURCE_ALPACA, SOURCE_YF, SOURCE_FALLBACK, SOURCE_OLD_PRINT)` |
| V223-2 | Alpaca old-print classifier and `*_answers` methods | 1 | sonnet | M `swingbot/core/marketdata/providers/alpaca_provider.py`, M `tests/marketdata/test_alpaca_provider.py` | `AlpacaProvider._price_verdict(snap, now, max_age_s) -> tuple[float \| None, bool]`; `latest_price_answers(tickers, max_trade_age_s) -> tuple[dict[str, float], frozenset[str]]`; `latest_quote_answers(tickers, max_trade_age_s) -> tuple[dict[str, QuoteDetail], frozenset[str]]` |
| V223-3 | Router tags old prints apart from misses | 1 | sonnet | M `swingbot/core/marketdata/providers/router.py`, M `tests/marketdata/test_provider_router.py` | `router._stats["old_print"]`; `router.last_source(t)` may return `"yfinance-old-print"` |
| V223-4 | `old_print_rate` telemetry field and embed line | 1 | sonnet | M `swingbot/core/scanning/telemetry.py`, M `swingbot/core/scanning/scan_run.py` (docstring), M `swingbot/commands/scanning/notices.py`, M `tests/scanning/test_provider_health.py`, M `tests/scanning/test_ops_watch.py` | `telemetry.old_print_rate(price_sources: dict \| None) -> float \| None`; row field `old_print_rate` |
| V223-5 | System-health key and Risk pooled-rate docstring | 2 | sonnet | M `swingbot/admin/api_v1/ops_health.py`, M `swingbot/admin/api_v1/risk.py`, M `tests/admin/test_api_v1_ops_health.py`, M `tests/admin/test_api_v1_risk.py` | `/api/v1/system/health` provider rows carry `old_print_rate` |
| V223-6 | Provider health panel "Old prints" column | 2 | sonnet | M `frontend/src/app/api/models.ts`, M `frontend/src/app/workspaces/system/provider-health-panel.ts`, M `frontend/src/app/workspaces/system/provider-health-panel.spec.ts`, M `frontend/src/app/stores/system.store.spec.ts` | `ProviderHealthRow.old_print_rate?: number \| null`; `Ticker.price_source` union adds `'yfinance-old-print'`; `ProviderHealthLine.oldPrint: string` |
| V223-7 | Watchlist badge tooltip for old prints | 2 | sonnet | M `frontend/src/app/workspaces/watchlist/watchlist.ts`, M `frontend/src/app/workspaces/watchlist/watchlist.spec.ts` | `WATCHLIST_OLD_PRINT_HINT` (exported const) |
| V223-8 | Release, pipeline watch, production acceptance | 2 | sonnet | M `VERSION.json`, M `swingbot/admin/version_history.json` | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | [2026-11-10-v223-provider-alert-stale-quote-split_1-classify-route-telemetry.md](2026-11-10-v223-provider-alert-stale-quote-split_1-classify-route-telemetry.md) | V223-1..V223-4 | tag list, Alpaca classifier, router tagging, `old_print_rate` field and embeds |
| 2 | [2026-11-10-v223-provider-alert-stale-quote-split_2-display-release.md](2026-11-10-v223-provider-alert-stale-quote-split_2-display-release.md) | V223-5..V223-8 | system-health key, Risk docstring, Angular panel and watchlist, release and acceptance |

## Handoff

Implemented and released 2026-11-10: V223-1..7 on main, bot 2.18.1 / ui 1.40.4, CI green on `0fb1f9f0`.
Closed out with `skills: none affected`.

- **Still owed:** V223-8 Step 5 production acceptance (read-only) on the first weekday window after deploy
  (09:00-14:30 and 21:00-22:00 UTC, no degraded post, `old_print_rate` high, regular rows 0), then confirm the ops channel stayed quiet.
- **Accepted blind spot (panel: staff-engineer, quant-engineer, both ADVISORY):** a frozen IEX feed *outside* the NYSE regular session
  while the tape is open now reads as `yfinance-old-print`, which never alerts; it shows only in the display-only `old_print_rate`.
  A frozen feed in regular hours still alerts. If extended-hours scans become frequent, consider alerting on a sustained high `old_print_rate`.
- **Open-bell spike:** just after 09:30 ET (and after a holiday/weekend open) a prior-session print older than the max age is a real miss, so a brief fallback-rate spike is expected.
- **Rollback note:** rolling back to 2.18.0 also reverts commits `3baaad99` (refresher held-symbol yfinance during a scan) and `9a93ac51` (trades last close), which rode this release unspecced.
- **UI:** the compact watchlist card wraps every cell in an inert button, so the old-print hint (and the existing fallback hint) cannot be opened by touch at 390 px. Pre-existing; not fixed here.
