import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  PREV_CLOSE_LABEL, PriceKind, ProgressFields, ProgressInput,
  hasPosition, livePnl, liveR, positionProgress, pyRound,
} from './position-progress';

interface Case {
  name: string;
  row: ProgressInput;
  price: number | null;
  price_kind: PriceKind;
  expected: ProgressFields & { r_multiple: number | null };
}

/** Written by V248-2; tests/admin/test_v248_progress_parity.py reads the same file. */
const CASES: Case[] = JSON.parse(
  readFileSync(join(process.cwd(), '..', 'tests', 'fixtures', 'v248', 'progress_cases.json'), 'utf8'));
const BAR_KEYS = ['progress_pct', 'entry_pct', 'progress_band', 'blink_seconds', 'status_label'] as const;

/** The R `_attach_unrealized_pnl` puts on the row at `price`. */
function shownR(row: ProgressInput, price: number | null): number | null {
  if (price === null || row.entry === null || !hasPosition(row.status)) return null;
  return liveR(row, price);
}

describe('position-progress parity with trade_progress.py (v248)', () => {
  it('reads the 16 shared cases', () => {
    expect(Array.isArray(CASES)).toBe(true);
    expect(new Set(CASES.map((c) => c.name)).size).toBe(16);
  });

  for (const c of CASES) {
    it(c.name, () => {
      const row = structuredClone(c.row);
      const got = positionProgress(row, c.price, c.price_kind);
      expect(Object.keys(got).sort()).toEqual([...BAR_KEYS].sort());
      expect(got).toEqual(Object.fromEntries(BAR_KEYS.map((k) => [k, c.expected[k]])));
      expect(shownR(row, c.price)).toEqual(c.expected.r_multiple);
      expect(row).toEqual(c.row);                                   // pure
    });
  }
});

describe('positionProgress (v248)', () => {
  const bull = CASES.find((c) => c.name === 'bull_live_toward_target')!.row;

  it('a prev-close bar never claims a stop, a target or urgency', () => {
    for (const price of [80, 92, 105, 119, 140]) {
      const got = positionProgress(bull, price, 'prev_close');
      const live = positionProgress(bull, price);
      expect(got).toMatchObject({ progress_band: 'neutral', blink_seconds: null, status_label: PREV_CLOSE_LABEL });
      expect([got.progress_pct, got.entry_pct]).toEqual([live.progress_pct, live.entry_pct]);
    }
  });

  it('defaults to a live price', () =>
    expect(positionProgress(bull, 92).progress_band).toBe('toward_stop'));

  it('a null direction reads as bullish, like the server', () =>
    expect(positionProgress({ ...bull, direction: null }, 110)).toEqual(positionProgress(bull, 110)));

  it('an EXPIRED row is not terminal on the server, so it keeps a bar', () =>
    expect(positionProgress({ ...bull, status: 'EXPIRED' }, 110).progress_pct).toBe(66.7));
});

describe('liveR / livePnl (v248)', () => {
  const row: ProgressInput = { status: 'ACTIVE', direction: 'bullish', entry: 100, stop_loss: 95,
    target: 120, risk_stop: 90, banked_fraction: null, banked_r: null };

  it('measures R against the original stop', () => expect(liveR(row, 110)).toBe(1));
  it('mirrors the short side', () =>
    expect(liveR({ ...row, direction: 'bearish', risk_stop: 110 }, 95)).toBe(0.5));
  it('is null without a risk basis or a price', () => {
    expect(liveR({ ...row, risk_stop: null }, 110)).toBeNull();
    expect(liveR({ ...row, risk_stop: 100 }, 110)).toBeNull();
    expect(liveR(row, 0)).toBeNull();
  });
  it('blends a banked TP1 leg, and is null when the leg has no R', () => {
    const banked = { ...row, banked_fraction: 0.5, banked_r: 2 };
    expect(liveR(banked, 105)).toBe(1.25);
    expect(liveR({ ...banked, banked_r: null }, 105)).toBeNull();
    expect(liveR({ ...banked, direction: 'long' }, 105)).toBeNull();
  });
  it('P&L % follows the direction', () => {
    expect(livePnl(row, 110)).toBe(10);
    expect(livePnl({ entry: 50, direction: 'bearish' }, 45)).toBe(10);
    expect(livePnl({ entry: null, direction: 'bullish' }, 45)).toBeNull();
  });
  it('hasPosition is the server rule', () => {
    expect(['ACTIVE', 'PARTIAL', 'EXPIRED'].map(hasPosition)).toEqual([true, true, true]);
    expect(['PENDING', 'CLOSED', 'CANCELLED'].map(hasPosition)).toEqual([false, false, false]);
  });
});

describe('pyRound (v248)', () => {
  it('rounds like Python, exact ties to even', () => {
    expect(pyRound(0.125, 2)).toBe(0.12);
    expect(pyRound(0.375, 2)).toBe(0.38);
    expect(pyRound(-0.125, 2)).toBe(-0.12);
    expect(pyRound(12.25, 1)).toBe(12.2);
    expect(pyRound(2.675, 2)).toBe(2.67);       // 2.67499999… in binary: not a tie
    expect(pyRound(66.66666, 1)).toBe(66.7);
    expect(pyRound(2.2 - 1.6 * 0.8, 2)).toBe(0.92);
  });
});
