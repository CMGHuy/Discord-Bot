import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PageSpec } from './data-table/data-table.types';
import { PaginationComponent } from './pagination';

/* NG39 — the pager. Every assertion here is really about one thing: the
 * numbers come from `total`, which is the post-filter pre-slice count, and
 * never from anything the pager can see on screen.
 */

@Component({
  imports: [PaginationComponent],
  template: `<sb-pagination [pagination]="spec()" (pageChange)="pages.push($event)" />`,
})
class Host {
  readonly spec = signal<PageSpec>({ total: 90, page: 1, perPage: 25 });
  readonly pages: number[] = [];
}

describe('PaginationComponent', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const buttons = () => [...el().querySelectorAll('button')] as HTMLButtonElement[];
  const range = () => el().querySelector('.range')!.textContent!.trim();

  it('renders nothing when everything fits on one page', () => {
    host.spec.set({ total: 12, page: 1, perPage: 25 });
    fixture.detectChanges();

    expect(el().querySelector('.pager')).toBeNull();
  });

  it('counts pages from the total, not from the rows on screen', () => {
    expect(el().querySelector('.of')!.textContent).toContain('1 / 4');
  });

  it('shows the range of the current page', () => {
    expect(range()).toBe('1–25 of 90');

    host.spec.set({ total: 90, page: 3, perPage: 25 });
    fixture.detectChanges();
    expect(range()).toBe('51–75 of 90');
  });

  it('clamps the last page to the total rather than overshooting it', () => {
    host.spec.set({ total: 90, page: 4, perPage: 25 });
    fixture.detectChanges();

    expect(range()).toBe('76–90 of 90');
  });

  it('emits the target page', () => {
    buttons()[1].click();
    expect(host.pages).toEqual([2]);

    host.spec.set({ total: 90, page: 2, perPage: 25 });
    fixture.detectChanges();
    buttons()[0].click();
    expect(host.pages).toEqual([2, 1]);
  });

  it('disables previous on the first page and next on the last', () => {
    expect(buttons()[0].disabled).toBe(true);
    expect(buttons()[1].disabled).toBe(false);

    host.spec.set({ total: 90, page: 4, perPage: 25 });
    fixture.detectChanges();
    expect(buttons()[0].disabled).toBe(false);
    expect(buttons()[1].disabled).toBe(true);
  });

  it('emits nothing when a disabled end is clicked anyway', () => {
    buttons()[0].click();
    expect(host.pages).toEqual([]);
  });

  it('survives a perPage of zero without dividing by it', () => {
    host.spec.set({ total: 90, page: 1, perPage: 0 });
    fixture.detectChanges();

    expect(el().querySelector('.pager')).toBeNull();
  });
});

// --- SR15: the per-page selector -----------------------------------------

describe('PaginationComponent per-page selector', () => {
  function build(perPage: number, total: number, showPerPage: boolean) {
    const f = TestBed.createComponent(PaginationComponent);
    f.componentRef.setInput('pagination', { page: 1, perPage, total });
    f.componentRef.setInput('showPerPage', showPerPage);
    f.detectChanges();
    return f;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('is absent unless the table opts in', () => {
    const el = build(25, 100, false).nativeElement as HTMLElement;
    expect(el.querySelector('select')).toBeNull();
  });

  it('offers 10 / 25 / 50 / All', () => {
    const el = build(25, 100, true).nativeElement as HTMLElement;
    const options = [...el.querySelectorAll('option')].map((o) => o.textContent!.trim());
    expect(options).toEqual(['10', '25', '50', 'All']);
  });

  it('emits 0 for All', () => {
    const f = build(25, 100, true);
    const emitted: number[] = [];
    f.componentInstance.perPageChange.subscribe((v: number) => emitted.push(v));
    const select = (f.nativeElement as HTMLElement).querySelector('select')!;
    (select as HTMLSelectElement).value = '0';
    select.dispatchEvent(new Event('change'));
    expect(emitted).toEqual([0]);
  });

  it('stays visible when All collapses the list to one page', () => {
    // The trap this guards: nested inside the pager, choosing All removes the
    // pager and with it the only control that could undo the choice.
    const el = build(0, 3, true).nativeElement as HTMLElement;
    expect(el.querySelector('.pager')).toBeNull();
    expect(el.querySelector('select')).not.toBeNull();
  });
});
