import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { EdgeTab } from './edge';
describe('EdgeTab',()=>{beforeEach(()=>TestBed.resetTestingModule());it('shows scoped rolling measures and all-time calibration',()=>{TestBed.configureTestingModule({providers:[provideZonelessChangeDetection(),{provide:AnalyticsStore,useValue:{scopeN:signal(30),performance:signal({win_rate:55,rolling_wr:[{date:'2026-08-01',win_rate:55}],rolling_exp_r:[{date:'2026-08-01',exp_r:.2}]}),strategies:signal({cumulative:{RSI:[{date:'2026-08-01',cum_r:1}]}}),calibration:signal({deciles:[{decile:'80-89',win_rate:83}]})}}]});const f=TestBed.createComponent(EdgeTab);f.detectChanges();const e=f.nativeElement as HTMLElement;expect(e.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);expect(e.querySelector('sb-small-multiples')).not.toBeNull();expect(e.textContent).toContain('all-time');});

  // A screenshot pass (v94 V2) once caught 2/3 * 100 = 66.66666... rendered
  // raw in the Calibration deciles panel, overflowing its container -- the
  // fix rounds a decile's win rate to one decimal before it reaches the bar.
  it('rounds a decile win rate instead of overflowing the panel with a raw float', () => {
    TestBed.configureTestingModule({providers:[provideZonelessChangeDetection(),{provide:AnalyticsStore,useValue:{scopeN:signal(30),performance:signal({win_rate:55,rolling_wr:[],rolling_exp_r:[]}),strategies:signal({cumulative:{}}),calibration:signal({deciles:[{decile:'60-69',win_rate:200/3}]})}}]});
    const f=TestBed.createComponent(EdgeTab);
    f.detectChanges();
    expect(f.componentInstance.decileBins()).toEqual([{ label: '60-69', count: 66.7 }]);
    expect((f.nativeElement as HTMLElement).textContent).not.toContain('66.66666');
  });
});

describe('edge.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/edge.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
