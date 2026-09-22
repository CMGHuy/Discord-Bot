import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { ExecutionTab } from './execution';

function render() {
  const quality = { exit_reasons: [{ reason: 'tp1', n: 40 }, { reason: 'other', n: 60 }], unmapped_reasons: [{ status: 'closed', text: '', n: 60 }], hold_by_outcome: { ratio: .48, severity: 'low', avg_winner_days: .31, avg_loser_days: .64 }, hold_points: [{ outcome: 'win', days: .31 }, { outcome: 'loss', days: .64 }], efficiency: { bins: [], n: 324, median: .429 }, mae: { bins: [], n: 0, median: null }, scatter: [], coverage: { mfe_r: { non_null: 555, total: 591, pct: 93.9 } }, min_cell_n: 20 };
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: { scopeN: signal(591), exitQuality: signal(quality), journal: signal({ digest: ['Wait for the retest.'] }) } }, { provide: PreferencesStore, useValue: { values: () => ({}) } }] });
  const fixture = TestBed.createComponent(ExecutionTab); fixture.detectChanges(); return { fixture, el: fixture.nativeElement as HTMLElement };
}
describe('ExecutionTab', () => { beforeEach(() => TestBed.resetTestingModule());
  it('leads with the four-number verdict before its charts', () => { const { el } = render(); expect(el.querySelector('.verdict')!.compareDocumentPosition(el.querySelector('sb-histogram')!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); expect(el.textContent).toContain('0.43'); expect(el.textContent).toContain('0.48'); });
  it('keeps unrecorded exits visible and uses hold strips', () => { const { fixture, el } = render(); expect((fixture.componentInstance as any).exitReasonSegments().find((x: any) => x.label === 'unrecorded')?.count).toBe(60); expect(el.querySelector('sb-strip-plot')).not.toBeNull(); expect(el.querySelector('sb-donut')).toBeNull(); });
});
