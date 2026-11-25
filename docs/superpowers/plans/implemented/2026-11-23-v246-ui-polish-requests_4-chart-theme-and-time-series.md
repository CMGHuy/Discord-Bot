# v246 — UI polish, Plan A of five: requests — Part 4: chart theme, `sb-time-series`, linked scrolling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-13" -A 400 <this file>`).

**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) §A3 ("`ui/chart/chart-theme.ts`", "`sb-time-series`", "Linked scrolling") and the A rows of "Error, empty and edge states" and "Testing".
**Index:** [2026-11-23-v246-ui-polish-requests_0-index.md](2026-11-23-v246-ui-polish-requests_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` decisions live there; every task below implicitly includes them.

Tasks: V246-12 (theme exports on the existing `chart-theme.ts`), V246-13 (`sb-time-series`: kinds, formats, data edge cases, height, Gallery exhibit), V246-13b (its lifecycle: own `ResizeObserver`, theme repaint, release on destroy), V246-14 (`TimeScaleSync` and the `sync` input). V246-13b is a split of V246-13 (the task passed 20 KB); the controller adds its ledger row directly below V246-13.

Order: V246-12 → V246-13 → V246-13b → V246-14. V246-12 has no dependency inside Plan A and may run beside V246-5 (index § Parallelisation). Part 5 (V246-15..V246-17) consumes everything this part produces. All frontend commands run from the worktree root with `cd frontend &&`; `--include` paths are relative to `frontend/`.

Facts these tasks rely on (verified on main 2026-11-24, not restated in code):

- `ui/chart/chart-theme.ts` exists (Handoff 5): `chartPalette()`, `chartOptions(palette)`, `TICK_FALLBACK_PX`, and the re-exported `token()` / `tokenPx()` from `chart-frame.ts`. `chartOptions()` sets `timeScale.timeVisible: false` (brief Trap 5).
- `lightweight-charts` ^5.2.1 runs for real under jsdom: `workspaces/dashboard/panels/equity-candles.spec.ts` mounts real charts and reaches them through a cast (`fixture.componentInstance as unknown as { chart: … }`). No spec in the repo uses `vi.mock`; these tasks do not either. jsdom has no `ResizeObserver`: specs stub it with `vi.stubGlobal`.
- `src/test-setup.ts` injects the flattened Graphite `:root` literals (palette names such as `--doctena-mint-400` included). A spec measures Navy by appending a `:root[data-theme="navy"]{…}` style built from `resolveTokenIn('navy', name)` (`ui/testing/theme-tokens.ts`), the way the equity-candles theme spec does.
- The colour gate (`ui/primitives.spec.ts`) forbids hex and `rgb()`/`hsl()` literals in `.ts` source; `'transparent'` is a keyword and is allowed.
- `ui/format.ts`: `num(v, 2)` groups thousands and signs a loss with U+2212; `rMultiple(v)` is `+1.50R` / `−1.00R` / `0.00R`; `pct(v, 2)` is `+3.00%` / `−2.50%`.
- `ChartPalette` literals exist in two spec fixtures (`ui/chart/indicator-panes.spec.ts:38`, `ui/chart/plan-lines.spec.ts:22`), so this part adds **no** `ChartPalette` field: the extra inks (`--text-secondary` axis text, `--accent-soft` area fill) are read through the new `themedToken()` instead, and those fixtures stay untouched.
- `resolveToken(name)` lives in `ui/testing/resolve-token.ts` (Graphite), `resolveTokenIn(theme, name)` in `ui/testing/theme-tokens.ts`; `installMatchMediaPolyfill()` in `src/app/testing/match-media-polyfill.ts` (fancy-canvas needs `matchMedia` before a real chart is created).
- `lightweight-charts` v5 typings used below exist (`frontend/node_modules/lightweight-charts/dist/typings.d.ts`): `PriceFormatCustom { type: 'custom'; formatter; minMove }`, `AreaSeries`, `BaselineSeries`, `CandlestickSeries`, `LineSeries`, `LineStyle`, `IPriceLine`, `LogicalRange`, `LogicalRangeChangeEventHandler`, `ISeriesApi.seriesType()` / `.data()` / `.priceFormatter()`, `IChartApi.removeSeries()`, series options `lineVisible` and `pointMarkersVisible`.
- `workspaces/gallery/gallery.spec.ts` ("the gallery shows every primitive") reads every `selector: 'sb-…'` under `ui/` off disk and fails until `gallery.ts` contains `<sb-<name>`: a new `ui/` component ships with its Gallery exhibit in the same task.

---

# Phase 7 — One chart theme

### Task V246-12: Chart theme: `priceFormat`, `rFormat`, `pctFormat`, `applyChartTheme`, `SVG_CHART_TOKENS`, Navy fallback logged once

**Model:** sonnet — additive exports on one existing 177-line module with every value, name and test fixed below; no consumer changes.

**Files:**
- Modify: `frontend/src/app/ui/chart/chart-theme.ts` — the import block (lines 1-4), `chartPalette()` (lines 105-129), and new exports appended after `chartOptions()` (ends line 177)
- Modify: `frontend/src/app/ui/chart/chart-theme.spec.ts` — the import block (lines 1-4) and four `describe` blocks appended after the last one (file ends line 180)

**Interfaces:**
- Consumes: `token()`, `tokenPx()`, `CHART_CHROME` (`ui/chart/chart-frame.ts`, unchanged); `num`, `pct`, `rMultiple` (`ui/format.ts`, unchanged); the existing `ChartPalette`, `chartPalette()`, `chartOptions()`.
- Produces (V246-13, V246-14, V246-16, V246-17 import these from `ui/chart/chart-theme`):
  - `export const priceFormat: PriceFormatCustom` — `num(v, 2)`: `997,800.00`, `−1,234.50`.
  - `export const rFormat: PriceFormatCustom` — `rMultiple(v)`: `+1.50R`, `−1.00R`, `0.00R`.
  - `export const pctFormat: PriceFormatCustom` — `pct(v, 2)`: `+3.00%`, `−2.50%`.
  - `export function applyChartTheme(chart: IChartApi, palette: ChartPalette = chartPalette()): void` — applies `chartOptions(palette)` minus `autoSize` (theming never changes sizing), with `layout.textColor` = the `SVG_CHART_TOKENS.axisText` ink. Like `chartOptions()`, it sets `timeScale.timeVisible: false`; a caller with an intraday axis re-applies its own time-scale options afterwards (brief Trap 5).
  - `export const SVG_CHART_TOKENS` — the `as const` object of Step 5: token names `line`, `pos`, `neg`, `grid`, `axisText`, `crosshair`, `barRadius`, `labelSize` (bare custom-property names, `var(<name>)` in CSS or `themedToken(<name>)` on a canvas) and px numbers `strokeWidth`, `strokeWidthThin`, `barGap`.
  - `export function themedToken(name: string): string` — `token(name)`; when that is empty, the value `name` takes under `data-theme="navy"`, with one `console.warn` per name per page load. Not in the index ledger: a helper V246-13 consumes for `--accent-soft`; `chartPalette()` now reads every entry through it.

**Why.** Spec §A3 "`ui/chart/chart-theme.ts`": one module exports the series colours from the tokens, `priceFormat` (thousands separators, two decimals, the true minus), `rFormat` (signed, `R` suffix), `applyChartTheme(chart)` and `SVG_CHART_TOKENS`. The module already exists (Handoff 5): this task extends it. Token names follow Handoff 3: the spec's `--money-pos/-neg` are `--pos/--neg`, `--border-subtle` is `--border`, `--text-tertiary` (crosshair) is `--text-muted`; axis text is the spec's own `--text-secondary`. The edge-state rule "a missing token falls back to the Navy value and logs once" is `themedToken()`: Navy is the default theme (v240), and the only place its values live at runtime is the stylesheet's `:root[data-theme="navy"]` block, so the fallback reads it by setting the root attribute to `navy` for one synchronous read and putting it back (no frame paints in between, and no `MutationObserver` in `frontend/src` reacts to it). A token missing under Navy too stays empty (lightweight-charts ignores an empty colour) and is still logged once. `pctFormat` is the third `valueFormat` the spec gives `sb-time-series` (`'price' | 'r' | 'pct'`), so it lives beside the other two.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/chart/chart-theme.spec.ts`, replace the import block (lines 1-4) with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { createChart, LineSeries } from 'lightweight-charts';
import type { ChartOptions, DeepPartial, IChartApi } from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { resolveToken } from '../testing/resolve-token';
import { resolveTokenIn } from '../testing/theme-tokens';
import { CHART_CHROME } from './chart-frame';
import {
  SVG_CHART_TOKENS, TICK_FALLBACK_PX, applyChartTheme, chartOptions, chartPalette, pctFormat, priceFormat,
  rFormat, themedToken, tokenPx,
} from './chart-theme';

// The real-chart tests below create a lightweight-charts instance; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();
```

Append at the end of the file:

```ts
/* -- v246 §A3 -- formats, applyChartTheme, SVG tokens, Navy fallback -------- */

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/chart/chart-theme.ts'), 'utf8');

/** Layers Navy values for `names` the way tokens.css does and switches the root to Navy; returns the undo. */
function navyFor(names: readonly string[]): () => void {
  const root = document.documentElement;
  const previous = root.getAttribute('data-theme');
  const style = document.createElement('style');
  style.textContent = `:root[data-theme="navy"]{${names.map((n) => `${n}:${resolveTokenIn('navy', n)}`).join(';')}}`;
  document.head.appendChild(style);
  root.setAttribute('data-theme', 'navy');
  return () => {
    style.remove();
    if (previous === null) root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', previous);
  };
}

function recordingChart(): { chart: IChartApi; applied: DeepPartial<ChartOptions>[] } {
  const applied: DeepPartial<ChartOptions>[] = [];
  const chart = { applyOptions: (options: DeepPartial<ChartOptions>) => applied.push(options) } as unknown as IChartApi;
  return { chart, applied };
}

describe('value formats (v246 §A3)', () => {
  it('prices group thousands and sign a loss with the true minus', () => {
    expect(priceFormat.type).toBe('custom');
    expect(priceFormat.minMove).toBe(0.01);
    expect(priceFormat.formatter(997800)).toBe('997,800.00');
    expect(priceFormat.formatter(-1234.5)).toBe('−1,234.50');
    expect(priceFormat.formatter(-1234.5)).not.toContain('-');
    expect(priceFormat.formatter(-0.001)).toBe('0.00');
  });

  it('signs an R and suffixes it', () => {
    expect(rFormat.formatter(1.5)).toBe('+1.50R');
    expect(rFormat.formatter(-1)).toBe('−1.00R');
    expect(rFormat.formatter(0)).toBe('0.00R');
  });

  it('signs a percentage', () => {
    expect(pctFormat.formatter(3)).toBe('+3.00%');
    expect(pctFormat.formatter(-2.5)).toBe('−2.50%');
  });

  it('is what a real series prints on its price scale', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    const chart = createChart(element, { width: 300, height: 200 });
    try {
      const series = chart.addSeries(LineSeries, { priceFormat });
      expect(series.priceFormatter().format(997800)).toBe('997,800.00');
      series.applyOptions({ priceFormat: rFormat });
      expect(series.priceFormatter().format(-1)).toBe('−1.00R');
    } finally {
      chart.remove();
      element.remove();
    }
  });
});

describe('applyChartTheme (v246 §A3)', () => {
  it('applies the chart chrome with the axis text in --text-secondary', () => {
    const { chart, applied } = recordingChart();
    const palette = chartPalette();
    applyChartTheme(chart);

    expect(applied).toHaveLength(1);
    const options = applied[0];
    expect(options.layout?.background).toEqual({ color: palette.surface });
    expect(options.layout?.textColor).toBe(resolveToken('--text-secondary'));
    expect(options.grid?.vertLines?.color).toBe(palette.border);
    expect(options.grid?.horzLines?.color).toBe(palette.border);
    expect(options.rightPriceScale?.borderColor).toBe(palette.axis);
    expect(options.timeScale?.borderColor).toBe(palette.axis);
    expect(options.timeScale?.timeVisible).toBe(false);
    expect(options.crosshair?.vertLine?.color).toBe(resolveToken('--text-muted'));
    expect(options.crosshair?.horzLine?.color).toBe(resolveToken('--text-muted'));
  });

  it('never touches sizing: autoSize is not part of the theme', () => {
    const { chart, applied } = recordingChart();
    applyChartTheme(chart);
    expect(Object.hasOwn(applied[0], 'autoSize')).toBe(false);
    expect(chartOptions(chartPalette()).autoSize).toBe(true);
  });

  it('uses the palette it is given', () => {
    const { chart, applied } = recordingChart();
    applyChartTheme(chart, { ...chartPalette(), surface: 'given-surface' });
    expect(applied[0].layout?.background).toEqual({ color: 'given-surface' });
  });

  it('is accepted by a real chart and leaves it fixed-size', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    const chart = createChart(element, { width: 300, height: 200 });
    try {
      applyChartTheme(chart);
      expect(chart.options().autoSize).toBe(false);
      expect(chart.options().layout.textColor).toBe(resolveToken('--text-secondary'));
    } finally {
      chart.remove();
      element.remove();
    }
  });

  it('follows a theme switch: the next call reads the Navy inks', () => {
    const graphite = { surface: resolveToken('--surface'), text: resolveToken('--text-secondary') };
    const undo = navyFor(['--surface', '--text-secondary']);
    try {
      const { chart, applied } = recordingChart();
      applyChartTheme(chart);
      expect(applied[0].layout?.background).toEqual({ color: resolveTokenIn('navy', '--surface') });
      expect(applied[0].layout?.textColor).toBe(resolveTokenIn('navy', '--text-secondary'));
      expect(resolveTokenIn('navy', '--surface')).not.toBe(graphite.surface);
      expect(resolveTokenIn('navy', '--text-secondary')).not.toBe(graphite.text);
    } finally {
      undo();
    }
  });
});

describe('SVG_CHART_TOKENS (v246 §A3)', () => {
  it('names real tokens, mapped from the spec (Handoff 3)', () => {
    expect(SVG_CHART_TOKENS.line).toBe('--accent');
    expect(SVG_CHART_TOKENS.pos).toBe('--pos');
    expect(SVG_CHART_TOKENS.neg).toBe('--neg');
    expect(SVG_CHART_TOKENS.grid).toBe(CHART_CHROME.grid);
    expect(SVG_CHART_TOKENS.axisText).toBe('--text-secondary');
    expect(SVG_CHART_TOKENS.crosshair).toBe('--text-muted');
    expect(SVG_CHART_TOKENS.barRadius).toBe('--radius-sm');
    expect(SVG_CHART_TOKENS.labelSize).toBe(CHART_CHROME.tickSize);
    for (const name of [SVG_CHART_TOKENS.line, SVG_CHART_TOKENS.pos, SVG_CHART_TOKENS.neg, SVG_CHART_TOKENS.grid,
      SVG_CHART_TOKENS.axisText, SVG_CHART_TOKENS.crosshair, SVG_CHART_TOKENS.barRadius, SVG_CHART_TOKENS.labelSize]) {
      expect(() => resolveToken(name), name).not.toThrow();
    }
  });

  it('carries the stroke widths and the bar gap the SVG charts draw today, in px', () => {
    expect(SVG_CHART_TOKENS.strokeWidth).toBe(2);
    expect(SVG_CHART_TOKENS.strokeWidthThin).toBe(1);
    expect(SVG_CHART_TOKENS.barGap).toBe(2);
  });
});

describe('themedToken: the Navy fallback (v246 edge states)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns a resolving token as is, without a warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(themedToken('--accent')).toBe(resolveToken('--accent'));
    expect(warn).not.toHaveBeenCalled();
  });

  it('falls back to the Navy value for a token the current theme lacks, and warns once', () => {
    const root = document.documentElement;
    const previous = root.getAttribute('data-theme');
    const navy = resolveTokenIn('navy', '--surface');
    const style = document.createElement('style');
    style.textContent = `:root[data-theme="navy"]{--v246-navy-only:${navy}}`;
    document.head.appendChild(style);
    root.setAttribute('data-theme', 'graphite');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      expect(themedToken('--v246-navy-only')).toBe(navy);
      expect(themedToken('--v246-navy-only')).toBe(navy);
      expect(warn).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0][0])).toContain('--v246-navy-only');
      expect(root.getAttribute('data-theme')).toBe('graphite');
    } finally {
      style.remove();
      if (previous === null) root.removeAttribute('data-theme');
      else root.setAttribute('data-theme', previous);
    }
  });

  it('returns empty for a token missing under Navy too, restores the root, and warns once', () => {
    const root = document.documentElement;
    const previous = root.getAttribute('data-theme');
    root.removeAttribute('data-theme');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      expect(themedToken('--v246-nowhere')).toBe('');
      expect(themedToken('--v246-nowhere')).toBe('');
      expect(warn).toHaveBeenCalledTimes(1);
      expect(root.hasAttribute('data-theme')).toBe(false);
    } finally {
      if (previous !== null) root.setAttribute('data-theme', previous);
    }
  });

  it('reads every palette entry through it', () => {
    const body = SOURCE.slice(SOURCE.indexOf('export function chartPalette'), SOURCE.indexOf('export const TICK_FALLBACK_PX'));
    expect(body.match(/\btoken\(/g)).toBeNull();
    expect(body.match(/\bthemedToken\(/g)).toHaveLength(Object.keys(chartPalette()).length);
  });
});
```

`TICK_FALLBACK_PX`, `chartOptions` and `tokenPx` stay imported: the existing blocks above use them.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/chart-theme.spec.ts`
Expected: FAIL to compile: `./chart-theme` has no exported member `SVG_CHART_TOKENS`, `applyChartTheme`, `pctFormat`, `priceFormat`, `rFormat` or `themedToken`.

- [ ] **Step 3: Imports**

In `frontend/src/app/ui/chart/chart-theme.ts`, replace lines 1-4 with:

```ts
import { CrosshairMode, DeepPartial } from 'lightweight-charts';
import type { ChartOptions, IChartApi, PriceFormatCustom } from 'lightweight-charts';

import { num, pct, rMultiple } from '../format';
import { CHART_CHROME, token, tokenPx } from './chart-frame';
```

- [ ] **Step 4: Read the palette through `themedToken()`**

Inside `chartPalette()` only (lines 105-129), turn each of the 18 `token(` calls into `themedToken(`; entries, order and the `CHART_CHROME.grid` comment stay:

```bash
cd frontend && sed -i '105,129s/\btoken(/themedToken(/' src/app/ui/chart/chart-theme.ts && sed -n '105,129p' src/app/ui/chart/chart-theme.ts | grep -c 'themedToken('
```

Expected: `18` (every entry from `up: themedToken('--pos')` to `tooltipBorder: themedToken(CHART_CHROME.tooltipBorder)`). The re-export on line 13 (`export { token, tokenPx };`) is outside the range and stays.

- [ ] **Step 5: Append the new exports**

Append after `chartOptions()` (after line 177):

```ts
/* -- v246 §A3: one chart theme -------------------------------------------- */

/** Token names logged once already (v246 edge states: "logs once"). */
const warnedTokens = new Set<string>();

/**
 * `token(name)`, falling back to the value `name` takes under Navy -- the
 * default theme since v240 -- when the current theme resolves it empty, and
 * saying so once per name. The Navy values live only in the stylesheet's
 * `:root[data-theme="navy"]` block (the colour gate forbids a copy in a `.ts`
 * file), so the fallback reads them by switching the root attribute to
 * `navy` for one synchronous read and restoring it; no frame paints in
 * between. A token missing under Navy too stays empty, which
 * lightweight-charts draws as nothing rather than crashing.
 */
export function themedToken(name: string): string {
  const value = token(name);
  if (value) return value;
  const navy = navyValue(name);
  if (!warnedTokens.has(name)) {
    warnedTokens.add(name);
    console.warn(`chart-theme: ${name} did not resolve; ${navy ? 'using its Navy value' : 'it is missing under Navy too'}`);
  }
  return navy;
}

function navyValue(name: string): string {
  const root = document.documentElement;
  const previous = root.getAttribute('data-theme');
  if (previous === 'navy') return '';
  root.setAttribute('data-theme', 'navy');
  try {
    return token(name);
  } finally {
    if (previous === null) root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', previous);
  }
}

/**
 * Tokens and dimensions for the six SVG charts (line-chart, histogram,
 * bar-list, sparkline, share-bar, gauge; V246-17), so they stop carrying
 * their own literals. Colour, radius and size entries are bare custom-property
 * NAMES, like `CHART_CHROME`: a stylesheet embeds `var(<name>)`, a canvas
 * reads `themedToken(<name>)`. The numbers are px, the values those charts
 * draw today (series stroke 2, zero line and grid 1, bar gap 2).
 * The spec's names are mapped onto real tokens (v246 Handoff 3).
 */
export const SVG_CHART_TOKENS = {
  line: '--accent',
  pos: '--pos',
  neg: '--neg',
  grid: CHART_CHROME.grid,
  axisText: '--text-secondary',
  crosshair: '--text-muted',
  strokeWidth: 2,
  strokeWidthThin: 1,
  barRadius: '--radius-sm',
  barGap: 2,
  labelSize: CHART_CHROME.tickSize,
} as const;

/** A money or price axis: thousands grouped, two decimals, a true minus on a loss (`997,800.00`, `−1,234.50`). */
export const priceFormat: PriceFormatCustom = { type: 'custom', minMove: 0.01, formatter: (value: number) => num(value, 2) };

/** An R axis: signed, `R` suffix (`+1.50R`, `−1.00R`, `0.00R`). */
export const rFormat: PriceFormatCustom = { type: 'custom', minMove: 0.01, formatter: (value: number) => rMultiple(value) };

/** A percentage axis: signed (`+3.00%`, `−2.50%`). */
export const pctFormat: PriceFormatCustom = { type: 'custom', minMove: 0.01, formatter: (value: number) => pct(value, 2) };

/**
 * Themes any lightweight-charts instance: layout, grid, crosshair, time and
 * price scale borders from `chartOptions(palette)`, with the scale text in
 * the SVG charts' axis ink so canvas and SVG axes read alike. `autoSize` is
 * left out: theming must not change how a chart sizes itself. Like
 * `chartOptions()`, this sets `timeScale.timeVisible: false`; a chart with an
 * intraday axis re-applies its own time-scale options after calling this.
 * Call again on a theme switch: every colour is read at call time.
 */
export function applyChartTheme(chart: IChartApi, palette: ChartPalette = chartPalette()): void {
  const options = chartOptions(palette);
  delete options.autoSize;
  chart.applyOptions({ ...options, layout: { ...options.layout, textColor: themedToken(SVG_CHART_TOKENS.axisText) } });
}
```

`SVG_CHART_TOKENS` is declared after `chartPalette()` but only read inside `applyChartTheme()` at call time, so the order is safe.

- [ ] **Step 6: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/chart-theme.spec.ts`
Expected: PASS, 0 failed (the existing `chartPalette`, `chartOptions`, `tokenPx` and v195 blocks included).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed. It pulls in every spec that imports `chart-theme` (equity-candles, trade-chart, the primitives, indicator-panes, plan-lines): their colours are unchanged because every token resolves under jsdom, so `themedToken()` returns what `token()` did. The colour gate (`ui/primitives.spec.ts`) passes: the new code has no hex, `rgb()` or `hsl()` literal.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/chart/chart-theme.ts frontend/src/app/ui/chart/chart-theme.spec.ts
git commit -m "feat(v246): chart theme -- priceFormat/rFormat/pctFormat, applyChartTheme, SVG_CHART_TOKENS, Navy fallback logged once" -m "Extends the existing chart-theme.ts (spec §A3): grouped, true-minus price axis; signed R and % axes; one theme call for any lightweight-charts instance (no autoSize, axis text --text-secondary); bare token names for the SVG charts; chartPalette reads through themedToken, which falls back to the Navy value once per missing token."
```


# Phase 8 — `sb-time-series` and linked scrolling

### Task V246-13: `sb-time-series`: area / baseline / candles, value formats, height, Gallery exhibit

**Model:** opus — a new canvas-chart component driving a third-party API for real under jsdom, with effect ordering (build, data, style, size) that V246-13b and V246-14 extend.

**Files:**
- Create: `frontend/src/app/ui/chart/time-series.ts`
- Create: `frontend/src/app/ui/chart/time-series.spec.ts`
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts` — one import (above line 9), `imports: [...]` (insert `TimeSeries` before `Timeline`, ~line 221), two exhibits after `<sb-line-chart [series]="lineChartSeries" />` (line 584), two fields above `protected readonly lineChartSeries` (line 1146). Not in the index ledger; the Gallery gate (part header) requires it.

**Interfaces:**
- Consumes (V246-12, `ui/chart/chart-theme`): `applyChartTheme(chart, palette)`, `chartPalette()`, `priceFormat`, `rFormat`, `pctFormat`, `themedToken(name)`.
- Produces (exact, from the index ledger; V246-15 binds them):
  - `TimeSeries` (`sb-time-series`): `kind = input.required<TimeSeriesKind>()`, `points = input.required<readonly TimeSeriesDatum[]>()`, `valueFormat = input<TimeSeriesFormat>('price')`, `height = input<number>(220)`, `label = input.required<string>()`.
  - `export type TimeSeriesKind = 'area' | 'baseline' | 'candles'`; `export type TimeSeriesFormat = 'price' | 'r' | 'pct'`; `export interface TimeSeriesPoint { time: string; value: number }`; `export interface TimeSeriesCandle { time: string; open: number; high: number; low: number; close: number }`; `export type TimeSeriesDatum = TimeSeriesPoint | TimeSeriesCandle`.
  - `export function collapseByDay<T extends { time: string }>(points: readonly T[]): T[]` — one row per `time.slice(0, 10)`, the last in input order wins, `time` trimmed to `YYYY-MM-DD`, sorted ascending.
  - For V246-13b and V246-14 (private, reached by name): `chart: IChartApi | null` (created once and kept across a `kind` change; only the series is rebuilt), `plottable()`, `areaOptions()`, `baselineOptions()`, `seriesOptions()`, `build()`, `render()`, `restyle()`, `resize()`, the style effect, `teardown()` (the `DestroyRef.onDestroy` body), and the spec helpers `mount()`, `set()`, `inside()`, `values()`, `EQUITY` in `time-series.spec.ts`.

**Why.** Spec §A3 "`sb-time-series`": a thin `lightweight-charts` wrapper with `kind`, `points`, `valueFormat` and `height`. `area` is the equity curve: the accent line over an accent → transparent fill (`--accent-soft` on top, the keyword `'transparent'` at the bottom). `baseline` at 0 is drawdown: below zero filled with `--neg-soft` (the 12% loss tint, "`--money-neg` at low opacity" under Handoff 3) under a `--neg` line, plus a zero line in the axis ink (`--border-strong`, `chartPalette().axis`). `candles` draws OHLC by day in the up/down inks. lightweight-charts rejects two rows with one time, so same-day points collapse (brief §3). `label` names a canvas that has no text of its own (`role="img"`); the host's height is the `height` input, so the card reserves its space before the chart paints. Width comes from the plot box: this task resizes on a `height` change and on new data. V246-13b (the second half of this task, split at 20 KB) adds the edge states (non-finite values, 0 and 1 point, the fit once a width arrives), the `ResizeObserver`, the theme repaint and the full release on destroy.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/ui/chart/time-series.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import type {
  AreaSeriesOptions, BaselineSeriesOptions, CandlestickSeriesOptions, IChartApi, IPriceLine, ISeriesApi,
  SeriesType, SingleValueData,
} from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { resolveToken } from '../testing/resolve-token';
import { THEME_STORAGE } from '../theme.service';
import {
  TimeSeries, TimeSeriesCandle, TimeSeriesDatum, TimeSeriesFormat, TimeSeriesKind, TimeSeriesPoint, collapseByDay,
} from './time-series';

// A real lightweight-charts chart is created; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

type Internals = { chart: IChartApi | null; series: ISeriesApi<SeriesType> | null; zeroLine: IPriceLine | null };
const inside = (fixture: ComponentFixture<TimeSeries>) => fixture.componentInstance as unknown as Internals;
const values = (fixture: ComponentFixture<TimeSeries>) =>
  inside(fixture).series!.data().map((row) => (row as SingleValueData).value);

const EQUITY: TimeSeriesPoint[] = [
  { time: '2026-10-01', value: 0 }, { time: '2026-10-02', value: 120.5 }, { time: '2026-10-05', value: -40 },
];
const CANDLES: TimeSeriesCandle[] = [
  { time: '2026-10-01', open: 100, high: 120, low: 90, close: 110 },
  { time: '2026-10-02', open: 110, high: 112, low: 95, close: 98 },
];

function mount(kind: TimeSeriesKind, points: readonly TimeSeriesDatum[], valueFormat?: TimeSeriesFormat) {
  TestBed.configureTestingModule({
    // Black first: Navy is the default since v240, and V246-13b's theme test flips to Navy.
    providers: [provideZonelessChangeDetection(),
      { provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }],
  });
  const fixture = TestBed.createComponent(TimeSeries);
  fixture.componentRef.setInput('kind', kind);
  fixture.componentRef.setInput('points', points);
  fixture.componentRef.setInput('label', 'Equity curve');
  if (valueFormat) fixture.componentRef.setInput('valueFormat', valueFormat);
  fixture.detectChanges();
  return fixture;
}

function set(fixture: ComponentFixture<TimeSeries>, name: string, value: unknown): void {
  fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
}

afterEach(() => vi.restoreAllMocks());

describe('collapseByDay', () => {
  it('keeps the last point of each day, keyed and labelled by the date part, in time order', () => {
    expect(collapseByDay([
      { time: '2026-10-01T10:00:00Z', value: 1 }, { time: '2026-10-01T16:00:00Z', value: 2 }, { time: '2026-09-30', value: 0 },
    ])).toEqual([{ time: '2026-09-30', value: 0 }, { time: '2026-10-01', value: 2 }]);
  });

  it('returns nothing for nothing', () => {
    expect(collapseByDay([])).toEqual([]);
  });
});

describe('sb-time-series (v246 §A3)', () => {
  it('draws an area in the accent over an accent-to-transparent fill, with a zero line', () => {
    const fixture = mount('area', EQUITY);
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as AreaSeriesOptions;
    expect(series!.seriesType()).toBe('Area');
    expect(options.lineColor).toBe(resolveToken('--accent'));
    expect(options.topColor).toBe(resolveToken('--accent-soft'));
    expect(options.bottomColor).toBe('transparent');
    expect(values(fixture)).toEqual([0, 120.5, -40]);
    expect(zeroLine!.options().price).toBe(0);
    expect(zeroLine!.options().color).toBe(resolveToken('--border-strong'));
  });

  it('draws drawdown as a baseline at zero, shaded in the loss tint below it', () => {
    const fixture = mount('baseline', [{ time: '2026-10-01', value: 0 }, { time: '2026-10-02', value: -1.5 }], 'r');
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as BaselineSeriesOptions;
    expect(series!.seriesType()).toBe('Baseline');
    expect(options.baseValue).toEqual({ type: 'price', price: 0 });
    expect(options.bottomLineColor).toBe(resolveToken('--neg'));
    expect(options.bottomFillColor1).toBe(resolveToken('--neg-soft'));
    expect(options.bottomFillColor2).toBe(resolveToken('--neg-soft'));
    expect(options.topFillColor1).toBe('transparent');
    expect(zeroLine).not.toBeNull();
  });

  it('draws candles in the up and down inks, without a zero line', () => {
    const fixture = mount('candles', CANDLES);
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as CandlestickSeriesOptions;
    expect(series!.seriesType()).toBe('Candlestick');
    expect(options.upColor).toBe(resolveToken('--pos'));
    expect(options.downColor).toBe(resolveToken('--neg'));
    expect(series!.data()).toHaveLength(2);
    expect(zeroLine).toBeNull();
  });

  it('themes the chart through applyChartTheme', () => {
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    expect(chart.options().layout.textColor).toBe(resolveToken('--text-secondary'));
    expect(chart.options().autoSize).toBe(false);
  });

  it('formats the price scale per valueFormat', () => {
    const fixture = mount('area', EQUITY);
    const format = (value: number) => inside(fixture).series!.priceFormatter().format(value);
    expect(format(997800)).toBe('997,800.00');
    set(fixture, 'valueFormat', 'r');
    expect(format(-1)).toBe('−1.00R');
    set(fixture, 'valueFormat', 'pct');
    expect(format(3)).toBe('+3.00%');
  });

  it('rebuilds only the series when the kind changes', () => {
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const removed = vi.spyOn(chart, 'removeSeries');
    set(fixture, 'kind', 'baseline');
    expect(inside(fixture).chart).toBe(chart);
    expect(removed).toHaveBeenCalledTimes(1);
    expect(inside(fixture).series!.seriesType()).toBe('Baseline');
    expect(values(fixture)).toEqual([0, 120.5, -40]);
  });

  it('names the canvas and reserves its height', () => {
    const fixture = mount('area', EQUITY);
    const host = fixture.nativeElement as HTMLElement;
    expect(host.getAttribute('role')).toBe('img');
    expect(host.getAttribute('aria-label')).toBe('Equity curve');
    expect(host.style.height).toBe('220px');
    const resize = vi.spyOn(inside(fixture).chart!, 'resize');
    set(fixture, 'height', 160);
    expect(host.style.height).toBe('160px');
    expect(resize).toHaveBeenLastCalledWith(expect.any(Number), 160);
  });

  it('removes its chart on destroy', () => {
    const fixture = mount('area', EQUITY);
    const remove = vi.spyOn(inside(fixture).chart!, 'remove');
    fixture.destroy();
    expect(remove).toHaveBeenCalledTimes(1);
    expect(inside(fixture).chart).toBeNull();
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts`
Expected: FAIL to compile: cannot find module `./time-series`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/ui/chart/time-series.ts`:

```ts
import {
  ChangeDetectionStrategy, Component, DestroyRef, ElementRef, effect, inject, input, untracked, viewChild,
} from '@angular/core';
import { AreaSeries, BaselineSeries, CandlestickSeries, LineStyle, createChart } from 'lightweight-charts';
import type {
  AreaSeriesPartialOptions, BaselineSeriesPartialOptions, CandlestickData, CandlestickSeriesPartialOptions,
  IChartApi, IPriceLine, ISeriesApi, SeriesType, SingleValueData, Time,
} from 'lightweight-charts';

import { ChartPalette, applyChartTheme, chartPalette, pctFormat, priceFormat, rFormat, themedToken } from './chart-theme';

export type TimeSeriesKind = 'area' | 'baseline' | 'candles';
export type TimeSeriesFormat = 'price' | 'r' | 'pct';
export interface TimeSeriesPoint { time: string; value: number }
export interface TimeSeriesCandle { time: string; open: number; high: number; low: number; close: number }
export type TimeSeriesDatum = TimeSeriesPoint | TimeSeriesCandle;

const FORMATS = { price: priceFormat, r: rFormat, pct: pctFormat } as const;

type Row = SingleValueData<Time> | CandlestickData<Time>;
type KindOptions = AreaSeriesPartialOptions | BaselineSeriesPartialOptions | CandlestickSeriesPartialOptions;

/** One row per day (`time.slice(0, 10)`), the last in input order winning, sorted by day:
 *  lightweight-charts rejects two rows with one time. */
export function collapseByDay<T extends { time: string }>(points: readonly T[]): T[] {
  const byDay = new Map<string, T>();
  for (const point of points) {
    const day = point.time.slice(0, 10);
    byDay.set(day, { ...point, time: day });
  }
  return [...byDay.values()].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
}

const isCandle = (datum: TimeSeriesDatum): datum is TimeSeriesCandle => 'open' in datum;

/** The right shape for `kind`; a row of the other shape is dropped. */
function plottable(kind: TimeSeriesKind, datum: TimeSeriesDatum): boolean {
  return kind === 'candles' ? isCandle(datum) : !isCandle(datum);
}

function rows(kind: TimeSeriesKind, points: readonly TimeSeriesDatum[]): Row[] {
  return collapseByDay(points.filter((datum) => plottable(kind, datum))).map((datum) => isCandle(datum)
    ? { time: datum.time as Time, open: datum.open, high: datum.high, low: datum.low, close: datum.close }
    : { time: datum.time as Time, value: datum.value });
}

function areaOptions(palette: ChartPalette): AreaSeriesPartialOptions {
  return { lineWidth: 2, priceLineVisible: false,
    lineColor: palette.accent, topColor: themedToken('--accent-soft'), bottomColor: 'transparent' };
}

function baselineOptions(palette: ChartPalette): BaselineSeriesPartialOptions {
  return { lineWidth: 2, priceLineVisible: false,
    baseValue: { type: 'price', price: 0 },
    topLineColor: palette.down, topFillColor1: 'transparent', topFillColor2: 'transparent',
    bottomLineColor: palette.down, bottomFillColor1: palette.negSoft, bottomFillColor2: palette.negSoft };
}

function candleOptions(palette: ChartPalette): CandlestickSeriesPartialOptions {
  return { priceLineVisible: false, borderVisible: false,
    upColor: palette.up, downColor: palette.down, wickUpColor: palette.up, wickDownColor: palette.down };
}

function seriesOptions(kind: TimeSeriesKind, palette: ChartPalette): KindOptions {
  if (kind === 'area') return areaOptions(palette);
  if (kind === 'baseline') return baselineOptions(palette);
  return candleOptions(palette);
}

function addSeries(chart: IChartApi, kind: TimeSeriesKind): ISeriesApi<SeriesType> {
  if (kind === 'area') return chart.addSeries(AreaSeries);
  if (kind === 'baseline') return chart.addSeries(BaselineSeries);
  return chart.addSeries(CandlestickSeries);
}

/**
 * v246 §A3: a time series on lightweight-charts, themed by `chart-theme.ts`.
 * `area` is an equity curve, `baseline` (base 0) a drawdown shaded below
 * zero, `candles` OHLC by day. The chart is created once; a `kind` change
 * rebuilds only the series. Sized from the plot box (no `autoSize`, which
 * `applyChartTheme` leaves out), released in `teardown()`.
 */
@Component({
  selector: 'sb-time-series',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'img', '[attr.aria-label]': 'label()', '[style.height.px]': 'height()' },
  template: `<div class="plot" #plot></div>`,
  styles: `
    :host { display: block; position: relative; min-width: 0; }
    .plot { position: absolute; inset: 0; }
  `,
})
export class TimeSeries {
  readonly kind = input.required<TimeSeriesKind>();
  readonly points = input.required<readonly TimeSeriesDatum[]>();
  readonly valueFormat = input<TimeSeriesFormat>('price');
  readonly height = input<number>(220);
  readonly label = input.required<string>();

  private readonly plot = viewChild.required<ElementRef<HTMLDivElement>>('plot');
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private zeroLine: IPriceLine | null = null;

  constructor() {
    effect(() => {
      const element = this.plot().nativeElement;
      const kind = this.kind();
      untracked(() => this.build(element, kind));
    });
    effect(() => {
      const data = rows(this.kind(), this.points());
      untracked(() => this.render(data));
    });
    effect(() => {
      this.valueFormat();
      untracked(() => this.restyle());
    });
    effect(() => {
      const height = this.height();
      untracked(() => this.resize(height));
    });
    inject(DestroyRef).onDestroy(() => this.teardown());
  }

  private build(element: HTMLElement, kind: TimeSeriesKind): void {
    if (!this.chart) {
      this.chart = createChart(element, { width: element.clientWidth, height: this.height() });
    }
    if (this.series) this.chart.removeSeries(this.series);
    this.series = addSeries(this.chart, kind);
    this.zeroLine = kind === 'candles' ? null : this.series.createPriceLine({
      price: 0, color: chartPalette().axis, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false, title: '',
    });
  }

  private render(data: Row[]): void {
    if (!this.chart || !this.series) return;
    this.series.setData(data);
    this.restyle();
    this.resize(this.height());
  }

  private restyle(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    const palette = chartPalette();
    applyChartTheme(chart, palette);
    series.applyOptions({ ...seriesOptions(this.kind(), palette), priceFormat: FORMATS[this.valueFormat()] });
    this.zeroLine?.applyOptions({ color: palette.axis });
  }

  /** Width from the plot box, height from the input. */
  private resize(height: number): void {
    this.chart?.resize(this.plot().nativeElement.clientWidth, height);
  }

  private teardown(): void {
    this.chart?.remove();
    this.chart = null;
    this.series = null;
    this.zeroLine = null;
  }
}
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 5: Exhibit it in the Gallery**

In `frontend/src/app/workspaces/gallery/gallery.ts`, add above line 9 (`import { TradeChart } …`):

```ts
import { TimeSeries, TimeSeriesPoint } from '../../ui/chart/time-series';
```

In the `imports: [...]` array, insert `TimeSeries,` directly before `Timeline,`. After `<sb-line-chart [series]="lineChartSeries" />` (line 584) add:

```html
      <sb-time-series kind="area" [points]="timeSeriesEquity" [height]="160" label="Gallery equity curve" />
      <sb-time-series kind="baseline" [points]="timeSeriesDrawdown" valueFormat="r" [height]="120" label="Gallery drawdown in R" />
```

Directly above `protected readonly lineChartSeries` (line 1146) add:

```ts
  /** v246 §A3: sb-time-series, an equity area and a drawdown baseline on the same days. */
  protected readonly timeSeriesEquity: TimeSeriesPoint[] = [
    { time: '2026-09-01', value: 0 }, { time: '2026-09-02', value: 180 }, { time: '2026-09-03', value: 95 },
    { time: '2026-09-04', value: 260 }, { time: '2026-09-07', value: 210 },
  ];
  protected readonly timeSeriesDrawdown: TimeSeriesPoint[] = [
    { time: '2026-09-01', value: 0 }, { time: '2026-09-02', value: 0 }, { time: '2026-09-03', value: -0.85 },
    { time: '2026-09-04', value: 0 }, { time: '2026-09-07', value: -0.5 },
  ];
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/gallery/gallery.spec.ts`
Expected: PASS, 0 failed (`renders sb-time-series` included; the spec already installs the matchMedia polyfill).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed. The source-scanning style gates (`ui/spacing.spec.ts`, `ui/radius.spec.ts`, `ui/primitives.spec.ts`, `ui/money-colour.spec.ts`) pass: the component's CSS has no spacing, radius or colour literal.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/ui/chart/time-series.ts frontend/src/app/ui/chart/time-series.spec.ts frontend/src/app/workspaces/gallery/gallery.ts
git commit -m "feat(v246): sb-time-series -- area, baseline and candles on lightweight-charts with price/R/% scales" -m "Spec §A3: accent area over an --accent-soft fill; drawdown baseline at 0 in --neg-soft with a zero line; same-day points collapse; height reserved on the host; Gallery exhibit (the every-primitive gate)."
```

### Task V246-13b: `sb-time-series` edge states and lifecycle: non-finite values, 0/1 point, fit, `ResizeObserver`, theme repaint, release on destroy

**Model:** opus — effect and teardown ordering on a live canvas chart (a theme effect that must die with the view, an observer that must not outlive the chart), the half of V246-13 a later leak would come from.

**Files:**
- Modify: `frontend/src/app/ui/chart/time-series.ts` (created by V246-13) — one import; `plottable()`, the three option builders, four fields, the style effect, `build()`, `render()`, `resize()`, `teardown()`, a new `observe()`
- Modify: `frontend/src/app/ui/chart/time-series.spec.ts` (created by V246-13) — two import lines and one `describe` appended at the end

**Interfaces:**
- Consumes: V246-13's `time-series.ts` and its spec helpers (`mount()`, `set()`, `inside()`, `values()`, `EQUITY`); `ThemeService` and `THEME_STORAGE` (`ui/theme.service.ts`); `resolveTokenIn` (`ui/testing/theme-tokens.ts`).
- Produces: no new public member; the ledger's `TimeSeries` contract is unchanged. For V246-14: `teardown()` now releases the observer, then the chart (V246-14 inserts the sync release between them), and the chart is still created once in `build()`.

**Why.** This is the second half of V246-13 (split at the 20 KB cap; the controller adds its ledger row below V246-13). Spec "Error, empty and edge states": "`sb-time-series` with 0 points shows the card's existing empty state; with 1 point it draws a marker with no line", so 0 points keep an empty series (the consumer shows its empty state, V246-15) and 1 point turns the line off and the point markers on. A non-finite value (`cum_pct ?? 0` upstream can still meet a `NaN`) is dropped before lightweight-charts sees it. Spec §A3: the component "owns create/resize/destroy (a `ResizeObserver`, removed on destroy)", and "the theme listens to `theme.service.ts` so a theme switch repaints the charts without a reload"; "a spec asserts all three [the range subscription, the observer and the theme subscription] are released on destroy". `ThemeService.theme` is a signal, so the subscription is the read inside the style effect; Angular destroys that effect with the view, which the destroy test proves by flipping the theme after `destroy()` and seeing no `applyOptions`. The range subscription is V246-14's. Fitting waits for a non-zero width (the equity-candles lesson: `fitContent()` on a zero-width chart leaves an unusable range), and fires once per new data set.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/ui/chart/time-series.spec.ts`, change two import lines:

```ts
import { resolveTokenIn } from '../testing/theme-tokens';
import { THEME_STORAGE, ThemeService } from '../theme.service';
```

(the first is added below `import { resolveToken } from '../testing/resolve-token';`, the second replaces `import { THEME_STORAGE } from '../theme.service';`). Append at the end of the file:

```ts
/** A ResizeObserver stand-in: `notify()` fires the last observer's callback. */
function fakeResizeObserver() {
  const state = { notify: () => {}, disconnect: vi.fn() };
  class FakeObserver {
    constructor(callback: () => void) { state.notify = callback; }
    observe(): void {}
    disconnect(): void { state.disconnect(); }
  }
  vi.stubGlobal('ResizeObserver', FakeObserver);
  return state;
}

describe('sb-time-series edge states and lifecycle (v246 §A3)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('collapses same-day points and drops a non-finite value', () => {
    const fixture = mount('area', [
      { time: '2026-10-01T09:00:00Z', value: 1 }, { time: '2026-10-01T17:00:00Z', value: 2 },
      { time: '2026-10-02', value: Number.NaN }, { time: '2026-10-03', value: 4 },
    ]);
    expect(values(fixture)).toEqual([2, 4]);
  });

  it('drops a candle with a non-finite price', () => {
    const fixture = mount('candles', [
      { time: '2026-10-01', open: 100, high: 120, low: 90, close: 110 },
      { time: '2026-10-02', open: 110, high: Number.POSITIVE_INFINITY, low: 95, close: 98 },
    ]);
    expect(inside(fixture).series!.data()).toHaveLength(1);
  });

  it('keeps an empty series for no points, and fills it when points arrive', () => {
    const fixture = mount('area', []);
    expect(inside(fixture).series!.data()).toHaveLength(0);
    set(fixture, 'points', EQUITY);
    expect(values(fixture)).toEqual([0, 120.5, -40]);
  });

  it('draws one point as a marker without a line, and the line again from two', () => {
    const fixture = mount('area', [{ time: '2026-10-01', value: 5 }]);
    const options = () => inside(fixture).series!.options() as AreaSeriesOptions;
    expect(options().lineVisible).toBe(false);
    expect(options().pointMarkersVisible).toBe(true);
    set(fixture, 'points', EQUITY);
    expect(options().lineVisible).toBe(true);
    expect(options().pointMarkersVisible).toBe(false);
  });

  it('marks a single drawdown point too', () => {
    const fixture = mount('baseline', [{ time: '2026-10-01', value: -0.4 }], 'r');
    const options = inside(fixture).series!.options() as BaselineSeriesOptions;
    expect(options.lineVisible).toBe(false);
    expect(options.pointMarkersVisible).toBe(true);
  });

  it('fits new data once the plot has a width', () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600);
    const fixture = mount('area', []);
    const fit = vi.spyOn(inside(fixture).chart!.timeScale(), 'fitContent');
    set(fixture, 'points', EQUITY);
    set(fixture, 'height', 180);
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('resizes to the host width on an observer tick, and fits once a width arrives', () => {
    const observer = fakeResizeObserver();
    let width = 0;
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const resize = vi.spyOn(chart, 'resize');
    const fit = vi.spyOn(chart.timeScale(), 'fitContent');
    width = 600;
    observer.notify();
    observer.notify();
    expect(resize).toHaveBeenLastCalledWith(600, 220);
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('repaints on a theme switch, without a reload', async () => {
    const fixture = mount('area', EQUITY);
    const names = ['--accent', '--accent-soft', '--surface', '--text-secondary'];
    const style = document.createElement('style');
    style.textContent = `:root[data-theme="navy"]{${names.map((n) => `${n}:${resolveTokenIn('navy', n)}`).join(';')}}`;
    document.head.appendChild(style);
    try {
      TestBed.inject(ThemeService).set('navy');
      fixture.detectChanges();
      await fixture.whenStable();
      const { chart, series } = inside(fixture);
      expect(resolveTokenIn('navy', '--accent')).not.toBe(resolveToken('--accent'));
      expect((series!.options() as AreaSeriesOptions).lineColor).toBe(resolveTokenIn('navy', '--accent'));
      expect((series!.options() as AreaSeriesOptions).topColor).toBe(resolveTokenIn('navy', '--accent-soft'));
      expect(chart!.options().layout.textColor).toBe(resolveTokenIn('navy', '--text-secondary'));
      expect((chart!.options().layout.background as { color: string }).color).toBe(resolveTokenIn('navy', '--surface'));
    } finally {
      style.remove();
    }
  });

  it('releases its ResizeObserver, its chart and its theme subscription on destroy', async () => {
    const observer = fakeResizeObserver();
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const remove = vi.spyOn(chart, 'remove');
    const applied = vi.spyOn(chart, 'applyOptions');
    fixture.destroy();
    expect(observer.disconnect).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);
    expect(inside(fixture).chart).toBeNull();
    TestBed.inject(ThemeService).set('navy');
    await fixture.whenStable();
    expect(applied).not.toHaveBeenCalled();
  });
});
```

`BaselineSeriesOptions` and `AreaSeriesOptions` are already imported by V246-13's spec.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts`
Expected: FAIL in the appended block only: the `NaN` row and the infinite candle reach the series (lightweight-charts may throw on them), one point keeps `lineVisible: true`, `fitContent` is never called, the observer is never created or disconnected, and the theme flip leaves the Graphite accent. V246-13's tests still pass.

- [ ] **Step 3: Implement**

All edits are in `frontend/src/app/ui/chart/time-series.ts`; everything not named here (`collapseByDay`, `rows`, `candleOptions`, `addSeries`, the decorator, the inputs, the build, data and height effects) stays as V246-13 wrote it.

(a) Below the two `lightweight-charts` imports add `import { ThemeService } from '../theme.service';`.

(b) Replace `plottable()` and its doc comment with:

```ts
/** The right shape for `kind`, every value finite; anything else is dropped, never thrown on. */
function plottable(kind: TimeSeriesKind, datum: TimeSeriesDatum): boolean {
  if (kind === 'candles') return isCandle(datum) && [datum.open, datum.high, datum.low, datum.close].every(Number.isFinite);
  return !isCandle(datum) && Number.isFinite(datum.value);
}
```

(c) Replace `areaOptions()`, `baselineOptions()` and `seriesOptions()` with:

```ts
/** One point is a marker with no line (v246 edge states); two or more draw the line. */
function areaOptions(palette: ChartPalette, single: boolean): AreaSeriesPartialOptions {
  return { lineWidth: 2, lineVisible: !single, pointMarkersVisible: single, priceLineVisible: false,
    lineColor: palette.accent, topColor: themedToken('--accent-soft'), bottomColor: 'transparent' };
}

function baselineOptions(palette: ChartPalette, single: boolean): BaselineSeriesPartialOptions {
  return { lineWidth: 2, lineVisible: !single, pointMarkersVisible: single, priceLineVisible: false,
    baseValue: { type: 'price', price: 0 },
    topLineColor: palette.down, topFillColor1: 'transparent', topFillColor2: 'transparent',
    bottomLineColor: palette.down, bottomFillColor1: palette.negSoft, bottomFillColor2: palette.negSoft };
}

function seriesOptions(kind: TimeSeriesKind, palette: ChartPalette, single: boolean): KindOptions {
  if (kind === 'area') return areaOptions(palette, single);
  if (kind === 'baseline') return baselineOptions(palette, single);
  return candleOptions(palette);
}
```

(d) After `private zeroLine: IPriceLine | null = null;` add:

```ts
  private readonly theme = inject(ThemeService);
  private resizeObserver: ResizeObserver | null = null;
  private count = 0;
  private pendingFit = false;
```

(e) Replace the style effect (the one reading `this.valueFormat()`) with:

```ts
    // ThemeService is a signal: reading it here is the subscription, destroyed with the view.
    effect(() => {
      this.theme.theme();
      this.valueFormat();
      untracked(() => this.restyle());
    });
```

(f) Replace `build()`, `render()`, `resize()` and `teardown()`, and add `observe()` after `build()`:

```ts
  private build(element: HTMLElement, kind: TimeSeriesKind): void {
    if (!this.chart) {
      this.chart = createChart(element, { width: element.clientWidth, height: this.height() });
      this.observe(element);
    }
    if (this.series) this.chart.removeSeries(this.series);
    this.series = addSeries(this.chart, kind);
    this.zeroLine = kind === 'candles' ? null : this.series.createPriceLine({
      price: 0, color: chartPalette().axis, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false, title: '',
    });
    this.count = 0;
  }

  /** jsdom has no ResizeObserver; without one the chart still sizes on data and height changes. */
  private observe(element: HTMLElement): void {
    if (typeof ResizeObserver === 'undefined') return;
    this.resizeObserver = new ResizeObserver(() => this.resize(this.height()));
    this.resizeObserver.observe(element);
  }

  private render(data: Row[]): void {
    if (!this.chart || !this.series) return;
    this.series.setData(data);
    this.count = data.length;
    this.restyle();
    this.pendingFit = true;
    this.resize(this.height());
  }

  /** Width from the plot box, height from the input; the first non-zero width after new data fits it. */
  private resize(height: number): void {
    const chart = this.chart;
    if (!chart) return;
    const width = this.plot().nativeElement.clientWidth;
    chart.resize(width, height);
    if (this.pendingFit && width > 0) {
      this.pendingFit = false;
      chart.timeScale().fitContent();
    }
  }

  /** Observer first, chart last: nothing may call into a removed chart. */
  private teardown(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.chart?.remove();
    this.chart = null;
    this.series = null;
    this.zeroLine = null;
  }
```

(g) In `restyle()`, pass the one-point flag: `seriesOptions(this.kind(), palette)` becomes `seriesOptions(this.kind(), palette, this.count === 1)`.

(h) In the class doc comment, replace "Sized from the plot box (no `autoSize`, which `applyChartTheme` leaves out), released in `teardown()`." with "Sized by its own ResizeObserver (no `autoSize`, which `applyChartTheme` leaves out), repainted on a theme switch, released in `teardown()`."

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts`
Expected: PASS, 0 failed (V246-13's tests and the appended block).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (the Gallery spec mounts both exhibits; jsdom has no `ResizeObserver`, so `observe()` returns early there).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chart/time-series.ts frontend/src/app/ui/chart/time-series.spec.ts
git commit -m "feat(v246): sb-time-series edge states and lifecycle -- non-finite drop, 1-point marker, fit on first width, ResizeObserver, theme repaint, release on destroy" -m "Spec §A3 and edge states: 0 points keep an empty series, 1 point draws a marker with no line; the chart follows ThemeService without a reload; observer, chart and theme effect are released on destroy (asserted)."
```

### Task V246-14: Linked scrolling: `TimeScaleSync` with a ping-pong guard; `sb-time-series` `sync` input released on destroy

**Model:** sonnet — one small class with a re-entrancy guard, tested on hand-rolled fake charts, plus one input and two lines of teardown on V246-13b's component; every name is fixed below.

**Files:**
- Create: `frontend/src/app/ui/chart/time-scale-sync.ts`
- Create: `frontend/src/app/ui/chart/time-scale-sync.spec.ts`
- Modify: `frontend/src/app/ui/chart/time-series.ts` (V246-13, V246-13b) — one import, the `sync` input after `label`, two fields, one effect after the build effect, `build()`, a new `link()` method, `teardown()`
- Modify: `frontend/src/app/ui/chart/time-series.spec.ts` — one import and one `describe` appended at the end

**Interfaces:**
- Consumes: `TimeSeries` as V246-13b leaves it (`chart` created once in `build()`; `teardown()` = observer, then chart); the spec helpers `inside()`, `set()`, `EQUITY`.
- Produces (exact, from the index ledger; V246-15 binds them):
  - `export class TimeScaleSync { register(chart: IChartApi): () => void }` — subscribes `chart` to the group; the returned function unsubscribes it (idempotent). Registering one chart twice keeps one subscription.
  - `TimeSeries.sync = input<TimeScaleSync | null>(null)` — the chart joins the group on creation (or when `sync` is set later), leaves the old group when `sync` changes or becomes `null`, and leaves it on destroy before the chart is removed. V246-15 creates one `new TimeScaleSync()` per Overview tab and binds it to both the equity and the drawdown chart.

**Why.** Spec §A3 "Linked scrolling": "`lightweight-charts` 5 has no shared time scale, so each chart subscribes to the other's `subscribeVisibleLogicalRangeChange`, with a guard flag against ping-pong. `sb-time-series` unsubscribes in its `DestroyRef.onDestroy`, alongside its `ResizeObserver` and its `theme.service` subscription. A spec asserts all three are released on destroy." The guard is two-fold: a `following` flag stops the synchronous echo (setting B's range makes B report the change while A's handler is still on the stack), and an equality check stops a late echo (if B reports after the stack unwinds, A already shows that range and is not set again). Logical ranges are bar indices; Overview's two charts are fed the same days (V246-15), so one logical range means the same dates on both. A `null` range (a chart with no data) moves nothing. A plain class, not an Angular service: the group is per pair of charts, never app-wide, so the consumer owns its instance. The spec drives fake charts that fire synchronously, the worst case for ping-pong; `vi.mock` is not used (part header).

- [ ] **Step 1: Write the failing `TimeScaleSync` spec**

Create `frontend/src/app/ui/chart/time-scale-sync.spec.ts`:

```ts
import type { IChartApi, LogicalRange, LogicalRangeChangeEventHandler } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';

import { TimeScaleSync } from './time-scale-sync';

const range = (from: number, to: number) => ({ from, to }) as LogicalRange;

/** A chart reduced to its time scale. Setting the range reports it at once: the worst case for ping-pong. */
function fakeChart() {
  let handlers: LogicalRangeChangeEventHandler[] = [];
  let visible: LogicalRange | null = null;
  const report = () => handlers.forEach((handler) => handler(visible));
  const scale = {
    subscribeVisibleLogicalRangeChange: (handler: LogicalRangeChangeEventHandler) => { handlers.push(handler); },
    unsubscribeVisibleLogicalRangeChange: (handler: LogicalRangeChangeEventHandler) => {
      handlers = handlers.filter((h) => h !== handler);
    },
    getVisibleLogicalRange: () => visible,
    setVisibleLogicalRange: vi.fn((next: LogicalRange) => { visible = next; report(); }),
  };
  return {
    chart: { timeScale: () => scale } as unknown as IChartApi,
    set: scale.setVisibleLogicalRange,
    /** A user gesture: the range moves and the chart reports it. */
    scroll(next: LogicalRange | null) { visible = next; report(); },
    /** The library reporting later, after the call stack has unwound. */
    quietly(next: LogicalRange) { visible = next; },
    listeners: () => handlers.length,
  };
}

describe('TimeScaleSync (v246 §A3 linked scrolling)', () => {
  it('moves every other chart to the scrolled range, once, and never back to the source', () => {
    const sync = new TimeScaleSync();
    const [a, b, c] = [fakeChart(), fakeChart(), fakeChart()];
    for (const fake of [a, b, c]) sync.register(fake.chart);
    a.scroll(range(2, 10));
    expect(b.set).toHaveBeenCalledTimes(1);
    expect(b.set).toHaveBeenCalledWith(range(2, 10));
    expect(c.set).toHaveBeenCalledTimes(1);
    expect(a.set).not.toHaveBeenCalled();
  });

  it('ignores a late echo of a range the source already shows', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.set.mockImplementation((next: LogicalRange) => b.quietly(next));
    a.scroll(range(4, 12));
    b.scroll(range(4, 12));
    expect(b.set).toHaveBeenCalledTimes(1);
    expect(a.set).not.toHaveBeenCalled();
  });

  it('follows the other way too', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.scroll(range(0, 5));
    expect(a.set).toHaveBeenCalledWith(range(0, 5));
  });

  it('moves nothing for a null range', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    a.scroll(null);
    expect(b.set).not.toHaveBeenCalled();
  });

  it('stops following once released, and a second release is harmless', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    const release = sync.register(a.chart);
    sync.register(b.chart);
    release();
    expect(a.listeners()).toBe(0);
    a.scroll(range(1, 3));
    b.scroll(range(6, 9));
    expect(b.set).not.toHaveBeenCalled();
    expect(a.set).not.toHaveBeenCalled();
    expect(() => release()).not.toThrow();
  });

  it('subscribes a chart once however often it is registered', () => {
    const sync = new TimeScaleSync();
    const a = fakeChart();
    const first = sync.register(a.chart);
    const second = sync.register(a.chart);
    expect(a.listeners()).toBe(1);
    second();
    expect(a.listeners()).toBe(0);
    expect(() => first()).not.toThrow();
  });

  it('drops its guard again when a follower throws', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.set.mockImplementationOnce(() => { throw new Error('disposed'); });
    expect(() => a.scroll(range(1, 2))).toThrow('disposed');
    a.scroll(range(3, 4));
    expect(b.set).toHaveBeenLastCalledWith(range(3, 4));
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-scale-sync.spec.ts`
Expected: FAIL to compile: cannot find module `./time-scale-sync`.

- [ ] **Step 3: Write `TimeScaleSync`**

Create `frontend/src/app/ui/chart/time-scale-sync.ts`:

```ts
import type { IChartApi, LogicalRange, LogicalRangeChangeEventHandler } from 'lightweight-charts';

/** Logical ranges are fractional bar indices; closer than this is the same view. */
const SAME_RANGE_EPSILON = 1e-6;

function sameRange(a: LogicalRange | null, b: LogicalRange): boolean {
  return a !== null && Math.abs(a.from - b.from) < SAME_RANGE_EPSILON && Math.abs(a.to - b.to) < SAME_RANGE_EPSILON;
}

/**
 * v246 §A3 "Linked scrolling". lightweight-charts 5 has no shared time
 * scale, so every registered chart follows the others' visible logical
 * range. Two guards keep it from ping-ponging: `following` swallows the
 * echo a follower reports while the source's handler is still running, and
 * `sameRange` swallows an echo that arrives later, when the source already
 * shows that range. Charts in one group must share their bars (the same
 * days), or one logical range means different dates on each.
 */
export class TimeScaleSync {
  private readonly handlers = new Map<IChartApi, LogicalRangeChangeEventHandler>();
  private following = false;

  /** Joins `chart` to the group; the returned function leaves it (safe to call twice). */
  register(chart: IChartApi): () => void {
    if (!this.handlers.has(chart)) {
      const handler: LogicalRangeChangeEventHandler = (range) => this.follow(chart, range);
      this.handlers.set(chart, handler);
      chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    }
    return () => this.release(chart);
  }

  private release(chart: IChartApi): void {
    const handler = this.handlers.get(chart);
    if (!handler) return;
    this.handlers.delete(chart);
    chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
  }

  private follow(source: IChartApi, range: LogicalRange | null): void {
    if (this.following || range === null) return;
    this.following = true;
    try {
      for (const chart of this.handlers.keys()) {
        if (chart !== source && !sameRange(chart.timeScale().getVisibleLogicalRange(), range)) {
          chart.timeScale().setVisibleLogicalRange(range);
        }
      }
    } finally {
      this.following = false;
    }
  }
}
```

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-scale-sync.spec.ts`
Expected: PASS, 0 failed.

- [ ] **Step 4: Write the failing `sync` input tests**

In `frontend/src/app/ui/chart/time-series.spec.ts`, add below the `./time-series` import:

```ts
import { TimeScaleSync } from './time-scale-sync';
```

Append at the end of the file:

```ts
describe('sb-time-series linked scrolling (v246 §A3)', () => {
  function spiedSync() {
    const sync = new TimeScaleSync();
    const release = vi.fn();
    const register = vi.spyOn(sync, 'register').mockReturnValue(release);
    return { sync, register, release };
  }

  /** `sync` set before the first change detection, the way a template binds it. */
  function mountSynced(sync: TimeScaleSync) {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(),
        { provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }],
    });
    const fixture = TestBed.createComponent(TimeSeries);
    fixture.componentRef.setInput('kind', 'area');
    fixture.componentRef.setInput('points', EQUITY);
    fixture.componentRef.setInput('label', 'Equity curve');
    fixture.componentRef.setInput('sync', sync);
    fixture.detectChanges();
    return fixture;
  }

  it('registers its chart once with the sync it is given', () => {
    const { sync, register } = spiedSync();
    const fixture = mountSynced(sync);
    expect(register).toHaveBeenCalledTimes(1);
    expect(register).toHaveBeenCalledWith(inside(fixture).chart);
  });

  it('keeps its registration across a kind change: the chart is the same', () => {
    const { sync, register, release } = spiedSync();
    const fixture = mountSynced(sync);
    set(fixture, 'kind', 'baseline');
    expect(register).toHaveBeenCalledTimes(1);
    expect(release).not.toHaveBeenCalled();
  });

  it('leaves the old sync for a new one, and any sync for null', () => {
    const first = spiedSync();
    const second = spiedSync();
    const fixture = mountSynced(first.sync);
    set(fixture, 'sync', second.sync);
    expect(first.release).toHaveBeenCalledTimes(1);
    expect(second.register).toHaveBeenCalledWith(inside(fixture).chart);
    set(fixture, 'sync', null);
    expect(second.release).toHaveBeenCalledTimes(1);
  });

  it('joins a sync set after it was created', () => {
    const { sync, register } = spiedSync();
    const fixture = mount('area', EQUITY);
    expect(register).not.toHaveBeenCalled();
    set(fixture, 'sync', sync);
    expect(register).toHaveBeenCalledWith(inside(fixture).chart);
  });

  it('releases its sync on destroy, before the chart is removed', () => {
    const { sync, release } = spiedSync();
    const fixture = mountSynced(sync);
    const chart = inside(fixture).chart!;
    const order: string[] = [];
    const remove = chart.remove.bind(chart);
    release.mockImplementation(() => order.push('sync'));
    vi.spyOn(chart, 'remove').mockImplementation(() => { order.push('chart'); remove(); });
    fixture.destroy();
    expect(order).toEqual(['sync', 'chart']);
  });
});
```

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts`
Expected: FAIL: `setInput('sync', …)` throws `NG0303`-style "Input sync does not exist" (or the test fails at `register` never being called); the earlier blocks pass.

- [ ] **Step 5: Add the `sync` input to `sb-time-series`**

In `frontend/src/app/ui/chart/time-series.ts`:

Add below `import { ThemeService } from '../theme.service';`:

```ts
import { TimeScaleSync } from './time-scale-sync';
```

(keep it after the `./chart-theme` import if the linter orders imports alphabetically: `./chart-theme` < `./time-scale-sync`.)

After `readonly label = input.required<string>();` add:

```ts
  /** v246 §A3: charts bound to one TimeScaleSync scroll together (Overview's equity and drawdown). */
  readonly sync = input<TimeScaleSync | null>(null);
```

After `private pendingFit = false;` add:

```ts
  private linked: TimeScaleSync | null = null;
  private releaseSync: (() => void) | null = null;
```

In the constructor, directly after the first (build) effect, add:

```ts
    effect(() => {
      const sync = this.sync();
      untracked(() => this.link(sync));
    });
```

In `build()`, after `this.observe(element);` add `this.link(this.sync());` (a sync bound before the first render joins as soon as the chart exists, whatever order the effects run in):

```ts
    if (!this.chart) {
      this.chart = createChart(element, { width: element.clientWidth, height: this.height() });
      this.observe(element);
      this.link(this.sync());
    }
```

Add the method after `observe()`:

```ts
  /** Joins `sync`, leaving the previous group first; a no-op when nothing changed or before the chart exists. */
  private link(sync: TimeScaleSync | null): void {
    if (!this.chart || sync === this.linked) return;
    this.releaseSync?.();
    this.linked = sync;
    this.releaseSync = sync ? sync.register(this.chart) : null;
  }
```

Replace `teardown()` with:

```ts
  /** Observer, then the sync group, then the chart: nothing may call into a removed chart. */
  private teardown(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.releaseSync?.();
    this.releaseSync = null;
    this.linked = null;
    this.chart?.remove();
    this.chart = null;
    this.series = null;
    this.zeroLine = null;
  }
```

- [ ] **Step 6: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/chart/time-series.spec.ts --include src/app/ui/chart/time-scale-sync.spec.ts`
Expected: PASS, 0 failed.

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (the Gallery mounts `sb-time-series` without `sync`; the default `null` links nothing).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/ui/chart/time-scale-sync.ts frontend/src/app/ui/chart/time-scale-sync.spec.ts frontend/src/app/ui/chart/time-series.ts frontend/src/app/ui/chart/time-series.spec.ts
git commit -m "feat(v246): linked scrolling -- TimeScaleSync with a ping-pong guard; sb-time-series sync input, released on destroy" -m "Spec §A3: each chart in a group follows the others' visible logical range; a re-entrancy flag stops the synchronous echo and a same-range check the late one. sb-time-series joins on creation, swaps groups on input change and leaves before its chart is removed (asserted)."
```
