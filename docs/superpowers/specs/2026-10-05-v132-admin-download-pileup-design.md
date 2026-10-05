# v132 — Admin download pile-up: tape cache, lock wait limit, fallback poll

**Version:** ui 1.21.1 · bot 2.0.1 (at writing)
**Bump:** bot patch, ui patch
**Edge:** none (integrity) — the admin UI stops taking itself down; no trade, signal or plan changes

## Why

On 2026-10-05 the production admin container ran out of file handles
(984 of 1024) and stopped rendering pages. Price fetches failed with
`unable to open database file`, DNS and SSL trust-anchor errors — all
symptoms of handle exhaustion, not of Yahoo. A restart cleared it. The bot and
database containers were unaffected.

A stack dump of the live process (py-spy, taken from the host) showed the
whole mechanism:

| Evidence | Value |
|---|---|
| Request threads parked on `yf_safe.py:31` (`with _DOWNLOAD_LOCK`) | 363 |
| …of which in the daily-bars batch (`data.py:117`) | 255 |
| …of which in the live-price batch (`data.py:227`) | 108 |
| Thread holding the lock | one `/api/v1/market/tape` request, in `yfinance.download` (`market.py:692`) |
| Inbound sockets from the tunnel in `CLOSE_WAIT` | 610 |
| Tape requests after the restart, two idle clients, no scan running | 141 in about 3 minutes |

The chain, from trigger to collapse:

1. **Trigger.** When a browser's event stream fails, `EventStream` falls back
   to bumping every event counter every 5 seconds
   (`frontend/src/app/api/event-stream.ts`, `POLL_INTERVAL_MS = 5_000`). Every
   store refetches, the tape included. Two clients in fallback produce about
   24 tape requests a minute — the measured rate.
2. **Expensive call.** Each tape request makes two Yahoo downloads: live
   prices, and **two years of daily bars for every flagged symbol**, used only
   to compute one change percentage per row. The price batch has a 15-second
   cache but nothing stops every caller refetching at once when it expires.
   The daily batch has no cache at all.
3. **Bottleneck.** Every in-process yfinance download is serialised by one
   lock (`swingbot/core/marketdata/yf_safe.py`), a workaround for a yfinance
   thread-safety bug. The lock has no wait limit.
4. **Collapse.** Requests arrive faster than the lock serves them. The tunnel
   times out and closes its side; the thread keeps its socket until its turn.
   Handles climb to the limit, then downloads fail too.

The same errors appear in the log 25 minutes before any unusual traffic. A
screenshot audit that reloaded about 80 pages turned a slow pile-up into a
fast one, but ordinary use reaches the same state on its own.

## What is not known

**Why the clients were in fallback mode.** Two explanations fit, and the fix
for each is different:

- The stream never works through the Cloudflare tunnel (buffering or an idle
  timeout), so every public client polls permanently.
- The server's 8-connection cap was full, so later clients were refused and
  degraded.

Task 1 measures which. Parts A and B below are correct under either answer.

## Design

### Part A — Tape batches are cached and shared (server)

A small single-flight cache in front of the tape's two batch calls, in a new
module `swingbot/admin/tape_cache.py`:

- **Keyed per symbol**, not per symbol list, so two clients with overlapping
  flagged lists share entries.
- **Daily bars:** TTL 300 seconds. The tape reads only the previous close from
  them, which changes once a day.
- **Live prices:** keep the existing 15-second TTL in `data.py`; add
  single-flight in front of it.
- **Single-flight:** when a fetch for a set of missing symbols is already in
  flight, a second caller waits on that fetch's result rather than starting
  its own. One download per expiry, however many tabs are open.
- **Failure is not cached.** A symbol that came back empty is retried on the
  next call; a symbol with an expired entry and a failed refetch keeps serving
  the expired entry (stale beats blank, the tape's existing contract).

`tape()` calls the cache instead of `market_data.get_daily_data_batch` and
`get_current_price_batch` directly. Nothing else changes caller: the scanner,
the chart endpoint and trading decisions keep their current paths, and
`allow_stale=False` callers never touch this cache.

### Part B — The download lock has a wait limit for admin requests (server)

`yf_safe.download` gains an optional `lock_timeout` argument. Without it the
behaviour is exactly today's: wait as long as it takes. With it, a caller that
cannot take the lock in time raises `DownloadBusy`.

- The admin's display paths pass a limit (10 seconds, one config field
  `ADMIN_YF_LOCK_TIMEOUT_SECONDS`). Tape and watchlist rows already degrade to
  "no price" when a batch raises, so a busy lock becomes a priceless row for
  one refresh instead of a held socket.
- The scanner, backtests and every trading-decision path pass nothing and are
  unchanged.
- `DownloadBusy` is logged at `info`, once per request, not as an error with a
  traceback — it is expected under load.

This is the safety net. Part A removes the queue in normal operation; Part B
bounds it when Yahoo itself is slow.

### Part C — The fallback poll stops hammering market data (client)

- **Task 1 result decides the first half.** If the stream fails through the
  tunnel, fix the transport (response headers that disable proxy buffering, a
  ping interval under the tunnel's idle timeout). If the cap was the cause,
  raise or restructure it. Either way the goal is that a healthy public client
  is `live`, not `degraded`.
- **Fallback polling becomes tiered.** `EventStream` keeps the 5-second timer
  for cheap, database-backed events and bumps the market-data events (`scan`,
  which drives the tape) every 30 seconds. Subscribers still never ask which
  mode they are in; the tiering lives inside `EventStream`. The cost is that
  anything else subscribed to `scan` (scan progress on the System workspace)
  also refreshes every 30 seconds while a client is degraded; that is
  accepted, because degraded should be rare once the transport is fixed.
- **A hidden tab does not poll.** While `document.hidden`, the fallback timer
  pauses, and one bump fires when the tab becomes visible again.

## Out of scope

- Replacing Werkzeug's development server. It would not remove the lock, and
  the event broker already records it as an accepted pre-existing condition
  (`swingbot/admin/events/broker.py`, "The cap").
- Upgrading yfinance past 1.4.0 to drop the lock. Worth doing; separate spec,
  because it touches the scanner's data path.
- Computing the tape's change percentage from something cheaper than two years
  of bars. Part A makes the cost irrelevant.

## Error handling

| Situation | Behaviour |
|---|---|
| Yahoo slow, lock held longer than the limit | Tape row renders without price or change; next refresh retries |
| In-flight fetch raises | Every waiter on it gets the same failure and falls back to stale entries |
| Cache holds an expired entry and the refetch fails | Expired entry is served |
| Symbol never fetched successfully | Row renders without price, as today |

## Testing

- **Cache unit tests:** N concurrent callers with a slow fake download produce
  exactly one download; overlapping symbol lists share entries; a failed fetch
  is not cached; an expired entry survives a failed refetch.
- **Lock tests:** with the lock held, a call with `lock_timeout` raises
  `DownloadBusy` inside the limit; a call without it still waits.
- **Tape endpoint test:** 20 concurrent `/market/tape` requests against a
  slow fake download complete with at most two downloads and no thread left
  waiting. This is the regression test for the incident.
- **EventStream tests:** in degraded mode the market-data counter bumps on the
  30-second tier and the others on the 5-second tier; a hidden document pauses
  both; visibility returning fires one bump.
- **Production check after deploy:** with two clients open for ten minutes,
  the admin process's handle and thread counts stay flat.

## Tasks, in order

1. Measure why public clients degrade (stream through the tunnel versus the
   connection cap) and record the answer in this spec.
2. Part A — tape cache with single-flight.
3. Part B — lock wait limit and `DownloadBusy`.
4. Part C — transport fix chosen by task 1, tiered fallback poll, hidden-tab
   pause.
5. Full suite, deploy, production check.

Tasks 2 and 3 are independent of each other and of task 1. Task 4 depends on
task 1's answer.
