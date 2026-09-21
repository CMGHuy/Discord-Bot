import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TradesStore } from '../../stores/trades.store';
import { PositionsTable, POSITION_TABS } from './positions-table';

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
      'Open 1', 'Pending 0', 'Partial 0', 'Closed 0', 'Cancelled 0',
    ]);
  });

  it('mirrors each tab\'s count into the compact "· N" shown below md', () => {
    const f = mount();
    const counts = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"] .count')]
      .map((el) => el.textContent?.trim());
    expect(counts).toEqual(['· 1', '· 0', '· 0', '· 0', '· 0']);
  });

  it('queries only the active tab, not all five', () => {
    mount();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'ACTIVE', page: 1, per_page: 5 });
  });

  it('re-queries with the new status when a tab is chosen', () => {
    const f = mount();
    setQuery.mockClear();
    (f.nativeElement as HTMLElement)
      .querySelectorAll<HTMLButtonElement>('[role="tab"]')[1].click();
    f.detectChanges();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'PENDING' });
  });

  it('uses five rows per page for every lifecycle tab', () => {
    const f = mount();
    for (const tab of POSITION_TABS) clickTab(f, tab.id);

    expect(setQuery.mock.calls.map(([query]) => query.per_page)).toEqual(
      Array(POSITION_TABS.length).fill(5),
    );
  });

  it('re-queries the selected tab when its pager changes page', () => {
    const f = mount();
    setQuery.mockClear();
    (f.componentInstance as unknown as { goToPage(page: number): void }).goToPage(2);
    f.detectChanges();

    expect(setQuery).toHaveBeenCalledWith(expect.objectContaining({ page: 2, per_page: 5 }));
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
});
