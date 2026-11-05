# v208 — Benchmark tab: the bot's account against SPY, QQQ, Nasdaq and Dow (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (main @ a131cd9f; its *Amendment after the code brief* overrides earlier spec text)

## Goal

The partner wants one plain answer to "is the bot worth running, or would
holding the index have done better?", whether over one day ("S&P is up 2%
today: what did the bot do?"), a quarter or the whole live book. Nothing
answers it today. The Overview tab's v94 "SPY indexed" overlay is dead:
`get_extended_stats` stopped computing `spy_cum` in 4ae117dc, so production
always sends `benchmark.spy_indexed: []` and no SPY line has ever been drawn.

Once this ships, Analytics gains a **Benchmark** tab. It shows the live paper
book's main-ledger equity (the v172 `equity_samples` definition, the same
1D closes the Dashboard draws) on one % axis with SPY, QQQ (both total
return), the Nasdaq Composite and the Dow (both labelled "price"). Every line
is rebased to 0% at the close before the range starts. Two bot lines sit side
by side: **Bot · account** (cash included, the honest number) and **Bot ·
deployed** (trade P&L on the capital in trades, labelled "not account
return"), with an exposure band under the chart explaining the gap. Around
the chart: a Today card that refreshes every ~5 minutes in session with an
"as of HH:MM ET" stamp, a range picker (1W…All, default 3M), toggle chips, a
stat strip (total %, drawdown in % and $, losing streak, Sharpe, beta ± SE,
alpha with t-stat, every tile with its N), a paged daily table, and
up/down capture against a selectable index.

How it works: two new stored facts feed pure functions. `equity_samples`
gains `open_notional` (Σ |open shares × price|, written by the recorder;
history re-derived from daily closes by the backfill script and flagged
`open_notional_approx`). A new `benchmark_bars` table holds one row per
symbol per NYSE session (`day_pct` is the only return ever read), filled by a
new refresher step `benchmarks` (intraday every 5 minutes, final after the
close, full adjusted-history rewrite once per session day, proxy ETF from the
new `BENCHMARK_PROXY_SYMBOLS` key when Yahoo is blank). Series alignment,
gaps, the `base_balance` break, deployed return and every stat live in three
new pure modules under `swingbot/core/analytics/`; one thin endpoint
`GET /api/v1/analytics/benchmark` loads and assembles them.

What it leaves alone: trading, sizing, alerts and Discord; `mtm_candles` and
the Dashboard equity chart (pinned equal); the tape and `TAPE_PROXY_SYMBOLS`;
the recorder's weekday-only session check; every other analytics endpoint
except the equity curve, which loses its dead `benchmark` key. v208 is
**USD-only**: no currency toggle, no FX conversion; the tab shows a banner if
the account or a book ticker is not USD.

Success is measured by tests (`Edge: none (integrity)`, alpha is never
presented as edge): the tab's daily closes equal the Dashboard's 1D closes on
one fixture; a missing bot session renders "—", never 0%, and its spanning
pair leaves beta/Sharpe/capture/Beat?; the N guards (20 / 60 / 10+10); the
deployed-return edge cases (round trip, 5% no-chain, short clipped at
−100%); the refresher-off and empty states; the paper / pre-tax / not-advice
line; and layout specs at 390 / 820 / 1440 px. In production: `benchmark_bars`
fills by itself after the deploy, and the backfill fills `open_notional` with
a dry-run count that matches the applied count.

## Architecture

- **Storage** (V208-1, V208-2): one Alembic revision `v208_001` adds
  `equity_samples.open_notional` / `open_notional_approx` and creates
  `benchmark_bars` and `benchmark_refresh` (per-symbol "last full refresh"
  date: the stored guard the spec asks for; no generic key/value table
  exists). All new columns are promoted (`register()` tuple +
  `PROMOTION_REASONS`), never left in `doc`.
- **Equity seam** (V208-3, V208-4): `swingbot/core/tracking/equity.py` stays
  the one equity definition. `EquitySnapshot` gains `open_notional`;
  `session_trade_pnl()` gives the deployed numerator from realized legs plus
  the unrealized change (so `base_balance` never enters it). The recorder
  writes the column; `scripts/data/backfill_equity_samples.py
  --open-notional` fills history with a targeted UPDATE, dry-run by default.
- **Benchmark bars** (V208-5, V208-6): `swingbot/core/marketdata/benchmarks.py`
  fetches raw + adjusted daily bars (`yf_safe.download(..., auto_adjust=False)`)
  and builds rows; `swingbot/refresher/benchmarks.py:benchmarks_step` is
  appended to `loop.STEPS` after `quotes.fx_snap_step`.
- **Pure analytics** (V208-7..V208-10b): `benchmark.py` (formulas + N guards),
  `benchmark_series.py` (session alignment, gaps, breaks, deployed return,
  exposure), `benchmark_view.py` (range clamp, rebase, stat assembly, daily
  rows, Today card, response dict). No I/O in any of them.
- **API** (V208-11, V208-12): new `swingbot/admin/api_v1/benchmark.py`
  (loaders + param validation + paging, every function < 15); the dead
  `_index_benchmark` overlay leaves `analytics.py` and the SPA together.
- **SPA** (V208-13..V208-17): typed client + store slice, `<sb-line-chart>`
  extended (colour, dash, gaps, multi-series hover) plus a sibling
  `<sb-exposure-strip>` on the same x scale, and `tabs/benchmark.ts` built in
  three slices (frame + Today card + chips, strip + chart, table + capture +
  footnote).
- **Production** (V208-18): deploy, revision check, refresher fill check,
  `open_notional` backfill dry-run → PITR check → apply → verify, rollback SQL
  written into `DEPLOY_HETZNER.md`.

**Tech stack:** Python 3.11, Flask, SQLAlchemy + psycopg 3, Alembic, pandas,
yfinance via `yf_safe`, pytest; Angular standalone components + signals +
`@ngrx/signals`, Vitest via `frontend/scripts/ng-test.mjs`.

## Global Constraints

- **USD only.** No `currency` request parameter, no index or equity FX conversion, no FX backfill. `open_notional` is stored unconverted, like `unrealized_pnl`.
- Mixed-currency banner, exact copy: `Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency`. Shown when `fx.account_currency_code() != "USD"` or any trade in range or open has a non-USD quote currency.
- Standing line under the Today card, exact copy: `Paper trades only. Returns are pre-tax and exclude fees and slippage; indexes are buy-and-hold. Not a recommendation or forecast.` (the live book models no frictions: `core/tracking/performance.py:15`).
- Footnote tax sentence, exact copy: `Swing turnover is taxed as short-term gains, so after-tax results would differ from this chart.`
- Line under the stat strip, exact copy: `<N> sessions, paper book — beta/alpha are indicative, not evidence of edge.`
- Bot · deployed label everywhere: `on capital in trades — not account return`. Today-card bot cells while open: `unrealised · paper`.
- Chip labels: `Bot · account`, `Bot · deployed`, `SPY`, `QQQ`, `Nasdaq Comp. (price)`, `Dow (price)`. Default on: Bot · account, Bot · deployed, SPY, QQQ.
- Series keys (API and SPA): `bot_account`, `bot_deployed`, `SPY`, `QQQ`, `^IXIC`, `^DJI`. `BENCHMARK_SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")`; total return = SPY, QQQ (`adj_close`); price = ^IXIC, ^DJI (`close`).
- Returns are read from `benchmark_bars.day_pct` only, never close-to-close across rows. Proxy rows: `source_symbol != symbol`, `close` and `adj_close` NULL, `day_pct` = the proxy's own close / prev close − 1.
- A `final = false` bar and today's partial bot candle feed **only** the Today card, never the series, stats or daily table (no-lookahead). Today's session joins the series once `session_state == "closed"` and its four bars are final.
- Sessions come from the holiday- and half-day-aware `nyse_calendar()` / `is_nyse_regular_session` / `session_close` / `last_regular_close` (`swingbot/core/market/session.py`), never the weekday-only `is_regular_session`. A bot candle on a non-session day is skipped.
- Bot · account daily close = the close of `equity_candles.mtm_candles(rows, "1D")` for that NY date, reused unchanged.
- Rebase: base = close of the session before the range's first session; first-session close if none exists. `N` = daily returns actually used.
- Gap rule: a bot return spanning missing sessions pairs with the compounded index `day_pct` over the same span; the pair counts toward Total % and drawdown, never toward beta, alpha, Sharpe, capture or Beat?. Missing renders `—`, never `0%`.
- `base_balance` break: a session whose close-to-close `realized_balance` change differs from its realized legs by more than `0.01` is excluded from every stat; the cumulative line carries flat; a `base_balance` marker names it.
- Deployed: `r_dep = P / D`; `P` = `equity.session_trade_pnl(...)`; `D` = peak `open_notional` over the session's point samples and the previous close; not chained when `D` is missing or `< 0.05 × equity` (`DEPLOYED_MIN_SHARE = 0.05`); clipped at `−1.0` and flagged. Exposure = time-weighted mean of `open_notional / equity` over the session's point samples.
- Guards: beta and Sharpe need `N ≥ 20` one-session pairs; alpha `N ≥ 60`; capture `≥ 10` index-up and `≥ 10` index-down sessions. Below: value `null`, reason `needs ≥ <k> sessions`. Risk-free = 0, labelled `rf = 0`. Sharpe uses ddof = 1. Annualisation 252.
- Headline alpha: SPY over the All range only, rendered bold; every other alpha cell plain with tooltip `1 of 24 cells` (4 indexes × 6 ranges; the spec's 48 counted 2 currencies, removed by the amendment).
- Capture tooltip states the sum-ratio formula: `Σ bot return on index-up days ÷ Σ index return on those days (sum ratio, not the geometric form)`.
- Empty states, exact copy: no bars at all → `No benchmark data yet`; refresher off and bars stop before the last completed session → `Benchmarks not updating — refresher is off`. Never zeros.
- Endpoint: `GET /api/v1/analytics/benchmark`, `require_auth`; params `from`, `to` (`YYYY-MM-DD`), `capture` (one of `BENCHMARK_SYMBOLS`, default `SPY`), `limit` (default 120, max 500), `before` (`YYYY-MM-DD`, daily paging); any other param → 400 `invalid` with `unknown parameter '<x>'; allowed: [...]`.
- New config key `BENCHMARK_PROXY_SYMBOLS`, section `Data Sources`, default `^IXIC=ONEQ,^DJI=DIA`, directly after `TAPE_PROXY_SYMBOLS`, listed in `.env.example`. The tape and `TAPE_PROXY_SYMBOLS` are untouched.
- Revision id `v208_001`, file `swingbot/core/db/migrations/versions/v208_001_benchmark.py`; `down_revision` = what `python -m alembic heads` prints at implementation time (`v205_001` today, `v207_001` if v207 merged first). Exactly one head.
- Every function written or changed < 15 cyclomatic complexity (`python scripts/dev/complexity_gate.py`); the four legacy `analytics.py` functions ≥ 15 are not touched.
- Every UI change is designed and checked at 390 px, 820 px and 1440 px; touch targets ≥ 44 px; the daily table scrolls sideways on phone with a sticky date column; colour is never the only line identifier.
- Narrow test runs only: backend `python scripts/dev/testrun.py file <test>`; frontend `node frontend/scripts/ng-test.mjs frontend --include <spec>`. **No task runs the full suite**; CI does after the push. A task whose tests reach Postgres runs `/replicate-prod-db` first (shared `swing-db` container, port 56789).

## Review Focus

1. **Holiday and half-day sessions:** a live sample recorded on an NYSE holiday (the recorder is weekday-only) must not become a session; a half-day's close is 13:00 ET. Owner: V208-8 (holiday candle skipped), V208-6 (half-day close gates `final`).
2. **The very first live session:** no prior close exists, so the base is the first close and `N` is one fewer; a 1W range starting before `live_since` clamps and says so. Owner: V208-10.
3. **Refresher restarted after days down:** the first post-close cycle must catch up every missing session in one full refresh, not one per cycle, and never re-run on the next cycle. Owner: V208-6.
4. **A proxy day next to a level day:** the return at a source switch comes from `day_pct` only; an intraday row the day after a proxy day (no `close`) is skipped, not computed from NULL. Owner: V208-5.
5. **Today while the session is open with no sample yet:** bot cells `—`, never `0%`; index cells still show with `as of`. Owner: V208-10b (contract), V208-15 (render).

## Parallelisation

| Group | Tasks | Files | Why sequential inside |
|---|---|---|---|
| A storage | V208-1 → (V208-2 ‖ V208-3) → V208-4 | `schema.py`, migration, `repositories/equity_samples.py`, `repositories/benchmark_bars.py`; `equity.py`, `equity_recorder.py`; `backfill_equity_samples.py` | V208-2 and V208-3 need V208-1's columns/tables; their files are disjoint; V208-4 needs V208-1's `update_open_notional` and V208-3's `open_notional_of` |
| B bars | V208-5 → V208-6 | `config.py`, `.env.example`, `marketdata/benchmarks.py` → `refresher/benchmarks.py`, `refresher/loop.py`, `DEPLOY_HETZNER.md` | V208-6 calls V208-5's builders and V208-2's repos |
| C stats | V208-7 | `core/analytics/benchmark.py` | none; pure, may start at once |
| D series | V208-8 → V208-9 → V208-10 → V208-10b | `core/analytics/benchmark_series.py` (8 creates, 9 extends) → `core/analytics/benchmark_view.py` | 9 extends 8's module; 10 consumes 7, 8, 9; 10b extends 10's module; 9 also needs V208-3's `session_trade_pnl` |
| E API | V208-11 ‖ V208-12 | `api_v1/benchmark.py` + `api_v1/__init__.py`; `api_v1/analytics.py` + SPA overlay files | 11 needs 2, 5, 10b; 12 is independent backend-wise; files disjoint |
| F SPA | V208-12 → V208-13 → (V208-14 ‖) → V208-15 → V208-16 → V208-17 | `models.ts` (12 removes, 13 adds), `api-client.ts`, `analytics.store.ts`; `ui/line-chart.ts`, `ui/exposure-strip.ts`; `tabs/benchmark.ts` (15 creates, 16 and 17 extend) | 13 edits `models.ts` after 12; 15 needs 13's store and 14's chart; 16 and 17 extend 15's component |
| G production | V208-18 | `docs/deploy/DEPLOY_HETZNER.md` | needs every task merged and CI green; edits the doc after V208-6 |

The SPA (F) needs only the response contract fixed in the ledger (V208-10's
shape), so V208-13/V208-14 may start before the backend is merged. **v207
overlap:** V207-15 also edits `analytics.ts` and `analytics.spec.ts`, and
V207-5b's `tests/admin/access_expectations.py` must classify every new rule:
if v207 is merged when V208-11 runs, V208-11 adds the `/api/v1/analytics/benchmark`
GET row (`viewer`) and a viewer GET test; otherwise v207 carries both.
`down_revision` for V208-1 likewise follows whichever head exists.

## Task ledger

| Id | Title | Part | Model | Files (C = create, M = modify) | Produces for later tasks |
|---|---|---|---|---|---|
| V208-1 | `v208_001`: `open_notional` columns, `benchmark_bars`, `benchmark_refresh` | 1 | opus | M `swingbot/core/db/schema.py`; C `swingbot/core/db/migrations/versions/v208_001_benchmark.py`; M `swingbot/core/db/repositories/equity_samples.py`; C `tests/db/test_v208_benchmark_schema.py`; M `tests/db/test_equity_samples_repository.py`; M `tests/db/test_unknown_field_round_trip.py` (new tables in `NOT_REPOSITORY_BACKED`; V208-2 moves them to `CASES`) | `equity_samples.open_notional` Float(53) NULL, `open_notional_approx` Boolean NULL (both promoted); `schema.benchmark_bars`: PK (`symbol` Text, `session` Date), `close` Float(53) NULL, `adj_close` Float(53) NULL, `day_pct` Float(53) NULL, `source_symbol` Text NOT NULL, `final` Boolean NOT NULL, `as_of` TIMESTAMPTZ NOT NULL, + `doc`, `updated_at`; `schema.benchmark_refresh`: `symbol` Text PK, `full_refreshed_on` Date NOT NULL, + standard; `EquitySampleRepository.update_open_notional(sample_id: int, open_notional: Decimal \| None, approx: bool \| None, conn=None) -> None`; `_prepared()` rounds `open_notional` to 2 dp |
| V208-2 | `BenchmarkBarRepository` + `BenchmarkRefreshRepository` | 1 | sonnet | C `swingbot/core/db/repositories/benchmark_bars.py`; C `tests/db/test_benchmark_bars_repository.py`; M `tests/db/test_unknown_field_round_trip.py` | `benchmark_bars_repo() -> BenchmarkBarRepository`: `upsert_bars(rows: list[dict], conn=None) -> int` (on conflict (`symbol`,`session`) overwrite every column), `list_range(symbols: Sequence[str], start: date, end: date, conn=None) -> list[dict]` (ordered symbol, session), `last_session(symbol: str, conn=None) -> date \| None`; `benchmark_refresh_repo() -> BenchmarkRefreshRepository`: `full_refreshed_on(symbol: str, conn=None) -> date \| None`, `mark_full_refresh(symbol: str, day: date, conn=None) -> None`. Bar row dict keys: `symbol, session, close, adj_close, day_pct, source_symbol, final, as_of` |
| V208-3 | `EquitySnapshot.open_notional`, `session_trade_pnl`, recorder writes the column | 1 | sonnet | M `swingbot/core/tracking/equity.py`; M `swingbot/commands/scanning/equity_recorder.py`; M `tests/tracking/test_equity_definition.py`; M `tests/commands/test_equity_recorder.py`; C `tests/tracking/test_equity_candles_unchanged_v208.py` | `EquitySnapshot.open_notional: Decimal = Decimal("0")` (last field, defaulted); `equity.open_notional_of(positions: list[dict], prices: dict[str, float]) -> Decimal` (Σ \|shares × price\| over priced positions); `equity.session_trade_pnl(legs: list[RealizedLeg], prev_at: datetime, at: datetime, prev_unrealized: Decimal, unrealized: Decimal) -> Decimal` (Σ leg.amount for prev_at < leg.at ≤ at, plus unrealized − prev_unrealized); recorder rows carry `open_notional` and `open_notional_approx=False` |
| V208-4 | Backfill `--open-notional` (dry-run default, targeted UPDATE) | 1 | sonnet | M `scripts/data/backfill_equity_samples.py`; M `tests/scripts/test_backfill_equity_samples.py` | CLI `--open-notional [--apply]`; `fill_open_notional(repo, trades: list[dict], bars: dict, *, apply: bool) -> OpenNotionalReport`; `OpenNotionalReport(seen: int, filled: int, backfill_rows: int, live_rows: int, unpriced: int)`; dry run prints `open_notional: would fill <filled> rows (<backfill_rows> backfill, <live_rows> live), <unpriced> unpriced`; apply prints `open_notional: filled <filled> rows ...`; touches only `open_notional`/`open_notional_approx` (approx=True); new `build_day_rows` rows also carry `open_notional` + approx=True |
| V208-5 | `BENCHMARK_PROXY_SYMBOLS` + `marketdata/benchmarks.py` bar builders | 2 | sonnet | M `swingbot/config.py`; M `.env.example`; C `tests/test_config_v208_keys.py`; C `swingbot/core/marketdata/benchmarks.py`; C `tests/marketdata/test_benchmarks.py` | `BENCHMARK_SYMBOLS`, `TOTAL_RETURN = frozenset({"SPY","QQQ"})`; `benchmark_proxy_map() -> dict[str, str]`; `history_rows(symbol: str, frame: pd.DataFrame, *, source_symbol: str, sessions: Sequence[date], final_through: date, now: datetime) -> list[dict]`; `fetch_history(symbols: Sequence[str], start: date) -> dict[str, pd.DataFrame]` (raw + adjusted via `yf_safe.download(..., auto_adjust=False)`); `history_with_fallback(symbol: str, start: date, *, sessions: Sequence[date], final_through: date, now: datetime, fetch=fetch_history) -> list[dict]`; `latest_benchmark_prices(symbols: Sequence[str]) -> dict[str, float]`; `intraday_row(symbol: str, prev: dict \| None, price: float \| None, session: date, now: datetime) -> dict \| None` |
| V208-6 | Refresher step `benchmarks` + DEPLOY_HETZNER step line | 2 | sonnet | C `swingbot/refresher/benchmarks.py`; M `swingbot/refresher/loop.py`; M `docs/deploy/DEPLOY_HETZNER.md` (refresher section lists the step); C `tests/refresher/test_benchmarks_step.py` | `benchmarks_step(ctx: CycleContext) -> None` (never raises; swallowed key `ops.refresher.benchmarks`); `INTRADAY_EVERY_S = 300`; `live_since() -> date \| None` (NY date of the earliest `equity_samples` row, any source); `STEPS[-1] is benchmarks_step`, right after `quotes.fx_snap_step` |
| V208-7 | `core/analytics/benchmark.py`: formulas + small-sample guards | 2 | sonnet | C `swingbot/core/analytics/benchmark.py`; C `tests/analytics/test_benchmark_stats.py` | constants `TRADING_DAYS=252`, `MIN_BETA_N=20`, `MIN_SHARPE_N=20`, `MIN_ALPHA_N=60`, `MIN_CAPTURE_SIDE_N=10`; `Estimate(value: float \| None, se: float \| None, t: float \| None, n: int, reason: str \| None)`; `Capture(up: float \| None, down: float \| None, ratio: float \| None, up_n: int, down_n: int, reason: str \| None)`; `BeatCount(up_days: int, up_beat: int, down_days: int, down_beat: int)`; `total_return(r) -> float \| None`; `cumulative(r) -> list[float]`; `max_drawdown(r) -> float \| None`; `money_drawdown(closes) -> float \| None`; `losing_streak(r) -> int`; `sharpe(r) -> Estimate`; `beta(bot, idx) -> Estimate`; `alpha(bot, idx) -> Estimate` (annualised, t-stat); `capture(bot, idx) -> Capture`; `beat_count(bot, idx) -> BeatCount`; all fractions, never % |
| V208-8 | `benchmark_series.py`: account closes, session alignment, gaps, `base_balance` breaks | 3 | opus | C `swingbot/core/analytics/benchmark_series.py`; C `tests/analytics/test_benchmark_series.py` | `bot_session_closes(rows: list[dict], sessions: Sequence[date]) -> dict[date, float]`; `base_balance_breaks(rows: list[dict], legs: list[RealizedLeg], sessions: Sequence[date]) -> set[date]`; `AlignedDay(session: date, bot_close: float \| None, bot_ret: float \| None, span: int, index_ret: dict[str, float \| None], index_proxy: dict[str, bool], missing: bool, base_break: bool)` with property `one_session` (span == 1 and not missing and not base_break); `align(sessions: Sequence[date], closes: dict[date, float], index_pct: dict[str, dict[date, tuple[float \| None, bool]]], breaks: set[date]) -> list[AlignedDay]` |
| V208-9 | `benchmark_series.py`: exposure + Bot · deployed | 3 | opus | M `swingbot/core/analytics/benchmark_series.py`; C `tests/analytics/test_benchmark_deployed.py` | `DEPLOYED_MIN_SHARE = 0.05`; `rows_by_session(rows: list[dict], sessions: Sequence[date]) -> dict[date, list[dict]]` (point rows, NY day, `at` order); `Exposure(pct: float \| None, open_n: int, approx: bool)`; `exposure_by_session(by_day: dict[date, list[dict]]) -> dict[date, Exposure]`; `Deployed(ret: float \| None, clipped: bool, approx: bool, reason: str \| None)` (reason `"no_exposure"` / `"below_min"` / `"missing"`); `deployed_returns(by_day: dict[date, list[dict]], legs: list[RealizedLeg], sessions: Sequence[date]) -> dict[date, Deployed]` |
| V208-10 | `benchmark_view.py`: inputs, session state, clamp, frame, series | 3 | opus | C `swingbot/core/analytics/benchmark_view.py`; C `tests/analytics/test_benchmark_view.py` | `pct`, `SERIES_KEYS`, `LABELS`, `BenchmarkInputs(rows, legs, bars, sessions, now, account_currency: str, mixed_tickers: list[str], refresher_on: bool)`, `view_session_state(now: datetime) -> str` (`pre`/`open`/`closed`), `live_since_of`, `completed_sessions`, `RangeSpec`, `clamp_range`, `index_pct`, `Frame`, `build_frame`, `deployed_counts`, `build_series` |
| V208-10b | `benchmark_view.py`: stats, vs, capture, daily rows, Today card, status, `build_benchmark` | 3 | opus | M `swingbot/core/analytics/benchmark_view.py`; C `tests/analytics/test_benchmark_response.py` | `build_benchmark(inputs, *, start: date \| None, end: date \| None, capture: str) -> dict` returning the **response contract** below (`daily` complete, newest first, no paging; ValueError on unknown capture); `stat(value, n, reason=None) -> dict`; `last_closed_session(sessions, now)`; `benchmarks_status(bars, last_closed, refresher_on) -> (str, date \| None)` |
| V208-11 | `GET /api/v1/analytics/benchmark` | 4 | sonnet | C `swingbot/admin/api_v1/benchmark.py`; M `swingbot/admin/api_v1/__init__.py` (import list in `register()`); C `tests/admin/test_api_v1_benchmark.py`; M `tests/admin/access_expectations.py` only if v207 is merged | route `analytics_benchmark()`; `_load_inputs(now: datetime) -> BenchmarkInputs`; `_page_daily(daily: list[dict], before: date \| None, limit: int) -> tuple[list[dict], bool]`; response = contract + `daily` paged + `daily_has_more: bool` |
| V208-12 | Remove the dead v94 SPY overlay; Overview links to Benchmark | 4 | sonnet | M `swingbot/admin/api_v1/analytics.py`; M `tests/admin/test_api_v1_analytics.py`; M `frontend/src/app/api/models.ts`; M `frontend/src/app/workspaces/analytics/tabs/overview.ts` (+ `overview.spec.ts`); M `frontend/src/app/stores/analytics.snapshot.spec.ts`; M `frontend/src/app/stores/analytics.store.spec.ts` | Overview link text `Compare with indexes → Benchmark tab`, `routerLink="/insights/analytics"`, `queryParams {tab: 'benchmark'}`; `AnalyticsEquityCurve` has no `benchmark` key |
| V208-13 | SPA client, models, store slice for the Benchmark tab | 4 | sonnet | M `frontend/src/app/api/models.ts`; M `frontend/src/app/api/api-client.ts` (+ spec); M `frontend/src/app/stores/analytics.store.ts` (+ `analytics.store.spec.ts`) | TS types `AnalyticsBenchmark`, `BenchmarkSeries`, `BenchmarkPoint`, `BenchmarkStat`, `BenchmarkDailyRow`, `BenchmarkRange = '1W' \| '1M' \| '3M' \| 'YTD' \| '1Y' \| 'All'`; `ApiClient.analyticsBenchmark(params: BenchmarkParams): Observable<AnalyticsBenchmark>` with `BenchmarkParams { from?: string; to?: string; capture?: string; limit?: number; before?: string }`; exported `benchmarkRangeDates(range: BenchmarkRange, today: string): { from?: string; to?: string }`; store: `AnalyticsTab` + `'benchmark'`, state `benchmark`, `benchmarkError`, `benchmarkRange` (default `'3M'`), `benchmarkCapture` (default `'SPY'`), `benchmarkLoadingMore`; methods `setBenchmarkRange(r)`, `setBenchmarkCapture(sym)`, `refreshBenchmark()`, `loadMoreBenchmarkDaily()`; `PanelKey` + `'benchmark'` loaded only while the tab is open |
| V208-14 | `<sb-line-chart>` colour/dash/gaps/multi hover + `<sb-exposure-strip>` | 4 | sonnet | M `frontend/src/app/ui/line-chart.ts` (+ `line-chart.spec.ts`); C `frontend/src/app/ui/exposure-strip.ts` (+ spec) | `LineChartPoint { date: string; value: number \| null; day?: number \| null; flag?: string }`; `LineChartSeries { name: string; points: LineChartPoint[]; color?: string; dashed?: boolean }`; input `hoverDetail: boolean` (default false: Overview tooltip unchanged); `seriesPath` breaks the path at `null`; `ExposureStrip` selector `sb-exposure-strip`, inputs `dates: string[]`, `bars: { date: string; pct: number \| null; approx: boolean }[]` |
| V208-15 | Benchmark tab frame: registration, scope-bar mode, Today card, paper line, range picker, chips, polling, banners | 5 | sonnet | C `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ `benchmark.spec.ts`); M `frontend/src/app/workspaces/analytics/analytics.ts` (+ `analytics.spec.ts`); M `frontend/src/app/workspaces/analytics/scope-bar.ts` (+ spec); M `frontend/scripts/layout-audit-lib.mjs` (+ `layout-audit-lib.test.mjs`) | `BenchmarkTab` selector `sb-benchmark-tab`; signal `visible: WritableSignal<Set<string>>` of series keys; `POLL_MS = 300_000`; scope-bar input `[benchmark]` (date range only + note `Equity is account-wide: ledger, strategy, horizon and direction filters do not apply.`) |
| V208-16 | Benchmark tab: stat strip + chart + exposure band + markers | 5 | sonnet | M `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ spec) | `statTiles` computed; chart series built from `visible()` |
| V208-17 | Benchmark tab: daily table, up/down capture, footnote, three-width layout | 5 | sonnet | M `frontend/src/app/workspaces/analytics/tabs/benchmark.ts` (+ spec) | — |
| V208-18 | Production: deploy, `v208_001` check, refresher fill, `open_notional` backfill run + rollback runbook | 5 | opus | M `docs/deploy/DEPLOY_HETZNER.md` (`### v208: benchmark bars and open_notional`) | — |

### Response contract (V208-10b produces, V208-11 serves, V208-13 types)

`stat` = `{"value": float | null, "n": int, "reason": str | null}`. All `*_pct`
and `day_pct`/`cum_pct` values are percentages (×100, 4 dp); dates are
`YYYY-MM-DD`.

```json
{
  "range": {"from": "2026-08-07", "to": "2026-11-05", "live_since": "2026-08-07",
            "sessions_n": 63, "clamped": true, "is_all": false},
  "as_of": "2026-11-05T15:35:00+00:00", "session_state": "pre|open|closed",
  "account_currency": "USD", "mixed_tickers": [],
  "benchmarks_status": "ok|stale|empty", "benchmarks_last_session": "2026-11-04",
  "today": {"session": "2026-11-05", "final": false,
            "lines": {"bot_account": {"pct": 0.31, "final": false},
                      "SPY": {"pct": 1.02, "final": false}}},
  "series": [{"key": "bot_account", "label": "Bot · account", "kind": "bot",
              "total_return": true,
              "points": [{"date": "2026-08-07", "cum_pct": 0.0, "day_pct": null,
                          "span": 1, "missing": false, "proxy": false,
                          "approx": false, "clipped": false}]}],
  "markers": [{"date": "2026-09-14", "kind": "base_balance"}],
  "exposure": [{"date": "2026-08-07", "pct": 41.2, "open_n": 3, "approx": true}],
  "stats": {"bot_account": {"total_pct": "stat", "max_dd_pct": "stat", "sharpe": "stat",
                            "money_dd": "stat", "losing_streak": 3, "approx_share": null}},
  "vs": {"SPY": {"lead_pp": "stat",
                 "beta": {"value": 0.42, "se": 0.18, "n": 61, "reason": null},
                 "alpha": {"value": 6.1, "t": 0.9, "n": 61, "reason": null, "headline": true}}},
  "capture": {"index": "SPY", "up_pct": "stat", "down_pct": "stat", "ratio": "stat",
              "up_n": 33, "down_n": 28,
              "beat": {"up_days": 33, "up_beat": 14, "down_days": 28, "down_beat": 19}},
  "daily": [{"date": "2026-11-04", "lines": {"bot_account": -0.12, "bot_deployed": null,
                                             "SPY": 0.4}, "exposure_pct": 38.0,
             "open_n": 2, "beat": false, "span": 1, "missing": false}],
  "daily_has_more": true
}
```

`stats` has an entry per series key (index entries omit `money_dd`;
`approx_share` is set only on `bot_deployed`, the share of in-range sessions
built from approximated `open_notional`). `vs` has an entry per index.
`losing_streak` is set on both bot keys only. `daily_has_more` is added by
V208-11. `today` in state `pre` is the last completed session with
`final: true`.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-05-v208-benchmark-tab_1-equity-storage.md` | V208-1..V208-4 | migration + columns + tables, bar repos, equity seam + recorder, `open_notional` backfill |
| 2 | `2026-11-05-v208-benchmark-tab_2-bars-refresher-stats.md` | V208-5..V208-7 | proxy key + bar builders, refresher step, pure stats |
| 3 | `2026-11-05-v208-benchmark-tab_3-series-and-view.md` | V208-8..V208-10b | session alignment + gaps + breaks, deployed + exposure, response assembly |
| 4 | `2026-11-05-v208-benchmark-tab_4-api-and-spa-data.md` | V208-11..V208-14 | endpoint, dead-overlay removal, SPA client + store, chart extension |
| 5 | `2026-11-05-v208-benchmark-tab_5-tab-and-release.md` | V208-15..V208-18 | the tab in three slices, production rollout |

## Notes for part writers

- The brief (`.superpowers/briefs/2026-11-05-v208-benchmark-tab.md`) is the
  code context; its § 0 gaps are resolved by the spec amendment and the
  Global Constraints above.
- Production backfill command (V208-18): the script is dry-run by default, so
  the run is `docker compose exec -T bot python scripts/data/backfill_equity_samples.py --open-notional --apply`
  (the spec's command without `--apply` is the dry run). Rollback SQL, verbatim:
  `UPDATE equity_samples SET open_notional = NULL, open_notional_approx = NULL WHERE open_notional_approx IS TRUE`.
- V208-4 pricing: every row the script fills is priced from daily bars and
  marked `open_notional_approx = TRUE`; recorder rows carry `FALSE`, so the
  rollback never touches them.
- `benchmark_refresh` is the spec's "stored last full refresh date": a full
  refresh for a symbol runs when `full_refreshed_on(symbol)` is before the
  last completed NYSE session; it doubles as start-up catch-up.
- V208-6's DEPLOY_HETZNER edit is one bullet in `## The refresher service
  (v201)`; V208-18 adds the `### v208` runbook section. Check
  `tests/scripts/test_deploy_refresher_guard_shape.py` before both edits.
- The spec's "1 of 48 cells" is written `1 of 24 cells` (see Global
  Constraints); flagged to the controller.
