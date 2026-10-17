import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { PlanCard, PlanFigures, gapNoteApplies, planRows, restingStopLine, rrLine } from './plan-card';

const base: PlanFigures = { direction: 'bullish', status: 'PARTIAL', entryType: 'stop_entry',
  trigger: 101, entry: 100, riskStop: 95, stopLoss: 99, workingStop: 100,
  target1: 110, target2: 120, acceptance: 98, riskReward: 2.18, riskPerShare: 2.49, rewardPerShare: 5.42 };

describe('PlanCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('keeps original risk, working stop and signed distances distinct', () => {
    const rows = planRows(base);
    expect(rows.map(row => row.level)).toEqual(['Order', 'Trigger', 'Entry', 'Stop', 'Working stop', 'Target 1', 'Target 2', 'Acceptance']);
    expect(rows[0]).toMatchObject({ price: null, note: 'Buy stop 101.00', pctFromEntry: null });
    expect(rows[3]).toMatchObject({ price: 95, pctFromEntry: -5, tone: 'neg' });
    expect(rows[4]).toMatchObject({ price: 100, note: '(was 95.00)', tone: null });
    expect(rows[5]).toMatchObject({ pctFromEntry: 10, tone: 'pos' });
    expect(rows[2].pctFromEntry).toBeNull();
  });
  it('omits unavailable optional rows and suppresses ambiguous legacy working stops', () => {
    const legacy = { ...base, trigger: 100, riskStop: null, target2: null, acceptance: null };
    expect(planRows(legacy).map(row => row.level)).toEqual(['Order', 'Entry', 'Stop', 'Target 1']);
    expect(planRows(legacy)[2].price).toBe(99);
    expect(restingStopLine(legacy)).toBeNull();
    expect(gapNoteApplies(legacy)).toBe(false);
    expect(planRows({ ...base, entry: 0 }).every(row => row.pctFromEntry === null)).toBe(true);
  });
  it.each(['ACTIVE', 'PARTIAL', 'CLOSED', 'PENDING'])('limits the stop cue for %s', status => {
    expect(restingStopLine({ ...base, status })).toBe(['ACTIVE', 'PARTIAL'].includes(status) ? 'Move your resting stop to 100.00' : null);
    expect(restingStopLine({ ...base, status, workingStop: 95 })).toBeNull();
  });
  it('renders ratio context only when known', () => {
    expect(rrLine(base)).toBe('R:R 2.18 · risk 2.49 / reward 5.42 per share');
    expect(rrLine({ ...base, riskPerShare: null })).toBe('R:R 2.18');
    expect(rrLine({ ...base, rewardPerShare: null })).toBe('R:R 2.18');
    expect(rrLine({ ...base, riskReward: null })).toBeNull();
  });
  it('renders one panel with actionable notes and table-local scrolling', () => {
    const f = TestBed.createComponent(PlanCard);
    f.componentRef.setInput('figures', base); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelectorAll('sb-panel')).toHaveLength(1);
    expect(el.querySelector('h2')?.textContent).toBe('Plan');
    expect(el.querySelector('.table-scroll table.levels')).not.toBeNull();
    expect(el.querySelector('[data-level="Working stop"]')?.textContent).toContain('(was 95.00)');
    expect(el.querySelector('.resting-stop')?.textContent).toContain('Move your resting stop to 100.00');
    expect(el.querySelector('.gap-line')?.textContent).toContain('A gap through the trigger fills at the open, not at entry.');
    expect(el.querySelector('.paper-line')?.textContent).toContain('Paper plan — this page places no orders.');
    f.componentRef.setInput('figures', { ...base, riskReward: null, trigger: 100, workingStop: 95 }); f.detectChanges();
    expect(el.querySelector('.resting-stop, .gap-line, .rr-line')).toBeNull();
  });
});
