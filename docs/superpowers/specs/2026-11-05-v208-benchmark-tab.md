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
11. **Currency toggle: deferred (see *Amendment after the code brief*).** The
    partner chose a toggle, then confirmed the account is **USD trading US
    stocks**, so the toggle would always be hidden. v208 compares in USD
    only. The design below is kept as the follow-up's starting point.
    Original decision: **Currency toggle: USD / account currency.** The account equity is kept
    in the account currency; the indexes move in USD. A segmented switch
    beside the range picker picks the comparison currency, and every line,
    stat and "Beat?" is computed in it:
    - **USD** (the default when the account currency is not USD): the bot's
      daily equity close is converted to USD at that session's rate.
      Comparison = what the account is worth to a USD holder. *Panel
      (quant-researcher):* this is **not** "trading skill only", because the
      idle cash also moves with EUR/USD. The tooltip says so, and the
      FX-neutral view of the trades is Bot · deployed (below).
    - **Account currency:** each index level is converted into the account
      currency at that session's rate. Comparison = what holding the index
      would have earned in the partner's wallet.
    - When the account currency *is* USD, the switch is hidden and both
      modes are the same series. A test pins that.
    - FX comes from the bot's existing FX store and refresher steps (the
      `fx_convert` path behind `admin/api_v1/money.py`). Do not add a second
      FX source. The FX store keys rates by **Berlin day**
      (`swingbot/core/marketdata/fx_convert.py:37`): an NYSE session maps to
      the Berlin calendar day of its 16:00 ET close (the same date). The
      admin reads FX cache-only (`fetch=False`), so the plan includes a
      one-off **historical-rate backfill** back to `live_since` for the
      account currency pair. A session with no rate after that shows "—" in
      the converted series and counts as "missing" (see *Gaps*), never as
      flat.
    - Exposure % is currency-free and does not change with the switch.
    - **Bot · deployed is always computed in account currency and is
      FX-neutral:** its numerator is trade P&L only, never cash revaluation
      (see below). It is the same series in both modes, and the switch
      leaves it untouched. *Panel (quant-researcher):* converting the whole
      equity delta would have booked cash FX moves as deployed return.

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
    candle is "missing" (gap, "—"); see *Gaps* below.
- **Daily return** `r_t = E_t / E_{t-1} - 1`.
- **Rebase:** the base is the **close of the session before the range's
  first session**, so the first session's return is included. The chart's
  0% point sits on that prior close, and `N` = the number of daily returns
  actually used. Chart, Total % and the N on the tiles always agree. If no
  prior close exists (the very start of the live book), the first session's
  close is the base, and `N` counts one fewer.
- **`base_balance` change:** the paper account has no deposits or
  withdrawals, so an edit to `base_balance` is the one known break. The
  return of the session containing the change is **excluded** from every
  stat (Total %, drawdown, Sharpe, beta, alpha, capture, Beat?). The
  cumulative line carries flat across it, and a marker on the chart names
  it. *Panel (quant-researcher).*

### Gaps (missing bot or FX sessions)

*Panel (quant-researcher):* when a bot return spans one or more missing
sessions (no equity candle, or no FX rate in the selected currency):

- the index return for that pair is the **compounded `day_pct` over the same
  span**, so the cumulative index curve never loses a day;
- the spanning pair is **excluded from beta, alpha, Sharpe, capture and
  Beat?**, which need one-session returns. It still counts toward Total %
  and drawdown for both sides (same span, same compounding);
- the daily table shows the missing sessions as "—" rows and the spanning
  row marked "covers N sessions".

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
  - **Seam** (*panel, staff-engineer*): the recorder builds its row from
    `EquitySnapshot`/`snapshot_at` in `swingbot/core/tracking/equity.py`
    (`equity_recorder.py:73-77`, `:90`). So `EquitySnapshot` gains
    `open_notional` (and the per-session trade P&L used below), computed in
    `equity.py`, the one equity definition. A test pins every existing
    `EquitySnapshot` field, and the Dashboard candles, unchanged on a
    fixture.
  - **Production run of the backfill** (*panel, staff-engineer, was
    BLOCKING*), following `schema-evolution.md` § Before running a data
    revision on production:
    - Order: dry-run on the local replica (`/replicate-prod-db`) printing
      the row counts it would touch, then the PITR/backup check, then the
      run in the `bot` container
      (`docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional`).
    - The script touches **only** `open_notional`/`open_notional_approx`,
      never the existing equity columns.
    - **Rollback:** `UPDATE equity_samples SET open_notional = NULL,
      open_notional_approx = NULL WHERE open_notional_approx IS TRUE`
      (recorder-written rows keep their values). The plan writes this into
      its production task.
  - **Long-run cost:** `open_notional_approx` stays as long as approximated
    rows are in range. Nothing removes it, and it costs one boolean per row.
    The owner is the equity module (`equity.py`).
- **Exposure_t** = mean over the session's samples of
  `open_notional / equity`, as a %.
  - Time-weighted, so a position held for an hour does not count as a full
    day.
  - A session with no `open_notional` values shows exposure "—".
- **Bot · deployed daily return** (*redesigned after the panel,
  quant-researcher*):
  `r_dep_t = P_t / D_t`, where
  - `P_t` = the session's **trade P&L only**: the change in (realized +
    unrealized) trade P&L in account currency, from the previous session
    close to this one. It is not the equity delta, so cash revaluation and
    `base_balance` edits never enter it.
  - `D_t` = the **peak** `open_notional` over the session's samples and the
    previous close. A position held for one hour is divided by its full
    notional, so short holds are not inflated (a time-weighted mean would
    have inflated a 1-hour round trip about 6.5×).
  - If `D_t` is below **5% of equity**, or missing, the session is **not
    chained**: the deployed line carries flat and shows "—" in the table,
    and the session is excluded from deployed stats. This replaces the
    earlier 1% floor, which allowed 100× scaling.
  - `r_dep_t ≤ −100%` cannot happen with a peak-notional denominator for
    long positions. It can for shorts that gap past 100%. Such a session is
    clipped at −100% and flagged. A test covers it.
  - Label everywhere: **"on capital in trades — not account return"**.
- **Exposure_t** keeps the time-weighted mean (it answers "how much of the
  day was capital at work"). Only the deployed denominator uses the peak.

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
  - **The full adjusted-history re-fetch runs once per session day**,
    guarded by a stored "last full refresh" date (*panel, staff-engineer*).
    It never runs on every post-close cycle.
  - It respects the existing scan-running skip that `_refresh_index` uses.
  - `docs/deploy/DEPLOY_HETZNER.md` § The refresher service (v201) lists the
    new step.
  - **Refresher off** (`ADMIN_REFRESHER=off`): `benchmark_bars` stops
    filling. The tab shows the index lines up to the last stored session with
    an empty-state note ("Benchmarks not updating — refresher is off").
    With no rows at all it shows "No benchmark data yet". It never shows
    zeros. A test covers both.
  - **Long-run cost:** about 4 rows a session (~1,000 a year), owned by the
    refresher. Nothing to remove.
- **Source:** yfinance daily bars for `SPY`, `QQQ`, `^IXIC`, `^DJI`, like the
  tape (`marketdata/shared/tape.py`). Intraday comes from the existing
  `latest_prices` path (Alpaca for SPY/QQQ, the yfinance tape path for the ^
  symbols).
  - If Yahoo returns nothing for an index, fall back to a proxy ETF. *Panel
    (staff-engineer):* the proxies come from a **new config key
    `BENCHMARK_PROXY_SYMBOLS`** (default `^IXIC=ONEQ,^DJI=DIA`), not from
    `TAPE_PROXY_SYMBOLS`. That key also drives the tape
    (`swingbot/core/marketdata/shared/tape.py:58-60`) and may be overridden
    in the production `.env`. The tape is untouched, and the new key has a
    safe default, so production needs no `.env` edit.
  - A proxy-sourced day is flagged and shown as such in the tooltip.
- **Total return vs price:**
  - SPY and QQQ use `adj_close` (dividends included). That is what holding
    them actually earned.
  - ^IXIC and ^DJI are price indexes and use `close`. Their **chip labels
    themselves** read "Nasdaq Comp. (price)" and "Dow (price)", and the
    tooltip and footnote repeat it (*panel, financial-advisor*). The
    default-on pair stays SPY + QQQ, both total return.
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
| Up-capture | `Σ r_bot on index-up days / Σ r_idx on index-up days`, %. The tooltip states this sum-ratio formula (not the geometric standard form) |
| Down-capture | the same over index-down days (flat days excluded) |
| Capture ratio | up-capture / down-capture |
| Beat count | sessions where `r_bot > r_idx`, split up and down |
| Bot $ drawdown | the max drawdown of the account line in money (selected currency) |
| Losing-day streak | the longest run of consecutive negative-return sessions for each bot line |

The last two are from the *panel (financial-advisor)*: drawdown in units a
retail trader feels.

**Small-sample guard** (tightened by the *panel, quant-researcher*):
- Beta and Sharpe need **N ≥ 20** one-session pairs. Alpha needs **N ≥ 60**.
  Below that they show "—" with the tooltip "needs ≥ N sessions".
- Capture needs **≥ 10 index-up and ≥ 10 index-down sessions** each.
- Beta shows its standard error, and alpha its t-stat, next to the value
  ("β 0.42 ± 0.18", "α +6.1% (t 0.9)").
- Every stat tile shows its `N`.
- The tab says in one line under the strip: "N sessions, paper book —
  beta/alpha are indicative, not evidence of edge."
- **Multiple comparisons:** alpha is computable for 4 indexes × 2
  currencies × 6 ranges. The **headline pair is fixed: SPY, USD, All**. It
  is the only alpha shown in bold. Every other alpha cell is plain and
  carries "1 of 48 cells" in its tooltip.
- Never present alpha as edge. It is not a pre-registered measurement and
  `Edge:` stays `none`.
- Deployed-line stats show the **share of sessions in range built from
  approximated `open_notional`** next to them ("38% approx."), not only in a
  tooltip (*panel, quant-researcher*).

## Labelling: paper, pre-tax, not advice

*Panel (financial-advisor), was BLOCKING.* The tab answers "worth running?",
so its copy must not read as a verdict or a recommendation:

- **A standing line under the Today card:** "Paper trades only. Returns are
  pre-tax; bot figures include modelled frictions, indexes are buy-and-hold
  with no costs. Not a recommendation or forecast." The frictions wording
  names whatever `frictions.py` models; the plan verifies that.
- **One sentence on tax drag** in the footnote: swing turnover is taxed as
  short-term gains, so after-tax results would differ from this chart.
- **"Beat?" and lead/lag are labelled descriptive:** the column header
  tooltip says "this session's return was higher, not evidence of edge".
- **The Today card's bot cells** read "unrealised · paper" while the session
  is open.
- **Bot · deployed** stays default-on (the partner asked for both lines), but
  its chip and tooltip carry "on capital in trades — not account return".

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
    equity-curve endpoint and `models.ts:653`, plus the `benchmarkSeries`
    computed at `tabs/overview.ts:264-269`, and update the tests that pin
    the shape *in the same task* (*panel, staff-engineer*):
    `tests/admin/test_api_v1_analytics.py:347`,
    `stores/analytics.snapshot.spec.ts:75`, `analytics.store.spec.ts:219`,
    `tabs/overview.spec.ts:56`;
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
- Any return shown without the paper / pre-tax / not-advice line on the tab.
- The USD mode described as "trading skill only".
- A bot return spanning a gap compared with a one-session index return.

## Tests (ship with the work)

- **`benchmark.py` stats:** known small arrays for each formula, plus empty,
  single-session, all-flat-index (capture undefined → "—"), and zero-variance
  (Sharpe "—") inputs, and the N < 20 guard.
- **Day-close equality:** this tab's daily equity closes equal the Dashboard
  `mtm_candles(…, '1D')` closes on the same fixture.
- **Deployed return:** an intraday round-trip day (peak denominator), a
  zero-exposure day, the 5% no-chain threshold, a short gapping past −100%
  (clipped and flagged), and a cash-FX-only day giving 0 deployed return.
- **Gaps:** a missing bot session (index compounded over the span, the pair
  excluded from beta/Sharpe/capture/Beat?), a `base_balance` change
  excluded from stats, and rebase N matching the returns used.
- **Guards:** N thresholds (20 / 60 / 10+10), beta SE and alpha t-stat on a
  known fixture, and headline-alpha bolding.
- **Labelling:** the paper/pre-tax line present, price-only chip labels,
  and the refresher-off empty state.
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

## Amendment after the code brief (2026-11-05)

The plan-briefer (`.superpowers/briefs/2026-11-05-v208-benchmark-tab.md`
§ 0) found five places where this spec does not match the code. Resolved as
follows:

1. **The equity pipeline does no FX conversion.** `equity.py`, the recorder,
   `equity_candles.py` and the backfill sum P&L in each ticker's quote
   currency. **Partner (2026-11-05): the account is USD and the book is US
   stocks**, so equity is USD already. Consequences:
   - **The currency toggle (decision 11) is out of v208.** v208 compares in
     USD only. There is no `currency` request parameter, no index FX
     conversion and no historical FX backfill. Exposure and deployed-return
     figures are USD.
   - `open_notional` is stored **unconverted, like `unrealized_pnl`** (the
     same quote-currency sum).
   - The tab asserts the precondition. If `account_currency_code() != 'USD'`
     or any open or in-range trade has a non-USD quote currency, the tab
     shows a banner: "Benchmark assumes a USD account trading USD stocks —
     figures may be mixed-currency". Tested.
   - Follow-up (its own spec, only if the account ever leaves USD):
     converting equity at record time plus the toggle as designed in
     decision 11.
2. **The live book models no frictions.** `swingbot/core/edge/frictions.py`
   is used only by backtests and screens, and
   `core/tracking/performance.py:15` ignores slippage and fees. The standing
   label is corrected to: "Paper trades only. Returns are pre-tax and
   **exclude fees and slippage**; indexes are buy-and-hold. Not a
   recommendation or forecast." The anti-goal is unchanged.
3. **Session calendar.** Use the holiday- and half-day-aware
   `is_nyse_regular_session` / `session_state` / `nyse_calendar()` /
   `session_close` everywhere in v208, not the weekday-only
   `is_regular_session`. A live sample recorded on an NYSE holiday falls on
   a non-session day, and the alignment in *Bot · account daily series*
   already skips it. The recorder itself is not changed here; its use of
   the weekday-only helper is noted as a separate integrity fix.
4. **FX rate semantics:** moot for v208 (see 1).
5. **Promoted columns.** The new `equity_samples` columns and every
   `benchmark_bars` column are added to the `register()` promoted tuple and
   to `PROMOTION_REASONS`, per `schema-evolution.md`. Otherwise they land in
   `doc` JSON. `_prepared()` rounding is extended to `open_notional`. A
   repository test reads each new column back from its real column.

Spec line references for the recorder (`equity_recorder.py:73-77, :90`) are
approximate; the brief has the exact lines.

## Panel review

Run 2026-11-05 on a6814db8: staff-engineer, financial-advisor, quant-researcher (serial).

**BLOCKING**
- staff-engineer: open_notional backfill rewrites prod rows with no run plan or rollback -- applied (dry-run on replica, PITR check, bot-container command, NULL-reset rollback, columns touched limited).
- financial-advisor: figures not labelled pre-tax / pre-cost / paper -- applied (standing line under Today card, tax-drag footnote, anti-goal).
- financial-advisor: "worth running?" + Beat?/lead-lag invite a verdict on a small paper book -- applied (paper/not-advice line, Beat? and lead/lag labelled descriptive, "not evidence of edge" under the strip).

**ADVISORY**
- quant-researcher: USD mode is not "trading skill only"; cash FX leaks into deployed numerator -- applied (USD mode relabelled; deployed redesigned on trade P&L only, FX-neutral, identical in both modes).
- quant-researcher: time-weighted denominator inflates short holds, 1% floor allows 100x, r <= -100% -- applied (peak-notional denominator, 5% no-chain threshold, clip + flag at -100%, tests).
- quant-researcher: gap-spanning bot returns paired with one-session index returns -- applied (new Gaps section: compound index over span, exclude pair from beta/Sharpe/capture/Beat?).
- quant-researcher: one N>=20 gate too weak; capture needs up/down counts; show uncertainty -- applied (alpha N>=60, capture 10+10, beta SE, alpha t-stat).
- quant-researcher: alpha across 48 cells, no headline pair -- applied (headline SPY/USD/All, others tooltip "1 of 48 cells").
- quant-researcher: base_balance break undefined for stats -- applied (session excluded from all stats, line carries flat, marker).
- quant-researcher: rebase point vs N ambiguous -- applied (base = prior session close, N = returns used).
- quant-researcher: sum-ratio capture not the standard form -- applied (formula in tooltip).
- quant-researcher: share of approximated exposure days hidden in tooltip -- applied (shown next to deployed stats).
- quant-researcher: stale mark prices bias beta (hand-off to quant-engineer) -- rejected: out of this panel's roles; the recorder already skips writes with open positions but no live prices (equity_recorder.py `_record`), noted for the plan's quant-engineer review if one runs.
- staff-engineer: ^IXIC=ONEQ in TAPE_PROXY_SYMBOLS reaches the tape and may be overridden by prod .env -- applied (separate BENCHMARK_PROXY_SYMBOLS key with safe default; tape untouched).
- staff-engineer: FX store keyed by Berlin day, cache-only on admin, no history -- applied (session->Berlin-day mapping stated, one-off historical FX backfill to live_since).
- staff-engineer: full adj-history refetch every post-close cycle; refresher-off empty state undefined -- applied (once-per-session-day guard, empty states, DEPLOY_HETZNER step listed).
- staff-engineer: recorder change goes through EquitySnapshot in equity.py -- applied (seam named, existing fields + Dashboard pinned unchanged).
- staff-engineer: dropping spy_indexed breaks pinned tests -- applied (tests and benchmarkSeries listed for the same task).
- staff-engineer: new column/table have no owner or removal note -- applied (long-run cost lines).
- staff-engineer: deployed denominator soundness (hand-off) -- applied via the quant-researcher redesign above.
- financial-advisor: deployed % not comparable to indexes, don't default-on -- applied in part (labelled "on capital in trades -- not account return"); rejected the default-off: the partner asked for both bot lines on the chart.
- financial-advisor: drawdown only in % -- applied (bot $ drawdown, losing-day streak).
- financial-advisor: price-only label only in tooltip -- applied (in chip labels; default pair stays SPY+QQQ total return).
- financial-advisor: tax drag of swing turnover unnamed -- applied (footnote sentence).
- financial-advisor: intraday bot cell could read as banked -- applied ("unrealised · paper").
- financial-advisor: alpha/beta validity and polling design (hand-offs) -- applied via quant-researcher and staff-engineer findings above.
