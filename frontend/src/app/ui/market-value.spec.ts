import { Component, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MarketStatus } from '../api/models';
import { LiveValuesStore } from '../stores/live-values.store';
import { CLOCK } from './clock';
import { MarketValue, errorIsCurrent } from './market-value';

const NOW = Date.parse('2026-10-30T15:00:00Z'); // a Friday, regular hours
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const regular: MarketStatus = {
  session: 'regular', last_close_at: '2026-10-29T20:00:00Z', stale_price_s: 120, stale_snapshot_s: 600,
  heartbeat: { beat_at: null, cadence_s: 30, stalled: false },
};

@Component({
  imports: [MarketValue],
  template: `<sb-market-value [errorOnly]="eo" [asOf]="a" [refreshing]="r" [error]="e" [errorAt]="errAt" [kind]="kind" [computedAt]="computedAt" [staleInputs]="staleInputs">187.42</sb-market-value>`,
})
class Host {
  a: string | null = ago(12);
  r = false;
  e: string | null = null;
  errAt: string | null = null;
  eo = false;
  kind: 'price' | 'snapshot' = 'price';
  computedAt: string | null = null;
  staleInputs = false;
}

describe('sb-market-value (v201)', () => {
  let clock: WritableSignal<number>;
  let status: WritableSignal<MarketStatus>;

  beforeEach(() => {
    clock = signal(NOW);
    status = signal(regular);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: CLOCK, useValue: clock },
        { provide: LiveValuesStore, useValue: { status } },
      ],
    });
  });

  function render(init: Partial<Host> = {}) {
    const f = TestBed.createComponent(Host);
    Object.assign(f.componentInstance, init);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('errorOnly shows a current error without the age or a separator (v248)', () => {
    const el = render({ eo: true, a: ago(840), e: 'no quote', errAt: ago(30) });
    expect(el.querySelector('.mv-age')).toBeNull();
    expect(err(el)?.textContent?.trim()).toBe('refresh failed: no quote');
  });

  it('errorOnly with no current error renders nothing (v248)', () => {
    const el = render({ eo: true, a: ago(12), e: 'no quote', errAt: ago(5) });
    expect(el.querySelector('.mv-age')).toBeNull();
    expect(err(el)).toBeNull();
    expect((el.querySelector('sb-market-value') as HTMLElement).classList).toContain('mv-empty');
  });

  it('shows the value and its age', () => {
    const el = render();
    expect(el.textContent).toContain('187.42');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('12 s ago');
  });

  it('puts the age on the price baseline: meta baseline-aligned, spinner centred out of it', () => {
    const el = render({ r: true });
    expect(getComputedStyle(el.querySelector('.mv-meta') as HTMLElement).alignItems).toBe('baseline');
    expect(getComputedStyle(el.querySelector('.mv-meta sb-spinner') as HTMLElement).alignSelf).toBe('center');
  });

  it('keeps the meta baseline-aligned with no spinner and no age', () => {
    const el = render({ a: null, r: false });
    expect(el.querySelector('.mv-age')).toBeNull();
    expect(getComputedStyle(el.querySelector('.mv-meta') as HTMLElement).alignItems).toBe('baseline');
  });

  it('takes no space when there is nothing to show (no as-of, spinner or error)', () => {
    const el = render({ a: null, r: false, e: null });
    const host = el.querySelector('sb-market-value') as HTMLElement;
    expect(host.classList).toContain('mv-empty');
    expect(getComputedStyle(host).display).toBe('none');
  });

  it('stays visible with no as-of while refreshing or failed', () => {
    for (const init of [{ a: null, r: true }, { a: null, e: 'timeout' }]) {
      const host = render(init).querySelector('sb-market-value') as HTMLElement;
      expect(host.classList).not.toContain('mv-empty');
      expect(getComputedStyle(host).display).not.toBe('none');
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(),
        { provide: CLOCK, useValue: clock }, { provide: LiveValuesStore, useValue: { status } }] });
    }
  });

  it('stays visible with a value', () => {
    const host = render().querySelector('sb-market-value') as HTMLElement;
    expect(host.classList).not.toContain('mv-empty');
  });

  it('spinner beside the value while refreshing', () => {
    const el = render({ r: true });
    expect(el.querySelector('sb-spinner')).not.toBeNull();
    expect((el.querySelector('.mv-value') as HTMLElement).hidden).toBe(false);
  });

  it('spinner alone when no value was ever stored', () => {
    const el = render({ a: null, r: true });
    expect(el.querySelector('sb-spinner')).not.toBeNull();
    expect((el.querySelector('.mv-value') as HTMLElement).hidden).toBe(true);
  });

  const err = (el: HTMLElement) => el.querySelector('.mv-err');
  const tone = (el: HTMLElement) => el.querySelector('.mv')?.getAttribute('data-tone');

  it('a fresh price hides an error: the spinner keeps running (v248)', () => {
    const el = render({ r: true, e: 'no quote', errAt: ago(5) });
    expect(err(el)).toBeNull();
    expect(el.querySelector('sb-spinner')).not.toBeNull();
    expect(tone(el)).toBe('fresh');
  });

  it('a stale price shows a current error in red, with its text (v248)', () => {
    const el = render({ a: ago(840), r: true, e: 'no quote', errAt: ago(30) });
    expect(err(el)?.textContent?.trim()).toBe('· refresh failed: no quote');
    expect(err(el)?.getAttribute('title')).toBe('no quote');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('14 min ago');
    expect(tone(el)).toBe('failed');
    expect(el.querySelector('sb-spinner')).toBeNull();
  });

  it('an error older than the price stays hidden; the age stays merely stale (v248)', () => {
    const el = render({ a: ago(840), e: 'no quote', errAt: ago(900) });
    expect(err(el)).toBeNull();
    expect(tone(el)).toBe('stale');
  });

  it('an error recorded at the price time still shows (v248)', () => {
    const at = ago(840);
    expect(err(render({ a: at, e: 'no quote', errAt: at }))).not.toBeNull();
  });

  it('no price at all shows the error without a separator (v248)', () => {
    const el = render({ a: null, e: 'timeout' });
    expect(err(el)?.textContent?.trim()).toBe('refresh failed: timeout');
    expect((el.querySelector('sb-market-value') as HTMLElement).classList).not.toContain('mv-empty');
  });

  it('a consumer that passes no errorAt (watchlist, tape) shows a current error on a stale price (v248)', () =>
    expect(err(render({ a: ago(840), e: 'no quote' }))).not.toBeNull());

  it('outside the regular session the error never shows and the age is grey (v248)', () => {
    status.set({ ...regular, session: 'extended' });
    const el = render({ a: ago(840), e: 'no quote', errAt: ago(30) });
    expect(err(el)).toBeNull();
    expect(tone(el)).toBe('closed');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('pre-market · last trade 14 min ago');
  });

  it('cuts a long error to 60 characters, the full text in its title (v248)', () => {
    const long = 'x'.repeat(80);
    const shown = err(render({ a: null, e: long }))!;
    const text = shown.textContent!.trim().replace('refresh failed: ', '');
    expect(text.length).toBe(60);
    expect(text.endsWith('…')).toBe(true);
    expect(shown.getAttribute('title')).toBe(long);
  });

  it('a snapshot error shows as before (v248 leaves snapshots alone)', () => {
    const el = render({ kind: 'snapshot', a: '2026-10-28', computedAt: ago(180), e: 'build failed' });
    expect(err(el)?.textContent?.trim()).toBe('refresh failed');
  });

  it('a stale price takes the stale tone', () => {
    const el = render({ a: ago(180) });
    expect(el.querySelector('.mv')?.getAttribute('data-tone')).toBe('stale');
  });

  it('shows the age and value of a fresh snapshot with a date-only input', () => {
    const el = render({ kind: 'snapshot', a: '2026-10-28', computedAt: ago(180) });
    expect(el.querySelector('.mv')?.getAttribute('data-tone')).toBe('fresh');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('3 min ago');
    expect(el.querySelector<HTMLElement>('.mv-value')?.hidden).toBe(false);
  });

  it('shows a stale tone for a snapshot with stale inputs', () => {
    const el = render({ kind: 'snapshot', a: '2026-10-28', computedAt: ago(180), staleInputs: true });
    expect(el.querySelector('.mv')?.getAttribute('data-tone')).toBe('stale');
  });

  it('shows only the spinner for a snapshot waiting on its first build', () => {
    const el = render({ kind: 'snapshot', a: '2026-10-28', r: true });
    expect(el.querySelector<HTMLElement>('.mv-value')?.hidden).toBe(true);
    expect(el.querySelector('sb-spinner')).not.toBeNull();
  });

  it('the age ticks with the clock', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    clock.set(NOW + 60_000);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.mv-age')?.textContent?.trim()).toBe('1 min ago');
  });
});

describe('errorIsCurrent (v248)', () => {
  const A = '2026-10-30T14:00:00Z';
  const B = '2026-10-30T14:05:00Z';
  it('is current with no error time, no price time, or an error at or after the price', () => {
    expect(errorIsCurrent(null, A)).toBe(true);
    expect(errorIsCurrent(B, null)).toBe(true);
    expect(errorIsCurrent(B, A)).toBe(true);
    expect(errorIsCurrent(A, A)).toBe(true);
  });
  it('is not current when the price is newer than the error', () =>
    expect(errorIsCurrent(A, B)).toBe(false));
});
