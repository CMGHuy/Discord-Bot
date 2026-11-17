import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { ExecutionTab, exclusionCaption } from './execution';
import { OVERRIDE_FIDELITY_FIXTURE } from './override-fidelity.fixture';

function render(overrides: Record<string, unknown> = {}) {
  const quality = { exit_reasons: [{ reason: 'tp1', n: 40 }, { reason: 'other', n: 60 }], unmapped_reasons: [{ status: 'closed', text: '', n: 60 }], hold_by_outcome: { ratio: .48, severity: 'low', avg_winner_days: .31, avg_loser_days: .64 }, hold_points: [{ outcome: 'win', days: .31 }, { outcome: 'loss', days: .64 }], efficiency: { bins: [], n: 324, median: .429 }, mae: { bins: [], n: 0, median: null }, scatter: [], coverage: { mfe_r: { non_null: 555, total: 591, pct: 93.9 } }, min_cell_n: 20, ...overrides };
  TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), { provide: AnalyticsStore, useValue: { scopeN: signal(591), exitQuality: signal(quality), exitQualityError: signal(null), reload: () => {}, journal: signal({ digest: ['Wait for the retest.'] }), overrideFidelity: signal(OVERRIDE_FIDELITY_FIXTURE), overrideFidelityError: signal(null) } }, { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } }] });
  const fixture = TestBed.createComponent(ExecutionTab); fixture.detectChanges(); return { fixture, el: fixture.nativeElement as HTMLElement };
}
describe('ExecutionTab', () => { beforeEach(() => TestBed.resetTestingModule());
  it('leads with the four-number verdict before its charts', () => { const { el } = render(); expect(el.querySelector('.verdict')!.compareDocumentPosition(el.querySelector('sb-histogram')!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); expect(el.textContent).toContain('0.43'); expect(el.textContent).toContain('0.48'); });
  it('keeps unrecorded exits visible and uses hold strips', () => { const { fixture, el } = render(); expect((fixture.componentInstance as any).exitReasonSegments().find((x: any) => x.label === 'unrecorded')?.count).toBe(60); expect(el.querySelector('sb-strip-plot')).not.toBeNull(); expect(el.querySelector('sb-donut')).toBeNull(); });
  it('mounts Overrides vs engine full width after the verdict, before the charts', () => { const { el } = render(); const panel = el.querySelector('sb-override-fidelity-panel')!; expect(panel).not.toBeNull(); expect(panel.parentElement?.classList.contains('panels')).toBe(false); expect(el.querySelector('.verdict')!.compareDocumentPosition(panel)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); expect(panel.compareDocumentPosition(el.querySelector('sb-histogram')!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING); });
});

const EXCURSION = { sources: { '5min': 300, daily: 280, none: 11 }, included: 340, excluded: 240, total: 591 };

describe('exclusionCaption (v228)', () => {
  it('says how many trades fed the panel and how many short daily holds it left out', () => {
    expect(exclusionCaption({ sources: {}, included: 351, excluded: 240, total: 591 }))
      .toBe('351 of 591 trades; 240 short holds on daily bars excluded');
  });

  it('names entries without figures apart, never as short daily holds', () => {
    // 591 - 340 - 240 = 11 entries had no bars at all: no source, short hold.
    expect(exclusionCaption(EXCURSION))
      .toBe('340 of 591 trades; 240 short holds on daily bars excluded; 11 without excursion figures');
  });

  it('still states a zero exclusion, so the reader knows the rule ran', () => {
    expect(exclusionCaption({ sources: { '5min': 12 }, included: 12, excluded: 0, total: 12 }))
      .toBe('12 of 12 trades; 0 short holds on daily bars excluded');
  });

  it('says nothing for an empty scope or a server older than v228', () => {
    expect(exclusionCaption({ sources: {}, included: 0, excluded: 0, total: 0 })).toBeNull();
    expect(exclusionCaption(undefined)).toBeNull();
  });
});

describe('ExecutionTab — trust-rule disclosure (v228)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('captions the Exit efficiency panel under its histogram', () => {
    const { el } = render({ excursion: EXCURSION });
    const caption = el.querySelector('sb-histogram + .caption');
    expect(caption?.textContent?.trim())
      .toBe('340 of 591 trades; 240 short holds on daily bars excluded; 11 without excursion figures');
    // Inside the Exit efficiency panel, not the verdict card (which also says "Exit efficiency").
    const panel = caption!.closest('sb-panel')!;
    expect(panel.querySelector('sb-histogram')).not.toBeNull();
    expect(panel.querySelector('.verdict')).toBeNull();
  });

  it('carries the excluded count in the verdict card hint', () => {
    const { fixture } = render({ excursion: EXCURSION });
    const efficiency = (fixture.componentInstance.verdict() as { label: string; hint: string }[])
      .find((v) => v.label === 'Exit efficiency')!;
    expect(efficiency.hint).toBe('N=324 · 240 short holds on daily bars excluded');
  });

  it('keeps the old panel and hint when the server sends no excursion block', () => {
    const { fixture, el } = render();
    expect(el.querySelector('sb-histogram + .caption')).toBeNull();
    const efficiency = (fixture.componentInstance.verdict() as { label: string; hint: string }[])
      .find((v) => v.label === 'Exit efficiency')!;
    expect(efficiency.hint).toBe('N=324');
  });

  it('shows no caption for an empty scope', () => {
    const { el } = render({ excursion: { sources: {}, included: 0, excluded: 0, total: 0 } });
    expect(el.querySelector('sb-histogram + .caption')).toBeNull();
  });
});

describe('execution.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    // A media query at 800px puts this file and ViewportService on
    // different scales -- see breakpoints.ts. v95 A7.
    const src = readFileSync(
      join(process.cwd(), 'src/app/workspaces/analytics/tabs/execution.ts'),
      'utf8',
    );
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
