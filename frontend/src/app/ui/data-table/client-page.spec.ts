import { signal } from '@angular/core';
import { describe, expect, it } from 'vitest';
import { createClientPage } from './client-page';

describe('createClientPage', () => {
  it('slices to the requested page size', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    expect(page.visible()).toEqual(Array.from({ length: 10 }, (_, i) => i));
  });

  it('pageSpec.total is the pre-slice count, not visible().length', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    expect(page.pageSpec()).toEqual({ total: 30, page: 1, perPage: 10 });
  });

  it('setPage moves the window', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    page.setPage(2);
    expect(page.visible()).toEqual(Array.from({ length: 10 }, (_, i) => i + 10));
  });

  it('a row set shrinking below the current page clamps back rather than showing nothing', () => {
    const rows = signal(Array.from({ length: 30 }, (_, i) => i));
    const page = createClientPage(rows, 10);
    page.setPage(3); // rows 20-29
    rows.set(Array.from({ length: 15 }, (_, i) => i)); // only 2 pages now
    expect(page.page()).toBe(2);
    expect(page.visible()).toEqual(Array.from({ length: 5 }, (_, i) => i + 10));
  });
});
