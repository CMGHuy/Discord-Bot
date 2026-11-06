import { DomainAvailability } from '../api/models';

const UNAVAILABLE_REASONS = new Map([
  ['insufficient_overlap', 'fewer than 2 overlapping bars'],
  ['zero_variance', 'benchmark did not move'],
]);

export function lowerBoundLabel(value: string, missing: number): string | null {
  if (missing <= 0) return null;
  return `≥ ${value}, ${missing} position${missing === 1 ? '' : 's'} unpriced`;
}

export function unavailableLabel(reason: string | null | undefined): string {
  if (reason == null) return 'unavailable';
  return `unavailable: ${UNAVAILABLE_REASONS.get(reason) ?? reason}`;
}

export function availabilityReason(
  a: DomainAvailability | 'zero_variance' | null | undefined,
): string | null {
  if (a === 'zero_variance') return a;
  return a?.state === 'unavailable' ? a.reason ?? 'unavailable' : null;
}
