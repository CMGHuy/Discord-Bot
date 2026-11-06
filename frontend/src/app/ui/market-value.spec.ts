import { Component, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MarketStatus } from '../api/models';
import { LiveValuesStore } from '../stores/live-values.store';
import { CLOCK } from './clock';
import { MarketValue } from './market-value';

const NOW = Date.parse('2026-10-30T15:00:00Z'); // a Friday, regular hours
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const regular: MarketStatus = {
  session: 'regular', last_close_at: '2026-10-29T20:00:00Z', stale_price_s: 120,
  heartbeat: { beat_at: null, cadence_s: 30, stalled: false },
};

@Component({
  imports: [MarketValue],
  template: `<sb-market-value [asOf]="a" [refreshing]="r" [error]="e">187.42</sb-market-value>`,
})
class Host {
  a: string | null = ago(12);
  r = false;
  e: string | null = null;
}

describe('sb-market-value (v201)', () => {
  let clock: WritableSignal<number>;

  beforeEach(() => {
    clock = signal(NOW);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: CLOCK, useValue: clock },
        { provide: LiveValuesStore, useValue: { status: signal(regular) } },
      ],
    });
  });

  function render(init: Partial<Host> = {}) {
    const f = TestBed.createComponent(Host);
    Object.assign(f.componentInstance, init);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

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
        { provide: CLOCK, useValue: clock }, { provide: LiveValuesStore, useValue: { status: signal(regular) } }] });
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

  it('error stops the spinner', () => {
    const el = render({ r: true, e: 'no quote' });
    expect(el.querySelector('sb-spinner')).toBeNull();
    expect(el.querySelector('.mv-err')?.textContent?.trim()).toBe('refresh failed');
    expect(el.querySelector('.mv-age')?.textContent?.trim()).toBe('12 s ago');
  });

  it('a stale price takes the stale tone', () => {
    const el = render({ a: ago(180) });
    expect(el.querySelector('.mv')?.getAttribute('data-tone')).toBe('stale');
  });

  it('the age ticks with the clock', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    clock.set(NOW + 60_000);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.mv-age')?.textContent?.trim()).toBe('1 min ago');
  });
});
