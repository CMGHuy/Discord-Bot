import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { FreshRequestService } from '../api/fresh-request.service';
import { asyncInputs, Async, skeletonGrid, type AsyncEmptyReason, type SkeletonShape } from './async';

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
      [shape]="shape"
      [announce]="announce"
      (retry)="retried = retried + 1; onRetried()"
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
  announce: string | null = null;
  retried = 0;
  onRetried: () => void = () => undefined;
  shape: SkeletonShape = 'table';
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

  it('exposes one polite live region for pushed updates', () => {
    const { el } = render();
    const region = el.querySelector('[aria-live]')!;
    expect(region.getAttribute('aria-live')).toBe('polite');
    expect(el.querySelectorAll('[aria-live]').length).toBe(1);
  });

  it('announces only what the caller gives it', () => {
    const { el } = render({ announce: '3 trades updated' });
    expect(el.querySelector('[aria-live]')!.textContent).toContain('3 trades updated');
  });
});

/* Spec v168 §3 #4: the skeleton was already shaped (rows x cols); v168 swaps
 * its pulse for a moving shimmer and adds `shape` for placeholders that are
 * not tables. Every cell keeps the table-row height, so nothing reflows when
 * the content replaces it. */
describe('Async skeleton shapes (v168 #4)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const cells = (row: Element) => [...row.querySelectorAll('.skeleton-cell')];

  it('defaults to the table shape it always had', () => {
    const { el } = render({ loading: true });
    const skeleton = el.querySelector('.skeleton')!;
    expect(skeleton.classList).toContain('shape-table');
    expect(el.querySelectorAll('.skeleton-row').length).toBe(3);
    for (const row of el.querySelectorAll('.skeleton-row')) expect(cells(row).length).toBe(2);
  });

  it('draws a panel as a heading bar over full-width rows', () => {
    const { el } = render({ loading: true, shape: 'panel' });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(el.querySelector('.skeleton')!.classList).toContain('shape-panel');
    expect(rows.length).toBe(3);
    expect(cells(rows[0]).map((cell) => cell.className)).toEqual(['skeleton-cell head']);
    expect(rows.slice(1).map((row) => cells(row).length)).toEqual([1, 1]);
  });

  it('draws a figure as a label over a value', () => {
    const { el } = render({ loading: true, shape: 'figure' });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(el.querySelector('.skeleton')!.classList).toContain('shape-figure');
    expect(rows.map((row) => cells(row).map((cell) => cell.className))).toEqual([
      ['skeleton-cell label'],
      ['skeleton-cell value'],
    ]);
  });

  it('keeps aria-busy and the live region whatever the shape', () => {
    const { el } = render({ loading: true, shape: 'figure', announce: 'Loading' });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
    expect(el.querySelectorAll('[aria-live]').length).toBe(1);
    expect(el.querySelector('.skeleton')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('computes the grid as a pure table of shapes', () => {
    expect(skeletonGrid('table', 2, 3)).toEqual([['', '', ''], ['', '', '']]);
    expect(skeletonGrid('panel', 3, 4)).toEqual([['head'], [''], ['']]);
    expect(skeletonGrid('panel', 1, 4)).toEqual([['head']]);
    expect(skeletonGrid('figure', 6, 4)).toEqual([['label'], ['value']]);
  });

  it('shimmers with a moving gradient instead of pulsing (source text)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/async.ts'), 'utf8');
    const cell = source.match(/\.skeleton-cell\s*\{[^}]*\}/)![0];
    expect(cell).toContain('animation: sb-shimmer 1.6s linear infinite;');
    expect(cell).toContain('background-size: 200% 100%;');
    expect(cell).toContain('height: var(--control-h);');
    expect(source).not.toContain('sb-pulse-soft');
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

  it('emits Retry inside markFresh, so the reload it triggers is fresh (v171 D2)', () => {
    const fresh = TestBed.inject(FreshRequestService);
    const { f, el } = render({ error: 'The admin could not be reached.' });
    let markingDuringRetry: boolean | null = null;
    f.componentInstance.onRetried = () => { markingDuringRetry = fresh.isMarking(); };
    (el.querySelector('button.retry') as HTMLButtonElement).click();
    expect(f.componentInstance.retried).toBe(1);
    expect(markingDuringRetry).toBe(true);
    expect(fresh.isMarking()).toBe(false);
  });
});
