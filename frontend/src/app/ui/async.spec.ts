import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { FreshRequestService } from '../api/fresh-request.service';
import { asyncInputs, Async, BAR_WIDTHS, barWidth, skeletonGrid, type AsyncEmptyReason, type SkeletonShape } from './async';

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
      [skeletonCols]="cols"
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
  cols = 2;
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
      .toContain('Awaiting data');
    expect(render({ empty: true, reason: 'measured-zero' }).el.textContent)
      .toContain('Result: 0');
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

  /* v186 D5: thin bars by column index, a 'tiles' shape on the strip grid,
   * and a quiet opacity pulse in place of the shimmer. */
  const barWidths = (row: Element) =>
    cells(row).map((cell) => (cell as HTMLElement).style.getPropertyValue('--bar-w'));

  it('sizes the bars by column index: 40, 65, 30, 55 per cent, repeating', () => {
    expect([...BAR_WIDTHS]).toEqual(['40%', '65%', '30%', '55%']);
    expect([0, 1, 2, 3, 4, 5, 8].map(barWidth)).toEqual(['40%', '65%', '30%', '55%', '40%', '65%', '40%']);
  });

  it('gives a 4-column grid the four widths on every row', () => {
    const { el } = render({ loading: true, cols: 4 });
    const rows = [...el.querySelectorAll('.skeleton-row')];
    expect(rows.length).toBe(3);
    for (const row of rows) expect(barWidths(row)).toEqual(['40%', '65%', '30%', '55%']);
  });

  it('repeats the sequence across a 6-column grid', () => {
    const { el } = render({ loading: true, cols: 6 });
    for (const row of el.querySelectorAll('.skeleton-row')) {
      expect(barWidths(row)).toEqual(['40%', '65%', '30%', '55%', '40%', '65%']);
    }
  });

  it('keeps the cell classes exact while it sets the bar width', () => {
    const { el } = render({ loading: true, shape: 'figure' });
    const label = el.querySelector('.skeleton-cell.label') as HTMLElement;
    expect(label.className).toBe('skeleton-cell label');
    expect(label.style.getPropertyValue('--bar-w')).toBe('40%');
  });

  it('draws tiles as label and value bars on the strip grid', () => {
    const { el } = render({ loading: true, shape: 'tiles', cols: 2 });
    const skeleton = el.querySelector('.skeleton')!;
    expect(skeleton.classList).toContain('shape-tiles');
    expect(skeleton.getAttribute('aria-hidden')).toBe('true');
    expect(el.querySelector('.skeleton-row')).toBeNull();
    const grid = skeleton.querySelector(':scope > .sb-strip-grid') as HTMLElement;
    expect(grid.classList).toContain('sb-strip-fixed');
    expect(grid.style.getPropertyValue('--strip-cols')).toBe('2');
    const tiles = [...grid.querySelectorAll(':scope > .skeleton-tile')];
    expect(tiles.length).toBe(6); // skeletonRows 3 x skeletonCols 2
    for (const tile of tiles) {
      expect([...tile.children].map((bar) => bar.className)).toEqual(['skeleton-bar label', 'skeleton-bar value']);
    }
  });

  it('keeps aria-busy and the one live region for tiles', () => {
    const { el } = render({ loading: true, shape: 'tiles', announce: 'Loading' });
    expect(el.querySelector('sb-async')!.getAttribute('aria-busy')).toBe('true');
    expect(el.querySelectorAll('[aria-live]').length).toBe(1);
  });

  it('keeps each cell a table row tall and moves the paint onto a thin bar (source text)', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/async.ts'), 'utf8');
    const cell = source.match(/\.skeleton-cell\s*\{[^}]*\}/)![0];
    expect(cell).toContain('height: var(--control-h);');
    expect(cell).not.toContain('animation');
    expect(cell).not.toContain('background');
    const bar = source.match(/\.skeleton-cell::before,\s*\.skeleton-bar\s*\{[^}]*\}/)![0];
    expect(bar).toContain('height: 8px;');
    expect(bar).toContain('border-radius: var(--radius-sm);');
    expect(bar).toContain('animation: sb-skeleton-pulse calc(1800ms * var(--motion-scale)) ease-in-out infinite;');
    expect(source.match(/\.skeleton-cell::before\s*\{[^}]*\}/)![0]).toContain('width: var(--bar-w, 60%);');
    expect(source.match(/\.skeleton-bar\.label\s*\{[^}]*\}/)![0]).toContain('width: 35%;');
    expect(source.match(/\.skeleton-bar\.value\s*\{[^}]*\}/)![0]).toContain('width: 60%;');
    expect(source).not.toContain('sb-shimmer');
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

/* v195 Phase 2: empty, loading and error each have one style, rendered in
 * the panel body. sb-async keeps the classes the workspace specs query
 * (.failed, .retry) and draws them exactly as sb-panel-error does; its
 * empty branch is sb-empty-state, reason included. */
describe('one empty, loading and error style (v195 Phase 2)', () => {
  const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
  const ASYNC = read('src/app/ui/async.ts');
  const ASYNC_STYLES = ASYNC.slice(ASYNC.indexOf('styles:')).replace(/\/\*[\s\S]*?\*\//g, '');
  const PANEL_ERROR = read('src/app/ui/panel-error.ts');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ruleIn = (source: string, selector: string) =>
    source.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const declarations = (rule: string) =>
    rule.slice(rule.indexOf('{') + 1, rule.lastIndexOf('}')).split(';').map((d) => d.trim()).filter(Boolean).sort();

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it("draws sb-async's error and Retry exactly like sb-panel-error's", () => {
    const error = ruleIn(PANEL_ERROR, '.error');
    expect(error).toContain('border-left: 2px solid var(--neg);');
    expect(error).toContain('background: var(--neg-soft);');
    expect(error).not.toContain('dashed');
    expect(declarations(ruleIn(ASYNC, '.failed'))).toEqual(declarations(error));
    expect(declarations(ruleIn(ASYNC, '.retry'))).toEqual(declarations(ruleIn(PANEL_ERROR, '.retry')));
    expect(declarations(ruleIn(ASYNC, '.retry:hover'))).toEqual(declarations(ruleIn(PANEL_ERROR, '.retry:hover')));
  });

  it('renders its empty state through sb-empty-state, reason included, and styles no second one', () => {
    const { el } = render({ empty: true, reason: 'measured-zero' });
    const reasons = [...el.querySelectorAll('.reason')];
    expect(reasons).toHaveLength(1);
    expect(reasons[0].closest('sb-empty-state')).not.toBeNull();
    expect(reasons[0].textContent!.trim()).toBe('Result: 0');
    expect(ASYNC_STYLES).not.toMatch(/\.empty-wrap|\.reason\b/);
  });

  it('paints skeleton bars in the strong rule colour and mixes none', () => {
    const bar = ASYNC.match(/\.skeleton-cell::before,\s*\.skeleton-bar\s*\{[^}]*\}/)![0];
    expect(bar).toContain('background: var(--border-strong);');
    expect(ASYNC).not.toContain('color-mix(');
  });

  it('pads a tiles skeleton like the KPI cell it stands in for (V195-11)', () => {
    expect(ruleIn(ASYNC, '.skeleton-tile')).toContain('padding: var(--space-10) var(--panel-pad);');
  });
});
