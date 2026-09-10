# v83 — MINE news crawl

**Bump:** ui minor · bot none
**Edge:** none (integrity)

## Problem

The MINE lane (`frontend/src/app/shell/tape/names-lane.ts`) shows flagged/watchlisted
symbols with price, change%, and a `context_label` (e.g. earnings countdown), fed by
`TapeStore` refetching `GET /market/tape` on every scan-event tick. There is no
headline/news surface anywhere in the terminal — a trader can be blindsided by a
news-driven move with no in-app signal that something just broke. FMP already has an
unused per-symbol `news()` client method (`swingbot/core/marketdata/fmp_client.py:249`)
but nothing calls it from a live feature.

## Scope

Add a scrolling headline crawl under the MINE lane, showing:
- Per-symbol headlines for names currently flagged in MINE.
- General market-wide breaking headlines (indices, macro), independent of any symbol.
- Both interleaved, newest first, restricted to a rolling recency window (last 2–4h) —
  not "today" by calendar date, since "breaking" is about recency, not the trading day.

Out of scope: news-driven alerts, trade-plan changes, or any strategy/expectancy
signal derived from headlines. This is a situational-awareness display only —
Edge: none (integrity), not a new signal source.

## Architecture

A dedicated `NewsStore`/`news-crawl` pair, decoupled from `TapeStore`, because
"breaking" is time-based (independent poll) while `TapeStore` is refetch-on-scan-event
— folding a second polling responsibility into `TapeStore` would blur its single
responsibility and its existing tests.

**Backend** — new route in `swingbot/admin/api_v1/market.py`, following the existing
`tape()` view's pattern (stateless, symbols as query params, imports inside the view,
try/except degrades instead of 500s):

- `GET /market/news?symbols=<flagged-symbols>` — for each flagged symbol, calls
  `fmp_client.news(symbol)`; additionally calls a new `fmp_client.general_news()`
  method (added alongside the existing `news()`, same client, FMP's general/stock-market
  news endpoint — same provider/API key, no new credentials).
- Merges both result sets, dedupes by article URL, filters to the rolling recency
  window, sorts newest-first.
- Server-side cache with a ~55s TTL (just under the client's 60s poll) so concurrent
  sessions don't multiply FMP calls. On an upstream rate-limit response, serves the
  last cached result past its TTL and logs a warning rather than erroring.

**Frontend** — new `frontend/src/app/stores/news.store.ts`, polling
`api.news(flaggedSymbols)` every 60s on its own timer (independent of `TapeStore`'s
scan-event refetch). Holds the merged, deduped headline list as
`{symbol: string | null, headline: string, source: string, url: string, publishedAt: string}[]`.

New component `frontend/src/app/shell/tape/news-crawl.ts`, rendered as a scrolling
sub-row beneath the existing MINE price row (`names-lane.ts`) — `context_label` and
the price row are untouched. Each headline is clickable, opening `url` in a new tab
(`window.open`).

## Data flow

1. `NewsStore` timer fires (60s) → `api.news(flaggedSymbols)`.
2. Backend checks TTL cache; on miss, fans out to FMP per-symbol `news()` calls (one
   per currently-flagged MINE symbol) plus one `general_news()` call.
3. Merge → dedupe by URL → filter to recency window → sort newest-first → cache →
   return.
4. `NewsStore` replaces its held list; `news-crawl` re-renders the scroll with the
   new list, restarting its animation.

## Error handling

Mirrors `tape()`'s degrade-not-fail philosophy:

- A per-symbol FMP call fails/times out → skip that symbol's news, keep the rest;
  never blocks the general-news half.
- The general-news FMP call fails → per-symbol headlines still show; crawl is just
  shorter.
- Both fail → empty list; the sub-row renders nothing — no error banner, no layout
  shift, same as tape's graceful degradation.
- No flagged symbols in MINE → general news only.
- FMP rate-limit response → serve last cached result past its TTL, log a warning.

## Testing

- Backend: unit tests on the merge/dedup/recency-filter logic and each degrade path
  (symbol fetch raises, general fetch raises, both raise, cache hit vs miss),
  following existing `market.py` route test conventions (FMP calls mocked, no live
  network).
- Frontend: `NewsStore` test for the poll timer and dedup-on-refetch; `news-crawl`
  component test for render and empty state.

## Open questions for the implementation plan

- Exact FMP general-news endpoint/response shape to confirm against the live API
  (verify with `symbol-verifier`/a spike before the plan locks field names).
- Recency window exact bound (2h vs 4h) — pick one during implementation, not a
  design blocker.
