import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { EdgeTab } from './edge';
describe('EdgeTab',()=>{beforeEach(()=>TestBed.resetTestingModule());it('shows scoped rolling measures and all-time calibration',()=>{TestBed.configureTestingModule({providers:[provideZonelessChangeDetection(),{provide:AnalyticsStore,useValue:{scopeN:signal(30),performance:signal({win_rate:55,rolling_wr:[{date:'2026-08-01',win_rate:55}],rolling_exp_r:[{date:'2026-08-01',exp_r:.2}]}),strategies:signal({cumulative:{RSI:[{date:'2026-08-01',cum_r:1}]}}),calibration:signal({deciles:[{decile:'80-89',win_rate:83}]})}}]});const f=TestBed.createComponent(EdgeTab);f.detectChanges();const e=f.nativeElement as HTMLElement;expect(e.querySelectorAll('sb-line-chart').length).toBeGreaterThanOrEqual(2);expect(e.querySelector('sb-small-multiples')).not.toBeNull();expect(e.textContent).toContain('all-time');});});
