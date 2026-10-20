import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT } from '../../ui/format';

/** Backend reason vocabulary, with the trade page's wording. */
export const EXIT_REASON_LABELS: Readonly<Record<string, string>> = {
  'tp1': 'TP1',
  'tp1_runner_be': 'Runner at breakeven',
  'runner_be': 'Runner at breakeven',
  'tp1_runner_tp2': 'Runner at T2',
  'runner_tp2': 'Runner at T2',
  'runner_trail': 'Runner trailed',
  'stop': 'Stop',
  'loss': 'Stop',
  'scratch': 'Scratch',
  'timeout': 'Time exit',
  'time_exit': 'Time exit',
  'auto (near-tp stall)': 'Stall exit',
  'stall_exit': 'Stall exit',
  'reversed': 'Reversed',
  'manual_bulk': 'Bulk close',
};

export const GAPPED_R = -1.05;

export function reasonLabel(reason: string | null | undefined): string | null {
  const trimmed = reason?.trim();
  if (!trimmed) return null;
  const key = trimmed.toLowerCase();
  return Object.hasOwn(EXIT_REASON_LABELS, key) ? EXIT_REASON_LABELS[key] : trimmed;
}

export function exitReasonLabel(
  legs: readonly Leg[],
  history: readonly StatusEvent[],
  r: number | null,
): string {
  const labels = legs.map(leg => reasonLabel(leg.reason)).filter(label => label !== null);
  if (!labels.length) {
    const fallback = history.map(event => reasonLabel(event.reason)).filter(label => label !== null).at(-1);
    if (fallback) labels.push(fallback);
  }
  if (!labels.length) return ABSENT;
  const last = labels.length - 1;
  if (labels[last] === 'Stop' && r !== null && r < GAPPED_R) labels[last] += ' (gapped)';
  return labels.join(' + ');
}
