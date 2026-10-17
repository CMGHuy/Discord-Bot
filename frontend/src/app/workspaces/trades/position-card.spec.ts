import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { PositionCard, PositionFigures, positionRows } from './position-card';

const base: PositionFigures = { status: 'PARTIAL', shares: 3, positionValue: 300, dollarAtRisk: 7.47,
  sizingMode: 'risk', gapP90Pct: 1.25, gapFragile: true, tp1Pct: 50, breakevenTriggerPct: 60,
  trailAtrMult: 1.5, expiresOn: '2026-10-20', timeExitOn: '2026-10-21', holdCapBars: 10 };

describe('PositionCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('labels partial risk at the original stop and formats sizing and management rows', () => {
    const rows = positionRows(base);
    expect(rows.map(row => row.label)).toEqual(['Open shares', 'Deployed', '$ at risk', 'Sizing mode', 'Gap risk (p90)', 'TP1 closes', 'Break-even at', 'Trail', 'Expires on', 'Time exit on', 'Hold cap']);
    expect(rows[0].value).toBe('3');
    expect(rows[2]).toMatchObject({ value: '7.47', sub: 'open shares, at original stop' });
    expect(rows[4]).toMatchObject({ value: '1.25%', fragile: true });
    expect(rows[5].value).toBe('50%');
    expect(rows[6].value).toBe('60% of TP1');
    expect(rows[7].value).toBe('1.5 × ATR');
    expect(rows[10].value).toBe('10 bars');
    expect(positionRows({ ...base, status: 'ACTIVE' })[0].label).toBe('Shares');
    expect(positionRows({ ...base, status: 'ACTIVE' })[2].sub).toBeNull();
  });
  it('hides null rows while retaining real zeros', () => {
    const absent = Object.fromEntries(Object.keys(base).map(key => [key, null])) as unknown as PositionFigures;
    expect(positionRows(absent)).toEqual([]);
    expect(positionRows({ ...absent, shares: 0, dollarAtRisk: 0, tp1Pct: 0, holdCapBars: 0 }).map(row => row.value)).toEqual(['0', '0.00', '0%', '0 bars']);
  });
  it('shows the fragile chip with gap risk and explains only absent snapshots', () => {
    const f = TestBed.createComponent(PositionCard);
    f.componentRef.setInput('figures', base); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelector('h2')?.textContent).toBe('Position');
    expect(el.querySelector('[data-row="$ at risk"]')?.textContent).toContain('open shares, at original stop');
    expect(el.querySelector('sb-chip')?.textContent).toContain('fragile');
    expect(el.querySelector('.section-help')).toBeNull();
    f.componentRef.setInput('figures', { ...base, sizingMode: null, gapFragile: false }); f.detectChanges();
    expect(el.querySelector('.section-help')?.textContent).toContain('Position size is snapshotted when the trade opens. A trade with no sizing snapshot was logged before that feature existed.');
    expect(el.querySelector('sb-chip')).toBeNull();
  });
});
