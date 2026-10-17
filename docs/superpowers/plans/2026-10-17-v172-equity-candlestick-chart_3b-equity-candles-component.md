# v172 Equity candlestick chart, part 3b: the `sb-equity-candles` component and its wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V172-9:" -A 400 docs/superpowers/plans/2026-10-17-v172-equity-candlestick-chart_3b-equity-candles-component.md`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md) (its `## Corrections from the code brief` win: currency from `connection.currency()`, viewer prefs through the server-backed `PreferencesStore`, account label "Paper account · before tax and costs", the `portfolio-value.spec.ts` "no `1W`" assertion is replaced)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md) — **Global Constraints (UI copy and UI behaviour above all), Parallelisation, the task ledger and `$WT`/`$R` are defined there.** Split from part 3 (`_3-dashboard-ui-release.md`, V172-8) to keep each file under 1500 lines; the API contract summary at the top of part 3 applies here too.

`$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-17-v172-equity-candlestick-chart`, `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths, `git -C $WT` and `npm --prefix $WT/frontend`. One frontend spec runs with `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/<path>.spec.ts`.

# Phase 3 — Dashboard UI (continued)

### Task V172-9: `sb-equity-candles`: chart, hollow approx candles, seam marker, caption, readout, states

**Model:** sonnet — one chart component following `trade-chart.ts`

**Files:**
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`
- Create: `frontend/src/app/ui/chart/primitives/vline-primitive.ts`
- Create: `frontend/src/app/ui/chart/primitives/vline-primitive.spec.ts`
- Create: `frontend/src/app/testing/equity-candles-store.stub.ts` (test helper, reused by V172-10)
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`
- Create: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`

**Interfaces:**
- Consumes (V172-8): `EquityCandle`, `EquityCandlesResponse`, `EquityTimeframe`, `EquityBasis` (`api/models.ts`); `EquityCandlesStore` with `tf()`, `basis()`, `data()`, `loading()`, `error()`, `load()`, `setTimeframe()`, `setBasis()`. Existing: `chartOptions`, `chartPalette`, `token` (`ui/chart/chart-theme.ts`), `Async` (`ui/async.ts`, selector `sb-async`), `money`, `num`, `pct` (`ui/format.ts`), `installMatchMediaPolyfill` (`testing/match-media-polyfill.ts`).
- Produces (consumed by V172-10):
  - Component `EquityCandles`, selector `sb-equity-candles`, injects `EquityCandlesStore`, input `currency = input('€')`; template has an empty `<div class="controls"></div>` as its first child (V172-10 fills it) and these classes: `.readout` (with one `.part` span per readout part), `.chart` (canvas host), `.caption`, `.account`; protected `onCrosshair(param: { logical?: number | null })`, `seriesData()`, `state()`.
  - `equity-candles.model.ts`: `toChartTime(t: string, tf: EquityTimeframe): Time`, `toSeriesData(candles: readonly EquityCandle[], tf: EquityTimeframe, colors: CandleColors): CandlestickData<Time>[]`, `readoutParts(candle: EquityCandle, basis: EquityBasis, currency: string, tf: EquityTimeframe): string[]`, `emptyMessage(tf: EquityTimeframe, recordingSince: string | null): string`, `approxCaption(recordingSince: string | null): string`, plus `candleLabel`, `seamIndex`, `isIntraday`, `BASIS_LABEL`, `ACCOUNT_LABEL`, `SEAM_LABEL`, `CHANGE_PCT_TOOLTIP`, `interface CandleColors { up; down; faint }`.
  - `VLinePrimitive` with `setLine(spec: VLineSpec | null)`, `current(): VLineSpec | null`; `interface VLineSpec { time: Time; label: string; color: string; textColor: string }`.
  - `equityCandlesStoreStub(data?: EquityCandlesResponse | null)` returning signal-backed `tf`, `basis`, `data`, `loading`, `error`, a `calls` counter object `{ load: number; tf: EquityTimeframe[]; basis: EquityBasis[] }`, and `load()`, `setTimeframe()`, `setBasis()`; type `EquityCandlesStoreStub`.

Design notes the implementer needs:
- **Time axis.** 1D/1W candles use the `YYYY-MM-DD` string as a business-day time. 1H/4H use "wall-clock seconds": the New York wall time read as if it were UTC (`Date.parse(t.slice(0, 19) + 'Z') / 1000`), so the axis labels show New York hours whatever the viewer's zone. On the November fall-back day the 01:00 hour repeats on the wall clock; the second one is placed one second after the first so the series stays strictly ascending (lightweight-charts throws otherwise). The readout always prints the candle's own `t`, so this never shows.
- **Crosshair → candle** uses `param.logical` (the bar index of the single series), not `param.time`, so it is independent of how the library echoes business-day times.
- **Hollow approx candle:** per-point `color: 'transparent'`, `borderColor` = `--pos`/`--neg` by direction, `wickColor` = `--text-faint`.
- **Seam:** the first candle that is not `approx` and follows at least one `approx` candle gets a vertical line at its left edge labelled `Recording started` (`VLinePrimitive`). No approx candle → no line.
- **Caption** shows while any approx candle is inside the visible logical range (whole series before the first range event).
- **No animation:** `setData` on every refetch, `fitContent()` only when the timeframe or basis changes, never a CSS transition on the chart.

- [ ] **Step 1: Write the failing tests**

Create `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { EquityCandle } from '../../../api/models';
import {
  ACCOUNT_LABEL,
  approxCaption,
  candleLabel,
  emptyMessage,
  readoutParts,
  seamIndex,
  toChartTime,
  toSeriesData,
} from './equity-candles.model';

function candle(overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
           change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false, ...overrides };
}

const COLORS = { up: 'UP', down: 'DOWN', faint: 'FAINT' };

describe('equity candles model', () => {
  it('keeps daily and weekly times as business-day strings', () => {
    expect(toChartTime('2026-10-16', '1D')).toBe('2026-10-16');
    expect(toChartTime('2026-10-12', '1W')).toBe('2026-10-12');
  });

  it('reads intraday times as New York wall clock', () => {
    // 09:00 New York, whatever the offset, is 09:00 on the axis.
    expect(toChartTime('2026-10-16T09:00:00-04:00', '1H')).toBe(Date.UTC(2026, 9, 16, 9) / 1000);
    expect(toChartTime('2026-12-01T12:00:00-05:00', '4H')).toBe(Date.UTC(2026, 11, 1, 12) / 1000);
  });

  it('keeps the series strictly ascending across the fall-back hour', () => {
    const data = toSeriesData([
      candle({ t: '2026-11-01T01:00:00-04:00' }),
      candle({ t: '2026-11-01T01:00:00-05:00' }),
      candle({ t: '2026-11-01T02:00:00-05:00' }),
    ], '1H', COLORS);
    const times = data.map((p) => p.time as number);
    expect(times[1]).toBe(times[0] + 1);
    expect(times[2]).toBeGreaterThan(times[1]);
  });

  it('draws an approx candle hollow and a measured one with the series colours', () => {
    const [up, down, measured] = toSeriesData([
      candle({ o: 100, c: 110, approx: true }),
      candle({ t: '2026-10-19', o: 110, c: 90, approx: true }),
      candle({ t: '2026-10-20', approx: false }),
    ], '1D', COLORS);
    expect(up).toMatchObject({ color: 'transparent', borderColor: 'UP', wickColor: 'FAINT' });
    expect(down).toMatchObject({ color: 'transparent', borderColor: 'DOWN', wickColor: 'FAINT' });
    expect(measured.color).toBeUndefined();
    expect(measured).toMatchObject({ time: '2026-10-20', open: 10120.5, high: 10210, low: 10090.2, close: 10180.4 });
  });

  it('labels candles by timeframe', () => {
    expect(candleLabel('2026-10-16', '1D')).toBe('Oct 16, 2026');
    expect(candleLabel('2026-10-12', '1W')).toBe('Week of Oct 12, 2026');
    expect(candleLabel('2026-10-16T13:00:00-04:00', '4H')).toBe('Oct 16, 2026 13:00 ET');
  });

  it('builds the readout: when, O H L C, change, % vs prev close, basis', () => {
    expect(readoutParts(candle(), 'mtm', '€', '1D')).toEqual([
      'Oct 16, 2026', 'O 10,120.50', 'H 10,210.00', 'L 10,090.20', 'C 10,180.40',
      '+59.90 €', '+0.59% vs prev close', 'Open + closed',
    ]);
  });

  it('names the closed-trades basis and flags approx and skipped positions', () => {
    const parts = readoutParts(candle({ approx: true, skipped: 2, change: -5, change_pct: -0.05 }),
                               'realized', '$', '1D');
    expect(parts).toContain('Closed trades only');
    expect(parts).toContain('approx');
    expect(parts).toContain('2 positions not counted');
    expect(parts).toContain('-5.00 $');
    expect(readoutParts(candle({ skipped: 1 }), 'mtm', '€', '1D')).toContain('1 position not counted');
  });

  it('shows a dash when the percentage has no base', () => {
    expect(readoutParts(candle({ change_pct: null }), 'mtm', '€', '1D')).toContain('— vs prev close');
  });

  it('words the empty state by timeframe', () => {
    expect(emptyMessage('1H', '2026-10-20T13:35:00Z'))
      .toBe('No hourly samples yet — recording started Oct 20, 2026');
    expect(emptyMessage('4H', '2026-10-20T13:35:00Z'))
      .toBe('No hourly samples yet — recording started Oct 20, 2026');
    expect(emptyMessage('1H', null)).toBe('No equity samples yet');
    expect(emptyMessage('1D', null)).toBe('No equity samples yet');
  });

  it('dates the approx caption in New York', () => {
    // 02:00 UTC on the 21st is still the 20th in New York.
    expect(approxCaption('2026-10-21T02:00:00Z'))
      .toBe('Before Oct 20, 2026: rebuilt from daily bars — ranges are outer bounds');
    expect(approxCaption(null))
      .toBe('Before recording started: rebuilt from daily bars — ranges are outer bounds');
  });

  it('puts the seam on the first measured candle after a rebuilt one', () => {
    expect(seamIndex([candle({ approx: true }), candle({ approx: true }), candle(), candle()])).toBe(2);
    expect(seamIndex([candle(), candle()])).toBe(-1);
    expect(seamIndex([candle({ approx: true })])).toBe(-1);
    expect(seamIndex([])).toBe(-1);
  });

  it('states the account label exactly', () => {
    expect(ACCOUNT_LABEL).toBe('Paper account · before tax and costs');
  });
});
```

Create `$WT/frontend/src/app/ui/chart/primitives/vline-primitive.spec.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';

import { VLinePrimitive } from './vline-primitive';

function fakeContext() {
  return {
    save: vi.fn(), restore: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(),
    fillStyle: '', font: '', textBaseline: '',
  };
}

function attach(coordinate: number | null) {
  const primitive = new VLinePrimitive();
  const requestUpdate = vi.fn();
  const chart = { timeScale: () => ({
    timeToCoordinate: () => coordinate,
    options: () => ({ barSpacing: 10 }),
  }) };
  primitive.attached({ chart, series: {}, requestUpdate } as never);
  return { primitive, requestUpdate };
}

function draw(primitive: VLinePrimitive) {
  const context = fakeContext();
  const target = { useBitmapCoordinateSpace: (cb: (scope: unknown) => void) => cb({
    context, horizontalPixelRatio: 2, verticalPixelRatio: 2, bitmapSize: { width: 400, height: 300 },
  }) };
  primitive.paneViews()[0].renderer()!.draw(target as never);
  return context;
}

const SPEC = { time: '2026-10-20', label: 'Recording started', color: 'LINE', textColor: 'TEXT' };

describe('VLinePrimitive', () => {
  it('draws one full-height line at the left edge of the bar, with its label', () => {
    const { primitive } = attach(100);
    primitive.setLine(SPEC as never);
    const context = draw(primitive);
    // centre 100 - half of barSpacing 10 = 95 CSS px = 190 bitmap px.
    expect(context.fillRect).toHaveBeenCalledWith(190, 0, 2, 300);
    expect(context.fillText).toHaveBeenCalledWith('Recording started', 198, 8);
  });

  it('draws nothing without a line or off screen', () => {
    const { primitive } = attach(100);
    expect(draw(primitive).fillRect).not.toHaveBeenCalled();
    const offscreen = attach(null).primitive;
    offscreen.setLine(SPEC as never);
    expect(draw(offscreen).fillRect).not.toHaveBeenCalled();
  });

  it('asks the chart to repaint when the line changes', () => {
    const { primitive, requestUpdate } = attach(100);
    primitive.setLine(SPEC as never);
    expect(requestUpdate).toHaveBeenCalledTimes(1);
    expect(primitive.current()).toEqual(SPEC);
    primitive.setLine(null);
    expect(primitive.current()).toBeNull();
  });
});
```

Create `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { EquityCandle, EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { EquityCandles } from './equity-candles';

// A real lightweight-charts chart is created; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

function candle(t: string, overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t, o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
           samples: 4, skipped: 0, approx: false, ...overrides };
}

function response(candles: EquityCandle[], overrides: Partial<EquityCandlesResponse> = {}): EquityCandlesResponse {
  return { tf: '1D', basis: 'mtm', currency_symbol: '€', candles,
           recording_since: '2026-10-20T13:35:00Z', as_of: '2026-10-21T14:35:00Z', ...overrides };
}

const MIXED = [
  candle('2026-10-16', { approx: true }),
  candle('2026-10-19', { approx: true, o: 110, c: 105, change: -5, change_pct: -4.55 }),
  candle('2026-10-20', { o: 105, c: 112, change: 7, change_pct: 6.67, skipped: 2 }),
];

function render(data: EquityCandlesResponse | null, error: string | null = null) {
  const stub = equityCandlesStoreStub(data);
  stub.error.set(error);
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: EquityCandlesStore, useValue: stub }],
  });
  const fixture = TestBed.createComponent(EquityCandles);
  fixture.componentRef.setInput('currency', '€');
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement, stub };
}

function readout(el: HTMLElement): string[] {
  return [...el.querySelectorAll('.readout .part')].map((p) => p.textContent!.trim());
}

describe('sb-equity-candles', () => {
  it('reads out the latest candle when nothing is hovered', () => {
    const { el } = render(response(MIXED));
    const parts = readout(el);
    expect(parts[0]).toBe('Oct 20, 2026');
    expect(parts).toContain('C 112.00');
    expect(parts).toContain('+7.00 €');
    expect(parts).toContain('+6.67% vs prev close');
    expect(parts).toContain('Open + closed');
    expect(parts).toContain('2 positions not counted');
  });

  it('explains the percentage in a tooltip', () => {
    const { el } = render(response(MIXED));
    const pctPart = [...el.querySelectorAll('.readout .part')]
      .find((p) => p.textContent!.includes('vs prev close'))!;
    expect(pctPart.getAttribute('title'))
      .toBe("Change from the previous candle's close, not a return on capital");
  });

  it('follows the crosshair, and returns to the latest candle when it leaves', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['onCrosshair']({ logical: 1 });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 19, 2026');
    expect(readout(el)).toContain('approx');

    fixture.componentInstance['onCrosshair']({ logical: undefined });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 20, 2026');
  });

  it('draws rebuilt candles hollow, with the outer-bounds caption and the seam', () => {
    const { fixture, el } = render(response(MIXED));
    // jsdom lays the chart out at 0px, so whatever range it reports is not a
    // real viewport: clear it, as before the first range event.
    fixture.componentInstance['visible'].set(null);
    fixture.detectChanges();
    const data = fixture.componentInstance['seriesData']();
    expect(data[0].color).toBe('transparent');
    expect(data[1].color).toBe('transparent');
    expect(data[2].color).toBeUndefined();
    expect(el.querySelector('.caption')?.textContent?.trim())
      .toBe('Before Oct 20, 2026: rebuilt from daily bars — ranges are outer bounds');
    const seam = fixture.componentInstance['seam']?.current();
    expect(seam?.label).toBe('Recording started');
    expect(seam?.time).toBe('2026-10-20');
  });

  it('hides the caption once the rebuilt candles scroll out of view', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['visible'].set({ from: 2, to: 2 });
    fixture.detectChanges();
    expect(el.querySelector('.caption')).toBeNull();
  });

  it('shows no caption and no seam when every candle was recorded', () => {
    const { fixture, el } = render(response([candle('2026-10-20'), candle('2026-10-21')]));
    expect(el.querySelector('.caption')).toBeNull();
    expect(fixture.componentInstance['seam']?.current()).toBeNull();
  });

  it('shows the hourly empty state with the recording date, never an empty axis', () => {
    const { fixture, el } = render(response([], { tf: '1H' }));
    expect(fixture.componentInstance['state']()).toBe('empty');
    expect(el.querySelector('sb-async')?.textContent)
      .toContain('No hourly samples yet — recording started Oct 20, 2026');
    expect(el.querySelector('.chart')?.classList.contains('hidden')).toBe(true);
  });

  it('shows the loading skeleton before the first answer', () => {
    const { fixture, el } = render(null);
    expect(fixture.componentInstance['state']()).toBe('loading');
    expect(el.querySelector('sb-async')?.getAttribute('aria-busy')).toBe('true');
  });

  it('offers a retry on error that reloads the store', () => {
    const { el, stub } = render(null, 'Equity candles could not be loaded.');
    const retry = [...el.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Retry')!;
    retry.click();
    expect(stub.calls.load).toBe(1);
  });

  it('always states what the account is', () => {
    const { el } = render(response(MIXED));
    expect(el.querySelector('.account')?.textContent?.trim())
      .toBe('Paper account · before tax and costs');
  });

  it('uses the currency it is given, not the API symbol', () => {
    const { fixture, el } = render(response(MIXED, { currency_symbol: '$' }));
    fixture.componentRef.setInput('currency', '£');
    fixture.detectChanges();
    expect(readout(el)).toContain('+7.00 £');
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/chart/primitives/vline-primitive.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts
```

Expected: all three fail to resolve their module under test.

- [ ] **Step 3: Write the model helpers**

Create `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts`:

```ts
import type { CandlestickData, Time, UTCTimestamp } from 'lightweight-charts';

import { EquityBasis, EquityCandle, EquityTimeframe } from '../../../api/models';
import { money, num, pct } from '../../../ui/format';

/**
 * Pure helpers for `sb-equity-candles` — spec v172 § 5. Everything here is
 * testable without a canvas; the component only wires these to the chart.
 */

export const BASIS_LABEL: Record<EquityBasis, string> = {
  mtm: 'Open + closed',
  realized: 'Closed trades only',
};

/** v172 correction 7: `realized_pnl_amount` carries no slippage or
 *  commission, so the label states both exclusions. */
export const ACCOUNT_LABEL = 'Paper account · before tax and costs';
export const SEAM_LABEL = 'Recording started';
export const CHANGE_PCT_TOOLTIP = "Change from the previous candle's close, not a return on capital";

const NY = 'America/New_York';
const DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' });
const NY_DAY = new Intl.DateTimeFormat('en-US', { timeZone: NY, month: 'short', day: 'numeric', year: 'numeric' });

export interface CandleColors {
  up: string;
  down: string;
  faint: string;
}

export function isIntraday(tf: EquityTimeframe): boolean {
  return tf === '1H' || tf === '4H';
}

/** Business-day string for 1D/1W; for 1H/4H the New York wall time read as
 *  if it were UTC, so the axis shows New York hours in every viewer zone. */
export function toChartTime(t: string, tf: EquityTimeframe): Time {
  if (!isIntraday(tf)) return t.slice(0, 10) as Time;
  return Math.floor(Date.parse(`${t.slice(0, 19)}Z`) / 1000) as UTCTimestamp;
}

export function toSeriesData(
  candles: readonly EquityCandle[],
  tf: EquityTimeframe,
  colors: CandleColors,
): CandlestickData<Time>[] {
  const out: CandlestickData<Time>[] = [];
  let last = Number.NEGATIVE_INFINITY;
  for (const candle of candles) {
    let time = toChartTime(candle.t, tf);
    if (typeof time === 'number') {
      // The fall-back hour repeats on the wall clock (01:00 EDT, then 01:00
      // EST); the series must be strictly ascending, so a repeat sits 1s later.
      if (time <= last) time = (last + 1) as UTCTimestamp;
      last = time;
    }
    const point: CandlestickData<Time> = { time, open: candle.o, high: candle.h, low: candle.l, close: candle.c };
    if (candle.approx) {
      // Hollow: rebuilt from daily bars, its range is an outer bound.
      point.color = 'transparent';
      point.borderColor = candle.c >= candle.o ? colors.up : colors.down;
      point.wickColor = colors.faint;
    }
    out.push(point);
  }
  return out;
}

function dayLabel(ymd: string): string {
  return DAY.format(new Date(`${ymd}T00:00:00Z`));
}

/** The New York calendar date of an instant. */
function recordingDate(iso: string): string {
  return NY_DAY.format(new Date(iso));
}

export function candleLabel(t: string, tf: EquityTimeframe): string {
  if (tf === '1W') return `Week of ${dayLabel(t.slice(0, 10))}`;
  if (tf === '1D') return dayLabel(t.slice(0, 10));
  return `${dayLabel(t.slice(0, 10))} ${t.slice(11, 16)} ET`;
}

function skippedNote(skipped: number): string {
  return `${skipped} position${skipped === 1 ? '' : 's'} not counted`;
}

export function readoutParts(
  candle: EquityCandle,
  basis: EquityBasis,
  currency: string,
  tf: EquityTimeframe,
): string[] {
  const parts = [
    candleLabel(candle.t, tf),
    `O ${num(candle.o)}`,
    `H ${num(candle.h)}`,
    `L ${num(candle.l)}`,
    `C ${num(candle.c)}`,
    money(candle.change, currency),
    `${pct(candle.change_pct)} vs prev close`,
    BASIS_LABEL[basis],
  ];
  if (candle.approx) parts.push('approx');
  if (candle.skipped > 0) parts.push(skippedNote(candle.skipped));
  return parts;
}

export function emptyMessage(tf: EquityTimeframe, recordingSince: string | null): string {
  if (isIntraday(tf) && recordingSince) {
    return `No hourly samples yet — recording started ${recordingDate(recordingSince)}`;
  }
  return 'No equity samples yet';
}

export function approxCaption(recordingSince: string | null): string {
  const when = recordingSince ? recordingDate(recordingSince) : 'recording started';
  return `Before ${when}: rebuilt from daily bars — ranges are outer bounds`;
}

/** Index of the first recorded candle that follows a rebuilt one, or -1. */
export function seamIndex(candles: readonly EquityCandle[]): number {
  let sawApprox = false;
  for (let i = 0; i < candles.length; i++) {
    if (candles[i].approx) sawApprox = true;
    else if (sawApprox) return i;
  }
  return -1;
}
```

Note on the readout's minus sign: `money()` prints a negative through `toLocaleString`, i.e. a hyphen-minus (`-5.00 $`), which is what the model test expects; `pct()` prints `-0.05%`. Do not switch to `signed()` here: the rest of the Dashboard's money figures use `money()`.

- [ ] **Step 4: Write the seam primitive**

Create `$WT/frontend/src/app/ui/chart/primitives/vline-primitive.ts`:

```ts
import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

import { token } from '../chart-theme';

/**
 * One labelled vertical line at a bar's left edge — v172's "Recording
 * started" seam between candles rebuilt from daily bars and candles built
 * from recorded samples.
 *
 * At most one line at a time: `setLine(null)` removes it. The line sits at
 * the bar's LEFT edge (centre minus half the bar spacing) because the seam is
 * where recording began, not the middle of the first recorded candle.
 */
export interface VLineSpec {
  time: Time;
  label: string;
  color: string;
  textColor: string;
}

interface BitmapScope {
  context: CanvasRenderingContext2D;
  horizontalPixelRatio: number;
  verticalPixelRatio: number;
  bitmapSize: { width: number; height: number };
}

interface DrawTarget {
  useBitmapCoordinateSpace: (cb: (scope: BitmapScope) => void) => void;
}

const LABEL_PX = 11;
const LABEL_INSET_PX = 4;

class VLineRenderer implements IPrimitivePaneRenderer {
  constructor(
    private readonly line: () => VLineSpec | null,
    private readonly chart: () => IChartApi | null,
  ) {}

  draw(target: DrawTarget): void {
    const spec = this.line();
    const chart = this.chart();
    if (!spec || !chart) return;
    const scale = chart.timeScale();
    const centre = scale.timeToCoordinate(spec.time);
    // Scrolled off screen.
    if (centre === null) return;
    const x = centre - scale.options().barSpacing / 2;

    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio, bitmapSize }) => {
      const px = Math.round(x * horizontalPixelRatio);
      context.save();
      context.fillStyle = spec.color;
      context.fillRect(px, 0, Math.max(1, Math.floor(horizontalPixelRatio)), bitmapSize.height);
      context.fillStyle = spec.textColor;
      const family = token('--font-sans') || 'sans-serif';
      context.font = `${Math.round(LABEL_PX * verticalPixelRatio)}px ${family}`;
      context.textBaseline = 'top';
      context.fillText(
        spec.label,
        px + Math.round(LABEL_INSET_PX * horizontalPixelRatio),
        Math.round(LABEL_INSET_PX * verticalPixelRatio),
      );
      context.restore();
    });
  }
}

class VLinePaneView implements IPrimitivePaneView {
  constructor(private readonly renderer_: VLineRenderer) {}

  zOrder(): 'top' {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer {
    return this.renderer_;
  }
}

export class VLinePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private spec: VLineSpec | null = null;
  private requestUpdate: (() => void) | null = null;
  private readonly views: VLinePaneView[];

  constructor() {
    this.views = [new VLinePaneView(new VLineRenderer(() => this.spec, () => this.chart))];
  }

  current(): VLineSpec | null {
    return this.spec;
  }

  setLine(spec: VLineSpec | null): void {
    this.spec = spec;
    this.requestUpdate?.();
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.chart = null;
    this.requestUpdate = null;
  }

  updateAllViews(): void {}

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }
}
```

- [ ] **Step 5: Write the store stub**

Create `$WT/frontend/src/app/testing/equity-candles-store.stub.ts` (plain Angular signals, no `vitest` import: this folder is compiled by the app build too):

```ts
import { signal } from '@angular/core';

import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../api/models';

/**
 * A stand-in for `EquityCandlesStore` in component specs (v172): the same
 * signal and method names, no HTTP, no EventStream, no preferences. `calls`
 * records what the component asked for.
 */
export function equityCandlesStoreStub(data: EquityCandlesResponse | null = null) {
  const tf = signal<EquityTimeframe>(data?.tf ?? '1D');
  const basis = signal<EquityBasis>(data?.basis ?? 'mtm');
  const calls = { load: 0, tf: [] as EquityTimeframe[], basis: [] as EquityBasis[] };
  return {
    tf: tf.asReadonly(),
    basis: basis.asReadonly(),
    data: signal<EquityCandlesResponse | null>(data),
    loading: signal(false),
    error: signal<string | null>(null),
    calls,
    load: (): void => {
      calls.load += 1;
    },
    setTimeframe: (value: EquityTimeframe): void => {
      calls.tf.push(value);
      tf.set(value);
    },
    setBasis: (value: EquityBasis): void => {
      calls.basis.push(value);
      basis.set(value);
    },
  };
}

export type EquityCandlesStoreStub = ReturnType<typeof equityCandlesStoreStub>;
```

- [ ] **Step 6: Write the component**

Create `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`:

```ts
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import {
  CandlestickData,
  CandlestickSeries,
  IChartApi,
  ISeriesApi,
  Time,
  createChart,
} from 'lightweight-charts';

import { EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { Async } from '../../../ui/async';
import { chartOptions, chartPalette, token } from '../../../ui/chart/chart-theme';
import { VLinePrimitive } from '../../../ui/chart/primitives/vline-primitive';
import {
  ACCOUNT_LABEL,
  CHANGE_PCT_TOOLTIP,
  SEAM_LABEL,
  approxCaption,
  emptyMessage,
  isIntraday,
  readoutParts,
  seamIndex,
  toSeriesData,
} from './equity-candles.model';

type ChartState = 'loading' | 'error' | 'empty' | 'chart';

/**
 * The account as candles — spec v172 § 5. Replaces the 30-point sparkline
 * inside `sb-portfolio-value`.
 *
 * The chart is created once (untracked, like `TradeChart`) and fed by
 * `setData` on every refetch: candles never animate or flash, and the
 * viewport is reset (`fitContent`) only when the timeframe or basis changes.
 * Backfilled candles are hollow, a caption states their range is an outer
 * bound while one is in view, and a vertical line marks where recording
 * started. Currency comes from the `currency` input (`connection.currency()`
 * upstream), never the API's `currency_symbol`.
 */
@Component({
  selector: 'sb-equity-candles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async],
  template: `
    <div class="controls"></div>
    @if (readout().length) {
      <p class="readout">
        @for (part of readout(); track $index) {
          <span class="part" [attr.title]="part.endsWith('vs prev close') ? changeTooltip : null">{{ part }}</span>
        }
      </p>
    }
    @if (state() !== 'chart') {
      <sb-async
        class="states"
        [loading]="state() === 'loading'"
        [error]="store.error()"
        [empty]="state() === 'empty'"
        emptyReason="no-data-yet"
        [emptyTitle]="emptyTitle()"
        [skeletonRows]="3"
        [skeletonCols]="1"
        (retry)="store.load()"
      />
    }
    <div #host class="chart" [class.hidden]="state() !== 'chart'"></div>
    @if (showCaption()) {
      <p class="caption">{{ caption() }}</p>
    }
    <p class="account">{{ accountLabel }}</p>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .readout {
      margin: 0 0 var(--space-6);
      font-size: var(--text-table);
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .part + .part::before { content: '·'; margin: 0 var(--space-4); color: var(--text-faint); }
    .part[title] { text-decoration: underline dotted; cursor: help; }
    .chart { width: 100%; height: 200px; }
    .chart.hidden { display: none; }
    .caption, .account { margin: var(--space-6) 0 0; font-size: var(--text-chip); }
    .caption { color: var(--text-muted); }
    .account { color: var(--text-faint); }
    @media (max-width: 639px) {
      .chart { height: 160px; }
    }
  `,
})
export class EquityCandles {
  readonly currency = input('€');

  protected readonly store = inject(EquityCandlesStore);
  protected readonly accountLabel = ACCOUNT_LABEL;
  protected readonly changeTooltip = CHANGE_PCT_TOOLTIP;

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart: IChartApi | null = null;
  private series: ISeriesApi<'Candlestick'> | null = null;
  protected seam: VLinePrimitive | null = null;
  private renderedView = '';

  /** Read once: chart colours come from the tokens at creation, as in
   *  `TradeChart`. `--text-faint` is the hollow candle's wick. */
  private readonly colors = (() => {
    const palette = chartPalette();
    return { up: palette.up, down: palette.down, faint: token('--text-faint'), muted: palette.textMuted };
  })();

  private readonly hoverIndex = signal<number | null>(null);
  protected readonly visible = signal<{ from: number; to: number } | null>(null);

  protected readonly candles = computed(() => this.store.data()?.candles ?? []);

  protected readonly state = computed<ChartState>(() => {
    if (this.store.error()) return 'error';
    const data = this.store.data();
    if (!data) return 'loading';
    return data.candles.length ? 'chart' : 'empty';
  });

  protected readonly seriesData = computed<CandlestickData<Time>[]>(() => {
    const data = this.store.data();
    return data ? toSeriesData(data.candles, data.tf, this.colors) : [];
  });

  /** The hovered candle, or the latest one with no crosshair. */
  private readonly shown = computed(() => {
    const candles = this.candles();
    const index = this.hoverIndex();
    return (index !== null ? candles[index] : undefined) ?? candles.at(-1) ?? null;
  });

  protected readonly readout = computed<string[]>(() => {
    const data = this.store.data();
    const candle = this.shown();
    return data && candle ? readoutParts(candle, data.basis, this.currency(), data.tf) : [];
  });

  protected readonly emptyTitle = computed(() =>
    emptyMessage(this.store.data()?.tf ?? this.store.tf(), this.store.data()?.recording_since ?? null));

  protected readonly caption = computed(() => approxCaption(this.store.data()?.recording_since ?? null));

  /** True while an approx candle is inside the visible range (the whole
   *  series before the chart reports its first range). */
  protected readonly showCaption = computed(() => {
    const candles = this.candles();
    const range = this.visible();
    const from = range ? Math.max(0, Math.floor(range.from)) : 0;
    const to = range ? Math.min(candles.length - 1, Math.ceil(range.to)) : candles.length - 1;
    return candles.slice(from, to + 1).some((candle) => candle.approx);
  });

  constructor() {
    const destroyRef = inject(DestroyRef);

    effect(() => {
      const element = this.host().nativeElement;
      // untracked: creating the chart must not subscribe to the data.
      untracked(() => this.create(element));
    });

    effect(() => {
      const data = this.store.data();
      const points = this.seriesData();
      untracked(() => this.render(data, points));
    });

    destroyRef.onDestroy(() => {
      this.chart?.remove();
      this.chart = null;
      this.series = null;
      this.seam = null;
    });
  }

  /** Crosshair → candle by bar index; `undefined`/`null` (pointer left the
   *  pane) falls back to the latest candle. */
  protected onCrosshair(param: { logical?: number | null }): void {
    const logical = param.logical;
    this.hoverIndex.set(logical === undefined || logical === null ? null : Math.round(logical));
  }

  private create(element: HTMLElement): void {
    if (this.chart) return;
    const palette = chartPalette();
    const chart = createChart(element, chartOptions(palette));
    const series = chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      borderUpColor: palette.up,
      borderDownColor: palette.down,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    this.seam = new VLinePrimitive();
    series.attachPrimitive(this.seam);
    chart.subscribeCrosshairMove((param) => this.onCrosshair(param));
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) =>
      this.visible.set(range ? { from: range.from, to: range.to } : null));
    this.chart = chart;
    this.series = series;
  }

  private render(data: EquityCandlesResponse | null, points: CandlestickData<Time>[]): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    this.hoverIndex.set(null);
    series.setData(points);
    chart.applyOptions({ timeScale: { timeVisible: data ? isIntraday(data.tf) : false, secondsVisible: false } });
    const seam = data ? seamIndex(data.candles) : -1;
    this.seam?.setLine(seam >= 0
      ? { time: points[seam].time, label: SEAM_LABEL, color: this.colors.faint, textColor: this.colors.muted }
      : null);
    const view = data ? `${data.tf}/${data.basis}` : '';
    if (view && view !== this.renderedView) {
      chart.timeScale().fitContent();
      this.renderedView = view;
    }
  }
}
```

- [ ] **Step 7: Run the tests to see them pass**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/chart/primitives/vline-primitive.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts
npm --prefix $WT/frontend exec -- ng build --configuration development
```

Expected: every spec passes, 0 failed; the build succeeds (it compiles `testing/equity-candles-store.stub.ts` too, which is why the stub imports no test library). If `'Oct 16, 2026'` style assertions fail with a different format, the Node ICU is not full; print `new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', year:'numeric'}).format(new Date())` and report it rather than loosening the assertion. If the seam test sees `null`, check that `render()` ran: the data effect must read `this.store.data()` and `this.seriesData()` outside `untracked`.

- [ ] **Step 8: Commit on the branch**

```bash
git -C $WT add frontend/src/app/workspaces/dashboard/panels/equity-candles.model.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.model.spec.ts frontend/src/app/ui/chart/primitives/vline-primitive.ts frontend/src/app/ui/chart/primitives/vline-primitive.spec.ts frontend/src/app/testing/equity-candles-store.stub.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts
git -C $WT commit -m "feat(ui): sb-equity-candles -- hollow rebuilt candles, recording seam, OHLC readout and states (v172)"
git -C $R status --short
```

End the commit message with the attribution line from the session's system reminder. Expected: one commit on the branch; `$R`'s status shows no change from this task.

### Task V172-10: Controls, prefs, replace the sparkline in `sb-portfolio-value`, three-width check

**Model:** sonnet — template/CSS wiring and spec rewrite in the dashboard panels

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts` (imports, the `<div class="controls"></div>` line, the whole `styles:` literal, two option arrays and two handlers)
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` (append four tests)
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts` (whole file below)
- Modify: `frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts` (whole file below)
- Modify: `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts` (imports + `beforeEach` providers: it renders `sb-portfolio-value`)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (imports + one provider in `seed()`: it renders the whole Dashboard)

**Interfaces:**
- Consumes (V172-8): `EquityCandlesStore.tf()`, `.basis()`, `.setTimeframe(tf)`, `.setBasis(basis)`; `EQUITY_TIMEFRAMES`, `EQUITY_BASES` (`ui/equity-chart-prefs.ts`). (V172-9): `EquityCandles` (`sb-equity-candles`, input `currency`), `BASIS_LABEL` (`equity-candles.model.ts`), `equityCandlesStoreStub` (`testing/equity-candles-store.stub.ts`). Existing: `Segmented`, `SegmentOption` (`ui/segmented.ts`: inputs `options`, `label`, model `value`; buttons carry `aria-pressed`).
- Produces: nothing consumed later. `sb-portfolio-value` keeps its four inputs (`balance`, `changePct`, `points`, `currency`) so `trading-performance.ts` and `dashboard.ts` are not edited; `points` is no longer drawn (the 30-day series stays in the API this release, spec § 4).

Layout this task implements (spec § 5 three-device table; `--control-h` already becomes 44px under `(pointer: coarse), (max-width: 639px)` in `styles/tokens.css`, which is what makes `sb-segmented`'s buttons 44px tall on phone without a local override):

| Width | Order | Controls | Chart |
|---|---|---|---|
| < 640 | controls, chart, states, readout, caption, account | timeframe and basis on two lines (each `flex-basis: 100%`) | 160px |
| 640–1023 | controls, readout, chart, … | one wrapping row | 200px |
| ≥ 1024 | controls with the readout inline at their right, then chart, … | one row | 200px |

- [ ] **Step 1: Write the failing tests**

Append inside the `describe('sb-equity-candles', ...)` block of `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` (before its closing `});`):

```ts
  function buttons(el: HTMLElement, group: string): HTMLButtonElement[] {
    return [...el.querySelectorAll<HTMLButtonElement>(`[aria-label="${group}"] button`)];
  }

  it('offers the four timeframes with the stored one pressed', () => {
    const { el } = render(response(MIXED));
    const chips = buttons(el, 'Candle timeframe');
    expect(chips.map((b) => b.textContent!.trim())).toEqual(['1H', '4H', '1D', '1W']);
    expect(chips.find((b) => b.getAttribute('aria-pressed') === 'true')?.textContent?.trim()).toBe('1D');
  });

  it('switches timeframe through the store', () => {
    const { fixture, el, stub } = render(response(MIXED));
    buttons(el, 'Candle timeframe').find((b) => b.textContent!.trim() === '1W')!.click();
    fixture.detectChanges();
    expect(stub.calls.tf).toEqual(['1W']);
    expect(buttons(el, 'Candle timeframe').find((b) => b.getAttribute('aria-pressed') === 'true')
      ?.textContent?.trim()).toBe('1W');
  });

  it('offers the two bases by name and switches through the store', () => {
    const { fixture, el, stub } = render(response(MIXED));
    const toggle = buttons(el, 'Equity basis');
    expect(toggle.map((b) => b.textContent!.trim())).toEqual(['Open + closed', 'Closed trades only']);
    toggle[1].click();
    fixture.detectChanges();
    expect(stub.calls.basis).toEqual(['realized']);
  });

  it('keeps the controls when there is nothing to draw', () => {
    const { el } = render(response([], { tf: '1H' }));
    expect(buttons(el, 'Candle timeframe').length).toBe(4);
    expect(buttons(el, 'Equity basis').length).toBe(2);
  });
```

Replace `$WT/frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts` entirely with (the old "renders no equity-range controls" test asserted there is no `1W` button; spec correction 10 replaces it with the test that the four timeframes are offered):

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { PortfolioValue } from './portfolio-value';

// sb-equity-candles creates a real lightweight-charts chart.
installMatchMediaPolyfill();

const CANDLES: EquityCandlesResponse = {
  tf: '1D', basis: 'mtm', currency_symbol: '€', recording_since: '2026-10-20T13:35:00Z',
  as_of: '2026-10-21T14:35:00Z',
  candles: [{ t: '2026-10-20', o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
              samples: 4, skipped: 0, approx: false }],
};

describe('portfolio value panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub(CANDLES) },
      ],
    });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(PortfolioValue);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the balance as the hero figure with its currency', () => {
    const el = render({ balance: 997480.01, changePct: 0.36, currency: '€' });
    expect(el.querySelector('.figure')?.textContent).toContain('997,480.01');
    expect(el.querySelector('.figure')?.textContent).toContain('€');
  });

  it('tones the day change by sign', () => {
    expect(render({ balance: 1, changePct: 0.36, currency: '€' })
      .querySelector('.change')?.classList.contains('pos')).toBe(true);
    expect(render({ balance: 1, changePct: -0.36, currency: '€' })
      .querySelector('.change')?.classList.contains('neg')).toBe(true);
  });

  it('renders no value rather than a zero when the balance is missing', () => {
    const el = render({ balance: null, changePct: null, currency: '€' });
    expect(el.querySelector('.figure')?.textContent).not.toContain('0.00');
    expect(el.querySelector('.change')).toBeNull();
  });

  it('draws the equity candles where the sparkline was', () => {
    const el = render({ balance: 1, changePct: 0, points: [1, 2, 3], currency: '€' });
    expect(el.querySelector('sb-equity-candles')).not.toBeNull();
    expect(el.querySelector('sb-sparkline')).toBeNull();
  });

  it('offers the four candle timeframes', () => {
    const el = render({ balance: 1, changePct: 0, currency: '€' });
    const labels = [...el.querySelectorAll('button')].map((b) => b.textContent!.trim());
    expect(labels).toEqual(expect.arrayContaining(['1H', '4H', '1D', '1W']));
    expect(labels).not.toContain('1M');
    expect(labels).not.toContain('ALL');
  });

  it('passes its currency to the candles', () => {
    const el = render({ balance: 1, changePct: 0, currency: '£' });
    expect(el.querySelector('sb-equity-candles .readout')?.textContent).toContain('£');
  });
});
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
```

Expected: the four new `sb-equity-candles` tests fail (no `[aria-label="Candle timeframe"]` group); `portfolio-value.spec.ts` fails on `sb-equity-candles` being absent and on the missing `1H`/`4H`/`1D`/`1W` buttons.

- [ ] **Step 3: Add the controls to `sb-equity-candles`**

In `$WT/frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`:

1. Change the models import line and add three imports below the existing ones:

```ts
import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../../../api/models';
```

```ts
import { EQUITY_BASES, EQUITY_TIMEFRAMES } from '../../../ui/equity-chart-prefs';
import { SegmentOption, Segmented } from '../../../ui/segmented';
```

and add `BASIS_LABEL,` to the `./equity-candles.model` import list.

2. Change `imports: [Async],` to `imports: [Async, Segmented],`.

3. Replace the template line `<div class="controls"></div>` with:

```html
    <div class="controls">
      <sb-segmented
        class="timeframe"
        label="Candle timeframe"
        [options]="timeframeOptions"
        [value]="store.tf()"
        (valueChange)="onTimeframe($event)"
      />
      <sb-segmented
        class="basis"
        label="Equity basis"
        [options]="basisOptions"
        [value]="store.basis()"
        (valueChange)="onBasis($event)"
      />
    </div>
```

4. Replace the whole `styles: \`...\`,` literal with:

```ts
  styles: `
    /* Grid areas carry the three-device order (spec v172 § 5): readout above
       the chart on tablet, inline right of the controls on desktop, under the
       chart on phone. minmax(0, 1fr) keeps a long readout from widening the
       panel: it wraps instead, so the page never scrolls sideways. */
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas: "controls" "readout" "chart" "states" "caption" "account";
      row-gap: var(--space-6);
      min-width: 0;
    }
    .controls {
      grid-area: controls;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-6) var(--space-10);
      min-width: 0;
    }
    .readout {
      grid-area: readout;
      margin: 0;
      min-width: 0;
      font-size: var(--text-table);
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
    }
    .part + .part::before { content: '·'; margin: 0 var(--space-4); color: var(--text-faint); }
    .part[title] { text-decoration: underline dotted; cursor: help; }
    .states { grid-area: states; }
    .chart { grid-area: chart; width: 100%; min-width: 0; height: 200px; }
    .chart.hidden { display: none; }
    .caption, .account { margin: 0; font-size: var(--text-chip); }
    .caption { grid-area: caption; color: var(--text-muted); }
    .account { grid-area: account; color: var(--text-faint); }

    /* Phone: the two controls on their own lines (44px targets come from
       --control-h in tokens.css), readout and caption under the chart. */
    @media (max-width: 639px) {
      :host { grid-template-areas: "controls" "chart" "states" "readout" "caption" "account"; }
      .controls sb-segmented { flex: 1 1 100%; }
      .chart { height: 160px; }
    }

    /* Desktop: the readout sits inline at the right of the controls. */
    @media (min-width: 1024px) {
      :host {
        grid-template-columns: auto minmax(0, 1fr);
        grid-template-areas:
          "controls readout"
          "chart chart"
          "states states"
          "caption caption"
          "account account";
        column-gap: var(--space-10);
      }
      .readout { align-self: center; justify-self: end; text-align: right; }
    }
  `,
```

5. In the class body, directly after `protected readonly changeTooltip = CHANGE_PCT_TOOLTIP;`, add:

```ts
  protected readonly timeframeOptions: SegmentOption[] =
    EQUITY_TIMEFRAMES.map((tf) => ({ value: tf, label: tf }));
  protected readonly basisOptions: SegmentOption[] =
    EQUITY_BASES.map((basis) => ({ value: basis, label: BASIS_LABEL[basis] }));

  /** `sb-segmented` speaks strings; only a known value reaches the store,
   *  which writes it to the server-backed preferences. */
  protected onTimeframe(value: string): void {
    const tf = EQUITY_TIMEFRAMES.find((option) => option === value);
    if (tf) this.store.setTimeframe(tf as EquityTimeframe);
  }

  protected onBasis(value: string): void {
    const basis = EQUITY_BASES.find((option) => option === value);
    if (basis) this.store.setBasis(basis as EquityBasis);
  }
```

- [ ] **Step 4: Replace the sparkline in `sb-portfolio-value`**

Replace `$WT/frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts` entirely with:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { amount, pct } from '../../../ui/format';
import { EquityCandles } from './equity-candles';

/**
 * The account, in one figure and one chart — v85 D8, v172.
 *
 * The figure and the day change stay as they were; v172 replaces the
 * 30-point sparkline under them with `sb-equity-candles` (1H · 4H · 1D · 1W,
 * mark-to-market or closed trades only), which fetches its own candles.
 *
 * No panel of its own: it renders as the first section inside
 * `sb-trading-performance`'s single panel (v85 dashboard revision) rather
 * than as a sibling card, so the host binds `display: block` and leaves
 * borders/heading to whichever panel embeds it.
 */
@Component({
  selector: 'sb-portfolio-value',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [EquityCandles],
  template: `
    @if (balance() !== null) {
      <p class="figure">{{ money() }}</p>
    } @else {
      <p class="figure muted">—</p>
    }

    @if (changePct() !== null) {
      <p class="change" [class.pos]="changePct()! > 0" [class.neg]="changePct()! < 0">
        {{ fmtPct(changePct()) }} today
      </p>
    }

    <sb-equity-candles [currency]="currency()" />
  `,
  styles: `
    :host { display: block; }
    .figure {
      margin: 0;
      font-size: var(--text-title);
      font-weight: 600;
      color: var(--text);
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
      /* v95 A5: the figure is one number -- wrapped, it reads as several. */
      white-space: nowrap;
    }
    .figure.muted { color: var(--text-faint); }
    .change {
      margin: var(--space-4) 0 var(--space-10);
      font-size: var(--text-body);
      font-variant-numeric: tabular-nums;
    }
    .change.pos { color: var(--pos); }
    .change.neg { color: var(--neg); }
  `,
})
export class PortfolioValue {
  readonly balance = input<number | null>(null);
  readonly changePct = input<number | null>(null);
  /** The API's 30-day `equity_30d` series. Still bound by
   *  `sb-trading-performance` and still served (spec v172 § 4 keeps it this
   *  release); no longer drawn here. Retiring it is a separate change. */
  readonly points = input<readonly number[]>([]);
  readonly currency = input('€');

  protected readonly money = computed(() => amount(this.balance(), this.currency()));
  protected fmtPct = pct;
}
```

- [ ] **Step 5: Give the two parent specs the store stub**

`sb-trading-performance` and the Dashboard now construct `sb-equity-candles`, which injects `EquityCandlesStore` and creates a chart.

In `$WT/frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts`, add below the existing imports:

```ts
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';

installMatchMediaPolyfill();
```

and change its `beforeEach` line `TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });` to:

```ts
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
      ],
    });
```

In `$WT/frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, add below the existing imports:

```ts
import { EquityCandlesStore } from '../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';

installMatchMediaPolyfill();
```

and in `seed()`'s provider list, directly after `{ provide: PreferencesStore, useValue: preferencesStub },`, add:

```ts
      { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
```

- [ ] **Step 6: Run the tests to see them pass**

```bash
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/portfolio-value.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/panels/trading-performance.spec.ts
npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/dashboard/dashboard.spec.ts
npm --prefix $WT/frontend exec -- ng build --configuration development
```

Expected: every spec passes, 0 failed; the build succeeds. A `trading-performance.spec.ts` test that reads the component's source off disk (it imports `node:fs`) is unaffected: `trading-performance.ts` is not edited.

- [ ] **Step 7: Check the three widths in a real browser (Playwright)**

The candles endpoint is stubbed in the browser with a fixture (20 rebuilt candles, then recorded ones), so the check does not depend on the local database having samples; everything else is the local admin. Start both servers in the background (Bash `run_in_background: true`, one call each):

```bash
python $WT/admin_ui.py
```

```bash
npm --prefix $WT/frontend exec -- ng serve --port 4123
```

Wait until `http://localhost:4123/app/` answers (`curl -s -o /dev/null -w "%{http_code}" http://localhost:4123/app/` prints `200`). If the admin cannot reach a database and exits, stop here, say so in the task report, and leave the check to V172-13 Step 5 (production); do not skip it silently.

Write the session-scratchpad file `<scratchpad>/v172-widths.cjs` (never inside the repo):

```js
// v172 three-width check for sb-equity-candles. Usage: node v172-widths.cjs <WT> <outDir>
const { createRequire } = require('node:module');
const { mkdirSync } = require('node:fs');
const [wt, out] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('playwright');
mkdirSync(out, { recursive: true });

function fixture() {
  const candles = [];
  let close = 10000;
  for (let i = 0, day = Date.UTC(2026, 8, 1); candles.length < 30; i++, day += 86400000) {
    const date = new Date(day);
    if (date.getUTCDay() === 0 || date.getUTCDay() === 6) continue;
    const open = close;
    close = Math.round((open + Math.sin(i) * 80) * 100) / 100;
    const change = Math.round((close - open) * 100) / 100;
    candles.push({ t: date.toISOString().slice(0, 10), o: open, h: Math.max(open, close) + 40,
                   l: Math.min(open, close) - 40, c: close, change,
                   change_pct: Math.round((change / open) * 10000) / 100, samples: 4,
                   skipped: candles.length === 25 ? 1 : 0, approx: candles.length < 20 });
  }
  return { currency_symbol: '€', candles, recording_since: '2026-09-29T13:35:00Z',
           as_of: new Date().toISOString() };
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.route('**/api/v1/equity/candles**', (route) => {
    const url = new URL(route.request().url());
    route.fulfill({ json: { ...fixture(), tf: url.searchParams.get('tf') ?? '1D',
                            basis: url.searchParams.get('basis') ?? 'mtm' } });
  });
  await page.goto('http://localhost:4123/app/');
  // LOCAL dev admin only (default admin/admin unless the shell exports
  // ADMIN_USERNAME/ADMIN_PASSWORD). Never point this at production. If the
  // fill does not match the form, sign in by hand in the window: the wait
  // below gives two minutes.
  const password = page.locator('input[type=password]');
  if (await password.count()) {
    await page.locator('input:not([type=password])').first().fill(process.env.ADMIN_USERNAME ?? 'admin');
    await password.fill(process.env.ADMIN_PASSWORD ?? 'admin');
    await password.press('Enter');
  }
  await page.waitForSelector('sb-equity-candles .chart canvas', { timeout: 120000 });
  for (const width of [1280, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(600);
    const m = await page.evaluate(() => {
      const host = document.querySelector('sb-equity-candles');
      const box = (sel) => host.querySelector(sel)?.getBoundingClientRect() ?? null;
      const chart = box('.chart');
      const controls = box('.controls');
      const readout = box('.readout');
      const heights = [...host.querySelectorAll('.controls button')].map((b) => b.getBoundingClientRect().height);
      return {
        pageOverflowPx: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        chartHeight: Math.round(chart.height),
        smallestControlPx: Math.round(Math.min(...heights)),
        readoutInlineWithControls: readout ? readout.top < controls.bottom && readout.left > controls.left : null,
        readoutAboveChart: readout ? readout.bottom <= chart.top + 1 : null,
        readoutBelowChart: readout ? readout.top >= chart.bottom - 1 : null,
        caption: host.querySelector('.caption')?.textContent?.trim() ?? null,
        account: host.querySelector('.account')?.textContent?.trim() ?? null,
      };
    });
    console.log(width, JSON.stringify(m));
    await page.locator('sb-equity-candles').screenshot({ path: `${out}/equity-${width}.png` });
    await page.screenshot({ path: `${out}/page-${width}.png`, fullPage: true });
  }
  await browser.close();
})();
```

Run it (install Chromium once per machine first if Playwright asks: `npm --prefix $WT/frontend exec -- playwright install chromium`):

```bash
node "<scratchpad>/v172-widths.cjs" "$WT" "<scratchpad>/v172-widths"
```

Expected output, one line per width:
- `1280`: `pageOverflowPx` 0, `chartHeight` 200, `readoutInlineWithControls` true.
- `768`: `pageOverflowPx` 0, `chartHeight` 200, `readoutAboveChart` true.
- `390`: `pageOverflowPx` 0, `chartHeight` 160, `smallestControlPx` ≥ 44, `readoutBelowChart` true.
- Every width: `caption` = `Before Sep 29, 2026: rebuilt from daily bars — ranges are outer bounds`, `account` = `Paper account · before tax and costs`.

Then open `equity-1280.png`, `equity-768.png` and `equity-390.png` with the Read tool and confirm by eye: the first 20 candles are hollow (outline only, faint wick), the later ones filled, a vertical "Recording started" line sits at the seam, the timeframe chips and the basis toggle are on two lines at 390 and on one row at 768/1280. Any failed expectation is fixed in `equity-candles.ts`'s styles and the script re-run; stop both background servers afterwards. Record the six measurement lines in the task report.

- [ ] **Step 8: Complexity and commit on the branch**

No Python changed in this task. Commit:

```bash
git -C $WT add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.ts frontend/src/app/workspaces/dashboard/panels/portfolio-value.spec.ts frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts
git -C $WT commit -m "feat(ui): equity candles replace the dashboard sparkline -- timeframe chips, basis toggle, three-device layout (v172)"
git -C $R status --short
```

End the commit message with the attribution line from the session's system reminder. Expected: one commit on the branch; `$R`'s status shows no change from this task.

