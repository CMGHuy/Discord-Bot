import { TradeRow } from '../../api/models';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { age, held, heldPrecise, num, signed, text } from '../../ui/format';

/**
 * The columns the Trades list shows by default — spec 3 Decision 2.
 *
 * A short set, not eighteen. The old dashboard showed everything at once and
 * became unreadable; the remaining fields live in row expansion and are each
 * individually re-addable through the column picker, so nothing is lost, it is
 * merely not shouted.
 *
 * 'held' sits immediately left of 'opened_at' in both densities: how long a
 * position has been (or was) held is read together with when it started, and
 * the pair reads as one span rather than as two unrelated facts at opposite
 * ends of the row. It was previously in Full only, which meant the default
 * view could not answer "how long has this been running" at all.
 */
export const COMPACT_COLUMNS = [
  'num',
  'status',
  'ticker',
  'confidence_level',
  'direction',
  'now',
  'plan',
  'pnl_pct',
  'r_multiple',
  'held',
  'opened_at',
  'closed_at',
];

/**
 * Full adds what compact folds away: the risk/reward numbers, the setup
 * (strategy, horizon), and the realised amount. It is not "every column" —
 * the picker still exists for that.
 */
export const FULL_COLUMNS = [
  'num',
  'status',
  'ticker',
  'confidence_level',
  'direction',
  'now',
  'plan',
  'risk_reward',
  'r_multiple',
  'strategy',
  'horizon',
  'pnl_pct',
  'realized_pnl_amount',
  'held',
  'opened_at',
  'closed_at',
];

/**
 * Columns the table pins: present in every density, absent from the picker,
 * immovable by drag or keyboard.
 *
 * Row actions are not a column the user chose to show — they are how a row is
 * operated. Hiding them would leave a table you can read and not use.
 */
export const PINNED_COLUMNS = ['actions'];

/** Persistence keys for the column preferences. Stable across releases.
 *
 *  Two ids over one set of definitions: the Dashboard and Trades render the
 *  same columns and must not share an arrangement. They are read for
 *  different reasons — one at a glance, one in depth — so a layout that suits
 *  one is not a layout that suits the other. */
export const TRADES_TABLE_ID = 'trades';
export const DASHBOARD_TABLE_ID = 'dashboard';

/**
 * Every column the Trades table can show.
 *
 * `key` doubles as the sort field for anything marked sortable, so those keys
 * must match the API's `TRADE_SORTABLE` set exactly — an unsortable field is a
 * 400 from the collection endpoint, not a silent no-op. The columns that are
 * merely displayable carry no `sortable`, which is why several obvious ones
 * (strategy, horizon, tier) are not clickable: the server does not sort by
 * them, and offering a control that 400s would be worse than not offering it.
 */
export function tradeColumns(): ColumnDef<TradeRow>[] {
  return [
    // Rendered by the workspace as a link to the detail view — the keyboard
    // route into a row, since row clicks are mouse-only by design.
    { key: 'num', header: '#', width: '3rem' },
    { key: 'status', header: 'Status', sortable: true },
    { key: 'ticker', header: 'Ticker', value: (row) => row.ticker, sortable: true },
    { key: 'now', header: 'Now', value: (row) => num(row.current_price), numeric: true },
    { key: 'pnl_pct', header: 'P&L %', numeric: true, sortable: true },
    { key: 'held', header: 'Held', value: (row) => held(row.held_hours), numeric: true, sortable: true },
    { key: 'actions', header: '', width: '1px' },

    // Not in COMPACT_COLUMNS/FULL_COLUMNS or the picker -- the Dashboard's
    // Closed group opts into this one explicitly, inserted ahead of
    // 'opened_at' (see dashboard.ts's `closedVisible`). `held` above already
    // covers a LIVE position's age at a glance; a CLOSED position's hold
    // period is fixed rather than ticking, so the day/hour/minute precision
    // here is signal rather than noise the way it would be on an open row.
    { key: 'hold', header: 'Hold', value: (row) => heldPrecise(row.held_hours), numeric: true },

    /* -- individually re-addable through the column picker ---------------- */
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true, sortable: true },
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true },
    { key: 'target', header: 'Target', value: (row) => num(row.target), numeric: true },
    { key: 'risk_reward', header: 'R:R', value: (row) => num(row.risk_reward), numeric: true },
    // Rich cell (trades.ts's rMultipleCell) adds sb-magnitude beneath; value
    // is the fallback used wherever cell isn't wired up. v54 Task 28: signed()
    // not rMultiple() -- the header already names the unit ('R'), so the cell
    // does not repeat it down every row.
    { key: 'r_multiple', header: 'R', value: (row) => signed(row.r_multiple), numeric: true, sortable: true },
    { key: 'strategy', header: 'Strategy', value: (row) => text(row.strategy) },
    { key: 'horizon', header: 'Horizon', value: (row) => text(row.horizon) },
    { key: 'direction', header: 'Direction', width: '3.5rem' },
    // Entry, target and stop in one cell (SR8). Not sortable: there is no
    // single field behind it, and `sort=plan` is a 400 from the collection
    // endpoint. The three keys remain as separate columns for the picker.
    { key: 'plan', header: 'Plan', width: '12rem' },
    { key: 'tier', header: 'Tier' },
    { key: 'confidence_level', header: 'Confidence' },
    { key: 'shares', header: 'Shares', value: (row) => num(row.shares, 0), numeric: true },
    { key: 'position_value', header: 'Deployed', value: (row) => num(row.position_value), numeric: true },
    {
      key: 'realized_pnl_amount',
      header: 'Realised',
      value: (row) => num(row.realized_pnl_amount),
      numeric: true,
      sortable: true,
    },
    { key: 'exit_price', header: 'Exit', value: (row) => num(row.exit_price), numeric: true, sortable: true },
    { key: 'opened_at', header: 'Opened', sortable: true },
    { key: 'closed_at', header: 'Closed', sortable: true },
    { key: 'origin', header: 'Origin', value: (row) => text(row.origin) },

    /* -- SR53: the plan's own columns ---------------------------------------
     *
     * These are what made the old plans board readable for a plan that has not
     * filled. A PENDING row has no `entry`, no `opened_at` and no `held_hours`
     * — all three describe an execution — so without these it is a row of em
     * dashes. Picker-addable rather than default: they are empty on a closed
     * position, which is most of the table most of the time. */

    // The stop-entry price still being waited on. `plan` (SR8) falls back to it
    // when there is no fill, so this column is for reading the two side by
    // side rather than for finding out there is a trigger at all.
    { key: 'trigger_price', header: 'Trigger', value: (row) => num(row.trigger_price), numeric: true },
    { key: 'target2', header: 'Target 2', value: (row) => num(row.target2), numeric: true },
    // The plans board's Age column. Sorts on the plan's creation, which is the
    // only time an unfilled plan has.
    {
      key: 'created_at',
      header: 'Created',
      value: (row) => (row.created_at ? age(row.created_at) : null),
      sortable: true,
    },
    // 0-100 composite from analytics.rank — badge, quality, regime, freshness.
    // Zero decimals: it is a ranking, and the third digit of a composite is
    // precision the inputs do not have.
    {
      key: 'follow_score',
      header: 'Follow',
      value: (row) => num(row.follow_score, 0),
      numeric: true,
      sortable: true,
    },
  ];
}

/**
 * Status filters, as a chip row.
 *
 * **Chips, not tabs.** Tabs would reintroduce the "separate page per state"
 * model that collapsing Plans, Journal and the two dashboard tables into one
 * Trades workspace exists to abolish — spec v14 Decision 4 says so outright.
 *
 * **Two parameters, one row.** `status` and `outcome` are different questions
 * — `status` is where the position is in its lifecycle, `outcome` is how it
 * ended — and win and loss are indistinguishable by status, because both
 * normalise to CLOSED. So each chip names the parameter it filters on, and
 * only one is ever set at a time.
 *
 * NG54: before that, every chip sent `status` and five of the six matched
 * nothing. `status=win` was querying a field that never holds "win", and
 * `status=cancelled` was case-mismatched against CANCELLED. It read as "no
 * trades in that state" rather than as a bug, which is why it survived to
 * the acceptance gate.
 */
export interface StatusChip {
  value: string;
  label: string;
  /** Which query parameter this chip drives. */
  param: 'status' | 'outcome';
}

export const STATUS_CHIPS: StatusChip[] = [
  // Pending was missing entirely, which left the old /plans page — whose
  // whole purpose was listing un-filled plans — with no equivalent here.
  { value: 'PENDING', label: 'Pending', param: 'status' },
  // `open` is a server-side alias for ACTIVE-or-PARTIAL. One chip, because
  // "is my position live" is one question.
  { value: 'open', label: 'Open', param: 'status' },
  // The lifecycle's other end, and the only one that was unreachable: Win
  // and Loss between them cover only the trades that HAVE an outcome, so a
  // scratch (closed at break-even, outcome neither) matched no chip at all,
  // and there was no way to ask "everything that is done" in one click --
  // which is the Dashboard's own Closed group, whose "All N →" link lands
  // here on exactly this filter. Exact-match on the normalised status, the
  // same field `_filter_by_status` compares case-insensitively, so it also
  // picks up the legacy v1 rows that map to CLOSED.
  { value: 'CLOSED', label: 'Closed', param: 'status' },
  { value: 'win', label: 'Win', param: 'outcome' },
  { value: 'loss', label: 'Loss', param: 'outcome' },
  { value: 'CANCELLED', label: 'Cancelled', param: 'status' },
  { value: 'EXPIRED', label: 'Expired', param: 'status' },
];

/**
 * The URL patch for a chip selection — both parameters, always.
 *
 * Writing both is the point. Setting only the one a chip uses would leave the
 * other behind on a switch: going from Win to Cancelled would navigate to
 * `?outcome=win&status=CANCELLED`, the server would intersect them, and the
 * table would be empty under a chip that looks selected. Passing `null` for
 * an unselected chip is also how "All" clears both.
 */
export function chipQuery(value: string | null): {
  status: string | null;
  outcome: string | null;
} {
  const chip = STATUS_CHIPS.find((c) => c.value === value);
  return {
    status: chip?.param === 'status' ? chip.value : null,
    outcome: chip?.param === 'outcome' ? chip.value : null,
  };
}
