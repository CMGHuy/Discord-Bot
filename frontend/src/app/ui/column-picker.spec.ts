import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PreferencesStore } from '../stores/preferences.store';
import { ColumnPickerComponent, PickableColumn } from './column-picker';
import { Density } from './data-table/data-table.types';
import { readTableColumns } from './table-prefs';

/* NG39 — the column picker.
 *
 * The three constraints spec v14 puts on this component are the tests: reset
 * is always available, the default set is its own thing, and there is no way
 * to express an order. Persistence is asserted against the real
 * `PreferencesStore` with a faked HTTP backend, because the thing worth
 * checking is that it calls `resetColumns` (forget) rather than `setColumns`
 * (store the defaults as a choice) — a distinction a mock would let through.
 */

const COLUMNS: PickableColumn[] = [
  { key: 'num', header: '#' },
  { key: 'status', header: 'Status' },
  { key: 'ticker', header: 'Ticker' },
  { key: 'pnl', header: 'P&L %' },
];

const DEFAULTS = ['num', 'status', 'ticker'];
const ALL_KEYS = COLUMNS.map((c) => c.key);

@Component({
  imports: [ColumnPickerComponent],
  template: `
    <sb-column-picker
      [density]="density"
      tableId="trades"
      [columns]="columns"
      [defaults]="defaults"
      [visible]="visible()"
      (visibleChange)="emitted.push($event); visible.set($event)"
    />
  `,
})
class Host {
  readonly columns = COLUMNS;
  readonly defaults = DEFAULTS;
  readonly density: Density = 'compact';
  readonly visible = signal<string[]>([...DEFAULTS]);
  readonly emitted: string[][] = [];
}

describe('ColumnPickerComponent', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let preferences: InstanceType<typeof PreferencesStore>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    preferences = TestBed.inject(PreferencesStore);
    fixture.detectChanges();

    (fixture.nativeElement.querySelector('.trigger') as HTMLButtonElement).click();
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const boxes = () =>
    [...el().querySelectorAll('.panel input[type=checkbox]')] as HTMLInputElement[];
  const labels = () =>
    [...el().querySelectorAll('.panel label span')].map((s) => s.textContent!.trim());

  it('lists every column, not only the visible ones', () => {
    expect(labels()).toEqual(['#', 'Status', 'Ticker', 'P&L %']);
    expect(boxes().map((b) => b.checked)).toEqual([true, true, true, false]);
  });

  it('lists them in the table order and offers no way to reorder', () => {
    // Constraint 2. If this ever fails because a control was added, the table
    // still has no ordering input, so the control would be a lie.
    expect(labels()).toEqual(COLUMNS.map((c) => c.header));
    expect(el().querySelectorAll('[draggable=true]')).toHaveLength(0);
    expect(el().querySelector('.panel button:not(.reset)')).toBeNull();
  });

  it('adds a hidden column and emits in table order, not click order', () => {
    boxes()[3].click();
    fixture.detectChanges();

    expect(host.emitted.at(-1)).toEqual(['num', 'status', 'ticker', 'pnl']);
  });

  it('removes a visible column', () => {
    boxes()[1].click();
    fixture.detectChanges();

    expect(host.emitted.at(-1)).toEqual(['num', 'ticker']);
  });

  it('persists the choice against the table id', () => {
    boxes()[3].click();
    fixture.detectChanges();

    // Read through the SR12 helper, not the pre-SR12 store method: the
    // picker now stores per density, so 'what did trades save' is a question
    // about a (table, density) pair.
    expect(readTableColumns(preferences.values(), 'trades', 'compact', ALL_KEYS))
      .toEqual(['num', 'status', 'ticker', 'pnl']);
    // A table nobody touched still reports its baseline.
    expect(readTableColumns(preferences.values(), 'watchlist', 'compact', ALL_KEYS))
      .toEqual(ALL_KEYS);
  });

  it('will not let the last visible column be unchecked', () => {
    // An empty table is not a column preference, it is a broken screen whose
    // only way back is this same menu.
    host.visible.set(['ticker']);
    fixture.detectChanges();

    const ticker = boxes()[2];
    expect(ticker.disabled).toBe(true);

    ticker.click();
    fixture.detectChanges();
    expect(host.visible()).toEqual(['ticker']);
  });

  it('always offers a reset, even when nothing has been changed', () => {
    // Constraint 1: the designed state is reachable in one click at all times,
    // not only once the picker notices it has been departed from.
    expect(host.visible()).toEqual(DEFAULTS);
    expect(el().querySelector('.reset')).not.toBeNull();
  });

  it('resets to the defaults input rather than to the current set', () => {
    boxes()[3].click();
    fixture.detectChanges();
    expect(host.visible()).toHaveLength(4);

    (el().querySelector('.reset') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(host.emitted.at(-1)).toEqual(DEFAULTS);
  });

  it('forgets the preference on reset instead of storing the defaults', () => {
    // Storing them would freeze today's designed columns forever: a table
    // that later gains a default column would not show it to anyone who had
    // ever pressed reset.
    boxes()[3].click();
    fixture.detectChanges();
    expect(preferences.values()['tables.trades.compact.columns']).toBeDefined();

    (el().querySelector('.reset') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(preferences.values()['tables.trades.compact.columns']).toBeUndefined();
  });

  it('reports how many of the columns are showing', () => {
    expect(el().querySelector('.count')!.textContent!.trim()).toBe('3/4');
  });
});
