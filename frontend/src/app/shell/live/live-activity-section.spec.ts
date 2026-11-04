import { describe, expect, it } from 'vitest';

import { LiveEvent, LiveEventsMeta } from '../../api/models';
import { activityLine, activityView, missingText, pnlParts } from './live-activity-section';

const NOW = new Date('2026-10-29T13:00:00Z');               // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const event = (over: Partial<LiveEvent> = {}): LiveEvent => ({
  at: ago(6), kind: 'trade_closed', text: 'NVDA closed · TP2', tone: 'positive', ref: '812', pnl: { r: 2.1, amount: 441 }, ...over,
});
const ALERT = event({ kind: 'plan_alerted', text: 'AAPL plan alerted · long', tone: 'info', pnl: null, at: ago(20) });
const meta = (over: Partial<LiveEventsMeta> = {}): LiveEventsMeta => ({ availability: 'ok', as_of: ago(0), missing: [], ...over });

describe('activityLine (spec v202 §4.4)', () => {
  it('appends R, its amount and the paper label to a P&L row', () => {
    expect(activityLine(event())).toBe('NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)');
    expect(activityLine(event(), '$')).toBe('NVDA closed · TP2 · +2.1R (441 $) (paper, pre-cost)');
  });
  it('signs a loss with a true minus and keeps the amount unsigned', () => {
    expect(activityLine(event({ pnl: { r: -1, amount: -210 }, tone: 'negative' }))).toBe('NVDA closed · TP2 · −1.0R (210 €) (paper, pre-cost)');
  });
  it('omits a missing amount, and leaves a row without P&L alone', () => {
    expect(activityLine(event({ pnl: { r: 1, amount: null } }))).toBe('NVDA closed · TP2 · +1.0R (paper, pre-cost)');
    expect(activityLine(ALERT)).toBe('AAPL plan alerted · long');
    expect(pnlParts(null, '€')).toBeNull();
  });
});

describe('missingText', () => {
  it('words the kinds of a failed source', () => {
    expect(missingText(meta({ availability: 'partial', missing: ['tp1_hit', 'paper_filled'] }))).toBe('Some sources unavailable: TP1 hits, paper fills');
    expect(missingText(meta({ availability: 'partial', missing: [] }))).toBe('Some sources unavailable');
    expect(missingText(meta())).toBeNull();
  });
});

describe('activityView (spec v202 §6)', () => {
  it('is loading, then unavailable when the first answer failed or the source is down', () => {
    expect(activityView([], null, true, ago(2), NOW, '€').state).toBe('loading');
    expect(activityView([], null, false, ago(2), NOW, '€').state).toBe('unavailable');
    expect(activityView([], meta({ availability: 'unavailable' }), false, ago(2), NOW, '€').state).toBe('unavailable');
  });
  it('reads Nothing yet today only with no rows and a recent scan', () => {
    expect(activityView([], meta(), false, ago(2), NOW, '€')).toMatchObject({ state: 'ok', quiet: true, scanWarning: null });
    expect(activityView([ALERT], meta(), false, ago(2), NOW, '€').quiet).toBe(false);
  });
  it('never reads a missed scan as a quiet day', () => {
    expect(activityView([], meta(), false, ago(300), NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan since 09:00 (5h ago)' });
    expect(activityView([ALERT], meta(), false, ago(300), NOW, '€').scanWarning).toBe('No scan since 09:00 (5h ago)');
    expect(activityView([], meta(), false, null, NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan yet' });
  });
  it('builds a row per event with its time, tone and P&L parts', () => {
    expect(activityView([event()], meta(), false, ago(2), NOW, '€').rows).toEqual([{
      key: `${ago(6)}|trade_closed|812`, time: '13:54 · 6m ago', text: 'NVDA closed · TP2', tone: 'positive',
      pnl: { r: '+2.1R', amount: '441 €' }, line: 'NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)',
    }]);
  });
});
