import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConnectionStore } from '../stores/connection.store';
import { MarketStatus } from '../api/models';
import { AgeHint, PAGE_PRICE_WINDOW_S, ageText, marketAgeLabel } from './age-hint';

let marketActive: boolean | null = true;

function render(ageS: number | null, windowS = PAGE_PRICE_WINDOW_S): HTMLElement {
  const f = TestBed.createComponent(AgeHint);
  f.componentRef.setInput('ageS', ageS);
  f.componentRef.setInput('windowS', windowS);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('ageText (v171 D2)', () => {
  it('reads seconds under a minute', () => expect(ageText(12)).toBe('12 s ago'));
  it('rounds seconds', () => expect(ageText(12.6)).toBe('13 s ago'));
  it('reads whole minutes', () => {
    expect(ageText(60)).toBe('1 min ago');
    expect(ageText(119)).toBe('1 min ago');
    expect(ageText(180)).toBe('3 min ago');
  });
  it('reads hours past an hour', () => expect(ageText(7300)).toBe('2 h ago'));
  it('is null for no age, NaN or a negative age', () => {
    expect(ageText(null)).toBeNull();
    expect(ageText(Number.NaN)).toBeNull();
    expect(ageText(-1)).toBeNull();
  });
});

describe('AgeHint (sb-age-hint)', () => {
  beforeEach(() => {
    marketActive = true;
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(),
      { provide: ConnectionStore, useValue: { marketActive: () => marketActive } }] });
  });

  it('renders nothing while the market is closed or its state is unknown, however old', () => {
    marketActive = false;
    expect(render(7200).querySelector('.age-hint')).toBeNull();
    marketActive = null;
    expect(render(7200).querySelector('.age-hint')).toBeNull();
  });

  it('renders nothing inside the window', () => {
    expect(render(60).querySelector('.age-hint')).toBeNull();
    expect(render(14, 15).querySelector('.age-hint')).toBeNull();
  });

  it('renders the age once the price is older than its window', () => {
    expect(render(61).querySelector('.age-hint')?.textContent?.trim()).toBe('1 min ago');
    expect(render(16, 15).querySelector('.age-hint')?.textContent?.trim()).toBe('16 s ago');
  });

  it('renders nothing for an unknown age (pre-v171 rows, flag off)', () => {
    expect(render(null).querySelector('.age-hint')).toBeNull();
  });

  it('is plain text: no spinner, no icon, never the word live', () => {
    const el = render(240);
    expect(el.querySelector('svg, .spinner, sb-icon')).toBeNull();
    expect(el.textContent?.toLowerCase()).not.toContain('live');
    expect(el.querySelector('.age-hint')?.getAttribute('title')).toBe('Price is 4 min old');
  });
});

const NOW = Date.parse('2026-10-31T15:00:00Z'); // a Saturday

describe('marketAgeLabel (v201)', () => {
  const st = (session: MarketStatus['session'], stalled = false): MarketStatus => ({
    session, last_close_at: '2026-10-30T20:00:00Z', stale_price_s: 120,
    heartbeat: { beat_at: null, cadence_s: 30, stalled },
  });

  it('fresh price in regular hours reads its age', () =>
    expect(marketAgeLabel(new Date(NOW - 12_000).toISOString(), NOW, st('regular'))).toEqual({ text: '12 s ago', tone: 'fresh' }));
  it('price older than the regular limit is stale', () =>
    expect(marketAgeLabel(new Date(NOW - 180_000).toISOString(), NOW, st('regular')).tone).toBe('stale'));
  it('closed market reads last close, not stale', () =>
    expect(marketAgeLabel('2026-10-30T19:59:58Z', NOW, st('closed'))).toEqual({ text: 'last close · Fri 16:00 ET', tone: 'closed' }));
  it('closed market with a price older than the close shows its own time', () =>
    expect(marketAgeLabel('2026-10-28T19:40:00Z', NOW, st('closed'))).toEqual({ text: 'as of Wed 15:40 ET', tone: 'closed' }));
  it('stalled feed wins over closed', () =>
    expect(marketAgeLabel('2026-10-30T19:59:58Z', NOW, st('closed', true)).tone).toBe('stalled'));
  it('no as-of gives no text', () => expect(marketAgeLabel(null, NOW, st('regular')).text).toBeNull());
  it('no status yet reads the age, fresh', () =>
    expect(marketAgeLabel(new Date(NOW - 5_000).toISOString(), NOW, null)).toEqual({ text: '5 s ago', tone: 'fresh' }));
});

describe('marketAgeLabel snapshot', () => {
  const status = (session: MarketStatus['session'], stalled = false): MarketStatus => ({
    session, last_close_at: '2026-10-30T20:00:00Z', stale_price_s: 120, stale_snapshot_s: 600,
    heartbeat: { beat_at: null, cadence_s: 30, stalled },
  });
  const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
  const snap = (computedAt: string | null, staleInputs = false) =>
    ({ kind: 'snapshot' as const, computedAt, staleInputs });

  it('takes snapshot age from computed_at, regardless of the input date', () =>
    expect(marketAgeLabel('2026-10-28', NOW, status('regular'), snap(ago(180))))
      .toEqual({ text: '3 min ago', tone: 'fresh' }));
  it('uses the snapshot age limit', () =>
    expect(marketAgeLabel(null, NOW, status('regular'), snap(ago(700))).tone).toBe('stale'));
  it('flags stale inputs even for a recent snapshot', () =>
    expect(marketAgeLabel(null, NOW, status('extended'), snap(ago(5), true)).tone).toBe('stale'));
  it('shows the last close when built after the close', () =>
    expect(marketAgeLabel(null, NOW, status('closed'), snap('2026-10-30T21:10:00Z')))
      .toEqual({ text: 'as of last close · Fri 16:00 ET', tone: 'closed' }));
  it('shows its own time as stale when built before the close', () =>
    expect(marketAgeLabel(null, NOW, status('closed'), snap('2026-10-30T19:00:00Z')))
      .toEqual({ text: 'as of Fri 15:00 ET', tone: 'stale' }));
  it('flags stale inputs even when built after the close', () =>
    expect(marketAgeLabel(null, NOW, status('closed'), snap('2026-10-30T21:10:00Z', true)).tone).toBe('stale'));
  it('gives a stalled heartbeat priority over stale inputs', () =>
    expect(marketAgeLabel(null, NOW, status('regular', true), snap(ago(5), true)).tone).toBe('stalled'));
  it('shows no age when computed_at is null', () =>
    expect(marketAgeLabel('2026-10-28', NOW, status('regular'), snap(null)))
      .toEqual({ text: null, tone: 'fresh' }));
});
