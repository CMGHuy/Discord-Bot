import type { TradeRow } from '../../api/models';
import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, date, dateTime, held, num, pct, rMultiple, share, signed } from '../../ui/format';
import { exitReasonLabel } from './exit-reasons';
import { averageExit, daysUntil, lastHistoryReason, legRsLine, outcomeTone, pctFrom, statusGroup, Tone } from './trade-figures';

export const COST_CAPTION = 'before fees & tax';
export const PAPER_FILLS_LINE = 'Paper fills at plan levels; real fills and slippage may differ.';
export const STALE_FLAG = 'delayed';

export interface StripContext {
  trade: TradeRow;
  legs: readonly Leg[];
  history: readonly StatusEvent[];
  riskPerShare: number | null;
  banked: Leg | null;
  bankedStats: { pct: number; amount: number | null } | null;
  expiresOn: string | null;
  timeExitOn: string | null;
  now: Date;
}

export interface StripIndicator {
  status: string;
  current: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
}

export interface OutcomeTile {
  id: string;
  label: string;
  value: string;
  sub: string | null;
  tone: Tone;
  costCaption: boolean;
  stale: boolean;
  indicator: StripIndicator | null;
}

function tile(id: string, label: string, value: string, extras: Partial<OutcomeTile> = {}): OutcomeTile {
  return { id, label, value, sub: null, tone: null, costCaption: false, stale: false, indicator: null, ...extras };
}

function joined(parts: (string | null)[]): string | null {
  return parts.filter(part => part !== null).join(' · ') || null;
}

function closedTiles(ctx: StripContext): OutcomeTile[] {
  const t = ctx.trade;
  const tone = outcomeTone(t.r_multiple ?? null);
  const risk = t.shares != null && ctx.riskPerShare != null
    ? `1R = $${num(t.shares * ctx.riskPerShare)}` : null;
  return [
    tile('result', 'Result', rMultiple(t.r_multiple), { tone, sub: joined([risk, legRsLine(ctx.legs)]) }),
    tile('pnl', 'P&L', signed(t.realized_pnl_amount), { tone, costCaption: true, sub: `${pct(t.pnl_pct)} on position` }),
    tile('entry-exit', 'Entry → exit', `${num(t.entry)} → ${num(averageExit(ctx.legs, t.exit_price ?? null))}`),
    tile('held', 'Held', held(t.held_hours)),
    tile('exit', 'Exit', exitReasonLabel(ctx.legs, ctx.history, t.r_multiple ?? null)),
  ];
}

function bankedTile(ctx: StripContext): OutcomeTile | null {
  const leg = ctx.banked;
  if (!leg || ctx.trade.status !== 'PARTIAL') return null;
  const stats = ctx.bankedStats;
  const fraction = leg.fraction == null ? null : leg.fraction * 100;
  return tile('banked', 'Banked', `${share(fraction)} @ ${num(leg.exitPrice)}`, {
    tone: outcomeTone(leg.r ?? null), costCaption: true,
    sub: joined([rMultiple(leg.r), stats ? pct(stats.pct) : null, stats ? signed(stats.amount) : null]),
  });
}

function openTiles(ctx: StripContext): OutcomeTile[] {
  const t = ctx.trade;
  const current = t.current_price ?? null;
  const days = daysUntil(ctx.timeExitOn, ctx.now.getTime());
  const stale = t.current_price_stale === true;
  const tiles = [
    tile('price', 'Price', num(current), {
      stale, sub: `to stop ${pct(pctFrom(current, t.stop_loss ?? null))} · to T1 ${pct(pctFrom(current, t.target ?? null))}`,
    }),
    tile('unrealised', 'Unrealised', signed(t.realized_pnl_amount), {
      stale, tone: outcomeTone(t.r_multiple ?? null), costCaption: true,
      sub: `${pct(t.pnl_pct)} ${t.status === 'PARTIAL' ? 'on open shares' : 'on position'}`,
    }),
    tile('progress', 'Progress', ABSENT, { indicator: {
      status: t.status, current, entry: t.entry ?? null, stop: t.stop_loss ?? null, target: t.target ?? null,
    } }),
    tile('held', 'Held', held(t.held_hours), { sub: days === null ? null : `time exit in ${days}d` }),
  ];
  const banked = bankedTile(ctx);
  if (banked) tiles.push(banked);
  return tiles;
}

function pendingTiles(ctx: StripContext): OutcomeTile[] {
  const t = ctx.trade;
  const current = t.current_price ?? null;
  return [
    tile('trigger', 'Trigger', num(t.trigger_price), { sub: current === null ? null
      : `now ${num(current)} · ${pct(pctFrom(current, t.trigger_price ?? null))} to trigger` }),
    tile('distance', 'Distance', t.distance_to_trigger_r == null ? ABSENT : `${num(t.distance_to_trigger_r)}R`),
    tile('expires', 'Expires', date(ctx.expiresOn), { sub: t.bars_to_expiry == null ? null : `${t.bars_to_expiry} bars left` }),
    tile('created', 'Created', dateTime(t.created_at)),
  ];
}

function unfilledTiles(ctx: StripContext): OutcomeTile[] {
  const t = ctx.trade;
  const status = t.status?.toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase()) || ABSENT;
  return [
    tile('status', 'Status', status, { sub: lastHistoryReason(ctx.history) }),
    tile('created', 'Created', dateTime(t.created_at)),
    tile('trigger', 'Trigger', num(t.trigger_price)),
    tile('fill', 'Fill', 'Never filled'),
  ];
}

export function outcomeTiles(ctx: StripContext): OutcomeTile[] {
  const builders = { closed: closedTiles, open: openTiles, pending: pendingTiles, unfilled: unfilledTiles };
  return builders[statusGroup(ctx.trade.status ?? null, ctx.trade.exit_price ?? null)](ctx);
}
