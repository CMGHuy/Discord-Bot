import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TradesStore } from '../../stores/trades.store';
import { PositionsTable } from './positions-table';

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

  it('offers the five lifecycle tabs, in lifecycle order', () => {
    const f = mount();
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
      .map((t) => t.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels).toEqual([
      'Open positions 1', 'Pending 0', 'Partial 0', 'Closed 0', 'Cancelled 0',
    ]);
  });

  it('queries only the active tab, not all five', () => {
    mount();
    expect(setQuery).toHaveBeenCalledTimes(1);
    expect(setQuery.mock.calls[0][0]).toMatchObject({ status: 'ACTIVE' });
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
});
