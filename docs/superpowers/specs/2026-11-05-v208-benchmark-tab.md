# v208 — Benchmark tab: the bot's account against SPY, QQQ, Nasdaq and Dow

**Version:** ui 1.39.0 · bot 2.16.4
**Bump:** ui minor, bot minor (a new Analytics tab the partner reads daily; a new table, refresher step and endpoint behind it)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, quant-researcher

## Why

The partner wants one plain answer: **is the bot worth running, or would
holding the index have done better?** Specifically, "S&P is up 2% today: what
did the bot do?", and the same comparison over a week, a quarter or the whole
live book.

Nothing answers this today. The Analytics Overview tab has a v94 "SPY indexed"
overlay that is dead. `swingbot/admin/api_v1/analytics.py:89`
`_index_benchmark` reads `spy_cum` from `get_extended_stats`, which stopped
computing it in 4ae117dc. Production always emits `benchmark.spy_indexed: []`,
and `tabs/overview.ts:144-148` only uses it to pick between two caption
strings. No SPY line has ever been drawn from it.

The account's own equity has existed since v172 (`equity_samples`: realized
balance plus open positions marked to market, sampled every 5 minutes in
regular hours, with backfill rows before that). This spec puts that equity on
one % axis with four benchmarks.

## Decisions (agreed 2026-11-05 brainstorm)

1. **Placement:** a new **Benchmark** tab inside Analytics. It is not its own
   nav page and not a public page. v207 viewers may read it (it lives under
   Insights).
2. **Source:** the **live paper book only**, **main ledger only**: exactly the
   v172 `equity_samples` equity definition (`swingbot/core/tracking/equity.py`).
   No backtest replay, and no weak or outlook trades.
3. **One % chart, all lines rebased to 0%** at the first session of the
   selected range. Every benchmark is a toggle.
4. **Benchmarks:** SPY, QQQ (Nasdaq-100), the **Nasdaq Composite (^IXIC)** and
   the **Dow Jones (^DJI)**. All four ship toggleable. Default on: Bot ·
   account, Bot · deployed, SPY, QQQ.
5. **Two bot lines**, because the account sits partly in cash while the
   indexes are 100% invested:
   - **Bot · account:** the honest notional-account % (cash included).
   - **Bot · deployed:** return on the capital actually in open trades.
   - An **exposure band** under the chart (% of equity deployed each day)
     explains why the two differ.
6. **Range picker:** 1W, 1M, 3M (default), YTD, 1Y, All. A range is clamped
   to the first session with equity data, and the clamp is shown ("Live book
   since 2026-08-07").
7. **Today card:** live-ish intraday. While the US regular session is open,
   index and bot figures refresh every ~5 minutes and show "as of HH:MM ET".
   The figures are final after the close.
8. **Stats** for the selected range, for each visible line:
   - total %, max drawdown, and the bot's lead or lag against each visible
     index (the stat strip);
   - **beta** and **alpha** of Bot · account against each visible index, plus
     a **Sharpe** ratio for every line;
   - **up/down capture** against one index picked from a selector.
9. **Daily comparison table**, newest first and paged. Each row has the daily
   % for each index, both bot lines, exposure %, open-trade count, and
   "Beat?" (Bot · account against the capture-selector index).
10. **Layout order, top to bottom** (approved against the mockup): Today card
    → range picker → toggle chips → stat strip (incl. alpha/beta/Sharpe) →
    chart + exposure band → daily table → up/down capture.
11. **Currency toggle: USD / account currency.** The account equity is kept
    in the account currency; the indexes move in USD. A segmented switch
    beside the range picker picks the comparison currency, and every line,
    stat and "Beat?" is computed in it:
    - **USD** (the default when the account currency is not USD): the bot's
      daily equity close is converted to USD at that session's rate.
      Comparison = trading skill only.
    - **Account currency:** each index level is converted into the account
      currency at that session's rate. Comparison = what holding the index
      would have earned in the partner's wallet.
    - When the account currency *is* USD, the switch is hidden and both
      modes are the same series. A test pins that.
    - FX comes from the bot's existing FX store and refresher steps (the
      `fx_convert` path behind `admin/api_v1/money.py`). Do not add a second
      FX source. A session with no rate shows "—" for that session in the
      converted series and is counted as "missing", never as flat.
      Exposure % is currency-free and does not change with the switch.
      Bot · deployed converts its numerator and denominator in the same
      currency, so its % only moves through the FX change of the open P&L.

## Data

### Bot · account daily series

- **Daily close equity:** exactly the close of the Dashboard's
  `equity_candles.mtm_candles(rows, '1D')` candle for that New York calendar
  day (`swingbot/core/tracking/equity_candles.py:134`), reused as it is.
  `mtm_candles` is **not** changed, so the Dashboard is untouched and this
  tab matches it exactly; a test pins that equality. *My call (builder
  check):* this replaces an earlier "last row before 16:00, prefer live"
  rule that would have contradicted the equality.
  - Bot days are then aligned to benchmark sessions: for each NYSE session,
    the bot's close is the candle of that calendar day. A weekend/holiday
    candle (backfill) is not a session and is skipped. A session with no
    candle is "missing" (gap, "—"), and the next session's return is taken
    against the last present close, flagged as spanning the gap.
- **Daily return** `r_t = E_t / E_{t-1} - 1`.
- **Rebase:** cumulative `Π(1+r) - 1` from the first session in range. The
  paper account has no deposits or withdrawals, so `base_balance` changes
  (if the partner ever edits it) are the one known break. *Builder's call:*
  detect a `base_balance` change inside the range and show a marker. Don't
  silently chain across it.

### Exposure and Bot · deployed (new stored field)

`equity_samples` stores no deployed-capital figure, and exposure cannot be
recovered from the existing columns. Add one column:

- **`open_notional`** (`Float(53)`, nullable): `Σ open_shares × price` over
  the held positions priced in that sample, in account currency, converted
  the same way `unrealized_pnl` is.
  - It is the absolute notional, so shorts count positively. Exposure means
    capital at work, not net delta.
  - `NULL` on rows written before the migration.
- **Writers:**
  - The recorder (`commands/scanning/equity_recorder.py`) writes it on every
    new row.
  - `scripts/data/backfill_equity_samples.py` gains the ability to fill it
    for historical `backfill` rows (and to re-derive it for pre-migration
    `live` rows from the same trades and daily closes), so exposure has the
    whole live-book history. *My call (builder check):* pricing intraday
    rows from daily closes is an accepted approximation. A new nullable
    boolean `open_notional_approx` marks re-derived values, and the tooltip
    says "exposure approximate" on days built from them. The acceptance test
    checks the derivation against a fixture, not against live prices.
  - Follow `docs/claude/schema-evolution.md`: an Alembic revision, no
    read-time upcasting.
- **Exposure_t** = mean over the session's samples of
  `open_notional / equity`, as a %.
  - Time-weighted, so a position held for an hour does not count as a full
    day.
  - A session with no `open_notional` values shows exposure "—".
- **Bot · deployed daily return** = `(E_t - E_{t-1}) / D_t`, where `D_t` is
  the session's mean `open_notional`. *My call:* the time-weighted average,
  not the prior close, because a trade opened and closed intraday has a prior
  close notional of 0. That would divide by zero or explode.
  - If `D_t` is 0 or missing, the day's deployed return is 0 for chaining and
    shown "—" in the table.
  - Cap the denominator below at 1% of equity to stop tiny exposures
    producing absurd %s. *Builder may tune this, but must test it.*

### Benchmark series (new table + refresher step)

- **New table `benchmark_bars`:** (`symbol`, `session` date, `close`,
  `adj_close`, `day_pct`, `source_symbol`, `final` bool, `as_of`
  timestamptz), unique on (`symbol`, `session`). It is a Postgres table with
  an Alembic revision, so admin, refresher and bot share it.
  - **Returns are read from `day_pct`, never from close-to-close across
    rows.** *My call (builder check):* a proxy-sourced day (`source_symbol`
    ≠ `symbol`, e.g. DIA for ^DJI) stores the proxy's own day % (a
    like-for-like close/prev-close of the proxy) and leaves `close` NULL,
    because v171 proxies are "change % only, never a level". Mixing levels
    across a source switch would corrupt the return at the edge.
  - `day_pct` uses `adj_close` for SPY/QQQ and `close` for ^IXIC/^DJI (see
    below).
  - **Adjusted history is rewritten.** *My call (builder check):* Yahoo
    revises past adjusted closes after each dividend, so after the close
    the step re-fetches the whole history since `live_since` for the four
    symbols (a few hundred rows, one call each) and overwrites `adj_close`
    and `day_pct`. `final=true` means "the session is closed and its close
    is official", not "never rewritten".
- **New refresher step `benchmarks`**, added to `swingbot/refresher/loop.py`
  `STEPS`:
  - During the regular session, every ~5 minutes, it upserts today's row with
    `final=false` from the latest quote.
  - After the close (and on start-up catch-up), it writes the official daily
    close with `final=true` and back-fills any missing sessions since the
    first equity session.
  - It respects the existing scan-running skip that `_refresh_index` uses.
- **Source:** yfinance daily bars for `SPY`, `QQQ`, `^IXIC`, `^DJI`, like the
  tape (`marketdata/shared/tape.py`). Intraday comes from the existing
  `latest_prices` path (Alpaca for SPY/QQQ, the yfinance tape path for the ^
  symbols).
  - If Yahoo returns nothing for an index, fall back through
    `TAPE_PROXY_SYMBOLS` (`^DJI=DIA`). Add `^IXIC=ONEQ` to its default.
  - A proxy-sourced day is flagged and shown as such in the tooltip.
- **Total return vs price:**
  - SPY and QQQ use `adj_close` (dividends included). That is what holding
    them actually earned.
  - ^IXIC and ^DJI are price indexes and use `close`. The tooltip and a
    footnote say "price only".
  - *My call.* The partner may prefer DIA/ONEQ total-return ETFs instead.
    Flag it, don't decide it silently.
- **Session calendar:** the bot's existing NYSE session helper
  (`is_regular_session` and its calendar). Bot and benchmark series are
  inner-joined on session date.

## Stats (backend, pure functions)

All stats live in a new `swingbot/core/analytics/benchmark.py`: pure
functions over aligned daily-return arrays, no I/O. They are computed for the
selected range only.

| Stat | Definition |
|---|---|
| Total % | `Π(1+r) - 1` |
| Max drawdown | the largest peak-to-trough drop of the cumulative curve, % |
| Lead / lag | `bot_total - index_total`, percentage points |
| Beta | OLS slope of bot-account daily returns on index daily returns |
| Alpha | annualised Jensen alpha, `(mean(r_bot) - β·mean(r_idx)) × 252`. **Risk-free = 0**, labelled "rf = 0" |
| Sharpe | `mean(r)/std(r) × √252`, rf = 0, sample std (ddof=1) |
| Up-capture | `Σ r_bot on index-up days / Σ r_idx on index-up days`, % |
| Down-capture | the same over index-down days (flat days excluded) |
| Capture ratio | up-capture / down-capture |
| Beat count | sessions where `r_bot > r_idx`, split up and down |

**Small-sample guard:**
- Beta, alpha, Sharpe and capture show "—" with the tooltip "needs ≥ 20
  sessions" when the range has fewer than 20 joined sessions.
- Every stat tile shows its `N` (sessions).
- The live book is young, so these numbers are noisy. The tab says so in one
  line under the strip ("N sessions — treat beta/alpha as indicative").
- Never present alpha as edge. It is not a pre-registered measurement and
  `Edge:` stays `none`.

## API

`GET /api/v1/analytics/benchmark?from=YYYY-MM-DD&to=YYYY-MM-DD&capture=SPY`
(`require_auth`; readable by v207 viewers). The response carries:

- `range`: the effective from/to after the clamp, `live_since`, `sessions_n`
- `as_of`, `session_state` (`pre` / `open` / `closed`), `today`: per-line
  today % with `final` flags
- `series[]`: `{key, label, kind: bot|index, total_return: bool,
  points: [{date, cum_pct, day_pct, proxy?}]}` for bot_account, bot_deployed,
  SPY, QQQ, ^IXIC, ^DJI
- `exposure[]`: `{date, pct, open_n}`
- `stats{}` per series key, with N; `vs{}` per index (lead/lag, beta, alpha)
- `capture{}` for the requested index
- `daily[]`: the table rows, paged with `limit`/`before` like the equity
  candles endpoint

The request also takes `currency=usd|account` (decision 11); the response
echoes the effective currency and `account_currency`.

**Today card contract.** *My call (builder check):*
- `pre` (before the open): the card shows the **last completed session**,
  labelled with its date and "final".
- `open`: bot today % = latest live equity sample against the previous
  session's daily close (that close may come from a backfill row, which is
  fine because it is the same equity definition). With no sample yet
  today, the bot cells show "—". They never show 0%.
- `closed`: today's final session.

Other analytics scope filters (ledger, strategy, horizon, direction) **do not
apply**: equity is account-wide. On this tab the scope bar shows only the
date range, with a one-line note. *My call.*

## SPA

- **New tab:**
  - `{ id: 'benchmark', label: 'Benchmark' }` in `analytics.ts:82`
  - a component `tabs/benchmark.ts`
  - the tab union in `analytics.store.ts`
  - a `fetchPanel` entry, so it loads only when it is open
- **Polling:** while `session_state === 'open'` and the tab is visible, the
  tab re-fetches every 5 minutes (it pauses when the page is hidden).
- **Chart:** reuse `<sb-line-chart>` (`ui/line-chart.ts`) for the % lines.
  - Extend it with whatever it lacks (a multi-series hover tooltip giving
    cumulative and day % per series, a dashed style, a 0% baseline), without
    changing the Overview's rendering.
  - The exposure band is a small bar strip that shares the x axis.
  - *Builder's call:* a strip inside the same component vs a sibling. It must
    align to the same dates.
- **Colours:** bot account = primary accent; bot deployed = the same hue,
  dashed; indexes = distinct, colour-blind-safe series colours from the
  existing chart palette. Every line also has a label or legend (not
  colour-only).
- **Three devices** (`docs/claude/ui-design.md`):
  - **Phone:** Today card stacks, chips wrap at ≥ 44 px touch targets, stat
    tiles in 2 columns, chart full width with tap-to-inspect, and the daily
    table scrolls sideways with a sticky date column.
  - **Tablet and desktop:** tiles auto-fit; the table pages at the
    per-page default.
- **Remove the dead v94 overlay:**
  - drop `_index_benchmark` and `benchmark.spy_indexed` from the
    equity-curve endpoint and `models.ts:653`;
  - replace the two Overview caption notes with a one-line link "Compare
    with indexes → Benchmark tab".

## Ordering with v207

v208 does **not** wait for v207 (viewer accounts, planned, not yet
implemented). *My call (builder check):* the endpoint ships behind the
existing `require_auth`, and the tab sits in Analytics like its siblings.
Whichever plan merges second carries the viewer test. If v207 is already
merged when v208 starts, v208 adds "a viewer can GET it" to its endpoint
tests. Otherwise v207's viewer matrix gains the route.

## Non-goals

- Backtest or replay data, and weak or outlook ledgers.
- A public or marketing page.
- Per-trade "did this trade beat SPY over its hold" comparisons.
- Sector ETFs, IWM, or an equal-weight watchlist benchmark.
- A configurable risk-free rate.
- Discord commands for this view.
- Anything that changes trading, sizing or alerts.

## Anti-goals (fails even if it works)

- The Bot · account day closes disagree with the Dashboard equity chart's 1D
  closes.
- A day the index moved but the bot had no equity sample shows the bot as
  "0%". Missing must render as a gap/"—", never as flat.
- Price-only indexes presented as if they were total-return.
- Alpha shown without its N and rf=0 label, or worded as proven edge.
- Today's intraday figures shown without an "as of" stamp, or not marked
  final after the close.

## Tests (ship with the work)

- **`benchmark.py` stats:** known small arrays for each formula, plus empty,
  single-session, all-flat-index (capture undefined → "—"), and zero-variance
  (Sharpe "—") inputs, and the N < 20 guard.
- **Day-close equality:** this tab's daily equity closes equal the Dashboard
  `mtm_candles(…, '1D')` closes on the same fixture.
- **Deployed denominator:** an intraday round-trip day, a zero-exposure day,
  and the 1% floor.
- **`open_notional`:**
  - the recorder writes it (shorts counted absolute, FX-converted);
  - the migration leaves old rows NULL;
  - the backfill fills them.
- **Refresher step:** intraday upsert `final=false`, close write
  `final=true`, catch-up of missing sessions, proxy fallback (stores
  `day_pct` and `source_symbol` with `close` NULL), adjusted-history rewrite,
  and the scan-running skip.
- **Currency toggle:** USD and account-currency series on an EUR fixture, a
  missing FX day rendering as "—", exposure unchanged by the switch, and the
  switch hidden for a USD account (both modes identical).
- **Today card:** the `pre` / `open` (with and without a sample) / `closed`
  states.
- **Endpoint:** clamping to `live_since`, the capture param, paging, a viewer
  can read it, and unknown params are a 400 (house style).
- **SPA:**
  - tab registration and lazy fetch, toggles, range switching;
  - polling only while open and visible;
  - "—" rendering for missing days and small N;
  - the Overview link replacing the dead notes;
  - layout specs at the phone, tablet and desktop widths.
- **The tests DB:** run `/replicate-prod-db` before the store/migration tests.

## What follows

- If the partner wants total-return parity for the price indexes: switch
  ^IXIC/^DJI to ONEQ/DIA (one config line plus a label).
- Once Stage 1 eToro demo trading lands (`docs/claude/etoro-roadmap.md`), a
  third bot line from the demo account balance could sit on the same chart.
