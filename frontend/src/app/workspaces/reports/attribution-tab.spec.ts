import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { ExpectancyAttribution, ReportEnvelope } from '../../api/models';
import { LATEST_HEADING, R_CAPTION, ReportsStore } from '../../stores/reports.store';
import { ATTRIBUTION, NOT_RUN, ok } from '../../testing/report-fixtures';
import { AttributionTab, formatInterval, formatR } from './attribution-tab';

/* The fixture's latest reading says PREDICTIVE while its verdict of record
 * says WEAK, so "which one did the page show as the verdict" has a wrong
 * answer these tests can catch. */

function create(
  envelope: ReportEnvelope<ExpectancyAttribution> = ok(ATTRIBUTION),
): ComponentFixture<AttributionTab> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  const fixture = TestBed.createComponent(AttributionTab);
  TestBed.inject(ReportsStore).resolveTab('attribution').subscribe();
  TestBed.inject(HttpTestingController)
    .expectOne('/api/v1/reports/expectancy-attribution').flush(envelope);
  fixture.detectChanges();
  return fixture;
}

const host = (fixture: ComponentFixture<AttributionTab>): HTMLElement => fixture.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
const panel = (fixture: ComponentFixture<AttributionTab>, heading: string): HTMLElement =>
  Array.from(host(fixture).querySelectorAll<HTMLElement>('sb-panel'))
    .find((el) => text(el).startsWith(heading))!;

describe('formatR / formatInterval', () => {
  it('signs positive values and writes an em dash for a missing one', () => {
    expect([formatR(0.224), formatR(-0.05), formatR(0), formatR(null)]).toEqual(['+0.22R', '-0.05R', '0.00R', '—']);
    expect(formatInterval(0.03, 0.41)).toBe('[+0.03R, +0.41R]');
    expect(formatInterval(null, 0.41)).toBe('—');
  });
});

describe('AttributionTab', () => {
  it('shows exactly one verdict chip: the verdict of record, with its date and N', () => {
    const fixture = create();
    const chips = Array.from(host(fixture).querySelectorAll('sb-chip'));
    expect(chips.map((chip) => text(chip))).toEqual(['WEAK']);
    expect(text(panel(fixture, 'Verdict of record'))).toContain('fixed 2026-10-12 · N 214');
    // The latest reading's own verdict word never appears as a verdict.
    expect(text(host(fixture))).not.toContain('PREDICTIVE');
  });

  it('puts the latest reading in its own descriptive block, one column per population', () => {
    const fixture = create();
    const latest = panel(fixture, LATEST_HEADING);
    expect(latest.querySelector('sb-chip')).toBeNull();
    expect(text(latest.querySelector('[data-population="Live"]'))).toContain('+0.22R [+0.03R, +0.41R]');
    expect(text(latest.querySelector('[data-population="TRAIN"]'))).toContain('+0.04R [-0.02R, +0.10R]');
  });

  it('shows each factor as delta and interval, with the candidate marker only below q 0.10', () => {
    const fixture = create();
    const row = (key: string) => text(host(fixture).querySelector(`[data-factor="${key}"]`));
    expect(row('RSI trend alignment')).toContain('+0.19R [+0.04R, +0.35R]');
    expect(row('RSI trend alignment')).toContain('screen candidate');
    expect(row('MACD momentum')).toContain('+0.03R [-0.12R, +0.18R]');
    expect(row('MACD momentum')).not.toContain('screen candidate');
    expect(panel(fixture, 'Factors').querySelector('sb-chip')).toBeNull();
  });

  it('draws a thin bucket withheld, with its N, and gives it no marker even at q 0.01', () => {
    const fixture = create();
    const earnings = host(fixture).querySelector<HTMLElement>('[data-dimension="earnings"]')!;
    const withheld = earnings.querySelector('li.withheld')!;
    expect(text(withheld)).toContain('0-5');
    expect(text(withheld)).toContain('12');
    expect(text(earnings)).not.toContain('screen candidate');
  });

  it('marks a bucket below q 0.10 and names its population', () => {
    const fixture = create();
    const regime = host(fixture).querySelector<HTMLElement>('[data-dimension="regime2_state"]')!;
    expect(text(regime)).toContain('screen candidate: bull_quiet (Live)');
    expect(regime.querySelectorAll('sb-bar-list').length).toBe(2);
  });

  it('repeats the reading per direction and per horizon', () => {
    const fixture = create();
    const bearish = text(host(fixture).querySelector('[data-split="Direction:bearish"]'));
    expect(bearish).toContain('-0.05R [-0.30R, +0.20R]');
    expect(bearish).toContain('44');
    expect(host(fixture).querySelectorAll('[data-split]').length).toBe(4);
  });

  it('states the looks count, the seed and the caption in the footer', () => {
    const fixture = create();
    const footer = text(host(fixture).querySelector('.footer'));
    expect(footer).toContain('looks: 37 — BH family for every q on this tab');
    expect(footer).toContain('Seed 42');
    expect(footer).toContain(R_CAPTION);
    expect(footer).toContain('descriptive — not a gate');
    expect(footer).toContain('Live: 2026-07-06..2026-10-05, N 214');
  });

  it('reads an absent population as "not in this run", never as zeros', () => {
    const fixture = create(ok({ ...ATTRIBUTION, populations: { live: ATTRIBUTION.populations.live, train: null } }));
    expect(text(host(fixture).querySelector('[data-population="TRAIN"]'))).toContain('not in this run');
    expect(text(host(fixture).querySelector('[data-dimension="regime2_state"]'))).toContain('not in this run');
    expect(text(host(fixture))).not.toContain('0.00R');
  });

  it('renders nothing of its own when the report has not run', () => {
    const fixture = create(NOT_RUN);
    expect(host(fixture).querySelector('sb-panel')).toBeNull();
    expect(host(fixture).querySelector('sb-chip')).toBeNull();
  });
});
