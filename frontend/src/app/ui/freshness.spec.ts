import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Freshness } from './freshness';

const NOW = new Date('2026-09-11T14:30:00Z');

function render(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(Freshness);
  f.componentRef.setInput('at', '2026-09-11T14:29:30Z');
  f.componentRef.setInput('now', NOW);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.freshness')!;
}

describe('Freshness (v85 D30)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('prints the time the data is as of', () => {
    expect(render({}).textContent).toContain('as of');
  });

  it('is not stale inside the threshold', () => {
    expect(render({}).classList).not.toContain('stale');
  });

  it('is stale past the threshold', () => {
    const el = render({ at: '2026-09-11T14:00:00Z', staleAfterSec: 900 });
    expect(el.classList).toContain('stale');
  });

  it('says stale in words, not by colour alone', () => {
    const el = render({ at: '2026-09-11T14:00:00Z', staleAfterSec: 900 });
    expect(el.textContent).toContain('stale');
  });

  it('reports an absent timestamp as unknown rather than as now', () => {
    const el = render({ at: null });
    expect(el.textContent).toContain('age unknown');
    expect(el.classList).toContain('stale');
  });

  it('reports an unparseable timestamp as unknown', () => {
    const el = render({ at: 'not-a-date' });
    expect(el.textContent).toContain('age unknown');
  });

  it('prints a date-only marker as the date, not a bogus midnight time', () => {
    // Risk's metrics/correlation panels feed a daily-bar `as_of`
    // ("2026-09-10") that has no time-of-day. Slicing it as a full
    // timestamp would always read "00:00:00" regardless of real freshness.
    const el = render({ at: '2026-09-10' });
    expect(el.textContent).toContain('as of 2026-09-10');
    expect(el.textContent).not.toContain('00:00:00');
  });

  it('is announced politely rather than interrupting', () => {
    expect(render({}).getAttribute('aria-live')).toBe('polite');
  });
});
