/**
 * Client port of the server's position bar and live R: `row_progress` in
 * swingbot/admin/api_v1/trade_progress.py, `_live_r` in api_v1/trades.py and
 * `unrealized_pnl` in admin/dashboard.py. The contract is
 * tests/fixtures/v248/progress_cases.json, which the Python and the vitest
 * suites both read; change both sides and the fixture together. Pure, no
 * Angular imports, and the arithmetic order is the server's (float parity).
 */
import { PriceKind } from '../api/models';

export type { PriceKind } from '../api/models';

export const PREV_CLOSE_LABEL = 'At prev close (not live)';
const TERMINAL: ReadonlySet<string> = new Set(['CLOSED', 'CANCELLED']);   // trades._TERMINAL

export interface ProgressInput {
  status: string;
  direction: string | null;
  entry: number | null;
  stop_loss: number | null;
  target: number | null;
  bar_kind?: string | null;
  runner_best?: number | null;
  banked_exit_price?: number | null;
  risk_stop?: number | null;
  banked_fraction?: number | null;
  banked_r?: number | null;
}

export interface ProgressFields {
  progress_pct: number | null;
  entry_pct: number | null;
  progress_band: 'toward_stop' | 'neutral' | 'toward_target' | null;
  blink_seconds: number | null;
  status_label: string;
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const clampPct = (v: number): number => Math.max(0, Math.min(100, v));
const noBar = (label: string): ProgressFields =>
  ({ progress_pct: null, entry_pct: null, progress_band: null, blink_seconds: null, status_label: label });

/** Python's `round(x, nd)`: exact binary ties go to even. */
export function pyRound(x: number, nd: number): number {
  const exact = Math.abs(x).toFixed(nd + 21);                 // toFixed reads the exact binary value
  if (!exact.endsWith('5' + '0'.repeat(20))) return Number(x.toFixed(nd));
  const kept = exact.slice(0, -21);                           // truncated to nd decimals
  const even = Number(kept.replace('.', '').slice(-1)) % 2 === 0;
  const mag = even ? Number(kept) : Number((Number(kept) + 10 ** -nd).toFixed(nd));
  return x < 0 ? -mag : mag;
}

export function hasPosition(status: string): boolean {
  return !TERMINAL.has(status) && status !== 'PENDING';
}

/** trade_proximity (core/tracking/performance.py): the band reads the 4-dp proximity, the label the raw one. */
function proximity(direction: string, entry: number, stop: number, target: number, price: number) {
  const risk = Math.abs(entry - stop) || 1e-9;
  const reward = Math.abs(target - entry) || 1e-9;
  const delta = direction === 'bullish' ? price - entry : entry - price;
  const p = Math.max(-1, Math.min(1, delta >= 0 ? delta / reward : delta / risk));
  const label = p >= 0
    ? (p > 0.66 ? 'Near target' : p > 0.15 ? 'Trending toward target' : 'Near entry')
    : (p < -0.66 ? 'Near stop-loss' : p < -0.15 ? 'Trending toward stop' : 'Near entry');
  return { score: pyRound(p, 4), blink: pyRound(2.2 - 1.6 * Math.abs(p), 2), label };
}

function standardBar(row: ProgressInput, price: number | null): ProgressFields {
  const { entry, stop_loss: sl, target: tp } = row;
  if (price === null || !isNum(entry) || !isNum(sl) || !isNum(tp)) return noBar('No live price');
  const direction = row.direction || 'bullish';
  const isBull = direction === 'bullish';
  const span = isBull ? tp - sl : sl - tp;
  if (span <= 0) return noBar('No live price');
  const prox = proximity(direction, entry, sl, tp, price);
  const pos = (isBull ? price - sl : sl - price) / span * 100;
  const ent = (isBull ? entry - sl : sl - entry) / span * 100;
  const band = prox.score > 0.15 ? 'toward_target' : prox.score < -0.15 ? 'toward_stop' : 'neutral';
  return { progress_pct: clampPct(pyRound(pos, 1)), entry_pct: clampPct(pyRound(ent, 1)),
    progress_band: band, blink_seconds: prox.blink, status_label: prox.label };
}

function trailingBar(row: ProgressInput, price: number | null): ProgressFields {
  const stop = row.stop_loss, best = row.runner_best;
  if (price === null || !isNum(stop) || !isNum(best)) return noBar(row.status);
  const isBull = row.direction !== 'bearish';
  const span = isBull ? best - stop : stop - best;
  if (span <= 0) return noBar(row.status);
  const pos = clampPct((isBull ? price - stop : stop - price) / span * 100);
  const leg = row.banked_exit_price;
  const ent = isNum(leg) ? (isBull ? leg - stop : stop - leg) / span * 100 : 0;
  const band = pos >= 66 ? 'toward_target' : pos <= 33 ? 'toward_stop' : 'neutral';
  const label = band === 'toward_stop' ? 'Near trailing stop' : band === 'toward_target' ? 'Near best price' : 'Trailing';
  const urgency = Math.max(0, 1 - pos / 50);
  return { progress_pct: pyRound(pos, 1), entry_pct: clampPct(pyRound(ent, 1)),
    progress_band: band, blink_seconds: pyRound(2.2 - 1.6 * urgency, 2), status_label: label };
}

/** Index Decision 2: a bar drawn from yesterday's close is never urgent. */
function prevCloseBar(fields: ProgressFields, kind: PriceKind): ProgressFields {
  if (kind !== 'prev_close' || fields.progress_pct === null) return fields;
  return { ...fields, progress_band: 'neutral', blink_seconds: null, status_label: PREV_CLOSE_LABEL };
}

export function positionProgress(row: ProgressInput, price: number | null, kind: PriceKind = 'live'): ProgressFields {
  if (row.bar_kind === 'trailing' && !TERMINAL.has(row.status)) return prevCloseBar(trailingBar(row, price), kind);
  if (!hasPosition(row.status)) return noBar(row.status);
  return prevCloseBar(standardBar(row, price), kind);
}

/** metrics.open_trade_r over the one banked leg (null without a risk basis). */
function blendedR(row: ProgressInput, price: number): number | null {
  const { entry, risk_stop: stop, direction, banked_fraction: fraction, banked_r: leg } = row;
  if (!Number.isFinite(price) || !isNum(entry) || !isNum(stop) || !isNum(fraction) || !isNum(leg)) return null;
  if (direction !== 'bullish' && direction !== 'bearish') return null;
  const risk = Math.abs(entry - stop);
  if (risk === 0) return null;
  const move = (direction === 'bullish' ? price - entry : entry - price) / risk;
  return pyRound(fraction * leg + Math.max(0, 1 - fraction) * move, 2);
}

/** trades._live_r: R at `price` against the original stop, blended with a banked TP1 leg. */
export function liveR(row: ProgressInput, price: number): number | null {
  if (row.banked_fraction === null || row.banked_fraction === undefined) {
    const { entry, risk_stop: stop } = row;
    if (!price || !entry || !stop) return null;
    const risk = Math.abs(entry - stop);
    if (risk === 0) return null;
    return pyRound((row.direction === 'bullish' ? price - entry : entry - price) / risk, 2);
  }
  return blendedR(row, price);
}

/** dashboard.unrealized_pnl: the server's pnl_pct for an open row. */
export function livePnl(row: Pick<ProgressInput, 'entry' | 'direction'>, price: number): number | null {
  const entry = row.entry;
  if (!price || !entry) return null;
  const raw = (price - entry) / entry * 100;
  return pyRound(row.direction === 'bullish' ? raw : -raw, 2);
}
