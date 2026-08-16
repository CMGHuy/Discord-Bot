/* The /api/v1 contract, in TypeScript.
 *
 * Spec `2026-08-08-v11-admin-rest-api-design.md` Decision 6: **there is no
 * OpenAPI document and no code generation.** These interfaces are written by
 * hand, and what keeps them honest is `tests/admin/api_v1_contract.py` plus
 * the per-endpoint contract tests -- those assert types rather than mere key
 * presence, and fail on an undeclared key as loudly as on a missing one. So
 * a field renamed, retyped or added on the Python side breaks a Python test,
 * and that test is the reminder to come and edit this file.
 *
 * That means one rule when editing here: **mirror the contract test, not the
 * endpoint's current output.** The two agree today; when they disagree, the
 * test is the contract and the endpoint has a bug.
 *
 * `number | null` appears everywhere because most of this data is derived
 * from trades that may not have closed, priced, or been sized yet. It is
 * NULLABLE_NUMBER in the Python contract, and collapsing it to `number` here
 * would push a runtime `null` into arithmetic that TypeScript said was safe.
 */

/* -- envelopes ---------------------------------------------------------- */

/** The one collection envelope. `total` is the count after filtering but
 *  BEFORE slicing -- it is the pager's denominator, not `items.length`. */
export interface Collection<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

/** The one error body. `code` is stable and may be branched on; `message` is
 *  for humans and may change freely. */
/* -- session ------------------------------------------------------------ */

export interface Identity {
  authenticated: boolean;
  username: string | null;
}

export interface Health {
  ok: boolean;
  versions: Versions;
  /** SR58 — whether the US market is open right now.
   *
   *  On `/health` rather than `/dashboard` because "are these prices live"
   *  is a global fact: the indicator sits beside the connection status in
   *  the shell, which must not depend on a workspace being open. */
  market_active: boolean;
  /** The account's currency symbol — `CURRENCY_SYMBOL`, which defaults to
   *  `€`. Here for the same reason `market_active` is: it applies to every
   *  account-level figure the SPA renders, so a workspace endpoint would be
   *  the wrong owner. NOT per-ticker — `ChartResponse.currency` is that, and
   *  it can legitimately differ per instrument. */
  currency: string;
}

export interface Versions {
  ui: string;
  bot: string;
  last_updated: string | null;
}

/* -- trades ------------------------------------------------------------- */

/** A row in the trades list. The union of plan-backed and legacy positions:
 *  `origin` says which, and every field either side lacks is null. */
export interface TradeRow {
  id: string;
  origin: string;
  status: string;
  ticker: string;
  direction: string;
  strategy: string | null;
  horizon: string | null;
  tier: string | null;
  badge: string | null;
  confidence_level: number | null;
  confidence_score: number | null;
  quality_score: number | null;
  entry: number | null;
  stop_loss: number | null;
  target: number | null;
  target2: number | null;
  risk_reward: number | null;
  shares: number | null;
  position_value: number | null;
  current_price: number | null;
  exit_price: number | null;
  realized_pnl_amount: number | null;
  pnl_pct: number | null;
  r_multiple: number | null;
  held_hours: number | null;
  opened_at: string | null;
  closed_at: string | null;
  has_note: boolean;
  /* SR53 — the plan's own numbers, so a row that has not filled is not mostly
     nulls. `opened_at` and `held_hours` describe an execution; these describe
     the plan. Null on a legacy row, which never had a plan. */
  created_at: string | null;
  trigger_price: number | null;
  follow_score: number | null;
  /* SR7 — the status bar, computed server-side so the cell draws rather than
     calculates, and so the arithmetic lives next to the bot's own near-close
     alerts instead of being reimplemented here. `progress_band` names which
     pair of tokens to interpolate between; no colour crosses the wire. */
  progress_pct: number | null;
  entry_pct: number | null;
  progress_band: 'toward_stop' | 'neutral' | 'toward_target' | null;
  blink_seconds: number | null;
  status_label: string;
}

/** The heavy half of a trade, fetched only for the detail view.
 *
 *  One shape for both origins on purpose: the server fills the plan-only
 *  fields with null for legacy records rather than returning two shapes, so
 *  the Plan tab is one component instead of a component and a branch. */
export interface TradeDetailFields {
  /** The underlying trade record's id. The plan id is the public identity,
   *  but close/cancel/delete act on this one. Null when no trade was ever
   *  opened for the plan. */
  trade_id: string | null;
  /** The journal note's TEXT, for the Notes tab to render and edit.
   *
   *  The row's `has_note` only answers whether one exists. Without this the
   *  tab could write through `PUT /trades/{id}/note` and never read back what
   *  it wrote. Null both when there is no note and when the position has no
   *  journal entry at all -- entries are written at close, so an open trade
   *  usually has none, and the tab renders that as a state rather than an
   *  error. */
  note: string | null;
  created_at: string | null;
  plan_source: string | null;
  entry_type: string | null;
  trigger_price: number | null;
  expiry_bars: number | null;
  tp1_fraction: number | null;
  breakeven_trigger_fraction: number | null;
  trail_atr_mult: number | null;
  working_stop: number | null;
  runner_high_close: number | null;
  stop_mult_applied: number | null;
  quality_breakdown: unknown[];
  badge_stats: Record<string, unknown>;
  status_history: unknown[];
  legs_realized: unknown[];
  legs: unknown[];
  confidence_breakdown: unknown;
  explanation: string | null;
  confirmed_by: string[];
  target_sources: string[];
  stop_sources: string[];
  target2_sources: string[];
  sizing_mode: string | null;
  account_balance_after: number | null;
}

/** `GET /trades/:id` -- a list row plus the heavy fields. */
export interface TradeDetail extends TradeRow {
  detail: TradeDetailFields;
}

export interface TradeNote {
  id: string;
  note: string;
}

/** Filters the list endpoint accepts. A parameter it does not know is a 400,
 *  not a silent no-op -- a silently ignored filter is how a filter that has
 *  stopped working survives to production. */
/** `POST /trades/clear-open` and `POST /trades/clear-history`. The count is
 *  the only thing either returns, and it is what the confirmation reports —
 *  "cleared" without a number cannot be told from "there was nothing to
 *  clear". */
export interface ClearResult {
  removed: number;
}

export interface TradeQuery {
  page?: number;
  per_page?: number;
  /** `field` or `-field` for descending. Closed set -- see SORTABLE. */
  sort?: string;
  status?: string;
  /** How it ended: win | loss | open | closed. `status` normalises win and
   *  loss to CLOSED, so this is the only way to separate them. */
  outcome?: string;
  ticker?: string;
  strategy?: string;
  horizon?: string;
  direction?: string;
  tier?: string;
  origin?: string;
  has_note?: boolean;
  /** SR52. VALIDATED or WEAK, compared case-insensitively server-side. */
  badge?: string;
  /** SR52. The 1-5 level. Named `confidence` in the URL and stored as
   *  `confidence_level` on the row; `_FILTER_KEYS` bridges the two. */
  confidence?: string;
}

export const TRADE_SORTABLE = [
  'opened_at', 'closed_at', 'ticker', 'status', 'pnl_pct', 'r_multiple',
  'entry', 'exit_price', 'held_hours', 'realized_pnl_amount',
  // SR53. A ranking is a column nobody wants unsorted, and `created_at` is the
  // only time an unfilled plan has to sort by.
  'created_at', 'follow_score',
] as const;

/* -- dashboard ------------------------------------------------------------ */

export interface EquitySeries {
  points: unknown[];
  change_pct: number | null;
}

export interface Dashboard {
  account_balance: number | null;
  open_pnl_pct: number | null;
  risk_used_pct: number | null;
  risk_cap_pct: number | null;
  open_trades: number;
  avg_confidence: number | null;
  win_rate: number | null;
  expectancy_r: number | null;
  equity_30d: EquitySeries;
  position_premium: Record<string, unknown>;
  /** SR53 — the five plan-lifecycle counts, keyed by status. Loosely typed
   *  like `position_premium`: the statuses come from `PlanStatus` on the Python
   *  side, and an empty object is what a failed collector returns. */
  lifecycle: Record<string, unknown>;
  /** SR58 — the date scope the server actually applied, echoed back. */
  scope: { mode: DashboardScope };
  /** SR58 — realised P&L over the scoped closes. Amounts are null, never 0,
   *  when nothing closed: "nothing closed today" and "closed exactly flat"
   *  are different facts. */
  realized: {
    amount: number | null;
    pct: number | null;
    n: number;
    wins: number;
    losses: number;
  };
}

/** The Jinja dashboard's three date scopes. `active` is today plus anything
 *  still open; `today` is today alone; `all` is every day. */
export type DashboardScope = 'active' | 'today' | 'all';

/* -- analytics ---------------------------------------------------------- */

/**
 * `GET /analytics/snapshot` — the pre-built analytics blob, forwarded verbatim
 * (`api_v1/analytics.py:44-48`).
 *
 * **This name used to describe something else entirely.** Until SR50 it held
 * the six relocated Dashboard metrics — `wins`, `losses`, `avg_realized_pct`
 * and so on — which are the `relocated` block of `/analytics/performance`, not
 * this endpoint's response at all. `analyticsSnapshot()` declared that type
 * and would have mis-shaped every field it returned; the mistype never bit
 * because no store ever called the method. That is the same fact the parity
 * audit recorded from the other side.
 *
 * Loosely typed on purpose, for the reason the Dashboard's two loose fields
 * give: `swingbot/core/analytics` owns these shapes, and pinning an interface
 * to them would make every backend tweak a compile error in the client. The
 * narrowing happens once, in `AnalyticsStore`.
 *
 * `by` is keyed by the ten dimensions in `aggregate.py:DIMENSIONS` — strategy,
 * horizon, tier, badge, confidence, direction, dow, month, ticker, source —
 * each holding one `StatRow` per group.
 */
export interface AnalyticsSnapshot {
  built_at: string | null;
  overall: Record<string, unknown>;
  equity_curve: { points?: unknown[]; skipped_n?: number } | null;
  drawdown: unknown[];
  rolling_wr: unknown[];
  by: Record<string, unknown[]>;
  calibration: Record<string, unknown>;
  r_multiples: unknown[];
}

/** A histogram bucket. Empty interior buckets are present with `count: 0` —
 *  dropping them would let the chart silently redraw its own x-axis. */
export interface HistogramBucket {
  lo: number;
  hi: number;
  count: number;
}

/** One holding-period band. `win_rate` is null (never 0) for an empty band. */
export interface HoldingBucket {
  bucket: string;
  n: number;
  win_rate: number | null;
  avg_return_pct: number | null;
}

/**
 * SR54 — every figure `stats.html` used to derive in browser JS.
 *
 * All of it is `number | null`, and null means "not enough data", never zero.
 * The workspace must render null as an em dash rather than coercing: a fresh
 * account showing "Calmar 0.00" reads as a measured result, not an empty one.
 *
 * `win_rate` and `expectancy_r` appear BOTH here and at the top level of
 * `AnalyticsPerformance`. That is deliberate, not duplication: the top-level
 * pair is the account's all-time record, and this pair is scoped by the
 * selected date range.
 */
export interface AnalyticsDerived {
  avg_win_pct: number | null;
  avg_loss_pct: number | null;
  total_return_pct: number | null;
  annualised_return_pct: number | null;
  calmar: number | null;
  volatility_ann_pct: number | null;
  trades_per_month: number | null;
  pct_in_market: number | null;
  sharpe_ann: number | null;
  sortino_ann: number | null;
  win_rate: number | null;
  expectancy_r: number | null;
}

export interface AnalyticsPerformance {
  totals: Record<string, unknown>;
  relocated: Record<string, unknown>;
  /** All-time, NOT scoped by the range — see `AnalyticsDerived`. */
  win_rate: number | null;
  /** All-time, NOT scoped by the range — see `AnalyticsDerived`. */
  expectancy_r: number | null;
  by_confidence: Record<string, unknown>;
  range: {
    from: string | null;
    to: string | null;
    span_years: number | null;
    n: number;
  };
  derived: AnalyticsDerived;
  distributions: { returns: HistogramBucket[]; r_multiples: HistogramBucket[] };
  rolling_returns: { date: string; return_pct: number }[];
  holding_period_split: HoldingBucket[];
  calendar: { month: string; return_pct: number; n: number }[];
  cumulative_by_strategy: Record<string, { date: string; cum_pct: number }[]>;
  benchmark: { spy_cum: Record<string, number> };
}

/**
 * SR55 — one position's journal entry.
 *
 * Every excursion figure is nullable because `build_entry` degrades to null
 * when the ticker's bars were unavailable at close, rather than raising. A
 * missing MFE means "we could not measure it", never "it did not move".
 */
export interface JournalEntry {
  trade_id: string;
  ticker: string;
  strategy: string;
  horizon_key: string;
  direction: string;
  tier: string | null;
  badge: string | null;
  quality_score: number | null;
  outcome: string;
  r_realized: number | null;
  /** Maximum favourable excursion, in R. */
  mfe_r: number | null;
  /** Maximum adverse excursion, in R. */
  mae_r: number | null;
  /** Share of the favourable move actually captured, 0–1. */
  exit_efficiency: number | null;
  holding_days: number | null;
  tags: string[];
  auto_lesson: string | null;
  note: string;
  opened_at: string | null;
  closed_at: string | null;
  created_at: string | null;
}

/**
 * `GET /trades/:id/journal`.
 *
 * `journaled: false` is a 200, not a 404 — entries are written at close, so
 * an open position having none is the normal case and must be readable as a
 * state rather than caught as an error.
 */
export interface TradeJournal {
  journaled: boolean;
  entry: JournalEntry | null;
}

/** `GET /analytics/journal` — the trailing-week digest and recurring lessons. */
export interface AnalyticsJournal {
  digest: string[];
  lessons: string[];
  /** Entries behind both lists, so a digest from three is not read like one
   *  drawn from three hundred. */
  entries_n: number;
}

export interface AnalyticsStrategies {
  strategies: unknown[];
  heatmap: Record<string, unknown>;
}

export interface AnalyticsCalibration {
  deciles: unknown[];
  tiers: unknown[];
  drift: unknown[];
}

export interface AnalyticsPlans {
  funnel: { posted: number; filled: number; hit_tp1: number; closed: number };
  in_flight: number;
  fill_rate: {
    resolved_n: number;
    fill_rate_pct: number | null;
    median_days_to_fill: number | null;
  };
  badges: Record<string, number>;
  tiers: Record<string, number>;
}

/** `GET /analytics/registry`.
 *
 *  It really is this one key. The `{strategies, horizons, cells}` shape this
 *  interface used to declare belongs to the HEATMAP nested inside
 *  `/analytics/strategies` -- pinned by `test_strategies_ships_series_not_svg`
 *  -- and describing the registry with it meant the first caller would have
 *  read three keys the endpoint has never sent. Same failure as the `ohlcv`
 *  envelope: it type-checks and returns `undefined`. */
export interface AnalyticsRegistry {
  registry: unknown[];
}

/* -- jobs and tuning ---------------------------------------------------- */

export interface JobList {
  jobs: unknown[];
}

export interface Job {
  id: string;
  state: string;
  log_tail: string;
}

/** What `POST /jobs/tune` answers: the new job's id and nothing else.
 *
 *  NOT a `Job` -- the handler returns `{"job_id": ...}` and never the job
 *  itself, so a caller that read `.state` off this got `undefined`. Fetch the
 *  job with `job(id)`, or wait for the `jobs` event. */
export interface JobStarted {
  job_id: string;
}

/** `GET /jobs/:id/result` — a finished tuning job's grid.
 *
 *  `strategy` is null and `grid` empty while the job is still running: the
 *  endpoint answers 200 with the same three keys either way, so nothing here
 *  has to branch on which shape arrived (SR51). */
export interface JobResult {
  job_id: string;
  strategy: string | null;
  grid: unknown[];
}

export interface ProposalList {
  proposals: unknown[];
}

export interface Proposal {
  filename: string;
  proposal: Record<string, unknown>;
}

/* -- watchlist ----------------------------------------------------------- */

export interface Ticker {
  symbol: string;
  company_name: string | null;
  open_trades: number;
  closed_trades: number;
  /** ISO date (`YYYY-MM-DD`), or null when Yahoo has no calendar data for
   *  this symbol (or it's an ETF, which never reports earnings). */
  next_earnings_date: string | null;
  /** Full ISO-8601 UTC timestamp for the same event, or null under the same
   *  conditions as next_earnings_date -- always UTC regardless of the
   *  reporting company's own exchange timezone, so the client can render
   *  any local time (e.g. Europe/Berlin) from one consistent source. Never
   *  confirmed by the company for a future date; treat as an estimate. */
  next_earnings_datetime: string | null;
}

/** `GET /watchlist/tickers`. A plain list, NOT a `Collection` — the watchlist
 *  is not paginated and the endpoint ships no envelope. This was typed
 *  `Collection<Ticker>`, which compiled and would have handed the store
 *  `undefined` at runtime; `tests/admin/test_api_v1_watchlist.py` asserts
 *  `body["tickers"]`, the same trap `OhlcvResponse` records. */
export interface TickerList {
  tickers: Ticker[];
}

/** `POST /watchlist/tickers`. One endpoint for single and bulk add, which is
 *  why the result is per-symbol: pasting thirty symbols with one typo adds
 *  twenty-nine and names the one, rather than failing the batch. */
export interface TickerAddResult {
  added: string[];
  already_present: string[];
  invalid: string[];
  /** The watchlist size after the add. */
  total: number;
}

export interface TickerRemoveResult {
  removed: string;
  total: number;
}

/** One `GET /watchlist/suggest` hit. `name` here, not `company_name` — it
 *  comes from the ticker directory rather than from the watchlist row. */
export interface TickerSuggestion {
  symbol: string;
  name: string;
}

export interface TickerSuggestions {
  results: TickerSuggestion[];
}

/* -- risk --------------------------------------------------------------- */

export interface RiskHeat {
  open_pct: number | null;
  cap_pct: number | null;
  utilisation_pct: number | null;
}

export interface RiskPosition {
  trade_id: string;
  ticker: string;
  strategy: string | null;
  shares: number | null;
  entry: number | null;
  stop_loss: number | null;
  risk_pct: number | null;
}

export interface SectorHeat {
  sector: string;
  heat_pct: number | null;
}

export interface Throttle {
  multiplier: number | null;
  paused: boolean;
}

export interface Killswitch {
  on: boolean;
  reason: string | null;
  at: string | null;
}

export interface ScanHealth {
  durations_s: number[];
  latest_s: number | null;
  slowdown: boolean;
}

/** `POST /risk/killswitch`'s body. The toggle deliberately does NOT return
 *  the whole risk resource — see `ApiClient.setKillswitch`. */
export interface KillswitchResult {
  killswitch: Killswitch;
}

export interface Risk {
  heat: RiskHeat;
  positions: RiskPosition[];
  sector_heat: SectorHeat[];
  clusters: unknown[];
  throttle: Throttle;
  killswitch: Killswitch;
  scan_health: ScanHealth;
}

/* -- system ------------------------------------------------------------- */

export interface SettingField {
  key: string;
  label: string;
  type: string;
  /** Typed `object` in the Python contract: the value's type follows the
   *  field's `type`, so it is genuinely heterogeneous. */
  value: unknown;
  default: string;
  help: string;
  min: number | null;
  max: number | null;
  step: number | null;
  options: unknown[];
  sensitive: boolean;
  hot_reloadable: boolean;
}

export interface SettingSection {
  name: string;
  icon: string;
  description: string;
  fields: SettingField[];
}

export interface Settings {
  sections: SettingSection[];
  audit: unknown[];
  restart_available: boolean;
}

/** One changed setting, as both the preview and the save report it — the
 *  server builds them from the same `settings_diff`, so what was approved
 *  and what was written cannot disagree. `old`/`new` are already `•••` on
 *  both sides for a sensitive field. */
export interface SettingsDiffRow {
  key: string;
  label: string;
  old: string;
  new: string;
  sensitive: boolean;
}

export interface SettingsPreview {
  diff: SettingsDiffRow[];
  /** LABELS, not keys, of changed fields the bot cannot pick up on SIGHUP.
   *  Empty is the normal case. */
  restart_required: string[];
}

export interface SettingsSaveResult extends SettingsPreview {
  /** The write succeeded even when this did not: `ok: false` means only
   *  that the signal telling the bot to re-read `.env` failed, which is
   *  routine outside Docker. */
  hot_reload: { ok: boolean; message: string };
}

/** `applied` is a COUNT of recognised keys. Import is lenient where PUT is
 *  strict — the body is a pasted file, possibly from an older build. */
export interface SettingsImportResult {
  applied: number;
  unknown_keys: string[];
}

export interface Logs {
  source: string;
  lines: number;
  path: string;
  content: string;
}

export interface LogClearResult {
  source: string;
  /** False with a reason when there was no file to clear. Not a failure:
   *  there was nothing to delete and nothing went wrong. */
  ok: boolean;
  message: string;
}

export interface BotRestartResult {
  ok: boolean;
  message: string;
}

export interface ScanStatus {
  pending: boolean;
  triggered_at: string | null;
  paused: boolean;
  paused_at: string | null;
  running: boolean;
  bot_alive: boolean;
  bot_last_seen: string | null;
  /** Null when the bot has never reported -- distinct from false. */
  bot_session_active: boolean | null;
  bot_scan_paused: boolean | null;
}

export interface ScanCommandResult {
  ok: boolean;
  message: string;
  scan: ScanStatus;
}

/* -- market: the interactive chart (SR33, v25) -------------------------- */

/** A bar in `GET /market/chart/:ticker`.
 *
 *  Note `t` -- an int Unix epoch in SECONDS, not a `YYYY-MM-DD` string. One
 *  time type across this whole payload: the overlay
 *  shapes below carry epochs too, and lightweight-charts converts both
 *  through the same `timeToCoordinate`. Mixing the two representations in
 *  one chart is how an overlay lands a year away from its candle, which
 *  renders perfectly happily and is wrong. */
export interface ChartBar {
  /** Unix epoch, SECONDS. */
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

/** A point on an overlay shape: `[epochSeconds, price]`.
 *
 *  The price is nullable because a rolling window's warm-up bars have no
 *  value (a Donchian channel shifts a 20-bar window). The server carries
 *  those as `null` rather than NaN -- `JSON.parse` rejects a bare `NaN`
 *  token outright, which would fail the entire chart load. */
export type ChartPoint = [number, number | null];

/** An indicator line, computed over the full loaded frame and then sliced to
 *  the visible window -- so its last value does not move when the window
 *  changes. `null` is a warm-up bar with no value, not zero. */
export type ChartSeries = (number | null)[];

/** The indicator panes. **Every key is optional**: an indicator the frame is
 *  too short for is omitted from the object entirely rather than sent as a
 *  list of nulls, and the client omits the pane in turn (spec Decision 10's
 *  third degraded state). An empty pane with an axis and no line would read
 *  as "this indicator is flat" instead of "there is not enough history". */
export interface ChartIndicators {
  macd?: {
    line: ChartSeries;
    signal: ChartSeries;
    /** MACD minus signal. */
    hist: ChartSeries;
  };
  rsi?: ChartSeries;
  /** Keltner envelope. The middle band is the 20-EMA the price pane can
   *  already draw as an overlay, so only the envelope is carried. */
  kc?: {
    upper: ChartSeries;
    lower: ChartSeries;
  };
}

/** One bin of the horizontal volume histogram. `price` is the bin's CENTRE,
 *  not an edge. Empty when there is not enough history -- unlike an
 *  indicator this is an overlay on the price pane, so there is no pane to
 *  omit. */
export interface VolumeProfileBin {
  price: number;
  volume: number;
}

/** The plan lines. Decision 10's names, NOT `TradeLevels`' `tp1`/`tp2`:
 *  these feed price lines whose axis tags read "target 1", and
 *  `working_stop` (the live breakeven/trail floor) has no equivalent there
 *  at all. A missing level is `null` and must stay undrawn -- rendering it
 *  at 0 rescales the whole price axis and reads as a real level. */
export interface ChartLevels {
  entry: number | null;
  stop: number | null;
  target1: number | null;
  target2: number | null;
  working_stop: number | null;
}

/* The overlay's geometry, mirroring `swingbot/core/charts/chart_geometry.py`
 * shape by shape. That module is the ONE implementation, shared with the PNG
 * the bot posts to Discord, so the browser and the image cannot disagree
 * about where a level sits -- these types describe its output and must never
 * grow a field the Python does not emit. */

/** An indicator line: an EMA, VWAP, a Bollinger or Donchian band. */
export interface CurveShape {
  kind: 'curve';
  label: string;
  points: ChartPoint[];
}

/** A Fibonacci retracement fan. The whole fan is drawn faintly with the
 *  matching member bolder, because a lone horizontal line at 61.8% says
 *  nothing about the swing it was measured from.
 *
 *  `ratios` is `[ratio, price, isMatch]`. `matched` may name a ratio label
 *  (`"Fib 61.8%"`), an anchor (`"Swing high"`/`"Swing low"`), or be null for
 *  a Fib label matching no ratio at all -- the fan is still drawn. */
export interface FibFanShape {
  kind: 'fib_fan';
  /** The 0% anchor: `[epochSeconds, price]`. */
  origin: ChartPoint;
  /** The 100% anchor: `[epochSeconds, price]`. */
  anchor: ChartPoint;
  ratios: [number, number | null, boolean][];
  matched: string | null;
  matched_price: number | null;
}

/** An unfilled fair value gap, as a rectangle running from the third candle
 *  of the 3-bar pattern that opened it to the right edge -- an unfilled gap
 *  is still unfilled today, which is the point of drawing it. */
export interface FvgZoneShape {
  kind: 'fvg_zone';
  t_from: number;
  t_to: number;
  price_low: number | null;
  price_high: number | null;
  mid: number | null;
  label: string;
}

/** A price level. `full_width` false means a BOUNDED segment: a rolling S/R
 *  level is only meaningful over the bars it was measured across, so drawing
 *  it as a full-width line would claim history it never described. */
export interface HorizontalShape {
  kind: 'horizontal';
  price: number;
  t_from: number;
  t_to: number;
  label: string;
  full_width: boolean;
}

/** A zigzag pivot: one point in time, drawn as a lone diamond. Its own kind
 *  rather than a zero-length `horizontal`, which would lose that it is not a
 *  level extending anywhere. */
export interface MarkerShape {
  kind: 'marker';
  t: number;
  price: number;
  label: string;
  pivot_kind: 'high' | 'low';
}

/** A diagonal support/resistance line, with the pivots it was fitted
 *  through.
 *
 *  `p1`/`p2` are the segment's ENDS -- two extrapolated positions at the fit
 *  window's edges, which no candle need ever have visited. `pivots` are the
 *  bars that actually touched the line and earned it the `Nx` in its label,
 *  so there are `strength` of them and not two. Drawing the ends as the
 *  diamonds is a bug the PNG renderer has already had once.
 *
 *  The line is never fitted at request time -- it is read off the trade,
 *  which is what makes this line and the PNG's line the same line. */
export interface TrendlineShape {
  kind: 'trendline';
  p1: ChartPoint;
  p2: ChartPoint;
  pivots: ChartPoint[];
  label: string;
}

/** Discriminated on `kind`, so a `switch` over it is exhaustive and adding a
 *  shape on the Python side becomes a compile error here rather than a
 *  silently undrawn overlay. */
export type ChartShape =
  | CurveShape
  | FibFanShape
  | FvgZoneShape
  | HorizontalShape
  | MarkerShape
  | TrendlineShape;

/** One confirming method drawn for one side of the trade. Both sides are
 *  returned when both have something drawable, target first -- the method
 *  that confirmed the target and the one holding the stop are different
 *  methods, and one overlay could only ever tell half of it. The list is
 *  empty when neither side has anything to draw (an older trade with no
 *  recorded sources, or one confirmed only by a candlestick pattern). */
export interface ChartOverlay {
  side: 'target' | 'stop';
  /** The confirming-method label the legend prints, e.g. `"EMA20"`. */
  source: string;
  shape: ChartShape;
}

/** `GET /market/chart/:ticker?trade_id=<id>&window=<bars>`.
 *
 *  Everything the interactive chart draws, in one request, computed by the
 *  same Python that draws the PNG posted to Discord (spec Decision 10).
 *
 *  Keyed by TICKER, with the trade optional: the subject of a chart is the
 *  instrument, and a plan is an annotation on top of it. Keyed by trade there
 *  was no way to chart a watchlist ticker at all, which is what forced the
 *  second, thinner chart component this type replaced.
 *
 *  `window` defaults to 120 and must be 20-500 -- out of range is a 400, NOT
 *  a clamp, so a caller asking for 5000 bars finds out rather than silently
 *  receiving a chart it did not ask for. */
export interface ChartResponse {
  ticker: string;
  ohlcv: ChartBar[];
  indicators: ChartIndicators;
  volume_profile: VolumeProfileBin[];
  /** Null without a `trade_id` -- no plan, no lines. Not an object of nulls:
   *  "there is no plan here" and "the plan has no target" are different
   *  answers and the chart draws them differently. */
  levels: ChartLevels | null;
  /** Empty, never null. Both sides when both are drawable, target first. */
  overlays: ChartOverlay[];
  /** The legend's fit notes, verbatim from the same helpers the PNG prints:
   *  the dates and prices a line was fitted between. Empty without a trade,
   *  because there is then no fit to explain. */
  notes: string[];
  /** The symbol this ticker actually trades in (`$`, `€`, ...). */
  currency: string;
}

/* -- preferences -------------------------------------------------------- */

/** Per-user UI state. Opaque to the server on purpose -- it is UI state, and
 *  a server that validated its shape would need editing every time the SPA
 *  remembered one more thing. Typed here, where it is actually used. */
export interface Preferences {
  /** Visible column ids, per table id. Absent means "the table's default".
   *
   *  Pre-SR12 shape, kept because it is already in people's saved
   *  preferences. SR12's per-density keys are flat and dotted
   *  (`tables.trades.compact.columns`) and live alongside it. */
  tables?: Record<string, string[]>;
  /** SR12 onward: flat dotted keys, so a new preference is a new key rather
   *  than a schema migration. Values are whatever that key stores, and every
   *  reader validates — see `ui/table-prefs.ts` for why that tolerance is
   *  what makes a stale preference degrade instead of break. */
  [key: string]: unknown;
}

/* -- versions ----------------------------------------------------------- */

/** One release: a distinct tuple of component versions, with the commit that
 *  introduced it. `versions` is keyed by component name and carries `null` for
 *  a component that did not exist yet — which is a different fact from a
 *  component that did not change, and the strip draws the two differently. */
export interface Release {
  date: string;
  /** The last date this exact tuple was still current. Equal to `date` for a
   *  tuple superseded the same day. */
  last_seen: string;
  commit: string;
  subject: string;
  versions: Record<string, string | null>;
  /** Components whose value differs from the previous release. Derived by the
   *  generator, never here — see the note in `build_version_matrix.py`. */
  changed: string[];
}

export interface VersionHistory {
  /** When the frozen file was generated; null if it was never generated. */
  generated_at: string | null;
  /** The server's own sentence about what the data does and does not claim.
   *  Rendered verbatim rather than restated, so the page cannot drift into
   *  promising "tested" where the API says "shipped". */
  basis: string | null;
  /** Read from VERSION.json per request, so it always matches the sidebar. */
  live: Record<string, string>;
  /** VERSION.json has moved on since the frozen file was generated. */
  stale: boolean;
  /** Lane and chip order: first-appearance, so adding a component appends. */
  components: string[];
  current: Record<string, string>;
  /** Oldest first on the wire. The store reverses exactly once. */
  releases: Release[];
}

/** A selected `{component, version}` pair, or null for "no filter". */
export type VersionFilter = { component: string; version: string } | null;
