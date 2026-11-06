import { describe, expect, it } from 'vitest';

import { parseScanEventProgress } from './scan-event-progress';

/* v206 P1-c — the `scan` frame's payload, validated.
 *
 * The broker sends `{seq, at, progress: {running, progress}}` on a `scan`
 * event when its read worked, and a thin `{seq, at}` when it did not. A
 * malformed payload is treated as absent: the connection store then falls
 * back to fetching `/system/scan`, which is always right, instead of
 * patching half a record into the progress strip.
 */

const RECORD = {
  at: '2026-11-05T15:40:00+00:00', pct: 66, stage: 'analyzing',
  current_ticker: 'AAPL', done: 50, total: 100, qualifying_found: 3,
};

const frame = (progress: unknown) => ({ seq: 7, at: '2026-11-05T15:40:00+00:00', progress });

const without = (key: keyof typeof RECORD): Record<string, unknown> => {
  const copy: Record<string, unknown> = { ...RECORD };
  delete copy[key];
  return copy;
};

describe('parseScanEventProgress', () => {
  it('reads a running scan and its record', () => {
    expect(parseScanEventProgress(frame({ running: true, progress: RECORD }))).toEqual({
      running: true, progress: RECORD,
    });
  });

  it('reads an idle scan with no record as running false, progress null', () => {
    expect(parseScanEventProgress(frame({ running: false, progress: null }))).toEqual({
      running: false, progress: null,
    });
  });

  it('accepts a record whose current ticker is null', () => {
    const record = { ...RECORD, current_ticker: null };
    expect(parseScanEventProgress(frame({ running: true, progress: record }))?.progress)
      .toEqual(record);
  });

  it('is null for a thin frame with no progress key (failed read, older server)', () => {
    expect(parseScanEventProgress({ seq: 7, at: '2026-11-05T15:40:00+00:00' })).toBeNull();
  });

  it('is null for progress: null, which the server never sends', () => {
    expect(parseScanEventProgress(frame(null))).toBeNull();
  });

  it.each([
    ['a null frame', null],
    ['a string frame', 'scan'],
    ['a number frame', 7],
    ['an array frame', [frame({ running: true, progress: RECORD })]],
    ['undefined', undefined],
  ])('is null for %s', (_label, input) => {
    expect(parseScanEventProgress(input)).toBeNull();
  });

  it.each([
    ['running missing', { progress: RECORD }],
    ['running as a string', { running: 'true', progress: RECORD }],
    ['progress missing', { running: true }],
    ['progress as a string', { running: true, progress: '66%' }],
    ['progress as an array', { running: true, progress: [RECORD] }],
  ])('is null when %s', (_label, payload) => {
    expect(parseScanEventProgress(frame(payload))).toBeNull();
  });

  it.each([
    ['at missing', without('at')],
    ['pct as a string', { ...RECORD, pct: '66' }],
    ['pct not finite', { ...RECORD, pct: Number.POSITIVE_INFINITY }],
    ['stage as a number', { ...RECORD, stage: 3 }],
    ['current_ticker as a number', { ...RECORD, current_ticker: 1 }],
    ['current_ticker missing', without('current_ticker')],
    ['done missing', without('done')],
    ['total as null', { ...RECORD, total: null }],
    ['qualifying_found as a string', { ...RECORD, qualifying_found: '3' }],
  ])('is null, never partial, when the record has %s', (_label, record) => {
    expect(parseScanEventProgress(frame({ running: true, progress: record }))).toBeNull();
  });

  it('keeps only the known fields, so nothing extra reaches the store', () => {
    const parsed = parseScanEventProgress(frame({
      running: true, extra: 'x', progress: { ...RECORD, note: 'server-only' },
    }));
    expect(parsed).toEqual({ running: true, progress: RECORD });
    expect(Object.keys(parsed!.progress!).sort()).toEqual(Object.keys(RECORD).sort());
  });
});
