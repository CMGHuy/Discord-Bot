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
export const DEFAULT_TRADE_COLUMNS = [
  'num',
  'status',
  'ticker',
  'now',
  'pnl_pct',
  'held',
  'actions',
];

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
    { key: 'direction', header: 'Direction', value: (row) => text(row.direction) },
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
 */
export const STATUS_CHIPS = [
  { value: 'open', label: 'Open' },
  { value: 'win', label: 'Win' },
  { value: 'loss', label: 'Loss' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'expired', label: 'Expired' },
];
