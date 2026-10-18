import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { Leg } from '../../stores/trade-detail.store';
import { OutcomeCard, legRows } from './outcome-card';

const legs: Leg[] = [
  { fraction: 0.5, exitPrice: 110, r: 2, reason: 'TP1' },
  { fraction: 0.5, exitPrice: 100, r: 0, reason: 'runner_be' },
];

describe('OutcomeCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('formats leg shares, mapped reasons and neutral near-zero R', () => {
    expect(legRows(legs)).toEqual([
      { share: '50%', exit: '110.00', r: '+2.00R', tone: 'pos', reason: 'TP1' },
      { share: '50%', exit: '100.00', r: '0.00R', tone: null, reason: 'Runner at breakeven' },
    ]);
    expect(legRows([{ ...legs[0], r: -0.05, reason: 'custom reason' }])[0])
      .toMatchObject({ tone: null, reason: 'custom reason' });
    expect(legRows([{ ...legs[0], r: -1 }])[0].tone).toBe('neg');
  });
  it('keeps an unfinished leg visible without claiming a settled result', () => {
    expect(legRows([{ fraction: null, exitPrice: null, r: 2, reason: 'TP1' }])).toEqual([
      { share: '—', exit: '—', r: '—', tone: null, reason: '—' },
    ]);
    expect(legRows([{ ...legs[0], r: null, reason: null }])[0]).toMatchObject({ r: '—', tone: null, reason: '—' });
  });
  it.each(['open', 'pending', 'closed', 'unfilled'])('keeps the timeline and selects the right content for %s', group => {
    const f = TestBed.createComponent(OutcomeCard);
    f.componentRef.setInput('group', group);
    f.componentRef.setInput('direction', 'bearish');
    f.componentRef.setInput('target2', 90);
    f.componentRef.setInput('stopLoss', 105);
    f.componentRef.setInput('legs', legs);
    f.componentRef.setInput('timeline', [{ status: 'PENDING', reason: 'created', at: null }]);
    f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelector('sb-outcome-path')?.textContent).toContain('PENDING');
    expect(el.querySelector('sb-outcome-path')?.textContent).not.toContain('Scale-out');
    expect(el.querySelector('sb-if-it-gets-there') !== null).toBe(group === 'open' || group === 'pending');
    expect(el.querySelectorAll('table.legs tbody tr')).toHaveLength(group === 'closed' ? 2 : 0);
    if (group === 'closed') {
      expect(el.querySelector('.table-scroll table.legs')).not.toBeNull();
      expect(el.querySelector('table.legs')?.textContent).toContain('Runner at breakeven');
    }
  });
  it('shows a single exit leg and hides an empty exit panel', () => {
    const f = TestBed.createComponent(OutcomeCard);
    f.componentRef.setInput('group', 'closed');
    f.componentRef.setInput('legs', [legs[0]]); f.detectChanges();
    expect(f.nativeElement.querySelectorAll('table.legs tbody tr')).toHaveLength(1);
    f.componentRef.setInput('legs', []); f.detectChanges();
    expect(f.nativeElement.querySelector('table.legs')).toBeNull();
  });
});
