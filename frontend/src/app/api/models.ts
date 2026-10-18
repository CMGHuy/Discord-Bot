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
export interface TradeCollection extends Collection<TradeRow> { prices_as_of?: string | null; }

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
  /** v86 -- the cohort risk verdict: `COHORT_POOR` / `COHORT_STRONG` /
   *  `COHORT_TYPICAL` / `COHORT_UNKNOWN`. Never null -- a pre-v86 record or
   *  an unstamped plan reports `COHORT_UNKNOWN` server-side rather than a
   *  field every caller would have to null-check separately from `badge`.
   *  Optional here (not on every existing fixture) so a spec written before
   *  this field existed is not forced to grow it. */
  cohort_label?: string;
  /** The numbers behind `cohort_label` -- `regime2_state`, `win_rate`,
   *  `expectancy_r`, `n_live`, `n_backtest`, `run_date`. `{}` only for a plan
   *  issued before the cohort registry existed, or whose risk-feature
   *  stamping otherwise never ran. A `COHORT_UNKNOWN` plan issued against a
   *  real registry is still stamped with the full dict (it just fell below
   *  the registry's N floor) -- `n_live`/`n_backtest` can be 0 there, and a
   *  reader must treat that as "not enough data", not compute a WR/ExpR line
   *  off the zeroed stats. Untyped like `TradeDetailFields`'s other stat
   *  bags (`badge_stats`, `confidence_breakdown`) -- the shape varies by
   *  which cohort branch stamped it. */
  cohort_stats?: Record<string, unknown>;
  confidence_level: number | null;
  confidence_score: number | null;
  quality_score: number | null;
  entry: number | null;
  stop_loss: number | null;
  /** v166 -- the plan's ORIGINAL risk stop. `stop_loss` is the working
   *  (trailing) stop once a plan is PARTIAL; this is the stop the position
   *  was sized against, so risk per share and "$ at risk" read it first.
   *  The API always sends it (null on a row with no stop). Optional here,
   *  like `cohort_label`, so a typed fixture written before this field
   *  existed is not forced to grow it. */
  risk_stop?: number | null;
  target: number | null;
  target2: number | null;
  /** The TP1 leg's own fraction/fill-price/R once a PARTIAL plan has banked
   *  it. All three null until then; a legacy trade never scale-outs so
   *  always null. */
  banked_fraction: number | null;
  banked_exit_price: number | null;
  banked_r: number | null;
  risk_reward: number | null;
  shares: number | null;
  /** The share count still exposed to price movement right now -- `shares`
   *  is the ORIGINAL size at open and stays that after a TP1 partial closes
   *  part of the position; a live P&L dollar figure has to scale by this
   *  instead. Equal to `shares` until a leg has realized. */
  open_shares: number | null;
  position_value: number | null;
  current_price: number | null;
  /** True when `current_price` did not come from a live intraday tick this
   *  request -- yfinance's fast_info fallback, or a last-known-good cache
   *  entry served past its TTL (`admin/api_v1/trades.py::_attach_current_
   *  prices`). The MRNA incident (2026-09-18): a fallback echoed yesterday's
   *  close during premarket and the status bar read "Near stop-loss" for a
   *  position that never actually touched it. Always present, never null --
   *  false when there is no price at all. */
  current_price_stale: boolean;
  exit_price: number | null;
  realized_pnl_amount: number | null;
  pnl_pct: number | null;
  r_multiple: number | null;
  held_hours: number | null;
  opened_at: string | null;
  closed_at: string | null;
  has_note: boolean;
  /** Whether this row's CURRENT status was entered today (Europe/Berlin
   *  calendar day). See the `today` query param on `TradeQuery` below. */
  today: boolean;
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
  target_is_banked_tp1: boolean;
  stop_kind: 'risk' | 'trailing' | 'derived_floor';
  bar_kind: 'progress' | 'approach' | 'trailing' | 'none';
  /** Best price since TP1 -- the 100% end of a trailing runner's bar (0% is
   *  the trailing stop). Server-side input to `progress_pct`; null until the
   *  runner has recorded one and on every row that is not a runner. */
  runner_best?: number | null;
  /** Trailing runner only: P&L % vs the original fill if the trailing stop
   *  is hit (bar 0%) and at the best price since TP1 (bar 100%). */
  stop_pnl_pct?: number | null;
  best_pnl_pct?: number | null;
  floor_r: number | null;
  price_r: number | null;
  headroom_r: number | null;
  distance_to_trigger_r: number | null;
  bars_to_expiry: number | null;
  /** Which row this is out of how many, when a scaled-out position has
   *  been split into one row per leg (v79). 0/1 for every row that
   *  isn't split. */
  leg_index: number;
  leg_total: number;
}

export type GateKey = 'rs' | 'regime' | 'earnings';

export interface GatePart {
  label: string;
  value: number | string | null;
}

export interface GateRow {
  key: GateKey;
  label: string;
  value: number | string | null;
  threshold: number | null;
  margin: number | null;
  applies: boolean;
  parts: GatePart[];
  note: string | null;
}

export interface CalendarRow {
  date: string;
  kind: 'opex_monthly';
  label: string;
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
  entry_context: Record<string, unknown>;
  risk_features: Record<string, unknown>;
  cohort_label: string | null;
  confidence_points: Record<string, number> | null;
  confidence_unevaluated: string[];
  gates: GateRow[];
  sessions_since_created: number | null;
  expires_on: string | null;
  time_exit_on: string | null;
  calendar: CalendarRow[];
  hold_cap_bars: number | null;
  acceptance_level: number | null;
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

/** What POST /trades/close-open reports. `failed` is separate from `closed`
 *  on purpose: a partial success has to be able to say so. */
export interface CloseOpenResult {
  closed: number;
  failed: number;
  tickers: string[];
}

/** `?scope=` on POST /trades/close-open -- which of the two closeable
 *  statuses (ACTIVE, PARTIAL) a bulk close actually closes. Omitted (the
 *  default) matches 'open_partial': both. */
export type CloseScope = 'open' | 'partial' | 'open_partial';

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
  /** Whether this row's CURRENT status was entered today (Europe/Berlin
   *  calendar day). The Dashboard lifecycle strip's date scope, sent
   *  alongside `status` from a card click so Today/Today+open narrows all
   *  five statuses the same way the strip's own counts do -- not just
   *  CLOSED/CANCELLED. Tri-state like `has_note`: absent means unfiltered. */
  today?: boolean;
  /** v85 D32. The opened-at range -- inclusive on both ends, `YYYY-MM-DD`,
   *  camelCase here because this is the store's own query slice; `ApiClient`
   *  maps the pair to `opened_from`/`opened_to` on the wire. A `null` bound
   *  drops that parameter entirely rather than sending it empty, the same
   *  convention every other filter in this interface follows. */
  openedFrom?: string | null;
  openedTo?: string | null;
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
  /** Sum of shares x (price - entry) over open positions; null when none has a share count. */
  open_pnl_amount: number | null;
  risk_used_pct: number | null;
  risk_cap_pct: number | null;
  open_trades: number;
  avg_confidence: number | null;
  win_rate: number | null;
  win_rate_n: number;
  expectancy_r: number | null;
  expectancy_n: number;
  payoff_ratio: number | null;
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
  /** The plan-lifecycle diagram's "Expires" definition names this number --
   *  projected from the server's own DEFAULT_EXPIRY_BARS constant rather
   *  than the SPA hardcoding a second copy that could drift from it. */
  default_expiry_bars: number;
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
  /** v94 T1 additions below. Every real response carries all four -- they
   *  are optional here (rather than widening `EMPTY_DERIVED` and every
   *  existing `AnalyticsDerived` test fixture across the codebase, which
   *  T1's brief keeps out of scope) so a fixture that predates them still
   *  type-checks; `overview.ts` reads each with `?? null`, which already
   *  treats "absent" and "null" the same way a fixture gap should. */
  /** Gross realised win / |gross realised loss|, unitless like
   *  `sharpe_ann`/`sortino_ann` beside it (`metrics.profit_factor`, scoped). */
  profit_factor?: number | null;
  /** The Outcome panel's Avg win/Avg loss/Payoff rows. R-based (mean of the
   *  R-multiples on each side), not the P&L-percent `avg_win_pct`/
   *  `avg_loss_pct` above -- those answer a different question. `payoff_r`
   *  is `avg_win_r / |avg_loss_r|` over that SAME R-multiples list
   *  (`metrics.payoff_ratio`), never re-derived. */
  avg_win_r?: number | null;
  avg_loss_r?: number | null;
  payoff_r?: number | null;
}

/** One closed trade, cumulative in R (v85 D39, R9-01). `drawdown_r` is
 *  peak-to-current, non-negative. Ordered by close date, not calendar day --
 *  a day with no closes is a missing observation, not a flat one. */
export interface EquityCurvePoint {
  date: string;
  cum_r: number;
  drawdown_r: number;
  cum_pnl: number;
  cum_pct: number | null;
}

export type LedgerScope = 'main' | 'weak' | 'both';
export type AnalyticsUnit = 'r' | 'pct' | 'money';
export interface BookScope { from: string | null; to: string | null; ledger: LedgerScope; strategy: string | null; horizon: string | null; direction: string | null; }
export interface Scoped { scope: BookScope; n: number; }

export interface AnalyticsEquityCurve extends Scoped {
  points: EquityCurvePoint[];
  points_n: number;
  as_of: string | null;
  benchmark: { spy_indexed: { date: string; pct: number }[] };
}

/** One strategy or horizon's aggregate (v85 D40, R9-02). `total_r` is a
 *  true sum, never `exp_r * n` -- a trade `r_multiple()` cannot compute is
 *  skipped from both, and deriving one from the other would print a number
 *  nobody actually computed. `badge` is present only for `dim=strategy`. */
export interface AnalyticsByDimensionRow {
  key: string;
  exp_r: number | null;
  total_r: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_r: number | null;
  n: number;
  wins: number; losses: number; avg_win_r: number | null; avg_loss_r: number | null; total_pnl: number;
  badge?: string;
  soak?: unknown;
}

export interface AnalyticsByDimension extends Scoped {
  rows: AnalyticsByDimensionRow[];
  as_of: string | null;
  min_cell_n: number;
}

export interface AnalyticsPerformance extends Scoped {
  totals: Record<string, unknown>;
  relocated: Record<string, unknown>;
  win_rate: number | null;
  win_rate_n: number;
  expectancy_r: number | null;
  expectancy_n: number;
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
  risk_reward_split: HoldingBucket[];
  calendar: { month: string; return_pct: number | null; pnl?: number; n: number }[];
  cumulative_by_strategy: Record<string, { date: string; cum_pct: number }[]>;
  benchmark: { spy_cum: Record<string, number> };
  rolling_wr: { date: string; win_rate: number }[];
  rolling_exp_r: { date: string; exp_r: number }[];
  /** v94 T1 -- the Overview tab's Streaks row (`metrics.streaks`, scoped
   *  like every other block here). `current`/`current_kind` describe the
   *  streak still running as of the scope's last close; `current_kind` is
   *  null only when `current` is 0 (no win/loss trade closes the scope). */
  streaks: {
    current: number;
    current_kind: 'win' | 'loss' | null;
    best_win_streak: number;
    worst_loss_streak: number;
  };
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
export interface AnalyticsJournal extends Scoped {
  digest: string[];
  lessons: string[];
  /** Entries behind both lists, so a digest from three is not read like one
   *  drawn from three hundred. */
  entries_n: number;
}

export interface AnalyticsStrategies extends Scoped {
  strategies: unknown[];
  /** Legacy matrix retained until the v94 Attribution heat grid fully
   * replaces the existing Strategies workspace. */
  heatmap?: { strategies: string[]; horizons: string[]; cells: unknown[] };
  registry_scope: 'all-time';
  contribution: { strategy: string; total_r: number | null; n: number }[];
  cumulative: Record<string, { date: string; cum_r: number }[]>;
}

/** v164: one row of the pre-registered live loss watch (spec D2), as
 *  `calibration.live_loss_watch` emits it. `alert` means live ExpR for this
 *  row is below zero with ~90% one-sided confidence; the `registry_*` fields
 *  are backtest context only, never comparable with the live figures. */
export interface LiveLossRow {
  source: string;
  strategy: string;
  /** `null` is the pooled row of its `(source, strategy)`. */
  horizon: string | null;
  live_n: number;
  /** 0–100 over wins and losses only; `null` when there is neither. */
  live_wr: number | null;
  live_expr: number | null;
  /** 90th percentile of the week-clustered bootstrap of mean R. */
  bound_upper: number | null;
  alert: boolean;
  registry_status: string | null;
  registry_window_kind: 'TRAIN' | 'VALIDATION' | null;
  registry_run_date: string | null;
  registry_expr: number | null;
}

/** Rows already ordered by the server (alerts first, then confluence by
 *  horizon with the pooled row last, then strategies by name). */
export interface LiveLossWatch {
  rows: LiveLossRow[];
  counts: Record<string, number>;
}

export interface AnalyticsCalibration {
  deciles: unknown[];
  levels: unknown[];
  drift: unknown[];
  /** Absent on a snapshot cached before v164; the API then sends the empty
   *  shape, but the client tolerates the key missing as well. */
  live_loss_watch?: LiveLossWatch;
  scope: 'all-time';
}

/** `GET /analytics/exit-quality`: all-time journal exit diagnostics. */
export interface AnalyticsExitQuality extends Scoped {
  exit_reasons: unknown[];
  unmapped_reasons: { status: string; text: string; n: number }[];
  hold_by_outcome: unknown;
  hold_points: { outcome: string; days: number }[];
  efficiency: { bins: unknown[]; n: number; median: number | null };
  mae: { bins: unknown[]; n: number; median: number | null };
  scatter: unknown[];
  coverage: Record<string, { non_null: number; total: number; pct: number }>;
  min_cell_n: number;
}

/** v142 — `GET /analytics/partials` (`swingbot/core/analytics/partials.py`).
 *  Rates are percentages 0-100; every R is on the plan's initial risk. The
 *  scope's date range filters on FILL date and `n` is the filled plans. */
export interface PartialsKpis {
  tp1_rate: number | null; tp1_rate_n: number | null;
  tp1_tp2_rate: number | null; tp1_tp2_n: number;
  beat_all_out: number | null; beat_all_out_n: number;
  mean_runner_delta_r: number | null;
  median_tp1_exit_sessions: number | null; tp1_exit_n: number;
}
export type PartialsStage = 'filled' | 'tp1' | 'runner_closed' | 'tp2';
export type PartialsBucket = 'tp2' | 'trail' | 'floor' | 'stall' | 'time' | 'manual' | 'no_tp2' | 'open' | 'other';
export type PartialsDimension = 'strategy' | 'horizon' | 'side' | 'month';
export type PartialsHoldStage = 'entry_tp1' | 'tp1_exit' | 'entry_exit';
export interface PartialsHold { p25: number | null; median: number | null; p75: number | null; points: number[]; }
export interface PartialsBreakdownRow extends PartialsKpis { key: string; n: number; thin: boolean; }
export interface PartialsLadderRow { level_r: number; touch_rate: number | null; cf_exp_r: number | null; n: number; }
export interface PartialsSplitRow { fraction: number; exp_r: number | null; n: number; }
export interface PartialsOutcome { bucket: PartialsBucket; n: number; share: number | null; avg_runner_r: number | null; }
export interface AnalyticsPartials extends Scoped {
  kpis: PartialsKpis;
  funnel: { stage: PartialsStage; n: number }[];
  outcomes: PartialsOutcome[];
  counterfactuals: {
    actual_exp_r: number | null; all_out_exp_r: number | null; giveback: number[];
    ladder: PartialsLadderRow[]; split: PartialsSplitRow[];
    path_unavailable: number; runner_r_unavailable: number;
  };
  holds: Record<PartialsHoldStage, PartialsHold>;
  breakdowns: Record<PartialsDimension, PartialsBreakdownRow[]>;
  thin_n: number;
  population: { filled: number; partial: number; unreadable: number };
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
  scope: 'all-time';
}

export interface AnalyticsHeatGrid extends Scoped {
  rows: string[]; cols: string[];
  cells: { r: number; c: number; n: number; exp_r: number | null; win_rate: number | null }[];
  folded: { n_strategies: number; cells: { c: number; n: number; exp_r: number | null; win_rate: number | null }[] };
  min_cell_n: number;
}

/** One row of `_registry_rows()`: the committed out-of-sample badge for a
 *  strategy, joined against how that strategy is actually doing live. */
export interface StrategyRow {
  strategy: string;
  /** `VALIDATED` or `WEAK` — whether it cleared its one-shot OOS bar. */
  status: string;
  /** OOS sample and result, from the committed validation registry. */
  n: number;
  win_rate: number;
  expectancy_r: number;
  window: string | null;
  run_date: string | null;
  /** Live counterparts. Null until there are closed trades to measure. */
  live_n: number | null;
  live_wr: number | null;
  delta_vs_oos: number | null;
  /** Pre-registered decay rule: live_n >= 20 and live_wr < oos_wr - 10. */
  decayed: boolean;
  /** Age of the evidence itself, derived server-side from `run_date` at read
   *  time and never stored: `fresh` | `aging` | `stale` | `unknown`. A
   *  different fact from `decayed` above, which is live-vs-OOS win-rate drift.
   *  Display only — nothing is gated on it. */
  evidence_decay: string;
  gate_description: string | null;
  /** Rolling 10-trade win rate, oldest first. Carries nulls for windows the
   *  server could not compute, which the sparkline cannot plot. */
  win_rate_series: (number | null)[];
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
  registry: StrategyRow[];
}

/* -- research (v150) ---------------------------------------------------- */

/** Which docs folder a ledger row's `record` points into. */
export type LedgerRecordKind = 'results' | 'specs' | 'plans' | 'other';

/** One pre-registration: the nine fields the ledger stores, plus three the
 *  endpoint derives. `n`, `exp_r` and `p` are null on most historical rows —
 *  a null is "not recorded", never zero. */
export interface LedgerRow {
  id: string;
  /** `YYYY-MM-DD`. */
  date: string;
  hypothesis: string;
  instrument: string;
  n: number | null;
  exp_r: number | null;
  p: number | null;
  verdict: string;
  /** Repo-relative path of the results doc, spec or plan that records it. */
  record: string;
  /** BH q-value across every ledger row with a p-value. Reported, never
   *  gating; null when `p` is null. Filters do not change it. */
  q: number | null;
  /** Whether `record` resolves in the deployed build. */
  record_exists: boolean;
  record_kind: LedgerRecordKind;
}

/** `GET /research/ledger`. The vocabularies come from the server so a
 *  verdict added to the ledger later appears as a filter without a release. */
export interface ResearchLedger {
  rows: LedgerRow[];
  /** How many rows have a p-value: the BH family size behind every `q`. */
  q_family_m: number;
  verdicts: string[];
  instruments: string[];
}

/* -- reports (v150) ----------------------------------------------------- */

/** The envelope both `GET /reports/*` endpoints return. `not_run` is a
 *  state the page renders ("Not yet run"), not an error. */
export interface ReportEnvelope<T> {
  status: 'ok' | 'not_run';
  generated_at: string | null;
  result: T | null;
}

/* Field names below are v146's and v147's, pinned 2026-10-15 from the
 * builders' own output (`report-fixtures.spec.ts` holds the key lists). Units
 * differ between the two reports: v146 `win_rate` is a PERCENT (0-100), v147
 * `*_win_rate` and `fill_rate` are FRACTIONS (0-1). */

/** The verdict that counts: fixed at the first qualifying run and carried
 *  forward unchanged by every later one. */
export interface VerdictOfRecord {
  verdict: string;
  /** `YYYY-MM-DD` of the run that fixed it. */
  date: string;
  /** v146: rows that entered the verdict, live + TRAIN. v147: the cell's
   *  distinct filled blocked setups at that run. */
  n: number;
}

/** p25 / median / p75 of the planned risk:reward ratio; all null when no
 *  row carried one. */
export interface AttributionQuartiles {
  p25: number | null;
  median: number | null;
  p75: number | null;
}

/** v146: does confidence order R? Spearman rho plus the top-minus-bottom
 *  tercile ExpR with its week-clustered 95% interval. The interval and p are
 *  null when a tercile is under v146's floor. */
export interface AttributionMonotonicity {
  /** Rows with a confidence score. */
  n: number;
  spearman_rho: number | null;
  tercile_spread: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p: number | null;
  /** The interval lies wholly below zero. Reported inside NOT PREDICTIVE. */
  inverted: boolean;
  /** Rows per tercile: [bottom, middle, top]. */
  tercile_n: number[];
  /** R:R quartiles per tercile, same order as `tercile_n`. */
  rr_by_tercile: AttributionQuartiles[];
}

/** v146: ExpR where a confidence factor scored > 0, minus where it scored 0.
 *  `key` is the factor's display name (e.g. `MACD momentum`). */
export interface AttributionFactor {
  key: string;
  /** `n_pos + n_zero`. */
  n: number;
  n_pos: number;
  n_zero: number;
  delta: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p: number | null;
  /** BH q over every look on the report. */
  q: number | null;
}

export interface AttributionBucket {
  label: string;
  n: number;
  /** PERCENT (0-100); a win is net `r > 0`. */
  win_rate: number | null;
  /** Net of frictions. */
  exp_r: number | null;
  exp_r_gross: number | null;
  /** v146 sets this on every bucket below its floor. The page never tests N. */
  thin: boolean;
  /** This bucket's ExpR minus the rest of its grouping's, with its interval
   *  and p (null on a thin bucket or a thin rest). */
  delta: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p: number | null;
  q: number | null;
  /** `confidence_decile` buckets only. */
  unevaluated_n?: number;
  /** `confidence_decile` buckets only. */
  rr?: AttributionQuartiles;
}

/** ISO Mondays of the first and last entry week in the population. */
export interface AttributionWindow {
  first_week: string;
  last_week: string;
}

export interface AttributionPopulation {
  window: AttributionWindow;
  n: number;
  monotonicity: AttributionMonotonicity;
  factors: AttributionFactor[];
  /** Grouping -> its buckets, in the report's own order. Groupings:
   *  confidence_decile, confidence_level, confluence, regime2_state,
   *  rs_quintile, direction, horizon, earnings, earnings_in_hold. */
  buckets: Record<string, AttributionBucket[]>;
  /** The monotonicity table again per direction (`bullish` / `bearish`) and
   *  per horizon key (`2w`, `3m`, ...). */
  splits: {
    direction: Record<string, AttributionMonotonicity>;
    horizon: Record<string, AttributionMonotonicity>;
  };
  /** Fixed caveats for this population, in order. */
  notes: string[];
}

/** `load_latest()` of `swingbot/core/infra/expectancy_attribution_store.py`. */
export interface ExpectancyAttribution {
  generated_at: string;
  /** The latest run's reading. Descriptive once a verdict of record exists. */
  verdict: string;
  verdict_of_record: VerdictOfRecord;
  /** The BH family size behind every q on this report. */
  looks: number;
  seed: number;
  /** Earnings file set, TRAIN input, frictions, resamples. Shown as-is. */
  provenance: Record<string, unknown>;
  /** Never pooled. Either side may be absent from a run. */
  populations: {
    live: AttributionPopulation | null;
    train: AttributionPopulation | null;
  };
}

/** v147: one verdict cell, gate x population. Five verdict cells, then three
 *  note cells (`rs`/train, `no_qualifying_target`/live and /train). */
export interface GateCell {
  /** `rs`, `risk_cap`, `compression` or `no_qualifying_target`. */
  gate: string;
  population: 'live' | 'train';
  /** The latest reading: GATE EARNS | GATE COSTS | INCONCLUSIVE | WAITING.
   *  Always WAITING when `note` is set. */
  verdict: string;
  /** Distinct filled blocked setups. v147 counts it; the page never does. */
  n: number;
  /** Distinct filled setups in the taken arm. */
  taken_n: number;
  /** Null until the first reading at or above v147's floor. */
  verdict_of_record: VerdictOfRecord | null;
  /** Blocked ExpR minus taken ExpR, its interval, p and BH q over the five
   *  verdict cells. Null when the cell had no eligible reading. */
  latest: { difference: number; ci_low: number; ci_high: number; q: number; p: number } | null;
  in_sample: boolean;
  /** A fixed non-verdict state persisted by v147: "no TRAIN population",
   *  "no verdict — no-plan", "no TRAIN taken arm — no as-of earnings
   *  archive", or "taken arm below the floor (...)". */
  note: string | null;
}

/** v147: one detail row, gate x reason x population. */
export interface GateCounterfactualRow {
  gate: string;
  reason: string;
  population: 'live' | 'train';
  blocked_n: number;
  no_plan_n: number;
  /** FRACTION (0-1) of tried blocked setups that filled. */
  fill_rate: number | null;
  blocked_exp_r: number | null;
  /** FRACTION (0-1). */
  blocked_win_rate: number | null;
  /** Filled setups in the taken arm. */
  taken_n: number;
  taken_exp_r: number | null;
  /** FRACTION (0-1). */
  taken_win_rate: number | null;
  /** The taken arm's booked R, beside the re-walk; never the taken ExpR. */
  taken_realised_exp_r: number | null;
  near_miss_n: number | null;
  near_miss_exp_r: number | null;
  rest_n: number | null;
  rest_exp_r: number | null;
  /** `risk_cap` rows only: the fixed-dollar-risk figure beside R. */
  dollar_risk: number | null;
  over_cap: boolean;
  in_sample: boolean;
}

/** `load_report()` of `swingbot/core/infra/gate_counterfactual_store.py`. */
export interface GateCounterfactual {
  generated_at: string;
  live_window: string | null;
  /** The BH family size: the five verdict cells. */
  bh_family: number;
  seed: number;
  /** Fixed caveats, in order. */
  limitations: string[];
  cells: GateCell[];
  rows: GateCounterfactualRow[];
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
 *  endpoint answers 200 with the same keys either way, so nothing here has to
 *  branch on which shape arrived (SR51). `data_source` (v162) is the training
 *  data the grid ran on: `"yfinance"` for a result written before v162, null
 *  while there is no result yet. */
export interface JobResult {
  job_id: string;
  strategy: string | null;
  grid: unknown[];
  data_source: string | null;
}

/** `GET /jobs/tune/defaults` (v162) — the launcher's training-data picker:
 *  the server's TRAINING_DATA_SOURCE and every value it accepts. */
export interface TuneDefaults {
  data_source: string;
  choices: string[];
}

export interface ProposalList {
  proposals: unknown[];
}

export interface Proposal {
  filename: string;
  proposal: Record<string, unknown>;
}

/* -- watchlist ----------------------------------------------------------- */

/** The Watchlist's Signal column (v85 D34) -- the bot's own opinion, read off
 *  the live plan set rather than derived from price. `score`/`horizon`/
 *  `strategy` are null together with `state: 'none'` -- there is no partial
 *  signal, only "the scanner has an opinion" or "it does not". */
export interface TickerSignal {
  state: 'none' | 'pending' | 'active';
  score: number | null;
  horizon: string | null;
  strategy: string | null;
}

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
  /** v85 D33 -- batched market data (`swingbot/admin/watchlist_rows.py`,
   *  `build_market_rows`). `price` prefers a live intraday quote over the
   *  last close, when the US market is open; all fields are null together
   *  when the cache has nothing for this symbol yet. */
  price: number | null;
  /** v106 -- which provider served `price` when it is the live overlay;
   *  null when `price` is the cached close. Only `yfinance-fallback` is
   *  flagged in the table: Alpaca missed and yfinance answered instead. */
  price_source?: 'alpaca' | 'yfinance' | 'yfinance-fallback' | null;
  /** The date of the bar `price`/the change columns/`spark` were computed
   *  from -- NOT when the request was served. A page reading "as of now"
   *  over Friday's close on a Sunday is the failure this field guards
   *  against, and a symbol whose `as_of` lags the rest of the table is
   *  flagged rather than shown silently beside fresher rows. */
  as_of: string | null;
  change_1d_pct: number | null;
  change_1w_pct: number | null;
  change_1m_pct: number | null;
  /** Up to 30 daily closes, oldest first. Empty (never a single flat point)
   *  when there is no history to draw. */
  spark: number[];
  signal: TickerSignal;
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

/** v106 -- the live data provider and how often Alpaca misses.
 *  `fallback_rate` is yfinance-fallback over everything Alpaca was asked for
 *  across the last `scans` scans that logged it; null when none did. */
export interface DataSourcesHealth {
  enabled: boolean;
  feed: string;
  breaker_open: boolean;
  fallback_rate: number | null;
  scans: number;
}

export interface ScanHealth {
  durations_s: number[];
  latest_s: number | null;
  slowdown: boolean;
  data_sources?: DataSourcesHealth | null;
}

/** `POST /risk/killswitch`'s body. The toggle deliberately does NOT return
 *  the whole risk resource — see `ApiClient.setKillswitch`. */
export interface KillswitchResult {
  killswitch: Killswitch;
}

/** One institutional metric (v85 D37) — `value` is `null`, never `0`, when
 *  `risk_metrics.py` can't justify a number; `n` is always the sample size
 *  actually attempted, which is what lets the tile say "N=3" instead of
 *  rendering a bare dash with no way to tell why. */
export interface RiskMetric {
  value: number | null;
  n: number;
}

export interface RiskMetrics {
  var_95: RiskMetric;
  expected_shortfall_95: RiskMetric;
  annualised_vol: RiskMetric;
  beta_spy: RiskMetric;
  sharpe_r: RiskMetric;
  max_drawdown_r: RiskMetric;
  as_of: string | null;
  /** The ticker `beta_spy` was actually computed against --
   *  `config.MARKET_REGIME_TICKER`, which an operator can change away from
   *  "SPY". The payload key stays `beta_spy` (a rename is a bigger, riskier
   *  change); this is what lets the tile label stay honest instead of
   *  hardcoding "SPY". */
  benchmark_symbol: string;
}

/** Pairwise Pearson correlation of daily returns (v85 D38). `values[i][j]`
 *  is `null`, never `0`, for a pair with too little overlap to correlate —
 *  zero correlation is a finding, no data is not. */
export interface Correlation {
  labels: string[];
  values: (number | null)[][];
}

export interface Risk {
  heat: RiskHeat;
  positions: RiskPosition[];
  sector_heat: SectorHeat[];
  clusters: unknown[];
  throttle: Throttle;
  killswitch: Killswitch;
  scan_health: ScanHealth;
  metrics: RiskMetrics;
  correlation: Correlation;
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

/** A running scan's published progress, or absent when none is running.
 *
 *  `pct` is a **whole-scan** figure the bot derives, not the ratio of the
 *  `done`/`total` beside it: a scan runs three phases and resets its counters
 *  at each one, so those two numbers describe the *current phase* only.
 *  Deriving a bar from them would run 0->100 three times per scan. See
 *  `swingbot/core/scanning/progress_store.py` for the phase bands.
 *
 *  `at` is what makes a stalled scan visible. A bot that dies mid-scan leaves
 *  its running flag set and this record frozen; without the timestamp the UI
 *  would show a live-looking bar that will never move again. */
export interface ScanProgressRecord {
  /** ISO 8601, UTC. When the bot last published -- not when the scan began. */
  at: string;
  /** 0-100 across the whole scan. */
  pct: number;
  /** The bot's own phase name: `starting`, `crawling data`, `analyzing`,
   *  `building alerts`. Mapped to display text in the SPA, not by the bot. */
  stage: string;
  current_ticker: string | null;
  /** Progress within `stage`, whose unit changes with it: tickers while
   *  crawling, ticker x horizon checks while analysing, alerts while
   *  building. */
  done: number;
  total: number;
  qualifying_found: number;
}

export interface ScanStatus {
  pending: boolean;
  triggered_at: string | null;
  paused: boolean;
  paused_at: string | null;
  running: boolean;
  bot_alive: boolean;
  bot_last_seen: string | null;
  /** Null when the bot has never completed a tick -- unknown, not failing. */
  bot_healthy: boolean | null;
  bot_last_success: string | null;
  bot_consecutive_failures: number;
  /** Null when the bot has never reported -- distinct from false. */
  bot_session_active: boolean | null;
  bot_scan_paused: boolean | null;
  /** Null whenever no scan is publishing. Render that as "no bar", never as
   *  0% -- "a scan has started and achieved nothing" is a different claim. */
  progress: ScanProgressRecord | null;
}

export interface ScanCommandResult {
  ok: boolean;
  message: string;
  scan: ScanStatus;
}

/* -- system health (v148) ------------------------------------------------ */

/** One scheduled scan's provider figures, from `GET /system/health`.
 *  Rates are fractions (0.05 = 5%). The four figures are null on a row
 *  written before v148 -- render "—", never 0. */
export interface ProviderHealthRow {
  at: string;
  tickers: number;
  /** yfinance-fallback / (alpaca + yfinance-fallback), daily frames and live
   *  prices pooled; null when Alpaca was asked for nothing. */
  provider_fallback_rate: number | null;
  /** Frames whose last bar is before the previous NYSE session. Display
   *  only: no alert reads it. */
  stale_symbols: number | null;
  empty_symbols: number | null;
  empty_rate: number | null;
}

/** Errors a process caught and carried on from, per call-site tag. */
export interface SwallowedRow {
  process: 'bot' | 'admin';
  tag: string;
  count: number;
  first_at: string | null;
  last_at: string | null;
  /** `Type: message`, at most 200 characters; no traceback. */
  last_error: string | null;
}

export interface SystemHealth {
  /** Newest first, at most 20. */
  providers: ProviderHealthRow[];
  /** Percent (1-100): the levels the ops-channel alert fires above. */
  thresholds: { fallback_pct: number; empty_pct: number };
  /** Highest count first. */
  swallowed: SwallowedRow[];
  /** When the bot's counts began (its process start); null when the bot has
   *  not yet written them. */
  bot_counts_since: string | null;
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
  /** Symbol -> tag names, for the watchlist's view-only grouping/labeling
   *  (v85 R7-03, spec D35). `data/watchlist.json` is read by the bot on every
   *  scan; a tag is a pure UI concern that must never reach it, so it lives
   *  here instead -- one flat key, since there is no per-table axis to it.
   *  Read/written via `ui/watchlist-prefs.ts`, consumed by R7-05. */
  watchlistTags?: Record<string, string[]>;
  /** v85 D40 (R9-05) -- which measure the Performance tab's strategy table
   *  and horizon bars are sorted/sized by. ExpR by default: "which is
   *  better per shot" is the question this app's edge priorities rank
   *  first (CLAUDE.md), and a fresh session should open on that answer. */
  analyticsMeasure?: 'exp_r' | 'total_r' | 'win_rate';
  /** v85 D41 (R9-06) -- whether the Performance tab's Breakdowns band is
   *  expanded. Collapsed (absent/false) by default: the first screen is
   *  the KPI row and equity curve, not the histograms below it. */
  analyticsBreakdownsOpen?: boolean;
  analyticsUnit?: AnalyticsUnit;
  analyticsScope?: Partial<BookScope>;
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
  /** Provenance is nullable where the deployed container has no Git range. */
  provenance?: {
    commit_range: string | null;
    commits: number | null;
    spec: string | null;
    changelog: string[];
  };
  telemetry?: {
    uptime_pct: number | null;
    error_rate: number | null;
    median_scan_sec: number | null;
    n_days: number | null;
    source: 'marker' | 'backfill';
  };
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

/* -- calendar ----------------------------------------------------------- */

/** One day cell. `net_pnl_amount` and `net_r` are null when nothing on that
 *  day had a computable figure -- which is NOT the same as a flat $0 day,
 *  and the grid must render the two differently. */
export interface CalendarDay {
  date: string;
  net_pnl_amount: number | null;
  net_r: number | null;
  trade_count: number;
  win_rate: number | null;
}

/** The visible month's pooled figures. Same fields as a day, minus the
 *  date -- a month total carrying a `date` invites reading it as a day. */
export interface CalendarTotals {
  net_pnl_amount: number | null;
  net_r: number | null;
  trade_count: number;
  win_rate: number | null;
}

export interface CalendarWeekday {
  weekday: string;
  avg_pnl_amount: number | null;
  avg_r: number | null;
  win_rate: number | null;
  trade_count: number;
}

export interface CalendarStreak {
  direction: string | null;
  days: number;
}

export interface CalendarFilters {
  strategies: string[];
  horizons: string[];
}

/** One row in the day drawer: the trade record joined with its journal
 *  entry. The journal half (`mfe_r`, `mae_r`, `exit_efficiency`, `tags`,
 *  `auto_lesson`) is absent for an unjournaled trade. */
export interface CalendarTrade {
  trade_id: string;
  /** Present for plan-backed trades; the Trades detail route keys on it. */
  plan_id: string | null;
  opened_at: string | null;
  ticker: string;
  strategy: string;
  horizon: string | null;
  direction: string | null;
  day: string;
  closed_at: string | null;
  outcome: string | null;
  pnl_amount: number | null;
  r_multiple: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  exit_efficiency: number | null;
  tags: string[];
  auto_lesson: string | null;
  /** A scaled-out position is one row per realized leg, each on the day
   *  that leg closed -- the same split the Trades table makes (v79), so a
   *  banked TP1 partial counts on its own day. 0/1 for an unsplit trade.
   *  `leg_total` includes a runner that is still open. A leg is counted
   *  as an individual trade: its `outcome` and `r_multiple` are the leg's
   *  own, and the legs' `pnl_amount` sum to the trade's realized total. */
  leg_index: number;
  leg_total: number;
  /** v165 D1 -- read from the leg part itself, never re-derived. Every
   *  figure is null when its input is missing (never 0). */
  entry_price: number | null;
  /** The leg's own exit for a leg row, the trade exit for a whole trade. */
  exit_price: number | null;
  /** The final recorded stop (a trailed or break-even runner's stop moved). */
  stop_price: number | null;
  tp1: number | null;
  tp2: number | null;
  /** Leg-scaled for a leg row. */
  shares: number | null;
  /** Null when either stamp is missing or the close precedes the open. */
  held_hours: number | null;
  /** Signed by direction: a short that fell is positive. Null on a missing or zero entry. */
  return_pct: number | null;
  /** One of metrics `EXIT_REASONS` (tp1, runner_tp2, runner_trail, runner_be,
   *  stop, scratch, timeout, reversed, other). */
  exit_reason: string;
}

/** `days`/`totals` are the requested month; `day_of_week`, `best_day`,
 *  `worst_day` and `streak` are all of history under the same filter --
 *  a weekday average drawn from one month would be 4-5 observations. */
export interface PnlCalendar {
  /** Instant the server composed this filtered calendar response. */
  as_of: string;
  month: string;
  days: CalendarDay[];
  totals: CalendarTotals;
  day_of_week: CalendarWeekday[];
  best_day: CalendarDay | null;
  worst_day: CalendarDay | null;
  streak: CalendarStreak;
  filters: CalendarFilters;
}

export interface CalendarDayTrades {
  /** Instant the server composed this selected-day drill-down. */
  as_of: string;
  date: string;
  trades: CalendarTrade[];
  /** Summary fields are composed from exactly the same filtered rows as
   *  `trades`, so the pane cannot disagree with its drill-down list. */
  trade_count: number;
  winners: number;
  losers: number;
  total_r: number | null;
  total_ccy: number | null;
  win_rate: number | null;
  avg_trade_r: number | null;
  worst_drawdown_r: number | null;
  contributors: Array<{ ticker: string | null; r: number }>;
  detractors: Array<{ ticker: string | null; r: number }>;
  /** v165 D2 -- this day against the OTHER trading days under the filter. */
  context: DayContext;
  /** v165 D3 -- exactly the rows in `trades`, grouped four ways. */
  breakdown: DayBreakdown;
}

/** A difference from a reference day. Null when either side has no figure. */
export interface DayDelta {
  pnl_amount: number | null;
  r: number | null;
}

/** v165 D2. `percentile` is null below 20 other trading days (the page
 *  says why with `history_days`); the day is never in its own reference set. */
export interface DayContext {
  percentile: number | null;
  /** Other trading days with a non-null net P&L. */
  history_days: number;
  vs_avg_day: DayDelta;
  vs_weekday_avg: DayDelta;
}

/** One group of a day's rows. `win_rate` is 0-100 and null for a group with
 *  no decided rows; a null key arrives as `"unknown"`. */
export interface DayBreakdownRow {
  key: string;
  n: number;
  pnl_amount: number | null;
  r: number | null;
  win_rate: number | null;
}

export type DayBreakdownDimension = 'strategy' | 'horizon' | 'direction' | 'exit_reason';

/** Each dimension sorted by P&L descending, nulls last. */
export type DayBreakdown = Record<DayBreakdownDimension, DayBreakdownRow[]>;

export interface SparkClose {
  date: string;
  close: number;
}

/** v165 D4. Daily closes from 3 bars before entry to at most 3 bars after
 *  the exit bar (`exit_bar` indexes `closes`; later bars are context, drawn
 *  dimmed). Ticks are the recorded prices -- all null when entry no longer
 *  sits on the bars. `stale`: the cache ends before the exit day. */
export interface SparkSeries {
  closes: SparkClose[];
  exit_bar: number;
  last_bar: string;
  stale: boolean;
  entry: number | null;
  stop: number | null;
  tp1: number | null;
  tp2: number | null;
  exit: number | null;
  exit_date: string;
}

/** Keyed `"<trade_id>:<leg_index>"`. A null value: no cached bars (or a
 *  spot metal); a missing key: the row was past the 50-row cap. */
export interface CalendarDaySparklines {
  as_of: string;
  date: string;
  truncated: boolean;
  series: Record<string, SparkSeries | null>;
}

/* -- live tape ---------------------------------------------------------- */

/** One Lane B tile. `price`/`change_pct` are null when the feed had no answer
 *  for this symbol — a different fact from a flat move, and rendered
 *  differently, so a flagged name never silently vanishes from the tape. */
export interface TapeRow {
  symbol: string;
  price: number | null;
  change_pct: number | null;
  /** Exactly one context, or null. A position outranks a plan, which outranks
   *  an earnings date — the server resolves the precedence. */
  context_kind: 'position' | 'plan' | 'earnings' | null;
  context_label: string | null;
  /** 0 position, 1 plan, 2 neither. The client sorts on this so the ordering
   *  rule lives in one place. */
  sort_rank: number;
}

export interface TapeResponse {
  /** ISO-8601 UTC instant the server composed this answer at. Rendered in the
   *  pinned end-cap; never inside the moving track. */
  as_of: string;
  rows: TapeRow[];
}
