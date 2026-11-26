# v248 — Open-positions price integrity (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-7" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md)
**Brief:** `.superpowers/briefs/2026-11-25-v248-open-positions-price-integrity.md` — its §3 excerpts, §6 complexity and §7 traps override the spec's line cites wherever they disagree.

## Goal

On 2026-11-25, before the US open, the Open positions panel on
bomeo-capital.com showed four held names as `ACTIVE no price` with a bare
`—` for NOW, and four more with a good price beside a red `refresh failed`.
Production showed four separate causes: DOCU has bid/ask but no trade before
the open, and the code treats that as no price while yfinance fails on it
every cycle; after a deploy the overlay brings prices back but never
recomputes STATUS, so `no price` sits next to a priced NOW cell; the
`refresh failed` and `15 h ago` labels fire on old errors and on ordinary
pre-market ages; and, unrelated to the panel, the nightly short-interest job
loses about 30 of 92 symbols every weekday to an exhausted side pool. None of
this changes a trade, but the partner reads the live book from this panel,
and a panel that cries wolf hides the day a price really is gone.

Once this ships, a held position (ACTIVE or PARTIAL) always shows a price:
the live trade when there is one, otherwise yesterday's close tagged
`prev close`, with P&L % and R suffixed `at prev close` and a neutral STATUS
bar that never claims a stop or target is near. A held row with neither shows
`no price yet` and why. STATUS, P&L % and R follow the price the row shows,
including live overlay updates. `refresh failed` and a red age appear only in
the regular session when the price is stale and the error is newer than the
price; pre-market and closed ages read grey (`pre-market · last trade 15 h
ago`). The refresher fetches held names first after a restart and whenever
one has no live price this session; yfinance backs off per ticker after 3
misses (30 min doubling to 4 h, capped at 10 min for a held name in the
session). A new 2-minute ops check pages the ops channel once per ticker per
session day when a held price goes stale in the session, plus one recovery
line. The short-interest job sizes its workers to the side pool and retries
its failures once, serially.

How it works: the server's progress arithmetic moves into one pure module
(`trade_progress.py`) that the client mirrors in `position-progress.ts`; one
JSON fixture drives both test suites so they cannot drift. The mark
repository returns `error_at` from the query it already runs, so the client
can compare it with the price's `as_of`. Backoff and ops-notice dedupe live
in the existing `market_cache` shared store under two new kinds
(`yf_backoff`, `ops_held_price`): no table, no Alembic revision, so rollback
stays image-only. One shared price cell and figure formatter render NOW,
P&L % and R the same on the Trades page and the Dashboard Open positions
table.

What it leaves alone: entries, stops, targets, sizing and alerts; the price
providers (free Alpaca IEX stays, yfinance stays the fallback); the
watchlist; the main DB pool and the side pool's size and timeout. The
bid/ask midpoint is never used as a price.

How we know it worked: every task's narrow tests pass, including the shared
parity fixture on both sides; the closing Playwright check renders the
worst-case row at 390, 768 and 1440 with no value truncated, and
`layout-audit.mjs` reports nothing new on `/dashboard` and `/trades`; CI is
green after the push. After deploy (spec § Rollout): the next pre-market
panel shows grey ages and DOCU on `prev close`; the next 22:40 UTC run logs
no `QueuePool limit` lines and ≤ 10 % failed; the first session sends no
spurious ops notice.

## Architecture

- **Wire** (V248-1): `RefreshMarkRepository.error_marks()` returns text and
  `error_at` from one query; `errors()` delegates to it. `MarketQuote` gains
  `error_at`; `quote_fields` adds `price_error_at`; the `/market/updates`
  quote item adds `error_at`. The session for the age wording is the one
  `status_block()` and `market_meta` already carry (`MarketStatus.session`):
  no new wire field for it.
- **Progress** (V248-2): new `swingbot/admin/api_v1/trade_progress.py`
  holds the bar arithmetic (`row_progress`, `status_fields`,
  `trailing_bar_fields`), `price_kind`-aware; `trades.py` delegates.
  `tests/fixtures/v248/progress_cases.json` is the parity fixture
  (`DATA_READERS` row).
- **Held rows** (V248-3): `_attach_door_prices` prices held rows from
  `last_close` when no live trade exists (`price_kind = prev_close`,
  `price_as_of = None` so any later priced overlay upgrades it);
  `_attach_status_fields` passes `price_kind` through.
- **Backoff** (V248-4, V248-5): new `swingbot/core/marketdata/yf_backoff.py`
  (pure policy + one store read/write per call, fail open) wired into
  `data._yf_quote_details`, the seam both the refresher and the bot's
  `latest_quotes` path use. Config `HELD_PRICE_STALE_ALERT_MIN` lands here.
- **Held first** (V248-6): `refresher/quotes.py` fetches a priority batch
  (all held on the first cycle; held without a live price this session
  afterwards) with the full yfinance cap whatever `scan_running` says.
- **Ops notice** (V248-7, V248-8): pure verdict + line formatter in
  `ops_watch.py`, embed in `notices.py`; `held_price_watch` (2 min) reads
  with `read_quotes(enqueue=False)`, dedupes in the shared store, runs the
  09:00 ET pre-open check, and is guarded and registered in
  `loops._always_on_loops()`.
- **Short interest** (V248-9): workers `max(1, sum(pool_limits()))`, one
  serial retry pass, summary `retried N, recovered M`, WARNING above 10 %.
- **Client progress** (V248-10, V248-11): `ui/position-progress.ts` mirrors
  `row_progress` and `_live_r`; `overlayQuote` recomputes progress and R and
  sets `price_kind = 'live'` when it replaces a price on a trade row, and
  patches `price_error_at`.
- **Labels** (V248-12): `ageText` gains days; `marketAgeLabel` gains the
  extended branch and the new closed wording; `sb-market-value` gains
  `errorAt` and shows the error only in the regular session, when stale and
  when the error is newer than the price (or there is no price).
- **Shared cells** (V248-13): `sb-position-price` (NOW), `sb-position-figure`
  (P&L % / R with `at prev close`), `StatusCell` prev-close title and
  `no price yet`; worst-case row fixture JSON.
- **Pages** (V248-14 Trades, V248-15 Dashboard) adopt the shared cells; the
  closing check (V248-16) drives both at three widths.

**Tech stack:** Python 3.11, Flask, SQLAlchemy, discord.py `tasks.loop`,
pytest; Angular (zoneless, signals, standalone), vitest under `ng test`,
Playwright for the closing check.

## Global Constraints

- **No table, no column, no Alembic revision.** Backoff and dedupe state go
  through `market_shared_repo().read_entries / write_entries` under kinds
  `yf_backoff` and `ops_held_price`; rollback stays image-only.
- **The bid/ask midpoint is never a price**, on the server or the client.
- **Held** means trade-row status `ACTIVE` or `PARTIAL`
  (`trades._OPEN_STATUSES`) on the API and the client; in the refresher it
  is the existing `ctx.symbols.held` (open trades and open plans); in the
  backoff and the ops check it is the tickers of `trades_repo().open_trades()`.
- `price_kind` is `"live"` or `"prev_close"`, present only on held rows from
  the door path; absent means live. `price_error_at` and the updates item's
  `error_at` are ISO-8601 UTC strings or null.
- Thresholds are the spec's: backoff after **3** misses, **30 min** first
  pause doubling to **4 h**, held-in-session cap `HELD_PRICE_STALE_ALERT_MIN`
  (default **10**); ops notice once per ticker per session day, **10**
  tickers then `+N more`, error text **60** chars; pre-open check at
  **09:00 ET**; short-interest WARNING above **10 %** failed.
- The panel's stale threshold stays `admin_refresh.stale_after_s("price",
  session_state)`; no new constant.
- Fail open everywhere the side pool is read or written
  (`DatabaseUnavailable`, SQLAlchemy `TimeoutError`): yfinance goes ahead,
  the ops tick skips, nothing raises into a caller.
- Complexity < 15 for every touched function (`scripts/dev/complexity_gate.py`);
  `list_trades` (E32, legacy) gets no new branch; `_row_from_plan` (14) and
  `_trailing_status_fields` (13) get none either — new logic goes in new
  helpers.
- Narrow verification only: `python scripts/dev/testrun.py file <test>` for
  Python, `cd frontend && npx ng test --watch=false --include <spec>` for a
  frontend spec. No task runs the full suite; CI does.
- Tests that reach Postgres (`tests/db/`, `tests/marketdata/test_refresh_quote_batch.py`,
  `tests/admin/`, `tests/admin_market/`) run after `/replicate-prod-db`, in the
  shared `swing-db` container (port 56789), never a per-task database.
- UI: designed and checked at phone, tablet and desktop together
  (`docs/claude/ui-design.md`); tokens only; the true minus (U+2212) via
  `ui/format.ts`; grey state text uses an existing muted token that meets
  contrast; live updates never move focus.
- Browser checks use Playwright only and log in with `.env`'s
  `ADMIN_USERNAME` / `ADMIN_PASSWORD`, loaded in-process and never printed.
- Scoped commits, one task one or two commits, single-line subjects. Do not
  bump `VERSION.json` in a task; `/close-out` does it.

## Review Focus

1. **A row priced twice** (the sort-by-price branch of `list_trades` runs
   the attach helpers twice): the prev-close fill and the status pass must
   be idempotent and never overwrite a live price — test in V248-3.
2. **A prev-close row meeting a priced update** whose `as_of` is older than
   the bid/ask `quote_at`: it must still upgrade to live (V248-3 clears
   `price_as_of`; V248-11 tests the upgrade and that a priceless update
   never downgrades).
3. **Holiday and half-day**: the pre-open check must not fire on an NYSE
   holiday, and a half-day afternoon reads `after hours` (the tape stays
   open to 20:00 ET, so the server sends `extended`) — tests in
   V248-8 and V248-12.
4. **Busy side pool** during the backoff read/write or the ops tick: no
   exception escapes, yfinance proceeds, the tick skips — tests in V248-4
   and V248-8.
5. **Non-trade consumers** of `overlayQuote` and `sb-market-value`
   (watchlist, tape, tickers): no progress or R keys appear on their rows
   and referential equality holds when nothing changes — tests in V248-11
   and V248-12.

## Parallelisation

Default: run the tasks in id order, one at a time. Sequential edges and
their reasons:

- V248-1 → V248-3: V248-3's API tests assert the full held-row field set,
  `price_error_at` from `quote_fields` included.
- V248-1 → V248-6: both edit `swingbot/admin/market_values.py`.
- V248-2 → V248-3: V248-3 calls `trade_progress.row_progress(...,
  price_kind=)` from `_attach_status_fields`; both edit
  `swingbot/admin/api_v1/trades.py`.
- V248-2 → V248-10: the TypeScript parity spec reads
  `tests/fixtures/v248/progress_cases.json`.
- V248-4 → V248-5: V248-5 wires `yf_backoff.partition` / `record` into
  `data._yf_quote_details`.
- V248-4 → V248-7, V248-8: they read `config.HELD_PRICE_STALE_ALERT_MIN`.
- V248-7 → V248-8: same file (`ops_watch.py`); V248-8 consumes the verdict,
  `HeldPriceItem`, `held_price_lines` and `notices.held_price_embed`.
- V248-10 → V248-11, V248-13: they consume `positionProgress`, `liveR`,
  `PriceKind` and the new `models.ts` fields.
- V248-12 → V248-13: `sb-position-price` passes `errorAt` to
  `sb-market-value`.
- V248-13 → V248-13b: the cells use the formatter.
- V248-13b → V248-14, V248-15: the pages adopt the shared cells.
- V248-14, V248-15 → V248-16: the closing check exercises the finished
  pages.

Safe in parallel if the controller wants to (disjoint files, no contract
between them): **V248-9** with anything (short interest is self-contained);
**V248-4 ∥ V248-1** (`config.py`, `yf_backoff.py` vs `market_refresh.py`,
`market_values.py`, `market_updates.py`); **V248-14 ∥ V248-15** (`trades.ts`
vs `dashboard.ts`); **V248-11 ∥ V248-12** (`live-values.store.ts` vs
`age-hint.ts`, `market-value.ts`). The partner's default is one subagent at a time;
parallel runs only when asked.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V248-1 | `error_at` beside the error from one query; `price_error_at` on trade rows, `error_at` on `/market/updates` | 1 | sonnet | M `swingbot/core/db/repositories/market_refresh.py`, M `swingbot/admin/market_values.py`, M `swingbot/admin/api_v1/market_updates.py`, M `tests/db/test_market_refresh_repos.py`, M `tests/admin_market/conftest.py`, M `tests/admin_market/test_market_values.py`, M `tests/admin_market/test_market_updates.py` | `RefreshMarkRepository.error_marks(keys, *, conn=None) -> dict[str, tuple[str, datetime \| None]]` (`errors()` delegates, still one query); `MarketQuote.error_at: Optional[str] = None` (ISO); `quote_fields()` adds `"price_error_at"`; `/market/updates` quote item adds `"error_at"` |
| V248-2 | Shared progress module (`row_progress`, prev-close neutral bar) + parity fixture + `DATA_READERS` row | 1 | sonnet | C `swingbot/admin/api_v1/trade_progress.py`, C `tests/fixtures/v248/progress_cases.json`, C `tests/admin/test_v248_progress_parity.py`, M `swingbot/admin/api_v1/trades.py`, M `scripts/dev/select_tests.py` | `trade_progress.PRICE_LIVE = "live"`, `PRICE_PREV_CLOSE = "prev_close"`, `PREV_CLOSE_LABEL = "At prev close (not live)"`; `row_progress(row: dict, price: float \| None, *, price_kind: str = PRICE_LIVE) -> dict` (the five bar keys; dispatches trailing / terminal-or-PENDING / standard like `_attach_status_fields`); `status_fields(...)`, `trailing_bar_fields(...)` same signature; fixture rows `{name, row, price, price_kind, expected: {progress_pct, entry_pct, progress_band, blink_seconds, status_label, r_multiple}}` |
| V248-3 | Held rows always priced: live trade, else `last_close` as `prev_close`; neutral STATUS; idempotent | 1 | sonnet | M `swingbot/admin/api_v1/trades.py`, M `tests/admin/test_api_quote_fields.py` | trade row `price_kind: "live" \| "prev_close"` (held door rows only); prev-close row has `current_price = last_close`, `price_as_of = None`, `price_age_s = None`, `current_price_stale = False`; `trades._price_held_rows(live: list[dict]) -> None` |
| V248-4 | `HELD_PRICE_STALE_ALERT_MIN` config + `yf_backoff` policy and shared-store state (fail open) | 2 | sonnet | C `swingbot/core/marketdata/yf_backoff.py`, C `tests/marketdata/test_yf_backoff.py`, M `swingbot/config.py`, M `.env.example`, M `tests/infra/test_config_ops_alerts.py` | `config.HELD_PRICE_STALE_ALERT_MIN` (int, default 10, min 1, max 120, hot-reload); `yf_backoff.KIND = "yf_backoff"`, `entry_key(symbol) -> str` (`"yf_backoff:SYM"`), `BackoffState(misses: int = 0, skip_until: datetime \| None = None, written_at: datetime \| None = None)`, `after_miss(state, now) -> BackoffState`, `is_skipped(state, now, *, held_in_session: bool, held_cap: timedelta) -> bool`, `BackoffBatch(fetch: list[str], skipped: list[str], states: dict[str, BackoffState])`, `partition(tickers: list[str], now: datetime \| None = None) -> BackoffBatch`, `record(batch: BackoffBatch, got: Iterable[str], now: datetime \| None = None) -> None`, `held_symbols(now: datetime \| None = None) -> frozenset[str]` (60 s TTL), `_reset_for_tests() -> None` |
| V248-5 | Backoff at the shared yfinance seam `_yf_quote_details`; both callers honour it; INFO on enter/leave | 2 | sonnet | M `swingbot/core/marketdata/data.py`, M `tests/marketdata/test_refresh_quote_batch.py`, M `tests/marketdata/test_data.py` | none |
| V248-6 | Refresher: held tickers first (first cycle all held; later, held without a live price this session) with the full yfinance cap | 2 | sonnet | M `swingbot/refresher/quotes.py`, M `swingbot/admin/market_values.py`, M `tests/refresher/test_quote_cycle.py`, M `tests/admin_market/test_market_values.py` | `market_values.session_priced(quote: MarketQuote \| None, now: datetime) -> bool`; `quotes._held_primed: bool` (module global, tests reset it) |
| V248-7 | Ops held-price verdict (truth table), phone-readable lines, embed | 3 | sonnet | M `swingbot/commands/scanning/ops_watch.py`, M `swingbot/commands/scanning/notices.py`, M `tests/scanning/test_ops_watch.py` | `ops_watch.HeldPriceItem(symbol: str, age_s: float \| None, error: str \| None, prev_close: bool, no_price: bool)`; `held_price_verdict(*, session: str, age_s: float \| None, has_last_close: bool, uptime_s: float, threshold_min: int, notified: bool, recovered: bool, pre_open: bool) -> str \| None` (`"alert"` / `"recover"` / None); `held_price_lines(items: Sequence[HeldPriceItem], *, limit: int = 10) -> list[str]`; `in_pre_open_window(now: datetime) -> bool`; `notices.held_price_embed(lines: list[str], *, recovery: bool) -> discord.Embed` |
| V248-8 | `held_price_watch` loop: read-only quotes, shared-store dedupe (restart-safe), pre-open check, guard + registration | 3 | sonnet | M `swingbot/commands/scanning/ops_watch.py`, M `swingbot/commands/scanning/loops.py`, M `tests/scanning/test_ops_watch.py`, M `tests/commands/test_loop_guard.py` | `async ops_watch.held_price_tick(now: datetime \| None = None) -> dict[str, list[str]]` (`{"alert": [...], "recover": [...]}`); `@tasks.loop(minutes=2) ops_watch.held_price_watch`; store kind `"ops_held_price"`, key `"ops_held_price:<SYM>:<YYYY-MM-DD>"` (ET session date), value `{"notified_at": iso, "recovered_at": iso \| None}` |
| V248-9 | Short interest: workers = side-pool capacity, one serial retry pass, `retried`/`recovered` summary, 10 % WARNING | 3 | sonnet | M `swingbot/core/market/short_interest.py`, M `swingbot/commands/scanning/loops.py`, M `tests/market/test_short_interest.py` | `refresh_short_interest(...)` returns `{"updated": int, "failed": list[str], "retried": int, "recovered": int}`; `short_interest._worker_count() -> int` |
| V248-10 | Client models + `position-progress.ts` (`positionProgress`, `liveR`) with the shared parity fixture | 4 | sonnet | C `frontend/src/app/ui/position-progress.ts`, C `frontend/src/app/ui/position-progress.spec.ts`, M `frontend/src/app/api/models.ts` | `export type PriceKind = 'live' \| 'prev_close'`; `export interface ProgressInput` (status, direction, entry, stop_loss, target, bar_kind?, runner_best?, banked_exit_price?, risk_stop?, banked_fraction?, banked_r?); `export interface ProgressFields { progress_pct; entry_pct; progress_band; blink_seconds; status_label }`; `export function positionProgress(row: ProgressInput, price: number \| null, kind: PriceKind = 'live'): ProgressFields`; `export function liveR(row: ProgressInput, price: number): number \| null`; `export const PREV_CLOSE_LABEL = 'At prev close (not live)'`; models: `QuoteUpdate.error_at: string \| null`, `RowQuoteFields.price_error_at?: string \| null`, `RowQuoteFields.price_kind?: PriceKind`, `TradeRow.price_kind?: PriceKind` |
| V248-11 | `overlayQuote` recomputes progress and R from the shown price, sets `price_kind = 'live'`, never downgrades, patches `price_error_at` | 4 | sonnet | M `frontend/src/app/stores/live-values.store.ts`, M `frontend/src/app/stores/live-values.store.spec.ts` | none (`overlayQuote` signature unchanged) |
| V248-12 | Session-aware age wording (`pre-market` / `after hours` / `market closed`, days unit) and the `sb-market-value` error rule (`errorAt`) | 4 | sonnet | M `frontend/src/app/ui/age-hint.ts`, M `frontend/src/app/ui/age-hint.spec.ts`, M `frontend/src/app/ui/market-value.ts`, M `frontend/src/app/ui/market-value.spec.ts` | `MarketValue.errorAt = input<string \| null>(null)`; `export function errorIsCurrent(errorAt: string \| null, asOf: string \| null): boolean`; `marketAgeLabel` extended/closed text `'<pre-market \| after hours \| market closed> · last trade <age>'`, tone `'closed'` |
| V248-13 | Shared formatter, worst-case row fixture, `StatusCell` prev-close title and `no price yet` | 5 | sonnet | C `frontend/src/app/ui/position-format.ts`, C `frontend/src/app/ui/position-format.spec.ts`, C `frontend/src/app/testing/fixtures/v248-worst-case-row.json`, M `frontend/src/app/ui/status-cell.ts`, M `frontend/src/app/ui/status-cell.spec.ts` | `export type PositionPriceRow = RowQuoteFields & { status: string }`; `figureTone`, `figureText`, `positionPriceText`, `closeDateTag` and the copy constants; `StatusCellRow.last_close?`; `export function positionFigure(value: number \| null \| undefined, unit: 'pct' \| 'r', kind?: PriceKind \| null): { text: string; suffix: string \| null }`; `export const HELD_STATUSES: ReadonlySet<string>` (`ACTIVE`, `PARTIAL`); `export const NO_PRICE_REASON = 'no trade and no daily close cached'`; `export const PREV_CLOSE_ARIA = 'price is previous close, not live'`; `StatusCellRow.price_kind?`, `StatusCellRow.current_price?` |
| V248-13b | Shared cells: `sb-position-price` (NOW) and `sb-position-figure` (P&L % / R) | 5 | sonnet | C `frontend/src/app/ui/position-price.ts`, C `frontend/src/app/ui/position-price.spec.ts` | `PositionPrice` (`sb-position-price`, `row = input.required<PositionPriceRow>()`); `PositionFigure` (`sb-position-figure`, inputs `value: number \| null`, `unit: 'pct' \| 'r'`, `kind: PriceKind \| null`); `PositionPriceRow` re-exported from `position-format.ts` |
| V248-14 | Trades page: NOW, P&L % and R cells use the shared cells (three widths) | 5 | sonnet | M `frontend/src/app/workspaces/trades/trades.ts`, M `frontend/src/app/workspaces/trades/trades.spec.ts` | none |
| V248-15 | Dashboard Open positions: P&L % and R cells use the shared cells, `errorAt` passed (three widths) | 5 | sonnet | M `frontend/src/app/workspaces/dashboard/dashboard.ts`, M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | none |
| V248-16 | Closing check: worst-case row on `/dashboard` and `/trades` at 390/768/1440 (route-intercepted) + `layout-audit.mjs` | 5 | sonnet | C `frontend/scripts/v248-price-rows-check.mjs`, C `frontend/scripts/v248-price-rows-check-lib.mjs`, C `frontend/scripts/v248-price-rows-check-lib.test.mjs` | none |

16 rows; the cap is 20, so at most four `b` splits fit before this plan is a
`SCOPE`.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-25-v248-open-positions-price-integrity_1-wire-and-held-rows.md` | V248-1..V248-3 | `error_at` on the wire, the shared progress module and parity fixture, held rows priced from prev close |
| 2 | `2026-11-25-v248-open-positions-price-integrity_2-yf-backoff-and-held-first.md` | V248-4..V248-6 | Config field, yfinance per-ticker backoff and its wiring, refresher held-first |
| 3 | `2026-11-25-v248-open-positions-price-integrity_3-ops-notice-and-short-interest.md` | V248-7..V248-9 | Ops verdict and message, the `held_price_watch` loop, the short-interest pool fix |
| 4 | `2026-11-25-v248-open-positions-price-integrity_4-client-progress-and-labels.md` | V248-10..V248-12 | TypeScript progress and R, overlay recompute, session-aware age wording and error rule |
| 5 | `2026-11-25-v248-open-positions-price-integrity_5-shared-cells-and-check.md` | V248-13..V248-16 | Shared price/figure cells and StatusCell, Trades and Dashboard adoption, closing check |

## Decisions the spec left open (binding on part writers)

1. **Python progress home:** `swingbot/admin/api_v1/trade_progress.py`;
   `trades._status_fields` / `_trailing_status_fields` keep their names and
   delegate (the trailing wrapper still adds `_runner_pnl_fields`).
   `trade_proximity` stays the Python source of the band; the TypeScript
   port is held to it by the fixture.
2. **Prev-close bar:** progress position computed from the prev close and
   clamped as today, `progress_band = "neutral"`, `blink_seconds = None`,
   `status_label = PREV_CLOSE_LABEL`; same for the trailing variant.
3. **Prev-close row `price_as_of = None`**, so the overlay's `isNewer`
   upgrades it on any priced update; the NOW cell shows `last_close_date`
   instead of an age.
4. **Session for 1c** is `MarketStatus.session` from `status_block()` /
   `market_meta` (already server-computed at response time); no per-quote
   field.
5. **Error rule:** the error shows only when the session is regular **and**
   (the price is stale or there is no price) **and** `errorIsCurrent`
   (`errorAt` null, `asOf` null, or `errorAt >= asOf`). It reads
   `· refresh failed: <error ≤ 60 chars>` in red; the age turns red with it.
6. **`ageText` days:** ≥ 24 h reads `N d ago` (floor), everywhere.
7. **Backoff held cap** is applied at read time:
   effective `skip_until = min(skip_until, written_at + cap)` for a held
   ticker in the regular session, `written_at` being the entry's
   `fetched_at`. A download exception (not a miss) records nothing; an
   empty frame counts as a miss for every asked ticker.
8. **No-price-at-all** (no live price, no `last_close`) in the regular
   session alerts on first sight, bypassing both the age threshold and the
   uptime guard; outside the session only the 09:00–09:30 ET pre-open window
   on an NYSE trading day pages it.
9. **`DATA_READERS`** names the Python parity test only
   (`testrun.py changed` runs pytest targets); the TypeScript spec reads the
   same file and runs under `ng test` in CI.
10. **Short-interest summary** stays in `loops.daily_short_interest_refresh`;
    it logs at WARNING instead of INFO when `failed > 10 %` of the symbols.
