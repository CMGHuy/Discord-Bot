import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { CancelPlanRow } from '../../api/models';
import { CANCEL_PAYLOAD } from '../../testing/cancel-fixtures';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { CancelsTable } from './cancels-table';

function create(rows: CancelPlanRow[]): ComponentFixture<CancelsTable> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([]),
    ],
  });
  const fixture = TestBed.createComponent(CancelsTable);
  fixture.componentRef.setInput('rows', rows);
  fixture.detectChanges();
  return fixture;
}

const host = (f: ComponentFixture<CancelsTable>): HTMLElement => f.nativeElement;
const text = (el: Element | null): string => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
const bodyRows = (f: ComponentFixture<CancelsTable>): HTMLElement[] =>
  Array.from(host(f).querySelectorAll<HTMLElement>('sb-data-table tbody tr'))
    .filter((tr) => !tr.classList.contains('expansion'));

describe('CancelsTable', () => {
  it('lists one row per replayed cancel, a risk_cap plan twice', () => {
    const f = create(CANCEL_PAYLOAD.rows);
    expect(bodyRows(f).length).toBe(6);
    expect(text(bodyRows(f)[0])).toContain('risk_cap · trigger');
    expect(text(bodyRows(f)[0])).toContain('Setup lost (tie)');
    expect(text(bodyRows(f)[0])).toContain('−1.00R');
    expect(text(bodyRows(f)[1])).toContain('risk_cap · crossing (estimated)');
    expect(text(bodyRows(f)[1])).toContain('Setup reached TP1');
    expect(text(bodyRows(f)[1])).toContain('+1.00R');
  });

  it('shows ticker, strategy, badge tier, horizon, cancel date and cap-implied size', () => {
    const row = text(bodyRows(create(CANCEL_PAYLOAD.rows))[0]);
    for (const part of ['AAPL', 'EMA20', 'VALIDATED', '4w', '2026-10-20', '72.5%']) expect(row).toContain(part);
    expect(text(bodyRows(create(CANCEL_PAYLOAD.rows))[2])).toContain('Wrong cancel');
  });

  it('names an exclusion and shows no R for an excluded row', () => {
    const xom = text(bodyRows(create(CANCEL_PAYLOAD.rows))[5]);
    expect(xom).toContain('Excluded: split in window');
    expect(xom).toContain('other (never_triggered)');
    expect(xom).toContain('—');
    expect(xom).not.toMatch(/[+-]\d+\.\d{2}R/);
  });

  it('pages six rows and shows no pager at five or fewer', () => {
    expect(host(create(CANCEL_PAYLOAD.rows)).querySelector('sb-pagination')).not.toBeNull();
    expect(host(create(CANCEL_PAYLOAD.rows.slice(0, 5))).querySelector('sb-pagination')).toBeNull();
  });

  it('says so when the filter matches nothing', () => {
    expect(text(host(create([])))).toContain('No cancelled plans match this filter');
  });

  it('declares its phone compact row', () => {
    const cols = (create([]).componentInstance as unknown as { columns: () => ColumnDef<CancelPlanRow>[] }).columns();
    const slot = (key: string) => cols.find((c) => c.key === key)?.compact;
    expect(slot('ticker')).toEqual({ line: 1, order: 1 });
    expect(slot('verdict')).toEqual({ line: 1, order: 2 });
    expect(slot('cancel_date')).toEqual({ line: 2, order: 1 });
    expect(slot('r')).toEqual({ line: 2, order: 2 });
  });
});
