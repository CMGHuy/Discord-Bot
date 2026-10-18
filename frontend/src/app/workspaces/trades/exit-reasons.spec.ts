import { describe, expect, it } from 'vitest';

import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { EXIT_REASON_LABELS, GAPPED_R, exitReasonLabel, reasonLabel } from './exit-reasons';

/* v166 — the exit-reason label on the trade page's Result strip and the
 * Outcome card's leg rows. SPCX (production trade f48c80e2) closed in two
 * legs, `tp1` then `tp1_runner_be`, for a blended +1.83R. */

const leg = (reason: string | null, r: number | null = null): Leg => ({
  fraction: 0.5, exitPrice: 100, r, reason,
});
const event = (status: string, reason: string | null): StatusEvent => ({
  status, reason, at: '2026-10-01T14:00:00Z',
});

describe('reasonLabel', () => {
  it('maps every spec row to its label', () => {
    const cases: Array<[string, string]> = [
      ['tp1', 'TP1'],
      ['tp1_runner_be', 'Runner at breakeven'], ['runner_be', 'Runner at breakeven'],
      ['tp1_runner_tp2', 'Runner at T2'], ['runner_tp2', 'Runner at T2'],
      ['runner_trail', 'Runner trailed'],
      ['stop', 'Stop'], ['loss', 'Stop'],
      ['scratch', 'Scratch'],
      ['timeout', 'Time exit'], ['time_exit', 'Time exit'],
      ['auto (near-tp stall)', 'Stall exit'], ['stall_exit', 'Stall exit'],
      ['reversed', 'Reversed'],
    ];
    for (const [reason, label] of cases) expect(reasonLabel(reason)).toBe(label);
  });

  it('keeps stall exits apart from time exits', () => {
    expect(reasonLabel('stall_exit')).not.toBe(reasonLabel('time_exit'));
  });

  it('trims and lower-cases before the lookup', () => {
    expect(reasonLabel('TP1')).toBe('TP1');
    expect(reasonLabel('  Runner_TRAIL ')).toBe('Runner trailed');
  });

  it('shows unknown text as written, trimmed', () => {
    expect(reasonLabel(' manual close ')).toBe('manual close');
    expect(reasonLabel(' constructor ')).toBe('constructor');
    expect(reasonLabel('__proto__')).toBe('__proto__');
  });

  it('returns null for no reason at all', () => {
    expect(reasonLabel(null)).toBeNull();
    expect(reasonLabel(undefined)).toBeNull();
    expect(reasonLabel('   ')).toBeNull();
  });

  it('stores only lower-case, trimmed keys', () => {
    for (const key of Object.keys(EXIT_REASON_LABELS)) expect(key).toBe(key.trim().toLowerCase());
  });
});

describe('exitReasonLabel', () => {
  it('joins a two-leg close in leg order (SPCX)', () => {
    const legs = [leg('tp1', 2.23), leg('tp1_runner_be', 1.43)];
    expect(exitReasonLabel(legs, [], 1.83)).toBe('TP1 + Runner at breakeven');
  });

  it('has no "+" for a single leg', () => {
    expect(exitReasonLabel([leg('runner_trail', 0.8)], [], 0.8)).toBe('Runner trailed');
  });

  it('skips a leg with no reason (the open runner)', () => {
    expect(exitReasonLabel([leg('TP1', 1.2), leg(null)], [], 0.6)).toBe('TP1');
  });

  it('labels a stall exit', () => {
    expect(exitReasonLabel([leg('stall_exit', 0.4)], [], 0.4)).toBe('Stall exit');
  });

  it('falls back to the last status_history reason when no leg has one', () => {
    const history = [event('ACTIVE', 'trigger filled'), event('CLOSED', 'time_exit'), event('CLOSED', null)];
    expect(exitReasonLabel([], history, -0.2)).toBe('Time exit');
  });

  it('says "—" with neither legs nor a history reason', () => {
    expect(exitReasonLabel([], [], null)).toBe('—');
    expect(exitReasonLabel([leg(null)], [event('CLOSED', null)], null)).toBe('—');
  });

  it('marks a stop that gapped past -1.05R', () => {
    expect(GAPPED_R).toBe(-1.05);
    expect(exitReasonLabel([leg('stop', -1.4)], [], -1.4)).toBe('Stop (gapped)');
    expect(exitReasonLabel([leg('loss', -1.2)], [], -1.2)).toBe('Stop (gapped)');
  });

  it('does not mark an ordinary stop, or one with no R', () => {
    expect(exitReasonLabel([leg('stop', -1.0)], [], -1.0)).toBe('Stop');
    expect(exitReasonLabel([leg('stop', -1.05)], [], -1.05)).toBe('Stop');
    expect(exitReasonLabel([leg('stop')], [], null)).toBe('Stop');
  });

  it('only marks the last label, and only when it is a stop', () => {
    expect(exitReasonLabel([leg('tp1', 2), leg('stop', -1.3)], [], -1.2)).toBe('TP1 + Stop (gapped)');
    expect(exitReasonLabel([leg('stop', -1.3), leg('scratch', 0)], [], -1.2)).toBe('Stop + Scratch');
  });

  it('marks a history-derived stop too', () => {
    expect(exitReasonLabel([], [event('CLOSED', 'stop')], -1.5)).toBe('Stop (gapped)');
  });
});
