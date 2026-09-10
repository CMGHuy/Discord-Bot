import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { PnlCell } from './pnl-cell';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/pnl-cell.ts'), 'utf8');

@Component({
  imports: [PnlCell],
  template: `<sb-pnl-cell [pct]="pct()" [amount]="amount()" currency="€" />`,
})
class Host {
  readonly pct = signal<number | null>(4.2);
  readonly amount = signal<number | null>(9.8);
}

describe('PnlCell (v80 cell contract)', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const text = () => el().textContent!.replace(/\s+/g, ' ').trim();
  const cell = () => el().querySelector('.pnl') as HTMLElement;
  const set = (p: number | null, a: number | null) => {
    host.pct.set(p);
    host.amount.set(a);
    fixture.detectChanges();
  };

  it('reads the percentage and the amount together', () => {
    expect(text()).toBe('+4.20% (+9.80 €)');
  });

  it('colours a gain green', () => {
    expect(cell().classList).toContain('pos');
  });

  it('colours a loss red, with both figures signed', () => {
    set(-1.35, -6.1);
    expect(text()).toBe('-1.35% (-6.10 €)');
    expect(cell().classList).toContain('neg');
  });

  it('leaves an exact zero uncoloured', () => {
    set(0, 0);
    expect(text()).toBe('0.00% (0.00 €)');
    expect(cell().classList).not.toContain('pos');
    expect(cell().classList).not.toContain('neg');
  });

  it('is an em dash when there is nothing to price', () => {
    set(null, null);
    expect(text()).toBe('—');
    expect(cell()).toBeNull();
  });

  it('leaves an unknown amount out rather than printing "(—)"', () => {
    set(4.2, null);
    expect(text()).toBe('+4.20%');
    expect(el().querySelector('.amount')).toBeNull();
  });

  it('flashes when the percentage changes, never on first render', () => {
    expect(cell().classList).not.toContain('flash-up');
    set(5, 11.2);
    expect(cell().classList).toContain('flash-up');
  });

  it('keeps both figures on one line', () => {
    expect(SOURCE).toMatch(/\.pnl \{[^}]*white-space: nowrap/);
  });
});
