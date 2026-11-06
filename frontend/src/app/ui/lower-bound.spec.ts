import { describe, expect, it } from 'vitest';

import { availabilityReason, lowerBoundLabel, unavailableLabel } from './lower-bound';

describe('lowerBoundLabel', () => {
  it.each([
    [0, null],
    [1, '≥ $1,200, 1 position unpriced'],
    [3, '≥ $1,200, 3 positions unpriced'],
  ] as const)('labels the figure when %i positions are unpriced', (missing, label) => {
    expect(lowerBoundLabel('$1,200', missing)).toBe(label);
  });
});

describe('unavailableLabel', () => {
  it.each([
    ['insufficient_overlap', 'unavailable: fewer than 2 overlapping bars'],
    ['zero_variance', 'unavailable: benchmark did not move'],
    ['foo', 'unavailable: foo'],
    [null, 'unavailable'],
  ])('explains %s', (reason, label) => {
    expect(unavailableLabel(reason)).toBe(label);
  });
});

describe('availabilityReason', () => {
  it('passes through the zero-variance reason', () => {
    expect(availabilityReason('zero_variance')).toBe('zero_variance');
  });

  it('reports an unavailable domain reason', () => {
    expect(availabilityReason({ state: 'unavailable', checked_at: 'x', reason: 'market_data_unavailable' }))
      .toBe('market_data_unavailable');
  });

  it('reports no reason for an available or omitted domain', () => {
    expect(availabilityReason({ state: 'ok', checked_at: 'x', reason: null })).toBeNull();
    expect(availabilityReason(undefined)).toBeNull();
  });
});
