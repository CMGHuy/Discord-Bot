# v248 — Open-positions price integrity: never unpriced, never falsely alarming

**Version:** ui 1.49.0 · bot 2.19.9
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer, veteran-trader

`Edge: none (integrity)`: no entry, exit, stop or alert rule changes. The
work makes the live book readable: a held position always shows a price,
labels say what is true, and a real outage pages the ops channel. The nightly
short-interest fix restores data that is lost today. `Bump: ui minor`: the
Open positions panel shows different labels, a prev-close fallback and a
STATUS that follows live prices. `Bump: bot patch`: the refresher, the
short-interest job and one new ops notice change behaviour that operators see,
not traders.

## Why

The partner's screenshot (bomeo-capital.com, Open positions, 2026-11-25 about
12:55 UTC, before the US open) showed:

- HOOD, AMAT, GLW and DOCU as `ACTIVE no price`, NOW `—`, and P&L
  `— 15 h ago refresh failed → +3.14% - −1.95%`.
- SNDK, COIN, ARM and NKE with a price, but `10 s ago refresh failed` /
  `1 min ago refresh failed` beside it.

The read-only investigation on production (2026-11-25, 12:57–13:05 UTC) found
four separate causes:

| # | Cause | Evidence | State |
|---|---|---|---|
| 1 | **DOCU has no trade price.** Alpaca IEX returns bid/ask but no last trade before the open, and the code treats a quote with `price: null` as no price. The yfinance fallback fails with `YFPricesMissingError('possibly delisted; no price data found (period=1d)')` every 1–3 min (1,056 hits in bot.log since 11-24 09:00). | `market_cache` `quote:DOCU` = `{"price": null, "source": "alpaca-iex", "bid": 76.57, "ask": 84.18, "trade_at": null, "quote_at": "2026-11-24T21:00Z"}`; `market_refresh_marks` `quote:DOCU` error `no quote` | Ongoing |
| 2 | **HOOD/AMAT/GLW were briefly unpriced after the 12:30 UTC deploy** recreated all three containers. By 13:02 they had live Alpaca prices aged 12–100 s, no error. STATUS kept saying `no price` because `progress_pct`/`progress_band` are computed only server-side when `/api/v1/trades` builds the row (`api_v1/trades.py:1280-1284`), and the live overlay (`live-values.store.ts:19-47`) updates `current_price` but never progress. | `read_quotes(enqueue=False)` in the admin container at 13:02:14 | Transient, recurs on every deploy |
| 3 | **Labels read as alarms when nothing is wrong.** `sb-market-value` shows `refresh failed` whenever `price_error` is non-null (`ui/market-value.ts:21`), with no regard to whether a newer good price exists. The error persists in `market_refresh_marks` until the ticker's next `mark()` (`core/db/repositories/market_refresh.py:160-195`). The `N ago` age is the quote's `trade_at`/`quote_at` (`admin/market_values.py:47-55`), so before the open every healthy ticker reads `15 h ago`. | code trace | By design |
| 4 | **The nightly short-interest job exhausts the side pool.** `daily_short_interest_refresh` (`commands/scanning/loops.py:1055-1082`, 22:40 UTC, weekdays) runs `ThreadPoolExecutor(max_workers=4)` (`core/market/short_interest.py:147`) against a side engine of `pool_size=1, max_overflow=1, pool_timeout=0.25 s` (`core/db/side_engine.py:43-47, 58-64`). Every weekday since 11-12 it logs `QueuePool limit of size 1 overflow 1 reached` and ends `65 updated, 27 failed of 92` (11-24), `62 updated, 30 failed` (11-23). | bot.log 22:40–22:41 on 11-12, 13, 16–20, 23, 24 | Ongoing, silent data loss |

Cause 4 does not touch this panel. It is in scope because the partner chose
to fix it in the same spec (brainstorm, 2026-11-25).

## Goals

- A held position (an open or partial trade) never shows `—` for its price on
  the Open positions panel or the Trades page.
- STATUS, P&L % and R follow the price the row shows, including live updates.
- `refresh failed` and a red age appear only when something is actually wrong:
  the regular session is open and the price is stale.
- An operator learns of a real outage from Discord before the partner sees it
  on the panel.
- The short-interest job completes all symbols it can fetch, every night.

## Non-goals

- No change to entries, stops, targets, sizing or alerts.
- No new price provider and no paid feed (the free Alpaca IEX feed stays).
- No watchlist change. DOCU stays; its yfinance failure is handled by the
  backoff (§ 4).
- No change to the main DB pool (`core/db/engine.py`, 5+5).

## Anti-goals

- A fallback price that looks live. A prev-close figure must never be
  mistaken for a live one: the label, not just the colour, says so.
- Using the bid/ask midpoint as a price. DOCU's pre-open spread was 76.57 /
  84.18, about 10 %; a midpoint would put a fake P&L on the book.
- An alert storm. The ops notice fires once per ticker per session day, plus
  one recovery.
- Hiding a real failure. During the regular session a stale price stays red
  and keeps its error text.

## Approaches

| | What | Trade-off |
|---|---|---|
| A | Frontend only: STATUS from the live price, expiring errors, session-aware wording | Fixes what is seen; DOCU still `—` whenever Alpaca has no trade |
| B | A, plus prev-close fallback for held rows, held-first refresh after a restart, yfinance per-ticker backoff | Fixes the panel and the data gap; an outage is still discovered by looking |
| **C (chosen)** | B, plus a Discord ops notice for stale held prices during the regular session, plus the short-interest pool fix | Most work; closes the loop on detection and on the unrelated nightly loss |

The partner chose C on 2026-11-25.

## Design

### 1. Honest panel (frontend)

**1a. Progress follows the shown price.** Move the progress computation that
`/api/v1/trades` does (`api_v1/trades.py:1280-1284`: `progress_pct`,
`progress_band`, `bar_kind` from entry/stop/target and `current_price`) into
one pure function shared in shape by server and client. The server keeps
computing it for the initial response. The client recomputes it in
`overlayQuote` (`live-values.store.ts`) whenever the overlay replaces
`current_price`, so `StatusCell` (`ui/status-cell.ts:200, 219-226`) never
shows `no price` next to a priced NOW cell. P&L % and R already follow
`current_price` on the client; verify, and cover with a test.

**1b. The error clears when a newer good price exists.** `sb-market-value`
shows `refresh failed` only when `price_error` is set **and** the failure is
newer than the price it sits beside. The backend adds `price_error_at` (the
`market_refresh_marks.error_at` it already stores) to each quote in
`/api/v1/trades` and `/market/updates`. The client compares `price_error_at`
with `price_as_of`; when the price is newer, the error is suppressed.

**1c. Session-aware age wording.** The quote payload carries the
`session_state()` value (`core/market/session.py:251`: regular / extended /
closed) computed server-side at response time. The age label becomes:

| Session | Price age | Shown | Colour |
|---|---|---|---|
| regular | ≤ stale threshold | `12 s ago` | normal |
| regular | > stale threshold | `14 min ago · refresh failed` (error text if any) | red |
| extended | any | `pre-market · last trade 15 h ago` / `after hours · …` | grey |
| closed | any | `market closed · last trade 2 d ago` | grey |

The stale threshold is the existing staleness used for colour in
`market_values._due` (`admin/market_values.py:83-96`); no new constant.

**1d. Prev-close rows.** A row priced from the fallback (§ 2) shows its NOW
value with a `prev close` tag, and its P&L % and R with an `at prev close`
suffix, in grey. STATUS shows the progress bar computed from that price.

**1e. Three widths.** Per `docs/claude/ui-design.md`: on phone the age/error
tag and the `prev close` tag wrap under the value, never truncate; on tablet
and desktop they stay inline. The same rules apply to the Trades page NOW
cell (`trades.ts:453-463`) and the dashboard positions table
(`dashboard.ts:482, 496`). Checked at all three widths with Playwright.

### 2. A held position always has a price (backend)

`_attach_door_prices` (`api_v1/trades.py:1454-1464`) already adds
`last_close` for unpriced rows (`market_values.last_close_fields`). Change the
row contract for held rows (`OPEN`, `PARTIAL`, and `ACTIVE` in the panel's
sense):

- `current_price` = live trade price when present, else `last_close`.
- New field `price_kind`: `live` | `prev_close`. Absent on rows that are not
  held.
- `progress_*`, `pnl_pct`, `r_now` computed from that price.
- The bid/ask midpoint is never used.

The live overlay must not downgrade: a `/market/updates` quote with no price
leaves a `prev_close` row as it is; a quote with a price replaces it and sets
`price_kind = live`.

`last_close` comes from the daily bars already cached; when even that is
missing (a brand-new listing), the row shows `—` as today and § 5 covers it.

### 3. Held tickers first after a restart (refresher)

On the refresher's first cycle after process start, `quote_step`
(`refresher/quotes.py`) fetches `ctx.symbols.held` in a batch of its own
before the watchlist, with the full yfinance budget, whatever
`ctx.scan_running` says. Later cycles keep today's ordering. With 1a in place
the panel catches up on its own within one overlay poll.

### 4. yfinance per-ticker backoff

Today a ticker yfinance cannot serve (DOCU) is retried every cycle. Add a
per-ticker backoff in the yfinance fallback path inside
`data.refresh_quote_batch` (`core/marketdata/data.py:209-230`):

- After **3** consecutive `YFPricesMissingError` (or empty result) for a
  symbol, skip its yfinance fallback for **30 min**; each further miss after
  a skip doubles the pause, capped at **4 h**. One success resets it.
- State lives in the shared market-data layer (Postgres, like the existing
  budget counters), so the bot and the refresher see the same state and it
  survives a restart. Key per symbol, value `{misses, skip_until}`.
- Alpaca is never skipped by this rule.
- A skipped held ticker still gets its prev-close price through § 2.
- Log one `INFO` line when a ticker enters or leaves backoff, not one per
  cycle.

### 5. Ops notice: stale held price during the regular session

A new check in `ops_watch.py`, following its pattern (pure verdict function,
tested by truth table; the loop posts through `loops._ops_channel()` looked up
at call time):

- **Fires** when `session_state() == regular`, the process has been up longer
  than the threshold (as `BOOTED_AT` already does for the scan watchdog), and
  a held ticker's live trade price is older than **10 min** or absent.
- **Once per ticker per session day**: one notice listing the ticker, the age
  of its last trade, its last error text, and whether it is on prev close.
  Several tickers going stale in the same check are grouped in one message.
- **Recovery**: one line when that ticker has a fresh price again.
- Runs every 2 min inside the bot process. Quiet outside the regular session.
- Threshold is a config field `HELD_PRICE_STALE_ALERT_MIN` (default 10) in
  `swingbot/config.py`, hot-reloadable like the rest.

### 6. Short-interest job fits its pool

- `short_interest.py:147`: `max_workers` becomes the side pool's capacity
  (`sum(side_engine.pool_limits())`, 2 in the bot), not 4.
- After the parallel pass, symbols whose fetch returned `None` get **one**
  serial retry pass.
- The summary line keeps its shape and adds `retried N, recovered M`.
- If `failed` is still above 10 % of the symbols, log it at `WARNING`.

No pool size or timeout changes: the 0.25 s fail-open timeout is the side
engine's contract (`side_engine.py:60`, "a busy pool fails open, never
queues").

## Testing

Every change ships with its unit tests (backend and frontend), edge and empty
cases included.

- **1a** — client progress recomputation: price arrives for a `no price` row →
  bar and % appear; price crosses stop/target; missing entry/stop → stays
  `no price`; parity test against the server function on the same fixtures.
- **1b** — error suppressed when `price_as_of > price_error_at`; shown when
  older or equal; shown when no price at all; null `price_error_at`.
- **1c** — label table above, one test per row, plus holiday and half-day via
  the session calendar.
- **1d / 1e** — component tests for the `prev close` tag; Playwright check at
  phone, tablet and desktop widths.
- **2** — `_attach_door_prices`: live wins over last_close; last_close used
  with `price_kind=prev_close`; neither → `—`; bid/ask-only quote → prev
  close, never midpoint; non-held rows unchanged; overlay never downgrades.
- **3** — first cycle orders held first with the full yfinance budget even
  during a scan; second cycle unchanged.
- **4** — 3 misses → skip; skip window doubles, caps at 4 h; a success
  resets; Alpaca path untouched; state shared across two layer clients.
- **5** — verdict truth table (session × age × uptime × already-notified);
  once per day; recovery; grouping; config default.
- **6** — workers equal pool capacity; a failing first pass is retried once;
  summary line fields; the 10 % warning.

Tests reaching Postgres run after `/replicate-prod-db`, in the shared
`swing-db` container.

## Rollout

Ships through the normal CI deploy. After deploy:

1. The panel during the next pre-market: no red `refresh failed`, grey
   `pre-market · last trade …`, DOCU on `prev close`.
2. The next weekday 22:40 UTC: bot.log has no `QueuePool limit` lines from
   `daily_short_interest_refresh`, and the summary shows ≤ 10 % failed.
3. The first regular session: no spurious ops notice. To check the notice
   fires, look for it the next time a held ticker goes stale; do not induce
   one on production.

## Left to the builder

- Where the shared progress function lives on the Python side and how the
  TypeScript twin is kept in parity (a fixture file both sides test against
  is the suggested route).
- The exact backoff key name and table in the market-data layer.
- Message wording of the ops notice, within the content listed in § 5.

## Out of scope

- A paid real-time feed or SIP data from Alpaca.
- Replacing yfinance as the fallback.
- Pre-market P&L from bid/ask.
