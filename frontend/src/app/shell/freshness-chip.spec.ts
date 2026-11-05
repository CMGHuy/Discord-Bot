import { describe, expect, it } from 'vitest';

import { scanAge } from './freshness-chip';

const NOW = Date.parse('2026-10-27T12:00:00Z');

describe('scanAge (v195 Phase 3)', () => {
  it.each([
    ['2026-10-27T11:59:40Z', 'just now'],
    ['2026-10-27T11:59:00Z', '1m ago'],
    ['2026-10-27T11:48:00Z', '12m ago'],
    ['2026-10-27T11:00:00Z', '1h ago'],
    ['2026-10-27T09:00:00Z', '3h ago'],
    ['2026-10-25T12:00:00Z', '2d ago'],
  ])('%s reads %s', (at, text) => {
    expect(scanAge(at, NOW)).toBe(text);
  });

  it('is null for a missing or unreadable time', () => {
    expect(scanAge(null, NOW)).toBeNull();
    expect(scanAge('', NOW)).toBeNull();
    expect(scanAge('not a date', NOW)).toBeNull();
  });

  it('never reads a time from the future as negative', () => {
    expect(scanAge('2026-10-27T12:05:00Z', NOW)).toBe('just now');
  });
});
