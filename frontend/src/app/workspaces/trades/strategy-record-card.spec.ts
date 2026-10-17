import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { StrategyRow } from '../../api/models';
import { StrategyRecordCard } from './strategy-record-card';

const row: StrategyRow = { strategy: 'VWAP', status: 'WEAK', n: 30, win_rate: 40, expectancy_r: 0.25, window: '2026', run_date: null, live_n: 0, live_wr: null, delta_vs_oos: null, decayed: true, evidence_decay: 'unknown', gate_description: null, win_rate_series: [] };

describe('StrategyRecordCard', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('preserves the Strategy tab labels, formatters and decay warning', () => {
    const f = TestBed.createComponent(StrategyRecordCard);
    f.componentRef.setInput('strategy', 'VWAP'); f.componentRef.setInput('row', row); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelector('h2')?.textContent).toBe('Strategy record');
    expect([...el.querySelectorAll('dt')].map(dt => dt.textContent)).toEqual(['Strategy', 'Status', 'OOS sample', 'OOS win rate', 'OOS expectancy', 'Live sample', 'Live win rate', 'Live vs OOS', 'Window']);
    expect([...el.querySelectorAll('dd')].map(dd => dd.textContent)).toEqual(['VWAP', 'WEAK', '30.00', '+40.00%', '0.25R', '0.00', '—', '—', '2026']);
    expect(el.querySelector('.decayed')?.textContent?.trim()).toBe("Live results have decayed against this strategy's out-of-sample record.");
    f.componentRef.setInput('row', { ...row, decayed: false }); f.detectChanges();
    expect(el.querySelector('.decayed')).toBeNull();
  });
  it('prioritises errors, then missing strategy, then missing registry entry', () => {
    const f = TestBed.createComponent(StrategyRecordCard); f.detectChanges();
    const el: HTMLElement = f.nativeElement;
    expect(el.querySelector('.record-state')?.textContent).toBe('This position has no strategy recorded.');
    f.componentRef.setInput('strategy', 'VWAP'); f.detectChanges();
    expect(el.querySelector('.record-state')?.textContent).toBe('The registry has no entry for VWAP.');
    f.componentRef.setInput('error', 'Registry unavailable'); f.componentRef.setInput('row', row); f.detectChanges();
    expect(el.querySelector('.record-state')?.textContent).toBe('Registry unavailable');
    expect(el.querySelector('dl')).toBeNull();
  });
});
