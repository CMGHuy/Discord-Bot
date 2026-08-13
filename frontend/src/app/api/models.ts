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
}

export const TRADE_SORTABLE = [
  'opened_at', 'closed_at', 'ticker', 'status', 'pnl_pct', 'r_multiple',
  'entry', 'exit_price', 'held_hours', 'realized_pnl_amount',
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
}

/* -- analytics ---------------------------------------------------------- */

export interface AnalyticsSnapshot {
  wins: number | null;
  losses: number | null;
  avg_realized_pct: number | null;
  best_trade_pct: number | null;
  worst_trade_pct: number | null;
  avg_holding_days: number | null;
}

export interface AnalyticsPerformance {
  totals: Record<string, unknown>;
  relocated: Record<string, unknown>;
  win_rate: number | null;
  expectancy_r: number | null;
  by_confidence: Record<string, unknown>;
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

export interface ProposalList {
  proposals: unknown[];
}

export interface Proposal {
  filename: string;
  proposal: Record<string, unknown>;
}

/* -- universe ----------------------------------------------------------- */

export interface Ticker {
  symbol: string;
  company_name: string | null;
  open_trades: number;
  closed_trades: number;
}

/** `GET /universe/tickers`. A plain list, NOT a `Collection` — the watchlist
 *  is not paginated and the endpoint ships no envelope. This was typed
 *  `Collection<Ticker>`, which compiled and would have handed the store
 *  `undefined` at runtime; `tests/admin/test_api_v1_universe.py` asserts
 *  `body["tickers"]`, the same trap `OhlcvResponse` records. */
export interface TickerList {
  tickers: Ticker[];
}

/** `POST /universe/tickers`. One endpoint for single and bulk add, which is
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

/** One `GET /universe/suggest` hit. `name` here, not `company_name` — it
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

/* -- market ------------------------------------------------------------- */

export interface Candle {
  /** `YYYY-MM-DD`, which is also what lightweight-charts accepts directly. */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** The plan lines a chart draws. Present ONLY when `trade_id` was supplied
 *  and resolved -- an unresolvable id is a 404 rather than a chart quietly
 *  missing its levels, because a plain chart that looks complete is how a
 *  reader concludes the lines were never set. */
export interface TradeLevels {
  entry: number | null;
  stop_loss: number | null;
  tp1: number | null;
  tp2: number | null;
  direction: string | null;
}

/** `GET /market/ohlcv/:ticker`.
 *
 *  An ENVELOPE, not a bare array. This was previously typed as `Candle[]`,
 *  which compiled fine and would have handed the chart `undefined` at
 *  runtime -- NG45 is the first consumer, so it is the first thing that
 *  would have noticed. `tests/admin/test_api_v1_market.py` is the contract
 *  and it asserts `body["bars"]`. */
export interface OhlcvResponse {
  ticker: string;
  bars: Candle[];
  levels?: TradeLevels;
}

/* -- preferences -------------------------------------------------------- */

/** Per-user UI state. Opaque to the server on purpose -- it is UI state, and
 *  a server that validated its shape would need editing every time the SPA
 *  remembered one more thing. Typed here, where it is actually used. */
export interface Preferences {
  /** Visible column ids, per table id. Absent means "the table's default". */
  tables?: Record<string, string[]>;
}
