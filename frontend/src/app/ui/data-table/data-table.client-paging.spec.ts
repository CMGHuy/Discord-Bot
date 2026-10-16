import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { DataTable } from './data-table';
import { ColumnDef } from './data-table.types';

interface Row { id: string }
const columns: ColumnDef<Row>[] = [{ key: 'id', header: 'Id', value: (r) => r.id }];

describe('DataTable clientPaging (v167)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function build(count: number) {
    const f = TestBed.createComponent(DataTable<Row>);
    f.componentRef.setInput('rows', Array.from({ length: count }, (_, i) => ({ id: `r${i}` })));
    f.componentRef.setInput('columns', columns);
    f.componentRef.setInput('visible', ['id']);
    f.componentRef.setInput('rowKey', (r: Row) => r.id);
    f.componentRef.setInput('clientPaging', 'test-table');
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('slices to the desktop default and offers the rows dropdown', () => {
    const el = build(23);
    expect(el.querySelectorAll('tbody tr.row')).toHaveLength(10);
    expect(el.querySelector('.per-page select')).not.toBeNull();
    expect(el.querySelector('.range')!.textContent).toContain('1–10 of 23');
  });

  it('shows no pager at or below the smallest page size', () => {
    const el = build(5);
    expect(el.querySelectorAll('tbody tr.row')).toHaveLength(5);
    expect(el.querySelector('.bar')).toBeNull();
  });
});
