import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, num, rMultiple } from '../../ui/format';

export const NEUTRAL_R_BAND = 0.1;
export type Tone = 'pos' | 'neg' | null;
export type StatusGroup = 'closed' | 'open' | 'pending' | 'unfilled';

export function outcomeTone(r: number | null): Tone {
  if (r === null || Math.abs(r) < NEUTRAL_R_BAND) return null;
  return r > 0 ? 'pos' : 'neg';
}

/** Normalize over the settled fractions; an unfinished runner has no exit. */
export function averageExit(legs: readonly Leg[], exitPrice: number | null): number | null {
  let weightedPrice = 0;
  let totalFraction = 0;
  for (const leg of legs) {
    if (leg.fraction === null || leg.fraction <= 0 || leg.exitPrice === null) continue;
    weightedPrice += leg.fraction * leg.exitPrice;
    totalFraction += leg.fraction;
  }
  return totalFraction > 0 ? weightedPrice / totalFraction : exitPrice;
}

export function statusGroup(status: string | null, exitPrice: number | null): StatusGroup {
  switch (status?.trim().toUpperCase()) {
    case 'CLOSED': return 'closed';
    case 'ACTIVE':
    case 'PARTIAL': return 'open';
    case 'PENDING': return 'pending';
    default: return exitPrice !== null ? 'closed' : 'unfilled';
  }
}

export function sideLabel(direction: string | null): 'Long' | 'Short' | null {
  switch (direction?.trim().toLowerCase()) {
    case 'bullish':
    case 'long': return 'Long';
    case 'bearish':
    case 'short': return 'Short';
    default: return null;
  }
}

export function orderWording(
  entryType: string | null, direction: string | null, price: number | null,
): string {
  if (entryType === null) return ABSENT;
  const side = sideLabel(direction);
  if (entryType === 'market') return side ? `Market (${side.toLowerCase()})` : 'Market';
  if (entryType === 'stop_entry' || entryType === 'limit') {
    const action = side === 'Long' ? 'Buy' : 'Sell';
    const order = entryType === 'stop_entry' ? 'stop' : 'limit';
    const label = side ? `${action} ${order}` : `${order === 'stop' ? 'Stop' : 'Limit'} entry`;
    return `${label} ${num(price)}`;
  }
  return `${entryType} ${num(price)}`;
}

export function pctFrom(from: number | null, to: number | null): number | null {
  if (from === null || to === null || from === 0) return null;
  return (to - from) / from * 100;
}

export function legRsLine(legs: readonly Leg[]): string | null {
  const settled = legs.filter((leg) => leg.r !== null);
  return settled.length >= 2 ? settled.map((leg) => rMultiple(leg.r)).join(' / ') : null;
}

export function lastHistoryReason(history: readonly StatusEvent[]): string | null {
  for (let index = history.length - 1; index >= 0; index--) {
    const reason = history[index].reason?.trim();
    if (reason) return reason;
  }
  return null;
}

/** Date-only ISO inputs use JavaScript's UTC interpretation. */
export function daysUntil(iso: string | null, now: number): number | null {
  if (iso === null) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.ceil((then - now) / 86_400_000));
}
