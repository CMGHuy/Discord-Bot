import { describe, expect, it } from 'vitest';

import { deriveActivity } from './activity';

function row(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'p1', leg_index: 0, ticker: 'ASTS', direction: 'bullish',
    status: 'ACTIVE', opened_at: '2026-09-11T15:53:00Z', closed_at: null,
    ...over,
  } as never;
}

describe('activity derivation', () => {
  it('emits an opened event for a filled position', () => {
    const events = deriveActivity([row()]);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ kind: 'opened', ticker: 'ASTS' });
  });

  it('emits both opened and closed for a position that has closed', () => {
    const events = deriveActivity([
      row({ status: 'CLOSED', closed_at: '2026-09-11T16:20:00Z' }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['closed', 'opened']);
  });

  it('emits cancelled rather than closed for a cancelled plan', () => {
    const events = deriveActivity([
      row({ status: 'CANCELLED', opened_at: null, closed_at: '2026-09-11T16:20:00Z' }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['cancelled']);
  });

  it('never emits a TP1 event, because no row carries a TP1 timestamp', () => {
    const events = deriveActivity([
      row({ status: 'PARTIAL', banked_fraction: 0.5, banked_r: 1.0 }),
    ]);
    expect(events.map((e) => e.kind)).toEqual(['opened']);
  });

  it('orders newest first across every row', () => {
    const events = deriveActivity([
      row({ id: 'a', opened_at: '2026-09-11T10:00:00Z' }),
      row({ id: 'b', opened_at: '2026-09-11T14:00:00Z' }),
    ]);
    expect(events.map((e) => e.id)).toEqual(['b:opened', 'a:opened']);
  });

  it('skips rows with no usable timestamp instead of dating them now', () => {
    expect(deriveActivity([row({ opened_at: null, closed_at: null })])).toEqual([]);
  });

  it('caps the feed at the requested limit', () => {
    const rows = Array.from({ length: 20 }, (_, i) =>
      row({ id: `p${i}`, opened_at: `2026-09-11T10:${String(i).padStart(2, '0')}:00Z` }));
    expect(deriveActivity(rows, 6)).toHaveLength(6);
  });
});
