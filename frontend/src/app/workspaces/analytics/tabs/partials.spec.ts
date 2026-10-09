import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AnalyticsPartials } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import {
  PartialsTab, funnelRows, givebackBins, kpiTiles, ladderRows, monthTrend, outcomeSegments,
  runnerWaterfall, splitRows, touchRows,
} from './partials';
import { PARTIALS_FIXTURE } from './partials.fixture';

function render(payload: AnalyticsPartials | null, error: string | null = null) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: AnalyticsStore, useValue: { partials: signal(payload), partialsError: signal(error), reload: () => {} } },
      { provide: PreferencesStore, useValue: { values: () => ({}) } },
    ],
  });
  const fixture = TestBed.createComponent(PartialsTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('partials helpers', () => {
  it('leads the KPI row with the five figures, the hero marked', () => {
    const tiles = kpiTiles(PARTIALS_FIXTURE);
    expect(tiles.map((t) => t.label)).toEqual(
      ['TP1 rate', 'TP1 → TP2', 'Runner beat all-out', 'Mean runner ΔR', 'Median TP1 → exit']);
    expect(tiles.filter((t) => t.hero).map((t) => [t.value, t.sample, t.tone])).toEqual([['80.0%', 5, 'pos']]);
    expect(tiles[3].value).toBe('+0.32R');
  });

  it('draws the funnel as a share of filled trades, keeping each count', () => {
    expect(funnelRows(PARTIALS_FIXTURE).map((r) => [r.label, r.value, r.n])).toEqual([
      ['Filled', 100, 8], ['Hit TP1', 75, 6], ['Runner closed', 62.5, 5], ['Hit TP2', 12.5, 1]]);
  });

  it('labels each outcome with its average runner R', () => {
    const segments = outcomeSegments(PARTIALS_FIXTURE);
    expect(segments[0]).toEqual({ label: 'TP2 +4.00R', count: 1, tone: 'pos' });
    expect(segments.find((s) => s.label.startsWith('Open'))?.label).toBe('Open —');
  });

  it('builds the waterfall from all-out to actual ExpR', () => {
    const [allOut, runner] = runnerWaterfall(PARTIALS_FIXTURE);
    expect(allOut).toEqual({ label: 'All-out at TP1', value: 2 });
    expect(runner.value).toBeCloseTo(0.324, 6);
  });

  it('draws one ladder bar per TP2 level, then the actual setup', () => {
    expect(ladderRows(PARTIALS_FIXTURE)).toEqual([
      { label: 'TP2 at 1.5R', value: 1.75, n: 4 }, { label: 'TP2 at 2.0R', value: 2, n: 4 },
      { label: 'TP2 at 2.5R', value: 2.25, n: 4 }, { label: 'TP2 at 3.0R', value: 2.2175, n: 4 },
      { label: 'TP2 at 4.0R', value: 2.3425, n: 4 }, { label: 'Actual', value: 2.324, n: 5 }]);
    expect(touchRows(PARTIALS_FIXTURE).map((r) => [r.label, r.value])).toEqual([
      ['1.5R', 100], ['2.0R', 100], ['2.5R', 100], ['3.0R', 50], ['4.0R', 25]]);
  });

  it('labels the split rows by the share taken at TP1', () => {
    expect(splitRows(PARTIALS_FIXTURE).map((r) => r.label)).toEqual(['33% at TP1', '50% at TP1', '67% at TP1']);
  });

  it('bins giveback in half-R steps, keeping empty bins between', () => {
    expect(givebackBins([0.2, 1.26, 0.6, 0.4])).toEqual([
      { label: '0.0–0.5R', count: 2 }, { label: '0.5–1.0R', count: 1 }, { label: '1.0–1.5R', count: 1 }]);
    expect(givebackBins([])).toEqual([]);
  });

  it('trends the hero figure by month', () => {
    expect(monthTrend(PARTIALS_FIXTURE.breakdowns.month)[0].points).toEqual([
      { date: '2026-09-01', value: 75 }, { date: '2026-10-01', value: 80 }]);
  });
});

describe('PartialsTab', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('renders every panel from one payload, hero first among the KPIs', () => {
    const { el } = render(PARTIALS_FIXTURE);
    expect(el.querySelector('sb-line-chart')).toBeNull();            // ladder is a bar list
    expect(el.querySelectorAll('sb-stat-tile')).toHaveLength(5);
    expect(el.querySelector('.tile.hero')?.textContent).toContain('Runner beat all-out');
    for (const selector of ['sb-share-bar', 'sb-waterfall', 'sb-histogram', 'sb-strip-plot', 'sb-segmented']) {
      expect(el.querySelector(selector)).not.toBeNull();
    }
    expect(el.querySelector('.footer')?.textContent).toContain('1 closed runners without a price path');
    expect(el.querySelector('.footer')?.textContent).toContain('not a gate');
  });

  it('dims thin breakdown rows and switches dimension in place', () => {
    const { fixture, el } = render(PARTIALS_FIXTURE);
    expect(el.querySelectorAll('tr.thin')).toHaveLength(2);           // MACD and RSI, both N < 10
    (fixture.componentInstance as PartialsTab).dimension.set('month');
    fixture.detectChanges();
    const rows = [...el.querySelectorAll('.breakdown tbody tr')];
    expect(rows.map((r) => r.classList.contains('thin'))).toEqual([false, true]);
    expect(el.querySelectorAll('sb-line-chart')).toHaveLength(1);    // the month trend only
  });

  it('shows the empty state when the scope holds no partial trade', () => {
    const empty = { ...PARTIALS_FIXTURE, population: { filled: 3, partial: 0, unreadable: 0 } };
    const { el } = render(empty);
    expect(el.querySelector('sb-empty-state')).not.toBeNull();
    expect(el.querySelector('sb-stat-tile')).toBeNull();
  });

  it('shows its own error with a retry', () => {
    const { el } = render(null, 'boom');
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
  });
});

describe('partials.ts breakpoints', () => {
  it('uses only declared breakpoint values in width queries', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/partials.ts'), 'utf8');
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.length).toBeGreaterThan(0);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
