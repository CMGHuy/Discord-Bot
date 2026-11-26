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
`/api/v1/trades` does (`api_v1/trades.py:1300-1345`: `progress_pct` and
`progress_band` from entry/stop/target and `current_price`, plus the
trailing-runner variant; `bar_kind` comes from `_row_from_plan`, l.317) into
one pure function shared in shape by server and client. The server keeps
computing it for the initial response. The client recomputes it in
`overlayQuote` (`live-values.store.ts`) whenever the overlay replaces
`current_price`, so `StatusCell` (`ui/status-cell.ts:200, 219-226`) never
shows `no price` next to a priced NOW cell. P&L % already follows
`current_price` on the client (`livePnlPct`); `r_multiple` does not, it is the
server value, so the same recompute updates R from the shown price. Cover
both with tests.

**1b. The error clears when a newer good price exists.** `sb-market-value`
shows `refresh failed` only when `price_error` is set **and** the failure is
newer than the price it sits beside. The backend adds `price_error_at` (the
`market_refresh_marks.error_at` it already stores) to each quote in
`/api/v1/trades` and `/market/updates`. The client compares `price_error_at`
with `price_as_of`; when the price is newer, the error is suppressed.
`market_refresh.errors()` (`core/db/repositories/market_refresh.py:190`)
returns `error_at` beside the text **from the same query**; no second query
per `/market/updates` poll.

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
`market_values._due` (`admin/market_values.py:83-96`); no new constant. It
is deliberately shorter than the ops notice threshold of § 5: the panel turns
red first, and Discord is paged only if the price stays stale for
`HELD_PRICE_STALE_ALERT_MIN`. Both are named in the config help text of the
new field so the gap is visible.

**1d. Prev-close rows.** A row priced from the fallback (§ 2) shows its NOW
value with a `prev close` tag, and its P&L % and R with an `at prev close`
suffix, in grey. STATUS shows a **neutral** position bar from that price: it
never shows a stop-hit, target-hit or near-stop / near-target band while
`price_kind = prev_close`, because before the open the real price can sit far
from yesterday's close (DOCU's pre-open quote was 76.57 / 84.18).

**1e. No price at all.** A held row with neither a live price nor a
`last_close` shows `no price yet` with a one-line reason (`no trade and no
daily close cached`), never a bare `—`.

**1f. One formatter for all three screens.** The `prev close` tag, the age
wording of 1c and the sign/unit format of P&L % and R come from one shared
component and formatter, used by the Open positions panel, the Trades page NOW
cell (`trades.ts:453-463`) and the dashboard positions table
(`dashboard.ts:482, 496`), so one position never reads differently across
screens.

**1g. Three widths and accessibility.** Per `docs/claude/ui-design.md`:

- On phone the age/error tag and the `prev close` tag wrap under the value;
  the NOW, P&L % and R values themselves are never truncated. The worst case
  (a stale held row in the regular session with error text, `prev close` tag
  and `at prev close` suffix) is a named fixture. The table scrolls inside its
  own container, never the page.
- On tablet and desktop the tags stay inline.
- Grey state text meets contrast on the panel background. Each tag has an
  accessible name (e.g. `price is previous close, not live`). Live overlay
  updates never move focus.
- The gate is `node frontend/scripts/layout-audit.mjs` at the three widths for
  the Open positions panel, the Trades page and the dashboard table, driven
  by Playwright.

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
missing (a brand-new listing), the row shows `no price yet` (1e) and § 5
pages it at once.

### 3. Held tickers first (refresher)

`quote_step` (`refresher/quotes.py`) fetches, in a batch of its own before
the watchlist and with the full yfinance budget whatever `ctx.scan_running`
says:

- on the first cycle after process start, every held ticker;
- on every later cycle, each held ticker that has no live price in the
  current session yet (a new fill, or one still on prev close).

Other held tickers keep today's ordering. With 1a in place the panel catches
up on its own within one overlay poll.

### 4. yfinance per-ticker backoff

Today a ticker yfinance cannot serve (DOCU) is retried every cycle. Add a
per-ticker backoff at the shared yfinance seam, `_yf_quote_details`
(`core/marketdata/data.py:399`), so it covers every caller: the refresher's
`refresh_quote_batch` (`data.py:206`) and the bot's quote reads through
`router.latest_quotes(..., _yf_quote_details)` (`data.py:249, 254`), which
feed the stop monitor and lifecycle as well as the panel.

- After **3** consecutive `YFPricesMissingError` (or empty result) for a
  symbol, skip its yfinance fallback for **30 min**; each further miss after
  a skip doubles the pause, capped at **4 h**. One success resets it.
- **Held tickers during the regular session** are capped at
  `HELD_PRICE_STALE_ALERT_MIN` (10 min) instead of 4 h, so an Alpaca miss and
  a long backoff can never leave a held name blind for hours.
- State lives in the existing shared market-data store,
  `market_shared_repo().read_entries / write_entries`
  (`core/db/repositories/market_shared.py:45, 56`, already used by the budget
  and breaker), under kind `yf_backoff`, key per symbol, value
  `{misses, skip_until}`. **No new table and no Alembic revision**, so an
  image-only rollback stays safe (`docs/deploy/DEPLOY_HETZNER.md` § Rolling
  back); an older image ignores the unknown kind. The bot and the refresher
  see the same state and it survives a restart.
- Reading or writing the state fails open when the side pool is busy: the
  yfinance call goes ahead as today.
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
- **No price at all**: a held ticker with neither a live price nor a
  `last_close` is paged on the first check that sees it, regardless of the
  10-min threshold.
- **Pre-open check**: once per session day at 09:00 ET (30 min before the
  open, when resting orders are placed), held tickers with no price at all
  are paged. A held ticker on prev close is *not* paged before the open; that
  is the normal pre-market state.
- **Once per ticker per session day**: one notice listing the ticker, the age
  of its last trade, its last error text, and whether it is on prev close.
  The dedupe and recovery state lives in the same shared store as § 4, kind
  `ops_held_price`, key `<symbol>:<session date>`, so a deploy or restart
  does not re-notify.
- **Phone-readable**: one line per ticker (symbol, age, `prev close` flag),
  error text shortened to 60 characters, at most 10 tickers then `+N more`.
  Several tickers going stale in the same check share one message.
- **Recovery**: one line when that ticker has a fresh price again.
- **Read-only**: the check reads quotes with `read_quotes(enqueue=False)`
  (`admin/market_values.py`), so it never triggers a provider fetch or a
  budget take; a busy side pool makes it skip that tick (fail open).
- Runs every 2 min inside the bot process. Outside the regular session only
  the pre-open check runs.
- Threshold is a config field `HELD_PRICE_STALE_ALERT_MIN` (default 10) in
  `swingbot/config.py`, hot-reloadable like the rest.

### 6. Short-interest job fits its pool

- `short_interest.py:147`: `max_workers` becomes
  `max(1, sum(side_engine.pool_limits()))` (2 in the bot, 1 in a spawned
  worker), not 4. This lowers contention but does not remove it: other bot
  threads share the side pool at 22:40.
- After the parallel pass, symbols whose fetch returned `None` get **one**
  serial retry pass. This is the real fix; the worker cap only makes it
  cheaper.
- The summary line keeps its shape and adds `retried N, recovered M`.
- If `failed` is still above 10 % of the symbols, log it at `WARNING`. That
  warning is the check that the fix worked (§ Rollout 2).

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
- **1d–1g** — component tests for the `prev close` tag, its accessible name,
  the neutral bar (no hit / near band on prev close), `no price yet`, and the
  shared formatter used by all three screens; `layout-audit.mjs` at phone,
  tablet and desktop widths with the worst-case row fixture.
- **2** — `_attach_door_prices`: live wins over last_close; last_close used
  with `price_kind=prev_close`; neither → `no price yet`; bid/ask-only quote
  → prev close, never midpoint; non-held rows unchanged; overlay never
  downgrades.
- **3** — first cycle orders all held first with the full yfinance budget
  even during a scan; later cycles put only held tickers without a live
  price this session first.
- **4** — 3 misses → skip; skip window doubles, caps at 4 h; held in regular
  session capped at 10 min; a success resets; Alpaca path untouched; both
  callers (refresher batch and bot `latest_quotes`) honour it; state shared
  across two layer clients; busy pool fails open.
- **5** — verdict truth table (session × age × uptime × already-notified ×
  no-price-at-all); pre-open check at 09:00 ET; dedupe survives a restart;
  recovery; grouping with `+N more`; never enqueues a fetch; config default.
- **Parity fixture** — the 1a progress cases live in one fixture file read by
  both the Python and the TypeScript tests; it gets a `DATA_READERS` row in
  `scripts/dev/select_tests.py` so `testrun.py changed` picks up both sides.
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

Rollback is image-only: the spec adds no table and no Alembic revision
(§ 4, § 5), so the database needs nothing. Use the image path of
`docs/deploy/DEPLOY_HETZNER.md` § Rolling back
(`SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:sha-<good-sha> ./deploy/deploy.sh`),
or `/rollback` (`scripts/ops/rollback_code.sh`), which keeps all trading data.
`/rollback` refuses by default because `swingbot/refresher/quotes.py` is in
`MARKET_DATA_WRITER_PATHS` (`scripts/ops/rollback_checks.py`): pass
`--allow-writer-drift`, and note that the refresher then stays stopped, so the
admin panel gets no quote refreshes until the hold is released. Do not use
`scripts/ops/rollback_to.sh`: it is a point-in-time restore of Postgres,
`market_data/` and `.env`, which would rewind trading data for no benefit here.

## Left to the builder

- Where the shared progress function lives on the Python side; the parity
  fixture file path (under `tests/fixtures/`).
- Message wording of the ops notice, within the content and limits in § 5.

## Out of scope

- A paid real-time feed or SIP data from Alpaca.
- Replacing yfinance as the fallback.
- Pre-market P&L from bid/ask.

## Panel review

Spec review, 2026-11-25, roles run serially: ux-designer, staff-engineer,
veteran-trader. One BLOCKING, the rest ADVISORY; all applied.

- staff-engineer (BLOCKING): backoff state "in Postgres" with the table left to the builder implies an unwritten migration and rollback step -- applied: § 4 reuses `market_shared_repo` entries (kind `yf_backoff`), no table, no Alembic revision; § Rollout states image-only rollback.
- staff-engineer + veteran-trader: a 4 h yfinance skip can blind a held ticker in the session -- applied: § 4 caps held tickers in the regular session at `HELD_PRICE_STALE_ALERT_MIN`.
- staff-engineer: backoff in `refresh_quote_batch` misses the bot's `latest_quotes` path -- applied: § 4 moves it to `_yf_quote_details` (`data.py:399`), covering both callers.
- staff-engineer: ops-notice dedupe has no home and would re-notify after each deploy -- applied: § 5 stores it in the shared store, kind `ops_held_price`.
- staff-engineer: the 2-min check must not cause fetches or pool pressure -- applied: § 5 reads with `read_quotes(enqueue=False)` and fails open.
- staff-engineer: worker cap of `sum(pool_limits())` does not remove contention and is 1 in a spawned worker -- applied: § 6 states the retry pass is the real fix, uses `max(1, ...)`, and names the 10 % warning as the check.
- staff-engineer: `price_error_at` widens a repository read on a polled endpoint -- applied: § 1b requires it from the same query.
- staff-engineer: the Python/TypeScript parity fixture needs a `DATA_READERS` row -- applied: § Testing.
- staff-engineer: two stale thresholds can disagree -- applied: § 1c states the gap is deliberate (panel red first, Discord after the alert threshold) and names both in the config help.
- veteran-trader: a prev-close row must not show stop/target hit or near bands -- applied: § 1d neutral bar.
- veteran-trader: no notice in the pre-open window when resting orders are placed -- applied: § 5 pre-open check at 09:00 ET for held tickers with no price at all; prev close before the open is normal and not paged.
- veteran-trader + ux-designer: a held row with no price at all is a silent `—` and is not paged explicitly -- applied: § 1e `no price yet` with reason; § 5 pages it on first sight.
- veteran-trader: held-first only on the first cycle leaves new fills behind -- applied: § 3 also puts held tickers without a live price this session first on every cycle.
- ux-designer: name `layout-audit.mjs` as the three-width gate -- applied: § 1g.
- ux-designer: worst-case row width not pinned -- applied: § 1g worst-case fixture, values never truncated, table scrolls inside its container.
- ux-designer: contrast, accessible names, no focus steal -- applied: § 1g.
- ux-designer: grouped ops message must read on a phone -- applied: § 5 one line per ticker, 60-char error, `+N more` after 10.
- ux-designer: one position must read the same on all three screens -- applied: § 1f shared formatter.

## Panel review (pre-close-out, 2026-11-26)

Seats: ux-designer, staff-engineer, veteran-trader, run on `main...2026-11-25-v248-open-positions-price-integrity`.

- staff-engineer: BLOCKING, Rollout called `rollback_to.sh` image-only though it is a PITR restore; `/rollback` needs `--allow-writer-drift` and leaves the refresher stopped -- applied (Rollout rewritten above).
- staff-engineer: refresher and bot command layer now import `swingbot/admin/market_values` (package seam, not in architecture.md) -- rejected for now: ADVISORY, `market_values` is pure and the seam predates v248 for `read_quotes`; carry to a follow-up that moves it under `core/marketdata/shared/`.
- staff-engineer: `yf_backoff` reads the trading store from the marketdata seam (60 s cache, fail open) -- rejected: ADVISORY, as specified.
- staff-engineer: a whole-batch empty frame counts a miss for every ticker, so a yfinance outage can back off the non-held fallback set for hours -- rejected: ADVISORY, carried as a follow-up (held names are capped at 10 min; Alpaca untouched).
- staff-engineer: no off switch for the backoff or `held_price_watch` -- rejected: ADVISORY, carried.
- staff-engineer: dedupe mark written after the post, per-tick WARNING with no ops channel -- rejected: ADVISORY, carried.
- staff-engineer: no owner or prune for the `yf_backoff` / `ops_held_price` market_cache kinds -- rejected: ADVISORY, growth is bounded by incidents x universe; carried.
- ux-designer: `aria-label` on plain spans (`prevAria`, `.fig-suffix`) may not be announced -- rejected: ADVISORY, carried.
- ux-designer: full refresh error only in `title`, cut to 60 chars -- rejected: ADVISORY, diagnostic string.
- ux-designer: prev-close bar's aria-label replaces `status_label` -- rejected: ADVISORY, neutral by spec.
- ux-designer: `NO_PRICE_REASON` should carry a next step -- rejected: ADVISORY, carried.
- veteran-trader: prev-close bar hides that yesterday's close is already beyond stop/target -- rejected: ADVISORY, the spec says never claim a stop/target is near; the `at prev close` R figure carries it. Partner's call.
- veteran-trader: a thin pre-market print counts as live and drives Near-stop/target labels -- rejected: ADVISORY, per spec; carried as a partner call.
- veteran-trader: pre-market / after-hours split uses `etHour < 12` on the client clock -- rejected: ADVISORY, cosmetic.
- veteran-trader: confirm the ops notice says the position is unmonitored and re-fires or clears -- rejected: ADVISORY, recovery line exists (V248-7/8).

