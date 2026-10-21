# v181 — Dashboard range chart: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V181-7:" -A 400 docs/superpowers/plans/2026-10-21-v181-dashboard-range-chart_1b-palette-chart-and-cards.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v181-dashboard-range-chart-design.md](../specs/2026-10-21-v181-dashboard-range-chart-design.md)
**Brief:** `.superpowers/briefs/2026-10-21-v181-dashboard-range-chart.md`
**Worktree:** implement V181-1..V181-16 in `.claude/worktrees/2026-10-21-v181-dashboard-range-chart` (branch of the same name, created in V181-1's first step; `docs/claude/document-lifecycle.md`). V181-17 runs the full suite in the worktree, merges to `main`, then `/panel` and `/close-out` run on `main`.

## Goal

The Dashboard's Trading performance panel holds a candlestick chart of the
paper account's equity. You can already zoom and drag it, but nothing reacts:
the API sends only the newest 120 candles, so a drag to the left hits a wall.
The readout describes one candle and never the window on screen. The eight KPI
cards follow only the Today / All days toggle. The timeframe stays fixed while
you zoom, so zoomed-out 1H candles turn into slivers. Most P&L figures are not
coloured either, so the panel doesn't read at a glance. The partner wants it to
work like TradingView: the window on screen *is* the question, and every
figure on the panel answers it.

Once shipped:

- Dragging left pages in older history.
- Zooming steps the timeframe up or down at 250 / 15 visible bars.
- With no candle hovered, the readout summarises the visible range: equity
  change, high/low, and max drawdown within the range.
- A preset row (1D · 5D · 1M · 3M · 6M · YTD · 1Y · All, plus a live Range
  chip; a native dropdown on phones) re-scopes the KPI cards and the Closed
  tab. The link works both ways: a preset moves the chart, and a hand zoom or
  pan switches the scope to Range.
- All P&L colour runs through `--pos` / `--neg`, which move to a more
  saturated palette. One frontend helper applies the rules:
  - the sign colours change and P&L figures;
  - win rate and payoff are judged as a pair against break-even, with a
    ±0.5 pp neutral band and no colour below 5 closes;
  - risk used is judged against its cap.
- KPI cards take a soft tint.
- The chart gets a dashed baseline at the window's opening equity, with a
  wash above and below it.

How it works:

- Backend: two additive query parameters.
  - `before` (+ `has_more`) on `/equity/candles` slices the full series the
    server already builds.
  - `mode=range&from=&to=` on `/dashboard` threads one `ClosedWindow` through
    every place `mode` is read today. The extraction pulls `dashboard()`
    below its complexity baseline of 21.
  - `/trades` gains `closed_from` / `closed_to` so the Closed tab agrees with
    the KPIs.
- Frontend: every decision sits in pure functions in the new
  `equity-range.model.ts`. The chart component only wires chart events to
  those functions, and uses a programmatic-move flag so a preset click or a
  timeframe step never flips the scope to Range.
- Range windows are whole New York buckets, the clock the candles use. 1D
  keeps today's Berlin-day `mode=today`.

Left alone:

- alerts, plans, stops and fills;
- database-level paging;
- point-in-time figures (balance, Open P&L, open trades, risk used), which
  stay "now" and get a "now" sub-label outside 1D;
- card order and weight (v85 D9);
- the unused `equity_30d` series.

Success means:

- every spec Testing bullet has a passing test;
- `dashboard()` measures below 21 and the baseline is shrunk;
- the token contrast and ΔE gates pass on the new palette with no exemption;
- a Playwright pass at 375 / 768 / 1280 px, light and dark, shows the preset
  row (dropdown under 640 px), the tints and the range readout without a
  horizontal page scroll;
- one full suite is green (`0 failed`, `0 xfailed`).

## Architecture

- **Backend (Flask, `swingbot/admin/api_v1/`):**
  - `equity.py` slices with a `before` cursor parsed by the new
    `equity_candles.parse_bucket_label` (the inverse of `bucket_label`).
  - The new `closed_window.py` owns the `[from, to)` window type, its 400
    validation and the in-window test. `dashboard.py` and `trades.py` both
    import it.
  - `dashboard()` gets `_parse_range_window` and `_scope_trades`.
- **Frontend (Angular signals, `@ngrx/signals`):**
  - `equity-range.model.ts` (pure) holds the range, paging, timeframe, tone,
    preset and scope functions.
  - `EquityCandlesStore` (root) owns the pages, `hasMore`, the page error and
    `atLiveEdge`.
  - `DashboardStore` (route-provided) owns the `ScopeSelection`, `stale`, the
    debounced range refetch and the chart target.
  - `sb-equity-candles` owns the chart handle and the programmatic-move flag.
  - The dashboard workspace component connects the two stores.
- **Palette:** new saturated primitives in `palette.css` feed `--pos` /
  `--neg` / `--pos-soft` / `--neg-soft`. The Discord charts follow:
  `chart_style.THEME` and `STYLE_VERSION` change, and
  `tests/charts/resolved_tokens.json` is regenerated.

**Tech stack:** Python 3.11, Flask, pytest; Angular (zoneless, signals), `@ngrx/signals`, vitest, lightweight-charts series primitives; Playwright for the visual check.

## Global Constraints

- `GET /equity/candles`: `DEFAULT_LIMIT = 120`, `MAX_LIMIT = 500` unchanged; the history page request is `limit=200`. `before` accepts exactly the `t` form the endpoint emits for that `tf` (ISO date for 1D/1W read as that New York bucket's start; ISO datetime with offset for 1H/4H); any other shape is a 400. Exclusive (`bucket start < cursor instant`), aware-instant comparison. `has_more` is computed on the full series before slicing; the slice is taken after `add_change`. Without `before`, behaviour is unchanged. Both bases.
- History paging triggers when the visible logical range comes within **20** candles of the oldest loaded candle and the last response said `has_more`; one page in flight at a time; a page from a superseded tf/basis is dropped; the viewport does not move on prepend.
- Auto timeframe: more than **250** visible bars → step up one (1H→4H→1D→1W); fewer than **15** → step down one; hold at the edge of history; `250 / ratio > 15` holds over every adjacent pair; the centre time is preserved; the step writes the timeframe preference like a manual pick; a timeframe change never changes the scope window.
- Readout range stats over **in-window candles** (every candle whose bucket intersects the visible logical range, a partly visible edge candle counting whole): equity change = first `o` → last `c` (% and money); High/Low = extremes of `h`/`l`; max drawdown within range = peak-to-trough of closes as % of the running peak, `null` ("—") when the peak ≤ 0. Labels: "Equity change", "High", "Low", "Max drawdown within range"; the KPI card is "Realised in range".
- Reuse `ACCOUNT_LABEL` from `equity-candles.model.ts` (its current text, unchanged) under the readout and on the KPI grid — never a second wording.
- Colour: `--pos` good, `--neg` bad, `--text-secondary` neutral/no data, `--warn` only for risk used 75–100% of cap. An em dash is never coloured. Breakeven pair: `--pos` when win rate > `100 / (1 + payoff)` + 0.5 pp, `--neg` when < it − 0.5 pp, neutral inside; neutral when either is null, payoff ≤ 0, or fewer than **5** closes. Risk used: neutral < 75 % of cap, warn 75–100 %, `--neg` at/over cap. Avg confidence and Open trades are neutral. The API sends no colour.
- Card tint: `--pos-soft` / `--neg-soft` behind a pos/neg figure; neutral and warn cards stay plain. Phone summary rows take the same tint.
- Palette: new primitives only in `frontend/src/styles/palette.css`; every pairing (light, dark, figure on its soft tint) passes `ui/contrast.spec.ts` and `ui/chart-palette.spec.ts` — a failing value is adjusted, never exempted. `chart_style.THEME["pos"/"neg"]`, `STYLE_VERSION` and `tests/charts/resolved_tokens.json` change in the same commit.
- Scope: presets **1D · 5D · 1M · 3M · 6M · YTD · 1Y · All** plus a **Range** chip showing the visible dates (`3 Sep – 18 Oct`). Phone (< 640 px): one native `<select>`, 44 px (`--control-h`). Tablet/desktop: chips, wrapping, never a horizontal page scroll. The preset persists in server-backed preferences (`dashboard.scope.preset`); an ad-hoc Range is never persisted.
- Request mapping: 1D → `mode=today` (Berlin day, unchanged); All → `mode=all`; 5D/1M/3M/6M/YTD/1Y/Range → `mode=range` with New York bucket-edge bounds. Preset `from` = the New York day start the preset reaches back to; preset `to` = the next New York midnight after `now` (the end of the current 1D bucket, a bucket edge for 1H/4H/1D), so KPIs move only when a new day opens and never with a timeframe change.
- `mode=range`: both bounds required, timezone-aware, `from ≤ to`, else 400 (`ApiError("invalid", …, 400)`). Closes count when `from ≤ closed_at < to` on aware instants, stored naive `closed_at` read as UTC. Open trades stay in scope exactly as in `mode=today`, so a Berlin-midnight-to-midnight window equals `mode=today`.
- `dashboard()` is legacy at complexity **21** (`scripts/dev/complexity_baseline.json`, key `swingbot.admin.api_v1.dashboard:dashboard`): it must not rise; record before and after; shrink the baseline with `python scripts/dev/complexity_gate.py --update`. Every new or changed function < 15.
- `test_dashboard_reads_the_trade_log_once` stays green: no second `TradeLog` read.
- Range refetch debounced **~300 ms** after the gesture settles; stale responses are dropped by a latest-request counter. A failed range refetch keeps the last KPIs, dimmed, with a stale hint.
- A failed history page keeps the loaded candles and shows "Couldn't load earlier history · Retry" at the left edge. A scan refresh never snaps the viewport to now; "↦ Latest" returns to the live edge.
- "now" sub-label on Open P&L, Open trades and Risk used whenever the scope is not 1D. No-close hint: "none closed in range" outside 1D/All, "none closed today" on 1D.
- Every UI change is checked at 375 / 768 / 1280 px, light and dark (`docs/claude/ui-design.md`).
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`; frontend: `cd frontend && npx ng test --include <spec> --watch=false`, the Angular unit-test builder). One full suite only, in V181-17.
- Before the first backend test run in the worktree (V181-1), run `/replicate-prod-db` (CLAUDE.md).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Several scoped commits, never one big one.

## Parallelisation

At most two implementers at once, and both in the one worktree, so only
tasks with disjoint files and no contract dependency run together.

- **V181-1 ∥ V181-2**: the backend endpoint and the pure range model are disjoint (`equity.py`/`equity_candles.py` vs `equity-range.model.ts`).
- **V181-5 ∥ V181-2..4**: the palette (`palette.css`, `tokens.spec.ts`, `chart_style.py`, `resolved_tokens.json`) shares no file with the model or the store.
- **V181-6 ∥ V181-3/4**: the new baseline primitive is a fresh file.
- **V181-10 ∥ V181-12**: backend `dashboard.py` and frontend `equity-range.model.ts`/`equity-chart-prefs.ts`/`models.ts`/`api-client.ts` are disjoint.

Sequential edges, each with its reason:

- V181-2 → V181-3 → V181-4 → V181-12: all append to `equity-range.model.ts` (shared file).
- V181-1 → V181-3: the store's paging consumes `before` and `has_more` (contract).
- V181-3 → V181-7: the chart consumes `EquityCandlesStore.loadOlder` / `hasMore` / `pageError` / `atLiveEdge` (contract).
- V181-6 → V181-7: the chart attaches `BaselinePrimitive` (contract).
- V181-7 → V181-8 → V181-15: all edit `equity-candles.ts` (shared file); V181-8 creates the programmatic-move flag that V181-15 consumes.
- V181-4, V181-5 → V181-9: the cards consume the tone helpers and the `--pos-soft`/`--neg-soft` values (contract + gate).
- V181-9 → V181-14: both edit `trading-performance.ts` / its spec (shared file).
- V181-10 → V181-11: `trades.py` imports `closed_window.py` (contract); the agreement test calls `/dashboard?mode=range`.
- V181-12 → V181-13 → V181-14 → V181-15: store consumes the model and the prefs key; the controls and link consume the store (contract); V181-14 and V181-15 both edit `dashboard.ts` (shared file).
- V181-11 → V181-14: the Closed tab sends `closed_from`/`closed_to` (contract).
- V181-15 → V181-16 → V181-17: the visual check needs every UI task; the full suite is last by rule.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1a | `2026-10-21-v181-dashboard-range-chart_1a-api-paging-and-range-model.md` | V181-1..V181-4 | `before`/`has_more`, pure range model, store paging, tone helpers |
| 1b | `2026-10-21-v181-dashboard-range-chart_1b-palette-chart-and-cards.md` | V181-5..V181-8 | palette ripple, baseline primitive, chart readout/paging/Latest, auto timeframe |
| 1c | `2026-10-21-v181-dashboard-range-chart_1c-kpi-card-tints.md` | V181-9 | card tints and caption (split from 1b for the 1500-line limit) |
| 2a | `2026-10-21-v181-dashboard-range-chart_2a-range-api-and-scope-store.md` | V181-10..V181-12 | `mode=range` + extraction, `/trades` closed window, presets model + prefs |
| 2c | `2026-10-21-v181-dashboard-range-chart_2c-dashboard-store-scope.md` | V181-13 | `DashboardStore` scope (split from 2a for the 1500-line limit; runs before 2b) |
| 2b | `2026-10-21-v181-dashboard-range-chart_2b-scope-controls-link-and-close-out.md` | V181-14..V181-17 | preset control + phone dropdown + "now" labels, two-way link, Playwright check, full suite / merge / panel / close-out |

Part 1 (1a + 1b + 1c) touches neither `dashboard.py` nor `trades.py` and is shippable alone (spec Decomposition).

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V181-1 | `/equity/candles` `before` cursor and `has_more` | 1a | sonnet | M `swingbot/core/tracking/equity_candles.py`, M `swingbot/admin/api_v1/equity.py`, M `tests/tracking/test_equity_candles.py`, M `tests/admin/test_api_v1_equity.py` | `equity_candles.parse_bucket_label(label: str, tf: str) -> datetime` (aware NY bucket start; `ValueError` on any other shape); equity.py `_before(tf: str) -> datetime \| None` (400 via `ApiError("invalid", …, 400)`); response key `has_more: bool`; query `?before=<t>` |
| V181-2 | Pure range model: in-window candles, bounds, stats, next timeframe | 1a | sonnet | C `frontend/src/app/workspaces/dashboard/panels/equity-range.model.ts`, C `.../panels/equity-range.model.spec.ts` | `interface LogicalWindow {from: number; to: number}`; `interface TimeWindow {from: string; to: string}` (ISO UTC, `[from,to)`); `interface RangeStats {change: number; changePct: number \| null; high: number; low: number; maxDrawdownPct: number \| null}`; `inWindowCandles(range: LogicalWindow \| null, candles: readonly EquityCandle[]): EquityCandle[]`; `nyMidnight(isoDate: string): Date`; `bucketStartInstant(t: string, tf: EquityTimeframe): Date`; `bucketEndInstant(t: string, tf: EquityTimeframe): Date` (next bucket start on the NY wall clock); `windowBounds(candles: readonly EquityCandle[], tf: EquityTimeframe): TimeWindow \| null`; `rangeStats(candles: readonly EquityCandle[]): RangeStats \| null`; `TF_STEP_UP_BARS = 250`, `TF_STEP_DOWN_BARS = 15`, `TF_RATIO: Record<EquityTimeframe, number>`; `nextTimeframe(barCount: number, tf: EquityTimeframe, atHistoryEdge: boolean): EquityTimeframe` |
| V181-3 | History paging: client `before`, page merge, store pages | 1a | sonnet | M `frontend/src/app/api/models.ts` (`EquityCandlesResponse.has_more: boolean`), M `frontend/src/app/api/api-client.ts` + `api-client.spec.ts`, M `equity-range.model.ts` + spec, M `frontend/src/app/stores/equity-candles.store.ts` + `.spec.ts`, M `frontend/src/app/testing/equity-candles-store.stub.ts`, M `dashboard.spec.ts`, `panels/equity-candles.spec.ts`, `panels/portfolio-value.spec.ts` (`has_more: false` on their response literals) | `ApiClient.equityCandles(tf, basis, limit?: number, before?: string)`; `HISTORY_PAGE_LIMIT = 200`, `PAGE_TRIGGER_CANDLES = 20` (model); `prependPage(loaded: readonly EquityCandle[], page: readonly EquityCandle[]): EquityCandle[]`; `mergeLatest(loaded: readonly EquityCandle[], latest: readonly EquityCandle[]): EquityCandle[]`; `shouldLoadOlder(range: LogicalWindow \| null, hasMore: boolean, busy: boolean): boolean`; store state `hasMore: boolean`, `pageLoading: boolean`, `pageError: boolean`, `atLiveEdge: boolean`; store methods `loadOlder(): void`, `setAtLiveEdge(atEdge: boolean): void`; stub gains the same members |
| V181-4 | Profit/loss tone helpers | 1a | haiku | M `equity-range.model.ts` + spec | `type PnlTone = 'pos' \| 'neg' \| 'warn' \| 'neutral'`; `BREAKEVEN_BAND_PP = 0.5`; `MIN_CLOSES_FOR_TONE = 5`; `RISK_WARN_FRACTION = 0.75`; `signTone(value: number \| null): PnlTone`; `drawdownTone(pct: number \| null): PnlTone`; `breakevenPairTone(winRatePct: number \| null, payoff: number \| null, closes: number \| null): PnlTone`; `riskTone(usedPct: number \| null, capPct: number \| null): PnlTone` |
| V181-5 | Saturated candle palette and its ripple | 1b | sonnet | M `frontend/src/styles/palette.css`, M `frontend/src/styles/tokens.css` (only if a tier-2 alias moves), M `frontend/src/app/ui/tokens.spec.ts`, M `swingbot/core/charts/chart_style.py` (`THEME["pos"]`, `THEME["neg"]`, `STYLE_VERSION = "v181"`), M `tests/charts/resolved_tokens.json` (regenerated by `python scripts/dev/dump_tokens.py`), M `tests/charts/test_chart_theme.py` (digest pin) | final hex/rgba values of `--pos`, `--neg`, `--pos-soft`, `--neg-soft` (light and dark) — consumed only via the tokens |
| V181-6 | Baseline-and-wash series primitive | 1b | sonnet | C `frontend/src/app/ui/chart/primitives/baseline-primitive.ts`, C `.../primitives/baseline-primitive.spec.ts` | `interface BaselineSpec {value: number; line: string; above: string; below: string}`; `class BaselinePrimitive implements ISeriesPrimitive<Time>` with `setBaseline(spec: BaselineSpec \| null): void`, pane view `zOrder()` = `'bottom'` |
| V181-7 | Chart: range readout, caption, paging trigger, page-error note, baseline, "↦ Latest" | 1b | sonnet | M `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts` + `equity-candles.spec.ts`, M `equity-candles.model.ts` + spec (`rangeReadoutParts`) | `rangeReadoutParts(stats: RangeStats \| null, currency: string): ReadoutPart[]` (model; parts carry a `tone: PnlTone`); component `inWindow` computed over `visible`; `BaselinePrimitive` attached; Latest button calls `timeScale().scrollToRealTime()` |
| V181-8 | Auto timeframe on zoom with the programmatic-move flag | 1b | sonnet | M `equity-candles.ts` + spec | component private `programmatic: boolean` and `moveProgrammatically(fn: () => void): void`; on tf change it restores the preserved centre via `setVisibleRange` under the flag |
| V181-9 | KPI card tones, tints and the account caption | 1c | sonnet | M `frontend/src/app/ui/metric-card.ts`, C `frontend/src/app/ui/metric-card.spec.ts`, M `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts` + spec, M `portfolio-value.ts` + spec (change colour via `signTone`) | `MetricCard` input `tint = input<PnlTone \| null>(null)` (pos/neg tint the card and colour the value; warn colours only; neutral plain; a dash never coloured); trading-performance computed tones `winPairTone`, `payoffTone` (same pair), `riskTone`, `openPnlTone`, `realizedTone`, `expectancyTone` |
| V181-10 | `/dashboard?mode=range`: one window through every consumer | 2a | opus | C `swingbot/admin/api_v1/closed_window.py`, M `swingbot/admin/api_v1/dashboard.py`, M `tests/admin/test_api_v1_dashboard.py`, C `tests/admin/test_closed_window.py`, M `scripts/dev/complexity_baseline.json` | `class ClosedWindow(NamedTuple): start: datetime; end: datetime`; `parse_closed_window(from_raw: str \| None, to_raw: str \| None, *, names: tuple[str, str] = ("from", "to")) -> ClosedWindow`; `closed_in_window(iso_ts: str \| None, window: ClosedWindow) -> bool`; dashboard.py `_SCOPES = ("active", "today", "all", "range")`, `_parse_range_window(mode: str) -> ClosedWindow \| None`, `_scope_trades(all_raw: list[dict], mode: str, window: ClosedWindow \| None) -> list[dict]`, `_realized_parts(trades: list[dict], mode: str, window: ClosedWindow \| None = None)`, `_lifecycle_counts(mode: str, all_trades: list[dict], window: ClosedWindow \| None = None)`; response `scope: {"mode", "from", "to"}` (`from`/`to` ISO UTC or null) |
| V181-11 | `/trades?closed_from=&closed_to=` for the Closed tab | 2a | sonnet | M `swingbot/admin/api_v1/trades.py`, M `tests/admin/test_api_v1_trades.py` | query params `closed_from`/`closed_to` (both or neither; same 400s); trades.py `_in_closed_scope(status: str, closed_at: str \| None, window: ClosedWindow) -> bool` (non-terminal or `closed_in_window`) |
| V181-12 | Presets, scope request mapping, the preset preference, client params | 2a | sonnet | M `equity-range.model.ts` + spec, M `frontend/src/app/ui/equity-chart-prefs.ts` + spec, M `models.ts`, M `api-client.ts` + spec | `type ScopePreset = '1D' \| '5D' \| '1M' \| '3M' \| '6M' \| 'YTD' \| '1Y' \| 'All'`; `SCOPE_PRESETS: readonly ScopePreset[]`; `type ScopeSelection = {kind: 'preset'; preset: ScopePreset} \| {kind: 'range'; window: TimeWindow}`; `interface ChartTarget {window: TimeWindow \| null; seq: number}` (null window = all history); `presetBounds(preset: Exclude<ScopePreset, '1D' \| 'All'>, now: Date): TimeWindow`; `chartWindowFor(preset: ScopePreset, now: Date): TimeWindow \| null`; `scopeToRequest(scope: ScopeSelection, now: Date): {mode: DashboardScope; window: TimeWindow \| null}`; `rangeChipLabel(window: TimeWindow): string` (`3 Sep – 18 Oct`); `showsNowLabel(scope: ScopeSelection): boolean`; prefs `SCOPE_PRESET_KEY = 'dashboard.scope.preset'`, `readScopePreset(prefs: Preferences): ScopePreset` (default `'1D'`), `writeScopePreset(prefs, preset: ScopePreset): void`; models `DashboardScope` gains `'range'`, `Dashboard.scope` gains `from?: string \| null; to?: string \| null`, `TradeQuery` gains `closedFrom?: string \| null; closedTo?: string \| null`; `ApiClient.dashboard(mode?: DashboardScope, window?: TimeWindow \| null)`; `trades()` maps `closedFrom`/`closedTo` → `closed_from`/`closed_to` |
| V181-13 | `DashboardStore` scope selection, range refetch, stale | 2c | sonnet | M `frontend/src/app/stores/dashboard.store.ts` + `dashboard.store.spec.ts` | state `selection: ScopeSelection`, `stale: boolean`, `targetSeq: number`; computed `scope: DashboardScope`, `preset: ScopePreset \| null`, `closedWindow: TimeWindow \| null`, `chartTarget: ChartTarget`; methods `setPreset(preset: ScopePreset): void` (writes the preference, bumps `targetSeq`), `setRange(window: TimeWindow): void` (debounced 300 ms, no preference write, no `targetSeq` bump), `setScope(scope: DashboardScope): void` kept (`today` → 1D, `all` → All) |
| V181-14 | Preset control, phone dropdown, "now" labels, stale dimming, Closed tab window | 2b | sonnet | M `trading-performance.ts` + spec, M `frontend/src/app/workspaces/dashboard/dashboard.ts` + `dashboard.spec.ts`, M `frontend/src/app/workspaces/dashboard/positions-table.ts` + spec | trading-performance inputs `selection = input<ScopeSelection>(…1D)`, `stale = input<boolean>(false)`, output `presetChange = output<ScopePreset>()` (replace `scope`/`scopeChange`); positions-table input `closedWindow = input<TimeWindow \| null>(null)` |
| V181-15 | Two-way link: preset moves the chart, a hand pan sets Range | 2b | sonnet | M `equity-candles.ts` + spec, M `portfolio-value.ts`, M `trading-performance.ts` (pass-through), M `dashboard.ts` + spec | `EquityCandles` input `target = input<ChartTarget \| null>(null)`, output `rangeChange = output<TimeWindow>()` (user gestures only); same pass-through input/output on `sb-portfolio-value` and `sb-trading-performance` (`chartTarget`, `chartRangeChange`) |
| V181-16 | Playwright check at 375 / 768 / 1280, light and dark | 2b | sonnet | none committed (the Playwright script lives in the session scratchpad) | screenshots only |
| V181-17 | Full suite, merge, panel, close-out | 2b | sonnet | none (merge commit; `/close-out` moves the plan) | — |
