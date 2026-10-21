import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { BAND_INSUFFICIENT, BAND_NOT_POSITIVE, BAND_OK, BAND_TIE } from './variance-band.fixture';
import { CAPTION, CAVEAT, HEADER_COPY, ZONE_COPY } from './variance-band.model';
import { VarianceBandPanel } from './variance-band-panel';

function render(band: unknown, error: string | null = null) {
  const reload = vi.fn();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { varianceBand: signal(band), varianceBandError: signal(error), reload } },
      { provide: ConnectionStore, useValue: { currency: signal('$') } },
    ],
  });
  const fixture = TestBed.createComponent(VarianceBandPanel);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const bar = (key: string) => el.querySelector(`.bar[data-bar="${key}"]`) as HTMLElement;
  return { el, bar, reload };
}

describe('VarianceBandPanel', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('is titled and scoped, and has no control at all', () => {
    const { el } = render(BAND_OK);
    expect(el.querySelector('sb-panel-header h2')?.textContent).toBe('Normal bad luck');
    expect(el.textContent).toContain(HEADER_COPY);
    // Non-interactive: no hint, no Table toggle, no link, nothing focusable.
    expect(el.querySelectorAll('button, a, [tabindex], sb-hint').length).toBe(0);
  });

  it('draws two bars, each with three labelled segments and their values as text', () => {
    const { bar } = render(BAND_OK);
    const run = bar('run');
    const drawdown = bar('drawdown');
    expect(run.querySelector('.bar-label')?.textContent).toBe('Losing days in a row');
    expect(drawdown.querySelector('.bar-label')?.textContent).toBe('Drawdown over the last 50 close days');
    expect([...run.querySelectorAll('.track .seg')].map((s) => s.getAttribute('data-zone')))
      .toEqual(['normal', 'rough', 'outside']);
    expect([...run.querySelectorAll('.legend li')].map((li) => li.textContent?.replace(/\s+/g, ' ').trim()))
      .toEqual(['Normal ≤ 4 days', 'Rough > 4 to ≤ 7 days', 'Outside > 7 days']);
    expect(drawdown.querySelector('.legend')?.textContent).toContain('> 6.6R');
  });

  it('skips the rough segment when p80 equals p95', () => {
    const { bar } = render(BAND_TIE);
    expect([...bar('run').querySelectorAll('.track .seg')].map((s) => s.getAttribute('data-zone')))
      .toEqual(['normal', 'outside']);
    expect(bar('run').querySelector('.legend')?.textContent).not.toContain('Rough');
    expect([...bar('drawdown').querySelectorAll('.track .seg')]).toHaveLength(3);
  });

  it("writes each bar's zone in words under it", () => {
    const ok = render(BAND_OK);
    expect(ok.bar('run').querySelector('.zone')?.textContent).toBe(ZONE_COPY.normal);
    expect(ok.bar('drawdown').querySelector('.zone')?.textContent).toBe(ZONE_COPY.rough);
    TestBed.resetTestingModule();
    const outside = render(BAND_NOT_POSITIVE);
    expect(outside.bar('run').querySelector('.zone')?.textContent).toBe(ZONE_COPY.outside);
    expect(outside.bar('drawdown').querySelector('.zone')?.textContent).toBe(ZONE_COPY.outside);
  });

  it('gives the marker a text equivalent, on screen and to screen readers', () => {
    const { bar } = render(BAND_OK);
    expect(bar('run').querySelector('.now')?.textContent).toBe('now: 4 days, 9 calendar days long');
    expect(bar('drawdown').querySelector('.now')?.textContent)
      .toBe('now: 5.3R (≈ $312.34), 23 calendar days since the peak');
    const track = bar('run').querySelector('.track') as HTMLElement;
    expect(track.getAttribute('role')).toBe('img');
    expect(track.getAttribute('aria-label')).toContain('now: 4 days, 9 calendar days long');
    // BAND_OK's 50-day run band: p80 4, p95 7 -> scaleMax 8.75; a run of 4 sits at 45.71%.
    expect(parseFloat((bar('run').querySelector('.marker') as HTMLElement).style.left)).toBeCloseTo(45.714, 2);
  });

  it('shows the uncertainty, the spans, the 20-day line, ExpR with N and window, and composition', () => {
    const { el } = render(BAND_OK);
    const text = el.textContent as string;
    expect(text).toContain('p95 ≈ 7 (6–8)');
    expect(text).toContain('p95 ≈ 6.6R (5.9–7.4R)');
    expect(text).toContain("50 close days ≈ 13.2 weeks at this book's pace");
    expect(text).toContain("20 close days ≈ 5.3 weeks at this book's pace");
    expect(text).toContain('Over 20 close days: p95 4 days in a row, 4.4R drawdown');
    expect(el.querySelector('.expr')?.textContent).toBe('Book: ExpR +0.21R over N=222 trades (2026-01-05 to 2026-10-16)');
    expect(el.querySelector('.composition')?.textContent)
      .toBe('Close days: 118 v2, 42 legacy · Trades: 2w 88, 4w 131, unknown 3');
    expect(el.querySelector('.caption')?.textContent).toBe(CAPTION);
  });

  it('adds the caveat only when ExpR is not positive', () => {
    expect(render(BAND_OK).el.textContent).not.toContain(CAVEAT);
    TestBed.resetTestingModule();
    const { el } = render(BAND_NOT_POSITIVE);
    expect(el.querySelector('.caveat')?.textContent).toBe(CAVEAT);
  });

  it('shows approximate dollars and their derivation only when the band carries them', () => {
    const withDollars = render(BAND_OK).el;
    expect(withDollars.querySelector('.dollar-note')?.textContent)
      .toBe('≈ $ = R × the median per-trade dollar risk ($59.26), from shares × entry-to-stop distance.');
    TestBed.resetTestingModule();
    const without = render(BAND_TIE).el;
    expect(without.querySelector('.dollar-note')).toBeNull();
    expect(without.textContent).not.toContain('≈ $');
    expect(without.textContent).not.toContain('—');   // omitted, never a dash
  });

  it('says what is missing when the book is too short, and draws no bar', () => {
    const { el } = render(BAND_INSUFFICIENT);
    expect(el.querySelector('.insufficient')?.textContent)
      .toBe('Needs 100 close days over 20 weeks (64 days, 15 weeks so far).');
    expect(el.querySelector('.bar')).toBeNull();
  });

  it('replaces the body with a retry surface that retries only this panel', () => {
    const { el, reload } = render(null, 'The admin is not responding.');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.querySelector('.bar')).toBeNull();
    (el.querySelector('sb-panel-error button') as HTMLButtonElement).click();
    expect(reload).toHaveBeenCalledWith('varianceBand');
  });

  it('never says "edge" in any state', () => {
    for (const band of [BAND_OK, BAND_TIE, BAND_NOT_POSITIVE, BAND_INSUFFICIENT]) {
      TestBed.resetTestingModule();
      expect(render(band).el.textContent).not.toMatch(/\bedge\b/i);
    }
  });
});

describe('variance-band-panel.ts layout', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/analytics/tabs/variance-band-panel.ts'), 'utf8',
  );

  it('stacks the bars on phones and uses only declared breakpoints', () => {
    expect(src).toMatch(/@media \(max-width: 639px\) \{ \.bars \{ grid-template-columns: 1fr; \} \}/);
    const allowed = new Set(['639', '640', '1023', '1024', '1439', '1440', '1919', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });

  it('wraps copy instead of truncating it', () => {
    expect(src).not.toMatch(/text-overflow:\s*ellipsis/);
    expect(src).not.toMatch(/white-space:\s*nowrap/);
  });
});
