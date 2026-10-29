import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { CANCELS_URL, CancelsStore, NO_FILTER } from '../../stores/cancels.store';
import { CANCEL_PAYLOAD, EMPTY_CANCEL_PAYLOAD } from '../../testing/cancel-fixtures';
import { RouteTitleService } from '../../routing/route-title.service';
import { Cancels } from './cancels';

function create(body: object = CANCEL_PAYLOAD, init?: { status: number; statusText: string }): ComponentFixture<Cancels> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      provideRouter([]),
    ],
  });
  const fixture = TestBed.createComponent(Cancels);
  TestBed.inject(CancelsStore).load().subscribe({ error: () => undefined });
  TestBed.inject(HttpTestingController).expectOne(CANCELS_URL).flush(body, init);
  fixture.detectChanges();
  return fixture;
}

const host = (f: ComponentFixture<Cancels>): HTMLElement => f.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
const bodyRows = (f: ComponentFixture<Cancels>): HTMLElement[] =>
  Array.from(host(f).querySelectorAll<HTMLElement>('sb-cancels-table sb-data-table tbody tr'))
    .filter((tr) => !tr.classList.contains('expansion'));
const click = (f: ComponentFixture<Cancels>, selector: string): void => {
  host(f).querySelector<HTMLElement>(selector)!.click();
  f.detectChanges();
};

describe('Cancels', () => {
  it('renders the summary and the table from one request', () => {
    const f = create();
    expect(host(f).querySelector('sb-cancels-summary')).not.toBeNull();
    expect(bodyRows(f).length).toBe(6);
    TestBed.inject(HttpTestingController).verify();
  });

  it('filters the table from a card and clears it on a second click', () => {
    const f = create();
    click(f, '[data-card="risk_cap"]');
    expect(bodyRows(f).length).toBe(1);
    expect(text(bodyRows(f)[0])).toContain('AAPL');
    expect(text(host(f).querySelector('.filter-line'))).toContain('risk_cap');
    expect(text(host(f).querySelector('.filter-line'))).toContain('1 of 6 rows');
    click(f, '[data-card="risk_cap"]');
    expect(bodyRows(f).length).toBe(6);
    expect(host(f).querySelector('.filter-line')).toBeNull();
  });

  it('filters from a count and from a split, and Clear filter resets both', () => {
    const f = create();
    click(f, '[data-outcome="wrong"]');
    expect(bodyRows(f).length).toBe(1);
    expect(text(bodyRows(f)[0])).toContain('MSFT');
    click(f, '[data-split="direction:long"]');
    expect(bodyRows(f).length).toBe(1);
    const clear = Array.from(host(f).querySelectorAll<HTMLElement>('.filter-line button'))
      .find((b) => text(b) === 'Clear filter')!;
    clear.click();
    f.detectChanges();
    expect(bodyRows(f).length).toBe(6);
    expect(TestBed.inject(CancelsStore).filter()).toEqual(NO_FILTER);
  });

  it('shows an empty book as figures, never as an empty state', () => {
    const f = create(EMPTY_CANCEL_PAYLOAD);
    expect(text(host(f).querySelector('[data-figure="precision"]'))).toContain('— of 0');
    expect(text(host(f))).not.toContain('Nothing to replay');
    expect(text(host(f))).toContain('No cancelled plans match this filter');
  });

  it('shows the error and no figures when the first load fails', () => {
    const f = create({ error: { code: 'internal', message: 'boom' } }, { status: 500, statusText: 'Server Error' });
    expect(host(f).querySelector('sb-cancels-summary')).toBeNull();
    expect(TestBed.inject(CancelsStore).error()).toBeTruthy();
  });

  it('keeps the figures when a reload fails', () => {
    const f = create();
    TestBed.inject(CancelsStore).load().subscribe({ error: () => undefined });
    TestBed.inject(HttpTestingController).expectOne(CANCELS_URL)
      .flush({ error: { code: 'internal', message: 'boom' } }, { status: 500, statusText: 'Server Error' });
    f.detectChanges();
    expect(host(f).querySelector('sb-cancels-summary')).not.toBeNull();
  });
});

/* -- v195 Phase 4 -- Cancels on sb-page ------------------------------------- */

describe('Cancels on sb-page (v195 Phase 4)', () => {
  it('renders the route title as the one h1, from sb-page', () => {
    const f = create();
    TestBed.inject(RouteTitleService).set('Cancels', "Were the bot's own cancels right?");
    f.detectChanges();
    expect(host(f).querySelectorAll('h1')).toHaveLength(1);
    expect(text(host(f).querySelector('sb-page h1.title'))).toBe('Cancels');
  });

  it('keeps the summary directly above the table, in one primary element', () => {
    const f = create();
    const primary = host(f).querySelector('sb-page [page-primary]')!;
    expect(primary.tagName.toLowerCase()).toBe('sb-async');
    const summary = primary.querySelector('sb-cancels-summary')!;
    const table = primary.querySelector('sb-cancels-table')!;
    expect(summary.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('is read-only: no header action, no scope bar, no KPI or secondary slot', () => {
    const f = create();
    for (const slot of ['[page-actions]', '[page-scope]', '[page-kpis]', '[page-secondary]']) {
      expect(host(f).querySelector(slot), slot).toBeNull();
    }
    expect(host(f).querySelector('sb-page .danger, sb-page .danger-quiet')).toBeNull();
  });
});
