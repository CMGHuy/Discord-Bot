import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { asyncInputs, Async, type AsyncEmptyReason } from './async';

@Component({
  imports: [Async],
  template: `
    <sb-async
      [loading]="loading"
      [error]="error"
      [empty]="empty"
      [emptyReason]="reason"
      [emptyTitle]="'No closed trades'"
      [staleAsOf]="staleAsOf"
      [skeletonRows]="3"
      [skeletonCols]="2"
      (retry)="retried = retried + 1"
    >
      <p class="content">loaded</p>
    </sb-async>
  `,
})
class Host {
  loading = false;
  error: string | null = null;
  empty = false;
  reason: AsyncEmptyReason = 'no-data-yet';
  staleAsOf: string | null = null;
  retried = 0;
}

function render(patch: Partial<Host> = {}) {
  const f = TestBed.createComponent(Host);
  Object.assign(f.componentInstance, patch);
  f.detectChanges();
  return { f, el: f.nativeElement as HTMLElement };
}

describe('Async', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('shows the content when there is nothing wrong', () => {
    const { el } = render();
    expect(el.querySelector('.content')).toBeTruthy();
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('shows a shaped skeleton while loading, not a spinner', () => {
    const { el } = render({ loading: true });
    expect(el.querySelectorAll('.skeleton-row').length).toBe(3);
    expect(el.querySelectorAll('.skeleton-row')[0].children.length).toBe(2);
    expect(el.querySelector('.content')).toBeNull();
  });

  it('marks itself busy while loading', () => {
    const { el } = render({ loading: true });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
  });

  it('shows the error and offers a retry that emits', () => {
    const { f, el } = render({ error: 'Request failed' });
    expect(el.textContent).toContain('Request failed');
    el.querySelector<HTMLButtonElement>('.retry')!.click();
    expect(f.componentInstance.retried).toBe(1);
  });

  it('distinguishes a measured zero from missing data', () => {
    expect(render({ empty: true, reason: 'no-data-yet' }).el.textContent)
      .toContain('awaiting data');
    expect(render({ empty: true, reason: 'measured-zero' }).el.textContent)
      .toContain('result: 0');
  });

  it('dims the content and names the time when the data is stale', () => {
    const { el } = render({ staleAsOf: '15:42' });
    expect(el.querySelector('.content')).toBeTruthy();
    expect(el.querySelector('.stale-badge')!.textContent).toContain('as of 15:42');
  });

  it('prefers error over loading, and loading over empty', () => {
    const { el } = render({ error: 'boom', loading: true, empty: true });
    expect(el.textContent).toContain('boom');
    expect(el.querySelector('.skeleton')).toBeNull();
  });
});

const at = () => new Date('2026-08-23T15:42:00');

describe('asyncInputs', () => {
  const src = (data: unknown, loading: boolean, error: string | null) => ({
    data: () => data as never,
    loading: () => loading,
    error: () => error,
  });
  const opts = { isEmpty: (d: unknown[]) => d.length === 0, now: at };

  it('reports a first-load failure as an error', () => {
    expect(asyncInputs(src(null, false, 'boom'), opts))
      .toEqual({ loading: false, error: 'boom', empty: false, staleAsOf: null });
  });

  it('demotes a refetch failure to stale so the numbers stay on screen', () => {
    expect(asyncInputs(src([1], false, 'boom'), opts))
      .toEqual({ loading: false, error: null, empty: false, staleAsOf: '15:42' });
  });

  it('reports loading only while there is nothing to show', () => {
    expect(asyncInputs(src(null, true, null), opts).loading).toBe(true);
    // A background refresh over existing data is not a loading state: the
    // skeleton would blank a screen the reader is already reading.
    expect(asyncInputs(src([1], true, null), opts).loading).toBe(false);
  });

  it('reports empty only once data has actually arrived', () => {
    expect(asyncInputs(src(null, false, null), opts).empty).toBe(false);
    expect(asyncInputs(src([], false, null), opts).empty).toBe(true);
  });
});
