import { TradeRow } from '../../api/models';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { held, num, rMultiple, text } from '../../ui/format';

/**
 * The seven columns the Trades list shows by default — spec 3 Decision 2.
 *
 * Seven, not eighteen. The old dashboard showed everything at once and became
 * unreadable; the other eleven fields live in row expansion and are each
 * individually re-addable through the column picker, so nothing is lost, it is
 * merely not shouted.
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
  'held',
  'realized_pnl_amount',
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

/** Persistence key for the column preference. Stable across releases. */
export const TRADES_TABLE_ID = 'trades';

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

    /* -- individually re-addable through the column picker ---------------- */
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true, sortable: true },
    { key: 'stop_loss', header: 'Stop', value: (row) => num(row.stop_loss), numeric: true },
    { key: 'target', header: 'Target', value: (row) => num(row.target), numeric: true },
    { key: 'risk_reward', header: 'R:R', value: (row) => num(row.risk_reward), numeric: true },
    { key: 'r_multiple', header: 'R', value: (row) => rMultiple(row.r_multiple), numeric: true, sortable: true },
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
