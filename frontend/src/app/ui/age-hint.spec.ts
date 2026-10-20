import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConnectionStore } from '../stores/connection.store';
import { AgeHint, PAGE_PRICE_WINDOW_S, ageText } from './age-hint';

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
