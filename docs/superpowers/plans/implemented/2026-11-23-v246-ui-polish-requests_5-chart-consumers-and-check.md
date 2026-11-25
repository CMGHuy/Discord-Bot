# v246 — UI polish, Plan A of five: requests — Part 5: chart consumers and the closing check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-16" -A 400 <this file>`).

**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) §A3 ("The Analytics Overview equity and drawdown move onto it", "Dashboard equity", "SVG charts") and the A rows of "Error, empty and edge states", "Three devices" and "Testing".
**Index:** [2026-11-23-v246-ui-polish-requests_0-index.md](2026-11-23-v246-ui-polish-requests_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` decisions live there; every task below implicitly includes them.

Tasks: V246-15 (Analytics Overview equity and drawdown on `sb-time-series`, linked, drawdown header), V246-16 (Dashboard equity candles on the shared theme, axis defects), V246-17 (the six SVG charts read `SVG_CHART_TOKENS`), V246-18 (the closing Playwright check and layout audit).

Order: V246-15 needs V246-2 (same file) and V246-14 (`TimeScaleSync`, `sync` input); V246-16 needs V246-10 (same file) and V246-12; V246-17 needs V246-12; V246-18 runs last, after every other v246 task is merged into the worktree. All frontend commands run from the worktree root with `cd frontend &&`; `--include` paths are relative to `frontend/`.

Facts these tasks rely on (verified on main 2026-11-25, not restated in code):

- Part 4 produces, in `ui/chart/chart-theme.ts`: `priceFormat`, `rFormat`, `pctFormat` (`PriceFormatCustom`), `applyChartTheme(chart, palette = chartPalette())` (applies `chartOptions(palette)` **without** `autoSize`, `layout.textColor` = `--text-secondary`, and `timeScale.timeVisible: false`), `themedToken(name)`, and `SVG_CHART_TOKENS = { line: '--accent', pos: '--pos', neg: '--neg', grid: CHART_CHROME.grid /* --border */, axisText: '--text-secondary', crosshair: '--text-muted', strokeWidth: 2, strokeWidthThin: 1, barRadius: '--radius-sm', barGap: 2, labelSize: CHART_CHROME.tickSize /* --text-micro */ } as const`. In `ui/chart/time-series.ts`: `TimeSeries` (`sb-time-series`, inputs `kind`, `points`, `valueFormat`, `height`, `label`, `sync`), `TimeSeriesPoint { time: string; value: number }`; it collapses same-day points itself (last wins), drops non-finite values, draws one point as a marker, and keeps an empty series for 0 points (the consumer shows its own empty state). In `ui/chart/time-scale-sync.ts`: `TimeScaleSync { register(chart): () => void }`.
- `lightweight-charts` runs for real under jsdom once `installMatchMediaPolyfill()` (`src/app/testing/match-media-polyfill.ts`) has run; jsdom has no `ResizeObserver`, and `TimeSeries` and `EquityCandles` both skip it when absent. No spec in the repo uses `vi.mock`.
- `ui/format.ts`: `money(value, unit, decimals = 2)` returns `ABSENT` (`—`) for `null`/`undefined` and signs a loss with U+2212; `num`, `rMultiple`, `pct`, `fixed` as in part 4.
- `ViewportService` (`ui/breakpoints.ts`) exposes `isPhone: Signal<boolean>` (below 640px); `phoneViewport()` in `ui/data-table/testing/reachability.ts` provides a phone stand-in for specs (jsdom matches no media query).
- The colour gate (`ui/primitives.spec.ts`) forbids hex and `rgb()`/`hsl()` literals in non-spec `.ts` source.
- `workspaces/gallery/gallery.spec.ts` fails for any `ui/` `sb-` selector the Gallery does not render. This part adds **no** `ui/` selector, so the Gallery is untouched.
- `frontend/scripts/*.test.mjs` run under pytest through `tests/scripts/test_node_scripts.py` (auto-discovered, `node --test`), so a new `*-lib.test.mjs` joins CI without any suite edit.

---

# Phase 9 — Chart consumers

### Task V246-15: Analytics Overview equity (area) and drawdown (baseline) on `sb-time-series`, linked; drawdown header shows max drawdown € and longest losing streak

**Model:** sonnet — one consumer swapping two chart elements and adding two computed texts, with every input, value and assertion fixed below; the chart component itself is done.

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.ts` — imports (lines 1-26), `imports: [...]` (lines 126-130), the Equity panel's `@else` branch (lines 163-167), styles (`.pane-label`, line 220), `format` (lines 241-242), `equityHint` (lines 248-250), `equitySeries` / `drawdownSeries` (lines 275-286), the drawdown money in `kpiTiles` (line 339). Line numbers are main's on 2026-11-25; V246-2 (`rBins`, `rColumns`) and v247 edit the same file first, so find each block by the name quoted.
- Modify: `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts` — the import block (lines 1-20), `draws equity and drawdown as two panes, not a toggle` (lines 148-153), the Equity hint test (line 242), one `describe` appended at the end of the file.

**Interfaces:**
- Consumes: `TimeSeries`, `TimeSeriesFormat`, `TimeSeriesPoint` (`ui/chart/time-series`, V246-13/13b/14); `TimeScaleSync` (`ui/chart/time-scale-sync`, V246-14); `maxDrawdown(values)` (this file, unchanged); `performance.streaks.worst_loss_streak` (`api/models.ts`, unchanged); `money`, `ABSENT` (`ui/format`); `AnalyticsUnit` (`api/models.ts:690`).
- Produces: `export const DRAWDOWN_CHART_LABEL = 'Drawdown below the running high, in R'` (this file; read only by its spec). V246-18 looks for two `sb-time-series` inside the Overview Equity panel.

**Why.** Spec §A3: "The Analytics Overview equity and drawdown move onto it and keep their N and total labels in the card header. The drawdown header adds the money units a retail trader feels: max drawdown in € and the longest losing streak … Neither is a new calculation." Handoff 6 names the sources: `maxDrawdown()` over `cum_pnl` (already behind the Max drawdown tile's money line, so this task hoists it into one `computed` both read) and `streaks.worst_loss_streak` (already in the payload, shown today in the Outcome panel's Streaks row). "Linked scrolling": one `TimeScaleSync` per tab instance, bound to both charts. Equity is an `area` in the scope bar's unit, its axis format following the unit (`r` → `'r'`, `pct` → `'pct'`, `money` → `'price'`; the card header already carries the currency). Drawdown is a `baseline` at 0 fed `-drawdown_r`: that series is R in the payload whatever the unit, so its axis always reads R — today's `sb-line-chart` ran it through the unit formatter and printed an R value as `€` in money mode; this task fixes that by construction. A zero drawdown is written `0`, never `-0` (a `-0` prints a stray minus). Heights: 200px for equity, 120px for drawdown (the old SVG panes were 140px each; the drawdown is the secondary pane). Both inputs come from the same `points()`, so both charts hold the same days and one logical range means the same dates on both (V246-14's premise). The equity hint changes because its old sentence ("the x-axis is the sequence of trades, dated") is no longer true: `sb-time-series` draws one point per closing day (the day's last value, `collapseByDay`) on a time axis. Its asserted phrase "per closed trade, ordered by close date" stays. With 0 points the panel keeps its own `sb-empty-state` (spec edge states); 1 point is `sb-time-series`'s marker. `format` (the unit formatter the two line charts used) has no reader left and is deleted.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`:

(a) Add to the import block, below `import { MarketMeta } from '../../../api/models';`:

```ts
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { TimeScaleSync } from '../../../ui/chart/time-scale-sync';
import { TimeSeries } from '../../../ui/chart/time-series';
import { money } from '../../../ui/format';
```

and `DRAWDOWN_CHART_LABEL` to the existing `./overview` import. Directly after the last import line add:

```ts
// sb-time-series creates a real lightweight-charts chart; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();
```

(b) Replace the test `draws equity and drawdown as two panes, not a toggle` with:

```ts
  it('draws equity and drawdown as two panes, not a toggle', () => {
    const { el } = render();
    expect(el.querySelectorAll('sb-time-series')).toHaveLength(2);
    expect(el.textContent).toContain('Drawdown');
    expect(el.querySelector('sb-segmented[aria-label="Equity view"]')).toBeNull();
  });
```

(c) In `Equity and R distribution hints state the paper, gross, pre-tax basis`, below `expect(hintText(fixture, 'Equity definition')).toContain('per closed trade, ordered by close date');` add:

```ts
    expect(hintText(fixture, 'Equity definition')).toContain("one point per closing day, at the day's last close");
    expect(hintText(fixture, 'Equity definition')).not.toContain('the x-axis is the sequence of trades');
```

(d) Append at the end of the file:

```ts
/** The tab's sb-time-series instances in template order: equity, then drawdown. */
function timeSeries(fixture: ComponentFixture<unknown>): TimeSeries[] {
  return fixture.debugElement.queryAll(By.directive(TimeSeries)).map((debug) => debug.componentInstance as TimeSeries);
}

/** The drawdown pane's header facts, whitespace collapsed. */
function paneFacts(el: HTMLElement): string {
  return el.querySelector('.pane-facts')?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('OverviewTab equity and drawdown on sb-time-series (v246 §A3)', () => {
  beforeEach(() => TestBed.resetTestingModule());

  it('draws equity as an area and drawdown as a baseline, never the SVG line chart', () => {
    const { fixture, el } = render();
    const charts = timeSeries(fixture);
    expect(charts.map((chart) => chart.kind())).toEqual(['area', 'baseline']);
    expect(charts.map((chart) => chart.height())).toEqual([200, 120]);
    expect(el.querySelector('sb-line-chart')).toBeNull();
  });

  it('feeds equity in the selected unit and formats its axis to match', () => {
    const cases = [
      { unit: 'r', values: [1, 0.5], format: 'r' },
      { unit: 'pct', values: [0.7, 0.4], format: 'pct' },
      { unit: 'money', values: [70, 40], format: 'price' },
    ] as const;
    for (const { unit, values, format } of cases) {
      TestBed.resetTestingModule();
      const [equity] = timeSeries(render({ unit: signal(unit) }).fixture);
      expect(equity.points(), unit).toEqual([
        { time: '2026-08-01', value: values[0] }, { time: '2026-08-02', value: values[1] },
      ]);
      expect(equity.valueFormat(), unit).toBe(format);
    }
  });

  it('draws drawdown below zero in R whatever the unit, with a plain zero', () => {
    for (const unit of ['r', 'pct', 'money']) {
      TestBed.resetTestingModule();
      const [, drawdown] = timeSeries(render({ unit: signal(unit) }).fixture);
      const values = drawdown.points().map((point) => point.value);
      expect(values, unit).toEqual([0, -0.5]);
      expect(Object.is(values[0], -0), unit).toBe(false);
      expect(drawdown.valueFormat(), unit).toBe('r');
    }
  });

  it('links the two charts through one TimeScaleSync', () => {
    const [equity, drawdown] = timeSeries(render().fixture);
    expect(equity.sync()).toBeInstanceOf(TimeScaleSync);
    expect(drawdown.sync()).toBe(equity.sync());
  });

  it('names each canvas for assistive technology, in the selected unit', () => {
    const [equity, drawdown] = timeSeries(render({ unit: signal('money') }).fixture);
    expect(equity.label()).toBe('Equity curve, cumulative $ per closed trade');
    expect(drawdown.label()).toBe(DRAWDOWN_CHART_LABEL);
  });

  it('heads the drawdown pane with max drawdown in money and the longest losing streak', () => {
    const performance = storeStub().performance();
    const { el } = render({ performance: signal({
      ...performance,
      streaks: { current: 1, current_kind: 'loss', best_win_streak: 3, worst_loss_streak: 4 },
    }) });
    // cum_pnl 70 -> 40: the largest fall is 30, shown as a loss.
    expect(paneFacts(el)).toBe(`Max drawdown ${money(-30, '$')} · Longest losing streak 4`);
  });

  it('shows a dash for a streak the payload does not carry, and a plain zero drawdown', () => {
    const { el } = render({ equityCurve: signal({
      points: [{ date: '2026-08-01', cum_r: 1, drawdown_r: 0, cum_pnl: 70, cum_pct: 0.7 },
               { date: '2026-08-02', cum_r: 2, drawdown_r: 0, cum_pnl: 90, cum_pct: 0.9 }],
      points_n: 2, as_of: '2026-08-02', scope: {}, n: 2,
    }) });
    expect(paneFacts(el)).toBe(`Max drawdown ${money(0, '$')} · Longest losing streak —`);
    expect(paneFacts(el)).not.toContain('−');
  });

  it('keeps the empty state and draws no chart when the scope has no closed trades', () => {
    const { fixture, el } = render({ equityCurve: signal({ points: [], points_n: 0, as_of: null, scope: {}, n: 0 }) });
    expect(timeSeries(fixture)).toHaveLength(0);
    expect(el.textContent).toContain('No closed trades in this scope');
    expect(el.querySelector('.pane-facts')).toBeNull();
  });
});
```

The existing test `keeps the money equivalent under the max drawdown tile` keeps guarding the tile's money line now that it reads the hoisted `maxDrawdownMoney`.

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: FAIL — the build reports `DRAWDOWN_CHART_LABEL` is not exported; once that is stubbed, no `sb-time-series` is rendered (0 of 2), `.pane-facts` is empty and the hint lacks "one point per closing day".

- [ ] **Step 3: Implement**

In `frontend/src/app/workspaces/analytics/tabs/overview.ts`:

(a) Imports. Replace `import { AnalyticsPerformance, HistogramBucket } from '../../../api/models';` with:

```ts
import { AnalyticsPerformance, AnalyticsUnit, HistogramBucket } from '../../../api/models';
```

Delete `import { LineChart, LineChartSeries } from '../../../ui/line-chart';` and add below `import { BarList } from '../../../ui/bar-list';`:

```ts
import { TimeScaleSync } from '../../../ui/chart/time-scale-sync';
import { TimeSeries, TimeSeriesFormat, TimeSeriesPoint } from '../../../ui/chart/time-series';
```

(b) Below `function maxDrawdown(...) { ... }` add:

```ts
/** v246 §A3: the equity axis reads in the unit the scope bar selects. */
const EQUITY_FORMAT: Record<AnalyticsUnit, TimeSeriesFormat> = { r: 'r', pct: 'pct', money: 'price' };

/** The drawdown canvas's name: its values are R whatever the unit toggle says. */
export const DRAWDOWN_CHART_LABEL = 'Drawdown below the running high, in R';
```

(c) In the component's `imports: [...]`, replace `LineChart` with `TimeSeries`.

(d) In the template's Equity panel, replace the body of the final `@else` branch

```html
          <sb-line-chart [series]="equitySeries()" [referenceLine]="0" [valueFormat]="format" />
          <h4 class="pane-label">Drawdown</h4>
          <sb-line-chart [series]="drawdownSeries()" [valueFormat]="format" />

```

with:

```html
          <sb-time-series kind="area" [points]="equityPoints()" [valueFormat]="equityFormat()" [height]="200"
            [label]="equityLabel()" [sync]="timeSync" />
          <div class="pane-head">
            <h4 class="pane-label">Drawdown</h4>
            <p class="pane-facts">
              <span>Max drawdown <span class="num">{{ maxDrawdownText() }}</span></span>
              <span class="sep" aria-hidden="true"> · </span>
              <span>Longest losing streak <span class="num">{{ lossStreakText() }}</span></span>
            </p>
          </div>
          <sb-time-series kind="baseline" [points]="drawdownPoints()" valueFormat="r" [height]="120"
            [label]="drawdownLabel" [sync]="timeSync" />
```

(e) In `styles`, replace the `.pane-label` rule with:

```css
    /* v246 §A3: the drawdown pane's own header -- its title, then the money
       units a retail trader feels. The facts wrap under the title on a narrow card. */
    .pane-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-4) var(--space-10); margin: var(--space-10) 0 var(--space-4); min-width: 0; }
    .pane-label { font-size: var(--text-chip); color: var(--text-secondary); margin: 0; }
    .pane-facts { margin: 0; font-size: var(--text-chip); color: var(--text-muted); min-width: 0; }
    .pane-facts .num { color: var(--text); font-variant-numeric: tabular-nums; white-space: nowrap; }
```

(f) Delete `readonly format = (value: number) => inUnit({ r: value, pct: value, money: value }, this.store.unit(), this.connection.currency());` (two lines; the template no longer reads it, and nothing else does: `git grep -n "\.format\b" -- frontend/src/app/workspaces/analytics/tabs/` is empty). `inUnit` stays imported — `kpiTiles` uses it.

(g) Replace `equityHint` with:

```ts
  protected readonly equityHint = computed(() =>
    `Cumulative ${this.unitLabelText()} per closed trade, ordered by close date: one point per closing day, `
    + `at the day's last close. A day with no closes is not a flat day: the axis steps from one closing day `
    + `to the next. ${PERFORMANCE_CAVEAT}`);
```

(h) Replace `equitySeries` and `drawdownSeries` (and the blank lines after them) with:

```ts
  /** One linked pair per tab: scrolling either chart moves the other (V246-14). */
  protected readonly timeSync = new TimeScaleSync();
  protected readonly drawdownLabel = DRAWDOWN_CHART_LABEL;

  readonly equityPoints = computed<TimeSeriesPoint[]>(() => {
    const unit = this.store.unit();
    return this.points().map((p) => ({
      time: p.date,
      value: unit === 'money' ? p.cum_pnl : unit === 'pct' ? (p.cum_pct ?? 0) : p.cum_r,
    }));
  });
  readonly equityFormat = computed<TimeSeriesFormat>(() => EQUITY_FORMAT[this.store.unit()]);
  protected readonly equityLabel = computed(() => `Equity curve, cumulative ${this.unitLabelText()} per closed trade`);

  /** Below the running high, so never positive; a zero stays `0`, not `-0`. */
  readonly drawdownPoints = computed<TimeSeriesPoint[]>(() =>
    this.points().map((p) => ({ time: p.date, value: p.drawdown_r === 0 ? 0 : -p.drawdown_r })));

  /** Largest fall of cumulative realised P&L in the scope: the Max drawdown
   *  tile's money line and the drawdown pane's header read this one figure. */
  private readonly maxDrawdownMoney = computed(() => {
    const points = this.points();
    return points.length ? maxDrawdown(points.map((p) => p.cum_pnl)) : null;
  });
  protected readonly maxDrawdownText = computed(() => {
    const worst = this.maxDrawdownMoney();
    return money(worst === null ? null : worst === 0 ? 0 : -worst, this.connection.currency());
  });
  protected readonly lossStreakText = computed(() => {
    const streak = this.store.performance()?.streaks?.worst_loss_streak;
    return typeof streak === 'number' ? String(streak) : ABSENT;
  });
```

(i) In `kpiTiles`, replace

```ts
    const drawdownMoney = points.length ? maxDrawdown(points.map((p) => p.cum_pnl)) : null;
```

with

```ts
    const drawdownMoney = this.maxDrawdownMoney();
```

- [ ] **Step 4: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/analytics/tabs/overview.spec.ts`
Expected: PASS, 0 failed (the new `describe`, the replaced pane test, the hint test, and every earlier test).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (`ui/line-chart.ts` keeps its other consumers: Benchmark, Edge, Partials, small multiples, Gallery).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/analytics/tabs/overview.ts frontend/src/app/workspaces/analytics/tabs/overview.spec.ts
git commit -m "feat(v246): Analytics Overview equity and drawdown on sb-time-series, linked; drawdown header shows max drawdown and longest losing streak" -m "Spec §A3: equity is an accent area in the selected unit, drawdown a baseline below zero always in R, scrolling together through one TimeScaleSync. The pane header reads maxDrawdown() over cum_pnl and streaks.worst_loss_streak (no new calculation); the equity hint now describes the one-point-per-day time axis."
```

### Task V246-16: Dashboard equity candles: `applyChartTheme`, `priceFormat`, last-value tag clear of axis labels at 390, whole hour/day ticks

**Model:** opus — a 687-line chart component whose theme, gesture and time-axis contracts (brief Trap 5) must all survive a change to how the chart is created, themed and sized.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts` — the `lightweight-charts` and `chart-theme` imports (lines 15-22, 31), one import (`ViewportService`), `timeScaleOptions()` (lines 66-69), two new exports after it, one field beside `private readonly theme` (line 342), one effect in the constructor after the restyle effect (~line 428), `create()` (lines 606-633), `restyle()` (lines 636-643). V246-10 edits this file's template and styles first; find each block by the name quoted.
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` — imports (lines 1-15), `render()` (lines 36-48), the `follows the theme (v225)` block's `NAVY_CSS` and first test (lines 863, 893-895), one `describe` appended at the end.
- Not here: the stray `)` and the primitive it may live in — V246-16b (split from this task at the 20 KB cap; the controller adds its ledger row directly below V246-16).

**Interfaces:**
- Consumes (V246-12, `ui/chart/chart-theme`): `applyChartTheme(chart, palette)`, `priceFormat`, `chartPalette()`; `ViewportService.isPhone` (`ui/breakpoints.ts`).
- Produces (this file; read by its spec and by V246-16b): `export const CANDLE_SCALE_MARGINS = { top: 0.12, bottom: 0.12 } as const`; `export function wholeTickLabel(time: Time, type: TickMarkType): string | null`.

**Why.** Spec §A3 "Dashboard equity": "calls `applyChartTheme` and uses `priceFormat`. Its last-value tag shifts so it never sits on top of an axis label (`lastValueVisible` with `priceScale.scaleMargins`, or the tag moved into the header next to the balance on narrow widths; the plan picks after measuring at 390). The stray `)` tick goes. The time axis shows only whole hours or days."

- *Theme and format.* `create()` builds the chart with `{ autoSize: true }` only (this chart sizes itself; `applyChartTheme` leaves `autoSize` out on purpose) and then calls `applyChartTheme`; `restyle()` calls it on a theme flip. Both re-apply `timeScaleOptions(data)` afterwards, because `applyChartTheme` resets `timeVisible` like `chartOptions()` does (brief Trap 5, Global Constraints). The axis text moves from `--text-muted` to `--text-secondary` with the shared theme, which is why the v225 theme test's expected `textColor` changes. `priceFormat` replaces `{ type: 'price', precision: 2 }`: `997800.00` becomes `997,800.00`, a loss reads with U+2212.
- *Last-value tag: the pick.* At 390 the chart is 160px tall with three or four price labels, so any tag lands on one of them; scale margins alone cannot clear it at that height. The account balance is already printed large directly above the chart (`sb-portfolio-value`'s `.figure`), so below 640px the tag is turned off (`lastValueVisible: false`) — the spec's "tag moved into the header next to the balance", where the balance *is* the tag's value. From 640px up the tag stays, with `scaleMargins` 12% top and bottom so the newest candle's tag is never pushed onto the top or bottom tick label. `ViewportService.isPhone` is a signal, so crossing 640px (rotation, a resized window) re-applies it without a reload.
- *Whole hours or days.* Intraday times are Berlin wall time read as UTC (`toChartTime`), so a tick's UTC minutes are its wall minutes. `wholeTickLabel` labels a time tick only on a whole hour (`15:00`) and blanks any other (a US-session candle at `15:30` is never an axis label); day, month and year ticks keep the library's labels (`null`). The fall-back hour's repeat sits one second later (`toSeriesData`) and still reads as its whole hour. The formatter rides in `timeScaleOptions()`, so every path that re-applies the time scale keeps it.
- *The `)`.* No code path in this component prints one (brief §0.8), so it is found in Chromium first: that is V246-16b, which runs after this task because a blanked `:30` tick label (above) may be its source.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`:

(a) Imports: change `import { provideZonelessChangeDetection } from '@angular/core';` to `import { Provider, provideZonelessChangeDetection, signal } from '@angular/core';`, and add:

```ts
import { TickMarkType } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';

import { ViewportService } from '../../../ui/breakpoints';
import { resolveTokenIn } from '../../../ui/testing/theme-tokens';
```

and `CANDLE_SCALE_MARGINS`, `wholeTickLabel` to the `./equity-candles` import.

(b) `render()` takes extra providers. Change its signature and providers line to:

```ts
function render(data: EquityCandlesResponse | null, error: string | null = null, extra: Provider[] = []) {
  const stub = equityCandlesStoreStub(data);
  stub.error.set(error);
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: EquityCandlesStore, useValue: stub },
      // Start in Black: Navy is the default since v240, and these specs flip to Navy.
      { provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }, ...extra],
  });
```

(the rest of `render()` is unchanged).

(c) In `follows the theme (v225)`, replace the `NAVY_CSS` line with:

```ts
    // v246: the shared theme writes axis text in --text-secondary, so Navy layers that ink too.
    const NAVY_TEXT_SECONDARY = resolveTokenIn('navy', '--text-secondary');
    const NAVY_CSS = ':root[data-theme="navy"]{--surface:#0c1424;--text-muted:#9fb0c8;--text-faint:#5f6f8a;'
      + `--text-secondary:${NAVY_TEXT_SECONDARY}}`;
```

and in `re-applies the chart ground and the candle colours, and keeps the intraday time axis`, change `textColor: '#9fb0c8'` to `textColor: NAVY_TEXT_SECONDARY`.

(d) Append at the end of the file:

```ts
describe('sb-equity-candles on the shared chart theme (v246 §A3)', () => {
  type Internals = { chart: IChartApi; series: ISeriesApi<'Candlestick'> };
  const inner = (fixture: { componentInstance: EquityCandles }) => fixture.componentInstance as unknown as Internals;
  const at = (iso: string) => (Date.parse(iso) / 1000) as Time;

  /** A ViewportService stand-in whose phone flag the test moves. */
  function viewport(phone: boolean) {
    const isPhone = signal(phone);
    return { isPhone, provider: { provide: ViewportService, useValue: {
      isPhone, isNarrow: signal(phone), viewport: signal(phone ? 'xs' : 'lg'),
    } } };
  }

  beforeEach(() => TestBed.resetTestingModule());

  it('groups thousands on the price axis and signs a loss with the true minus', () => {
    const { fixture } = render(response(MIXED));
    const formatter = inner(fixture).series.priceFormatter();
    expect(formatter.format(997800)).toBe('997,800.00');
    expect(formatter.format(-1234.5)).toBe('−1,234.50');
  });

  it('takes the shared theme and still sizes itself', () => {
    const { fixture } = render(response(MIXED));
    const options = inner(fixture).chart.options();
    expect(options.layout.textColor).toBe(token('--text-secondary'));
    expect(options.autoSize).toBe(true);
    expect(options.layout.attributionLogo).toBe(false);
  });

  it('keeps the last-value tag from 640px up, with room above and below the candles', () => {
    const { fixture } = render(response(MIXED), null, [viewport(false).provider]);
    expect(inner(fixture).series.options().lastValueVisible).toBe(true);
    expect(inner(fixture).series.priceScale().options().scaleMargins).toEqual(CANDLE_SCALE_MARGINS);
  });

  it('drops the tag on a phone, where the balance above the chart states it, and follows a crossing', () => {
    const phone = viewport(true);
    const { fixture } = render(response(MIXED), null, [phone.provider]);
    expect(inner(fixture).series.options().lastValueVisible).toBe(false);
    phone.isPhone.set(false);
    fixture.detectChanges();
    expect(inner(fixture).series.options().lastValueVisible).toBe(true);
  });

  it('labels intraday ticks on whole hours only and leaves day ticks to the library', () => {
    expect(wholeTickLabel(at('2026-10-01T15:00:00Z'), TickMarkType.Time)).toBe('15:00');
    expect(wholeTickLabel(at('2026-10-01T09:00:00Z'), TickMarkType.Time)).toBe('09:00');
    expect(wholeTickLabel(at('2026-10-01T15:30:00Z'), TickMarkType.Time)).toBe('');
    // The repeated fall-back hour sits one second later and is still its whole hour.
    expect(wholeTickLabel(at('2026-10-25T01:00:01Z'), TickMarkType.TimeWithSeconds)).toBe('01:00');
    expect(wholeTickLabel(at('2026-10-01T00:00:00Z'), TickMarkType.DayOfMonth)).toBeNull();
    expect(wholeTickLabel('2026-10-01' as Time, TickMarkType.Time)).toBeNull();
  });

  it('keeps the whole-hour formatter and the intraday axis through a theme flip', async () => {
    const { fixture } = render(response(hourlyCandles(30), { tf: '1H' }));
    const chart = inner(fixture).chart;
    expect(chart.options().timeScale.tickMarkFormatter).toBe(wholeTickLabel);
    TestBed.inject(ThemeService).set('navy');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(chart.options().timeScale.tickMarkFormatter).toBe(wholeTickLabel);
    expect(chart.options().timeScale.timeVisible).toBe(true);
  });
});
```

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: FAIL — the build reports `CANDLE_SCALE_MARGINS` and `wholeTickLabel` are not exported; with those stubbed, the formatter prints `997800.00`, `textColor` is `--text-muted`, the phone keeps its tag, and the v225 test sees the old `textColor`.

- [ ] **Step 2: Implement the theme, the format, the tag and the ticks**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`:

(a) Imports: add `TickMarkType` to the `lightweight-charts` import; replace `import { ChartPalette, chartOptions, chartPalette, token } from '../../../ui/chart/chart-theme';` with

```ts
import { ChartPalette, applyChartTheme, chartPalette, priceFormat, token } from '../../../ui/chart/chart-theme';
import { ViewportService } from '../../../ui/breakpoints';
```

(b) Replace `timeScaleOptions()` and its comment with:

```ts
/** v246 §A3: room above and below the candles, so the newest candle's
 *  last-value tag is never pushed onto the top or bottom price label. */
export const CANDLE_SCALE_MARGINS = { top: 0.12, bottom: 0.12 } as const;

/** v246 §A3: an intraday tick is labelled only on a whole hour; any other
 *  time tick is blank. Times are Berlin wall time read as UTC (`toChartTime`),
 *  so UTC minutes are wall minutes; the fall-back repeat (one second later)
 *  is still its whole hour. Day, month and year ticks keep the library's
 *  labels (`null`). */
export function wholeTickLabel(time: Time, type: TickMarkType): string | null {
  const timeTick = type === TickMarkType.Time || type === TickMarkType.TimeWithSeconds;
  if (!timeTick || typeof time !== 'number') return null;
  const at = new Date(time * 1000);
  return at.getUTCMinutes() === 0 ? `${String(at.getUTCHours()).padStart(2, '0')}:00` : '';
}

/** Time on the axis for 1H/4H only, whole hours only; one place for create(),
 *  render() and a theme flip, because applyChartTheme() alone resets timeVisible. */
function timeScaleOptions(data: EquityCandlesResponse | null) {
  return { timeVisible: data ? isIntraday(data.tf) : false, secondsVisible: false, tickMarkFormatter: wholeTickLabel };
}
```

(c) Below `private readonly theme = inject(ThemeService);` add:

```ts
  /** v246 §A3: below 640px the balance above the chart is the last value. */
  private readonly viewport = inject(ViewportService);
```

(d) In the constructor, directly after the restyle effect, add:

```ts
    // v246 §A3: the last-value tag sits on a price label at phone height; the
    // balance printed above the chart carries that figure there instead.
    effect(() => {
      const phone = this.viewport.isPhone();
      untracked(() => this.series?.applyOptions({ lastValueVisible: !phone }));
    });
```

(e) In `create()`, replace the lines from `const chart = createChart(element, chartOptions(palette));` through the closing `});` of `chart.addSeries(...)` with:

```ts
    // Sized by the library (autoSize); themed by the shared module, which
    // never sets sizing and resets timeVisible, hence the time scale after it.
    const chart = createChart(element, { autoSize: true });
    applyChartTheme(chart, palette);
    chart.applyOptions({ timeScale: timeScaleOptions(this.store.data()) });
    const series = chart.addSeries(CandlestickSeries, {
      ...candleSeriesColors(palette),
      priceLineVisible: false,
      lastValueVisible: !this.viewport.isPhone(),
      priceFormat,
    });
    series.priceScale().applyOptions({ scaleMargins: CANDLE_SCALE_MARGINS });
```

(f) In `restyle()`, replace `chart.applyOptions(chartOptions(palette));` with `applyChartTheme(chart, palette);` (the next line, `chart.applyOptions({ timeScale: timeScaleOptions(this.store.data()) });`, stays).

- [ ] **Step 3: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: PASS, 0 failed (the new `describe`, the updated v225 theme test, and every gesture, target and Latest-button test unchanged).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed (`dashboard.spec.ts` and `portfolio-value` specs mount this component).

The browser view at 390, 820 and 1440 is V246-16b's probe and V246-18's check.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts
git commit -m "fix(v246): Dashboard equity candles on the shared chart theme -- grouped price axis, no last-value tag on a phone, whole-hour ticks" -m "Spec §A3: applyChartTheme + priceFormat (997,800.00, true minus); below 640px the balance above the chart replaces the tag, from 640px up 12% scale margins keep it off the edge labels; intraday ticks only on whole hours."
```

### Task V246-16b: Dashboard equity candles: confirm the stray `)` at the left of the time axis in Chromium and keep edge tick labels whole

**Model:** opus — the glyph has no source in the code (brief §0.8); the task confirms it from screenshots and a DOM probe in a real browser before changing the time scale, whose range contracts (v181 targets, paging, the Latest button) must all survive.

**Files:**
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts` — `timeScaleOptions()` (as V246-16 left it).
- Modify: `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts` — one test appended to V246-16's `describe('sb-equity-candles on the shared chart theme (v246 §A3)')`.
- Create (not committed): `<scratchpad>/find-paren.mjs`, the probe below.
- Not expected: a primitive under `ui/chart/primitives/` (the ledger allowed for one). None draws text near the time axis — `vline-primitive.ts` writes its "Recording started" label at the top of the pane, `baseline-primitive.ts` draws no text — so a primitive only changes if the probe contradicts this, and then the task stops (Step 2).

This task is a split of V246-16 (20 KB cap); the controller adds its ledger row directly below V246-16. It runs after V246-16.

**Interfaces:**
- Consumes: V246-16's `timeScaleOptions(data)` (returns `{ timeVisible, secondsVisible: false, tickMarkFormatter: wholeTickLabel }`) and its spec `describe`'s `inner()` helper.
- Produces: `timeScaleOptions()` also returns `fixLeftEdge: true`. No new export.

**Why.** Spec §A3: "a stray `)` sits at the left of the time axis (1440)" and "The stray `)` tick goes." Nothing in `equity-candles.ts` prints a `)` (the readout's `(…%)` sits above the chart, the caption below it), but lightweight-charts does draw a cut glyph there: its time axis centres each tick label on its bar and only pulls an edge label inside the axis when `fixLeftEdge` is set (`TimeScale` marks `needAlignCoordinate` for the leftmost labels only when the left edge is fixed; `TimeAxisWidget._alignTickMarkLabelCoordinate` then shifts them). With the edge free, a label on the leftmost visible bar is drawn half outside the canvas, and the right half of a `0`, `O` or `C` reads as `)`. Fixing the left edge makes the library keep that label whole, and it stops a drag past the oldest loaded candle into empty space; paging still triggers, because `shouldLoadOlder` fires while `range.from < PAGE_TRIGGER_CANDLES` and a fixed edge still reaches index 0. The v181 targets use `first - 0.4` as their left bound, inside the half bar a fixed edge allows. Step 1 confirms this source in Chromium first, because the brief could not find it in code (§0.8): a different source is the controller's call, not a guess.

- [ ] **Step 1: Confirm the source (before changing anything)**

Build and serve a local replica the way the layout audit does (`docs/claude/ui-design.md` § Checklist): `/replicate-prod-db`, `cd frontend && npm run build`, `python admin_ui.py`, base `http://localhost:1234`. Save this probe as `<scratchpad>/find-paren.mjs`, run `node <scratchpad>/find-paren.mjs <scratchpad> 1440` from `frontend/` (Playwright resolves from `frontend/node_modules`), then open the four PNGs it writes:

```js
import { chromium } from 'playwright';
const [out, widthArg] = process.argv.slice(2);
const width = Number(widthArg ?? 1440);
const base = 'http://localhost:1234';
try { process.loadEnvFile('../.env'); } catch { /* the sign-in below fails and says so */ }
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: 'block' });
const page = await context.newPage();
await page.goto(base, { waitUntil: 'domcontentloaded' });
const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
const signedIn = await page.evaluate(async ({ url, body }) => (await fetch(url, { method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).ok,
  { url: `${base}/api/v1/session`, body: { username, password } });
if (!signedIn) throw new Error('cannot sign in: is admin_ui.py up, and does .env set ADMIN_USERNAME/ADMIN_PASSWORD?');
await page.goto(`${base}/dashboard`, { waitUntil: 'load' });
for (const tf of ['1H', '4H', '1D', '1W']) {
  await page.locator('sb-equity-candles .timeframe button.segment', { hasText: tf }).click();
  await page.waitForTimeout(1500);
  const box = await page.locator('sb-equity-candles .stage').boundingBox();
  // The bottom-left corner, where the glyph was seen: 160 x 40 CSS px.
  await page.screenshot({ path: `${out}/paren-${tf}@${width}.png`, clip: { x: box.x, y: box.y + box.height - 40, width: 160, height: 40 } });
  const caption = await page.locator('sb-equity-candles .caption').isVisible();
  const overlapping = await page.evaluate(() => {
    const stage = document.querySelector('sb-equity-candles .stage').getBoundingClientRect();
    return [...document.querySelectorAll('body *')].filter((el) => {
      const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
      const r = el.getBoundingClientRect();
      return text && r.bottom > stage.bottom - 40 && r.top < stage.bottom + 4 && r.right > stage.left && r.left < stage.left + 160;
    }).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}: ${el.textContent.trim().slice(0, 40)}`);
  });
  console.log(tf, `caption=${caption}`, JSON.stringify(overlapping));
}
await browser.close();
```

Read the result:

- No DOM hit, and the `)` sits on the time-axis band of a timeframe whose leftmost visible bar carries a tick label → the cut edge label, as expected. Go on.
- No `)` in any PNG → V246-16's whole-hour labels already blanked the cut label (a `:30` tick); go on anyway — the edge is still free, and the next label on the leftmost bar would be cut the same way.
- The DOM list names an element whose text ends in `)`, or the glyph sits inside the plot (above the axis band) → stop and report `BLOCKED: stray ')' is <the element, or where in the plot>` with the console output and the PNG paths. Do not change anything for it.

- [ ] **Step 2: Write the failing test**

Append to V246-16's `describe('sb-equity-candles on the shared chart theme (v246 §A3)', …)` in `frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts`:

```ts
  it('keeps the leftmost tick label whole: the left edge is fixed, through render and a theme flip', async () => {
    const { fixture, stub } = render(response(dailyCandles(40)));
    const chart = inner(fixture).chart;
    expect(chart.options().timeScale.fixLeftEdge).toBe(true);
    stub.data.set(response(hourlyCandles(30), { tf: '1H' }));
    fixture.detectChanges();
    expect(chart.options().timeScale.fixLeftEdge).toBe(true);
    TestBed.inject(ThemeService).set('navy');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(chart.options().timeScale.fixLeftEdge).toBe(true);
  });
```

(`equityCandlesStoreStub` exposes `data` as a writable signal; the paging tests set it the same way.)

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: FAIL in this test only — `fixLeftEdge` is `false` (the library default).

- [ ] **Step 3: Implement**

In `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, replace V246-16's `timeScaleOptions()` and its comment with:

```ts
/** Time on the axis for 1H/4H only, whole hours only; one place for create(),
 *  render() and a theme flip, because applyChartTheme() alone resets timeVisible.
 *  v246 §A3: the left edge is fixed, so lightweight-charts keeps the leftmost
 *  tick label inside the axis instead of cutting it in half (the stray ")"). */
function timeScaleOptions(data: EquityCandlesResponse | null) {
  return {
    timeVisible: data ? isIntraday(data.tf) : false,
    secondsVisible: false,
    tickMarkFormatter: wholeTickLabel,
    fixLeftEdge: true,
  };
}
```

- [ ] **Step 4: Run the spec and the probe to verify**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/dashboard/panels/equity-candles.spec.ts`
Expected: PASS, 0 failed — the new test, and every v181 target, paging and Latest-button test unchanged (targets stay inside the half bar a fixed edge allows; paging still fires at the left edge).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed.

Rebuild (`cd frontend && npm run build`, restart `python admin_ui.py`) and re-run the probe at 1440, 820 and 390 (`node <scratchpad>/find-paren.mjs <scratchpad> 820`, `… 390`). Expected: no `)` in any PNG; at 390 no last-value tag over a price label (V246-16). By hand at 1440: drag the chart to the right until the oldest candle reaches the left edge — it stops there, and older history still loads (the candle count grows).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/dashboard/panels/equity-candles.ts frontend/src/app/workspaces/dashboard/panels/equity-candles.spec.ts
git commit -m "fix(v246): Dashboard equity time axis keeps its leftmost tick label whole -- the stray ')' is gone" -m "Spec §A3: lightweight-charts drew the label on the leftmost bar half outside the axis (the right half of a 0 reads as ')'), and only aligns edge labels when fixLeftEdge is set. Confirmed in Chromium at 1440 (probe: <timeframes it showed on>); paging and v181 targets unchanged."
```

### Task V246-17: SVG token sweep: line-chart, histogram, bar-list, sparkline, share-bar, gauge read `SVG_CHART_TOKENS`

**Model:** sonnet — mechanical substitutions in six small components with every old and new string given, plus one behaviour change (a single-series line chart in the accent) pinned by a render test.

**Files:**
- Modify: `frontend/src/app/ui/line-chart.ts` — imports (lines 1-4), styles (lines 147-153), `colorOf()` (lines 209-211); `frontend/src/app/ui/line-chart.spec.ts` — one `describe` appended.
- Modify: `frontend/src/app/ui/histogram.ts` — imports (line 3), styles (lines 77, 79, 95-97, 107, 115-118); `frontend/src/app/ui/histogram.spec.ts` — one `describe` appended.
- Modify: `frontend/src/app/ui/bar-list.ts` — imports (line 2), the one-line `styles` (line 17); `frontend/src/app/ui/bar-list.spec.ts` — one `describe` appended.
- Modify: `frontend/src/app/ui/sparkline.ts` — imports (line 3), styles (lines 82, 89-90); Create: `frontend/src/app/ui/sparkline.spec.ts`.
- Modify: `frontend/src/app/ui/share-bar.ts` — imports (line 2), the one-line `styles` (line 11); `frontend/src/app/ui/share-bar.spec.ts` — one `describe` appended.
- Modify: `frontend/src/app/ui/gauge.ts` — imports (line 3), styles (lines 58-60, 66); `frontend/src/app/ui/gauge.spec.ts` — one `describe` appended.

**Interfaces:**
- Consumes (V246-12, `ui/chart/chart-theme`): `SVG_CHART_TOKENS` (`line` `--accent`, `pos` `--pos`, `neg` `--neg`, `grid` `--border`, `axisText` `--text-secondary`, `crosshair` `--text-muted`, `barRadius` `--radius-sm`, `labelSize` `--text-micro`; px numbers `strokeWidth` 2, `strokeWidthThin` 1, `barGap` 2), `themedToken(name)`; `CHART_CHROME.axis` (`--border-strong`, `ui/chart/chart-frame.ts`, unchanged).
- Produces: none. No input, output or selector changes; every consumer page (Analytics tabs, small multiples, stat tiles, Reports, Providers, Watchlist, Gallery) renders as before apart from the inks below.

**Why.** Spec §A3: "**SVG charts** (`line-chart.ts`, `histogram.ts`, `bar-list.ts`, `sparkline.ts`, `share-bar.ts`, `gauge.ts`) take colours and stroke values from `SVG_CHART_TOKENS` instead of their own literals", and the theme's inks: "neutral line = `--accent` … axis text = `--text-secondary`, crosshair = `--text-tertiary`" (→ `--text-muted`, Handoff 3). The components already use tokens, so most of this is single-sourcing: the CSS reads `var(${SVG_CHART_TOKENS.pos})` (still `var(--pos)` after interpolation) and `${SVG_CHART_TOKENS.strokeWidth}` instead of its own copy. What visibly changes, on purpose:
- a **one-series** `sb-line-chart` draws in the accent instead of `--chart-1`, the blue "used nowhere else on the site" the partner flagged (spec "What's wrong"); several series keep the categorical `--chart-N` palette, which `SVG_CHART_TOKENS` does not replace, and an explicit `color` still wins;
- bin and row **labels** (histogram, bar-list) move from `--text-muted` to the axis-text ink `--text-secondary`, as the canvas charts do since V246-12;
- **zero lines** (line-chart, bar-list's signed axis) use the axis ink `CHART_CHROME.axis` (`--border-strong`), the zero line `sb-time-series` draws; **reference lines** (line-chart, histogram, bar-list) use the crosshair ink `--text-muted`, one step up from `--text-faint`;
- the sparkline's stroke goes from 1.25 to `strokeWidthThin` (1px): a 24px-tall trend line in a tile is the thin stroke.

Left alone, as geometry or non-chart ink: the gauge arc's `stroke-width="10"` (the dial's thickness in its 120-unit view box), layout gaps in `--space-*`, the muted sparkline and "below" bar ink `--text-faint`/`--text-muted` (no chart token names a deliberately quiet ink), text colours of values and counts.

- [ ] **Step 1: Write the failing tests**

Each appended block reads its component's source the way `histogram.spec.ts` already does. Add `import { readFileSync } from 'node:fs';` and `import { join } from 'node:path';` to `line-chart.spec.ts` and `gauge.spec.ts` (the other specs have them).

(a) `frontend/src/app/ui/line-chart.spec.ts` — add `import { themedToken } from './chart/chart-theme';` and append:

```ts
describe('LineChart reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/line-chart.ts'), 'utf8');

  function render(series: { name: string; color?: string; points: { date: string; value: number }[] }[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(LineChart);
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  const POINTS = [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 1 }];

  it('draws a lone series in the accent, not the categorical blue', () => {
    const stroke = render([{ name: 'Equity', points: POINTS }]).querySelector('path.series')!.getAttribute('stroke');
    expect(stroke).toBe(themedToken('--accent'));
    expect(stroke).not.toBe(themedToken('--chart-1'));
  });

  it('keeps the categorical palette for several series and an explicit colour for any', () => {
    const el = render([{ name: 'a', points: POINTS }, { name: 'b', points: POINTS }]);
    expect([...el.querySelectorAll('path.series')].map((p) => p.getAttribute('stroke')))
      .toEqual([themedToken('--chart-1'), themedToken('--chart-2')]);
    TestBed.resetTestingModule();
    const lone = render([{ name: 'a', color: '--chart-3', points: POINTS }]);
    expect(lone.querySelector('path.series')!.getAttribute('stroke')).toBe(themedToken('--chart-3'));
  });

  it('takes stroke widths and line inks from the shared tokens', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).toMatch(/path\.series \{ stroke-width: \$\{SVG_CHART_TOKENS\.strokeWidth\};/);
    expect(src).toMatch(/line\.zero \{ stroke: var\(\$\{CHART_CHROME\.axis\}\); stroke-width: \$\{SVG_CHART_TOKENS\.strokeWidthThin\};/);
    expect(src).toMatch(/stroke: var\(\$\{SVG_CHART_TOKENS\.crosshair\}\);/);
    expect(src).not.toMatch(/stroke-width:\s*[\d.]/);
  });
});
```

(b) `frontend/src/app/ui/histogram.spec.ts` — append:

```ts
describe('Histogram reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/histogram.ts'), 'utf8');

  it('imports the shared tokens and declares no chart ink, radius or gap of its own', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).not.toMatch(/var\(--(pos|neg|accent|radius-sm)\)/);
    expect(src).not.toMatch(/gap: 2px|border-left: 1px/);
  });

  it('colours gains and losses, rounds bars and spaces them from the tokens', () => {
    expect(src).toMatch(/\.fill \{[^}]*background: var\(\$\{SVG_CHART_TOKENS\.pos\}\);[^}]*border-radius: var\(\$\{SVG_CHART_TOKENS\.barRadius\}\);/);
    expect(src).toContain('.fill.negative { background: var(${SVG_CHART_TOKENS.neg}); }');
    expect(src).toContain('ul { display: grid; gap: ${SVG_CHART_TOKENS.barGap}px; list-style: none; }');
  });

  it('writes bin labels in the axis-text ink at the label size', () => {
    expect(src).toMatch(/\.label \{\s*color: var\(\$\{SVG_CHART_TOKENS\.axisText\}\);\s*font-size: var\(\$\{SVG_CHART_TOKENS\.labelSize\}\);/);
  });
});
```

(c) `frontend/src/app/ui/bar-list.spec.ts` — append:

```ts
describe('BarList reads SVG_CHART_TOKENS (v246 §A3)', () => {
  it('imports the shared tokens and declares no chart ink, radius or hairline of its own', () => {
    expect(BAR_SOURCE).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(BAR_SOURCE).not.toMatch(/var\(--(pos|neg|accent|radius-sm)\)/);
    expect(BAR_SOURCE).not.toMatch(/border-left:1px/);
  });

  it('takes tones, the zero axis, the reference line and labels from the tokens', () => {
    expect(BAR_SOURCE).toContain(".fill[data-tone='pos']{background:var(${SVG_CHART_TOKENS.pos})}");
    expect(BAR_SOURCE).toContain(".fill[data-tone='neg']{background:var(${SVG_CHART_TOKENS.neg})}");
    expect(BAR_SOURCE).toContain(".fill[data-tone='above']{background:var(${SVG_CHART_TOKENS.line})}");
    expect(BAR_SOURCE).toContain('border-left:${SVG_CHART_TOKENS.strokeWidthThin}px solid var(${CHART_CHROME.axis})');
    expect(BAR_SOURCE).toContain('border-left:${SVG_CHART_TOKENS.strokeWidthThin}px dashed var(${SVG_CHART_TOKENS.crosshair})');
    expect(BAR_SOURCE).toContain('.label{color:var(${SVG_CHART_TOKENS.axisText});font-size:var(${SVG_CHART_TOKENS.labelSize})');
  });
});
```

(d) Create `frontend/src/app/ui/sparkline.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Sparkline } from './sparkline';

function render(points: readonly number[]): SVGPathElement | null {
  const fixture = TestBed.createComponent(Sparkline);
  fixture.componentRef.setInput('points', points);
  fixture.detectChanges();
  return (fixture.nativeElement as HTMLElement).querySelector('path');
}

describe('Sparkline tone (v246 §A3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('tones the line by net direction, first point to last', () => {
    expect(render([1, 3, 2])!.classList.contains('pos')).toBe(true);
    expect(render([3, 1, 2])!.classList.contains('neg')).toBe(true);
    expect(render([2, 5, 2])!.classList.length).toBe(0);
  });

  it('draws nothing for no points and an untoned line for one', () => {
    expect(render([])).toBeNull();
    expect(render([4])!.classList.length).toBe(0);
  });
});

describe('Sparkline reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/sparkline.ts'), 'utf8');

  it('takes its stroke width and gain/loss inks from the shared tokens', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).toContain('stroke-width: ${SVG_CHART_TOKENS.strokeWidthThin};');
    expect(src).toContain('.pos { stroke: var(${SVG_CHART_TOKENS.pos}); }');
    expect(src).toContain('.neg { stroke: var(${SVG_CHART_TOKENS.neg}); }');
    expect(src).not.toMatch(/stroke-width:\s*[\d.]/);
    expect(src).not.toMatch(/var\(--(pos|neg)\)/);
  });
});
```

(e) `frontend/src/app/ui/share-bar.spec.ts` — append:

```ts
describe('ShareBar reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/share-bar.ts'), 'utf8');

  it('imports the shared tokens and declares no chart ink, radius or gap of its own', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).not.toMatch(/var\(--(pos|neg|accent|radius-sm)\)/);
    expect(src).not.toContain('gap:2px');
  });

  it('takes the tones, the segment gap and the radius from the tokens', () => {
    expect(src).toContain("[data-tone='pos'] { background:var(${SVG_CHART_TOKENS.pos}); }");
    expect(src).toContain("[data-tone='neg'] { background:var(${SVG_CHART_TOKENS.neg}); }");
    expect(src).toContain("[data-tone='accent'] { background:var(${SVG_CHART_TOKENS.line}); }");
    expect(src).toContain('gap:${SVG_CHART_TOKENS.barGap}px;');
    expect(src).toContain('border-radius:var(${SVG_CHART_TOKENS.barRadius});');
  });
});
```

(f) `frontend/src/app/ui/gauge.spec.ts` — append:

```ts
describe('Gauge reads SVG_CHART_TOKENS (v246 §A3)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/gauge.ts'), 'utf8');

  it('draws the track, the needle and the over-limit state in the shared inks', () => {
    expect(src).toMatch(/import \{[^}]*SVG_CHART_TOKENS[^}]*\} from '\.\/chart\/chart-theme'/);
    expect(src).toContain('.track { stroke: var(${SVG_CHART_TOKENS.grid}); }');
    expect(src).toContain('.needle { stroke: var(${SVG_CHART_TOKENS.line}); }');
    expect(src).toContain('.over .needle { stroke: var(${SVG_CHART_TOKENS.neg}); }');
    expect(src).toContain('.over .readout { color: var(${SVG_CHART_TOKENS.neg}); }');
    expect(src).not.toMatch(/var\(--(neg|accent|border)\)/);
  });
});
```

- [ ] **Step 2: Run the specs to verify they fail**

Run: `cd frontend && npx ng test --watch=false --include src/app/ui/line-chart.spec.ts --include src/app/ui/histogram.spec.ts --include src/app/ui/bar-list.spec.ts --include src/app/ui/sparkline.spec.ts --include src/app/ui/share-bar.spec.ts --include src/app/ui/gauge.spec.ts`
Expected: FAIL in the six `reads SVG_CHART_TOKENS` blocks (no import, literal inks) and in `draws a lone series in the accent` (stroke is `--chart-1`). The sparkline tone tests and every existing test pass.

- [ ] **Step 3: Implement**

In each file, add `import { SVG_CHART_TOKENS } from './chart/chart-theme';` below the other `./chart/…` import, or below the `@angular/core` import where there is none (line-chart adds `SVG_CHART_TOKENS, themedToken`; histogram, bar-list and line-chart keep their `CHART_CHROME` import). Then:

(a) `line-chart.ts` styles — replace lines 147-153 with:

```css
    path.series { stroke-width: ${SVG_CHART_TOKENS.strokeWidth}; vector-effect: non-scaling-stroke; }
    line.zero { stroke: var(${CHART_CHROME.axis}); stroke-width: ${SVG_CHART_TOKENS.strokeWidthThin}; vector-effect: non-scaling-stroke; }
    line.reference {
      stroke: var(${SVG_CHART_TOKENS.crosshair});
      stroke-width: ${SVG_CHART_TOKENS.strokeWidthThin};
      stroke-dasharray: 4 3;
      vector-effect: non-scaling-stroke;
    }
```

and `colorOf()`:

```ts
  /** An explicit token wins; a lone series is the neutral line (v246 §A3,
   *  the accent); several series take the categorical palette by index. */
  protected colorOf(series: LineChartSeries, index: number): string {
    if (series.color) return token(series.color);
    return this.series().length === 1 ? themedToken(SVG_CHART_TOKENS.line) : seriesColour(index);
  }
```

(b) `histogram.ts` styles: `border-left: 1px dashed var(--text-faint);` → `border-left: ${SVG_CHART_TOKENS.strokeWidthThin}px dashed var(${SVG_CHART_TOKENS.crosshair});`; `ul { display: grid; gap: 2px; list-style: none; }` → `ul { display: grid; gap: ${SVG_CHART_TOKENS.barGap}px; list-style: none; }`; in `.label`, `color: var(${CHART_CHROME.tickColour});` → `color: var(${SVG_CHART_TOKENS.axisText});` and `font-size: var(${CHART_CHROME.tickSize});` → `font-size: var(${SVG_CHART_TOKENS.labelSize});`; both `border-radius: var(--radius-sm);` → `border-radius: var(${SVG_CHART_TOKENS.barRadius});`; `background: var(--pos);` → `background: var(${SVG_CHART_TOKENS.pos});`; `.fill.negative { background: var(--neg); }` → `.fill.negative { background: var(${SVG_CHART_TOKENS.neg}); }`. Drop the `CHART_CHROME` import if nothing else in the file reads it (`grep -n CHART_CHROME frontend/src/app/ui/histogram.ts`), and update the v54 D5 comment above `.label` to say the label takes the shared axis-text ink.

(c) `bar-list.ts` one-line `styles` — exact substring swaps:
- `.label{color:var(${CHART_CHROME.tickColour});font-size:var(${CHART_CHROME.tickSize})` → `.label{color:var(${SVG_CHART_TOKENS.axisText});font-size:var(${SVG_CHART_TOKENS.labelSize})`
- every `border-radius:var(--radius-sm)` (2) → `border-radius:var(${SVG_CHART_TOKENS.barRadius})`
- `border-left:1px solid var(--border-strong)` → `border-left:${SVG_CHART_TOKENS.strokeWidthThin}px solid var(${CHART_CHROME.axis})`
- `border-left:1px dashed var(--text-faint)` → `border-left:${SVG_CHART_TOKENS.strokeWidthThin}px dashed var(${SVG_CHART_TOKENS.crosshair})`
- `background:var(--pos)` → `background:var(${SVG_CHART_TOKENS.pos})`; `background:var(--neg)` → `background:var(${SVG_CHART_TOKENS.neg})`; `background:var(--accent)` → `background:var(${SVG_CHART_TOKENS.line})`

(d) `sparkline.ts` styles: `stroke-width: 1.25;` → `stroke-width: ${SVG_CHART_TOKENS.strokeWidthThin};`; `.pos { stroke: var(--pos); }` → `.pos { stroke: var(${SVG_CHART_TOKENS.pos}); }`; `.neg { stroke: var(--neg); }` → `.neg { stroke: var(${SVG_CHART_TOKENS.neg}); }`. Above `stroke: var(--text-muted);` add the comment `/* Flat or unknown: quieter than any chart ink -- a trend inside a tile. */`.

(e) `share-bar.ts` one-line `styles`: `gap:2px;` → `gap:${SVG_CHART_TOKENS.barGap}px;`; every `var(--radius-sm)` (6) → `var(${SVG_CHART_TOKENS.barRadius})`; `background:var(--pos)` → `background:var(${SVG_CHART_TOKENS.pos})`; `background:var(--neg)` → `background:var(${SVG_CHART_TOKENS.neg})`; `background:var(--accent)` → `background:var(${SVG_CHART_TOKENS.line})`.

(f) `gauge.ts` styles: `.track { stroke: var(--border); }` → `.track { stroke: var(${SVG_CHART_TOKENS.grid}); }`; `.needle { stroke: var(--accent); }` → `.needle { stroke: var(${SVG_CHART_TOKENS.line}); }`; `.over .needle { stroke: var(--neg); }` → `.over .needle { stroke: var(${SVG_CHART_TOKENS.neg}); }`; `.over .readout { color: var(--neg); }` → `.over .readout { color: var(${SVG_CHART_TOKENS.neg}); }`. The two `stroke-width="10"` template attributes stay (the dial's thickness).

Check that no hand-made literal is left: `grep -nE "var\(--(pos|neg|accent|radius-sm)\)|stroke-width:\s*[0-9]" frontend/src/app/ui/{line-chart,histogram,bar-list,sparkline,share-bar,gauge}.ts` prints nothing.

- [ ] **Step 4: Run the specs to verify they pass**

Run: the Step 2 command again.
Expected: PASS, 0 failed — every existing test as well (the containment and label-overflow source tests match rules this task does not touch).

Then: `python scripts/dev/testrun.py changed`
Expected: 0 failed. The colour gate (`ui/primitives.spec.ts`) passes: no hex or `rgb()` was added. If a consumer spec pinned a lone series' stroke to `--chart-1`, update that expectation to `themedToken('--accent')` in the same commit (none did on 2026-11-25: `git grep -n "chart-1" -- 'frontend/src/**/*.spec.ts'` lists only palette and tooltip tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/line-chart.ts frontend/src/app/ui/line-chart.spec.ts frontend/src/app/ui/histogram.ts frontend/src/app/ui/histogram.spec.ts frontend/src/app/ui/bar-list.ts frontend/src/app/ui/bar-list.spec.ts frontend/src/app/ui/sparkline.ts frontend/src/app/ui/sparkline.spec.ts frontend/src/app/ui/share-bar.ts frontend/src/app/ui/share-bar.spec.ts frontend/src/app/ui/gauge.ts frontend/src/app/ui/gauge.spec.ts
git commit -m "refactor(v246): the six SVG charts read SVG_CHART_TOKENS -- one source for chart inks, stroke widths, bar radius and gap" -m "Spec §A3. Visible on purpose: a lone line-chart series in the accent (not the --chart-1 blue), bin and row labels in the axis-text ink, zero lines in the axis ink, reference lines in the crosshair ink, a 1px sparkline. Gauge arc thickness and layout gaps untouched."
```


---

# Phase 10 — Closing check

### Task V246-18: Closing browser check: bottom-edge alignment per bar and the layout audit at 390/820/1440

**Model:** sonnet — a Playwright script on the pattern of `shell-nav-check.mjs`, its pure helpers under `node --test`, and a scripted run; no app code changes.

**Files:**
- Create: `frontend/scripts/v246-bar-alignment-check.mjs` — the browser check.
- Create: `frontend/scripts/v246-bar-alignment-check-lib.mjs` — its pure helpers (bars, widths, verdicts).
- Create: `frontend/scripts/v246-bar-alignment-check-lib.test.mjs` — `node --test` for the helpers; `tests/scripts/test_node_scripts.py` picks it up (every `frontend/scripts/*.test.mjs`), so CI runs it with no suite edit.

The ledger row names only the script; the lib and its test follow the repo's pattern for browser checks (`shell-nav-check-lib.mjs` + `.test.mjs`) so the verdict logic is tested without a browser. The controller adds the two paths to the V246-18 ledger row.

**Interfaces:**
- Consumes: every v246 task merged in the worktree (the `sb-field` bars of V246-7..V246-10, the charts of V246-15..V246-17); `exitCode`, `formatResult` from `frontend/scripts/shell-nav-check-lib.mjs` (v247, unchanged); `frontend/scripts/layout-audit.mjs` and its `audit.json` (`{ unallowed: [{ route, width, check, selector, detail }] }`, unchanged).
- Produces: none.

**Why.** Index Goal "How we know it worked": "the closing task's Playwright check reports one bottom edge per bar on Trades, Calendar, Analytics, Watchlist and Dashboard at 390, 820 and 1440, and `node frontend/scripts/layout-audit.mjs` reports no overflow, target-size or text-size finding on those pages". Handoff 9: jsdom has no layout, so the consumer tasks assert CSS source and this task measures in Chromium, at 1440 (`--control-h` 28px) and at 820 and 390 (44px), which covers both token values. A bar wraps on a narrow screen, so "one bottom edge" is per visual row: fields are grouped into rows by their vertical centre, and each row's bottoms must agree within 1px. Each control inside a field must be `--control-h` tall (±1px; an `sb-hint` trigger inside a label is not a control). The layout audit visits every route and fails on any finding the allow-list does not name; this plan answers for the five bar pages and three checks, so the check reads `audit.json` and fails on those only — a finding elsewhere is reported by the audit's own exit code and goes to plan B, not fixed here. Spec "Three devices": Playwright only, signed in through `POST /api/v1/session` with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` loaded inside the process and never printed.

- [ ] **Step 1: Write the failing helper tests**

Create `frontend/scripts/v246-bar-alignment-check-lib.test.mjs`:

```js
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  AUDIT_CHECKS, BARS, DEFAULT_BASE, VIEWPORTS,
  auditVerdict, bottomVerdict, controlHeightAt, groupRows, heightVerdict, parseArgs,
} from './v246-bar-alignment-check-lib.mjs';

test('parseArgs defaults to the local admin, strips a trailing slash, takes --out and --audit', () => {
  assert.deepEqual(parseArgs([]), { base: DEFAULT_BASE, out: null, audit: null });
  assert.deepEqual(parseArgs(['--base', 'http://localhost:4123/', '--audit', 'a.json']),
    { base: 'http://localhost:4123', out: null, audit: 'a.json' });
  assert.throws(() => parseArgs(['--widths', '390']), /unknown or incomplete flag --widths/);
  assert.throws(() => parseArgs(['--out']), /unknown or incomplete flag --out/);
});

test('measures phone, tablet and desktop, with 44px controls below 1024px and 28px from it', () => {
  assert.deepEqual(VIEWPORTS.map((v) => v.width), [390, 820, 1440]);
  assert.equal(controlHeightAt(390), 44);
  assert.equal(controlHeightAt(1023), 44);
  assert.equal(controlHeightAt(1024), 28);
  assert.equal(controlHeightAt(1440), 28);
});

test('checks the five bars v246 wraps in sb-field', () => {
  assert.deepEqual(BARS.map((b) => b.name), ['trades', 'calendar', 'analytics', 'watchlist', 'dashboard']);
  assert.deepEqual(BARS.map((b) => b.path), ['/trades', '/calendar', '/insights/analytics', '/watchlist', '/dashboard']);
  assert.equal(BARS.find((b) => b.name === 'calendar').bar, 'sb-control-row[align="end"]');
  assert.deepEqual(AUDIT_CHECKS, ['overflow', 'tap', 'text']);
});

test('groups fields into visual rows by their vertical centre', () => {
  const rows = groupRows([
    { name: 'b', top: 0, bottom: 44 }, { name: 'a', top: 20, bottom: 44 }, { name: 'c', top: 60, bottom: 104 },
  ]);
  assert.deepEqual(rows.map((row) => row.map((box) => box.name)), [['b', 'a'], ['c']]);
  assert.deepEqual(groupRows([]), []);
});

test('passes rows whose bottoms agree within a pixel and names the row that does not', () => {
  assert.deepEqual(bottomVerdict([{ name: 'a', top: 0, bottom: 44 }, { name: 'b', top: 18, bottom: 44.8 }]), []);
  assert.deepEqual(bottomVerdict([{ name: 'Range', top: 0, bottom: 52 }, { name: 'Unit', top: 0, bottom: 24 }]),
    ['row 1: Range=52.0 Unit=24.0']);
  assert.deepEqual(bottomVerdict([]), []);
});

test('names every control that is not --control-h tall, half a pixel or more off', () => {
  assert.deepEqual(heightVerdict([{ name: 'Strategy', height: 28.4 }, { name: '‹', height: 24 }], 28), ['‹=24.0']);
  assert.deepEqual(heightVerdict([], 44), []);
});

test('keeps only the bar pages and the overflow, tap and text checks from the audit', () => {
  const unallowed = [
    { route: '/trades', width: 390, check: 'tap', selector: 'button.x', detail: '30x30' },
    { route: '/trades', width: 390, check: 'baseline', selector: 'p', detail: '3px' },
    { route: '/system', width: 390, check: 'overflow', selector: 'main', detail: '+12px' },
  ];
  assert.deepEqual(auditVerdict(unallowed), ['/trades @390 tap button.x -- 30x30']);
  assert.deepEqual(auditVerdict([]), []);
});
```

Run: `node --test frontend/scripts/v246-bar-alignment-check-lib.test.mjs`
Expected: FAIL — `Cannot find module …/v246-bar-alignment-check-lib.mjs`.

- [ ] **Step 2: Implement the helpers**

Create `frontend/scripts/v246-bar-alignment-check-lib.mjs`:

```js
/**
 * Pure helpers for v246-bar-alignment-check.mjs (v246 V246-18; spec v246 "Three devices",
 * index Handoff 9): the bars, the widths, the expected control height and the verdicts.
 * No browser here, so `node --test` covers all of it.
 */
export { exitCode, formatResult } from './shell-nav-check-lib.mjs';

export const DEFAULT_BASE = 'http://localhost:1234';
export const BOTTOM_TOLERANCE_PX = 1;

/** Phone, tablet, desktop: 820 (not 768) is the tablet the spec's findings were seen at. */
export const VIEWPORTS = Object.freeze([
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'desktop', width: 1440, height: 900 },
]);

/** `--control-h`: 44px below 1024px, 28px from 1024px (styles/tokens.css). */
export function controlHeightAt(width) {
  return width < 1024 ? 44 : 28;
}

/** Every bar a v246 task wraps in sb-field (V246-7..V246-10), and where it lives. */
export const BARS = Object.freeze([
  { name: 'trades', path: '/trades', bar: 'sb-toolbar' },
  { name: 'calendar', path: '/calendar', bar: 'sb-control-row[align="end"]' },
  { name: 'analytics', path: '/insights/analytics', bar: 'sb-control-bar' },
  { name: 'watchlist', path: '/watchlist', bar: 'sb-toolbar' },
  { name: 'dashboard', path: '/dashboard', bar: 'sb-equity-candles .controls' },
]);

/** The layout-audit checks this plan answers for on the bar pages (index Goal). */
export const AUDIT_CHECKS = Object.freeze(['overflow', 'tap', 'text']);

const FLAGS = new Set(['--base', '--out', '--audit']);

export function parseArgs(argv) {
  const opts = { base: DEFAULT_BASE, out: null, audit: null };
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (!FLAGS.has(flag) || value === undefined) throw new Error(`unknown or incomplete flag ${flag}`);
    opts[flag.slice(2)] = flag === '--base' ? value.replace(/\/+$/, '') : value;
  }
  return opts;
}

/** Boxes `{ name, top, bottom }` as visual rows: a box joins the first row its vertical centre falls in. */
export function groupRows(boxes) {
  const rows = [];
  for (const box of [...boxes].sort((a, b) => a.top - b.top)) {
    const centre = (box.top + box.bottom) / 2;
    const row = rows.find((r) => centre >= r.top && centre <= r.bottom);
    if (row) {
      row.boxes.push(box);
      row.top = Math.min(row.top, box.top);
      row.bottom = Math.max(row.bottom, box.bottom);
    } else {
      rows.push({ top: box.top, bottom: box.bottom, boxes: [box] });
    }
  }
  return rows.map((row) => row.boxes);
}

/** One message per row whose bottoms spread past the tolerance; [] when every row lines up. */
export function bottomVerdict(boxes, tolerance = BOTTOM_TOLERANCE_PX) {
  return groupRows(boxes).flatMap((row, index) => {
    const bottoms = row.map((box) => box.bottom);
    if (Math.max(...bottoms) - Math.min(...bottoms) <= tolerance) return [];
    return [`row ${index + 1}: ${row.map((box) => `${box.name}=${box.bottom.toFixed(1)}`).join(' ')}`];
  });
}

/** Controls `{ name, height }` that are not `expected` px tall; under half a pixel is rounding. */
export function heightVerdict(controls, expected) {
  return controls.filter((c) => Math.abs(c.height - expected) >= 0.5).map((c) => `${c.name}=${c.height.toFixed(1)}`);
}

/** The audit's unallowed findings on the bar pages, for the checks this plan answers for. */
export function auditVerdict(unallowed, routes = BARS.map((b) => b.path), checks = AUDIT_CHECKS) {
  return unallowed
    .filter((f) => routes.includes(f.route) && checks.includes(f.check))
    .map((f) => `${f.route} @${f.width} ${f.check} ${f.selector} -- ${f.detail}`);
}
```

Run: `node --test frontend/scripts/v246-bar-alignment-check-lib.test.mjs`
Expected: PASS, 7 tests.

- [ ] **Step 3: Write the browser check**

Create `frontend/scripts/v246-bar-alignment-check.mjs`:

```js
#!/usr/bin/env node
/**
 * v246 V246-18: every bar v246 wraps in sb-field lines its fields up on one bottom edge per
 * visual row, with every control --control-h tall, at 390, 820 and 1440 (spec v246 "Three
 * devices", index Handoff 9). With --audit, also fails on the layout audit's overflow, tap
 * and text findings on those five pages.
 *   node frontend/scripts/v246-bar-alignment-check.mjs [--base http://localhost:1234] [--out DIR] [--audit FILE]
 * .env ADMIN_USERNAME/ADMIN_PASSWORD stay in this process, never printed. Exit 0 / 1 failed / 2 cannot run.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import {
  BARS, VIEWPORTS, auditVerdict, bottomVerdict, controlHeightAt, exitCode, formatResult, heightVerdict, parseArgs,
} from './v246-bar-alignment-check-lib.mjs';

const ENV_FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '.env');
const results = [];

class CannotRun extends Error {}

function check(name, ok, detail = '') {
  const result = { name, ok: Boolean(ok), detail };
  results.push(result);
  console.log(formatResult(result));
}

async function signedInState(browser, base) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  try { process.loadEnvFile(ENV_FILE); } catch { /* no .env: the check below says so */ }
  const { ADMIN_USERNAME: username, ADMIN_PASSWORD: password } = process.env;
  const ok = Boolean(username && password) && await page.evaluate(async ({ url, body }) => (await fetch(url, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })).ok, { url: `${base}/api/v1/session`, body: { username, password } }).catch(() => false);
  const state = ok ? await context.storageState() : null;
  await context.close();
  if (!state) throw new CannotRun(`cannot sign in at ${base}: is the local admin up, and does .env set ADMIN_USERNAME/ADMIN_PASSWORD?`);
  return state;
}

/** Runs in the page: each visible sb-field in the bar, and each control inside it (an sb-hint trigger is not one). */
function measure(barSelector) {
  const bar = document.querySelector(barSelector);
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const fields = bar ? [...bar.querySelectorAll('sb-field')].filter(shown) : [];
  const nameOf = (field) => field.querySelector('.field-label')?.textContent.trim() || field.textContent.trim().slice(0, 24);
  return {
    fields: fields.map((field) => {
      const r = field.getBoundingClientRect();
      return { name: nameOf(field), top: r.top, bottom: r.bottom };
    }),
    controls: fields.flatMap((field) => [...field.querySelectorAll('select, input:not([type="hidden"]), button')]
      .filter((el) => shown(el) && !el.closest('sb-hint'))
      .map((el) => ({ name: `${nameOf(field)}:${el.getAttribute('aria-label') ?? el.textContent.trim().slice(0, 12)}`,
        height: el.getBoundingClientRect().height }))),
  };
}

async function checkBar(page, spec, width, base, out) {
  await page.goto(`${base}${spec.path}`, { waitUntil: 'load' });
  const bar = page.locator(spec.bar).first();
  await bar.waitFor({ state: 'visible', timeout: 20000 });
  await page.waitForTimeout(500); // fonts and the last layout pass
  const { fields, controls } = await page.evaluate(measure, spec.bar);
  const at = `${spec.name}@${width}`;
  // Below 640px an sb-toolbar may hold every control in its sheet (inlineFrom): no inline field is not a defect there.
  const sheetOnly = width < 640 && spec.bar === 'sb-toolbar';
  check(`fields-${at}`, fields.length > 0 || sheetOnly, 'no sb-field in the bar');
  const rows = bottomVerdict(fields);
  check(`bottom-edge-${at}`, rows.length === 0, rows.join('; '));
  const heights = heightVerdict(controls, controlHeightAt(width));
  check(`control-h-${at}`, heights.length === 0, `expected ${controlHeightAt(width)}px: ${heights.join(', ')}`);
  await bar.screenshot({ path: join(out, `${spec.name}@${width}.png`) });
}

async function runViewport(browser, state, viewport, base, out) {
  const { width, height } = viewport;
  const context = await browser.newContext({
    storageState: state, viewport: { width, height }, serviceWorkers: 'block', hasTouch: width < 1024, isMobile: width < 640,
  });
  const page = await context.newPage();
  try {
    for (const spec of BARS) await checkBar(page, spec, width, base, out);
  } finally {
    await context.close();
  }
}

function checkAudit(file) {
  const { unallowed = [] } = JSON.parse(readFileSync(file, 'utf8'));
  const found = auditVerdict(unallowed);
  check('layout-audit-bar-pages', found.length === 0, found.join('; '));
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const out = opts.out ?? join(tmpdir(), 'swingbot-v246-bar-alignment');
  mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  try {
    const state = await signedInState(browser, opts.base);
    for (const viewport of VIEWPORTS) await runViewport(browser, state, viewport, opts.base, out);
  } finally {
    await browser.close();
  }
  if (opts.audit) checkAudit(opts.audit);
  else console.log('no --audit file: the layout-audit findings were not checked');
  writeFileSync(join(out, 'results.json'), JSON.stringify(results, null, 2));
  console.log(`${results.filter((r) => r.ok).length}/${results.length} passed; shots and results.json in ${out}`);
  return exitCode(results);
}

main().then((code) => process.exit(code), (error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(2);
});
```

- [ ] **Step 4: Run the audit and the check against a local replica**

Bring up the local replica the layout audit uses (`docs/claude/ui-design.md` § Checklist): `/replicate-prod-db`, then `cd frontend && npm run build`, then `python admin_ui.py` (base `http://localhost:1234`). Then, from the worktree root:

```bash
node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,820,1440 --out "$TMPDIR/v246-audit"
node frontend/scripts/v246-bar-alignment-check.mjs --base http://localhost:1234 --out "$TMPDIR/v246-bars" --audit "$TMPDIR/v246-audit/audit.json"
```

(`$TMPDIR` is any scratch directory; on Git Bash use the session's scratchpad path.)

Expected: the check prints 46 lines, all `PASS` — `fields-`, `bottom-edge-` and `control-h-` for 5 bars × 3 widths, then `layout-audit-bar-pages` — and `46/46 passed`, exit 0. The audit's own exit code may be 1 for findings on other pages; list them in the task report for plan B, they are not this task's.

A `FAIL` is a defect in the task that owns that bar, fixed there before this task closes: `bottom-edge-` or a `fields-` miss → the bar's consumer task (Trades V246-7, Calendar V246-8, Analytics V246-9, Watchlist and Dashboard V246-10) or the bar primitives (V246-5, V246-6); `control-h-` → the control (V246-4) or the consumer; `layout-audit-bar-pages` → the page's consumer task. Fix in that file with its own spec updated, commit it scoped to that task's id (`fix(v246): V246-8 …`), rebuild, and re-run both commands until the check exits 0. Open each PNG in the `--out` directory once: every bar should read as one tidy row (or tidy rows at 390).

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed (`tests/scripts/test_node_scripts.py` runs the new `.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/v246-bar-alignment-check.mjs frontend/scripts/v246-bar-alignment-check-lib.mjs frontend/scripts/v246-bar-alignment-check-lib.test.mjs
git commit -m "test(v246): closing browser check -- one bottom edge per bar row and --control-h controls at 390/820/1440, plus the layout audit on the bar pages" -m "Index Goal and Handoff 9: Trades, Calendar, Analytics, Watchlist and Dashboard bars measured in Chromium (28px at 1440, 44px at 820 and 390); audit.json overflow/tap/text findings on those pages fail the check. Run against a local replica: 46/46 passed."
```

