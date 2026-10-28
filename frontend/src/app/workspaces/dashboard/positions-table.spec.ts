import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TradesStore } from '../../stores/trades.store';
import { PositionsTable, POSITION_TABS } from './positions-table';
import { tradeColumns } from '../trades/trades.columns';

describe('positions table', () => {
  let setQuery: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setQuery = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
  });

  function mount(inputs: Record<string, unknown> = {}) {
    const f = TestBed.createComponent(PositionsTable);
    // The component provides TradesStore itself; override the instance it got.
    const store = f.debugElement.injector.get(TradesStore) as unknown as {
      setQuery: unknown;
    };
    store.setQuery = setQuery;
    f.componentRef.setInput('counts', { ACTIVE: 1, PENDING: 0, PARTIAL: 0, CLOSED: 0, CANCELLED: 0 });
    // The three other required inputs aren't this file's concern -- minimal
    // valid values so NG0950 doesn't fire before the per-test overrides run.
    f.componentRef.setInput('columns', []);
    f.componentRef.setInput('visibleFor', () => []);
    f.componentRef.setInput('rowKey', (row: { id: string }) => row.id);
    for (const [k, v] of Object.entries(inputs)) f.componentRef.setInput(k, v);
    f.detectChanges();
    return f;
  }

  /** Clicks the tab strip button for `id`, by its fixed POSITION_TABS index --
   *  the rendered label carries a live count too, so an id lookup is more
   *  robust than matching on label text. */
  function clickTab(f: ReturnType<typeof mount>, id: string): void {
    const index = POSITION_TABS.findIndex((t) => t.id === id);
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[index].click();
    f.detectChanges();
  }

  it('offers the five lifecycle tabs, in lifecycle order', () => {
    const f = mount();
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"] .label')]
      .map((el) => el.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels).toEqual([
      'Pending 0', 'Open 1', 'Partial 0', 'Closed 0', 'Cancelled 0',
    ]);
  });

  it('mirrors each tab\'s count into the compact "· N" shown below md', () => {
    const f = mount();
    const counts = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"] .count')]
      .map((el) => el.textContent?.trim());
    expect(counts).toEqual(['· 0', '· 1', '· 0', '· 0', '· 0']);
  });

  it('queries only the active tab, not all five', () => {
    mount();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'ACTIVE', page: 1, per_page: 10 });
  });

  it('re-queries with the new status when a tab is chosen', () => {
    const f = mount();
    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[0].click();
    f.detectChanges();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'PENDING' });
  });

  it('uses the device default rows per page (10 on desktop) for every lifecycle tab', () => {
    const f = mount();
    for (const tab of POSITION_TABS) clickTab(f, tab.id);

    const statuses = new Set(setQuery.mock.calls.map(([query]) => query.status));
    expect([...statuses].sort()).toEqual(POSITION_TABS.map((t) => t.status).sort());
    expect(setQuery.mock.calls.every(([query]) => query.per_page === 10)).toBe(true);
  });

  it('re-queries the selected tab when its pager changes page', () => {
    const f = mount();
    setQuery.mockClear();
    (f.componentInstance as unknown as { goToPage(page: number): void }).goToPage(2);
    f.detectChanges();

    expect(setQuery).toHaveBeenCalledWith(expect.objectContaining({ page: 2, per_page: 10 }));
  });

  it('passes the Today scope only to the closed and cancelled tabs', () => {
    const f = mount({ today: true });
    // ACTIVE is all-time regardless of the page scope.
    expect(setQuery.mock.calls.at(-1)![0].today).toBeUndefined();

    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[3].click();
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ status: 'CLOSED', today: true });
  });

  it('orders the closed tab by close time, newest first, and the others by open time', () => {
    const f = mount();
    expect(setQuery.mock.calls.at(-1)![0].sort).toBe('-opened_at');

    setQuery.mockClear();
    clickTab(f, 'CLOSED');
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ status: 'CLOSED', sort: '-closed_at' });
  });

  it('resets to the first page when the tab changes', () => {
    const f = mount();
    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[2].click();
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ page: 1 });
  });

  it('keeps a column reorder when the tab changes and changes back', () => {
    const f = mount();
    const reordered: string[][] = [];
    f.componentInstance.reorder.subscribe((order: string[]) => reordered.push(order));

    // A drag inside the ACTIVE tab emits the reconciled picker list upward.
    f.componentInstance.reorder.emit(['status', 'ticker', 'plan']);
    f.detectChanges();

    // Switch away and back; the table must ask for the same order it was given.
    clickTab(f, 'PENDING');
    clickTab(f, 'ACTIVE');
    expect(reordered.at(-1)).toEqual(['status', 'ticker', 'plan']);
  });

  it('asks for the right column set per tab from one shared picker list', () => {
    const seen: string[] = [];
    const f = mount({ visibleFor: (tab: string) => { seen.push(tab); return ['ticker']; } });
    clickTab(f, 'CLOSED');
    clickTab(f, 'CANCELLED');
    expect(seen).toContain('ACTIVE');
    expect(seen).toContain('CLOSED');
    expect(seen).toContain('CANCELLED');
  });

  it('keeps the Plan column floor the two-line runner cell was measured against (v177)', () => {
    // Line 2 adds height, not width: the column keeps its 12rem floor and
    // stays inline from xs on every tab, PARTIAL and CLOSED included.
    const plan = tradeColumns().find((c) => c.key === 'plan')!;
    expect(plan.width).toBe('12rem');
    expect(plan.inlineFrom).toBe('xs');
  });

  it('passes its phone-tap choice to the table, the generic drawer by default (v179 §6a.4)', () => {
    const f = mount();
    expect((f.componentInstance as unknown as { phoneTap: () => string }).phoneTap()).toBe('drawer');
    f.componentRef.setInput('phoneTap', 'emit');
    f.detectChanges();
    expect((f.componentInstance as unknown as { phoneTap: () => string }).phoneTap()).toBe('emit');
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/positions-table.ts'), 'utf8');
    expect(source).toMatch(/<sb-data-table[^>]*\[phoneTap\]="phoneTap\(\)"/);
  });
  it('sends the range window, not the Today flag, to the closed and cancelled tabs (v181 §6)', () => {
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const f = mount({ today: null, closedWindow: window });
    // ACTIVE is all-time regardless of the page scope.
    expect(setQuery.mock.calls.at(-1)![0]).not.toHaveProperty('closedFrom');

    clickTab(f, 'CLOSED');
    const closed = setQuery.mock.calls.at(-1)![0];
    expect(closed).toMatchObject({ status: 'CLOSED', closedFrom: window.from, closedTo: window.to });
    expect(closed.today).toBeUndefined();

    clickTab(f, 'CANCELLED');
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ closedFrom: window.from, closedTo: window.to });
  });

  it('lets the window win over a stale Today flag', () => {
    const window = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
    const f = mount({ today: true, closedWindow: window });
    clickTab(f, 'CLOSED');
    expect(setQuery.mock.calls.at(-1)![0].today).toBeUndefined();
  });

  it.each(['CLOSED', 'CANCELLED'])('resets paged %s results when the effective close filter changes', (tab) => {
    const f = mount({ today: null });
    clickTab(f, tab);
    const pager = f.componentInstance as unknown as { goToPage(page: number): void };
    const firstWindow = { from: '2026-10-15T04:00:00.000Z', to: '2026-10-20T04:00:00.000Z' };
    const nextWindow = { from: '2026-10-17T04:00:00.000Z', to: '2026-10-20T04:00:00.000Z' };
    for (const window of [firstWindow, nextWindow, null]) {
      pager.goToPage(3);
      f.detectChanges();
      expect(setQuery.mock.calls.at(-1)![0].page).toBe(3);
      setQuery.mockClear();
      f.componentRef.setInput('closedWindow', window);
      f.detectChanges();
      expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ status: tab, page: 1 });
      expect(setQuery.mock.calls.every(([query]) => query.page === 1)).toBe(true);
    }
    pager.goToPage(3);
    f.detectChanges();
    f.componentRef.setInput('today', true);
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0]).toMatchObject({ today: true, page: 1 });
  });

  it('preserves the page when a new window has the same effective bounds', () => {
    const window = { from: '2026-10-15T04:00:00.000Z', to: '2026-10-20T04:00:00.000Z' };
    const f = mount({ closedWindow: window });
    clickTab(f, 'CLOSED');
    (f.componentInstance as unknown as { goToPage(page: number): void }).goToPage(3);
    f.detectChanges();
    f.componentRef.setInput('closedWindow', { ...window });
    f.detectChanges();
    expect(setQuery.mock.calls.at(-1)![0].page).toBe(3);
  });

  it('keeps an open tab on its page when the closed filter changes', () => {
    const f = mount();
    (f.componentInstance as unknown as { goToPage(page: number): void }).goToPage(3);
    f.detectChanges();
    setQuery.mockClear();
    f.componentRef.setInput('closedWindow', { from: '2026-10-15T04:00:00.000Z', to: '2026-10-20T04:00:00.000Z' });
    f.componentRef.setInput('today', true);
    f.detectChanges();
    expect(setQuery).not.toHaveBeenCalled();
  });

});

/* -- v195 Phase 4 and §1.4 -------------------------------------------------- */

describe('positions table after the Dashboard moved onto sb-page', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/positions-table.ts'), 'utf8');

  it('no longer projects table actions: Close all is the page header\'s', () => {
    expect(src).not.toContain('table-actions');
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
